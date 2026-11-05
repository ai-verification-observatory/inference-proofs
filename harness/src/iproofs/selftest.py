"""RFC-0011 §Calibration self-test: `iproofs machine-record --selftest`.

Runs ST-CLOCK, ST-NVML, ST-SAMPLER and ST-JITTER on the bound GPU, and ST-CGROUP, ST-WATCH and
ST-OOM with the `probe` subcommand of the pinned `systems/fake` image under a harness slice.
A check whose prerequisite is missing (no GPU, no probe image, no systemd) fails and says why;
the self-test is the calibration a real host needs before any number from it is trusted.
"""

import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from iproofs import __version__
from iproofs.adapter import docker_create_argv, give_io_to_adapter
from iproofs.errors import ErrorKind, IProofsError
from iproofs.measure import (
    CgroupReader,
    CgroupSlice,
    ContainerCgroupReader,
    GpuBackend,
    NullCgroupReader,
    NvmlBackend,
    ReleaseWatcher,
    Sampler,
    SelfTestCheck,
    st_cgroup,
    st_cgroup_hosted,
    st_clock,
    st_jitter,
    st_nvml,
    st_oom,
    st_sampler,
    st_watch,
    timed_call,
)

CHECKS = ("ST-CLOCK", "ST-SAMPLER", "ST-JITTER", "ST-CGROUP", "ST-WATCH", "ST-NVML", "ST-OOM")
SAVED = ".selftest.json"  # under the results root; the runner copies it into manifests


def run_selftest(
    *,
    gpu_index: int | None,
    probe_image: str | None,
    work: Path,
    backend: Callable[[int], GpuBackend] = NvmlBackend,
    sampler_s: float = 5.0,
    hosted_probe: Path | None = None,
    cgroup_root: Path = Path("/sys/fs/cgroup"),
) -> list[SelfTestCheck]:
    """`hosted_probe` (the fake system's entrypoint) selects hosted execution (RFC-0006): the
    probe runs as a process in this container, and ST-OOM is not run, since the container
    can set no memory limit to exceed."""
    reads = [time.monotonic_ns() for _ in range(100_000)]
    checks = [st_clock(reads)]
    gpu: GpuBackend | None = None
    try:
        if gpu_index is None:
            raise IProofsError(ErrorKind.ENVIRONMENT, "no GPU bound (--gpu)")
        gpu = backend(gpu_index)
        checks.append(st_nvml(gpu))
    except Exception as e:
        checks.append(SelfTestCheck("ST-NVML", False, f"NVML unavailable: {e}"))
    if gpu is not None:
        sampler = Sampler(gpu_index, NullCgroupReader(), backend=gpu)
        start = time.monotonic_ns()
        sampler.start()
        time.sleep(sampler_s)
        end = time.monotonic_ns()
        checks += [st_sampler(sampler.stop(start, end)), st_jitter(sampler.lateness_ns)]
    else:
        checks += [SelfTestCheck(c, False, "no GPU sampler") for c in ("ST-SAMPLER", "ST-JITTER")]
    if hosted_probe is not None:
        reader = ContainerCgroupReader(cgroup_root)
        checks.append(_hosted_cgroup(hosted_probe, work / "st-cgroup", reader))
        checks.append(_hosted_watch(hosted_probe, work / "st-watch"))
        return sorted(checks, key=lambda c: CHECKS.index(c.name))
    for name, check in (("ST-CGROUP", cgroup), ("ST-WATCH", _watch), ("ST-OOM", _oom)):
        try:
            if probe_image is None:
                raise IProofsError(ErrorKind.ENVIRONMENT, "no probe image (--probe-image)")
            checks.append(check(probe_image, work / name.lower()))
        except IProofsError as e:
            checks.append(SelfTestCheck(name, False, e.message))
    return sorted(checks, key=lambda c: CHECKS.index(c.name))


def probe(image: str, io: Path, mode: str, *, memory: str | None = None,
          cgroup_parent: str | None = None, **fields: object) -> int:  # fmt: skip
    """Run the fake image's `probe` subcommand; `fields` go into its job.json."""
    io.mkdir(parents=True, exist_ok=True)
    (io / "job.json").write_text(json.dumps({"probe": mode, **fields}))
    give_io_to_adapter(io)
    argv = docker_create_argv(image, "probe", io, models_dir=None, gpu=None, cpuset="0",
                              mems="0", memory=memory, cgroup_parent=cgroup_parent)  # fmt: skip
    return timed_call(argv, 60.0).exit_code


