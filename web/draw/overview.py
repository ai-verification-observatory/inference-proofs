"""The Overview page (`overview.html`, RFC-0018 SI-7): every system run on one plot.

The reader picks the two figures the plot draws, one up and one across, among cost vs serving,
verify time, proof size, Fidelity and the model's size (the pickers are radio buttons: the page's
own rules move every system, with or without script; words.js keeps the pair in the address).
Cost vs serving across and verify time up are drawn first.

Up and right is always the better end: an axis whose figure is better low (cost, time, size) runs
from its largest value to its smallest, and a corner of the plot says in words what that end is
("cheaper to prove, faster to verify"). A decade axis is labelled in the words a reader counts in
(1 min, 1 h; 100B, 1T) at their true places; the figures themselves keep their one unit
(`words.number`). Cost vs serving's axis always reaches 1×, serving itself.

A system on the plot is a dot where its two figures meet, drawn larger the larger its model
(`unit_of`: a step of size, not an area to measure), its name and its model's size beside it,
and, for a row that has not passed, that it has not (its dot open). A system in hand (pointed
at, focused, or tapped once on a touch screen) draws two lines to the axes, prints its two
figures on them, and opens a card by its dot with its criteria: the glyph, its petals named. A
row with a figure missing on an axis picked leaves the plot and is named under it.

Every system shares the axes, so a change of scale between models is seen by position; nothing
is ranked, divided or ordered across models, and no mark joins two systems. Under the plot the
systems not run stand by their reason. No quotient computed here is printed.
"""

import math
import re

from . import state as S
from .chrome import (
    OVERVIEW_PAGE,
    footer,
    further,
    has,
    header,
    lead_figure,
    not_passed,
    page,
    proving_figure,
)
from .hexagon import glyph_svg
from .ladder import (
    ROW_GLYPH,
    fidelity_row,
    href,
    name_of,
    not_run_html,
    states,
    states_words,
)
from .pages import title_band
from .words import (
    FIGURE_HEAD,
    OVERVIEW_ACROSS,
    OVERVIEW_BETTER,
    OVERVIEW_COUNTS,
    OVERVIEW_LEAD,
    OVERVIEW_MODEL,
    OVERVIEW_OFF,
    OVERVIEW_UP,
    PETAL_NAME,
    SCALE_LINEAR,
    SCALE_LOG,
    SCALE_NOT_RUN,
    SCALE_SERVING,
    e,
    number,
    params,
    shown,
)

# every figure a plot can draw, in the pickers' order: its stored unit and the end it is better
# at; the pair drawn when the address names none
DIMS = {"multiple": ("ratio", "low"), "proving": ("ratio", "low"),
        "check-time": ("s/request", "low"),
        "proof-size": ("B/request", "low"), "fidelity": ("percent", "high"),
        "model": ("parameters", "high")}  # fmt: skip
X0, Y0 = "multiple", "check-time"
# a stored value in the unit an axis reads it in (bytes as MB); 1 for the others
READING = {"B/request": 1e-6}
# the room left past the largest and under the smallest value on a decade axis, as a factor
PAD = 1.25
# Martian Mono's advance, in em, at the width the site sets it (87.5 %), at the tick labels' size
ADV, TICK_PX = 0.65, 12
# the narrowest plot each set of tick labels is drawn for (words.css): a desktop's (from 1181 px),
# a narrower one (from 761 px) and a phone of 320 px
PLOT_FULL, PLOT_WIDE, PLOT_NARROW = 760, 520, 240
AXIS_H = 34  # the axis under the plot
# a mark's glyph: its unit, by its model's size: UNIT at 100M parameters and UNIT_STEP more for
# each decade, between UNIT_LEAST and UNIT_MOST
UNIT, UNIT_STEP, UNIT_LEAST, UNIT_MOST = 0.8, 0.25, 0.7, 1.9
# a name past this share of the plot's width stands left of its mark, and a mark past this share
# of its height has its criteria card under it
FLIP, HIGH = 0.72, 0.6


def selector(eid):
    """An id as a selector: an id may hold a dot ("llama-3.1-8b"), which a selector escapes."""
    return "#" + re.sub(r"([^A-Za-z0-9_-])", r"\\\1", eid)


def pc(v):
    return f"{v:.2f}%"


# ------------------------------------------------------------------ a figure, per row
def head_of(dim):
    return OVERVIEW_MODEL if dim == "model" else FIGURE_HEAD[dim]


