"""The six Level 1 checks of one row (RFC-0018 §The six checks, CH-1 to CH-8).

Every state is computed from stored records only (CH-6): the release's counted sessions
(`run.json`, `manifest.json`, `controls.json`, `verify-trace/*.json`), the rung's
`fidelity.json` and reproduction records `results/<release>/<system>/reproductions/<check>.json`.
No reviewer sets a state. Nothing here writes a file or reads a clock.
"""

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from iproofs.errors import ErrorKind, IProofsError
from iproofs.release import RunView
from iproofs.serialize import load_yaml

HELD, FAILED, UNDECIDED = "held", "failed", "undecided"
SYSTEM_LIMIT, NOT_RUN, NOT_RESOLVED, NOT_REPRODUCED = (
    "system limit",
    "not run",
    "not resolved",
    "not reproduced",
)
# The order of the table (CH-7): the glyph draws the checks in this order.
CHECKS = ("run", "model", "prompt", "reply", "no_weight_file", "fidelity")
COUNTED_TRIALS = 3  # CH-1: 3 counted trials per control (per position for C1)
C1_POSITIONS = ("first", "last", "interior")
UNCOUNTED = frozenset({"void", "error"})  # trials that decided nothing (CH-1)
# When parts of a check disagree, the first state here decides (a failure stands over a gap).
_CAUSE_ORDER = (SYSTEM_LIMIT, NOT_REPRODUCED, NOT_RUN, NOT_RESOLVED)


@dataclass(frozen=True, slots=True)
class CheckState:
    """One check's outcome. `cause` is set only on `undecided` (one of the four causes);
    `evidence` holds repository paths; `note` a publisher's sentence (CH-5) or the reason."""

    state: str
    cause: str | None
    evidence: tuple[str, ...]
    note: str | None = None

    def tree(self) -> dict[str, object]:
        return {
            "state": self.state,
            "cause": self.cause,
            "evidence": list(self.evidence),
            "note": self.note,
        }


def _held(evidence: Iterable[str]) -> CheckState:
    return CheckState(HELD, None, tuple(evidence))


def _undecided(cause: str, evidence: Iterable[str] = (), note: str | None = None) -> CheckState:
    return CheckState(UNDECIDED, cause, tuple(evidence), note)


def _combine(parts: Sequence[CheckState]) -> CheckState:
    """A check made of parts (MODEL: P1 and C3; REPLY: coverage and three positions): failed if
    any part failed, else undecided with the first cause of `_CAUSE_ORDER`, else held."""
    evidence = tuple(dict.fromkeys(e for p in parts for e in p.evidence))
    failed = [p for p in parts if p.state == FAILED]
    if failed:
        return CheckState(FAILED, None, evidence, _notes(failed))
    open_ = [p for p in parts if p.state == UNDECIDED]
    if open_:
        cause = min((str(p.cause) for p in open_), key=_CAUSE_ORDER.index)
        return CheckState(UNDECIDED, cause, evidence, _notes(p for p in open_ if p.cause == cause))
    return CheckState(HELD, None, evidence)


def _notes(parts: Iterable[CheckState]) -> str | None:
    notes = list(dict.fromkeys(p.note for p in parts if p.note))
    return "; ".join(notes) if notes else None


# ---------------------------------------------------------------- level and release access


def field_of(node: object, name: str, default: object = None) -> object:
    """A field of the level model or of its tree read from `levels/<id>.yaml`."""
    if isinstance(node, Mapping):
        return node.get(name, default)
    return getattr(node, name, default)


def int_of(node: object, name: str, default: int) -> int:
    value = field_of(node, name)
    return value if isinstance(value, int) else default


def level_id(level: object) -> str:
    return str(field_of(level, "id"))


def rung_of(level: object, rung: str) -> object:
    for r in field_of(level, "rungs") or ():  # type: ignore[attr-defined]
        if field_of(r, "id") == rung:
            return r
    raise IProofsError(ErrorKind.CONFIG, f"level {level_id(level)} has no rung {rung!r}")


def rung_workload(level: object, rung: str, system: str) -> str | None:
    workloads = field_of(rung_of(level, rung), "workloads") or {}
    found = field_of(workloads, system)
    return None if found is None else str(found)


def level_digest(root: Path, level: object) -> str:
    """The digest a counted run's manifest names for this level (RFC-0018 §The level file)."""
    from iproofs.level import level_digest as digest  # noqa: PLC0415

    return digest(root / "levels" / f"{level_id(level)}.yaml")


