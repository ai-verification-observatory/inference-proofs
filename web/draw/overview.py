"""The overview (`index.html`): the ladder (RFC-0018 SI-1). The title, then one section per
model, largest first, the frontier's marked as the largest model proved: its head (model,
publisher, architecture, the serving baseline) and its rows in the board's order (OR-5), then
the systems not run (SI-4). Rows sort
only by the order rule: no column head re-sorts them. Also the figure cells the system pages use.
"""

from . import state as S
from .chrome import (
    CHECKS_PAGE,
    counted,
    footer,
    has,
    header,
    lead_figure,
    not_passed,
    page,
    parts_of,
    row_cost,
    rung_of,
)
from .hexagon import glyph_svg
from .words import (
    CAUSE_WORD,
    CHECK_NAME,
    FIDELITY_TITLE,
    FIGURE_HEAD,
    FRONTIER_WORD,
    FULL_LOAD_WORD,
    NULL_WORD,
    OF_WHICH,
    PETAL_NAME,
    REFERENCE_WORD,
    SCALE_NOT_RUN,
    SEP,
    STATE_WORD,
    STEP_WORD,
    WHOLE_SESSIONS,
    architecture,
    e,
    labels,
    number,
    params,
    sig,
    sub_words,
)

# what the checks do not test (the checks page)
NOT_TESTED = (
    "These six checks run each system's own prover and verifier from the outside. They do not "
    "attempt to cryptographically forge a proof or extract hidden weights: mathematical "
    "soundness and weight secrecy are reported from the publisher's documentation, not proved "
    "by our test suite."
)
ROW_GLYPH = 3  # the row glyph's unit in px: its arms carry their names (159 by 87 px)
# a phone's row glyph, px a unit, no names (62.5 by 77.5 px): whole device pixels at 2x
PHONE_GLYPH = 2.5


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


BARE = ""  # `fig_html`'s `sub` for a figure with no line under it


def fig_html(f, n=None, sub=None, why=None, note=None):
    """One stored figure: the number in a reading unit, its labels in its title, and under it its
    scope in a word and its sample size (AGENTS.md rule 2). `sub` replaces the line under it
    (`BARE`: no line, as the ladder and the Scale page print a figure; its labels stay in its
    title, `n` and `note` among them, and stand in full on the system's page); `why` replaces a
    null figure's reason (NO_STEADY_WORD on a row with no steady state)."""
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
    return (f'<span class="fig" title="{e(labels(f, n, note))}"><span class="n">{e(num)}</span>'
            f'<span class="u{x}">{e(unit)}</span></span>'
            + (f'<span class="sub">{sub_line(line)}</span>' if line else ""))  # fmt: skip


def sub_line(line):
    """The line under a figure, escaped, its dot in a span (a phone's ladder row breaks the line
    there instead, scope over n)."""
    return e(line).replace(SEP, f'<span class="sep">{SEP}</span>')


def nobreak(text):
    """Words escaped, a short token that holds a hyphen ("17B-128E", "Apache-2.0") kept on one
    line; a long one (a repository name) may still break."""
    return " ".join(f'<span class="nw">{e(t)}</span>' if "-" in t and len(t) <= 12 else e(t)
                    for t in str(text).split(" "))  # fmt: skip


def lead_fig(row, bare=False):
    """A row's one figure, labelled for what it is (CO-5, `chrome.lead_figure`). Returns (label,
    figure html); `bare` (the overview's band): the figure's plain name and the figure alone,
    what it is in its title."""
    label, f, _ = lead_figure(row)
    if bare:
        return FIGURE_HEAD["multiple"], multiple_html(row, parts=False, bare=True)
    return label, fig_html(f, counted(row))


def whole_note(row, key):
    """CO-5's label for a figure of the whole sessions, for its title; nothing for a steady one."""
    if key != "session_multiple":
        return None
    return WHOLE_SESSIONS.format(n=rung_of(row)["requests_per_session"])


