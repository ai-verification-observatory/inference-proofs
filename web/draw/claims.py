"""A card's validated claims on its system page (RFC-0009 S1, RFC-0016 OVR-7, OVR-8): beside
each property, its state, our reason and a link to its entry in "How we read it", and, for an
overridden cell, its stated state and what contradicts it; then, folded in "How we read it", per
property the deciding quote with its source at the pin, both quotes of a conflict, the sources
read and the controls the map ties to it with their outcomes; then the card's identity, the card
in full (folded) and its `quality_gap` and `residual` beside the agreement rate (RFC-0015 RC-6).

Every word printed here is the system's own (quotes, card fields), the criteria file's (reasons),
a stored outcome or a fixed word for a stored id: nothing is inferred.
"""

import json
import re

from . import state as S
from .plates import (
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

GITHUB_BLOB = re.compile(
    r"https://github\.com/([^/]+/[^/]+)/blob/([0-9a-f]{7,40})/([^#?]+)(?:\?[^#]*)?(?:#(L\d+(?:-L\d+)?))?"
)


def pin_label(url):
    """A source link's words: repository@commit (8 hex), path and lines, as a quote's source
    reads; a link that is no GitHub file at a commit keeps its path words (`source_label`)."""
    m = GITHUB_BLOB.match(url)
    if not m:
        return source_label(url)
    return " ".join(x for x in (f"{m[1]}@{m[2][:8]}", m[3], m[4]) if x)


def source_link(url, prefix=""):
    """A small underlined link to a source at its pin (`.qsrc`)."""
    return f'<a class="qsrc" href="{e(url)}">{path_html(prefix + pin_label(url), ext=True)}</a>'


def quote_source(q):
    """A quote's source at the pin: repository@commit, path and lines, linked at that commit. The
    words name the repository without its owner (the facts' pinned row names it in full), so the
    link keeps to one line in the fold's text column; the owner stays in the link and its title."""
    where = " ".join(x for x in (q.get("path"), q.get("lines")) if x)
    full = f"{q['repo']}@{q['commit'][:8]} {where}".strip()
    label = f"{q['repo'].rsplit('/', 1)[-1]}@{q['commit'][:8]} {where}".strip()
    return (
        f'<a class="qsrc" href="{e(q["url"])}" title="{e(full)}">{path_html(label, ext=True)}</a>'
    )


def quote_html(q):
    """The quote, verbatim (its line breaks kept, words.css `.eq p`), with its source under it."""
    return (
        f'<blockquote class="eq"><p>“{e(q["text"])}”</p></blockquote>'
        f'<p class="es">{quote_source(q)}</p>'
    )


def deciding_quotes(sid, prop, cell):
    """S1 item 1: the quote the state rests on (`decides: true`; in a conflict, the quote of the
    stated state, RFC-0016 ST-8). A stated cell with no deciding quote, or a deciding quote with
    no repository, commit or link, stops the build: a state is never printed without its source
    (AGENTS.md rule 9)."""
    quotes = [q for q in cell["quotes"] if q.get("decides")]
    if cell["state"] != "not_stated" and not quotes:
        raise RuntimeError(f"criteria {sid}/{prop}: state {cell['state']} with no deciding quote")
    for q in quotes:
        if not all(q.get(k) for k in ("repo", "commit", "url")):
            raise RuntimeError(f"criteria {sid}/{prop}: a printed quote has no repo, commit or url")
    return quotes


def ev_line(cls, label, body, block=False):
    """One line of a property's evidence: a quiet label ("quote", "read", "controls", "stated")
    in its own column, the text beside it (words.css `.eqs`, `.er`, `.ec`, `.ex`). block: the
    text holds a quote, so the line is a `div` (a `p` cannot hold a `blockquote`)."""
    if block:
        return (
            f'<div class="{cls}"><span class="ek">{label}</span><div class="eb">{body}</div></div>'
        )
    return f'<p class="{cls}"><span class="ek">{label}</span><span class="eb">{body}</span></p>'


def sources_read(items, same_as=None):
    """RFC-0016 ST-2: what was read for a Not stated cell, one line per repository, which links
    the repository's tree at that commit. A list equal to an earlier property's names that
    property instead of printing it twice."""
    if same_as:
        prop = next(p for p in S.PROPS if p["id"] == same_as)
        return ev_line("er", "read", f'as for <a class="qsrc" href="#read-{e(same_as)}">'
                                     f'<span class="seg">{e(prop["name"])}</span></a>')  # fmt: skip
    parts = []
    for s in items:  # criteria/1: a repository at a full commit with its paths, or a web page
        if "repo" in s:
            head = path_html(f"{s['repo']}@{s['commit'][:8]}", ext=True)
            url = f"https://github.com/{s['repo']}/tree/{s['commit']}"
            names = ", ".join(f'<span class="nw">{e(x)}</span>' for x in s["paths"])
            parts.append(
                f'<span class="rd"><a class="qsrc" href="{e(url)}">{head}</a> {names}</span>'
            )
        else:
            parts.append(f'<span class="rd">{source_link(s["url"])} retrieved '
                         f"{e(s['retrieved'])}</span>")  # fmt: skip
    return ev_line("er", "read", "".join(parts))


def run_ref(rid, record):
    """A run named by its id; its record once the release is published."""
    return record_html(record, rid) if record else path_html(rid)


def no_run_read():
    """Why a card row reads no run (RFC-0016 OVR-5): the criteria file names no release, or the
    release it names lists no run of the card."""
    release = S.CRIT.get("release")
    if release is None:
        return "no run read, since the criteria file names no release (RFC-0016 OVR-5)"
    return f"no run read, since release {release} and those before it list no run of this card (RFC-0016 OVR-5)"


def control_lines(pc, prop):
    """RFC-0016 OVR-7: each control the map ties to the property, with its outcome in every run
    read, one line per run that recorded any of them (linked to its `controls.json`), then the
    runs that recorded none, named in one line ("not run"). One form for every case: "controls",
    then the ids or "none", then what the runs say. With no run read (OVR-5), the line says why,
    so it never reads as a run that skipped them."""
    entry = pc["properties"][prop]
    if not entry["mapped"]:
        return ev_line("ec", "controls", with_rule("none (RFC-0008)"))
    ids = ", ".join(entry["mapped"])
    if not pc["runs"]:
        return ev_line("ec", "controls", f"{e(ids)}: {with_rule(readable(no_run_read()))}")
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
        out.append(ev_line("ec", "controls", f"{', '.join(said)} in run "
                                             f"{run_ref(run['run_id'], run['controls'])}"))  # fmt: skip
    if silent:
        runs = ", ".join(run_ref(r["run_id"], r["record"]) for r in silent)
        word = "run" if len(silent) == 1 else "runs"
        out.append(ev_line("ec", "controls", f"{e(ids)}: not run in {word} {runs}"))
    return "".join(out)


def contradicted_line(cell, pc, prop):
    """RFC-0016 OVR-4, OVR-7: an overridden cell's stated state and each control and run that
    contradicts it, in one line under the property's reason: the one line of the cell's evidence
    kept beside the glyph, since it changes the state."""
    if not cell.get("stated"):
        return ""
    found = pc["properties"][prop]["contradicted"] if pc and not pc["withheld"] else []
    runs = "; ".join(f'<span class="nw">{e(x["control"])}</span> accepted in run '
                     f"{run_ref(x['run_id'], x['record'])}" for x in found)  # fmt: skip
    return ev_line("ex", "stated", e(STATE_WORD[cell["stated"]])
                   + ("; contradicted by " + runs if runs else ""))  # fmt: skip


def evidence(sid, prop, pc):
    """What one property's block holds under its state and reason besides the link to how we
    read it: for an overridden cell, its stated state and what contradicts it (not under a
    pending disclosure: OVR-8, `pc` withheld), since that line changes the state; else nothing."""
    cell = S.CRIT["rows"][sid]["cells"][prop]
    if pc is None or pc["withheld"]:
        return ""
    line = contradicted_line(cell, pc, prop)
    return f'<div class="ev">{line}</div>' if line else ""


def evidence_of(sid, pc, order):
    """Each property's block evidence (`evidence`), by property id, in `order`."""
    return {prop: evidence(sid, prop, pc) for prop in order}


def conflict_lines(cell):
    """RFC-0016 ST-8: every quote of a conflicting cell, each with the state whose rule it meets
    and its source at the pin."""
    if not cell["conflict"]:
        return ""
    lines = []
    for q in cell["quotes"]:
        label = e(STATE_WORD[q["meets"]].lower()) if q.get("meets") else "quote"
        lines.append(ev_line("eqs", label, quote_html(q), block=True))
    return "".join(lines)


def read_entries(sid, pc, order):
    """How we read each property (RFC-0009 S1 item 1, RFC-0016 ST-2, ST-8, OVR-7), by property
    id, in `order`: the deciding quote verbatim with its source at the pin (in a conflict, every
    quote with the state whose rule it meets), the sources read (one line per repository, linked
    at its commit, with the paths read; a list equal to an earlier property's names that
    property), and the controls the map ties to it with their outcome in every run read (none
    under a pending disclosure, OVR-8). A property with none of these has no entry."""
    out, seen = {}, {}
    for prop in order:
        cell = S.CRIT["rows"][sid]["cells"][prop]
        quotes = deciding_quotes(sid, prop, cell)
        body = conflict_lines(cell) or "".join(
            ev_line("eqs", "quote", quote_html(q), block=True) for q in quotes
        )
        if cell["sources_read"]:
            key = json.dumps(cell["sources_read"], sort_keys=True)
            body += sources_read(cell["sources_read"], seen.get(key))
            seen.setdefault(key, prop)
        if pc is not None and not pc["withheld"]:
            body += control_lines(pc, prop)
        if body:
            out[prop] = body
    return out


def how_we_read(entries):
    """How we read it, folded in a native `details` that opens with one press, with or without
    script: one entry per property of `read_entries`, its id `read-<property>` (the rose's
    "source" links; words.js opens the fold when a link or the address names an entry, and moves
    focus to it). With no entry, no fold."""
    names = {p["id"]: p["name"] for p in S.PROPS}
    rows = "".join(f'<div id="read-{e(prop)}" tabindex="-1"><dt>{e(names[prop])}</dt><dd>{body}</dd></div>'
                   for prop, body in entries.items())  # fmt: skip
    if not rows:
        return ""
    return (
        '<details class="howread" id="how-we-read">'
        '<summary><span class="sect sm">How we read it</span></summary>'
        f'<dl class="cf hw">{rows}</dl></details>'
    )


# ------------------------------------------------------------------ the card: identity, in full, gap


def card_fact(cfg):
    """S1 item 2: the card's identity, a link to its file and its digest, and whether a system
    maintainer reviewed this version (RFC-0002 §Failure modes)."""
    card = cfg["card"]
    digest = str(card["digest"]).removeprefix("sha256:")
    lines = [
        f'<span class="nw">{e(card["configuration"])}</span> · version {e(card["card_version"])}',
        f'<a href="{e(card["link"])}">{path_html(card["path"], ext=True)}</a>',
        f"sha256 <code>{e(digest[:12])}</code>",
    ]
    if not card["reviewed"]:
        lines.append("card not reviewed by system maintainers")
    return '<span class="links cardid">' + "".join(f"<span>{x}</span>" for x in lines) + "</span>"


SCALAR = {None: "null", True: "true", False: "false"}


def own_sources(path, children, sources):
    """The card's `sources` entries for the field at `path` (`relation`, `security.notion`,
    `residual.1`): its own key, and any deeper key that names no child of the field, labelled
    with the rest of its key. A child's entries are printed under that child."""
    out = []
    for key, url in sources.items():
        if key == path:
            out.append(source_link(url))
        elif key.startswith(path + "."):
            rest = key[len(path) + 1 :]
            if rest.split(".", 1)[0] not in children:
                out.append(source_link(url, f"{rest}: "))
    return f'<p class="es">{"".join(out)}</p>' if out else ""


def card_value(v, path="", sources=None):
    """One card value as stored, with its sources (the card's `sources` keyed by `path`): text,
    a link for a source URL, a list one item per line, a mapping as its own keys and values.
    A field's own sources follow a text value and head a list or mapping, above its items."""
    sources = sources or {}
    if isinstance(v, list):
        own = own_sources(path, {str(i) for i in range(len(v))}, sources)
        items = "".join(
            f"<li>{card_value(x, f'{path}.{i}', sources)}</li>" for i, x in enumerate(v)
        )
        return own + (f'<ul class="cl">{items}</ul>' if v else "none")
    if isinstance(v, dict):
        own = own_sources(path, set(v), sources)
        rows = "".join(f"<div><dt>{e(k)}</dt><dd>{card_value(x, f'{path}.{k}', sources)}</dd></div>"
                       for k, x in v.items())  # fmt: skip
        return own + (f'<dl class="cn">{rows}</dl>' if v else "none")
    if isinstance(v, str) and v.startswith("https://"):
        text = source_link(v)
    elif v is None or isinstance(v, bool):
        text = SCALAR[v]
    else:
        text = e(v)
    return text + own_sources(path, set(), sources)


def card_full(cfg, sid):
    """S1 item 4: the claim card in full, each field with its sources, folded in a native
    `details` that opens with one press, with or without script."""
    body = cfg["card"]["body"]
    sources = body.get("sources") or {}
    rows = "".join(
        f"<div><dt>{e(k)}</dt><dd>{card_value(v, k, sources)}</dd></div>"
        for k, v in body.items()
        if k != "sources"
    )
    return (
        f'<details class="cardfull" id="card-{e(cfg["configuration"])}">'
        f'<summary><span class="sect sm">Claim card in full</span></summary>'
        f'<dl class="cf">{rows}</dl></details>'
    )


def gap_items(body, field):
    """`quality_gap` or `residual` as the card states it, each item with its source under it;
    "not stated" where the card holds no such field (AGENTS.md rule 9)."""
    v = body.get(field)
    if not v:
        return "not stated"
    sources = body.get("sources") or {}
    if field == "quality_gap":
        items = "".join(
            f"<li>{e(x['metric'])}: {e(x['value'])}"
            + (f'<p class="es">{source_link(x["source"])}</p>' if x.get("source") else "")
            + "</li>"
            for x in v
        )
        return (
            own_sources(field, {str(i) for i in range(len(v))}, sources)
            + f'<ul class="cl">{items}</ul>'
        )
    return card_value(v, field, sources)


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
    """S1 item 5: open, after the card, its `quality_gap` and `residual` under a label of their
    own, with the agreement rate on a plate beside them, where the release reports one
    (RFC-0015 RC-6)."""
    body = cfgs[0]["card"]["body"]
    gap = (
        '<div class="gapc"><p class="lbl">Quality gap and residual</p><dl class="facts gapf">'
        f"<div><dt>quality gap</dt><dd>{gap_items(body, 'quality_gap')}</dd></div>"
        f"<div><dt>residual</dt><dd>{gap_items(body, 'residual')}</dd></div></dl></div>"
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
