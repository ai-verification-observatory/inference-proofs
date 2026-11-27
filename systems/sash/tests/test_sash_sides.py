"""RFC-0018 CO-10 (proposed) on CPU: `prove` reports its phase in three parts, the proving of the
prompt's blocks and of the reply's block from compose-chunks' chunk rows and the rest, so CO-9's
whole phases are unchanged. Upstream is stub_upstream.py; the stored chunk rows of ten real
replies (fixtures/gpu/chunk-rows.json) are summed as `prove` sums them."""

import json
import statistics
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from sash_fixtures import load, run_step

HERE = Path(__file__).resolve().parent
PROMPT = list(range(128))
TOK = list(range(1000, 1064))
WHOLE = ["ids", "witness", "kernels_emit", "kernels_build", "prove"]


@pytest.fixture
def adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setenv("IPROOFS_SASH_STUB_TOK", json.dumps(TOK))
    return load(tmp_path, monkeypatch)


def prove(adapter: ModuleType, replies: int) -> dict[str, Any]:
    c = run_step(adapter, "commit", model_dir="/models")
    adapter.host("/io/prompts.jsonl").write_text((json.dumps(PROMPT) + "\n") * replies)
    return run_step(adapter, "prove", commitment_id=c["commitment_id"], model_dir="/models",
                    prover_files=c["prover_files"], prompts_file="/io/prompts.jsonl",
                    batch_size=1, batches=replies)  # fmt: skip


def phases(out: dict[str, Any]) -> dict[str, float]:
    return {p["name"]: p["seconds"] for p in out["phases"]}


def test_prove_reports_its_phase_by_side(adapter: ModuleType) -> None:
    """The stub's grid (128 + 64, 2 layers): blocks 0 and 1 are the prompt's, block 2 the reply's;
    each a row per layer and a head on blocks 1 and 2. The stub's rows take (1 + block) µs: the
    prompt side is 2 x 1 µs + 3 x 2 µs = 8 µs a reply, the reply side 3 x 3 µs = 9 µs."""
    out = prove(adapter, replies=2)
    got = phases(out)
    assert list(got) == [*WHOLE, "prove__prompt", "prove__reply", "prove__rest"]
    assert got["prove__prompt"] == pytest.approx(2 * 8e-6)
    assert got["prove__reply"] == pytest.approx(2 * 9e-6)
    assert got["prove__prompt"] + got["prove__reply"] + got["prove__rest"] == pytest.approx(
        got["prove"]
    )
    assert got["prove__rest"] > 0
    assert out["warnings"] == []


@pytest.mark.parametrize("rows", ["none", "drop"])
def test_prove_reports_no_part_without_every_row(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch, rows: str
) -> None:
    """A slice that prints no chunk rows, or one fewer than its segments: no part is reported for
    the session, never one side alone or a sum over some replies; the whole phases are kept."""
    monkeypatch.setenv("IPROOFS_SASH_STUB_ROWS", rows)
    out = prove(adapter, replies=1)
    assert list(phases(out)) == WHOLE
    [warning] = out["warnings"]
    assert warning.startswith("prove is not reported by side (RFC-0018 CO-10): req-0: its chunk")


def plan_of(tags: list[str], tmp: Path) -> str:
    (tmp / "plan.txt").write_text("# plan\n" + "".join(f"--x 1 --ser-tag {t}\n" for t in tags))
    return "/io/plan.txt"


def test_block_seconds_hand_case(adapter: ModuleType) -> None:
    """Two blocks of 2 layers in two slices: B0L0 3.0, B0L1 4.0, B0head 0.5 (prompt side 7.5);
    B1L0 5.0, B1L1 6.0, B1head 0.25 (reply side 11.25)."""
    io = adapter.host("/io")
    rows = [("B0L0", 3.0), ("B0L1", 4.0), ("B0head", 0.5), ("B1L0", 5.0), ("B1L1", 6.0),
            ("B1head", 0.25)]  # fmt: skip
    plan = plan_of([t for t, _ in rows], io)
    docs = [{"result": {"chunks": [{"ser_tag": t, "chunk_secs": s} for t, s in rows[a:b]]}}
            for a, b in ((0, 4), (4, 6))]  # fmt: skip
    assert adapter.block_seconds(docs, plan, 1) == (7.5, 11.25)
    assert adapter.prove_parts(20.0, (7.5, 11.25)) == {
        "prove__prompt": 7.5, "prove__reply": 11.25, "prove__rest": 1.25}  # fmt: skip
    assert "exceeds its prove phase" in adapter.prove_parts(18.0, (7.5, 11.25))
    twice = [docs[0], docs[1], {"result": {"chunks": [{"ser_tag": "B1L1", "chunk_secs": 6.0}]}}]
    assert "not the plan's 6 each once" in adapter.block_seconds(twice, plan, 1)
    bad = [docs[0], {"result": {"chunks": [{"ser_tag": "B1L1", "chunk_secs": None},
                                           *docs[1]["result"]["chunks"][1:]]}}]  # fmt: skip
    assert "'B1L1' has chunk_secs None" in adapter.block_seconds(bad, plan, 1)


def test_block_seconds_on_stored_chunk_rows(adapter: ModuleType) -> None:
    """Ten real replies of 512 + 512 at the pin (fixtures/gpu/chunk-rows.json): block 0 with its
    head (the prompt side) and block 1 with its head (the reply side), summed per reply. Hand
    check with the same rows: block 0 361.4 to 367.6 s, mean 364.0 s; block 1 368.8 to 374.9 s,
    mean 372.2 s. Session 1, reply 0: 361.351 s and 372.813 s."""
    stored = json.loads((HERE / "fixtures/gpu/chunk-rows.json").read_text())
    tags = [f"B{b}{k}" for b in (0, 1) for k in [*(f"L{x}" for x in range(32)), "head"]]
    plan = plan_of(tags, adapter.host("/io"))
    sides = []
    for session in stored["sessions"]:
        for reply in session["replies"]:
            assert [s["plan_slice"] for s in reply["slices"]] == [[0, 64], [64, 66]]
            docs = [{"result": {"chunks": s["chunks"]}} for s in reply["slices"]]
            sides.append(adapter.block_seconds(docs, plan, 1))
    assert len(sides) == 10
    assert sides[0] == pytest.approx((361.351, 372.813), abs=5e-4)
    prompt, reply = zip(*sides, strict=True)
    assert (round(min(prompt), 1), round(max(prompt), 1)) == (361.4, 367.6)
    assert (round(min(reply), 1), round(max(reply), 1)) == (368.8, 374.9)
    assert round(statistics.fmean(prompt), 1) == 364.0
    assert round(statistics.fmean(reply), 1) == 372.2
