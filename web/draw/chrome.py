"""Page chrome: addresses, fonts, the inline script, header, search field, footer and the page
frame with its share tags (Open Graph, X, icons) naming the preview pictures by their hash.

`load_faces` reads fonts/faces.json and stops the build on a font file whose name does not carry
its hash. `version` names words.css, words.js and search.json by the first 12 hex of their sha256.
"""

import hashlib
import html
import json
import re

from . import state as S
from .inks import GROUND
from .mark import lockup_svg
from .words import (
    BATCH,
    BATCH_MANY,
    CAUSE_WORD,
    CHECK_NAME,
    FIGURE_HEAD,
    FIGURE_NAME,
    HOW_MULTIPLE,
    HOW_ON,
    NOT_SPLIT,
    PART_WORD,
    PETAL_NAME,
    SERVING_GPU,
    STATE_WORD,
    WHOLE_SESSIONS,
    e,
    petal_step,
    release_tail,
    shown,
)

# ------------------------------------------------------------------ chrome
# Pages are files <name>.html served at clean, root-relative addresses (vercel.json cleanUrls;
# serve.py does the same locally), so every link works at any depth, the 404 page included.
LEVEL_ANCHOR = "level"  # the mandate's line on the level, where the footer's level cell leads
MANDATE_PAGE = (
    "/mandate"  # what the site is for, what it does and does not do, who runs it (under Learn)
)
CHECKS_PAGE = "/checks"  # what each of the six checks tests, the order rule, what is not tested
LEARN_PAGE = "/learn"  # the hub of the Learn pages (learn.py), when the tree holds their words
OVERVIEW_PAGE = "/overview"  # every system on one drawing (overview.py); "/scale" until 2026-11-20
AUTORESEARCH_PAGE = "/autoresearch"  # announced, not open yet: "Coming soon", then what it plans


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
    Site text stays visible while fonts load; preview cards wait for their own font."""
    out = []
    for f in S.FACES:
        stretch = f"font-stretch:{f['stretch']};" if f.get("stretch") else ""
        display = "swap" if site else "block"
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


def page_styles(cls):
    """Inline the page's existing rules, preserving their cascade and all responsive states."""
    styles = json.loads((S.HERE / "styles.json").read_text())
    if styles["source"] != hashlib.sha256((S.HERE / "words.css").read_bytes()).hexdigest():
        raise RuntimeError("styles.json is stale: run npm run styles in web/ before site build")
    excluded = set()
    if "learnpage" not in cls.split():
        excluded.add("learn")
    if "overviewpage" not in cls.split():
        excluded.add("overview")
    if cls == "home":
        excluded.add("details")
    else:
        excluded.add("partners")
    return "".join(part["css"] for part in styles["sections"] if part["scope"] not in excluded)


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


TABS = (("/", "Ladder", "home"), (OVERVIEW_PAGE, "Overview", "overview"),
        (LEARN_PAGE, "Learn", "learn"), (CHECKS_PAGE, "Checks", "checks"),
        (AUTORESEARCH_PAGE, "Autoresearch", "autoresearch"))  # fmt: skip


def header(here, under=False):
    """The top bar: the lockup, the pages as tabs, search and GitHub. here: the page's tab
    ("home", "overview", "learn", "checks", "autoresearch"), "system" for a system page (under the
    ladder's tab) or None; `under` when the page in view is under that tab's page and not the page
    itself (a Learn article, the glossary, the mandate). Learn is a tab only when the tree holds
    the Learn words. Systems are reached
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
# (3 px), cells (5 px) and gaps (1 px) sit on whole pixels; the words in paper, the mark in accent.
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
        '<label class="sr" for="q">Search</label>'
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


def credit_words(linked=True):
    """Who builds the site and who convenes it, from the facts file (`credit`), as one sentence."""
    c = S.V["credit"]

    def org(o):
        return f'<a href="{e(o["url"])}">{e(o["name"])}</a>' if linked else e(o["name"])

    return f"Built by the {org(c['builder'])}, convened by {org(c['lead'])}."


def mark_shape(path):
    """A member's mark file (`credit.members[].mark`): its width over its height, from an SVG's
    viewBox or a PNG's header."""
    data = path.read_bytes()
    if path.suffix == ".png":
        return int.from_bytes(data[16:20], "big") / int.from_bytes(data[20:24], "big")
    box = re.search(rb'viewBox="\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)', data)
    if not box:
        raise RuntimeError(f"{path.name}: a member's mark with no viewBox")
    return float(box[1]) / float(box[2])


