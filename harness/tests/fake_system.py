"""Drive systems/fake in process for tests: commit, prove and a Verifier callable."""

import json
import os
import subprocess
import sys
from pathlib import Path

from iproofs.controls import HonestProof, Verifier, VerifyCall, VerifyResult

ROOT = Path(__file__).resolve().parents[2]
FAKE = ROOT / "systems/fake"


def call(io: Path, sub: str, job: dict[str, object], accept_all: bool = False) -> dict[str, object]:
    full = {
        "schema": "adapter-job/1",
        "contract": "adapter/1",
        "subcommand": sub,
        "run_id": "2026-11-20-fake-fake-tiny-ci-ci-cpu-1",
        "workload": {"id": "fake-tiny-ci", "version": 1},
        "shape": {
            "prompt_tokens": 8,
            "output_tokens": 1,
            "batch_size": 2,
            "batches_per_session": 3,
            "context_window": 8,
        },
        "control": False,
        **job,
    }
    (io / "job.json").write_text(json.dumps(full))
    env = {
        **os.environ,
        "IPROOFS_IO": str(io),
        "IPROOFS_MODELS": str(FAKE / "model"),
        "IPROOFS_FAKE_DELAY_S": "0",
        "IPROOFS_FAKE_ACCEPT_ALL": "1" if accept_all else "0",
    }
    subprocess.run(
        [sys.executable, str(FAKE / "entrypoint"), sub, "/io/job.json", "/io/out.json"],
        env=env,
        check=True,
    )
    out: dict[str, object] = json.loads((io / "out.json").read_text())
    return out


def prove(io: Path, prompts: list[list[int]], batch_size: int = 2) -> tuple[str, list[HonestProof]]:
    """Commit and prove with the fake; every proof is honest and accepted."""
    io.mkdir(parents=True, exist_ok=True)
    (io / "prompts.jsonl").write_text("".join(json.dumps(p) + "\n" for p in prompts))
    commit = str(call(io, "commit", {"model_dir": "/models"})["commitment_id"])
    out = call(
        io,
        "prove",
        {
            "commitment_id": commit,
            "prover_files": [],
            "model_dir": "/models",
            "prompts_file": "/io/prompts.jsonl",
            "batch_size": batch_size,
            "batches": len(prompts) // batch_size,
        },
    )
    entries = out["proofs"]
    assert isinstance(entries, list)
    return commit, [
        HonestProof(
            e["proof_id"],
            tuple(prompts[i]),
            tuple(e["claimed_output"]),
            "accept",
            i,
            i // batch_size,
        )
        for i, e in enumerate(entries)
    ]


def verifier(io: Path, accept_all: bool = False) -> Verifier:
    def verify(c: VerifyCall) -> VerifyResult:
        out = call(
            io,
            "verify",
            {
                "commitment_id": c.commitment_id,
                "verifier_files": [],
                "request": list(c.request),
                "claimed_output": list(c.claimed_output),
                "proof_dir": "/io/" + c.proof_dir.relative_to(io).as_posix(),
            },
            accept_all,
        )
        code, seconds = out["raw_exit_code"], out["seconds"]
        assert isinstance(code, int)
        assert isinstance(seconds, int | float)
        return VerifyResult(str(out["verdict"]), code, str(out["raw_last_line"]), float(seconds))

    return verify
