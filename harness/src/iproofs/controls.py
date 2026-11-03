"""Negative controls: mutations, honest twins, classification (RFC-0008).

INV-CTRL-1: every mutated input is produced here, by the harness; adapters never mutate.
INV-CTRL-3: every mutation is a deterministic function of `control_seed`, the control id and
the honest inputs.
"""

import math
import os
import random
import re
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from iproofs.errors import ErrorKind, IProofsError

CONTROL_SEED_RE = re.compile(r"^0x[0-9a-f]{16}$")


def new_control_seed() -> str:
    """A fresh 64-bit seed from the OS, written as `0x` plus 16 lowercase hex digits."""
    return f"0x{int.from_bytes(os.urandom(8), 'big'):016x}"


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
