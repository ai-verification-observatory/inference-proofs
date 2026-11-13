"""The system pages (RFC-0018 SI-3), the checks page and the 404.

A system page holds one row of the board: its other figures in one ruled row; the glyph once,
large, its arms the heads of a ruled table of the petals (state, reason, and behind a disclosure
the publisher's quotes and basis); then the six checks as a ruled table (state, cause, evidence
behind a disclosure), the cost parts, fidelity beside the model's controls and the sessions.
"""

import re

from . import state as S
from .chrome import (
    CHECKS_PAGE,
    MANDATE_PAGE,
    card_current,
    cards_record,
    counted,
    footer,
    has,
    header,
    lead_figure,
    link,
    page,
    pnav,
    row_cost,
    rung_of,
)
from .hexagon import glyph_svg
from .overview import (
    NOT_TESTED,
    defined,
    fig_html,
    filled,
    href,
    kl_html,
    lead_fig,
    name_of,
    nobreak,
    position_html,
    serving_words,
    split_html,
    standing_html,
    states,
)
from .plots import fid_svg, hbar
from .words import (
    BASIS_READING,
    BASIS_WORD,
    CAUSE_WORD,
    CHECK_CAUSE_WORD,
    CHECK_FAILED,
    CHECK_HELD,
    CHECK_NAME,
    CONTROL_NAME,
    FIGURE_NAME,
    FIGURE_RULE,
    FULL_LOAD_WORD,
    HOLLOW_RULE,
    M_COL,
    M_NAME,
    MANDATE,
    MANDATE_BELIEF,
    MANDATE_MEMBERS_IN,
    MANDATE_WHAT,
    NO_STEADY_WORD,
    NULL_WORD,
    OF_WHICH,
    ORDER_RULE,
    P_ABOVE,
    PART_WORD,
    PETAL_CAUSE_RULE,
    PETAL_CHECKS,
    PETAL_NAME,
    PETAL_RULE,
    PREFIX,
    READING_RULE,
    SCOPE_COL_WORD,
    SCOPE_ROW_WORD,
    SCOPE_VALUE_WORD,
    STATE_WORD,
    STEP_WORD,
    VISIBLE_TAG_WORD,
    WHOLE_SESSIONS,
    e,
    kl_head,
    number,
    params,
    quoted,
    sig,
)

GLYPH = 6  # the checks page's key glyph, px per unit (318 by 174 px)
GPU_S = "gpu_s/request"  # a session's values: GPU-seconds per reply (RFC-0018 CO-1, CO-3)
PROOF_SIZE = "Proof size per reply"


def section(sid, title, body):
    return (f'<section class="blk" id="{sid}" aria-labelledby="h-{sid}">'
            f'<h2 class="sect" id="h-{sid}">{e(title)}</h2>{body}</section>')  # fmt: skip


RUN_ID = re.compile(r"^(\d{4}-\d{2}-\d{2})-.*-(\d+)$")


def where(d):
    """A record's directory in short: its run by date and ordinal, then what lies under it."""
    parts = d.split("/")
    for i, part in enumerate(parts):
        m = RUN_ID.match(part)
        if m:
            return " / ".join([f"{m[1]} \u00b7 {m[2]}", *parts[i + 1 :]])
    return parts[-1]


def run_link(row, run_id):
    """A run by date and ordinal (its id in the title), linked to its record."""
    rel = S.V["release"]
    label = f'<span title="{e(run_id)}">{e(where(run_id))}</span>'
    if rel is None or not str(rel["board"]).startswith("releases/"):
        return f'<span class="rid">{label}</span>'
    path = f"results/{rel['id']}/{row['system']}/{run_id}/run.json"
    return f'<a class="rid" href="{e(link(path))}" title="{e(run_id)}">{e(where(run_id))}</a>'


def evidence_html(paths):
    """A check's records, one link per file: its run by date and ordinal, the file's name and,
    for a JSON Pointer into it, the entries it points at ("controls/1"); a directory's files
    (a trace per proof makes many) as one link to the directory with their count."""
    files: dict[str, list[str]] = {}
    for p in paths:
        path, _, ptr = p.partition("#")
        files.setdefault(path.rstrip("/"), []).append(ptr.strip("/"))
    dirs: dict[str, list[str]] = {}
    for path in files:
        dirs.setdefault(path.rsplit("/", 1)[0], []).append(path)
    out = []
    for d, paths_in in dirs.items():
        whole = [p for p in paths_in if not any(files[p])]
        if len(whole) > 1:  # several plain files of one directory: one link to it
            names = ", ".join(p.rsplit("/", 1)[-1] for p in whole)
            said = f" / {names}" if len(whole) <= 3 else f" ({len(whole):,} files)"
            out.append(f'<a class="ev" href="{e(S.REPO_URL)}/tree/{e(S.LINK_REF)}/{e(d)}" '
                       f'title="{e(d)}">{e(where(d) + said)}</a>')  # fmt: skip
        for path in (p for p in paths_in if len(whole) <= 1 or p not in whole):
            ptrs = [x for x in files[path] if x]
            name = path.rsplit("/", 1)[-1]
            label = f"{where(path.rsplit('/', 1)[0])} / {name}"
            href = link(path) + (f"#/{ptrs[0]}" if len(ptrs) == 1 else "")
            at = f" · {', '.join(ptrs)}" if ptrs else ""
            out.append(f'<a class="ev" href="{e(href)}" title="{e(path)}">{e(label)}'
                       f'<span class="nw">{e(at)}</span></a>')  # fmt: skip
    return "".join(out)


