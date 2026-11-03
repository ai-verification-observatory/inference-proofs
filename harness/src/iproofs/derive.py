"""Derived metrics and statistics from stored raw quantities (RFC-0004).

INV-ARCH-5: every function here is pure: no clock, no file writes, no network.
"""

import statistics
from collections.abc import Callable, Mapping, Sequence

from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import Shape
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
        steady = measured(
            None, Unit.S, Scope.PROVE_STEADY, ref, NullReason.NOT_EXTERNALLY_OBSERVABLE
        )
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
        if q.get("grade") == Grade.EXTERNAL and formula != "P-CAMPAIGN":  # INV-MAP-1
            raise IProofsError(
                ErrorKind.INTERNAL,
                f"{formula}: an external figure cannot feed a formula over measured inputs",
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


def _ratio(x: list[float], gpus: int) -> float:
    return nonzero(x[0]) / nonzero(x[1])


def _over(x: list[float], gpus: int) -> float:
    return x[0] / nonzero(x[1])


def _amortised(h: int) -> Callable[[list[float], int], float]:
    def f(x: list[float], gpus: int) -> float:
        return x[0] / nonzero(nonzero(x[1]) / nonzero(x[2]) * h)

    return f


# Formula id -> evaluation over input values in `source.inputs` order (RFC-0004 catalogue).
COMPUTE: dict[str, Callable[[list[float], int], float]] = {
    "D-RATE-S": _ratio,
    "D-SPT-S": _ratio,
    "D-COST-1K-S": lambda x, gpus: x[0] * 1000 * gpus * x[1] / 3600,
    "D-APT-S": lambda x, gpus: x[0] * x[1],
    "D-COMMIT-AMORT-H1": _amortised(1),
    "D-COMMIT-AMORT-H1000": _amortised(1000),
    "D-BPT": _over,
    "D-VSPT": _over,
    "D-VSPT-1T": _over,
}


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
    out: dict[str, QuantityTree] = {}

    def metric(name: str) -> Input:
        return (f"{run_json}#/metrics/{name}", metrics.get(name) or out.get(name))

    def put(name: str, formula: str, unit: Unit, scope: Scope | None, inputs: list[Input]) -> None:
        compute = COMPUTE[formula]
        out[name] = derived(
            formula, harness_version, unit, scope, inputs, lambda x: compute(x, gpus)
        )

    for scope in RATE_SCOPES:
        sec = metric(_SECONDS[scope])
        tok = metric(
            "tokens_covered_steady" if scope is Scope.PROVE_STEADY else "tokens_covered_total"
        )
        put(f"rate_{scope}", "D-RATE-S", Unit.TOKEN_PER_S, scope, [tok, sec])
        put(f"seconds_per_token_{scope}", "D-SPT-S", Unit.S_PER_TOKEN, scope, [sec, tok])
        put(
            f"cost_per_1k_tokens_{scope}",
            "D-COST-1K-S",
            Unit.USD_PER_1K_TOKEN,
            scope,
            [metric(f"seconds_per_token_{scope}"), price],
        )
        put(
            f"active_param_tokens_per_second_{scope}",
            "D-APT-S",
            Unit.PARAM_TOKEN_PER_S,
            scope,
            [metric(f"rate_{scope}"), active_parameters],
        )
    commit = [metric("commit_seconds"), metric("tokens_covered_total"), metric("requests_count")]
    for h in (1, 1000):
        put(
            f"commit_seconds_per_token_h{h}",
            f"D-COMMIT-AMORT-H{h}",
            Unit.S_PER_TOKEN,
            Scope.COMMIT,
            commit,
        )
    total = metric("tokens_covered_total")
    put(
        "proof_bytes_per_token",
        "D-BPT",
        Unit.B_PER_TOKEN,
        None,
        [metric("proof_bytes_total"), total],
    )
    put(
        "verify_seconds_per_token",
        "D-VSPT",
        Unit.S_PER_TOKEN,
        Scope.VERIFY,
        [metric("verify_seconds_total"), total],
    )
    put(
        "verify_single_thread_seconds_per_token",
        "D-VSPT-1T",
        Unit.S_PER_TOKEN,
        Scope.VERIFY_SINGLE_THREAD,
        [metric("verify_single_thread_seconds"), first_proof_tokens],
    )
    return out


# ---------------------------------------------------------------- configuration statistics

MIN_REPETITIONS = 3

# Formula registry: every id a derived quantity may name in `source.ref` (INV-QTY-6).
FORMULAS = {
    "D-RATE-S": "T(S) / sec(S)",
    "D-SPT-S": "sec(S) / T(S)",
    "D-COST-1K-S": "D-SPT-S * 1000 * gpus * price / 3600",
    "D-COMMIT-AMORT-H1": "commit_seconds / (tokens_covered_total / requests_count * 1)",
    "D-COMMIT-AMORT-H1000": "commit_seconds / (tokens_covered_total / requests_count * 1000)",
    "D-APT-S": "D-RATE-S * active_parameters_per_token",
    "D-BPT": "proof_bytes_total / tokens_covered_total",
    "D-VSPT": "verify_seconds_total / tokens_covered_total",
    "D-VSPT-1T": "first-proof single-thread verify seconds / first-proof tokens",
    "D-STAT": "over successful repetitions in repetition order: statistics.mean, "
    "statistics.stdev (n - 1, null when n < 2), min, max",
}


def insufficient_repetitions(n: int) -> bool:
    """Fewer than three successful repetitions: published with the label, never hidden."""
    return n < MIN_REPETITIONS


def statistic(inputs: Sequence[Input], failed: Sequence[str], version: str) -> QuantityTree:
    """D-STAT over one metric's per-repetition values, ordered by repetition (INV-DERIVE-1).

    `inputs` holds one (pointer, quantity) per successful repetition and `failed` one pointer
    per failed repetition (its run.json failure record). Null values are left out of n. With
    no value at all the result is null: `step_failed` when every repetition failed
    (INV-QTY-8), otherwise the inputs' own null reason as a plain quantity.
    """
    present = [q for _, q in inputs if q is not None]
    units = {str(q["unit"]) for q in present}
    scopes = {q["scope"] for q in present}
    if len(units) > 1 or len(scopes) > 1:
        raise IProofsError(
            ErrorKind.INTERNAL, f"D-STAT over mixed units {units} or scopes {scopes}"
        )
    unit = Unit(units.pop()) if units else Unit.COUNT
    scope_value = scopes.pop() if scopes else None
    scope = None if scope_value is None else Scope(str(scope_value))
    values = [float(v) for q in present if isinstance(v := q["value"], int | float)]
    if not values and present:
        reason = NullReason(str(present[0]["null_reason"]))
        return derived("D-STAT", version, unit, scope, inputs, lambda _: _raise(reason))
    n = len(values)
    if n == 0:
        if not failed:
            raise IProofsError(ErrorKind.INTERNAL, "D-STAT over no repetition at all")
        out = derived("D-STAT", version, unit, scope, [(r, None) for r in failed], lambda _: 0.0)
        out["null_reason"] = str(NullReason.STEP_FAILED)
        out["stats"] = {
            "n": 0,
            "n_failed": len(failed),
            "mean": None,
            "stdev": None,
            "min": None,
            "max": None,
        }
        return out
    mean = statistics.mean(values)
    stats = {
        "n": n,
        "n_failed": len(failed),
        "mean": mean,
        "stdev": statistics.stdev(values) if n >= 2 else None,
        "min": min(values),
        "max": max(values),
    }
    valued = [(ref, q) for ref, q in inputs if q is not None and q["value"] is not None]
    out = derived("D-STAT", version, unit, scope, valued, lambda _: mean)
    out["stats"] = stats
    return out


def _raise(reason: NullReason) -> float:
    raise _Null(reason)


# ---------------------------------------------------------------- tokens covered


def tokens_per_proof(
    kind: str, shape: Shape, declared: int | None, proof_id: str
) -> tuple[int, int]:
    """(prompt, output) positions one proof binds (RFC-0004 §Tokens covered, INV-TOK-1).

    `kind` is `system.yaml` `proofs.tokens_covered`; `declared` is the adapter's per-proof
    count from out.json, if it sent one. A count that disagrees with the harness count, or
    that the shape cannot hold, is an `adapter` error at step `prove` (INV-ADAPTER-7).
    """
    if kind == "window":
        counted = (shape.prompt_tokens, 0)
    elif kind == "prompt_plus_output":
        counted = (shape.prompt_tokens, shape.output_tokens)
    elif kind == "declared_per_proof":
        limit = shape.prompt_tokens + shape.output_tokens
        if declared is None or not 1 <= declared <= limit:
            raise IProofsError(
                ErrorKind.ADAPTER,
                f"proof {proof_id}: declared tokens_covered {declared} outside 1..{limit}",
                step="prove",
            )
        prompt = min(declared, shape.prompt_tokens)
        return prompt, declared - prompt
    else:
        raise IProofsError(ErrorKind.CONFIG, f"unknown proofs.tokens_covered {kind!r}")
    if declared is not None and declared != sum(counted):
        raise IProofsError(
            ErrorKind.ADAPTER,
            f"proof {proof_id}: adapter tokens_covered {declared} != harness count {sum(counted)}",
            step="prove",
        )
    return counted


def tokens_metrics(per_proof: Sequence[tuple[int, int]], run_json: str) -> dict[str, QuantityTree]:
    """tokens_covered_total, _prompt, _output and _steady (proofs 2..k), in release order."""
    ref = f"{run_json}#/proofs"
    total = sum(p + o for p, o in per_proof)
    steady = sum(p + o for p, o in per_proof[1:])
    values = {
        "tokens_covered_total": total,
        "tokens_covered_prompt": sum(p for p, _ in per_proof),
        "tokens_covered_output": sum(o for _, o in per_proof),
        "tokens_covered_steady": steady,
    }
    return {name: measured(v, Unit.TOKEN, None, ref, None) for name, v in values.items()}


def honest_verdict_failure(verdicts: Mapping[str, str]) -> IProofsError | None:
    """INV-TOK-2: a repetition with any honest proof not accepted fails at `verify`."""
    bad = {pid: v for pid, v in sorted(verdicts.items()) if v != "accept"}
    if not bad:
        return None
    return IProofsError(
        ErrorKind.ADAPTER, f"INV-TOK-2: honest proofs not accepted: {bad}", step="verify"
    )


# ---------------------------------------------------------------- recompute (gate G4)


class UnknownFormula(Exception):
    """A derived quantity names a formula id that is not in the registry (DER-2)."""


def formula_of(q: Mapping[str, object]) -> tuple[str, str]:
    """(formula id, harness version) from `source.ref` = `derive:<id>@<version>`."""
    source = q["source"]
    assert isinstance(source, Mapping)
    ref = str(source["ref"])
    if not ref.startswith("derive:") or "@" not in ref:
        raise UnknownFormula(ref)
    formula, version = ref.removeprefix("derive:").split("@", 1)
    return formula, version


def recompute(q: Mapping[str, object], inputs: Sequence[Input], gpus: int) -> QuantityTree:
    """Re-evaluate a stored derived quantity from its resolved inputs, in stored order."""
    formula, version = formula_of(q)
    scope = None if q["scope"] is None else Scope(str(q["scope"]))
    if formula == "D-STAT":
        stats = q.get("stats")
        if isinstance(stats, Mapping) and stats["n"] == 0:
            return statistic([], [ref for ref, _ in inputs], version)
        n_failed = int(stats["n_failed"]) if isinstance(stats, Mapping) else 0
        return statistic(inputs, [f"failed:{i}" for i in range(n_failed)], version)
    if formula not in COMPUTE:
        raise UnknownFormula(formula)
    compute = COMPUTE[formula]
    return derived(
        formula, version, Unit(str(q["unit"])), scope, inputs, lambda x: compute(x, gpus)
    )
