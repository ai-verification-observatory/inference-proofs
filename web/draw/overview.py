"""The overview page (index.html): one sortable table per model and workload (S6), the
references and the systems not benchmarked yet, and the helpers the other pages share with it
(model sizes, shapes, pins).
"""

import json
import re

from . import state as S
from .chrome import REF_PAGE, footer, header, masthead, page
from .hexagon import pie_svg
from .plates import (
    COLS,
    HEAD,
    METRIC,
    SORT_WORDS,
    aria,
    configs_of,
    first_config,
    glyph,
    has_figures,
    keep,
    name_of,
    readable,
    row_id,
    runs_counts,
    sentence_case,
    states_said,
    upstream,
    value_link,
    with_rule,
    words,
)
from .words import FAMILY_WORD, NATIVE_HEADER, STATUS_WORD, e, gpu_words, slug

# ------------------------------------------------------------------ home rows


def size_words(n):
    """A parameter count as the site prints it: 400000000000 is 400B, 8030261248 8.03B."""
    return f"{n / 1e9:.3g}B"


def pin_link(cfg):
    up = upstream(cfg)
    href = f"https://github.com/{up['repo']}/tree/{up['commit']}"
    return f'<a class="pin" href="{e(href)}" title="Pinned upstream commit {e(up["commit"])}">@{e(up["commit"][:8])}</a>'


def kind_words(rid):
    """A reference's role, as its facts word it, without the name it repeats."""
    kt = words(S.V["facts"]["rows"][rid]["kind_words"])
    name = name_of(rid)
    return sentence_case(kt[len(name) + 2 :]) if kt.startswith(name + ": ") else kt


def row_keys(cfg):
    """{col: the stored value in its base unit, or None}: the sort keys of one row (S4)."""
    return {col: cfg["figures"][METRIC[col]]["sort_key"] for col in COLS}


def row_html(rid, name, g, href, idle, right, table=False, keys=None):
    """One home row: pie, name and its pin (or a reference's kind), then `right`, the four figures.
    The model is the section's own heading, so a system row does not repeat it."""
    # the row header is named by the system's name alone, not by the six states and pin it also holds
    # a row under a pending disclosure draws no state and no text (RFC-0016 OVR-8)
    said = f'<p class="sr">{e(states_said(g))}</p>' if g["drawn"] else ""
    cells = g["cells"] if g["drawn"] else None
    cell = f' role="rowheader" aria-labelledby="{e(rid)}-name"' if table else ""
    hid = f' id="{e(rid)}-name"' if table else ""
    attrs = ' role="row"' if table else ""
    if table and keys is not None:  # a sortable table's row: its name and sort keys (S4, S5)
        attrs += (
            f' data-name="{e(name.lower())}" data-k="{e(json.dumps(keys, separators=(",", ":")))}"'
        )
    return f'''
<div class="row" id="{e(rid)}"{attrs}>
  <div class="r-main">
    <div class="sysc"{cell}>
      <a class="pie" href="{e(href)}" tabindex="-1" aria-hidden="true">{pie_svg(g["states"], 120, cells=cells, hit=True)}<span class="tip"></span></a>
      <div class="who"><h3 class="name"{hid}><a href="{e(href)}">{e(name)}</a></h3>{said}{idle}</div>
    </div>
    {right}
  </div>
</div>'''


def figures(cfg, base, table, who=""):
    """The four figures of a home row; each links to its own plate, at base + "-" + its column."""
    cell = ' role="cell"' if table else ""
    return (
        '<div class="vals">'
        + "".join(
            f'<div class="vc"{cell} data-col="{c}">{value_link(cfg, c, f"{base}-{c}", who)}</div>'
            for c in COLS
        )
        + "</div>"
    )


def sort_heads():
    """The column heads of the sortable table: each one a button with its sort glyph."""

    def head(col, label, cls=""):
        on = col == "system"
        w = SORT_WORDS[col]
        return (
            f'<div class="hc{cls}" role="columnheader" data-col="{col}"'
            + (' aria-sort="ascending"' if on else "")
            + ">"
            f'<button type="button" class="sb" data-col="{col}" data-asc="{e(w["asc"])}" data-desc="{e(w["desc"])}">'
            f'{label}\u00a0<span class="g" aria-hidden="true">{"↑" if on else "↕"}</span></button></div>'
        )

    return (
        f'<div class="heads" role="row">{head("system", "System", " hsys")}'
        + "".join(head(c, e(HEAD[c])) for c in COLS)
        + "</div>"
    )


