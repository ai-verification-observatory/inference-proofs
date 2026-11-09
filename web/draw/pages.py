"""The other pages: one per benchmarked system (its glyph with each property beside its slice,
facts, figures and tamper tests), the reference page, the criteria page and the 404 page.
"""

import re

from . import state as S
from .chrome import CRIT_PAGE, footer, header, page, ref_label
from .claims import (
    card_fact,
    card_full,
    evidence_of,
    gap_block,
    how_we_read,
    property_controls_of,
    read_entries,
    run_ref,
)
from .hexagon import hex_svg, key_mini, pie_svg, sized
from .overview import kind_words, model_line, plate_prefix
from .plates import (
    COLS,
    EXT,
    MORE,
    PER_GBIT,
    PER_GBIT_COLS,
    aria,
    blob,
    configs_of,
    fig,
    figure_rows,
    glyph,
    has_figures,
    keep,
    left_words,
    metric_of,
    name_of,
    overhead_notes,
    path_html,
    per_gbit_basis,
    plate,
    readable,
    row_id,
    runs_counts,
    setup_diff,
    setup_dl,
    setup_parts,
    setup_shared,
    source_label,
    source_words,
    upstream,
    with_rule,
    words,
)
from .words import (
    ACCEPTED_WHY,
    CONTROL_WORDS,
    FAIL_KIND,
    FAIL_STEP,
    FAMILY_WORD,
    NOT_READ_HEAD,
    OUTCOME_SHORT,
    OUTCOME_VERB,
    OUTCOME_WORDS,
    STATE_CLS,
    STATE_ORDER,
    STATE_WORD,
    STATUS_WORD,
    TAMPERS,
    amount,
    count_word,
    dates_html,
    e,
    gpu_words,
    labels,
    mean_words,
    scope_words,
    shown,
    sig4,
    spread_line,
    why_words,
)

# ------------------------------------------------------------------ system page: the pie with its six properties around it


# Clockwise from twelve, slices 1 to 3 face right and 4 to 6 face left; each property sits on its slice's side.
SIDE = {1: "r", 2: "r", 3: "r", 4: "l", 5: "l", 6: "l"}


def rose_item(c, pre, ev="", src=""):
    """One property beside its slice: its name (a link to what its states mean), its question for
    screen readers, the state, and our short reason (left out when it only repeats Not stated).
    On a system page the reason is the link to the property's entry in "How we read it" (`src`,
    its id), or the state word where there is no reason; for an overridden cell, the one line
    that changes its state follows (`ev`, draw/claims.py); nothing else. The state's square is
    shown only where the rows sit away from the glyph (phones; the slice beside it has the ink)."""
    generic = (
        c["state"] == "not_stated" and c["reason"].startswith("Not stated") and not c["quotes"]
    )
    why = "" if generic else e(words(c["reason"]))
    sr = f'<span class="sr">: how we read {e(c["name"])}</span>'
    word = e(c["word"])
    if src and why:
        why = f'<a class="psrc" href="#{e(src)}">{why}{sr}</a>'
    elif src:
        word = f'<a class="psrc" href="#{e(src)}">{word}{sr}</a>'
    reason = f'<p class="rr">{why}</p>' if why else ""
    state = f'<p class="rs"><i class="sw {STATE_CLS[c["state"]]}"></i>{word}</p>'
    return (
        f'<li class="rp {SIDE[c["n"]]}" id="{pre}p-{e(c["prop"])}" data-n="{c["n"]}">'
        f'<p class="rn"><a href="{CRIT_PAGE}#{e(c["prop"])}">{e(c["name"])}</a><span class="sr">. {e(c["question"])}</span></p>'
        f"{state}{reason}{ev}</li>"
    )


def rose(g, hid, name, level=2, pre="", ev=None, src=None):
    """The pie, centred, with each property beside its own slice. level: the hidden heading's level
    under the page's own; pre: an id prefix when one page holds several roses; ev and src: on a
    system page, each property's overridden line and the id of its entry in "How we read it",
    by property id."""
    ev, src = ev or {}, src or {}
    items = "".join(
        rose_item(c, pre, ev.get(c["prop"], ""), src.get(c["prop"], "")) for c in g["cells"]
    )
    return (
        f'<div class="rose"><h{level} id="{e(hid)}" class="sr">What one proof establishes</h{level}>'
        f'<div class="rpie" role="img" aria-label="{e(aria(g, name, outside=True))}">{hex_svg(184, states=g["states"], hit=True, names=[c["name"] for c in g["cells"]])}</div>'
        f'<ol class="rprops" role="list" aria-labelledby="{e(hid)}">{items}</ol></div>'
    )


def facts_dl(items):
    return (
        '<dl class="facts">'
        + "".join(f"<div><dt>{e(k)}</dt><dd>{v}</dd></div>" for k, v in items)
        + "</dl>"
    )


def price_text(cfg):
    """The GPU-hour price a cost assumes (RFC-0006 C1, C7), from the release's reference file:
    "at 5.345 USD per H200-hour (median list price, four providers, 2026-11-08)"; "" without."""
    pr = cfg.get("price")
    if not pr:
        return ""
    gpu = cfg["gpu"]["short"] or cfg["gpu"]["model"]
    return (f"at {sig4(pr['usd_per_gpu_hour'])}\u00a0USD per {gpu}-hour (median list price, "
            f"{count_word(pr['providers'])} providers, {pr['date']})")  # fmt: skip


