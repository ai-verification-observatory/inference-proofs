"""RFC-0004 release rows: D-OVERHEAD-S, D-OVERHEAD-HIGH-S and D-OVERHEAD-WARM in GPU-seconds
per token (INV-DERIVE-2, -8, -9, -11), D-AGREE and D-PROVIDER-SPREAD.

Every value here is a fixture value, not a result."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from iproofs.derive import FORMULAS, agreement_rate, overhead, overhead_formula, provider_spread
from iproofs.model import Workload, load
from iproofs.quantity import NullReason, Scope
from iproofs.release import WARM, RunView, _Context, _release_rows, headline_scope
from iproofs.schema import SchemaRegistry

ROLES = {"ref-serve": "serve", "ref-recompute": "recompute"}
ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
WL = {"id": "fp-maverick-w1024-b24", "version": 1}
DIGEST = "sha256:" + "d" * 64
IMAGE = "docker.io/vllm/vllm-openai@sha256:" + "c" * 64
COMMIT = "5df63a7203cdb9328d824a27b682e77c7b9928be"
GSPT = "gpu_seconds_per_token_prove.steady"
SESSION = "gpu_seconds_per_token_prove.session"


def q(
    value: float | None, unit: str = "token/s", scope: str | None = "prove.steady"
) -> dict[str, object]:
    return {"value": value, "unit": unit, "scope": scope, "grade": "measured", "tier": "reported",
            "source": {"kind": "harness", "ref": "fixture"},
            "null_reason": None if value is not None else "step_failed"}  # fmt: skip


def test_agreement_rate_hand_computed() -> None:
    """TC-AGREE-FIXTURE totals: 11 agreeing positions and 1 disagreeing give 11/12."""
    agree = [("a1", q(5.0, "count", None)), ("a2", q(6.0, "count", None))]
    disagree = [("d1", q(0.0, "count", None)), ("d2", q(1.0, "count", None))]
    out = agreement_rate(agree, disagree, version="1")
    assert out["value"] == 11 / 12
    assert agreement_rate([], [], version="1")["value"] is None  # none compared


def test_provider_spread_single_provider_null() -> None:
    one = provider_spread({"p1": [("r1", q(10.0)), ("r2", q(20.0))]}, Scope.PROVE_STEADY, "1")
    assert (one["value"], one["null_reason"]) == (None, "not_applicable")
    two = provider_spread({"p2": [("r3", q(30.0))], "p1": [("r1", q(10.0)), ("r2", q(20.0))]},
                          Scope.PROVE_STEADY, "1")  # fmt: skip
    assert two["value"] == 30.0 / 15.0  # provider means 15 and 30
    assert two["source"]["inputs"] == ["r1", "r2", "r3"]  # type: ignore[index]


def gspt(value: float | None, reason: str | None = None) -> dict[str, object]:
    """A repetition's `gpu_seconds_per_token_prove.steady` (fixture value)."""
    out = q(value, "gpu_s/token")
    if value is None:
        out["null_reason"] = reason or "step_failed"
    return out


def test_overhead_worked_example() -> None:
    """TC-GSPT-WORKED and the worked example's overhead rows: system 0.01 s/token on 1 GPU is
    0.01 gpu_s/token; serving 40,000 token/s on 4 GPUs is 0.000025 x 4 = 0.0001 gpu_s/token,
    so D-OVERHEAD-prove.steady is 100; at high load 80,000 token/s gives 0.00005 and 200."""
    matched = overhead([("sys", gspt(0.01))], [("srv", gspt(0.000025 * 4))], Scope.PROVE_STEADY,
                       version="1")  # fmt: skip
    assert matched["value"] == pytest.approx(100.0, rel=1e-12)
    assert (matched["unit"], matched["scope"], matched["null_reason"]) == (
        "ratio", "prove.steady", None)  # fmt: skip
    assert matched["source"]["inputs"] == ["sys", "srv"]  # type: ignore[index]
    assert matched["source"]["ref"] == "derive:D-OVERHEAD-S@1"  # type: ignore[index]
    high = overhead([("sys", gspt(0.01))], [("srv", gspt(0.00005))], Scope.PROVE_STEADY,
                    high=True, version="1")  # fmt: skip
    assert high["value"] == pytest.approx(200.0, rel=1e-12)
    assert high["source"]["ref"] == "derive:D-OVERHEAD-HIGH-S@1"  # type: ignore[index]
    assert REGISTRY.errors("quantity/1", matched, def_name="quantity") == []


