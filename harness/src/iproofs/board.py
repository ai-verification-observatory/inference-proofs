"""The Level 1 board (RFC-0018 §Order, §The board file): `releases/<release>/board.json`.

`build_board` reads stored records only (the release's runs, the rungs' `fidelity.json`, the
baseline runs) and returns a `board/1` tree; it writes nothing and reads no clock, so the same
records give the same bytes. The order rule (OR-1 to OR-6) is a set of pure functions over
`RowSummary` values.
"""

import json
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iproofs import __version__
from iproofs.checks import (
    CHECKS,
    HELD,
    RowSessions,
    Session,
    checks_from,
    fidelity_path,
    field_of,
    int_of,
    level_digest,
    level_id,
    rel,
    release_run_dirs,
    row_sessions,
    started_at,
)
from iproofs.derive import (
    ADAPTER_PHASE_TOLERANCE,
    Input,
    Pooled,
    QuantityTree,
    derived,
    further_reply_gpu_seconds,
    generation_seconds,
    nonzero,
    one_time_gpu_seconds,
    one_time_mark,
    phases_within,
    pooled_per_reply,
    release_groups,
    reply_tokens_per_gpu_second,
    served_reply_tokens_per_gpu_second,
    session_per_reply,
    statistic,
    steady_per_reply,
)
from iproofs.errors import ErrorKind, IProofsError
from iproofs.fidelity import run_slots as fidelity_run_slots
from iproofs.fidelity import with_steps as fidelity_with_steps
from iproofs.glyph import (
    Coverage,
    Petal,
    faithful_model,
    glyph,
    load_proof_build,
    load_properties,
    statement_petals,
)
from iproofs.model import card_path
from iproofs.proof_build import record_path
from iproofs.provenance import file_digest
from iproofs.quantity import Grade, NullReason, Scope, SourceKind, Tier, Unit
from iproofs.release import RunView
from iproofs.serialize import load_yaml
from iproofs.setups import SETUP_RECORD, SETUPS, record_problems

NO_SECURITY_LEVEL = "publisher states no security level"  # OR-2
NO_LEVEL_STATEMENT = "publisher states no Level 1 statement"  # SI-4a

# ---------------------------------------------------------------- the cost rule (CO-5, CO-9)

# RFC-0018 Q55 (2026-11-26): which cost a release prints. `whole-session` is CO-5 as Q29
# amended it, the rule v1.0 was published under; `further-reply` is CO-9, the cost of a further
# reply with the one-time work apart, for every later release. A board built by CO-9 records it
# in `cost_rule`; a board without the field was built by the whole-session rule.
WHOLE_SESSION = "whole-session"
FURTHER_REPLY = "further-reply"
COST_RULES = (WHOLE_SESSION, FURTHER_REPLY)
WHOLE_SESSION_RELEASES = frozenset({"v1.0"})

# CO-9: the prove phase an adapter reports as the generation of a reply's tokens, for a system
# with no generation phase of its own (AD-4). SASH: `ids`, the greedy continuation its integer
# model decodes before the witness (systems/sash/README.md, `prove`; entrypoint, `ids`)
GENERATION_PHASES = {"sash": "ids"}
GENERATION_MARKS = "generation_marks"
ADAPTER_PHASES = "adapter_phases"


def cost_rule(release: str, override: str | None = None) -> str:
    """Q55: the cost rule a release's board is built by: `override` when given (a preview),
    else whole-session for the releases published under it, else further-reply."""
    if override is not None:
        if override not in COST_RULES:
            raise IProofsError(ErrorKind.CONFIG, f"unknown cost rule {override!r}; "
                               f"one of {', '.join(COST_RULES)}")  # fmt: skip
        return override
    return WHOLE_SESSION if release in WHOLE_SESSION_RELEASES else FURTHER_REPLY


# ---------------------------------------------------------------- order rule (OR-1 to OR-6)


@dataclass(frozen=True, slots=True)
class RowSummary:
    """What the order rule reads of one row. `multiple` is the row's mean multiple (None
    without one); `m` its sessions' steady values; `session` its sessions' cost per reply and
    `session_mean` their mean."""

    system: str
    passed: bool
    stated: bool
    multiple: float | None = None
    m: tuple[float, ...] = ()
    session_mean: float | None = None
    session: tuple[float, ...] = ()
    relation: bool = True  # SI-4a: the publisher states Level 1's statement at the pin

    @property
    def ranked(self) -> bool:
        """OR-1, OR-2, SI-4a: a passed row whose publisher states a security level and states
        that an accept is the committed model's own greedy reply to the prompt."""
        return self.passed and self.stated and self.relation


def placed_above(a: RowSummary, b: RowSummary, margin: float) -> bool:
    """OR-3: A above B when both have a multiple, A's mean multiple is at most (1 - margin)
    times B's and A's highest m is below B's lowest; a row with a multiple is above one
    without; two rows without a multiple compare the same way on session cost per reply."""
    if a.multiple is not None and b.multiple is not None:
        return _clear(a.multiple, a.m, b.multiple, b.m, margin)
    if a.multiple is not None:
        return True
    if b.multiple is not None:
        return False
    if a.session_mean is None or b.session_mean is None:
        return False
    return _clear(a.session_mean, a.session, b.session_mean, b.session, margin)


def _clear(
    mean_a: float,
    values_a: Sequence[float],
    mean_b: float,
    values_b: Sequence[float],
    margin: float,
) -> bool:
    if not values_a or not values_b:
        return False
    return mean_a <= (1 - margin) * mean_b and max(values_a) < min(values_b)


def positions(rows: Sequence[RowSummary], margin: float) -> dict[str, int]:
    """OR-4: each ranked row's position, 1 plus the number of ranked rows placed above it."""
    ranked = [r for r in rows if r.ranked]
    return {
        r.system: 1 + sum(placed_above(o, r, margin) for o in ranked if o is not r) for r in ranked
    }


def order(rows: Sequence[RowSummary], margin: float) -> list[tuple[RowSummary, int | None]]:
    """OR-5: ranked rows by position (equal positions alphabetical), then passed unranked rows,
    then rows that have not passed, each group alphabetical. Pairs (row, position or None)."""
    at = positions(rows, margin)
    ranked = sorted((r for r in rows if r.ranked), key=lambda r: (at[r.system], r.system))
    unranked = sorted((r for r in rows if r.passed and not r.ranked), key=lambda r: r.system)
    rest = sorted((r for r in rows if not r.passed), key=lambda r: r.system)
    return [(r, at.get(r.system)) for r in (*ranked, *unranked, *rest)]


@dataclass(frozen=True, slots=True)
class RungSummary:
    id: str
    parameters_total: int
    rows: tuple[tuple[RowSummary, int | None], ...]  # in `order` order


def frontier(rungs: Sequence[RungSummary]) -> dict[str, object] | None:
    """OR-6: the largest rung by total parameters with a passed row whose publisher states Level
    1's statement (SI-4a); the rows at position 1 there, or every such row when none is ranked;
    and the count of systems run on it."""
    for rung in sorted(rungs, key=lambda r: -r.parameters_total):
        passed = [(r, p) for r, p in rung.rows if r.passed and r.relation]
        if not passed:
            continue
        first = [r.system for r, p in passed if p == 1]
        return {
            "rung": rung.id,
            "rows": first or [r.system for r, _ in passed],
            "systems_run": len(rung.rows),
        }
    return None


# ---------------------------------------------------------------- quantities


def _quantity(
    value: float | None,
    unit: Unit,
    scope: Scope | None,
    formula: str,
    inputs: Sequence[str],
    reason: NullReason | None = None,
    note: str | None = None,
) -> QuantityTree:
    """A derived quantity computed here from record fields that are not quantities (release
    times, events), with its inputs as pointers."""
    out: QuantityTree = {
        "value": value,
        "unit": str(unit),
        "scope": None if scope is None else str(scope),
        "grade": str(Grade.DERIVED),
        "tier": str(Tier.REPORTED),
        "source": {
            "kind": str(SourceKind.DERIVATION),
            "ref": f"derive:{formula}@{__version__}",
            "inputs": list(inputs) or ["(no input)"],
        },
        "null_reason": None if value is not None else str(reason or NullReason.MISSING_INPUT),
    }
    if note:
        out["note"] = note[:500]
    return out


