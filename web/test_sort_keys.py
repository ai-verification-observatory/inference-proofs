"""Sort keys and figures of the overview, against hand-computed cases from the synthetic
placeholder release (harness/tests/fixtures/placeholder_release.py): every key is the value the
fixture index stores. Run from the repository root: uv run pytest web -q
"""

import copy
import html
import json
import re

import pytest

from iproofs.quantity import Grade, NullReason, Scope, Tier
from iproofs.site import inputs

ROW = re.compile(r'<div class="row" id="([^"]+)" role="row" data-name="[^"]+" data-k="([^"]+)">')


@pytest.fixture(scope="module")
def keys(site):
    """{system: {column: key}} as the fixture build's overview prints them."""
    text = (site.out / "index.html").read_text()
    return {rid: json.loads(html.unescape(k)) for rid, k in ROW.findall(text)}


def close(a, b):
    return abs(a - b) <= 1e-9 * max(1.0, abs(b))


def test_keys_are_the_stored_values(site, keys):
    # S4: the key is the value the index stores, in its base unit, never a printed figure
    for cfg in site.view["configurations"]:
        if cfg["kind"] != "prover":
            continue
        for col in site.build.BOARD:
            metric = site.build.metric_of(cfg, col)  # the overhead: the row's headline
            assert keys[cfg["system"]][col] == cfg["figures"][metric]["value"], (cfg["system"], col)


def test_overhead_missing(site, keys):
    # the placeholder's production-serving runs are on a prover profile, so they pair with no row
    # (RFC-0015 SRV-10): no overhead for FlashProve; SASH's steady scope is not observable, so
    # its row shows the warm figure (RFC-0004 INV-DERIVE-11), null for want of a baseline
    assert keys["flashprove"]["overhead"] is None
    assert keys["sash"]["overhead"] is None
    provers = [c for c in site.view["configurations"] if c["kind"] == "prover"]
    figures = {c["system"]: c["figures"]["overhead_vs_production_prove.steady"] for c in provers}
    assert figures["flashprove"]["null_reason"] == "not_applicable"
    assert figures["sash"]["null_reason"] == "not_externally_observable"
    shown = {c["system"]: c["figures"][site.build.metric_of(c, "overhead")] for c in provers}
    assert shown["flashprove"]["metric"] == "overhead_vs_production_prove.steady"
    assert shown["sash"]["metric"] == "overhead_vs_production_warm"
    assert shown["sash"]["null_reason"] == "missing_input"


def test_warm_overhead_names_both_scopes(site):
    # RFC-0004 INV-DERIVE-11, RFC-0009 S2: SASH's headline is the warm figure; with a value (a
    # fixture value, not a result) its cell and its plate print both scopes, and without one the
    # plate still prints them, with why the steady figure is null
    b = site.build
    cfg = copy.deepcopy(next(c for c in b.PROVERS if c["system"] == "sash"))
    warm = cfg["figures"][b.metric_of(cfg, "overhead")]
    assert warm["metric"] == b.WARM
    assert b.readable(b.WARM_LINE) in b.plate(cfg, "overhead")
    assert "steady state" in b.plate(cfg, "overhead")
    warm["value"] = 1000.0
    assert b.cell_words(cfg, "overhead")[1] == [b.SCOPE_SHORT[b.WARM]]
    assert b.WARM_LINE in b.cell_words(cfg, "overhead")[2]
    plate = b.plate(cfg, "overhead")
    assert f"<dt>scope</dt><dd>{b.readable(b.WARM_LINE)}</dd>" in plate
    assert "start-up included on both sides" not in plate


def test_units_normalise(site):
    b = site.build
    assert b.amount(19.83e9, "B") == ("19.83", "GB")
    assert b.amount(5023.08, "B") == ("5.023", "kB")
    assert b.amount(2410.5333, "s") == ("40.18", "min")
    assert b.amount(64.3667, "s") == ("64.37", "s")
    assert b.amount(0.03, "s") == ("30.00", "ms")
    # the prefix that leaves no leading zero: 68.21 µs, 222.9 B, 56.49 GiB; 999.96 µs is 1.000 ms
    assert b.amount(6.821e-14, "s/bit_token") == ("68.21", "\N{MICRO SIGN}s")
    assert b.amount(2.229e-7, "B/bit_token") == ("222.9", "B")
    assert b.amount(57850, "MiB") == ("56.49", "GiB")
    assert b.amount(0.00099996, "s") == ("1.000", "ms")
    assert b.shown(1583, "ratio") == "1,583×"
    assert b.shown(1024.0, "token") == "1,024 positions"
    assert b.shown(0.0114974, "USD/1k_token") == "0.01150 USD / 1k positions"
    assert (b.sig4(3.12), b.sig4(121.2667), b.sig4(0.851061), b.sig4(0)) == (
        "3.120",
        "121.3",
        "0.8511",
        "0",
    )


