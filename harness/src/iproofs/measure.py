"""Clock events, container-call timing, release watcher, sampling, proof sizes (RFC-0011).

INV-ARCH-4: durations are read here, from the monotonic clock only (C-1).
"""

import ctypes
import ctypes.util
import hashlib
import itertools
import math
import os
import select
import stat
import struct
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Literal, Protocol

from iproofs.derive import span_seconds
from iproofs.errors import ErrorKind, IProofsError

KILL_WAIT_S = 30  # RFC-0010 §Timeouts: wait for the killed container to exit

__all__ = [
    "LOG_HEAD_BYTES",
    "LOG_TAIL_BYTES",
    "CallTiming",
    "Capture",
    "CgroupReader",
    "CgroupSlice",
    "ContainerCgroupReader",
    "EventLog",
    "GpuBackend",
    "GpuSample",
    "NullCgroupReader",
    "NvmlBackend",
    "Release",
    "ReleaseWatcher",
    "Sampler",
    "SamplerSummary",
    "SelfTestCheck",
    "SliceCgroupReader",
    "StepResources",
    "cap_text",
    "check_gpu_free",
    "drain",
    "job_hash",
    "nvml_available",
    "pin_harness_cpu",
    "select_readers",
    "span_seconds",
    "st_cgroup",
    "st_clock",
    "st_jitter",
    "st_nvml",
    "st_oom",
    "st_sampler",
    "st_watch",
    "stop_stale_holds",
    "summarize",
    "timed_call",
]


@dataclass(frozen=True, slots=True)
class CallTiming:
    start_ns: int  # read after `docker create` returned, before `docker start` is spawned
    end_ns: int  # read after the `docker start --attach` process is reaped
    exit_code: int
    container_id: str  # T-3: kept in memory only; never logged or written
    stdout: str
    stderr: str


# ---------------------------------------------------------------- resource readers (RFC-0011)


class CgroupReader(Protocol):
    """RFC-0011 §Cgroup accounting; a reading is None where the host cannot take it."""

    def memory_peak(self) -> int | None: ...
    def memory_anon(self) -> int | None: ...
    def cpu_usage_usec(self) -> int | None: ...
    def oom_kills(self) -> int | None: ...


class NullCgroupReader:
    """RFC-0011 §Portability: no cgroup v2 slice (non-Linux hosts, hosted CI, fake system
    only). Every reading is None, so host-memory and CPU metrics are null, `not_applicable`."""

    def memory_peak(self) -> int | None:
        return None

    def memory_anon(self) -> int | None:
        return None

    def cpu_usage_usec(self) -> int | None:
        return None

    def oom_kills(self) -> int | None:
        return None


@dataclass(frozen=True, slots=True)
class StepResources:
    """What the GPU sampler and the cgroup reader saw over one call; None where nothing was
    read. The runner turns each field into its RFC-0004 metric."""

    gpu_memory_peak_mib: float | None = None
    gpu_util_mean_pct: float | None = None
    gpu_util_p95_pct: float | None = None
    gpu_energy_j: float | None = None
    host_memory_peak_kernel: int | None = None
    host_memory_peak_anon: int | None = None
    cpu_seconds: float | None = None


def nvml_available() -> bool:
    try:
        import pynvml  # noqa: PLC0415 (optional extra, INV-ARCH-6)

        pynvml.nvmlInit()
    except Exception:
        return False
    return True


def select_readers(
    *,
    gpu_profile: bool,
    hosted: bool = False,
    nvml: Callable[[], bool] = nvml_available,
    cgroup_root: Path = Path("/sys/fs/cgroup"),
) -> CgroupReader:
    """Null readers only for a profile without a GPU (`ci-cpu`). A GPU profile never falls
    back to them: without NVML it is an `environment` failure before any timed step. Hosted
    execution reads its own container's cgroup (RFC-0006 §Hosted execution)."""
    if not gpu_profile:
        return NullCgroupReader()
    if not nvml():
        raise IProofsError(
            ErrorKind.ENVIRONMENT,
            "the profile needs a GPU but NVML is unavailable on this host (RFC-0011 §Portability)",
        )
    if hosted:
        if not (cgroup_root / "cpu.stat").is_file():
            raise IProofsError(ErrorKind.ENVIRONMENT, f"no cgroup v2 counters at {cgroup_root}")
        return ContainerCgroupReader(cgroup_root)
    raise IProofsError(
        ErrorKind.ENVIRONMENT,
        "GPU and cgroup sampling are not implemented yet (issues #114, #115)",
    )