def _stat(
    values: Sequence[float | None],
    unit: Unit,
    scope: Scope | None,
    formula: str,
    inputs: Sequence[str],
    reason: NullReason,
    note: str | None = None,
) -> QuantityTree:
    """The mean over counted sessions with its range (a `statistic`), or null with `reason`
    when a session has no value or there is no session."""
    if not values or any(v is None for v in values):
        return _quantity(None, unit, scope, formula, inputs, reason, note)
    xs = [float(v) for v in values if v is not None]
    mean = statistics.mean(xs)
    out = _quantity(mean, unit, scope, formula, inputs)
    out["stats"] = {
        "n": len(xs),
        "n_failed": 0,
        "mean": mean,
        "stdev": statistics.stdev(xs) if len(xs) >= 2 else None,
        "min": min(xs),
        "max": max(xs),
        "median": statistics.median(xs),
    }
    return out


def _ratio(formula: str, unit: Unit, scope: Scope | None, a: Input, b: Input) -> QuantityTree:
    return derived(formula, __version__, unit, scope, [a, b], lambda x: x[0] / nonzero(x[1]))


def _usd(scope: Scope | None, gpu_seconds: Input, price: Input) -> QuantityTree:
    return derived("D-L1-USD", __version__, Unit.USD_PER_REQUEST, scope, [gpu_seconds, price],
                   lambda x: x[0] * x[1] / 3600)  # fmt: skip


def _reply_tokens(figures: Sequence["SessionFigures"], tokens: int,
                  inputs: Sequence[str]) -> QuantityTree:  # fmt: skip
    """CO-8 (adopted 2026-11-16): reply tokens per GPU-second over whole sessions, the request's
    reply tokens over the sessions' mean GPU-seconds per reply (CO-1), with its range (the tokens
    over the largest and the smallest session) and n; null where a session has no value."""
    per_reply = [f.per_reply for f in figures]
    if not per_reply or not tokens or any(v is None or v <= 0 for v in per_reply):
        return _quantity(None, Unit.TOKEN_PER_GPU_S, Scope.WHOLE_WALL, "D-L1-REPLY-TOKENS",
                         inputs, NullReason.MISSING_INPUT)  # fmt: skip
    r = reply_tokens_per_gpu_second([float(v) for v in per_reply if v is not None], tokens)
    out = _quantity(r.value, Unit.TOKEN_PER_GPU_S, Scope.WHOLE_WALL, "D-L1-REPLY-TOKENS", inputs)
    out["stats"] = {"n": r.n, "n_failed": 0, "mean": r.value, "stdev": None, "min": r.low,
                    "max": r.high}  # fmt: skip
    return out


def _served_tokens(per_reply: QuantityTree, tokens: int, inputs: Sequence[str],
                   note: str | None) -> QuantityTree:  # fmt: skip
    """CO-8 (amended 2026-11-16): the serving baseline's reply tokens per GPU-second, the
    request's reply tokens over its GPU-seconds per reply at full load, at the baseline's scope.
    One rate over the timed batches of one run: it has no range; `note` says what it counts."""
    v = per_reply.get("value")
    if not isinstance(v, int | float) or v <= 0 or not tokens:
        return _quantity(None, Unit.TOKEN_PER_GPU_S, Scope.PROVE_STEADY, "D-L1-SERVED-TOKENS",
                         inputs, NullReason.MISSING_INPUT)  # fmt: skip
    rate = served_reply_tokens_per_gpu_second(tokens, float(v))
    return _quantity(rate, Unit.TOKEN_PER_GPU_S, Scope.PROVE_STEADY, "D-L1-SERVED-TOKENS",
                     inputs, note=note)  # fmt: skip


def _null(
    unit: Unit, scope: Scope | None, formula: str, ref: str, reason: NullReason
) -> QuantityTree:
    return _quantity(None, unit, scope, formula, [ref], reason)


# ---------------------------------------------------------------- sessions' figures (CO-1 to CO-3)


def bound_gpus(run: RunView) -> int | None:
    """SE-2: the GPUs the session bound: `machine.gpu.bound_indices`, a single `bound_index`,
    else run.json `inputs.gpu_count`."""
    gpu = run.get("manifest", "machine", "gpu")
    if isinstance(gpu, dict):
        indices = gpu.get("bound_indices")
        if isinstance(indices, list) and indices:
            return len(indices)
        if isinstance(gpu.get("bound_index"), int):
            return 1
    count = run.get("run", "inputs", "gpu_count", "value")
    return count if isinstance(count, int) and count > 0 else None


def reply_times(run: RunView) -> list[int]:
    """Each request's reply release: the last release among its proofs (a joined set of proofs,
    RFC-0017 INV-REQ-2, releases its reply with its last proof)."""
    by_request: dict[object, int] = {}
    proofs = run.run.get("proofs")
    for i, p in enumerate(proofs if isinstance(proofs, list) else []):
        t = p.get("release_mono_ns") if isinstance(p, dict) else None
        if isinstance(t, int):
            key = p.get("request_index", f"proof-{i}")
            by_request[key] = max(t, by_request.get(key, t))
    return sorted(by_request.values())


def _event(run: RunView, name: str) -> int | None:
    events = run.run.get("events")
    for e in events if isinstance(events, list) else []:
        if isinstance(e, dict) and e.get("event") == name and isinstance(e.get("mono_ns"), int):
            return int(e["mono_ns"])
    return None


@dataclass(frozen=True, slots=True)
class SessionFigures:
    session: Session
    gpus: int | None
    groups: tuple[int, ...]
    m: float | None
    cause: str | None
    per_reply: float | None  # CO-1
    generation: float | None = None  # CO-3: the generation phase's GPU-seconds over N
    commit: float | None = None  # CO-7: the `commit` call's GPU-seconds over N
    further: "Further | None" = None  # CO-9

    def tree(self, rule: str = WHOLE_SESSION) -> dict[str, object]:
        out: dict[str, object] = {
            "slot": self.session.slot,
            "run_id": self.session.run_id,
            "gpus": self.gpus,
            "groups": list(self.groups),
            "m": self.m,
            "session": self.per_reply,
            "generation_gpu_seconds_per_reply": self.generation,
            "steady": self.m is not None,
            "cause": self.cause,
        }
        if rule == FURTHER_REPLY:  # CO-9: each session's own figures, per reply and once
            f = self.further
            out["further_reply"] = f.per_reply if f else None
            out["further_reply_generation"] = f.generation_per_reply if f else None
            out["one_time"] = f.one_time if f else None
        return out


@dataclass(frozen=True, slots=True)
class Further:
    """CO-9 for one session: the GPU-seconds from the start of `prove` to its last reply
    (`gpu_seconds`, over `replies`), the generation inside them and where that figure comes from
    (`split`: the AD-4 marks, or the adapter's reported phases once they sum to the prove call),
    and the one-time work before `prove`. A None says the record cannot give the figure; `cause`
    says why for the split, `one_time_cause` for the one-time work."""

    gpu_seconds: float | None
    replies: int
    generation: float | None
    split: str | None
    cause: str | None
    check: dict[str, object] | None  # the adapter phases' sum against the prove call
    one_time: float | None
    one_time_cause: str | None
    setup: dict[str, object] | None  # the setup a session reused: its record and GPU-seconds

    @property
    def per_reply(self) -> float | None:
        if self.gpu_seconds is None or self.replies < 1:
            return None
        return self.gpu_seconds / self.replies

    @property
    def generation_per_reply(self) -> float | None:
        if self.generation is None or self.replies < 1:
            return None
        return self.generation / self.replies


def _setup_of(run: RunView, root: Path | None) -> tuple[dict[str, object] | None, str | None]:
    """CO-9: the setup a session reused (run.json `setup`), its record read from
    `<results>/<release>/<system>/_setups/<setup id>/setup.json` beside the session and checked
    against the digest the session recorded; (block, None), or (None, why) when the record is
    not stored. A record whose digest is not the one the session names stops the board."""
    ref = run.run.get("setup")
    if not isinstance(ref, dict):
        return None, None
    path = run.path.parent / SETUPS / str(ref.get("setup_id")) / SETUP_RECORD
    if not path.is_file():
        return None, f"the setup record {ref.get('setup_id')} is not stored"
    got = file_digest(path)
    if got != ref.get("record_digest"):
        raise IProofsError(ErrorKind.INTEGRITY, f"{path}: digest {got}; the session "
                           f"{run.run_id} names {ref.get('record_digest')}")  # fmt: skip
    doc = json.loads(path.read_text())
    problems = record_problems(doc)
    if problems:
        raise IProofsError(ErrorKind.INTEGRITY, f"{path}: {problems[0]}")
    spent = (doc.get("gpu_seconds") or {}).get("value")
    if not isinstance(spent, int | float):
        return None, f"the setup record {ref.get('setup_id')} holds no GPU-seconds"
    restore = (ref.get("restore_seconds") or {}).get("value")
    where = rel(root, path) if root is not None else path.as_posix()
    return {"setup_id": str(ref.get("setup_id")), "record": where,
            "gpu_seconds": float(spent),
            "restore_seconds": float(restore) if isinstance(restore, int | float) else None,
            }, None  # fmt: skip


