"""Job state machine, run-id allocation and run directory writing (RFC-0010).

One job is one system, one workload, one shape and one repetition on one machine. Every job
reaches `written`; a failed job is written with its failure record, never dropped
(INV-RUN-4, AGENTS.md rule 5).
"""

import errno
import json
import os
import shutil
import statistics
import time
import traceback
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol, TextIO

from iproofs import __version__
from iproofs.adapter import ContainerRunner, IoDirs, StepResult, check_proofs
from iproofs.controls import (
    HonestProof,
    VerifyCall,
    VerifyResult,
    controls_document,
    new_control_seed,
    run_shared_controls,
)
from iproofs.derive import (
    QuantityTree,
    derive_repetition,
    honest_verdict_failure,
    measured,
    scope_seconds,
    tokens_metrics,
    tokens_per_proof,
)
from iproofs.errors import ErrorKind, Failure, IProofsError
from iproofs.log import Event, JsonlLogger, Progress
from iproofs.log.redact import Redactor
from iproofs.measure import (
    LOG_HEAD_BYTES,
    LOG_TAIL_BYTES,
    Capture,
    EventLog,
    ReleaseWatcher,
    StepResources,
    cap_text,
    files_bytes,
    proof_size,
    select_readers,
    span_seconds,
)
from iproofs.model import (
    AdapterOut,
    ClaimCard,
    ProofEntry,
    ProverProfile,
    ReferenceFile,
    System,
    Workload,
    card_path,
    load,
    load_reference,
)
from iproofs.provenance import (
    Host,
    file_digest,
    file_records,
    git_state,
    machine_drift,
    machine_record,
)
from iproofs.quantity import NullReason, Scope, Unit
from iproofs.schema import SchemaRegistry
from iproofs.serialize import write_json, write_jsonl, write_text
from iproofs.workloads import load_workload, materialise_prompts, model_dir, workload_digest

# RFC-0014 §The commitment record: <job tmp>/commitment/{verifier,prover}/, never mounted
# read-write (kept with io/ under --keep-io); prover-ro/ holds the rechecked copies mounted
# read-only for prove.
RUN_DIR_CAP_BYTES = 10 * 1024 * 1024  # RFC-0009 §Storage, a limit
SECOND_CUT_HEAD_BYTES = 64 * 1024
SECOND_CUT_TAIL_BYTES = 192 * 1024
COMMITMENT_STORE = "commitment"
STORE_SIDES = {"verifier_files": "verifier", "prover_files": "prover"}
SCRATCH = (COMMITMENT_STORE, "prover-ro")

STATES = (
    "pending",
    "resolved",
    "image_ready",
    "machine_recorded",
    "info",
    "setup",
    "commit",
    "prove",
    "verify",
    "controls",
    "written",
)
MIN_REPETITIONS = 3


@dataclass(frozen=True, slots=True)
class JobSpec:
    system: str
    workload: str
    workload_version: int
    profile: str
    repetition: int  # 1-based index within this invocation
    control_suite: bool
    results_root: str
    release: str


class Environment(Protocol):
    """The host side of a job: machine record, GPU and CPU binding (RFC-0006)."""

    def host(self) -> Host: ...
    def gpu(self) -> int | None: ...
    def cpus(self, role: Literal["prover", "verifier", "verifier_1"]) -> tuple[str, str]: ...


@dataclass(frozen=True, slots=True)
class RunnerIdentity:
    """Who ran the job (RFC-0007 tiers read it). Self-declared; #83 adds the CLI flags."""

    handle: str
    organisation: str
    affiliated_systems: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> "RunnerIdentity":
        systems = os.environ.get("IPROOFS_RUNNER_SYSTEMS", "")
        return cls(
            os.environ.get("IPROOFS_RUNNER", "undeclared"),
            os.environ.get("IPROOFS_RUNNER_ORG", "undeclared"),
            tuple(s for s in systems.split(",") if s),
        )


class CpuOnlyEnvironment:
    """A CPU-only host for profiles without a GPU (`ci-cpu`); the GPU host path is #73 to #76."""

    def host(self) -> Host:
        return Host()

    def gpu(self) -> int | None:
        return None

    def cpus(self, role: Literal["prover", "verifier", "verifier_1"]) -> tuple[str, str]:
        return "0", "0"


def allocate_run_id(results_root: Path, spec: JobSpec, date: str) -> tuple[str, Path]:
    """INV-RUN-6: the smallest unused n; the staging directory is created atomically."""
    parent = results_root / spec.release / spec.system
    parent.mkdir(parents=True, exist_ok=True)
    n = 1
    while True:
        run_id = f"{date}-{spec.system}-{spec.workload}-{spec.profile}-{n}"
        staging = parent / f".staging-{run_id}"
        if not (parent / run_id).exists():
            try:
                staging.mkdir()
            except FileExistsError:
                pass
            else:
                return run_id, staging
        n += 1


@dataclass(slots=True)
class Job:
    spec: JobSpec
    run_id: str
    staging: Path
    state: str = "pending"
    steps: dict[str, StepResult] = field(default_factory=dict)
    failure: Failure | None = None
    events: EventLog = field(default_factory=EventLog)
    # resolved inputs
    system: System | None = None
    workload: Workload | None = None
    reference: ReferenceFile | None = None
    reference_file: str = ""
    models: Path | None = None
    seed: int = 0
    prompts: list[list[int]] = field(default_factory=list)
    image: str = ""
    machine: dict[str, object] = field(default_factory=dict)
    commit: AdapterOut | None = None
    proofs: AdapterOut | None = None
    releases: list[tuple[str, int]] = field(default_factory=list)
    observable: bool = False
    verify_seconds: dict[str, float] = field(default_factory=dict)
    verdicts: dict[str, str] = field(default_factory=dict)
    single_thread_seconds: float | None = None
    warnings: list[str] = field(default_factory=list)
    commands: list[dict[str, object]] = field(default_factory=list)
    prompt_set_digest: str = ""
    image_inputs: list[dict[str, object]] = field(default_factory=list)
    commitment_record: dict[str, object] | None = None
    logs: dict[str, Capture] = field(default_factory=dict)  # "<step>.stdout" -> bounded capture
    log_prefix: str = ""  # "controls-" when `iproofs controls` adds calls to a written run
    resources: dict[str, StepResources] = field(default_factory=dict)  # step -> readings
    proof_records: list[dict[str, object]] = field(default_factory=list)
    proof_bytes: dict[str, int] = field(default_factory=dict)