def price_words(cfg):
    """`price_text`, linked to the reference file it comes from."""
    said = price_text(cfg)
    return (f'<a href="{e(blob(cfg["price"]["file"]))}">{dates_html(e(said))}{EXT}</a>'
            if said else "")  # fmt: skip


def label_cell(key, html):
    """One label of a more-numbers row: its key, which the column's head names from 761 px and
    the cell itself where the cells stack (phones), then its words; empty without words."""
    cls = f"ml m-{key}"
    return (
        f'<td class="{cls}"><span class="mk">{key}: </span>{html}</td>'
        if html
        else f'<td class="{cls}"></td>'
    )


def more_table(cfg, caption, shared=None):
    """The other figures, each with the labels its setup's line does not state (S2, S3), one
    column each, its head printed once: the spread; the scope when timed, with grade and tier
    where they differ and, for a cost, the price it assumes; the record's key in the release
    index. A missing one is one row: its name and why, as a plate with no value."""
    shared = shared or {}
    more = ""
    for metric, label in MORE:
        f = cfg["figures"][metric]
        head = f'<th scope="row">{e(readable(label))}</th>'
        if f["value"] is None:
            more += (
                f'<tr>{head}<td class="ml mw" colspan="4">{with_rule(why_words(f, cfg))}</td></tr>'
            )
            continue
        cells = {k: v for k, v, _ in figure_rows(cfg, f) if k not in shared}
        spread = with_rule(readable(cells.pop("spread", "")))
        scope = [cells.pop("scope")] if "scope" in cells else []
        scope = " · ".join(scope + [f"{k}: {v}" for k, v in cells.items()])
        scope = dates_html(with_rule(readable(scope)))
        if f["unit"] == "USD/1k_token" and (price := price_words(cfg)):
            scope += ("\u00a0· " if scope else "") + price
        n, u = amount(f["value"], f["unit"])
        # "GPU cost per 1M tokens": the row names the basis, so the value keeps its currency
        val = fig(f"{n} {u.split(' per ')[0]}" if f["unit"] == "USD/1k_token"
                  else shown(f["value"], f["unit"]))  # fmt: skip
        said = f' title="{e(mean_words(f))}"' if f.get("stats") else ""
        src = f'<span class="src">{path_html(source_words(f, shared))}</span>'
        more += (f'<tr>{head}<td class="mv"{said}>{val}</td>{label_cell("spread", spread)}'
                 f'{label_cell("scope", scope)}{label_cell("source", src)}</tr>')  # fmt: skip
    heads = "".join(f'<th scope="col">{h}</th>' for h in ("Figure", "Value", "Spread", "Scope",
                                                          "Source"))  # fmt: skip
    return (
        f'<table class="mtab more"><caption class="sr">{e(caption)}</caption>'
        f"<thead><tr>{heads}</tr></thead><tbody>{more}</tbody></table>"
    )


def control_name(cid):
    """A control's id with its tamper in words (RFC-0008): "C6 (flipped bit)"."""
    return f"{cid} ({CONTROL_WORDS[cid]})" if cid in CONTROL_WORDS else cid


def accepted_words(cfg):
    """Which control each stored `accepted` outcome is, by its id (the block under the tally
    names it in words), and whether its own expected set holds acceptance: a system's
    weakened-prover control expects it, a tampered proof does not (RFC-0008); one that tampered
    only with a part the system declares verify does not read is named alone, its block saying
    it tests nothing (RFC-0008, amendment of 2026-11-09). Listed from the records, never
    counted."""
    out = []
    for a in cfg["accepted"]:
        if a.get("not_read"):
            out.append(a["control"])
        else:
            out.append(ACCEPTED_WHY[(a["source"], a["passed"] is True)].format(id=a["control"]))
    return "; ".join(out)


def tamper_words(cfg):
    """The runs the counts are over (each kept run that recorded its controls, by its date and
    ordinal linked to its `controls.json`), then each stored outcome count of the
    configuration's controls (RFC-0008), zero counts left out; no sum or difference of them
    (AGENTS.md rule 3). The accepted count says which controls it counts, so a control that
    expects acceptance never reads as a tampered proof the checker took, and one that tests
    nothing says so."""
    counts = cfg["controls"]["counts"]
    said = []
    for k, w in OUTCOME_WORDS:
        if counts.get(k):
            # each count in the weight of a figure, its words in the reading voice
            count = w.format(n="\x00").replace("\x00", f"<b>{counts[k]:,}</b>")
            words = e(readable(count.replace("<b>", "\x01").replace("</b>", "\x02")))
            words = words.replace("\x01", "<b>").replace("\x02", "</b>")
            if k == "accepted" and not all(a.get("not_read") for a in cfg["accepted"]):
                words += f" ({e(accepted_words(cfg))})"
            said.append(words)
    if not said:
        return ""
    runs = cfg["control_runs"]
    refs = ", ".join(run_ref(r["run_id"], r["record"]) for r in runs)
    word = "run" if len(runs) == 1 else "runs"
    return f"In {len(runs)} {word} ({refs}): {'\u00a0· '.join(said)}"


