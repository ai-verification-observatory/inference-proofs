"""MADE OF WORDS: build the prototype pages from the data in _data/.

Run: python3 -I build.py
Reads only _data/site.json and _data/criteria.json (next to this file). Types no number and no
quote: every value, label, quote, pin and hash comes from the two data files. The build computes
pie geometry, the sort keys of the home figures (raw values from the data, units normalised) and
the contrast of each ink, which it writes into README.md between markers.
"""

import html
import json
import math
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE / "_data"
SITE_BYTES = (DATA / "site.json").read_bytes()
CRIT_BYTES = (DATA / "criteria.json").read_bytes()
site = json.loads(SITE_BYTES)
crit = json.loads(CRIT_BYTES)
G, H5, OV = site["glyph"], site["home5"], site["overview"]


def e(s):
    return html.escape(str(s), quote=True)


# ------------------------------------------------------------------ consistency checks
# The sha256 of criteria.json as the data pipeline read it, recorded in site.json. The copy in
# _data/ is in the repository's canonical JSON form (iproofs fmt), so its bytes differ; the
# content checks below tie the two files together instead.
crit_sha = G["input"]["sha256"]
assert G["order"] == crit["order"]
for rid, states in crit["test_mapping"].items():
    if rid in G["rows"]:
        assert G["rows"][rid]["states"] == states, f"states differ for {rid}"

# ------------------------------------------------------------------ inks
GROUND, PAPER, MUTED, RULE = "#0b0b0c", "#f1efe9", "#9b978e", "#6f6a62"
VIOLET = "#c45cff"
INK = {k: v["ink"] for k, v in G["states"].items() if k != "grey"}
CLS = {k: v["cls"] for k, v in G["states"].items()}
WORD = {k: v["word"] for k, v in G["states"].items()}


def lum(h):
    h = h.lstrip("#")
    c = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(a, b):
    x, y = sorted([lum(a), lum(b)], reverse=True)
    return (x + 0.05) / (y + 0.05)


ladder, prev = [], GROUND
ladder.append(
    (
        "Not stated",
        f"none (empty, outline `{RULE}`, {ratio(RULE, GROUND):.2f}:1)",
        f"{lum(GROUND):.3f}",
        "1.00:1",
        "",
    )
)
for st, word in (("red", "No"), ("amber", "Partly"), ("green", "Yes")):
    step = ratio(INK[st], prev)
    assert step >= 1.7, word
    ladder.append(
        (
            word,
            f"`{INK[st]}`",
            f"{lum(INK[st]):.3f}",
            f"{ratio(INK[st], GROUND):.2f}:1",
            f"{step:.2f}:1",
        )
    )
    prev = INK[st]
pairs = [
    ("paper text on ground", PAPER, GROUND),
    ("muted text on ground", MUTED, GROUND),
    ("black text on violet", GROUND, VIOLET),
    ("violet text on ground", VIOLET, GROUND),
]
pairs += [(f"ground text on {WORD[s]}", GROUND, INK[s]) for s in ("green", "amber", "red")]
for name, a, b in pairs:
    assert ratio(a, b) >= 4.5, name

# ------------------------------------------------------------------ sort keys (computed, never typed)
# Each home figure column sorts on the raw number the data stores for it, in the axis chart that
# plots it (site.json: axes.<axis>.charts[<chart>].views.<view>.rows[].value), multiplied into one base
# unit per column by the chart's declared unit. A unit not in UNIT stops the build.
SORT_AXIS = {
    "covers": ("one-proof-covers", "positions"),
    "proof_size": ("proof-size", "per-proof"),
    "check_time": ("check-time", "per-proof"),
    "overhead": ("overhead", "ratio"),
}
UNIT = {
    "token positions": 1,
    "B": 1,
    "kB": 1e3,
    "MB": 1e6,
    "GB": 1e9,
    "TB": 1e12,
    "s": 1,
    "ms": 1e-3,
    "min": 60,
    "h": 3600,
    "ratio": 1,
}
# the words a figure prints after its number, for the build's own cross-check only (never a key)
SHOWN_UNIT = {
    "positions": 1,
    "B": 1,
    "kB": 1e3,
    "MB": 1e6,
    "GB": 1e9,
    "s": 1,
    "ms": 1e-3,
    "min": 60,
    "×": 1,
}
SORT_WORDS = {
    "covers": "covers",
    "proof_size": "proof-size-per-proof",
    "check_time": "check-time-per-proof",
    "overhead": "overhead",
}


def chart(col):
    axis, cid = SORT_AXIS[col]
    return next(c for c in site["axes"][axis]["charts"] if c["id"] == cid)


def sort_key(row_id, col, view):
    """The raw number behind one home figure, in the column's base unit; None when the data has none."""
    ch = chart(col)
    factor = UNIT[ch["unit"]]
    r = next((x for x in ch["views"][view]["rows"] if x["row"] == row_id), None)
    if r is None or r.get("value") is None:
        return None
    return r["value"] * factor


