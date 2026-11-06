"""MADE OF WORDS: build the prototype pages from the data in _data/.

Run: python3 -I build.py
Reads only _data/site.json and _data/criteria.json (next to this file). Types no number: every
value, label, pin and hash comes from the two data files. The site shows only the benchmark's own
runs, set side by side per model. The pages carry no marking of placeholder data: the README
says which numbers are placeholders. The build
computes pie geometry, the sort keys of the home figures (raw values from the data, units
normalised) and the contrast of each ink, which it writes into README.md between markers.
"""

import html
import json
import math
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE / "_data"
site = json.loads((DATA / "site.json").read_bytes())
crit = json.loads((DATA / "criteria.json").read_bytes())
G, H5, OV = site["glyph"], site["home5"], site["overview"]
VIEW = "run"  # the benchmark's own runs; the systems' published figures are not shown


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

# ------------------------------------------------------------------ models
# Each system is shown on the biggest model it runs (total parameters in its workload records).
# Rows are set side by side only within one model; the models follow each other, biggest first.


def model_name(row):
    return (row.get("model") or "").split(" · ")[0]


def wl_model(wid):
    return site["workloads"][wid]["model"]


PROVERS = [r for r in H5["rows"] if r["kind"] == "prover"]


def biggest_workload(sid):
    wls = [w for w in site["workloads"].values() if w["system"] == sid]
    return max(wls, key=lambda w: w["model"]["parameters_total"])["id"]


for _r in PROVERS:
    assert (
        wl_model(_r["workload"])["digest"] == wl_model(biggest_workload(_r["system"]))["digest"]
    ), f"{_r['id']}: the home row runs the system's biggest model"


def model_of(row):
    """The model a row ran, by the content hash its workload records."""
    return wl_model(row["workload"])["digest"]


MODELS = sorted(
    {model_of(r) for r in PROVERS},
    key=lambda d: (
        -next(wl_model(r["workload"])["parameters_total"] for r in PROVERS if model_of(r) == d)
    ),
)
MODEL_NAME = {d: model_name(next(r for r in PROVERS if model_of(r) == d)) for d in MODELS}
assert len(set(MODEL_NAME.values())) == len(MODELS)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


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
# plots it (site.json: axes.<axis>.charts[<chart>].views.run.rows[].value), multiplied into one base
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


def sort_key(row_id, col, view=VIEW):
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
    """{col: key or None} for one home row, checked against the figure the row prints."""
    out = {}
    for col in SORT_AXIS:
        k = sort_key(row["id"], col)
        cell = row["cells"][col][VIEW]
        shown = shown_number(cell.get("value")) if cell.get("value") else None
        if k is None:
            assert shown is None or row["kind"] != "prover", (
                f"{row['id']} {col}: printed number with no raw value"
            )
        else:
            assert shown is not None, f"{row['id']} {col}: raw value but no printed number"
            assert abs(k - shown[0]) <= shown[1] * 1.0001, (
                f"{row['id']} {col}: raw {k} vs printed {cell['value']}"
            )
        out[col] = k
    return out


def sort_words():
    """{col: {dir: words}}: how each order reads aloud, from the data's own direction words."""
    sk = {s["key"]: s for s in OV["sort_keys"]}
    out = {"system": {"asc": "A to Z", "desc": "Z to A"}}
    for col in SORT_AXIS:
        w = sk[SORT_WORDS[col]]
        assert w["column"] == HEAD[col], col
        out[col] = dict(w["dir_words"])
    return out


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


# ------------------------------------------------------------------ words and labels


CUT = (" These tests show only what happened to these attempts, nothing more.", " Printed as text.")


def cut(text):
    """Data sentences the site does not print."""
    for c in CUT:
        text = text.replace(c, "").replace(c.strip(), "")
    return text.strip()


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
# Placeholder markings in the data's own label text ("· MOCK ·", "MOCK fixture", warnings about mock
# values) are dropped: the site prints figures and their labels as a release would.
MOCKY = re.compile(r"\bmock\b", re.I)


def clean(text):
    """A label without its placeholder parts: " · "-separated segments that mention mock are dropped."""
    return " · ".join(s for s in str(text).split(" · ") if not MOCKY.search(s))


