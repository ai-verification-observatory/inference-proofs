"""RFC-0001 §Testing Strategy test_licence_boundary (INV-GOV-6)."""

import json
import subprocess
from pathlib import Path

import pytest

from iproofs.validate.licence import check, licence, main
from iproofs.validate.tree import tracked_files

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("systems/sash/claims/default.yaml", "data"),
        ("systems/sash/claim.yaml", "data"),
        ("systems/sash/external.yaml", "data"),
        ("systems/sash/replies/v0.1.md", "data"),
        ("systems/sash/entrypoint", "code"),
        ("systems/sash/system.yaml", "code"),
        ("results/v0.1/x/run.json", "data"),
        ("rfcs/0001-process-and-governance.md", "data"),
        ("harness/src/iproofs/cli.py", "code"),
        ("schema/run/1.schema.json", "code"),
        ("Makefile", "code"),  # fits neither list: code
    ],
)
def test_licence_boundary(path: str, expected: str) -> None:
    assert licence(path) == expected


def test_unmapped_adapter_file_fails() -> None:
    files = ["systems/sash/Dockerfile", "systems/sash/notes.txt", "systems/sash/claim.yaml"]
    assert [(f.path, f.rule) for f in check(files)] == [("systems/sash/notes.txt", "LIC-1")]


def test_every_tracked_file_is_mapped() -> None:
    files = tracked_files(ROOT)
    assert {licence(f) for f in files} == {"code", "data"}
    assert [f.line() for f in check(files)] == []


def test_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for rel in ["schema/quantity/1.schema.json", "docs/a.md", "systems/x/notes.txt"]:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("{}\n")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    monkeypatch.chdir(tmp_path)
    assert main([]) == 1
    out = capsys.readouterr()
    assert out.out == "code: 2 files\ndata: 1 files\n"
    assert "systems/x/notes.txt LIC-1" in out.err
    (tmp_path / "systems/x/notes.txt").unlink()
    assert main(["--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "docs/a.md": "data",
        "schema/quantity/1.schema.json": "code",
    }
