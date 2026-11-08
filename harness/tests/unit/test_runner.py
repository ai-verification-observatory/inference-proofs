import json
import shutil
from pathlib import Path

import pytest

from iproofs import cli
from iproofs.adapter import ContainerRunner, InProcessRunner, StepResult
from iproofs.runner import JobSpec, Runner, allocate_run_id
from iproofs.schema import SchemaRegistry
from iproofs.validate import check_derived
from secret_samples import sample

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
        "digests.txt",
        "logs",
        "manifest.json",
        "run.json",
        "verifier",
    ]
    assert check_derived(run_dir / "run.json", ROOT) == []  # derived values recompute exactly


def test_g4_survives_a_weight_bits_correction(tmp_path: Path) -> None:
    """RFC-0003 WB-4: the runner copies the workload's asserted inputs into run.json `inputs`
    and D-SPAB-S points there, so correcting the workload file's weight bits after the run
    leaves G4 clean (it does not read the workload file at HEAD)."""
    run_dir = runner().run(spec(tmp_path / "results"))
    doc = read(run_dir)
    inputs = doc["inputs"]
    assert isinstance(inputs, dict)
    assert inputs["weight_bits"]["value"] == 8  # file_size: 64 B x 8 / 64 parameters
    assert inputs["active_parameters_per_token"]["value"] == 64
    metrics = doc["metrics"]
    assert isinstance(metrics, dict)
    spab = metrics["seconds_per_active_weight_bit_token_prove.session"]
    assert spab["source"]["inputs"][2].endswith("run.json#/inputs/weight_bits")
    root = tmp_path / "repo"
    for tree in ("schema", "reference"):
        shutil.copytree(ROOT / tree, root / tree)
    (root / "workloads").mkdir()
    text = (ROOT / "workloads/fake-tiny-ci.yaml").read_text()
    corrected = text.replace(
        'weight_bits: {basis: "file_size"', 'weight_bits: {bits: 4, basis: "stated"'
    )
    corrected = corrected.replace(', files: ["weights.bin"]}', "}")
    assert corrected != text
    (root / "workloads/fake-tiny-ci.yaml").write_text(corrected)
    assert check_derived(run_dir / "run.json", root) == []


def test_controls_skipped_without_flag(tmp_path: Path) -> None:
    run_dir = runner().run(spec(tmp_path))
    assert not (run_dir / "controls.json").exists()
    states = [json.loads(line).get("to") for line in (run_dir / "logs/harness.jsonl").open()]
    assert "controls" not in states
    assert states[-1] is None  # job.written carries no transition


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
                ("upstream failed at " + sample("SEC-5"),),
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
    assert sample("SEC-5") not in json.dumps(failure)  # redacted before writing
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


def test_failed_prompt_build_still_names_the_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A job that fails while building prompts (a missing extra, here) writes a valid manifest
    naming its image, not an internal error."""
    from iproofs import runner as runner_module  # noqa: PLC0415
    from iproofs.errors import ErrorKind, IProofsError  # noqa: PLC0415

    def missing(*_: object, **__: object) -> list[list[int]]:
        raise IProofsError(ErrorKind.ENVIRONMENT, "tokenizers is not installed")

    monkeypatch.setattr(runner_module, "materialise_prompts", missing)
    doc = read(runner().run(spec(tmp_path)))
    failure = doc["failure"]
    assert isinstance(failure, dict)
    assert (doc["status"], failure["kind"]) == ("failed", "environment")
