"""RFC-0018 CO-10 (proposed 2026-11-27, Q56): the prompt side and the reply side. Request A on
the ladder (level, runner, baseline), the serving baseline on each side, a further reply split
into its sides from the adapter's per-side parts and by position, and the multiples, on
hand-computed cases."""

import json
import math
import shutil
from pathlib import Path
from typing import Any

import pytest

from fixtures.board import RELEASE, RUNG, Tree, fidelity, fidelity_row, three_sessions
from iproofs.baseline import FullLoad, full_load
from iproofs.board import FURTHER_REPLY, build_board
from iproofs.derive import (
    FORMULAS,
    apportion,
    phase_parts,
    reply_side_baseline,
    side_multiples,
    whole_phases,
)
from iproofs.errors import IProofsError
from iproofs.level import prompt_side_workload
from iproofs.runner import level_run
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
SERVING = "llama-3.1-8b-instruct-bf16"
A = "l1-l31-8b-p512-o1"


# ---------------------------------------------------------------- the derivation, pure


def test_apportion_adds_the_shared_rest_by_position() -> None:
    """80 GPU-s with measured parts 30 and 40: the rest 10 goes 5 and 5 over 512 and 512
    positions, so 35 and 45; over 512 and 1,536 positions it goes 2.5 and 7.5."""
    assert apportion(80.0, (30.0, 40.0), (512, 512)) == (35.0, 45.0)
    assert apportion(80.0, (30.0, 40.0), (512, 1536)) == (32.5, 47.5)
    assert apportion(80.0, (0.0, 0.0), (512, 512)) == (40.0, 40.0)
    # parts 0.5 % over the total are rounding: the rest is 0; 5 % over is refused
    assert apportion(100.0, (50.0, 50.5), (1, 1)) == (50.0, 50.5)
    with pytest.raises(IProofsError):
        apportion(100.0, (50.0, 55.0), (1, 1))


def test_the_total_multiple_is_the_weighted_mean_of_the_sides() -> None:
    """s_A = 0.01, s_B = 0.04 GPU-s a reply; a further reply of 7 GPU-s, 1 on the prompt side
    and 6 on the reply side: 1 / 0.01 = 100 and 6 / 0.03 = 200; with w = 0.25 the total
    7 / 0.04 = 175 = 0.25 x 100 + 0.75 x 200."""
    s_a, s_b = 0.01, 0.04
    assert math.isclose(reply_side_baseline(s_a, s_b), 0.03)
    prompt, reply = side_multiples(1.0, 6.0, s_a, s_b)
    assert (math.isclose(prompt, 100.0), math.isclose(reply, 200.0)) == (True, True)
    w = s_a / s_b
    assert math.isclose(7.0 / s_b, w * prompt + (1 - w) * reply)
    assert math.isclose(7.0 / s_b, 175.0)
    with pytest.raises(IProofsError):
        reply_side_baseline(0.04, 0.04)  # s_B <= s_A: no reply side


def test_a_phase_part_is_not_a_whole_phase() -> None:
    phases = {"ids": 20.0, "ids__prompt": 2.0, "ids__reply": 14.0, "prove": 80.0,
              "prove__prompt": 30.0}  # fmt: skip
    assert whole_phases(phases) == {"ids": 20.0, "prove": 80.0}
    assert phase_parts(phases, "ids") == {"prompt": 2.0, "reply": 14.0}
    assert phase_parts(phases, "prove") == {"prompt": 30.0}


def test_formula_ids_are_registered() -> None:
    assert {"D-L1-BASELINE-REPLY", "D-L1-PROMPT-SHARE", "D-L1-PROMPT-GENERATION",
            "D-L1-REPLY-GENERATION", "D-L1-PROMPT-PROVING", "D-L1-REPLY-PROVING", "D-L1-PROMPT",
            "D-L1-REPLY", "D-L1-PROMPT-MULTIPLE",
            "D-L1-REPLY-MULTIPLE"} <= set(FORMULAS)  # fmt: skip


# ---------------------------------------------------------------- request A: level and runner


def test_request_a_is_found_in_the_rungs_serving_record() -> None:
    assert prompt_side_workload(ROOT, SERVING, 512) == A
    assert prompt_side_workload(ROOT, "llama-4-maverick-17b-128e-instruct-fp8", 512) == (
        "l1-maverick-p512-o1")  # fmt: skip
    assert prompt_side_workload(ROOT, "gpt2-fp32", 512) is None


