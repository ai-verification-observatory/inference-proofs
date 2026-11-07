"""RFC-0009 §Testing Strategy: the §Site rules on the pages `iproofs site build` writes (#320).

Page tests run over two builds: the placeholder release with every test-only case (`extras`,
never deployed) and the committed `web/` pages (the deployed build, `extras=False`), each with
the view it was printed from. A check that needs a test-only case skips on `web/` and says so.

Where RFC-0009 §Site lists a gap for #320 that its second pull request closes (system page
validated claims, card identity and card in full, run ids and links, per-configuration sections,
the References table's roles, the footer links), the test says so in its docstring and checks
what the pages hold today. Renamed tests (RFC-0009 §Testing Strategy): `test_display_rounding`
is `test_sort_key_is_stored_value`, `test_no_aggregate_score_column` is `test_no_ranking`,
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

from fixtures.placeholder_release import build_site
from iproofs.site import reply_html
from iproofs.site.view import site_view

ROOT = Path(__file__).resolve().parents[3]
COLS = ("covers", "proof_size", "check_time", "overhead")
METRIC = {
    "covers": "tokens_covered_per_proof",
    "proof_size": "proof_bytes",
    "check_time": "verify_seconds",
    "overhead": "overhead_vs_serving_prove.session",
}
WORD = {"yes": "Yes", "partly": "Partly", "no": "No", "not_stated": "Not stated"}
VAL = re.compile(r'<a class="val" href="([^"]*)" title="([^"]*)">(.*?)</a>', re.S)
ROW = re.compile(
    r'<div class="row" id="([^"]+)" role="row" data-name="([^"]+)" data-k="([^"]+)">'
    r"(.*?)\n</div>",
    re.S,
)
TABLE = re.compile(
    r'<section class="sec bench" id="([^"]+)".*?<div class="tbl" role="table".*?'
    r'<div class="rows" role="rowgroup">(.*?)</section>',
    re.S,
)
SECTION = re.compile(r'<section class="sec bench" id="[^"]+".*?</section>', re.S)
HEAD = re.compile(r'<div class="hc[^"]*" role="columnheader"[^>]*>(.*?)</div>')
HEADER = re.compile(r'<div class="sysc" role="rowheader"[^>]*>(.*?)\n    </div>', re.S)
PLATE = re.compile(r'<div class="plate" id="([^"]+)" data-col="([^"]+)">(.*?)</dl></div>', re.S)
DD = re.compile(r"<dt>([^<]+)</dt><dd>(.*?)</dd>", re.S)
NUMBER = re.compile(r'<span class="n">([^<]+)</span><span class="u">([^<]+)</span>')
SPREAD = re.compile(
    r"(\d+) completed, (\d+) failed · (\S+(?: \S+)?) to (\S+(?: \S+)?) · mean \S+(?: \S+)?"
    r" · sd \S+(?: \S+)?"
)
# reading units back to the stored base unit, by hand (RFC-0012: scaling is display only)
SCALE = {"positions": 1.0, "B": 1.0, "kB": 1e3, "MB": 1e6, "GB": 1e9, "TB": 1e12, "ms": 1e-3,
         "s": 1.0, "min": 60.0, "h": 3600.0, "\N{MULTIPLICATION SIGN}": 1.0}  # fmt: skip


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


def _build(root: Path, *, extras: bool) -> tuple[Path, dict[str, Any]]:
    out = build_site(root / "repo", root / "out", extras=extras)
    return out, site_view(root / "repo")


@pytest.fixture(scope="module")
def extras(tmp_path_factory: pytest.TempPathFactory) -> Build:
    out, view = _build(tmp_path_factory.mktemp("site-extras"), extras=True)
    return Build("extras", {p.name: p.read_text("utf-8") for p in out.glob("*.html")}, view, out)


@pytest.fixture(scope="module")
def deployed(tmp_path_factory: pytest.TempPathFactory) -> Build:
    """The committed web/ pages, with the view of the build that wrote them (web/ tests hold
    the committed files equal to a fresh build)."""
    _, view = _build(tmp_path_factory.mktemp("site-web"), extras=False)
    web = ROOT / "web"
    return Build("web", {p.name: p.read_text("utf-8") for p in web.glob("*.html")}, view, web)


@pytest.fixture(scope="module", params=["extras", "web"])
def site(request: pytest.FixtureRequest) -> Build:
    build = request.getfixturevalue("extras" if request.param == "extras" else "deployed")
    assert isinstance(build, Build)
    return build


def provers(view: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for c in view["configurations"] if c["kind"] == "prover"]


def row_config(view: dict[str, Any], rid: str) -> dict[str, Any]:
    """The configuration an overview row id names: `system` or `system--configuration--workload`."""
    system, _, rest = rid.partition("--")
    configuration, _, workload = rest.partition("--")
    found = [c for c in provers(view) if c["system"] == system and (not configuration or (
        c["configuration"], c["workload"]["id"]) == (configuration, workload))]  # fmt: skip
    assert len(found) == 1, rid
    return found[0]


def system_config(build: Build, system: str) -> dict[str, Any]:
    """The configuration a system page shows: the one its configuration line names."""
    text = build.pages[f"{system}.html"]
    named = plain(re.search(r"<dt>configuration</dt><dd>(.*?)</dd>", text, re.S)[1])  # type: ignore[index]
    configuration, workload, _, profile = named.split(" · ")
    found: list[dict[str, Any]] = [c for c in build.view["configurations"] if c["system"] == system
             and (c["configuration"], c["workload"]["id"], c["profile"])
             == (configuration, workload, profile)]  # fmt: skip
    assert len(found) == 1, named
    return found[0]


def test_page_set_and_footer(site: Build) -> None:
    """Page table: the overview, one page per benchmarked system, the references, the criteria
    and Not found; every footer names the release and links the criteria page. The release,
    sponsors and conflicts and targets pages and the footer links to them and to `index.json`
    are RFC-0009 §Site gaps for #320 (its second pull request; the index waits for #146)."""
    want = {"index.html", "reference.html", "criteria.html", "404.html"}
    want |= {f"{s}.html" for s in site.view["orders"]["benchmarked"]}
    assert want <= set(site.pages)
    release = site.view["release"]["id"]
    for name, text in site.pages.items():
        foot = text[text.index('<footer class="foot">') :]
        assert f"Release {release}" in plain(foot), name
        assert 'href="/criteria"' in foot, name


