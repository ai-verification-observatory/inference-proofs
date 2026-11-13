"""The scale page (`scale.html`, RFC-0018 SI-7): every row of the board on a decade axis, one
figure at a time (the multiple of serving, cost, check time and proof size per reply).

Each figure is a section; the strip of sections picks the one drawn (words.js), and with no script
all four are drawn. A section is one table with its axis once at the head and one group (lane) per
model in the level's order under it, its rows in the board's order (OR-5): position, name and
standing, the plot, and the stored figure printed by `fig_html`, alone: its labels are in its
title, and in full on the system's page the row links to. Every lane shares
one decade grid (`extent` over the whole board), so a change of scale between models is seen by
position; nothing is ranked, divided or ordered across lanes, and no mark joins two lanes.

The plot is SVG with no viewBox: every horizontal coordinate is a percentage of its cell, written
here from the view, so text keeps its size at any width and no inline style is needed. A mark is
the row's figure; ticks are its counted sessions, or a range its stored minimum and maximum. They
are positions only: no quotient computed here is printed.
"""

import math

from . import state as S
from .chrome import (
    CHECKS_PAGE,
    SCALE_PAGE,
    counted,
    footer,
    has,
    header,
    page,
    pnav,
    row_cost,
)
from .overview import (
    BARE,
    fig_html,
    href,
    multiple_html,
    name_of,
    nobreak,
    position_html,
    scope_note,
    serving_missing,
    standing_html,
)
from .pages import section, title_band
from .words import (
    FIGURE_HEAD,
    FIGURE_RULE,
    SCALE_LEAD,
    SCALE_LOG,
    SCALE_NOT_RUN,
    SCALE_SERVING,
    architecture,
    e,
    number,
    params,
)

# the figures, in the strip's order (the first is drawn when the address names none): the section's
# id, its name, and the stored unit its axis reads in
DIMS = (("multiple", FIGURE_HEAD["multiple"], "ratio"),
        ("cost", FIGURE_HEAD["cost"], "USD/request"),
        ("check-time", FIGURE_HEAD["check-time"], "s/request"),
        ("proof-size", FIGURE_HEAD["proof-size"], "B/request"))  # fmt: skip
# a stored value in the unit `words.number` reads it in (bytes read as MB); 1 for the others
READING = {"B/request": 1e-6}
# Martian Mono's advance, in em, at the width the site sets it (87.5 %): every glyph alike,
# measured in the served face by the browser (11 px tick labels: 7.15 px a character)
ADV, TICK_PX = 0.65, 11
# the narrowest plot each set of tick labels is drawn for (words.css): a row on one line from
# 1181 px or on two from 601 px (549 px), and a phone of 320 px (272 px)
PLOT_WIDE, PLOT_NARROW = 549, 272
H, MID = 40, 20  # a row's plot: its height in px and its centre line
AXIS_H = 32  # the axis under a lane's head


# ------------------------------------------------------------------ what a lane draws, per figure
def read(v, unit):
    return v * READING.get(unit, 1) if v is not None else None


def baseline_value(rung, key):
    b = rung["baseline"]
    return b[key]["value"] if b and has(b[key]) else None


def figure_of(row, dim):
    """The row's one stored figure for this dimension, as the ladder prints it."""
    figs = row["figures"]
    if dim == "multiple":
        m = figs["multiple"]
        return m if has(m) or not has(figs["session_multiple"]) else figs["session_multiple"]
    if dim == "cost":
        return row_cost(row)
    return figs["verify_seconds_per_reply" if dim == "check-time" else "proof_bytes_per_reply"]


def ticks_of(row, dim, rung):
    """Where the counted sessions sit, in the axis's unit: the multiple and the cost from each
    session's GPU time (m where the row has a steady state, else the whole session), placed by
    the rung's serving GPU time or by the row's own price (its stored USD over its stored GPU
    time); none for check time and proof size, which store no value per session."""
    figs = row["figures"]
    steady = has(figs["multiple"])
    vals = [s.get("m" if steady else "session") for s in row["sessions"]]
    vals = [v for v in vals if v is not None]
    if dim == "multiple":
        b = baseline_value(rung, "gpu_seconds_per_reply")
        return [v / b for v in vals] if b else []
    if dim == "cost":
        usd = figs["steady_usd_per_reply" if steady else "session_usd_per_reply"]
        gpu = figs["steady_gpu_seconds_per_reply" if steady else "session_gpu_seconds_per_reply"]
        return [v * usd["value"] / gpu["value"] for v in vals] if has(usd) and has(gpu) else []
    return []