def _adapter_split(run: RunView, phase: str) -> tuple[float | None, str | None,
                                                      dict[str, object] | None]:  # fmt: skip
    """CO-9: the seconds the adapter reports for its generation phase `phase` of `prove`, once
    the prove phases it reports sum to the harness-timed prove call within the tolerance:
    (seconds, None, check); else (None, why, check or None)."""
    found = run.get("run", "adapter_phases", "prove")
    phases = {str(k): float(v["value"]) for k, v in found.items()
              if isinstance(v, dict) and isinstance(v.get("value"), int | float)} \
        if isinstance(found, dict) else {}  # fmt: skip
    if phase not in phases:
        return None, f"the adapter reports no {phase} phase of prove", None
    call = run.get("run", "metrics", "prove_call_seconds", "value")
    if not isinstance(call, int | float):
        return None, "no harness-timed prove call", None
    within = phases_within(phases, float(call))
    check: dict[str, object] = {"run_id": run.run_id, "phases_seconds": sum(phases.values()),
                                "prove_call_seconds": float(call), "within": within}  # fmt: skip
    if not within:
        return None, (f"the adapter's prove phases sum to {sum(phases.values()):.1f} s, the "
                      f"prove call took {float(call):.1f} s"), check  # fmt: skip
    return phases[phase], None, check


def further_figures(s: Session, n: int, gpus: int | None, times: Sequence[int],
                    phase_seconds: float | None, root: Path | None = None,
                    mark_cause: str | None = None) -> Further:  # fmt: skip
    """CO-9 for one session of a row of the rung's N = `n` replies released at `times`, on
    `gpus` bound GPUs, whose AD-4 generation phase lasted `phase_seconds` (None without one)."""
    prove = _event(s.run, "prove.start")
    commit = _event(s.run, "commit.start")
    spent = None if gpus is None or prove is None or not times \
        else further_reply_gpu_seconds(prove, times, gpus)  # fmt: skip
    generation: float | None = None
    split: str | None = None
    cause: str | None = None
    check: dict[str, object] | None = None
    phase = GENERATION_PHASES.get(str(s.run.run.get("system")))
    if gpus is None:
        cause = "no bound GPU recorded"
    elif mark_cause is not None:
        cause = mark_cause
    elif phase_seconds is not None:
        generation, split = phase_seconds * gpus, GENERATION_MARKS
    elif phase is not None:
        seconds, cause, check = _adapter_split(s.run, phase)
        if seconds is not None:
            generation, split = seconds * gpus, ADAPTER_PHASES
    else:
        cause = "no generation phase of its own and no generation phase its adapter reports"
    setup, setup_cause = _setup_of(s.run, root)
    reused = s.run.run.get("setup") is not None
    one_time: float | None = None
    one_cause: str | None = None
    if gpus is None or prove is None or commit is None:
        one_cause = "no commit or prove start recorded"
    elif reused and setup is None:
        one_cause = setup_cause
    else:
        made = setup.get("gpu_seconds") if setup else None
        restore = setup.get("restore_seconds") if setup else None
        one_time = one_time_gpu_seconds(
            commit, prove, gpus,
            float(made) if isinstance(made, int | float) else None,
            float(restore) if isinstance(restore, int | float) else None,
        )  # fmt: skip
    return Further(spent, n, generation, split, cause, check, one_time, one_cause, setup)


def session_figures(s: Session, n: int, level: object, root: Path | None = None) -> SessionFigures:
    times = reply_times(s.run)
    gpus = bound_gpus(s.run)
    gap = field_of(field_of(level, "steady"), "group_gap_s")
    groups = release_groups(times, float(gap) if isinstance(gap, int | float) else 1.0)
    phase, missing = generation_seconds(s.run.run.get("marks"))
    if gpus is None:
        m, cause = None, None
    elif missing is not None:
        m, cause = None, missing
    else:
        m, cause = steady_per_reply(groups, gpus, level, phase)
    # a session that reused a setup (run.json `setup`) timed only a check of the setup's state
    # from its commit start; CO-1 counts the session from the start of commit, so no figure
    commit = None if s.run.run.get("setup") is not None else _event(s.run, "commit.start")
    per_reply = (
        None if gpus is None or commit is None or not times
        else session_per_reply(commit, times, n, gpus)
    )  # fmt: skip
    replies = sum(g.size for g in groups)
    generation = None if phase is None or gpus is None or not replies else phase * gpus / replies
    end = _event(s.run, "commit.end")
    spent = (None if gpus is None or commit is None or end is None or end < commit or n <= 0
             else (end - commit) / 1e9 * gpus / n)  # fmt: skip
    further = further_figures(s, n, gpus, times, phase, root, missing)
    return SessionFigures(s, gpus, tuple(g.size for g in groups), m, cause, per_reply, generation,
                          spent, further)  # fmt: skip


# ---------------------------------------------------------------- level inputs


def _load_level(root: Path, level: object) -> object:
    if not isinstance(level, str):
        return level
    from iproofs.level import load_level  # noqa: PLC0415

    return load_level(root, level)


def price_of(root: Path, level: object) -> tuple[dict[str, object], Input]:
    """The board's price block and the price as a formula input: `levels/<id>.yaml` `price`
    names a reference file and a key of its `costs` (RFC-0006 C7)."""
    price = field_of(level, "price")
    reference = str(field_of(price, "reference") or "")
    cost = str(field_of(price, "cost") or "")
    ref = f"{reference}#/costs/{cost}/price_per_gpu_hour_usd"
    path = root / reference
    basis = load_yaml(path).get("costs") if reference and path.is_file() else None
    entry = basis.get(cost) if isinstance(basis, dict) else None
    q = entry.get("price_per_gpu_hour_usd") if isinstance(entry, dict) else None
    if not isinstance(q, dict):
        q = {"value": None, "unit": str(Unit.USD_PER_GPU_HOUR), "scope": None,
             "grade": str(Grade.ASSERTED), "tier": str(Tier.REPORTED),
             "source": {"kind": str(SourceKind.REFERENCE_FILE), "ref": ref},
             "null_reason": str(NullReason.MISSING_INPUT)}  # fmt: skip
    date = entry.get("date") if isinstance(entry, dict) else None
    block: dict[str, object] = {"basis": cost, "reference": reference, "usd_per_gpu_hour": q,
                                "date": None if date is None else str(date)}  # fmt: skip
    return block, (ref, q)


# ---------------------------------------------------------------- baseline (CO-4)


