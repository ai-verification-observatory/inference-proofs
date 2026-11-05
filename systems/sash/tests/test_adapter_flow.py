"""commit, prove and verify end to end on CPU, every upstream process replaced by
stub_upstream.py; and the weakening-flag guard (RFC-0005 §Weakening configurations)."""

import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from sash_fixtures import load, run_step

Step = Callable[..., dict[str, Any]]
PROMPT = list(range(128))
TOK = list(range(1000, 1064))  # the ids the stub's statements state for each block


@pytest.fixture
def adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    return load(tmp_path, monkeypatch)


@pytest.fixture
def step(adapter: ModuleType) -> Step:
    return lambda sub, **fields: run_step(adapter, sub, **fields)


def commands(adapter: ModuleType) -> list[dict[str, Any]]:
    path = adapter.host("/io/commands.jsonl")
    return [json.loads(ln) for ln in path.read_text().splitlines()] if path.is_file() else []


def argvs(adapter: ModuleType, word: str) -> list[list[str]]:
    return [c["argv"] for c in commands(adapter) if word in c["argv"]]


def prove_job(commit_out: dict[str, Any]) -> dict[str, Any]:
    return {"commitment_id": commit_out["commitment_id"], "model_dir": "/models",
            "prover_files": commit_out["prover_files"], "prompts_file": "/io/prompts.jsonl",
            "batch_size": 1, "batches": 1}  # fmt: skip


