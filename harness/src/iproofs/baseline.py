"""The Level 1 serving baseline at full load (RFC-0018 CO-4), from a stored `ref-serve` run.

A ladder run (`manifest.json` `workload.load_point: ladder`) serves the rung's ladder prompts
(`baseline.prompts`) at each concurrency c of the level's `baseline.ladder`:
`baseline.warmup_batches` warm-up batches, then `baseline.timed_batches` timed batches of c
distinct prompts, one after another, each output released with an id that names its
concurrency, batch and whether it is a warm-up (`systems/ref-serve/entrypoint`, `proof_id`).

For each c, the timed span runs from the last warm-up release to the last timed release, and
the rate is r_c = timed replies / (span x GPUs), the GPUs being those the run bound
(`manifest.json` `machine.gpu.bound_indices`, RFC-0018 SE-2). Full load is the lowest c with
r_c >= (1 - `baseline.plateau`) x max r; the baseline's GPU-seconds per reply is 1 / r there.
A rung whose outputs are not the plan's (a failed request, a missing batch) is recorded failed
and skipped. Pure: it reads the two files and returns values (INV-ARCH-5).
"""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from iproofs import __version__
from iproofs.derive import Input, QuantityTree, derived, measured, nonzero
from iproofs.quantity import NullReason, Scope, Unit

RATE_FORMULA = "D-L1-BASELINE-RATE"  # timed replies / (span x GPUs)
FORMULA = "D-L1-BASELINE"  # span x GPUs / timed replies, at full load
_ID = re.compile(r"^c([1-9][0-9]*)-([wb])([0-9]+)-r([0-9]+)$")


class BaselineRule(Protocol):
    @property
    def ladder(self) -> Sequence[int]: ...
    @property
    def plateau(self) -> float: ...
    @property
    def warmup_batches(self) -> int: ...
    @property
    def timed_batches(self) -> int: ...
    @property
    def prompts(self) -> int: ...


class RungLike(Protocol):
    @property
    def id(self) -> str: ...
    @property
    def workloads(self) -> Mapping[str, str]: ...


class LevelLike(Protocol):
    """What full_load reads of `iproofs.level.Level` (levels/L1.yaml)."""

    @property
    def baseline(self) -> BaselineRule: ...
    @property
    def rungs(self) -> Sequence[RungLike]: ...


@dataclass(frozen=True)
class FullLoad:
    run_id: str
    rung: str
    concurrency: int  # the full-load rung of the ladder
    gpus: int
    gpu_seconds_per_reply: QuantityTree  # gpu_s/request, scope prove.steady
    ladder: tuple[tuple[int, QuantityTree], ...]  # (c, replies per GPU-second), ladder order
    failed: tuple[tuple[int, str], ...]  # (c, cause) of each failed ladder rung


@dataclass(frozen=True)
class _Output:
    warmup: bool
    batch: int
    position: int
    request_index: int | None
    released_ns: int


def _record_path(run_dir: Path, name: str) -> str:
    """The record's path from the repository root (`results/...`) when the run lies under it."""
    parts = run_dir.parts
    if "results" in parts:
        at = len(parts) - 1 - parts[::-1].index("results")
        return "/".join((*parts[at:], name))
    return (run_dir / name).as_posix()


def _rung_for(level: LevelLike, workload: str) -> RungLike | None:
    return next((r for r in level.rungs if workload in r.workloads.values()), None)


def _plan_problem(outputs: Sequence[_Output], c: int, rule: BaselineRule) -> str | None:
    """None when the rung released exactly its plan (`ladder_plan` in the adapter): batch s of
    the rung (warm-ups first) serving ladder prompts (s x c + j) mod `prompts`, every timed
    release after the last warm-up release; else the cause."""
    warmup, timed, count = rule.warmup_batches, rule.timed_batches, rule.prompts
    warm = [o for o in outputs if o.warmup]
    done = [o for o in outputs if not o.warmup]
    if len(warm) != warmup * c:
        return f"{len(warm)} of {warmup * c} warm-up replies released"
    if len(done) != timed * c:
        return f"{len(done)} of {timed * c} timed replies released"
    for kind, got, batches, first in (("warm-up", warm, warmup, 0), ("timed", done, timed, warmup)):
        want = {(k, j, ((first + k) * c + j) % count) for k in range(batches) for j in range(c)}
        if {(o.batch, o.position, o.request_index) for o in got} != want:
            return f"{kind} replies differ from the plan of {batches} batch(es) of {c}"
    if min(o.released_ns for o in done) <= max(o.released_ns for o in warm):
        return "a timed reply was released before the warm-up ended"
    return None


@dataclass(frozen=True)
class _Records:
    run_id: str
    rung: RungLike
    gpus: int
    outputs: dict[int, list[_Output]]  # by concurrency


