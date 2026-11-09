"""RFC-0009 §Testing Strategy: the §Site rules on the pages `iproofs site build` writes (#320).

Page tests run over two builds of the synthetic placeholder release: with every test-only case
(`extras`) and without (`web`, the build as deployed, `extras=False`), each with the view it was
printed from. A check that needs a test-only case skips on `web` and says so.

Gaps RFC-0009 §Site lists (S6 table headings on the overview and the Not benchmarked yet note;
records printed as index pointers, not links) are named in the docstring of the test they
touch. Renamed tests
(RFC-0009 §Testing Strategy): `test_display_rounding` is `test_sort_key_is_stored_value`,
`test_no_aggregate_score_column` is `test_no_ranking`,
`test_superseded_and_ineligible_struck_through` is `test_runs_left_out_listed`,
`test_no_script_tags_required` is `test_reads_without_script`.

Every number below is a placeholder fixture value, not a result.
"""

import base64
import hashlib
import html
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from fixtures.builds import SiteBuild
from iproofs.site import renderer
from iproofs.site.view import site_view

ROOT = Path(__file__).resolve().parents[3]
# a system page's plates; the overview's figures (RFC-0009 S6)
PER_GBIT_COLS = ("per_bit", "size_bit", "check_bit")
COLS = ("covers", "proof_size", "check_time", "overhead", *PER_GBIT_COLS)
BOARD = ("overhead", *PER_GBIT_COLS)
METRIC = {
    "covers": "tokens_covered_per_proof",
    "proof_size": "proof_bytes",
    "check_time": "verify_seconds",
    "overhead": "overhead_vs_production_prove.steady",
    "per_bit": "seconds_per_active_weight_bit_token_prove.steady",
    "size_bit": "proof_bytes_per_active_weight_bit_token",
    "check_bit": "verify_seconds_per_active_weight_bit_token",
}


def metric(cfg: dict[str, Any], col: str) -> str:
    """The statistic a column shows for a configuration: the headline overhead the index names,
    prover time per active weight bit at the scope the view chose (steady, else session)."""
    if col == "overhead":
        return str(cfg["overhead_metric"])
    if col == "per_bit":
        return str(cfg["per_bit_metric"])
    return METRIC[col]


WORD = {"yes": "Yes", "partly": "Partly", "no": "No", "not_stated": "Not stated"}
VAL = re.compile(r'<a class="val" href="([^"]*)" title="([^"]*)">(.*?)</a>', re.S)
ROW = re.compile(
    r'<div class="row" id="([^"]+)" role="row" data-name="([^"]+)" data-k="([^"]+)">'
    r"(.*?)\n</div>",
    re.S,
)
TABLE = re.compile(
    r'<section class="sec board" id="([^"]+)".*?<div class="tbl" role="table".*?'
    r'<div class="rows" role="rowgroup">(.*?)</section>',
    re.S,
)
SECTION = re.compile(r'<section class="sec board" id="[^"]+".*?</section>', re.S)
HEAD = re.compile(r'<div class="hc[^"]*" role="columnheader"[^>]*>(.*?)</div>')
HEADER = re.compile(r'<div class="sysc" role="rowheader"[^>]*>(.*?)\n    </div>', re.S)
PLATE = re.compile(r'<div class="plate" id="([^"]+)" data-col="([^"]+)">(.*?)</dl></div>', re.S)
DD = re.compile(r"<dt>([^<]+)</dt><dd>(.*?)</dd>", re.S)
NUMBER = re.compile(r'<span class="n">([^<]+)</span><span class="u(?: x)?">([^<]+)</span>')
# an overview cell's title: sample size and range (S3); the plate it links holds mean and sd
TITLE_SPREAD = re.compile(
    r"(\d+) completed, (\d+) failed, (\S+(?: \S+)? to \S+(?: \S+)?|\S+ \S+ for every run)"
)
# a plate's spread (S3; the setup's runs line names n): the range with its unit once and the
# mean, then the sd; a constant once, with its run count
SPREAD = re.compile(r"all \d+ runs: .+|\S+ to \S+(?: \S+)?, mean \S+(?: \S+)?(?: · sd .+)?")
# reading units back to the stored base unit, by hand (RFC-0012: scaling is display only)
SCALE = {"tokens": 1.0, "B": 1.0, "kB": 1e3, "MB": 1e6, "GB": 1e9, "TB": 1e12, "ns": 1e-9,
         "\N{MICRO SIGN}s": 1e-6, "ms": 1e-3, "s": 1.0, "min": 60.0, "h": 3600.0,
         "\N{MULTIPLICATION SIGN}": 1.0}  # fmt: skip


@dataclass(frozen=True)
class Build:
    kind: str  # "extras" or "web"
    pages: dict[str, str]
    view: dict[str, Any]
    out: Path


def plain(text: str) -> str:
    """Text of an HTML fragment, tags dropped, entities and no-break spaces read."""
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text).replace("\N{NO-BREAK SPACE}", " ")).strip()


def flat(text: str) -> str:
    """Text of an HTML fragment with its tags dropped in place, so a path split into parts for
    line breaks reads whole."""
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", html.unescape(text).replace("\N{NO-BREAK SPACE}", " ")).strip()


@pytest.fixture(scope="module")
def extras(extras_build: SiteBuild) -> Build:
    """The extras build (shared and read-only, fixtures/builds), with its view."""
    out, view = extras_build.out, site_view(extras_build.repo)
    return Build("extras", {p.name: p.read_text("utf-8") for p in out.glob("*.html")}, view, out)


@pytest.fixture(scope="module")
def deployed(placeholder_build: SiteBuild) -> Build:
    """The build without test-only cases (shared and read-only, fixtures/builds), with its view."""
    out, view = placeholder_build.out, site_view(placeholder_build.repo)
    return Build("web", {p.name: p.read_text("utf-8") for p in out.glob("*.html")}, view, out)


@pytest.fixture(scope="module", params=["extras", "web"])
def site(request: pytest.FixtureRequest) -> Build:
    build = request.getfixturevalue("extras" if request.param == "extras" else "deployed")
    assert isinstance(build, Build)
    return build


def provers(view: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for c in view["configurations"] if c["kind"] == "prover"]


def row_config(view: dict[str, Any], rid: str) -> dict[str, Any]:
    """The configuration a row id names: `system` (its overview row: the workload `facts.json`
    names for it, or its only configuration) or `system--configuration--workload`."""
    system, _, rest = rid.partition("--")
    configuration, _, workload = rest.partition("--")
    found = [c for c in provers(view) if c["system"] == system and (not configuration or (
        c["configuration"], c["workload"]["id"]) == (configuration, workload))]  # fmt: skip
    named = view["facts"]["rows"][system].get("overview_workload")
    if not configuration and named is not None:
        found = [c for c in found if c["workload"]["id"] == named]
    assert len(found) == 1, rid
    return found[0]


def system_configs(build: Build, system: str) -> list[dict[str, Any]]:
    """The configurations a system page shows, in page order: one section each, named by its
    configuration line; every configuration of the system in the view, each once."""
    text = build.pages[f"{system}.html"]
    out: list[dict[str, Any]] = []
    where = r'<h3 id="h-[^"]+" class="sect sm setup" title="([^"]*)">'
    for named in re.findall(where, text, re.S):
        configuration, workload, _, profile = html.unescape(named).split(" · ")
        found = [c for c in build.view["configurations"] if c["system"] == system
                 and (c["configuration"], c["workload"]["id"], c["profile"])
                 == (configuration, workload, profile)]  # fmt: skip
        assert len(found) == 1, named
        out.append(found[0])
    assert [c["position"] for c in out] == [
        c["position"] for c in build.view["configurations"] if c["system"] == system]  # fmt: skip
    return out


