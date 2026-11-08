"""RFC-0006 §H200 profiles: `prover-h200` (the v0.1 reference, docker on a bare-metal host) and
`prover-h200-hosted` (a minimum spec for a hosted H200 container), their conformance on fake
machine records of hosts with several GPUs, the prover CPU count a hosted job binds, and the
per-GPU-model cost basis (C7)."""

import copy
import dataclasses
import os
from pathlib import Path
from typing import Any

import pytest

from iproofs import cli, provenance
from iproofs.adapter import HostedRunner, image_environment
from iproofs.errors import IProofsError
from iproofs.model import ProverProfile, VerifierProfile, load_reference
from iproofs.provenance import Cpu, Host, Topology, check_profile, select_cpus, usable_topology
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "harness/tests/fixtures/host"
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
REF = load_reference("v0.1", ROOT, REGISTRY)
GIB = 1024**3
GB = 10**9
DRIVER = "999.99.99"  # a stand-in for the pins the profiles wait for (RFC-0006 Q3, Q5)


def profile(pid: str, *, pinned: bool = True) -> ProverProfile:
    found = REF.profiles[pid]
    assert isinstance(found, ProverProfile)
    return dataclasses.replace(found, driver=DRIVER) if pinned else found


# A bare-metal node as prover-h200 describes it: 2 sockets, 8 H200 SXM, docker under systemd.
BARE: dict[str, Any] = {
    "gpu": {"model": "NVIDIA H200", "count_visible": 8, "memory_total_mib": 143771,
            "bound_index": 0, "numa_node": 0, "driver_version": DRIVER},
    "cpu": {"logical_cpus": 224},
    "memory": {"available_bytes_at_start": 1900 * GIB},
    "disk": {"type": "nvme", "free_bytes_at_start": 3000 * GIB},
    "os": {"id": "ubuntu", "version_id": "24.04"},
    "kernel": {"release": "6.8.0-62-generic"},
    "container": {"docker_engine": "27.3.1", "cgroup_driver": "systemd", "cgroup_version": "2",
                  "nvidia_container_toolkit": "1.17.3"},
}  # fmt: skip

# Hugging Face Jobs `h200` as its flavor table states it (1x H200, 23 vCPU, 256 GB RAM, 3000 GB
# disk, read 2026-11-08). How the provider limits CPUs (a quota, a cpuset or a VM) is not
# documented; the probe (docs/runbooks/host-probe.py) reads it. Here: a 23-CPU quota on a host
# whose sysfs shows 192 CPUs.
HF_H200: dict[str, Any] = {
    "gpu": {"model": "NVIDIA H200", "count_visible": 1, "memory_total_mib": 143771,
            "bound_index": 0, "numa_node": 0, "driver_version": DRIVER},
    "cpu": {"logical_cpus": 192, "cgroup_quota_cpus": 23.0},
    "memory": {"available_bytes_at_start": 1800 * GIB, "cgroup_limit_bytes": 256 * GB},
    "disk": {"free_bytes_at_start": 3000 * GB},
    "kernel": {"release": "6.8.0-62-generic"},
    "container": {"execution": "hosted", "cgroup_version": "2"},
}  # fmt: skip

# `h200x2` (2x H200, 46 vCPU, 512 GB RAM, 6000 GB disk): the job binds GPU 1, GPU 0 stays idle.
HF_H200X2: dict[str, Any] = copy.deepcopy(HF_H200)
HF_H200X2["gpu"] |= {"count_visible": 2, "bound_index": 1, "numa_node": 1}
HF_H200X2["cpu"]["cgroup_quota_cpus"] = 46.0
HF_H200X2["memory"]["cgroup_limit_bytes"] = 512 * GB
HF_H200X2["disk"]["free_bytes_at_start"] = 6000 * GB


def checks(record: dict[str, Any], prof: ProverProfile, numa_cpus: int = 96) -> list[str]:
    found = check_profile(record, prof, numa_node_cpus=numa_cpus, gpu_processes=0)
    return [f.check for f in found]


