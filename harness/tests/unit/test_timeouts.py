import json
import os
from pathlib import Path

import pytest

from iproofs.adapter import InProcessRunner
from iproofs.errors import ErrorKind, IProofsError
from iproofs.measure import timed_call
from iproofs.model import System
from iproofs.runner import JobSpec, Runner
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
FAKE = ROOT / "systems/fake"
IMAGE = "ghcr.io/example/iproofs-fake@sha256:" + "a" * 64


@pytest.fixture
def fake_docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "docker-state"
    state.mkdir()
    monkeypatch.setenv(
        "PATH", f"{ROOT / 'harness/tests/fixtures/fake-docker'}{os.pathsep}{os.environ['PATH']}"
    )
    monkeypatch.setenv("FAKE_DOCKER_STATE", str(state))
    monkeypatch.setenv("FAKE_DOCKER_ENTRYPOINT", str(FAKE / "entrypoint"))
    return state


def argv(io: Path) -> list[str]:
    (io / "job.json").write_text(
        json.dumps(
            {
                "schema": "adapter-job/1",
                "contract": "adapter/1",
                "subcommand": "info",
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
        )
    )
    return ["docker", "create", "-v", f"{io}:/io:rw", IMAGE, "info", "/io/job.json", "/io/out.json"]


def test_timeout_kills_container(
    tmp_path: Path, fake_docker: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_DOCKER_START_DELAY_S", "30")
    with pytest.raises(IProofsError) as e:
        timed_call(argv(tmp_path), timeout_s=0.3)
    assert e.value.kind is ErrorKind.TIMEOUT
    assert (fake_docker / "killed").read_text().startswith("--signal KILL ")
    assert not list(fake_docker.glob("*.json"))  # the container was removed


def test_oom_is_resource(
    tmp_path: Path, fake_docker: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_DOCKER_OOM", "1")
    with pytest.raises(IProofsError) as e:
        timed_call(argv(tmp_path), timeout_s=10)
    assert e.value.kind is ErrorKind.RESOURCE
    assert e.value.exit_code == 137


def test_timeout_recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """docs/spec/07: a prove step over its wall limit is recorded as a timeout failure."""
    real = System.timeout
    monkeypatch.setattr(
        System, "timeout", lambda self, step: 0.3 if step == "prove" else real(self, step)
    )
    env = {
        "IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78",
        "IPROOFS_FAKE_DELAY_S": "1",
    }
    runner = Runner(
        InProcessRunner(FAKE / "entrypoint", REGISTRY, env=env),
        root=ROOT,
        registry=REGISTRY,
        image="local/in-process@sha256:" + "0" * 64,
    )
    run_dir = runner.run(
        JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, False, str(tmp_path), "v0.1")
    )
    doc = json.loads((run_dir / "run.json").read_text())
    assert (doc["status"], doc["failure"]["kind"], doc["failure"]["step"]) == (
        "failed",
        "timeout",
        "prove",
    )
    assert '"event":"step.timeout"' in (run_dir / "logs/harness.jsonl").read_text()
