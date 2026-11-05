# RFC-0011: External measurement and resource sampling

- Status: Draft
- Authors: AbdelStark
- Created: 2026-11-03
- Target milestone: v0.1-beta
- Requires: RFC-0004, RFC-0005, RFC-0006, RFC-0010
- Supersedes: none
- Discussion: pull request that introduces it

## Summary

This RFC specifies how the harness measures a job from outside the adapter container: the clock, how a container call is timed, how proof release times are observed, how GPU and host resources are sampled, how proof sizes are counted, and the self-test a host runs before its numbers are accepted. Every recorded metric in RFC-0004 is produced by exactly one mechanism defined here.

## Motivation

The benchmark's numbers are only as good as the instruments behind them. PRD F9 asks for a harness that "measures externally": upstream figures come from scripts and records readers cannot always see (FlashProve's performance page says its measuring scripts are not in the repository, RFC-0007), so this project must not depend on code inside the container for its headline numbers. The draft SPEC listed the quantities (wall time, GPU memory peak at 10 Hz or faster, host memory from cgroup with file cache excluded, CPU time, energy, proof size) but not how to obtain each one correctly. Three details decide whether the numbers are right: cgroup files vanish when a container exits, page cache inflates `memory.peak`, and a proof's release time is invisible unless the adapter makes it observable. This RFC fixes all three.

## Goals

- Durations come from one monotonic clock in the harness process; no duration uses wall-clock time.
- Proof release times are observed by the harness, not reported by the adapter.
- GPU sampling meets 10 Hz minimum (20 Hz target) with gaps detected and reported.
- Final cgroup counters (`memory.peak`, `cpu.stat`) are read after the container exits, exactly.
- The harness's own measurement overhead stays inside a stated budget and runs on CPUs the job does not use.
- A host proves it can measure (self-test) before any run on it is accepted.

## Non-Goals

- Profiling inside the prover (kernel timings, NVTX ranges). Adapter-reported phases are allowed but are labelled and never feed derived metrics (RFC-0004 INV-GRADE-2).
- Network and disk I/O accounting (containers run with `--network none`; disk I/O is not a v0.1 metric).
- Non-Linux hosts for GPU runs. CPU-only steps (validation, derivation, fake-system runs) work anywhere; the cgroup and inotify mechanisms below are Linux-only and are replaced by portable fallbacks or disabled elsewhere (§Portability).

## Proposed Design

### Clock

- C-1. Durations use `time.monotonic_ns()` (CLOCK_MONOTONIC on Linux). Records also carry RFC 3339 UTC wall-clock timestamps from `datetime.now(UTC)` for humans; these never enter arithmetic.
- C-2. Every boundary event in RFC-0004 §Timing scopes is a `mono_ns` integer stored in `run.json` `events` (`{"event": "prove.start", "mono_ns": ...}`, RFC-0012), so every duration can be recomputed from stored events. Seconds metrics are derived from events by `iproofs.measure.span_seconds(start_ns, end_ns) -> float` = `(end_ns - start_ns) / 1e9`.
- C-3. The harness process pins itself (`os.sched_setaffinity`) to one logical CPU outside `cpu.bound_prover` and `cpu.bound_verifier` (RFC-0006), so its threads never compete with the job.

### Timing a container call

Each adapter call is two Docker CLI steps: `docker create` (untimed, returns the container id) then `docker start --attach <id>` (timed).

```python
@dataclass(frozen=True, slots=True)
class CallTiming:
    start_ns: int        # immediately before spawning `docker start --attach`
    end_ns: int          # immediately after the subprocess is reaped
    exit_code: int
    container_id: str    # kept in memory only; never written to records

def timed_call(argv_create: Sequence[str], timeout_s: float, on_started: Callable[[str], None]) -> CallTiming: ...
```

- T-1. `start_ns` is read after `docker create` returns and before `subprocess.Popen` of `docker start`. Container start-up (namespace creation, GPU device injection) is inside the call and is not subtracted (RFC-0004).
- T-2. Timeout per step comes from `system.yaml` (RFC-0010). On timeout the harness runs `docker kill`, records kind `timeout`, and still reads final cgroup counters.
- T-3. The container id is used for cgroup paths and kill only; it is a host-local identifier and is never logged or written (RFC-0006 exclusion list).

### Cgroup accounting

The container's own cgroup is removed by the runtime when the container exits, so its final counters cannot be read afterwards. The harness therefore places each container under a parent slice it owns:

- G-1. Before each call the harness starts a placeholder scope `systemd-run --scope --slice=iproofs-<job_hash>-<step>.slice --unit=iproofs-<job_hash>-<step>-hold sleep infinity`, where `job_hash` is the first 12 hex digits of the sha256 of the run id. This keeps the slice alive after the container exits.
- G-2. The container is created with `--cgroup-parent=iproofs-<job_hash>-<step>.slice`. Its cgroup becomes a child of the slice; cgroup v2 hierarchical accounting makes the slice's `memory.peak` and `cpu.stat` cover it.
- G-3. Before start the harness reads the slice's `memory.peak` (placeholder only) as `baseline_bytes` and `cpu.stat` `usage_usec` as `cpu_baseline_usec`. After the call ends it reads both again, then stops the placeholder unit.
- G-4. `<step>_host_memory_peak_kernel` = slice `memory.peak` after the call (bytes, includes page cache, exact for the slice, biased upward by at most `baseline_bytes`, which is recorded). `<step>_cpu_seconds` = (`usage_usec` after − `cpu_baseline_usec`) / 1e6.
- G-5. `<step>_host_memory_peak_anon` = max over samples of `memory.stat` `anon` of the slice, sampled at 10 Hz by the sampler thread. It excludes file cache and is a sampled peak: a spike shorter than the sampling period can be missed.

RISK: "host memory peak, file cache excluded" has no exact kernel counter in cgroup v2; the anon peak is sampled. Resolution: both numbers are published with their definitions (`kernel` exact including cache, `anon` sampled excluding cache), never one silently in place of the other. If a system's anon peak and kernel peak diverge by more than page cache explains in review, a follow-up RFC MAY add an eBPF-based peak.

```python
class CgroupReader:
    def __init__(self, slice_path: Path) -> None: ...         # /sys/fs/cgroup/iproofs.slice/... resolved via `systemctl show -p ControlGroup`
    def memory_peak(self) -> int: ...                          # bytes, memory.peak
    def memory_anon(self) -> int: ...                          # bytes, memory.stat "anon"
    def cpu_usage_usec(self) -> int: ...                       # cpu.stat "usage_usec"
    def oom_kills(self) -> int: ...                            # memory.events "oom_kill"
```

- G-6. A non-zero `oom_kill` delta over the call makes the step fail with kind `resource`, whatever the exit code.
- G-7. If `memory.peak` is absent (kernel older than 5.19) or the slice cannot be created, the conformance check fails (RFC-0006 PC-KERNEL, PC-CGROUP) before any timed step.

### Proof release watcher

Adapters write each proof as `/io/proofs/.tmp-<proof_id>/` and then `rename(2)` it to `/io/proofs/<proof_id>/` (RFC-0005). `/io` is a bind mount of a host directory, so the rename is visible on the host.

```python
@dataclass(frozen=True, slots=True)
class Release:
    proof_id: str
    mono_ns: int

class ReleaseWatcher:
    def __init__(self, proofs_dir: Path, poll_interval_s: float = 0.010) -> None: ...
    def start(self) -> None: ...              # before the prove call starts
    def stop(self) -> list[Release]: ...      # after the prove call ends; ordered by mono_ns
    @property
    def mechanism(self) -> Literal["inotify", "poll"]: ...
    @property
    def observable(self) -> bool: ...         # false when releases are not distinguishable (W-4)
```

- W-1. On Linux the watcher uses inotify through `ctypes` (`inotify_init1`, `inotify_add_watch` with `IN_MOVED_TO | IN_ONLYDIR`) in a dedicated thread; the timestamp is `monotonic_ns()` taken when the event is read. No third-party dependency.
- W-2. If inotify is unavailable, the watcher polls `os.scandir` every 10 ms and timestamps a new non-`.tmp-` directory at the first poll that sees it. `mechanism` records which was used; with polling the release time error is at most one poll interval plus scheduling delay.
- W-3. A directory that appears without passing through `.tmp-` (direct creation) is accepted but logged as event `release.nonatomic`; a proof whose parts change after release (detected by comparing part sizes at release and after the call) fails the job with kind `adapter`.
- W-4. `observable` is false when `system.yaml` declares `incremental_proofs: false`, or when all k releases fall within one inotify read batch or one poll interval. Then `prove.steady` is null with `not_externally_observable` (RFC-0004 INV-SCOPE-3).
- W-5. Releases after the prove call has exited are an `adapter` error (the adapter must finish writing before exiting).

### GPU sampler

