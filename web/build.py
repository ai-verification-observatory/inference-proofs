"""MADE OF WORDS: build the public site from the data in _data/.

Run: python3 -I build.py
Reads _data/site.json and _data/criteria.json, the fonts in fonts/ and words.css / words.js (next to
this file), and the RFC file names in ../rfcs to link rule codes. Types no number: every value,
label, pin and hash comes from the data. The site shows only the benchmark's own runs, on one
model. The pages carry no marking of placeholder data: the README says which numbers are
placeholders.

Writes the pages (index, one per system, reference, criteria, 404), the preview-card sources and
icon in og/, the @font-face block in words.css, vercel.json (headers with the inline script's
hash, redirects, cache rules) and the contrast table in README.md. It computes pie geometry, the
sort keys of the home figures (raw values from the data, units normalised), the contrast of each
ink, and the content hashes that version words.css, words.js and the pictures.
"""

import base64
import hashlib
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
# The footer pins the committed criteria.json by its sha256. The data pipeline read an earlier
# copy (site.json glyph.input); the content checks below tie the committed file to it.
crit_sha = hashlib.sha256((DATA / "criteria.json").read_bytes()).hexdigest()
assert G["order"] == crit["order"]
for rid, states in crit["test_mapping"].items():
    if rid in G["rows"]:
        assert G["rows"][rid]["states"] == states, f"states differ for {rid}"

# ------------------------------------------------------------------ models
# The site compares systems on one model, Llama 4 Maverick (400B parameters): only systems run on
# it are shown (the data puts every benchmarked system there, _data/maverick_only.py). Rows are set
# side by side only within one model, biggest first, should the data ever hold more than one.
TARGET_MODEL = "Llama 4 Maverick"


def model_name(row):
    return (row.get("model") or "").split(" · ")[0]


def wl_model(wid):
    return site["workloads"][wid]["model"]


PROVERS = [r for r in H5["rows"] if r["kind"] == "prover"]


for _r in PROVERS:
    assert model_name(_r) == TARGET_MODEL, f"{_r['id']} is not on {TARGET_MODEL}"


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
# words.css renders these inks; its :root must hold the same values the checks below compute on
_CSS_INKS = dict(re.findall(r"--(\w+):\s*(#[0-9a-f]{6})", (HERE / "words.css").read_text()))
for _k, _v in {
    "ground": GROUND,
    "paper": PAPER,
    "muted": MUTED,
    "rule": RULE,
    "violet": VIOLET,
    "yes": INK["green"],
    "partly": INK["amber"],
    "no": INK["red"],
}.items():
    assert _CSS_INKS.get(_k) == _v, (
        f"words.css --{_k} is {_CSS_INKS.get(_k)}, the build checks {_v}"
    )
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


def sort_key(row_id, col):
    """The raw number behind one home figure, in the column's base unit; None when the data has none."""
    ch = chart(col)
    factor = UNIT[ch["unit"]]
    r = next((x for x in ch["views"][VIEW]["rows"] if x["row"] == row_id), None)
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


# ------------------------------------------------------------------ the glyph: the hex asterisk
# Six triangles make a point-top hexagon, one per property, clockwise from twelve: segment i spans
# the side from vertex 60*i to vertex 60*(i+1), so 1 to 3 sit on the right and 4 to 6 on the left,
# on the pie's own 60-degree axes. The cuts between them widen toward the centre, so the ground
# they leave draws an asterisk, the footnote mark. A Not stated slot keeps only its side, as a line,
# so it reads as empty; where two empty slots meet, a short tick down the cut keeps them countable.
# Drawn in device pixels (viewBox 0 0 size size): every gap and line is sized for the size it is
# shown at, and up to 40 px the centre and the flat sides sit on the pixel grid.
C30 = math.cos(math.radians(30))


def pt(r, deg):
    a = math.radians(deg)
    return r * math.sin(a), -r * math.cos(a)


def _add(p, q, k=1.0):
    return p[0] + k * q[0], p[1] + k * q[1]


def _cross(p1, p2, p3, p4):
    d1, d2 = (p2[0] - p1[0], p2[1] - p1[1]), (p4[0] - p3[0], p4[1] - p3[1])
    den = d1[0] * d2[1] - d1[1] * d2[0]
    t = ((p3[0] - p1[0]) * d2[1] - (p3[1] - p1[1]) * d2[0]) / den
    return p1[0] + t * d1[0], p1[1] + t * d1[1]


def _seg(i, R, wr, wc, inset=0.0):
    """Segment i around the origin, with cut half-widths wr/2 at the rim and wc/2 at the centre,
    every edge moved inward by inset."""
    a0, a1 = 60 * i, 60 * (i + 1)
    v0, v1 = pt(R, a0), pt(R, a1)
    n0, n1 = pt(1, a0 + 90), pt(1, a1 - 90)  # inward normals of the two cuts
    e0 = (_add(v0, n0, wr / 2 + inset), _add((0, 0), n0, wc / 2 + inset))
    e1 = (_add(v1, n1, wr / 2 + inset), _add((0, 0), n1, wc / 2 + inset))
    m = pt(1, a0 + 30)  # outward normal of the side
    s0, s1 = _add(v0, m, -inset), _add(v1, m, -inset)
    return [_cross(*e0, s0, s1), _cross(*e1, s0, s1), _cross(*e0, *e1)]


def _frame(size):
    """Centre and circumradius in px. Up to 40 px the centre sits on a pixel centre and the
    vertical sides on pixel edges, so the cut at twelve and both flat sides are crisp."""
    if size <= 40:
        half = math.floor(size * 0.5 * C30 - 0.5) + 0.5
        return (size / 2 + 0.5, size / 2), half / C30
    return (size / 2, size / 2), size / 2 * 0.985


def _d(poly, c):
    return "M" + "L".join(f"{x + c[0]:.2f} {y + c[1]:.2f}" for x, y in poly) + "Z"


