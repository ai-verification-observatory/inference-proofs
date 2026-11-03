"""RFC-0014 §The commitment record: verify sees only what the harness recorded at commit."""

import dataclasses
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from iproofs.adapter import InProcessRunner, StepResult
from iproofs.runner import JobSpec, Runner
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
FAKE = ROOT / "systems/fake"
ENV = {"IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78"}
VK = b"recorded verifier key, 32 bytes."
PK = b"recorded prover key, 32 bytes..."
Hook = Callable[[str, Path, dict[str, Any]], None]


class KeyedFake:
    """The fake adapter, plus verifier and prover files at commit and hooks around steps."""

    def __init__(
        self, before: Hook | None = None, after: Hook | None = None, *, forge: bool = False
    ) -> None:
        self.inner = InProcessRunner(FAKE / "entrypoint", REGISTRY, env=ENV)
        self.before, self.after, self.forge = before, after, forge

    def run(self, image: str, sub: str, io: Path, **kw: Any) -> StepResult:
        if self.before:
            self.before(sub, io, kw)
        result = self.inner.run(image, sub, io, **kw)
        assert result.out is not None
        if sub == "commit":
            (io / "state/vk.bin").write_bytes(VK)
            (io / "state/pk.bin").write_bytes(PK)
            out = dataclasses.replace(
                result.out, verifier_files=("/io/state/vk.bin",), prover_files=("/io/state/pk.bin",)
            )
            result = dataclasses.replace(result, out=out)
        if sub == "prove" and self.forge:
            result = forged(io, result)
        if self.after:
            self.after(sub, io, kw)
        return result


def forged(io: Path, result: StepResult) -> StepResult:
    """The prover forges its key file, echoes a commitment and ships the recorded key."""
    assert result.out is not None
    (io / "state/vk.bin").write_bytes(b"forged verifier key, 32 bytes..")
    out = json.loads((io / "out.json").read_text())
    (io / "out.json").write_text(json.dumps({**out, "commitment_id": "forged"}))
    (io / "report.bin").write_bytes(VK)
    out_doc = dataclasses.replace(result.out, binding_report="/io/report.bin")
    return dataclasses.replace(result, out=out_doc)


def run(tmp_path: Path, containers: KeyedFake) -> Path:
    spec = JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, False, str(tmp_path), "v0.1")
    image = "local/in-process@sha256:" + "0" * 64
    return Runner(containers, root=ROOT, registry=REGISTRY, image=image).run(spec)  # type: ignore[arg-type]


def test_verify_io_contains_only_recorded_commitment(tmp_path: Path) -> None:
    seen: list[tuple[set[str], bytes, str, list[tuple[Path, str]]]] = []
    prove_mounts: list[tuple[Path, str]] = []

    def before(sub: str, io: Path, kw: dict[str, Any]) -> None:
        if sub == "prove":
            prove_mounts.extend(kw["ro_mounts"])
        if sub == "verify":
            job = json.loads((io / "job.json").read_text())
            names = {p.name for p in io.iterdir()}
            seen.append(
                (
                    names,
                    (io / "verifier/vk.bin").read_bytes(),
                    job["commitment_id"],
                    kw["ro_mounts"],
                )
            )

    containers = KeyedFake(before, forge=True)
    run_dir = run(tmp_path, containers)
    doc = json.loads((run_dir / "run.json").read_text())
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert doc["status"] == "completed", doc["failure"]["message"]
    recorded = manifest["commitment"]
    assert [f["name"] for f in recorded["verifier_files"]] == ["vk.bin"]
    assert [f["name"] for f in recorded["prover_files"]] == ["pk.bin"]
    assert [target for _, target in prove_mounts] == ["/io/state/pk.bin"]  # read-only for prove
    assert seen
    for names, vk, commitment_id, mounts in seen:
        assert names == {"job.json", "verifier", "proof"}  # nothing else from the prover
        assert vk == VK  # the recorded file, not the prover's forged copy
        assert commitment_id == recorded["commitment_id"]
        assert [target for _, target in mounts] == ["/io/verifier"]
    assert any("names commitment_id" in w for w in doc["warnings"])
    assert any("binding report /io/report.bin equals" in w for w in doc["warnings"])
    events = [json.loads(line) for line in (run_dir / "logs/harness.jsonl").open()]
    assert sum(e["event"] == "policy.warning" for e in events) == 2
    assert sorted(p.name for p in run_dir.iterdir()) == [
        "digests.txt",
        "logs",
        "manifest.json",
        "run.json",
        "verifier",
    ]  # the store is scratch, like io/


def test_verifier_file_changed_before_verify_fails(tmp_path: Path) -> None:
    def after(sub: str, io: Path, kw: dict[str, Any]) -> None:
        if sub == "prove":  # the store changes on the host between commit and verify
            (io.parent / "commitment/verifier/vk.bin").write_bytes(b"x" * 32)

    run_dir = run(tmp_path, KeyedFake(after=after))
    doc = json.loads((run_dir / "run.json").read_text())
    assert doc["status"] == "failed"
    failure = doc["failure"]
    assert (failure["kind"], failure["step"]) == ("integrity", "verify")
    assert "vk.bin does not match the commit record" in failure["message"]
