"""RFC-0007 §Tolerance, §Eligibility, §Verdict and digest matching (§Testing Strategy cases)."""

import json
import math
from pathlib import Path

import pytest

from iproofs import cli
from iproofs.adapter import InProcessRunner
from iproofs.release import compare, tolerance, write_reproduction
from iproofs.runner import JobSpec, Runner, RunnerIdentity
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
IMAGE = "ghcr.io/example/iproofs-fake@sha256:" + "a" * 64
SEEDS = ("0x0000000000000001", "0x0000000000000002", "0x0000000000000003")


# ---------------------------------------------------------------- tolerance


def test_tolerance_relative_dominates() -> None:
    bound, difference, within = tolerance(100, 1, 3, 109, 1, 3)
    assert 3 * math.sqrt(1 / 3 + 1 / 3) == pytest.approx(2.449, abs=1e-3)
    assert (bound, difference, within) == (10.0, 9.0, True)


def test_tolerance_relative_fails() -> None:
    assert tolerance(100, 1, 3, 111, 1, 3) == (10.0, 11.0, False)


def test_tolerance_statistical_dominates() -> None:
    bound, difference, within = tolerance(100, 10, 3, 115, 10, 3)
    assert bound == 3 * math.sqrt(100 / 3 + 100 / 3)
    assert bound == pytest.approx(24.49, abs=1e-2)
    assert (difference, within) == (15.0, True)


def test_tolerance_zero_variance() -> None:
    assert tolerance(0, 0, 3, 0, 0, 3) == (0.0, 0.0, True)
    assert tolerance(0, 0, 3, 1e-9, 0, 3)[2] is False


# ---------------------------------------------------------------- records over run directories


def make_run(  # noqa: PLR0913 (one fixture knob per RFC rule)
    results: Path,
    run_id: str,
    *,
    seed: str,
    runner: tuple[str, str] = ("b", "Org B"),
    image: str = IMAGE,
    rate: float | None = 100.0,
    verdicts: tuple[str, ...] = ("accept", "accept"),
    controls: dict[str, str] | None = None,
    digests: tuple[str, ...] = ("sha256:" + "1" * 64,),
    binding: tuple[int, ...] = (0, 1),
) -> Path:
    d = results / "v0.1/fake" / run_id
    d.mkdir(parents=True)
    run = {
        "run_id": run_id,
        "system": "fake",
        "status": "completed",
        "proofs": [{"proof_id": f"req-{i}", "verdict": v} for i, v in enumerate(verdicts)],
        "metrics": {
            "rate_prove.steady": {"value": rate, "unit": "token/s", "scope": "prove.steady"},
            "proof_bytes": {"value": 64, "unit": "B", "scope": None},
        },
    }
    manifest = {
        "release": "v0.1",
        "runner": {"handle": runner[0], "organisation": runner[1], "affiliated_systems": []},
        "claim": {"configuration": "default"},
        "workload": {
            "id": "fake-tiny-ci",
            "version": 1,
            "prompt_seed": seed,
            "file_digest": "sha256:" + "2" * 64,
            "corpus_digest": "sha256:" + "3" * 64,
            "model": {"digest": "sha256:" + "4" * 64},
        },
        "profile": {"prover": "ci-cpu", "verifier": "ci-cpu"},
        "system": {"image": {"ref": image}, "adapter_dirty": False},
        "harness": {"git_dirty": False},
        "provider": "provider-1",
        "machine": {"cpu": {"bound_prover": list(binding)}},
        "proofs": [{"digest": x} for x in digests],
    }
    (d / "run.json").write_text(json.dumps(run))
    (d / "manifest.json").write_text(json.dumps(manifest))
    if controls is not None:
        entries = [{"id": k, "outcome": v} for k, v in controls.items()]
        (d / "controls.json").write_text(json.dumps({"controls": entries}))
    return d


CONTROLS = {"C1": "rejected", "C5": "invalid_call"}


def configuration(
    results: Path, first_controls: dict[str, str] = CONTROLS, **repro: object
) -> tuple[Path, Path]:
    """Three original runs by Org A; three replays and one fresh seed by Org B, elsewhere."""
    orig = [
        make_run(
            results,
            f"2026-11-20-fake-fake-tiny-ci-ci-cpu-{i + 1}",
            seed=s,
            runner=("a", "Org A"),
            controls=CONTROLS if i == 0 else None,
        )
        for i, s in enumerate(SEEDS)
    ]
    reps = [
        make_run(
            results,
            f"2026-11-25-fake-fake-tiny-ci-ci-cpu-{i + 1}",
            seed=s,
            binding=(8, 9),
            controls=first_controls if i == 0 else None,
            **repro,  # type: ignore[arg-type]
        )
        for i, s in enumerate((*SEEDS, "0x00000000000000ff"))
    ]
    return orig[0], reps[0]


def record(
    results: Path,
    *,
    deterministic: bool = False,
    first_controls: dict[str, str] = CONTROLS,
    **repro: object,
) -> dict[str, object]:
    orig, rep = configuration(results, first_controls, **repro)
    out = compare(orig, rep, deterministic_proofs=deterministic, maintainer_organisations=["Org C"])
    assert REGISTRY.errors("reproduction/1", out) == []
    return out


def comparison(rec: dict[str, object], metric: str) -> dict[str, object]:
    entries = rec["comparisons"]
    assert isinstance(entries, list)
    return next(c for c in entries if c["metric"] == metric)


