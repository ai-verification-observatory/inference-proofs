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
    Input,
    QuantityTree,
    derived,
    generation_seconds,
    nonzero,
    release_groups,
    session_per_reply,
    steady_per_reply,
)
from iproofs.errors import ErrorKind, IProofsError
from iproofs.glyph import (
    PETALS,
    Petal,
    any_model,
    faithful_model,
    glyph,
    load_properties,
    statement_petals,
)
from iproofs.quantity import Grade, NullReason, Scope, SourceKind, Tier, Unit
from iproofs.release import RunView
from iproofs.serialize import load_yaml

NO_SECURITY_LEVEL = "publisher states no security level"  # OR-2

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

    @property
    def ranked(self) -> bool:
        """OR-1, OR-2: a passed row whose publisher states a security level."""
        return self.passed and self.stated


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
    """OR-6: the largest rung by total parameters with a passed row; the rows at position 1
    there, or every passed row when none is ranked; and the count of systems run on it."""
    for rung in sorted(rungs, key=lambda r: -r.parameters_total):
        passed = [(r, p) for r, p in rung.rows if r.passed]
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

    def tree(self) -> dict[str, object]:
        return {
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


def session_figures(s: Session, n: int, level: object) -> SessionFigures:
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
    commit = _event(s.run, "commit.start")
    per_reply = (
        None if gpus is None or commit is None or not times
        else session_per_reply(commit, times, n, gpus)
    )  # fmt: skip
    replies = sum(g.size for g in groups)
    generation = None if phase is None or gpus is None or not replies else phase * gpus / replies
    return SessionFigures(s, gpus, tuple(g.size for g in groups), m, cause, per_reply, generation)


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
    price: Input,
) -> tuple[dict[str, object], Input, list[RunView]]:  # fmt: skip
    """The rung's baseline block, its GPU-seconds per reply as a formula input, and the runs
    read. The first run by start time of the rung's serving record under this level that has a
    full load is used."""
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
            "ladder": [], "cause": cause,
        }  # fmt: skip
        return missing, (ref, q), mine
    run, load = found
    q = dict(load.gpu_seconds_per_reply)
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
    block: dict[str, object] = {
        "path": rel(root, path),
        "bar": {"control": str(bar["control"]), "mean_prefix": bar["mean_prefix"]}
        if isinstance(bar, dict) else None,
        "controls": controls,
        "cause": None if isinstance(bar, dict) else "no damaged control that every honest "
        "control scores above (FI-5)",
    }  # fmt: skip
    return block, doc if isinstance(doc, dict) else None


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

    def summary(self, has_baseline: bool) -> RowSummary:
        ms = [f.m for f in self.figures]
        steady = bool(ms) and all(m is not None for m in ms)
        cost = [f.per_reply for f in self.figures]
        full = bool(cost) and all(c is not None for c in cost)
        return RowSummary(
            self.system, self.passed, self.stated,
            multiple=statistics.mean(m for m in ms if m is not None)
            if steady and has_baseline else None,
            m=tuple(m for m in ms if m is not None) if steady else (),
            session_mean=statistics.mean(c for c in cost if c is not None) if full else None,
            session=tuple(c for c in cost if c is not None) if full else (),
        )  # fmt: skip


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


def _row_tree(
    row: _Row,
    index: str,
    position: int | None,
    baseline: Input,
    price: Input,
    fidelity_rows: Mapping[str, object],
    n: int,
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
                    f"cold sessions of {n} replies")  # fmt: skip
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
    first = (row.sessions.counted_in_order() or row.sessions.all)[0]
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
        "unranked_reason": NO_SECURITY_LEVEL if row.passed and not row.stated else None,
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
        "steady_usd_per_reply": _usd(Scope.PROVE_STEADY, steady_in, price),
        "session_usd_per_reply": _usd(Scope.WHOLE_WALL, session_in, price),
        "sessions": [f.tree() for f in figures],
        "incomplete_sessions": [s.incomplete_tree() for s in row.sessions.incomplete],
        "fidelity": _row_fidelity(fidelity_rows.get(row.system)),
        "security": row.security,
        "verify_seconds_per_reply": _metric_stat(
            figures, "verify_seconds_per_request", Unit.S_PER_REQUEST, Scope.VERIFY
        ),
        "proof_bytes_per_reply": _metric_stat(
            figures, "proof_bytes_per_request", Unit.B_PER_REQUEST, None
        ),
    }