def scope_note(row, f):
    """CO-5's label for any figure timed over the whole sessions (a session's cost beside its
    multiple), so the figures of one row carry the same scope words in their titles."""
    if f is None or f.get("scope") != "whole_wall":
        return None
    return WHOLE_SESSIONS.format(n=rung_of(row)["requests_per_session"])


def serving_missing(b, why="no full load recorded"):
    """A model's serving figure where the board holds none: "not run yet" with no serving run,
    "not measured" with one; the stored cause in its title."""
    word = "not run yet" if b is None or b.get("run_id") is None else "not measured"
    cause = (b or {}).get("cause") or why
    return f'<span class="na" title="{e(cause)}">{word}</span>'


def multiple_html(row, parts=True, bare=False):
    """CO-5: the multiple; with no steady state, the session cost over serving, labelled as whole
    sessions. With `parts`, its two parts under it (CO-7, `split_html`). `bare` (the ladder, the
    Scale page): the figures alone, no line of scope and n under any."""
    _, f, key = lead_figure(row)
    split = split_html(row, key, bare=bare) if parts else ""
    if bare:
        return fig_html(f, counted(row), sub=BARE, note=whole_note(row, key)) + (
            split if has(f) else ""
        )
    if key == "session_multiple":
        n = rung_of(row)["requests_per_session"]
        count = f["n"] if f["n"] is not None else counted(row)
        sub = f"{WHOLE_SESSIONS.format(n=n)}{SEP}n\u00a0=\u00a0{count}"
        return fig_html(f, counted(row), sub=sub) + split
    return fig_html(f, counted(row)) + (split if has(f) else "")


def split_html(row, key, bar=True, of_which=False, bare=False):
    """CO-7: under a multiple (`key`: the steady one or the whole sessions'), its two parts, each
    a figure with its scope and n (`bare`: the figure alone, where the whole above them says both
    once), after a bar of their shares, where the system generates in a phase of its own; nothing
    otherwise. The part that is not generation first, in paper."""
    parts = parts_of(row, key)
    if not parts:
        return ""
    (w1, f1), (w2, f2) = parts
    share = 100 * f1["value"] / (f1["value"] + f2["value"])
    svg = ""
    if bar:
        # each share at its own length; one too short to see is marked by a line where it ends
        nib = f'<line class="nib" x1="{share:.2f}" x2="{share:.2f}" y2="4"/>' if share < 1.5 else ""
        svg = (f'<svg class="sbar" viewBox="0 0 100 4" preserveAspectRatio="none" aria-hidden="true">'
               f'<rect class="bp" width="{share:.2f}" height="4"/>'
               f'<rect class="bg" x="{share:.2f}" width="{100 - share:.2f}" height="4"/>{nib}</svg>')  # fmt: skip
    n = counted(row)
    pre = f"{OF_WHICH} " if of_which else ""  # with no bar, the words tie each part to its whole
    line, note = (BARE, whole_note(row, key)) if bare else (None, None)
    out = "".join(f'<span class="part {c}"><span class="pl">{e(pre + w)}</span>'
                  f"{fig_html(f, n, sub=line, note=note)}</span>"
                  for c, w, f in (("pp", w1, f1), ("pg", w2, f2)))  # fmt: skip
    return f'<span class="split">{svg}{out}</span>'