def _empty_line(size, c, R, wr, wc, empty, key):
    """The sides of the empty slots as one line; ticks down the cuts where two empty slots meet."""
    sw = max(1.4, size * 0.024) if key else (1.5 if size < 32 else max(1.25, size * 0.016))
    tick = (0 if size < 24 else 0.22) * R
    rc = R - (sw / 2) / C30  # a corner of the inset outline

    def xy(p):
        return f"{p[0] + c[0]:.2f} {p[1] + c[1]:.2f}"

    E, parts, ticks = set(empty), [], []
    if len(E) == 6:
        parts.append("M" + "L".join(xy(pt(rc, 60 * k)) for k in range(6)) + "Z")
        ticks = list(range(6))
    else:
        for f in (i for i in sorted(E) if (i - 1) % 6 not in E):
            run = [f]
            while (run[-1] + 1) % 6 in E:
                run.append((run[-1] + 1) % 6)
            pts = [_seg(run[0], R, wr, wc, sw / 2)[0]]
            for i in run[1:]:
                pts.append(pt(rc, 60 * i))
                ticks.append(i)
            pts.append(_seg(run[-1], R, wr, wc, sw / 2)[1])
            parts.append("M" + "L".join(xy(p) for p in pts))
    for k in ticks if tick else []:
        v = pt(rc, 60 * k)
        parts.append(f"M{xy(v)}L{xy(_add(v, pt(1, 60 * k), -tick))}")
    cls = "eo eo-s" if size < 24 and not key else "eo"
    return f'<path class="{cls}" stroke-width="{sw:.2f}" d="{"".join(parts)}"/>'


def hex_svg(size, states=None, key=None, mono=False, cells=None, hit=False, cls="pie-svg"):
    """The glyph. states: six state keys, inked by words.css (.sl.yes ...). key: n, the legend key
    (slot n filled, the rest as line). mono: every slot filled in currentColor (the logo).
    cells: each slot carries its property's name and state word (read by words.js). hit: a still
    copy of the six triangles on top takes the pointer, so a lifted slot never slips from under it."""
    c, R = _frame(size)
    wr, wc = (
        (max(1.0, size * 0.016), max(3.0, size * 0.10))
        if mono
        else (max(1.0, size * 0.012), max(1.8, size * 0.05))
    )
    parts, empty = [], []
    for i in range(6):
        d = _d(_seg(i, R, wr, wc), c)
        if mono:
            parts.append(f'<path d="{d}"/>')
        elif key:
            if key == i + 1:
                parts.append(f'<path class="on" d="{d}"/>')
            else:
                empty.append(i)
        else:
            extra = ""
            if cells:
                extra = f' data-name="{e(cells[i]["name"])}" data-word="{e(cells[i]["word"])}"'
            # a Not stated slot keeps an unfilled shape too: the pointer can lift it, and its edge shows
            parts.append(
                f'<path class="sl s{i + 1} {CLS[states[i]]}" data-n="{i + 1}"{extra} d="{d}"/>'
            )
            if states[i] == "grey":
                empty.append(i)
    if empty:
        parts.append(_empty_line(size, c, R, wr, wc, empty, key))
    if hit:
        parts.append(
            '<g class="hit">'
            + "".join(
                f'<path class="h{i + 1}" data-n="{i + 1}" d="{_d(_seg(i, R, 0, 0), c)}"/>'
                for i in range(6)
            )
            + "</g>"
        )
    return (
        f'<svg class="{cls}" viewBox="0 0 {size} {size}" width="{size}" height="{size}" '
        f'aria-hidden="true" focusable="false">{"".join(parts)}</svg>'
    )


def pie_svg(states, size, cells=None, hit=False):
    return hex_svg(size, states=states, cells=cells, hit=hit)


def key_mini(n, size=48):
    """One property's place in the glyph: its own slot filled, the other five as line (words.css inks it)."""
    return hex_svg(size, key=n, cls="kmini")


def mark_svg(size, cls="lm"):
    """The logo mark: the six slots in one colour (currentColor), the asterisk between them."""
    return hex_svg(size, mono=True, cls=cls)


# The direction each slot steps out along when lifted (the bisector of slot i). words.css holds
# them as --dx/--dy on .s1 to .s6, so the pages carry no inline style; the build checks they agree.
LIFT = {i + 1: pt(1, 60 * i + 30) for i in range(6)}
_css = (HERE / "words.css").read_text()
for _n, (_dx, _dy) in LIFT.items():
    _m = re.search(rf"\.s{_n} {{ --dx: (-?[\d.]+); --dy: (-?[\d.]+); }}", _css)
    assert _m, f"words.css lacks the .s{_n} lift"
    assert abs(float(_m[1]) - _dx) < 1e-3, f".s{_n} --dx"
    assert abs(float(_m[2]) - _dy) < 1e-3, f".s{_n} --dy"


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
# values, "in the fixture") are dropped: the site prints figures and their labels as a release would.
MOCKY = re.compile(r"\bmock\b", re.I)
FIXTURE = re.compile(r"\s+in the fixture(?=[.;,]|$)", re.I)

# Data phrases the site words differently, for a reader who has not read the RFCs. Each must still
# occur in the data, so a change there shows up here.
PHRASES = {
    # overhead divides by plain serving's time; the reason names that reference and the consequence
    "The reference could not run this model on one H100": "Plain serving could not run this model on one H100, so there is no baseline to divide by",
    "the reference could not run this model on one H100": "Plain serving could not run this model on one H100, so there is no baseline to divide by",
    # one name per reference: the pages call it a rerun
    "recompute needs them": "a rerun needs them",
    "a checker holding the weights recomputes": "a checker holding the weights reruns it",
    # criteria.json speaks of the workflow and of text the site does not print (quotes, cards)
    "The number itself is a quote in its card; the glyph shows only whether one is stated and proven.": "The state shows only whether a level is stated and proven.",
    "is printed as text beside the segment (no row proves its programs)": "is not shown: no row proves its programs",
    "it is printed as text beside the glyph, not coloured.": "it does not change the state.",
    "no row claims it; it is printed as text.": "no row claims it.",
    "; printed as text.": ".",
    " (hiding from a host operator is another property)": "",
    "or not copied yet": "or we have not recorded it yet",
}
_data_text = json.dumps(site, ensure_ascii=False) + json.dumps(crit, ensure_ascii=False)
for _k in PHRASES:
    assert _k in _data_text, f"PHRASES: {_k!r} no longer in the data"

# RFC rule codes ("(RFC-0015 NM-1)") in data text: a link to the RFC on the page, never the bare code
RFC_RULE = re.compile(r"\s*\((RFC-(\d{4})(?:\s[A-Z]+-\d+)?)\)")
RFC_FILES = {f.name[:4]: f.name for f in (HERE.parent / "rfcs").glob("[0-9][0-9][0-9][0-9]-*.md")}


