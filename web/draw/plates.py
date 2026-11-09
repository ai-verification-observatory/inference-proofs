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
    GRADE_WORD,
    PER_BIT_LIMIT,
    PER_GBIT,
    SCOPE_LINES,
    SCOPE_SHORT,
    STATE_WORD,
    TIER_WORD,
    boundary_words,
    e,
    gpu_words,
    labels,
    scope_words,
    shown,
    spread_line,
    title_spread,
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


def setup_parts(cfg):
    """A setup as a reader names it: model, prompt, batch and GPUs."""
    sh = cfg["workload"]["shape"]
    b = sh["batch_size"]
    return [S.MODEL_NAME[cfg["workload"]["model"]["digest"]],
            f"{sh['prompt_tokens']:,}-token prompt",
            f"{b:,} request{'s' if b != 1 else ''} per batch", gpu_words(cfg)]  # fmt: skip


def setup_diff(cfg):
    """The words of a setup that differ from its system's other setups ("24 requests per
    batch"); every word for a system with one setup; its workload id where no word differs."""
    parts = setup_parts(cfg)
    others = [setup_parts(c) for c in configs_of(cfg["system"]) if row_id(c) != row_id(cfg)]
    if not others:
        return parts
    diff = [x for i, x in enumerate(parts) if any(o[i] != x for o in others)]
    return diff or [cfg["workload"]["id"]]


def config_of_run(rid):
    """The rendered configuration a run belongs to, or None (a run of an earlier release)."""
    return next((c for c in S.CONFIGS if rid in c["runs"]["records"]), None)


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
        + (f'<span class="u{" x" if u == "×" else ""}">{e(u)}</span>' if u else "")
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
    part = ", for part of the active weights" if wb.get("covers") == "part" else ""
    return f"{bits} per active weight, {BITS_BASIS.get(wb.get('basis'), wb.get('basis'))}{part}"


# how each order reads aloud
SORT_WORDS = {
    "system": {"asc": "A to Z", "desc": "Z to A"},
    "covers": {"asc": "fewer tokens first", "desc": "more tokens first"},
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
    ("cost_per_1k_tokens_prove.session", "GPU cost per 1M tokens"),
    ("commit_seconds", "Preparing the model (once)"),
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
        "Production serving is the baseline of the overhead ratio.",
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
    "the row is a reference": "for a reference (production serving)",
}

# RFC rule codes ("(RFC-0015 NM-1)", "(RFC-0006 C5)", "(RFC-0016 Q10)") in text: a link to the
# RFC on the page, never the bare code
RFC_RULE = re.compile(r"\s*\((RFC-(\d{4})(?:\s[A-Z]+-?\d+)?)\)")


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


# an outside link's arrow: not read aloud, not underlined (an inline block), held to the word
# before it (path_html ext, or a nowrap span)
EXT = '<span class="xa" aria-hidden="true">\u00a0↗</span>'


def path_html(text, ext=False):
    """A source path that breaks only after a "/" or "_", before a ".", or after a " · ", never
    inside a word, and whose separator ends a line rather than starts one. ext: end it with the
    outside link's arrow, held to the last part so the arrow never wraps onto a line of its own."""
    segs = re.split("\u00a0· | · ", text)
    out = []
    for i, sg in enumerate(segs):
        subs = [s for s in re.split(r"(?<=[/_])|(?=\.[A-Za-z])", sg) if s]
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
        return f'<a href="{e(href)}">{path_html(no_rule(text), ext=True)}</a>'
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
    return f'<a href="{e(blob(path))}">{path_html(words or path, ext=True)}</a>'


RUN_ID = re.compile(r"(\d{4}-\d{2}-\d{2})-.*-(\d+)$")


def run_ref(rid, record):
    """A run by its date and ordinal ("2026-11-08 · 2"), its full id read aloud and in the
    link's title, linked to its record once the release is published; an id of another shape
    whole."""
    m = RUN_ID.match(rid)
    if not m:
        return record_html(record, rid) if record else path_html(rid)
    short = (
        f'<span aria-hidden="true">{m[1]}\u00a0·\u00a0{m[2]}</span><span class="sr">{e(rid)}</span>'
    )
    if not record:
        return f'<span class="nw" title="{e(rid)}">{short}</span>'
    return (f'<a class="run" href="{e(blob(record))}" title="{e(rid)}">'
            f'<span class="nw">{short}{EXT}</span></a>')  # fmt: skip


