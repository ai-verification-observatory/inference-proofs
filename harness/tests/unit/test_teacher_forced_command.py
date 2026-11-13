"""`iproofs fidelity run --teacher-forced` and `score --part teacher-forced`: the parts that
decide what a record may be used for (RFC-0018 FI-14, FI-15)."""

import json
from math import log
from pathlib import Path

import pytest

from iproofs.commands import teacher_forced as cmd
from iproofs.commands.fidelity import Call
from iproofs.errors import IProofsError
from iproofs.provenance import file_digest
from iproofs.teacher_forced import Pass, board_block, score_pass, write_topk

D = "sha256:" + "11" * 32


def run_record(name: str, ids: list[str], prompts: int = 3, **more: object) -> dict[str, object]:
    return {
        "name": name,
        "ids": ids,
        "prompts": prompts,
        "of": 3,
        "not_run": {},
        "level": {"digest": D},
        "prompts_digest": D,
        "reference": {"digest": D},
        **more,
    }


def test_a_pass_is_read_only_from_a_run_of_every_prompt(tmp_path: Path) -> None:
    (tmp_path / "top").mkdir()
    (tmp_path / "top/sash.jsonl").write_text('[1,2]\n{"failed":"refused"}\n[3,4]\n')
    trial = ("run-trial.json", run_record("trial", ["sash"], prompts=1))
    full = ("run-sash.json", run_record("sash", ["sash"]))
    found, run = cmd._pass_of("sash", tmp_path, [trial], "ref", 3, D, D, D)
    assert found.tops is None
    assert found.cause == "not run on every prompt: run-trial.json ran 1 of 3"
    assert run is None
    found, run = cmd._pass_of("sash", tmp_path, [trial, full], "ref", 3, D, D, D)
    assert found.tops == ((1, 2), None, (3, 4))
    assert found.causes == {1: "refused"}
    assert run == "ref/run-sash.json"


def test_a_run_of_other_prompts_or_another_reference_is_refused(tmp_path: Path) -> None:
    other = "sha256:" + "22" * 32
    bad = ("run-x.json", run_record("x", ["q8_0"], reference={"digest": other}))
    with pytest.raises(IProofsError, match="other reference replies"):
        cmd._pass_of("q8_0", tmp_path, [bad], "ref", 3, D, D, D)


def test_a_control_not_run_keeps_its_cause(tmp_path: Path) -> None:
    why = "not run: left out of this job (--only)"
    left_out = ("run-controls.json", run_record("controls", [], not_run={"q2_k": why}))
    found, _ = cmd._pass_of("q2_k", tmp_path, [left_out], "ref", 3, D, D, D)
    assert found.cause == why
    # the vLLM run of the rung leaves it to the controls part; the part's own word stays
    other = ("run-vllm.json", run_record("vllm", [], not_run={"q2_k": "run in llama.cpp"}))
    found, _ = cmd._pass_of("q2_k", tmp_path, [left_out, other], "ref", 3, D, D, D)
    assert found.cause == why
    status = {"controls": {"q8_0": {"status": "failed", "cause": "llama-quantize exited 1"}}}
    (tmp_path / "status-controls.json").write_text(json.dumps(status))
    found, _ = cmd._pass_of("q8_0", tmp_path, [left_out], "ref", 3, D, D, D)
    assert found.cause == "llama-quantize exited 1"


def test_only_keeps_the_named_controls_and_the_reference_call() -> None:
    calls: list[Call] = [
        ("reference", Path("m"), [{"id": "reference-2"}, {"id": "q8_0"}], True, {}),
        ("other_model", Path("o"), [{"id": "smaller-model"}], True, {}),
    ]
    not_run: dict[str, str] = {}
    kept = cmd._only(calls, not_run, {"q8_0"})
    assert [(c[0], [x["id"] for x in c[2]]) for c in kept] == [("reference", ["q8_0"])]
    assert not_run == {"reference-2": cmd.LEFT_OUT, "smaller-model": cmd.LEFT_OUT}


def test_prover_files_must_be_the_ones_the_sessions_record(tmp_path: Path) -> None:
    given = tmp_path / "given"
    given.mkdir()
    (given / "attn_ranges.json").write_text("{}")
    good = file_digest(given / "attn_ranges.json")
    placed, record = cmd._place_prover_files(
        given, {"prover_files": {"attn_ranges.json": [good]}}, tmp_path / "io"
    )
    assert placed == ["/io/state/prover-files/attn_ranges.json"]
    assert record["files"] == {"attn_ranges.json": good}
    with pytest.raises(IProofsError, match="the counted sessions record"):
        cmd._place_prover_files(given, {"prover_files": {"attn_ranges.json": [D]}}, tmp_path / "x")
    # sessions that disagree among themselves on a file match no file
    with pytest.raises(IProofsError, match="the counted sessions record"):
        cmd._place_prover_files(given, {"prover_files": {"attn_ranges.json": [D, good]}},
                                tmp_path / "y")  # fmt: skip


def test_kl_is_measured_from_the_lists_and_the_board_recomputes_everything(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "raw"
    for name, q in (("reference", 0.5), ("sash", 0.25)):
        (raw / name).mkdir(parents=True)
        for i in range(2):
            write_topk(raw / name / f"{i}.topk", [([1, 2], [log(q), log(1 - q)])] * 4)
    values = cmd._measure(tmp_path, raw, ["q8_0", "sash"], 2)
    want = 0.5 * log(2) + 0.5 * log(2 / 3)
    assert values["engines"]["sash"]["per_prompt"] == pytest.approx([want, want], abs=1e-6)
    assert "q8_0" not in values["engines"]  # no lists stored for it
    assert values["reference"]["lists"].startswith("sha256:")
    with pytest.raises(IProofsError, match="no lists of the reference"):
        cmd._measure(tmp_path, tmp_path / "nothing", ["sash"], 2)

    # the board's block: scores from the stored top tokens, or it stops
    reference = [[1, 1, 1, 1], [2, 2, 2, 2]]
    top = tmp_path / "sash.jsonl"
    top.write_text("[1,1,1,0]\n[2,2,2,2]\n")
    scored = score_pass(Pass("sash", ((1, 1, 1, 0), (2, 2, 2, 2)), {}), reference, system=True)
    doc = {"n": 2, "positions": 4, "measure": {"unit": "agreeing positions", "label": "l",
                                               "alpha": 0.05},
           "kl": {"top_k": 256}, "reference_pass": None, "controls": [],
           "rows": {"sash": {**scored.record(), "run": "r", "computed_by": "c", "label": "l",
                             "kl": None, "kl_note": "not measured", "tests": []}}}  # fmt: skip
    block = board_block(doc, "p", {"sash": top}, reference)
    rows: dict[str, dict[str, object]] = block["rows"]  # type: ignore[assignment]
    assert (rows["sash"]["mean"], rows["sash"]["median"], rows["sash"]["n"]) == (3.5, 3.5, 2)
    top.write_text("[1,1,1,1]\n[2,2,2,2]\n")  # the stored top tokens now say 4 and 4
    with pytest.raises(ValueError, match="not the ones its stored top tokens give"):
        board_block(doc, "p", {"sash": top}, reference)