def control_tests(cfg):
    """The system's own registered controls (RFC-0008 §System-specific controls) and what the
    checker did with each in the runs, as stored."""
    out = ""
    for sc in cfg["system_controls"]:
        outcomes = {o["outcome"] for o in sc["outcomes"]}
        if sc["kind"] == "weakened_prover":
            text = f"Control test: we turned off one check on purpose, with a switch {name_of(cfg['system'])} documents for this."
        else:
            text = f"Control test {sc['id']}."
        passed = {o["passed"] for o in sc["outcomes"]}
        expect = ""
        if passed == {True}:
            expect = ", as this control expects"
        elif passed == {False}:
            expect = ", outside what this control expects"
        if len(outcomes) == 1:
            o = outcomes.pop()
            text += (
                f" The checker {OUTCOME_VERB[o]} the proof{expect}."
                if o in OUTCOME_VERB
                else f" Outcome: {o}{expect}."
            )
        else:
            text += (
                " Outcomes by run: "
                + "; ".join(f"{x['run_id']}: {x['outcome']}" for x in sc["outcomes"])
                + "."
            )
        link = (
            f' <a class="qs" href="{e(sc["source"])}">{path_html(source_label(sc["source"]), ext=True)}</a>'
            if sc["source"]
            else ""
        )
        out += f'<p class="ctl">{e(text)}{link}</p>'
    return out


def status_words(st, cfg):
    """A status fact in one form for every system: the system's own words about it, linked to
    its README at the pin, the state word in the link's title; or, without them, the state
    word; then its last push (where it was read in the title)."""
    word = STATUS_WORD[st["state"]]
    if st.get("quote"):
        up = upstream(cfg)
        href = f"https://github.com/{up['repo']}/blob/{up['commit']}/README.md"
        out = f'<a href="{e(href)}" title="{e(word)}">“{e(st["quote"])}”{EXT}</a>'
    else:
        out = e(word)
    if st.get("last_push"):
        src = f"{st['source']}, retrieved {st['retrieved']}" if st.get("source") else ""
        out += (f' · <span class="nw" title="{e(src)}">last push {e(st["last_push"])}</span>'
                if src else f" · last push {e(st['last_push'])}")  # fmt: skip
    return out


def pinned(cfg):
    """The card's repository at its pin first (RFC-0016 SRC-2: only it decides), then every other
    repository the row's sources read cite, at the commit the criteria file read it."""
    up = upstream(cfg)
    repos = [(up["repo"], up["commit"])]
    pins = S.CRIT["pins"]
    cited = set()
    for c in S.CRIT["rows"][cfg["system"]]["cells"].values():
        for q in [*c["quotes"], *((c.get("outside_pin") or {}).get("quotes") or [])]:
            cited.add(q.get("repo"))
        cited |= {s["repo"] for s in c["sources_read"] if "repo" in s}
    repos += [(r, pins[r]) for r in pins if r in cited and r != up["repo"]]
    return "".join(
        f'<a href="https://github.com/{e(r)}/tree/{e(c)}">{path_html(r)}<span class="nw"> @{e(c[:8])}{EXT}</span></a>'
        for r, c in repos
    )


def config_where(cfg):
    return " · ".join(
        [cfg["configuration"], cfg["workload"]["id"], cfg["workload"]["division"], cfg["profile"]]
    )


def setup_words(cfg):
    """A setup as a reader names it: model, prompt, batch and GPUs; its ids ride in the
    heading's title and in the workload line under it."""
    return " · ".join(setup_parts(cfg))


def setup_heading(cfg, hid):
    """A setup's heading. On a page of several setups it prints only the words that set this
    one apart ("24 requests per batch"), so it stays one line; the full line is read aloud and
    rides in its title with the ids."""
    full = setup_words(cfg)
    title = f"{full} · {config_where(cfg)}"
    if len(configs_of(cfg["system"])) == 1:
        return f'<h3 id="{e(hid)}" class="sect sm setup" title="{e(title)}">{keep(readable(full))}</h3>'
    short = " · ".join(setup_diff(cfg))
    return (f'<h3 id="{e(hid)}" class="sect sm setup" title="{e(title)}">'
            f'<span aria-hidden="true">{keep(readable(short))}</span>'
            f'<span class="sr">{e(full)}</span></h3>')  # fmt: skip


def left_out(cfg):
    """S7: every run of the configuration its figures leave out, each by its date and ordinal
    linked to its record (its id in the link's title): a failed run with its failure kind, step
    and exit code, its last line one press away; a superseded run with its reason and the run
    that replaces it; an ineligible run with its reasons. Named in words."""
    runs = cfg["runs"]
    rows = []
    for f in runs["failed"]:
        what = FAIL_KIND[f["kind"]] + (f" {FAIL_STEP[f['step']]}" if f["step"] in FAIL_STEP else "")
        if f["exit_code"] is not None:
            what += f" · exit\u00a0{f['exit_code']}"
        last = (f'<details class="ll"><summary>last line</summary><p>“{e(f["last_line"])}”</p>'
                "</details>" if f["last_line"] else "")  # fmt: skip
        rows.append(f"{e(what)} · {run_ref(f['run_id'], f['record'])}{last}")
    for x in runs["left_out"]:
        if x["replaced_by"]:
            why = "; ".join(r.split(": ", 1)[1] if ": " in r else r for r in x["reasons"])
            by = run_ref(x["replaced_by"], x["replaced_by_record"])
            rows.append(
                f"superseded: {e(why)}; replaced by {by} · {run_ref(x['run_id'], x['record'])}"
            )
        else:
            rows.append(f"left out: {e('; '.join(x['reason_words']))} · "
                        f"{run_ref(x['run_id'], x['record'])}")  # fmt: skip
    if not rows:
        return ""
    items = "".join(f"<li>{r}</li>" for r in rows)
    return f'<ul class="runs lo" aria-label="Runs left out of these figures">{items}</ul>'


