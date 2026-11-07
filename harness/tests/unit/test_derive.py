import json
import math
from pathlib import Path

import pytest

from iproofs.derive import (
    COMPUTE,
    FORMULAS,
    QuantityTree,
    derive_repetition,
    measured,
    scope_seconds,
)
from iproofs.errors import ErrorKind, IProofsError
from iproofs.quantity import NullReason, Scope, Unit
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "harness/tests/fixtures/derive/worked-example"
RUN = "results/v0.1/fake/2026-11-20-fake-fake-tiny-ci-ci-cpu-1/run.json"
NS = 1_000_000_000
UNITS = {
    "tokens_covered_total": Unit.TOKEN, "tokens_covered_steady": Unit.TOKEN,
    "requests_count": Unit.COUNT, "proof_bytes_total": Unit.B, "verify_seconds_total": Unit.S,
    "proofs_count": Unit.COUNT,
}  # fmt: skip


def q(name: str, value: float | None, reason: str | None = None) -> QuantityTree:
    scope = Scope.VERIFY if UNITS.get(name) is Unit.S else None
    return measured(value, UNITS.get(name, Unit.S), scope, f"{RUN}#/raw",
                    None if reason is None else NullReason(reason))  # fmt: skip


def asserted(value: float, unit: Unit, ref: str) -> QuantityTree:
    return {"value": value, "unit": str(unit), "scope": None, "grade": "asserted",
            "tier": "reported", "source": {"kind": "reference_file", "ref": ref},
            "null_reason": None}  # fmt: skip


def worked_example() -> tuple[dict[str, QuantityTree], dict[str, QuantityTree]]:
    inputs = json.loads((FIXTURE / "inputs.json").read_text())
    events = {k: round(v * NS) for k, v in inputs["events_s"].items()}
    releases = [round(r * NS) for r in inputs["releases_s"]]
    metrics: dict[str, QuantityTree] = {k: q(k, v) for k, v in inputs["metrics"].items()}
    metrics |= scope_seconds(events, releases, observable=True, run_json=RUN)
    out = derive(metrics, price=inputs["price_usd_per_gpu_hour"], gpus=inputs["gpus"],
                 params=inputs["active_parameters_per_token"])  # fmt: skip
    return metrics, out


def derive(
    metrics: dict[str, QuantityTree],
    *,
    price: float = 3.6,
    gpus: int = 1,
    params: float = 8e9,
    reference: bool = False,
) -> dict[str, QuantityTree]:
    price_ref = "reference/v0.1.yaml#/cost/price_per_gpu_hour_usd"
    params_ref = "workloads/x.yaml#/model/parameters/active_per_token"
    return derive_repetition(
        metrics,
        run_json=RUN,
        harness_version="0.1.0",
        gpus=gpus,
        price=(price_ref, asserted(price, Unit.USD_PER_GPU_HOUR, price_ref)),
        active_parameters=(params_ref, asserted(params, Unit.COUNT, params_ref)),
        first_proof_tokens=(f"{RUN}#/proofs/0/tokens_covered", q("tokens_covered_total", 1000)),
        reference=reference,
    )


def test_worked_example() -> None:
    """RFC-0004 §Worked example: every hand-computed value (test fixture, not a result)."""
    metrics, out = worked_example()
    expected = json.loads((FIXTURE / "expected.json").read_text())
    for name, want in expected.items():
        got = (metrics | out)[name]["value"]
        assert isinstance(got, float | int), name
        assert math.isclose(got, want, rel_tol=1e-12), (name, got, want)


def test_derived_labels() -> None:
    _, out = worked_example()
    rate = out["rate_prove.steady"]
    assert rate["unit"] == "token/s"
    assert rate["scope"] == "prove.steady"
    assert rate["grade"] == "derived"
    assert rate["tier"] == "reported"
    assert rate["source"] == {
        "kind": "derivation",
        "ref": "derive:D-RATE-S@0.1.0",
        "inputs": [f"{RUN}#/metrics/tokens_covered_steady", f"{RUN}#/metrics/prove_steady_seconds"],
    }


def test_outputs_are_schema_valid() -> None:
    registry = SchemaRegistry.from_tree(ROOT / "schema")
    _, out = worked_example()
    for name, value in out.items():
        assert registry.errors("quantity/1", value, def_name="quantity") == [], name


def test_null_div() -> None:
    """TC-NULL-DIV: zero tokens or zero seconds give null, never NaN, infinity or 0."""
    metrics, _ = worked_example()
    metrics["tokens_covered_total"] = q("tokens_covered_total", 0)
    out = derive(metrics)
    for name in ("rate_prove.session", "proof_bytes_per_token", "verify_seconds_per_token",
                 "commit_seconds_per_token_h1", "tokens_covered_per_proof"):  # fmt: skip
        assert out[name]["value"] is None, name
        assert out[name]["null_reason"] == "not_applicable", name