def shown_number(text):
    """A printed figure ("18.78 MB", "1,583×") as a number and the half step of its last digit, in base units."""
    m = re.match(r"^([\d,]+)(?:\.(\d+))?\s*(\S+)", text or "")
    if not m or m.group(3) not in SHOWN_UNIT:
        return None
    f = SHOWN_UNIT[m.group(3)]
    dec = len(m.group(2) or "")
    return float(
        m.group(1).replace(",", "") + ("." + m.group(2) if m.group(2) else "")
    ) * f, 0.5 * 10**-dec * f


def row_keys(row):
    """{view: {col: key or None}} for one home row, checked against the figure the row prints."""
    out = {}
    for view in ("published", "run"):
        out[view] = {}
        for col in SORT_AXIS:
            k = sort_key(row["id"], col, view)
            cell = row["cells"][col][view]
            shown = shown_number(cell.get("value")) if cell.get("value") else None
            if k is None:
                assert shown is None or row["kind"] != "prover", (
                    f"{row['id']} {col} {view}: printed number with no raw value"
                )
            else:
                assert shown is not None, (
                    f"{row['id']} {col} {view}: raw value but no printed number"
                )
                assert abs(k - shown[0]) <= shown[1] * 1.0001, (
                    f"{row['id']} {col} {view}: raw {k} vs printed {cell['value']}"
                )
            out[view][col] = k
        out[view] = out[view]
    return out


def sort_options():
    """[(value, words)] for the sort control: System A to Z first (the default), then each figure column."""
    sk = {s["key"]: s for s in OV["sort_keys"]}
    opts = [("system-asc", "System, A to Z"), ("system-desc", "System, Z to A")]
    for col in SORT_AXIS:
        w = sk[SORT_WORDS[col]]
        assert w["column"] == HEAD[col], col
        opts += [(f"{col}-{d}", f"{HEAD[col]}, {w['dir_words'][d]}") for d in ("asc", "desc")]
    return opts


# ------------------------------------------------------------------ the flat pie


def pt(r, deg):
    a = math.radians(deg)
    return r * math.sin(a), -r * math.cos(a)


def wedge(i, R, g):
    """Wedge i (0..5, clockwise from twelve) of radius R, inset by g from both edges and the arc."""
    a0, a1 = 60 * i, 60 * (i + 1)
    r = R - g
    d = math.degrees(math.asin(g / r))
    ax, ay = pt(2 * g, a0 + 30)
    x0, y0 = pt(r, a0 + d)
    x1, y1 = pt(r, a1 - d)
    return f"M{ax:.2f} {ay:.2f}L{x0:.2f} {y0:.2f}A{r:.2f} {r:.2f} 0 0 1 {x1:.2f} {y1:.2f}Z"


def pie_svg(states, size, cls="", g=None, cells=None):
    """One pie. With cells, each slice carries its property's name and state word (read by words.js)."""
    R = size / 2
    g = g if g is not None else max(1.0, size / 80)
    m = 8 if size > 40 else 2
    parts = []
    for i, st in enumerate(states):
        dx, dy = pt(1, 60 * i + 30)
        extra = ""
        if cells:
            c = cells[i]
            extra = f' data-name="{e(c["name"])}" data-word="{e(c["word"])}"'
        parts.append(
            f'<path class="sl s{i + 1} {CLS[st]}" data-n="{i + 1}"{extra} style="--dx:{dx:.3f};--dy:{dy:.3f}" d="{wedge(i, R, g)}"/>'
        )
    return (
        f'<svg class="pie-svg {cls}" viewBox="{-R - m} {-R - m} {size + 2 * m} {size + 2 * m}" width="{size + 2 * m}" height="{size + 2 * m}" '
        f'aria-hidden="true" focusable="false">{"".join(parts)}</svg>'
    )


def key_mini(n, size=48):
    """One property's place in the pie: its own wedge filled with paper, the other five in black line."""
    R = size / 2
    parts = []
    for i in range(6):
        on = i + 1 == n
        parts.append(f'<path class="{"on" if on else ""}" d="{wedge(i, R - 3, 0.001)}"/>')
    parts.sort(key=lambda x: 'class="on"' in x)  # the filled wedge last, so its outline sits on top
    return f'<svg class="kmini" viewBox="{-R} {-R} {size} {size}" width="{size}" height="{size}" aria-hidden="true" focusable="false">{"".join(parts)}</svg>'


def mini(n, size=22):
    """A small key pie, drawn like the header legend: the one property's wedge in paper, the others in line."""
    out = pie_svg(["grey"] * 6, size, "mini", g=1.0)
    return out.replace(f'class="sl s{n} unstated"', f'class="sl s{n} lit"')


# ------------------------------------------------------------------ words and labels


MD = re.compile(r"`([^`]+)`|\*(?=\S)([^*]+?)(?<=\S)\*")
CUT = (" These tests show only what happened to these attempts, nothing more.", " Printed as text.")


def cut(text):
    """Data sentences the site does not print."""
    for c in CUT:
        text = text.replace(c, "").replace(c.strip(), "")
    return text.strip()


