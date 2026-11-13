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
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol, TextIO

from iproofs import __version__, selftest
from iproofs.adapter import (
    TRACE_FILE,
    ContainerRunner,
    DockerRunner,
    IoDirs,
    StepResult,
    check_proofs,
    check_requests,
)
from iproofs.controls import (
    EXPECTED,
    LEVEL_TRIALS,
    LEVEL_VERIFIER_CONTROLS,
    SEED_RECORD,
    SEED_SCHEMA,
    SHARED_PROVER_CONTROLS,
    SHARED_VERIFIER_CONTROLS,
    HonestProof,
    Mutator,
    NotApplicable,
    Series,
    VerifyCall,
    VerifyResult,
    controls_document,
    disclosure_pending,
    level_control_record,
    merge_parts,
    new_control_seed,
    parse_only,
    part_document,
    part_name,
    parts_read,
    perturb_model,
    prover_side_record,
    run_shared_controls,
    seed_document,
    system_control_record,
)
from iproofs.derive import (
    STEADY_RULE,
    QuantityTree,
    derive_repetition,
    honest_verdict_failure,
    measured,
    released_before_start,
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
    IdleWatch,
    NullCgroupReader,
    ReleaseWatcher,
    Sampler,
    StepResources,
    cap_text,
    files_bytes,
    proof_size,
    reduce_strace,
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
    ServingModel,
    ServingProfile,
    System,
    SystemControl,
    SystemControls,
    VerifierProfile,
    Workload,
    card_path,
    load,
    load_reference,
)
from iproofs.provenance import (
    ConformanceFailure,
    CpuBinding,
    Host,
    archive_proof,
    check_profile,
    file_digest,
    file_records,
    git_state,
    idle_use,
    machine_drift,
    machine_record,
    model_digest,
    proof_digest,
    select_cpus,
    select_verifier_cpus,
    usable_topology,
)
from iproofs.quantity import (
    Grade,
    NullReason,
    Scope,
    SourceKind,
    Tier,
    Unit,
    check_closed_division,
)
from iproofs.replies import read_replies, split_replies
from iproofs.schema import SchemaRegistry
from iproofs.serialize import write_json, write_jsonl, write_text
from iproofs.serving import (
    SHORT_STEADY,
    SIZING_MIN_BATCHES,
    SIZING_WARNING,
    ensure_serving_model,
    record_for,
    serving_manifest,
)
from iproofs.workloads import (
    BEACON_WINDOW,
    asserted_inputs,
    default_cache,
    ensure_model,
    generator_seed,
    hub_download,
    load_workload,
    materialise_prompts,
    model_dir,
    workload_digest,
)

VERIFY_TRACE = "verify-trace"  # RFC-0018 CH-4: <run-dir>/verify-trace/<proof_id>.json
UNTIMED = ("verify", "logprobs", "perturb", "mutate_reply")  # no step of the run's timing
MARKS = ("generation.start", "generation.end")  # RFC-0018 AD-4, under /io/marks

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


@dataclass(frozen=True, slots=True)
class LevelRun:
    """A session of a level (RFC-0018 §Sessions): the level file by digest, the rung whose
    workload the system runs, the slot k (1 to `slots`) whose N prompts prove gets, and the
    request every reply must meet. `beacon` is the level's stored beacon record (`beacon/1`),
    the seed of a `beacon-window/1` workload; None while no round is stored."""

    id: str
    digest: str
    rung: str
    slot: int | None  # None: the serving baseline's ladder run (CO-4), which proves no slot
    slots: int
    requests: int
    prompt_tokens: int
    output_tokens: int
    beacon: Mapping[str, object] | None = None
    ladder: tuple[int, ...] = ()  # CO-4: `baseline.ladder`, `warmup_batches`, `timed_batches`,
    warmup_batches: int = 0  # and the count of distinct ladder prompts (`baseline.prompts`)
    timed_batches: int = 0
    ladder_prompts: int = 0


def level_run(
    root: Path,
    registry: SchemaRegistry,
    level_id: str,
    system: str,
    workload: str,
    slot: int | None,
) -> LevelRun:
    """`iproofs run --level ID --session K`: the level file, the rung on which `system` runs
    `workload`, and slot K. A workload on no rung, or a slot outside 1..slots, is `config`.
    Without a slot (`--load ladder`, CO-4) the rung is the one any system runs `workload` on."""
    from iproofs.level import (  # noqa: PLC0415 (Level 1 only)
        beacon_file,
        level_digest,
        level_file,
        load_beacon,
        load_level,
    )

    level = load_level(root, level_id, registry=registry)
    rung = next((r for r in level.rungs if r.workloads.get(system) == workload
                 or (slot is None and workload in r.workloads.values())), None)  # fmt: skip
    if rung is None:
        raise IProofsError(ErrorKind.CONFIG, f"{level_id} has no rung on which {system} runs "
                           f"{workload}")  # fmt: skip
    if slot is not None and not 1 <= slot <= level.sessions.slots:
        raise IProofsError(ErrorKind.CONFIG, f"--session {slot}: {level_id} has slots 1 to "
                           f"{level.sessions.slots}")  # fmt: skip
    beacon = (
        load_beacon(root, level, registry=registry)
        if beacon_file(root, level.id).is_file()
        else None
    )
    b = level.baseline
    return LevelRun(level.id, level_digest(level_file(root, level.id)), rung.id, slot,
                    level.sessions.slots, rung.requests_per_session,
                    level.request.prompt_tokens, level.request.output_tokens, beacon,
                    tuple(b.ladder), b.warmup_batches, b.timed_batches, b.prompts)  # fmt: skip


@dataclass(frozen=True, slots=True)
class ModelPaths:
    """RFC-0018 CH-4: what a trace path is matched against (container and host forms, with
    their realpaths, taken before any file is removed) and the host files whose presence the
    verify-trace record states."""

    files: frozenset[str]
    dirs: frozenset[str]
    host_files: tuple[Path, ...]


def model_paths(wl: Workload, models: Path | None) -> ModelPaths:
    """The workload's `model.files` under /models and under the host model directory, each
    with its realpath, and the directories themselves."""
    files = {f"/models/{f.path}" for f in wl.model.files}
    dirs = {"/models"}
    host: list[Path] = []
    if models is not None:
        dirs |= {str(models), os.path.realpath(models)}
        for f in wl.model.files:
            host.append(models / f.path)
            files |= {str(models / f.path), os.path.realpath(models / f.path)}
    return ModelPaths(frozenset(files), frozenset(dirs), tuple(host))


class Environment(Protocol):
    """The host side of a job: machine record, GPU and CPU binding (RFC-0006)."""

    def host(self) -> Host: ...
    def gpu(self) -> int | None: ...
    def cpus(self, role: Literal["prover", "verifier", "verifier_1"]) -> tuple[str, str]: ...


# calls that run on the verifier's CPUs with no GPU and no weights: `verify`, and the
# adapter's `mutate_reply` (RFC-0018 AD-6), which a verifier host runs for C1
NO_GPU_CALLS = ("verify", "mutate_reply")


def bound_gpus(env: "Environment") -> tuple[int, ...]:
    """Every GPU the environment binds (RFC-0006 R6): a serving environment's list, else the
    one bound GPU, else none."""
    many = getattr(env, "gpus", None)
    if callable(many):
        return tuple(many())
    one = env.gpu()
    return () if one is None else (one,)


