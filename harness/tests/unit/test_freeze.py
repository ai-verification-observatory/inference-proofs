"""RFC-0009 §Freeze algorithm: `iproofs release freeze` over the fixture release."""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from fixtures.release_tree import build, commit
from iproofs import cli
from iproofs.errors import IProofsError
from iproofs.quantity import Tier
from iproofs.release import RunView, _Late, _rel, _statistics
from iproofs.schema import SchemaRegistry
from iproofs.workloads import asserted_inputs, load_workload

ROOT = Path(__file__).resolve().parents[3]
GOLDEN = ROOT / "harness/tests/golden/index/v0.1.json"


def freeze(root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> int:
    monkeypatch.chdir(root)
    code = cli.main(["release", "freeze", "v0.1"])
    capsys.readouterr()
    return code


def index(root: Path) -> dict[str, object]:
    doc: dict[str, object] = json.loads((root / "releases/v0.1/index.json").read_text())
    return doc


def edit_release(root: Path, change: dict[str, object]) -> None:
    path = root / "releases/v0.1/release.yaml"
    doc = yaml.safe_load(path.read_text())
    path.write_text(yaml.safe_dump(doc | change, sort_keys=False))
    commit(root, "edit release")


def configuration(root: Path) -> dict[str, object]:
    configurations = index(root)["configurations"]
    assert isinstance(configurations, list)
    assert len(configurations) == 1
    only: dict[str, object] = configurations[0]
    return only


def test_deterministic_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    update_golden: bool,
) -> None:
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
        build(tmp_path / name)
        assert freeze(tmp_path / name, monkeypatch, capsys) == 0
    a, b = ((tmp_path / n / "releases/v0.1/index.json").read_bytes() for n in ("a", "b"))
    assert a == b
    registry = SchemaRegistry.from_tree(ROOT / "schema")
    assert registry.errors("release-index/1", index(tmp_path / "a")) == []
    if update_golden:
        GOLDEN.write_bytes(a)
    assert a == GOLDEN.read_bytes()


def test_review_window_under_14_days_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    build(tmp_path)
    edit_release(tmp_path, {"review_window": {"opens": "2027-02-15", "closes": "2027-02-28"}})
    monkeypatch.chdir(tmp_path)
    assert cli.main(["release", "freeze", "v0.1"]) == 1
    assert "is under 14 days" in capsys.readouterr().err
    assert not (tmp_path / "releases/v0.1/index.json").exists()


def test_freeze_price_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """TC-FREEZE-PRICE-ZERO (RFC-0006 C6): the old placeholder price stops the freeze."""
    build(tmp_path)
    path = tmp_path / "reference/v0.1.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["cost"]["price_per_gpu_hour_usd"]["value"] = 0.0
    path.write_text(yaml.safe_dump(doc, sort_keys=False))
    commit(tmp_path, "unpriced")
    monkeypatch.chdir(tmp_path)
    assert cli.main(["release", "freeze", "v0.1"]) == 1
    assert "has no price or no date (RFC-0006 C6)" in capsys.readouterr().err
    assert not (tmp_path / "releases/v0.1/index.json").exists()


def test_freeze_date_must_follow_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    build(tmp_path)
    edit_release(tmp_path, {"freeze_date": "2027-03-01"})
    monkeypatch.chdir(tmp_path)
    assert cli.main(["release", "freeze", "v0.1"]) == 1
    assert "freeze_date 2027-03-01 is not after 2027-03-01" in capsys.readouterr().err


def test_insufficient_repetitions_flagged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    build(tmp_path, runs=4)  # 2 eligible, 1 dirty, 1 superseded
    assert freeze(tmp_path, monkeypatch, capsys) == 0
    config = configuration(tmp_path)
    assert config["insufficient_repetitions"] is True
    assert config["statistics"]["proof_bytes"]["stats"]["n"] == 2  # type: ignore[index]


def test_ineligible_run_excluded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    build(tmp_path)
    assert freeze(tmp_path, monkeypatch, capsys) == 0
    config = configuration(tmp_path)
    dirty = "2026-11-06-fake-fake-tiny-ci-ci-cpu-4"
    assert dirty not in config["runs"]  # type: ignore[operator]
    assert {"run_id": dirty, "reasons": ["harness_dirty"]} in config["ineligible"]  # type: ignore[operator]
    inputs = config["statistics"]["proof_bytes"]["source"]["inputs"]  # type: ignore[index]
    assert not any(dirty in i for i in inputs)
    assert config["insufficient_repetitions"] is False


def test_superseded_run_excluded_and_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    build(tmp_path)
    assert freeze(tmp_path, monkeypatch, capsys) == 0
    config = configuration(tmp_path)
    withdrawn = "2026-11-07-fake-fake-tiny-ci-ci-cpu-5"
    assert withdrawn not in config["runs"]  # type: ignore[operator]
    assert {"run_id": withdrawn, "reasons": ["superseded: wrong CPU binding"]} in config[
        "ineligible"
    ]  # type: ignore[operator]


def test_controls_summarised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    build(tmp_path)
    assert freeze(tmp_path, monkeypatch, capsys) == 0
    controls: Any = index(tmp_path)["controls"]
    assert len(controls) == 1
    summary = controls[0]
    stored = json.loads(next((tmp_path / "results").rglob("controls.json")).read_text())
    for outcome, count in summary["counts"].items():
        assert count == stored["summary"][outcome]
    assert summary["outside_expected"] == []