def md_html(text):
    """A quote as HTML: whitespace folded, markdown markers dropped and set as type."""
    text = " ".join(text.split())
    out, last = [], 0
    for m in MD.finditer(text):
        out.append(e(text[last : m.start()]))
        out.append(
            f"<code>{e(m.group(1))}</code>"
            if m.group(1) is not None
            else f"<em>{e(m.group(2))}</em>"
        )
        last = m.end()
    out.append(e(text[last:]))
    return "".join(out)


def silent_words(c):
    sw = c.get("source_words") or ""
    if sw == "not copied yet":
        return "Not copied by us yet"
    if c.get("searched"):
        return f"Silent in the {c['searched']} sources read"
    return c["reason_short"]


KNOWN = ("scope", "grade", "checked", "source", "workload", "grade, step")


def parse_title(t):
    parts = t.split(" · ")
    head, kv = parts[0], []
    for p in parts[1:]:
        k = p.split(": ", 1)[0]
        if ": " in p and k in KNOWN:
            kv.append([k, p.split(": ", 1)[1]])
        elif kv:
            kv[-1][1] += " · " + p
        else:
            head += " · " + p
    return head, kv


def split_value(v):
    """Number, its unit (the next word), and any words after it, as stored."""
    m = re.match(r"^([\d,.]+)\s*(\S*)\s*(.*)$", v)
    return (m.group(1), m.group(2), m.group(3)) if m else (None, None, v)


def fig(v):
    n, u, rest = split_value(v)
    if n is None:
        return f'<span class="na word">{e(rest)}</span>'
    return (
        f'<span class="fig"><span class="n">{e(n)}</span>'
        + (f'<span class="u">{e(u)}</span>' if u else "")
        + (f'<span class="ux">{e(rest)}</span>' if rest else "")
        + "</span>"
    )


COLS = ["covers", "proof_size", "check_time", "overhead"]
HEAD = {
    "covers": "One proof covers",
    "proof_size": "Proof size",
    "check_time": "Check time",
    "overhead": "Overhead",
}
MOCK = '<b class="mock" title="Invented for layout: no benchmark run made this value">MOCK</b>'


def card_line(x, k):
    return next((ln for ln in (x.get("card") or {}).get("lines", []) if ln["k"] == k), None)


def spread_parts(x):
    """A run's spread as stored: the sample size and the range, the two parts the home shows."""
    sp = card_line(x, "SPREAD")
    return sp["v"].split(" · ")[:2] if sp else []


def fallback_lines(x):
    """The label lines under a figure. A cell with no value shows only why (the card's WHY line)."""
    if not x.get("value"):
        why = card_line(x, "WHY")
        if why:
            return [why["v"]]
    sp = spread_parts(
        x
    )  # sample size and range first, whatever else the cell stores (AGENTS.md rule 5)
    if x.get("lines"):
        return sp + x["lines"]
    head, kv = parse_title(x["title"])
    if kv:
        return sp + [f"{k}: {v}" for k, v in kv if k in ("scope", "grade", "grade, step")]
    word = (x.get("absent") or {}).get("text", "")
    if word and head.startswith(word + ": "):
        head = head[len(word) + 2 :]
    return (
        [t + ("." if not t.endswith(".") else "") for t in head.split(". ") if t]
        if ". " in head
        else [head]
    )


def value_link(row, col, view, href):
    """A figure on the home row: a link to the figures on the row's own page; its labels ride in the title."""
    x = row["cells"][col][view]
    inner = (
        fig(x["value"]) if x.get("value") else f'<span class="na">{e(x["absent"]["text"])}</span>'
    )
    lines = "".join(f"<span>{e(ln)}</span>" for ln in fallback_lines(x))
    sp = card_line(x, "SPREAD")
    title = x["title"] + (f" · spread: {sp['v']}" if sp else "")
    return (
        f'<a class="val v-{view}" href="{e(href)}" title="{e(title)}">'
        f'<span class="lbl">{e(HEAD[col])}</span><span class="vm">{inner}</span>'
        f'<span class="sub">{MOCK if x.get("mock") else ""}{lines}</span></a>'
    )


PLATE_ORDER = [
    "spread",
    "as published",
    "scope",
    "its scope",
    "grade",
    "grade, step",
    "checked",
    "workload",
    "precision",
    "baseline",
    "its caveat",
    "our reading",
    "why",
    "note",
    "warning",
    "source",
    "note ",
]


def link_or_text(text, href):
    """A source as a link only when it resolves: a root-relative path (a MOCK fixture in site.json) is text."""
    text = text.replace(" ↗", "")
    return f'<a href="{e(href)}">{e(text)} ↗</a>' if href and not href.startswith("/") else e(text)


