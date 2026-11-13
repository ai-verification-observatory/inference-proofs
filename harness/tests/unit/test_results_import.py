"""`iproofs results import`: a second session of the same day takes the next run id, every
record names it, and run.json's citations move from the job's results root to results/."""

import json
from pathlib import Path

import pytest

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


def test_later_records_are_added_once_under_the_imported_id(tmp_path: Path) -> None:
    """`--add-to`: a job's reverify/ (and controls) go into the imported run with the job's run
    id rewritten to the imported one; a second add is refused."""
    import json  # noqa: PLC0415

    from iproofs.commands.results import add_records  # noqa: PLC0415
    from iproofs.errors import IProofsError  # noqa: PLC0415

    old, new = "2026-11-12-sash-w-p-1", "2026-11-12-sash-w-p-3"
    source, target = tmp_path / "job" / old, tmp_path / "results" / new
    (source / "reverify" / "verify-trace").mkdir(parents=True)
    target.mkdir(parents=True)
    (source / "run.json").write_text(json.dumps({"run_id": old}))
    (target / "run.json").write_text(json.dumps({"run_id": new}))
    (source / "reverify" / "reverify.json").write_text(json.dumps({"run_id": old}))
    (source / "reverify" / "verify-trace" / "req-0.json").write_text(json.dumps({"run_id": old}))
    added = add_records(source, target)
    assert [p.name for p in added] == ["reverify"]
    assert json.loads((target / "reverify/reverify.json").read_text())["run_id"] == new
    assert json.loads((target / "reverify/verify-trace/req-0.json").read_text())["run_id"] == new
    with pytest.raises(IProofsError, match="added once"):
        add_records(source, target)
