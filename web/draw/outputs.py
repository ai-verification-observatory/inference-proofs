"""The files written beside the pages: search.json, vercel.json (with the inline script's hash),
the preview-card sources and icon in og/, the @font-face block between the markers in words.css
(stopping the build when the markers are missing) and the contrast table in README.md.
"""

import base64
import hashlib
import re

from . import state as S
from .chrome import (
    CARD_H,
    CARD_W,
    CHECKS_PAGE,
    HEAD_SCRIPT,
    LEARN_PAGE,
    MANDATE_PAGE,
    font_faces,
    level_words,
    rung_of,
)
from .hexagon import glyph_svg
from .inks import COBALT, GROUND, LINE, MUTED, PAPER, ratio
from .learn import glossary, glossary_entries
from .mark import lockup_svg, mark_svg, stacked_svg, tile_svg
from .overview import filled, href, name_of, standing, states
from .words import (
    CHECK_HELD,
    CHECK_NAME,
    FIGURE_NAME,
    FIGURE_RULE,
    MANDATE_BELIEF,
    PETAL_NAME,
    PETAL_RULE,
    architecture,
    e,
)

# ------------------------------------------------------------------ search
# search.json, the local index the header's search reads (words.js; nothing leaves the browser):
# the systems with a row, the models, the six checks, the pages, the Learn pages with the
# glossary's terms, and the systems not run. Each
# entry: its name, where it leads, its kind, the group words.js lists it under and the group's
# tier (systems first, not run last: the order says what kind of entry it is, never how a system
# did), a line of context, its glyph and the words it is found by.
# a page's entry carries the mark, drawn on whole pixels (26 x 18 px) in its 28 px slot
PAGE_MARK = mark_svg(2, cls="pie-svg lm", small=True)
# the script sorts the page in view first inside a tier, which would split a group in two: the
# Learn pages and the glossary's terms each get a tier of their own
TIER = {"system": 0, "model": 1, "petal": 2, "check": 3, "figure": 4, "page": 4, "learn": 4.1,
        "term": 4.2, "notrun": 5}  # fmt: skip
GROUP = {"system": "Systems", "model": "Models", "petal": "Glyph", "check": "Checks",
         "figure": "Figures", "page": "Pages", "learn": "Learn", "term": "Glossary",
         "notrun": "Not run"}  # fmt: skip


def search_entries():
    out = []

    def add(kind, name, url, meta, pie, terms=""):
        words = " ".join([name, meta, terms])
        out.append({"kind": kind, "tier": TIER[kind], "group": GROUP[kind], "name": name,
                    "url": url, "meta": meta, "pie": pie,
                    "terms": " ".join(words.lower().split())})  # fmt: skip

    for row in S.ROWS:
        add(
            "system",
            name_of(row),
            href(row),
            f"{rung_of(row)['model']} · {standing(row)}",
            glyph_svg(1, states(row)),
            f"{row['workload']} {row['system']}",
        )
    for rung in S.V["rungs"]:
        add(
            "model",
            rung["model"],
            f"/#{rung['id']}",
            f"{rung['publisher']} · "
            f"{architecture(rung['parameters_total'], rung.get('parameters_active'))}",
            "",
            rung["id"],
        )
    for pid in S.V["petals"]:
        add("petal", PETAL_NAME[pid], f"{CHECKS_PAGE}#{pid}", PETAL_RULE[pid][0], "")
    for c in S.V["checks"]:
        add("check", CHECK_NAME[c], f"{CHECKS_PAGE}#{c}", filled(CHECK_HELD[c]), "")
    for f, lines in FIGURE_RULE.items():
        add("figure", FIGURE_NAME[f], f"{CHECKS_PAGE}#{f}", filled(lines[0][1]), "")
    add(
        "page",
        "Checks",
        CHECKS_PAGE,
        "The six checks, the figures, the order rule, what is not tested",
        PAGE_MARK,
        "checks terms proof commitment request ladder figures order rule undecided unranked "
        "not tested",
    )
    add(
        "page",
        "Mandate",
        MANDATE_PAGE,
        MANDATE_BELIEF,
        PAGE_MARK,
        "mandate about who operator conflicts",
    )
    if lv := S.V.get("learn"):
        add("learn", lv["title"], LEARN_PAGE, lv["lead"], PAGE_MARK, "learn explain guide intro")
        for t in lv["tracks"]:
            for p in t["pages"]:
                add("learn", p["title"], f"/{p['slug']}", p["summary"], "", t["name"])
        g = glossary()
        add("learn", g["title"], f"/{g['slug']}", g["summary"], "", "terms words definitions")
        for name, tid, first in glossary_entries():
            add("term", name, f"/{g['slug']}#{tid}", first, "")
    for r in S.V["not_run"]:
        add("notrun", r["name"], f"/#nr-{r['id']}", r["reason"], "")
    return out


