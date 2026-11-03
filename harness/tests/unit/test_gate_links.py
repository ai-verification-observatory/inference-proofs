"""RFC-0013 §G12: relative links and anchors (LNK-1), RFC references (LNK-2)."""

from pathlib import Path

from iproofs.validate import links
from iproofs.validate.tree import validate_tree

ROOT = Path(__file__).resolve().parents[3]
G12 = "harness/tests/fixtures/gates/G12"


def test_known_bad_fixture() -> None:
    found = [(f.path, f.rule) for f in validate_tree(ROOT, only=[G12]) if f.gate == "G12"]
    assert found == [
        (f"{G12}/broken.md:3", "LNK-1"),
        (f"{G12}/broken.md:4", "LNK-1"),
        (f"{G12}/broken.md:5", "LNK-2"),
    ]


def corpus(tmp_path: Path, doc: str) -> list[str]:
    (tmp_path / "rfcs").mkdir()
    (tmp_path / "rfcs/0001-process.md").write_text("# RFC-0001\n")
    (tmp_path / "docs/spec").mkdir(parents=True)
    glossary = (ROOT / "docs/spec/10-glossary.md").read_text()
    (tmp_path / "docs/spec/10-glossary.md").write_text(glossary)
    (tmp_path / "docs/x.md").write_text(doc)
    return [f.line() for f in links.check(tmp_path, ["docs/x.md"])]


def test_glossary_html_anchor_passes(tmp_path: Path) -> None:
    assert corpus(tmp_path, "See [attested](spec/10-glossary.md#attested) and RFC-0001.\n") == []


def test_github_slug_rules(tmp_path: Path) -> None:
    doc = (
        "# Title\n"
        "## `iproofs run` (the CLI)\n"
        "## Steps: 1, 2 & 3\n"
        "## Title\n"
        "## A [link](x.md) heading\n"
        "```\n## Not a heading\n[no](missing.md) RFC-9999\n```\n"
        "[a](#iproofs-run-the-cli) [b](#steps-1-2--3) [c](#title-1) [d](#a-link-heading)\n"
        "Inline code is skipped: `[x](missing.md)` and `RFC-9999`.\n"
        "[e](https://example.org/a) [f](#not-a-heading)\n"
    )
    assert corpus(tmp_path, doc) == [
        "G12 docs/x.md:12 LNK-1: #not-a-heading: no such anchor (fix: fix the path or the heading)"
    ]


def test_tree_passes() -> None:
    assert [f.line() for f in validate_tree(ROOT) if f.gate == "G12"] == []


def test_external_links_listed_not_fetched_in_validate(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("[a](https://example.org/a) [b](https://example.org/a)\n")
    assert links.external_links(tmp_path, ["README.md"]) == [
        ("README.md:1", "https://example.org/a")
    ]
