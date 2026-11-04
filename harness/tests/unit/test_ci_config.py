import re
import subprocess
import sys
from pathlib import Path

import pytest
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
    return [re.sub(r"^(\w+=\S+ )+", "", ln) for ln in lines if "uv run" in ln]


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


def test_shards_partition_the_suite() -> None:
    """Every test runs in exactly one shard (docs/spec/07 §Sharding)."""
    from conftest import shard_of  # noqa: PLC0415

    ids = [f"t{i:03d}" for i in range(100)]
    parts = [shard_of(ids, f"{i}/3") for i in (1, 2, 3)]
    assert set().union(*parts) == set(ids)
    assert sum(len(p) for p in parts) == len(ids)
    assert sorted(len(p) for p in parts) == [33, 33, 34]
    with pytest.raises(pytest.UsageError):
        shard_of(ids, "4/3")


def test_shards_cover_the_workflow_matrix() -> None:
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    shard = ci["jobs"]["test-shard"]
    assert shard["env"]["IPROOFS_SHARD"].endswith(f"/{len(shard['strategy']['matrix']['shard'])}")
    assert ci["jobs"]["tests"]["needs"] == "test-shard"