class Runner:
    def __init__(  # noqa: PLR0913 (keyword-only configuration)
        self,
        containers: ContainerRunner,
        *,
        root: Path,
        registry: SchemaRegistry,
        env: Environment | None = None,
        clock: Callable[[], int] = time.monotonic_ns,
        image: str | None = None,
        operator: RunnerIdentity | None = None,
        provider: str = "undeclared",
        replay_seed: int | None = None,
        keep_io: bool = False,
        progress: TextIO | None = None,
        log_level: str = "info",
    ) -> None:
        self.containers = containers
        self.root = root
        self.registry = registry
        self.env = env or CpuOnlyEnvironment()
        self.clock = clock
        self.image = image
        self.operator = operator or RunnerIdentity.from_env()
        self.provider = provider
        # RFC-0003 §Seed policy: a fresh seed per job, or a recorded one replayed (--prompts-from)
        self.replay_seed = replay_seed
        self.keep_io = keep_io
        self.progress = progress  # stderr for progress lines; None with --quiet
        self.log_level = log_level
        self.repetitions = 1
        self.controls_done = False
        self.redact = Redactor.from_host()

    # ---------------------------------------------------------------- public

    def run_many(self, base: JobSpec, repetitions: int) -> list[Path]:
        below = repetitions < MIN_REPETITIONS  # allowed for tests, always marked
        self.repetitions = repetitions
        return [
            self.run(replace(base, repetition=r), below_minimum=below)
            for r in range(1, repetitions + 1)
        ]

    def run(self, spec: JobSpec, *, below_minimum: bool = False, seed: int | None = None) -> Path:
        """Drive one job from `pending` to `written`; returns the run directory."""
        date = datetime.now(UTC).date().isoformat()
        results = Path(spec.results_root)
        run_id, staging = allocate_run_id(results, spec, date)
        job = Job(spec, run_id, staging, events=EventLog(clock=self.clock))
        seed = self.replay_seed if seed is None else seed
        job.seed = int.from_bytes(os.urandom(8), "big") if seed is None else seed
        if below_minimum:
            job.warnings.append("repetitions_below_minimum")
        (staging / "logs").mkdir()
        lock = {
            "pid": os.getpid(),
            "boot_id": _boot_id(),
            "run_id": run_id,
            "spec": asdict(spec),
            "seed": f"0x{job.seed:016x}",
        }
        (staging / "job.lock").write_text(json.dumps(lock))
        with (staging / "logs/harness.jsonl").open("w") as stream:
            progress = (
                Progress(self.progress, spec.repetition, self.repetitions, self.redact)
                if self.progress is not None
                else None
            )
            log = JsonlLogger(
                stream,
                level=self.log_level,
                redactor=self.redact,
                mono=self.clock,
                on_record=progress,
            )
            log.log(Event.RUNNER_START, job=run_id, harness_version=__version__)
            actions: dict[str, Callable[[Job], None]] = {
                "resolved": self._resolve,
                "image_ready": self._image,
                "machine_recorded": self._machine,
                "info": self._info,
                "setup": self._setup,
                "commit": self._commit,
                "prove": lambda j: self._prove(j, log),
                "verify": lambda j: self._verify(j, log),
                "controls": lambda j: self._controls(j, log),
            }
            for state in STATES[1:-1]:  # resolved .. controls
                if state == "controls" and not (spec.control_suite and not self.controls_done):
                    continue  # once per configuration, on the first successful repetition
                previous, job.state = job.state, state
                log.log(Event.JOB_STATE, job=run_id, step=state, **{"from": previous, "to": state})
                try:
                    actions[state](job)
                except IProofsError as e:
                    job.failure = self.redact.failure(Failure.from_error(e, step=state))
                except OSError as e:
                    if e.errno != errno.ENOSPC:
                        raise
                    job.failure = Failure.build(ErrorKind.RESOURCE, state, "disk full (ENOSPC)")
                except Exception:  # a harness bug is still recorded (INV-RUN-4)
                    text = self.redact(traceback.format_exc())
                    job.failure = Failure.build(
                        ErrorKind.INTERNAL,
                        state,
                        text.splitlines()[-1],
                        last_lines=text.splitlines(),
                    )
                if job.failure is not None:
                    if job.failure.kind is ErrorKind.TIMEOUT:
                        timeout = job.system.timeout(state) if job.system else None
                        log.log(Event.STEP_TIMEOUT, job=run_id, step=state, timeout_s=timeout)
                    elif job.failure.kind is ErrorKind.RESOURCE:
                        log.log(Event.STEP_OOM, job=run_id, step=state)
                    log.log(
                        Event.JOB_FAILED,
                        job=run_id,
                        step=state,
                        kind=str(job.failure.kind),
                        message=job.failure.message,
                        exit_code=job.failure.exit_code,
                    )
                    break
            self._machine_drift(job, log)
            final = self._write(job, log)
            log.log(
                Event.JOB_WRITTEN,
                job=run_id,
                step="written",
                run_dir=final.name,
                outcome="failed" if job.failure else "completed",
            )
        self._cap_run_dir(job)
        final.parent.joinpath(f".staging-{run_id}").rename(final)
        _fsync_dir(final.parent)  # the run directory exists only complete (INV-RUN-2)
        return final

    def recover(self, results_root: Path) -> list[Path]:
        """Crash recovery (RFC-0010): an abandoned staging directory becomes a failed run.

        A staging directory whose runner is still alive on this boot means another runner is
        active on the tree: exit 3. A recovered job is never continued (INV-RUN-3).
        """
        recovered = []
        for staging in sorted(results_root.glob("*/*/.staging-*")):
            lock_file = staging / "job.lock"
            lock = json.loads(lock_file.read_text()) if lock_file.is_file() else {}
            if lock.get("boot_id") == _boot_id() and _alive(int(lock.get("pid", 0))):
                raise IProofsError(
                    ErrorKind.ENVIRONMENT,
                    f"another runner is active on {results_root} (pid {lock['pid']})",
                )
            if "spec" not in lock:
                raise IProofsError(
                    ErrorKind.INTERNAL, f"{staging.name}: no job.lock to recover from"
                )
            recovered.append(self._recover_one(staging, lock))
        return recovered

    def _recover_one(self, staging: Path, lock: dict[str, object]) -> Path:
        spec = JobSpec(**lock["spec"])  # type: ignore[arg-type]
        run_id = str(lock["run_id"])
        job = Job(spec, run_id, staging, seed=int(str(lock["seed"]), 16))
        log_path = staging / "logs/harness.jsonl"
        states = (
            [json.loads(line).get("to") for line in log_path.open()] if log_path.exists() else []
        )
        last = next((st for st in reversed(states) if st), "pending")
        try:  # inputs for the manifest; nothing is run again
            self._resolve_inputs(job)
            self._image(job)
            prompts = staging / "io/prompts.jsonl"
            job.prompt_set_digest = file_digest(prompts) if prompts.is_file() else ""
        except IProofsError:
            job.workload = None
        job.failure = Failure.build(ErrorKind.INTERNAL, last, "runner terminated before completion")
        if not job.prompt_set_digest:
            job.workload = None  # never resolved: no manifest can be written
        (staging / "logs").mkdir(exist_ok=True)
        with log_path.open("a") as stream:
            JsonlLogger(stream, redactor=self.redact, mono=self.clock).log(
                Event.RUNNER_RECOVERED, job=run_id, run_id=run_id, last_state=last
            )
        final = self._write(job)
        self._cap_run_dir(job)
        staging.rename(final)
        _fsync_dir(final.parent)
        return final

    # ---------------------------------------------------------------- states

    def _resolve(self, job: Job) -> None:
        assert job.workload is None
        self._resolve_inputs(job)
        assert job.workload is not None
        assert job.models is not None
        job.prompts = materialise_prompts(self.root, job.workload, job.models, job.seed)
        io = job.staging / "io"
        io.mkdir()
        job.prompt_set_digest = write_jsonl(io / "prompts.jsonl", job.prompts)

    def _resolve_inputs(self, job: Job) -> None:
        """System, workload, reference file and the hash-checked model directory."""
        spec = job.spec
        system = load(self.root / "systems" / spec.system / "system.yaml", self.registry)
        if not isinstance(system, System):
            raise IProofsError(
                ErrorKind.CONFIG, f"systems/{spec.system}/system.yaml is not a system"
            )
        if spec.workload not in system.workload_ids():
            raise IProofsError(
                ErrorKind.CONFIG, f"{spec.system} does not list workload {spec.workload}"
            )
        wl = load_workload(
            spec.workload, spec.workload_version, root=self.root, registry=self.registry
        )
        job.reference, job.reference_file = self._reference(spec)
        job.system, job.workload = system, wl
        job.models = model_dir(self.root, wl)

    def _reference(self, spec: JobSpec) -> tuple[ReferenceFile, str]:
        """The release's reference file, or the CI file for CI-only profiles (`ci-cpu`)."""
        for release in (spec.release, "ci"):
            path = self.root / "reference" / f"{release}.yaml"
            if path.is_file():
                ref = load_reference(release, self.root, self.registry)
                if spec.profile in ref.profiles:
                    return ref, f"reference/{release}.yaml"
        raise IProofsError(ErrorKind.CONFIG, f"profile {spec.profile!r} is in no reference file")

    def _image(self, job: Job) -> None:
        assert job.system is not None
        if self.image is not None:
            job.image = self.image
        elif job.system.image is not None:
            job.image = f"{job.system.image.repository}@{job.system.image.digest}"
        else:
            raise IProofsError(ErrorKind.CONFIG, f"{job.spec.system} has no pinned image")

    def _record(self, job: Job) -> dict[str, object]:
        """RFC-0006 §Machine record from the environment's allowlisted probes."""
        roles = ("prover", "verifier", "verifier_1")
        return machine_record(
            self.env.host(),
            results=Path(job.spec.results_root),
            gpu_index=self.env.gpu(),
            cpus={role: _cpu_list(self.env.cpus(role)[0]) for role in roles},  # type: ignore[arg-type]
            mems=_cpu_list(self.env.cpus("prover")[1]),
            provider=self.provider,
            redact=self.redact,
        )

    def _machine_drift(self, job: Job, log: JsonlLogger) -> None:
        """INV-MR-2: collected again after the last step; drift is an environment failure."""
        if job.failure is not None or not job.machine:
            return
        changed = machine_drift(job.machine, self._record(job))
        if changed:
            message = f"machine record changed during the job: {'; '.join(changed)}"
            job.failure = Failure.build(ErrorKind.ENVIRONMENT, "written", self.redact(message))
            log.log(
                Event.JOB_FAILED,
                job=job.run_id,
                step="written",
                kind="environment",
                message=job.failure.message,
                exit_code=None,
            )

    def _machine(self, job: Job) -> None:
        job.machine = self._record(job)
        assert job.reference is not None
        profile = job.reference.profiles[job.spec.profile]
        gpu = isinstance(profile, ProverProfile) and profile.gpu is not None
        select_readers(gpu_profile=gpu)  # null readers only without a GPU; never a fallback

    def _call(
        self,
        job: Job,
        sub: str,
        extra: dict[str, object],
        io: Path | None = None,
        *,
        control: bool = False,
        ro_mounts: Sequence[tuple[Path, str]] = (),
    ) -> tuple[AdapterOut, StepResult]:
        assert job.system is not None
        assert job.workload is not None
        io = io or job.staging / "io"
        shape = job.workload.shape
        write_json(
            io / "job.json",
            {
                "schema": "adapter-job/1",
                "contract": "adapter/1",
                "subcommand": sub,
                "run_id": job.run_id,
                "workload": {"id": job.workload.id, "version": job.workload.version},
                "shape": {
                    "prompt_tokens": shape.prompt_tokens,
                    "output_tokens": shape.output_tokens,
                    "batch_size": shape.batch_size,
                    "batches_per_session": shape.batches_per_session,
                    "context_window": shape.context_window,
                },
                "control": control,
                **extra,
            },
        )
        role: Literal["prover", "verifier", "verifier_1"] = (
            "prover" if sub != "verify" else ("verifier_1" if extra.get("_single") else "verifier")
        )
        job_json = json.loads((io / "job.json").read_text())
        job_json.pop("_single", None)
        write_json(io / "job.json", job_json)
        cpuset, mems = self.env.cpus(role)
        started_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        result = self.containers.run(
            job.image,
            sub,
            io,
            models_dir=job.models if sub != "verify" else None,
            gpu=self.env.gpu() if sub != "verify" else None,
            cpuset=cpuset,
            mems=mems,
            memory=None,
            timeout_s=job.system.timeout(sub),
            ro_mounts=ro_mounts,
            log_sinks=[
                job.logs.setdefault(f"{job.log_prefix}{sub}.{s}", Capture())
                for s in ("stdout", "stderr")
            ],
        )
        gpu = self.env.gpu() if sub != "verify" else None
        job.commands.append(
            {
                "step": sub,
                "argv": [self.redact(a) for a in result.argv] or [sub],
                "cpuset": cpuset,
                "mems": mems,
                "gpus": None if gpu is None else f"device={gpu}",
                "network": "none",
                "started_at": started_at,
                "exit_code": result.exit_code,
            }
        )
        if sub != "verify":
            job.steps[sub] = result
            job.events.record(f"{sub}.start", result.started_mono_ns)
            job.events.record(f"{sub}.end", result.ended_mono_ns)
        for stream in ("stdout", "stderr"):  # at most 1 MiB each, so a crash keeps them
            name = f"{job.log_prefix}{sub}.{stream}"
            if job.logs[name].total:
                (job.staging / "logs" / name).write_text(self.redact(job.logs[name].text()))
        if sub in {"commit", "prove"} and result.exit_code == 0:
            shutil.copyfile(io / "out.json", io / f"{sub}.out.json")
        if result.exit_code != 0 or result.out is None:
            raise IProofsError(
                ErrorKind.ADAPTER,
                f"{sub} exited {result.exit_code}",
                step=sub,
                exit_code=result.exit_code,
                last_lines=result.stderr_tail,
            )
        return result.out, result

    def _info(self, job: Job) -> None:
        assert job.system is not None
        out, _ = self._call(job, "info", {})
        job.image_inputs = [
            {"name": i.name, "url": i.url, "digest": i.digest} for i in out.image_inputs or ()
        ]
        pinned = job.system.upstream.commit if job.system.upstream else None
        if pinned is not None and out.upstream_commit != pinned:
            raise IProofsError(
                ErrorKind.INTEGRITY,
                f"info reports upstream {out.upstream_commit}, system.yaml pins {pinned}",
            )

    def _setup(self, job: Job) -> None:
        self._call(job, "setup", {})

    def _commit(self, job: Job) -> None:
        """RFC-0014 §The commitment record: copy the commit step's files into a store no
        later container mounts read-write, and record their digests."""
        job.commit, _ = self._call(job, "commit", {"model_dir": "/models"})
        io = IoDirs(job.staging / "io")
        records: dict[str, object] = {"commitment_id": job.commit.commitment_id}
        for kind, side in STORE_SIDES.items():
            store = job.staging / COMMITMENT_STORE / side
            store.mkdir(parents=True)
            copies = []
            for container_path in getattr(job.commit, kind) or ():
                src = io.host(container_path, "commit")
                dst = store / src.name
                if src.is_symlink() or not src.is_file() or dst.exists():
                    raise IProofsError(
                        ErrorKind.ADAPTER,
                        f"{container_path}: not a regular file, or a second file of that name",
                        step="commit",
                    )
                shutil.copyfile(src, dst)
                copies.append(dst)
            records[kind] = file_records(copies)
        job.commitment_record = records

    def _recorded(self, job: Job, kind: str, into: Path, step: str) -> list[Path]:
        """Copies of the recorded files of one side in `into`, each digest rechecked against
        the manifest record immediately before the call that uses them (RFC-0014)."""
        assert job.commitment_record is not None
        entries = job.commitment_record[kind]
        assert isinstance(entries, list)
        copies = []
        for entry in entries:
            name, digest = str(entry["name"]), str(entry["digest"])
            dst = into / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(job.staging / COMMITMENT_STORE / STORE_SIDES[kind] / name, dst)
            dst.chmod(0o444)
            if file_digest(dst) != digest:
                raise IProofsError(
                    ErrorKind.INTEGRITY,
                    f"{STORE_SIDES[kind]} file {name} does not match the commit record",
                    step=step,
                )
            copies.append(dst)
        return copies

    def _commitment_echo(self, job: Job) -> list[str]:
        """RFC-0014 rule 5: prove output that echoes the commitment is noted, never used."""
        assert job.commitment_record is not None
        found = []
        raw = json.loads((job.staging / "io/prove.out.json").read_text())
        if _has_key(raw, "commitment_id"):
            found.append("policy: prove out.json names commitment_id; verify uses the record")
        entries = job.commitment_record["verifier_files"]
        assert isinstance(entries, list)
        recorded = {str(e["digest"]): str(e["name"]) for e in entries}
        report = job.proofs.binding_report if job.proofs else None
        if report and file_digest(IoDirs(job.staging / "io").host(report, "prove")) in recorded:
            found.append(f"policy: binding report {report} equals a recorded verifier file")
        for proof in job.proof_records:
            for part in proof["parts"]:  # type: ignore[attr-defined]
                if part["digest"] in recorded:
                    found.append(
                        f"policy: proof {proof['proof_id']} part {part['name']} equals the "
                        f"recorded verifier file {recorded[part['digest']]}"
                    )
        return found

    def _prove(self, job: Job, log: JsonlLogger | None = None) -> None:
        assert job.system is not None
        assert job.workload is not None
        assert job.commit is not None
        # the recorded prover files, read-only over the paths the commit step wrote
        recorded = self._recorded(job, "prover_files", job.staging / "prover-ro", "prove")
        ro = list(zip(recorded, job.commit.prover_files or (), strict=True))
        watcher = ReleaseWatcher(
            job.staging / "io/proofs",
            clock=self.clock,
            incremental_proofs=job.system.incremental_proofs,
        )
        watcher.start()
        try:
            out, _ = self._call(
                job,
                "prove",
                {
                    "commitment_id": job.commit.commitment_id,
                    "prover_files": list(job.commit.prover_files or ()),
                    "model_dir": "/models",
                    "prompts_file": "/io/prompts.jsonl",
                    "batch_size": job.workload.shape.batch_size,
                    "batches": job.workload.shape.batches_per_session,
                },
                ro_mounts=ro,
            )
        finally:
            end = job.steps["prove"].ended_mono_ns if "prove" in job.steps else None
            releases = watcher.stop(call_end_ns=end)
        job.warnings += check_proofs(IoDirs(job.staging / "io"), out, job.system)
        watcher.check_unchanged()
        job.proofs, job.observable = out, watcher.observable
        io_root = job.staging / "io"
        for entry in out.proofs or ():
            size = proof_size(io_root / "proofs" / entry.proof_id, io_root)  # Z-1 to Z-3
            job.proof_records.append(
                {
                    "proof_id": entry.proof_id,
                    "digest": size.digest,
                    "parts": [{"name": n, "digest": d, "bytes": b} for n, b, d in size.parts],
                    "archive": None,
                }
            )
            job.proof_bytes[entry.proof_id] = size.bytes
        job.releases = [(r.proof_id, r.mono_ns) for r in releases]
        for i, r in enumerate(releases, start=1):
            job.events.record("proof.released", r.mono_ns)
            if log is not None:
                log.log(
                    Event.PROOF_RELEASED,
                    job=job.run_id,
                    step="prove",
                    proof_id=r.proof_id,
                    release_mono_ns=r.mono_ns,
                    index=i,
                    of=len(releases),
                )
        for warning in self._commitment_echo(job):
            job.warnings.append(warning)
            if log is not None:
                log.log(Event.POLICY_WARNING, job=job.run_id, step="prove", detail=warning)

    def _verify(self, job: Job, log: JsonlLogger | None = None) -> None:
        """Every proof on the verifier profile, then the first on one CPU (RFC-0010)."""
        assert job.proofs is not None
        assert job.commit is not None
        entries = {p.proof_id: p for p in job.proofs.proofs or ()}
        (job.staging / "verifier").mkdir()
        for i, (proof_id, _) in enumerate(job.releases):
            seconds, verdict = self._verify_one(job, proof_id, entries[proof_id], single=False)
            job.verify_seconds[proof_id], job.verdicts[proof_id] = seconds, verdict
            if log is not None:
                record = json.loads((job.staging / "verifier" / f"{proof_id}.json").read_text())
                log.log(
                    Event.VERIFY_RESULT,
                    job=job.run_id,
                    step="verify",
                    proof_id=proof_id,
                    verdict=verdict,
                    raw_exit_code=record["raw_exit_code"],
                    cpus=self.env.cpus("verifier")[0],
                    index=i + 1,
                    of=len(job.releases),
                )
            if i == 0:
                job.single_thread_seconds, _ = self._verify_one(
                    job, proof_id, entries[proof_id], single=True
                )
        failure = honest_verdict_failure(job.verdicts)
        if failure is not None:
            raise failure

    def _verify_one(
        self, job: Job, proof_id: str, entry: ProofEntry, *, single: bool
    ) -> tuple[float, str]:
        """A fresh verify io dir: the proof, the verifier files from the commit record, and the
        commitment from the harness record, never from the proof (AGENTS.md rule 6)."""
        assert job.commit is not None
        io = job.staging / "verify" / (proof_id + ("-1cpu" if single else ""))
        shutil.copytree(job.staging / "io/proofs" / proof_id, io / "proof")
        files = self._verifier_files(job, io)
        request_index = entry.request_index
        out, result = self._call(
            job,
            "verify",
            {
                "commitment_id": job.commit.commitment_id,
                "verifier_files": files,
                "request": job.prompts[request_index],
                "claimed_output": list(entry.claimed_output),
                "proof_dir": "/io/proof",
                "_single": single,
            },
            io=io,
            ro_mounts=[(io / "verifier", "/io/verifier")] if files else [],
        )
        result_path = job.staging / "verifier" / f"{proof_id}{'-1cpu' if single else ''}.json"
        write_json(
            result_path,
            {
                "verdict": out.verdict,
                "raw_exit_code": out.raw_exit_code,
                "raw_last_line": out.raw_last_line,
                "seconds": out.seconds,
            },
        )
        # the harness wall time of the call, not the adapter-reported seconds (INV-GRADE-2)
        return span_seconds(result.started_mono_ns, result.ended_mono_ns), str(out.verdict)

    # ---------------------------------------------------------------- controls

    def honest_proofs(self, job: Job) -> list[HonestProof]:
        assert job.proofs is not None
        assert job.workload is not None
        entries = {p.proof_id: p for p in job.proofs.proofs or ()}
        batch = job.workload.shape.batch_size
        return [
            HonestProof(
                pid,
                tuple(job.prompts[entries[pid].request_index]),
                tuple(entries[pid].claimed_output),
                job.verdicts.get(pid, ""),
                ns,
                entries[pid].request_index // batch,
            )
            for pid, ns in job.releases
        ]

    def _controls(self, job: Job, log: JsonlLogger) -> None:
        """The shared control suite against the honest proofs (RFC-0008 §Where controls run)."""
        assert job.commit is not None
        assert job.workload is not None
        seed = new_control_seed()
        work = job.staging / "controls-io"
        trials = 0

        def verify(call: VerifyCall) -> VerifyResult:
            nonlocal trials
            trials += 1
            io = work / f"call-{trials}"
            shutil.copytree(call.proof_dir, io / "proof")
            files = self._verifier_files(job, io)
            out, result = self._call(
                job,
                "verify",
                {
                    "commitment_id": call.commitment_id,
                    "verifier_files": files,
                    "request": list(call.request),
                    "claimed_output": list(call.claimed_output),
                    "proof_dir": "/io/proof",
                },
                io=io,
                control=True,
                ro_mounts=[(io / "verifier", "/io/verifier")] if files else [],
            )
            return VerifyResult(
                str(out.verdict),
                int(out.raw_exit_code or 0),
                str(out.raw_last_line or ""),
                span_seconds(result.started_mono_ns, result.ended_mono_ns),
            )

        proofs = self.honest_proofs(job)
        dirs = {p.proof_id: job.staging / "io/proofs" / p.proof_id for p in proofs}
        records = run_shared_controls(
            proofs,
            dirs,
            str(job.commit.commitment_id),
            None,
            workload=job.workload,
            seed=seed,
            verify=verify,
            work=work / "mutations",
        )
        for r in records:
            for t in r["trials"]:  # type: ignore[attr-defined]
                log.log(
                    Event.CONTROL_TRIAL,
                    job=job.run_id,
                    step="controls",
                    control=r["id"],
                    trial=t["seed_index"],
                    outcome=t["outcome"],
                )
            twin = r["twin"]
            if r["outcome"] == "void" and isinstance(twin, dict):
                log.log(
                    Event.CONTROL_TWIN_MISMATCH,
                    job=job.run_id,
                    step="controls",
                    control=r["id"],
                    twin_verdict=twin["verdict"],
                )
        doc = controls_document(
            job.run_id, seed, job.image, self._verifier_profile(job), None, records
        )
        if doc["disclosure_pending"]:
            log.log(
                Event.CONTROL_DISCLOSURE_PENDING,
                job=job.run_id,
                step="controls",
                control=[r["id"] for r in records if r["outcome"] == "accepted"],
            )
        errors = self.registry.errors("controls/1", doc)
        if errors:
            raise IProofsError(
                ErrorKind.INTERNAL, "controls.json fails controls/1: " + "; ".join(errors)
            )
        write_json(job.staging / "controls.json", doc)
        self.controls_done = True

    def _verifier_files(self, job: Job, io: Path) -> list[str]:
        """The recorded verifier files in a fresh verify io dir, never the prover's copies."""
        copies = self._recorded(job, "verifier_files", io / "verifier", "verify")
        return [f"/io/verifier/{p.name}" for p in copies]

    def _verifier_profile(self, job: Job) -> str:
        profiles = job.reference.profiles if job.reference else {}
        return "verifier-cpu" if "verifier-cpu" in profiles else job.spec.profile

    # ---------------------------------------------------------------- written

    def _write(self, job: Job, log: JsonlLogger | None = None) -> Path:
        """Assemble, validate and write the run's documents (RFC-0010 §Writing the run directory).

        A document that fails its schema is a harness bug: it is kept under `logs/invalid/`
        and the job is recorded as failed `internal` with documents that do validate.
        """
        spec = job.spec
        final = Path(spec.results_root) / spec.release / spec.system / job.run_id
        run_json = self._pointer(final / "run.json")
        metrics: dict[str, QuantityTree] = {}
        if job.failure is None:
            try:
                metrics = self._metrics(job, run_json)
            except IProofsError as e:
                job.failure = self.redact.failure(Failure.from_error(e, step="written"))
        doc = self._run_doc(job, metrics)
        manifest = self._manifest(job) if job.workload and job.system else None
        invalid = {"run.json": (doc, self.registry.errors("run/1", doc))}
        if manifest is not None:
            invalid["manifest.json"] = (manifest, self.registry.errors("manifest/1", manifest))
        bad = {name: errors for name, (_, errors) in invalid.items() if errors}
        if bad:
            kept = job.staging / "logs/invalid"
            kept.mkdir(parents=True, exist_ok=True)
            for name in bad:
                (kept / name).write_text(json.dumps(invalid[name][0], indent=2, default=str))
            message = "; ".join(f"{n} fails its schema: {e[0]}" for n, e in sorted(bad.items()))
            job.failure = Failure.build(ErrorKind.INTERNAL, "written", message)
            doc = self._run_doc(job, {})
            manifest = None if "manifest.json" in bad else manifest
        write_json(job.staging / "run.json", doc)
        if manifest is not None:
            write_json(job.staging / "manifest.json", manifest)
        lines = [f"proofs/{p['proof_id']}\t{p['digest']}\n" for p in job.proof_records]
        for name, capture in sorted(job.logs.items()):
            if capture.total:  # the digest of the whole stream, before redaction and cuts
                lines.append(f"logs/{name}\t{capture.digest}\n")
            if capture.elided and log is not None:
                log.log(
                    Event.LOG_TRUNCATED,
                    job=job.run_id,
                    file=f"logs/{name}",
                    elided_bytes=capture.elided,
                )
        write_text(job.staging / "digests.txt", "".join(sorted(lines)))
        # proof bytes never stay in a run directory (RFC-0009) unless --keep-io (RFC-0010)
        for scratch in (
            ("prover-ro", "verify", "controls-io")
            if self.keep_io
            else (*SCRATCH, "io", "verify", "controls-io")
        ):
            shutil.rmtree(job.staging / scratch, ignore_errors=True)
        (job.staging / "job.lock").unlink()
        return final

    def _resource_metrics(self, job: Job, run_json: str) -> dict[str, QuantityTree]:
        """RFC-0004 resource metrics for the steps that ran; a field nothing read is null with
        `not_applicable` (RFC-0011 §Portability, null readers)."""
        m: dict[str, QuantityTree] = {}
        for step, scope in (("commit", Scope.COMMIT), ("prove", Scope.PROVE_SESSION)):
            if step not in job.steps:
                continue
            r = job.resources.get(step, StepResources())
            for metric, value, unit in (
                ("gpu_memory_peak", r.gpu_memory_peak_mib, Unit.MIB),
                ("gpu_util_mean", r.gpu_util_mean_pct, Unit.PERCENT),
                ("gpu_util_p95", r.gpu_util_p95_pct, Unit.PERCENT),
                ("gpu_energy", r.gpu_energy_j, Unit.J),
                ("host_memory_peak_kernel", r.host_memory_peak_kernel, Unit.B),
                ("host_memory_peak_anon", r.host_memory_peak_anon, Unit.B),
                ("cpu_seconds", r.cpu_seconds, Unit.S),
            ):
                m[f"{step}_{metric}"] = measured(
                    value,
                    unit,
                    scope if unit is Unit.S else None,
                    f"{run_json}#/raw/{step}",
                    None if value is not None else NullReason.NOT_APPLICABLE,
                )
        if job.verify_seconds:
            anon = job.resources.get("verify", StepResources()).host_memory_peak_anon
            m["verify_host_memory_peak_anon"] = measured(
                anon,
                Unit.B,
                None,
                f"{run_json}#/raw/verify",
                None if anon is not None else NullReason.NOT_APPLICABLE,
            )
        return m

    def _cap_run_dir(self, job: Job) -> None:
        """RFC-0009 §Storage, after the harness log is closed: each log file at most the first
        256 KiB and last 768 KiB; then the run directory at most 10 MiB, cutting adapter logs
        to 64 KiB and 192 KiB, largest first, and harness.jsonl last. Every log's digest before
        truncation is in digests.txt, and every cut is a `log.truncated` event."""
        logs = job.staging / "logs"
        digests_file = job.staging / "digests.txt"
        digests = (
            dict(line.split("\t", 1) for line in digests_file.read_text().splitlines() if line)
            if digests_file.is_file()
            else {}
        )
        cuts: list[tuple[str, int]] = []

        def cut(path: Path, head: int, tail: int) -> None:
            data = path.read_bytes()
            kept, elided = cap_text(data, head, tail)
            if elided:
                name = path.relative_to(job.staging).as_posix()
                digests.setdefault(name, file_digest(path))
                path.write_bytes(kept)
                cuts.append((name, elided))

        files = sorted(p for p in logs.rglob("*") if p.is_file()) if logs.is_dir() else []
        for path in files:
            name = path.relative_to(job.staging).as_posix()
            digests.setdefault(name, file_digest(path))
            capture = job.logs.get(path.name)
            if not (capture and capture.elided and path.parent == logs):  # cut once at capture
                cut(path, LOG_HEAD_BYTES, LOG_TAIL_BYTES)

        def size() -> int:
            return sum(p.stat().st_size for p in job.staging.rglob("*") if p.is_file())

        adapter = [p for p in files if p.suffix in (".stdout", ".stderr")]
        for path in [*sorted(adapter, key=lambda p: -p.stat().st_size), logs / "harness.jsonl"]:
            if size() <= RUN_DIR_CAP_BYTES or not path.is_file():
                break
            cut(path, SECOND_CUT_HEAD_BYTES, SECOND_CUT_TAIL_BYTES)
        write_text(digests_file, "".join(f"{k}\t{v}\n" for k, v in sorted(digests.items())))
        if cuts:
            with (logs / "harness.jsonl").open("a") as stream:
                log = JsonlLogger(stream, redactor=self.redact, mono=self.clock)
                for name, elided in cuts:
                    log.log(Event.LOG_TRUNCATED, job=job.run_id, file=name, elided_bytes=elided)

    def _run_doc(self, job: Job, metrics: dict[str, QuantityTree]) -> dict[str, object]:
        spec = job.spec
        tokens = self._tokens(job) if metrics else [(0, 0)] * len(job.releases)
        return {
            "schema": "run/1",
            "run_id": job.run_id,
            "release": spec.release,
            "system": spec.system,
            "workload": {"id": spec.workload, "version": spec.workload_version},
            "profile": spec.profile,
            "repetition": spec.repetition,
            "control": False,
            "system_kind": job.system.kind if job.system else "test",
            "claim": None,
            "status": "failed" if job.failure else "completed",
            "failure": job.failure.to_json() if job.failure else None,
            "replaces": None,
            "raw": {},
            "adapter_phases": {},
            "metrics": metrics,
            "events": job.events.events,
            "proofs": [
                {
                    "proof_id": pid,
                    "release_mono_ns": ns,
                    "tokens_covered": sum(tokens[i]),
                    "verdict": job.verdicts.get(pid),
                }
                for i, (pid, ns) in enumerate(job.releases)
            ],
            "warnings": list(job.warnings),
        }

    def _manifest(self, job: Job) -> dict[str, object]:
        """manifest.json: everything needed to rerun the job (RFC-0014 §manifest.json)."""
        assert job.system is not None
        assert job.workload is not None
        spec, system, wl = job.spec, job.system, job.workload
        harness_commit, harness_dirty = git_state(
            self.root, ["harness", "pyproject.toml", "uv.lock"]
        )
        _, adapter_dirty = git_state(self.root, [f"systems/{system.name}"])
        card = card_path(self.root, system.name, "default")
        card_doc = load(card, self.registry) if card else None
        claim = (
            {
                "system": system.name,
                "configuration": card_doc.configuration,
                "card_version": card_doc.card_version,
            }
            if isinstance(card_doc, ClaimCard)
            else None
        )
        source = wl.model.source
        verifier = self._verifier_profile(job)
        return {
            "schema": "manifest/1",
            "run_id": job.run_id,
            "release": spec.release,
            "control": False,
            "harness": {
                "version": __version__,
                "git_commit": harness_commit,
                "git_dirty": harness_dirty,
                "lock_digest": file_digest(self.root / "uv.lock"),
                "nonconforming": False,
            },
            "runner": {
                "handle": self.operator.handle,
                "organisation": self.operator.organisation,
                "affiliated_systems": list(self.operator.affiliated_systems),
            },
            "claim": claim,
            "provider": self.provider,
            "system": {
                "name": system.name,
                "system_manifest_digest": file_digest(
                    self.root / "systems" / system.name / "system.yaml"
                ),
                "claim_digest": file_digest(card) if card else None,
                "upstream": (
                    {"repo": system.upstream.repo, "commit": system.upstream.commit}
                    if system.upstream
                    else None
                ),
                "adapter_commit": harness_commit,
                "adapter_dirty": adapter_dirty,
                "image": {
                    "ref": job.image,
                    "digest_kind": "config" if job.image.startswith("local/") else "manifest",
                },
                "image_inputs": job.image_inputs,
            },
            "workload": {
                "id": wl.id,
                "version": wl.version,
                "file_digest": workload_digest(self.root, wl.id),
                "model": {
                    "source": f"{source.hub}:{source.path or source.repo}",
                    "revision": wl.model.revision,
                    "digest": wl.model.digest,
                },
                "corpus_digest": wl.prompts.corpus_digest,
                "prompt_seed": f"0x{job.seed:016x}",
                "prompt_set_digest": job.prompt_set_digest,
            },
            "profile": {
                "prover": spec.profile,
                "verifier": verifier,
                "verifier_host": "same_as_prover",
                "reference_file": job.reference_file,
                "reference_digest": file_digest(self.root / job.reference_file),
            },
            "machine": job.machine,
            "self_test": {"passed": False, "checks": []},  # not run until #116; ineligible
            "commands": job.commands,
            "commitment": job.commitment_record if system.kind != "reference" else None,
            "proofs": job.proof_records,
            "warnings": job.warnings,
        }

    def _pointer(self, path: Path) -> str:
        full = path.resolve() if path.exists() else path.absolute()
        root = self.root.resolve()
        return full.relative_to(root).as_posix() if full.is_relative_to(root) else str(full)

    def _tokens(self, job: Job) -> list[tuple[int, int]]:
        assert job.system is not None
        assert job.workload is not None
        if job.proofs is None or job.system.proofs is None:
            return []
        entries = {p.proof_id: p for p in job.proofs.proofs or ()}
        kind = job.system.proofs.tokens_covered
        return [
            tokens_per_proof(kind, job.workload.shape, entries[pid].tokens_covered, pid)
            for pid, _ in job.releases
        ]

    def _metrics(self, job: Job, run_json: str) -> dict[str, QuantityTree]:
        assert job.workload is not None
        assert job.reference is not None
        m = scope_seconds(
            job.events.first(),
            [ns for _, ns in job.releases],
            observable=job.observable,
            run_json=run_json,
        )
        per_proof = self._tokens(job)
        m |= tokens_metrics(per_proof, run_json)
        shape = job.workload.shape

        def count(v: int) -> QuantityTree:
            return measured(v, Unit.COUNT, None, f"{run_json}#/proofs", None)

        m["requests_count"] = count(shape.batch_size * shape.batches_per_session)
        m["proofs_count"] = count(len(job.releases))
        m["verdicts_accept_count"] = count(sum(v == "accept" for v in job.verdicts.values()))
        sizes = [float(job.proof_bytes[pid]) for pid, _ in job.releases]
        bref = f"{run_json}#/proofs"
        if sizes:
            m["proof_bytes"] = _statistic(sizes, Unit.B, None, bref)
        m["proof_bytes_total"] = measured(sum(sizes), Unit.B, None, bref, None)
        if job.commit is not None:
            io_root = job.staging / "io"
            for metric, files in (
                ("verifier_download_bytes", job.commit.verifier_files),
                ("prover_keep_bytes", job.commit.prover_files),
            ):
                m[metric] = measured(
                    files_bytes(list(files or ()), io_root),
                    Unit.B,
                    None,
                    f"{run_json}#/proofs",
                    None,
                )
        m |= self._resource_metrics(job, run_json)
        walls = [job.verify_seconds[pid] for pid, _ in job.releases]
        vref = f"{run_json}#/verifier"
        m["verify_seconds"] = _statistic(walls, Unit.S, Scope.VERIFY, vref)
        m["verify_seconds_total"] = measured(sum(walls), Unit.S, Scope.VERIFY, vref, None)
        if job.single_thread_seconds is not None:
            m["verify_single_thread_seconds"] = _statistic(
                [job.single_thread_seconds], Unit.S, Scope.VERIFY_SINGLE_THREAD, vref
            )
        profile = job.reference.profiles[job.spec.profile]
        gpus = profile.gpu.count if isinstance(profile, ProverProfile) and profile.gpu else 0
        price_ptr = f"{job.reference_file}#/cost/price_per_gpu_hour_usd"
        params_ptr = f"workloads/{job.workload.id}.yaml#/model/parameters/active_per_token"
        price_q = json.loads(json.dumps(_price_tree(self.root / job.reference_file)))
        params_q = {
            "value": job.workload.model.parameters.active_per_token,
            "tier": "reported",
            "source": {"kind": "harness", "ref": ""},
        }
        first = (
            {
                "value": sum(per_proof[0]),
                "tier": "reported",
                "source": {"kind": "harness", "ref": ""},
            }
            if per_proof
            else None
        )
        m |= derive_repetition(
            m,
            run_json=run_json,
            harness_version=__version__,
            gpus=gpus,
            price=(price_ptr, price_q),
            active_parameters=(params_ptr, params_q),
            first_proof_tokens=(f"{run_json}#/proofs/0/tokens_covered", first),
        )
        return m


