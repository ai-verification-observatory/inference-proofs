"""Sort keys of the home figures against hand-computed cases from _data/site.json.

The site shows only the benchmark's own runs (MOCK until a release exists), so every key is a run value.
Run: python3 -m pytest test_sort_keys.py   (or: python3 test_sort_keys.py)
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build

ROWS = {r["system"]: r for r in build.PROVERS}
K = {sid: build.row_keys(r) for sid, r in ROWS.items()}


def close(a, b):
    return abs(a - b) <= 1e-9 * max(1.0, abs(b))


def test_proof_size_in_bytes():
    # printed "18.78 MB" and "19.80 GB": 18.78 x 10^6 B and 19.80 x 10^9 B, so MB sorts before GB
    assert abs(K["flashprove"]["proof_size"] - 18.78e6) <= 0.005e6
    assert close(K["sash"]["proof_size"], 19_800_000_000)
    assert K["flashprove"]["proof_size"] < K["sash"]["proof_size"]


def test_check_time_in_seconds():
    # 3.120 s against 121.3 s
    assert close(K["flashprove"]["check_time"], 3.12)
    assert abs(K["sash"]["check_time"] - 121.3) <= 0.05


def test_covers_in_positions():
    # positions one proof covers, by the workload record both systems run: a 1,024-token prompt
    w = build.site["workloads"]["fp-maverick-w1024-b24"]
    assert (
        K["flashprove"]["covers"]
        == K["sash"]["covers"]
        == w["one_proof_covers"]["tokens_counted"]
        == 1024
    )


def test_overhead_ratio_and_missing():
    # the reference could not run Llama 4 Maverick on one H100: no overhead for either system
    assert K["flashprove"]["overhead"] is None
    assert K["sash"]["overhead"] is None


def test_units_normalise():
    assert build.UNIT["GB"] / build.UNIT["MB"] == 1000
    assert build.UNIT["min"] == 60 * build.UNIT["s"]
    n, half = build.shown_number("19.83 GB")
    assert close(n, 19.83e9)
    assert close(half, 0.005e9)
    n, half = build.shown_number("1,583×")
    assert n == 1583
    assert half == 0.5
    assert build.shown_number("Not published") is None


def test_sort_words():
    w = build.sort_words()
    assert w["system"]["asc"] == "A to Z"
    assert w["proof_size"]["asc"] == "small to large"
    assert w["check_time"]["desc"] == "long to short"
    assert set(w) == {"system", *build.COLS}


def test_one_model():
    # only systems run on Llama 4 Maverick are shown; the references are those on it
    assert [build.MODEL_NAME[d] for d in build.MODELS] == [build.TARGET_MODEL]
    assert {r["workload"] for r in build.H5["rows"]} == {"fp-maverick-w1024-b24"}
    refs = sorted(r["id"].split("--")[0] for r in build.H5["rows"] if r["kind"] == "reference")
    assert refs == ["ref-recompute", "ref-serve"]


def test_sorted_orders():
    # hand-computed from the printed figures: 18.78 MB < 19.80 GB, 3.120 s < 121.3 s
    by = lambda col: sorted(K, key=lambda s: K[s][col])  # noqa: E731
    assert by("proof_size") == ["flashprove", "sash"]
    assert by("check_time") == ["flashprove", "sash"]


def test_home_figures_show_spread():
    # every figure whose data holds a SPREAD line shows its sample size and range first
    seen = 0
    for r in ROWS.values():
        for col in build.COLS:
            x = r["cells"][col][build.VIEW]
            sp = build.card_line(x, "SPREAD")
            if not sp or not x.get("value"):
                continue
            lines = build.fallback_lines(x)
            n, rng = sp["v"].split(" · ")[:2]
            assert lines[:2] == [n, rng], (r["id"], col, lines)
            seen += 1
    assert seen == 4


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
            print("ok", name)
