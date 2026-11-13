"""`iproofs fidelity run --teacher-forced` and `score --part teacher-forced`: the parts that
decide what a record may be used for (RFC-0018 FI-14, FI-15)."""

import argparse
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
    found, made = cmd._pass_of("sash", tmp_path, [trial], "ref", 3, D, D, D)
    assert found.tops is None
    assert found.cause == (
        "not run on every prompt: of 3, the stored runs cover run-trial.json prompts 0 to 0"
    )
    assert made == ()
    found, made = cmd._pass_of("sash", tmp_path, [trial, full], "ref", 3, D, D, D)
    assert found.tops == ((1, 2), None, (3, 4))
    assert found.causes == {1: "refused"}
    assert made == ("ref/run-sash.json",)


def test_shards_that_cover_every_prompt_once_make_one_pass(tmp_path: Path) -> None:
    """Three runs of prompts 0, 1 and 2 (a control split across jobs): their top tokens are
    joined in prompt order; with one shard missing, or one prompt covered twice, no pass."""
    (tmp_path / "top").mkdir()
    for lo, top in ((0, [1, 2]), (1, [3, 4]), (2, [5, 6])):
        (tmp_path / "top" / f"q8_0@{lo}.jsonl").write_text(json.dumps(top) + "\n")
    shard = [
        (f"run-controls-q8_0-{lo}.json",
         run_record(f"controls-q8_0-{lo}", ["q8_0"], prompts=1, offset=lo))
        for lo in (2, 0, 1)
    ]  # fmt: skip
    found, made = cmd._pass_of("q8_0", tmp_path, shard, "ref", 3, D, D, D)
    assert found.tops == ((1, 2), (3, 4), (5, 6))
    assert made == tuple(f"ref/run-controls-q8_0-{lo}.json" for lo in (0, 1, 2))
    joined = (tmp_path / "top" / "q8_0.jsonl").read_text().splitlines()
    assert [json.loads(x) for x in joined] == [[1, 2], [3, 4], [5, 6]]
    (tmp_path / "top" / "q8_0.jsonl").unlink()
    found, made = cmd._pass_of("q8_0", tmp_path, shard[:2], "ref", 3, D, D, D)  # prompt 1 missing
    assert (found.tops, made) == (None, ())
    assert found.cause.startswith("not run on every prompt: of 3, the stored runs cover")
    twice = [*shard, ("run-again.json", run_record("again", ["q8_0"], prompts=1, offset=1))]
    found, _ = cmd._pass_of("q8_0", tmp_path, twice, "ref", 3, D, D, D)
    assert found.tops is None


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


def _score_files(io: Path, docs: list[dict[str, object]]) -> None:
    (io / "score").mkdir(parents=True)
    for i, doc in enumerate(docs):
        (io / "score" / f"{i}.json").write_text(json.dumps(doc))


def _part(own: list[int]) -> dict[str, object]:
    return {"own": {"run": "session-1", "reply": own}, "scoring": True, "ok": False,
            "said": {"upstream_commit": "c", "adapter_commit": "a", "adapter_dirty": False},
            "image": "i@sha256:" + "0" * 64, "workload": "w", "records": [],
            "pin": {"sessions": []}, "prover_files": None}  # fmt: skip


def test_a_stopped_system_run_keeps_the_prompts_that_finished(tmp_path: Path) -> None:
    """A run cut at a deadline during `score`: request 0 is the system's own reply, requests
    1 and 2 finished (one declined by the system), request 3 never did."""
    io, out = tmp_path / "io", tmp_path / "out"
    own = [5, 6, 7]
    _score_files(io, [{"top": own}, {"top": [1, 2, 3]}, {"failed": "RangeConditionFailed"}])
    (io / "score" / "1.topk").write_bytes(b"lists")
    record: dict[str, object] = {"prompts": 4, "of": 4}
    args = argparse.Namespace(system="sys")
    ok = cmd._system_record(args, record, _part(own), io, out, 4, "stopped by signal 15")
    assert ok is False
    assert record["prompts"] == 2
    assert record["stopped"] == "stopped by signal 15; 2 of 4 prompts kept"
    assert (record["ids"], record["failed_prompts"]) == (["sys"], [1])
    assert record["own_reply_check"] == {"prompt": 0, "session": "session-1", "positions": 3,
                                         "agreeing": 3}  # fmt: skip
    lines = (out / "top" / "sys@0.jsonl").read_text().splitlines()  # a part: <id>@<first prompt>
    assert [json.loads(x) for x in lines] == [[1, 2, 3], {"failed": "RangeConditionFailed"}]
    assert (out / "raw" / "sys" / "0.topk").read_bytes() == b"lists"
    calls: list[dict[str, object]] = record["calls"]  # type: ignore[assignment]
    assert calls[-1]["exit_code"] == 124


def test_nothing_is_stored_when_the_systems_own_reply_is_not_reproduced(tmp_path: Path) -> None:
    io = tmp_path / "io"
    _score_files(io, [{"top": [5, 6, 0]}, {"top": [1, 2, 3]}])
    args = argparse.Namespace(system="sys")
    with pytest.raises(IProofsError, match="2 of 3 positions agree"):
        cmd._system_record(args, {}, {**_part([5, 6, 7]), "ok": True}, io, tmp_path / "out", 1,
                           None)  # fmt: skip
    assert not (tmp_path / "out").exists()


def test_a_finished_system_run_is_a_pass_of_every_prompt(tmp_path: Path) -> None:
    io, out = tmp_path / "io", tmp_path / "out"
    _score_files(io, [{"top": [5]}, {"top": [1]}, {"top": [2]}])
    part = {**_part([5]), "ok": True}
    record: dict[str, object] = {"prompts": 2, "of": 2}
    assert cmd._system_record(argparse.Namespace(system="sys"), record, part, io, out, 2, None)
    assert (record["prompts"], "stopped" in record, record["ids"]) == (2, False, ["sys"])