# the licence the facts file names -> its text in the repository (a licence with no file stops the
# build)
LICENCE_FILE = {"CC BY 4.0": "LICENSES/CC-BY-4.0.txt"}


# a phone's footer is a list, a name and its value on each line: the names a wide screen's strip
# leaves out
FOOT_NAME = {"level": "Rules", "licence": "Licence"}


def footer():
    """Every page's footer: the level's name, linked to the mandate's line on it (which holds its
    freeze date and links the level file), the release's board file when there is one, the
    licence (linked to its text) and who builds the site. One strip of cells on a wide screen;
    on a phone a ruled list, a name and its value on each line (`fk` the name, `fv` the value;
    `fp` is printed on a phone only, `fx` on a wide screen only)."""
    rel, c = S.V["release"], S.V["credit"]

    def named(key):
        return f'<span class="fk fp">{e(FOOT_NAME[key])}</span>'

    def org(o):
        return f'<a href="{e(o["url"])}">{e(o["name"])}</a>'

    # the level's name under its term on every screen ("Rules", as "Release" names the release)
    level = f'<span class="fv">{e(S.V["level"]["name"])}</span>'
    parts = [f'<a href="{MANDATE_PAGE}#{LEVEL_ANCHOR}"><span class="fk">{e(FOOT_NAME["level"])}'
             f"</span> {level}</a>"]  # fmt: skip
    if rel is not None:
        board = rel["board"]
        where = link(board) if board.startswith("releases/") else None
        tail = release_tail(rel)
        parts.append(f'<a class="nw" href="{e(where)}"><span class="fk">Release</span> '
                     f'<span class="fv">{e(tail)}</span></a>' if where
                     else f'<span class="nw">Release {e(tail)}</span><code>{e(board)}</code>')  # fmt: skip
    lic = S.V["licence"]
    parts.append(f'<a class="nw" href="{e(link(LICENCE_FILE[lic]))}">{named("licence")}'
                 f'<span class="fv">{e(lic)}</span></a>')  # fmt: skip
    # `credit_words`, each half a line of a phone's list
    parts.append(
        '<span class="fcr"><span class="fci"><span class="fk">Built by<span class="fx"> the</span>'
        f'</span> {org(c["builder"])}</span><span class="fx">, </span><span class="fci">'
        f'<span class="fk">convened by</span> {org(c["lead"])}</span><span class="fx">.</span></span>'
    )
    cells = "".join(f"<li>{p}</li>" for p in parts)
    return f'<footer class="foot"><ul class="fcells">{cells}</ul></footer>'


def pnav(title, items, end=""):
    """A page's sections as a strip that stays under the top bar (words.js marks the one in
    view): the page's title, shown once the band has scrolled away, then one link per section,
    items as (id, label); `end` at the strip's right end, out of its scroll."""
    links = "".join(f'<a href="#{sid}">{e(label)}</a>' for sid, label in items)
    return (f'<nav class="pnav" aria-label="Sections"><div class="ps">'
            f'<span class="ps-t" aria-hidden="true">{e(title)}</span>{links}</div>{end}</nav>')  # fmt: skip


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


