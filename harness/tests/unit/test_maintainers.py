"""RFC-0001 §Roles: MAINTAINERS.md rows and seat rules (RFC-0001 §Testing Strategy)."""

from pathlib import Path

import pytest

from iproofs import cli
from iproofs.validate import governance

ROOT = Path(__file__).resolve().parents[3]
HEADER = (
    "| Handle | Role | Organisation | Systems maintained | Declared interests | Since |\n"
    "|---|---|---|---|---|---|\n"
)


def table(*rows: tuple[str, str, str, str]) -> str:
    """Rows of (handle, role, organisation, declared interests)."""
    body = "".join(f"| {h} | {r} | {o} | none | {i} | 2026-11-03 |\n" for h, r, o, i in rows)
    return "# Maintainers\n\n" + HEADER + body


def rules(text: str, *, release: bool = False) -> list[tuple[str, bool]]:
    return [(f.rule, f.warning) for f in governance.check(text, release=release)]


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (("ann", "maintainer", "", "none"), [("GOV-1", False)]),  # missing organisation
        (("ann", "maintainer", "Org A", ""), [("GOV-1", False)]),  # missing interests
        (("ann", "maintainer", "Org A", "none"), []),  # `none` is a declaration
        (("ann", "maintainer", "undeclared", "none"), [("GOV-1", True)]),  # placeholder warns
    ],
)
def test_maintainers_file_schema(row: tuple[str, str, str, str], expected: object) -> None:
    other = ("bo", "maintainer", "Org B", "none")
    assert rules(table(row, other)) == expected


def test_seat_rule() -> None:
    two = table(("a", "maintainer", "Org A", "none"), ("b", "maintainer", "Org B", "none"))
    assert rules(two) == []  # INV-GOV-1 holds
    one = table(("a", "maintainer", "Org A", "none"), ("b", "maintainer", "Org A", "none"))
    assert rules(one) == [("GOV-2", True)]  # a warning before release
    assert rules(one, release=True) == [("GOV-2", False)]  # a failure at release approval
    three_one = table(
        *[(h, "maintainer", "Org A", "none") for h in "abc"], ("d", "maintainer", "Org B", "none")
    )
    assert rules(three_one) == [("GOV-3", False)]  # INV-GOV-2
    two_two = table(*[(h, "maintainer", o, "none") for h, o in zip("abcd", "AABB", strict=True)])
    assert rules(two_two) == []


def test_unaffiliated_individuals_are_their_own_organisation() -> None:
    solo = table(*[(h, "maintainer", "none", "none") for h in "abcd"])
    assert rules(solo) == []  # four people, four organisations


def test_system_maintainers_do_not_hold_seats() -> None:
    text = table(("a", "maintainer", "Org A", "none"), ("s", "system maintainer", "Org B", "none"))
    assert rules(text) == [("GOV-2", True)]


def test_repository_file_has_every_field() -> None:
    """G1 against the real file: no row lacks a field; placeholders only warn."""
    found = governance.check((ROOT / "MAINTAINERS.md").read_text())
    assert [f.line() for f in found if not f.warning] == []
    assert governance.parse((ROOT / "MAINTAINERS.md").read_text())


def test_warnings_go_to_stderr_and_pass(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(ROOT)
    assert cli.main(["validate", "MAINTAINERS.md"]) == 0  # placeholders only warn
    out = capsys.readouterr()
    assert "GOV-" not in out.out  # stdout is the failure list
    assert "validate: 0 failures in 0 files" in out.err
