# RFC-0010: Harness runner and job lifecycle

- Status: Draft
- Authors: AbdelStark
- Created: 2026-11-03
- Target milestone: v0.1-alpha
- Requires: RFC-0004, RFC-0005, RFC-0008, RFC-0011, RFC-0012
- Supersedes: none
- Discussion: pull request that introduces it

## Summary

Defines the `iproofs` command line, the job (one system, one workload, one shape, one repetition, one machine), the job state machine and what is written at each state, the concurrency model, step timeouts, the retry policy, the error taxonomy, and how failures are recorded so that no run is ever dropped or silently resumed. It is the operational core that turns the adapter contract ([RFC-0005](0005-adapter-contract.md)) and the measurement rules ([RFC-0011](0011-measurement-and-sampling.md)) into run directories ([RFC-0009](0009-results-and-publication.md)).

## Motivation

PRD requirement F9 asks for "a harness that runs a job end to end, measures externally, collects the adapter's internal timings and writes a result file valid against the schema". Non-functional requirement N3 asks that failed runs be "recorded, not dropped" ([PRD Section 7](../docs/PRD.md#7-requirements)). [AGENTS.md hard rule 5](../AGENTS.md#hard-rules) forbids rounding away results. A runner that retries a failed proving step until it succeeds, or resumes a half-finished job after a crash, would publish a number that never happened as measured. The runner's semantics therefore need to be fixed before any adapter exists.

Scenarios:

1. A runner on an H100 host runs three repetitions of `fp-maverick-w1024-b24`; the second repetition is OOM killed during `prove`. The run directory for repetition 2 is written with a `resource` failure; repetitions 1 and 3 are written normally; statistics report n = 2 and n_failed = 1.
2. The host loses power during `commit`. On restart, the runner finds an incomplete job directory, records it as a failed job of kind `internal` at step `commit`, and starts the next repetition from `pending`.
3. A CI job runs `iproofs run --system fake --workload fake-tiny-ci --profile ci-cpu --control-suite` on a hosted CPU runner in a few minutes, with no GPU.

## Goals

- One deterministic state machine per job, with every transition logged and every terminal job written.
- No timed step is ever retried; only network fetches outside timed scopes retry.
- A stable CLI with documented exit codes, usable from CI and by hand.
- Atomic writes: a run directory is either absent or complete and schema-valid; partial work lives in a staging directory.
- A crash never produces a measured row.
- A typed internal API that tests can drive without containers.

## Non-Goals

- Scheduling across hosts, queueing, or a service. One runner process drives one host.
- Running several jobs on one GPU concurrently.
- Resuming a job mid-step.
- Uploading results anywhere. Publication is a pull request ([RFC-0009](0009-results-and-publication.md)).

## Proposed Design

### Command line

`iproofs` uses stdlib `argparse`. Subcommands, arguments and behaviour:

| Command | Arguments | Behaviour |
|---|---|---|
| `iproofs validate [PATH ...] [--all] [--changed-since REF] [--format {text,json}]` | paths to files or directories; default and flags as [RFC-0013](0013-validation-and-ci.md#local-use) defines them | runs every CI check of [RFC-0013](0013-validation-and-ci.md) on the paths |
| `iproofs derive RUN_DIR [--check]` | one run directory | computes derived metrics and statistics ([RFC-0004](0004-metrics-timing-grades.md)); without `--check` writes them into a new `run.json` only for a run being written; with `--check` recomputes and compares bit for bit |
| `iproofs run --system S --workload W --profile P [--repetitions N] [--results DIR] [--control-suite] [--provider NAME] [--prompts-from RUN_DIR] [--allow-nonconforming]` | `N` default 3, minimum 1 (values below 3 are allowed for tests and marked `repetitions_below_minimum: true`); `DIR` default `results/`; `--provider` records the hosting provider in the machine record ([RFC-0006](0006-reference-hardware-and-cost.md#machine-record)); `--prompts-from` replays the prompt seeds of an earlier run (reference rows and reproductions, [RFC-0015](0015-reference-rows.md#steps-per-job)); `--allow-nonconforming` skips the profile conformance failure for development only and writes `harness.nonconforming: true` into the manifest, which the validator refuses (gate rule POL-4, [RFC-0013](0013-validation-and-ci.md#g6-policy-check)) | runs N jobs sequentially, then derives statistics across them |
| `iproofs controls RUN_DIR [--prepare-perturbed WORKLOAD]` | completed run directory | runs the control suite ([RFC-0008](0008-negative-controls.md)) and writes `controls.json`; with `--draw-seed`, the seed record of a split suite; with `--only`, one part of it, with that seed; and with `--merge`, `controls.json` from the parts ([RFC-0008 §Split suites](0008-negative-controls.md#split-suites)) |
| `iproofs machine-record [--selftest]` | none | prints the machine record ([RFC-0006](0006-reference-hardware-and-cost.md)) as JSON on stdout; `--selftest` also runs the calibration checks of [RFC-0011](0011-measurement-and-sampling.md#calibration-self-test) and exits 3 if any fails |
| `iproofs fetch-model WORKLOAD [--headers-only]` | workload id | fetches weights by source and revision, checks every file hash ([RFC-0014](0014-provenance-and-integrity.md)), then recomputes a `computed` weight width from the verified files ([RFC-0003](0003-workloads.md#weight-bits) WB-5); `--headers-only` fetches no weights and recomputes that width from HTTP range reads of the file headers at the pinned revision, printing the result as JSON |
| `iproofs prompts build WORKLOAD --seed SEED` | workload id, 64-bit seed | materialises the prompt set, prints its digest ([RFC-0003](0003-workloads.md)) |
| `iproofs reproduce compare ORIG_RUN REPRO_RUN` | two run directories or run groups | applies the tolerance rule of [RFC-0007](0007-evidence-tiers-and-reproduction.md), writes a reproduction record |
| `iproofs release freeze RELEASE` | release id | writes `releases/<release>/index.json` |
| `iproofs release plan RELEASE` | release id | projects the run-campaign compute budget from external figures with the derivation code ([08](../docs/spec/08-performance-budget.md#run-campaign-compute-budget)); output is `projected`, never a result |
| `iproofs site build [--out DIR]` | default the repository's `web/` | generates the public site from the newest frozen release (RFC-0009 §Site) |

Global options: `--log-level {debug,info,warning}` (default `info`), `--quiet` (no progress on stderr). No option changes what is measured; anything that would is part of the workload or system file and goes through review.

Exit codes (all commands):

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | a check failed: validation error, `derive --check` mismatch, reproduction outside tolerance |
| 2 | usage error (argparse) |
| 3 | environment does not meet the profile or a prerequisite (no cgroup v2, other GPU processes, missing Docker) |
| 4 | at least one job ran and was recorded as failed |
| 5 | internal error (harness bug); a run directory, if any, records it |

For `iproofs run`, a run directory is written for every job when the exit code is 0 or 4. Exit 3 is raised before any job starts, so nothing is written.

### Job specification

```python
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True, slots=True)
class JobSpec:
    system: str            # system id, RFC-0012 pattern
    workload: str          # workload id
    workload_version: int
    profile: str           # prover profile id, RFC-0006
    repetition: int        # 1-based index within this invocation
    control_suite: bool    # run RFC-0008 controls after verify
    results_root: str      # path to results/
    release: str           # e.g. "v0.1", from reference/<release>.yaml in force
```

The run id is `<YYYY-MM-DD>-<system>-<workload>-<profile>-<n>` where the date is the UTC date at job start and `n` is the smallest positive integer not already used under `results/<release>/<system>/` for that prefix (INV-RUN-6).

### State machine

```
pending -> resolved -> image_ready -> machine_recorded -> info -> setup -> commit -> prove -> verify -> controls -> written
   any non-terminal state --(failure)--> failed(step) -> written
```

- `controls` is skipped (transition `verify -> written`) when `control_suite` is false.
- `written` is the only terminal state. A failed job reaches `written` with `status: "failed"` and its failure record.

| State | Action on entry | Writes to staging |
|---|---|---|
| `pending` | create staging dir `results/<release>/<system>/.staging-<run-id>/`, write `job.lock` with pid and start time | `job.lock`, `logs/harness.jsonl` |
| `resolved` | load and validate system, workload, reference files; resolve model dir by digest; draw the job seed; materialise prompts and their digest | `manifest.partial.json` (inputs) |
| `image_ready` | check the local image digest equals `system.yaml` `image.digest` (pull by digest if absent, retried as `fetch`) | image record |
| `machine_recorded` | record the machine; check the profile; check no other compute process on the bound GPU; choose the cpuset | machine record |
| `info` | run `info`; check `upstream_commit` equals `system.yaml` | `io/info/out.json` |
| `setup` | run `setup` | `io/setup/` |
| `commit` | run `commit` with sampling | commit record (commitment id, files, sizes, times) |
| `prove` | run `prove` with sampling and the release watcher | proof release times, proof digests, out.json |
| `verify` | for each proof, run `verify` on the verifier profile (8 CPUs), then once on 1 CPU for the first proof | `verifier/<proof_id>.json` |
| `controls` | run the control suite | `controls.json` |
| `written` | compute raw metrics; assemble `run.json` and `manifest.json`; validate both; rename staging to the run dir | final run dir |

Each transition emits a `job.state` event ([05-observability](../docs/spec/05-observability.md#events-catalogue)). The verify step runs `verify` for every proof; single-thread verify runs for the first proof only, to bound CPU time.

### Writing the run directory

- All files are written into the staging dir. Each file is written to `<name>.tmp`, flushed, `fsync`ed, then renamed. JSON uses the single writer of [RFC-0012](0012-schemas-and-serialization.md).
- On `written`, the runner validates `run.json`, `manifest.json` and `controls.json` (if present) against their schemas. If validation fails, the job is recorded as failed `internal` (a harness bug), with the invalid document kept under `logs/invalid/`.
- The staging dir is renamed to `results/<release>/<system>/<run-id>/` and the parent directory is `fsync`ed. A run directory therefore exists only complete (INV-RUN-2).
- Job io dirs (`io/`) with proofs are not part of the run directory committed to git; proofs are digested into `digests.txt`, one proof per configuration is archived ([RFC-0014](0014-provenance-and-integrity.md)), and the io dir is deleted after archival unless `--keep-io` is given.

### Crash recovery

On start, `iproofs run` scans `results/<release>/*/.staging-*`. For each staging dir whose `job.lock` pid is not alive, the runner writes a failed run: `status: "failed"`, failure `{kind: "internal", step: <last state reached>, message: "runner terminated before completion"}`, keeping logs and any partial records, then renames it as a normal run dir. It never continues the job (INV-RUN-3). A staging dir whose pid is alive makes the runner exit 3 (another runner is active on this tree).

### Concurrency

- One job at a time per GPU; one runner process per host in v0.1. The runner holds an exclusive `flock` on `results/.runner.lock` for the duration of `iproofs run`.
- Steps within a job are strictly sequential.
- During `commit`, `prove` and `verify`, the runner starts sampler threads ([RFC-0011](0011-measurement-and-sampling.md)): one NVML sampler, one cgroup sampler, and during `prove` one release watcher. Samplers write to in-memory ring buffers and never block the main thread; the main thread joins them after the container exits.
- The main thread runs `docker create` (untimed), then blocks on `docker start --attach` with the step timeout ([RFC-0011](0011-measurement-and-sampling.md#timing-a-container-call)).

### Timeouts

Each step's wall limit comes from `system.yaml` `timeouts_s` or the defaults in [RFC-0005](0005-adapter-contract.md#systemyaml). When a limit is reached the runner sends `docker kill --signal KILL iproofs-<run-id>-<step>`, waits up to 30 s for the container to exit, and records a `timeout` failure. Model fetch and image pull have their own limit of 6 hours each (a target for fetches of models of about 200 GB, not a measurement).

### Retry policy

- Only `fetch` operations retry: model weights, prompt corpus downloads, image pulls by digest. Up to 3 attempts, with backoff of 2 s, 8 s and 32 s. All run before `machine_recorded`, outside every timed scope.
- No timed step (`setup`, `commit`, `prove`, `verify`, controls) is ever retried within a job (INV-RUN-1). A failed repetition is recorded and counts in `n_failed` ([RFC-0004](0004-metrics-timing-grades.md)). The runner then continues with the next repetition.
- A runner MAY start a new invocation with more repetitions later; those are new jobs with new run ids, and all jobs, failed ones included, enter the statistics of the configuration.

### Error taxonomy

```python
from enum import StrEnum

class ErrorKind(StrEnum):
    CONFIG = "config"
    ENVIRONMENT = "environment"
    INTEGRITY = "integrity"
    FETCH = "fetch"
    ADAPTER = "adapter"
    TIMEOUT = "timeout"
    RESOURCE = "resource"
    POLICY = "policy"
    INTERNAL = "internal"

class IProofsError(Exception):
    kind: ErrorKind
    def __init__(self, kind: ErrorKind, message: str, *, step: str | None = None,
                 exit_code: int | None = None, last_lines: tuple[str, ...] = ()) -> None: ...
```

| Kind | Triggers | CLI exit |
|---|---|---|
| `config` | input file fails its schema; unknown system or workload; workload not in `system.yaml` `workloads` | 1 (validate) or 2 (run, before jobs) |
| `environment` | cgroup v1; kernel below 5.19; Docker below 25.0; profile not met; other compute process on the GPU | 3 |
| `integrity` | model file hash mismatch; image digest mismatch; `info` upstream commit mismatch; unpinned reference | 4 (inside a job) or 1 (validate) |
| `fetch` | network failure after 3 attempts | 4 |
| `adapter` | non-zero exit; invalid out.json; INV-ADAPTER-6, 7 or 8 violated | 4 |
| `timeout` | step wall limit reached | 4 |
| `resource` | container OOM killed; disk full (`ENOSPC`) | 4 |
| `policy` | forbidden flag outside a control job; control job submitted as measured row | 4 (run) or 1 (validate) |
| `internal` | unexpected exception; own output fails its schema; crash recovery | 5 |

Verdicts (`accept`, `reject`, `no_verdict`, `invalid_call`) are results, not errors.

### Failure record

```python
@dataclass(frozen=True, slots=True)
class Failure:
    kind: ErrorKind
    step: str                      # state name at which the failure occurred
    message: str                   # redacted, <= 4096 bytes
    exit_code: int | None          # container or process exit code, if any
    last_lines: tuple[str, ...]    # last 50 lines of adapter stderr, redacted
    at: str                        # RFC 3339 UTC timestamp
```

Serialised into `run.json` as `failure` (null for successful jobs). Redaction follows [05-observability](../docs/spec/05-observability.md#redaction).

### Internal API

```python
@dataclass(frozen=True, slots=True)
class StepResult:
    step: str
    started_mono_ns: int
    ended_mono_ns: int
    exit_code: int
    out: dict[str, object] | None        # validated adapter-out document
    samples: "SampleSet"                 # RFC-0011
    releases: tuple[tuple[str, int], ...] = ()  # (proof_id, release_mono_ns), prove only

class ContainerRunner(Protocol):
    def run(self, image: str, subcommand: str, io_dir: Path, *, gpu: int | None,
            cpuset: str, mems: str, memory: str | None, timeout_s: float) -> StepResult: ...

@dataclass(slots=True)
class Job:
    spec: JobSpec
    state: str
    staging: Path
    steps: dict[str, StepResult]
    failure: Failure | None
    def advance(self) -> None: ...       # performs the action for the next state; raises IProofsError

class Runner:
    def __init__(self, containers: ContainerRunner, clock: Callable[[], int] = time.monotonic_ns) -> None: ...
    def run(self, spec: JobSpec) -> Path: ...                         # returns the written run dir
    def run_many(self, base: JobSpec, repetitions: int) -> list[Path]: ...
    def recover(self, results_root: Path) -> list[Path]: ...          # crash recovery
```

`ContainerRunner` has two implementations: `DockerRunner` (real) and `InProcessRunner` (tests, calls the fake adapter's Python entrypoint directly with the same file contract). The clock is injectable so state-machine tests are deterministic.

### Interaction with measurement and controls

- The runner owns the timed window: it reads the clock immediately before spawning `docker start --attach` and immediately after it returns ([RFC-0011](0011-measurement-and-sampling.md)). Sampler threads are started before and stopped after that window.
- Raw metrics (wall times, samples, release times, sizes) are written into `run.json` as quantities with `grade: "measured"`, `source.kind: "harness"`. Adapter phases become quantities with `source.kind: "adapter"`. Derived metrics are computed by `iproofs.derive` from the stored raw values, never from in-memory values (INV-RUN-5).
- The control suite reuses the runner's verify path and container runner with `control: true`; its outputs go only to `controls.json` (INV-CTRL-4).

### Invariants

- **INV-RUN-1:** No timed step is retried within a job.
- **INV-RUN-2:** A run directory under `results/` is complete and schema-valid, or does not exist.
- **INV-RUN-3:** A job interrupted before `written` is recorded as failed and never resumed.
- **INV-RUN-4:** Every job reaches `written`, including failed ones; the only exception is exit 3 raised before the first job starts.
- **INV-RUN-5:** Derived values in `run.json` equal what `iproofs derive` computes from the stored raw values.
- **INV-RUN-6:** Run ids are unique within `results/<release>/<system>/`.
- **INV-RUN-7:** The commitment passed to any `verify` comes from the job's commit record (INV-ADAPTER-5).

## Alternatives Considered

1. **Retry a failed `prove` once.** Considered because transient GPU errors happen and a rerun is cheaper than a new invocation. Rejected: the published distribution would silently exclude failures, which N3 forbids. The runner continues with the next repetition instead, and failures are visible.
2. **Resume interrupted jobs from the last completed step.** Considered because commits for the Maverick workloads take a long time. Rejected: the resumed job's timings would mix two process lifetimes and two machine states (page cache, GPU clocks), and `whole_wall` would be meaningless.
3. **A workflow engine (for example a DAG scheduler) or a job queue service.** Considered for multi-host campaigns. Rejected for v0.1: one host, one GPU, sequential jobs; a dependency and a service are not justified. A later RFC can add scheduling around the same `JobSpec`.
4. **Click or Typer for the CLI.** Considered for ergonomics. Rejected: `argparse` covers the surface, avoids a dependency, and keeps exit codes under direct control.
5. **Write results directly into the run directory as the job progresses.** Rejected: a crash would leave a directory that looks like a run; the staging-then-rename scheme keeps INV-RUN-2.

## Drawbacks

- A transient failure costs a full repetition, which on the SASH 4,096-position shape is long (upstream whole-wall rate 0.840 positions/s over 4,608 positions, grade external, tier reported, source SASH results at `11decec3c0b62c707618aab5deb82750b355d202`).
- Sequential jobs leave the GPU idle during `verify` and controls, which run on CPU. Pipelining is possible later but would contaminate CPU measurements of the next job.
- Crash recovery relies on pid liveness; a pid reused after reboot could make a stale staging dir look alive. The lock records boot id (`/proc/sys/kernel/random/boot_id`) as well as pid to rule that out.

## Conflicts of Interest

The author's affiliations and any interest in a measured system are declared in `MAINTAINERS.md` before this RFC enters Last call (RFC-0001).

## Migration / Rollout

- New RFC; no harness exists yet. The draft SPEC's job description (Section 3 of the initial design) is superseded by this RFC.
- v0.1-alpha ships the state machine with `InProcessRunner` and `DockerRunner` against `systems/fake`. v0.1-beta adds GPU sampling and the real adapters.
- CLI changes follow the harness SemVer policy ([09-release-and-versioning](../docs/spec/09-release-and-versioning.md)); exit codes are part of the public API and change only with a major version (or a minor version while 0.x, with a CHANGELOG entry).

## Testing Strategy

- `test_state_machine_happy_path`: `InProcessRunner` with the fake adapter visits every state in order and emits one `job.state` event per transition.
- `test_controls_skipped_without_flag`: `verify -> written` when `control_suite` is false.
- `test_failure_at_each_step`: parametrised over `info`, `setup`, `commit`, `prove`, `verify`; a fake adapter exiting 1 at that step yields a written run dir with `failure.step` equal to the step and exit code 4 from the CLI.
- `test_no_retry_of_timed_steps`: a fake adapter that fails once then succeeds is called exactly once per job for the failing step.
- `test_fetch_retries_three_times_with_backoff`: an injected fetcher failing twice then succeeding is called three times; sleeps of 2 s and 8 s are requested from an injected sleeper.
- `test_timeout_kills_container`: a fake step sleeping beyond a 1 s limit yields `timeout` and a `docker kill` call recorded by a stub.
- `test_oom_is_resource`: a stubbed `docker inspect` reporting `OOMKilled: true` yields `resource`.
- `test_crash_recovery_records_internal_failure`: a staging dir with a dead pid becomes a run dir with `failure.kind == "internal"` and the last reached step; no adapter call is made.
- `test_live_staging_blocks_runner`: a staging dir with a live pid and the current boot id makes `iproofs run` exit 3.
- `test_run_dir_atomic`: killing the runner between file writes never leaves a directory under `results/` without `run.json`.
- `test_run_id_increments`: two runs on the same day get suffixes 1 and 2.
- `test_exit_codes`: each documented exit code is produced by a minimal scenario (bad argument 2, cgroup v1 stub 3, failed job 4, injected exception 5, `derive --check` mismatch 1).
- `test_derived_from_stored_raw`: altering a raw value in a written `run.json` makes `iproofs derive --check` fail.
- `test_repetitions_below_minimum_marked`: `--repetitions 1` sets `repetitions_below_minimum: true`.

## Open Questions

- Resolved Q1: controls run once per configuration, on the first successful repetition ([RFC-0008](0008-negative-controls.md#where-controls-run)).
- OPEN QUESTION Q2 (owner: AbdelStark, resolve by: 2027-01-31): Whether single-thread verify should cover every proof rather than the first. Default: first proof only.
- OPEN QUESTION Q3 (owner: AbdelStark, resolve by: 2026-12-01): The size of the archive cap for io dirs kept with `--keep-io`. Default: no cap; the runner warns when free disk drops below the profile's 500 GB requirement.

## References

- [PRD Section 7, F9 and N3](../docs/PRD.md#7-requirements).
- [RFC-0004](0004-metrics-timing-grades.md), [RFC-0005](0005-adapter-contract.md), [RFC-0006](0006-reference-hardware-and-cost.md), [RFC-0007](0007-evidence-tiers-and-reproduction.md), [RFC-0008](0008-negative-controls.md), [RFC-0009](0009-results-and-publication.md), [RFC-0011](0011-measurement-and-sampling.md), [RFC-0012](0012-schemas-and-serialization.md), [RFC-0013](0013-validation-and-ci.md), [RFC-0014](0014-provenance-and-integrity.md).
- [docs/spec/04-error-model.md](../docs/spec/04-error-model.md), [docs/spec/05-observability.md](../docs/spec/05-observability.md).
- Linux `rename(2)`, `fsync(2)`, `flock(2)`.
