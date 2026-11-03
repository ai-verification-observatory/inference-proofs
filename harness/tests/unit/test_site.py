"""RFC-0009 §Site rules S1, S2, S4, S7 and no required scripts, on the fixture release."""

import re

import pytest

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