def sentence_case(text):
    """Each sentence starts with a capital, as data fragments joined with ". " sometimes do not.
    Only prose: a short label ("per proof", "1 token checked") or an id keeps its own case."""
    if len(text.split()) < 4 or not text[:1].islower():
        return re.sub(r"(\. )([a-z])", lambda m: m[1] + m[2].upper(), text)
    text = text[:1].upper() + text[1:]
    return re.sub(r"(\. )([a-z])", lambda m: m[1] + m[2].upper(), text)


def words(text):
    """Data text as the site prints it: placeholder words dropped, phrases reworded."""
    text = FIXTURE.sub("", str(text))
    for k, v in PHRASES.items():
        text = text.replace(k, v)
    return text


def clean(text):
    """A label without its placeholder parts: " · "-separated segments that mention mock are dropped."""
    return " · ".join(s for s in words(text).split(" · ") if not MOCKY.search(s))


def clean_prose(text):
    """A sentence without the clauses (split at "; ") that speak of placeholder records."""
    out = []
    for s in words(text).split(". "):
        keep = "; ".join(c for c in s.rstrip(".").split("; ") if not MOCKY.search(c))
        if keep:
            out.append(keep)
    return sentence_case(". ".join(out) + ".") if out else ""


def no_rule(text):
    """Text without its RFC rule codes (where a link cannot go, as inside another link or a title)."""
    return RFC_RULE.sub("", text)


def with_rule(text):
    """Escaped text whose RFC rule codes become a small link to the RFC."""
    out, last = [], 0
    for m in RFC_RULE.finditer(text):
        out.append(e(text[last : m.start()]))
        f = RFC_FILES.get(m[2])
        assert f, f"no rfcs/{m[2]}-*.md for {m[1]}"
        end = m.end()
        if text[end : end + 1] in (
            ".",
            ";",
            ",",
        ):  # the sentence ends before the link, not after it
            out.append(text[end])
            end += 1
        out.append(
            f' <a class="rule" href="{e(REPO_URL)}/blob/main/rfcs/{f}" title="{e(m[1])}">rule<span class="sr"> {e(m[1])}</span>{EXT}</a>'
        )
        last = end
    out.append(e(text[last:]))
    return "".join(out)


def readable(text):
    """A printed figure label: whole numbers stay with their units, the spread reads in words."""
    # n counts the completed runs only; the failed ones are not counted in the figure
    text = re.sub(
        r"\bn = (\d+) runs?, n_failed = (\d+)", r"\1 completed, \2 failed", text, flags=re.I
    )
    text = re.sub(r"^1 (proof|check)$", r"per \1", text)
    text = text.replace(" · ", "\u00a0· ")  # a separator never starts a line
    # a count word stays with what it counts ("one H100"), a statistic with its number ("sd 0")
    text = re.sub(r"\b(one|two|three|four|five|six|seven|eight|nine|ten) (?=\w)", "\\1\u00a0", text)
    text = re.sub(r"\b(mean|sd) (?=[\d.])", "\\1\u00a0", text)
    return re.sub(r"(\d) (?=[A-Za-zµ%×])", "\\1\u00a0", text)


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
    return row["cells"][col][VIEW]


RAW = re.compile(r" \([\d.]+ [^)]*\)")  # the raw float the data adds after a printed figure


def value_link(row, col, href, who=""):
    """A figure on the home row: a link to the figures on the row's own page; its labels ride in the
    title. The lines under it are plain text (a link cannot hold the rule links the plates carry)."""
    x = cell(row, col)
    inner = (
        fig(x["value"]) if x.get("value") else f'<span class="na">{e(x["absent"]["text"])}</span>'
    )
    shown = [sentence_case(readable(no_rule(clean(ln)))) for ln in fallback_lines(x)]
    if "by definition" in (x.get("value") or ""):
        shown = []  # "1× by definition" says it; the data's sentence would say it twice more
    lines = "".join(f"<span>{e(ln)}</span>" for ln in shown if ln)
    sp = card_line(x, "SPREAD")
    if x.get("value"):
        spread = f" · spread: {sp['v']}" if sp else ""
        title = sentence_case(readable(no_rule(clean(RAW.sub("", x["title"], count=1) + spread))))
    else:  # only why it is missing: a missing number has no grade
        why = card_line(x, "WHY")
        title = sentence_case(no_rule(words(why["v"]))) if why else x["absent"]["text"]
    name = f'<span class="sr">, {e(who)}</span>' if who else ""
    return (
        f'<a class="val" href="{e(href)}" title="{e(title)}">'
        f'<span class="lbl">{e(HEAD[col])}{name}</span><span class="vm">{inner}</span>'
        f'<span class="sub">{lines}</span></a>'
    )


# the label rows of a plate, in this order; "note" is the title's own sentence when no label is stored
PLATE_ORDER = [
    "spread",
    "scope",
    "grade",
    "grade, step",
    "checked",
    "workload",
    "why",
    "warning",
    "source",
    "note",
]
NO_VALUE_DROPS = (
    "grade",
    "grade, step",
    "checked",
)  # a grade or check of a number that does not exist
EXT = '<span aria-hidden="true">\u00a0↗</span>'  # an outside link's arrow: not read aloud, never alone on a line


def path_html(text):
    """A source path that breaks only after a "/" or a " · ", never inside a part, and whose
    separator ends a line rather than starts one."""
    segs = re.split("\u00a0· | · ", text)
    out = []
    for i, sg in enumerate(segs):
        subs = re.split(r"(?<=/)", sg)
        sep = "\u00a0·" if i < len(segs) - 1 else ""
        out.append(
            "<wbr>".join(
                f'<span class="seg">{e(s)}{sep if j == len(subs) - 1 else ""}</span>'
                for j, s in enumerate(subs)
            )
        )
    return " ".join(out)


def keep(text):
    """Escaped text whose hyphenated words (ids, dates, model names) never break at a hyphen; a
    "/" inside one may still break."""
    out, last = [], 0
    for m in re.finditer(r"\S*\w-\w\S*", text):
        out.append(e(text[last : m.start()]))
        out.append(
            "<wbr>".join(f'<span class="nw">{e(s)}</span>' for s in re.split(r"(?<=/)", m[0]))
        )
        last = m.end()
    out.append(e(text[last:]))
    return "".join(out)