def hosted_probe_call(entrypoint: Path, io: Path, mode: str, **fields: object) -> int:
    """The fake entrypoint's `probe` as a process of this container (hosted execution)."""
    io.mkdir(parents=True, exist_ok=True)
    (io / "job.json").write_text(json.dumps({"probe": mode, **fields}))
    argv = [sys.executable, str(entrypoint), "probe", "/io/job.json", "/io/out.json"]
    env = {**os.environ, "IPROOFS_IO": str(io.resolve())}
    return subprocess.run(argv, env=env, check=False, timeout=60).returncode


def _hosted_cgroup(entrypoint: Path, io: Path, reader: CgroupReader) -> SelfTestCheck:
    baseline, cpu0 = reader.memory_anon(), reader.cpu_usage_usec()
    sampler = Sampler(None, reader, target_hz=20.0)
    start = time.monotonic_ns()
    sampler.start()
    try:
        hosted_probe_call(entrypoint, io, "alloc")
    finally:
        summary = sampler.stop(start, time.monotonic_ns())
    cpu1 = reader.cpu_usage_usec()
    rise = (
        None
        if summary.anon_peak_bytes is None or baseline is None
        else (summary.anon_peak_bytes - baseline)
    )
    cpu = None if cpu0 is None or cpu1 is None else (cpu1 - cpu0) / 1e6
    return st_cgroup_hosted(rise, cpu)


def _hosted_watch(entrypoint: Path, io: Path) -> SelfTestCheck:
    watcher = ReleaseWatcher(io / "proofs")
    (io / "proofs").mkdir(parents=True, exist_ok=True)
    watcher.start()
    hosted_probe_call(entrypoint, io, "watch")
    releases = watcher.stop(call_end_ns=None)
    return st_watch([r.mono_ns for r in releases], watcher.mechanism)


def run_id() -> str:
    return f"selftest-{time.time_ns()}"


def cgroup(image: str, io: Path) -> SelfTestCheck:
    slice_ = CgroupSlice(run_id(), "probe-alloc")
    reader = slice_.start()
    sampler = Sampler(None, reader, target_hz=20.0)
    start = time.monotonic_ns()
    sampler.start()
    try:
        probe(image, io, "alloc", cgroup_parent=slice_.name)
    finally:
        summary = sampler.stop(start, time.monotonic_ns())
    peak, cpu = slice_.finish()
    return st_cgroup(peak, summary.anon_peak_bytes, cpu)


def _watch(image: str, io: Path) -> SelfTestCheck:
    watcher = ReleaseWatcher(io / "proofs")
    (io / "proofs").mkdir(parents=True, exist_ok=True)
    watcher.start()
    probe(image, io, "watch")
    releases = watcher.stop(call_end_ns=None)
    return st_watch([r.mono_ns for r in releases], watcher.mechanism)


def _oom(image: str, io: Path) -> SelfTestCheck:
    slice_ = CgroupSlice(run_id(), "probe-oom")
    slice_.start()
    try:
        probe(image, io, "oom", memory="64m", cgroup_parent=slice_.name)
    except IProofsError as e:
        if e.kind is not ErrorKind.RESOURCE:
            raise
    try:
        slice_.finish()
    except IProofsError as e:
        if e.kind is ErrorKind.RESOURCE:
            return st_oom(1)  # G-6 saw the kill
        raise
    return st_oom(0)


def as_record(checks: list[SelfTestCheck]) -> dict[str, object]:
    """manifest/1 `self_test`: {passed, checks[{name, passed}]}."""
    return {
        "passed": all(c.passed for c in checks),
        "checks": [{"name": c.name, "passed": c.passed} for c in checks],
    }


def save(results: Path, record: dict[str, object]) -> Path:
    results.mkdir(parents=True, exist_ok=True)
    path = results / SAVED
    path.write_text(json.dumps({"harness_version": __version__, "self_test": record}, indent=2))
    return path


def saved(results: Path) -> dict[str, object] | None:
    """The host's last self-test, if it was taken by this harness version."""
    path = results / SAVED
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if doc.get("harness_version") != __version__ or not isinstance(doc.get("self_test"), dict):
        return None
    result: dict[str, object] = doc["self_test"]
    return result


def report(checks: list[SelfTestCheck]) -> None:
    for c in checks:
        print(f"{c.name}: {'pass' if c.passed else 'FAIL'} ({c.detail})", file=sys.stderr)
