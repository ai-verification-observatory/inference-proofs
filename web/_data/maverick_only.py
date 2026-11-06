"""Place every benchmarked system on Llama 4 Maverick, the one model the site compares on.

Run once from web/: python3 -I _data/maverick_only.py   (it does nothing on data it already changed)

The site shows only systems run on Llama 4 Maverick (400B parameters). SASH's pinned code runs
Llama 3.1 8B only (RFC-0003), so its rows on that model are PLACEHOLDERS moved onto FlashProve's
workload for layout, like every other benchmark result in this snapshot. This script edits only
what build.py reads, and every new value is taken from the data, never typed:

- SASH's home row moves to FlashProve's workload and model. What one proof covers is the
  workload's own figure, copied from FlashProve's cell on it. Overhead is that workload's: the
  reference could not run the model on one H100, so it is FlashProve's "No value" cell. Proof
  size, check time and the more-numbers keep SASH's placeholder values; their labels name the
  new workload and configuration, and the per-unit lines under them ("1 proof") are the workload's.
- The axis charts the sort keys come from follow: the same values for the moved row, under its
  new id, with covers and overhead taken from FlashProve's row on the workload.
- SASH's model fact, workload line and tamper configuration follow.
- The reference rows on Llama 3.1 8B go, since no system is shown on that model. Plain serving's
  overhead, 1x by definition whether or not it has run, was stated only on its 8B row; that cell
  moves onto its Llama 4 Maverick row first.

The rest of site.json (configurations, the overview's precomputed orders and the published
views) still describes the earlier snapshot; build.py does not read it.
"""

import copy
import json
import pathlib

DATA = pathlib.Path(__file__).resolve().parent / "site.json"
site = json.loads(DATA.read_text())

OLD_WL, NEW_WL = "sash-l31-8b-c4096", "fp-maverick-w1024-b24"
OLD_ID = f"sash--{OLD_WL}--prover-h100"
NEW_ID = f"sash--{NEW_WL}--prover-h100"
FP_ID = f"flashprove--{NEW_WL}--prover-h100"
COLS = ("covers", "proof_size", "check_time", "overhead")
SORT_CHARTS = {  # build.py SORT_AXIS: the chart each home column sorts on
    "covers": ("one-proof-covers", "positions"),
    "proof_size": ("proof-size", "per-proof"),
    "check_time": ("check-time", "per-proof"),
    "overhead": ("overhead", "ratio"),
}
FROM_FLASHPROVE = ("covers", "overhead")  # properties of the workload, not of the system


def renamed(obj):
    """A deep copy with the old configuration and workload ids replaced by the new ones."""
    text = json.dumps(obj, ensure_ascii=False)
    return json.loads(text.replace(OLD_ID, NEW_ID).replace(OLD_WL, NEW_WL))


def move_sash(rows, fp):
    """SASH's row onto FlashProve's workload; covers, overhead and per-unit lines are the workload's."""
    i = next(n for n, r in enumerate(rows) if r["id"] == OLD_ID)
    sash = renamed(rows[i])
    sash["workload"], sash["model"] = NEW_WL, fp["model"]
    for col in FROM_FLASHPROVE:
        text = json.dumps(copy.deepcopy(fp["cells"][col]), ensure_ascii=False)
        sash["cells"][col] = json.loads(text.replace("FLASHPROVE", "SASH").replace(FP_ID, NEW_ID))
    # the lines under proof size and check time count per unit of the workload ("1 proof", "1 check")
    for col in ("proof_size", "check_time"):
        for view, cell in sash["cells"][col].items():
            if fp["cells"][col].get(view, {}).get("lines"):
                cell["lines"] = list(fp["cells"][col][view]["lines"])
    rows[i] = sash


def keep_serving_baseline(rows):
    """Plain serving's overhead is 1x by definition, run or not; only its Llama 3.1 8B row says so,
    so that definitional cell moves onto its Llama 4 Maverick row before the 8B rows go."""
    old = next(r for r in rows if r["id"] == f"ref-serve--{OLD_WL}--prover-h100")
    new = next(r for r in rows if r["id"] == f"ref-serve--{NEW_WL}--prover-h100")
    for view, cell in old["cells"]["overhead"].items():
        if cell.get("value"):
            new["cells"]["overhead"][view] = renamed(cell)


def move_chart_rows():
    """The axis charts the sort keys come from: the moved row under its new id, covers and overhead
    from FlashProve's row on the workload; the 8B reference rows go."""
    for col, (axis, chart_id) in SORT_CHARTS.items():
        chart = next(c for c in site["axes"][axis]["charts"] if c["id"] == chart_id)
        for view in chart["views"].values():
            fp_row = next((r for r in view["rows"] if r["row"] == FP_ID), None)
            for r in view["rows"]:
                if r["row"] == OLD_ID:
                    r["row"] = NEW_ID
                    if col in FROM_FLASHPROVE and fp_row is not None:
                        r["value"] = fp_row.get("value")
            view["rows"] = [
                r for r in view["rows"] if not (r["row"].startswith("ref-") and OLD_WL in r["row"])
            ]


def move_system_facts():
    """SASH's model fact, workload line and tamper configuration follow the move."""
    s, f = site["systems"]["sash"], site["systems"]["flashprove"]
    s["home_line"] = f["home_line"]
    s["tamper"]["config_id"] = NEW_ID
    card = {
        r["system"]: r["cells"]["system"]["published"]["card"]
        for r in site["overview"]["rows"]
        if r["kind"] == "prover"
    }
    model = next(ln["v"] for ln in card["flashprove"]["lines"] if ln["k"] == "MODEL")
    for ln in card["sash"]["lines"]:
        if ln["k"] == "MODEL":
            ln["v"] = model


def main():
    rows = site["home5"]["rows"]
    if any(r["id"] == NEW_ID for r in rows):
        print("already on Llama 4 Maverick: nothing to do")
        return
    move_sash(rows, next(r for r in rows if r["id"] == FP_ID))
    keep_serving_baseline(rows)
    site["home5"]["rows"] = [
        r for r in rows if not (r["kind"] == "reference" and r["workload"] == OLD_WL)
    ]
    move_chart_rows()
    move_system_facts()
    # canonical JSON (iproofs fmt): sorted keys, two-space indent, a final newline
    DATA.write_text(json.dumps(site, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"moved {OLD_ID} to {NEW_ID}; removed the reference rows on {OLD_WL}")


if __name__ == "__main__":
    main()