@dataclass(frozen=True, slots=True)
class RunnerIdentity:
    """Who ran the job, as declared (recorded in the manifest)."""

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
    topology. `n_prover` is the profile's `cpu.logical_cpus_on_gpu_numa_node` and `n_verifier`
    verifier-cpu's `cpu.logical_cpus`; a hosted host binds only CPUs of its own scheduler
    affinity (`usable_topology`)."""

    def __init__(self, gpu_index: int, host: Host, n_prover: int, n_verifier: int = 8) -> None:
        self._host, self._gpu = host, gpu_index
        node = host.gpu(gpu_index).get("numa_node")
        if not isinstance(node, int) or node < 0:
            raise IProofsError(ErrorKind.ENVIRONMENT, f"no NUMA node for GPU {gpu_index} (NVML)")
        self.binding = select_cpus(
            usable_topology(host), node, n_prover=n_prover, n_verifier=n_verifier
        )

    def host(self) -> Host:
        return self._host

    def gpu(self) -> int | None:
        return self._gpu

    def cpus(self, role: Literal["prover", "verifier", "verifier_1"]) -> tuple[str, str]:
        cpus = self.binding.roles()[role]
        return ",".join(map(str, cpus)), ",".join(map(str, self.binding.mems))


class ServingEnvironment(GpuEnvironment):
    """A hosted serving host (RFC-0006 R6): `gpu.count` GPUs bound by index (`--gpus`). No
    verifier runs (a reference runs no `verify`), so the server and its tensor-parallel workers
    get every CPU the container may use, over every NUMA node; the first GPU's node must still
    hold `n_prover` of them (PC-CPU-NUMA)."""

    def __init__(self, gpu_indices: Sequence[int], host: Host, n_prover: int) -> None:
        if not gpu_indices or len(set(gpu_indices)) != len(gpu_indices):
            raise IProofsError(ErrorKind.CONFIG, f"--gpus {list(gpu_indices)}: distinct indices")
        super().__init__(gpu_indices[0], host, n_prover, n_verifier=0)  # no verifier
        cpus = usable_topology(host).cpus
        every, nodes = tuple(sorted(c.id for c in cpus)), tuple(sorted({c.node for c in cpus}))
        self.binding = CpuBinding(prover=every, verifier=(), verifier_1=(), mems=nodes)
        self._gpus = tuple(gpu_indices)

    def gpus(self) -> tuple[int, ...]:
        return self._gpus


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


class VerifierEnvironment:
    """A host without a GPU that runs only the verifier-side controls of a stored run
    (RFC-0008 §Split suites): the verifier profile's `n_verifier` CPUs from those this process
    may use (`usable_topology`); it binds no prover, so no prove step runs on it."""

    def __init__(self, host: Host, n_verifier: int) -> None:
        topology = usable_topology(host)
        self._host = host
        self._cpus = select_verifier_cpus(topology, n_verifier)
        node = {c.id: c.node for c in topology.cpus}
        self._mems = ",".join(map(str, sorted({node[c] for c in self._cpus})))

    def host(self) -> Host:
        return self._host

    def gpu(self) -> int | None:
        return None

    def cpus(self, role: Literal["prover", "verifier", "verifier_1"]) -> tuple[str, str]:
        if role == "prover":
            raise IProofsError(ErrorKind.CONFIG, "a verifier host binds no prover CPUs")
        cpus = self._cpus if role == "verifier" else self._cpus[:1]
        return ",".join(map(str, cpus)), self._mems


STATE_AFTER_COMMIT = "state-after-commit.json"  # io/state's top-level entries once commit ended


def copy_state_after_commit(src_io: Path, dst_io: Path) -> None:
    """A control prove's io/state: the entries commit left (RFC-0008 P1: commit W, then prove
    with W'), not what the run's own prove wrote after it (a work directory an adapter makes
    anew, a build cache). A run with no record of them (made before it was kept) gives its
    whole state, as before."""
    state = src_io / "state"
    if not state.is_dir():
        return
    record = src_io / STATE_AFTER_COMMIT
    if not record.is_file():
        shutil.copytree(state, dst_io / "state")
        return
    (dst_io / "state").mkdir(parents=True)
    for name in json.loads(record.read_text()):
        entry = state / name
        if entry.is_dir() and not entry.is_symlink():
            shutil.copytree(entry, dst_io / "state" / name, symlinks=True)
        elif entry.exists() or entry.is_symlink():
            shutil.copy2(entry, dst_io / "state" / name, follow_symlinks=False)


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
    # RFC-0015 SRV-1, SRV-6, SRV-8: a production-serving job's entry, record and shape
    serving_entry: ReferenceWorkload | None = None
    serving_record: ServingModel | None = None
    run_shape: tuple[int, int] | None = None  # (batch size, batches) when not the workload's
    prompt_prefix_digest: str | None = None
    sizing: bool = False  # RFC-0015 SRV-1: a sizing capture (--sizing-batches)
    engine_interface: str | None = None  # from the recorded engine command (RFC-0015 Q8)
    engine_observed: dict[str, object] | None = None  # the engine as the adapter saw it run
    level: Mapping[str, object] | None = None  # manifest `level` of a level session (RFC-0018)
    model_paths: ModelPaths | None = None  # RFC-0018 CH-4, taken before the first verify
    models_removed: bool = False  # hosted level run: the weights left the cache before verify
    optional_subcommands: tuple[str, ...] = ()  # from info (RFC-0018 AD-2)
    ladder: dict[str, object] | None = None  # prove job.json of a ladder run (RFC-0018 CO-4)
    marks: list[tuple[str, int]] = field(default_factory=list)  # (name, mono_ns), AD-4


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
        prompts_from: str | None = None,
        claims: list[list[int]] | None = None,
        hosted: bool = False,
        load: str = "matched",
        source_prompt_digest: str | None = None,
        sizing_batches: int | None = None,
        level: LevelRun | None = None,
        control_run: bool = False,
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
        self.nonconforming: list[ConformanceFailure] = []
        self.controls_done = False
        self.redact = Redactor.from_host()
        self.hosted = hosted  # RFC-0006 §Hosted execution
        self.load = load  # RFC-0015 SRV-1: a production-serving job's load point
        self.source_prompt_digest = source_prompt_digest  # the --prompts-from run's (SRV-8)
        self.sizing_batches = sizing_batches  # RFC-0015 SRV-1: a sizing capture's batch count
        self.readers: CgroupReader = NullCgroupReader()
        self.level = level  # RFC-0018: one run is one session of this slot
        self.control_run = control_run  # CH-1b: one request of the slot, never a session

    # ---------------------------------------------------------------- public

    def run_many(self, base: JobSpec, repetitions: int) -> list[Path]:
        if self.level is not None and repetitions != 1:
            raise IProofsError(ErrorKind.CONFIG, "a level run is one session; it takes no "
                               "repetitions (RFC-0018 SE-1)")  # fmt: skip
        below = repetitions < MIN_REPETITIONS and self.level is None  # tests; always marked
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
        if self.level is not None:
            job.level = {"id": self.level.id, "digest": self.level.digest}
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
            actions: dict[str, Callable[[Job], object]] = {
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
        if self.control_run:  # CH-1b: one request of the slot, at batch 1
            job.run_shape = (1, 1)
        batch, batches = _run_shape(job)
        count = batch * batches
        if self.level is not None and self.load == "ladder":
            job.prompts = self._ladder_prompts(job, count)
        elif self.level is not None and self.control_run:
            job.prompts = self._level_prompts(job, self.level.requests)[:count]
        elif self.level is not None:
            job.prompts = self._level_prompts(job, count)
        else:
            job.prompts = materialise_prompts(
                self.root, job.workload, job.models, job.seed,
                count=count, own_tokenizer=job.serving_record is not None,
            )  # fmt: skip
        io = job.staging / "io"
        io.mkdir()
        job.prompt_set_digest = write_jsonl(io / "prompts.jsonl", job.prompts)
        if count != job.workload.prompts.count and self.load != "ladder":  # SRV-8: extended set
            prefix = job.staging / "logs/prompt-prefix.jsonl"
            job.prompt_prefix_digest = write_jsonl(
                prefix, job.prompts[: job.workload.prompts.count]
            )
            prefix.unlink()
        own = job.prompt_prefix_digest or job.prompt_set_digest
        if self.source_prompt_digest is not None and own != self.source_prompt_digest:
            raise IProofsError(ErrorKind.CONFIG, f"the first {job.workload.prompts.count} "
                               f"prompts have digest {own}, the --prompts-from run "
                               f"{self.source_prompt_digest} (RFC-0015 SRV-8)")  # fmt: skip
        if _recompute(job):  # RFC-0015 RC-1: the claims come from the --prompts-from run
            if self.claims is None or len(self.claims) < len(job.prompts):
                raise IProofsError(
                    ErrorKind.CONFIG, "a ref-recompute job needs --prompts-from a run with claims"
                )
            write_jsonl(io / "claimed.jsonl", self.claims)

    def _level_shape(self, job: Job) -> None:
        lv, wl = self.level, job.workload
        assert lv is not None
        assert wl is not None
        shape = (wl.shape.prompt_tokens, wl.shape.output_tokens)
        if shape != (lv.prompt_tokens, lv.output_tokens):
            raise IProofsError(ErrorKind.CONFIG, f"{wl.id} has shape {shape[0]} + {shape[1]} "
                               f"tokens; {lv.id} requests {lv.prompt_tokens} + "
                               f"{lv.output_tokens}")  # fmt: skip

    def _ladder_prompts(self, job: Job, count: int) -> list[list[int]]:
        """RFC-0018 CO-4: the rung's ladder prompts, after its slots' prompts and KL windows in
        the beacon stream (`iproofs.level.baseline_prompts`). A workload that draws from a seed
        (the fake systems) draws `count` prompts from the job's seed instead."""
        lv, wl = self.level, job.workload
        assert lv is not None
        assert wl is not None
        assert job.models is not None
        self._level_shape(job)
        if wl.prompts.generator != BEACON_WINDOW:
            return materialise_prompts(self.root, wl, job.models, job.seed, count=count,
                                       own_tokenizer=job.serving_record is not None)  # fmt: skip
        if lv.beacon is None:
            raise IProofsError(ErrorKind.CONFIG, f"{wl.id} draws from the {lv.id} beacon; "
                               f"no levels/{lv.id}-beacon.json is stored yet")  # fmt: skip
        from iproofs.level import (  # noqa: PLC0415 (Level 1 only)
            baseline_prompts,
            load_level,
            rung_stream,
            rung_tokenizer_workload,
        )
        from iproofs.workloads import (  # noqa: PLC0415
            local_corpus,
            pinned_corpus,
            tokenizer_file,
            tokenizer_for,
        )

        level = load_level(self.root, lv.id, registry=self.registry)
        rung = level.rung(lv.rung)
        digest = level.prompts.corpus_digest
        texts = local_corpus(self.root, digest) or pinned_corpus(self.root, digest)
        if texts is None:
            raise IProofsError(ErrorKind.CONFIG, f"corpus {digest} is not available locally")
        source = rung_tokenizer_workload(self.root, level, rung)
        tokenizer = tokenizer_for(tokenizer_file(self.root, source, default_cache()))
        stream = rung_stream(texts, tokenizer, level, rung, str(lv.beacon["randomness"]))
        job.seed = generator_seed(wl, lv.beacon)
        prompts = baseline_prompts(stream, level, rung)
        if len(prompts) != count:
            raise IProofsError(ErrorKind.CONFIG, f"{len(prompts)} ladder prompts, a run of "
                               f"{count}")  # fmt: skip
        return prompts

    def _level_prompts(self, job: Job, count: int) -> list[list[int]]:
        """RFC-0018 §Sessions: slot k's N prompts of the rung's stream. The workload's shape is
        the level's request and its prompt count (one session) is the rung's N, or `config`
        before any step. A `beacon-window/1` workload draws with the stored beacon record."""
        lv, wl = self.level, job.workload
        assert lv is not None
        assert wl is not None
        assert job.models is not None
        self._level_shape(job)
        if lv.slot is None:
            raise IProofsError(ErrorKind.CONFIG, "a level session needs --session (RFC-0018)")
        if wl.prompts.count != lv.requests or count != lv.requests:
            raise IProofsError(ErrorKind.CONFIG, f"{wl.id} proves {count} prompts of a set of "
                               f"{wl.prompts.count}; a {lv.id} session of rung {lv.rung} "
                               f"proves {lv.requests}")  # fmt: skip
        seed: int | Mapping[str, object] = job.seed
        if wl.prompts.generator == BEACON_WINDOW:
            if lv.beacon is None:
                raise IProofsError(ErrorKind.CONFIG, f"{wl.id} draws from the {lv.id} beacon; "
                                   f"no levels/{lv.id}-beacon.json is stored yet")  # fmt: skip
            seed = lv.beacon
        job.seed = generator_seed(wl, seed)  # the manifest's prompt_seed
        return materialise_prompts(self.root, wl, job.models, seed, slot=lv.slot)

    def _resolve_inputs(
        self, job: Job, log: JsonlLogger | None = None, *, models: bool = True
    ) -> None:
        """System, workload, reference file and the hash-checked model directory (left out
        with `models=False`, for verify calls only: a verifier never sees the weights)."""
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
        profile = job.reference.profiles[spec.profile]
        count = profile_gpu_count(profile, spec.profile)  # INV-DERIVE-8
        job.system, job.workload = system, wl
        if _serve(job):
            self._serving(job, profile, count)
        elif isinstance(profile, ServingProfile):
            raise IProofsError(ErrorKind.CONFIG, f"profile {spec.profile} runs production "
                               "serving only (RFC-0006 R6)")  # fmt: skip
        elif self.load != "matched":
            raise IProofsError(ErrorKind.CONFIG, "--load is for production serving (SRV-1)")
        elif self.sizing_batches is not None:
            raise IProofsError(ErrorKind.CONFIG, "--sizing-batches is for production serving "
                               "(RFC-0015 SRV-1)")  # fmt: skip
        bound = bound_gpus(self.env)
        if count is not None and bound and len(bound) != count:  # PC-GPU-COUNT, INV-DERIVE-8
            raise IProofsError(ErrorKind.CONFIG, f"{len(bound)} bound GPU(s) {list(bound)}, "
                               f"profile {spec.profile} holds {count}")  # fmt: skip
        if not models:  # a verify call only: a verifier never sees the weights
            job.models = None
        elif job.serving_record is not None:  # the publisher's release, not the workload's
            job.models = self._serving_models(job.serving_record, log)
        else:
            job.models = self._models(wl, log)

    def _serving(self, job: Job, profile: object, count: int | None) -> None:
        """RFC-0015 SRV-1, SRV-6 and RFC-0006 R6 for a production-serving job: a serving
        profile (a GPU prover profile is refused; the CPU-only CI profile runs the fake
        reference), the system.yaml entry of the load point and GPU count, the serving record
        that names the workload, and the placement rule."""
        assert job.system is not None
        assert job.workload is not None
        spec = job.spec
        if not isinstance(profile, ServingProfile) and getattr(profile, "gpu", None) is not None:
            raise IProofsError(ErrorKind.CONFIG, f"production serving runs on a serving profile "
                               f"(RFC-0006 R6), not {spec.profile}")  # fmt: skip
        entries = [w for w in job.system.workloads if isinstance(w, ReferenceWorkload)
                   and w.id == spec.workload and (w.load_point or "matched") == self.load
                   and (count is None or w.gpus in (None, count))]  # fmt: skip
        if not entries:
            raise IProofsError(ErrorKind.CONFIG, f"{spec.system} lists no {self.load} entry for "
                               f"{spec.workload} on {count} GPU(s) (RFC-0015 SRV-6)")  # fmt: skip
        job.serving_entry = entry = entries[0]
        wl = job.workload
        if self.sizing_batches is not None:  # SRV-1: a sizing capture, matched load only
            job.run_shape = (wl.shape.batch_size, self._sizing(job, entry))
        elif self.load == "ladder":  # RFC-0018 CO-4: one batch of every ladder prompt
            if self.level is None:
                raise IProofsError(ErrorKind.CONFIG, "--load ladder serves a level's baseline: "
                                   "give --level (RFC-0018 CO-4)")  # fmt: skip
            job.run_shape = (self.level.ladder_prompts, 1)
            job.ladder = {"ladder": list(self.level.ladder),
                          "warmup_batches": self.level.warmup_batches,
                          "timed_batches": self.level.timed_batches}  # fmt: skip
        elif self.load == "high":
            job.run_shape = (entry.batch_size or wl.shape.batch_size,
                             max(wl.shape.batches_per_session, 2))  # fmt: skip
        else:
            batches = entry.batches_per_session_run or wl.shape.batches_per_session
            job.run_shape = (wl.shape.batch_size, batches)
        job.serving_record = record_for(self.root, self.registry, wl.id)
        if job.serving_record is None and wl.model.source.hub != "repository":
            raise IProofsError(ErrorKind.CONFIG, f"no serving record names {wl.id} "
                               "(workloads/serving/, RFC-0015 SRV-6)")  # fmt: skip

    def _sizing(self, job: Job, entry: ReferenceWorkload) -> int:
        """RFC-0015 SRV-1: a sizing capture serves the declared batch count at the workload's
        batch size, only while the entry's `batches_per_session_run` is null and only at the
        matched load, and at least 2 batches, so that the capture has a steady scope for
        `iproofs serving size-session`. The manifest marks it and run.json warns: it sizes
        the session and joins no overhead (RFC-0004 INV-DERIVE-2)."""
        n = self.sizing_batches
        assert n is not None
        if self.load != "matched":
            raise IProofsError(ErrorKind.CONFIG, "--sizing-batches sizes the matched load only "
                               "(RFC-0015 SRV-1)")  # fmt: skip
        if entry.batches_per_session_run is not None:
            raise IProofsError(ErrorKind.CONFIG, f"{entry.id} matched already has "
                               f"batches_per_session_run {entry.batches_per_session_run}; a "
                               "sizing capture is for a null count (RFC-0015 SRV-1)")  # fmt: skip
        if n < SIZING_MIN_BATCHES:
            raise IProofsError(ErrorKind.CONFIG, f"--sizing-batches {n}: a sizing capture needs "
                               f"at least {SIZING_MIN_BATCHES} batches, so that it has a steady "
                               "scope (RFC-0015 SRV-1)")  # fmt: skip
        job.sizing = True
        if SIZING_WARNING not in job.warnings:
            job.warnings.append(SIZING_WARNING)
        return n

    def _serving_models(self, record: ServingModel, log: JsonlLogger | None) -> Path:
        """The serving record's files, fetched and checked (RFC-0014 SM-2), rehashed per job."""
        start = self.clock()
        path = ensure_serving_model(
            record,
            default_cache(),
            download=hub_download,
            retry=lambda op: retry_fetch(op, f"serving model {record.id}", log=log),
            token=os.environ.get("HF_TOKEN"),  # publisher files only (Q7)
        )
        if log is not None:
            log.log(Event.INTEGRITY_MODEL_REHASH, what=record.id,
                    seconds=span_seconds(start, self.clock()))  # fmt: skip
        return path

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
        """RFC-0006 §Profile conformance check, once per invocation: every failure is recorded
        (manifest `harness.nonconforming`, run.json warnings) and none refuses the run."""
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
        if saved is not None and not saved.get("passed"):
            failures.append(ConformanceFailure("ST", "the host's last self-test failed"))
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
            gpu_indices=bound_gpus(self.env),
        )

    def _machine_drift(self, job: Job, log: JsonlLogger) -> None:
        """INV-MR-2: collected again after the last step; drift is an environment failure."""
        if job.failure is not None or not job.machine:
            return
        after = self._record(job)
        changed = machine_drift(job.machine, after)
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

    def _unbound(self, job: Job) -> list[int]:
        """The visible GPUs no step of the job binds (RFC-0006 PC-GPU-IDLE), by the machine
        record's visible count."""
        gpu = job.machine.get("gpu") if isinstance(job.machine, dict) else None
        visible = gpu.get("count_visible") if isinstance(gpu, dict) else None
        if not isinstance(visible, int):
            return []
        bound = set(bound_gpus(self.env))
        return [i for i in range(visible) if i not in bound]

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
        control: bool | Mapping[str, object] = False,
        ro_mounts: Sequence[tuple[Path, str]] = (),
        trace_dir: Path | None = None,
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
                "control": control if isinstance(control, bool) else dict(control),
                **extra,
            },
        )
        role: Literal["prover", "verifier", "verifier_1"] = (
            "prover" if sub not in NO_GPU_CALLS
            else ("verifier_1" if extra.get("_single") else "verifier")
        )  # fmt: skip
        job_json = json.loads((io / "job.json").read_text())
        job_json.pop("_single", None)
        write_json(io / "job.json", job_json)
        cpuset, mems = self.env.cpus(role)
        started_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        bound = bound_gpus(self.env) if sub not in NO_GPU_CALLS else ()
        sampler = Sampler(bound or None, self.readers)  # every bound GPU (RFC-0011)
        idle = IdleWatch(self._unbound(job), self.env.host().gpu_usage)  # PC-GPU-IDLE
        cpu0, oom0 = self.readers.cpu_usage_usec(), self.readers.oom_kills()
        sampler.start()
        idle.start()
        try:
            result = self._run_container(job, sub, io, cpuset, mems, ro_mounts, trace_dir)
        except BaseException:
            sampler.stop(0, 0)  # the call failed before it ended; nothing is recorded
            idle.stop()
            raise
        summary = sampler.stop(result.started_mono_ns, result.ended_mono_ns)
        for line in idle_use(idle.stop(), job.machine):  # PC-GPU-IDLE: recorded, never refused
            if line not in job.warnings:
                job.warnings.append(line)
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
        gpu = self._gpu_arg(sub)
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
        return self._after_call(job, sub, io, result, bool(control))

    def _run_container(
        self,
        job: Job,
        sub: str,
        io: Path,
        cpuset: str,
        mems: str,
        ro_mounts: Sequence[tuple[Path, str]],
        trace_dir: Path | None = None,
    ) -> StepResult:
        assert job.system is not None
        sinks = [job.logs.setdefault(f"{job.log_prefix}{sub}.{s}", Capture())
                 for s in ("stdout", "stderr")]  # fmt: skip
        models = job.models if sub not in NO_GPU_CALLS else None
        timeout = job.system.timeout(sub)
        if trace_dir is None:  # the call of every run before RFC-0018
            return self.containers.run(job.image, sub, io, models_dir=models,
                                       gpu=self._gpu_arg(sub), cpuset=cpuset, mems=mems,
                                       memory=None, timeout_s=timeout, ro_mounts=ro_mounts,
                                       log_sinks=sinks)  # fmt: skip
        return self.containers.run(job.image, sub, io, models_dir=models, gpu=self._gpu_arg(sub),
                                   cpuset=cpuset, mems=mems, memory=None, timeout_s=timeout,
                                   ro_mounts=ro_mounts, log_sinks=sinks,
                                   trace_dir=trace_dir)  # fmt: skip

    def _gpu_arg(self, sub: str) -> int | str | None:
        """The container runner's GPU: the one bound index, or a serving job's list
        (`CUDA_VISIBLE_DEVICES=0,1,2,3`, RFC-0006 R6); none for `verify` and `mutate_reply`."""
        bound = bound_gpus(self.env) if sub not in NO_GPU_CALLS else ()
        if not bound:
            return None
        return bound[0] if len(bound) == 1 else ",".join(map(str, bound))

    def _after_call(
        self, job: Job, sub: str, io: Path, result: StepResult, control: bool
    ) -> tuple[AdapterOut, StepResult]:
        if sub not in UNTIMED and not control:  # never moves the run's timing
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
            declared = _declared_failure(io, job) if result.exit_code != 0 else None
            if declared is not None:  # RFC-0005 amendment of 2026-11-09, reference adapters
                kind, message, evidence = declared
                raise IProofsError(kind, f"{sub}: {message}", step=sub,
                                   exit_code=result.exit_code,
                                   last_lines=(*result.stderr_tail, *evidence))  # fmt: skip
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
        job.optional_subcommands = tuple(out.optional_subcommands or ())
        pinned = job.system.upstream.commit if job.system.upstream else None
        if pinned is not None and out.upstream_commit != pinned:
            raise IProofsError(
                ErrorKind.INTEGRITY,
                f"info reports upstream {out.upstream_commit}, system.yaml pins {pinned}",
            )

    def _setup(self, job: Job, control: Mapping[str, object] | None = None) -> None:
        self._call(job, "setup", {}, control=control or False)

    def _commit(self, job: Job, control: Mapping[str, object] | None = None) -> None:
        """RFC-0014 §The commitment record: copy the commit step's files into a store no
        later container mounts read-write, and record their digests."""
        job.commit, _ = self._call(
            job, "commit", {"model_dir": "/models"}, control=control or False
        )
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
        state = job.staging / "io/state"
        names = sorted(p.name for p in state.iterdir()) if state.is_dir() else []
        (job.staging / "io" / STATE_AFTER_COMMIT).write_text(json.dumps(names) + "\n")

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

    def _prove(self, job: Job, log: JsonlLogger | None = None) -> None:  # noqa: PLR0912, PLR0915
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
        marks = ReleaseWatcher(job.staging / "io/marks", clock=self.clock, names=MARKS)
        marks.start()
        fields: dict[str, object] = {"claims_file": "/io/claimed.jsonl"} if _recompute(job) else {}
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
                    "batch_size": _run_shape(job)[0],
                    "batches": _run_shape(job)[1],
                }
                | _serving_fields(job),
                ro_mounts=ro,
            )
        except IProofsError as failure:
            # a failed step under another configuration is that configuration's failure
            problem = engine_command_problem(job.staging / "io", _engine_args(job), required=False)
            if reference and problem is not None:
                raise IProofsError(ErrorKind.CONFIG, problem, step="prove") from failure
            raise
        finally:
            end = job.steps["prove"].ended_mono_ns if "prove" in job.steps else None
            job.marks = [(m.proof_id, m.mono_ns) for m in marks.stop(call_end_ns=end)]
            releases = watcher.stop(call_end_ns=end)
        problem = engine_command_problem(job.staging / "io", _engine_args(job), required=True)
        if reference and problem is not None:
            raise IProofsError(ErrorKind.CONFIG, problem, step="prove")
        job.engine_interface = engine_interface(job.staging / "io")
        job.engine_observed = engine_observed(job.staging / "io")
        if job.serving_record is not None and watcher.mechanism != "inotify":  # SRV-1, W-1
            message = "a production-serving run needs the inotify release watcher; it polled"
            raise IProofsError(ErrorKind.ENVIRONMENT, message, step="prove")
        job.warnings += check_proofs(IoDirs(job.staging / "io"), out, job.system)
        job.warnings += [f"prove: {w}" for w in out.warnings]  # the adapter's, e.g. a ladder's
        # RFC-0017 INV-REQ-2; under a level, every request claims the level's reply (AD-1). A
        # serving ladder serves each ladder prompt once per concurrency (CO-4), so there each
        # served reply, not each prompt, holds the level's reply length.
        tokens = self.level.output_tokens if self.level else job.workload.shape.output_tokens
        if self.load == "ladder":
            short = sorted(
                {p.proof_id for p in out.proofs or () if len(p.claimed_output) != tokens}
            )
            if short:
                raise IProofsError(ErrorKind.ADAPTER, f"ladder replies of another length than "
                                   f"{tokens}: {short[:5]}", step="prove")  # fmt: skip
        else:
            check_requests(out, tokens)
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
        if job.level is not None:
            self._weights_away(job)
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

    def _mode(self) -> str:
        if isinstance(self.containers, DockerRunner):
            return DockerRunner.MODE
        return "hosted" if self.hosted else "in-process"

    def _weights_away(self, job: Job) -> None:
        """RFC-0018 CH-4 (b), after the last prove and before the first verify: the model
        paths a trace is matched against, taken while the files exist; then, in a hosted
        container, the workload's weights removed from the cache. Docker never mounts them
        into a verify container; repository test data (the fake systems) is never removed."""
        assert job.workload is not None
        job.model_paths = model_paths(job.workload, job.models)
        cached = job.workload.model.source.hub != "repository" and job.serving_record is None
        if self._mode() != "hosted" or job.models is None or not cached:
            return
        for p in [job.models, *job.models.rglob("*")]:  # the cache entry is read-only
            if p.is_dir() and not p.is_symlink():
                p.chmod(0o700)
        shutil.rmtree(job.models)
        job.models_removed = True

    def _verify_trace(self, job: Job, proof_id: str, trace_dir: Path, result: StepResult) -> None:
        """RFC-0018 CH-4: `verify-trace/<proof_id>.json`, the reduction of the verify call's
        file-open trace, whether a GPU was visible to it and whether the workload's model
        files were on its filesystem. No trace file means no trace tool ran: `tool` null."""
        assert job.model_paths is not None
        paths, mode = job.model_paths, self._mode()
        docker = mode == DockerRunner.MODE
        raw = trace_dir / TRACE_FILE
        text = raw.read_text("utf-8", errors="replace") if raw.is_file() else None
        realpath: Callable[[str], str] = (lambda p: p) if docker else os.path.realpath
        reduced = reduce_strace(text or "", paths.files, paths.dirs, realpath)

        def size(path: str) -> int | None:
            if docker or not os.path.isabs(path):  # a container path, or relative to its cwd
                return None
            try:
                return os.stat(path).st_size if os.path.isfile(path) else None
            except OSError:
                return None

        if docker:  # INV: a verify container is given neither a GPU nor /models
            given_gpu = "--gpus" in result.argv
            present = any(a.endswith((":/models:ro", ":/models")) for a in result.argv)
        else:
            given_gpu = self._gpu_arg("verify") is not None
            present = any(p.exists() for p in paths.host_files)
        doc: dict[str, object] = {
            "schema": "verify-trace/1",
            "run_id": job.run_id,
            "proof_id": proof_id,
            "mode": mode,
            "tool": "strace" if text is not None else None,
            "trace": None
            if text is None
            else {"digest": file_digest(raw), "bytes": raw.stat().st_size},
            "opened": [{"path": p, "bytes": size(p)} for p in reduced.opened],
            "failed_opens": reduced.failed,
            "model_files_opened": [{"path": c.path, "ok": c.ok} for c in reduced.model_files],
            "gpu_devices_opened": list(reduced.gpu_devices),
            "gpu_visible": given_gpu or bool(reduced.gpu_devices),
            "model_files_present": present,
            "model_files_removed": job.models_removed,
        }
        errors = self.registry.errors("verify-trace/1", doc)
        if errors:
            raise IProofsError(ErrorKind.INTERNAL, f"verify-trace fails its schema: {errors[0]}")
        (job.staging / VERIFY_TRACE).mkdir(exist_ok=True)
        write_json(job.staging / VERIFY_TRACE / f"{proof_id}.json", doc)

    def logprobs(self, job: Job, texts: Sequence[Sequence[int]], vocab: int) -> list[Path] | None:
        """RFC-0018 AD-2, FI-7: the system's own next-token distributions over each KL text, from
        the optional `logprobs` subcommand with the run's commitment and prover files. Each
        returned file holds, for the scored positions only (the second half of the text), one
        row of `vocab` float16 log-probabilities per position, row r predicting token
        len(text)/2 + r + 1. The files are large, so the paths are returned, each size checked.
        None, the defined unsupported outcome, when `info` does not list it; nothing is called."""
        if "logprobs" not in job.optional_subcommands:
            return None
        assert job.commit is not None
        io = job.staging / "logprobs-io"
        io.mkdir(parents=True)
        write_jsonl(io / "texts.jsonl", [list(t) for t in texts])
        recorded = self._recorded(job, "prover_files", job.staging / "prover-ro", "logprobs")
        ro = list(zip(recorded, job.commit.prover_files or (), strict=True))
        out, _ = self._call(job, "logprobs", {
            "commitment_id": job.commit.commitment_id,
            "prover_files": list(job.commit.prover_files or ()),
            "model_dir": "/models",
            "texts_file": "/io/texts.jsonl",
        }, io=io, ro_mounts=ro)  # fmt: skip
        files = out.logprobs_files or ()
        if len(files) != len(texts):
            raise IProofsError(ErrorKind.ADAPTER, f"logprobs: {len(files)} files for "
                               f"{len(texts)} texts", step="logprobs")  # fmt: skip
        paths = []
        for text, name in zip(texts, files, strict=True):
            path = IoDirs(io).host(name, "logprobs")
            rows = max(len(text) - len(text) // 2 - 1, 0)
            if path.stat().st_size != 2 * rows * vocab:
                raise IProofsError(ErrorKind.ADAPTER, f"logprobs: {name} has "
                                   f"{path.stat().st_size} bytes, not 2 x {rows} x {vocab}",
                                   step="logprobs")  # fmt: skip
            paths.append(path)
        return paths

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
        traced = job.level is not None and not single
        trace_dir = job.staging / "verify" / f"{proof_id}-trace" if traced else None
        if trace_dir is not None:
            trace_dir.mkdir(parents=True)
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
            trace_dir=trace_dir,
        )
        if trace_dir is not None:
            self._verify_trace(job, proof_id, trace_dir, result)
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
        self,
        job: Job,
        verify: Callable[[VerifyCall], VerifyResult],
        work: Path,
        only: Collection[str] | None = None,
        log: JsonlLogger | None = None,
    ) -> list[dict[str, object]]:
        """`systems/<name>/controls.yaml` (RFC-0008 §System-specific controls). A weakened prove
        runs in its own io dir with `control: true` and its flags passed explicitly; every verify
        uses the run's recorded commitment (INV-CTRL-6); the run's honest proof is the twin."""
        controls = [c for c in system_controls(self.root, self.registry, job.spec.system)
                    if only is None or c.id in only]  # fmt: skip
        if not controls:
            return []
        assert job.commit is not None
        assert job.workload is not None
        twin = self._honest_twin(job)

        def weakened(control: SystemControl) -> tuple[list[VerifyCall], object]:
            flags = control.control_flags or ()
            return self._control_prove(job, control.id, work, flags=flags, log=log)

        return [
            system_control_record(c, lambda c=c: weakened(c), lambda: [twin], verify)  # type: ignore[misc]
            for c in controls
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

    def _control_prove(  # noqa: PLR0913 (keyword-only options of one control prove)
        self,
        job: Job,
        control_id: str,
        work: Path,
        *,
        flags: Sequence[str] = (),
        models: Path | None = None,
        batches: int | None = None,
        log: JsonlLogger | None = None,
        trial: int = 0,
        control: Mapping[str, object] | None = None,
    ) -> tuple[list[VerifyCall], object]:
        """A `prove` with `control: true` in its own io dir: the run's commitment and prover
        files, optionally other weights (P1) or explicit flags (weakened provers). Returns the
        verify calls of its proofs, each against the run's commitment (INV-CTRL-6), and the
        binding report."""
        assert job.commit is not None
        assert job.workload is not None
        commitment = str(job.commit.commitment_id)
        shape = job.workload.shape
        io = work / (f"prove-{control_id}" + (f"-{trial}" if trial else ""))
        io.mkdir(parents=True)
        shutil.copyfile(job.staging / "io/prompts.jsonl", io / "prompts.jsonl")
        copy_state_after_commit(job.staging / "io", io)
        if models is None and job.models_removed:  # hosted level run: fetched again (CH-4)
            job.models = self._models(job.workload, log)
            job.models_removed = False
        honest_models = job.models
        job.models = models or honest_models
        try:
            out, result = self._call(
                job,
                "prove",
                {
                    "commitment_id": commitment,
                    "prover_files": list(job.commit.prover_files or ()),
                    "model_dir": "/models",
                    "prompts_file": "/io/prompts.jsonl",
                    "batch_size": _run_shape(job)[0],
                    "batches": batches or shape.batches_per_session,
                    "control_flags": list(flags),
                },
                io=io,
                control=control or True,
            )
        finally:
            job.models = honest_models
        self._log_call(log, job, control_id, None, "prove", result)
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
        none (RFC-0008 C3 and P1 are then `not_applicable` with that reason). The note records
        the reason only; the command that makes one goes to the progress stream."""
        assert job.workload is not None
        spec = job.spec
        path = perturbed_dir(Path(spec.results_root), spec.release, spec.system, spec.workload)
        if not (path / "perturbed.json").is_file():
            if self.progress is not None:
                print(f"controls: no perturbed commitment for {spec.workload}, so C3 and P1 do "
                      f"not apply; iproofs controls --prepare-perturbed {spec.workload} makes "
                      "one", file=self.progress)  # fmt: skip
            return "no perturbed commitment for this workload"
        record = load(path / "perturbed.json", self.registry)
        assert isinstance(record, PerturbedCommitmentRecord)
        made_for = (record.source_model_digest, record.workload["version"])
        if made_for != (job.workload.model.digest, job.workload.version):
            return "the perturbed commitment was made from other weights or workload version"
        if job.level is not None and "digest_w_prime" not in record.perturbation:
            return ("the perturbed commitment was not made by the adapter's perturb with the "
                    "level's model change (RFC-0018 CH-2, AD-5)")  # fmt: skip
        return record

    def _mutator(self, job: Job, work: Path, log: JsonlLogger | None) -> Mutator:
        """RFC-0018 AD-6: the adapter's `mutate_reply` on a copy of an honest proof, in its own
        io dir, with neither the weights nor a GPU. The adapter decides nothing here; the
        mutated proof goes to verify like any control's."""
        calls = 0

        def mutate(
            target: HonestProof, proof: Path, position: int, token: int, k: int
        ) -> tuple[Path, Mapping[str, object]]:
            nonlocal calls
            calls += 1
            self._check_proof(job, target.proof_id, "controls")
            io = work / f"mutate-{calls}"
            shutil.copytree(proof, io / "proof")
            fields = {"proof_dir": "/io/proof", "position": position, "token": token,
                      "out_dir": "/io/mutated"}  # fmt: skip
            out, result = self._call(job, "mutate_reply", fields, io=io, control=True)
            self._log_call(log, job, "C1", k, "mutate_reply", result)
            shutil.rmtree(io / "proof")
            mutated = io / "mutated"
            files = sorted(mutated.iterdir()) if mutated.is_dir() else []
            if (
                out.mutated is None
                or not files
                or any(p.is_symlink() or not p.is_file() for p in files)
            ):
                raise IProofsError(ErrorKind.ADAPTER, "mutate_reply: /io/mutated holds no proof "
                                   "of regular files", step="controls")  # fmt: skip
            return mutated, dict(out.mutated)

        return mutate

    def _perturb(self, job: Job, change: str, weights: Path) -> dict[str, object]:
        """RFC-0018 AD-5: the adapter's `perturb` writes W' to /io/perturbed, from the model
        directory and the level's change; W' moves to `weights` (the cache entry P1 reads)
        and the adapter's record of the change is returned."""
        if "perturb" not in job.optional_subcommands:
            raise IProofsError(ErrorKind.CONFIG, f"{job.spec.system} lists no perturb "
                               "subcommand: MODEL has no W' (RFC-0018 AD-5)")  # fmt: skip
        io = job.staging / "perturb-io"
        io.mkdir()
        fields: dict[str, object] = {"change": change, "model_dir": "/models",
                                     "out_dir": "/io/perturbed"}  # fmt: skip
        out, _ = self._call(job, "perturb", fields, io=io, control=True)
        made = io / "perturbed"
        if out.perturbation is None or not made.is_dir() or not any(made.iterdir()):
            raise IProofsError(ErrorKind.ADAPTER, "perturb wrote no model to /io/perturbed",
                               step="perturb")  # fmt: skip
        weights.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(made, weights)
        return dict(out.perturbation)

    def _no_perturb(self, job: Job) -> str | None:
        """RFC-0018 AD-5: under a level, MODEL needs W' from the adapter's own `perturb`."""
        if job.level is not None and "perturb" not in job.optional_subcommands:
            return "the adapter lists no perturb subcommand, so MODEL has no W' (RFC-0018 AD-5)"
        return None

    def _prover_controls(
        self,
        job: Job,
        perturbed: PerturbedCommitmentRecord | str,
        verify: Callable[[VerifyCall], VerifyResult],
        work: Path,
        only: Collection[str] | None = None,
        log: JsonlLogger | None = None,
    ) -> list[dict[str, object]]:
        """P1 and P2 (RFC-0008 §Shared controls, prover side), one batch each."""
        wanted = [cid for cid in SHARED_PROVER_CONTROLS if only is None or cid in only]
        if not wanted:
            return []
        twin = self._honest_twin(job)

        def p1(k: int = 0) -> list[VerifyCall]:
            if isinstance(perturbed, str):
                raise NotApplicable(perturbed)
            weights = perturbed_weights(perturbed)
            if weights is None:
                raise NotApplicable("the perturbed weights are not on this host")
            control = None
            if job.level is not None:  # RFC-0018: the job says which control and which W'
                control = {"id": "P1", "perturbation": dict(perturbed.perturbation)}
            return self._control_prove(job, "P1", work, models=weights, batches=1, log=log,
                                       trial=k, control=control)[0]  # fmt: skip

        def p2() -> list[VerifyCall]:
            raise NotApplicable("the workload declares one precision")

        builds = {"P1": p1, "P2": p2}
        return [
            level_control_record(
                "P1", [Series({}, p1)], lambda: [twin], verify, side="prover", trials=LEVEL_TRIALS
            )
            if cid == "P1" and job.level is not None
            else prover_side_record(
                cid, EXPECTED[cid], "shared", builds[cid], lambda: [twin], verify
            )
            for cid in wanted
        ]

    @staticmethod
    def _log_call(
        log: JsonlLogger | None,
        job: Job,
        control: str,
        trial: int | None,
        sub: str,
        result: StepResult,
    ) -> None:
        """`control.call` after each control call that returned, so a long suite shows its
        progress and a part stopped at its deadline leaves each finished call's span."""
        if log is not None:
            log.log(Event.CONTROL_CALL, job=job.run_id, step="controls", control=control,
                    trial=trial, subcommand=sub, exit_code=result.exit_code,
                    seconds=span_seconds(result.started_mono_ns, result.ended_mono_ns))  # fmt: skip

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

    def _controls(
        self,
        job: Job,
        log: JsonlLogger,
        *,
        seed: str | None = None,
        only: Sequence[str] | None = None,
        part: Mapping[str, object] | None = None,
    ) -> Path:
        """The control suite against the honest proofs (RFC-0008 §Where controls run), with a
        fresh seed unless one is given. Writes `controls.json`, or with `only` (a subset in
        suite order) a `controls-part/1` file for `--merge` (RFC-0008 §Split suites), whose
        `part` gives the seed record's digest and the host record; returns the path
        written."""
        assert job.commit is not None
        assert job.workload is not None
        seed = seed or new_control_seed()
        work = job.staging / "controls-io"
        trials = 0

        perturbed = self._no_perturb(job) or self._perturbed(job)
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
            try:
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
            finally:  # one copy at a time: the stored H100 SASH run's proof is 44.6 GB
                shutil.rmtree(io / "proof", ignore_errors=True)
            self._log_call(log, job, call.control_id, call.trial, "verify", result)
            return VerifyResult(
                str(out.verdict),
                int(out.raw_exit_code or 0),
                str(out.raw_last_line or ""),
                span_seconds(result.started_mono_ns, result.ended_mono_ns),
            )

        proofs = self.honest_proofs(job)
        dirs = {p.proof_id: job.staging / "io/proofs" / p.proof_id for p in proofs}
        reads = parts_read(job.system)  # refused before any call when it does not fit
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
            only=only,
            reads=reads,
            level=job.level is not None,
            no_perturbed=perturbed if isinstance(perturbed, str) else "",
            mutate=self._mutator(job, work, log)
            if job.level is not None and "mutate_reply" in job.optional_subcommands
            else None,
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
        records += self._prover_controls(job, perturbed, verify, work, only, log)
        records += self._system_controls(job, verify, work, only, log)
        made = None if isinstance(perturbed, str) else {
            "commitment_id": str(perturbed.commitment["commitment_id"]),
            "model_digest": perturbed.model_digest,
        }  # fmt: skip
        if disclosure_pending(records):
            log.log(
                Event.CONTROL_DISCLOSURE_PENDING,
                job=job.run_id,
                step="controls",
                control=[r["id"] for r in records if r["outcome"] == "accepted"],
            )
        doc, schema, path = self._controls_doc(job, seed, made, records, only, part)
        errors = self.registry.errors(schema, doc)
        if errors:
            raise IProofsError(
                ErrorKind.INTERNAL, f"{path.name} fails {schema}: " + "; ".join(errors)
            )
        write_json(path, doc)
        self.controls_done = True
        return path

    def _controls_doc(
        self,
        job: Job,
        seed: str,
        made: Mapping[str, str] | None,
        records: Sequence[Mapping[str, object]],
        only: Sequence[str] | None,
        part: Mapping[str, object] | None,
    ) -> tuple[dict[str, object], str, Path]:
        """(document, schema, path): controls.json, or with `only` a `controls-part/1` part."""
        if only is None:
            doc = controls_document(
                job.run_id, seed, job.image, self._verifier_profile(job), made, records
            )
            return doc, "controls/1", job.staging / "controls.json"
        assert part is not None
        same = self._part_header(job, seed, str(part["seed_record_digest"]), made)
        doc = part_document(same, part["host"], only, records)  # type: ignore[arg-type]
        return doc, "controls-part/1", job.staging / part_name(seed, only)

    def _part_header(
        self, job: Job, seed: str, seed_record_digest: str, made: Mapping[str, str] | None
    ) -> dict[str, object]:
        """What every part of one split suite shares (RFC-0008 §Split suites): the run, read
        from its manifest's bytes; the seed and its record; the image; the verifier and run
        profiles and the CPUs this host binds the verifier to; the perturbed commitment; the
        harness. The dirty flag covers what decides a control's inputs and outcome: the
        harness, the system's directory (its controls.yaml and adapter), the schemas and the
        reference files."""
        paths = ["harness", "pyproject.toml", "uv.lock", f"systems/{job.spec.system}", "schema",
                 "reference"]  # fmt: skip
        commit, dirty = git_state(self.root, paths)
        suite = [cid for cid, _ in control_suite(self.root, self.registry, job.spec.system)]
        if job.level is not None:  # RFC-0018 CH-1: a session's suite is its checks' controls
            suite = [cid for cid in suite if cid in (*LEVEL_VERIFIER_CONTROLS, "P1")]
        return {
            "run_id": job.run_id,
            "run_manifest_digest": file_digest(job.staging / "manifest.json"),
            "control_seed": seed,
            "seed_record_digest": seed_record_digest,
            "suite": suite,
            "image": job.image,
            "verifier_profile": self._verifier_profile(job),
            "profile": job.spec.profile,
            "verifier_cpus": len(_cpu_list(self.env.cpus("verifier")[0])),
            "perturbed_commitment": dict(made) if made else None,
            "harness_version": __version__,
            "harness_commit": commit,
            "harness_dirty": dirty,
        }

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
        # a job that failed before its prompts existed was never resolved: no manifest
        resolved = job.workload and job.system and job.prompt_set_digest
        manifest = self._manifest(job) if resolved else None
        # run.json names the card the manifest records (RFC-0016 OVR-5 reads it)
        claim = manifest.get("claim") if manifest is not None else None
        doc = self._run_doc(job, metrics, claim)
        if self.load == "ladder":  # the replies go beside run.json (iproofs.replies, SIZE-1)
            doc = split_replies(job.staging, doc)
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
            manifest = None if "manifest.json" in bad else manifest
            doc = self._run_doc(job, {}, claim if manifest is not None else None)
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
            ("prover-ro", "verify", "controls-io", "logprobs-io")
            if self.keep_io
            else (*SCRATCH, "io", "verify", "controls-io", "logprobs-io")
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

    def _run_doc(
        self, job: Job, metrics: dict[str, QuantityTree], claim: object = None
    ) -> dict[str, object]:
        spec = job.spec
        tokens = self._tokens(job) if metrics else [(0, 0)] * len(job.releases)
        return (
            {
                "schema": "run/1",
                "run_id": job.run_id,
                "release": spec.release,
                "system": spec.system,
                "workload": {"id": spec.workload, "version": spec.workload_version},
                "profile": spec.profile,
                "repetition": spec.repetition,
                "control": self.control_run,
                "system_kind": job.system.kind if job.system else "test",
                "claim": claim,
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
            }
            | ({"inputs": self._run_inputs(job)} if metrics and job.workload else {})
            | ({"marks": [{"name": n, "mono_ns": ns} for n, ns in job.marks]} if job.marks else {})
        )

    def _run_inputs(self, job: Job) -> dict[str, QuantityTree]:
        """run.json `inputs`: the workload's asserted inputs (RFC-0003 WB-4) and, for a profile
        with a GPU, its GPU count (RFC-0004 INV-DERIVE-8)."""
        assert job.workload is not None
        out = asserted_inputs(job.workload)
        if (count := self._gpu_count(job)) is not None:
            out["gpu_count"] = count
        return out

    def _gpu_count(self, job: Job) -> QuantityTree | None:
        """The profile's `gpu.count` as an asserted quantity (RFC-0004 INV-DERIVE-8), or None
        for a CPU-only test profile (`gpu: null`)."""
        assert job.reference is not None
        count = profile_gpu_count(job.reference.profiles[job.spec.profile], job.spec.profile)
        if count is None:
            return None
        ref = f"{job.reference_file}#/profiles/{job.spec.profile}/gpu/count"
        return {"value": count, "unit": str(Unit.COUNT), "scope": None,
                "grade": str(Grade.ASSERTED), "tier": str(Tier.REPORTED),
                "source": {"kind": str(SourceKind.REFERENCE_FILE), "ref": ref},
                "null_reason": None}  # fmt: skip

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
        return (
            {
                "schema": "manifest/1",
                "run_id": job.run_id,
                "release": spec.release,
                "control": self.control_run,
                "harness": {
                    "version": __version__,
                    "git_commit": harness_commit,
                    "git_dirty": harness_dirty,
                    "lock_digest": file_digest(self.root / "uv.lock"),
                    "nonconforming": bool(self.nonconforming),
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
                }
                | (
                    {"optional_subcommands": list(job.optional_subcommands)}
                    if job.optional_subcommands
                    else {}
                ),
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
                    "steady_rule": STEADY_RULE,  # RFC-0004 INV-SCOPE-5
                }
                | self._serving_workload(job),
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
            | self._serving_manifest(job)
            | self._level_manifest(job)
        )

    def _level_manifest(self, job: Job) -> dict[str, object]:
        """RFC-0018: a level session's level file by digest and its slot, rung and request
        count, with the beacon round its prompts were drawn from (null for a workload that
        draws from a seed)."""
        lv = self.level
        if lv is None or job.level is None:
            return {}
        beacon = None
        if lv.beacon is not None and job.workload is not None \
                and job.workload.prompts.generator == BEACON_WINDOW:  # fmt: skip
            beacon = {"round": lv.beacon["round"], "seed": f"0x{job.seed:016x}"}
        requests = lv.requests if lv.slot is not None else len(job.prompts)
        return {"level": dict(job.level),
                "session": {"slot": lv.slot, "rung": lv.rung, "requests": requests,
                            "beacon": beacon}}  # fmt: skip

    def _serving_workload(self, job: Job) -> dict[str, object]:
        """RFC-0010 manifest `workload` fields of a production-serving run (SRV-1, SRV-8)."""
        if job.serving_entry is None:
            return {}
        batch, batches = _run_shape(job)
        out: dict[str, object] = {"load_point": job.serving_entry.load_point or "matched",
                                  "batch_size_run": batch, "batches_per_session_run": batches,
                                  "prompt_count_run": batch * batches}  # fmt: skip
        if job.prompt_prefix_digest is not None:
            out["prompt_prefix_digest"] = job.prompt_prefix_digest
        if job.sizing:
            out["sizing_capture"] = True
        return out

    def _serving_manifest(self, job: Job) -> dict[str, object]:
        """RFC-0015 SRV-6: the engine as the run's system.yaml pins it and the serving record;
        `serving_model.digest` and `engine.image` are the overhead's join keys."""
        if job.serving_entry is None or job.system is None or job.system.engine is None:
            return {}
        engine = job.system.engine
        interface = job.engine_interface or "vllm serve"
        pinned = {"name": engine.name, "version": engine.version, "image": engine.image}
        seen = {"observed": job.engine_observed} if job.engine_observed is not None else {}
        out: dict[str, object] = {"engine": {**pinned, "interface": interface, **seen}}
        if job.serving_record is not None:
            out["serving_model"] = serving_manifest(job.serving_record)
        return out

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
        listed = (job.proofs.proofs or ()) if job.proofs is not None else ()
        entries = {p.proof_id: p for p in listed}
        indices = [e.request_index if (e := entries.get(pid)) else None for pid, _ in job.releases]
        batch = _batch_size(job)  # INV-SCOPE-5: the steady scope starts after the first batch
        times = [ns for _, ns in job.releases]
        m = scope_seconds(
            job.events.first(),
            times,
            observable=job.observable,
            run_json=run_json,
            batch_size=batch,
            request_indices=indices,
        )
        per_proof = self._tokens(job)
        m |= tokens_metrics(
            per_proof, run_json, batch_size=batch, request_indices=indices, releases=times
        )
        early = released_before_start(times, batch, indices)

        def count(v: int) -> QuantityTree:
            return measured(v, Unit.COUNT, None, f"{run_json}#/proofs", None)

        m["requests_count"] = count(_run_shape(job)[0] * _run_shape(job)[1])
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
        gpu_q = self._gpu_count(job)  # RFC-0004 INV-DERIVE-8, the input of D-GSPT-S
        gpus = int(str(gpu_q["value"])) if gpu_q is not None else 0
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
            gpu_count=None if gpu_q is None else (f"{run_json}#/inputs/gpu_count", gpu_q),
        )
        _steady_warnings(job, m, early)
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
        "median": statistics.median(values),  # RFC-0017 ST-1
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


