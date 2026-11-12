"""The Learn pages: the Markdown subset they are written in, their links, their words and the
worked examples their explorers print. Run from the repository root: uv run pytest web -q
"""

import html
import json
import re
from pathlib import Path
from typing import Any

import pytest

LEARN = Path(__file__).resolve().parent / "learn"
HREF = re.compile(r'href="(/[^"#?]*)(?:\?[^"#]*)?(?:#([^"]*))?"')
ID = re.compile(r'\bid="([^"]+)"')
# AGENTS.md rule 10 and RFC-0018 SI-6: words the site does not use in its own voice. A
# publisher's own words (a `:::quote` block, or words between quotation marks) and a cited work's
# title (a `:::reading` block) are not the site's voice.
BANNED = re.compile(
    r"\b(secure|securely|best|neutral|independent|independently|fastest|winner|beats|"
    r"provably safe|state[- ]of[- ]the[- ]art|cutting[- ]edge|revolutionary|game[- ]chang\w+)\b",
    re.I,
)
QUOTED = re.compile(r'^:::(quote|reading)\b.*?^:::[ \t]*$|"[^"\n]*"', re.M | re.S)


def md(build: Any, text: str, terms: tuple[str, ...] = ()) -> str:
    draw = build.draw.learn
    entry = {"path": "web/learn/test.md", "text": text}
    ctx = draw.context(entry, set(terms))
    return str(draw.markdown(draw.text_of(entry), ctx))


def test_markdown_subset(board_site: Any) -> None:
    """Each construct of the subset draws what its docstring says."""
    b = board_site.build
    assert (
        md(b, "A *b* **c** `d<e`.") == "<p>A <em>b</em> <strong>c</strong> <code>d&lt;e</code>.</p>"
    )
    assert md(b, 'He said "yes".') == "<p>He said “yes”.</p>"
    assert md(b, "[x](/checks#run) [y](https://example.org/a)") == (
        '<p><a href="/checks#run">x</a> <a href="https://example.org/a">y</a></p>'
    )
    assert md(b, "[r](repo:rfcs/0018-level-1-ladder.md#cost)") == (
        '<p><a href="https://github.com/ai-verification-observatory/inference-proofs/blob/main/'
        'rfcs/0018-level-1-ladder.md#cost">r</a></p>'
    )
    assert md(b, "a [[Soundness|sound]] verifier", ("soundness",)) == (
        '<p>a <a class="df" href="/glossary#soundness">sound</a> verifier</p>'
    )
    assert (
        md(b, "## Two words\n\ntext") == '<h2 class="ah" id="two-words">Two words</h2><p>text</p>'
    )
    assert md(b, "- a\n- b\n  c") == '<ul class="ls"><li>a</li><li>b c</li></ul>'
    assert md(b, "1. a\n2. b") == '<ol class="ls"><li>a</li><li>b</li></ol>'
    assert md(b, "| A | B |\n|---|---|\n| 1 | 2 |") == (
        '<div class="tw"><table class="rt lt"><thead><tr><th scope="col">A</th>'
        '<th scope="col">B</th></tr></thead><tbody><tr><th scope="row">1</th><td>2</td></tr>'
        "</tbody></table></div>"
    )
    assert md(b, "```\na < b\n```") == '<pre class="code">a &lt; b</pre>'
    assert md(b, ":::note Mind\nthis\n:::") == (
        '<aside class="note"><p class="nh">Mind</p><p>this</p></aside>'
    )
    stage = md(b, ":::stage outside No other run\nwords\n:::")
    assert 'class="stage outside" id="no-other-run"' in stage
    assert '<p class="chip outside">Outside a proof' in stage
    quote = md(b, ":::quote https://example.org/r Publisher, README\nIts `own` words.\n:::")
    assert quote == (
        '<blockquote class="said2"><p>Its <code>own</code> words.</p><cite>'
        '<a href="https://example.org/r">Publisher, README</a></cite></blockquote>'
    )


@pytest.mark.parametrize(
    "text",
    [
        "a dash " + chr(0x2014) + " as punctuation",
        "a range 1" + chr(0x2013) + "2",
        "[[missing]]",
        "[x](ftp://example.org)",
        ":::nothing here\nwords\n:::",
        ":::note\nnever closed",
        ":::figure no-such-figure\n:::",
        "## Twice\n\n## Twice",
        "| A | B |\n| 1 | 2 |",
        "- a\n1. b",
        "```\ncode with no closing fence",
        "a stray * star",
        "an unread [bracket",
        "a lone ` backtick",
        "[x](//example.org/elsewhere)",
        "## Main",
        ":::figure session\n:::\n\n:::figure session\n:::",
        ":::reading\n:::",
    ],
)
def test_markdown_halts_outside_the_subset(board_site: Any, text: str) -> None:
    """Outside the subset the build stops; it never prints markup as text."""
    with pytest.raises(RuntimeError):
        md(board_site.build, text)


