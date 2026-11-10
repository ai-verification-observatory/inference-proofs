"""Criteria rows as glyphs, the view's rows, words and labels, and one configuration's figures.

`glyph` turns a criteria row into the six cells the pages draw. The text helpers reword criteria
phrases (`PHRASES`), keep numbers with their units (`readable`) and turn RFC rule codes into links
(`with_rule`, which stops the build on a code that names no RFC). `cell_words` and `plate` print
one figure with every label (S2, S3); `runs_counts` says what a configuration with no
figure ran (S3, S7).
"""

import re

from . import state as S
from .words import (
    BITS_BASIS,
    PER_BIT_LIMIT,
    PER_GBIT,
    SCOPE_LINES,
    SCOPE_SHORT,
    STATE_WORD,
    e,
    labels,
    shown,
    spread_line,
    why_words,
)

# ------------------------------------------------------------------ the criteria's rows as glyphs


def glyph(rid):
    """One criteria row as the pages draw it: six states in slot order, each with its property,
    word, reason, quotes and the reason of the system's own statement outside the pin, which
    has no state and is never part of one (RFC-0016 SRC-3)."""
    row = S.CRIT["rows"][rid]
    cells = []
    for i, p in enumerate(S.PROPS):
        c = row["cells"][p["id"]]
        outside = (c.get("outside_pin") or {}).get("reason")
        cells.append({"n": i + 1, "prop": p["id"], "name": p["name"], "question": p["question"],
                      "state": c["state"], "word": STATE_WORD[c["state"]],
                      "reason": c.get("reason") or "", "quotes": c["quotes"],
                      "outside": outside})  # fmt: skip
    return {"states": [c["state"] for c in cells], "cells": cells}


def states_said(g, outside=False):
    """The six states in words (the pie's spoken name). outside: also what the system's own
    statement outside the pin says, which has no state and is not counted (RFC-0016 SRC-3);
    system pages only."""
    parts = []
    for c in g["cells"]:
        w = c["word"]
        if outside and c["outside"] is not None:
            w += f" (its own note outside the pin, not counted: {c['outside'].rstrip('.')})"
        parts.append(f"{c['name']}: {w}")
    return words("; ".join(parts) + ".")


def aria(g, name, outside=False):
    return f"{name}: {states_said(g, outside)}"


# ------------------------------------------------------------------ the view's rows


def name_of(rid):
    return S.V["facts"]["rows"][rid]["name"]


def upstream(cfg):
    """RFC-0009 S1: the pin is `upstream.commit` of the configuration's claim card."""
    return cfg["card"]["upstream"]


def row_id(cfg):
    """The row's id: the system's id, unless the system has more than one configuration."""
    same = [c for c in S.CONFIGS if c["system"] == cfg["system"]]
    if len(same) == 1:
        return cfg["system"]
    return f"{cfg['system']}--{cfg['configuration']}--{cfg['workload']['id']}"


def first_config(sid):
    return next(c for c in S.CONFIGS if c["system"] == sid)


def configs_of(sid):
    """The system's configurations in index order: one section each on its page."""
    return [c for c in S.CONFIGS if c["system"] == sid]


# ------------------------------------------------------------------ words and labels


def split_value(v):
    """Number, its unit (the next word), and any words after it."""
    m = re.match(r"^([\d,.]+)\s*(\S*)\s*(.*)$", v)
    return (m.group(1), m.group(2), m.group(3)) if m else (None, None, v)


def fig(v):
    n, u, rest = split_value(v)
    if n is None:
        return f'<span class="na word">{e(rest)}</span>'
    return (
        f'<span class="fig"><span class="n">{e(n)}</span>'
        + (f'<span class="u">{e(u)}</span>' if u else "")
        + (f'<span class="ux">{e(rest)}</span>' if rest else "")
        + "</span>"
    )


