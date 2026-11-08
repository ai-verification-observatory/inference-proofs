"""RFC-0008 §Split suites on the fake system: `iproofs controls RUN_DIR --only ... --seed ...`
writes parts, and each control's record in a part is the one a run of the whole suite with the
same seed writes."""

import functools
import itertools
import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from test_prover_side import repo as perturbable_repo

from iproofs import cli
from iproofs.adapter import InProcessRunner
from iproofs.errors import IProofsError
from iproofs.runner import (
    JobSpec,
    Runner,
    control_suite,
    controls_for_run,
    prepare_perturbed,
)
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
ENV = {"IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78",
       "IPROOFS_FAKE_DELAY_S": "0"}  # fmt: skip
IMAGE = "local/in-process@sha256:" + "0" * 64
SEED = "0x5f3c9a12d4e6b780"
SUITE = ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "P1", "P2",
         "fake-unsound-skip-tag", "fake-unsound-skip-nothing", "fake-fixture-proof"]  # fmt: skip


def ticks() -> Callable[[], int]:
    """A clock that moves 1 ms per read: every call's span is 1 ms, whichever host made it."""
    return functools.partial(next, itertools.count(0, 1_000_000))


def runner(r: Path, *, tick: bool = True, **kw: object) -> Runner:
    """The fake in process; the control calls on the ticking clock (a run needs the real one:
    its proof release times and its prove step come from different clocks)."""
    clock = ticks() if tick else None
    containers = InProcessRunner(r / "systems/fake/entrypoint", REGISTRY, env=ENV,
                                 **({"clock": clock} if clock else {}))  # fmt: skip
    return Runner(containers, root=r, registry=REGISTRY, image=IMAGE, **kw)  # type: ignore[arg-type]


@pytest.fixture
def kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """(repository, run directory): the fake with a perturbable tensor, its perturbed commitment
    (so C3 and P1 apply), three system controls, and one completed run kept with --keep-io."""
    monkeypatch.setenv("IPROOFS_CACHE", str(tmp_path / "cache"))
    r = perturbable_repo(tmp_path)
    fixture = ROOT / "harness/tests/fixtures/controls/fake-broken-controls.yaml"
    shutil.copy(fixture, r / "systems/fake/controls.yaml")
    git = ["git", "-C", str(r), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "controls", "--no-gpg-sign"], check=True)
    spec = JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, False, str(r / "results"), "v0.1")
    prepare_perturbed(runner(r, tick=False), spec, tmp_path / "cache")
    return r, runner(r, tick=False, keep_io=True).run(spec)


def twin_of(run_dir: Path, name: str) -> Path:
    """A second copy of a run directory, as another host would download it."""
    copy = run_dir.parent / name
    shutil.copytree(run_dir, copy)
    return copy


def test_parts_hold_the_records_of_one_whole_run(kept: tuple[Path, Path]) -> None:
    r, run_dir = kept
    assert [cid for cid, _ in control_suite(r, REGISTRY, "fake")] == SUITE
    whole = json.loads(
        controls_for_run(runner(r), twin_of(run_dir, "whole"), seed=SEED).read_text()
    )
    by_id = {c["id"]: c for c in whole["controls"]}
    assert by_id["C3"]["outcome"] == by_id["P1"]["outcome"] == "rejected"  # the full suite ran
    split = twin_of(run_dir, "split")
    asked = (["P1,C4", "C1,C2,C3"], ["fake-fixture-proof,C8", "C5,C6,C7"],
             ["fake-unsound-skip-nothing,P2,fake-unsound-skip-tag"])  # fmt: skip
    parts = [controls_for_run(runner(r), split, seed=SEED, only=only) for only in asked]
    assert len({p.name for p in parts}) == 3
    for path, only in zip(parts, asked, strict=True):
        doc = json.loads(path.read_text())
        assert REGISTRY.errors("controls-part/1", doc) == []
        assert doc["only"] == [c for c in SUITE if c in ",".join(only).split(",")]
        assert doc["controls"] == [by_id[c] for c in doc["only"]]
        assert (doc["control_seed"], doc["suite"], doc["verifier_cpus"]) == (SEED, SUITE, 1)
    assert not (split / "controls-io").exists()
    assert not (split / "controls.json").exists()
    with pytest.raises(IProofsError, match="never overwritten"):
        controls_for_run(runner(r), split, seed=SEED, only=asked[0])
    fresh = controls_for_run(runner(r), split, only=["C2"])
    assert json.loads(fresh.read_text())["control_seed"] != SEED  # no seed: drawn, and named


def test_verifier_part_needs_no_weights(
    kept: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    r, run_dir = kept

    def no_weights(*_: object) -> Path:
        raise AssertionError("a verifier-side part resolved the weights")

    monkeypatch.setattr(Runner, "_models", no_weights)
    part = controls_for_run(runner(r), run_dir, seed=SEED, only=["C1,C6,fake-fixture-proof"])
    assert [c["id"] for c in json.loads(part.read_text())["controls"]] == [
        "C1", "C6", "fake-fixture-proof"
    ]  # fmt: skip
    with pytest.raises(AssertionError, match="resolved the weights"):
        controls_for_run(runner(r), run_dir, seed=SEED, only=["P2"])


def test_cli_only_and_seed(kept: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    r, run_dir = kept
    monkeypatch.chdir(r)
    monkeypatch.setenv("IPROOFS_FAKE_DELAY_S", "0")
    monkeypatch.setenv("IPROOFS_FAKE_UPSTREAM", ENV["IPROOFS_FAKE_UPSTREAM"])
    base = ["controls", str(run_dir)]
    assert cli.main([*base, "--only", "C1,C2", "--seed", "6862529337877772160"]) == 0
    assert cli.main([*base, "--only", "C8", "--only", "P2", "--seed", SEED]) == 0
    parts = sorted(run_dir.glob("controls-part-5f3c9a12d4e6b780-*.json"))
    assert len(parts) == 2
    assert not (run_dir / "controls.json").exists()
    assert cli.main([*base, "--only", "C1", "--seed", "0xzz"]) == 2
    assert cli.main([*base, "--only", "C9", "--seed", SEED]) == 2
    assert cli.main(["controls", "--prepare-perturbed", "fake-tiny-ci", "--system", "fake",
                     "--profile", "ci-cpu", "--only", "C1"]) == 2  # fmt: skip