def value_of(row, rung, dim):
    """Where the row sits on this figure's axis, in the axis's unit, or None where the row has
    no such figure (a null figure, a Fidelity that reads as the check's state) or a decade axis
    has no place for it (zero or less)."""
    if dim == "model":
        return rung["parameters_total"]
    if dim == "fidelity":
        mine = fidelity_row(row)
        return mine["percent"] if mine else None
    f = figure_of(row, dim)
    v = f["value"] * READING.get(f["unit"], 1) if has(f) else None
    return v if v is not None and v > 0 else None


def figure_of(row, dim):
    """The row's one stored figure for cost, time or size, as the ladder prints it (the multiple
    at the whole sessions' scope wherever the row has it: `lead_figure`)."""
    if dim == "multiple":
        return lead_figure(row)[1]
    if dim == "proving":  # CO-9 (Q55): on a board built by the further-reply rule only
        return proving_figure(row)
    return row["figures"]["verify_seconds_per_reply" if dim == "check-time"
                          else "proof_bytes_per_reply"]  # fmt: skip


def pill_words(row, rung, dim):
    """The figure as a mark in hand prints it on its axis: number and unit."""
    if dim == "model":
        return params(rung["parameters_total"])
    if dim == "fidelity":
        return f"{fidelity_row(row)['percent']:.1f}\u202f%"
    f = figure_of(row, dim)
    return shown(f["value"], f["unit"])


def pill_html(row, rung, dim):
    """A figure on its axis while its system is in hand: the number, then its unit apart (the
    figure up sets its unit under the number, so it keeps to the axis's gutter)."""
    num, _, unit = pill_words(row, rung, dim).replace("\u202f", "\u00a0").partition("\u00a0")
    tail = f'<span class="pu">{e(unit)}</span>' if unit else ""
    return f'<span class="v v-{dim}">{e(num)}{tail}</span>'


# ------------------------------------------------------------------ an axis
def log_steps(dim):
    """The places a decade axis may be labelled at, as (value, words), smallest first: words a
    reader counts in, each at its true place."""
    if dim == "check-time":
        return [(0.01, "0.01 s"), (0.1, "0.1 s"), (1, "1 s"), (10, "10 s"), (60, "1 min"),
                (600, "10 min"), (3600, "1 h"), (36000, "10 h"), (360000, "100 h")]  # fmt: skip
    if dim in ("multiple", "proving"):
        return [(1, f"1× {SCALE_SERVING.lower()}")] + [(10**k, f"{10**k:,}×") for k in range(1, 9)]
    if dim == "proof-size":
        return [(10**k, f"{10**k:,} MB" if k >= 0 else f"{10**k:.{-k}f} MB") for k in range(-3, 7)]
    names = {6: "1M", 7: "10M", 8: "100M", 9: "1B", 10: "10B", 11: "100B", 12: "1T", 13: "10T"}
    return [(10**k, w) for k, w in names.items()]


def axis_of(dim, vals):
    """A figure's axis over these values, or None with none: where a value sits on it (`at`, the
    share of the way from the worse end to the better end) and its ticks as (share, words),
    worse end first."""
    if not vals:
        return None
    better_high = DIMS[dim][1] == "high"
    if dim == "fidelity":
        lo = min(90, 5 * math.floor((min(vals) - 1) / 5))
        hi, step = 100, 5 if 100 - lo <= 30 else 10
        span = [(v, f"{v}\u202f%") for v in range(lo, hi + 1, step)]

        def share(v):
            return (v - lo) / (hi - lo)
    else:
        steps = log_steps(dim)
        low = [s for s in steps if s[0] <= min(vals) / PAD] or steps[:1]
        high = [s for s in steps if s[0] >= max(vals) * PAD] or steps[-1:]
        lo, hi = (1 if dim in ("multiple", "proving") else low[-1][0]), high[0][0]
        if hi <= lo:
            hi = next(s for s, _ in steps if s > lo)
        span = [s for s in steps if lo <= s[0] <= hi]

        def share(v):
            return (math.log10(v) - math.log10(lo)) / (math.log10(hi) - math.log10(lo))

    def at(v):
        return share(v) if better_high else 1 - share(v)

    ticks = sorted((at(v), words) for v, words in span)
    return {"at": at, "ticks": ticks, "lo": lo, "hi": hi}