def test_within_tolerance(tmp_path: Path) -> None:
    rec = record(tmp_path, rate=105.0)
    assert rec["outcome"] == "within_tolerance", rec
    assert rec["eligibility"] == {
        "same_release": True,
        "same_image_digest": True,
        "same_workload_digests": True,
        "same_profile": True,
        "different_machine": True,
        "clean_build": True,
        "repetitions": 3,
    }
    assert rec["fresh_seed_runs"] == ["2026-11-25-fake-fake-tiny-ci-ci-cpu-4"]
    rate = comparison(rec, "rate_prove.steady")
    assert (rate["bound"], rate["difference"], rate["within"]) == (10.0, 5.0, True)
    assert rate["reproduction"] == {"mean": 105.0, "stdev": 0.0, "n": 3}  # replays only


def test_verdict_mismatch_overrides(tmp_path: Path) -> None:
    rec = record(tmp_path, first_controls={"C1": "accepted", "C5": "invalid_call"})
    assert all(c["within"] for c in rec["comparisons"])  # type: ignore[attr-defined]
    assert rec["verdicts_match"] is False
    assert rec["outcome"] == "outside_tolerance"


def test_digest_required_only_if_deterministic(tmp_path: Path) -> None:
    other = ("sha256:" + "9" * 64,)
    lax = record(tmp_path / "lax", digests=other)
    assert lax["digests"] == {"required": False, "matched": None}
    assert lax["outcome"] == "within_tolerance"
    strict = record(tmp_path / "strict", deterministic=True, digests=other)
    assert strict["digests"] == {"required": True, "matched": False}
    assert strict["outcome"] == "outside_tolerance"


def test_null_metric_handling(tmp_path: Path) -> None:
    both = tmp_path / "both"
    orig = [
        make_run(
            both,
            f"2026-11-20-fake-fake-tiny-ci-ci-cpu-{i + 1}",
            seed=s,
            runner=("a", "Org A"),
            rate=None,
        )
        for i, s in enumerate(SEEDS)
    ]
    reps = [
        make_run(
            both, f"2026-11-25-fake-fake-tiny-ci-ci-cpu-{i + 1}", seed=s, rate=None, binding=(8,)
        )
        for i, s in enumerate((*SEEDS, "0xff"))
    ]
    rec = compare(orig[0], reps[0], deterministic_proofs=False, maintainer_organisations=[])
    rate = comparison(rec, "rate_prove.steady")
    assert (rate["within"], rate["difference"]) == (None, None)
    assert rec["outcome"] == "within_tolerance"  # null on both sides does not fail
    one = record(tmp_path / "one", rate=None)
    rate = comparison(one, "rate_prove.steady")
    assert (rate["within"], rate["difference"]) == (False, None)
    assert one["outcome"] == "outside_tolerance"


def test_eligibility_image_digest(tmp_path: Path) -> None:
    rec = record(tmp_path, image="ghcr.io/example/iproofs-fake@sha256:" + "b" * 64)
    assert rec["eligibility"]["same_image_digest"] is False  # type: ignore[index]
    assert rec["outcome"] == "ineligible"


def test_affiliated_runner_is_ineligible(tmp_path: Path) -> None:
    rec = record(tmp_path, runner=("c", "Org C"))  # Org C maintains the system
    assert rec["outcome"] == "ineligible"


def test_needs_a_fresh_seed_and_three_replays(tmp_path: Path) -> None:
    orig, rep = configuration(tmp_path)
    fresh = sorted(rep.parent.iterdir())[-1]
    assert fresh.name.endswith("-4")
    for f in fresh.iterdir():
        f.unlink()
    fresh.rmdir()
    rec = compare(orig, rep, deterministic_proofs=False, maintainer_organisations=[])
    assert (rec["fresh_seed_runs"], rec["outcome"]) == ([], "ineligible")


# ---------------------------------------------------------------- the fake system end to end


def test_fake_runs_by_two_organisations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env = {"IPROOFS_FAKE_UPSTREAM": "64168df9fd0706dfd955b6795fa6f535872dff78"}
    spec = JobSpec("fake", "fake-tiny-ci", 1, "ci-cpu", 1, False, str(tmp_path), "v0.1")

    def runner(org: str, seed: int | None = None) -> Runner:
        containers = InProcessRunner(ROOT / "systems/fake/entrypoint", REGISTRY, env=env)
        return Runner(
            containers,
            root=ROOT,
            registry=REGISTRY,
            image="local/in-process@sha256:" + "0" * 64,
            operator=RunnerIdentity(org.lower(), org),
            replay_seed=seed,
        )

    orig = runner("Org A").run(spec)
    seed = int(json.loads((orig / "manifest.json").read_text())["workload"]["prompt_seed"], 16)
    repro = runner("Org B", seed).run(spec)
    rec = compare(orig, repro, deterministic_proofs=True, maintainer_organisations=[])
    assert REGISTRY.errors("reproduction/1", rec) == []
    assert rec["verdicts_match"] is True
    assert rec["digests"] == {"required": True, "matched": True}  # the fake is deterministic
    assert rec["outcome"] == "ineligible"  # one replay, no fresh seed, the same machine
    monkeypatch.chdir(ROOT)
    assert cli.main(["reproduce", "compare", str(orig), str(repro)]) == 1
    written = orig / "reproductions" / f"{repro.name}.json"
    assert REGISTRY.errors("reproduction/1", json.loads(written.read_text())) == []
    assert capsys.readouterr().out == written.read_text()  # CLI-3: the record on stdout
    with pytest.raises(Exception, match="append-only"):
        write_reproduction(orig, rec, REGISTRY)
