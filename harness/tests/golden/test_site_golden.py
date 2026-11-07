"""RFC-0009 §Site: every generated file of the placeholder release with its test cases, byte
for byte (S1 to S9 regressions), and the same bytes from a second build (CLI-4).

The golden holds the files `iproofs site build` writes from the release (pages, search index,
`vercel.json`, preview-card sources), not the static assets it copies (`words.css`, `words.js`,
fonts, pictures), so a font or picture change does not force a golden update.
"""

import shutil
from pathlib import Path

import pytest

from fixtures.placeholder_release import build_site

GOLDEN = Path(__file__).resolve().parent / "site"
GENERATED = ("*.html", "search.json", "vercel.json", "og/*.html", "og/icon.svg")


def generated(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for pattern in GENERATED for p in sorted(root.glob(pattern))}  # fmt: skip


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The placeholder release with every test-only case (`extras=True`), frozen and built."""
    root = tmp_path_factory.mktemp("site")
    return build_site(root / "repo", root / "out", extras=True)


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
