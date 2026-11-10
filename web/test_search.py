"""The search index of the fixture build: every system, reference, property and page once, each
leading somewhere real.

Run from the repository root: uv run pytest web -q
"""

import json
import re

import pytest


@pytest.fixture(scope="module")
def entries(site):
    return json.loads((site.out / "search.json").read_text())["entries"]


def test_every_kind(site, entries):
    # search finds systems, their sections, references, properties and the pages its label
    # promises; while /reference holds one reference, its entry stands for the page
    assert {x["kind"] for x in entries} == {"system", "section", "reference", "unbenchmarked",
                                            "property", "page"}  # fmt: skip
    pages = {x["url"] for x in entries if x["kind"] == "page"}
    one = len(site.view["orders"]["reference"]) == 1
    assert pages == {"/criteria", "/release"} | (set() if one else {"/reference"})
    if one:
        (ref,) = (x for x in entries if x["kind"] == "reference")
        assert "reference" in ref["terms"].split()


def test_every_entry_once(site, entries):
    # each name once in its group (every system has its own "Figures")
    keys = [(x["group"], x["name"]) for x in entries]
    assert len(keys) == len(set(keys))
    names = [x["name"] for x in entries]
    orders, rows = site.view["orders"], site.view["facts"]["rows"]
    want = {
        *(rows[s]["name"] for s in orders["benchmarked"]),
        *(rows[s]["name"] for s in orders["not_benchmarked"]),
        *(p["name"] for p in site.view["criteria"]["properties"]),
    }
    assert want <= set(names)
    assert sum(x["kind"] == "reference" for x in entries) == len(orders["reference"])


def test_every_url_leads_somewhere(site, entries):
    for x in entries:
        path, _, frag = x["url"].partition("#")
        page = site.out / f"{path.strip('/') or 'index'}.html"
        assert page.exists(), x["url"]
        if frag:
            assert len(re.findall(f' id="{re.escape(frag)}"', page.read_text())) == 1, x["url"]
