"""RFC-0005 §Verdict normalisation for FlashProve (INV-ADAPTER-9): every exit code that
verifier/docs/output.md documents, and an undocumented one, which is an adapter failure."""

from types import ModuleType

import flashprove_stubs
import pytest
from flashprove_stubs import COMMITMENT_ID, job, run

adapter = flashprove_stubs.adapter  # the fixture

CASES = [
    (0, "YES", "accept", "exact-match"),
    (0, "WITHIN LIMITS: clipped-gap C=256 theta=256 cap=0 s=16 sh=8", "accept", "clipped-gap"),
    (1, "NO: statement", "reject", None),
    (2, "input-unreadable-proof: x cannot be read: No such file", "invalid_call", None),
    (3, "PART PASSED: key", "invalid_call", None),
    (4, "PLAN ONLY: no proof was checked", "invalid_call", None),
    (5, "NOT CHECKED: internal-stage", "no_verdict", None),
    (14, "NOT-A-VERIFICATION", "invalid_call", None),
    (15, "", "invalid_call", None),
]


@pytest.mark.parametrize(("code", "line", "verdict", "policy"), CASES)
def test_verdict_map(
    adapter: ModuleType, code: int, line: str, verdict: str, policy: str | None
) -> None:
    assert adapter.verdict(code, line) == (verdict, policy)


@pytest.mark.parametrize(("code", "line"), [(7, "NO: statement"), (0, "NO: statement"), (-9, "")])
def test_undocumented_ending_fails(adapter: ModuleType, code: int, line: str) -> None:
    """Exit 7, exit 0 without an accepting line, and a signal: never a guessed verdict."""
    with pytest.raises(SystemExit, match="not documented"):
        adapter.verdict(code, line)


def verify_job(adapter: ModuleType) -> dict[str, object]:
    io = adapter.host("/io")
    names = ("policy.txt", "KL.bin", "layout.txt", "key.bin", "0.bin")
    for d in ("verifier", "proof"):
        (io / d).mkdir()
    for name in names:
        (io / "verifier" / name).write_bytes(b"x")
    (io / "proof/response.proof").write_bytes(b"p")
    files = [f"/io/verifier/{n}" for n in names]
    return job("verify", commitment_id=COMMITMENT_ID, verifier_files=files,
               request=list(range(8)), claimed_output=[3], proof_dir="/io/proof")  # fmt: skip


@pytest.mark.parametrize(("code", "line", "verdict", "policy"), CASES)
def test_verify_out_json(
    adapter: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    code: int,
    line: str,
    verdict: str,
    policy: str | None,
) -> None:
    """Through the stand-in cp_verify: raw exit code and last line kept, policy only on accept."""
    monkeypatch.setenv("STUB_VERIFY", f"{code}:{line}")
    out = run(adapter, "verify", verify_job(adapter))
    assert (out["verdict"], out.get("policy")) == (verdict, policy)
    assert out["raw_exit_code"] == code
    assert out["raw_last_line"] == (line or "some progress line")


def test_verify_undocumented_exit(adapter: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUB_VERIFY", "7:NO: statement")
    with pytest.raises(SystemExit, match="exit 7"):
        run(adapter, "verify", verify_job(adapter))
    assert not adapter.host("/io/out.json").exists()
