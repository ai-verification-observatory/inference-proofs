"""MADE OF WORDS: the renderer of the public site (RFC-0009 §Site).

`iproofs site build` computes every value the pages print into a view
(`iproofs.site.view.site_view`, from the newest frozen release, the claim cards, the criteria
file and `_data/facts.json`) and calls `render(view, out, write_json=..., write_text=...)`. This
module opens no data file and types no number: every value, label, pin and hash comes from the
view. It holds the drawing and the fixed words the pages print for stored values (scope, grade,
tier, null reasons, units, states, families), as RFC-0009 S2 allows. Standard library only.

`render` writes into `out`: the pages (index, one per system, reference, criteria, 404),
search.json, the preview-card sources and icon in og/, the @font-face block in words.css,
vercel.json (headers with the inline script's hash, redirects, cache rules) and the contrast
table in README.md when `out` holds one. The static assets (words.css, words.js, fonts/,
og/*.png, og/cards.json) are in `out` before it runs. It computes pie geometry, the contrast of
each ink and the content hashes that version words.css, words.js and the pictures.
"""

import base64
import hashlib
import html
import json
import math
import pathlib
import re

# Set by render(): the output folder, the view and what is read from it. Nothing is read when
# the module is imported.
HERE = OG = pathlib.Path()
V: dict = {}
CRIT: dict = {}
PROPS: list = []
CONFIGS: list = []
PROVERS: list = []
PAGE: dict = {}
MODELS: list = []
MODEL_NAME: dict = {}
INK: dict = {}
FACES: list = []
RFC_FILES: dict = {}
REPO_URL = LINK_REF = crit_sha = ""
ladder: list = []
pairs: list = []
WRITE_TEXT = WRITE_JSON = None


def e(s):
    return html.escape(str(s), quote=True)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# ------------------------------------------------------------------ words
# The fixed words a stored value prints as (RFC-0009 S2: the generator may word a stored value;
# it never changes it). Keyed by the stored ids, so an id with no words stops the build.
STATE_WORD = {"yes": "Yes", "partly": "Partly", "no": "No", "not_stated": "Not stated",
              None: "No state shown"}  # fmt: skip
STATE_CLS = {"yes": "yes", "partly": "partly", "no": "no", "not_stated": "unstated", None: "none"}
STATE_ORDER = ("yes", "partly", "no", "not_stated")  # the legend's order, display only
FAMILY_WORD = {"proved": "Proved", "attested": "Attested", "re_executed": "Re-executed",
               "fingerprinted": "Fingerprinted", "unchecked": "Unchecked"}  # fmt: skip
STATUS_WORD = {"active": "active", "unmaintained": "unmaintained", "archived": "archived",
               "no_repository": "no repository"}  # fmt: skip
SCOPE_WORD = {
    None: "none (not a timed number)",
    "setup": "setting up",
    "commit": "preparing the model",
    "prove.steady": "proving, steady state",
    "prove.session": "proving session",
    "whole_wall": "the whole run, wall clock",
    "verify": "checking ({cpus} CPU threads)",
    "verify.single_thread": "checking (one CPU thread)",
    "primitive": "one primitive",
}
GRADE_WORD = {
    "measured": "recorded by our harness",
    "derived": "calculated from recorded numbers",
    "projected": "projected, not measured",
    "external": "as the system publishes it",
    "asserted": "set in the reference file",
}
TIER_WORD = {
    "reported": "one runner, not yet checked",
    "peer-reviewed": "reviewed, not yet rerun",
    "reproduced": "rerun by an unaffiliated runner",
}
NULL_WORD = {
    "not_externally_observable": "The harness cannot observe this number from outside the system.",
    "fewer_than_two_proofs": "Fewer than two proofs in a run, so there is no per-proof figure.",
    "not_applicable": "Does not apply to this setup.",
    "step_failed": "The step that records this number failed in these runs.",
    "not_measurable_on_profile": "Not measurable on {gpu} (RFC-0015 NM-1).",
    "missing_input": "A number this one is calculated from is missing.",
}
# A missing overhead names its baseline: overhead divides by plain serving's time (D-OVERHEAD-S).
NM1_OVERHEAD = "Plain serving could not run this model on {gpu}, so there is no baseline to divide by (RFC-0015 NM-1)."
NOT_RECORDED = "Not recorded in these runs."
FAIL_KIND = {
    "config": "a configuration error",
    "environment": "a fault on the runner's machine",
    "integrity": "an integrity check failed",
    "fetch": "a download failed",
    "adapter": "the adapter failed",
    "timeout": "the run ran out of time",
    "resource": "the machine ran out of resources",
    "policy": "a policy check stopped it",
    "internal": "an error in our harness",
}
FAIL_STEP = {
    "setup": "while setting up",
    "commit": "while preparing the model",
    "prove": "while proving",
    "verify": "while checking",
    "upload": "while uploading its proofs",
    "fetch": "while fetching",
}
# RFC-0008 outcomes, each count as stored; zero counts are left out, and no total is printed
OUTCOME_WORDS = (
    ("rejected", "the checker rejected {n}"),
    ("invalid_call", "it refused {n} as malformed input"),
    ("accepted", "it accepted {n}"),
    ("no_verdict", "{n} ended with no verdict"),
    ("prover_failed", "in {n} the prover would not build the tampered proof"),
    ("error", "{n} ended in an error"),
    ("void", "{n} were void"),
    ("not_applicable", "{n} do not apply to this setup"),
)
OUTCOME_VERB = {"accepted": "accepted", "rejected": "rejected", "invalid_call": "refused",
                "no_verdict": "gave no verdict on", "error": "failed on"}  # fmt: skip
COUNT_WORD = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
              8: "eight", 9: "nine", 10: "ten"}  # fmt: skip
# RFC-0009 S6: above tables of different native workloads side by side (two workloads on one model)
NATIVE_HEADER = "Native workloads differ: rows are not a head-to-head comparison"
REF_LEAD = "The same model, task and GPU without a proof: plain serving checks nothing, a rerun needs the weights; they are baselines, not systems."


def count_word(n):
    return COUNT_WORD.get(n, f"{n:,}")


# ------------------------------------------------------------------ inks
GROUND, PAPER, MUTED, RULE = "#0b0b0c", "#f1efe9", "#9b978e", "#6f6a62"
VIOLET = "#c45cff"
UNSTATED = "#67635c"  # Not stated: a filled slot in a grey of its own, never a fourth hue


def lum(h):
    h = h.lstrip("#")
    c = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(a, b):
    x, y = sorted([lum(a), lum(b)], reverse=True)
    return (x + 0.05) / (y + 0.05)


def check_inks():
    """words.css renders the inks: the states' inks are read from its :root, the chrome's must
    equal the values the checks below compute on, and every pair keeps its contrast."""
    global INK, ladder, pairs
    css = dict(re.findall(r"--(\w+):\s*(#[0-9a-f]{6})", (HERE / "words.css").read_text()))
    INK = {s: css[s] for s in ("yes", "partly", "no")}
    for k, v in {"ground": GROUND, "paper": PAPER, "muted": MUTED, "rule": RULE,
                 "violet": VIOLET, "unstated": UNSTATED}.items():  # fmt: skip
        assert css.get(k) == v, f"words.css --{k} is {css.get(k)}, the build checks {v}"
    ladder, prev = [], UNSTATED
    ladder.append(("Not stated", f"`{UNSTATED}` (a grey, no hue)", f"{lum(UNSTATED):.3f}",
                   f"{ratio(UNSTATED, GROUND):.2f}:1", ""))  # fmt: skip
    for st in ("no", "partly", "yes"):
        step = ratio(INK[st], prev)
        # grey to red is told apart by hue, not lightness; the colour steps are told apart by both
        assert step >= 1.7 or prev == UNSTATED, st
        ladder.append((STATE_WORD[st], f"`{INK[st]}`", f"{lum(INK[st]):.3f}",
                       f"{ratio(INK[st], GROUND):.2f}:1", f"{step:.2f}:1"))  # fmt: skip
        prev = INK[st]
    pairs = [
        ("paper text on ground", PAPER, GROUND),
        ("muted text on ground", MUTED, GROUND),
        ("black text on violet", GROUND, VIOLET),
        ("violet text on ground", VIOLET, GROUND),
    ]
    pairs += [(f"ground text on {STATE_WORD[s]}", GROUND, INK[s]) for s in ("yes", "partly", "no")]
    for name, a, b in pairs:
        assert ratio(a, b) >= 4.5, name
    assert ratio(UNSTATED, GROUND) >= 3, (
        "a Not stated slot must stand off the ground (3:1 for shapes)"
    )