def _baseline(
    root: Path, runs: Sequence[RunView], level: object, rung: object, digest: str, index: str,
    price: Input, tokens: int = 0,
) -> tuple[dict[str, object], Input, list[RunView]]:  # fmt: skip
    """The rung's baseline block, its GPU-seconds per reply as a formula input, and the runs
    read. The first run by start time of the rung's serving record under this level that has a
    full load is used. The block holds the GPU model the run's manifest records and the reply
    tokens per GPU-second it serves (CO-8, amended 2026-11-16)."""
    tokens_in = [f"{index}/baseline/gpu_seconds_per_reply",
                 f"levels/{level_id(level)}.yaml#/request/output_tokens"]  # fmt: skip
    serving = str(field_of(rung, "serving"))
    mine = [r for r in runs
            if r.get("manifest", "serving_model", "id") == serving
            and r.get("manifest", "level", "digest") == digest]  # fmt: skip
    mine.sort(key=lambda r: (started_at(r), r.run_id))
    ref = f"{index}/baseline/gpu_seconds_per_reply"
    cause = "no baseline run stored"
    try:
        from iproofs.baseline import full_load  # noqa: PLC0415
    except ImportError:
        full_load = None  # type: ignore[assignment]
        cause = "no baseline module"
    found = None
    for r in mine if full_load is not None else []:
        result = full_load(r.path, level)  # type: ignore[arg-type]
        if isinstance(result, str):
            cause = result
            continue
        found = (r, result)
        break
    if found is None:
        q = _null(Unit.GPU_S_PER_REQUEST, Scope.PROVE_STEADY, "D-L1-BASELINE",
                  f"levels/{level_id(level)}.yaml#/rungs", NullReason.MISSING_INPUT)  # fmt: skip
        missing: dict[str, object] = {
            "serving": serving, "run_id": None, "gpus": None, "concurrency": None,
            "gpu_seconds_per_reply": q, "usd_per_reply": _usd(Scope.PROVE_STEADY, (ref, q), price),
            "ladder": [], "cause": cause, "gpu_model": None,
            "reply_tokens_per_gpu_second": _served_tokens(q, tokens, tokens_in, None),
        }  # fmt: skip
        return missing, (ref, q), mine
    run, load = found
    q = dict(load.gpu_seconds_per_reply)
    model = run.get("manifest", "machine", "gpu", "model")
    model = str(model) if isinstance(model, str) and model else None
    timed = int_of(field_of(level, "baseline"), "timed_batches", 0)
    # what the served rate counts, from the records: the timed replies at full load, one run
    note = (f"one serving run at full load: {timed:,} timed batches of {load.concurrency:,} "
            f"replies ({timed * load.concurrency:,} replies) on {load.gpus:,} x "
            f"{model or 'GPU model not recorded'}; one rate over the batches' span, no range"
            if timed else None)  # fmt: skip
    block: dict[str, object] = {
        "serving": serving,
        "run_id": run.run_id,
        "gpus": load.gpus,
        "concurrency": load.concurrency,
        "gpu_seconds_per_reply": q,
        "usd_per_reply": _usd(Scope.PROVE_STEADY, (ref, q), price),
        "ladder": [
            {"concurrency": c, "replies_per_gpu_second": dict(rate)} for c, rate in load.ladder
        ],
        "cause": None,
        "gpu_model": model,
        "reply_tokens_per_gpu_second": _served_tokens(q, tokens, tokens_in, note),
    }
    return block, (ref, q), mine


# ---------------------------------------------------------------- fidelity


def _fidelity(
    root: Path, release: str, rung: str
) -> tuple[dict[str, object], dict[str, object] | None]:
    """The rung's fidelity block and its `fidelity.json` (FI-5, FI-6), None when not stored."""
    path = fidelity_path(root, release, rung)
    if not path.is_file():
        none: dict[str, object] = {"path": None, "bar": None, "controls": [],
                                    "cause": "no fidelity.json stored"}  # fmt: skip
        return none, None
    doc = json.loads(path.read_text())
    controls = [{"id": str(c.get("id")), "kind": str(c.get("kind")),
                 "status": "ok" if c.get("status") == "ok" else "failed",
                 "mean_prefix": c.get("mean_prefix"), "kl": c.get("kl")}
                for c in doc.get("controls") or [] if isinstance(c, dict)]  # fmt: skip
    bar = doc.get("bar")
    records = _run_records(path.parent)
    slots, slots_cause = fidelity_run_slots(records)
    block: dict[str, object] = {
        "path": rel(root, path),
        "bar": {"control": str(bar["control"]), "mean_prefix": bar["mean_prefix"]}
        if isinstance(bar, dict) else None,
        "controls": controls,
        "cause": None if isinstance(bar, dict) else "no damaged control that every honest "
        "control scores above (FI-5)",
        # FI-8, FI-9, FM-5: each part of the fidelity run, its engine and the slot count it
        # stores, and the count FM-5 reads (none for a vLLM part, with why)
        "runs": [{"part": r.get("part"), "engine": (r.get("engine") or {}).get("tool"),
                  "slots": r.get("slots")} for r in records],
        "slots": slots,
        "slots_cause": slots_cause,
    }  # fmt: skip
    return block, doc if isinstance(doc, dict) else None


def _run_records(folder: Path) -> list[dict[str, Any]]:
    """The rung's fidelity run records: `fidelity-run.json`, then each part's."""
    paths = [folder / "fidelity-run.json", *sorted(folder.glob("fidelity-run-*.json"))]
    return [json.loads(p.read_text()) for p in paths if p.is_file()]


def _proved_replies(sessions: RowSessions, level: object, n: int) -> list[list[int]] | None:
    """FI-16: a row's proved replies in prompt order, from its counted sessions (FI-6's
    reading); None unless each of the level's slots has a session of n accepted replies."""
    from iproofs.fidelity import row_replies, session_replies  # noqa: PLC0415

    by_slot = {}
    for slot, session in sessions.counted.items():
        found = session_replies(session.run.run)
        if found is not None:
            by_slot[slot] = found
    return row_replies(by_slot, int_of(field_of(level, "sessions"), "slots", 0), n)


def _teacher_forced(
    root: Path, release: str, rung: str, proved: Mapping[str, list[list[int]] | None]
) -> dict[str, object] | None:
    """SI-9: the rung's teacher-forced block from `teacher-forced.json` (FI-10 to FI-15), its
    scores recomputed from the stored top tokens, and each row's count of proved tokens
    (FI-16) from `proved`, its proved replies; None when not stored. It gates nothing and no
    check, petal or position reads it."""
    from iproofs.teacher_forced import board_block, scoring_file  # noqa: PLC0415

    base = fidelity_path(root, release, rung).parent
    folder = root / "results" / release / "teacher-forced" / rung
    path = scoring_file(folder, "teacher-forced")  # the scoring in force (APP-1)
    if not path.is_file():
        return None
    doc = json.loads(path.read_text())
    reference = [json.loads(x) for x in (base / "reference.jsonl").read_text().splitlines() if x]
    tops = {p.stem: p for p in (folder / "top").glob("*.jsonl")}
    named = (doc.get("kl") or {}).get("values")  # the values this scoring was computed from
    values = root / str(named) if named else folder / "kl.json"
    kl = json.loads(values.read_text()) if values.is_file() else None
    try:
        return board_block(doc, rel(root, path), tops, reference, kl, proved)
    except (ValueError, KeyError) as e:
        raise IProofsError(ErrorKind.INTEGRITY, str(e)) from e


def _row_fidelity(row: object) -> dict[str, object] | None:
    if not isinstance(row, dict):
        return None
    scores = row.get("scores")
    return {
        "n": len(scores) if isinstance(scores, list) else 0,
        "mean_prefix": row.get("mean_prefix"),
        "p_above_bar": row.get("p_above_bar"),
        "p_below_bar": row.get("p_below_bar"),
        "kl": row.get("kl"),
        "kl_note": row.get("kl_note"),
    }


# ---------------------------------------------------------------- one row


@dataclass
class _Row:
    system: str
    workload: str
    sessions: RowSessions
    figures: list[SessionFigures]
    checks: dict[str, dict[str, object]]
    passed: bool
    security: dict[str, object] | None
    stated: bool
    petals: dict[str, Petal]
    relation: dict[str, object]  # SI-4a, `level_statement`

    def summary(self, has_baseline: bool, rule: str = WHOLE_SESSION) -> RowSummary:
        """What OR-3 reads. Without a steady state it compares the session cost per reply
        (CO-1); under CO-9 (Q55) the cost of a further reply, pooled, in its place."""
        ms = [f.m for f in self.figures]
        steady = bool(ms) and all(m is not None for m in ms)
        cost = [f.per_reply for f in self.figures]
        full = bool(cost) and all(c is not None for c in cost)
        mean = statistics.mean(c for c in cost if c is not None) if full else None
        if rule == FURTHER_REPLY:
            pooled = _pooled_of([f.further for f in self.figures])
            cost = [f.further.per_reply if f.further else None for f in self.figures]
            full = pooled is not None and all(c is not None for c in cost)
            mean = pooled.value if pooled is not None and full else None
        return RowSummary(
            self.system, self.passed, self.stated,
            multiple=statistics.mean(m for m in ms if m is not None)
            if steady and has_baseline else None,
            m=tuple(m for m in ms if m is not None) if steady else (),
            session_mean=mean,
            session=tuple(c for c in cost if c is not None) if full else (),
            relation=self.relation["stated"] is True,
        )  # fmt: skip


