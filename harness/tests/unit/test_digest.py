import hashlib
from pathlib import Path

import pytest

from iproofs import provenance
from iproofs.errors import ErrorKind, IProofsError
from iproofs.provenance import (
    check_digest,
    corpus_digest,
    file_digest,
    model_digest,
    prompt_set_digest,
    proof_digest,
)


def write(root: Path, files: dict[str, bytes]) -> Path:
    for name, data in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return root


def test_model_digest_known_vector(tmp_path: Path) -> None:
    """Expected value computed independently:

    x=$(printf 'x' | shasum -a 256 | cut -d' ' -f1)
    e=$(printf '' | shasum -a 256 | cut -d' ' -f1)
    n=$(printf '\\n' | shasum -a 256 | cut -d' ' -f1)
    printf 'a.bin\\t%s\\na/b.bin\\t%s\\nz\\t%s\\n' "$e" "$x" "$n" | shasum -a 256
    """
    root = write(tmp_path, {"a/b.bin": b"x", "a.bin": b"", "z": b"\n"})
    (root / "empty-dir").mkdir()  # empty subdirectories do not count
    assert model_digest(root) == (
        "sha256:51556c649bc128c39ee49f7174f10fedb2379d646fc29b1915ca84a6a23c764d"
    )


def test_sort_is_bytewise(tmp_path: Path) -> None:
    root = write(tmp_path, {"B": b"1", "a": b"2", "é": b"3"})
    lines = "".join(
        f"{n}\t{hashlib.sha256(d).hexdigest()}\n"
        for n, d in [("B", b"1"), ("a", b"2"), ("é", b"3")]
    )
    assert model_digest(root) == "sha256:" + hashlib.sha256(lines.encode()).hexdigest()


def test_symlink_rejected(tmp_path: Path) -> None:
    root = write(tmp_path / "m", {"w.bin": b"w"})
    (root / "link").symlink_to(root / "w.bin")
    with pytest.raises(IProofsError) as e:
        model_digest(root)
    assert e.value.kind is ErrorKind.INTEGRITY


def test_proof_digest_uses_part_names(tmp_path: Path) -> None:
    proof = write(tmp_path / "p1", {"body.bin": b"b", "tag.bin": b"t"})
    other = write(tmp_path / "p2", {"body.bin": b"b", "tag.bin": b"t"})
    assert proof_digest(proof) == proof_digest(other)


def test_proof_digest_rejects_nested_parts(tmp_path: Path) -> None:
    proof = write(tmp_path / "p", {"sub/part.bin": b"x"})
    with pytest.raises(IProofsError, match="nested part files"):
        proof_digest(proof)


def test_corpus_digest_uses_entry_id(tmp_path: Path) -> None:
    a = write(tmp_path, {"downloaded-name.txt": b"text"}) / "downloaded-name.txt"
    expected = f"gutenberg-1342\t{hashlib.sha256(b'text').hexdigest()}\n"
    assert corpus_digest({"gutenberg-1342": a}) == (
        "sha256:" + hashlib.sha256(expected.encode()).hexdigest()
    )


def test_file_and_prompt_set_digest(tmp_path: Path) -> None:
    p = write(tmp_path, {"prompts.jsonl": b'{"id":0}\n'}) / "prompts.jsonl"
    want = "sha256:" + hashlib.sha256(b'{"id":0}\n').hexdigest()
    assert file_digest(p) == prompt_set_digest(p) == want


@pytest.mark.parametrize(
    "bad", ["sha256:" + "A" * 64, "sha256:" + "a" * 63, "sha512:" + "a" * 64, "a" * 64, ""]
)
def test_check_digest_rejects_malformed(bad: str) -> None:
    with pytest.raises(IProofsError) as e:
        check_digest(bad)
    assert e.value.kind is ErrorKind.INTEGRITY


def test_check_digest_accepts_well_formed() -> None:
    good = "sha256:" + "0" * 64
    assert check_digest(good) == good


def test_hashing_several_files_at_once_gives_the_digests_of_a_loop(tmp_path: Path) -> None:
    """The model and proof digests are the same whether files are hashed one after another or
    several at a time, and a digest taken from hashes already in hand is the tree's digest."""
    files = {f"part-{i:02d}.bin": bytes([i]) * (3_000_000 + i) for i in range(12)}
    root = write(tmp_path, files | {"sub/config.json": b"{}"})
    paths = {name: root / name for name in [*files, "sub/config.json"]}
    one_by_one = {
        name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()
    }
    assert provenance.hex_digests(paths) == one_by_one
    assert provenance.listing_digest(one_by_one) == model_digest(root)
    partly = {name: one_by_one[name] for name in files}  # the nested file is hashed by the call
    assert provenance.checked_tree_digest(root, partly) == model_digest(root)
    wrong = partly | {"part-00.bin": "0" * 64}
    assert provenance.checked_tree_digest(root, wrong) != model_digest(root)
