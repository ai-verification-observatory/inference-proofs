from pathlib import Path

import pytest

from iproofs.errors import IProofsError
from iproofs.model import ProverProfile, VerifierProfile, load_reference
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")


def test_reference_valid() -> None:
    """TC-REF-VALID: the committed v0.1 file loads with its prover and verifier profiles."""
    ref = load_reference("v0.1", ROOT, REGISTRY)
    prover = ref.profiles["prover-h200"]
    verifier = ref.profiles["verifier-cpu"]
    assert isinstance(prover, ProverProfile)
    assert isinstance(verifier, VerifierProfile)
    assert prover.gpu is not None
    assert prover.gpu.count == 1
    assert prover.cpu.logical_cpus_on_gpu_numa_node == 24
    assert verifier.cpu.logical_cpus == 8
    assert verifier.emulation.allowed_on == (
        "prover-h200", "prover-h200-hosted", "prover-h100", "prover-h100-hosted"
    )  # fmt: skip
    assert ref.cost.price_per_gpu_hour_usd.grade == "asserted"


def test_reference_placeholders_are_visible() -> None:
    """The prices are set (C7); the drivers are unpinned (RFC-0006 Q3, Q5) and say so."""
    ref = load_reference("v0.1", ROOT, REGISTRY)
    assert (ref.cost.price_per_gpu_hour_usd.value or 0) > 0
    assert ref.costs is not None
    assert (ref.costs["h200"].price_per_gpu_hour_usd.value or 0) > 0
    for pid in ("prover-h100", "prover-h200", "prover-h200-hosted"):
        assert ref.profiles[pid].driver == "unpinned"  # type: ignore[union-attr]


def test_reference_ci_profile_has_no_gpu() -> None:
    ci = load_reference("ci", ROOT, REGISTRY).profiles["ci-cpu"]
    assert isinstance(ci, ProverProfile)
    assert ci.gpu is None


def test_reference_unknown_release() -> None:
    with pytest.raises(IProofsError, match="no reference file"):
        load_reference("v9.9", ROOT, REGISTRY)