def level_statement(props: Mapping[str, object] | None, commit: object) -> dict[str, object]:
    """SI-4a: whether the properties file, read at the row's commit, records the publisher's
    statement that an accept means the reply is the committed model's own computation, decoded
    greedily, on the prompt (`level_statement.accept_is_model_reply`, true with quotes). `read`
    is false for a file missing, without the fact, or read at another commit; `reading` is true
    when the fact carries a note (the reader's reading, not one sentence that says it)."""
    upstream = props.get("upstream") if props else None
    at_pin = isinstance(upstream, Mapping) and upstream.get("commit") == commit
    block = props.get("level_statement") if props and at_pin else None
    block = block if isinstance(block, Mapping) else {}
    fact = block.get("accept_is_model_reply")
    fact = fact if isinstance(fact, Mapping) else {}
    found = fact.get("quotes")
    quotes = [{"text": str(q["text"]), "url": str(q["url"])}
              for q in (found if isinstance(found, list) else [])
              if isinstance(q, Mapping) and q.get("text") and q.get("url")]  # fmt: skip
    stated = fact.get("value") is True and bool(quotes)
    read = block.get("sources_read")
    return {"read": bool(fact), "stated": stated, "reading": stated and bool(fact.get("note")),
            "quotes": quotes,
            "sources_read": [str(x) for x in read] if isinstance(read, list) else []}  # fmt: skip


def _unranked(row: _Row) -> str | None:
    """Why a passed row has no position: SI-4a first (no Level 1 statement), then OR-2."""
    if not row.passed:
        return None
    if row.relation["stated"] is not True:
        return NO_LEVEL_STATEMENT
    return None if row.stated else NO_SECURITY_LEVEL


def _security(level: object, system: str) -> tuple[dict[str, object] | None, bool]:
    found = field_of(field_of(field_of(level, "systems") or {}, system), "security")
    if found is None:
        return None, False
    stated = field_of(found, "stated") is True
    return {"stated": stated, "words": str(field_of(found, "words")),
            "source": str(field_of(found, "source"))}, stated  # fmt: skip


def _metric_stat(figures: Sequence[SessionFigures], metric: str, unit: Unit,
                 scope: Scope | None) -> QuantityTree:  # fmt: skip
    """The mean of a recorded per-request metric over the counted sessions (D-VSPR, D-BPR)."""
    found = []
    refs = []
    for f in figures:
        q = (f.session.run.run.get("metrics") or {}).get(metric)  # type: ignore[attr-defined]
        refs.append(f"{f.session.path}/run.json#/metrics/{metric}")
        found.append(q.get("value") if isinstance(q, dict) else None)
    formula = "D-VSPR" if metric.startswith("verify") else "D-BPR"
    if not found or any(not isinstance(v, int | float) for v in found):
        return _quantity(None, unit, scope, formula, refs, NullReason.MISSING_INPUT)
    return _stat([float(v) for v in found if isinstance(v, int | float)], unit, scope, formula,
                 refs, NullReason.MISSING_INPUT)  # fmt: skip


# ---------------------------------------------------------------- CO-9 on a row


def _pooled_of(further: Sequence["Further | None"], part: str = "all") -> Pooled | None:
    """CO-9: the pooled cost of the sessions' `part` (all of a further reply, its generation,
    or the proving: all less generation), None when a session lacks it."""
    pairs: list[tuple[float, int]] = []
    for f in further:
        if f is None:
            return None
        value = {"all": f.gpu_seconds, "generation": f.generation,
                 "proving": None if f.gpu_seconds is None or f.generation is None
                 else f.gpu_seconds - f.generation}[part]  # fmt: skip
        if value is None or f.replies < 1:
            return None
        pairs.append((value, f.replies))
    return pooled_per_reply(pairs) if pairs else None


def _pooled_quantity(further: Sequence["Further | None"], part: str, unit: Unit, formula: str,
                     inputs: Sequence[str], reason: NullReason,
                     note: str | None) -> QuantityTree:  # fmt: skip
    """CO-9: a pooled cost as a labelled quantity: the value is the sessions' summed GPU-seconds
    over their summed replies, its range and median each session's own, n the sessions."""
    found = _pooled_of(further, part)
    if found is None:
        return _quantity(None, unit, Scope.PROVE_SESSION, formula, inputs, reason, note)
    out = _quantity(found.value, unit, Scope.PROVE_SESSION, formula, inputs, note=note)
    out["stats"] = {"n": found.n, "n_failed": 0, "mean": found.value, "stdev": None,
                    "min": found.low, "max": found.high, "median": found.median}  # fmt: skip
    return out


def _over_baseline(name: str, q: QuantityTree, baseline: Input) -> QuantityTree:
    """CO-9: a pooled cost over the baseline's GPU-seconds per reply (D-L1-MULTIPLE), with the
    cost's own range and n over the same baseline (the baseline is one run: no range)."""
    out = _ratio("D-L1-MULTIPLE", Unit.RATIO, Scope.PROVE_SESSION, (name, q), baseline)
    stats, base = q.get("stats"), (baseline[1] or {}).get("value")
    if out["value"] is not None and isinstance(stats, dict) and isinstance(base, int | float):
        out["stats"] = {"n": stats["n"], "n_failed": 0, "mean": out["value"], "stdev": None,
                        "min": stats["min"] / base, "max": stats["max"] / base,
                        "median": stats["median"] / base}  # fmt: skip
    if q.get("note"):
        out["note"] = q["note"]
    return out


def _further_tokens(q: QuantityTree, tokens: int, inputs: Sequence[str]) -> QuantityTree:
    """CO-8 (amended 2026-11-26, Q55): the request's reply tokens over the cost of a further
    reply (CO-9), with its range (the tokens over the largest and the smallest session) and n.
    Over it the serving baseline's rate is the further reply's multiple."""
    v, stats = q.get("value"), q.get("stats")
    if not isinstance(v, int | float) or v <= 0 or not tokens or not isinstance(stats, dict):
        return _quantity(None, Unit.TOKEN_PER_GPU_S, Scope.PROVE_SESSION, "D-L1-FURTHER-TOKENS",
                         inputs, NullReason.MISSING_INPUT)  # fmt: skip
    out = _quantity(tokens / v, Unit.TOKEN_PER_GPU_S, Scope.PROVE_SESSION, "D-L1-FURTHER-TOKENS",
                    inputs)  # fmt: skip
    out["stats"] = {"n": stats["n"], "n_failed": 0, "mean": tokens / v, "stdev": None,
                    "min": tokens / stats["max"], "max": tokens / stats["min"]}  # fmt: skip
    return out


def _diagnostic(figures: Sequence[SessionFigures], metric: str, unit: Unit) -> QuantityTree:
    """CO-9 (Q55, point 4): a harness-sampled figure of the prove step, over the counted
    sessions (D-STAT): a diagnostic one step down, never a ladder figure."""
    inputs: list[Input] = []
    for f in figures:
        q = (f.session.run.run.get("metrics") or {}).get(metric)  # type: ignore[attr-defined]
        inputs.append((f"{f.session.path}/run.json#/metrics/{metric}",
                       q if isinstance(q, dict) else None))  # fmt: skip
    if not any(q is not None for _, q in inputs):
        return _quantity(None, unit, None, "D-STAT", [ref for ref, _ in inputs],
                         NullReason.MISSING_INPUT)  # fmt: skip
    return statistic(inputs, [], __version__)


def _by_slot(causes: Sequence[tuple[int | None, str | None]]) -> list[str]:
    """Each cause once, with the slots it holds for ("slots 1, 2: ...")."""
    slots: dict[str, list[str]] = {}
    for slot, cause in causes:
        if cause:
            slots.setdefault(cause, []).append(str(slot))
    return [f"slot{'s' if len(k) > 1 else ''} {', '.join(k)}: {c}" for c, k in slots.items()]


