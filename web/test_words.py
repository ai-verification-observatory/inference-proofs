"""The words the system pages print from a card or a quote, against hand-computed cases: every
word kept, only marks rendered. Run from the repository root: uv run pytest web -q
"""

import html
import re

import pytest

NNBSP = "\N{NARROW NO-BREAK SPACE}"


def test_card_text_renders_marks_and_keeps_words(site):
    b = site.build
    said = b.card_text('a `YES` from `cp_"x"` "is meant" and **pinned root**, the *sequence*')
    assert said == ("a <code>YES</code> from <code>cp_&quot;x&quot;</code> “is meant” and "
                    "<strong>pinned root</strong>, the <em>sequence</em>")  # fmt: skip
    # outer straight quotes turn curly; the full stop stays where the stored text has it
    assert (
        b.card_text('"Proofs are about the integer model".')
        == "“Proofs are about the integer model”."
    )
    # a lone product sign is no emphasis; a number keeps its percent sign
    assert b.card_text("bits = a * b") == "bits = a * b"
    assert b.card_text("3.11 % (one value)") == f"3.11{NNBSP}% (one value)"


def test_table_row_quote_is_a_one_row_table(site):
    b = site.build
    q = {"text": "each matmul's input | bound | nothing: the check itself", "repo": "o/r",
         "commit": "e" * 40, "path": "docs/statement.md", "lines": "L32",
         "url": "https://github.com/o/r/blob/" + "e" * 40 + "/docs/statement.md#L32"}  # fmt: skip
    said = b.quote_html(q)
    assert re.findall(r"<td>(.*?)</td>", said) == ["each matmul&#x27;s input", "bound",
                                                    "nothing: the check itself"]  # fmt: skip
    assert "“" not in said
    assert "|" not in said
    # a row quoted with its table's head: the head over it, so each cell says what it answers
    q["text"] = "# | edge | default\n12 | each matmul's input | bound"
    said = b.quote_html(q)
    assert re.findall(r'<th scope="col">(.*?)</th>', said) == ["#", "edge", "default"]
    assert re.findall(r"<td>(.*?)</td>", said) == ["12", "each matmul&#x27;s input", "bound"]
    q["text"] = "One bit per request is revealed."
    assert "<p>“One bit per request is revealed.”</p>" in b.quote_html(q)


def test_list_items_read_quote_then_source(site):
    """A list whose items have sources of their own prints the list's own source after the item
    that has none, so every item reads quote then source; a list with no item source keeps it
    above its items."""
    b = site.build
    url = "https://github.com/o/r/blob/" + "a" * 40 + "/known-limits.md#L{}"
    sources = {"residual": url.format(58), "residual.1": url.format(29)}
    said = b.card_value(["first", "second"], "residual", sources)
    items = re.findall(r"<li>(.*?)</li>", said)
    assert said.startswith('<ul class="cl">')
    assert items[0].startswith("first")
    assert '#L58"' in items[0]
    assert items[1].startswith("second")
    assert '#L29"' in items[1]
    assert '#L58"' not in items[1]
    said = b.card_value(["first", "second"], "residual", {"residual": url.format(58)})
    assert said.startswith('<p class="es">')
    assert said.count('#L58"') == 1


def test_deeper_source_keys_read_as_words(site):
    b = site.build
    url = "https://github.com/o/r/blob/" + "a" * 40 + "/THEOREM.md#L1"
    said = b.own_sources("security.notion", set(), {"security.notion.formal_name": url})
    assert ">formal name: " in re.sub(r"</?span[^>]*>", "", said)


def test_criteria_prints_not_stated_only_for_an_added_case(site):
    """The shared Not stated rule is printed once; a property's own Not stated row only where
    its rule adds a case ("Not stated, including <case>"), printed as the case."""
    b = site.build
    rule = "Not stated, including a proved run whose output tokens it does not name, or not copied yet."
    assert b.not_stated_case(rule) == "A proved run whose output tokens it does not name."
    assert b.not_stated_case("Not stated in the sources read, or not copied yet.") is None
    assert b.not_stated_case("No level stated for the configuration in the sources read.") is None
    text = (site.out / "criteria.html").read_text()
    for p in site.view["criteria"]["properties"]:
        sec = re.search(rf'<section class="crit" id="{p["id"]}".*?</section>', text, re.S)[0]
        case = b.not_stated_case(p["rules"]["not_stated"])
        assert ("Not stated</dt>" in sec) == (case is not None), p["id"]