def fidelity_word(row, page=None):
    """A row's fidelity as the surface prints it: the FIDELITY check's state in a word (held,
    failed, undecided: FI-6), linked to the Fidelity section of the system's page, which holds
    what it is read from. Its title carries the stored figures: the replies' mean count of
    leading tokens equal to the original's (FI-3), the rung's bar (FI-5) and n. The closeness
    grade is the glyph's Faithful model petal; KL is under Fidelity on the system's page."""
    check = next(c for c in row["checks"] if c["id"] == "fidelity")
    mine, bar = row["fidelity"], (rung_of(row)["fidelity"] or {}).get("bar")
    title = []
    if mine is not None and mine.get("mean_prefix") is not None:
        title.append(f"{FIDELITY_TITLE}: {sig(mine['mean_prefix'])} tokens")
        if bar is not None:
            title.append(f"bar: {sig(bar['mean_prefix'])} tokens")
        title += [f"n = {mine['n']:,} replies", f"record: {row['record']}/fidelity"]
    at = href(row) if page is None else page
    return (f'<a class="fw {e(check["state"])}" href="{e(at)}#fidelity" '
            f'title="{e("; ".join(title))}">{e(STATE_WORD[check["state"]])}</a>')  # fmt: skip


def position_html(row, rung):
    """A row's position as a square, position 1 solid paper, the others an outline; the count run
    under it. A row with no position keeps the square, a dash in it and no count (the dash is
    drawn, not read out: a screen reader reads "no position"), so every row starts alike."""
    if row["position"] is None:
        return ('<span class="pos p0"><span class="pn" aria-hidden="true">\u2013</span>'
                '<span class="sr">no position</span></span>')  # fmt: skip
    lead = " p1" if row["position"] == 1 else ""
    return (f'<span class="pos{lead}"><span class="pn">{row["position"]}</span>'
            f'<span class="of">of {rung["systems_run"]}</span></span>')  # fmt: skip


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
    missing = [f'<span class="ckn"><a class="df" href="{e(at)}#ck-{c["id"]}">'
               f'{e(CHECK_NAME[c["id"]])} check</a> {e(STATE_WORD[c["state"]])}</span>'
               for c in row["checks"] if c["state"] != "held"]  # fmt: skip
    state = f'<span class="nw">{e(not_passed(row))}{":" if missing else ""}</span>'
    # each comma inside the span of the check it follows, so a line never starts with one
    listed = " ".join(m.replace("</span>", ",</span>") if i < len(missing) - 1 else m
                      for i, m in enumerate(missing))  # fmt: skip
    return f"{state} {listed}" if missing else state


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


FIGURES = ("multiple", "cost", "check-time", "fidelity")  # the figure columns, in the row's order


def heads():
    """The figure columns' heads (`FIGURE_HEAD`: no word its unit says), each linked to its
    definition on the checks page."""
    return [defined(FIGURE_HEAD[f], f) for f in FIGURES]


def row_html(row, rung):
    glyph = glyph_svg(ROW_GLYPH, states(row), names=[PETAL_NAME[p["id"]] for p in row["glyph"]])
    # the same petals with no names, drawn in place of the first on a phone (words.css shows one)
    glyph += glyph_svg(PHONE_GLYPH, states(row), cls="pie-svg gsh")
    cost = row_cost(row)
    cells = (
        ("cm", multiple_html(row, bare=True)),
        ("cc", fig_html(cost, counted(row), sub=BARE, note=scope_note(row, cost))),
        ("ct", fig_html(row["figures"]["verify_seconds_per_reply"], counted(row), sub=BARE)),
        ("ck", fidelity_word(row)),
    )
    figs = "".join(f'<td class="{c}"><span class="lbl">{h}</span>{html}</td>'
                   for (c, html), h in zip(cells, heads(), strict=True))  # fmt: skip
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
    # no figure: the ladder's state word, the stored cause in its title
    if b is None or not has(b["gpu_seconds_per_reply"]):
        return f'<p class="rb"><span class="k">Serving</span> {serving_missing(b)}</p>'
    gpus = f"{b['gpus']} × H200" if b["gpus"] else "GPUs not recorded"
    return (f'<p class="rb"><span class="k">Serving</span> {e(engine_words())}, {e(gpus)}, '
            f"full load at {b['concurrency']:,} concurrent requests: "
            f'{fig_html(b["gpu_seconds_per_reply"], sub=FULL_LOAD_WORD)}</p>')  # fmt: skip


