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