```python
@dataclass(frozen=True, slots=True)
class GpuSample:
    mono_ns: int
    memory_used_mib: float
    util_gpu_pct: int
    energy_mj: int | None

@dataclass(frozen=True, slots=True)
class SamplerSummary:
    samples: int
    target_hz: float
    achieved_hz: float
    gaps_over_150ms: int
    gap_fraction: float            # time in gaps / call duration
    max_gap_ms: float
    degraded: bool                 # gap_fraction > 0.05
    memory_peak_mib: float
    memory_baseline_mib: float
    util_mean_pct: float
    util_p95_pct: float
    energy_j: float | None
    anon_peak_bytes: int           # from CgroupReader.memory_anon, same thread

class Sampler:
    def __init__(self, gpu_index: int | None, cgroup: CgroupReader, target_hz: float = 20.0) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> SamplerSummary: ...
    def write_trace(self, path: Path) -> None: ...   # 1 Hz downsampled trace (max per second), CSV
```

- S-1. One sampler thread per call, started before `start_ns` and stopped after `end_ns`. Samples outside [`start_ns`, `end_ns`] are discarded from the summary.
- S-2. Scheduling uses absolute deadlines `t0 + i × period`; a missed deadline is skipped, not caught up, so a stall shows as a gap rather than a burst.
- S-3. Per sample, on the bound GPU only (`nvmlDeviceGetHandleByIndex(bound_index)`): `nvmlDeviceGetMemoryInfo().used`, `nvmlDeviceGetUtilizationRates().gpu`, and once at start and end `nvmlDeviceGetTotalEnergyConsumption()` (mJ). `anon` from the cgroup reader is read in the same loop at every second sample (10 Hz).
- S-4. Memory peak is the max of `used` over the call; the pre-call `used` is recorded as `memory_baseline_mib` and not subtracted. Utilisation mean is the time-weighted mean over samples; p95 is the 95th percentile by the nearest-rank method.
- S-5. A gap is an interval between consecutive samples above 150 ms. If gaps cover more than 5 % of the call, the GPU metrics are written with `degraded: true` in the quantity's `quality` field (RFC-0012) and the site prints the flag.
- S-6. Energy is optional: if `nvmlDeviceGetTotalEnergyConsumption` returns `NVML_ERROR_NOT_SUPPORTED`, the energy metrics are null with `null_reason: not_applicable`.
- S-7. Foreign-process check: before `info` and before each GPU step, `nvmlDeviceGetComputeRunningProcesses` on the bound GPU MUST return no process; otherwise the job fails with kind `environment` (RFC-0006 PC-GPU-BUSY). The check is repeated after each GPU step; a foreign process found then marks the step's GPU metrics `degraded: true` and logs `gpu.foreign_process`.
- S-8. Verify steps have no GPU; the sampler runs with `gpu_index=None` and records only the cgroup anon peak.

### Proof size accounting

```python
def proof_bytes(proof_dir: Path, io_root: Path) -> int: ...
def files_bytes(paths: Sequence[str], io_root: Path) -> int: ...
```

- Z-1. `proof_bytes` sums `st_size` of every regular file under `/io/proofs/<proof_id>/`. Symbolic links, device files and paths that resolve outside `io_root` fail the job with kind `adapter` (trust boundary, docs/spec/06-security.md).
- Z-2. `verifier_download_bytes` = `files_bytes(commit.out.verifier_files)`, the per-commitment bytes a verifier fetches once. `prover_keep_bytes` = `files_bytes(commit.out.prover_files)`.
- Z-3. Sizes are bytes as stored, uncompressed. Each part's sha256 is computed at the same time for the proof digest (RFC-0012) and `digests.txt` (RFC-0009).

### Measurement overhead budget

Targets (not results), checked by the self-test and by GPU-host test GH-OVERHEAD:

| Item | Target |
|---|---|
| Sampler plus watcher CPU use | at most 1 % of one logical CPU at 20 Hz, on the harness CPU (C-3) |
| Sampling jitter | p99 deadline lateness at most 10 ms |
| Harness resident memory | at most 256 MiB during a call |
| Trace file size | 1 Hz downsampled trace, within the 1 MiB per-file log cap (RFC-0009) for calls up to 6 hours |

The harness never runs on prover or verifier CPUs (C-3), so its overhead does not enter the job's cgroup counters.

### Calibration self-test

`iproofs machine-record --selftest` runs on the host before its first run of a release and before each run campaign; its JSON result is stored in `manifest.json` `self_test`. A run whose manifest lacks a passing self-test from the same harness version is refused by the validator for `results/` (RFC-0013). Checks:

| Check id | Procedure | Pass when |
|---|---|---|
| ST-CLOCK | 100,000 consecutive `monotonic_ns()` reads | never decreasing; median step at most 1 µs |
| ST-SAMPLER | sampler for 5 s at 20 Hz on the bound GPU | achieved at least 10 Hz, no gap above 150 ms |
| ST-JITTER | same run | p99 lateness at most 10 ms |
| ST-CGROUP | probe container (the pinned `systems/fake` image, subcommand `probe`, used only by the self-test) allocates and touches 256 MiB of anonymous memory, under a harness slice | slice `memory.peak` and sampled anon peak both at least 256 MiB; `cpu.stat` increased |
| ST-WATCH | probe container renames 3 directories 200 ms apart in a bind mount | 3 releases seen, consecutive differences within 200 ms ± 20 ms, mechanism `inotify` |
| ST-NVML | NVML init, bound GPU handle, busy check | no foreign process; energy support recorded |
| ST-OOM | probe container exceeds a 64 MiB limit | `oom_kill` delta detected |

Failure of any check exits 3 (`environment`) and names the check.

On a host under hosted execution (RFC-0006 §Hosted execution), `iproofs machine-record --selftest --hosted` runs the `systems/fake` entrypoint's `probe` as a process of the container the harness runs in, not as a probe container. ST-CLOCK, ST-NVML, ST-SAMPLER and ST-JITTER are unchanged. ST-CGROUP passes when the container's sampled `memory.stat` anon rises at least 256 MiB over its baseline during the probe and `cpu.stat` increases; the container's `memory.peak` covers its whole life and is not read. ST-WATCH is unchanged, with the probe as a process. ST-OOM is not run and is absent from the record: the container cannot set a memory limit for a probe to exceed. OOM kills during a hosted job are still read from the container's `memory.events` (RFC-0006).

### Portability

On non-Linux hosts and in hosted CI (fake system only): the watcher uses polling, the sampler runs without NVML (`gpu_index=None`), and cgroup readers are replaced by a null reader that yields null host-memory and CPU metrics with `null_reason: not_applicable`. Such runs are valid for testing and can never enter `results/` for a release (the validator requires a passing self-test, which needs Linux and NVML).

### Failure modes

| Failure | Response |
|---|---|
| Slice cannot be created (no systemd, no permission) | conformance fails, `environment`, exit 3 |
| Container exits before the sampler's first sample | summary with `samples: 0`; GPU metrics null with `step_failed` if the call failed, else `degraded: true` |
| NVML call error during a call | sample skipped, counted as gap; after 10 consecutive errors the sampler stops, GPU metrics `degraded: true` |
| OOM kill | step fails, kind `resource` (G-6) |
| Timeout | `docker kill`, kind `timeout`, counters read (T-2) |
| Proof symlink or path escape | kind `adapter`, job failed (Z-1) |
| Release after call exit, or parts changed after release | kind `adapter` (W-3, W-5) |
| Foreign GPU process before a step | kind `environment` (S-7) |
| Placeholder unit left running after a crash | next `iproofs run` stops stale `iproofs-*-hold` units before conformance and logs `cgroup.stale_cleanup` |

## Alternatives Considered

- **`docker stats` for memory and CPU.** Considered because it needs no cgroup code. Rejected: it reports usage including page cache at roughly 1 Hz, no peak, and stops at container exit.
- **Read the container's own cgroup and sample `memory.peak` until exit.** Considered because it avoids the placeholder slice. Rejected: the final interval before exit is lost for both peak and CPU time; the parent slice gives exact final counters for the cost of one `sleep` process, whose memory is recorded as `baseline_bytes`.
- **`--cgroupns` and a cgroupfs driver with harness-created directories.** Considered as simpler than systemd. Rejected: Docker hosts in the wild use the systemd driver by default, and mixing drivers on one host is unsupported; one mechanism is tested.
- **Adapter-reported per-proof timestamps.** Considered because it needs no watcher. Rejected: it would make release times depend on container code (PRD F9); the rename contract costs adapters one `rename` call.
- **A sampling subprocess instead of a thread.** Considered to avoid interpreter lock effects. Rejected for v0.1: the main thread is blocked in `wait` and NVML calls release the lock; ST-JITTER detects a host where this assumption fails, and the design can move to a subprocess without changing any record.
- **DCGM instead of NVML.** Considered for richer counters. Rejected: an extra daemon on the host for counters NVML already gives.

## Drawbacks

- The harness needs permission to run `systemd-run` and Docker, in practice root or equivalent on the GPU host.
- Container start-up is inside every call time; for short verify calls it can be a visible fraction (shown via `info_seconds`).
- The anon peak is sampled and can miss short spikes (RISK above).
- Release times under polling carry up to 10 ms error, recorded via `mechanism`.