def link_or_text(text, href):
    """A source as a link only when it resolves (a root-relative path is text); rule codes as links."""
    text = text.replace(" ↗", "")
    if href and not href.startswith("/"):
        return f'<a href="{e(href)}">{path_html(no_rule(text))}{EXT}</a>'
    return with_rule(text)


def plate(row, col):
    x = cell(row, col)
    head, kv = parse_title(x["title"])
    kv = [[k, v, None] for k, v in kv]
    card = x.get("card") or {}
    if not kv and not card.get("lines"):
        kv = [["note", head, None]]  # no labels stored apart from the title's sentence
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
    if not x.get("value"):
        kv = [p for p in kv if p[0] not in NO_VALUE_DROPS]
    prose = (
        "note",
        "why",
        "warning",
    )  # sentences; the other labels are values and ids, kept as stored
    kv = [
        [k, sentence_case(clean(v)) if k in prose else clean(v), href]
        for k, v, href in kv
        if clean(v)
    ]
    dl = "".join(
        f"<div><dt>{e(k)}</dt><dd>{link_or_text(readable(v), href)}</dd></div>" for k, v, href in kv
    )
    val = fig(x["value"]) if x.get("value") else f'<span class="na">{e(x["absent"]["text"])}</span>'
    return (
        f'<div class="plate" data-col="{col}"><p class="lbl">{e(HEAD[col])}</p>'
        f'<p class="pv">{val}</p><dl>{dl}</dl></div>'
    )


# ------------------------------------------------------------------ chrome
# Pages are files <name>.html served at clean, root-relative addresses (vercel.json cleanUrls;
# serve.py does the same locally), so every link works at any depth, the 404 page included.
PAGE = {sid: f"/{sid}" for sid in G["orders"]["benchmarked"]}  # one page per benchmarked system
REF_PAGE = "/reference"  # one page for the reference systems
CRIT_PAGE = "/criteria"  # the draft criteria behind the six states (G["legend"]["href"] names it)
assert G["legend"]["href"].rstrip("/") == CRIT_PAGE, G["legend"]["href"]


def file_of(path):
    return HERE / f"{path.strip('/') or 'index'}.html"


# ------------------------------------------------------------------ fonts, served from fonts/
# fonts/faces.json lists each woff2 file (named with its own hash, so it can be cached for good)
# with the family, weights, widths and unicode range Google Fonts gives it. The arrows subset comes
# last, so its glyphs win where ranges overlap.
FACES = json.loads((HERE / "fonts" / "faces.json").read_text())["faces"]
for _f in FACES:
    _h = hashlib.sha256((HERE / "fonts" / _f["file"]).read_bytes()).hexdigest()[:10]
    assert _f["file"].endswith(f".{_h}.woff2"), f"fonts/{_f['file']} does not carry its hash"
FACES.sort(key=lambda f: f["subset"] == "arrows")
PRELOAD = ("archivo-latin.", "plex-mono-400-latin.", "plex-mono-500-latin.")


def font_faces(base):
    """The @font-face rules, with file URLs under base ("/fonts/" on the site, "../fonts/" for cards)."""
    out = []
    for f in FACES:
        stretch = f"font-stretch:{f['stretch']};" if f.get("stretch") else ""
        out.append(
            f'@font-face{{font-family:"{f["fam"]}";font-style:normal;font-weight:{f["wt"]};{stretch}'
            f'font-display:block;src:url({base}{f["file"]}) format("woff2");unicode-range:{f["range"]}}}'
        )
    return "\n".join(out)


def preloads():
    return "".join(
        f'<link rel="preload" href="/fonts/{f["file"]}" as="font" type="font/woff2" crossorigin>'
        for f in FACES
        if f["file"].startswith(PRELOAD)
    )


def version(name):
    """A file's URL with the first 12 hex of its sha256, so it can be cached until it changes
    (words.css, words.js, search.json)."""
    return f"/{name}?v={hashlib.sha256((HERE / name).read_bytes()).hexdigest()[:12]}"


# The one inline script: it marks that script runs (html.js) and that motion is welcome (html.anim)
# before the first paint. vercel.json allows exactly this script by its hash.
HEAD_SCRIPT = (
    'document.documentElement.classList.add("js");'
    'try{if(!matchMedia("(prefers-reduced-motion: reduce)").matches)document.documentElement.classList.add("anim")}catch(_){}'
)


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

    # The logo leads to the overview; the nav holds the other pages; systems are reached by search
    # (one link each would not scale) or from the overview.
    nav = a(REF_PAGE, "References", "reference") + a(CRIT_PAGE, "Criteria", "criteria")
    current = " aria-current=page" if here == "home" else ""
    return (
        f'<header class="top"><div class="tl"><p class="brand"><a class="logo" href="/"{current}>{LOGO_MARK}<span>Inference proofs</span></a></p>'
        f'<nav aria-label="Site">{nav}</nav></div>'
        f"{search_box(here)}"
        f'<a class="repo" href="{e(REPO_URL)}">{GITHUB_MARK}GitHub</a>'
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
        '<input id="q" type="search" autocomplete="off" spellcheck="false" placeholder="Search" '
        'role="combobox" aria-expanded="false" aria-controls="q-list" aria-autocomplete="list" '
        'aria-keyshortcuts="/ Control+K Meta+K">'
        '<kbd class="skey" aria-hidden="true">/</kbd></span>'
        f'<ul id="q-list" class="slist" role="listbox" aria-label="Results" hidden data-index="{version("search.json")}"></ul>'
        "</div>"
    )


def footer():
    label = G["label"]
    rfc = re.search(r"\(RFC-(\d{4})\)", label)
    head = label[: rfc.start()].rstrip() if rfc else label
    return (
        f'<footer class="foot"><p><a href="{CRIT_PAGE}">{e(head)}</a>'
        + (
            f' (<a class="nw" href="{e(REPO_URL)}/blob/main/rfcs/{RFC_FILES[rfc[1]]}">RFC-{rfc[1]}</a>)'
            if rfc
            else ""
        )
        + f'\u00a0· <a href="{e(REPO_URL)}/blob/main/web/_data/criteria.json">criteria.json</a> sha256 <code>{crit_sha[:12]}</code></p>'
        f"<p>{e(readable(site['release']['footer_line']).replace('CC BY 4.0', 'CC\u00a0BY\u00a04.0'))}</p></footer>"
    )