def plate_config(build: Build, system: str, pid: str) -> dict[str, Any]:
    """The configuration a plate on a system page belongs to, by its id: `fig-<column>` when
    the system has one configuration, else `<row id>-fig-<column>`."""
    configs = system_configs(build, system)
    if pid.startswith("fig-"):
        assert len(configs) == 1, pid
        return configs[0]
    return row_config(build.view, pid.rsplit("-fig-", 1)[0])


def more_rows(text: str) -> list[str]:
    """Every row of every more-numbers table on a page."""
    return [row for table in re.findall(r'<table class="mtab">(.*?)</table>', text, re.S)
            for row in re.findall(r'<tr><th scope="row">.*?</tr>', table)]  # fmt: skip


def test_page_set_and_footer(site: Build) -> None:
    """Page table: the overview, one page per benchmarked system, the references, the criteria,
    the release, Targets only when the release evaluates a target, and Not found; every footer
    names and links the release, whose page links its `index.json` and the criteria file; the
    header links the criteria page on every page."""
    want = {"index.html", "reference.html", "criteria.html", "release.html", "404.html"}
    want |= {f"{s}.html" for s in site.view["orders"]["benchmarked"]}
    if site.view["targets"]:
        want.add("targets.html")
    assert set(site.pages) == want
    assert bool(site.view["targets"]) == (site.kind == "extras")
    release = site.view["release"]
    for name, text in site.pages.items():
        foot = text[text.index('<footer class="foot">') :]
        assert f"Release {release['id']}" in plain(foot), name
        assert 'href="/release"' in foot, name
        assert 'href="/criteria"' in text[: text.index("</header>")], name
    assert f"/{release['index']}" in site.pages["release.html"]
    digest = site.view["criteria"]["sha256"].removeprefix("sha256:")[:12]
    assert digest in site.pages["release.html"]
    if site.kind == "web":
        vercel = json.loads((site.out / "vercel.json").read_text())
        assert vercel["cleanUrls"] is True
        assert "*.html" in vercel["buildCommand"]


def test_release_page(site: Build) -> None:
    """Page table, Release: every run the release lists, by id, with its status; the superseded
    and withdrawn runs with their reasons; the RFC commit, reference file, and claim cards with
    their digests."""
    text = site.pages["release.html"]
    said = flat(text)
    release = site.view["release"]
    for run in release["runs"]:
        assert run["run_id"] in said, run["run_id"]
    for x in release["superseded_runs"]:
        assert x["run_id"] in said
        assert x["reason"] in said
    assert f"/tree/{release['rfc_commit']}/rfcs" in text
    assert release["reference_file"] in said
    for card in release["claim_cards"]:
        assert card["path"] in said
        assert card["digest"].removeprefix("sha256:")[:12] in said
    assert ('href="/targets"' in text) == bool(site.view["targets"])


def test_targets_page(site: Build) -> None:
    """Page table, Targets (only when the release evaluates one): each target with its author,
    and each row it was evaluated against with its result, mean and least favourable value,
    each value with its labels and its record in the index."""
    if not site.view["targets"]:
        assert "targets.html" not in site.pages
        pytest.skip("the deployed release evaluates no target")
    text = site.pages["targets.html"]
    said = flat(text)
    for t in site.view["targets"]:
        assert t["author"]["name"] in said
        assert t["id"] in said
        for r in t["results"]:
            for key in ("mean", "least_favourable"):
                assert f"#/targets/{r['position']}/{key}" in said
    for label in ("scope: ", "grade: ", "evidence: ", "spread: "):
        assert label in said


def test_every_number_has_labels(site: Build) -> None:
    """S2: each overview figure names its unit in view and its grade and tier in its accessible
    description (its scope too, where it has one), and links its plate, which holds its record;
    each plate holds every label in view; each more-numbers row names its scope, grade and tier,
    or why it has no value. The record is the index pointer as text (RFC-0009 §Site gaps)."""
    seen = 0
    grades = ("recorded by our harness", "calculated from recorded numbers")
    for href, title, inner in VAL.findall(site.pages["index.html"]):
        if 'class="fig"' not in inner:
            continue
        assert NUMBER.search(inner), inner
        said = plain(title)
        assert any(g in said.lower() for g in grades), title
        assert "evidence: " in said, title
        assert "#" in href, href  # its plate, which names the record
        assert "fig-" in href, href
        seen += 1
    assert seen >= 6  # two systems, at least three measured figures each
    for system in site.view["orders"]["benchmarked"]:
        text = site.pages[f"{system}.html"]
        configs = system_configs(site, system)
        plates = PLATE.findall(text)
        assert len(plates) == len(COLS) * len(configs)
        # each setup states once what its figures share: workload, grade, tier, record prefix
        setl = re.findall(r'<dl class="tlab setl">(.*?)</dl>', text, re.S)
        shared = [{dt for dt, _ in DD.findall(dl)} for dl in setl]
        assert len(shared) == len(configs)
        for i, cfg in enumerate(configs):
            assert {"workload", "source"} <= shared[i]
            prefix = f"configurations/{cfg['position']}/statistics/"
            assert prefix in flat(re.findall(r'<dl class="tlab setl">(.*?)</dl>', text, re.S)[i])
        # RFC-0004 INV-DERIVE-7: under each setup's per-Gbit plates, the width, note and limit
        basis = re.findall(r'<dl class="tlab notes basis"[^>]*>(.*?)</dl>', text, re.S)
        assert len(basis) == len(configs)
        assert all({"weight bits", "limit"} <= {dt for dt, _ in DD.findall(b)} for b in basis)
        for pid, col, body in plates:
            cfg = plate_config(site, system, pid)
            dts = {dt for dt, _ in DD.findall(body)} | shared[configs.index(cfg)]
            f = cfg["figures"][metric(cfg, col)]
            if 'class="fig"' in body:
                assert {"grade", "evidence", "workload", "source"} <= dts, pid
                assert ("spread" in dts) or ("pairs" in dts), pid
                assert ("scope" in dts) == (f["scope"] is not None), pid  # a timed number
            else:  # a null value names its record; a metric the runs did not record has none
                assert "why" in dts, pid
                assert ("source" in body) == f["recorded"], pid
        rows = more_rows(text)
        assert len(rows) == 5 * len(configs)
        for row in rows:  # every label a plate holds, or why there is no value
            said = plain(row)
            if "No value" in said:
                continue
            for label in ("spread: ", "source: "):
                assert label in said, (label, said)


def test_glyph_before_numbers(site: Build) -> None:
    """S1: on every page each row's header, holding its glyph, precedes the row's first figure;
    a system row's header links the validated claims of its card on the system page
    (`/<system>#claims-<configuration>`, an anchor that page holds once) and a reference's glyph
    its entry on `/reference`."""
    index = site.pages["index.html"]
    rows = ROW.findall(index)
    assert rows
    for rid, _, _, body in rows:
        cfg = row_config(site.view, rid)
        system, anchor = cfg["system"], f"claims-{cfg['configuration']}"
        assert body.index('class="pie"') < body.index('class="vc"'), rid
        head = body[: body.index('class="vc"')]
        assert f'<a href="/{system}#{anchor}" title="pinned at ' in head, rid
        assert f'<a class="pie" href="/{system}#{anchor}"' in head, rid
        assert site.pages[f"{system}.html"].count(f'id="{anchor}"') == 1, rid
    for ref in site.view["orders"]["reference"]:  # a baseline, not a row (RFC-0009 S6)
        assert f'<div class="row" id="{ref}"' not in index, ref
    for system in site.view["orders"]["benchmarked"]:
        text = site.pages[f"{system}.html"]
        assert text.index('class="rpie"') < text.index('class="plate"'), system
    ref = site.pages["reference.html"]
    for gid in site.view["orders"]["reference"]:
        sec = ref[ref.index(f'id="{gid}" aria-labelledby') :]
        sec = sec[: sec.index("</section>")]
        glyph = sec.index("pie-svg")  # the reference's states before any figure
        assert 'class="fig"' not in sec or glyph < sec.index('class="fig"'), gid


