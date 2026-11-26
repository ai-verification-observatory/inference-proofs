"""RFC-0018 CO-9 (adopted 2026-11-26, Q55): the cost of a further reply, its generation and
proving parts, both multiples, and the one-time work apart with its 5 % mark, on hand-computed
cases; and the release's cost rule (v1.0 stays whole-session)."""

import json
import math
from pathlib import Path
from typing import Any

import pytest

from fixtures.board import RELEASE, RUNG, SYSTEM, Tree, fidelity, fidelity_row, three_sessions
from iproofs.board import FURTHER_REPLY, WHOLE_SESSION, build_board, cost_rule
from iproofs.derive import (
    FORMULAS,
    further_reply_gpu_seconds,
    one_time_gpu_seconds,
    one_time_mark,
    phases_within,
    pooled_per_reply,
)
from iproofs.errors import IProofsError
from iproofs.provenance import file_digest
from iproofs.schema import SchemaRegistry
from iproofs.serialize import dumps

ROOT = Path(__file__).resolve().parents[3]
NS = 1_000_000_000


@pytest.fixture
def tree(tmp_path: Path) -> Tree:
    return Tree(tmp_path)


def valid(board: dict[str, object]) -> None:
    assert SchemaRegistry.from_tree(ROOT / "schema").errors("board/1", board) == []