def system_controls(root: Path, registry: SchemaRegistry, system: str) -> list[SystemControl]:
    """`systems/<name>/controls.yaml`, in file order; none when the file is absent."""
    path = root / "systems" / system / "controls.yaml"
    if not path.is_file():
        return []
    doc = load(path, registry)
    assert isinstance(doc, SystemControls)
    return list(doc.controls)


def control_suite(root: Path, registry: SchemaRegistry, system: str) -> list[tuple[str, str]]:
    """(id, side) of every control of a system's suite, in the order a run writes them to
    controls.json: C1 to C8, P1, P2, then controls.yaml in file order (RFC-0008)."""
    return [
        *((cid, "verifier") for cid in SHARED_VERIFIER_CONTROLS),
        *((cid, "prover") for cid in SHARED_PROVER_CONTROLS),
        *((c.id, "prover" if c.kind == "weakened_prover" else "verifier")
          for c in system_controls(root, registry, system)),
    ]  # fmt: skip


def perturbed_weights(record: PerturbedCommitmentRecord) -> Path | None:
    """The perturbed weights of a stored perturbed commitment in this host's cache, or None
    when they are absent or have another digest (RFC-0008 P1)."""
    weights = default_cache() / "perturbed" / record.source_model_digest.removeprefix("sha256:")
    if not weights.is_dir() or model_digest(weights) != record.model_digest:
        return None
    return weights


