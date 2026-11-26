"""What the Learn pages draw: the figures, the explorers and the measured blocks.

A page's text names one by `:::figure <id>`, `:::explore <id>` or `:::measured <id>` (learn.py).
Each is a function of no argument that returns markup:

- a figure is a static drawing made of words, boxes and lines in the site's inks;
- an explorer is a figure a reader can operate. Its markup reads in full without script (every
  step, every case); words.js then shows one state at a time and adds the controls. A worked
  example an explorer prints is computed here, by the same arithmetic the script runs;
- a measured block prints figures of the board file through `fig_html`, with their labels, and
  says so when the board holds none. Nothing here types a measured number.

No inline style: the Content-Security-Policy allows none (outputs.vercel_json). Accent frames
what a reader operates; the state inks stay with the states of a check (words.css).
"""

import re

from . import state as S
from .chrome import CHECKS_PAGE, counted, has, lead_figure, rung_of, standing
from .glossary import term
from .ladder import (
    BARE,
    baseline_html,
    fig_html,
    href,
    multiple_html,
    name_of,
    serving_words,
    whole_line,
    whole_note,
)
from .pages import STATEMENT_HEAD, gpus_words, statement_given
from .words import CHECK_NAME, FIGURE_HEAD, SEP, e, release_tail

FIGURES: dict = {}
EXPLORERS: dict = {}
MEASURED: dict = {}

# what a stage of the deployment page rests on today: the first word of a `:::stage` block
# (learn.py)
STAGE_WORD = {
    "measured": "Run on this site",
    "demonstrated": "Shown in research",
    "proposed": "Proposed, parts built",
    "outside": "Outside a proof's reach",
}


def drawn(table, name):
    """Register a drawing under the name a page's text uses for it."""

    def register(f):
        table[name] = f
        return f

    return register


def arrow(cls="ar"):
    """An arrow between two boxes: it points right on a wide screen, down on a phone."""
    return (f'<svg class="{cls}" viewBox="0 0 40 16" width="40" height="16" aria-hidden="true" '
            'focusable="false"><path d="M0 8h34M27 2l8 6-8 6" fill="none" stroke="currentColor" '
            'stroke-width="2"/></svg>')  # fmt: skip


# ------------------------------------------------------------------ figures
@drawn(FIGURES, "parties")
def parties():
    """Who holds what: the operator, the verifier and the relying party (a proof of inference).
    Each thing held or passed carries a key (`data-k`): pointing at one lights it wherever it is
    held or passed (words.js), so a reader sees what the verifier never holds."""

    def held(words, cls=""):
        return "".join(f'<li{f" class={cls}" if cls else ""}{f" data-k={k}" if k else ""}>'
                       f"{e(w)}</li>" for w, k in words)  # fmt: skip

    def card(name, role, holds, never=()):
        return (f'<div class="pc"><p class="pk">{e(name)}</p><p class="pd">{e(role)}</p>'
                f'<ul class="ph">{held(holds)}{held(never, "nv")}</ul></div>')  # fmt: skip

    def passes(*lines):
        return (f'<div class="pa">{arrow()}<ul>'
                + "".join(f"<li{f' data-k={k}' if k else ''}>{e(a)}<span>{e(b)}</span></li>"
                          for a, b, k in lines)
                + "</ul></div>")  # fmt: skip

    return (
        '<div class="pt3">'
        + card("The operator", "runs the model, makes the proof",
               (("the model's weights", "w"), ("the prompt", "p"), ("the reply", "r")))
        + passes(("the commitment", "once, before any request", "c"),
                 ("a proof", "for each reply to be checked", "f"))
        + card("The verifier", "a program anyone can run",
               (("the commitment and its public settings", "c"), ("the prompt", "p"),
                ("the reply, given or read from the proof", "r"), ("the proof", "f")),
               never=(("never the weights", "w"),))
        + passes(("accepts or refuses", "with no GPU and no weights", "v"))
        + card("The relying party", "acts on the verdict",
               (("the verdict", "v"), ("the statement it stands for", ""),
                ("the assumptions it rests on", "")))
        + "</div>"
    )  # fmt: skip


@drawn(FIGURES, "pipeline")
def pipeline():
    """One forward pass as its operations. A tag marks what a step multiplies: the committed
    weights (the three weight products) or other activations (attention's mix); a step with no
    tag needs more than additions and multiplications, which the note under the steps says."""
    steps = (
        ("Embed", "look up one row of a table per token", "other"),
        ("Normalise", "divide by a root mean square", "other"),
        ("Attention: project", "multiply by weight matrices", "linear"),
        (
            "Attention: mix",
            "multiply activations by activations, take a softmax, multiply again",
            "mixed",
        ),
        ("MLP: project", "multiply by weight matrices", "linear"),
        ("MLP: activate", "apply a fixed curve to each number", "other"),
        ("Unembed", "multiply by a weight matrix", "linear"),
        ("Choose", "take the largest of the vocabulary's scores", "other"),
    )
    # the tag of a step that multiplies; the other steps carry none
    tag = {"linear": "× committed weights", "mixed": "× activations"}
    rows = "".join(
        f'<li class="op {"other" if k == "mixed" else k}"><span class="o1">{e(name)}</span>'
        f'<span class="o2">{e(does)}</span>'
        + (f'<span class="o3">{e(tag[k])}</span>' if k in tag else "")
        + "</li>"
        for name, does, k in steps
    )
    return (f'<ol class="ops">{rows}</ol><p class="opn">The steps from Normalise to MLP: activate repeat once '
            "per layer. A step with no tag needs more than additions and multiplications.</p>")  # fmt: skip


SESSION_SAID = (
    "A session on a time axis: the commit step, then a generation phase where a system has one, "
    "then four groups of proofs released one after another. The steady interval runs from the "
    "release of the first group to the release of the last. The generation phase is counted in "
    "m. The whole session starts with the commit step."
)
SESSION_GROUPS = ("group 1", "group 2", "group 3", "group 4")


