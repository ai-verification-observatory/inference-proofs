"""Page chrome: addresses, fonts, the inline script, header, search field, footer and the page
frame with its share tags (Open Graph, X, icons) naming the preview pictures by their hash.

`load_faces` reads fonts/faces.json and stops the build on a font file whose name does not carry
its hash. `version` names words.css, words.js and search.json by the first 12 hex of their sha256.
"""

import hashlib
import json
import re

from . import state as S
from .inks import GROUND
from .mark import lockup_svg
from .words import CAUSE_WORD, PETAL_NAME, STEP_WORD, e

# ------------------------------------------------------------------ chrome
# Pages are files <name>.html served at clean, root-relative addresses (vercel.json cleanUrls;
# serve.py does the same locally), so every link works at any depth, the 404 page included.
MANDATE_PAGE = "/mandate"  # what the site is for, what it does and does not do, who runs it
CHECKS_PAGE = "/checks"  # what each of the six checks tests, the order rule, what is not tested
LEARN_PAGE = "/learn"  # the hub of the Learn pages (learn.py), when the tree holds their words


def file_of(path):
    return S.HERE / f"{path.strip('/') or 'index'}.html"


def learn_page(slug):
    """The Learn page at that address, or None (a tree with no Learn words, or without it)."""
    tracks = (S.V.get("learn") or {}).get("tracks") or []
    return next((p for t in tracks for p in t["pages"] if p["slug"] == slug), None)


# ------------------------------------------------------------------ fonts, served from fonts/
# fonts/faces.json lists each woff2 file (named with its own hash, so it can be cached for good)
# with the family, weights, widths and unicode range Google Fonts gives it (latin and latin-ext). A
# subset named arrows, when one is listed, comes last, so its glyphs win where ranges overlap.
PRELOAD = ("big-shoulders-latin.", "martian-mono-latin.")


def load_faces():
    S.FACES = json.loads((S.HERE / "fonts" / "faces.json").read_text())["faces"]
    for f in S.FACES:
        h = hashlib.sha256((S.HERE / "fonts" / f["file"]).read_bytes()).hexdigest()[:10]
        assert f["file"].endswith(f".{h}.woff2"), f"fonts/{f['file']} does not carry its hash"
    S.FACES.sort(key=lambda f: f["subset"] == "arrows")


