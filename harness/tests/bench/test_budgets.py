"""B-VAL-TREE, B-DERIVE-RUN and B-CLI-START (docs/spec/08 §CPU-only tooling).

Each benchmark fails at twice its target and reports its time, with the target, to the job
summary named by IPROOFS_BENCH_SUMMARY. A time between the target and twice the target
passes; the summary line says so and a maintainer opens a `type:perf` issue.
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from fixtures.release_tree import build as build_release
from fixtures.synthetic_tree import generate
from iproofs.cli import main as cli_main
from iproofs.validate import check_derived
from iproofs.validate.tree import validate_tree

ROOT = Path(__file__).resolve().parents[3]
# ordinary test runs stay fast; CI sets IPROOFS_BENCH=1 on the default branch only
pytestmark = pytest.mark.skipif(
    os.environ.get("IPROOFS_BENCH") != "1", reason="benchmarks run with IPROOFS_BENCH=1"
)
COPY = ["schema", "systems/fake", "workloads/fake-tiny-ci.yaml", "reference",
        "harness/tests/fixtures/prompts"]  # fmt: skip


def report(budget: str, what: str, seconds: float, target_s: float) -> None:
    state = "within target" if seconds <= target_s else "over target, under the hard limit"
    unit, scale = ("ms", 1000) if target_s < 1 else ("s", 1)
    line = (
        f"{budget}: {seconds * scale:.1f} {unit} for {what} (target {target_s * scale:g} {unit}, "
        f"hard limit {2 * target_s * scale:g} {unit}; {state}; one sample on this runner)\n"
    )
    if path := os.environ.get("IPROOFS_BENCH_SUMMARY"):
        with open(path, "a") as f:
            f.write(line)
    assert seconds <= 2 * target_s, line


@pytest.fixture(scope="module")
def tree(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, list[Path]]:
    root = tmp_path_factory.mktemp("tree")
    for rel in COPY:
        src, dst = ROOT / rel, root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst) if src.is_dir() else shutil.copy(src, dst)
    runs = generate(root, 1000)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    return root, runs


def test_budget_validate_tree(tree: tuple[Path, list[Path]]) -> None:
    root, _ = tree
    start = time.monotonic()
    found = validate_tree(root)
    seconds = time.monotonic() - start
    assert [f.line() for f in found if not f.warning] == []
    report("B-VAL-TREE", "iproofs validate over 1,000 run directories", seconds, 60.0)


def test_budget_derive_run(tree: tuple[Path, list[Path]]) -> None:
    root, runs = tree
    start = time.monotonic()
    assert check_derived(runs[0] / "run.json", root) == []
    report(
        "B-DERIVE-RUN",
        "iproofs derive --check on one run directory",
        time.monotonic() - start,
        0.050,
    )


def test_budget_cli_start() -> None:
    cli = Path(sys.executable).with_name("iproofs")
    start = time.monotonic()
    subprocess.run([str(cli), "--help"], check=True, capture_output=True)
    report("B-CLI-START", "iproofs --help cold start", time.monotonic() - start, 0.5)


def test_budget_freeze(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """B-FREEZE: `iproofs release freeze` over a fixture release of 1,000 runs."""
    build_release(tmp_path, runs=1000)
    monkeypatch.chdir(tmp_path)
    start = time.monotonic()
    assert cli_main(["release", "freeze", "v0.1"]) == 0
    report("B-FREEZE", "iproofs release freeze over 1,000 run directories",
           time.monotonic() - start, 60.0)  # fmt: skip


def test_budget_site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """B-SITE: `iproofs site build` from the example board file (RFC-0018 §Site): the site reads
    the level file, one board file, the claim cards and the facts file, never the run records."""
    root = Path(__file__).resolve().parents[3]
    monkeypatch.chdir(root)
    start = time.monotonic()
    board = "harness/tests/fixtures/board/v1.0-example.json"
    assert cli_main(["site", "build", "--board", board, "--out", str(tmp_path / "out")]) == 0
    report("B-SITE", "iproofs site build from one board file",
           time.monotonic() - start, 60.0)  # fmt: skip
