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


def test_no_pages(entries):
    # the pages are in the nav; search finds systems and properties
    assert {x["kind"] for x in entries} == {"system", "reference", "unbenchmarked", "property"}


def test_every_entry_once(site, entries):
    names = [x["name"] for x in entries]
    assert len(names) == len(set(names))
    orders, rows = site.view["orders"], site.view["facts"]["rows"]
    want = {
        *(rows[s]["name"] for s in orders["benchmarked"]),
        *(rows[s]["name"] for s in orders["not_benchmarked"]),
        *(p["name"] for p in site.view["criteria"]["properties"]),
    }
    assert want <= set(names)
    assert sum(x["kind"] == "reference" for x in entries) == len(orders["reference"])


def test_not_benchmarked_are_marked_and_last(site, entries):
    nb = [x for x in entries if x["kind"] == "unbenchmarked"]
    assert len(nb) == len(site.view["orders"]["not_benchmarked"])
    assert all(x["badge"] == "Not benchmarked" for x in nb)
    assert all(x["tier"] > y["tier"] for x in nb for y in entries if y["kind"] != "unbenchmarked")


def test_every_url_leads_somewhere(site, entries):
    for x in entries:
        path, _, frag = x["url"].partition("#")
        page = site.out / f"{path.strip('/') or 'index'}.html"
        assert page.exists(), x["url"]
        if frag:
            assert len(re.findall(f' id="{re.escape(frag)}"', page.read_text())) == 1, x["url"]


def test_family_words(entries):
    # a system is found by the words people use for its family, not only by its own
    fp = next(x for x in entries if x["name"] == "FlashProve")
    assert "zk" in fp["terms"].split()
