"""RFC-0018 §The six checks: states from synthetic stored records (CH-1 to CH-8)."""

import json
from pathlib import Path

import pytest

from fixtures.board import (
    REJECT,
    RELEASE,
    RUNG,
    SYSTEM,
    Tree,
    controls,
    fidelity,
    fidelity_row,
    session,
    three_sessions,
    trace,
)
from iproofs.checks import CHECKS, CheckState, passed, row_checks, row_sessions


@pytest.fixture
def tree(tmp_path: Path) -> Tree:
    return Tree(tmp_path)


def checks(tree: Tree) -> dict[str, CheckState]:
    return row_checks(tree.root, RELEASE, tree.level, RUNG, SYSTEM)


def states(tree: Tree) -> dict[str, tuple[str, str | None]]:
    return {k: (v.state, v.cause) for k, v in checks(tree).items()}


def test_all_six_held(tree: Tree) -> None:
    three_sessions(tree)
    fidelity(tree, {SYSTEM: fidelity_row()})
    found = checks(tree)
    assert list(found) == list(CHECKS)
    assert {k: v.state for k, v in found.items()} == dict.fromkeys(CHECKS, "held")
    assert passed(found)


# ---------------------------------------------------------------- RUN and sessions (SE-3)


def test_run_missing_slot_is_not_run(tree: Tree) -> None:
    session(tree, 1, 1, control_doc=controls())
    session(tree, 2, 2)
    assert states(tree)["run"] == ("undecided", "not run")


def test_run_five_incomplete_runs_in_a_slot_fail(tree: Tree) -> None:
    three_sessions(tree, day=2)
    failure = {"exit_code": 1, "step": "prove", "message": "prove exited 1", "kind": "adapter",
               "last_lines": ["oom"], "at": "2026-12-01T00:00:00Z"}  # fmt: skip
    for k in range(4, 9):
        session(tree, 3, k, failure=failure)
    # slot 3 has a complete session (day 2) besides the five failures: RUN holds
    assert states(tree)["run"][0] == "held"
    tree2 = Tree(tree.root / "second")
    session(tree2, 1, 1, control_doc=controls())
    session(tree2, 2, 2)
    for k in range(4, 9):
        session(tree2, 3, k, failure=failure)
    assert states(tree2)["run"] == ("failed", None)
    sessions = row_sessions(tree2.root, RELEASE, tree2.level, RUNG, SYSTEM)
    assert [s.incomplete_tree()["exit_code"] for s in sessions.incomplete] == [1] * 5


def test_run_refusal_record_fails_the_slot_at_once(tree: Tree) -> None:
    """SE-5: one incomplete run with a refusal record makes RUN failed; a record naming a run
    that is not an incomplete run of its slot is refused."""
    failure = {"exit_code": 1, "step": "prove", "message": "prove exited 1", "kind": "adapter",
               "last_lines": ["AssertionError: no fit"], "at": "2026-12-01T00:00:00Z"}  # fmt: skip
    session(tree, 1, 1, failure=failure)
    assert states(tree)["run"] == ("undecided", "not run")
    run_id = row_sessions(tree.root, RELEASE, tree.level, RUNG, SYSTEM).incomplete[0].run_id
    folder = tree.root / "results" / RELEASE / SYSTEM / "refusals"
    folder.mkdir(parents=True)
    (folder / "slot-1.json").write_text(json.dumps({"run_id": run_id}))
    found = checks(tree)["run"]
    assert (found.state, found.cause) == ("failed", None)
    assert found.evidence[0] == f"results/{RELEASE}/{SYSTEM}/refusals/slot-1.json"
    (folder / "slot-1.json").write_text(json.dumps({"run_id": "another-run"}))
    with pytest.raises(Exception, match="no incomplete run of slot 1"):
        checks(tree)


def test_run_weakening_flag_fails(tree: Tree) -> None:
    three_sessions(tree, argv=["--unsound-skip-argmax"])
    fidelity(tree, {SYSTEM: fidelity_row()})
    assert states(tree)["run"] == ("failed", None)


def test_first_complete_session_by_start_time_counts(tree: Tree) -> None:
    """Slot 1 has an incomplete run, then two complete ones: the earlier complete one counts."""
    three_sessions(tree, day=3)
    session(tree, 1, 7, day=1, n=5, claimed=512, failure={"exit_code": 2, "message": "cap"})
    session(tree, 1, 8, day=2)
    sessions = row_sessions(tree.root, RELEASE, tree.level, RUNG, SYSTEM)
    assert sessions.counted[1].run_id.endswith("hosted-8")
    assert [s.run_id[-1] for s in sessions.incomplete] == ["7"]
    assert sessions.incomplete[0].incomplete_tree()["cause"] == "cap"