def test_every_number_has_labels(site: Build) -> None:
    """S2: each overview figure names its unit in view and its scope, grade, tier and record in
    its accessible description, and links its plate; each plate holds every label in view; each
    more-numbers row names its scope, grade and tier, or why it has no value. The record is the
    index pointer as text until #146 publishes the index (RFC-0009 §Site gaps)."""
    seen = 0
    for _, title, inner in VAL.findall(site.pages["index.html"]):
        if 'class="fig"' not in inner:
            continue
        assert NUMBER.search(inner), inner
        for label in ("scope: ", "grade: ", "checked: ", "source: releases/"):
            assert label in plain(title), (label, title)
        seen += 1
    assert seen >= 6  # two systems, three measured figures each
    for system in site.view["orders"]["benchmarked"]:
        text = site.pages[f"{system}.html"]
        figures = system_config(site, system)["figures"]
        plates = PLATE.findall(text)
        assert len(plates) == len(COLS)
        for pid, col, body in plates:
            dts = {dt for dt, _ in DD.findall(body)}
            if 'class="fig"' in body:
                assert {"spread", "scope", "grade", "checked", "workload", "source"} <= dts, pid
            else:  # a null value names its record; a metric the runs did not record has none
                assert "why" in dts, pid
                assert ("source" in dts) == figures[METRIC[col]]["recorded"], pid
        table = text[text.index('<table class="mtab">') : text.index("</table>")]
        for row in re.findall(r"<tr><th scope=\"row\">.*?</tr>", table):
            said = plain(row)
            assert ("scope: " in said and "grade: " in said and "checked: " in said) or (
                "No value" in said), said  # fmt: skip


