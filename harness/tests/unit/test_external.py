"""external/1 (RFC-0004 §Mapping from upstream scopes) and INV-MAP-1."""

from pathlib import Path

import pytest

from iproofs.derive import derived
from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import External, load
from iproofs.quantity import Scope, Unit
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")


@pytest.mark.parametrize("system", ["sash", "flashprove"])
def test_external_figures_load(system: str) -> None:
    doc = load(ROOT / f"systems/{system}/external.yaml", REGISTRY)
    assert isinstance(doc, External)
    assert doc.system == system
    for figure in doc.figures:
        q = figure.quantity
        assert (q.grade, q.tier, q.source.kind) == ("external", "reported", "upstream")
        assert doc.upstream.commit in q.source.ref  # INV-QTY-5: at the pin
        assert q.upstream_scope
        assert q.mapping is not None


def test_external_not_derivation_input() -> None:
    """INV-MAP-1: an external figure never feeds a formula over measured inputs."""
    doc = load(ROOT / "systems/sash/external.yaml", REGISTRY)
    assert isinstance(doc, External)
    tree = {
        "value": 3683.298, "unit": "s", "scope": "prove.steady", "grade": "external",
        "tier": "reported", "null_reason": None,
        "source": {"kind": "upstream", "ref": doc.figures[2].quantity.source.ref},
    }  # fmt: skip
    with pytest.raises(IProofsError) as e:
        derived("D-RATE-S", "0", Unit.TOKEN_PER_S, Scope.PROVE_STEADY,
                [("tokens", None), ("external.yaml#/figures/2", tree)], lambda v: 1.0)  # fmt: skip
    assert e.value.kind is ErrorKind.INTERNAL
    assert "external figure" in e.value.message
    projected = derived("P-CAMPAIGN", "0", Unit.S, Scope.WHOLE_WALL,
                        [("external.yaml#/figures/2", tree)], lambda v: v[0])  # fmt: skip
    assert projected["value"] == 3683.298  # the campaign projection may read external figures
