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


def _b24(order: list[int]) -> tuple[list[int], list[int | None]]:
    """Releases at 10 s + 1 s per batch: batch j releases at 10 + j s, request i of batch j at
    10 + j + i/1000 s (in `order`)."""
    releases = [10 * S + (i // 24) * S + (i % 24) * 1_000_000 for i in order]
    return releases, list(order)


def test_steady_batch() -> None:
    """TC-STEADY-BATCH (INV-SCOPE-5): b = 24, 5 batches, 120 releases. The start is the last
    release of requests 0 to 23 (10.023 s), the end the last release (14.023 s)."""
    releases, indices = _b24(list(range(120)))
    out = scope_seconds(EVENTS | {"prove.end": 20 * S}, releases, observable=True, run_json=RUN,
                        batch_size=24, request_indices=indices)  # fmt: skip
    assert out["prove_steady_seconds"]["value"] == pytest.approx(4.0)
    assert out["prove_session_seconds"]["value"] == pytest.approx(14.023 - 7)


def test_steady_batch_interleaved() -> None:
    """An interleaved release order (request 30 released at 10.0105 s, before request 23 at
    10.023 s) gives the same start: the last release of the first batch. Request 30 leaves
    the steady tokens (test_tokens.py); the window is unchanged. With every later request
    released before the first batch's last, there is no steady scope."""
    releases, indices = _b24(list(range(120)))
    releases[30] = 10 * S + 10_500_000
    out = scope_seconds(EVENTS | {"prove.end": 20 * S}, releases, observable=True, run_json=RUN,
                        batch_size=24, request_indices=indices)  # fmt: skip
    assert out["prove_steady_seconds"]["value"] == pytest.approx(4.0)
    releases, indices = _b24(list(range(48)))
    releases[23] = 12 * S  # the first batch ends after the second
    out = scope_seconds(EVENTS | {"prove.end": 20 * S}, releases, observable=True, run_json=RUN,
                        batch_size=24, request_indices=indices)  # fmt: skip
    assert out["prove_steady_seconds"]["null_reason"] == "fewer_than_two_proofs"
    releases, indices = _b24(list(range(24, 48)))  # no first-batch release at all
    out = scope_seconds(EVENTS | {"prove.end": 20 * S}, releases, observable=True, run_json=RUN,
                        batch_size=24, request_indices=indices)  # fmt: skip
    assert out["prove_steady_seconds"]["null_reason"] == "fewer_than_two_proofs"


def test_steady_batch_one_batch() -> None:
    """b = 24 and k = 24: one batch, so no steady scope."""
    releases, indices = _b24(list(range(24)))
    out = scope_seconds(EVENTS, releases, observable=True, run_json=RUN, batch_size=24,
                        request_indices=indices)  # fmt: skip
    assert out["prove_steady_seconds"]["null_reason"] == "fewer_than_two_proofs"


def test_steady_batch_missing_index() -> None:
    """b = 24 and a proof without `request_index`: missing_input."""
    releases, indices = _b24(list(range(48)))
    indices[40] = None
    out = scope_seconds(EVENTS, releases, observable=True, run_json=RUN, batch_size=24,
                        request_indices=indices)  # fmt: skip
    assert out["prove_steady_seconds"]["null_reason"] == "missing_input"


def test_steady_batch_one_is_release_order() -> None:
    """b = 1 keeps r_1 to r_k whatever the indices say (INV-SCOPE-5, as before)."""
    out = scope_seconds(EVENTS, [12 * S, 10 * S, 15 * S], observable=True, run_json=RUN,
                        batch_size=1, request_indices=[2, 0, 1])  # fmt: skip
    assert out["prove_steady_seconds"]["value"] == 5.0
