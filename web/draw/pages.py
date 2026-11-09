"""The other pages: one per benchmarked system (its glyph with each property beside its slice,
facts, figures and tamper tests), the reference page, the criteria page and the 404 page.
"""

from . import state as S
from .chrome import CRIT_PAGE, footer, header, page
from .claims import (
    card_fact,
    card_full,
    card_value,
    evidence_of,
    gap_block,
    how_we_read,
    property_controls_of,
    read_entries,
    run_ref,
)
from .hexagon import hex_svg, key_mini
from .overview import model_line, plate_prefix, shape_words
from .plates import (
    COLS,
    EXT,
    MORE,
    aria,
    configs_of,
    fig,
    glyph,
    has_figures,
    keep,
    name_of,
    path_html,
    plate,
    readable,
    record_html,
    row_id,
    runs_counts,
    source_html,
    source_label,
    upstream,
    with_rule,
    words,
)
from .words import (
    ACCEPTED_WHY,
    FAIL_KIND,
    FAIL_STEP,
    FAMILY_WORD,
    OUTCOME_SHORT,
    OUTCOME_VERB,
    OUTCOME_WORDS,
    PENDING,
    PENDING_TAMPER,
    REF_LEAD,
    STATE_CLS,
    STATE_ORDER,
    STATE_WORD,
    STATUS_WORD,
    amount,
    e,
    labels,
    shown,
    spread_line,
    why_words,
)

# ------------------------------------------------------------------ system page: the pie with its six properties around it


# Clockwise from twelve, slices 1 to 3 face right and 4 to 6 face left; each property sits on its slice's side.
SIDE = {1: "r", 2: "r", 3: "r", 4: "l", 5: "l", 6: "l"}


def rose_item(c, pre, drawn=True, ev="", src=""):
    """One property beside its slice: its name (a link to what its states mean), its question for
    screen readers, the state, and our short reason (left out when it only repeats Not stated).
    On a system page, after the reason, a small link to the property's entry in "How we read it"
    (`src`, its id), and, for an overridden cell, the one line that changes its state (`ev`,
    draw/claims.py); nothing else."""
    generic = (
        c["state"] == "not_stated" and c["reason"].startswith("Not stated") and not c["quotes"]
    )
    link = (f'<a class="psrc" href="#{e(src)}">source<span class="sr">: how we read '
            f"{e(c['name'])}</span></a>" if src else "")  # fmt: skip
    said = [x for x in ("" if generic else e(words(c["reason"])), link) if x]
    only = ' class="rr rsrc"' if said == [link] else ' class="rr"'  # the link alone, no reason
    reason = f"<p{only}>{' '.join(said)}</p>" if said else ""
    if not drawn:  # RFC-0016 OVR-8: the stated state in words, beside the notice, not drawn
        state = f'<p class="rs">{e("Stated: " + c["word"])}</p>'
    else:
        state = f'<p class="rs"><i class="sw {STATE_CLS[c["state"]]}"></i>{e(c["word"])}</p>'
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
        rose_item(c, pre, g["drawn"], ev.get(c["prop"], ""), src.get(c["prop"], ""))
        for c in g["cells"]
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


def more_table(cfg, caption):
    """The other figures, each with every label a plate holds (S2, S3): the spread, scope, grade,
    tier and the record in the release index; a missing one says why, and names its record when
    the runs recorded the metric."""
    more = ""
    for metric, label in MORE:
        f = cfg["figures"][metric]
        if f["value"] is not None:
            parts = [*([f"spread: {spread_line(f)}"] if f.get("stats") else []),
                     *(f"{k}: {v}" for k, v in labels(f, cfg))]  # fmt: skip
            lab = with_rule(readable(" · ".join(parts)))
            n, _ = amount(f["value"], f["unit"])
            # "GPU cost per 1,000 positions": the row names the basis, so the value drops its own
            val = fig(f"{n} USD" if f["unit"] == "USD/1k_token" else shown(f["value"], f["unit"]))
        else:
            # only why it is missing: the value cell says "No value", and a missing number has no grade
            lab = with_rule(why_words(f, cfg))
            val = '<span class="na">No value</span>'
        if f["recorded"]:
            lab += f'\u00a0· <span class="src">source: {source_html(f["source"])}</span>'
        more += f'<tr><th scope="row">{e(readable(label))}</th><td class="mv">{val}</td><td class="ml">{lab}</td></tr>'
    return (
        f'<table class="mtab"><caption class="sr">{e(caption)}</caption>'
        f'<thead><tr><th scope="col">Figure</th><th scope="col">Value</th><th scope="col">Labels</th></tr></thead><tbody>{more}</tbody></table>'
    )