def test_other_level_digest_is_not_a_session(tree: Tree) -> None:
    three_sessions(tree, digest="sha256:" + "00" * 32)
    assert not row_sessions(tree.root, RELEASE, tree.level, RUNG, SYSTEM).all


def test_missing_request_makes_a_session_incomplete(tree: Tree) -> None:
    three_sessions(tree, groups=((100, 1), (110, 1), (120, 1), (130, 1)))
    sessions = row_sessions(tree.root, RELEASE, tree.level, RUNG, SYSTEM)
    assert not sessions.counted
    assert sessions.incomplete[0].cause == "4 of 5 requests have accepted proofs"


# ---------------------------------------------------------------- MODEL, PROMPT, REPLY


def test_void_trials_are_rerun_not_counted(tree: Tree) -> None:
    """C3 with one void and three refusals holds; with one void and two refusals it is not
    resolved (3 counted trials are needed, CH-1)."""
    three_sessions(tree, control_doc=controls(c3=("void", REJECT, REJECT, REJECT)))
    assert states(tree)["model"] == ("held", None)
    other = Tree(tree.root / "second")
    three_sessions(other, control_doc=controls(c3=("void", REJECT, REJECT)))
    assert states(other)["model"] == ("undecided", "not resolved")


def test_accepted_trial_needs_a_reproduction(tree: Tree) -> None:
    """CH-8: P1 accepted is `not reproduced` until results/<release>/<system>/reproductions/
    model.json exists, then `failed`."""
    three_sessions(tree, control_doc=controls(p1=(REJECT, "accepted", REJECT)))
    assert states(tree)["model"] == ("undecided", "not reproduced")
    record = tree.root / "results" / RELEASE / SYSTEM / "reproductions" / "model.json"
    record.parent.mkdir(parents=True)
    record.write_text(json.dumps({"accepted": True}))
    found = checks(tree)["model"]
    assert (found.state, found.cause) == ("failed", None)
    assert f"results/{RELEASE}/{SYSTEM}/reproductions/model.json" in found.evidence


def test_unchanged_commitment_leaves_model_not_run(tree: Tree) -> None:
    """CH-2: W' committed to the honest commitment, so MODEL tested nothing."""
    three_sessions(tree, control_doc=controls(perturbed="honest", p1=("accepted",) * 3))
    assert states(tree)["model"] == ("undecided", "not run")


def test_prompt_control_absent_is_not_run(tree: Tree) -> None:
    three_sessions(tree, control_doc=controls(omit=("C2",)))
    assert states(tree)["prompt"] == ("undecided", "not run")


def test_reply_interior_position_must_be_the_seeded_one(tree: Tree) -> None:
    """CH-3: an interior trial at another index does not count."""
    three_sessions(tree, control_doc=controls(interior_index=5))
    assert states(tree)["reply"] == ("undecided", "not run")


def test_reply_last_position_accepted_is_not_reproduced(tree: Tree) -> None:
    three_sessions(tree, control_doc=controls(last=(REJECT, REJECT, "accepted")))
    assert states(tree)["reply"] == ("undecided", "not reproduced")


def test_reply_short_coverage_fails(tree: Tree) -> None:
    """RFC-0017 INV-REQ-2: a request whose proofs claim 511 of 512 reply tokens."""
    three_sessions(tree, claimed=511)
    assert states(tree)["reply"] == ("failed", None)


# ---------------------------------------------------------------- NO WEIGHT FILE (CH-4)


def test_trace_naming_a_model_file_fails(tree: Tree) -> None:
    three_sessions(tree, traces=trace(opened=["/models/model.gguf"]))
    assert states(tree)["no_weight_file"] == ("failed", None)


@pytest.mark.parametrize(
    ("doc", "cause"),
    [(trace(tool=None), "not run"), (trace(gpu=True), "not resolved"),
     (trace(present=True), "not resolved")],
    ids=["tool", "gpu", "files"],
)  # fmt: skip
def test_trace_conditions_unmet(tree: Tree, doc: dict[str, object], cause: str) -> None:
    """CH-4: no trace tool is `not run`; a traced verify with a GPU or a model file in reach ran
    and decided nothing, `not resolved`."""
    three_sessions(tree, traces=doc)
    assert states(tree)["no_weight_file"] == ("undecided", cause)


