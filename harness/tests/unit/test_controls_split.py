"""RFC-0008 §Split suites on the fake system: `iproofs controls RUN_DIR --draw-seed` records
the suite's one seed, `--only ...` writes parts with it, `--merge` writes controls.json, and the
merge of a suite split three ways is the same bytes as one run of the whole suite with the same
seed."""

import functools
import io
import itertools
import json
import shutil
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from test_prover_side import repo as perturbable_repo

from iproofs import cli
from iproofs.adapter import InProcessRunner, StepResult
from iproofs.errors import IProofsError
from iproofs.provenance import Host, file_digest, select_verifier_cpus, usable_topology
from iproofs.runner import (
    GpuEnvironment,
    Job,
    JobSpec,
    Runner,
    VerifierEnvironment,
    _part_host,
    control_suite,
    controls_for_run,
    draw_seed,
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


def seeded(run_dir: Path, name: str, seed: str = SEED) -> Path:
    """A copy of the run with its split suite's seed record, as `--draw-seed` writes it."""
    copy = twin_of(run_dir, name)
    draw_seed(REGISTRY, copy, control_seed=seed)
    return copy


def merge_dir(run_dir: Path, name: str) -> Path:
    """What the merge reads, and nothing else: run.json, manifest.json, controls-seed.json."""
    out = run_dir.parent / name
    out.mkdir()
    for f in ("run.json", "manifest.json", "controls-seed.json"):
        shutil.copy(run_dir / f, out / f)
    return out


def test_merged_parts_equal_one_run_byte_for_byte(
    kept: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each part runs on its own copy of the stored run with a fresh runner, as on separate
    hosts, and the merge reads only the three small files (docs/runbooks/hf-jobs.md stage 5)."""
    r, run_dir = kept
    monkeypatch.chdir(r)
    assert [cid for cid, _ in control_suite(r, REGISTRY, "fake")] == SUITE
    whole = controls_for_run(runner(r), twin_of(run_dir, "whole"), seed=SEED)
    stored = seeded(run_dir, "stored")
    asked = (["P1,C4", "C1,C2,C3"], ["fake-fixture-proof,C8", "C5,C6,C7"],
             ["fake-unsound-skip-nothing,P2,fake-unsound-skip-tag"])  # fmt: skip
    parts = [controls_for_run(runner(r), twin_of(stored, f"part-{i}"), only=only)
             for i, only in enumerate(asked)]  # fmt: skip
    assert len({p.name for p in parts}) == 3
    seed_digest = file_digest(stored / "controls-seed.json")
    for path, only in zip(parts, asked, strict=True):
        doc = json.loads(path.read_text())
        assert REGISTRY.errors("controls-part/1", doc) == []
        assert doc["only"] == [c for c in SUITE if c in ",".join(only).split(",")]
        assert [c["id"] for c in doc["controls"]] == doc["only"]
        assert (doc["control_seed"], doc["suite"], doc["verifier_cpus"]) == (SEED, SUITE, 1)
        assert doc["seed_record_digest"] == seed_digest
        assert doc["host"]["machine"]["verifier_host"] == "same_as_prover"
        assert not (path.parent / "controls-io").exists()
    target = merge_dir(stored, "merge")
    merged = merge_controls(REGISTRY, target, list(reversed(parts)))
    assert merged == target / "controls.json"
    assert merged.read_bytes() == whole.read_bytes()
    doc = json.loads(whole.read_text())
    outcomes = {c["id"]: c["outcome"] for c in doc["controls"]}
    assert outcomes["C3"] == outcomes["P1"] == "rejected"  # the full suite ran, not a stub
    assert outcomes["fake-unsound-skip-tag"] == "accepted"
    shutil.copy(merged, stored / "controls.json")
    assert cli.main(["derive", str(stored), "--check"]) == 0
    with pytest.raises(IProofsError, match="never overwritten"):
        merge_controls(REGISTRY, target, parts)
    with pytest.raises(IProofsError, match=r"already has controls\.json"):
        controls_for_run(runner(r), stored, only=asked[0])
    with pytest.raises(IProofsError, match="never redrawn"):
        draw_seed(REGISTRY, stored)


def test_split_runs_with_one_drawn_seed(kept: tuple[Path, Path]) -> None:
    """SPLIT-1: a part takes its seed from the run's seed record, drawn once by the harness;
    `seed` can only confirm it, and the whole suite no longer runs once a record exists."""
    r, run_dir = kept
    bare = twin_of(run_dir, "bare")
    with pytest.raises(IProofsError, match=r"no controls-seed\.json: draw the suite's seed"):
        controls_for_run(runner(r), bare, only=["C1"])
    when = datetime(2026, 11, 9, 10, 0, 0, tzinfo=UTC)
    record = draw_seed(REGISTRY, bare, now=lambda: when)
    doc = json.loads(record.read_text())
    assert REGISTRY.errors("controls-seed/1", doc) == []
    assert doc["drawn_at"] == "2026-11-09T10:00:00Z"
    assert doc["control_seed"] != SEED  # from os.urandom
    with pytest.raises(IProofsError, match="never redrawn"):
        draw_seed(REGISTRY, bare)
    with pytest.raises(IProofsError, match=f"--seed {SEED} is not the seed"):
        controls_for_run(runner(r), bare, seed=SEED, only=["C1"])
    with pytest.raises(IProofsError, match="its suite runs in parts"):
        controls_for_run(runner(r), bare)
    part = controls_for_run(runner(r), bare, seed=doc["control_seed"], only=["C1"])
    assert json.loads(part.read_text())["control_seed"] == doc["control_seed"]
    with pytest.raises(IProofsError, match="never overwritten"):
        controls_for_run(runner(r), bare, only=["C1"])
    edited = twin_of(bare, "edited")
    manifest = json.loads((edited / "manifest.json").read_text())
    (edited / "manifest.json").write_text(json.dumps(manifest | {"warnings": ["edited"]}))
    with pytest.raises(IProofsError, match="was not drawn for"):
        controls_for_run(runner(r), edited, only=["C2"])
    (edited / "controls-seed.json").write_text(json.dumps(doc | {"control_seed": "0x1"}))
    with pytest.raises(IProofsError, match="fails controls-seed/1"):
        controls_for_run(runner(r), edited, only=["C2"])
    failed = twin_of(run_dir, "failed")
    run = json.loads((failed / "run.json").read_text())
    (failed / "run.json").write_text(json.dumps(run | {"status": "failed"}))
    with pytest.raises(IProofsError, match="did not complete"):
        draw_seed(REGISTRY, failed)
    done = twin_of(run_dir, "done")
    (done / "controls.json").write_text("{}")
    with pytest.raises(IProofsError, match="never redrawn"):
        draw_seed(REGISTRY, done)


def test_merge_refuses_a_part_of_another_run_or_seed(kept: tuple[Path, Path]) -> None:
    r, run_dir = kept
    stored = seeded(run_dir, "one")
    one = controls_for_run(runner(r), stored, only=["C1"])
    other = twin_of(run_dir, "other")
    manifest = json.loads((other / "manifest.json").read_text())
    (other / "manifest.json").write_text(json.dumps(manifest | {"warnings": ["edited"]}))
    draw_seed(REGISTRY, other, control_seed=SEED)
    with pytest.raises(IProofsError, match="was not made against"):
        merge_controls(REGISTRY, other, [one])
    with pytest.raises(IProofsError, match="is given twice"):
        merge_controls(REGISTRY, stored, [one, one])
    bad = run_dir.parent / "bad.json"
    bad.write_text(json.dumps({"schema": "controls-part/1"}))
    with pytest.raises(IProofsError, match="fails controls-part/1"):
        merge_controls(REGISTRY, stored, [bad])
    redrawn = seeded(run_dir, "redrawn", seed="0x" + "1" * 16)
    two = controls_for_run(runner(r), redrawn, only=["C2"])
    assert two.name != one.name  # another seed, carried in the name
    with pytest.raises(IProofsError, match="did not run with"):
        merge_controls(REGISTRY, stored, [one, two])
    same_seed = twin_of(run_dir, "same-seed")  # the same value drawn at another time
    draw_seed(REGISTRY, same_seed, control_seed=SEED, now=lambda: datetime(2026, 1, 1, tzinfo=UTC))
    three = controls_for_run(runner(r), same_seed, only=["C2"])
    with pytest.raises(IProofsError, match="did not run with"):
        merge_controls(REGISTRY, stored, [one, three])
    with pytest.raises(IProofsError, match=r"no controls-seed\.json"):
        merge_controls(REGISTRY, run_dir, [one])


def test_verifier_part_needs_no_weights(
    kept: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    r, run_dir = kept
    stored = seeded(run_dir, "stored")

    def no_weights(*_: object) -> Path:
        raise AssertionError("a verifier-side part resolved the weights")

    monkeypatch.setattr(Runner, "_models", no_weights)
    part = controls_for_run(runner(r), stored, only=["C1,C6,fake-fixture-proof"])
    assert [c["id"] for c in json.loads(part.read_text())["controls"]] == [
        "C1", "C6", "fake-fixture-proof"
    ]  # fmt: skip
    with pytest.raises(AssertionError, match="resolved the weights"):
        controls_for_run(runner(r), stored, only=["P2"])


def test_p1_part_refused_without_the_perturbed_weights(
    kept: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A single run on the host that made the perturbed weights runs P1; a part on a host
    without them must not record `not_applicable` in its place (SPLIT-2)."""
    r, run_dir = kept
    stored = seeded(run_dir, "stored")
    weights = next((tmp_path / "cache/perturbed").iterdir())
    shutil.move(weights, tmp_path / "elsewhere")
    with pytest.raises(IProofsError, match=r"P1: the perturbed weights .* are not in this host"):
        controls_for_run(runner(r), stored, only=["P1"])
    assert not list(stored.glob("controls-part-*"))
    monkeypatch.setenv("IPROOFS_CACHE", str(tmp_path / "empty"))
    part = controls_for_run(runner(r), stored, only=["P2"])  # P2 needs no perturbed weights
    assert json.loads(part.read_text())["controls"][0]["outcome"] == "not_applicable"


class OneCpuVerifier(VerifierEnvironment):
    def __init__(self) -> None:
        super().__init__(Host(FIXTURE_HOST, run=lambda _: None, hosted=True), 1)


def test_prover_side_refused_where_no_prove_can_run(kept: tuple[Path, Path]) -> None:
    """A prove that cannot run on this host must stop the job, not read as `prover_failed`."""
    r, run_dir = kept
    stored = seeded(run_dir, "stored")
    on_gpu = seeded(run_dir, "gpu-profile")
    with pytest.raises(IProofsError, match="prover-side controls P1, fake-unsound-skip-tag"):
        controls_for_run(
            runner(r, env=OneCpuVerifier()), stored, only=["C1,P1,fake-unsound-skip-tag"]
        )
    part = controls_for_run(runner(r, env=OneCpuVerifier()), stored, only=["C1"])
    doc = json.loads(part.read_text())
    assert doc["verifier_cpus"] == 1
    machine = doc["host"]["machine"]
    assert machine["verifier_host"] == "separate"
    assert (machine["cpu"]["bound_prover"], machine["cpu"]["bound_verifier"]) == ([], [0])
    assert doc["host"]["nonconforming"] == [
        line for line in doc["host"]["nonconforming"] if line.startswith("PC-MEM")
    ]  # a verifier host is checked against verifier-cpu's memory only
    run = json.loads((on_gpu / "run.json").read_text())
    (on_gpu / "run.json").write_text(json.dumps(run | {"profile": "prover-h200-hosted"}))
    with pytest.raises(IProofsError, match="give --gpu"):
        controls_for_run(runner(r), on_gpu, only=["P2"])
    assert not list(on_gpu.glob("controls-part-*"))


def gpu_host(model: str) -> Host:
    """The fixture host with one GPU of `model` on NUMA node 0."""
    nvml = {"pci_bus_id": "00000000:17:00.0", "model": model, "count_visible": 1}
    return Host(FIXTURE_HOST, run=lambda _: None, nvml=lambda i: nvml, hosted=True)


def test_prover_part_records_its_host_and_refuses_another_gpu(kept: tuple[Path, Path]) -> None:
    """SPLIT-3: a prover-side part proves on the run's GPU model; the profile checks this host
    does not meet are recorded in the part, not refused."""
    r, run_dir = kept
    other = twin_of(run_dir, "h200-run")
    manifest = json.loads((other / "manifest.json").read_text())
    manifest["machine"]["gpu"] = {"model": "NVIDIA H200", "count_visible": 1}
    (other / "manifest.json").write_text(json.dumps(manifest))
    draw_seed(REGISTRY, other, control_seed=SEED)
    on_h100 = GpuEnvironment(0, gpu_host("NVIDIA H100 80GB HBM3"), n_prover=1, n_verifier=1)
    with pytest.raises(IProofsError, match="the run proved on 'NVIDIA H200'"):
        controls_for_run(runner(r, env=on_h100), other, only=["fake-unsound-skip-tag"])
    on_h200 = GpuEnvironment(0, gpu_host("NVIDIA H200"), n_prover=1, n_verifier=1)
    part = controls_for_run(runner(r, env=on_h200), other, only=["C1"])
    doc = json.loads(part.read_text())
    assert doc["host"]["machine"]["gpu"]["model"] == "NVIDIA H200"
    assert doc["host"]["machine"]["cpu"]["bound_prover"] == [0]
    assert doc["host"]["nonconforming"]  # the fixture host meets few of ci-cpu's checks
    job = Job(JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, True, str(r / "results"), "v0.1"),
              "run", other)  # fmt: skip
    runner_ = runner(r, env=on_h200)
    runner_._resolve_inputs(job, models=False)
    host = _part_host(runner_, job, manifest["machine"], prover_side=True)  # the run's GPU
    assert host["machine"]["gpu"]["model"] == "NVIDIA H200"  # type: ignore[index]
    verifier_side = controls_for_run(runner(r, env=on_h100), other, only=["C2"])
    assert json.loads(verifier_side.read_text())["host"]["machine"]["gpu"]["model"] == (
        "NVIDIA H100 80GB HBM3"
    )  # only proves are tied to the run's GPU


def test_each_control_call_logs_its_span(kept: tuple[Path, Path]) -> None:
    """`control.call` after every control call, and a progress line for it, so a part's job
    log shows how far it got (docs/spec/05)."""
    r, run_dir = kept
    stored = seeded(run_dir, "stored")
    stream = io.StringIO()
    controls_for_run(runner(r, progress=stream), stored, only=["C2,fake-unsound-skip-tag"])
    lines = stream.getvalue().splitlines()
    seen = [("twin", "verify"), ("C2", "verify"), ("fake-unsound-skip-tag", "prove"),
            ("twin", "verify"), *[("fake-unsound-skip-tag", "verify")] * 6]  # fmt: skip
    assert [tuple(line.split()[4:2:-1]) for line in lines] == seen
    assert lines[2].startswith("[rep 1/1] controls prove fake-unsound-skip-tag  00:00:00  exit 0")
    events = [json.loads(line) for line in (stored / "logs/harness.jsonl").read_text().splitlines()]
    calls = [e for e in events if e["event"] == "control.call"]
    assert [(e["control"], e["subcommand"]) for e in calls] == seen
    assert [e["trial"] for e in calls] == [0, 0, None, 0, 0, 1, 2, 3, 4, 5]
    assert all(e["exit_code"] == 0 and e["seconds"] >= 0 for e in calls)


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


def test_cli_split_and_merge(
    kept: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    r, run_dir = kept
    monkeypatch.chdir(r)
    monkeypatch.setenv("IPROOFS_FAKE_DELAY_S", "0")
    monkeypatch.setenv("IPROOFS_FAKE_UPSTREAM", ENV["IPROOFS_FAKE_UPSTREAM"])
    base = ["controls", str(run_dir)]
    assert cli.main([*base, "--only", "C1"]) == 2  # no seed drawn yet
    assert cli.main([*base, "--seed", SEED]) == 2  # a whole suite draws its own
    assert cli.main([*base, "--draw-seed", "--only", "C1"]) == 2
    assert cli.main([*base, "--draw-seed", "--merge", str(run_dir / "x.json")]) == 2
    capsys.readouterr()
    assert cli.main([*base, "--draw-seed"]) == 0
    printed = capsys.readouterr().out.split()
    seed = json.loads((run_dir / "controls-seed.json").read_text())["control_seed"]
    assert printed == [str(run_dir / "controls-seed.json"), seed]
    assert cli.main([*base, "--draw-seed"]) == 2
    assert cli.main([*base, "--only", "C1,C2,C3,C4,C5,C6,C7", "--seed", str(int(seed, 16))]) == 0
    assert cli.main(["--quiet", *base, "--only", "C8,P1,P2", "--only",
                     ",".join(SUITE[10:])]) == 0  # fmt: skip
    assert cli.main([*base, "--only", "C8", "--seed", SEED]) == 2  # not the drawn seed
    parts = sorted(run_dir.glob(f"controls-part-{seed[2:]}-*.json"))
    assert len(parts) == 2
    assert cli.main([*base, "--merge", *map(str, parts), "--seed", seed]) == 2
    assert cli.main([*base, "--merge", *map(str, parts)]) == 0
    doc = json.loads((run_dir / "controls.json").read_text())
    assert [c["id"] for c in doc["controls"]] == SUITE
    assert doc["control_seed"] == seed
    assert cli.main([*base, "--only", "C1", "--seed", "0xzz"]) == 2
    assert cli.main(["controls", "--prepare-perturbed", "fake-tiny-ci", "--system", "fake",
                     "--profile", "ci-cpu", "--only", "C1"]) == 2  # fmt: skip
    assert cli.main(["controls", "--prepare-perturbed", "fake-tiny-ci", "--system", "fake",
                     "--profile", "ci-cpu", "--draw-seed"]) == 2  # fmt: skip


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
    assert cli._verifier_cpus(ROOT, "v0.1", REGISTRY) == 8  # verifier-cpu's logical_cpus
    assert cli._verifier_cpus(ROOT, "ci", REGISTRY) == 8  # no verifier-cpu: the default
    assert cli._verifier_cpus(ROOT, "v9.9", REGISTRY) == 8  # no reference file


class OneCopyAtATime(InProcessRunner):
    """The fake, checking that no earlier control call's proof copy is still on disk."""

    calls = 0

    def run(self, image: str, subcommand: str, io_dir: Path, **kw: Any) -> StepResult:
        if subcommand == "verify" and io_dir.name.startswith("call-"):
            OneCopyAtATime.calls += 1
            assert [d.parent.name for d in io_dir.parent.glob("call-*/proof")] == [io_dir.name]
        return super().run(image, subcommand, io_dir, **kw)


def test_each_call_proof_copy_is_removed_after_the_call(kept: tuple[Path, Path]) -> None:
    r, run_dir = kept
    containers = OneCopyAtATime(r / "systems/fake/entrypoint", REGISTRY, env=ENV)
    runner_ = Runner(containers, root=r, registry=REGISTRY, image=IMAGE)
    controls_for_run(runner_, seeded(run_dir, "stored"), only=["C1,C6,P1"])
    assert OneCopyAtATime.calls == 2 + 6 + 3  # twin and trial; twin and five; twin and two proofs