# ------------------------------------------------------------------ numbers (display only)
# A stored value prints at four significant digits in a unit chosen for reading (S4); the sort key
# and the record keep the stored value in its base unit.
def sig4(v):
    if v == 0:
        return "0"
    return f"{v:,.{max(0, 3 - math.floor(math.log10(abs(v))))}f}"


def amount(v, unit):
    """(number, unit words) for a stored value in its stored unit."""
    if unit == "B":
        f, u = next(((f, u) for f, u in ((1e12, "TB"), (1e9, "GB"), (1e6, "MB"), (1e3, "kB"))
                     if abs(v) >= f), (1, "B"))  # fmt: skip
        return sig4(v / f), u
    if unit == "s":
        if v and abs(v) < 1:
            return sig4(v * 1e3), "ms"
        if abs(v) < 1e3:
            return sig4(v), "s"
        return (sig4(v / 60), "min") if abs(v) < 6e4 else (sig4(v / 3600), "h")
    words = {"token": "positions", "token/s": "positions/s", "USD/1k_token": "USD / 1k positions"}
    return sig4(v), words.get(unit, unit)


def shown(v, unit):
    n, u = amount(v, unit)
    return f"{n}×" if unit == "ratio" else f"{n} {u}"


def spread_parts(f):
    """The sample size and the range, the two parts the overview shows (S3)."""
    st = f.get("stats")
    if not st:
        return []
    lo, hi = (shown(st[k], f["unit"]) for k in ("min", "max"))
    if f["unit"] == "token":  # the figure above names the unit
        lo, hi = (x.rsplit(" ", 1)[0] for x in (lo, hi))
    return [f"{st['n']} completed, {st['n_failed']} failed", f"{lo} to {hi}"]


def spread_line(f):
    """The whole spread as a plate prints it: sample size, range, mean and sd (S3)."""
    st = f["stats"]
    parts = [*spread_parts(f), f"mean {shown(st['mean'], f['unit'])}"]
    if st.get("stdev") is not None:
        parts.append("sd 0" if st["stdev"] == 0 else f"sd {shown(st['stdev'], f['unit'])}")
    return " · ".join(parts)


def gpu_words(cfg):
    g = cfg["gpu"]
    return f"{count_word(g['count'])} {g['short'] or g['model']}"


def scope_words(f, cfg):
    return SCOPE_WORD[f["scope"]].format(cpus=cfg["verifier"]["logical_cpus"])


def why_words(f, cfg):
    """Why a figure has no value, from its stored null reason (or its absence from the runs)."""
    if not f["recorded"]:
        return NOT_RECORDED
    if f["null_reason"] == "not_measurable_on_profile" and f["metric"].startswith("overhead_"):
        return NM1_OVERHEAD.format(gpu=gpu_words(cfg))
    return NULL_WORD[f["null_reason"]].format(gpu=gpu_words(cfg))


def labels(f, cfg):
    return [("scope", scope_words(f, cfg)), ("grade", GRADE_WORD[f["grade"]]),
            ("checked", TIER_WORD[f["tier"]])]  # fmt: skip


# ------------------------------------------------------------------ the glyph: the hex asterisk
# Six triangles make a point-top hexagon, one per property, clockwise from twelve: segment i spans
# the side from vertex 60*i to vertex 60*(i+1), so 1 to 3 sit on the right and 4 to 6 on the left,
# on the pie's own 60-degree axes. The cuts between them widen toward the centre, so the ground
# they leave draws an asterisk, the footnote mark. Every slot is always filled: Not stated in a grey
# of its own (--unstated), so the hexagon is always whole.
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


# A property's name set in its own triangle (phone system pages, words.css shows them):
# condensed capitals in ground ink, in user units of the glyph's viewBox. A slanted side carries its
# name along it, the longer line nearer the side; an upright side, level, against it.
NAME_PX, NAME_CAP, NAME_GAP, NAME_INSET = 10.5, 7.45, 10.29, 4.7


def _name_lines(name, outer_first):
    """Two lines at most. Slanted: the line nearer the side (the wider part of the triangle) is the
    longer, and as short as that allows. Upright: the most even split."""
    w = name.upper().split()
    if len(w) == 1:
        return w
    cuts = [(" ".join(w[:k]), " ".join(w[k:])) for k in range(1, len(w))]
    if outer_first is None:
        return list(min(cuts, key=lambda ab: max(len(ab[0]), len(ab[1]))))
    fits = [
        ab for ab in cuts if len(ab[0 if outer_first else 1]) >= len(ab[1 if outer_first else 0])
    ]
    return list(min(fits or cuts, key=lambda ab: len(ab[0 if outer_first else 1])))


def _names_svg(names, c, R):
    out = []
    for i, name in enumerate(names):
        mid = 60 * i + 30
        if i in (
            1,
            4,
        ):  # the upright sides: level, against the side, centred on the centre's height
            lines = _name_lines(name, None)
            x = c[0] + (1 if i == 1 else -1) * (R * C30 - NAME_INSET)
            y0 = c[1] - (NAME_CAP + NAME_GAP * (len(lines) - 1)) / 2 + NAME_CAP
            anchor = "end" if i == 1 else "start"
            body = "".join(
                f'<text x="{x:.2f}" y="{y0 + k * NAME_GAP:.2f}" text-anchor="{anchor}">{e(t)}</text>'
                for k, t in enumerate(lines)
            )
        else:  # slanted: along the side, inward from its midpoint
            top = i in (0, 5)
            lines = _name_lines(name, top)
            mx, my = pt(R * C30, mid)
            rot = mid if top else mid - 180
            rot = rot - 360 if rot > 180 else rot
            if top:
                ys = [NAME_INSET + NAME_CAP + k * NAME_GAP for k in range(len(lines))]
            else:
                ys = [-NAME_INSET - (len(lines) - 1 - k) * NAME_GAP for k in range(len(lines))]
            body = (
                f'<g transform="translate({mx + c[0]:.2f} {my + c[1]:.2f}) rotate({rot:g})">'
                + "".join(
                    f'<text x="0" y="{y:.2f}" text-anchor="middle">{e(t)}</text>'
                    for t, y in zip(lines, ys, strict=True)
                )
                + "</g>"
            )
        out.append(f'<g class="t s{i + 1}">{body}</g>')
    return f'<g class="tx">{"".join(out)}</g>'


def hex_svg(
    size, states=None, key=None, mono=False, cells=None, hit=False, cls="pie-svg", names=None
):
    """The glyph: six filled triangles, always. states: six RFC-0016 state ids, inked by words.css
    (.sl.yes ... .sl.unstated, a grey of its own; None, a row under a pending disclosure, draws
    none of the four). key: n, the legend key (slot n in full ink, the other five faint). mono:
    every slot in currentColor (the logo). cells: each slot carries its property's name and state
    word (read by words.js). hit: a still copy of the six triangles on top takes the pointer, so a
    lifted slot never slips from under it. names: each slot's property name set in it (shown on
    phone system pages only)."""
    c, R = _frame(size)
    wr, wc = (
        (max(1.0, size * 0.016), max(3.0, size * 0.10))
        if mono
        else (max(1.0, size * 0.012), max(1.8, size * 0.05))
    )
    parts = []
    for i in range(6):
        d = _d(_seg(i, R, wr, wc), c)
        if mono:
            parts.append(f'<path d="{d}"/>')
        elif key:
            parts.append(f'<path class="{"on" if key == i + 1 else "off"}" d="{d}"/>')
        else:
            extra = ""
            if cells:
                extra = f' data-name="{e(cells[i]["name"])}" data-word="{e(cells[i]["word"])}"'
            parts.append(
                f'<path class="sl s{i + 1} {STATE_CLS[states[i]]}" data-n="{i + 1}"{extra} d="{d}"/>'
            )
    if names:
        parts.append(_names_svg(names, c, R))
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
    """One property's place in the glyph: its own slot in full ink, the other five faint (words.css inks it)."""
    return hex_svg(size, key=n, cls="kmini")


