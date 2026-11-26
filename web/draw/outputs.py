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
    ONLY_RUN,
    OVERVIEW_PAGE,
    SITE_URL,
    counted,
    credit_words,
    font_faces,
    further,
    mark_shape,
    only_run,
    rung_of,
    standing,
)
from .hexagon import glyph_svg
from .inks import ACCENT, ACCENT_LIGHT, GROUND, LIFT, LINE, MUTED, ON_ACCENT, PAPER, ratio
from .ladder import (
    BARE,
    fig_html,
    filled,
    href,
    lead_fig,
    name_of,
    proving_html,
    states,
)
from .learn import glossary, glossary_entries, sections
from .mark import lockup_svg, mark_svg, stacked_svg, tile_svg
from .overview import overview_words
from .words import (
    CHECK_LINE,
    CHECK_NAME,
    CHECKS_DESC,
    FIGURE_HEAD,
    FIGURE_LINE,
    FIGURE_NAME,
    MANDATE_DESC,
    PETAL_NAME,
    PETAL_QUESTION,
    PETAL_TERM,
    architecture,
    e,
    release_tail,
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
# the words a Learn page is found by besides its title, summary, track and sections' heads: the
# words a reader types for what a page holds without naming it so
LEARN_TERMS = {"deployment": "treaty between states enclave sampling"}


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
    # a petal, a check, a figure in one line each (the checks page's: the petal's question, the
    # check's passing rule, what the figure is), a pointer to its rule; a petal found by its field
    # term too
    for pid in S.V["petals"]:
        add("petal", PETAL_NAME[pid], f"{CHECKS_PAGE}#{pid}", PETAL_QUESTION[pid], "",
            PETAL_TERM[pid])  # fmt: skip
    for c in S.V["checks"]:
        add("check", CHECK_NAME[c], f"{CHECKS_PAGE}#{c}", filled(CHECK_LINE[c]), "")
    for f, line in FIGURE_LINE.items():
        add("figure", FIGURE_NAME[f], f"{CHECKS_PAGE}#{f}", filled(line), "")
    add(
        "page",
        "Checks",
        CHECKS_PAGE,
        CHECKS_DESC,
        PAGE_MARK,
        "checks figures order rule not decided not ranked not tested",
    )
    add(
        "page",
        "Overview",
        OVERVIEW_PAGE,
        overview_words(),
        PAGE_MARK,
        "overview scale chart graph log decade axis",
    )
    add(
        "page",
        "Mandate",
        MANDATE_PAGE,
        MANDATE_DESC,
        PAGE_MARK,
        "mandate about who runs",
    )
    if lv := S.V.get("learn"):
        add("learn", lv["title"], LEARN_PAGE, lv["lead"], PAGE_MARK, "learn explain guide intro")
        for t in lv["tracks"]:
            for p in t["pages"]:
                found = [t["name"], *sections(p), LEARN_TERMS.get(p["slug"], "")]
                add("learn", p["title"], f"/{p['slug']}", p["summary"], "", " ".join(found))
        g = glossary()
        add("learn", g["title"], f"/{g['slug']}", g["summary"], "", "terms words definitions")
        for name, tid, first in glossary_entries():
            add("term", name, f"/{g['slug']}#{tid}", first, "")
    for r in S.V["not_run"]:
        add("notrun", r["name"], f"/#nr-{r['id']}", r["reason"], "")
    return out


# ------------------------------------------------------------------ vercel.json, from the build
# Addresses the site no longer serves, each with the page that took its place: pages of the
# earlier site, then the Learn pages merged into others. A Learn page may not take one of these
# addresses (build.py, `setup`): its redirect would hide it.
GONE = {
    "/criteria": CHECKS_PAGE,
    "/reference": "/",
    "/release": "/",
    "/targets": "/",
    "/why-verify": "/proof-of-inference",
    "/before-you-rely": "/proof-of-inference",
    "/three-ways": "/deployment",
    "/treaty": "/deployment",
    "/inference": "/forward-pass",
    "/proof-systems": "/forward-pass",
    "/architectures": "/statement",
    "/cost": "/method",
    "/scale": OVERVIEW_PAGE,  # the Overview page's name until 2026-11-20
}


# What Vercel runs in web/ to fill public/ (assets.mjs copies the partners' marks, members/).
# Vercel refuses a build command over 256 characters, failing the deployment with no other sign.
BUILD_COMMAND = (
    "rm -rf public && mkdir -p public/og public/fonts && cp *.html search.json robots.txt "
    "sitemap.xml llms.txt public/ && cp og/*.png og/*.svg public/og/ && cp fonts/*.woff2 "
    "public/fonts/ && npm ci --include=dev --ignore-scripts && npm run assets"
)
if len(BUILD_COMMAND) > 256:
    raise RuntimeError(
        f"vercel.json: a build command of {len(BUILD_COMMAND)} characters (Vercel takes 256)"
    )


# Headers, redirects and cache rules depend on the build's own output (the inline script's hash,
# the pages written), so the build writes the whole file. Canonical JSON (iproofs fmt).
def vercel_json(pages=()):
    pages = list(pages)
    script = hashlib.sha256(HEAD_SCRIPT.encode()).digest()
    hashes = sorted(
        {
            base64.b64encode(hashlib.sha256(block.encode()).digest()).decode()
            for page in pages
            for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page)
        }
    )
    structured = "".join(f" 'sha256-{h}'" for h in hashes)
    style_hashes = sorted(
        {
            base64.b64encode(hashlib.sha256(block.encode()).digest()).decode()
            for page in pages
            for block in re.findall(r"<style>(.*?)</style>", page, re.S)
        }
    )
    styles = "".join(f" 'sha256-{h}'" for h in style_hashes)
    csp = "; ".join(
        [
            "default-src 'self'",
            f"script-src 'self' 'sha256-{base64.b64encode(script).decode()}'{structured} https://cdn.vercel-insights.com",
            f"style-src 'self'{styles}",
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
    # the addresses gone (GONE), and the systems of the level with no page in this build
    gone = dict(GONE)
    for sid in S.V["planned"]:
        if sid not in S.PAGE:
            gone[f"/{sid}"] = "/"
    routes = sorted(p.stem for p in S.HERE.glob("*.html") if p.stem not in {"index", "404"})
    redirects = {
        "/system": (first, False),
        **{src: (dst, src in GONE) for src, dst in gone.items()},
    }
    redirects.update({f"/{route}": (f"/{route}", True) for route in routes})
    aliases = [
        {"source": f"{src}{suffix}", "destination": dst, "permanent": permanent}
        for src, (dst, permanent) in sorted(redirects.items())
        for suffix in ("", ".html", "/")
        if suffix or src != dst
    ]
    return {
        "$schema": "https://openapi.vercel.sh/vercel.json",
        "buildCommand": BUILD_COMMAND,
        "cleanUrls": False,
        "framework": None,
        # every commit of the push, not only its last one; a previous commit outside the
        # deploy clone (a long push) makes git fail, which must build, not fail the deployment
        "ignoreCommand": (
            "git diff --quiet ${VERCEL_GIT_PREVIOUS_SHA:-HEAD^} HEAD -- . && exit 0 || exit 1"
        ),
        "outputDirectory": "public",
        "rewrites": [{"source": f"/{route}", "destination": f"/{route}.html"} for route in routes],
        "redirects": [
            *aliases,
            *(
                {"source": src, "destination": "/", "permanent": True}
                for src in ("/index", "/index.html", "/index/")
            ),
            # clients that ask for /favicon.ico get the PNG icon
            {"source": "/favicon.ico", "destination": "/og/icon-32.png", "permanent": False},
        ],
        "headers": [
            {
                "source": "/(.*)",
                "headers": [
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
    stacked lockup in paper with the mark in accent on the ground (as the site's top bar and the
    system cards) and the address."""
    css = f"""
html,body{{box-shadow:inset 0 0 0 2px {LINE}}}
.og-l{{position:absolute;left:96px;top:96px}}
.url{{position:absolute;left:96px;bottom:96px;font-size:26px;line-height:1;font-weight:600}}
"""
    body = (
        f'<div class="og-l">{stacked_svg(132, PAPER, ACCENT)}</div>'
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
    """A system page's card, the page in brief: the top bar's lockup; a lifted band with the
    system's name, its model with its size and, on the right, its one figure under its plain
    name; under it the standing, as large as a name, the cost and verify time per reply, and the
    glyph with its names; at the foot the release and the page's address. A card is shallower
    than the ladder (web/DEPTH.md): every figure with its unit alone, its scope and n on the page
    the address names; a figure with no position is set in the light weight, as on the band."""
    row = S.PAGE[pid]
    rung = rung_of(row)
    lines, size = card_name(name_of(row))
    label, lead = lead_fig(row, bare=True)
    n = counted(row)
    head, _, why = standing(row).partition(": ")
    if row["position"] is not None:  # OR-4: no count where nothing else ran on the model
        why = ONLY_RUN if only_run(row) else f"position {row['position']} of {rung['systems_run']}"
    rel = S.V["release"]
    when = f"Release {release_tail(rel)}" if rel else ""
    weight = 600 if row["position"] is not None else 400
    css = f"""
.top{{position:absolute;left:0;top:0;width:{CARD_W}px;height:72px;padding:0 64px;display:flex;align-items:center;box-shadow:inset 0 -1px 0 {LINE}}}
.band{{position:absolute;left:0;top:72px;width:{CARD_W}px;height:244px;padding:0 64px 28px;background:{LIFT};color:{PAPER};display:flex;align-items:flex-end;justify-content:space-between;gap:40px}}
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
.lead .n{{font-size:84px;line-height:.84;font-weight:{weight}}}
.lead .u{{font-size:44px;font-weight:{weight}}}
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
    # CO-9 (Q55): the proving multiple first, beside the total in the band
    proving = ((FIGURE_HEAD["proving"], proving_html(row, bare=True, batch=False)),) \
        if further() else ()  # fmt: skip
    cells = (*proving,
             (FIGURE_HEAD["proof-size"], fig_html(row["figures"]["proof_bytes_per_reply"], n, sub=BARE)),
             (FIGURE_HEAD["check-time"],
              fig_html(row["figures"]["verify_seconds_per_reply"], n, sub=BARE)))  # fmt: skip
    small = " sm" if len(why) > WHY_LONG else ""
    reason = f'<p class="mono why{small}">{e(why)}</p>' if why else ""
    figs = "".join(f'<div class="cell fit"><span class="lbl">{e(k)}</span>{v}</div>'
                   for k, v in cells)  # fmt: skip
    body = (
        f'<div class="top">{lockup_svg(22, ink=PAPER, mark=ACCENT_LIGHT)}</div>'
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
    """The site's icon: the mark in ground ink on accent, drawn on the 16 px grid (whole pixels at
    16 and at 32)."""
    return tile_svg(16, ACCENT, ON_ACCENT, xmlns=True) + "\n"


def icon_card(size=ICON, name="icon"):
    """The touch icon (180 px) and the PNG icon (32 px), each drawn for its own size."""
    body = tile_svg(size, ACCENT, ON_ACCENT)
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
# the members as a ruled grid of 1 to 12 cells, each its own mark (its light-on-dark version from
# its kit, a file under web/) or, with none, its name. Written only once a member is listed.
MEMBERS_CARD = "members"
MEMBER_COLS = {1: 1, 2: 2, 3: 3, 4: 2}  # columns by count; 5 to 9 names take 3, 10 to 12 take 4
MARK_TYPE = {".svg": "image/svg+xml", ".png": "image/png"}


def members_card():
    members = S.V["credit"]["members"]
    names = [m["name"] for m in members]
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
    # the marks, each drawn with the same area so a wide wordmark and a square read as one weight:
    # the largest area at which every mark fits 85 % of its cell's width and 60 % of its height
    marks = {m["name"]: S.HERE / m["mark"] for m in members if m.get("mark")}
    shape = {x: mark_shape(p) for x, p in marks.items()}
    area = min((min((cw * 0.85) ** 2 / r, (ch * 0.6) ** 2 * r) for r in shape.values()),
               default=0)  # fmt: skip

    def cell(x):
        if x not in marks:
            return f'<div class="disp">{e(x)}</div>'
        p, r = marks[x], shape[x]
        src = f"data:{MARK_TYPE[p.suffix]};base64,{base64.b64encode(p.read_bytes()).decode()}"
        w, h = (area * r) ** 0.5, (area / r) ** 0.5
        return (f'<div class="mk"><img src="{src}" alt="{e(x)}" '
                f'style="width:{w:.1f}px;height:{h:.1f}px"></div>')  # fmt: skip

    css = f"""
html,body{{box-shadow:inset 0 0 0 2px {LINE}}}
.cl{{position:absolute;left:96px;top:84px}}
.by{{position:absolute;left:96px;top:150px;width:1008px;font-size:20px;line-height:1.35;color:{MUTED}}}
.mg{{position:absolute;left:96px;bottom:84px;width:1008px;height:300px;display:grid;grid-template-columns:repeat({cols},1fr);grid-template-rows:repeat({rows},1fr);gap:1px;background:{LINE};border-block:1px solid {LINE}}}
.mg>div{{display:flex;align-items:center;padding:0 24px;background:{GROUND};font-size:{size}px;line-height:.92;text-wrap:balance}}
.mg>.mk{{justify-content:center}}
"""
    cells = "".join(cell(x) for x in names)
    cells += "<div></div>" * (rows * cols - n)
    body = (f'<div class="cl">{lockup_svg(26, ink=PAPER, mark=ACCENT_LIGHT)}</div>'
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
