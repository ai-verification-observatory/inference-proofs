"""RFC-0018 §The glyph (GL-1 to GL-5): each petal's rule on hand-built inputs, and the board's
glyph from synthetic records."""

import json
from pathlib import Path

from fixtures.board import RELEASE, SYSTEM, Tree, fidelity, fidelity_row, three_sessions
from iproofs.board import build_board
from iproofs.glyph import (
    NO_PROPERTIES,
    PETALS,
    any_model,
    faithful_model,
    statement_petal,
    statement_petals,
)

COMMIT = "a" * 40
HELD = dict.fromkeys(("run", "model", "prompt", "reply", "no_weight_file", "fidelity"), "held")
QUOTE = {"text": "a quote", "url": "https://example.org/x"}


def properties(**states: str) -> dict[str, object]:
    def petal(state: str) -> dict[str, object]:
        if state == "not_stated":
            return {"state": state, "reason": "silent", "quotes": [],
                    "sources_read": ["README.md", "docs/a.md"]}  # fmt: skip
        return {"state": state, "reason": f"{state} reason", "quotes": [QUOTE],
                "sources_read": ["README.md"]}  # fmt: skip

    return {"schema": "properties/1", "system": SYSTEM, "configuration": "default",
            "upstream": {"repo": "x/y", "commit": COMMIT}, "read": "2026-11-11",
            "petals": {p: petal(states.get(p, "green"))
                       for p in ("unforgeable", "weights_hidden", "no_trusted_party")}}  # fmt: skip


def state(petal: object) -> tuple[str, str]:
    return petal.state, petal.basis  # type: ignore[attr-defined]


# ---------------------------------------------------------------- statement petals


def test_statement_only() -> None:
    found = statement_petals(properties(unforgeable="amber"), HELD, COMMIT)
    assert state(found["unforgeable"]) == ("amber", "statement")
    assert found["unforgeable"].quotes == (QUOTE,)
    assert state(found["weights_hidden"]) == ("green", "statement")


def test_failed_check_lowers_its_petals() -> None:
    """GL-2: a failed Reply check sets unforgeable red; No weight file sets weights_hidden red;
    neither touches no_trusted_party."""
    reply_failed = {**HELD, "reply": "failed"}
    found = statement_petals(properties(), reply_failed, COMMIT)
    assert state(found["unforgeable"]) == ("red", "test")
    assert state(found["weights_hidden"]) == ("green", "statement")
    found = statement_petals(properties(), {**HELD, "no_weight_file": "failed"}, COMMIT)
    assert state(found["weights_hidden"]) == ("red", "test")
    assert state(found["unforgeable"]) == ("green", "statement")
    assert state(found["no_trusted_party"]) == ("green", "statement")


def test_held_check_never_raises() -> None:
    found = statement_petals(properties(unforgeable="red"), HELD, COMMIT)
    assert state(found["unforgeable"]) == ("red", "statement")


def test_not_stated_is_red_with_the_documents_read() -> None:
    petal = statement_petal("no_trusted_party", properties(no_trusted_party="not_stated"), COMMIT)
    assert (petal.state, petal.reason) == ("red", f"not stated in README.md, docs/a.md at {COMMIT}")


def test_missing_file_and_other_commit_are_red() -> None:
    assert statement_petal("unforgeable", None, COMMIT).reason == NO_PROPERTIES
    assert statement_petal("unforgeable", None).state == "red"
    assert statement_petal("unforgeable", properties(), "b" * 40).state == "red"


# ---------------------------------------------------------------- faithful model


def doc(row: list[int], rerun: list[int] | None) -> dict[str, object]:
    controls = [] if rerun is None else [{"id": "reference-2", "kind": "honest", "status": "ok",
                                          "scores": rerun}]  # fmt: skip
    return {"test": {"alpha": 0.05, "exact_up_to": 20, "resamples": 1000},
            "controls": controls, "rows": {SYSTEM: {"scores": row}}}  # fmt: skip


def test_faithful_green_when_the_rerun_is_not_above() -> None:
    """Equal scores: every sign vector reaches the observed mean 0, p = 1 >= alpha."""
    petal = faithful_model("held", None, doc([500] * 15, [500] * 15), SYSTEM, None)
    assert state(petal) == ("green", "test")


def test_faithful_amber_when_the_rerun_scores_above() -> None:
    """The rerun 10 tokens above the row on all 15 prompts: p = 1 / 2^15 < 0.05."""
    petal = faithful_model("held", None, doc([490] * 15, [500] * 15), SYSTEM, None)
    assert petal.state == "amber"


def test_faithful_red_and_hollow() -> None:
    assert faithful_model("failed", None, None, SYSTEM, None).state == "red"
    assert faithful_model("undecided", "not resolved", doc([1], [1]), SYSTEM, None).state == (
        "hollow"
    )
    assert faithful_model("held", None, None, SYSTEM, None).state == "hollow"
    assert faithful_model("held", None, doc([1] * 15, None), SYSTEM, None).state == "hollow"


def test_faithful_monte_carlo_needs_the_beacon() -> None:
    """n = 30 > exact_up_to: the test draws sign vectors, seeded from the beacon."""
    rows = doc([500] * 30, [500] * 30)
    assert faithful_model("held", None, rows, SYSTEM, None).state == "hollow"
    assert faithful_model("held", None, rows, SYSTEM, "ab" * 32).state == "green"


# ---------------------------------------------------------------- any model


def test_any_model_counts_rungs() -> None:
    assert any_model(2, 2, False).state == "green"
    assert any_model(2, 3, False).state == "amber"
    assert any_model(1, 2, False).state == "red"
    assert any_model(1, 2, True).state == "red"
    assert any_model(0, 2, False).state == "red"
    assert any_model(0, 2, True).state == "hollow"


# ---------------------------------------------------------------- the board's glyph


def test_board_glyph(tmp_path: Path) -> None:
    """A row that passed on the 8B rung only, with a properties file: statement petals as
    read, faithful green (15 equal scores), any_model red (1 of 2 rungs)."""
    tree = Tree(tmp_path)
    three_sessions(tree)
    fidelity(tree, {SYSTEM: fidelity_row()})
    path = tmp_path / "results" / RELEASE / "fidelity" / "llama-3.1-8b" / "fidelity.json"
    found = json.loads(path.read_text())
    found["controls"].append({"id": "reference-2", "kind": "honest", "status": "ok",
                              "scores": [500] * 15, "mean_prefix": 500.0, "kl": None})  # fmt: skip
    path.write_text(json.dumps(found))
    (tmp_path / "systems" / SYSTEM / "properties.yaml").write_text(
        json.dumps(properties(weights_hidden="amber", no_trusted_party="not_stated"))
    )
    board = build_board(tree.root, RELEASE, tree.level)
    (r,) = board["rungs"][1]["rows"]  # type: ignore[index]
    assert [p["id"] for p in r["glyph"]] == list(PETALS)
    assert [p["state"] for p in r["glyph"]] == ["green", "amber", "green", "red", "red"]
    assert [p["basis"] for p in r["glyph"]] == ["statement", "statement", "test", "run",
                                                 "statement"]  # fmt: skip