def plate(row, col, view):
    x = row["cells"][col][view]
    head, kv = parse_title(x["title"])
    kv = [[k, v, None] for k, v in kv]
    card = x.get("card") or {}
    if not kv and not card.get("lines"):
        kv = [["note ", head, None]]  # no labels stored apart from the title's sentence
    have = {k for k, _, _ in kv}
    for ln in card.get("lines", []):
        k = ln["k"].lower()
        if k == "source":
            for p in kv:
                if p[0] == "source":
                    p[2] = ln.get("href")
            continue
        if k in have or (k in ("grade, step",) and "grade" in have):
            continue
        kv.append([k, ln["v"], ln.get("href")])
    if "workload" not in {k for k, _, _ in kv}:
        kv.append(["workload", row["workload"], None])
    kv.sort(key=lambda p: PLATE_ORDER.index(p[0]) if p[0] in PLATE_ORDER else 99)
    dl = "".join(
        f"<div><dt>{e(k.strip())}</dt><dd>{link_or_text(v, href)}</dd></div>" for k, v, href in kv
    )
    cav = "".join(f'<p class="cav">{e(c["text"])}</p>' for c in card.get("caveats", []))
    val = fig(x["value"]) if x.get("value") else f'<span class="na">{e(x["absent"]["text"])}</span>'
    return (
        f'<div class="plate v-{view}" data-col="{col}"><p class="lbl">{e(HEAD[col])} {MOCK if x.get("mock") else ""}</p>'
        f'<p class="pv">{val}</p><dl>{dl}</dl>{cav}</div>'
    )


# ------------------------------------------------------------------ chrome
FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..900&family=IBM+Plex+Mono:wght@400;500;600&display=block" rel="stylesheet">'
)
PAGE = {sid: f"{sid}.html" for sid in G["orders"]["benchmarked"]}  # one page per benchmarked system
REF_PAGE = (
    "reference.html"  # one page for the reference rows, as the data's own hrefs (/reference/#row)
)


def header(here):
    def a(href, label, key):
        return f'<a href="{href}"{" aria-current=page" if here == key else ""}>{label}</a>'

    nav = a("index.html", "Overview", "home") + "".join(
        a(PAGE[sid], e(site["systems"][sid]["name"]), sid)
        for sid in sorted(PAGE, key=lambda k: site["systems"][k]["name"].lower())
    )
    return (
        f'<header class="top"><p class="brand"><a href="index.html">Inference proofs</a></p>'
        f'<nav aria-label="Site">{nav}</nav>'
        f'<p class="proto">Prototype · results {MOCK}</p></header>'
    )


def footer():
    return (
        f'<footer class="foot" id="criteria"><p>{e(G["label"])} · criteria.json sha256 <code>{crit_sha[:12]}</code></p>'
        f"<p>{e(site['banner'])}</p><p>{e(site['release']['footer_line'])} {MOCK}</p></footer>"
    )


def page(title, desc, body, cls):
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<script>try{{if(!matchMedia("(prefers-reduced-motion: reduce)").matches)document.documentElement.classList.add("anim")}}catch(_){{}}</script>'
        f'<title>{e(title)}</title><meta name="description" content="{e(desc)}"><meta name="color-scheme" content="dark">{FONTS}'
        f'<link rel="stylesheet" href="words.css"></head><body class="{cls}">{body}'
        f'<p class="sr" aria-live="polite" id="live"></p><script src="words.js" defer></script></body></html>'
    )


def states_key():
    return "".join(
        f'<span class="chip"><i class="sw {CLS[s]}"></i>{e(WORD[s])}</span>'
        for s in G["state_order"]
    )


def keyline(cls="keyline"):
    return f'<p class="{cls}">{states_key()}<a class="draft" href="#criteria" title="{e(G["label"])}">{e(G["legend"]["draft_short"])} →</a></p>'


def view_switch():
    chk = dict(parse_title(H5["rows"][0]["cells"]["proof_size"]["published"]["title"])[1])[
        "checked"
    ]
    return (
        f'<div class="grade" role="group" aria-label="Which values to show">'
        f'<button type="button" class="vk" data-view="published" aria-pressed="true">Published by each system</button>'
        f'<button type="button" class="vk" data-view="run" aria-pressed="false">Run here {MOCK}</button>'
        f'<span class="checked" title="{e(H5["bands"]["title"])}">Checked: {e(chk)}</span></div>'
    )


def masthead():
    """A plain legend: nothing in it can be pointed at or pressed."""
    items = "".join(
        f'<li class="q">{key_mini(p["n"])}<span class="qw">{e(p["name"])}</span><span class="qq">{e(p["question"])}</span></li>'
        for p in G["properties"]
    )
    return f"""
<section class="mast" aria-labelledby="h-mast">
  <div class="mast-in">
    <h1 id="h-mast" class="kick">What one proof establishes</h1>
    <ul class="map">{items}</ul>
    {keyline()}
  </div>
</section>"""


# ------------------------------------------------------------------ rows


def aria(g):
    """The data's spoken summary, without the slice numbers and the count before the names."""
    return re.sub(r"(: |; )\d (?=[A-Z])", r"\1", g["aria"]).replace(", six properties:", ":")