def runs_lead(cfg):
    """What the figures are over (S7): the completed runs, then those not counted, by kind."""
    runs = cfg["runs"]
    out = []
    if runs["failed"]:
        out.append(f"{len(runs['failed'])} failed")
    sup = sum(1 for x in runs["left_out"] if x["replaced_by"])
    if sup:
        out.append(f"{sup} superseded")
    other = len(runs["left_out"]) - sup
    if other:
        out.append(f"{other} left out")
    said = f"Runs: {len(runs['completed'])} completed"
    return said + (f", {', '.join(out)} (not counted)" if out else "")


def config_figures(cfg, name, one, basis=True):
    """One configuration's figures under a heading naming its setup: what they are over and the
    runs left out (S7), the labels its figures share, a plate per overview column with what
    qualifies the overhead under them, the per-Gbit basis under its three plates (basis: False
    where the page prints it once for every setup), and the other figures in a table. On a page
    of several setups each is a section of its own, its heading held at the top of the screen
    while its figures scroll (words.css), so a figure link's landing names its setup."""
    rid = row_id(cfg)
    shared = setup_shared(cfg)
    pre = plate_prefix(cfg)
    raw = "".join(plate(cfg, c, pre, shared) for c in COLS)
    per_gbit = "".join(plate(cfg, c, pre, shared) for c in PER_GBIT_COLS)
    body = (
        f"{setup_heading(cfg, f'h-{rid}')}"
        f'<p class="lead">{e(readable(runs_lead(cfg)))}</p>{left_out(cfg)}{setup_dl(cfg, shared)}'
        f'<div class="plates plates-sys">{raw}</div>{overhead_notes(cfg)}'
        f'<div class="plates plates-sys pgb"><p class="pgh">{e(PER_GBIT[:1].upper() + PER_GBIT[1:])}</p>'
        f"{per_gbit}</div>{per_gbit_basis(cfg) if basis else ''}"
        f"{more_table(cfg, f'More numbers for {name}, with spread, scope and source', shared)}"
    )
    return (body if one else
            f'<section class="cfgfigs" id="{e(rid)}" aria-labelledby="h-{e(rid)}">{body}</section>')  # fmt: skip


def figures_body(cfgs, name):
    """Every setup's figures. The per-Gbit basis (weight bits, note, limit) is grouped by what it
    says: where every setup of a page of several shares it, it prints once, under the Figures
    heading with the name of the basis, before the setups it qualifies; otherwise under each
    setup's per-Gbit plates."""
    one = len(cfgs) == 1
    bases = {per_gbit_basis(c) for c in cfgs}
    once = not one and len(bases) == 1
    head = (f'<p class="lbl basis-h">{e(PER_GBIT[:1].upper() + PER_GBIT[1:])}</p>{bases.pop()}'
            if once else "")  # fmt: skip
    return head + "".join(config_figures(c, name, one, basis=not once) for c in cfgs)


def trial_html(t):
    """One stored trial on one line (RFC-0008 §Reporting, "in full"): its seed, the mutation as
    stored, the outcome with the raw exit code and last line, and its time; the controls.json
    linked beside holds every field."""
    mut = t.get("mutation") or {}
    if "bit_offset" in mut and "part" in mut:
        how = f"bit {mut['bit_offset']:,} of {mut['part']} flipped"
    else:
        how = ", ".join(f"{k} {v}" for k, v in mut.items())
    raw = []
    if t.get("raw_exit_code") is not None:
        raw.append(f"exit {t['raw_exit_code']}")
    if t.get("raw_last_line") is not None:
        raw.append(f"“{t['raw_last_line']}”")
    parts = [f"seed {t['seed_index']}" if "seed_index" in t else "", how,
             OUTCOME_SHORT[t["outcome"]] + (f" ({', '.join(raw)})" if raw else ""),
             shown(t["seconds"], "s") if t.get("seconds") is not None else ""]  # fmt: skip
    return f"<li>{e(readable(' · '.join(x for x in parts if x)))}</li>"


