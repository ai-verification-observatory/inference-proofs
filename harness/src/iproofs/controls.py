"""Negative controls: mutations, honest twins, classification (RFC-0008).

INV-CTRL-1: every mutated input is produced here, by the harness; adapters never mutate.
INV-CTRL-3: every mutation is a deterministic function of `control_seed`, the control id and
the honest inputs.
"""

import hashlib
import json
import math
import os
import random
import re
import shutil
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import SystemControl, Workload
from iproofs.serialize import load_yaml

CONTROL_SEED_RE = re.compile(r"^0x[0-9a-f]{16}$")


def new_control_seed() -> str:
    """A fresh 64-bit seed from the OS, written as `0x` plus 16 lowercase hex digits."""
    return f"0x{int.from_bytes(os.urandom(8), 'big'):016x}"


SEED_TEXT_RE = re.compile(r"^(0[xX][0-9a-fA-F]{1,16}|[0-9]{1,20})$")


def parse_control_seed(text: str) -> str:
    """`--seed`: a 64-bit value in hex (`0x` and 1 to 16 digits) or in decimal, returned in the
    recorded form, `0x` plus 16 lowercase hex digits (RFC-0008 §Seeds)."""
    if not SEED_TEXT_RE.fullmatch(text):
        raise IProofsError(
            ErrorKind.CONFIG, f"--seed {text!r}: give a 64-bit value in hex (0x...) or decimal"
        )
    value = int(text, 16) if text[:2] in ("0x", "0X") else int(text)
    if value >= 1 << 64:
        raise IProofsError(ErrorKind.CONFIG, f"--seed {text!r} is above 2**64 - 1")
    return f"0x{value:016x}"


def rng(control_seed: str, control_id: str, k: int) -> random.Random:
    """Per-control generator; callers use `.random()` only (RFC-0008 §Seeds)."""
    if not CONTROL_SEED_RE.fullmatch(control_seed):
        raise ValueError(f"bad control seed {control_seed!r}")
    return random.Random(f"{control_seed}:{control_id}:{k}")


def seeded_index(control_seed: str, control_id: str, k: int, m: int) -> int:
    """An index in [0, m): floor(r * m) with r from the seeded generator."""
    if m < 1:
        raise ValueError("empty range")
    return math.floor(rng(control_seed, control_id, k).random() * m)


@dataclass(frozen=True, slots=True)
class HonestProof:
    """One honest proof of the run with the verdict its own verify step returned."""

    proof_id: str
    request: tuple[int, ...]
    claimed_output: tuple[int, ...]
    verdict: str
    release_mono_ns: int
    batch: int


@dataclass(frozen=True, slots=True)
class Selection:
    target: HonestProof | None
    other: HonestProof | None


def select(proofs: Sequence[HonestProof]) -> Selection:
    """target: first accepted proof in release order; other: the next accepted one with a
    different request (RFC-0008 §Proof selection). No accepted proof: every control is void."""
    accepted = [p for p in sorted(proofs, key=lambda p: p.release_mono_ns) if p.verdict == "accept"]
    if not accepted:
        return Selection(None, None)
    target = accepted[0]
    other = next((p for p in accepted[1:] if p.request != target.request), None)
    return Selection(target, other)


# ---------------------------------------------------------------- verifier-side mutations

SHARED_VERIFIER_CONTROLS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8")
SHARED_PROVER_CONTROLS = ("P1", "P2")
C6_TRIALS = 5


@dataclass(frozen=True, slots=True)
class VerifyCall:
    """One verify call of a control trial. The commitment always comes from a harness
    commit record (INV-CTRL-6); `proof_dir` is a host directory the harness wrote."""

    control_id: str
    trial: int
    commitment_id: str
    request: tuple[int, ...]
    claimed_output: tuple[int, ...]
    proof_dir: Path
    parts: tuple[str, ...]
    mutation: Mapping[str, object]


class NotApplicable(Exception):
    """A control's precondition fails; the message is the recorded reason."""