def blob(path):
    """A file of this repository, at the commit the site links (RFC-0009 S1, #320 plan §1.1)."""
    return f"{S.REPO_URL}/blob/{S.LINK_REF}/{path}"


# ------------------------------------------------------------------ one configuration's figures


def cell_words(cfg, col):
    """(value html, lines, title, measured) for one overview figure of a configuration. The line
    under it is its scope in one word (steady, with start-up, the checker's threads); its title
    holds the value, its scope, its runs and range, grade and evidence, and the plate it links
    holds every label with its record (S2, S3)."""
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
    parts = [f"{value} {PER_GBIT}" if col in PER_GBIT_COLS else value]
    lines = []
    if col == "overhead" and f["metric"] in SCOPE_LINES:  # RFC-0009 S1: its scope in view
        lines = [SCOPE_SHORT[f["metric"]]]
        parts.append(SCOPE_LINES[f["metric"]])  # both sides' scope (INV-DERIVE-11)
        if pairs := pairs_words(f):
            parts.append(pairs)
        brief = (cfg.get("overhead_words") or {}).get("brief")
        if brief:
            parts.append(brief)
    else:
        if f["scope"] is not None:
            parts.append(scope_words(f, cfg))
            short = SCOPE_SHORT.get(f["scope"])
            cpus = cfg["verifier"]["logical_cpus"]
            if short and col in ("per_bit", "check_bit") and ("{cpus}" not in short or cpus):
                lines = [short.format(cpus=cpus)]  # steady, with start-up, the checker's threads
        if spread := title_spread(f):
            parts.append(spread)
    parts += [GRADE_WORD[f["grade"]], f"evidence: {TIER_WORD[f['tier']]}"]
    return fig(value), lines, " · ".join(parts), True


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


class Html(str):
    """A plate row's value already in HTML (its runs linked), printed as it is."""


# why a completed run joins no pair of an overhead (iproofs.site.view.JOIN_WHY), in words
JOIN_WHY_WORDS = {
    "first_proof_boundary": "{boundary}, so {they} no overhead",
    "short_steady": "steady scope under 60 s, so {they} no overhead",
    "sizing_capture": "a sizing capture, so {they} no overhead",
    "other_prompts": "replayed the prompts of a run in no pair, so {they} none",
    None: "in no pair",
}


def left_words(cfg, runs):
    """The runs of one side an overhead leaves out, grouped by why, in words for a title:
    "2026-11-08 · 1, 2026-11-08 · 2: steady window from the first proof (runs before
    2026-11-09), so they join no overhead"."""
    by = {}
    for x in runs:
        by.setdefault(x["why"], []).append(x["run_id"])
    out = []
    for why, ids in by.items():
        short = ", ".join(" · ".join(m.groups()) if (m := RUN_ID.match(r)) else r for r in ids)
        they = "it joins" if len(ids) == 1 else "they join"
        said = JOIN_WHY_WORDS[why].format(boundary=boundary_words(cfg), they=they)
        out.append(f"{short}: {said}")
    return "Left out: " + "; ".join(out)


def pairs_html(cfg, f):
    """An overhead's pairs on its plate: the runs joined on each side, read from its source
    inputs, by date and ordinal linked to their records, then the range over the pairs; each
    side's count holds in its title the runs of its configuration left out and why."""
    joined = (cfg.get("overhead_runs") or {}).get(f["metric"])
    pairs = f.get("pairs") or {}
    if not joined or pairs.get("n_system") is None:
        return Html(e(readable(pairs_words(f))))
    sides = []
    for side, n, noun in (("system", pairs["n_system"], "prover run"),
                          ("serving", pairs["n_serving"], "serving run")):  # fmt: skip
        runs = joined[side]
        if len(runs) != n:
            raise RuntimeError(f"{f['metric']}: {n} {side} runs counted, {len(runs)} in its inputs")
        count = f"{n}\u00a0{noun}{'s' if n != 1 else ''}"
        left = [x for x in joined["left"] if x["side"] == side]
        if left:
            count = f'<span class="nw" title="{e(left_words(cfg, left))}">{count}</span>'
        refs = ", ".join(run_ref(r["run_id"], r["record"]) for r in runs)
        sides.append(f"{count} ({refs})")
    out = " × ".join(sides)
    if pairs.get("min") is not None:
        out += f", {e(shown(pairs['min'], 'ratio'))} to {e(shown(pairs['max'], 'ratio'))}"
    return Html(out)


