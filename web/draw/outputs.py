"""The files written beside the pages: search.json, vercel.json (with the inline script's hash),
the preview-card sources and icon in og/, the @font-face block between the markers in words.css
(stopping the build when the markers are missing) and the contrast table in README.md.
"""

import base64
import hashlib
import re
from urllib.parse import urlsplit

from . import state as S
from .chrome import (
    CARD_H,
    CARD_W,
    CHECKS_PAGE,
    HEAD_SCRIPT,
    LEARN_PAGE,
    MANDATE_PAGE,
    SCALE_PAGE,
    SITE_URL,
    counted,
    credit_words,
    font_faces,
    lead_figure,
    level_words,
    parts_of,
    row_cost,
    rung_of,
    standing,
)
from .hexagon import glyph_svg
from .inks import COBALT, GROUND, LINE, MUTED, PAPER, ratio
from .learn import glossary, glossary_entries
from .mark import lockup_svg, mark_svg, stacked_svg, tile_svg
from .overview import (
    fig_html,
    filled,
    href,
    lead_fig,
    name_of,
    states,
    sub_line,
)
from .scale import DIMS
from .words import (
    CHECK_HELD,
    CHECK_NAME,
    FIGURE_NAME,
    FIGURE_RULE,
    MANDATE_BELIEF,
    OF_WHICH,
    PETAL_NAME,
    PETAL_RULE,
    architecture,
    e,
    sub_words,
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
        "checks figures order rule undecided unranked not tested",
    )
    add(
        "page",
        "Scale",
        SCALE_PAGE,
        ", ".join(n for _, n, _ in DIMS),
        PAGE_MARK,
        "scale chart log decade axis",
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
    system cards) and the address."""
    css = f"""
html,body{{box-shadow:inset 0 0 0 2px {LINE}}}
.og-l{{position:absolute;left:96px;top:96px}}
.url{{position:absolute;left:96px;bottom:96px;font-size:26px;line-height:1;font-weight:600}}
"""
    body = (
        f'<div class="og-l">{stacked_svg(132, PAPER, COBALT)}</div>'
        f'<p class="mono url">{e(card_host())}</p>'
    )
    return card_page("home", body, css)


def card_host():
    """The site's host as a card prints it, from SITE_URL ("www." left out)."""
    host = urlsplit(SITE_URL).netloc
    return host.removeprefix("www.")


# Big Shoulders Display 900, each advance in em (measured in Chrome), for sizing a name before
# it is drawn; og.mjs stops on a name that still runs past its box
ADV = {
    "0": 0.507, "1": 0.274, "2": 0.49, "3": 0.504, "4": 0.511, "5": 0.515, "6": 0.499, "7": 0.485,
    "8": 0.501, "9": 0.499, "A": 0.478, "B": 0.472, "C": 0.49, "D": 0.495, "E": 0.408, "F": 0.406,
    "G": 0.493, "H": 0.485, "I": 0.23, "J": 0.453, "K": 0.497, "L": 0.402, "M": 0.745, "N": 0.543,
    "O": 0.497, "P": 0.471, "Q": 0.497, "R": 0.477, "S": 0.474, "T": 0.419, "U": 0.487, "V": 0.494,
    "W": 0.8, "X": 0.471, "Y": 0.465, "Z": 0.418, "a": 0.476, "b": 0.497, "c": 0.459, "d": 0.497,
    "e": 0.459, "f": 0.335, "g": 0.502, "h": 0.503, "i": 0.232, "j": 0.233, "k": 0.457, "l": 0.232,
    "m": 0.769, "n": 0.503, "o": 0.48, "p": 0.497, "q": 0.497, "r": 0.351, "s": 0.438, "t": 0.35,
    "u": 0.499, "v": 0.445, "w": 0.769, "x": 0.419, "y": 0.447, "z": 0.401, " ": 0.22, "-": 0.446,
    ".": 0.25,
}  # fmt: skip


def name_em(text):
    return sum(ADV.get(c, 0.8) for c in text)


CARD_NAME_W = 660  # the name's box on a system card, px (left of the band's figure)
CARD_NAME_ONE = (150, 104)  # one line: the largest size, and the smallest before it takes two
CARD_NAME_TWO = 74  # two lines: the largest size
WHY_LONG = 58  # the standing's reason longer than this, in characters, is set small (two lines)