def test_overhead_gspt_pairs() -> None:
    """TC-OVERHEAD-GSPT: three system and three serving repetitions (fixture values). Means
    0.02 and 0.0002 give 100; the pair range is 0.018 / 0.00025 = 72 to 0.022 / 0.00015 =
    146.66..."""
    system = [(f"s{i}", gspt(v)) for i, v in enumerate((0.018, 0.020, 0.022))]
    serve = [(f"v{i}", gspt(v)) for i, v in enumerate((0.00015, 0.0002, 0.00025))]
    out = overhead(system, serve, Scope.PROVE_STEADY, version="1")
    assert out["value"] == pytest.approx(0.02 / 0.0002, rel=1e-12)
    pairs = out["pairs"]
    assert isinstance(pairs, dict)
    assert (pairs["n_system"], pairs["n_serving"]) == (3, 3)
    assert pairs["min"] == pytest.approx(0.018 / 0.00025, rel=1e-12)
    assert pairs["max"] == pytest.approx(0.022 / 0.00015, rel=1e-12)
    assert REGISTRY.errors("quantity/1", out, def_name="quantity") == []


def test_overhead_sash_reason_first() -> None:
    """TC-OVERHEAD-SASH: a system steady null `not_externally_observable` passes that reason
    on, whatever the serving side."""
    sash = [("s", gspt(None, "not_externally_observable"))]
    for reason in (None, NullReason.MISSING_INPUT, NullReason.NOT_APPLICABLE):
        out = overhead(sash, [("v", gspt(0.0001))], Scope.PROVE_STEADY, reason=reason,
                       version="1")  # fmt: skip
        assert (out["value"], out["null_reason"]) == (None, "not_externally_observable")
        assert out["pairs"] == {"n_system": 0, "n_serving": 1, "min": None, "max": None}


def view(system: str, run_id: str, metrics: Mapping[str, object], *, failure: str | None = None,  # noqa: PLR0913
         prompts_from: str | None = None, profile: str = "prover-h200-hosted",
         digest: str = DIGEST, image: str = IMAGE, warnings: tuple[str, ...] = (),
         rule: str | None = "batch-membership", sizing: bool = False) -> RunView:  # fmt: skip
    failed = {"kind": failure, "last_lines": []} if failure else None
    run: dict[str, object] = {"run_id": run_id, "system": system, "metrics": metrics,
           "status": "failed" if failure else "completed", "profile": profile,
           "failure": failed, "warnings": list(warnings)}  # fmt: skip
    workload: dict[str, object] = {} if rule is None else {"steady_rule": rule}
    manifest: dict[str, object] = {
        "provider": "p1",
        "prompts_from": prompts_from,
        "profile": {"prover": profile},
        "workload": workload,
    }
    if system == "ref-serve":
        manifest["serving_model"] = {"digest": digest}
        manifest["engine"] = {"image": image, "interface": "vllm serve",
                              "observed": {"version": "0.32.0", "build_commit": COMMIT,
                                           "max_num_batched_tokens": 8192}}  # fmt: skip
        workload |= {"prompt_count_run": 120, "batches_per_session_run": 5}
        if sizing:  # RFC-0015 SRV-1: a sizing capture
            workload["sizing_capture"] = True
    return RunView(Path("results/v0.1") / system / run_id, run, manifest, None)


def ctx(runs: list[RunView], profile: str = "prover-h200-hosted",
        load_point: str | None = None) -> _Context:  # fmt: skip
    where: dict[str, object] = {
        "system": str(runs[0].run["system"]),
        "workload": WL,
        "profile": profile,
    }
    stats: dict[str, object] = {}
    return _Context(where, None, runs, stats, None, load_point, {})


class Profile:
    def __init__(self, count: int, pairs: tuple[str, ...] = ()) -> None:
        self.gpu = type("Gpu", (), {"count": count, "model": "NVIDIA H200"})()
        self.pairs_with = pairs