def test_claim_card_before_numbers(site: Build) -> None:
    """S1, INV-CLAIM-1: in every table across systems each row's header precedes the row's first
    figure and holds the glyph with each state as a word, the name, the pin of the row's card and,
    where the table holds two rows of the system, the card's `configuration`, and no value of any
    other card field; each state is the state the criteria file sets for that card (RFC-0016).
    On system pages the validated claims precede every figure (`_validated_claims`)."""
    criteria, props = site.view["criteria"]["rows"], site.view["criteria"]["properties"]
    for _, body in TABLE.findall(site.pages["index.html"]):
        rows = ROW.findall(body)
        for rid, _, _, row in rows:
            cfg = row_config(site.view, rid)
            header = HEADER.search(row)
            assert header, rid
            head = header[1]
            assert row.index(head) < row.index('class="vc"')
            assert "<svg" in head  # the glyph
            cells = criteria[cfg["system"]]["cells"]
            said = plain(re.search(r'<p class="sr">(.*?)</p>', head)[1])  # type: ignore[index]
            for p in props:
                state = cells[p["id"]]["state"]
                assert f"{p['name']}: {WORD[state]}" in said, (rid, p["id"])
            assert site.view["facts"]["rows"][cfg["system"]]["name"] in plain(head)
            assert f"pinned at {cfg['card']['body']['upstream']['commit'][:8]}" in head
            two = sum(row_config(site.view, r[0])["system"] == cfg["system"] for r in rows) > 1
            assert (cfg["configuration"] in plain(head)) == two, rid
            body_ = cfg["card"]["body"]
            for field, value in body_.items():
                if field in {"schema", "system", "configuration", "upstream", "card_version"}:
                    continue
                for text in _strings(value):
                    if len(text) > 12:  # long enough to be card text, not a common word
                        assert text not in plain(head), (rid, field)
    for system in site.view["orders"]["benchmarked"]:
        _validated_claims(site, system)


def _validated_claims(site: Build, system: str) -> None:
    """S1 on a system page, in DOM order: the validated claims (per property its state, reason
    and a link to how we read it, then, folded in "How we read it", the deciding quote with its
    source at the pin, both quotes of a conflict, the sources read and each mapped control in
    every run read), the card's
    identity with its file and digest, the card in full in a `details` element, both folds
    closed in the HTML as sent, then `quality_gap` and `residual` with the agreement rate
    outside them; all before every figure."""
    props = site.view["criteria"]["properties"]
    text = site.pages[f"{system}.html"]
    configs = system_configs(site, system)
    cfg = configs[0]
    card = cfg["card"]
    first_figure = re.search(r'class="plate" id="[^"]*fig-', text).start()  # type: ignore[union-attr]
    claims = text.index(f'id="claims-{cfg["configuration"]}"')
    identity = text.index(f'href="{card["link"]}"')
    folded = text.index(f'<details class="cardfull" id="card-{cfg["configuration"]}">')
    gap = text.index('class="gapblk"' if 'class="gapblk"' in text else "gapone")
    read = text.index('<details class="howread" id="how-we-read">')
    assert claims < text.index('class="rprops"') < read < identity < folded < gap < first_figure
    assert text.index('class="rprops"') < text.index('class="fig"')
    assert "<details open" not in text  # folded as sent (S1 item 4)
    details = text[folded : text.index("</details>", folded)]
    label = renderer(ROOT).draw.claims.card_key
    for field in card["body"]:
        if field not in ("sources", "schema", "card_version"):
            assert f"<dt>{label(field)}</dt>" in details, field
    assert "not_stated" not in details  # every enum in words
    assert card["digest"].removeprefix("sha256:")[:12] in plain(text[identity:folded])
    assert "not reviewed" not in plain(text[identity:folded])
    after = plain(text[gap:first_figure])
    assert "quality gap" in after
    assert "residual" in after
    # RFC-0015 RC-6: the rate beside them, outside the fold, or why it has none (one line when
    # the card states neither field and no run recorded a rate)
    if "gapone" not in text[gap : gap + 40]:
        assert 'class="plate" id="agree-' in text[gap:first_figure]
    else:
        assert "agreement with a rerun" in plain(text[gap:first_figure])
    if not cfg["agreement"]["recorded"]:
        assert "not recorded in these runs" in plain(text[gap:first_figure]).lower()
    pc = next((c["property_controls"] for c in configs if c.get("property_controls")), None)
    for p in props:
        _property_claims(site, system, p, pc)


PROPERTY_BLOCK = re.compile(
    r'<li class="rp [rl]" id="p-[a-z_]+" data-n="\d"><p class="rn">(?:(?!</p>).)*</p>'
    r'(<p class="rs"><i class="sw [a-z]+"></i>(?:(?!</p>).)*</p>)'
    r'(<p class="rr">(?:(?!</p>).)*</p>)?'
    r'(<div class="ev"><p class="ex"><span class="ek">stated</span><span class="eb">.*?</span>'
    r"</p></div>)?</li>",
    re.S,
)
# the link from a property to its entry in "How we read it": its reason, or its state word
READ_LINK = re.compile(
    r'<a class="psrc" href="#read-([a-z_]+)">[^<]*<span class="sr">: how we read ([^<]*)</span></a>'
)


def _property_claims(
    site: Build, system: str, p: dict[str, Any], pc: dict[str, Any] | None
) -> None:
    """One property of a system page's validated claims (`_validated_claims`): its block beside
    the glyph holds its state, our reason, a "source" link to its entry in "How we read it" and,
    for an overridden cell, its stated state with what contradicts it, nothing else; the quotes,
    what was read and the controls are in the entry (`_how_we_read`)."""
    criteria = site.view["criteria"]["rows"]
    text = site.pages[f"{system}.html"]
    cells = criteria[system]["cells"]
    item = re.search(rf'<li class="rp [rl]" id="p-{p["id"]}".*?</li>', text, re.S)
    assert item, (system, p["id"])
    body, said = item[0], flat(item[0])
    block = PROPERTY_BLOCK.fullmatch(body)
    assert block, (system, p["id"], body)  # name, state, reason, link, overridden line only
    assert "<blockquote" not in body, (system, p["id"])  # quotes are in the fold, not here
    entry = re.search(rf'<div id="read-{p["id"]}" tabindex="-1">', text)
    links = READ_LINK.findall((block[1] or "") + (block[2] or ""))
    if entry:  # the reason (or the state word) links this property's own entry, which exists
        assert links == [(p["id"], p["name"])], (system, p["id"])
    else:
        assert not links, (system, p["id"])
    cell = cells[p["id"]]
    state = cell["state"]
    assert '<p class="rs"><i class="sw ' in body
    assert WORD[state] in said, (system, p["id"])
    _how_we_read(site, system, p, pc)
    if pc is None or not cell.get("stated"):
        assert 'class="ex"' not in body, (system, p["id"])
        return
    line = re.search(r'<p class="ex">.*?</p>', body, re.S)
    assert line, (system, p["id"])
    assert f"stated {WORD[cell['stated']]}" in plain(line[0])
    if not cell["contradicted_by"]:
        return
    # one short line: the controls, then the run as a link to the entry, whose control line
    # prints the full id (a screen reader hears it in the link)
    controls = ", ".join(dict.fromkeys(x["control"] for x in cell["contradicted_by"]))
    runs = list(dict.fromkeys(x["run_id"] for x in cell["contradicted_by"]))
    shown = re.sub(r'<span class="sr">.*?</span>', "", line[0])
    word = "run" if len(runs) == 1 else "runs"
    assert flat(shown).endswith(f"{controls} accepted in {word}"), (system, p["id"], line[0])
    assert f'<a class="psrc" href="#read-{p["id"]}">{word}<span class="sr"> ' in line[0]
    assert f"accepted in {word} {', '.join(runs)}" in flat(line[0]), (system, p["id"])
    entry = re.search(rf'<div id="read-{p["id"]}" tabindex="-1">.*?</dd></div>', text, re.S)
    assert entry, (system, p["id"])
    for x in cell["contradicted_by"]:
        assert x["run_id"] in flat(entry[0]), (system, p["id"], x["run_id"])


