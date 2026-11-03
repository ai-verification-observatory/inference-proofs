import hashlib
from pathlib import Path

from fixtures.synthetic_tree import generate


def digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(root).as_posix().encode() + b"\0" + p.read_bytes())
    return h.hexdigest()


def test_synthetic_tree_deterministic(tmp_path: Path) -> None:
    a, b = generate(tmp_path / "a"), generate(tmp_path / "b")
    assert len(a) == len(b) == 1000
    assert digest(tmp_path / "a") == digest(tmp_path / "b")
