"""Teacher-forced top-token agreement and KL of a rung (RFC-0018 FI-10 to FI-15), pure and CPU
only. Printed beside FI-3's score; it gates nothing.

An engine (a control, the reference itself, or a system's own code through AD-7 `score`) is
fed each prompt followed by the stored reference reply. At each of the reply's positions it
gives its own top token and, where it can, its `top_k` most probable tokens with their
log-probabilities.

- FI-10: a prompt's score is the number of reply positions whose top token equals the
  reference token there, 0 to the reply length (512). Row t of the pass is computed after
  prompt + reply[:t] and predicts reply[t].
- FI-11: FI-4's sign-flip test on these integer scores, each row against each control, both
  ways. Seeds: `pair_seed` over ids prefixed `teacher_forced/`, so no draw is shared with
  FI-3's tests. A prompt on which a system's own code gave no top tokens scores 0 and is
  counted in `failed` with its cause.
- FI-12: KL at one position is the KL divergence, in nats, between the reference's and the
  engine's distributions over this partition of the vocabulary: each token that both lists
  hold, and one outcome for all the rest. It is at most the KL over the whole vocabulary.
  With p, q the probabilities on the common tokens S, m_p = 1 - sum_S p and m_q = 1 - sum_S q:
  KL = sum_S p (ln p - ln q) + m_p (ln m_p - ln m_q). A rest mass below `REST_FLOOR` is not
  resolved by float32 log-probabilities: the last term is left out when m_p is below it, and
  m_q is taken as the floor when it is below. A prompt's KL is the mean over its positions
  that hold a list on both sides (an engine may return none at a position, FI-12), a figure's
  the mean over the prompts that have one.
- FI-15: `build` writes `teacher-forced.json` (schema `teacher-forced/1`): the reference's own
  pass, each control, each row with its tests, and the KL figures.
"""

import hashlib
import json
import statistics
import struct
from array import array
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import exp, fsum, log
from pathlib import Path
from typing import Any, Literal

from iproofs.fidelity import PairTest, SignFlipRule, pair_seed, sign_flip_p
from iproofs.quantity import Unit

SCHEMA = "teacher-forced/1"
RUN_SCHEMA = "teacher-forced-run/1"
SCORE = "teacher_forced_agreement"
UNIT = "agreeing positions"
KL_UNIT = Unit.NAT_PER_TOKEN.value
TOP_K = 256  # FI-12: the most probable tokens an engine lists at a position
REST_FLOOR = 1e-6
LABEL = "computed by the system's own code on the reference reply, not by the proved computation"
ALIGNMENT = (
    "row t is computed after the prompt and the first t tokens of the reference reply and "
    "predicts reply token t, t from 0"
)
SEED_PREFIX = "teacher_forced/"
SEED_RULE_TEXT = (
    "FI-4's seed rule over the ids prefixed teacher_forced/: first 8 bytes, big-endian, of "
    "sha256(randomness || 0x00 || utf8(teacher_forced/a) || 0x00 || utf8(teacher_forced/b))"
)
KL_RULE = (
    "per position, the KL divergence in nats between the reference's and the engine's "
    "distributions over: each token both lists of the top_k most probable tokens hold, and one "
    "outcome for every other token; at most the KL over the whole vocabulary. A rest mass "
    "below rest_floor is left out on the reference's side and taken as rest_floor on the "
    "engine's. A prompt's value is the mean over its positions"
)
NO_LIST = -1  # the id a position without a list holds
NO_MASS = float("-inf")
MAGIC = b"TFK1"  # a prompt's lists: MAGIC, positions and k (uint32), ids (int32), logprobs
# (float32), each positions x k, row by row, little-endian

Status = Literal["ok", "failed"]


def agreement(top: Sequence[int], reference: Sequence[int]) -> int:
    """FI-10: the number of positions whose top token is the reference token."""
    if len(top) != len(reference):
        raise ValueError(f"{len(top)} top tokens for a reply of {len(reference)}")
    return sum(1 for a, b in zip(top, reference, strict=True) if a == b)


def fidelity_percent(mean: float | None, positions: int) -> float | None:
    """SI-9 (amended 2026-11-14): FI-10's mean as a percentage of the reply's positions, the
    figure the site names Fidelity; None where there is no mean."""
    if mean is None:
        return None
    if positions < 1:
        raise ValueError(f"{positions} positions")
    return mean / positions * 100


