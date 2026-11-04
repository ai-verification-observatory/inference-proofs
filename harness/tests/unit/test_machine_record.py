"""RFC-0006 §Machine record: TC-MR-FIELDS, TC-MR-NO-IDENTIFIERS, TC-MR-DRIFT."""

import json
import shutil
from pathlib import Path

import pytest

from iproofs.adapter import InProcessRunner
from iproofs.log.redact import Redactor
from iproofs.provenance import Host, machine_drift, machine_record, sysfs_bus_id
from iproofs.runner import CpuOnlyEnvironment, JobSpec, Runner
from iproofs.schema import SchemaRegistry
from iproofs.validate.tree import scan_text
from secret_samples import sample

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "harness/tests/fixtures/host"
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
UUID = sample("SEC-8")  # a GPU UUID, from the fixtures gate G9 skips
COMMANDS = {
    "uname -r": "6.8.0-45-generic",
    "docker version --format {{.Server.Version}}": "27.3.1",
    "docker info --format {{.CgroupDriver}} {{.CgroupVersion}}": "systemd 2",
    "nvidia-ctk --version": "NVIDIA Container Toolkit CLI version 1.16.2\ncommit: abc",
}


def nvml(index: int) -> dict[str, object]:
    return {
        "model": "NVIDIA H100 80GB HBM3",
        "count_visible": 8,
        "memory_total_mib": 81559,
        "driver_version": "560.35.03",
        "cuda_driver_api": "12.6",
        "pci_bus_id": "00000000:17:00.0",  # NVML form: 8-digit domain, sysfs uses 4
        "uuid": UUID,  # NVML knows it; the record must not carry it
        "serial": "1652022000123",
    }


def host(root: Path = FIXTURE, commands: dict[str, str] = COMMANDS) -> Host:
    return Host(root, run=lambda argv: commands.get(" ".join(argv)), nvml=nvml,
                dev_of=lambda _: (259, 0))  # fmt: skip


def record(h: Host, **kw: object) -> dict[str, object]:
    args: dict[str, object] = {
        "results": FIXTURE,
        "gpu_index": 0,
        "cpus": {"prover": [0, 1], "verifier": [2, 3], "verifier_1": [2]},
        "mems": [0],
        "provider": "example-cloud",
    }
    return machine_record(h, **{**args, **kw})  # type: ignore[arg-type]


def test_machine_record_fields() -> None:
    """TC-MR-FIELDS: the fixture tree gives exactly the RFC-0006 fields."""
    r = record(host())
    disk = r.pop("disk")
    assert isinstance(disk, dict)
    assert disk["type"] == "nvme"
    assert isinstance(disk["free_bytes_at_start"], int)
    assert r == {
        "gpu": {
            "model": "NVIDIA H100 80GB HBM3", "count_visible": 8, "memory_total_mib": 81559,
            "bound_index": 0, "numa_node": 0, "driver_version": "560.35.03",
            "cuda_driver_api": "12.6",
        },
        "cpu": {
            "model": "AMD EPYC 9654 96-Core Processor", "sockets": 2, "physical_cores": 4,
            "logical_cpus": 4, "smt_active": True, "bound_prover": [0, 1],
            "bound_verifier": [2, 3], "bound_verifier_single": [2],
        },
        "numa": {"bound_mems": [0], "nodes": 2},
        "memory": {"total_bytes": 1584538180 * 1024, "available_bytes_at_start": 1550793824 * 1024},
        "os": {"id": "ubuntu", "version_id": "24.04"},
        "kernel": {"release": "6.8.0-45-generic"},
        "container": {
            "docker_engine": "27.3.1", "cgroup_driver": "systemd", "cgroup_version": "2",
            "nvidia_container_toolkit": "1.16.2",
        },
        "provider": "example-cloud",
        "verifier_host": "same_as_prover",
    }  # fmt: skip
    manifest = json.loads((ROOT / "schema/manifest/examples/valid/fake-success.json").read_text())
    assert REGISTRY.errors("manifest/1", {**manifest, "machine": {**r, "disk": disk}}) == []
    extra = {**manifest, "machine": {**r, "hostname": "x"}}
    assert REGISTRY.errors("manifest/1", extra)  # INV-MR-1: nothing outside the list


