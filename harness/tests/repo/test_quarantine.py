"""Repository policy (RFC-0013 §G1): quarantined tests carry an issue, are at most 30 days old,
and nothing retries a failing test (docs/spec/07 §Flaky-test policy)."""

import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MAX_AGE_S = 30 * 24 * 3600
MARK = re.compile(r"pytest\.mark\.quarantine\b(\((?P<args>[^)]*)\))?")
RERUN = re.compile(r"pytest-rerunfailures|--reruns\b|\bflaky\b|pytest\.mark\.flaky")


def quarantine_problems(root: Path, now: float | None = None) -> list[str]:
    now = time.time() if now is None else now
    problems = []
    tests = [*root.glob("harness/tests/**/*.py"), *root.glob("systems/*/tests/**/*.py")]
    for path in sorted(tests):
        if path.name == "quarantine_plugin.py" or path == Path(__file__):
            continue
        for n, line in enumerate(path.read_text().splitlines(), start=1):
            m = MARK.search(line)
            if not m:
                continue
            where = f"{path.relative_to(root)}:{n}"
            if not re.search(r"\d", m.group("args") or ""):
                problems.append(f"{where}: quarantine without an issue number")
                continue
            added = _line_time(root, path, n)
            if added is not None and now - added > MAX_AGE_S:
                problems.append(f"{where}: quarantined more than 30 days; fix it or delete it")
    return problems


def _line_time(root: Path, path: Path, line: int) -> float | None:
    """The committer time of the commit that added the line; None when not committed yet."""
    out = subprocess.run(
        ["git", "-C", str(root), "blame", "--porcelain", "-L", f"{line},{line}", "--",
         str(path.relative_to(root))],
        capture_output=True, text=True, check=False,
    ).stdout  # fmt: skip
    if out.startswith("0" * 40):
        return None
    m = re.search(r"^committer-time (\d+)$", out, re.M)
    return float(m.group(1)) if m else None


def rerun_problems(root: Path) -> list[str]:
    files = [root / "pyproject.toml", root / "Makefile", *root.glob(".github/workflows/*.yml")]
    return [
        f"{p.relative_to(root)}:{n}: automatic retries are not allowed"
        for p in files
        if p.is_file()
        for n, line in enumerate(p.read_text().splitlines(), start=1)
        if RERUN.search(line)
    ]


def test_tree_follows_the_policy() -> None:
    assert quarantine_problems(ROOT) == []
    assert rerun_problems(ROOT) == []


def git(repo: Path, *args: str, when: str | None = None) -> None:
    env = {**os.environ, "GIT_AUTHOR_DATE": when or "", "GIT_COMMITTER_DATE": when or ""}
    if when is None:
        env = dict(os.environ)
    ident = [
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.invalid",
        "-c",
        "commit.gpgsign=false",
    ]
    subprocess.run(
        ["git", "-C", str(repo), *ident, *args], check=True, env=env, capture_output=True
    )


def test_quarantine_requires_issue(tmp_path: Path) -> None:
    (tmp_path / "harness/tests").mkdir(parents=True)
    (tmp_path / "harness/tests/test_x.py").write_text(
        "import pytest\n\n@pytest.mark.quarantine\ndef test_a(): ...\n"
        "@pytest.mark.quarantine(issue=42)\ndef test_b(): ...\n"
    )
    git(tmp_path, "init", "-q")
    assert quarantine_problems(tmp_path) == [
        "harness/tests/test_x.py:3: quarantine without an issue number"
    ]


def test_quarantine_older_than_30_days_fails(tmp_path: Path) -> None:
    (tmp_path / "harness/tests").mkdir(parents=True)
    path = tmp_path / "harness/tests/test_x.py"
    path.write_text("import pytest\n\n@pytest.mark.quarantine(issue=7)\ndef test_a(): ...\n")
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "old", when="2026-01-01T00:00:00Z")
    now = time.mktime(time.strptime("2026-01-20", "%Y-%m-%d"))
    assert quarantine_problems(tmp_path, now=now) == []  # 19 days
    later = now + 15 * 24 * 3600
    assert quarantine_problems(tmp_path, now=later) == [
        "harness/tests/test_x.py:3: quarantined more than 30 days; fix it or delete it"
    ]


def test_no_rerun_plugins_configured(tmp_path: Path) -> None:
    assert rerun_problems(ROOT) == []
    (tmp_path / "pyproject.toml").write_text('addopts = "--reruns 3"\n')
    assert rerun_problems(tmp_path) == ["pyproject.toml:1: automatic retries are not allowed"]


def test_quarantined_failure_does_not_block(tmp_path: Path) -> None:
    (tmp_path / "test_flaky.py").write_text(
        "import pytest\n\n@pytest.mark.quarantine(issue=99)\ndef test_flaky():\n    assert False\n"
    )
    summary = tmp_path / "summary.md"
    env = {**os.environ, "GITHUB_STEP_SUMMARY": str(summary)}
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "quarantine_plugin", "-p", "no:cacheprovider",
         "-o", "markers=quarantine(issue): flaky", "-o", "addopts=", "--rootdir", str(tmp_path),
         "-c", os.devnull, str(tmp_path / "test_flaky.py")],
        capture_output=True, text=True, env={**env, "PYTHONPATH": str(ROOT / "harness/tests")},
        check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stdout
    assert "1 xfailed" in done.stdout
    assert "test_flaky.py::test_flaky` failed (quarantined, issue #99)" in summary.read_text()
