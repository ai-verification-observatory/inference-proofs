"""A card's validated claims on its system page (RFC-0009 S1, RFC-0016 OVR-7): beside
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
    EXT,
    config_of_run,
    flags_html,
    path_html,
    readable,
    run_ref,
    setup_diff,
    source_html,
    source_label,
    with_rule,
)
from .words import (
    CONTROL_WORDS,
    OUTCOME_SHORT,
    STATE_WORD,
    curly,
    e,
    labels,
    mean_words,
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


# a Markdown table row quoted on its own ("a | b | c"): printed as a one-row table
TABLE_ROW = re.compile(r"^[^|\n]+(?: \| [^|\n]+)+$")


def quote_html(q):
    """The quote, verbatim (its line breaks kept, words.css `.eq p`), its inline marks rendered
    (`card_text`), with its source under it; a quoted table row as a one-row table."""
    text = q["text"]
    if TABLE_ROW.match(text):
        cells = "".join(f"<td>{card_text(x)}</td>" for x in text.split(" | "))
        body = f'<table class="qrow"><tr>{cells}</tr></table>'
    else:
        body = f"<p>“{card_text(text)}”</p>"
    return f'<blockquote class="eq">{body}</blockquote><p class="es">{quote_source(q)}</p>'


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


def control_label(cid):
    """A control's id, its tamper in words beside it (RFC-0008)."""
    words = CONTROL_WORDS.get(cid)
    return f'<span class="nw">{e(cid)}</span>' + (f" ({e(words)})" if words else "")


def setup_key(rid):
    """The words that set a run's setup apart from the system's other setups ("24 requests per
    batch"); "" for a run of no rendered configuration."""
    c = config_of_run(rid)
    return ", ".join(setup_diff(c)) if c else ""


def run_refs(runs, silent, labelled):
    """The runs of one control line, each by its date and ordinal linked to its record (its
    `run.json` where it recorded no control, `silent`). Runs of several setups share dates and
    ordinals, so where the card row reads more than one setup (`labelled`), each setup's runs
    are followed by the words that set it apart."""
    by = {}
    for r in runs:
        key = setup_key(r["run_id"]) if labelled else ""
        by.setdefault(key, []).append(
            run_ref(r["run_id"], r["record"] if silent else r["controls"])
        )
    return "; ".join(
        ", ".join(refs) + (f' <span class="nw">({e(k)})</span>' if k else "")
        for k, refs in by.items()
    )


def control_lines(pc, prop):
    """RFC-0016 OVR-7: each control the map ties to the property, with its outcome in every run
    read: one line per outcome the runs share ("C1 (changed output token), C2 (changed prompt
    token): rejected in 2 runs"), each run linked to its `controls.json` (or its `run.json`
    where it recorded none, "not run"). A property no control tests has no line; nor does a
    card row that reads no run, which OVR-5 makes an error for review to catch."""
    entry = pc["properties"][prop]
    if not entry["mapped"] or not pc["runs"]:
        return ""
    groups = {}  # (outcome words, controls) -> runs
    for run in pc["runs"]:
        found = [o for o in entry["outcomes"] if o["run_id"] == run["run_id"]]
        by = {}
        for o in found:
            w = OUTCOME_SHORT[o["outcome"]]
            if o.get("note") and o["outcome"] in ("not_applicable", "void", "error"):
                w += f" ({o['note']})"
            by.setdefault(w, []).append(o["control"])
        for w, cids in by.items():
            groups.setdefault((w, tuple(cids)), []).append(run)
    labelled = len({setup_key(r["run_id"]) for r in pc["runs"]}) > 1
    out = []
    for (w, cids), runs in groups.items():
        refs = run_refs(runs, w == OUTCOME_SHORT["not_run"], labelled)
        word = "run" if len(runs) == 1 else f"{len(runs)} runs"
        said = ", ".join(control_label(x) for x in cids)
        out.append(ev_line("ec", "tamper tests", f"{said}: {flags_html(e(w))} in {word}: {refs}"))
    return "".join(out)


