"""The search index: every system, reference, property and page once, each leading somewhere real.

Run: python3 -m pytest test_search.py   (or: python3 test_search.py)
"""

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build

ENTRIES = json.loads((build.HERE / "search.json").read_text())["entries"]


def test_index_is_the_built_one():
    assert build.search_entries() == ENTRIES


def test_no_pages():
    # the pages are in the nav; search finds systems and properties
    assert {x["kind"] for x in ENTRIES} == {"system", "reference", "unbenchmarked", "property"}


def test_every_entry_once():
    names = [x["name"] for x in ENTRIES]
    assert len(names) == len(set(names))
    want = {
        *(build.site["systems"][s]["name"] for s in build.PAGE),
        *(r["name"] for r in build.OV["not_benchmarked"]["rows"]),
        *(p["name"] for p in build.G["properties"]),
    }
    assert want <= set(names)
    assert sum(x["kind"] == "reference" for x in ENTRIES) == len(build.G["orders"]["reference"])


def test_not_benchmarked_are_marked_and_last():
    nb = [x for x in ENTRIES if x["kind"] == "unbenchmarked"]
    assert len(nb) == len(build.G["orders"]["not_benchmarked"])
    assert all(x["badge"] == "Not benchmarked" for x in nb)
    assert all(x["tier"] > y["tier"] for x in nb for y in ENTRIES if y["kind"] != "unbenchmarked")


def test_every_url_leads_somewhere():
    for x in ENTRIES:
        path, _, frag = x["url"].partition("#")
        page = build.file_of(path)
        assert page.exists(), x["url"]
        if frag:
            assert len(re.findall(f' id="{re.escape(frag)}"', page.read_text())) == 1, x["url"]


def test_family_words():
    # a system is found by the words people use for its family, not only by its own
    fp = next(x for x in ENTRIES if x["name"] == "FlashProve")
    assert "zk" in fp["terms"].split()


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
            print("ok", name)