def full_title(title):
    return title if title == "Inference proofs" else f"{title} · Inference proofs"


def page(title, desc, body, cls, path, card):
    """One page. path: its address under the site ("" for the home); card: its preview card's name,
    or None for a page that is never shared (the 404)."""
    meta = share_meta(title, desc, path, card) if card else '<meta name="robots" content="noindex">'
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<script>{HEAD_SCRIPT}</script>"
        f'<title>{e(full_title(title))}</title><meta name="description" content="{e(desc)}">'
        f'<meta name="color-scheme" content="dark"><meta name="theme-color" content="{GROUND}">'
        f"{meta}{icon_links()}{preloads()}"
        f'<link rel="stylesheet" href="{version("words.css")}"></head><body class="{cls}">{body}'
        f'<p class="sr" aria-live="polite" id="live"></p><script src="{version("words.js")}" defer></script></body></html>'
    )


def states_key():
    return "".join(
        f'<span class="chip"><i class="sw {CLS[s]}"></i>{e(WORD[s])}</span>'
        for s in G["state_order"]
    )


def keyline():
    return f'<p class="keyline">{states_key()}<a class="draft" href="{CRIT_PAGE}">{e(G["legend"]["draft_short"])}<span aria-hidden="true">\u00a0→</span></a></p>'


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


def aria(g, name=None):
    """The data's spoken summary, without the slice numbers and the count before the names; with
    name, it starts with the name the page shows (the data's own may differ, e.g. "Recompute")."""
    text = words(re.sub(r"(: |; )\d (?=[A-Z])", r"\1", g["aria"]).replace(", six properties:", ":"))
    return f"{name}: {states_said(g)}" if name else text


def states_said(g):
    """The six states in words, as the page's own reasons say them (for the pie's spoken name)."""
    return words(aria(g).split(": ", 1)[1])


def size_words(n):
    """A parameter count from the data as the site prints it: 400000000000 is 400B, 8030261248 8.03B."""
    return f"{n / 1e9:.3g}B"


def pin_link(sid):
    up = site["systems"][sid]["upstream"]
    return f'<a class="pin" href="{e(up["href"])}" title="Pinned upstream commit {e(up["commit"])}">@{e(up["commit_short"])}</a>'


def row_html(row, g, href, right, table=False):
    """One home row: pie, name and its pin (or a reference's kind), then `right`, the four figures.
    The model is the section's own heading, so a system row does not repeat it."""
    rid = row["id"].split("--")[0] if row["kind"] == "prover" else row["id"]
    # the row header is named by the system's name alone, not by the six states and pin it also holds
    cell = f' role="rowheader" aria-labelledby="{e(rid)}-name"' if table else ""
    hid = f' id="{e(rid)}-name"' if table else ""
    if row["kind"] == "prover":
        idle = pin_link(row["system"])
    else:
        # "Plain serving: the baseline ..." reads without the name it repeats
        kt = words(row["kind_title"])
        kt = kt[len(row["name"]) + 2 :] if kt.startswith(row["name"] + ": ") else kt
        idle = f"<span>{e(sentence_case(kt))}</span>"
    attrs = ""
    if table:
        attrs = f' role="row" data-name="{e(row["name"].lower())}" data-k="{e(json.dumps(row_keys(row), separators=(",", ":")))}"'
    return f'''
<div class="row" id="{e(rid)}"{attrs}>
  <div class="r-main">
    <div class="sysc"{cell}>
      <a class="pie" href="{e(href)}" tabindex="-1" aria-hidden="true">{pie_svg(g["states"], 120, cells=g["cells"], hit=True)}<span class="tip"></span></a>
      <div class="who"><h3 class="name"{hid}><a href="{e(href)}">{e(row["name"])}</a></h3><p class="sr">{e(states_said(g))}</p><p class="wl">{idle}</p></div>
    </div>
    {right}
  </div>
</div>'''