def contradicted_line(cell, pc, prop):
    """RFC-0016 OVR-4, OVR-7: an overridden cell's stated state and each control that
    contradicts it, in one short line under the property's reason: the one line of the cell's
    evidence kept beside the glyph, since it changes the state. The run is a link to the
    property's entry in "How we read it", whose control line prints its id and record: a run id
    (RFC-0010) is longer than the column beside a triangle, and wrapped it would push the other
    properties off their triangles. A screen reader hears the id in the link."""
    if not cell.get("stated"):
        return ""
    found = pc["properties"][prop]["contradicted"] if pc else []
    said = e(STATE_WORD[cell["stated"]])
    if found:
        controls = ", ".join(dict.fromkeys(x["control"] for x in found))
        runs = list(dict.fromkeys(x["run_id"] for x in found))
        word = "run" if len(runs) == 1 else "runs"
        said += (f'; <span class="nw">{e(controls)}</span> accepted in <a class="psrc" '
                 f'href="#read-{e(prop)}">{word}<span class="sr"> {e(", ".join(runs))}</span></a>')  # fmt: skip
    return ev_line("ex", "stated", said)


def evidence(sid, prop, pc):
    """What one property's block holds under its state and reason besides the link to how we
    read it: for an overridden cell, its stated state and what contradicts it, since that line
    changes the state; else nothing."""
    cell = S.CRIT["rows"][sid]["cells"][prop]
    if pc is None:
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


def shared_read(sid, order):
    """The sources-read list two or more properties share (the most shared one), printed once
    at the head of "How we read it"; None when no list is shared."""
    lists = [json.dumps(S.CRIT["rows"][sid]["cells"][p]["sources_read"], sort_keys=True)
             for p in order if S.CRIT["rows"][sid]["cells"][p]["sources_read"]]  # fmt: skip
    best = max(set(lists), key=lists.count, default=None)
    return json.loads(best) if best and lists.count(best) > 1 else None


def read_entries(sid, pc, order):
    """How we read each property (RFC-0009 S1 item 1, RFC-0016 ST-2, ST-8, OVR-7), by property
    id, in `order`: the deciding quote verbatim with its source at the pin (in a conflict, every
    quote with the state whose rule it meets), the sources read (one line per repository, linked
    at its commit, with the paths read; a list equal to an earlier property's names that
    property), and the controls the map ties to it with their outcome in every run read. A
    property with none of these has no entry."""
    out = {}
    common = shared_read(sid, order)
    if common:
        out["sources"] = sources_read(common)
    for prop in order:
        cell = S.CRIT["rows"][sid]["cells"][prop]
        quotes = deciding_quotes(sid, prop, cell)
        body = conflict_lines(cell) or "".join(
            ev_line("eqs", "quote", quote_html(q), block=True) for q in quotes
        )
        if cell["sources_read"] and cell["sources_read"] != common:
            body += sources_read(cell["sources_read"])
        if pc is not None:
            body += control_lines(pc, prop)
        if body:
            out[prop] = body
    return out


def how_we_read(entries):
    """How we read it, folded in a native `details` that opens with one press, with or without
    script: one entry per property of `read_entries`, its id `read-<property>` (the rose's
    "source" links; words.js opens the fold when a link or the address names an entry, and moves
    focus to it). With no entry, no fold."""
    names = {p["id"]: p["name"] for p in S.PROPS} | {"sources": "Every property"}
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
    """S1 item 2: the card's identity, a link to its file and its digest."""
    card = cfg["card"]
    digest = str(card["digest"]).removeprefix("sha256:")
    title = f"{card['configuration']} · {card['path']} · sha256 {digest}"
    return (f'<a href="{e(card["link"])}" title="{e(title)}">claim card, version '
            f'{e(card["card_version"])}{EXT}</a> · sha256 <code>{e(digest[:12])}</code>')  # fmt: skip


