"""Level 1 (RFC-0018 AD-1, AD-3) on CPU: the request's window and range, the integer model's own
replies before cp_prove, and verify on the whole reply. Upstream's programs and the integer model
are the stand-ins of flashprove_stubs.py; the window is T = 16 (`lt 4`) in place of 1,024."""

import json
import shutil
from pathlib import Path
from types import ModuleType
from typing import Any

import flashprove_stubs
import pytest
from flashprove_stubs import COMMITMENT_ID, commands, greedy, job, run

adapter = flashprove_stubs.adapter  # the fixture
P, R = 8, 8  # prompt and reply; P + R = T, so no filler
SHAPE = {"prompt_tokens": P, "output_tokens": R, "batch_size": 2, "batches_per_session": 2,
         "context_window": P + R}  # fmt: skip


def test_window_and_range_at_level_1(adapter: ModuleType) -> None:
    """512 + 512 in a window of 1,024: no filler, r = 511, e = 1,023 (verifying.md L119-127)."""
    words = adapter.request_words(list(range(1, 513)), list(range(600, 1112)), 1024)
    assert len(words) == 1026
    assert words[:1024] == [*range(1, 513), *range(600, 1112)]
    assert words[1024:] == [511, 1023]


def test_window_with_filler(adapter: ModuleType) -> None:
    """The example of verifier/docs/output.md L366-368: T = 64, 10 prompt and 5 reply ids, the
    filler 49 times, then 9 and 14 (66 words)."""
    words = adapter.request_words(list(range(10)), [7] * 5, 64)
    assert len(words) == 66
    assert words[15:64] == [0] * 49
    assert words[64:] == [9, 14]


def test_window_too_small(adapter: ModuleType) -> None:
    with pytest.raises(SystemExit, match="do not fit a window of 1024"):
        adapter.request_words([1] * 512, [2] * 513, 1024)


def test_window_from_the_parameter_file(adapter: ModuleType, tmp_path: Path) -> None:
    (tmp_path / "policy.txt").write_text("s 16\nlt 10\nsh 8\n")
    assert adapter.window_of(tmp_path / "policy.txt") == 1024
    (tmp_path / "policy.txt").write_text("s 16\n")
    with pytest.raises(SystemExit, match="0 lines `lt`"):
        adapter.window_of(tmp_path / "policy.txt")


def level1(adapter: ModuleType) -> tuple[list[list[int]], dict[str, Any]]:
    """Prompts, policy.txt with `lt 4`, and the commitment."""
    adapter.host("/io/fit/config/policy.txt").write_text("lt 4\n")
    rows = [[i + 1] + [7] * (P - 1) for i in range(5)]  # one more than the job uses
    adapter.host("/io/prompts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    out = run(adapter, "commit", job("commit", model_dir="/models", shape=SHAPE))
    adapter.host("/io/state/isk.tar").chmod(0o444)
    return rows, out


def prove(adapter: ModuleType, committed: dict[str, Any]) -> dict[str, Any]:
    return run(adapter, "prove", job("prove", commitment_id=committed["commitment_id"],
               prover_files=committed["prover_files"], model_dir="/models",
               prompts_file="/io/prompts.jsonl", batch_size=2, batches=2, shape=SHAPE))  # fmt: skip


def test_prove_generates_then_proves_the_whole_reply(adapter: ModuleType) -> None:
    rows, committed = level1(adapter)
    out = prove(adapter, committed)
    replies = [greedy(r, R) for r in rows[:4]]
    assert [p["claimed_output"] for p in out["proofs"]] == replies
    assert [p["name"] for p in out["phases"]] == ["float64_check", "generate", "cp_prove"]
    check, generate, cp_prove = commands(adapter)[1:]
    assert check["argv"][1:] == ["-B", "-m", "pytest", "-p", "no:cacheprovider", "-rs",
                                 "tests/test_arithmetic_edges.py"]  # fmt: skip
    assert check["cwd"].endswith("/src/integrations/vllm/integer_model")
    assert generate["argv"][1:3] == ["-B", "-c"]
    assert generate["argv"][6:8] == ["4", str(R)]  # four prompts, replies of R tokens
    assert sorted(json.loads(generate["argv"][-1])["sha256"]) == [
        "KL.bin", "fold.txt", "integer_model.json", "policy.txt", "wsums.txt"]  # fmt: skip
    assert cp_prove["argv"][0].endswith("/cp_prove")
    spec = json.loads(adapter.host("/io/state/prove/integer-model/integer_model.json").read_text())
    assert spec["weight_settings"]["verify_sums"] is True
    # each request laid for cp_prove: prompt, reply, r = P - 1, e = P + R - 1, a 32-byte nonce
    laid = sorted(adapter.host("/io/state/prove/spool/in").glob("*.req"))
    words = sorted(
        [int.from_bytes(b[i : i + 4], "little") for i in range(0, len(b) - 32, 4)]
        for b in (p.read_bytes() for p in laid)
    )
    assert words == sorted([*r, *g, P - 1, P + R - 1] for r, g in zip(rows, replies, strict=False))


def test_float64_check_with_a_skip_stops_prove(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OPERATING.md: every test should pass and none be skipped, or the GPU does not serve."""
    _, committed = level1(adapter)
    monkeypatch.setenv("STUB_FLOAT64", "==== 8 passed, 4 skipped in 0.50s ====")
    with pytest.raises(SystemExit, match="float64 check"):
        prove(adapter, committed)
    assert len(commands(adapter)) == 2  # cp_commit and the check; no generation, no cp_prove


def test_reply_longer_than_the_window_is_refused(adapter: ModuleType) -> None:
    _, committed = level1(adapter)
    adapter.host("/io/fit/config/policy.txt").write_text("lt 3\n")  # T = 8 < P + R
    with pytest.raises(SystemExit, match="do not fit a window of 8"):
        prove(adapter, committed)
    assert len(commands(adapter)) == 1


@pytest.mark.parametrize("position", [0, R - 1, 3])  # C1: first, last, interior reply token
def test_verify_checks_every_reply_token(
    adapter: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, position: int
) -> None:
    rows, committed = level1(adapter)
    out = prove(adapter, committed)
    reply = out["proofs"][1]["claimed_output"]
    fresh = tmp_path / "verify-io"
    (fresh / "verifier").mkdir(parents=True)
    for f in committed["verifier_files"]:
        shutil.copyfile(adapter.host(f), fresh / "verifier" / Path(f).name)
    shutil.copytree(adapter.host("/io/proofs/req-1"), fresh / "proof")
    monkeypatch.setenv("IPROOFS_IO", str(fresh))
    names = [f"/io/verifier/{Path(f).name}" for f in committed["verifier_files"]]
    fields = {"commitment_id": COMMITMENT_ID, "verifier_files": names, "request": rows[1],
              "proof_dir": "/io/proof", "shape": SHAPE}  # fmt: skip
    good = run(adapter, "verify", job("verify", claimed_output=reply, **fields))
    assert (good["verdict"], good["policy"]) == ("accept", "exact-match")
    changed = list(reply)
    changed[position] = (changed[position] + 1) % 1000
    bad = run(adapter, "verify", job("verify", claimed_output=changed, **fields))
    assert (bad["verdict"], bad["raw_exit_code"]) == ("reject", 1)
    call = commands(adapter)[0]
    assert "-next-token" not in call["argv"]
    assert call["argv"][6:8] == ["-id", COMMITMENT_ID]