def chip(state, word, form=""):
    """A state as a chip: ground ink on its state's ink, an outline when undecided or hollow; amber
    in lesser part notched (cut), a silent red an outline in the red ink (open)."""
    tok = f"{state} {form}".strip()
    return f'<span class="schip {tok}">{e(word)}</span>'


def stacked(heads, rows):
    """A ruled table whose cells carry their column's head (data-l), so a phone stacks each row
    as labelled lines instead of hiding columns past the edge. rows: lists of cell html."""
    ths = "".join(f'<th scope="col">{e(h)}</th>' for h in heads)
    trs = "".join(
        "<tr>" + "".join(f'<td data-l="{e(h)}">{c}</td>' for h, c in zip(heads, r, strict=True))
        + "</tr>" for r in rows
    )  # fmt: skip
    return f'<table class="rt stk"><thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table>'


def petals_of(check):
    """The petals whose red names a check (PETAL_CHECKS), by their place in the glyph (p1 to
    p5), so the page lights them with the check's row (words.js)."""
    return " ".join(f"p{i + 1}" for i, p in enumerate(S.V["petals"]) if check in PETAL_CHECKS[p])


def quote_links(quotes):
    return "".join(f'<a class="qt" href="{e(q["url"])}">\u201c{quoted(q["text"])}\u201d</a>'
                   for q in quotes)  # fmt: skip


def scope_card_html(formal):
    """Machine-checked's recorded facts, inside its Reason cell: the tool, the theorem (linked at
    the pin) and the trusted base as the publisher lists it, then the scope card: for soundness,
    zero knowledge and completeness, what the publisher states of the protocol, the verifier run
    and the prover run, each word linked to its first quote. It sets no state."""
    if formal is None:
        return ""
    theorem = formal["theorem"]
    if theorem and formal["theorem_url"]:
        theorem = f'<a href="{e(formal["theorem_url"])}"><code>{e(theorem)}</code></a>'
    elif theorem:
        theorem = f"<code>{e(theorem)}</code>"
    lines = (("tool", e(formal["tool"]) if formal["tool"] else None), ("theorem", theorem),
             ("trusted base", e(", ".join(formal["trusted_base"])) if formal["trusted_base"]
              else None))  # fmt: skip
    facts = "".join(f"<div><dt>{e(k)}</dt><dd>{v or e(SCOPE_VALUE_WORD['not_stated'])}</dd></div>"
                    for k, v in lines)  # fmt: skip

    def cell(c):
        word = e(SCOPE_VALUE_WORD[c["value"]])
        if c["quotes"]:
            word = f'<a class="sv" href="{e(c["quotes"][0]["url"])}">{word}</a>'
        return f'<td class="{e(c["value"])}">{word}</td>'

    card = formal["scope_card"]
    heads = "".join(f'<th scope="col">{e(w)}</th>' for w in SCOPE_COL_WORD.values())
    body = "".join(
        f'<tr><th scope="row">{e(SCOPE_ROW_WORD[r])}</th>'
        + "".join(cell(card[r][c]) for c in SCOPE_COL_WORD) + "</tr>"
        for r in SCOPE_ROW_WORD
    )  # fmt: skip
    return (f'<dl class="pf">{facts}</dl><table class="scard"><caption class="sr">Scope card</caption>'
            f'<thead><tr><td><span class="sr">What</span></td>{heads}</tr></thead>'
            f"<tbody>{body}</tbody></table>")  # fmt: skip


def visible_html(visible):
    """Weights hidden: what the publisher lists as visible to a proof's reader, each item linked
    to its quote, with its kind (only a value fitted to the weights sets the step)."""
    if not visible:
        return ""
    items = "".join(f'<li><a href="{e(v["quotes"][0]["url"])}">{e(v["item"])}</a> '
                    f'<span class="vt">{e(VISIBLE_TAG_WORD[v["tag"]])}</span></li>'
                    for v in visible)  # fmt: skip
    return f'<p class="pvh">Visible, as listed</p><ul class="pvis">{items}</ul>'


def basis_html(p):
    """What a petal rests on (the From cell): our tests, the publisher's documents, or, when a
    fact the decision read carries a note, the publisher's documents as we read them, linked to
    what that means."""
    if p["basis"] == "statement" and p["reading"]:
        docs, ours = BASIS_READING
        return f'{e(docs)}, <a class="df" href="{CHECKS_PAGE}#reading">{e(ours)}</a>'
    return e(BASIS_WORD[p["basis"]])


def counted_words(k, one):
    """A count in words: "1 quote", "16 quotes"."""
    return f"{k:,} {one}" if k == 1 else f"{k:,} {one}s"