def nb_models(r):
    """A system's models as its sources name them, whole (never cut mid-phrase), notes trimmed."""
    out = []
    for given in r["models"]:
        m = given.replace(" (model id as given)", "")
        out.append(
            "Model " + m
            if m.startswith("not named")
            else sentence_case(m)
            if m.startswith("no ")
            else m
        )
    return "; ".join(out)


def nb_meta(rid):
    """Family and repository status (the heading says no adapter runs them yet)."""
    status = S.V["facts"]["rows"][rid]["status"]["state"]
    return " · ".join([FAMILY_WORD[S.CRIT["rows"][rid]["family"]], STATUS_WORD[status]])


def nb_grid():
    out = ""
    for rid in S.V["orders"]["not_benchmarked"]:
        r, g = S.V["facts"]["rows"][rid], glyph(rid)
        out += (
            f'<li class="nb" id="nb-{e(rid)}"><span class="nbpie" role="img" aria-label="{e(aria(g, r["name"]))}">{pie_svg(g["states"], 56)}</span>'
            f'<div><h3 class="nbn">{e(r["name"])}</h3><p class="nbm">{keep(nb_models(r))}</p><p class="nbm">{keep(nb_meta(rid))}</p></div></li>'
        )
    return f'<ul class="nbgrid">{out}</ul>'


def shape_words(cfg):
    """What the configuration ran, from its workload record and reference profile, without the
    model name the section already prints."""
    sh = cfg["workload"]["shape"]
    out = sh["output_tokens"]
    tail = "the next token" if out == 1 else f"{out:,} output tokens"
    batch = sh["batch_size"]
    gpus = cfg["gpu"]["count"]
    return " · ".join([
        f"{sh['prompt_tokens']:,}-token prompt, {tail}",
        f"{batch:,} request{'s' if batch != 1 else ''} per batch",
        f"{gpu_words(cfg)} GPU{'s' if gpus != 1 else ''}",
    ])  # fmt: skip


def model_sizes(cfg):
    """The model's size from its workload record, so a row never reads as a 17B model."""
    p = cfg["workload"]["model"]["parameters"]
    total, active = p["total"], p["active_per_token"]
    if total == active:
        return f"{size_words(total)} parameters"
    return f"{size_words(total)} parameters, {size_words(active)} active per token"


def model_line(cfg):
    """The model fact of a system page: name, size and the precision proved."""
    m = cfg["workload"]["model"]
    p = m["parameters"]
    size = (f"{size_words(p['total'])} parameters (dense)" if p["total"] == p["active_per_token"]
            else f"{size_words(p['total'])} total, {size_words(p['active_per_token'])} active per token")  # fmt: skip
    prec = cfg["workload"]["precision"]["proved"]
    said = S.V["facts"]["models"][m["digest"]]["precision_words"].get(prec)
    return f"{S.MODEL_NAME[m['digest']]}, {size}, {prec}" + (f" ({said})" if said else "")


def facts_line(text):
    """A line of facts: each one a span, so phones can list them (words.css); the separator stays
    in the text, so the facts never run together when read aloud."""
    return '<span class="sep">\u00a0· </span>'.join(
        f"<span>{e(x)}</span>" for x in re.split(r"[ \u00a0]· ", text)
    )


def by_name(cfgs):
    return sorted(cfgs, key=lambda c: (name_of(c["system"]).lower(), c["position"]))


def tables():
    """S6: one table per model, largest first, then one per workload of that model."""
    out = []
    for d in S.MODELS:
        wls = sorted(
            {c["workload"]["id"] for c in S.PROVERS if c["workload"]["model"]["digest"] == d}
        )
        for wid in wls:
            rows = by_name(c for c in S.PROVERS if c["workload"]["id"] == wid)
            sid = slug(S.MODEL_NAME[d]) if len(wls) == 1 else f"{slug(S.MODEL_NAME[d])}-{slug(wid)}"
            out.append((d, sid, rows))
    return out


def plate_prefix(cfg):
    """The id prefix of a configuration's plates on its system page: `fig-` when the system has
    one configuration (RFC-0009 S1), else the row's id first, so each plate id is the page's
    only one and each overview figure links its own configuration's plate."""
    if len(configs_of(cfg["system"])) == 1:
        return "fig-"
    return f"{row_id(cfg)}-fig-"