def session_svg(cls, w, h, at, said):
    """One layout of the session drawing: `at` places each mark (x of commit, generation and
    each group's release; y of the brackets, the boxes, and the labels of the four groups, commit
    and generation; and, where two labels over brackets would meet, the x each is centred on,
    "x" by label, else its bracket's middle), `said` its words by line."""
    c0, c1, g0, g1 = at["commit"] + at["gen"]
    rel, y = at["groups"], at["y"]
    box = f'y="{y["box"]}" height="36"'
    ticks = "".join(
        f'<g class="grp{" g1" if k == 0 else ""}"><rect x="{x - at["gw"]}" {box} '
        f'width="{at["gw"]}"/><text x="{x - at["gw"] / 2:g}" y="{y["lab"][k]}" '
        f'text-anchor="middle">{label}</text></g>'
        for k, (x, label) in enumerate(zip(rel, SESSION_GROUPS, strict=True))
    )

    def lines(cls, x, ys, words):
        return "".join(f'<text class="{cls}" x="{x:g}" y="{yy}" text-anchor="middle">{t}</text>'
                       for yy, t in zip(ys, words, strict=True))  # fmt: skip

    top, base, low = y["br"], y["box"] + 36, y["low"]
    mid = {"m": (g0 + g1) / 2, "steady": (rel[0] + rel[-1]) / 2} | at.get("x", {})
    return (
        f'<svg class="sx {cls}" viewBox="0 0 {w} {h}" role="img" aria-label="{SESSION_SAID}">'
        f'<line class="ax" x1="{c0}" y1="{base}" x2="{w - c0}" y2="{base}"/>'
        f'<rect class="scm" x="{c0}" {box} width="{c1 - c0}"/>'
        f'<text x="{(c0 + c1) / 2:g}" y="{y["lab"][4]}" text-anchor="middle">commit</text>'
        f'<rect class="sgn" x="{g0}" {box} width="{g1 - g0}"/>'
        f'<text x="{(g0 + g1) / 2:g}" y="{y["lab"][5]}" text-anchor="middle">generation</text>'
        f"{ticks}"
        f'<path class="br" d="M{g0} {top}v-10H{g1}v10"/>'
        + lines("bt", mid["m"], y["m"], said["m"])
        + f'<path class="br" d="M{rel[0]} {top}v-10H{rel[-1]}v10"/>'
        + lines("bt", mid["steady"], y["steady"], said["steady"])
        + f'<path class="br2" d="M{c0} {low}v10H{rel[-1]}v-10"/>'
        + lines("bt2", (c0 + rel[-1]) / 2, y["whole"], said["whole"])
        + "</svg>"
    )


@drawn(FIGURES, "session")
def session():
    """One session on a time axis: commit, a generation phase where a system has one, the first
    release group and the later groups, and the GPU time that makes m (RFC-0018 CO-1 to CO-3).
    Two layouts of one drawing: a wide one, and on a phone a narrow one at its own size, its
    long words on two lines, the names under the axis on two rows, in turn, and the two labels
    over the brackets drawn apart (each is wider than its bracket: measured in Chrome, "counted
    in m" 101 units, "the GPU time behind m" 177 of the 328)."""
    wide = session_svg(
        "sxw", 681, 190,
        {"commit": (1, 101), "gen": (113, 223), "groups": (301, 401, 501, 601), "gw": 26,
         "y": {"br": 52, "box": 72, "lab": (130,) * 6, "low": 150, "m": (30,),
               "steady": (30,), "whole": (180,)}},
        {"m": ("generation: counted in m",), "steady": ("steady interval: the GPU time behind m",),
         "whole": ("whole session: from the start of the commit step",)},
    )  # fmt: skip
    narrow = session_svg(
        "sxn", 328, 206,
        {"commit": (4, 54), "gen": (62, 122), "groups": (160, 206, 252, 298), "gw": 18,
         "y": {"br": 52, "box": 64, "lab": (120, 138, 120, 138, 120, 138), "low": 150,
               "m": (14, 30), "steady": (14, 30), "whole": (178, 194)},
         "x": {"m": 72, "steady": 238}},
        {"m": ("generation:", "counted in m"), "steady": ("steady interval:", "the GPU time behind m"),
         "whole": ("whole session: from the start", "of the commit step")},
    )  # fmt: skip
    return f'<div class="tw">{wide}{narrow}</div>'


# ------------------------------------------------------------------ explorers
# ---- a random check of a matrix product (Freivalds) and a sumcheck of an inner product: the
# worked examples, by the arithmetic words.js runs. The sentences words.js prints are the
# templates here ({name} filled in), so the page reads the same with script and without.
P = 97  # the small prime field of the worked examples: small enough that a lie sometimes survives
FA = ((2, 0, 1), (1, 3, 0), (0, 1, 2))
FB = ((1, 2, 0), (0, 1, 1), (3, 0, 1))
WRONG = (1, 2, 1)  # row, column, and what is added there to make the claimed product false
RC_WORDS = {
    "diff": "different: the claimed product is refused",
    "miss": "equal: this draw misses the wrong entry",
    "true": "equal: the claimed product is the true one",
    "tally": "{n} {draws} from {set} so far, {k} of them refused the claimed product.",
    "draw": "draw",  # {draws} after a count of one
    "draws": "draws",
    "bits": "Draw r from 0 and 1",
    "field": "Draw r from 0 to {top}",
    "many": "Draw {n} times from 0 to {top}",
    "manybits": "Draw {n} times from 0 and 1",
    "setbits": "0 and 1",
    "setfield": "0 to {top}",
    "wrong": "One entry of the claimed product is wrong",
}
RC_RUNS = 1000  # how many draws each "many" button makes (from the field, from 0 and 1)


def data_words(words):
    return " ".join(f'data-w-{k}="{e(v)}"' for k, v in words.items())


def fill(template, **values):
    return template.format(**values)


def matmul(a, b):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(len(b))) % P
                       for j in range(len(b[0]))) for i in range(len(a)))  # fmt: skip


def matvec(a, v):
    return tuple(sum(x * y for x, y in zip(row, v, strict=True)) % P for row in a)


def claimed(honest):
    """The product the prover claims: A·B, or A·B with one entry changed."""
    c = [list(row) for row in matmul(FA, FB)]
    if not honest:
        i, j, d = WRONG
        c[i][j] = (c[i][j] + d) % P
    return tuple(tuple(row) for row in c)