def clean_prose(text):
    """A sentence without the clauses (split at "; ") that speak of placeholder records."""
    out = []
    for s in str(text).split(". "):
        keep = "; ".join(c for c in s.rstrip(".").split("; ") if not MOCKY.search(c))
        if keep:
            out.append(keep)
    return ". ".join(out) + "." if out else ""


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


def cell(row, col):
    """One figure of a row. A reference stores "same as above" for what one proof covers: it shows the
    figure of the system it runs beside, named, since the references no longer sit under that row."""
    x = row["cells"][col][VIEW]
    if row["kind"] == "reference" and x.get("value") == "same as above":
        served = next(r for r in PROVERS if r["workload"] == row["workload"])
        name = site["systems"][served["system"]]["name"]
        words = x["title"].replace("the row it serves", name)
        assert words != x["title"], x["title"]
        y = served["cells"][col][VIEW]
        card = {**y["card"], "caveats": [*y["card"].get("caveats", []), {"text": words}]}
        return {**y, "title": words, "lines": [words], "card": card}
    return x


def value_link(row, col, href):
    """A figure on the home row: a link to the figures on the row's own page; its labels ride in the title."""
    x = cell(row, col)
    inner = (
        fig(x["value"]) if x.get("value") else f'<span class="na">{e(x["absent"]["text"])}</span>'
    )
    lines = "".join(f"<span>{e(clean(ln))}</span>" for ln in fallback_lines(x) if clean(ln))
    sp = card_line(x, "SPREAD")
    title = clean(x["title"] + (f" · spread: {sp['v']}" if sp else ""))
    return (
        f'<a class="val" href="{e(href)}" title="{e(title)}">'
        f'<span class="lbl">{e(HEAD[col])}</span><span class="vm">{inner}</span>'
        f'<span class="sub">{lines}</span></a>'
    )


PLATE_ORDER = [
    "spread",
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
    """A source as a link only when it resolves: a root-relative path is text."""
    text = text.replace(" ↗", "")
    return f'<a href="{e(href)}">{e(text)} ↗</a>' if href and not href.startswith("/") else e(text)


def plate(row, col):
    x = cell(row, col)
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
    if "workload" not in {k for k, _, _ in kv} and not row.get("summary"):
        kv.append(["workload", row["workload"], None])
    kv.sort(key=lambda p: PLATE_ORDER.index(p[0]) if p[0] in PLATE_ORDER else 99)
    kv = [[k, clean(v), href] for k, v, href in kv if clean(v)]
    dl = "".join(
        f"<div><dt>{e(k.strip())}</dt><dd>{link_or_text(v, href)}</dd></div>" for k, v, href in kv
    )
    cav = "".join(f'<p class="cav">{e(c["text"])}</p>' for c in card.get("caveats", []))
    val = fig(x["value"]) if x.get("value") else f'<span class="na">{e(x["absent"]["text"])}</span>'
    return (
        f'<div class="plate" data-col="{col}"><p class="lbl">{e(HEAD[col])}</p>'
        f'<p class="pv">{val}</p><dl>{dl}</dl>{cav}</div>'
    )


# ------------------------------------------------------------------ chrome
FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..900&family=IBM+Plex+Mono:wght@400;500;600&display=block" rel="stylesheet">'
)
PAGE = {sid: f"{sid}.html" for sid in G["orders"]["benchmarked"]}  # one page per benchmarked system
REF_PAGE = "reference.html"  # one page for the reference systems


# The project's repository, as the data's own links name it (every workload and source link
# points into it); the header links to it.
REPOS = {
    "/".join(w["href"].split("github.com/", 1)[1].split("/")[:2])
    for w in site["workloads"].values()
}
assert len(REPOS) == 1, REPOS
REPO_URL = f"https://github.com/{REPOS.pop()}"
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

    nav = a("index.html", "Overview", "home") + "".join(
        a(PAGE[sid], e(site["systems"][sid]["name"]), sid)
        for sid in sorted(PAGE, key=lambda k: site["systems"][k]["name"].lower())
    )
    return (
        f'<header class="top"><p class="brand"><a href="index.html">Inference proofs</a></p>'
        f'<nav aria-label="Site">{nav}</nav>'
        f'<a class="repo" href="{e(REPO_URL)}">{GITHUB_MARK}GitHub</a>'
        "</header>"
    )


