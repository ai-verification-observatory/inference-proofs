"""FlashProve adapter image on CPU (#68): the Dockerfile rules and `info`/`setup`, in process and
against the out.json `info` returned by the built image (fixtures/info.json)."""

import importlib.machinery
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from iproofs.provenance import dockerfile_problems
from iproofs.schema import SchemaRegistry

HERE = Path(__file__).resolve().parent
SYSTEM = HERE.parent
ROOT = SYSTEM.parents[1]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
COMMIT = "9e2bdd8ff5bf9c62f18263d7dac189b0400b260c"


@pytest.fixture
def adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setenv("IPROOFS_IO", str(tmp_path))
    monkeypatch.setenv("IPROOFS_INPUTS", str(HERE / "fixtures/inputs.json"))
    loader = importlib.machinery.SourceFileLoader("flashprove", str(SYSTEM / "entrypoint"))
    spec = importlib.util.spec_from_loader("flashprove", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def run(adapter: ModuleType, sub: str) -> dict[str, Any]:
    io = adapter.host("/io")
    job = {"schema": "adapter-job/1", "contract": "adapter/1", "subcommand": sub, "run_id": "r",
           "workload": {"id": "fp-maverick-w1024-b1", "version": 1}}  # fmt: skip
    (io / "job.json").write_text(json.dumps(job))
    adapter.sys.argv = ["entrypoint", sub, "/io/job.json", "/io/out.json"]
    assert adapter.main() == 0
    out: dict[str, Any] = json.loads((io / "out.json").read_text())
    assert REGISTRY.errors("adapter-out/1", out) == []
    return out


def test_dockerfile_rules() -> None:
    lock = (SYSTEM / "inputs.lock").read_text()
    assert dockerfile_problems((SYSTEM / "Dockerfile").read_text(), lock) == []


def test_upstream_pinned_and_checked() -> None:
    """INV-ADAPTER-2: the fetch stage adds the pin and checks it with `git rev-parse HEAD`."""
    dockerfile = (SYSTEM / "Dockerfile").read_text()
    assert f"FlashProve.git#{COMMIT}" in dockerfile
    assert f'test "$(git -C /src rev-parse HEAD)" = {COMMIT}' in dockerfile
    assert "patch" not in dockerfile.split("FROM fetch", 1)[1]  # B4


def test_info(adapter: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IPROOFS_ADAPTER_COMMIT", "a" * 40)
    monkeypatch.setenv("IPROOFS_ADAPTER_DIRTY", "false")
    out = run(adapter, "info")
    assert (out["system"], out["upstream_commit"]) == ("flashprove", COMMIT)
    assert out["profile"] == "prover-h100"
    assert out["workloads"] == ["fp-maverick-w1024-b1", "fp-maverick-w1024-b24",
                                "l1-maverick-p512-o512"]  # fmt: skip
    assert (out["adapter_commit"], out["adapter_dirty"]) == ("a" * 40, False)
    assert out["optional_subcommands"] == ["perturb"]
    names = [i["name"] for i in out["image_inputs"]]
    assert names == [
        "FlashProve",
        "wikitext-2-raw-v1-train",
        "llama2-tokenizer",
        "llama4-tokenizer",
    ]


def test_image_info_fixture() -> None:
    """`info` as the built image returned it: valid, with the lock's inputs and the toolchains."""
    out = json.loads((HERE / "fixtures/info.json").read_text())
    assert REGISTRY.errors("adapter-out/1", out) == []
    assert out["upstream_commit"] == COMMIT
    locked = [ln.split("\t") for ln in (SYSTEM / "inputs.lock").read_text().splitlines()
              if ln and not ln.startswith("#")]  # fmt: skip
    assert [[i["name"], i["url"], i["digest"]] for i in out["image_inputs"]] == locked
