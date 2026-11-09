"""The overview page (index.html): one sortable table across models, one row per benchmarked
system on its overview workload (S5, S6), default-sorted by overhead against production serving;
then the systems not benchmarked yet; and the helpers the other pages share with it (model
sizes, shapes, pins).
"""

import json
import re

from . import state as S
from .chrome import footer, header, masthead, page
from .hexagon import pie_svg
from .plates import (
    BOARD,
    BOARD_GROUPS,
    BOARD_HEAD,
    SORT_WORDS,
    aria,
    bits_words,
    configs_of,
    glyph,
    keep,
    metric_of,
    name_of,
    readable,
    row_id,
    sentence_case,
    states_said,
    upstream,
    value_link,
    words,
)
from .words import FAMILY_WORD, STATUS_WORD, e, gpu_words

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
    return {col: cfg["figures"][metric_of(cfg, col)]["sort_key"] for col in BOARD}


def board_configs():
    """S6: the overview's rows, one per benchmarked system: its configuration on the workload
    `facts.json` names for it (`overview_workload`), or its only configuration. A system with
    more than one and none named, or a named workload it did not run, stops the build."""
    out = []
    for sid in S.V["orders"]["benchmarked"]:
        cfgs = [c for c in S.PROVERS if c["system"] == sid]
        named = S.V["facts"]["rows"][sid].get("overview_workload")
        if named is not None:
            cfgs = [c for c in cfgs if c["workload"]["id"] == named]
        if len(cfgs) != 1:
            raise RuntimeError(f"{sid}: {len(cfgs)} configurations for its overview row; name one "
                               "workload as `overview_workload` in web/_data/facts.json")  # fmt: skip
        out.append(cfgs[0])
    return board_order(out)


def board_order(cfgs):
    """S5: the default order, overhead against production serving ascending (the stored value);
    a row with no overhead last; ties by system name, then profile, then index position."""

    def key(c):
        k = row_keys(c)["overhead"]
        return (k is None, k or 0.0, name_of(c["system"]).lower(), c["profile"], c["position"])

    return sorted(cfgs, key=key)


DEFAULT_COL = "overhead"


def sort_heads():
    """The column heads: System and each figure a button with its sort glyph, under the line
    its group shares (BOARD_GROUPS: the overhead's baseline, the three figures' per-Gbit basis),
    which a screen reader hears in the button."""

    def head(col, label, said="", cls=""):
        on = col == DEFAULT_COL
        w = SORT_WORDS[col]
        return (
            f'<div class="hc{cls}" role="columnheader" data-col="{col}"'
            + (' aria-sort="ascending"' if on else "")
            + ">"
            f'<button type="button" class="sb" data-col="{col}" data-asc="{e(w["asc"])}" data-desc="{e(w["desc"])}">'
            f'{label}\u00a0<span class="g" aria-hidden="true">{"↑" if on else "↕"}</span>'
            + (f'<span class="sr">, {e(said)}</span>' if said else "")
            + "</button></div>"
        )

    group_of = {c: words for cols, words in BOARD_GROUPS for c in cols}
    groups = "".join(
        f'<div class="hg hg-{e(cols[0])}" aria-hidden="true"><span>{e(words)}</span></div>'
        for cols, words in BOARD_GROUPS
    )
    return (
        f'<div class="heads" role="row">{head("system", "System", cls=" hsys")}{groups}'
        + "".join(head(c, e(BOARD_HEAD[c]), group_of.get(c, "")) for c in BOARD)
        + "</div>"
    )


def model_lines(cfg):
    """The row's model under the system's name, only what a comparison needs: its name, then its
    active parameters, the weight width the per-Gbit figures divide by and the batch size (and a
    closed or open workload's division). The rest (total parameters, the width's basis, prompt
    and output lengths, GPUs) is in the cell's title and on the system page."""
    p = cfg["workload"]["model"]["parameters"]
    total, active = p["total"], p["active_per_token"]
    wb = cfg["workload"]["precision"].get("weight_bits") or {}
    bits = f"{wb['bits']:.2g}-bit" if wb.get("bits") is not None else "bits not recorded"
    short = [
        f"{size_words(active)} active",
        bits,
        f"batch\u00a0{cfg['workload']['shape']['batch_size']:,}",
    ]
    if cfg["workload"]["division"] != "native":
        short.append(f"{cfg['workload']['division']} division")
    size = (f"{size_words(total)}, dense" if total == active
            else f"{size_words(total)} total, {size_words(active)} active")  # fmt: skip
    title = " · ".join([size, bits_words(cfg), shape_words(cfg)])
    return (
        f'<div class="mc" title="{e(title)}"><p class="mn">{e(S.MODEL_NAME[cfg["workload"]["model"]["digest"]])}</p>'
        f'<p class="ms">{facts_line(readable(" · ".join(short)))}</p></div>'
    )


def board_row(cfg):
    """One overview row: the row header (glyph, name, pin, and the model under them), then the
    figures, each a link to its own plate on the system page."""
    sid = cfg["system"]
    name, g, href = name_of(sid), glyph(sid), claims_href(cfg)
    said = f'<p class="sr">{e(states_said(g))}</p>' if g["drawn"] else ""  # OVR-8: no state
    cells = g["cells"] if g["drawn"] else None
    keys = e(json.dumps(row_keys(cfg), separators=(",", ":")))
    vals = "".join(
        f'<div class="vc" role="cell" data-col="{c}">{value_link(cfg, c, fig_href(cfg, c), name)}</div>'
        for c in BOARD
    )
    return f'''
<div class="row" id="{e(sid)}" role="row" data-name="{e(name.lower())}" data-k="{keys}">
  <div class="r-main">
    <div class="sysc" role="rowheader" aria-labelledby="{e(sid)}-name">
      <a class="pie" href="{e(href)}" tabindex="-1" aria-hidden="true">{pie_svg(g["states"], 120, cells=cells, hit=True)}<span class="tip"></span></a>
      <div class="who"><h3 class="name" id="{e(sid)}-name"><a href="{e(href)}">{e(name)}</a></h3>{said}<p class="wl">{pin_link(cfg)}</p></div>
      {model_lines(cfg)}
    </div>
    <div class="vals">{vals}</div>
  </div>
</div>'''


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


# the overview's description, in its meta and share tags
HOME_DESC = ("Six properties of one proof per system (draft criteria), and one row per system: "
             "overhead against production serving, then proving time, proof size and check time "
             "per token per Gbit of active weights, sortable by column.")  # fmt: skip


def build_index():
    rows = board_configs()
    first = f"{BOARD_HEAD[DEFAULT_COL]}, {SORT_WORDS[DEFAULT_COL]['asc']}"
    n = len(rows)
    nb_count = len(S.V["orders"]["not_benchmarked"])
    body = f"""
{header("home")}
<main id="main">
{masthead()}
<div class="wrap">
  <section class="sec board" id="benchmarked" aria-labelledby="h-bench">
    <div class="sec-h"><h2 id="h-bench" class="sect">Benchmarked<sup aria-hidden="true">{n}</sup><span class="sr">, {n} systems</span></h2></div>
    <div class="tbl" role="table" aria-labelledby="h-bench" aria-describedby="sort-now" data-col="{DEFAULT_COL}" data-dir="asc">
      {sort_heads()}
      <div class="rows" role="rowgroup">{"".join(board_row(c) for c in rows)}</div>
    </div>
  </section>
  <p id="sort-now" hidden>{e(first)}</p>
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
