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


# a cell recorded not_stated is printed No, its reason saying it is not stated (RFC-0016 ST-2)
WORD = {"yes": "Yes", "partly": "Partly", "no": "No", "not_stated": "No"}
VAL = re.compile(r'<a class="val" href="([^"]*)" title="([^"]*)">(.*?)</a>', re.S)
ROW = re.compile(
    r'<div class="row" id="([^"]+)" role="row" data-name="([^"]+)" data-k="([^"]+)">'
    r"(.*?)\n</div>",
    re.S,
)
HEADER = re.compile(r'<div class="sysc" role="rowheader"[^>]*>(.*?)\n    </div>', re.S)
# a plate; one with no value (`nil`) is one row, its name and why
PLATE = re.compile(
    r'<div class="plate(?: nil)?" id="([^"]+)" data-col="([^"]+)">(.*?)</dl></div>', re.S
)
DD = re.compile(r"<dt>([^<]+)</dt><dd>(.*?)</dd>", re.S)
NUMBER = re.compile(r'<span class="n">([^<]+)</span><span class="u(?: x)?">([^<]+)</span>')
# an overview cell's title: sample size and range (S3); the plate it links holds the sd
TITLE_SPREAD = re.compile(
    r"(\d+) completed, (\d+) failed, (\S+(?: \S+)? to \S+(?: \S+)?|the same in all \d+ runs)"
)
# a plate's spread (S3; the setup's runs line names n, the plate's number is the mean): the range
# with its unit once, then the sd; a constant as the same in all its runs, without its value
SPREAD = re.compile(r"the same in all \d+ runs|\S+ to \S+(?: \S+)?(?: · sd .+)?")
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
        configuration, workload, _, profile = html.unescape(named).split(" · ")[-4:]
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
    return [row for table in re.findall(r'<table class="mtab more">(.*?)</table>', text, re.S)
            for row in re.findall(r'<tr><th scope="row">.*?</tr>', table)]  # fmt: skip


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
        # RFC-0004 INV-DERIVE-7: the width, note and limit under each setup's per-Gbit plates,
        # or once under the Figures heading where every setup of the page shares them
        basis = re.findall(r'<dl class="tlab notes basis"[^>]*>(.*?)</dl>', text, re.S)
        assert len(basis) == len(set(basis))
        assert len(basis) == len(configs) or len(basis) == 1
        assert all({"weight bits", "limit"} <= {dt for dt, _ in DD.findall(b)} for b in basis)
        for pid, col, body in plates:
            cfg = plate_config(site, system, pid)
            dts = {dt for dt, _ in DD.findall(body)} | shared[configs.index(cfg)]
            f = cfg["figures"][metric(cfg, col)]
            if 'class="fig"' in body:
                assert {"grade", "evidence", "workload", "source"} <= dts, pid
                assert ("spread" in dts) or ("pairs" in dts), pid
                assert ("scope" in dts) == (f["scope"] is not None), pid  # a timed number
            else:  # one row, its name and why: no value line, no record; the warm overhead
                # keeps its scope (RFC-0004 INV-DERIVE-11)
                own = {dt for dt, _ in DD.findall(body)}
                assert body.startswith('<dl><div><dt class="lbl"'), pid
                assert '<p class="pv"' not in body, pid
                assert "source" not in own, pid
                assert ("scope" in own) == (f["metric"] == "overhead_vs_production_warm"), pid
        rows = more_rows(text)
        assert len(rows) == 5 * len(configs)
        for row in rows:  # every label a plate holds, or why there is no value
            said = plain(row)
            if 'class="ml mw"' in row:
                continue
            for label in ("spread: ", "source: "):
                assert label in said, (label, said)


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
    first_figure = re.search(r'class="plate(?: nil)?" id="[^"]*fig-', text).start()  # type: ignore[union-attr]
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
# the link from a property to its entry in "How we read it": the property's name (the state and
# the reason are plain text)
READ_LINK = re.compile(r'<p class="rn"><a href="#read-([a-z_]+)">([^<]*)</a>')


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
    links = READ_LINK.findall(body)
    if entry:  # the name links this property's own entry, which exists
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


def quote_words(text: str) -> str:
    """A stored quote's words, its inline marks (code, strong, emphasis), double quotes and a
    table row's cell bars left out: what the page prints, every word in place."""
    t = re.sub(r"\*\*|`", "", text)
    t = re.sub(r"(?<![\w*])\*([^*\s][^*]*?)\*(?![\w*])", r"\1", t)
    return re.sub(r"\s+", " ", t.replace(" | ", " ").replace('"', "")).strip()


def quote_words_printed(body: str) -> str:
    """The words of every quote an entry prints, its marks rendered and quotes curly, a quoted
    table's cells and rows apart, read back as `quote_words` writes them."""
    quotes = re.findall(r'<blockquote class="eq">(.*?)</blockquote>', body, re.S)
    said = flat(" | ".join(re.sub(r"</t[dhr]>(?=.)", " ", q) for q in quotes))  # cells apart
    said = said.replace("\N{NARROW NO-BREAK SPACE}", " ")
    return re.sub(r"\s+", " ", re.sub('[\u201c\u201d"]', "", said))