def test_level_run_serves_request_a_on_the_ladder_with_a_one_token_reply() -> None:
    lv = level_run(ROOT, REGISTRY, "L1", "ref-serve", A, None)
    assert (lv.rung, lv.slot, lv.prompt_tokens, lv.output_tokens, lv.prompt_side) == (
        "llama-3.1-8b", None, 512, 1, True)  # fmt: skip
    b = level_run(ROOT, REGISTRY, "L1", "ref-serve", "l1-l31-8b-p512-o512", None)
    assert (b.output_tokens, b.prompt_side) == (512, False)
    assert (lv.ladder, lv.ladder_prompts) == (b.ladder, b.ladder_prompts)  # the same ladder


@pytest.mark.parametrize(("system", "slot"), [("ref-serve", 1), ("sash", None), ("sash", 1)])
def test_request_a_is_never_a_session_or_a_prover_run(system: str, slot: int | None) -> None:
    with pytest.raises(IProofsError) as e:
        level_run(ROOT, REGISTRY, "L1", system, A, slot)
    assert e.value.kind.value == "config"


# ---------------------------------------------------------------- the baseline of request A


def test_full_load_takes_request_a_only_when_the_caller_names_its_rung(tmp_path: Path) -> None:
    from test_baseline import RATES, ladder_run, level  # noqa: PLC0415

    run_dir = ladder_run(tmp_path, RATES, 1)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    manifest["workload"]["id"] = A
    (run_dir / "manifest.json").write_text(json.dumps(manifest))
    lv = level(tuple(RATES))
    assert isinstance(full_load(run_dir, lv), str)  # on no rung: never the rung's baseline
    got = full_load(run_dir, lv, {A: "llama-3.1-8b"})
    assert isinstance(got, FullLoad)
    assert (got.rung, got.concurrency) == ("llama-3.1-8b", 8)
    assert math.isclose(float(got.gpu_seconds_per_reply["value"]), 1 / 60, rel_tol=1e-6)  # type: ignore[arg-type]


# ---------------------------------------------------------------- the board


@pytest.fixture
def tree(tmp_path: Path) -> Tree:
    return Tree(tmp_path)


def _q(value: float) -> dict[str, object]:
    return {"value": value, "unit": "gpu_s/request", "scope": "prove.steady", "grade": "derived",
            "tier": "reported", "null_reason": None,
            "source": {"kind": "derivation", "ref": "derive:D-L1-BASELINE@0.1.0",
                       "inputs": ["x#/proofs"]}}  # fmt: skip


def serving(tree: Tree, monkeypatch: pytest.MonkeyPatch, s_b: float = 0.5,
            s_a: float | None = 0.1) -> None:  # fmt: skip
    """The rung's serving runs: its request at full load `s_b` GPU-s a reply and, unless
    `s_a` is None, its request A at `s_a` (CO-4 by a stub); the serving record and request A's
    workload as the repository holds them."""
    for rel in (f"workloads/serving/{SERVING}.yaml", f"workloads/{A}.yaml"):
        (tree.root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, tree.root / rel)

    def load(value: float, run_id: str) -> object:
        class Load:
            concurrency, gpus, ladder = 64, 1, ()

        Load.run_id = run_id  # type: ignore[attr-defined]
        Load.gpu_seconds_per_reply = _q(value)  # type: ignore[attr-defined]
        return Load()

    runs: list[tuple[str, str | None]] = [
        ("2026-12-04-ref-serve-l1-l31-8b-p512-o512-serving-1", None)
    ]
    if s_a is not None:
        # started first: the rung's baseline must still be the request's own run (CO-10)
        runs.append(("2026-12-03-ref-serve-l1-l31-8b-p512-o1-serving-1", A))
    for run_id, workload in runs:
        d = tree.run_dir("ref-serve", run_id)
        d.mkdir(parents=True)
        (d / "run.json").write_text(json.dumps({"run_id": run_id, "system": "ref-serve"}))
        manifest: dict[str, Any] = {"serving_model": {"id": SERVING},
                                    "level": {"digest": tree.digest}}  # fmt: skip
        if workload:
            manifest["workload"] = {"id": workload, "load_point": "ladder"}
        (d / "manifest.json").write_text(json.dumps(manifest))
    import iproofs.baseline  # noqa: PLC0415

    def stub(run_dir: Path, level: object, workloads: object = None) -> object:
        """Each run's own full load, whatever the caller names."""
        if "-p512-o1-" in run_dir.name:
            assert s_a is not None
            return load(s_a, run_dir.name)
        return load(s_b, run_dir.name)

    monkeypatch.setattr(iproofs.baseline, "full_load", stub)


