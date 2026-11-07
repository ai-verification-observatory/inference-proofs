"""The glyph's geometry: the hex asterisk as SVG (`hex_svg`, `pie_svg`, `key_mini`, `mark_svg`),
the property names set in its triangles, and the slice lifts, which `check_lifts` holds to the
`--dx`/`--dy` values on `.s1` to `.s6` in words.css.
"""

import math
import re

from . import state as S
from .words import STATE_CLS, e

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
    css = (S.HERE / "words.css").read_text()
    for n, (dx, dy) in LIFT.items():
        m = re.search(rf"\.s{n} {{ --dx: (-?[\d.]+); --dy: (-?[\d.]+); }}", css)
        assert m, f"words.css lacks the .s{n} lift"
        assert abs(float(m[1]) - dx) < 1e-3, f".s{n} --dx"
        assert abs(float(m[2]) - dy) < 1e-3, f".s{n} --dy"
