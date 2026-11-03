"""RFC-0009 §Right of reply: RPL-1, the reply files a release names, and the G8 exemption."""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from iproofs.validate.tree import g8_language, reply_words, validate_tree
from secret_samples import sample

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "harness/tests/fixtures/gates/G2/reply-301-words.md"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for rel in ["schema", "systems/fake", "workloads/fake-tiny-ci.yaml", "reference"]:
        src, dst = ROOT / rel, tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst) if src.is_dir() else shutil.copy(src, dst)
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    return tmp_path


def add(repo: Path, rel: str, text: str) -> str:
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(text)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    return rel


def test_301_words_fails(repo: Path) -> None:
    rel = add(repo, "systems/fake/replies/v0.1.md", FIXTURE.read_text())
    found = [(f.rule, f.message) for f in validate_tree(repo, only=[rel])]
    assert found == [("RPL-1", "301 words; a reply has at most 300")]
    words = FIXTURE.read_text().split()
    add(repo, rel, " ".join(words[:-1]) + "\n")  # 300 words pass
    assert validate_tree(repo, only=[rel]) == []


def test_reply_word_count_ignores_link_targets() -> None:
    assert reply_words('See [our notes](https://example.org/a/very/long/target "title").') == 3
    assert reply_words("See [our notes][1].\n\n[1]: https://example.org/notes\n") == 3
    assert reply_words("- one\n- two *three*\n") == 5


def test_reply_excluded_from_language_lint(repo: Path) -> None:
    text = "Our system is the fastest and the best.\n"  # the maintainers' own words
    reply = add(repo, "systems/fake/replies/v0.1.md", text)
    readme = add(repo, "systems/fake/README.md", text)  # the same words outside a reply
    assert g8_language(repo, [reply]) == []
    assert {f.rule for f in g8_language(repo, [readme])} == {"LANG-1"}


def test_reply_still_scanned_for_secrets(repo: Path) -> None:
    rel = add(repo, "systems/fake/replies/v0.1.md", f"Contact: {sample('SEC-1')}\n")
    assert "G9" in {f.gate for f in validate_tree(repo, only=[rel])}


def test_release_names_missing_reply(repo: Path) -> None:
    doc = yaml.safe_load((ROOT / "schema/release/examples/valid/v0.1.yaml").read_text())
    doc |= {"runs": [], "replies": {"fake": "systems/fake/replies/v0.1.md"}}
    rel = add(repo, "releases/v0.1/release.yaml", yaml.safe_dump(doc, sort_keys=False))
    found = [(f.rule, f.message) for f in validate_tree(repo, only=[rel])]
    assert ("XREF-4", "reply file systems/fake/replies/v0.1.md does not exist") in found
    add(repo, "systems/fake/replies/v0.1.md", "A short reply.\n")
    assert not [f for f in validate_tree(repo, only=[rel]) if "reply" in f.message]


def test_html_escaped() -> None:
    """RFC-0009 §Right of reply: printed unedited with HTML escaped; emphasis, lists and links
    only."""
    from iproofs.site import reply_html  # noqa: PLC0415

    out = str(reply_html('<img src=x onerror="a()"> **bold** & [docs](https://example.org/d)'))
    assert out == ('<p>&lt;img src=x onerror=&quot;a()&quot;&gt; <strong>bold</strong> &amp; '
                   '<a href="https://example.org/d">docs</a></p>')  # fmt: skip
