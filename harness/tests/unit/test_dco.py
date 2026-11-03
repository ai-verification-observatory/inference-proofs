"""RFC-0013 §G11 and RFC-0001 test_dco_gate: DCO-1 over a fixture repository."""

import subprocess
from pathlib import Path

import pytest

from iproofs.errors import ErrorKind, IProofsError
from iproofs.validate.dco import check_range, main

AUTHOR = ["-c", "user.name=Ann Author", "-c", "user.email=ann@example.invalid"]


def commit(repo: Path, message: str, *extra: str) -> None:
    (repo / f"{message.split(maxsplit=1)[0]}.txt").write_text(message)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), *AUTHOR, "-c", "commit.gpgsign=false", "commit", "-qm", message,
         *extra],
        check=True,
    )  # fmt: skip


def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    commit(tmp_path, "base", "-s")
    return tmp_path


def test_dco_gate(tmp_path: Path) -> None:
    r = repo(tmp_path)
    commit(r, "signed", "-s")
    assert check_range(r, "HEAD~1..HEAD") == []
    commit(r, "unsigned")
    commit(r, "wrong email\n\nSigned-off-by: Ann Author <someone@example.invalid>")
    found = check_range(r, "HEAD~3..HEAD")
    assert [f.rule for f in found] == ["DCO-1", "DCO-1"]  # newest first: mismatch, unsigned
    assert all(f.gate == "G11" for f in found)


def test_email_case_and_merges(tmp_path: Path) -> None:
    r = repo(tmp_path)
    commit(r, "upper\n\nSigned-off-by: Ann Author <ANN@example.invalid>")
    subprocess.run(["git", "-C", str(r), "checkout", "-qb", "side", "HEAD~1"], check=True)
    commit(r, "side", "-s")
    subprocess.run(["git", "-C", str(r), "checkout", "-q", "main"], check=True)
    subprocess.run(
        ["git", "-C", str(r), *AUTHOR, "merge", "-q", "--no-ff", "--no-edit", "side"], check=True
    )
    assert check_range(r, "HEAD~2..HEAD") == []  # the merge commit itself is not checked


def test_cli_exit_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    r = repo(tmp_path)
    commit(r, "unsigned")
    monkeypatch.chdir(r)
    assert main(["HEAD~1..HEAD"]) == 1
    assert main(["HEAD~1"]) == 0  # the signed base commit alone
    assert main([]) == 2


def test_git_failure_is_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(IProofsError) as e:
        check_range(tmp_path, "HEAD~1..HEAD")  # not a repository
    assert e.value.kind == ErrorKind.CONFIG
    monkeypatch.chdir(tmp_path)
    assert main(["HEAD~1..HEAD"]) == 1
    assert capsys.readouterr().err.startswith("dco: git log HEAD~1..HEAD failed")
