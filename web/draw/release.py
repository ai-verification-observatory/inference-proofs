"""The release's own pages: the release record (`/release`) and, when the release evaluates
one, the targets (`/targets`). RFC-0009 §Site, page table.

Each prints what `release.yaml`, the release index and the target files hold, in the site's
words for stored ids; nothing is counted or ranked here.
"""

from . import state as S
from .chrome import RELEASE_PAGE, TARGETS_PAGE, footer, has_targets, header, page
from .claims import run_ref
from .plates import EXT, blob, keep, name_of, path_html, readable, source_html
from .words import FAIL_KIND, PENDING_TAMPER, e, labels, shown, spread_line

TARGET_GRADE = "set in the target file"
RESULT_WORD = {"meets": "meets", "does_not_meet": "does not meet",
               "not_evaluable": "not evaluable"}  # fmt: skip


def band(title):
    return (
        '<section class="mast mast-sys" aria-labelledby="h-name"><div class="mast-in">'
        f'<h1 id="h-name" class="sysname"><span class="lt">{e(title)}</span></h1></div></section>'
    )


def rows_dl(rows, cls="tlab"):
    items = "".join(f"<div><dt>{e(k)}</dt><dd>{v}</dd></div>" for k, v in rows)
    return f'<dl class="{cls}">{items}</dl>'


def section(sid, title, body, small=False):
    """A section of a release page; small: a heading in the small size, for a section of a line
    or two under a title that already names it."""
    cls = "sect sm" if small else "sect"
    return (f'<section class="blk" id="{e(sid)}" aria-labelledby="h-{e(sid)}">'
            f'<h2 id="h-{e(sid)}" class="{cls}">{e(title)}</h2>{body}</section>')  # fmt: skip


def file_link(path):
    return f'<a href="{e(blob(path))}">{path_html(path)}{EXT}</a>'


def system_link(sid):
    href = S.PAGE.get(sid) or f"/reference#{sid}"
    return f'<a href="{e(href)}">{e(name_of(sid))}</a>'


# ------------------------------------------------------------------ the release record


def run_status(run, left):
    """A listed run's status (a word) and what it adds: a failure's kind, the reason the index
    records for a run left out of the figures, or the run that replaced a superseded one."""
    if run["run_id"] in left:
        x = left[run["run_id"]]
        if x["replaced_by"]:
            return "superseded", f"replaced by {run_ref(x['replaced_by'], x['replaced_by_record'])}"
        return "left out", e("; ".join(x["reason_words"]))
    if run["status"] == "failed":
        return "failed", e(FAIL_KIND.get(run["failure"], str(run["failure"])))
    return "completed", ""


def release_facts():
    rel = S.V["release"]
    rfc = rel["rfc_commit"]
    index = file_link(rel["index"])
    cards = "".join(
        f'<span><span class="nw">{e(c["system"])}</span> · {e(c["configuration"])} · version '
        f"{e(c['card_version'])} · {file_link(c['path'])} · sha256 "
        f"<code>{e(str(c['digest']).removeprefix('sha256:')[:12])}</code></span>"
        for c in rel["claim_cards"]
    )
    systems = (
        '<span class="links">'
        + "".join(
            f"<span>{system_link(s)}</span>"
            for s in [*S.V["orders"]["benchmarked"], *S.V["orders"]["reference"]]
        )
        + "</span>"
    )
    rows = [
        ("release", e(rel["id"])),
        (
            "RFCs",
            f'<a href="{e(S.REPO_URL)}/tree/{e(rfc)}/rfcs">rfcs/<span class="nw">@{e(rfc[:8])}</span>{EXT}</a>',
        ),
        ("reference file", file_link(rel["reference_file"])),
        ("harness", e(rel["harness_version"])),
        ("index", index),
        ("systems", systems),
        ("claim cards", f'<span class="links">{cards}</span>'),
    ]
    if has_targets():
        rows.append(("targets", f'<a href="{TARGETS_PAGE}">{len(S.V["targets"])} evaluated</a>'))
    return rows_dl(rows, "facts relf")


def runs_listed():
    """Every run the release lists, grouped by system and setup (workload and profile) in the
    order the release first lists each, each run by its id with its status and record."""
    left = {x["run_id"]: x for c in S.CONFIGS for x in c["runs"]["left_out"]}
    groups = {}
    for run in S.V["release"]["runs"]:
        groups.setdefault((run["system"], run["workload"], run["profile"]), []).append(run)
    body = ""
    for (sid, workload, profile), runs in groups.items():
        rows = []
        for run in runs:
            status, more = run_status(run, left)
            rows.append((status, f'<span class="rid">{run_ref(run["run_id"], run["record"])}</span>'
                                 + (f'<span class="rw">{more}</span>' if more else "")))  # fmt: skip
        body += (f'<p class="rgh">{e(name_of(sid))} · {keep(f"{workload} · {profile}")}</p>'
                 + rows_dl(rows, "tlab runs"))  # fmt: skip
    withdrawn = S.V["release"]["superseded_runs"]
    if withdrawn:
        body += '<p class="rgh">Withdrawn</p>' + rows_dl(
            [(x["run_id"], e(x["reason"])) for x in withdrawn], "tlab runs")  # fmt: skip
    return body