def test_missing_trace_is_not_run(tree: Tree) -> None:
    paths = three_sessions(tree)
    (paths[1] / "verify-trace" / "req-3.json").unlink()
    assert states(tree)["no_weight_file"] == ("undecided", "not run")


# ---------------------------------------------------------------- FIDELITY and CH-5


def test_fidelity_from_the_rung_file(tree: Tree) -> None:
    three_sessions(tree)
    assert states(tree)["fidelity"] == ("undecided", "not run")
    fidelity(tree, {SYSTEM: fidelity_row("failed")})
    assert states(tree)["fidelity"] == ("failed", None)
    fidelity(tree, {SYSTEM: fidelity_row("undecided", "not resolved")}, bar=False)
    assert states(tree)["fidelity"] == ("undecided", "not resolved")


def test_system_limit_from_the_level_file(tree: Tree) -> None:
    """CH-5: a limit recorded under systems.<id>.limits.<check> makes the check undecided,
    `system limit`, with the publisher's sentence; the row cannot pass."""
    three_sessions(tree)
    fidelity(tree, {SYSTEM: fidelity_row()})
    systems = tree.level["systems"]
    assert isinstance(systems, dict)
    systems[SYSTEM]["limits"] = {"prompt": {"words": "the verifier takes no prompt",
                                            "source": "https://example.org/x"}}  # fmt: skip
    found = checks(tree)
    assert (found["prompt"].state, found["prompt"].cause) == ("undecided", "system limit")
    assert found["prompt"].note == "the verifier takes no prompt"
    assert not passed(found)


def test_error_trials_do_not_count(tree: Tree) -> None:
    """CH-1: an `error` trial decided nothing, like a void one."""
    three_sessions(tree, control_doc=controls(c2=("error", REJECT, REJECT)))
    assert states(tree)["prompt"] == ("undecided", "not resolved")


def test_c1_trial_without_a_position_counts_nowhere(tree: Tree) -> None:
    doc = controls()
    for c in doc["controls"]:  # type: ignore[attr-defined]
        if c["id"] == "C1":
            for t in c["trials"]:
                t["detail"].pop("position")
    three_sessions(tree, control_doc=doc)
    assert states(tree)["reply"] == ("undecided", "not run")


def test_failed_open_of_a_model_file_is_not_an_open(tree: Tree) -> None:
    """A model file whose open failed (`ok` false: removed before verify) read nothing."""
    three_sessions(tree, traces=trace(failed=["/models/model.gguf"]))
    assert states(tree)["no_weight_file"] == ("held", None)


def test_p1_failed_prove_needs_the_provers_reason(tree: Tree) -> None:
    """CH-1: a P1 `prover_failed` whose line is only the harness's "prove exited N" decided
    nothing (the adapter may have failed before the prover ran, FlashProve session 1); with the
    prover's own last line it counts as a refusal."""
    doc = controls(p1=("prover_failed",) * 3)
    for c in doc["controls"]:  # type: ignore[attr-defined]
        if c["id"] == "P1":
            for t in c["trials"]:
                t["raw_last_line"] = "adapter: prove exited 1"
    three_sessions(tree, control_doc=doc)
    assert states(tree)["model"] == ("undecided", "not resolved")
    other = Tree(tree.root / "second")
    doc = controls(p1=("prover_failed",) * 3)
    for c in doc["controls"]:  # type: ignore[attr-defined]
        if c["id"] == "P1":
            for t in c["trials"]:
                t["raw_last_line"] = (
                    "adapter: prove exited 2: commitment does not match the weights"
                )
    three_sessions(other, control_doc=doc)
    assert states(other)["model"] == ("held", None)


def control_run(tree: Tree, *, adapter: str | None = None) -> Path:
    """A complete control run of slot 1 (CH-1b): run.json control true, P1 refused 3 of 3."""
    path = session(tree, 1, 4, control_doc=controls(omit=("C1", "C2", "C3")))
    run = json.loads((path / "run.json").read_text())
    (path / "run.json").write_text(json.dumps({**run, "control": True}))
    if adapter is not None:
        manifest = json.loads((path / "manifest.json").read_text())
        manifest["system"]["adapter_commit"] = adapter
        (path / "manifest.json").write_text(json.dumps(manifest))
    return path


def test_p1_from_a_control_run_at_the_rows_pin(tree: Tree) -> None:
    """CH-1b: MODEL takes P1 from a complete control run at the counted sessions' pin; one at
    another pin decides nothing; a control run is never a session."""
    three_sessions(tree, control_doc=controls(omit=("P1",)))
    assert states(tree)["model"] == ("undecided", "not run")
    control_run(tree)
    assert states(tree)["model"] == ("held", None)
    assert states(tree)["run"] == ("held", None)  # still three sessions, none incomplete
    other = Tree(tree.root / "second")
    three_sessions(other, control_doc=controls(omit=("P1",)))
    control_run(other, adapter="b" * 40)
    assert states(other)["model"] == ("undecided", "not run")