def phases(values: dict[str, float], call: float) -> Any:
    """A run.json edit: the adapter's prove phases (RFC-0004 adapter_phases, parts named
    `<phase>__<part>`) and the harness-timed prove call."""

    def edit(run: dict[str, Any]) -> None:
        def q(v: float, ref: str, kind: str) -> dict[str, object]:
            return {"value": v, "unit": "s", "scope": "primitive" if kind == "adapter"
                    else "prove.session", "grade": "measured", "tier": "reported",
                    "null_reason": None, "source": {"kind": kind, "ref": ref}}  # fmt: skip

        run["adapter_phases"] = {"prove": {k: q(v, f"x#/adapter_phases/prove/{k}", "adapter")
                                           for k, v in values.items()}}  # fmt: skip
        run["metrics"]["prove_call_seconds"] = q(call, "x#/events", "harness")

    return edit


SASH = {"ids": 20.0, "ids__prompt": 2.0, "ids__reply": 14.0, "prove": 80.0,
        "prove__prompt": 30.0, "prove__reply": 40.0}  # fmt: skip


def board(tree: Tree) -> dict[str, Any]:
    out = build_board(tree.root, RELEASE, tree.level, FURTHER_REPLY)
    assert REGISTRY.errors("board/1", out) == []
    return out


def rung_of(b: dict[str, Any]) -> dict[str, Any]:
    found: dict[str, Any] = next(r for r in b["rungs"] if r["id"] == RUNG)
    return found


def test_sides_from_the_adapters_parts(tree: Tree, monkeypatch: pytest.MonkeyPatch) -> None:
    """One GPU, prove from 40 s, five replies up to 140 s: a further reply is 100 / 5 = 20 GPU-s,
    `ids` 20 of it (generation), 80 proving. Generation: parts 2 and 14, the rest 4 split 2 and
    2 by 512 and 512 positions, so 4 and 16 GPU-s, 0.8 and 3.2 a reply. Proving: parts 30 and
    40, the rest 10 split 5 and 5, so 35 and 45, 7 and 9 a reply. Totals 7.8 and 12.2 (20).
    Serving: s_B 0.5, s_A 0.1, so 0.4 on the reply side and w = 0.2. Multiples: proving 7 / 0.1
    = 70 and 9 / 0.4 = 22.5; total 78 and 30.5; and 0.2 x 78 + 0.8 x 30.5 = 40 = 20 / 0.5."""
    three_sessions(tree, commit_end=38.0, prove_start=40.0, run_edit=phases(SASH, 100.5))
    fidelity(tree, {"sash": fidelity_row()})
    serving(tree, monkeypatch)
    rung = rung_of(board(tree))
    base = rung["baseline"]["sides"]
    assert base["workload"] == A
    assert base["request"] == {"prompt_tokens": 512, "output_tokens": 1}
    assert math.isclose(base["prompt_gpu_seconds_per_reply"]["value"], 0.1)
    assert math.isclose(base["reply_gpu_seconds_per_reply"]["value"], 0.4)
    assert math.isclose(base["prompt_share"]["value"], 0.2)
    assert rung["baseline"]["gpu_seconds_per_reply"]["value"] == 0.5  # the request's, unchanged
    (row,) = rung["rows"]
    sides = row["sides"]
    assert (sides["generation_core"], sides["proving_core"]) == ("adapter_phases",) * 2
    got = {k: sides[k]["value"] for k in ("prompt_generation_gpu_seconds",
           "reply_generation_gpu_seconds", "prompt_proving_gpu_seconds",
           "reply_proving_gpu_seconds", "prompt_gpu_seconds", "reply_gpu_seconds")}  # fmt: skip
    want = (0.8, 3.2, 7.0, 9.0, 7.8, 12.2)
    assert all(math.isclose(v, w) for v, w in zip(got.values(), want, strict=True)), got
    assert math.isclose(got["prompt_gpu_seconds"] + got["reply_gpu_seconds"],
                        row["further_reply_gpu_seconds"]["value"])  # fmt: skip
    multiples = [sides[k]["value"] for k in ("prompt_proving_multiple", "reply_proving_multiple",
                                             "prompt_multiple", "reply_multiple")]  # fmt: skip
    assert all(math.isclose(v, w) for v, w in zip(multiples, (70.0, 22.5, 78.0, 30.5),
                                                  strict=True)), multiples  # fmt: skip
    w = base["prompt_share"]["value"]
    for total, prompt, reply in (("further_reply_multiple", "prompt_multiple", "reply_multiple"),
                                 ("further_reply_proving_multiple", "prompt_proving_multiple",
                                  "reply_proving_multiple")):  # fmt: skip
        assert math.isclose(
            row[total]["value"], w * sides[prompt]["value"] + (1 - w) * sides[reply]["value"]
        )
    assert sides["prompt_proving_gpu_seconds"]["stats"]["n"] == 3
    assert [s["prompt_proving"] for s in sides["sessions"]] == [7.0] * 3


