"""RFC-0018 §Order (OR-1 to OR-6) on hand-built rows, and the board built from synthetic
stored records (§The board file)."""

import json
import math
from pathlib import Path

import pytest

from fixtures.board import RELEASE, RUNG, SYSTEM, Tree, fidelity, fidelity_row, three_sessions
from iproofs.board import (
    NO_SECURITY_LEVEL,
    RowSummary,
    RungSummary,
    build_board,
    frontier,
    order,
    placed_above,
    positions,
)
from iproofs.schema import SchemaRegistry
from iproofs.serialize import dumps

ROOT = Path(__file__).resolve().parents[3]
MARGIN = 0.10


def row(system: str, multiple: float | None, m: tuple[float, ...] = (), *, passed: bool = True,
        stated: bool = True, session: tuple[float, ...] = ()) -> RowSummary:  # fmt: skip
    mean = sum(session) / len(session) if session else None
    return RowSummary(system, passed, stated, multiple, m, mean, session)


# ---------------------------------------------------------------- OR-3: margin and spread


def test_margin() -> None:
    """A at 0.89 of B with disjoint session ranges is placed above; at 0.95 it is not."""
    b = row("b", 10.0, (9.8, 10.0, 10.2))
    assert placed_above(row("a", 8.9, (8.8, 8.9, 9.0)), b, MARGIN)
    assert not placed_above(row("a", 9.5, (9.4, 9.5, 9.6)), b, MARGIN)
    assert not placed_above(b, row("a", 8.9, (8.8, 8.9, 9.0)), MARGIN)


def test_margin_boundary_is_inclusive() -> None:
    """Exactly (1 - margin) times B's mean is enough (`at most`)."""
    assert placed_above(row("a", 9.0, (8.9, 9.1)), row("b", 10.0, (9.5, 10.5)), MARGIN)


def test_spread() -> None:
    """Means 40 % apart but A's highest m reaches B's lowest: neither is above."""
    a, b = row("a", 6.0, (4.0, 6.0, 10.0)), row("b", 10.0, (10.0, 10.0, 10.0))
    assert not placed_above(a, b, MARGIN)
    assert not placed_above(b, a, MARGIN)


def test_ties_share_a_position_alphabetically() -> None:
    rows = [row("zeta", 9.5, (9.4, 9.6)), row("alpha", 10.0, (9.9, 10.1)),
            row("mid", 5.0, (4.9, 5.1))]  # fmt: skip
    assert [(r.system, p) for r, p in order(rows, MARGIN)] == [
        ("mid", 1), ("alpha", 2), ("zeta", 2)
    ]  # fmt: skip


def test_lone_row_holds_position_one() -> None:
    assert positions([row("only", 50.0, (49.0, 51.0))], MARGIN) == {"only": 1}


def test_lone_row_without_a_multiple_holds_position_one() -> None:
    assert positions([row("only", None, session=(100.0, 101.0))], MARGIN) == {"only": 1}


def test_no_stated_level_is_passed_and_unranked() -> None:
    rows = [row("a", 5.0, (5.0,), stated=False), row("b", 10.0, (10.0,))]
    ordered = order(rows, MARGIN)
    assert [(r.system, p, r.ranked) for r, p in ordered] == [("b", 1, True), ("a", None, False)]


def test_row_without_steady_state_is_ranked_after() -> None:
    """OR-3: a row with a multiple is above one without, whatever the session costs."""
    with_m = row("z", 30.0, (29.0, 31.0), session=(500.0, 510.0))
    without = row("a", None, session=(10.0, 11.0))
    assert placed_above(with_m, without, MARGIN)
    assert not placed_above(without, with_m, MARGIN)
    assert [(r.system, p) for r, p in order([without, with_m], MARGIN)] == [("z", 1), ("a", 2)]


