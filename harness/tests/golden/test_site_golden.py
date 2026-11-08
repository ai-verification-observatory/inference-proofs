"""RFC-0009 §Site: every generated file of the placeholder release with its test cases, byte
for byte (S1 to S9 regressions), and the same bytes from a second build (CLI-4).

The golden holds the files `iproofs site build` writes from the release (pages, search index,
`vercel.json`, preview-card sources), not the static assets it copies (`words.css`, `words.js`,
fonts, pictures), so a font or picture change does not force a golden update.
"""

import contextlib
import shutil
from pathlib import Path

import pytest

from fixtures.builds import SiteBuild, writable_copy
from fixtures.placeholder_release import build_site
from fixtures.repo import commit, git
from iproofs import cli

GOLDEN = Path(__file__).resolve().parent / "site"
GENERATED = ("*.html", "search.json", "vercel.json", "og/*.html", "og/icon.svg")


def generated(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for pattern in GENERATED for p in sorted(root.glob(pattern))}  # fmt: skip


@pytest.fixture(scope="module")
def site(extras_build: SiteBuild) -> Path:
    """The placeholder release with every test-only case (`extras=True`), frozen and built
    (the shared build, fixtures/builds)."""
    return extras_build.out


def test_site_matches_golden(site: Path, update_golden: bool) -> None:
    built = generated(site)
    if update_golden:
        shutil.rmtree(GOLDEN, ignore_errors=True)
        for rel, data in built.items():
            (GOLDEN / rel).parent.mkdir(parents=True, exist_ok=True)
            (GOLDEN / rel).write_bytes(data)
    golden = generated(GOLDEN)
    assert sorted(built) == sorted(golden)
    for rel in built:
        assert built[rel] == golden[rel], rel
    pages = {"index.html", "flashprove.html", "sash.html", "reference.html", "criteria.html",
             "404.html"}  # fmt: skip
    assert pages <= set(built)  # every page type the site writes today


def test_two_builds_same_bytes(site: Path, tmp_path: Path) -> None:
    """CLI-4: the same inputs give the same bytes."""
    again = build_site(tmp_path / "repo", tmp_path / "out", extras=True)
    assert generated(again) == generated(site)


def test_build_ignores_git(extras_build: SiteBuild, tmp_path: Path) -> None:
    """CLI-4: the build reads no git history and no tracking state, so a full clone, a depth-1
    clone (site.yml, Vercel) and a tree with no `.git` give the same bytes (#320 plan R4)."""
    full = writable_copy(extras_build.repo, tmp_path / "full")  # built and frozen (exit 0)
    commit(full, "freeze v0.1")  # the index committed, as a release pull request does
    shallow = tmp_path / "shallow"
    git(tmp_path, "clone", "-q", "--depth", "1", full.resolve().as_uri(), str(shallow))
    bare = tmp_path / "bare"
    shutil.copytree(full, bare, ignore=shutil.ignore_patterns(".git"))
    built = {}
    for tree in (full, shallow, bare):
        out = tmp_path / f"out-{tree.name}"
        with contextlib.chdir(tree):
            assert cli.main(["site", "build", "--out", str(out)]) == 0
        built[tree.name] = generated(out)
    assert not (bare / ".git").exists()
    assert built["full"] == built["shallow"] == built["bare"]
    assert set(built["full"]) == set(generated(GOLDEN))
