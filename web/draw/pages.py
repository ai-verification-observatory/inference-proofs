"""The system pages (RFC-0018 SI-3), the checks page and the 404.

A system page holds one row of the board: the glyph once, large, its arms the heads of a ruled
table of the petals (state, reason, the publisher's quotes, basis); then
the six checks as a ruled table (state, cause, evidence), the sessions, the cost parts and
fidelity beside the model's controls.
"""

import re

from . import state as S
from .chrome import (
    CHECKS_PAGE,
    MANDATE_PAGE,
    footer,
    header,
    learn_page,
    link,
    page,
    pnav,
    rung_of,
)
from .hexagon import glyph_svg
from .overview import (
    NOT_TESTED,
    counted,
    fig_html,
    filled,
    has,
    href,
    kl_html,
    lead_fig,
    name_of,
    nobreak,
    position_html,
    serving_words,
    standing_html,
    states,
)
from .plots import fid_svg, hbar
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
    PETAL_CHECKS,
    PETAL_NAME,
    PETAL_RULE,
    PETAL_WORD,
    STATE_WORD,
    TERMS,
    e,
    kl_head,
    number,
    params,
    quoted,
    sig,
)

GLYPH = 6  # the checks page's key glyph, px per unit (318 by 174 px)
GPU_S = "gpu_s/request"  # a session's values: GPU-seconds per reply (RFC-0018 CO-1, CO-3)


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


def chip(state, word):
    """A state as a chip: ground ink on its state's ink, an outline when undecided or hollow."""
    return f'<span class="schip {state}">{e(word)}</span>'


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


def glyph_html(row):
    """The glyph once, large, as the heads of the petals' table: each arm is its petal's name on
    the ink of its state (never its state word: the ink says it, and the chip beside it), on one
    stem, then the state, the reason with the publisher's quotes linked, and what it rests on
    (SI-3). An arm, its row and the checks its red names light together."""
    trs = []
    for i, p in enumerate(row["glyph"]):
        quotes = "".join(f'<a class="qt" href="{e(q["url"])}">\u201c{quoted(q["text"])}\u201d</a>'
                         for q in p["quotes"])  # fmt: skip
        trs.append(
            f'<tr class="pt {p["state"]}"><th scope="row">'
            f'<a class="sl s{i + 1} {p["state"]}" href="{CHECKS_PAGE}#{p["id"]}" data-k="p{i + 1}">'
            f"<span>{e(PETAL_NAME[p['id']])}</span></a></th>"
            f'<td class="cst">{chip(p["state"], PETAL_WORD[p["state"]])}</td>'
            f'<td><span class="rs">{e(p["reason"])}</span>{quotes}</td>'
            f'<td class="bs">{e(BASIS_WORD[p["basis"]])}</td></tr>'
        )
    return ('<div class="checks"><table class="rt ckt gbig"><thead><tr><th scope="col">Petal</th>'
            '<th scope="col">State</th><th scope="col">Reason</th><th scope="col">From</th></tr>'
            f'</thead><tbody>{"".join(trs)}</tbody></table></div>')  # fmt: skip