def page(title, desc, body, cls, path, card, css=""):
    """One page. path: its address under the site ("" for the home); card: its preview card's name,
    or None for a page that is never shared (the 404); css: rules of this page's own, written by
    its renderer after the site's (where its marks stand, the Overview page: `overview.py`)."""
    title, desc = SEARCH_COPY.get(path, (title, desc))
    meta = (
        share_meta(title, desc, path, card, body)
        if card
        else '<meta name="robots" content="noindex">'
    )
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, interactive-widget=resizes-content">'
        # the styles before the inline script: the @view-transition rule is then known when the
        # page is revealed, so a transition into it is not skipped
        f"{preloads()}<style>{page_styles(cls)}{css}</style>"
        f"<script>{HEAD_SCRIPT}</script>"
        f'<title>{e(full_title(title))}</title><meta name="description" content="{e(desc)}">'
        f'<meta name="color-scheme" content="dark"><meta name="theme-color" content="{GROUND}">'
        f'{meta}{icon_links()}</head><body class="{cls}">{new_tab(body)}'
        f'<p class="sr" role="status" aria-atomic="true" id="live"></p><script src="{version("words.js")}" defer></script>'
        f'<script defer src="https://cdn.vercel-insights.com/v1/script.js"></script></body></html>'
    )


# ------------------------------------------------------------------ preview cards
# What a shared link shows: Open Graph and X tags on every page, and one picture per card. The
# renderer writes each picture's source, og/<card>.html (CARD_W x CARD_H CSS px, the view's own
# words and pies); og.mjs renders it to og/<card>.png at CARD_SCALE and records both sha256 in
# og/cards.json. The pages name each picture with its hash, so a new picture is a new URL for link
# caches; a page whose picture was not rendered, or was rendered from another source than the one
# this build wrote (card_current), names the home card, never a missing or stale picture.
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
    """The picture in words, from the same data the picture draws: the system and its model, the
    band's figure, the standing, proof size and verify time per reply, the petals. Each figure with its
    unit, as the picture prints it."""
    if card == "home":
        return "Inference proofs."
    row = S.PAGE[card]
    lead = lead_words(row)
    figs = [(FIGURE_HEAD["proof-size"], row["figures"]["proof_bytes_per_reply"]),
            (FIGURE_HEAD["check-time"], row["figures"]["verify_seconds_per_reply"])]  # fmt: skip
    cells = ". ".join(f"{k}: {fig_words(v)}" for k, v in figs)
    states = "; ".join(
        f"{PETAL_NAME[p['id']]}: {petal_step(p)}"
        + (f", {CAUSE_WORD[p['cause']]}" if p["step"] is None else "")
        for p in row["glyph"]
    )
    name = S.V["systems"][row["system"]]["name"]
    # the standing's own colon (before the checks not held) reads as brackets after "Standing:"
    head, colon, rest = standing(row).partition(": ")
    stand = f"{head} ({rest})" if colon else head
    return (f"{name} on {rung_of(row)['model']}. {lead}. Standing: {stand}. {cells}. "
            f"{states}.")  # fmt: skip


def rung_of(row):
    return next(r for r in S.V["rungs"] if r["id"] == row["rung"])


# ------------------------------------------------------------------ a row's figures and standing
# Here, not in ladder.py, so the share tags (`card_alt`) say what the pages and the card print.
def has(f):
    return f is not None and f["value"] is not None


def counted(row):
    """The counted sessions a row's figures are over."""
    return len(row["sessions"]) or None


def fig_words(f):
    """A stored figure in plain words: the number in its unit."""
    return shown(f["value"], f["unit"]) if has(f) else "none"


# CO-7: a printed multiple's two parts, where the system generates in a phase of its own, in the
# order they are drawn (the part that is not generation first)
SPLITS = {"multiple": (("proving", "proving_multiple"), ("generation", "generation_multiple")),
          "session_multiple": (("commit_and_proving", "session_commit_and_proving_multiple"),
                               ("generation", "session_generation_multiple"))}  # fmt: skip


