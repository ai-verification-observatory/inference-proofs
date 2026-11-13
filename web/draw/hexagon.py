"""The glyph's geometry: the proof lines as SVG (`glyph_svg`: five arms for a row, RFC-0018 §The
glyph). The turnstile with one arm per petal: a cobalt stem, and each arm the petal's name in
ground ink on the ink of its state. The site's logo is the turnstile itself (mark.py).
"""

from . import state as S
from .inks import COBALT, GROUND, MUTED
from .words import e

# ------------------------------------------------------------------ the glyph: a stem and its arms
# Drawn on the mark's own units (mark.py: stem 3, cell 5, gap 1): the stem 3 units wide, an arm 5
# high, 1 unit of ground between arms, each arm joined to the stem as the mark's first cell is.
# Every arm has the same length in every state, so the outline never changes and nothing adds up.
# A state is the arm's ink (green, amber, red); a red arm's name is struck, so the name cannot be
# read as a warning about the property; hollow is an outline, open toward the stem, its name in the
# muted ink. With names an arm is 50 units long and the names are set 4 units high; without (under
# 3 px a unit, where the names could not be read) it is 22 long and the stem stands 1 unit proud.
# The viewBox is in units, so every edge sits on a whole pixel at a whole-pixel unit.
STEM, ARM, GAP = 3, 5, 1
LONG, SHORT = 50, 22
NAME, PAD, TRACK = 4.0, 1.6, 0.04  # the name's size, its inset in units, its tracking in em
STRIKE = 0.5  # a red name's strike, in units
# Big Shoulders Display 800, capitals: each advance in em (measured in the face, kerning off). A
# struck name is set to this width (textLength), so the strike and the name always end together.
CAPS = {
    "A": 0.443, "B": 0.441, "C": 0.455, "D": 0.461, "E": 0.381, "F": 0.378, "G": 0.457, "H": 0.455,
    "I": 0.215, "J": 0.422, "K": 0.459, "L": 0.374, "M": 0.691, "N": 0.508, "O": 0.462, "P": 0.437,
    "Q": 0.462, "R": 0.445, "S": 0.441, "T": 0.384, "U": 0.453, "V": 0.456, "W": 0.733, "X": 0.436,
    "Y": 0.43, "Z": 0.388, "0": 0.473, "1": 0.255, "2": 0.457, "3": 0.47, "4": 0.48, "5": 0.48,
    "6": 0.465, "7": 0.447, "8": 0.467, "9": 0.466, " ": 0.217, "-": 0.414, ".": 0.239,
}  # fmt: skip


def name_units(name):
    """A name's width in units, set in capitals at NAME with TRACK after each letter but the last."""
    caps = name.upper()
    return (sum(CAPS.get(c, 0.45) for c in caps) + TRACK * (len(caps) - 1)) * NAME


def _n(x):
    return f"{x:.3f}".rstrip("0").rstrip(".")


def _ink(state):
    """An arm's ink as presentation attributes, so the glyph reads with no stylesheet (words.css
    sets the same inks and wins over these)."""
    if state == "hollow":
        return f'fill="none" stroke="{MUTED}"'
    return f'fill="{COBALT if state == "key" else S.INK.get(state, MUTED)}"'


def glyph_svg(unit, states, names=None, cls="pie-svg", hrefs=None):
    """The glyph: a stem and one arm per state, top to bottom. unit: px per unit (3 on the board,
    1 in the search list). states: each arm's state (green, amber and red filled, hollow an
    outline; key the checks page's cobalt). names: each arm's name set in it (then the arms are
    long). hrefs: each arm (and its name) a link there, out of the tab order (the svg is hidden
    from assistive tech; the page's own text holds the same links)."""
    n = len(states)
    long = bool(names)
    over = 0 if long else GAP
    w, h = STEM + (LONG if long else SHORT), n * ARM + (n - 1) * GAP
    px = 1 / unit
    arms = []
    for i, state in enumerate(states):
        y = i * (ARM + GAP)
        klass = f'class="sl s{i + 1} {state}"'
        if state == "hollow":
            d = f"M{STEM} {_n(y + px / 2)}H{_n(w - px / 2)}V{_n(y + ARM - px / 2)}H{STEM}"
            arm = f'<path {klass} {_ink(state)} stroke-width="{_n(px)}" d="{d}"/>'
        else:
            arm = f'<rect {klass} {_ink(state)} x="{STEM}" y="{y}" width="{w - STEM}" height="{ARM}"/>'
        if long:
            x, base = STEM + PAD, y + (ARM + NAME * 0.8) / 2
            ink = MUTED if state == "hollow" else GROUND
            style = (f'font-family="Big Shoulders Display,system-ui,sans-serif" font-weight="800" '
                     f'font-size="{_n(NAME)}" letter-spacing="{_n(NAME * TRACK)}" fill="{ink}"')  # fmt: skip
            caps = e(names[i].upper())
            if state == "red":
                tw = name_units(names[i])
                text = (f'<text x="{_n(x)}" y="{_n(base)}" textLength="{_n(tw)}" {style}>{caps}</text>'
                        f'<rect x="{_n(x - 0.5)}" y="{_n(y + (ARM - STRIKE) / 2)}" '
                        f'width="{_n(tw + 1)}" height="{STRIKE}" fill="{GROUND}"/>')  # fmt: skip
            else:
                text = f'<text x="{_n(x)}" y="{_n(base)}" {style}>{caps}</text>'
            arm += f'<g class="t s{i + 1} {state}">{text}</g>'
        if hrefs:
            arm = f'<a href="{e(hrefs[i])}" tabindex="-1">{arm}</a>'
        arms.append(arm)
    stem = (
        f'<rect class="stem" fill="{COBALT}" y="{-over}" width="{STEM}" height="{h + 2 * over}"/>'
    )
    return (
        f'<svg class="{cls}" viewBox="0 {-over} {w} {h + 2 * over}" width="{_n(w * unit)}" '
        f'height="{_n((h + 2 * over) * unit)}" shape-rendering="crispEdges" aria-hidden="true" '
        f'focusable="false">{stem}{"".join(arms)}</svg>'
    )