def _split_block(figures: Sequence[SessionFigures]) -> dict[str, object]:
    """CO-9: where the generation part of a further reply comes from, the same for every counted
    session or none: the AD-4 marks, or the adapter's reported phases once each session's sum
    to its harness-timed prove call within the tolerance; with each session's check."""
    further = [f.further for f in figures]
    splits = {f.split if f else None for f in further}
    source = splits.pop() if len(splits) == 1 else None
    causes = _by_slot([(g.session.slot, g.further.cause if g.further else None)
                       for g in figures])  # fmt: skip
    if source is None and not causes and len(splits) > 1:
        causes = ["the counted sessions split their replies from different sources"]
    phase = GENERATION_PHASES.get(str(figures[0].session.run.run.get("system"))) \
        if figures and source == ADAPTER_PHASES else None  # fmt: skip
    return {
        "source": source,
        "phase": phase,
        "tolerance": ADAPTER_PHASE_TOLERANCE
        if source == ADAPTER_PHASES or any(f is not None and f.check is not None for f in further)
        else None,
        "sessions": [f.check for f in further if f is not None and f.check is not None],
        "cause": "; ".join(causes) if source is None and causes else None,
    }


def _further_fields(row: _Row, index: str, baseline: Input, price: Input, tokens: int,
                    batch: int | None, workload: str) -> dict[str, object]:  # fmt: skip
    """CO-9 (adopted 2026-11-26, Q55): the cost of a further reply and its two parts, both
    multiples, the one-time work apart with its 5 % mark, the proved rate over the further
    reply (CO-8 as Q55 amends it), the proving batch, and the prove step's diagnostics."""
    figures = row.figures
    further = [f.further for f in figures]
    events = [f"{f.session.path}/run.json#/events" for f in figures]
    proofs = [f"{f.session.path}/run.json#/proofs" for f in figures]
    split = _split_block(figures)
    adapter = split["source"] == ADAPTER_PHASES
    phase = split["phase"]
    if split["source"] == GENERATION_MARKS:
        split_in = [f"{f.session.path}/run.json#/marks" for f in figures]
        split_note = None
    elif adapter:
        split_in = [x for f in figures for x in (
            f"{f.session.path}/run.json#/adapter_phases/prove/{phase}",
            f"{f.session.path}/run.json#/adapter_phases/prove",
            f"{f.session.path}/run.json#/metrics/prove_call_seconds")]  # fmt: skip
        split_note = (f"generation as the adapter reports it (adapter_phases.prove.{phase}, "
                      "source adapter, tier reported), its prove phases summing to the "
                      "harness-timed prove call within "
                      f"{ADAPTER_PHASE_TOLERANCE:.0%} in every session")  # fmt: skip
    else:
        split_in = [*events, *proofs]
        split_note = f"no split: {split['cause']}" if split["cause"] else "no split"
    total = _pooled_quantity(further, "all", Unit.GPU_S_PER_REQUEST, "D-L1-FURTHER",
                             [*events, *proofs], NullReason.MISSING_INPUT,
                             f"pooled over {len(figures)} sessions: their GPU-seconds from "
                             "the start of prove to the last reply, over their replies",
                             )  # fmt: skip
    suffix = "-ADAPTER" if adapter else ""
    generation = _pooled_quantity(further, "generation", Unit.GPU_S_PER_REQUEST,
                                  f"D-L1-FURTHER-GENERATION{suffix}", split_in,
                                  NullReason.NOT_APPLICABLE, split_note)  # fmt: skip
    proving = _pooled_quantity(further, "proving", Unit.GPU_S_PER_REQUEST,
                               f"D-L1-FURTHER-PROVING{suffix}", [*events, *proofs, *split_in],
                               NullReason.NOT_APPLICABLE, split_note)  # fmt: skip
    if split["source"] is None:  # the parts are null together
        generation = _quantity(None, Unit.GPU_S_PER_REQUEST, Scope.PROVE_SESSION,
                               "D-L1-FURTHER-GENERATION", split_in, NullReason.NOT_APPLICABLE,
                               split_note)  # fmt: skip
        proving = _quantity(None, Unit.GPU_S_PER_REQUEST, Scope.PROVE_SESSION,
                            "D-L1-FURTHER-PROVING", split_in, NullReason.NOT_APPLICABLE,
                            split_note)  # fmt: skip
    total_ref = f"{index}/further_reply_gpu_seconds"
    proving_ref = f"{index}/further_reply_proving_gpu_seconds"
    # the one-time work: each session's own, from commit start to prove start, and the setup
    setups = [f.setup for f in further if f is not None and f.setup is not None]
    one_in = [*events, *[f"{f.session.path}/run.json#/setup" for f in figures
                         if f.further is not None and f.further.setup is not None],
              *sorted({str(s["record"]) + "#/gpu_seconds" for s in setups})]  # fmt: skip
    one_causes = _by_slot([(g.session.slot, g.further.one_time_cause if g.further else None)
                           for g in figures])  # fmt: skip
    one_note = ("the commit call and the harness taking its files, from commit start to prove "
                "start" + (", with the setup run's GPU-seconds and the restore of its state"
                           if setups else ""))  # fmt: skip
    one_time = _stat([f.one_time if f else None for f in further], Unit.GPU_S, Scope.COMMIT,
                     "D-L1-ONE-TIME", one_in, NullReason.MISSING_INPUT,
                     "; ".join(one_causes) if one_causes else one_note)  # fmt: skip
    one_ref = f"{index}/one_time_gpu_seconds"
    f_value, c_value = one_time.get("value"), total.get("value")
    mark = _quantity(
        one_time_mark(float(f_value), float(c_value))
        if isinstance(f_value, int | float) and isinstance(c_value, int | float) and c_value > 0
        else None,
        Unit.COUNT, None, "D-L1-ONE-TIME-MARK", [one_ref, total_ref], NullReason.MISSING_INPUT,
        "replies after which the one-time work is at most 5 % of the total",
    )  # fmt: skip
    return {
        "further_reply_gpu_seconds": total,
        "further_reply_generation_gpu_seconds": generation,
        "further_reply_proving_gpu_seconds": proving,
        "further_reply_split": split,
        "further_reply_multiple": _over_baseline(total_ref, total, baseline),
        "further_reply_proving_multiple": _over_baseline(proving_ref, proving, baseline),
        "further_reply_tokens_per_gpu_second": _further_tokens(
            total, tokens, [total_ref, "levels/L1.yaml#/request/output_tokens"]
        ),
        "further_reply_usd_per_reply": _usd(Scope.PROVE_SESSION, (total_ref, total), price),
        "one_time_gpu_seconds": one_time,
        "one_time_usd": derived(
            "D-L1-USD",
            __version__,
            Unit.USD,
            Scope.COMMIT,
            [(one_ref, one_time), price],
            lambda x: x[0] * x[1] / 3600,
        ),
        "one_time_mark_replies": mark,
        "one_time_setups": [
            {"setup_id": s["setup_id"], "record": s["record"], "gpu_seconds": s["gpu_seconds"]}
            for s in {str(s["setup_id"]): s for s in setups}.values()
        ],
        "proving_batch": {
            "replies": batch,
            "source": f"workloads/{workload}.yaml#/shape/batch_size",
        },
        "prove_gpu_util_mean": _diagnostic(figures, "prove_gpu_util_mean", Unit.PERCENT),
        "prove_gpu_memory_peak": _diagnostic(figures, "prove_gpu_memory_peak", Unit.MIB),
    }