def with_(record: dict[str, Any], path: str, value: object) -> dict[str, Any]:
    out = copy.deepcopy(record)
    section, key = path.split(".")
    out[section][key] = value
    return out


def test_h200_profiles_declared() -> None:
    """The reference asks for one H200 and prover-h100's host needs; the hosted form for one H200
    and the minimums of the smallest hosted H200 offer: 15 + 8 CPUs, 200 GiB."""
    h100 = profile("prover-h100")
    p = profile("prover-h200", pinned=False)
    assert p.gpu is not None
    assert (p.gpu.model, p.gpu.form_factor, p.gpu.count) == ("NVIDIA H200", "SXM", 1)
    assert p.cpu == h100.cpu
    assert p.host_memory_gib_min == h100.host_memory_gib_min == 330
    assert p.disk == h100.disk
    assert p.container_runtime == h100.container_runtime
    assert (p.driver, p.cost) == ("unpinned", "h200")
    hosted = profile("prover-h200-hosted", pinned=False)
    assert hosted.gpu == p.gpu
    assert (hosted.cpu.logical_cpus_on_gpu_numa_node, hosted.cpu.logical_cpus_total_min) == (15, 23)
    verifier = REF.profiles["verifier-cpu"]
    assert isinstance(verifier, VerifierProfile)
    assert hosted.cpu.logical_cpus_on_gpu_numa_node + verifier.cpu.logical_cpus == 23
    assert hosted.host_memory_gib_min == 200
    assert hosted.host_memory_gib_min * GIB < 256 * GB  # the h200 flavor qualifies
    assert hosted.container_runtime == profile("prover-h100-hosted").container_runtime
    assert (hosted.driver, hosted.cost) == ("unpinned", "h200")
    h200 = [pid for pid, found in REF.profiles.items()
            if isinstance(found, ProverProfile) and found.gpu
            and "H200" in found.gpu.model]  # fmt: skip
    assert h200 == ["prover-h200", "prover-h200-hosted"]
    assert {"prover-h200", "prover-h200-hosted", "prover-h100"} <= set(
        verifier.emulation.allowed_on
    )


def test_bare_metal_h200_conforms() -> None:
    assert checks(BARE, profile("prover-h200")) == []


def test_unpinned_driver_is_the_only_failure() -> None:
    """Until the pins, every H200 host fails PC-DRIVER and nothing else (RFC-0006 R3, Q3, Q5)."""
    assert checks(BARE, profile("prover-h200", pinned=False)) == ["PC-DRIVER"]
    assert checks(HF_H200, profile("prover-h200-hosted", pinned=False), 23) == ["PC-DRIVER"]


def test_h100_host_fails_the_h200_profiles() -> None:
    record = with_(with_(BARE, "gpu.model", "NVIDIA H100 80GB HBM3"), "gpu.memory_total_mib", 81559)
    assert checks(record, profile("prover-h200")) == ["PC-GPU-MODEL", "PC-GPU-MEM"]
    assert "PC-GPU-MODEL" in checks(BARE, profile("prover-h100"))
    hosted = with_(HF_H200, "gpu.model", "NVIDIA H100 80GB HBM3")
    assert checks(hosted, profile("prover-h200-hosted")) == ["PC-GPU-MODEL"]


def test_gpu_count_is_a_lower_bound() -> None:
    """R1: a node with 8 H200 passes whichever GPU the job binds; the others stay idle."""
    assert checks(with_(BARE, "gpu.bound_index", 5), profile("prover-h200")) == []
    assert checks(with_(BARE, "gpu.count_visible", 1), profile("prover-h200")) == []
    assert checks(with_(BARE, "gpu.count_visible", 0), profile("prover-h200")) == ["PC-GPU-COUNT"]


