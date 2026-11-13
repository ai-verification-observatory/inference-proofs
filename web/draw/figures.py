"""What the Learn pages draw: the figures, the explorers and the measured blocks.

A page's text names one by `:::figure <id>`, `:::explore <id>` or `:::measured <id>` (learn.py).
Each is a function of no argument that returns markup:

- a figure is a static drawing made of words, boxes and lines in the site's inks;
- an explorer is a figure a reader can operate. Its markup reads in full without script (every
  step, every case); words.js then shows one state at a time and adds the controls. A worked
  example an explorer prints is computed here, by the same arithmetic the script runs;
- a measured block prints figures of the board file through `fig_html`, with their labels, and
  says so when the board holds none. Nothing here types a measured number.

No inline style: the Content-Security-Policy allows none (outputs.vercel_json). Cobalt frames
what a reader operates; the state inks stay with the states of a check (words.css).
"""

from . import state as S
from .overview import baseline_html, counted, fig_html, href, multiple_html, name_of, standing
from .words import CHECK_NAME, FIGURE_NAME, STATE_WORD, e

FIGURES: dict = {}
EXPLORERS: dict = {}
MEASURED: dict = {}

# what a stage of the treaty page rests on today: the first word of a `:::stage` block (learn.py)
# and the mark on each step of the treaty walk
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
                ("the reply", "r"), ("the proof", "f")),
               never=(("never the weights", "w"),))
        + passes(("accepts or refuses", "with no GPU and no weights", "v"))
        + card("The relying party", "acts on the verdict",
               (("the verdict", "v"), ("the statement it stands for", ""),
                ("the assumptions it rests on", "")))
        + "</div>"
    )  # fmt: skip


