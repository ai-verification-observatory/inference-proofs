"""Job state machine, run-id allocation and run directory writing (RFC-0010).

One job is one system, one workload, one shape and one repetition on one machine. Every job
reaches `written`; a failed job is written with its failure record, never dropped
(INV-RUN-4, AGENTS.md rule 5).
"""

import errno
import json
import os
import re
import shutil
import statistics
import time
import traceback
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol, TextIO

from iproofs import __version__, selftest
from iproofs.adapter import ContainerRunner, IoDirs, StepResult, check_proofs
from iproofs.controls import (
    EXPECTED,
    HonestProof,
    NotApplicable,
    VerifyCall,
    VerifyResult,
    controls_document,
    new_control_seed,
    perturb_model,
    prover_side_record,
    run_shared_controls,
    system_control_record,
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
    CgroupReader,
    EventLog,
    NullCgroupReader,
    ReleaseWatcher,
    Sampler,
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
    PerturbedCommitmentRecord,
    ProofEntry,
    ProverProfile,
    ReferenceFile,
    ReferenceWorkload,
    System,
    SystemControl,
    SystemControls,
    Workload,
    card_path,
    load,
    load_reference,
)
from iproofs.provenance import (
    ConformanceFailure,
    Host,
    archive_proof,
    check_profile,
    file_digest,
    file_records,
    git_state,
    machine_drift,
    machine_record,
    model_digest,
    proof_digest,
    select_cpus,
    usable_topology,
)
from iproofs.quantity import NullReason, Scope, Unit, check_closed_division
from iproofs.schema import SchemaRegistry
from iproofs.serialize import write_json, write_jsonl, write_text
from iproofs.workloads import (
    asserted_inputs,
    default_cache,
    ensure_model,
    load_workload,
    materialise_prompts,
    model_dir,
    workload_digest,
)

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


class GpuEnvironment:
    """A GPU host (RFC-0006 §CPU and memory selection): the bound GPU by NVML index, the
    prover's CPUs on its NUMA node and the verifier's elsewhere, a pure function of the
    topology. `n_prover` is the profile's `cpu.logical_cpus_on_gpu_numa_node`; a hosted host
    binds only CPUs of its own scheduler affinity (`usable_topology`)."""

    def __init__(self, gpu_index: int, host: Host, n_prover: int) -> None:
        self._host, self._gpu = host, gpu_index
        node = host.gpu(gpu_index).get("numa_node")
        if not isinstance(node, int) or node < 0:
            raise IProofsError(ErrorKind.ENVIRONMENT, f"no NUMA node for GPU {gpu_index} (NVML)")
        self.binding = select_cpus(usable_topology(host), node, n_prover=n_prover)

    def host(self) -> Host:
        return self._host

    def gpu(self) -> int | None:
        return self._gpu

    def cpus(self, role: Literal["prover", "verifier", "verifier_1"]) -> tuple[str, str]:
        cpus = self.binding.roles()[role]
        return ",".join(map(str, cpus)), ",".join(map(str, self.binding.mems))


class CpuOnlyEnvironment:
    """A CPU-only host for profiles without a GPU (`ci-cpu`); the GPU host path is #73 to #76."""

    def host(self) -> Host:
        return Host()

    def gpu(self) -> int | None:
        return None

    def cpus(self, role: Literal["prover", "verifier", "verifier_1"]) -> tuple[str, str]:
        """Prover on CPU 0, verifier on CPU 1 (RFC-0006: the two never overlap); a one-CPU
        host has nowhere else to put the verifier and is refused by the overlap check."""
        verifier = "1" if (os.cpu_count() or 1) > 1 else "0"
        return ("0" if role == "prover" else verifier), "0"


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


JOB_CONFIGURATION = "default"  # v0.1 jobs carry no configuration (JobSpec, system.yaml)


def job_card(root: Path, registry: SchemaRegistry, system: str) -> tuple[Path, ClaimCard] | None:
    """The claim card a job of `system` records in its manifest, with its path:
    `claims/default.yaml`, else a single `claim.yaml` (RFC-0002 §File and identity). A v0.1 job
    names no configuration, so a system whose only cards are `claims/<other>.yaml` records
    none."""
    card = card_path(root, system, JOB_CONFIGURATION)
    doc = load(card, registry) if card else None
    return (card, doc) if card and isinstance(doc, ClaimCard) else None