def _completed_run(run_dir: Path) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads((run_dir / "run.json").read_text())
    if doc["status"] != "completed":
        raise IProofsError(
            ErrorKind.CONFIG, f"{run_dir} did not complete; controls need accepted proofs"
        )
    return doc


def draw_seed(
    registry: SchemaRegistry,
    run_dir: Path,
    *,
    control_seed: str | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> Path:
    """`iproofs controls RUN_DIR --draw-seed`: the one seed of a run's split suite, drawn
    from `os.urandom` and written to RUN_DIR/controls-seed.json with the time it was drawn
    (RFC-0008 SPLIT-1). Written once: refused when the file or controls.json exists. It needs
    only run.json and manifest.json, so it can run on a copy that holds just those two.
    `control_seed` is for tests, which need a known seed; the command never passes one."""
    for name in ("controls.json", SEED_RECORD):
        if (run_dir / name).exists():
            raise IProofsError(ErrorKind.CONFIG, f"{run_dir / name} exists; it is never redrawn")
    run_id = _completed_run(run_dir)["run_id"]
    drawn_at = now().astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    doc = seed_document(run_id, file_digest(run_dir / "manifest.json"),
                        control_seed or new_control_seed(), drawn_at)  # fmt: skip
    errors = registry.errors(SEED_SCHEMA, doc)
    if errors:
        raise IProofsError(ErrorKind.INTERNAL, f"{SEED_RECORD} fails {SEED_SCHEMA}: {errors[0]}")
    write_json(run_dir / SEED_RECORD, doc)
    return run_dir / SEED_RECORD


def read_seed(registry: SchemaRegistry, run_dir: Path) -> tuple[str, str]:
    """(control_seed, sha256 of the file) of RUN_DIR/controls-seed.json, which must be valid
    and drawn for this run: its run id and the digest of this manifest.json (SPLIT-1)."""
    path = run_dir / SEED_RECORD
    if not path.is_file():
        raise IProofsError(
            ErrorKind.CONFIG,
            f"{run_dir} has no {SEED_RECORD}: draw the suite's seed once with "
            f"iproofs controls {run_dir} --draw-seed",
        )
    doc = json.loads(path.read_text())
    errors = registry.errors(SEED_SCHEMA, doc)
    if errors:
        raise IProofsError(ErrorKind.CONFIG, f"{path} fails {SEED_SCHEMA}: {errors[0]}")
    run_id = json.loads((run_dir / "run.json").read_text())["run_id"]
    if (doc["run_id"], doc["run_manifest_digest"]) != (
        run_id,
        file_digest(run_dir / "manifest.json"),
    ):
        raise IProofsError(ErrorKind.CONFIG, f"{path} was not drawn for {run_dir}")
    return str(doc["control_seed"]), file_digest(path)


def _part_host(
    runner: Runner, job: Job, run_machine: Mapping[str, Any], prover_side: bool
) -> dict[str, object]:
    """The host a part ran on (RFC-0008 SPLIT-3, SPLIT-4): its machine record (RFC-0006, the
    allowlisted fields only) and the lines of every profile check it does not meet, which are
    recorded, not refused. Refused: a prover-side part on a GPU other than the run's, whose
    proves would be another configuration's."""
    env = runner.env
    verifier_only = isinstance(env, VerifierEnvironment)
    roles = ("verifier", "verifier_1") if verifier_only else ("prover", "verifier", "verifier_1")
    cpus = {role: _cpu_list(env.cpus(role)[0]) for role in roles}  # type: ignore[arg-type]
    record = machine_record(
        env.host(),
        results=job.staging,
        gpu_index=env.gpu(),
        cpus=cpus,
        mems=_cpu_list(env.cpus(roles[0])[1]),  # type: ignore[arg-type]
        provider=runner.provider,
        verifier_host="separate" if verifier_only else "same_as_prover",
        redact=runner.redact,
    )
    assert job.reference is not None
    lines: list[str] = []
    if verifier_only:
        found = job.reference.profiles.get("verifier-cpu")
        memory: dict[str, Any] = record.get("memory", {})  # type: ignore[assignment]
        usable = min(memory.get("available_bytes_at_start", 0),
                     memory.get("cgroup_limit_bytes", 2**63))  # fmt: skip
        if isinstance(found, VerifierProfile) and usable < found.host_memory_gib * 1024**3:
            lines.append(f"PC-MEM: {usable} B available or allowed < {found.host_memory_gib} GiB")
    else:
        profile = job.reference.profiles[job.spec.profile]
        if isinstance(profile, ProverProfile):
            gpu = record.get("gpu")
            node = gpu.get("numa_node") if isinstance(gpu, dict) else None
            topology = usable_topology(env.host()).cpus
            on_node = sum(c.node == node for c in topology) if node is not None else None
            lines = [f.line() for f in check_profile(record, profile, numa_node_cpus=on_node)]
        ran_on = (run_machine.get("gpu") or {}).get("model")
        here = (record.get("gpu") or {}).get("model")  # type: ignore[attr-defined]
        if prover_side and ran_on is not None and here != ran_on:
            raise IProofsError(
                ErrorKind.CONFIG,
                f"the run proved on {ran_on!r}; this host's GPU is {here!r}: prover-side "
                "controls prove on the run's GPU (RFC-0008 SPLIT-3)",
            )
    return {"machine": record, "nonconforming": lines}


def controls_for_run(  # noqa: PLR0915 (one check per refusal)
    runner: Runner,
    run_dir: Path,
    *,
    seed: str | None = None,
    only: Sequence[str] | None = None,
) -> Path:
    """`iproofs controls RUN_DIR`: the control suite against a completed run whose proof bytes
    were kept (`--keep-io`); adds `controls.json` to the run directory (append-only), once per
    run, whole or from parts. With `only` it runs those controls with the seed of the run's
    controls-seed.json (`seed`, if given, must be that one) and writes a part for `--merge`
    (RFC-0008 §Split suites); the whole suite runs with `seed` (tests) or a fresh one, and is
    refused once a seed record exists. The weights are resolved only when a prover-side control
    runs, and a prover-side control of a GPU profile needs the runner's GPU."""
    if (run_dir / "controls.json").exists():  # once per configuration (§Where controls run)
        raise IProofsError(ErrorKind.CONFIG, f"{run_dir} already has controls.json")
    io = run_dir / "io"
    if not (io / "proofs").is_dir() or not (io / "prove.out.json").is_file():
        raise IProofsError(ErrorKind.CONFIG, f"{run_dir} kept no proofs; rerun with --keep-io")
    doc = _completed_run(run_dir)
    suite = control_suite(runner.root, runner.registry, doc["system"])
    ids = parse_only(only, [cid for cid, _ in suite]) if only is not None else None
    part: dict[str, object] | None = None
    if ids is not None:
        recorded, seed_digest = read_seed(runner.registry, run_dir)
        if seed is not None and seed != recorded:
            raise IProofsError(
                ErrorKind.CONFIG,
                f"--seed {seed} is not the seed {recorded} of {run_dir / SEED_RECORD}",
            )
        seed = recorded
        target = run_dir / part_name(seed, ids)
        if target.exists():
            raise IProofsError(ErrorKind.CONFIG, f"{target} exists; it is never overwritten")
    elif (run_dir / SEED_RECORD).exists():
        raise IProofsError(
            ErrorKind.CONFIG,
            f"{run_dir} has {SEED_RECORD}: its suite runs in parts (--only) and --merge",
        )
    prover = [cid for cid, side in suite if side == "prover" and (ids is None or cid in ids)]
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
    runner._resolve_inputs(job, models=bool(prover))
    assert job.reference is not None
    profile = job.reference.profiles[spec.profile]
    gpu_profile = isinstance(profile, ProverProfile) and profile.gpu is not None
    no_gpu = gpu_profile and runner.env.gpu() is None  # GPU index 0 is a GPU
    no_prover = isinstance(runner.env, VerifierEnvironment) or no_gpu
    if prover and no_prover:  # a prove that cannot run here must not read as prover_failed
        raise IProofsError(
            ErrorKind.CONFIG,
            f"prover-side controls {', '.join(prover)} prove on a host of {spec.profile}: give "
            "--gpu on such a host, or --only verifier-side controls",
        )
    manifest = json.loads((run_dir / "manifest.json").read_text())
    job.image = manifest["system"]["image"]["ref"]
    job.level = manifest.get("level")  # a level session's suite (RFC-0018 CH-1)
    job.optional_subcommands = tuple(manifest["system"].get("optional_subcommands", ()))
    job.commitment_record = manifest["commitment"]  # digests rechecked before every verify
    job.proof_records = manifest["proofs"]  # proof digests rechecked before every control
    if not (run_dir / COMMITMENT_STORE).is_dir():
        raise IProofsError(ErrorKind.CONFIG, f"{run_dir} kept no commitment store")
    if ids is not None:
        perturbed = runner._perturbed(job)
        if "P1" in ids and not isinstance(perturbed, str) and perturbed_weights(perturbed) is None:
            raise IProofsError(  # a single run on the host that made them would run P1
                ErrorKind.CONFIG,
                f"P1: the perturbed weights of {perturbed.model_digest} are not in this host's "
                "cache; run P1's part where they are (RFC-0008 SPLIT-2)",
            )
        host = _part_host(runner, job, manifest.get("machine") or {}, bool(prover))
        part = {"seed_record_digest": seed_digest, "host": host}
    job.prompts = [json.loads(line) for line in (io / "prompts.jsonl").read_text().splitlines()]
    for name, attr in (("commit", "commit"), ("prove", "proofs")):
        out = load(io / f"{name}.out.json", runner.registry)
        assert isinstance(out, AdapterOut)
        setattr(job, attr, out)
    job.releases = [(p["proof_id"], p["release_mono_ns"]) for p in doc["proofs"]]
    job.verdicts = {p["proof_id"]: p["verdict"] for p in doc["proofs"]}
    progress = None if runner.progress is None else Progress(runner.progress, 1, 1, runner.redact)
    try:
        with (run_dir / "logs/harness.jsonl").open("a") as stream:
            log = JsonlLogger(stream, redactor=runner.redact, mono=runner.clock, on_record=progress)
            return runner._controls(job, log, seed=seed, only=ids, part=part)
    finally:
        shutil.rmtree(run_dir / "controls-io", ignore_errors=True)


def merge_controls(registry: SchemaRegistry, run_dir: Path, parts: Sequence[Path]) -> Path:
    """`iproofs controls RUN_DIR --merge PART...`: the `controls.json` of a suite run in parts
    (RFC-0008 §Split suites). RUN_DIR needs run.json, manifest.json and the controls-seed.json
    the parts ran with. Every part must be valid `controls-part/1` and made against this run
    (its run id, the digest of its manifest.json and of its seed record); `merge_parts` checks
    the rest. The document is checked against `controls/1` and written once, never over an
    existing one."""
    target = run_dir / "controls.json"
    if target.exists():
        raise IProofsError(ErrorKind.CONFIG, f"{target} exists; it is never overwritten")
    run_id = json.loads((run_dir / "run.json").read_text())["run_id"]
    manifest = file_digest(run_dir / "manifest.json")
    seed, seed_digest = read_seed(registry, run_dir)
    docs: dict[str, dict[str, object]] = {}
    for path in parts:
        if str(path) in docs:
            raise IProofsError(ErrorKind.CONFIG, f"{path} is given twice")
        doc = json.loads(path.read_text())
        errors = registry.errors("controls-part/1", doc)
        if errors:
            raise IProofsError(ErrorKind.CONFIG, f"{path} fails controls-part/1: {errors[0]}")
        made_for = (doc["run_id"], doc["run_manifest_digest"])
        if made_for != (run_id, manifest):
            raise IProofsError(ErrorKind.CONFIG, f"{path} was not made against {run_dir}")
        if (doc["control_seed"], doc["seed_record_digest"]) != (seed, seed_digest):
            raise IProofsError(ErrorKind.CONFIG, f"{path} did not run with {run_dir / SEED_RECORD}")
        docs[str(path)] = doc
    merged = merge_parts(docs)
    errors = registry.errors("controls/1", merged)
    if errors:
        message = f"merged controls.json fails controls/1: {errors[0]}"
        raise IProofsError(ErrorKind.INTERNAL, message)
    write_json(target, merged)
    return target


def perturbed_dir(results_root: Path, release: str, system: str, workload: str) -> Path:
    """Where a workload's perturbed commitment lives (RFC-0008 §Shared controls)."""
    return results_root / release / system / "_controls" / workload


def prepare_perturbed(
    runner: Runner, spec: JobSpec, cache: Path, change: str | None = None
) -> Path:
    """`iproofs controls --prepare-perturbed WORKLOAD` (RFC-0008 C3 and P1): perturb one
    element of the workload's weights into `<cache>/perturbed/<model digest>/`, commit that
    copy through the adapter, and store the commit record and its files under
    `results/<release>/<system>/_controls/<workload>/`. Once per workload per release; the
    perturbed weights stay in the cache on this host.

    With `change` (a level's `systems.<id>.model_change`, RFC-0018 CH-2), W' comes from the
    adapter's own `perturb` subcommand (AD-5), refused when its `info` does not list it, and
    the setup and commit of W' run as control C3 with that perturbation in their job."""
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
        control: dict[str, object] | None = None
        if change is not None:
            perturbation: dict[str, object] = runner._perturb(job, change, weights)
            control = {"id": "C3", "perturbation": perturbation}
        else:
            try:
                perturbation = asdict(perturb_model(job.models, weights))
            except NotApplicable as e:
                raise IProofsError(ErrorKind.CONFIG, f"cannot perturb {spec.workload}: {e}") from e
        job.models = weights
        if control is not None:
            runner._setup(job, control)
        runner._commit(job, control)
        record: dict[str, Any] = {
            "schema": "perturbed-commitment/1",
            "release": spec.release,
            "system": spec.system,
            "workload": {"id": job.workload.id, "version": job.workload.version},
            "source_model_digest": source,
            "model_digest": model_digest(weights),
            "perturbation": perturbation,
            "commitment": job.commitment_record,
            "image": job.image,
            "harness_version": __version__,
        } | ({"change": change} if change is not None else {})
        errors = runner.registry.errors("perturbed-commitment/1", record)
        if errors:
            raise IProofsError(ErrorKind.INTERNAL, "perturbed.json: " + "; ".join(errors))
        out.mkdir(parents=True)
        shutil.copytree(job.staging / COMMITMENT_STORE, out / "commitment")
        write_json(out / "perturbed.json", record)
    return out / "perturbed.json"


DECLARABLE = {"config": ErrorKind.CONFIG, "resource": ErrorKind.RESOURCE}


def _declared_failure(io: Path, job: Job) -> tuple[ErrorKind, str, list[str]] | None:
    """RFC-0005 (amendment of 2026-11-09): a reference adapter that exits non-zero may declare
    why in `/io/failure.json` {kind, message, evidence}: `config` (an engine environment
    variable the image does not set, a GPU count other than the tensor-parallel size, RFC-0015
    SRV-3) or `resource` (the engine's KV cache below the matched load, with the engine's own
    line as evidence, SRV-6). Anything else, or a proving system, stays an `adapter` failure."""
    path = io / "failure.json"
    if not _reference(job) or not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text())
    except ValueError:
        return None
    kind = DECLARABLE.get(str(doc.get("kind"))) if isinstance(doc, dict) else None
    if kind is None:
        return None
    evidence = doc.get("evidence")
    lines = [str(x)[:1000] for x in evidence[:20]] if isinstance(evidence, list) else []
    return kind, str(doc.get("message", ""))[:1000], lines