def _quotes_printed(
    system: str, p: dict[str, Any], cell: dict[str, Any], body: str, said: str
) -> None:
    """S1 item 1 in the property's entry of "How we read it": the one quote marked `decides`,
    verbatim, with its source at the pin; a stated cell always prints it; a quote that does not
    decide is printed only in a conflict (both quotes, `conflict_lines`)."""
    deciding = [q for q in cell["quotes"] if q.get("decides")]
    if cell["state"] != "not_stated":
        assert len(deciding) == 1, (system, p["id"])  # a stated cell prints the quote it rests on
    for q in [q for q in cell["quotes"] if q not in deciding]:  # a non-deciding quote: not here
        assert cell["conflict"] or q["text"] not in html.unescape(body), (system, p["id"])
    for q in deciding:  # verbatim, with its source at the pin
        assert q["text"] in html.unescape(body), (system, p["id"])
        assert f'href="{html.escape(q["url"])}"' in body, (system, p["id"])
        where = f"@{q['commit'][:8]} {q['path']} {q['lines']}"
        assert f"{q['repo'].rsplit('/', 1)[-1]}{where}" in said, (system, p["id"])
        assert f'title="{html.escape(q["repo"] + where)}"' in body, (system, p["id"])


def _how_we_read(site: Build, system: str, p: dict[str, Any], pc: dict[str, Any] | None) -> None:
    """RFC-0016 ST-2, ST-8, OVR-7 in the fold "How we read it": the deciding quote with its
    source, both quotes of a conflict, the sources read, and each mapped control in every run
    read (no run read says why, never "not run"). The entry takes focus (`tabindex="-1"`,
    words.js)."""
    text = site.pages[f"{system}.html"]
    cell = site.view["criteria"]["rows"][system]["cells"][p["id"]]
    entry = re.search(
        rf'<div id="read-{p["id"]}" tabindex="-1"><dt>(.*?)</dt><dd>(.*?)</dd></div>', text, re.S
    )
    controls = pc is not None
    quoted = any(q.get("decides") for q in cell["quotes"])
    if not (quoted or cell["sources_read"] or cell["conflict"] or controls):
        assert entry is None, (system, p["id"])
        return
    assert entry, (system, p["id"])
    assert flat(entry[1]) == p["name"]
    body, said = entry[2], flat(entry[2])
    _quotes_printed(system, p, cell, body, said)
    if cell["sources_read"]:
        _sources_read(site, system, p, said)
    for q in cell["quotes"] if cell["conflict"] else []:  # both quotes of a conflict
        assert q["text"] in html.unescape(body), (system, p["id"])
    if not controls:
        assert 'class="ec"' not in body, (system, p["id"])
        return
    assert pc is not None
    mapped = pc["properties"][p["id"]]["mapped"]
    if not mapped:  # no RFC-0008 control tests the property: no control line
        assert 'class="ec"' not in body, (system, p["id"])
    for cid in mapped:
        assert cid in said, (system, cid)
    for run in pc["runs"] if mapped else []:  # every run read, under every mapped property
        assert run["run_id"] in said, (system, p["id"], run["run_id"])
    if not pc["runs"] and mapped:  # no run read says why, never "not run" (OVR-5)
        assert f"{', '.join(mapped)}: no run read, since " in said, (system, p["id"])
        assert "not run" not in said, (system, p["id"])


def _sources_read(site: Build, system: str, p: dict[str, Any], said: str) -> None:
    """RFC-0016 ST-2: what was read, one line per repository linked at its commit with the paths
    read; the list two or more properties share is printed once, at the head of the fold
    (`read-sources`), and a property whose list it is prints none of its own."""
    cells = site.view["criteria"]["rows"][system]["cells"]
    text = site.pages[f"{system}.html"]
    mine = cells[p["id"]]["sources_read"]
    lists = [json.dumps(c["sources_read"], sort_keys=True) for c in cells.values()
             if c["sources_read"]]  # fmt: skip
    if lists.count(json.dumps(mine, sort_keys=True)) > 1 and 'id="read-sources"' in text:
        head = re.search(r'<div id="read-sources" tabindex="-1">(.*?)</dd></div>', text, re.S)
        assert head, system
        if json.dumps(mine, sort_keys=True) == max(set(lists), key=lists.count):
            assert 'class="er"' not in said, (system, p["id"])
            said = flat(head[1])
    for source in mine:  # criteria/1: a repository at a full commit, or a web page
        if "repo" in source:
            assert ", ".join(source["paths"]) in said, (system, source)
            tree = f"https://github.com/{source['repo']}/tree/{source['commit']}"
            assert tree in text, (system, source)
        else:
            assert f"retrieved {source['retrieved']}" in said, (system, source)


def test_stated_cell_needs_its_deciding_quote() -> None:
    """S1 item 1, AGENTS.md rule 9: the quote printed is the one marked `decides`, wherever it
    sits in the cell, also in a conflict (RFC-0016 ST-8: the quote of the stated state); a
    stated cell with none, or a deciding quote with no repo, commit or url, stops the build
    instead of printing a state with nothing under it."""
    deciding = renderer(ROOT).draw.claims.deciding_quotes
    q = {"repo": "o/r", "commit": "a" * 40, "url": "https://github.com/o/r", "text": "t"}
    other = {**q, "text": "u", "decides": False}
    cell = {"state": "yes", "conflict": False, "quotes": [other, {**q, "decides": True}]}
    assert deciding("s", "p", cell) == [{**q, "decides": True}]
    assert deciding("s", "p", {**cell, "conflict": True}) == [{**q, "decides": True}]
    with pytest.raises(RuntimeError, match="no deciding quote"):
        deciding("s", "p", {**cell, "quotes": [other]})
    with pytest.raises(RuntimeError, match="no repo, commit or url"):
        deciding("s", "p", {**cell, "quotes": [{"text": "t", "decides": True}]})
    assert deciding("s", "p", {"state": "not_stated", "conflict": False, "quotes": []}) == []


def test_conflict_quotes_folded() -> None:
    """RFC-0016 ST-8 in "How we read it": every quote of a conflicting cell, verbatim, each with
    the state whose rule it meets and its source at the pin; a cell with no conflict adds none
    (no criteria cell conflicts yet, so the case is built here)."""
    lines = renderer(ROOT).draw.claims.conflict_lines
    q = {"repo": "o/r", "commit": "a" * 40, "path": "README.md", "lines": "L1",
         "url": "https://github.com/o/r/blob/" + "a" * 40 + "/README.md#L1"}  # fmt: skip
    yes = {**q, "text": "it holds", "meets": "yes", "decides": False}
    partly = {**q, "text": "it holds in part", "meets": "partly", "decides": True}
    out = lines({"conflict": True, "quotes": [yes, partly]})
    line = r'<div class="eqs"><span class="ek">(\w+)</span><div class="eb">(.*?)</div></div>'
    rows = re.findall(line, out, re.S)
    assert [(k, flat(v)) for k, v in rows] == [
        ("yes", "“it holds”r@aaaaaaaa README.md L1 ↗"),
        ("partly", "“it holds in part”r@aaaaaaaa README.md L1 ↗"),
    ]
    assert out.count(f'href="{q["url"]}"') == 2
    assert lines({"conflict": False, "quotes": [yes, partly]}) == ""