def petal_more(p):
    """What a petal holds beyond its reason, one click away: a native disclosure whose summary
    names it by count (the quotes, Machine-checked's scope card, Weights hidden's visible list),
    opening onto them and what the petal rests on (SI-3). A petal with none of them prints only
    what it rests on."""
    said = [counted_words(len(p["quotes"]), "quote")] if p["quotes"] else []
    if p["formal"] is not None:
        said.append("scope card")
    if p["visible"]:
        said.append(counted_words(len(p["visible"]), "visible value"))
    if p["sources"] and not said:
        said.append(counted_words(len(p["sources"]), "document") + " read")
    if not said:
        return f'<span class="bs">{basis_html(p)}</span>'
    # a silent red: the documents read, each linked at the pin (GL-1)
    docs = ", ".join(f'<a href="{e(d["url"])}">{e(d["path"])}</a>' for d in p["sources"])
    body = (quote_links(p["quotes"]) + scope_card_html(p["formal"]) + visible_html(p["visible"])
            + f'<p class="pfrom"><span class="k">From</span> {basis_html(p)}'
            + (f": {docs}" if docs else "") + "</p>")  # fmt: skip
    said = " · ".join(f'<span class="nw">{e(w)}</span>' for w in said)
    owner = f'<span class="sr">, {e(PETAL_NAME[p["id"]])}</span>'
    return f'<details class="more"><summary>{said}{owner}</summary>{body}</details>'


def glyph_html(row):
    """The glyph once, large, as the heads of the petals' table: each arm is its petal's name on
    the ink of its state (never its state word: the ink says it, and the chip beside it), on one
    stem, then the step in words with the cause of a red or hollow petal, the reason, and at the
    row's end what the petal holds besides (`petal_more`). An arm, its row and the checks its red
    names light together."""
    trs = []
    for i, p in enumerate(row["glyph"]):
        tok = f"{p['state']} {p['form']}".strip()
        data = f' data-step="{e(p["step"] or "none")}"'
        state = chip(p["state"], STEP_WORD[p["step"]], p["form"])
        if p["cause"] is not None:  # the reason says it; the chip links its definition
            data += f' data-cause="{e(p["cause"])}"'
            state = (f'<a class="cc" href="{CHECKS_PAGE}#cause-{e(p["cause"])}" '
                     f'title="{e(CAUSE_WORD[p["cause"]])}">{state}</a>')  # fmt: skip
        trs.append(
            f'<tr class="pt {tok}"><th scope="row">'
            f'<a class="sl s{i + 1} {tok}"{data} href="{CHECKS_PAGE}#{p["id"]}" data-k="p{i + 1}">'
            f"<span>{e(PETAL_NAME[p['id']])}</span></a></th>"
            f'<td class="cst">{state}</td>'
            f'<td class="prs"><span class="rs">{e(p["reason"])}</span>{petal_more(p)}</td></tr>'
        )
    return ('<div class="checks"><table class="rt ckt gbig"><caption class="sr">Petal, state, '
            f'reason</caption><tbody>{"".join(trs)}</tbody></table></div>')  # fmt: skip


NOTE_SHORT = 48  # a check's note longer than this, in characters, is left to its records


def note_gist(note):
    """A check's note as its row prints it: the words after an internal id ("P1: ", a run's
    request) when it leads them, and only when they are short; None otherwise."""
    head, sep, tail = note.partition(": ")
    gist = tail if sep and " " not in head else note
    return gist if len(gist) <= NOTE_SHORT else None


def checks_html(row):
    """The six checks, the entry gate: one ruled row per check: name, state, cause (a column
    only where a check has one, a short note under it), and its records one click away, the
    note in full with them. A check names the petals its failure turns red."""
    caused = any(c["cause"] or c.get("note") for c in row["checks"])
    trs = []
    for c in row["checks"]:
        cause, note = "", c.get("note")
        if c["cause"]:
            cause = (f'<a class="cw df" href="{CHECKS_PAGE}#undecided" '
                     f'title="{e(CHECK_CAUSE_WORD[c["cause"]])}">{e(c["cause"])}</a>')  # fmt: skip
        gist = note_gist(note) if note else None
        if gist:
            cause += f'<span class="cn">{quoted(gist)}</span>'
        full = f'<p class="cn">{quoted(note)}</p>' if note and gist != note else ""
        recs = counted_words(len(c["evidence"]), "record") if c["evidence"] else "note"
        owner = f'<span class="sr">, {e(CHECK_NAME[c["id"]])}</span>'
        more = (f'<details class="more"><summary>{e(recs)}{owner}</summary>{full}'
                f"{evidence_html(c['evidence'])}</details>"
                if c["evidence"] or full else "")  # fmt: skip
        to = petals_of(c["id"])
        to = f' data-to="{to}"' if to else ""
        trs.append(
            f'<tr class="ck {c["state"]}" id="ck-{c["id"]}"><th scope="row">'
            f'<a href="{CHECKS_PAGE}#{c["id"]}"{to}>{e(CHECK_NAME[c["id"]])}</a></th>'
            f'<td class="cst">{chip(c["state"], STATE_WORD[c["state"]])}</td>'
            + (f"<td>{cause}</td>" if caused else "")
            + f"<td>{more}</td></tr>"
        )
    cause_th = '<th scope="col">Cause</th>' if caused else ""
    return ('<table class="rt ckt cks"><thead><tr><th scope="col">Check</th><th scope="col">'
            f'State</th>{cause_th}<th scope="col">Evidence</th></tr></thead>'
            f'<tbody>{"".join(trs)}</tbody></table>')  # fmt: skip


def plain(v, unit, record):
    """A number the board stores without labels (a session's value, a mean prefix), in its
    column's unit, its record in its title."""
    if v is None:
        return '<span class="na">none</span>'
    n, u = (sig(v), "tokens") if unit == "tokens" else number(v, unit)
    return (f'<span class="fig" title="record: {e(record)}"><span class="n">{e(n)}</span>'
            f'<span class="u">{e(u)}</span></span>')  # fmt: skip


