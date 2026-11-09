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
    run_short,
    setup_diff,
    source_html,
    source_label,
    with_rule,
)
from .words import (
    CONTROL_WORDS,
    OUTCOME_SHORT,
    STATE_WORD,
    count_word,
    curly,
    e,
    labels,
    mean_words,
    note_words,
    sig4,
    spread_line,
    why_words,
)

# ------------------------------------------------------------------ one property's evidence

GITHUB_BLOB = re.compile(
    r"https://github\.com/([^/]+/[^/]+)/blob/([0-9a-f]{7,40})/([^#?]+)(?:\?[^#]*)?(?:#(L\d+(?:-L\d+)?))?"
)


def pin_words(repo, commit, where):
    """(link words, title) of a source at its pin: on the system page of the repository the card
    pins (`S.HOME`, named once in the facts' pinned row), path and lines alone; another
    repository by its name first ("zk-inference-results: REPRODUCE.md L1406"); off a system
    page, repository@commit first. The title holds repository@commit, path and lines; the link
    keeps the full pinned commit (AGENTS.md rule 11)."""
    full = f"{repo}@{commit[:8]} {where}".strip()
    if S.HOME and repo == S.HOME:
        return where, full
    if S.HOME:
        return f"{repo.rsplit('/', 1)[-1]}: {where}", full
    return full, full


def pin_label(url):
    """A source link's (words, title) (`pin_words`); a link that is no GitHub file at a commit
    keeps its path words (`source_label`)."""
    m = GITHUB_BLOB.match(url)
    if not m:
        return source_label(url), ""
    return pin_words(m[1], m[2], " ".join(x for x in (m[3], m[4]) if x))


def source_link(url, prefix="", label=None):
    """A small underlined link to a source at its pin (`.qsrc`); label: its words, where not
    the link's own path and lines."""
    words, title = pin_label(url)
    said = f' title="{e(title)}"' if title else ""
    return (f'<a class="qsrc" href="{e(url)}"{said}>'
            f"{path_html(prefix + (label or words), ext=True)}</a>")  # fmt: skip


def quote_source(q):
    """A quote's source at the pin: its path and lines linked at that commit (`pin_words`)."""
    words, title = pin_words(q["repo"], q["commit"],
                             " ".join(x for x in (q.get("path"), q.get("lines")) if x))  # fmt: skip
    return (
        f'<a class="qsrc" href="{e(q["url"])}" title="{e(title)}">{path_html(words, ext=True)}</a>'
    )


def one_source(urls):
    """One link for several sources that are consecutive lines of one file at one commit
    ("docs/figures.tsv L45-L47"), or None where they are not."""
    found = [GITHUB_BLOB.match(u or "") for u in urls]
    if len(found) < 2 or not all(m and m[4] for m in found):
        return None
    if len({(m[1], m[2], m[3]) for m in found}) != 1:
        return None
    spans = sorted(tuple(int(x) for x in re.findall(r"\d+", m[4])) for m in found)
    lo, hi = spans[0][0], spans[0][-1]
    for span in spans[1:]:
        if span[0] > hi + 1:
            return None
        hi = max(hi, span[-1])
    return source_link(f"{urls[0].split('#', 1)[0]}#L{lo}-L{hi}")


# a Markdown table row quoted on its own ("a | b | c"), or several, the first its table's head
TABLE_ROW = re.compile(r"^[^|\n]+(?: \| [^|\n]+)+$")


def quote_html(q):
    """The quote, verbatim (its line breaks kept, words.css `.eq p`), its inline marks rendered
    (`card_text`), with its source under it; a quoted table row as a one-row table, and a row
    quoted with its table's head (its first line, "L19, L32") under that head, so each cell
    says what it answers."""
    text = q["text"]
    rows = text.split("\n")
    if all(TABLE_ROW.match(r) for r in rows):
        head = ""
        if len(rows) > 1:
            head = "".join(f'<th scope="col">{card_text(x)}</th>' for x in rows[0].split(" | "))
            head, rows = f"<thead><tr>{head}</tr></thead>", rows[1:]
        body = "".join(
            "<tr>" + "".join(f"<td>{card_text(x)}</td>" for x in r.split(" | ")) + "</tr>"
            for r in rows
        )
        body = f'<table class="qrow">{head}<tbody>{body}</tbody></table>'
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


def run_list_words(runs, labelled, full=False):
    """Runs in words for a title: "2026-11-08 · 1, 2026-11-08 · 2 (1 request per batch); ..."
    by setup where the card row reads several; full: each run's whole id, as a screen reader
    hears it."""
    by = {}
    for r in runs:
        rid = r["run_id"] if full else run_short(r["run_id"])
        by.setdefault(setup_key(r["run_id"]) if labelled else "", []).append(rid)
    return "; ".join(", ".join(ids) + (f" ({k})" if k else "") for k, ids in by.items())


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