def test_rows_without_multiple_compare_on_session_cost() -> None:
    a = row("a", None, session=(10.0, 10.5))
    b = row("b", None, session=(20.0, 21.0))
    c = row("c", None, session=(10.4, 10.6))
    assert [(r.system, p) for r, p in order([b, c, a], MARGIN)] == [
        ("a", 1), ("c", 1), ("b", 3)
    ]  # fmt: skip


def test_groups_in_order_each_alphabetical() -> None:
    """OR-5: ranked, then passed unranked, then not passed; each group alphabetical."""
    rows = [
        row("x-failed", 1.0, (1.0,), passed=False),
        row("b-unranked", 2.0, (2.0,), stated=False),
        row("a-failed", None, passed=False),
        row("a-unranked", 3.0, (3.0,), stated=False),
        row("ranked", 9.0, (9.0,)),
    ]
    assert [(r.system, p) for r, p in order(rows, MARGIN)] == [
        ("ranked", 1), ("a-unranked", None), ("b-unranked", None),
        ("a-failed", None), ("x-failed", None),
    ]  # fmt: skip


def test_frontier() -> None:
    """OR-6: the largest rung with a passed row; its position-1 rows, else every passed row."""
    small = RungSummary("small", 8, tuple(order([row("s", 2.0, (2.0,))], MARGIN)))
    big_failed = RungSummary("big", 400, tuple(order([row("f", 1.0, (1.0,), passed=False)],
                                                      MARGIN)))  # fmt: skip
    assert frontier([big_failed, small]) == {"rung": "small", "rows": ["s"], "systems_run": 1}
    unranked = RungSummary("mid", 100, tuple(order(
        [row("u2", 2.0, (2.0,), stated=False), row("u1", 1.0, (1.0,), stated=False),
         row("f", 1.0, (1.0,), passed=False)], MARGIN)))  # fmt: skip
    assert frontier([small, unranked]) == {"rung": "mid", "rows": ["u1", "u2"], "systems_run": 3}
    assert frontier([big_failed]) is None


# ---------------------------------------------------------------- the board file


@pytest.fixture
def tree(tmp_path: Path) -> Tree:
    return Tree(tmp_path)


def valid(board: dict[str, object]) -> None:
    errors = SchemaRegistry.from_tree(ROOT / "schema").errors("board/1", board)
    assert errors == []


def test_board_from_stored_records(tree: Tree) -> None:
    """Three sessions of 5 replies released at 100, 110, 120, 130 and 140 s on one GPU, commit
    starting at 0 s: m = 40 / 4 = 10 GPU-seconds per further reply, session cost 140 / 5 = 28;
    no baseline run, so no multiple; the empty rung is present with no row."""
    three_sessions(tree)
    fidelity(tree, {SYSTEM: fidelity_row()})
    board = build_board(tree.root, RELEASE, tree.level)
    valid(board)
    rungs = board["rungs"]
    assert isinstance(rungs, list)
    assert [r["id"] for r in rungs] == ["llama-4-maverick", RUNG, "gpt-2"]
    assert rungs[0]["rows"] == []
    assert rungs[0]["systems_run"] == 0
    (r,) = rungs[1]["rows"]
    assert (r["passed"], r["ranked"], r["position"]) == (True, True, 1)
    assert math.isclose(r["steady_gpu_seconds_per_reply"]["value"], 10.0)
    assert r["steady_gpu_seconds_per_reply"]["stats"]["n"] == 3
    assert math.isclose(r["session_gpu_seconds_per_reply"]["value"], 28.0)
    assert math.isclose(r["session_usd_per_reply"]["value"], 28.0 * 3.6 / 3600)
    assert (r["multiple"]["value"], r["multiple"]["null_reason"]) == (None, "missing_input")
    assert [s["groups"] for s in r["sessions"]] == [[1] * 5] * 3
    assert board["frontier"] == {"rung": RUNG, "rows": [SYSTEM], "systems_run": 1}
    assert board["date"] == "2026-12-01"