# the plates of a system page, and the figures of a reference (whose rows make no proof)
COLS = ["covers", "proof_size", "check_time", "overhead"]
# the three cost figures on one basis, per token covered per Gbit of active weights (PER_GBIT):
# prover time (D-SPAB-S), proof size (D-BPAB), check time (D-VSPAB)
PER_GBIT_COLS = ["per_bit", "size_bit", "check_bit"]
SYS_COLS = [*COLS, *PER_GBIT_COLS]
# the overview's figures (RFC-0009 S6): the overhead, then the three on the per-Gbit basis
BOARD = ["overhead", *PER_GBIT_COLS]
# each figure's full name: a plate's label, and the name a screen reader hears in a row's cell
HEAD = {
    "covers": "One proof covers",
    "proof_size": "Proof size",
    "check_time": "Check time",
    "overhead": "Overhead vs production serving",
    "per_bit": f"Proving time {PER_GBIT}",
    "size_bit": f"Proof size {PER_GBIT}",
    "check_bit": f"Check time {PER_GBIT}",
}
# the overview's column heads, under one line each group shares (BOARD_GROUPS)
BOARD_HEAD = {"overhead": "Overhead", "per_bit": "Proving time", "size_bit": "Proof size",
              "check_bit": "Check time"}  # fmt: skip
BOARD_GROUPS = [(["overhead"], "vs production serving"), (PER_GBIT_COLS, PER_GBIT)]
# the stored statistic behind each column (iproofs.site.view.FIGURES, PER_BIT, PER_BIT_SIZE)
METRIC = {
    "covers": "tokens_covered_per_proof",
    "proof_size": "proof_bytes",
    "check_time": "verify_seconds",
    "overhead": "overhead_vs_production_prove.steady",
    "per_bit": "seconds_per_active_weight_bit_token_prove.steady",
    "size_bit": "proof_bytes_per_active_weight_bit_token",
    "check_bit": "verify_seconds_per_active_weight_bit_token",
}


def metric_of(cfg, col):
    """The stored statistic behind one column of a configuration: the overhead column shows the
    row's headline overhead, which release code names (`overhead_metric`: the steady figure, or
    the warm figure for a system with no steady scope, RFC-0004 INV-DERIVE-11); prover time per
    active weight bit the steady figure, or the session figure where it is null (`per_bit_metric`)."""
    if col == "overhead":
        return cfg.get("overhead_metric") or METRIC[col]
    if col == "per_bit":
        return cfg.get("per_bit_metric") or METRIC[col]
    return METRIC[col]


def bits_words(cfg):
    """The weight width D-SPAB-S divides by, as the workload records it (RFC-0003 WB-1 to WB-5)."""
    wb = cfg["workload"]["precision"].get("weight_bits") or {}
    if not wb:
        return "weight bits not recorded"
    bits = f"{wb['bits']:.4g} bits" if wb.get("bits") is not None else "bits"
    part = ", part of the weights" if wb.get("covers") == "part" else ""
    return f"{bits} per active weight, {BITS_BASIS.get(wb.get('basis'), wb.get('basis'))}{part}"


# how each order reads aloud
SORT_WORDS = {
    "system": {"asc": "A to Z", "desc": "Z to A"},
    "covers": {"asc": "fewer positions first", "desc": "more positions first"},
    "proof_size": {"asc": "small to large", "desc": "large to small"},
    "check_time": {"asc": "short to long", "desc": "long to short"},
    "overhead": {
        "asc": "closer to production serving first",
        "desc": "further from production serving first",
    },
    "per_bit": {"asc": "less proving time first", "desc": "more proving time first"},
    "size_bit": {"asc": "small to large", "desc": "large to small"},
    "check_bit": {"asc": "short to long", "desc": "long to short"},
}
# More numbers on a system page, in this order: the stored statistic and its row label
MORE = [
    ("rate_prove.session", "Proving rate"),
    ("cost_per_1k_tokens_prove.session", "GPU cost per 1,000 positions"),
    ("commit_seconds", "Commit once"),
    ("verify_host_memory_peak_anon", "Checker memory"),
    ("prove_gpu_memory_peak", "GPU memory"),
]
# A reference row makes no proof (RFC-0015 REF-2): its cells say so, in these words
REF_CELLS = {
    "covers": (
        "Same as the system",
        "Same token count as the system it runs beside (RFC-0015 REF-3).",
    ),
    "proof_size": ("No proof", "This row makes no proof (RFC-0015 REF-2)."),
    "check_time": ("Does not apply", "This row makes no proof (RFC-0015 REF-2)."),
}
REF_OVERHEAD = {
    "serve": (
        "Baseline",
        "Production serving is the baseline of the overhead ratio, whether or not it has run.",
    ),
    "recompute": ("Does not apply", "A rerun is not the baseline."),
}
REF_BASELINE = "by definition"  # the line under production serving's Baseline, as its siblings

