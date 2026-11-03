"""Error branches of iproofs.derive and iproofs.controls, which decide what is published and
so are held to full branch coverage (docs/spec/07 §Coverage)."""

from pathlib import Path

import pytest

from iproofs.controls import (
    HonestProof,
    VerifyCall,
    VerifyResult,
    c6,
    control_record,
    system_control_record,
)
from iproofs.derive import UnknownFormula, formula_of, recompute, statistic, tokens_per_proof
from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import Shape, SystemControl

SHAPE = Shape(prompt_tokens=8, output_tokens=1, batch_size=2, batches_per_session=3,
              context_window=8)  # fmt: skip
REF = "run.json#/metrics/x"


def q(value: float | None, reason: str | None = None) -> dict[str, object]:
    return {"value": value, "unit": "s", "scope": "verify", "grade": "measured",
            "tier": "reported", "source": {"kind": "harness", "ref": REF},
            "null_reason": reason}  # fmt: skip


def test_statistic_over_null_values_keeps_their_reason() -> None:
    out = statistic([(REF, q(None, "not_applicable"))], [], "0")
    assert (out["value"], out["null_reason"]) == (None, "not_applicable")


def test_unknown_token_rule_is_config() -> None:
    with pytest.raises(IProofsError) as e:
        tokens_per_proof("per_layer", SHAPE, None, "p0")
    assert e.value.kind is ErrorKind.CONFIG


def test_unknown_formula_reference() -> None:
    with pytest.raises(UnknownFormula):
        formula_of({"source": {"kind": "derivation", "ref": "not-a-formula"}})
    with pytest.raises(UnknownFormula):
        recompute({"scope": None, "source": {"kind": "derivation", "ref": "derive:D-NONE@0"}},
                  [], 1)  # fmt: skip


def test_recompute_statistics() -> None:
    stored = statistic([(REF, q(2.0)), (REF, q(4.0))], [], "0")
    assert recompute(stored, [(REF, q(2.0)), (REF, q(4.0))], 1) == stored
    failed = statistic([], ["run.json#/failure"], "0")
    assert recompute(failed, [("run.json#/failure", None)], 1) == failed


def test_empty_part_is_internal(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/body.bin").write_bytes(b"")
    honest = HonestProof("p0", (1,), (2,), "accept", 0, 0)
    with pytest.raises(IProofsError) as e:
        c6(honest, "c", tmp_path / "src", tmp_path / "dst", "0x" + "0" * 16, 0)
    assert e.value.kind is ErrorKind.INTERNAL


def test_twin_error_and_prover_failure() -> None:
    call = VerifyCall("C1", 0, "c", (1,), (2,), Path("/nowhere"), ("a",), {})

    def broken(c: VerifyCall) -> VerifyResult:
        raise IProofsError(ErrorKind.ADAPTER, "verify exited 9")

    record = control_record("C1", lambda: [call], lambda: [call], broken)
    assert (record["outcome"], record["passed"]) == ("error", None)
    assert "twin" in str(record["note"])

    def no_prover() -> tuple[list[VerifyCall], object]:
        raise IProofsError(ErrorKind.ADAPTER, "prove exited 3")

    control = SystemControl(
        id="skip-x",
        kind="weakened_prover",
        expected=("accepted",),
        control_flags=("--unsound-skip-x",),
        requires_unbound_edge="x",
    )
    record = system_control_record(control, no_prover, lambda: [call], broken)
    assert (record["outcome"], record["passed"]) == ("prover_failed", False)
