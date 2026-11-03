import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = sorted((ROOT / ".github/workflows").glob("*.yml"))


def workflow_commands() -> list[str]:
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    commands: list[str] = []
    for job in ci["jobs"].values():
        for step in job["steps"]:
            run = step.get("run", "")
            if run.startswith("uv run") and run not in commands:
                commands.append(run)
    return commands


def make_commands() -> list[str]:
    recipe = (ROOT / "Makefile").read_text().split("ci:\n", 1)[1]
    lines = [ln.strip() for ln in recipe.splitlines() if ln.startswith("\t")]
    return [re.sub(r"^\w+=\S+ ", "", ln) for ln in lines if "uv run" in ln]


def test_make_ci_runs_the_workflow_commands() -> None:
    assert make_commands() == workflow_commands()


def test_actions_pinned_by_full_commit() -> None:
    uses = [m.group(1) for wf in WORKFLOWS for m in re.finditer(r"uses:\s*(\S+)", wf.read_text())]
    assert uses
    for ref in uses:
        assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", ref), ref


def test_workflow_permissions_read_only() -> None:
    for wf in WORKFLOWS:
        assert yaml.safe_load(wf.read_text())["permissions"] == {"contents": "read"}


def test_g1_rejects_known_bad_fixture() -> None:
    bad = ROOT / "harness/tests/fixtures/gates/G1/ruff_violation.py"
    cmd = [sys.executable, "-m", "ruff", "check", "--isolated", str(bad)]
    result = subprocess.run(cmd, check=False, capture_output=True)
    assert result.returncode == 1
    assert b"F401" in result.stdout
