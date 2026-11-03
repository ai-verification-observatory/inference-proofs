import json
from pathlib import Path

import pytest

from iproofs.adapter import InProcessRunner, StepResult
from iproofs.errors import ErrorKind, IProofsError
from iproofs.runner import JobSpec, Runner, retry_fetch
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
FAKE = ROOT / "systems/fake"


def failing(kind: ErrorKind, times: int) -> tuple[list[int], object]:
    calls: list[int] = []

    def op() -> str:
        calls.append(1)
        if len(calls) <= times:
            raise IProofsError(kind, "network unreachable")
        return "ok"

    return calls, op


def test_fetch_retries_three_times_with_backoff() -> None:
    sleeps: list[float] = []
    calls, op = failing(ErrorKind.FETCH, 2)
    assert retry_fetch(op, "weights", sleep=sleeps.append) == "ok"  # type: ignore[arg-type]
    assert (len(calls), sleeps) == (3, [2.0, 8.0])


def test_fetch_gives_up_after_three_attempts() -> None:
    sleeps: list[float] = []
    calls, op = failing(ErrorKind.FETCH, 5)
    with pytest.raises(IProofsError) as e:
        retry_fetch(op, "weights", sleep=sleeps.append)  # type: ignore[arg-type]
    assert e.value.kind is ErrorKind.FETCH
    assert (len(calls), sleeps) == (3, [2.0, 8.0])


def test_other_kinds_never_retry() -> None:
    sleeps: list[float] = []
    calls, op = failing(ErrorKind.INTEGRITY, 5)
    with pytest.raises(IProofsError):
        retry_fetch(op, "weights", sleep=sleeps.append)  # type: ignore[arg-type]
    assert (len(calls), sleeps) == (1, [])


def test_no_retry_of_timed_steps(tmp_path: Path) -> None:
    """INV-RUN-1: a failing prove is called once; the next repetition is a new job."""
    calls: list[str] = []
    env = {
        "IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78",
        "IPROOFS_FAKE_DELAY_S": "0",
    }
    inner = InProcessRunner(FAKE / "entrypoint", REGISTRY, env=env)

    class FailProve:
        def run(self, image: str, subcommand: str, io_dir: Path, **kw: object) -> StepResult:
            calls.append(subcommand)
            result = inner.run(image, subcommand, io_dir, **kw)  # type: ignore[arg-type]
            if subcommand == "prove":
                return StepResult("prove", 0, 1, 1, None, ())
            return result

    runner = Runner(
        FailProve(), root=ROOT, registry=REGISTRY, image="local/in-process@sha256:" + "0" * 64
    )
    dirs = runner.run_many(
        JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, False, str(tmp_path), "v0.1"), 2
    )
    assert calls.count("prove") == 2  # once per repetition, never retried
    assert [json.loads((d / "run.json").read_text())["status"] for d in dirs] == [
        "failed",
        "failed",
    ]
