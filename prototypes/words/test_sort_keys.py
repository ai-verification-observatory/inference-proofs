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
    # positions one proof covers, by the workload records: 1,024 prompt; 4,096 prompt and 512 output
    w = build.site["workloads"]
    assert (
        K["flashprove"]["covers"]
        == w["fp-maverick-w1024-b24"]["one_proof_covers"]["tokens_counted"]
    )
    assert (
        K["sash"]["covers"]
        == w["sash-l31-8b-c4096"]["one_proof_covers"]["tokens_counted"]
        == 4096 + 512
    )


def test_overhead_ratio_and_missing():
    assert K["flashprove"]["overhead"] is None  # "No value"
    assert round(K["sash"]["overhead"]) == 1583


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


def test_orders_agree_with_the_data():
    # the data's own sorted orders (overview.sort_pages, run view), prover rows only, give the same order
    ids = {r["id"]: sid for sid, r in ROWS.items()}
    seen = 0
    for sp in build.OV["sort_pages"]:
        col = next((c for c, w in build.SORT_WORDS.items() if w == sp["key"]), None)
        if col is None or sp["view"] != build.VIEW:
            continue
        want = [ids[i] for i in sp["order"] if i in ids]
        have = [k for k in K if K[k][col] is not None]
        have.sort(key=lambda s: K[s][col], reverse=sp["dir"] == "desc")
        have += sorted(k for k in K if K[k][col] is None)
        assert have == want, (col, sp["dir"], have, want)
        seen += 1
    assert seen


def test_sort_words():
    w = build.sort_words()
    assert w["system"]["asc"] == "A to Z"
    assert w["proof_size"]["asc"] == "small to large"
    assert w["check_time"]["desc"] == "long to short"
    assert set(w) == {"system", *build.COLS}


def test_models_biggest_first():
    # each system on the biggest model it runs, by total parameters; the models in that order
    assert [build.MODEL_NAME[d] for d in build.MODELS] == ["Llama 4 Maverick", "Llama 3.1 8B"]
    w = build.site["workloads"]
    assert (
        w["fp-maverick-w1024-b24"]["model"]["parameters_total"]
        > w["sash-l31-8b-c4096"]["model"]["parameters_total"]
    )
    assert build.biggest_workload("sash").startswith("sash-l31-8b")
    refs = [r for r in build.H5["rows"] if r["kind"] == "reference"]
    for d in build.MODELS:
        assert sorted(r["id"].split("--")[0] for r in refs if build.model_of(r) == d) == [
            "ref-recompute",
            "ref-serve",
        ]


def test_reference_covers_names_the_system():
    # a reference stores "same as above"; shown away from that row, it prints the system's figure, named
    r = next(x for x in build.H5["rows"] if x["id"].startswith("ref-serve--sash"))
    x = build.cell(r, "covers")
    assert x["value"] == ROWS["sash"]["cells"]["covers"][build.VIEW]["value"]
    assert "as SASH" in x["title"]


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