def random_check(r, honest=False):
    """One random check of the claimed product with the vector r: A·(B·r) against C·r."""
    left, right = matvec(FA, matvec(FB, r)), matvec(claimed(honest), r)
    return {"r": r, "left": left, "right": right, "equal": left == right}


def grid(m, mark=None, cls="mx"):
    """A matrix as a table of its entries (one marked: the changed one)."""
    trs = "".join(
        "<tr>" + "".join(
            f'<td{" class=bad" if mark == (i, j) else ""}>{v}</td>' for j, v in enumerate(row)
        ) + "</tr>"
        for i, row in enumerate(m)
    )  # fmt: skip
    return f'<table class="{cls}"><tbody>{trs}</tbody></table>'


def column(v, cls="mx"):
    return grid(tuple((x,) for x in v), cls=cls)


def named(label, matrix):
    """A matrix and its name as one group: a line that wraps never leaves a name without it."""
    return f'<div class="mxg"><span class="lb">{e(label)}</span>{matrix}</div>'


def flat(m):
    """A matrix as the script reads it: its rows, entries separated by spaces, rows by commas."""
    return ",".join(" ".join(str(v) for v in row) for row in m)


@drawn(EXPLORERS, "random-check")
def random_check_html():
    """A·B against a claimed C with one wrong entry: two draws worked in full, one that catches
    the change and one that misses it. With script: draw r, from bits or from the whole field,
    once or RC_RUNS times, each set with its own count of refusals."""
    i, j, _ = WRONG

    def draw(r):
        got = random_check(r)
        verdict = RC_WORDS["miss"] if got["equal"] else RC_WORDS["diff"]
        return (f'<div class="dr"><div class="eq">{named("r", column(got["r"]))}'
                f'{named("A·(B·r)", column(got["left"]))}{named("C·r", column(got["right"]))}</div>'
                f'<p class="vd">{e(verdict)}</p></div>')  # fmt: skip

    data = (f'data-a="{flat(FA)}" data-b="{flat(FB)}" data-c="{flat(claimed(False))}" '
            f'data-ok="{flat(claimed(True))}" data-p="{P}" data-runs="{RC_RUNS}" '
            f"{data_words(RC_WORDS)}")  # fmt: skip
    shown_c = f'<div class="xcl">{grid(claimed(False), mark=(i, j))}</div>'
    return (
        f'<div class="xpl" data-x="random-check" {data}>'
        f'<div class="eq mm">{named("A", grid(FA))}{named("B", grid(FB))}'
        f"{named('claimed C', shown_c)}"
        f'<span class="lv">arithmetic modulo {P}</span></div>'
        f'<div class="xo">{draw((1, 0, 1))}{draw((1, 1, 0))}</div></div>'
    )


# the sumcheck of an inner product <a, b> of two vectors of four numbers, over the field of P
# elements: two rounds, a polynomial of degree two in each (three values sent)
SA = (2, 7, 1, 8)
SB = (3, 1, 4, 1)
CHALLENGES = (5, 11)  # the worked example's two random draws
LIE = 1  # what the lying prover adds to the true result
SC_WORDS = {
    "honest": "An honest prover claims the result {claim}",
    "lying": "A lying prover claims the result {claim}",
    "round": "Round {k}",
    "sent": "{s0}, {s1}, {s2}",
    "check": "{s0} + {s1} = {sum}, the running claim",
    "last": "a(r)·b(r) = {a} · {b} = {final}, and the last claim is {last}: {verdict}",
    "accepted": "accepted",
    "refused": "refused",
    "lies": "The prover lies about the result",
    "redraw": "Draw new challenges",
    "many": "Run {n} times",
    "runs": "Over {n} runs with fresh challenges the verifier accepted {k}.",
}


def fold(v, r):
    """The table of a multilinear polynomial with its first variable set to r."""
    half = len(v) // 2
    return tuple(((1 - r) * v[k] + r * v[half + k]) % P for k in range(half))


def round_poly(a, b):
    """s(0), s(1), s(2) of s(X) = sum over the other variables of a(X, ..)·b(X, ..)."""
    return tuple(sum(x * y for x, y in zip(fold(a, t), fold(b, t), strict=True)) % P
                 for t in (0, 1, 2))  # fmt: skip


def at(s, r):
    """The polynomial of degree two through (0, s0), (1, s1), (2, s2), at r."""
    inv2 = pow(2, -1, P)
    l0 = (r - 1) * (r - 2) * inv2
    l1 = -r * (r - 2)
    l2 = r * (r - 1) * inv2
    return (s[0] * l0 + s[1] * l1 + s[2] * l2) % P


def sumcheck(challenges=CHALLENGES, lie=0):
    """The transcript of one run: the claim, then per round the three values sent, the running
    claim their first two must sum to, the challenge and the next claim; then the final check
    against a(r)·b(r). A lying prover adds `lie` to the result and then, each round, sends the
    s(0) that makes the round's check pass, its other two values unchanged."""
    a, b = SA, SB
    claim = (sum(x * y for x, y in zip(a, b, strict=True)) + lie) % P
    rounds, running = [], claim
    for r in challenges:
        s = list(round_poly(a, b))
        s[0] = (running - s[1]) % P  # honest: the true s(0); lying: the value that passes
        nxt = at(s, r)
        rounds.append({"s": tuple(s), "claim": running, "r": r, "next": nxt})
        running, a, b = nxt, fold(a, r), fold(b, r)
    final = a[0] * b[0] % P
    return {"claim": claim, "rounds": rounds, "a": a[0], "b": b[0], "final": final,
            "accepted": final == running}  # fmt: skip