def test_hosted_record_fails_the_docker_h200_profile() -> None:
    """prover-h200 is docker only: a hosted container's record fails its runtime check."""
    record = copy.deepcopy(BARE)
    record["container"] = {"execution": "hosted", "cgroup_version": "2"}
    assert "PC-RUNTIME" in checks(record, profile("prover-h200"))
    assert {"PC-RUNTIME", "PC-OS", "PC-DISK"} <= set(checks(HF_H200, profile("prover-h200")))


def test_small_numa_node_and_memory_fail() -> None:
    """The probe's requirements are the profile's: 24 CPUs on the GPU's node, 330 GiB."""
    assert checks(BARE, profile("prover-h200"), numa_cpus=16) == ["PC-CPU-NUMA"]
    record = with_(BARE, "memory.available_bytes_at_start", 256 * GIB)
    assert checks(record, profile("prover-h200")) == ["PC-MEM"]


def test_both_hf_flavors_meet_the_hosted_minimum() -> None:
    """The 1-GPU `h200` flavor (23 CPUs, 256 GB) and the 2-GPU `h200x2` (GPU 1 bound) pass;
    so does a VM-like `h200` whose sysfs shows only its 23 CPUs, without a quota."""
    hosted = profile("prover-h200-hosted")
    assert checks(HF_H200, hosted, numa_cpus=23) == []
    assert checks(HF_H200X2, hosted, numa_cpus=23) == []
    vm = copy.deepcopy(HF_H200)
    vm["cpu"] = {"logical_cpus": 23}
    assert checks(vm, hosted, numa_cpus=23) == []


def test_hosted_minimums_fail_below() -> None:
    hosted = profile("prover-h200-hosted")
    assert checks(with_(HF_H200, "cpu.cgroup_quota_cpus", 14.0), hosted, 23) == ["PC-CPU-QUOTA"]
    assert checks(with_(HF_H200, "memory.cgroup_limit_bytes", 192 * GIB), hosted, 23) == ["PC-MEM"]
    assert checks(with_(HF_H200, "cpu.logical_cpus", 22), hosted, 23) == ["PC-CPU-TOTAL"]
    assert checks(HF_H200, hosted, numa_cpus=14) == ["PC-CPU-NUMA"]
    assert checks(with_(HF_H200, "gpu.memory_total_mib", 97871), hosted, 23) == ["PC-GPU-MEM"]


def test_flashprove_floor_is_not_the_hosted_minimum() -> None:
    """R2's exception: the `h200` flavor meets the profile but not FlashProve's 330 GB floor
    (systems/flashprove/README.md); `h200x2` meets both."""
    floor = 330 * GB
    assert HF_H200["memory"]["cgroup_limit_bytes"] < floor
    assert HF_H200X2["memory"]["cgroup_limit_bytes"] >= floor


def test_select_cpus_on_23_cpus() -> None:
    """TC-CPU-HOSTED: one node of 23 CPUs (no SMT) gives 15 prover CPUs and the other 8 to the
    verifier; 24 prover CPUs do not fit."""
    topology = Topology(tuple(Cpu(i, 0, i, 0) for i in range(23)))
    binding = select_cpus(topology, 0, n_prover=15)
    assert binding.prover == tuple(range(15))
    assert binding.verifier == tuple(range(15, 23))
    assert binding.verifier_1 == (15,)
    with pytest.raises(IProofsError, match="not enough CPUs for verifier emulation"):
        select_cpus(topology, 0, n_prover=16)


