"""RFC-0009 §Site rules S1, S2, S4 to S8 and no required scripts, on the fixture release."""

import json
import re
from pathlib import Path

import pytest
from markupsafe import escape

from fixtures.release_tree import build_rich
from iproofs import cli
from iproofs.site import number, reply_html

CELL = re.compile(r'<td class="q">(.*?)</td>', re.S)


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    root = tmp_path_factory.mktemp("repo")
    build_rich(root)
    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(root)
        assert cli.main(["release", "freeze", "v0.1"]) == 0
        assert cli.main(["site", "build", "--out", str(root / "out")]) == 0
    out = root / "out"
    return {p.relative_to(out).as_posix(): p.read_text() for p in out.rglob("*.html")}


def test_every_number_has_labels(site: dict[str, str]) -> None:
    """S2: each value cell names unit, grade and tier and links its JSON Pointer; no value
    is shown outside such a cell."""
    cells = 0
    for rel, text in site.items():
        found = CELL.findall(text)
        for cell in found:
            for label in ('class="label unit"', 'class="label grade"', 'class="label tier"',
                          'class="src" href="'):  # fmt: skip
                assert label in cell, (rel, cell)
        assert text.count('class="num"') == sum(c.count('class="num"') for c in found), rel
        cells += len(found)
    assert cells > 0


def test_claim_card_before_numbers(site: dict[str, str]) -> None:
    """S1: on every system page the claim card comes before the first number."""
    systems = [rel for rel in site if "/systems/" in rel]
    assert sorted(systems) == ["v0.1/systems/fake-broken.html", "v0.1/systems/fake.html",
                               "v0.1/systems/ref-serve.html"]  # fmt: skip
    for rel in systems:
        text = site[rel]
        assert text.index('id="claim-card"') < text.index('class="num"'), rel


def test_no_script_tags_required(site: dict[str, str]) -> None:
    assert not [rel for rel, text in site.items() if "<script" in text.lower()]


def test_superseded_and_ineligible_struck_through(site: dict[str, str]) -> None:
    """S7, with the reasons."""
    text = site["v0.1/systems/fake.html"]
    assert "<del>2026-11-07-fake-fake-tiny-ci-ci-cpu-5</del>: superseded: wrong CPU binding" in text
    assert "<del>2026-11-06-fake-fake-tiny-ci-ci-cpu-4</del>: harness_dirty" in text


def test_display_rounding() -> None:
    """S4: four significant digits for display only."""
    assert (number(1.5), number(36.0), number(0.123456), number(12346.0)) == (
        "1.500", "36.00", "0.1235", "1.235e+04")  # fmt: skip
    assert (number(None), number(3)) == ("null", "3")


def test_reply_escaped() -> None:
    out = str(reply_html("We *disagree*: <script>x</script> [notes](https://example.org/n)\n\n"
                         "- one\n- [bad](javascript:alert(1))"))  # fmt: skip
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert '<a href="https://example.org/n">notes</a>' in out
    assert "<em>disagree</em>" in out
    assert 'href="javascript' not in out  # only http(s) links become links
    assert "<ul><li>one</li>" in out


ROW_SYSTEM = re.compile(r'<th scope="row"><a href="\.\./systems/([^"]+)\.html">')
HEADERS = re.compile(r'<th scope="col">(?:<a [^>]*>)?([^<]+)')


def test_default_order_alphabetical(site: dict[str, str]) -> None:
    """S5: the default division table is alphabetical; other orders only behind links."""
    default = ROW_SYSTEM.findall(site["v0.1/divisions/open.html"])
    assert default == sorted(default) == ["fake", "fake-broken"]
    assert 'href="open-by-prove_session_seconds.html"' in site["v0.1/divisions/open.html"]
    assert "v0.1/divisions/open-by-prove_session_seconds.html" in site
    assert "Native workloads differ" not in site["v0.1/divisions/open.html"]  # S6: native only


def test_no_aggregate_score_column(site: dict[str, str]) -> None:
    for rel in (r for r in site if "/divisions/" in r):
        headers = HEADERS.findall(site[rel])
        assert headers[:4] == ["System", "Claim card summary", "Workload", "Profile"], rel
        assert not [h for h in headers if re.search(r"score|rank|total|overall|best", h, re.I)]
        assert "<strong>" not in site[rel].split("<table>")[1]  # no highlighted cell


def test_generated_html_passes_g8(site: dict[str, str], tmp_path: Path) -> None:
    """S8: the site text passes the RFC-0013 G8 word list (replies are excluded at source)."""
    from iproofs.validate.tree import g8_language  # noqa: PLC0415

    for rel, text in site.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    assert g8_language(tmp_path, [], named=sorted(site)) == []


def test_unexpected_control_printed_in_full(tmp_path: Path) -> None:
    build_rich(tmp_path)
    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(tmp_path)
        assert cli.main(["release", "freeze", "v0.1"]) == 0
        index_path = tmp_path / "releases/v0.1/index.json"
        index = json.loads(index_path.read_text())
        stored = next((tmp_path / "results/v0.1/fake").glob("*/controls.json"))
        record = json.loads(stored.read_text())["controls"][0]
        index["controls"][0]["outside_expected"] = [
            {"run_id": stored.parent.name, "control_id": record["id"], "outcome": "accepted"}
        ]
        index_path.write_text(json.dumps(index))
        assert cli.main(["site", "build", "--out", str(tmp_path / "out")]) == 0
    page = (tmp_path / "out/v0.1/controls.html").read_text()
    assert f"{record['id']} in run {stored.parent.name}: accepted." in page
    assert str(escape(json.dumps(record, indent=2, sort_keys=True))) in page