def transcript(run, who):
    # a variable stays on the line of the words it ends
    heads = ("Running claim", "Prover sends s(0),\u00a0s(1),\u00a0s(2)", "Verifier checks",
             "Verifier draws\u00a0r", "New claim\u00a0s(r)")  # fmt: skip
    rows = ""
    for k, rd in enumerate(run["rounds"], start=1):
        s0, s1, s2 = rd["s"]
        tds = (rd["claim"], e(fill(SC_WORDS["sent"], s0=s0, s1=s1, s2=s2)),
               e(fill(SC_WORDS["check"], s0=s0, s1=s1, sum=(s0 + s1) % P)), rd["r"], rd["next"])  # fmt: skip
        rows += (f'<tr><th scope="row">{e(fill(SC_WORDS["round"], k=k))}</th>'
                 + "".join(f'<td data-l="{e(h)}">{v}</td>' for h, v in zip(heads, tds, strict=True))
                 + "</tr>")  # fmt: skip
    last = fill(SC_WORDS["last"], a=run["a"], b=run["b"], final=run["final"],
                last=run["rounds"][-1]["next"],
                verdict=SC_WORDS["accepted" if run["accepted"] else "refused"])  # fmt: skip
    return (
        f'<div class="tr"><p class="vd">{e(fill(SC_WORDS[who], claim=run["claim"]))}</p>'
        '<div class="tw"><table class="rt lt mt"><thead><tr><td></td>'
        + "".join(f'<th scope="col">{e(h)}</th>' for h in heads)
        + f'</tr></thead><tbody>{rows}</tbody></table></div><p class="vl">{e(last)}</p></div>'
    )


@drawn(EXPLORERS, "sumcheck")
def sumcheck_html():
    """Two runs on the same draws, in full: first a prover that claims a result off by one,
    then an honest one. With script: the lying run first; choose the prover, draw again, run many
    times."""
    vectors = (f'<div class="eq mm"><span class="lb">a, the weights</span>{grid((SA,))}'
               f'<span class="lb">b, the activations</span>{grid((SB,))}'
               f'<span class="lv">arithmetic modulo {P}</span></div>')  # fmt: skip
    data = (f'data-a="{flat((SA,))}" data-b="{flat((SB,))}" data-p="{P}" data-lie="{LIE}" '
            f'data-runs="1000" {data_words(SC_WORDS)}')  # fmt: skip
    return (f'<div class="xpl" data-x="sumcheck" {data}>{vectors}<div class="xo">'
            f'{transcript(sumcheck(lie=LIE), "lying")}{transcript(sumcheck(), "honest")}'
            "</div></div>")  # fmt: skip


# ------------------------------------------------------------------ measured blocks
def release_words():
    rel = S.V["release"]
    if not rel:
        return "No board yet"
    return f"From the board, release {release_tail(rel)}"


def rows_words(found):
    """The board in one sentence: how many rows, how many passed, and how many sessions stand
    behind them against the number the level asks for."""
    n, passed = len(found), sum(1 for _, row in found if row["passed"])
    slots = S.V["constants"]["slots"]
    short = sum(1 for _, row in found if len(row["sessions"]) < slots)
    said = f"{n} {'row' if n == 1 else 'rows'} so far: {passed} passed all six checks."
    if short:
        who = "It rests" if n == 1 else f"{short} of them rest{'s' if short == 1 else ''}"
        said += f" {who} on fewer than the {slots} sessions a position needs."
    return said


def row_figure(row):
    """A row's multiple with, under it, what it counted and n, once (its two parts are the system
    page's, CO-7). The line under the whole breaks before its dot, so "n" keeps its dot."""
    return multiple_html(row).replace(
        f'<span class="sep">{SEP}</span>', '<span class="sep"> ·\u00a0</span>'
    )


@drawn(MEASURED, "rows")
def measured_rows():
    """Every row of the board, one table per model (nothing is ranked across models):
    system, standing, multiple of serving, check time and proof size per reply. What the
    figures counted and n are said once, under the multiple; the rest print bare, their labels
    in their title. A row with no position is set in the muted ink, as on the ladder."""
    found = [(rung, row) for rung in S.V["rungs"] for row in rung["rows"]]
    if not found:
        return ('<p class="none">No system has a row yet. The <a href="/">ladder</a> shows each '
                "one as it is run.</p>")  # fmt: skip
    heads = ("System", "Standing", FIGURE_HEAD["multiple"], FIGURE_HEAD["check-time"],
             FIGURE_HEAD["proof-size"])  # fmt: skip
    ths = "".join(f'<th scope="col">{h}</th>' for h in heads)

    def tr(row):
        return (
            "<tr>"
            f'<th scope="row"><a href="{e(href(row))}">{e(name_of(row))}</a></th>'
            f'<td data-l="{heads[1]}">{e(standing(row))}</td>'
            f'<td data-l="{heads[2]}">{row_figure(row)}</td>'
            f'<td data-l="{heads[3]}">'
            f"{fig_html(row['figures']['verify_seconds_per_reply'], counted(row), sub=BARE)}</td>"
            f'<td data-l="{heads[4]}">'
            f"{fig_html(row['figures']['proof_bytes_per_reply'], counted(row), sub=BARE)}</td></tr>"
        )

    tables = "".join(
        f'<div class="tw"><table class="rt mt"><caption class="bm">On {e(rung["model"])}</caption>'
        f'<thead><tr>{ths}</tr></thead><tbody>{"".join(tr(row) for row in rung["rows"])}</tbody>'
        "</table></div>"
        for rung in S.V["rungs"] if rung["rows"]
    )  # fmt: skip
    return (f'<p class="fl">{e(release_words())}</p><p class="ms-s">{e(rows_words(found))}</p>'
            f"{tables}")  # fmt: skip


def serving_line(rung):
    """A model's serving baseline in one line (CO-4): how it was served, then its GPU-seconds per
    reply, bare (the words before it say full load); with none, why."""
    b = rung["baseline"]
    if (
        b is None
        or b["gpu_seconds_per_reply"] is None
        or b["gpu_seconds_per_reply"]["value"] is None
    ):
        return baseline_html(rung)
    return (f'<p class="rb"><span class="k">Serving</span> {e(serving_words(b))}: '
            f'{fig_html(b["gpu_seconds_per_reply"], sub=BARE)}</p>')  # fmt: skip


@drawn(MEASURED, "baselines")
def measured_baselines():
    """Each model's serving baseline in one line (CO-4)."""
    lines = "".join(f'<div class="bl2"><p class="bm">{e(rung["model"])}</p>{serving_line(rung)}'
                    "</div>" for rung in S.V["rungs"])  # fmt: skip
    return f'<p class="fl">{e(release_words())}</p>{lines}'


