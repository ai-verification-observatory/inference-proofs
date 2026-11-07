"""RFC-0009 §Site rules on the pages `iproofs site build` writes (#320).

Page tests run over two builds: the placeholder release with every test-only case
(`extras=True`, never deployed) and the committed `web/` pages (the deployed build).
"""

import html
import json
import re
from pathlib import Path
from typing import Any

import pytest

from fixtures.placeholder_release import build_site
from iproofs.site import reply_html
from iproofs.site.view import site_view

ROOT = Path(__file__).resolve().parents[3]
VAL = re.compile(r'<a class="val" href="[^"]*" title="([^"]*)">(.*?)</a>', re.S)
ROW = re.compile(
    r'<div class="row" id="([^"]+)" role="row" data-name="([^"]+)" '
    r'data-k="([^"]+)">'
)
TABLE = re.compile(
    r'<div class="tbl" role="table".*?<div class="rows" role="rowgroup">'
    r"(.*?)</section>",
    re.S,
)
HEAD = re.compile(r'<div class="hc[^"]*" role="columnheader"[^>]*>(.*?)</div>')


def plain(text: str) -> str:
    return html.unescape(text).replace("\N{NO-BREAK SPACE}", " ")


@pytest.fixture(scope="module")
def extras(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("site")
    out = build_site(root / "repo", root / "out", extras=True)
    return {"out": out, "view": site_view(root / "repo")}


@pytest.fixture(scope="module", params=["extras", "web"])
def pages(request: pytest.FixtureRequest) -> dict[str, str]:
    out = request.getfixturevalue("extras")["out"] if request.param == "extras" else ROOT / "web"
    return {p.name: p.read_text("utf-8") for p in sorted(out.glob("*.html"))}


def test_page_set(pages: dict[str, str]) -> None:
    """RFC-0009 §Site page table, as far as #320 PR 1 writes it."""
    assert {"index.html", "reference.html", "criteria.html", "404.html"} <= set(pages)
    assert {"flashprove.html", "sash.html"} <= set(pages)


def test_every_number_has_labels(pages: dict[str, str]) -> None:
    """S2: every printed figure names its scope, grade, tier and its record in the index."""
    seen = 0
    for title, inner in VAL.findall(pages["index.html"]):
        if 'class="fig"' not in inner:
            continue
        for label in ("scope: ", "grade: ", "checked: ", "source: releases/"):
            assert label in plain(title), (label, title)
        seen += 1
    assert seen >= 6  # two systems, three measured figures each


def test_statistics_shown(pages: dict[str, str]) -> None:
    """S3: every figure with statistics shows its sample size and range on the overview; a
    reference row whose runs all failed shows its counts and that it is below the minimum."""
    for title, inner in VAL.findall(pages["index.html"]):
        if "spread: " not in html.unescape(title):
            continue
        sub = plain(re.sub(r"<[^>]+>", " ", inner))
        assert re.search(r"\d+ completed, \d+ failed", sub), sub
        assert " to " in sub, sub
    assert pages["index.html"].count("below minimum repetitions") == 2


def test_sort_key_is_stored_value(extras: dict[str, Any]) -> None:
    """S4: each sort key is the value the index stores, in its base unit."""
    index = (extras["out"] / "index.html").read_text()
    stored = {(c["system"], c["configuration"], c["workload"]["id"]): c
              for c in extras["view"]["configurations"]}  # fmt: skip
    metrics = {"covers": "tokens_covered_per_proof", "proof_size": "proof_bytes",
               "check_time": "verify_seconds",
               "overhead": "overhead_vs_serving_prove.session"}  # fmt: skip
    rows = ROW.findall(index)
    assert rows
    for rid, _, keys in rows:
        system, _, rest = rid.partition("--")
        configuration, _, workload = rest.partition("--")
        cfg = next(c for k, c in stored.items() if k[0] == system and (
            not configuration or (k[1], k[2]) == (configuration, workload)))  # fmt: skip
        got = json.loads(html.unescape(keys))
        for col, metric in metrics.items():
            assert got[col] == cfg["figures"][metric]["value"], (rid, col)


def test_default_order_alphabetical(pages: dict[str, str]) -> None:
    """S5: every table lists its systems A to Z by name; other orders only on request."""
    tables = TABLE.findall(pages["index.html"])
    assert tables
    for body in tables:
        names = [name for _, name, _ in ROW.findall(body)]
        assert names == sorted(names)
    assert 'aria-sort="ascending"' in pages["index.html"]


def test_no_ranking(pages: dict[str, str]) -> None:
    """S5: no score, rank or total column, and no highlighted row."""
    words = [re.sub(r"<[^>]+>", "", h) for h in HEAD.findall(pages["index.html"])]
    assert words
    assert not [w for w in words if re.search(r"score|rank|total|overall|best", w, re.I)]
    assert "<strong>" not in pages["index.html"]


def test_glyph_before_numbers(pages: dict[str, str]) -> None:
    """S1: on a system page the six properties come before the first figure."""
    for name in ("flashprove.html", "sash.html"):
        text = pages[name]
        assert text.index('class="rpie"') < text.index('class="plate"'), name


def test_pending_row_draws_no_state(extras: dict[str, Any]) -> None:
    """RFC-0016 OVR-8: a row under a pending disclosure draws none of the four states."""
    index = (extras["out"] / "index.html").read_text()
    row = index[index.index('<div class="row" id="sash"') :]
    row = row[: row.index('<div class="vals">')]
    assert len(re.findall(r'class="sl s\d none"', row)) == 6


def test_reply_escaped() -> None:
    out = reply_html("We *disagree*: <script>x</script> [notes](https://example.org/n)\n\n"
                     "- one\n- [bad](javascript:alert(1))")  # fmt: skip
    assert isinstance(out, str)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert '<a href="https://example.org/n">notes</a>' in out
    assert "<em>disagree</em>" in out
    assert 'href="javascript' not in out  # only http(s) links become links
    assert "<ul><li>one</li>" in out


def test_generated_html_passes_g8(pages: dict[str, str], tmp_path: Path) -> None:
    """S8: the site text passes the RFC-0013 G8 word list (replies are excluded at source)."""
    from iproofs.validate.tree import g8_language  # noqa: PLC0415

    for name, text in pages.items():
        (tmp_path / name).write_text(text)
    assert g8_language(tmp_path, [], named=sorted(pages)) == []
