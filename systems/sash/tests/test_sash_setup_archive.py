"""The SASH state a setup run's commit leaves, through the harness's own archive and restore
(iproofs.setups): the restored state passes the adapter's reuse check, which runs only
nvidia-smi and cuobjdump, the cargo registry link stays a link, and a reply whose emission adds
nothing proves on the restored binary without a build."""

import json
import shutil
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from sash_fixtures import load, run_step

from iproofs.provenance import file_digest
from iproofs.setups import archive_state, restore_state

PROMPT = list(range(128))
TOK = list(range(1000, 1064))


@pytest.fixture
def adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setenv("IPROOFS_SASH_STUB_TOK", json.dumps(TOK))
    return load(tmp_path, monkeypatch)


def commands(adapter: ModuleType) -> list[str]:
    path = adapter.host("/io/commands.jsonl")
    lines = path.read_text().splitlines() if path.is_file() else []
    return [json.loads(ln)["argv"][0] for ln in lines]


def setup_then_restore(adapter: ModuleType, tmp_path: Path) -> tuple[dict[str, Any], str]:
    """A setup run's commit, its /io/state archived, then a fresh /io restored from it."""
    out = run_step(adapter, "commit", model_dir="/models")
    io = adapter.host("/io")
    archive = tmp_path / "state.tar"
    archive_state(io / "state", archive)
    digest = file_digest(archive)
    shutil.rmtree(io)
    io.mkdir()
    restore_state(archive, digest, io)
    return out, digest


def test_a_restored_archive_passes_the_reuse_check_and_builds_nothing(
    adapter: ModuleType, tmp_path: Path
) -> None:
    fresh, _ = setup_then_restore(adapter, tmp_path)
    state = adapter.host("/io/state")
    assert (state / "build/cargo/registry").is_symlink()
    assert (state / "build/kernels.done").read_text() == fresh["kernels"]["build_key"]
    setup_state = {"commitment_id": fresh["commitment_id"],
                   "build_key": fresh["kernels"]["build_key"]}  # fmt: skip
    out = run_step(adapter, "commit", model_dir="/models", setup_state=setup_state)
    assert commands(adapter) == ["nvidia-smi", "cuobjdump"]
    assert [p["name"] for p in out["phases"]] == ["setup_check"]
    assert out["commitment_id"] == fresh["commitment_id"]
    before = len(commands(adapter))
    adapter.host("/io/prompts.jsonl").write_text(json.dumps(PROMPT) + "\n")
    proved = run_step(adapter, "prove", commitment_id=out["commitment_id"], model_dir="/models",
                      prover_files=out["prover_files"], prompts_file="/io/prompts.jsonl",
                      batch_size=1, batches=1)  # fmt: skip
    assert "cargo" not in commands(adapter)[before:]
    assert proved["kernels"]["replies_built"] == 0


def test_a_setup_named_by_another_commitment_is_refused_after_restore(
    adapter: ModuleType, tmp_path: Path
) -> None:
    fresh, _ = setup_then_restore(adapter, tmp_path)
    with pytest.raises(SystemExit, match="hash to"):
        run_step(adapter, "commit", model_dir="/models",
                 setup_state={"commitment_id": "sha256:" + "0" * 64})  # fmt: skip
    assert set(commands(adapter)) <= {"nvidia-smi", "cuobjdump"}
    assert fresh["commitment_id"] != "sha256:" + "0" * 64