def mark_svg(size, cls="lm"):
    """The logo mark: the six slots in one colour (currentColor), the asterisk between them."""
    return hex_svg(size, mono=True, cls=cls)


# The direction each slot steps out along when lifted (the bisector of slot i). words.css holds
# them as --dx/--dy on .s1 to .s6, so the pages carry no inline style; the build checks they agree.
LIFT = {i + 1: pt(1, 60 * i + 30) for i in range(6)}


def check_lifts():
    css = (HERE / "words.css").read_text()
    for n, (dx, dy) in LIFT.items():
        m = re.search(rf"\.s{n} {{ --dx: (-?[\d.]+); --dy: (-?[\d.]+); }}", css)
        assert m, f"words.css lacks the .s{n} lift"
        assert abs(float(m[1]) - dx) < 1e-3, f".s{n} --dx"
        assert abs(float(m[2]) - dy) < 1e-3, f".s{n} --dy"


# ------------------------------------------------------------------ the criteria's rows as glyphs


def glyph(rid):
    """One criteria row as the pages draw it: six states in slot order, each with its property,
    word, reason, quotes and the system's own statement outside the pin (never part of a state)."""
    row = CRIT["rows"][rid]
    cells = []
    for i, p in enumerate(PROPS):
        c = row["cells"][p["id"]]
        outside = (c.get("outside_pin") or {}).get("state")
        cells.append({"n": i + 1, "prop": p["id"], "name": p["name"], "question": p["question"],
                      "state": c["state"], "word": STATE_WORD[c["state"]],
                      "reason": c.get("reason") or "", "quotes": c["quotes"],
                      "outside": outside})  # fmt: skip
    return {"states": [c["state"] for c in cells], "cells": cells}


def states_said(g, outside=False):
    """The six states in words (the pie's spoken name). outside: also the system's own statement
    outside the pin, which is never part of the state (RFC-0016 SRC-3); system pages only."""
    parts = []
    for c in g["cells"]:
        w = c["word"]
        if outside and c["outside"] is not None:
            w += f" (its own note outside the pin says {STATE_WORD[c['outside']]})"
        parts.append(f"{c['name']}: {w}")
    return words("; ".join(parts) + ".")


def aria(g, name, outside=False):
    return f"{name}: {states_said(g, outside)}"


# ------------------------------------------------------------------ words and labels


def split_value(v):
    """Number, its unit (the next word), and any words after it."""
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
# the stored statistic behind each overview column (iproofs.site.view.FIGURES)
METRIC = {
    "covers": "tokens_covered_per_proof",
    "proof_size": "proof_bytes",
    "check_time": "verify_seconds",
    "overhead": "overhead_vs_serving_prove.session",
}
# how each order reads aloud
SORT_WORDS = {
    "system": {"asc": "A to Z", "desc": "Z to A"},
    "covers": {"asc": "fewer positions first", "desc": "more positions first"},
    "proof_size": {"asc": "small to large", "desc": "large to small"},
    "check_time": {"asc": "short to long", "desc": "long to short"},
    "overhead": {
        "asc": "closer to plain serving first",
        "desc": "further from plain serving first",
    },
}
# More numbers on a system page, in this order: the stored statistic and its row label
MORE = [
    ("rate_prove.session", "Proving rate"),
    ("cost_per_1k_tokens_prove.session", "GPU cost per 1,000 positions"),
    ("commit_seconds", "Commit once"),
    ("verify_host_memory_peak_anon", "Checker memory"),
    ("prove_gpu_memory_peak", "GPU memory"),
]
# A reference row makes no proof (RFC-0015 REF-2): its cells say so, in these words
REF_CELLS = {
    "covers": (
        "Same as the system",
        "Same token count as the system it runs beside (RFC-0015 REF-3).",
    ),
    "proof_size": ("No proof", "This row makes no proof (RFC-0015 REF-2)."),
    "check_time": ("Does not apply", "This row makes no proof (RFC-0015 REF-2)."),
}
REF_OVERHEAD = {
    "serve": (
        "Baseline",
        "Plain serving is the baseline of the overhead ratio, whether or not it has run.",
    ),
    "recompute": ("Does not apply", "A rerun is not the baseline."),
}