class FakeServing:
    """The release-commit facts the join reads (iproofs.release._Serving), as fixtures."""

    def __init__(self, digest: str = DIGEST, image: str = IMAGE) -> None:
        self.digest, self.image = digest, image
        self.profiles = {"prover-h200-hosted": Profile(1), "prover-h100-hosted": Profile(1),
                         "serving-h200x2-hosted": Profile(2, ("prover-h200-hosted",)),
                         "serving-h200x4-hosted": Profile(4, ("prover-h200-hosted",)),
                         "serving-h200x8-hosted": Profile(8, ("prover-h200-hosted",)),
                         "serving-h200x4": Profile(4, ("prover-h200",))}  # fmt: skip

    def named(self, workload: str) -> str | None:
        return "ref-serve"

    def system(self, name: str) -> dict[str, object]:
        args = ["--tensor-parallel-size", "4", "--max-model-len", "1025"]
        entries = [{"id": WL["id"], "load_point": "matched", "gpus": 4,
                    "engine_args": [*args, "--max-num-seqs", "24"]},
                   {"id": WL["id"], "load_point": "high", "gpus": 4,
                    "engine_args": args}]  # fmt: skip
        return {"engine": {"name": "vllm", "version": "0.32.0", "image": self.image,
                           "commit": COMMIT}, "workloads": entries}  # fmt: skip

    def record(self, workload: str) -> object:
        model = type("M", (), {"digest": self.digest})()
        precision = type("P", (), {"name": "FP8", "release_statement": "not stated"})()
        publisher = type("U", (), {"name": "Meta"})()
        return type("R", (), {"model": model, "id": "r", "version": 1, "precision": precision,
                              "publisher": publisher})()  # fmt: skip

    def pairs(self, serving_profile: object, system_profile: object) -> bool:
        return str(system_profile) in self.profiles[str(serving_profile)].pairs_with

    def gpus(self, profile: object) -> int:
        return int(self.profiles[str(profile)].gpu.count)

    def gpu_model(self, profile: object) -> str:
        return "NVIDIA H200"

    def runtime(self, profile: object) -> str:
        return "hosted" if "hosted" in str(profile) else "docker host"

    def workload(self, workload: str) -> Workload:
        doc = load(ROOT / f"workloads/{workload}.yaml", REGISTRY)
        assert isinstance(doc, Workload)
        return doc


def system_ctx(values: tuple[float, ...] = (0.01,), rule: str | None = "batch-membership",
               ) -> _Context:  # fmt: skip
    runs = [view("flashprove", f"s-{i}", {GSPT: gspt(v)}, rule=rule) for i, v in enumerate(values)]
    return ctx(runs)


def serve_ctx(prefix: str, values: tuple[float | None, ...], *, profile: str =
              "serving-h200x4-hosted", load_point: str = "matched", source: str = "s-0",
              failure: str | None = None, **keys: Any) -> _Context:  # fmt: skip
    runs = [view("ref-serve", f"{prefix}-{i}", {} if v is None else {GSPT: gspt(v)},
                 failure=failure if v is None else None, prompts_from=source, profile=profile,
                 **keys) for i, v in enumerate(values)]  # fmt: skip
    return ctx(runs, profile, load_point)


def join(found: list[_Context], serving: FakeServing | None = None) -> dict[str, object]:
    _release_rows("v0.1", found, ROLES, serving or FakeServing())  # type: ignore[arg-type]
    return found[0].statistics


