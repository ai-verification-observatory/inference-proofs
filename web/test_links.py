"""Links to other sites open in a new tab, with no opener and no referrer; the site's own links do not.

Run from the repository root: uv run pytest web -q
"""

import re
from pathlib import Path

import build
import pytest

WEB = Path(__file__).resolve().parent
PAGES = sorted(WEB.glob("*.html"))
A = re.compile(r"<a\s[^>]*>")


def attr(tag, name):
    m = re.search(rf'\b{name}="([^"]*)"', tag)
    return m and m[1]


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_external_links_open_in_a_new_tab(page):
    tags = A.findall(page.read_text())
    external = [t for t in tags if (attr(t, "href") or "").startswith(("http://", "https://"))]
    assert external, f"{page.name} links to no other site"
    for t in external:
        assert attr(t, "target") == "_blank", t
        assert set((attr(t, "rel") or "").split()) >= {"noopener", "noreferrer"}, t


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_site_links_stay_in_the_tab(page):
    for t in A.findall(page.read_text()):
        if not (attr(t, "href") or "").startswith(("http://", "https://")):
            assert attr(t, "target") is None, t


def test_new_tab_leaves_a_target_it_finds():
    html = '<a href="https://x.test/">x</a><a href="/sash">s</a><a target="_self" href="https://y.test/">y</a>'
    out = build.new_tab(html)
    assert out.count('target="_blank" rel="noopener noreferrer"') == 1
    assert '<a href="/sash">' in out
    assert '<a target="_self" href="https://y.test/">' in out