def accepted_words(cfg):
    """Which control each stored `accepted` outcome is, and whether its own expected set holds
    acceptance: a system's weakened-prover control expects it, a tampered proof does not
    (RFC-0008). Listed from the records, never counted here."""
    return ", and ".join(ACCEPTED_WHY[(a["source"], a["passed"] is True)].format(id=a["control"])
                         for a in cfg["accepted"])  # fmt: skip


def tamper_words(cfg):
    """Each stored outcome count of the configuration's controls (RFC-0008), zero counts left
    out; no sum or difference of them (AGENTS.md rule 3). The accepted count names each
    accepted control, so a control that expects acceptance never reads as a tampered proof
    the checker took."""
    counts = cfg["controls"]["counts"]
    said = []
    for k, w in OUTCOME_WORDS:
        if counts.get(k):
            said.append(w.format(n=counts[k]) + (f" ({accepted_words(cfg)})" if k == "accepted"
                                                 else ""))  # fmt: skip
    return (
        ("Tampering tests on this setup, by outcome: " + "; ".join(said) + ".")
        if said
        else "No tampering test ran on this setup."
    )


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
            f' <a class="qs" href="{e(sc["source"])}">{e(source_label(sc["source"]))}{EXT}</a>'
            if sc["source"]
            else ""
        )
        out += f'<p class="ctl">{e(text)}{link}</p>'
    return out


def status_words(st):
    """A status fact in one form for every system: the state, then its date and source if stored."""
    out = STATUS_WORD[st["state"]]
    if st.get("last_push"):
        src = f" ({st['source']}, retrieved {st['retrieved']})" if st.get("source") else ""
        out += f" · last push {st['last_push']}{src}"
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
        f'<a href="https://github.com/{e(r)}/tree/{e(c)}">{path_html(r)}<span class="nw"> @{e(c[:8])}</span>{EXT}</a>'
        for r, c in repos
    )


def config_where(cfg):
    return " · ".join(
        [cfg["configuration"], cfg["workload"]["id"], cfg["workload"]["division"], cfg["profile"]]
    )


def left_out(cfg):
    """S7: every run of the configuration its figures leave out, each by its id with its record:
    a failed run with its failure kind, step, exit code and last line; a superseded run with its
    reason and the run that replaces it; an ineligible run with its reasons. Named in words."""
    runs = cfg["runs"]
    rows = []
    for f in runs["failed"]:
        parts = [
            FAIL_KIND[f["kind"]] + (f" {FAIL_STEP[f['step']]}" if f["step"] in FAIL_STEP else "")
        ]
        if f["exit_code"] is not None:
            parts.append(f"exit code {f['exit_code']}")
        if f["last_line"]:
            parts.append(f'last line: "{f["last_line"]}"')
        rows.append(("failed", f["run_id"], f["record"], e("; ".join(parts))))
    for x in runs["left_out"]:
        if x["replaced_by"]:
            why = "; ".join(r.split(": ", 1)[1] if ": " in r else r for r in x["reasons"])
            by = f"replaced by {run_ref(x['replaced_by'], x['replaced_by_record'])}"
            rows.append(("superseded", x["run_id"], x["record"], f"{e(why)}; {by}"))
        else:
            rows.append(("left out", x["run_id"], x["record"], e("; ".join(x["reason_words"]))))
    if not rows:
        return ""
    items = "".join(f'<div><dt>{e(k)}</dt><dd><span class="rid">{run_ref(rid, rec)}</span>'
                    f'<span class="rw">{why}</span></dd></div>' for k, rid, rec, why in rows)  # fmt: skip
    return f'<dl class="tlab runs" aria-label="Runs left out of these figures">{items}</dl>'