@pytest.fixture
def proved(adapter: ModuleType, step: Step, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setenv("IPROOFS_SASH_STUB_TOK", json.dumps(TOK))
    adapter.host("/io/prompts.jsonl").write_text(json.dumps(PROMPT) + "\n")
    c = step("commit", model_dir="/models")
    return {"commit": c, "prove": step("prove", **prove_job(c))}


def verify(step: Step, done: dict[str, Any], claimed: list[int] = TOK) -> dict[str, Any]:
    c = done["commit"]
    return step("verify", commitment_id=c["commitment_id"], verifier_files=c["verifier_files"],
                request=PROMPT, claimed_output=claimed, proof_dir="/io/proofs/req-0")  # fmt: skip


def test_commit(adapter: ModuleType, proved: dict[str, Any]) -> None:
    c = proved["commit"]
    assert c["verifier_files"] == ["/io/state/model-roots.json", "/io/state/grid.json"]
    assert c["commitment_id"] == adapter.commitment_of(c["verifier_files"])
    grid = json.loads(adapter.host("/io/state/grid.json").read_text())
    # 128 + 64 positions in blocks of 64: 3 blocks of 2 layers and 2 head segments
    assert (grid["blocks"], grid["head_blocks"]) == (3, [1, 2])
    assert (grid["expect_layer_links"], grid["expect_token_links"]) == (5, 4)
    [roots] = argvs(adapter, "model-roots")
    assert roots[0] == "/usr/local/bin/zk-prover-simd"
    assert "--pins" in roots
    assert not adapter.host("/io/state/commit-witness").exists()


def test_prove_releases_one_grid(adapter: ModuleType, proved: dict[str, Any]) -> None:
    [proof] = proved["prove"]["proofs"]
    assert (proof["proof_id"], proof["request_index"], proof["claimed_output"]) == ("req-0", 0, TOK)
    released = adapter.host("/io/proofs/req-0")
    assert proof["parts"] == sorted(p.name for p in released.iterdir())
    assert len(proof["parts"]) == 8 * 3 + 1  # three files per segment and the plan
    assert not list(adapter.host("/io/proofs").glob(".tmp-*"))
    # the grid is proved on the rebuilt CUDA backend, never on the image's SIMD binary
    [compose] = argvs(adapter, "compose-chunks")
    assert compose[0] == "/io/state/build/t-cuda/release/zk-prover"
    assert compose[compose.index("--ser-dir") + 1] == "/io/proofs/.tmp-req-0"
    tools = [c["argv"][0] for c in commands(adapter)]
    assert tools.index("cuobjdump") < tools.index("/io/state/build/t-cuda/release/zk-prover")
    binding = json.loads(adapter.host("/io/binding.json").read_text())
    assert binding["all_bound"] is True
    assert binding["unsound_skips"] == []


def test_command_log(adapter: ModuleType, proved: dict[str, Any]) -> None:
    lines = commands(adapter)
    assert lines
    assert all(set(c) == {"argv", "cwd", "started_mono_ns", "exit_code"} for c in lines)
    flat = [a for c in lines for a in c["argv"]]
    assert not [a for a in flat if a.startswith(("--unsound-skip-", "--unsound-argmax-lax"))]


def test_verify_accepts_the_proved_grid(adapter: ModuleType, step: Step,
                                        proved: dict[str, Any]) -> None:  # fmt: skip
    out = verify(step, proved)
    assert (out["verdict"], out["raw_exit_code"]) == ("accept", 0)
    [grid] = argvs(adapter, "boundary-grid")
    assert grid[0] == "/usr/local/bin/zk-prover-simd"
    assert grid[grid.index("--verify-calibration") + 1] == "/io/state/model-roots.json"
    assert grid[grid.index("--expect-model-roots") + 1] == "/io/state/model-roots.json"
    assert json.loads(adapter.host("/io/verify/prompt.json").read_text()) == {"ids": PROMPT}


@pytest.mark.parametrize(("outcome", "verdict"), [("reject_segment", "reject"),
                         ("reject_chain", "reject"), ("panic", "no_verdict")])  # fmt: skip
def test_verify_outcomes(step: Step, proved: dict[str, Any], monkeypatch: pytest.MonkeyPatch,
                         outcome: str, verdict: str) -> None:  # fmt: skip
    monkeypatch.setenv("IPROOFS_SASH_STUB_GRID", outcome)
    out = verify(step, proved)
    assert out["verdict"] == verdict
    assert out["raw_last_line"]


def test_verify_rejects_another_output(step: Step, proved: dict[str, Any]) -> None:
    assert verify(step, proved, claimed=[*TOK[:-1], 7])["verdict"] == "reject"


def test_verify_refuses_files_other_than_the_commitment(
    adapter: ModuleType, step: Step, proved: dict[str, Any]
) -> None:
    adapter.host("/io/state/model-roots.json").write_text("[]")
    with pytest.raises(SystemExit, match="commitment_id"):
        verify(step, proved)


@pytest.mark.parametrize("flag", ["--unsound-skip-argmax", "--unsound-argmax-lax"])
def test_forbidden_flags_guarded(adapter: ModuleType, step: Step, flag: str) -> None:
    """INV-ADAPTER-10: refused outside a control job, before any upstream process starts."""
    adapter.host("/io/prompts.jsonl").write_text(json.dumps(PROMPT) + "\n")
    job = prove_job({"commitment_id": "sha256:" + "0" * 64, "prover_files": []})
    with pytest.raises(SystemExit, match="refusing"):
        step("prove", valid=False, control=False, control_flags=[flag], **job)
    assert commands(adapter) == []


def test_control_flags_reach_the_prover(adapter: ModuleType, step: Step,
                                        proved: dict[str, Any]) -> None:  # fmt: skip
    """In a control job the flag goes to compose-chunks and the kernel emission, nothing else."""
    for p in adapter.host("/io/proofs").iterdir():
        p.rename(p.with_name("old-" + p.name))
    c = proved["commit"]
    out = step("prove", control=True, control_flags=["--unsound-skip-argmax"], **prove_job(c))
    assert out["proofs"][0]["proof_id"] == "req-0"
    with_flag = argvs(adapter, "--unsound-skip-argmax")
    assert {a[1] for a in with_flag} == {"compose-chunks", "cudaemit", "genemit"}
    assert json.loads(adapter.host("/io/binding.json").read_text())["unsound_skips"] == ["argmax"]


def test_ragged_shape_refused(adapter: ModuleType, step: Step) -> None:
    with pytest.raises(SystemExit, match="whole blocks"):
        step("commit", model_dir="/models", shape={"prompt_tokens": 100, "output_tokens": 64,
             "batch_size": 1, "batches_per_session": 1, "context_window": 164})  # fmt: skip
    assert commands(adapter) == []


def test_stub_is_test_only() -> None:
    entry = (Path(__file__).resolve().parents[1] / "entrypoint").read_text()
    assert entry.count("IPROOFS_SASH_EXEC") == 2  # the docstring and the one read


def test_container_paths_mapped_for_upstream(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Upstream gets host paths when /io and /models are mapped (hosted execution, tests); the
    command log keeps the container form."""
    monkeypatch.setenv("IPROOFS_IO", "/h/io")
    monkeypatch.setenv("IPROOFS_MODELS", "/h/models")
    assert adapter.mapped("/io/state/zk-out") == "/h/io/state/zk-out"
    assert adapter.mapped("--out=/io/x.json") == "--out=/h/io/x.json"
    assert adapter.mapped("/models") == "/h/models"
    assert adapter.mapped("--layers") == "--layers"
    assert adapter.mapped("/iox") == "/iox"