class SliceCgroupReader:
    """RFC-0011 §Cgroup accounting: counters of a harness-owned parent slice (cgroup v2),
    which outlive the container's own cgroup."""

    def __init__(self, slice_path: Path) -> None:
        self.path = slice_path

    def _int(self, name: str) -> int:
        return int((self.path / name).read_text().strip())

    def _field(self, name: str, key: str) -> int:
        for line in (self.path / name).read_text().splitlines():
            k, _, v = line.partition(" ")
            if k == key:
                return int(v)
        raise IProofsError(ErrorKind.ENVIRONMENT, f"{name} of {self.path.name} has no {key}")

    def memory_peak(self) -> int:
        return self._int("memory.peak")

    def memory_anon(self) -> int:
        return self._field("memory.stat", "anon")

    def cpu_usage_usec(self) -> int:
        return self._field("cpu.stat", "usage_usec")

    def oom_kills(self) -> int:
        return self._field("memory.events", "oom_kill")


class ContainerCgroupReader(SliceCgroupReader):
    """Hosted execution: the counters of the container the harness runs in. The CPU time and
    OOM kills are read as differences over a call and `anon` is sampled during it; the kernel
    peak is the container's since it started, so it is not a step's and is not read."""

    def memory_peak(self) -> int | None:  # type: ignore[override]
        return None


def job_hash(run_id: str) -> str:
    """G-1: the first 12 hex digits of sha256 of the run id."""
    return hashlib.sha256(run_id.encode()).hexdigest()[:12]


class CgroupSlice:
    """G-1 to G-4 for one step: a placeholder scope keeps `iproofs-<hash>-<step>.slice` alive,
    the container is created with `--cgroup-parent` set to it, and the slice's counters are
    read before and after the call. `run` and `popen` are replaced in tests."""

    def __init__(
        self,
        run_id: str,
        step: str,
        *,
        cgroup_root: Path = Path("/sys/fs/cgroup"),
        run: Callable[[list[str]], str] | None = None,
        popen: Callable[[list[str]], object] | None = None,
    ) -> None:
        self.name = f"iproofs-{job_hash(run_id)}-{step}.slice"
        self.unit = f"iproofs-{job_hash(run_id)}-{step}-hold"
        self.root = cgroup_root
        self.run = run or _systemctl
        self.popen = popen or (lambda argv: subprocess.Popen(argv, stdout=subprocess.DEVNULL))
        self.reader: SliceCgroupReader | None = None
        self.baseline_bytes = 0
        self.cpu_baseline_usec = 0
        self.oom_baseline = 0

    def start(self) -> SliceCgroupReader:
        """G-1 and G-3: create the slice, then read its baseline. G-7: no slice or no
        `memory.peak` is an environment failure, before any timed step."""
        self.popen(["systemd-run", "--scope", f"--slice={self.name}", f"--unit={self.unit}",
                    "sleep", "infinity"])  # fmt: skip
        group = self.run(["systemctl", "show", "-p", "ControlGroup", "--value", self.name])
        path = self.root / group.strip().lstrip("/")
        if not group.strip() or not (path / "memory.peak").is_file():
            raise IProofsError(
                ErrorKind.ENVIRONMENT,
                f"cgroup slice {self.name} or its memory.peak is missing (PC-CGROUP, G-7)",
            )
        self.reader = SliceCgroupReader(path)
        self.baseline_bytes = self.reader.memory_peak()
        self.cpu_baseline_usec = self.reader.cpu_usage_usec()
        self.oom_baseline = self.reader.oom_kills()
        return self.reader

    def finish(self) -> tuple[int, float]:
        """G-4 and G-6: (`host_memory_peak_kernel` bytes, `cpu_seconds`) after the call; an OOM
        kill in the slice during the call is a `resource` failure whatever the exit code."""
        assert self.reader is not None
        try:
            peak = self.reader.memory_peak()
            cpu = (self.reader.cpu_usage_usec() - self.cpu_baseline_usec) / 1e6
            oom = self.reader.oom_kills() - self.oom_baseline
        finally:
            self.run(["systemctl", "stop", f"{self.unit}.scope"])
        if oom > 0:
            raise IProofsError(ErrorKind.RESOURCE, f"{oom} OOM kill(s) in {self.name} (G-6)")
        return peak, cpu


