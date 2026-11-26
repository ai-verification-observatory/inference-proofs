"""The overview (`index.html`): the ladder (RFC-0018 SI-1, amended 2026-11-23, Q54). The title,
then one board: the figure columns' heads, printed once and kept under the top bar; then one table
per model, largest first, opened by its divider (its size in a tab, its name, its serving rate, its
copies' Fidelity), which stays under the heads while its rows pass, then its rows in the board's
order (OR-5); then the systems not run (SI-4); then the partners. Rows sort only by the order rule: no column head
re-sorts them. What the layout already shows is not printed (the largest model with a passed row,
a position's count, "Passed" beside a position, "proved" on the rate under the multiple), and a
screen reader still hears it. Also the figure cells the system pages use.
"""

from . import state as S
from .chrome import (
    CHECKS_PAGE,
    MANDATE_PAGE,
    ONLY_RUN,
    batch_words,
    counted,
    fig_words,
    footer,
    further,
    has,
    header,
    how_computed,
    lead_figure,
    mark_shape,
    not_passed,
    not_split,
    page,
    proving_figure,
    rate_pair,
    rung_of,
    serving_gpu,
    version,
)
from .glossary import term
from .hexagon import glyph_svg
from .words import (
    BASIS_BITS,
    CAUSE_WORD,
    CHECK_NAME,
    CHECK_PLAIN,
    CONTROL_NAME,
    COPY_FIG_TITLE,
    COPY_WORD,
    FIDELITY_AGAINST,
    FIDELITY_CHECK_TITLE,
    FIDELITY_FIG_TITLE,
    FIDELITY_PROVED_TITLE,
    FIDELITY_TITLE,
    FIGURE_ANCHOR,
    FIGURE_ASK,
    FIGURE_ASK_FURTHER,
    FIGURE_HEAD,
    FORMAT_WORD,
    FULL_LOAD_WORD,
    FURTHER,
    GRADE_WORD,
    LADDER_COLS,
    NOT_SPLIT,
    NULL_WORD,
    PETAL_NAME,
    PETAL_PLAIN,
    PROVED_HEAD,
    RATE_HOW,
    RATE_IS,
    RATE_PER,
    RATE_PROVED,
    REFERENCE_WORD,
    SCALE_NOT_RUN,
    SCOPE_WORD,
    SEP,
    STATE_WORD,
    STEADY_STATE,
    TIER_WORD,
    WHOLE_SESSIONS,
    WHY_HEAD,
    WHY_TOP_TOKEN,
    e,
    labels,
    number,
    params,
    petal_step,
    range_words,
    session_count,
    shown,
    sig,
    sub_words,
)

# what the checks do not test (the checks page, #not-tested; RFC-0018 Non-Goals)
NOT_TESTED = (
    "None of our checks try to forge a proof. Soundness and weight secrecy are not tested by "
    "our harness; instead, the glyph grades what each publisher states and proves."
)
# the binding-only gap (RFC-0018 SI-4, SI-4a), on the checks page beside NOT_TESTED
BINDING_GAP = (
    "Three checks alter one input that the verifier must reject, and the other three test "
    "honest runs. A trivial system whose proof is just a keyed hash of the commitment, prompt, "
    "and reply computed from the weights would pass all six checks and appear on the ladder as "
    "Passed. However, it would receive no ranking position: ranking requires a recorded "
    "publisher statement (or our reading of one) that an accepted proof guarantees the "
    "committed model's own greedy reply."
)
ROW_GLYPH = 3  # a glyph's unit in px where its arms carry their names (159 by 87 px)
# the ladder row's glyph, at every width (amended 2026-11-23, Q54): its arms without their names
# (50 by 62 px); each arm's name and grade are one hover away (words.js, from `states_words`) and
# one click away, on the system page's Criteria
LADDER_GLYPH = 2


def states(row):
    """The five petals, in the glyph's order (GL-5), as glyph_svg draws them: each with its state,
    step, cause and form (view._glyph)."""
    return row["glyph"]


def petal_words(p):
    """A petal's step in words, and for a Not decided petal what it waits on (§The glyph, step
    table, amended 2026-11-16; GL-3): Not met, Failed and Not stated already say their cause."""
    words = petal_step(p)
    return f"{words}, {CAUSE_WORD[p['cause']]}" if p["step"] is None else words


def states_words(row):
    """The petals in words, for screen readers (the glyph is drawn, not read): "Integrity:
    Partly met"; one span per petal, its name in <b>, which words.js shows beside a petal
    pointed at with the petal's plain sentence (`data-plain`, not read out): the ladder's glyph
    draws no names, so this is where a pointer finds them. It sits in the glyph's cell, so the
    row's header reads the name and standing only."""
    return "; ".join(f'<span data-plain="{e(PETAL_PLAIN[p["id"]])}"><b>{e(PETAL_NAME[p["id"]])}'
                     f"</b>: {e(petal_words(p))}</span>" for p in row["glyph"])  # fmt: skip


