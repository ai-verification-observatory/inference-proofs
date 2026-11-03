import json
from pathlib import Path

import pytest

from iproofs import cli
from iproofs.adapter import InProcessRunner, StepResult
from iproofs.errors import IProofsError
from iproofs.runner import JobSpec, Runner, controls_for_run
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
FAKE = ROOT / "systems/fake"
ENV = {
    "IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78",
    "IPROOFS_FAKE_DELAY_S": "0",
}
IMAGE = "local/in-process@sha256:" + "0" * 64


def cli_run(system: str, results: Path, *extra: str) -> int:
    return cli.main(
        [
            "run",
            "--system",
            system,
            "--workload",
            "fake-tiny-ci",
            "--profile",
            "ci-cpu",
            "--results",
            str(results),
            "--in-process",
            *extra,
        ]
    )


def controls(results: Path, system: str = "fake") -> list[dict[str, object]]:
    files = sorted((results / "v0.1" / system).glob("*/controls.json"))
    return [json.loads(f.read_text()) for f in files]


@pytest.fixture(autouse=True)
def at_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)
    monkeypatch.setenv("IPROOFS_FAKE_DELAY_S", "0")


def test_control_suite_fake_passes_once_per_configuration(tmp_path: Path) -> None:
    assert cli_run("fake", tmp_path, "--control-suite", "--repetitions", "2") == 0
    docs = controls(tmp_path)
    assert len(docs) == 1  # on the first successful repetition only (RFC-0008)
    summary = docs[0]["summary"]
    assert isinstance(summary, dict)
    assert summary["accepted"] == 0
    assert summary["passed"] == 7  # C3 waits for the perturbed commitment (#90)
    assert docs[0]["disclosure_pending"] is False
    assert REGISTRY.errors("controls/1", docs[0]) == []
    run = json.loads(next((tmp_path / "v0.1/fake").glob("*-1/run.json")).read_text())
    assert run["control"] is False
    assert not any("control" in k for k in run["metrics"])  # never in run.json metrics


def test_control_suite_fake_broken_all_accepted(tmp_path: Path) -> None:
    """RFC-0008 test_fake_broken_all_accepted, through the CLI."""
    assert cli_run("fake-broken", tmp_path, "--control-suite", "--repetitions", "1") == 0
    doc = controls(tmp_path, "fake-broken")[0]
    records = doc["controls"]
    assert isinstance(records, list)
    outcomes = {c["outcome"] for c in records}
    assert outcomes == {"accepted", "not_applicable"}
    assert doc["disclosure_pending"] is True
    log = (next((tmp_path / "v0.1/fake-broken").iterdir()) / "logs/harness.jsonl").read_text()
    assert '"event":"control.disclosure_pending"' in log
    assert log.count('"event":"control.trial"') == 11  # 7 single trials + C6's 5 - C3


class FailSecondControlCall:
    """Fails the second control verify call (C1's trial, after its twin)."""

    def __init__(self) -> None:
        self.inner = InProcessRunner(FAKE / "entrypoint", REGISTRY, env=ENV)

    def run(self, image: str, subcommand: str, io_dir: Path, **kw: object) -> StepResult:
        result = self.inner.run(image, subcommand, io_dir, **kw)  # type: ignore[arg-type]
        if io_dir.name == "call-2":
            return StepResult(subcommand, result.started_mono_ns, result.ended_mono_ns, 9, None, ())
        return result


def test_control_suite_error_is_isolated(tmp_path: Path) -> None:
    runner = Runner(FailSecondControlCall(), root=ROOT, registry=REGISTRY, image=IMAGE)
    run_dir = runner.run(
        JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, True, str(tmp_path), "v0.1")
    )
    doc = json.loads((run_dir / "controls.json").read_text())
    by_id = {c["id"]: c for c in doc["controls"]}
    assert by_id["C1"]["outcome"] == "error"
    assert by_id["C2"]["outcome"] == "rejected"
    assert json.loads((run_dir / "run.json").read_text())["status"] == "completed"


def test_control_suite_on_kept_run(tmp_path: Path) -> None:
    assert cli_run("fake", tmp_path, "--repetitions", "1", "--keep-io") == 0
    run_dir = next((tmp_path / "v0.1/fake").iterdir())
    assert cli.main(["controls", str(run_dir)]) == 0
    assert (run_dir / "controls.json").is_file()
    assert not (run_dir / "controls-io").exists()
    assert cli.main(["derive", str(run_dir), "--check"]) == 0
    assert cli.main(["controls", str(run_dir)]) == 2  # controls.json is never overwritten


def test_control_suite_needs_kept_proofs(tmp_path: Path) -> None:
    assert cli_run("fake", tmp_path, "--repetitions", "1") == 0
    run_dir = next((tmp_path / "v0.1/fake").iterdir())
    runner = Runner(
        InProcessRunner(FAKE / "entrypoint", REGISTRY, env=ENV), root=ROOT, registry=REGISTRY
    )
    with pytest.raises(IProofsError, match="--keep-io"):
        controls_for_run(runner, run_dir)