def figures(row, href, table):
    cell = ' role="cell"' if table else ""
    return (
        '<div class="vals">'
        + "".join(
            f'<div class="vc"{cell} data-col="{c}">{value_link(row, c, href, row["name"])}</div>'
            for c in COLS
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


NB_SAID = {"no adapter yet"}  # true of every row under "Not benchmarked yet": the heading says it


def nb_models(r):
    """A system's models as its sources name them, whole (never cut mid-phrase), notes trimmed."""
    out = []
    for given in r["models"]:
        m = given.replace(" (model id as given)", "")
        out.append(
            "Model " + m
            if m.startswith("not named")
            else sentence_case(m)
            if m.startswith("no ")
            else m
        )
    return "; ".join(out)


def nb_meta(r):
    """Family and status, then the chips that add something (no repeat of the status or heading)."""
    seen = {r["status_label"].lower(), *NB_SAID}
    if r["status_label"].lower() == "no repository":
        seen.add("no public code")
    chips = [c.lower() for c in r["chips"] if c.lower() not in seen]
    return " · ".join(dict.fromkeys([r["family_label"], r["status_label"], *chips]))


def nb_grid():
    rows = {r["id"]: r for r in OV["not_benchmarked"]["rows"]}
    out = ""
    for rid in sorted(G["orders"]["not_benchmarked"], key=lambda k: rows[k]["name"].lower()):
        r, g = rows[rid], G["rows"][rid]
        out += (
            f'<li class="nb" id="nb-{e(rid)}"><span class="nbpie" role="img" aria-label="{e(aria(g, r["name"]))}">{pie_svg(g["states"], 56)}</span>'
            f'<div><h3 class="nbn">{e(r["name"])}</h3><p class="nbm">{keep(nb_models(r))}</p><p class="nbm">{keep(nb_meta(r))}</p></div></li>'
        )
    return f'<ul class="nbgrid">{out}</ul>'


def workload_line(row):
    """What the row ran, as the data says it, without the model name the section already prints."""
    sys_row = next(r for r in PROVERS if r["workload"] == row["workload"])
    line = site["systems"][sys_row["system"]]["home_line"]
    name = model_name(sys_row)
    return line.split(" · ", 1)[1] if line.startswith(name + " · ") else line


def model_sizes(row):
    """The model's size from its workload record, so a row never reads as a 17B model."""
    m = wl_model(row["workload"])
    total, active = m["parameters_total"], m["parameters_active_per_token"]
    if total == active:
        return f"{size_words(total)} parameters"
    return f"{size_words(total)} parameters, {size_words(active)} active per token"


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
            cells[c] = {
                "value": None,
                "absent": {"text": "Same as the system"},
                # a sentence: its rule link then follows the full stop
                "title": xs[0]["title"]
                .replace("the row it serves", "the system it runs beside")
                .rstrip(".")
                + ".",
                "lines": [],
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
    <div class="sec-h"><h2 id="h-{sid_}" class="sect">{e(name)}</h2><p class="sec-l">{e(readable(model_sizes(rows[0]) + " · " + workload_line(rows[0])))}</p></div>
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
            figures(r, f"{REF_PAGE}#{r['id']}-figures", False),
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
  <p id="sort-now" hidden>{e(first)}</p>
  <section class="sec refs" id="references" aria-labelledby="h-refs">
    <div class="sec-h"><h2 id="h-refs" class="sect">References</h2></div>
    {plain_heads("Reference")}
    {refs}
  </section>
  <section class="sec" id="not-yet" aria-labelledby="h-nb">
    <div class="sec-h"><h2 id="h-nb" class="sect">{e(next(t["label"] for t in OV["tabs"] if t["id"] == "not_benchmarked"))}<sup aria-hidden="true">{nb_count}</sup><span class="sr">, {nb_count} systems</span></h2></div>
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


def rose_item(c, pre):
    """One property beside its slice: its name (a link to what its states mean), its question for
    screen readers, the state, and our short reason (left out when it only repeats Not stated)."""
    st = c["state"]
    generic = st == "grey" and c["reason_short"].startswith("Not stated") and not c.get("source")
    reason = "" if generic else f'<p class="rr">{e(words(c["reason_short"]))}</p>'
    return (
        f'<li class="rp {SIDE[c["n"]]}" id="{pre}p-{e(c["prop"])}" data-n="{c["n"]}">'
        f'<p class="rn"><a href="{CRIT_PAGE}#{e(c["prop"])}">{e(c["name"])}</a><span class="sr">. {e(c["question"])}</span></p>'
        f'<p class="rs"><i class="sw {CLS[st]}"></i>{e(c["word"])}</p>{reason}</li>'
    )


def rose(g, hid, name, level=2, pre=""):
    """The pie, centred, with each property beside its own slice. level: the hidden heading's level
    under the page's own; pre: an id prefix when one page holds several roses."""
    return (
        f'<div class="rose"><h{level} id="{e(hid)}" class="sr">What one proof establishes</h{level}>'
        f'<div class="rpie" role="img" aria-label="{e(aria(g, name))}">{pie_svg(g["states"], 184, hit=True)}</div>'
        f'<ol class="rprops" role="list" aria-labelledby="{e(hid)}">{"".join(rose_item(c, pre) for c in g["cells"])}</ol></div>'
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
        head, kv = parse_title(RAW.sub("", m["title"], count=1))
        if m.get("value"):
            lab = " · ".join(f"{k}: {val}" for k, val in kv) if kv else head
            lab = with_rule(readable(clean(lab)))
            n, u, rest = split_value(m["value"])
            # "GPU cost per 1,000 positions": the row names the basis, so the value drops its own
            basis = re.search(r"per ([\d,]+) (\w+)$", m["label"])
            val = fig(f"{n} {u}" if basis and rest and basis[2] in rest else m["value"])
        else:
            # only why it is missing: the value cell says "No value", and a missing number has no grade
            why = head.split(". ")[0] if head.startswith(m["absent"] + ": ") else head
            why = why[len(m["absent"]) + 2 :] if why.startswith(m["absent"] + ": ") else why
            lab = with_rule(clean_prose(why))
            val = f'<span class="na">{e(m["absent"])}</span>'
        more += f'<tr><th scope="row">{e(readable(m["label"]))}</th><td class="mv">{val}</td><td class="ml">{lab}</td></tr>'
    return (
        f'<table class="mtab"><caption class="sr">{e(caption)}</caption>'
        f'<thead><tr><th scope="col">Figure</th><th scope="col">Value</th><th scope="col">Labels</th></tr></thead><tbody>{more}</tbody></table>'
    )


def control(t):
    """The control test: run (filled) or documented but not run yet; either way the page says so."""
    c = t.get("control_test")
    if not c or c.get("state") not in ("filled", "documented_not_run"):
        return ""
    link = (
        f' <a class="qs" href="{e(c["href"])}">{e(c["link_text"])}{EXT}</a>'
        if c.get("href")
        else ""
    )
    return f'<p class="ctl">{e(clean_prose(c["text"]))}{link}</p>'


def card_fact(lines, k):
    return next((ln["v"] for ln in lines if ln["k"] == k), "")


def status_words(v):
    """A status fact in one form for every system: the state, then its date and source if stored.
    'active (last push 2026-10-19; archived on GitHub: no (GitHub API, retrieved 2026-11-05))' reads
    'active · last push 2026-10-19 (GitHub API, retrieved 2026-11-05)'; the system's own words go."""
    state = v.split(': "')[0].split(" (")[0]
    push = re.search(r"last push (\d{4}-\d{2}-\d{2})", v)
    src = re.search(r"\(([^()]*retrieved [^()]*)\)", v)
    return state + (f" · last push {push[1]}" + (f" ({src[1]})" if src else "") if push else "")


def build_system(sid):
    s = site["systems"][sid]
    g = G["rows"][sid]
    row = next(r for r in PROVERS if r["system"] == sid)
    ovr = next(r for r in OV["rows"] if r["kind"] == "prover" and r["system"] == sid)
    lines = ovr["cells"]["system"]["published"]["card"]["lines"]
    repos = "".join(
        f'<a href="{e(r["href"])}">{path_html(r["repo"])}<span class="nw"> @{e(r["commit_short"])}</span>{EXT}</a>'
        for r in s["about"]["repos"]
    )
    facts = [
        ("kind", e(words(row["kind_title"]))),
        ("model", keep(card_fact(lines, "MODEL"))),
        ("pinned", f'<span class="links">{repos}</span>'),
        ("licence", e(card_fact(lines, "LICENCE"))),
        ("status", keep(status_words(card_fact(lines, "STATUS")))),
        ("adapter", f'<a href="{e(s["adapter_readme"])}">systems/{e(sid)}/README.md{EXT}</a>'),
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
      {rose(g, "h-props", s["name"])}
      {facts_dl(facts)}
    </section>
    <section class="blk" id="figures" aria-labelledby="h-figs">
      <div class="sec-h"><h2 id="h-figs" class="sect">Figures</h2><p class="sec-l">{e(readable(s["home_line"]))}</p></div>
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
    """One page for the reference systems: each one's six properties, then its one set of figures."""
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
            ("kind", e(words(r0["kind_title"]))),
            (
                "model" if len(rows) == 1 else "models",
                e(" · ".join(MODEL_NAME[model_of(x)] for x in rows)),
            ),
        ]
        r = ref_summary(gid)
        figs = (
            f'<div class="reffigs" id="{e(gid)}-figures"><h3 class="sect sm">Figures</h3>'
            f'<div class="plates plates-sys">{"".join(plate(r, c) for c in COLS)}</div></div>'
        )
        secs += f'''
    <section class="refsys" id="{e(gid)}" aria-labelledby="h-{e(gid)}">
      <h2 id="h-{e(gid)}" class="refh">{e(r0["name"])}</h2>
      <div class="over">{rose(g, f"h-{gid}-props", r0["name"], level=3, pre=f"{gid}-")}{facts_dl(facts)}</div>
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


# ------------------------------------------------------------------ search
# search.json, the local index the header's search reads (words.js; nothing leaves the browser).
# Systems and properties only: the pages are in the nav. Each entry: its name, where it leads, its kind and tier (benchmarked first, not benchmarked last:
# the order says what kind of entry it is, never how good a system is), a line of context, its pie
# and the words it is found by. TERMS adds the words people search with for a family of systems.
# Only words true of every system in the family: how a system proves (STARK, SNARK, sumcheck...) comes
# from its own stated technique, never from its family (AGENTS.md rule 9).
TERMS = {
    "proved": "zk proof cryptographic",
    "attested": "tee enclave hardware attestation confidential",
    "re-executed": "rerun re-execution recompute optimistic dispute",
    "fingerprinted": "fingerprint",
}
# words for what the data's code field says about a system's source
CODE_TERMS = {"no_public_code": "closed source"}
TIER = {"system": 0, "property": 1, "reference": 2, "unbenchmarked": 3}
BADGE = {"reference": "Reference", "unbenchmarked": "Not benchmarked", "property": "Property"}


def family(text):
    return text.split(":", 1)[0].strip().lower()


def search_entries():
    out = []

    def add(kind, name, url, meta, pie, terms, fam=""):
        words_ = " ".join([name, meta, terms, TERMS.get(fam, ""), BADGE.get(kind, "")])
        out.append(
            {
                "kind": kind,
                "tier": TIER[kind],
                "badge": BADGE.get(kind, ""),
                "name": name,
                "url": url,
                "meta": meta,
                "pie": pie,
                "terms": " ".join(words_.lower().split()),
            }
        )

    for r in PROVERS:
        s, g = site["systems"][r["system"]], G["rows"][r["system"]]
        add(
            "system",
            s["name"],
            PAGE[r["system"]],
            f"{family(r['kind_title']).capitalize()} · {model_name(r)}",
            pie_svg(g["states"], 28),
            f"{r['kind_title']} {s['upstream']['repo']}",
            family(r["kind_title"]),
        )
    for gid in G["orders"]["reference"]:
        r = ref_summary(gid)
        add(
            "reference",
            r["name"],
            f"{REF_PAGE}#{gid}",
            sentence_case(words(r["kind_title"])[len(r["name"]) + 2 :])
            if r["kind_title"].startswith(r["name"] + ": ")
            else words(r["kind_title"]),
            pie_svg(G["rows"][gid]["states"], 28),
            "reference baseline",
        )
    nb = {r["id"]: r for r in OV["not_benchmarked"]["rows"]}
    for rid in G["orders"]["not_benchmarked"]:
        r = nb[rid]
        add(
            "unbenchmarked",
            r["name"],
            f"/#nb-{rid}",
            f"{r['family_label']} · {nb_models(r)}",
            pie_svg(G["rows"][rid]["states"], 28),
            # status, models, source and stated technique; not the "by" field, which names people
            " ".join(
                [
                    nb_meta(r),
                    *r["models"],
                    r.get("code_label") or "",
                    CODE_TERMS.get(r.get("code"), ""),
                    r["technique_words"] if r.get("technique") not in (None, "not_stated") else "",
                ]
            ),
            r["family_label"].lower(),
        )
    for p in G["properties"]:
        add(
            "property", p["name"], f"{CRIT_PAGE}#{p['id']}", p["question"], key_mini(p["n"], 28), ""
        )
    return out


# ------------------------------------------------------------------ the criteria and the 404


def build_criteria():
    """What each state means for each property, from criteria.json: the draft the pies are coloured by."""
    props = {p["id"]: p for p in crit["properties"]}
    secs = ""
    for gp in G["properties"]:
        p = props[gp["id"]]
        states = "".join(
            f'<div><dt><i class="sw {CLS[s]}"></i>{e(WORD[s])}</dt><dd>{e(words(p[s]))}</dd></div>'
            for s in G["state_order"]
        )
        note = f'<p class="cnote">{e(words(p["not_here"]))}</p>' if p.get("not_here") else ""
        secs += (
            f'<section class="crit" id="{e(p["id"])}" aria-labelledby="h-{e(p["id"])}">'
            f'<div class="ch">{key_mini(gp["n"])}<h2 id="h-{e(p["id"])}" class="sect">{e(p["name"])}</h2>'
            f'<p class="cq">{e(p["question"])}</p></div><dl class="cs">{states}</dl>{note}</section>'
        )
    body = f"""
{header("criteria")}
<main id="main" class="sys critpage">
  <section class="mast mast-sys" aria-labelledby="h-name">
    <div class="mast-in"><h1 id="h-name" class="sysname"><span class="lt">Criteria</span></h1></div>
  </section>
  <div class="wrap">
    {secs}
  </div>
</main>
{footer()}"""
    return page(
        "Criteria",
        "What Yes, Partly, No and Not stated mean for each of the six properties of one proof (draft criteria).",
        body,
        "system criteria",
        CRIT_PAGE.strip("/"),
        "home",
    )


def build_404():
    body = f"""
{header(None)}
<main id="main" class="sys">
  <section class="mast mast-sys" aria-labelledby="h-name">
    <div class="mast-in"><h1 id="h-name" class="sysname"><span class="lt">Not found</span></h1></div>
  </section>
</main>
{footer()}"""
    return page("Not found", "No page at this address.", body, "system notfound", "404", None)


# ------------------------------------------------------------------ vercel.json, from the build
# Headers, redirects and cache rules depend on the build's own output (the inline script's hash,
# the first system page), so the build writes the whole file. Canonical JSON (iproofs fmt).
def vercel_json():
    script = hashlib.sha256(HEAD_SCRIPT.encode()).digest()

    csp = "; ".join(
        [
            "default-src 'self'",
            f"script-src 'self' 'sha256-{base64.b64encode(script).decode()}'",
            "style-src 'self'",
            "img-src 'self'",
            "font-src 'self'",
            "connect-src 'self'",
            "object-src 'none'",
            "base-uri 'none'",
            "form-action 'none'",
            "frame-ancestors 'none'",
        ]
    )
    forever = [{"key": "Cache-Control", "value": "public, max-age=31536000, immutable"}]
    first = PAGE[G["orders"]["benchmarked"][0]]
    return {
        "$schema": "https://openapi.vercel.sh/vercel.json",
        "buildCommand": "rm -rf public && mkdir -p public/og public/fonts && cp *.html words.css words.js search.json public/ && cp og/*.png og/*.svg public/og/ && cp fonts/*.woff2 public/fonts/",
        "cleanUrls": True,
        "trailingSlash": False,
        "framework": None,
        "ignoreCommand": "git diff --quiet HEAD^ HEAD -- .",
        "outputDirectory": "public",
        "redirects": [
            {"source": "/system", "destination": first, "permanent": True},
            {"source": "/system.html", "destination": first, "permanent": True},
        ],
        "headers": [
            {
                "source": "/(.*)",
                "headers": [
                    # noindex while the results are placeholders (README)
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


CARD_CSS = f"""
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{CARD_W}px;height:{CARD_H}px;overflow:hidden;background:{GROUND};color:{PAPER};-webkit-font-smoothing:antialiased}}
.mono{{font-family:"IBM Plex Mono",monospace}}
.disp{{font-family:"Archivo",sans-serif;font-stretch:66%;font-weight:900}}
.sl.yes{{fill:{INK["green"]}}}.sl.partly{{fill:{INK["amber"]}}}.sl.no{{fill:{INK["red"]}}}
.sl.unstated{{fill:none}}.eo{{fill:none;stroke:{RULE};stroke-linejoin:miter}}.eo-s{{stroke:#8a847a}}
.pie-svg{{display:block;overflow:visible}}
.kmini .on{{fill:{GROUND}}}.kmini .eo{{stroke:{GROUND}}}
.sw{{display:inline-block;width:.62em;height:.62em;margin-right:.32em;vertical-align:.02em}}
.sw.yes{{background:{INK["green"]}}}.sw.partly{{background:{INK["amber"]}}}.sw.no{{background:{INK["red"]}}}.sw.unstated{{box-shadow:inset 0 0 0 2px {RULE}}}
"""


def card_page(card, body, css):
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{e(card)} card</title>'
        f"<style>{font_faces('../fonts/')}\n{CARD_CSS}{css}</style></head><body>{body}</body></html>\n"
    )


def home_card():
    """Only what does not change with the systems benchmarked, since link previews stay cached:
    violet, the six properties, each beside its place in the glyph; black, the site's mark and name."""
    props = "".join(
        f'<li>{key_mini(p["n"], 52)}<span class="disp">{e(p["name"])}</span></li>'
        for p in G["properties"]
    )
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
        f'<div class="r">{mark_svg(176, cls="mark")}'
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
    """The site's icon: the hex asterisk in ground ink on the violet field."""
    parts = "".join(re.findall(r'<path d="[^"]+"/>', mark_svg(64)))
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-10 -10 84 84">'
        f'<rect x="-10" y="-10" width="84" height="84" fill="{VIOLET}"/><g fill="{GROUND}">{parts}</g></svg>\n'
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


def write_font_faces():
    """The @font-face block in words.css, between its markers, from fonts/faces.json."""
    css = (HERE / "words.css").read_text()
    block = "/* fonts: written by build.py */\n" + font_faces("/fonts/") + "\n/* /fonts */"
    new = re.sub(
        r"/\* fonts: written by build.py \*/.*?/\* /fonts \*/", lambda _: block, css, flags=re.S
    )
    assert new != css or block in css, "words.css lacks the fonts markers"
    (HERE / "words.css").write_text(new)


def main():
    write_font_faces()
    write_cards()
    # before the pages: they link it by its hash
    (HERE / "search.json").write_text(
        json.dumps({"entries": search_entries()}, indent=2, sort_keys=True, ensure_ascii=False)
        + "\n"
    )
    file_of("/").write_text(build_index())
    for sid, path in PAGE.items():
        file_of(path).write_text(build_system(sid))
    file_of(REF_PAGE).write_text(build_reference())
    file_of(CRIT_PAGE).write_text(build_criteria())
    (HERE / "404.html").write_text(build_404())
    # the build's pages are the only pages: a page it no longer writes would still be deployed
    pages = {
        file_of("/"),
        *(file_of(q) for q in PAGE.values()),
        file_of(REF_PAGE),
        file_of(CRIT_PAGE),
    }
    stale = set(HERE.glob("*.html")) - pages - {HERE / "404.html"}
    assert not stale, f"pages the build no longer writes: {sorted(q.name for q in stale)}"
    assert {q.stem for q in OG.glob("*.html")} == {"icon", "home", *PAGE}, (
        "stale card sources in og/"
    )
    (HERE / "vercel.json").write_text(
        json.dumps(vercel_json(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
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
    print("built the pages, 404.html, vercel.json and the card sources in og/")


if __name__ == "__main__":
    main()
