"""Shared fixtures: the DeepProve entrypoint loaded in process, /io and /models on tmp dirs.

Test modules wrap these in their own fixtures: a conftest.py here would shadow
harness/tests/conftest.py, which tests import as `conftest`."""

import importlib.machinery
import importlib.util
import json
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from iproofs.schema import SchemaRegistry

HERE = Path(__file__).resolve().parent
SYSTEM = HERE.parent
ROOT = SYSTEM.parents[1]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
RUN_ID = "2026-11-11-deepprove-l1-gpt2-p512-o512-prover-cpu-hosted-1"
SHAPE = {"prompt_tokens": 512, "output_tokens": 512, "batch_size": 1, "batches_per_session": 5,
         "context_window": 1024}  # fmt: skip


def vocab() -> dict[str, int]:
    """GPT-2's 256 single-byte tokens (ids 0 to 255, in bytes_to_unicode order), the end token,
    and two whole-word tokens of the real vocabulary ("Hello" 15496, "Ġworld" 995)."""
    bs = [*range(0x21, 0x7F), *range(0xA1, 0xAD), *range(0xAE, 0x100)]
    cs = list(bs)
    for n, b in enumerate(b for b in range(256) if b not in bs):
        bs.append(b)
        cs.append(256 + n)
    return {**{chr(c): i for i, c in enumerate(cs)}, "Hello": 15496, "Ġworld": 995,
            "<|endoftext|>": 50256}  # fmt: skip


def load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    io, models = tmp_path / "io", tmp_path / "models"
    io.mkdir()
    models.mkdir()
    for name in ("model.safetensors", "config.json", "tokenizer.json"):
        (models / name).write_bytes(name.encode())  # stand-ins: the stub never reads them
    (models / "vocab.json").write_text(json.dumps(vocab()))
    stub = HERE / "deepprove_stub.py"
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    inputs = tmp_path / "inputs.json"  # what the image's build writes from inputs.lock (B5)
    subprocess.run([sys.executable, str(SYSTEM.parent / "fake/write_inputs.py"),
                    str(SYSTEM / "inputs.lock"), str(inputs)], check=True)  # fmt: skip
    monkeypatch.setenv("IPROOFS_IO", str(io))
    monkeypatch.setenv("IPROOFS_MODELS", str(models))
    monkeypatch.setenv("IPROOFS_INPUTS", str(inputs))
    monkeypatch.setenv("IPROOFS_DEEPPROVE_EXEC", str(stub))
    for var in ("IPROOFS_DEEPPROVE_STUB_EOS", "IPROOFS_DEEPPROVE_STUB_DROP"):
        monkeypatch.delenv(var, raising=False)
    loader = importlib.machinery.SourceFileLoader("deepprove", str(SYSTEM / "entrypoint"))
    spec = importlib.util.spec_from_loader("deepprove", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def run_step(adapter: ModuleType, sub: str, **fields: Any) -> dict[str, Any]:
    """Write a schema-valid job.json, run one subcommand in process, return its schema-checked
    out.json."""
    io = adapter.host("/io")
    job = {"schema": "adapter-job/1", "contract": "adapter/1", "subcommand": sub, "run_id": RUN_ID,
           "workload": {"id": "l1-gpt2-p512-o512", "version": 1}, "control": False,
           "shape": SHAPE, **fields}  # fmt: skip
    assert REGISTRY.errors("adapter-job/1", job) == []
    (io / "job.json").write_text(json.dumps(job))
    adapter.sys.argv = ["entrypoint", sub, "/io/job.json", "/io/out.json"]
    assert adapter.main() == 0
    out: dict[str, Any] = json.loads((io / "out.json").read_text())
    assert REGISTRY.errors("adapter-out/1", out) == []
    return out


def commands(adapter: ModuleType) -> list[list[str]]:
    path = adapter.host("/io/commands.jsonl")
    lines = path.read_text().splitlines() if path.is_file() else []
    return [json.loads(line)["argv"] for line in lines]
