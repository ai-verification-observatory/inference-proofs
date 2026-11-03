"""TC-CPU-DETERMINISTIC (RFC-0006): same input, same output; disjoint sets; real CPUs."""

from hypothesis import given
from hypothesis import strategies as st

from iproofs.errors import IProofsError
from iproofs.provenance import Cpu, Topology, select_cpus


@st.composite
def topologies(draw: st.DrawFn) -> tuple[Topology, int]:
    nodes = draw(st.integers(min_value=1, max_value=3))
    cores = draw(st.integers(min_value=1, max_value=20))
    smt = draw(st.integers(min_value=1, max_value=2))
    ids = draw(st.permutations(range(nodes * cores * smt)))
    cpus = [
        Cpu(ids[(n * cores + c) * smt + t], n, c, n)
        for n in range(nodes)
        for c in range(cores)
        for t in range(smt)
    ]
    return Topology(tuple(sorted(cpus, key=lambda c: c.id))), draw(st.integers(0, nodes - 1))


@given(topologies(), st.integers(1, 24), st.integers(1, 8))
def test_select_cpus_deterministic(
    tn: tuple[Topology, int], n_prover: int, n_verifier: int
) -> None:
    topo, node = tn
    try:
        a = select_cpus(topo, node, n_prover, n_verifier)
    except IProofsError:
        return
    assert select_cpus(topo, node, n_prover, n_verifier) == a
    assert not set(a.prover) & set(a.verifier)
    known = {c.id for c in topo.cpus}
    assert set(a.prover) | set(a.verifier) <= known
    assert {c.node for c in topo.cpus if c.id in a.prover} == {node}
    assert len(a.prover) == n_prover
    assert len(a.verifier) == n_verifier