def card_name(name):
    """The name's lines and size: one line as large as fits, or, for a long name, two lines split
    at the space nearest its middle, never more than CARD_NAME_TWO px."""
    one = min(CARD_NAME_ONE[0], CARD_NAME_W / name_em(name))
    spaces = [i for i, c in enumerate(name) if c == " "]
    if one >= CARD_NAME_ONE[1] or not spaces:
        return [name], int(one)
    cut = min(spaces, key=lambda i: abs(name_em(name[:i]) - name_em(name[i + 1 :])))
    lines = [name[:cut], name[cut + 1 :]]
    two = min(CARD_NAME_TWO, CARD_NAME_W / max(name_em(t) for t in lines))
    return (lines, int(two)) if two > one else ([name], int(one))


def system_card(pid):
    """A system page's card, the page in brief: the top bar's lockup; a cobalt band with the
    system's name, its model with its size and, on the right, its one figure labelled for what it
    is; under it the standing, as large as a name, the cost and check time per reply, and the
    glyph with its names; at the foot the level, the release and the page's address. Every
    figure with its unit, scope and n (AGENTS.md rule 2); a figure with no position is set in the
    light weight, as on the band."""
    row = S.PAGE[pid]
    rung = rung_of(row)
    lines, size = card_name(name_of(row))
    label, lead = lead_fig(row)
    n = counted(row)
    _, f, key = lead_figure(row)
    if parts := parts_of(row, key):  # CO-7: the two parts beside the figure, its scope under all
        pts = "".join(f'<span class="pt"><span class="pw">{e(OF_WHICH)} {e(w)}</span>'
                      f'{fig_html(p, sub="")}</span>' for w, p in parts)  # fmt: skip
        lead = (fig_html(f, sub="") + f'<span class="pts">{pts}</span>'
                f'<span class="sub">{sub_line(sub_words(f, n))}</span>')  # fmt: skip
    head, _, why = standing(row).partition(": ")
    if row["position"] is not None:
        why = f"position {row['position']} of {rung['systems_run']}"
    rel = S.V["release"]
    when = level_words() + (
        f" · Release {rel['id']}" + (f", {rel['date']}" if rel["date"] else "") if rel else ""
    )
    weight = 600 if row["position"] is not None else 400
    css = f"""
.top{{position:absolute;left:0;top:0;width:{CARD_W}px;height:72px;padding:0 64px;display:flex;align-items:center;box-shadow:inset 0 -1px 0 {LINE}}}
.band{{position:absolute;left:0;top:72px;width:{CARD_W}px;height:244px;padding:0 64px 28px;background:{COBALT};color:{GROUND};display:flex;align-items:flex-end;justify-content:space-between;gap:40px}}
.who{{width:{CARD_NAME_W}px}}
.name{{font-size:{size}px;line-height:.86;letter-spacing:-.012em;white-space:nowrap}}
.model{{margin-top:16px;font-size:17px;line-height:23px;font-weight:600}}
.model span{{display:block;font-weight:400}}
.lead{{width:340px;text-align:right}}
.lbl{{display:block;font-size:12px;line-height:16px;font-weight:600;letter-spacing:.08em;text-transform:uppercase}}
.lead .lbl{{margin-bottom:12px;text-wrap:balance}}
.fig{{display:flex;align-items:baseline;white-space:nowrap}}
.lead .fig{{justify-content:flex-end}}
.n{{letter-spacing:-.04em}}
.lead .n{{font-size:{68 if parts else 84}px;line-height:.84;font-weight:{weight}}}
.lead .u{{font-size:{36 if parts else 44}px;font-weight:{weight}}}
.pts{{display:block;margin-top:10px}}
.pt{{display:flex;justify-content:flex-end;align-items:baseline;gap:8px;font-size:13px;line-height:18px}}
.lead .pt .n{{font-size:15px;line-height:18px;font-weight:600;letter-spacing:0}}
.lead .pt .u{{font-size:13px;font-weight:400}}
.sub{{display:block;margin-top:10px;font-size:14px;line-height:18px}}
.na{{font-size:28px;line-height:1}}
.low{{position:absolute;left:64px;top:344px;width:690px}}
.st{{padding-bottom:18px;border-bottom:1px solid {LINE}}}
.st .lbl,.cell .lbl{{color:{MUTED}}}
.sw{{margin-top:8px;font-size:48px;line-height:.9;text-transform:uppercase;letter-spacing:.01em}}
.why{{margin-top:8px;font-size:18px;line-height:24px}}
.why.sm{{margin-top:6px;font-size:14px;line-height:18px}}
.cells{{display:flex}}
.cell{{flex:1 1 0;min-width:0;padding:16px 20px 0 0}}
.cell+.cell{{padding-left:20px;border-left:1px solid {LINE}}}
.cell .lbl{{margin-bottom:10px}}
.cell .n{{font-size:34px;line-height:1;font-weight:600}}
.cell .u{{margin-left:6px;font-size:16px}}
.cell .sub{{color:{MUTED}}}
.g{{position:absolute;right:64px;top:348px}}
.foot{{position:absolute;left:64px;right:64px;bottom:24px;display:flex;justify-content:space-between;align-items:baseline;font-size:15px;line-height:20px}}
.foot .lvl{{color:{MUTED}}}
.foot .url{{font-size:18px;font-weight:600}}
.pie-svg{{overflow:visible}}
"""
    glyph = glyph_svg(6, states(row), names=[PETAL_NAME[p["id"]] for p in row["glyph"]])
    model = (f'{e(rung["model"])}<span>'
             f'{e(architecture(rung["parameters_total"], rung.get("parameters_active")))}</span>')  # fmt: skip
    cells = ((FIGURE_NAME["cost"], fig_html(row_cost(row), n)),
             (FIGURE_NAME["check-time"], fig_html(row["figures"]["verify_seconds_per_reply"], n)))  # fmt: skip
    small = " sm" if len(why) > WHY_LONG else ""
    reason = f'<p class="mono why{small}">{e(why)}</p>' if why else ""
    figs = "".join(f'<div class="cell fit"><span class="lbl">{e(k)}</span>{v}</div>'
                   for k, v in cells)  # fmt: skip
    body = (
        f'<div class="top">{lockup_svg(22, ink=PAPER, mark=COBALT)}</div>'
        f'<div class="band"><div class="who fit"><p class="disp name fit">'
        f'{"<br>".join(e(t) for t in lines)}</p><p class="mono model fit">{model}</p></div>'
        f'<div class="mono lead fit"><span class="lbl">{e(label)}</span>{lead}</div></div>'
        f'<div class="low"><div class="st fit"><span class="mono lbl">Standing</span>'
        f'<p class="disp sw">{e(head)}</p>{reason}</div><div class="mono cells">{figs}</div></div>'
        f'<div class="g">{glyph}</div><div class="mono foot"><span class="lvl">{e(when)}</span>'
        f'<span class="url">{e(card_host())}/{e(pid)}</span></div>'
    )
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
    if S.V["credit"]["members"]:
        S.WRITE_TEXT(S.OG / f"{MEMBERS_CARD}.html", members_card())