def sessions_html(row):
    """SE-3: each counted session (slot, run, m, session cost per reply, steady state or why
    not), then every incomplete session with its exit code and last line (AGENTS.md rule 5)."""
    rec = row["record"]
    gen = any(s.get("generation_gpu_seconds_per_reply") is not None for s in row["sessions"])

    def cells(k, s):
        at = f"{rec}/sessions/{k}"
        g = s.get("generation_gpu_seconds_per_reply")  # CO-7: the generation phase, part of the
        return [  # whole session (and of m, where the session has one)
            str(s["slot"]),
            run_link(row, s["run_id"]),
            plain(s["m"], GPU_S, f"{at}/m"),
            plain(s["session"], GPU_S, f"{at}/session"),
            *([plain(g, GPU_S, f"{at}/generation_gpu_seconds_per_reply")] if gen else []),
            "yes" if s["steady"] else e(s["cause"] or "no"),
            f"{len(s['groups']):,}",
        ]

    of_gen = f"{OF_WHICH} {PART_WORD['generation']}".capitalize()
    heads = ["Slot", "Run", M_COL, "Session", *([of_gen] if gen else []),
             "Steady state", "Release groups"]  # fmt: skip
    out = (stacked(heads, [cells(k, s) for k, s in enumerate(row["sessions"])])
           if row["sessions"] else '<p class="none">No counted session.</p>')  # fmt: skip
    if row["incomplete"]:
        rows = [
            [
                str(s["slot"]) if s["slot"] is not None else "",
                run_link(row, s["run_id"]),
                e(s["exit_code"]) if s["exit_code"] is not None else "none",
                e(s["step"] or ""),
                e(s["cause"]),
                f"<code>{e(s['last_line'] or '')}</code>",
            ]
            for s in row["incomplete"]
        ]
        out += '<h3 class="sub-h">Incomplete sessions</h3>' + stacked(
            ["Slot", "Run", "Exit code", "Step", "Cause", "Last line"], rows
        )
    if row.get("replaced"):  # SE-3a: listed with why, in no figure and no check
        rows = [
            [
                str(s["slot"]) if s["slot"] is not None else "",
                run_link(row, s["run_id"]),
                run_link(row, s["replaced_by"]),
                e(s["cause"]),
            ]
            for s in row["replaced"]
        ]
        out += '<h3 class="sub-h">Replaced sessions</h3>' + stacked(
            ["Slot", "Run", "Replaced by", "Why"], rows
        )
    return out


def of_which(word):
    return f"{OF_WHICH} {PART_WORD[word]}"


# CO-7: a GPU time's two parts, where the system generates in a phase of its own, drawn in this
# order (the part that is not generation first, in paper)
GPU_PARTS = {
    "steady_gpu_seconds_per_reply": (("proving", "steady_proving_gpu_seconds_per_reply"),
                                     ("generation", "steady_generation_gpu_seconds_per_reply")),
    "session_gpu_seconds_per_reply": (
        ("commit_and_proving", "session_commit_and_proving_gpu_seconds_per_reply"),
        ("generation", "session_generation_gpu_seconds_per_reply")),
}  # fmt: skip


def cost_bars(row):
    """CO-1 to CO-3 drawn: serving, the steady m and the whole session, each in GPU time per
    reply on one scale, this row's own (one model); m and the session each in two parts where the
    system generates in a phase of its own (CO-7). Each line: its name, its bar, its labelled
    figure and its parts' figures; a figure the board holds no value for draws no line
    (`cost_html` names it)."""
    figs, n = row["figures"], counted(row)
    b = (rung_of(row)["baseline"] or {}).get("gpu_seconds_per_reply")
    m, s = figs["steady_gpu_seconds_per_reply"], figs["session_gpu_seconds_per_reply"]
    present = [f["value"] for f in (b, m, s) if has(f)]
    if not present:
        return ""
    top = max(present)
    lines = []

    def line(cls, name, f, fig, ink="bs", key=None):
        if not has(f):
            return
        parts = [(w, figs.get(k)) for w, k in GPU_PARTS.get(key, ())]
        split = parts and all(has(p) for _, p in parts)
        segs = [(p["value"], c) for (_, p), c in zip(parts, ("bp", "bg"), strict=True)] if split \
            else [(f["value"], ink)]  # fmt: skip
        cps = ""
        if split:
            cps = "".join(f'<span class="cpt {c}"><span class="cpl">{e(of_which(w))}</span>'
                          f"{fig_html(p, n)}</span>"
                          for (w, p), c in zip(parts, ("pp", "pg"), strict=True))  # fmt: skip
            cps = f'<span class="cps">{cps}</span>'
        bar = hbar(segs, top, h=14, cls="hb")
        lines.append(f'<div class="cl {cls}"><span class="cln">{e(name)}</span>{bar}'
                     f'<span class="clf">{fig}</span>{cps}</div>')  # fmt: skip

    line("srv", "Serving GPU time per reply", b, fig_html(b, sub=FULL_LOAD_WORD))
    line("std", M_NAME, m, fig_html(m, n), key="steady_gpu_seconds_per_reply")
    line("ses", "Session GPU time per reply", s, fig_html(s, n), "bc",
         "session_gpu_seconds_per_reply")  # fmt: skip
    return f'<div class="cbars">{"".join(lines)}</div>'


