"""The system pages (RFC-0018 SI-3), the checks page and the 404.

A system page holds one row of the board: the glyph once, large, each petal's name in its own
triangle, with a ruled table of the petals (state, reason, the publisher's quotes, basis); then
the six checks as a ruled table (state, cause, evidence), the sessions, the cost parts and
fidelity beside the model's controls.
"""

import re

from . import state as S
from .chrome import CHECKS_PAGE, MANDATE_PAGE, footer, header, link, page, rung_of
from .hexagon import glyph_svg
from .overview import (
    NOT_TESTED,
    baseline_html,
    counted,
    fig_html,
    filled,
    href,
    kl_html,
    name_of,
    standing,
    states,
)
from .words import (
    BASIS_WORD,
    CAUSE_WORD,
    CHECK_EVIDENCE,
    CHECK_FAILED,
    CHECK_HELD,
    CHECK_NAME,
    FIGURE_NAME,
    FIGURE_RULE,
    MANDATE,
    MANDATE_BELIEF,
    MANDATE_WHAT,
    ORDER_RULE,
    PETAL_NAME,
    PETAL_RULE,
    PETAL_WORD,
    STATE_WORD,
    TERMS,
    e,
    kl_head,
    number,
    quoted,
    sig,
)

GLYPH = 200  # the system page's glyph, in the units its names are set in
GPU_S = "gpu_s/request"  # a session's values: GPU-seconds per reply (RFC-0018 CO-1, CO-3)


def band(title, sub=""):
    return (f'<section class="mast mast-sys" aria-labelledby="h-name"><div class="mast-in">'
            f'<h1 id="h-name" class="sysname">{e(title)}</h1>{sub}</div></section>')  # fmt: skip


def section(sid, title, body):
    return (f'<section class="blk" id="{sid}" aria-labelledby="h-{sid}">'
            f'<h2 class="sect sm" id="h-{sid}">{e(title)}</h2>{body}</section>')  # fmt: skip


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
    """A check's records, one link per directory: its run by date and ordinal with the file's
    name, or with the count of files where it holds several (a trace per proof makes many)."""
    dirs: dict[str, list[str]] = {}
    for p in paths:
        dirs.setdefault(p.rsplit("/", 1)[0], []).append(p)
    out = []
    for d, files in dirs.items():
        if len(files) == 1:
            label = f"{where(d)} / {files[0].rsplit('/', 1)[-1]}"
            out.append(f'<a class="ev" href="{e(link(files[0]))}" title="{e(files[0])}">'
                       f"{e(label)}</a>")  # fmt: skip
        else:
            out.append(f'<a class="ev" href="{e(S.REPO_URL)}/tree/{e(S.LINK_REF)}/{e(d)}" '
                       f'title="{e(d)}">{e(where(d))} ({len(files):,} files)</a>')  # fmt: skip
    return "".join(out)


def swatch(state):
    return f'<i class="sw {state}" aria-hidden="true"></i>'


def glyph_html(row):
    """The glyph once, large, each petal's name in its triangle (never its state: the ink says
    it), then one ruled row per petal: name, state, reason with the publisher's quotes linked,
    and what it rests on (SI-3)."""
    names = [PETAL_NAME[p["id"]] for p in row["glyph"]]
    glyph = glyph_svg(GLYPH, states(row), names=names, cls="pie-svg big")
    trs = []
    for p in row["glyph"]:
        quotes = "".join(f'<a class="qt" href="{e(q["url"])}">\u201c{quoted(q["text"])}\u201d</a>'
                         for q in p["quotes"])  # fmt: skip
        trs.append(
            f'<tr class="pt {p["state"]}"><th scope="row">'
            f'<a href="{CHECKS_PAGE}#{p["id"]}">{e(PETAL_NAME[p["id"]])}</a></th>'
            f'<td class="cst">{swatch(p["state"])}{e(PETAL_WORD[p["state"]])}</td>'
            f'<td><span class="rs">{e(p["reason"])}</span>{quotes}</td>'
            f'<td class="bs">{e(BASIS_WORD[p["basis"]])}</td></tr>'
        )
    table = ('<table class="rt ckt"><thead><tr><th scope="col">Petal</th><th scope="col">State'
             '</th><th scope="col">Reason</th><th scope="col">From</th></tr></thead>'
             f'<tbody>{"".join(trs)}</tbody></table>')  # fmt: skip
    return f'<div class="checks"><div class="gbig">{glyph}</div>{table}</div>'


