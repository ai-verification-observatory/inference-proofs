"""End to end from the placeholder release to the pages (#320): synthetic runs, `iproofs derive
--check` on every run, `iproofs release freeze`, `iproofs site build`, through the CLI.

The checks read the pages and the frozen `index.json` only, never the site view, so each figure
is traced from the HTML to the stored field it came from (AGENTS.md rule 3: derived numbers are
computed, not typed). CPU only, no network. Every number here is a placeholder fixture value.
"""

import contextlib
import html
import json
import math
import re
from pathlib import Path
from typing import Any

import pytest

from fixtures.builds import SiteBuild
from fixtures.placeholder_release import RELEASE
from iproofs import cli
from iproofs.derive import FORMULAS

INDEX = f"releases/{RELEASE}/index.json"
POINTER = re.compile(rf"{re.escape(INDEX)}#(/[^\s<\"]+)")
VAL = re.compile(r'<a class="val" href="[^"]*" title="([^"]*)">(.*?)</a>', re.S)
ROW = re.compile(r'<div class="row" id="([^"]+)" role="row" data-name="[^"]+" data-k="([^"]+)">')
PLATE = re.compile(r'<div class="plate" id="[^"]+" data-col="[^"]+">(.*?)</dl></div>', re.S)
NUMBER = re.compile(r'<span class="n">([^<]+)</span><span class="u">([^<]+)</span>')
SCALE = {"positions": 1.0, "B": 1.0, "kB": 1e3, "MB": 1e6, "GB": 1e9, "TB": 1e12, "ms": 1e-3,
         "s": 1.0, "min": 60.0, "h": 3600.0, "\N{MULTIPLICATION SIGN}": 1.0,
         # more numbers: token/s, and USD per 1,000 tokens (the row names the basis)
         "positions/s": 1.0, "USD": 1.0}  # fmt: skip
MORE_ROW = re.compile(r'<tr><th scope="row">.*?</tr>', re.S)
COLUMN = {
    "covers": "tokens_covered_per_proof",
    "proof_size": "proof_bytes",
    "check_time": "verify_seconds",
    "overhead": "overhead_vs_production_prove.steady",
    "per_bit": "seconds_per_active_weight_bit_token_prove.steady",
    "size_bit": "proof_bytes_per_active_weight_bit_token",
    "check_bit": "verify_seconds_per_active_weight_bit_token",
}


def column(statistics: dict[str, Any], headline: dict[str, Any] | None, col: str) -> str:
    """The statistic an overview column shows: the overhead the index names as the headline,
    prover time per active weight bit at `prove.steady`, else at `prove.session`."""
    if col == "overhead" and headline:
        return str(headline["metric"])
    if col == "per_bit" and (statistics.get(COLUMN[col]) or {}).get("value") is None:
        return "seconds_per_active_weight_bit_token_prove.session"
    return COLUMN[col]


@pytest.fixture(scope="module")
def built(placeholder_build: SiteBuild) -> tuple[Path, Path]:
    """(tree, out): the placeholder tree, its runs checked and frozen, and the site built. The
    tree, its freeze and the site are the shared deployed build (fixtures/builds), which runs
    `iproofs release freeze` and `iproofs site build` through the CLI and fails on a non-zero
    exit; `iproofs derive --check` never writes, so it runs on that tree here."""
    tree, out = placeholder_build.repo, placeholder_build.out
    runs = sorted(p.parent for p in tree.glob("results/*/*/*/run.json"))
    assert len(runs) >= 12  # 3 + 5 prover runs, 3 + 3 reference runs
    with contextlib.chdir(tree):
        for run in runs:
            assert cli.main(["derive", "--check", str(run)]) == 0, run.name
    assert (tree / INDEX).is_file()  # frozen
    assert (out / "index.html").is_file()  # built
    return tree, out


def index(tree: Path) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads((tree / INDEX).read_text())
    return doc


def resolve(doc: Any, pointer: str) -> Any:
    """RFC 6901 JSON Pointer."""
    for raw in pointer.lstrip("/").split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        doc = doc[int(part)] if isinstance(doc, list) else doc[part]
    return doc


def pages(out: Path) -> dict[str, str]:
    return {p.name: p.read_text("utf-8") for p in sorted(out.glob("*.html"))}


def printed(number: str, unit: str, stored_unit: str = "") -> float:
    """A printed figure in its stored base unit; a per-bit unit (s/bit_token, B/bit_token) is
    printed per Gbit of active weights, 1e9 bits."""
    per_gbit = 1e-9 if stored_unit.endswith("/bit_token") else 1.0
    return float(number.replace(",", "")) * SCALE[unit] * per_gbit


def close_at_4(value: float, stored: float) -> bool:
    """The printed value is the stored one at 4 significant digits."""
    exponent = math.floor(math.log10(abs(stored)))
    return abs(value - stored) <= 0.5 * 10.0 ** (exponent - 3) * 1.0001