def row_html(row, g, href, fig_href, table):
    """One home row. In the sortable table it is an ARIA row of five cells and carries its sort keys."""
    rid = row["id"].split("--")[0] if row["kind"] == "prover" else row["id"]
    pie = pie_svg(g["states"], 120, cells=g["cells"])
    cell = ' role="cell"' if table else ""
    vals = "".join(
        f'<div class="vc"{cell} data-col="{c}">'
        + "".join(
            value_link(row, c, v, fig_href + ("-run" if v == "run" else ""))
            for v in ("published", "run")
        )
        + "</div>"
        for c in COLS
    )
    if row["kind"] == "prover":
        up = site["systems"][row["system"]]["upstream"]
        idle = "".join(f"<span>{e(m)}</span>" for m in (row["model"] or "").split(" · ") if m)
        idle += f'<a class="pin" href="{e(up["href"])}" title="Pinned upstream commit {e(up["commit"])}">@{e(up["commit_short"])}</a>'
    else:
        serves = site["systems"][row["serves"]]["name"] if row.get("serves") else ""
        idle = f"<span>beside {e(serves)}</span><span>{e(row['workload'])}</span>"
    attrs = ""
    if table:
        attrs = f' role="row" data-name="{e(row["name"].lower())}" data-k="{e(json.dumps(row_keys(row), separators=(",", ":")))}"'
    return f'''
<div class="row" id="{e(rid)}"{attrs}>
  <div class="r-main">
    <div class="sysc"{cell}>
      <a class="pie" href="{e(href)}" tabindex="-1" aria-hidden="true">{pie}<span class="tip"></span></a>
      <div class="who"><h2 class="name"><a href="{e(href)}"><span>{e(row["name"])}</span><span class="sr">. {e(aria(g).split(": ", 1)[1])}</span></a></h2><p class="wl">{idle}</p></div>
    </div>
    <div class="vals">{vals}</div>
  </div>
</div>'''


def nb_list():
    rows = {r["id"]: r for r in OV["not_benchmarked"]["rows"]}
    out = ""
    for rid in G["orders"]["not_benchmarked"]:
        r, g = rows[rid], G["rows"][rid]
        q = r["quotes"].get("what")
        quote = (
            f'<blockquote>“{md_html(q["text"])}”</blockquote><a class="qs" href="{e(q["href"])}">{e(q["label"])}'
            + (f" · retrieved {e(q['retrieved'])}" if q.get("retrieved") else "")
            + " ↗</a>"
            if q
            else ""
        )
        meta = " · ".join([r["family_label"], r["status_label"]] + [c.lower() for c in r["chips"]])
        out += f"""
<article class="row nbrow" id="nb-{e(rid)}">
  <div class="r-main">
    <div class="sysc"><span class="pie">{pie_svg(g["states"], 120, cells=g["cells"])}<span class="tip" aria-hidden="true"></span></span>
    <div class="who"><h2 class="name"><span>{e(r["name"])}</span><span class="sr">. {e(aria(g).split(": ", 1)[1])}</span></h2>
      <p class="wl"><span>{e(meta)}</span><span>{e(r["models_short"])}</span></p></div></div>
    <div class="nbq">{quote}</div>
  </div>
</article>"""
    return out


SHORT = {"benchmarked": "Benchmarked", "reference": "Reference", "not_benchmarked": "Not yet"}


def sort_heads():
    """The column heads of the sortable table: each one a button with its sort glyph."""

    def head(col, label, cls=""):
        on = col == "system"
        return (
            f'<div class="hc{cls}" role="columnheader" data-col="{col}"'
            + (' aria-sort="ascending"' if on else "")
            + ">"
            f'<button type="button" class="sb" data-col="{col}">{label}<span class="g" aria-hidden="true">{"↑" if on else "↕"}</span></button></div>'
        )

    return (
        f'<div class="heads" role="row">{head("system", "System", " hsys")}'
        + "".join(head(c, e(HEAD[c])) for c in COLS)
        + "</div>"
    )


def sort_control():
    opts = "".join(
        f'<option value="{v}"{" selected" if v == "system-asc" else ""}>{e(w)}</option>'
        for v, w in sort_options()
    )
    return f'<label class="sortc" for="sort"><span>Sort</span><select id="sort">{opts}</select></label>'


