"""GPU-host tests of CPU binding and the machine record (RFC-0006): the cpuset lies on the
GPU's NUMA node on distinct physical cores, and the GH-MR-H200 (or GH-MR-H100) record validates.
They bind what a job on the profile binds: `IPROOFS_PROFILE` (default prover-h200) of
`IPROOFS_RELEASE`'s reference file (default v0.1) gives the prover CPU count, and on a hosted
profile only the CPUs of this process's scheduler affinity count (`usable_topology`). Skipped
without NVML."""

import os
from pathlib import Path

from iproofs.log.redact import Redactor
from iproofs.model import HostedRuntime, ProverProfile, load_reference
from iproofs.provenance import Host, machine_record, select_cpus, usable_topology
from iproofs.schema import SchemaRegistry

from .gpu_host import GPU, needs_nvml

pytestmark = needs_nvml
ROOT = Path(__file__).resolve().parents[3]
PROFILE = os.environ.get("IPROOFS_PROFILE", "prover-h200")
RELEASE = os.environ.get("IPROOFS_RELEASE", "v0.1")


def profile() -> ProverProfile:
    found = load_reference(RELEASE, ROOT, SchemaRegistry.from_tree(ROOT / "schema")).profiles[
        PROFILE
    ]
    assert isinstance(found, ProverProfile)
    return found


def host_of(p: ProverProfile) -> Host:
    return Host(hosted=isinstance(p.container_runtime, HostedRuntime))


def test_cpuset_on_gpu_numa_node() -> None:
    p = profile()
    host = host_of(p)
    node = host.gpu(GPU)["numa_node"]
    topology = usable_topology(host)
    binding = select_cpus(topology, int(node), p.cpu.logical_cpus_on_gpu_numa_node)  # type: ignore[call-overload]
    cpus = {c.id: c for c in topology.cpus}
    assert len(binding.prover) == p.cpu.logical_cpus_on_gpu_numa_node
    assert all(cpus[i].node == node for i in binding.prover)
    on_node = {(c.package, c.core) for c in topology.cpus if c.node == node}
    cores = {(cpus[i].package, cpus[i].core) for i in binding.prover}
    assert len(cores) == min(len(binding.prover), len(on_node))  # SMT siblings only when short
    assert not set(binding.prover) & (set(binding.verifier) | set(binding.verifier_1))


def test_machine_record_validates(tmp_path: Path) -> None:
    """GH-MR-H200 (GH-MR-H100 on prover-h100), second half: this host's record validates."""
    p = profile()
    host = host_of(p)
    node = int(host.gpu(GPU)["numa_node"])  # type: ignore[call-overload]
    binding = select_cpus(usable_topology(host), node, p.cpu.logical_cpus_on_gpu_numa_node)
    record = machine_record(host, results=tmp_path, gpu_index=GPU, cpus=binding.roles(),
                            mems=binding.mems, provider="undeclared",
                            redact=Redactor.from_host())  # fmt: skip
    registry = SchemaRegistry.from_tree(ROOT / "schema")
    assert registry.errors("manifest/1", record, def_name="machine") == []
    assert record["gpu"]["model"].startswith(("NVIDIA H100", "NVIDIA H200"))  # type: ignore[index]
