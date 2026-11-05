"""controls.yaml (RFC-0008 §System-specific controls): every edge it names is the claim card's,
and a control job through stub_upstream.py yields a binding report the harness reads as unbound."""

import dataclasses
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml
from sash_fixtures import REGISTRY, SYSTEM, load, run_step

from iproofs.controls import VerifyCall, VerifyResult, edge_unbound, system_control_record
from iproofs.model import SystemControl, SystemControls
from iproofs.model import load as load_doc

DOC = load_doc(SYSTEM / "controls.yaml", REGISTRY)
assert isinstance(DOC, SystemControls)
CONTROLS = DOC.controls
CARD = yaml.safe_load((SYSTEM / "claim.yaml").read_text())["binding"]["edges"]
PROMPT, TOK = list(range(128)), list(range(1000, 1064))


def test_edges_are_the_claim_cards() -> None:
    for c in CONTROLS:
        assert c.kind == "weakened_prover"
        assert c.expected == ("accepted",)
        assert "eb95bfa887299d1637550228d42086c27cbb2b3b" in (c.source or "")
        [flag] = c.control_flags or ("",)
        [edge] = [e for e in CARD if e["edge"] == c.requires_unbound_edge]
        assert flag == edge["switch"] or flag in edge["edge"]  # the card names the switch
    # one control per switch the card names, plus --unsound-argmax-lax
    switches = {e["switch"] for e in CARD} - {None}
    assert {f for c in CONTROLS for f in c.control_flags or ()} == {
        *switches,
        "--unsound-argmax-lax",
    }


def test_report_names_are_the_claim_cards(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = load(tmp_path, monkeypatch)
    assert list(adapter.CARD_EDGES) == [e["edge"] for e in CARD]


def prove(adapter: ModuleType, **fields: Any) -> dict[str, Any]:
    adapter.host("/io/prompts.jsonl").write_text(json.dumps(PROMPT) + "\n")
    c = run_step(adapter, "commit", model_dir="/models")
    job = {"commitment_id": c["commitment_id"], "model_dir": "/models",
           "prover_files": c["prover_files"], "prompts_file": "/io/prompts.jsonl",
           "batch_size": 1, "batches": 1}  # fmt: skip
    out = run_step(adapter, "prove", **job, **fields)
    report = json.loads(adapter.host(out["binding_report"]).read_text())
    return {"commit": c, "report": report}


@pytest.mark.parametrize("control", CONTROLS, ids=lambda c: c.id)
def test_weakened_prover_requires_unbound_edge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, control: SystemControl
) -> None:
    """The control's prove marks its edge unbound and the record passes; an honest prove's
    report marks it bound, so the same accepted outcome would not pass."""
    monkeypatch.setenv("IPROOFS_SASH_STUB_TOK", json.dumps(TOK))
    (tmp_path / "honest").mkdir()
    (tmp_path / "control").mkdir()
    honest = prove(load(tmp_path / "honest", monkeypatch))["report"]
    assert control.requires_unbound_edge
    assert honest["edges"][control.requires_unbound_edge] == "bound"
    assert not edge_unbound(honest, control.requires_unbound_edge)

    adapter = load(tmp_path / "control", monkeypatch)
    done = prove(adapter, control=True, control_flags=list(control.control_flags or ()))
    flags = {a for c in adapter.host("/io/commands.jsonl").read_text().splitlines()
             for a in json.loads(c)["argv"] if a.startswith("--unsound-")}  # fmt: skip
    assert flags == set(control.control_flags or ())
    assert done["report"]["unsound_skips"]

    def verify(call: VerifyCall) -> VerifyResult:
        c = done["commit"]
        out = run_step(adapter, "verify", commitment_id=c["commitment_id"],
                       verifier_files=c["verifier_files"], request=PROMPT, claimed_output=TOK,
                       proof_dir="/io/proofs/req-0")  # fmt: skip
        return VerifyResult(out["verdict"], out["raw_exit_code"], out["raw_last_line"], 0.0)

    call = VerifyCall(control.id, 0, done["commit"]["commitment_id"], tuple(PROMPT), tuple(TOK),
                      adapter.host("/io/proofs/req-0"), (), {})  # fmt: skip
    twin = dataclasses.replace(call, control_id="twin")
    record = system_control_record(control, lambda: ([call], done["report"]), lambda: [twin],
                                   verify)  # fmt: skip
    assert (record["outcome"], record["passed"]) == ("accepted", True)
    record = system_control_record(control, lambda: ([call], honest), lambda: [twin], verify)
    assert record["passed"] is False
