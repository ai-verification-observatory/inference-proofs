"""Page chrome: addresses, fonts, the inline script, header, search field, footer, legend and the
page frame with its share tags (Open Graph, X, icons) naming the preview pictures by their hash.

`load_faces` reads fonts/faces.json and stops the build on a font file whose name does not carry
its hash. `version` names words.css, words.js and search.json by the first 12 hex of their sha256.
"""

import hashlib
import json
import re

from . import state as S
from .hexagon import key_mini, mark_svg
from .inks import GROUND
from .plates import first_config, glyph, name_of, readable, upstream
from .words import STATE_CLS, STATE_ORDER, STATE_WORD, e

# ------------------------------------------------------------------ chrome
# Pages are files <name>.html served at clean, root-relative addresses (vercel.json cleanUrls;
# serve.py does the same locally), so every link works at any depth, the 404 page included.
REF_PAGE = "/reference"  # one page for the reference systems
CRIT_PAGE = "/criteria"  # the criteria behind the six states
RELEASE_PAGE = "/release"  # the release record (RFC-0009 §Release record)
TARGETS_PAGE = "/targets"  # relying parties' targets, only when the release evaluates one


def has_targets():
    return bool(S.V["targets"])


def file_of(path):
    return S.HERE / f"{path.strip('/') or 'index'}.html"


# ------------------------------------------------------------------ fonts, served from fonts/
# fonts/faces.json lists each woff2 file (named with its own hash, so it can be cached for good)
# with the family, weights, widths and unicode range Google Fonts gives it. The arrows subset comes
# last, so its glyphs win where ranges overlap.
PRELOAD = ("archivo-latin.", "plex-mono-400-latin.", "plex-mono-500-latin.")


def load_faces():
    S.FACES = json.loads((S.HERE / "fonts" / "faces.json").read_text())["faces"]
    for f in S.FACES:
        h = hashlib.sha256((S.HERE / "fonts" / f["file"]).read_bytes()).hexdigest()[:10]
        assert f["file"].endswith(f".{h}.woff2"), f"fonts/{f['file']} does not carry its hash"
    S.FACES.sort(key=lambda f: f["subset"] == "arrows")


def font_faces(base):
    """The @font-face rules, with file URLs under base ("/fonts/" on the site, "../fonts/" for cards)."""
    out = []
    for f in S.FACES:
        stretch = f"font-stretch:{f['stretch']};" if f.get("stretch") else ""
        out.append(
            f'@font-face{{font-family:"{f["fam"]}";font-style:normal;font-weight:{f["wt"]};{stretch}'
            f'font-display:block;src:url({base}{f["file"]}) format("woff2");unicode-range:{f["range"]}}}'
        )
    return "\n".join(out)


def preloads():
    return "".join(
        f'<link rel="preload" href="/fonts/{f["file"]}" as="font" type="font/woff2" crossorigin>'
        for f in S.FACES
        if f["file"].startswith(PRELOAD)
    )


def version(name):
    """A file's URL with the first 12 hex of its sha256, so it can be cached until it changes
    (words.css, words.js, search.json)."""
    return f"/{name}?v={hashlib.sha256((S.HERE / name).read_bytes()).hexdigest()[:12]}"


# The one inline script: it marks that script runs (html.js) and that motion is welcome (html.anim)
# before the first paint. vercel.json allows exactly this script by its hash.
HEAD_SCRIPT = (
    'document.documentElement.classList.add("js");'
    'try{if(!matchMedia("(prefers-reduced-motion: reduce)").matches)document.documentElement.classList.add("anim")}catch(_){}'
)

# GitHub's mark (Octicons mark-github, 16 px, MIT licence)
GITHUB_MARK = (
    '<svg class="gh" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false"><path fill="currentColor" d="'
    "M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 "
    "0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 "
    "0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 .27-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 "
    "1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33-.66"
    "-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01 1.3.01 1.49 "
    "0 .21-.15.45-.55.38A7.995 7.995 0 0 1 0 8c0-4.42 3.58-8 8-8Z"
    '"/></svg>'
)