def _quotes_printed(
    system: str, p: dict[str, Any], cell: dict[str, Any], body: str, said: str, home: str
) -> None:
    """S1 item 1 in the property's entry of "How we read it": the one quote marked `decides`,
    verbatim, with its source at the pin; a stated cell always prints it; a quote that does not
    decide is printed only in a conflict (both quotes, `conflict_lines`)."""
    deciding = [q for q in cell["quotes"] if q.get("decides")]
    if cell["state"] != "not_stated":
        assert len(deciding) == 1, (system, p["id"])  # a stated cell prints the quote it rests on
    printed = quote_words_printed(body)
    for q in [q for q in cell["quotes"] if q not in deciding]:  # a non-deciding quote: not here
        assert cell["conflict"] or quote_words(q["text"]) not in printed, (system, p["id"])
    for q in deciding:  # verbatim, with its source at the pin: path and lines in the card's own
        # repository (the facts' pinned row names it), another repository's name first
        assert quote_words(q["text"]) in printed, (system, p["id"])
        assert f'href="{html.escape(q["url"])}"' in body, (system, p["id"])
        where = f"{q['path']} {q['lines']}"
        shown = where if q["repo"] == home else f"{q['repo'].rsplit('/', 1)[-1]}: {where}"
        title = f"{q['repo']}@{q['commit'][:8]} {where}"
        link = re.search(
            rf'<a class="qsrc" href="{re.escape(html.escape(q["url"]))}" '
            rf'title="{re.escape(html.escape(title))}"[^>]*>(.*?)</a>',
            body,
            re.S,
        )
        assert link, (system, p["id"])
        assert flat(link[1]) == f"{shown} ↗", (system, p["id"], flat(link[1]))


def _how_we_read(site: Build, system: str, p: dict[str, Any], pc: dict[str, Any] | None) -> None:
    """RFC-0016 ST-2, ST-8, OVR-7 in the fold "How we read it": the deciding quote with its
    source, both quotes of a conflict, the sources read, and each mapped control in every run
    read (with no run read, no control line: OVR-5 makes that an error for review). The entry
    takes focus (`tabindex="-1"`, words.js)."""
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
    home = next(c for c in site.view["configurations"] if c["system"] == system)["card"]
    _quotes_printed(system, p, cell, body, said, home["upstream"]["repo"])
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
    for cid in mapped if pc["runs"] else []:
        assert cid in said, (system, cid)
    for run in pc["runs"] if mapped else []:  # every run read, under every mapped property
        assert run["run_id"] in said, (system, p["id"], run["run_id"])
    if not pc["runs"]:  # no run read: no control line, never "not run" (OVR-5)
        assert 'class="ec"' not in body, (system, p["id"])


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
    on system pages: the counts in its setup's runs line, the mean as its number (its title
    says so, so the spread never repeats it), the range and the sd under it; the same in the
    title of its overview cell (owner decision of 2026-11-09: nothing but a scope word under an
    overview figure), equal to the stored ones; a reference whose runs all failed shows its
    counts and "below minimum repetitions" on `/reference`; each more-numbers row shows them
    too."""
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
            assert "mean" not in plain(spread), spread
            assert f'<p class="pv" title="mean of {stats["n"]} runs">' in body, pid
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


MORE_SPREAD = re.compile(r"spread: (the same in all \d+ runs|.+? to .+?)( · |$)")
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
    per Gbit names its scope in a word (steady, or session where the steady figure is null), its
    full words read aloud, check time its
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
        under = {c: plain(re.sub(r'<span class="sr">.*?</span>', "", m[1])) if (m := sub.search(v))
                 else "" for c, v in cells.items()}  # fmt: skip
        aloud = {c: plain("".join(re.findall(r'<span class="sr">(.*?)</span>', m[1])))
                 if (m := sub.search(v)) else "" for c, v in cells.items()}  # fmt: skip
        over = cfg["figures"][cfg["overhead_metric"]]
        if over["value"] is not None:
            assert plain(b.words.SCOPE_LINES[over["metric"]]) in said["overhead"], rid
            pairs = over["pairs"]
            assert f"{pairs['n_system']} prover run" in said["overhead"], rid
            assert f"{pairs['n_serving']} serving run" in said["overhead"], rid
            assert plain(cfg["overhead_words"]["brief"]) in said["overhead"], rid
            assert under["overhead"] == b.words.SCOPE_SHORT[over["metric"]], rid
            assert aloud["overhead"] == plain(b.words.SCOPE_LINES[over["metric"]]), rid
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
                == {"prove.steady": "steady", "prove.session": "session"}[bit["scope"]]
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
        plates = [m.start() for m in re.finditer('class="plate(?: nil)?" id="[^"]*fig-', text)]
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
            if u.get("not_read"):  # tests nothing: the expected set rides in the head's title
                said += " " + html.unescape(" ".join(re.findall(r'title="([^"]*)"', block)))
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
        assert "Every outcome fell inside its expected set." in plain(release)
    else:
        assert seen == 2  # FlashProve's C1 and SASH's C2
        assert "Every outcome fell inside" not in plain(release)
        assert "Outside their expected set:" in plain(release)