# Criteria phrases the site words differently, for a reader who has not read the RFCs. Each must
# still occur in the criteria or facts file, so a change there shows up here.
PHRASES = {
    # one name per reference: the pages call it a rerun
    "recompute needs them": "a rerun needs them",
    "a checker holding the weights recomputes": "a checker holding the weights reruns it",
    "or not copied yet": "or we have not recorded it yet",
    # the criteria page speaks of the configuration, not of the file's rows
    "the configuration the row reads": "the configuration run",
}

# RFC rule codes ("(RFC-0015 NM-1)") in text: a link to the RFC on the page, never the bare code
RFC_RULE = re.compile(r"\s*\((RFC-(\d{4})(?:\s[A-Z]+-\d+)?)\)")


def sentence_case(text):
    """Each sentence starts with a capital, as fragments joined with ". " sometimes do not.
    Only prose: a short label ("per proof", "1 token checked") or an id keeps its own case."""
    if len(text.split()) < 4 or not text[:1].islower():
        return re.sub(r"(\. )([a-z])", lambda m: m[1] + m[2].upper(), text)
    text = text[:1].upper() + text[1:]
    return re.sub(r"(\. )([a-z])", lambda m: m[1] + m[2].upper(), text)


def words(text):
    """Criteria and facts text as the site prints it: phrases reworded."""
    text = str(text)
    for k, v in PHRASES.items():
        text = text.replace(k, v)
    return text


def no_rule(text):
    """Text without its RFC rule codes (where a link cannot go, as inside another link or a title)."""
    return RFC_RULE.sub("", text)


def with_rule(text):
    """Escaped text whose RFC rule codes become a small link to the RFC."""
    out, last = [], 0
    for m in RFC_RULE.finditer(text):
        out.append(e(text[last : m.start()]))
        f = S.RFC_FILES.get(m[2])
        assert f, f"no rfcs/{m[2]}-*.md for {m[1]}"
        end = m.end()
        if text[end : end + 1] in (
            ".",
            ";",
            ",",
        ):  # the sentence ends before the link, not after it
            out.append(text[end])
            end += 1
        out.append(
            f' <a class="rule" href="{e(S.REPO_URL)}/blob/{S.RFC_REF}/rfcs/{f}" title="{e(m[1])}">rule<span class="sr"> {e(m[1])}</span>{EXT}</a>'
        )
        last = end
    out.append(e(text[last:]))
    return "".join(out)


def readable(text):
    """A printed figure label: whole numbers stay with their units, the spread reads in words."""
    text = text.replace(" · ", "\u00a0· ")  # a separator never starts a line
    # a count word stays with what it counts ("one H100"), a statistic with its number ("sd 0")
    text = re.sub(r"\b(one|two|three|four|five|six|seven|eight|nine|ten) (?=\w)", "\\1\u00a0", text)
    text = re.sub(r"\b(mean|sd) (?=[\d.])", "\\1\u00a0", text)
    # a number stays with its unit, not with the "to" of a range
    return re.sub(r"(\d) (?=(?!to )[A-Za-zµ%×])", "\\1\u00a0", text)


EXT = '<span aria-hidden="true">\u00a0↗</span>'  # an outside link's arrow: not read aloud, never alone on a line


def path_html(text, ext=False):
    """A source path that breaks only after a "/" or a " · ", never inside a part, and whose
    separator ends a line rather than starts one. ext: end it with the outside link's arrow,
    held to the last part so the arrow never wraps onto a line of its own."""
    segs = re.split("\u00a0· | · ", text)
    out = []
    for i, sg in enumerate(segs):
        subs = re.split(r"(?<=/)", sg)
        sep = "\u00a0·" if i < len(segs) - 1 else ""
        out.append(
            "<wbr>".join(
                f'<span class="seg">{e(s)}{sep if j == len(subs) - 1 else ""}</span>'
                for j, s in enumerate(subs)
            )
        )
    html = " ".join(out)
    if ext:
        head, _, last = html.rpartition('<span class="seg">')
        html = f'{head}<span class="nw"><span class="seg">{last}{EXT}</span>'
    return html


def keep(text):
    """Escaped text whose hyphenated words (ids, dates, model names) never break at a hyphen; a
    "/" inside one may still break."""
    out, last = [], 0
    for m in re.finditer(r"\S*\w-\w\S*", text):
        out.append(e(text[last : m.start()]))
        out.append(
            "<wbr>".join(f'<span class="nw">{e(s)}</span>' for s in re.split(r"(?<=/)", m[0]))
        )
        last = m.end()
    out.append(e(text[last:]))
    return "".join(out)