# what a relying party supplies to each system's verifier (deployment page): the Statement
# block's rows a verifier does not check itself, by system (RFC-0018 SI-3, amended 2026-11-15)
SUPPLY_HEAD = {"verifier": "The verifier, pinned", "commit_record": "The commitment, from a register",
               "request": "The prompt, and the reply where it is given",
               "decoding": "The decoding rule", "unchecked": "What no call checks"}  # fmt: skip


@drawn(MEASURED, "supplies")
def measured_supplies():
    """Per system with a Statement block: the verifier it runs at its row's commit, then what
    the claim card says of the commitment, the request, the decoding rule and what no call
    checks, each item what the records show is given and the card's words, linked."""
    found = [row for rung in S.V["rungs"] for row in rung["rows"] if row.get("statement")]
    if not found:
        return (
            '<p class="none">No system has a claim card that says what its verifier is given.</p>'
        )
    heads = ["", *(name_of(row) for row in found)]

    def cell(row, rid):
        st = row["statement"]
        if rid == "verifier":
            at = f" at <code>{e(row['commit'][:7])}</code>" if row["commit"] else ""
            pin = S.V["systems"][row["system"]].get("pin")
            pr = f', <a href="{e(pin["url"])}">pull request #{pin["pull"]:,}</a>' if pin else ""
            return f"<code>{e(st['program'])}</code>{at}{pr}"
        r = next(x for x in st["rows"] if x["id"] == rid)
        said = ('<span class="na">not stated</span>' if r["said"] is None else
                "".join(f'<p class="stc">{e(q["text"])} <a href="{e(q["url"])}">source</a></p>'
                        for q in r["said"]))  # fmt: skip
        given = statement_given(row, st, rid)
        return (f"<p>{given}</p>" if given else "") + said

    ths = "".join(f'<th scope="col">{e(h)}</th>' for h in heads)
    trs = "".join(
        f'<tr><th scope="row">{e(SUPPLY_HEAD[rid])}</th>'
        + "".join(f'<td data-l="{e(name_of(row))}">{cell(row, rid)}</td>' for row in found)
        + "</tr>"
        for rid in SUPPLY_HEAD
    )
    assert set(SUPPLY_HEAD) - {"verifier"} <= set(STATEMENT_HEAD)
    return (
        f'<p class="fl">{e(release_words())}</p><div class="tw"><table class="rt mt">'
        f"<thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table></div>"
    )


# ------------------------------------------------------------------ how a check works
# The drawings of the page "How a check works" (web/learn/how-a-check-works.md): the request,
# who holds what, the six checks and the fraction behind the headline figure. Each is SVG in the
# site's inks with its words as text: a token or a weight is a cell in rule ink, the one we change
# is filled in paper, a thing taken away is dashed. The state inks stay with states (words.css),
# so none is used here. The request's sizes are the level's (`S.V["request"]`), the slots its
# constants, the fraction's figures the board's; no number is typed.
def tx(x, y, words, cls="", anchor=""):
    """A line of words at (x, y); `anchor` "middle" or "end" sets where (x, y) is on it."""
    c = f' class="{cls}"' if cls else ""
    a = f' text-anchor="{anchor}"' if anchor else ""
    return f'<text x="{x:g}" y="{y:g}"{c}{a}>{e(words)}</text>'


def cells(x, y, n, size, gap=2, changed=(), after=None, h=None):
    """A row of `n` cells from (x, y): the `changed` ones filled in paper; from `after` on, the
    cells are drawn in the line ink (past the first difference, which nothing counts)."""
    out = ""
    for k in range(n):
        cls = "x" if k in changed else "o" if after is not None and k > after else "c"
        out += (f'<rect class="{cls}" x="{x + k * (size + gap):g}" y="{y:g}" width="{size:g}" '
                f'height="{h or size:g}"/>')  # fmt: skip
    return out


def box(x, y, w, h, words=(), cls="b"):
    """A box with its words centred, one line each."""
    mid, top = x + w / 2, y + h / 2 - 7 * (len(words) - 1) + 4
    return (f'<rect class="{cls}" x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}"/>'
            + "".join(tx(mid, top + 14 * k, t, "p", "middle") for k, t in enumerate(words)))  # fmt: skip


def go(x1, y1, x2, y2):
    """An arrow from (x1, y1) to (x2, y2), level or upright, its head at the end."""
    if y1 == y2:
        s = 1 if x2 > x1 else -1
        head = f"M{x2 - 7 * s:g} {y2 - 5:g}L{x2:g} {y2:g}L{x2 - 7 * s:g} {y2 + 5:g}"
    else:
        s = 1 if y2 > y1 else -1
        head = f"M{x2 - 5:g} {y2 - 7 * s:g}L{x2:g} {y2:g}L{x2 + 5:g} {y2 - 7 * s:g}"
    return f'<path class="a" d="M{x1:g} {y1:g}L{x2:g} {y2:g}{head}"/>'


def hc_svg(cls, w, h, said, body):
    return (f'<svg class="hc {cls}" viewBox="0 0 {w} {h}" role="img" aria-label="{e(said)}">'
            f"{body}</svg>")  # fmt: skip


def wide_narrow(wide, narrow):
    """Two layouts of one drawing: the wide one, and on a phone the narrow one (words.css)."""
    return f'<div class="hcw">{wide.replace("hc ", "hc hcl ", 1)}{narrow.replace("hc ", "hc hcs ", 1)}</div>'


