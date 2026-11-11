import json
import math
from pathlib import Path

import pytest

from iproofs.derive import (
    COMPUTE,
    FORMULAS,
    Group,
    QuantityTree,
    derive_repetition,
    freeze_values,
    generation_seconds,
    later_group_seconds,
    measured,
    recompute,
    release_groups,
    scope_seconds,
    session_per_reply,
    steady_per_reply,
)
from iproofs.errors import ErrorKind, IProofsError
from iproofs.quantity import NullReason, Scope, Unit
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "harness/tests/fixtures/derive/worked-example"
RUN = "results/v0.1/fake/2026-11-20-fake-fake-tiny-ci-ci-cpu-1/run.json"
PARAMS_REF = f"{RUN}#/inputs/active_parameters_per_token"  # RFC-0003 WB-4: copied into run.json
BITS_REF = f"{RUN}#/inputs/weight_bits"
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
                 params=inputs["active_parameters_per_token"],
                 bits=inputs["weight_bits"])  # fmt: skip
    return metrics, out


def derive(
    metrics: dict[str, QuantityTree],
    *,
    price: float = 3.6,
    gpus: int = 1,
    params: float = 8e9,
    bits: float | None = 8.0,
    reference: bool = False,
) -> dict[str, QuantityTree]:
    price_ref = "reference/v0.1.yaml#/cost/price_per_gpu_hour_usd"
    return derive_repetition(
        metrics,
        run_json=RUN,
        harness_version="0.1.0",
        gpus=gpus,
        price=(price_ref, asserted(price, Unit.USD_PER_GPU_HOUR, price_ref)),
        active_parameters=(PARAMS_REF, asserted(params, Unit.COUNT, PARAMS_REF)),
        weight_bits=(
            BITS_REF,
            None if bits is None else asserted(bits, Unit.BIT_PER_WEIGHT, BITS_REF),
        ),
        first_proof_tokens=(f"{RUN}#/proofs/0/tokens_covered", q("tokens_covered_total", 1000)),
        reference=reference,
        gpu_count=(GPUS_REF, asserted(gpus, Unit.COUNT, GPUS_REF)),
    )


GPUS_REF = f"{RUN}#/inputs/gpu_count"


def test_gpu_seconds_per_token_x4() -> None:
    """TC-GSPT-WORKED and TC-GSPT-X4 (RFC-0004 INV-DERIVE-8): D-GSPT = D-SPT x gpus, 0.01 x 1
    on the worked example and 0.01 x 4 on a 4-GPU serving profile (fixture values); D-COST-1K
    reads the same `inputs.gpu_count` pointer, so 0.01 x 1,000 x 4 x 3.60 / 3,600 = 0.04."""
    metrics, out = worked_example()
    assert out["gpu_seconds_per_token_prove.steady"]["value"] == 0.01
    x4 = derive(dict(metrics), gpus=4)
    gspt = x4["gpu_seconds_per_token_prove.steady"]
    assert gspt["value"] == pytest.approx(0.04, rel=1e-12)
    assert (gspt["unit"], gspt["scope"], gspt["grade"]) == (
        "gpu_s/token",
        "prove.steady",
        "derived",
    )
    assert gspt["source"]["inputs"] == [f"{RUN}#/metrics/seconds_per_token_prove.steady", GPUS_REF]  # type: ignore[index]
    cost = x4["cost_per_1k_tokens_prove.steady"]
    assert cost["value"] == pytest.approx(0.04, rel=1e-12)
    assert cost["source"]["inputs"][2] == GPUS_REF  # type: ignore[index]
    spt = x4["seconds_per_token_prove.steady"]
    inputs = [(f"{RUN}#/metrics/seconds_per_token_prove.steady", spt),
              (GPUS_REF, asserted(4, Unit.COUNT, GPUS_REF))]  # fmt: skip
    assert recompute(gspt, inputs, 0) == gspt  # G4 recomputes it from its stored inputs