def further():
    """Whether the board was built by the further-reply rule (RFC-0018 CO-9, Q55: every release
    after v1.0): its rows print a further reply's two multiples, the total and the proving part."""
    return S.V.get("cost_rule") == "further-reply"


def lead_figure(row):
    """A row's one figure (CO-5, amended 2026-11-15): the whole sessions' multiple, named so in
    its label, on every row that has one, so the rows of a rung print one scope; else the steady
    multiple (or its null). The order rule still reads the steady multiple (OR-3): this changes
    what is printed, never a position. On a board built by the further-reply rule (CO-9, Q55), a
    further reply's total multiple on every row, the proving one beside it (`proving_figure`).
    Returns (label, figure, its key in the row's figures)."""
    figs = row["figures"]
    if further():
        return FIGURE_NAME["multiple"], figs["further_reply_multiple"], "further_reply_multiple"
    if has(figs["session_multiple"]):
        n = rung_of(row)["requests_per_session"]
        return (f"{FIGURE_NAME['multiple']}, {WHOLE_SESSIONS.format(n=n)}",
                figs["session_multiple"], "session_multiple")  # fmt: skip
    return FIGURE_NAME["multiple"], figs["multiple"], "multiple"


def proving_figure(row):
    """CO-9: the row's proving multiple, printed beside its total on every surface; None on a
    board built by the whole-session rule."""
    return row["figures"].get("further_reply_proving_multiple") if further() else None


def not_split(row):
    """CO-9: why a row prints no proving multiple, in the board's words ("no split: slots 1, 2,
    3: ..."), for the title of its "not measured"."""
    f = proving_figure(row) or {}
    split = row.get("further_split") or {}
    return f.get("note") or split.get("cause") or NOT_SPLIT


def batch_words(row):
    """CO-9: the replies one proof batch holds, in words ("24 replies per proof"); None where
    the board does not say."""
    n = (row.get("proving_batch") or {}).get("replies")
    if not isinstance(n, int):
        return None
    return BATCH.get(n) or BATCH_MANY.format(n=n)


def gpu_name(row):
    """The GPU the row's counted sessions ran on, as their manifests record it (the facts file's
    short name); the serving GPU where no manifest is stored."""
    seen = (row.get("machine") or {}).get("gpu_model") or []
    return " or ".join(seen) if seen else SERVING_GPU


def how_computed(row, key=None):
    """The headline in one plain sentence (B5): what is divided by what, at which scope, on
    which GPUs, at one GPU price, by the figure the row prints (`lead_figure`), or by `key` (the
    proving multiple beside it, CO-9)."""
    key = key or lead_figure(row)[2]
    gpu = gpu_name(row)
    on = HOW_ON[gpu == SERVING_GPU].format(gpu=gpu, serving=SERVING_GPU)
    return HOW_MULTIPLE[key].format(on=on)


def parts_of(row, key):
    """The two parts of the row's figure `key` as (name, figure), or none where either part has
    no value (CO-7)."""
    parts = [(PART_WORD[w], row["figures"].get(k)) for w, k in SPLITS.get(key, ())]
    return parts if parts and all(has(f) for _, f in parts) else []


# CO-8: the proved rate whose quotient with the served rate is the printed multiple, by the
# multiple's key (amended 2026-11-26, Q55: a further reply's on a board built by its rule)
PROVED_RATE = {"session_multiple": "session_reply_tokens_per_gpu_second",
               "further_reply_multiple": "further_reply_tokens_per_gpu_second"}  # fmt: skip


def rate_pair(row):
    """The two rates the headline is made of (CO-8, amended 2026-11-16): the row's reply tokens
    per GPU-second over whole sessions and its model's serving baseline's, as (proved, served,
    proved GPU, served GPU); None where the row's figure is not the whole sessions' multiple or
    either rate is missing, so served over proved is always the multiple printed above it."""
    key = lead_figure(row)[2]
    proved = row["figures"].get(PROVED_RATE.get(key, ""))
    b = rung_of(row)["baseline"] or {}
    served = b.get("reply_tokens_per_gpu_second")
    if not (has(proved) and has(served)):
        return None
    return proved, served, gpu_name(row), serving_gpu(b)