def checked():
    """Per configuration: how many of its runs completed and failed."""
    rows = []
    order = [*S.V["orders"]["benchmarked"], *S.V["orders"]["reference"]]
    for c in sorted(S.CONFIGS, key=lambda c: (order.index(c["system"]), c["position"])):
        said = [keep(f"{c['workload']['id']} · {c['profile']}"),
                e(f"{len(c['runs']['completed'])} completed, {len(c['runs']['failed'])} failed")]  # fmt: skip
        rows.append((name_of(c["system"]), "; ".join(said)))
    return rows_dl(rows, "tlab runs")


def unexpected_list():
    """Every control outcome outside its expected set, each linked to where its system page
    prints it in full; a row under a pending disclosure prints only the RFC-0008 notice."""
    rows = []
    for c in S.CONFIGS:
        if not c["unexpected"]:
            continue
        sid = c["system"]
        row = S.CRIT["rows"].get(sid)
        if row is not None and not row["drawn"]:
            rows.append((name_of(sid), e(PENDING_TAMPER)))
            continue
        for u in c["unexpected"]:
            href = f"{S.PAGE.get(sid, '/reference')}#unexpected-{u['control']}-{u['run_id']}"
            rows.append((name_of(sid), f'<a href="{e(href)}">{e(u["control"])} in run '
                                       f'{path_html(u["run_id"])}</a>'))  # fmt: skip
    if not rows:
        return '<p class="lead">No control outcome fell outside its expected set.</p>'
    return rows_dl(rows, "tlab runs")


def build_release():
    rel = S.V["release"]
    body = f"""
{header("release")}
<main id="main" class="sys relpage">
  {band("Release " + rel["id"])}
  <div class="wrap">
    {release_facts()}
    {section("runs", "Runs", runs_listed())}
    {section("checked", "Runs per setup", checked())}
    {section("unexpected", "Unexpected outcomes", unexpected_list())}
  </div>
</main>
{footer()}"""
    return page(
        f"Release {rel['id']}",
        f"Release {rel['id']}: its runs, claim cards and reference file.",
        body,
        "system release",
        RELEASE_PAGE.strip("/"),
        "home",
    )


# ------------------------------------------------------------------ targets


def target_value(q, cfg, pointer):
    """A target's mean or least favourable value with every label in view (S2, S3)."""
    if q["value"] is None:
        return e("No value")
    parts = [shown(q["value"], q["unit"])]
    if q.get("stats"):
        parts.append(f"spread: {spread_line(q)}")
    parts += [f"{k}: {v}" for k, v in labels(q, cfg)]
    return (
        e(readable(" · ".join(parts)))
        + f'\u00a0· <span class="src">source: {source_html(pointer)}</span>'
    )


def threshold_words(t, th):
    """The target's threshold with its labels (S2): a value its author sets, so its grade reads
    as set in the target file, not as a measurement."""
    cfg = next(c for c in S.CONFIGS if any(r["system"] == c["system"] for r in t["results"]))
    said = [f"{t['metric']} {t['comparator']} {shown(th['value'], th['unit'])}"]
    said += [f"{k}: {TARGET_GRADE if k == 'grade' and th['grade'] == 'asserted' else v}"
             for k, v in labels(th, cfg)]  # fmt: skip
    pointer = f"{t['path']}#/threshold"
    return e(readable(" · ".join(said))) + f"\u00a0· source: {path_html(pointer)}"


def build_targets():
    secs = ""
    index = S.V["release"]["index"]
    for t in S.V["targets"]:
        th = t["threshold"]
        head = [
            ("author", e(f"{t['author']['name']} ({t['author']['affiliation']})")),
            ("date", e(t["date"])),
            ("asks", threshold_words(t, th)),
            ("file", file_link(t["path"])),
        ]
        if t.get("rationale"):
            head.append(("rationale", e(t["rationale"])))
        rows = []
        for r in t["results"]:
            cfg = next(c for c in S.CONFIGS if c["system"] == r["system"]
                       and c["workload"]["id"] == r["workload"]["id"] and c["profile"] == r["profile"])  # fmt: skip
            base = f"{index}#/targets/{r['position']}"
            said = [keep(f"{r['workload']['id']} · {r['profile']}"), e(RESULT_WORD[r["result"]])]
            if r.get("reason"):
                said.append(e(r["reason"]))
            lines = "; ".join(said)
            for key, word in (("mean", "mean"), ("least_favourable", "least favourable")):
                if r.get(key):
                    lines += f'<span class="rw">{e(word)}: {target_value(r[key], cfg, f"{base}/{key}")}</span>'
            rows.append((name_of(r["system"]), lines))
        secs += section(f"t-{t['id']}", t["id"], rows_dl(head) + rows_dl(rows, "tlab runs"))
    body = f"""
{header("targets")}
<main id="main" class="sys relpage">
  {band("Targets")}
  <div class="wrap">{secs}</div>
</main>
{footer()}"""
    return page(
        "Targets",
        "The targets relying parties publish, and the rows of this release evaluated against them.",
        body,
        "system targets",
        TARGETS_PAGE.strip("/"),
        "home",
    )