def test_sources_read_shared(monkeypatch: pytest.MonkeyPatch) -> None:
    """RFC-0016 ST-2 in "How we read it": the list two or more properties share, whatever the
    order of each entry's keys, is printed once at the head of the fold, and those properties
    print none of their own; the same entries with their paths in another order are another
    list, printed in full; a property with nothing to show has no row."""
    build = renderer(ROOT)
    state = build.draw.state
    one = [{"repo": "o/r", "commit": "a" * 40, "paths": ["README.md", "docs/cost-model.md"]}]
    same = [{"paths": ["README.md", "docs/cost-model.md"], "commit": "a" * 40, "repo": "o/r"}]
    other = [{"repo": "o/r", "commit": "a" * 40, "paths": ["docs/cost-model.md", "README.md"]}]
    empty = {"state": "not_stated", "sources_read": [], "conflict": False, "quotes": []}
    cells = {
        "a": {**empty, "sources_read": one},
        "b": {**empty, "sources_read": same},
        "c": {**empty, "sources_read": other},
        "d": empty,
    }
    names = {"a": "First", "b": "Second", "c": "Third", "d": "Fourth"}
    monkeypatch.setattr(state, "CRIT", {"rows": {"s": {"cells": cells}}})
    monkeypatch.setattr(state, "PROPS", [{"id": k, "name": v} for k, v in names.items()])
    claims = build.draw.claims
    out = claims.how_we_read(claims.read_entries("s", None, ["a", "b", "c", "d"]))
    entry = r'<div id="read-(\w+)" tabindex="-1"><dt>[^<]*</dt><dd>(.*?)</dd></div>'
    rows = dict(re.findall(entry, out, re.S))
    assert set(rows) == {"sources", "c"}  # a and b share the list printed at the head
    label = '<span class="ek">read</span>'  # the label, then the sources in their own column
    assert all(r.startswith(f'<p class="er">{label}') for r in rows.values())
    rows = {k: v.replace(label, "") for k, v in rows.items()}
    assert flat(rows["sources"]) == "o/r@aaaaaaaa ↗ README.md, docs/cost-model.md"
    assert flat(rows["c"]) == "o/r@aaaaaaaa ↗ docs/cost-model.md, README.md"
    assert '<span class="nw">docs/cost-model.md</span>' in rows["c"]  # never breaks inside


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def test_statistics_shown(site: Build) -> None:
    """S3: every statistic shows its six values (completed, failed, minimum, maximum, mean, sd)
    on system pages, and the same in the title of its overview cell (owner decision of
    2026-11-09: nothing but a scope word under an overview figure), equal to the stored ones; a
    reference whose runs all failed shows its counts and "below minimum repetitions" on
    `/reference`; each more-numbers row shows the six values too."""
    for _, title, inner in VAL.findall(site.pages["index.html"]):
        if 'class="fig"' not in inner or " completed, " not in html.unescape(title):
            continue
        assert TITLE_SPREAD.search(plain(html.unescape(title))), title
    for system in site.view["orders"]["benchmarked"]:
        text = site.pages[f"{system}.html"]
        configs = system_configs(site, system)
        leads = [plain(x) for x in re.findall(r'<p class="lead">(.*?)</p>', text)]
        for cfg, lead in zip(configs, leads, strict=True):  # n and n_failed, once per setup
            assert lead.startswith(f"Runs: {len(cfg['runs']['completed'])} completed"), lead
            if cfg["runs"]["failed"]:
                assert f"{len(cfg['runs']['failed'])} failed" in lead, lead
        for pid, col, body in PLATE.findall(text):
            cfg = plate_config(site, system, pid)
            f = cfg["figures"][metric(cfg, col)]
            stats = f.get("stats")
            if not stats:
                continue
            assert stats["n"] == len(cfg["runs"]["completed"]), pid
            spread = dict(DD.findall(body))["spread"]
            assert SPREAD.fullmatch(plain(spread)), spread
        for cfg, rows in zip(configs, _chunks(more_rows(text), 5), strict=True):
            for (stat, _), row in zip(MORE, rows, strict=True):
                stats = cfg["figures"][stat].get("stats")
                if not stats or cfg["figures"][stat]["value"] is None:
                    continue
                assert MORE_SPREAD.search(plain(row)), row
    failed = [c for c in site.view["configurations"]
              if c["kind"] == "reference" and c["insufficient_repetitions"]]  # fmt: skip
    assert failed
    for page in ("reference.html",):  # the overview holds no reference row (RFC-0009 S6)
        assert site.pages[page].count("below minimum repetitions") == len(failed), page
        for c in failed:
            n = f"{len(c['runs']['completed'])} completed, {len(c['runs']['failed'])} failed"
            assert n in plain(site.pages[page]), (page, c["system"])


def _chunks(items: list[str], n: int) -> list[list[str]]:
    return [items[i : i + n] for i in range(0, len(items), n)]


MORE_SPREAD = re.compile(r"spread: (all \d+ runs: |.+? to .+?, mean )")
# the more-numbers rows, in the renderer's order (web/draw/plates.py MORE)
MORE = (("rate_prove.session", "Proving rate"),
        ("cost_per_1k_tokens_prove.session", "GPU cost per 1M tokens"),
        ("commit_seconds", "Preparing the model (once)"),
        ("verify_host_memory_peak_anon", "Checker memory"),
        ("prove_gpu_memory_peak", "GPU memory"))  # fmt: skip


def _significant(number: str) -> int:
    digits = number.replace(",", "").replace(".", "").lstrip("0")
    return len(digits)


def test_sort_key_is_stored_value(site: Build) -> None:
    """S4: each sort key equals the value the index stores, in its base unit, and the printed
    figure is that value at 4 significant digits in a reading unit (scaled back by hand here)."""
    rows = ROW.findall(site.pages["index.html"])
    assert rows
    for rid, _, keys, body in rows:
        cfg = row_config(site.view, rid)
        got = json.loads(html.unescape(keys))
        assert set(got) == set(BOARD)
        cells = dict(re.findall(r'data-col="([^"]+)">(<a class="val".*?</a>)</div>', body, re.S))
        for col in BOARD:
            stored = cfg["figures"][metric(cfg, col)]["value"]
            assert got[col] == stored, (rid, col)
            printed = NUMBER.search(cells[col])
            if stored is None:
                assert printed is None, (rid, col)
                continue
            assert printed, (rid, col)
            number, unit = printed[1], printed[2]
            assert _significant(number) == 4 or float(number.replace(",", "")).is_integer()
            # no leading zero where a prefix can avoid one: 68.21 µs, not 0.06821 ms
            assert float(number.replace(",", "")) >= 1 or unit in ("B", "\N{MULTIPLICATION SIGN}")
            # per token, per Gbit of active weights: seconds and bytes per 1e9 bits
            per_gbit = 1e-9 if col in PER_GBIT_COLS else 1.0
            value = float(number.replace(",", "")) * SCALE[unit] * per_gbit
            exponent = math.floor(math.log10(abs(value)))
            assert abs(value - stored) <= 0.5 * 10 ** (exponent - 3) * 1.0001, (rid, col)


def test_default_order_by_overhead(site: Build) -> None:
    """S5: the HTML as sent holds the rows by overhead against production serving, ascending, by
    the stored value (the row's headline, steady or warm, its scope in its cell); a row with no
    overhead last; ties by name. The overhead head carries `aria-sort`; other orders on request
    (`shoot.mjs`). Not benchmarked yet stays A to Z."""
    index = site.pages["index.html"]
    names = site.view["facts"]["rows"]
    rows = [(row_config(site.view, rid), json.loads(html.unescape(k))["overhead"])
            for rid, _, k, _ in ROW.findall(index)]  # fmt: skip
    assert rows
    want = sorted(rows, key=lambda r: (r[1] is None, r[1] or 0.0,
                                       names[r[0]["system"]]["name"].lower()))  # fmt: skip
    assert [c["system"] for c, _ in rows] == [c["system"] for c, _ in want]
    for cfg, key in rows:  # each figure carries its scope in its cell
        assert key == cfg["figures"][cfg["overhead_metric"]]["value"]
    head = r'<div class="hc[^"]*" role="columnheader" data-col="([^"]+)"([^>]*)>'
    heads = re.findall(head, index)
    assert [c for c, a in heads if "aria-sort" in a] == ["overhead"]
    assert 'data-col="overhead" data-dir="asc"' in index
    nb = site.view["orders"]["not_benchmarked"]
    assert [names[r]["name"].lower() for r in nb] == sorted(names[r]["name"].lower() for r in nb)


