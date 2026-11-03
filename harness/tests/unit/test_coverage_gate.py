"""The coverage gate fails when a module held to full branch coverage drops below it."""

import json
import subprocess
import sys
from pathlib import Path

GATE = Path(__file__).resolve().parents[1] / "coverage_gate.py"


def report(tmp_path: Path, derive_branches_covered: int) -> Path:
    def entry(lines: int, branches: int, covered_branches: int) -> dict[str, object]:
        summary = {"covered_lines": lines, "num_statements": lines}
        return {"summary": {**summary, "covered_branches": covered_branches,
                            "num_branches": branches}}  # fmt: skip

    doc = {
        "totals": {"percent_covered_display": "95"},
        "files": {
            "harness/src/iproofs/derive.py": entry(100, 40, derive_branches_covered),
            "harness/src/iproofs/controls.py": entry(100, 20, 20),
            "harness/src/iproofs/validate/tree.py": entry(100, 50, 50),
        },
    }
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(doc))
    return path


def gate(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(GATE), str(path)], capture_output=True, text=True,
                          check=False, env={"PATH": "/usr/bin:/bin"})  # fmt: skip


def test_full_coverage_passes(tmp_path: Path) -> None:
    done = gate(report(tmp_path, 40))
    assert done.returncode == 0, done.stderr
    assert "iproofs.derive: 100.00 %" in done.stdout


def test_an_uncovered_derive_branch_fails(tmp_path: Path) -> None:
    done = gate(report(tmp_path, 39))  # one branch of iproofs.derive left uncovered
    assert done.returncode == 1
    assert "iproofs.derive is under its floor" in done.stderr
