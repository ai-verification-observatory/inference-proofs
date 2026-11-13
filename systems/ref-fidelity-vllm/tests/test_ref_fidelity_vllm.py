"""ref-fidelity-vllm on CPU: `reference` and `other_model` calls against a stand-in for vLLM, so
the replies' order, the rerun's reversed batches and the status record are checked without a
GPU."""

import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import ClassVar

import pytest

from iproofs.schema import SchemaRegistry

HERE = Path(__file__).resolve().parent
SYSTEM = HERE.parent
ROOT = SYSTEM.parents[1]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
N = 8


class FakeLLM:
    """Replies that depend on the prompt only (a deterministic engine), and records the order
    the prompts were sent in."""

    sent: ClassVar[list[list[list[int]]]] = []

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    def generate(self, inputs: list[dict], params: object, use_tqdm: bool) -> list[object]:
        FakeLLM.sent.append([i["prompt_token_ids"] for i in inputs])
        n = int(params.max_tokens)  # type: ignore[attr-defined]
        return [
            SimpleNamespace(outputs=[SimpleNamespace(token_ids=[i["prompt_token_ids"][0]] * n)])
            for i in inputs
        ]


@pytest.fixture
def adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    for name, sub in (("IPROOFS_IO", "io"), ("IPROOFS_MODELS", "models")):
        (tmp_path / sub).mkdir()
        monkeypatch.setenv(name, str(tmp_path / sub))
    fake = ModuleType("fake_vllm")
    fake.LLM = FakeLLM  # type: ignore[attr-defined]
    fake.SamplingParams = SimpleNamespace  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fake_vllm", fake)
    monkeypatch.setenv("IPROOFS_VLLM_FAKE", "fake_vllm")
    monkeypatch.setenv("IPROOFS_SYSTEM_YAML", str(SYSTEM / "system.yaml"))
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0,1,2,3,4,5,6,7")
    FakeLLM.sent = []
    loader = importlib.machinery.SourceFileLoader("ref_fidelity_vllm", str(SYSTEM / "entrypoint"))
    spec = importlib.util.spec_from_loader("ref_fidelity_vllm", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    io = tmp_path / "io"
    (io / "prompts.jsonl").write_text("".join(json.dumps([10 + i, 1, 2]) + "\n" for i in range(5)))
    return module


def job(call: str, controls: list[dict]) -> dict:
    return {
        "subcommand": "prove",
        "call": call,
        "model_dir": "/models",
        "dtype": "bf16",
        "prompts_file": "/io/prompts.jsonl",
        "output_tokens": N,
        "controls": controls,
        "replies": True,
    }


def test_reference_and_rerun_in_prompt_order(adapter: ModuleType, tmp_path: Path) -> None:
    controls = [
        {"id": "reference-2", "kind": "honest", "recipe": "rerun"},
        {"id": "q8_0", "kind": "honest", "recipe": "quantize", "type": "Q8_0"},
    ]
    out = adapter.prove(job("reference", controls))
    assert REGISTRY.errors("adapter-out/1", out) == []
    io = tmp_path / "io" / "fidelity"
    ref = [json.loads(x) for x in (io / "replies/reference.jsonl").read_text().splitlines()]
    rerun = [json.loads(x) for x in (io / "replies/reference-2.jsonl").read_text().splitlines()]
    assert ref == rerun == [[10 + i] * N for i in range(5)]
    assert [p[0] for p in FakeLLM.sent[1]] == [14, 13, 12, 11, 10]  # the rerun's batches differ
    status = json.loads((io / "status.json").read_text())
    assert status["reference"]["status"] == "ok"
    assert status["controls"]["reference-2"]["status"] == "ok"
    assert status["controls"]["q8_0"]["status"] == "failed"
    assert "quantize" in status["controls"]["q8_0"]["cause"]
    assert status["kl_base"]["status"] == "failed"


def test_other_model_call(adapter: ModuleType, tmp_path: Path) -> None:
    adapter.prove(
        job("other_model", [{"id": "smaller-model", "kind": "damaged", "recipe": "other_model"}])
    )
    status = json.loads((tmp_path / "io/fidelity/status.json").read_text())
    assert status["controls"]["smaller-model"]["status"] == "ok"
    assert (tmp_path / "io/fidelity/replies/smaller-model.jsonl").is_file()


def test_info_validates(adapter: ModuleType) -> None:
    out = adapter.info({"subcommand": "info"})
    assert REGISTRY.errors("adapter-out/1", out) == []
    assert out["upstream_commit"] == "5df63a7203cdb9328d824a27b682e77c7b9928be"


# ---------------------------------------------------------------- teacher-forced (FI-10 to FI-13)

REPLY_LEN = 4


class ForcedLLM(FakeLLM):
    """`prompt_logprobs` of a stand-in model over a vocabulary of 50: the top token after a
    token t is t + 1 at log 1/2, with t + 2 at log 1/4 and the lower ids 0 to 2 at log 1/16.
    As vLLM does, each entry lists the sequence's own token first, then the most probable
    ones, and the first entry is None. `flat` returns vLLM's flat container form."""

    flat = False
    asked: ClassVar[list[object]] = []

    def generate(self, inputs: list[dict], params: object, use_tqdm: bool) -> list[object]:
        import math  # noqa: PLC0415

        FakeLLM.sent.append([i["prompt_token_ids"] for i in inputs])
        ForcedLLM.asked.append(params)
        k = int(params.prompt_logprobs)  # type: ignore[attr-defined]
        outs = []
        for i in inputs:
            seq = i["prompt_token_ids"]
            entries: list[dict | None] = [None]
            for j in range(1, len(seq)):
                t = seq[j - 1]
                dist = {t + 1: math.log(0.5), t + 2: math.log(0.25), 2: math.log(1 / 16),
                        0: math.log(1 / 16), 1: math.log(1 / 16)}  # fmt: skip
                top = list(dist.items())[:k]
                own = dist.get(seq[j], math.log(1e-6))
                entries.append({seq[j]: SimpleNamespace(logprob=own),
                                **{v: SimpleNamespace(logprob=lp) for v, lp in top}})  # fmt: skip
            found: object = entries
            if self.flat:
                found = SimpleNamespace(start_indices=[], end_indices=[], token_ids=[], logprobs=[])
                for e in entries:
                    found.start_indices.append(len(found.token_ids))  # type: ignore[attr-defined]
                    for v, lp in (e or {}).items():
                        found.token_ids.append(v)  # type: ignore[attr-defined]
                        found.logprobs.append(lp.logprob)  # type: ignore[attr-defined]
                    found.end_indices.append(len(found.token_ids))  # type: ignore[attr-defined]
            outs.append(SimpleNamespace(prompt_logprobs=found, outputs=[]))
        return outs


def forced_job(call: str, controls: list[dict], top_k: int, tmp_path: Path) -> dict:
    # prompt i is [10 + i, 1, 2]; the reference reply continues 3, 4, 9, 10: the stand-in's top
    # token (the last token plus 1) agrees at positions 0, 1 and 3 and gives 5 at position 2
    replies = [[3, 4, 9, 10] for _ in range(5)]
    (tmp_path / "io/reference.jsonl").write_text("".join(json.dumps(r) + "\n" for r in replies))
    return {**job(call, controls),
            "teacher_forced": {"replies_file": "/io/reference.jsonl", "top_k": top_k}}  # fmt: skip


@pytest.mark.parametrize("flat", [False, True])
def test_teacher_forced_reference_and_rerun(
    adapter: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flat: bool
) -> None:
    import math  # noqa: PLC0415
    import struct  # noqa: PLC0415

    monkeypatch.setattr(sys.modules["fake_vllm"], "LLM", ForcedLLM)
    monkeypatch.setattr(ForcedLLM, "flat", flat)
    ForcedLLM.asked = []
    controls = [{"id": "reference-2", "kind": "honest", "recipe": "rerun"},
                {"id": "q8_0", "kind": "honest", "recipe": "quantize", "type": "Q8_0"}]  # fmt: skip
    out = adapter.prove(forced_job("reference", controls, 3, tmp_path))
    assert REGISTRY.errors("adapter-out/1", out) == []
    io = tmp_path / "io"
    status = json.loads((io / "fidelity/status.json").read_text())
    assert status["reference"]["status"] == "ok"
    assert status["controls"]["reference-2"]["status"] == "ok"
    assert status["controls"]["q8_0"]["status"] == "failed"
    for ident in ("reference", "reference-2"):
        lines = (io / f"fidelity/teacher-forced/top/{ident}.jsonl").read_text().splitlines()
        assert [json.loads(x) for x in lines] == [[3, 4, 5, 10]] * 5
    # the whole sequence goes in as token ids; the rerun in reverse order
    assert FakeLLM.sent[0][0] == [10, 1, 2, 3, 4, 9, 10]
    assert [s[0] for s in FakeLLM.sent[1]] == [14, 13, 12, 11, 10]
    params = ForcedLLM.asked[0]
    assert (params.prompt_logprobs, params.max_tokens, params.temperature) == (5, 1, 0.0)  # type: ignore[attr-defined]
    assert not (io / "fidelity/replies").exists()
    blob = (io / "fidelity/teacher-forced/raw/reference/2.topk").read_bytes()
    assert struct.unpack("<II", blob[4:12]) == (REPLY_LEN, 3)
    ids = struct.unpack("<12i", blob[12:60])
    lps = struct.unpack("<12f", blob[60:])
    # position 2 follows token 4: 5 at 1/2, 6 at 1/4, then the lowest id of the three at 1/16
    assert ids[6:9] == (5, 6, 0)
    assert lps[6:9] == pytest.approx((math.log(0.5), math.log(0.25), math.log(1 / 16)))
    # position 0 follows the prompt's last token, 2: its own token 3 is the top one, once
    assert ids[0:3] == (3, 4, 0)


def test_engine_starts_with_the_cap_on_listed_tokens(
    adapter: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys.modules["fake_vllm"], "LLM", ForcedLLM)
    made: list[ForcedLLM] = []
    real = adapter.Engine

    def engine(*args: object) -> object:
        made.append(real(*args).llm)
        return real(*args)

    monkeypatch.setattr(adapter, "make_engine", engine)
    with pytest.raises(SystemExit, match="256 were asked for"):  # the stand-in lists 5
        adapter.prove(forced_job("reference", [], 256, tmp_path))
    assert made[0].kwargs["max_logprobs"] == 256
    assert made[0].kwargs["max_model_len"] == 3 + 4 + 64
    assert made[0].kwargs["enable_prefix_caching"] is False


def test_fewer_listed_tokens_than_asked_fails_the_pass(adapter: ModuleType) -> None:
    with pytest.raises(RuntimeError, match="lists 2 tokens"):
        adapter.ordered([4, 4, 9], [-0.5, -0.5, -2.0], 3)
    assert adapter.ordered([9, 4, 7, 4], [-0.5, -0.5, -2.0, -0.5], 2) == ([4, 9], [-0.5, -0.5])
