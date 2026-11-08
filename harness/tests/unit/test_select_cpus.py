"""RFC-0006 §CPU and memory selection: TC-CPU-2SOCKET-SMT, TC-CPU-SMALL-NODE, TC-CPU-SMT-OFF."""

from pathlib import Path

import pytest

from iproofs.errors import ErrorKind, IProofsError
from iproofs.provenance import (
    Cpu,
    Host,
    Topology,
    machine_record,
    read_topology,
    select_cpus,
)

ROOT = Path(__file__).resolve().parents[3]


def two_sockets(smt: bool = True, cores: int = 24) -> Topology:
    """Linux numbering: first threads of socket 0 then socket 1, then their SMT siblings."""
    cpus = [Cpu(s * cores + c, s, c, s) for s in (0, 1) for c in range(cores)]
    if smt:
        cpus += [Cpu(2 * cores + s * cores + c, s, c, s) for s in (0, 1) for c in range(cores)]
    return Topology(tuple(cpus))


def test_select_cpus_two_sockets_smt() -> None:
    """TC-CPU-2SOCKET-SMT: GPU on node 1; one prover CPU per physical core of node 1."""
    b = select_cpus(two_sockets(), gpu_numa_node=1, n_prover=24)
    assert b.prover == tuple(range(24, 48))
    assert b.verifier == tuple(range(72, 80))  # node 1's SMT siblings come before node 0
    assert b.verifier_1 == (72,)
    assert b.mems == (1,)
    assert not set(b.prover) & set(b.verifier)


def test_select_cpus_small_node() -> None:
    """TC-CPU-SMALL-NODE: a node with 16 logical CPUs cannot hold 24 prover CPUs."""
    with pytest.raises(IProofsError) as e:
        select_cpus(two_sockets(cores=8), gpu_numa_node=0, n_prover=24)
    assert e.value.kind is ErrorKind.ENVIRONMENT
    assert "PC-CPU-NUMA" in e.value.message


def test_select_cpus_smt_off() -> None:
    """TC-CPU-SMT-OFF: no siblings; the second pass is empty and the result is the same."""
    b = select_cpus(two_sockets(smt=False), gpu_numa_node=0, n_prover=24)
    assert b.prover == tuple(range(24))
    assert b.verifier == tuple(range(24, 32))  # the other node, in order
    assert select_cpus(two_sockets(smt=False), gpu_numa_node=0, n_prover=24) == b


def test_select_cpus_verifier_shortage() -> None:
    topo = Topology(tuple(Cpu(i, 0, i, 0) for i in range(26)))
    with pytest.raises(IProofsError, match="verifier emulation"):
        select_cpus(topo, gpu_numa_node=0, n_prover=24)


def test_select_cpus_from_the_fixture_host_and_into_the_record() -> None:
    topo = read_topology(ROOT / "harness/tests/fixtures/host")
    assert [(c.id, c.package, c.core, c.node) for c in topo.cpus] == [
        (0, 0, 0, 0), (1, 0, 1, 0), (2, 1, 0, 1), (3, 1, 1, 1)
    ]  # fmt: skip
    b = select_cpus(topo, gpu_numa_node=1, n_prover=2, n_verifier=2)
    assert (b.prover, b.verifier, b.mems) == ((2, 3), (0, 1), (1,))
    host = Host(ROOT / "harness/tests/fixtures/host", run=lambda argv: None, nvml=lambda i: None,
                dev_of=lambda p: (259, 0))  # fmt: skip
    record = machine_record(host, results=ROOT, gpu_index=None, cpus=b.roles(), mems=b.mems,
                            provider="p")  # fmt: skip
    cpu, numa = record["cpu"], record["numa"]
    assert isinstance(cpu, dict)
    assert isinstance(numa, dict)
    assert (cpu["bound_prover"], cpu["bound_verifier"], cpu["bound_verifier_single"]) == (
        [2, 3], [0, 1], [0]
    )  # fmt: skip
    assert numa["bound_mems"] == [1]
