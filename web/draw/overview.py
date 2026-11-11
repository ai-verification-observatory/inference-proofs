"""The overview (`index.html`): the ladder (RFC-0018 SI-1). The frontier headline, then one section
per model, largest first: its head (model, publisher, total parameters, the request, the serving
baseline) and its rows in the board's order (OR-5), then the systems not run (SI-4). Rows sort
only by the order rule: no column head re-sorts them. Also the figure cells the system pages use.
"""

from . import state as S
from .chrome import footer, header, page, rung_of
from .hexagon import glyph_svg, sized
from .words import (
    CHECK_NAME,
    NULL_WORD,
    PETAL_NAME,
    PETAL_WORD,
    STATE_WORD,
    architecture,
    e,
    labels,
    number,
    sub_words,
)

# RFC-0018 SI-2, under the first rung; and what the checks do not test (the checks page)
UNDER = ("Ranked by cost among systems that passed our checks. The glyph shows how far each is "
         "from a perfect prover; it does not move the order.")  # fmt: skip
NOT_TESTED = ("These checks run each system's own prover and verifier. None attempts a forged "
              "proof: soundness and weight secrecy are not tested.")  # fmt: skip
ROW_GLYPH = (56, 44)  # the row glyph's sizes: wide screens, then phones


def states(row):
    """The five petals' states, in the glyph's order (GL-5)."""
    return [p["state"] for p in row["glyph"]]


def states_words(row):
    """The petals in words, for screen readers (the glyph is drawn, not read)."""
    return ", ".join(f"{PETAL_NAME[p['id']]} {PETAL_WORD[p['state']]}" for p in row["glyph"])


def name_of(row):
    return S.V["systems"][row["system"]]["name"]


def href(row):
    return f"/{row['page']}"


def fig_html(f, n=None, sub=None):
    """One stored figure: the number in a reading unit, its labels in its title, and under it its
    scope in a word and its sample size (AGENTS.md rule 2). `sub` replaces the line under it."""
    if f is None:
        return '<span class="na">not recorded</span>'
    if f["value"] is None:
        why = NULL_WORD[f["null_reason"]]
        return (
            f'<span class="na" title="{e(labels(f))}">none</span><span class="sub">{e(why)}</span>'
        )
    num, unit = number(f["value"], f["unit"])
    x = " x" if f["unit"] == "ratio" else ""
    line = sub if sub is not None else sub_words(f, n)
    return (f'<span class="fig" title="{e(labels(f))}"><span class="n">{e(num)}</span>'
            f'<span class="u{x}">{e(unit)}</span></span>'
            + (f'<span class="sub">{e(line)}</span>' if line else ""))  # fmt: skip


def counted(row):
    """The counted sessions a row's figures are over."""
    return len(row["sessions"]) or None


def multiple_html(row):
    """CO-5: the multiple; with no steady state, the session cost over serving, labelled as cold
    sessions."""
    figs = row["figures"]
    m = figs["multiple"]
    if m is not None and m["value"] is not None:
        return fig_html(m, counted(row))
    cold = figs["session_multiple"]
    if cold is not None and cold["value"] is not None:
        n = rung_of(row)["requests_per_session"]
        count = cold["n"] if cold["n"] is not None else counted(row)
        return fig_html(cold, sub=f"cold sessions of {n:,} replies · n\u00a0=\u00a0{count}")
    return fig_html(m)


def kl_html(row):
    fid = row["fidelity"] or {}
    kl = fid.get("kl")
    if kl is not None and kl["value"] is not None:
        return fig_html(kl)
    note = fid.get("kl_note") or "not measured"
    return f'<span class="na" title="{e(note)}">not measured</span>'


def position_html(row, rung):
    if row["position"] is None:
        return ""
    return (f'<span class="pn">{row["position"]}</span>'
            f'<span class="of">of {rung["systems_run"]}</span>')  # fmt: skip


def standing(row):
    """Passed (a system on a model, SI-6), passed and unranked with why, or not passed with the
    checks not held (SI-1)."""
    if row["passed"] and not row["ranked"]:
        return f"passed, unranked: {row['unranked_reason']}"
    if row["passed"]:
        return "passed"
    missing = [f"{CHECK_NAME[c['id']]} {STATE_WORD[c['state']]}" for c in row["checks"]
               if c["state"] != "held"]  # fmt: skip
    return "not passed: " + ", ".join(missing) if missing else "not passed"


HEADS = ("", "", "System", "Multiple of serving", "Cost per reply", "Check time per reply",
         "KL to the 16-bit model")  # fmt: skip


def row_cost(row):
    """The cost per reply at the multiple's own scope: steady when the row has a steady
    multiple, else its cold sessions, so one row never mixes two scopes."""
    figs = row["figures"]
    steady = figs["multiple"].get("value") is not None
    return figs["steady_usd_per_reply" if steady else "session_usd_per_reply"]


