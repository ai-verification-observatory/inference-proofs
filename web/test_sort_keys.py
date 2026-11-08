"""Sort keys and figures of the overview, against hand-computed cases from the placeholder release.

Until v0.1 the runs are placeholders (harness/tests/fixtures/placeholder_release.py): every key is
the value the placeholder index stores. Run from the repository root: uv run pytest web -q
"""

import html
import json
import re

import pytest

from iproofs.quantity import Grade, NullReason, Scope, Tier
from iproofs.site import inputs

ROW = re.compile(r'<div class="row" id="([^"]+)" role="row" data-name="[^"]+" data-k="([^"]+)">')


@pytest.fixture(scope="module")
def keys(site):
    """{system: {column: key}} as the committed overview prints them."""
    text = (site.web / "index.html").read_text()
    return {rid: json.loads(html.unescape(k)) for rid, k in ROW.findall(text)}


def close(a, b):
    return abs(a - b) <= 1e-9 * max(1.0, abs(b))


def test_keys_are_the_stored_values(site, keys):
    # S4: the key is the value the index stores, in its base unit, never a printed figure
    for cfg in site.view["configurations"]:
        if cfg["kind"] != "prover":
            continue
        for col, metric in site.build.METRIC.items():
            assert keys[cfg["system"]][col] == cfg["figures"][metric]["value"], (cfg["system"], col)


def test_proof_size_in_bytes(keys):
    # printed "18.78 MB" and "19.80 GB": 18.78 x 10^6 B and 19.80 x 10^9 B, so MB sorts before GB
    assert abs(keys["flashprove"]["proof_size"] - 18.78e6) <= 0.005e6
    assert close(keys["sash"]["proof_size"], 19_800_000_000)
    assert keys["flashprove"]["proof_size"] < keys["sash"]["proof_size"]


def test_check_time_in_seconds(keys):
    # 3.120 s against 121.3 s
    assert close(keys["flashprove"]["check_time"], 3.12)
    assert abs(keys["sash"]["check_time"] - 121.3) <= 0.05


def test_covers_in_positions(site, keys):
    # D-TPP, positions one proof covers: FlashProve proves the 1,024-token window of its
    # workload; SASH's prompt_plus_output rule counts its own workload's 1,024 prompt plus 64
    # output tokens, 1,088 by hand
    shapes = {c["system"]: c["workload"]["shape"] for c in site.view["configurations"]}
    assert keys["flashprove"]["covers"] == shapes["flashprove"]["context_window"] == 1024
    sash = shapes["sash"]
    assert keys["sash"]["covers"] == sash["prompt_tokens"] + sash["output_tokens"] == 1088


def test_overhead_missing(site, keys):
    # plain serving could not run Llama 4 Maverick on one H100 (RFC-0015 NM-1): no overhead for
    # FlashProve; the placeholder holds no reference run on SASH's workload: not recorded
    assert keys["flashprove"]["overhead"] is None
    assert keys["sash"]["overhead"] is None
    figures = {
        c["system"]: c["figures"]["overhead_vs_serving_prove.session"]
        for c in site.view["configurations"]
        if c["kind"] == "prover"
    }
    assert figures["flashprove"]["null_reason"] == "not_measurable_on_profile"
    assert figures["sash"]["recorded"] is False


def test_units_normalise(site):
    b = site.build
    assert b.amount(19.83e9, "B") == ("19.83", "GB")
    assert b.amount(5023.08, "B") == ("5.023", "kB")
    assert b.amount(2410.5333, "s") == ("40.18", "min")
    assert b.amount(64.3667, "s") == ("64.37", "s")
    assert b.amount(0.03, "s") == ("30.00", "ms")
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
    assert w["proof_size"]["asc"] == "small to large"
    assert w["check_time"]["desc"] == "long to short"
    assert set(w) == {"system", *site.build.COLS}


def test_two_models(site):
    # one table per model, largest first: Llama 4 Maverick (FlashProve), then Llama 3.1 8B
    # (SASH); the two references
    tables = site.build.tables()
    assert [(site.build.MODEL_NAME[d], [c["system"] for c in rows]) for d, _, rows in tables] == [
        ("Llama 4 Maverick", ["flashprove"]),
        ("Llama 3.1 8B", ["sash"]),
    ]
    assert site.view["orders"]["reference"] == ["ref-serve", "ref-recompute"]


def test_reference_cells(site):
    # a reference makes no proof (RFC-0015 REF-2): covers follows the system, a proof's figures do
    # not apply, plain serving is the baseline of the overhead, the rerun's overhead does not apply
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
    # every reference run failed with kind resource: counts, below the minimum, NM-1 (S3, S7)
    for gid in site.view["orders"]["reference"]:
        line = site.build.runs_counts(site.build.first_config(gid))
        assert (
            line
            == "0 completed, 3 failed · below minimum repetitions · not measurable on one H100 (RFC-0015 NM-1)"
        )


def test_readable_labels(site):
    nb = "\N{NO-BREAK SPACE}"  # a number keeps its word on its line
    assert site.build.readable("3 completed, 0 failed") == f"3{nb}completed, 0{nb}failed"
    assert site.build.readable("18.77 MB to 18.78 MB") == f"18.77{nb}MB to 18.78{nb}MB"
    assert site.build.no_rule("one H100 (RFC-0015 NM-1).") == "one H100."


def test_home_figures_show_spread(site):
    # every measured figure shows its sample size and range first (S3), One proof covers included
    seen = 0
    for cfg in site.build.PROVERS:
        for col in site.build.COLS:
            f = cfg["figures"][site.build.METRIC[col]]
            if f["value"] is None:
                continue
            lines = site.build.cell_words(cfg, col)[1]
            st = f["stats"]
            assert lines[0] == f"{st['n']} completed, {st['n_failed']} failed", (cfg["system"], col)
            assert " to " in lines[1]
            seen += 1
    assert seen == 6


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