def learn_pages(board_site: Any) -> dict[str, str]:
    slugs = board_site.build.draw.learn.slugs()
    assert slugs[0] == "learn"
    assert len(slugs) > 10
    return {s: (board_site.out / f"{s}.html").read_text() for s in slugs}


def test_every_listed_page_is_built_and_linked(board_site: Any) -> None:
    """The hub links every page of the index; each page of a track names its place in it."""
    pages = learn_pages(board_site)
    hub = pages["learn"]
    for slug in pages:
        if slug != "learn":
            assert f'href="/{slug}"' in hub, slug
    view = board_site.build.draw.state.V["learn"]
    for track in view["tracks"]:
        for k, entry in enumerate(track["pages"], start=1):
            text = pages[entry["slug"]]
            assert f"{k} of {len(track['pages'])}" in text, entry["slug"]
            assert (
                f'<h1 id="h-name" class="sysname lt-h">{html.escape(entry["title"])}</h1>' in text
            )


def test_site_links_resolve(board_site: Any) -> None:
    """Every link of a Learn page to a page of the site names a page the build wrote, and where
    it names a place in it, an id that page holds. The same for the links that lead to the Learn
    pages from the checks page and the mandate."""
    out = board_site.out
    ids = {p.stem: set(ID.findall(p.read_text())) for p in out.glob("*.html")}
    ids[""] = ids["index"]
    sources = {**learn_pages(board_site),
               "checks": (out / "checks.html").read_text(),
               "mandate": (out / "mandate.html").read_text()}  # fmt: skip
    seen = 0
    for name, text in sources.items():
        for path, frag in HREF.findall(text):
            target = path.strip("/")
            if target.split("/")[0] in ("fonts", "og") or "." in target:
                continue  # a file of the site, not a page
            assert target in ids, (name, path)
            if frag:
                assert html.unescape(frag) in ids[target], (name, path, frag)
            seen += 1
    assert seen > 100


def test_words_follow_the_house_rules() -> None:
    """In the site's own voice: none of the words rule 10 and SI-6 exclude, and no release
    before Level 1 named (SI-5). Checked on the texts, outside quotes and reading lists."""
    for path in sorted([*LEARN.glob("*.md"), LEARN / "index.yaml"]):
        text = QUOTED.sub("", path.read_text())
        found = BANNED.search(text)
        assert found is None, (
            path.name,
            found[0],
            text[max(0, found.start() - 60) : found.end() + 20],
        )
        assert "v0.1" not in text, path.name


def test_glossary_holds_every_term_once(board_site: Any) -> None:
    """A term is defined once (AGENTS.md, Writing style): the glossary's ids are distinct, and
    the search index lists each term at its own address."""
    entries = board_site.build.draw.learn.glossary_entries()
    ids = [tid for _, tid, _ in entries]
    assert len(ids) == len(set(ids))
    assert len(ids) > 20
    assert all(first.endswith(".") and len(first) > 20 for _, _, first in entries)
    index = json.loads((board_site.out / "search.json").read_text())
    listed = {x["url"] for x in index["entries"]}
    assert {f"/glossary#{tid}" for tid in ids} <= listed


def test_code_keeps_its_quotes_and_a_quote_block_its_dash(board_site: Any) -> None:
    """Quotes are set curly in the site's words and left as typed in code; a closing `:::` with
    a space after it still ends the publisher's words, so the dash check sees what follows."""
    b = board_site.build
    assert md(b, 'Run `print("x")` and say "x".') == (
        "<p>Run <code>print(&quot;x&quot;)</code> and say “x”.</p>"
    )
    dash = chr(0x2014)
    with pytest.raises(RuntimeError):
        md(b, f":::quote https://example.org Who\ntheir {dash} words\n::: \n\nour {dash} words")


