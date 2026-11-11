"""RFC-0018 round 2 on CPU: the generation marks (AD-4), `perturb` (AD-5) on a synthetic GGUF
file, and W' accepted only in P1 and C3 control jobs (CH-2)."""

import json
import shutil
import struct
from pathlib import Path
from types import ModuleType

import flashprove_stubs
import pytest
from flashprove_stubs import commands, job, run

adapter = flashprove_stubs.adapter  # the fixture
P, R = 8, 8
SHAPE = {"prompt_tokens": P, "output_tokens": R, "batch_size": 2, "batches_per_session": 1,
         "context_window": P + R}  # fmt: skip


def level1(adapter: ModuleType) -> dict[str, object]:
    adapter.host("/io/fit/config/policy.txt").write_text("lt 4\n")
    rows = [[i + 1] + [7] * (P - 1) for i in range(2)]
    adapter.host("/io/prompts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    out = run(adapter, "commit", job("commit", model_dir="/models", shape=SHAPE))
    adapter.host("/io/state/isk.tar").chmod(0o444)
    return out


def prove_job(committed: dict[str, object], **fields: object) -> dict[str, object]:
    return job("prove", commitment_id=committed["commitment_id"], model_dir="/models",
               prover_files=committed["prover_files"], prompts_file="/io/prompts.jsonl",
               batch_size=2, batches=1, shape=SHAPE, **fields)  # fmt: skip


def test_generation_marks(adapter: ModuleType) -> None:
    run(adapter, "prove", prove_job(level1(adapter)))
    marks = adapter.host("/io/marks")
    assert sorted(p.name for p in marks.iterdir()) == ["generation.end", "generation.start"]
    start, end = (marks / "generation.start").stat(), (marks / "generation.end").stat()
    assert start.st_size == end.st_size == 0
    assert start.st_mtime_ns <= end.st_mtime_ns


def test_no_marks_for_one_output_token(adapter: ModuleType) -> None:
    out = run(adapter, "commit", job("commit", model_dir="/models"))
    rows = [[i + 1] + [7] * 7 for i in range(6)]
    adapter.host("/io/prompts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    run(adapter, "prove", job("prove", commitment_id=out["commitment_id"], model_dir="/models",
        prover_files=out["prover_files"], prompts_file="/io/prompts.jsonl", batch_size=2,
        batches=3))  # fmt: skip
    assert not adapter.host("/io/marks").exists()


# ---------------------------------------------------------------- perturb