def _row_tree(
    row: _Row,
    index: str,
    position: int | None,
    baseline: Input,
    price: Input,
    fidelity_rows: Mapping[str, object],
    n: int,
    tokens: int = 0,
) -> dict[str, object]:
    figures = row.figures
    proofs = [f"{f.session.path}/run.json#/proofs" for f in figures]
    causes = sorted({f"slot {f.session.slot}: {f.cause}" for f in figures if f.cause})
    marks = [f"{f.session.path}/run.json#/marks" for f in figures if f.generation is not None]
    steady = _stat([f.m for f in figures], Unit.GPU_S_PER_REQUEST, Scope.PROVE_STEADY,
                   "D-L1-STEADY", [*proofs, *marks], NullReason.NOT_APPLICABLE,
                   "no steady state: " + "; ".join(causes) if causes else None)  # fmt: skip
    events = [f"{f.session.path}/run.json#/events" for f in figures]
    session = _stat([f.per_reply for f in figures], Unit.GPU_S_PER_REQUEST, Scope.WHOLE_WALL,
                    "D-L1-SESSION", [*events, *proofs], NullReason.MISSING_INPUT,
                    f"whole sessions of {n} replies")  # fmt: skip
    steady_in = (f"{index}/steady_gpu_seconds_per_reply", steady)
    # CO-7: m = generation + proving where the adapter generates in a phase of its own (AD-4)
    phased = bool(figures) and all(f.generation is not None for f in figures)
    no_phase = None if phased else "no generation phase of its own: generation, if any, is " \
        "inside the proving interval"  # fmt: skip
    generation = _stat([f.generation if f.m is not None else None for f in figures],
                       Unit.GPU_S_PER_REQUEST, Scope.PROVE_STEADY, "D-L1-GENERATION",
                       marks or proofs, NullReason.NOT_APPLICABLE, no_phase)  # fmt: skip
    proving = _stat([f.m - f.generation if f.m is not None and f.generation is not None
                     else None for f in figures],
                    Unit.GPU_S_PER_REQUEST, Scope.PROVE_STEADY, "D-L1-PROVING",
                    [*proofs, *marks], NullReason.NOT_APPLICABLE, no_phase)  # fmt: skip
    generation_in = (f"{index}/steady_generation_gpu_seconds_per_reply", generation)
    proving_in = (f"{index}/steady_proving_gpu_seconds_per_reply", proving)
    session_in = (f"{index}/session_gpu_seconds_per_reply", session)
    # CO-7 (amended 2026-11-13): the session cost per reply splits the same way, timed as CO-1
    unsplit = NullReason.MISSING_INPUT if phased else NullReason.NOT_APPLICABLE
    session_generation = _stat([f.generation for f in figures], Unit.GPU_S_PER_REQUEST,
                               Scope.WHOLE_WALL, "D-L1-GENERATION", marks or proofs, unsplit,
                               no_phase)  # fmt: skip
    commit_proving = _stat([f.per_reply - f.generation
                            if f.per_reply is not None and f.generation is not None else None
                            for f in figures], Unit.GPU_S_PER_REQUEST, Scope.WHOLE_WALL,
                           "D-L1-COMMIT-PROVING", [*events, *proofs, *marks], unsplit,
                           no_phase)  # fmt: skip
    # CO-7 (amended 2026-11-15): the session cost per reply in its timed calls: the `commit`
    # call, the generation phase where there is one, and the rest (proving, and the seconds
    # between the calls); every row has the first and the last
    commit_part = _stat([f.commit for f in figures], Unit.GPU_S_PER_REQUEST, Scope.COMMIT,
                        "D-L1-COMMIT", events, NullReason.MISSING_INPUT)  # fmt: skip
    rest = _stat([f.per_reply - f.commit - (f.generation or 0.0)
                  if f.per_reply is not None and f.commit is not None
                  and (f.generation is not None or not phased) else None for f in figures],
                 Unit.GPU_S_PER_REQUEST, Scope.WHOLE_WALL, "D-L1-SESSION-PROVING",
                 [*events, *proofs, *marks], NullReason.MISSING_INPUT)  # fmt: skip
    # the generation phase per reply token: its GPU-seconds over N, over the request's reply
    # tokens (the level's request.output_tokens)
    per_token = _stat([f.generation / tokens if f.generation is not None and tokens else None
                       for f in figures], Unit.GPU_S_PER_TOKEN, Scope.WHOLE_WALL,
                      "D-L1-GENERATION-TOKEN", [*(marks or proofs), "levels/L1.yaml#/request/"
                                                "output_tokens"], unsplit, no_phase)  # fmt: skip
    # CO-8 (adopted 2026-11-16): the request's reply tokens over the whole sessions' GPU time
    reply_tokens = _reply_tokens(
        figures, tokens, [*events, *proofs, "levels/L1.yaml#/request/output_tokens"]
    )
    session_generation_in = (f"{index}/session_generation_gpu_seconds_per_reply",
                             session_generation)  # fmt: skip
    commit_proving_in = (f"{index}/session_commit_and_proving_gpu_seconds_per_reply",
                         commit_proving)  # fmt: skip
    first = (row.sessions.counted_in_order() or row.sessions.all
             or [s for s, _ in row.sessions.ineligible])[0]  # fmt: skip
    commit = first.run.get("manifest", "system", "upstream", "commit")
    configuration = first.run.get("manifest", "claim", "configuration")
    return {
        "system": row.system,
        "workload": row.workload,
        "configuration": None if configuration is None else str(configuration),
        "commit": commit if isinstance(commit, str) and len(commit) == 40 else None,
        "checks": row.checks,
        "passed": row.passed,
        "glyph": glyph(row.petals),
        "ranked": position is not None,
        "position": position,
        "unranked_reason": _unranked(row),
        "level_statement": row.relation,
        "multiple": _ratio("D-L1-MULTIPLE", Unit.RATIO, Scope.PROVE_STEADY, steady_in, baseline),
        "session_multiple": _ratio(
            "D-L1-MULTIPLE", Unit.RATIO, Scope.WHOLE_WALL, session_in, baseline
        ),
        "steady_gpu_seconds_per_reply": steady,
        "steady_generation_gpu_seconds_per_reply": generation,
        "steady_proving_gpu_seconds_per_reply": proving,
        "generation_multiple": _ratio(
            "D-L1-MULTIPLE", Unit.RATIO, Scope.PROVE_STEADY, generation_in, baseline
        ),
        "proving_multiple": _ratio(
            "D-L1-MULTIPLE", Unit.RATIO, Scope.PROVE_STEADY, proving_in, baseline
        ),
        "session_gpu_seconds_per_reply": session,
        "session_generation_gpu_seconds_per_reply": session_generation,
        "session_commit_and_proving_gpu_seconds_per_reply": commit_proving,
        "session_commit_gpu_seconds_per_reply": commit_part,
        "session_proving_gpu_seconds_per_reply": rest,
        "generation_gpu_seconds_per_reply_token": per_token,
        "session_reply_tokens_per_gpu_second": reply_tokens,
        "session_generation_multiple": _ratio(
            "D-L1-MULTIPLE", Unit.RATIO, Scope.WHOLE_WALL, session_generation_in, baseline
        ),
        "session_commit_and_proving_multiple": _ratio(
            "D-L1-MULTIPLE", Unit.RATIO, Scope.WHOLE_WALL, commit_proving_in, baseline
        ),
        "steady_usd_per_reply": _usd(Scope.PROVE_STEADY, steady_in, price),
        "session_usd_per_reply": _usd(Scope.WHOLE_WALL, session_in, price),
        "sessions": [f.tree() for f in figures],
        "incomplete_sessions": [s.incomplete_tree() for s in row.sessions.incomplete],
        "replaced_sessions": [
            {"run_id": a.run_id, "slot": a.slot, "replaced_by": b.run_id, "cause": why}
            for a, b, why in row.sessions.replaced
        ],
        # SE-3b: runs kept out of the release by RFC-0014 §Eligibility, with its reason codes
        "ineligible_sessions": [
            {"run_id": s.run_id, "slot": s.slot, "reasons": list(reasons)}
            for s, reasons in row.sessions.ineligible
        ],
        "fidelity": _row_fidelity(fidelity_rows.get(row.system)),
        "security": row.security,
        "verify_seconds_per_reply": _metric_stat(
            figures, "verify_seconds_per_request", Unit.S_PER_REQUEST, Scope.VERIFY
        ),
        "proof_bytes_per_reply": _metric_stat(
            figures, "proof_bytes_per_request", Unit.B_PER_REQUEST, None
        ),
    }


def _by_rule(out: dict[str, object], row: _Row, index: str, rule: str, root: Path,
             baseline: Input, price: Input, tokens: int) -> dict[str, object]:  # fmt: skip
    """The row's tree under the release's cost rule: unchanged under the whole-session rule;
    under CO-9 (Q55) each session also gives its own further reply and one-time work, and the
    row its CO-9 figures."""
    if rule != FURTHER_REPLY:
        return out
    out["sessions"] = [f.tree(rule) for f in row.figures]
    return out | _further_fields(
        row, index, baseline, price, tokens, _batch_size(root, row.workload), row.workload
    )


# ---------------------------------------------------------------- the board


def _with_steps(
    root: Path, release: str, level: object, rung: object, doc: dict[str, object] | None
) -> dict[str, object] | None:
    """FM-4a: a `fidelity.json` scored before the step tests existed gets them computed from its
    own stored scores (results are append-only, so the stored file is not written again)."""
    if doc is None or "steps" in doc:
        return doc
    randomness = beacon_randomness(root, level_id(level))
    if randomness is None:
        return doc  # no beacon record: FM-4 reads "no step tests stored"
    folder = fidelity_path(root, release, str(field_of(rung, "id"))).parent
    slots, slots_cause = fidelity_run_slots(_run_records(folder))  # FM-5: every part of the run
    controls: Sequence[object] = field_of(rung, "controls") or ()  # type: ignore[assignment]
    specs = [{k: field_of(c, k) for k in ("id", "kind", "recipe", "type")} for c in controls]
    return fidelity_with_steps(doc, specs, slots, randomness, slots_cause)


