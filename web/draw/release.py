"""The release's own pages: the release record (`/release`) and, when the release evaluates
one, the targets (`/targets`). RFC-0009 §Site, page table.

Each prints what `release.yaml`, the release index and the target files hold, in the site's
words for stored ids; nothing is counted or ranked here.
"""

from . import state as S
from .chrome import RELEASE_PAGE, TARGETS_PAGE, footer, has_targets, header, page
from .claims import control_label, run_ref
from .plates import (
    EXT,
    blob,
    configs_of,
    keep,
    name_of,
    path_html,
    readable,
    setup_diff,
    source_html,
)
from .words import FAIL_STEP, OUTCOME_SHORT, e, labels, shown, spread_line

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
    return f'<a href="{e(blob(path))}">{path_html(path, ext=True)}</a>'


def system_link(sid):
    href = S.PAGE.get(sid) or f"/reference#{sid}"
    return f'<a href="{e(href)}">{e(name_of(sid))}</a>'


# ------------------------------------------------------------------ the release record


def run_status(run, left, failed):
    """A listed run's status where it is not a plain completed run: a failure with its exit code
    and step, the reason the index records for a run left out of the figures, or the run that
    replaced a superseded one; "" for a completed run."""
    if run["run_id"] in left:
        x = left[run["run_id"]]
        if x["replaced_by"]:
            return f"superseded, replaced by {run_ref(x['replaced_by'], x['replaced_by_record'])}"
        return f"left out: {e('; '.join(x['reason_words']))}"
    if run["status"] == "failed":
        f = failed.get(run["run_id"]) or {}
        said = "failed"
        if f.get("exit_code") is not None:
            said += f": exit {f['exit_code']}"
        if f.get("step") in FAIL_STEP:
            said += f" {FAIL_STEP[f['step']]}"
        return e(said)
    return ""


def release_facts():
    rel = S.V["release"]
    rfc = rel["rfc_commit"]
    index = file_link(rel["index"])
    order = [*S.V["orders"]["benchmarked"], *S.V["orders"]["reference"]]
    claim_cards = sorted(rel["claim_cards"], key=lambda c: (
        order.index(c["system"]) if c["system"] in order else len(order), c["system"]))  # fmt: skip
    cards = "".join(
        f"<span>{e(name_of(c['system']))} · version {e(c['card_version'])} · "
        f"{file_link(c['path'])} · sha256 "
        f"<code>{e(str(c['digest']).removeprefix('sha256:')[:12])}</code></span>"
        for c in claim_cards
    )

    def links(ids):
        return (
            '<span class="links">'
            + "".join(f"<span>{system_link(s)}</span>" for s in ids)
            + "</span>"
        )

    crit = (f'<a href="{e(S.REPO_URL)}/blob/main/{e(S.CRIT["path"])}">'
            f"{path_html(S.CRIT['path'], ext=True)}</a> · sha256 <code>{S.crit_sha[:12]}</code>")  # fmt: skip
    rows = [
        (
            "rules",
            f'<a href="{e(S.REPO_URL)}/tree/{e(rfc)}/rfcs">rfcs/<span class="nw">@{e(rfc[:8])}{EXT}</span></a>',
        ),
        ("reference file", file_link(rel["reference_file"])),
        ("criteria", crit),
        ("harness", e(rel["harness_version"])),
        ("index", index),
        ("systems", links(S.V["orders"]["benchmarked"])),
        ("references", links(S.V["orders"]["reference"])),
        ("claim cards", f'<span class="links">{cards}</span>'),
    ]
    if has_targets():
        rows.append(("targets", f'<a href="{TARGETS_PAGE}">{len(S.V["targets"])} evaluated</a>'))
    return rows_dl(rows, "facts relf")


def setup_label(c):
    """A configuration's group heading: its system, workload and profile, and a serving
    configuration's load point with its batch ("matched load, 24 requests per batch")."""
    out = f"{name_of(c['system'])} · {c['workload']['id']} · {c['profile']}"
    sv = c.get("serving") or {}
    load = sv.get("load") or c.get("load_point")
    if load:
        b = sv.get("batch")
        out += f" · {load} load" + (
            f", {b:,} request{'s' if b != 1 else ''} per batch" if b else ""
        )
    return out


