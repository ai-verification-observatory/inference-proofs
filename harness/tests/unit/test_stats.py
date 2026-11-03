from pathlib import Path

import pytest

from iproofs.derive import FORMULAS, QuantityTree, insufficient_repetitions, measured, statistic
from iproofs.errors import IProofsError
from iproofs.quantity import NullReason, Scope, Unit, statistic_problems
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
FAILED = "results/v0.1/fake/2026-11-20-fake-fake-tiny-ci-ci-cpu-3/run.json#/failure"


def rep(i: int, value: float | None, reason: str | None = None) -> tuple[str, QuantityTree]:
    ref = f"results/v0.1/fake/2026-11-20-fake-fake-tiny-ci-ci-cpu-{i}/run.json#/metrics/rate"
    q = measured(value, Unit.TOKEN_PER_S, Scope.PROVE_STEADY, ref,
                 None if reason is None else NullReason(reason))  # fmt: skip
    return ref, q


def check(out: QuantityTree) -> None:
    def_name = "statistic" if "stats" in out else "quantity"
    assert REGISTRY.errors("quantity/1", out, def_name=def_name) == []
    assert statistic_problems(out) == []


def test_stat_failed() -> None:
    """TC-STAT-FAILED: RFC-0004 statistics fixture (not a result)."""
    out = statistic([rep(1, 100.0), rep(2, 110.0), rep(4, 90.0)], [FAILED], "0.1.0")
    assert out["stats"] == {"n": 3, "n_failed": 1, "mean": 100.0, "stdev": 10.0,
                            "min": 90.0, "max": 110.0}  # fmt: skip
    assert out["value"] == 100.0
    assert out["unit"] == "token/s"
    assert out["scope"] == "prove.steady"
    assert out["source"]["ref"] == "derive:D-STAT@0.1.0"  # type: ignore[index]
    check(out)


def test_stat_n1() -> None:
    """TC-STAT-N1: one repetition, stdev null."""
    out = statistic([rep(1, 7.0)], [FAILED, FAILED], "0.1.0")
    assert out["stats"]["stdev"] is None  # type: ignore[index]
    assert out["value"] == 7.0
    check(out)


def test_stat_n0_all_failed() -> None:
    out = statistic([], [FAILED] * 3, "0.1.0")
    assert out["value"] is None
    assert out["null_reason"] == "step_failed"
    assert out["stats"] == {"n": 0, "n_failed": 3, "mean": None, "stdev": None,
                            "min": None, "max": None}  # fmt: skip
    check(out)


def test_stat_n2() -> None:
    out = statistic([rep(1, 1.0), rep(2, 3.0)], [], "0.1.0")
    assert out["stats"]["stdev"] == pytest.approx(2**0.5)  # type: ignore[index]
    check(out)


def test_unobservable_in_every_repetition_keeps_its_reason() -> None:
    out = statistic([rep(i, None, "not_externally_observable") for i in (1, 2, 3)], [], "0.1.0")
    assert out["value"] is None
    assert out["null_reason"] == "not_externally_observable"
    assert "stats" not in out
    check(out)


def test_null_repetitions_left_out_of_n() -> None:
    out = statistic([rep(1, 4.0), rep(2, None, "missing_input"), rep(3, 6.0)], [], "0.1.0")
    assert out["stats"]["n"] == 2  # type: ignore[index]
    assert len(out["source"]["inputs"]) == 2  # type: ignore[index]
    check(out)


def test_mixed_units_rejected() -> None:
    ref, q = rep(2, 1.0)
    with pytest.raises(IProofsError, match="mixed units"):
        statistic([rep(1, 1.0), (ref, {**q, "unit": "s"})], [], "0.1.0")


def test_insufficient_repetitions() -> None:
    assert insufficient_repetitions(2)
    assert not insufficient_repetitions(3)


def test_formula_registry_records_statistics_choice() -> None:
    assert "statistics.mean" in FORMULAS["D-STAT"]
    assert "statistics.stdev" in FORMULAS["D-STAT"]


def test_no_repetition_at_all_is_internal_error() -> None:
    with pytest.raises(IProofsError, match="no repetition"):
        statistic([], [], "0.1.0")