def _statistic(values: list[float], unit: Unit, scope: Scope | None, ref: str) -> QuantityTree:
    """A measured statistic over proofs of one repetition (RFC-0004 §Recorded metrics)."""
    mean = statistics.mean(values)
    q = measured(mean, unit, scope, ref, None)
    q["stats"] = {
        "n": len(values),
        "n_failed": 0,
        "mean": mean,
        "stdev": statistics.stdev(values) if len(values) >= 2 else None,
        "min": min(values),
        "max": max(values),
    }
    return q


def _price_tree(path: Path) -> dict[str, object]:
    from iproofs.schema import parse_tree  # noqa: PLC0415

    cost = parse_tree(path)["cost"]
    assert isinstance(cost, dict)
    price = cost["price_per_gpu_hour_usd"]
    assert isinstance(price, dict)
    return price


def _boot_id() -> str:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return "unknown"


def recorded_seed(run_dir: Path, workload: str, version: int) -> int:
    """The prompt seed a run recorded, for replay; its workload must be the same one."""
    manifest = run_dir / "manifest.json"
    if not manifest.is_file():
        raise IProofsError(ErrorKind.CONFIG, f"{run_dir} has no manifest.json to replay")
    recorded = json.loads(manifest.read_text())["workload"]
    if (recorded["id"], recorded["version"]) != (workload, version):
        raise IProofsError(
            ErrorKind.CONFIG,
            f"{run_dir} ran {recorded['id']} v{recorded['version']}, not {workload} v{version}",
        )
    return int(recorded["prompt_seed"], 16)


