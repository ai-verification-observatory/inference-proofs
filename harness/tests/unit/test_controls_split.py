"""RFC-0008 §Split suites on the fake system: `iproofs controls RUN_DIR --only ... --seed ...`
writes parts, `--merge` writes controls.json, and the merge of a suite split three ways is the
same bytes as one run of the whole suite with the same seed."""

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
from iproofs.provenance import Host, select_verifier_cpus, usable_topology
from iproofs.runner import (
    JobSpec,
    Runner,
    VerifierEnvironment,
    control_suite,
    controls_for_run,
    merge_controls,
    prepare_perturbed,
)
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
FIXTURE_HOST = ROOT / "harness/tests/fixtures/host"
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


def test_merged_parts_equal_one_run_byte_for_byte(
    kept: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    r, run_dir = kept
    monkeypatch.chdir(r)
    assert [cid for cid, _ in control_suite(r, REGISTRY, "fake")] == SUITE
    whole = controls_for_run(runner(r), twin_of(run_dir, "whole"), seed=SEED)
    split = twin_of(run_dir, "split")
    asked = (["P1,C4", "C1,C2,C3"], ["fake-fixture-proof,C8", "C5,C6,C7"],
             ["fake-unsound-skip-nothing,P2,fake-unsound-skip-tag"])  # fmt: skip
    parts = [controls_for_run(runner(r), split, seed=SEED, only=only) for only in asked]
    assert len({p.name for p in parts}) == 3
    for path, only in zip(parts, asked, strict=True):
        doc = json.loads(path.read_text())
        assert REGISTRY.errors("controls-part/1", doc) == []
        assert doc["only"] == [c for c in SUITE if c in ",".join(only).split(",")]
        assert [c["id"] for c in doc["controls"]] == doc["only"]
        assert (doc["control_seed"], doc["suite"], doc["verifier_cpus"]) == (SEED, SUITE, 1)
    merged = merge_controls(REGISTRY, split, list(reversed(parts)))
    assert merged == split / "controls.json"
    assert merged.read_bytes() == whole.read_bytes()
    doc = json.loads(whole.read_text())
    outcomes = {c["id"]: c["outcome"] for c in doc["controls"]}
    assert outcomes["C3"] == outcomes["P1"] == "rejected"  # the full suite ran, not a stub
    assert outcomes["fake-unsound-skip-tag"] == "accepted"
    assert not (split / "controls-io").exists()
    assert cli.main(["derive", str(split), "--check"]) == 0
    with pytest.raises(IProofsError, match="never overwritten"):
        merge_controls(REGISTRY, split, parts)
    with pytest.raises(IProofsError, match="never overwritten"):
        controls_for_run(runner(r), split, seed=SEED, only=asked[0])


def test_merge_refuses_a_part_of_another_run(kept: tuple[Path, Path]) -> None:
    r, run_dir = kept
    one = controls_for_run(runner(r), twin_of(run_dir, "one"), seed=SEED, only=["C1"])
    other = twin_of(run_dir, "other")
    manifest = json.loads((other / "manifest.json").read_text())
    manifest["warnings"] = ["edited"]
    (other / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(IProofsError, match="was not made against"):
        merge_controls(REGISTRY, other, [one])
    with pytest.raises(IProofsError, match="is given twice"):
        merge_controls(REGISTRY, run_dir.parent / "one", [one, one])
    bad = run_dir.parent / "bad.json"
    bad.write_text(json.dumps({"schema": "controls-part/1"}))
    with pytest.raises(IProofsError, match="fails controls-part/1"):
        merge_controls(REGISTRY, run_dir, [bad])
    other_seed = controls_for_run(runner(r), run_dir.parent / "one", only=["C2"])
    assert other_seed.name != one.name  # no --seed: a fresh one, carried in the name
    with pytest.raises(IProofsError, match=r"differs .* in control_seed"):
        merge_controls(REGISTRY, run_dir.parent / "one", [one, other_seed])


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


class OneCpuVerifier(VerifierEnvironment):
    def __init__(self) -> None:
        super().__init__(Host(FIXTURE_HOST, run=lambda _: None, hosted=True), 1)


def test_prover_side_refused_where_no_prove_can_run(kept: tuple[Path, Path]) -> None:
    """A prove that cannot run on this host must stop the job, not read as `prover_failed`."""
    r, run_dir = kept
    on_gpu = twin_of(run_dir, "gpu-profile")
    with pytest.raises(IProofsError, match="prover-side controls P1, fake-unsound-skip-tag"):
        controls_for_run(
            runner(r, env=OneCpuVerifier()), run_dir, only=["C1,P1,fake-unsound-skip-tag"]
        )
    part = controls_for_run(runner(r, env=OneCpuVerifier()), run_dir, seed=SEED, only=["C1"])
    assert json.loads(part.read_text())["verifier_cpus"] == 1
    run = json.loads((on_gpu / "run.json").read_text())
    (on_gpu / "run.json").write_text(json.dumps(run | {"profile": "prover-h200-hosted"}))
    with pytest.raises(IProofsError, match="give --gpu"):
        controls_for_run(runner(r), on_gpu, only=["P2"])
    assert not list(on_gpu.glob("controls-part-*"))


def test_verifier_environment_binds_the_profile_cpus() -> None:
    host = Host(FIXTURE_HOST, run=lambda _: None, hosted=True)
    env = VerifierEnvironment(host, 3)
    assert env.cpus("verifier") == ("0,1,2", "0,1")
    assert env.cpus("verifier_1") == ("0", "0,1")
    assert (env.gpu(), env.host()) == (None, host)
    with pytest.raises(IProofsError, match="binds no prover"):
        env.cpus("prover")
    with pytest.raises(IProofsError, match="not enough CPUs for the verifier profile: 4 < 8"):
        VerifierEnvironment(host, 8)
    assert select_verifier_cpus(usable_topology(host), 4) == (0, 1, 2, 3)


def test_cli_split_and_merge(kept: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    r, run_dir = kept
    monkeypatch.chdir(r)
    monkeypatch.setenv("IPROOFS_FAKE_DELAY_S", "0")
    monkeypatch.setenv("IPROOFS_FAKE_UPSTREAM", ENV["IPROOFS_FAKE_UPSTREAM"])
    base = ["controls", str(run_dir)]
    assert cli.main([*base, "--only", "C1,C2,C3,C4,C5,C6,C7", "--seed", "6862529337877772160"]) == 0
    assert cli.main([*base, "--only", "C8,P1,P2", "--only", ",".join(SUITE[10:]),
                     "--seed", SEED]) == 0  # fmt: skip
    parts = sorted(run_dir.glob("controls-part-5f3c9a12d4e6b780-*.json"))
    assert len(parts) == 2
    assert cli.main([*base, "--merge", *map(str, parts), "--seed", SEED]) == 2
    assert cli.main([*base, "--merge", *map(str, parts)]) == 0
    doc = json.loads((run_dir / "controls.json").read_text())
    assert [c["id"] for c in doc["controls"]] == SUITE
    assert doc["control_seed"] == SEED
    assert cli.main([*base, "--only", "C1", "--seed", "0xzz"]) == 2
    assert cli.main(["controls", "--prepare-perturbed", "fake-tiny-ci", "--system", "fake",
                     "--profile", "ci-cpu", "--only", "C1"]) == 2  # fmt: skip


def test_cli_hosted_needs_the_pinned_image(
    kept: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A hosted container is the system's pinned image; a run made with another image (here
    the in-process one) cannot be controlled in it."""
    r, run_dir = kept
    monkeypatch.chdir(r)
    inner = InProcessRunner(r / "systems/fake/entrypoint", REGISTRY, env=ENV)
    monkeypatch.setattr(cli, "_containers", lambda *a, **k: (inner, None, REGISTRY))
    assert cli.main(["controls", str(run_dir), "--hosted", "--only", "C1"]) == 2
    assert "--hosted runs in the pinned image" in capsys.readouterr().err


def test_cli_hosted_verifier_host_and_gpu(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without --gpu a hosted controls job binds the release's verifier-cpu CPUs; with --gpu
    the run's prover profile, as `iproofs run --gpu` does."""
    from iproofs import runner as runner_mod  # noqa: PLC0415

    made: list[tuple[Host, int]] = []

    class Spy(OneCpuVerifier):
        def __init__(self, host: Host, n: int) -> None:
            made.append((host, n))
            super().__init__()

    monkeypatch.setattr(runner_mod, "VerifierEnvironment", Spy)
    assert isinstance(cli._verifier_host(ROOT, "v0.1", REGISTRY), Spy)
    ((host, n),) = made
    assert (host.hosted, n) == (True, 8)
    with pytest.raises(IProofsError, match="no verifier-cpu"):
        cli._verifier_host(ROOT, "ci", REGISTRY)