def claims_href(cfg):
    """A row header's link: the validated claims of the row's card on its system page (S1)."""
    return f"{S.PAGE[cfg['system']]}#claims-{cfg['configuration']}"


def fig_href(cfg, col):
    """An overview figure's plate on the system page."""
    return f"{S.PAGE[cfg['system']]}#{plate_prefix(cfg)}{col}"


def pin_line(r, rows):
    """A row header's pin, and the card's `configuration` where the table holds two rows of the
    system (RFC-0009 S1): the card's identity, no claim text."""
    two = sum(x["system"] == r["system"] for x in rows) > 1
    cfg = f'<span class="nw"> · {e(r["configuration"])}</span>' if two else ""
    return f'<p class="wl">{pin_link(r)}{cfg}</p>'


# the overview's description, in its meta and share tags
HOME_DESC = "Six properties of one proof per system (draft criteria), and the benchmark's own figures per model, sortable by column."


def build_index():
    first = f"System, {SORT_WORDS['system']['asc']}"
    secs = ""
    seen = set()
    all_tables = tables()
    for d, sid_, rows in all_tables:
        name = S.MODEL_NAME[d]
        native = ""
        if d not in seen and sum(x[0] == d for x in all_tables) > 1:
            native = f'<p class="sec-l">{e(NATIVE_HEADER)}</p>'
        seen.add(d)
        body_rows = "".join(
            row_html(
                row_id(r),
                name_of(r["system"]),
                glyph(r["system"]),
                claims_href(r),
                pin_line(r, rows),
                '<div class="vals">'
                + "".join(
                    f'<div class="vc" role="cell" data-col="{c}">{value_link(r, c, fig_href(r, c), name_of(r["system"]))}</div>'
                    for c in COLS
                )
                + "</div>",
                True,
                row_keys(r),
            )
            for r in rows
        )
        secs += f"""
  <section class="sec bench" id="{sid_}" aria-labelledby="h-{sid_}">
    <div class="sec-h"><h2 id="h-{sid_}" class="sect">{e(name)}</h2><p class="sec-l">{facts_line(readable(model_sizes(rows[0]) + " · " + shape_words(rows[0])))}</p>{native}</div>
    <div class="tbl" role="table" aria-labelledby="h-{sid_}" aria-describedby="sort-now" data-col="system" data-dir="asc">
      {sort_heads()}
      <div class="rows" role="rowgroup">{body_rows}</div>
    </div>
  </section>"""
    refs = ""
    for rid in S.V["orders"]["reference"]:
        cfg = first_config(rid)
        counts = "".join(f'<p class="wl">{with_rule(readable(runs_counts(c)))}</p>'
                         for c in S.CONFIGS if c["system"] == rid and not has_figures(c))  # fmt: skip
        refs += row_html(
            rid,
            name_of(rid),
            glyph(rid),
            f"{REF_PAGE}#{rid}",
            f'<p class="wl"><span>{e(kind_words(rid))}</span></p>{counts}',
            figures(cfg, f"{REF_PAGE}#{rid}-fig", True, who=name_of(rid)),
            True,
        )
    nb_count = len(S.V["orders"]["not_benchmarked"])
    body = f"""
{header("home")}
<main id="main">
{masthead()}
<div class="wrap">
  {secs}
  <p id="sort-now" hidden>{e(first)}</p>
  <section class="sec refs" id="references" aria-labelledby="h-refs">
    <div class="sec-h"><h2 id="h-refs" class="sect">References</h2></div>
    <div role="table" aria-labelledby="h-refs">
    {plain_heads("Reference")}
    {refs}
    </div>
  </section>
  <section class="sec" id="not-yet" aria-labelledby="h-nb">
    <div class="sec-h"><h2 id="h-nb" class="sect">Not benchmarked yet<sup aria-hidden="true">{nb_count}</sup><span class="sr">, {nb_count} systems</span></h2></div>
    {nb_grid()}
  </section>
</div>
</main>
{footer()}"""
    return page(
        "Inference proofs",
        HOME_DESC,
        body,
        "home",
        "",
        "home",
    )


def plain_heads(first):
    """Column heads for a table that does not sort: the same columns, not pressable (S9: each
    cell has one column header)."""
    return (
        f'<div class="heads plain" role="row"><span class="hsys" role="columnheader">{e(first)}</span>'
        + "".join(f'<span role="columnheader">{e(HEAD[c])}</span>' for c in COLS)
        + "</div>"
    )
