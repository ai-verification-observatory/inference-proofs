"""RFC-0015 §Precision matching: TC-PRECISION-SUBST and PM-1."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from iproofs.adapter import InProcessRunner
from iproofs.runner import JobSpec, Runner
from iproofs.schema import SchemaRegistry
from iproofs.validate.precision import bit_widths, check, substituted, substitution_problem

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
IMAGE = "ghcr.io/example/engine@sha256:" + "a" * 64
DOCS = "https://docs.example.org/engine/v1/quantization"


def test_bit_widths_and_order() -> None:
    assert (bit_widths("W8A8"), bit_widths("w4a16"), bit_widths("int8")) == (
        (8, 8),
        (4, 16),
        (8, 8),
    )
    assert bit_widths("mxfp4-custom") is None
    assert substitution_problem("int8", "W8A16") is None  # same weights, higher activations
    assert substitution_problem("W4A16", "W8A8") is None  # next higher weight width
    assert "lower bit width" in str(substitution_problem("int8", "W4A16"))
    assert "lower bit width" in str(substitution_problem("W8A16", "W8A8"))
    assert "unknown scheme" in str(substitution_problem("int8", "mxfp4-custom"))
    assert "no substitution to declare" in str(substitution_problem("int8", "W8A8"))
    assert substitution_problem("W8A8", "fp8") is None  # PM-4: same widths, another format
    assert "no substitution to declare" in str(substitution_problem("bf16", "fp16"))
    assert substituted(ROOT, "no-such-system", "fake-tiny-ci", REGISTRY) is False


def repo(tmp_path: Path, used: str, substitution: dict[str, str] | None) -> Path:
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
    ref = r / "systems/fake-ref"
    ref.mkdir()
    shutil.copy(ROOT / "systems/fake/entrypoint", ref / "entrypoint")
    system = {
        "schema": "system/1", "name": "fake-ref", "kind": "reference",
        "reference_role": "recompute", "contract": "adapter/1",
        "engine": {"name": "engine", "version": "1", "image": IMAGE},
        "workloads": [{"id": "fake-tiny-ci", "precision_used": used,
                       "precision_substitution": substitution, "engine_args": []}],
        "deterministic_proofs": True, "incremental_proofs": True, "forbidden_flags": [],
    }  # fmt: skip
    (ref / "system.yaml").write_text(yaml.safe_dump(system))
    git = ["git", "-C", str(r), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "fixture", "--no-gpg-sign"], check=True)
    return r


def rules(r: Path, *files: str) -> list[tuple[str, str]]:
    return [(f.rule, f.message) for f in check(r, list(files), REGISTRY)]


def test_precision_subst(tmp_path: Path) -> None:
    """TC-PRECISION-SUBST: lower bit width rejected; higher accepted and every quantity flagged."""
    lower = repo(tmp_path / "lower", "W4A16", {"reason": "engine lacks int8", "source": DOCS})
    assert rules(lower, "systems/fake-ref/system.yaml") == [
        ("PM-2", "fake-tiny-ci: W4A16 is a lower bit width than the workload's int8")
    ]
    higher = repo(tmp_path / "higher", "W8A16", {"reason": "engine lacks W8A8 on H100",
                                                 "source": DOCS})  # fmt: skip
    assert rules(higher, "systems/fake-ref/system.yaml") == []
    env = {
        "IPROOFS_FAKE_UPSTREAM": "0" * 40,
        "IPROOFS_FAKE_NAME": "fake-ref",
        "IPROOFS_FAKE_DELAY_S": "0.02",
    }
    containers = InProcessRunner(higher / "systems/fake-ref/entrypoint", REGISTRY, env=env)
    runner = Runner(containers, root=higher, registry=REGISTRY, image="local/x@sha256:" + "0" * 64)
    spec = JobSpec(
        "fake-ref", "fake-tiny-ci", 1, "ci-cpu", 1, False, str(higher / "results"), "v0.1"
    )
    run_dir = runner.run(spec)
    doc = json.loads((run_dir / "run.json").read_text())
    assert doc["status"] == "completed", doc["failure"]["message"]
    assert all(q["quality"]["precision_substituted"] for q in doc["metrics"].values())
    rel = run_dir.relative_to(higher).as_posix() + "/run.json"
    assert rules(higher, rel) == []
    stripped = {k: {**q, "quality": None} for k, q in doc["metrics"].items()}
    (run_dir / "run.json").write_text(json.dumps({**doc, "metrics": stripped}))
    assert {r for r, _ in rules(higher, rel)} == {"PM-2"}  # a row that lost its flag fails


def test_undeclared_difference_fails(tmp_path: Path) -> None:
    r = repo(tmp_path, "W8A16", None)
    assert [rule for rule, _ in rules(r, "systems/fake-ref/system.yaml")] == ["PM-1"]


@pytest.mark.parametrize("used", ["int8", "W8A8"])
def test_matching_precision_passes(tmp_path: Path, used: str) -> None:
    r = repo(tmp_path, used, None)
    assert rules(r, "systems/fake-ref/system.yaml") == ([] if used == "int8" else [
        ("PM-1", "fake-tiny-ci: uses W8A8, the workload serves int8, and no substitution is "
         "declared")
    ])  # fmt: skip


def test_unknown_workload_left_to_xref(tmp_path: Path) -> None:
    r = repo(tmp_path, "W8A16", None)
    path = r / "systems/fake-ref/system.yaml"
    path.write_text(path.read_text().replace("id: fake-tiny-ci", "id: no-such-workload"))
    assert rules(r, "systems/fake-ref/system.yaml") == []
