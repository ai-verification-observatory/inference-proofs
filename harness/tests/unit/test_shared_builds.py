"""The guard on the shared placeholder builds (fixtures/builds, #344): read-only while tests
run, and a change to them fails the session whatever the user, root included."""

import stat
from pathlib import Path

import pytest

from fixtures.builds import WRITE, kept_unchanged, tree_digest, writable_copy


def small_tree(root: Path) -> Path:
    (root / "a/b").mkdir(parents=True)
    (root / "a/b/c.json").write_text("{}\n")
    (root / "d.txt").write_text("d\n")
    return root


def modes(root: Path) -> dict[str, int]:
    return {p.relative_to(root).as_posix(): p.stat().st_mode for p in [root, *root.rglob("*")]}


def test_read_only_inside_and_restored_after(tmp_path: Path) -> None:
    tree = small_tree(tmp_path / "t")
    start = modes(tree)
    with kept_unchanged(tree):
        assert all(m & WRITE == 0 for m in modes(tree).values())
    assert modes(tree) == start


def changed_in_block(tree: Path, change: str) -> None:
    with kept_unchanged(tree):
        dirs = (tree, tree / "a/b")
        for p in (*dirs, tree / "a/b/c.json"):
            p.chmod(p.stat().st_mode | stat.S_IWUSR)  # as root could write anyway
        if change == "edit":
            (tree / "a/b/c.json").write_text("[]\n")
        elif change == "add":
            (tree / "a/b/new").write_text("")
        elif change == "remove":
            (tree / "a/b/c.json").unlink()
        for p in (*dirs, tree / "a/b/c.json"):  # read-only again: only the digest can tell
            if p.exists():
                p.chmod(p.stat().st_mode & ~WRITE)
        if change == "chmod":
            (tree / "a/b/c.json").chmod(0o500)  # bytes unchanged: only the mode check can tell


@pytest.mark.parametrize(
    ("change", "seen_in"),
    [("edit", "contents"), ("add", "contents"), ("remove", "contents"), ("chmod", "modes")],
)
def test_change_fails_on_leaving(tmp_path: Path, change: str, seen_in: str) -> None:
    """A change slips past the modes when they do not bind (root); the digest still sees it.
    A chmod leaves the bytes alone, and would be undone silently when the modes are put back;
    the mode check sees it."""
    tree = small_tree(tmp_path / "t")
    with pytest.raises(AssertionError, match="changed a shared build") as caught:
        changed_in_block(tree, change)
    assert [k for k in ("contents", "modes") if f"{k} of" in str(caught.value)] == [seen_in]


def test_bytecode_cache_left_out(tmp_path: Path) -> None:
    tree = small_tree(tmp_path / "t")
    digest = tree_digest(tree)
    (tree / "a/__pycache__").mkdir()
    (tree / "a/__pycache__/x.pyc").write_bytes(b"\0")
    assert tree_digest(tree) == digest
    (tree / "a/b/c.json").write_text("[]\n")
    assert tree_digest(tree) != digest


def test_writable_copy(tmp_path: Path) -> None:
    tree = small_tree(tmp_path / "t")
    (tree / "a/__pycache__").mkdir()
    with kept_unchanged(tree):
        copy = writable_copy(tree, tmp_path / "copy")
        (copy / "a/b/c.json").write_text("[]\n")  # the copy is the test's to edit
        (copy / "a/b/new").write_text("")
    assert not (copy / "a/__pycache__").exists()
    assert (tree / "a/b/c.json").read_text() == "{}\n"