def outcome_words(o):
    """One control's outcome in one run, with the reason a stored note gives where it does not
    apply, was void or failed ("did not apply (the workload declares one precision)")."""
    w = OUTCOME_SHORT[o["outcome"]]
    if o.get("note") and o["outcome"] in ("not_applicable", "void", "error"):
        w += f" ({note_words(o['note'])})"
    return w


def control_lines(pc, prop):
    """RFC-0016 OVR-7: the controls the map ties to the property with their outcome in every run
    read, under one label. The runs that recorded tamper tests are named once, as a set linked
    to the tamper tests that list them ("in the 2 tamper-test runs", then "in them"); a line per
    outcome the controls share over that set ("C1 (changed output token), C2 (changed prompt
    token): rejected in the 2 tamper-test runs"), runs listed by date and ordinal only where outcomes
    differ between them; then one line for the runs that recorded none ("none run in the other
    7"), each run in its title and read aloud. Where no run read recorded any, one line says so
    ("not run in the 4 runs read"). A property no control tests has no line; nor does a card row
    that reads no run, which OVR-5 makes an error for review to catch."""
    entry = pc["properties"][prop]
    if not entry["mapped"] or not pc["runs"]:
        return ""
    labelled = len({setup_key(r["run_id"]) for r in pc["runs"]}) > 1
    tested = [r for r in pc["runs"] if r["controls"]]
    other = [r for r in pc["runs"] if not r["controls"]]
    said = {(o["control"], o["run_id"]): outcome_words(o) for o in entry["outcomes"]}
    names = {cid: control_label(cid) for cid in entry["mapped"]}
    lines = []
    if tested:
        n = len(tested)
        where = "the tamper-test run" if n == 1 else f"the {n} tamper-test runs"
        link = (f'<a class="psrc" href="#tamper" title="{e(run_list_words(tested, labelled))}">'
                f'{e(where)}<span class="sr"> ({e(run_list_words(tested, labelled, True))})'
                "</span></a>")  # fmt: skip
        shared, mixed = {}, []
        for cid in entry["mapped"]:
            words = [said[(cid, r["run_id"])] for r in tested]
            if len(set(words)) == 1:
                shared.setdefault(words[0], []).append(cid)
            else:
                mixed.append(cid)
        for i, (w, cids) in enumerate(shared.items()):
            head, _, why = w.partition(" (")
            them = link if not i else ("it" if n == 1 else "them")  # the set named once
            lines.append(f"{', '.join(names[c] for c in cids)}: {e(head)} in {them}"
                         + (f" ({flags_html(e(why))}" if why else ""))  # fmt: skip
        for cid in mixed:
            by = {}
            for r in tested:
                by.setdefault(said[(cid, r["run_id"])], []).append(r)
            parts = "; ".join(f"{flags_html(e(w))} in {run_refs(rs, False, labelled)}"
                              for w, rs in by.items())  # fmt: skip
            lines.append(f"{names[cid]}: {parts}")
    if other:
        runs = (f'<span class="nw" title="{e(run_list_words(other, labelled))}">{{count}}'
                f'<span class="sr"> ({e(run_list_words(other, labelled, True))})</span></span>')  # fmt: skip
        if tested:
            count = f"the other {len(other)}" if len(other) > 1 else "the other run"
            lines.append(f"none run in {runs.format(count=e(count))}")
        else:
            count = f"the {len(other)} runs read" if len(other) > 1 else "the run read"
            lines.append(f"{', '.join(names.values())}: not run in {runs.format(count=e(count))}")
    body = "".join(f'<span class="cg">{x}</span>' for x in lines)
    return ev_line("ec", "tamper tests", body)


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


# a list of same-shaped mappings printed as a table, by its path: its columns' heads where its
# source's own table names them (docs/statement.md L19 at SASH's pin: "#", "edge", "default",
# "turned off by"), and the key whose values open with the row's number, printed as its own column
CARD_TABLE_HEAD = {
    ("binding.edges", "state"): "default",
    ("binding.edges", "switch"): "turned off by",
}
CARD_TABLE_NUMBER = {"binding.edges": "edge"}
SCALARS = (str, int, float, bool, type(None))


def card_table(rows, path):
    """A list of mappings that share their keys, all scalar, as one table: its heads printed once
    (CARD_TABLE_HEAD), one row per item, "—" where an item gives no value; a key every item
    holds a source URL in is printed once under the table, as one link where the sources are
    consecutive lines of one file (`one_source`), else as a column. Values print as stored."""
    keys = list(rows[0])
    linked = [k for k in keys if all(str(r[k] or "").startswith("https://") for r in rows)]
    cols = [k for k in keys if k not in linked]
    numbered = CARD_TABLE_NUMBER.get(path)
    heads = (["#"] if numbered else []) + [
        CARD_TABLE_HEAD.get((path, k), card_key(k)) for k in cols
    ]
    under = ""
    for k in linked:
        joined = one_source([r[k] for r in rows])
        if joined:
            under += joined
        else:
            heads.append(card_key(k))
            cols.append(k)
    body = ""
    for r in rows:
        cells = []
        for k in cols:
            v = r[k]
            if k == numbered and isinstance(v, str) and (m := re.match(r"(\d+) (.+)$", v)):
                cells += [e(m[1]), card_text(m[2])]
                continue
            if v is None:
                cells.append("—")
            elif isinstance(v, str) and v.startswith("https://"):
                cells.append(source_link(v))
            elif isinstance(v, str):
                cells.append(breakable(card_text(v)) if v.startswith("--") else card_text(v))
            else:
                cells.append(e(SCALAR.get(v, v)))
        if numbered and len(cells) != len(heads):  # an item without its number: no table
            return None
        body += "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"
    head = "".join(f'<th scope="col">{e(h)}</th>' for h in heads)
    under = f'<p class="es">{under}</p>' if under else ""
    return (f'<div class="ctw"><table class="ctab"><thead><tr>{head}</tr></thead>'
            f"<tbody>{body}</tbody></table></div>{under}")  # fmt: skip