def checks_html(row):
    """The six checks, the entry gate: one ruled row per check: name, state, cause, evidence."""
    trs = []
    for c in row["checks"]:
        cause = ""
        if c["cause"]:
            cause = f'<span class="cw" title="{e(CAUSE_WORD[c["cause"]])}">{e(c["cause"])}</span>'
        if c.get("note"):
            cause += f'<span class="cn">{quoted(c["note"])}</span>'
        trs.append(
            f'<tr class="ck {c["state"]}"><th scope="row">'
            f'<a href="{CHECKS_PAGE}#{c["id"]}">{e(CHECK_NAME[c["id"]])}</a></th>'
            f'<td class="cst">{swatch(c["state"])}{e(STATE_WORD[c["state"]])}</td>'
            f"<td>{cause}</td><td>{evidence_html(c['evidence'])}</td></tr>"
        )
    return ('<table class="rt ckt"><thead><tr><th scope="col">Check</th><th scope="col">State'
            '</th><th scope="col">Cause</th><th scope="col">Evidence</th></tr></thead>'
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

    def gen_td(k, s):  # CO-3: the reply-generation phase, already inside m
        if not gen:
            return ""
        g = s.get("generation_gpu_seconds_per_reply")
        return f"<td>{plain(g, GPU_S, f'{rec}/sessions/{k}/generation_gpu_seconds_per_reply')}</td>"

    trs = "".join(
        f"<tr><td>{s['slot']}</td><td>{run_link(row, s['run_id'])}</td>"
        f"<td>{plain(s['m'], GPU_S, f'{rec}/sessions/{k}/m')}</td>{gen_td(k, s)}"
        f"<td>{plain(s['session'], GPU_S, f'{rec}/sessions/{k}/session')}</td>"
        f"<td>{'yes' if s['steady'] else e(s['cause'] or 'no')}</td>"
        f"<td>{len(s['groups']):,}</td></tr>"
        for k, s in enumerate(row["sessions"])
    )
    gen_th = '<th scope="col">Of which generation</th>' if gen else ""
    out = ('<table class="rt"><thead><tr><th scope="col">Slot</th><th scope="col">Run</th>'
           f'<th scope="col">Steady, m</th>{gen_th}<th scope="col">Session</th>'
           '<th scope="col">Steady state</th><th scope="col">Release groups</th></tr></thead>'
           f"<tbody>{trs}</tbody></table>") if row["sessions"] else (
           '<p class="none">No counted session.</p>')  # fmt: skip
    if row["incomplete"]:
        trs = "".join(
            f"<tr><td>{s['slot'] if s['slot'] is not None else ''}</td>"
            f"<td>{run_link(row, s['run_id'])}</td>"
            f"<td>{e(s['exit_code']) if s['exit_code'] is not None else 'none'}</td>"
            f"<td>{e(s['step'] or '')}</td><td>{e(s['cause'])}</td>"
            f"<td><code>{e(s['last_line'] or '')}</code></td></tr>"
            for s in row["incomplete"]
        )
        out += ('<h3 class="sub-h">Incomplete sessions</h3><table class="rt"><thead><tr>'
                '<th scope="col">Slot</th><th scope="col">Run</th><th scope="col">Exit code</th>'
                '<th scope="col">Step</th><th scope="col">Cause</th><th scope="col">Last line</th>'
                f"</tr></thead><tbody>{trs}</tbody></table>")  # fmt: skip
    return out


def split_parts(figs, n):
    """CO-7: the proving and generation parts of the multiple and of m, where the system
    generates in a phase of its own; none otherwise."""
    split = [figs.get(k) for k in ("proving_multiple", "generation_multiple")]
    if any(f is None or f["value"] is None for f in split):
        return []
    return [
        ("Of which proving, multiple of serving", fig_html(figs["proving_multiple"], n)),
        ("Of which generation, multiple of serving", fig_html(figs["generation_multiple"], n)),
        ("Proving GPU time per further reply",
         fig_html(figs["steady_proving_gpu_seconds_per_reply"], n)),
        ("Generation GPU time per further reply",
         fig_html(figs["steady_generation_gpu_seconds_per_reply"], n)),
    ]  # fmt: skip


def cost_html(row):
    """The cost parts (CO-1 to CO-5), each figure as the board stores it."""
    rung = rung_of(row)
    figs, b, n = row["figures"], rung["baseline"] or {}, counted(row)
    cold = f"cold sessions of {rung['requests_per_session']:,} replies"
    price = S.V["price"]
    parts = [
        ("Multiple of serving", fig_html(figs["multiple"], n)),
        *split_parts(figs, n),
        ("Steady GPU time per further reply", fig_html(figs["steady_gpu_seconds_per_reply"], n)),
        ("Serving GPU time per reply, full load", fig_html(b.get("gpu_seconds_per_reply"))),
        ("Session GPU time per reply", fig_html(figs["session_gpu_seconds_per_reply"], n)),
        (f"Multiple of serving, {cold}", fig_html(figs["session_multiple"], n)),
        ("Steady cost per reply", fig_html(figs["steady_usd_per_reply"], n)),
        ("Session cost per reply", fig_html(figs["session_usd_per_reply"], n)),
        ("Serving cost per reply", fig_html(b.get("usd_per_reply"))),
        ("Price of one H200 GPU-hour", fig_html(price and price["usd_per_gpu_hour"],
                                                sub=f"{price['basis']}, {price['date']}"
                                                if price else None)),
        ("Check time per reply", fig_html(figs["verify_seconds_per_reply"], n)),
        ("Proof size per reply", fig_html(figs["proof_bytes_per_reply"], n)),
    ]  # fmt: skip
    rows = "".join(f"<div><dt>{e(k)}</dt><dd>{v}</dd></div>" for k, v in parts)
    return f'{baseline_html(rung)}<dl class="parts">{rows}</dl>'


def fidelity_html(row):
    """FI-5, FI-6, FI-7: the row's mean matched prefix and KL beside the model's controls, the bar
    marked."""
    fid = rung_of(row)["fidelity"]
    mine = row["fidelity"]
    out = []
    if mine is not None:
        out.append(
            f'<tr class="me"><th scope="row">{e(name_of(row))}</th><td>this system</td>'
            f'<td>{plain(mine["mean_prefix"], "tokens", row["record"] + "/fidelity/mean_prefix")}<span class="sub">n\u00a0=\u00a0{mine["n"]:,}'
            f"</span></td><td>{kl_html(row)}</td></tr>"
        )
    bar = (fid or {}).get("bar")

    def at(i):
        return f"{fid['record']}/controls/{i}/mean_prefix"

    for i, c in enumerate((fid or {}).get("controls") or []):
        is_bar = bar is not None and bar["control"] == c["id"]
        kind = c["kind"] + (", the bar" if is_bar else "")
        if c["status"] == "failed":
            kind += ", failed to run"
        kl = fig_html(c["kl"]) if c["kl"] is not None and c["kl"]["value"] is not None else (
            '<span class="na">not measured</span>')  # fmt: skip
        out.append(
            f'<tr class="{"bar" if is_bar else ""}"><th scope="row">{e(c["id"])}</th>'
            f"<td>{e(kind)}</td><td>{plain(c['mean_prefix'], 'tokens', at(i))}</td>"
            f"<td>{kl}</td></tr>"
        )
    if not out:
        return '<p class="none">Not run yet.</p>'
    lead = ""
    if mine is not None and mine["p_above_bar"] is not None:
        lead = (f'<p class="pl">p above the bar {e(sig(mine["p_above_bar"], 2))}, p below '
                f'{e(sig(mine["p_below_bar"], 2))}</p>')  # fmt: skip
    if fid is not None and bar is None:
        lead += f'<p class="pl">No bar: {e(fid["cause"] or "no damaged copy qualified")}</p>'
    return (f'{lead}<table class="rt fid"><thead><tr><th scope="col">Replies</th>'
            '<th scope="col">Kind</th><th scope="col">Mean matched prefix</th>'
            f'<th scope="col">{e(kl_head(rung_of(row)["reference_dtype"]))}</th></tr></thead>'
            f'<tbody>{"".join(out)}</tbody></table>')  # fmt: skip


def system_page(row):
    rung = rung_of(row)
    sysd = S.V["systems"][row["system"]]
    pos = (f", position {row['position']} of {rung['systems_run']}"
           if row["position"] is not None else "")  # fmt: skip
    bits = [f"{standing(row)}{pos}", f"on {rung['model']}"]
    if row["commit"]:
        bits.append(f"pinned at {row['commit'][:8]}")
    if sysd["licence"]:
        bits.append(sysd["licence"]["name"])
    sub = f'<p class="bsub">{e(" · ".join(bits))}</p>'
    body = f"""
{header(None)}
<main id="main" class="sys">
  {band(name_of(row), sub)}
  <div class="wrap">
    {glyph_html(row)}
    {section("checks", "Checks", checks_html(row))}
    {section("sessions", "Sessions", sessions_html(row))}
    {section("cost", "Cost", cost_html(row))}
    {section("fidelity", "Fidelity", fidelity_html(row))}
  </div>
</main>
{footer()}"""
    desc = f"{name_of(row)} on {rung['model']}: its glyph, six checks, cost against serving."
    return page(name_of(row), desc, body, "system", row["page"], row["page"])


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


def build_checks():
    """The terms, the five petals (RFC-0018 §The glyph), the six checks as the entry gate (§The
    six checks) with what is not tested, the figures (§Cost, FI-7) and the order rule."""
    names = [PETAL_NAME[p] for p in S.V["petals"]]
    glyph = glyph_svg(GLYPH, ["key"] * len(names), names=names, cls="pie-svg big")
    petals = "".join(
        f'<section class="chk" id="{p}" aria-labelledby="h-{p}"><h2 class="cn2" id="h-{p}">'
        f"{e(PETAL_NAME[p])}</h2><dl class=\"cs\">"
        + "".join(f"<div><dt>{swatch(k)}{k}</dt><dd>{e(rule)}</dd></div>"
                  for k, rule in zip(("green", "amber", "red"), PETAL_RULE[p], strict=True))
        + "</dl></section>"
        for p in S.V["petals"]
    )  # fmt: skip
    checks = "".join(
        f'<section class="chk" id="{c}" aria-labelledby="h-{c}"><h3 class="cn2" id="h-{c}">'
        f"{e(CHECK_NAME[c])}</h3>"
        + rules((("held", CHECK_HELD[c]), ("failed", CHECK_FAILED[c]),
                 ("evidence", CHECK_EVIDENCE[c])))
        + "</section>"
        for c in S.V["checks"]
    )  # fmt: skip
    figures = "".join(
        f'<section class="chk" id="{f}" aria-labelledby="h-{f}"><h3 class="cn2" id="h-{f}">'
        f"{e(FIGURE_NAME[f])}</h3>{rules(FIGURE_RULE[f])}</section>"
        for f in FIGURE_RULE
    )
    gate = ("A system passes on a model when it holds all six checks there. A failed check "
            "turns its petals red; a held check never turns a petal green.")  # fmt: skip
    hollow = ("A hollow petal is not decided yet: a measured petal with no result, its cause "
              "beside it. A petal read from the publisher's documents is red where they are "
              "silent.")  # fmt: skip
    causes = "".join(f"<div><dt>{e(k)}</dt><dd>{e(v)}</dd></div>" for k, v in CAUSE_WORD.items())
    passed = (f'<p class="rd" id="passed">{e(gate)}</p>'
              f'<p class="rd" id="not-tested">{e(NOT_TESTED)}</p>')  # fmt: skip
    body = f"""
{header("checks")}
<main id="main" class="sys">
  {band("Checks")}
  <div class="wrap">
    {section("terms", "Terms", rules(TERMS))}
    <div class="cwrap"><div class="gbig">{glyph}</div><div class="clist">{petals}
      <p class="rd hl">{e(hollow)}</p></div></div>
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
    do not do, who runs it and how to check us. Each line has a plain label that links to the
    rule binding it (the rule's name is the link's title)."""

    def rule(label, name, path):
        if not path:
            return e(label)
        return f'<a href="{e(link(path))}" title="{e(path)}, {e(name)}">{e(label)}</a>'

    blocks = "".join(
        section(title.lower().replace(" ", "-"), title, '<dl class="cs">' + "".join(
            f"<div><dt>{rule(label, name, path)}</dt><dd>{e(words)}</dd></div>"
            for label, name, path, words in lines) + "</dl>")
        for title, lines in MANDATE
    )  # fmt: skip
    body = f"""
{header(None)}
<main id="main" class="sys">
  <section class="mast mast-sys" aria-labelledby="h-name"><div class="mast-in">
    <h1 id="h-name" class="sysname creed">{e(MANDATE_BELIEF)}</h1></div></section>
  <div class="wrap">
    <p class="rd lead">{e(MANDATE_WHAT)}</p>
    {blocks}
  </div>
</main>
{footer()}"""
    return page("Mandate", MANDATE_WHAT, body, "system mandatepage", MANDATE_PAGE.strip("/"),
                "home")  # fmt: skip


def build_404():
    """Not found: the system pages; the header and footer link every other page."""
    systems = "".join(f'<li><a href="{e(href(r))}">{e(name_of(r))}</a></li>' for r in S.ROWS)
    listed = f'<ul class="lost" aria-label="Systems">{systems}</ul>' if systems else ""
    body = f"""
{header(None)}
<main id="main" class="sys">
  {band("Not found")}
  <div class="wrap">{listed}</div>
</main>
{footer()}"""
    return page("Not found", "No page at this address.", body, "system notfound", "404", None)
