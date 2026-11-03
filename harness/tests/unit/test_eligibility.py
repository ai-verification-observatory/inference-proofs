"""RFC-0014 §Eligibility: which stored runs may enter a release, with stable reasons."""

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from iproofs.adapter import InProcessRunner
from iproofs.model import Release
from iproofs.release import REASONS, eligibility
from iproofs.runner import JobSpec, Runner
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
ENV = {"IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78",
       "IPROOFS_FAKE_DELAY_S": "0"}  # fmt: skip
IMAGE = "ghcr.io/example/iproofs-fake@sha256:" + "a" * 64
CARD = "sha256:" + "c" * 64


@pytest.fixture(scope="module")
def stored(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One completed fake run, as written by the runner."""
    out = tmp_path_factory.mktemp("stored")
    containers = InProcessRunner(ROOT / "systems/fake/entrypoint", REGISTRY, env=ENV)
    runner = Runner(containers, root=ROOT, registry=REGISTRY, image="local/x@sha256:" + "0" * 64)
    return runner.run(JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, False, str(out), "v0.1"))


def setup(
    tmp_path: Path, stored: Path, edit: Callable[[dict[str, Any]], None]
) -> tuple[Path, Release]:
    """A repository whose fake system.yaml pins IMAGE at one commit, the stored run made
    eligible (then changed by `edit`), and a release that lists it and its claim card."""
    root = tmp_path / "repo"
    (root / "systems/fake").mkdir(parents=True)
    system = yaml.safe_load((ROOT / "systems/fake/system.yaml").read_text())
    repository, _, digest = IMAGE.partition("@")
    system["image"] = {"repository": repository, "digest": digest}
    (root / "systems/fake/system.yaml").write_text(yaml.safe_dump(system))
    git = ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "pin", "--no-gpg-sign"], check=True)
    commit = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True,
                            check=True).stdout.strip()  # fmt: skip
    run_dir = root / "results/v0.1/fake" / stored.name
    shutil.copytree(stored, run_dir)
    m = json.loads((run_dir / "manifest.json").read_text())
    m["harness"] |= {"git_dirty": False, "nonconforming": False}
    m["self_test"] = {"passed": True, "checks": [{"name": "ST-CLOCK", "passed": True}]}
    m["claim"] = {"system": "fake", "configuration": "default", "card_version": 1}
    m["system"] |= {"adapter_commit": commit, "adapter_dirty": False, "claim_digest": CARD,
                    "image": {"ref": IMAGE, "digest_kind": "manifest"}}  # fmt: skip
    m["proofs"][0]["archive"] = "https://archive.example.org/v0.1/fake/req-0.tar"
    edit(m)
    (run_dir / "manifest.json").write_text(json.dumps(m))
    doc = yaml.safe_load((ROOT / "schema/release/examples/valid/v0.1.yaml").read_text())
    doc["runs"] = [run_dir.relative_to(root).as_posix()]
    doc["claim_cards"] = [{"system": "fake", "configuration": "default", "card_version": 1,
                           "path": "systems/fake/claims/default.yaml", "digest": CARD}]  # fmt: skip
    return run_dir, Release.from_tree(doc)


def reasons(tmp_path: Path, stored: Path, edit: Callable[[dict[str, Any]], None]) -> list[str]:
    run_dir, release = setup(tmp_path, stored, edit)
    ok, found = eligibility(run_dir, release, run_dir.parents[3], REGISTRY)
    assert ok is (found == [])
    assert set(found) <= set(REASONS)
    return found


def test_eligible_run_has_no_reasons(tmp_path: Path, stored: Path) -> None:
    assert reasons(tmp_path, stored, lambda m: None) == []


def test_failed_self_test_ineligible(tmp_path: Path, stored: Path) -> None:
    def failed(m: dict[str, Any]) -> None:
        m["self_test"] = {"passed": False, "checks": [{"name": "ST-NVML", "passed": False}]}

    assert reasons(tmp_path, stored, failed) == ["self_test_failed"]


def test_dirty_harness_marks_ineligible(tmp_path: Path, stored: Path) -> None:
    def dirty(m: dict[str, Any]) -> None:
        m["harness"]["git_dirty"] = True
        m["system"]["adapter_dirty"] = True

    assert reasons(tmp_path, stored, dirty) == ["harness_dirty", "adapter_dirty"]


def test_config_digest_kind_ineligible(tmp_path: Path, stored: Path) -> None:
    def config(m: dict[str, Any]) -> None:
        m["system"]["image"]["digest_kind"] = "config"

    assert reasons(tmp_path, stored, config) == ["image_digest_kind_config"]


def test_claim_card_mismatch_ineligible(tmp_path: Path, stored: Path) -> None:
    def other_card(m: dict[str, Any]) -> None:
        m["system"]["claim_digest"] = "sha256:" + "d" * 64

    assert reasons(tmp_path, stored, other_card) == ["claim_card_not_listed"]
    assert reasons(tmp_path / "none", stored, lambda m: m.update(claim=None)) == [
        "claim_card_not_listed"
    ]


@pytest.mark.parametrize(
    ("edit", "want"),
    [
        (lambda m: m.update(release="v0.2"), ["other_release"]),
        (lambda m: m["harness"].update(nonconforming=True), ["nonconforming_host"]),
        (lambda m: m["harness"].update(git_commit="abc123"), ["manifest_invalid"]),  # short pin
        (
            lambda m: m["system"]["image"].update(ref="ghcr.io/x/y@sha256:" + "b" * 64),
            ["image_differs_from_system_yaml"],
        ),
        (lambda m: m["system"].update(adapter_commit="f" * 40), ["image_differs_from_system_yaml"]),
        (lambda m: m["proofs"][0].update(archive=None), ["no_archived_proof"]),
    ],
)
def test_each_condition_has_its_reason(
    tmp_path: Path, stored: Path, edit: Callable[[dict[str, Any]], None], want: list[str]
) -> None:
    assert reasons(tmp_path, stored, edit) == want


def test_stored_fake_run_is_ineligible_as_is(tmp_path: Path, stored: Path) -> None:
    """A CI run (local image, no self-test, no claim card) fails several conditions at once."""
    release = Release.from_tree(
        {
            **yaml.safe_load((ROOT / "schema/release/examples/valid/v0.1.yaml").read_text()),
            "runs": [],
        }
    )
    ok, found = eligibility(stored, release, ROOT, REGISTRY)
    assert not ok
    assert found[:2] == ["self_test_failed", "claim_card_not_listed"]
    assert "image_digest_kind_config" in found
