"""RFC-0001 §Testing Strategy test_licence_boundary (INV-GOV-6)."""

from pathlib import Path

import pytest

from iproofs.validate.licence import check, licence
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
