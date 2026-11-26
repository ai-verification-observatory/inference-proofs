"""The system pages (RFC-0018 SI-3), the checks page and the 404.

A system page holds one row of the board: its band; the five criteria, one row each (its grade
in words and its track, what it misses one click down, `petal.py`); the statement; the six checks
as a ruled table (state, cause, evidence behind a disclosure); the cost, fidelity beside the
model's controls and the sessions.
"""

import math
import re

from . import state as S
from .chrome import (
    CHECKS_PAGE,
    LEARN_PAGE,
    LEVEL_ANCHOR,
    MANDATE_PAGE,
    PROVED_RATE,
    card_current,
    cards_record,
    counted,
    fig_words,
    footer,
    further,
    gpu_name,
    has,
    header,
    how_computed,
    lead_figure,
    link,
    not_split,
    page,
    parts_of,
    pnav,
    proving_figure,
    rate_pair,
    rung_of,
    share_words,
)
from .glossary import term
from .hexagon import glyph_svg
from .ladder import (
    BARE,
    BINDING_GAP,
    NOT_TESTED,
    PARTNERS_ID,
    RATE_ANCHOR,
    agree_title,
    defined,
    fig_html,
    filled,
    further_line,
    how_link,
    href,
    multiple_html,
    name_of,
    nobreak,
    part_term,
    pct,
    proved_words,
    proving_html,
    rate_html,
    request_words,
    serving_words,
    standing_html,
    states,
    steady_line,
    sub_line,
    whole_line,
    whole_note,
)
from .petal import chip, control_name, criteria_section, quote_links, state_word
from .plots import (
    PLOT_BESIDE,
    axis_svg,
    decade_words,
    dot_plot,
    fid_svg,
    hbar,
    lin_x,
    log_extent,
    log_x,
)
from .words import (
    ADAPTER_SPLIT,
    BASIS_BITS,
    BASIS_READING,
    CARD_ERRATUM,
    CAUSE_WORD,
    CHECK_CAUSE_LEAD,
    CHECK_CAUSE_WORD,
    CHECK_DECIDE,
    CHECK_FAILED,
    CHECK_HELD,
    CHECK_MORE,
    CHECK_NAME,
    CHECK_PLAIN,
    CHECKS_DESC,
    COPY_WORD,
    DTYPE_BITS,
    FID_HEAD,
    FID_KIND,
    FID_WHO,
    FIDELITY_AGAINST,
    FIGURE_ANCHOR,
    FIGURE_HEAD,
    FIGURE_NAME,
    FORMAT_HEAD,
    FORMAT_WORD,
    FULL_LOAD_WORD,
    FURTHER,
    FURTHER_PARTS_HEAD,
    FURTHER_TERM,
    KEPT_CHANGE,
    KEPT_HEAD,
    KEPT_MEANS,
    KEPT_TIME,
    KIND_TERM,
    KNOW_COLS,
    KNOW_HEAD,
    KNOW_LINES,
    KNOW_WHERE,
    KNOW_WORD,
    LIM_CEILING,
    LIM_COPY,
    LIM_ENGINES,
    LIM_LLAMA,
    LIM_ORIGINAL,
    LIM_PART,
    LIM_PROMPTS,
    LIM_VLLM,
    M_COL,
    M_HEAD,
    M_NAME,
    MANDATE,
    MANDATE_BELIEF,
    MANDATE_CORRECTIONS,
    MANDATE_CORRECTIONS_IN,
    MANDATE_DESC,
    MANDATE_LEVEL,
    MANDATE_LEVEL_IN,
    MANDATE_LEVEL_LINK,
    MANDATE_MEMBERS_IN,
    MANDATE_MODELS,
    MEMORY_HEAD,
    NEXT_BY,
    NEXT_HEAD,
    NO_SPLIT,
    NO_STEADY_WORD,
    NOT_RUN_LEAD,
    NOT_RUN_RULE,
    NOTION_HEAD,
    NULL_WORD,
    OF_WHICH,
    ONE_TIME_MARK,
    ORDER_RULE,
    P_ABOVE,
    P_FLOOR,
    PART_WORD,
    PARTS_HEAD,
    PETAL_CAUSE_DRAW,
    PETAL_CAUSE_RULE,
    PETAL_MORE,
    PETAL_NAME,
    PETAL_NOT_GRADED,
    PETAL_PLAIN,
    PETAL_PROTECTS,
    PETAL_QUESTION,
    PETAL_RULE,
    PETAL_STEPS_FOOT,
    PETAL_TERM,
    PREFIX,
    PROOFS_HEAD,
    PROVED_HEAD,
    PROVED_LINK,
    RATE_PER,
    RATE_PROVED,
    READ_AS,
    READING_RULE,
    REASON_LINK,
    RECORD_WORD,
    REPLY_TOKENS_HEAD,
    ROUTES,
    SCALE_LOG,
    SCOPE_BOUND_HEAD,
    SCOPE_CARD_HEAD,
    SCOPE_CARD_WORD,
    SCOPE_COL_WORD,
    SCOPE_ROW_WORD,
    SCOPE_SHORT,
    SCOPE_TERMS,
    SCOPE_TESTED,
    SCOPE_VALUE_WORD,
    SCOPE_WORD,
    SE3A_NONE,
    SE3A_ROW,
    SE3B_NONE,
    SE3B_ROW,
    SEP,
    STATE_WORD,
    STATED_SECURITY,
    STATEMENT_WORD,
    STEP_WORD,
    TF_AGREE,
    TF_BOTH,
    TF_FAILED,
    TF_INTERVAL,
    TF_KL,
    TF_KL_SUB,
    TF_KL_TITLE,
    TF_NOT_PROVED,
    TF_PROVED,
    TF_PROVED_MEAN,
    TF_PROVED_SPLIT,
    TF_SUB,
    TF_TEST,
    TF_TESTS_ON,
    TIER_WORD,
    TRIAL_NO_PROOF,
    TRIAL_REFUSED,
    TRIAL_WHAT,
    TRIALS_HEAD,
    UTIL_HEAD,
    architecture,
    beside_unit,
    curly,
    e,
    figure_rules,
    kl_head,
    number,
    quoted,
    range_words,
    sig,
    step_key,
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


def run_path(system, run_id, name="run.json"):
    """A file of a run's directory (RFC-0009 §Storage), by its path in the repository; None where
    the board is not a release's (a preview), so no run directory stands behind it."""
    rel = S.V["release"]
    if rel is None or not str(rel["board"]).startswith("releases/"):
        return None
    return f"results/{rel['id']}/{system}/{run_id}/{name}"


# the system whose runs are the serving baselines (inputs.engine reads its pin)
SERVING_SYSTEM = "ref-serve"


def run_link(row, run_id, system=None):
    """A run by date and ordinal (its id in the title), linked to its record."""
    path = run_path(system or row["system"], run_id)
    if path is None:
        return f'<span class="rid"><span title="{e(run_id)}">{e(where(run_id))}</span></span>'
    return f'<a class="rid" href="{e(link(path))}" title="{e(run_id)}">{e(where(run_id))}</a>'


# a counted run's records beside its run.json (RFC-0009 §Storage): what it ran with, and what
# the harness logged
RUN_RECORDS = (("manifest", "manifest.json"), ("log", "logs/harness.jsonl"))


def run_records(row, run_id):
    """A run linked to its record, then to its manifest and its harness log, each piece kept
    whole (the file's path in its title)."""
    paths = [(w, run_path(row["system"], run_id, name)) for w, name in RUN_RECORDS]
    return kept(run_link(row, run_id), *(f'<a class="rid" href="{e(link(p))}" title="{e(p)}">'
                                         f"{e(w)}</a>" for w, p in paths if p))  # fmt: skip


def run_words(path):
    """The run a record lies under, by date and ordinal ("2026-11-11 · 1"); None outside a run."""
    for part in path.split("/"):
        m = RUN_ID.match(part)
        if m:
            return f"{m[1]} \u00b7 {m[2]}"
    return None


def record_words(path, ptrs=()):
    """A record in words: its run, then what the file holds (RECORD_WORD), or, for JSON Pointers
    into it, their count by the entries' kind ("2 controls"). No file name, path or entry id: those
    stand in the link's title."""
    word = RECORD_WORD.get(path.rsplit("/", 1)[-1], path.rsplit("/", 1)[-1])
    if ptrs:
        word = counted_words(len(ptrs), ptrs[0].split("/")[0].removesuffix("s"))
    run = run_words(path)
    return f"{run}: {word}" if run else word


def evidence_links(paths):
    """A check's records, one link per file, labelled in words (`record_words`), the file's path
    and the entries a JSON Pointer names in its title; a directory's files (a trace per proof
    makes many) as one link to the directory with their count. A list: its length is the count
    the check's summary prints."""
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
            said = (", ".join(record_words(p).rsplit(": ", 1)[-1] for p in whole)
                    if len(whole) <= 3 else f"{len(whole):,} files")  # fmt: skip
            run = run_words(d)
            out.append(f'<a class="ev" href="{e(S.REPO_URL)}/tree/{e(S.LINK_REF)}/{e(d)}" '
                       f'title="{e(d)}">{e(f"{run}: {said}" if run else said)}</a>')  # fmt: skip
        for path in (p for p in paths_in if len(whole) <= 1 or p not in whole):
            ptrs = [x for x in files[path] if x]
            href = link(path) + (f"#/{ptrs[0]}" if len(ptrs) == 1 else "")
            title = path + (" #/" + ", /".join(ptrs) if ptrs else "")
            out.append(f'<a class="ev" href="{e(href)}" title="{e(title)}">'
                       f"{e(record_words(path, ptrs))}</a>")  # fmt: skip
    return out


def stacked(heads, rows, titles=None):
    """A ruled table whose cells carry their column's head (data-l), so a phone stacks each row
    as labelled lines instead of hiding columns past the edge. rows: lists of cell html; titles:
    a head's title, by the head."""
    titles = titles or {}

    def th(h):
        title = f' title="{e(titles[h])}"' if h in titles else ""
        return f'<th scope="col"{title}>{e(h)}</th>'

    ths = "".join(th(h) for h in heads)
    trs = "".join(
        "<tr>" + "".join(f'<td data-l="{e(h)}">{c}</td>' for h, c in zip(heads, r, strict=True))
        + "</tr>" for r in rows
    )  # fmt: skip
    return f'<table class="rt stk"><thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table>'


def scope_card_html(formal):
    """The scope card (MC-6, amended 2026-11-15): for soundness, zero knowledge and completeness,
    the publisher's bound verbatim and linked, then what it states of the protocol, the verifier
    run and the prover run, each word linked to its first quote. The two cells that ask a
    property of the wrong party print "does not apply". It sets no state."""
    if formal is None:
        return ""

    # each cell carries its column's head (`data-h`): a phone stacks the card, one block a row
    def cell(c, col):
        word = e(SCOPE_VALUE_WORD[c["value"]])
        if c["quotes"]:
            word = f'<a class="sv" href="{e(c["quotes"][0]["url"])}">{word}</a>'
        return f'<td class="{e(c["value"])}" data-h="{e(SCOPE_COL_WORD[col])}">{word}</td>'

    def bound(r):
        b = (formal.get("scope_bounds") or {}).get(r)
        h = f' data-h="{e(SCOPE_BOUND_HEAD)}"'
        if not b:
            return f'<td class="not_stated"{h}>{e(SCOPE_VALUE_WORD["not_stated"])}</td>'
        text = quoted(b["text"])
        if b["quotes"]:
            text = f'<a class="sv" href="{e(b["quotes"][0]["url"])}">{text}</a>'
        return f'<td class="sb"{h}>{text}</td>'

    card = formal["scope_card"]
    heads = f'<th scope="col">{e(SCOPE_BOUND_HEAD)}</th>' + "".join(
        f'<th scope="col">{e(w)}</th>' for w in SCOPE_COL_WORD.values())  # fmt: skip
    body = "".join(
        f'<tr><th scope="row">{e(SCOPE_ROW_WORD[r])}</th>{bound(r)}'
        + "".join(cell(card[r][c], c) for c in SCOPE_COL_WORD) + "</tr>"
        for r in SCOPE_ROW_WORD
    )  # fmt: skip
    return (f'<p class="pvh">{e(SCOPE_CARD_HEAD)}</p>'
            f'<table class="scard"><caption class="sr">Scope card</caption>'
            f'<thead><tr><td><span class="sr">What</span></td>{heads}</tr></thead>'
            f"<tbody>{body}</tbody></table>")  # fmt: skip


def scope_head_html(row):
    """Under the five criteria (the paragraph after MC-7, amended 2026-11-17, owner decision):
    soundness, zero knowledge and completeness on one line, in that order, each linked to its
    definition, with the petal that grades it or our Run check's count of accepted replies; the
    publisher's stated security, verbatim with its link, and the scope card one click down."""
    n = row["honest_accepted"]
    parts = []
    for slug_, name, pid in SCOPE_TERMS:
        term = f'<a class="df" href="/glossary#{slug_}">{e(name)}</a>'
        if pid is not None:  # graded by its criterion above; the glossary says which
            continue
        run = f'<a href="{CHECKS_PAGE}#run">{e(CHECK_NAME["run"])} check</a>'
        said = e(SCOPE_TESTED.format(n=f"{n:,}", run="\x00")).replace(" of ", "\u00a0of\u00a0")
        said = said.replace("\x00", run)
        if row["incomplete"]:
            said += e(f", {counted_words(len(row['incomplete']), 'incomplete session')} "
                      "not counted")  # fmt: skip
        parts.append(f'<span class="szt">{term}: {said}</span>')
    line = f'<p class="szc">{"".join(parts)}</p>'
    sec = row.get("security") or {}
    security = ""
    if sec.get("words"):
        src = str(sec.get("source") or "")
        key = src.partition("#")[2]
        url = S.V["systems"][row["system"]].get("sources", {}).get(key) or (
            src if src.startswith("https://") else None)  # fmt: skip
        words = quoted(sec["words"])
        words = f'<a href="{e(url)}">{words}</a>' if url else words
        notion = (row.get("statement") or {}).get("notion") or []
        if notion:  # the publisher's own name for the notion, verbatim (SI-3)
            words += f" {e(NOTION_HEAD)}: " + quote_links(notion)
        security = f"<div><dt>{e(STATED_SECURITY)}</dt><dd>{words}</dd></div>"
    formal = {p["id"]: p for p in row["glyph"]}["machine_checked"]["formal"]
    card = scope_card_html(formal)
    held = [w for w, part in ((STATED_SECURITY, security), (SCOPE_CARD_WORD, card)) if part]
    more = ""
    if held:
        security = f'<dl class="pf">{security}</dl>' if security else ""
        more = (f'<details class="more"><summary>{e(", ".join(held))}</summary>{security}{card}'
                "</details>")  # fmt: skip
    return f'<div class="psb">{line}{more}</div>'


def counted_words(k, one):
    """A count in words: "1 quote", "16 quotes"."""
    return f"{k:,} {one}" if k == 1 else f"{k:,} {one}s"


def criteria_block(row):
    """The Criteria section (amended 2026-11-22, owner decision): what each criterion needs for
    Met, has, misses and where to check (`petal.criteria_section`), then soundness, zero
    knowledge and completeness."""
    return criteria_section(row, scope_head_html(row))


# RFC-0018 SI-3 (amended 2026-11-15): the Statement block's rows, in the view's order
STATEMENT_HEAD = {"commit_record": "From our commit record", "request": "From the request",
                  "proof": "From the proof", "decoding": "Decoding rule",
                  "unchecked": "Checked by no call", "architecture": "Architecture"}  # fmt: skip


def statement_given(row, st, rid):  # noqa: PLR0911 (one return per row)
    """What the verifier the row runs is given, for one row of the Statement block, from the
    records: the files `commit` wrote (the manifests), the request's sizes, the proof's files
    the verifier reads (`system.yaml`), the level's decoding rule; the architecture's word."""
    req = S.V["request"]
    if rid == "commit_record":
        files = ", ".join(st["verifier_files"])
        return ("the commitment" + (f" and the files <code>commit</code> wrote: <code>{e(files)}"
                                    "</code>" if files else ""))  # fmt: skip
    if rid == "request":
        said = f"the prompt, {st['prompt_tokens']:,} token ids"
        if st["reply"] == "record":
            said += f", and the {st['output_tokens']:,}-token reply from our record"
        return e(said)
    if rid == "proof":
        kinds = ", ".join(f"{k['count']:,} × {k['kind']}" if k["count"] > 1 else k["kind"]
                          for k in st["proof_read"])  # fmt: skip
        said = (f"{st['proof_files']:,} {'file' if st['proof_files'] == 1 else 'files'}: "
                f"<code>{e(kinds)}</code>") if kinds else "its files"  # fmt: skip
        if st["reply"] == "proof":
            said += ". The verifier is not given the reply and reads it from the proof"
        if st.get("proof_caveat"):
            cav = st["proof_caveat"]
            said += f". {e(cav[:1].upper() + cav[1:])}"
        return said
    if rid == "decoding":
        return e(f"{req['decoding']}, at every reply position")
    if rid == "architecture":
        if st["architecture_visible"]:
            return e(f"visible: {st['architecture_visible']}")
        return e(SCOPE_VALUE_WORD["not_stated"])
    return ""


def statement_html(row):
    """SI-3 (amended 2026-11-15): what the verifier the row runs is given, and from where (our
    commit record, the request, the proof), the decoding rule, what no call checks and what of
    the architecture a proof shows. Each row: what the records show is given, then the claim
    card's words on it, each linked to the publisher's line, or "not stated". It sets no state."""
    st = row.get("statement")
    if not st:
        return f'<p class="none">{e(SCOPE_VALUE_WORD["not_stated"])}</p>'
    rows = []
    ls = row.get("level_statement")
    if ls is not None:  # SI-4a: what an accept says, the publisher's words beside it
        key = "read" if ls["reading"] else "stated" if ls["stated"] else "not"
        quotes = "".join(f'<p class="stc">{e(q["text"])} <a href="{e(q["url"])}">source</a></p>'
                         for q in ls["quotes"])  # fmt: skip
        rows.append(
            [e(ACCEPT_HEAD), e(STATEMENT_WORD[key]), quotes or e(SCOPE_VALUE_WORD["not_stated"])]
        )
    for r in st["rows"]:
        said = (f'<span class="na">{e(SCOPE_VALUE_WORD["not_stated"])}</span>' if r["said"] is None
                else "".join(f'<p class="stc">{e(q["text"])} <a href="{e(q["url"])}" '
                             f'title="{e(q["field"])}">source</a></p>' for q in r["said"]))  # fmt: skip
        rows.append([e(STATEMENT_HEAD[r["id"]]), statement_given(row, st, r["id"]), said])
    fix = st.get("erratum")
    erratum = ""
    if fix:  # the card is kept byte for byte (the runs record its digest): said beside its link
        fields = " and ".join(f"<code>{e(f)}</code>" for f in fix["fields"])
        q = fix["level_1"]
        erratum = (f'<p class="cn">{CARD_ERRATUM.format(fields=fields, says=e(fix["says"]))} '
                   f'<a class="qt" href="{e(q["url"])}">\u201c{e(q["quote"])}\u201d</a></p>')  # fmt: skip
    return erratum + stacked(["What", "Given", "Claim card"], rows)


def note_parts(note):
    """A check's note as (the internal id that leads it, "P1" or a run's request, or ""; its
    words)."""
    head, sep, tail = note.partition(": ")
    if not (sep and " " not in head):
        return "", note
    return head, tail


def decide_html(c, note):
    """What decides a check that is not decided, and who acts (CHECK_DECIDE), where the table
    names it; the session from the run the check's note opens with."""
    if c["state"] != "undecided":
        return ""
    found = CHECK_DECIDE.get((c["id"], c["cause"])) or CHECK_DECIDE.get((None, c["cause"]))
    if not found:
        return ""
    text, by = found
    session = run_words(note_parts(note or "")[0]) if "{session}" in text else None
    if "{session}" in text and session is None:
        return ""
    said = text.format(session=session)
    return (f'<p class="pnx"><span class="k">{e(NEXT_HEAD["decide"])}:</span> {e(said)}. '
            f"{e(NEXT_BY[(by,)])}</p>")  # fmt: skip


def sentences(parts):
    """Words of a labelled line, one sentence per part: the first stays in lower case after its
    label, as the block's other lines do; each later one opens with a capital."""
    return ". ".join([parts[0], *(s[:1].upper() + s[1:] for s in parts[1:])])


def trials_html(trials):
    """What a check's counted trials sent (RFC-0018 CH-1c), from the board: per control and
    position, the trials, the inputs they sent and how many were refused, so three trials of one
    changed input never read as three inputs."""
    if not trials:
        return ""

    def one(t):
        n, inputs = t["trials"], t["inputs"]
        sent = ("the same input each time" if inputs == 1 and n > 1
                else "a new input each time" if inputs == n
                else f"{inputs:,} inputs")  # fmt: skip
        none, by = t.get("no_proof", 0), t["refused"] - t.get("no_proof", 0)
        how = [f"in {none:,}, {TRIAL_NO_PROOF}"] if none else []
        how += [f"{by:,} {TRIAL_REFUSED}"] if by or not none else []
        return f"{TRIAL_WHAT[(t['control'], t['position'])]}: {n:,} trials, {sent}, and " \
            + ", and ".join(how)  # fmt: skip

    words = sentences([one(t) for t in trials]) + "."
    return f'<p class="cn"><span class="k">{e(TRIALS_HEAD)}</span> {e(words)}</p>'


TRIAL_OTHER = (
    "machine_checked"  # the view's place of another verifier's trial (iproofs.site.system)
)


def kept_html(row, place):
    """The row's stored verifier trials printed at `place` (a check's id, or Machine-checked),
    each from its record: what its changed calls did and how many the verifier refused, beside
    its honest calls accepted, with its record. A trial sets no state (RFC-0008 §Verifier
    trials). Only a trial of another of the publisher's verifiers prints its times: they are what
    no counted session took (the Verifying line); the row's own verifier is timed there."""
    out = []
    for t in row.get("trials_kept") or ():
        if t["place"] != place:
            continue
        who = t["verifier"] if place == TRIAL_OTHER else "the verifier"
        said = [f"{who} accepted {t['accepted']:,} of "
                f"{counted_words(t['honest'], 'honest proof')}"
                + (f" ({t['counted']:,} from counted sessions)" if t["counted"] < t["honest"]
                   else "")]  # fmt: skip
        said += [f"{KEPT_CHANGE.get(k, k)}: {t['changed_rejected']:,} of {t['changed']:,} refused"
                 for k in t["changes"]]  # fmt: skip
        if place == TRIAL_OTHER and t["seconds_min"] is not None:
            lo, hi = f"{t['seconds_min']:,.0f}", f"{t['seconds_max']:,.0f}"
            span = lo if lo == hi else f"{lo} to {hi}"
            said.append(f"{span}\u00a0s per proof, {KEPT_TIME}, n\u00a0=\u00a0"
                        f"{t['honest'] - t['no_verdict']:,}")  # fmt: skip
        means = " ".join(KEPT_MEANS[k] for k in t["changes"]
                         if k in KEPT_MEANS and t["changed_rejected"] == t["changed"])  # fmt: skip
        words = sentences(said) + "." + (f" {means}" if means else "")
        rec = (
            f'<a class="ev" href="{e(link(t["record"]))}" title="{e(t["record"])}">trial record</a>'
        )
        out.append(f'<p class="cn"><span class="k">{e(KEPT_HEAD)}</span> '
                   f"{e(words)} {rec}</p>")  # fmt: skip
    return "".join(out)


def plain(v, unit, record, said="", missing="none"):
    """A number the board stores without labels (a session's value, a mean prefix), in its
    column's unit, the labels its block knows (`said`: scope, n) and its record in its title;
    `missing` in its place when there is none."""
    if v is None:
        return f'<span class="na">{e(missing)}</span>'
    n, u = (sig(v), unit) if unit in ("tokens", "positions") else number(v, unit)
    title = f"{said}; record: {record}" if said else f"record: {record}"
    return (f'<span class="fig" title="{e(title)}"><span class="n">{e(n)}</span>'
            f'<span class="u">{e(u)}</span></span>')  # fmt: skip


def steady_cell(s, at, said):
    """A session's steady state in one cell (CO-3): its m, or "none" with the cause under it."""
    cell = plain(s["m"], GPU_S, f"{at}/m", said)
    if not s["steady"]:
        cell += f'<span class="sub">{e(s["cause"] or "no")}</span>'
    return cell


RULE_ID = re.compile(r"\b[A-Z]{2}-\d+[a-z]?\b")  # a rule's id in words ("SE-3a")


def whole_ids(text):
    """Escaped words with each rule id kept on one line (a line never breaks at its hyphen)."""
    return RULE_ID.sub(lambda m: f'<span class="nw">{m[0]}</span>', text)


def replaced_why(s):
    """A replaced session's reason (SE-3a) without its closing clause, where that clause names
    only what the row's Slot and Replaced by cells print ("; slot 1 counts <its run>")."""
    tail = f"; slot {s['slot']} counts {s['replaced_by']}"
    return s["cause"].removesuffix(tail)


def sessions_html(row, counted_table=True):
    """SE-3: each counted session (slot, run, m or why there is none, session cost per reply),
    then every incomplete session with its exit code and last line (AGENTS.md rule 5), then each
    replaced session (SE-3a), its reason said once over the table where the sessions share it,
    then each run RFC-0014 keeps out of the release with its reasons (SE-3b)."""
    rec = row["record"]
    gen = any(s.get("generation_gpu_seconds_per_reply") is not None for s in row["sessions"])
    # release groups: a column where the sessions differ, else said once over the table
    groups = {len(s["groups"]) for s in row["sessions"]}
    steady, whole = (f"scope: {SCOPE_WORD[k]}" for k in ("prove.steady", "whole_wall"))

    def cells(k, s):
        at = f"{rec}/sessions/{k}"
        g = s.get("generation_gpu_seconds_per_reply")  # CO-7: the generation phase, part of the
        return [  # whole session (and of m, where the session has one)
            str(s["slot"]),
            run_link(row, s["run_id"]),
            steady_cell(s, at, steady),
            plain(s["session"], GPU_S, f"{at}/session", whole),
            *([plain(g, GPU_S, f"{at}/generation_gpu_seconds_per_reply", whole)] if gen else []),
            *([f"{len(s['groups']):,}"] if len(groups) > 1 else []),
        ]

    of_gen = f"{OF_WHICH} {PART_WORD['generation']}".capitalize()
    heads = ["Slot", "Run", M_COL, "Session", *([of_gen] if gen else []),
             *(["Release groups"] if len(groups) > 1 else [])]  # fmt: skip
    once = (f'<p class="rb"><span class="k">Release groups</span> {next(iter(groups)):,} in each '
            "session</p>" if len(groups) == 1 else "")  # fmt: skip
    # D1: what a session, a slot and a whole session are, each linked to its definition, once
    lead = (
        f'<p class="rd">Each {term("session", "Session")} is one run from a cold start on '
        f"one {term('slot', 'Slot')}'s prompts, and one counts per slot. Session: its GPU "
        f"time per reply over the {term('whole session', 'Whole session')}. {e(M_COL)}: the "
        f"same after its first release group, in {term('steady state', 'Steady state')}.</p>"
    )
    out = ""
    if counted_table:
        out = (lead + once + stacked(heads, [cells(k, s) for k, s in enumerate(row["sessions"])],
                                     {M_COL: M_NAME})
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
        whys = [replaced_why(s) for s in row["replaced"]]
        once = len(set(whys)) == 1
        rows = [
            [
                str(s["slot"]) if s["slot"] is not None else "",
                run_link(row, s["run_id"]),
                run_link(row, s["replaced_by"]),
                *([] if once else [e(why)]),
            ]
            for s, why in zip(row["replaced"], whys, strict=True)
        ]
        lead = (
            f'<p class="rb"><span class="k">Why</span> <span>{whole_ids(e(whys[0]))}</span></p>'
            if once
            else ""
        )
        out += (
            '<h3 class="sub-h">Replaced sessions</h3>'
            + lead
            + stacked(["Slot", "Run", "Replaced by", *([] if once else ["Why"])], rows)
        )
    if row.get("ineligible"):  # SE-3b: kept out by RFC-0014, in no figure and no check
        rows = [
            [
                str(s["slot"]) if s["slot"] is not None else "",
                run_link(row, s["run_id"]),
                e(SEP.join(s["words"])),
            ]
            for s in row["ineligible"]
        ]
        out += '<h3 class="sub-h">Ineligible sessions</h3>' + stacked(["Slot", "Run", "Why"], rows)
    return out


def kept(*pieces):
    """A line's pieces (markup), each kept whole: a line too long breaks between two, the dot that
    parts them opening the next line, never left at a line's end."""
    head, *rest = pieces
    return f'<span class="nw">{head}</span>' + "".join(
        f' <span class="nw">\u00b7\u00a0{p}</span>' for p in rest
    )


# CO-7: a GPU time's two parts, where the system generates in a phase of its own, drawn in this
# order (the part that is not generation first, in paper)
GPU_PARTS = {
    "steady_gpu_seconds_per_reply": (("proving", "steady_proving_gpu_seconds_per_reply"),
                                     ("generation", "steady_generation_gpu_seconds_per_reply")),
    "session_gpu_seconds_per_reply": (
        ("commit_and_proving", "session_commit_and_proving_gpu_seconds_per_reply"),
        ("generation", "session_generation_gpu_seconds_per_reply")),
}  # fmt: skip


def cost_sub(f, n, head="", own=False):
    """The line under a Cost figure, where the block's Proving line says the whole sessions and
    their n once (`n`, the counted sessions): nothing for a figure that shares both, else what
    differs (a steady or a verify scope, another n), a scope its `head` already names left out
    ("Verify time" over no "verify"). A figure the Proving line does not cover (`own`: verify
    time, proof size) prints its n even where it is the block's. None (the figure's own line)
    with no n."""
    if n is None or not has(f):
        return None
    short = SCOPE_SHORT[f["scope"]]
    block = SCOPE_SHORT["prove.session"] if further() else "session"  # the block's line says it
    said = [short] if short not in ("", "session", block) and short not in head.lower() else []
    count = f["n"] if f["n"] is not None else n
    if own or count != n:
        said.append(f"n\u00a0=\u00a0{count}")
    if spread := range_words(f):  # AGENTS.md rule 5: a mean prints its range
        said.append(spread)
    return SEP.join(said)


def serving_fig(f, line=True):
    """The serving baseline's figure: timed at full load (CO-4), so its title names that scope;
    with the Serving line above it (`line`) nothing under it, else "full load"."""
    if not has(f):
        return fig_html(f)
    return fig_html({**f, "scope": "serving"}, sub=BARE if line else FULL_LOAD_WORD)


def gpu_parts(figs, key):
    """A GPU time's two parts (CO-7) as (part word, figure), where the board holds both; else
    None."""
    parts = [(w, figs.get(k)) for w, k in GPU_PARTS.get(key, ())]
    return parts if parts and all(has(p) for _, p in parts) else None


def cost_bars(row, drawn):
    """CO-7 drawn: a GPU time per reply that splits in two (the steady m or the whole session,
    where the system generates in a phase of its own) as one bar of its two parts, on one scale,
    this row's own (one model). Each line: its name, its bar, its labelled figure and its parts'
    figures. A GPU time with no parts is a figure of the sheet under the bars (`cost_html`): a
    bar of one part says no more than its figure. `drawn`: (name, figure, key, title)."""
    figs, n = row["figures"], counted(row)
    if not drawn:
        return ""
    top = max(f["value"] for _, f, _, _ in drawn)
    lines = []
    for name, f, key, title in drawn:
        parts = gpu_parts(figs, key)
        segs = [(p["value"], c) for (_, p), c in zip(parts, ("bp", "bg"), strict=True)]
        # each part under its whole, by its name alone (CO-7)
        cps = "".join(f'<span class="cpt {c}"><span class="cpl">{e(PART_WORD[w])}</span>'
                      f"{fig_html(p, n, sub=cost_sub(p, n))}</span>"
                      for (w, p), c in zip(parts, ("pp", "pg"), strict=True))  # fmt: skip
        bar = hbar(segs, top, h=14, cls="hb")
        named = f' title="{e(title)}"' if title else ""
        fig = fig_html(f, n, sub=cost_sub(f, n, name))
        lines.append(f'<div class="cl"><span class="cln"{named}>{e(beside_unit(name))}</span>{bar}'
                     f'<span class="clf">{fig}</span><span class="cps">{cps}</span></div>')  # fmt: skip
    return f'<div class="cbars">{"".join(lines)}</div>'


def low_first(name):
    """A label inside a list: its first letter lower case, unless it opens a capitalised word
    ("GPU time" stays)."""
    return name if name[1:2].isupper() else name[:1].lower() + name[1:]


def missing_html(missing):
    """The figures the board holds no value for, named once per reason, in the board's words."""
    return "".join(
        f'<p class="cnone">{e(", ".join(k if i == 0 else low_first(k) for i, k in enumerate(names)))}'
        f": none, {e(why)}</p>"
        for why, names in missing.items()
    )  # fmt: skip


def gpus_words(row):
    """The GPUs a row's counted sessions bound (SE-2, the sessions' `gpus`): "1 × H200"; where
    the rented machine held more, as its manifests record (SE-2: printed, not counted), "2 × H200
    rented, 1 given to the job and priced"."""
    bound = {s.get("gpus") for s in row["sessions"]}
    if not bound or not all(bound):
        return "GPUs not recorded"
    said = " or ".join(f"{g:,}" for g in sorted(bound))
    seen = (row.get("machine") or {}).get("gpus_visible") or []
    if seen and max(seen) > max(bound):
        rented = " or ".join(f"{g:,}" for g in seen)
        return f"{rented} × H200 rented, {said} given to the job and priced"
    return f"{said} × H200"


def words_or(values):
    """A record's values in words: one, or each joined by "or" where the sessions differ."""
    return " or ".join(str(v) for v in values)


HOST_WORD = {"same_as_prover": "the prover's host"}  # a manifest's `verifier_host`, in words


def verifying_html(row):
    """The Verifying line (CO-6's verify time, amended 2026-11-15): the program the row's verify
    time timed, on what (the verifier's CPUs and their model, the host, whether a GPU was
    visible to it, from the counted sessions' manifests and traces), the range of the sessions'
    means and n; then each of the publisher's verifiers no session timed."""
    st, mc = row.get("statement"), row.get("machine")
    f = row["figures"]["verify_seconds_per_reply"]
    if not st or not has(f):
        return ""
    said = [f"<code>{e(st['program'])}</code>"]
    if mc and mc["verifier_cpus"] and mc["cpu_model"]:
        cpus = words_or(mc["verifier_cpus"])
        host = words_or(HOST_WORD.get(h, h) for h in mc["verifier_host"])
        on = f"on {cpus} CPUs of an {words_or(mc['cpu_model'])}" + (f", {host}" if host else "")
        seen = mc["verify_gpu_visible"]  # from the verify traces
        on += {(True,): ", its GPU visible", (False,): ", no GPU visible"}.get(
            tuple(seen), ", a GPU visible in some sessions" if seen else ""
        )
        said.append(e(on))
    spread = range_words(f)
    count = f["n"] if f["n"] is not None else counted(row)
    timed = (f"{spread}, the {count:,} sessions' means" if spread
             else fig_words(f)) + f", n\u00a0=\u00a0{count:,}"  # fmt: skip
    rel = (S.V["release"] or {}).get("id")
    untimed = "".join(f" \u00b7 {e(u)}: not timed" + (f" in {e(rel)}'s sessions" if rel else "")
                      + (f" (a trial under {PETAL_NAME['machine_checked']})" if any(
                          t["place"] == TRIAL_OTHER and u.lower() in t["verifier"].lower()
                          for t in row.get("trials_kept") or ()) else "")
                      for u in st["untimed"])  # fmt: skip
    return (f'<p class="rb"><span class="k">Verifying</span> <span>{" ".join(said)}{e(SEP)}'
            f"{e(timed)}{untimed}</span></p>")  # fmt: skip


def ran_html(row):
    """The Ran on line: where the counted sessions ran and what with, as their manifests record
    it (the provider, the image by its digest, the harness and adapter commits, each linked at
    its full hash); each distinct value where the sessions differ."""
    mc = row.get("machine") or {}
    if not mc.get("provider"):
        return ""

    def commit(h):
        return f'<a href="{e(S.REPO_URL)}/commit/{e(h)}" title="{e(h)}"><code>{e(h[:8])}</code></a>'

    def image(ref):
        name, _, digest = ref.rpartition("@")
        short = f"{name.rsplit('/', 1)[-1]}@{digest[:15]}" if digest else ref
        return f'<code title="{e(ref)}">{e(short)}</code>'

    said = [e(words_or(mc["provider"]))]
    if mc.get("image"):
        said.append("image " + " or ".join(image(r) for r in mc["image"]))
    for word, key in (("harness", "harness_commit"), ("adapter", "adapter_commit")):
        if mc.get(key):
            said.append(f"{word} " + " or ".join(commit(h) for h in mc[key]))
    return f'<p class="rb"><span class="k">Ran on</span> <span>{", ".join(said)}</span></p>'


def format_html(p):
    """The proved copy's number format in words, as the publisher states it (RFC-0018 SI-9,
    amended 2026-11-16): "integer weights, fixed-point activations, as the publisher states",
    each distinct quote after it, linked at the pin; "number format: not stated" where the
    properties file records the format and the publisher states none; "" where it records none."""
    fmt = p.get("number_format")
    if not fmt:
        return ""
    words = [f"{FORMAT_WORD[fmt[k]['value']]} {k}" for k in ("weights", "activations")
             if fmt[k]["value"] in FORMAT_WORD]  # fmt: skip
    if not words:
        return e(f"{FORMAT_HEAD}: not stated")
    quotes = {q["url"]: q for k in ("weights", "activations") for q in fmt[k]["quotes"]}
    silent = [k for k in ("weights", "activations") if fmt[k]["value"] not in FORMAT_WORD]
    tail = "".join(f", and the {k}' format is not stated" for k in silent)
    return (e(", ".join(words)) + ", as the publisher states: " + quote_links(list(quotes.values()))
            + e(tail))  # fmt: skip


def proved_html(row):
    """What the row proves, at the head of its Fidelity section (RFC-0018 SI-3, SI-9, amended
    2026-11-16): the copy (its workload record), its words, its weight bits and how they were
    found, where the bits cover part of the weights, so; then its number format as the publisher
    states it, with the quotes (`format_html`)."""
    p = row.get("precision")
    if not p:
        return ""
    said = (f'<a href="{e(link(p["record"]))}" title="{e(p["record"])}">{e(p["proved"])}</a>'
            + (f" ({e(p['proved_words'])})" if p["proved_words"] else ""))  # fmt: skip
    if isinstance(p["bits"], int | float):
        n = f"{p['bits']:,}" if float(p["bits"]).is_integer() else sig(p["bits"], 3)
        how = BASIS_BITS.get(p["bits_basis"], p["bits_basis"] or "")
        if p["bits_source"]:
            how = f'<a href="{e(p["bits_source"])}">{e(how)}</a>'
        part = " for part of the weights" if p["bits_covers"] == "part" else ""
        said += f", {e(n)} bits per weight{e(part)}, {how}"
    if fmt := format_html(p):  # a sentence of its own (escaped words open it)
        said += f". {fmt[:1].upper()}{fmt[1:]}"
    return f'<p class="rb"><span class="k">Proved</span> <span>{said}</span></p>'


def generation_html(row):
    """CO-7 (amended 2026-11-15): where the system generates in a phase of its own, what
    generates (the facts file, with the publisher's words linked) and that phase's GPU-seconds
    per reply token, with its range and n."""
    gen = S.V["systems"][row["system"]].get("generation")
    f = row["figures"].get("generation_gpu_seconds_per_reply_token")
    if not gen or not has(f):
        return ""
    quote = f'<a class="qt" href="{e(gen["url"])}">\u201c{e(gen["quote"])}\u201d</a>'
    sub = SEP.join(w for w in (range_words(f), f"n\u00a0=\u00a0{f['n']}" if f["n"] else "") if w)
    return (f'<p class="rb"><span class="k">Generation</span> <span>{e(gen["words"])} '
            f"{quote}{e(SEP)}{fig_html(f, sub=sub)}</span></p>")  # fmt: skip


def size_html(row):
    """What Proof size counts: every file a proof is released as, by kind, from the sessions'
    manifests (a size is the bytes as written, JSON text where the files are JSON)."""
    st = row.get("statement")
    if not st or not st["proof_parts_count"] or not has(row["figures"]["proof_bytes_per_reply"]):
        return ""
    kinds = ", ".join(f"{k['count']:,} × {k['kind']}" if k["count"] > 1 else k["kind"]
                      for k in st["proof_parts"])  # fmt: skip
    n = st["proof_parts_count"]
    return (f'<p class="rb"><span class="k">Proof size</span> <span>the bytes of the {n:,} '
            f"{'file' if n == 1 else 'files'} a proof is released as, as written: "
            f"<code>{e(kinds)}</code></span></p>")  # fmt: skip


def ladder_html(rung):
    """CO-4: the serving ladder, each concurrency's rate, the full-load rung marked; behind a
    disclosure, under the Serving line."""
    b = rung["baseline"] or {}
    ladder = [c for c in b.get("ladder") or [] if c["rate"] is not None]
    if not ladder:
        return ""
    top = max(c["rate"]["value"] for c in ladder) if all(has(c["rate"]) for c in ladder) else 0
    rows = []
    for c in ladder:
        full = c["concurrency"] == b["concurrency"]
        # each rate a bar from zero on one scale, the ladder's highest rate; full load in paper
        bar = (
            hbar([(c["rate"]["value"], "bp" if full else "bg")], top, h=8, cls="hb lbar")
            if top > 0
            else ""
        )
        rows.append([f"{c['concurrency']:,}" + (" (full load)" if full else ""),
                     f'<span class="lrt">{fig_html(c["rate"], sub=BARE)}{bar}</span>'])  # fmt: skip
    return (f'<h3 class="sub-h">Serving ladder, {len(ladder):,} concurrencies</h3>'
            + stacked(["Concurrent requests", "Rate"], rows))  # fmt: skip


# a stored tier's glossary entry, where its words link (D2: they say whose runs these are)
TIER_TERM = {"reported": "Evidence: our runs only, not rerun by anyone else"}


def reply_tokens_html(row):
    """CO-8 (adopted 2026-11-16): reply tokens per GPU-second, once, beside the session GPU time:
    the figure with its unit, its range, n in whole sessions and the GPUs bound, then what the
    records do not time apart. It depends on the GPU, so it prints nowhere above this depth."""
    f = row["figures"].get(
        PROVED_RATE.get(lead_figure(row)[2], "session_reply_tokens_per_gpu_second")
    )
    if not has(f):
        return ""
    st = f.get("stats") or {}
    count = f["n"] if f["n"] is not None else counted(row)
    said = []
    if (st.get("n") or 0) > 1 and st.get("min") is not None and st.get("max") is not None:
        lo, hi = (number(st[k], f["unit"])[0] for k in ("min", "max"))
        said.append(e(f"{lo} to {hi}"))
    said.append(
        f"n\u00a0=\u00a0{count:,} "
        + (term("sessions", "Session") if further() else term("whole sessions", "Whole session"))
    )
    bound = sorted({s.get("gpus") for s in row["sessions"] if s.get("gpus")})
    if bound:  # the GPUs the sessions bound, the ones its GPU-seconds count (SE-2)
        said.append(e(f"{' or '.join(f'{g:,}' for g in bound)} × {gpu_name(row)}"))
    head = term(REPLY_TOKENS_HEAD, REPLY_TOKENS_HEAD)
    return (f'<p class="rb rtk"><span class="k">{head}</span> <span>'
            f"{fig_html(f, count, sub=BARE)} ({', '.join(said)})</span></p>")  # fmt: skip


def evidence_words(named):
    """The evidence tier of a block's figures in words (TIER_WORD, AGENTS.md rule 2), once for the
    block where they share one; else each tier with the figures that carry it. `named`: (name,
    figure) pairs, each figure present."""
    tiers: dict[str, list[str]] = {}
    for k, f in named:
        tiers.setdefault(TIER_WORD[f["tier"]], []).append(beside_unit(k))

    def linked(w):
        tier = next((k for k, v in TIER_WORD.items() if v == w), None)
        return term(w, TIER_TERM[tier]) if tier in TIER_TERM else e(w)

    if len(tiers) == 1:
        return linked(next(iter(tiers)))
    return e(SEP).join(f"{linked(w)}: {e(', '.join(low_first(k) for k in ks))}"
                     for w, ks in tiers.items())  # fmt: skip


# CO-7 (amended 2026-11-15): the session less its commit call and its generation phase
PROVING_REST = "Proving GPU time per reply"


def split_html(row):
    """CO-9 (Q55): where a further reply's generation part comes from, one line: the adapter's
    phase with each session's reported phases against its harness-timed prove call, the
    generation marks, or why the board splits none (the board's words)."""
    sp = row.get("further_split")
    if not further() or sp is None:
        return ""
    if sp.get("source") is None:
        said = e(f"{NO_SPLIT}: {sp.get('cause') or 'no source recorded'}")
    elif sp.get("source") == "generation_marks":
        said = "generation from the system's own generation phase"
    else:
        checks = ", ".join(f"{c['phases_seconds']:,.1f}\u00a0s of {c['prove_call_seconds']:,.1f}"
                           "\u00a0s" for c in sp.get("sessions") or [])  # fmt: skip
        tol = f"{sp['tolerance'] * 100:g}\u00a0%" if sp.get("tolerance") is not None else ""
        said = e(f"generation as the adapter reports it (its {sp.get('phase')} phase); its "
                 f"phases sum to {checks} of the timed prove call, within {tol}")  # fmt: skip
    return f'<p class="rb"><span class="k">Split</span> <span>{said}</span></p>'


def setups_html(row):
    """CO-9 (Q55): the setups the counted sessions reused, counted in the one-time work: each by
    its id, its GPU time and its record."""
    found = row.get("one_time_setups") or []
    if not found:
        return ""
    said = ", ".join(
        f'<a href="{e(link(s["record"]))}"><code>{e(s["setup_id"][:12])}</code></a> '
        f"{e(number(s['gpu_seconds'], 'gpu_s')[0])}\u00a0GPU-h"
        for s in found
    )
    return f'<p class="rb"><span class="k">Setup</span> <span>{said}</span></p>'


def cost_html(row):
    """The cost parts (CO-1 to CO-5), each figure as the board stores it (the figures block above
    prints the cost alone): how the model was served; once what the proving figures are over (the
    GPUs the counted sessions bound, SE-2, and the whole sessions, n), a figure that differs
    saying so under it (`cost_sub`); once the evidence of the block's figures (the tier, which
    their titles also carry: DEPTH law 3). Then a GPU time with two parts drawn as a bar
    (`cost_bars`), a sheet of the other figures, and, once, each figure the board holds no value
    for with the board's reason (a steady figure on a row with no steady state: NO_STEADY_WORD).
    Verify time and proof size close the sheet, each with its own scope and n under it (SI-8): the
    Proving line names the proving's GPUs and sessions, not theirs."""
    rung = rung_of(row)
    figs, b, n = row["figures"], rung["baseline"] or {}, counted(row)
    price = S.V["price"]
    _, _, key = lead_figure(row)
    # the multiple the band does not print: a steady row's session one, beside the session cost
    # (CO-5's label is the band's, for a row's one figure; this one's scope is in its title)
    session = (f"Session {FIGURE_NAME['multiple'].lower()}", figs["session_multiple"], n)
    # CO-9: on a further reply's board the session figures say so, apart from its own
    lead = "Session c" if further() else "C"
    steady = (f"Steady {FIGURE_NAME['multiple'].lower()}", figs["multiple"], n)
    # CO-9 (Q55): a further reply's board keeps both, computed and stored, here
    others = {"multiple": [session], "session_multiple": [steady]}.get(key, [session, steady])
    gpu = [("Serving GPU time per reply", b.get("gpu_seconds_per_reply"), None, None),
           (M_HEAD, figs["steady_gpu_seconds_per_reply"], n, "steady_gpu_seconds_per_reply"),
           ("Session GPU time per reply", figs["session_gpu_seconds_per_reply"], n,
            "session_gpu_seconds_per_reply"),
           # CO-7 (amended 2026-11-15): the session in its timed calls
           (f"{lead}ommit GPU time per reply", figs.get("session_commit_gpu_seconds_per_reply"),
            n, None),
           (PROVING_REST if not further() else f"Session {PROVING_REST.lower()}",
            figs.get("session_proving_gpu_seconds_per_reply"), n, None),
           # CO-9 (Q55): the prove step's diagnostics, never a ladder figure
           *(((UTIL_HEAD, figs["prove_gpu_util_mean"], n, None),
              (MEMORY_HEAD, figs["prove_gpu_memory_peak"], n, None)) if further() else ())]  # fmt: skip
    # a GPU time with two parts is drawn (its head's title its full name), the others are cells
    drawn = [(k, f, key, M_NAME if k == M_HEAD else "") for k, f, _, key in gpu
             if has(f) and gpu_parts(figs, key)]  # fmt: skip
    sheet = [*((k, f, count) for k, f, count, key in gpu if not any(f is d[1] for d in drawn)),
             *others, ("Steady cost per reply", figs["steady_usd_per_reply"], n),
             ("Session cost per reply", figs["session_usd_per_reply"], n),
             ]  # fmt: skip
    # the block's tiles print the multiple's cost, the serving cost, the price, verify time and
    # proof size: the sheet holds the rest
    usd = {"session_multiple": "session_usd_per_reply",
           "further_reply_multiple": "further_reply_usd_per_reply"}.get(key, "steady_usd_per_reply")  # fmt: skip
    sheet = [x for x in sheet if x[1] is not figs[usd]]
    own = ()
    no_steady = not has(figs["multiple"]) and figs["multiple"]["null_reason"] == "not_applicable"
    steady_figs = (figs["multiple"], figs["steady_gpu_seconds_per_reply"],
                   figs["steady_usd_per_reply"])  # fmt: skip
    missing: dict[str, list[str]] = {}
    for k, f, _ in sheet:
        if has(f):
            continue
        why = ("not recorded" if not f else NO_STEADY_WORD
               if no_steady and any(f is g for g in steady_figs) else NULL_WORD[f["null_reason"]])  # fmt: skip
        missing.setdefault(why, []).append(k)
    base = rung["baseline"]
    line = bool(base) and has(base["gpu_seconds_per_reply"])
    rows = [(k, serving_fig(f, line) if count is None and k.startswith("Serving")
             else fig_html(f, count, sub=cost_sub(f, n, k, any(f is o for o in own))))
            for k, f, count in sheet if has(f)]  # fmt: skip
    if price and has(price["usd_per_gpu_hour"]):  # the head says what, the unit per what
        when = f"as of {price['date']}" if price["date"] else None
        rows.append(("H200 price", fig_html(price["usd_per_gpu_hour"], sub=when,
                                            note=f"basis: {price['basis']}")))  # fmt: skip
    else:
        missing.setdefault("not recorded", []).append("Price of one H200 GPU-hour")
    m_title = f' title="{e(M_NAME)}"'
    cells = "".join(f"<div><dt{m_title if k == M_HEAD else ''}>{e(beside_unit(k))}</dt>"
                    f"<dd>{v}</dd></div>" for k, v in rows)  # fmt: skip
    against = (f'{e(SEP)}<a href="#proved">{e(PROVED_LINK[0])}</a>{e(PROVED_LINK[1])}'
               if row.get("precision") else "")  # fmt: skip
    # the serving run, linked to its record as a session is
    run = (f" ({run_link(row, base['run_id'], SERVING_SYSTEM)})"
           if line and base.get("run_id") else "")  # fmt: skip
    serving = (f'<p class="rb"><span class="k">Serving</span> <span>{e(serving_words(base))}'
               f"{run}{against}</span></p>" if line else "")  # fmt: skip
    whole = e(whole_line(row, n)).replace(
        "whole sessions", term("whole sessions", "Whole session"), 1
    )
    over = (f'<span class="nw">{e(gpus_words(row))},</span> '
            f'<span class="nw">{whole}</span>')  # fmt: skip
    proving = f'<p class="rb"><span class="k">Proving</span> <span>{over}</span></p>' if n else ""
    # the tier of every figure the block prints (the price is the reference file's, not a run's)
    shown = [(k, f) for k, f, _, _ in drawn] + [(k, f) for k, f, _ in sheet if has(f)]
    evidence = (f'<p class="rb"><span class="k">Evidence</span> <span>{evidence_words(shown)}'
                "</span></p>" if shown else "")  # fmt: skip
    missing.pop(NO_STEADY_WORD, None)  # the sessions table prints each session's none and why
    return (f"{serving}{proving}{split_html(row)}{setups_html(row)}{generation_html(row)}"
            f"{verifying_html(row)}{size_html(row)}{reply_tokens_html(row)}{evidence}{ran_html(row)}"
            f"{cost_bars(row, drawn)}"
            f'<dl class="parts">{cells}</dl>{missing_html(missing)}{ladder_html(rung)}')  # fmt: skip


def p_html(p):
    """A p value at two significant digits; below 0.001 as a power of ten, the exponent raised
    ("5.0 × 10" and "minus 6" above it), which reads where seven decimal places do not."""
    if p == 0 or p >= 0.001:
        return e(sig(p, 2))
    exp = math.floor(math.log10(p))
    mant = f"{p / 10**exp:.1f}"
    if mant == "10.0":
        mant, exp = "1.0", exp + 1
    return f"{mant}\u00a0\u00d7\u00a010<sup>\u2212{-exp}</sup>"


def p_floor(n):
    """FI-4: the lowest p a test on n prompts can give: 2^-n when it counts every sign vector,
    1 / (1 + resamples) when it draws them."""
    c = S.V["constants"]
    return 2.0**-n if n <= c["fidelity_exact_up_to"] else 1 / (1 + c["fidelity_resamples"])


def p_said(p, n):
    """A p as a line prints it: "p = 0.0058"; at its test's floor a drawn p is a bound, "p <
    5.0 × 10^-6, the test's floor", and a counted one its value with the same words."""
    if p != p_floor(n):
        return f"p\u00a0=\u00a0{p_html(p)}"
    if n <= S.V["constants"]["fidelity_exact_up_to"]:
        return f"p\u00a0=\u00a0{p_html(p)}{e(P_FLOOR)}"
    return f"p\u00a0&lt;\u00a0{p_html(p_bound(p))}{e(P_FLOOR)}"


def p_bound(p):
    """The two-digit power of ten at or above p, so "p < bound" holds as printed."""
    exp = math.floor(math.log10(p))
    mant = math.ceil(p / 10**exp * 10) / 10
    return mant * 10**exp


RULE_AT = re.compile(r"\s*\((?:RFC-\d+ )?[A-Z]{2}-\d+[a-z]?\)$")  # a note's closing rule id


def control_th(cid):
    """A control's row head, its id in the title where its name is not the id; an id in
    parentheses after the name is set small in the mono face, whose underscore reads."""
    name, title = control_name(cid)
    at = f' title="{e(title)}"' if title else ""
    words, paren, rest = name.partition(" (")
    said = e(words) + (f' <span class="cid">({e(rest)}</span>' if paren else "")
    return f'<th scope="row"{at}>{said}</th>'


def kl_why(row):
    """Why the row's KL is not measured, in visible words (its note without the state that opens
    it and the rule id that closes it, which stay in the title), and the note whole."""
    note = (row["fidelity"] or {}).get("kl_note") or ""
    return RULE_AT.sub("", note.removeprefix("not measured: ").removeprefix("not measured")), note


def kl_cell(row):
    """The row's KL in its column: the figure, or "not measured" with why under it."""
    kl = (row["fidelity"] or {}).get("kl")
    if has(kl):
        return fig_html(kl)
    why, note = kl_why(row)
    return (f'<span class="na" title="{e(note or "not measured")}">not measured</span>'
            + (f'<span class="sub">{e(why)}</span>' if why else ""))  # fmt: skip


def tf_kl_html(entry, block_n):
    """A teacher-forced KL figure with its labels in its title (its n under it where it is not
    the block's), or "not measured" with the cause."""
    kl = entry["kl"]
    if kl is None:
        note = entry["kl_note"] or "not measured"
        return f'<span class="na" title="{e(note)}">not measured</span>'
    num, unit = number(kl["value"], kl["unit"])
    title = (f"{kl['unit']} · measured, reported · {kl['note']} · {kl['n']:,} prompts, "
             f"{kl['positions']:,} positions · mean probability the original gives the pooled "
             f"tokens: {sig(kl['reference_rest_mass'] or 0, 2)} · record: {kl['source']}")  # fmt: skip
    sub = "" if kl["n"] == block_n else f'<span class="sub">{e(TF_KL_SUB.format(n=kl["n"]))}</span>'
    return (f'<span class="fig" title="{e(title)}"><span class="n">{e(num)}</span>'
            f'<span class="u">{e(unit)}</span></span>{sub}')  # fmt: skip


def agree_html(entry, tf, sub):
    """FI-10's agreement for one row of the table: the percentage of the positions (SI-9), its
    labels in its title, and `sub` (the median, failed prompts) under it; "not run" with the
    cause in its title where the pass did not run."""
    if entry is None or entry["status"] != "ok":
        why = (entry or {}).get("cause") or "not run"
        return f'<span class="na" title="{e(why)}">not run</span>'
    # each part with its label, so the title's lines keep one column (the ladder's Fidelity title does the same)
    return (f'<span class="fig" title="{e(agree_title(entry, tf))}">'
            f'<span class="n">{e(pct(entry["percent"]))}</span><span class="u">%</span></span>'
            + "".join(f'<span class="sub">{e(line)}</span>' for line in sub if line))  # fmt: skip


def interval_words(entry):
    """SI-9: a percentage's 95 % bootstrap interval over the prompts, as the board computed it."""
    low, high = entry["percent_interval"]
    return TF_INTERVAL.format(low=pct(low), high=pct(high))


def median_words(entry, tf):
    """The median in the mean's unit, a percentage of the positions."""
    if entry is None or entry["status"] != "ok":
        return ""
    return TF_SUB.format(median=f"{pct(entry['median'] / tf['positions'] * 100)}\u202f%")


def tests_html(row, tf, mine):
    """FI-11's tests, printed and not gating (SI-9): one native disclosure under the table, its
    summary their count, each control's two p values on a line (the row above it, below it), each
    half kept whole (`kept`): a line too long breaks between the two."""
    if mine is None:
        return ""
    tests = {(t["a"], t["b"]): t["p"] for t in mine["tests"]}
    lines = []
    for c in tf["controls"]:
        above, below = tests.get((row["system"], c["id"])), tests.get((c["id"], row["system"]))
        if above is None or below is None:
            continue
        name, title = control_name(c["id"])
        at = f' title="{e(title)}"' if title else ""
        words = (e(TF_TEST.format(name=name_of(row), above="\0", below="\1"))
                 .replace("\0", p_said(above, tf["n"]))
                 .replace("\1", p_said(below, tf["n"])))  # fmt: skip
        lines.append(f"<div><dt{at}>{e(name)}</dt><dd>{kept(*words.split(' · '))}</dd></div>")
    if not lines:
        return ""
    said = f"{counted_words(2 * len(lines), 'test')} {TF_TESTS_ON}"  # the measure, visible
    return f'<h3 class="sub-h">{e(said)}</h3><dl class="fts">{"".join(lines)}</dl>'


NOT_RUN = '<span class="na">not run</span>'


def fid_tr(cls, th, kind, cells, heads, tf, entry, ink):
    """A row of the Fidelity table: its head, kind, the track of its teacher-forced mean (with a
    teacher-forced pass; `ink` its tick's class), then one cell per figure column, in `heads`'
    order."""
    track = ""
    if tf:
        mean = entry["mean"] if entry is not None and entry["status"] == "ok" else None
        track = (
            f'<td class="trk" aria-hidden="true">{fid_svg(mean, None, tf["positions"], ink)}</td>'
        )
    tds = "".join(f'<td data-l="{e(FID_HEAD.get(h, h))}">{c}</td>'
                  for h, c in zip(heads[2:], cells, strict=True))  # fmt: skip
    at = f' class="{cls}"' if cls else ""
    return f'<tr{at}>{th}<td data-l="{e(FID_KIND)}">{kind}</td>{track}{tds}</tr>'


def own_rows(row, tf, any_kl, heads):
    """The system's own replies: its Fidelity (median and failed prompts under it), its mean
    matched prefix (n in replies, where the Cost's n counts sessions, and p above the bar under
    it), its teacher-forced KL; then FI-13's label word for word, what ran and the records in a row
    of their own under it, on the same paper."""
    mine = row["fidelity"]
    tf_mine = tf["rows"].get(row["system"]) if tf else None
    if mine is None and tf_mine is None:
        return []
    cells = []
    if tf:
        sub = [median_words(tf_mine, tf)]
        if tf_mine is not None and tf_mine.get("percent_interval"):
            sub.append(interval_words(tf_mine))
        if tf_mine is not None and tf_mine["failed"]:
            causes = sorted({f["cause"] for f in tf_mine["failed"]})
            sub.append(TF_FAILED.format(k=len(tf_mine["failed"]), n=tf_mine["n"]) + ": "
                       + SEP.join(causes))  # fmt: skip
        cells.append(agree_html(tf_mine, tf, sub))
    if mine is not None:
        prefix = plain(mine["mean_prefix"], "tokens", row["record"] + "/fidelity/mean_prefix",
                       f"n = {mine['n']:,} replies")  # fmt: skip
        said = [e(f"n\u00a0=\u00a0{mine['n']:,} replies")]
        if mine["p_above_bar"] is not None:
            said.append(
                e(P_ABOVE.format(p="\0")).replace("\0", p_said(mine["p_above_bar"], mine["n"]))
            )
        cells.append(f'{prefix}<span class="sub">{kept(*said)}</span>')
    else:
        cells.append(NOT_RUN)
    if tf:
        cells.append(tf_kl_html(tf_mine, tf["n"]) if tf_mine is not None else NOT_RUN)
    if any_kl:
        cells.append(kl_cell(row))
    out = fid_tr("me", f'<th scope="row">{e(name_of(row))}</th>', "this system", cells, heads, tf,
                 tf_mine, "me")  # fmt: skip
    if tf_mine is not None:  # FI-13: whose computation, what ran, the records; the columns it
        # labels named, since the row it sits under holds the leading tokens (FI-3) too
        records = [p for p in (tf_mine["run"], tf["path"]) if p]
        whose = f"{name_of(row)}'s {TF_BOTH}"
        label = (f'<p>{e(whose)}: {e(tf_mine["label"])}. What ran: '
                 f'{e(tf_mine["computed_by"])}.</p>{"".join(evidence_links(records))}')  # fmt: skip
        out += f'<tr class="me ml"><td colspan="{len(heads) + 1}">{label}</td></tr>'
    return [(fid_score(tf_mine, mine), out)]


def control_rows(fid, tf, any_kl, heads):
    """The model's controls, FI-3's in their order, then any only the teacher-forced pass has:
    each one's Fidelity (its median under it), its mean matched prefix, its teacher-forced KL; the
    bar's row ruled. A control that failed to run reads not run, its kind says so."""
    bar = (fid or {}).get("bar")
    fcs = {c["id"]: (i, c) for i, c in enumerate((fid or {}).get("controls") or [])}
    tcs = {c["id"]: c for c in (tf or {}).get("controls") or []}
    out = []
    for cid in [*fcs, *(k for k in tcs if k not in fcs)]:
        i, c = fcs.get(cid, (None, None))
        t = tcs.get(cid)
        is_bar = bar is not None and bar["control"] == cid
        if not (is_bar or FID_COPY.match(cid)):  # the table holds the quantized copies; the
            continue  # other controls stay in the fidelity record
        failed = c is not None and c["status"] == "failed"
        kind = (
            (c or t)["kind"]
            + (", the bar" if is_bar else "")
            + (", failed to run" if failed else "")
        )
        none = f'<span class="na">{"not run" if failed or c is None else "not measured"}</span>'
        cells = [agree_html(t, tf, [median_words(t, tf)])] if tf else []
        cells.append(plain(c["mean_prefix"], "tokens", f"{fid['record']}/controls/{i}/mean_prefix",
                           missing="not run" if failed else "not measured")
                     if c is not None else none)  # fmt: skip
        if tf:
            cells.append(tf_kl_html(t, tf["n"]) if t is not None else NOT_RUN)
        if any_kl:
            kl = (c or {}).get("kl")
            cells.append(fig_html(kl) if has(kl) else none)
        # honest or damaged, linked to what the level means by it (FI-2), then the rest
        word = (c or t)["kind"]
        kind_html = term(word, KIND_TERM) + e(kind[len(word) :])
        tr = fid_tr("bar" if is_bar else "", control_th(cid), kind_html, cells, heads, tf, t,
                    (c or t)["kind"])  # fmt: skip
        out.append((fid_score(t, c), tr))
    return out


# the controls the Fidelity table prints: the quantized copies, by llama.cpp's type names
# ("q8_0", "q4_k_m"); a rerun, a model with blocks cut and a smaller model stay in the record
FID_COPY = re.compile(r"^q\d")


def fid_score(tf_entry, entry):
    """What the Fidelity table sorts on, highest first: a row's top-token agreement (FI-10's
    mean), else its mean matched prefix; a row with neither goes last."""
    if tf_entry is not None and tf_entry.get("status") == "ok" and tf_entry.get("mean") is not None:
        return (1, tf_entry["mean"])
    prefix = (entry or {}).get("mean_prefix")
    if isinstance(prefix, dict):  # a stored quantity
        prefix = prefix.get("value")
    return (0, prefix) if prefix is not None else (-1, 0.0)


def fidelity_html(row):
    """SI-9 and FI-3 to FI-7 in one table: the system's own replies (a paper row) and each of the
    model's controls, with Fidelity (FI-10's agreement, as a percentage of the reply's positions,
    its median under it) drawn on a track of the positions, the mean matched prefix the check reads
    (FI-3; the system's n and p above the bar under it, the bar's row ruled), and the KL of the
    teacher-forced pass (FI-12). Under the system's row, in a row of its own, FI-13's label word for
    word, what ran and the records. The tests (FI-11) one click away under the table. KL to the
    original weights (FI-7) is a column where a system or a control of the model has the figure;
    where none does, one line at the section's head says why the row's is not measured (law 2)."""
    rung = rung_of(row)
    fid, tf = rung["fidelity"], rung.get("teacher_forced")
    kl_h = kl_head(rung["reference_dtype"])
    # KL to the original weights is printed for each control (FI-7): a column wherever a system or
    # a control of the model has the figure
    any_kl = any(has((r.get("fidelity") or {}).get("kl")) for r in rung["rows"]) or any(
        has(c.get("kl")) for c in (fid or {}).get("controls") or []
    )
    heads = [FID_WHO, FID_KIND, *([TF_AGREE] if tf else []), PREFIX, *([TF_KL] if tf else []),
             *([kl_h] if any_kl else [])]  # fmt: skip
    # one board, highest Fidelity first: the system's row takes its place among the copies
    scored = own_rows(row, tf, any_kl, heads) + control_rows(fid, tf, any_kl, heads)
    body = "".join(tr for _, tr in sorted(scored, key=lambda r: r[0], reverse=True))
    if not body:
        return '<p class="none">Not run yet.</p>'
    lead = ""
    if fid is not None and fid.get("bar") is None:
        lead = f'<p class="flead">No bar: {e(fid["cause"] or "no damaged copy qualified")}</p>'
    if not any_kl and row["fidelity"] is not None:  # why, in words: no title alone (DEPTH law 3)
        why, note = kl_why(row)
        lead += (f'<p class="flead">{e(kl_h)}: <span class="na" title="{e(note or "not measured")}">'
                 f"not measured</span>{f' ({e(why)})' if why else ''}</p>")  # fmt: skip
    lead = proved_html(row) + lead
    ths = (f'<th scope="col">{e(heads[0])}</th><th scope="col">{e(heads[1])}</th>'
           + ('<th scope="col" class="trk" aria-hidden="true"></th>' if tf else "")
           + "".join(f'<th scope="col"{tf_title(h, tf)}>{e(FID_HEAD.get(h, h))}</th>'
                     for h in heads[2:]))  # fmt: skip
    tests = tests_html(row, tf, tf["rows"].get(row["system"])) if tf else ""
    limits = "".join(f'<p class="flead">{e(line)}</p>' for line in fid_limits(rung, tf))
    return (f'{lead}<table class="rt stk fid"><thead><tr>{ths}</tr></thead>'
            f"<tbody>{body}</tbody></table>{limits}{tests}")  # fmt: skip


def fid_limits(rung, tf):
    """What the Fidelity measures rest on, each line from the records (depth 3): where the
    original was fetched and the ceiling its own pass sets (FI-1, FI-15), the engines and slots
    of each part of the fidelity run (FI-9, FM-5), and what the prompts are cut from."""
    out = []
    o = rung.get("original")
    if o and o.get("repo"):
        bits = DTYPE_BITS.get(o["dtype"], o["dtype"])
        line = LIM_ORIGINAL.format(repo=o["repo"], rev=str(o["revision"])[:7], bits=bits)
        owner = str(o["repo"]).split("/")[0]
        if o.get("publisher_repo") and str(o["publisher_repo"]).split("/")[0] != owner:
            line += LIM_COPY.format(publisher=rung["publisher"])
        own = (tf or {}).get("reference_pass")
        if own and own.get("status") == "ok" and own.get("mean") is not None:
            line += LIM_CEILING.format(ceiling=pct(own["mean"] / tf["positions"] * 100))
        out.append(line)
    fid = rung.get("fidelity") or {}
    parts = []
    for r in fid.get("runs") or []:
        part = LIM_PART.get(r["part"], r["part"] or "")
        if r["engine"] == "vllm":
            parts.append(LIM_VLLM.format(part=part))
        elif r["engine"] is not None and r["slots"] is not None:
            slots = "one request" if r["slots"] == 1 else f"{r['slots']:,} requests"
            parts.append(LIM_LLAMA.format(part=part, slots=slots))
    if parts:
        line = LIM_ENGINES.format(parts=", and ".join(parts))
        out.append(line)
    corpus = S.V.get("corpus")
    if corpus and corpus["texts"]:
        out.append(LIM_PROMPTS.format(tokens=S.V["request"]["prompt_tokens"], texts=corpus["texts"],
                                      hosts=", ".join(corpus["hosts"]),
                                      licences=", ".join(corpus["licences"])))  # fmt: skip
    return out


def tf_title(head, tf):
    """A column head's title (the teacher-forced KL's says what it compares, FI-12) and, for the
    Fidelity column, its class (words.css sets its width)."""
    if tf and head == TF_KL:
        return f' title="{e(TF_KL_TITLE.format(k=tf["top_k"]))}"'
    full = f' title="{e(head)}"' if head in FID_HEAD else ""  # the head prints the short name
    return (' class="fag"' if head == TF_AGREE else "") + full


def band_two(row):
    """CO-9 (Q55): the band's two multiples side by side, each under its plain name: the total,
    the proved rate under it (CO-8), and the proving part, the replies one proof covers under it
    (or "not measured", its cause in its title); under both, once, what they counted and n."""
    _, f, _ = lead_figure(row)
    n = counted(row)
    count = (f or {}).get("n") or n
    total = fig_html(f, n, sub=BARE, how=how_computed(row)) + rate_html(row, f"#{RATE_ANCHOR}")
    line = sub_line(further_line(count)).replace(FURTHER, term(FURTHER, FURTHER_TERM), 1)
    return (f'<span class="sbx"><span class="sbl">{defined(FIGURE_HEAD["multiple"], "multiple")}'
            f"</span>{total}</span>"
            f'<span class="sbx"><span class="sbl">{defined(FIGURE_HEAD["proving"], "proving")}'
            f'</span>{proving_html(row, bare=True)}</span><span class="sub">{line}</span>')  # fmt: skip


def band_figure(row):
    """The band's one figure (`multiple_html`); of the whole sessions, its title
    names them and n, as the line under it does (law 3)."""
    _, f, key = lead_figure(row)
    if key != "session_multiple":
        return multiple_html(row)
    count = f["n"] if f["n"] is not None else counted(row)
    # the line under it, "whole sessions" linked to their definition (D1)
    line = sub_line(whole_line(row, count)).replace(
        "whole sessions", term("whole sessions", "Whole session"), 1
    )
    return (fig_html(f, count, sub=BARE, note=whole_note(row, key), how=how_computed(row))
            + f'<span class="sub">{line}</span>')  # fmt: skip


# ------------------------------------------------------------------ the body's blocks, as the ladder
# Each block of a system's page (amended 2026-11-17): what is computed, with its unit and labels;
# what it means, in a head or a few words linked to its definition (the checks page, the
# glossary); what it says for this system. How it is measured and why the rule is what it is are
# on the checks page and in Learn. The system's own data one level down (its records, sessions,
# the publisher's words, every copy) sits in one native disclosure per block.


def dig(label, inner):
    """A block's own data one click down: one native disclosure, its summary a plain label."""
    return (f'<details class="more dig"><summary>{e(label)}</summary>'
            f'<div class="dig-in">{inner}</div></details>')  # fmt: skip


def tiles(cells, cls=""):
    """A block's figures as the Figures row draws them: each (head, figure html, id or ""); `cls`
    a class more (words.css: "drawn", the tiles under a drawing)."""
    out = []
    for k, v, at in cells:
        place = f' id="{at}"' if at else ""
        out.append(f"<div{place}><dt>{k}</dt><dd>{v}</dd></div>")
    return f'<dl class="figs tiles{f" {cls}" if cls else ""}">{"".join(out)}</dl>'


def scope_html(*parts):
    """What a block's figures share (scope, n, GPUs, evidence), said once over them (DEPTH: once
    per block); each part is markup."""
    said = [p for p in parts if p]
    sep = f'<span class="sep">{SEP}</span>'
    return f'<p class="scope">{sep.join(said)}</p>' if said else ""


def lines_html(pairs):
    """Figures of one cell, one a line, each after its word ("proved", "8-bit copy"), the words in
    one column and the figures in the next."""
    return '<span class="tls">' + "".join(f'<span class="tlw">{w}</span><span class="tf">{f}</span>'
                                          for w, f in pairs) + "</span>"  # fmt: skip


def mean(words):
    """What a figure means, in a few words under it."""
    return f'<span class="mean">{e(words)}</span>'


# the Statement block's lines, by the board's row ids (SI-3, amended 2026-11-17)
STATEMENT_LINE = {"commit_record": "From our commit record", "request": "From the request",
                  "proof": "From the proof", "decoding": "Decoding",
                  "unchecked": "Not checked by any call", "architecture": "Architecture"}  # fmt: skip
# what an accept says, by whether the publisher states Level 1's statement at the pin (SI-4a)
ACCEPT_HEAD = "An accept means"
ACCEPT_SAYS = "the committed model's own greedy reply to the prompt"
ACCEPT_STATE = {"stated": "stated", "read": "no single sentence states it",
                "not": "not stated: no position"}  # fmt: skip


def given_short(st, rid):
    """What the verifier is given, for one line of the Statement block, in a few words; the files'
    names in a title (they are in full in the block's disclosure)."""
    if rid == "commit_record":
        k, names = len(st["verifier_files"]), ", ".join(st["verifier_files"])
        files = f' and <span title="{e(names)}">{e(counted_words(k, "file"))}</span>' if k else ""
        return "the commitment" + files.replace(" and ", ", ", 1)
    if rid == "request":
        said = f"the prompt ({st['prompt_tokens']:,} token ids)"
        if st["reply"] == "record":
            said += f", our {st['output_tokens']:,}-token reply"
        return e(said)
    if rid == "proof":
        said = counted_words(st["proof_files"], "file")
        them = "them" if st["proof_files"] > 1 else "it"
        said = e(said + (f", and the verifier reads the reply from {them}"
                         if st["reply"] == "proof" else ""))  # fmt: skip
        if st.get("proof_caveat"):  # a gap in our own verdict stays in view (law 2)
            cav = st["proof_caveat"]
            said += (f'<span class="sub cav">{e(cav[:1].upper() + cav[1:])}. '
                     '<a href="/statement#the-seams">The seams ↗</a></span>')  # fmt: skip
        return said
    if rid == "decoding":
        return e(f"{S.V['request']['decoding']}, at every reply position")
    if rid == "architecture":
        seen = st["architecture_visible"]
        return (
            e(f"visible: {seen}")
            if seen
            else f'<span class="na">{e(SCOPE_VALUE_WORD["not_stated"])}</span>'
        )
    return ""


def sources_html(quotes):
    """A line's evidence: the publisher's line it rests on ("source"), or each of several by its
    number; "not stated" where the publisher is silent."""
    if not quotes:
        return f'<span class="na">{e(SCOPE_VALUE_WORD["not_stated"])}</span>'
    links = [f'<a href="{e(q["url"])}" title="{e(q.get("text") or "")}">{e(str(i + 1))}</a>'
             for i, q in enumerate(quotes)]  # fmt: skip
    if len(links) == 1:
        return links[0].replace(">1</a>", ">source</a>")
    return "sources " + " ".join(links)


def statement_block(row):
    """SI-3 and SI-4a as a short list: the verifier, what an accept says (and whether the
    publisher states it), what the verifier is given and from where, the decoding rule, what no
    call checks and what of the architecture a proof shows; each line with its source. The claim
    card line by line, with every file named, one click down."""
    st = row.get("statement")
    if not st:
        return f'<p class="none">{e(SCOPE_VALUE_WORD["not_stated"])}</p>'
    lines = []
    card = (f'<a href="{e(link(st["card"]))}" title="{e(st["card"])}">claim card</a>'
            if st["card"] else "")  # fmt: skip
    lines.append(("Verifier", f"<code>{e(st['program'])}</code>", card))
    ls = row.get("level_statement")
    if ls is not None:
        if ls["reading"]:
            said = (f'<a class="df" href="{CHECKS_PAGE}#reading">{e(READ_AS)}</a>: '
                    f"{e(ACCEPT_STATE['read'])}")  # fmt: skip
        elif ls["stated"]:
            said = e(ACCEPT_STATE["stated"])
        else:
            said = f'<span class="na">{e(ACCEPT_STATE["not"])}</span>'
        lines.append((ACCEPT_HEAD, f'{e(ACCEPT_SAYS)} <span class="qs">({said})</span>',
                      sources_html(ls["quotes"])))  # fmt: skip
    for r in st["rows"]:
        given = given_short(st, r["id"])
        if not given:  # nothing given: the publisher's words name it, or it is not stated
            given = (e("listed by the publisher") if r["said"]
                     else f'<span class="na">{e(SCOPE_VALUE_WORD["not_stated"])}</span>')  # fmt: skip
        src = sources_html(r["said"]) if r["said"] or r["id"] != "unchecked" else ""
        lines.append((STATEMENT_LINE[r["id"]], given, src))
    trs = "".join(f'<tr><th scope="row">{e(k)}</th><td>{v}</td><td class="src">{s}</td></tr>'
                  for k, v, s in lines)  # fmt: skip
    quotes = sum(len(r["said"] or ()) for r in st["rows"])
    return (f'<table class="rt kvt"><tbody>{trs}</tbody></table>'
            + dig(f"Claim card in full ({counted_words(quotes, 'quote')})",
                  statement_html(row)))  # fmt: skip


def first_record(c):
    """A check's first record, one link labelled by what the file holds (its run and path in the
    title); its other records are in the block's disclosure."""
    path, _, ptr = c["evidence"][0].partition("#")
    path = path.rstrip("/")
    ptr = ptr.strip("/")
    word = RECORD_WORD.get(path.rsplit("/", 1)[-1], path.rsplit("/", 1)[-1])
    href_ = link(path) + (f"#/{ptr}" if ptr else "")
    return f'<a class="ev" href="{e(href_)}" title="{e(c["evidence"][0])}">{e(word)}</a>'


def checks_block(row):
    """The six checks, the entry gate: each one's name (linked to its rule), its state, its cause
    where it has one (a check not decided says why, and who acts, in view: law 2), and one record.
    Every record, trial and long note one click down, by check."""
    caused = any(c["cause"] or (c["state"] == "undecided" and c.get("note")) for c in row["checks"])
    trs, more, count = [], [], 0
    for c in row["checks"]:
        note = c.get("note")
        cause = ""
        if c["cause"]:
            cause = (f'<a class="cw df" href="{CHECKS_PAGE}#cause-{e(c["cause"].replace(" ", "-"))}" '
                     f'title="{e(c["cause"])}">{e(CHECK_CAUSE_WORD[c["cause"]])}</a>')  # fmt: skip
        head = e(note_parts(note)[0]) if note else ""
        at = f' title="{head}"' if head else ""
        if note and c["state"] == "undecided":
            cause += f'<span class="cn"{at}>{quoted(note_parts(note)[1])}</span>'
        cause += decide_html(c, note)
        links = evidence_links(c["evidence"])
        count += len(links)
        full = (f'<p class="cn"{at}>{quoted(note_parts(note)[1])}</p>'
                if note and c["state"] != "undecided" else "")  # fmt: skip
        ran = trials_html(c.get("trials") or ()) + kept_html(row, c["id"])
        if links or full or ran:
            more.append(f'<div><dt>{e(CHECK_NAME[c["id"]])}</dt><dd>{full}{ran}'
                        f'<span class="evs">{"".join(links)}</span></dd></div>')  # fmt: skip
        rec = first_record(c) if c["evidence"] else '<span class="na">none</span>'
        trs.append(
            f'<tr class="ck {c["state"]}" id="ck-{c["id"]}"><th scope="row">'
            f'<a href="{CHECKS_PAGE}#{c["id"]}" title="{e(filled(CHECK_PLAIN[c["id"]]))}">'
            f"{e(CHECK_NAME[c['id']])}</a></th>"
            f'<td class="cst">{state_word(c["state"], STATE_WORD[c["state"]])}</td>'
            + (f"<td>{cause}</td>" if caused else "")
            + f'<td class="cev">{rec}</td></tr>'
        )
    cause_th = '<th scope="col">Cause</th>' if caused else ""
    table = ('<table class="rt ckt cks"><thead><tr><th scope="col">Check</th><th scope="col">'
             f'State</th>{cause_th}<th scope="col">Record</th></tr></thead>'
             f'<tbody>{"".join(trs)}</tbody></table>')  # fmt: skip
    records = dig(f"Every record and trial ({count:,} records)",
                  f'<dl class="ckr">{"".join(more)}</dl>') if more else ""  # fmt: skip
    return table + records


# what each figure of the Cost block means, in a few words under it
COST_MEAN = {"rate": "served over proved is the cost vs serving",
             "parts": "each over a served reply's GPU time, as the whole is",
             "check-time": "verifier wall time", "proof-size": "every proof file, as written"}  # fmt: skip


def on_point(html, whole, frac):
    """A figure padded so figures in one column line up on the decimal point ("2.027" over
    "2,669" reads as two and two thousand, not as two equal widths): `whole` and `frac` are the
    widest whole and fractional parts in the column, in characters of the mono face."""
    num = re.search(r'<span class="n">([^<]*)</span>', html)[1]
    a, dot, b = num.partition(".")
    left, right = whole - len(a), frac - len(dot + b)
    if not (0 <= left <= 9 and 0 <= right <= 9):  # the classes words.css has (no inline style: CSP)
        raise ValueError(f"a figure's padding out of range: {left}, {right}")
    return f'<span class="np pl{left} pr{right}">{html}</span>'


def rates_tile(row):
    """The two rates the multiple divides (CO-8): proved and served, in one unit, aligned on their
    decimal point, each with its unit and GPU; None where the row has no pair."""
    pair = rate_pair(row)
    if pair is None:
        return None
    proved, served, gp, sg = pair
    n = counted(row)
    lines = [(proved, RATE_PROVED, gp, n), (served, "served", sg, None)]
    shown = [fig_html(f, k, sub=BARE, unit=RATE_PER.format(gpu=g)) for f, _, g, k in lines]
    nums = [re.search(r'<span class="n">([^<]*)</span>', h)[1].partition(".") for h in shown]
    whole, frac = max(len(a) for a, _, _ in nums), max(len(d + b) for _, d, b in nums)
    figs = [(e(w), on_point(h, whole, frac)) for (_, w, _, _), h in zip(lines, shown, strict=True)]
    tile = f'<span class="rts">{lines_html(figs)}</span>' + mean(COST_MEAN["rate"])
    return tile


def rates_plot(row):
    """CO-8 drawn: the two rates the band's multiple divides, each a mark at its own rate on one
    decade axis of reply tokens per GPU-second, beside its figure: this system's proved rate the
    solid mark, its model's served rate the outlined one, so the distance between the two marks
    is the multiple. The figures are aligned on their decimal point, as in the tile this
    replaces. Every place is a stored value; the multiple itself is the band's alone. None where
    the row has no rate pair, a rate is not above zero or the two ran on different GPUs (one
    axis holds one unit): the tile then prints what the row has."""
    pair = rate_pair(row)
    if pair is None:
        return None
    proved, served, gp, sg = pair
    if gp != sg or min(proved["value"], served["value"]) <= 0:
        return None
    lines = [("me", RATE_PROVED, proved, counted(row), "me"), ("sv", "served", served, None, "ref")]
    shown = [fig_html(f, k, sub=BARE, unit=RATE_PER.format(gpu=gp)) for _, _, f, k, _ in lines]
    nums = [re.search(r'<span class="n">([^<]*)</span>', h)[1].partition(".") for h in shown]
    whole, frac = max(len(a) for a, _, _ in nums), max(len(d + b) for _, d, b in nums)
    lo, hi = log_extent([proved["value"], served["value"]])
    grid = [log_x(10**k, lo, hi) for k in range(lo, hi + 1)]
    ticks = [(g, decade_words(k)) for g, k in zip(grid, range(lo, hi + 1), strict=True)]
    minor = [log_x(m * 10**k, lo, hi) for k in range(lo, hi) for m in (2, 5)]
    rows = [(cls, e(w), on_point(h, whole, frac), log_x(f["value"], lo, hi), kind)
            for (cls, w, f, _, kind), h in zip(lines, shown, strict=True)]  # fmt: skip
    caption = e(f"{RATE_PER.format(gpu=gp)}, {SCALE_LOG}")
    # the stretch between the two marks, shaded: what the multiple measures
    between = tuple(x for *_, x, _ in rows)
    return dot_plot(defined(FIGURE_HEAD["rate"], "rate"), caption, axis_svg(ticks, minor), grid,
                    rows, RATE_ANCHOR, mean(COST_MEAN["rate"]), between)  # fmt: skip


def parts_tile(row):
    """CO-7 (amended 2026-11-17): the band's multiple in its two parts, commit and proving then
    generation, each with its unit, and the two as one bar from zero, split where the first ends; printed only here, on the system page, and only for a row that
    times them apart. None otherwise."""
    _, _, key = lead_figure(row)
    parts = parts_of(row, key)
    if not parts:
        return None
    n = counted(row)
    figs = [(f'<span class="ptk {c}">{part_term(w)}</span>',
             fig_html(f, n, sub=BARE, note=whole_note(row, key)))
            for (w, f), c in zip(parts, ("pp", "pg"), strict=True)]  # fmt: skip
    # the two parts end to end, from zero to their sum, each in the ink of its word's mark
    segs = [(f["value"], c) for (_, f), c in zip(parts, ("bp", "bg"), strict=True)]
    whole = sum(v for v, _ in segs)
    bar = hbar(segs, whole, h=14, cls="hb pbar") if whole > 0 and min(segs)[0] >= 0 else ""
    return f'<span class="rts">{lines_html(figs)}</span>{bar}' + mean(COST_MEAN["parts"])


def further_parts_tile(row):
    """CO-9 (Q55): a further reply in GPU-seconds, then its two parts, proving then generation,
    each with its range, and the two as one bar from zero split where the first ends; where the
    board splits none, the further reply alone and why there is no split (DEPTH law 2). An
    adapter-reported split says so (its labels are in each part's title)."""
    figs, n = row["figures"], counted(row)
    total = figs["further_reply_gpu_seconds"]
    parts = [(w, figs[k]) for w, k in (("proving", "further_reply_proving_gpu_seconds"),
                                       ("generation", "further_reply_generation_gpu_seconds"))]  # fmt: skip
    lines = [(term(FURTHER, FURTHER_TERM), fig_html(total, n, sub=range_words(total) or BARE))]
    split = row.get("further_split") or {}
    if not all(has(f) for _, f in parts):
        lines.append((e(NO_SPLIT), f'<span class="na">{e(not_split(row))}</span>'))
        return f'<span class="rts">{lines_html(lines)}</span>'
    lines += [(f'<span class="ptk {c}">{part_term(w)}</span>',
               fig_html(f, n, sub=range_words(f) or BARE))
              for (w, f), c in zip(parts, ("pp", "pg"), strict=True)]  # fmt: skip
    segs = [(f["value"], c) for (_, f), c in zip(parts, ("bp", "bg"), strict=True)]
    whole = sum(v for v, _ in segs)
    bar = hbar(segs, whole, h=14, cls="hb pbar") if whole > 0 and min(segs)[0] >= 0 else ""
    how = ""
    if split.get("source") == "adapter_phases" and split.get("tolerance") is not None:
        how = mean(ADAPTER_SPLIT.format(tol=f"{split['tolerance'] * 100:g}\u00a0%"))
    return f'<span class="rts">{lines_html(lines)}</span>{bar}{how}'


def one_time_tile(row):
    """CO-9 (Q55): the one-time work, once, in GPU-hours, with its range and n, never divided by
    the replies; under it its mark, the replies after which it is at most 5 % of the total."""
    figs, n = row["figures"], counted(row)
    f, mark = figs["one_time_gpu_seconds"], figs["one_time_mark_replies"]
    count = f["n"] if f["n"] is not None else n
    sub = SEP.join(w for w in (f"n\u00a0=\u00a0{count}" if count else "", range_words(f)) if w)
    out = fig_html(f, n, sub=sub)
    if has(mark):
        out += f'<span class="otm">{e(ONE_TIME_MARK)} {fig_html(mark, sub=BARE)}</span>'
    return out


def further_cells(row):
    """CO-9's tiles of the Cost block: the further reply in two parts, the one-time work and its
    mark, then (as for every board) verify time and proof size, and the cost in USD, the one-time
    work's among it."""
    figs, n = row["figures"], counted(row)
    b = rung_of(row)["baseline"] or {}
    cells = [(defined(FURTHER_PARTS_HEAD, "multiple"), further_parts_tile(row), "parts"),
             (defined(FIGURE_HEAD["one-time"], "one-time"), one_time_tile(row), "one-time")]  # fmt: skip
    for k, f in (("check-time", figs["verify_seconds_per_reply"]),
                 ("proof-size", figs["proof_bytes_per_reply"])):  # fmt: skip
        sub = cost_sub(f, n, FIGURE_HEAD[k], own=True)
        cells.append((defined(FIGURE_HEAD[k], k), fig_html(f, n, sub=sub) + mean(COST_MEAN[k]), ""))
    usd, price = figs["further_reply_usd_per_reply"], S.V["price"]
    if has(usd):
        under = [(e(RATE_PROVED), fig_html(usd, n, sub=BARE))]
        if has(b.get("usd_per_reply")):
            under.append(("served", fig_html(b["usd_per_reply"], sub=BARE)))
        if has(figs["one_time_usd"]):
            under.append(("once", fig_html(figs["one_time_usd"], n, sub=BARE)))
        if price and has(price["usd_per_gpu_hour"]):
            basis = f"basis: {price['basis']}"
            under.append(("H200", fig_html(price["usd_per_gpu_hour"], sub=BARE, note=basis)))
        cells.append((defined(FIGURE_HEAD["cost"], "cost"),
                      f'<span class="usd">{lines_html(under)}</span>', ""))  # fmt: skip
    return cells


def cost_block(row):
    """The Cost block (CO-1 to CO-8), led by its figures: the two rates the band's multiple
    divides, drawn on one axis (`rates_plot`; a tile where the row has no rate pair), its two
    parts where the row times them apart (CO-7, printed nowhere else), verify
    time, proof size and, small, the cost in USD; what they share (scope,
    n, GPUs, evidence) once over them. How each side ran, every GPU time and the serving ladder
    one click down (`cost_html`)."""
    figs, n = row["figures"], counted(row)
    b = rung_of(row)["baseline"] or {}
    _, lead, key = lead_figure(row)
    count = (lead or {}).get("n") or n
    scope = {"session_multiple": whole_line, "further_reply_multiple": lambda _, c: further_line(c)
             }.get(key, lambda _, c: steady_line(c))(row, count)  # fmt: skip
    scope = (e(scope).replace("whole sessions", term("whole sessions", "Whole session"), 1)
             .replace(FURTHER, term(FURTHER, FURTHER_TERM), 1))  # fmt: skip
    bound = sorted({s.get("gpus") for s in row["sessions"] if s.get("gpus")})
    gpus = e(f"{' or '.join(f'{g:,}' for g in bound)} × {gpu_name(row)}") if bound else ""
    shown = [(k, f) for k, f in (("multiple", lead), ("verify", figs["verify_seconds_per_reply"]),
                                 ("size", figs["proof_bytes_per_reply"])) if has(f)]  # fmt: skip
    tier = evidence_words(shown) if shown else ""
    cells = []
    plot = rates_plot(row)  # the two rates, drawn; else as a tile
    rates = None if plot else rates_tile(row)
    if rates:
        cells.append((defined(FIGURE_HEAD["rate"], "rate"), rates, RATE_ANCHOR))
    if further():  # CO-9 (Q55): the further reply's parts, the one-time work, the two routes
        tier = evidence_words([(k, f) for k, f in (
            ("multiple", lead), ("proving", proving_figure(row)),
            ("one-time", figs["one_time_gpu_seconds"]),
            ("verify", figs["verify_seconds_per_reply"]),
            ("size", figs["proof_bytes_per_reply"])) if has(f)])  # fmt: skip
        return (scope_html(scope, gpus, tier) + (plot or "")
                + tiles([*cells, *further_cells(row)], "drawn" if plot else "")
                + f'<p class="cmn">{e(ROUTES)}</p>'
                + dig("GPU time, hardware and serving", cost_html(row)))  # fmt: skip
    if split := parts_tile(row):
        cells.append((defined(PARTS_HEAD, "multiple"), split, "parts"))
    for k, f in (("check-time", figs["verify_seconds_per_reply"]),
                 ("proof-size", figs["proof_bytes_per_reply"])):  # fmt: skip
        sub = cost_sub(f, n, FIGURE_HEAD[k], own=True)
        cells.append((defined(FIGURE_HEAD[k], k), fig_html(f, n, sub=sub) + mean(COST_MEAN[k]), ""))
    usd = (
        figs["session_usd_per_reply"] if key == "session_multiple" else figs["steady_usd_per_reply"]
    )
    price = S.V["price"]
    if has(usd):
        under = [(e(RATE_PROVED), fig_html(usd, n, sub=BARE))]
        if has(b.get("usd_per_reply")):
            under.append(("served", fig_html(b["usd_per_reply"], sub=BARE)))
        if price and has(price["usd_per_gpu_hour"]):
            basis = f"basis: {price['basis']}"
            under.append(("H200", fig_html(price["usd_per_gpu_hour"], sub=BARE, note=basis)))
        cells.append((defined(FIGURE_HEAD["cost"], "cost"),
                      f'<span class="usd">{lines_html(under)}</span>', ""))  # fmt: skip
    return (
        scope_html(scope, gpus, tier)
        + (plot or "")
        + tiles(cells, "drawn" if plot else "")
        + dig("GPU time, hardware and serving", cost_html(row))
    )


def fidelity_plot(row, fid, tf, mine):
    """SI-9 drawn: top-token agreement on one axis, from the ten under the lowest drawn value
    (90 % at most) to 100 %, each end labelled; the rows of the table one click down (Q48: the
    model's quantized copies and the bar's row, FI-3's in their order then any only this pass
    has) as outlined marks and this system as the one solid mark, one row each, highest first as
    the table orders them, each beside its labelled figure. A row that did not run prints "not
    run" and is not drawn. n is said once, in the caption, where the drawn rows share it; else
    under each figure. None where nothing ran."""

    def ok(t):
        return t is not None and t["status"] == "ok" and t.get("percent") is not None

    def named(cid):
        name, title = control_name(cid)
        words = name.partition(" (")[0]
        said = term(words, "Q8_0 and Q4_K_M") if cid in FIDELITY_AGAINST else e(words)
        return f'<span title="{e(title)}">{said}</span>' if title else said

    bar = ((fid or {}).get("bar") or {}).get("control")
    fcs = {c["id"]: c for c in (fid or {}).get("controls") or []}
    tcs = {c["id"]: c for c in tf.get("controls") or []}
    ids = [i for i in (*fcs, *(k for k in tcs if k not in fcs)) if i == bar or FID_COPY.match(i)]
    lines = [(mine, row["fidelity"], "me", e(name_of(row)), "me"),
             *((tcs.get(i), fcs.get(i), "cp", named(i), "ref") for i in ids)]  # fmt: skip
    drawn = [t for t, *_ in lines if ok(t)]
    if not drawn:
        return None
    lo = min(10 * math.floor(min(t["percent"] for t in drawn) / 10), 90)
    grid = [lin_x(v, lo, 100) for v in range(lo, 101, 10)]
    ticks = [(x, f"{v} %") for x, v in zip(grid, range(lo, 101, 10), strict=True)]
    ns = {t["n"] for t in drawn}  # one n for the drawing, or each row's under its figure
    rows = []
    for t, _, cls, word, kind in sorted(lines, key=lambda r: fid_score(r[0], r[1]), reverse=True):
        own = [f"n\u00a0=\u00a0{t['n']:,} prompts"] if ok(t) and len(ns) > 1 else []
        x = lin_x(t["percent"], lo, 100) if ok(t) else None
        rows.append((cls, word, agree_html(t, tf, own), x, kind))
    caption = "top-token agreement"
    if len(ns) == 1:
        caption += f", n\u00a0=\u00a0{next(iter(ns)):,} prompts"
    head = defined(FIGURE_HEAD["fidelity"], FIGURE_ANCHOR["fidelity"])
    return dot_plot(head, e(caption), axis_svg(ticks, wide=PLOT_BESIDE), grid, rows)


def proofs_html(row, mine):
    """FI-16: the row's pass against its proofs, from the board's count: the positions where a
    proved reply starts like the original's (up to and including the first token that differs)
    and how many of them the row's code gave the proved token at, then the same at the
    positions where the two replies part; "not compared" where the row has no proved reply for
    every prompt. It gates nothing."""
    tie = mine.get("proved_tokens")
    if tie is None:
        return f'<span class="na">not compared</span>{mean(TF_NOT_PROVED)}'
    split = TF_PROVED_SPLIT.format(agreeing=tie["split_agreeing"], positions=tie["split_positions"])
    return (f'<span class="pw">{e(TF_PROVED.format(**tie))}</span>'
            f'<span class="sub">{e(split)}</span>'
            f"{mean(TF_PROVED_MEAN.format(name=name_of(row)))}")  # fmt: skip


def fidelity_block(row):
    """The Fidelity block (SI-9): the Fidelity figure with its n among the quantized copies, drawn
    on one axis (`fidelity_plot`; as tiles, with the 8-bit and 4-bit copies, where none ran), what
    the row proves, its count against the proofs (FI-16, `proofs_html`), the Fidelity check's
    state with the matched leading tokens and the bar, and KL to the original or "not measured"
    (law 2). Every copy, the tests, the publisher's words on the number format and the run's
    sources one click down (`fidelity_html`)."""
    rung = rung_of(row)
    fid, tf = rung["fidelity"], rung.get("teacher_forced")
    mine = (tf or {}).get("rows", {}).get(row["system"]) if tf else None
    cells = []
    plot = fidelity_plot(row, fid, tf, mine) if tf and mine is not None else None
    if tf and mine is not None and not plot:
        sub = [f"top-token agreement, n\u00a0=\u00a0{mine['n']:,} prompts"]
        cells.append((defined(FIGURE_HEAD["fidelity"], FIGURE_ANCHOR["fidelity"]),
                      agree_html(mine, tf, sub), ""))  # fmt: skip
    proved = proved_words(row).removeprefix(f"{PROVED_HEAD}: ")
    if proved:
        p = row["precision"]
        cells.append((term("Proved", "Proved"),
                      f'<span class="pw">{e(proved)}</span>{mean(p["proved"])}', "proved"))  # fmt: skip
    if tf and not plot:
        by = {c["id"]: c for c in tf.get("controls") or []}
        copies = [(e(COPY_WORD[i]), agree_html(by[i], tf, [])) for i in FIDELITY_AGAINST if i in by]
        if copies:
            cells.append((term("Copies", "Q8_0 and Q4_K_M"), lines_html(copies), ""))
    if mine is not None and mine["status"] == "ok":
        cells.append((defined(PROOFS_HEAD, FIGURE_ANCHOR["fidelity"]), proofs_html(row, mine), ""))
    check = next(c for c in row["checks"] if c["id"] == "fidelity")
    said = state_word(check["state"], STATE_WORD[check["state"]])
    own, bar = row["fidelity"], (fid or {}).get("bar")
    if own is not None and own.get("mean_prefix") is not None:
        mine_n = f"n = {own['n']:,} replies"
        at = row["record"] + "/fidelity/mean_prefix"
        lines = [(e(name_of(row)), plain(own["mean_prefix"], "tokens", at, mine_n))]
        ids = [c["id"] for c in (fid or {}).get("controls") or []]
        if bar is not None and bar["control"] in ids:
            i = ids.index(bar["control"])
            at = f"{fid['record']}/controls/{i}/mean_prefix"
            lines.append(("pass bar", plain(bar["mean_prefix"], "tokens", at)))
        said += lines_html(lines) + mean("matched leading tokens, mean")
    cells.append((defined("Fidelity check", "fidelity"), said, ""))
    kl = (row["fidelity"] or {}).get("kl")
    cells.append((defined(FIGURE_NAME["kl"], "kl"),
                  fig_html(kl) if has(kl) else '<span class="na">not measured</span>', ""))  # fmt: skip
    return (
        (plot or "")
        + tiles(cells, "drawn" if plot else "")
        + dig("The copies, the tests and the sources", fidelity_html(row))
    )


def sessions_block(row):
    """SE-3: the counted sessions in one table (slot, run, the whole session's GPU time per
    reply, its generation part, the steady one or why there is none), the release groups once
    over it; the sessions not counted, by kind and count, in view, and listed one click down."""
    rec = row["record"]
    if not row["sessions"]:
        return '<p class="none">No counted session.</p>'
    gen = any(s.get("generation_gpu_seconds_per_reply") is not None for s in row["sessions"])
    groups = {len(s["groups"]) for s in row["sessions"]}
    steady, whole = (f"scope: {SCOPE_WORD[k]}" for k in ("prove.steady", "whole_wall"))
    heads = [("Slot", e("Slot")), ("Run", e("Run")),
             ("Session", term("Session", "Whole session")),
             *([("Generation", part_term("generation"))] if gen else []),
             (M_COL, term(M_COL, "Steady state")),
             *([("Release groups", e("Release groups"))] if len(groups) > 1 else [])]  # fmt: skip
    trs = []
    for k, s in enumerate(row["sessions"]):
        at = f"{rec}/sessions/{k}"
        g = s.get("generation_gpu_seconds_per_reply")
        cells = [str(s["slot"]), run_records(row, s["run_id"]),
                 plain(s["session"], GPU_S, f"{at}/session", whole),
                 *([plain(g, GPU_S, f"{at}/generation_gpu_seconds_per_reply", whole)] if gen else []),
                 steady_cell(s, at, steady),
                 *([f"{len(s['groups']):,}"] if len(groups) > 1 else [])]  # fmt: skip
        trs.append("<tr>" + "".join(f'<td data-l="{e(h)}">{c}</td>'
                                    for (h, _), c in zip(heads, cells, strict=True)) + "</tr>")  # fmt: skip
    ths = "".join(f'<th scope="col">{h}</th>' for _, h in heads)
    table = (
        f'<table class="rt stk"><thead><tr>{ths}</tr></thead><tbody>{"".join(trs)}</tbody></table>'
    )
    once = f"{next(iter(groups)):,} release groups in each" if len(groups) == 1 else ""
    others = [(len(row.get(k) or ()), w) for k, w in (("incomplete", "incomplete"),
                                                      ("replaced", "replaced"),
                                                      ("ineligible", "ineligible"))]  # fmt: skip
    kept_out = ", ".join(f"{k:,} {w}" for k, w in others if k)
    scope = scope_html(e(f"{len(row['sessions']):,} counted"), e(once),
                       e(f"not counted: {kept_out}") if kept_out else "")  # fmt: skip
    rest = sessions_html(row, counted_table=False)
    return scope + table + (dig("Sessions not counted", rest) if rest else "")


PAPER_WORD = "PDF, at the commit this row runs"  # the band's Paper fact, linked (D5)
NAME_SIZES = (6, 12, 20)  # a system's name on its band: one size per length up to these
SHARE = (
    "Share",
    "Share card",
    "Copy link",
    "Copied",
)  # the share group: its name, its actions, done
# the card link's title (D4): what clicking it does, said before it is clicked
SHARE_CARD_TITLE = ("This page's share card is an image of its glyph and figure, the one a link "
                    "preview shows. It opens in a new tab, where you can save or share it.")  # fmt: skip


def share_html(row):
    """The share group's actions: the page's share card, opened in a new tab as the image it is
    (a reader who clicks "Share card" sees it, then saves or shares it; it no longer downloads
    unannounced), while its picture is the one this build's source was rendered to (none
    otherwise), and Copy link, which words.js shows and runs (it copies the page's canonical
    address and says so)."""
    pid = row["page"]
    card = ""
    if card_current(pid):
        v = cards_record()[pid]["png"][:12]
        card = (f'<a href="/og/{e(pid)}.png?v={e(v)}" target="_blank" rel="noopener" '
                f'title="{e(SHARE_CARD_TITLE)}">{e(SHARE[1])}'
                '<span class="sr"> (image, opens in a new tab)</span></a>')  # fmt: skip
    return (card + f'<button type="button" class="cplink" data-done="{e(SHARE[3])}" hidden>'
            f"{e(SHARE[2])}</button>")  # fmt: skip


def pin_html(pin, name):
    """A row that runs a change to the publisher's code, in label-and-fact form (SI-3(c), amended
    2026-11-15): the pull request, whether upstream merged it, who wrote it (linked to the
    mandate's ties), and what the publisher's own commit did on the level's request, linked to
    its record."""
    sep = f'<span class="sep">{SEP}</span>'
    merged = "merged upstream" if pin["merged"] else "not merged upstream"
    who = '<a href="/mandate#ties">by this project\'s owner</a>' if pin["by_owner"] else ""
    record = (f' (<a href="{e(link(pin["record"]))}" title="{e(pin["record"])}">record</a>)'
              if pin.get("record") else "")  # fmt: skip
    facts = [f'<a href="{e(pin["url"])}">PR #{pin["pull"]:,}</a>', e(merged), who,
             f"upstream <code>{e(pin['upstream_commit'][:7])}</code>: "
             f"{e(pin['upstream_outcome'])}{record}"]  # fmt: skip
    return sep.join(f'<span class="nw">{f}</span>' if i < 3 else f
                    for i, f in enumerate(facts) if f)  # fmt: skip


def system_page(row):
    """A system on a model (SI-3): the band (its name, sized by its length, never more than two
    lines; its one figure on the right, labelled for what it is; the facts under them, the
    publisher's repository at the row's commit among them), then the five criteria (the glyph's
    petals, in words and tracks), the statement, the checks, the cost, fidelity and, last, the
    sessions (the audit trail)."""
    rung = rung_of(row)
    sysd = S.V["systems"][row["system"]]
    name = name_of(row)
    facts = [("f-st", "Standing", standing_html(row, "")),
             ("f-md", "Model", f'<a href="/#{e(rung["id"])}">{nobreak(rung["model"])}</a>'
              f'<span class="msz">{e(rung["publisher"])}{SEP}'
              f'{e(architecture(rung["parameters_total"], rung.get("parameters_active")))}</span>')]  # fmt: skip
    source = ""
    pin = sysd.get("pin")
    if pin:  # a change to the publisher's code: the source is its pull request (SI-3)
        source = (f'<a href="{e(pin["url"])}">{nobreak(sysd["repo"] or name)} '
                  f'<span class="nw">#{pin["pull"]:,}</span></a>')  # fmt: skip
        facts.append(("f-src", "Source", source))
    elif sysd["repo"]:  # the publisher's repository, at the commit the row runs
        at = f"/tree/{e(row['commit'])}" if row["commit"] else ""
        source = (f'<a href="https://github.com/{e(sysd["repo"])}{at}">'
                  f'{nobreak(sysd["repo"])}</a>')  # fmt: skip
        facts.append(("f-src", "Source", source))
    paper = ""
    if sysd.get("paper"):  # D5: the publisher's paper, at the row's commit, where it has one
        paper = f'<a href="{e(sysd["paper"])}">{e(PAPER_WORD)}</a>'
        facts.append(("f-pap", "Paper", paper))
    if pin:  # SI-3 (amended 2026-11-15): the version the row runs, at depth 2
        facts.append(("f-pin", "Version", pin_html(pin, name)))
    share = share_html(row)
    size = next((i + 1 for i, k in enumerate(NAME_SIZES) if len(name) <= k), len(NAME_SIZES) + 1)
    # the figure's plain name, the figure, and under it, once, what was counted and n (CO-5)
    unranked = "" if row["position"] is not None else " unr"
    if further():  # CO-9: the two multiples
        band_fig = f'<p class="sbm two{unranked}">{band_two(row)}</p>'
    else:
        label, lead = FIGURE_HEAD["multiple"], band_figure(row)
        lead += rate_html(row, f"#{RATE_ANCHOR}")
        band_fig = (f'<p class="sbm{unranked}"><span class="sbl">{defined(label, "multiple")}'
                    f"</span>{lead}</p>")  # fmt: skip
    band_ = (
        f'<section class="mast mast-sys sysb" aria-labelledby="h-name"><div class="mast-in">'
        f'<div class="sb"><h1 id="h-name" class="sysname nm{size}">{e(name)}</h1>'
        f"{band_fig}</div>"
        '<dl class="facts">'
        + "".join(f'<div class="{c}"><dt>{k}</dt><dd>{v}</dd></div>' for c, k, v in facts)
        + "</dl></div></section>"
    )
    # a phone's band holds the name, the model, the standing and the figure, and no more: the
    # source and the share group stand at the page's foot there (the source from 560 px down,
    # the share group from 760 px down, where the strip has no room for it)
    foot = (
        '<dl class="fend">'
        + (f'<div class="f-src"><dt>Source</dt><dd>{source}</dd></div>' if source else "")
        + (f'<div class="f-pap"><dt>Paper</dt><dd>{paper}</dd></div>' if paper else "")
        + f'<div class="fshr"><dt>{e(SHARE[0])}</dt><dd>{share}</dd></div></dl>'
    )
    # the share group at the strip's end on a wide screen
    share_strip = f'<div class="shr" role="group" aria-label="{e(SHARE[0])}">{share}</div>'
    # the criteria keep the section's address (#glyph) and each one its own (#petal-<id>), so
    # links made before 2026-11-22 still land
    parts = (("glyph", "Criteria"), ("statement", "Statement"),
             ("checks", "Checks"), ("cost", "Cost"), ("fidelity", "Fidelity"),
             ("sessions", "Sessions"))  # fmt: skip
    body = f"""
{header("system")}
<main id="main" class="sys">
  {band_}
  {pnav(name, parts, share_strip)}
  <div class="wrap">
    {section("glyph", "Criteria", criteria_block(row))}
    {section("statement", "Statement", statement_block(row))}
    {section("checks", "Checks", checks_block(row))}
    {section("cost", "Cost", cost_block(row))}
    {section("fidelity", "Fidelity", fidelity_block(row))}
    {section("sessions", "Sessions", sessions_block(row))}
    {foot}
  </div>
</main>
{footer()}"""
    # depth 0: where the system stands and its one figure with its parts, each with its unit (as
    # the card's alt says); what was counted is a step down, under the band's figure
    desc = share_words(row)
    return page(name, desc, body, "system syspage", row["page"], row["page"])


def build_system(pid):
    return system_page(S.PAGE[pid])


def linked(text, key):
    """A rule's words escaped, the phrase REASON_LINK names for `key` linked to where Learn gives
    the rule's reason; any other words escaped alone."""
    if key not in REASON_LINK:
        return e(text)
    phrase, address = REASON_LINK[key]
    head, found, tail = text.partition(phrase)
    if not found:
        raise RuntimeError(f"no {phrase!r} in the words of {key}")
    return f'{e(head)}<a href="{e(address)}">{e(phrase)}</a>{e(tail)}'


def rule_lines(lines, ids=(), at=""):
    """Labelled lines: (label, words) pairs, the level's constants filled in; a line with no label
    is its block's own. A label in `ids` is an address of its own, its spaces as hyphens. `at`
    names the lines' constant in REASON_LINK: the phrase it names links to the rule's reason (the
    label, where the label is the phrase)."""

    def line(k, v):
        key = (at, k)
        to_label = key in REASON_LINK and REASON_LINK[key][0] == k
        dt = linked(k, key) if to_label else e(k)
        dd = e(filled(v)) if to_label else linked(filled(v), key)
        place = f' id="{e(k.replace(" ", "-"))}"' if k in ids else ""
        return f"<div{place}><dt>{dt}</dt><dd>{dd}</dd></div>"

    return "".join(line(k, v) for k, v in lines)


def rules(lines, ids=(), at=""):
    """`rule_lines` as one list."""
    return f'<dl class="cs">{rule_lines(lines, ids, at)}</dl>'


def title_band(title, cls="ttl", kicker="", under=""):
    """The band of a page that is not a system's (the checks, the mandate, the 404): its title
    at the home title's size; `kicker` over it, where the page stands under another (the
    mandate under Learn); `under` it, a line in the band's own ink."""
    kick = f'<p class="kick">{kicker}</p>' if kicker else ""
    return (f'<div class="mast mast-t"><div class="mast-in">{kick}<h1 id="h-name" class="{cls}">'
            f"{e(title)}</h1>{under}</div></div>")  # fmt: skip


def cause_rule(cause, text):
    """A petal cause's rule (PETAL_CAUSE_RULE) with its opening words ("Not stated (drawn as an
    outline)", "Not decided (drawn hollow), Fidelity only") drawn as the chip a system page
    prints for such a petal, those words kept for a screen reader; what follows them ("Fidelity
    only") in words."""
    state_words = next(k for k in PETAL_CAUSE_DRAW if text.startswith(k))
    after = text[len(state_words) :]
    only, rest = after[2:].partition(": ")[::2] if after.startswith(", ") else ("", after[2:])
    state, form = PETAL_CAUSE_DRAW[state_words]
    drawn = chip(state, STEP_WORD[step_key("red" if state == "red" else None, cause)], form)
    lead = f"{e(only)}: " if only else ""
    return (f'<span aria-hidden="true">{drawn}</span><span class="sr">{e(state_words)}'
            f'{", " if only else ": "}</span>{lead}{e(rest)}')  # fmt: skip


INK = {"green": "green", "amber_upper": "amber", "amber_lower": "amber", "red": "red",
       None: "hollow"}  # a stored step's ink, as view.STEP_STATE  # fmt: skip


def step_chip(key):
    """A STEP_WORD key drawn as the chip a system page prints for it: its ink, and its form (cut
    for Partly met, open for Not stated)."""
    step, cause = key if isinstance(key, tuple) else (key, None)
    form = "cut" if step == "amber_lower" else "open" if cause == "not_stated" else ""
    return chip(INK[step], STEP_WORD[key], form)


def step_rule(rule):
    """A step's rule: a sentence, or its bullets as a list."""
    if isinstance(rule, str):
        return e(rule)
    return '<ul class="srl">' + "".join(f"<li>{e(r)}</li>" for r in rule) + "</ul>"


def petal_rules(p):
    """A petal on the checks page (depth 4, amended 2026-11-16): its name and field term, its
    plain sentence, whom it protects, the field's question; then each step it can take as the chip
    a system page prints beside its rule in one sentence, top step first; its terms; and what it
    leaves to another place."""
    lines = rule_lines((("", PETAL_PLAIN[p]), ("protects", PETAL_PROTECTS[p]),
                        ("question", PETAL_QUESTION[p])))  # fmt: skip
    steps = "".join(f"<div><dt>{step_chip(k)}</dt><dd>{step_rule(rule)}</dd></div>"
                    for k, rule in PETAL_RULE[p])  # fmt: skip
    more = rule_lines(PETAL_MORE.get(p, ()))
    if p in PETAL_NOT_GRADED:
        more += rule_lines((("", PETAL_NOT_GRADED[p]),))
    return (f'<div class="chk" id="{p}"><h3 class="cn2">{e(PETAL_NAME[p])}</h3>'
            f'<p class="cterm">{e(PETAL_TERM[p])}</p><dl class="cs">{lines}{steps}{more}</dl>'
            "</div>")  # fmt: skip


def know_html():
    """What we test and what we read (KNOW_LINES): what a line is about, where a row shows it,
    each check, petal and figure linked to its rule on this page by the name the site gives it,
    and how it is known."""

    def where(ids):
        names = []
        for i in ids:
            if i == "figures":
                names += [(f, FIGURE_NAME[f]) for f in figure_rules(S.V["cost_rule"])]
            else:
                # a check and a petal of one name are told apart (SPEC 5.1): Fidelity check,
                # Fidelity petal
                if i in CHECK_NAME:
                    name = CHECK_NAME[i] + (" check" if CHECK_NAME[i] in PETAL_NAME.values()
                                            else "")  # fmt: skip
                elif i in PETAL_NAME:
                    name = PETAL_NAME[i] + (" petal" if PETAL_NAME[i] in CHECK_NAME.values()
                                            else "")  # fmt: skip
                else:
                    name = KNOW_WHERE[i]
                names.append((i, name))
        return ", ".join(f'<a href="#{e(a)}">{e(n)}</a>' for a, n in names) or "none"

    rows = [[e(what), where(ids), e(KNOW_WORD[how])] for what, ids, how in KNOW_LINES]
    return (f'<h3 class="sub-h" id="what-we-test">{e(KNOW_HEAD)}</h3>'
            + stacked(list(KNOW_COLS), rows))  # fmt: skip


def source_html(src):
    """The fact that sets a not-run reason, linked to where it is read; nothing for `not yet
    run`, which needs none (SI-4b)."""
    return f'<a href="{e(src["url"])}">{e(curly(src["words"]))}</a>' if src else ""


def not_run_rules():
    """SI-4b: the order of the reasons a system is not run, each reason with its words and the
    systems it holds, each system with the fact that sets its reason, linked to its source."""
    groups: dict[str, list[dict]] = {}
    for r in S.V["not_run"]:
        groups.setdefault(r["reason"], []).append(r)
    blocks = "".join(
        f'<div class="chk" id="nr-{e(reason.replace(" ", "-"))}"><h3 class="cn2">'
        f'{e(reason[0].upper() + reason[1:])}</h3><dl class="cs">'
        + rule_lines((("", words),))
        + "".join(f'<div><dt>{e(r["name"])}</dt><dd>{source_html(r["source"])}</dd></div>'
                  for r in sorted(groups.get(reason, []), key=lambda r: r["name"].lower()))
        + "</dl></div>"
        for reason, words in NOT_RUN_RULE.items()
    )  # fmt: skip
    return f'<p class="rd">{e(NOT_RUN_LEAD)}</p><div class="clist">{blocks}</div>'


def build_checks():
    """The rules behind a row: the request and the six checks as the entry gate (RFC-0018 §The six
    checks) with what is not tested, then the undecided causes; the figures (§Cost, FI-7, SI-9);
    the order rule (§Order); last the five petals (§The glyph), the key beside their rules, then
    why a petal is red or undecided, and what "our reading" means."""
    ids = list(S.V["petals"])
    names = [PETAL_NAME[p] for p in ids]
    glyph = glyph_svg(GLYPH, ["key"] * len(names), names=names, cls="pie-svg big",
                      hrefs=[f"#{p}" for p in ids])  # fmt: skip
    # each petal: its plain sentence, then its steps as the chips a system page prints (STEP_WORD)
    petals = "".join(petal_rules(p) for p in ids)
    # the six checks: on a wide screen one table (words.css), its heads over the passes and fails
    # lines (their own terms then left to a screen reader), each check's name and plain sentence in
    # its first column; a block each on a narrow one
    checks = '<div class="ckh" aria-hidden="true"><span>Check</span><span>Passes when</span>' + \
        "<span>Fails when</span></div>" + "".join(
        f'<div class="chk" id="{c}"><div class="chd"><h3 class="cn2">{e(CHECK_NAME[c])} check</h3>'
        f'<p class="ckp">{e(filled(CHECK_PLAIN[c]))}</p></div>'
        + rules((("passes", CHECK_HELD[c]), ("fails", CHECK_FAILED[c]), *CHECK_MORE.get(c, ())),
                at="CHECK_MORE")
        + "</div>"
        for c in S.V["checks"]
    )  # fmt: skip
    figs = figure_rules(S.V["cost_rule"])  # Q55: the rule the board was built by
    figures = "".join(
        f'<div class="chk" id="{f}"><h3 class="cn2">{e(FIGURE_NAME[f])}</h3>'
        f"{rules(figs[f], at='FIGURE_RULE')}</div>"
        for f in figs
    )
    # the request's one home on the site (SI-8), and what passed means
    gate = (
        f"Every runnable system pinned to a public commit receives the exact same request: "
        f"{request_words()}. Generation never stops early on an end-of-sequence token. A system "
        "passes on a model when all six checks pass."
    )
    # what the glyph is and what its petals rest on, at the head of their rules (§The glyph, GL-1,
    # GL-2, GL-8, FM-2, MC-5, §Reading the tables)
    summary = (
        "The glyph shows how close a system comes to an ideal prover across five separate "
        "properties, never summed into a single score. Four petals are graded from the "
        "publisher's documentation at the pinned commit, while Fidelity comes from our own "
        "fidelity run (and stays undecided whenever the Fidelity check does). A failed check "
        "flips any contradicted petal to Failed, an undecided check lowers nothing, and a passed "
        "check raises none. Whenever a rule is ambiguous, the lower grade applies."
    )
    # the step words once, each on its chip (the inks are drawn, never named: SI-6)
    legend = ('<p class="rd slg">' + " ".join(step_chip(k) for k in STEP_WORD) + "</p>"
              f'<p class="rd">{e(PETAL_STEPS_FOOT)}</p>')  # fmt: skip
    # why a petal is red or hollow: one address per cause, which the grade word of a system page's
    # criterion links, in a block after the key's (a block inside it would be read as a sixth
    # petal: words.js pairs the key's arms with `.cwrap .chk`); then what "our reading" means
    # (#reading, which a criterion's "our reading" links)
    petal_causes = "".join(
        f'<div id="cause-{e(k)}"><dt>{e(CAUSE_WORD[k])}</dt><dd>{cause_rule(k, v)}</dd></div>'
        for k, v in PETAL_CAUSE_RULE.items()
    )
    after_key = (
        '<div class="clist"><div class="chk"><h3 class="cn2">Why a petal is low or not decided</h3>'
        f'<dl class="cs">{petal_causes}</dl></div>'
        f'<div class="chk" id="reading"><h3 class="cn2">{e(BASIS_READING[1].capitalize())}</h3>'
        f'<dl class="cs">{rule_lines((("", READING_RULE),))}</dl></div></div>'
    )
    # why a check is undecided, the six checks' last block (#undecided, which a system page's
    # cause links): a cause's words are inline on a system page; here each is a sentence
    causes = "".join(f'<div id="cause-{e(k.replace(" ", "-"))}"><dt>{e(k)}</dt>'
                     f"<dd>{e(v[0].upper() + v[1:])}.</dd></div>"
                     for k, v in CHECK_CAUSE_WORD.items())  # fmt: skip
    undecided = (f'<div class="chk" id="undecided"><h3 class="cn2">Checks not decided</h3>'
                 f'<dl class="cs">{rule_lines((("", CHECK_CAUSE_LEAD),))}{causes}</dl></div>')  # fmt: skip
    passed = (f'<p class="rd" id="passed">{e(gate)}</p>'
              f'<p class="rd" id="not-tested">{linked(NOT_TESTED, ("NOT_TESTED", ""))}</p>'
              f'<p class="rd" id="binding">{e(BINDING_GAP)}</p>')  # fmt: skip
    six = (f'{how_link("rd")}{passed}<div class="clist six">{checks}</div><div class="clist">{undecided}</div>'
           f"{know_html()}")  # fmt: skip
    parts = (("checks", "Six checks"), ("figures", "Figures"), ("order", "Order"),
             ("glyph", "Glyph"), ("not-run", "Not run"))  # fmt: skip
    # the order rule; "largest model with a passed row" (OR-6, recorded on the board) keeps an
    # address of its own
    order = rules(ORDER_RULE, ids=("unranked", "largest model with a passed row"), at="ORDER_RULE")
    key = (f'<p class="rd">{linked(summary, ("summary", ""))}</p>{legend}'
           f'<div class="cwrap"><div class="gbig">{glyph}</div><div class="clist">{petals}'
           f"</div></div>{after_key}")  # fmt: skip
    body = f"""
{header("checks")}
<main id="main" class="sys">
  {title_band("Checks")}
  {pnav("Checks", parts)}
  <div class="wrap">
    {section("checks", "The six checks", six)}
    {section("figures", "Figures", f'<div class="clist">{figures}</div>')}
    {section("order", "Order", order)}
    {section("glyph", "Glyph", key)}
    {section("not-run", "Systems not run", not_run_rules())}
  </div>
</main>
{footer()}"""
    return page("Checks", CHECKS_DESC, body, "system checkspage", CHECKS_PAGE.strip("/"), "home")


def build_mandate():
    """The mandate: the belief as the headline, then who runs it (with the members, once any has
    agreed), what we do, what we do not do and how to check us (the level and its file among
    them: the footer's level cell leads there). A line bound by a rule prints the rule under its
    label, the document and the rule's id as the link's words, the link to the section of the
    file that holds it (DEPTH law 3: a phone and a keyboard see it). The names in a line are the
    facts file's (`credit`), linked as the footer links them."""

    def label(text, name, path):
        if not path:
            return e(text)
        if isinstance(path, str) and path.startswith("https://"):  # a source outside the repo
            return f'{e(text)}<a class="rl" href="{e(path)}">{e(name)}</a>'
        names, paths = (name, path) if isinstance(path, tuple) else ((name,), (path,))
        file = paths[0].split("#", 1)[0]
        rfc = re.match(r"rfcs/(\d{4})-", file)
        doc = f"RFC-{rfc[1]}" if rfc else file.rsplit("/", 1)[-1]
        if len(paths) == 1:
            return (f'{e(text)}<a class="rl" href="{e(link(path))}" title="{e(path)}">'
                    f"{e(doc)}, {e(name)}</a>")  # fmt: skip
        # rules of one file in two sections: the document once, each rule's id a link to its own
        ids = ", ".join(f'<a href="{e(link(p))}" title="{e(p)}">{e(n)}</a>'
                        for n, p in zip(names, paths, strict=True))  # fmt: skip
        return f'{e(text)}<span class="rl">{e(doc)}, {ids}</span>'

    credit = S.V["credit"]
    names = {k: f'<a href="{e(credit[k]["url"])}">{e(credit[k]["name"])}</a>'
             for k in ("lead", "builder")}  # fmt: skip

    # SE-3a and SE-3b in words, from the board's rows (a count typed here would go stale)
    def by_row(key, one, none, noun):
        said = []
        for r in S.ROWS:
            n = len(r.get(key) or ())
            if n:
                said.append(one.format(n="one" if n == 1 else f"{n:,}", name=name_of(r),
                                       **{noun: noun if n == 1 else f"{noun}s"}))  # fmt: skip
        return ", and ".join(said) or none

    names["se3a"] = e(by_row("replaced", SE3A_ROW, SE3A_NONE, "slot"))
    names["se3b"] = e(by_row("ineligible", SE3B_ROW, SE3B_NONE, "session"))

    def words_html(words):
        return e(words).format_map(names) if "{" in words else e(words)

    members = credit["members"]
    # the partners' names in display type, a ruled row (the home page's Partners heading leads
    # here); nothing while none has agreed
    row = (f'<div class="mbr" id="{PARTNERS_ID}"><dt>Partners</dt><dd><ul class="mbl">' + "".join(
        f'<li><a href="{e(m["url"])}">{e(m["name"])}</a></li>' for m in members)
        + "</ul></dd></div>") if members else ""  # fmt: skip
    lv = S.V["level"]
    # the level, its file's path under it as the link, as a bound line's rule is (its digest in
    # the title); its state opens the line
    state = f"Frozen {lv['frozen']}." if lv["frozen"] else "Draft."
    # the rules added since the freeze that decided rows: named, with their links, on /method
    phrase, href = MANDATE_LEVEL_LINK
    history = e(MANDATE_LEVEL).replace(e(phrase), f'<a href="{e(href)}">{e(phrase)}</a>', 1)
    level = (f'<div id="{LEVEL_ANCHOR}"><dt>{e(lv["name"])}<a class="rl" href="{e(link(lv["path"]))}" '
             f'title="{e(lv["digest"])}">{e(lv["path"])}</a></dt>'
             f"<dd>{e(state)} {history}</dd></div>")  # fmt: skip
    # the models it fixes, largest first, each with its publisher and architecture: the ladder
    # prints neither (RFC-0018 Q54), and a model no system has run on has no page of its own
    level += ('<div id="models"><dt>' + e(MANDATE_MODELS) + '</dt><dd><ul>' + "".join(
        f'<li><a href="/#{e(r["id"])}">{nobreak(r["model"])}</a>{SEP}{e(r["publisher"])}{SEP}'
        f'{e(architecture(r["parameters_total"], r.get("parameters_active")))}</li>'
        for r in S.V["rungs"]) + "</ul></dd></div>")  # fmt: skip
    # the dated corrections, newest first, the last row of their section
    corrections = ('<div id="corrections"><dt>Corrections</dt><dd><ul>' + "".join(
        f"<li>{e(day)}: {e(words)}</li>" for day, words in MANDATE_CORRECTIONS)
        + "</ul></dd></div>")  # fmt: skip
    blocks = "".join(
        section(title.lower().replace(" ", "-"), title, '<dl class="cs">' + "".join(
            f"<div><dt>{label(text, name, path)}</dt><dd>{words_html(words)}</dd></div>"
            for text, name, path, words in lines)
            + (row if title == MANDATE_MEMBERS_IN else "")
            + (level if title == MANDATE_LEVEL_IN else "")
            + (corrections if title == MANDATE_CORRECTIONS_IN else "") + "</dl>")
        for title, lines in MANDATE
    )  # fmt: skip
    parts = mandate_parts()
    # where the page stands: under Learn, whose hub lists it (the Learn tab is marked)
    kicker = f'<span><a href="{LEARN_PAGE}">Learn</a></span>' if S.V.get("learn") else ""
    body = f"""
{header("learn", under=True)}
<main id="main" class="sys">
  {title_band(MANDATE_BELIEF, cls="ttl creed", kicker=kicker)}
  {pnav("Mandate", parts)}
  <div class="wrap">
    {blocks}
  </div>
</main>
{footer()}"""
    return page("Mandate", MANDATE_DESC, body, "system mandatepage learnpage",
                MANDATE_PAGE.strip("/"), "home")  # fmt: skip


def mandate_parts():
    """The mandate's sections as (anchor, title), in its order: its own strip, and the Learn
    hub's block on it."""
    return [(title.lower().replace(" ", "-"), title) for title, _ in MANDATE]


def build_404():
    """Not found: the systems with a page, each with its glyph and model; the header and footer
    link the rest (the ladder holds the models)."""
    systems = "".join(
        f'<li><a href="{e(href(r))}">{glyph_svg(2, states(r))}'
        f'<span class="ln">{e(name_of(r))}</span><span class="lp">{nobreak(rung_of(r)["model"])}</span>'
        "</a></li>"
        for r in S.ROWS
    )
    lists = (
        '<section class="blk" aria-labelledby="h-systems">'
        f'<h2 class="sect" id="h-systems">Systems</h2><ul class="lost lsys">{systems}</ul></section>'
    ) if systems else ""  # fmt: skip
    body = f"""
{header(None)}
<main id="main" class="sys">
  {title_band("Not found")}
  <div class="wrap">{lists}</div>
</main>
{footer()}"""
    return page("Not found", "No page at this address.", body, "system notfound", "404", None)
