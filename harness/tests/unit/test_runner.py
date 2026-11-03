import json
from pathlib import Path

import pytest

from iproofs import cli
from iproofs.adapter import ContainerRunner, InProcessRunner, StepResult
from iproofs.errors import IProofsError
from iproofs.runner import JobSpec, Runner, allocate_run_id
from iproofs.schema import SchemaRegistry
from iproofs.validate import check_derived

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
FAKE = ROOT / "systems/fake"
UPSTREAM = {
    "IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78",
    "IPROOFS_FAKE_DELAY_S": "0.02",
}


def spec(results: Path, **kw: object) -> JobSpec:
    base = {
        "system": "fake",
        "workload": "fake-tiny-ci",
        "workload_version": 1,
        "profile": "ci-cpu",
        "repetition": 1,
        "control_suite": False,
        "results_root": str(results),
        "release": "v0.1",
    }
    return JobSpec(**{**base, **kw})  # type: ignore[arg-type]


def runner(containers: ContainerRunner | None = None) -> Runner:
    containers = containers or InProcessRunner(FAKE / "entrypoint", REGISTRY, env=UPSTREAM)
    return Runner(
        containers, root=ROOT, registry=REGISTRY, image="local/in-process@sha256:" + "0" * 64
    )


def read(run_dir: Path) -> dict[str, object]:
    doc: dict[str, object] = json.loads((run_dir / "run.json").read_text())
    return doc


def test_state_machine_happy_path(tmp_path: Path) -> None:
    run_dir = runner().run(spec(tmp_path))
    doc = read(run_dir)
    assert doc["status"] == "completed"
    assert REGISTRY.errors("run/1", doc) == []
    metrics = doc["metrics"]
    assert isinstance(metrics, dict)
    assert metrics["prove_steady_seconds"]["value"] > 0
    assert metrics["tokens_covered_total"]["value"] == 48  # 6 proofs of 8 tokens
    assert metrics["verdicts_accept_count"]["value"] == 6
    stored = doc["events"]
    assert isinstance(stored, list)
    events = [e["event"] for e in stored]
    assert events.count("proof.released") == 6
    assert sorted(p.name for p in run_dir.iterdir()) == [
        "logs",
        "manifest.json",
        "run.json",
        "verifier",
    ]
    assert check_derived(run_dir / "run.json", ROOT) == []  # derived values recompute exactly


def test_controls_skipped_without_flag(tmp_path: Path) -> None:
    run_dir = runner().run(spec(tmp_path))
    assert not (run_dir / "controls.json").exists()
    states = [json.loads(line).get("to") for line in (run_dir / "logs/harness.jsonl").open()]
    assert "controls" not in states
    assert states[-1] is None  # job.written carries no transition


def test_control_suite_not_yet_wired(tmp_path: Path) -> None:
    with pytest.raises(IProofsError, match="#89"):
        runner().run(spec(tmp_path, control_suite=True))


class FailAt:
    """A container runner that makes one step exit non-zero."""

    def __init__(self, step: str) -> None:
        self.step = step
        self.inner = InProcessRunner(FAKE / "entrypoint", REGISTRY, env=UPSTREAM)

    def run(self, image: str, subcommand: str, io_dir: Path, **kw: object) -> StepResult:
        result = self.inner.run(image, subcommand, io_dir, **kw)  # type: ignore[arg-type]
        if subcommand == self.step:
            return StepResult(
                subcommand,
                result.started_mono_ns,
                result.ended_mono_ns,
                7,
                None,
                ("upstream failed at 10.0.0.9",),
            )
        return result


@pytest.mark.parametrize("step", ["info", "setup", "commit", "prove", "verify"])
def test_failure_at_each_step(tmp_path: Path, step: str) -> None:
    run_dir = runner(FailAt(step)).run(spec(tmp_path))
    doc = read(run_dir)
    assert doc["status"] == "failed"
    failure = doc["failure"]
    assert isinstance(failure, dict)
    assert (failure["kind"], failure["step"], failure["exit_code"]) == ("adapter", step, 7)
    assert "10.0.0.9" not in json.dumps(failure)  # redacted before writing
    assert REGISTRY.errors("run/1", doc) == []


def test_failed_run_exits_4_through_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr("iproofs.adapter.InProcessRunner", lambda *a, **k: FailAt("prove"))
    code = cli.main(
        [
            "run",
            "--system",
            "fake",
            "--workload",
            "fake-tiny-ci",
            "--profile",
            "ci-cpu",
            "--repetitions",
            "1",
            "--results",
            str(tmp_path),
            "--in-process",
        ]
    )
    assert code == 4


def test_run_id_increments(tmp_path: Path) -> None:
    first, _ = allocate_run_id(tmp_path, spec(tmp_path), "2026-11-20")
    second, _ = allocate_run_id(tmp_path, spec(tmp_path), "2026-11-20")
    assert first.endswith("-ci-cpu-1")
    assert second.endswith("-ci-cpu-2")


def test_repetitions_below_minimum_marked(tmp_path: Path) -> None:
    dirs = runner().run_many(spec(tmp_path), 2)
    assert len(dirs) == 2
    for d in dirs:
        assert "repetitions_below_minimum" in read(d)["warnings"]  # type: ignore[operator]
    assert [read(d)["repetition"] for d in dirs] == [1, 2]