## Conflicts of Interest

The author's affiliations and any interest in a measured system are declared in `MAINTAINERS.md` before this RFC enters Last call (RFC-0001).

## Migration / Rollout

New RFC; no results exist. It replaces the measurement table of the draft SPEC §4 with mechanisms; the draft's "host memory peak, file cache excluded" becomes two labelled metrics. Fields introduced in `run/1` and `manifest/1` (RFC-0012): `events`, `sampler` summaries per step, `watcher.mechanism`, `selftest`, quantity `quality.degraded`. Adapters gain one obligation (atomic proof directories, RFC-0005) that the fake system implements first.

## Testing Strategy

CPU-only (hosted CI):

- TC-SPAN: `span_seconds` on fixed integers; exact results.
- TC-WATCH-POLL: temp dir, a thread renames 5 `.tmp-` directories 50 ms apart; poll watcher returns 5 releases, ordered, each within 50 ms ± 15 ms of the previous.
- TC-WATCH-INOTIFY (Linux runners): same with inotify; tolerance ± 5 ms.
- TC-WATCH-BURST: 5 renames within 1 ms; `observable` false.
- TC-WATCH-DECLARED: `incremental_proofs: false` gives `observable` false regardless of timing.
- TC-WATCH-NONATOMIC: direct mkdir; release accepted, event `release.nonatomic` logged.
- TC-WATCH-MUTATED: a part grows after release; job fails `adapter`.
- TC-SAMPLER-GAPS: sampler with a fake NVML backend that stalls 400 ms twice in a 20 s call (gaps cover 4 % of it); `gaps_over_150ms` 2, `degraded` false; stall 400 ms 10 times; `degraded` true. (Two 400 ms stalls in 5 s would cover 16 %, above the S-5 threshold.)
- TC-SAMPLER-P95: fake utilisation series 1..100; p95 equals 95 by nearest rank.
- TC-SAMPLER-ENERGY-UNSUPPORTED: fake backend raises not supported; energy null `not_applicable`.
- TC-CGROUP-PARSE: `memory.stat`, `cpu.stat`, `memory.events` fixtures parsed to exact integers.
- TC-PROOF-BYTES: fixture proof dirs; symlink and `..` escape both fail `adapter`; sizes exact.
- TC-FOREIGN-PROC: fake NVML returns one process; job fails `environment` before `info`.

GPU host (runbook, not hosted CI):

- GH-SELFTEST: `iproofs machine-record --selftest` passes on prover-h100.
- GH-CGROUP-EXACT: probe container allocates 1 GiB anon then exits immediately; slice `memory.peak` at least 1 GiB after exit (proves the final read survives exit).
- GH-OVERHEAD: 30-minute fake prove call; harness CPU at most 1 % of one CPU, p99 lateness at most 10 ms.
- GH-NVML-PEAK: CUDA probe allocates 40 GiB on the bound GPU for 2 s; `memory_peak_mib` at least 40,960.

## Open Questions

- OPEN QUESTION Q1 (owner: AbdelStark, resolve by: 2027-01-31): should verify calls on a separate verifier host use the same slice mechanism or a lighter reader? Default until resolved: same mechanism, same self-test on that host.
- OPEN QUESTION Q2 (owner: AbdelStark, resolve by: 2027-01-31): does any v0.1 upstream write proofs incrementally at its pin? Default until resolved: each adapter declares `incremental_proofs` from the upstream documentation; the declaration is confirmed by the first GPU-host run and corrected by pull request.

## References

- docs/PRD.md §7 (F9), §11.
- [RFC-0004](0004-metrics-timing-grades.md) for metric ids and scopes; [RFC-0005](0005-adapter-contract.md) for the proof directory contract; [RFC-0006](0006-reference-hardware-and-cost.md) for CPU binding and conformance; [RFC-0009](0009-results-and-publication.md) for log caps; [RFC-0010](0010-harness-runner.md) for steps, timeouts and error kinds; [RFC-0012](0012-schemas-and-serialization.md) for `run/1` fields.
- Linux kernel documentation, cgroup v2 (`memory.peak`, `memory.stat`, `cpu.stat`, `memory.events`) and inotify(7).
- NVIDIA Management Library API reference (`nvmlDeviceGetMemoryInfo`, `nvmlDeviceGetUtilizationRates`, `nvmlDeviceGetTotalEnergyConsumption`, `nvmlDeviceGetComputeRunningProcesses`).
