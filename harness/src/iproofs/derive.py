"""Derived metrics and statistics from stored raw quantities (RFC-0004).

INV-ARCH-5: every function here is pure: no clock, no file writes, no network.
"""

import statistics
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from iproofs import __version__
from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import Shape
from iproofs.quantity import Grade, NullReason, Scope, SourceKind, Tier, Unit
from iproofs.serialize import load_yaml

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
    "D-SPAB-S": lambda x, gpus: x[0] / nonzero(x[1] * x[2]),
    "D-COMMIT-AMORT-H1": _amortised(1),
    "D-COMMIT-AMORT-H1000": _amortised(1000),
    "D-BPT": _over,
    "D-VSPT": _over,
    "D-VSPT-1T": _over,
    "D-TPP": _ratio,
}


def derive_repetition(  # noqa: PLR0913 (one keyword per formula input outside run.json)
    metrics: Mapping[str, QuantityTree],
    *,
    run_json: str,
    harness_version: str,
    gpus: int,
    price: Input,
    active_parameters: Input,
    weight_bits: Input,
    first_proof_tokens: Input,
    reference: bool = False,
) -> dict[str, QuantityTree]:
    """Every repetition-level formula of RFC-0004 over one repetition's recorded metrics.

    `price`, `active_parameters`, `weight_bits` and `first_proof_tokens` are (pointer,
    quantity) pairs from the reference file, run.json `inputs` (the workload record's
    `model.parameters` and `precision.weight_bits` as copied at run time, RFC-0003 WB-4) and
    run.json `proofs[0]`; a quantity of None is a missing input. Each formula is evaluated
    left to right as written in the RFC table (INV-DERIVE-5). `reference` is true for a
    `kind: reference` system (RFC-0015), whose D-TPP and D-SPAB-S are null (INV-DERIVE-6,
    INV-DERIVE-7).
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
        put(
            f"seconds_per_active_weight_bit_token_{scope}",
            "D-SPAB-S",
            Unit.S_PER_BIT_TOKEN,
            scope,
            [metric(f"seconds_per_token_{scope}"), active_parameters, weight_bits],
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
    put("tokens_covered_per_proof", "D-TPP", Unit.TOKEN, None, [total, metric("proofs_count")])
    if reference:  # INV-DERIVE-6, INV-DERIVE-7: a reference row proves nothing (REF-2)
        for name, q in out.items():
            if formula_of(q)[0] in PROVER_ONLY:
                out[name] = _nulled(q, NullReason.NOT_APPLICABLE)
    return out


# Formulas that describe proving: null with `not_applicable` on a `kind: reference` row.
PROVER_ONLY = frozenset({"D-TPP", "D-SPAB-S"})

# RFC-0004 Q3: formulas a release freeze evaluates for a run stored before they existed.
FREEZE_FORMULAS = frozenset({"D-TPP", "D-SPAB-S"})


def freeze_values(
    metrics: Mapping[str, QuantityTree],
    *,
    run_json: str,
    harness_version: str,
    active_parameters: Input,
    weight_bits: Input,
    reference: bool,
) -> dict[str, QuantityTree]:
    """RFC-0004 Q3: the FREEZE_FORMULAS values a stored run lacks, from its recorded metrics
    (pointers into its unchanged run.json) and the workload record at the release commit. A
    value whose run.json input the run does not hold is null with `missing_input`."""
    out = derive_repetition(
        metrics,
        run_json=run_json,
        harness_version=harness_version,
        gpus=0,
        price=("", None),
        active_parameters=active_parameters,
        weight_bits=weight_bits,
        first_proof_tokens=("", None),
        reference=reference,
    )
    stored = f"{run_json}#/metrics/"
    late = {}
    for name, q in out.items():
        if name in metrics or formula_of(q)[0] not in FREEZE_FORMULAS:
            continue
        source = q["source"]
        assert isinstance(source, Mapping)
        held = [
            ref.removeprefix(stored) in metrics
            for ref in source["inputs"]
            if ref.startswith(stored)
        ]
        late[name] = q if all(held) else _nulled(q, NullReason.MISSING_INPUT)
    return late


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
    "D-SPAB-S": "D-SPT-S / (active_parameters_per_token * weight_bits)",
    "D-BPT": "proof_bytes_total / tokens_covered_total",
    "D-VSPT": "verify_seconds_total / tokens_covered_total",
    "D-VSPT-1T": "first-proof single-thread verify seconds / first-proof tokens",
    "D-TPP": "tokens_covered_total / proofs_count",
    "D-STAT": "over successful repetitions in repetition order: statistics.mean, "
    "statistics.stdev (n - 1, null when n < 2), min, max",
    "D-OVERHEAD-S": "mean(ref-serve rate_<S>) / mean(system rate_<S>)",
    "D-AGREE": "agreement_positions / (agreement_positions + disagreement_positions), "
    "summed over paired ref-recompute runs",
    "D-PROVIDER-SPREAD": "largest provider mean rate_<S> / smallest provider mean rate_<S>",
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
    if not values and present:  # every input is null: derived() returns their null reason
        return derived("D-STAT", version, unit, scope, inputs, lambda _: 0.0)
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


def recompute(
    q: Mapping[str, object], inputs: Sequence[Input], gpus: int, *, reference: bool = False
) -> QuantityTree:
    """Re-evaluate a stored derived quantity from its resolved inputs, in stored order.
    `reference` is true for a run of a `kind: reference` system (INV-DERIVE-6, INV-DERIVE-7)."""
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
    out = derived(formula, version, Unit(str(q["unit"])), scope, inputs, lambda x: compute(x, gpus))
    if reference and formula in PROVER_ONLY:  # INV-DERIVE-6, INV-DERIVE-7
        return _nulled(out, NullReason.NOT_APPLICABLE)
    return out


# ---------------------------------------------------------------- run-campaign budget (spec 08)

CAMPAIGN_REPETITIONS = 3  # the RFC-0004 minimum


def project_campaign(
    release: str, root: Path, repetitions: int = CAMPAIGN_REPETITIONS
) -> dict[str, object]:
    """docs/spec/08 §Run-campaign compute budget, formula P-CAMPAIGN, per configuration:
    repetitions x whole_wall + one perturbed-weights commit (C3) + two prover-side control
    proves (P1, P2) + the reference row's session, all from `external` figures. Grade
    `projected`; a missing input makes it null with `missing_input` and is listed. Setup,
    counted once per image per host, is not in any configuration's figure."""
    figures = _external_figures(root)
    out = []
    for system, workload in sorted({(s, w) for s, w, _ in figures if not s.startswith("ref-")}):
        ref = _reference_for(root, figures, workload)
        wanted = [(system, "whole_wall_seconds"), (system, "commit_seconds"),
                  (system, "prove_session_seconds"), (ref, "prove_session_seconds")]  # fmt: skip
        inputs = [
            figures.get((s_, workload, m), (f"{s_}:{workload}:{m} (missing)", None))
            for s_, m in wanted
        ]
        total = derived("P-CAMPAIGN", __version__, Unit.S, Scope.WHOLE_WALL, inputs,
                        lambda v: repetitions * v[0] + v[1] + 2 * v[2] + v[3])  # fmt: skip
        total["grade"] = str(Grade.PROJECTED)
        verify = figures.get((system, workload, "verify_single_thread_seconds"))
        out.append({
            "system": system,
            "workload": workload,
            "campaign_gpu_seconds": total,
            "missing": [ref.removesuffix(" (missing)") for ref, q in inputs if q is None],
            # verifier-side controls C1 to C8 run on CPU; shown apart, from the verify figure
            "verify_seconds_per_proof_external": verify[1] if verify else None,
        })  # fmt: skip
    return {"release": release, "repetitions": repetitions, "configurations": out}


