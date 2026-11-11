"""Level 1 (RFC-0018) on CPU: the grid of 512 + 512, five requests a session with one proof
released per request as it completes, and C1 on the whole reply. Every upstream process is
stub_upstream.py; the model has 2 layers in the stub, 32 in the geometry checks."""

import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from sash_fixtures import load, run_step

SHAPE = {"prompt_tokens": 512, "output_tokens": 512, "batch_size": 1, "batches_per_session": 5,
         "context_window": 1024}  # fmt: skip
PROMPTS = [[i] * 512 for i in range(1, 6)]
TOK = list(range(1000, 1512))  # the ids the stub's statements state for each block


@pytest.fixture
def adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setenv("IPROOFS_SASH_STUB_TOK", json.dumps(TOK))
    return load(tmp_path, monkeypatch)


def test_geometry_512_512(adapter: ModuleType) -> None:
    """Two blocks of 512: block 0 the prompt, block 1 the reply; the head over both; links by
    headline-c4096.sh L113-L114: 2 x 31 + 2 = 64 and 1 x 32 = 32."""
    g = adapter.geometry(SHAPE, 32)
    assert (g["blocks"], g["head_blocks"]) == (2, [0, 1])
    assert (g["expect_layer_links"], g["expect_token_links"]) == (64, 32)


def test_geometry_of_the_recorded_headline(adapter: ModuleType) -> None:
    """4,096 + 512: 9 blocks, head blocks 7 and 8, 290 segments (results repository,
    runs/2026-09-09-headline-c4096-h100/config.json)."""
    g = adapter.geometry({"prompt_tokens": 4096, "output_tokens": 512}, 32)
    assert (g["blocks"], g["head_blocks"]) == (9, [7, 8])
    assert g["blocks"] * 32 + len(g["head_blocks"]) == 290


def commands(adapter: ModuleType) -> list[list[str]]:
    lines = adapter.host("/io/commands.jsonl").read_text().splitlines()
    return [json.loads(line)["argv"] for line in lines]


def session(adapter: ModuleType) -> dict[str, Any]:
    adapter.host("/io/prompts.jsonl").write_text("".join(json.dumps(p) + "\n" for p in PROMPTS))
    c = run_step(adapter, "commit", model_dir="/models", shape=SHAPE)
    p = run_step(adapter, "prove", shape=SHAPE, commitment_id=c["commitment_id"],
                 model_dir="/models", prover_files=c["prover_files"],
                 prompts_file="/io/prompts.jsonl", batch_size=1, batches=5)  # fmt: skip
    return {"commit": c, "prove": p}


def test_one_commit_five_proofs_each_released_before_the_next_begins(adapter: ModuleType) -> None:
    done = session(adapter)
    assert [p["proof_id"] for p in done["prove"]["proofs"]] == [f"req-{i}" for i in range(5)]
    assert all(p["claimed_output"] == TOK for p in done["prove"]["proofs"])
    released = [
        json.loads(ln) for ln in adapter.host("/io/stub-released.jsonl").read_text().splitlines()
    ]
    assert released == [[f"req-{i}" for i in range(k)] for k in range(5)]
    argvs = commands(adapter)
    assert sum("model-roots" in a for a in argvs) == 1
    gen = [a for a in argvs if "harness.witness.gen_ids" in a]
    assert len(gen) == 5
    assert gen[0][gen[0].index("--prefix") + 1 :][:5] == ["512", "--offset", "0", "--new", "513"]
    shift = next(a for a in argvs if "harness.witness.shift_ids" in a)
    assert shift[shift.index("--new") + 1] == "512"
    plan = next(a for a in argvs if "harness.witness.plan" in a)
    assert plan[plan.index("--blocks") + 1] == "2"
    assert plan[plan.index("--head-blocks") + 1] == "0,1"
    extract = next(a for a in argvs if "harness.witness.extract" in a)
    assert extract[extract.index("--tokens") + 1 :][:3] == ["1024", "--chunk", "512"]


def mutate(adapter: ModuleType, position: int, token: int) -> dict[str, Any]:
    """RFC-0018 AD-6."""
    return run_step(adapter, "mutate_reply", proof_dir="/io/proofs/req-2",
                    position=position, token=token, out_dir="/io/mutated")  # fmt: skip


