"""RFC-0011 §GPU sampler: TC-SAMPLER-GAPS, TC-SAMPLER-P95, TC-SAMPLER-ENERGY-UNSUPPORTED,
TC-FOREIGN-PROC."""

import time
from pathlib import Path

import pytest

from iproofs.errors import ErrorKind, IProofsError
from iproofs.measure import GpuSample, NullCgroupReader, Sampler, check_gpu_free, summarize

MS = 1_000_000


def series(
    duration_ms: int, stalls: int, period_ms: int = 50, stall_ms: int = 400
) -> list[GpuSample]:
    """Samples every period, with `stalls` gaps of stall_ms spread over the call."""
    out, t, done = [], 0, 0
    every = duration_ms // (stalls + 1) if stalls else duration_ms + 1
    while t < duration_ms:
        out.append(GpuSample(t * MS, 1000.0, 50))
        step = stall_ms if stalls and done < stalls and t and t % every < period_ms else period_ms
        done += step == stall_ms
        t += step
    return out


def test_sampler_gaps() -> None:
    """TC-SAMPLER-GAPS: two 400 ms stalls in a 20 s call are counted and stay under 5 %;
    ten make the call's GPU metrics degraded (S-5)."""
    two = summarize(series(20_000, 2), 0, 20_000 * MS, target_hz=20, baseline_mib=900.0)
    assert two.gaps_over_150ms == 2
    assert two.max_gap_ms == 400
    assert two.gap_fraction == pytest.approx(0.04)
    assert two.degraded is False
    ten = summarize(series(20_000, 10), 0, 20_000 * MS, target_hz=20, baseline_mib=900.0)
    assert ten.gaps_over_150ms == 10
    assert ten.degraded is True


def test_sampler_p95_and_mean() -> None:
    """TC-SAMPLER-P95: utilisation 1..100, evenly spaced: p95 by nearest rank is 95."""
    samples = [GpuSample(i * 50 * MS, float(i), i) for i in range(1, 101)]
    s = summarize(samples, 50 * MS, 5050 * MS, target_hz=20, baseline_mib=0.0)
    assert s.util_p95_pct == 95
    assert s.util_mean_pct == pytest.approx(50.5)  # equal weights: the plain mean
    assert (s.memory_peak_mib, s.memory_baseline_mib) == (100.0, 0.0)  # baseline not subtracted


def test_samples_outside_the_call_are_discarded() -> None:
    samples = [GpuSample(t * MS, 9999.0 if t < 0 else 10.0, 1) for t in (-50, 0, 50, 100)]
    s = summarize(samples, 0, 100 * MS, target_hz=20, baseline_mib=None)
    assert (s.samples, s.memory_peak_mib) == (3, 10.0)  # S-1


class FakeGpu:
    def __init__(self, energy: list[int | None], processes: int = 0) -> None:
        self.energy = energy
        self.processes = processes

    def memory_used_mib(self) -> float:
        return 512.0

    def util_pct(self) -> int:
        return 30

    def energy_mj(self) -> int | None:
        return self.energy.pop(0)

    def compute_processes(self) -> int:
        return self.processes


def run_sampler(gpu: FakeGpu) -> tuple[Sampler, int, int]:
    sampler = Sampler(0, NullCgroupReader(), target_hz=200.0, backend=gpu)
    start = time.monotonic_ns()
    sampler.start()
    time.sleep(0.05)
    end = time.monotonic_ns()
    return sampler, start, end


def test_sampler_energy_unsupported() -> None:
    """TC-SAMPLER-ENERGY-UNSUPPORTED: energy is None, which the runner records as null with
    `not_applicable` (S-6)."""
    sampler, start, end = run_sampler(FakeGpu([None, None]))
    summary = sampler.stop(start, end)
    assert summary.energy_j is None
    assert summary.samples > 0
    assert summary.anon_peak_bytes is None  # a null cgroup reader reads nothing


def test_sampler_energy_and_trace(tmp_path: Path) -> None:
    sampler, start, end = run_sampler(FakeGpu([1_000_000, 1_250_000]))
    assert sampler.stop(start, end).energy_j == 250.0  # mJ difference, in J
    sampler.write_trace(tmp_path / "gpu.csv")
    lines = (tmp_path / "gpu.csv").read_text().splitlines()
    assert lines[0] == "second,memory_used_mib_max,util_gpu_pct_max"
    assert lines[1] == "0,512.0,30"


def test_foreign_process() -> None:
    """TC-FOREIGN-PROC: one process on the bound GPU is an environment failure."""
    check_gpu_free(FakeGpu([], processes=0))
    with pytest.raises(IProofsError) as e:
        check_gpu_free(FakeGpu([], processes=1))
    assert e.value.kind is ErrorKind.ENVIRONMENT
    assert "PC-GPU-BUSY" in e.value.message
