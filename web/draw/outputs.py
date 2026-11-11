"""The files written beside the pages: search.json, vercel.json (with the inline script's hash),
the preview-card sources and icon in og/, the @font-face block between the markers in words.css
(stopping the build when the markers are missing) and the contrast table in README.md.
"""

import base64
import hashlib
import re

from . import state as S
from .chrome import CARD_H, CARD_W, CHECKS_PAGE, HEAD_SCRIPT, font_faces, rung_of
from .hexagon import glyph_svg, mark_svg
from .inks import GROUND, MUTED, PAPER, VIOLET, ratio
from .overview import href, name_of, standing, states
from .words import CHECK_HELD, CHECK_NAME, PETAL_NAME, PETAL_RULE, architecture, e

# ------------------------------------------------------------------ search
# search.json, the local index the header's search reads (words.js; nothing leaves the browser):
# the systems with a row, the models, the six checks, the pages and the systems not run. Each
# entry: its name, where it leads, its kind, the group words.js lists it under and the group's
# tier (systems first, not run last: the order says what kind of entry it is, never how a system
# did), a line of context, its glyph and the words it is found by.
TIER = {"system": 0, "model": 1, "petal": 2, "check": 3, "page": 4, "notrun": 5}
GROUP = {"system": "Systems", "model": "Models", "petal": "Glyph", "check": "Checks",
         "page": "Pages", "notrun": "Not run"}  # fmt: skip


def search_entries():
    out = []

    def add(kind, name, url, meta, pie, terms=""):
        words = " ".join([name, meta, terms])
        out.append({"kind": kind, "tier": TIER[kind], "group": GROUP[kind], "name": name,
                    "url": url, "meta": meta, "pie": pie,
                    "terms": " ".join(words.lower().split()), "found": []})  # fmt: skip

    for row in S.ROWS:
        add(
            "system",
            name_of(row),
            href(row),
            f"{rung_of(row)['model']} · {standing(row)}",
            glyph_svg(28, states(row)),
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
        add("check", CHECK_NAME[c], f"{CHECKS_PAGE}#{c}", CHECK_HELD[c], "")
    add(
        "page",
        "Checks",
        CHECKS_PAGE,
        "The six checks, the order rule, what is not tested",
        mark_svg(28, cls="pie-svg lm"),
        "checks order rule undecided not tested",
    )
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
        "ignoreCommand": "git diff --quiet HEAD^ HEAD -- .",
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
.mono{{font-family:"IBM Plex Mono",monospace}}
.disp{{font-family:"Archivo",sans-serif;font-stretch:66%;font-weight:900}}
.sl.green{{fill:{S.INK["green"]}}}.sl.amber{{fill:{S.INK["amber"]}}}.sl.red{{fill:{S.INK["red"]}}}.sl.hollow{{fill:none;stroke:{MUTED}}}
.pie-svg{{display:block;overflow:visible}}
"""


def card_page(card, body, css):
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{e(card)} card</title>'
        f"<style>{font_faces('../fonts/')}\n{card_css()}{css}</style></head><body>{body}</body></html>\n"
    )


def home_card():
    """Only what does not change with the systems run, since link previews stay cached: the
    site's mark and name on the violet field."""
    css = f"""
.l{{position:absolute;inset:0;background:{VIOLET};color:{GROUND};padding:64px 80px;display:flex;align-items:center;gap:72px}}
.mark{{display:block;width:300px;height:300px;fill:{GROUND};flex:none}}
.name{{font-size:150px;line-height:.86;letter-spacing:-.008em}}
.url{{font-size:22px;letter-spacing:.04em;margin-top:32px}}
"""
    body = (f'<div class="l">{mark_svg(300, cls="mark")}<div><p class="disp name">Inference<br>'
            'proofs</p><p class="mono url">inferenceproofs.ai</p></div></div>')  # fmt: skip
    return card_page("home", body, css)


def system_card(pid):
    """The system page's first screen: its name on the violet band, its model, and its glyph
    with each petal's name in its triangle."""
    row = S.PAGE[pid]
    names = [PETAL_NAME[p["id"]] for p in row["glyph"]]
    css = f"""
.band{{position:absolute;left:0;top:0;right:0;height:206px;background:{VIOLET};color:{GROUND};padding:0 56px;overflow:hidden}}
.name{{position:absolute;left:52px;bottom:-9px;font-size:200px;line-height:.8;letter-spacing:-.012em;white-space:nowrap}}
.meta{{position:absolute;right:56px;top:40px;text-align:right;font-size:18px;line-height:1.5}}
.meta b{{display:block;font-weight:600;letter-spacing:.12em;text-transform:uppercase;font-size:17px;margin-bottom:6px}}
.g{{position:absolute;left:50%;top:222px;transform:translateX(-50%)}}
.g svg{{display:block;width:390px;height:390px}}
.t text{{fill:{GROUND};font:800 10.5px/1 "Archivo",sans-serif;font-stretch:64%;letter-spacing:.015em}}
.t.hollow text{{fill:{PAPER}}}
"""
    body = (f'<div class="band"><h1 class="disp name">{e(name_of(row))}</h1>'
            f'<p class="mono meta"><b>Inference proofs</b>{e(rung_of(row)["model"])}<br>'
            f"{e(standing(row))}</p></div>"
            f'<div class="g">{glyph_svg(200, states(row), names=names)}</div>')  # fmt: skip
    return card_page(pid, body, css)


ICON = 180  # the touch icon's side, CSS px at scale 1
FAVICON = 32  # the PNG icon for clients that read no SVG icon


def icon_svg():
    """The site's icon: the hex asterisk in ground ink on the violet field."""
    parts = "".join(re.findall(r'<path d="[^"]+"/>', mark_svg(64)))
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-10 -10 84 84">'
        f'<rect x="-10" y="-10" width="84" height="84" fill="{VIOLET}"/><g fill="{GROUND}">{parts}</g></svg>\n'
    )


def icon_card(size=ICON, name="icon"):
    body = f'<img src="icon.svg" width="{size}" height="{size}" alt="" style="display:block">'
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
    block = "/* fonts: written by build.py */\n" + font_faces("/fonts/") + "\n/* /fonts */"
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