# ------------------------------------------------------------------ vercel.json, from the build
# Headers, redirects and cache rules depend on the build's own output (the inline script's hash,
# the pages written), so the build writes the whole file. Canonical JSON (iproofs fmt).
def vercel_json():
    script = hashlib.sha256(HEAD_SCRIPT.encode()).digest()
    csp = "; ".join(
        [
            "default-src 'self'",
            f"script-src 'self' 'sha256-{base64.b64encode(script).decode()}' https://cdn.vercel-insights.com",
            "style-src 'self'",
            "img-src 'self'",
            "font-src 'self'",
            "connect-src 'self' https://*.vercel-insights.com",
            "object-src 'none'",
            "base-uri 'none'",
            "form-action 'none'",
            "frame-ancestors 'none'",
        ]
    )
    forever = [{"key": "Cache-Control", "value": "public, max-age=31536000, immutable"}]
    first = href(S.ROWS[0]) if S.ROWS else "/"
    # pages of the earlier site, and the systems of the level with no page in this build
    gone = {"/criteria": CHECKS_PAGE, "/reference": "/", "/release": "/", "/targets": "/"}
    for sid in S.V["planned"]:
        if sid not in S.PAGE:
            gone[f"/{sid}"] = "/"
    return {
        "$schema": "https://openapi.vercel.sh/vercel.json",
        "buildCommand": "rm -rf public && mkdir -p public/og public/fonts && cp *.html words.css words.js search.json public/ && cp og/*.png og/*.svg public/og/ && cp fonts/*.woff2 public/fonts/",
        "cleanUrls": True,
        "trailingSlash": False,
        "framework": None,
        # every commit of the push, not only its last one
        "ignoreCommand": "git diff --quiet ${VERCEL_GIT_PREVIOUS_SHA:-HEAD^} HEAD -- .",
        "outputDirectory": "public",
        "redirects": [
            {"source": "/system", "destination": first, "permanent": False},
            {"source": "/system.html", "destination": first, "permanent": False},
            *(
                {"source": src, "destination": dst, "permanent": False}
                for src, dst in sorted(gone.items())
            ),
            # clients that ask for /favicon.ico get the PNG icon
            {"source": "/favicon.ico", "destination": "/og/icon-32.png", "permanent": False},
        ],
        "headers": [
            {
                "source": "/(.*)",
                "headers": [
                    # noindex: the site is not announced (README)
                    {"key": "X-Robots-Tag", "value": "noindex"},
                    {"key": "X-Content-Type-Options", "value": "nosniff"},
                    {"key": "Referrer-Policy", "value": "strict-origin-when-cross-origin"},
                    {"key": "Content-Security-Policy", "value": csp},
                    {"key": "X-Frame-Options", "value": "DENY"},
                    {
                        "key": "Permissions-Policy",
                        "value": "camera=(), microphone=(), geolocation=()",
                    },
                ],
            },
            # versioned by ?v=<hash> (words.css, words.js, the pictures) or by the file name (fonts)
            {"source": "/(words\\.css|words\\.js|search\\.json)", "headers": forever},
            {"source": "/og/(.*)\\.png", "headers": forever},
            {"source": "/fonts/(.*)", "headers": forever},
        ],
    }


# ------------------------------------------------------------------ preview card sources
# og/<card>.html for og.mjs to render, and the icon (the share tags that name them: chrome.py).


def card_css():
    return f"""
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{CARD_W}px;height:{CARD_H}px;overflow:hidden;background:{GROUND};color:{PAPER};-webkit-font-smoothing:antialiased}}
svg{{display:block}}
.mono{{font-family:"Martian Mono",monospace;font-stretch:87.5%}}
.disp{{font-family:"Big Shoulders Display",sans-serif;font-weight:900}}
"""


def card_page(card, body, css):
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{e(card)} card</title>'
        f"<style>{font_faces('../fonts/')}\n{card_css()}{css}</style></head><body>{body}</body></html>\n"
    )


def home_card():
    """Only what does not change with the systems run, since link previews stay cached: the
    stacked lockup in paper with the mark in cobalt on the ground (as the site's top bar and the
    system cards), the address and the level."""
    css = f"""
html,body{{box-shadow:inset 0 0 0 2px {LINE}}}
.og-l{{position:absolute;left:96px;top:96px}}
.url{{position:absolute;left:96px;bottom:120px;font-size:26px;line-height:1;font-weight:600}}
.lvl{{position:absolute;left:96px;bottom:84px;font-size:22px;line-height:1;font-weight:400;color:{MUTED}}}
"""
    body = (f'<div class="og-l">{stacked_svg(132, PAPER, COBALT)}</div>'
            f'<p class="mono url">inferenceproofs.ai</p><p class="mono lvl">{e(level_words())}</p>')  # fmt: skip
    return card_page("home", body, css)


