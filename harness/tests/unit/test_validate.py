import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from iproofs import cli
from iproofs.validate.tree import validate_tree

ROOT = Path(__file__).resolve().parents[3]
GATES = ROOT / "harness/tests/fixtures/gates"
RUN_DIR = "results/v0.1/fake/2026-11-20-fake-fake-tiny-ci-ci-cpu-1"


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A minimal repository: the schemas, the fake system and its workload, the reference files."""
    for rel in [
        "schema",
        "systems/fake",
        "workloads/fake-tiny-ci.yaml",
        "reference",
        "harness/tests/fixtures/prompts",
    ]:
        src, dst = ROOT / rel, tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst) if src.is_dir() else shutil.copy(src, dst)
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "-A")
    git(tmp_path, "-c", "user.email=ci@example.org", "-c", "user.name=ci", "commit", "-qm", "base")
    return tmp_path


def place(repo: Path, fixture: str, target: str) -> None:
    dst = repo / target
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(GATES / fixture, dst)
    git(repo, "add", "-A")


def rules(repo: Path) -> set[tuple[str, str]]:
    return {(f.gate, f.rule) for f in validate_tree(repo)}


def test_clean_repository_passes(repo: Path) -> None:
    assert validate_tree(repo) == []


def test_g2_unknown_workload(repo: Path) -> None:
    place(repo, "G2/run-unknown-workload.json", f"{RUN_DIR}/run.json")
    assert ("G2", "XREF-1") in rules(repo)


def test_g2_rate_without_scope(repo: Path) -> None:
    place(repo, "G2/run-rate-without-scope.json", f"{RUN_DIR}/run.json")
    found = [f for f in validate_tree(repo) if f.rule == "SCHEMA"]
    assert any(f.message.startswith("/metrics/rate_prove.steady:") for f in found)


def test_g3_not_canonical(repo: Path) -> None:
    place(repo, "G3/not-canonical.json", "workloads/extra.json")
    assert ("G3", "FMT-1") in rules(repo)


def test_g5_bare_float(repo: Path) -> None:
    place(repo, "G5/manifest-bare-float.json", f"{RUN_DIR}/manifest.json")
    found = [f for f in validate_tree(repo) if f.rule == "LBL-4"]
    assert [f.pointer for f in found] == ["/machine/gpu_clock_mhz"]


def test_g2_size_limit(repo: Path) -> None:
    big = repo / "workloads/blob.bin"
    with big.open("wb") as f:
        f.truncate(5 * 1024 * 1024 + 1)
    git(repo, "add", "-A")
    assert ("G2", "SIZE-1") in rules(repo)


def test_failure_output_sorted_and_formatted(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    place(repo, "G3/not-canonical.json", "workloads/b.json")
    place(repo, "G3/not-canonical.json", "workloads/a.json")
    place(repo, "G2/run-unknown-workload.json", f"{RUN_DIR}/run.json")
    monkeypatch.chdir(repo)
    assert cli.main(["validate"]) == 1
    out = capsys.readouterr()
    lines = out.out.splitlines()
    assert lines == sorted(lines, key=lambda line: (line.split()[0], line.split()[1].encode()))
    line_re = r"^G\d+ \S+ [A-Z0-9-]+: .+$"
    assert all(re.match(line_re, line) for line in lines), lines
    fmt = [line for line in lines if " FMT-1:" in line]
    assert [line.split()[1] for line in fmt] == ["workloads/a.json", "workloads/b.json"]
    assert re.search(r"validate: \d+ failures in \d+ files", out.err)


def test_format_json_fields(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    place(repo, "G3/not-canonical.json", "workloads/a.json")
    monkeypatch.chdir(repo)
    assert cli.main(["validate", "--format", "json"]) == 1
    [item] = json.loads(capsys.readouterr().out)
    assert set(item) == {"gate", "path", "pointer", "line", "rule", "message", "hint"}
    assert item["hint"] == "run iproofs fmt workloads/a.json"


def test_fmt_fixes_format(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    place(repo, "G3/not-canonical.json", "workloads/a.json")
    monkeypatch.chdir(repo)
    assert cli.main(["fmt", "workloads/a.json"]) == 0
    assert cli.main(["validate"]) == 0


def test_fmt_is_hidden(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert " fmt" not in capsys.readouterr().out


def test_repository_validates() -> None:
    """The repository itself passes every tree gate."""
    assert [f.line() for f in validate_tree(ROOT)] == []