def marks_of(row, dim, rung, unit):
    """(mean, ticks, range) in the axis's unit: the figure, its sessions, and the stretch they
    cover (or the figure's stored minimum and maximum where no session value is stored)."""
    f = figure_of(row, dim)
    mean = read(f["value"], unit) if has(f) else None
    ticks = ticks_of(row, dim, rung)
    stats = (f or {}).get("stats") or {}
    if len(ticks) > 1:
        span = (min(ticks), max(ticks))
    elif not ticks and stats.get("min") is not None and stats.get("max") is not None:
        span = (read(stats["min"], unit), read(stats["max"], unit))
    else:
        span = None
    return mean, ticks, span


def serving_of(rung, dim):
    """Where serving sits on this axis: 1× on the multiple's (serving over itself), the rung's
    stored serving cost on the cost's; None where the figure has no serving counterpart or the
    rung has no baseline."""
    if dim == "multiple":
        return 1.0 if baseline_value(rung, "gpu_seconds_per_reply") else None
    if dim == "cost":
        return baseline_value(rung, "usd_per_reply")
    return None


def values(dim, unit, rungs):
    """Every value the dimension draws on these rungs: figures, sessions, ranges, serving."""
    out = []
    for rung in rungs:
        out.append(serving_of(rung, dim))
        for row in rung["rows"]:
            mean, ticks, span = marks_of(row, dim, rung, unit)
            out += [mean, *ticks, *(span or ())]
    return [v for v in out if v is not None and v > 0]


# ------------------------------------------------------------------ the decade axis
def extent(vals, ratio=False):
    """The decades drawn, (lo, hi): from the decade of the smallest value to one past the
    largest's, never fewer than two; a multiple's axis starts at 1× at most. None with no value."""
    if not vals:
        return None
    lo = math.floor(math.log10(min(vals)))
    if ratio:
        lo = min(0, lo)
    hi = math.floor(math.log10(max(vals))) + 1
    return lo, max(hi, lo + 2)


def pos(v, lo, hi):
    """A value's place on the axis, in percent of the plot's width."""
    return 100 * (math.log10(v) - lo) / (hi - lo)


def pct(x):
    return f"{x:.2f}%"


def tick_words(k, unit):
    """A decade as the axis prints it: a display word, not a measurement."""
    if unit == "ratio":
        return f"{10**k:,}×"
    return f"{10**k:,}" if k >= 0 else f"{10**k:.{-k}f}"


def labelled(lo, hi, unit, width):
    """The decades labelled on a plot `width` px wide: every k-th from lo, k the least for which
    two labels never meet (a start-anchored end label beside a centred one is the worst pair)."""
    w = max(len(tick_words(k, unit)) for k in range(lo, hi + 1)) * ADV * TICK_PX
    d = width / (hi - lo)
    k = next(k for k in range(1, hi - lo + 1) if k * d >= 1.5 * w + 12 or k == hi - lo)
    return set(range(lo, hi + 1, k))


def axis_svg(lo, hi, unit):
    """The axis under a lane's head: a tick at each decade and at its 2 and 5, and the decades'
    words in two sets, for a wide plot and a phone's (words.css shows one)."""
    out = []
    for k in range(lo, hi + 1):
        x = pct(pos(10**k, lo, hi))
        out.append(f'<line class="mj" x1="{x}" x2="{x}" y1="18" y2="{AXIS_H}"/>')
        if k < hi:
            for m in (2, 5):
                xm = pct(pos(m * 10**k, lo, hi))
                out.append(f'<line class="mn" x1="{xm}" x2="{xm}" y1="25" y2="{AXIS_H}"/>')
    for cls, width in (("w", PLOT_WIDE), ("n", PLOT_NARROW)):
        for k in sorted(labelled(lo, hi, unit, width)):
            anchor = "start" if k == lo else "end" if k == hi else "middle"
            out.append(f'<text class="tl {cls}" x="{pct(pos(10**k, lo, hi))}" y="12" '
                       f'text-anchor="{anchor}">{e(tick_words(k, unit))}</text>')  # fmt: skip
    return (f'<svg class="ax" width="100%" height="{AXIS_H}" aria-hidden="true" '
            f'focusable="false">{"".join(out)}</svg>')  # fmt: skip


