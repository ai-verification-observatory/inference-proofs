"""The breakpoints in words.css: one scale of widths, one block per width query, wide to narrow.

The scale is the list of widths in the comment that heads the narrower section of words.css
("Breakpoints (px): ..."); web/README.md lists the same widths. A width query opens one block,
uses only widths of the scale (a min-width is a scale width plus 1 px, for 561 to 960 say), sets
each selector once (a selector list counts as each of its selectors), and comes after every block
for wider screens. The hover, reduced-motion, print, forced-colours and landscape (max-height) queries are
not width blocks: they may repeat and keep their places, but a width inside one is still on the scale.

Run from the repository root: uv run pytest web -q
"""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parent
CSS = (WEB / "words.css").read_text()
SCALE_LINE = re.compile(r"Breakpoints \(px\):\s*((?:\d+\s+)*\d+)")
WIDTH = re.compile(r"\((min|max)-width:\s*(\d+)px\)")
OUTSIDE = ("hover", "prefers-reduced-motion", "print", "forced-colors", "max-height")


def scale_of(text: str) -> list[int]:
    """The widths a "Breakpoints (px): ..." line lists, in its order."""
    m = SCALE_LINE.search(text)
    assert m, "no 'Breakpoints (px):' line"
    return [int(w) for w in m.group(1).split()]


