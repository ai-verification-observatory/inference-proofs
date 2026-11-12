"""The overview (`index.html`): the ladder (RFC-0018 SI-1). The frontier headline, then one section
per model, largest first: its head (model, publisher, total parameters, the serving
baseline) and its rows in the board's order (OR-5), then the systems not run (SI-4). Rows sort
only by the order rule: no column head re-sorts them. Also the figure cells the system pages use.
"""

from . import state as S
from .chrome import CHECKS_PAGE, footer, header, page, rung_of
from .hexagon import glyph_svg, sized
from .words import (
    CHECK_NAME,
    FIGURE_NAME,
    NULL_WORD,
    PETAL_NAME,
    PETAL_WORD,
    REFERENCE_WORD,
    STATE_WORD,
    architecture,
    e,
    kl_head,
    labels,
    number,
    params,
    sub_words,
)

# what the checks do not test (the checks page)
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


def defined(words, anchor):
    """Words linked to where the checks page defines them."""
    return f'<a class="df" href="{CHECKS_PAGE}#{anchor}">{e(words)}</a>'


def standing_html(row):
    """`standing` on the overview: passed, unranked and each check not held link to their
    definitions."""
    if row["passed"] and not row["ranked"]:
        return (f"{defined('passed', 'passed')}, {defined('unranked', 'unranked')}: "
                f"{e(row['unranked_reason'])}")  # fmt: skip
    if row["passed"]:
        return defined("passed", "passed")
    missing = [f"{defined(CHECK_NAME[c['id']], c['id'])} {e(STATE_WORD[c['state']])}"
               for c in row["checks"] if c["state"] != "held"]  # fmt: skip
    return "not passed: " + ", ".join(missing) if missing else "not passed"


def reference_words():
    """Each model's reference precision (FI-1): "16-bit for A and B, 32-bit for C"."""
    by: dict[str, list[str]] = {}
    for rung in S.V["rungs"]:
        by.setdefault(REFERENCE_WORD[rung["reference_dtype"]], []).append(rung["model"])
    return ", ".join(f"{word} for {' and '.join(models)}" for word, models in by.items())


def filled(text):
    """A rule of `words` with the level file's constants in it."""
    r, c = S.V["request"], S.V["constants"]
    return text.format(
        gap=f"{c['group_gap_s']:g}\u202fs",
        reference=reference_words(),
        slots=c["slots"],
        attempts=c["attempts_per_slot"],
        reply_tokens=f"{r['output_tokens']:,}",
        full=f"{(1 - c['plateau']) * 100:g}\u202f%",
        top=f"{c['ladder_top']:,}",
        margin=f"{S.V['order_margin'] * 100:g}\u202f%",
        request=request_words().capitalize(),
    )


FIGURES = ("multiple", "cost", "check-time", "kl")  # the figure columns, in the row's order