def breakable(flag):
    """A flag, in HTML, that breaks only after a hyphen between two words on a narrow screen,
    never inside its leading "--" ("--unsound-" "skip-" "residual-" "stream", each part whole)."""
    parts = re.split(r"(?<=[a-z0-9]-)(?=[a-z0-9])", flag)
    return "<wbr>".join(f'<span class="nw">{x}</span>' for x in parts)


def card_value(v, path="", sources=None):
    """One card value as stored, with its sources (the card's `sources` keyed by `path`): text,
    a link for a source URL, a list one item per line, a mapping as its own keys and values, a
    list of mappings that share their keys as one table (`card_table`). A field's own sources
    follow its value: after a text, after a mapping's last field. A list's own sources head it
    when none of its items has a source; when some have, they follow each item that has none,
    so every item reads quote then source."""
    sources = sources or {}
    if (isinstance(v, list) and len(v) > 1 and all(isinstance(x, dict) for x in v)
            and len({tuple(x) for x in v}) == 1
            and all(isinstance(y, SCALARS) for x in v for y in x.values())
            and not any(has_source(f"{path}.{i}", sources) for i in range(len(v)))):  # fmt: skip
        table = card_table(v, path)
        if table:
            return own_sources(path, {str(i) for i in range(len(v))}, sources) + table
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
        return (f'<dl class="cn">{rows}</dl>' if v else "none") + own
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


# a quality gap's value: its figure, then its labels in brackets, "; " between them
GAP_VALUE = re.compile(r"^(.*?) \((.*)\)$")
LEAD_END = {"the", "a", "an", "of", "to"}  # a lead never ends on these words


def gap_lead(metrics):
    """The words every metric starts with, whole words, never ending on an article or a
    preposition that belongs to the rest ("positions at which ... differs from"); 0 for none."""
    split = [m.split(" ") for m in metrics]
    n = 0
    while n < min(len(s) for s in split) - 1 and len({s[n] for s in split}) == 1:
        n += 1
    while n and split[0][n - 1] in LEAD_END:
        n -= 1
    return n


def gap_items(body, field):
    """`quality_gap` or `residual` as the card states it, "not stated" where the card holds no
    such field (AGENTS.md rule 9). Each quality gap item reads its metric and value with its
    source; where items share them, the words their metrics open with, the labels every value
    holds and a source of consecutive lines of one file are printed once (the lead, then one
    short item per comparison, then the shared labels and the source), every word kept."""
    v = body.get(field)
    if not v:
        return "not stated"
    sources = body.get("sources") or {}
    if field != "quality_gap":
        return card_value(v, field, sources)
    own = own_sources(field, {str(i) for i in range(len(v))}, sources)
    metrics = [str(x["metric"]) for x in v]
    values = [GAP_VALUE.match(str(x["value"])) for x in v]
    n = gap_lead(metrics) if len(v) > 1 else 0
    labels = [m[2].split("; ") if m else [] for m in values]
    shared = ([x for x in labels[0] if all(x in ls for ls in labels)]
              if len(v) > 1 and all(values) else [])  # fmt: skip
    joined = one_source([x.get("source") for x in v])
    items = ""
    for x, m, ls in zip(v, values, labels, strict=True):
        metric = " ".join(str(x["metric"]).split(" ")[n:])
        rest = [y for y in ls if y not in shared]
        value = (f"{m[1]} ({'; '.join(rest)})" if rest else m[1]) if m else str(x["value"])
        src = (
            "" if joined or not x.get("source") else f'<p class="es">{source_link(x["source"])}</p>'
        )
        items += f"<li>{card_text(metric)}: {card_text(value)}{src}</li>"
    lead = f'<p class="gl">{card_text(" ".join(metrics[0].split(" ")[:n]))}:</p>' if n else ""
    every = "both" if len(v) == 2 else f"all {count_word(len(v))}"
    tail = (f'<p class="gl">{every}: {card_text("; ".join(shared))}</p>'
            if shared else "")  # fmt: skip
    under = f'<p class="es">{joined}</p>' if joined else ""
    return f'{own}{lead}<ul class="cl{" gi" if n else ""}">{items}</ul>{tail}{under}'


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