def labelled(ticks, width):
    """The ticks labelled on an axis `width` px long, by index: every k-th from the last (the
    better end, where the eye goes first), k the least for which two labels never meet."""
    last = len(ticks) - 1
    if last < 1:
        return set(range(len(ticks)))
    w = max(len(words) for _, words in ticks) * ADV * TICK_PX
    d = width / last
    k = next(k for k in range(1, last + 1) if k * d >= 1.4 * w + 12 or k == last)
    return {i for i in range(last, -1, -k)}


def across_svg(dim, axis):
    """The axis under the plot for this figure: a tick at each of its places and their words in
    three sets, for a desktop's plot, a narrower one and a phone's (words.css shows one)."""
    ticks = axis["ticks"]
    out = [f'<line class="mj" x1="{pc(100 * x)}" x2="{pc(100 * x)}" y1="0" y2="8"/>'
           for x, _ in ticks]  # fmt: skip
    for tl, width in (("x", PLOT_FULL), ("w", PLOT_WIDE), ("n", PLOT_NARROW)):
        for i in sorted(labelled(ticks, width)):
            x, words = ticks[i]
            anchor = "start" if x < 0.03 else "end" if x > 0.97 else "middle"
            out.append(f'<text class="tl {tl}" x="{pc(100 * x)}" y="25" text-anchor="{anchor}">'
                       f"{e(words)}</text>")  # fmt: skip
    return (f'<svg class="ax ox x-{dim}" data-lo="{axis["lo"]:g}" data-hi="{axis["hi"]:g}" '
            f'width="100%" height="{AXIS_H}" aria-hidden="true" focusable="false">'
            f'{"".join(out)}</svg>')  # fmt: skip


def tick_tspan(words):
    """An up tick's words; serving's own name apart, which a phone's narrow gutter leaves out."""
    head, _, tail = words.partition(" ")
    if tail == SCALE_SERVING.lower():
        return f'{e(head)}<tspan class="tsv"> {e(tail)}</tspan>'
    return e(words)


def up_svg(dim, axis):
    """The axis left of the plot for this figure, as tall as it; a place is counted from the
    plot's foot."""
    out = []
    for y, words in axis["ticks"]:
        at = pc(100 - 100 * y)
        out.append(f'<line class="mj" x1="90%" x2="100%" y1="{at}" y2="{at}"/>'
                   f'<text class="tl" x="86%" y="{at}" dy=".35em" text-anchor="end">{tick_tspan(words)}'
                   "</text>")  # fmt: skip
    return (f'<svg class="ax oy y-{dim}" width="100%" height="100%" aria-hidden="true" '
            f'focusable="false">{"".join(out)}</svg>')  # fmt: skip


def grid_svg(dim, axis, side):
    """One figure's lines across the plot (`side` x: upright lines, y: level ones). Serving's own
    place, 1×, is drawn in the frame's ink: the end every cost is read against."""
    out = []
    for f, words in axis["ticks"]:
        goal = ' class="goal"' if dim in ("multiple", "proving") and words.startswith("1×") else ""
        if side == "x":
            out.append(f'<line{goal} x1="{pc(100 * f)}" x2="{pc(100 * f)}" y1="0" y2="100%"/>')
        else:
            at = pc(100 - 100 * f)
            out.append(f'<line{goal} x1="0" x2="100%" y1="{at}" y2="{at}"/>')
    return (f'<svg class="gl {side}-{dim}" width="100%" height="100%" aria-hidden="true" '
            f'focusable="false">{"".join(out)}</svg>')  # fmt: skip


def unit_words(dim):
    """An axis's unit and scale in words."""
    if dim == "fidelity":
        return f"%, {SCALE_LINEAR}"
    if dim == "model":
        return f"parameters, {SCALE_LOG}"
    unit = DIMS[dim][0]
    _, sign = number(1, unit)
    rest = f" {SCALE_SERVING.lower()}" if unit == "ratio" else ""
    return f"{sign}{rest}, {SCALE_LOG}"


# ------------------------------------------------------------------ the systems
def unit_of(rung):
    """The unit a model's systems' dots are drawn at on the plot: a step up for each decade of
    its parameters, so a larger model's dot is larger. A step of size, not a measure: the model's
    size is printed beside the name."""
    step = UNIT + UNIT_STEP * (math.log10(rung["parameters_total"]) - 8)
    return round(min(UNIT_MOST, max(UNIT_LEAST, step)), 2)