def test_each_figure_names_its_scope(site: Build) -> None:
    """S2, owner decisions of 2026-11-09: on the overview each figure carries its labels in its
    title (scope, grade, tier and the spread where it has one; its record on its plate); the
    overhead's title names its scope (both sides', or the warm pairing's), its prover and serving
    run counts and what each side ran, and the cell its scope in a word; proving time per token
    per Gbit names its scope in a word (steady, or with start-up where the steady figure is
    null), check time its
    scope in its title; the row header names the weight width they divide by. Nothing else sits
    under a figure: the full details are on the plate it links."""
    b = renderer(ROOT).draw
    title = re.compile(r'title="([^"]*)"')
    rows = ROW.findall(site.pages["index.html"])
    for rid, _, _, body in rows:
        cfg = row_config(site.view, rid)
        cells = dict(re.findall(r'data-col="([^"]+)">(<a class="val".*?</a>)</div>', body, re.S))
        said = {c: plain(html.unescape(t[1])) if (t := title.search(v)) else ""
                for c, v in cells.items()}  # fmt: skip
        sub = re.compile(r'<span class="sub">(.*?)</span></a>')
        under = {c: plain(m[1]) if (m := sub.search(v)) else "" for c, v in cells.items()}
        over = cfg["figures"][cfg["overhead_metric"]]
        if over["value"] is not None:
            assert plain(b.words.SCOPE_LINES[over["metric"]]) in said["overhead"], rid
            pairs = over["pairs"]
            assert f"{pairs['n_system']} prover run" in said["overhead"], rid
            assert f"{pairs['n_serving']} serving run" in said["overhead"], rid
            assert plain(cfg["overhead_words"]["brief"]) in said["overhead"], rid
            assert under["overhead"] == b.words.SCOPE_SHORT[over["metric"]], rid
        bit = cfg["figures"][cfg["per_bit_metric"]]
        steady = cfg["figures"][METRIC["per_bit"]]
        assert cfg["per_bit_metric"] == (
            METRIC["per_bit"]
            if steady["value"] is not None
            else "seconds_per_active_weight_bit_token_prove.session"
        )
        if bit["value"] is not None:
            scope = {"prove.steady": "proving, steady state", "prove.session": "proving session"}
            assert scope[bit["scope"]] in said["per_bit"], rid
            assert (
                under["per_bit"]
                == {"prove.steady": "steady", "prove.session": "with start-up"}[bit["scope"]]
            ), rid
            assert f"{bit['stats']['n']} completed" in said["per_bit"], rid
        check = cfg["figures"][METRIC["check_bit"]]
        if check["value"] is not None:
            cpus = cfg["verifier"]["logical_cpus"]
            assert f"checking ({cpus} CPU threads)" in said["check_bit"], rid
            assert under["check_bit"] == f"{cpus} threads", rid
        assert under["size_bit"] == "", rid
        header = HEADER.search(body)
        assert header, rid
        # the width in short in view, in full in the model cell's title
        wb = cfg["workload"]["precision"]["weight_bits"]
        assert f"{wb['bits']:.4g}-bit" in plain(header[1]), rid
        assert "per active weight" in html.unescape(header[1]), rid


def test_deployed_figures_by_hand() -> None:
    """The deployed release's overview figures, against the values its `index.json` stores
    (Hugging Face H200 runs, `reported` tier): FlashProve on fp-maverick-w1024-b24 shows the
    steady overhead (D-OVERHEAD-S) and the steady proving time per token per Gbit of active
    weights, 6.82e-14 s/bit_token printed as 68.21 µs (x 1e9 bits per Gbit, x 1e6 µs per s);
    SASH shows the warm overhead (D-OVERHEAD-WARM) and, with no steady scope, the session time,
    7.54e-11 s/bit_token printed as 75.41 ms. Proof size per token per Gbit (D-BPAB):
    FlashProve 18,335.17 B/token / (17e9 x 4.83916 bits) = 2.2288e-7 B/bit_token, 222.9 B;
    SASH 41,105,525 B/token / (8,030,261,248 x 8 bits) = 6.3985e-4 B/bit_token, 639.9 kB. Check
    time per token per Gbit (D-VSPAB): FlashProve 0.0163436 s/token / 8.22658e10 bits =
    1.9867e-13 s/bit_token, 198.7 µs; SASH 3.279154 s/token / 6.42421e10 bits =
    5.1044e-11 s/bit_token, 51.04 ms."""
    index = ROOT / "releases/v0.1/index.json"
    if not index.exists():
        pytest.skip("no frozen release")
    view = site_view(ROOT)
    b = renderer(ROOT).draw
    got = {c["system"]: c for c in view["configurations"] if c["kind"] == "prover"
           and c["workload"]["id"] in ("fp-maverick-w1024-b24", "sash-l31-8b-c1024")}  # fmt: skip
    fp, sash = got["flashprove"], got["sash"]
    assert fp["per_bit_metric"].endswith("prove.steady")
    assert sash["per_bit_metric"].endswith("prove.session")
    assert sash["overhead_metric"] == "overhead_vs_production_warm"
    assert b.words.shown(6.82085750604253e-14, "s/bit_token") == "68.21 \N{MICRO SIGN}s"
    assert b.words.shown(7.540596017714907e-11, "s/bit_token") == "75.41 ms"
    assert math.isclose(fp["figures"][fp["per_bit_metric"]]["value"], 6.82085750604253e-14)
    assert math.isclose(sash["figures"][sash["per_bit_metric"]]["value"], 7.540596017714907e-11)
    size, check = METRIC["size_bit"], METRIC["check_bit"]
    for cfg, bits, bpt, vspt, size_shown, check_shown in (
        (fp, 17e9 * 4.83916475612899, 18335.170963541666, 0.016343559571372478,
         "222.9 B", "198.7 \N{MICRO SIGN}s"),
        (sash, 8030261248 * 8, 41105524.851715684, 3.279154322772059, "639.9 kB", "51.04 ms"),
    ):  # fmt: skip
        assert math.isclose(cfg["figures"][size]["value"], bpt / bits, rel_tol=1e-9)
        assert math.isclose(cfg["figures"][check]["value"], vspt / bits, rel_tol=1e-9)
        assert b.words.shown(cfg["figures"][size]["value"], "B/bit_token") == size_shown
        assert b.words.shown(cfg["figures"][check]["value"], "s/bit_token") == check_shown


def test_board_order_by_hand(monkeypatch: pytest.MonkeyPatch) -> None:
    """S5 on hand-made rows: overhead ascending by stored value, whatever the scope; a row with
    no overhead last; ties by system name whatever its case, then profile, then position."""
    draw = renderer(ROOT).draw
    rows = {"a": {"name": "alpha"}, "b": {"name": "Beta"}, "c": {"name": "gamma"}}
    monkeypatch.setattr(draw.state, "V", {"facts": {"rows": rows}})

    def cfg(system: str, overhead: float | None, profile: str = "p", position: int = 0) -> Any:
        figs: dict[str, dict[str, float | None]] = {m: {"sort_key": None} for m in
                ("proof_bytes_per_active_weight_bit_token",
                 "verify_seconds_per_active_weight_bit_token", "per-bit")}  # fmt: skip
        figs["over"] = {"sort_key": overhead}
        return {"system": system, "profile": profile, "position": position, "figures": figs,
                "overhead_metric": "over", "per_bit_metric": "per-bit"}  # fmt: skip

    given = [cfg("a", None), cfg("c", 15756.0), cfg("b", 61.28), cfg("a", 61.28, "p", 3),
             cfg("a", 61.28, "p", 1)]  # fmt: skip
    got = [(c["system"], c["position"]) for c in draw.overview.board_order(given)]
    assert got == [("a", 1), ("a", 3), ("b", 0), ("c", 0), ("a", 0)]


