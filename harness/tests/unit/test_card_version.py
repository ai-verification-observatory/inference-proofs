"""RFC-0002 §Rules 5 and §Configuration identity 1 on edited claim cards (CARD-1 to CARD-3)."""

import copy
import subprocess
from pathlib import Path

import pytest
import yaml

from iproofs.validate.tree import card_edit_problems, g2_card_edits

PIN = "64168df9fd0706dfd955b6795fa6f535872dff78"
REVIEW = {"handle": "m", "organisation": "Org", "date": "2026-11-03", "card_version": 3}
CARD: dict[str, object] = {
    "system": "fake",
    "configuration": "default",
    "card_version": 3,
    "upstream": {"repo": "o/r", "commit": PIN},
    "relation": "the output is the greedy next token",
    "reviewed_by": [REVIEW],
}


def edit(**changes: object) -> dict[str, object]:
    card = copy.deepcopy(CARD)
    card.update(changes)
    return card


def rules(new: dict[str, object]) -> list[str]:
    return [rule for rule, _, _ in card_edit_problems(CARD, new)]


@pytest.mark.parametrize(
    ("new", "expected"),
    [
        (edit(relation="changed"), ["CARD-1"]),  # no increment
        (edit(relation="changed", card_version=4), ["CARD-2"]),  # stale reviewed_by
        (edit(relation="changed", card_version=4, reviewed_by=[]), []),  # passes
        (edit(reviewed_by=[REVIEW, {**REVIEW, "handle": "n"}]), []),  # add a current review
        (edit(relation="changed", card_version=5, reviewed_by=[]), ["CARD-1"]),  # +2
        (edit(reviewed_by=[REVIEW, {**REVIEW, "card_version": 2}]), ["CARD-2"]),  # wrong version
    ],
)
def test_card_version_reset(new: dict[str, object], expected: list[str]) -> None:
    assert rules(new) == expected


def test_new_pin_is_a_new_configuration() -> None:
    new = edit(upstream={"repo": "o/r", "commit": "f" * 40}, card_version=4, reviewed_by=[])
    assert rules(new) == ["CARD-3"]


def git(repo: Path, *args: str) -> None:
    ident = [
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.invalid",
        "-c",
        "commit.gpgsign=false",
    ]
    subprocess.run(["git", "-C", str(repo), *ident, *args], check=True, capture_output=True)


def test_checks_cards_changed_since_base(tmp_path: Path) -> None:
    card = tmp_path / "systems/fake/claim.yaml"
    card.parent.mkdir(parents=True)
    card.write_text(yaml.safe_dump(CARD))
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    git(tmp_path, "checkout", "-qb", "edit")
    card.write_text(yaml.safe_dump(edit(relation="changed")))
    (tmp_path / "systems/fake/claims").mkdir()
    (tmp_path / "systems/fake/claims/new.yaml").write_text(yaml.safe_dump(edit(card_version=1)))
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "edit")
    found = [(f.path, f.rule) for f in g2_card_edits(tmp_path, "main")]
    assert found == [("systems/fake/claim.yaml", "CARD-1")]  # a new card is not an edit