# Criteria phrases the site words differently, for a reader who has not read the RFCs. Each must
# still occur in the criteria or facts file, so a change there shows up here.
PHRASES = {
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

# RFC rule codes ("(RFC-0015 NM-1)") in text: a link to the RFC on the page, never the bare code
RFC_RULE = re.compile(r"\s*\((RFC-(\d{4})(?:\s[A-Z]+-\d+)?)\)")


def sentence_case(text):
    """Each sentence starts with a capital, as fragments joined with ". " sometimes do not.
    Only prose: a short label ("per proof", "1 token checked") or an id keeps its own case."""
    if len(text.split()) < 4 or not text[:1].islower():
        return re.sub(r"(\. )([a-z])", lambda m: m[1] + m[2].upper(), text)
    text = text[:1].upper() + text[1:]
    return re.sub(r"(\. )([a-z])", lambda m: m[1] + m[2].upper(), text)


def words(text):
    """Criteria and facts text as the site prints it: phrases reworded."""
    text = str(text)
    for k, v in PHRASES.items():
        text = text.replace(k, v)
    return text


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
    text = text.replace(" · ", "\u00a0· ")  # a separator never starts a line
    # a count word stays with what it counts ("one H100"), a statistic with its number ("sd 0")
    text = re.sub(r"\b(one|two|three|four|five|six|seven|eight|nine|ten) (?=\w)", "\\1\u00a0", text)
    text = re.sub(r"\b(mean|sd) (?=[\d.])", "\\1\u00a0", text)
    # a number stays with its unit, not with the "to" of a range
    return re.sub(r"(\d) (?=(?!to )[A-Za-zµ%×])", "\\1\u00a0", text)


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
    """A source as a link when it has one; otherwise text, its rule codes as links."""
    if href:
        return f'<a href="{e(href)}">{path_html(no_rule(text))}{EXT}</a>'
    return with_rule(text)


def blob(path):
    """A file of this repository, at the commit the site links (RFC-0009 S1, #320 plan §1.1)."""
    return f"{REPO_URL}/blob/{LINK_REF}/{path}"


# ------------------------------------------------------------------ one configuration's figures


def cell_words(cfg, col):
    """(value html, lines, title, measured) for one overview figure of a configuration."""
    if cfg["kind"] == "reference":
        word, line = (REF_OVERHEAD[cfg["reference_role"]] if col == "overhead"
                      else REF_CELLS[col])  # fmt: skip
        if col == "overhead" and cfg["reference_role"] == "serve":  # the word says it all
            return f'<span class="na">{e(word)}</span>', [], no_rule(line), False
        return f'<span class="na">{e(word)}</span>', [no_rule(line)], word, False
    f = cfg["figures"][METRIC[col]]
    if f["value"] is None:
        why = why_words(f, cfg)
        return '<span class="na">No value</span>', [no_rule(why)], no_rule(why), False
    value = shown(f["value"], f["unit"])
    unit_line = {"covers": "{n} token{s} checked", "proof_size": "per proof",
                 "check_time": "per check"}.get(col)  # fmt: skip
    out_tokens = cfg["workload"]["shape"]["output_tokens"]
    tail = (
        [unit_line.format(n=f"{out_tokens:,}", s="" if out_tokens == 1 else "s")]
        if unit_line
        else []
    )
    title = " · ".join([value, *(f"{k}: {v}" for k, v in labels(f, cfg)),
                        f"source: {f['source']}", f"spread: {spread_line(f)}"] if f.get("stats")
                       else [value, *(f"{k}: {v}" for k, v in labels(f, cfg)),
                             f"source: {f['source']}"])  # fmt: skip
    return fig(value), [*spread_parts(f), *tail], title, True


def value_link(cfg, col, href, who=""):
    """A figure on the overview row: a link to the figure's own plate; its labels ride in the
    title. The lines under it are plain text (a link cannot hold the rule links the plates carry)."""
    inner, shown_lines, title, measured = cell_words(cfg, col)
    title = sentence_case(readable(title) if measured else title)
    lines = "".join(f"<span>{e(sentence_case(readable(ln)))}</span>" for ln in shown_lines if ln)
    name = f'<span class="sr">, {e(who)}</span>' if who else ""
    return (
        f'<a class="val" href="{e(href)}" title="{e(title)}">'
        f'<span class="lbl">{e(HEAD[col])}{name}</span><span class="vm">{inner}</span>'
        f'<span class="sub">{lines}</span></a>'
    )


def workload_link(cfg):
    return cfg["workload"]["id"], blob(cfg["workload"]["record"])


def plate(cfg, col, pid=""):
    """One figure's plate, every label in view (S2, S3); pid: an id prefix, so an overview
    figure can link to its own plate."""
    kv = []
    if cfg["kind"] == "reference":
        word, line = (REF_OVERHEAD[cfg["reference_role"]] if col == "overhead"
                      else REF_CELLS[col])  # fmt: skip
        val = f'<span class="na">{e(word)}</span>'
        kv.append(("note", line, None))
    else:
        f = cfg["figures"][METRIC[col]]
        if f["value"] is None:
            val = '<span class="na">No value</span>'
            kv += [("workload", *workload_link(cfg)), ("why", why_words(f, cfg), None)]
        else:
            val = fig(shown(f["value"], f["unit"]))
            if f.get("stats"):
                kv.append(("spread", spread_line(f), None))
            kv += [(k, v, None) for k, v in labels(f, cfg)]
            kv.append(("workload", *workload_link(cfg)))
        if f["recorded"]:
            kv.append(("source", f["source"], None))
    dl = "".join(
        f"<div><dt>{e(k)}</dt><dd>{source_html(v) if k == 'source' else link_or_text(readable(v), href)}</dd></div>"
        for k, v, href in kv
    )
    return (
        f'<div class="plate"{f' id="{e(pid)}{col}"' if pid else ""} data-col="{col}"><p class="lbl">{e(HEAD[col])}</p>'
        f'<p class="pv">{val}</p><dl>{dl}</dl></div>'
    )


def source_html(pointer):
    """A figure's record in the release index, as text until the index is published (#146)."""
    file, _, frag = pointer.partition("#")
    return path_html(file) + "<wbr>" + path_html("#" + frag)


def has_figures(cfg):
    """False for a configuration whose kept runs all failed: it holds no statistic."""
    return any(f["recorded"] for f in cfg["figures"].values())


def runs_counts(cfg):
    """A configuration whose kept runs all failed holds no statistic: its counts, whether it has
    fewer completed runs than a release needs, and RFC-0015 NM-1 when it applies (S3, S7)."""
    runs = cfg["runs"]
    parts = [f"{len(runs['completed'])} completed, {len(runs['failed'])} failed"]
    if cfg["insufficient_repetitions"]:
        parts.append("below minimum repetitions")
    if runs["not_measurable"]:
        parts.append(f"not measurable on {gpu_words(cfg)} (RFC-0015 NM-1)")
    return " · ".join(parts)


def runs_line(cfg):
    """S7: what the figures are over, and every kept run not counted, with its failure record."""
    runs = cfg["runs"]
    out = [f"Runs of this setup: {len(runs['completed'])} completed"]
    if runs["failed"]:
        n = len(runs["failed"])
        said = []
        for f in runs["failed"]:
            parts = [
                FAIL_KIND[f["kind"]]
                + (f" {FAIL_STEP[f['step']]}" if f["step"] in FAIL_STEP else "")
            ]
            if f["exit_code"] is not None:
                parts.append(f"exit code {f['exit_code']}")
            if f["last_line"]:
                parts.append(f'last line: "{f["last_line"]}"')
            said.append("; ".join(parts))
        out.append(f"{n} failed and {'is' if n == 1 else 'are'} not counted ({'; '.join(said)})")
    superseded = [x for x in runs["left_out"] if x["replaced_by"]]
    other = [x for x in runs["left_out"] if not x["replaced_by"]]
    if superseded:
        why = "; ".join(r.split(": ", 1)[1] if ": " in r else r
                        for x in superseded for r in x["reasons"])  # fmt: skip
        out.append(f"{len(superseded)} superseded and replaced ({why})")
    if other:
        out.append(f"{len(other)} left out ({'; '.join(r for x in other for r in x['reasons'])})")
    return "; ".join(out) + ". Each number below is over the completed runs."


# ------------------------------------------------------------------ chrome
# Pages are files <name>.html served at clean, root-relative addresses (vercel.json cleanUrls;
# serve.py does the same locally), so every link works at any depth, the 404 page included.
REF_PAGE = "/reference"  # one page for the reference systems
CRIT_PAGE = "/criteria"  # the criteria behind the six states


def file_of(path):
    return HERE / f"{path.strip('/') or 'index'}.html"


# ------------------------------------------------------------------ fonts, served from fonts/
# fonts/faces.json lists each woff2 file (named with its own hash, so it can be cached for good)
# with the family, weights, widths and unicode range Google Fonts gives it. The arrows subset comes
# last, so its glyphs win where ranges overlap.
PRELOAD = ("archivo-latin.", "plex-mono-400-latin.", "plex-mono-500-latin.")


def load_faces():
    global FACES
    FACES = json.loads((HERE / "fonts" / "faces.json").read_text())["faces"]
    for f in FACES:
        h = hashlib.sha256((HERE / "fonts" / f["file"]).read_bytes()).hexdigest()[:10]
        assert f["file"].endswith(f".{h}.woff2"), f"fonts/{f['file']} does not carry its hash"
    FACES.sort(key=lambda f: f["subset"] == "arrows")


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
        '<input id="q" type="search" autocomplete="off" autocorrect="off" autocapitalize="none" '
        'enterkeyhint="go" spellcheck="false" placeholder="Search" '
        'role="combobox" aria-expanded="false" aria-controls="q-list" aria-autocomplete="list" '
        'aria-keyshortcuts="/ Control+K Meta+K">'
        '<kbd class="skey" aria-hidden="true">/</kbd>'
        '<button type="button" class="sclose" aria-label="Close search">×</button></span>'
        f'<ul id="q-list" class="slist" role="listbox" aria-label="Results" hidden data-index="{version("search.json")}"></ul>'
        "</div>"
    )


def criteria_label():
    """The criteria's standing, from RFC-0016's own status line: (label, short label, RFC the
    label cites). The label changes only once the RFC is Accepted."""
    rfc = CRIT["rfc"]
    if rfc["status"].startswith(("Accepted", "Final")):
        return "Criteria", "Criteria", rfc["file"][:4]
    return "Draft criteria, prototype only, needs an RFC", "Draft criteria, needs an RFC", "0001"


def footer():
    head, _, rfc = criteria_label()
    rel = V["release"]
    line = (
        f"Release {rel['id']}"
        + (" (candidate)" if rel["candidate"] else "")
        + f" · licence {rel['licence']}"
    )
    return (
        f'<footer class="foot"><p><a href="{CRIT_PAGE}">{e(head)}</a>'
        f' (<a class="nw" href="{e(REPO_URL)}/blob/main/rfcs/{RFC_FILES[rfc]}">RFC-{rfc}</a>)'
        f'\u00a0· <a href="{e(REPO_URL)}/blob/main/{e(CRIT["path"])}">criteria.json</a> sha256 <code>{crit_sha[:12]}</code></p>'
        f"<p>{e(readable(line).replace('CC BY 4.0', 'CC\u00a0BY\u00a04.0'))}</p></footer>"
    )


def full_title(title):
    return title if title == "Inference proofs" else f"{title} · Inference proofs"


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
        f'<link rel="stylesheet" href="{version("words.css")}"></head><body class="{cls}">{body}'
        f'<p class="sr" aria-live="polite" id="live"></p><script src="{version("words.js")}" defer></script></body></html>'
    )


def states_key():
    return "".join(
        f'<span class="chip"><i class="sw {STATE_CLS[s]}"></i>{e(STATE_WORD[s])}</span>'
        for s in STATE_ORDER
    )


def keyline():
    return f'<p class="keyline">{states_key()}<a class="draft" href="{CRIT_PAGE}">{e(criteria_label()[1])}<span aria-hidden="true">\u00a0→</span></a></p>'


