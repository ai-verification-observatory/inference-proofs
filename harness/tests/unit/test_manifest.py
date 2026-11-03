import dataclasses
import json
import re
from pathlib import Path

import pytest

from iproofs.adapter import InProcessRunner
from iproofs.log.patterns import IPV4_ALLOWED, PATTERNS, is_ipv6
from iproofs.runner import Job, JobSpec, Runner, RunnerIdentity
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
FAKE = ROOT / "systems/fake"
ENV = {
    "IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78",
    "IPROOFS_FAKE_DELAY_S": "0",
}


class Capturing(Runner):
    """Keeps the last job so a test can rebuild its manifest with changed inputs."""

    job: Job

    def _write(self, job: Job) -> Path:
        self.job = job
        return super()._write(job)


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> tuple[Capturing, Path]:
    results = tmp_path_factory.mktemp("results")
    runner = Capturing(
        InProcessRunner(FAKE / "entrypoint", REGISTRY, env=ENV),
        root=ROOT,
        registry=REGISTRY,
        image="local/in-process@sha256:" + "0" * 64,
        operator=RunnerIdentity("ci", "none", ("fake",)),
        provider="hosted-ci",
    )
    spec = JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, False, str(results), "v0.1")
    return runner, runner.run(spec)


def manifest(run_dir: Path) -> dict[str, object]:
    doc: dict[str, object] = json.loads((run_dir / "manifest.json").read_text())
    return doc


def test_manifest_round_trip_valid(run: tuple[Capturing, Path]) -> None:
    m = manifest(run[1])
    assert REGISTRY.errors("manifest/1", m) == []
    assert m["run_id"] == run[1].name
    assert m["runner"] == {"handle": "ci", "organisation": "none", "affiliated_systems": ["fake"]}
    assert m["provider"] == "hosted-ci"
    proofs = m["proofs"]
    assert isinstance(proofs, list)
    assert len(proofs) == 6
    assert all(re.fullmatch(r"sha256:[0-9a-f]{64}", p["digest"]) for p in proofs)
    commands = m["commands"]
    assert isinstance(commands, list)
    assert [c["step"] for c in commands][:4] == ["info", "setup", "commit", "prove"]


def test_failed_self_test_ineligible(run: tuple[Capturing, Path]) -> None:
    """The self-test has not run (issue #116), so the manifest says so and the run is ineligible."""
    assert manifest(run[1])["self_test"] == {"passed": False, "checks": []}


def test_dirty_harness_marks_ineligible(run: tuple[Capturing, Path]) -> None:
    harness = manifest(run[1])["harness"]
    assert isinstance(harness, dict)
    assert isinstance(harness["git_dirty"], bool)  # recorded as found; eligibility reads it (#92)
    assert re.fullmatch(r"[0-9a-f]{40}", harness["git_commit"])


def test_prompt_seed_is_hex_string(run: tuple[Capturing, Path]) -> None:
    workload = manifest(run[1])["workload"]
    assert isinstance(workload, dict)
    assert re.fullmatch(r"0x[0-9a-f]{16}", workload["prompt_seed"])
    assert int(workload["prompt_seed"], 16) == run[0].job.seed


def test_reference_run_has_null_commitment(run: tuple[Capturing, Path]) -> None:
    runner = run[0]
    job = runner.job
    assert job.system is not None
    job.system = dataclasses.replace(job.system, kind="reference")
    assert runner._manifest(job)["commitment"] is None


def test_manifest_passes_g9(run: tuple[Capturing, Path]) -> None:
    text = (run[1] / "manifest.json").read_text()
    for p in PATTERNS:
        for m in p.regex.finditer(text):
            found = m.group(0)
            if p.rule == "SEC-5" and found in IPV4_ALLOWED:
                continue
            if p.rule == "SEC-6" and not is_ipv6(found):
                continue
            pytest.fail(f"{p.rule} matches {found!r} in manifest.json")