@dataclass(frozen=True, slots=True)
class TopK:
    """One prompt's lists: at each position the `k` most probable tokens, most probable
    first, and their log-probabilities in nats."""

    positions: int
    k: int
    ids: array[int]
    logprobs: array[float]

    def row(self, t: int) -> tuple[array[int], array[float]]:
        return self.ids[t * self.k : (t + 1) * self.k], self.logprobs[t * self.k : (t + 1) * self.k]


def write_topk(path: Path, rows: Sequence[tuple[Sequence[int], Sequence[float]]]) -> None:
    """The file an adapter writes for one prompt (the adapters carry their own copy)."""
    k = len(rows[0][0])
    if any(len(i) != k or len(lp) != k for i, lp in rows):
        raise ValueError("every position lists the same number of tokens")
    ids = array("i", [t for i, _ in rows for t in i])
    lps = array("f", [x for _, lp in rows for x in lp])
    path.write_bytes(MAGIC + struct.pack("<II", len(rows), k) + ids.tobytes() + lps.tobytes())


def read_topk(path: Path) -> TopK:
    data = path.read_bytes()
    if data[:4] != MAGIC or len(data) < 12:
        raise ValueError(f"{path.name} is not a top-k file")
    positions, k = struct.unpack("<II", data[4:12])
    if len(data) != 12 + 8 * positions * k or positions < 1 or k < 1:
        raise ValueError(f"{path.name}: {len(data)} B for {positions} positions of {k} tokens")
    ids, lps = array("i"), array("f")
    ids.frombytes(data[12 : 12 + 4 * positions * k])
    lps.frombytes(data[12 + 4 * positions * k :])
    return TopK(positions, k, ids, lps)


def position_kl(
    ref_ids: Sequence[int],
    ref_lp: Sequence[float],
    ids: Sequence[int],
    lp: Sequence[float],
) -> tuple[float, float]:
    """FI-12 at one position: the KL in nats and the reference's rest mass m_p."""
    theirs = dict(zip(ids, lp, strict=True))
    terms: list[float] = []
    ps: list[float] = []
    qs: list[float] = []
    for token, a in zip(ref_ids, ref_lp, strict=True):
        b = theirs.get(token)
        if b is None or a == NO_MASS:  # a listed token of probability 0 adds nothing
            continue
        p = exp(a)
        ps.append(p)
        qs.append(exp(b))
        terms.append(p * (a - b))
    m_p = max(0.0, 1.0 - fsum(ps))
    m_q = max(REST_FLOOR, 1.0 - fsum(qs))
    if m_p >= REST_FLOOR:
        terms.append(m_p * (log(m_p) - log(m_q)))
    return fsum(terms), m_p


def prompt_kl(reference: TopK, engine: TopK) -> tuple[float, float, int] | None:
    """A prompt's mean KL over the positions that hold a list on both sides, its mean reference
    rest mass there, and the number of those positions; None when there is none. A position
    without a list holds the id -1 (`NO_LIST`)."""
    if reference.positions != engine.positions:
        raise ValueError(f"{engine.positions} positions against the reference's "
                         f"{reference.positions}")  # fmt: skip
    kls: list[float] = []
    rests: list[float] = []
    for t in range(reference.positions):
        ref_ids, ref_lp = reference.row(t)
        ids, lp = engine.row(t)
        if ref_ids[0] == NO_LIST or ids[0] == NO_LIST:
            continue
        kl, rest = position_kl(ref_ids, ref_lp, ids, lp)
        kls.append(kl)
        rests.append(rest)
    if not kls:
        return None
    return fsum(kls) / len(kls), fsum(rests) / len(rests), len(kls)


@dataclass(frozen=True, slots=True)
class Pass:
    """One engine's pass over the rung's prompts: per prompt its top tokens, or the cause it
    has none; None for the whole pass with `cause` when it did not run."""

    id: str
    tops: tuple[tuple[int, ...] | None, ...] | None
    causes: Mapping[int, str]  # prompt index to the cause, for a prompt without top tokens
    cause: str | None = None  # why the whole pass has no top tokens