def unexpected_full(cfg):
    """RFC-0008 §Reporting: each outcome outside its control's expected set, from its stored
    record: the control named in words, its run, outcome and expected set, the honest twin,
    each trial on one line, and the record it comes from. An accepted record whose accepted
    trials all tampered with a part the system declares verify does not read says it tests
    nothing, with the same control's outcome in the configuration's other runs beside it."""
    out = ""
    for u in cfg["unexpected"]:
        rec = u["stored"] or {}
        name = control_name(u["control"])
        expected = ", ".join(OUTCOME_SHORT[x] for x in rec.get("expected") or [])
        title = ""
        if u.get("not_read"):  # tests nothing: the expected set rides in the head's title
            parts = ", ".join(f'<span class="nw">{e(x)}</span>' for x in u["not_read"])
            lead = f"{e(name)}: {NOT_READ_HEAD.format(parts=parts)}"
            title = f"expected outcomes: {expected}"
        else:
            lead = (f"{e(name)}: {e(OUTCOME_SHORT[u['outcome']])}, outside its expected "
                    f"outcomes (expected: {e(expected)})")  # fmt: skip
        rows = [("", lead, title)]
        rows.append(("run", run_ref(u["run_id"], u["record"] or None), ""))
        tw = rec.get("twin")
        if tw:
            rows.append(
                ("honest proof", e(f"verdict {tw['verdict']}, exit {tw['raw_exit_code']}"), "")
            )
        trials = rec.get("trials") or []
        if trials:
            same = sum(1 for t in trials if t["outcome"] == u["outcome"])
            label = ("trial" if len(trials) == 1 else
                     f"{same} of {len(trials)} trials {OUTCOME_SHORT[u['outcome']]}")  # fmt: skip
            items = "".join(trial_html(t) for t in trials)
            rows.append((label, f'<ol class="trials">{items}</ol>', ""))
        for o in u.get("others") or []:
            # the outcome over the run's trials, and where its trials were kept (RFC-0008 READ-3)
            tamper = TAMPERS.get(u["control"], "changes")
            note = (f" ({tamper} kept off {', '.join(o['parts_not_read'])}, declared not read)"
                    if o["parts_not_read"] else "")  # fmt: skip
            count = f"{o['trials_same']} of {o['trials']} trials " if o.get("trials") else ""
            rows.append(("other run", f"{e(readable(count + OUTCOME_SHORT[o['outcome']] + note))}"
                                      f" · {run_ref(o['run_id'], o['record'])}", ""))  # fmt: skip
        items = "".join(f"<div><dt>{e(k)}</dt><dd>{v}</dd></div>" if k else
                        f'<div class="ul"><dd{f' title="{e(t)}"' if t else ""}>{v}</dd></div>'
                        for k, v, t in rows)  # fmt: skip
        out += (f'<dl class="tlab unexp" id="unexpected-{e(u["control"])}-{e(u["run_id"])}">'
                f"{items}</dl>")  # fmt: skip
    return out


def config_tamper(cfg, many):
    """One configuration's tamper tests: its setup (where a page holds several), each stored
    outcome count, every outcome outside its expected set, then the system's own controls."""
    head = setup_heading(cfg, f"t-{row_id(cfg)}") if many else ""
    tally = tamper_words(cfg)
    said = (f'<p class="tamper">{tally}</p>' if tally
            else '<p class="tamper none">No tamper test ran on this setup.</p>')  # fmt: skip
    return f"{head}{said}{unexpected_full(cfg)}{control_tests(cfg)}"


# what a system page holds, by the plate that holds it, as its description names it
DESC_FIGURES = (("overhead", "overhead against production serving"), ("per_bit", "proving time"),
                ("proof_size", "proof size"), ("check_time", "check time"))  # fmt: skip


def system_desc(sid):
    """A system page's description (search results, link previews), from the view, no number:
    the system, the models and GPUs it ran, and what the page holds, each figure only where a
    setup has a value for it."""
    cfgs = configs_of(sid)
    models = " and ".join(
        dict.fromkeys(S.MODEL_NAME[c["workload"]["model"]["digest"]] for c in cfgs)
    )
    gpus = " or ".join(dict.fromkeys(gpu_words(c) for c in cfgs))
    held = ["what one proof establishes"]
    held += [w for col, w in DESC_FIGURES
             if any(c["figures"][metric_of(c, col)]["value"] is not None for c in cfgs)]  # fmt: skip
    said = ", ".join(held[:-1]) + f" and {held[-1]}" if len(held) > 1 else held[0]
    return f"{name_of(sid)} proving {models} on {gpus}: {said}."


def claims_section(sid, cfgs, g, facts):
    """S1: the card's validated claims (the pie, and per property its state, reason, a link to
    how we read it and an overridden cell's one line; then, folded, how we read it: per property
    the deciding quote with its source, both quotes of a conflict, the sources read and the
    control outcomes), its identity among the facts, the card in full (folded) and its quality
    gap and residual beside the agreement rate; before any figure. "How we read it" stays in the
    validated claims, before the facts in reading order (S1 item 1); words.css sets it under the
    pie and the facts on wide screens."""
    cfg = cfgs[0]
    pc = property_controls_of(cfgs)
    order = [c["prop"] for c in g["cells"]]
    entries = read_entries(sid, pc, order)
    src = {prop: f"read-{prop}" for prop in entries}
    name = name_of(sid)
    return (
        f'<section class="claims" id="claims-{e(cfg["configuration"])}" aria-labelledby="h-props">'
        f'<div class="over" id="properties">{rose(g, "h-props", name, ev=evidence_of(sid, pc, order), src=src)}'
        f"{how_we_read(entries)}{facts_dl(facts)}</div>"
        f"{card_full(cfg, sid)}{gap_block(cfgs)}</section>"
    )