def spread_kv(f):
    """A plate's spread: range, mean and sd (the setup's runs line names n); an overhead's runs
    and range over its pairs."""
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


def limit_words():
    """RFC-0004 INV-DERIVE-7's limit, its prompt lengths those of the release's workloads (by
    model), computed from their records, never typed."""
    by_model = {}
    for c in S.CONFIGS:
        name = S.MODEL_NAME[c["workload"]["model"]["digest"]]
        by_model.setdefault(name, set()).add(c["workload"]["shape"]["prompt_tokens"])
    differ = {m: sorted(n) for m, n in by_model.items() if len(n) > 1}
    if differ:
        prompts = "; ".join(
            f"the {m} workloads of this release have "
            + ", ".join(f"{n:,}" for n in ns[:-1])
            + f" and {ns[-1]:,} prompt tokens"
            for m, ns in sorted(differ.items())
        )
    else:
        lengths = sorted({n for ns in by_model.values() for n in ns})
        prompts = (f"every workload of this release has a {lengths[0]:,}-token prompt"
                   if len(lengths) == 1 else
                   "each model's workloads in this release share one prompt length")  # fmt: skip
    return PER_BIT_LIMIT.format(prompts=prompts)


SHARED = ("workload", "grade", "evidence")  # labels a setup's figures may share (setup_shared)


def figure_rows(cfg, f):
    """A measured figure's own labels (S2, S3): its spread or pairs, and its scope when it is
    timed; then grade and evidence, which a setup's figures usually share."""
    kv = list(spread_kv(f))
    for k, v in labels(f, cfg):
        if k == "scope" and f["scope"] is None:
            continue  # not a timed number: no scope row
        kv.append((k, v, None))
    return kv


def setup_figures(cfg):
    """Every figure a configuration's section prints: its plates' and its more-numbers rows'."""
    return [cfg["figures"][metric_of(cfg, c)] for c in (*COLS, *PER_GBIT_COLS)] + [
        cfg["figures"][m] for m, _ in MORE
    ]


def setup_shared(cfg):
    """{label: value} the setup states once over its figures (S2): the workload (with its
    division and profile), and the grade and evidence where every measured figure has the same;
    `source` is the pointer's common prefix in the release index."""
    shared = {"workload": None}
    measured = [f for f in setup_figures(cfg) if f["value"] is not None]
    for key in ("grade", "evidence"):
        values = {dict(labels(f, cfg))[key] for f in measured}
        if len(values) == 1:
            shared[key] = values.pop()
    shared["source"] = f"{S.V['release']['index']}#/configurations/{cfg['position']}/statistics/"
    return shared


def setup_dl(cfg, shared):
    """The labels a setup's figures share, once, under its runs line."""
    wid, href = workload_link(cfg)
    rows = [("workload", f'<a href="{e(href)}">{path_html(wid, ext=True)}</a> · '
                         f'<span title="division">{e(cfg["workload"]["division"])}</span> · '
                         f'<span title="profile">{keep(cfg["profile"])}</span>')]  # fmt: skip
    rows += [(k, e(shared[k])) for k in ("grade", "evidence") if k in shared]
    rows.append(("source", source_html(shared["source"])))
    return (
        '<dl class="tlab setl">'
        + "".join(f"<div><dt>{e(k)}</dt><dd>{v}</dd></div>" for k, v in rows)
        + "</dl>"
    )


def source_key(f, shared):
    """A figure's record: the key under its setup's pointer prefix, or the whole pointer."""
    prefix = (shared or {}).get("source")
    if prefix and f["source"].startswith(prefix):
        return f["source"][len(prefix) :]
    return f["source"]


