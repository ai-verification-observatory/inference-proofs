"""Level 1 (RFC-0018) on CPU: the worker's argv, the prompt as text and the token check, five
requests a session with one proof released per request, the end token, the commit and verify
wiring (verify refuses: AGENTS.md rule 6), and C1's mutation. Every upstream process is
deepprove_stub.py, whose proof files follow the layout README.md §Proof file reads."""

import json
from pathlib import Path
from types import ModuleType
from typing import Any

import deepprove_stub as stub
import pytest
from deepprove_fixtures import commands, load, run_step, vocab

from iproofs.adapter import check_requests
from iproofs.errors import IProofsError
from iproofs.model import AdapterOut

SPACE = 220  # GPT-2's "Ġ", the single-byte token of b" "
PROMPTS = [[SPACE if k % 7 == 6 else (i * 13 + k) % 94 for k in range(512)] for i in range(5)]


@pytest.fixture
def adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    return load(tmp_path, monkeypatch)


def session(adapter: ModuleType, prompts: list[list[int]] = PROMPTS) -> dict[str, Any]:
    adapter.host("/io/prompts.jsonl").write_text("".join(json.dumps(p) + "\n" for p in prompts))
    c = run_step(adapter, "commit", model_dir="/models")
    p = run_step(adapter, "prove", commitment_id=c["commitment_id"], model_dir="/models",
                 prover_files=c["prover_files"], prompts_file="/io/prompts.jsonl",
                 batch_size=1, batches=len(prompts))  # fmt: skip
    return {"commit": c, "prove": p}


# ------------------------------------------------------------------ prompt text


def test_byte_alphabet_matches_gpt2() -> None:
    """bytes_to_unicode: 256 characters; space is Ġ (U+0120), newline Ċ (U+010A), NUL Ā."""
    dec = vocab()
    assert len([t for t, i in dec.items() if i < 256]) == 256
    assert (dec["Ġ"], dec["Ċ"], dec["Ā"], dec["!"]) == (220, 198, 188, 0)


def test_prompt_text_hand_case(adapter: ModuleType) -> None:
    """GPT-2's vocabulary reads [15496, 995] as "Hello world"."""
    assert adapter.prompt_text([15496, 995], "/models/vocab.json") == "Hello world"
    assert adapter.prompt_text([15496, 50256], "/models/vocab.json") == "Hello<|endoftext|>"


def test_prompt_text_refuses_a_cut_character(adapter: ModuleType) -> None:
    """A window that ends inside a UTF-8 character (here 0xE2 alone) cannot be a string."""
    e2 = adapter.byte_decoder()  # character -> byte; the id of byte 0xE2 is its vocab index
    ids = json.loads(adapter.host("/models/vocab.json").read_text())
    cut = ids[next(c for c, b in e2.items() if b == 0xE2)]
    with pytest.raises(SystemExit, match="not UTF-8"):
        adapter.prompt_text([15496, cut], "/models/vocab.json")
    nul = ids[next(c for c, b in e2.items() if b == 0)]
    with pytest.raises(SystemExit, match="NUL"):
        adapter.prompt_text([15496, nul], "/models/vocab.json")


def test_worker_argv(adapter: ModuleType) -> None:
    """worker/main.rs L203-L205 and L277-L332 at the pin; nothing else is passed."""
    assert adapter.worker_argv("-x y", 512) == [
        "/usr/local/bin/deep-prove-worker", "--tensor-store", "temporary", "one-shot",
        "--model", "/models/model.safetensors", "--model-format", "safetensors",
        "--tokenizer", "/models/tokenizer.json", "--config", "/models/config.json",
        "--max-new-tokens", "512", "--prompt=-x y"]  # fmt: skip


# ------------------------------------------------------------------ session


def test_one_commit_five_proofs_each_with_its_reply(adapter: ModuleType) -> None:
    done = session(adapter)
    proofs = done["prove"]["proofs"]
    assert [p["proof_id"] for p in proofs] == [f"req-{i}" for i in range(5)]
    for i, p in enumerate(proofs):
        assert p["parts"] == ["proof.bin"]
        assert p["claimed_output"] == stub.reply_of(PROMPTS[i], 512)
        assert adapter.host(f"/io/proofs/req-{i}/proof.bin").is_file()
    assert done["prove"]["warnings"] == []
    assert not list(adapter.host("/io/proofs").glob(".tmp-*"))
    workers = commands(adapter)
    assert len(workers) == 5
    for argv, prompt in zip(workers, PROMPTS, strict=True):
        assert argv[argv.index("--max-new-tokens") + 1] == "512"
        text = argv[-1].removeprefix("--prompt=")
        assert [stub.byte_ids()[b] for b in text.encode()] == prompt
    check_requests(AdapterOut.from_tree(done["prove"]), 512)  # RFC-0017 INV-REQ-2