def test_a_learn_page_cannot_take_another_pages_address(board_site: Any) -> None:
    """A slug of web/learn/index.yaml that is a site page, a redirect or a system stops the
    build: it would silently replace that page, or be hidden behind its redirect."""
    build = board_site.build
    whole = build.draw.state.V
    view = json.loads(json.dumps(whole))
    view["learn"]["tracks"][0]["pages"][0]["slug"] = "checks"
    try:
        with pytest.raises(RuntimeError, match="taken by another page"):
            build.setup(view, board_site.out)
    finally:
        build.setup(whole, board_site.out)


def test_worked_examples(board_site: Any) -> None:
    """The explorers' arithmetic against hand-computed cases."""
    f = board_site.build.draw.figures
    # A·B by hand, and the one changed entry of the claimed product
    assert f.matmul(f.FA, f.FB) == ((5, 4, 1), (1, 5, 3), (6, 1, 3))
    assert f.claimed(False)[1][2] == 4
    # r = (1, 0, 1) reads the changed column: A·(B·r) = (6, 4, 9), C·r = (6, 5, 9)
    caught = f.random_check((1, 0, 1))
    assert (caught["left"], caught["right"], caught["equal"]) == ((6, 4, 9), (6, 5, 9), False)
    # r = (1, 1, 0) does not read it
    assert f.random_check((1, 1, 0))["equal"]
    # of the 8 vectors of bits, the 4 with r[2] = 1 catch the change: one half
    bits = [(a, b, c) for a in (0, 1) for b in (0, 1) for c in (0, 1)]
    assert sum(not f.random_check(r)["equal"] for r in bits) == 4
    # the sumcheck of <(2,7,1,8), (3,1,4,1)> = 25 modulo 97, challenges 5 and 11.
    # Round 1 by hand: s(0) = 2·3 + 7·1 = 13, s(1) = 1·4 + 8·1 = 12, s(2) = 0·5 + 9·1 = 9.
    run = f.sumcheck()
    assert run["claim"] == 25
    assert run["rounds"][0]["s"] == (13, 12, 9)
    # s(5) through (0,13), (1,12), (2,9): s(X) = 13 - X^2, so s(5) = -12 = 85 modulo 97
    assert run["rounds"][0]["next"] == 85
    assert run["accepted"]
    assert run["final"] == run["rounds"][1]["next"]
    lying = f.sumcheck(lie=1)
    assert lying["claim"] == 26
    assert not lying["accepted"]
    # a lie survives exactly when a challenge is 1 or 2 (the other values the prover sent
    # stay true there): 97^2 - 95^2 = 384 of the 9,409 pairs, under the bound 2·2/97
    survived = sum(f.sumcheck((a, b), lie=1)["accepted"] for a in range(f.P) for b in range(f.P))
    assert survived == 384
    assert survived / f.P**2 <= 2 * 2 / f.P
    assert all(f.sumcheck((a, b))["accepted"] for a in (0, 1, 2, 50, 96) for b in (0, 3, 96))
    # every reply generated at the cost of serving, 1 in 100 proved at 100 times it: twice the
    # serving bill. Every reply proved: the two parts add up to the row's multiple
    assert f.bill(0.01, 1, 100) == 2
    assert f.bill(1, 10, 100) == 110
    assert f.times(f.bill(0.001, 1, 1000)) == "2×"
    # the sampling figures the treaty page and "Before you rely" state in words: a swap of 1
    # reply in 100 is caught by 300 draws about 95 times in 100, 1 in 10,000 about 3 times in 100
    assert round(100 * (1 - 0.99**300)) == 95
    assert round(100 * (1 - 0.9999**300)) == 3


def test_learn_styles_touch_no_other_page() -> None:
    """words.css names its classes in two or three letters, so a new rule can restyle an old
    page by accident (a rule for `.tl` once moved every page's header). Every selector of the
    Learn section holds a class that no rule outside the section uses."""
    css = re.sub(r"/\*.*?\*/", "", (LEARN.parent / "words.css").read_text(), flags=re.S)
    css = re.sub(r"@font-face\{[^}]*\}", "", css)
    start = css.index(".kick {")
    end = css.index(".foot {")
    learn, rest = css[start:end], css[:start] + css[end:]
    used_elsewhere = set(
        re.findall(r"\.([a-zA-Z][\w-]*)", "".join(re.findall(r"([^{}]+)\{", rest)))
    )
    for block in re.findall(r"([^{}]+)\{", learn):
        for selector in (part.strip() for part in block.split(",")):
            if not selector or selector.startswith("@"):
                continue
            classes = set(re.findall(r"\.([a-zA-Z][\w-]*)", selector))
            assert classes - used_elsewhere, f"{selector!r} restyles classes of other pages"