def _steady_warnings(job: Job, m: Mapping[str, QuantityTree], early: int) -> None:
    """RFC-0004 INV-SCOPE-5: later-batch requests released before the steady start; RFC-0015
    SRV-1: a serving run's steady scope under 60 s keeps its value, labelled (it joins no
    D-OVERHEAD-S, INV-DERIVE-2)."""
    if early:
        job.warnings.append(f"{early} later-batch request(s) released at or before the steady "
                            "start, left out of the steady tokens")  # fmt: skip
    steady = m.get("prove_steady_seconds", {}).get("value")
    if job.serving_entry is not None and isinstance(steady, float) and steady < 60:
        job.warnings.append(SHORT_STEADY)


def profile_gpu_count(profile: object, name: str) -> int | None:
    """RFC-0004 INV-DERIVE-8: the GPUs a configuration on `profile` holds, `gpu.count`; None for
    a CPU-only test profile (`gpu: null`). A GPU profile without a positive count is `config`
    (the schema requires one; this holds for every profile class)."""
    gpu = getattr(profile, "gpu", None)
    if gpu is None:
        return None
    count = getattr(gpu, "count", None)
    if not isinstance(count, int) or count < 1:
        raise IProofsError(ErrorKind.CONFIG, f"profile {name} has GPU count {count!r}, not >= 1")
    return count