@drawn(FIGURES, "request")
def request_figure():
    """The request (RFC-0018 Terms, PR-1, PR-2): the prompt's and the reply's tokens as two rows
    of cells, what sets each, and that it is the same for every system."""
    r = S.V["request"]
    p, o, how = r["prompt_tokens"], r["output_tokens"], r["decoding"]
    said = (f"The request: a prompt of {p:,} tokens, then a reply of {o:,} tokens, {how}. "
            "The prompts are cut from public books with a seed from a public randomness beacon. "
            "Every system gets the same request, on every model.")  # fmt: skip
    prompt_words = ("cut from public books with a seed", "from a public randomness beacon")
    reply_words = (f"{how}: the model's top token at", "each step, and no end token stops it")
    same = "the same request for every system, on every model"
    wide = hc_svg(
        "hreq", 980, 150, said,
        tx(0, 16, f"Prompt: {p:,} tokens", "p") + cells(0, 28, 32, 12, h=24)
        + "".join(tx(0, 76 + 16 * k, t) for k, t in enumerate(prompt_words))
        + go(452, 40, 494, 40)
        + tx(500, 16, f"Reply: {o:,} tokens", "p") + cells(500, 28, 32, 12, h=24)
        + "".join(tx(500, 76 + 16 * k, t) for k, t in enumerate(reply_words))
        + '<path class="k" d="M0 112v8H946v-8"/>' + tx(473, 142, same, "p", "middle"),
    )  # fmt: skip
    narrow = hc_svg(
        "hreq", 360, 300, said,
        tx(0, 16, f"Prompt: {p:,} tokens", "p") + cells(0, 28, 20, 16)
        + "".join(tx(0, 68 + 17 * k, t) for k, t in enumerate(prompt_words))
        + go(8, 100, 8, 124)
        + tx(0, 146, f"Reply: {o:,} tokens", "p") + cells(0, 158, 20, 16)
        + "".join(tx(0, 198 + 17 * k, t) for k, t in enumerate(reply_words))
        + '<path class="k" d="M0 234v8H358v-8"/>'
        + tx(0, 266, "the same request for every", "p") + tx(0, 283, "system, on every model", "p"),
    )  # fmt: skip
    return wide_narrow(wide, narrow)


FLOW_SAID = (
    "It takes three steps. First, the prover commits to the weights and sends the commitment "
    "once, before any prompt. Then the prover runs the model on the prompt and proves the reply. "
    "Finally, the verifier checks the proof against the commitment, the prompt and the reply, and "
    "accepts or refuses it, with no weights and no GPU. The prover holds the weights, but the "
    "verifier never does."
)
FLOW_STEPS = ("1  Commit to the weights", "2  Generate and prove", "3  Verify")


@drawn(FIGURES, "flow")
def flow_figure():
    """Who holds what at each step: the prover's lane and the verifier's, the commitment sent
    once, the reply and its proof sent for each prompt, the verdict. On a phone the lanes are two
    columns and the steps run down."""
    wide = hc_svg(
        "hflow", 1000, 300, FLOW_SAID,
        "".join(tx(x, 16, s, "p") for x, s in zip((160, 420, 740), FLOW_STEPS, strict=True))
        + '<path class="k" d="M0 30H1000"/><path class="l" d="M0 156H1000"/>'
        + tx(0, 66, "Prover", "d") + tx(0, 90, "holds the weights")
        + tx(0, 200, "Verifier", "d") + tx(0, 224, "never holds") + tx(0, 240, "the weights")
        # 1: the weights, and their commitment sent down once
        + box(160, 50, 200, 36, ("the weights",)) + go(260, 86, 260, 190)
        + tx(270, 120, "sent once,") + tx(270, 136, "before any prompt")
        + box(160, 190, 200, 36, ("the commitment",))
        # 2: the prompt in, the model's reply and proof out, sent down
        + box(420, 50, 90, 36, ("prompt",)) + go(510, 68, 540, 68)
        + box(540, 50, 160, 36, ("reply and proof",)) + tx(420, 106, "the model runs, then proves")
        + go(660, 86, 660, 190) + tx(670, 136, "for each prompt")
        + box(520, 190, 180, 36, ("prompt, reply, proof",))
        # 3: the verifier, given all of it, gives its verdict
        + tx(740, 176, "no weights, no GPU") + go(700, 208, 740, 208)
        + '<path class="a" d="M260 226V276H790V234M785 233l5-7 5 7"/>'
        + box(740, 190, 130, 36, ("the verifier",)) + go(870, 208, 900, 208)
        + tx(906, 204, "accepts", "p") + tx(906, 220, "or refuses", "p"),
    )  # fmt: skip
    narrow = hc_svg(
        "hflow", 360, 470, FLOW_SAID,
        tx(0, 22, "Prover", "d") + tx(190, 22, "Verifier", "d")
        + tx(0, 42, "holds the weights") + tx(190, 42, "never holds them")
        + '<path class="k" d="M0 56H360"/>'
        + tx(0, 80, FLOW_STEPS[0], "p")
        + box(0, 92, 170, 36, ("the weights",)) + go(172, 110, 188, 110)
        + box(190, 92, 170, 36, ("the commitment",))
        + tx(190, 146, "sent once, before") + tx(190, 163, "any prompt")
        + '<path class="l" d="M0 180H360"/>'
        + tx(0, 204, FLOW_STEPS[1], "p")
        + box(0, 216, 170, 36, ("reply and proof",)) + go(172, 234, 188, 234)
        + box(190, 212, 170, 44, ("prompt, reply", "and proof"))
        + tx(0, 270, "the model runs on") + tx(0, 287, "the prompt, then proves")
        + tx(190, 270, "for each prompt")
        + '<path class="l" d="M0 304H360"/>'
        + tx(0, 328, FLOW_STEPS[2], "p")
        + box(190, 340, 170, 36, ("the verifier",)) + go(275, 376, 275, 400)
        + tx(275, 418, "accepts or refuses", "p", "middle")
        + tx(0, 446, "from the commitment, prompt, reply and")
        + tx(0, 463, "proof, with no weights and no GPU"),
    )  # fmt: skip
    return wide_narrow(wide, narrow)


def verdict(*lines):
    """The outcome a check needs, at the right of its picture, after an arrow."""
    top = 60 - 8 * (len(lines) - 1) + 4
    return go(208, 60, 238, 60) + "".join(tx(246, top + 16 * k, t, "p")
                                          for k, t in enumerate(lines))  # fmt: skip