def low_first(name):
    """A label inside a list: its first letter lower case, unless it opens a capitalised word
    ("GPU time" stays)."""
    return name if name[1:2].isupper() else name[:1].lower() + name[1:]


def missing_html(missing):
    """The figures the board holds no value for, named once per reason, in the board's words."""
    return "".join(
        f'<p class="cnone">{e(", ".join(k if i == 0 else low_first(k) for i, k in enumerate(names)))}'
        f": none, {e(why)}</p>"
        for why, names in missing.items()
    )  # fmt: skip


def cost_html(row):
    """The cost parts (CO-1 to CO-5) the band and the figures block do not print, each figure as
    the board stores it: the serving baseline, the GPU times drawn on one scale (`cost_bars`),
    then a sheet of the other figures; then, once, each figure the board holds no value for with
    the board's reason (a steady figure on a row with no steady state: NO_STEADY_WORD)."""
    rung = rung_of(row)
    figs, b, n = row["figures"], rung["baseline"] or {}, counted(row)
    whole = WHOLE_SESSIONS.format(n=rung["requests_per_session"])
    price = S.V["price"]
    _, _, key = lead_figure(row)
    steady_multiple = f"Steady {FIGURE_NAME['multiple'].lower()}"
    other = ((f"{FIGURE_NAME['multiple']}, {whole}", figs["session_multiple"], n)
             if key == "multiple" else (steady_multiple, figs["multiple"], n))  # fmt: skip
    drawn = [("Serving GPU time per reply", b.get("gpu_seconds_per_reply"), None),
             (M_NAME, figs["steady_gpu_seconds_per_reply"], n),
             ("Session GPU time per reply", figs["session_gpu_seconds_per_reply"], n)]  # fmt: skip
    shown = row_cost(row)  # printed in the figures block
    sheet = [other, ("Steady cost per reply", figs["steady_usd_per_reply"], n),
             ("Session cost per reply", figs["session_usd_per_reply"], n),
             ("Serving cost per reply", b.get("usd_per_reply"), None)]  # fmt: skip
    no_steady = not has(figs["multiple"]) and figs["multiple"]["null_reason"] == "not_applicable"
    steady_figs = (figs["multiple"], figs["steady_gpu_seconds_per_reply"],
                   figs["steady_usd_per_reply"])  # fmt: skip
    missing: dict[str, list[str]] = {}
    for k, f, _ in (*drawn, *sheet):
        if has(f):
            continue
        why = ("not recorded" if not f else NO_STEADY_WORD
               if no_steady and any(f is g for g in steady_figs) else NULL_WORD[f["null_reason"]])  # fmt: skip
        missing.setdefault(why, []).append(k)
    rows = [(k, fig_html(f, count, sub=FULL_LOAD_WORD if count is None and k.startswith("Serving")
                         else None)) for k, f, count in sheet if has(f) and f is not shown]  # fmt: skip
    if price and has(price["usd_per_gpu_hour"]):
        rows.append(("Price of one H200 GPU-hour",
                     fig_html(price["usd_per_gpu_hour"], sub=f"{price['basis']}, {price['date']}")))  # fmt: skip
    else:
        missing.setdefault("not recorded", []).append("Price of one H200 GPU-hour")
    cells = "".join(f"<div><dt>{e(k)}</dt><dd>{v}</dd></div>" for k, v in rows)
    base = rung["baseline"]
    serving = (f'<p class="rb"><span class="k">Serving</span> {e(serving_words(base))}</p>'
               if base and has(base["gpu_seconds_per_reply"]) else "")  # fmt: skip
    missing.pop(NO_STEADY_WORD, None)  # the sessions table prints each session's none and why
    return (f'{serving}{cost_bars(row)}<dl class="parts">{cells}</dl>'
            f"{missing_html(missing)}")  # fmt: skip