# ---------------------------------------------------------------- the board


def build_board(root: Path, release: str, level: object) -> dict[str, object]:
    """RFC-0018 §The board file: the `board/1` tree of `release` under `level` (a level model,
    its tree, or its id)."""
    level = _load_level(root, level)
    digest = level_digest(root, level)
    price_block, price = price_of(root, level)
    margin = field_of(field_of(level, "order"), "margin")
    if not isinstance(margin, int | float):
        raise IProofsError(ErrorKind.CONFIG, f"level {level_id(level)} has no order.margin")
    runs = [RunView.read(p) for p in release_run_dirs(root, release)]
    randomness = beacon_randomness(root, level_id(level))
    dates: set[str] = set()
    rungs_out, summaries = [], []
    rung_list: Sequence[object] = field_of(level, "rungs") or ()  # type: ignore[assignment]
    for ri, rung in enumerate(rung_list):
        rung_id = str(field_of(rung, "id"))
        n = int_of(rung, "requests_per_session", 0)
        base = f"releases/{release}/board.json#/rungs/{ri}"
        baseline_block, baseline, read = _baseline(root, runs, level, rung, digest, base, price)
        dates |= {r.run_id[:10] for r in read}
        fidelity_block, fidelity_doc = _fidelity(root, release, rung_id)
        fidelity_rows = fidelity_doc.get("rows") if fidelity_doc else None
        fidelity_rows = fidelity_rows if isinstance(fidelity_rows, dict) else {}
        rows = []
        for system, workload in sorted(_workloads(rung).items()):
            sessions = row_sessions(root, release, level, rung_id, system, digest)
            if not sessions.all:
                continue  # not run: no row (RFC-0018 §The board file)
            dates |= {s.run_id[:10] for s in sessions.all}
            states = checks_from(root, release, level, rung_id, system, sessions, digest)
            security, stated = _security(level, system)
            first = (sessions.counted_in_order() or sessions.all)[0]
            commit = first.run.get("manifest", "system", "upstream", "commit")
            petals = statement_petals(
                load_properties(root, system), {k: v.state for k, v in states.items()},
                str(commit) if isinstance(commit, str) else None,
            )  # fmt: skip
            fid = states["fidelity"]
            petals["faithful_model"] = faithful_model(fid.state, fid.cause, fidelity_doc, system,
                                                      randomness)  # fmt: skip
            petals["any_model"] = any_model(0, 0, True)  # set once every rung is read
            rows.append(_Row(
                system, str(workload), sessions,
                [session_figures(s, n, level) for s in sessions.counted_in_order()],
                {name: states[name].tree() for name in CHECKS},
                all(states[name].state == HELD for name in CHECKS), security, stated, petals,
            ))  # fmt: skip
        has_baseline = baseline[1] is not None and baseline[1].get("value") is not None
        ordered = order([r.summary(has_baseline) for r in rows], float(margin))
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
            "rows": [_row_tree(by_system[s.system], f"{base}/rows/{j}", p, baseline, price,
                               fidelity_rows, n)
                     for j, (s, p) in enumerate(ordered)],
        })  # fmt: skip
    _any_model(rungs_out)
    request = field_of(level, "request")
    return {
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


def _any_model(rungs: Sequence[Mapping[str, object]]) -> None:
    """The `any_model` petal of every row, from the system's rows on every rung."""
    rows = [r for rung in rungs for r in rung["rows"]]  # type: ignore[attr-defined]
    for r in rows:
        mine = [o for o in rows if o["system"] == r["system"]]
        passed_rungs = sum(o["passed"] is True for o in mine)
        undecided = any(c["state"] == "undecided" for o in mine for c in o["checks"].values())
        r["glyph"][PETALS.index("any_model")] = any_model(passed_rungs, len(rungs),
                                                          undecided).tree()  # fmt: skip


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