@pytest.mark.parametrize("position", [0, 511, 200])  # C1: first, last, interior reply token
def test_c1_mutated_proof_is_refused_by_the_grid(adapter: ModuleType, position: int) -> None:
    """The reply token changed in the proof where the grid reads it, and the head's paired
    emitted token with it; verify gets the honest claimed reply; the grid refuses (here the
    stand-in's segment binding, as verify_composed's Horner check)."""
    done = session(adapter)
    c = done["commit"]
    fields = {"commitment_id": c["commitment_id"], "verifier_files": c["verifier_files"],
              "request": PROMPTS[2], "claimed_output": TOK, "shape": SHAPE}  # fmt: skip
    honest = run_step(adapter, "verify", proof_dir="/io/proofs/req-2", **fields)
    assert (honest["verdict"], honest["warnings"]) == ("accept", [])
    out = mutate(adapter, position, TOK[position] + 1)
    head = "B1head.fixed.json" if position else "B0head.fixed.json"
    assert out["mutated"]["parts"] == ["B1L0.fixed.json", head]
    mutated = run_step(adapter, "verify", proof_dir="/io/mutated", **fields)
    assert (mutated["verdict"], mutated["raw_exit_code"]) == ("reject", 1)
    assert mutated["warnings"]  # the note: the claim differs from the proof's ids
    grid = [a for a in commands(adapter) if "boundary-grid" in a][-1]
    assert grid[grid.index("--expect-layer-links") + 1] == "4"  # 2 blocks x (2 - 1) + 2
    assert grid[grid.index("--expect-token-links") + 1] == "2"  # (2 - 1) x 2
    prompt = json.loads(adapter.host("/io/verify/prompt.json").read_text())
    assert prompt == {"ids": PROMPTS[2]}  # the prompt only: the claim never reaches the grid


@pytest.mark.parametrize(("position", "head", "index"), [(0, "B0head", 511), (5, "B1head", 4)])
def test_mutate_reply_changes_two_values_and_nothing_else(
    adapter: ModuleType, position: int, head: str, index: int
) -> None:
    session(adapter)
    out = mutate(adapter, position, 77)
    assert out["mutated"]["fields"] == [f"B1L0.fixed.json tok_in[{position}]",
                                        f"{head}.fixed.json tok_out[{index}]"]  # fmt: skip
    src, dst = adapter.host("/io/proofs/req-2"), adapter.host("/io/mutated")
    assert sorted(p.name for p in src.iterdir()) == sorted(p.name for p in dst.iterdir())
    changed = [
        p.name for p in sorted(src.iterdir()) if p.read_bytes() != (dst / p.name).read_bytes()
    ]
    assert changed == sorted(["B1L0.fixed.json", f"{head}.fixed.json"])
    for name, key, at in (("B1L0", "tok_in", position), (head, "tok_out", index)):
        before = json.loads((src / f"{name}.fixed.json").read_text())
        after = json.loads((dst / f"{name}.fixed.json").read_text())
        assert (after[key][at], before[key][at]) == (77, TOK[position])
        before[key][at] = 77
        assert after == before
    bytes_before = (src / "B1L0.fixed.json").read_bytes()
    bytes_after = (dst / "B1L0.fixed.json").read_bytes()
    assert len(bytes_before) - len(str(TOK[position])) == len(bytes_after) - 2


def test_mutate_reply_refuses_a_position_past_the_reply(adapter: ModuleType) -> None:
    session(adapter)
    with pytest.raises(SystemExit, match="outside the reply's 512 tokens"):
        mutate(adapter, 512, 1)


ROW0 = [0x4000, 0x3F80, 0x3E80, 0xBF00]


def test_perturb_moves_one_int8_code(adapter: ModuleType) -> None:
    """W' from a two-shard model: o_proj of layer 0 in the second shard, row 0 of which is the
    hand case of test_sash_weight_change.py (2.0, 1.0, 0.25, -0.5): column 1, one step up."""
    models = adapter.host("/models")
    tensor = "model.layers.0.self_attn.o_proj.weight"
    for name, tensors in (("model-00001-of-00002.safetensors", {"lm_head.weight": [0x3F80] * 4}),
                          ("model-00002-of-00002.safetensors",
                           {tensor: [*ROW0, 0x3F80, 0, 0, 0]})):  # fmt: skip
        header, data = {}, b""
        for t, values in tensors.items():
            header[t] = {"dtype": "BF16", "shape": [len(values) // 4, 4],
                         "data_offsets": [len(data), len(data) + 2 * len(values)]}  # fmt: skip
            data += b"".join(v.to_bytes(2, "little") for v in values)
        text = json.dumps(header).encode()
        (models / name).write_bytes(len(text).to_bytes(8, "little") + text + data)
    out = run_step(adapter, "perturb", change="the smallest change to one BF16 "
                   "weight ...", model_dir="/models", out_dir="/io/perturbed")  # fmt: skip
    rec = out["perturbation"]
    assert (rec["tensor"], rec["index"], rec["old"], rec["new"]) == (tensor, 1, "803f", "813f")
    assert rec["digest_tool"] is None
    assert rec["digest_w"] != rec["digest_w_prime"]
    copy = adapter.host("/io/perturbed")
    assert sorted(p.name for p in copy.iterdir()) == sorted(p.name for p in models.iterdir())
    a = (models / "model-00002-of-00002.safetensors").read_bytes()
    b = (copy / "model-00002-of-00002.safetensors").read_bytes()
    assert [i for i in range(len(a)) if a[i] != b[i]] == [len(a) - 16 + 2]
    assert (copy / "config.json").read_bytes() == (models / "config.json").read_bytes()