def test_release_join_matched_and_high() -> None:
    """The matched row gives D-OVERHEAD-S and the high row D-OVERHEAD-HIGH-S, with inputs at
    the repetitions' gpu_seconds_per_token, and the conditions block on the system row."""
    found = [system_ctx(), serve_ctx("m", (0.0001,)),
             serve_ctx("h", (0.00005,), load_point="high")]  # fmt: skip
    stats = join(found)
    matched = stats["overhead_vs_production_prove.steady"]
    high = stats["overhead_vs_production_high_prove.steady"]
    assert isinstance(matched, dict)
    assert isinstance(high, dict)
    assert matched["value"] == pytest.approx(100.0, rel=1e-12)
    assert high["value"] == pytest.approx(200.0, rel=1e-12)
    assert matched["source"]["inputs"] == [
        "results/v0.1/flashprove/s-0/run.json#/metrics/gpu_seconds_per_token_prove.steady",
        "results/v0.1/ref-serve/m-0/run.json#/metrics/gpu_seconds_per_token_prove.steady",
    ]
    assert "overhead_vs_production_prove.steady" not in found[1].statistics
    entry = found[0].entry
    assert entry is not None
    conditions = entry["overhead_conditions"]
    assert isinstance(conditions, dict)
    assert conditions["serving_configuration"] == "releases/v0.1/index.json#/configurations/1"
    assert conditions["high_configuration"] == "releases/v0.1/index.json#/configurations/2"
    assert conditions["n"] == {"system": 1, "serving_matched": 1, "serving_high": 1}
    assert conditions["gpus"] == {"system": 1, "serving": 4, "serving_high": 4}
    engine = conditions["engine"]
    assert engine["settings"] == ("engine defaults except --tensor-parallel-size 4, "
                                  "--max-model-len 1025, --max-num-seqs 24")  # fmt: skip
    assert engine["settings_high"] == ("engine defaults except --tensor-parallel-size 4, "
                                       "--max-model-len 1025")  # fmt: skip
    assert engine["max_num_batched_tokens"] == {"matched": 8192, "high": 8192}
    assert (conditions["runtime"], conditions["proved_precision"]) == ("hosted", "UD-Q4_K_XL")
    assert conditions["batch"]["matched"] == 24
    json.dumps(found[0].statistics)


def test_overhead_pair_profile() -> None:
    """TC-OVERHEAD-PAIR-PROFILE: a serving row whose profile does not pair (another GPU, or a
    docker serving profile against a hosted prover row) gives not_applicable."""
    for profile in ("prover-h100-hosted", "serving-h200x4"):
        stats = join([system_ctx(), serve_ctx("m", (0.0001,), profile=profile)])
        out = stats["overhead_vs_production_prove.steady"]
        assert (out["value"], out["null_reason"]) == (None, "not_applicable")  # type: ignore[index]


def overhead_of(found: list[_Context], key: str = "overhead_vs_production_prove.steady",
                ) -> tuple[object, object]:  # fmt: skip
    out = join(found)[key]
    assert isinstance(out, dict)
    return out["value"], out["null_reason"]


def test_overhead_fewest() -> None:
    """TC-OVERHEAD-FEWEST: TP4 with one paired success and two resource failures, TP8 with
    three successes: TP4 joins, so the mean is TP4's."""
    tp4 = serve_ctx("a", (0.0001, None, None), failure="resource")
    tp8 = serve_ctx("b", (0.0004, 0.0004, 0.0004), profile="serving-h200x8-hosted")
    stats = join([system_ctx(), tp8, tp4])
    assert stats["overhead_vs_production_prove.steady"]["value"] == pytest.approx(100.0)  # type: ignore[index]


def test_overhead_smallest_joinable_count() -> None:
    """The matched join takes the smallest GPU count with a joinable run; failed attempts at a
    smaller count neither block nor admit a larger one."""
    tp8 = serve_ctx("b", (0.0004,), profile="serving-h200x8-hosted")
    assert overhead_of([system_ctx(), tp8]) == (pytest.approx(25.0), None)
    failed = serve_ctx("a", (None, None), failure="adapter")
    assert overhead_of([system_ctx(), failed, tp8]) == (pytest.approx(25.0), None)
    smaller = serve_ctx("d", (0.0002,), profile="serving-h200x2-hosted")
    assert overhead_of([system_ctx(), smaller, tp8]) == (pytest.approx(50.0), None)


def test_overhead_short_steady_and_rule() -> None:
    """SRV-1: a serving run whose steady scope lasts under 60 s joins no overhead; INV-SCOPE-5:
    neither does a run at batch size above 1 recorded without the batch-membership rule, on
    either side (the system side gives not_applicable)."""
    short = serve_ctx("m", (0.0001,), warnings=("steady scope under 60 s",))
    assert overhead_of([system_ctx(), short]) == (None, "missing_input")
    old = serve_ctx("m", (0.0001,), rule=None)
    assert overhead_of([system_ctx(), old]) == (None, "missing_input")
    before = system_ctx(rule=None)
    assert overhead_of([before, serve_ctx("m", (0.0001,))]) == (None, "not_applicable")


def test_overhead_high_same_placement() -> None:
    """The high load joins only at the matched load's profile and GPU count."""
    found = [system_ctx(), serve_ctx("m", (0.0001,)),
             serve_ctx("h", (0.00005,), load_point="high",
                       profile="serving-h200x8-hosted")]  # fmt: skip
    high = "overhead_vs_production_high_prove.steady"
    assert overhead_of(found, high) == (None, "not_applicable")
    assert overhead_of([system_ctx(), serve_ctx("m", (0.0001,))], high) == (None, "missing_input")


