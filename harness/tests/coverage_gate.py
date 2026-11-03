"""Coverage gate (docs/spec/07 §Coverage), run after `pytest --cov --cov-branch`.

Usage: python harness/tests/coverage_gate.py coverage.json. Fails when a module group is under
its floor; writes the line coverage of the whole package, a target and not a gate, to the CI
job summary. The floors only rise.
"""

import json
import os
import sys
from pathlib import Path

# group -> (path prefix inside iproofs, floor in percent, statements and branches together)
FLOORS = {
    "iproofs.derive": ("derive.py", 100.0),
    "iproofs.controls": ("controls.py", 100.0),
    "iproofs.validate": ("validate/", 100.0),
}
LINE_TARGET = 90.0


def group_percent(files: dict[str, dict[str, dict[str, int]]], prefix: str) -> float:
    covered = total = 0
    for name, data in files.items():
        if name.split("iproofs/", 1)[-1].startswith(prefix):
            s = data["summary"]
            covered += s["covered_lines"] + s.get("covered_branches", 0)
            total += s["num_statements"] + s.get("num_branches", 0)
    return 100.0 * covered / total if total else 100.0


def main(path: str) -> int:
    report = json.loads(Path(path).read_text())
    files = report["files"]
    lines = report["totals"]["percent_covered_display"]
    out = [f"line and branch coverage of iproofs: {lines} % on this run (target {LINE_TARGET:g} %)"]
    failed = []
    for group, (prefix, floor) in FLOORS.items():
        pct = group_percent(files, prefix)
        out.append(f"{group}: {pct:.2f} % statements and branches (floor {floor:g} %)")
        if pct + 1e-9 < floor:
            failed.append(group)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a") as f:
            f.write("\n".join(out) + "\n")
    print("\n".join(out))
    for group in failed:
        print(f"coverage: {group} is under its floor", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
