import json
import os
from pathlib import Path

import pytest

from iproofs import cli, serialize
from iproofs import runner as runner_module
from iproofs.adapter import InProcessRunner
from iproofs.errors import ErrorKind, IProofsError
from iproofs.runner import JobSpec, Runner, _boot_id
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
FAKE = ROOT / "systems/fake"
ENV = {
    "IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78",
    "IPROOFS_FAKE_DELAY_S": "0",
}


def runner() -> Runner:
    return Runner(
        InProcessRunner(FAKE / "entrypoint", REGISTRY, env=ENV),
        root=ROOT,
        registry=REGISTRY,
        image="local/in-process@sha256:" + "0" * 64,
    )


def crashed_staging(results: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A job killed while writing its documents, with a dead pid in its lock."""
    real = serialize.write_json

    def crash(path: Path, obj: object) -> str:
        if path.name == "run.json":
            raise KeyboardInterrupt
        return real(path, obj)  # type: ignore[arg-type]

    monkeypatch.setattr(runner_module, "write_json", crash)
    with pytest.raises(KeyboardInterrupt):
        runner().run(JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, False, str(results), "v0.1"))
    monkeypatch.setattr(runner_module, "write_json", real)
    staging = next((results / "v0.1/fake").glob(".staging-*"))
    lock = json.loads((staging / "job.lock").read_text())
    lock["pid"] = 2**22 + 7  # no such process
    (staging / "job.lock").write_text(json.dumps(lock))
    return staging


def test_crash_recovery_records_internal_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = crashed_staging(tmp_path, monkeypatch)
    [recovered] = runner().recover(tmp_path)
    assert not staging.exists()
    assert recovered.name == staging.name.removeprefix(".staging-")
    doc = json.loads((recovered / "run.json").read_text())
    assert doc["status"] == "failed"
    assert doc["failure"]["kind"] == "internal"
    assert doc["failure"]["step"] == "verify"  # the last state the job reached
    assert doc["failure"]["message"] == "runner terminated before completion"
    assert REGISTRY.errors("run/1", doc) == []
    manifest = json.loads((recovered / "manifest.json").read_text())
    assert REGISTRY.errors("manifest/1", manifest) == []
    log = (recovered / "logs/harness.jsonl").read_text()
    assert '"event":"runner.recovered"' in log


def test_live_staging_blocks_runner(tmp_path: Path) -> None:
    staging = tmp_path / "v0.1/fake/.staging-2026-11-20-fake-fake-tiny-ci-ci-cpu-1"
    staging.mkdir(parents=True)
    (staging / "job.lock").write_text(json.dumps({"pid": os.getpid(), "boot_id": _boot_id()}))
    with pytest.raises(IProofsError) as e:
        runner().recover(tmp_path)
    assert e.value.kind is ErrorKind.ENVIRONMENT


def test_cli_exits_3_on_live_staging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)
    staging = tmp_path / "v0.1/fake/.staging-x"
    staging.mkdir(parents=True)
    (staging / "job.lock").write_text(json.dumps({"pid": os.getpid(), "boot_id": _boot_id()}))
    code = cli.main(
        [
            "run",
            "--system",
            "fake",
            "--workload",
            "fake-tiny-ci",
            "--profile",
            "ci-cpu",
            "--results",
            str(tmp_path),
            "--in-process",
            "--repetitions",
            "1",
        ]
    )
    assert code == 3