def test_generation_without_parts_stays_unsplit(
    tree: Tree, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same sessions with no part reported: the proving 80 GPU-s splits 40 and 40 by
    position (8 a reply each side), the generation and the totals are null."""
    three_sessions(tree, commit_end=38.0, prove_start=40.0,
                   run_edit=phases({"ids": 20.0, "prove": 80.0}, 100.5))  # fmt: skip
    serving(tree, monkeypatch)
    sides = rung_of(board(tree))["rows"][0]["sides"]
    assert (sides["generation_core"], sides["proving_core"]) == (None, None)
    assert (sides["prompt_proving_gpu_seconds"]["value"],
            sides["reply_proving_gpu_seconds"]["value"]) == (8.0, 8.0)  # fmt: skip
    for k in ("prompt_generation_gpu_seconds", "reply_gpu_seconds", "reply_multiple"):
        assert (sides[k]["value"], sides[k]["null_reason"]) == (None, "not_applicable")
    assert math.isclose(sides["prompt_proving_multiple"]["value"], 80.0)  # 8 / 0.1


def test_parts_off_the_prove_call_are_not_taken(
    tree: Tree, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Parts with whole phases 9 % off the prove call (110 s): no side figure."""
    three_sessions(tree, commit_end=38.0, prove_start=40.0, run_edit=phases(SASH, 110.0))
    serving(tree, monkeypatch)
    sides = rung_of(board(tree))["rows"][0]["sides"]
    for k in ("prompt_proving_gpu_seconds", "reply_proving_gpu_seconds"):
        assert sides[k]["value"] is None


def test_flashprove_generation_parts_inside_its_marks(
    tree: Tree, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two GPUs, prove from 35 s, AD-4 marks 40 to 90 s, replies up to 140 s: a further reply is
    210 GPU-s over 5 = 42, generation 100 (20 a reply), proving 110. `generate`'s parts 1 and
    15 s are 2 and 30 GPU-s, the rest 68 split 34 and 34: 36 and 64, 7.2 and 12.8 a reply. The
    proving has no part: 55 and 55, 11 a reply each side. Totals 18.2 and 23.8; over 0.1 and
    0.4: 182 and 59.5, and 0.2 x 182 + 0.8 x 59.5 = 84 = 42 / 0.5."""
    tree.add_system(RUNG, "flashprove", "l1-l31-8b-p512-o512")
    reported = {"float64_check": 5.0, "generate": 45.0, "generate__load": 25.0,
                "generate__prompt": 1.0, "generate__reply": 15.0, "cp_prove": 50.0}  # fmt: skip
    three_sessions(tree, system="flashprove", gpus=2, generation=(40.0, 90.0), commit_end=30.0,
                   prove_start=35.0, run_edit=phases(reported, 100.5))  # fmt: skip
    serving(tree, monkeypatch)
    sides = rung_of(board(tree))["rows"][0]["sides"]
    assert (sides["generation_core"], sides["proving_core"]) == ("adapter_phases", None)
    got = [sides[k]["value"] for k in ("prompt_generation_gpu_seconds",
           "reply_generation_gpu_seconds", "prompt_proving_gpu_seconds",
           "reply_proving_gpu_seconds", "prompt_multiple", "reply_multiple")]  # fmt: skip
    want = (7.2, 12.8, 11.0, 11.0, 182.0, 59.5)
    assert all(math.isclose(v, w) for v, w in zip(got, want, strict=True)), got


def test_no_request_a_run_leaves_the_board_without_sides(
    tree: Tree, monkeypatch: pytest.MonkeyPatch
) -> None:
    three_sessions(tree, commit_end=38.0, prove_start=40.0, run_edit=phases(SASH, 100.5))
    serving(tree, monkeypatch, s_a=None)
    rung = rung_of(board(tree))
    assert "sides" not in rung["baseline"]
    assert "sides" not in rung["rows"][0]
    whole = build_board(tree.root, RELEASE, tree.level)  # v1.0's rule: never any side
    assert "sides" not in rung_of(whole)["baseline"]


def test_no_reply_side_when_request_a_costs_as_much(
    tree: Tree, monkeypatch: pytest.MonkeyPatch
) -> None:
    three_sessions(tree, commit_end=38.0, prove_start=40.0, run_edit=phases(SASH, 100.5))
    serving(tree, monkeypatch, s_b=0.5, s_a=0.5)
    rung = rung_of(board(tree))
    base = rung["baseline"]["sides"]
    assert base["reply_gpu_seconds_per_reply"]["value"] is None
    assert base["cause"] is not None
    sides = rung["rows"][0]["sides"]
    assert sides["reply_multiple"]["value"] is None
    assert math.isclose(sides["prompt_multiple"]["value"], 7.8 / 0.5)