def stop_stale_holds(run: Callable[[list[str]], str] | None = None) -> list[str]:
    """Placeholder scopes a crashed runner left behind; stopped before conformance."""
    run = run or _systemctl
    listing = run(["systemctl", "list-units", "--plain", "--no-legend", "iproofs-*-hold.scope"])
    units = [line.split()[0] for line in listing.splitlines() if line.strip()]
    for unit in units:
        run(["systemctl", "stop", unit])
    return units


def _systemctl(argv: list[str]) -> str:
    done = subprocess.run(argv, capture_output=True, text=True, check=False)
    return done.stdout


# ---------------------------------------------------------------- GPU sampler (RFC-0011)

GAP_NS = 150_000_000  # S-5: a gap is an interval between samples above 150 ms
DEGRADED_FRACTION = 0.05  # S-5: degraded when gaps cover more than 5 % of the call


class GpuBackend(Protocol):
    """What the sampler reads from the bound GPU (NVML on a host, a fake in tests)."""

    def memory_used_mib(self) -> float: ...
    def util_pct(self) -> int: ...
    def energy_mj(self) -> int | None: ...  # None where the device does not support it (S-6)
    def compute_processes(self) -> int: ...


class NvmlBackend:
    """`nvidia-ml-py` (the `[gpu]` extra), imported lazily (INV-ARCH-6), bound to one GPU."""

    def __init__(self, index: int) -> None:
        import pynvml  # noqa: PLC0415

        pynvml.nvmlInit()
        self.nvml = pynvml
        self.handle = pynvml.nvmlDeviceGetHandleByIndex(index)

    def memory_used_mib(self) -> float:
        return float(self.nvml.nvmlDeviceGetMemoryInfo(self.handle).used) / (1024 * 1024)

    def util_pct(self) -> int:
        return int(self.nvml.nvmlDeviceGetUtilizationRates(self.handle).gpu)

    def energy_mj(self) -> int | None:
        try:
            return int(self.nvml.nvmlDeviceGetTotalEnergyConsumption(self.handle))
        except self.nvml.NVMLError_NotSupported:
            return None

    def compute_processes(self) -> int:
        return len(self.nvml.nvmlDeviceGetComputeRunningProcesses(self.handle))


@dataclass(frozen=True, slots=True)
class GpuSample:
    mono_ns: int
    memory_used_mib: float
    util_gpu_pct: int
    energy_mj: int | None = None


@dataclass(frozen=True, slots=True)
class SamplerSummary:
    """RFC-0011 §GPU sampler; GPU fields are None when the call has no GPU (S-8)."""

    samples: int
    target_hz: float
    achieved_hz: float
    gaps_over_150ms: int
    gap_fraction: float
    max_gap_ms: float
    degraded: bool
    memory_peak_mib: float | None
    memory_baseline_mib: float | None
    util_mean_pct: float | None
    util_p95_pct: float | None
    energy_j: float | None
    anon_peak_bytes: int | None


def summarize(
    samples: Sequence[GpuSample],
    start_ns: int,
    end_ns: int,
    *,
    target_hz: float,
    baseline_mib: float | None,
    energy: tuple[int | None, int | None] = (None, None),
    anon: Sequence[int] = (),
) -> SamplerSummary:
    """S-1 window, S-4 peak, baseline and time-weighted mean, p95 by nearest rank, S-5 gaps."""
    inside = sorted(
        (s for s in samples if start_ns <= s.mono_ns <= end_ns), key=lambda s: s.mono_ns
    )
    duration = max(end_ns - start_ns, 1)
    stamps = [start_ns, *(s.mono_ns for s in inside), end_ns]
    gaps = [b - a for a, b in itertools.pairwise(stamps) if b - a > GAP_NS]
    fraction = sum(gaps) / duration
    peak = max((s.memory_used_mib for s in inside), default=None)
    utils = [s.util_gpu_pct for s in inside]
    mean = p95 = None
    if inside:
        weights = [b - a for a, b in itertools.pairwise(stamps[1:])]  # each sample to the next
        mean = sum(u * w for u, w in zip(utils, weights, strict=True)) / max(sum(weights), 1)
        ranked = sorted(utils)
        p95 = float(ranked[math.ceil(0.95 * len(ranked)) - 1])
    e0, e1 = energy
    return SamplerSummary(
        samples=len(inside),
        target_hz=target_hz,
        achieved_hz=len(inside) / (duration / 1e9),
        gaps_over_150ms=len(gaps),
        gap_fraction=fraction,
        max_gap_ms=max(gaps, default=0) / 1e6,
        degraded=fraction > DEGRADED_FRACTION,
        memory_peak_mib=peak,
        memory_baseline_mib=baseline_mib,
        util_mean_pct=mean,
        util_p95_pct=p95,
        energy_j=(e1 - e0) / 1000 if e0 is not None and e1 is not None else None,
        anon_peak_bytes=max(anon, default=None),
    )