def checks_html(row):
    """The six checks, the entry gate: one ruled row per check: name, state, cause (a column
    only where a check has one), evidence. A check names the petals its failure turns red."""
    caused = any(c["cause"] or c.get("note") for c in row["checks"])
    trs = []
    for c in row["checks"]:
        cause = ""
        if c["cause"]:
            cause = (f'<a class="cw df" href="{CHECKS_PAGE}#undecided" '
                     f'title="{e(CAUSE_WORD[c["cause"]])}">{e(c["cause"])}</a>')  # fmt: skip
        if c.get("note"):
            cause += f'<span class="cn">{quoted(c["note"])}</span>'
        to = petals_of(c["id"])
        to = f' data-to="{to}"' if to else ""
        trs.append(
            f'<tr class="ck {c["state"]}" id="ck-{c["id"]}"><th scope="row">'
            f'<a href="{CHECKS_PAGE}#{c["id"]}"{to}>{e(CHECK_NAME[c["id"]])}</a></th>'
            f'<td class="cst">{chip(c["state"], STATE_WORD[c["state"]])}</td>'
            + (f"<td>{cause}</td>" if caused else "")
            + f"<td>{evidence_html(c['evidence'])}</td></tr>"
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
        g = s.get("generation_gpu_seconds_per_reply")  # CO-3: the generation phase, inside m
        return [
            str(s["slot"]),
            run_link(row, s["run_id"]),
            plain(s["m"], GPU_S, f"{at}/m"),
            *([plain(g, GPU_S, f"{at}/generation_gpu_seconds_per_reply")] if gen else []),
            plain(s["session"], GPU_S, f"{at}/session"),
            "yes" if s["steady"] else e(s["cause"] or "no"),
            f"{len(s['groups']):,}",
        ]

    heads = ["Slot", "Run", "Steady, m", *(["Of which generation"] if gen else []), "Session",
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


def cost_bars(row):
    """CO-1 to CO-3 drawn: serving, the steady m (its proving and generation parts where the
    system generates in a phase of its own) and the whole session, each in GPU time per reply on
    one scale, this row's own (one model). Each line: its name, its bar, its labelled figure."""
    figs, n = row["figures"], counted(row)
    b = (rung_of(row)["baseline"] or {}).get("gpu_seconds_per_reply")
    m, s = figs["steady_gpu_seconds_per_reply"], figs["session_gpu_seconds_per_reply"]
    p, g = (figs.get(k) for k in ("steady_proving_gpu_seconds_per_reply",
                                  "steady_generation_gpu_seconds_per_reply"))  # fmt: skip
    present = [f["value"] for f in (b, m, s) if has(f)]
    if not present:
        return ""
    top = max(present)
    lines = []

    def line(cls, name, f, segs, fig, parts=""):
        bar = hbar(segs, top, h=14, cls="hb") if has(f) else '<span class="hbn"></span>'
        lines.append(f'<div class="cl {cls}"><span class="cln">{e(name)}</span>{bar}'
                     f'<span class="clf">{fig}</span>{parts}</div>')  # fmt: skip

    line("srv", "Serving GPU time per reply", b,
         [(b["value"], "bs")] if has(b) else [], fig_html(b))  # fmt: skip
    if has(m) and has(p) and has(g):
        parts = "".join(f'<span class="cpt {c}"><span class="cpl">{w}</span>{fig_html(f, n)}</span>'
                        for c, w, f in (("pp", "of which proving", p),
                                        ("pg", "of which generation", g)))  # fmt: skip
        line("std", "Steady GPU time per further reply", m,
             [(p["value"], "bp"), (g["value"], "bg")], fig_html(m, n),
             f'<span class="cps">{parts}</span>')  # fmt: skip
    else:
        line("std", "Steady GPU time per further reply", m,
             [(m["value"], "bs")] if has(m) else [], fig_html(m, n))  # fmt: skip
    line(
        "ses",
        "Session GPU time per reply",
        s,
        [(s["value"], "bc")] if has(s) else [],
        fig_html(s, n),
    )
    return f'<div class="cbars">{"".join(lines)}</div>'


def cost_html(row):
    """The cost parts (CO-1 to CO-5), each figure as the board stores it: the serving baseline,
    the GPU times drawn on one scale (`cost_bars`), then a sheet of the other figures, the row's
    one figure first and larger (labelled as the band labels it)."""
    rung = rung_of(row)
    figs, b, n = row["figures"], rung["baseline"] or {}, counted(row)
    cold = f"cold sessions of {rung['requests_per_session']:,} replies"
    price = S.V["price"]
    label, lead = lead_fig(row)
    steady = (FIGURE_NAME["multiple"], fig_html(figs["multiple"], n))
    other = steady if label != FIGURE_NAME["multiple"] else (
        f"{FIGURE_NAME['multiple']}, {cold}", fig_html(figs["session_multiple"], n))  # fmt: skip
    split = []
    if has(figs.get("proving_multiple")) and has(figs.get("generation_multiple")):
        split = [("Of which proving, multiple of serving", fig_html(figs["proving_multiple"], n)),
                 ("Of which generation, multiple of serving",
                  fig_html(figs["generation_multiple"], n))]  # fmt: skip
    parts = [
        (label, lead),
        *split,
        other,
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
    base = rung["baseline"]
    serving = (f'<p class="rb"><span class="k">Serving</span> {e(serving_words(base))}</p>'
               if base and has(base["gpu_seconds_per_reply"]) else "")  # fmt: skip
    return f'{serving}{cost_bars(row)}<dl class="parts">{rows}</dl>'


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
    heads = ("Replies", "Kind", "Mean matched prefix", kl_h)

    def tds(kind, track, prefix, kl):
        return (f'<td data-l="Kind">{kind}</td>'
                f'<td class="trk" aria-hidden="true">{fid_svg(track[0], edge, whole, track[1])}</td>'
                f'<td data-l="{e(heads[2])}">{prefix}</td><td data-l="{e(kl_h)}">{kl}</td>')  # fmt: skip

    out = []
    if mine is not None:
        prefix = plain(mine["mean_prefix"], "tokens", row["record"] + "/fidelity/mean_prefix")
        sub = f"n\u00a0=\u00a0{mine['n']:,}"
        if mine["p_above_bar"] is not None:
            sub += (f" · p above the bar {sig(mine['p_above_bar'], 2)}, p below "
                    f"{sig(mine['p_below_bar'], 2)}")  # fmt: skip
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
            f'<tr class="{"bar" if is_bar else ""}"><th scope="row">{e(c["id"])}</th>'
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
    ths = (f'<th scope="col">{e(heads[0])}</th><th scope="col">{e(heads[1])}</th>'
           f'<th scope="col" class="trk" aria-hidden="true"></th>'
           + "".join(f'<th scope="col">{e(h)}</th>' for h in heads[2:]))  # fmt: skip
    return (f'{lead}<table class="rt stk fid"><thead><tr>{ths}</tr></thead>'
            f'<tbody>{"".join(out)}</tbody></table>')  # fmt: skip


NAME_SIZES = (6, 12, 20)  # a system's name on its band: one size per length up to these


def system_page(row):
    """A system on a model (SI-3): the band (its name, sized by its length, never more than two
    lines; its one figure on the right, labelled for what it is; the facts under them), then the
    glyph and its petals, the checks, the sessions, the cost and fidelity."""
    rung = rung_of(row)
    sysd = S.V["systems"][row["system"]]
    name = name_of(row)
    facts = [("Standing", standing_html(row, "")),
             ("Model", f'<a href="/#{e(rung["id"])}">{nobreak(rung["model"])}</a>')]  # fmt: skip
    if row["position"] is not None:
        facts.append(("Position", position_html(row, rung)))
    if row["commit"]:
        facts.append(("Pinned at", f"<code>{e(row['commit'][:8])}</code>"))
    if sysd["licence"]:
        facts.append(("Licence", nobreak(sysd["licence"]["name"])))
    size = next((i + 1 for i, k in enumerate(NAME_SIZES) if len(name) <= k), len(NAME_SIZES) + 1)
    label, lead = lead_fig(row)
    unranked = "" if row["position"] is not None else " unr"
    band_ = (
        f'<section class="mast mast-sys sysb" aria-labelledby="h-name"><div class="mast-in">'
        f'<div class="sb"><h1 id="h-name" class="sysname nm{size}">{e(name)}</h1>'
        f'<p class="sbm{unranked}"><span class="sbl">{e(label)}</span>{lead}</p></div>'
        '<dl class="facts">'
        + "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in facts)
        + "</dl></div></section>"
    )
    parts = (("glyph", "Glyph"), ("checks", "Checks"), ("sessions", "Sessions"), ("cost", "Cost"),
             ("fidelity", "Fidelity"))  # fmt: skip
    body = f"""
{header("system")}
<main id="main" class="sys">
  {band_}
  {pnav(name, parts)}
  <div class="wrap">
    {section("glyph", "Glyph", glyph_html(row))}
    {section("checks", "Checks", checks_html(row))}
    {section("sessions", "Sessions", sessions_html(row))}
    {section("cost", "Cost", cost_html(row))}
    {section("fidelity", "Fidelity", fidelity_html(row))}
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


def explained(lead, slug, cls="rd lead"):
    """One line that leads to the Learn page explaining this one; nothing without that page."""
    found = learn_page(slug)
    if found is None:
        return ""
    return f'<p class="{cls}">{e(lead)} <a href="/{e(slug)}">{e(found["title"])}</a>.</p>'


def title_band(title, sub="", cls="ttl"):
    """The band of a page that is not a system's (the checks, the mandate, the 404): its title
    at the home title's size, and a line under it."""
    return (f'<div class="mast mast-t"><div class="mast-in"><h1 id="h-name" class="{cls}">'
            f"{e(title)}</h1>{sub}</div></div>")  # fmt: skip


def build_checks():
    """The five petals (RFC-0018 §The glyph) as the key beside their rules, the six checks as the
    entry gate (§The six checks) with what is not tested, the undecided causes, the figures (§Cost,
    FI-7), the order rule, then the terms. The page opens on the glyph, as a system page does."""
    ids = list(S.V["petals"])
    names = [PETAL_NAME[p] for p in ids]
    glyph = glyph_svg(GLYPH, ["key"] * len(names), names=names, cls="pie-svg big",
                      hrefs=[f"#{p}" for p in ids])  # fmt: skip
    petals = "".join(
        f'<div class="chk" id="{p}"><h3 class="cn2">{e(PETAL_NAME[p])}</h3><dl class="cs">'
        + "".join(f"<div><dt>{chip(k, k)}</dt><dd>{e(rule)}</dd></div>"
                  for k, rule in zip(("green", "amber", "red"), PETAL_RULE[p], strict=True))
        + "</dl></div>"
        for p in ids
    )  # fmt: skip
    checks = "".join(
        f'<div class="chk" id="{c}"><h3 class="cn2">{e(CHECK_NAME[c])}</h3>'
        + rules((("held", CHECK_HELD[c]), ("failed", CHECK_FAILED[c]),
                 ("evidence", CHECK_EVIDENCE[c])))
        + "</div>"
        for c in S.V["checks"]
    )  # fmt: skip
    figures = "".join(
        f'<div class="chk" id="{f}"><h3 class="cn2">{e(FIGURE_NAME[f])}</h3>'
        f"{rules(FIGURE_RULE[f])}</div>"
        for f in FIGURE_RULE
    )
    gate = ("A system passes on a model when it holds all six checks there. A failed check "
            "turns its petals red; a held check never turns a petal green.")  # fmt: skip
    hollow = ("A hollow petal is not decided yet: a measured petal with no result, its cause "
              "beside it. A petal read from the publisher's documents is red where they are "
              "silent.")  # fmt: skip
    causes = "".join(f'<div id="cause-{e(k.replace(" ", "-"))}"><dt>{e(k)}</dt><dd>{e(v)}</dd></div>'
                     for k, v in CAUSE_WORD.items())  # fmt: skip
    passed = (f'<p class="rd" id="passed">{e(gate)}</p>'
              f'<p class="rd" id="not-tested">{e(NOT_TESTED)}</p>')  # fmt: skip
    parts = (("glyph", "Glyph"), ("checks", "The six checks"), ("undecided", "Undecided"),
             ("figures", "Figures"), ("order", "Order"), ("terms", "Terms"))  # fmt: skip
    key = (f'<div class="cwrap"><div class="gbig">{glyph}</div><div class="clist">{petals}'
           f'<p class="rd hl">{e(hollow)}</p></div></div>')  # fmt: skip
    lead = explained("The reason for each rule on this page:", "method", cls="tsub")
    body = f"""
{header("checks")}
<main id="main" class="sys">
  {title_band("Checks", lead)}
  {pnav("Checks", parts)}
  <div class="wrap">
    {section("glyph", "Glyph", key)}
    {section("checks", "The six checks", f'{passed}<div class="clist">{checks}</div>')}
    {section("undecided", "Undecided", f'<dl class="cs">{causes}</dl>')}
    {section("figures", "Figures", f'<div class="clist">{figures}</div>')}
    {section("order", "Order", rules(ORDER_RULE, ids=("unranked",)))}
    {section("terms", "Terms", rules(TERMS))}
  </div>
</main>
{footer()}"""
    return page("Checks", "The five petals of the glyph, the six checks, the figures, the order "
                "rule.", body, "system checkspage", CHECKS_PAGE.strip("/"), "home")  # fmt: skip


def build_mandate():
    """The mandate: the belief as the headline, what the site is for, then what we do, what we
    do not do, who runs it and how to check us. A line bound by a rule names it under its words,
    linked to the file that holds it."""

    def rule(name, path):
        if not path:
            return ""
        return (f'<a class="qsrc" href="{e(link(path))}">'
                f"{e(path.rsplit('/', 1)[-1])} · {e(name)}</a>")  # fmt: skip

    blocks = "".join(
        section(title.lower().replace(" ", "-"), title, '<dl class="cs">' + "".join(
            f"<div><dt>{e(label)}</dt><dd>{e(words)}{rule(name, path)}</dd></div>"
            for label, name, path, words in lines) + "</dl>")
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
    {explained("Why a claim about an AI system needs evidence:", "why-verify", cls="rd")}
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