def test_listed_claim_card_digest_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    build(tmp_path)
    (tmp_path / "systems/fake/claims/default.yaml").write_text("# changed\n")
    commit(tmp_path, "edit card")
    monkeypatch.chdir(tmp_path)
    assert cli.main(["release", "freeze", "v0.1"]) == 1
    assert "does not match its listed digest" in capsys.readouterr().err


def test_gate_failure_stops_freeze(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    build(tmp_path)
    run_json = next((tmp_path / "results").rglob("run.json"))
    run_json.write_text(json.dumps(json.loads(run_json.read_text())))  # not canonical: G3
    commit(tmp_path, "reformat")
    monkeypatch.chdir(tmp_path)
    assert cli.main(["release", "freeze", "v0.1"]) == 1
    assert "gates failed: G3" in capsys.readouterr().err


# ---------------------------------------------------------------- RFC-0004 Q3, RFC-0003 WB-4

WORKED = ROOT / "harness/tests/fixtures/derive/worked-example/run.json"
SCOPES = ("prove.steady", "prove.session", "whole_wall")
LATE = ("tokens_covered_per_proof", *(f"seconds_per_active_weight_bit_token_{s}" for s in SCOPES))


def stored_run(n: int, *, late_keys: bool, inputs: dict[str, Any] | None) -> RunView:
    """A completed fake-tiny-ci repetition from the worked example's metrics; without
    `late_keys` it is a run stored before D-TPP and D-SPAB-S (fixture values, not a result)."""
    doc = json.loads(WORKED.read_text())
    rid = f"2026-11-0{n}-fake-fake-tiny-ci-ci-cpu-{n}"
    doc |= {"run_id": rid, "workload": {"id": "fake-tiny-ci", "version": 1}}
    doc["metrics"] = {k: v for k, v in doc["metrics"].items() if late_keys or k not in LATE}
    doc.pop("inputs")
    if inputs is not None:
        doc["inputs"] = inputs
    return RunView(Path(f"results/v0.1/fake/{rid}"), doc, {}, None)


def late_statistics(runs: list[RunView]) -> tuple[dict[str, Any], _Late]:
    late = _Late(ROOT, SchemaRegistry.from_tree(ROOT / "schema"), "v0.1")
    tiers = {r.run_id: Tier.REPORTED for r in runs}
    return _statistics(runs, tiers, late), late


def fake_inputs() -> dict[str, Any]:
    registry = SchemaRegistry.from_tree(ROOT / "schema")
    return asserted_inputs(load_workload("fake-tiny-ci", root=ROOT, registry=registry))


def test_freeze_evaluates_a_stored_run_without_the_key() -> None:
    """RFC-0004 Q3: a run stored before D-SPAB-S and D-TPP stays in n. The freeze evaluates
    its values into `freeze_derived`, and D-STAT points there; the newer run counts as stored."""
    old = stored_run(1, late_keys=False, inputs=None)
    new = stored_run(2, late_keys=True, inputs=fake_inputs())
    stats, late = late_statistics([old, new])
    for name in LATE:
        assert stats[name]["stats"]["n"] == 2, name
        assert stats[name]["source"]["inputs"][0] == (
            f"releases/v0.1/index.json#/freeze_derived/{old.run_id}/{name}"
        )
    assert sorted(late.values) == [old.run_id]
    spab = late.values[old.run_id]["seconds_per_active_weight_bit_token_prove.steady"]
    assert spab["source"]["inputs"] == [  # type: ignore[index]
        f"{_rel(old)}/run.json#/metrics/seconds_per_token_prove.steady",
        "workloads/fake-tiny-ci.yaml#/model/parameters/active_per_token",
        "workloads/fake-tiny-ci.yaml#/precision/weight_bits",
    ]
    # hand-computed: 0.01 s/token over 64 parameters x 8 bits (fake-tiny-ci, file size)
    assert spab["value"] == 0.01 / (64 * 8.0)
    assert late.values[old.run_id]["tokens_covered_per_proof"]["value"] == 1000


def test_freeze_value_of_another_workload_version_is_missing_input() -> None:
    """RFC-0004 Q3: the workload record now holds another version than the run's, so its
    inputs do not apply: D-SPAB-S is null with `missing_input`; D-TPP needs no workload."""
    old = stored_run(1, late_keys=False, inputs=None)
    old.run["workload"] = {"id": "fake-tiny-ci", "version": 2}
    _, late = late_statistics([old])
    values = late.values[old.run_id]
    assert values["seconds_per_active_weight_bit_token_prove.steady"]["null_reason"] == (
        "missing_input"
    )
    assert values["tokens_covered_per_proof"]["value"] == 1000


def test_freeze_stops_on_different_workload_inputs() -> None:
    """RFC-0003 WB-4: one configuration's repetitions share the workload's weight bits; a run
    recorded with other bits (the worked example's 8e9 parameters) stops the freeze."""
    worked = json.loads(WORKED.read_text())["inputs"]
    runs = [stored_run(1, late_keys=True, inputs=fake_inputs()),
            stored_run(2, late_keys=True, inputs=worked)]  # fmt: skip
    with pytest.raises(IProofsError, match="WB-4"):
        late_statistics(runs)
