import dataclasses
import json
import os
from pathlib import Path

import pytest

from iproofs.adapter import IoDirs, check_proofs, read_out
from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import AdapterOut, System, load
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
PROVE_OUT = json.loads((ROOT / "schema/adapter-out/examples/valid/prove.json").read_text())


def fake_system(**changes: object) -> System:
    system = load(ROOT / "schema/system/examples/valid/fake.yaml", REGISTRY)
    assert isinstance(system, System)
    return dataclasses.replace(system, **changes)  # type: ignore[arg-type]


def released(io: Path, proof_id: str = "req-0", parts: dict[str, bytes] | None = None) -> Path:
    d = io / "proofs" / proof_id
    d.mkdir(parents=True)
    for name, data in (parts or {"body.bin": b"b", "tag.bin": b"t"}).items():
        (d / name).write_bytes(data)
    return d


def write_out(io: Path, out: dict[str, object]) -> AdapterOut:
    (io / "out.json").write_text(json.dumps(out))
    return read_out(IoDirs(io), REGISTRY, str(out["subcommand"]))


def adapter_error(fn: object, *args: object) -> str:
    with pytest.raises(IProofsError) as e:
        fn(*args)  # type: ignore[operator]
    assert e.value.kind is ErrorKind.ADAPTER
    return e.value.message


def test_path_safety_valid_prove(tmp_path: Path) -> None:
    released(tmp_path)
    (tmp_path / "proofs/.tmp-req-1").mkdir()
    out = write_out(tmp_path, PROVE_OUT)
    warnings = check_proofs(IoDirs(tmp_path), out, fake_system())
    assert warnings == ["/io/proofs/.tmp-req-1: unreleased temporary proof directory ignored"]


@pytest.mark.parametrize("bad", ["/io/../../etc/passwd", "/etc/passwd", "relative/x", "/models/x"])
def test_path_escape_rejected(tmp_path: Path, bad: str) -> None:
    assert "path" in adapter_error(IoDirs(tmp_path).host, bad, "commit")


def test_path_safety_symlink_escape_rejected(tmp_path: Path) -> None:
    (tmp_path / "state").mkdir()
    (tmp_path / "state/link").symlink_to("/etc")
    assert "escapes its mount" in adapter_error(IoDirs(tmp_path).host, "/io/state/link/passwd", "x")


def test_path_safety_out_paths_checked(tmp_path: Path) -> None:
    out = {**json.loads((ROOT / "schema/adapter-out/examples/valid/commit.json").read_text())}
    (tmp_path / "state").mkdir()
    (tmp_path / "state/vk.bin").symlink_to("/etc/hosts")
    (tmp_path / "out.json").write_text(json.dumps(out))
    assert "escapes its mount" in adapter_error(read_out, IoDirs(tmp_path), REGISTRY, "commit")


def test_path_safety_symlink_part_rejected(tmp_path: Path) -> None:
    d = released(tmp_path, parts={"body.bin": b"b"})
    (d / "tag.bin").symlink_to(d / "body.bin")
    out = write_out(tmp_path, PROVE_OUT)
    msg = adapter_error(check_proofs, IoDirs(tmp_path), out, fake_system())
    assert "INV-ADAPTER-8: /io/proofs/req-0/tag.bin is not a regular file" in msg


def test_path_safety_device_like_file_rejected(tmp_path: Path) -> None:
    # A FIFO stands in for a device node, which needs privileges to create.
    d = released(tmp_path, parts={"body.bin": b"b"})
    os.mkfifo(d / "tag.bin")
    out = write_out(tmp_path, PROVE_OUT)
    assert "not a regular file" in adapter_error(check_proofs, IoDirs(tmp_path), out, fake_system())


def test_unlisted_proof_is_adapter_failure(tmp_path: Path) -> None:
    released(tmp_path)
    released(tmp_path, "req-9")
    out = write_out(tmp_path, PROVE_OUT)
    msg = adapter_error(check_proofs, IoDirs(tmp_path), out, fake_system())
    assert "released but not listed ['req-9']" in msg


def test_listed_but_unreleased_is_adapter_failure(tmp_path: Path) -> None:
    (tmp_path / "proofs").mkdir()
    out = write_out(tmp_path, PROVE_OUT)
    msg = adapter_error(check_proofs, IoDirs(tmp_path), out, fake_system())
    assert "listed but not released ['req-0']" in msg


def test_path_safety_out_json_too_large(tmp_path: Path) -> None:
    with (tmp_path / "out.json").open("wb") as f:
        f.truncate(128 * 1024 * 1024 + 1)
    assert "larger than" in adapter_error(read_out, IoDirs(tmp_path), REGISTRY, "prove")


def test_path_safety_invalid_out_json(tmp_path: Path) -> None:
    (tmp_path / "out.json").write_text('{"schema": "adapter-out/1"}')
    assert "/io/out.json is invalid" in adapter_error(read_out, IoDirs(tmp_path), REGISTRY, "prove")


def test_path_safety_part_cap(tmp_path: Path) -> None:
    released(tmp_path, parts={"body.bin": b"b", "tag.bin": b"t", "extra.bin": b"e"})
    out = write_out(tmp_path, PROVE_OUT)
    msg = adapter_error(check_proofs, IoDirs(tmp_path), out, fake_system(max_proof_parts=2))
    assert "has 3 parts, cap 2" in msg


def test_path_safety_part_size_cap(tmp_path: Path) -> None:
    released(tmp_path, parts={"body.bin": b"12345", "tag.bin": b"t"})
    out = write_out(tmp_path, PROVE_OUT)
    msg = adapter_error(check_proofs, IoDirs(tmp_path), out, fake_system(max_proof_bytes=4))
    assert "/io/proofs/req-0/body.bin is larger than the 4-byte cap" in msg


def test_path_safety_parts_must_match_listing(tmp_path: Path) -> None:
    released(tmp_path, parts={"body.bin": b"b"})
    out = write_out(tmp_path, PROVE_OUT)
    msg = adapter_error(check_proofs, IoDirs(tmp_path), out, fake_system())
    assert "parts on disk ['body.bin'] != listed ['body.bin', 'tag.bin']" in msg


def test_path_safety_messages_never_name_host_paths(tmp_path: Path) -> None:
    released(tmp_path)
    released(tmp_path, "req-9")
    out = write_out(tmp_path, PROVE_OUT)
    assert str(tmp_path) not in adapter_error(check_proofs, IoDirs(tmp_path), out, fake_system())