def test_one_row_per_system(site: Build) -> None:
    """S6: one table across models, one row per benchmarked system, on the workload
    `facts.json` names for it (`overview_workload`) or its only one; its glyph once. A system's
    other configurations are on its system page only; reference rows are not on the overview
    (they are the baseline the overhead divides by)."""
    index = site.pages["index.html"]
    assert len(TABLE.findall(index)) == 1
    rows = [rid for rid, *_ in ROW.findall(index)]
    assert sorted(rows) == sorted(site.view["orders"]["benchmarked"])
    for system in rows:
        cfgs = [c for c in provers(site.view) if c["system"] == system]
        named = site.view["facts"]["rows"][system].get("overview_workload")
        want = named or cfgs[0]["workload"]["id"]
        assert len(cfgs) == 1 or named, system
        assert row_config(site.view, system)["workload"]["id"] == want, system
        assert index.count(f'<a class="pie" href="/{system}#') == 1, system
        assert f'id="nb-{system}"' not in index, system
    for ref in site.view["orders"]["reference"]:
        assert f'<div class="row" id="{ref}"' not in index, ref
    if site.kind == "extras":  # FlashProve's batch-1 workload stays on its system page
        fp = [c["workload"]["id"] for c in provers(site.view) if c["system"] == "flashprove"]
        assert sorted(fp) == ["fp-maverick-w1024-b1", "fp-maverick-w1024-b24"]
        assert row_config(site.view, "flashprove")["workload"]["id"] == "fp-maverick-w1024-b24"


def test_no_ranking(site: Build) -> None:
    """S5: no rank number, medal, aggregate score or marked extreme value on any page."""
    heads = [plain(h) for h in HEAD.findall(site.pages["index.html"])]
    assert heads
    assert not [w for w in heads if re.search(r"score|rank|total|overall|best", w, re.I)]
    for name, text in site.pages.items():
        assert "<strong>" not in text, name
        assert not re.search(r'class="[^"]*\b(best|winner|rank|medal|podium|leader)\b', text), name
        assert not re.search("[\U0001f947-\U0001f949\U0001f3c6]", text), name  # medals, cup
        assert not re.search(r"#\s?1\b|\b1st\b", plain(text)), name


def test_division_named(site: Build) -> None:
    """S6: the system page names the workload, its division and the profile of the configuration
    it shows; on the overview a row on a closed or open workload names its division beside its
    model (RFC-0003 §Divisions); a native row names none."""
    for system in site.view["orders"]["benchmarked"]:
        text = plain(site.pages[f"{system}.html"])
        for cfg in system_configs(site, system):
            assert cfg["workload"]["division"] in {"native", "closed", "open"}
            where = f"{cfg['workload']['id']} ↗ · {cfg['workload']['division']} · {cfg['profile']}"
            assert where in text, system
    for rid, *_, body in ROW.findall(site.pages["index.html"]):  # a closed row says so
        division = row_config(site.view, rid)["workload"]["division"]
        model = plain(re.search(r'<div class="mc"[^>]*>(.*?)</div>', body, re.S)[1])  # type: ignore[index]
        assert (f"{division} division" in model) == (division != "native"), rid


def test_runs_left_out_listed(site: Build) -> None:
    """S7: each failed repetition and each superseded or ineligible run of each configuration a
    system page shows is listed above that configuration's figures, by its run id, with its
    reasons (a failure's exit code and last line; a superseded run's replacing run), and is in
    no statistic (the completed count is over the completed runs only). Each run's record is
    linked (`test_run_records_link`)."""
    listed = 0
    for system in site.view["orders"]["benchmarked"]:
        text = site.pages[f"{system}.html"]
        leads = [m.start() for m in re.finditer('<p class="lead">', text)]
        plates = [m.start() for m in re.finditer('class="plate" id="[^"]*fig-', text)]
        configs = system_configs(site, system)
        assert len(leads) == len(configs)
        for i, (cfg, at) in enumerate(zip(configs, leads, strict=True)):
            # each configuration's runs come before its own plates, after the previous ones
            assert at < plates[i * len(COLS)]
            assert i == 0 or plates[i * len(COLS) - 1] < at
            block = text[at : plates[i * len(COLS)]]
            listed += _left_out_listed(cfg, flat(block), block, system)
    assert listed >= 2  # SASH: one failed repetition, one superseded run


def _left_out_listed(cfg: dict[str, Any], said: str, block: str, system: str) -> int:
    """One configuration's runs line and list hold each of its runs not counted (S7)."""
    listed = 0
    runs = cfg["runs"]
    assert f"{len(runs['completed'])} completed" in said
    for f in runs["failed"]:
        assert f["run_id"] in said, system
        if f["exit_code"] is not None:
            assert f"exit {f['exit_code']}" in said, system
        if f["last_line"]:
            assert f["last_line"] in said, system
        listed += 1
    for x in runs["left_out"]:
        assert x["run_id"] in said, system
        if x["replaced_by"]:
            assert "replaced by" in said, system
            assert x["replaced_by"] in said, system
        for reason in x["reason_words"]:
            assert reason.split(": ", 1)[-1] in said, (system, reason)
        listed += 1
    if runs["failed"] or runs["left_out"]:
        assert 'class="runs lo"' in block
        assert '<span class="rec">' not in block
    for f in cfg["figures"].values():
        if f.get("stats"):
            assert f["stats"]["n"] == len(runs["completed"]), system
            assert f["stats"]["n_failed"] == len(runs["failed"]), system
    return listed


def test_run_records_link(extras: Build) -> None:
    """S7: each run left out links its record (and the run that replaced it) at the commit the
    site links."""
    build = renderer(ROOT)
    view = json.loads(json.dumps(extras.view))
    build.setup(view, extras.out)
    sash = next(c for c in view["configurations"] if c["system"] == "sash")
    block = build.draw.pages.left_out(sash)
    for x in [*sash["runs"]["left_out"], *sash["runs"]["failed"]]:
        assert f'href="{view["repository"]}/blob/main/{x["record"]}"' in block, x["run_id"]
    for x in sash["runs"]["left_out"]:
        if x["replaced_by"]:
            assert f'/blob/main/{x["replaced_by_record"]}"' in block


def test_unexpected_control_printed_in_full(site: Build) -> None:
    """RFC-0008 §Reporting: every control outcome outside its expected set is printed on its
    system page from its stored record (control, run, outcome, expected set, the honest twin,
    each trial on one line with its seed, mutation, outcome, raw exit code and last line, and
    the record), and the release page links it."""
    release = site.pages["release.html"]
    seen = 0
    for cfg in provers(site.view):
        text = site.pages[f"{cfg['system']}.html"]
        for u in cfg["unexpected"]:
            anchor = f"unexpected-{u['control']}-{u['run_id']}"
            start = text.index(f'id="{anchor}"')
            block = text[start : text.index("</dl>", start)]
            said = flat(block)
            stored = u["stored"]
            assert u["control"] in said
            assert u["run_id"] in said
            assert f'/{u["record"]}"' in block  # the record, in full
            for x in stored["expected"]:
                assert x.replace("_", " ").replace("invalid call", "refused") in said or x in said
            trials = re.findall(r"<li>(.*?)</li>", block, re.S)
            assert len(trials) == len(stored["trials"])
            for t, line in zip(stored["trials"], trials, strict=True):
                one = plain(line)
                assert f"seed {t['seed_index']}" in one, one
                assert t["raw_last_line"] in html.unescape(line), one
                for v in t["mutation"].values():
                    assert (f"{v:,}" if isinstance(v, int) else str(v)) in one, (v, one)
            assert f'href="/{cfg["system"]}#{anchor}"' in release
            assert text.index('id="h-tamper"') < text.index(f'id="{anchor}"')
            seen += 1
    if site.kind == "web":
        assert not seen
        assert "No tamper-test outcome fell outside its expected set." in plain(release)
    else:
        assert seen == 2  # FlashProve's C1 and SASH's C2


