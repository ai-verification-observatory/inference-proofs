from pathlib import Path

import pytest

from iproofs.errors import IProofsError
from iproofs.model import ProverProfile, VerifierProfile, load_reference
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")


def test_reference_valid() -> None:
    """TC-REF-VALID: the committed v0.1 file loads with both profiles."""
    ref = load_reference("v0.1", ROOT, REGISTRY)
    prover = ref.profiles["prover-h100"]
    verifier = ref.profiles["verifier-cpu"]
    assert isinstance(prover, ProverProfile)
    assert isinstance(verifier, VerifierProfile)
    assert prover.gpu is not None
    assert prover.gpu.count == 1
    assert prover.cpu.logical_cpus_on_gpu_numa_node == 24
    assert verifier.cpu.logical_cpus == 8
    assert verifier.emulation.allowed_on == ("prover-h100",)
    assert ref.cost.price_per_gpu_hour_usd.grade == "asserted"


def test_reference_placeholders_are_visible() -> None:
    """The price is set (#78); the driver stays a placeholder until #77 resolves it."""
    ref = load_reference("v0.1", ROOT, REGISTRY)
    assert (ref.cost.price_per_gpu_hour_usd.value or 0) > 0
    assert ref.profiles["prover-h100"].driver == "unpinned"  # type: ignore[union-attr]


def test_reference_ci_profile_has_no_gpu() -> None:
    ci = load_reference("ci", ROOT, REGISTRY).profiles["ci-cpu"]
    assert isinstance(ci, ProverProfile)
    assert ci.gpu is None


def test_reference_unknown_release() -> None:
    with pytest.raises(IProofsError, match="no reference file"):
        load_reference("v9.9", ROOT, REGISTRY)