def footer():
    return (
        f'<footer class="foot" id="criteria"><p>{e(G["label"])} · criteria.json sha256 <code>{crit_sha[:12]}</code></p>'
        f"<p>{e(site['release']['footer_line'])}</p></footer>"
    )


def page(title, desc, body, cls, path, card):
    """One page. path: its address under the site ("" for the home); card: its preview card's name."""
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<script>try{{if(!matchMedia("(prefers-reduced-motion: reduce)").matches)document.documentElement.classList.add("anim")}}catch(_){{}}</script>'
        f'<title>{e(title)}</title><meta name="description" content="{e(desc)}"><meta name="color-scheme" content="dark">'
        f"{share_meta(title, desc, path, card)}{icon_links()}{FONTS}"
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


# ------------------------------------------------------------------ home rows


def aria(g):
    """The data's spoken summary, without the slice numbers and the count before the names."""
    return re.sub(r"(: |; )\d (?=[A-Z])", r"\1", g["aria"]).replace(", six properties:", ":")


def pin_link(sid):
    up = site["systems"][sid]["upstream"]
    return f'<a class="pin" href="{e(up["href"])}" title="Pinned upstream commit {e(up["commit"])}">@{e(up["commit_short"])}</a>'


def row_html(row, g, href, right, table=False):
    """One home row: pie, name and what it ran, then `right` (four figures, or one line)."""
    rid = row["id"].split("--")[0] if row["kind"] == "prover" else row["id"]
    cell = ' role="cell"' if table else ""
    if row["kind"] == "prover":
        idle = "".join(f"<span>{e(m)}</span>" for m in (row["model"] or "").split(" · ") if m)
        idle += pin_link(row["system"])
    else:
        kt = row[
            "kind_title"
        ]  # "Plain serving: the baseline ..." reads without the name it repeats
        idle = f"<span>{e(kt[len(row['name']) + 2 :] if kt.startswith(row['name'] + ': ') else kt)}</span>"
    attrs = ""
    if table:
        attrs = f' role="row" data-name="{e(row["name"].lower())}" data-k="{e(json.dumps(row_keys(row), separators=(",", ":")))}"'
    return f'''
<div class="row" id="{e(rid)}"{attrs}>
  <div class="r-main">
    <div class="sysc"{cell}>
      <a class="pie" href="{e(href)}" tabindex="-1" aria-hidden="true">{pie_svg(g["states"], 120, cells=g["cells"])}<span class="tip"></span></a>
      <div class="who"><h3 class="name"><a href="{e(href)}"><span>{e(row["name"])}</span><span class="sr">. {e(aria(g).split(": ", 1)[1])}</span></a></h3><p class="wl">{idle}</p></div>
    </div>
    {right}
  </div>
</div>'''


def figures(row, href, table):
    cell = ' role="cell"' if table else ""
    return (
        '<div class="vals">'
        + "".join(
            f'<div class="vc"{cell} data-col="{c}">{value_link(row, c, href)}</div>' for c in COLS
        )
        + "</div>"
    )


def sort_heads():
    """The column heads of the sortable table: each one a button with its sort glyph."""
    words = sort_words()

    def head(col, label, cls=""):
        on = col == "system"
        w = words[col]
        return (
            f'<div class="hc{cls}" role="columnheader" data-col="{col}"'
            + (' aria-sort="ascending"' if on else "")
            + ">"
            f'<button type="button" class="sb" data-col="{col}" data-asc="{e(w["asc"])}" data-desc="{e(w["desc"])}">'
            f'{label}<span class="g" aria-hidden="true">{"↑" if on else "↕"}</span></button></div>'
        )

    return (
        f'<div class="heads" role="row">{head("system", "System", " hsys")}'
        + "".join(head(c, e(HEAD[c])) for c in COLS)
        + "</div>"
    )