def name_of(row):
    return S.V["systems"][row["system"]]["name"]


def href(row):
    return f"/{row['page']}"


BARE = ""  # `fig_html`'s `sub` for a figure with no line under it
RATE_ANCHOR = "tokens"  # the Cost section's line on the two rates, on a system's page


def fig_html(f, n=None, sub=None, why=None, note=None, how=None, unit=None):
    """One stored figure: the number in a reading unit, its labels in its title, and under it its
    scope in a word and its sample size (AGENTS.md rule 2). `sub` replaces the line under it
    (`BARE`: no line, as the ladder and the Overview page print a figure; its labels stay in its
    title, `n` and `note` among them, and stand in full on the system's page); `why` replaces a
    null figure's reason (NO_STEADY_WORD on a row with no steady state); `how` opens the title
    with how the figure is computed (the headline's, `how_computed`); `unit` replaces the unit's
    words (a rate's GPU named: "tokens/s per H200")."""
    if f is None:
        return '<span class="na">not recorded</span>'
    if f["value"] is None:
        why = why or NULL_WORD[f["null_reason"]]
        return (
            f'<span class="na" title="{e(labels(f))}">none</span><span class="sub">{e(why)}</span>'
        )
    num, said = number(f["value"], f["unit"])
    unit = unit or said
    x = " x" if f["unit"] == "ratio" else ""
    line = sub if sub is not None else sub_words(f, n)
    # the probe (words.js) prints a title's "key: value" parts, split at "; ", one row each: the
    # method sentence keeps a key of its own and holds no "; "
    title = f"how: {how.rstrip('.')}; {labels(f, n, note)}" if how else labels(f, n, note)
    return (f'<span class="fig" title="{e(title)}"><span class="n">{e(num)}</span>'
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
    figure html); `bare` (the ladder's band): the figure's plain name and the figure alone,
    what it is in its title."""
    label, f, _ = lead_figure(row)
    if bare:
        return FIGURE_HEAD["multiple"], multiple_html(row, bare=True)
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


def whole_line(row, count):
    """What a figure of the whole sessions counted, as the line under it says it: their number,
    then CO-5's label whole ("3 whole sessions of 120 replies")."""
    label = WHOLE_SESSIONS.format(n=rung_of(row)["requests_per_session"])
    if count is None:
        return label
    return f"{label}{SEP}{session_count(count)}" if count == 1 else f"{count:,} {label}"


def further_line(count):
    """What a figure of a further reply counted, as the line under it says it (CO-9): "further
    reply · 3 sessions"."""
    return SEP.join([FURTHER, *([session_count(count)] if count is not None else [])])


def proving_html(row, bare=False, to=None, batch=True):
    """CO-9 (Q55): the row's proving multiple, beside its total on every surface; "not measured"
    where the board splits no generation from the further reply, the board's cause in its title
    (and in words under Cost: DEPTH law 2). `bare` and `to` as `multiple_html`'s; `batch`: under
    it, the replies one proof covers, which the proving part depends on (its source in its
    title). Nothing on a board built by the whole-session rule."""
    f = proving_figure(row)
    if f is None:
        return ""
    if has(f):
        count = f["n"] if f["n"] is not None else counted(row)
        sub = BARE if bare else further_line(count)
        how = how_computed(row, "further_reply_proving_multiple")
        fig = to_section(fig_html(f, counted(row), sub=sub, how=how), to)
    else:
        fig = f'<span class="na nsp" title="{e(not_split(row))}">{e(NOT_SPLIT)}</span>'
    words = batch_words(row) if batch else None
    if not words:
        return fig
    src = (row.get("proving_batch") or {}).get("source")
    title = f' title="{e(f"proving batch: {words}; record: {src}")}"' if src else ""
    return f'{fig}<span class="cmx"><span class="bat"{title}>{e(words)}</span></span>'


def steady_line(count):
    """What a steady figure counted, as the line under it says it (CO-3): "steady state · 3
    sessions"."""
    return SEP.join([STEADY_STATE, *([session_count(count)] if count is not None else [])])


def serving_missing(b, why="no full load recorded"):
    """A model's serving figure where the board holds none: "not run yet" with no serving run,
    "not measured" with one; the stored cause in its title."""
    word = "not run yet" if b is None or b.get("run_id") is None else "not measured"
    cause = (b or {}).get("cause") or why
    return f'<span class="na" title="{e(cause)}">{word}</span>'


def to_section(html, to):
    """A figure linked to its section of the system's page (`to`, its address), on the ladder:
    the row leads to the page, a figure to where it was taken (DEPTH law 1). None: as it is."""
    return f'<a class="flk" href="{e(to)}">{html}</a>' if to else html


def multiple_html(row, bare=False, to=None, rates=None):
    """CO-5: the multiple; with no steady state, the session cost over serving, labelled as whole
    sessions. Its two parts (CO-7) are not printed with it: since 2026-11-17 they print only in
    the system page's Cost block (`pages.parts_tile`). `bare` (the ladder, the
    Overview page): the figures alone, no line of scope and n under any; `to` (the ladder): the
    figure linked there. `rates` (the ladder only, amended 2026-11-16, 2026-11-23): under it, the
    line of the proved rate (`rate_html`, its word "proved" heard, not printed), linked to that
    address, in one block (`cmx`) that a phone sets under the multiple."""
    _, f, key = lead_figure(row)
    split = ""
    if rates is not None:
        under = rate_html(row, rates, said=False)
        split = f'<span class="cmx">{under}</span>' if under else ""
    how = how_computed(row)
    if bare:
        fig = fig_html(f, counted(row), sub=BARE, note=whole_note(row, key), how=how)
        return (to_section(fig, to) if has(f) else fig) + (split if has(f) else "")
    if key == "session_multiple":
        count = f["n"] if f["n"] is not None else counted(row)
        return fig_html(f, counted(row), sub=whole_line(row, count), how=how) + split
    if key == "further_reply_multiple" and has(f):
        count = f["n"] if f["n"] is not None else counted(row)
        return fig_html(f, counted(row), sub=further_line(count), how=how) + split
    if not has(f):
        return fig_html(f, counted(row))
    count = f["n"] if f["n"] is not None else counted(row)
    return fig_html(f, counted(row), sub=steady_line(count), how=how) + split


def rate_html(row, to, said=True):
    """The proved rate, in one small line under the multiple (CO-8, amended 2026-11-17):
    "2.027 proved", then its unit and GPU, "tokens/s per H200"; the request's reply tokens per
    GPU-second, linked to `to` (the Cost section's line on the two rates, where their scope, n,
    range and GPUs are printed: DEPTH law 3). The served rate is not repeated here: the model's
    divider prints it once for all its rows (`served_html`), in the same unit. `said` False (the
    ladder, amended 2026-11-23, Q54): "proved" is heard, not printed, the rate standing under the
    model's served rate in the same column. The title says how the two read against the multiple
    (served over proved is it) and carries each rate's labels and record. Nothing where the row
    has no pair (`rate_pair`)."""
    pair = rate_pair(row)
    if pair is None:
        return ""
    proved, served, gp, _ = pair
    pn = number(proved["value"], proved["unit"])[0]
    word = e(RATE_PROVED) if said else f'<span class="sr">{e(RATE_PROVED)}</span>'
    words = (f'<span class="rp"><span class="n">{e(pn)}</span> {word}</span>'
             f'<span class="sr">, </span><span class="ru">{e(RATE_PER.format(gpu=gp))}</span>')  # fmt: skip
    _, lead, _ = lead_figure(row)
    count = proved["n"] if proved["n"] is not None else counted(row)
    whole = (SCOPE_WORD[proved["scope"]] if proved["scope"] == "prove.session"
             else WHOLE_SESSIONS.format(n=rung_of(row)["requests_per_session"]))  # fmt: skip
    spread = range_words(proved)
    b = rung_of(row)["baseline"]
    title = [RATE_HOW.format(tokens=f"{S.V['request']['output_tokens']:,}"),
             RATE_IS.format(multiple=fig_words(lead)),
             f"proved: {shown(proved['value'], proved['unit'])}, {whole}, n = {count:,} sessions"
             + (f", range {spread}" if spread else "") + f", on {gp}",
             f"served: {shown(served['value'], served['unit'])}, {serving_words(b)}",
             f"grade: {GRADE_WORD[proved['grade']]}", f"evidence: {TIER_WORD[proved['tier']]}",
             f"record: {proved['source']}", f"record: {served['source']}"]  # fmt: skip
    return f'<a class="rts" href="{e(to)}" title="{e("; ".join(title))}">{words}</a>'


# a part's glossary entry, where it has one (D1: a term the surface prints is one click away)
PART_TERM = {"generation": "Generation", "commit and proving": "Commit and proving"}


def part_term(w):
    """A part's name, linked to its glossary entry where it has one."""
    return term(w, PART_TERM[w]) if w in PART_TERM else e(w)


def pct(v):
    """A percentage as the site prints it: one decimal."""
    return f"{v:.1f}"


def tf_record(tf, entry):
    """Where the board holds a teacher-forced entry's percentage (`tf["record"]`, the block's
    pointer; a printed percentage names its value there), found by the entry itself."""
    at = next((f"rows/{k}" for k, v in tf["rows"].items() if v is entry), None)
    if at is None:
        at = next(f"controls/{i}" for i, c in enumerate(tf["controls"]) if c is entry)
    return f"{tf['record']}/{at}/percent"


def agree_title(entry, tf):
    """FI-10's agreement's labels, for its title, each with its key (the probe gives each its
    row): its mean of the pass's positions, n, the interval where the board computed one, and its
    record. The system page's Fidelity table and the ladder's copies print the same."""
    said = (
        f"mean: {sig(entry['mean'])} of {tf['positions']:,} positions; n = {entry['n']:,} prompts"
    )
    if entry.get("percent_interval"):
        low, high = entry["percent_interval"]
        said += f"; interval: 95\u00a0%, {pct(low)} to {pct(high)}\u202f%"
    return f"{said}; record: {tf_record(tf, entry)}"


def copies_of(rung):
    """The rung's 8-bit and 4-bit copies that ran (their teacher-forced pass's controls), in
    FIDELITY_AGAINST's order. They are the rung's: its one pass runs them for every row, so the
    rows of a model always share them."""
    tf = rung.get("teacher_forced") or {}
    by = {c["id"]: c for c in tf.get("controls") or []}
    return [by[i] for i in FIDELITY_AGAINST
            if i in by and by[i]["status"] == "ok" and by[i].get("percent") is not None]  # fmt: skip


def copies_html(rung):
    """The rung's 8-bit and 4-bit copies' Fidelity, once on its divider (SI-9, amended
    2026-11-23, Q54): each copy's plain name, then its figure with its unit, its labels in its
    title (what it is, then `agree_title`). Printed where a row of the model prints a Fidelity
    figure, which they are the scale of; "" where none does."""
    if not any(fidelity_row(r) for r in rung["rows"]):
        return ""
    tf = rung["teacher_forced"]
    out = []
    for c in copies_of(rung):
        title = f"{COPY_FIG_TITLE.format(copy=CONTROL_NAME[c['id']])}; {agree_title(c, tf)}"
        out.append(f'<span class="dcy"><span class="dcl">{e(COPY_WORD[c["id"]])}</span> '
                   f'<span class="fig" title="{e(title)}"><span class="n">'
                   f'{e(pct(c["percent"]))}</span><span class="u">%</span></span></span>')  # fmt: skip
    return '<span class="sr">; </span>'.join(out)


def fidelity_row(row):
    """The record a row's Fidelity figure is printed from (its rung's teacher-forced pass), or
    None where the surface prints the check's state instead: no pass, a pass that failed, or one
    that gave another token than a proof states at a position one covers (FI-16: its code is not
    shown to be the proved model's)."""
    tf = rung_of(row).get("teacher_forced") or {}
    mine = (tf.get("rows") or {}).get(row["system"])
    if mine is None or mine["status"] != "ok" or mine.get("percent") is None:
        return None
    tie = mine.get("proved_tokens")
    if tie is not None and tie["agreeing"] != tie["positions"]:
        return None
    return mine


def bits_words(bits):
    """Weight bits at 3 significant digits, whole when integral ("4.84", "8")."""
    return f"{bits:,.0f}" if float(bits).is_integer() else sig(bits, 3)


def proved_words(row):
    """What the row proves (RFC-0018 SI-9, amended 2026-11-16): its weight bits from the workload
    record and its number format from the properties file, where that records one (never
    inferred from a format's name), then its activations, the part of the weights the bits cover
    where they cover a part, and "number format not stated" where the publisher states none:
    "proved: 4.84-bit integer weights, integer activations". Printed on the system page (the
    Fidelity block's Proved line, the Fidelity criterion), not on the ladder since 2026-11-23
    (Q54). "" where the row has no precision record."""
    p = row.get("precision") or {}
    if not p:
        return ""
    fmt = p.get("number_format") or {}
    w, a = (
        FORMAT_WORD.get((fmt.get(k) or {}).get("value", "")) for k in ("weights", "activations")
    )
    bits = p.get("bits")
    head = f"{bits_words(bits)}-bit " if isinstance(bits, int | float) else ""
    said = f"{PROVED_HEAD}: {head}{w + ' ' if w else ''}weights"
    if a:
        said += f", {a} activations"
    if p.get("bits_covers") == "part":
        said += ", for part of the weights"
    if fmt and not (w and a):  # recorded, and the publisher states no format for a part
        said += ("; number format not stated" if not (w or a)
                 else f"; {'activations' if w else 'weights'}' format not stated")  # fmt: skip
    return said


def proved_title(row):
    """The proved copy in a Fidelity figure's title: its id, its bits and how they were found,
    and what they cover."""
    p = row.get("precision") or {}
    if not p:
        return ""
    said = f"{PROVED_HEAD}: {p['proved']}"
    if isinstance(p.get("bits"), int | float):
        said += f", {bits_words(p['bits'])} bits per weight"
        if p.get("bits_covers") == "part":
            said += " for part of the weights"
        if how := BASIS_BITS.get(p.get("bits_basis") or ""):
            said += f", {how}"
    return said


def fidelity_word(row):
    """A row's Fidelity as the ladder prints it (RFC-0018 SI-9, amended 2026-11-14, 2026-11-23):
    FI-10's mean as a percentage of the reply's positions, linked to the Fidelity section of the
    system's page, alone in its cell: the copies it reads against stand once on its model's
    divider (`copies_html`), and what the row proves is on its system page. Its title says what
    it is, why top-token agreement, whose computation, the proved copy, the copies' ids, n and the
    record, and the Fidelity check's state, which it does not set, and the row's count against
    the proofs (FI-16). A row with no teacher-forced pass prints the check's state in a word, as
    before, and so does a row whose pass gave another token than a proof states at a position one
    covers."""
    tf = rung_of(row).get("teacher_forced") or {}
    mine = fidelity_row(row)
    if mine is None:
        return check_word(row)
    tie = mine.get("proved_tokens")
    check = next(c for c in row["checks"] if c["id"] == "fidelity")
    low_high = mine.get("percent_interval")
    why = WHY_TOP_TOKEN.format(tokens=S.V["request"]["output_tokens"])
    # each part "key: value", so the probe gives each its row (fig_html)
    copies = "copies: " + ", ".join(f"{COPY_WORD[i]} {i.upper()}" for i in FIDELITY_AGAINST)
    title = [FIDELITY_FIG_TITLE, f"why: {why.removeprefix(WHY_HEAD).rstrip('.')}",
             f"how: {mine['label']}", f"n = {mine['n']:,} prompts",
             *([f"interval: 95\u00a0%, {pct(low_high[0])} to {pct(low_high[1])}\u202f%"]
               if low_high else []),
             *([proved_title(row)] if proved_title(row) else []), copies,
             *([FIDELITY_PROVED_TITLE.format(**tie)] if tie is not None else []),
             FIDELITY_CHECK_TITLE.format(state=STATE_WORD[check["state"]]),
             f"record: {tf['record']}/rows/{row['system']}/percent"]  # fmt: skip
    return (f'<a class="fig fp" href="{e(href(row))}#fidelity" title="{e("; ".join(title))}">'
            f'<span class="n">{e(pct(mine["percent"]))}</span><span class="u">%</span></a>')  # fmt: skip


def check_word(row):
    """A row's fidelity as the surface prints it: the FIDELITY check's state in a word (held,
    failed, undecided: FI-6), linked to the Fidelity section of the system's page, which holds
    what it is read from. Its title carries the stored figures: the replies' mean count of
    leading tokens equal to the original's (FI-3), the rung's bar (FI-5) and n. The closeness
    grade is the glyph's Fidelity petal; KL is under Fidelity on the system's page."""
    check = next(c for c in row["checks"] if c["id"] == "fidelity")
    mine, bar = row["fidelity"], (rung_of(row)["fidelity"] or {}).get("bar")
    title = []
    if mine is not None and mine.get("mean_prefix") is not None:
        title.append(f"{FIDELITY_TITLE}: {sig(mine['mean_prefix'])} tokens")
        if bar is not None:
            title.append(f"bar: {sig(bar['mean_prefix'])} tokens")
        title += [f"n = {mine['n']:,} replies", f"record: {row['record']}/fidelity"]
    return (f'<a class="fw {e(check["state"])}" href="{e(href(row))}#fidelity" '
            f'title="{e("; ".join(title))}">{e(STATE_WORD[check["state"]])}</a>')  # fmt: skip


def position_html(row, rung):
    """A row's position as a square, position 1 solid paper, the others an outline. The count run
    is heard, not printed (amended 2026-11-23, Q54): the rows under the model's divider are few
    enough to count. A row with no position keeps the square, a dash in it (the dash is drawn,
    not read out: a screen reader reads "no position"), so every row starts alike. The only
    system run on its model (OR-4, amended 2026-11-17) holds position 1 against nothing: its
    square is an outline; its title and a screen reader say why."""
    if row["position"] is None:
        return ('<span class="pos p0"><span class="pn" aria-hidden="true">\u2013</span>'
                '<span class="sr">no position</span></span>')  # fmt: skip
    if rung["systems_run"] == 1:
        return (f'<span class="pos solo" title="{e(ONLY_RUN)}"><span class="pn">{row["position"]}'
                f'</span><span class="sr">, {e(ONLY_RUN)}</span></span>')  # fmt: skip
    lead = " p1" if row["position"] == 1 else ""
    return (f'<span class="pos{lead}"><span class="pn">{row["position"]}</span>'
            f'<span class="sr"> of {rung["systems_run"]}</span></span>')  # fmt: skip


def defined(words, anchor, title=None):
    """Words linked to where the checks page defines them (a short hyphened token on one line);
    `title`: what the link's hover says (a column's plain question)."""
    at = f' title="{e(title)}"' if title else ""
    return f'<a class="df" href="{CHECKS_PAGE}#{anchor}"{at}>{nobreak(words)}</a>'


def standing_html(row, page=None):
    """`standing` on the ladder and the Overview page (§2.3, amended 2026-11-16): Passed and not ranked link to their
    definitions, each check not passed to its row on the system page (its cause and evidence).
    `page` is the address of that page from where the words are printed ("" on the page
    itself)."""
    if row["passed"] and not row["ranked"]:
        return (f"{defined('Passed', 'passed')}, {defined('not ranked', 'unranked')}: "
                f"{e(row['unranked_reason'])}")  # fmt: skip
    if row["passed"]:
        return defined("Passed", "passed")
    at = href(row) if page is None else page
    missing = [f'<span class="ckn"><a class="df" href="{e(at)}#ck-{c["id"]}" '
               f'title="{e(filled(CHECK_PLAIN[c["id"]]))}">'
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


# the figure columns, in the row's order (SI-1, amended 2026-11-16: proof size in the place of
# USD, which is printed under Cost on a system's page only)
FIGURES = ("multiple", "proof-size", "check-time", "fidelity")
# on a board built by the further-reply rule (CO-9, Q55): the proving multiple beside the total
FIGURES_FURTHER = ("multiple", "proving", "proof-size", "check-time", "fidelity")


def figure_cols():
    """The figure columns of this board, in the row's order."""
    return FIGURES_FURTHER if further() else FIGURES


def cols():
    """The board's columns, one <col> each (`COLS`, a column more for the proving multiple)."""
    if not further():
        return COLS
    return "<colgroup>" + "".join(f'<col class="c{i}">' for i in range(1, 9)) + "</colgroup>"


# the board's columns, one <col> each: the heads printed once over the board and every model's
# table share them, so each head stands over its figures (words.css sets their widths)
COLS = ('<colgroup><col class="c1"><col class="c2"><col class="c3"><col class="c4">'
        '<col class="c5"><col class="c6"><col class="c7"></colgroup>')  # fmt: skip


def heads():
    """The figure columns' heads (`FIGURE_HEAD`: no word its unit says), each linked to its
    definition on the checks page (Fidelity to the figure's, not the check's: FIGURE_ANCHOR), the
    plain question the column answers in its title (`FIGURE_ASK`, amended 2026-11-23, Q54)."""
    ask = FIGURE_ASK | (FIGURE_ASK_FURTHER if further() else {})
    return [defined(FIGURE_HEAD[f], FIGURE_ANCHOR.get(f, f), ask[f]) for f in figure_cols()]


def heads_html():
    """The figure columns' heads, printed once over the board (Q54), in one line that stays
    under the top bar. The columns before them have no head: the square, the glyph and the name
    say what they are. Laid out on the board's columns, not read as a table: each model's table
    names its columns to a screen reader (`sr_head`)."""
    cells = "".join(
        f'<th class="h-{f}">{h}</th>' for f, h in zip(figure_cols(), heads(), strict=True)
    )
    return (
        f'<div class="lhd"><table class="lht" role="presentation">{cols()}<tr>'
        f'<td colspan="3"></td>{cells}</tr></table></div>'
    )


def sr_head():
    """A model's table's column names, for a screen reader only: the heads printed once over the
    board say the figures' to the eye, and the square, the glyph and the name say the rest."""
    names = (*LADDER_COLS, *(FIGURE_HEAD[f] for f in figure_cols()))
    return ('<thead class="srh"><tr>' + "".join(
        f'<th scope="col"><span class="sr">{e(n)}</span></th>' for n in names) + "</tr></thead>")  # fmt: skip


def linked_fig(html, f, to):
    """A ladder figure linked to its section (`to_section`); a missing one ("none" and why) as it
    is."""
    return to_section(html, to) if has(f) else html


def row_html(row, rung):
    """A system's row (SI-1, amended 2026-11-23, Q54): its position's square; its glyph, the
    small one, its arms without their names, at every width; its name, and under it its standing
    where the row holds no position (a row that holds one has passed: its standing is heard, and
    a phone, which draws no square, prints it); then its four figures. The row leads to the
    system's page; each figure to where it was taken: the multiple, its proved rate, the proof
    size and the verify time to Cost, where their scope and n are printed (Fidelity's word links
    its own). Each figure but the multiple carries its head as a label, which a phone shows."""
    glyph = glyph_svg(LADDER_GLYPH, states(row))
    size, verify = (
        row["figures"]["proof_bytes_per_reply"],
        row["figures"]["verify_seconds_per_reply"],
    )
    at = href(row)
    multiple = multiple_html(row, bare=True, to=f"{at}#cost", rates=f"{at}#{RATE_ANCHOR}")
    cells = (
        *((("cv", proving_html(row, bare=True, to=f"{at}#cost")),) if further() else ()),
        ("cc", linked_fig(fig_html(size, counted(row), sub=BARE), size, f"{at}#cost")),
        ("ct", linked_fig(fig_html(verify, counted(row), sub=BARE), verify, f"{at}#cost")),
        ("ck", fidelity_word(row)),
    )
    figs = "".join(f'<td class="{c}"><span class="lbl">{h}</span>{html}</td>'
                   for (c, html), h in zip(cells, heads()[1:], strict=True))  # fmt: skip
    placed = " placed" if row["position"] is not None else ""
    return (
        f'<tr class="row" id="row-{e(row["page"])}">'
        f'<td class="cp">{position_html(row, rung)}</td>'
        f'<td class="cg"><span class="sr pw">{states_words(row)}</span>'
        f'<a class="glyph" href="{e(at)}" tabindex="-1" aria-hidden="true">{glyph}</a></td>'
        f'<th class="csys{placed}" scope="row"><a class="sname" href="{e(at)}">{e(name_of(row))}</a>'
        f'<span class="st">{standing_html(row)}</span></th><td class="cm">{multiple}</td>{figs}</tr>'
    )


def divider_html(rung):
    """A model's divider (SI-1, amended 2026-11-23, Q54): a slim row under an accent rule, quieter
    than its systems' rows and the same in form whatever the model's state. Its size in the tab
    and its name, the model's heading, over the position, glyph and name columns (a long name
    wraps beside its tab); its serving rate, named, starting in the Cost vs serving column, over
    its rows' proved rates in the same unit (CO-8), free to run on over the proof size's empty
    cell; its copies' Fidelity in the Fidelity column (`copies_html`). A model no system has run
    on says so beside its name. It stays under the heads while its rows pass."""
    rid = e(rung["id"])
    none = "" if rung["rows"] else f'<span class="none">{e(SCALE_NOT_RUN)}</span>'
    copies = copies_html(rung)
    fid = (
        f'<span class="lbl">{heads()[-1]}</span><span class="dcp">{copies}</span>' if copies else ""
    )
    span = ' colspan="2"' if further() else ""
    return (f'<tr class="dv"><td class="dvh" colspan="3">'
            f'<div class="dvn"><span class="rk">{e(params(rung["parameters_total"]))}</span>'
            f'<h2 class="rm" id="h-{rid}">{nobreak(rung["model"])}</h2>{none}</div></td>'
            f'<td class="dvs" colspan="2"><span class="dl">{e(FIGURE_HEAD["serving"])}</span> '
            f'{served_html(rung["baseline"])}</td><td class="dve"{span}></td>'
            f'<td class="dvf">{fid}</td></tr>')  # fmt: skip


def model_html(rung):
    """A model's table: the board's columns, their names for a screen reader, its divider, then
    its rows in the board's order (OR-5). A table of its own, so its divider stays stuck only
    while its rows pass, and the next model's pushes it off. It carries the model's id, the
    address a system page's model links to (a box at every width: a phone's divider makes
    none)."""
    rows = "".join(row_html(r, rung) for r in rung["rows"])
    rid = e(rung["id"])
    return (f'<table class="lad" id="{rid}" aria-labelledby="h-{rid}">{cols()}{sr_head()}'
            f"<tbody>{divider_html(rung)}{rows}</tbody></table>")  # fmt: skip


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
    """How the baseline was served (CO-4): the publisher's release, the engine, its GPUs and the
    full-load concurrency, then what its figure is over: the timed batches there, one run."""
    gpus = f"{b['gpus']} × H200" if b["gpus"] else "GPUs not recorded"
    rel = b.get("release") or {}
    head = (f"{rel['publisher']}'s {rel['precision']} release, "
            if rel.get("publisher") and rel.get("precision") else "")  # fmt: skip
    batches = S.V["constants"].get("timed_batches")
    over = (f"{SEP}n\u00a0=\u00a0{batches:,} timed batches, 1 run"
            if batches and b.get("run_id") else "")  # fmt: skip
    return (f"{head}{engine_words()}, {gpus}, full load at {b['concurrency']:,} concurrent "
            f"requests{over}")  # fmt: skip


def served_html(b):
    """A model's serving rate as its divider prints it (CO-8, amended 2026-11-16): the baseline's
    reply tokens per GPU-second, its GPU named ("2,669 tokens/s per H200"), the unit of the rows'
    rate line under it; the state where the board holds none. The stored note on how it was
    served opens its title under the key "how", so the probe does not take its first words for
    one."""
    f = (b or {}).get("reply_tokens_per_gpu_second")
    if not has(f):
        return serving_missing(b)
    return fig_html(f, sub=BARE, how=f.get("note"), unit=RATE_PER.format(gpu=serving_gpu(b)))


# the ladder's lead (SI-1, amended 2026-11-16): one sentence, what a proof of inference is, for a
# reader with no context; the ladder under it says the rest
PROOF_WORDS = ("A proof of inference lets anyone verify that a reply came from a committed model "
               "running on a specific prompt, without seeing the weights.")  # fmt: skip


def band_html():
    """The band: the title on one line, and under it the lead (`lead_html`). The frontier (OR-6)
    is named neither in the title nor on the ladder (amended 2026-11-23, Q54): the ladder runs
    largest model first, and its rows say who passed where and at what multiple."""
    run = any(r["rows"] for r in S.V["rungs"])
    title = "Proved inference, by model size" if run else "No system has run yet."
    return f'<h1 class="band-h">{e(title)}</h1>{lead_html(run)}'


def lead_html(run):
    """One sentence under the title, for a reader with no context: what a proof of inference is.
    The ladder below it holds the figures; none is repeated here."""
    proof = e(PROOF_WORDS).replace("committed model", term("committed model", "Commitment"), 1)
    return f'<p class="lede">{proof}</p>{how_link()}'


# the Learn page that draws the request, the flow, the six checks and the headline figure: one
# click from the lead, for a reader with no context (web/learn/how-a-check-works.md)
HOW_PAGE = ("how-a-check-works", "How a check works")


def how_link(cls="lto"):
    """A link to the page that draws how a check works; nothing in a tree without it."""
    slug, words = HOW_PAGE
    pages = [p["slug"] for t in (S.V.get("learn") or {}).get("tracks", ()) for p in t["pages"]]
    return f'<p class="{cls}"><a href="/{slug}">{e(words)}</a></p>' if slug in pages else ""


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
            f'<a href="{CHECKS_PAGE}#not-run">Systems not run</a></h2><dl class="nrg">{rows}</dl></section>')  # fmt: skip


# ------------------------------------------------------------------ the partners
# The home page's last section (DEPTH.md: depth 1, the Mandate's list one click down), set as the
# systems not run are: its heading over a ruled grid, as many cells a line as fit, each partner's
# own mark (`credit.members`, a file under web/members/ from its kit) linked to its site. A cell
# in hand takes accent under ground ink, as a footer link does. The marks share one area (as on
# the members' card), drawn as masks so one ink sets them all.
PARTNERS_ID = "partners"  # the Mandate's row of them, where the heading leads


def partners_html():
    members = [m for m in S.V["credit"]["members"] if m.get("mark")]
    if not members:
        return "", ""
    cells = "".join(
        f'<li><a class="ptn-c" href="{e(m["url"])}">'
        f'<span class="ptn-m ptn-m{i}" role="img" aria-label="{e(m["name"])}"></span></a></li>'
        for i, m in enumerate(members, 1)
    )
    html_ = (f'<section class="ptn" aria-labelledby="h-ptn"><h2 class="nrh" id="h-ptn">'
             f'<a href="{MANDATE_PAGE}#{PARTNERS_ID}">Partners</a></h2>'
             f'<ul class="ptn-g">{cells}</ul></section>')  # fmt: skip
    # each mark's own width over height (`--k`, its square root: the mark is --s·k wide and --s/k
    # tall, so every mark covers --s²) and its file
    css = "".join(
        f".ptn-m{i}{{--k:{mark_shape(S.HERE / m['mark']) ** 0.5:.4f};"
        f"-webkit-mask-image:url({version(m['mark'])});mask-image:url({version(m['mark'])})}}"
        for i, m in enumerate(members, 1)
    )
    return html_, css


def build_index():
    """The home page: the band, then the board (the heads once, a table per model), the systems
    not run, and the partners."""
    board = heads_html() + "".join(model_html(r) for r in S.V["rungs"])
    partners, css = partners_html()
    body = f"""
{header("home")}
<main id="main" class="home">
  <section class="mast"><div class="mast-in">{band_html()}</div></section>
  <div class="wrap ladder{" two" if further() else ""}">{board}</div>
  <div class="wrap">{not_run_html()}{partners}</div>
</main>
{footer()}"""
    return page("Inference proofs", home_words(), body, "home", "", "home", css=css)


def home_words():
    """The home page in a sentence (its description and share text): what a proof states, the
    largest model one proved on (OR-6; left out while there is none), and what each row holds."""
    front = S.V["frontier"]
    rung = next((r for r in S.V["rungs"] if front and r["id"] == front["rung"]), None)
    size = f" up to {params(rung['parameters_total'])} parameters" if rung else ""
    return (f"Proofs that a reply is the one a committed model returns for a prompt, from systems "
            f"run on open-weights models{size}: six checks each, and the cost of a proved reply as "
            "a multiple of serving it.")  # fmt: skip