def fidelity_html(row):
    """FI-5, FI-6, FI-7: the row's mean matched prefix and KL beside the model's controls, each
    drawn on a track from no matched token to the whole reply, the bar marked; the system's own
    replies a paper row, its p values under its prefix."""
    fid = rung_of(row)["fidelity"]
    mine = row["fidelity"]
    bar = (fid or {}).get("bar")
    whole = S.V["request"]["output_tokens"]
    edge = bar["mean_prefix"] if bar is not None else None
    kl_h = kl_head(rung_of(row)["reference_dtype"])
    # KL is a column only where a row of the rung has it; otherwise one line says so
    any_kl = (has((mine or {}).get("kl"))
              or any(has(c["kl"]) for c in (fid or {}).get("controls") or []))  # fmt: skip
    heads = ("Replies", "Kind", PREFIX, *((kl_h,) if any_kl else ()))

    def tds(kind, track, prefix, kl):
        return (f'<td data-l="Kind">{kind}</td>'
                f'<td class="trk" aria-hidden="true">{fid_svg(track[0], edge, whole, track[1])}</td>'
                f'<td data-l="{e(heads[2])}">{prefix}</td>'
                + (f'<td data-l="{e(kl_h)}">{kl}</td>' if any_kl else ""))  # fmt: skip

    out = []
    if mine is not None:
        prefix = plain(mine["mean_prefix"], "tokens", row["record"] + "/fidelity/mean_prefix")
        sub = f"n\u00a0=\u00a0{mine['n']:,}"
        if mine["p_above_bar"] is not None:
            sub += " · " + P_ABOVE.format(p=sig(mine["p_above_bar"], 2))
        out.append(f'<tr class="me"><th scope="row">{e(name_of(row))}</th>'
                   + tds("this system", (mine["mean_prefix"], "me"),
                         f'{prefix}<span class="sub">{e(sub)}</span>', kl_html(row))
                   + "</tr>")  # fmt: skip

    def at(i):
        return f"{fid['record']}/controls/{i}/mean_prefix"

    for i, c in enumerate((fid or {}).get("controls") or []):
        is_bar = bar is not None and bar["control"] == c["id"]
        kind = c["kind"] + (", the bar" if is_bar else "")
        if c["status"] == "failed":
            kind += ", failed to run"
        kl = fig_html(c["kl"]) if has(c["kl"]) else '<span class="na">not measured</span>'
        out.append(
            f'<tr class="{"bar" if is_bar else ""}"><th scope="row">'
            f"{e(CONTROL_NAME.get(c['id'], c['id']))}</th>"
            + tds(
                e(kind),
                (c["mean_prefix"], "bar" if is_bar else c["kind"]),
                plain(c["mean_prefix"], "tokens", at(i)),
                kl,
            )
            + "</tr>"
        )
    if not out:
        return '<p class="none">Not run yet.</p>'
    lead = ""
    if fid is not None and bar is None:
        lead = f'<p class="flead">No bar: {e(fid["cause"] or "no damaged copy qualified")}</p>'
    if not any_kl:
        note = (mine or {}).get("kl_note") or "not measured"
        lead += (f'<p class="flead">{e(kl_h)}: <span class="na" title="{e(note)}">not measured'
                 "</span></p>")  # fmt: skip
    ths = (f'<th scope="col">{e(heads[0])}</th><th scope="col">{e(heads[1])}</th>'
           f'<th scope="col" class="trk" aria-hidden="true"></th>'
           + "".join(f'<th scope="col">{e(h)}</th>' for h in heads[2:]))  # fmt: skip
    return (f'{lead}<table class="rt stk fid"><thead><tr>{ths}</tr></thead>'
            f'<tbody>{"".join(out)}</tbody></table>')  # fmt: skip


def figures_html(row):
    """The row's other figures (the band prints its one figure) as one ruled row of cells, each
    with its unit, scope and n: cost per reply at the multiple's own scope, check time and proof
    size per reply, then fidelity: the replies' mean matched prefix on its track against the
    model's bar, and KL where it was measured."""
    rung, figs, n = rung_of(row), row["figures"], counted(row)
    cells = [(defined(FIGURE_NAME["cost"], "cost"), fig_html(row_cost(row), n)),
             (defined(FIGURE_NAME["check-time"], "check-time"),
              fig_html(figs["verify_seconds_per_reply"], n)),
             (e(PROOF_SIZE), fig_html(figs["proof_bytes_per_reply"], n))]  # fmt: skip
    mine, fid = row["fidelity"], rung["fidelity"] or {}
    bar = fid.get("bar")
    if mine is None:
        prefix = '<span class="na">not run yet</span>'
    else:
        track = ""  # the Fidelity section draws the tracks
        if bar is not None:
            i = next(k for k, c in enumerate(fid["controls"]) if c["id"] == bar["control"])
            at = f"{fid['record']}/controls/{i}/mean_prefix"
            track = (f'<span class="fbar"><span class="k">bar</span>'
                     f'{plain(bar["mean_prefix"], "tokens", at)}</span>')  # fmt: skip
        prefix = (plain(mine["mean_prefix"], "tokens", row["record"] + "/fidelity/mean_prefix")
                  + f'<span class="sub">n\u00a0=\u00a0{mine["n"]:,}</span>' + track)  # fmt: skip
    cells.append((defined(PREFIX, "fidelity"), prefix))
    if mine is not None and has(mine.get("kl")):
        cells.append((defined(kl_head(rung["reference_dtype"]), "kl"), fig_html(mine["kl"])))
    return '<dl class="figs">' + "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>"
                                         for k, v in cells) + "</dl>"  # fmt: skip


NAME_SIZES = (6, 12, 20)  # a system's name on its band: one size per length up to these
SHARE = ("Share", "Card", "Copy link", "Copied")  # the share group: its name, its two actions, done


def share_html(row):
    """The share group's actions: the page's card as a download, while its picture is the one
    this build's source was rendered to (none otherwise), and Copy link, which words.js shows and
    runs (it copies the page's canonical address and says so)."""
    pid = row["page"]
    card = ""
    if card_current(pid):
        v = cards_record()[pid]["png"][:12]
        card = f'<a href="/og/{e(pid)}.png?v={e(v)}" download="{e(pid)}.png">{e(SHARE[1])}</a>'
    return (card + f'<button type="button" class="cplink" data-done="{e(SHARE[3])}" hidden>'
            f"{e(SHARE[2])}</button>")  # fmt: skip


