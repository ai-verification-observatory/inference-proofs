"""The inks and their contrast: `check_inks` reads the state inks from words.css, checks that the
chrome inks equal the ones computed with, and stops the build on a state step under 1.7:1, a text
pair under 4.5:1 or a Not stated slot under 3:1 on the ground. It keeps the ladder and the pairs
for the contrast table in README.md (outputs.write_readme).
"""

import re

from . import state as S
from .words import STATE_WORD

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
    css = dict(re.findall(r"--(\w+):\s*(#[0-9a-f]{6})", (S.HERE / "words.css").read_text()))
    S.INK = {s: css[s] for s in ("yes", "partly", "no")}
    for k, v in {"ground": GROUND, "paper": PAPER, "muted": MUTED, "rule": RULE,
                 "violet": VIOLET, "unstated": UNSTATED}.items():  # fmt: skip
        assert css.get(k) == v, f"words.css --{k} is {css.get(k)}, the build checks {v}"
    S.ladder, prev = [], UNSTATED
    S.ladder.append(("Not stated", f"`{UNSTATED}` (a grey, no hue)", f"{lum(UNSTATED):.3f}",
                     f"{ratio(UNSTATED, GROUND):.2f}:1", ""))  # fmt: skip
    for st in ("no", "partly", "yes"):
        step = ratio(S.INK[st], prev)
        # grey to red is told apart by hue, not lightness; the colour steps are told apart by both
        assert step >= 1.7 or prev == UNSTATED, st
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
    assert ratio(UNSTATED, GROUND) >= 3, (
        "a Not stated slot must stand off the ground (3:1 for shapes)"
    )