def test_null_input_reason_propagates() -> None:
    events = {"commit.start": 0, "prove.start": 1 * NS}
    metrics = scope_seconds(events, [2 * NS, 3 * NS], observable=False, run_json=RUN)
    metrics["tokens_covered_steady"] = q("tokens_covered_steady", 10)
    out = derive(metrics)
    assert out["rate_prove.steady"]["value"] is None
    assert out["rate_prove.steady"]["null_reason"] == "not_externally_observable"
    assert out["cost_per_1k_tokens_prove.steady"]["null_reason"] == "not_externally_observable"


def test_missing_input_is_missing_input() -> None:
    out = derive({})
    assert out["verify_seconds_per_token"]["null_reason"] == "missing_input"


def test_adapter_input_refused() -> None:
    """INV-GRADE-2: adapter-reported timings never feed a formula."""
    metrics, _ = worked_example()
    adapter = dict(metrics["verify_seconds_total"])
    adapter["source"] = {"kind": "adapter", "ref": f"{RUN}#/adapter_phases/verify"}
    metrics["verify_seconds_total"] = adapter
    with pytest.raises(IProofsError) as e:
        derive(metrics)
    assert e.value.kind is ErrorKind.INTERNAL


def test_quality_flags_are_or_of_inputs() -> None:
    """INV-QTY-9: a degraded input marks the derived value degraded."""
    metrics, _ = worked_example()
    metrics["proof_bytes_total"] = {**metrics["proof_bytes_total"], "quality": {"degraded": True}}
    out = derive(metrics)
    assert out["proof_bytes_per_token"]["quality"] == {"degraded": True}
    assert "quality" not in out["verify_seconds_per_token"]


def test_tier_is_lowest_input_tier() -> None:
    """INV-DERIVE-4."""
    metrics, _ = worked_example()
    metrics["tokens_covered_total"] = {**metrics["tokens_covered_total"], "tier": "reproduced"}
    metrics["proof_bytes_total"] = {**metrics["proof_bytes_total"], "tier": "peer-reviewed"}
    assert derive(metrics)["proof_bytes_per_token"]["tier"] == "peer-reviewed"


def test_tokens_covered_per_proof_worked_example() -> None:
    """TC-TPP-WORKED: RFC-0004 worked example D-TPP row, 5,000 / 5 = 1,000 token (fixture)."""
    _, out = worked_example()
    tpp = out["tokens_covered_per_proof"]
    assert isinstance(tpp["value"], float)
    assert math.isclose(tpp["value"], 1000.0, rel_tol=1e-12)
    assert (tpp["grade"], tpp["unit"], tpp["scope"], tpp["null_reason"]) == (
        "derived", "token", None, None
    )  # fmt: skip


def test_tokens_covered_per_proof_zero_is_null() -> None:
    """TC-TPP-ZERO: zero proofs, or zero tokens over 5 proofs, give null `not_applicable`."""
    metrics, _ = worked_example()
    for edit in ({"proofs_count": q("proofs_count", 0)},
                 {"tokens_covered_total": q("tokens_covered_total", 0)}):  # fmt: skip
        tpp = derive(metrics | edit)["tokens_covered_per_proof"]
        assert tpp["value"] is None, edit
        assert tpp["null_reason"] == "not_applicable", edit


def test_tokens_covered_per_proof_reference_is_null() -> None:
    """TC-TPP-REFERENCE: a `kind: reference` repetition (1 proof, 4,608 token; fixture values,
    not a result) gives null `not_applicable` (INV-DERIVE-6)."""
    metrics = {"proofs_count": q("proofs_count", 1),
               "tokens_covered_total": q("tokens_covered_total", 4608)}  # fmt: skip
    assert derive(metrics)["tokens_covered_per_proof"]["value"] == 4608.0  # control: a prover
    tpp = derive(metrics, reference=True)["tokens_covered_per_proof"]
    assert tpp["value"] is None
    assert tpp["null_reason"] == "not_applicable"


def test_tokens_covered_per_proof_source() -> None:
    """TC-TPP-SOURCE: formula id and inputs in order, tokens then proofs (INV-DERIVE-4)."""
    _, out = worked_example()
    assert out["tokens_covered_per_proof"]["source"] == {
        "kind": "derivation",
        "ref": "derive:D-TPP@0.1.0",
        "inputs": [f"{RUN}#/metrics/tokens_covered_total", f"{RUN}#/metrics/proofs_count"],
    }


def test_formula_registry_names_every_emitted_id() -> None:
    """INV-QTY-6: every formula id derive emits is in FORMULAS, so a page can name it."""
    _, out = worked_example()
    emitted = {str(v["source"]["ref"]).split(":")[1].split("@")[0] for v in out.values()}  # type: ignore[index]
    assert emitted | {"D-STAT", "D-OVERHEAD-S", "D-AGREE", "D-PROVIDER-SPREAD"} <= set(FORMULAS)
    assert set(COMPUTE) <= set(FORMULAS)