def plot_svg(lo, hi, serve, mean=None, ticks=(), span=None):
    """One row's plot: the decade lines and track, serving's line, the sessions' range and
    ticks, and the figure's mark (none where the figure is null). Lines run past the plot's
    height; the cell clips them to the row, so the grid reads through a lane."""
    out = [f'<line class="gd" x1="{x}" x2="{x}" y1="-200" y2="{H + 200}"/>'
           for x in (pct(pos(10**k, lo, hi)) for k in range(lo, hi + 1))]  # fmt: skip
    out.append(f'<line class="tk" x1="0%" x2="100%" y1="{MID}" y2="{MID}"/>')
    if serve is not None:
        x = pct(pos(serve, lo, hi))
        out.append(f'<line class="sv" x1="{x}" x2="{x}" y1="-200" y2="{H + 200}"/>')
    if span is not None:
        out.append(f'<line class="rg" x1="{pct(pos(span[0], lo, hi))}" '
                   f'x2="{pct(pos(span[1], lo, hi))}" y1="{MID}" y2="{MID}"/>')  # fmt: skip
    for t in ticks:
        x = pct(pos(t, lo, hi))
        # as tall as the mark, so sessions under it hide behind it and only a spread one shows
        out.append(f'<line class="ss" x1="{x}" x2="{x}" y1="{MID - 7}" y2="{MID + 7}"/>')
    if mean is not None:
        out.append(f'<svg class="mk" x="{pct(pos(mean, lo, hi))}" y="{MID}" overflow="visible">'
                   '<rect x="-7" y="-7" width="14" height="14"/></svg>')  # fmt: skip
    return (f'<svg class="lx" width="100%" height="{H}" aria-hidden="true" focusable="false">'
            f'{"".join(out)}</svg>')  # fmt: skip


# ------------------------------------------------------------------ a lane, a section, the page
def figure_html(row, dim):
    """The row's figure as the ladder prints it, with its two parts where it has them (CO-7)."""
    if dim == "multiple":
        return multiple_html(row, bare=True)
    f = figure_of(row, dim)
    return fig_html(f, counted(row), sub=BARE, note=scope_note(row, f))


def serving_html(rung, dim):
    """The stored serving figure a model's head prints: GPU time beside the multiple (its 1x),
    named "Serving" as on the ladder; USD beside the cost, named "Serving cost", so each head names
    one quantity; the state where the rung has no baseline; nothing for a figure with no serving
    counterpart."""
    if dim not in ("multiple", "cost"):
        return ""
    b = rung["baseline"]
    key = "gpu_seconds_per_reply" if dim == "multiple" else "usd_per_reply"
    fig = serving_missing(b) if b is None or not has(b[key]) else fig_html(b[key], sub=BARE)
    head = SCALE_SERVING if dim == "multiple" else f"{SCALE_SERVING} {FIGURE_HEAD['cost'].lower()}"
    return f'<span class="lsv"><span class="k">{e(head)}</span>{fig}</span>'


