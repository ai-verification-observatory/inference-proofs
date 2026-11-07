"""A card's validated claims on its system page (RFC-0009 S1, RFC-0016 OVR-7, OVR-8): per
property the deciding quote with its source at the pin, the sources read when Not stated, both
quotes of a conflict, the controls the map ties to the property and their outcomes; then the
card's identity, the card in full (folded) and its `quality_gap` and `residual` beside the
agreement rate (RFC-0015 RC-6).

Every word printed here is the system's own (quotes, card fields), the criteria file's (reasons),
a stored outcome or a fixed word for a stored id: nothing is inferred.
"""

from . import state as S
from .plates import (
    EXT,
    path_html,
    readable,
    record_html,
    source_html,
    source_label,
    with_rule,
)
from .words import (
    OUTCOME_SHORT,
    STATE_WORD,
    e,
    labels,
    sig4,
    spread_line,
    why_words,
)

# ------------------------------------------------------------------ one property's evidence


def quote_source(q):
    """A quote's source at the pin: repository@commit, path and lines, linked at that commit."""
    where = " ".join(x for x in (q.get("path"), q.get("lines")) if x)
    label = f"{q['repo']}@{q['commit'][:8]} {where}".strip()
    return f'<a class="qsrc" href="{e(q["url"])}">{path_html(label)}{EXT}</a>'


def quote_html(q):
    """The quote, verbatim, with its source under it."""
    return (
        f'<blockquote class="eq"><p>“{e(q["text"])}”</p></blockquote>'
        f'<p class="es">{quote_source(q)}</p>'
    )


def sources_read(items):
    """RFC-0016 ST-2: what was read for a Not stated cell (criteria/1 `sources_read`), each
    repository at its commit with the paths read, each web page with its retrieval date."""
    parts = []
    for s in items:
        if "repo" in s:
            head = f"{s['repo']}@{s['commit'][:8]}"
            parts.append(f"{path_html(head)}: {e(', '.join(s['paths']))}")
        else:
            parts.append(f"{path_html(source_label(s['url']))} retrieved {e(s['retrieved'])}")
    return f'<p class="er"><span class="ek">Read</span> {"; ".join(parts)}</p>'


def run_ref(rid, record):
    """A run named by its id; its record once the release is published."""
    return record_html(record, rid) if record else path_html(rid)


def control_lines(pc, prop):
    """RFC-0016 OVR-7: each control the map ties to the property, with its outcome in every run
    read, one line per run that recorded any of them (linked to its `controls.json`), then the
    runs that recorded none, named in one line ("not run"). A property no control is tied to
    says so. With no run read (the criteria file names no release, OVR-5), every mapped control
    reads "not run"."""
    entry = pc["properties"][prop]
    if not entry["mapped"]:
        return f'<p class="ec">{with_rule("No control tests this property (RFC-0008).")}</p>'
    ids = ", ".join(entry["mapped"])
    if not pc["runs"]:
        return f'<p class="ec"><span class="ek">Controls</span> {e(ids)}: not run</p>'
    out, silent = [], []
    for run in pc["runs"]:
        found = [o for o in entry["outcomes"] if o["run_id"] == run["run_id"]]
        if all(o["outcome"] == "not_run" for o in found):
            silent.append(run)
            continue
        said = []
        for o in found:
            w = OUTCOME_SHORT[o["outcome"]]
            if o.get("note") and o["outcome"] in ("not_applicable", "void", "error"):
                w += f" ({o['note']})"
            said.append(f'<span class="nw">{e(o["control"])}</span> {e(w)}')
        out.append(
            f'<p class="ec">{", ".join(said)} <span class="ek">in run</span> '
            f"{run_ref(run['run_id'], run['controls'])}</p>"
        )
    if silent:
        runs = ", ".join(run_ref(r["run_id"], r["record"]) for r in silent)
        word = "run" if len(silent) == 1 else "runs"
        out.append(
            f'<p class="ec"><span class="ek">Controls</span> {e(ids)}: not run '
            f'<span class="ek">in {word}</span> {runs}</p>'
        )
    return "".join(out)


def contradicted_lines(cell, pc, prop):
    """RFC-0016 OVR-4, OVR-7: an overridden cell's stated state, then each control and run that
    contradicts it."""
    if not cell.get("stated"):
        return ""
    found = pc["properties"][prop]["contradicted"] if pc and not pc["withheld"] else []
    runs = "; ".join(f'<span class="nw">{e(x["control"])}</span> accepted in run '
                     f"{run_ref(x['run_id'], x['record'])}" for x in found)  # fmt: skip
    return (f'<p class="ex"><span class="ek">Stated</span> {e(STATE_WORD[cell["stated"]])}'
            f'{"; contradicted by " + runs if runs else ""}</p>')  # fmt: skip


def evidence(sid, prop, pc):
    """What one property's state rests on, under its reason: the deciding quote (both, in a
    conflict), or the sources read; the stated state of an overridden cell and what contradicts
    it; the mapped controls' outcomes. Under a pending disclosure (OVR-8, `pc` withheld) the
    quotes only."""
    cell = S.CRIT["rows"][sid]["cells"][prop]
    quotes = cell["quotes"]
    shown = quotes[:1] if not cell["conflict"] else quotes
    body = "".join(quote_html(q) for q in shown if q.get("repo"))
    if not quotes and cell["sources_read"]:
        body += sources_read(cell["sources_read"])
    if pc is not None and not pc["withheld"]:
        body += contradicted_lines(cell, pc, prop) + control_lines(pc, prop)
    return f'<div class="ev">{body}</div>' if body else ""


# ------------------------------------------------------------------ the card: identity, in full, gap


