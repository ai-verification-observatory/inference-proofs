import pytest

from iproofs.errors import ErrorKind, Failure, IProofsError, exit_code

# RFC-0010 §Error taxonomy, exit column.
EXPECTED = {
    ("config", "validate"): 1,
    ("config", "preflight"): 2,
    ("environment", "preflight"): 3,
    ("environment", "job"): 3,
    ("integrity", "job"): 4,
    ("integrity", "validate"): 1,
    ("fetch", "job"): 4,
    ("adapter", "job"): 4,
    ("timeout", "job"): 4,
    ("resource", "job"): 4,
    ("policy", "job"): 4,
    ("policy", "validate"): 1,
    ("internal", "job"): 5,
    ("internal", "validate"): 5,
}


@pytest.mark.parametrize(("kind", "phase"), EXPECTED)
def test_exit_code_table(kind: str, phase: str) -> None:
    assert exit_code(ErrorKind(kind), phase) == EXPECTED[(kind, phase)]  # type: ignore[arg-type]


def test_kinds_are_exactly_the_taxonomy() -> None:
    assert {k.value for k in ErrorKind} == {
        "config", "environment", "integrity", "fetch", "adapter",
        "timeout", "resource", "policy", "internal",
    }  # fmt: skip


@pytest.mark.parametrize("verdict", ["accept", "reject", "no_verdict", "invalid_call"])
def test_verdicts_are_not_error_kinds(verdict: str) -> None:
    assert verdict not in {k.value for k in ErrorKind}


def test_last_lines_keeps_last_50() -> None:
    lines = [f"line {i}" for i in range(80)]
    failure = Failure.build(ErrorKind.ADAPTER, "prove", "boom", last_lines=lines)
    assert failure.last_lines == tuple(lines[30:])


def test_message_truncated_to_4096_bytes() -> None:
    failure = Failure.build(ErrorKind.INTERNAL, "commit", "é" * 3000)  # 6000 bytes
    assert len(failure.message.encode("utf-8")) <= 4096
    assert failure.message == "é" * 2048


def test_from_error_prefers_error_step_and_serialises() -> None:
    err = IProofsError(ErrorKind.TIMEOUT, "prove exceeded 43200 s", step="prove", exit_code=137)
    failure = Failure.from_error(err, step="commit", at="2026-11-03T10:00:00Z")
    assert failure.to_json() == {
        "kind": "timeout",
        "step": "prove",
        "message": "prove exceeded 43200 s",
        "exit_code": 137,
        "last_lines": [],
        "at": "2026-11-03T10:00:00Z",
    }


def test_default_timestamp_is_utc_rfc3339() -> None:
    at = Failure.build(ErrorKind.FETCH, "resolved", "x").at
    assert at.endswith("Z")
    assert "T" in at