def link_or_text(text, href):
    """A source as a link when it has one; otherwise text, its rule codes as links."""
    if href:
        return f'<a href="{e(href)}">{path_html(no_rule(text))}{EXT}</a>'
    return with_rule(text)


def source_label(url):
    """A link's words: the file path and lines a GitHub blob URL names."""
    m = re.match(
        r"https://github\.com/[^/]+/[^/]+/blob/[0-9a-f]+/([^#?]+)(?:\?[^#]*)?(?:#(L\d+(?:-L\d+)?))?",
        url,
    )
    return f"{m[1]} {m[2]}" if m and m[2] else (m[1] if m else url)


def record_html(path, words=None):
    """A record of the release (a run's `run.json` or `controls.json`) as a link to the file.
    words: the link's text, when not the path (a run id)."""
    return f'<a href="{e(blob(path))}">{path_html(words or path)}{EXT}</a>'


def blob(path):
    """A file of this repository, at the commit the site links (RFC-0009 S1, #320 plan §1.1)."""
    return f"{S.REPO_URL}/blob/{S.LINK_REF}/{path}"


# ------------------------------------------------------------------ one configuration's figures


def cell_words(cfg, col):
    """(value html, lines, title, measured) for one overview figure of a configuration. The line
    under it is its scope in one word where the rows of its column differ in it (steady, session,
    session vs warm), else none; every label rides in its title, and the plate it links holds
    them all in view (S2, S3)."""
    if cfg["kind"] == "reference":
        word, line = (REF_OVERHEAD[cfg["reference_role"]] if col == "overhead"
                      else REF_CELLS[col])  # fmt: skip
        if col == "overhead" and cfg["reference_role"] == "serve":  # the baseline's own note
            return f'<span class="na">{e(word)}</span>', [REF_BASELINE], no_rule(line), False
        return f'<span class="na">{e(word)}</span>', [], no_rule(line), False
    f = cfg["figures"][metric_of(cfg, col)]
    if f["value"] is None:
        return '<span class="na">No value</span>', [], no_rule(why_words(f, cfg)), False
    value = shown(f["value"], f["unit"])
    said = [*(f"{k}: {v}" for k, v in labels(f, cfg))]
    lines = []
    if col == "overhead" and f["metric"] in SCOPE_LINES:  # RFC-0009 S1: its scope in view
        lines = [SCOPE_SHORT[f["metric"]]]
        said[0] = f"scope: {SCOPE_LINES[f['metric']]}"  # both sides' scope (INV-DERIVE-11)
        if pairs := pairs_words(f):
            said.append(f"pairs: {pairs}")
        brief = (cfg.get("overhead_words") or {}).get("brief")
        if brief:
            said.append(f"ran: {brief}")
    if (
        col == "per_bit"
    ):  # steady, or session where the steady figure is null (RFC-0004 INV-SCOPE-1)
        lines = [SCOPE_SHORT[f["scope"]]]
    # the basis and its limit ride in the title (RFC-0004 INV-DERIVE-7)
    value_said = f"{value} {PER_GBIT}" if col in PER_GBIT_COLS else value
    title = " · ".join([value_said, *said, f"source: {f['source']}",
                        *([f"spread: {spread_line(f)}"] if f.get("stats") else [])])  # fmt: skip
    if col in PER_GBIT_COLS:
        title += f" · weight bits: {bits_words(cfg)} · {PER_BIT_LIMIT}"
    return fig(value), lines, title, True


def pairs_words(f):
    """An overhead's runs and range: its prover runs times its serving runs, and the least and
    greatest ratio over those pairs; "" when the figure holds none."""
    pairs = f.get("pairs") or {}
    if pairs.get("n_system") is None:
        return ""
    ns, nv = pairs["n_system"], pairs["n_serving"]
    out = f"{ns} prover run{'s' if ns != 1 else ''} × {nv} serving run{'s' if nv != 1 else ''}"
    if pairs.get("min") is not None:
        out += f", {shown(pairs['min'], 'ratio')} to {shown(pairs['max'], 'ratio')}"
    return out


