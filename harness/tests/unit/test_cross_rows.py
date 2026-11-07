"""RFC-0004 release rows: D-OVERHEAD-S, D-AGREE, D-PROVIDER-SPREAD, and RFC-0015 NM-1.

Every value here is a fixture value, not a result."""

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from iproofs.derive import agreement_rate, overhead, provider_spread
from iproofs.quantity import Scope, Tier
from iproofs.release import RunView, _Context, _release_rows
from iproofs.schema import SchemaRegistry

ROLES = {"ref-serve": "serve", "ref-recompute": "recompute"}
REGISTRY = SchemaRegistry.from_tree(Path(__file__).resolve().parents[3] / "schema")
WL = {"id": "sash-l31-8b-c1024", "version": 1}


def q(
    value: float | None, unit: str = "token/s", scope: str | None = "prove.steady"
) -> dict[str, object]:
    return {"value": value, "unit": unit, "scope": scope, "grade": "measured", "tier": "reported",
            "source": {"kind": "harness", "ref": "fixture"},
            "null_reason": None if value is not None else "step_failed"}  # fmt: skip


def test_overhead_prove_steady_worked_example() -> None:
    """D-OVERHEAD-prove.steady: 10,000 token/s served over 100 token/s proved gives 100."""
    out = overhead(("ref", q(10_000.0)), ("sys", q(100.0)), Scope.PROVE_STEADY, joined=True,
                   measurable=True, version="1")  # fmt: skip
    assert (out["value"], out["unit"], out["scope"], out["null_reason"]) == (
        100.0, "ratio", "prove.steady", None)  # fmt: skip
    assert out["source"]["inputs"] == ["ref", "sys"]  # type: ignore[index]


def test_overhead_mismatch_not_applicable() -> None:
    """TC-OVERHEAD-MISMATCH: rows that do not join give null with not_applicable."""
    out = overhead(("ref", q(10_000.0)), ("sys", q(100.0)), Scope.PROVE_STEADY, joined=False,
                   measurable=True, version="1")  # fmt: skip
    assert (out["value"], out["null_reason"]) == (None, "not_applicable")


def test_agreement_rate_hand_computed() -> None:
    """TC-AGREE-FIXTURE totals: 11 agreeing positions and 1 disagreeing give 11/12."""
    agree = [("a1", q(5.0, "count", None)), ("a2", q(6.0, "count", None))]
    disagree = [("d1", q(0.0, "count", None)), ("d2", q(1.0, "count", None))]
    out = agreement_rate(agree, disagree, measurable=True, version="1")
    assert out["value"] == 11 / 12
    assert agreement_rate([], [], measurable=True, version="1")["value"] is None  # none compared


def test_provider_spread_single_provider_null() -> None:
    one = provider_spread({"p1": [("r1", q(10.0)), ("r2", q(20.0))]}, Scope.PROVE_STEADY, "1")
    assert (one["value"], one["null_reason"]) == (None, "not_applicable")
    two = provider_spread({"p2": [("r3", q(30.0))], "p1": [("r1", q(10.0)), ("r2", q(20.0))]},
                          Scope.PROVE_STEADY, "1")  # fmt: skip
    assert two["value"] == 30.0 / 15.0  # provider means 15 and 30
    assert two["source"]["inputs"] == ["r1", "r2", "r3"]  # type: ignore[index]


def view(system: str, run_id: str, metrics: Mapping[str, object], *, failure: str | None = None,
         prompts_from: str | None = None, profile: str = "prover-h100") -> RunView:  # fmt: skip
    run: dict[str, object] = {"run_id": run_id, "system": system, "metrics": metrics,
           "status": "failed" if failure else "completed",
           "failure": {"kind": failure} if failure else None}  # fmt: skip
    manifest: dict[str, object] = {
        "provider": "p1",
        "prompts_from": prompts_from,
        "profile": {"prover": profile},
    }
    return RunView(Path("results/v0.1") / system / run_id, run, manifest, None)


