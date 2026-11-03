import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from iproofs import controls as ctl
from iproofs.controls import HonestProof, NotApplicable
from iproofs.errors import IProofsError

ROOT = Path(__file__).resolve().parents[3]
FAKE = ROOT / "systems/fake"
SEED = "0x0123456789abcdef"


def honest(pid: str, request: tuple[int, ...], t: int, batch: int = 0) -> HonestProof:
    return HonestProof(pid, request, (5,), "accept", t, batch)


def proof_dir(tmp: Path, parts: dict[str, bytes]) -> Path:
    d = tmp / "honest"
    d.mkdir()
    for name, data in parts.items():
        (d / name).write_bytes(data)
    return d


def test_c1_changes_last_token_mod_vocab(tmp_path: Path) -> None:
    target = HonestProof("p", (1, 2), (3, 9), "accept", 1, 0)
    call = ctl.c1(target, "c", tmp_path, vocab_size=10)
    assert call.claimed_output == (3, 0)
    assert call.request == target.request


def test_c1_identical_mutation_is_internal_error(tmp_path: Path) -> None:
    target = HonestProof("p", (1,), (0,), "accept", 1, 0)
    with pytest.raises(IProofsError, match="identical"):
        ctl.c1(target, "c", tmp_path, vocab_size=1)


def test_c2_changes_one_seeded_position(tmp_path: Path) -> None:
    target = honest("p", tuple(range(1024)), 1)
    call = ctl.c2(target, "c", tmp_path, vocab_size=2048, seed=SEED)
    diff = [i for i, (a, b) in enumerate(zip(target.request, call.request, strict=True)) if a != b]
    assert diff == [call.mutation["position"]]


def test_c3_not_applicable_without_perturbed_commit(tmp_path: Path) -> None:
    with pytest.raises(NotApplicable, match="no perturbed commitment"):
        ctl.c3(honest("p", (1,), 1), "c", None, tmp_path)
    assert ctl.c3(honest("p", (1,), 1), "c", "c-perturbed", tmp_path).commitment_id == "c-perturbed"


def test_c4_needs_a_different_request(tmp_path: Path) -> None:
    target = honest("p", (1,), 1)
    with pytest.raises(NotApplicable):
        ctl.c4(target, None, "c", tmp_path)
    call = ctl.c4(target, honest("q", (2,), 2), "c", tmp_path)
    assert call.request == (2,)


def test_c5_truncates_largest_part_tiebreak_by_name(tmp_path: Path) -> None:
    src = proof_dir(tmp_path, {"b.bin": b"12345678", "a.bin": b"abcdefgh", "c.bin": b"x"})
    call = ctl.c5(honest("p", (1,), 1), "c", src, tmp_path / "c5")
    assert call.mutation == {"part": "a.bin", "bytes": 4}
    assert (tmp_path / "c5/a.bin").read_bytes() == b"abcd"
    assert (tmp_path / "c5/b.bin").read_bytes() == b"12345678"
    assert (src / "a.bin").read_bytes() == b"abcdefgh"  # honest proof untouched


def test_c6_five_trials_flip_one_bit(tmp_path: Path) -> None:
    src = proof_dir(tmp_path, {"body.bin": bytes(range(40)), "tag.bin": bytes(32)})
    for s in range(ctl.C6_TRIALS):
        call = ctl.c6(honest("p", (1,), 1), "c", src, tmp_path / f"c6-{s}", SEED, s)
        part = str(call.mutation["part"])
        before, after = (src / part).read_bytes(), (call.proof_dir / part).read_bytes()
        flipped = sum(bin(x ^ y).count("1") for x, y in zip(before, after, strict=True))
        assert flipped == 1
        again = ctl.c6(honest("p", (1,), 1), "c", src, tmp_path / f"c6-{s}-again", SEED, s)
        assert again.mutation == call.mutation  # reproducible from the seed


def test_c7_not_applicable_batch_one() -> None:
    proofs = [honest("p", (1,), 1), honest("q", (2,), 2)]
    with pytest.raises(NotApplicable, match="batch size 1"):
        ctl.c7_pair(proofs, batch_size=1)


def test_c7_pair_same_batch_only() -> None:
    proofs = [honest("p", (1,), 1, batch=0), honest("q", (2,), 2, batch=1)]
    with pytest.raises(NotApplicable, match="in one batch"):
        ctl.c7_pair(proofs, batch_size=2)
    a, b = ctl.c7_pair([*proofs, honest("r", (3,), 3, batch=1)], batch_size=2)
    assert (a.proof_id, b.proof_id) == ("q", "r")