@dataclass(frozen=True, slots=True)
class Scored:
    """FI-10 for one pass. A failed prompt scores 0 (FI-11)."""

    id: str
    status: Status
    cause: str | None
    scores: tuple[int, ...] = ()
    failed: tuple[tuple[int, str], ...] = ()

    @property
    def mean(self) -> float | None:
        return sum(self.scores) / len(self.scores) if self.scores else None

    @property
    def median(self) -> float | None:
        return float(statistics.median(self.scores)) if self.scores else None

    @property
    def mean_not_failed(self) -> float | None:
        """The mean over the prompts that have top tokens."""
        bad = {i for i, _ in self.failed}
        kept = [s for i, s in enumerate(self.scores) if i not in bad]
        return sum(kept) / len(kept) if kept else None

    def record(self) -> dict[str, object]:
        return {
            "status": self.status,
            "cause": self.cause,
            "scores": list(self.scores),
            "failed": [{"prompt": i, "cause": c} for i, c in self.failed],
            "mean": self.mean,
            "median": self.median,
            "mean_not_failed": self.mean_not_failed,
        }


def score_pass(run: Pass, reference: Sequence[Sequence[int]], *, system: bool) -> Scored:
    """FI-10 over the prompts. A control or the reference with a prompt that has no top tokens
    failed as a whole (an engine we drive either ran or did not); a system's failed prompts
    score 0 and are listed (FI-11)."""
    if run.tops is None:
        return Scored(run.id, "failed", run.cause or "not run")
    if len(run.tops) != len(reference):
        return Scored(run.id, "failed", f"{len(run.tops)} prompts for {len(reference)}")
    failed = tuple((i, run.causes.get(i, "no top tokens")) for i, t in enumerate(run.tops)
                   if t is None)  # fmt: skip
    if failed and not system:
        i, cause = failed[0]
        return Scored(run.id, "failed", f"prompt {i}: {cause}")
    scores = tuple(0 if t is None else agreement(t, ref)
                   for t, ref in zip(run.tops, reference, strict=True))  # fmt: skip
    return Scored(run.id, "ok", None, scores, failed)


def above(a: Scored, b: Scored, rule: SignFlipRule) -> PairTest:
    """FI-11: FI-4's test "a scores above b" on the teacher-forced scores."""
    diffs = [x - y for x, y in zip(a.scores, b.scores, strict=True)]
    exact = len(diffs) <= rule.exact_up_to
    seed = None if exact else pair_seed(rule.randomness_hex, SEED_PREFIX + a.id, SEED_PREFIX + b.id)
    p = sign_flip_p(diffs, exact_up_to=rule.exact_up_to, resamples=rule.resamples, seed=seed or 0)
    return PairTest(a.id, b.id, len(diffs), p, "exact" if exact else "monte-carlo", seed)


def row_tests(row: Scored, controls: Sequence[Scored], rule: SignFlipRule) -> list[PairTest]:
    """The row against each control that ran, above and below, in level-file order."""
    out: list[PairTest] = []
    for c in controls:
        if c.status == "ok" and row.status == "ok" and len(c.scores) == len(row.scores):
            out += [above(row, c, rule), above(c, row, rule)]
    return out


def kl_figure(
    per_prompt: Sequence[float | None],
    rests: Sequence[float | None],
    positions: Sequence[int],
    source_ref: str,
    note: str,
) -> dict[str, object] | None:
    """FI-12: the mean over the prompts that have a value, as a labelled quantity with its n
    (prompts), the positions it covers and the mean reference rest mass; None when no prompt
    has one."""
    values = [v for v in per_prompt if v is not None]
    if not values:
        return None
    kept = [r for r in rests if r is not None]
    return {
        "value": fsum(values) / len(values),
        "unit": KL_UNIT,
        "scope": None,
        "grade": "measured",
        "tier": "reported",
        "source": {"kind": "adapter", "ref": source_ref},
        "null_reason": None,
        "note": note,
        "n": len(values),
        "positions": sum(positions),
        "reference_rest_mass": fsum(kept) / len(kept) if kept else None,
    }


# ---------------------------------------------------------------- the stored KL values (FI-12)


