import json
from enum import StrEnum
from pathlib import Path

import pytest

from iproofs import quantity as qty
from iproofs.schema import SchemaRegistry, check_examples

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = json.loads((ROOT / "schema/quantity/1.schema.json").read_text())
DEFS = SCHEMA["$defs"]
EXAMPLES = ROOT / "schema/quantity/examples"


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry.from_tree(ROOT / "schema")


def example(name: str) -> dict[str, object]:
    path = next(EXAMPLES.glob(f"*/{name}.json"))
    loaded: dict[str, object] = json.loads(path.read_text())
    return loaded


@pytest.mark.parametrize(
    ("enum", "prop"),
    [
        (qty.Unit, "unit"),
        (qty.Scope, "scope"),
        (qty.Grade, "grade"),
        (qty.Tier, "tier"),
        (qty.NullReason, "null_reason"),
        (qty.ScopeMapping, "mapping"),
    ],
)
def test_enums_match_schema(enum: type[StrEnum], prop: str) -> None:
    schema_values = [v for v in DEFS["quantityCore"]["properties"][prop]["enum"] if v is not None]
    assert [e.value for e in enum] == schema_values


def test_source_kind_enum_matches_schema() -> None:
    assert [k.value for k in qty.SourceKind] == DEFS["source"]["properties"]["kind"]["enum"]


def test_time_units_match_schema() -> None:
    rule = next(r for r in DEFS["quantityCore"]["allOf"] if "INV-QTY-3" in r["$comment"])
    assert {u.value for u in qty.TIME_UNITS} == set(rule["if"]["properties"]["unit"]["enum"])


@pytest.mark.parametrize(
    ("name", "invariant"),
    [
        ("quantity.missing-null-reason", "INV-QTY-1"),
        ("quantity.null-without-reason", "INV-QTY-2"),
        ("quantity.value-with-reason", "INV-QTY-2"),
        ("quantity.time-null-scope", "INV-QTY-3"),
        ("quantity.external-no-upstream-scope", "INV-QTY-5"),
        ("quantity.external-from-harness", "INV-QTY-5"),
        ("quantity.derived-no-inputs", "INV-QTY-6"),
        ("quantity.measured-from-upstream", "INV-QTY-7"),
        ("statistic.n1-stdev", "INV-QTY-8"),
        ("statistic.n0-value", "INV-QTY-8"),
        ("quantity.quality-on-asserted", "INV-QTY-9"),
    ],
)
def test_invariant_rejected(registry: SchemaRegistry, name: str, invariant: str) -> None:
    def_name = name.split(".", 1)[0]
    assert registry.errors("quantity/1", example(name), def_name=def_name), invariant


def test_quantity_with_stats_and_statistic_with_unknown_key_rejected(
    registry: SchemaRegistry,
) -> None:
    assert registry.errors("quantity/1", example("quantity.with-stats"), def_name="quantity")
    assert registry.errors("quantity/1", example("statistic.unknown-key"), def_name="statistic")


def test_statistic_value_must_equal_mean() -> None:
    good = example("statistic.three-repetitions")
    assert qty.statistic_problems(good) == []
    bad = {**good, "value": 9.0}
    assert qty.statistic_problems(bad) == ["INV-QTY-8: value 9.0 != stats.mean 10.0"]


def test_lowest_tier() -> None:
    assert qty.lowest_tier([qty.Tier.REPRODUCED, qty.Tier.REPORTED]) is qty.Tier.REPORTED
    assert qty.lowest_tier([qty.Tier.REPRODUCED, qty.Tier.PEER_REVIEWED]) is (
        qty.Tier.PEER_REVIEWED
    )
    with pytest.raises(ValueError, match="no input tiers"):
        qty.lowest_tier([])


def test_identifier_patterns(registry: SchemaRegistry) -> None:
    ok = {
        "systemId": "fake-broken", "configurationId": "default", "workloadId": "sash-l31-8b-c4096",
        "profileId": "prover-h100", "releaseId": "v0.1",
        "runId": "2026-11-20-fake-fake-tiny-ci-ci-cpu-1", "proofId": "req-0001.b1",
        "controlId": "C7", "digest": "sha256:" + "a" * 64, "commit": "0" * 40,
    }  # fmt: skip
    bad = {
        "systemId": "Sash", "workloadId": "ab", "profileId": "x", "releaseId": "0.1",
        "runId": "2026-11-20-fake-0", "proofId": "../x", "controlId": "C9",
        "digest": "sha256:abc", "commit": "eb95bfa",
    }  # fmt: skip
    for name, value in ok.items():
        assert not registry.errors("quantity/1", value, def_name=name), name  # type: ignore[arg-type]
    for name, value in bad.items():
        assert registry.errors("quantity/1", value, def_name=name), name  # type: ignore[arg-type]


def test_all_schema_examples(registry: SchemaRegistry) -> None:
    assert check_examples(ROOT / "schema", registry) == []
