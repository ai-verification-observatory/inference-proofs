"""RFC-0013 §G12: relative links and anchors (LNK-1), RFC references (LNK-2)."""

import email.message
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import pytest

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


class _Response:
    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _urlopen(request: urllib.request.Request, timeout: float) -> _Response:
    """Offline stand-in: the last path segment of the url picks the outcome."""
    url = request.full_url
    last = url.rsplit("/", 1)[-1]
    if last.isdigit():
        raise urllib.error.HTTPError(url, int(last), "status", email.message.Message(), None)
    if last == "down":
        raise urllib.error.URLError("refused")
    return _Response()


def test_fetch_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    urls = ["https://example.org/ok", "https://example.org/404", "https://example.org/403",
            "https://example.org/429", "https://example.org/down"]  # fmt: skip
    assert links.fetch_failures([("a.md:1", u) for u in urls]) == [
        "a.md:1 https://example.org/404: HTTP 404",
        "a.md:1 https://example.org/down: <urlopen error refused>",
    ]


def test_external_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "schema/quantity").mkdir(parents=True)
    (tmp_path / "schema/quantity/1.schema.json").write_text("{}\n")
    (tmp_path / "README.md").write_text("[a](https://example.org/404) [b](docs/x.md)\n")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    monkeypatch.chdir(tmp_path)
    assert links.main([]) == 2
    assert links.main(["--external"]) == 1
    out = capsys.readouterr()
    assert out.out == "README.md:1 https://example.org/404: HTTP 404\n"
    assert out.err.endswith("links: 1 external links failed\n")