def header(here):
    def a(href, label, key):
        return f'<a href="{href}"{" aria-current=page" if here == key else ""}>{label}</a>'

    # The logo leads to the overview; the nav holds the other pages; systems are reached by search
    # (one link each would not scale) or from the overview.
    nav = a(REF_PAGE, "References", "reference") + a(CRIT_PAGE, "Criteria", "criteria")
    current = " aria-current=page" if here == "home" else ""
    return (
        f'<header class="top"><div class="tl"><p class="brand"><a class="logo" href="/"{current}>{LOGO_MARK}<span>Inference proofs</span></a></p>'
        f'<nav aria-label="Site">{nav}</nav></div>'
        f"{search_box(here)}"
        f'<a class="repo" href="{e(S.REPO_URL)}">{GITHUB_MARK}<span>GitHub</span></a>'
        "</header>"
    )


# The site's mark, as on the icon and the preview cards: the hex asterisk, here in violet
LOGO_MARK = mark_svg(22)

SEARCH_MARK = (
    '<svg class="si" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">'
    '<circle cx="6.5" cy="6.5" r="5" fill="none" stroke="currentColor" stroke-width="1.6"/>'
    '<path d="M10.2 10.2 15 15" stroke="currentColor" stroke-width="1.6" stroke-linecap="square"/></svg>'
)


def search_box(here):
    """The search field: a combobox over search.json (words.js fills the list). With script only;
    on phones a button opens it over the top bar. The current system page's name is not needed."""
    return (
        '<div class="search" role="search">'
        f'<button type="button" class="sopen" aria-label="Search" aria-expanded="false">{SEARCH_MARK}</button>'
        f'<label class="sr" for="q">Search systems, properties and pages</label>'
        f'<span class="sfield">{SEARCH_MARK}'
        '<input id="q" type="search" autocomplete="off" autocorrect="off" autocapitalize="none" '
        'enterkeyhint="go" spellcheck="false" placeholder="Search" '
        'role="combobox" aria-expanded="false" aria-controls="q-list" aria-autocomplete="list" '
        'aria-keyshortcuts="/ Control+K Meta+K">'
        '<kbd class="skey" aria-hidden="true">/</kbd>'
        '<button type="button" class="sclose" aria-label="Close search">×</button></span>'
        f'<ul id="q-list" class="slist" role="listbox" aria-label="Results" hidden data-index="{version("search.json")}"></ul>'
        "</div>"
    )


def footer():
    """Every page's footer: the criteria and their file, then the release (its page and its
    `index.json`) and the licence."""
    rel = S.V["release"]
    index = (
        f'<a class="nw" href="{e(S.REPO_URL)}/blob/{S.LINK_REF}/{e(rel["index"])}">index.json</a>'
    )
    name = f"Release {rel['id']}"
    licence = readable(f"licence {rel['licence']}").replace("CC BY 4.0", "CC\u00a0BY\u00a04.0")
    return (
        f'<footer class="foot"><p><a href="{CRIT_PAGE}">Criteria</a>'
        f'\u00a0· <a href="{e(S.REPO_URL)}/blob/main/{e(S.CRIT["path"])}">criteria.json</a> sha256 <code>{S.crit_sha[:12]}</code></p>'
        f'<p><a class="nw" href="{RELEASE_PAGE}">{e(name)}</a>\u00a0· {index}'
        f"\u00a0· {e(licence)}</p></footer>"
    )


def full_title(title):
    return title if title == "Inference proofs" else f"{title} · Inference proofs"


# A link to another site (every site link is root-relative) opens in a new tab, with no opener and
# no referrer: the reader keeps the page they were reading.
EXTERNAL_A = re.compile(r'<a (?![^>]*\btarget=)([^>]*\bhref="https?://[^"]*"[^>]*)>')


def new_tab(html):
    return EXTERNAL_A.sub(r'<a \1 target="_blank" rel="noopener noreferrer">', html)