def test_gspt_without_gpu_count_is_absent() -> None:
    """A CPU-only test profile records no GPU count: no D-GSPT-S, and D-COST-1K-S keeps its
    two stored inputs and the profile's count (a run stored before 2026-11-09 recomputes so)."""
    metrics, _ = worked_example()
    out = derive_repetition(
        metrics, run_json=RUN, harness_version="0.1.0", gpus=2,
        price=("p", asserted(3.6, Unit.USD_PER_GPU_HOUR, "p")),
        active_parameters=(PARAMS_REF, asserted(8e9, Unit.COUNT, PARAMS_REF)),
        weight_bits=(BITS_REF, asserted(8.0, Unit.BIT_PER_WEIGHT, BITS_REF)),
        first_proof_tokens=("t", None),
    )  # fmt: skip
    assert not [k for k in out if k.startswith("gpu_seconds")]
    assert out["cost_per_1k_tokens_prove.steady"]["value"] == pytest.approx(0.02, rel=1e-12)
    source = out["cost_per_1k_tokens_prove.steady"]["source"]
    assert isinstance(source, dict)
    assert len(source["inputs"]) == 2


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


@pytest.mark.parametrize(("params", "bits"), [(0.0, 8.0), (8e9, 0.0)])
def test_null_div_active_weight_bits(params: float, bits: float) -> None:
    """TC-NULL-DIV for D-SPAB-S: zero parameters or zero weight bits (reachable through a G4
    recompute of an edited input) give null `not_applicable`, never infinity."""
    metrics, _ = worked_example()
    q = derive(metrics, params=params, bits=bits)[SPAB]
    assert (q["value"], q["null_reason"]) == (None, "not_applicable")


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
    assert emitted | {"D-STAT", "D-OVERHEAD-S", "D-OVERHEAD-HIGH-S", "D-AGREE",
                      "D-PROVIDER-SPREAD"} <= set(FORMULAS)  # fmt: skip
    assert set(COMPUTE) <= set(FORMULAS)


SPAB = "seconds_per_active_weight_bit_token_prove.steady"


def test_seconds_per_active_weight_bit_worked_example() -> None:
    """TC-SPAB-WORKED: RFC-0004 worked example D-SPAB row, 0.01 / (8.0e9 x 8) = 1.5625e-13
    s/bit_token (fixture values, not a result), with its labels."""
    _, out = worked_example()
    spab = out[SPAB]
    assert isinstance(spab["value"], float)
    assert math.isclose(spab["value"], 1.5625e-13, rel_tol=1e-12)
    assert (spab["grade"], spab["unit"], spab["scope"], spab["tier"], spab["null_reason"]) == (
        "derived", "s/bit_token", "prove.steady", "reported", None
    )  # fmt: skip


def test_seconds_per_active_weight_bit_source() -> None:
    """TC-SPAB-SOURCE: formula id and inputs in order: D-SPT-S, parameters, weight bits."""
    _, out = worked_example()
    assert out[SPAB]["source"] == {
        "kind": "derivation",
        "ref": "derive:D-SPAB-S@0.1.0",
        "inputs": [
            f"{RUN}#/metrics/seconds_per_token_prove.steady",
            PARAMS_REF,
            BITS_REF,
        ],
    }


def test_seconds_per_active_weight_bit_no_bits_is_missing_input() -> None:
    """TC-SPAB-NO-BITS: a workload record without weight bits gives null `missing_input`."""
    metrics, _ = worked_example()
    out = derive(metrics, bits=None)
    for scope in ("prove.steady", "prove.session", "whole_wall"):
        q = out[f"seconds_per_active_weight_bit_token_{scope}"]
        assert (q["value"], q["null_reason"]) == (None, "missing_input"), scope
    assert out["seconds_per_token_prove.steady"]["value"] is not None  # the time is still there


def test_seconds_per_active_weight_bit_recorded_null_bits() -> None:
    """TC-SPAB-NO-BITS as the runner records it: run.json `inputs.weight_bits` is a null
    asserted quantity with `missing_input` (RFC-0003 WB-3), which D-SPAB-S passes on."""
    metrics, _ = worked_example()
    null_bits = {**asserted(8.0, Unit.BIT_PER_WEIGHT, BITS_REF), "value": None,
                 "null_reason": "missing_input"}  # fmt: skip
    out = derive_repetition(
        metrics, run_json=RUN, harness_version="0.1.0", gpus=1, price=("p", None),
        active_parameters=(PARAMS_REF, asserted(8e9, Unit.COUNT, PARAMS_REF)),
        weight_bits=(BITS_REF, null_bits), first_proof_tokens=("t", None),
    )  # fmt: skip
    assert (out[SPAB]["value"], out[SPAB]["null_reason"]) == (None, "missing_input")


