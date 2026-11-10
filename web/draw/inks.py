"""The inks and their contrast: `check_inks` reads the state inks from words.css, checks that the
chrome inks equal the ones computed with, and stops the build on a state step under 1.7:1 (from
the ground up to Yes; Not stated is drawn as No) or a text pair under 4.5:1. It keeps the ladder and the pairs for the contrast table
in README.md (outputs.write_readme).
"""

import re

from . import state as S
from .words import STATE_WORD

# ------------------------------------------------------------------ inks
GROUND, PAPER, MUTED, RULE = "#0b0b0c", "#f1efe9", "#9b978e", "#6f6a62"
VIOLET = "#c45cff"


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
    css = dict(re.findall(r"--(\w+):\s*(#[0-9a-f]{6})", (S.HERE / "words.css").read_text()))
    S.INK = {s: css[s] for s in ("yes", "partly", "no")}
    for k, v in {"ground": GROUND, "paper": PAPER, "muted": MUTED, "rule": RULE,
                 "violet": VIOLET}.items():  # fmt: skip
        assert css.get(k) == v, f"words.css --{k} is {css.get(k)}, the build checks {v}"
    S.ladder, prev = [], GROUND
    for st in ("no", "partly", "yes"):
        step = ratio(S.INK[st], prev)
        # every step, the ground to No included, is told apart by lightness as well as hue, so the
        # three states hold under colour-vision deficiency and in greyscale (Not stated is drawn as No)
        assert step >= 1.7, st
        S.ladder.append((STATE_WORD[st], f"`{S.INK[st]}`", f"{lum(S.INK[st]):.3f}",
                         f"{ratio(S.INK[st], GROUND):.2f}:1", f"{step:.2f}:1"))  # fmt: skip
        prev = S.INK[st]
    S.pairs = [
        ("paper text on ground", PAPER, GROUND),
        ("muted text on ground", MUTED, GROUND),
        ("black text on violet", GROUND, VIOLET),
        ("violet text on ground", VIOLET, GROUND),
    ]
    S.pairs += [
        (f"ground text on {STATE_WORD[s]}", GROUND, S.INK[s]) for s in ("yes", "partly", "no")
    ]
    for name, a, b in S.pairs:
        assert ratio(a, b) >= 4.5, name