def build_system(sid):
    """A system page, drawn with its card's repository as the page's home (`S.HOME`): its source
    links print path and lines, the facts' pinned row naming the repository once."""
    S.HOME = upstream(configs_of(sid)[0])["repo"]
    try:
        return system_page(sid)
    finally:
        S.HOME = ""


def system_page(sid):
    name = name_of(sid)
    cfgs = configs_of(sid)
    cfg = cfgs[0]
    one = len(cfgs) == 1
    g = glyph(sid)
    row = S.V["facts"]["rows"][sid]
    models = list(dict.fromkeys(model_line(c) for c in cfgs))
    facts = [
        ("kind", keep(words(f"{FAMILY_WORD[S.CRIT['rows'][sid]['family']]}: {row['technique']}"))),
        ("model" if len(models) == 1 else "models", keep(" · ".join(models))),
        ("pinned", f'<span class="links">{pinned(cfg)}</span>'),
        ("licence", e(row["licence"]["name"])),
        ("status", status_words(row["status"], cfg)),
        ("card", card_fact(cfg)),
        (
            "adapter",
            f'<a href="{e(cfg["adapter_readme"])}">{path_html(f"systems/{sid}/README.md", ext=True)}</a>',
        ),
    ]
    body = f"""
{header(sid)}
<main id="main" class="sys">
  <section class="mast mast-sys" aria-labelledby="h-name">
    <div class="mast-in"><h1 id="h-name" class="sysname"><span class="lt">{e(name)}</span></h1></div>
  </section>
  <div class="wrap">
    {claims_section(sid, cfgs, g, facts)}
    <section class="blk" id="figures" aria-labelledby="h-figs">
      <div class="sec-h"><h2 id="h-figs" class="sect">Figures</h2></div>
      {figures_body(cfgs, name)}
    </section>
    <section class="blk" id="tamper" aria-labelledby="h-tamper">
      <h2 id="h-tamper" class="sect">Tamper tests</h2>
      {"".join(config_tamper(c, not one) for c in cfgs)}
    </section>
  </div>
</main>
{footer()}"""
    return page(
        name,
        system_desc(sid),
        body,
        "system",
        sid,
        sid,
    )


# what production serving measured, each in a column of the reference page's table: the stored
# statistic, the head, and the unit the head names (its cells print the number alone when they
# all read in it)
SERVING_COLS = (("gpu_seconds_per_token_prove.steady", "GPU time per token", None),
                ("rate_prove.steady", "Tokens per second", "tokens/s"),
                ("cost_per_1k_tokens_prove.steady", "GPU cost per 1M tokens", None))  # fmt: skip


def engine_words(cfg):
    sv = cfg.get("serving") or {}
    return f"{sv['engine']} {sv['version']}" if sv.get("engine") else ""


def serving_setup(cfg, shared=()):
    """What a serving configuration ran, as the overhead's conditions record it, less what
    every row of the table shares (`shared`, said once in its caption)."""
    sv = cfg.get("serving") or {}
    model = S.MODEL_NAME[cfg["workload"]["model"]["digest"]]
    gpus = sv.get("gpus") or cfg["gpu"]["count"]
    parts = [model, f"{sv.get('publisher')} {sv.get('precision')}" if sv.get("precision") else "",
             engine_words(cfg), f"{count_word(gpus)} {cfg['gpu']['short'] or cfg['gpu']['model']}"]  # fmt: skip
    if sv.get("batch"):
        b = sv["batch"]
        parts.append(f"{b:,} request{'s' if b != 1 else ''} per batch ({sv['load']} load)")
    return " · ".join(x for x in parts if x and x not in shared)


def serving_cols(cfgs):
    """Per column, whether its cells print the number alone: every row's value reads in the
    unit its head names."""
    bare = {}
    for metric, _, unit in SERVING_COLS:
        units = {amount(c["figures"][metric]["value"], c["figures"][metric]["unit"])[1]
                 for c in cfgs if c["figures"][metric]["value"] is not None}  # fmt: skip
        bare[metric] = unit is not None and units == {unit}
    return bare


def serving_cell(cfg, metric, bare):
    """One measured value of production serving: the value (the number alone where its head
    names its unit, `bare`), every label and its record in its title (S2, S3)."""
    f = cfg["figures"][metric]
    if f["value"] is None:
        return '<td><span class="na">No value</span></td>'
    n, u = amount(f["value"], f["unit"])
    val = fig(n if bare else f"{n} {u.removesuffix('/token').split(' per ')[0]}")
    st = f.get("stats") or {}
    # the row's head names its runs; the title the spread over them
    said = [f"{n} {u}", scope_words(f, cfg), *([spread_line(f)] if st else []),
            *(f"{k}: {v}" for k, v in labels(f, cfg)[1:]), f"source: {source_words(f)}"]  # fmt: skip
    if f["unit"] == "USD/1k_token" and (price := price_text(cfg)):
        said.append(price)
    return f'<td title="{e(readable(" · ".join(said)))}">{val}</td>'


