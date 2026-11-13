"""The overview (`index.html`): the ladder (RFC-0018 SI-1). The frontier headline, then one section
per model, largest first: its head (model, publisher, total parameters, the serving
baseline) and its rows in the board's order (OR-5), then the systems not run (SI-4). Rows sort
only by the order rule: no column head re-sorts them. Also the figure cells the system pages use.
"""

from . import state as S
from .chrome import CHECKS_PAGE, footer, header, level_words, page, rung_of
from .hexagon import glyph_svg
from .words import (
    CAUSE_WORD,
    CHECK_NAME,
    FIGURE_NAME,
    FULL_LOAD_WORD,
    NULL_WORD,
    PETAL_NAME,
    REFERENCE_WORD,
    SEP,
    STATE_WORD,
    STEP_WORD,
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
ROW_GLYPH = 3  # the row glyph's unit in px: its arms carry their names (159 by 87 px)
# a phone's row glyph, px a unit, no names (37.5 by 46.5 px): whole device pixels at 2x
PHONE_GLYPH = 1.5


def states(row):
    """The five petals, in the glyph's order (GL-5), as glyph_svg draws them: each with its state,
    step, cause and form (view._glyph)."""
    return row["glyph"]


def petal_words(p):
    """A petal's step in words, and for a red or hollow petal its cause (§The glyph, step table;
    GL-1, GL-3)."""
    words = STEP_WORD[p["step"]]
    return f"{words}, {CAUSE_WORD[p['cause']]}" if p["cause"] is not None else words


def states_words(row):
    """The petals in words, for screen readers (the glyph is drawn, not read); one span per
    petal, its name in <b>, which words.js shows beside a petal pointed at. It sits in the
    glyph's cell, so the row's header reads the name and standing only."""
    return "; ".join(f"<span><b>{e(PETAL_NAME[p['id']])}</b> {e(petal_words(p))}</span>"
                     for p in row["glyph"])  # fmt: skip


def name_of(row):
    return S.V["systems"][row["system"]]["name"]


def href(row):
    return f"/{row['page']}"


def fig_html(f, n=None, sub=None, why=None):
    """One stored figure: the number in a reading unit, its labels in its title, and under it its
    scope in a word and its sample size (AGENTS.md rule 2). `sub` replaces the line under it; `why`
    replaces a null figure's reason (NO_STEADY_WORD on a row with no steady state)."""
    if f is None:
        return '<span class="na">not recorded</span>'
    if f["value"] is None:
        why = why or NULL_WORD[f["null_reason"]]
        return (
            f'<span class="na" title="{e(labels(f))}">none</span><span class="sub">{e(why)}</span>'
        )
    num, unit = number(f["value"], f["unit"])
    x = " x" if f["unit"] == "ratio" else ""
    line = sub if sub is not None else sub_words(f, n)
    return (f'<span class="fig" title="{e(labels(f))}"><span class="n">{e(num)}</span>'
            f'<span class="u{x}">{e(unit)}</span></span>'
            + (f'<span class="sub">{sub_line(line)}</span>' if line else ""))  # fmt: skip


def sub_line(line):
    """The line under a figure, escaped, its dot in a span (a phone's ladder row breaks the line
    there instead, scope over n)."""
    return e(line).replace(SEP, f'<span class="sep">{SEP}</span>')


def has(f):
    return f is not None and f["value"] is not None


def nobreak(text):
    """Words escaped, a short token that holds a hyphen ("17B-128E", "Apache-2.0") kept on one
    line; a long one (a repository name) may still break."""
    return " ".join(f'<span class="nw">{e(t)}</span>' if "-" in t and len(t) <= 12 else e(t)
                    for t in str(text).split(" "))  # fmt: skip


def counted(row):
    """The counted sessions a row's figures are over."""
    return len(row["sessions"]) or None


def lead_fig(row):
    """A row's one figure, labelled for what it is (CO-5): the multiple of serving; with no
    steady state, the whole sessions' multiple, named so in its label; else the multiple's
    null. Returns (label, figure)."""
    figs = row["figures"]
    m, cold = figs["multiple"], figs["session_multiple"]
    if not has(m) and has(cold):
        n = rung_of(row)["requests_per_session"]
        return (f"{FIGURE_NAME['multiple']}, whole sessions of {n:,} replies",
                fig_html(cold, counted(row)))  # fmt: skip
    return FIGURE_NAME["multiple"], fig_html(m, counted(row))


def multiple_html(row):
    """CO-5: the multiple; with no steady state, the session cost over serving, labelled as whole
    sessions."""
    figs = row["figures"]
    m = figs["multiple"]
    if m is not None and m["value"] is not None:
        return fig_html(m, counted(row)) + split_html(row)
    cold = figs["session_multiple"]
    if cold is not None and cold["value"] is not None:
        n = rung_of(row)["requests_per_session"]
        count = cold["n"] if cold["n"] is not None else counted(row)
        return fig_html(cold, sub=f"whole sessions of {n:,} replies{SEP}n\u00a0=\u00a0{count}")
    return fig_html(m)


def split_html(row):
    """CO-7: under the multiple, its proving and generation parts as two figures, with a bar of
    their shares of m, where the system generates in a phase of its own; nothing otherwise."""
    figs = row["figures"]
    p, g = figs.get("proving_multiple"), figs.get("generation_multiple")
    if not p or not g or p["value"] is None or g["value"] is None:
        return ""
    share = 100 * p["value"] / (p["value"] + g["value"])
    # each share at its own length; one too short to see is marked by a line where it ends (as plots.hbar)
    nib = f'<line class="nib" x1="{share:.2f}" x2="{share:.2f}" y2="4"/>' if share < 1.5 else ""
    bar = (f'<svg class="sbar" viewBox="0 0 100 4" preserveAspectRatio="none" aria-hidden="true">'
           f'<rect class="bp" width="{share:.2f}" height="4"/>'
           f'<rect class="bg" x="{share:.2f}" width="{100 - share:.2f}" height="4"/>{nib}</svg>')  # fmt: skip

    def part(name, f, cls):
        num, unit = number(f["value"], f["unit"])
        return (
            f'<span class="part {cls}" title="{e(labels(f))}"><span class="pn">{e(num)}'
            f'<span class="px">{e(unit)}</span></span><span class="pl">{name}</span></span>'
        )

    return (
        f'<span class="split">{bar}{part("proving", p, "pp")}{part("generation", g, "pg")}</span>'
    )


def kl_html(row):
    fid = row["fidelity"] or {}
    kl = fid.get("kl")
    if kl is not None and kl["value"] is not None:
        return fig_html(kl)
    note = fid.get("kl_note") or "not measured"
    return f'<span class="na" title="{e(note)}">not measured</span>'


def position_html(row, rung):
    """A row's position as a square, position 1 solid paper, the others an outline; the count run
    under it. A row with no position keeps the square, a dash in it and no count (the dash is
    drawn, not read out: the cell is empty to a screen reader), so every row starts alike."""
    if row["position"] is None:
        return '<span class="pos p0"><span class="pn" aria-hidden="true">\u2013</span></span>'
    lead = " p1" if row["position"] == 1 else ""
    return (f'<span class="pos{lead}"><span class="pn">{row["position"]}</span>'
            f'<span class="of">of {rung["systems_run"]}</span></span>')  # fmt: skip


def not_passed(row):
    """The standing of a row that has not passed: "not passed" with a failed check, "not passed
    yet" while every check not held is undecided (RFC-0018: an undecided check is never worded as
    a failure)."""
    failed = any(c["state"] == "failed" for c in row["checks"])
    return "not passed" if failed else "not passed yet"


def standing(row):
    """Passed (a system on a model, SI-6), passed and unranked with why, or not passed with the
    checks not held (SI-1), each named as a check."""
    if row["passed"] and not row["ranked"]:
        return f"passed, unranked: {row['unranked_reason']}"
    if row["passed"]:
        return "passed"
    missing = [f"{CHECK_NAME[c['id']]} check {STATE_WORD[c['state']]}" for c in row["checks"]
               if c["state"] != "held"]  # fmt: skip
    return f"{not_passed(row)}: " + ", ".join(missing) if missing else not_passed(row)


def defined(words, anchor):
    """Words linked to where the checks page defines them (a short hyphened token on one line)."""
    return f'<a class="df" href="{CHECKS_PAGE}#{anchor}">{nobreak(words)}</a>'


def standing_html(row, page=None):
    """`standing` on the overview: passed and unranked link to their definitions, each check not
    held to its row on the system page (its cause and evidence). `page` is the address of that
    page from where the words are printed ("" on the page itself)."""
    if row["passed"] and not row["ranked"]:
        return (f"{defined('passed', 'passed')}, {defined('unranked', 'unranked')}: "
                f"{e(row['unranked_reason'])}")  # fmt: skip
    if row["passed"]:
        return defined("passed", "passed")
    at = href(row) if page is None else page
    missing = [f'<a class="df" href="{e(at)}#ck-{c["id"]}">{e(CHECK_NAME[c["id"]])} check</a> '
               f"{e(STATE_WORD[c['state']])}" for c in row["checks"] if c["state"] != "held"]  # fmt: skip
    return f"{not_passed(row)}: " + ", ".join(missing) if missing else not_passed(row)


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
    multiple, else its whole sessions, so one row never mixes two scopes."""
    figs = row["figures"]
    steady = figs["multiple"].get("value") is not None
    return figs["steady_usd_per_reply" if steady else "session_usd_per_reply"]


def row_html(row, rung):
    glyph = glyph_svg(ROW_GLYPH, states(row), names=[PETAL_NAME[p["id"]] for p in row["glyph"]])
    # the same petals with no names, drawn in place of the first on a phone (words.css shows one)
    glyph += glyph_svg(PHONE_GLYPH, states(row), cls="pie-svg gsh")
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
        f'<td class="cg"><span class="sr pw">{states_words(row)}</span>'
        f'<a class="glyph" href="{e(href(row))}" tabindex="-1" aria-hidden="true">{glyph}</a></td>'
        f'<th class="csys" scope="row"><a class="sname" href="{e(href(row))}">{e(name_of(row))}</a>'
        f'<span class="st">{standing_html(row)}</span></th>{figs}</tr>'
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
            f'{fig_html(b["gpu_seconds_per_reply"], sub=FULL_LOAD_WORD)}</p>')  # fmt: skip


def serving_words(b):
    gpus = f"{b['gpus']} × H200" if b["gpus"] else "GPUs not recorded"
    return f"{engine_words()}, {gpus}, full load at {b['concurrency']:,} concurrent requests"


def rung_meta(rung):
    """A model's head as labelled facts: publisher, parameters, the serving baseline (CO-4) and
    its GPU time per reply, "full load" under it (the Serving fact names the concurrency)."""
    b = rung["baseline"]
    facts = [("Publisher", e(rung["publisher"])),
             ("Parameters", nobreak(architecture(rung["parameters_total"],
                                                 rung.get("parameters_active"))))]  # fmt: skip
    if b is None:
        facts.append(("Serving", "not run yet"))
    elif not has(b["gpu_seconds_per_reply"]):
        facts.append(("Serving", e(b["cause"] or "no full load recorded")))
    else:
        facts.append(("Serving", e(serving_words(b))))
        facts.append(("Serving GPU time per reply",
                      fig_html(b["gpu_seconds_per_reply"], sub=FULL_LOAD_WORD)))  # fmt: skip
    return '<dl class="meta">' + "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>"
                                         for k, v in facts) + "</dl>"  # fmt: skip


def rung_html(rung):
    """A model: a cobalt rule with its size in a tab, its name, its facts; then its rows, whose
    heads stay under the top bar with the size beside them while a long rung scrolls."""
    size = e(params(rung["parameters_total"]))
    head = (
        f'<header class="rh"><p class="rk">{size}</p>'
        f'<h2 class="rm" id="h-{e(rung["id"])}">{nobreak(rung["model"])}</h2>'
        f"{rung_meta(rung)}</header>"
    )
    if not rung["rows"]:
        body = '<p class="none">Not run yet.</p>'
    else:
        first = (f'<th scope="col"><span class="hk" aria-hidden="true">{size}</span>'
                 f'<span class="hm" aria-hidden="true">{nobreak(rung["model"])}</span>'
                 '<span class="sr">Position</span></th>'
                 '<th scope="col"><span class="sr">Petals</span></th>')  # fmt: skip
        ths = first + "".join(f'<th scope="col">{h}</th>' for h in ("System", *heads(rung)))
        rows = "".join(row_html(r, rung) for r in rung["rows"])
        cols = ('<colgroup><col class="c1"><col class="c2"><col class="c3"><col class="c4">'
                '<col class="c5"><col class="c6"><col class="c7"></colgroup>')  # fmt: skip
        body = (
            f'<table class="lad">{cols}<thead><tr>{ths}</tr></thead><tbody>{rows}</tbody></table>'
        )
    return (f'<section class="rung" id="{e(rung["id"])}" aria-labelledby="h-{e(rung["id"])}">'
            f"{head}{body}</section>")  # fmt: skip


def lead_words(rung):
    """Who leads on a model: position 1 (its name in display type), the systems that passed
    unranked, none passed (yet, while no row has a failed check), or not run yet."""
    rows = rung["rows"]
    first = [name_of(r) for r in rows if r["position"] == 1]
    if first:
        return f'<span class="bx-n">#1</span><span class="bx-w">{e(", ".join(first))}</span>'
    passed = [name_of(r) for r in rows if r["passed"]]
    failed = any(c["state"] == "failed" for r in rows for c in r["checks"])
    words = ("passed: " + ", ".join(passed) if passed
             else ("none passed" if failed else "none passed yet") if rows
             else "not run yet")  # fmt: skip
    return f'<span class="bx-q">{e(words)}</span>'


def frontier_html():
    """The band: the level and the request, the title on one line, then one block of ground ink
    for the largest model a system passed on (OR-6), or else the largest tried: its size, its name,
    who leads there, how many systems ran, and its position 1's multiple, labelled, with its scope
    and n. The block is a link to that model's rung. No other model is named in the band: the
    rungs under it are the list."""
    rungs, front = S.V["rungs"], S.V["frontier"]
    run = [r for r in rungs if r["rows"]]
    lead = front["rung"] if front else (run[0]["id"] if run else None)
    tag = "Largest model proved" if front else "Largest model tried"
    block = ""
    for rung in (r for r in rungs if r["id"] == lead):
        fig = ""
        if front:
            for row in (r for r in rung["rows"] if r["position"] == 1):
                label, f = lead_fig(row)
                fig += f'<span class="bx-f"><span class="bx-l">{e(label)}</span>{f}</span>'
        block = (
            f'<div class="bl"><a class="bx" href="#{e(rung["id"])}">'
            f'<span class="bx-p">{e(params(rung["parameters_total"]))}</span>'
            f'<span class="bx-k">{e(tag)}</span>'
            f'<span class="bx-m">{nobreak(rung["model"])}</span>'
            f'<span class="bx-s">{lead_words(rung)}</span>'
            f'<span class="bx-c">{rung["systems_run"]:,} {"system" if rung["systems_run"] == 1 else "systems"} run</span>{fig}</a></div>'
        )
    title = "Proved inference, by model size" if run else "No system has run yet."
    return (f'<p class="bk"><span>{e(level_words())}</span><span>{e(request_words())}</span></p>'
            f'<h1 class="band-h">{e(title)}</h1>{block}')  # fmt: skip


def not_run_html():
    """The systems not run (SI-4), grouped by their reason, A to Z, each group's names A to Z
    in display type: each reason is said once."""
    if not S.V["not_run"]:
        return ""
    groups: dict[str, list[dict]] = {}
    for r in S.V["not_run"]:
        groups.setdefault(r["reason"], []).append(r)
    rows = "".join(
        f'<div><dt>{e(reason)}</dt><dd><ul class="nrl">'
        + "".join(f'<li id="nr-{e(r["id"])}"><span class="nn">{e(r["name"])}</span></li>'
                  for r in sorted(groups[reason], key=lambda r: r["name"].lower()))
        + "</ul></dd></div>"
        for reason in sorted(groups, key=str.lower)
    )  # fmt: skip
    return (f'<section class="notrun" aria-labelledby="h-notrun"><h2 class="nrh" id="h-notrun">'
            f'Systems not run</h2><dl class="nrg">{rows}</dl></section>')  # fmt: skip


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