def test_overhead_prompts_pairing() -> None:
    """TC-OVERHEAD-PROMPTS: serving runs that replay another system's runs do not enter the
    mean; none paired gives missing_input."""
    stats = join([system_ctx(), serve_ctx("m", (0.0001,), source="other-run")])
    out = stats["overhead_vs_production_prove.steady"]
    assert (out["value"], out["null_reason"]) == (None, "missing_input")  # type: ignore[index]
    stats = join([system_ctx()])  # no serving configuration at all
    assert stats["overhead_vs_production_prove.steady"]["null_reason"] == "missing_input"  # type: ignore[index]


def test_overhead_failed_serving() -> None:
    """Serving attempts that all failed leave the overhead null `missing_input`."""
    for kind in ("resource", "adapter"):
        failed = serve_ctx("m", (None, None), failure=kind)
        assert overhead_of([system_ctx(), failed]) == (None, "missing_input")


def test_overhead_digest() -> None:
    """TC-OVERHEAD-DIGEST: another model digest or another engine image gives not_applicable;
    a run under another record version with the same digest joins (the join keys on digests)."""
    other_model = serve_ctx("m", (0.0001,), digest="sha256:" + "e" * 64)
    out = join([system_ctx(), other_model])["overhead_vs_production_prove.steady"]
    assert out["null_reason"] == "not_applicable"  # type: ignore[index]
    other_engine = serve_ctx("m", (0.0001,), image="docker.io/vllm/vllm-openai@sha256:" + "f" * 64)
    out = join([system_ctx(), other_engine])["overhead_vs_production_prove.steady"]
    assert out["null_reason"] == "not_applicable"  # type: ignore[index]
    same = join([system_ctx(), serve_ctx("m", (0.0001,))])["overhead_vs_production_prove.steady"]
    assert same["value"] == pytest.approx(100.0)  # type: ignore[index]


def test_steady_overheads_only_and_ci_absent() -> None:
    """Only the steady overheads (and the warm one for a system without a steady scope) are
    computed; a workload that names no serve-role system has none."""
    sys = with_session(system_ctx(), (0.02,))
    stats = join([sys, with_session(serve_ctx("m", (0.0001,)), (0.0004,))])
    found = sorted(k for k in stats if k.startswith("overhead"))
    assert found == [
        f"overhead_vs_production_high_{GSPT[22:]}",
        f"overhead_vs_production_{GSPT[22:]}",
    ]
    none = FakeServing()
    none.named = lambda workload: None  # type: ignore[method-assign]
    assert not [k for k in join([system_ctx()], none) if k.startswith("overhead")]


@pytest.mark.parametrize("kind", ["resource", "adapter"])
def test_failed_recompute_nulls_agreement(kind: str) -> None:
    """D-AGREE when every recompute attempt failed: null `step_failed`, inputs the failures."""
    system = system_ctx()
    recompute = ctx([view("ref-recompute", "c-1", {}, failure=kind, prompts_from="s-0")])
    _release_rows("v0.1", [system, recompute], ROLES, None)
    agree = system.statistics["agreement_rate"]
    assert isinstance(agree, dict)
    assert agree["null_reason"] == "step_failed"
    assert agree["source"]["inputs"] == ["results/v0.1/ref-recompute/c-1/run.json#/failure"]
    assert REGISTRY.errors("quantity/1", agree, def_name="quantity") == []


def test_agreement_joined_and_other_failure() -> None:
    system = system_ctx()
    counts = {"agreement_positions": q(11.0, "count", None),
              "disagreement_positions": q(1.0, "count", None)}  # fmt: skip
    recompute = ctx([view("ref-recompute", "c-1", counts, prompts_from="s-0")])
    _release_rows("v0.1", [system, recompute], ROLES, None)
    assert system.statistics["agreement_rate"]["value"] == 11 / 12  # type: ignore[index]
    system = system_ctx()
    failed = ctx([view("ref-recompute", "c-1", {}, failure="internal", prompts_from="s-0")])
    _release_rows("v0.1", [system, failed], ROLES, None)
    out = system.statistics["agreement_rate"]
    assert (out["value"], out["null_reason"]) == (None, "step_failed")  # type: ignore[index]