def source_words(f, shared=None):
    """A figure's record as a label reads it: its key, with the factor a reading unit applies
    to the stored value where the key names another unit (a cost stored per 1k tokens, shown
    per 1M: "cost_per_1k_tokens_prove.session × 1,000")."""
    key = source_key(f, shared)
    return f"{key} × 1,000" if f["unit"] == "USD/1k_token" else key


def plate(cfg, col, pid="", shared=None):
    """One figure's plate (S2, S3): its value and the labels it does not share with the rest of
    its setup (shared: setup_shared, printed once above the plates); pid: an id prefix, so an
    overview figure can link to its own plate."""
    shared = shared or {}
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
            if "workload" not in shared:
                kv.append(("workload", *workload_link(cfg)))
            kv.append(("why", why_words(f, cfg), None))
            if col == "overhead" and f["metric"] in SCOPE_LINES:  # INV-DERIVE-11, warm
                kv.append(("scope", SCOPE_LINES[f["metric"]], None))
        else:
            val = fig(shown(f["value"], f["unit"]))
            kv += [(k, pairs_html(cfg, f) if k == "pairs" else v, h)
                   for k, v, h in figure_rows(cfg, f) if k not in shared]  # fmt: skip
            if "workload" not in shared:
                kv.append(("workload", *workload_link(cfg)))
        if f["recorded"]:
            kv.append(("source", source_words(f, shared), None))
    dl = "".join(
        f"<div><dt>{e(k)}</dt><dd>{v if isinstance(v, Html) else path_html(v) if k == 'source' else link_or_text(readable(v), href)}</dd></div>"
        for k, v, href in kv
    )
    return (
        f'<div class="plate"{f' id="{e(pid)}{col}"' if pid else ""} data-col="{col}"><p class="lbl">{e(HEAD[col])}</p>'
        f'<p class="pv">{val}</p><dl>{dl}</dl></div>'
    )


def dates_html(html):
    """A date (2026-11-08) in text that never breaks at its hyphens."""
    return re.sub(r"\b\d{4}-\d{2}-\d{2}\b", lambda m: f'<span class="nw">{m[0]}</span>', html)


def flags_html(html):
    """Engine flags (`--max-model-len 1025`) as code that never breaks inside."""
    return re.sub(
        r"--[a-z][a-z0-9-]*(?:[ \u00a0]\d+)?", lambda m: f'<code class="nw">{m[0]}</code>', html
    )


def overhead_notes(cfg):
    """RFC-0004 INV-DERIVE-9, -11: what qualifies the headline overhead, from the release's
    records, full width under the setup's plates: its conditions, the precision note, the
    figure at high load, and, for a warm figure, why the steady one is null."""
    if cfg["kind"] != "prover":
        return ""
    f = cfg["figures"][metric_of(cfg, "overhead")]
    words = cfg.get("overhead_words") or {}
    rows = [(label, flags_html(with_rule(readable(words[key]))))
            for key, label in (("conditions", "conditions"), ("precision", "precision"),
                               ("high", "at high load")) if words.get(key)]  # fmt: skip
    steady = cfg["figures"].get(METRIC["overhead"])
    if steady and steady["metric"] != f["metric"] and steady["value"] is None:
        rows.append(("steady state", with_rule(readable(why_words(steady, cfg)))))
    if not rows:
        return ""
    items = "".join(f"<div><dt>{e(k)}</dt><dd>{v}</dd></div>" for k, v in rows)
    return f'<dl class="tlab notes" aria-label="{e(HEAD["overhead"])}: conditions">{items}</dl>'


def per_gbit_basis(cfg):
    """RFC-0004 INV-DERIVE-7, once under the three per-Gbit plates: the weight width they divide
    by with its source, its note, and the limit."""
    wb = cfg["workload"]["precision"].get("weight_bits") or {}
    rows = [("weight bits", link_or_text(readable(bits_words(cfg)), wb.get("source")))]
    if wb.get("note"):
        rows.append(("note", flags_html(dates_html(with_rule(readable(wb["note"]))))))
    rows.append(("limit", e(limit_words())))
    items = "".join(f"<div><dt>{e(k)}</dt><dd>{v}</dd></div>" for k, v in rows)
    return f'<dl class="tlab notes basis" aria-label="{e(PER_GBIT)}">{items}</dl>'


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
