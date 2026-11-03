"""RFC-0013 §G8, the neutral-language lint (LANG-1, LANG-2)."""

from pathlib import Path

import pytest

from iproofs import cli
from iproofs.validate.tree import g8_language, validate_tree

ROOT = Path(__file__).resolve().parents[3]
G8 = "harness/tests/fixtures/gates/G8"


def lint(tmp_path: Path, text: str, rel: str = "docs/x.md") -> list[tuple[str, str, bool]]:
    (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / rel).write_text(text)
    return [(f.path, f.rule, f.warning) for f in g8_language(tmp_path, [rel])]


def test_known_bad_fixtures() -> None:
    found = [(f.path, f.rule) for f in validate_tree(ROOT, only=[G8]) if f.gate == "G8"]
    assert found == [(f"{G8}/emoji.md:3", "LANG-2"), (f"{G8}/listed-word.md:3", "LANG-1")]


def test_fixture_directory_fails_on_the_command_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(ROOT)
    assert cli.main(["validate", G8]) == 1
    assert "LANG-1" in capsys.readouterr().out


@pytest.mark.parametrize(
    "text",
    [
        'The project never names a "fastest" system.\n',  # a quoted mention
        "It never names a “winner”.\n",  # typographic quotes
        "Forbidden words such as `beats` fail CI.\n",  # a backtick span
        "Delivery is best effort, and best-effort retries are logged.\n",
        "A heartbeat every second; the bestiary is unrelated.\n",  # whole words only
    ],
)
def test_mentions_and_exceptions_pass(tmp_path: Path, text: str) -> None:
    assert lint(tmp_path, text) == []


def test_uses_fail_case_insensitive(tmp_path: Path) -> None:
    text = "State of the Art results.\nIt Outperforms the rest.\n"
    assert lint(tmp_path, text) == [
        ("docs/x.md:1", "LANG-1", False),
        ("docs/x.md:2", "LANG-1", False),
    ]


def test_lang_allow_is_a_notice(tmp_path: Path) -> None:
    text = "<!-- lang-allow: beat quoting a paper title -->\nHow to beat the clock.\n"
    assert lint(tmp_path, text) == [("docs/x.md:2", "LANG-1", True)]


def test_scope_and_allowlist(tmp_path: Path) -> None:
    for rel in ("AGENTS.md", "systems/sash/replies/v0.1.md", "harness/notes.md"):
        assert lint(tmp_path, "the fastest\n", rel) == []
    assert lint(tmp_path, "the fastest\n", "systems/sash/README.md") == [
        ("systems/sash/README.md:1", "LANG-1", False)
    ]


def test_tree_passes() -> None:
    assert [f.line() for f in validate_tree(ROOT) if f.gate == "G8" and not f.warning] == []