class Sampler:
    """S-1 to S-3: one thread per call on absolute deadlines `t0 + i * period`; a missed
    deadline is skipped, not caught up, so a stall shows as a gap (S-2). The cgroup `anon`
    is read every second sample (10 Hz at 20 Hz)."""

    def __init__(
        self,
        gpu_index: int | None,
        cgroup: CgroupReader,
        target_hz: float = 20.0,
        *,
        backend: GpuBackend | None = None,
        clock: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self.gpu = backend if backend is not None or gpu_index is None else NvmlBackend(gpu_index)
        self.cgroup = cgroup
        self.target_hz = target_hz
        self.clock = clock
        self.samples: list[GpuSample] = []
        self.anon: list[int] = []
        self.lateness_ns: list[int] = []  # sample time minus its deadline (ST-JITTER)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._baseline: float | None = None
        self._energy_start: int | None = None

    def start(self) -> None:
        if self.gpu is not None:
            self._baseline = self.gpu.memory_used_mib()
            self._energy_start = self.gpu.energy_mj()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        period = int(1e9 / self.target_hz)
        t0, i = self.clock(), 0
        while not self._stop.is_set():
            now = self.clock()
            deadline = t0 + i * period
            if now < deadline:
                self._stop.wait((deadline - now) / 1e9)
                continue
            self.lateness_ns.append(now - deadline)
            i = (now - t0) // period + 1  # S-2: skip missed deadlines
            if self.gpu is not None:
                self.samples.append(GpuSample(now, self.gpu.memory_used_mib(), self.gpu.util_pct()))
            if i % 2 == 0 and (anon := self.cgroup.memory_anon()) is not None:
                self.anon.append(anon)

    def stop(self, start_ns: int, end_ns: int) -> SamplerSummary:
        """The summary over the call window [start_ns, end_ns] (S-1)."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        end_energy = self.gpu.energy_mj() if self.gpu is not None else None
        return summarize(
            self.samples, start_ns, end_ns, target_hz=self.target_hz,
            baseline_mib=self._baseline, energy=(self._energy_start, end_energy), anon=self.anon,
        )  # fmt: skip

    def write_trace(self, path: Path) -> None:
        """1 Hz trace, the maximum per second, as CSV (RFC-0011)."""
        if not self.samples:
            return
        t0 = self.samples[0].mono_ns
        rows: dict[int, tuple[float, int]] = {}
        for s in self.samples:
            sec = (s.mono_ns - t0) // 1_000_000_000
            mem, util = rows.get(sec, (0.0, 0))
            rows[sec] = (max(mem, s.memory_used_mib), max(util, s.util_gpu_pct))
        lines = ["second,memory_used_mib_max,util_gpu_pct_max\n"]
        lines += [f"{sec},{mem:.1f},{util}\n" for sec, (mem, util) in sorted(rows.items())]
        path.write_text("".join(lines))


# ---------------------------------------------------------------- self-test checks (RFC-0011)

MIB = 1024 * 1024


@dataclass(frozen=True, slots=True)
class SelfTestCheck:
    name: str  # ST-*
    passed: bool
    detail: str


def st_clock(reads: Sequence[int]) -> SelfTestCheck:
    """100,000 consecutive monotonic reads: never decreasing, median step at most 1 us."""
    steps = [b - a for a, b in itertools.pairwise(reads)]
    median = sorted(steps)[len(steps) // 2] if steps else 0
    ok = bool(steps) and min(steps) >= 0 and median <= 1_000
    return SelfTestCheck(
        "ST-CLOCK",
        ok,
        f"{len(reads)} reads, min step {min(steps, default=0)} ns, median {median} ns",
    )


def st_sampler(summary: SamplerSummary) -> SelfTestCheck:
    """5 s at 20 Hz on the bound GPU: at least 10 Hz achieved, no gap above 150 ms."""
    ok = summary.achieved_hz >= 10 and summary.gaps_over_150ms == 0
    return SelfTestCheck(
        "ST-SAMPLER",
        ok,
        f"{summary.achieved_hz:.1f} Hz, {summary.gaps_over_150ms} gaps over 150 ms",
    )


def st_jitter(lateness_ns: Sequence[int]) -> SelfTestCheck:
    """The same run: p99 lateness at most 10 ms."""
    ranked = sorted(lateness_ns)
    p99 = ranked[math.ceil(0.99 * len(ranked)) - 1] if ranked else None
    ok = p99 is not None and p99 <= 10_000_000
    return SelfTestCheck("ST-JITTER", ok, f"p99 lateness {None if p99 is None else p99 / 1e6} ms")


def st_cgroup(kernel_peak: int, anon_peak: int | None, cpu_seconds: float) -> SelfTestCheck:
    """A probe touching 256 MiB under a harness slice: both peaks at least 256 MiB, CPU up."""
    ok = kernel_peak >= 256 * MIB and (anon_peak or 0) >= 256 * MIB and cpu_seconds > 0
    return SelfTestCheck(
        "ST-CGROUP",
        ok,
        f"memory.peak {kernel_peak} B, anon peak {anon_peak} B, cpu {cpu_seconds} s",
    )


def st_watch(release_ns: Sequence[int], mechanism: str) -> SelfTestCheck:
    """3 renames 200 ms apart: 3 releases, steps 200 ms +- 20 ms, seen by inotify."""
    steps = [b - a for a, b in itertools.pairwise(sorted(release_ns))]
    ok = (
        len(release_ns) == 3
        and mechanism == "inotify"
        and all(abs(d - 200_000_000) <= 20_000_000 for d in steps)
    )
    return SelfTestCheck(
        "ST-WATCH",
        ok,
        f"{len(release_ns)} releases by {mechanism}, steps {[d / 1e6 for d in steps]} ms",
    )


def st_nvml(backend: GpuBackend) -> SelfTestCheck:
    """NVML init and the bound GPU's handle (done by the caller), then the busy check."""
    busy = backend.compute_processes()
    energy = backend.energy_mj() is not None
    return SelfTestCheck(
        "ST-NVML", busy == 0, f"{busy} foreign process(es); energy supported: {energy}"
    )


def st_oom(oom_kills: int) -> SelfTestCheck:
    """A probe over a 64 MiB limit: the slice's `oom_kill` delta is seen."""
    return SelfTestCheck("ST-OOM", oom_kills > 0, f"oom_kill delta {oom_kills}")


def check_gpu_free(backend: GpuBackend) -> None:
    """S-7 and RFC-0006 PC-GPU-BUSY: no foreign compute process on the bound GPU before
    `info` and before each GPU step; otherwise the job fails with `environment`."""
    if (n := backend.compute_processes()) > 0:
        raise IProofsError(
            ErrorKind.ENVIRONMENT, f"{n} compute process(es) already on the bound GPU (PC-GPU-BUSY)"
        )


# ---------------------------------------------------------------- bounded output capture

LOG_HEAD_BYTES = 256 * 1024  # RFC-0009 §Storage: per log file, first 256 KiB ...
LOG_TAIL_BYTES = 768 * 1024  # ... and last 768 KiB
CHUNK = 64 * 1024


def omitted_marker(k: int) -> bytes:
    return f"[iproofs: {k} bytes omitted, full digest in digests.txt]\n".encode()


class Capture:
    """One output stream kept as its first and last bytes, with the sha256 and length of all
    of it, so a runaway adapter cannot fill memory or disk (docs/spec/06-security.md)."""

    def __init__(self, head: int = LOG_HEAD_BYTES, tail: int = LOG_TAIL_BYTES) -> None:
        self.head_limit, self.tail_limit = head, tail
        self.head, self.tail = bytearray(), bytearray()
        self.total = 0
        self._sha = hashlib.sha256()
        self._lock = threading.Lock()

    def feed(self, chunk: bytes) -> None:
        with self._lock:
            self.total += len(chunk)
            self._sha.update(chunk)
            room = self.head_limit - len(self.head)
            if room > 0:
                self.head += chunk[:room]
                chunk = chunk[room:]
            self.tail += chunk
            if len(self.tail) > self.tail_limit:
                del self.tail[: len(self.tail) - self.tail_limit]

    @property
    def digest(self) -> str:
        return "sha256:" + self._sha.hexdigest()

    @property
    def elided(self) -> int:
        return self.total - len(self.head) - len(self.tail)

    def kept(self) -> bytes:
        middle = omitted_marker(self.elided) if self.elided else b""
        return bytes(self.head) + middle + bytes(self.tail)

    def text(self) -> str:
        return self.kept().decode("utf-8", errors="replace")


def _pump(stream: IO[bytes], sinks: Sequence[Capture]) -> None:
    while chunk := stream.read1(CHUNK) if hasattr(stream, "read1") else stream.read(CHUNK):
        for sink in sinks:
            sink.feed(chunk)


def drain(
    proc: "subprocess.Popen[bytes]", out: Sequence[Capture], err: Sequence[Capture]
) -> list[threading.Thread]:
    """Read both pipes on threads into bounded captures; join the threads after the wait."""
    threads = [
        threading.Thread(target=_pump, args=(pipe, sinks), daemon=True)
        for pipe, sinks in ((proc.stdout, out), (proc.stderr, err))
        if pipe is not None
    ]
    for t in threads:
        t.start()
    return threads


def cap_text(data: bytes, head: int, tail: int) -> tuple[bytes, int]:
    """The first `head` and last `tail` bytes joined by the omitted marker, and the count."""
    elided = len(data) - head - tail
    if elided <= 0:
        return data, 0
    return data[:head] + omitted_marker(elided) + data[len(data) - tail :], elided


def timed_call(
    argv_create: Sequence[str],
    timeout_s: float,
    on_started: Callable[[str], None] = lambda cid: None,
    clock: Callable[[], int] = time.monotonic_ns,
    sinks: Sequence[Capture] = (),
) -> CallTiming:
    """Time one adapter call: `docker create` untimed, `docker start --attach` timed (T-1).
    `sinks` (stdout, stderr) also receive the output: the run's per-file log captures."""
    created = subprocess.run(list(argv_create), capture_output=True, text=True, check=False)
    if created.returncode != 0:
        raise IProofsError(
            ErrorKind.ENVIRONMENT,
            f"docker create failed: {created.stderr.strip()}",
            exit_code=created.returncode,
        )
    cid = created.stdout.strip()
    out, err = Capture(), Capture()
    start = clock()
    proc = subprocess.Popen(
        ["docker", "start", "--attach", cid], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    threads = drain(proc, [out, *sinks[:1]], [err, *sinks[1:2]])
    try:
        on_started(cid)  # samplers attach to the container's cgroup here (RFC-0011)
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired as e:
        subprocess.run(
            ["docker", "kill", "--signal", "KILL", cid], capture_output=True, check=False
        )
        try:
            proc.wait(timeout=KILL_WAIT_S)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        for t in threads:
            t.join()
        _remove(cid)
        raise IProofsError(
            ErrorKind.TIMEOUT,
            f"step exceeded {timeout_s} s",
            last_lines=tuple(err.text().splitlines()[-50:]),
        ) from e
    end = clock()
    for t in threads:
        t.join()
    stdout, stderr = out.text(), err.text()
    oom = proc.returncode != 0 and _oom_killed(cid)
    _remove(cid)
    if oom:
        raise IProofsError(
            ErrorKind.RESOURCE,
            "container killed: out of memory",
            exit_code=proc.returncode,
            last_lines=tuple(stderr.splitlines()[-50:]),
        )
    return CallTiming(start, end, proc.returncode, cid, stdout, stderr)


def _remove(cid: str) -> None:
    subprocess.run(["docker", "rm", "-f", cid], capture_output=True, check=False)


def _oom_killed(cid: str) -> bool:
    inspect = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.OOMKilled}}", cid],
        capture_output=True,
        text=True,
        check=False,
    )
    return inspect.stdout.strip() == "true"