def test_board_multiple_and_unsteady_rows(tree: Tree, monkeypatch: pytest.MonkeyPatch) -> None:
    """With a baseline of 0.5 GPU-seconds per reply the steady row's multiple is m / 0.5; a row
    whose sessions have three groups has no steady state, no multiple and ranks after."""
    three_sessions(tree)
    tree.add_system(RUNG, "other", "l1-other")
    three_sessions(tree, system="other", workload="l1-other",
                   groups=((100, 1), (110, 2), (120, 2)))  # fmt: skip
    fidelity(tree, {SYSTEM: fidelity_row(), "other": fidelity_row()})
    base = {"value": 0.5, "unit": "gpu_s/request", "scope": "prove.steady", "grade": "derived",
            "tier": "reported", "null_reason": None,
            "source": {"kind": "derivation", "ref": "derive:D-L1-BASELINE@0.1.0",
                       "inputs": ["x#/proofs"]}}  # fmt: skip

    class Load:
        run_id, concurrency, gpus, gpu_seconds_per_reply, ladder = "r", 64, 1, base, ()

    serve = tree.run_dir("ref-serve", "2026-12-04-ref-serve-l1-l31-8b-p512-o512-serving-1")
    serve.mkdir(parents=True)
    (serve / "run.json").write_text(json.dumps({"run_id": serve.name, "system": "ref-serve"}))
    (serve / "manifest.json").write_text(json.dumps({
        "serving_model": {"id": "llama-3.1-8b-instruct-bf16"},
        "level": {"digest": tree.digest}}))  # fmt: skip
    import iproofs.baseline  # noqa: PLC0415

    monkeypatch.setattr(iproofs.baseline, "full_load", lambda run_dir, level: Load())
    board = build_board(tree.root, RELEASE, tree.level)
    valid(board)
    rung = board["rungs"][1]  # type: ignore[index]
    assert rung["baseline"]["concurrency"] == 64
    steady, unsteady = rung["rows"]
    assert (steady["system"], steady["position"]) == (SYSTEM, 1)
    assert math.isclose(steady["multiple"]["value"], 10.0 / 0.5)
    # no generation phase: no split (CO-7)
    assert steady["proving_multiple"]["value"] is None
    assert steady["steady_generation_gpu_seconds_per_reply"]["null_reason"] == "not_applicable"
    assert (unsteady["system"], unsteady["position"]) == ("other", 2)
    assert unsteady["multiple"]["null_reason"] == "not_applicable"
    assert {s["cause"] for s in unsteady["sessions"]} == {"too few groups"}
    assert unsteady["session_multiple"]["value"] is not None
    assert board["date"] == "2026-12-04"


def test_unranked_reason_and_failed_row(tree: Tree) -> None:
    three_sessions(tree)
    fidelity(tree, {SYSTEM: fidelity_row()})
    systems = tree.level["systems"]
    assert isinstance(systems, dict)
    systems[SYSTEM]["security"]["stated"] = False
    (r,) = build_board(tree.root, RELEASE, tree.level)["rungs"][1]["rows"]  # type: ignore[index]
    assert (r["passed"], r["ranked"], r["position"]) == (True, False, None)
    assert r["unranked_reason"] == NO_SECURITY_LEVEL
    fidelity(tree, {SYSTEM: fidelity_row("failed")})
    board = build_board(tree.root, RELEASE, tree.level)
    (r,) = board["rungs"][1]["rows"]  # type: ignore[index]
    assert (r["passed"], r["unranked_reason"], board["frontier"]) == (False, None, None)


def test_board_is_deterministic(tree: Tree) -> None:
    three_sessions(tree)
    first = dumps(build_board(tree.root, RELEASE, tree.level))
    assert dumps(build_board(tree.root, RELEASE, tree.level)) == first


def test_formula_ids_are_registered() -> None:
    from iproofs.derive import FORMULAS  # noqa: PLC0415

    assert {"D-L1-SESSION", "D-L1-STEADY", "D-L1-BASELINE", "D-L1-MULTIPLE",
            "D-L1-USD"} <= set(FORMULAS)  # fmt: skip