def runs_lead(cfg):
    """What the figures are over (S7), and how many runs they leave out, by kind."""
    runs = cfg["runs"]
    n = len(runs["completed"])
    said = [f"Runs of this setup: {n} completed"]
    out = []
    if runs["failed"]:
        out.append(f"{len(runs['failed'])} failed")
    sup = sum(1 for x in runs["left_out"] if x["replaced_by"])
    if sup:
        out.append(f"{sup} superseded")
    other = len(runs["left_out"]) - sup
    if other:
        out.append(f"{other} left out")
    if out:
        said.append(f"not counted: {', '.join(out)}")
    return "; ".join(said) + ". Each number below is over the completed runs."


def config_figures(cfg, name, one):
    """One configuration's figures: what they are over and the runs left out (S7), a plate per
    overview column, the other figures in a table. one: the system has one configuration, so
    the section heading already names the model and shape; otherwise a heading names the
    configuration first."""
    head = ""
    if not one:
        rid = row_id(cfg)
        head = (f'<div class="sec-h"><h3 id="h-{e(rid)}" class="sect sm">{keep(config_where(cfg))}</h3>'
                f'<p class="sec-l">{e(readable(S.MODEL_NAME[cfg["workload"]["model"]["digest"]] + " · " + shape_words(cfg)))}</p></div>')  # fmt: skip
    plates = "".join(plate(cfg, c, plate_prefix(cfg)) for c in COLS)
    body = (
        f'{head}<p class="lead">{e(runs_lead(cfg))}</p>{left_out(cfg)}'
        f'<div class="plates plates-sys">{plates}</div>'
        f"{more_table(cfg, f'More numbers for {name}, with spread, scope, grade, checked step and source')}"
    )
    return body if one else f'<div class="cfgfigs" id="{e(row_id(cfg))}">{body}</div>'


TRIAL_KEYS = (
    "seed_index",
    "outcome",
    "verdict",
    "raw_exit_code",
    "raw_last_line",
    "seconds",
    "mutation",
)  # the stored order of a trial's fields, as printed (schema controls/1)
SHOWN = {"id", "outcome", "expected", "side", "source", "twin", "trials", "note"}


def trial_html(t):
    """One stored trial in full: every field under its stored name, the mutation as its own
    keys and values or "none" when it holds none (RFC-0008 §Reporting: "in full")."""
    keys = [*(k for k in TRIAL_KEYS if k in t), *(k for k in t if k not in TRIAL_KEYS)]
    rows = []
    for k in keys:
        v = t[k]
        if k == "outcome":
            v = OUTCOME_SHORT[v]
        if k == "raw_last_line":
            shown_ = f"“{e(v)}”"
        elif isinstance(v, dict) and not v:
            shown_ = "none"
        else:
            shown_ = card_value(v)
        rows.append(f"<div><dt>{e(k)}</dt><dd>{shown_}</dd></div>")
    return f'<dl class="cn">{"".join(rows)}</dl>'


def unexpected_full(cfg):
    """RFC-0008 §Reporting: each outcome outside its control's expected set, printed in full
    from its stored record (every field, each trial with its mutation and raw last line), with
    the record it comes from."""
    out = ""
    for u in cfg["unexpected"]:
        rec = u["stored"] or {}
        kv = [
            ("control", e(u["control"])),
            ("run", run_ref(u["run_id"], None)),
            ("outcome", e(OUTCOME_SHORT[u["outcome"]])),
            ("expected", e(", ".join(OUTCOME_SHORT[x] for x in rec.get("expected") or []))),
            ("side", e(rec.get("side"))),
            ("source", e(rec.get("source"))),
        ]
        tw = rec.get("twin")
        kv.append(("honest twin", e(f"verdict {tw['verdict']}, exit code {tw['raw_exit_code']}")
                   if tw else "none"))  # fmt: skip
        kv += [(k, card_value(v)) for k, v in rec.items() if k not in SHOWN]
        kv += [("trial", trial_html(t)) for t in rec.get("trials") or []]
        kv.append(("note", e(rec["note"]) if rec.get("note") else "none"))
        kv.append(("record", record_html(u["record"]) if u["record"] else "not in this release"))
        rows = "".join(f"<div><dt>{e(k)}</dt><dd>{v}</dd></div>" for k, v in kv)
        out += (f'<dl class="tlab unexp" id="unexpected-{e(u["control"])}-{e(u["run_id"])}">'
                f"{rows}</dl>")  # fmt: skip
    return out


