import json
from pathlib import Path

import pytest

from iproofs.adapter import InProcessRunner
from iproofs.errors import ErrorKind, IProofsError
from iproofs.measure import files_bytes, proof_bytes, proof_size
from iproofs.provenance import proof_digest
from iproofs.runner import JobSpec, Runner
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")


def proof(io: Path, parts: dict[str, bytes], proof_id: str = "req-0") -> Path:
    d = io / "proofs" / proof_id
    d.mkdir(parents=True)
    for name, data in parts.items():
        (d / name).write_bytes(data)
    return d


def test_proof_bytes_exact(tmp_path: Path) -> None:
    """TC-PROOF-BYTES: bytes as stored, summed over parts."""
    d = proof(tmp_path, {"body.bin": b"x" * 1000, "tag.bin": b"y" * 32, "empty": b""})
    assert proof_bytes(d, tmp_path) == 1032
    size = proof_size(d, tmp_path)
    assert [(n, b) for n, b, _ in size.parts] == [("body.bin", 1000), ("empty", 0), ("tag.bin", 32)]


def test_proof_digest_matches_rfc0012(tmp_path: Path) -> None:
    d = proof(tmp_path, {"b.bin": b"1", "a.bin": b"2"})
    assert proof_size(d, tmp_path).digest == proof_digest(d)


def test_symlink_part_is_adapter_error(tmp_path: Path) -> None:
    d = proof(tmp_path, {"body.bin": b"x"})
    (d / "tag.bin").symlink_to(d / "body.bin")
    with pytest.raises(IProofsError) as e:
        proof_bytes(d, tmp_path)
    assert e.value.kind is ErrorKind.ADAPTER


def test_escape_is_adapter_error(tmp_path: Path) -> None:
    (tmp_path / "io").mkdir()
    (tmp_path / "secret").write_bytes(b"s")
    for bad in ["/io/../secret", "/etc/hosts"]:
        with pytest.raises(IProofsError) as e:
            files_bytes([bad], tmp_path / "io")
        assert e.value.kind is ErrorKind.ADAPTER


def test_files_bytes(tmp_path: Path) -> None:
    (tmp_path / "state").mkdir()
    (tmp_path / "state/vk.bin").write_bytes(b"v" * 7)
    (tmp_path / "state/pk.bin").write_bytes(b"p" * 5)
    assert files_bytes(["/io/state/vk.bin", "/io/state/pk.bin"], tmp_path) == 12


def test_size_metrics_in_a_fake_run(tmp_path: Path) -> None:
    env = {
        "IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78",
        "IPROOFS_FAKE_DELAY_S": "0",
    }
    runner = Runner(
        InProcessRunner(ROOT / "systems/fake/entrypoint", REGISTRY, env=env),
        root=ROOT,
        registry=REGISTRY,
        image="local/in-process@sha256:" + "0" * 64,
    )
    run_dir = runner.run(
        JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, False, str(tmp_path), "v0.1")
    )
    metrics = json.loads((run_dir / "run.json").read_text())["metrics"]
    assert metrics["proof_bytes"]["stats"]["n"] == 6
    assert metrics["proof_bytes"]["value"] == 64  # body 32 B + tag 32 B per proof
    assert metrics["proof_bytes_total"]["value"] == 384
    assert metrics["proof_bytes_per_token"]["value"] == 384 / 48
    assert metrics["verifier_download_bytes"]["value"] == 0  # the fake keeps no files
    assert metrics["proof_bytes"]["unit"] == "B"
    assert metrics["proof_bytes"]["grade"] == "measured"