def raw_digest(directory: Path) -> str:
    """The digest that names an engine's lists: sha256 over `<file name> TAB <sha256>` lines of
    its `.topk` files, sorted by name. The lists stay outside the repository."""
    lines = "".join(
        f"{p.name}\t{hashlib.sha256(p.read_bytes()).hexdigest()}\n"
        for p in sorted(directory.glob("*.topk"), key=lambda p: p.name)
    )
    return "sha256:" + hashlib.sha256(lines.encode()).hexdigest()


def measure_kl(reference: Path, engine: Path, n: int) -> dict[str, object]:
    """FI-12 for one engine from the lists of both: per prompt (0 to n - 1) its mean KL, its
    mean reference rest mass and the positions counted, null where either side has no file."""
    kls: list[float | None] = []
    rests: list[float | None] = []
    positions: list[int] = []
    for i in range(n):
        a, b = reference / f"{i}.topk", engine / f"{i}.topk"
        found = prompt_kl(read_topk(a), read_topk(b)) if a.is_file() and b.is_file() else None
        kls.append(found[0] if found else None)
        rests.append(found[1] if found else None)
        positions.append(found[2] if found else 0)
    return {"per_prompt": kls, "reference_rest_mass": rests, "positions": positions,
            "lists": raw_digest(engine)}  # fmt: skip


# ---------------------------------------------------------------- teacher-forced.json (FI-15)

ENGINE_NOTE = "computed by the engine on the control's file, on the reference reply"
NO_KL = "not measured: no lists of the most probable tokens are stored for it"
NO_REFERENCE_KL = "not measured: the reference's pass stored no lists of its most probable tokens"


@dataclass(frozen=True, slots=True)
class Entry:
    """One line of the document: a control, a row or the reference's own pass."""

    spec: Mapping[str, object]  # id, and for a control kind, recipe and type
    scored: Scored
    run: str | None  # the run record that holds its pass
    kl: Mapping[str, object] | None  # its stored KL values (`measure_kl`)
    runs: tuple[str, ...] = ()  # every run record of the pass, where shards made it


def _kl_block(entry: Entry, has_reference: bool, ref: str, note: str) -> dict[str, object]:
    if entry.kl is None:
        return {"kl": None, "kl_note": NO_KL if has_reference else NO_REFERENCE_KL}
    values: Any = entry.kl
    figure = kl_figure(values["per_prompt"], values["reference_rest_mass"], values["positions"],
                       f"{ref}#/engines/{entry.scored.id}", note)  # fmt: skip
    return {"kl": figure, "kl_note": note if figure else NO_KL}


def build(
    header: Mapping[str, object],
    rule: SignFlipRule,
    reference_pass: Entry | None,
    controls: Sequence[Entry],
    rows: Sequence[Entry],
    kl_ref: str,
    has_reference_lists: bool,
    computed_by: Mapping[str, str],
) -> dict[str, object]:
    """`teacher-forced.json`. `header` holds level, rung, n, prompts_digest, reference and
    positions; `computed_by` says, per row, whose computation its figures are (FI-13)."""
    ok = [c.scored for c in controls]
    return {
        "schema": SCHEMA,
        **header,
        "gating": False,
        "measure": {
            "score": SCORE,
            "unit": UNIT,
            "alignment": ALIGNMENT,
            "label": LABEL,
            "test": "paired-sign-flip",
            "alpha": rule.alpha,
            "exact_up_to": rule.exact_up_to,
            "resamples": rule.resamples,
            "seed_rule": SEED_RULE_TEXT,
            "failed_prompt": "scores 0 and is listed with its cause",
        },
        "kl": {
            "unit": KL_UNIT,
            "top_k": TOP_K,
            "rest_floor": REST_FLOOR,
            "rule": KL_RULE,
            "values": kl_ref if has_reference_lists else None,
        },
        "reference_pass": None
        if reference_pass is None
        else {
            **reference_pass.scored.record(),
            "run": reference_pass.run,
            "runs": list(reference_pass.runs),
        },
        "controls": [
            {
                **{k: c.spec.get(k) for k in ("id", "kind", "recipe", "type")},
                **c.scored.record(),
                "run": c.run,
                "runs": list(c.runs),
                **_kl_block(c, has_reference_lists, kl_ref, ENGINE_NOTE),
            }
            for c in controls
        ],
        "rows": {
            r.scored.id: {
                **r.scored.record(),
                "run": r.run,
                "runs": list(r.runs),
                "computed_by": computed_by.get(r.scored.id, ""),
                "label": LABEL,
                **_kl_block(r, has_reference_lists, kl_ref, LABEL),
                "tests": [t.record() for t in row_tests(r.scored, ok, rule)],
            }
            for r in sorted(rows, key=lambda r: r.scored.id)
        },
    }