# ------------------------------------------------------------------ the members' banner
# og/members.html, a picture for posts (no page names it): the lockup, who builds the site, and
# the members' names as a ruled grid of 1 to 12 cells. Written only once a member is listed.
MEMBERS_CARD = "members"
MEMBER_COLS = {1: 1, 2: 2, 3: 3, 4: 2}  # columns by count; 5 to 9 names take 3, 10 to 12 take 4


def members_card():
    names = [m["name"] for m in S.V["credit"]["members"]]
    n = len(names)
    cols = MEMBER_COLS.get(n, 3 if n <= 9 else 4)
    rows = -(-n // cols)
    # the grid: 1008 px wide between the 96 px margins, 300 px tall over the bottom margin. Every
    # name on one line when that keeps three quarters of the size two lines allow, else on two,
    # sized so its longer half fits its cell (Big Shoulders 900 runs under 0.5 em a letter)
    cw, ch = (1008 - (cols - 1)) / cols - 48, (300 - (rows - 1)) / rows
    half = max(max(len(x) - len(x) // 2, *map(len, x.split())) for x in names)
    one, two = (min(96, ch * 0.38, cw / (0.5 * k)) for k in (max(map(len, names)), half))
    size = int(one if one >= 0.75 * two else two)
    css = f"""
html,body{{box-shadow:inset 0 0 0 2px {LINE}}}
.cl{{position:absolute;left:96px;top:84px}}
.by{{position:absolute;left:96px;top:150px;width:1008px;font-size:20px;line-height:1.35;color:{MUTED}}}
.mg{{position:absolute;left:96px;bottom:84px;width:1008px;height:300px;display:grid;grid-template-columns:repeat({cols},1fr);grid-template-rows:repeat({rows},1fr);gap:1px;background:{LINE};border-block:1px solid {LINE}}}
.mg>div{{display:flex;align-items:center;padding:0 24px;background:{GROUND};font-size:{size}px;line-height:.92;text-wrap:balance}}
"""
    cells = "".join(f'<div class="disp">{e(x)}</div>' for x in names)
    cells += "<div></div>" * (rows * cols - n)
    body = (f'<div class="cl">{lockup_svg(26, ink=PAPER, mark=COBALT)}</div>'
            f'<p class="mono by">{credit_words(linked=False)}</p>'
            f'<div class="mg">{cells}</div>')  # fmt: skip
    return card_page(MEMBERS_CARD, body, css)


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
