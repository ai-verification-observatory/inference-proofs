"""The search index: every system, reference, property and page once, each leading somewhere real.

Run from the repository root: uv run pytest web -q
"""

import json
import re
from pathlib import Path

WEB = Path(__file__).resolve().parent
ENTRIES = json.loads((WEB / "search.json").read_text())["entries"]


def test_index_is_the_built_one(site):
    assert (site.out / "search.json").read_bytes() == (WEB / "search.json").read_bytes()


def test_no_pages():
    # the pages are in the nav; search finds systems and properties
    assert {x["kind"] for x in ENTRIES} == {"system", "reference", "unbenchmarked", "property"}


def test_every_entry_once(site):
    names = [x["name"] for x in ENTRIES]
    assert len(names) == len(set(names))
    orders, rows = site.view["orders"], site.view["facts"]["rows"]
    want = {
        *(rows[s]["name"] for s in orders["benchmarked"]),
        *(rows[s]["name"] for s in orders["not_benchmarked"]),
        *(p["name"] for p in site.view["criteria"]["properties"]),
    }
    assert want <= set(names)
    assert sum(x["kind"] == "reference" for x in ENTRIES) == len(orders["reference"])


def test_not_benchmarked_are_marked_and_last(site):
    nb = [x for x in ENTRIES if x["kind"] == "unbenchmarked"]
    assert len(nb) == len(site.view["orders"]["not_benchmarked"])
    assert all(x["badge"] == "Not benchmarked" for x in nb)
    assert all(x["tier"] > y["tier"] for x in nb for y in ENTRIES if y["kind"] != "unbenchmarked")


def test_every_url_leads_somewhere():
    for x in ENTRIES:
        path, _, frag = x["url"].partition("#")
        page = WEB / f"{path.strip('/') or 'index'}.html"
        assert page.exists(), x["url"]
        if frag:
            assert len(re.findall(f' id="{re.escape(frag)}"', page.read_text())) == 1, x["url"]


def test_family_words():
    # a system is found by the words people use for its family, not only by its own
    fp = next(x for x in ENTRIES if x["name"] == "FlashProve")
    assert "zk" in fp["terms"].split()