def _parts(proof_dir: Path) -> list[Path]:
    return sorted(proof_dir.iterdir(), key=lambda p: p.name)


def _copy_proof(src: Path, dst: Path, skip: str | None = None) -> Path:
    dst.mkdir(parents=True)
    for part in _parts(src):
        if part.name != skip:
            shutil.copyfile(part, dst / part.name)
    return dst


def _changed(original: object, mutated: object, control_id: str) -> None:
    if original == mutated:
        raise IProofsError(
            ErrorKind.INTERNAL, f"{control_id}: mutated input is identical to the original"
        )


def c1(target: HonestProof, commit: str, proof_dir: Path, vocab_size: int) -> VerifyCall:
    """Change the claimed output token: the last token becomes (t + 1) mod vocab_size."""
    out = list(target.claimed_output)
    out[-1] = (out[-1] + 1) % vocab_size
    _changed(list(target.claimed_output), out, "C1")
    return VerifyCall(
        "C1",
        0,
        commit,
        target.request,
        tuple(out),
        proof_dir,
        _names(proof_dir),
        {"index": len(out) - 1, "token": out[-1]},
    )


def c2(target: HonestProof, commit: str, proof_dir: Path, vocab_size: int, seed: str) -> VerifyCall:
    """Change one prompt token at a seeded position."""
    req = list(target.request)
    p = seeded_index(seed, "C2", 0, len(req))
    req[p] = (req[p] + 1) % vocab_size
    _changed(list(target.request), req, "C2")
    return VerifyCall(
        "C2",
        0,
        commit,
        tuple(req),
        target.claimed_output,
        proof_dir,
        _names(proof_dir),
        {"position": p, "token": req[p]},
    )


def c3(target: HonestProof, commit: str, perturbed: str | None, proof_dir: Path) -> VerifyCall:
    """Verify against the commitment of perturbed weights, from its harness commit record."""
    if perturbed is None:
        raise NotApplicable("no perturbed commitment for this workload")
    _changed(commit, perturbed, "C3")
    return VerifyCall(
        "C3",
        0,
        perturbed,
        target.request,
        target.claimed_output,
        proof_dir,
        _names(proof_dir),
        {"commitment": "perturbed"},
    )


def c4(target: HonestProof, other: HonestProof | None, commit: str, proof_dir: Path) -> VerifyCall:
    """Replay the target's proof for a different request."""
    if other is None or other.request == target.request:
        raise NotApplicable("no second accepted proof with a different request")
    return VerifyCall(
        "C4",
        0,
        commit,
        other.request,
        other.claimed_output,
        proof_dir,
        _names(proof_dir),
        {"request_of": other.proof_id},
    )


