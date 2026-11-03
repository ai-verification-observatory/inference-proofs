"""GPU-host tests of CPU binding and the machine record (RFC-0006): the cpuset lies on the
GPU's NUMA node on distinct physical cores, and GH-MR-H100's record validates. Skipped
without NVML."""

from pathlib import Path

from iproofs.log.redact import Redactor
from iproofs.provenance import Host, machine_record, read_topology, select_cpus
from iproofs.schema import SchemaRegistry

from .gpu_host import GPU, needs_nvml

pytestmark = needs_nvml
ROOT = Path(__file__).resolve().parents[3]


def test_cpuset_on_gpu_numa_node() -> None:
    node = Host().gpu(GPU)["numa_node"]
    topology = read_topology()
    binding = select_cpus(topology, int(node))  # type: ignore[call-overload]
    cpus = {c.id: c for c in topology.cpus}
    assert all(cpus[i].node == node for i in binding.prover)
    on_node = {(c.package, c.core) for c in topology.cpus if c.node == node}
    cores = {(cpus[i].package, cpus[i].core) for i in binding.prover}
    assert len(cores) == min(len(binding.prover), len(on_node))  # SMT siblings only when short
    assert not set(binding.prover) & (set(binding.verifier) | set(binding.verifier_1))


def test_machine_record_validates(tmp_path: Path) -> None:
    """GH-MR-H100, second half: the record of this host validates against manifest/1."""
    host = Host()
    binding = select_cpus(read_topology(), int(host.gpu(GPU)["numa_node"]))  # type: ignore[call-overload]
    record = machine_record(host, results=tmp_path, gpu_index=GPU, cpus=binding.roles(),
                            mems=binding.mems, provider="undeclared",
                            redact=Redactor.from_host())  # fmt: skip
    registry = SchemaRegistry.from_tree(ROOT / "schema")
    assert registry.errors("manifest/1", record, def_name="machine") == []
    assert record["gpu"]["model"].startswith("NVIDIA H100")  # type: ignore[index]
