"""The words the system pages print from a card or a quote, against hand-computed cases: every
word kept, only marks rendered. Run from the repository root: uv run pytest web -q
"""

import re

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