def system_page(row):
    """A system on a model (SI-3): the band (its name, sized by its length, never more than two
    lines; its one figure on the right, labelled for what it is; the facts under them, the
    publisher's repository at the row's commit among them), then the glyph and its petals, its
    other figures, the checks, the cost, fidelity and, last, the sessions (the audit trail)."""
    rung = rung_of(row)
    sysd = S.V["systems"][row["system"]]
    name = name_of(row)
    facts = [("Standing", standing_html(row, "")),
             ("Model", f'<a href="/#{e(rung["id"])}">{nobreak(rung["model"])}</a>')]  # fmt: skip
    if row["position"] is not None:
        facts.append(("Position", position_html(row, rung)))
    if sysd["repo"]:  # the publisher's repository, at the commit the row runs
        at = f"/tree/{e(row['commit'])}" if row["commit"] else ""
        facts.append(("Source", f'<a href="https://github.com/{e(sysd["repo"])}{at}">'
                                f'{nobreak(sysd["repo"])}</a>'))  # fmt: skip
    share = share_html(row)
    size = next((i + 1 for i, k in enumerate(NAME_SIZES) if len(name) <= k), len(NAME_SIZES) + 1)
    label, lead = lead_fig(row)
    lead += split_html(row, lead_figure(row)[2], bar=False, of_which=True)
    unranked = "" if row["position"] is not None else " unr"
    band_ = (
        f'<section class="mast mast-sys sysb" aria-labelledby="h-name"><div class="mast-in">'
        f'<div class="sb"><h1 id="h-name" class="sysname nm{size}">{e(name)}</h1>'
        f'<p class="sbm{unranked}"><span class="sbl">{e(label)}</span>{lead}</p></div>'
        '<dl class="facts">'
        + "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in facts)
        + f'<div class="fshr"><dt>{e(SHARE[0])}</dt><dd>{share}</dd></div>'
        + "</dl></div></section>"
    )
    # the share group at the strip's end on a wide screen, among the band's facts on a phone
    share_strip = (f'<div class="shr" role="group" aria-label="{e(SHARE[0])}">'
                   f'<span class="shl" aria-hidden="true">{e(SHARE[0])}</span>{share}</div>')  # fmt: skip
    parts = (("figures", "Figures"), ("glyph", "Glyph"), ("checks", "Checks"), ("cost", "Cost"),
             ("fidelity", "Fidelity"), ("sessions", "Sessions"))  # fmt: skip
    body = f"""
{header("system")}
<main id="main" class="sys">
  {band_}
  {pnav(name, parts, share_strip)}
  <div class="wrap">
    {section("figures", "Figures", figures_html(row))}
    {section("glyph", "Glyph", glyph_html(row))}
    {section("checks", "Checks", checks_html(row))}
    {section("cost", "Cost", cost_html(row))}
    {section("fidelity", "Fidelity", fidelity_html(row))}
    {section("sessions", "Sessions", sessions_html(row))}
  </div>
</main>
{footer()}"""
    desc = f"{name} on {rung['model']}: its glyph, six checks, cost against serving."
    return page(name, desc, body, "system syspage", row["page"], row["page"])


def build_system(pid):
    return system_page(S.PAGE[pid])


def rules(lines, ids=()):
    """Labelled lines as one list: (label, words) pairs, the level's constants filled in. A label
    in `ids` is an address of its own."""

    def at(k):
        return f' id="{k}"' if k in ids else ""

    return '<dl class="cs">' + "".join(
        f"<div{at(k)}><dt>{e(k)}</dt><dd>{e(filled(v))}</dd></div>" for k, v in lines
    ) + "</dl>"  # fmt: skip


def title_band(title, sub="", cls="ttl"):
    """The band of a page that is not a system's (the checks, the mandate, the 404): its title
    at the home title's size, and a line under it."""
    return (f'<div class="mast mast-t"><div class="mast-in"><h1 id="h-name" class="{cls}">'
            f"{e(title)}</h1>{sub}</div></div>")  # fmt: skip


