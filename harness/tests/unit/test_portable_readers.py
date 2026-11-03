"""RFC-0011 §Portability: null readers on hosts without NVML or cgroup v2, never on a GPU
profile."""

import json
from pathlib import Path

import pytest

from iproofs.adapter import InProcessRunner
from iproofs.errors import ErrorKind, IProofsError
from iproofs.measure import CgroupReader, NullCgroupReader, ReleaseWatcher, select_readers
from iproofs.runner import JobSpec, Runner
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
ENV = {
    "IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78",
    "IPROOFS_FAKE_DELAY_S": "0",
}
RESOURCES = [
    f"{step}_{m}"
    for step in ("commit", "prove")
    for m in (
        "gpu_memory_peak",
        "gpu_util_mean",
        "gpu_util_p95",
        "gpu_energy",
        "host_memory_peak_kernel",
        "host_memory_peak_anon",
        "cpu_seconds",
    )
] + ["verify_host_memory_peak_anon"]


def test_null_reader_quantities_labelled(tmp_path: Path) -> None:
    reader: CgroupReader = select_readers(gpu_profile=False)
    assert isinstance(reader, NullCgroupReader)
    readings = [reader.memory_peak(), reader.memory_anon(), reader.cpu_usage_usec()]
    assert readings == [None, None, None]
    containers = InProcessRunner(ROOT / "systems/fake/entrypoint", REGISTRY, env=ENV)
    runner = Runner(containers, root=ROOT, registry=REGISTRY, image="local/x@sha256:" + "0" * 64)
    spec = JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, False, str(tmp_path), "v0.1")
    run = json.loads((runner.run(spec) / "run.json").read_text())
    assert run["status"] == "completed"
    assert REGISTRY.errors("run/1", run) == []  # valid on this host, Linux or macOS
    for metric in RESOURCES:
        q = run["metrics"][metric]
        assert (q["value"], q["null_reason"]) == (None, "not_applicable"), metric
    assert run["metrics"]["prove_cpu_seconds"]["scope"] == "prove.session"
    assert run["metrics"]["commit_cpu_seconds"]["scope"] == "commit"


def test_gpu_profile_never_uses_null_reader() -> None:
    with pytest.raises(IProofsError) as e:
        select_readers(gpu_profile=True, nvml=lambda: False)
    assert e.value.kind is ErrorKind.ENVIRONMENT
    assert "NVML is unavailable" in e.value.message


def test_watcher_polls_without_inotify(tmp_path: Path) -> None:
    watcher = ReleaseWatcher(tmp_path, force_poll=True)
    watcher.start()
    watcher.stop(call_end_ns=None)
    assert watcher.mechanism == "poll"