def masthead():
    """A plain legend: nothing in it can be pointed at or pressed."""
    items = "".join(
        f'<li class="q">{key_mini(i + 1)}<span class="qw">{e(p["name"])}</span><span class="qq">{e(p["question"])}</span></li>'
        for i, p in enumerate(PROPS)
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


def size_words(n):
    """A parameter count as the site prints it: 400000000000 is 400B, 8030261248 8.03B."""
    return f"{n / 1e9:.3g}B"


def name_of(rid):
    return V["facts"]["rows"][rid]["name"]


def upstream(cfg):
    """RFC-0009 S1: the pin is `upstream.commit` of the configuration's claim card."""
    return cfg["card"]["upstream"]


def pin_link(cfg):
    up = upstream(cfg)
    href = f"https://github.com/{up['repo']}/tree/{up['commit']}"
    return f'<a class="pin" href="{e(href)}" title="Pinned upstream commit {e(up["commit"])}">@{e(up["commit"][:8])}</a>'


def kind_words(rid):
    """A reference's role, as its facts word it, without the name it repeats."""
    kt = words(V["facts"]["rows"][rid]["kind_words"])
    name = name_of(rid)
    return sentence_case(kt[len(name) + 2 :]) if kt.startswith(name + ": ") else kt


def row_id(cfg):
    """The row's id: the system's id, unless the system has more than one configuration."""
    same = [c for c in CONFIGS if c["system"] == cfg["system"]]
    if len(same) == 1:
        return cfg["system"]
    return f"{cfg['system']}--{cfg['configuration']}--{cfg['workload']['id']}"


def row_keys(cfg):
    """{col: the stored value in its base unit, or None}: the sort keys of one row (S4)."""
    return {col: cfg["figures"][METRIC[col]]["sort_key"] for col in COLS}


def row_html(rid, name, g, href, idle, right, table=False, keys=None):
    """One home row: pie, name and its pin (or a reference's kind), then `right`, the four figures.
    The model is the section's own heading, so a system row does not repeat it."""
    # the row header is named by the system's name alone, not by the six states and pin it also holds
    cell = f' role="rowheader" aria-labelledby="{e(rid)}-name"' if table else ""
    hid = f' id="{e(rid)}-name"' if table else ""
    attrs = ""
    if table:
        attrs = f' role="row" data-name="{e(name.lower())}" data-k="{e(json.dumps(keys, separators=(",", ":")))}"'
    return f'''
<div class="row" id="{e(rid)}"{attrs}>
  <div class="r-main">
    <div class="sysc"{cell}>
      <a class="pie" href="{e(href)}" tabindex="-1" aria-hidden="true">{pie_svg(g["states"], 120, cells=g["cells"], hit=True)}<span class="tip"></span></a>
      <div class="who"><h3 class="name"{hid}><a href="{e(href)}">{e(name)}</a></h3><p class="sr">{e(states_said(g))}</p>{idle}</div>
    </div>
    {right}
  </div>
</div>'''


def figures(cfg, base, table, block=None, who=""):
    """The four figures of a home row; each links to its own plate, at base + "-" + its column, or
    all to one block (a reference's figures, short enough to show whole with its name)."""
    cell = ' role="cell"' if table else ""
    return (
        '<div class="vals">'
        + "".join(
            f'<div class="vc"{cell} data-col="{c}">{value_link(cfg, c, block or f"{base}-{c}", who)}</div>'
            for c in COLS
        )
        + "</div>"
    )


def sort_heads():
    """The column heads of the sortable table: each one a button with its sort glyph."""

    def head(col, label, cls=""):
        on = col == "system"
        w = SORT_WORDS[col]
        return (
            f'<div class="hc{cls}" role="columnheader" data-col="{col}"'
            + (' aria-sort="ascending"' if on else "")
            + ">"
            f'<button type="button" class="sb" data-col="{col}" data-asc="{e(w["asc"])}" data-desc="{e(w["desc"])}">'
            f'{label}\u00a0<span class="g" aria-hidden="true">{"↑" if on else "↕"}</span></button></div>'
        )

    return (
        f'<div class="heads" role="row">{head("system", "System", " hsys")}'
        + "".join(head(c, e(HEAD[c])) for c in COLS)
        + "</div>"
    )


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


def nb_meta(rid):
    """Family and repository status (the heading says no adapter runs them yet)."""
    status = V["facts"]["rows"][rid]["status"]["state"]
    return " · ".join([FAMILY_WORD[CRIT["rows"][rid]["family"]], STATUS_WORD[status]])


def nb_grid():
    out = ""
    for rid in V["orders"]["not_benchmarked"]:
        r, g = V["facts"]["rows"][rid], glyph(rid)
        out += (
            f'<li class="nb" id="nb-{e(rid)}"><span class="nbpie" role="img" aria-label="{e(aria(g, r["name"]))}">{pie_svg(g["states"], 56)}</span>'
            f'<div><h3 class="nbn">{e(r["name"])}</h3><p class="nbm">{keep(nb_models(r))}</p><p class="nbm">{keep(nb_meta(rid))}</p></div></li>'
        )
    return f'<ul class="nbgrid">{out}</ul>'


def shape_words(cfg):
    """What the configuration ran, from its workload record and reference profile, without the
    model name the section already prints."""
    sh = cfg["workload"]["shape"]
    out = sh["output_tokens"]
    tail = "the next token" if out == 1 else f"{out:,} output tokens"
    batch = sh["batch_size"]
    gpus = cfg["gpu"]["count"]
    return " · ".join([
        f"{sh['prompt_tokens']:,}-token prompt, {tail}",
        f"{batch:,} request{'s' if batch != 1 else ''} per batch",
        f"{gpu_words(cfg)} GPU{'s' if gpus != 1 else ''}",
    ])  # fmt: skip


def model_sizes(cfg):
    """The model's size from its workload record, so a row never reads as a 17B model."""
    p = cfg["workload"]["model"]["parameters"]
    total, active = p["total"], p["active_per_token"]
    if total == active:
        return f"{size_words(total)} parameters"
    return f"{size_words(total)} parameters, {size_words(active)} active per token"


def model_line(cfg):
    """The model fact of a system page: name, size and the precision proved."""
    m = cfg["workload"]["model"]
    p = m["parameters"]
    size = (f"{size_words(p['total'])} parameters (dense)" if p["total"] == p["active_per_token"]
            else f"{size_words(p['total'])} total, {size_words(p['active_per_token'])} active per token")  # fmt: skip
    prec = cfg["workload"]["precision"]["proved"]
    said = V["facts"]["models"][m["digest"]]["precision_words"].get(prec)
    return f"{MODEL_NAME[m['digest']]}, {size}, {prec}" + (f" ({said})" if said else "")


def facts_line(text):
    """A line of facts: each one a span, so phones can list them (words.css); the separator stays
    in the text, so the facts never run together when read aloud."""
    return '<span class="sep">\u00a0· </span>'.join(
        f"<span>{e(x)}</span>" for x in re.split(r"[ \u00a0]· ", text)
    )


def by_name(cfgs):
    return sorted(cfgs, key=lambda c: (name_of(c["system"]).lower(), c["position"]))


def tables():
    """S6: one table per model, largest first, then one per workload of that model."""
    out = []
    for d in MODELS:
        wls = sorted(
            {c["workload"]["id"] for c in PROVERS if c["workload"]["model"]["digest"] == d}
        )
        for wid in wls:
            rows = by_name(c for c in PROVERS if c["workload"]["id"] == wid)
            sid = slug(MODEL_NAME[d]) if len(wls) == 1 else f"{slug(MODEL_NAME[d])}-{slug(wid)}"
            out.append((d, sid, rows))
    return out


def first_config(sid):
    return next(c for c in CONFIGS if c["system"] == sid)


def fig_href(cfg, col):
    """An overview figure's plate on the system page (the system's first configuration has
    plates today; another configuration links to the page)."""
    page_ = PAGE[cfg["system"]]
    return f"{page_}#fig-{col}" if cfg is first_config(cfg["system"]) else page_


def pin_line(r, rows):
    """A row header's pin, and the card's `configuration` where the table holds two rows of the
    system (RFC-0009 S1): the card's identity, no claim text."""
    two = sum(x["system"] == r["system"] for x in rows) > 1
    cfg = f'<span class="nw"> · {e(r["configuration"])}</span>' if two else ""
    return f'<p class="wl">{pin_link(r)}{cfg}</p>'


def build_index():
    first = f"System, {SORT_WORDS['system']['asc']}"
    secs = ""
    seen = set()
    all_tables = tables()
    for d, sid_, rows in all_tables:
        name = MODEL_NAME[d]
        native = ""
        if d not in seen and sum(x[0] == d for x in all_tables) > 1:
            native = f'<p class="sec-l">{e(NATIVE_HEADER)}</p>'
        seen.add(d)
        body_rows = "".join(
            row_html(
                row_id(r),
                name_of(r["system"]),
                glyph(r["system"]),
                PAGE[r["system"]],
                pin_line(r, rows),
                '<div class="vals">'
                + "".join(
                    f'<div class="vc" role="cell" data-col="{c}">{value_link(r, c, fig_href(r, c), name_of(r["system"]))}</div>'
                    for c in COLS
                )
                + "</div>",
                True,
                row_keys(r),
            )
            for r in rows
        )
        secs += f"""
  <section class="sec bench" id="{sid_}" aria-labelledby="h-{sid_}">
    <div class="sec-h"><h2 id="h-{sid_}" class="sect">{e(name)}</h2><p class="sec-l">{facts_line(readable(model_sizes(rows[0]) + " · " + shape_words(rows[0])))}</p>{native}</div>
    <div class="tbl" role="table" aria-labelledby="h-{sid_}" aria-describedby="sort-now" data-col="system" data-dir="asc">
      {sort_heads()}
      <div class="rows" role="rowgroup">{body_rows}</div>
    </div>
  </section>"""
    refs = ""
    for rid in V["orders"]["reference"]:
        cfg = first_config(rid)
        counts = "".join(f'<p class="wl">{with_rule(readable(runs_counts(c)))}</p>'
                         for c in CONFIGS if c["system"] == rid and not has_figures(c))  # fmt: skip
        refs += row_html(
            rid,
            name_of(rid),
            glyph(rid),
            f"{REF_PAGE}#{rid}",
            f'<p class="wl"><span>{e(kind_words(rid))}</span></p>{counts}',
            figures(cfg, "", False, block=f"{REF_PAGE}#{rid}-figures", who=name_of(rid)),
        )
    nb_count = len(V["orders"]["not_benchmarked"])
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
    <div class="sec-h"><h2 id="h-nb" class="sect">Not benchmarked yet<sup aria-hidden="true">{nb_count}</sup><span class="sr">, {nb_count} systems</span></h2></div>
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


def plain_heads(first):
    """Column heads for a block that does not sort: the same columns, for the eye only."""
    return (
        f'<div class="heads plain" aria-hidden="true"><span class="hsys">{e(first)}</span>'
        + "".join(f"<span>{e(HEAD[c])}</span>" for c in COLS)
        + "</div>"
    )


# ------------------------------------------------------------------ system page: the pie with its six properties around it


# Clockwise from twelve, slices 1 to 3 face right and 4 to 6 face left; each property sits on its slice's side.
SIDE = {1: "r", 2: "r", 3: "r", 4: "l", 5: "l", 6: "l"}


def rose_item(c, pre):
    """One property beside its slice: its name (a link to what its states mean), its question for
    screen readers, the state, and our short reason (left out when it only repeats Not stated)."""
    generic = (
        c["state"] == "not_stated" and c["reason"].startswith("Not stated") and not c["quotes"]
    )
    reason = "" if generic else f'<p class="rr">{e(words(c["reason"]))}</p>'
    return (
        f'<li class="rp {SIDE[c["n"]]}" id="{pre}p-{e(c["prop"])}" data-n="{c["n"]}">'
        f'<p class="rn"><a href="{CRIT_PAGE}#{e(c["prop"])}">{e(c["name"])}</a><span class="sr">. {e(c["question"])}</span></p>'
        f'<p class="rs"><i class="sw {STATE_CLS[c["state"]]}"></i>{e(c["word"])}</p>{reason}</li>'
    )


def rose(g, hid, name, level=2, pre=""):
    """The pie, centred, with each property beside its own slice. level: the hidden heading's level
    under the page's own; pre: an id prefix when one page holds several roses."""
    return (
        f'<div class="rose"><h{level} id="{e(hid)}" class="sr">What one proof establishes</h{level}>'
        f'<div class="rpie" role="img" aria-label="{e(aria(g, name, outside=True))}">{hex_svg(184, states=g["states"], hit=True, names=[c["name"] for c in g["cells"]])}</div>'
        f'<ol class="rprops" role="list" aria-labelledby="{e(hid)}">{"".join(rose_item(c, pre) for c in g["cells"])}</ol></div>'
    )


def facts_dl(items):
    return (
        '<dl class="facts">'
        + "".join(f"<div><dt>{e(k)}</dt><dd>{v}</dd></div>" for k, v in items)
        + "</dl>"
    )


def more_table(cfg, caption):
    more = ""
    for metric, label in MORE:
        f = cfg["figures"][metric]
        if f["value"] is not None:
            lab = with_rule(readable(" · ".join(f"{k}: {v}" for k, v in labels(f, cfg))))
            n, _ = amount(f["value"], f["unit"])
            # "GPU cost per 1,000 positions": the row names the basis, so the value drops its own
            val = fig(f"{n} USD" if f["unit"] == "USD/1k_token" else shown(f["value"], f["unit"]))
        else:
            # only why it is missing: the value cell says "No value", and a missing number has no grade
            lab = with_rule(why_words(f, cfg))
            val = '<span class="na">No value</span>'
        more += f'<tr><th scope="row">{e(readable(label))}</th><td class="mv">{val}</td><td class="ml">{lab}</td></tr>'
    return (
        f'<table class="mtab"><caption class="sr">{e(caption)}</caption>'
        f'<thead><tr><th scope="col">Figure</th><th scope="col">Value</th><th scope="col">Labels</th></tr></thead><tbody>{more}</tbody></table>'
    )


def tamper_words(cfg):
    """Each stored outcome count of the configuration's controls (RFC-0008), zero counts left
    out; no sum or difference of them (AGENTS.md rule 3)."""
    counts = cfg["controls"]["counts"]
    said = [w.format(n=counts[k]) for k, w in OUTCOME_WORDS if counts.get(k)]
    return (
        ("Tampering tests on this setup, by outcome: " + "; ".join(said) + ".")
        if said
        else "No tampering test ran on this setup."
    )


def source_label(url):
    """A link's words: the file path and lines a GitHub blob URL names."""
    m = re.match(
        r"https://github\.com/[^/]+/[^/]+/blob/[0-9a-f]+/([^#?]+)(?:\?[^#]*)?(?:#(L\d+(?:-L\d+)?))?",
        url,
    )
    return f"{m[1]} {m[2]}" if m and m[2] else (m[1] if m else url)


def control_tests(cfg):
    """The system's own registered controls (RFC-0008 §System-specific controls) and what the
    checker did with each in the runs, as stored."""
    out = ""
    for sc in cfg["system_controls"]:
        outcomes = {o["outcome"] for o in sc["outcomes"]}
        if sc["kind"] == "weakened_prover":
            text = f"Control test: we turned off one check on purpose, with a switch {name_of(cfg['system'])} documents for this."
        else:
            text = f"Control test {sc['id']}."
        if len(outcomes) == 1:
            o = outcomes.pop()
            text += (
                f" The checker {OUTCOME_VERB[o]} the proof."
                if o in OUTCOME_VERB
                else f" Outcome: {o}."
            )
        else:
            text += (
                " Outcomes by run: "
                + "; ".join(f"{x['run_id']}: {x['outcome']}" for x in sc["outcomes"])
                + "."
            )
        link = (
            f' <a class="qs" href="{e(sc["source"])}">{e(source_label(sc["source"]))}{EXT}</a>'
            if sc["source"]
            else ""
        )
        out += f'<p class="ctl">{e(text)}{link}</p>'
    return out


def status_words(st):
    """A status fact in one form for every system: the state, then its date and source if stored."""
    out = STATUS_WORD[st["state"]]
    if st.get("last_push"):
        src = f" ({st['source']}, retrieved {st['retrieved']})" if st.get("source") else ""
        out += f" · last push {st['last_push']}{src}"
    return out


def pinned(cfg):
    """The card's repository at its pin first (RFC-0016 SRC-2: only it decides), then every other
    repository the row's sources read cite, at the commit the criteria file read it."""
    up = upstream(cfg)
    repos = [(up["repo"], up["commit"])]
    pins = CRIT["pins"]
    cited = set()
    for c in CRIT["rows"][cfg["system"]]["cells"].values():
        for q in [*c["quotes"], *((c.get("outside_pin") or {}).get("quotes") or [])]:
            cited.add(q.get("repo"))
        cited |= {s.split("@", 1)[0] for s in c["sources_read"] if "@" in s}
    repos += [(r, pins[r]) for r in pins if r in cited and r != up["repo"]]
    return "".join(
        f'<a href="https://github.com/{e(r)}/tree/{e(c)}">{path_html(r)}<span class="nw"> @{e(c[:8])}</span>{EXT}</a>'
        for r, c in repos
    )


def build_system(sid):
    name = name_of(sid)
    cfg = first_config(sid)
    g = glyph(sid)
    row = V["facts"]["rows"][sid]
    facts = [
        ("kind", keep(words(f"{FAMILY_WORD[CRIT['rows'][sid]['family']]}: {row['technique']}"))),
        ("model", keep(model_line(cfg))),
        ("pinned", f'<span class="links">{pinned(cfg)}</span>'),
        ("licence", e(row["licence"]["name"])),
        ("status", keep(status_words(row["status"]))),
        ("adapter", f'<a href="{e(cfg["adapter_readme"])}">systems/{e(sid)}/README.md{EXT}</a>'),
    ]
    plates = "".join(plate(cfg, c, "fig-") for c in COLS)
    where = " · ".join(
        [cfg["configuration"], cfg["workload"]["id"], cfg["workload"]["division"], cfg["profile"]]
    )
    body = f'''
{header(sid)}
<main id="main" class="sys">
  <section class="mast mast-sys" aria-labelledby="h-name">
    <div class="mast-in"><h1 id="h-name" class="sysname"><span class="lt">{e(name)}</span></h1></div>
  </section>
  <div class="wrap">
    <section class="over" id="properties" aria-label="{e(name)}: properties and facts">
      {rose(g, "h-props", name)}
      {facts_dl(facts)}
    </section>
    <section class="blk" id="figures" aria-labelledby="h-figs">
      <div class="sec-h"><h2 id="h-figs" class="sect">Figures</h2><p class="sec-l">{e(readable(MODEL_NAME[cfg["workload"]["model"]["digest"]] + " · " + shape_words(cfg)))}</p></div>
      <p class="lead">{e(runs_line(cfg))}</p>
      <div class="plates plates-sys">{plates}</div>
      {more_table(cfg, f"More numbers for {name}, with scope, grade, checked step and source")}
    </section>
    <section class="blk" id="tamper" aria-labelledby="h-tamper">
      <h2 id="h-tamper" class="sect">Tamper tests</h2>
      <p class="tamper">{e(tamper_words(cfg))}</p>
      <dl class="tlab"><div><dt>configuration</dt><dd>{keep(where)}</dd></div></dl>
      {control_tests(cfg)}
    </section>
  </div>
</main>
{footer()}'''
    return page(
        name,
        system_desc(sid),
        body,
        "system",
        sid,
        sid,
    )


def build_reference():
    """One page for the reference systems: each one's six properties, then its one set of figures."""
    secs = ""
    for gid in V["orders"]["reference"]:
        g = glyph(gid)
        name = name_of(gid)
        cfgs = [c for c in CONFIGS if c["system"] == gid]
        models = list(dict.fromkeys(MODEL_NAME[c["workload"]["model"]["digest"]] for c in cfgs))
        facts = [
            ("kind", e(words(V["facts"]["rows"][gid]["kind_words"]))),
            ("model" if len(models) == 1 else "models", e(" · ".join(models))),
        ]
        cfg = cfgs[0]
        counts = "".join(f'<p class="lead">{with_rule(readable(runs_counts(c)))}</p>'
                         for c in cfgs if not has_figures(c))  # fmt: skip
        figs = (
            f'<div class="reffigs" id="{e(gid)}-figures"><h3 class="sect sm">Figures<span class="of"> · {e(name)}</span></h3>'
            f'{counts}<div class="plates plates-sys">{"".join(plate(cfg, c, f"{gid}-fig-") for c in COLS)}</div></div>'
        )
        secs += f'''
    <section class="refsys" id="{e(gid)}" aria-labelledby="h-{e(gid)}">
      <h2 id="h-{e(gid)}" class="refh">{e(name)}</h2>
      <div class="over">{rose(g, f"h-{gid}-props", name, level=3, pre=f"{gid}-")}{facts_dl(facts)}</div>
      {figs}
    </section>'''
    body = f"""
{header("reference")}
<main id="main" class="sys refpage">
  <section class="mast mast-sys" aria-labelledby="h-name">
    <div class="mast-in"><h1 id="h-name" class="sysname refname"><span class="lt">References</span></h1></div>
  </section>
  <div class="wrap">
    <p class="reflead">{e(REF_LEAD)}</p>
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
# words for what the facts' code field says about a system's source
CODE_TERMS = {"no_public_code": "closed source"}
TIER = {"system": 0, "property": 1, "reference": 2, "unbenchmarked": 3}
BADGE = {"reference": "Reference", "unbenchmarked": "Not benchmarked", "property": "Property"}


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

    for sid in V["orders"]["benchmarked"]:
        cfg = first_config(sid)
        fam = FAMILY_WORD[CRIT["rows"][sid]["family"]]
        kind_title = f"{fam}: {V['facts']['rows'][sid]['technique']}"
        add(
            "system",
            name_of(sid),
            PAGE[sid],
            f"{fam} · {MODEL_NAME[cfg['workload']['model']['digest']]}",
            pie_svg(glyph(sid)["states"], 28),
            f"{kind_title} {upstream(cfg)['repo']}",
            fam.lower(),
        )
    for gid in V["orders"]["reference"]:
        add(
            "reference",
            name_of(gid),
            f"{REF_PAGE}#{gid}",
            kind_words(gid),
            pie_svg(glyph(gid)["states"], 28),
            "reference baseline",
        )
    for rid in V["orders"]["not_benchmarked"]:
        r = V["facts"]["rows"][rid]
        fam = FAMILY_WORD[CRIT["rows"][rid]["family"]]
        add(
            "unbenchmarked",
            r["name"],
            f"/#nb-{rid}",
            f"{fam} · {nb_models(r)}",
            pie_svg(glyph(rid)["states"], 28),
            # status, models, source and stated technique; not the people behind it
            " ".join(
                [
                    nb_meta(rid),
                    *r["models"],
                    (r.get("code") or "").replace("_", " "),
                    CODE_TERMS.get(r.get("code"), ""),
                    r.get("technique") or "",
                ]
            ),
            fam.lower(),
        )
    for i, p in enumerate(PROPS):
        add("property", p["name"], f"{CRIT_PAGE}#{p['id']}", p["question"], key_mini(i + 1, 28), "")
    return out


# ------------------------------------------------------------------ the criteria and the 404


def build_criteria():
    """What each state means for each property, from the criteria file: the rules the glyphs are drawn by."""
    # a jump index of the six properties, shown on phones (words.css), names only
    idx = "".join(
        f'<li><a href="#{e(p["id"])}">{key_mini(i + 1, 22)}<span>{e(p["name"])}</span></a></li>'
        for i, p in enumerate(PROPS)
    )
    secs = ""
    for i, p in enumerate(PROPS):
        states = "".join(
            f'<div><dt><i class="sw {STATE_CLS[s]}"></i>{e(STATE_WORD[s])}</dt><dd>{e(words(p["rules"][s]))}</dd></div>'
            for s in STATE_ORDER
        )
        note = f'<p class="cnote">{e(words(p["not_here"]))}</p>' if p.get("not_here") else ""
        secs += (
            f'<section class="crit" id="{e(p["id"])}" aria-labelledby="h-{e(p["id"])}">'
            f'<div class="ch">{key_mini(i + 1)}<h2 id="h-{e(p["id"])}" class="sect">{e(p["name"])}</h2>'
            f'<p class="cq">{e(p["question"])}</p></div><dl class="cs">{states}</dl>{note}</section>'
        )
    body = f"""
{header("criteria")}
<main id="main" class="sys critpage">
  <section class="mast mast-sys" aria-labelledby="h-name">
    <div class="mast-in"><h1 id="h-name" class="sysname"><span class="lt">Criteria</span></h1></div>
  </section>
  <div class="wrap">
    <ul class="cidx" aria-label="Properties">{idx}</ul>
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
    first = PAGE[V["orders"]["benchmarked"][0]]
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
# What a shared link shows: Open Graph and X tags on every page, and one picture per card. The
# renderer writes each picture's source, og/<card>.html (CARD_W x CARD_H CSS px, the view's own
# words and pies); og.mjs renders it to og/<card>.png at CARD_SCALE and records both sha256 in
# og/cards.json. The pages name each picture with its hash, so a new picture is a new URL for link
# caches, and test_cards.py fails when a committed picture was not rendered from its committed source.
SITE_URL = "https://www.inferenceproofs.ai"
CARD_W, CARD_H, CARD_SCALE = 1200, 630, 2
HOME_DESC = "Six properties of one proof per system (draft criteria), and the benchmark's own figures per model, sortable by column."


def system_desc(sid):
    return f"{name_of(sid)}: six properties of one proof (draft criteria) and the benchmark's own figures with their labels."


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
    draft = criteria_label()[1]
    if card == "home":
        return "Inference proofs: " + ", ".join(p["name"] for p in PROPS) + "."
    cfg = first_config(card)
    states = "; ".join(f"{c['name']}: {c['word']}" for c in glyph(card)["cells"])
    model = MODEL_NAME[cfg["workload"]["model"]["digest"]]
    return f"{name_of(card)} on {model} @{upstream(cfg)['commit'][:8]}. {states}. {draft}."


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


def card_css():
    return f"""
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{CARD_W}px;height:{CARD_H}px;overflow:hidden;background:{GROUND};color:{PAPER};-webkit-font-smoothing:antialiased}}
.mono{{font-family:"IBM Plex Mono",monospace}}
.disp{{font-family:"Archivo",sans-serif;font-stretch:66%;font-weight:900}}
.sl.yes{{fill:{INK["yes"]}}}.sl.partly{{fill:{INK["partly"]}}}.sl.no{{fill:{INK["no"]}}}
.sl.unstated{{fill:{UNSTATED}}}
.pie-svg{{display:block;overflow:visible}}
.kmini .on{{fill:{GROUND}}}.kmini .off{{fill:{GROUND};opacity:.2}}
.sw{{display:inline-block;width:.62em;height:.62em;margin-right:.32em;vertical-align:.02em}}
.sw.yes{{background:{INK["yes"]}}}.sw.partly{{background:{INK["partly"]}}}.sw.no{{background:{INK["no"]}}}.sw.unstated{{background:{UNSTATED}}}
"""


def card_page(card, body, css):
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{e(card)} card</title>'
        f"<style>{font_faces('../fonts/')}\n{card_css()}{css}</style></head><body>{body}</body></html>\n"
    )