def test_c8_not_applicable_single_part(tmp_path: Path) -> None:
    src = proof_dir(tmp_path, {"only.bin": b"x"})
    with pytest.raises(NotApplicable, match="single part"):
        ctl.c8(honest("p", (1,), 1), "c", src, tmp_path / "c8", SEED)


def test_c8_drops_one_part(tmp_path: Path) -> None:
    src = proof_dir(tmp_path, {"a.bin": b"a", "b.bin": b"b"})
    call = ctl.c8(honest("p", (1,), 1), "c", src, tmp_path / "c8", SEED)
    assert len(call.parts) == 1
    assert call.mutation["dropped"] not in call.parts


def test_commitment_never_from_proof(tmp_path: Path) -> None:
    """A forged commitment file in the proof directory never reaches the verify call."""
    src = proof_dir(tmp_path, {"body.bin": b"b" * 32, "commitment.txt": b"forged"})
    call = ctl.c5(honest("p", (1,), 1), "from-harness-record", src, tmp_path / "c5")
    assert call.commitment_id == "from-harness-record"


def fake(io: Path, sub: str, job: dict[str, object]) -> dict[str, object]:
    full = {
        "schema": "adapter-job/1",
        "contract": "adapter/1",
        "subcommand": sub,
        "run_id": "2026-11-20-fake-fake-tiny-ci-ci-cpu-1",
        "workload": {"id": "fake-tiny-ci", "version": 1},
        "shape": {
            "prompt_tokens": 8,
            "output_tokens": 1,
            "batch_size": 2,
            "batches_per_session": 1,
            "context_window": 8,
        },
        "control": False,
        **job,
    }
    (io / "job.json").write_text(json.dumps(full))
    env = {
        **os.environ,
        "IPROOFS_IO": str(io),
        "IPROOFS_MODELS": str(FAKE / "model"),
        "IPROOFS_FAKE_DELAY_S": "0",
    }
    subprocess.run(
        [sys.executable, str(FAKE / "entrypoint"), sub, "/io/job.json", "/io/out.json"],
        env=env,
        check=True,
    )
    out: dict[str, object] = json.loads((io / "out.json").read_text())
    return out


def test_controls_against_fake_verifier(tmp_path: Path) -> None:
    """Every shared verifier-side control is rejected (or invalid_call) by the fake verifier."""
    io = tmp_path / "io"
    io.mkdir()
    prompts = [list(range(8)), list(range(1, 9))]
    (io / "prompts.jsonl").write_text("".join(json.dumps(p) + "\n" for p in prompts))
    commit = str(fake(io, "commit", {"model_dir": "/models"})["commitment_id"])
    out = fake(
        io,
        "prove",
        {
            "commitment_id": commit,
            "prover_files": [],
            "model_dir": "/models",
            "prompts_file": "/io/prompts.jsonl",
            "batch_size": 2,
            "batches": 1,
        },
    )
    entries = out["proofs"]
    assert isinstance(entries, list)
    proofs = [
        HonestProof(e["proof_id"], tuple(prompts[i]), tuple(e["claimed_output"]), "accept", i, 0)
        for i, e in enumerate(entries)
    ]
    dirs = {p.proof_id: io / "proofs" / p.proof_id for p in proofs}
    target, other = proofs
    work = io / "mutations"
    a, b = ctl.c7_pair(proofs, batch_size=2)
    calls = [
        ctl.c1(target, commit, dirs["req-0"], vocab_size=256),
        ctl.c2(target, commit, dirs["req-0"], vocab_size=256, seed=SEED),
        ctl.c3(target, commit, "0" * 64, dirs["req-0"]),
        ctl.c4(target, other, commit, dirs["req-0"]),
        ctl.c5(target, commit, dirs["req-0"], work / "c5"),
        *(ctl.c6(target, commit, dirs["req-0"], work / f"c6-{s}", SEED, s) for s in range(5)),
        ctl.c7(a, b, commit, dirs[b.proof_id]),
        ctl.c8(target, commit, dirs["req-0"], work / "c8", SEED),
    ]
    for call in calls:
        verdict = fake(
            io,
            "verify",
            {
                "commitment_id": call.commitment_id,
                "verifier_files": [],
                "request": list(call.request),
                "claimed_output": list(call.claimed_output),
                "proof_dir": "/io/" + call.proof_dir.relative_to(io).as_posix(),
            },
        )["verdict"]
        allowed = (
            {"reject", "invalid_call"} if call.control_id in {"C5", "C6", "C8"} else {"reject"}
        )
        assert verdict in allowed, (call.control_id, call.trial, verdict)