# why a completed serving run is in no steady statistic, from its own records (iproofs.site.view
# run_why), in words
STEADY_WHY_WORDS = {
    "one_batch": "no steady window (one batch)",
    "short_steady": "steady window under 60 s",
    "sizing_capture": "a sizing capture",
    None: "in no statistic",
}


def serving_runs(cfg):
    """The runs a row's figures share, in HTML: "3 runs", or, where its statistics leave a
    completed run out, "4 of 5 runs", each left-out run and why in its title; None where its
    figures read different runs."""
    figs = [cfg["figures"][m] for m, _, _ in SERVING_COLS if cfg["figures"][m].get("stats")]
    read = {tuple(f.get("runs") or ()) for f in figs}
    ns = {f["stats"]["n"] for f in figs}
    if len(ns) != 1 or len(read) != 1:
        return None
    n, done, got = ns.pop(), cfg["runs"]["completed"], set(read.pop())
    left = [r for r in done if r not in got]
    if not left:
        return e(f"{n:,} run{'s' if n != 1 else ''}")
    why = [{"run_id": r, "why": (cfg.get("run_why") or {}).get(r)} for r in left]
    title = left_words(cfg, why, STEADY_WHY_WORDS)
    return f'<span class="nw" title="{e(title)}">{n:,} of {len(done):,} runs</span>'


def serving_table(gid, cfgs):
    """Production serving's measurements: one row per configuration it ran, its setup and its run
    count, then the steady GPU time per token, the rate and the cost per 1M tokens. What every
    row shares (the scope, the engine) is said once, in the caption; a head that names its
    unit holds it for its cells."""
    rows_of = [c for c in cfgs if has_figures(c)]
    if not rows_of:
        return ""
    scopes = {scope_words(c["figures"][m], c) for c in rows_of for m, _, _ in SERVING_COLS
              if c["figures"][m]["value"] is not None}  # fmt: skip
    engines = {engine_words(c) for c in rows_of}
    shared = [
        *(scopes if len(scopes) == 1 else []),
        *(x for x in engines if len(engines) == 1 and x),
    ]
    bare = serving_cols(rows_of)
    rows = ""
    for c in rows_of:
        runs = serving_runs(c)
        head = keep(readable(serving_setup(c, shared))) + (f" · {runs}" if runs else "")
        rows += (f'<tr><th scope="row">{head}</th>'
                 + "".join(serving_cell(c, m, bare[m]) for m, _, _ in SERVING_COLS) + "</tr>")  # fmt: skip
    heads = "".join(f'<th scope="col">{e(h)}</th>' for _, h, _ in SERVING_COLS)
    # the caption heads a table of serving: a shared scope reads without its "serving, " lead
    caption = "\u00a0· ".join(f'<span class="nw">{e(x.removeprefix("serving, "))}</span>'
                              for x in ["Measured", *shared])  # fmt: skip
    return (f'<table class="mtab stab" id="{e(gid)}-figures"><caption class="sect sm">{caption}</caption>'
            f'<thead><tr><th scope="col">Setup</th>{heads}</tr></thead><tbody>{rows}</tbody></table>')  # fmt: skip


def common_reason(g):
    """The words every cell's reason shares, when all six states are one: "By definition:
    nothing is checked"; "" when they share none."""
    reasons = [c["reason"] for c in g["cells"]]
    prefix = reasons[0]
    for r in reasons[1:]:
        while not r.startswith(prefix):
            prefix = prefix[:-1]
    return prefix.rstrip(" ,;.:")


def reference_claims(gid, g, name):
    """A reference's six states: where all six are one, the glyph once, small, a link to what
    the states mean (its states read in its label), beside the reason the six share ("By
    definition: nothing is checked."; RFC-0016 SRC-5, SRC-7); otherwise the glyph with each
    property beside its slice."""
    if len(set(g["states"])) == 1:
        why = common_reason(g)
        line = f'<p class="refline">{e(words(why))}.</p>' if why else ""
        # its petals name themselves under a pointer or a tap, in the line's place, as a card's do
        pie = sized(
            lambda s: pie_svg(g["states"], s, cells=g["cells"] if s == 120 else None, hit=True),
            (120, 72),
        )
        return (f'<div class="refone"><a class="refpie" href="{CRIT_PAGE}" aria-label="{e(aria(g, name))}">'
                f'{pie}</a><div class="reft">{line}<p class="tip" aria-hidden="true"></p></div></div>')  # fmt: skip
    return f'<div class="over">{rose(g, f"h-{gid}-props", name, level=3, pre=f"{gid}-")}</div>'