def mark_html(row, rung, places, dims, css):
    """One system on the plot: a box at its place (its shares on every axis are custom
    properties, the page's rules pick the two drawn) holding the two lines to the axes and the
    two figures on them, shown while it is in hand, and its mark, a link to its page: a dot at
    its model's step of size, its name and its model's size, and for a row not passed that it
    has not (and an open dot). While it is in hand, a card by the dot holds its glyph with its
    petals named: the criteria, which a screen reader reads in the link."""
    page_id = row["page"]
    bid = f"ob-{page_id}"
    props = {f"f-{d}": f"{v:.4f}" for d, v in places.items()} | {"u": unit_of(rung)}
    css.append(f"{selector(bid)}{{{';'.join(f'--{k}:{v}' for k, v in props.items())}}}")
    # a name near the better end of the axis across stands left of its mark
    for d, v in places.items():
        if v > FLIP:
            css.append(f".ovw:has(#ox-{d}:checked) {selector(bid)} .onw{{left:auto;"
                       f"right:calc(5px * var(--u) + 10px);align-items:flex-end}}")  # fmt: skip
    missing = " ".join(f"no-{d}" for d in dims if d not in places)
    state = "ok" if row["passed"] else "np"
    note = "" if row["passed"] else f'<span class="ons">{e(not_passed(row))}</span>'
    # the criteria card under the mark where the mark stands high on the axis up
    for d, v in places.items():
        if v > HIGH:
            css.append(f".ovw:has(#oy-{d}:checked) {selector(bid)} .otp{{bottom:auto;"
                       f"top:calc(5px * var(--u) + 14px)}}")  # fmt: skip
    pills = "".join(pill_html(row, rung, d) for d in places)
    arms = glyph_svg(ROW_GLYPH, states(row), names=[PETAL_NAME[p["id"]] for p in row["glyph"]])
    return (
        f'<div class="obx {state} {missing}" id="{bid}" data-s="{e(page_id)}">'
        '<i class="gx"></i><i class="gy"></i>'
        f'<span class="opv opvx" aria-hidden="true">{pills}</span>'
        f'<span class="opv opvy" aria-hidden="true">{pills}</span>'
        f'<span class="otp" aria-hidden="true">{arms}</span>'
        f'<a class="mk" href="{e(href(row))}"><span class="gm" aria-hidden="true"></span>'
        f'<span class="onw"><span class="onl"><span class="onm">{e(name_of(row))}</span>'
        f'<span class="osz">{e(params(rung["parameters_total"]))}</span></span>{note}</span>'
        f'<span class="sr">: {states_words(row)}</span></a></div>'
    )


# ------------------------------------------------------------------ the pickers and their rules
def picker_html(side, dims, chosen):
    """One axis's picker: a radio button per figure, the one drawn checked; `side` x or y."""
    word, arrow = (OVERVIEW_ACROSS, "→") if side == "x" else (OVERVIEW_UP, "↑")
    chips = "".join(
        f'<label class="opc"><input type="radio" name="o{side}" id="o{side}-{d}" value="{d}"'
        f"{' checked' if d == chosen else ''}><span>{e(head_of(d))}</span></label>"
        for d in dims
    )
    units = "".join(f'<span class="ou u-{side}-{d}">{e(unit_words(d))}</span>' for d in dims)
    return (f'<fieldset class="opk opk{side}"><legend class="sr">{e(word)}</legend>'
            f'<div class="pkr"><span class="pkl" aria-hidden="true"><span class="oar">{arrow}</span>'
            f'{e(word)}</span>{chips}<span class="oun">{units}</span></div></fieldset>')  # fmt: skip


def switch_css(dims):
    """The page's rules that draw the two figures picked: each axis's ticks, lines and unit, every
    system's place, the figures on a mark in hand, and a row missing one of the two leaves the
    plot and is named under it."""
    out = []
    for d in dims:
        x, y = f".ovw:has(#ox-{d}:checked)", f".ovw:has(#oy-{d}:checked)"
        out += [
            f"{x} :is(.x-{d},.u-x-{d},.b-x-{d}),{y} :is(.y-{d},.u-y-{d},.b-y-{d}){{display:block}}",
            f"{x} .b-x-{d},{y} .b-y-{d}{{display:inline}}",
            f"{x} .obx{{--fx:var(--f-{d})}}",
            f"{y} .obx{{--fy:var(--f-{d})}}",
            f"{x} .opvx .v-{d},{y} .opvy .v-{d}{{display:inline}}",
            f"{x} .obx.no-{d},{y} .obx.no-{d}{{display:none}}",
            f"{x} .ooff:has(.no-{d}),{y} .ooff:has(.no-{d}){{display:block}}",
            f"{x} .oon.no-{d},{y} .oon.no-{d}{{display:inline}}",
        ]
    return "".join(out)