def session_q(value: float | None, reason: str | None = None) -> dict[str, object]:
    """A repetition's `gpu_seconds_per_token_prove.session` (fixture value)."""
    out = q(value, "gpu_s/token", "prove.session")
    if value is None:
        out["null_reason"] = reason or "step_failed"
    return out


def with_session(found: _Context, values: tuple[float | None, ...]) -> _Context:
    for run, v in zip(found.kept, values, strict=True):
        run.run["metrics"][SESSION] = session_q(v)  # type: ignore[index]
    return found


def test_overhead_warm_formula() -> None:
    """TC-OVERHEAD-WARM, D-OVERHEAD-WARM (RFC-0004 INV-DERIVE-11) by hand: the prover's session
    of 0.5 gpu_s/token (544 s for 1,088 tokens on 1 GPU, its start-up inside) over warm
    serving's steady 0.0005 gpu_s/token (0.544 s per 1,088-token request on 1 GPU) is 1,000. The
    quantity carries the prover's scope; the formula names serving's."""
    out = overhead([("sys", session_q(544 / 1088))], [("srv", gspt(0.544 / 1088))],
                   Scope.PROVE_SESSION, warm=True, version="1")  # fmt: skip
    assert out["value"] == pytest.approx(1000.0, rel=1e-12)
    assert (out["scope"], out["unit"], out["grade"]) == ("prove.session", "ratio", "derived")
    assert out["source"]["ref"] == "derive:D-OVERHEAD-WARM@1"  # type: ignore[index]
    assert out["pairs"] == {"n_system": 1, "n_serving": 1, "min": pytest.approx(1000.0),
                            "max": pytest.approx(1000.0)}  # fmt: skip
    assert REGISTRY.errors("quantity/1", out, def_name="quantity") == []
    assert overhead_formula(Scope.PROVE_SESSION, warm=True) == "D-OVERHEAD-WARM"
    assert overhead_formula(Scope.PROVE_SESSION, high=True) == "D-OVERHEAD-HIGH-S"
    assert overhead_formula(Scope.PROVE_STEADY) == "D-OVERHEAD-S"
    assert "prove.steady, matched load" in FORMULAS["D-OVERHEAD-WARM"]


def test_overhead_steady_headline_flashprove_like() -> None:
    """A FlashProve-like row (fixture values): steady 0.01 / (0.000025 x 4) = 100 is the
    headline, start-up excluded."""
    found = [with_session(system_ctx(), (0.02,)),
             with_session(serve_ctx("m", (0.000025 * 4,)), (0.0001 * 4,))]  # fmt: skip
    stats = join(found)
    steady = stats["overhead_vs_production_prove.steady"]
    assert steady["value"] == pytest.approx(100.0, rel=1e-12)  # type: ignore[index]
    entry = found[0].entry
    assert entry is not None
    assert entry["overhead_headline"] == {"metric": "overhead_vs_production_prove.steady",
                                          "formula": "D-OVERHEAD-S", "scope": "prove.steady",
                                          "serving_scope": "prove.steady",
                                          "start_up": "excluded"}  # fmt: skip
    assert entry["overhead_conditions"]["warm"] is True  # type: ignore[index]
    assert WARM not in stats  # INV-DERIVE-11: a system with a steady scope has no warm figure


def sash_ctx(session: float | None = 0.5) -> _Context:
    """A SASH-like system row: one proof per request, so its steady scope is not externally
    observable (RFC-0004 Q2); its session is 0.5 gpu_s/token (544 s for 1,088 tokens on 1 GPU,
    fixture values)."""
    return ctx([view("sash", "s-0", {GSPT: gspt(None, "not_externally_observable"),
                                     SESSION: session_q(session)})])  # fmt: skip


def lengthened(steady: float | None, session: float, **keys: Any) -> _Context:
    """A matched serving row replaying the SASH-like run, lengthened per RFC-0015 SRV-1: its
    steady figure (None: one batch, no steady scope) and its session figure, start-up inside."""
    found = with_session(serve_ctx("m", (None,), **keys), (session,))
    found.kept[0].run["metrics"][GSPT] = (gspt(steady) if steady is not None  # type: ignore[index]
                                          else gspt(None, "fewer_than_two_proofs"))  # fmt: skip
    return found


