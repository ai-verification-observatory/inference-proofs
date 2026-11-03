"""RFC-0008 §System-specific controls: controls.yaml, weakened provers and fixture proofs."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from iproofs.adapter import InProcessRunner, StepResult
from iproofs.controls import edge_unbound
from iproofs.runner import JobSpec, Runner
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
PIN = "f7cf1d696bd15cf1601f48ea4c51ae20e57c9d82"  # systems/fake-broken/system.yaml


class Spy:
    """fake-broken, with every verify job's commitment kept."""

    def __init__(self) -> None:
        env = {"IPROOFS_FAKE_UPSTREAM": PIN, "IPROOFS_FAKE_DELAY_S": "0.01"}
        self.inner = InProcessRunner(ROOT / "systems/fake-broken/entrypoint", REGISTRY, env=env)
        self.commitments: list[str] = []

    def run(self, image: str, sub: str, io: Path, **kw: Any) -> StepResult:
        if sub == "verify":
            self.commitments.append(json.loads((io / "job.json").read_text())["commitment_id"])
        return self.inner.run(image, sub, io, **kw)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    copied = [
        "schema",
        "systems/fake",
        "systems/fake-broken",
        "workloads/fake-tiny-ci.yaml",
        "reference",
        "harness/tests/fixtures/prompts",
        "uv.lock",
        "pyproject.toml",
    ]
    for rel in copied:
        src, dst = ROOT / rel, repo / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst) if src.is_dir() else shutil.copy(src, dst)
    fixture = ROOT / "harness/tests/fixtures/controls/fake-broken-controls.yaml"
    shutil.copy(fixture, repo / "systems/fake-broken/controls.yaml")
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "fixture", "--no-gpg-sign"], check=True)
    return repo


def test_system_controls_from_controls_yaml(repo: Path, tmp_path: Path) -> None:
    spy = Spy()
    image = "local/x@sha256:" + "0" * 64
    runner = Runner(spy, root=repo, registry=REGISTRY, image=image)  # type: ignore[arg-type]
    spec = JobSpec("fake-broken", "fake-tiny-ci", 1, "ci-cpu", 1, True, str(tmp_path / "r"), "v0.1")
    run_dir = runner.run(spec)
    doc = json.loads((run_dir / "controls.json").read_text())
    assert REGISTRY.errors("controls/1", doc) == []
    system = {c["id"]: c for c in doc["controls"] if c["source"] == "system"}
    tag = system["fake-unsound-skip-tag"]
    nothing = system["fake-unsound-skip-nothing"]
    fixture = system["fake-fixture-proof"]
    assert (tag["side"], tag["outcome"], tag["passed"]) == ("prover", "accepted", True)
    assert {t["outcome"] for t in tag["trials"]} == {"accepted"}
    assert (fixture["outcome"], fixture["passed"]) == ("not_applicable", None)
    assert "not specified" in fixture["note"]
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert set(spy.commitments) == {manifest["commitment"]["commitment_id"]}  # INV-CTRL-6
    run = json.loads((run_dir / "run.json").read_text())
    assert run["status"] == "completed"
    assert [e["event"] for e in run["events"]].count("prove.start") == 1  # controls never retime
    assert nothing["outcome"] == "accepted"
    assert nothing["passed"] is False


def test_weakened_prover_requires_unbound_edge() -> None:
    """An accepted outcome with the edge marked bound does not pass."""
    assert edge_unbound({"edges": {"tag": "unbound"}}, "tag") is True
    assert edge_unbound({"edges": {"tag": "bound"}}, "tag") is False
    assert edge_unbound({"edges": [{"edge": "tag", "state": "unbound"}]}, "tag") is True
    assert edge_unbound(None, "tag") is False
