"""docs/spec/08 §Run-campaign compute budget: P-CAMPAIGN and `iproofs release plan`."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from iproofs import cli
from iproofs.derive import project_campaign
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
SOURCE = {"kind": "upstream", "ref": "https://example.org/figures.tsv#L1"}


def external(root: Path, system: str, figures: dict[str, float]) -> None:
    """A fixture external.yaml; the values are round fixtures, not measurements."""
    path = root / "systems" / system / "external.yaml"
    path.parent.mkdir(parents=True)
    rows = [
        {"id": metric, "metric": metric, "workload": "w1",
         "quantity": {"value": value, "unit": "s", "scope": "whole_wall", "grade": "external",
                      "tier": "reported", "source": dict(SOURCE), "null_reason": None}}
        for metric, value in figures.items()
    ]  # fmt: skip
    path.write_text(yaml.safe_dump({"schema": "external/1", "system": system, "figures": rows}))


def fixture(tmp_path: Path, whole_wall: bool = True) -> Path:
    figures = {"commit_seconds": 20.0, "prove_session_seconds": 30.0}
    if whole_wall:
        figures["whole_wall_seconds"] = 100.0
    external(tmp_path, "sys-a", figures)
    external(tmp_path, "ref-serve", {"prove_session_seconds": 10.0})
    return tmp_path


def test_project_campaign_hand_computed(tmp_path: Path) -> None:
    out = project_campaign("v0.1", fixture(tmp_path))
    config: Any = out["configurations"][0]  # type: ignore[index]
    assert len(out["configurations"]) == 1  # type: ignore[arg-type]
    q = config["campaign_gpu_seconds"]
    assert q["value"] == 390.0  # 3 x 100 + 20 + 2 x 30 + 10, by hand
    assert (q["grade"], q["unit"], q["scope"]) == ("projected", "s", "whole_wall")
    assert q["source"]["ref"].startswith("derive:P-CAMPAIGN@")
    assert q["source"]["inputs"] == [
        f"systems/sys-a/external.yaml#/figures/{i}/quantity" for i in (2, 0, 1)
    ] + ["systems/ref-serve/external.yaml#/figures/0/quantity"]
    assert REGISTRY.errors("quantity/1", q, def_name="quantity") == []  # labels hold
    assert config["missing"] == []


def test_missing_whole_wall_gives_missing_input(tmp_path: Path) -> None:
    root = fixture(tmp_path, whole_wall=False)
    path = root / "systems/sys-a/external.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["figures"].append(
        {**json.loads(json.dumps(doc["figures"][0])), "workload": None}
    )  # no shape: not an input
    path.write_text(yaml.safe_dump(doc))
    out = project_campaign("v0.1", root)
    config: Any = out["configurations"][0]  # type: ignore[index]
    assert len(out["configurations"]) == 1  # type: ignore[arg-type]
    q = config["campaign_gpu_seconds"]
    assert (q["value"], q["null_reason"], q["grade"]) == (None, "missing_input", "projected")
    assert config["missing"] == ["sys-a:w1:whole_wall_seconds"]
    assert REGISTRY.errors("quantity/1", q, def_name="quantity") == []


def test_projection_never_written_to_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = fixture(tmp_path)
    shutil.copytree(ROOT / "schema", root / "schema")
    monkeypatch.chdir(root)
    assert cli.main(["release", "plan", "v0.1"]) == 0
    assert json.loads(capsys.readouterr().out)["configurations"][0]["system"] == "sys-a"
    assert sorted(p.name for p in root.iterdir()) == ["schema", "systems"]  # nothing written
    assert cli.main(["release", "plan", "v0.1", "--repetitions", "2"]) == 2  # below RFC-0004