def test_freeze_values_fill_only_missing_keys() -> None:
    """RFC-0004 Q3: for a run stored before D-TPP and D-SPAB-S, the freeze evaluates exactly
    those keys from its recorded metrics; a key the run already holds is left alone."""
    metrics, out = worked_example()
    stored = {
        **metrics,
        **{k: v for k, v in out.items() if k.startswith(("rate_", "seconds_per_t"))},
    }
    late = freeze_values(
        stored, run_json=RUN, harness_version="0.1.0",
        active_parameters=(PARAMS_REF, asserted(8e9, Unit.COUNT, PARAMS_REF)),
        weight_bits=(BITS_REF, asserted(8.0, Unit.BIT_PER_WEIGHT, BITS_REF)), reference=False,
    )  # fmt: skip
    spab = [f"seconds_per_active_weight_bit_token_{s}" for s in ("prove.steady", "prove.session",
                                                                   "whole_wall")]  # fmt: skip
    per_bit = ["proof_bytes_per_active_weight_bit_token",
               "verify_seconds_per_active_weight_bit_token"]  # fmt: skip
    # RFC-0017: the per-request figures too; cost needs the stored D-COST-1K-S, absent here,
    # and no GPU count is given, so there is no D-GSPR-S
    cost = [f"cost_per_request_{s}" for s in ("prove.steady", "prove.session", "whole_wall")]
    per_request = ["tokens_covered_per_request", "proof_bytes_per_request",
                   "verify_seconds_per_request"]  # fmt: skip
    assert sorted(late) == sorted([*spab, *per_bit, *cost, *per_request,
                                   "tokens_covered_per_proof"])  # fmt: skip
    assert [late[n]["value"] for n in per_request] == [1000, 2000000, 5]
    for name in cost:
        assert (late[name]["value"], late[name]["null_reason"]) == (None, "missing_input")
    for name in per_bit:  # their D-BPT and D-VSPT inputs are not in this stored run
        assert (late[name]["value"], late[name]["null_reason"]) == (None, "missing_input")
    assert late[SPAB]["source"]["inputs"][0] == f"{RUN}#/metrics/seconds_per_token_prove.steady"  # type: ignore[index]
    assert math.isclose(late[SPAB]["value"], 1.5625e-13, rel_tol=1e-12)  # type: ignore[arg-type]
    assert late["tokens_covered_per_proof"]["value"] == 1000
    held = {**stored, "tokens_covered_per_proof": out["tokens_covered_per_proof"]}
    assert "tokens_covered_per_proof" not in freeze_values(
        held, run_json=RUN, harness_version="0.1.0", active_parameters=(PARAMS_REF, None),
        weight_bits=(BITS_REF, None), reference=False,
    )  # fmt: skip


def test_seconds_per_active_weight_bit_reference_is_null() -> None:
    """TC-SPAB-REFERENCE: a `kind: reference` row gives null `not_applicable` (INV-DERIVE-7)."""
    metrics, _ = worked_example()
    q = derive(metrics, reference=True)[SPAB]
    assert (q["value"], q["null_reason"]) == (None, "not_applicable")


def test_seconds_per_active_weight_bit_follows_steady_null() -> None:
    """TC-SPAB-NULL: a null D-SPT-S passes its own reason on (k = 1: fewer_than_two_proofs)."""
    events = {"commit.start": 0, "prove.start": 1 * NS}
    metrics = scope_seconds(events, [2 * NS], observable=True, run_json=RUN)
    metrics["tokens_covered_steady"] = q("tokens_covered_steady", 0)
    assert derive(metrics)[SPAB]["null_reason"] == "fewer_than_two_proofs"


BPAB = "proof_bytes_per_active_weight_bit_token"
VSPAB = "verify_seconds_per_active_weight_bit_token"


def per_bit_case(
    proofs: int,
    tokens_per_proof: int,
    bytes_per_proof: float,
    verify_per_proof: float,
    params: float,
    bits: float,
) -> dict[str, QuantityTree]:
    """One repetition's recorded totals (fixture values, not a result), derived."""
    metrics = {
        "proofs_count": q("proofs_count", proofs),
        "tokens_covered_total": q("tokens_covered_total", proofs * tokens_per_proof),
        "proof_bytes_total": q("proof_bytes_total", proofs * bytes_per_proof),
        "verify_seconds_total": q("verify_seconds_total", proofs * verify_per_proof),
    }
    return derive(metrics, params=params, bits=bits)