def _batch_size(job: Job) -> int:
    """The run's batch size (INV-SCOPE-5): the workload's, or a serving run's (SRV-1)."""
    return _run_shape(job)[0]


def _run_shape(job: Job) -> tuple[int, int]:
    """(batch size, batches): the workload's shape, or a production-serving run's (SRV-1)."""
    assert job.workload is not None
    if job.run_shape is not None:
        return job.run_shape
    return job.workload.shape.batch_size, job.workload.shape.batches_per_session


def _serve(job: Job) -> bool:
    return (
        job.system is not None
        and job.system.kind == "reference"
        and (job.system.reference_role == "serve")
    )


def _serving_fields(job: Job) -> dict[str, object]:
    """job.json's load point and GPU count for a production-serving prove (RFC-0005)."""
    entry = job.serving_entry
    if entry is None:
        return {}
    gpus = {"gpus": entry.gpus} if entry.gpus is not None else {}
    return {"load_point": entry.load_point or "matched", **gpus, **(job.ladder or {})}


def _engine_args(job: Job) -> tuple[str, ...]:
    """The job's `engine_args` in system.yaml at the run's commit (RFC-0015 SRV-3): the serving
    entry's, else the workload's first reference entry."""
    assert job.system is not None
    if job.serving_entry is not None:
        return job.serving_entry.engine_args
    return next(
        (w.engine_args for w in job.system.workloads
         if isinstance(w, ReferenceWorkload) and w.id == job.spec.workload),
        (),
    )  # fmt: skip