def nb_grid():
    rows = {r["id"]: r for r in OV["not_benchmarked"]["rows"]}
    out = ""
    for rid in sorted(G["orders"]["not_benchmarked"], key=lambda k: rows[k]["name"].lower()):
        r, g = rows[rid], G["rows"][rid]
        meta = " · ".join([r["family_label"], r["status_label"]] + [c.lower() for c in r["chips"]])
        out += (
            f'<li class="nb" id="nb-{e(rid)}"><span class="nbpie" role="img" aria-label="{e(aria(g))}">{pie_svg(g["states"], 56)}</span>'
            f'<div><h3 class="nbn">{e(r["name"])}</h3><p class="nbm">{e(r["models_short"])}</p><p class="nbm">{e(meta)}</p></div></li>'
        )
    return f'<ul class="nbgrid">{out}</ul>'


def workload_line(row):
    """What the row ran, as the data says it, without the model name the section already prints."""
    sys_row = next(r for r in PROVERS if r["workload"] == row["workload"])
    line = site["systems"][sys_row["system"]]["home_line"]
    name = model_name(sys_row)
    return line.split(" · ", 1)[1] if line.startswith(name + " · ") else line


def plain_heads(first):
    """Column heads for a block that does not sort: the same columns, for the eye only."""
    return (
        f'<div class="heads plain" aria-hidden="true"><span class="hsys">{e(first)}</span>'
        + "".join(f"<span>{e(HEAD[c])}</span>" for c in COLS)
        + "</div>"
    )


def by_name(rows):
    return sorted(rows, key=lambda r: site["systems"][r["system"]]["name"].lower())


def ref_summary(gid):
    """One home row per reference, whatever the model: each figure as the models share it. Where they
    differ, the one that holds a value (plain serving's overhead is 1x by definition, run or not);
    what one proof covers follows the system the reference runs beside, so it says so."""
    rows = sorted(
        (x for x in H5["rows"] if x["kind"] == "reference" and x["id"].split("--")[0] == gid),
        key=lambda x: MODELS.index(model_of(x)),
    )
    cells = {}
    for c in COLS:
        xs = [x["cells"][c][VIEW] for x in rows]
        if all(x.get("value") == "same as above" for x in xs):
            ref = re.search(r"\(([^)]+)\)", xs[0]["title"])
            cells[c] = {
                "value": None,
                "absent": {"text": "Same as the system"},
                "title": xs[0]["title"].replace("the row it serves", "the system it runs beside"),
                "lines": [ref.group(1)] if ref else [],
            }
        else:
            cells[c] = next((x for x in xs if x.get("value")), xs[0])
    return {
        **rows[0],
        "id": gid,
        "summary": True,
        "cells": {c: {VIEW: x} for c, x in cells.items()},
    }


def build_index():
    first = f"System, {sort_words()['system']['asc']}"
    secs = ""
    for d in MODELS:
        name, sid_ = MODEL_NAME[d], slug(MODEL_NAME[d])
        rows = by_name(r for r in PROVERS if model_of(r) == d)
        body_rows = "".join(
            row_html(
                r,
                G["rows"][r["system"]],
                PAGE[r["system"]],
                figures(r, f"{PAGE[r['system']]}#figures", True),
                True,
            )
            for r in rows
        )
        secs += f"""
  <section class="sec bench" id="{sid_}" aria-labelledby="h-{sid_}">
    <div class="sec-h"><h2 id="h-{sid_}" class="sect">{e(name)}</h2><p class="sec-l">{e(workload_line(rows[0]))}</p></div>
    <div class="tbl" role="table" aria-labelledby="h-{sid_}" aria-describedby="sort-now" data-col="system" data-dir="asc">
      {sort_heads()}
      <div class="rows" role="rowgroup">{body_rows}</div>
    </div>
  </section>"""
    refs = "".join(
        row_html(
            r,
            G["rows"][r["id"]],
            f"{REF_PAGE}#{r['id']}",
            figures(r, f"{REF_PAGE}#{r['id']}", False),
        )
        for r in (ref_summary(gid) for gid in G["orders"]["reference"])
    )
    nb_count = len(G["orders"]["not_benchmarked"])
    body = f"""
{header("home")}
<main id="main">
{masthead()}
<div class="wrap">
  {secs}
  <p class="sr" id="sort-now">{e(first)}</p>
  <section class="sec refs" id="references" aria-labelledby="h-refs">
    <div class="sec-h"><h2 id="h-refs" class="sect">References</h2></div>
    {plain_heads("Reference")}
    {refs}
  </section>
  <section class="sec" id="not-yet" aria-labelledby="h-nb">
    <div class="sec-h"><h2 id="h-nb" class="sect">{e(next(t["label"] for t in OV["tabs"] if t["id"] == "not_benchmarked"))}<sup>{nb_count}</sup></h2></div>
    {nb_grid()}
  </section>
</div>
</main>
{footer()}"""
    return page(
        "Inference proofs",
        HOME_DESC,
        body,
        "home",
        "",
        "home",
    )