def home_card():
    """Only what does not change with the systems benchmarked, since link previews stay cached:
    violet, the six properties, each beside its place in the glyph; black, the site's mark and name."""
    props = "".join(
        f'<li>{key_mini(i + 1, 52)}<span class="disp">{e(p["name"])}</span></li>'
        for i, p in enumerate(PROPS)
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
    g = glyph(sid)
    cfg = first_config(sid)
    items = "".join(
        f'<li class="p{c["n"]} {SIDE[c["n"]]}"><p class="mono pn">{e(c["name"])}</p>'
        f'<p class="disp pw"><i class="sw {STATE_CLS[c["state"]]}"></i>{e(c["word"])}</p></li>'
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
        f'<div class="band"><h1 class="disp name">{e(name_of(sid))}</h1>'
        f'<p class="mono meta"><b>Inference proofs</b>{e(MODEL_NAME[cfg["workload"]["model"]["digest"]])}<br>@{e(upstream(cfg)["commit"][:8])}</p></div>'
        f'<div class="rose">{pie_svg(g["states"], 330)}<ol>{items}</ol></div>'
        f'<p class="mono draft">{e(criteria_label()[1])}</p>'
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
    WRITE_TEXT(OG / "icon.svg", icon_svg())
    WRITE_TEXT(OG / "icon.html", icon_card())
    WRITE_TEXT(OG / "home.html", home_card())
    for sid in PAGE:
        WRITE_TEXT(OG / f"{sid}.html", system_card(sid))


def write_font_faces():
    """The @font-face block in words.css, between its markers, from fonts/faces.json."""
    css = (HERE / "words.css").read_text()
    block = "/* fonts: written by build.py */\n" + font_faces("/fonts/") + "\n/* /fonts */"
    new = re.sub(
        r"/\* fonts: written by build.py \*/.*?/\* /fonts \*/", lambda _: block, css, flags=re.S
    )
    assert new != css or block in css, "words.css lacks the fonts markers"
    WRITE_TEXT(HERE / "words.css", new)


def write_readme():
    readme = HERE / "README.md"
    if not readme.exists():
        return
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
        readme.read_text(),
        flags=re.S,
    )
    WRITE_TEXT(readme, txt)


# ------------------------------------------------------------------ render


def setup(view, out):
    """Read the view into the module's globals and run the checks the drawing rests on."""
    global HERE, OG, V, CRIT, PROPS, CONFIGS, PROVERS, PAGE, MODELS, MODEL_NAME
    global RFC_FILES, REPO_URL, LINK_REF, crit_sha
    HERE = pathlib.Path(out)
    OG = HERE / "og"
    V = view
    CRIT = view["criteria"]
    PROPS = [p for pid in CRIT["order"] for p in CRIT["properties"] if p["id"] == pid]
    CONFIGS = view["configurations"]
    PROVERS = [c for c in CONFIGS if c["kind"] == "prover"]
    PAGE = {sid: f"/{sid}" for sid in view["orders"]["benchmarked"]}
    REPO_URL, LINK_REF = view["repository"], view["link_ref"]
    RFC_FILES = {f[:4]: f for f in view["rfcs"] if re.match(r"\d{4}-", f)}
    crit_sha = CRIT["sha256"].removeprefix("sha256:")
    models = {c["workload"]["model"]["digest"]: c["workload"]["model"]["parameters"]["total"]
              for c in CONFIGS}  # fmt: skip
    MODEL_NAME = {d: view["facts"]["models"][d]["name"] for d in models}
    assert len(set(MODEL_NAME.values())) == len(MODEL_NAME), "two models share a name"
    MODELS = sorted((d for d in models if any(c["workload"]["model"]["digest"] == d for c in PROVERS)),
                    key=lambda d: (-models[d], MODEL_NAME[d]))  # fmt: skip
    text = json.dumps(CRIT, ensure_ascii=False) + json.dumps(view["facts"], ensure_ascii=False)
    for k in PHRASES:
        assert k in text, f"PHRASES: {k!r} no longer in the criteria or facts file"
    for rid, row in CRIT["rows"].items():
        assert row["family"] in FAMILY_WORD, f"{rid}: no words for family {row['family']!r}"
    check_inks()
    check_lifts()
    load_faces()


def render(view, out, *, write_json, write_text):
    """Write the site for `view` into `out` (module docstring); returns the pages written."""
    global WRITE_TEXT, WRITE_JSON
    WRITE_TEXT, WRITE_JSON = write_text, write_json
    setup(view, out)
    write_font_faces()
    write_cards()
    # before the pages: they link it by its hash
    write_json(HERE / "search.json", {"entries": search_entries()})
    pages = {file_of("/"): build_index()}
    for sid, path in PAGE.items():
        pages[file_of(path)] = build_system(sid)
    pages[file_of(REF_PAGE)] = build_reference()
    pages[file_of(CRIT_PAGE)] = build_criteria()
    pages[HERE / "404.html"] = build_404()
    for path, text in pages.items():
        write_text(path, text)
    # the build's pages are the only pages: a page it no longer writes would still be deployed
    stale = set(HERE.glob("*.html")) - set(pages)
    assert not stale, f"pages the build no longer writes: {sorted(q.name for q in stale)}"
    assert {q.stem for q in OG.glob("*.html")} == {"icon", "home", *PAGE}, (
        "stale card sources in og/"
    )
    write_json(HERE / "vercel.json", vercel_json())
    write_readme()
    return sorted(pages)