def build_checks():
    """The five petals (RFC-0018 §The glyph) as the key beside their rules, the six checks as the
    entry gate (§The six checks) with what is not tested, the undecided causes, the figures (§Cost,
    FI-7), then the order rule. The page opens on the glyph, as a system page does."""
    ids = list(S.V["petals"])
    names = [PETAL_NAME[p] for p in ids]
    glyph = glyph_svg(GLYPH, ["key"] * len(names), names=names, cls="pie-svg big",
                      hrefs=[f"#{p}" for p in ids])  # fmt: skip
    # the four decided steps, each as the chip a system page prints (STEP_WORD), beside its rule
    keys = (("green", "", "green"), ("amber", "", "amber_upper"), ("amber", "cut", "amber_lower"),
            ("red", "", "red"))  # fmt: skip
    petals = "".join(
        f'<div class="chk" id="{p}"><h3 class="cn2">{e(PETAL_NAME[p])}</h3><dl class="cs">'
        + "".join(f"<div><dt>{chip(state, STEP_WORD[step], form)}</dt><dd>{e(rule)}</dd></div>"
                  for (state, form, step), rule in zip(keys, PETAL_RULE[p], strict=True))
        + "</dl></div>"
        for p in ids
    )  # fmt: skip
    checks = "".join(
        f'<div class="chk" id="{c}"><h3 class="cn2">{e(CHECK_NAME[c])}</h3>'
        + rules((("held", CHECK_HELD[c]), ("failed", CHECK_FAILED[c])))
        + "</div>"
        for c in S.V["checks"]
    )  # fmt: skip
    figures = "".join(
        f'<div class="chk" id="{f}"><h3 class="cn2">{e(FIGURE_NAME[f])}</h3>'
        f"{rules(FIGURE_RULE[f])}</div>"
        for f in FIGURE_RULE
    )
    gate = ("The six checks are tests we run on every system. A system passes on a model when "
            "all six checks are held there. The five petals grade what the publisher states, and "
            "Faithful model what our fidelity run measured: a failed check turns its petals red, "
            "a held check never turns one green.")  # fmt: skip
    # why a petal is red or hollow: one address per cause, which a system page's State cell links
    petal_causes = "".join(
        f'<div id="cause-{e(k)}"><dt>{e(CAUSE_WORD[k])}</dt><dd>{e(v)}</dd></div>'
        for k, v in PETAL_CAUSE_RULE.items()
    )  # fmt: skip
    causes = "".join(f'<div id="cause-{e(k.replace(" ", "-"))}"><dt>{e(k)}</dt><dd>{e(v)}</dd></div>'
                     for k, v in CHECK_CAUSE_WORD.items())  # fmt: skip
    passed = (f'<p class="rd" id="passed">{e(gate)}</p>'
              f'<p class="rd" id="not-tested">{e(NOT_TESTED)}</p>')  # fmt: skip
    parts = (("glyph", "Glyph"), ("checks", "The six checks"), ("undecided", "Undecided"),
             ("figures", "Figures"), ("order", "Order"))  # fmt: skip
    key = (f'<div class="cwrap"><div class="gbig">{glyph}</div><div class="clist">{petals}'
           f'<p class="rd hl">{e(HOLLOW_RULE)}</p><dl class="cs pcause">{petal_causes}</dl>'
           f'<p class="rd hl" id="reading">{e(READING_RULE)}</p>'
           "</div></div>")  # fmt: skip
    body = f"""
{header("checks")}
<main id="main" class="sys">
  {title_band("Checks")}
  {pnav("Checks", parts)}
  <div class="wrap">
    {section("glyph", "Glyph", key)}
    {section("checks", "The six checks", f'{passed}<div class="clist">{checks}</div>')}
    {section("undecided", "Undecided", f'<dl class="cs">{causes}</dl>')}
    {section("figures", "Figures", f'<div class="clist">{figures}</div>')}
    {section("order", "Order", rules(ORDER_RULE, ids=("unranked",)))}
  </div>
</main>
{footer()}"""
    return page("Checks", "The five petals of the glyph, the six checks, the figures, the order "
                "rule.", body, "system checkspage", CHECKS_PAGE.strip("/"), "home")  # fmt: skip


def build_mandate():
    """The mandate: the belief as the headline, what the site is for, then what we do, what we
    do not do, who runs it (with the members, once any has agreed) and how to check us. A line
    bound by a rule links its label to the file that holds it, the rule named in the title."""

    def label(text, name, path):
        if not path:
            return e(text)
        return (f'<a href="{e(link(path))}" title="{e(path.rsplit("/", 1)[-1])}, {e(name)}">'
                f"{e(text)}</a>")  # fmt: skip

    members = S.V["credit"]["members"]
    # the members' names in display type, a ruled row; nothing while none has agreed
    row = ('<div class="mbr"><dt>Members</dt><dd><ul class="mbl">' + "".join(
        f'<li><a href="{e(m["url"])}">{e(m["name"])}</a></li>' for m in members)
        + "</ul></dd></div>") if members else ""  # fmt: skip
    blocks = "".join(
        section(title.lower().replace(" ", "-"), title, '<dl class="cs">' + "".join(
            f"<div><dt>{label(text, name, path)}</dt><dd>{e(words)}</dd></div>"
            for text, name, path, words in lines)
            + (row if title == MANDATE_MEMBERS_IN else "") + "</dl>")
        for title, lines in MANDATE
    )  # fmt: skip
    parts = [(title.lower().replace(" ", "-"), title) for title, _ in MANDATE]
    body = f"""
{header("mandate")}
<main id="main" class="sys">
  {title_band(MANDATE_BELIEF, cls="ttl creed")}
  {pnav("Mandate", parts)}
  <div class="wrap">
    <p class="rd lead">{e(MANDATE_WHAT)}</p>
    {blocks}
  </div>
</main>
{footer()}"""
    return page("Mandate", MANDATE_WHAT, body, "system mandatepage", MANDATE_PAGE.strip("/"),
                "home")  # fmt: skip


def build_404():
    """Not found: the models of the ladder, largest first, each leading to its section, and the
    systems with a page, each with its glyph and model; the header and footer link the rest."""
    models = "".join(
        f'<li><a href="/#{e(r["id"])}"><span class="lp">{e(params(r["parameters_total"]))}</span>'
        f'<span class="ln">{e(r["model"])}</span></a></li>'
        for r in S.V["rungs"]
    )
    systems = "".join(
        f'<li><a href="{e(href(r))}">{glyph_svg(2, states(r))}'
        f'<span class="ln">{e(name_of(r))}</span><span class="lp">{e(rung_of(r)["model"])}</span>'
        "</a></li>"
        for r in S.ROWS
    )
    lists = "".join(
        f'<section class="blk" aria-labelledby="h-{k}"><h2 class="sect" id="h-{k}">{t}</h2>'
        f'<ul class="lost{c}">{items}</ul></section>'
        for k, t, c, items in (("models", "Models", "", models),
                               ("systems", "Systems", " lsys", systems))
        if items
    )  # fmt: skip
    body = f"""
{header(None)}
<main id="main" class="sys">
  {title_band("Not found")}
  <div class="wrap">{lists}</div>
</main>
{footer()}"""
    return page("Not found", "No page at this address.", body, "system notfound", "404", None)