def build_board(  # noqa: PLR0915 (one statement per block of the board)
    root: Path, release: str, level: object, rule: str | None = None
) -> dict[str, object]:
    """RFC-0018 §The board file: the `board/1` tree of `release` under `level` (a level model,
    its tree, or its id), by the release's cost rule (Q55: `cost_rule`; `rule` overrides it, for
    a preview)."""
    rule = cost_rule(release, rule)
    level = _load_level(root, level)
    digest = level_digest(root, level)
    price_block, price = price_of(root, level)
    margin = field_of(field_of(level, "order"), "margin")
    if not isinstance(margin, int | float):
        raise IProofsError(ErrorKind.CONFIG, f"level {level_id(level)} has no order.margin")
    alpha = field_of(field_of(level, "fidelity"), "alpha")  # F5: the step tests' alpha
    level_alpha = float(alpha) if isinstance(alpha, int | float) else None
    runs = [RunView.read(p) for p in release_run_dirs(root, release)]
    reply_tokens = int_of(field_of(level, "request"), "output_tokens", 0)
    dates: set[str] = set()
    rungs_out, summaries = [], []
    rung_list: Sequence[object] = field_of(level, "rungs") or ()  # type: ignore[assignment]
    for ri, rung in enumerate(rung_list):
        rung_id = str(field_of(rung, "id"))
        n = int_of(rung, "requests_per_session", 0)
        base = f"releases/{release}/board.json#/rungs/{ri}"
        baseline_block, baseline, read = _baseline(root, runs, level, rung, digest, base, price,
                                                   reply_tokens)  # fmt: skip
        dates |= {r.run_id[:10] for r in read}
        fidelity_block, fidelity_doc = _fidelity(root, release, rung_id)
        fidelity_doc = _with_steps(root, release, level, rung, fidelity_doc)
        fidelity_rows = fidelity_doc.get("rows") if fidelity_doc else None
        fidelity_rows = fidelity_rows if isinstance(fidelity_rows, dict) else {}
        rows = []
        for system, workload in sorted(_workloads(rung).items()):
            sessions = row_sessions(root, release, level, rung_id, system, digest)
            kept_out = [s for s, _ in sessions.ineligible]
            if not sessions.all and not kept_out:
                continue  # not run: no row (RFC-0018 §The board file)
            dates |= {s.run_id[:10] for s in (*sessions.all, *kept_out)}
            states = checks_from(root, release, level, rung_id, system, sessions, digest)
            security, stated = _security(level, system)
            first = (sessions.counted_in_order() or sessions.all or kept_out)[0]
            commit = first.run.get("manifest", "system", "upstream", "commit")
            configuration = first.run.get("manifest", "claim", "configuration")
            coverage = Coverage(_granularity(root, system), _batch_size(root, str(workload)))
            props = load_properties(root, system)
            build = load_proof_build(root, release, system)
            petals = statement_petals(
                props, {k: v.state for k, v in states.items()},
                str(commit) if isinstance(commit, str) else None, coverage, build,
                record_path(release, system) if build is not None else None,
            )  # fmt: skip
            fid = states["fidelity"]
            petals["faithful_model"] = faithful_model(
                fid.state,
                fid.cause,
                fidelity_doc,
                system,
                _policy(root, system, configuration),
                level_alpha,
                str(field_of(field_of(rung, "reference"), "dtype")),
                _weight_bits(root, str(workload)),
            )
            rows.append(_Row(
                system, str(workload), sessions,
                [session_figures(s, n, level, root) for s in sessions.counted_in_order()],
                {name: states[name].tree() for name in CHECKS},
                all(states[name].state == HELD for name in CHECKS), security, stated, petals,
                level_statement(props, commit),
            ))  # fmt: skip
        has_baseline = baseline[1] is not None and baseline[1].get("value") is not None
        ordered = order([r.summary(has_baseline, rule) for r in rows], float(margin))
        by_system = {r.system: r for r in rows}
        summaries.append(RungSummary(rung_id, int_of(rung, "parameters_total", 0),
                                     tuple(ordered)))  # fmt: skip
        rungs_out.append({
            "id": rung_id,
            "model": str(field_of(rung, "model")),
            "publisher": str(field_of(rung, "publisher")),
            "parameters_total": int_of(rung, "parameters_total", 0),
            "parameters_active": int_of(rung, "parameters_active", 0),
            "requests_per_session": n,
            "systems_run": len(rows),
            "baseline": baseline_block,
            "fidelity": fidelity_block,
            "rows": [_by_rule(_row_tree(by_system[s.system], f"{base}/rows/{j}", p, baseline,
                                        price, fidelity_rows, n, reply_tokens),
                              by_system[s.system], f"{base}/rows/{j}", rule, root, baseline,
                              price, reply_tokens)
                     for j, (s, p) in enumerate(ordered)],
        })  # fmt: skip
        teacher_forced = _teacher_forced(  # FI-16: each row's proved replies, from its sessions
            root, release, rung_id, {r.system: _proved_replies(r.sessions, level, n) for r in rows}
        )
        if teacher_forced is not None:  # SI-9: printed figures only; absent while not scored
            rungs_out[-1]["teacher_forced"] = teacher_forced
    request = field_of(level, "request")
    return ({"cost_rule": rule} if rule == FURTHER_REPLY else {}) | {
        "schema": "board/1",
        "level": level_id(level),
        "level_digest": digest,
        "release": release,
        "date": max(dates) if dates else None,
        "price": price_block,
        "request": {
            "prompt_tokens": int_of(request, "prompt_tokens", 0),
            "output_tokens": int_of(request, "output_tokens", 0),
            "decoding": str(field_of(request, "decoding")),
        },
        "frontier": frontier(summaries),
        "rungs": rungs_out,
    }


def _key(path: Path, *keys: str) -> object:
    """`keys` in the YAML file at `path`, None when the file or a key is missing."""
    found: object = load_yaml(path) if path.is_file() else None
    for k in keys:
        found = found.get(k) if isinstance(found, Mapping) else None
    return found


def _granularity(root: Path, system: str) -> str | None:
    """How much one proof covers (`proofs.granularity` of system.yaml), the glyph's Coverage."""
    found = _key(root / "systems" / system / "system.yaml", "proofs", "granularity")
    return found if isinstance(found, str) else None


def _weight_bits(root: Path, workload: str) -> float | None:
    """The proved copy's weight bits (`precision.weight_bits.bits` of the workload): a printed
    sentence of the Fidelity petal reads it, no step does."""
    found = _key(root / "workloads" / f"{workload}.yaml", "precision", "weight_bits", "bits")
    return float(found) if isinstance(found, int | float) and not isinstance(found, bool) else None


def _batch_size(root: Path, workload: str) -> int | None:
    """The replies of one batch (`shape.batch_size` of the workload), the glyph's Coverage."""
    found = _key(root / "workloads" / f"{workload}.yaml", "shape", "batch_size")
    return found if isinstance(found, int) and not isinstance(found, bool) else None


def _policy(root: Path, system: str, configuration: object) -> str | None:
    """The claim card's `coverage.policy.kind` for the row's configuration (FM-3)."""
    if not isinstance(configuration, str):
        return None
    card = card_path(root, system, configuration)
    found = None if card is None else _key(card, "coverage", "policy", "kind")
    return found if isinstance(found, str) else None


def beacon_randomness(root: Path, level: str) -> str | None:
    """The beacon round's randomness that seeds the FI-4 tests (`levels/<id>-beacon.json`)."""
    path = root / "levels" / f"{level}-beacon.json"
    if not path.is_file():
        return None
    found = json.loads(path.read_text()).get("randomness")
    return str(found) if isinstance(found, str) else None


def _workloads(rung: object) -> dict[str, str]:
    found = field_of(rung, "workloads")
    return {str(k): str(v) for k, v in found.items()} if isinstance(found, Mapping) else {}


def board_path(root: Path, release: str) -> Path:
    return root / "releases" / release / "board.json"
