"""RFC-0004 release rows: D-OVERHEAD-S and D-OVERHEAD-HIGH-S in GPU-seconds per token
(INV-DERIVE-2, -8, -9), D-AGREE, D-PROVIDER-SPREAD, and RFC-0015 NM-1.

Every value here is a fixture value, not a result."""

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from iproofs.derive import agreement_rate, overhead, provider_spread
from iproofs.model import Workload, load
from iproofs.quantity import NullReason, Scope, Tier
from iproofs.release import RunView, _Context, _release_rows, _serving_nm1
from iproofs.schema import SchemaRegistry

ROLES = {"ref-serve": "serve", "ref-recompute": "recompute"}
ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
WL = {"id": "fp-maverick-w1024-b24", "version": 1}
DIGEST = "sha256:" + "d" * 64
IMAGE = "docker.io/vllm/vllm-openai@sha256:" + "c" * 64
GSPT = "gpu_seconds_per_token_prove.steady"
WHOLE = "gpu_seconds_per_token_whole_wall"


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
    for reason in (None, NullReason.MISSING_INPUT, NullReason.NOT_MEASURABLE_ON_PROFILE):
        out = overhead(sash, [("v", gspt(0.0001))], Scope.PROVE_STEADY, reason=reason,
                       version="1")  # fmt: skip
        assert (out["value"], out["null_reason"]) == (None, "not_externally_observable")
        assert out["pairs"] == {"n_system": 0, "n_serving": 1, "min": None, "max": None}


def view(system: str, run_id: str, metrics: Mapping[str, object], *, failure: str | None = None,
         prompts_from: str | None = None, profile: str = "prover-h200-hosted",
         digest: str = DIGEST, image: str = IMAGE) -> RunView:  # fmt: skip
    run: dict[str, object] = {"run_id": run_id, "system": system, "metrics": metrics,
           "status": "failed" if failure else "completed", "profile": profile,
           "failure": {"kind": failure} if failure else None}  # fmt: skip
    manifest: dict[str, object] = {
        "provider": "p1",
        "prompts_from": prompts_from,
        "profile": {"prover": profile},
    }
    if system == "ref-serve":
        manifest["serving_model"] = {"digest": digest}
        manifest["engine"] = {"image": image, "interface": "vllm serve"}
        manifest["workload"] = {"prompt_count_run": 120, "batches_per_session_run": 5}
    return RunView(Path("results/v0.1") / system / run_id, run, manifest, None)


def ctx(runs: list[RunView], profile: str = "prover-h200-hosted",
        load_point: str | None = None) -> _Context:  # fmt: skip
    where: dict[str, object] = {
        "system": str(runs[0].run["system"]),
        "workload": WL,
        "profile": profile,
    }
    stats: dict[str, object] = {}
    return _Context(where, None, runs, {r.run_id: Tier.REPORTED for r in runs}, stats, None,
                    load_point, {})  # fmt: skip


class Profile:
    def __init__(self, count: int, pairs: tuple[str, ...] = ()) -> None:
        self.gpu = type("Gpu", (), {"count": count, "model": "NVIDIA H200"})()
        self.pairs_with = pairs


class FakeServing:
    """The release-commit facts the join reads (iproofs.release._Serving), as fixtures."""

    def __init__(self, digest: str = DIGEST, image: str = IMAGE) -> None:
        self.digest, self.image = digest, image
        self.profiles = {"prover-h200-hosted": Profile(1), "prover-h100-hosted": Profile(1),
                         "serving-h200x4-hosted": Profile(4, ("prover-h200-hosted",)),
                         "serving-h200x8-hosted": Profile(8, ("prover-h200-hosted",)),
                         "serving-h200x4": Profile(4, ("prover-h200",))}  # fmt: skip

    def named(self, workload: str) -> str | None:
        return "ref-serve"

    def system(self, name: str) -> dict[str, object]:
        return {"engine": {"name": "vllm", "version": "0.32.0", "image": self.image}}

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


def system_ctx(values: tuple[float, ...] = (0.01,)) -> _Context:
    runs = [view("flashprove", f"s-{i}", {GSPT: gspt(v)}) for i, v in enumerate(values)]
    return ctx(runs)


def serve_ctx(prefix: str, values: tuple[float | None, ...], *, profile: str =
              "serving-h200x4-hosted", load_point: str = "matched", source: str = "s-0",
              failure: str | None = None, **keys: str) -> _Context:  # fmt: skip
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
    assert conditions["gpus"] == {"system": 1, "serving": 4}
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


def test_overhead_fewest() -> None:
    """TC-OVERHEAD-FEWEST: TP4 with one paired success and two resource failures, TP8 with
    three successes: TP4 joins, so the mean is TP4's."""
    tp4 = serve_ctx("a", (0.0001, None, None), failure="resource")
    tp8 = serve_ctx("b", (0.0004, 0.0004, 0.0004), profile="serving-h200x8-hosted")
    stats = join([system_ctx(), tp8, tp4])
    assert stats["overhead_vs_production_prove.steady"]["value"] == pytest.approx(100.0)  # type: ignore[index]


def test_overhead_prompts_pairing() -> None:
    """TC-OVERHEAD-PROMPTS: serving runs that replay another system's runs do not enter the
    mean; none paired gives missing_input."""
    stats = join([system_ctx(), serve_ctx("m", (0.0001,), source="other-run")])
    out = stats["overhead_vs_production_prove.steady"]
    assert (out["value"], out["null_reason"]) == (None, "missing_input")  # type: ignore[index]
    stats = join([system_ctx()])  # no serving configuration at all
    assert stats["overhead_vs_production_prove.steady"]["null_reason"] == "missing_input"  # type: ignore[index]


def test_overhead_nm1() -> None:
    """TC-OVERHEAD-NM1: every serving attempt on a paired profile failed resource."""
    stats = join([system_ctx(), serve_ctx("m", (None, None), failure="resource")])
    out = stats["overhead_vs_production_prove.steady"]
    assert (out["value"], out["null_reason"]) == (None, "not_measurable_on_profile")  # type: ignore[index]
    adapter = join([system_ctx(), serve_ctx("m", (None,), failure="adapter")])
    assert adapter["overhead_vs_production_prove.steady"]["null_reason"] == "missing_input"  # type: ignore[index]
    assert not _serving_nm1(serve_ctx("m", (None,), failure="adapter"))


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


def test_whole_wall_not_applicable_and_ci_absent() -> None:
    sys = system_ctx()
    sys.kept[0].run["metrics"][WHOLE] = gspt(0.02)  # type: ignore[index]
    stats = join([sys, serve_ctx("m", (0.0001,))])
    assert stats[f"overhead_vs_production_{WHOLE[22:]}"]["null_reason"] == "not_applicable"  # type: ignore[index]
    none = FakeServing()
    none.named = lambda workload: None  # type: ignore[method-assign]
    assert not [k for k in join([system_ctx()], none) if k.startswith("overhead")]


@pytest.mark.parametrize("kind", ["resource", "adapter"])
def test_nm1_nulls_agreement(kind: str) -> None:
    """TC-NM-1 for D-AGREE: every recompute attempt failed with resource or adapter."""
    system = system_ctx()
    recompute = ctx([view("ref-recompute", "c-1", {}, failure=kind, prompts_from="s-0")])
    _release_rows("v0.1", [system, recompute], ROLES, None)
    agree = system.statistics["agreement_rate"]
    assert isinstance(agree, dict)
    assert agree["null_reason"] == "not_measurable_on_profile"
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
