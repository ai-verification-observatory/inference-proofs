import json
from pathlib import Path

import pytest

from iproofs import runner as runner_module
from iproofs import serialize
from iproofs.adapter import InProcessRunner
from iproofs.runner import JobSpec, Runner
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
FAKE = ROOT / "systems/fake"
ENV = {
    "IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78",
    "IPROOFS_FAKE_DELAY_S": "0",
}


def runner(keep_io: bool = False) -> Runner:
    return Runner(
        InProcessRunner(FAKE / "entrypoint", REGISTRY, env=ENV),
        root=ROOT,
        registry=REGISTRY,
        image="local/in-process@sha256:" + "0" * 64,
        keep_io=keep_io,
    )


def spec(results: Path) -> JobSpec:
    return JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, False, str(results), "v0.1")


def test_run_dir_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A crash while writing never leaves a run directory without run.json under results/."""
    real = serialize.write_json

    def crash_on_manifest(path: Path, obj: object) -> str:
        if path.name == "manifest.json":
            raise KeyboardInterrupt  # the runner is killed between file writes
        return real(path, obj)  # type: ignore[arg-type]

    monkeypatch.setattr(runner_module, "write_json", crash_on_manifest)
    with pytest.raises(KeyboardInterrupt):
        runner().run(spec(tmp_path))
    parent = tmp_path / "v0.1/fake"
    finals = [d for d in parent.iterdir() if not d.name.startswith(".staging-")]
    assert finals == []  # only the staging directory exists; crash recovery (#107) handles it
    assert [d.name.startswith(".staging-") for d in parent.iterdir()] == [True]


def test_invalid_document_kept_under_logs_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Runner, "_manifest", lambda self, job: {"schema": "manifest/1"})
    run_dir = runner().run(spec(tmp_path))
    doc = json.loads((run_dir / "run.json").read_text())
    assert doc["status"] == "failed"
    assert doc["failure"]["kind"] == "internal"
    assert doc["failure"]["step"] == "written"
    assert "manifest.json fails its schema" in doc["failure"]["message"]
    assert REGISTRY.errors("run/1", doc) == []
    assert (run_dir / "logs/invalid/manifest.json").is_file()
    assert not (run_dir / "manifest.json").exists()


def test_keep_io_retains_io_dir(tmp_path: Path) -> None:
    kept = runner(keep_io=True).run(spec(tmp_path / "kept"))
    assert (kept / "io/proofs").is_dir()
    assert (kept / "io/prove.out.json").is_file()
    plain = runner().run(spec(tmp_path / "plain"))
    assert not (plain / "io").exists()
    assert not (plain / "verify").exists()


def test_digests_txt_sorted(tmp_path: Path) -> None:
    run_dir = runner().run(spec(tmp_path))
    lines = (run_dir / "digests.txt").read_text().splitlines()
    assert lines == sorted(lines, key=str.encode)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    expected = sorted(f"proofs/{p['proof_id']}\t{p['digest']}" for p in manifest["proofs"])
    assert [line for line in lines if line.startswith("proofs/")] == expected
    assert len(expected) == 6
    logs = [line.split("\t")[0] for line in lines if not line.startswith("proofs/")]
    assert "logs/harness.jsonl" in logs  # every log's digest before any truncation (RFC-0009)
    assert all(name.startswith(("logs/", "archive/")) for name in logs)


def test_verifier_record_per_proof(tmp_path: Path) -> None:
    run_dir = runner().run(spec(tmp_path))
    names = sorted(p.name for p in (run_dir / "verifier").iterdir())
    assert names[:2] == ["req-0-1cpu.json", "req-0.json"]
    assert len([n for n in names if not n.endswith("-1cpu.json")]) == 6
