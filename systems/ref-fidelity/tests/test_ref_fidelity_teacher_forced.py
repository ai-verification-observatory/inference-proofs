"""ref-fidelity's teacher-forced pass (RFC-0018 FI-10 to FI-13) on CPU against a scripted
llama-server: one request per reply position, token ids in, the generated token and the
`n_probs` list out."""

import json
import math
import struct
from pathlib import Path
from types import ModuleType
from typing import Any, ClassVar

import pytest
import test_ref_fidelity as shared
from test_ref_fidelity import REGISTRY, fake_tools

adapter = shared.adapter  # the fixture, under its name

V = 8
PROMPTS = [[i] * 512 for i in range(1, 4)]
# the reference reply continues each prompt by adding 1 modulo 8, which is the scripted
# reference model's own top token everywhere
REPLIES = [[(p[0] + 1 + t) % V for t in range(512)] for p in PROMPTS]
NO_LIST = 7  # the position whose token the scripted server returns without a list


class Forced:
    """`/completion` for a prompt of token ids: the top token after the last id is that id
    plus 1 modulo 8; a Q4_K_M file adds 2 at positions 99, 199, .. instead. `n_probs` 3 lists
    the top token at 1/2, the next id at 1/4 and the one after at 1/8, unsorted."""

    requests: ClassVar[list[dict[str, Any]]] = []

    def __init__(self, model: Path, slots: int, ctx: int, log: Path) -> None:
        self.kind = model.read_text().split()[-1]
        assert ctx == 512 + 512 + 64

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        assert path == "/completion"
        Forced.requests.append(body)
        prefix = body["prompt"]
        assert isinstance(prefix, list)
        assert all(isinstance(t, int) for t in prefix)
        t = len(prefix) - 512
        step = 2 if self.kind == "Q4_K_M" and t % 100 == 99 else 1
        top = (prefix[-1] + step) % V
        doc: dict[str, Any] = {"tokens": [top], "stop_type": "limit"}
        if body["n_probs"] and t != NO_LIST:
            entries = [{"id": (top + d) % V, "logprob": math.log(0.5 ** (d + 1)), "token": "x",
                        "bytes": [120]} for d in (2, 0, 1)]  # fmt: skip
            doc["completion_probabilities"] = [{"id": top, "top_logprobs": entries}]
        return doc

    def stop(self) -> None:
        pass


def job(io: Path, top_k: int) -> dict[str, object]:
    (io / "prompts.jsonl").write_text("".join(json.dumps(p) + "\n" for p in PROMPTS))
    (io / "reference.jsonl").write_text("".join(json.dumps(r) + "\n" for r in REPLIES))
    return {"subcommand": "prove", "call": "reference", "rung": "llama-3.1-8b",
            "model_dir": "/models", "dtype": "bf16", "prompts_file": "/io/prompts.jsonl",
            "output_tokens": 512, "slots": 2,
            "teacher_forced": {"replies_file": "/io/reference.jsonl", "top_k": top_k},
            "controls": [{"id": "reference-2", "kind": "honest", "recipe": "rerun"},
                         {"id": "q4_k_m", "kind": "honest", "recipe": "quantize",
                          "type": "Q4_K_M"},
                         {"id": "drop-every-4th-block", "kind": "damaged",
                          "recipe": "drop_blocks", "every": 4}]}  # fmt: skip


def tops(io: Path, ident: str) -> list[list[int]]:
    path = io / f"fidelity/teacher-forced/top/{ident}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_top_tokens_of_the_reference_and_each_control(
    adapter: ModuleType,
    tmp_path: Path,
) -> None:
    io = tmp_path / "io"
    calls = fake_tools(adapter, fail={"drop_blocks.py"})
    Forced.requests = []
    setattr(adapter, "make_server", Forced)  # noqa: B010
    out = adapter.prove(job(io, top_k=3))
    assert REGISTRY.errors("adapter-out/1", out) == []
    status = json.loads((io / "fidelity/status.json").read_text())
    assert status["reference"]["status"] == "ok"
    states = {k: v["status"] for k, v in status["controls"].items()}
    assert states == {"reference-2": "ok", "q4_k_m": "ok", "drop-every-4th-block": "failed"}
    assert tops(io, "reference") == REPLIES == tops(io, "reference-2")
    q4 = tops(io, "q4_k_m")
    assert [t for t in range(512) if q4[0][t] != REPLIES[0][t]] == [99, 199, 299, 399, 499]
    assert status["controls"]["q4_k_m"]["positions_without_list"] == [1, 1, 1]
    # each prompt is written as it finishes, and the file goes once the pass is whole
    assert not list((io / "fidelity/teacher-forced/partial").glob("*.jsonl"))
    # no reply is generated and no KL tool runs in this mode
    assert not (io / "fidelity/replies").exists()
    assert not any("llama-perplexity" in c[0] for c in calls)
    # one request per position: token ids only, one token, the slot's cache kept
    first = Forced.requests[0]
    assert first == {"prompt": first["prompt"], "n_predict": 1, "ignore_eos": False,
                     "temperature": 0.0, "samplers": ["temperature"], "n_probs": 3,
                     "cache_prompt": True, "id_slot": first["id_slot"], "return_tokens": True,
                     "stream": False}  # fmt: skip
    assert len(Forced.requests) == 3 * 3 * 512
    by_slot: dict[int, set[int]] = {}
    for r in Forced.requests[: 3 * 512]:
        by_slot.setdefault(r["id_slot"], set()).add(r["prompt"][0])
    assert by_slot == {0: {1, 3}, 1: {2}}  # prompts 0 and 2 on slot 0, prompt 1 on slot 1
    lengths = sorted(len(r["prompt"]) for r in Forced.requests[: 3 * 512] if r["prompt"][0] == 2)
    assert lengths == list(range(512, 1024))  # prompt, then prompt + reply[:t]


