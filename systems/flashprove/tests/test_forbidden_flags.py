"""RFC-0005 §Weakening configurations: an option that gives up FlashProve's weight hiding is
refused before any upstream process starts, unless the job is a control job."""

import json
from types import ModuleType

import flashprove_stubs
import pytest
from flashprove_stubs import TOKENS, commands, job, run

adapter = flashprove_stubs.adapter  # the fixture


def test_forbidden_flags_listed(adapter: ModuleType) -> None:
    assert adapter.FORBIDDEN_FLAGS == ["-public-weights", "-keep-for-the-audit"]


def prove_job(adapter: ModuleType, flags: list[str], control: bool) -> dict[str, object]:
    out = run(adapter, "commit", job("commit", model_dir="/models"))
    rows = [[i + 1] + [7] * (TOKENS - 1) for i in range(2)]
    adapter.host("/io/prompts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return job("prove", commitment_id=out["commitment_id"], prover_files=out["prover_files"],
               model_dir="/models", prompts_file="/io/prompts.jsonl", batch_size=1, batches=2,
               control=control, control_flags=flags)  # fmt: skip


@pytest.mark.parametrize("flag", ["-public-weights", "-keep-for-the-audit"])
def test_forbidden_flags_guarded(adapter: ModuleType, flag: str) -> None:
    doc = prove_job(adapter, [flag, "/io/seed.bin"], control=False)
    with pytest.raises(SystemExit, match="outside a control job"):
        run(adapter, "prove", doc)
    assert [c["argv"][0].rsplit("/", 1)[1] for c in commands(adapter)] == ["cp_commit"]


def test_control_job_passes_flags(adapter: ModuleType) -> None:
    out = run(adapter, "prove", prove_job(adapter, ["-public-weights", "/io/s"], control=True))
    assert len(out["proofs"]) == 2
    assert commands(adapter)[-1]["argv"][-2:] == ["-public-weights", "/io/s"]