def config_tamper(cfg, drawn):
    """One configuration's controls: each stored outcome count, every outcome outside its
    expected set in full, then the system's own controls; under a pending disclosure only the
    RFC-0008 notice (RFC-0016 OVR-8)."""
    where = (
        f'<dl class="tlab"><div><dt>configuration</dt><dd>{keep(config_where(cfg))}</dd></div></dl>'
    )
    if not drawn:
        return f'<p class="tamper">{with_rule(PENDING_TAMPER)}</p>{where}'
    return (f'<p class="tamper">{e(tamper_words(cfg))}</p>{where}{unexpected_full(cfg)}'
            f"{control_tests(cfg)}")  # fmt: skip


def system_desc(sid):
    return f"{name_of(sid)}: six properties of one proof (draft criteria) and the benchmark's own figures with their labels."


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


def reply_section(sid):
    """§Right of reply: the system maintainers' reply, unedited, escaped at build."""
    reply = S.V["release"]["replies"].get(sid)
    if not reply:
        return ""
    return (f'<section class="blk reply" id="reply" aria-labelledby="h-reply">'
            f'<h2 id="h-reply" class="sect">Reply from the system maintainers</h2>'
            f'<div class="replyb">{reply}</div></section>')  # fmt: skip


def build_system(sid):
    name = name_of(sid)
    cfgs = configs_of(sid)
    cfg = cfgs[0]
    one = len(cfgs) == 1
    g = glyph(sid)
    row = S.V["facts"]["rows"][sid]
    models = list(dict.fromkeys(model_line(c) for c in cfgs))
    facts = [
        ("card", card_fact(cfg)),
        ("kind", keep(words(f"{FAMILY_WORD[S.CRIT['rows'][sid]['family']]}: {row['technique']}"))),
        ("model" if len(models) == 1 else "models", keep(" · ".join(models))),
        ("pinned", f'<span class="links">{pinned(cfg)}</span>'),
        ("licence", e(row["licence"]["name"])),
        ("status", keep(status_words(row["status"]))),
        ("adapter", f'<a href="{e(cfg["adapter_readme"])}">systems/{e(sid)}/README.md{EXT}</a>'),
    ]
    shape = (f'<p class="sec-l">{e(readable(S.MODEL_NAME[cfg["workload"]["model"]["digest"]] + " · " + shape_words(cfg)))}</p>'
             if one else "")  # fmt: skip
    notice = "" if g["drawn"] else f'<p class="lead notice">{with_rule(PENDING)}</p>'
    body = f"""
{header(sid)}
<main id="main" class="sys">
  <section class="mast mast-sys" aria-labelledby="h-name">
    <div class="mast-in"><h1 id="h-name" class="sysname"><span class="lt">{e(name)}</span></h1></div>
  </section>
  <div class="wrap">
    {notice}{claims_section(sid, cfgs, g, facts)}
    <section class="blk" id="figures" aria-labelledby="h-figs">
      <div class="sec-h"><h2 id="h-figs" class="sect">Figures</h2>{shape}</div>
      {"".join(config_figures(c, name, one) for c in cfgs)}
    </section>
    <section class="blk" id="tamper" aria-labelledby="h-tamper">
      <h2 id="h-tamper" class="sect">Tamper tests</h2>
      {"".join(config_tamper(c, g["drawn"]) for c in cfgs)}
    </section>
    {reply_section(sid)}
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


def build_reference():
    """One page for the reference systems: each one's six properties, then its one set of figures."""
    secs = ""
    for gid in S.V["orders"]["reference"]:
        g = glyph(gid)
        name = name_of(gid)
        cfgs = [c for c in S.CONFIGS if c["system"] == gid]
        models = list(dict.fromkeys(S.MODEL_NAME[c["workload"]["model"]["digest"]] for c in cfgs))
        facts = [
            ("kind", e(words(S.V["facts"]["rows"][gid]["kind_words"]))),
            ("model" if len(models) == 1 else "models", e(" · ".join(models))),
        ]
        cfg = cfgs[0]
        counts = "".join(f'<p class="lead">{with_rule(readable(runs_counts(c)))}</p>'
                         for c in cfgs if not has_figures(c))  # fmt: skip
        figs = (
            f'<div class="reffigs" id="{e(gid)}-figures"><h3 class="sect sm">Figures<span class="of"> · {e(name)}</span></h3>'
            f'{counts}<div class="plates plates-sys">{"".join(plate(cfg, c, f"{gid}-fig-") for c in COLS)}</div></div>'
        )
        secs += f'''
    <section class="refsys" id="{e(gid)}" aria-labelledby="h-{e(gid)}">
      <h2 id="h-{e(gid)}" class="refh">{e(name)}</h2>
      <div class="over">{rose(g, f"h-{gid}-props", name, level=3, pre=f"{gid}-")}{facts_dl(facts)}</div>
      {figs}
    </section>'''
    body = f"""
{header("reference")}
<main id="main" class="sys refpage">
  <section class="mast mast-sys" aria-labelledby="h-name">
    <div class="mast-in"><h1 id="h-name" class="sysname refname"><span class="lt">References</span></h1></div>
  </section>
  <div class="wrap">
    <p class="reflead">{e(REF_LEAD)}</p>
    {secs}
  </div>
</main>
{footer()}"""
    return page(
        "References",
        "The references: production serving and a rerun by a weights holder, their six properties and their figures.",
        body,
        "system reference",
        "reference",
        "home",
    )