def check_pictures():
    """Each check's picture (340 by 120 units), by its id: what we change and what must come
    of it."""
    slots = S.V["constants"]["slots"]
    rows = "".join(tx(0, 26 + 30 * k, f"session {k + 1}") + cells(82, 16 + 30 * k, 8, 12)
                   for k in range(slots))  # fmt: skip
    grid = "".join(cells(0, 22 + 15 * r, 13, 12, 3, changed=(6,) if r == 2 else ())
                   for r in range(5))  # fmt: skip
    reply = "".join(tx(0, 32 + 30 * k, w) + cells(64, 22 + 30 * k, 10, 12, changed=(c,))
                    for k, (w, c) in enumerate((("first", 0), ("inside", 5), ("last", 9))))  # fmt: skip
    return {
        "run": (
            f"{slots} sessions from a cold start, every reply proved and accepted",
            rows + verdict("every proof", "accepted"),
        ),
        "model": (
            "A grid of weights with one changed: no accepted proof",
            tx(0, 12, "weights, one changed") + grid + verdict("no accepted", "proof"),
        ),
        "prompt": (
            "A row of prompt tokens with one changed: the proof is refused",
            tx(0, 40, "prompt tokens, one changed")
            + cells(0, 50, 13, 13, changed=(8,))
            + verdict("refused"),
        ),
        "reply": (
            "Three rows of reply tokens, the first, one inside and the last changed: each "
            "proof refused",
            reply + verdict("each", "refused"),
        ),
        "no_weight_file": (
            "The verifier with no model file and no GPU: it still reaches its verdict",
            box(0, 34, 96, 52, ("the", "verifier"))
            + box(108, 22, 92, 32, ("no model",), "d")
            + box(108, 66, 92, 32, ("no GPU",), "d")
            + verdict("a verdict", "reached"),
        ),
        "fidelity": (
            "The original's reply and the proved reply, token by token: we count the leading "
            "tokens that match, up to the first difference, and the proved replies must match "
            "more than the bar",
            '<path class="k" d="M72 22v-6H140v6"/>'
            + tx(72, 10, "matched leading tokens")
            + tx(0, 40, "original")
            + cells(72, 30, 9, 12, after=4)
            + tx(0, 72, "proved")
            + cells(72, 62, 9, 12, changed=(5,), after=5)
            + tx(72, 100, "then nothing counts")
            + verdict("above", "the bar"),
        ),
    }


# what each check does and what it needs (RFC-0018, the six checks), for a reader with no context;
# the rules in full are the checks page's (`CHECK_HELD`), which each name links
CHECK_DOES = {
    "run": ("We run", "the publisher's prover honestly from a cold start as published",
            "each of the {slots} slots produces a complete session with an accepted proof for "
            "every reply"),
    "model": ("We change", "a single weight after the prover commits to the original weights",
              "no proof is accepted against the original commitment, and an honest proof is "
              "rejected against the modified weights' commitment"),
    "prompt": ("We change", "one prompt token at a seeded position",
               "the verifier rejects the proof"),
    "reply": ("We change", "the first, last, or one interior reply token, one at a time",
              "the verifier rejects every modified proof, and every honest proof covers all "
              "{reply} reply tokens"),
    "no_weight_file": ("We remove", "the model files and GPU access from the verifier",
                       "the verifier still reaches every verdict without them"),
    "fidelity": ("We compare", "each proved reply against the original model's reply token by "
                 "token from the start",
                 "proved replies match more leading tokens than the bar (a deliberately damaged "
                 "copy), verified by a paired statistical test"),
}  # fmt: skip


# the terms a panel's words link to the glossary, at their first use (D1): (words, entry)
NEED_TERMS = (("slots", "Slot"), ("session", "Session"), ("the bar", "Bar"))


def need_html(words):
    """A panel's "passes when" words, escaped, each term NEED_TERMS names linked once."""
    out = e(words)
    for w, entry in NEED_TERMS:
        out = re.sub(rf"\b{re.escape(w)}\b", lambda _m, w=w, entry=entry: term(w, entry), out,
                     count=1)  # fmt: skip
    return out


@drawn(FIGURES, "checks")
def checks_figure():
    """The six checks as six panels, in the board's order: each its name (linked to its rule),
    a picture of what we change and what must come of it, and the two in words."""
    fill = {"slots": S.V["constants"]["slots"], "reply": f"{S.V['request']['output_tokens']:,}"}
    pics = check_pictures()
    panels = ""
    for c in S.V["checks"]:
        said, body = pics[c]
        how, what, need = CHECK_DOES[c]
        panels += (
            f'<div class="hcp"><p class="hcn"><a href="{CHECKS_PAGE}#{c}">{e(CHECK_NAME[c])}</a>'
            f'</p>{hc_svg("hchk", 340, 120, said, body)}<dl class="hcd">'
            f"<div><dt>{e(how)}</dt><dd>{e(what)}</dd></div>"
            f"<div><dt>Passes when</dt><dd>{need_html(need.format(**fill))}</dd></div></dl></div>"
        )
    return f'<div class="hcg">{panels}</div>'


# the figure each multiple is over (CO-1, CO-4, CO-5): which GPU time a row's printed multiple
# divides, by the multiple's key in the row's figures
OVER = {"session_multiple": "session_gpu_seconds_per_reply",
        "multiple": "steady_gpu_seconds_per_reply",
        "further_reply_multiple": "further_reply_gpu_seconds"}  # fmt: skip
# what the proved side of the fraction counted, by the multiple's key (CO-9, Q55: a further reply)
OVER_WORDS = {"multiple": "steady state", "further_reply_multiple": "further reply"}


def fraction_row():
    """The row the fraction is drawn for: the frontier's first row (OR-6), else the first row
    with a printed multiple; None while the board has none."""
    front = S.V["frontier"]
    found = [*(front["rows"] if front else ()),
             *(row for rung in S.V["rungs"] for row in rung["rows"])]  # fmt: skip
    for row in found:
        _, f, key = lead_figure(row)
        b = rung_of(row)["baseline"]
        if has(f) and b and has(b["gpu_seconds_per_reply"]) and has(row["figures"][OVER[key]]):
            return row
    return None


def fraction_parts(row):
    """The row's printed multiple and the two figures it is the ratio of: (over, under,
    multiple, key)."""
    _, f, key = lead_figure(row)
    return row["figures"][OVER[key]], rung_of(row)["baseline"]["gpu_seconds_per_reply"], f, key