def test_per_bit_proof_size_and_check_time_flashprove_like() -> None:
    """TC-BPAB-WORKED, TC-VSPAB-WORKED, a FlashProve-like case (fixture values, not a result):
    120 proofs of 1,024 positions each, 17,408,000 B and 17.408 s to check per proof, 17e9
    active parameters at 4 bits, so 6.8e10 bits of active weights per token.
    D-BPT = 120 x 17,408,000 / (120 x 1,024) = 17,000 B/token;
    D-BPAB = 17,000 / 6.8e10 = 2.5e-7 B/bit_token (250 B per token per Gbit).
    D-VSPT = 120 x 17.408 / (120 x 1,024) = 0.017 s/token;
    D-VSPAB = 0.017 / 6.8e10 = 2.5e-13 s/bit_token (0.25 ms per token per Gbit)."""
    out = per_bit_case(120, 1024, 17_408_000, 17.408, 17e9, 4.0)
    assert math.isclose(out["proof_bytes_per_token"]["value"], 17_000, rel_tol=1e-12)  # type: ignore[arg-type]
    assert math.isclose(out[BPAB]["value"], 2.5e-7, rel_tol=1e-12)  # type: ignore[arg-type]
    assert math.isclose(out[VSPAB]["value"], 2.5e-13, rel_tol=1e-12)  # type: ignore[arg-type]
    assert (out[BPAB]["unit"], out[BPAB]["scope"], out[BPAB]["grade"]) == (
        "B/bit_token", None, "derived")  # fmt: skip
    assert (out[VSPAB]["unit"], out[VSPAB]["scope"], out[VSPAB]["grade"]) == (
        "s/bit_token", "verify", "derived")  # fmt: skip
    assert out[BPAB]["source"] == {
        "kind": "derivation",
        "ref": "derive:D-BPAB@0.1.0",
        "inputs": [f"{RUN}#/metrics/proof_bytes_per_token", PARAMS_REF, BITS_REF],
    }
    assert out[VSPAB]["source"]["inputs"] == [  # type: ignore[index]
        f"{RUN}#/metrics/verify_seconds_per_token", PARAMS_REF, BITS_REF]  # fmt: skip


def test_per_bit_proof_size_and_check_time_sash_like() -> None:
    """TC-BPAB-WORKED, TC-VSPAB-WORKED, a SASH-like case (fixture values, not a result): one
    proof of 1,088 positions (1,024 prompt and 64 output), 43,520,000,000 B and 3,481.6 s to
    check, 8e9 active parameters at 8 bits, so 6.4e10 bits of active weights per token.
    D-BPT = 43,520,000,000 / 1,088 = 40,000,000 B/token;
    D-BPAB = 40,000,000 / 6.4e10 = 6.25e-4 B/bit_token (625 kB per token per Gbit).
    D-VSPT = 3,481.6 / 1,088 = 3.2 s/token;
    D-VSPAB = 3.2 / 6.4e10 = 5e-11 s/bit_token (50 ms per token per Gbit)."""
    out = per_bit_case(1, 1088, 43_520_000_000, 3481.6, 8e9, 8.0)
    assert math.isclose(out["verify_seconds_per_token"]["value"], 3.2, rel_tol=1e-12)  # type: ignore[arg-type]
    assert math.isclose(out[BPAB]["value"], 6.25e-4, rel_tol=1e-12)  # type: ignore[arg-type]
    assert math.isclose(out[VSPAB]["value"], 5e-11, rel_tol=1e-12)  # type: ignore[arg-type]


def test_per_bit_proof_size_and_check_time_nulls() -> None:
    """No weight bits: both null `missing_input`; a reference row: both null `not_applicable`."""
    metrics = {"proofs_count": q("proofs_count", 1),
               "tokens_covered_total": q("tokens_covered_total", 1000),
               "proof_bytes_total": q("proof_bytes_total", 1e6),
               "verify_seconds_total": q("verify_seconds_total", 1.0)}  # fmt: skip
    for kw, reason in (({"bits": None}, "missing_input"), ({"reference": True}, "not_applicable")):
        out = derive(metrics, **kw)
        for name in (BPAB, VSPAB):
            assert (out[name]["value"], out[name]["null_reason"]) == (None, reason), (name, kw)