def serving_gpu(b):
    """The GPU a model's serving baseline ran on, by its short name (CO-4: H200)."""
    return (b or {}).get("gpu") or SERVING_GPU


def only_run(row):
    """Whether the row is the only system run on its model (OR-4, amended 2026-11-15): its
    position is then printed unfilled, with no count, since nothing on the model was ranked
    against it."""
    return rung_of(row)["systems_run"] == 1


ONLY_RUN = "only system run on this model"


def share_words(row):
    """A system page in a sentence (its description and share text, depth 0): the system, its
    model and standing and its one figure, as the card prints them (its two parts are the system
    page's Cost block's, CO-7, amended 2026-11-17)."""
    name = S.V["systems"][row["system"]]["name"]
    said = standing(row)  # a state word is lower case in prose
    return f"{name} on {rung_of(row)['model']}, {said[0].lower() + said[1:]}. {lead_words(row)}."


def lead_words(row):
    """The row's one figure in words: "Cost vs serving: 1,317×". Its two parts are not said here
    (CO-7, amended 2026-11-17: not every system times them apart, so they are no surface figure)."""
    _, f, _ = lead_figure(row)
    said = f"{FIGURE_HEAD['multiple']}: {fig_words(f)}"
    if further():  # CO-9: the proving multiple beside it, or that it is not measured
        p = proving_figure(row)
        said += f"; {FIGURE_HEAD['proving']}: {fig_words(p) if has(p) else NOT_SPLIT}"
    return said


def not_passed(row):
    """The standing of a row that has not passed (RFC-0018 §2.3, amended 2026-11-16): "Not
    passed" with a failed check, "Not passed yet" while every check not passed is not decided (a
    check not decided is never worded as a failure)."""
    failed = any(c["state"] == "failed" for c in row["checks"])
    return "Not passed" if failed else "Not passed yet"


def standing(row):
    """Passed (a system on a model, SI-6), Passed, not ranked with why, or Not passed with the
    checks not passed (SI-1), each named as a check."""
    if row["passed"] and not row["ranked"]:
        return f"Passed, not ranked: {row['unranked_reason']}"
    if row["passed"]:
        return "Passed"
    missing = [f"{CHECK_NAME[c['id']]} check {STATE_WORD[c['state']]}" for c in row["checks"]
               if c["state"] != "held"]  # fmt: skip
    return f"{not_passed(row)}: " + ", ".join(missing) if missing else not_passed(row)


def card_current(card):
    """Whether og/<card>.png was rendered from the source this build wrote (cards.json holds the
    source's sha256): a picture of an earlier board is never named."""
    rec, src = cards_record().get(card), S.OG / f"{card}.html"
    return (
        bool(rec) and src.exists() and rec["source"] == hashlib.sha256(src.read_bytes()).hexdigest()
    )


# Search copy describes the existing page; it never changes the visible heading or lead.
SEARCH_COPY = {
    "": (
        "Provable inference benchmark",
        "Compare proof-of-inference systems on open-weights models: six checks, proving cost vs serving, proof size, verification time and fidelity.",
    ),
    "deployment": (
        "AI treaty verification and deployments",
        "How proofs of inference could support a hypothetical US-China AI agreement: model commitments, sampled replies, trusted traffic records and verification limits.",
    ),
    "glossary": (
        "Provable inference glossary",
        "Definitions for proof of inference, zero knowledge, soundness, model commitments, quantization, fidelity and trusted execution environments.",
    ),
    "learn": (
        "Learn about proofs of inference",
        "Learn what a proof of inference shows, how verification works, and how to interpret benchmark costs, model fidelity and AI treaty proposals.",
    ),
}