def runs_listed():
    """Every run the release lists, grouped by configuration (a serving configuration by its
    load point too), in the order the release first lists each, under a heading with its counts;
    each run by its date and ordinal linked to its record (its id read aloud and in the title),
    its status only where it is not a plain completed run."""
    left = {x["run_id"]: x for c in S.CONFIGS for x in c["runs"]["left_out"]}
    failed = {f["run_id"]: f for c in S.CONFIGS for f in c["runs"]["failed"]}
    owner = {}
    for c in S.CONFIGS:
        for rid in [*c["runs"]["records"], *(x["run_id"] for x in c["runs"]["left_out"])]:
            owner.setdefault(rid, c)
    groups = {}
    for run in S.V["release"]["runs"]:
        c = owner.get(run["run_id"])
        key = c["position"] if c else (run["system"], run["workload"], run["profile"])
        groups.setdefault(key, (c, run, []))[2].append(run)
    body = ""
    for c, first, runs in groups.values():
        if c:
            head = setup_label(c)
            counts = [f"{len(c['runs']['completed'])} completed"]
            if c["runs"]["failed"]:
                counts.append(f"{len(c['runs']['failed'])} failed")
            if c["runs"]["left_out"]:
                counts.append(f"{len(c['runs']['left_out'])} left out")
            head += " · " + ", ".join(counts)
        else:
            head = f"{name_of(first['system'])} · {first['workload']} · {first['profile']}"
        items = "".join(
            f"<li>{run_ref(run['run_id'], run['record'])}"
            + (f' <span class="rw">{st}</span>' if (st := run_status(run, left, failed)) else "")
            + "</li>"
            for run in runs
        )
        body += f'<p class="rgh">{keep(readable(head))}</p><ul class="runs rl">{items}</ul>'
    withdrawn = S.V["release"]["superseded_runs"]
    if withdrawn:
        body += '<p class="rgh">Withdrawn</p>' + rows_dl(
            [(x["run_id"], e(x["reason"])) for x in withdrawn], "tlab runs")  # fmt: skip
    return body


def unexpected_list():
    """Every tamper-test outcome outside its expected set, each line linked to where its system
    page prints it in full, its run by date and ordinal linked to its record. One accepted only
    on a part the system declares verify does not read is listed apart, under a line that says
    it tests nothing (RFC-0008, amendment of 2026-11-09); "every outcome fell inside" only when
    neither list holds a line."""
    rows, nothing = [], []
    for c in S.CONFIGS:
        sid = c["system"]
        many = len(configs_of(sid)) > 1  # setups share dates and ordinals: name the setup
        who = name_of(sid) + (f", {', '.join(setup_diff(c))}" if many else "")
        for u in c["unexpected"]:
            href = f"{S.PAGE.get(sid, '/reference')}#unexpected-{u['control']}-{u['run_id']}"
            what = f"{e(readable(who))} · {control_label(u['control'])}"
            if not u.get("not_read"):
                what += f" · {e(OUTCOME_SHORT[u['outcome']])}"
            line = f'<a href="{e(href)}">{what}</a>{run_ref(u["run_id"], u["record"])}'
            (nothing if u.get("not_read") else rows).append(f'<li class="tl">{line}</li>')
    if not rows and not nothing:
        return '<p class="lead">Every outcome fell inside its expected set.</p>'
    out = ""
    if rows:
        out += ('<p class="lead">Outside their expected set:</p>'
                f'<ul class="runs lo">{"".join(rows)}</ul>')  # fmt: skip
    if nothing:
        out += ('<p class="lead">Accepted only on a part <code>verify</code> does not read, so '
                f'it tests nothing:</p><ul class="runs lo">{"".join(nothing)}</ul>')  # fmt: skip
    return out


def build_release():
    rel = S.V["release"]
    body = f"""
{header("release")}
<main id="main" class="sys relpage">
  {band("Release " + rel["id"])}
  <div class="wrap">
    {release_facts()}
    {section("runs", "Runs", runs_listed())}
    {section("tamper", "Tamper tests", unexpected_list())}
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