def engine_interface(io: Path) -> str | None:
    """RFC-0015 Q8: the interface the adapter built the engine in, from its recorded command:
    `vllm serve` for the OpenAI-compatible server, `LLM class` for the Python class."""
    path = io / "commands.jsonl"
    for line in path.read_text(errors="replace").splitlines() if path.is_file() else []:
        try:
            argv = json.loads(line).get("argv")
        except (ValueError, AttributeError):
            continue
        if isinstance(argv, list) and argv[:2] == ["vllm", "serve"]:
            return "vllm serve"
        if isinstance(argv, list) and argv[:1] == ["vllm.LLM"]:
            return "LLM class"
    return None


OBSERVED_KEYS = ("version", "build_commit", "max_num_batched_tokens")


def engine_observed(io: Path) -> dict[str, object] | None:
    """RFC-0004 INV-DERIVE-2 (e): the engine the adapter saw run, from its recorded command
    (`engine_observed`: installed version, the image ENV's build commit, and the batched-token
    limit the engine logged); None when the adapter recorded none."""
    path = io / "commands.jsonl"
    for line in path.read_text(errors="replace").splitlines() if path.is_file() else []:
        try:
            seen = json.loads(line).get("engine_observed")
        except (ValueError, AttributeError):
            continue
        if isinstance(seen, dict):
            out = {k: seen.get(k) for k in OBSERVED_KEYS}
            ok = (all(isinstance(out[k], str | None) for k in OBSERVED_KEYS[:2])
                  and isinstance(out["max_num_batched_tokens"], int | None))  # fmt: skip
            return out if ok else None
    return None


