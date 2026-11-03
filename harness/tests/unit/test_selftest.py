"""RFC-0011 §Calibration self-test: each ST check on good and bad input, with fakes."""

import json
from pathlib import Path

import pytest

from iproofs import cli, selftest
from iproofs.adapter import InProcessRunner
from iproofs.measure import (
    SamplerSummary,
    st_cgroup,
    st_clock,
    st_jitter,
    st_nvml,
    st_oom,
    st_sampler,
    st_watch,
)
from iproofs.runner import JobSpec, Runner
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
MIB = 1024 * 1024
MS = 1_000_000


def summary(hz: float, gaps: int) -> SamplerSummary:
    return SamplerSummary(100, 20.0, hz, gaps, 0.0, 0.0, False, 1.0, 1.0, 1.0, 1.0, None, None)


class FakeGpu:
    def __init__(self, processes: int) -> None:
        self.processes = processes

    def memory_used_mib(self) -> float:
        return 1.0

    def util_pct(self) -> int:
        return 0

    def energy_mj(self) -> int | None:
        return None

    def compute_processes(self) -> int:
        return self.processes


@pytest.mark.parametrize(
    ("check", "good", "bad"),
    [
        (st_clock, [list(range(0, 100_000, 10))], [[0, 10, 5, 20]]),  # a decreasing clock
        (st_clock, [list(range(0, 100_000, 10))], [list(range(0, 10_000_000, 2_000))]),  # 2 us
        (st_sampler, [summary(19.8, 0)], [summary(8.0, 0)]),
        (st_sampler, [summary(19.8, 0)], [summary(19.8, 1)]),
        (st_jitter, [[1 * MS] * 99 + [9 * MS]], [[1 * MS] * 98 + [11 * MS] * 2]),
        (st_cgroup, [300 * MIB, 270 * MIB, 0.4], [300 * MIB, 100 * MIB, 0.4]),
        (st_cgroup, [300 * MIB, 270 * MIB, 0.4], [300 * MIB, 270 * MIB, 0.0]),
        (st_watch, [[0, 200 * MS, 405 * MS], "inotify"], [[0, 200 * MS, 405 * MS], "poll"]),
        (st_watch, [[0, 200 * MS, 405 * MS], "inotify"], [[0, 200 * MS, 450 * MS], "inotify"]),
        (st_nvml, [FakeGpu(0)], [FakeGpu(1)]),
        (st_oom, [1], [0]),
    ],
)
def test_each_check(check: object, good: list[object], bad: list[object]) -> None:
    assert callable(check)
    assert check(*good).passed is True
    assert check(*bad).passed is False


def test_missing_prerequisites_fail_and_say_why(tmp_path: Path) -> None:
    checks = selftest.run_selftest(gpu_index=None, probe_image=None, work=tmp_path)
    assert [c.name for c in checks] == list(selftest.CHECKS)
    assert [c.name for c in checks if c.passed] == ["ST-CLOCK"]
    assert all("no " in c.detail or "unavailable" in c.detail for c in checks[1:])


def test_saved_result_goes_into_every_manifest(tmp_path: Path) -> None:
    record = {"passed": True, "checks": [{"name": c, "passed": True} for c in selftest.CHECKS]}
    selftest.save(tmp_path, record)
    assert selftest.saved(tmp_path) == record
    env = {"IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78"}
    registry = SchemaRegistry.from_tree(ROOT / "schema")
    containers = InProcessRunner(ROOT / "systems/fake/entrypoint", registry, env=env)
    runner = Runner(containers, root=ROOT, registry=registry, image="local/x@sha256:" + "0" * 64)
    spec = JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, False, str(tmp_path), "v0.1")
    (run_dir,) = runner.run_many(spec, 1)
    assert json.loads((run_dir / "manifest.json").read_text())["self_test"] == record


def test_a_failed_self_test_is_a_conformance_failure(tmp_path: Path) -> None:
    selftest.save(tmp_path, {"passed": False, "checks": [{"name": "ST-OOM", "passed": False}]})
    env = {"IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78"}
    registry = SchemaRegistry.from_tree(ROOT / "schema")
    containers = InProcessRunner(ROOT / "systems/fake/entrypoint", registry, env=env)
    runner = Runner(containers, root=ROOT, registry=registry, image="local/x@sha256:" + "0" * 64)
    spec = JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, False, str(tmp_path), "v0.1")
    (run_dir,) = runner.run_many(spec, 1)  # a test system: a warning, not a refusal
    warnings = json.loads((run_dir / "run.json").read_text())["warnings"]
    assert "conformance: ST: the host's last self-test failed" in warnings


def test_cli_exits_3_and_names_the_checks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["machine-record", "--selftest", "--results", str(tmp_path)]) == 3
    out = capsys.readouterr()
    assert json.loads(out.out)["self_test"]["passed"] is False
    assert "ST-NVML" in out.err
    assert selftest.saved(tmp_path) is not None