def serving_words(b):
    gpus = f"{b['gpus']} × H200" if b["gpus"] else "GPUs not recorded"
    return f"{engine_words()}, {gpus}, full load at {b['concurrency']:,} concurrent requests"


def rung_meta(rung):
    """A model's head as labelled facts: publisher, architecture (the tab says its size: a
    mixture of experts names its active parameters only, as the Scale page's head does) and its
    serving GPU time per reply (CO-4), the figure every multiple under it is over. How it was
    served (engine, GPUs, concurrency) is on a system's page, under Cost."""
    b = rung["baseline"]
    facts = [("Publisher", e(rung["publisher"])),
             ("Architecture", nobreak(architecture(rung["parameters_total"],
                                                   rung.get("parameters_active"), sized=False)))]  # fmt: skip
    if b is None or not has(b["gpu_seconds_per_reply"]):
        facts.append(("Serving", serving_missing(b)))
    else:
        facts.append((FIGURE_HEAD["serving"],
                      fig_html(b["gpu_seconds_per_reply"], sub=BARE)))  # fmt: skip
    return '<dl class="meta">' + "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>"
                                         for k, v in facts) + "</dl>"  # fmt: skip


def rung_html(rung):
    """A model: a cobalt rule with its size in a tab, its name, its facts; then its rows, whose
    heads stay under the top bar with the size beside them while a long rung scrolls. The
    frontier's rung (OR-6: the largest with a passed row) says so beside its tab."""
    size = e(params(rung["parameters_total"]))
    front = S.V["frontier"]
    mark = f'<p class="rf">{e(FRONTIER_WORD)}</p>' if front and front["rung"] == rung["id"] else ""
    head = (
        f'<header class="rh"><p class="rk">{size}</p>{mark}'
        f'<h2 class="rm" id="h-{e(rung["id"])}">{nobreak(rung["model"])}</h2>'
        f"{rung_meta(rung)}</header>"
    )
    if not rung["rows"]:
        body = f'<p class="none">{e(SCALE_NOT_RUN)}</p>'
    else:
        first = (f'<th scope="col"><span class="hk" aria-hidden="true">{size}</span>'
                 f'<span class="hm" aria-hidden="true">{nobreak(rung["model"])}</span>'
                 '<span class="sr">Position</span></th>'
                 '<th scope="col"><span class="sr">Petals</span></th>')  # fmt: skip
        ths = first + "".join(f'<th scope="col">{h}</th>' for h in ("System", *heads()))
        rows = "".join(row_html(r, rung) for r in rung["rows"])
        cols = ('<colgroup><col class="c1"><col class="c2"><col class="c3"><col class="c4">'
                '<col class="c5"><col class="c6"><col class="c7"></colgroup>')  # fmt: skip
        body = (
            f'<table class="lad">{cols}<thead><tr>{ths}</tr></thead><tbody>{rows}</tbody></table>'
        )
    return (f'<section class="rung" id="{e(rung["id"])}" aria-labelledby="h-{e(rung["id"])}">'
            f"{head}{body}</section>")  # fmt: skip


def band_html():
    """The band: the title on one line, and nothing else. The frontier (OR-6) is not named here:
    its rung, in the ladder under the band, is marked as the largest model proved (`rung_html`),
    and its rows say who passed there, at what multiple and how many systems ran."""
    run = any(r["rows"] for r in S.V["rungs"])
    title = "Proved inference, by model size" if run else "No system has run yet."
    return f'<h1 class="band-h">{e(title)}</h1>'


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
  <section class="mast"><div class="mast-in">{band_html()}</div></section>
  <div class="wrap ladder">{rungs}</div>
  <div class="wrap">{not_run_html()}</div>
</main>
{footer()}"""
    models = ", ".join(r["model"] for r in S.V["rungs"])
    desc = f"Provers on {models}: six checks each, and what a proved reply costs against serving."
    return page("Inference proofs", desc, body, "home", "", "home")