# ---------------------------------------------------------------- the board's block (SI-9)


def board_block(doc: Mapping[str, Any], path: str, tops: Mapping[str, Path],
                reference: Sequence[Sequence[int]],
                kl_values: Mapping[str, Any] | None = None) -> dict[str, object]:  # fmt: skip
    """What the board prints of `teacher-forced.json`, after recomputing every score it holds
    from the stored top tokens (`tops`: id to its `top/<id>.jsonl`) and the reference replies,
    every mean and median from the scores, and every KL figure from the stored per-prompt
    values (`kl_values`, kl.json); a difference stops the board (AGENTS.md rule 3)."""

    def checked(ident: str, entry: Mapping[str, Any], system: bool) -> None:
        scores = [int(x) for x in entry["scores"]]
        if entry["status"] == "ok":
            lines = [json.loads(x) for x in tops[ident].read_text().splitlines() if x.strip()]
            again = [0 if isinstance(t, dict) else agreement(t, r)
                     for t, r in zip(lines, reference, strict=True)]  # fmt: skip
            if again != scores or (not system and any(isinstance(t, dict) for t in lines)):
                raise ValueError(f"{path}: the scores of {ident} are not the ones its stored "
                                 "top tokens give")  # fmt: skip
        mean = sum(scores) / len(scores) if scores else None
        median = float(statistics.median(scores)) if scores else None
        if (entry["mean"], entry["median"]) != (mean, median):
            raise ValueError(f"{path}: the mean or median of {ident} is not its scores'")
        kl = entry.get("kl")
        if kl is not None:
            stored = ((kl_values or {}).get("engines") or {}).get(ident) or {}
            values = [v for v in stored.get("per_prompt") or [] if v is not None]
            if not values or kl["value"] != fsum(values) / len(values) or kl["n"] != len(values):
                raise ValueError(f"{path}: the KL figure of {ident} is not the mean of its "
                                 "stored per-prompt values")  # fmt: skip

    def figure(entry: Mapping[str, Any]) -> dict[str, object]:
        kl = entry.get("kl")
        return {"status": entry["status"], "cause": entry["cause"], "n": len(entry["scores"]),
                "mean": entry["mean"], "median": entry["median"],
                "percent": fidelity_percent(entry["mean"], int(doc["positions"])),
                "mean_not_failed": entry["mean_not_failed"],
                "failed": [dict(f) for f in entry["failed"]], "run": entry["run"],
                "kl": None if kl is None else {k: kl[k] for k in (
                    "value", "unit", "n", "positions", "reference_rest_mass", "note")}
                | {"source": kl["source"]["ref"]},
                "kl_note": entry.get("kl_note")}  # fmt: skip

    controls = []
    for c in doc["controls"]:
        checked(str(c["id"]), c, False)
        controls.append({"id": c["id"], "kind": c["kind"], **figure(c)})
    rows = {}
    for system, r in doc["rows"].items():
        checked(system, r, True)
        rows[system] = {**figure(r), "computed_by": r["computed_by"], "label": r["label"],
                        "tests": [dict(t) for t in r["tests"]]}  # fmt: skip
    own = doc.get("reference_pass")
    if own is not None:
        checked("reference", {**own, "kl": None}, False)
    return {
        "path": path,
        "n": doc["n"],
        "positions": doc["positions"],
        "unit": doc["measure"]["unit"],
        "label": doc["measure"]["label"],
        "gating": False,
        "alpha": doc["measure"]["alpha"],
        "top_k": doc["kl"]["top_k"],
        "reference_pass": None if own is None else {
            k: own[k] for k in ("status", "cause", "mean", "median", "run")},
        "controls": controls,
        "rows": rows,
    }  # fmt: skip