def lane_html(rung, dim, unit, ext):
    """One model under the section's one axis: a group of the table, headed by its size in a tab
    and its name under a cobalt rule, its architecture (the tab says its size: a mixture of
    experts names its active parameters only), with its serving figure where the figure has one
    (its state where the model has none, as on the ladder); then its rows on the section's decade grid (`ext`). A model not run is its head and a line."""
    total, active = rung["parameters_total"], rung.get("parameters_active")
    size = e(params(total))
    facts = architecture(total, active, sized=False)
    serving = serving_html(rung, dim)
    head = (f'<tr class="grp"><th colspan="4" scope="rowgroup" id="{dim}-{e(rung["id"])}">'
            f'<span class="lh"><span class="rk">{size}</span>'
            f'<span class="ln">{nobreak(rung["model"])}</span>'
            f'<span class="lf">{nobreak(facts)}</span>{serving}</span></th></tr>')  # fmt: skip
    if not rung["rows"] or ext is None:
        return (f'<tbody class="lane">{head}<tr class="nrun"><td colspan="4">'
                f"{e(SCALE_NOT_RUN)}</td></tr></tbody>")  # fmt: skip
    lo, hi = ext
    serve = serving_of(rung, dim)
    trs = []
    for row in rung["rows"]:
        mean, ticks, span = marks_of(row, dim, rung, unit)
        trs.append(
            f'<tr class="row {"ok" if row["passed"] else "np"}" id="scale-{dim}-{e(row["page"])}">'
            f'<td class="cp">{position_html(row, rung)}</td>'
            f'<th class="csys" scope="row"><a class="sname" href="{e(href(row))}">'
            f'{e(name_of(row))}</a><span class="st">{standing_html(row)}</span></th>'
            f'<td class="cx" aria-hidden="true">{plot_svg(lo, hi, serve, mean, ticks, span)}</td>'
            f'<td class="cf">{figure_html(row, dim)}</td></tr>'
        )
    return f'<tbody class="lane">{head}{"".join(trs)}</tbody>'


def panel_html(dim, name, unit, shared=True):
    """One figure's section: one table, its axis once at the head, a group per model under it,
    largest first. `shared`: every group on the decade grid of the whole board (SI-7); False sets
    each group on its own values' grid in a table of its own (the stricter reading, Q17)."""
    rungs = S.V["rungs"]
    whole = extent(values(dim, unit, rungs), unit == "ratio")
    named = (f'<a class="df" href="{CHECKS_PAGE}#{dim}">{e(name)}</a>' if dim in FIGURE_RULE
             else e(name))  # fmt: skip
    # the unit keeps its own case in the uppercased head ("s/reply", not "S/REPLY")
    _, sign = number(1, unit)
    rest = f" {SCALE_SERVING.lower()}" if unit == "ratio" else ""
    words = f'<span class="u">{e(sign)}</span>{e(rest)}, {e(SCALE_LOG)}'

    def table(groups, ext):
        lo, hi = ext if ext is not None else (0, 1)
        axis = axis_svg(lo, hi, unit) if ext is not None else ""
        thead = ('<thead><tr><th scope="col" class="cp"><span class="sr">Position</span></th>'
                 '<th scope="col" class="csys">System</th>'
                 f'<th scope="col" class="cx"><span class="al">{words}</span>'
                 f"{axis}</th>"
                 f'<th scope="col" class="cf">{named}</th></tr></thead>')  # fmt: skip
        return (f'<table class="scl" data-lo="{lo}" data-hi="{hi}">'
                f'<caption class="sr">{e(name)}</caption>{thead}{groups}</table>')  # fmt: skip

    if shared:
        body = table("".join(lane_html(r, dim, unit, whole) for r in rungs), whole)
    else:
        body = "".join(table(lane_html(r, dim, unit, g), g) for r in rungs
                       for g in [extent(values(dim, unit, [r]), unit == "ratio")])  # fmt: skip
    return section(dim, name, body).replace('class="blk"', 'class="blk scl-panel"', 1)


def build_scale():
    panels = "".join(panel_html(d, n, u) for d, n, u in DIMS)
    body = f"""
{header("scale")}
<main id="main" class="sys">
  {title_band("Scale").replace("</h1>", f'</h1><p class="lt-s">{e(SCALE_LEAD)}.</p>', 1)}
  {pnav("Scale", [(d, n) for d, n, _ in DIMS])}
  <div class="wrap">{panels}</div>
</main>
{footer()}"""
    names = [n.lower() for _, n, _ in DIMS]
    desc = f"{SCALE_LEAD}: {', '.join(names[:-1])} and {names[-1]}."
    return page("Scale", desc, body, "system scalepage", SCALE_PAGE.strip("/"), "home")
