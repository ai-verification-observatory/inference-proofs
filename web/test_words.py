"""The words the system pages print from a card or a quote, against hand-computed cases: every
word kept, only marks rendered. Run from the repository root: uv run pytest web -q
"""

import html
import re

import pytest


def test_pairs_name_their_runs_and_why_others_join_none(site):
    """An overhead plate's pairs: each side's joined runs by date and ordinal, linked; each
    side's count carries in its title the runs left out and why (by hand)."""
    b = site.build
    rid = "2026-11-0{}-flashprove-fp-maverick-w1024-b24-prover-h200-hosted-{}"
    sid = "2026-11-09-ref-serve-fp-maverick-w1024-b24-serving-h200x4-hosted-{}"
    joined = {
        "system": [{"run_id": rid.format(9, 1), "record": "r/p1/run.json"}],
        "serving": [{"run_id": sid.format(n), "record": f"r/s{n}/run.json"} for n in (3, 4)],
        "left": [{"run_id": rid.format(8, n), "side": "system", "why": "first_proof_boundary"}
                 for n in (1, 2)] + [{"run_id": sid.format(1), "side": "serving",
                                      "why": "short_steady"}],
    }  # fmt: skip
    metric = "overhead_vs_production_prove.steady"
    cfg = {"overhead_runs": {metric: joined},
           "steady_boundary": "first-proof boundary (before 2026-11-09)"}  # fmt: skip
    f = {"metric": metric, "pairs": {"n_system": 1, "n_serving": 2, "min": 61.0, "max": 61.51}}
    said = b.pairs_html(cfg, f)
    text = re.sub(r'<span class="sr">.*?</span>|<[^>]+>', "", said).replace(
        "\N{NO-BREAK SPACE}", " "
    )
    assert text == ("1 prover run (2026-11-09 · 1 ↗) × 2 serving runs (2026-11-09 · 3 ↗, "
                    "2026-11-09 · 4 ↗), 61.00× to 61.51×")  # fmt: skip
    titles = re.findall(r'<span class="nw" title="([^"]+)">', said)
    assert titles == [
        "Left out: 2026-11-08 · 1, 2026-11-08 · 2: steady window from the first proof (runs "
        "before 2026-11-09), so they join no overhead",
        "Left out: 2026-11-09 · 1: steady scope under 60 s, so it joins no overhead",
    ]
    f["pairs"]["n_serving"] = 3  # a count its inputs do not hold stops the build
    with pytest.raises(RuntimeError):
        b.pairs_html(cfg, f)


def test_serving_runs_name_what_their_statistics_leave_out(site):
    """A production-serving row names the runs its statistics read: "4 runs", or, where they
    leave a completed run out, "4 of 5 runs" with each such run and why in its title, read from
    its own records (by hand, after releases/v0.1 configurations[4])."""
    b = site.build
    rid = "2026-11-09-ref-serve-sash-l31-8b-c1024-serving-h200x1-hosted-{}"
    runs = [rid.format(n) for n in range(1, 6)]
    figs = {m: {"stats": {"n": 4}, "runs": runs[1:]} for m, _, _ in b.SERVING_COLS}
    cfg = {"figures": figs, "runs": {"completed": runs},
           "run_why": {runs[0]: "one_batch", runs[1]: "short_steady"}}  # fmt: skip
    said = b.serving_runs(cfg)
    assert re.sub(r"<[^>]+>", "", said) == "4 of 5 runs"
    assert html.unescape(re.search(r'title="([^"]+)"', said)[1]) == (
        "Left out: 2026-11-09 · 1: no steady window (one batch)"
    )
    cfg["runs"]["completed"] = runs[1:]
    assert b.serving_runs(cfg) == "4 runs"