def test_table_semantics(site: Build) -> None:
    """S9: every cell of a table across systems has one column header and one row header through
    ARIA roles, a sorted column's header carries `aria-sort`, and every glyph state is a word in
    the row header's cell, read after the system's name; the more-numbers tables use `th` with
    `scope`."""
    index = site.pages["index.html"]
    for sec in SECTION.findall(index):
        heads = HEAD.findall(sec)
        assert len(heads) == 1 + len(BOARD)  # System (the model under its name), the figures
        assert sec.count('role="columnheader"') == len(heads)
        assert sec.count('aria-sort="') == 1
        for rid, _, _, row in ROW.findall(sec):
            assert row.count('role="rowheader"') == 1, rid
            assert row.count('role="cell"') == len(BOARD), rid
            head = HEADER.search(row)[1]  # type: ignore[index]
            assert head.index('class="name"') < head.index('<p class="sr">'), rid
            assert re.search(r'<p class="sr">[^<]*: (Yes|Partly|No|Not stated)', head), rid
    for system in site.view["orders"]["benchmarked"]:
        tables = re.findall(r'<table class="mtab">(.*?)</table>', site.pages[f"{system}.html"])
        assert tables
        for table in tables:
            rows = re.findall(r"<tr>(.*?)</tr>", table)
            assert rows[0].count('<th scope="col">') == 3
            for row in rows[1:]:
                assert row.count('<th scope="row">') == 1
                assert row.count("<td") == 2


def local(url: str) -> bool:
    """A root-relative address on the site's own origin."""
    return url.startswith("/") and not url.startswith("//")


def test_reads_without_script(site: Build) -> None:
    """S10: every row, figure, label and glyph state is in the HTML as sent; every script is a
    site file or an inline script whose hash the Content-Security-Policy lists; no page loads a
    script, style sheet, font, image or frame from another origin (links to other sites are
    allowed)."""
    vercel = json.loads((site.out / "vercel.json").read_text())
    csp = next(h["value"] for rule in vercel["headers"] for h in rule["headers"]
               if h["key"] == "Content-Security-Policy")  # fmt: skip
    allowed = set(re.findall(r"'(sha256-[^']+)'", csp))
    for name, text in site.pages.items():
        for attrs, body in re.findall(r"<script([^>]*)>(.*?)</script>", text, re.S):
            src = re.search(r'src="([^"]+)"', attrs)
            if src:
                assert local(src[1]), (name, src[1])
                assert not body.strip()
            else:
                digest = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
                assert f"sha256-{digest}" in allowed, name
        for tag in re.findall(r"<(?:img|iframe|source|video|audio|embed|object)\b[^>]*>", text):
            src = re.search(r'(?:src|data)="([^"]+)"', tag)
            assert not src or local(src[1]), tag
        for tag in re.findall(r"<link\b[^>]*>", text):
            if re.search(r'rel="(stylesheet|preload|icon|apple-touch-icon|modulepreload)"', tag):
                href = re.search(r'href="([^"]+)"', tag)[1]  # type: ignore[index]
                assert local(href), tag
        assert not re.search(r"url\(\s*['\"]?(https?:)?//", text), name
    index = site.pages["index.html"]
    rows = ROW.findall(index)
    for system in site.view["orders"]["benchmarked"]:
        assert any(rid == system for rid, *_ in rows)
    assert all(NUMBER.search(body) for *_, body in rows)  # figures are in the HTML as sent
    for ref in site.view["orders"]["not_benchmarked"]:
        assert site.view["facts"]["rows"][ref]["name"] in plain(index), ref


def test_tally_names_each_accepted_control(site: Build) -> None:
    """RFC-0008, AGENTS.md rule 10: an accepted outcome is never printed as a bare count. Each
    "it accepted N" names the controls it counts and whether each one's own expected set holds
    acceptance, so a system's weakened-prover control (which expects acceptance) never reads as
    a tampered proof the checker took; the control line says it was expected."""
    seen = 0
    for system in site.view["orders"]["benchmarked"]:
        text = plain(site.pages[f"{system}.html"])
        for cfg in system_configs(site, system):
            for a in cfg["accepted"]:
                assert a["control"] in text, (system, a["control"])
        for m in re.finditer(r"accepted (\d+)", text):
            assert text[m.end() : m.end() + 2] == " (", text[m.start() : m.end() + 40]
            seen += 1
        for a in (a for c in system_configs(site, system) for a in c["accepted"]):
            if a["source"] == "system" and a["passed"]:
                assert "the control test below, which expects acceptance" in text
                assert "accepted the proof, as this control expects" in text
    assert seen >= 1  # the deployed SASH's weakened-prover control; the extras FlashProve's C1


def test_figures_link_their_own_plate(site: Build) -> None:
    """S2, S11: each overview figure of a system row links a plate on its system page, in the
    same column and of the row's own configuration (its source names the configuration's
    position in the index)."""
    index = site.pages["index.html"]
    linked = 0
    for rid, _, _, body in ROW.findall(index):
        cfg = row_config(site.view, rid)
        for col, href in re.findall(r'data-col="([^"]+)"><a class="val" href="([^"]*)"', body):
            page, _, frag = href.partition("#")
            assert page == f"/{cfg['system']}", href
            text = site.pages[f"{page[1:]}.html"]
            plates = {pid: (c, b) for pid, c, b in PLATE.findall(text)}
            assert frag in plates, href
            assert plate_config(site, cfg["system"], frag) is cfg, href
            assert plates[frag][0] == col, href
            source = re.sub(r"<[^>]+>", "", plates[frag][1])
            f = cfg["figures"][metric(cfg, col)]
            if f["recorded"]:  # its record is this configuration's: the key under its prefix
                assert f["source"].rsplit("/statistics/", 1)[1] in source, href
                assert f"#/configurations/{cfg['position']}/statistics/" in flat(text), href
            linked += 1
    assert linked == len(BOARD) * len(site.view["orders"]["benchmarked"])


def test_generated_html_passes_g8(site: Build, tmp_path: Path) -> None:
    """S8: every page the build writes passes the RFC-0013 G8 word list."""
    from iproofs.validate.tree import g8_language  # noqa: PLC0415

    for name, text in site.pages.items():
        (tmp_path / name).write_text(text)
    assert g8_language(tmp_path, [], named=sorted(site.pages)) == []


def test_overview_says_each_thing_once(site: Build) -> None:
    """Owner decisions of 2026-11-09: the legend names the properties and nothing else (the
    slice inks and their tips name the states; Criteria is in the header); the section headings
    carry no count; the row header prints no pin (the name's title holds it, the system page
    prints it); Not benchmarked yet names each family once, as a group heading, and each card's
    status only where it is not active; each glyph there names its petals (hit wedges, a tip)."""
    index = site.pages["index.html"]
    mast = index[index.index('<section class="mast"') : index.index("</section>")]
    assert 'class="chip"' not in mast
    assert "<a " not in mast
    assert "Not stated" not in mast
    assert "<sup" not in index
    assert 'class="pin"' not in index
    assert 'class="wl"' not in index
    rows, crit = site.view["facts"]["rows"], site.view["criteria"]["rows"]
    families = {crit[r]["family"] for r in site.view["orders"]["not_benchmarked"]}
    heads = re.findall(r'<h3 class="nbh" id="nbh-([a-z_]+)">', index)
    assert sorted(heads) == sorted(families)
    for rid in site.view["orders"]["not_benchmarked"]:
        card = re.search(rf'<li class="nb" id="nb-{rid}">(.*?)</li>', index, re.S)
        assert card, rid
        assert card[1].count('class="hit"') >= 1, rid
        assert 'class="tip"' in card[1], rid
        said = plain(card[1])
        assert "Active" not in said, rid
        assert "Proved" not in said, rid
        if rows[rid]["status"]["state"] != "active":
            assert said.lower().count(rows[rid]["status"]["state"].replace("_", " ")) == 1, rid
        if crit[rid].get("own_sources"):
            assert '<h4 class="nbn"><a href="https://' in card[1], rid