# ------------------------------------------------------------------ system page: the pie with its six properties around it


# Clockwise from twelve, slices 1 to 3 face right and 4 to 6 face left; each property sits on its slice's side.
SIDE = {1: "r", 2: "r", 3: "r", 4: "l", 5: "l", 6: "l"}


def rose_item(c):
    st = c["state"]
    generic = st == "grey" and c["reason_short"].startswith("Not stated") and not c.get("source")
    reason = "" if generic else f'<p class="rr">{e(c["reason_short"])}</p>'
    return (
        f'<li class="rp {SIDE[c["n"]]}" id="p-{e(c["prop"])}" data-n="{c["n"]}" title="{e(c["question"])}">'
        f'<p class="rn">{e(c["name"])}</p><p class="rs"><i class="sw {CLS[st]}"></i>{e(c["word"])}</p>{reason}</li>'
    )


def rose(g, hid):
    """The pie, centred, with each property beside its own slice: name, state and our short reason."""
    return (
        f'<div class="rose"><h2 id="{e(hid)}" class="sr">What one proof establishes</h2>'
        f'<div class="rpie" role="img" aria-label="{e(aria(g))}">{pie_svg(g["states"], 184)}</div>'
        f'<ol class="rprops" role="list" aria-labelledby="{e(hid)}">{"".join(rose_item(c) for c in g["cells"])}</ol></div>'
    )


def facts_dl(items):
    return (
        '<dl class="facts">'
        + "".join(f"<div><dt>{e(k)}</dt><dd>{v}</dd></div>" for k, v in items)
        + "</dl>"
    )


def more_table(row, caption):
    more = ""
    for m in row["more"][VIEW]:
        head, kv = parse_title(m["title"])
        lab = " · ".join(f"{k}: {val}" for k, val in kv) if kv else head
        val = fig(m["value"]) if m.get("value") else f'<span class="na">{e(m["absent"])}</span>'
        more += f'<tr><th scope="row">{e(m["label"])}</th><td class="mv">{val}</td><td class="ml">{e(clean(lab))}</td></tr>'
    return (
        f'<table class="mtab"><caption class="sr">{e(caption)}</caption>'
        f'<thead><tr><th scope="col">Figure</th><th scope="col">Value</th><th scope="col">Labels</th></tr></thead><tbody>{more}</tbody></table>'
    )


def control(t):
    c = t.get("control_test")
    if not c or c.get("state") != "filled":
        return ""
    return (
        f'<p class="ctl">{e(clean_prose(c["text"]))} '
        f'<a class="qs" href="{e(c["href"])}">{e(c["link_text"])} ↗</a></p>'
    )


def card_fact(lines, k):
    return next((ln["v"] for ln in lines if ln["k"] == k), "")


