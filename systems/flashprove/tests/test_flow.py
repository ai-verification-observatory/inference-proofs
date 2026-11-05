"""commit, prove and verify end to end on CPU, with upstream's three programs replaced by the
stand-ins of flashprove_stubs.py, and the harness's handling of the commitment record imitated
(RFC-0014 §The commitment record: copies, prover files read-only, a fresh io dir for verify)."""

import json
import os
import shutil
import tarfile
from pathlib import Path
from types import ModuleType
from typing import Any

import flashprove_stubs
import pytest
from flashprove_stubs import COMMITMENT_ID, TOKENS, commands, job, run

adapter = flashprove_stubs.adapter  # the fixture


def prompts(adapter: ModuleType, count: int, first: int = 1) -> list[list[int]]:
    rows = [[first + i] + [7] * (TOKENS - 1) for i in range(count)]
    path = adapter.host("/io/prompts.jsonl")
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return rows


def commit(adapter: ModuleType) -> dict[str, Any]:
    out = run(adapter, "commit", job("commit", model_dir="/models"))
    adapter.host("/io/state/isk.tar").chmod(0o444)  # the harness mounts it read-only
    return out


def prove(adapter: ModuleType, out: dict[str, Any], **fields: Any) -> dict[str, Any]:
    return run(adapter, "prove", job("prove", commitment_id=out["commitment_id"],
               prover_files=out["prover_files"], model_dir="/models",
               prompts_file="/io/prompts.jsonl", batch_size=fields.pop("size", 2),
               batches=fields.pop("batches", 3), **fields))  # fmt: skip


def test_commit(adapter: ModuleType) -> None:
    out = commit(adapter)
    assert out["commitment_id"] == COMMITMENT_ID
    assert out["verifier_files"] == [
        "/io/state/commit/config/policy.txt",
        "/io/state/commit/config/KL.bin",
        "/io/state/commit/config/layout.txt",
        "/io/state/commit/ivk/key.bin",
        "/io/state/commit/ivk/leaf/0.bin",
    ]
    assert out["prover_files"] == ["/io/state/isk.tar"]
    names = [Path(f).name for f in out["verifier_files"] + out["prover_files"]]
    assert len(set(names)) == len(names)  # the harness's store keeps files by name
    tar_path = adapter.host("/io/state/isk.tar")
    assert out["sizes"] == {"verifier_bytes": 10 + 6 + 10 + 3 + 4,
                            "prover_bytes": tar_path.stat().st_size}  # fmt: skip
    with tarfile.open(tar_path) as tar:
        assert {"isk/seed.bin", "isk/leaf/0/count.bin", "isk/anchor/count.bin"} <= set(
            tar.getnames()
        )
    assert not adapter.host("/io/state/commit/isk").exists()  # prove uses the record only
    [command] = commands(adapter)
    assert command["argv"][1:] == [
        "-weights", str(adapter.host("/models/UD-Q4_K_XL")),
        "-config", str(adapter.host("/io/state/commit/config")), "-M", "1",
        "-ivk", str(adapter.host("/io/state/commit/ivk")),
        "-isk", str(adapter.host("/io/state/commit/isk")),
    ]  # fmt: skip
    assert command["exit_code"] == 0


def test_commit_refuses_another_fit(adapter: ModuleType) -> None:
    """The fit must have upstream's published digests (examples/maverick/expected.txt)."""
    adapter.host("/models/flashprove-config/KL.bin").write_text("other scales")
    with pytest.raises(SystemExit, match=r"not the published config/KL\.bin"):
        commit(adapter)
    assert commands(adapter) == []


def test_flow(adapter: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = prompts(adapter, 7)  # one more than the job uses
    committed = commit(adapter)
    out = prove(adapter, committed)
    assert [p["request_index"] for p in out["proofs"]] == list(range(6))
    assert [p["claimed_output"] for p in out["proofs"]] == [[r[0]] for r in rows[:6]]
    proofs = adapter.host("/io/proofs")
    assert sorted(p.name for p in proofs.iterdir()) == [f"req-{i}" for i in range(6)]  # no .tmp-
    assert sorted(os.listdir(proofs / "req-0")) == ["response.proof", "response.y"]
    prove_call = commands(adapter)[-1]
    assert prove_call["argv"][1:] == [
        "-isk", str(adapter.host("/io/state/prove/isk")),
        "-spool", str(adapter.host("/io/state/prove/spool")),
        "-batch", "2", "-in-step", "2", "-most-batches", "3", "-memory", "lean,tensor-rooms=8",
    ]  # fmt: skip
    # verify in a fresh io dir holding only copies of the recorded verifier files
    fresh = tmp_path / "verify-io"
    (fresh / "verifier").mkdir(parents=True)
    for f in committed["verifier_files"]:
        shutil.copyfile(adapter.host(f), fresh / "verifier" / Path(f).name)
    shutil.copytree(proofs / "req-4", fresh / "proof")
    monkeypatch.setenv("IPROOFS_IO", str(fresh))
    names = [f"/io/verifier/{Path(f).name}" for f in committed["verifier_files"]]
    fields = {"commitment_id": COMMITMENT_ID, "verifier_files": names, "request": rows[4],
              "proof_dir": "/io/proof"}  # fmt: skip
    good = run(adapter, "verify", job("verify", claimed_output=[rows[4][0]], **fields))
    assert (good["verdict"], good["policy"], good["raw_last_line"]) == (
        "accept",
        "exact-match",
        "YES",
    )
    bad = run(adapter, "verify", job("verify", claimed_output=[rows[4][0] + 1], **fields))
    assert (bad["verdict"], bad["raw_exit_code"], bad["raw_last_line"]) == (
        "reject",
        1,
        "NO: statement",
    )
    [call, _] = commands(adapter)
    assert call["argv"][6:] == ["-id", COMMITMENT_ID, "-next-token", "-j", call["argv"][-1]]


def test_prove_wrong_prompt_length(adapter: ModuleType) -> None:
    committed = commit(adapter)
    adapter.host("/io/prompts.jsonl").write_text("[1, 2]\n" * 6)
    with pytest.raises(SystemExit, match=r"need 6 prompts of 8 token ids"):
        prove(adapter, committed)


def test_prove_failed_request(adapter: ModuleType) -> None:
    """A request that cp_prove answers with <id>.failed makes prove fail, with what was seen."""
    committed = commit(adapter)
    prompts(adapter, 2, first=998)  # the second one is 999: the stand-in fails it
    with pytest.raises(SystemExit, match=r"exited 0, last line 'p258 end 0'; failed \[1\]"):
        prove(adapter, committed, size=1, batches=2)
    assert [p.name for p in adapter.host("/io/proofs").iterdir()] == ["req-0"]


def test_prove_bad_exit(adapter: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    committed = commit(adapter)
    prompts(adapter, 6)
    monkeypatch.setenv("STUB_PROVE_EXIT", "1")
    with pytest.raises(SystemExit, match=r"cp_prove exited 1, last line 'p258 end 1'"):
        prove(adapter, committed)
    assert commands(adapter)[-1]["exit_code"] == 1
