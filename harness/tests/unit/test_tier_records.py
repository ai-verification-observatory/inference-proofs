"""review/1 and reproduction/1 examples load into their models (RFC-0007)."""

from pathlib import Path

import pytest

from iproofs.model import ReproductionRecord, ReviewRecord, load
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")


@pytest.mark.parametrize("path", sorted((ROOT / "schema/review/examples/valid").glob("*.json")))
def test_review_examples_load(path: Path) -> None:
    review = load(path, REGISTRY)
    assert isinstance(review, ReviewRecord)
    checks = (review.checks.pins, review.checks.logs, review.checks.controls)
    assert review.outcome == "objected" or set(checks) == {"pass"}


def test_reproduction_example_loads() -> None:
    path = ROOT / "schema/reproduction/examples/valid/ineligible-same-machine.json"
    record = load(path, REGISTRY)
    assert isinstance(record, ReproductionRecord)
    assert record.outcome == "ineligible"
    assert not record.eligibility.different_machine
    assert record.comparisons[0].original.n == 3
