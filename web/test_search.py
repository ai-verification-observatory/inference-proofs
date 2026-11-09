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


def test_every_kind(entries):
    # search finds systems, references, properties and the pages its label promises
    assert {x["kind"] for x in entries} == {"system", "reference", "unbenchmarked", "property",
                                            "page"}  # fmt: skip
    pages = {x["url"] for x in entries if x["kind"] == "page"}
    assert pages == {"/reference", "/criteria", "/release"}


def test_found_by_what_they_ran(site, entries):
    # a system and production serving are found by the workload, GPU and engine they ran
    for x in entries:
        if x["kind"] not in ("system", "reference"):
            continue
        sid = x["url"].rsplit("#", 1)[-1] if x["kind"] == "reference" else x["url"].strip("/")
        for c in (c for c in site.view["configurations"] if c["system"] == sid):
            assert c["workload"]["id"] in x["terms"], (x["name"], c["workload"]["id"])
            if c["gpu"]["short"]:
                assert c["gpu"]["short"].lower() in x["terms"].split(), x["name"]


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


def test_not_benchmarked_are_grouped_and_last(site, entries):
    # no badge on a row: each entry names its group, the group words.js lists it under
    nb = [x for x in entries if x["kind"] == "unbenchmarked"]
    assert len(nb) == len(site.view["orders"]["not_benchmarked"])
    assert all(x["group"] == "Not benchmarked" for x in nb)
    assert not any("badge" in x for x in entries)
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
