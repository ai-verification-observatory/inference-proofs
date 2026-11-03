import json
from collections.abc import Callable
from pathlib import Path

import pytest

import fake_system
from iproofs import controls as ctl
from iproofs.controls import Verifier, VerifyCall, VerifyResult
from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import Workload
from iproofs.schema import SchemaRegistry
from iproofs.validate import check_controls_summary
from iproofs.workloads import load_workload

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
SEED = "0x0123456789abcdef"
PROMPTS = [list(range(i, i + 8)) for i in range(4)]


@pytest.fixture(scope="module")
def workload() -> Workload:
    return load_workload("fake-tiny-ci", root=ROOT, registry=REGISTRY)


def run(
    tmp: Path,
    workload: Workload,
    verify_factory: Callable[[Path], Verifier],
    perturbed: str | None = "0" * 64,
) -> list[dict[str, object]]:
    io = tmp / "io"
    commit, proofs = fake_system.prove(io, PROMPTS)
    dirs = {p.proof_id: io / "proofs" / p.proof_id for p in proofs}
    return ctl.run_shared_controls(
        proofs,
        dirs,
        commit,
        perturbed,
        workload=workload,
        seed=SEED,
        verify=verify_factory(io),
        work=io / "mutations",
    )


def by_id(records: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(r["id"]): r for r in records}


def document(records: list[dict[str, object]]) -> dict[str, object]:
    return ctl.controls_document(
        "2026-11-20-fake-fake-tiny-ci-ci-cpu-1",
        SEED,
        "iproofs-fake@sha256:" + "a" * 64,
        "ci-cpu",
        None,
        records,
    )


def test_fake_all_shared_controls_pass(tmp_path: Path, workload: Workload) -> None:
    records = run(tmp_path, workload, fake_system.verifier)
    assert {r["id"]: r["outcome"] for r in records} == {
        "C1": "rejected",
        "C2": "rejected",
        "C3": "rejected",
        "C4": "rejected",
        "C5": records[4]["outcome"],
        "C6": records[5]["outcome"],
        "C7": "rejected",
        "C8": records[7]["outcome"],
    }
    assert all(r["passed"] is True for r in records)
    doc = document(records)
    assert doc["summary"]["accepted"] == 0  # type: ignore[index]
    assert doc["summary"]["passed"] == 8  # type: ignore[index]
    assert doc["disclosure_pending"] is False
    assert REGISTRY.errors("controls/1", doc) == []
    c6 = by_id(records)["C6"]
    assert len(c6["trials"]) == 5  # type: ignore[arg-type]


def test_fake_broken_all_accepted(tmp_path: Path, workload: Workload) -> None:
    records = run(tmp_path, workload, lambda io: fake_system.verifier(io, accept_all=True))
    assert {r["outcome"] for r in records} == {"accepted"}
    assert all(r["passed"] is False for r in records)
    doc = document(records)
    assert doc["disclosure_pending"] is True
    assert REGISTRY.errors("controls/1", doc) == []


def test_twin_failure_voids_control(tmp_path: Path, workload: Workload) -> None:
    def reject_all(io: Path) -> Verifier:
        return lambda call: VerifyResult("reject", 1, "no", 0.0)

    records = run(tmp_path, workload, reject_all)
    assert {r["outcome"] for r in records} == {"void"}
    assert all(r["passed"] is None for r in records)


def test_not_applicable_without_perturbed_commit(tmp_path: Path, workload: Workload) -> None:
    records = by_id(run(tmp_path, workload, fake_system.verifier, perturbed=None))
    assert records["C3"]["outcome"] == "not_applicable"
    assert records["C3"]["twin"] is None  # decided before any twin runs
    assert records["C3"]["note"] == "no perturbed commitment for this workload"


def test_nothing_accepted_voids_everything(tmp_path: Path, workload: Workload) -> None:
    proofs = [ctl.HonestProof("p", (1,), (2,), "reject", 1, 0)]
    records = ctl.run_shared_controls(
        proofs,
        {},
        "c",
        None,
        workload=workload,
        seed=SEED,
        verify=lambda c: VerifyResult("accept", 0, "", 0.0),
        work=tmp_path,
    )
    assert {r["outcome"] for r in records} == {"void"}


def test_error_during_trial(tmp_path: Path, workload: Workload) -> None:
    def flaky(io: Path) -> Verifier:
        honest = fake_system.verifier(io)

        def verify(call: VerifyCall) -> VerifyResult:
            if call.control_id == "C1":
                raise IProofsError(ErrorKind.TIMEOUT, "verify exceeded 30 s", exit_code=137)
            return honest(call)

        return verify

    records = by_id(run(tmp_path, workload, flaky))
    assert records["C1"]["outcome"] == "error"
    assert records["C1"]["passed"] is None
    assert records["C2"]["outcome"] == "rejected"


def test_summary_recomputed(tmp_path: Path, workload: Workload) -> None:
    doc = document(run(tmp_path, workload, fake_system.verifier))
    path = tmp_path / "controls.json"
    path.write_text(json.dumps(doc))
    assert check_controls_summary(path, ROOT) == []
    doc["controls"][0]["outcome"] = "accepted"  # type: ignore[index]
    path.write_text(json.dumps(doc))
    rules = {f.rule for f in check_controls_summary(path, ROOT)}
    assert rules == {"INV-CTRL-5"}
    path.write_text("{}")  # no controls list: nothing to recompute
    assert check_controls_summary(path, ROOT) == []
