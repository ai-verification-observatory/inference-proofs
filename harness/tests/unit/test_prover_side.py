"""RFC-0008 §Shared controls, prover side: the perturbed commitment, C3 and P1 on the fake."""

import hashlib
import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from test_perturb import f32, write_safetensors

from iproofs import cli
from iproofs.adapter import InProcessRunner
from iproofs.errors import IProofsError
from iproofs.provenance import model_digest
from iproofs.runner import JobSpec, Runner, prepare_perturbed
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
ENV = {"IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78",
       "IPROOFS_FAKE_DELAY_S": "0"}  # fmt: skip
IMAGE = "local/in-process@sha256:" + "0" * 64


def repo(tmp_path: Path) -> Path:
    """A repository copy whose fake model also holds a safetensors tensor of 1,024 F32s."""
    r = tmp_path / "repo"
    copied = [
        "schema",
        "systems/fake",
        "systems/fake-broken",
        "workloads/fake-tiny-ci.yaml",
        "reference",
        "harness/tests/fixtures/prompts",
        "uv.lock",
        "pyproject.toml",
    ]
    for rel in copied:
        src, dst = ROOT / rel, r / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst) if src.is_dir() else shutil.copy(src, dst)
    weights = r / "systems/fake/model"
    write_safetensors(weights / "model.safetensors", {"w": ("F32", [1024], f32(*[0.25] * 1024))})
    path = r / "workloads/fake-tiny-ci.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["model"]["files"] = [
        {"path": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
         "bytes": p.stat().st_size}
        for p in sorted(weights.iterdir())
    ]  # fmt: skip
    doc["model"]["digest"] = model_digest(weights)
    path.write_text(yaml.safe_dump(doc, sort_keys=False))
    git = ["git", "-C", str(r), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "fixture", "--no-gpg-sign"], check=True)
    return r


@pytest.fixture
def cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("IPROOFS_CACHE", str(tmp_path / "cache"))
    return tmp_path / "cache"


def runner(r: Path) -> Runner:
    containers = InProcessRunner(r / "systems/fake/entrypoint", REGISTRY, env=ENV)
    return Runner(containers, root=r, registry=REGISTRY, image=IMAGE)


def spec(r: Path, control_suite: bool) -> JobSpec:
    return JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, control_suite, str(r / "results"),
                   "v0.1")  # fmt: skip


def control(doc: dict[str, object], cid: str) -> dict[str, object]:
    return next(c for c in doc["controls"] if c["id"] == cid)  # type: ignore[attr-defined]


def test_prover_side_p1_and_c3_reject_perturbed_weights(tmp_path: Path, cache: Path) -> None:
    r = repo(tmp_path)
    stored = prepare_perturbed(runner(r), spec(r, False), cache)
    record = json.loads(stored.read_text())
    assert stored == r / "results/v0.1/fake/_controls/fake-tiny-ci/perturbed.json"
    assert REGISTRY.errors("perturbed-commitment/1", record) == []
    assert record["perturbation"]["tensor"] == "w"
    assert record["model_digest"] != record["source_model_digest"]
    assert (
        model_digest(cache / "perturbed" / record["source_model_digest"][7:])
        == (record["model_digest"])
    )
    with pytest.raises(IProofsError, match="already holds"):
        prepare_perturbed(runner(r), spec(r, False), cache)  # once per workload per release

    run_dir = runner(r).run(spec(r, True))
    doc = json.loads((run_dir / "controls.json").read_text())
    assert REGISTRY.errors("controls/1", doc) == []
    assert doc["perturbed_commitment"] == {
        "commitment_id": record["commitment"]["commitment_id"],
        "model_digest": record["model_digest"],
    }
    p1, c3, p2 = control(doc, "P1"), control(doc, "C3"), control(doc, "P2")
    assert (p1["side"], p1["outcome"], p1["passed"]) == ("prover", "rejected", True)
    assert p1["twin"] == {"verdict": "accept", "raw_exit_code": 0}
    assert len(p1["trials"]) == 2  # type: ignore[arg-type]  # one batch of batch size 2
    assert (c3["outcome"], c3["passed"]) == ("rejected", True)
    assert (p2["outcome"], p2["note"]) == ("not_applicable", "the workload declares one precision")
    run = json.loads((run_dir / "run.json").read_text())
    assert sorted(p["proof_id"] for p in run["proofs"]) == [f"req-{i}" for i in range(6)]  # no P1


def test_prover_side_without_perturbed_commitment(tmp_path: Path, cache: Path) -> None:
    """With no perturbed commitment C3 and P1 do not apply: the record keeps the reason, the
    command that makes one goes to the progress stream, never into the published note."""
    r = repo(tmp_path)
    run = runner(r)
    run.progress = io.StringIO()
    doc = json.loads((run.run(spec(r, True)) / "controls.json").read_text())
    assert doc["perturbed_commitment"] is None
    for cid in ("C3", "P1"):
        assert control(doc, cid)["outcome"] == "not_applicable"
        assert control(doc, cid)["note"] == "no perturbed commitment for this workload"
    assert "iproofs controls --prepare-perturbed fake-tiny-ci" in run.progress.getvalue()


def test_prover_side_weights_missing_on_host(tmp_path: Path, cache: Path) -> None:
    r = repo(tmp_path)
    prepare_perturbed(runner(r), spec(r, False), cache)
    shutil.rmtree(cache / "perturbed")
    doc = json.loads((runner(r).run(spec(r, True)) / "controls.json").read_text())
    p1 = control(doc, "P1")
    assert (p1["outcome"], p1["note"]) == (
        "not_applicable",
        "the perturbed weights are not on this host",
    )
    assert control(doc, "C3")["outcome"] == "rejected"  # C3 needs only the stored record


def test_perturb_cli_toy_model_has_no_tensor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The repository's fake model is 64 raw bytes: no tensor qualifies, so nothing is stored."""
    monkeypatch.chdir(ROOT)
    monkeypatch.setenv("IPROOFS_CACHE", str(tmp_path / "cache"))
    argv = ["controls", "--prepare-perturbed", "fake-tiny-ci", "--system", "fake", "--profile",
            "ci-cpu", "--in-process", "--results", str(tmp_path / "results")]  # fmt: skip
    assert cli.main(argv) == 2
    assert "cannot perturb fake-tiny-ci" in capsys.readouterr().err
    assert not (tmp_path / "results").exists()
    assert cli.main(["controls", "--prepare-perturbed", "fake-tiny-ci"]) == 2  # no --system