def off_html(entries, dims):
    """The systems a pair of figures leaves off the plot, one of the two missing: named under it,
    each a link to its page (the page's rules show the line, and a name, for the pair drawn). A
    bad result is said where the plot is, in words."""
    off = [(row, places) for row, _, places in entries if len(places) < len(dims)]
    if not off:
        return ""
    names = "".join(f'<a class="oon {" ".join(f"no-{d}" for d in dims if d not in places)}" '
                    f'href="{e(href(row))}">{e(name_of(row))}</a>' for row, places in off)  # fmt: skip
    return f'<p class="ooff"><span class="k">{e(OVERVIEW_OFF)}</span>{names}</p>'


def counts_html():
    """The counts under the title: systems run, passed, models, systems not run."""
    n = {"run": len(S.ROWS), "passed": sum(1 for r in S.ROWS if r["passed"]),
         "models": len(S.V["rungs"]), "not_run": len(S.V["not_run"])}  # fmt: skip
    cells = "".join(f'<li><span class="ocv">{n[k]:,}</span><span class="ocl">{e(words)}</span></li>'
                    for k, words in OVERVIEW_COUNTS)  # fmt: skip
    return f'<ul class="ocn">{cells}</ul>'


def plot_html(css):
    """The plot and its two pickers. With no system run, a line says so."""
    pairs = [(row, rung) for rung in S.V["rungs"] for row in rung["rows"]]
    vals = {d: [v for row, rung in pairs if (v := value_of(row, rung, d)) is not None]
            for d in DIMS}  # fmt: skip
    dims = [d for d in DIMS if vals[d]]
    if X0 not in dims or Y0 not in dims:
        return f'<p class="onr">{e(SCALE_NOT_RUN)}</p>'
    axes = {d: axis_of(d, vals[d]) for d in dims}
    entries = []
    for row, rung in pairs:
        places = {d: axes[d]["at"](v) for d in dims
                  if (v := value_of(row, rung, d)) is not None}  # fmt: skip
        entries.append((row, rung, places))
    css.append(switch_css(dims))
    marks = "".join(mark_html(row, rung, places, dims, css) for row, rung, places in entries)
    better = "".join(f'<span class="b-x-{d}">{e(OVERVIEW_BETTER[d])}</span>' for d in dims)
    better_y = "".join(f'<span class="b-y-{d}">{e(OVERVIEW_BETTER[d])}</span>' for d in dims)
    return (
        f'<div class="ovw" id="plot">'
        f'<div class="ovc">{picker_html("y", dims, Y0)}'
        f'<div class="ovq"><div class="oyw">{"".join(up_svg(d, axes[d]) for d in dims)}</div>'
        f'<p class="obt"><span class="oar" aria-hidden="true">↗</span>{better}'
        f'<span class="cm">, </span>{better_y}</p>'
        f'<div class="ovb">{"".join(grid_svg(d, axes[d], "x") for d in dims)}'
        f"{''.join(grid_svg(d, axes[d], 'y') for d in dims)}"
        f"{marks}</div>"
        f'<div class="oxw">{"".join(across_svg(d, axes[d]) for d in dims)}</div></div>'
        f"{picker_html('x', dims, X0)}{off_html(entries, dims)}</div></div>"
    )


# ------------------------------------------------------------------ the page
def build_overview():
    css: list[str] = []
    plot = plot_html(css)
    body = f"""
{header("overview")}
<main id="main" class="sys">
  {title_band("Overview", under=counts_html())}
  <div class="wrap"><section class="ovs" aria-label="{e(OVERVIEW_LEAD)}">{plot}</section>
  {not_run_html()}</div>
</main>
{footer()}"""
    return page("Overview", overview_words(), body, "system overviewpage",
                OVERVIEW_PAGE.strip("/"), "home", css="".join(css))  # fmt: skip


def overview_words():
    """The overview page in a line (its description and its search line): its figures' names in
    lower case."""
    # the proving multiple is a figure of a further-reply board only (CO-9, Q55)
    ups = ", ".join(head_of(d).lower() for d in DIMS if d != X0 and (d != "proving" or further()))
    return f"{OVERVIEW_LEAD}: {FIGURE_HEAD[X0].lower()} against {ups}."