def build_system(sid):
    s = site["systems"][sid]
    g = G["rows"][sid]
    row = next(r for r in PROVERS if r["system"] == sid)
    ovr = next(r for r in OV["rows"] if r["kind"] == "prover" and r["system"] == sid)
    lines = ovr["cells"]["system"]["published"]["card"]["lines"]
    repos = "".join(
        f'<a href="{e(r["href"])}">{e(r["repo"])} @{e(r["commit_short"])} ↗</a>'
        for r in s["about"]["repos"]
    )
    status = card_fact(lines, "STATUS").split(': "')[0]  # the state, without the system's own words
    facts = [
        ("kind", e(row["kind_title"])),
        ("model", e(card_fact(lines, "MODEL"))),
        ("pinned", f'<span class="links">{repos}</span>'),
        ("licence", e(card_fact(lines, "LICENCE"))),
        ("status", e(status)),
        ("adapter", f'<a href="{e(s["adapter_readme"])}">systems/{e(sid)}/README.md ↗</a>'),
    ]
    t = s["tamper"]
    plates = "".join(plate(row, c) for c in COLS)
    body = f'''
{header(sid)}
<main id="main" class="sys">
  <section class="mast mast-sys" aria-labelledby="h-name">
    <div class="mast-in"><h1 id="h-name" class="sysname"><span class="lt">{e(s["name"])}</span></h1></div>
  </section>
  <div class="wrap">
    <section class="over" id="properties" aria-label="{e(s["name"])}: properties and facts">
      {rose(g, "h-props")}
      {facts_dl(facts)}
    </section>
    <section class="blk" id="figures" aria-labelledby="h-figs">
      <div class="sec-h"><h2 id="h-figs" class="sect">Figures</h2><p class="sec-l">{e(s["home_line"])}</p></div>
      <p class="lead">{e(s["runs_line"])}</p>
      <div class="plates plates-sys">{plates}</div>
      {more_table(row, f"More numbers for {s['name']}, with scope, grade, checked step and source")}
    </section>
    <section class="blk" id="tamper" aria-labelledby="h-tamper">
      <h2 id="h-tamper" class="sect">Tamper tests</h2>
      <p class="tamper">{e(clean_prose(cut(t["sentence"])))}</p>
      <dl class="tlab"><div><dt>configuration</dt><dd>{e(t["config_id"])}</dd></div></dl>
      {control(t)}
    </section>
  </div>
</main>
{footer()}'''
    return page(
        s["name"],
        system_desc(sid),
        body,
        "system",
        sid,
        sid,
    )


def build_reference():
    """One page for the reference systems: each one's six properties, then its figures on each model."""
    tab = next(t for t in OV["tabs"] if t["id"] == "reference")
    secs = ""
    for gid in G["orders"]["reference"]:
        g = G["rows"][gid]
        rows = sorted(
            (x for x in H5["rows"] if x["kind"] == "reference" and x["id"].split("--")[0] == gid),
            key=lambda x: MODELS.index(model_of(x)),
        )
        r0 = rows[0]
        facts = [
            ("kind", e(r0["kind_title"])),
            ("models", e(" · ".join(MODEL_NAME[model_of(x)] for x in rows))),
        ]
        r = ref_summary(gid)
        figs = (
            f'<div class="reffigs" id="{e(gid)}-figures"><h3 class="sect sm">Figures</h3>'
            f'<div class="plates plates-sys">{"".join(plate(r, c) for c in COLS)}</div></div>'
        )
        secs += f'''
    <section class="refsys" id="{e(gid)}" aria-labelledby="h-{e(gid)}">
      <h2 id="h-{e(gid)}" class="refh">{e(r0["name"])}</h2>
      <div class="over">{rose(g, f"h-{gid}-props")}{facts_dl(facts)}</div>
      {figs}
    </section>'''
    body = f"""
{header("reference")}
<main id="main" class="sys refpage">
  <section class="mast mast-sys" aria-labelledby="h-name">
    <div class="mast-in"><h1 id="h-name" class="sysname refname"><span class="lt">References</span></h1></div>
  </section>
  <div class="wrap">
    <p class="reflead">{e(tab["sentence"])}</p>
    {secs}
  </div>
</main>
{footer()}"""
    return page(
        "References",
        "The references: plain serving and a rerun by a weights holder, their six properties and their figures.",
        body,
        "system reference",
        "reference",
        "home",
    )


# ------------------------------------------------------------------ preview cards
# What a shared link shows: Open Graph and X tags on every page, and one picture per card. build.py
# writes each picture's source, og/<card>.html (CARD_W x CARD_H CSS px, the data's own words and
# pies); og.mjs renders it to og/<card>.png at CARD_SCALE and records both sha256 in og/cards.json.
# The pages name each picture with its hash, so a new picture is a new URL for link caches, and
# test_cards.py fails when a committed picture was not rendered from its committed source.
SITE_URL = "https://www.inferenceproofs.ai"
CARD_W, CARD_H, CARD_SCALE = 1200, 630, 2
OG = HERE / "og"
HOME_DESC = "Six properties of one proof per system (draft criteria), and the benchmark's own figures per model, sortable by column."


def system_desc(sid):
    return f"{site['systems'][sid]['name']}: six properties of one proof (draft criteria) and the benchmark's own figures with their labels."