def test_glyph_before_numbers(site: Build) -> None:
    """S1: on every page each row's header, holding its glyph, precedes the row's first figure;
    a system row's header links its system page and a reference's glyph its entry on
    `/reference`. The `#claims-<configuration>` target is an RFC-0009 §Site gap for #320."""
    index = site.pages["index.html"]
    rows = ROW.findall(index)
    assert rows
    for rid, _, _, body in rows:
        system = row_config(site.view, rid)["system"]
        assert body.index('class="pie"') < body.index('class="vc"'), rid
        assert f'<a href="/{system}">' in body[: body.index('class="vc"')], rid
    for ref in site.view["orders"]["reference"]:
        row = index[index.index(f'<div class="row" id="{ref}">') :]
        assert row.index('class="pie"') < row.index('class="vc"'), ref
        assert f'href="/reference#{ref}"' in row[: row.index('class="vc"')], ref
    for system in site.view["orders"]["benchmarked"]:
        text = site.pages[f"{system}.html"]
        assert text.index('class="rpie"') < text.index('class="plate"'), system
    ref = site.pages["reference.html"]
    for gid in site.view["orders"]["reference"]:
        sec = ref[ref.index(f'id="{gid}" aria-labelledby') :]
        assert sec.index('class="rpie"') < sec.index('class="plate"'), gid


def test_claim_card_before_numbers(site: Build) -> None:
    """S1, INV-CLAIM-1: in every table across systems each row's header precedes the row's first
    figure and holds the glyph with each state as a word, the name, the pin of the row's card and,
    where the table holds two rows of the system, the card's `configuration`, and no value of any
    other card field; each state is the state the criteria file sets for that card (RFC-0016).
    On system pages the validated claims precede every figure. Their quotes, sources and control
    outcomes, the card's identity and digest, the card in full and the agreement rate are
    RFC-0009 §Site gaps for #320 (its second pull request)."""
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
            said = plain(re.search(r'<p class="sr">(.*?)</p>', head)[1])  # type: ignore[index]
            cells = criteria[cfg["system"]]["cells"]
            for p in props:
                state = cells[p["id"]]["state"]
                if state is not None:  # a pending row draws no state (OVR-8)
                    assert f"{p['name']}: {WORD[state]}" in said, (rid, p["id"])
            assert site.view["facts"]["rows"][cfg["system"]]["name"] in plain(head)
            assert f"/tree/{cfg['card']['body']['upstream']['commit']}" in head
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
        text = site.pages[f"{system}.html"]
        assert text.index('class="rprops"') < text.index('class="fig"'), system
        cells = criteria[system]["cells"]
        for p in props:
            item = re.search(rf'<li class="rp [rl]" id="p-{p["id"]}".*?</li>', text, re.S)
            assert item, (system, p["id"])
            state = cells[p["id"]]["state"]
            if state is not None:
                assert '<p class="rs"><i class="sw ' in item[0]
                assert WORD[state] in plain(item[0]), (system, p["id"])


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
    on system pages, and its counts and range on the overview, equal to the stored ones; a
    reference whose runs all failed shows its counts and "below minimum repetitions" on the
    overview and on `/reference`. The more-numbers table's statistics are a gap for #320."""
    for _, title, inner in VAL.findall(site.pages["index.html"]):
        if "spread: " not in html.unescape(title):
            continue
        assert re.search(r"\d+ completed, \d+ failed", plain(inner)), inner
        assert " to " in plain(inner), inner
    for system in site.view["orders"]["benchmarked"]:
        cfg = system_config(site, system)
        for _, col, body in PLATE.findall(site.pages[f"{system}.html"]):
            stats = cfg["figures"][METRIC[col]].get("stats")
            if not stats:
                continue
            spread = dict(DD.findall(body))["spread"]
            got = SPREAD.fullmatch(plain(spread))
            assert got, spread
            assert (int(got[1]), int(got[2])) == (stats["n"], stats["n_failed"])
    failed = [c for c in site.view["configurations"]
              if c["kind"] == "reference" and c["insufficient_repetitions"]]  # fmt: skip
    assert failed
    for page in ("index.html", "reference.html"):
        assert site.pages[page].count("below minimum repetitions") == len(failed), page
        for c in failed:
            n = f"{len(c['runs']['completed'])} completed, {len(c['runs']['failed'])} failed"
            assert n in plain(site.pages[page]), (page, c["system"])


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
        assert set(got) == set(COLS)
        cells = dict(re.findall(r'data-col="([^"]+)">(<a class="val".*?</a>)</div>', body, re.S))
        for col, metric in METRIC.items():
            stored = cfg["figures"][metric]["value"]
            assert got[col] == stored, (rid, col)
            printed = NUMBER.search(cells[col])
            if stored is None:
                assert printed is None, (rid, col)
                continue
            assert printed, (rid, col)
            number, unit = printed[1], printed[2]
            assert _significant(number) == 4 or float(number.replace(",", "")).is_integer()
            value = float(number.replace(",", "")) * SCALE[unit]
            exponent = math.floor(math.log10(abs(value)))
            assert abs(value - stored) <= 0.5 * 10 ** (exponent - 3) * 1.0001, (rid, col)