def engine_command_problem(io: Path, args: Sequence[str], *, required: bool) -> str | None:
    """RFC-0015 SRV-3: the engine command a reference adapter records in /io/commands.jsonl
    (RFC-0005 §Command log) ends with the job's `engine_args`, verbatim, as system.yaml at the
    run's commit lists them. The adapter reads its options from the system.yaml baked into its
    image, so an image built from another system.yaml would otherwise serve one configuration
    under another's manifest. None when it does, or when there is nothing to compare: no
    `engine_args`, or no engine command and not `required` (a step that failed before the
    engine started). Ported from branch ref-serve-gguf, commit 4cdc33f."""
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


def _reference(job: Job) -> bool:
    return job.system is not None and job.system.kind == "reference"


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
    doc = json.loads((run_dir / "run.json").read_text())
    proofs = doc.get("proofs", [])
    replies = read_replies(run_dir, doc)  # from the entries, or the replies file by digest
    claims = {p.get("request_index"): replies.get(str(p.get("proof_id"))) for p in proofs}
    if not proofs or None in claims.values() or set(claims) != set(range(len(claims))):
        raise IProofsError(ErrorKind.CONFIG, f"{run_dir}: no claimed outputs in the source run")
    return [list(claims[i] or ()) for i in range(len(claims))]


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