def media_blocks(css: str) -> list[tuple[str, str]]:
    """Each top-level @media rule as (query, body), comments removed, in file order."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out, i = [], 0
    while (at := css.find("@media", i)) != -1:
        start = css.index("{", at)
        depth, j = 1, start + 1
        while depth:
            depth += {"{": 1, "}": -1}.get(css[j], 0)
            j += 1
        out.append((" ".join(css[at + len("@media") : start].split()), css[start + 1 : j - 1]))
        i = j
    return out


def selectors(body: str) -> list[str]:
    """Each selector a block body sets, a list split at its top-level commas, whitespace normalised."""
    out = []
    for group in re.findall(r"([^{}]+)\{[^{}]*\}", body):
        depth, part = 0, ""
        for ch in group:
            depth += {"(": 1, ")": -1}.get(ch, 0)
            if ch == "," and not depth:
                out.append(" ".join(part.split()))
                part = ""
            else:
                part += ch
        out.append(" ".join(part.split()))
    return out


def width_problems(query: str, widths: list[tuple[str, str]], scale: list[int]) -> list[str]:
    """What is wrong with the widths of one query: [] when each is on the scale and the range is not empty."""
    found = []
    kinds = [kind for kind, _ in widths]
    if kinds.count("min") > 1 or kinds.count("max") > 1:
        found.append(f"@media {query}: more than one min-width or max-width")
    for kind, px in widths:
        if kind == "max" and int(px) not in scale:
            found.append(f"@media {query}: {px} px is not on the scale")
        if kind == "min" and int(px) - 1 not in scale:
            found.append(f"@media {query}: {px} px is not a scale width plus 1 px")
    bounds = {kind: int(px) for kind, px in widths}
    if "min" in bounds and "max" in bounds and bounds["min"] - 1 >= bounds["max"]:
        found.append(f"@media {query}: an empty range")
    return found


def problems(css: str, scale: list[int]) -> list[str]:
    """What breaks the scale in a stylesheet: [] when nothing does."""
    found: list[str] = []
    if scale != sorted(set(scale), reverse=True):
        found.append(f"the scale is not one list of widths, wide to narrow: {scale}")
    seen: set[tuple[tuple[str, int], ...]] = set()
    last = None  # (key, query) of the previous width block: its lower edge, the further down the file the narrower
    for query, body in media_blocks(css):
        widths = WIDTH.findall(query)
        if any(word in query for word in OUTSIDE):
            # not a width block: it may repeat and keeps its place, but its widths are on the scale
            found += width_problems(query, widths, scale)
            continue
        if not widths or WIDTH.sub("", query).replace("and", "").strip():
            found.append(f"@media {query}: not a min-width or max-width query")
            continue
        found += width_problems(query, widths, scale)
        # the same bounds are the same width query, however the text is spaced
        same = tuple(sorted((kind, int(px)) for kind, px in widths))
        if same in seen:
            found.append(f"@media {query}: a second block for this width")
        seen.add(same)
        bounds = {kind: int(px) for kind, px in widths}
        # a max-width block applies down to 0 and sits by its max; a block with a min-width sits by
        # its min - 1, just above the block of that width, so it overrides every wider block in its range
        key = (bounds["min"] - 1, 1) if "min" in bounds else (bounds.get("max", 0), 0)
        if last and key > last[0]:
            found.append(f"@media {query}: comes after {last[1]}, a block for narrower screens")
        last = (key, query)
        names = selectors(body)
        for name in sorted({n for n in names if names.count(n) > 1}):
            found.append(f"@media {query}: {name} set twice")
    return found


def test_words_css_is_on_the_scale():
    assert problems(CSS, scale_of(CSS)) == []


def test_every_width_of_the_scale_is_used():
    queries = [q for q, _ in media_blocks(CSS) if not any(word in q for word in OUTSIDE)]
    used = {int(px) - (kind == "min") for q in queries for kind, px in WIDTH.findall(q)}
    assert set(scale_of(CSS)) == used


def test_readme_lists_the_same_scale():
    assert scale_of((WEB / "README.md").read_text()) == scale_of(CSS)


def test_what_the_build_reads_stays():
    # the build reads the fonts markers, the :root inks and the slice lifts from words.css
    assert "/* fonts: written by build.py */" in CSS
    assert "/* /fonts */" in CSS
    assert re.search(r":root \{[^}]*--yes: #[0-9a-f]{6};", CSS)
    assert all(
        re.search(rf"\.s{n} \{{ --dx: -?[\d.]+; --dy: -?[\d.]+; }}", CSS) for n in range(1, 7)
    )


SCALE = [960, 560, 360]
VALID = """
.a { color: red; }
@media (hover: hover) { .a:hover { color: blue; } }
@media (max-width: 960px) { .a { margin: 0; } .b { margin: 0; } }
/* @media (max-width: 961px) { a comment is not a rule } */
@media (min-width: 561px) and (max-width: 960px) { .a { padding: 0; } }
@media (max-width: 560px) {
  .a { margin: 1px; }
  .a .b, .b { margin: 2px; }
  :is(.a, .b) .c { margin: 3px; }
}
@media (min-width: 361px) and (max-width: 560px) { .b { padding: 1px; } }
@media (max-width: 360px) { .a { margin: 2px; } }
@media (prefers-reduced-motion: reduce) { * { animation: none !important; } }
@media (max-height: 500px) and (orientation: landscape) { .a { padding: 0; } }
@media (max-height: 500px) and (orientation: landscape) and (max-width: 960px) { .a { padding: 1px; } }
@media (max-height: 500px) and (orientation: landscape) and (max-width: 960px) { .b { padding: 1px; } }
@media (forced-colors: active) { .a { border: 1px solid CanvasText; } }
"""


def test_valid_example():
    assert problems(VALID, SCALE) == []


def test_a_second_block_for_one_width_fails():
    css = "@media (max-width: 560px) { .a { margin: 0; } }\n@media (max-width: 560px) { .b { margin: 0; } }"
    assert problems(css, SCALE) == ["@media (max-width: 560px): a second block for this width"]
    # spaced another way, it is still the same width query
    css = "@media (max-width: 560px) { .a { margin: 0; } }\n@media (max-width:560px) { .b { margin: 0; } }"
    assert problems(css, SCALE) == ["@media (max-width:560px): a second block for this width"]


def test_a_width_off_the_scale_fails():
    assert problems("@media (max-width: 635px) { .a { margin: 0; } }", SCALE) == [
        "@media (max-width: 635px): 635 px is not on the scale"
    ]
    assert problems(
        "@media (min-width: 560px) and (max-width: 960px) { .a { margin: 0; } }", SCALE
    ) == ["@media (min-width: 560px) and (max-width: 960px): 560 px is not a scale width plus 1 px"]
    # a width inside a landscape or hover query is on the scale too
    q = "(max-height: 500px) and (orientation: landscape) and (max-width: 950px)"
    assert problems(f"@media {q} {{ .a {{ padding: 0; }} }}", SCALE) == [
        f"@media {q}: 950 px is not on the scale"
    ]
    assert problems(
        "@media (hover: hover) and (min-width: 950px) { .a { color: red; } }", SCALE
    ) == ["@media (hover: hover) and (min-width: 950px): 950 px is not a scale width plus 1 px"]


def test_two_bounds_of_one_kind_or_an_empty_range_fails():
    assert problems(
        "@media (max-width: 960px) and (max-width: 560px) { .a { margin: 0; } }", SCALE
    ) == ["@media (max-width: 960px) and (max-width: 560px): more than one min-width or max-width"]
    assert problems(
        "@media (min-width: 961px) and (max-width: 560px) { .a { margin: 0; } }", SCALE
    ) == ["@media (min-width: 961px) and (max-width: 560px): an empty range"]


def test_a_wider_block_after_a_narrower_one_fails():
    css = "@media (max-width: 560px) { .a { margin: 0; } }\n@media (max-width: 960px) { .a { margin: 1px; } }"
    assert problems(css, SCALE) == [
        "@media (max-width: 960px): comes after (max-width: 560px), a block for narrower screens"
    ]
    # a min-width block sits above the block of its lower width, not above a wider one
    css = "@media (min-width: 561px) and (max-width: 960px) { .a { margin: 0; } }\n@media (max-width: 960px) { .b { margin: 0; } }"
    assert len(problems(css, SCALE)) == 1


def test_a_selector_set_twice_in_a_block_fails():
    css = "@media (max-width: 960px) { .a { margin: 0; } .b { margin: 0; } .a  { padding: 0; } }"
    assert problems(css, SCALE) == ["@media (max-width: 960px): .a set twice"]
    # in two selector lists, in any order, but not a comma inside :is()
    css = "@media (max-width: 960px) { .a, .b { margin: 0; } :is(.a, .b) .c { margin: 0; } .b, .a { padding: 0; } }"
    assert problems(css, SCALE) == [
        "@media (max-width: 960px): .a set twice",
        "@media (max-width: 960px): .b set twice",
    ]


def test_another_width_form_fails():
    assert problems("@media (width <= 560px) { .a { margin: 0; } }", SCALE) == [
        "@media (width <= 560px): not a min-width or max-width query"
    ]
