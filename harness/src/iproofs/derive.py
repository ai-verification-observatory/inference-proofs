"""Derived metrics and statistics from stored raw quantities (RFC-0004).

INV-ARCH-5: every function here is pure: no clock, no file writes, no network.
"""

from collections.abc import Mapping, Sequence

from iproofs.errors import ErrorKind, IProofsError
from iproofs.quantity import Grade, NullReason, Scope, SourceKind, Tier, Unit

QuantityTree = dict[str, object]

# Call steps whose `<step>.start` and `<step>.end` events bound a `<step>_seconds` metric.
CALL_SCOPES = {"info": Scope.SETUP, "setup": Scope.SETUP, "commit": Scope.COMMIT}


def span_seconds(start_ns: int, end_ns: int) -> float:
    """RFC-0011 C-2: seconds between two monotonic events."""
    return (end_ns - start_ns) / 1e9


def measured(
    value: float | None, unit: Unit, scope: Scope | None, ref: str, null_reason: NullReason | None
) -> QuantityTree:
    """A harness-measured quantity as stored in run.json (tier reported, INV-QTY-4)."""
    return {
        "value": value,
        "unit": str(unit),
        "scope": None if scope is None else str(scope),
        "grade": str(Grade.MEASURED),
        "tier": str(Tier.REPORTED),
        "source": {"kind": str(SourceKind.HARNESS), "ref": ref},
        "null_reason": None if null_reason is None else str(null_reason),
    }


def scope_seconds(
    events: Mapping[str, int],
    releases: Sequence[int],
    *,
    observable: bool,
    run_json: str,
) -> dict[str, QuantityTree]:
    """Seconds per timing scope from call events and proof release times (RFC-0004 §Timing scopes).

    `events` maps event names such as `commit.start` to monotonic ns; `releases` holds the
    release times r_1..r_k; `observable` is the release watcher's verdict (INV-SCOPE-3).
    """
    ref = f"{run_json}#/events"
    out: dict[str, QuantityTree] = {}
    for step, scope in CALL_SCOPES.items():
        if f"{step}.start" in events and f"{step}.end" in events:
            secs = span_seconds(events[f"{step}.start"], events[f"{step}.end"])
            out[f"{step}_seconds"] = measured(secs, Unit.S, scope, ref, None)
    if "prove.start" in events and "prove.end" in events:
        call = span_seconds(events["prove.start"], events["prove.end"])
        out["prove_call_seconds"] = measured(call, Unit.S, Scope.PROVE_SESSION, ref, None)
    if not releases or "prove.start" not in events:
        return out
    r = sorted(releases)
    r_1, r_k = r[0], r[-1]
    order = [events.get("commit.start"), events["prove.start"], r_1, r_k]
    known = [t for t in order if t is not None]
    if known != sorted(known):  # INV-SCOPE-4
        raise IProofsError(
            ErrorKind.INTERNAL,
            f"INV-SCOPE-4 violated: commit start, prove start, r_1, r_k = {order}",
        )
    session = span_seconds(events["prove.start"], r_k)
    out["prove_session_seconds"] = measured(session, Unit.S, Scope.PROVE_SESSION, ref, None)
    if "commit.start" in events:
        whole = span_seconds(events["commit.start"], r_k)
        out["whole_wall_seconds"] = measured(whole, Unit.S, Scope.WHOLE_WALL, ref, None)
    if not observable:  # INV-SCOPE-3
        steady = measured(None, Unit.S, Scope.PROVE_STEADY, ref,
                          NullReason.NOT_EXTERNALLY_OBSERVABLE)  # fmt: skip
    elif len(r) < 2:  # INV-SCOPE-2
        steady = measured(None, Unit.S, Scope.PROVE_STEADY, ref, NullReason.FEWER_THAN_TWO_PROOFS)
    else:
        steady = measured(span_seconds(r_1, r_k), Unit.S, Scope.PROVE_STEADY, ref, None)
    out["prove_steady_seconds"] = steady
    return out