def icon_links():
    rec = cards_record().get("icon")
    v = f"?v={rec['png'][:12]}" if rec else ""
    return (
        '<link rel="icon" href="/og/icon.svg" type="image/svg+xml">'
        f'<link rel="apple-touch-icon" href="/og/icon.png{v}">'
    )


def cards_record():
    f = OG / "cards.json"
    return json.loads(f.read_text()) if f.exists() else {}


def card_alt(card):
    """The picture in words, from the same data the picture draws."""
    draft = G["legend"]["draft_short"]
    if card == "home":
        return "Inference proofs: " + ", ".join(p["name"] for p in G["properties"]) + "."
    s, g = site["systems"][card], G["rows"][card]
    row = next(r for r in PROVERS if r["system"] == card)
    states = "; ".join(f"{c['name']}: {c['word']}" for c in g["cells"])
    return f"{s['name']} on {model_name(row)} @{s['upstream']['commit_short']}. {states}. {draft}."


def share_meta(title, desc, path, card):
    url = f"{SITE_URL}/{path}"
    rec = cards_record().get(card)
    img = f"{SITE_URL}/og/{card}.png" + (f"?v={rec['png'][:12]}" if rec else "")
    full = title if title == "Inference proofs" else f"{title} · Inference proofs"
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


CARD_CSS = f"""
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{CARD_W}px;height:{CARD_H}px;overflow:hidden;background:{GROUND};color:{PAPER};-webkit-font-smoothing:antialiased}}
.mono{{font-family:"IBM Plex Mono",monospace}}
.disp{{font-family:"Archivo",sans-serif;font-stretch:66%;font-weight:900}}
.sl.yes{{fill:{INK["green"]}}}.sl.partly{{fill:{INK["amber"]}}}.sl.no{{fill:{INK["red"]}}}
.sl.unstated{{fill:{GROUND};stroke:{RULE};stroke-width:1.2}}
.pie-svg{{display:block;overflow:visible}}
.kmini path{{fill:transparent;stroke:{GROUND};stroke-width:1.8;stroke-linejoin:round}}.kmini path.on{{fill:{PAPER};stroke-width:2.2}}
.sw{{display:inline-block;width:.62em;height:.62em;margin-right:.32em;vertical-align:.02em}}
.sw.yes{{background:{INK["green"]}}}.sw.partly{{background:{INK["amber"]}}}.sw.no{{background:{INK["red"]}}}.sw.unstated{{box-shadow:inset 0 0 0 2px {RULE}}}
"""


def card_page(card, body, css):
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{e(card)} card</title>{FONTS}'
        f"<style>{CARD_CSS}{css}</style></head><body>{body}</body></html>\n"
    )


def home_card():
    """Only what does not change with the systems benchmarked, since link previews stay cached:
    violet, the six properties, each beside its place in the pie; black, the site's mark and name."""
    props = "".join(
        f'<li>{key_mini(p["n"], 52)}<span class="disp">{e(p["name"])}</span></li>'
        for p in G["properties"]
    )
    mark = "".join(f'<path d="{wedge(i, 26, 1.6)}"/>' for i in range(6))
    css = f"""
.l{{position:absolute;left:0;top:0;width:690px;height:{CARD_H}px;background:{VIOLET};color:{GROUND};padding:50px 56px}}
.r{{position:absolute;left:690px;top:0;right:0;height:{CARD_H}px;padding:50px 52px;display:flex;flex-direction:column;justify-content:center}}
.k{{font-size:20px;font-weight:600;letter-spacing:.12em;text-transform:uppercase}}
ul{{list-style:none;margin-top:30px;display:grid;gap:14px}}
li{{display:flex;align-items:center;gap:20px}}
li .disp{{font-size:58px;line-height:1;letter-spacing:-.004em}}
.mark{{display:block;width:176px;height:176px;fill:{VIOLET}}}
.name{{font-size:104px;line-height:.86;margin-top:40px;letter-spacing:-.008em}}
.url{{font-size:19px;color:{MUTED};letter-spacing:.04em;margin-top:26px}}
"""
    body = (
        f'<div class="l"><p class="k mono">What one proof establishes</p><ul>{props}</ul></div>'
        f'<div class="r"><svg class="mark" viewBox="-32 -32 64 64" aria-hidden="true">{mark}</svg>'
        f'<p class="disp name">Inference<br>proofs</p><p class="mono url">inferenceproofs.ai</p></div>'
    )
    return card_page("home", body, css)


