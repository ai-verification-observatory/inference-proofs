import shutil
import subprocess
from pathlib import Path

import pytest

from iproofs.validate.tree import validate_tree

ROOT = Path(__file__).resolve().parents[3]
G7 = ROOT / "harness/tests/fixtures/gates/G7"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
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
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    return tmp_path


def place(repo: Path, fixture: str, target: str) -> list[tuple[str, str]]:
    shutil.copy(G7 / fixture, repo / target)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    return [(f.path, f.rule) for f in validate_tree(repo) if f.gate == "G7"]


def test_fake_dockerfile_is_pinned(repo: Path) -> None:
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    assert [f for f in validate_tree(repo) if f.gate == "G7"] == []


def test_checkout_of_full_hash_or_variable_passes(repo: Path) -> None:
    dockerfile = repo / "systems/fake/Dockerfile"
    extra = f"RUN git checkout ${{UPSTREAM_COMMIT}}\nRUN git checkout {'0' * 40}\n"
    dockerfile.write_text(dockerfile.read_text() + extra)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    assert [f for f in validate_tree(repo) if f.gate == "G7"] == []


def test_unpinned_dockerfile(repo: Path) -> None:
    found = place(repo, "Dockerfile-unpinned", "systems/fake/Dockerfile")
    d = "systems/fake/Dockerfile"
    assert found == [
        (f"{d}:2", "PIN-2"),  # FROM without a digest
        (f"{d}:3", "PIN-1"),  # short upstream commit
        (f"{d}:4", "PIN-1"),  # git checkout of a branch
        (f"{d}:5", "PIN-5"),  # pip package without ==version (numpy==2.1.0 is fine)
        (f"{d}:6", "PIN-5"),  # apt package without =version
        (f"{d}:7", "PIN-2"),
        (f"{d}:7", "PIN-5"),  # latest
    ]


def test_reference_range_rejected(repo: Path) -> None:
    found = place(repo, "reference-range.yaml", "reference/v0.1.yaml")
    assert found == [("reference/v0.1.yaml", "PIN-4")]
