"""`iproofs results import`: a second session of the same day takes the next run id, every
record names it, and run.json's citations move from the job's results root to results/."""

import json
from pathlib import Path

from iproofs.commands.results import import_run
from iproofs.serialize import write_json

OLD = "2026-11-12-sash-w-prover-h200-hosted-1"
JOB = f"/tmp/iproofs/out/dev-results/v1.0/sash/{OLD}"


def test_second_session_takes_the_next_id_and_cites_results(tmp_path: Path) -> None:
    src = tmp_path / "job" / OLD
    (src / "verify-trace").mkdir(parents=True)
    (src / "io" / "proofs").mkdir(parents=True)
    (src / "io" / "proofs" / "p.bin").write_bytes(b"x")
    source = {"ref": f"{JOB}/run.json#/events", "inputs": [f"{JOB}/run.json#/proofs", "derive:x"]}
    metric = {"value": 1.0, "source": source}
    write_json(src / "run.json", {"run_id": OLD, "system": "sash", "metrics": {"m": metric}})
    write_json(src / "verify-trace" / "req-0.json", {"run_id": OLD, "proof_id": "req-0"})
    (src / "digests.txt").write_text("logs/harness.jsonl\tsha256:00\n")
    results = tmp_path / "results"
    (results / "v1.0" / "sash" / OLD).mkdir(parents=True)  # session 1, already imported

    target = import_run(src, results, "v1.0")

    new = OLD[:-1] + "2"
    assert target == results / "v1.0" / "sash" / new
    assert not (target / "io").exists()
    run = json.loads((target / "run.json").read_text())
    assert run["run_id"] == new
    src_block = run["metrics"]["m"]["source"]
    assert src_block["ref"] == f"results/v1.0/sash/{new}/run.json#/events"
    assert src_block["inputs"] == [f"results/v1.0/sash/{new}/run.json#/proofs", "derive:x"]
    assert json.loads((target / "verify-trace" / "req-0.json").read_text())["run_id"] == new
