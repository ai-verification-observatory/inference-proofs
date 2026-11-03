"""Job state machine, run-id allocation and run directory writing (RFC-0010).

One job is one system, one workload, one shape and one repetition on one machine. Every job
reaches `written`; a failed job is written with its failure record, never dropped
(INV-RUN-4, AGENTS.md rule 5).
"""

import json
import os
import shutil
import statistics
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

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
from iproofs.log import Event, JsonlLogger
from iproofs.log.redact import Redactor
from iproofs.measure import EventLog, ReleaseWatcher, span_seconds
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
from iproofs.provenance import file_digest, file_records, git_state, proof_digest
from iproofs.quantity import Scope, Unit
from iproofs.schema import SchemaRegistry
from iproofs.serialize import write_json, write_jsonl
from iproofs.workloads import load_workload, materialise_prompts, model_dir, workload_digest

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

    def machine_record(self) -> dict[str, object]: ...
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

    def machine_record(self) -> dict[str, object]:
        return {}

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
    proof_records: list[dict[str, object]] = field(default_factory=list)


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
        self.controls_done = False
        self.redact = Redactor.from_host()

    # ---------------------------------------------------------------- public

    def run_many(self, base: JobSpec, repetitions: int) -> list[Path]:
        below = repetitions < MIN_REPETITIONS  # allowed for tests, always marked
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
        (staging / "job.lock").write_text(json.dumps({"pid": os.getpid(), "boot_id": _boot_id()}))
        with (staging / "logs/harness.jsonl").open("w") as stream:
            log = JsonlLogger(stream, redactor=self.redact, mono=self.clock)
            log.log(Event.RUNNER_START, job=run_id, harness_version=__version__)
            actions: dict[str, Callable[[Job], None]] = {
                "resolved": self._resolve,
                "image_ready": self._image,
                "machine_recorded": self._machine,
                "info": self._info,
                "setup": self._setup,
                "commit": self._commit,
                "prove": self._prove,
                "verify": self._verify,
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
                except Exception:  # a harness bug is still recorded (INV-RUN-4)
                    text = self.redact(traceback.format_exc())
                    job.failure = Failure.build(
                        ErrorKind.INTERNAL,
                        state,
                        text.splitlines()[-1],
                        last_lines=text.splitlines(),
                    )
                if job.failure is not None:
                    log.log(
                        Event.JOB_FAILED,
                        job=run_id,
                        step=state,
                        kind=str(job.failure.kind),
                        message=job.failure.message,
                        exit_code=job.failure.exit_code,
                    )
                    break
            final = self._write(job)
            log.log(
                Event.JOB_WRITTEN,
                job=run_id,
                step="written",
                run_dir=final.name,
                outcome="failed" if job.failure else "completed",
            )
        final.parent.joinpath(f".staging-{run_id}").rename(final)
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

    def _machine(self, job: Job) -> None:
        job.machine = self.env.machine_record()

    def _call(
        self,
        job: Job,
        sub: str,
        extra: dict[str, object],
        io: Path | None = None,
        *,
        control: bool = False,
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
        (job.staging / "logs" / f"{sub}.stderr").open("a").write(
            self.redact("\n".join(result.stderr_tail)) + "\n"
        )
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
        job.commit, _ = self._call(job, "commit", {"model_dir": "/models"})
        io = IoDirs(job.staging / "io")
        files = {
            k: file_records([io.host(p, "commit") for p in getattr(job.commit, k) or ()])
            for k in ("verifier_files", "prover_files")
        }
        job.commitment_record = {"commitment_id": job.commit.commitment_id, **files}

    def _prove(self, job: Job) -> None:
        assert job.system is not None
        assert job.workload is not None
        assert job.commit is not None
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
            )
        finally:
            end = job.steps["prove"].ended_mono_ns if "prove" in job.steps else None
            releases = watcher.stop(call_end_ns=end)
        job.warnings += check_proofs(IoDirs(job.staging / "io"), out, job.system)
        watcher.check_unchanged()
        job.proofs, job.observable = out, watcher.observable
        for entry in out.proofs or ():
            d = job.staging / "io/proofs" / entry.proof_id
            parts = [d / name for name in entry.parts]
            job.proof_records.append(
                {
                    "proof_id": entry.proof_id,
                    "digest": proof_digest(d),
                    "parts": file_records(parts),
                    "archive": None,
                }
            )
        job.releases = [(r.proof_id, r.mono_ns) for r in releases]
        for r in releases:
            job.events.record("proof.released", r.mono_ns)

    def _verify(self, job: Job) -> None:
        """Every proof on the verifier profile, then the first on one CPU (RFC-0010)."""
        assert job.proofs is not None
        assert job.commit is not None
        entries = {p.proof_id: p for p in job.proofs.proofs or ()}
        (job.staging / "verifier").mkdir()
        for i, (proof_id, _) in enumerate(job.releases):
            seconds, verdict = self._verify_one(job, proof_id, entries[proof_id], single=False)
            job.verify_seconds[proof_id], job.verdicts[proof_id] = seconds, verdict
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
        assert job.commit is not None
        files = []
        for container_path in job.commit.verifier_files or ():
            host = IoDirs(job.staging / "io").host(container_path, "verify")
            (io / "verifier").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(host, io / "verifier" / host.name)
            files.append(f"/io/verifier/{host.name}")
        return files

    def _verifier_profile(self, job: Job) -> str:
        profiles = job.reference.profiles if job.reference else {}
        return "verifier-cpu" if "verifier-cpu" in profiles else job.spec.profile

    # ---------------------------------------------------------------- written

    def _write(self, job: Job) -> Path:
        spec = job.spec
        final = Path(spec.results_root) / spec.release / spec.system / job.run_id
        run_json = self._pointer(final / "run.json")
        metrics: dict[str, QuantityTree] = {}
        if job.failure is None:
            metrics = self._metrics(job, run_json)
        proofs = [
            {
                "proof_id": pid,
                "release_mono_ns": ns,
                "tokens_covered": sum(self._tokens(job)[i]),
                "verdict": job.verdicts.get(pid),
            }
            for i, (pid, ns) in enumerate(job.releases)
        ]
        warnings = list(job.warnings)
        doc = {
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
            "proofs": proofs,
            "warnings": warnings,
        }
        errors = self.registry.errors("run/1", doc)
        if errors:
            raise IProofsError(ErrorKind.INTERNAL, "run.json fails run/1: " + "; ".join(errors))
        write_json(job.staging / "run.json", doc)
        if job.workload is not None and job.system is not None:
            manifest = self._manifest(job)
            errors = self.registry.errors("manifest/1", manifest)
            if errors:
                raise IProofsError(
                    ErrorKind.INTERNAL, "manifest fails manifest/1: " + "; ".join(errors)
                )
            write_json(job.staging / "manifest.json", manifest)
        # proof bytes never stay in a run directory (RFC-0009) unless --keep-io (RFC-0010)
        for scratch in (
            ("verify", "controls-io") if self.keep_io else ("io", "verify", "controls-io")
        ):
            shutil.rmtree(job.staging / scratch, ignore_errors=True)
        (job.staging / "job.lock").unlink()
        return final

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


def _statistic(values: list[float], unit: Unit, scope: Scope, ref: str) -> QuantityTree:
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
    job = Job(spec, doc["run_id"], run_dir)
    runner._resolve_inputs(job)
    job.image = json.loads((run_dir / "manifest.json").read_text())["system"]["image"]["ref"]
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