def test_freeze_refuses_another_level_digest(tree: Tree) -> None:
    """RFC-0018 §The level file: a v1 release freezes only runs naming its level by digest;
    v0.x releases predate levels."""
    from iproofs.release import RunView, level_mismatches, release_level  # noqa: PLC0415

    assert (release_level("v0.1"), release_level("v1.0"), release_level("v2.3")) == (
        None, "L1", "L2"
    )  # fmt: skip
    good = three_sessions(tree)[0]
    bad = three_sessions(Tree(tree.root / "b"), digest="sha256:" + "00" * 32)[0]
    runs = {p.name: RunView.read(p) for p in (good, bad)}
    assert [line.split()[0] for line in level_mismatches(runs, tree.digest)] == [bad.name]


def test_board_session_with_a_generation_phase(tree: Tree) -> None:
    """Five replies released 10 s apart after a 50 s generation phase on two GPUs: m = 40 x 2
    / 4 + 50 x 2 / 5 = 40 GPU-seconds per further reply; the phase's 20 is printed apart."""
    three_sessions(tree, gpus=2, generation=(40.0, 90.0))
    board = build_board(tree.root, RELEASE, tree.level)
    valid(board)
    (r,) = board["rungs"][1]["rows"]  # type: ignore[index]
    assert {s["generation_gpu_seconds_per_reply"] for s in r["sessions"]} == {20.0}
    assert {s["m"] for s in r["sessions"]} == {40.0}
    assert math.isclose(r["steady_gpu_seconds_per_reply"]["value"], 40.0)
    # CO-7: the split, 20 of generation and 40 - 20 = 20 of proving
    assert math.isclose(r["steady_generation_gpu_seconds_per_reply"]["value"], 20.0)
    assert math.isclose(r["steady_proving_gpu_seconds_per_reply"]["value"], 20.0)


def test_board_split_multiples(tree: Tree, monkeypatch: pytest.MonkeyPatch) -> None:
    """CO-7: m = 40 GPU-seconds per further reply, 20 of them generation (the phase test above),
    over a baseline of 0.5: multiple 80, proving 40, generation 40, and the two parts sum to m."""
    three_sessions(tree, gpus=2, generation=(40.0, 90.0))
    base = {"value": 0.5, "unit": "gpu_s/request", "scope": "prove.steady", "grade": "derived",
            "tier": "reported", "null_reason": None,
            "source": {"kind": "derivation", "ref": "derive:D-L1-BASELINE@0.1.0",
                       "inputs": ["x#/proofs"]}}  # fmt: skip

    class Load:
        run_id, concurrency, gpus, gpu_seconds_per_reply, ladder = "r", 64, 1, base, ()

    serve = tree.run_dir("ref-serve", "2026-12-04-ref-serve-l1-l31-8b-p512-o512-serving-1")
    serve.mkdir(parents=True)
    (serve / "run.json").write_text(json.dumps({"run_id": serve.name, "system": "ref-serve"}))
    (serve / "manifest.json").write_text(json.dumps({
        "serving_model": {"id": "llama-3.1-8b-instruct-bf16"},
        "level": {"digest": tree.digest}}))  # fmt: skip
    import iproofs.baseline  # noqa: PLC0415

    monkeypatch.setattr(iproofs.baseline, "full_load", lambda run_dir, level: Load())
    board = build_board(tree.root, RELEASE, tree.level)
    valid(board)
    (r,) = board["rungs"][1]["rows"]  # type: ignore[index]
    assert math.isclose(r["multiple"]["value"], 80.0)
    assert math.isclose(r["proving_multiple"]["value"], 40.0)
    assert math.isclose(r["generation_multiple"]["value"], 40.0)
    assert r["proving_multiple"]["source"]["inputs"][0].endswith(
        "/steady_proving_gpu_seconds_per_reply"
    )