def gguf(tensors: list[tuple[str, int, bytes]]) -> bytes:
    """A GGUF file of version 3 with general.alignment 32 and one row per tensor."""

    def text(s: str) -> bytes:
        return struct.pack("<Q", len(s)) + s.encode()

    head = b"GGUF" + struct.pack("<IQQ", 3, len(tensors), 1)
    head += text("general.alignment") + struct.pack("<II", 4, 32)
    data, at = b"", 0
    for name, kind, body in tensors:
        head += text(name) + struct.pack("<IQQIQ", 2, 256, len(body) // 144, kind, at)
        data += body
        at += len(body)
    return head + b"\0" * (-len(head) % 32) + data


def q4k(h: bytes, scales: list[int], codes: bytes) -> bytes:
    return h + b"\0\0" + bytes(scales) + codes


# block 0: h = 0, no step moves anything; block 1: h = 1.0, sub-block 0's scale is 63 and
# cannot rise, sub-block 1's is 5 (byte 0x45, upper bits 01) with codes in the high halves
BLOCKS = q4k(b"\0\0", [1] * 12, b"\x11" * 128) + q4k(b"\x00\x3c", [63, 0x45] + [0] * 10,
                                                     b"\x10" * 32 + b"\0" * 96)  # fmt: skip


def models(adapter: ModuleType) -> Path:
    model: Path = adapter.host("/models/UD-Q4_K_XL")
    names = adapter.SHARDS
    (model / names[0]).write_bytes(gguf([("blk.0.attn_q.weight", 14, b"\1" * 210),
                                         ("blk.0.attn_k.weight", 12, BLOCKS)]))  # fmt: skip
    for name in names[1:]:
        (model / name).write_bytes(gguf([]))
    return model


def perturb_job() -> dict[str, object]:
    return job("perturb", change="one Q4_K block scale of one dense attention tensor of block 0, "
               "raised by one step, in the committed GGUF file", model_dir="/models",
               out_dir="/io/perturbed")  # fmt: skip


def test_perturb_raises_one_q4k_scale(adapter: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    model = models(adapter)
    monkeypatch.setenv("STUB_WSUMS", "other sums")  # weight_sums sees other integers in W'
    out = run(adapter, "perturb", perturb_job())
    rec = out["perturbation"]
    assert (rec["tensor"], rec["index"], rec["old"], rec["new"]) == (
        "blk.0.attn_k.weight", 256 + 32, "45", "46")  # fmt: skip
    assert rec["digest_w"] != rec["digest_w_prime"]
    assert rec["digest_tool"].startswith("bin/weight_sums")
    before = (model / adapter.SHARDS[0]).read_bytes()
    after = adapter.host(f"/io/perturbed/UD-Q4_K_XL/{adapter.SHARDS[0]}").read_bytes()
    diff = [i for i in range(len(before)) if before[i] != after[i]]
    assert [(before[i], after[i]) for i in diff] == [(0x45, 0x46)]
    for name in adapter.SHARDS[1:]:
        assert adapter.host(f"/io/perturbed/UD-Q4_K_XL/{name}").read_bytes() == (
            model / name).read_bytes()  # fmt: skip
    [ws] = commands(adapter)
    assert ws["argv"][0].endswith("/bin/weight_sums")
    assert ws["argv"][-5:] == [str(adapter.host(f"/io/perturbed/UD-Q4_K_XL/{n}"))
                               for n in adapter.SHARDS]  # fmt: skip


def test_perturb_refuses_a_change_that_leaves_the_integers(adapter: ModuleType) -> None:
    models(adapter)  # the stand-in weight_sums writes the published sums: nothing moved
    with pytest.raises(SystemExit, match="left every committed integer"):
        run(adapter, "perturb", perturb_job())


def test_perturb_refuses_another_change(adapter: ModuleType) -> None:
    models(adapter)
    doc = perturb_job() | {"change": "one BF16 weight"}
    with pytest.raises(SystemExit, match="Q4_K scale step"):
        run(adapter, "perturb", doc)


# ---------------------------------------------------------------- W' in control jobs


def setup_job(control: object) -> dict[str, object]:
    return job("setup", control=control)


@pytest.mark.parametrize("control", [False, True, {"id": "C2"}])
def test_other_wsums_refused_outside_p1_and_c3(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch, control: object
) -> None:
    shutil.rmtree(adapter.host("/io/fit"))
    monkeypatch.setenv("STUB_WSUMS", "other")
    with pytest.raises(SystemExit, match=r"not the published model/wsums\.txt"):
        run(adapter, "setup", setup_job(control))


def test_c3_setup_and_commit_accept_w_prime(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C3: setup builds W''s wsums.txt with bin/weight_sums and commits to it, with warnings."""
    shutil.rmtree(adapter.host("/io/fit"))
    monkeypatch.setenv("STUB_WSUMS", "other")
    control = {"id": "C3", "perturbation": {"tensor": "blk.0.attn_k.weight"}}
    out = run(adapter, "setup", setup_job(control))
    assert out["ready"] is True
    assert [w.split(" is ")[0] for w in out["warnings"]] == ["model/wsums.txt"]
    assert adapter.host("/io/fit/weights/wsums.txt").read_text() == "other\n"
    committed = run(adapter, "commit", job("commit", model_dir="/models", control=control))
    assert [w.split(" is ")[0] for w in committed["warnings"]] == ["model/wsums.txt"]


def test_p1_proves_w_prime_against_ws_commitment(adapter: ModuleType) -> None:
    committed = level1(adapter)
    model = adapter.host("/models/UD-Q4_K_XL")
    (model / adapter.SHARDS[0]).write_bytes(b"W prime")
    out = run(adapter, "prove", prove_job(committed, control={"id": "P1", "perturbation": {}}))
    assert adapter.host(f"/io/fit/weights/{adapter.SHARDS[0]}").read_bytes() == b"W prime"
    spec = json.loads(adapter.host("/io/state/prove/integer-model/integer_model.json").read_text())
    assert spec["weight_settings"]["verify_sums"] is False
    assert len(out["warnings"]) == 2


def test_honest_prove_keeps_the_committed_weights(adapter: ModuleType) -> None:
    committed = level1(adapter)
    (adapter.host("/models/UD-Q4_K_XL") / adapter.SHARDS[0]).write_bytes(b"W prime")
    out = run(adapter, "prove", prove_job(committed))
    assert adapter.host(f"/io/fit/weights/{adapter.SHARDS[0]}").read_bytes() != b"W prime"
    spec = json.loads(adapter.host("/io/state/prove/integer-model/integer_model.json").read_text())
    assert spec["weight_settings"]["verify_sums"] is True
    assert out["warnings"] == []
