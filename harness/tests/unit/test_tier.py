"""RFC-0007 §Effective tier at release freeze, INV-TIER-3, INV-TIER-6 and INV-TIER-7."""

import json
from pathlib import Path
from typing import Any

import pytest

from fixtures.release_tree import build, commit
from iproofs import cli
from iproofs.quantity import Tier
from iproofs.release import RunView, effective_tier, quantity_tier
from iproofs.validate.tree import validate_tree

ROOT = Path(__file__).resolve().parents[3]
RUN_ID = "2027-01-10-fake-fake-tiny-ci-ci-cpu-1"
REPRO = json.loads(next((ROOT / "schema/reproduction/examples/valid").glob("*.json")).read_text())


def run(dirty: bool = False, grade: str = "measured") -> RunView:
    metrics = {
        "prove_session_seconds": {"grade": grade, "tier": "reported", "value": 1.0},
        "rate_prove.session": {"grade": "derived", "tier": "reported", "value": 2.0,
                               "source": {"inputs": [f"results/v0.1/fake/{RUN_ID}/run.json"
                                                     "#/metrics/prove_session_seconds"]}},
        "cost_per_1k_tokens": {"grade": "derived", "tier": "reported", "value": 3.0,
                               "source": {"inputs": [f"results/v0.1/fake/{RUN_ID}/run.json"
                                                     "#/metrics/rate_prove.session",
                                                     "reference/v0.1.yaml#/cost"]}},
    }  # fmt: skip
    if grade == "external":  # imported upstream figures only
        metrics = {k: {**q, "grade": "external"} for k, q in metrics.items()}
    manifest = {
        "harness": {"git_dirty": dirty},
        "system": {"adapter_dirty": False},
        "runner": {"handle": "r", "organisation": "Runner Org", "affiliated_systems": []},
    }
    return RunView(Path(RUN_ID), {"run_id": RUN_ID, "system": "fake", "metrics": metrics},
                   manifest, None)  # fmt: skip


def review(org: str, outcome: str = "approved") -> dict[str, object]:
    return {"run_id": RUN_ID, "outcome": outcome, "reviewer": {"handle": "v", "organisation": org}}


def repro(
    org: str, outcome: str = "within_tolerance", affiliated: tuple[str, ...] = ()
) -> dict[str, object]:
    runner = {"handle": "p", "organisation": org, "affiliated_systems": list(affiliated)}
    return {"original_run_ids": [RUN_ID], "outcome": outcome, "runner": runner}


@pytest.mark.parametrize(
    ("view", "reviews", "repros", "want"),
    [
        (run(), [], [], Tier.REPORTED),
        (run(), [review("Other Org")], [], Tier.PEER_REVIEWED),
        (run(), [review("runner org")], [], Tier.REPORTED),  # same organisation, any case
        (run(), [review("Other Org", "objected")], [], Tier.REPORTED),
        (run(), [], [repro("Third Org")], Tier.REPRODUCED),
        (
            run(),
            [review("Other Org")],
            [repro("Third Org", affiliated=("fake",))],
            Tier.PEER_REVIEWED,
        ),
        (run(), [], [repro("Maintainer Org")], Tier.REPORTED),  # a system maintainer's organisation
        (run(), [], [repro("Runner Org")], Tier.REPORTED),  # the original runner's organisation
        (run(), [], [repro("Third Org", "outside_tolerance")], Tier.REPORTED),
        (run(dirty=True), [review("Other Org")], [repro("Third Org")], Tier.REPORTED),
        (run(grade="external"), [], [repro("Third Org")], Tier.REPORTED),
    ],
)
def test_effective_tier_order(
    view: RunView, reviews: list[dict[str, Any]], repros: list[dict[str, Any]], want: Tier
) -> None:
    assert effective_tier(view, reviews, repros, ["Maintainer Org"]) == want


def test_derived_tier_minimum() -> None:
    view = run()
    assert quantity_tier(view, "prove_session_seconds", Tier.REPRODUCED) == Tier.REPRODUCED
    assert quantity_tier(view, "rate_prove.session", Tier.REPRODUCED) == Tier.REPRODUCED
    assert quantity_tier(view, "cost_per_1k_tokens", Tier.REPRODUCED) == Tier.REPORTED  # price


def freeze(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> dict[str, Any]:
    monkeypatch.chdir(root)
    code = cli.main(["release", "freeze", "v0.1"])
    assert code == 0, capsys.readouterr().err
    configuration: dict[str, Any] = json.loads((root / "releases/v0.1/index.json").read_text())[
        "configurations"][0]  # fmt: skip
    return configuration


def add_repro(root: Path, outcome: str) -> str:
    runs = sorted((root / "results/v0.1/fake").iterdir())[:3]  # the three eligible runs
    runner = {"handle": "p", "organisation": "Third Org", "affiliated_systems": []}
    eligibility = {**REPRO["eligibility"], "different_machine": True}
    record = REPRO | {"original_run_ids": [r.name for r in runs], "outcome": outcome,
                      "runner": runner, "eligibility": eligibility}  # fmt: skip
    path = runs[0] / "reproductions" / f"{REPRO['reproduction_run_ids'][0]}.json"
    path.parent.mkdir()
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    commit(root, "reproduction")
    return path.relative_to(root).as_posix()


def test_reproduced_tier_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rel = add_repro(build(tmp_path).parents[2], "within_tolerance")
    config = freeze(tmp_path, monkeypatch, capsys)
    assert config["effective_tier"] == "reproduced"
    assert config["evidence"]["reproductions"] == [rel]
    assert config["statistics"]["proof_bytes"]["tier"] == "reproduced"


def test_failed_repro_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rel = add_repro(build(tmp_path).parents[2], "outside_tolerance")
    config = freeze(tmp_path, monkeypatch, capsys)
    assert config["evidence"]["reproductions"] == [rel]  # listed with both sets of numbers
    assert config["effective_tier"] == "reported"  # never lowered, never raised by it


def test_own_organisation_review_rejected(tmp_path: Path) -> None:
    """INV-TIER-3: G2 rejects a review by the run's own organisation."""
    build(tmp_path)
    first = sorted((tmp_path / "results/v0.1/fake").iterdir())[0]
    record = json.loads((ROOT / "schema/review/examples/valid/approved.json").read_text())
    record |= {"run_id": first.name, "reviewer": {"handle": "v", "organisation": "None"}}
    path = first / "reviews/v-2027-01-20.json"
    path.parent.mkdir()
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    commit(tmp_path, "review")
    rel = path.relative_to(tmp_path).as_posix()
    assert [f.rule for f in validate_tree(tmp_path, only=[rel])] == ["TIER-3"]
