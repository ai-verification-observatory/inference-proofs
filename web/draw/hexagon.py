"""The glyph's geometry: the asterisk of n triangles as SVG (`glyph_svg`: five petals for a row,
RFC-0018 §The glyph; `mark_svg`: the six-slot hex, the logo), and the names set in its triangles.
"""

import math

from .words import e

# ------------------------------------------------------------------ the glyph: an asterisk of triangles
# n triangles make a point-top polygon, clockwise from twelve: segment i spans the side from vertex
# step*i to vertex step*(i+1) (step = 360/n). The cuts between them widen toward the centre, so the
# ground they leave draws an asterisk, the footnote mark. A row's glyph has five petals: green,
# amber and red filled, hollow an outline only, drawn inside its cuts (GL-3). The logo is the
# six-slot hex in one colour. Drawn in device pixels (viewBox 0 0 size size): every gap and line
# is sized for the size it is shown at (a page draws one copy per size it shows); up to 128 px the
# hex's centre and flat sides sit on the pixel grid.
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


def _seg(i, n, R, wr, wc, inset=0.0):
    """Segment i of n around the origin, with cut half-widths wr/2 at the rim and wc/2 at the
    centre, every edge moved inward by inset."""
    step = 360 / n
    a0, a1 = step * i, step * (i + 1)
    v0, v1 = pt(R, a0), pt(R, a1)
    n0, n1 = pt(1, a0 + 90), pt(1, a1 - 90)  # inward normals of the two cuts
    e0 = (_add(v0, n0, wr / 2 + inset), _add((0, 0), n0, wc / 2 + inset))
    e1 = (_add(v1, n1, wr / 2 + inset), _add((0, 0), n1, wc / 2 + inset))
    m = pt(1, a0 + step / 2)  # outward normal of the side
    s0, s1 = _add(v0, m, -inset), _add(v1, m, -inset)
    return [_cross(*e0, s0, s1), _cross(*e1, s0, s1), _cross(*e0, *e1)]


def _frame(size, n, snap=True):
    """Centre and circumradius in px. The hex, snapped (up to 40 px, and up to 128 px in state
    inks), has its centre on a pixel centre and its upright sides on pixel edges. Another polygon
    fits the box by its width, its centre moved down so it sits in the middle of the box."""
    if n == 6:
        if snap:
            half = math.floor(size * 0.5 * C30 - 0.5) + 0.5
            return (size / 2 + 0.5, size / 2), half / C30
        return (size / 2, size / 2), size / 2 * 0.985
    step = 360 / n
    width = 2 * max(abs(pt(1, step * k)[0]) for k in range(n))
    bottom = max(pt(1, step * k)[1] for k in range(n))
    R = size * 0.985 / max(width, 1 + bottom)
    return (size / 2, size / 2 + R * (1 - bottom) / 2), R


def _d(poly, c):
    return "M" + "L".join(f"{x + c[0]:.2f} {y + c[1]:.2f}" for x, y in poly) + "Z"


# A name set in its own triangle (the system and checks pages): condensed capitals, in ground ink
# on a filled triangle and in paper on an outline, in user units of the glyph's viewBox. A side
# that leans carries its name along it, the longer line nearer the side; a steep side (within 30
# degrees of upright), level, against it.
NAME_PX, NAME_CAP, NAME_GAP, NAME_INSET = 10.5, 7.45, 10.29, 4.7


def _name_lines(name, outer_first):
    """Two lines at most. Along a side: the line nearer the side (the wider part of the
    triangle) is the longer, and as short as that allows. Level: the most even split."""
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


def _names_svg(names, c, R, states=None):
    out = []
    n = len(names)
    step = 360 / n
    apothem = R * math.cos(math.radians(step / 2))
    for i, name in enumerate(names):
        mid = step * i + step / 2
        mx, my = pt(apothem, mid)
        if 60 < mid % 180 < 120:  # a steep side: level, against it, centred on its middle
            lines = _name_lines(name, None)
            right = mid < 180
            lean = abs(math.cos(math.radians(mid))) * NAME_GAP * len(lines)  # room for its slope
            x = c[0] + mx + (-1 if right else 1) * (NAME_INSET + lean)
            y0 = c[1] + my - (NAME_CAP + NAME_GAP * (len(lines) - 1)) / 2 + NAME_CAP
            anchor = "end" if right else "start"
            body = "".join(
                f'<text x="{x:.2f}" y="{y0 + k * NAME_GAP:.2f}" text-anchor="{anchor}">{e(t)}</text>'
                for k, t in enumerate(lines)
            )
        else:  # along the side, inward from its midpoint
            top = mid < 90 or mid > 270
            lines = _name_lines(name, top)
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
        state = f" {states[i]}" if states else ""
        out.append(f'<g class="t s{i + 1}{state}">{body}</g>')
    return f'<g class="tx">{"".join(out)}</g>'


def glyph_svg(size, states=None, mono=False, cls="pie-svg", names=None, n=None):
    """The glyph: one triangle per state (five petals for a row). states: each petal's state
    (green, amber and red filled, hollow an outline inside its cuts; words.css inks them). mono:
    n slots in currentColor (the logo). names: each slot's name set in it."""
    n = n or len(states)
    c, R = _frame(size, n, size <= 40 or (size <= 128 and not mono))
    wr, wc = (
        (max(1.0, size * 0.016), max(3.0, size * 0.10))
        if mono
        else (max(1.0, size * 0.012), max(1.8, size * 0.05))
    )
    line = max(1.0, round(size / 48, 1))  # an outline's width, in px
    parts = []
    for i in range(n):
        if mono:
            parts.append(f'<path d="{_d(_seg(i, n, R, wr, wc, 0.0), c)}"/>')
        elif states[i] == "hollow":
            d = _d(_seg(i, n, R, wr, wc, line / 2), c)
            parts.append(f'<path class="sl s{i + 1} hollow" stroke-width="{line:g}" d="{d}"/>')
        else:
            d = _d(_seg(i, n, R, wr, wc, 0.0), c)
            parts.append(f'<path class="sl s{i + 1} {states[i]}" d="{d}"/>')
    if names:
        parts.append(_names_svg(names, c, R, states))
    return (
        f'<svg class="{cls}" viewBox="0 0 {size} {size}" width="{size}" height="{size}" '
        f'aria-hidden="true" focusable="false">{"".join(parts)}</svg>'
    )


def sized(draw, sizes):
    """One copy of a glyph per size a page shows it at, each marked with its size (`w<size>`):
    words.css shows the copy for the width in use, so its cuts and sides sit on the pixel grid
    instead of being scaled between pixels. draw: size -> svg."""
    return "".join(draw(s).replace('<svg class="', f'<svg class="w{s} ', 1) for s in sizes)


def mark_svg(size, cls="lm"):
    """The logo mark: the six-slot hex in one colour (currentColor), the asterisk between them."""
    return glyph_svg(size, mono=True, cls=cls, n=6)
