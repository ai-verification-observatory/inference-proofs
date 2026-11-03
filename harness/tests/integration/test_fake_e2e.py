"""Fake-system end-to-end runs (RFC-0013 §G10, docs/spec/07 §Fake-system integration).

By default `docker` is the stand-in CLI in harness/tests/fixtures/fake-docker, so this module
runs anywhere. With IPROOFS_REAL_DOCKER=1 it builds the fake images from systems/*/Dockerfile
and runs real containers through the same DockerRunner (the fake-e2e CI job).
"""

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from iproofs import cli
from iproofs.adapter import DockerRunner, StepResult
from iproofs.validate import check_derived
from iproofs.validate.tree import validate_tree

ROOT = Path(__file__).resolve().parents[3]
REAL = os.environ.get("IPROOFS_REAL_DOCKER") == "1"
COPY = [
    "schema",
    "systems/fake",
    "systems/fake-broken",
    "workloads/fake-tiny-ci.yaml",
    "reference",
    "uv.lock",
    "pyproject.toml",
    "harness/tests/fixtures/prompts",
]
Image = Callable[..., str]


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A minimal repository holding the fake systems, so a run writes into its results/."""
    repo = tmp_path / "repo"
    for rel in COPY:
        src, dst = ROOT / rel, repo / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst) if src.is_dir() else shutil.copy(src, dst)
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "fixture", "--no-gpg-sign"], check=True)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("IPROOFS_FAKE_DELAY_S", "0.01")
    if not REAL:
        state = tmp_path / "docker-state"
        state.mkdir()
        fake_docker = ROOT / "harness/tests/fixtures/fake-docker"
        monkeypatch.setenv("PATH", f"{fake_docker}{os.pathsep}{os.environ['PATH']}")
        monkeypatch.setenv("FAKE_DOCKER_STATE", str(state))
    return repo


@pytest.fixture
def image(monkeypatch: pytest.MonkeyPatch) -> Image:
    """The image ID for a fake system, optionally with an injected prove fault."""

    def build(system: str, fault: str = "") -> str:
        pin = yaml.safe_load((ROOT / "systems" / system / "system.yaml").read_text())
        commit = pin["upstream"]["commit"]
        if not REAL:
            monkeypatch.setenv(
                "FAKE_DOCKER_ENTRYPOINT", str(ROOT / "systems" / system / "entrypoint")
            )
            monkeypatch.setenv("IPROOFS_FAKE_UPSTREAM", commit)
            monkeypatch.setenv("IPROOFS_FAKE_FAULT", fault)
            return "sha256:" + "0" * 64
        argv = ["docker", "build", "-q", "--build-arg", f"IPROOFS_FAKE_UPSTREAM={commit}"]
        argv += ["--build-arg", f"IPROOFS_FAKE_FAULT={fault}"] if fault else []
        argv += ["-f", str(ROOT / "systems" / system / "Dockerfile"), str(ROOT / "systems")]
        return subprocess.run(argv, check=True, capture_output=True, text=True).stdout.strip()

    return build


def iproofs_run(system: str, image_id: str, repetitions: int, *extra: str) -> int:
    """`iproofs run` as RFC-0013 E2E-1 writes it, plus the local image."""
    argv = ["run", "--system", system, "--workload", "fake-tiny-ci", "--profile", "ci-cpu"]
    argv += ["--repetitions", str(repetitions), "--results", "results", "--image", image_id]
    return cli.main([*argv, *extra])


def why(repo: Path) -> list[object]:
    """Failure records of every run so far, for assertion messages."""
    runs = sorted((repo / "results").glob("*/*/*/run.json"))
    return [json.loads(p.read_text()).get("failure") for p in runs]


def run_dirs(repo: Path, system: str) -> list[Path]:
    return sorted(p for p in (repo / "results/v0.1" / system).iterdir() if p.is_dir())


def read(run_dir: Path, name: str) -> dict[str, object]:
    doc: dict[str, object] = json.loads((run_dir / name).read_text())
    return doc


def controls(run_dir: Path) -> dict[str, str]:
    entries = read(run_dir, "controls.json")["controls"]
    assert isinstance(entries, list)
    return {c["id"]: c["outcome"] for c in entries}


def test_e2e_fake_and_fake_broken(repo: Path, image: Image) -> None:
    """E2E-1: three sound runs, one weak-verifier run flagged, every record valid."""
    assert iproofs_run("fake", image("fake"), 3, "--control-suite") == 0, why(repo)
    assert iproofs_run("fake-broken", image("fake-broken"), 1, "--control-suite") == 0, why(repo)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    assert validate_tree(repo) == []  # G2 to G9 over every produced file

    fake = run_dirs(repo, "fake")
    assert len(fake) == 3
    for d in fake:
        run = read(d, "run.json")
        assert run["status"] == "completed"
        manifest = read(d, "manifest.json")
        assert manifest["system"]["image"]["digest_kind"] == "config"  # type: ignore[index]
        metrics = run["metrics"]
        assert isinstance(metrics, dict)
        assert metrics["verdicts_accept_count"]["value"] == metrics["proofs_count"]["value"] == 6
        gpu = {k: v for k, v in metrics.items() if "gpu" in k}
        assert all(
            v["value"] is None and v["null_reason"] == "not_applicable" for v in gpu.values()
        )
        assert check_derived(d / "run.json", repo) == []  # iproofs derive --check

    # RFC-0008: the suite runs once per configuration, on the first successful repetition
    assert [(d / "controls.json").exists() for d in fake] == [True, False, False]
    found = controls(fake[0])
    applicable = {k: v for k, v in found.items() if v != "not_applicable"}
    # C5, C6 and C8 may end as invalid_call; every other applicable control must be rejected
    assert all(
        v == "rejected" or (k in {"C5", "C6", "C8"} and v == "invalid_call")
        for k, v in applicable.items()
    ), found

    (broken,) = run_dirs(repo, "fake-broken")
    found = controls(broken)
    outcomes = [v for v in found.values() if v != "not_applicable"]
    assert outcomes, found
    assert set(outcomes) == {"accepted"}, found  # the weak verifier is caught
    summary = read(broken, "controls.json")["summary"]
    assert isinstance(summary, dict)
    assert summary["passed"] == 0
    assert summary["accepted"] == len(outcomes)
    assert check_derived(broken / "run.json", repo) == []


def failure(repo: Path) -> dict[str, object]:
    (run_dir,) = run_dirs(repo, "fake")
    run = read(run_dir, "run.json")
    assert run["status"] == "failed"
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    assert validate_tree(repo) == []  # a failed run is a valid record
    found = run["failure"]
    assert isinstance(found, dict)
    return found


def test_failed_step_recorded(repo: Path, image: Image) -> None:
    assert iproofs_run("fake", image("fake", "exit"), 1) == 4
    found = failure(repo)
    assert (found["kind"], found["step"], found["exit_code"]) == ("adapter", "prove", 3), found
    assert "fake: injected prove failure" in found["last_lines"]  # type: ignore[operator]


def test_timeout_recorded(repo: Path, image: Image) -> None:
    system = repo / "systems/fake/system.yaml"
    system.write_text(system.read_text().replace("prove: 60", "prove: 2"))
    assert iproofs_run("fake", image("fake", "sleep"), 1) == 4
    found = failure(repo)
    assert (found["kind"], found["step"]) == ("timeout", "prove"), found


def test_path_traversal_rejected(repo: Path, image: Image) -> None:
    assert iproofs_run("fake", image("fake", "escape"), 1) == 4
    found = failure(repo)
    assert (found["kind"], found["step"]) == ("adapter", "prove"), found


def test_commitment_from_record(repo: Path, image: Image, monkeypatch: pytest.MonkeyPatch) -> None:
    """AGENTS.md rule 6: every verify call gets the commitment the harness recorded."""
    sent: list[dict[str, object]] = []
    inner = DockerRunner.run

    def spy(self: DockerRunner, image: str, sub: str, io_dir: Path, **kw: Any) -> StepResult:
        if sub == "verify":
            sent.append(json.loads((io_dir / "job.json").read_text()))
        return inner(self, image, sub, io_dir, **kw)

    monkeypatch.setattr(DockerRunner, "run", spy)
    assert iproofs_run("fake", image("fake"), 1) == 0, why(repo)
    (run_dir,) = run_dirs(repo, "fake")
    recorded = read(run_dir, "manifest.json")["commitment"]
    assert isinstance(recorded, dict)
    assert sent
    assert {job["commitment_id"] for job in sent} == {recorded["commitment_id"]}


@pytest.mark.skipif(not REAL, reason="needs real containers (IPROOFS_REAL_DOCKER=1)")
def test_network_none(repo: Path, image: Image) -> None:
    assert iproofs_run("fake", image("fake", "network"), 1) == 4
    found = failure(repo)
    assert (found["kind"], found["step"], found["exit_code"]) == ("adapter", "prove", 3), found
    assert any("network unreachable" in line for line in found["last_lines"])  # type: ignore[attr-defined]