def build_reference():
    """One page for the references in the release: each one's name, its role, its six states,
    then what it measured (production serving: one row per configuration it ran)."""
    secs = ""
    for gid in S.V["orders"]["reference"]:
        g = glyph(gid)
        name = name_of(gid)
        cfgs = [c for c in S.CONFIGS if c["system"] == gid]
        counts = "".join(f'<p class="lead">{with_rule(readable(runs_counts(c)))}</p>'
                         for c in cfgs if not has_figures(c))  # fmt: skip
        secs += f'''
    <section class="refsys" id="{e(gid)}" aria-labelledby="h-{e(gid)}">
      <h2 id="h-{e(gid)}" class="refh">{e(name)}</h2>
      <p class="reflead">{e(kind_words(gid))}</p>
      {reference_claims(gid, g, name)}
      {serving_table(gid, cfgs)}{counts}
    </section>'''
    label = ref_label()
    names = [name_of(gid) for gid in S.V["orders"]["reference"]]
    body = f"""
{header("reference")}
<main id="main" class="sys refpage">
  <section class="mast mast-sys" aria-labelledby="h-name">
    <div class="mast-in"><h1 id="h-name" class="sysname refname"><span class="lt">{e(label)}</span></h1></div>
  </section>
  <div class="wrap">
    {secs}
  </div>
</main>
{footer()}"""
    its = "its" if len(names) == 1 else "their"
    return page(
        label,
        f"{' and '.join(names)}: {its} six properties and what was measured.",
        body,
        "system reference",
        "reference",
        "home",
    )


# ------------------------------------------------------------------ the criteria and the 404


# a property's Not stated rule that adds a case to the shared one (printed once, under the
# title): "Not stated, including <case>, or not copied yet." prints as the case; any other
# Not stated rule says what the shared rule and the property's note already say, and is left out
NOT_STATED_CASE = re.compile(r"^Not stated, including (.+?)(?:, or not copied yet)?\.$")


def not_stated_case(rule):
    """The case a property's Not stated rule adds to the shared rule, as a sentence, or None."""
    m = NOT_STATED_CASE.match(rule)
    return f"{m[1][:1].upper()}{m[1][1:]}." if m else None


def not_stated_rule():
    """The Not stated rule every property shares: the criteria file's meaning of the state, with
    the clause its property rules end with ("or not copied yet")."""
    return S.CRIT["states"]["not_stated"]["meaning"]


def rule_words(rule):
    """A state's rule as the criteria page prints it: the column already says it is what the
    documentation says, so the lead-in goes; the shared Not stated clause is printed once."""
    text = words(rule).replace(", or we have not recorded it yet", "")
    m = re.match(r"The documentation says (?:that )?(.)", text)
    if m:
        text = m[1].upper() + text[m.end() :]
        text = text.replace(", or that ", ", or ").replace(", that ", ", ")
    return readable(text)


def build_criteria():
    """What each state means for each property, from the criteria file: the rules the glyphs are drawn by."""
    # a jump index of the six properties, shown on phones (words.css), names only
    idx = "".join(
        f'<li><a href="#{e(p["id"])}">{key_mini(i + 1, 22)}<span>{e(p["name"])}</span></a></li>'
        for i, p in enumerate(S.PROPS)
    )
    secs = ""
    for i, p in enumerate(S.PROPS):
        rules = {s: rule_words(p["rules"][s]) for s in STATE_ORDER if s != "not_stated"}
        if case := not_stated_case(p["rules"]["not_stated"]):
            rules["not_stated"] = readable(words(case))
        states = "".join(
            f'<div><dt><i class="sw {STATE_CLS[s]}"></i>{e(STATE_WORD[s])}</dt><dd>{with_rule(r)}</dd></div>'
            for s, r in rules.items()
        )
        note = f'<p class="cnote">{e(words(p["not_here"]))}</p>' if p.get("not_here") else ""
        secs += (
            f'<section class="crit" id="{e(p["id"])}" aria-labelledby="h-{e(p["id"])}">'
            f'<div class="ch">{sized(lambda s, n=i + 1: key_mini(n, s), (48, 32))}<h2 id="h-{e(p["id"])}" class="sect">{e(p["name"])}</h2>'
            f'<p class="cq">{e(p["question"])}</p></div><dl class="cs">{states}</dl>{note}</section>'
        )
    body = f"""
{header("criteria")}
<main id="main" class="sys critpage">
  <section class="mast mast-sys" aria-labelledby="h-name">
    <div class="mast-in"><h1 id="h-name" class="sysname"><span class="lt">Criteria</span></h1></div>
  </section>
  <div class="wrap">
    <p class="cshared"><i class="sw unstated"></i><b>{e(STATE_WORD["not_stated"])}</b> {e(words(not_stated_rule()))}</p>
    <ul class="cidx" aria-label="Properties">{idx}</ul>
    {secs}
  </div>
</main>
{footer()}"""
    return page(
        "Criteria",
        "What Yes, Partly, No and Not stated mean for each of the six properties of one proof.",
        body,
        "system criteria",
        CRIT_PAGE.strip("/"),
        "home",
    )


def build_404():
    """Not found: the benchmarked systems, each with its glyph. The header, its logo and the
    footer already link every other page."""
    systems = "".join(
        f'<li><a href="{e(S.PAGE[sid])}">{pie_svg(glyph(sid)["states"], 28)}<span>{e(name_of(sid))}</span></a></li>'
        for sid in S.V["orders"]["benchmarked"]
    )
    body = f"""
{header(None)}
<main id="main" class="sys">
  <section class="mast mast-sys" aria-labelledby="h-name">
    <div class="mast-in"><h1 id="h-name" class="sysname"><span class="lt">Not found</span></h1></div>
  </section>
  <div class="wrap"><ul class="lost" aria-label="Systems">{systems}</ul></div>
</main>
{footer()}"""
    return page("Not found", "No page at this address.", body, "system notfound", "404", None)