def controls_for_run(runner: Runner, run_dir: Path) -> Path:
    """`iproofs controls RUN_DIR`: the control suite against a completed run whose proof bytes
    were kept (`--keep-io`); adds `controls.json` to the run directory (append-only)."""
    if (run_dir / "controls.json").exists():
        raise IProofsError(ErrorKind.CONFIG, f"{run_dir} already has controls.json")
    io = run_dir / "io"
    if not (io / "proofs").is_dir() or not (io / "prove.out.json").is_file():
        raise IProofsError(ErrorKind.CONFIG, f"{run_dir} kept no proofs; rerun with --keep-io")
    doc = json.loads((run_dir / "run.json").read_text())
    if doc["status"] != "completed":
        raise IProofsError(
            ErrorKind.CONFIG, f"{run_dir} did not complete; controls need accepted proofs"
        )
    spec = JobSpec(
        doc["system"],
        doc["workload"]["id"],
        doc["workload"]["version"],
        doc["profile"],
        doc["repetition"],
        True,
        str(run_dir.parent.parent.parent),
        doc["release"],
    )
    job = Job(spec, doc["run_id"], run_dir, log_prefix="controls-")
    runner._resolve_inputs(job)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    job.image = manifest["system"]["image"]["ref"]
    job.commitment_record = manifest["commitment"]  # digests rechecked before every verify
    if not (run_dir / COMMITMENT_STORE).is_dir():
        raise IProofsError(ErrorKind.CONFIG, f"{run_dir} kept no commitment store")
    job.prompts = [json.loads(line) for line in (io / "prompts.jsonl").read_text().splitlines()]
    for name, attr in (("commit", "commit"), ("prove", "proofs")):
        out = load(io / f"{name}.out.json", runner.registry)
        assert isinstance(out, AdapterOut)
        setattr(job, attr, out)
    job.releases = [(p["proof_id"], p["release_mono_ns"]) for p in doc["proofs"]]
    job.verdicts = {p["proof_id"]: p["verdict"] for p in doc["proofs"]}
    with (run_dir / "logs/harness.jsonl").open("a") as stream:
        runner._controls(job, JsonlLogger(stream, redactor=runner.redact, mono=runner.clock))
    shutil.rmtree(run_dir / "controls-io", ignore_errors=True)
    return run_dir / "controls.json"