def system_card(pid):
    """A system page's card: the lockup, the system's name, its model and standing, the level,
    and its glyph (the five petals in their state inks) on the right."""
    row = S.PAGE[pid]
    name = name_of(row)
    # the name on one line, at most 220 px, smaller for a long name (Big Shoulders 900 runs under
    # 0.45 em a letter), in the 672 px left of the glyph
    size = min(220, int(672 / (0.45 * max(len(name), 1))))
    css = f"""
html,body{{box-shadow:inset 0 0 0 2px {LINE}}}
.cl{{position:absolute;left:96px;top:84px}}
.sn{{position:absolute;left:90px;top:196px;font-size:{size}px;line-height:.8;letter-spacing:-.005em;white-space:nowrap}}
.sr{{position:absolute;left:96px;top:410px;width:672px;font-size:24px;line-height:1.35;font-weight:400;color:{MUTED}}}
.lvl{{position:absolute;left:96px;bottom:84px;font-size:22px;line-height:1;color:{MUTED}}}
.g{{position:absolute;right:96px;top:165px}}
.g svg{{display:block}}
.sl.green{{fill:{S.INK["green"]}}}.sl.amber{{fill:{S.INK["amber"]}}}.sl.red{{fill:{S.INK["red"]}}}.sl.hollow{{fill:none;stroke:{MUTED}}}
.sl.red.open{{fill:none;stroke:{S.INK["red"]}}}
.pie-svg{{overflow:visible}}
"""
    body = (f'<div class="cl">{lockup_svg(26, ink=PAPER, mark=COBALT)}</div>'
            f'<p class="disp sn">{e(name)}</p>'
            f'<p class="mono sr">{e(rung_of(row)["model"])}<br>{e(standing(row))}</p>'
            f'<p class="mono lvl">{e(level_words())}</p>'
            f'<div class="g">{glyph_svg(6, states(row), names=[PETAL_NAME[p["id"]] for p in row["glyph"]])}</div>')  # fmt: skip
    return card_page(pid, body, css)


ICON = 180  # the touch icon's side, CSS px at scale 1
FAVICON = 32  # the PNG icon for clients that read no SVG icon


def icon_svg():
    """The site's icon: the mark in ground ink on cobalt, drawn on the 16 px grid (whole pixels at
    16 and at 32)."""
    return tile_svg(16, COBALT, GROUND, xmlns=True) + "\n"


def icon_card(size=ICON, name="icon"):
    """The touch icon (180 px) and the PNG icon (32 px), each drawn for its own size."""
    body = tile_svg(size, COBALT, GROUND)
    page_ = card_page(name, body, "")
    return page_.replace(
        '<html lang="en">', f'<html lang="en" data-w="{size}" data-h="{size}" data-scale="1">', 1
    ).replace(
        f"html,body{{width:{CARD_W}px;height:{CARD_H}px;",
        f"html,body{{width:{size}px;height:{size}px;",
    )


def write_cards():
    S.OG.mkdir(exist_ok=True)
    S.WRITE_TEXT(S.OG / "icon.svg", icon_svg())
    S.WRITE_TEXT(S.OG / "icon.html", icon_card())
    S.WRITE_TEXT(S.OG / "icon-32.html", icon_card(FAVICON, "icon-32"))
    S.WRITE_TEXT(S.OG / "home.html", home_card())
    for pid in S.PAGE:
        S.WRITE_TEXT(S.OG / f"{pid}.html", system_card(pid))


def write_font_faces():
    """The @font-face block in words.css, between its markers, from fonts/faces.json."""
    css = (S.HERE / "words.css").read_text()
    block = (
        "/* fonts: written by build.py */\n" + font_faces("/fonts/", site=True) + "\n/* /fonts */"
    )
    new = re.sub(
        r"/\* fonts: written by build.py \*/.*?/\* /fonts \*/", lambda _: block, css, flags=re.S
    )
    assert new != css or block in css, "words.css lacks the fonts markers"
    S.WRITE_TEXT(S.HERE / "words.css", new)


def write_readme():
    readme = S.HERE / "README.md"
    if not readme.exists():
        return
    table = (
        "| State | Ink | Luminance | Contrast on the ground `"
        + GROUND
        + "` | Step from the state below |\n|---|---|---|---|---|\n"
        + "\n".join(f"| {a} | {b} | {c} | {d} | {f} |" for a, b, c, d, f in S.ladder)
        + "\n\n| Pair | Contrast |\n|---|---|\n"
        + "\n".join(f"| {n} (`{a}` on `{b}`) | {ratio(a, b):.2f}:1 |" for n, a, b in S.pairs)
    )
    txt = re.sub(
        r"<!-- ladder -->.*<!-- /ladder -->",
        "<!-- ladder -->\n" + table + "\n<!-- /ladder -->",
        readme.read_text(),
        flags=re.S,
    )
    S.WRITE_TEXT(readme, txt)
