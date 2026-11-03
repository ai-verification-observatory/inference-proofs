"""Derived metrics and statistics from stored raw quantities (RFC-0004).

INV-ARCH-5: every function here is pure: no clock, no file writes, no network.
"""

from collections.abc import Callable, Mapping, Sequence

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


# ---------------------------------------------------------------- repetition-level formulas

RATE_SCOPES = (Scope.PROVE_STEADY, Scope.PROVE_SESSION, Scope.WHOLE_WALL)
_SECONDS = {
    Scope.PROVE_STEADY: "prove_steady_seconds",
    Scope.PROVE_SESSION: "prove_session_seconds",
    Scope.WHOLE_WALL: "whole_wall_seconds",
}
_TIER_ORDER = [str(t) for t in (Tier.REPORTED, Tier.PEER_REVIEWED, Tier.REPRODUCED)]

Input = tuple[str, Mapping[str, object] | None]  # (JSON pointer, quantity or None if absent)


class _Null(Exception):
    """A formula input is null, missing or a zero denominator: the result is null."""

    def __init__(self, reason: NullReason) -> None:
        self.reason = reason


def _value(q: Mapping[str, object] | None) -> float:
    if q is None:
        raise _Null(NullReason.MISSING_INPUT)
    if q["value"] is None:
        raise _Null(NullReason(str(q["null_reason"])))
    v = q["value"]
    assert isinstance(v, int | float)
    return float(v)


def nonzero(x: float) -> float:
    """A zero denominator gives a null result, never NaN or infinity (TC-NULL-DIV)."""
    if x == 0:
        raise _Null(NullReason.NOT_APPLICABLE)
    return x


def derived(
    formula: str,
    version: str,
    unit: Unit,
    scope: Scope | None,
    inputs: Sequence[Input],
    compute: Callable[[list[float]], float],
) -> QuantityTree:
    """Evaluate `compute` on the input values in order; null with a reason when it cannot."""
    present = [q for _, q in inputs if q is not None]
    for q in present:
        source = q["source"]
        assert isinstance(source, Mapping)
        if source["kind"] == SourceKind.ADAPTER:  # INV-GRADE-2
            raise IProofsError(
                ErrorKind.INTERNAL, f"{formula}: adapter-reported input cannot feed a formula"
            )
    try:
        value: float | None = compute([_value(q) for _, q in inputs])
        reason: NullReason | None = None
    except _Null as null:
        value, reason = None, null.reason
    tiers = [str(q["tier"]) for q in present] or [str(Tier.REPORTED)]
    out: QuantityTree = {
        "value": value,
        "unit": str(unit),
        "scope": None if scope is None else str(scope),
        "grade": str(Grade.DERIVED),
        "tier": min(tiers, key=_TIER_ORDER.index),  # INV-DERIVE-4
        "source": {
            "kind": str(SourceKind.DERIVATION),
            "ref": f"derive:{formula}@{version}",
            "inputs": [ref for ref, _ in inputs],
        },
        "null_reason": None if reason is None else str(reason),
    }
    flags: dict[str, bool] = {}
    for q in present:  # INV-QTY-9: quality flags are the OR of the inputs
        quality = q.get("quality")
        if isinstance(quality, Mapping):
            for flag, on in quality.items():
                flags[str(flag)] = flags.get(str(flag), False) or bool(on)
    if flags:
        out["quality"] = flags
    return out


def derive_repetition(
    metrics: Mapping[str, QuantityTree],
    *,
    run_json: str,
    harness_version: str,
    gpus: int,
    price: Input,
    active_parameters: Input,
    first_proof_tokens: Input,
) -> dict[str, QuantityTree]:
    """Every repetition-level formula of RFC-0004 over one repetition's recorded metrics.

    `price`, `active_parameters` and `first_proof_tokens` are (pointer, quantity) pairs from
    the reference file, the workload record and run.json `proofs[0]`. Each formula is
    evaluated left to right as written in the RFC table (INV-DERIVE-5).
    """
    v = harness_version
    out: dict[str, QuantityTree] = {}

    def metric(name: str) -> Input:
        return (f"{run_json}#/metrics/{name}", metrics.get(name) or out.get(name))

    for scope in RATE_SCOPES:
        sec = metric(_SECONDS[scope])
        tok = metric(
            "tokens_covered_steady" if scope is Scope.PROVE_STEADY else "tokens_covered_total"
        )
        out[f"rate_{scope}"] = derived(
            "D-RATE-S", v, Unit.TOKEN_PER_S, scope, [tok, sec],
            lambda x: nonzero(x[0]) / nonzero(x[1]),
        )  # fmt: skip
        out[f"seconds_per_token_{scope}"] = derived(
            "D-SPT-S", v, Unit.S_PER_TOKEN, scope, [sec, tok],
            lambda x: nonzero(x[0]) / nonzero(x[1]),
        )  # fmt: skip
        out[f"cost_per_1k_tokens_{scope}"] = derived(
            "D-COST-1K-S", v, Unit.USD_PER_1K_TOKEN, scope,
            [metric(f"seconds_per_token_{scope}"), price],
            lambda x: x[0] * 1000 * gpus * x[1] / 3600,
        )  # fmt: skip
        out[f"active_param_tokens_per_second_{scope}"] = derived(
            "D-APT-S", v, Unit.PARAM_TOKEN_PER_S, scope,
            [metric(f"rate_{scope}"), active_parameters], lambda x: x[0] * x[1],
        )  # fmt: skip
    commit = [metric("commit_seconds"), metric("tokens_covered_total"), metric("requests_count")]
    for h in (1, 1000):
        out[f"commit_seconds_per_token_h{h}"] = derived(
            f"D-COMMIT-AMORT-H{h}", v, Unit.S_PER_TOKEN, Scope.COMMIT, commit,
            lambda x: x[0] / nonzero(nonzero(x[1]) / nonzero(x[2]) * h),  # noqa: B023 (called now)
        )  # fmt: skip
    total = metric("tokens_covered_total")
    out["proof_bytes_per_token"] = derived(
        "D-BPT", v, Unit.B_PER_TOKEN, None, [metric("proof_bytes_total"), total],
        lambda x: x[0] / nonzero(x[1]),
    )  # fmt: skip
    out["verify_seconds_per_token"] = derived(
        "D-VSPT", v, Unit.S_PER_TOKEN, Scope.VERIFY, [metric("verify_seconds_total"), total],
        lambda x: x[0] / nonzero(x[1]),
    )  # fmt: skip
    out["verify_single_thread_seconds_per_token"] = derived(
        "D-VSPT-1T", v, Unit.S_PER_TOKEN, Scope.VERIFY_SINGLE_THREAD,
        [metric("verify_single_thread_seconds"), first_proof_tokens],
        lambda x: x[0] / nonzero(x[1]),
    )  # fmt: skip
    return out