def _cpu_list(spec: str) -> list[int]:
    """`0-3,8` -> [0, 1, 2, 3, 8] (a docker cpuset string)."""
    out: list[int] = []
    for part in filter(None, spec.split(",")):
        low, _, high = part.partition("-")
        out += range(int(low), int(high or low) + 1)
    return out


def _has_key(doc: object, key: str) -> bool:
    if isinstance(doc, dict):
        return key in doc or any(_has_key(v, key) for v in doc.values())
    return isinstance(doc, list) and any(_has_key(v, key) for v in doc)


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by another user
    return True


FETCH_BACKOFF_S = (2.0, 8.0, 32.0)
FETCH_ATTEMPTS = 3


def retry_fetch[T](
    op: Callable[[], T],
    what: str,
    *,
    log: JsonlLogger | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """RFC-0010 §Retry policy: only fetches retry, up to 3 attempts, outside every timed scope.

    The wait before attempt n + 1 is FETCH_BACKOFF_S[n - 1]; with three attempts the waits are
    2 s and 8 s. Errors of any other kind are raised at once.
    """
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        try:
            return op()
        except IProofsError as e:
            if e.kind is not ErrorKind.FETCH:
                raise
            if attempt == FETCH_ATTEMPTS:
                if log:
                    log.log(Event.FETCH_FAILED, what=what, attempts=attempt)
                raise
            backoff = FETCH_BACKOFF_S[attempt - 1]
            if log:
                log.log(Event.FETCH_ATTEMPT, what=what, attempt=attempt, backoff_s=backoff)
            sleep(backoff)
    raise AssertionError("unreachable")