@dataclass(slots=True)
class EventLog:
    """Lifecycle events stored in run.json `events` as {event, mono_ns} (RFC-0011 C-2)."""

    clock: Callable[[], int] = time.monotonic_ns
    events: list[dict[str, object]] = field(default_factory=list)

    def record(self, name: str, mono_ns: int | None = None) -> int:
        stamp = self.clock() if mono_ns is None else mono_ns
        self.events.append({"event": name, "mono_ns": stamp})
        return stamp

    def first(self) -> dict[str, int]:
        """Event name -> first timestamp, the input of `iproofs.derive.scope_seconds`."""
        out: dict[str, int] = {}
        for e in self.events:
            out.setdefault(str(e["event"]), int(str(e["mono_ns"])))
        return out

    def releases(self) -> list[int]:
        return [int(str(e["mono_ns"])) for e in self.events if e["event"] == "proof.released"]


def pin_harness_cpu(job_cpus: Iterable[int]) -> int | None:
    """C-3: pin the harness to one logical CPU outside the job's cpusets (Linux only)."""
    if not sys.platform.startswith("linux"):
        return None
    taken = set(job_cpus)
    free = sorted(set(os.sched_getaffinity(0)) - taken)
    if not free:
        raise IProofsError(ErrorKind.ENVIRONMENT, "no CPU left for the harness outside the job")
    os.sched_setaffinity(0, {free[-1]})
    return free[-1]