def test_default_order_alphabetical(site: Build) -> None:
    """S5: the HTML as sent holds every table's rows A to Z by name; other orders on request."""
    tables = TABLE.findall(site.pages["index.html"])
    assert tables
    names = site.view["facts"]["rows"]
    for _, body in tables:
        shown = [names[row_config(site.view, rid)["system"]]["name"].lower()
                 for rid, *_ in ROW.findall(body)]  # fmt: skip
        assert shown == sorted(shown)
    assert 'aria-sort="ascending"' in site.pages["index.html"]
    nb = site.view["orders"]["not_benchmarked"]
    assert [names[r]["name"].lower() for r in nb] == sorted(names[r]["name"].lower() for r in nb)


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
    it shows. Table headings naming them on the overview and `/reference` are RFC-0009 §Site
    gaps for #320 (an owner decision on the overview's look)."""
    for system in site.view["orders"]["benchmarked"]:
        cfg = system_config(site, system)
        assert cfg["workload"]["division"] in {"native", "closed", "open"}
        text = plain(site.pages[f"{system}.html"])
        where = f"{cfg['workload']['id']} · {cfg['workload']['division']} · {cfg['profile']}"
        assert where in text, system


def test_native_workloads_header(site: Build) -> None:
    """S6: tables of different native workloads side by side (two workloads on one model) carry
    the header above them; a model with one workload table carries none."""
    sections = SECTION.findall(site.pages["index.html"])
    header = "Native workloads differ: rows are not a head-to-head comparison"
    models: dict[str, list[str]] = {}
    for sec in sections:
        name = plain(re.search(r'<h2 [^>]*class="sect">(.*?)</h2>', sec)[1])  # type: ignore[index]
        models.setdefault(name, []).append(sec)
    side_by_side = [secs for secs in models.values() if len(secs) > 1]
    if site.kind == "web":
        assert not side_by_side
        assert header not in site.pages["index.html"]
        pytest.skip("the deployed release has one workload per model; the extras build has two")
    assert side_by_side
    for secs in side_by_side:  # once, above the first table of the model
        assert [header in plain(s) for s in secs] == [True] + [False] * (len(secs) - 1)
    assert site.pages["index.html"].count(header) == len(side_by_side)