@drawn(FIGURES, "pipeline")
def pipeline():
    """One forward pass as its operations, the linear ones apart from the rest."""
    steps = (
        ("Embed", "look up one row of a table per token", "lookup"),
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
    word = {
        "linear": "matrix product",
        "lookup": "table lookup",
        "other": "not arithmetic",
        "mixed": "computed values, and not arithmetic",
    }
    rows = "".join(
        f'<li class="op {"other" if k == "mixed" else k}"><span class="o1">{e(name)}</span><span class="o2">{e(does)}</span>'
        f'<span class="o3">{e(word[k])}</span></li>'
        for name, does, k in steps
    )
    return (f'<ol class="ops">{rows}</ol><p class="opn">The steps from Normalise to MLP: activate repeat once '
            "per layer. Every step repeats for every position of the prompt and of the reply.</p>")  # fmt: skip


SESSION_SAID = (
    "A session on a time axis: the commit step, then a generation phase where a system has one, "
    "then four groups of proofs released one after another. The steady interval runs from the "
    "release of the first group to the release of the last. The generation phase counts in m as "
    "well. The whole session starts with the commit step."
)
SESSION_GROUPS = ("group 1", "group 2", "group 3", "group 4")


def session_svg(cls, w, h, at, said):
    """One layout of the session drawing: `at` places each mark (x of commit, generation and
    each group's release; y of the brackets, the boxes, and the labels of the four groups, commit
    and generation), `said` its words by line."""
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
    return (
        f'<svg class="sx {cls}" viewBox="0 0 {w} {h}" role="img" aria-label="{SESSION_SAID}">'
        f'<line class="ax" x1="{c0}" y1="{base}" x2="{w - c0}" y2="{base}"/>'
        f'<rect class="scm" x="{c0}" {box} width="{c1 - c0}"/>'
        f'<text x="{(c0 + c1) / 2:g}" y="{y["lab"][4]}" text-anchor="middle">commit</text>'
        f'<rect class="sgn" x="{g0}" {box} width="{g1 - g0}"/>'
        f'<text x="{(g0 + g1) / 2:g}" y="{y["lab"][5]}" text-anchor="middle">generation</text>'
        f"{ticks}"
        f'<path class="br" d="M{g0} {top}v-10H{g1}v10"/>'
        + lines("bt", (g0 + g1) / 2, y["m"], said["m"])
        + f'<path class="br" d="M{rel[0]} {top}v-10H{rel[-1]}v10"/>'
        + lines("bt", (rel[0] + rel[-1]) / 2, y["steady"], said["steady"])
        + f'<path class="br2" d="M{c0} {low}v10H{rel[-1]}v-10"/>'
        + lines("bt2", (c0 + rel[-1]) / 2, y["whole"], said["whole"])
        + "</svg>"
    )


@drawn(FIGURES, "session")
def session():
    """One session on a time axis: commit, a generation phase where a system has one, the first
    release group and the later groups, and the GPU time that makes m (RFC-0018 CO-1 to CO-3).
    Two layouts of one drawing: a wide one, and on a phone a narrow one at its own size, its
    long words on two lines and the names under the axis on two rows, in turn."""
    wide = session_svg(
        "sxw", 720, 190,
        {"commit": (20, 120), "gen": (132, 242), "groups": (320, 420, 520, 620), "gw": 26,
         "y": {"br": 52, "box": 72, "lab": (130,) * 6, "low": 150, "m": (30,),
               "steady": (30,), "whole": (180,)}},
        {"m": ("in m too",), "steady": ("steady interval: the GPU time behind m",),
         "whole": ("whole session: from the start of the commit step",)},
    )  # fmt: skip
    narrow = session_svg(
        "sxn", 328, 206,
        {"commit": (4, 54), "gen": (62, 122), "groups": (160, 206, 252, 298), "gw": 18,
         "y": {"br": 52, "box": 64, "lab": (120, 138, 120, 138, 120, 138), "low": 150,
               "m": (30,), "steady": (14, 30), "whole": (178, 194)}},
        {"m": ("in m too",), "steady": ("steady interval:", "the GPU time behind m"),
         "whole": ("whole session: from the start", "of the commit step")},
    )  # fmt: skip
    return f'<div class="tw">{wide}{narrow}</div>'


# ------------------------------------------------------------------ explorers
# ---- the treaty walk: who holds what at each step, and what the Inspectorate can conclude
TREATY_PARTIES = ("State A's operator", "The Inspectorate", "State B")
# each step carries the mark of the stage it belongs to on the treaty page (STAGE_WORD), or none
TREATY_STEPS = (
    {
        "title": "The agreement",
        "stage": None,
        "does": "State A and State B agree on a rule for their declared data centres: serve only "
        "models entered in a shared register, and train nothing above an agreed size. Neither "
        "will show the other its weights.",
        "holds": (("its model's weights",), (), ()),
        "can": "Nothing yet: no claim has been made that could be checked.",
        "cannot": "Tell which model any data centre is running.",
    },
    {
        "title": "Register a model, prove a reply",
        "stage": "measured",
        "does": "State A's operator computes a commitment to its model and enters it in the "
        "register. The commitment fixes the weights, and publishing it does not publish them. For a "
        "prompt and a reply the Inspectorate holds, the operator can then make a proof.",
        "holds": (
            ("its model's weights", "+ the commitment", "+ a proof for each reply asked about"),
            ("+ the commitment", "+ a prompt, a reply and its proof"),
            ("+ the commitment",),
        ),
        "can": "Check that a reply is what the registered model gives for its prompt, with no "
        "weights and no GPU.",
        "cannot": "Read the weights from the commitment, know that the reply was served, or "
        "know yet that the committed model is one the agreement allows.",
    },
    {
        "title": "Evaluate the registered model",
        "stage": "demonstrated",
        "does": "The Inspectorate, or evaluators it appoints, test the model. Each test reply "
        "comes with a proof against the registered commitment, which ties the test results to "
        "the registered weights. This has been shown on small models.",
        "holds": (
            (
                "its model's weights",
                "the commitment",
                "+ the test prompts and replies",
                "+ their proofs",
            ),
            ("the commitment", "+ the test results", "+ their proofs"),
            ("the commitment", "+ the Inspectorate's report"),
        ),
        "can": "Say that the test results are those of the registered weights, without holding "
        "them.",
        "cannot": "Judge by a proof whether the tests were the right tests, or whether the same "
        "weights behave the same behind another system prompt or filter.",
    },
    {
        "title": "Record the traffic, then sample it",
        "stage": "proposed",
        "does": "Equipment at the data centre's network boundary keeps a fingerprint of every "
        "prompt and reply. Every reply is generated by the proved copy of the registered model, so "
        "that any of them can be proved. Afterwards the Inspectorate draws replies at random "
        "from the record and asks for their proofs.",
        "holds": (
            (
                "its model's weights",
                "the commitment",
                "every prompt and reply",
                "+ proofs of the sampled replies",
            ),
            (
                "the commitment",
                "+ a fingerprint of every prompt and reply",
                "+ the sampled prompts, replies and proofs",
            ),
            ("the commitment", "+ the sampled prompts and replies, if State A releases them"),
        ),
        "can": "Check each sampled reply against the registered model, and bound how often the "
        "traffic could be something else.",
        "cannot": "Rely on the sample unless the equipment is trusted, the draw comes after the "
        "record, and the draw cannot be predicted. Tying each proof to the record is not built "
        "yet.",
    },
    {
        "title": "A model is substituted",
        "stage": "proposed",
        "does": "For some replies the operator used another model. When one of them is drawn, "
        "no valid proof exists for it: the operator sends none, or one the verifier refuses.",
        "holds": (
            (
                "its model's weights",
                "+ other weights",
                "the commitment",
                "+ no valid proof for those replies",
            ),
            ("the commitment", "the record", "+ a refusal, or a missing proof"),
            ("the commitment", "+ the Inspectorate's report"),
        ),
        "can": "Show State B one recorded reply for which State A gave no valid proof.",
        "cannot": "Tell a fault from a substitution without an investigation, or count on "
        "catching a single substituted reply.",
    },
    {
        "title": "What stays outside",
        "stage": "outside",
        "does": "A proof speaks about the replies it covers. It is silent on anything else the "
        "same machines did, on machines nobody declared, on how the model was trained and on "
        "what the model can do.",
        "holds": (
            (
                "its model's weights",
                "possibly: other work on the same machines",
                "possibly: machines it never declared",
            ),
            ("the commitment", "the record", "the proofs"),
            ("the commitment", "the Inspectorate's reports"),
        ),
        "can": "State exactly what was checked, on which declared machines, under which "
        "assumptions.",
        "cannot": "Show that a data centre did nothing else, or find one that was never "
        "declared. Those take equipment on every output, inspections and intelligence.",
    },
)


@drawn(EXPLORERS, "treaty")
def treaty():
    """Every step in full, in order; with script, one at a time with a step bar above."""
    steps = ""
    for k, s in enumerate(TREATY_STEPS, start=1):
        cols = "".join(
            f'<div class="lcd"><p class="pk">{e(name)}</p><ul class="ph">'
            + "".join(f'<li{" class=nw3" if h.startswith("+ ") else ""}>{e(h.removeprefix("+ "))}</li>'
                      for h in held)
            + ("" if held else '<li class="nv">nothing yet</li>')
            + "</ul></div>"
            for name, held in zip(TREATY_PARTIES, s["holds"], strict=True)
        )  # fmt: skip
        mark = (f'<p class="chip {s["stage"]}">{e(STAGE_WORD[s["stage"]])}</p>'
                if s["stage"] else "")  # fmt: skip
        steps += (
            f'<li class="xst"><p class="xn">Step {k} of {len(TREATY_STEPS)}</p>'
            f'<h3 class="xh">{e(s["title"])}</h3>{mark}<p class="xd">{e(s["does"])}</p>'
            f'<div class="bd">{cols}</div>'
            f'<dl class="xcc"><div><dt>The Inspectorate can</dt><dd>{e(s["can"])}</dd></div>'
            f"<div><dt>It cannot</dt><dd>{e(s['cannot'])}</dd></div></dl></li>"
        )
    return f'<div class="xpl" data-x="steps"><ol class="xsl">{steps}</ol></div>'


# ---- tamper and check: what is changed, what the verifier binds, the verdict (RFC-0008 C1 to
# C3, P1; RFC-0018 Model, Prompt, Reply)
TAMPER = (
    ("model", "one weight of the model", "the committed model"),
    ("prompt", "one token of the prompt", "the prompt"),
    ("reply", "one token of the reply", "the reply"),
)


@drawn(EXPLORERS, "tamper")
def tamper():
    """The three controls as a table (what is changed, what a verifier that binds it does, the
    check that tests it). With script: choose what to change and what the verifier binds; the
    panel and the three verdicts are drawn here, hidden until words.js shows them."""
    heads = (
        "We change",
        "A verifier that ties its yes to it",
        "A verifier that does not",
        "Our check",
    )
    rows = "".join(
        f'<tr><th scope="row" data-l="{heads[0]}">{e(what.capitalize())}</th>'
        f'<td data-l="{heads[1]}"><i class="sw held" aria-hidden="true"></i>refuses</td>'
        f'<td data-l="{heads[2]}"><i class="sw failed" aria-hidden="true"></i>accepts a '
        "statement that is false</td>"
        f'<td data-l="{heads[3]}"><a href="/checks#{cid}">{e(CHECK_NAME[cid])}</a></td></tr>'
        for cid, what, _ in TAMPER
    )
    ths = "".join(f'<th scope="col">{h}</th>' for h in heads)
    table = (f'<table class="rt lt mt"><thead><tr>{ths}</tr></thead><tbody>{rows}'
             f'<tr><th scope="row" data-l="{heads[0]}">Nothing</th><td colspan="2" data-l="Any verifier">'
             '<i class="sw held" aria-hidden="true"></i>accepts: a refusal means something only '
             "if the same verifier accepts the untouched proof</td>"
             f'<td data-l="{heads[3]}">run beside every change</td></tr>'
             "</tbody></table>")  # fmt: skip

    def boxes(group, legend, word, checked):
        return (f'<fieldset class="xg"><legend>{e(legend)}</legend>' + "".join(
            f'<label class="xc"><input type="checkbox" name="{group}" value="{cid}"'
            f'{" checked" if checked else ""} data-words="{e(part if group == "bind" else what)}" '
            f'data-check="{e(CHECK_NAME[cid])}">{e(word(what, part))}</label>'
            for cid, what, part in TAMPER) + "</fieldset>")  # fmt: skip

    panel = (
        '<div class="xpn" hidden>'
        + boxes("change", "Change", lambda what, part: what, False)
        + boxes("bind", "The verifier under test ties its yes to", lambda what, part: part, True)
        + '<div class="xv" role="status">'
        '<p data-v="twin">The verifier <b>accepts</b>. Nothing was changed, and a refusal '
        "means something only if the untouched proof is accepted.</p>"
        '<p data-v="refuse">The verifier <b>refuses</b>: the proof no longer matches '
        '<span data-slot="parts"></span>.</p>'
        '<p data-v="false">The verifier <b>accepts a statement that is false</b>: it does not '
        'tie its yes to <span data-slot="parts"></span>. On this site, once the acceptance was '
        "reproduced with the system's own command, these checks would read failed: "
        '<span data-slot="checks"></span>.</p>'
        "</div>"
        '<ul class="xk" aria-label="What our controls would report for this verifier">'
        + "".join(f'<li data-check="{cid}"><i class="sw" aria-hidden="true"></i>{e(CHECK_NAME[cid])} '
                  f'<span data-held="{STATE_WORD["held"]}" data-failed="{STATE_WORD["failed"]}">'
                  "</span></li>" for cid, _, _ in TAMPER)
        + "</ul></div>"
    )  # fmt: skip
    hint = "Change something, or weaken the verifier, and see the verdict."
    return (f'<div class="xpl" data-x="tamper" data-w-hint="{hint}">{panel}'
            f'<div class="tw">{table}</div></div>')  # fmt: skip


# ---- a random check of a matrix product (Freivalds) and a sumcheck of an inner product: the
# worked examples, by the arithmetic words.js runs. The sentences words.js prints are the
# templates here ({name} filled in), so the page reads the same with script and without.
P = 97  # the small prime field of the worked examples: small enough that a lie sometimes survives
FA = ((2, 0, 1), (1, 3, 0), (0, 1, 2))
FB = ((1, 2, 0), (0, 1, 1), (3, 0, 1))
WRONG = (1, 2, 1)  # row, column, and what is added there to make the claimed product false
RC_WORDS = {
    "diff": "different: the claimed product is refused",
    "miss": "equal: this draw misses the change",
    "true": "equal, as it must be: this claimed product is the true one",
    "tally": "{n} draws from {set} so far, {k} of them refused the claimed product.",
    "bits": "Draw r from 0 and 1",
    "field": "Draw r from 0 to {top}",
    "many": "Draw {n} times from 0 to {top}",
    "setbits": "0 and 1",
    "setfield": "0 to {top}",
    "wrong": "One entry of the claimed product is wrong",
}
RC_RUNS = 1000  # how many draws the "many" button makes


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


def flat(m):
    """A matrix as the script reads it: its rows, entries separated by spaces, rows by commas."""
    return ",".join(" ".join(str(v) for v in row) for row in m)


@drawn(EXPLORERS, "random-check")
def random_check_html():
    """A·B against a claimed C with one wrong entry: two draws worked in full, one that catches
    the change and one that misses it. With script: draw r, from bits or from the whole field."""
    i, j, _ = WRONG

    def draw(r):
        got = random_check(r)
        verdict = RC_WORDS["miss"] if got["equal"] else RC_WORDS["diff"]
        return (f'<div class="dr"><div class="eq"><span class="lb">r</span>{column(got["r"])}'
                f'<span class="lb">A·(B·r)</span>{column(got["left"])}'
                f'<span class="lb">C·r</span>{column(got["right"])}</div>'
                f'<p class="vd">{e(verdict)}</p></div>')  # fmt: skip

    data = (f'data-a="{flat(FA)}" data-b="{flat(FB)}" data-c="{flat(claimed(False))}" '
            f'data-ok="{flat(claimed(True))}" data-p="{P}" data-runs="{RC_RUNS}" '
            f"{data_words(RC_WORDS)}")  # fmt: skip
    return (
        f'<div class="xpl" data-x="random-check" {data}>'
        f'<div class="eq mm"><span class="lb">A</span>{grid(FA)}<span class="lb">B</span>{grid(FB)}'
        f'<span class="lb">claimed C</span><div class="cl">{grid(claimed(False), mark=(i, j))}</div>'
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
    heads = ("Running claim", "Prover sends s(0), s(1), s(2)", "Verifier checks",
             "Verifier draws r", "New claim s(r)")  # fmt: skip
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
    """Two runs on the same draws, in full: an honest prover, then one that claims a result
    off by one. With script: choose the prover, draw again, run many times."""
    vectors = (f'<div class="eq mm"><span class="lb">a, the weights</span>{grid((SA,))}'
               f'<span class="lb">b, the activations</span>{grid((SB,))}'
               f'<span class="lv">arithmetic modulo {P}</span></div>')  # fmt: skip
    data = (f'data-a="{flat((SA,))}" data-b="{flat((SB,))}" data-p="{P}" data-lie="{LIE}" '
            f'data-runs="1000" {data_words(SC_WORDS)}')  # fmt: skip
    return (f'<div class="xpl" data-x="sumcheck" {data}>{vectors}<div class="xo">'
            f'{transcript(sumcheck(), "honest")}{transcript(sumcheck(lie=LIE), "lying")}'
            "</div></div>")  # fmt: skip


# ---- the cost of proving a share of replies: arithmetic on two parts the reader sets. Under
# exact match (RFC-0018 AD-3) a reply can be proved only if the committed copy generated it, and
# the sample is drawn after serving, so generation is paid on every reply and proving on the share.
SHARES = ((0.001, "1 in 1,000"), (0.01, "1 in 100"), (1.0, "every reply"))
PARTS = ((1, 100), (10, 100), (100, 100))  # example (generation, proving) parts, × serving
COST_WORDS = {
    "share": "Share of replies proved",
    "generation": "Generation part, × serving",
    "proving": "Proving part, × serving",
    "out": "With every reply generated at {g} serving and {share} of replies proved at {p} "
    "serving, the total bill is {total} the serving bill.",
    "hint": "Move the share and type the two parts.",
    "hintrows": "Move the share and type the two parts, or press a row to use its parts.",
}


def bill(share, generation, proving):
    """Every reply is generated by the committed copy, at `generation` times the cost of serving
    one; a share of them is also proved, each at `proving` times. The total, in units of the
    serving bill. At a share of 1 it is the row's multiple: generation plus proving."""
    return generation + share * proving


def times(x):
    return f"{x:,.2f}".rstrip("0").rstrip(".") + "×"


@drawn(EXPLORERS, "cost")
def cost():
    """A table for three example pairs of parts and three shares, and the board's rows that print
    their multiple in two parts (CO-7). With script: a slider for the share and a field for each
    part, which a row of the board fills in when pressed."""
    names = [f"generation {g:,}×, proving {p:,}×" for g, p in PARTS]
    head = "".join(f'<th scope="col">{n}</th>' for n in names)
    body = "".join(
        f'<tr><th scope="row" data-l="{COST_WORDS["share"]}">{e(label)}</th>'
        + "".join(f'<td data-l="{n}">{times(bill(share, g, p))}</td>'
                  for n, (g, p) in zip(names, PARTS, strict=True)) + "</tr>"
        for share, label in SHARES
    )  # fmt: skip
    presets = ""
    for rung in S.V["rungs"]:
        for row in rung["rows"]:
            g, p = (row["figures"].get(k) for k in ("generation_multiple", "proving_multiple"))
            if g and p and g["value"] is not None and p["value"] is not None:
                presets += (
                    f'<li data-g="{g["value"]}" data-p="{p["value"]}"><span class="pn2">'
                    f"{e(name_of(row))} on {e(rung['model'])}</span>"
                    f'<span class="pv">generation {fig_html(g, counted(row))}</span>'
                    f'<span class="pv">proving {fig_html(p, counted(row))}</span></li>'
                )
    measured = (f'<div class="xp2"><p class="fl">{e(release_words())}: rows that print their '
                f'multiple in two parts</p><ul class="pre">{presets}</ul></div>' if presets else "")  # fmt: skip
    return (
        f'<div class="xpl" data-x="cost" data-g="{PARTS[0][0]}" data-p="{PARTS[0][1]}" '
        f"{data_words(COST_WORDS)}>{measured}"
        f'<div class="tw"><table class="rt lt mt"><thead><tr><th scope="col">{COST_WORDS["share"]}'
        f"</th>{head}</tr></thead><tbody>{body}</tbody></table></div>"
        '<p class="xf">Total bill = serving bill × (generation part + share proved × proving '
        "part). Every reply is generated by the committed copy of the model, and a share of them "
        "is also proved. A generation part of 1 would be a copy that is as cheap to serve as the "
        "original. Arithmetic on example inputs, not a measurement.</p></div>"
    )


# ------------------------------------------------------------------ measured blocks
def release_words():
    rel = S.V["release"]
    if not rel:
        return "No board yet"
    return f"From the board, release {rel['id']}" + (f" ({rel['date']})" if rel["date"] else "")


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


@drawn(MEASURED, "rows")
def measured_rows():
    """Every row of the board, one table per model (nothing is set side by side across models):
    system, standing, multiple of serving, check time and proof size per reply. A row with no
    position is set in the muted ink, as on the ladder."""
    found = [(rung, row) for rung in S.V["rungs"] for row in rung["rows"]]
    if not found:
        return ('<p class="none">No system has a row yet. The <a href="/">ladder</a> shows each '
                "one as it is run.</p>")  # fmt: skip
    heads = ("System", "Standing", FIGURE_NAME["multiple"], FIGURE_NAME["check-time"],
             "Proof size per reply")  # fmt: skip
    ths = "".join(f'<th scope="col">{h}</th>' for h in heads)

    def tr(row):
        return (
            "<tr>"
            f'<th scope="row" data-l="{heads[0]}"><a href="{e(href(row))}">{e(name_of(row))}</a></th>'
            f'<td data-l="{heads[1]}">{e(standing(row))}</td>'
            f'<td data-l="{heads[2]}">{multiple_html(row)}</td>'
            f'<td data-l="{heads[3]}">'
            f"{fig_html(row['figures']['verify_seconds_per_reply'], counted(row))}</td>"
            f'<td data-l="{heads[4]}">'
            f"{fig_html(row['figures']['proof_bytes_per_reply'], counted(row))}</td></tr>"
        )

    tables = "".join(
        f'<div class="tw"><table class="rt mt"><caption class="bm">On {e(rung["model"])}</caption>'
        f'<thead><tr>{ths}</tr></thead><tbody>{"".join(tr(row) for row in rung["rows"])}</tbody>'
        "</table></div>"
        for rung in S.V["rungs"] if rung["rows"]
    )  # fmt: skip
    return (f'<p class="fl">{e(release_words())}</p><p class="ms-s">{e(rows_words(found))}</p>'
            f"{tables}")  # fmt: skip


@drawn(MEASURED, "baselines")
def measured_baselines():
    """Each model's serving baseline in one line, as the overview prints it (CO-4)."""
    lines = "".join(f'<div class="bl2"><p class="bm">{e(rung["model"])}</p>{baseline_html(rung)}'
                    "</div>" for rung in S.V["rungs"])  # fmt: skip
    return f'<p class="fl">{e(release_words())}</p>{lines}'