def ctx(runs: list[RunView], stats: Mapping[str, object], profile: str = "prover-h100") -> _Context:
    where: dict[str, object] = {
        "system": str(runs[0].run["system"]),
        "workload": WL,
        "profile": profile,
    }
    return _Context(where, None, runs, {r.run_id: Tier.REPORTED for r in runs}, dict(stats))


def contexts(*, ref_profile: str = "prover-h100", ref_failure: str | None = None) -> list[_Context]:
    system = ctx([view("sash", "s-1", {"rate_prove.steady": q(100.0)})],
                 {"rate_prove.steady": q(100.0)})  # fmt: skip
    ref_run = view("ref-serve", "r-1", {} if ref_failure else {"rate_prove.steady": q(10_000.0)},
                   failure=ref_failure, profile=ref_profile)  # fmt: skip
    ref = ctx([ref_run], {"rate_prove.steady": q(None if ref_failure else 10_000.0)}, ref_profile)
    counts = {"agreement_positions": q(11.0, "count", None),
              "disagreement_positions": q(1.0, "count", None)}  # fmt: skip
    recompute = ctx([view("ref-recompute", "c-1", {} if ref_failure else counts,
                          failure=ref_failure, prompts_from="s-1")], {})  # fmt: skip
    return [system, ref, recompute]


def test_release_rows_join_and_agreement() -> None:
    found = contexts()
    _release_rows("v0.1", found, ROLES)
    stats = found[0].statistics
    assert stats["overhead_vs_serving_prove.steady"]["value"] == 100.0  # type: ignore[index]
    assert stats["overhead_vs_serving_prove.steady"]["source"]["inputs"] == [  # type: ignore[index]
        "releases/v0.1/index.json#/configurations/1/statistics/rate_prove.steady",
        "releases/v0.1/index.json#/configurations/0/statistics/rate_prove.steady",
    ]
    assert stats["agreement_rate"]["value"] == 11 / 12  # type: ignore[index]
    assert stats["provider_spread_prove.steady"]["null_reason"] == "not_applicable"  # type: ignore[index]
    assert "overhead_vs_serving_prove.steady" not in found[1].statistics  # reference rows: none


def test_release_rows_profile_mismatch() -> None:
    """TC-OVERHEAD-JOIN: a ref-serve row on another profile does not join."""
    found = contexts(ref_profile="prover-a100")
    _release_rows("v0.1", found, ROLES)
    out = found[0].statistics["overhead_vs_serving_prove.steady"]
    assert (out["value"], out["null_reason"]) == (None, "not_applicable")  # type: ignore[index]


@pytest.mark.parametrize("kind", ["resource", "adapter"])
def test_nm1_nulls_dependants(kind: str) -> None:
    """TC-NM-1: every reference attempt failed with resource or adapter."""
    found = contexts(ref_failure=kind)
    _release_rows("v0.1", found, ROLES)
    stats = found[0].statistics
    for metric in ("overhead_vs_serving_prove.steady", "agreement_rate"):
        assert stats[metric]["null_reason"] == "not_measurable_on_profile"  # type: ignore[index]
    # with no completed paired run, D-AGREE points at the failure records (quantity/1)
    assert stats["agreement_rate"]["source"]["inputs"] == [  # type: ignore[index]
        "results/v0.1/ref-recompute/c-1/run.json#/failure"
    ]
    agree = stats["agreement_rate"]
    assert isinstance(agree, dict)
    assert REGISTRY.errors("quantity/1", agree, def_name="quantity") == []


def test_agreement_all_paired_failed_other_kind() -> None:
    """Every paired run failed, not under NM-1: D-AGREE is null `step_failed` (INV-QTY-8)."""
    found = contexts(ref_failure="internal")
    _release_rows("v0.1", found, ROLES)
    out = found[0].statistics["agreement_rate"]
    assert (out["value"], out["null_reason"]) == (None, "step_failed")  # type: ignore[index]


def test_other_failure_is_not_nm1() -> None:
    found = contexts(ref_failure="internal")
    _release_rows("v0.1", found, ROLES)
    out = found[0].statistics["overhead_vs_serving_prove.steady"]
    assert out["null_reason"] == "step_failed"  # type: ignore[index]
    json.dumps(found[0].statistics)  # serialisable as written to index.json