def test_pairs_name_their_runs_and_why_others_join_none(site):
    """An overhead plate's pairs: each side's joined runs by date and ordinal, linked; each
    side's count carries in its title the runs left out and why (by hand)."""
    b = site.build
    rid = "2026-11-0{}-flashprove-fp-maverick-w1024-b24-prover-h200-hosted-{}"
    sid = "2026-11-09-ref-serve-fp-maverick-w1024-b24-serving-h200x4-hosted-{}"
    joined = {
        "system": [{"run_id": rid.format(9, 1), "record": "r/p1/run.json"}],
        "serving": [{"run_id": sid.format(n), "record": f"r/s{n}/run.json"} for n in (3, 4)],
        "left": [{"run_id": rid.format(8, n), "side": "system", "why": "first_proof_boundary"}
                 for n in (1, 2)] + [{"run_id": sid.format(1), "side": "serving",
                                      "why": "short_steady"}],
    }  # fmt: skip
    metric = "overhead_vs_production_prove.steady"
    cfg = {"overhead_runs": {metric: joined},
           "steady_boundary": "first-proof boundary (before 2026-11-09)"}  # fmt: skip
    f = {"metric": metric, "pairs": {"n_system": 1, "n_serving": 2, "min": 61.0, "max": 61.51}}
    said = b.pairs_html(cfg, f)
    text = re.sub(r'<span class="sr">.*?</span>|<[^>]+>', "", said).replace(
        "\N{NO-BREAK SPACE}", " "
    )
    assert text == ("1 prover run (2026-11-09 · 1 ↗) × 2 serving runs (2026-11-09 · 3 ↗, "
                    "2026-11-09 · 4 ↗), 61.00× to 61.51×")  # fmt: skip
    titles = re.findall(r'<span class="nw" title="([^"]+)">', said)
    assert titles == [
        "Left out: 2026-11-08 · 1, 2026-11-08 · 2: steady window from the first proof (runs "
        "before 2026-11-09), so they join no overhead",
        "Left out: 2026-11-09 · 1: steady scope under 60 s, so it joins no overhead",
    ]
    f["pairs"]["n_serving"] = 3  # a count its inputs do not hold stops the build
    with pytest.raises(RuntimeError):
        b.pairs_html(cfg, f)


def test_labels_read_whole(site):
    """A label reads as a phrase (by hand): the weight width with its basis and coverage, the
    older steady boundary, and a cost's record with the factor its reading unit applies."""
    b = site.build
    wb = {"bits": 8, "basis": "stated", "covers": "part"}
    cfg = {"workload": {"precision": {"weight_bits": wb}},
           "steady_boundary": "first-proof boundary (before 2026-11-09)"}  # fmt: skip
    assert b.bits_words(cfg) == (
        "8 bits per active weight, stated by the system, for part of the active weights"
    )
    assert b.boundary_words(cfg) == "steady window from the first proof (runs before 2026-11-09)"
    cost = {"unit": "USD/1k_token", "source": "x#/s/cost_per_1k_tokens_prove.session"}
    assert b.source_words(cost, {"source": "x#/s/"}) == "cost_per_1k_tokens_prove.session × 1,000"
    rate = {"unit": "token/s", "source": "x#/s/rate_prove.session"}
    assert b.source_words(rate, {"source": "x#/s/"}) == "rate_prove.session"


def test_system_descriptions_say_what_the_page_holds(site):
    """A system page's description names the system, the models and GPUs it ran and what the
    page holds, from the view: no number of its own and no words about itself."""
    b = site.build
    for sid in site.view["orders"]["benchmarked"]:
        cfgs = [c for c in site.view["configurations"] if c["system"] == sid]
        said = b.system_desc(sid)
        assert said.startswith(f"{site.view['facts']['rows'][sid]['name']} proving ")
        for c in cfgs:
            assert b.S.MODEL_NAME[c["workload"]["model"]["digest"]] in said
            assert b.gpu_words(c) in said
        assert "what one proof establishes" in said
        assert "benchmark's own" not in said
        text = (site.out / f"{sid}.html").read_text()
        assert f'<meta name="description" content="{html.escape(said)}">' in text


def test_serving_runs_name_what_their_statistics_leave_out(site):
    """A production-serving row names the runs its statistics read: "4 runs", or, where they
    leave a completed run out, "4 of 5 runs" with each such run and why in its title, read from
    its own records (by hand, after releases/v0.1 configurations[4])."""
    b = site.build
    rid = "2026-11-09-ref-serve-sash-l31-8b-c1024-serving-h200x1-hosted-{}"
    runs = [rid.format(n) for n in range(1, 6)]
    figs = {m: {"stats": {"n": 4}, "runs": runs[1:]} for m, _, _ in b.SERVING_COLS}
    cfg = {"figures": figs, "runs": {"completed": runs},
           "run_why": {runs[0]: "one_batch", runs[1]: "short_steady"}}  # fmt: skip
    said = b.serving_runs(cfg)
    assert re.sub(r"<[^>]+>", "", said) == "4 of 5 runs"
    assert html.unescape(re.search(r'title="([^"]+)"', said)[1]) == (
        "Left out: 2026-11-09 · 1: no steady window (one batch)"
    )
    cfg["runs"]["completed"] = runs[1:]
    assert b.serving_runs(cfg) == "4 runs"