def heads(rung):
    """The figure columns' heads, each linked to its definition; the KL head names the precision
    of the rung's reference (FI-1)."""
    names = {**FIGURE_NAME, "kl": kl_head(rung["reference_dtype"])}
    return [defined(names[f], f) for f in FIGURES]


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
    figs = "".join(f'<td class="{c}"><span class="lbl">{h}</span>{html}</td>'
                   for (c, html), h in zip(cells, heads(rung), strict=True))  # fmt: skip
    return (
        f'<tr class="row" id="row-{e(row["page"])}">'
        f'<td class="cp">{position_html(row, rung)}</td>'
        f'<td class="cg"><a class="glyph" href="{e(href(row))}" tabindex="-1" aria-hidden="true">'
        f"{glyph}</a></td>"
        f'<th class="csys" scope="row"><a class="sname" href="{e(href(row))}">{e(name_of(row))}</a>'
        f'<span class="st">{standing_html(row)}</span>'
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


def rung_html(rung):
    head = (
        f'<header class="rh"><h2 class="rm" id="h-{e(rung["id"])}">{e(rung["model"])}</h2>'
        f'<p class="ri">{e(rung["publisher"])} · '
        f"{e(architecture(rung['parameters_total'], rung.get('parameters_active')))}</p>"
        f"{baseline_html(rung)}</header>"
    )
    if not rung["rows"]:
        body = '<p class="none">Not run yet.</p>'
    else:
        ths = "".join(f'<th scope="col">{h}</th>' for h in ("", "", "System", *heads(rung)))
        rows = "".join(row_html(r, rung) for r in rung["rows"])
        cols = '<colgroup><col class="c1"><col class="c2"><col class="c3"><col><col><col><col></colgroup>'
        body = (
            f'<table class="lad">{cols}<thead><tr>{ths}</tr></thead><tbody>{rows}</tbody></table>'
        )
    return (f'<section class="rung" id="{e(rung["id"])}" aria-labelledby="h-{e(rung["id"])}">'
            f"{head}{body}</section>")  # fmt: skip


def _best_multiple(rung):
    """The lowest multiple of serving among the rung's passed rows, formatted, or None."""
    found = []
    for row in rung["rows"]:
        m = row["figures"]["multiple"] if row["passed"] else None
        if m is not None and m["value"] is not None:
            found.append(m)
    if not found:
        return None
    best = min(found, key=lambda m: m["value"])
    num, unit = number(best["value"], best["unit"])
    return f"{num}{unit} serving"


def frontier_html():
    """The band: one line, the largest model a system passed on (OR-6) and who holds position 1
    there, or the largest model run when none passed; under it, how many other models and
    systems the ladder holds."""
    rungs, front = S.V["rungs"], S.V["frontier"]
    run = [r for r in rungs if r["rows"]]
    systems = {row["system"] for r in rungs for row in r["rows"]}
    if not run:
        return (f'<h1 class="band-h">No system has run yet.</h1>'
                f'<p class="fsub">{e(request_words())}</p>')  # fmt: skip
    rung = next(r for r in rungs if r["id"] == front["rung"]) if front else run[0]
    if front:
        names = ", ".join(name_of(row) for row in front["rows"])
        said = f"#1 {names}" if front["rows"][0]["position"] == 1 else f"passed: {names}"
        state, tag = "s2 bl-top", "Largest model proved"
        shown = {row["system"] for row in front["rows"]}
    else:
        said = f"{len(rung['rows'])} run, none passed"
        state, tag, shown = "s1 bl-top", "Largest model run", set()
    line = (
        f'<li class="bl-r {state}"><a href="#{e(rung["id"])}">'
        f'<span class="bl-k">{e(tag)}</span>'
        f'<span class="bl-m">{e(rung["model"])}</span>'
        f'<span class="bl-p">{e(params(rung["parameters_total"]))}</span>'
        f'<span class="bl-bar" aria-hidden="true"></span>'
        f'<span class="bl-s">{e(said)}</span>'
        f'<span class="bl-c">{e(_best_multiple(rung) or "")}</span>{{more}}</a></li>'
    )
    more_models, more_systems = len(rungs) - 1, len(systems - shown)
    more = [f"+{more_models} model{'s' if more_models != 1 else ''}"] if more_models else []
    if more_systems:
        more.append(f"+{more_systems} system{'s' if more_systems != 1 else ''}")
    line = line.replace(
        "{more}", f'<span class="bl-more">{e(" · ".join(more))}</span>' if more else ""
    )
    return (f'<h1 class="band-h">Proved inference, by model size</h1><ol class="bl">{line}</ol>'
            f'<p class="fsub">{e(request_words())}</p>')  # fmt: skip


def not_run_html():
    items = "".join(
        f'<li id="nr-{e(r["id"])}"><span class="nn">{e(r["name"])}</span>'
        f'<span class="nr">{e(r["reason"])}</span></li>'
        for r in S.V["not_run"]
    )
    return (f'<section class="notrun" aria-labelledby="h-notrun"><h2 class="sect" id="h-notrun">'
            f'Not run</h2><ul class="nrl">{items}</ul></section>')  # fmt: skip


def build_index():
    rungs = "".join(rung_html(r) for r in S.V["rungs"])
    body = f"""
{header("home")}
<main id="main" class="home">
  <section class="mast"><div class="mast-in">{frontier_html()}</div></section>
  <div class="wrap ladder">{rungs}</div>
  <div class="wrap">{not_run_html()}</div>
</main>
{footer()}"""
    models = ", ".join(r["model"] for r in S.V["rungs"])
    desc = f"{S.V['level']['name']}: provers on {models}, six checks each, cost against serving."
    return page("Inference proofs", desc, body, "home", "", "home")
