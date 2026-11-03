import json
import shutil
import subprocess
from pathlib import Path

import pytest

from iproofs.validate.tree import forbidden_match, validate_tree

ROOT = Path(__file__).resolve().parents[3]
G6 = ROOT / "harness/tests/fixtures/gates/G6"
RUN_DIR = "results/v0.1/fake/2026-11-20-fake-fake-tiny-ci-ci-cpu-1"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for rel in [
        "schema",
        "systems/fake",
        "workloads/fake-tiny-ci.yaml",
        "reference",
        "harness/tests/fixtures/prompts",
    ]:
        src, dst = ROOT / rel, tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst) if src.is_dir() else shutil.copy(src, dst)
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    return tmp_path


def place(repo: Path, source: Path | str, target: str) -> None:
    dst = repo / target
    dst.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(source, Path):
        shutil.copy(source, dst)
    else:
        dst.write_text(source)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)


def rules(repo: Path) -> list[str]:
    return [f.rule for f in validate_tree(repo) if f.gate == "G6"]


def test_measured_run_with_forbidden_flag_fails(repo: Path) -> None:
    place(repo, G6 / "manifest-forbidden-flag.json", f"{RUN_DIR}/manifest.json")
    assert rules(repo) == ["POL-1"]


def test_control_job_may_use_the_flag(repo: Path) -> None:
    doc = json.loads((G6 / "manifest-forbidden-flag.json").read_text())
    doc["control"] = True
    place(repo, json.dumps(doc), f"{RUN_DIR}/manifest.json")
    assert rules(repo) == []


def test_nonconforming_run_refused(repo: Path) -> None:
    place(repo, G6 / "manifest-nonconforming.json", f"{RUN_DIR}/manifest.json")
    assert rules(repo) == ["POL-4"]


def test_unlisted_entrypoint_literal_fails(repo: Path) -> None:
    place(repo, G6 / "entrypoint-unlisted", "systems/fake/entrypoint")
    found = [f for f in validate_tree(repo) if f.rule == "POL-3"]
    assert [f.path for f in found] == ["systems/fake/entrypoint:2"]


def test_listed_entrypoint_literal_passes(repo: Path) -> None:
    place(repo, (ROOT / "systems/fake/entrypoint").read_text(), "systems/fake/entrypoint")
    assert rules(repo) == []


def test_control_run_with_measured_quantities_fails(repo: Path) -> None:
    run = json.loads((ROOT / "schema/run/examples/valid/fake-success.json").read_text())
    run["control"] = True
    place(repo, json.dumps(run), f"{RUN_DIR}/run.json")
    assert "POL-2" in rules(repo)


@pytest.mark.parametrize(
    ("token", "pattern", "hit"),
    [
        ("--unsound-skip-edge", "--unsound-skip-*", True),
        ("--unsound-skip-edge", "--unsound-skip-", True),  # a bare entry is a prefix
        ("--sound", "--unsound-skip-*", False),
        ("--UNSOUND-skip-edge", "--unsound-skip-*", False),  # case sensitive
    ],
)
def test_forbidden_match(token: str, pattern: str, hit: bool) -> None:
    assert forbidden_match(token, pattern) is hit
