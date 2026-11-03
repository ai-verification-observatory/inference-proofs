"""GPU-host tests of the NVML sampler (RFC-0011 §Testing Strategy, docs/runbooks/gpu-run.md):
the 60 s rate and gaps, GH-NVML-PEAK and GH-OVERHEAD. Skipped without NVML."""

import os
import resource
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from iproofs.measure import (
    NullCgroupReader,
    NvmlBackend,
    ReleaseWatcher,
    Sampler,
    SamplerSummary,
    st_jitter,
)

from .gpu_host import GPU, needs_nvml

pytestmark = needs_nvml
MIB = 1024 * 1024
ALLOC = "import time, torch; x = torch.empty(40 * 2**30, dtype=torch.uint8, device='cuda'); "
ALLOC += "x.fill_(1); torch.cuda.synchronize(); time.sleep(2)"


def sample(
    seconds: float, during: Callable[[], object] | None = None
) -> tuple[Sampler, SamplerSummary]:
    sampler = Sampler(GPU, NullCgroupReader(), backend=NvmlBackend(GPU))
    start = time.monotonic_ns()
    sampler.start()
    if during is not None:
        during()
    else:
        time.sleep(seconds)
    return sampler, sampler.stop(start, time.monotonic_ns())


def test_sampler_rate_and_gaps_60s() -> None:
    """At least 10 Hz over 60 s, gaps above 150 ms on at most 5 % of the call (S-5)."""
    sampler, summary = sample(60.0)
    assert summary.achieved_hz >= 10.0, summary
    assert summary.gap_fraction <= 0.05, summary
    assert not summary.degraded
    assert st_jitter(sampler.lateness_ns).passed


def test_nvml_peak_known_allocation() -> None:
    """GH-NVML-PEAK: a CUDA probe holds 40 GiB on the bound GPU for 2 s."""
    image = os.environ.get("IPROOFS_CUDA_PROBE_IMAGE")
    if not image:
        pytest.skip("set IPROOFS_CUDA_PROBE_IMAGE to a pinned image with python3 and torch")
    argv = ["docker", "run", "--rm", "--gpus", f"device={GPU}", "--network=none", image,
            "python3", "-c", ALLOC]  # fmt: skip
    _, summary = sample(0, lambda: subprocess.run(argv, check=True, timeout=600))
    assert (summary.memory_peak_mib or 0) >= 40_960, summary


def test_overhead() -> None:
    """GH-OVERHEAD (B-OVH-CPU, B-OVH-JITTER, B-OVH-RSS): the sampler and release watcher of
    one 30-minute call. Run with IPROOFS_GH_OVERHEAD=1."""
    if os.environ.get("IPROOFS_GH_OVERHEAD") != "1":
        pytest.skip("30-minute test: set IPROOFS_GH_OVERHEAD=1")
    seconds = 1800.0
    with tempfile.TemporaryDirectory() as proofs:
        watcher = ReleaseWatcher(Path(proofs))
        watcher.start()
        before = resource.getrusage(resource.RUSAGE_SELF)
        sampler, _ = sample(seconds)
        after = resource.getrusage(resource.RUSAGE_SELF)
        watcher.stop(call_end_ns=None)
    cpu = (after.ru_utime + after.ru_stime) - (before.ru_utime + before.ru_stime)
    assert cpu / seconds <= 0.01, f"harness CPU {cpu} s over {seconds} s"
    ranked = sorted(sampler.lateness_ns)
    assert ranked[int(0.99 * (len(ranked) - 1))] <= 10_000_000  # p99 lateness at most 10 ms
    assert after.ru_maxrss * 1024 <= 256 * MIB  # Linux reports KiB