def test_four_digits_at_any_size(site):
    # S4: four significant digits above 9,999 too, by hand: 122,880 tokens is 1.229e5
    b = site.build
    assert b.sig4(122880) == "122,900"
    assert b.sig4(12346.0) == "12,350"
    assert b.sig4(1024) == "1,024"
    assert b.shown(16384.0, "token") == "16,380 positions"
    assert b.shown(12346, "ratio") == "12,350×"


def test_sort_words(site):
    w = site.build.SORT_WORDS
    assert w["system"]["asc"] == "A to Z"
    assert {"system", *site.build.BOARD} <= set(w)


def test_reference_cells(site):
    # a reference makes no proof (RFC-0015 REF-2): covers follows the system, a proof's figures do
    # not apply, production serving is the overhead's baseline, the rerun's overhead does not apply
    got = {}
    for gid in site.view["orders"]["reference"]:
        cfg = site.build.first_config(gid)
        got[gid] = {
            c: re.sub(r"<[^>]+>", "", site.build.cell_words(cfg, c)[0]) for c in site.build.COLS
        }
    for gid in got:
        assert got[gid]["covers"] == "Same as the system"
        assert got[gid]["proof_size"] == "No proof"
        assert got[gid]["check_time"] == "Does not apply"
    assert got["ref-serve"]["overhead"] == "Baseline"
    assert got["ref-recompute"]["overhead"] == "Does not apply"


def test_reference_runs_all_failed(site):
    # every reference run failed with kind resource: the counts, below the minimum (S3, S7)
    for gid in site.view["orders"]["reference"]:
        line = site.build.runs_counts(site.build.first_config(gid))
        assert line == "0 completed, 3 failed · below minimum repetitions"


def test_readable_labels(site):
    nb = "\N{NO-BREAK SPACE}"  # a number keeps its word on its line
    assert site.build.readable("3 completed, 0 failed") == f"3{nb}completed, 0{nb}failed"
    assert site.build.readable("18.77 MB to 18.78 MB") == f"18.77{nb}MB to 18.78{nb}MB"
    assert site.build.no_rule("one H100 (RFC-0015 NM-1).") == "one H100."


def test_home_figures_show_spread(site):
    # every measured overview figure carries its sample size and range in its title (S3), with
    # its grade and evidence, and no record pointer (its plate holds it in view)
    seen = 0
    for cfg in site.build.PROVERS:
        for col in site.build.BOARD:
            f = cfg["figures"][site.build.metric_of(cfg, col)]
            if f["value"] is None or not f.get("stats"):
                continue
            title = site.build.cell_words(cfg, col)[2]
            st = f["stats"]
            assert f"{st['n']} completed, {st['n_failed']} failed, " in title, (cfg["system"], col)
            assert site.build.GRADE_WORD[f["grade"]] in title
            assert f"evidence: {site.build.TIER_WORD[f['tier']]}" in title
            assert "releases/" not in title
            assert site.build.PER_BIT_LIMIT not in title
            seen += 1
    assert seen


def test_titles_are_short(site):
    # an overview figure's title: value, scope, runs and range, grade and evidence; the
    # per-Gbit limit sits once, on the line the three heads share (RFC-0004 INV-DERIVE-7)
    for cfg in site.build.PROVERS:
        for col in site.build.BOARD:
            assert len(site.build.cell_words(cfg, col)[2]) < 360, (cfg["system"], col)
    text = (site.out / "index.html").read_text()
    assert text.count(html.escape(site.build.PER_BIT_LIMIT)) == 2  # the line's title, read aloud


def test_range_words(site):
    # a range names its unit once, twice only where the prefix changes inside it (by hand)
    b = site.build
    assert b.range_words(6.761e-14, 6.891e-14, "s/bit_token") == "67.61 to 68.91 \N{MICRO SIGN}s"
    assert b.range_words(0.0009999, 0.001001, "s") == "999.9 \N{MICRO SIGN}s to 1.001 ms"
    assert b.range_words(61.0, 61.51, "ratio") == "61.00× to 61.51×"


def test_every_stored_id_has_words(site):
    # a stored id with no words would stop the build; each vocabulary is covered in full
    b = site.build
    assert set(inputs.STATES) <= set(b.STATE_WORD)
    assert set(inputs.STATES) <= set(b.STATE_CLS)
    assert set(inputs.FAMILIES) == set(b.FAMILY_WORD)
    assert {s.value for s in Scope} | {None} == set(b.SCOPE_WORD)
    assert {g.value for g in Grade} == set(b.GRADE_WORD)
    assert {t.value for t in Tier} == set(b.TIER_WORD)
    assert {n.value for n in NullReason} == set(b.NULL_WORD)
