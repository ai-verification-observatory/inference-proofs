"""RFC-0014 §Proof digests and archive: the deterministic archive of one proof."""

import json
import os
import tarfile
from pathlib import Path

from iproofs.adapter import InProcessRunner
from iproofs.provenance import archive_proof, file_digest
from iproofs.runner import JobSpec, Runner
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
ENV = {"IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78",
       "IPROOFS_FAKE_DELAY_S": "0"}  # fmt: skip


def proof(root: Path, mtime: int, mode: int) -> Path:
    d = root / "req-0"
    d.mkdir(parents=True)
    for name, data in (("tag.bin", b"t" * 32), ("body.bin", b"b" * 40)):  # written out of order
        (d / name).write_bytes(data)
        (d / name).chmod(mode)
        os.utime(d / name, (mtime, mtime))
    return d


def test_tar_is_deterministic(tmp_path: Path) -> None:
    a = archive_proof(proof(tmp_path / "a", 1_700_000_000, 0o600), tmp_path / "a.tar")
    b = archive_proof(proof(tmp_path / "b", 1_800_000_000, 0o755), tmp_path / "b.tar")
    assert a == b
    assert (tmp_path / "a.tar").read_bytes() == (tmp_path / "b.tar").read_bytes()
    assert a == (file_digest(tmp_path / "a.tar"), (tmp_path / "a.tar").stat().st_size)
    with tarfile.open(tmp_path / "a.tar") as tar:
        members = tar.getmembers()
        assert [m.name for m in members] == ["body.bin", "tag.bin"]
        assert {(m.mtime, m.uid, m.gid, m.mode, m.uname) for m in members} == {(0, 0, 0, 0o644, "")}
        assert tar.extractfile("body.bin").read() == b"b" * 40  # type: ignore[union-attr]
    assert (tmp_path / "a.tar").read_bytes()[257:263] == b"ustar\x00"  # POSIX ustar, uncompressed


def test_run_archives_one_proof_per_configuration(tmp_path: Path) -> None:
    containers = InProcessRunner(ROOT / "systems/fake/entrypoint", REGISTRY, env=ENV)
    runner = Runner(containers, root=ROOT, registry=REGISTRY, image="local/x@sha256:" + "0" * 64)
    spec = JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, False, str(tmp_path), "v0.1")
    dirs = runner.run_many(spec, 3)
    tars = sorted((tmp_path / ".archive/v0.1/fake/fake-tiny-ci/ci-cpu").glob("*.tar"))
    assert len(tars) == 1  # the first proof of repetition 1 only
    first = json.loads((dirs[0] / "run.json").read_text())
    accepted = sorted(first["proofs"], key=lambda p: p["release_mono_ns"])[0]["proof_id"]
    assert tars[0].name == f"{dirs[0].name}-{accepted}.tar"
    line = f"archive/{accepted}.tar\t{file_digest(tars[0])}\n"
    assert line in (dirs[0] / "digests.txt").read_text()
    assert all("archive/" not in (d / "digests.txt").read_text() for d in dirs[1:])
    manifest = json.loads((dirs[0] / "manifest.json").read_text())
    assert {p["archive"] for p in manifest["proofs"]} == {None}  # no uri until uploaded
