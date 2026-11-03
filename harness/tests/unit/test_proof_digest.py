"""RFC-0014: a proof changed on disk after its release is caught before it is used."""

import json
from pathlib import Path

import pytest

from iproofs.adapter import InProcessRunner
from iproofs.runner import JobSpec, Runner
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
ENV = {"IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78",
       "IPROOFS_FAKE_DELAY_S": "0"}  # fmt: skip


def tamper_after(monkeypatch: pytest.MonkeyPatch, step: str) -> None:
    """Flip one byte of the first proof's tag.bin right after `step` finishes."""
    original = getattr(Runner, step)

    def wrapped(self: Runner, job: object, *args: object) -> None:
        original(self, job, *args)
        part = job.staging / "io/proofs/req-0/tag.bin"  # type: ignore[attr-defined]
        data = bytearray(part.read_bytes())
        data[0] ^= 1
        part.write_bytes(bytes(data))

    monkeypatch.setattr(Runner, step, wrapped)


def run(tmp_path: Path, control_suite: bool) -> dict[str, object]:
    containers = InProcessRunner(ROOT / "systems/fake/entrypoint", REGISTRY, env=ENV)
    runner = Runner(containers, root=ROOT, registry=REGISTRY, image="local/x@sha256:" + "0" * 64)
    spec = JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, control_suite, str(tmp_path), "v0.1")
    doc: dict[str, object] = json.loads((runner.run(spec) / "run.json").read_text())
    return doc


def test_changed_part_detected_before_control(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tamper_after(monkeypatch, "_verify")
    doc = run(tmp_path, control_suite=True)
    assert doc["status"] == "failed"
    failure = doc["failure"]
    assert isinstance(failure, dict)
    assert (failure["kind"], failure["step"]) == ("integrity", "controls")
    assert "req-0 changed on disk after release" in failure["message"]


def test_changed_part_detected_before_verify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tamper_after(monkeypatch, "_prove")
    doc = run(tmp_path, control_suite=False)
    failure = doc["failure"]
    assert isinstance(failure, dict)
    assert (failure["kind"], failure["step"]) == ("integrity", "verify")