# ------------------------------------------------------------------ the criteria and the 404


def build_criteria():
    """What each state means for each property, from the criteria file: the rules the glyphs are drawn by."""
    # a jump index of the six properties, shown on phones (words.css), names only
    idx = "".join(
        f'<li><a href="#{e(p["id"])}">{key_mini(i + 1, 22)}<span>{e(p["name"])}</span></a></li>'
        for i, p in enumerate(S.PROPS)
    )
    secs = ""
    for i, p in enumerate(S.PROPS):
        states = "".join(
            f'<div><dt><i class="sw {STATE_CLS[s]}"></i>{e(STATE_WORD[s])}</dt><dd>{e(words(p["rules"][s]))}</dd></div>'
            for s in STATE_ORDER
        )
        note = f'<p class="cnote">{e(words(p["not_here"]))}</p>' if p.get("not_here") else ""
        secs += (
            f'<section class="crit" id="{e(p["id"])}" aria-labelledby="h-{e(p["id"])}">'
            f'<div class="ch">{key_mini(i + 1)}<h2 id="h-{e(p["id"])}" class="sect">{e(p["name"])}</h2>'
            f'<p class="cq">{e(p["question"])}</p></div><dl class="cs">{states}</dl>{note}</section>'
        )
    body = f"""
{header("criteria")}
<main id="main" class="sys critpage">
  <section class="mast mast-sys" aria-labelledby="h-name">
    <div class="mast-in"><h1 id="h-name" class="sysname"><span class="lt">Criteria</span></h1></div>
  </section>
  <div class="wrap">
    <ul class="cidx" aria-label="Properties">{idx}</ul>
    {secs}
  </div>
</main>
{footer()}"""
    return page(
        "Criteria",
        "What Yes, Partly, No and Not stated mean for each of the six properties of one proof (draft criteria).",
        body,
        "system criteria",
        CRIT_PAGE.strip("/"),
        "home",
    )


def build_404():
    body = f"""
{header(None)}
<main id="main" class="sys">
  <section class="mast mast-sys" aria-labelledby="h-name">
    <div class="mast-in"><h1 id="h-name" class="sysname"><span class="lt">Not found</span></h1></div>
  </section>
</main>
{footer()}"""
    return page("Not found", "No page at this address.", body, "system notfound", "404", None)
