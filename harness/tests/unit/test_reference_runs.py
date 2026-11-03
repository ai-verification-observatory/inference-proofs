"""RFC-0015 §Steps per job: TC-REF-SKIP, TC-REF-TOKENS, TC-PROMPTS-FROM."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from iproofs import cli

ROOT = Path(__file__).resolve().parents[3]
IMAGE = "ghcr.io/example/fake@sha256:" + "a" * 64


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The fake systems plus `fake-ref`, the fake entrypoint declared as a reference system."""
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
    ref = repo / "systems/fake-ref"
    ref.mkdir()
    shutil.copy(ROOT / "systems/fake/entrypoint", ref / "entrypoint")
    system = {
        "schema": "system/1",
        "name": "fake-ref",
        "kind": "reference",
        "reference_role": "recompute",
        "contract": "adapter/1",
        "engine": {"name": "fake", "version": "1", "image": IMAGE},
        "workloads": [
            {"id": "fake-tiny-ci", "precision_used": "int8", "precision_substitution": None,
             "engine_args": []}
        ],
        "deterministic_proofs": True,
        "incremental_proofs": True,
        "forbidden_flags": [],
    }  # fmt: skip
    (ref / "system.yaml").write_text(yaml.safe_dump(system))
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "fixture", "--no-gpg-sign"], check=True)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("IPROOFS_FAKE_DELAY_S", "0.02")  # releases apart, so steady is observable
    monkeypatch.setenv("IPROOFS_FAKE_UPSTREAM", "64168df9fd0706dfd955b6795fa6f535872dff78")
    return repo


def run(system: str, results: Path, *extra: str) -> int:
    argv = ["--quiet", "run", "--system", system, "--workload", "fake-tiny-ci"]
    argv += ["--profile", "ci-cpu", "--repetitions", "1", "--results", str(results)]
    return cli.main([*argv, "--in-process", *extra])


def only_run(results: Path, system: str) -> Path:
    (d,) = (results / "v0.1" / system).iterdir()
    return d


def test_reference_skips_commit_and_verify(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-REF-SKIP and TC-REF-TOKENS."""
    monkeypatch.setattr("iproofs.cli._containers", _in_process_any)
    # a reference system is held to its profile; this host is not ci-cpu, so allow it here
    assert run("fake-ref", repo / "results", "--allow-nonconforming") == 0
    d = only_run(repo / "results", "fake-ref")
    doc = json.loads((d / "run.json").read_text())
    manifest = json.loads((d / "manifest.json").read_text())
    assert doc["status"] == "completed", doc["failure"]
    assert doc["system_kind"] == "reference"
    events = [json.loads(line) for line in (d / "logs/harness.jsonl").open()]
    skipped = [e["to"] for e in events if e["event"] == "job.state" and e.get("skipped")]
    assert skipped == ["commit", "verify"]
    m = doc["metrics"]
    for metric in ("commit_seconds", "whole_wall_seconds"):
        assert (m[metric]["value"], m[metric]["null_reason"]) == (None, "not_applicable")
    assert m["prove_session_seconds"]["value"] > 0
    assert m["prove_steady_seconds"]["value"] > 0
    assert "proof_bytes" not in m  # outputs, not proofs
    assert "verify_seconds" not in m
    assert m["tokens_covered_total"]["value"] == 48  # fake's window rule: 8 per release, 6
    assert manifest["commitment"] is None
    assert not (d / "controls.json").exists()


def test_prompts_from_replays_the_source_run(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-PROMPTS-FROM: the same prompt digest as the source run; the source is recorded."""
    assert run("fake", repo / "results") == 0
    source = only_run(repo / "results", "fake")
    assert run("fake", repo / "replay", "--prompts-from", str(source)) == 0
    replay = only_run(repo / "replay", "fake")
    a, b = (json.loads((x / "manifest.json").read_text()) for x in (source, replay))
    assert a["workload"]["prompt_set_digest"] == b["workload"]["prompt_set_digest"]
    assert (a["prompts_from"], b["prompts_from"]) == (None, source.name)


def test_prompts_from_refuses_another_version_or_a_failed_run(repo: Path, tmp_path: Path) -> None:
    assert run("fake", repo / "results") == 0
    source = only_run(repo / "results", "fake")
    other = tmp_path / "other"
    shutil.copytree(source, other)
    manifest = json.loads((other / "manifest.json").read_text())
    manifest["workload"]["version"] = 2
    (other / "manifest.json").write_text(json.dumps(manifest))
    assert run("fake", repo / "x", "--prompts-from", str(other)) == 2  # config
    failed = tmp_path / "failed"
    shutil.copytree(source, failed)
    doc = json.loads((failed / "run.json").read_text())
    (failed / "run.json").write_text(json.dumps({**doc, "status": "failed"}))
    assert run("fake", repo / "y", "--prompts-from", str(failed)) == 2


def _in_process_any(  # type: ignore[no-untyped-def]
    system_file: Path, in_process: bool, image_id: str | None = None
):
    """The CLI runs only test systems in process; this test runs the reference fixture so."""
    from iproofs.adapter import InProcessRunner  # noqa: PLC0415
    from iproofs.schema import SchemaRegistry  # noqa: PLC0415

    registry = SchemaRegistry.from_tree(system_file.parents[2] / "schema")
    runner = InProcessRunner(system_file.parent / "entrypoint", registry,
                             env={"IPROOFS_FAKE_NAME": "fake-ref"})  # fmt: skip
    return runner, "local/in-process@sha256:" + "0" * 64, registry