def check_card_class(root: Path, registry: SchemaRegistry, system: System, wl: Workload) -> None:
    """RFC-0003 §Divisions: a closed workload admits only a card with its exact `claim_class`,
    so a job of another class, or of a system with no card the job records (`job_card`), is a
    `config` error before any container starts. A reference system has no card (RFC-0015) and
    runs on every workload."""
    if wl.division != "closed" or system.kind == "reference":
        return
    found = job_card(root, registry, system.name)
    if found is None:
        where = f"systems/{system.name}/claims/{JOB_CONFIGURATION}.yaml"
        raise IProofsError(
            ErrorKind.CONFIG,
            f"closed workload {wl.id} fixes claim_class {wl.claim_class!r}; "
            f"{system.name} has no claim card a job records ({where} or "
            f"systems/{system.name}/claim.yaml)",
        )
    check_closed_division(wl.division, wl.claim_class, found[1].claim_class)


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
    adapter_build: tuple[str | None, bool | None] = (None, None)  # (commit, dirty) from info
    commitment_record: dict[str, object] | None = None
    logs: dict[str, Capture] = field(default_factory=dict)  # "<step>.stdout" -> bounded capture
    log_prefix: str = ""  # "controls-" when `iproofs controls` adds calls to a written run
    resources: dict[str, StepResources] = field(default_factory=dict)  # step -> readings
    proof_records: list[dict[str, object]] = field(default_factory=list)
    proof_bytes: dict[str, int] = field(default_factory=dict)
    archive: tuple[str, str, int] | None = None  # (proof id, tar digest, bytes), RFC-0014
    agreement: dict[str, dict[str, int | None]] = field(default_factory=dict)  # RFC-0015 RC-3


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
        allow_nonconforming: bool = False,
        prompts_from: str | None = None,
        claims: list[list[int]] | None = None,
        hosted: bool = False,
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
        self.prompts_from = prompts_from  # the source run id, recorded in the manifest
        self.claims = claims  # the source run's claimed outputs, for ref-recompute (RC-1)
        self.keep_io = keep_io
        self.progress = progress  # stderr for progress lines; None with --quiet
        self.log_level = log_level
        self.repetitions = 1
        self.allow_nonconforming = allow_nonconforming  # development only (RFC-0006)
        self.nonconforming: list[ConformanceFailure] = []
        self.controls_done = False
        self.redact = Redactor.from_host()
        self.hosted = hosted  # RFC-0006 §Hosted execution
        self.readers: CgroupReader = NullCgroupReader()

    # ---------------------------------------------------------------- public

    def run_many(self, base: JobSpec, repetitions: int) -> list[Path]:
        below = repetitions < MIN_REPETITIONS  # allowed for tests, always marked
        self.repetitions = repetitions
        self._conform(base)
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
        job.warnings += [f"conformance: {f.line()}" for f in self.nonconforming]
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
                "resolved": lambda j: self._resolve(j, log),
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
                if self._skip(job, state, log):
                    continue
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

    def _resolve(self, job: Job, log: JsonlLogger | None = None) -> None:
        assert job.workload is None
        self._resolve_inputs(job, log)
        assert job.workload is not None
        assert job.models is not None
        self._image(job)  # named before anything below can fail
        if _reference(job) and self._coverage(job) is None:
            raise IProofsError(
                ErrorKind.CONFIG,
                f"{job.spec.workload} lists no proving system whose token rule a reference row"
                " counts by (RFC-0015 REF-3)",
            )
        job.prompts = materialise_prompts(self.root, job.workload, job.models, job.seed)
        io = job.staging / "io"
        io.mkdir()
        job.prompt_set_digest = write_jsonl(io / "prompts.jsonl", job.prompts)
        if _recompute(job):  # RFC-0015 RC-1: the claims come from the --prompts-from run
            if self.claims is None or len(self.claims) < len(job.prompts):
                raise IProofsError(
                    ErrorKind.CONFIG, "a ref-recompute job needs --prompts-from a run with claims"
                )
            write_jsonl(io / "claimed.jsonl", self.claims)

    def _resolve_inputs(self, job: Job, log: JsonlLogger | None = None) -> None:
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
        check_card_class(self.root, self.registry, system, wl)
        job.reference, job.reference_file = self._reference(spec)
        job.system, job.workload = system, wl
        job.models = self._models(wl, log)

    def _models(self, wl: Workload, log: JsonlLogger | None) -> Path:
        """Repository toy data (the fake systems) or the verified cache entry (RFC-0014): fetched
        once, rehashed at every job start outside every timed scope."""
        if wl.model.source.hub == "repository":
            return model_dir(self.root, wl)
        start = self.clock()
        path = ensure_model(
            wl,
            default_cache(),
            retry=lambda op: retry_fetch(op, f"model {wl.id}", log=log),
            token=os.environ.get("HF_TOKEN"),  # to the fetch call only (docs/spec/06)
        )
        if log is not None:
            seconds = span_seconds(start, self.clock())
            log.log(Event.INTEGRITY_MODEL_REHASH, what=wl.id, seconds=seconds)
        return path

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

    def _conform(self, spec: JobSpec) -> None:
        """RFC-0006 §Profile conformance check, once per invocation and before any staging
        directory exists, so a refused host writes nothing to results/ (exit 3). A test system
        (fake, fake-broken) runs anywhere, RFC-0011 §Portability; its failures are warnings."""
        system = load(self.root / "systems" / spec.system / "system.yaml", self.registry)
        assert isinstance(system, System)
        profile = self._reference(spec)[0].profiles[spec.profile]
        if not isinstance(profile, ProverProfile):
            return
        record = self._record_for(spec)
        gpu = record.get("gpu")
        node = gpu.get("numa_node") if isinstance(gpu, dict) else None
        cpus = usable_topology(self.env.host()).cpus
        on_node = sum(c.node == node for c in cpus) if node is not None else None
        failures = check_profile(record, profile, numa_node_cpus=on_node)
        saved = selftest.saved(Path(spec.results_root))
        if saved is not None and not saved.get("passed"):  # RFC-0014: a failed self-test stops
            failures.append(ConformanceFailure("ST", "the host's last self-test failed"))
        if failures and not self.allow_nonconforming and system.kind != "test":
            raise IProofsError(
                ErrorKind.ENVIRONMENT,
                f"this host does not meet profile {spec.profile}: "
                + "; ".join(f.line() for f in failures),
            )
        self.nonconforming = failures

    def _skip(self, job: Job, state: str, log: JsonlLogger) -> bool:
        """Controls run once per configuration, on the first successful repetition (RFC-0008);
        a reference system skips commit, verify and controls (RFC-0015 §Steps per job)."""
        if state == "controls" and not (job.spec.control_suite and not self.controls_done):
            return True
        if _reference(job) and state in ("commit", "verify", "controls"):
            log.log(Event.JOB_STATE, job=job.run_id, step=state, skipped=True,
                    **{"from": job.state, "to": state})  # fmt: skip
            return True
        return False

    def _record(self, job: Job) -> dict[str, object]:
        return self._record_for(job.spec)

    def _record_for(self, spec: JobSpec) -> dict[str, object]:
        """RFC-0006 §Machine record from the environment's allowlisted probes."""
        roles = ("prover", "verifier", "verifier_1")
        return machine_record(
            self.env.host(),
            results=Path(spec.results_root),
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
        prover = set(_cpu_list(self.env.cpus("prover")[0]))
        verifier = set(_cpu_list(self.env.cpus("verifier")[0]))
        if prover & verifier:  # RFC-0006: verification is never disturbed by the prover
            raise IProofsError(
                ErrorKind.ENVIRONMENT,
                f"verifier CPUs {sorted(verifier)} overlap prover CPUs {sorted(prover)}",
            )
        job.machine = self._record(job)
        assert job.reference is not None
        profile = job.reference.profiles[job.spec.profile]
        gpu = isinstance(profile, ProverProfile) and profile.gpu is not None
        # null readers only without a GPU; never a fallback
        self.readers = select_readers(gpu_profile=gpu, hosted=self.hosted)

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
        gpu_index = self.env.gpu() if sub != "verify" else None
        sampler = Sampler(gpu_index, self.readers)
        cpu0, oom0 = self.readers.cpu_usage_usec(), self.readers.oom_kills()
        sampler.start()
        try:
            result = self._run_container(job, sub, io, cpuset, mems, ro_mounts)
        except BaseException:
            sampler.stop(0, 0)  # the call failed before it ended; nothing is recorded
            raise
        summary = sampler.stop(result.started_mono_ns, result.ended_mono_ns)
        cpu1, oom1 = self.readers.cpu_usage_usec(), self.readers.oom_kills()
        if not control:
            job.resources[sub] = StepResources(
                gpu_memory_peak_mib=summary.memory_peak_mib,
                gpu_util_mean_pct=summary.util_mean_pct,
                gpu_util_p95_pct=summary.util_p95_pct,
                gpu_energy_j=summary.energy_j,
                host_memory_peak_kernel=self.readers.memory_peak(),
                host_memory_peak_anon=summary.anon_peak_bytes,
                cpu_seconds=None if cpu0 is None or cpu1 is None else (cpu1 - cpu0) / 1e6,
            )
        if oom0 is not None and oom1 is not None and oom1 > oom0:  # G-6, whatever the exit code
            raise IProofsError(ErrorKind.RESOURCE, f"{oom1 - oom0} OOM kill(s) in {sub}", step=sub)
        gpu = self.env.gpu() if sub != "verify" else None
        job.commands.append(
            {
                "step": sub,
                "argv": [self.redact(a) for a in result.argv] or [sub],
                "cpuset": cpuset,
                "mems": mems,
                "gpus": None if gpu is None else f"device={gpu}",
                "network": "provider" if self.hosted else "none",
                "started_at": started_at,
                "exit_code": result.exit_code,
            }
        )
        return self._after_call(job, sub, io, result, control)

    def _run_container(
        self,
        job: Job,
        sub: str,
        io: Path,
        cpuset: str,
        mems: str,
        ro_mounts: Sequence[tuple[Path, str]],
    ) -> StepResult:
        assert job.system is not None
        return self.containers.run(
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

    def _after_call(
        self, job: Job, sub: str, io: Path, result: StepResult, control: bool
    ) -> tuple[AdapterOut, StepResult]:
        if sub != "verify" and not control:  # a control call never moves the run's timing
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
        job.adapter_build = (out.adapter_commit, out.adapter_dirty)  # baked in at build (B6)
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

    def _recorded(
        self,
        job: Job,
        kind: str,
        into: Path,
        step: str,
        record: dict[str, object] | None = None,
        store: Path | None = None,
    ) -> list[Path]:
        """Copies of the recorded files of one side in `into`, each digest rechecked against
        the manifest record immediately before the call that uses them (RFC-0014)."""
        record = record or job.commitment_record
        store = store or job.staging / COMMITMENT_STORE
        assert record is not None
        entries = record[kind]
        assert isinstance(entries, list)
        copies = []
        for entry in entries:
            name, digest = str(entry["name"]), str(entry["digest"])
            dst = into / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(store / STORE_SIDES[kind] / name, dst)
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
        reference = _reference(job)  # RFC-0015: no commitment, outputs instead of proofs
        assert reference or job.commit is not None
        ro: list[tuple[Path, str]] = []
        if job.commit is not None:  # the recorded prover files, read-only (RFC-0014)
            recorded = self._recorded(job, "prover_files", job.staging / "prover-ro", "prove")
            ro = list(zip(recorded, job.commit.prover_files or (), strict=True))
        watcher = ReleaseWatcher(
            job.staging / "io/proofs",
            clock=self.clock,
            incremental_proofs=job.system.incremental_proofs,
        )
        watcher.start()
        fields: dict[str, object] = {"claims_file": "/io/claimed.jsonl"} if _recompute(job) else {}
        args = _engine_args(job)
        try:
            out, _ = self._call(
                job,
                "prove",
                fields
                | {
                    "commitment_id": job.commit.commitment_id if job.commit else "not_applicable",
                    "prover_files": list(job.commit.prover_files or ()) if job.commit else [],
                    "model_dir": "/models",
                    "prompts_file": "/io/prompts.jsonl",
                    "batch_size": job.workload.shape.batch_size,
                    "batches": job.workload.shape.batches_per_session,
                },
                ro_mounts=ro,
            )
        except IProofsError as failure:
            # a failed step under another configuration is that configuration's failure
            problem = engine_command_problem(job.staging / "io", args, required=False)
            if reference and problem is not None:
                raise IProofsError(ErrorKind.CONFIG, problem, step="prove") from failure
            raise
        finally:
            end = job.steps["prove"].ended_mono_ns if "prove" in job.steps else None
            releases = watcher.stop(call_end_ns=end)
        problem = engine_command_problem(job.staging / "io", args, required=True)
        if reference and problem is not None:
            raise IProofsError(ErrorKind.CONFIG, problem, step="prove")
        job.warnings += check_proofs(IoDirs(job.staging / "io"), out, job.system)
        watcher.check_unchanged()
        job.proofs, job.observable = out, watcher.observable
        if _recompute(job):
            assert self.claims is not None
            job.agreement = {
                e.proof_id: agreement(e.claimed_output, self.claims[e.request_index], e.proof_id)
                for e in out.proofs or ()
            }
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
            if not reference:  # REF-2: outputs, not proofs; no proof bytes
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
        for warning in [] if reference else self._commitment_echo(job):
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
        self._archive(job)

    def _check_proof(self, job: Job, proof_id: str, step: str) -> None:
        """RFC-0014: the proof's digest, rechecked immediately before a verify or a control
        mutation, still equals the one taken at its release."""
        recorded = next(p["digest"] for p in job.proof_records if p["proof_id"] == proof_id)
        if proof_digest(job.staging / "io/proofs" / proof_id) != recorded:
            raise IProofsError(
                ErrorKind.INTEGRITY, f"proof {proof_id} changed on disk after release", step=step
            )

    def _archive(self, job: Job) -> None:
        """RFC-0014: one proof per configuration in full, the first proof of repetition 1 that
        verified `accept`, as a deterministic tar under `<results>/.archive/` (never committed;
        uploaded per docs/runbooks/gpu-run.md). Its digest goes into digests.txt."""
        spec = job.spec
        where = Path(spec.results_root) / ".archive" / spec.release / spec.system
        where = where / spec.workload / spec.profile
        first = next((pid for pid, _ in job.releases if job.verdicts.get(pid) == "accept"), None)
        if spec.repetition != 1 or first is None or _reference(job) or any(where.glob("*.tar")):
            return
        job.archive = (first, *archive_proof(job.staging / "io/proofs" / first,
                                             where / f"{job.run_id}-{first}.tar"))  # fmt: skip

    def _verify_one(
        self, job: Job, proof_id: str, entry: ProofEntry, *, single: bool
    ) -> tuple[float, str]:
        """A fresh verify io dir: the proof, the verifier files from the commit record, and the
        commitment from the harness record, never from the proof (AGENTS.md rule 6)."""
        assert job.commit is not None
        io = job.staging / "verify" / (proof_id + ("-1cpu" if single else ""))
        self._check_proof(job, proof_id, "verify")
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

    def _system_controls(
        self, job: Job, verify: Callable[[VerifyCall], VerifyResult], work: Path
    ) -> list[dict[str, object]]:
        """`systems/<name>/controls.yaml` (RFC-0008 §System-specific controls). A weakened prove
        runs in its own io dir with `control: true` and its flags passed explicitly; every verify
        uses the run's recorded commitment (INV-CTRL-6); the run's honest proof is the twin."""
        path = self.root / "systems" / job.spec.system / "controls.yaml"
        if not path.is_file():
            return []
        doc = load(path, self.registry)
        assert isinstance(doc, SystemControls)
        assert job.commit is not None
        assert job.workload is not None
        twin = self._honest_twin(job)

        def weakened(control: SystemControl) -> tuple[list[VerifyCall], object]:
            return self._control_prove(job, control.id, work, flags=control.control_flags or ())

        return [
            system_control_record(c, lambda c=c: weakened(c), lambda: [twin], verify)  # type: ignore[misc]
            for c in doc.controls
        ]

    def _honest_twin(self, job: Job) -> VerifyCall:
        """The run's first honest proof against its own commitment: the twin of every
        prover-side control (RFC-0008 §Honest twins)."""
        assert job.commit is not None
        honest = self.honest_proofs(job)[0]
        honest_dir = job.staging / "io/proofs" / honest.proof_id
        parts = tuple(p.name for p in sorted(honest_dir.iterdir()))
        return VerifyCall("twin", 0, str(job.commit.commitment_id), honest.request,
                          honest.claimed_output, honest_dir, parts, {})  # fmt: skip

    def _control_prove(
        self,
        job: Job,
        control_id: str,
        work: Path,
        *,
        flags: Sequence[str] = (),
        models: Path | None = None,
        batches: int | None = None,
    ) -> tuple[list[VerifyCall], object]:
        """A `prove` with `control: true` in its own io dir: the run's commitment and prover
        files, optionally other weights (P1) or explicit flags (weakened provers). Returns the
        verify calls of its proofs, each against the run's commitment (INV-CTRL-6), and the
        binding report."""
        assert job.commit is not None
        assert job.workload is not None
        commitment = str(job.commit.commitment_id)
        shape = job.workload.shape
        io = work / f"prove-{control_id}"
        io.mkdir(parents=True)
        shutil.copyfile(job.staging / "io/prompts.jsonl", io / "prompts.jsonl")
        if (job.staging / "io/state").is_dir():
            shutil.copytree(job.staging / "io/state", io / "state")
        honest_models = job.models
        job.models = models or honest_models
        try:
            out, _ = self._call(
                job,
                "prove",
                {
                    "commitment_id": commitment,
                    "prover_files": list(job.commit.prover_files or ()),
                    "model_dir": "/models",
                    "prompts_file": "/io/prompts.jsonl",
                    "batch_size": shape.batch_size,
                    "batches": batches or shape.batches_per_session,
                    "control_flags": list(flags),
                },
                io=io,
                control=True,
            )
        finally:
            job.models = honest_models
        check_proofs(IoDirs(io), out, job.system)  # type: ignore[arg-type]
        report = None
        if out.binding_report:
            report = json.loads(IoDirs(io).host(out.binding_report, "prove").read_text())
        calls = [
            VerifyCall(control_id, i, commitment, tuple(job.prompts[e.request_index]),
                       tuple(e.claimed_output), io / "proofs" / e.proof_id, tuple(e.parts), {})
            for i, e in enumerate(out.proofs or ())
        ]  # fmt: skip
        return calls, report

    def _perturbed(self, job: Job) -> PerturbedCommitmentRecord | str:
        """The workload's perturbed commitment for this release and system, or why there is
        none (RFC-0008 C3 and P1 are then `not_applicable` with that reason)."""
        assert job.workload is not None
        spec = job.spec
        path = perturbed_dir(Path(spec.results_root), spec.release, spec.system, spec.workload)
        if not (path / "perturbed.json").is_file():
            return (
                "no perturbed commitment; run iproofs controls --prepare-perturbed " + spec.workload
            )
        record = load(path / "perturbed.json", self.registry)
        assert isinstance(record, PerturbedCommitmentRecord)
        made_for = (record.source_model_digest, record.workload["version"])
        if made_for != (job.workload.model.digest, job.workload.version):
            return "the perturbed commitment was made from other weights or workload version"
        return record

    def _prover_controls(
        self,
        job: Job,
        perturbed: PerturbedCommitmentRecord | str,
        verify: Callable[[VerifyCall], VerifyResult],
        work: Path,
    ) -> list[dict[str, object]]:
        """P1 and P2 (RFC-0008 §Shared controls, prover side), one batch each."""
        twin = self._honest_twin(job)

        def p1() -> list[VerifyCall]:
            if isinstance(perturbed, str):
                raise NotApplicable(perturbed)
            weights = default_cache() / "perturbed" / perturbed.source_model_digest[7:]
            if not weights.is_dir() or model_digest(weights) != perturbed.model_digest:
                raise NotApplicable("the perturbed weights are not on this host")
            return self._control_prove(job, "P1", work, models=weights, batches=1)[0]

        def p2() -> list[VerifyCall]:
            raise NotApplicable("the workload declares one precision")

        return [
            prover_side_record(cid, EXPECTED[cid], "shared", build, lambda: [twin], verify)
            for cid, build in (("P1", p1), ("P2", p2))
        ]

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

        perturbed = self._perturbed(job)
        store = perturbed_dir(Path(job.spec.results_root), job.spec.release, job.spec.system,
                              job.spec.workload) / "commitment"  # fmt: skip

        def verify(call: VerifyCall) -> VerifyResult:
            nonlocal trials
            trials += 1
            io = work / f"call-{trials}"
            if call.proof_dir.parent == job.staging / "io/proofs":  # an honest proof, unmutated
                self._check_proof(job, call.proof_dir.name, "controls")
            shutil.copytree(call.proof_dir, io / "proof")
            if call.mutation.get("commitment") == "perturbed":  # C3: its own verifier files
                assert not isinstance(perturbed, str)
                record = dict(perturbed.commitment)
                files = [f"/io/verifier/{p.name}" for p in self._recorded(
                    job, "verifier_files", io / "verifier", "verify", record, store)]  # fmt: skip
            else:
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
            None if isinstance(perturbed, str) else perturbed.commitment["commitment_id"],  # type: ignore[arg-type]
            workload=job.workload,
            seed=seed,
            verify=verify,
            work=work / "mutations",
            check=lambda proof_id: self._check_proof(job, proof_id, "controls"),
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
        records += self._prover_controls(job, perturbed, verify, work)
        records += self._system_controls(job, verify, work)
        made = None if isinstance(perturbed, str) else {
            "commitment_id": str(perturbed.commitment["commitment_id"]),
            "model_digest": perturbed.model_digest,
        }  # fmt: skip
        doc = controls_document(
            job.run_id, seed, job.image, self._verifier_profile(job), made, records
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
        # a job that failed before its prompts existed was never resolved: no manifest
        resolved = job.workload and job.system and job.prompt_set_digest
        manifest = self._manifest(job) if resolved else None
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
        if job.archive:
            lines.append(f"archive/{job.archive[0]}.tar\t{job.archive[1]}\n")
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
                    None if value is not None else self._null_resource(metric),
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

    def _null_resource(self, metric: str) -> NullReason:
        """Hosted execution cannot read a step's kernel memory peak (RFC-0006)."""
        if self.hosted and metric == "host_memory_peak_kernel":
            return NullReason.NOT_MEASURABLE_ON_PROFILE
        return NullReason.NOT_APPLICABLE

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

    def _claim(self, job: Job, proof_id: str) -> dict[str, object]:
        """The request and claimed output of a proof (RFC-0015 RC-1), with its agreement."""
        entries = job.proofs.proofs or () if job.proofs is not None else ()
        entry = next((e for e in entries if e.proof_id == proof_id), None)
        if entry is None:
            return {}
        out: dict[str, object] = {
            "request_index": entry.request_index,
            "claimed_output": list(entry.claimed_output),
        }
        if proof_id in job.agreement:
            out["agreement"] = job.agreement[proof_id]
        return out

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
                | self._claim(job, pid)
                for i, (pid, ns) in enumerate(job.releases)
            ],
            "warnings": list(job.warnings),
        } | ({"inputs": asserted_inputs(job.workload)} if metrics and job.workload else {})

    def _manifest(self, job: Job) -> dict[str, object]:
        """manifest.json: everything needed to rerun the job (RFC-0014 §manifest.json)."""
        assert job.system is not None
        assert job.workload is not None
        spec, system, wl = job.spec, job.system, job.workload
        harness_commit, harness_dirty = git_state(
            self.root, ["harness", "pyproject.toml", "uv.lock"]
        )
        _, adapter_dirty = git_state(self.root, [f"systems/{system.name}"])
        found = job_card(self.root, self.registry, system.name)
        card, card_doc = found if found else (None, None)
        claim = (
            {
                "system": system.name,
                "configuration": card_doc.configuration,
                "card_version": card_doc.card_version,
            }
            if card_doc is not None
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
                "nonconforming": bool(self.nonconforming) and self.allow_nonconforming,
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
                # the image's own record when it bakes one in (B6), else this checkout's
                "adapter_commit": job.adapter_build[0]
                if re.fullmatch(r"[0-9a-f]{40}", job.adapter_build[0] or "")
                else harness_commit,
                "adapter_dirty": adapter_dirty
                if job.adapter_build[1] is None
                else job.adapter_build[1],
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
            # the host's last self-test from this harness version (RFC-0011); none: ineligible
            "prompts_from": self.prompts_from,
            "self_test": selftest.saved(Path(job.spec.results_root))
            or {"passed": False, "checks": []},
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
        kind = self._coverage(job)
        if job.proofs is None or kind is None:
            return []
        entries = {p.proof_id: p for p in job.proofs.proofs or ()}
        return [
            tokens_per_proof(kind, job.workload.shape, entries[pid].tokens_covered, pid)
            for pid, _ in job.releases
        ]

    def _substituted(self, job: Job) -> bool:
        assert job.system is not None
        return any(
            isinstance(w, ReferenceWorkload) and w.id == job.spec.workload
            and w.precision_substitution is not None
            for w in job.system.workloads
        )  # fmt: skip

    def _coverage(self, job: Job) -> str | None:
        """The token rule: the system's own, or for a reference row the rule of the system it
        serves, the first proving system the workload lists (RFC-0015 REF-3)."""
        assert job.system is not None
        assert job.workload is not None
        if job.system.proofs is not None:
            return job.system.proofs.tokens_covered
        for name in job.workload.systems:
            path = self.root / "systems" / name / "system.yaml"
            served = load(path, self.registry) if path.is_file() else None
            if isinstance(served, System) and served.kind != "reference" and served.proofs:
                return served.proofs.tokens_covered
        return None

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
        for name, key in (("agreement_positions", "agree"), ("disagreement_positions", "disagree")):
            if job.agreement:  # RFC-0015 RC-5, per position over every request
                m[name] = count(sum(int(a[key] or 0) for a in job.agreement.values()))
        m["proofs_count"] = count(len(job.releases))
        m["verdicts_accept_count"] = count(sum(v == "accept" for v in job.verdicts.values()))
        bref = f"{run_json}#/proofs"
        if _reference(job):  # RFC-0015: no commit step, so no commit time and no whole wall
            eref = f"{run_json}#/events"
            na = NullReason.NOT_APPLICABLE
            m["commit_seconds"] = measured(None, Unit.S, Scope.COMMIT, eref, na)
            m["whole_wall_seconds"] = measured(None, Unit.S, Scope.WHOLE_WALL, eref, na)
        else:
            sizes = [float(job.proof_bytes[pid]) for pid, _ in job.releases]
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
        walls = [job.verify_seconds[pid] for pid, _ in job.releases if pid in job.verify_seconds]
        vref = f"{run_json}#/verifier"
        if walls:
            m["verify_seconds"] = _statistic(walls, Unit.S, Scope.VERIFY, vref)
            m["verify_seconds_total"] = measured(sum(walls), Unit.S, Scope.VERIFY, vref, None)
        if job.single_thread_seconds is not None:
            m["verify_single_thread_seconds"] = _statistic(
                [job.single_thread_seconds], Unit.S, Scope.VERIFY_SINGLE_THREAD, vref
            )
        profile = job.reference.profiles[job.spec.profile]
        gpus = profile.gpu.count if isinstance(profile, ProverProfile) and profile.gpu else 0
        pointer = job.reference.price_pointer(job.spec.profile)  # RFC-0006 C7
        price_ptr = f"{job.reference_file}#{pointer}"
        price_q = json.loads(json.dumps(_price_tree(self.root / job.reference_file, pointer)))
        # RFC-0003 WB-4: the workload's asserted inputs, as copied into run.json `inputs`
        inputs = asserted_inputs(job.workload)
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
            active_parameters=(
                f"{run_json}#/inputs/active_parameters_per_token",
                inputs["active_parameters_per_token"],
            ),
            weight_bits=(f"{run_json}#/inputs/weight_bits", inputs["weight_bits"]),
            first_proof_tokens=(f"{run_json}#/proofs/0/tokens_covered", first),
            reference=_reference(job),
        )
        if self._substituted(job):  # RFC-0015 PM-2: every quantity of the row is flagged
            for q in m.values():
                q["quality"] = {**(q.get("quality") or {}), "precision_substituted": True}  # type: ignore[dict-item]
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


def _price_tree(path: Path, pointer: str) -> dict[str, object]:
    """The price quantity at `pointer` (`/cost/...` or `/costs/<basis>/...`) of a reference file."""
    from iproofs.schema import parse_tree  # noqa: PLC0415

    node: object = parse_tree(path)
    for part in pointer.strip("/").split("/"):
        assert isinstance(node, dict)
        node = node[part]
    assert isinstance(node, dict)
    return node


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
    run = run_dir / "run.json"
    if not run.is_file() or json.loads(run.read_text()).get("status") != "completed":
        raise IProofsError(ErrorKind.CONFIG, f"{run_dir} did not complete; nothing to replay")
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
    job.proof_records = manifest["proofs"]  # proof digests rechecked before every control
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


def perturbed_dir(results_root: Path, release: str, system: str, workload: str) -> Path:
    """Where a workload's perturbed commitment lives (RFC-0008 §Shared controls)."""
    return results_root / release / system / "_controls" / workload


def prepare_perturbed(runner: Runner, spec: JobSpec, cache: Path) -> Path:
    """`iproofs controls --prepare-perturbed WORKLOAD` (RFC-0008 C3 and P1): perturb one
    element of the workload's weights into `<cache>/perturbed/<model digest>/`, commit that
    copy through the adapter, and store the commit record and its files under
    `results/<release>/<system>/_controls/<workload>/`. Once per workload per release; the
    perturbed weights stay in the cache on this host."""
    import tempfile  # noqa: PLC0415

    out = perturbed_dir(Path(spec.results_root), spec.release, spec.system, spec.workload)
    if (out / "perturbed.json").exists():
        raise IProofsError(ErrorKind.CONFIG, f"{out} already holds a perturbed commitment")
    with tempfile.TemporaryDirectory() as tmp:
        job = Job(spec, f"perturbed-{spec.workload}", Path(tmp))
        (job.staging / "logs").mkdir()
        (job.staging / "io").mkdir()
        runner._resolve_inputs(job)
        runner._image(job)
        runner._info(job)
        assert job.models is not None
        assert job.workload is not None
        source = model_digest(job.models)
        weights = cache / "perturbed" / source.removeprefix("sha256:")
        shutil.rmtree(weights, ignore_errors=True)
        try:
            change = perturb_model(job.models, weights)
        except NotApplicable as e:
            raise IProofsError(ErrorKind.CONFIG, f"cannot perturb {spec.workload}: {e}") from e
        job.models = weights
        runner._commit(job)
        record: dict[str, object] = {
            "schema": "perturbed-commitment/1",
            "release": spec.release,
            "system": spec.system,
            "workload": {"id": job.workload.id, "version": job.workload.version},
            "source_model_digest": source,
            "model_digest": model_digest(weights),
            "perturbation": asdict(change),
            "commitment": job.commitment_record,
            "image": job.image,
            "harness_version": __version__,
        }
        errors = runner.registry.errors("perturbed-commitment/1", record)
        if errors:
            raise IProofsError(ErrorKind.INTERNAL, "perturbed.json: " + "; ".join(errors))
        out.mkdir(parents=True)
        shutil.copytree(job.staging / COMMITMENT_STORE, out / "commitment")
        write_json(out / "perturbed.json", record)
    return out / "perturbed.json"


def _reference(job: Job) -> bool:
    return job.system is not None and job.system.kind == "reference"


def _engine_args(job: Job) -> tuple[str, ...]:
    """The workload's `engine_args` in system.yaml at the run's commit (RFC-0015 SRV-3)."""
    assert job.system is not None
    return next(
        (w.engine_args for w in job.system.workloads
         if isinstance(w, ReferenceWorkload) and w.id == job.spec.workload),
        (),
    )  # fmt: skip


def engine_command_problem(io: Path, args: Sequence[str], *, required: bool) -> str | None:
    """RFC-0015 SRV-3: the engine command a reference adapter records in /io/commands.jsonl
    (RFC-0005 §Command log) ends with the workload's `engine_args`, verbatim, as system.yaml at
    the run's commit lists them. The adapter reads its options from the system.yaml baked into
    its image, so an image built from another system.yaml (another `--n-cpu-moe` N, for one)
    would otherwise serve one configuration under another's manifest. None when it does, or
    when there is nothing to compare: no `engine_args`, or no engine command and not
    `required` (a step that failed before the engine started)."""
    if not args:
        return None
    path = io / "commands.jsonl"
    recorded: list[list[str]] = []
    for line in path.read_text(errors="replace").splitlines() if path.is_file() else []:
        try:
            doc = json.loads(line)
        except ValueError:
            continue
        argv = doc.get("argv") if isinstance(doc, dict) else None
        if isinstance(argv, list) and all(isinstance(a, str) for a in argv):
            recorded.append(argv)
    if not recorded:
        return (
            f"no engine command in /io/commands.jsonl to check against system.yaml's "
            f"engine_args {list(args)}"
            if required
            else None
        )
    if any(argv[-len(args) :] == list(args) for argv in recorded if len(argv) >= len(args)):
        return None
    return (
        f"the engine command line does not end with system.yaml's engine_args {list(args)} "
        f"(the image's system.yaml differs from the run's commit); recorded: {recorded[-1]}"
    )


def _recompute(job: Job) -> bool:
    return _reference(job) and job.system is not None and job.system.reference_role == "recompute"


def agreement(
    argmax: Sequence[int], claimed: Sequence[int], proof_id: str
) -> dict[str, int | None]:
    """RFC-0015 RC-3 and RC-7: each claimed position against the teacher-forced argmax at that
    position; positions after a disagreement are still compared."""
    if len(argmax) != len(claimed):
        raise IProofsError(
            ErrorKind.ADAPTER,
            f"{proof_id}: {len(argmax)} argmax positions for {len(claimed)} claimed tokens",
            step="prove",
        )
    differ = [i for i, (a, c) in enumerate(zip(argmax, claimed, strict=True)) if a != c]
    return {"agree": len(claimed) - len(differ), "disagree": len(differ),
            "first_disagreement": differ[0] if differ else None}  # fmt: skip


def recorded_claims(run_dir: Path) -> list[list[int]]:
    """The claimed outputs of a completed run, by request index (RFC-0015 RC-1)."""
    proofs = json.loads((run_dir / "run.json").read_text()).get("proofs", [])
    claims = {p.get("request_index"): p.get("claimed_output") for p in proofs}
    if not proofs or None in claims.values() or set(claims) != set(range(len(claims))):
        raise IProofsError(ErrorKind.CONFIG, f"{run_dir}: no claimed outputs in the source run")
    return [list(claims[i]) for i in range(len(claims))]


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
