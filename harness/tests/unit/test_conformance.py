"""RFC-0006 §Profile conformance check: TC-CONFORM-EACH and the exit-3 path."""

import copy
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from iproofs import cli
from iproofs.model import ContainerRuntime, Disk, GpuSpec, OsSpec, ProverCpu, ProverProfile
from iproofs.provenance import check_profile

ROOT = Path(__file__).resolve().parents[3]
GIB = 1024**3
PROFILE = ProverProfile(
    kind="prover",
    gpu=GpuSpec(model="NVIDIA H100 80GB HBM3", form_factor="SXM", count=1, memory_mib_min=80000),
    cpu=ProverCpu(logical_cpus_on_gpu_numa_node=24, logical_cpus_total_min=32),
    host_memory_gib_min=330,
    disk=Disk(type="local NVMe", free_gib_min=500),
    os=OsSpec(id="ubuntu", version_id="24.04"),
    kernel_min="5.19",
    driver="560.35.03",
    container_runtime=ContainerRuntime(
        docker_engine_min="25.0", nvidia_container_toolkit_min="1.17", cgroup_driver="systemd"
    ),
)
RECORD: dict[str, Any] = {
    "gpu": {"model": "NVIDIA H100 80GB HBM3", "count_visible": 8, "memory_total_mib": 81559,
            "bound_index": 0, "numa_node": 0, "driver_version": "560.35.03"},
    "cpu": {"logical_cpus": 384},
    "memory": {"available_bytes_at_start": 1500 * GIB},
    "disk": {"type": "nvme", "free_bytes_at_start": 3000 * GIB},
    "os": {"id": "ubuntu", "version_id": "24.04"},
    "kernel": {"release": "6.8.0-45-generic"},
    "container": {"docker_engine": "27.3.1", "cgroup_driver": "systemd", "cgroup_version": "2",
                  "nvidia_container_toolkit": "1.17.3"},
}  # fmt: skip


def checks(record: dict[str, Any], **kw: Any) -> list[str]:
    kw = {"numa_node_cpus": 96, "gpu_processes": 0, **kw}
    return [f.check for f in check_profile(record, PROFILE, **kw)]


def flipped(path: str, value: object) -> dict[str, Any]:
    record = copy.deepcopy(RECORD)
    section, key = path.split(".")
    record[section][key] = value
    return record


def test_conforming_record_passes() -> None:
    assert checks(RECORD) == []


@pytest.mark.parametrize(
    ("check", "record", "extra"),
    [
        ("PC-GPU-MODEL", flipped("gpu.model", "NVIDIA A100-SXM4-80GB"), {}),
        ("PC-GPU-MEM", flipped("gpu.memory_total_mib", 40960), {}),
        ("PC-GPU-COUNT", flipped("gpu.count_visible", 0), {}),
        ("PC-GPU-BUSY", RECORD, {"gpu_processes": 1}),
        ("PC-DRIVER", flipped("gpu.driver_version", "550.54.15"), {}),
        ("PC-CPU-NUMA", RECORD, {"numa_node_cpus": 16}),
        ("PC-CPU-TOTAL", flipped("cpu.logical_cpus", 16), {}),
        ("PC-MEM", flipped("memory.available_bytes_at_start", 64 * GIB), {}),
        ("PC-DISK", flipped("disk.type", "ssd"), {}),
        ("PC-OS", flipped("os.version_id", "22.04"), {}),
        ("PC-KERNEL", flipped("kernel.release", "5.15.0-105-generic"), {}),
        ("PC-CGROUP", flipped("container.cgroup_version", "1"), {}),
        ("PC-RUNTIME", flipped("container.docker_engine", "24.0.7"), {}),
    ],
)
def test_conform_each(check: str, record: dict[str, Any], extra: dict[str, Any]) -> None:
    """TC-CONFORM-EACH: flipping exactly one fixture field fails exactly that check."""
    assert checks(record, **extra) == [check]


def test_missing_probes_fail_their_checks() -> None:
    found = checks({}, numa_node_cpus=None, gpu_processes=None)
    assert {"PC-GPU-MODEL", "PC-OS", "PC-KERNEL", "PC-CGROUP", "PC-RUNTIME", "PC-CPU-NUMA"} <= set(
        found
    )


@pytest.fixture
def prover_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A copy of the fake system declared as a prover, so a failed check refuses the run."""
    repo = tmp_path / "repo"
    copied = [
        "schema",
        "systems/fake",
        "systems/fake-broken",
        "workloads/fake-tiny-ci.yaml",
        "reference",
        "harness/tests/fixtures/prompts",
        "uv.lock",
        "pyproject.toml",
    ]
    for rel in copied:
        src, dst = ROOT / rel, repo / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst) if src.is_dir() else shutil.copy(src, dst)
    system = repo / "systems/fake/system.yaml"
    doc = yaml.safe_load(system.read_text())
    doc |= {"kind": "prover", "profile": "prover-h100",
            "image": {"repository": "ghcr.io/example/iproofs-fake", "digest": "sha256:" + "a" * 64},
            "maintainers": [{"handle": "m", "organisation": "Org"}]}  # fmt: skip
    system.write_text(yaml.safe_dump(doc))
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    monkeypatch.chdir(repo)
    return repo


def test_nonconforming_host_exits_3_and_writes_nothing(prover_repo: Path) -> None:
    results = prover_repo / "results"
    argv = ["--quiet", "run", "--system", "fake", "--workload", "fake-tiny-ci", "--profile",
            "prover-h100", "--repetitions", "1", "--results", str(results)]  # fmt: skip
    assert cli.main(argv) == 3  # no H100 here: environment, before anything is timed
    assert not results.exists() or not any(results.rglob("*"))


def run_fake(tmp_path: Path, *extra: str) -> dict[str, Any]:
    argv = ["--quiet", "run", "--system", "fake", "--workload", "fake-tiny-ci", "--profile",
            "ci-cpu", "--repetitions", "1", "--results", str(tmp_path), "--in-process",
            *extra]  # fmt: skip
    assert cli.main(argv) == 0
    (manifest,) = tmp_path.rglob("manifest.json")
    doc: dict[str, Any] = json.loads(manifest.read_text())
    doc["_run"] = json.loads((manifest.parent / "run.json").read_text())
    return doc


def test_test_systems_run_anywhere_and_flag_is_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fake run on a host that fails ci-cpu runs, with warnings; --allow-nonconforming also
    marks the manifest, which the validator refuses in results/ (POL-4)."""
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(
        "iproofs.runner.check_profile",
        lambda *a, **k: [
            __import__("iproofs.provenance", fromlist=["ConformanceFailure"]).ConformanceFailure(
                "PC-OS", "darwin, the profile needs ubuntu 24.04"
            )
        ],
    )
    plain = run_fake(tmp_path / "plain")
    assert plain["harness"]["nonconforming"] is False
    assert "conformance: PC-OS: darwin, the profile needs ubuntu 24.04" in plain["_run"]["warnings"]
    flagged = run_fake(tmp_path / "flagged", "--allow-nonconforming")
    assert flagged["harness"]["nonconforming"] is True