def release_run_dirs(root: Path, release: str) -> list[Path]:
    """The release's runs: `releases/<release>/release.yaml` `runs` less its superseded runs
    when the record exists, else every run directory under `results/<release>/`."""
    record = root / "releases" / release / "release.yaml"
    if record.is_file():
        doc = load_yaml(record)
        superseded = {
            str(s.get("run_id")) for s in _list(doc.get("superseded_runs")) if isinstance(s, dict)
        }
        dirs = [root / str(p) for p in _list(doc.get("runs"))]
        return [d for d in dirs if d.name not in superseded and (d / "run.json").is_file()]
    return sorted(p.parent for p in (root / "results" / release).glob("*/*/run.json"))


def _list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def rel(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


# ---------------------------------------------------------------- sessions (SE-1 to SE-4)


@dataclass(frozen=True, slots=True)
class Session:
    """One stored session of a row: complete or not, with the slot its manifest names."""

    run: RunView
    path: str  # the run directory as a repository path
    slot: int | None
    started: str
    complete: bool
    cause: str | None  # why the session is incomplete

    @property
    def run_id(self) -> str:
        return self.run.run_id

    def incomplete_tree(self) -> dict[str, object]:
        failure = self.run.run.get("failure")
        failure = failure if isinstance(failure, dict) else {}
        lines = failure.get("last_lines")
        last = lines[-1] if isinstance(lines, list) and lines else None
        code = failure.get("exit_code")
        return {
            "run_id": self.run_id,
            "slot": self.slot,
            "exit_code": code if isinstance(code, int) else None,
            "step": None if failure.get("step") is None else str(failure["step"]),
            "cause": self.cause or "incomplete",
            "last_line": None if last is None else str(last)[:500],
        }


@dataclass(frozen=True)
class RowSessions:
    """SE-3: per slot the first complete session by start time; every incomplete one."""

    counted: dict[int, Session]
    incomplete: list[Session]
    all: list[Session] = field(default_factory=list)

    def counted_in_order(self) -> list[Session]:
        return [self.counted[k] for k in sorted(self.counted)]


def started_at(run: RunView) -> str:
    """The session's start: its first command's `started_at` (ISO, so text order is time)."""
    commands = run.manifest.get("commands")
    times = [str(c["started_at"]) for c in _list(commands)
             if isinstance(c, dict) and c.get("started_at")]  # fmt: skip
    return min(times) if times else ""


def _requests(run: RunView) -> dict[int, list[dict[str, object]]]:
    out: dict[int, list[dict[str, object]]] = {}
    for p in _list(run.run.get("proofs")):
        if isinstance(p, dict) and isinstance(p.get("request_index"), int):
            out.setdefault(int(p["request_index"]), []).append(p)
    return out


def _incomplete_cause(run: RunView, n: int) -> str | None:
    """SE-1: complete when `prove` exited 0 and every one of the N requests has accepted
    proofs; None when complete, else the cause."""
    if not run.ok:
        failure = run.run.get("failure")
        message = failure.get("message") if isinstance(failure, dict) else None
        return str(message) if message else "the session did not complete"
    if run.get("manifest", "system", "adapter_dirty") is not False:
        return "the adapter tree was dirty or unknown"
    requests = _requests(run)
    accepted = sum(
        1 for i in range(n)
        if requests.get(i) and all(p.get("verdict") == "accept" for p in requests[i])
    )  # fmt: skip
    if accepted != n:
        return f"{accepted} of {n} requests have accepted proofs"
    return None


def row_sessions(
    root: Path, release: str, level: object, rung: str, system: str, digest: str | None = None
) -> RowSessions:
    """The row's sessions among the release's runs: the system's runs of the rung's workload
    whose manifest names this level by digest, controls excluded, ordered by start time."""
    workload = rung_workload(level, rung, system)
    n = int_of(rung_of(level, rung), "requests_per_session", 0)
    digest = digest or level_digest(root, level)
    found = []
    for path in release_run_dirs(root, release):
        run = RunView.read(path)
        if (run.run.get("system") != system or run.run.get("control") is True
                or run.get("manifest", "workload", "id") != workload
                or run.get("manifest", "level", "digest") != digest):  # fmt: skip
            continue
        slot = run.get("manifest", "session", "slot")
        cause = _incomplete_cause(run, n)
        if not isinstance(slot, int):
            slot, cause = None, cause or "the manifest names no session slot"
        found.append(Session(run, rel(root, path), slot, started_at(run), cause is None, cause))
    found.sort(key=lambda s: (s.started, s.run_id))
    counted: dict[int, Session] = {}
    for s in found:
        if s.complete and s.slot is not None and s.slot not in counted:
            counted[s.slot] = s
    return RowSessions(counted, [s for s in found if not s.complete], found)


# ---------------------------------------------------------------- RUN


def _forbidden_flags(root: Path, system: str) -> list[str]:
    path = root / "systems" / system / "system.yaml"
    doc = load_yaml(path) if path.is_file() else {}
    return [str(f) for f in _list(doc.get("forbidden_flags"))]


def _weakened(run: RunView, flags: Sequence[str]) -> list[str]:
    used = []
    for c in _list(run.manifest.get("commands")):
        argv = c.get("argv") if isinstance(c, dict) else None
        used += [str(a) for a in _list(argv) if any(str(a).startswith(f) for f in flags)]
    return used


def check_run(sessions: RowSessions, level: object, flags: Sequence[str]) -> CheckState:
    """RUN: held when every slot has a complete session and no counted session used a
    weakening flag; failed on a weakening flag or a slot with `attempts_per_slot` incomplete
    runs and none complete; else undecided, `not run`."""
    for s in sessions.counted_in_order():
        used = _weakened(s.run, flags)
        if used:
            return CheckState(FAILED, None, (f"{s.path}/manifest.json",),
                              f"{s.run_id} used {', '.join(sorted(set(used)))}")  # fmt: skip
    slots = int_of(field_of(level, "sessions"), "slots", 3)
    attempts = int_of(field_of(level, "sessions"), "attempts_per_slot", 5)
    for k in range(1, slots + 1):
        tried = [s for s in sessions.incomplete if s.slot == k]
        if k not in sessions.counted and len(tried) >= attempts:
            return CheckState(FAILED, None, tuple(f"{s.path}/run.json" for s in tried),
                              f"slot {k} has {len(tried)} incomplete runs")  # fmt: skip
    evidence = [f"{s.path}/run.json" for s in sessions.counted_in_order()]
    missing = [k for k in range(1, slots + 1) if k not in sessions.counted]
    if missing:
        slots_text = ", ".join(str(k) for k in missing)
        return _undecided(NOT_RUN, evidence, f"no complete session in slot {slots_text}")
    return _held(evidence)


# ---------------------------------------------------------------- MODEL, PROMPT, REPLY


@dataclass(frozen=True, slots=True)
class Trial:
    control: str
    position: str | None
    outcome: str
    seed_index: int
    evidence: str


def _position(trial: Mapping[str, object]) -> str | None:
    """C1's reply position, as the runner records it on each trial (`detail.position`); a C1
    trial without one counts at no position."""
    detail = trial.get("detail")
    position = detail.get("position") if isinstance(detail, Mapping) else None
    return str(position) if position in C1_POSITIONS else None


def _interior_ok(seed: object, trial: Mapping[str, object], output: int) -> bool:
    """CH-3: an interior trial k mutates `seeded_index(control_seed, "C1-interior", k, R - 2)
    + 1`; a trial at another index does not count."""
    from iproofs.controls import seeded_index  # noqa: PLC0415

    mutation = trial.get("mutation")
    index = mutation.get("index") if isinstance(mutation, Mapping) else None
    k = trial.get("seed_index")
    if not isinstance(index, int) or not isinstance(k, int) or not isinstance(seed, str):
        return False
    return index == seeded_index(seed, "C1-interior", k, output - 2) + 1


def control_trials(sessions: RowSessions, output: int) -> tuple[list[Trial], list[str], str | None]:
    """Every trial of the counted sessions' `controls.json`, with the ids of the controls
    present and the note of a perturbed commitment equal to the honest one (CH-2)."""
    trials: list[Trial] = []
    present: list[str] = []
    same_commitment = None
    for s in sessions.counted_in_order():
        doc = s.run.controls
        if not isinstance(doc, dict):
            continue
        path = f"{s.path}/controls.json"
        perturbed = doc.get("perturbed_commitment")
        honest = s.run.get("manifest", "commitment", "commitment_id")
        if isinstance(perturbed, dict) and perturbed.get("commitment_id") == honest:
            same_commitment = "the weight change left the commitment unchanged (CH-2)"
        seed = doc.get("control_seed")
        for i, c in enumerate(_list(doc.get("controls"))):
            if not isinstance(c, dict):
                continue
            cid = str(c.get("id"))
            present.append(cid)
            for t in _list(c.get("trials")):
                if not isinstance(t, dict):
                    continue
                position = _position(t) if cid == "C1" else None
                outcome = str(t.get("outcome"))
                if (
                    position == "interior"
                    and outcome not in UNCOUNTED
                    and not _interior_ok(seed, t, output)
                ):
                    continue  # not the seeded interior position: it does not count
                trials.append(Trial(cid, position, outcome, int(t.get("seed_index") or 0),
                                    f"{path}#/controls/{i}"))  # fmt: skip
    return trials, present, same_commitment


def _reproduction(root: Path, release: str, system: str, check: str) -> Path | None:
    path = root / "results" / release / system / "reproductions" / f"{check}.json"
    return path if path.is_file() else None


def control_state(
    trials: Sequence[Trial],
    present: Sequence[str],
    control: str,
    refused: frozenset[str],
    position: str | None = None,
) -> CheckState:
    """One control at one position: failed when a counted trial was accepted, held when at
    least 3 counted trials (`void` and `error` left out, CH-1) were all refused, else
    undecided: `not run` when the control is absent or has no counted trial, `not resolved`
    otherwise."""
    mine = [t for t in trials if t.control == control and t.position == position]
    counted = [t for t in mine if t.outcome not in UNCOUNTED]
    evidence = tuple(dict.fromkeys(t.evidence for t in mine))
    where = control if position is None else f"{control} at the {position} position"
    if any(t.outcome == "accepted" for t in counted):
        return CheckState(FAILED, None, evidence, f"{where}: a trial was accepted")
    if control not in present or not counted:
        return _undecided(NOT_RUN, evidence, f"{where}: no counted trial stored")
    if len(counted) >= COUNTED_TRIALS and all(t.outcome in refused for t in counted):
        return CheckState(HELD, None, evidence)
    held = sum(t.outcome in refused for t in counted)
    return _undecided(NOT_RESOLVED, evidence, f"{where}: {held} of {COUNTED_TRIALS} trials refused")


def _reproduced(state: CheckState, root: Path, release: str, system: str, check: str) -> CheckState:
    """CH-8: a failure from an accepted trial stands only with a reproduction record."""
    if state.state != FAILED:
        return state
    found = _reproduction(root, release, system, check)
    if found is None:
        return _undecided(NOT_REPRODUCED, state.evidence, state.note)
    return CheckState(FAILED, None, (*state.evidence, rel(root, found)), state.note)


VERIFIER_REFUSED = frozenset({"rejected"})
PROVER_REFUSED = frozenset({"rejected", "prover_failed"})  # P1: no accepted proof


def coverage_state(sessions: RowSessions, output: int) -> CheckState:
    """REPLY, first half (RFC-0017 INV-REQ-2): every request's accepted proofs claim
    `output` reply tokens between them."""
    for s in sessions.counted_in_order():
        for i, proofs in sorted(_requests(s.run).items()):
            claimed = sum(len(_list(p.get("claimed_output"))) for p in proofs)
            if claimed != output:
                return CheckState(FAILED, None, (f"{s.path}/run.json",),
                                  f"{s.run_id} request {i}: {claimed} of {output} reply tokens "
                                  "covered")  # fmt: skip
    return _held(f"{s.path}/run.json" for s in sessions.counted_in_order())


# ---------------------------------------------------------------- NO WEIGHT FILE (CH-4)


def no_weight_file_state(sessions: RowSessions) -> CheckState:
    """Held when every counted verdict has a trace written by a trace tool, with no GPU
    visible, no model file present and no model file opened; failed when a trace names a model
    file; else undecided, `not run` (a missing trace, no trace tool, a GPU or a model file in
    reach)."""
    if not sessions.counted:
        return _undecided(NOT_RUN, (), "no counted session")
    opened: list[str] = []
    gaps: list[str] = []
    evidence: list[str] = []
    for s in sessions.counted_in_order():
        evidence.append(f"{s.path}/verify-trace/")
        for p in _list(s.run.run.get("proofs")):
            if not isinstance(p, dict) or p.get("verdict") is None:
                continue
            pid = str(p.get("proof_id"))
            path = s.run.path / "verify-trace" / f"{pid}.json"
            if not path.is_file():
                gaps.append(f"{s.run_id}/{pid}: no trace")
                continue
            trace = json.loads(path.read_text())
            files = [
                f
                for f in _list(trace.get("model_files_opened"))
                if isinstance(f, dict) and f.get("ok") is True
            ]  # a failed open read nothing
            if files:
                opened.append(f"{s.path}/verify-trace/{pid}.json")
            elif trace.get("tool") is None:
                gaps.append(f"{s.run_id}/{pid}: no trace tool")
            elif trace.get("gpu_visible") is not False:
                gaps.append(f"{s.run_id}/{pid}: a GPU was visible")
            elif trace.get("model_files_present") is not False:
                gaps.append(f"{s.run_id}/{pid}: model files were present")
    if opened:
        return CheckState(FAILED, None, tuple(opened), "a verify call opened a model file")
    if gaps:
        more = f" (and {len(gaps) - 1} more)" if len(gaps) > 1 else ""
        return _undecided(NOT_RUN, evidence, gaps[0] + more)
    return _held(evidence)


# ---------------------------------------------------------------- FIDELITY (FI-6)


def fidelity_path(root: Path, release: str, rung: str) -> Path:
    return root / "results" / release / "fidelity" / rung / "fidelity.json"


def fidelity_state(root: Path, release: str, rung: str, system: str, digest: str) -> CheckState:
    """FIDELITY: the row's state as the rung's `fidelity.json` computed it."""
    path = fidelity_path(root, release, rung)
    if not path.is_file():
        return _undecided(NOT_RUN, (), "no fidelity.json for the rung")
    doc = json.loads(path.read_text())
    where = (rel(root, path),)
    level = doc.get("level")
    if isinstance(level, dict) and level.get("digest") not in (None, digest):
        return _undecided(NOT_RUN, where, "fidelity.json names another level digest")
    row = (doc.get("rows") or {}).get(system)
    if not isinstance(row, dict):
        return _undecided(NOT_RUN, where, "fidelity.json has no row for the system")
    state, cause = row.get("state"), row.get("cause")
    if state in (HELD, FAILED):
        return CheckState(str(state), None, where)
    if state == UNDECIDED and cause in _CAUSE_ORDER:
        return _undecided(str(cause), where)
    return _undecided(NOT_RESOLVED, where, f"fidelity.json state {state!r}")


# ---------------------------------------------------------------- the row


def _limit(level: object, system: str, check: str) -> CheckState | None:
    """CH-5: a test the system's design makes impossible, recorded in the level file as
    `systems.<id>.limits.<check>` {words, source}: undecided, `system limit`."""
    limits = field_of(field_of(field_of(level, "systems") or {}, system) or {}, "limits") or {}
    found = field_of(limits, check)
    if found is None:
        return None
    source = field_of(found, "source")
    return _undecided(SYSTEM_LIMIT, () if source is None else (str(source),),
                      str(field_of(found, "words") or "") or None)  # fmt: skip


def row_checks(
    root: Path, release: str, level: object, rung: str, system: str
) -> dict[str, CheckState]:
    """The six checks of one row, in table order (CH-7)."""
    digest = level_digest(root, level)
    sessions = row_sessions(root, release, level, rung, system, digest)
    return checks_from(root, release, level, rung, system, sessions, digest)


def checks_from(
    root: Path,
    release: str,
    level: object,
    rung: str,
    system: str,
    sessions: RowSessions,
    digest: str,
) -> dict[str, CheckState]:
    """`row_checks` over sessions already read."""
    output = int_of(field_of(level, "request"), "output_tokens", 0)
    trials, present, same = control_trials(sessions, output)

    def control(cid: str, refused: frozenset[str], position: str | None = None) -> CheckState:
        return control_state(trials, present, cid, refused, position)

    model = _combine([control("P1", PROVER_REFUSED), control("C3", VERIFIER_REFUSED)])
    model = _reproduced(model, root, release, system, "model")
    if same is not None:  # CH-2: W' committed as W, so no trial of MODEL tested anything
        model = _undecided(NOT_RUN, model.evidence, same)
    coverage = coverage_state(sessions, output)
    positions = _combine([control("C1", VERIFIER_REFUSED, p) for p in C1_POSITIONS])
    positions = _reproduced(positions, root, release, system, "reply")
    reply = coverage if coverage.state == FAILED else _combine([coverage, positions])
    out = {
        "run": check_run(sessions, level, _forbidden_flags(root, system)),
        "model": model,
        "prompt": _reproduced(control("C2", VERIFIER_REFUSED), root, release, system, "prompt"),
        "reply": reply,
        "no_weight_file": no_weight_file_state(sessions),
        "fidelity": fidelity_state(root, release, rung, system, digest),
    }
    if not sessions.counted:  # CH-1: the checks run against counted sessions' proofs
        for name in ("model", "prompt", "reply", "no_weight_file"):
            if out[name].state != FAILED:
                out[name] = _undecided(NOT_RUN, out[name].evidence, "no counted session")
    for name in CHECKS:
        limit = _limit(level, system, name)
        if limit is not None and out[name].state != FAILED:
            out[name] = limit
    return out


def passed(checks: Mapping[str, CheckState]) -> bool:
    """A row passed when all six checks held."""
    return all(checks[name].state == HELD for name in CHECKS)