SCALAR = {None: "not stated", True: "yes", False: "no"}
# a card field's key as a label, where its plain form is not one (claim/1)
CARD_KEY = {"claim_class": "claim", "relation_formal": "formal statement", "not_hidden": "not hidden",
            "tokens_covered": "tokens covered", "forbidden_flags": "forbidden flags"}  # fmt: skip
# card enum values in words; any other value is printed as stored
CARD_VALUE = {"not_stated": "not stated", "segment_grid": "a grid of segments",
              "exact_match": "exact match"}  # fmt: skip
CARD_PATH_VALUE = {("coverage.phase", "both"): "both phases"}
CARD_SKIP = {"schema", "card_version", "sources"}  # the card line gives its version and digest


def card_key(k):
    return CARD_KEY.get(k, str(k).replace("_", " "))


def card_text(v):
    """Card or quote text as the system wrote it, no word changed (AGENTS.md rule 9): its inline
    code, strong and emphasis marks rendered; its straight double quotes curly, opening after a
    space or bracket and closing elsewhere (never inside code); a number's space before % or ‰
    one that never breaks."""
    codes = []

    def hold(m):
        codes.append(m[1])
        return f"\x00{len(codes) - 1}\x00"

    t = curly(re.sub(r"`([^`]+)`", hold, str(v)))
    t = re.sub(r"(\d) (?=[%‰])", "\\1\u202f", t)
    t = e(t)
    t = re.sub(r"\*\*([^*\s][^*]*?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*([^*\s][^*]*?)\*(?![\w*])", r"<em>\1</em>", t)
    return re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{e(codes[int(m[1])])}</code>", t)


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
                out.append(source_link(url, f"{' '.join(card_key(x) for x in rest.split('.'))}: "))
    return f'<p class="es">{"".join(out)}</p>' if out else ""


def has_source(path, sources):
    """True when the card's `sources` name the field at `path` or anything under it."""
    return any(k == path or k.startswith(path + ".") for k in sources)


def card_value(v, path="", sources=None):
    """One card value as stored, with its sources (the card's `sources` keyed by `path`): text,
    a link for a source URL, a list one item per line, a mapping as its own keys and values.
    A field's own sources follow a text value and head a mapping, above its items. A list's own
    sources head it when none of its items has a source; when some have, they follow each item
    that has none, so every item reads quote then source."""
    sources = sources or {}
    if isinstance(v, list):
        own = own_sources(path, {str(i) for i in range(len(v))}, sources)
        sourced = [has_source(f"{path}.{i}", sources) for i in range(len(v))]
        after = bool(own) and any(sourced)
        items = "".join(
            f"<li>{card_value(x, f'{path}.{i}', sources)}{own if after and not sourced[i] else ''}</li>"
            for i, x in enumerate(v)
        )
        return ("" if after else own) + (f'<ul class="cl">{items}</ul>' if v else "none")
    if isinstance(v, dict):
        own = own_sources(path, set(v), sources)
        rows = "".join(f"<div><dt>{e(card_key(k))}</dt><dd>{card_value(x, f'{path}.{k}', sources)}</dd></div>"
                       for k, x in v.items() if not (k == "switch" and x is None))  # fmt: skip
        return own + (f'<dl class="cn">{rows}</dl>' if v else "none")
    if isinstance(v, str) and v.startswith("https://"):
        text = source_link(v)
    elif v is None or isinstance(v, bool):
        text = SCALAR[v]
    elif (path, v) in CARD_PATH_VALUE:
        text = e(CARD_PATH_VALUE[(path, v)])
    elif isinstance(v, str) and v in CARD_VALUE:
        text = e(CARD_VALUE[v])
    else:
        text = card_text(v)
    return text + own_sources(path, set(), sources)


def card_full(cfg, sid):
    """S1 item 4: the claim card in full, each field with its sources, folded in a native
    `details` that opens with one press, with or without script."""
    body = cfg["card"]["body"]
    sources = body.get("sources") or {}
    rows = "".join(
        f"<div><dt>{e(card_key(k))}</dt><dd>{card_value(v, k, sources)}</dd></div>"
        for k, v in body.items()
        if k not in CARD_SKIP
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
            f"<li>{card_text(x['metric'])}: {card_text(x['value'])}"
            + (f'<p class="es">{source_link(x["source"])}</p>' if x.get("source") else "")
            + "</li>"
            for x in v
        )
        return (
            own_sources(field, {str(i) for i in range(len(v))}, sources)
            + f'<ul class="cl">{items}</ul>'
        )
    return card_value(v, field, sources)