def test_every_configuration_on_the_pages(built: tuple[Path, Path]) -> None:
    tree, out = built
    site = pages(out)
    doc = index(tree)
    systems = {c["system"] for c in doc["configurations"]}
    assert systems == {"flashprove", "sash", "ref-serve", "ref-recompute"}
    rows = {rid for rid, _ in ROW.findall(site["index.html"])}
    for c in doc["configurations"]:
        if c["system"].startswith("ref-"):  # the baseline, on /reference, not an overview row
            assert f'<div class="row" id="{c["system"]}"' not in site["index.html"]
            assert f'id="{c["system"]}" aria-labelledby' in site["reference.html"]
        else:
            assert c["system"] in rows
            assert f"{c['system']}.html" in site


def _not_recorded(text: str, number: re.Match[str] | None, name: str) -> None:
    """A metric the runs did not record: no value, no record, and the words saying so."""
    assert number is None, (name, text)
    assert "Not recorded in these runs." in text, (name, text)


def test_every_figure_traces_to_the_index(built: tuple[Path, Path]) -> None:
    """Each overview figure and each plate names a statistic of the frozen index by its pointer,
    and prints that statistic's value at 4 significant digits; each overview sort key is that
    value as stored."""
    tree, out = built
    doc, site = index(tree), pages(out)
    traced = 0
    for title, inner in VAL.findall(site["index.html"]):
        found = POINTER.search(html.unescape(title))
        if not found:
            continue
        stat = resolve(doc, found[1])
        number = NUMBER.search(inner)
        assert number, title
        assert close_at_4(printed(number[1], number[2], stat["unit"]), stat["value"]), title
        traced += 1
    for name in ("flashprove.html", "sash.html"):
        for body in PLATE.findall(site[name]):
            source = re.sub(r"<[^>]+>", "", body)
            found = POINTER.search(source)
            number = NUMBER.search(body)
            if found is None:
                _not_recorded(source, number, name)
                continue
            stat = resolve(doc, found[1])
            if stat["value"] is None:
                assert number is None
                assert stat["null_reason"], found[1]
                continue
            assert number, (name, found[1])
            value = printed(number[1], number[2], stat["unit"])
            assert close_at_4(value, stat["value"]), (name, found[1])
            traced += 1
    assert traced >= 12  # two systems, three measured figures, on the overview and the plates
    more = 0
    for name in ("flashprove.html", "sash.html"):
        for row in MORE_ROW.findall(site[name]):
            found = POINTER.search(re.sub(r"<[^>]+>", "", row))
            number = NUMBER.search(row)
            if found is None:  # a metric the runs did not record: no value and no record
                assert number is None, (name, row)
                assert "Not recorded in these runs." in row
                continue
            stat = resolve(doc, found[1])
            if stat["value"] is None:
                assert number is None, (name, found[1])
                continue
            assert number, (name, found[1])
            value = printed(number[1], number[2])
            assert close_at_4(value, stat["value"]), (name, found[1])
            stats = stat["stats"]
            spread = f"{stats['n']} completed, {stats['n_failed']} failed"
            assert spread in re.sub(r"<[^>]+>", "", row).replace("\N{NO-BREAK SPACE}", " ")
            more += 1
    assert more >= 6  # two systems: proving rate, GPU cost, commit once
    _keys_are_stored(doc, site["index.html"])


def _keys_are_stored(doc: dict[str, Any], index_html: str) -> None:
    """Each overview sort key is the value the index stores for that row's column."""
    for rid, keys in ROW.findall(index_html):
        position = next(i for i, c in enumerate(doc["configurations"]) if c["system"] == rid)
        statistics = doc["configurations"][position]["statistics"]
        headline = doc["configurations"][position].get("overhead_headline")
        for col, key in json.loads(html.unescape(keys)).items():
            stored = statistics.get(column(statistics, headline, col), {}).get("value")
            assert key == stored, (rid, col)


def test_every_formula_is_in_derive(built: tuple[Path, Path]) -> None:
    """Every statistic a page points at is D-STAT over repetition values, each of them the
    output of a formula `iproofs.derive` holds (or a recorded metric); every formula id a page
    names is one `iproofs.derive` holds (#320: no site-only formula ids)."""
    tree, out = built
    doc = index(tree)
    text = "".join(pages(out).values())
    named = set(re.findall(r"\bD-[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*\b", re.sub(r"<[^>]+>", " ", text)))
    assert named <= set(FORMULAS), named - set(FORMULAS)
    pointers = set(POINTER.findall(html.unescape(text)))
    assert pointers
    for pointer in pointers:
        stat = resolve(doc, pointer)
        ref = stat["source"]["ref"]
        formula = ref.removeprefix("derive:").split("@")[0]
        assert formula in FORMULAS, (pointer, ref)
        for source in stat["source"]["inputs"]:
            path, _, inner = source.partition("#")
            metric = resolve(json.loads((tree / path).read_text()), inner)
            kind = metric["source"]["kind"]
            if kind == "derivation":
                assert metric["source"]["ref"].removeprefix("derive:").split("@")[0] in FORMULAS
            else:
                assert kind in {"measurement", "adapter", "harness", "workload"}, (source, kind)