def _external_figures(root: Path) -> dict[tuple[str, str, str], Input]:
    """(system, workload, metric) -> (pointer, quantity) over systems/*/external.yaml."""
    found: dict[tuple[str, str, str], Input] = {}
    for path in sorted(root.glob("systems/*/external.yaml")):
        doc = load_yaml(path)
        system = str(doc.get("system"))
        figures = doc.get("figures")
        for i, f in enumerate(figures if isinstance(figures, list) else []):
            if isinstance(f, dict) and f.get("workload"):
                rel = path.relative_to(root).as_posix()
                key = (system, str(f["workload"]), str(f["metric"]))
                found.setdefault(key, (f"{rel}#/figures/{i}/quantity", f["quantity"]))
    return found


def _reference_for(root: Path, figures: Mapping[tuple[str, str, str], Input], workload: str) -> str:
    """The workload's plain-serving system (RFC-0015 SRV-7: the one serve-role system its
    `systems` list names) when its workload file names one; otherwise the reference system with
    figures for this workload (ref-serve first), or ref-serve."""
    path = root / "workloads" / f"{workload}.yaml"
    listed = load_yaml(path).get("systems") if path.is_file() else None
    for name in listed if isinstance(listed, list) else []:  # as workloads.serving_system
        system = root / "systems" / str(name) / "system.yaml"
        doc = load_yaml(system) if system.is_file() else {}
        if doc.get("kind") == "reference" and doc.get("reference_role") == "serve":
            return str(name)
    systems = sorted({s for (s, w, _) in figures if w == workload and s.startswith("ref-")})
    return "ref-serve" if "ref-serve" in systems or not systems else systems[0]


