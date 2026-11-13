"""The inks and their contrast: `check_inks` reads the state inks from words.css, checks that the
chrome inks equal the ones computed with, and stops the build on a state step under 1.7:1 (from
the ground to red to amber to green) or a text pair under 4.5:1. A hollow petal is an outline
in muted ink, never a fourth fill; a red petal the publisher's silence set is an outline in the
red ink, its name in red on the ground (on a lifted row the name takes paper, words.css, since red
on lift is under 4.5:1); a check's state squares use green and red. It keeps the ladder and the
pairs for the contrast table in README.md (outputs.write_readme).
"""

import re

from . import state as S

GROUND, PAPER, MUTED, RULE = "#0b0b0c", "#f1efe9", "#9b978e", "#6f6a62"
LINE = "#2a2927"  # the hairline between rows (words.css --line), never text
LIFT = "#17171a"  # the ground under the row in hand (words.css --lift)
COBALT = "#5b7bff"  # the brand ink: the band, page titles, the mark and the stems
STATES = ("red", "amber", "green")  # the filled petal states, darkest first


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
    S.INK = {s: css[s] for s in STATES}
    for k, v in {"ground": GROUND, "paper": PAPER, "muted": MUTED, "rule": RULE,
                 "cobalt": COBALT, "lift": LIFT}.items():  # fmt: skip
        assert css.get(k) == v, f"words.css --{k} is {css.get(k)}, the build checks {v}"
    S.ladder, prev = [], GROUND
    for st in STATES:
        step = ratio(S.INK[st], prev)
        assert step >= 1.7, st
        S.ladder.append((st, f"`{S.INK[st]}`", f"{lum(S.INK[st]):.3f}",
                         f"{ratio(S.INK[st], GROUND):.2f}:1", f"{step:.2f}:1"))  # fmt: skip
        prev = S.INK[st]
    S.pairs = [
        ("paper text on ground", PAPER, GROUND),
        ("muted text on ground", MUTED, GROUND),
        ("black text on cobalt", GROUND, COBALT),
        ("cobalt text on ground", COBALT, GROUND),
        ("paper text on lift", PAPER, LIFT),
        ("muted text on lift", MUTED, LIFT),
        ("cobalt text on lift", COBALT, LIFT),
    ]
    S.pairs += [(f"ground text on {s}", GROUND, S.INK[s]) for s in STATES]
    S.pairs.append(("red text on ground", S.INK["red"], GROUND))  # a silent red petal's name
    for name, a, b in S.pairs:
        assert ratio(a, b) >= 4.5, name