def c5(target: HonestProof, commit: str, src: Path, dst: Path) -> VerifyCall:
    """Truncate the largest part to floor(size / 2) bytes; ties broken by name."""
    largest = sorted(_parts(src), key=lambda p: (-p.stat().st_size, p.name))[0]
    _copy_proof(src, dst)
    data = largest.read_bytes()
    cut = data[: len(data) // 2]
    _changed(data, cut, "C5")
    (dst / largest.name).write_bytes(cut)
    return VerifyCall(
        "C5",
        0,
        commit,
        target.request,
        target.claimed_output,
        dst,
        _names(dst),
        {"part": largest.name, "bytes": len(cut)},
    )


def c6(target: HonestProof, commit: str, src: Path, dst: Path, seed: str, s: int) -> VerifyCall:
    """Trial s of five: flip one bit at a seeded offset in a seeded part."""
    parts = _parts(src)
    part = parts[seeded_index(seed, "C6", 2 * s, len(parts))]
    data = bytearray(part.read_bytes())
    if not data:
        raise IProofsError(ErrorKind.INTERNAL, f"C6: part {part.name} is empty")
    off = seeded_index(seed, "C6", 2 * s + 1, len(data) * 8)
    data[off // 8] ^= 1 << (off % 8)
    _copy_proof(src, dst)
    (dst / part.name).write_bytes(bytes(data))
    return VerifyCall(
        "C6",
        s,
        commit,
        target.request,
        target.claimed_output,
        dst,
        _names(dst),
        {"part": part.name, "bit_offset": off},
    )


def c7_pair(proofs: Sequence[HonestProof], batch_size: int) -> tuple[HonestProof, HonestProof]:
    """Two accepted proofs of one batch with different requests, in release order."""
    if batch_size < 2:
        raise NotApplicable("batch size 1: no two proofs in one batch")
    accepted = [p for p in sorted(proofs, key=lambda p: p.release_mono_ns) if p.verdict == "accept"]
    for i, a in enumerate(accepted):
        for b in accepted[i + 1 :]:
            if a.batch == b.batch and a.request != b.request:
                return a, b
    raise NotApplicable("no two accepted proofs with different requests in one batch")


def c7(a: HonestProof, b: HonestProof, commit: str, b_proof_dir: Path) -> VerifyCall:
    """Swap the proofs of two requests in one batch: a's request with b's proof."""
    return VerifyCall(
        "C7",
        0,
        commit,
        a.request,
        a.claimed_output,
        b_proof_dir,
        _names(b_proof_dir),
        {"request_of": a.proof_id, "proof_of": b.proof_id},
    )


def c8(target: HonestProof, commit: str, src: Path, dst: Path, seed: str) -> VerifyCall:
    """Drop one seeded part of the proof."""
    parts = _parts(src)
    if len(parts) < 2:
        raise NotApplicable("the proof has a single part")
    dropped = parts[seeded_index(seed, "C8", 0, len(parts))]
    _copy_proof(src, dst, skip=dropped.name)
    return VerifyCall(
        "C8",
        0,
        commit,
        target.request,
        target.claimed_output,
        dst,
        _names(dst),
        {"dropped": dropped.name},
    )


def _names(proof_dir: Path) -> tuple[str, ...]:
    return tuple(p.name for p in _parts(proof_dir))


# ---------------------------------------------------------------- twins and classification

OUTCOME_OF_VERDICT = {
    "reject": "rejected",
    "accept": "accepted",
    "no_verdict": "no_verdict",
    "invalid_call": "invalid_call",
}
EXPECTED = {
    "C1": ("rejected",),
    "C2": ("rejected",),
    "C3": ("rejected",),
    "C4": ("rejected",),
    "C5": ("rejected", "invalid_call"),
    "C6": ("rejected", "invalid_call"),
    "C7": ("rejected",),
    "C8": ("rejected", "invalid_call"),
    "P1": ("prover_failed", "rejected"),
    "P2": ("prover_failed", "rejected"),
}
OUTCOMES = (
    "rejected",
    "accepted",
    "no_verdict",
    "invalid_call",
    "void",
    "not_applicable",
    "error",
    "prover_failed",
)
NEUTRAL = {"void", "not_applicable", "error"}  # neither pass nor fail


@dataclass(frozen=True, slots=True)
class VerifyResult:
    verdict: str
    raw_exit_code: int
    raw_last_line: str
    seconds: float


Verifier = Callable[[VerifyCall], VerifyResult]


def honest_call(p: HonestProof, commit: str, proof_dir: Path) -> VerifyCall:
    return VerifyCall(
        "twin", 0, commit, p.request, p.claimed_output, proof_dir, _names(proof_dir), {}
    )


def control_record(
    control_id: str,
    build: Callable[[], list[VerifyCall]],
    twins: Callable[[], list[VerifyCall]],
    verify: Verifier,
    *,
    side: str = "verifier",
    source: str = "shared",
    expected: Sequence[str] | None = None,
) -> dict[str, object]:
    """Run one control: applicability, honest twins first, then the trials (RFC-0008)."""
    expected = list(EXPECTED[control_id] if expected is None else expected)
    record: dict[str, object] = {
        "id": control_id,
        "side": side,
        "source": source,
        "expected": expected,
        "twin": None,
        "trials": [],
        "outcome": "not_applicable",
        "passed": None,
        "note": None,
    }
    try:
        calls = build()  # applicability is decided before any twin runs
    except NotApplicable as e:
        record["note"] = str(e)
        return record
    try:
        twin_results = [verify(c) for c in twins()]
    except IProofsError as e:
        return {**record, "outcome": "error", "note": f"twin: {e.kind}: {e.message}"}
    first = twin_results[0]
    record["twin"] = {"verdict": first.verdict, "raw_exit_code": first.raw_exit_code}
    if any(r.verdict != "accept" for r in twin_results):  # INV-CTRL-2
        return {**record, "outcome": "void", "note": "honest twin not accepted"}
    trials = []
    for call in calls:
        try:
            result = verify(call)
        except IProofsError as e:
            trials.append(
                {
                    "seed_index": call.trial,
                    "mutation": dict(call.mutation),
                    "verdict": None,
                    "outcome": "error",
                    "raw_exit_code": e.exit_code,
                    "raw_last_line": e.message[:4096],
                    "seconds": None,
                }
            )
            continue
        trials.append(
            {
                "seed_index": call.trial,
                "mutation": dict(call.mutation),
                "verdict": result.verdict,
                "outcome": OUTCOME_OF_VERDICT[result.verdict],
                "raw_exit_code": result.raw_exit_code,
                "raw_last_line": result.raw_last_line[:4096],
                "seconds": result.seconds,
            }
        )
    outcomes = [str(t["outcome"]) for t in trials]
    misses = [o for o in outcomes if o not in expected]
    outcome = misses[0] if misses else outcomes[0]  # C6: every trial must be expected
    record.update(trials=trials, outcome=outcome, passed=None if outcome in NEUTRAL else not misses)
    return record


def summary(records: Sequence[Mapping[str, object]]) -> dict[str, int]:
    """Counts per outcome plus run and passed; recomputed by `derive --check` (INV-CTRL-5)."""
    counts = {"run": len(records), "passed": sum(1 for r in records if r["passed"] is True)}
    counts |= {o: sum(1 for r in records if r["outcome"] == o) for o in OUTCOMES}
    return counts


def disclosure_pending(records: Sequence[Mapping[str, object]]) -> bool:
    """An accepted control whose expected set excludes acceptance (RFC-0008 §Disclosure)."""
    return any(
        r["outcome"] == "accepted" and "accepted" not in r["expected"]  # type: ignore[operator]
        for r in records
    )


def controls_document(
    run_id: str,
    control_seed: str,
    image: str,
    verifier_profile: str,
    perturbed: Mapping[str, str] | None,
    records: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """The `controls.json` document (schema controls/1)."""
    return {
        "schema": "controls/1",
        "run_id": run_id,
        "control_seed": control_seed,
        "image": image,
        "verifier_profile": verifier_profile,
        "perturbed_commitment": dict(perturbed) if perturbed else None,
        "controls": list(records),
        "summary": summary(records),
        "disclosure_pending": disclosure_pending(records),
    }


def run_shared_controls(  # noqa: PLR0913 (keyword-only inputs of one suite)
    proofs: Sequence[HonestProof],
    proof_dirs: Mapping[str, Path],
    commit: str,
    perturbed: str | None,
    *,
    workload: Workload,
    seed: str,
    verify: Verifier,
    work: Path,
    check: Callable[[str], None] = lambda proof_id: None,
    only: Collection[str] | None = None,
) -> list[dict[str, object]]:
    """C1 to C8 over a run's honest proofs, each after its honest twins (RFC-0008). `check`
    rechecks a proof's digest immediately before each control mutates it (RFC-0014). `only`
    keeps those controls; each still runs with its own twins and its own seeded mutations, so
    its record does not depend on which other controls ran (RFC-0008 §Split suites).

    `vocab_size` and `batch_size` come from the workload record (RFC-0003).
    """
    vocab_size, batch_size = workload.model.vocab_size, workload.shape.batch_size
    wanted = [cid for cid in SHARED_VERIFIER_CONTROLS if only is None or cid in only]
    chosen = select(proofs)
    target, other = chosen.target, chosen.other
    if target is None:
        return [
            {
                "id": cid,
                "side": "verifier",
                "source": "shared",
                "expected": list(EXPECTED[cid]),
                "twin": None,
                "trials": [],
                "outcome": "void",
                "passed": None,
                "note": "no accepted proof in the run",
            }
            for cid in wanted
        ]
    t_dir = proof_dirs[target.proof_id]

    def twin(*ps: HonestProof) -> Callable[[], list[VerifyCall]]:
        return lambda: [honest_call(p, commit, proof_dirs[p.proof_id]) for p in ps]

    def other_twin() -> list[VerifyCall]:
        return twin(target, *([other] if other else []))()

    def c7_calls() -> list[VerifyCall]:
        a, b = c7_pair(proofs, batch_size)
        return [c7(a, b, commit, proof_dirs[b.proof_id])]

    def c7_twins() -> list[VerifyCall]:
        a, b = c7_pair(proofs, batch_size)
        return twin(a, b)()

    builders: dict[str, tuple[Callable[[], list[VerifyCall]], Callable[[], list[VerifyCall]]]] = {
        "C1": (lambda: [c1(target, commit, t_dir, vocab_size)], twin(target)),
        "C2": (lambda: [c2(target, commit, t_dir, vocab_size, seed)], twin(target)),
        "C3": (lambda: [c3(target, commit, perturbed, t_dir)], twin(target)),
        "C4": (lambda: [c4(target, other, commit, t_dir)], other_twin),
        "C5": (lambda: [c5(target, commit, t_dir, work / "C5")], twin(target)),
        "C6": (
            lambda: [
                c6(target, commit, t_dir, work / f"C6-{s}", seed, s) for s in range(C6_TRIALS)
            ],
            twin(target),
        ),
        "C7": (c7_calls, c7_twins),
        "C8": (lambda: [c8(target, commit, t_dir, work / "C8", seed)], twin(target)),
    }

    def checked(build: Callable[[], list[VerifyCall]]) -> Callable[[], list[VerifyCall]]:
        def run() -> list[VerifyCall]:
            for p in filter(None, (target, other)):
                check(p.proof_id)
            return build()

        return run

    return [
        control_record(cid, checked(builders[cid][0]), builders[cid][1], verify) for cid in wanted
    ]


# ---------------------------------------------------------------- split suites

PART_SCHEMA = "controls-part/1"
# What every part of one suite shares; the merge refuses parts that differ in any of them.
PART_KEYS = (
    "run_id",
    "run_manifest_digest",
    "control_seed",
    "suite",
    "image",
    "verifier_profile",
    "profile",
    "verifier_cpus",
    "perturbed_commitment",
    "harness_version",
    "harness_commit",
    "harness_dirty",
)


def parse_only(values: Sequence[str], suite: Sequence[str]) -> tuple[str, ...]:
    """`--only ID[,ID...]` (repeatable): the asked controls in suite order. An empty, unknown or
    repeated id is a `config` error that names the suite."""
    asked = [cid.strip() for value in values for cid in value.split(",")]
    unknown = [cid for cid in asked if cid not in suite]
    if not asked or unknown:
        raise IProofsError(
            ErrorKind.CONFIG,
            f"--only: unknown control {', '.join(map(repr, unknown or ['']))}; "
            f"this suite is {', '.join(suite)}",
        )
    repeated = sorted({cid for cid in asked if asked.count(cid) > 1})
    if repeated:
        raise IProofsError(ErrorKind.CONFIG, f"--only names {', '.join(repeated)} twice")
    return tuple(cid for cid in suite if cid in asked)


def part_name(control_seed: str, only: Sequence[str]) -> str:
    """The file a part is written to: its seed and a digest of its subset, so two parts of
    one run never share a name unless they ran the same controls with the same seed."""
    subset = hashlib.sha256("\n".join(only).encode()).hexdigest()[:12]
    return f"controls-part-{control_seed.removeprefix('0x')}-{subset}.json"


def part_document(
    same: Mapping[str, object], only: Sequence[str], records: Sequence[Mapping[str, object]]
) -> dict[str, object]:
    """A `controls-part/1` document: the records of the controls in `only`, with what every
    part of the suite must share (`PART_KEYS`)."""
    return {
        "schema": PART_SCHEMA,
        **{key: same[key] for key in PART_KEYS},
        "only": list(only),
        "controls": list(records),
    }


def merge_parts(parts: Mapping[str, Mapping[str, Any]]) -> dict[str, object]:
    """RFC-0008 §Split suites: the `controls.json` document of a suite run in parts, keyed by
    their file names. Every part shares `PART_KEYS`; each holds the records of its own `only`,
    in suite order; together they cover the suite exactly once. The records go back in suite
    order and `summary` and `disclosure_pending` are recomputed, so the document is the one a
    single run with the same seed writes from the same verify results."""
    if not parts:
        raise IProofsError(ErrorKind.CONFIG, "--merge: no part given")
    names = list(parts)
    first = parts[names[0]]
    for name in names[1:]:
        differ = [key for key in PART_KEYS if parts[name][key] != first[key]]
        if differ:
            raise IProofsError(
                ErrorKind.CONFIG, f"{name} differs from {names[0]} in {', '.join(differ)}"
            )
    suite = list(first["suite"])
    owner: dict[str, str] = {}
    for name in names:
        ids = [str(r["id"]) for r in parts[name]["controls"]]
        if ids != list(parts[name]["only"]):
            raise IProofsError(
                ErrorKind.CONFIG, f"{name}: records {ids} are not its subset {parts[name]['only']}"
            )
        for cid in ids:
            if cid in owner:
                raise IProofsError(ErrorKind.CONFIG, f"{cid} is in both {owner[cid]} and {name}")
            owner[cid] = name
    if extra := [cid for cid in owner if cid not in suite]:
        raise IProofsError(ErrorKind.CONFIG, f"{', '.join(extra)} not in the suite {suite}")
    if gap := [cid for cid in suite if cid not in owner]:
        raise IProofsError(ErrorKind.CONFIG, f"no part ran {', '.join(gap)}")
    by_id = {str(r["id"]): r for name in names for r in parts[name]["controls"]}
    return controls_document(
        str(first["run_id"]),
        str(first["control_seed"]),
        str(first["image"]),
        str(first["verifier_profile"]),
        first["perturbed_commitment"],
        [by_id[cid] for cid in suite],
    )


# ---------------------------------------------------------------- perturbed weights (C3, P1)

MIN_PERTURB_ELEMENTS = 1024
# safetensors float dtypes: (bytes, exponent mask); one ulp up is one step of the bit pattern
FLOAT_DTYPES = {"F64": (8, 0x7FF0_0000_0000_0000), "F32": (4, 0x7F80_0000),
                "F16": (2, 0x7C00), "BF16": (2, 0x7F80)}  # fmt: skip
INT_DTYPES = {"I8": (1, True), "U8": (1, False), "I16": (2, True), "U16": (2, False),
              "I32": (4, True), "U32": (4, False), "I64": (8, True), "U64": (8, False)}  # fmt: skip


@dataclass(frozen=True, slots=True)
class Perturbation:
    """Element 0 of one tensor, before and after, as little-endian hex."""

    file: str
    tensor: str
    dtype: str
    before: str
    after: str


def safetensors_header(path: Path) -> tuple[int, dict[str, object]]:
    """(data start offset, header) of a safetensors file: an 8-byte little-endian length,
    then that many bytes of JSON."""
    with path.open("rb") as f:
        size = int.from_bytes(f.read(8), "little")
        header = json.loads(f.read(size))
    return 8 + size, header


def ulp_up(raw: bytes, dtype: str) -> bytes:
    """`raw` plus one unit in the last place at its stored precision (toward +infinity)."""
    if dtype in INT_DTYPES:
        width, signed = INT_DTYPES[dtype]
        value = int.from_bytes(raw, "little", signed=signed) + 1
        try:
            return value.to_bytes(width, "little", signed=signed)
        except OverflowError:
            raise NotApplicable(f"element 0 is the largest {dtype}") from None
    if dtype not in FLOAT_DTYPES:
        raise NotApplicable(f"dtype {dtype} has no defined unit in the last place here")
    width, exponent = FLOAT_DTYPES[dtype]
    sign = 1 << (8 * width - 1)
    bits = int.from_bytes(raw, "little")
    if bits & exponent == exponent:
        raise NotApplicable("element 0 is not finite")
    up = 1 if bits == sign else bits - 1 if bits & sign else bits + 1  # -0 goes to +min
    if up & exponent == exponent:
        raise NotApplicable(f"element 0 is the largest finite {dtype}")
    return up.to_bytes(width, "little")


def perturb_model(src: Path, dst: Path) -> Perturbation:
    """RFC-0008 C3: copy the model directory, take the tensor with the lexicographically first
    name among tensors of at least 1,024 elements (over every *.safetensors file), and add one
    unit in the last place to its element 0. Raises NotApplicable when no tensor qualifies."""
    found = []
    for path in sorted(src.rglob("*.safetensors")):
        start, header = safetensors_header(path)
        for name, info in header.items():
            if isinstance(info, dict) and math.prod(info.get("shape", [])) >= MIN_PERTURB_ELEMENTS:
                found.append((name, path, start + int(info["data_offsets"][0]), info["dtype"]))
    if not found:
        raise NotApplicable(f"no safetensors tensor of at least {MIN_PERTURB_ELEMENTS} elements")
    name, path, offset, dtype = min(found)
    width = INT_DTYPES[dtype][0] if dtype in INT_DTYPES else FLOAT_DTYPES.get(dtype, (1, 0))[0]
    with path.open("rb") as f:
        f.seek(offset)
        before = f.read(width)
    after = ulp_up(before, dtype)
    shutil.copytree(src, dst, symlinks=False)
    for p in [dst, *dst.rglob("*")]:  # the source cache is read-only; the copy must not be
        p.chmod(0o755 if p.is_dir() else 0o644)
    with (dst / path.relative_to(src)).open("r+b") as f:
        f.seek(offset)
        f.write(after)
    return Perturbation(path.relative_to(src).as_posix(), name, dtype, before.hex(), after.hex())


# ---------------------------------------------------------------- system-specific controls


def edge_unbound(report: object, edge: str) -> bool:
    """RFC-0008: the binding report marks `edge` unbound. A report is a JSON object with
    `edges`, either a mapping edge -> state or a list of {edge, state}."""
    edges = report.get("edges") if isinstance(report, dict) else None
    if isinstance(edges, dict):
        return edges.get(edge) == "unbound"
    if isinstance(edges, list):
        return any(e.get("edge") == edge and e.get("state") == "unbound" for e in edges
                   if isinstance(e, dict))  # fmt: skip
    return False


def prover_side_record(
    control_id: str,
    expected: Sequence[str],
    source: str,
    prove: Callable[[], list[VerifyCall]],
    twins: Callable[[], list[VerifyCall]],
    verify: Verifier,
    *,
    side: str = "prover",
) -> dict[str, object]:
    """A control whose trials come from a control prove (P1, P2, weakened provers). `prove`
    returns the verify calls of the proofs it made; a prove that fails is `prover_failed`,
    which passes when expected (RFC-0008 §Outcomes)."""
    base: dict[str, object] = {
        "id": control_id, "side": side, "source": source, "expected": list(expected),
        "twin": None, "trials": [], "outcome": "not_applicable", "passed": None, "note": None,
    }  # fmt: skip
    try:
        calls = prove()
    except NotApplicable as e:
        return {**base, "note": str(e)}
    except IProofsError as e:
        return {**base, "outcome": "prover_failed", "passed": "prover_failed" in expected,
                "note": f"{e.kind}: {e.message}"[:4096]}  # fmt: skip
    return control_record(control_id, lambda: calls, twins, verify, side=side, source=source,
                          expected=expected)  # fmt: skip


def system_control_record(
    control: SystemControl,
    run: Callable[[], tuple[list[VerifyCall], object]],
    twins: Callable[[], list[VerifyCall]],
    verify: Verifier,
) -> dict[str, object]:
    """One `controls.yaml` control (RFC-0008 §System-specific controls), recorded with
    `source: system` under the shared outcome and pass rules. `run` returns the verify calls
    and the binding report of a weakened prove; a `fixture_proof` control is not applicable
    until the delivery of upstream fixture proofs is specified."""
    expected = list(control.expected)
    record: dict[str, object] = {
        "id": control.id,
        "side": "prover" if control.kind == "weakened_prover" else "verifier",
        "source": "system",
        "expected": expected,
        "twin": None,
        "trials": [],
        "outcome": "not_applicable",
        "passed": None,
        "note": None,
    }
    if control.kind == "fixture_proof":
        record["note"] = f"fixture proof delivery is not specified yet; upstream: {control.source}"
        return record
    report: object = None

    def prove() -> list[VerifyCall]:
        nonlocal report
        calls, report = run()
        return calls

    done = prover_side_record(control.id, expected, "system", prove, twins, verify,
                              side=str(record["side"]))  # fmt: skip
    edge = control.requires_unbound_edge
    if done["passed"] is True and edge and not edge_unbound(report, edge):
        done |= {"passed": False, "note": f"binding report does not mark {edge!r} unbound"}
    return done


# ---------------------------------------------------------------- control map (RFC-0016 OVR-2)

# Control id -> the one glyph property an accepted outcome can contradict, or None. A
# system-specific control (`fixture_proof`, `weakened_prover`) is absent and maps to None (Q7).
CONTROL_PROPERTY: Mapping[str, str | None] = MappingProxyType({
    "C1": "whole_output",
    "C2": "whole_output",
    "C3": "model_bound",
    "C4": "whole_output",
    "C5": None,
    "C6": None,
    "C7": "whole_output",
    "C8": None,
    "P1": "model_bound",
    "P2": "model_bound",
})  # fmt: skip


def runs_read(root: Path, release: str | None, system: str, configuration: str) -> list[str]:
    """RFC-0016 OVR-5: the run directories read for one card row, as `release.yaml` lists them.

    The runs listed in `releases/<release>/release.yaml` and in every release with an earlier
    `freeze_date`, in freeze-date order then listed order, whose `run.json` `claim` names
    `system` and `configuration`; less every run a read release supersedes and every run a
    read run `replaces`. No release reads no run. The site and CRIT-13 both call this.
    """
    if release is None:
        return []
    named = root / "releases" / release / "release.yaml"
    if not named.is_file():
        raise IProofsError(ErrorKind.INTEGRITY, f"OVR-5: no releases/{release}/release.yaml")
    cutoff = str(load_yaml(named)["freeze_date"])
    docs = [load_yaml(path) for path in sorted((root / "releases").glob("*/release.yaml"))]
    read = sorted(
        (d for d in docs if d["release"] == release or str(d["freeze_date"]) < cutoff),
        key=lambda d: (str(d["freeze_date"]), str(d["release"])),
    )
    dropped = {str(s["run_id"]) for d in read for s in _items(d.get("superseded_runs"))}
    kept: list[tuple[str, str]] = []  # (run directory, run id)
    for doc in read:
        for run_dir in _items(doc.get("runs")):
            path = root / str(run_dir) / "run.json"
            try:
                run = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                raise IProofsError(ErrorKind.ENVIRONMENT, f"OVR-5: cannot read {path}: {e}") from e
            claim = run.get("claim") or {}
            if (claim.get("system"), claim.get("configuration")) != (system, configuration):
                continue
            if replaces := run.get("replaces"):
                dropped.add(str(replaces["run_id"]))
            if str(run_dir) not in (k for k, _ in kept):
                kept.append((str(run_dir), str(run["run_id"])))
    return [run_dir for run_dir, run_id in kept if run_id not in dropped]


def _items(node: object) -> list[Any]:
    """A YAML list, or no items when the key is absent."""
    return node if isinstance(node, list) else []
