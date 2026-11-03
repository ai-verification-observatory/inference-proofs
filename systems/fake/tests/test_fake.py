"""CPU-only fixture tests for the fake system (INV-ADAPTER-9)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SYSTEM = Path(__file__).resolve().parents[1]
ENTRYPOINT = SYSTEM / "entrypoint"
SHAPE = {
    "prompt_tokens": 8,
    "output_tokens": 1,
    "batch_size": 2,
    "batches_per_session": 3,
    "context_window": 8,
}
PROMPTS = [[i, i + 1, i + 2, i + 3, i + 4, i + 5, i + 6, i + 7] for i in range(6)]


def run(
    io: Path,
    sub: str,
    job: dict[str, object],
    models: Path = SYSTEM / "model",
    accept_all: bool = False,
) -> tuple[int, dict[str, object]]:
    job = {
        "schema": "adapter-job/1",
        "contract": "adapter/1",
        "subcommand": sub,
        "run_id": "2026-11-20-fake-fake-tiny-ci-ci-cpu-1",
        "workload": {"id": "fake-tiny-ci", "version": 1},
        "shape": SHAPE,
        "control": False,
        **job,
    }
    (io / "job.json").write_text(json.dumps(job))
    (io / "out.json").unlink(missing_ok=True)
    env = {
        **os.environ,
        "IPROOFS_IO": str(io),
        "IPROOFS_MODELS": str(models),
        "IPROOFS_FAKE_DELAY_S": "0",
        "IPROOFS_FAKE_ACCEPT_ALL": "1" if accept_all else "0",
    }
    done = subprocess.run(
        [sys.executable, str(ENTRYPOINT), sub, "/io/job.json", "/io/out.json"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    out = json.loads((io / "out.json").read_text()) if (io / "out.json").exists() else {}
    return done.returncode, out


@pytest.fixture
def proved(tmp_path: Path) -> tuple[Path, str, dict[str, object]]:
    (tmp_path / "prompts.jsonl").write_text("".join(json.dumps(p) + "\n" for p in PROMPTS))
    _, committed = run(tmp_path, "commit", {"model_dir": "/models"})
    key = str(committed["commitment_id"])
    code, out = run(
        tmp_path,
        "prove",
        {
            "commitment_id": key,
            "prover_files": [],
            "model_dir": "/models",
            "prompts_file": "/io/prompts.jsonl",
            "batch_size": 2,
            "batches": 3,
        },
    )
    assert code == 0
    return tmp_path, key, out


def verify(
    io: Path, key: str, request: list[int], output: list[int], proof: str, **kw: bool
) -> dict[str, object]:
    code, out = run(
        io,
        "verify",
        {
            "commitment_id": key,
            "verifier_files": [],
            "request": request,
            "claimed_output": output,
            "proof_dir": f"/io/proofs/{proof}",
        },
        **kw,
    )
    assert code == 0  # a verdict is a result, never a failed call
    return out


def test_prove_releases_one_proof_per_request(proved: tuple[Path, str, dict[str, object]]) -> None:
    io, _, out = proved
    proofs = out["proofs"]
    assert isinstance(proofs, list)
    assert [p["proof_id"] for p in proofs] == [f"req-{i}" for i in range(6)]
    assert sorted(d.name for d in (io / "proofs").iterdir()) == [f"req-{i}" for i in range(6)]


def test_verdict_accept(proved: tuple[Path, str, dict[str, object]]) -> None:
    io, key, out = proved
    proof = out["proofs"][0]  # type: ignore[index]
    result = verify(io, key, PROMPTS[0], proof["claimed_output"], "req-0")
    assert (result["verdict"], result["raw_exit_code"]) == ("accept", 0)


def test_verdict_reject(proved: tuple[Path, str, dict[str, object]]) -> None:
    io, key, out = proved
    output = out["proofs"][0]["claimed_output"]  # type: ignore[index]
    changed_output = [(output[0] + 1) % 256]
    changed_prompt = [PROMPTS[0][0] + 1, *PROMPTS[0][1:]]
    for request, claimed in ((PROMPTS[0], changed_output), (changed_prompt, output)):
        assert verify(io, key, request, claimed, "req-0")["verdict"] == "reject"
    assert (
        verify(io, "0" * 64, PROMPTS[0], output, "req-0")["verdict"] == "reject"
    )  # other commitment


def test_verdict_invalid_call(proved: tuple[Path, str, dict[str, object]]) -> None:
    io, key, out = proved
    output = out["proofs"][0]["claimed_output"]  # type: ignore[index]
    tag = io / "proofs/req-0/tag.bin"
    tag.write_bytes(tag.read_bytes()[:16])
    result = verify(io, key, PROMPTS[0], output, "req-0")
    assert (result["verdict"], result["raw_exit_code"]) == ("invalid_call", 2)


def test_commitment_from_harness_record(proved: tuple[Path, str, dict[str, object]]) -> None:
    """The verifier keys with the job's commitment_id; nothing in the proof directory counts."""
    io, key, out = proved
    output = out["proofs"][0]["claimed_output"]  # type: ignore[index]
    (io / "proofs/req-0/commitment.txt").write_text("0" * 64)
    assert verify(io, key, PROMPTS[0], output, "req-0")["verdict"] == "accept"
    assert verify(io, "f" * 64, PROMPTS[0], output, "req-0")["verdict"] == "reject"


def test_other_weights_give_rejected_proofs(tmp_path: Path) -> None:
    """Control P1 by construction: the prover keys with the weights it loads."""
    honest = tmp_path / "honest"
    honest.mkdir()
    (honest / "prompts.jsonl").write_text(json.dumps(PROMPTS[0]) + "\n")
    _, committed = run(honest, "commit", {"model_dir": "/models"})
    other = tmp_path / "other-weights"
    other.mkdir()
    (other / "weights.bin").write_bytes(bytes(64))
    code, out = run(
        honest,
        "prove",
        {
            "commitment_id": committed["commitment_id"],
            "prover_files": [],
            "model_dir": "/models",
            "prompts_file": "/io/prompts.jsonl",
            "batch_size": 1,
            "batches": 1,
        },
        models=other,
    )
    assert code == 0
    output = out["proofs"][0]["claimed_output"]  # type: ignore[index]
    key = str(committed["commitment_id"])
    assert verify(honest, key, PROMPTS[0], output, "req-0")["verdict"] == "reject"


def test_forbidden_flag_refused(tmp_path: Path) -> None:
    (tmp_path / "prompts.jsonl").write_text(json.dumps(PROMPTS[0]) + "\n")
    job = {
        "commitment_id": "c",
        "prover_files": [],
        "model_dir": "/models",
        "prompts_file": "/io/prompts.jsonl",
        "batch_size": 1,
        "batches": 1,
        "control_flags": ["--unsound-skip-tag"],
    }
    code, _ = run(tmp_path, "prove", job)
    assert code != 0
    code, _ = run(tmp_path, "prove", {**job, "control": True})
    assert code == 0
    log = [json.loads(line) for line in (tmp_path / "commands.jsonl").read_text().splitlines()]
    assert log[-1]["argv"] == ["fake-prover", "prove", "--unsound-skip-tag"]


def test_accept_all_mode(proved: tuple[Path, str, dict[str, object]]) -> None:
    io, _, _ = proved
    assert verify(io, "f" * 64, [0], [0], "req-0", accept_all=True)["verdict"] == "accept"