# Topics are local to pages that discuss them, not claims about a system's guarantees.
PAGE_TOPICS = {
    "": ("Proof of inference", "Verifiable inference", "LLM inference benchmarks", "NVIDIA H200"),
    "overview": ("Proving cost", "Proof size", "Verification time", "NVIDIA H200"),
    "checks": ("Inference verification", "Negative controls", "Model fidelity", "NVIDIA H200"),
    "mandate": ("Benchmark methodology", "Reproducible research"),
    "learn": ("Proof of inference", "AI verification"),
    "proof-of-inference": ("Proof of inference", "Model commitments", "Verification limits"),
    "how-a-check-works": ("Inference verification", "Model commitments", "Proving cost"),
    "deployment": (
        "AI treaty verification",
        "International AI agreements",
        "Hypothetical US-China AI agreement",
        "Trusted execution environments",
        "Traffic sampling",
    ),
    "method": ("Benchmark methodology", "Proving cost", "Model fidelity"),
    "statement": ("Verifiable computation", "Quantization", "Soundness"),
    "forward-pass": ("Verifiable computation", "Sumcheck", "Matrix multiplication"),
    "glossary": ("Proof of inference", "Zero knowledge", "Soundness", "Model fidelity"),
}


def share_meta(title, desc, path, card, body):
    url = f"{SITE_URL}/{path}"
    if card != "home" and not card_current(card):
        card = "home"
    rec = cards_record().get(card)
    img = f"{SITE_URL}/og/{card}.png" + (f"?v={rec['png'][:12]}" if rec else "")
    full = full_title(title)
    alt = card_alt(card)
    tags = [
        ("name", "robots", "index, follow, max-image-preview:large"),
        ("property", "og:locale", "en_US"),
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
    data = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "@id": url,
        "url": url,
        "name": full,
        "description": desc,
        "inLanguage": "en",
        "isPartOf": {
            "@type": "WebSite",
            "@id": f"{SITE_URL}/#website",
            "url": f"{SITE_URL}/",
            "name": "Inference proofs",
        },
    }
    topics = PAGE_TOPICS.get(path, ("Proof of inference", "Model fidelity", "Proving cost"))
    data["about"] = [{"@type": "Thing", "name": topic} for topic in topics]
    data["keywords"] = list(topics)
    # Section names and citation anchors come from the rendered headings, never a second outline.
    parts = [
        {
            "@type": "WebPageElement",
            "@id": f"{url}#{anchor}",
            "name": html.unescape(re.sub(r"<[^>]+>", "", label)),
        }
        for anchor, label in re.findall(r'<h2\b[^>]*\bid="([^"]+)"[^>]*>(.*?)</h2>', body, re.S)
    ]
    if parts:
        data["hasPart"] = parts
    data["isPartOf"]["sameAs"] = S.REPO_URL
    data["primaryImageOfPage"] = {
        "@type": "ImageObject",
        "url": img,
        "caption": alt,
        "width": CARD_W * CARD_SCALE,
        "height": CARD_H * CARD_SCALE,
    }
    if path:
        crumbs = [("Inference proofs", f"{SITE_URL}/")]
        if learn_page(path) or path in {"glossary", MANDATE_PAGE.strip("/")}:
            crumbs.append(("Learn", f"{SITE_URL}/learn"))
        crumbs.append((title, url))
        data["breadcrumb"] = {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": i, "name": name, "item": address}
                for i, (name, address) in enumerate(crumbs, 1)
            ],
        }
    structured = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return (
        f'<script type="application/ld+json">{structured}</script>'
        f'<link rel="canonical" href="{e(url)}">'
        '<link rel="help" type="text/plain" href="/llms.txt" title="Site guide for agents">'
    ) + "".join(f'<meta {k}="{v}" content="{e(c)}">' for k, v, c in tags)