# ---------------------------------------------------------------- proof release watcher

IN_CREATE = 0x00000100
IN_MOVED_TO = 0x00000080
IN_ONLYDIR = 0x01000000
IN_ISDIR = 0x40000000
_IN_NONBLOCK = 0o4000
_IN_CLOEXEC = 0o2000000
_EVENT_HEADER = struct.Struct("iIII")  # wd, mask, cookie, len


@dataclass(frozen=True, slots=True)
class Release:
    proof_id: str
    mono_ns: int


class ReleaseWatcher:
    """Timestamps each proof directory as it appears under /io/proofs (RFC-0011 W-1 to W-5).

    Adapters rename `.tmp-<id>` to `<id>`; on Linux the rename is read from inotify in a
    thread, elsewhere `os.scandir` polls every `poll_interval_s`.
    """

    def __init__(
        self,
        proofs_dir: Path,
        poll_interval_s: float = 0.010,
        *,
        incremental_proofs: bool = True,
        force_poll: bool = False,
        clock: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self.dir = proofs_dir
        self.interval = poll_interval_s
        self.incremental = incremental_proofs
        self.clock = clock
        self._mechanism: Literal["inotify", "poll"] = "poll"
        self._libc = None if force_poll or not sys.platform.startswith("linux") else _libc()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._releases: dict[str, tuple[int, int]] = {}  # proof id -> (mono_ns, batch)
        self._sizes: dict[str, dict[str, int]] = {}
        self.nonatomic: list[str] = []  # W-3: logged as release.nonatomic

    @property
    def mechanism(self) -> Literal["inotify", "poll"]:
        return self._mechanism

    @property
    def observable(self) -> bool:
        """W-4: false for non-incremental systems or when every release came in one batch."""
        batches = {batch for _, batch in self._releases.values()}
        return self.incremental and len(batches) > 1

    def start(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        fd = self._inotify() if self._libc is not None else None
        self._mechanism = "inotify" if fd is not None else "poll"
        target = self._run_inotify if fd is not None else self._run_poll
        self._thread = threading.Thread(
            target=target, args=(fd,) if fd is not None else (), name="release-watcher", daemon=True
        )
        self._thread.start()

    def stop(self, call_end_ns: int | None = None) -> list[Release]:
        """Stop after the prove call; W-5: a release after `call_end_ns` is an adapter error."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        self._scan(batch=-1)  # anything the reader had not yet seen
        releases = sorted(
            (Release(pid, ns) for pid, (ns, _) in self._releases.items()),
            key=lambda r: (r.mono_ns, r.proof_id),
        )
        # A release is observed up to one poll interval (or one inotify read) after it happens,
        # so only observations clearly after the call ended count as W-5 violations.
        lag_ns = int(max(2 * self.interval, 0.05) * 1e9)
        late = [
            r.proof_id
            for r in releases
            if call_end_ns is not None and r.mono_ns > call_end_ns + lag_ns
        ]
        if late:
            raise IProofsError(
                ErrorKind.ADAPTER, f"W-5: proofs released after prove exited: {late}", step="prove"
            )
        return releases

    def tmp_left(self) -> list[str]:
        """`.tmp-*` directories still present: logged as proof.tmp_left."""
        return sorted(p.name for p in self.dir.iterdir() if p.name.startswith(".tmp-"))

    def check_unchanged(self) -> None:
        """W-3: parts that change size after release fail the job with kind adapter."""
        for pid, sizes in sorted(self._sizes.items()):
            now = _part_sizes(self.dir / pid)
            if now != sizes:
                raise IProofsError(
                    ErrorKind.ADAPTER, f"W-3: proof {pid} changed after release", step="prove"
                )

    def _release(self, name: str, batch: int, atomic: bool) -> None:
        if name.startswith(".tmp-") or name in self._releases:
            return
        self._releases[name] = (self.clock(), batch)
        self._sizes[name] = _part_sizes(self.dir / name)
        if not atomic:
            self.nonatomic.append(name)

    def _scan(self, batch: int) -> None:
        with os.scandir(self.dir) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    self._release(entry.name, batch, atomic=True)

    def _run_poll(self) -> None:
        batch = 0
        while not self._stop.is_set():
            self._scan(batch)
            batch += 1
            self._stop.wait(self.interval)

    def _inotify(self) -> int | None:
        assert self._libc is not None
        fd = int(self._libc.inotify_init1(_IN_NONBLOCK | _IN_CLOEXEC))
        if fd < 0:
            return None
        wd = self._libc.inotify_add_watch(
            fd, os.fsencode(self.dir), IN_MOVED_TO | IN_CREATE | IN_ONLYDIR
        )
        if wd < 0:
            os.close(fd)
            return None
        return fd

    def _run_inotify(self, fd: int) -> None:
        batch = 0
        try:
            while not self._stop.is_set():
                ready, _, _ = select.select([fd], [], [], self.interval)
                if not ready:
                    continue
                data = os.read(fd, 1 << 16)
                offset = 0
                while offset < len(data):
                    _, mask, _, length = _EVENT_HEADER.unpack_from(data, offset)
                    name_bytes = data[
                        offset + _EVENT_HEADER.size : offset + _EVENT_HEADER.size + length
                    ]
                    offset += _EVENT_HEADER.size + length
                    name = name_bytes.rstrip(b"\0").decode(errors="replace")
                    if mask & IN_MOVED_TO:
                        self._release(name, batch, atomic=True)
                    elif mask & IN_CREATE and mask & IN_ISDIR:
                        self._release(name, batch, atomic=False)  # created without a .tmp- stage
                batch += 1
        finally:
            os.close(fd)


def _part_sizes(proof: Path) -> dict[str, int]:
    try:
        return {p.name: p.stat().st_size for p in proof.iterdir() if p.is_file()}
    except FileNotFoundError:
        return {}


def _libc() -> ctypes.CDLL | None:
    try:
        libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    except OSError:
        return None
    return libc if hasattr(libc, "inotify_init1") else None


# ---------------------------------------------------------------- proof sizes (RFC-0011 Z-1 to Z-3)


@dataclass(frozen=True, slots=True)
class ProofSize:
    bytes: int
    digest: str  # the RFC-0012 proof digest, computed in the same pass
    parts: tuple[tuple[str, int, str], ...]  # (name, bytes, sha256 digest) per part


def _regular_inside(path: Path, io_root: Path, what: str) -> None:
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise IProofsError(ErrorKind.ADAPTER, f"Z-1: {what} is not a regular file", step="prove")
    if not path.resolve().is_relative_to(io_root.resolve()):
        raise IProofsError(ErrorKind.ADAPTER, f"Z-1: {what} resolves outside /io", step="prove")


def proof_size(proof_dir: Path, io_root: Path) -> ProofSize:
    """Bytes as stored of every part of one proof, with per-part sha256 and the proof digest."""
    parts = []
    lines = []
    for part in sorted(proof_dir.iterdir(), key=lambda p: p.name.encode()):
        _regular_inside(part, io_root, f"/io/proofs/{proof_dir.name}/{part.name}")
        h = hashlib.sha256()
        size = 0
        with part.open("rb") as f:
            while chunk := f.read(1 << 20):
                h.update(chunk)
                size += len(chunk)
        parts.append((part.name, size, "sha256:" + h.hexdigest()))
        lines.append(f"{part.name}\t{h.hexdigest()}\n")
    digest = "sha256:" + hashlib.sha256("".join(lines).encode()).hexdigest()
    return ProofSize(sum(size for _, size, _ in parts), digest, tuple(parts))


def proof_bytes(proof_dir: Path, io_root: Path) -> int:
    return proof_size(proof_dir, io_root).bytes


def files_bytes(paths: Sequence[str], io_root: Path) -> int:
    """Total bytes of adapter files named by container path (verifier or prover files, Z-2)."""
    total = 0
    for container_path in paths:
        rel = container_path.removeprefix("/io/")
        if rel == container_path or ".." in Path(rel).parts:
            raise IProofsError(
                ErrorKind.ADAPTER, f"Z-1: {container_path} is outside /io", step="commit"
            )
        host = io_root / rel
        _regular_inside(host, io_root, container_path)
        total += host.stat().st_size
    return total