def test_lists_are_sorted_and_a_position_without_one_is_marked(
    adapter: ModuleType,
    tmp_path: Path,
) -> None:
    io = tmp_path / "io"
    fake_tools(adapter, fail={"drop_blocks.py"})
    setattr(adapter, "make_server", Forced)  # noqa: B010
    adapter.prove(job(io, top_k=3))
    blob = (io / "fidelity/teacher-forced/raw/reference/1.topk").read_bytes()
    assert blob[:4] == b"TFK1"
    assert struct.unpack("<II", blob[4:12]) == (512, 3)
    ids = struct.unpack("<1536i", blob[12 : 12 + 6144])
    lps = struct.unpack("<1536f", blob[12 + 6144 :])
    top = REPLIES[1][0]
    assert ids[:3] == (top, (top + 1) % V, (top + 2) % V)
    assert lps[:3] == pytest.approx((math.log(0.5), math.log(0.25), math.log(0.125)))
    assert ids[3 * NO_LIST : 3 * NO_LIST + 3] == (-1, -1, -1)


def test_top_tokens_alone_ask_for_no_list(adapter: ModuleType, tmp_path: Path) -> None:
    io = tmp_path / "io"
    fake_tools(adapter, fail={"drop_blocks.py"})
    Forced.requests = []
    setattr(adapter, "make_server", Forced)  # noqa: B010
    adapter.prove(job(io, top_k=0))
    assert {r["n_probs"] for r in Forced.requests} == {0}
    assert tops(io, "reference") == REPLIES
    assert not (io / "fidelity/teacher-forced/raw").exists()


def test_a_list_that_does_not_hold_the_generated_token_fails_the_control(
    adapter: ModuleType,
) -> None:
    entries = [{"id": 1, "logprob": -0.1}, {"id": 2, "logprob": -3.0}]
    with pytest.raises(adapter.ToolFailed, match="not its most probable"):
        adapter.listed_row(entries, 2, 2, "prompt 0, position 0")
    with pytest.raises(adapter.ToolFailed, match="listed 2 tokens"):
        adapter.listed_row(entries, 1, 3, "prompt 0, position 0")
    # equal values: the lower id first, and either may be the generated token
    tie = [{"id": 5, "logprob": -0.7}, {"id": 3, "logprob": -0.7}]
    assert adapter.listed_row(tie, 5, 2, "x") == ([3, 5], [-0.7, -0.7])


def test_a_documented_server_option_is_passed_and_recorded(
    adapter: ModuleType, tmp_path: Path
) -> None:
    """`server_args` reach llama-server's command line and the status; an option the image does
    not list fails the pass before any server starts."""
    io = tmp_path / "io"
    fake_tools(adapter, fail={"drop_blocks.py"})
    started: list[tuple[str, ...]] = []

    class WithArgs(Forced):
        def __init__(self, model: Path, slots: int, ctx: int, log: Path, *extra: str) -> None:
            super().__init__(model, slots, ctx, log)
            started.append(extra)

    setattr(adapter, "make_server", WithArgs)  # noqa: B010
    doc = job(io, top_k=0)
    doc["controls"] = []
    doc["teacher_forced"]["server_args"] = ["--swa-full"]  # type: ignore[index]
    adapter.prove(doc)
    assert started == [("--swa-full",)]
    status = json.loads((io / "fidelity/status.json").read_text())
    assert status["reference"]["server_args"] == ["--swa-full"]
    assert "--swa-full" in adapter.SERVER_ARGS
    doc["teacher_forced"]["server_args"] = ["--ctx-size", "1"]  # type: ignore[index]
    with pytest.raises(SystemExit, match="are not all among"):
        adapter.prove(doc)
    assert len(started) == 1