def build_index():
    tabs = OV["tabs"]
    tab_html = "".join(
        f'<button type="button" role="tab" class="tab" id="tab-{t["id"]}" aria-controls="panel-{t["id"]}" aria-selected="{"true" if i == 0 else "false"}" tabindex="{0 if i == 0 else -1}">'
        f'<span class="tl">{e(t["label"])}</span><span class="ts" aria-hidden="true">{e(SHORT[t["id"]])}</span><sup>{t["count"]}</sup></button>'
        for i, t in enumerate(tabs)
    )
    heads = "".join(f"<span>{e(HEAD[c])}</span>" for c in COLS)
    by_name = sorted(
        G["orders"]["benchmarked"], key=lambda sid: site["systems"][sid]["name"].lower()
    )
    assert by_name == G["orders"]["benchmarked"], "default order is System A to Z"
    bench = ""
    for sid in G["orders"]["benchmarked"]:
        row = next(r for r in H5["rows"] if r["system"] == sid and r["kind"] == "prover")
        bench += row_html(row, G["rows"][sid], PAGE[sid], f"{PAGE[sid]}#figures", True)
    refs = ""
    for row in (r for r in H5["rows"] if r["kind"] == "reference"):
        gid = row["id"].split("--")[0]
        refs += row_html(row, G["rows"][gid], f"{REF_PAGE}#{gid}", f"{REF_PAGE}#{row['id']}", False)
    body = f"""
{header("home")}
<main id="main">
{masthead()}
<div class="wrap">
  <div class="controls">
    <div class="tabs" role="tablist" aria-label="Rows to show">{tab_html}<span class="tab-bar" aria-hidden="true"></span></div>
    {view_switch()}
  </div>
  <div class="nbar figs-only"><p class="notice">{e(H5["notice"]["s6"])}</p>{sort_control()}</div>
  <section class="panel" id="panel-benchmarked" role="tabpanel" aria-labelledby="tab-benchmarked">
    <div class="tbl" role="table" aria-label="Benchmarked systems" aria-describedby="sort-now" data-col="system" data-dir="asc">
      {sort_heads()}
      <div class="rows" role="rowgroup">{bench}</div>
    </div>
    <p class="sr" id="sort-now">{e(sort_options()[0][1])}</p>
  </section>
  <section class="panel" id="panel-reference" role="tabpanel" aria-labelledby="tab-reference" hidden>
    <div class="heads" aria-hidden="true"><span>Reference row</span>{heads}</div>
    {refs}
  </section>
  <section class="panel" id="panel-not_benchmarked" role="tabpanel" aria-labelledby="tab-not_benchmarked" hidden>
    <div class="heads" aria-hidden="true"><span>System, A to Z</span><span>In its own words</span></div>
    {nb_list()}
  </section>
</div>
</main>
{footer()}"""
    return page(
        "Inference proofs",
        "Six properties of one proof per system, and the published figures with their labels, sortable by column. Prototype; run-here values are MOCK.",
        body,
        "home",
    )


# ------------------------------------------------------------------ system page: one property view


def quote_html(text, url, label):
    return (
        f'<blockquote>“{md_html(text)}”</blockquote><a class="qs" href="{e(url)}">{e(label)} ↗</a>'
    )


def prop_line(c):
    """One property: name and question, state and our reason, the decisive quote; the rest in a details."""
    st = c["state"]
    generic = st == "grey" and c["reason_short"].startswith("Not stated") and not c.get("source")
    reason = "" if generic else f'<p class="pr">{e(c["reason_short"])}</p>'
    q = (
        quote_html(c["source"]["text"], c["source"]["url"], c["source"]["label"])
        if c.get("source")
        else f'<p class="silent">{e(silent_words(c))}</p>'
    )
    more = [x for x in c.get("quotes", []) if not x.get("decides")]
    items, parts = "", []
    if more or c.get("aside"):
        parts.append("More quotes")
        items += "".join(f"<li>{quote_html(x['text'], x['url'], x['label'])}</li>" for x in more)
        if c.get("aside"):
            a = c["aside"]
            items += (
                f'<li class="aside"><p>{e(a["words"])}</p>'
                + "".join(quote_html(x["text"], x["url"], x["label"]) for x in a["quotes"])
                + "</li>"
            )
    if c.get("note"):
        parts.append("Our note")
        items += f'<li class="pnote"><p>{e(cut(c["note"]))}</p></li>'
    if c.get("outside_pin"):
        o = c["outside_pin"]
        parts.append(f'<span class="opw">{e(o["line"])}</span>')
        items += (
            '<li class="op">'
            + f'<p class="opr"><i class="sw {CLS[o["state"]]}"></i>{e(o["word"])} · {e(o["reason"])}</p>'
            + (
                quote_html(o["text"], o["url"], o["label"])
                if o.get("text")
                else f'<a class="qs" href="{e(o["url"])}">{e(o.get("label", o["url"]))} ↗</a>'
            )
            + "</li>"
        )
    det = (
        f'<details class="more"><summary>{" · ".join(parts)}</summary><ul>{items}</ul></details>'
        if parts
        else ""
    )
    return (
        f'<li class="prop" id="p-{e(c["prop"])}" data-n="{c["n"]}">'
        f'<div class="ph">{mini(c["n"], 26)}<h3 class="pn">{e(c["name"])}</h3><p class="pq">{e(c["question"])}</p></div>'
        f'<div class="pst"><p class="pw"><i class="sw {CLS[st]}"></i>{e(c["word"])}</p>{reason}</div>'
        f'<div class="pb">{q}{det}</div></li>'
    )


