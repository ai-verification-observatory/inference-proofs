"""Shared fixtures: the SASH entrypoint loaded in process, /io and /models on tmp dirs.

Test modules wrap these in their own fixtures: a conftest.py here would shadow
harness/tests/conftest.py, which tests import as `conftest`."""

import importlib.machinery
import importlib.util
import json
import stat
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from iproofs.schema import SchemaRegistry

HERE = Path(__file__).resolve().parent
SYSTEM = HERE.parent
REGISTRY = SchemaRegistry.from_tree(SYSTEM.parents[1] / "schema")


def load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    io, models = tmp_path / "io", tmp_path / "models"
    io.mkdir()
    models.mkdir()
    (models / "config.json").write_text(json.dumps({"num_hidden_layers": 2}))
    stub = HERE / "stub_upstream.py"
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("IPROOFS_IO", str(io))
    monkeypatch.setenv("IPROOFS_MODELS", str(models))
    monkeypatch.setenv("IPROOFS_INPUTS", str(HERE / "fixtures/inputs.json"))
    monkeypatch.setenv("IPROOFS_SASH_EXEC", str(stub))
    loader = importlib.machinery.SourceFileLoader("sash", str(SYSTEM / "entrypoint"))
    spec = importlib.util.spec_from_loader("sash", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


RUN_ID = "2026-11-05-sash-sash-l31-8b-c1024-prover-h100-1"


def run_step(adapter: ModuleType, sub: str, valid: bool = True, **fields: Any) -> dict[str, Any]:
    """Write job.json, run one subcommand in process, return its schema-checked out.json.
    `valid=False` writes a job the schema refuses, to test the adapter's own guard."""
    io = adapter.host("/io")
    job = {"schema": "adapter-job/1", "contract": "adapter/1", "subcommand": sub, "run_id": RUN_ID,
           "workload": {"id": "sash-l31-8b-c1024", "version": 1}, "control": False,
           "shape": {"prompt_tokens": 128, "output_tokens": 64, "batch_size": 1,
                     "batches_per_session": 1, "context_window": 192}, **fields}  # fmt: skip
    assert (REGISTRY.errors("adapter-job/1", job) == []) is valid
    (io / "job.json").write_text(json.dumps(job))
    adapter.sys.argv = ["entrypoint", sub, "/io/job.json", "/io/out.json"]
    assert adapter.main() == 0
    out: dict[str, Any] = json.loads((io / "out.json").read_text())
    assert REGISTRY.errors("adapter-out/1", out) == []
    return out
