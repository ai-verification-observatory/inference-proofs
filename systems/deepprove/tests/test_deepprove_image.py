"""DeepProve adapter image on CPU: the Dockerfile rules and `info`/`setup`, in process."""

from pathlib import Path
from types import ModuleType

import pytest
from deepprove_fixtures import ROOT, SYSTEM, load, run_step

from iproofs.provenance import dockerfile_problems
from iproofs.schema import SchemaRegistry

COMMIT = "9d1a53e2ef49ffa2c902b8689cd3c58057a4e662"
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")


@pytest.fixture
def adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    return load(tmp_path, monkeypatch)


def test_dockerfile_rules() -> None:
    lock = (SYSTEM / "inputs.lock").read_text()
    assert dockerfile_problems((SYSTEM / "Dockerfile").read_text(), lock) == []


def test_upstream_pinned_and_checked() -> None:
    """INV-ADAPTER-2: the fetch stage adds the pin and checks it with `git rev-parse HEAD`;
    B4: nothing after the fetch stage edits upstream source."""
    dockerfile = (SYSTEM / "Dockerfile").read_text()
    assert f"deep-prove.git#{COMMIT}" in dockerfile
    assert f'test "$(git -C /src rev-parse HEAD)" = {COMMIT}' in dockerfile
    build = dockerfile.split("FROM fetch", 1)[1]
    assert "patch" not in build
    assert "sed " not in build
    assert "strace=" in dockerfile  # RFC-0018 CH-4


def test_info_and_setup(adapter: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IPROOFS_ADAPTER_COMMIT", "a" * 40)
    monkeypatch.setenv("IPROOFS_ADAPTER_DIRTY", "false")
    out = run_step(adapter, "info")
    assert (out["system"], out["upstream_commit"]) == ("deepprove", COMMIT)
    assert out["workloads"] == ["l1-gpt2-p512-o512"]
    assert out["optional_subcommands"] == ["mutate_reply"]
    assert (out["adapter_commit"], out["adapter_dirty"]) == ("a" * 40, False)
    assert [i["name"] for i in out["image_inputs"]] == ["deep-prove", "rust-nightly-2026-01-27"]
    assert run_step(adapter, "setup")["ready"] is True