def prop_view(g, hid, title, owner=None):
    """The six properties at once: a small pie beside six lines. owner: the id of the heading naming the system."""
    lab = f"h-{e(hid)}" + (f" {e(owner)}" if owner else "")
    return (
        f'<section class="blk props-blk" id="properties-{e(hid)}" aria-labelledby="{lab}">'
        f'<div class="sect-h"><h2 id="h-{e(hid)}" class="sect">{e(title)}</h2>{keyline("keyline dark")}</div>'
        f'<div class="pview"><div class="ppie" role="img" aria-label="{e(aria(g))}">{pie_svg(g["states"], 152)}</div>'
        f'<ol class="props">{"".join(prop_line(c) for c in g["cells"])}</ol></div></section>'
    )


def more_table(row, caption):
    more = ""
    for v in ("published", "run"):
        for m in row["more"][v]:
            head, kv = parse_title(m["title"])
            lab = " · ".join(f"{k}: {val}" for k, val in kv) if kv else head
            val = fig(m["value"]) if m.get("value") else f'<span class="na">{e(m["absent"])}</span>'
            more += f'<tr class="v-{v}"><th scope="row">{e(m["label"])}</th><td class="mv">{val} {MOCK if m.get("mock") else ""}</td><td class="ml">{e(lab)}</td></tr>'
    return (
        f'<table class="mtab"><caption class="sr">{e(caption)}</caption>'
        f'<thead><tr><th scope="col">Figure</th><th scope="col">Value</th><th scope="col">Labels</th></tr></thead><tbody>{more}</tbody></table>'
    )


def control(t):
    c = t.get("control_test")
    if not c or c.get("state") != "filled":
        return ""
    return (
        f'<p class="ctl">{e(c["text"])} {MOCK if c.get("mock") else ""} '
        f'<a class="qs" href="{e(c["href"])}">{e(c["link_text"])} ↗</a></p>'
    )


def jump(items):
    return (
        '<nav class="jump" aria-label="On this page">'
        + "".join(f'<a href="#{h}">{e(t)}</a>' for h, t in items)
        + "</nav>"
    )


def build_system(sid):
    s = site["systems"][sid]
    g = G["rows"][sid]
    row = next(r for r in H5["rows"] if r["system"] == sid and r["kind"] == "prover")
    ovr = next(r for r in OV["rows"] if r["kind"] == "prover" and r["system"] == sid)
    nc = ovr["cells"]["system"]["published"]["card"]
    q = nc["quote"]
    facts = f"<div><dt>kind</dt><dd>{e(row['kind_title'])}</dd></div>"
    facts += "".join(
        f"<div><dt>{e(ln['k'].lower())}</dt><dd>"
        + (
            f'<a href="{e(ln["href"])}">{e(ln["v"].replace(" ↗", ""))} ↗</a>'
            if ln.get("href")
            else e(ln["v"])
        )
        + "</dd></div>"
        for ln in nc["lines"]
    )
    plates = "".join(plate(row, c, v) for v in ("published", "run") for c in COLS)
    t = s["tamper"]
    hc = s["home_configuration"]
    repos = "".join(
        f'<li><a href="{e(r["href"])}">{e(r["repo"])} @{e(r["commit_short"])} ↗</a> <span>{e(r["role"])} · licence <a href="{e(r["licence_href"])}">{e(r["licence"])}</a></span></li>'
        for r in s["about"]["repos"]
    )
    body = f'''
{header(sid)}
<main id="main" class="sys">
  <section class="mast mast-sys" aria-labelledby="h-name">
    <div class="mast-in">
      <div class="crumbs"><p><a href="index.html">← Overview</a><a href="{e(s["upstream"]["href"])}">{e(s["upstream"]["repo"])} @{e(s["upstream"]["commit_short"])} ↗</a></p>
        {jump([(f"properties-{sid}", "Properties"), ("figures", "Figures"), ("tamper", "Tamper tests"), ("sources", "Sources")])}</div>
      <h1 id="h-name" class="sysname"><span class="lt">{e(s["name"])}</span></h1>
    </div>
  </section>
  <div class="wrap">
    <section class="intro" aria-label="{e(s["name"])} in its own words">
      <div class="own-q"><blockquote class="own">“{md_html(q["text"])}”</blockquote><a class="qs" href="{e(q["href"])}">{e(q["label"])} ↗</a></div>
      <dl class="facts">{facts}</dl>
    </section>
    {prop_view(g, sid, "What one proof establishes")}
    <section class="blk" id="figures" aria-labelledby="h-figs">
      <h2 id="h-figs" class="sect">Figures</h2>
      <p class="lead">{e(s["home_line"])} · <a href="{e(hc["source"]["href"])}">{e(hc["source"]["link_text"])} ↗</a></p>
      <p class="lead runs run-only">{e(s["runs_line"])} {MOCK}</p>
      <div class="controls">{view_switch()}</div>
      <div class="plates plates-sys">{plates}</div>
      <h3 class="sect sm">More numbers</h3>
      {more_table(row, f"More numbers for {s['name']}, with scope, grade, checked step and source")}
    </section>
    <section class="blk" id="tamper" aria-labelledby="h-tamper">
      <h2 id="h-tamper" class="sect">Tamper tests on this setup {MOCK}</h2>
      <p class="tamper">{e(cut(t["sentence"]))}</p>
      <dl class="tlab"><div><dt>workload</dt><dd>{e(row["workload"] if row["id"] == t["config_id"] else t["config_id"])}</dd></div><div><dt>configuration</dt><dd>{e(t["config_id"])}</dd></div></dl>
      {control(t)}
    </section>
    <section class="blk" id="sources" aria-labelledby="h-src">
      <h2 id="h-src" class="sect">Sources and pins</h2>
      <ul class="srcs">{repos}<li><a href="{e(s["adapter_readme"])}">Our adapter notes: systems/{e(sid)}/README.md ↗</a></li></ul>
    </section>
  </div>
</main>
{footer()}'''
    return page(
        s["name"],
        f"{s['name']}: six properties of one proof (draft criteria) with the quotes that decide them, and its figures with their labels. Prototype; run-here values are MOCK.",
        body,
        "system",
    )