def agreement_plate(cfg, label, setup=None):
    """RFC-0015 RC-5, RC-6: the agreement rate with a rerun by a weights holder, every label in
    view (S2, S3); a missing rate is a row of the gap's list (`gap_block`)."""
    f = cfg["agreement"]
    kv = []
    val = f'<span class="fig"><span class="n">{e(sig4(f["value"]))}</span></span>'
    if f.get("stats"):
        kv.append(("spread", e(spread_line(f, count=True))))
    kv += [(k, e(v)) for k, v in labels(f, cfg)]
    kv.append(("source", source_html(f["source"])))
    dl = "".join(f"<div><dt>{e(k)}</dt><dd>{v}</dd></div>" for k, v in kv)
    return (f'<div class="plate" id="agree-{e(cfg["configuration"])}-{e(cfg["workload"]["id"])}">'
            f'<p class="lbl">{e(label)}{setup_id(setup)}</p>'
            f'<p class="pv"{f' title="{e(said)}"' if (said := mean_words(f)) else ""}>{val}</p>'
            f"<dl>{dl}</dl></div>")  # fmt: skip


def setup_id(wid):
    """A workload id in a plate's label, in its own case, never broken."""
    return f' · <span class="nw lid">{e(wid)}</span>' if wid else ""


def stated(v):
    """False for a card field that is absent, empty or only "not stated" (claim/1)."""
    if isinstance(v, list):
        return any(stated(x) for x in v)
    return bool(v) and v not in ("not stated", "not_stated")


def gap_block(cfgs):
    """S1 item 5: after the card, its `quality_gap` and `residual` with the agreement rate
    (RFC-0015 RC-6), one list whose rows name themselves: the two fields as the card states
    them ("not stated" where it is silent, AGENTS.md rule 9; one row for both when it states
    neither), then a missing rate as one row of why, one per distinct reason, naming its setup
    only where reasons differ. A recorded rate is a plate beside the list, one per
    configuration."""
    body = cfgs[0]["card"]["body"]
    agree = [c["agreement"] for c in cfgs]
    missing = {why_words(f, c) for f, c in zip(agree, cfgs, strict=True) if f["value"] is None}
    if not stated(body.get("quality_gap")) and not stated(body.get("residual")):
        rows = [("quality gap, residual", "not stated")]
    else:
        rows = [("quality gap", gap_items(body, "quality_gap")),
                ("residual", gap_items(body, "residual"))]  # fmt: skip
    plates, seen = "", set()
    for c in cfgs:
        f = c["agreement"]
        if f["value"] is None:
            why = why_words(f, c)
            if why in seen:
                continue
            seen.add(why)
            label = "agreement with a rerun" + (
                f" · {c['workload']['id']}" if len(missing) > 1 else ""
            )
            rows.append((label, with_rule(readable(why[:1].lower() + why[1:].rstrip(".")))))
        else:
            setup = c["workload"]["id"] if len(cfgs) > 1 else None
            plates += agreement_plate(c, "Agreement with a rerun", setup)
    items = "".join(f"<div><dt>{e(k)}</dt><dd>{v}</dd></div>" for k, v in rows)
    if not plates:
        return f'<dl class="facts gapf gapone">{items}</dl>'
    return (f'<div class="gapblk"><dl class="facts gapf">{items}</dl>'
            f'<div class="agree">{plates}</div></div>')  # fmt: skip


def property_controls_of(cfgs):
    """The card row's control lists: computed once per card row (OVR-5 reads the same runs for
    every configuration of the card), so the first configuration's are the row's."""
    return next((c["property_controls"] for c in cfgs if c.get("property_controls")), None)
