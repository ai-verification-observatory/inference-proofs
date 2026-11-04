"""RFC-0009 §Freeze algorithm: `iproofs release freeze` over the fixture release."""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from fixtures.release_tree import build, commit
from iproofs import cli
from iproofs.schema import SchemaRegistry

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