def build_reference():
    """One page for the reference rows: each reference system's six properties, then its rows' figures."""
    tab = next(t for t in OV["tabs"] if t["id"] == "reference")
    secs, jumps = "", []
    for gid in G["orders"]["reference"]:
        g = G["rows"][gid]
        rows = [r for r in H5["rows"] if r["kind"] == "reference" and r["id"].split("--")[0] == gid]
        r0 = rows[0]
        jumps.append((gid, r0["name"]))
        figs = ""
        for r in rows:
            serves = site["systems"][r["serves"]]["name"]
            plates = "".join(plate(r, c, v) for v in ("published", "run") for c in COLS)
            figs += (
                f'<div class="refrow" id="{e(r["id"])}"><h3 class="sect sm">Beside {e(serves)} · {e(r["workload"])}</h3>'
                f'<div class="plates plates-sys">{plates}</div>'
                + (
                    more_table(r, f"More numbers for {r0['name']} beside {serves}")
                    if any(m.get("value") for v in ("published", "run") for m in r["more"][v])
                    else ""
                )
                + "</div>"
            )
        secs += f'''
    <section class="refsys" id="{e(gid)}" aria-labelledby="h-{e(gid)}">
      <h2 id="h-{e(gid)}" class="refh">{e(r0["name"])}</h2>
      <p class="kt"><span>{e(r0["kind_stamp"].capitalize())}</span> {e(r0["kind_title"])}</p>
      {prop_view(g, gid + "-p", "What one proof establishes", f"h-{gid}")}
      <div class="reffigs blk"><h3 class="sect">Figures</h3>{figs}</div>
    </section>'''
    body = f"""
{header("reference")}
<main id="main" class="sys refpage">
  <section class="mast mast-sys" aria-labelledby="h-name">
    <div class="mast-in">
      <div class="crumbs"><p><a href="index.html">← Overview</a></p>{jump(jumps)}</div>
      <h1 id="h-name" class="sysname refname"><span class="lt">{e(tab["label"])}</span></h1>
    </div>
  </section>
  <div class="wrap">
    <p class="reflead">{e(tab["sentence"])}</p>
    <div class="controls">{view_switch()}</div>
    <p class="notice">{e(H5["notice"]["s6"])}</p>
    {secs}
  </div>
</main>
{footer()}"""
    return page(
        tab["label"],
        "The reference rows: plain serving and a rerun by a weights holder, their six properties and their figures. Prototype; run-here values are MOCK.",
        body,
        "system reference",
    )


def main():
    (HERE / "index.html").write_text(build_index())
    for sid, name in PAGE.items():
        (HERE / name).write_text(build_system(sid))
    (HERE / REF_PAGE).write_text(build_reference())
    first = PAGE[G["orders"]["benchmarked"][0]]
    (HERE / "system.html").write_text(
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="0; url={first}">'
        f'<link rel="canonical" href="{first}"><title>Moved</title></head><body><a href="{first}">{first}</a></body></html>'
    )
    readme = HERE / "README.md"
    if readme.exists():
        txt = readme.read_text()
        table = (
            "| Word | Ink | Luminance | Contrast on the ground `"
            + GROUND
            + "` | Step from the state below |\n|---|---|---|---|---|\n"
            + "\n".join(f"| {a} | {b} | {c} | {d} | {f} |" for a, b, c, d, f in ladder)
            + "\n\n| Pair | Contrast |\n|---|---|\n"
            + "\n".join(f"| {n} (`{a}` on `{b}`) | {ratio(a, b):.2f}:1 |" for n, a, b in pairs)
        )
        txt = re.sub(
            r"<!-- ladder -->.*<!-- /ladder -->",
            "<!-- ladder -->\n" + table + "\n<!-- /ladder -->",
            txt,
            flags=re.S,
        )
        readme.write_text(txt)
    print("built index.html,", ", ".join(PAGE.values()) + ",", REF_PAGE)


if __name__ == "__main__":
    main()