def test_runs_left_out_listed(site: Build) -> None:
    """S7: each failed repetition and each superseded or ineligible run of the configuration a
    system page shows is listed above its figures, with its reasons, exit code and last line, and
    is in no statistic (the completed count is over the completed runs only). Run ids, links to
    the run record and to the replacing run, and the sections of a system's other
    configurations, are RFC-0009 §Site gaps for #320 (its second pull request)."""
    listed = 0
    for system in site.view["orders"]["benchmarked"]:
        cfg = system_config(site, system)
        text = site.pages[f"{system}.html"]
        lead = text[text.index('<p class="lead">') :]
        lead = plain(lead[: lead.index("</p>")])
        assert text.index('<p class="lead">') < text.index('class="plate"')
        runs = cfg["runs"]
        assert f"{len(runs['completed'])} completed" in lead
        for f in runs["failed"]:
            if f["exit_code"] is not None:
                assert f"exit code {f['exit_code']}" in lead, system
            if f["last_line"]:
                assert f["last_line"] in lead, system
            listed += 1
        for x in runs["left_out"]:
            for reason in x["reasons"]:
                assert reason.split(": ", 1)[-1] in lead, (system, reason)
            listed += 1
        for f in cfg["figures"].values():
            if f.get("stats"):
                assert f["stats"]["n"] == len(runs["completed"]), system
                assert f["stats"]["n_failed"] == len(runs["failed"]), system
    assert listed >= 2  # SASH: one failed repetition, one superseded run


def test_table_semantics(site: Build) -> None:
    """S9: every cell of a table across systems has one column header and one row header through
    ARIA roles, a sorted column's header carries `aria-sort`, and every glyph state is a word in
    the row header's cell, read after the system's name; the more-numbers tables use `th` with
    `scope`. The References table's roles are an RFC-0009 §Site gap for #320."""
    index = site.pages["index.html"]
    for sec in SECTION.findall(index):
        heads = HEAD.findall(sec)
        assert len(heads) == 1 + len(COLS)
        assert sec.count('role="columnheader"') == len(heads)
        assert sec.count('aria-sort="') == 1
        for rid, _, _, row in ROW.findall(sec):
            assert row.count('role="rowheader"') == 1, rid
            assert row.count('role="cell"') == len(COLS), rid
            head = HEADER.search(row)[1]  # type: ignore[index]
            assert head.index('class="name"') < head.index('<p class="sr">'), rid
            assert re.search(r'<p class="sr">[^<]*: (Yes|Partly|No|Not stated)', head), rid
    for system in site.view["orders"]["benchmarked"]:
        table = site.pages[f"{system}.html"]
        table = table[table.index('<table class="mtab">') : table.index("</table>")]
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
    for cfg in provers(site.view):
        assert any(row_config(site.view, rid) is cfg for rid, *_ in rows)
    assert all(NUMBER.search(body) for *_, body in rows)  # figures are in the HTML as sent
    for ref in site.view["orders"]["not_benchmarked"]:
        assert site.view["facts"]["rows"][ref]["name"] in plain(index), ref


def test_pending_row_draws_no_state(site: Build) -> None:
    """RFC-0016 OVR-8: a row under a pending disclosure draws none of the four states."""
    pending = [rid for rid, row in site.view["criteria"]["rows"].items() if row.get("pending")]
    if site.kind == "web":
        assert not pending
        pytest.skip("no criteria row of the deployed build is under a pending disclosure")
    assert pending
    index = site.pages["index.html"]
    for rid in pending:
        row = index[index.index(f'<div class="row" id="{rid}"') :]
        row = row[: row.index('<div class="vals">')]
        assert len(re.findall(r'class="sl s\d none"', row)) == 6
        assert not re.search(r'class="sl s\d (yes|partly|no|unstated)"', row)


def test_reply_escaped() -> None:
    """§Right of reply: a reply is escaped; only http(s) links become links."""
    out = reply_html("We *disagree*: <script>x</script> [notes](https://example.org/n)\n\n"
                     "- one\n- [bad](javascript:alert(1))")  # fmt: skip
    assert isinstance(out, str)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert '<a href="https://example.org/n">notes</a>' in out
    assert "<em>disagree</em>" in out
    assert 'href="javascript' not in out
    assert "<ul><li>one</li>" in out


def test_generated_html_passes_g8(site: Build, tmp_path: Path) -> None:
    """S8: every page the build writes passes the RFC-0013 G8 word list (replies are excluded
    at source, RFC-0009 §Right of reply)."""
    from iproofs.validate.tree import g8_language  # noqa: PLC0415

    for name, text in site.pages.items():
        (tmp_path / name).write_text(text)
    assert g8_language(tmp_path, [], named=sorted(site.pages)) == []
