import re
import subprocess
import sys

import pytest

from iproofs.controls import HonestProof, new_control_seed, rng, seeded_index, select

SEED = "0x5f3c9a12d4e6b780"


def proof(pid: str, request: tuple[int, ...], verdict: str, t: int, batch: int = 0) -> HonestProof:
    return HonestProof(pid, request, (1,), verdict, t, batch)


def test_control_seed_format() -> None:
    seed = new_control_seed()
    assert re.fullmatch(r"0x[0-9a-f]{16}", seed)
    assert new_control_seed() != seed


def test_c2_seeded_position_stable() -> None:
    """Same seed, same position across processes; different seeds differ for 1,024 tokens."""
    here = seeded_index(SEED, "C2", 0, 1024)
    code = (
        f"from iproofs.controls import seeded_index; print(seeded_index({SEED!r}, 'C2', 0, 1024))"
    )
    there = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert int(there.stdout) == here
    seeds = [f"0x{i:016x}" for i in range(10)]
    assert len({seeded_index(s, "C2", 0, 1024) for s in seeds}) > 1


def test_control_seed_generator_keys_on_control_and_trial() -> None:
    assert rng(SEED, "C6", 0).random() != rng(SEED, "C6", 1).random()
    assert rng(SEED, "C6", 0).random() != rng(SEED, "C8", 0).random()
    assert rng(SEED, "C6", 0).random() == rng(SEED, "C6", 0).random()


@pytest.mark.parametrize("bad", ["0x123", "5f3c9a12d4e6b780", "0X5F3C9A12D4E6B780"])
def test_control_seed_rejects_malformed(bad: str) -> None:
    with pytest.raises(ValueError, match="bad control seed"):
        rng(bad, "C2", 0)


def test_control_seed_index_bounds() -> None:
    assert all(0 <= seeded_index(f"0x{i:016x}", "C8", 0, 3) < 3 for i in range(200))
    with pytest.raises(ValueError, match="empty range"):
        seeded_index(SEED, "C8", 0, 0)


def test_control_seed_select_target_and_other() -> None:
    proofs = [
        proof("p2", (2,), "accept", 30),
        proof("p0", (1,), "reject", 10),
        proof("p1", (1,), "accept", 20),
        proof("p3", (1,), "accept", 25),  # same request as target: not "other"
    ]
    chosen = select(proofs)
    assert chosen.target is not None
    assert chosen.target.proof_id == "p1"  # first accepted in release order
    assert chosen.other is not None
    assert chosen.other.proof_id == "p2"


def test_control_seed_select_no_other() -> None:
    chosen = select([proof("p0", (1,), "accept", 1), proof("p1", (1,), "accept", 2)])
    assert chosen.target is not None
    assert chosen.other is None


def test_control_seed_select_nothing_accepted() -> None:
    chosen = select([proof("p0", (1,), "reject", 1)])
    assert chosen.target is None
    assert chosen.other is None