def test_machine_record_no_identifiers(tmp_path: Path) -> None:
    """TC-MR-NO-IDENTIFIERS: a host seeded with a hostname, a MAC and a GPU UUID leaks none."""
    seeded = tmp_path / "host"
    shutil.copytree(FIXTURE, seeded, symlinks=True)
    (seeded / "etc/hostname").write_text("gpu-box-07.lab.example\n")
    (seeded / "sys/class/net/eth0").mkdir(parents=True)
    mac = sample("SEC-7")
    (seeded / "sys/class/net/eth0/address").write_text(mac + "\n")
    cpuinfo = seeded / "proc/cpuinfo"
    cpuinfo.write_text(cpuinfo.read_text().replace("Processor", "Processor gpu-box-07"))
    redact = Redactor.from_host(env={}, hostname="gpu-box-07.lab.example", home="/home/x")
    text = json.dumps(record(host(seeded), redact=redact))
    for leaked in ("gpu-box-07", mac, UUID, "1652022000123", "lab.example"):
        assert leaked not in text
    assert scan_text(text, "manifest.json") == []  # gate G9 finds nothing


def test_machine_record_drift() -> None:
    """TC-MR-DRIFT: a different kernel string between the two collections is reported."""
    before = record(host())
    after = record(host(commands={**COMMANDS, "uname -r": "6.8.0-46-generic"}))
    assert machine_drift(before, after) == [
        "kernel.release: '6.8.0-45-generic' -> '6.8.0-46-generic'"
    ]
    assert machine_drift(before, record(host())) == []


class FixtureHost(CpuOnlyEnvironment):
    def __init__(self, kernels: list[str]) -> None:
        self.kernels = kernels

    def host(self) -> Host:
        kernel = self.kernels.pop(0) if len(self.kernels) > 1 else self.kernels[0]
        return host(commands={**COMMANDS, "uname -r": kernel})


@pytest.mark.parametrize("kernels", [["6.8.0-45-generic"], ["6.8.0-45-generic", "6.9.0"]])
def test_runner_records_and_checks_drift(tmp_path: Path, kernels: list[str]) -> None:
    env = {
        "IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78",
        "IPROOFS_FAKE_DELAY_S": "0",
    }
    containers = InProcessRunner(ROOT / "systems/fake/entrypoint", REGISTRY, env=env)
    runner = Runner(containers, root=ROOT, registry=REGISTRY, env=FixtureHost(list(kernels)),
                    image="local/x@sha256:" + "0" * 64, provider="example-cloud")  # fmt: skip
    spec = JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, False, str(tmp_path), "v0.1")
    run_dir = runner.run(spec)
    run = json.loads((run_dir / "run.json").read_text())
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["machine"]["kernel"] == {"release": kernels[0]}
    assert manifest["machine"]["cpu"]["bound_prover"] == [0]  # the CPU-only binding, "0"
    for path in run_dir.rglob("*"):  # gate G9 over the run directory written from the fixture
        if path.is_file():
            assert scan_text(path.read_text(errors="replace"), path.name) == [], path
    if len(kernels) == 1:
        assert run["status"] == "completed"
    else:
        assert (run["failure"]["kind"], run["failure"]["step"]) == ("environment", "written")
        assert "kernel.release" in run["failure"]["message"]


@pytest.mark.parametrize(
    ("nvml_bus", "sysfs"),
    [
        ("00000000:17:00.0", "0000:17:00.0"),  # NVML_DEVICE_PCI_BUS_ID_FMT
        ("00000001:A3:00.0", "0001:a3:00.0"),
        ("0000:17:00.0", "0000:17:00.0"),  # already the sysfs form
        ("bogus", "bogus"),
    ],
)
def test_sysfs_bus_id(nvml_bus: str, sysfs: str) -> None:
    """The GPU's NUMA node is read from sysfs, which names devices with a 4-digit domain."""
    assert sysfs_bus_id(nvml_bus) == sysfs