def row_html(row, rung):
    glyph = sized(lambda s: glyph_svg(s, states(row)), ROW_GLYPH)
    cells = (
        ("cm", multiple_html(row)),
        ("cc", fig_html(row_cost(row), counted(row))),
        ("ct", fig_html(row["figures"]["verify_seconds_per_reply"], counted(row))),
        ("ck", kl_html(row)),
    )
    figs = "".join(f'<td class="{c}"><span class="lbl">{e(h)}</span>{html}</td>'
                   for (c, html), h in zip(cells, HEADS[3:], strict=True))  # fmt: skip
    return (
        f'<tr class="row" id="row-{e(row["page"])}">'
        f'<td class="cp">{position_html(row, rung)}</td>'
        f'<td class="cg"><a class="glyph" href="{e(href(row))}" tabindex="-1" aria-hidden="true">'
        f"{glyph}</a></td>"
        f'<th class="csys" scope="row"><a class="sname" href="{e(href(row))}">{e(name_of(row))}</a>'
        f'<span class="st">{e(standing(row))}</span>'
        f'<span class="sr">{e(states_words(row))}</span></th>{figs}</tr>'
    )


def request_words():
    r = S.V["request"]
    return (f"{r['prompt_tokens']:,} prompt tokens, {r['output_tokens']:,} reply tokens, "
            f"{r['decoding']}, every reply token checked")  # fmt: skip


def engine_words():
    eng = S.V["engine"] or {}
    name = {"vllm": "vLLM"}.get(str(eng.get("name")), eng.get("name") or "engine not recorded")
    return f"{name} {eng['version']}" if eng.get("version") else name


def baseline_html(rung):
    """The serving baseline in one line (CO-4): engine, GPUs, concurrency at full load and its
    GPU-seconds per reply."""
    b = rung["baseline"]
    if b is None:
        return '<p class="rb"><span class="k">Serving</span> not run yet</p>'
    if b["gpu_seconds_per_reply"] is None or b["gpu_seconds_per_reply"]["value"] is None:
        why = b["cause"] or "no full load recorded"
        return f'<p class="rb"><span class="k">Serving</span> {e(why)}</p>'
    gpus = f"{b['gpus']} × H200" if b["gpus"] else "GPUs not recorded"
    return (f'<p class="rb"><span class="k">Serving</span> {e(engine_words())}, {e(gpus)}, '
            f"full load at {b['concurrency']:,} concurrent requests: "
            f'{fig_html(b["gpu_seconds_per_reply"])}</p>')  # fmt: skip


def rung_html(rung, first):
    head = (
        f'<header class="rh"><h2 class="rm" id="h-{e(rung["id"])}">{e(rung["model"])}</h2>'
        f'<p class="ri">{e(rung["publisher"])} · '
        f"{e(architecture(rung['parameters_total'], rung.get('parameters_active')))} · "
        f"{e(request_words())}</p>"
        f"{baseline_html(rung)}</header>"
    )
    if not rung["rows"]:
        body = '<p class="none">Not run yet.</p>'
    else:
        ths = "".join(f'<th scope="col">{e(h)}</th>' for h in HEADS)
        rows = "".join(row_html(r, rung) for r in rung["rows"])
        cols = '<colgroup><col class="c1"><col class="c2"><col class="c3"><col><col><col><col></colgroup>'
        body = (
            f'<table class="lad">{cols}<thead><tr>{ths}</tr></thead><tbody>{rows}</tbody></table>'
        )
    after = f'<p class="nt">{e(UNDER)}</p>' if first else ""
    return (f'<section class="rung" id="{e(rung["id"])}" aria-labelledby="h-{e(rung["id"])}">'
            f"{head}{body}{after}</section>")  # fmt: skip


def frontier_html():
    """OR-6: the largest model with a passed row, the row at position 1 (or every passed row when
    none is ranked), its multiple and the count of systems run on that model."""
    f = S.V["frontier"]
    if f is None:
        said = "No system has passed yet." if S.V["release"] else "No system has run yet."
        return f'<h1 class="front">{e(said)}</h1>'
    names = " and ".join(f'<a href="{e(href(row))}">{e(name_of(row))}</a>' for row in f["rows"])
    first = f["rows"][0]
    count = f["systems_run"]
    where = (f"{first['position']} of {count} systems run on this model"
             if first["position"] is not None else
             f"{count} system{'s' if count != 1 else ''} run on this model")  # fmt: skip
    m = first["figures"]["multiple"]
    said = [where]
    if len(f["rows"]) == 1 and m is not None and m["value"] is not None:
        num, unit = number(m["value"], m["unit"])
        said.insert(0, f"{num}{unit} serving")
    return (f'<h1 class="front">{names} passed on {e(f["model"])}</h1>'
            f'<p class="fsub">{e(" · ".join(said))}</p>')  # fmt: skip


def not_run_html():
    items = "".join(
        f'<li id="nr-{e(r["id"])}"><span class="nn">{e(r["name"])}</span>'
        f'<span class="nr">{e(r["reason"])}</span></li>'
        for r in S.V["not_run"]
    )
    return (f'<section class="notrun" aria-labelledby="h-notrun"><h2 class="sect" id="h-notrun">'
            f'Not run</h2><ul class="nrl">{items}</ul></section>')  # fmt: skip


def build_index():
    rungs = "".join(rung_html(r, i == 0) for i, r in enumerate(S.V["rungs"]))
    body = f"""
{header("home")}
<main id="main" class="home">
  <section class="mast"><div class="mast-in">{frontier_html()}</div></section>
  <div class="wrap">{rungs}{not_run_html()}</div>
</main>
{footer()}"""
    models = ", ".join(r["model"] for r in S.V["rungs"])
    desc = f"{S.V['level']['name']}: provers on {models}, six checks each, cost against serving."
    return page("Inference proofs", desc, body, "home", "", "home")