def test_hosted_topology_is_the_affinity(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hosted container binds only CPUs of its scheduler affinity; a docker host, or a fixture
    tree, keeps every CPU."""
    full = provenance.read_topology(FIXTURE)
    assert [c.id for c in full.cpus] == [0, 1, 2, 3]
    host = Host(FIXTURE, run=lambda _: None, hosted=True)
    assert usable_topology(host) == full  # a fixture root, not the real one
    assert [c.id for c in usable_topology(host, allowed={1, 3}).cpus] == [1, 3]
    monkeypatch.setattr(provenance, "read_topology", lambda root: full)
    monkeypatch.setattr(os, "sched_getaffinity", lambda pid: {0, 2}, raising=False)
    real = Host(Path("/"), run=lambda _: None, hosted=True)
    assert [c.id for c in usable_topology(real).cpus] == [0, 2]
    docker = Host(Path("/"), run=lambda _: None)
    assert usable_topology(docker) == full


def test_run_binds_the_profiles_prover_cpus() -> None:
    """`iproofs run` passes the profile's `logical_cpus_on_gpu_numa_node` to the GPU host."""
    assert cli._prover_cpus(ROOT, "prover-h200-hosted", REGISTRY) == 15
    assert cli._prover_cpus(ROOT, "prover-h200", REGISTRY) == 24
    assert cli._prover_cpus(ROOT, "no-such-profile", REGISTRY) == 24


def test_second_gpu_stays_idle(tmp_path: Path) -> None:
    """Only the bound GPU is visible to a GPU step; verify sees none (RFC-0006 §Hosted)."""
    runner = HostedRunner(["python3", "/opt/x/entrypoint"], REGISTRY, {"PATH": "/usr/bin"})
    _, env = runner._command("prove", tmp_path / "io", None, 1, "0-14", [])
    assert env["CUDA_VISIBLE_DEVICES"] == "1"
    _, env = runner._command("verify", tmp_path / "io", None, 1, "15-22", [])
    assert env["CUDA_VISIBLE_DEVICES"] == ""


def test_price_pointer_per_gpu_model() -> None:
    """C7: the H200 profiles cost from `costs.h200`, H100 profiles keep `cost` (C4)."""
    assert REF.price_pointer("prover-h200") == "/costs/h200/price_per_gpu_hour_usd"
    assert REF.price_pointer("prover-h200-hosted") == "/costs/h200/price_per_gpu_hour_usd"
    assert REF.price_pointer("prover-h100") == "/cost/price_per_gpu_hour_usd"
    assert REF.price_pointer("prover-h100-hosted") == "/cost/price_per_gpu_hour_usd"
    assert REF.price_pointer("verifier-cpu") == "/cost/price_per_gpu_hour_usd"
    assert REF.costs is not None
    assert REF.costs["h200"].date == "2026-11-08"


def test_price_pointer_unknown_basis() -> None:
    broken = dataclasses.replace(
        REF, profiles={"p": dataclasses.replace(profile("prover-h200"), cost="b300")}
    )
    with pytest.raises(IProofsError, match="not in `costs`"):
        broken.price_pointer("p")


def test_hf_jobs_names_stay_out_of_the_adapter_environment() -> None:
    """Hugging Face Jobs adds JOB_ID, ACCELERATOR, CPU_CORES, MEMORY and HF_NETWORK_GROUP_*
    (jobs-configuration, read 2026-11-08), and the job command of hf-jobs.md its IPROOFS_* names;
    none of them, nor a secret such as HF_TOKEN, reaches the adapter. An image's own IPROOFS_*
    name stays."""
    environ = "\0".join([
        "PATH=/usr/bin", "JOB_ID=6a2aa7cec4f53f9fc5aa4cff", "ACCELERATOR=h200x2", "CPU_CORES=46",
        "MEMORY=512Gi", "HF_NETWORK_GROUP_PREFIX=x", "HF_TOKEN=hf_x", "HF_HOME=/data/hf",
        "IPROOFS_COMMIT=" + "0" * 40, "IPROOFS_UPLOAD=ns/iproofs-dev-runs",
        "IPROOFS_UPLOAD_DIR=/upload", "IPROOFS_LABEL=probe", "IPROOFS_JOB_BUDGET_S=600",
        "IPROOFS_GPU=1", "IPROOFS_ADAPTER_COMMIT=abc",
    ])  # fmt: skip
    assert image_environment(environ) == {
        "PATH": "/usr/bin", "HF_HOME": "/data/hf", "IPROOFS_ADAPTER_COMMIT": "abc"
    }  # fmt: skip