def reverify(run_dir: Path, *, digest: str = "sha256:" + "ab" * 32) -> None:
    """A reverify/ of every proof of `run_dir`, accepted, traced with no GPU (CH-4a); the
    session's manifest records each proof's sha256 as `sha256:abab...`."""
    run = json.loads((run_dir / "run.json").read_text())
    manifest = json.loads((run_dir / "manifest.json").read_text())
    manifest["proofs"] = [{"proof_id": p["proof_id"], "digest": "sha256:" + "ab" * 32}
                          for p in run["proofs"]]  # fmt: skip
    (run_dir / "manifest.json").write_text(json.dumps(manifest))
    (run_dir / "reverify" / "verify-trace").mkdir(parents=True)
    rows = []
    for p in run["proofs"]:
        name = f"reverify/verify-trace/{p['proof_id']}.json"
        (run_dir / name).write_text(json.dumps(trace()))
        rows.append({"proof_id": p["proof_id"], "verdict": "accept", "trace": name,
                     "proof_digest": digest})  # fmt: skip
    doc = {"schema": "reverify/1", "run_id": run["run_id"], "image": {"ref": None},
           "proofs": rows}  # fmt: skip
    (run_dir / "reverify" / "reverify.json").write_text(json.dumps(doc))


def test_a_reverify_on_a_gpu_less_host_stands_for_the_sessions_verdicts(tree: Tree) -> None:
    """CH-4a: every verdict traced with a GPU visible holds once a re-verify of the same run
    (same proof bytes by sha256) traced each proof with none; one of other bytes counts not."""
    runs = three_sessions(tree, traces=trace(gpu=True))
    assert states(tree)["no_weight_file"] == ("undecided", "not resolved")
    for run_dir in runs[:2]:
        reverify(run_dir)
    reverify(runs[2], digest="sha256:" + "0" * 64)
    assert states(tree)["no_weight_file"] == ("undecided", "not resolved")
    other = Tree(tree.root / "second")
    for run_dir in three_sessions(other, traces=trace(gpu=True)):
        reverify(run_dir)
    assert states(other)["no_weight_file"] == ("held", None)


def test_a_gpu_host_session_without_kept_proofs_gives_its_slot_to_a_later_one(tree: Tree) -> None:
    """SE-3a: slot 1's session verified with a GPU visible and was never re-verified; the first
    later complete session of slot 1 at the same pin whose verdicts meet CH-4 counts instead, and
    the replaced one is listed. At another adapter commit it does not replace it."""
    first = session(tree, 1, 1, traces=trace(gpu=True))
    session(tree, 2, 2)
    session(tree, 3, 3)
    later = session(tree, 1, 4)
    assert states(tree)["no_weight_file"] == ("held", None)
    rows = row_sessions(tree.root, RELEASE, tree.level, RUNG, SYSTEM)
    assert rows.counted[1].path.endswith(later.name)
    assert [(a.path.split("/")[-1], b.path.split("/")[-1]) for a, b, _ in rows.replaced] == [
        (first.name, later.name)
    ]
    other = Tree(tree.root / "second")
    session(other, 1, 1, traces=trace(gpu=True))
    session(other, 2, 2)
    session(other, 3, 3)
    moved = session(other, 1, 4)
    manifest = json.loads((moved / "manifest.json").read_text())
    manifest["system"]["adapter_commit"] = "b" * 40
    (moved / "manifest.json").write_text(json.dumps(manifest))
    assert states(other)["no_weight_file"] == ("undecided", "not resolved")
    assert row_sessions(other.root, RELEASE, other.level, RUNG, SYSTEM).replaced == []


def test_p1_line_with_a_python_exception_decides_nothing(tree: Tree) -> None:
    """CH-1a: "prove exited 1: FileNotFoundError: ..." is the adapter's failure, not a refusal."""
    doc = controls(p1=("prover_failed",) * 3)
    for c in doc["controls"]:  # type: ignore[attr-defined]
        if c["id"] == "P1":
            for t in c["trials"]:
                t["raw_last_line"] = "adapter: prove exited 1: FileNotFoundError: [Errno 2] x"
    three_sessions(tree, control_doc=doc)
    assert states(tree)["model"] == ("undecided", "not resolved")
