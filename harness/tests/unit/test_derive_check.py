import json
import math
from pathlib import Path

import pytest

from iproofs import cli
from iproofs.validate import check_derived

ROOT = Path(__file__).resolve().parents[3]
WORKED = ROOT / "harness/tests/fixtures/derive/worked-example"
DERIVED = sorted(
    k
    for k, v in json.loads((WORKED / "run.json").read_text())["metrics"].items()
    if v["grade"] == "derived" and v["value"] is not None
)


def edited(tmp_path: Path, edit: object) -> list[str]:
    doc = json.loads((WORKED / "run.json").read_text())
    edit(doc)  # type: ignore[operator]
    (tmp_path / "run.json").write_text(json.dumps(doc))
    return [f.line() for f in check_derived(tmp_path / "run.json", ROOT)]


def test_derive_check_worked_example_clean() -> None:
    assert check_derived(WORKED / "run.json", ROOT) == []


@pytest.mark.parametrize("name", DERIVED)
def test_derive_check_detects_one_ulp(tmp_path: Path, name: str) -> None:
    """P-CHECK-DETECTS: any stored derived value moved by one ulp fails DER-1."""

    def bump(doc: dict[str, dict[str, dict[str, float]]]) -> None:
        q = doc["metrics"][name]
        q["value"] = math.nextafter(q["value"], math.inf)

    lines = edited(tmp_path, bump)
    assert any(f"#/metrics/{name} DER-1:" in line for line in lines), lines


def test_derive_check_unknown_formula(tmp_path: Path) -> None:
    def rename(doc: dict[str, dict[str, dict[str, dict[str, str]]]]) -> None:
        doc["metrics"]["proof_bytes_per_token"]["source"]["ref"] = "derive:D-NOPE@0.1.0"

    assert any("DER-2: unknown formula D-NOPE" in line for line in edited(tmp_path, rename))


def test_derive_check_missing_input(tmp_path: Path) -> None:
    def drop(doc: dict[str, dict[str, object]]) -> None:
        del doc["metrics"]["proof_bytes_total"]

    # run.json in tmp_path, so the inputs of proof_bytes_per_token still point at the fixture;
    # pointing them at the edited copy makes one of them unresolvable
    def repoint(doc: dict[str, dict[str, dict[str, dict[str, list[str]]]]]) -> None:
        src = doc["metrics"]["proof_bytes_per_token"]["source"]
        src["inputs"] = [
            p.replace("proof_bytes_total", "proof_bytes_absent") for p in src["inputs"]
        ]

    assert any("DER-3: inputs missing" in line for line in edited(tmp_path, repoint))
    assert edited(tmp_path, drop) == []  # inputs still resolve in the fixture


def test_derive_check_null_reason_must_match(tmp_path: Path) -> None:
    def null(doc: dict[str, dict[str, dict[str, object]]]) -> None:
        doc["metrics"]["verify_single_thread_seconds_per_token"]["null_reason"] = "not_applicable"

    assert any(
        "verify_single_thread_seconds_per_token DER-1" in line for line in edited(tmp_path, null)
    )


PROVER_ONLY = ["tokens_covered_per_proof"] + [
    f"seconds_per_active_weight_bit_token_{s}"
    for s in ("prove.steady", "prove.session", "whole_wall")
]


def test_derive_check_reference_tokens_per_proof(tmp_path: Path) -> None:
    """INV-DERIVE-6, INV-DERIVE-7: in a `kind: reference` run, D-TPP and D-SPAB-S recompute
    as null `not_applicable`; a stored value fails DER-1."""

    def reference(doc: dict[str, object]) -> None:
        doc["system_kind"] = "reference"

    def reference_null(doc: dict[str, dict[str, dict[str, object]]]) -> None:
        reference(doc)  # type: ignore[arg-type]
        for name in PROVER_ONLY:
            q = doc["metrics"][name]
            q["value"], q["null_reason"] = None, "not_applicable"

    found = edited(tmp_path, reference)
    for name in PROVER_ONLY:
        assert any(f"{name} DER-1" in line for line in found), name
    assert edited(tmp_path, reference_null) == []


def test_g4_gate_fixture_fails(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["derive", str(ROOT / "harness/tests/fixtures/gates/G4"), "--check"]) == 1
    assert "rate_prove.steady DER-1" in capsys.readouterr().out


def test_cli_derive_check_clean(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["derive", str(WORKED), "--check"]) == 0


def test_derive_check_absent_weight_bits(tmp_path: Path) -> None:
    """RFC-0004 D-SPAB-S null rule: an unresolvable weight-bits input (a run without
    `inputs.weight_bits`); a stored null `missing_input` recomputes as it is, a stored value
    fails DER-3."""
    name = "seconds_per_active_weight_bit_token_prove.steady"

    def absent(doc: dict[str, dict[str, dict[str, dict[str, list[str]]]]]) -> None:
        src = doc["metrics"][name]["source"]
        src["inputs"] = [
            p.replace("/inputs/weight_bits", "/inputs/weight_bits_absent") for p in src["inputs"]
        ]

    def absent_null(doc: dict[str, dict[str, dict[str, object]]]) -> None:
        absent(doc)  # type: ignore[arg-type]
        q = doc["metrics"][name]
        q["value"], q["null_reason"] = None, "missing_input"

    assert any(f"{name} DER-3: inputs missing" in line for line in edited(tmp_path, absent))
    assert edited(tmp_path, absent_null) == []