# ---------------------------------------------------------------- RFC-0018 CO-1 to CO-3

GROUPS_FIXTURE = ROOT / "harness/tests/fixtures/derive/release-groups/releases.json"
STEADY = {"steady": {"group_gap_s": 1.0, "min_later_groups": 3, "tolerance": 0.05}}


def test_release_groups_v01_flashprove() -> None:
    """CO-6: five groups of 24, later per-reply times 7.116, 7.136, 7.141, 7.119 s, m = 7.128
    GPU-seconds per reply on one GPU (v0.1 published 5.746)."""
    doc = json.loads(GROUPS_FIXTURE.read_text())
    times = [p["release_mono_ns"] for p in doc["proofs"]]
    groups = release_groups(times, 1.0)
    assert [g.size for g in groups] == [24] * 5
    per_reply = [round(x, 3) for x in later_group_seconds(groups)]
    assert per_reply == [7.116, 7.136, 7.141, 7.119]
    m, cause = steady_per_reply(groups, doc["gpu_count"], STEADY)
    assert cause is None
    assert m is not None
    assert f"{m:.4g}" == "7.128"
    session = session_per_reply(doc["events"]["commit.start"], times, 120, doc["gpu_count"])
    assert math.isclose(session, (max(times) - doc["events"]["commit.start"]) / 1e9 / 120)


def groups_at(*spec: tuple[float, int]) -> list[Group]:
    """Groups released at the given seconds with the given sizes, 1 ms apart inside a group."""
    times = [int(t * NS) + i * 1_000_000 for t, n in spec for i in range(n)]
    return release_groups(times, 1.0)


def test_three_groups_is_not_steady() -> None:
    """Two later groups are fewer than `min_later_groups` (3): no steady state."""
    groups = groups_at((0, 4), (10, 4), (20, 4))
    assert len(groups) == 3
    assert steady_per_reply(groups, 1, STEADY) == (None, "too few groups")


def test_three_later_groups_of_uneven_size_is_not_steady() -> None:
    """Later groups of 4, 2 and 4 replies, 10 s apart: 2.5, 5.0 and 2.5 s per reply; the 5.0
    lies 100 % from the median 2.5, over the 5 % tolerance."""
    groups = groups_at((0, 4), (10, 4), (20, 2), (30, 4))
    assert steady_per_reply(groups, 1, STEADY) == (None, "uneven groups")


def test_steady_hand_case() -> None:
    """Groups of 2, 4, 4, 4 at 0, 10, 20, 30 s (last release of each 1 or 3 ms later) on two
    GPUs: m = (t_4 - t_1) x 2 / 12 = (30.003 - 0.001) x 2 / 12 s."""
    groups = groups_at((0, 2), (10, 4), (20, 4), (30, 4))
    m, cause = steady_per_reply(groups, 2, STEADY)
    assert cause is None
    assert m is not None
    assert math.isclose(m, (30.003 - 0.001) * 2 / 12, rel_tol=1e-12)


def test_group_gap_is_inclusive() -> None:
    """A release exactly `gap_s` after the previous one joins its group; just over starts one."""
    assert [g.size for g in release_groups([0, NS], 1.0)] == [2]
    assert [g.size for g in release_groups([0, NS + 1], 1.0)] == [1, 1]


def test_generation_phase_adds_to_m() -> None:
    """CO-3: groups of 2, 4, 4, 4 at 0, 10, 20, 30 s on two GPUs plus a 60 s generation phase:
    m = (30.003 - 0.001) x 2 / 12 + 60 x 2 / 14."""
    groups = groups_at((0, 2), (10, 4), (20, 4), (30, 4))
    marks = [{"name": "generation.start", "mono_ns": 5 * NS},
             {"name": "generation.end", "mono_ns": 65 * NS}]  # fmt: skip
    seconds, missing = generation_seconds(marks)
    assert (seconds, missing) == (60.0, None)
    m, cause = steady_per_reply(groups, 2, STEADY, seconds)
    assert cause is None
    assert m is not None
    assert math.isclose(m, (30.003 - 0.001) * 2 / 12 + 60 * 2 / 14, rel_tol=1e-12)
    assert generation_seconds(None) == (None, None)
    assert generation_seconds(marks[:1]) == (None, "missing generation mark")
