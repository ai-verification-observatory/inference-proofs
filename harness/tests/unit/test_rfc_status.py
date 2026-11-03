"""RFC-0001 §Testing Strategy test_rfc_status_index (GOV-4)."""

from pathlib import Path

from iproofs.validate.governance import check_rfc_index
from iproofs.validate.tree import validate_tree

ROOT = Path(__file__).resolve().parents[3]
INDEX = (
    "| # | Title | Status | Target milestone |\n|---|---|---|---|\n"
    "| [0001](0001-process.md) | Process | Draft | v0.1 |\n"
    "| [0002](0002-claim.md) | Claim | Accepted | v0.1 |\n"
)


def rfc(status: str) -> str:
    return f"# RFC\n\n- Status: {status}\n- Authors: x\n"


def rules(files: dict[str, str]) -> list[tuple[str, str]]:
    return [(f.path, f.message) for f in check_rfc_index({"rfcs/README.md": INDEX, **files})]


def test_rfc_status_index() -> None:
    ok = {"rfcs/0001-process.md": rfc("Draft"), "rfcs/0002-claim.md": rfc("Accepted")}
    assert rules({**ok, "rfcs/0000-template.md": rfc("Draft | Last call")}) == []
    # a Draft file listed as Accepted
    assert rules({**ok, "rfcs/0002-claim.md": rfc("Draft")}) == [
        ("rfcs/0002-claim.md", "status Draft but rfcs/README.md says Accepted")
    ]
    # a file missing from the index
    extra = {**ok, "rfcs/0003-new.md": rfc("Draft")}
    assert rules(extra) == [("rfcs/0003-new.md", "no row in rfcs/README.md")]
    # an unknown status value
    found = rules({**ok, "rfcs/0001-process.md": rfc("Approved")})
    assert found[0][0] == "rfcs/0001-process.md"
    assert "'Approved' is not one of Draft" in found[0][1]
    # an index row without a file
    assert rules({"rfcs/0001-process.md": rfc("Draft")}) == [
        ("rfcs/README.md:4", "row 0002-claim.md has no RFC file (Accepted)")
    ]


def test_superseded_by_names_its_successor() -> None:
    index = INDEX.replace("| Accepted |", "| Superseded |")
    files = {
        "rfcs/README.md": index,
        "rfcs/0001-process.md": rfc("Draft"),
        "rfcs/0002-claim.md": rfc("Superseded by RFC-0003"),
    }
    assert check_rfc_index(files) == []


def test_repository_index_matches() -> None:
    assert [f.line() for f in validate_tree(ROOT, only=["rfcs"]) if f.rule == "GOV-4"] == []