def spread_kv(f):
    """A plate's spread: n, range, mean and sd; an overhead's runs and range over its pairs."""
    if f.get("stats"):
        return [("spread", spread_line(f), None)]
    pairs = pairs_words(f)
    return [("pairs", pairs, None)] if pairs else []


def value_link(cfg, col, href, who=""):
    """A figure on the overview row: a link to the figure's own plate, its scope in one word
    under it where it has one; its labels ride in the title."""
    inner, lines, title, measured = cell_words(cfg, col)
    title = sentence_case(readable(title) if measured else title)
    sub = "".join(f"<span>{keep(ln)}</span>" for ln in lines if ln)
    name = f'<span class="sr">, {e(who)}</span>' if who else ""
    return (
        f'<a class="val" href="{e(href)}" title="{e(title)}">'
        f'<span class="lbl">{e(HEAD[col])}{name}</span><span class="vm">{inner}</span>'
        + (f'<span class="sub">{sub}</span>' if sub else "")
        + "</a>"
    )


def workload_link(cfg):
    return cfg["workload"]["id"], blob(cfg["workload"]["record"])


def plate(cfg, col, pid=""):
    """One figure's plate, every label in view (S2, S3); pid: an id prefix, so an overview
    figure can link to its own plate."""
    kv = []
    if cfg["kind"] == "reference":
        word, line = (REF_OVERHEAD[cfg["reference_role"]] if col == "overhead"
                      else REF_CELLS[col])  # fmt: skip
        val = f'<span class="na">{e(word)}</span>'
        kv.append(("note", line, None))
    else:
        f = cfg["figures"][metric_of(cfg, col)]
        if f["value"] is None:
            val = '<span class="na">No value</span>'
            kv += [("workload", *workload_link(cfg)), ("why", why_words(f, cfg), None)]
            if col == "overhead" and f["metric"] in SCOPE_LINES:  # INV-DERIVE-11, warm
                kv.append(("scope", SCOPE_LINES[f["metric"]], None))
        else:
            val = fig(shown(f["value"], f["unit"]))
            kv += spread_kv(f)
            kv += [(k, v, None) for k, v in labels(f, cfg)]
            kv.append(("workload", *workload_link(cfg)))
            words = cfg.get("overhead_words") if col == "overhead" else None
            for key in ("conditions", "precision", "high"):  # RFC-0004 INV-DERIVE-9
                if words and words.get(key):
                    kv.append((key, words[key], None))
        if col in PER_GBIT_COLS:  # RFC-0004 INV-DERIVE-7: the width, its note and the limit
            wb = cfg["workload"]["precision"].get("weight_bits") or {}
            kv.append(("weight bits", bits_words(cfg), wb.get("source")))
            if wb.get("note"):
                kv.append(("note", wb["note"], None))
            kv.append(("limit", PER_BIT_LIMIT, None))
        steady = cfg["figures"].get(METRIC["overhead"]) if col == "overhead" else None
        if steady and steady["metric"] != f["metric"] and steady["value"] is None:
            kv.append(("steady state", why_words(steady, cfg), None))  # why the session figure
        if f["recorded"]:
            kv.append(("source", f["source"], None))
    dl = "".join(
        f"<div><dt>{e(k)}</dt><dd>{source_html(v) if k == 'source' else link_or_text(readable(v), href)}</dd></div>"
        for k, v, href in kv
    )
    return (
        f'<div class="plate"{f' id="{e(pid)}{col}"' if pid else ""} data-col="{col}"><p class="lbl">{e(HEAD[col])}</p>'
        f'<p class="pv">{val}</p><dl>{dl}</dl></div>'
    )


def source_html(pointer):
    """A figure's record in the release index, as text until the index is published (#146)."""
    file, _, frag = pointer.partition("#")
    return path_html(file) + "<wbr>" + path_html("#" + frag)


def has_figures(cfg):
    """False for a configuration whose kept runs all failed: it holds no statistic."""
    return any(f["recorded"] for f in cfg["figures"].values())


def runs_counts(cfg):
    """A configuration whose kept runs all failed holds no statistic: its counts, whether it has
    fewer completed runs than a release needs (S3, S7)."""
    runs = cfg["runs"]
    parts = [f"{len(runs['completed'])} completed, {len(runs['failed'])} failed"]
    if cfg["insufficient_repetitions"]:
        parts.append("below minimum repetitions")
    return " · ".join(parts)
