"""The placeholder release builds several test modules read, built once per session (#344).

`placeholder_build` is the deployed build (`extras=False`), `extras_build` the build with every
test-only case (`extras=True`): each the placeholder tree at `repo`, frozen by `iproofs release
freeze`, and the site `iproofs site build` wrote from it at `out`
(`fixtures.placeholder_release.build_site`, which raises when either command exits non-zero).
Under xdist each worker builds the ones its tests ask for, once.

Both are shared, so no test may change them: their files and directories are made read-only
while the session runs, and at its end the fixture fails if any file under `repo` or `out`
differs from what the build wrote (the digest also catches a write by root, which ignores the
modes). A test that edits a tree works on `writable_copy` of it. Bytecode caches
(`__pycache__/`, written when a test loads the tree's `web/build.py`) are left out of the digest.
"""

import contextlib
import hashlib
import os
import shutil
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

WRITE = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH


@dataclass(frozen=True)
class SiteBuild:
    repo: Path  # the placeholder release tree, frozen
    out: Path  # the site built from it


def _walk(root: Path) -> Iterator[Path]:
    """Every path under `root` except bytecode caches, sorted, `root` first."""
    yield root
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for name in sorted([*dirnames, *filenames]):
            yield Path(dirpath, name)


def tree_digest(root: Path) -> str:
    """sha256 over every path under `root` (bytecode caches left out) with its kind and bytes."""
    h = hashlib.sha256()
    for path in _walk(root):
        rel = path.relative_to(root).as_posix().encode()
        if path.is_symlink():
            h.update(b"L" + rel + b"\0" + os.readlink(path).encode() + b"\0")
        elif path.is_dir():
            h.update(b"D" + rel + b"\0")
        else:
            data = path.read_bytes()
            h.update(b"F" + rel + b"\0" + str(len(data)).encode() + b"\0" + data)
    return h.hexdigest()


def _read_only(root: Path) -> dict[Path, int]:
    """Clear every write bit under `root`; returns the modes to put back."""
    modes = {}
    for path in _walk(root):
        if not path.is_symlink():
            modes[path] = path.stat().st_mode
            path.chmod(modes[path] & ~WRITE)
    return modes


def writable_copy(src: Path, dst: Path) -> Path:
    """`shutil.copytree(src, dst)` with the owner's write bit back on every copied path and no
    bytecode cache, for a test that edits a shared tree."""
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
    for path in _walk(dst):
        if not path.is_symlink():
            path.chmod(path.stat().st_mode | stat.S_IWUSR)
    return dst


@contextlib.contextmanager
def kept_unchanged(*roots: Path) -> Iterator[None]:
    """Every write bit under `roots` cleared inside the block and put back after it; on leaving,
    AssertionError if any path under them (bytecode caches left out) was added, removed or
    changed in the block."""
    before = [tree_digest(r) for r in roots]
    modes = {k: v for r in roots for k, v in _read_only(r).items()}
    try:
        yield
    finally:
        for path, mode in modes.items():
            with contextlib.suppress(FileNotFoundError):  # a removed path: the digest tells
                path.chmod(mode)
    changed = [str(r) for r, b in zip(roots, before, strict=True) if tree_digest(r) != b]
    assert not changed, f"a test changed a shared build: {changed}"


def _shared(factory: pytest.TempPathFactory, name: str, *, extras: bool) -> Iterator[SiteBuild]:
    from fixtures.placeholder_release import build_site  # noqa: PLC0415 (heavy, used here only)

    root = factory.mktemp(name)
    built = SiteBuild(root / "repo", build_site(root / "repo", root / "out", extras=extras))
    with kept_unchanged(built.repo, built.out):
        yield built


@pytest.fixture(scope="session")
def placeholder_build(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SiteBuild]:
    """The deployed placeholder build (`extras=False`), shared and read-only (module doc)."""
    yield from _shared(tmp_path_factory, "placeholder", extras=False)


@pytest.fixture(scope="session")
def extras_build(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SiteBuild]:
    """The placeholder build with every test-only case (`extras=True`), shared and read-only."""
    yield from _shared(tmp_path_factory, "placeholder-extras", extras=True)
