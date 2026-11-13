import shutil
import subprocess
from pathlib import Path

import pytest

from iproofs.validate.tree import g2_append_only

RUN = "results/v0.1/fake/2026-11-20-fake-fake-tiny-ci-ci-cpu-1"


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=ci@example.org", "-c", "user.name=ci", *args],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / RUN).mkdir(parents=True)
    (tmp_path / RUN / "run.json").write_text("{}\n")
    (tmp_path / RUN / "manifest.json").write_text("{}\n")
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    git(tmp_path, "checkout", "-qb", "change")
    return tmp_path


def commit(repo: Path) -> list[str]:
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "change")
    return [f.rule for f in g2_append_only(repo, "main")]


def test_modified_run_file_rejected(repo: Path) -> None:
    (repo / RUN / "run.json").write_text('{"edited": true}\n')
    assert commit(repo) == ["APP-1"]


def test_deleted_run_rejected(repo: Path) -> None:
    shutil.rmtree(repo / RUN)
    assert commit(repo) == ["APP-1", "APP-1"]


def test_added_other_file_in_existing_run_rejected(repo: Path) -> None:
    (repo / RUN / "extra.json").write_text("{}\n")
    assert commit(repo) == ["APP-1"]


def test_controls_added_once_to_an_existing_run_accepted(repo: Path) -> None:
    (repo / RUN / "controls.json").write_text("{}\n")
    (repo / RUN / "controls-seed.json").write_text("{}\n")
    (repo / RUN / "controls-parts/job-1").mkdir(parents=True)
    (repo / RUN / "controls-parts/job-1/controls-part-1.json").write_text("{}\n")
    assert commit(repo) == []
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "change")
    git(repo, "checkout", "-qb", "again")
    (repo / RUN / "controls-parts/job-2").mkdir(parents=True)
    (repo / RUN / "controls-parts/job-2/controls-part-2.json").write_text("{}\n")
    assert commit(repo) == ["APP-1"]  # a run's controls are added once


def test_new_run_directory_accepted(repo: Path) -> None:
    new = repo / RUN.replace("-1", "-2")
    new.mkdir(parents=True)
    (new / "run.json").write_text("{}\n")
    assert commit(repo) == []
