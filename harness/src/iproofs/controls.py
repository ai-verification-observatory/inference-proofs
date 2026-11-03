"""Negative controls: mutations, honest twins, classification (RFC-0008).

INV-CTRL-1: every mutated input is produced here, by the harness; adapters never mutate.
INV-CTRL-3: every mutation is a deterministic function of `control_seed`, the control id and
the honest inputs.
"""

import math
import os
import random
import re
from collections.abc import Sequence
from dataclasses import dataclass

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
