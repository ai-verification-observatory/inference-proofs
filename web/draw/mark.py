"""The site's mark and name: the turnstile ⊢ (`mark_svg`, `tile_svg`), the lockup INFERENCE ⊢
PROOFS (`lockup_svg`, `stacked_svg`).

The turnstile, on a grid of 20 by 15 units: a solid stem 3 units wide and 15 tall, and on its
centre line an arm of three square cells of 5 units with gaps of 1, the first cell joined to the
stem. Below 32 px it is redrawn on whole pixels (SMALL: 13 by 9 px for the 16 px icon, doubled for
32). The words are Big Shoulders Display 900 in outline (fonts/wordmark.json, written by
wordmark.py from the self-hosted font), tracked +0.02 em; the mark stands between them at cap
height, 4 units after the E and 3 units before the P (1 unit = cap height / 15).
"""

import json
import pathlib

from . import state as S

MASTER = (20, 15, ((0, 0, 3, 15), (3, 5, 5, 5), (9, 5, 5, 5), (15, 5, 5, 5)))
SMALL = (13, 9, ((0, 0, 2, 9), (2, 3, 3, 3), (6, 3, 3, 3), (10, 3, 3, 3)))
GAP_E, GAP_P = 4, 3  # units from the E to the stem, from the last cell to the P
TRACK = 0.02  # the words' tracking, in em


def mark_path(x, y, u, grid=MASTER):
    """The mark's parts as one path (the stem and its joined cell rasterise with no seam)."""
    return "".join(
        f"M{x + a * u:g} {y + b * u:g}h{w * u:g}v{h * u:g}h{-w * u:g}z" for a, b, w, h in grid[2]
    )


def mark_svg(u, cls="lm", small=False):
    """The mark alone in currentColor, u px per unit (small: the whole-pixel drawing)."""
    grid = SMALL if small else MASTER
    w, h = grid[0] * u, grid[1] * u
    return (f'<svg class="{cls}" viewBox="0 0 {w:g} {h:g}" width="{w:g}" height="{h:g}" '
            f'shape-rendering="crispEdges" aria-hidden="true" focusable="false">'
            f'<path fill="currentColor" d="{mark_path(0, 0, u, grid)}"/></svg>')  # fmt: skip


def tile_svg(px, ink, ground, xmlns=False):
    """The icon: the mark in ground ink centred on a square of the brand ink. 16 and 32 px use the
    whole-pixel drawing; larger sizes the master, centred on whole units."""
    if px in (16, 32):
        u = px // 16
        w, h = SMALL[0] * u, SMALL[1] * u
        body = mark_path((px - w) // 2, (px - h) // 2, u, SMALL)
    else:
        u = px // 30  # the master at 2/3 of the side
        w, h = MASTER[0] * u, MASTER[1] * u
        body = mark_path((px - w) // 2, (px - h) // 2, u)
    ns = ' xmlns="http://www.w3.org/2000/svg"' if xmlns else ""
    return (f'<svg{ns} viewBox="0 0 {px} {px}" width="{px}" height="{px}" shape-rendering="crispEdges">'
            f'<rect width="{px}" height="{px}" fill="{ink}"/><path fill="{ground}" d="{body}"/></svg>')  # fmt: skip


# ------------------------------------------------------------------ the words, in outline
def load_wordmark():
    """fonts/wordmark.json, checked against the font file faces.json lists (load_faces first)."""
    data = json.loads((pathlib.Path(S.HERE) / "fonts" / "wordmark.json").read_text())
    assert data["file"] in {f["file"] for f in S.FACES}, (
        f"fonts/wordmark.json is drawn from {data['file']}, which fonts/faces.json does not list: "
        "run wordmark.py"
    )
    S.WORDMARK = data


def word(name, x, base, C, track=TRACK):
    """A word in outline, its ink starting at x, on baseline base, cap height C px. Returns the
    svg and its ink width in px."""
    glyphs = S.WORDMARK["words"][name]
    s = C / S.WORDMARK["cap"]  # px per font unit (1000 per em)
    step = track * 1000
    left = glyphs[0]["ink"][0]
    parts = "".join(f'<path transform="translate({g["x"] + i * step - left:g} 0)" d="{g["d"]}"/>'
                    for i, g in enumerate(glyphs))  # fmt: skip
    last = len(glyphs) - 1
    width = (glyphs[-1]["x"] + last * step + glyphs[-1]["ink"][2] - left) * s
    return f'<g transform="translate({x:.3f} {base:.3f}) scale({s:.5f})">{parts}</g>', width


def overshoot(C):
    """Room above and below the caps for the round letters' overshoot, in px."""
    s = C / S.WORDMARK["cap"]
    over = max(max(-g["ink"][1] - S.WORDMARK["cap"], g["ink"][3])
               for gs in S.WORDMARK["words"].values() for g in gs)  # fmt: skip
    return over * s + 0.5


def lockup_svg(C, cls="lk", label="Inference proofs", ink=None, mark=None):
    """INFERENCE ⊢ PROOFS on one baseline, cap height C px (the mark's height). ink, mark: fills
    of the words and of the mark (None: left to the stylesheet, classes lw and lmk)."""
    u = C / 15
    ov = overshoot(C)
    a, wi = word("INFERENCE", 0, ov + C, C)
    x = wi + GAP_E * u
    if u == int(u):  # a whole-pixel unit: the mark's edges on the pixel grid
        x, ov = round(x), round(ov)
        a, wi = word("INFERENCE", 0, ov + C, C)
    m = mark_path(x, ov, u)
    x += MASTER[0] * u + GAP_P * u
    b, wp = word("PROOFS", x, ov + C, C)
    w, h = x + wp, C + 2 * ov
    wf = f' fill="{ink}"' if ink else ""
    mf = f' fill="{mark}"' if mark else ""
    return (f'<svg class="{cls}" viewBox="0 0 {w:.2f} {h:.2f}" width="{w:.1f}" height="{h:.1f}" '
            f'role="img" aria-label="{label}"><g class="lw"{wf}>{a}{b}</g>'
            f'<path class="lmk"{mf} shape-rendering="crispEdges" d="{m}"/></svg>')  # fmt: skip


def stacked_svg(C, ink, mark, cls="lk", label="Inference proofs"):
    """INFERENCE over ⊢ PROOFS, both lines ending on one edge: the first line's tracking is
    computed so its ink is as wide as the mark, its gap and PROOFS. Line gap 5 units."""
    u = C / 15
    ov = overshoot(C)
    _, wp = word("PROOFS", 0, 0, C)
    right = MASTER[0] * u + GAP_P * u + wp
    glyphs = S.WORDMARK["words"]["INFERENCE"]
    s = C / S.WORDMARK["cap"]
    bare = (glyphs[-1]["x"] + glyphs[-1]["ink"][2] - glyphs[0]["ink"][0]) * s
    track = (right - bare) / s / 1000 / (len(glyphs) - 1)
    a, wi = word("INFERENCE", 0, ov + C, C, track)
    y2 = ov + C + 5 * u
    m = mark_path(0, y2, u)
    b, _ = word("PROOFS", MASTER[0] * u + GAP_P * u, y2 + C, C)
    w, h = max(wi, right), 2 * C + 5 * u + 2 * ov
    return (f'<svg class="{cls}" viewBox="0 0 {w:.2f} {h:.2f}" width="{w:.1f}" height="{h:.1f}" '
            f'role="img" aria-label="{label}"><g fill="{ink}">{a}{b}</g>'
            f'<path fill="{mark}" d="{m}"/></svg>')  # fmt: skip
