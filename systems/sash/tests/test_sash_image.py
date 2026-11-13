"""SASH adapter image on CPU (#64): the Dockerfile rules and `info`/`setup`, in process and
against the out.json `info` returned by the built image (fixtures/info.json)."""

import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from sash_fixtures import load, run_step

from iproofs.provenance import dockerfile_problems
from iproofs.schema import SchemaRegistry

HERE = Path(__file__).resolve().parent
SYSTEM = HERE.parent
ROOT = SYSTEM.parents[1]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
COMMIT = "4f41667297430a598165c4a8604258fe37d952ae"
Step = Callable[..., dict[str, Any]]


@pytest.fixture
def adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    return load(tmp_path, monkeypatch)


@pytest.fixture
def step(adapter: ModuleType) -> Step:
    return lambda sub, **fields: run_step(adapter, sub, **fields)


def test_dockerfile_rules() -> None:
    lock = (SYSTEM / "inputs.lock").read_text()
    assert dockerfile_problems((SYSTEM / "Dockerfile").read_text(), lock) == []


def test_upstream_pinned_and_checked() -> None:
    """INV-ADAPTER-2: the fetch stage adds the pin and checks it with `git rev-parse HEAD`."""
    dockerfile = (SYSTEM / "Dockerfile").read_text()
    assert f"zk-inference-prover.git#{COMMIT}" in dockerfile
    assert f'test "$(git -C /src rev-parse HEAD)" = {COMMIT}' in dockerfile
    assert "patch" not in dockerfile.split("FROM fetch", 1)[1]  # B4


def test_info_and_setup(step: Step, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IPROOFS_ADAPTER_COMMIT", "a" * 40)
    monkeypatch.setenv("IPROOFS_ADAPTER_DIRTY", "false")
    out = step("info")
    assert (out["system"], out["upstream_commit"]) == ("sash", COMMIT)
    assert out["profile"] == "prover-h100"
    assert out["workloads"] == ["sash-l31-8b-c4096", "sash-l31-8b-c1024", "l1-l31-8b-p512-o512"]
    assert (out["adapter_commit"], out["adapter_dirty"]) == ("a" * 40, False)
    names = [i["name"] for i in out["image_inputs"]]
    assert names == ["zk-inference-prover", "rust-nightly-2025-07-14"]
    assert step("setup")["ready"] is True


def test_image_info_fixture() -> None:
    """`info` as the built image returned it: valid, with the lock's inputs and the toolchains."""
    out = json.loads((HERE / "fixtures/info.json").read_text())
    assert REGISTRY.errors("adapter-out/1", out) == []
    assert out["upstream_commit"] == COMMIT
    locked = [ln.split("\t") for ln in (SYSTEM / "inputs.lock").read_text().splitlines()
              if ln and not ln.startswith("#")]  # fmt: skip
    assert [[i["name"], i["url"], i["digest"]] for i in out["image_inputs"]] == locked


def test_vendored_crates_readable_by_the_adapter() -> None:
    """prove builds the CUDA library as uid 10001; some crate archives hold owner-only files."""
    assert "chmod -R a+rX /opt/cargo" in (SYSTEM / "Dockerfile").read_text()