def system_card(sid):
    """The system page's first screen: its name on the violet band, then its pie with each property beside its slice."""
    s, g = site["systems"][sid], G["rows"][sid]
    row = next(r for r in PROVERS if r["system"] == sid)
    items = "".join(
        f'<li class="p{c["n"]} {SIDE[c["n"]]}"><p class="mono pn">{e(c["name"])}</p>'
        f'<p class="disp pw"><i class="sw {CLS[c["state"]]}"></i>{e(c["word"])}</p></li>'
        for c in g["cells"]
    )
    css = f"""
.band{{position:absolute;left:0;top:0;right:0;height:206px;background:{VIOLET};color:{GROUND};padding:0 56px;overflow:hidden}}
.name{{position:absolute;left:52px;bottom:-9px;font-size:214px;line-height:.8;letter-spacing:-.012em;white-space:nowrap}}
.meta{{position:absolute;right:56px;top:40px;text-align:right;font-size:18px;line-height:1.5}}
.meta b{{display:block;font-weight:600;letter-spacing:.12em;text-transform:uppercase;font-size:17px;margin-bottom:6px}}
.rose{{position:absolute;left:56px;right:56px;top:232px;bottom:52px;display:grid;grid-template-columns:1fr 330px 1fr;
grid-template-areas:"p6 pie p1" "p5 pie p2" "p4 pie p3";column-gap:40px;align-items:center}}
.rose .pie-svg{{grid-area:pie;width:330px;height:330px;justify-self:center;align-self:center}}
ol{{display:contents;list-style:none}}
.p1{{grid-area:p1}}.p2{{grid-area:p2}}.p3{{grid-area:p3}}.p4{{grid-area:p4}}.p5{{grid-area:p5}}.p6{{grid-area:p6}}
.l{{text-align:right}}
.pn{{font-size:17px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:{VIOLET}}}
.pw{{font-size:46px;line-height:1.05;margin-top:4px;font-stretch:80%;font-weight:800}}
.rose .sl.unstated{{stroke-width:3.2}}
.draft{{position:absolute;right:56px;bottom:24px;font-size:16px;color:{MUTED}}}
"""
    body = (
        f'<div class="band"><h1 class="disp name">{e(s["name"])}</h1>'
        f'<p class="mono meta"><b>Inference proofs</b>{e(model_name(row))}<br>@{e(s["upstream"]["commit_short"])}</p></div>'
        f'<div class="rose">{pie_svg(g["states"], 330)}<ol>{items}</ol></div>'
        f'<p class="mono draft">{e(G["legend"]["draft_short"])}</p>'
    )
    return card_page(sid, body, css)


ICON = 180  # the touch icon's side, CSS px at scale 1


def icon_svg():
    """The site's icon: the six-slice pie in ground ink on the violet field."""
    parts = "".join(f'<path d="{wedge(i, 26, 1.6)}"/>' for i in range(6))
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-32 -32 64 64">'
        f'<rect x="-32" y="-32" width="64" height="64" fill="{VIOLET}"/><g fill="{GROUND}">{parts}</g></svg>\n'
    )


def icon_card():
    body = f'<img src="icon.svg" width="{ICON}" height="{ICON}" alt="" style="display:block">'
    page_ = card_page("icon", body, "")
    return page_.replace(
        '<html lang="en">', f'<html lang="en" data-w="{ICON}" data-h="{ICON}" data-scale="1">', 1
    ).replace(
        f"html,body{{width:{CARD_W}px;height:{CARD_H}px;",
        f"html,body{{width:{ICON}px;height:{ICON}px;",
    )


def write_cards():
    OG.mkdir(exist_ok=True)
    (OG / "icon.svg").write_text(icon_svg())
    (OG / "icon.html").write_text(icon_card())
    (OG / "home.html").write_text(home_card())
    for sid in PAGE:
        (OG / f"{sid}.html").write_text(system_card(sid))


def main():
    write_cards()
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
    print(
        "built index.html,", ", ".join(PAGE.values()) + ",", REF_PAGE, "and the card sources in og/"
    )


if __name__ == "__main__":
    main()
