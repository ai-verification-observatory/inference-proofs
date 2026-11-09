"""ref-recompute on CPU (INV-ADAPTER-9): the teacher-forced outputs builder and the release
protocol, against argmax tokens captured once on a GPU host (fixtures/capture, see its README),
then the harness's comparison of those tokens with the claims (RC-3, RC-5)."""

import importlib.machinery
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any, ClassVar

import pytest

from iproofs.provenance import dockerfile_problems
from iproofs.runner import agreement
from iproofs.schema import SchemaRegistry

HERE = Path(__file__).resolve().parent
SYSTEM = HERE.parent
ROOT = SYSTEM.parents[1]
CAPTURE = HERE / "fixtures/capture"
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")


@pytest.fixture
def adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    for name, sub in (("IPROOFS_IO", "io"), ("IPROOFS_MODELS", "models")):
        (tmp_path / sub).mkdir()
        monkeypatch.setenv(name, str(tmp_path / sub))
    monkeypatch.setenv("IPROOFS_SYSTEM_YAML", str(SYSTEM / "system.yaml"))
    entrypoint = str(SYSTEM.parent / "ref-serve/entrypoint")  # the image's entrypoint
    loader = importlib.machinery.SourceFileLoader("ref_recompute", entrypoint)
    spec = importlib.util.spec_from_loader("ref_recompute", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class Replay:
    """The engine, replaced by argmax tokens captured from it for the same prompt and claim."""

    calls: ClassVar[list[int]] = []

    def __init__(self, model: str, args: list[str]) -> None:
        prompts = (CAPTURE / "prompts.jsonl").read_text().splitlines()
        claims = (CAPTURE / "claimed.jsonl").read_text().splitlines()
        out = json.loads((CAPTURE / "out.json").read_text())["proofs"]
        rows = zip(prompts, claims, out, strict=True)
        self.known = {(p, c): o["claimed_output"] for p, c, o in rows}

    def argmax(self, prompt: list[int], claimed: list[int]) -> list[int]:
        Replay.calls.append(len(prompt) + len(claimed))
        return self.known[json.dumps(prompt), json.dumps(claimed)]


def prove_job(size: int, batches: int, *, claims: bool = True) -> dict[str, Any]:
    job = {"schema": "adapter-job/1", "contract": "adapter/1", "subcommand": "prove",
           "run_id": "2026-11-04-ref-recompute-sash-l31-8b-c1024-prover-h100-1",
           "workload": {"id": "sash-l31-8b-c1024", "version": 1},
           "shape": {"prompt_tokens": 1024, "output_tokens": 64, "batch_size": size,
                     "batches_per_session": batches, "context_window": 1088},
           "model_dir": "/models", "prompts_file": "/io/prompts.jsonl", "batch_size": size,
           "batches": batches, "control": False, "commitment_id": "not_applicable",
           "prover_files": []}  # fmt: skip
    return job | ({"claims_file": "/io/claimed.jsonl"} if claims else {})


def run(adapter: ModuleType, doc: dict[str, Any]) -> dict[str, Any]:
    io = Path(adapter.host("/io"))
    for name in ("prompts.jsonl", "claimed.jsonl"):
        (io / name).write_text((CAPTURE / name).read_text())
    (io / "job.json").write_text(json.dumps(doc))
    adapter.sys.argv = ["entrypoint", "prove", "/io/job.json", "/io/out.json"]
    assert adapter.main() == 0
    out: dict[str, Any] = json.loads((io / "out.json").read_text())
    assert REGISTRY.errors("adapter-job/1", doc) == []
    assert REGISTRY.errors("adapter-out/1", out) == []
    return out


def test_out_json_fixture(adapter: ModuleType) -> None:
    """The captured GPU run, replayed request by request (RC-2), released per request (RC-4)."""
    adapter.make_engine = Replay
    Replay.calls = []
    out = run(adapter, prove_job(1, 2))
    assert out["proofs"] == json.loads((CAPTURE / "out.json").read_text())["proofs"]
    assert Replay.calls == [1024 + 64, 1024 + 64]  # one forward pass over prompt plus claim
    io = Path(adapter.host("/io"))
    released = json.loads((io / "proofs/req-1/outputs.json").read_text())
    assert released == {"request_index": 1, "argmax": out["proofs"][1]["claimed_output"]}
    assert sorted(p.name for p in (io / "proofs").iterdir()) == ["req-0", "req-1"]


def test_captured_agreement() -> None:
    """RC-3 and RC-7 on the captured run: request 0 claims the engine's own greedy output and
    every position agrees; request 1 claims it with token 5 changed. Position 5 disagrees, and
    so does position 6, because the claimed prefix it is fed now holds the changed token."""
    out = json.loads((CAPTURE / "out.json").read_text())["proofs"]
    claims = [json.loads(line) for line in (CAPTURE / "claimed.jsonl").read_text().splitlines()]
    pairs = zip(out, claims, strict=True)
    found = [agreement(p["claimed_output"], c, p["proof_id"]) for p, c in pairs]
    assert found == [
        {"agree": 64, "disagree": 0, "first_disagreement": None},
        {"agree": 62, "disagree": 2, "first_disagreement": 5},
    ]


def test_batch_size_one_always(adapter: ModuleType) -> None:
    """RC-2: a batch-24 workload is still checked one request at a time."""
    adapter.make_engine = Replay
    Replay.calls = []
    run(adapter, prove_job(2, 1))
    assert len(Replay.calls) == 2


def test_claims_required(adapter: ModuleType) -> None:
    adapter.make_engine = Replay
    with pytest.raises(SystemExit, match=r"names no claims_file"):
        run(adapter, prove_job(1, 2, claims=False))


def test_dockerfile_rules() -> None:
    lock = (SYSTEM / "inputs.lock").read_text()
    assert dockerfile_problems((SYSTEM / "Dockerfile").read_text(), lock) == []
    # the same engine image as ref-serve; the GGUF plugin is recompute's only (RFC-0015 SRV-6)
    assert "vllm_gguf_plugin-0.0.5" in lock
    assert "vllm_gguf_plugin" not in (SYSTEM.parent / "ref-serve/inputs.lock").read_text()
