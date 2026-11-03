"""RFC-0006 §Verifier profile emulation and RFC-0005 §Container invocation for `verify`."""

import json
from pathlib import Path

import pytest

from iproofs.adapter import InProcessRunner, docker_create_argv
from iproofs.errors import ErrorKind
from iproofs.runner import CpuOnlyEnvironment, JobSpec, Runner
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
IMAGE = "ghcr.io/example/iproofs-fake@sha256:" + "a" * 64
ENV = {
    "IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78",
    "IPROOFS_FAKE_DELAY_S": "0",
}


def verify_argv(cpuset: str) -> list[str]:
    return docker_create_argv(
        IMAGE, "verify", Path("/srv/io"), models_dir=Path("/srv/models"), gpu=0,
        cpuset=cpuset, mems="0", memory=None,
    )  # fmt: skip


@pytest.mark.parametrize("cpuset", ["8-15", "8"])  # the verifier profile, then single-thread
def test_verifier_profile_docker_argv_flags(cpuset: str) -> None:
    a = " ".join(verify_argv(cpuset))
    assert "--gpus" not in a  # a verifier never gets a GPU, even when the job has one
    assert "--memory 32g" in a
    assert "--network none" in a
    assert f"--cpuset-cpus {cpuset} " in a
    assert "/models" not in a  # nor the weights


def run(tmp_path: Path, env: CpuOnlyEnvironment | None = None) -> dict[str, object]:
    containers = InProcessRunner(ROOT / "systems/fake/entrypoint", REGISTRY, env=ENV)
    runner = Runner(containers, root=ROOT, registry=REGISTRY, env=env,
                    image="local/x@sha256:" + "0" * 64)  # fmt: skip
    spec = JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, False, str(tmp_path), "v0.1")
    run_dir = runner.run(spec)
    doc: dict[str, object] = json.loads((run_dir / "run.json").read_text())
    doc["_manifest"] = json.loads((run_dir / "manifest.json").read_text())
    return doc


def test_verifier_profile_recorded_on_a_fake_run(tmp_path: Path) -> None:
    doc = run(tmp_path)
    assert doc["status"] == "completed"
    manifest = doc["_manifest"]
    assert isinstance(manifest, dict)
    assert manifest["profile"]["verifier_host"] == "same_as_prover"
    assert manifest["machine"]["verifier_host"] == "same_as_prover"
    cpu = manifest["machine"]["cpu"]
    assert not set(cpu["bound_prover"]) & set(cpu["bound_verifier"])
    metrics = doc["metrics"]
    assert isinstance(metrics, dict)
    assert metrics["verify_seconds"]["scope"] == "verify"
    assert metrics["verify_single_thread_seconds"]["scope"] == "verify.single_thread"
    assert metrics["verify_seconds"]["value"] > 0
    assert metrics["verify_single_thread_seconds"]["stats"]["n"] == 1  # the first proof only


class Overlapping(CpuOnlyEnvironment):
    def cpus(self, role: str) -> tuple[str, str]:
        return "0-3", "0"


def test_verifier_profile_never_overlaps_the_prover(tmp_path: Path) -> None:
    doc = run(tmp_path, Overlapping())
    failure = doc["failure"]
    assert isinstance(failure, dict)
    assert (failure["kind"], failure["step"]) == (str(ErrorKind.ENVIRONMENT), "machine_recorded")
