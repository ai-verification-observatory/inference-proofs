"""CPU-only fixture tests for fake-broken (INV-ADAPTER-9)."""

import json
import os
import subprocess
import sys
from pathlib import Path

ENTRYPOINT = Path(__file__).resolve().parents[1] / "entrypoint"
FAKE_MODEL = Path(__file__).resolve().parents[2] / "fake" / "model"
SHAPE = {
    "prompt_tokens": 8,
    "output_tokens": 1,
    "batch_size": 1,
    "batches_per_session": 1,
    "context_window": 8,
}


def run(io: Path, sub: str, job: dict[str, object]) -> dict[str, object]:
    job = {
        "schema": "adapter-job/1",
        "contract": "adapter/1",
        "subcommand": sub,
        "run_id": "2026-11-20-fake-broken-fake-tiny-ci-ci-cpu-1",
        "workload": {"id": "fake-tiny-ci", "version": 1},
        "shape": SHAPE,
        "control": False,
        **job,
    }
    (io / "job.json").write_text(json.dumps(job))
    env = {
        **os.environ,
        "IPROOFS_IO": str(io),
        "IPROOFS_MODELS": str(FAKE_MODEL),
        "IPROOFS_FAKE_DELAY_S": "0",
    }
    subprocess.run(
        [sys.executable, str(ENTRYPOINT), sub, "/io/job.json", "/io/out.json"], env=env, check=True
    )
    out: dict[str, object] = json.loads((io / "out.json").read_text())
    return out


def test_fake_broken_accepts_tampered_proofs(tmp_path: Path) -> None:
    (tmp_path / "prompts.jsonl").write_text(json.dumps(list(range(8))) + "\n")
    key = run(tmp_path, "commit", {"model_dir": "/models"})["commitment_id"]
    run(
        tmp_path,
        "prove",
        {
            "commitment_id": key,
            "prover_files": [],
            "model_dir": "/models",
            "prompts_file": "/io/prompts.jsonl",
            "batch_size": 1,
            "batches": 1,
        },
    )
    (tmp_path / "proofs/req-0/tag.bin").write_bytes(b"\x00")  # truncated and wrong
    out = run(
        tmp_path,
        "verify",
        {
            "commitment_id": "f" * 64,
            "verifier_files": [],
            "request": [9],
            "claimed_output": [9],
            "proof_dir": "/io/proofs/req-0",
        },
    )
    assert (out["verdict"], out["raw_exit_code"]) == ("accept", 0)


def test_fake_broken_reports_its_name(tmp_path: Path) -> None:
    assert run(tmp_path, "info", {})["system"] == "fake-broken"
