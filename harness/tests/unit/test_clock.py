import json
import os
import sys
from pathlib import Path

import pytest

from iproofs import adapter
from iproofs.adapter import DockerRunner
from iproofs.derive import scope_seconds
from iproofs.measure import CallTiming, EventLog, pin_harness_cpu, span_seconds, timed_call
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
FAKE = ROOT / "systems/fake"
IMAGE = "ghcr.io/example/iproofs-fake@sha256:" + "a" * 64
JOB = {
    "schema": "adapter-job/1",
    "contract": "adapter/1",
    "run_id": "2026-11-20-fake-fake-tiny-ci-ci-cpu-1",
    "workload": {"id": "fake-tiny-ci", "version": 1},
    "control": False,
    "shape": {
        "prompt_tokens": 8,
        "output_tokens": 1,
        "batch_size": 2,
        "batches_per_session": 3,
        "context_window": 8,
    },
}


@pytest.fixture
def fake_docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "docker-state"
    state.mkdir()
    bin_dir = ROOT / "harness/tests/fixtures/fake-docker"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_DOCKER_STATE", str(state))
    monkeypatch.setenv("FAKE_DOCKER_ENTRYPOINT", str(FAKE / "entrypoint"))
    monkeypatch.setenv("IPROOFS_FAKE_DELAY_S", "0")
    return state


def test_span() -> None:
    """TC-SPAN."""
    assert span_seconds(2_000_000_000, 3_500_000_000) == 1.5


def test_timed_window_excludes_create(
    tmp_path: Path, fake_docker: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_DOCKER_CREATE_DELAY_S", "1")
    io = tmp_path / "io"
    io.mkdir()
    (io / "job.json").write_text(json.dumps({**JOB, "subcommand": "info"}))
    argv = ["docker", "create", "-v", f"{io}:/io:rw", IMAGE, "info", "/io/job.json", "/io/out.json"]
    call = timed_call(argv, timeout_s=30)
    assert call.exit_code == 0
    assert span_seconds(call.start_ns, call.end_ns) < 1.0  # the 1 s create is outside


def test_docker_runner_end_to_end_and_container_id_never_written(
    tmp_path: Path, fake_docker: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-3: the container id is used for the call only and never reaches a written file."""
    io = tmp_path / "io"
    io.mkdir()
    (io / "job.json").write_text(
        json.dumps({**JOB, "subcommand": "commit", "model_dir": "/models"})
    )
    ids: list[str] = []

    def recording(*args: object, **kw: object) -> CallTiming:
        call = timed_call(*args, **kw)  # type: ignore[arg-type]
        ids.append(call.container_id)
        return call

    monkeypatch.setattr(adapter, "timed_call", recording)
    runner = DockerRunner(SchemaRegistry.from_tree(ROOT / "schema"))
    result = runner.run(
        IMAGE,
        "commit",
        io,
        models_dir=FAKE / "model",
        gpu=None,
        cpuset="0",
        mems="0",
        memory=None,
        timeout_s=30,
    )
    assert result.exit_code == 0
    assert result.out is not None
    assert len(ids) == 1
    assert list(fake_docker.iterdir()) == []  # the container was removed
    written = [p.read_text(errors="ignore") for p in io.rglob("*") if p.is_file()]
    assert all(ids[0] not in text for text in written)
    assert ids[0] not in repr(result)


def test_event_log_recomputes_every_scope() -> None:
    ticks = iter(range(0, 10**12, 10**9))
    log = EventLog(clock=lambda: next(ticks))
    for name in [
        "info.start",
        "info.end",
        "setup.start",
        "setup.end",
        "commit.start",
        "commit.end",
        "prove.start",
        "proof.released",
        "proof.released",
        "proof.released",
        "prove.end",
    ]:
        log.record(name)
    run = {"events": log.events}
    events = EventLog(events=run["events"])  # only the stored list is needed
    out = scope_seconds(events.first(), events.releases(), observable=True, run_json="r/run.json")
    assert {k: v["value"] for k, v in out.items()} == {
        "info_seconds": 1.0,
        "setup_seconds": 1.0,
        "commit_seconds": 1.0,
        "prove_call_seconds": 4.0,
        "prove_session_seconds": 3.0,
        "whole_wall_seconds": 5.0,
        "prove_steady_seconds": 2.0,
    }


def test_pin_harness_cpu() -> None:
    if not sys.platform.startswith("linux"):
        assert pin_harness_cpu({0, 1}) is None
        return
    before = os.sched_getaffinity(0)
    try:
        taken = set(sorted(before)[:1])
        if len(before) > 1:
            cpu = pin_harness_cpu(taken)
            assert cpu not in taken
            assert os.sched_getaffinity(0) == {cpu}
    finally:
        os.sched_setaffinity(0, before)