def test_prove_refuses_a_proof_of_other_tokens(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Upstream tokenizes the text itself; when its tokens are not the request's, the proof is
    of another prompt and is not released."""
    monkeypatch.setenv("IPROOFS_DEEPPROVE_STUB_DROP", "1")
    with pytest.raises(SystemExit, match=r"request 0: upstream tokenized .* from position 0"):
        session(adapter)
    assert not adapter.host("/io/proofs/req-0").exists()


def test_end_token_shortens_the_reply_and_coverage_fails(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The worker stops at 50256 (llm.rs L476-L481): the proof claims 100 tokens, prove says so,
    and the harness's coverage check refuses the request (RFC-0017 INV-REQ-2)."""
    monkeypatch.setenv("IPROOFS_DEEPPROVE_STUB_EOS", "100")
    done = session(adapter, PROMPTS[:1])
    (proof,) = done["prove"]["proofs"]
    assert proof["claimed_output"] == stub.reply_of(PROMPTS[0], 100)
    assert "stops after 100 of 512 tokens" in done["prove"]["warnings"][0]
    with pytest.raises(IProofsError, match="INV-REQ-2"):
        check_requests(AdapterOut.from_tree(done["prove"]), 512)


def test_control_flags_refused(adapter: ModuleType) -> None:
    adapter.host("/io/prompts.jsonl").write_text(json.dumps(PROMPTS[0]) + "\n")
    with pytest.raises(SystemExit, match="no control flag exists"):
        run_step(adapter, "prove", commitment_id="sha256:x", model_dir="/models",
                 prover_files=[], prompts_file="/io/prompts.jsonl", batch_size=1, batches=1,
                 control=True, control_flags=["--anything"])  # fmt: skip
    assert commands(adapter) == []


# ------------------------------------------------------------------ commit and verify


def test_commit_records_the_model_files_and_no_key(adapter: ModuleType) -> None:
    c = run_step(adapter, "commit", model_dir="/models")
    assert c["verifier_files"] == ["/io/state/commit.json"]
    assert c["prover_files"] == []
    record = json.loads(adapter.host("/io/state/commit.json").read_text())
    assert record["verifier_key"] is None
    assert sorted(record["model_files"]) == sorted(adapter.MODEL_FILES)
    assert c["commitment_id"] == adapter.commitment_of(c["verifier_files"])


def verify_job(c: dict[str, Any], **over: Any) -> dict[str, Any]:
    return {"commitment_id": c["commitment_id"], "verifier_files": c["verifier_files"],
            "request": PROMPTS[0], "claimed_output": stub.reply_of(PROMPTS[0], 512),
            "proof_dir": "/io/proofs/req-0", **over}  # fmt: skip


def test_verify_refuses_before_any_upstream_process(adapter: ModuleType) -> None:
    """AGENTS.md rule 6: deep-prove-cli verify reads the key from the proof file only."""
    c = session(adapter, PROMPTS[:1])["commit"]
    before = len(commands(adapter))
    with pytest.raises(SystemExit, match=r"verify refused .* rule 6") as e:
        run_step(adapter, "verify", **verify_job(c))
    assert "cli/main.rs L221-L235" in str(e.value)
    assert len(commands(adapter)) == before


def test_verify_checks_the_record_first(adapter: ModuleType) -> None:
    c = session(adapter, PROMPTS[:1])["commit"]
    with pytest.raises(SystemExit, match="do not match commitment_id"):
        run_step(adapter, "verify", **verify_job(c, commitment_id="sha256:" + "1" * 64))
    with pytest.raises(SystemExit, match="are not commit's"):
        run_step(adapter, "verify", **verify_job(c, verifier_files=["/io/state/other.json"]))


# ------------------------------------------------------------------ C1 (RFC-0018 AD-6)


def mutate(adapter: ModuleType, position: int, token: int) -> dict[str, Any]:
    return run_step(adapter, "mutate_reply", proof_dir="/io/proofs/req-2", position=position,
                    token=token, out_dir="/io/mutated")  # fmt: skip


@pytest.mark.parametrize("position", [0, 511, 200])  # C1: first, last, interior reply token
def test_mutate_reply_changes_two_elements_and_nothing_else(adapter: ModuleType,
                                                            position: int) -> None:  # fmt: skip
    session(adapter)
    out = mutate(adapter, position, 7777)
    i = 512 + position
    assert out["mutated"] == {"parts": ["proof.bin"],
                              "fields": [f"proof.bin io.input[0][{i}]",
                                         f"proof.bin io.output[0][{i - 1}]"]}  # fmt: skip
    before = adapter.host("/io/proofs/req-2/proof.bin").read_bytes()
    after = adapter.host("/io/mutated/proof.bin").read_bytes()
    head = adapter.read_head(before)
    io = adapter.read_io(before, head.tokens, head.end)
    old = stub.reply_of(PROMPTS[2], 512)[position]
    assert io.input[i] == io.output[i - 1] == old
    expected = bytearray(before)
    for slot in (io.input_at + 33 * i, io.output_at + 33 * (i - 1)):
        assert expected[slot] == 32  # the element's length byte stays
        expected[slot + 1 : slot + 33] = (7777).to_bytes(32, "little")
    assert after == bytes(expected)
    mutated = adapter.read_io(after, head.tokens, head.end)
    assert mutated.input[i] == mutated.output[i - 1] == 7777
    assert adapter.read_head(after) == head  # the prompt and the logging text are untouched


def test_mutate_reply_refuses_a_position_past_the_reply(adapter: ModuleType) -> None:
    session(adapter)
    with pytest.raises(SystemExit, match="outside the reply's 512 tokens"):
        mutate(adapter, 512, 1)


def test_read_io_refuses_an_unexpected_layout(adapter: ModuleType) -> None:
    session(adapter, PROMPTS[:1])
    buf = adapter.host("/io/proofs/req-0/proof.bin").read_bytes()
    head = adapter.read_head(buf)
    with pytest.raises(SystemExit, match="exactly once"):
        adapter.read_io(buf, [1, *head.tokens[1:]], head.end)
    twice = buf + buf[adapter.read_io(buf, head.tokens, head.end).input_at - 4 :]
    with pytest.raises(SystemExit, match="exactly once"):
        adapter.read_io(twice, head.tokens, head.end)
