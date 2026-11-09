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


def test_sections_found_by_what_they_hold(site, entries):
    """Each system page's sections, under the system's name, each leading to its anchor; the
    figures found by their names ("proof size", "check time"), and a system by the precision it
    proved."""
    b = site.build
    for sid in site.view["orders"]["benchmarked"]:
        name = site.view["facts"]["rows"][sid]["name"]
        mine = {x["name"]: x for x in entries if x["kind"] == "section" and x["group"] == name}
        assert set(mine) == {"Figures", "Tamper tests", "How we read it", "Claim card in full"}
        assert mine["Figures"]["url"] == f"/{sid}#figures"
        for col in (*b.COLS, *b.PER_GBIT_COLS):
            assert b.HEAD[col].lower() in mine["Figures"]["terms"], col
        system = next(x for x in entries if x["kind"] == "system" and x["name"] == name)
        for c in (c for c in site.view["configurations"] if c["system"] == sid):
            assert c["workload"]["precision"]["proved"].lower() in system["terms"].split()
    # words.js lists not-benchmarked systems last, then a match in the name before one in the
    # other words only, then a group's entries together (the page in view first)
    js = (site.web / "words.js").read_text()
    assert js.count("(a.x.tier === 5) - (b.x.tier === 5) || (a.r[0] === 2) - (b.r[0] === 2)") == 1
    assert (
        js.count("a.x.tier - b.x.tier || here(b) - here(a) || a.x.group.localeCompare(b.x.group)")
        == 1
    )


def test_sections_carry_their_system_and_figures(site, entries):
    """A section is found beside its system's name and models ("sash tamper"), which it holds
    apart from its terms (they never find it alone); a Figures section names each figure with
    the plate it leads to; a system shows the phrase it was found by, the precision it proved
    with its words among them."""
    b = site.build
    for sid in site.view["orders"]["benchmarked"]:
        name = site.view["facts"]["rows"][sid]["name"]
        models = {b.S.MODEL_NAME[c["workload"]["model"]["digest"]]
                  for c in site.view["configurations"] if c["system"] == sid}  # fmt: skip
        mine = [x for x in entries if x["kind"] == "section" and x["group"] == name]
        for x in mine:
            assert name.lower() in x["context"], x["name"]
            assert all(m.lower() in x["context"] for m in models), x["name"]
            assert name.lower() not in x["terms"].split(), x["name"]
        figs = next(x for x in mine if x["name"] == "Figures")["figures"]
        assert [f["name"] for f in figs][: len(b.COLS) + len(b.PER_GBIT_COLS)] == [
            b.HEAD[c] for c in (*b.COLS, *b.PER_GBIT_COLS)
        ]
        for f in figs:
            path, _, frag = f["url"].partition("#")
            page = (site.out / f"{path.strip('/')}.html").read_text()
            assert len(re.findall(f' id="{re.escape(frag)}"', page)) == 1, f["url"]
        system = next(x for x in entries if x["kind"] == "system" and x["name"] == name)
        for c in (c for c in site.view["configurations"] if c["system"] == sid):
            proved = c["workload"]["precision"]["proved"]
            said = site.view["facts"]["models"][c["workload"]["model"]["digest"]]
            words = said.get("precision_words", {}).get(proved)
            assert (f"{proved} ({words})" if words else proved) in system["found"]


def test_no_absence_is_searched_by(entries):
    """What a system's facts say is absent ("not named", "no LLM named", "none named", "size not
    stated", "model id as given", "no repository") shows on its card and is never a word it is
    found by."""
    for x in (x for x in entries if x["kind"] == "unbenchmarked"):
        for absent in ("not named", "none named", "no llm", "size not stated", "model id as given",
                       "no repository", "no public code"):  # fmt: skip
            assert absent not in x["terms"], (x["name"], absent)


def test_model_ids_beside_names(site):
    """An id a name already gives the family of is left to the line's title; an id the system
    names no other way is printed (by hand)."""
    b = site.build
    deep = {"models": ["GPT-2, Gemma 3, Llama 2", "google/gemma-3-1b-it (model id as given)",
                       "meta-llama/Llama-2-7b-hf (model id as given)"]}  # fmt: skip
    assert b.nb_models(deep) == "GPT-2, Gemma 3, Llama 2"
    assert b.nb_split(deep)[2] == ["google/gemma-3-1b-it", "meta-llama/Llama-2-7b-hf"]
    jolt = {"models": ["GPT-2 (125M)", "Qwen/Qwen2-0.5B (model id as given)"]}
    assert b.nb_models(jolt) == "GPT-2 (125M); Qwen/Qwen2-0.5B"
    assert b.nb_models({"models": ["not named"]}) == "Model not named"
    # quotes curly, as card text prints them
    assert b.nb_models({"models": ['LLaMA (branch "llama"), size not stated']}) == (
        "LLaMA (branch “llama”), size not stated"
    )