def test_tamper_tests_say_each_thing_once(site):
    """RFC-0008: the tally prints each count once, in the weight of a figure; an accepted record
    that tampered only with a part verify does not read is counted bare, its block saying once
    that it tests nothing; the same control in another run reads as its trials and where they
    were kept (READ-3), not as a cause (by hand, after releases/v0.1 FlashProve b1)."""
    b = site.build
    rid = "2026-11-0{}-flashprove-fp-maverick-w1024-b1-prover-h200-hosted-{}"
    one, two = rid.format(8, 3), rid.format(9, 2)
    cfg = {
        "controls": {"counts": {"rejected": 9, "accepted": 1, "not_applicable": 8}},
        "accepted": [{"control": "C6", "not_read": ["response.y"]}],
        "control_runs": [{"run_id": one, "record": "r/1/controls.json"},
                         {"run_id": two, "record": "r/2/controls.json"}],
        "unexpected": [{
            "control": "C6", "run_id": one, "outcome": "accepted", "record": "r/1/controls.json",
            "stored": {"expected": ["rejected", "invalid_call"], "trials": []},
            "not_read": ["response.y"],
            "others": [{"run_id": two, "outcome": "rejected", "record": "r/2/controls.json",
                        "trials": 5, "trials_same": 5, "parts_not_read": ["response.y"]}],
        }],
    }  # fmt: skip

    def text(h):
        return re.sub(r'<span class="sr">.*?</span>|<[^>]+>', "", h).replace(
            "\N{NO-BREAK SPACE}", " "
        )

    tally = b.tamper_words(cfg)
    assert text(tally).endswith("rejected 9 · accepted 1 · did not apply 8")
    assert "<b>1</b>" in tally
    assert "tests nothing" not in tally
    full = text(b.unexpected_full(cfg))
    assert full.count("tests nothing") == 1
    assert (
        "5 of 5 trials rejected (flips kept off response.y, declared not read) · 2026-11-09 · 2"
        in full
    )
    assert b.tamper_words({"controls": {"counts": {}}, "accepted": [], "control_runs": []}) == ""


def test_control_notes_read_as_results(site):
    """A control's stored note as the page prints it: an operator's remedy left out, one reason
    in one set of words whichever control recorded it (by hand)."""
    b = site.build
    old = "no perturbed commitment; run iproofs controls --prepare-perturbed fp-maverick-w1024-b1"
    assert b.note_words(old) == "no perturbed commitment for this workload"
    assert b.note_words("no perturbed commitment for this workload") == (
        "no perturbed commitment for this workload"
    )
    assert b.note_words("the workload declares one precision") == (
        "the workload declares one precision"
    )


def test_card_reads_each_thing_once(site):
    """The card in full (by hand, after SASH's binding edges and FlashProve's quality gap): a
    list of same-shaped mappings is one table, its heads the source's own, a source of
    consecutive lines one link under it; an object's sources follow its fields; items sharing a
    lead, labels and a source print them once, every word kept; on the card's own page a link
    reads path and lines."""
    b = site.build
    blob = "https://github.com/o/r/blob/" + "a" * 40 + "/docs/statement.md#L{}"
    edges = [{"edge": "1 residual stream", "state": "bound", "switch": "--unsound-skip-x",
              "source": blob.format(21)},
             {"edge": "2 each matmul's input", "state": "bound", "switch": None,
              "source": blob.format(22)}]  # fmt: skip
    b.S.HOME = "o/r"
    try:
        said = b.card_value(edges, "binding.edges", {})
        assert re.findall(r'<th scope="col">([^<]+)</th>', said) == [
            "#",
            "edge",
            "default",
            "turned off by",
        ]
        cells = [re.sub(r"<[^>]+>", "", c) for c in re.findall(r"<td>(.*?)</td>", said)]
        assert cells == ["1", "residual stream", "bound", "--unsound-skip-x",
                         "2", "each matmul&#x27;s input", "bound", "—"]  # fmt: skip
        assert said.count("<a ") == 1
        assert "#L21-L22" in said
        assert re.sub(r"<[^>]+>", "", said).endswith(
            "docs/statement.md L21-L22\N{NO-BREAK SPACE}\N{NORTH EAST ARROW}"
        )
        # an object's own source after its last field
        obj = b.card_value({"kind": "x", "verifier": "y"}, "notion", {"notion": blob.format(3)})
        assert obj.index("verifier") < obj.index("#L3")
        gap = [{"metric": "positions that differ from the 16-bit model's, all texts",
                "value": "6.81 % (one value, 3 runs; a Python implementation; external)",
                "source": blob.format(45)},
               {"metric": "positions that differ from the same file's in float32",
                "value": "3.11 % (one value; a Python implementation; external)",
                "source": blob.format(46)}]  # fmt: skip
        text = re.sub(r"</(?:p|li)>", "|", b.gap_items({"quality_gap": gap}, "quality_gap"))
        text = html.unescape(re.sub(r"<[^>]+>", "", text)).replace("\N{NO-BREAK SPACE}", " ")
        assert text.replace("\N{NARROW NO-BREAK SPACE}", " ").strip("|").split("|") == [
            "positions that differ from:",
            "the 16-bit model's, all texts: 6.81 % (one value, 3 runs)",
            "the same file's in float32: 3.11 % (one value)",
            "both: a Python implementation; external",
            "docs/statement.md L45-L46 \N{NORTH EAST ARROW}",
        ]
    finally:
        b.S.HOME = ""