def test_overhead_warm_headline_sash_like() -> None:
    """TC-OVERHEAD-WARM, a SASH-like row: D-OVERHEAD-S null `not_externally_observable`, so the
    headline is D-OVERHEAD-WARM, the prover's session over warm serving's steady scope: 0.5 /
    0.0005 = 1,000 (fixture values). The conditions are written for the warm figure, serving
    warm."""
    sash = sash_ctx()
    found = [sash, lengthened(0.0005, 0.0025)]
    stats = join(found)
    steady = stats["overhead_vs_production_prove.steady"]
    assert (steady["value"], steady["null_reason"]) == (None, "not_externally_observable")  # type: ignore[index]
    warm = stats[WARM]
    assert isinstance(warm, dict)
    assert warm["value"] == pytest.approx(1000.0, rel=1e-12)
    assert warm["source"]["ref"].startswith("derive:D-OVERHEAD-WARM@")
    assert warm["source"]["inputs"] == [
        f"results/v0.1/sash/s-0/run.json#/metrics/{SESSION}",
        f"results/v0.1/ref-serve/m-0/run.json#/metrics/{GSPT}",
    ]
    assert warm["pairs"] == {"n_system": 1, "n_serving": 1, "min": pytest.approx(1000.0),
                             "max": pytest.approx(1000.0)}  # fmt: skip
    entry = sash.entry
    assert entry is not None
    assert entry["overhead_headline"] == {
        "metric": WARM,
        "formula": "D-OVERHEAD-WARM",
        "scope": "prove.session",
        "serving_scope": "prove.steady",
        "start_up": "prover_only",
    }
    conditions = entry["overhead_conditions"]
    assert isinstance(conditions, dict)
    assert conditions["warm"] is True
    assert conditions["serving_configuration"] == "releases/v0.1/index.json#/configurations/1"
    assert REGISTRY.errors("quantity/1", warm, def_name="quantity") == []


def test_overhead_warm_nulls() -> None:
    """TC-OVERHEAD-WARM null cases, the SASH-like row: no production-serving run gives
    `missing_input` (headline still the warm figure, no conditions); a serving run of one batch
    (no steady scope) gives its own reason, `fewer_than_two_proofs`; a serving run with the
    warning "steady scope under 60 s" and a sizing capture (RFC-0015 SRV-1) enter no mean,
    `missing_input`; a failed prover session passes its reason on first."""
    sash = sash_ctx()
    stats = join([sash])
    out = stats[WARM]
    assert (out["value"], out["null_reason"]) == (None, "missing_input")  # type: ignore[index]
    assert sash.entry is not None
    assert sash.entry["overhead_headline"]["metric"] == WARM  # type: ignore[index]
    assert "overhead_conditions" not in sash.entry
    one = [sash_ctx(), lengthened(None, 0.0025)]
    assert overhead_of(one, WARM) == (None, "fewer_than_two_proofs")
    short = [sash_ctx(), lengthened(0.0005, 0.0025, warnings=("steady scope under 60 s",))]
    assert overhead_of(short, WARM) == (None, "missing_input")
    sizing = [sash_ctx(), lengthened(0.0005, 0.0025, sizing=True)]
    assert overhead_of(sizing, WARM) == (None, "missing_input")
    failed = [sash_ctx(None), lengthened(0.0005, 0.0025)]
    assert overhead_of(failed, WARM) == (None, "step_failed")


def test_headline_scope_rule() -> None:
    """INV-DERIVE-10: steady unless every repetition's steady figure is null for the system's
    own want of a steady scope (or none records it)."""
    assert headline_scope([("a", gspt(0.01))]) is Scope.PROVE_STEADY
    assert headline_scope([("a", gspt(None, "missing_input"))]) is Scope.PROVE_STEADY
    none = [("a", gspt(None, "not_externally_observable")),
            ("b", gspt(None, "fewer_than_two_proofs"))]  # fmt: skip
    assert headline_scope(none) is Scope.PROVE_SESSION
    assert headline_scope([("a", gspt(None, "fewer_than_two_proofs")),
                           ("b", gspt(0.01))]) is Scope.PROVE_STEADY  # fmt: skip
    assert headline_scope([]) is Scope.PROVE_SESSION