@drawn(MEASURED, "fraction")
def measured_fraction():
    """Cost vs serving as one drawn fraction (CO-5): a proved reply's GPU-seconds over a served
    reply's, each the board's figure with its labels, and the multiple they make."""
    row = fraction_row()
    if row is None:
        return ('<p class="none">No system has a figure yet. The <a href="/">ladder</a> shows '
                "each one as it is run.</p>")  # fmt: skip
    over, under, f, key = fraction_parts(row)
    n = counted(row)
    rung = rung_of(row)
    top = (f'<p class="hck">A proved reply</p>{fig_html(over, n, sub=BARE)}'
           f'<p class="hcm">{e(name_of(row))} on {e(rung["model"])}, {e(gpus_words(row))}: '
           f"{e(whole_line(row, n) if key == 'session_multiple' else OVER_WORDS[key])}</p>")  # fmt: skip
    low = (f'<p class="hck">Serving it</p>{fig_html(under, sub=BARE)}'
           f'<p class="hcm">{e(serving_words(rung["baseline"]))}</p>')  # fmt: skip
    whole = fig_html(f, n, sub=BARE, note=whole_note(row, key))
    return (f'<p class="fl">{e(release_words())}</p><div class="hcf">'
            f'<div class="hcq"><div class="hct">{top}</div>'
            '<svg class="hcb" viewBox="0 0 100 4" preserveAspectRatio="none" aria-hidden="true" '
            'focusable="false"><rect x="0" y="0" width="100" height="4"/></svg>'
            f'<div class="hct">{low}</div></div>'
            f'<p class="hce" aria-hidden="true">=</p>'
            f'<div class="hcr"><p class="hck">{e(FIGURE_HEAD["multiple"])}</p>{whole}</div></div>')  # fmt: skip


# ------------------------------------------------------------------ the Autoresearch page
# Mock-up of the track interface rendered on the Autoresearch hero band: a sample task, its Lean
# soundness theorem, and an illustrative search loop with verifier verdicts. Nothing has run yet,
# so each metric cell renders as a blank bar (screen-reader text: "no figure"), and the header bar
# states explicitly that this is a mock-up with invented variants.
LEAN_SKETCH = """theorem sound (P : Prover) (v : Fin N → F)
    (h : ∃ i, v i ∉ T) :
    Pr[verify T v (P v) = true] ≤ ε"""
# Past variants in the illustrative loop, oldest first: a accepted, r rejected, k kept; the last
# five match the table rows, followed by a cell for the currently running candidate.
LOOP_CELLS = "aarraraaarrara" + "arkar"
LOOP = (  # Table rows: (variant description, verifier verdict, kept)
    ("baseline prover", "accepted", False),
    ("drop one check", "rejected", False),
    ("sort before lookup", "accepted", True),
    ("GPU kernel for counts", "accepted", False),
    ("reuse a challenge", "rejected", False),
)
LOOP_HEADS = ("Variant", "Lean verifier", "Prover time", "Proof size", "Verify time")
CELL_SAID = {"a": "accepted", "r": "rejected", "k": "kept"}


@drawn(FIGURES, "autoresearch")
def autoresearch():
    nil = '<span class="nil"><span class="sr">no figure</span></span>'
    first = len(LOOP_CELLS) - len(LOOP) + 1

    def row(k, variant, said, kept):
        cls = "refused" if said == "rejected" else said
        figs = "".join(f'<td data-h="{e(h)}">{nil if said == "accepted" else ""}</td>'
                       for h in LOOP_HEADS[2:])  # fmt: skip
        mark = '<span class="kept">kept</span>' if kept else ""
        return (f'<tr class="{cls}"><td class="arn">{k:02d}</td>'
                f'<th scope="row">{e(variant)}</th><td class="arv">{e(said)}</td>{figs}'
                f'<td class="ark">{mark}</td></tr>')  # fmt: skip

    rows = "".join(row(first + k, *r) for k, r in enumerate(LOOP))
    running = (f'<tr class="running"><td class="arn">{len(LOOP_CELLS) + 1:02d}</td>'
               '<th scope="row">next variant</th><td class="arv">running</td>'
               + "".join(f'<td data-h="{e(h)}"></td>' for h in LOOP_HEADS[2:])
               + '<td class="ark"></td></tr>')  # fmt: skip
    heads = "".join(f'<th scope="col">{e(h)}</th>' for h in LOOP_HEADS)
    cells = "".join(f'<i class="c{c}"></i>' for c in LOOP_CELLS) + '<i class="crun"></i>'
    fixed = "".join(f"<div><dt>{e(k)}</dt><dd>{e(v)}</dd></div>" for k, v in (
        ("Size", "small (minutes on a CPU)"),
        ("Field", "not decided"),
        ("Security level", "not decided"),
        ("Assumptions", "random oracle"),
    ))  # fmt: skip
    return (
        '<div class="arx" role="group" aria-label="Mock-up of a task and automated loop">'
        '<p class="arx-bar"><span class="arx-app"><svg class="arx-tk" viewBox="0 0 19 16" '
        'width="14" height="12" aria-hidden="true" focusable="false"><path d="M0 0h3v16H0z'
        'M4 5h4v5H4zM9 5h4v5H9zM14 5h4v5h-4z"/></svg>autoresearch</span>'
        '<span class="arx-path">lookup · table of 2<sup>16</sup> · small size</span>'
        '<span class="arx-mock">Mock-up (no runs yet)</span></p>'
        '<div class="arx-in">'
        '<section class="arx-task" aria-label="Task">'
        '<p class="arx-h">Statement</p>'
        '<p class="arx-st">Every one of N values belongs to a public table T of 2<sup>16</sup> '
        "entries.</p>"
        '<p class="arx-h">Theorem in Lean</p>'
        f'<pre class="arx-code">{e(LEAN_SKETCH)}</pre>'
        f'<dl class="arx-fx">{fixed}</dl>'
        "</section>"
        '<section class="arx-loop" aria-label="Loop">'
        '<p class="arx-h">Loop</p>'
        f'<p class="arx-cells" aria-hidden="true">{cells}</p>'
        f'<table class="arx-t"><thead><tr><th scope="col"><span class="sr">Number</span></th>'
        f'{heads}<th scope="col"><span class="sr">Kept</span></th></tr></thead>'
        f"<tbody>{rows}{running}</tbody></table>"
        "</section>"
        "</div></div>"
    )