def baseline(tree: Tree, monkeypatch: pytest.MonkeyPatch, value: float = 0.5) -> None:
    """A serving run whose full load is `value` GPU-seconds per reply (CO-4)."""
    base = {"value": value, "unit": "gpu_s/request", "scope": "prove.steady",
            "grade": "derived", "tier": "reported", "null_reason": None,
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


def row_of(board: dict[str, object], j: int = 0) -> Any:
    return board["rungs"][1]["rows"][j]  # type: ignore[index]


def phases(ids: float, rest: float, call: float) -> Any:
    """A run.json edit: the adapter reports `ids` and `rest` seconds of prove (RFC-0004
    adapter_phases), and the harness timed the prove call at `call` seconds."""

    def edit(run: dict[str, Any]) -> None:
        def q(v: float, ref: str, kind: str) -> dict[str, object]:
            return {"value": v, "unit": "s", "scope": "primitive" if kind == "adapter"
                    else "prove.session", "grade": "measured", "tier": "reported",
                    "null_reason": None, "source": {"kind": kind, "ref": ref}}  # fmt: skip

        run["adapter_phases"] = {"prove": {"ids": q(ids, "x#/adapter_phases/prove/ids", "adapter"),
                                           "prove": q(rest, "x#/adapter_phases/prove/prove",
                                                      "adapter")}}  # fmt: skip
        run["metrics"]["prove_call_seconds"] = q(call, "x#/events", "harness")

    return edit


# ---------------------------------------------------------------- the derivation, pure


def test_pooled_sums_costs_before_dividing() -> None:
    """Two sessions of 100 GPU-s over 4 replies and 50 over 1: pooled (100 + 50) / 5 = 30, not
    the mean of 25 and 50 (37.5); the range and the median are the sessions' own."""
    p = pooled_per_reply([(100.0, 4), (50.0, 1)])
    assert (p.value, p.low, p.high, p.median, p.n) == (30.0, 25.0, 50.0, 37.5, 2)


def test_further_reply_runs_from_prove_start_to_the_last_reply() -> None:
    """prove starts at 35 s, the last of five replies is released at 140 s, two GPUs:
    (140 - 35) x 2 = 210 GPU-seconds, 42 a reply."""
    times = [int(t * NS) for t in (100, 110, 120, 130, 140)]
    assert further_reply_gpu_seconds(35 * NS, times, 2) == 210.0
    with pytest.raises(IProofsError):
        further_reply_gpu_seconds(150 * NS, times, 2)


def test_one_time_work_and_its_mark() -> None:
    """Commit at 0 s, prove at 35 s, two GPUs: 70 GPU-s; with a setup of 1,000 GPU-s and a 5 s
    restore, 70 + 1,000 + 10 = 1,080. Against a further reply of 42: ceil(19 x 70 / 42) =
    ceil(31.67) = 32 replies, and at 32 the one-time work is 70 / (70 + 32 x 42) <= 5 %."""
    assert one_time_gpu_seconds(0, 35 * NS, 2) == 70.0
    assert one_time_gpu_seconds(0, 35 * NS, 2, 1000.0, 5.0) == 1080.0
    assert one_time_mark(70.0, 42.0) == 32
    assert 70 / (70 + 32 * 42) <= 0.05 < 70 / (70 + 31 * 42)
    assert one_time_mark(19.0, 19.0) == 19  # exactly 5 % at 19 replies: the factor is 19, exact


def test_adapter_phases_must_sum_to_the_prove_call() -> None:
    """Phases of 20 and 80 s against a prove call of 100.5 s are within 1 %; against 110 s
    (9 % apart) they are not; an empty report never is."""
    assert phases_within({"ids": 20.0, "prove": 80.0}, 100.5)
    assert not phases_within({"ids": 20.0, "prove": 80.0}, 110.0)
    assert not phases_within({}, 100.0)


def test_formula_ids_are_registered() -> None:
    assert {"D-L1-FURTHER", "D-L1-FURTHER-GENERATION", "D-L1-FURTHER-GENERATION-ADAPTER",
            "D-L1-FURTHER-PROVING", "D-L1-FURTHER-PROVING-ADAPTER", "D-L1-FURTHER-TOKENS",
            "D-L1-ONE-TIME", "D-L1-ONE-TIME-MARK"} <= set(FORMULAS)  # fmt: skip


# ---------------------------------------------------------------- the rule a release uses


def test_v1_0_keeps_the_whole_session_rule_and_later_releases_take_co_9() -> None:
    assert cost_rule("v1.0") == WHOLE_SESSION
    assert cost_rule("v1.1") == FURTHER_REPLY
    assert cost_rule("v1.0", FURTHER_REPLY) == FURTHER_REPLY  # a preview's override
    with pytest.raises(IProofsError):
        cost_rule("v1.1", "per-token")


def test_a_whole_session_board_has_no_co_9_field(tree: Tree) -> None:
    three_sessions(tree, prove_start=35.0)
    board = build_board(tree.root, RELEASE, tree.level)
    assert "cost_rule" not in board
    assert "further_reply_gpu_seconds" not in row_of(board)
    assert "further_reply" not in row_of(board)["sessions"][0]


# ---------------------------------------------------------------- the board, by CO-9


def test_further_reply_split_by_generation_marks(
    tree: Tree, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two GPUs; commit from 0 s, prove from 35 s, an AD-4 generation phase from 40 to 90 s,
    five replies released at 100 to 140 s; baseline 0.5 GPU-s a reply. A further reply is
    (140 - 35) x 2 / 5 = 42 GPU-s: generation 50 x 2 / 5 = 20, proving 22. Multiples 84 and 44.
    One-time work 35 x 2 = 70 GPU-s, its mark ceil(19 x 70 / 42) = 32. The rate pair: 512 / 0.5
    = 1,024 served over 512 / 42 proved is 84, the total multiple (CO-8 as Q55 amends it)."""
    three_sessions(tree, gpus=2, generation=(40.0, 90.0), commit_end=30.0, prove_start=35.0)
    fidelity(tree, {SYSTEM: fidelity_row()})
    baseline(tree, monkeypatch)
    board = build_board(tree.root, RELEASE, tree.level, FURTHER_REPLY)
    valid(board)
    assert board["cost_rule"] == FURTHER_REPLY
    r = row_of(board)
    total, gen, proving = (r[f"further_reply{k}_gpu_seconds"]
                           for k in ("", "_generation", "_proving"))  # fmt: skip
    assert (total["value"], gen["value"], proving["value"]) == (42.0, 20.0, 22.0)
    assert (total["scope"], total["unit"], total["stats"]["n"]) == (
        "prove.session",
        "gpu_s/request",
        3,
    )
    assert gen["source"]["ref"].startswith("derive:D-L1-FURTHER-GENERATION@")
    assert r["further_reply_split"]["source"] == "generation_marks"
    assert math.isclose(r["further_reply_multiple"]["value"], 84.0)
    assert math.isclose(r["further_reply_proving_multiple"]["value"], 44.0)
    one = r["one_time_gpu_seconds"]
    assert (one["value"], one["unit"], one["stats"]["n"]) == (70.0, "gpu_s", 3)
    assert r["one_time_mark_replies"]["value"] == 32
    served = board["rungs"][1]["baseline"]["reply_tokens_per_gpu_second"]  # type: ignore[index]
    proved = r["further_reply_tokens_per_gpu_second"]
    assert math.isclose(proved["value"], 512 / 42)
    assert math.isclose(served["value"] / proved["value"], r["further_reply_multiple"]["value"])
    assert r["proving_batch"]["replies"] is None  # the fixture writes no workload file
    assert {(s["further_reply"], s["further_reply_generation"], s["one_time"])
            for s in r["sessions"]} == {(42.0, 20.0, 70.0)}  # fmt: skip
    # the whole-session figures stay as they were: (140 - 0) x 2 / 5 = 56
    assert r["session_gpu_seconds_per_reply"]["value"] == 56.0


def test_further_reply_split_by_the_adapters_phases(
    tree: Tree, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SASH reports `ids` (its generation) inside prove: 20 s of 100 s of phases, the prove call
    timed at 100.5 s (within 1 %). One GPU, prove from 40 s, replies at 100 to 140 s: a further
    reply is 100 / 5 = 20 GPU-s, generation 20 / 5 = 4, proving 16; over 0.5: 40 and 32."""
    three_sessions(tree, commit_end=38.0, prove_start=40.0, run_edit=phases(20.0, 80.0, 100.5))
    fidelity(tree, {SYSTEM: fidelity_row()})
    baseline(tree, monkeypatch)
    board = build_board(tree.root, RELEASE, tree.level, FURTHER_REPLY)
    valid(board)
    r = row_of(board)
    gen, proving = r["further_reply_generation_gpu_seconds"], r["further_reply_proving_gpu_seconds"]
    assert (r["further_reply_gpu_seconds"]["value"], gen["value"], proving["value"]) == (
        20.0, 4.0, 16.0)  # fmt: skip
    assert gen["source"]["ref"].startswith("derive:D-L1-FURTHER-GENERATION-ADAPTER@")
    assert proving["source"]["ref"].startswith("derive:D-L1-FURTHER-PROVING-ADAPTER@")
    assert any(i.endswith("/adapter_phases/prove/ids") for i in gen["source"]["inputs"])
    assert "source adapter" in gen["note"]
    split = r["further_reply_split"]
    assert (split["source"], split["phase"], split["tolerance"]) == ("adapter_phases", "ids", 0.01)
    assert [s["within"] for s in split["sessions"]] == [True] * 3
    assert math.isclose(r["further_reply_multiple"]["value"], 40.0)
    assert math.isclose(r["further_reply_proving_multiple"]["value"], 32.0)
    assert r["one_time_gpu_seconds"]["value"] == 40.0
    assert r["one_time_mark_replies"]["value"] == 38  # ceil(19 x 40 / 20)


def test_phases_far_from_the_prove_call_give_no_split(
    tree: Tree, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same phases against a prove call of 110 s (9 % apart): the board refuses the split,
    the total stays."""
    three_sessions(tree, prove_start=40.0, run_edit=phases(20.0, 80.0, 110.0))
    baseline(tree, monkeypatch)
    board = build_board(tree.root, RELEASE, tree.level, FURTHER_REPLY)
    valid(board)
    r = row_of(board)
    assert r["further_reply_gpu_seconds"]["value"] == 20.0
    for key in ("further_reply_generation_gpu_seconds", "further_reply_proving_gpu_seconds",
                "further_reply_proving_multiple"):  # fmt: skip
        assert (r[key]["value"], r[key]["null_reason"]) == (None, "not_applicable")
    split = r["further_reply_split"]
    assert split["source"] is None
    assert [s["within"] for s in split["sessions"]] == [False] * 3
    assert split["cause"].startswith("slots 1, 2, 3: the adapter's prove phases sum to 100.0 s")


def setup_record(tree: Tree, setup_id: str, gpu_seconds: float) -> str:
    """A setup/1 record stored beside the sessions, its digest returned."""
    folder = tree.root / "results" / RELEASE / SYSTEM / "_setups" / setup_id
    folder.mkdir(parents=True)

    def q(v: float, unit: str) -> dict[str, object]:
        return {"value": v, "unit": unit}

    path = folder / "setup.json"
    path.write_text(json.dumps({"setup_id": setup_id, "gpu_count": q(1, "count"),
                                "total_seconds": q(gpu_seconds, "s"),
                                "gpu_seconds": q(gpu_seconds, "gpu_s")}))  # fmt: skip
    return file_digest(path)


def reused(setup_id: str, digest: str, restore: float) -> Any:
    def edit(run: dict[str, Any]) -> None:
        run["setup"] = {"setup_id": setup_id, "record_digest": digest,
                        "restore_seconds": {"value": restore, "unit": "s"}}  # fmt: skip

    return edit


def test_a_reused_setup_is_one_time_work(tree: Tree) -> None:
    """Sessions that reused a setup of 1,000 GPU-s, restored in 5 s, commit at 0 s and prove at
    40 s on one GPU: one-time work 1,000 + 40 + 5 = 1,045 GPU-s; a further reply (140 - 40) / 5
    = 20, so the mark is ceil(19 x 1,045 / 20) = ceil(992.75) = 993. The whole-session cost has
    no value (setup_reused, CO-1), the further reply has."""
    digest = setup_record(tree, "2026-12-01-setup-sash-x-1", 1000.0)
    three_sessions(tree, prove_start=40.0, run_edit=reused("2026-12-01-setup-sash-x-1", digest,
                                                           5.0))  # fmt: skip
    board = build_board(tree.root, RELEASE, tree.level, FURTHER_REPLY)
    valid(board)
    r = row_of(board)
    assert r["session_gpu_seconds_per_reply"]["value"] is None
    assert r["further_reply_gpu_seconds"]["value"] == 20.0
    assert r["one_time_gpu_seconds"]["value"] == 1045.0
    assert r["one_time_mark_replies"]["value"] == 993
    (made,) = r["one_time_setups"]
    assert (made["setup_id"], made["gpu_seconds"]) == ("2026-12-01-setup-sash-x-1", 1000.0)


def test_a_setup_record_with_another_digest_stops_the_board(tree: Tree) -> None:
    setup_record(tree, "2026-12-01-setup-sash-x-1", 1000.0)
    three_sessions(
        tree,
        prove_start=40.0,
        run_edit=reused("2026-12-01-setup-sash-x-1", "sha256:" + "0" * 64, 5.0),
    )
    with pytest.raises(IProofsError):
        build_board(tree.root, RELEASE, tree.level, FURTHER_REPLY)


def test_a_missing_setup_record_leaves_the_one_time_work_null(tree: Tree) -> None:
    three_sessions(
        tree,
        prove_start=40.0,
        run_edit=reused("2026-12-01-setup-sash-x-1", "sha256:" + "0" * 64, 5.0),
    )
    r = row_of(build_board(tree.root, RELEASE, tree.level, FURTHER_REPLY))
    assert (r["one_time_gpu_seconds"]["value"], r["one_time_mark_replies"]["value"]) == (None, None)
    assert "is not stored" in r["one_time_gpu_seconds"]["note"]


def test_or_3_falls_back_on_the_further_reply(tree: Tree, monkeypatch: pytest.MonkeyPatch) -> None:
    """Two rows without a steady state (three release groups). SASH: commit at 0, prove at
    900 s, replies up to 1,020 s: whole session 1,020 / 5 = 204, further reply 120 / 5 = 24.
    The other: prove at 0, replies up to 300 s: 60 both ways. By whole sessions the other is
    first (60 <= 0.9 x 204); by CO-9 SASH is (24 <= 0.9 x 60)."""
    three_sessions(tree, prove_start=900.0, groups=((1000, 1), (1010, 1), (1020, 3)))
    tree.add_system(RUNG, "other", "l1-other")
    three_sessions(tree, system="other", workload="l1-other", prove_start=0.0,
                   groups=((100, 1), (110, 1), (300, 3)))  # fmt: skip
    fidelity(tree, {SYSTEM: fidelity_row(), "other": fidelity_row()})
    baseline(tree, monkeypatch)
    whole = build_board(tree.root, RELEASE, tree.level)
    further = build_board(tree.root, RELEASE, tree.level, FURTHER_REPLY)
    valid(further)
    assert [(r["system"], r["position"]) for r in whole["rungs"][1]["rows"]] == [  # type: ignore[index]
        ("other", 1), (SYSTEM, 2)]  # fmt: skip
    assert [(r["system"], r["position"]) for r in further["rungs"][1]["rows"]] == [  # type: ignore[index]
        (SYSTEM, 1), ("other", 2)]  # fmt: skip


def test_the_board_by_co_9_is_deterministic(tree: Tree) -> None:
    three_sessions(tree, prove_start=40.0, run_edit=phases(20.0, 80.0, 100.5))
    first = dumps(build_board(tree.root, RELEASE, tree.level, FURTHER_REPLY))
    assert dumps(build_board(tree.root, RELEASE, tree.level, FURTHER_REPLY)) == first


def test_stored_v1_0_records_by_co_9() -> None:
    """The v1.0 records by CO-9 (a preview: the stored board is not written): FlashProve's
    further reply is its whole session less the one-time work before prove, the parts add up,
    and the served rate over the proved one is the total multiple."""
    board = build_board(ROOT, "v1.0", "L1", FURTHER_REPLY)
    valid(board)
    stored = json.loads((ROOT / "releases" / "v1.0" / "board.json").read_text())
    rung = board["rungs"][0]  # type: ignore[index]
    (r,) = rung["rows"]
    (old,) = stored["rungs"][0]["rows"]
    assert r["system"] == "flashprove"
    n = rung["requests_per_session"]
    for s, o in zip(r["sessions"], old["sessions"], strict=True):
        assert math.isclose(s["further_reply"] + s["one_time"] / n, o["session"], rel_tol=1e-12)
    total = r["further_reply_gpu_seconds"]["value"]
    parts = (r["further_reply_generation_gpu_seconds"]["value"]
             + r["further_reply_proving_gpu_seconds"]["value"])  # fmt: skip
    assert math.isclose(total, parts, rel_tol=1e-12)
    served = rung["baseline"]["reply_tokens_per_gpu_second"]["value"]
    proved = r["further_reply_tokens_per_gpu_second"]["value"]
    assert math.isclose(served / proved, r["further_reply_multiple"]["value"], rel_tol=1e-12)
    assert r["proving_batch"]["replies"] == 24