# ---------------------------------------------------------------- release rows (RFC-0004, RFC-0015)


def _nulled(out: QuantityTree, reason: NullReason) -> QuantityTree:
    return {**out, "value": None, "null_reason": str(reason)}


def overhead(
    ref: Input, system: Input, scope: Scope, *, joined: bool, measurable: bool, version: str
) -> QuantityTree:
    """D-OVERHEAD-S: mean ref-serve `rate_<S>` over mean system `rate_<S>`. Null with
    `not_measurable_on_profile` when the ref-serve configuration could not run (NM-1), and
    with `not_applicable` when the rows do not join (INV-DERIVE-2)."""
    out = derived("D-OVERHEAD-S", version, Unit.RATIO, scope, [ref, system],
                  lambda x: x[0] / nonzero(x[1]))  # fmt: skip
    if not measurable:
        return _nulled(out, NullReason.NOT_MEASURABLE_ON_PROFILE)
    return out if joined else _nulled(out, NullReason.NOT_APPLICABLE)


def agreement_rate(
    agree: Sequence[Input], disagree: Sequence[Input], *, measurable: bool, version: str
) -> QuantityTree:
    """D-AGREE (RFC-0015 RC-5): agreement positions over compared positions, summed over the
    paired ref-recompute runs; null with `not_measurable_on_profile` under NM-1."""
    n = len(agree)
    out = derived("D-AGREE", version, Unit.RATIO, None, [*agree, *disagree],
                  lambda x: sum(x[:n]) / nonzero(sum(x)))  # fmt: skip
    return out if measurable else _nulled(out, NullReason.NOT_MEASURABLE_ON_PROFILE)


def provider_spread(
    by_provider: Mapping[str, Sequence[Input]], scope: Scope, version: str
) -> QuantityTree:
    """D-PROVIDER-SPREAD (RFC-0006 R4): the largest provider's mean `rate_<S>` over the
    smallest, inputs grouped by provider in name order; `not_applicable` under two providers."""
    names = sorted(by_provider)
    sizes = [len(by_provider[p]) for p in names]

    def spread(x: list[float]) -> float:
        means, start = [], 0
        for size in sizes:
            means.append(statistics.mean(x[start : start + size]))
            start += size
        return max(means) / nonzero(min(means))

    inputs = [i for p in names for i in by_provider[p]]
    out = derived("D-PROVIDER-SPREAD", version, Unit.RATIO, scope, inputs, spread)
    return out if len(names) >= 2 else _nulled(out, NullReason.NOT_APPLICABLE)
