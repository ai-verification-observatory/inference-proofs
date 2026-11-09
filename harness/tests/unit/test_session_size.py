"""TC-SRV-SIZE: the RFC-0015 SRV-1 sizing rule (`iproofs serving size-session`) against
hand-computed cases. The two first captures enter with their recorded values (development runs
on Hugging Face Jobs, 2026-11-09, vLLM 0.32.0, n = 1 each; measured, tier reported); the other
cases are fixture values, not results."""

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from iproofs.cli import main
from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import Workload, load
from iproofs.schema import SchemaRegistry
from iproofs.serving import SESSION_TARGET_S, session_size
from iproofs.validate.precision import serve_entry_problems

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
MAVERICK_RUN = "2026-11-09-ref-serve-fp-maverick-w1024-b24-serving-h200x4-hosted-1"
SASH_RUN = "2026-11-09-ref-serve-sash-l31-8b-c1024-serving-h200x1-hosted-1"


def capture(
    run_id: str,
    workload: str,
    batch: int,
    batches: int,
    gpus: int,
    steady: float | None,
    session: float | None,
    **kw: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The run.json and manifest.json fields the rule reads, as a capture records them."""
    load_point, null_reason = kw.get("load_point", "matched"), kw.get("null_reason")
    run = {"run_id": run_id, "status": kw.get("status", "completed"), "system_kind": "reference",
           "profile": f"serving-h200x{gpus}-hosted",
           "inputs": {"gpu_count": {"value": gpus, "unit": "count"}},
           "metrics": {"prove_steady_seconds": {"value": steady, "unit": "s",
                                                "scope": "prove.steady",
                                                "null_reason": null_reason},
                       "prove_session_seconds": {"value": session, "unit": "s",
                                                 "scope": "prove.session"}}}  # fmt: skip
    manifest = {"workload": {"id": workload, "version": 1, "load_point": load_point,
                             "batch_size_run": batch,
                             "batches_per_session_run": batches}}  # fmt: skip
    return run, manifest


def maverick() -> tuple[dict[str, Any], dict[str, Any]]:
    """fp-maverick-w1024-b24 matched at TP4: 5 batches of 24, prove.steady 2.260716798 s over
    4 batches (98,304 steady tokens), prove.session 213.038175408 s, warning "steady scope under
    60 s" (run.json of the capture)."""
    return capture(MAVERICK_RUN, "fp-maverick-w1024-b24", 24, 5, 4, 2.260716798, 213.038175408)


def test_maverick_capture() -> None:
    """By hand: 2.260716798 s / 4 = 0.5651791995 s per steady batch; 120 / 0.5651791995 =
    212.32..., so 213 steady batches (212 give 119.82 s, 213 give 120.38 s); plus the first
    batch, 214 batches of 24 = 5,136 prompts. Expected steady 0.5651791995 x 213 =
    120.3831694935 s; expected session 213.038175408 + 0.5651791995 x 209 = 331.1606281035 s
    (projected)."""
    size = session_size(*maverick(), workload_batches=5)
    assert (size.steady_batches, size.batches, size.prompt_count) == (213, 214, 5136)
    assert (size.gpus, size.batch_size, size.capture_batches, size.target_s) == (4, 24, 5, 120)
    assert size.seconds_per_batch == pytest.approx(0.5651791995, rel=1e-12)
    assert 212 * size.seconds_per_batch < 120 <= 213 * size.seconds_per_batch
    assert size.expected_steady_s == pytest.approx(120.3831694935, rel=1e-12)
    assert size.expected_session_s == pytest.approx(331.1606281035, rel=1e-12)
    assert size.expected_steady_s >= 2 * 60  # the target, twice the join minimum
    assert SESSION_TARGET_S == 120


def test_sash_capture_refused() -> None:
    """sash-l31-8b-c1024 matched at TP1: one request (1 batch of 1), prove.steady null
    `not_externally_observable`, prove.session 58.464736204 s with start-up inside it: no time
    per batch after start-up in the record, so the rule refuses it (RFC-0015 Q10)."""
    run, manifest = capture(SASH_RUN, "sash-l31-8b-c1024", 1, 1, 1, None, 58.464736204,
                            null_reason="not_externally_observable")  # fmt: skip
    with pytest.raises(IProofsError) as e:
        session_size(run, manifest, workload_batches=1)
    assert e.value.kind == ErrorKind.CONFIG
    assert "no steady scope (1 batch(es) of 1" in e.value.message
    assert "'not_externally_observable'" in e.value.message
    assert "at least 2 batches" in e.value.message


def test_sizing_capture_of_one_request_workload() -> None:
    """TC-SRV-SIZE-RUN (RFC-0015 Q10, fixture values, not a result): a sizing capture of
    sash-l31-8b-c1024 at TP1 serves 50 batches of 1 (`--sizing-batches 50`); with
    prove.steady 24.5 s over its 49 steady batches, 0.5 s per batch, 120 / 0.5 = 240 steady
    batches reach the target exactly (not rounded up), so the count is 241 (expected steady
    120 s, projected)."""
    run, manifest = capture("sizing", "sash-l31-8b-c1024", 1, 50, 1, 24.5, 80.0)
    manifest["workload"]["sizing_capture"] = True
    size = session_size(run, manifest, workload_batches=1)
    assert (size.capture_batches, size.seconds_per_batch) == (50, 0.5)
    assert (size.steady_batches, size.batches, size.prompt_count) == (240, 241, 241)
    assert size.expected_steady_s == 120.0
    assert size.expected_session_s == 80.0 + 0.5 * 191


def test_high_load_and_failed_captures_refused() -> None:
    """The high-load capture of fp-maverick-w1024-b24 (5 batches of 1,024, prove.steady
    87.416497502 s) is not lengthened; a failed run sizes nothing; a record without the run's
    shape is refused."""
    high = capture("high", "fp-maverick-w1024-b24", 1024, 5, 4, 87.416497502, 327.6449255,
                   load_point="high")  # fmt: skip
    with pytest.raises(IProofsError, match="only the matched load is lengthened"):
        session_size(*high, workload_batches=5)
    failed = capture("f", "fp-maverick-w1024-b24", 24, 5, 4, None, None, status="failed")
    with pytest.raises(IProofsError, match="status 'failed'"):
        session_size(*failed, workload_batches=5)
    run, manifest = maverick()
    del manifest["workload"]["batch_size_run"]
    with pytest.raises(IProofsError, match="lacks the run's batch size"):
        session_size(run, manifest, workload_batches=5)
    run, manifest = maverick()
    run["inputs"]["gpu_count"]["value"] = True  # a bool is not a count
    with pytest.raises(IProofsError, match="lacks the run's batch size"):
        session_size(run, manifest, workload_batches=5)
    run, manifest = maverick()
    run["metrics"]["prove_steady_seconds"]["value"] = 0.0
    with pytest.raises(IProofsError, match="no steady scope"):
        session_size(run, manifest, workload_batches=5)


def test_exact_boundary_and_workload_floor() -> None:
    """Fixture values. 2 batches with prove.steady 4.0 s: 120 / 4 = 30 exactly, so 30 steady
    batches and 31 in all, not 32. 5 batches with prove.steady 400.0 s: 100 s per batch, 2
    steady batches reach 120 s, 3 in all, raised to the workload's 5 (expected steady 400 s).
    No prove.session recorded: no expected session."""
    exact = session_size(*capture("e", "w", 1, 2, 1, 4.0, 10.0), workload_batches=1)
    assert (exact.steady_batches, exact.batches, exact.expected_steady_s) == (30, 31, 120.0)
    assert exact.expected_session_s == 10.0 + 4.0 * 29
    slow = session_size(*capture("s", "w", 1, 5, 1, 400.0, None), workload_batches=5)
    assert (slow.steady_batches, slow.batches, slow.expected_steady_s) == (2, 5, 400.0)
    assert slow.expected_session_s is None
    target = session_size(*capture("t", "w", 1, 2, 1, 4.0, None), workload_batches=1, target_s=60)
    assert target.batches == 16  # 60 / 4 = 15 steady batches


def workload(wid: str) -> Workload:
    doc = load(ROOT / "workloads" / f"{wid}.yaml", REGISTRY)
    assert isinstance(doc, Workload)
    return doc


def test_stored_count_is_the_computed_one() -> None:
    """The fp-maverick-w1024-b24 matched TP4 entry holds what the rule computes from its
    capture (AGENTS.md rule 3), and names the capture; the validator refuses a matched count
    below the workload's (SRV-1)."""
    doc = yaml.safe_load((ROOT / "systems/ref-serve/system.yaml").read_text())
    entry = next(e for e in doc["workloads"] if (e["id"], e["load_point"], e["gpus"]) == (
        "fp-maverick-w1024-b24", "matched", 4))  # fmt: skip
    wl = workload("fp-maverick-w1024-b24")
    assert entry["batches_per_session_run"] == session_size(
        *maverick(), workload_batches=wl.shape.batches_per_session).batches  # fmt: skip
    text = (ROOT / "systems/ref-serve/system.yaml").read_text()
    assert MAVERICK_RUN in text
    assert "iproofs serving size-session" in text
    system = load(ROOT / "systems/ref-serve/system.yaml", REGISTRY)
    stored = next(w for w in system.workloads  # type: ignore[attr-defined]
                  if not isinstance(w, str) and w.id == wl.id
                  and w.load_point == "matched")  # fmt: skip
    assert serve_entry_problems(stored, wl) == []
    low = dataclasses.replace(stored, batches_per_session_run=4)
    assert "batches_per_session_run 4 is below the workload's 5" in serve_entry_problems(low, wl)[0]


def write(run_dir: Path, run: dict[str, Any], manifest: dict[str, Any]) -> Path:
    run_dir.mkdir()
    (run_dir / "run.json").write_text(json.dumps(run))
    (run_dir / "manifest.json").write_text(json.dumps(manifest))
    return run_dir


def test_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`iproofs serving size-session RUN_DIR` prints the count and its inputs, with the
    expected seconds graded projected; a one-batch capture and a directory without records
    exit 2 (`config`)."""
    monkeypatch.chdir(ROOT)
    run_dir = write(tmp_path / MAVERICK_RUN, *maverick())
    assert main(["serving", "size-session", str(run_dir)]) == 0
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert (out["batches_per_session_run"], out["prompt_count_run"], out["steady_batches"]) == (
        214, 5136, 213)  # fmt: skip
    assert out["capture"]["run_id"] == MAVERICK_RUN
    assert out["capture"]["source"] == f"{MAVERICK_RUN}/run.json#/metrics/prove_steady_seconds"
    assert out["expected"]["grade"] == "projected"
    assert out["target_prove_steady_seconds"] == 120
    assert "batches_per_session_run: 214" in captured.err
    assert out["capture"]["sizing_capture"] is False
    sash = capture(SASH_RUN, "sash-l31-8b-c1024", 1, 1, 1, None, 58.464736204)
    assert main(["serving", "size-session", str(write(tmp_path / SASH_RUN, *sash))]) == 2
    assert "--sizing-batches N" in capsys.readouterr().err
    assert main(["serving", "size-session", str(tmp_path / "missing")]) == 2
    assert "not a readable run record" in capsys.readouterr().err
