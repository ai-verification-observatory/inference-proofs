"""The words the system pages print from a card or a quote, against hand-computed cases: every
word kept, only marks rendered. Run from the repository root: uv run pytest web -q
"""

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
