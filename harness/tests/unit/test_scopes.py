from pathlib import Path

import pytest

from iproofs.derive import scope_seconds, span_seconds
from iproofs.errors import ErrorKind, IProofsError
from iproofs.schema import SchemaRegistry

S = 1_000_000_000  # ns per second
RUN = "results/v0.1/fake/2026-11-20-fake-fake-tiny-ci-ci-cpu-1/run.json"
EVENTS = {
    "info.start": 0, "info.end": 1 * S,
    "setup.start": 1 * S, "setup.end": 3 * S,
    "commit.start": 4 * S, "commit.end": 6 * S,
    "prove.start": 7 * S, "prove.end": 16 * S,
}  # fmt: skip


def values(out: dict[str, dict[str, object]]) -> dict[str, object]:
    return {k: v["value"] for k, v in out.items()}


def test_scopes_from_events_and_releases() -> None:
    # Release times 10 s, 12 s, 15 s: steady covers r_1..r_k = 5 s.
    out = scope_seconds(EVENTS, [12 * S, 10 * S, 15 * S], observable=True, run_json=RUN)
    assert values(out) == {
        "info_seconds": 1.0,
        "setup_seconds": 2.0,
        "commit_seconds": 2.0,
        "prove_call_seconds": 9.0,
        "prove_session_seconds": 8.0,
        "whole_wall_seconds": 11.0,  # starts at the commit call, not at setup
        "prove_steady_seconds": 5.0,
    }
    steady = out["prove_steady_seconds"]
    assert steady["scope"] == "prove.steady"
    assert steady["unit"] == "s"
    assert steady["grade"] == "measured"
    assert steady["tier"] == "reported"
    assert steady["source"] == {"kind": "harness", "ref": f"{RUN}#/events"}
    assert out["whole_wall_seconds"]["scope"] == "whole_wall"


def test_steady_k1() -> None:
    """TC-STEADY-K1: one proof gives null steady with fewer_than_two_proofs."""
    out = scope_seconds(EVENTS, [10 * S], observable=True, run_json=RUN)
    assert out["prove_steady_seconds"]["value"] is None
    assert out["prove_steady_seconds"]["null_reason"] == "fewer_than_two_proofs"
    assert out["prove_session_seconds"]["value"] == 3.0


def test_steady_unobservable() -> None:
    """TC-STEADY-UNOBSERVABLE: session and whole wall stay, steady is null."""
    out = scope_seconds(EVENTS, [10 * S, 15 * S], observable=False, run_json=RUN)
    assert out["prove_steady_seconds"]["null_reason"] == "not_externally_observable"
    assert out["prove_session_seconds"]["value"] == 8.0
    assert out["whole_wall_seconds"]["value"] == 11.0


def test_scope_order() -> None:
    """TC-SCOPE-ORDER: a release before the prove call start is an internal error."""
    with pytest.raises(IProofsError) as e:
        scope_seconds(EVENTS, [6 * S, 10 * S], observable=True, run_json=RUN)
    assert e.value.kind is ErrorKind.INTERNAL
    assert "INV-SCOPE-4" in e.value.message


def test_no_proofs_reports_only_call_scopes() -> None:
    out = scope_seconds(EVENTS, [], observable=True, run_json=RUN)
    assert "prove_session_seconds" not in out
    assert out["prove_call_seconds"]["value"] == 9.0


def test_span_seconds() -> None:
    assert span_seconds(1, 1_500_000_001) == 1.5


def test_outputs_are_schema_valid_quantities() -> None:
    registry = SchemaRegistry.from_tree(Path(__file__).resolve().parents[3] / "schema")
    for releases, observable in [([10 * S, 15 * S], True), ([10 * S], True), ([10 * S], False)]:
        out = scope_seconds(EVENTS, releases, observable=observable, run_json=RUN)
        for name, q in out.items():
            assert registry.errors("quantity/1", q, def_name="quantity") == [], name