def card_fact(cfg):
    """S1 item 2: the card's identity, a link to its file and its digest, and whether a system
    maintainer reviewed this version (RFC-0002 §Failure modes)."""
    card = cfg["card"]
    digest = str(card["digest"]).removeprefix("sha256:")
    lines = [
        f'<span class="nw">{e(card["configuration"])}</span> · version {e(card["card_version"])}',
        f'<a href="{e(card["link"])}">{path_html(card["path"])}{EXT}</a>',
        f"sha256 <code>{e(digest[:12])}</code>",
    ]
    if not card["reviewed"]:
        lines.append("card not reviewed by system maintainers")
    return '<span class="links">' + "".join(f"<span>{x}</span>" for x in lines) + "</span>"


SCALAR = {None: "null", True: "true", False: "false"}


def card_value(v):
    """One card value as stored: text, a link for a source URL, a list one item per line, a
    mapping as its own keys and values."""
    if isinstance(v, str):
        if v.startswith("https://"):
            return f'<a class="qsrc" href="{e(v)}">{path_html(source_label(v))}{EXT}</a>'
        return e(v)
    if v is None or isinstance(v, bool):
        return SCALAR[v]
    if isinstance(v, list):
        items = "".join(f"<li>{card_value(x)}</li>" for x in v)
        return f'<ul class="cl">{items}</ul>' if v else "none"
    if isinstance(v, dict):
        rows = "".join(f"<div><dt>{e(k)}</dt><dd>{card_value(x)}</dd></div>" for k, x in v.items())
        return f'<dl class="cn">{rows}</dl>'
    return e(v)


def field_sources(body, field):
    """The card's `sources` entries for one field (`relation`, `relation.segment`...), linked."""
    out = []
    for key, url in (body.get("sources") or {}).items():
        if key == field or key.startswith(field + "."):
            sub = key[len(field) + 1 :]
            label = (f"{sub}: " if sub else "") + source_label(url)
            out.append(f'<a class="qsrc" href="{e(url)}">{path_html(label)}{EXT}</a>')
    return f'<p class="es">{" ".join(out)}</p>' if out else ""


def card_full(cfg, sid):
    """S1 item 4: the claim card in full, each field with its sources, folded in a native
    `details` that opens with one press, with or without script."""
    body = cfg["card"]["body"]
    rows = "".join(
        f"<div><dt>{e(k)}</dt><dd>{card_value(v)}{field_sources(body, k)}</dd></div>"
        for k, v in body.items()
        if k != "sources"
    )
    return (
        f'<details class="cardfull" id="card-{e(cfg["configuration"])}">'
        f'<summary><span class="sect sm">Claim card in full</span></summary>'
        f'<dl class="cf">{rows}</dl></details>'
    )


def gap_items(body, field):
    """`quality_gap` or `residual` as the card states it, with its sources; "not stated" where
    the card holds no such field (AGENTS.md rule 9)."""
    v = body.get(field)
    if not v:
        return "not stated"
    if field == "quality_gap":
        items = "".join(
            f"<li>{e(x['metric'])}: {e(x['value'])}"
            + (f' <a class="qsrc" href="{e(x["source"])}">{path_html(source_label(x["source"]))}{EXT}</a>'
               if x.get("source") else "")
            + "</li>"
            for x in v
        )  # fmt: skip
        return f'<ul class="cl">{items}</ul>'
    return card_value(v) + field_sources(body, field)


def agreement_plate(cfg, label):
    """RFC-0015 RC-5, RC-6: the agreement rate with a rerun by a weights holder, every label in
    view (S2, S3), or why it has no value."""
    f = cfg["agreement"]
    kv = []
    if f["value"] is None:
        val = '<span class="na">No value</span>'
        kv.append(("why", with_rule(readable(why_words(f, cfg)))))
    else:
        val = f'<span class="fig"><span class="n">{e(sig4(f["value"]))}</span></span>'
        if f.get("stats"):
            kv.append(("spread", e(spread_line(f))))
        kv += [(k, e(v)) for k, v in labels(f, cfg)]
    kv.append(("source", source_html(f["source"])))
    dl = "".join(f"<div><dt>{e(k)}</dt><dd>{v}</dd></div>" for k, v in kv)
    return (f'<div class="plate" id="agree-{e(cfg["configuration"])}-{e(cfg["workload"]["id"])}">'
            f'<p class="lbl">{e(label)}</p><p class="pv">{val}</p><dl>{dl}</dl></div>')  # fmt: skip


def gap_block(cfgs):
    """S1 item 5: open, after the card, its `quality_gap` and `residual` with the agreement
    rate on a plate beside them, where the release reports one (RFC-0015 RC-6)."""
    body = cfgs[0]["card"]["body"]
    gap = (
        '<dl class="facts gapf">'
        f"<div><dt>quality gap</dt><dd>{gap_items(body, 'quality_gap')}</dd></div>"
        f"<div><dt>residual</dt><dd>{gap_items(body, 'residual')}</dd></div></dl>"
    )
    rated = [c for c in cfgs if c["agreement"]["recorded"]]
    many = len(rated) > 1
    plates = "".join(
        agreement_plate(c, "Agreement with a rerun" + (f" · {c['workload']['id']}" if many else ""))
        for c in rated
    )
    return (
        f'<div class="gapblk">{gap}{f'<div class="agree">{plates}</div>' if plates else ""}</div>'
    )


def property_controls_of(cfgs):
    """The card row's control lists: computed once per card row (OVR-5 reads the same runs for
    every configuration of the card), so the first configuration's are the row's."""
    return next((c["property_controls"] for c in cfgs if c.get("property_controls")), None)