def page(title, desc, body, cls, path, card):
    """One page. path: its address under the site ("" for the home); card: its preview card's name,
    or None for a page that is never shared (the 404)."""
    meta = share_meta(title, desc, path, card) if card else '<meta name="robots" content="noindex">'
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, interactive-widget=resizes-content">'
        f"<script>{HEAD_SCRIPT}</script>"
        f'<title>{e(full_title(title))}</title><meta name="description" content="{e(desc)}">'
        f'<meta name="color-scheme" content="dark"><meta name="theme-color" content="{GROUND}">'
        f"{meta}{icon_links()}{preloads()}"
        f'<link rel="stylesheet" href="{version("words.css")}"></head><body class="{cls}">{new_tab(body)}'
        f'<p class="sr" aria-live="polite" id="live"></p><script src="{version("words.js")}" defer></script></body></html>'
    )


def states_key():
    return "".join(
        f'<span class="chip"><i class="sw {STATE_CLS[s]}"></i>{e(STATE_WORD[s])}</span>'
        for s in STATE_ORDER
    )


def keyline():
    return f'<p class="keyline">{states_key()}<a class="crit" href="{CRIT_PAGE}">Criteria<span aria-hidden="true">\u00a0→</span></a></p>'


def masthead():
    """A plain legend: nothing in it can be pointed at or pressed."""
    items = "".join(
        f'<li class="q">{key_mini(i + 1)}<span class="qw">{e(p["name"])}</span><span class="qq">{e(p["question"])}</span></li>'
        for i, p in enumerate(S.PROPS)
    )
    return f"""
<section class="mast" aria-labelledby="h-mast">
  <div class="mast-in">
    <h1 id="h-mast" class="kick">What one proof establishes</h1>
    <ul class="map">{items}</ul>
    {keyline()}
  </div>
</section>"""


# ------------------------------------------------------------------ preview cards
# What a shared link shows: Open Graph and X tags on every page, and one picture per card. The
# renderer writes each picture's source, og/<card>.html (CARD_W x CARD_H CSS px, the view's own
# words and pies); og.mjs renders it to og/<card>.png at CARD_SCALE and records both sha256 in
# og/cards.json. The pages name each picture with its hash, so a new picture is a new URL for link
# caches, and test_cards.py fails when a committed picture was not rendered from its committed source.
SITE_URL = "https://www.inferenceproofs.ai"
CARD_W, CARD_H, CARD_SCALE = 1200, 630, 2


def icon_links():
    rec = cards_record().get("icon")
    v = f"?v={rec['png'][:12]}" if rec else ""
    return (
        '<link rel="icon" href="/og/icon.svg" type="image/svg+xml">'
        f'<link rel="apple-touch-icon" href="/og/icon.png{v}">'
    )


def cards_record():
    f = S.OG / "cards.json"
    return json.loads(f.read_text()) if f.exists() else {}


def card_alt(card):
    """The picture in words, from the same data the picture draws."""
    if card == "home":
        return "Inference proofs: " + ", ".join(p["name"] for p in S.PROPS) + "."
    cfg = first_config(card)
    g = glyph(card)
    states = "; ".join(f"{c['name']}: {c['word']}" for c in g["cells"])
    model = S.MODEL_NAME[cfg["workload"]["model"]["digest"]]
    return f"{name_of(card)} on {model} @{upstream(cfg)['commit'][:8]}. {states}."


def share_meta(title, desc, path, card):
    url = f"{SITE_URL}/{path}"
    rec = cards_record().get(card)
    img = f"{SITE_URL}/og/{card}.png" + (f"?v={rec['png'][:12]}" if rec else "")
    full = full_title(title)
    alt = card_alt(card)
    tags = [
        ("property", "og:type", "website"),
        ("property", "og:site_name", "Inference proofs"),
        ("property", "og:title", full),
        ("property", "og:description", desc),
        ("property", "og:url", url),
        ("property", "og:image", img),
        ("property", "og:image:type", "image/png"),
        ("property", "og:image:width", str(CARD_W * CARD_SCALE)),
        ("property", "og:image:height", str(CARD_H * CARD_SCALE)),
        ("property", "og:image:alt", alt),
        ("name", "twitter:card", "summary_large_image"),
        ("name", "twitter:title", full),
        ("name", "twitter:description", desc),
        ("name", "twitter:image", img),
        ("name", "twitter:image:alt", alt),
    ]
    return f'<link rel="canonical" href="{e(url)}">' + "".join(
        f'<meta {k}="{v}" content="{e(c)}">' for k, v, c in tags
    )