def font_faces(base, site=False):
    """The @font-face rules, with file URLs under base ("/fonts/" on the site, "../fonts/" for cards).
    On the site the figures' face (Martian Mono) shows a system monospace after 100 ms rather than
    hiding text while it loads; the display face and the cards wait for their own font."""
    out = []
    for f in S.FACES:
        stretch = f"font-stretch:{f['stretch']};" if f.get("stretch") else ""
        display = "fallback" if site and f["fam"] == "Martian Mono" else "block"
        out.append(
            f'@font-face{{font-family:"{f["fam"]}";font-style:normal;font-weight:{f["wt"]};{stretch}'
            f'font-display:{display};src:url({base}{f["file"]}) format("woff2");unicode-range:{f["range"]}}}'
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


# The one inline script, before the first paint: it marks that script runs (html.js) and that
# motion is welcome (html.anim). On a page reached by a view transition (none under reduced
# motion), it also names the row the reader came back from (its name morphs back into
# it) and sets every morph to 200 ms on a quick ease-out. vercel.json allows exactly this script
# by its hash; README.md (Design) says what it does.
HEAD_SCRIPT = (
    '(function(){var d=document.documentElement;d.classList.add("js");'
    'try{if(!matchMedia("(prefers-reduced-motion: reduce)").matches)d.classList.add("anim")}catch(_){}'
    'addEventListener("pagereveal",function(e){var t=e.viewTransition;if(!t)return;try{'
    'var f=navigation.activation.from,r=f&&document.getElementById("row-"+new URL(f.url).pathname.slice(1)),'
    's=r?[[".sname","sysname"]].map(function(x){var el=r.querySelector(x[0]);'
    'el&&el.style.setProperty("view-transition-name",x[1]);return el}):[];'
    "t.ready.then(function(){d.getAnimations({subtree:true}).forEach(function(a){var k=a.effect;"
    'if(k&&/view-transition/.test(k.pseudoElement||""))k.updateTiming({duration:200,easing:"cubic-bezier(.2,.7,.2,1)"})})},function(){});'
    't.finished.finally(function(){s.forEach(function(el){el&&el.style.removeProperty("view-transition-name")})})'
    "}catch(_){}})})()"
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


TABS = (("/", "Ladder", "home"), (LEARN_PAGE, "Learn", "learn"), (CHECKS_PAGE, "Checks", "checks"),
        (MANDATE_PAGE, "Mandate", "mandate"))  # fmt: skip


def header(here, under=False):
    """The top bar: the lockup, the pages as tabs, search and GitHub. here: the page's tab
    ("home", "learn", "checks", "mandate"), "system" for a system page (under the ladder's tab)
    or None; `under` when the page in view is under that tab's page and not the page itself (a
    Learn article). Learn is a tab only when the tree holds the Learn words. Systems are reached
    from the ladder or by search (one link each would not scale)."""
    home = here == "home" and not under
    if here == "system":
        here, under = "home", True

    def tab(href, label, key):
        on = here == key
        attr = f" aria-current={'true' if under else 'page'}" if on else ""
        bar = '<i class="ti" aria-hidden="true"></i>' if on else ""
        return f'<a class="tab{" on" if on else ""}" href="{href}"{attr}>{label}{bar}</a>'

    nav = "".join(tab(*t) for t in TABS if t[2] != "learn" or S.V.get("learn"))
    logo = lockup_svg(LOGO_CAP)
    current = " aria-current=page" if home else ""
    return (
        '<a class="skip" href="#main">Skip to content</a>'
        f'<header class="top"><p class="brand"><a class="logo" href="/"{current}>{logo}</a></p>'
        f'<nav class="tabs" aria-label="Site">{nav}</nav>'
        f"{search_box(here)}"
        f'<a class="repo" href="{e(S.REPO_URL)}">{GITHUB_MARK}<span>GitHub</span></a>'
        "</header>"
    )


# The lockup INFERENCE ⊢ PROOFS at a cap height of 15 px: 1 px per unit of the mark, so its stem
# (3 px), cells (5 px) and gaps (1 px) sit on whole pixels; the words in paper, the mark in cobalt.
LOGO_CAP = 15

SEARCH_MARK = (
    '<svg class="si" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">'
    '<circle cx="6.5" cy="6.5" r="5" fill="none" stroke="currentColor" stroke-width="1.6"/>'
    '<path d="M10.2 10.2 15 15" stroke="currentColor" stroke-width="1.6" stroke-linecap="square"/></svg>'
)


def search_box(here):
    """The search field: a combobox over search.json (words.js fills the list). With script only;
    on phones a button opens it over the top bar. The word in the empty field is a span in the
    muted ink (a placeholder's own ink cannot be set with a one-colon selector); the input keeps a
    blank placeholder so :placeholder-shown says when the field is empty."""
    return (
        '<div class="search" role="search">'
        f'<button type="button" class="sopen" aria-label="Search" aria-expanded="false">{SEARCH_MARK}</button>'
        f'<label class="sr" for="q">Search systems, models, checks and pages</label>'
        f'<span class="sfield">{SEARCH_MARK}'
        '<input id="q" type="text" autocomplete="off" autocorrect="off" autocapitalize="none" '
        'enterkeyhint="go" spellcheck="false" placeholder=" " '
        'role="combobox" aria-expanded="false" aria-controls="q-list" aria-autocomplete="list" '
        'aria-keyshortcuts="Control+K Meta+K">'
        '<span class="sph" aria-hidden="true">Search</span>'
        '<button type="button" class="sclose" aria-label="Close search">×</button></span>'
        f'<ul id="q-list" class="slist" role="listbox" aria-label="Results" tabindex="-1" hidden data-index="{version("search.json")}"></ul>'
        "</div>"
    )


def link(path):
    """A file of the repository, linked at the branch the site is built from."""
    return f"{S.REPO_URL}/blob/{S.LINK_REF}/{path}"


def level_words():
    """The level and its state: "Level 1 (frozen 2026-11-11)", or "(draft)"."""
    lv = S.V["level"]
    state = f"frozen {lv['frozen']}" if lv["frozen"] else "draft"
    return f"{lv['name']} ({state})"


def footer():
    """Every page's footer, one strip of cells: the level file and its digest, the release's
    board file when there is one, the licence and the mandate."""
    lv, rel = S.V["level"], S.V["release"]
    parts = [f'<a href="{e(link(lv["path"]))}">{e(level_words())}</a>'
             f'<code>{e(lv["digest"][:19])}</code>']  # fmt: skip
    if rel is not None:
        board = rel["board"]
        where = link(board) if board.startswith("releases/") else None
        name = f"Release {rel['id']}" + (f", {rel['date']}" if rel["date"] else "")
        parts.append(f'<a class="nw" href="{e(where)}">{e(name)}</a>' if where
                     else f'<span class="nw">{e(name)}</span><code>{e(board)}</code>')  # fmt: skip
    parts.append(f"<span>{e(S.V['licence'])}</span>")
    parts.append(f'<a href="{MANDATE_PAGE}">Mandate</a>')
    cells = "".join(f"<li>{p}</li>" for p in parts)
    return f'<footer class="foot"><ul class="fcells">{cells}</ul></footer>'


def pnav(title, items):
    """A page's sections as a strip that stays under the top bar (words.js marks the one in
    view): the page's title, shown once the band has scrolled away, then one link per section,
    items as (id, label)."""
    links = "".join(f'<a href="#{sid}">{e(label)}</a>' for sid, label in items)
    return (f'<nav class="pnav" aria-label="Sections"><div class="ps">'
            f'<span class="ps-t" aria-hidden="true">{e(title)}</span>{links}</div></nav>')  # fmt: skip


def full_title(title):
    return title if title == "Inference proofs" else f"{title} · Inference proofs"


# A link to another site (every site link is root-relative) opens in a new tab, with no opener and
# no referrer: the reader keeps the page they were reading. A screen reader hears that it does.
EXTERNAL_A = re.compile(r'<a (?![^>]*\btarget=)([^>]*\bhref="https?://[^"]*"[^>]*)>(.*?)</a>', re.S)


def new_tab(html):
    return EXTERNAL_A.sub(
        r'<a \1 target="_blank" rel="noopener noreferrer">\2<span class="sr"> (new tab)</span></a>',
        html,
    )


def page(title, desc, body, cls, path, card):
    """One page. path: its address under the site ("" for the home); card: its preview card's name,
    or None for a page that is never shared (the 404)."""
    meta = share_meta(title, desc, path, card) if card else '<meta name="robots" content="noindex">'
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, interactive-widget=resizes-content">'
        # the stylesheet before the inline script: its @view-transition rule is then known when the
        # page is revealed, so a transition into it is not skipped
        f'{preloads()}<link rel="stylesheet" href="{version("words.css")}">'
        f"<script>{HEAD_SCRIPT}</script>"
        f'<title>{e(full_title(title))}</title><meta name="description" content="{e(desc)}">'
        f'<meta name="color-scheme" content="dark"><meta name="theme-color" content="{GROUND}">'
        f'{meta}{icon_links()}</head><body class="{cls}">{new_tab(body)}'
        f'<p class="sr" aria-live="polite" id="live"></p><script src="{version("words.js")}" defer></script>'
        f'<script defer src="https://cdn.vercel-insights.com/v1/script.js"></script></body></html>'
    )


# ------------------------------------------------------------------ preview cards
# What a shared link shows: Open Graph and X tags on every page, and one picture per card. The
# renderer writes each picture's source, og/<card>.html (CARD_W x CARD_H CSS px, the view's own
# words and pies); og.mjs renders it to og/<card>.png at CARD_SCALE and records both sha256 in
# og/cards.json. The pages name each picture with its hash, so a new picture is a new URL for link
# caches; a page whose picture was not rendered yet names the home card, never a missing file.
SITE_URL = "https://www.inferenceproofs.ai"
CARD_W, CARD_H, CARD_SCALE = 1200, 630, 2


def icon_links():
    """The SVG icon, a 32 px PNG for clients that read no SVG icon, and the touch icon."""

    def v(card):
        rec = cards_record().get(card)
        return f"?v={rec['png'][:12]}" if rec else ""

    return (
        '<link rel="icon" href="/og/icon.svg" type="image/svg+xml">'
        f'<link rel="icon" href="/og/icon-32.png{v("icon-32")}" sizes="32x32" type="image/png">'
        f'<link rel="apple-touch-icon" href="/og/icon.png{v("icon")}">'
    )


def cards_record():
    f = S.OG / "cards.json"
    return json.loads(f.read_text()) if f.exists() else {}


def card_alt(card):
    """The picture in words, from the same data the picture draws."""
    if card == "home":
        return "Inference proofs."
    row = S.PAGE[card]
    states = "; ".join(
        f"{PETAL_NAME[p['id']]}: {STEP_WORD[p['step']]}"
        + (f", {CAUSE_WORD[p['cause']]}" if p["cause"] is not None else "")
        for p in row["glyph"]
    )
    return f"{S.V['systems'][row['system']]['name']} on {rung_of(row)['model']}. {states}."


def rung_of(row):
    return next(r for r in S.V["rungs"] if r["id"] == row["rung"])


def share_meta(title, desc, path, card):
    url = f"{SITE_URL}/{path}"
    if card not in cards_record():
        card = "home"
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