def _read(run_dir: Path, level: LevelLike) -> _Records | str:  # noqa: PLR0911 (one cause each)
    """The ladder run's outputs by concurrency, its rung and bound GPUs, or why there are none."""
    try:
        run = json.loads((run_dir / "run.json").read_text())
        manifest = json.loads((run_dir / "manifest.json").read_text())
    except (OSError, ValueError) as e:
        return f"records unreadable: {e}"
    run_id = str(run.get("run_id"))
    if run.get("status") != "completed":
        failure = run.get("failure") or {}
        return f"run {run_id} failed: {failure.get('kind')}: {failure.get('message')}"
    workload = manifest.get("workload") or {}
    if workload.get("load_point") != "ladder":
        return f"run {run_id} is not a ladder run (load point {workload.get('load_point')!r})"
    rung = _rung_for(level, str(workload.get("id")))
    if rung is None:
        return f"workload {workload.get('id')!r} is on no rung of the level"
    bound = ((manifest.get("machine") or {}).get("gpu") or {}).get("bound_indices") or []
    if not bound:
        return f"run {run_id} records no bound GPU"
    by_c: dict[int, list[_Output]] = {}
    for proof in run.get("proofs") or []:
        m = _ID.match(str(proof.get("proof_id")))
        if m is None:
            return f"output {proof.get('proof_id')!r} is not a ladder output"
        out = _Output(m.group(2) == "w", int(m.group(3)), int(m.group(4)),
                      proof.get("request_index"), int(proof["release_mono_ns"]))  # fmt: skip
        by_c.setdefault(int(m.group(1)), []).append(out)
    return _Records(run_id, rung, len(bound), by_c)


def full_load(run_dir: Path, level: LevelLike) -> FullLoad | str:
    """RFC-0018 CO-4 from the run's stored records, or the cause there is no full load."""
    records = _read(run_dir, level)
    if isinstance(records, str):
        return records
    run_json = _record_path(run_dir, "run.json")
    gpus_ref = f"{_record_path(run_dir, 'manifest.json')}#/machine/gpu/bound_indices"
    gpus = measured(records.gpus, Unit.COUNT, None, gpus_ref, None)
    proofs_ref = f"{run_json}#/proofs"
    ladder: list[tuple[int, QuantityTree]] = []
    parts: dict[int, list[Input]] = {}
    failed: list[tuple[int, str]] = []
    for c in level.baseline.ladder:
        outputs = records.outputs.get(c, [])
        cause = _plan_problem(outputs, c, level.baseline) if outputs else "no reply released"
        if cause is None:
            done = [o for o in outputs if not o.warmup]
            start = max(o.released_ns for o in outputs if o.warmup)
            span = (max(o.released_ns for o in done) - start) / 1e9
            seconds = measured(span, Unit.S, Scope.PROVE_STEADY, proofs_ref, None)
            replies = measured(len(done), Unit.COUNT, None, proofs_ref, None)
        else:
            failed.append((c, cause))
            null = NullReason.STEP_FAILED
            seconds = measured(None, Unit.S, Scope.PROVE_STEADY, proofs_ref, null)
            replies = measured(None, Unit.COUNT, None, proofs_ref, null)
        inputs: list[Input] = [(proofs_ref, replies), (proofs_ref, seconds), (gpus_ref, gpus)]
        rate = derived(RATE_FORMULA, __version__, Unit.REQUEST_PER_GPU_S, Scope.PROVE_STEADY,
                       inputs, lambda x: x[0] / nonzero(x[1] * x[2]))  # fmt: skip
        ladder.append((c, rate))
        parts[c] = inputs
    rates = {c: v for c, q in ladder if isinstance(v := q["value"], int | float)}
    if not rates:
        return f"every ladder rung failed: {failed}"
    top = max(rates.values())
    full = min(c for c, r in rates.items() if r >= (1 - level.baseline.plateau) * top)
    if len(rates) > 1 and full == max(rates):  # CO-4: the rate still rose at the top rung
        return (f"not saturated: the rate still rises at the ladder's top rung (c = {full}), "
                f"more than {level.baseline.plateau:.0%} above the rung below")  # fmt: skip
    replies_q, seconds_q, gpus_q = parts[full]
    per_reply = derived(FORMULA, __version__, Unit.GPU_S_PER_REQUEST, Scope.PROVE_STEADY,
                        [seconds_q, gpus_q, replies_q],
                        lambda x: x[0] * x[1] / nonzero(x[2]))  # fmt: skip
    return FullLoad(run_id=records.run_id, rung=records.rung.id, concurrency=full,
                    gpus=records.gpus, gpu_seconds_per_reply=per_reply, ladder=tuple(ladder),
                    failed=tuple(failed))  # fmt: skip
