"""INV-GOV-4 merge guard (RFC-0001 §Conflicts of interest rule 2)."""

import subprocess
from pathlib import Path

import pytest

from iproofs.validate import merge_guard
from iproofs.validate.governance import parse

MAINTAINERS = """
| Handle | Role | Organisation | Systems maintained | Declared interests | Since |
|---|---|---|---|---|---|
| alice | maintainer | Lab A | none | advises SASH | 2026-11-03 |
| bob | maintainer | Lab B | none | none | 2026-11-03 |
| carol | maintainer | Lab C | flashprove | none | 2026-11-03 |
| dan | system maintainer | Lab D | sash | sash (author) | 2026-11-03 |
"""
ROWS = parse(MAINTAINERS)


def rules(paths: list[str], approved: list[str]) -> list[str]:
    return [f.message for f in merge_guard.check(paths, approved, ROWS)]


def test_merge_guard_conflicted_approval_fails() -> None:
    found = rules(["systems/sash/claim.yaml"], ["alice"])
    assert found == ["INV-GOV-4: changes to sash are approved only by alice, who declared an "
                     "interest in it"]  # fmt: skip
    assert rules(["results/v0.1/flashprove/run-1/run.json"], ["Carol"])  # maintains it, any case


def test_merge_guard_second_approval_passes() -> None:
    assert rules(["systems/sash/claim.yaml"], ["alice", "bob"]) == []
    assert rules(["systems/sash/claim.yaml"], ["alice", "dan"]) != []  # dan is no maintainer


def test_merge_guard_unrelated_change_passes() -> None:
    assert rules(["harness/src/iproofs/cli.py"], ["alice"]) == []
    assert rules(["systems/fake/system.yaml"], ["alice"]) == []
    assert rules(["systems/sash-two/system.yaml"], ["alice"]) == []  # a word, not a prefix
    assert rules(["systems/sash/README.md"], []) == []  # nobody approved yet: not this rule


def test_merge_guard_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                         capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    (tmp_path / "schema/quantity").mkdir(parents=True)
    (tmp_path / "schema/quantity/1.schema.json").write_text("{}")
    (tmp_path / "MAINTAINERS.md").write_text(MAINTAINERS)
    git = ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run([*git, "init", "-q", "-b", "main"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "base", "--no-gpg-sign"], check=True)
    (tmp_path / "systems/sash").mkdir(parents=True)
    (tmp_path / "systems/sash/claim.yaml").write_text("x: 1\n")
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "card", "--no-gpg-sign"], check=True)
    monkeypatch.chdir(tmp_path)
    assert merge_guard.main(["--base", "HEAD~1", "--approved", "alice"]) == 1
    assert "GOV-5" in capsys.readouterr().err
    assert merge_guard.main(["--base", "HEAD~1", "--approved", "alice,bob"]) == 0
    assert "systems touched ['sash']" in capsys.readouterr().out
