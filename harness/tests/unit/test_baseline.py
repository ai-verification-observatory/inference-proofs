"""RFC-0018 CO-4: the baseline at full load from a synthetic ladder record (iproofs.baseline)."""

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from iproofs import __version__
from iproofs.baseline import FullLoad, full_load
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
WORKLOAD = "l1-l31-8b-p512-o512"


@dataclass(frozen=True)
class Baseline:
    ladder: tuple[int, ...]
    plateau: float = 0.05
    warmup_batches: int = 1
    timed_batches: int = 3
    prompts: int = 64


@dataclass(frozen=True)
class Rung:
    id: str
    workloads: dict[str, str]


@dataclass(frozen=True)
class Level:
    baseline: Baseline
    rungs: tuple[Rung, ...]


def level(ladder: tuple[int, ...]) -> Level:
    """64 ladder prompts, one warm-up and three timed batches per concurrency."""
    return Level(Baseline(ladder), (Rung("llama-3.1-8b", {"sash": WORKLOAD}),))


def ladder_run(tmp_path: Path, rates: dict[int, float], gpus: int, count: int = 64,
               drop: int | None = None) -> Path:  # fmt: skip
    """A ladder run whose rung c serves its timed replies at rates[c] replies per GPU-second:
    one warm-up batch, then three timed batches of c, released in sequence; batch s of a rung
    serves prompts (s x c + j) mod count. `drop` leaves out the last timed batch of that rung,
    as a failed request does."""
    proofs, t, timed = [], 1_000_000_000, 3
    for c, rate in rates.items():
        t += 5_000_000_000  # the warm-up batch
        for j in range(c):
            proofs.append({"proof_id": f"c{c}-w0-r{j}", "request_index": j % count,
                           "release_mono_ns": t + j})  # fmt: skip
        span_ns = round(timed * c / (rate * gpus) * 1e9)  # the timed batches' span
        step = span_ns // timed
        for k in range(timed - (1 if drop == c else 0)):
            end = t + (span_ns if k == timed - 1 else (k + 1) * step)
            for j in range(c):
                index = ((1 + k) * c + j) % count
                proofs.append({"proof_id": f"c{c}-b{k}-r{j}", "request_index": index,
                               "release_mono_ns": end - (c - 1 - j)})  # fmt: skip
        t += span_ns + 1
    run_dir = tmp_path / "results/v1.0/ref-serve/r"
    run_dir.mkdir(parents=True)
    run = {"run_id": "r", "status": "completed", "failure": None,
           "proofs": [p | {"claimed_output": [1] * 4, "tokens_covered": 8, "verdict": None}
                      for p in proofs]}  # fmt: skip
    (run_dir / "run.json").write_text(json.dumps(run))
    manifest = {"workload": {"id": WORKLOAD, "load_point": "ladder"},
                "machine": {"gpu": {"bound_indices": list(range(gpus))}}}  # fmt: skip
    (run_dir / "manifest.json").write_text(json.dumps(manifest))
    return run_dir


RATES = {1: 10.0, 2: 19.0, 4: 35.0, 8: 60.0, 16: 61.0, 32: 61.5}


def test_full_load_plateau(tmp_path: Path) -> None:
    """Rates 10, 19, 35, 60, 61, 61.5: 0.95 x 61.5 = 58.425, so full load is c = 8 (rate 60),
    not the maximum's c = 32; GPU-seconds per reply 1 / 60."""
    got = full_load(ladder_run(tmp_path, RATES, 1), level(tuple(RATES)))
    assert isinstance(got, FullLoad)
    assert (got.concurrency, got.gpus, got.failed) == (8, 1, ())
    assert [c for c, _ in got.ladder] == list(RATES)
    for (c, q), rate in zip(got.ladder, RATES.values(), strict=True):
        assert q["value"] == pytest.approx(rate, rel=1e-6), c
        assert (q["unit"], q["scope"], q["grade"]) == ("request/gpu_s", "prove.steady", "derived")
    q = got.gpu_seconds_per_reply
    assert q["value"] == pytest.approx(1 / 60, rel=1e-6)
    assert (q["unit"], q["grade"], q["tier"]) == ("gpu_s/request", "derived", "reported")
    assert q["source"] == {"kind": "derivation", "ref": f"derive:D-L1-BASELINE@{__version__}",
                           "inputs": ["results/v1.0/ref-serve/r/run.json#/proofs",
                                      "results/v1.0/ref-serve/r/manifest.json#/machine/gpu/"
                                      "bound_indices",
                                      "results/v1.0/ref-serve/r/run.json#/proofs"]}  # fmt: skip
    assert REGISTRY.errors("quantity/1", q) == []
    assert REGISTRY.errors("quantity/1", got.ladder[0][1]) == []


def test_one_gpu_host_records_a_single_bound_index(tmp_path: Path) -> None:
    """A one-GPU serving host (the 8B ladder of 2026-11-11) records `bound_index` alone, not
    `bound_indices`: one GPU, cited at that field."""
    run_dir = ladder_run(tmp_path, RATES, 1)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    manifest["machine"]["gpu"] = {"bound_index": 0, "count_visible": 1}
    (run_dir / "manifest.json").write_text(json.dumps(manifest))
    got = full_load(run_dir, level(tuple(RATES)))
    assert isinstance(got, FullLoad)
    assert (got.concurrency, got.gpus) == (8, 1)
    assert got.gpu_seconds_per_reply["value"] == pytest.approx(1 / 60, rel=1e-6)
    source = got.gpu_seconds_per_reply["source"]
    assert isinstance(source, dict)
    assert "results/v1.0/ref-serve/r/manifest.json#/machine/gpu/bound_index" in source["inputs"]


def test_tolerance_edge(tmp_path: Path) -> None:
    """60 is below 0.95 x 64 = 60.8: full load moves to the next rung within the plateau."""
    rates = RATES | {32: 64.0}
    got = full_load(ladder_run(tmp_path, rates, 1), level(tuple(rates)))
    assert isinstance(got, FullLoad)
    assert got.concurrency == 16


def test_not_saturated_at_the_top_rung(tmp_path: Path) -> None:
    """The first Maverick ladder (2026-11-11): the rate rose 32 % from c = 128 to 256, so the
    top rung is the only one within the plateau and the ladder never reached capacity."""
    rates = {64: 1.9947, 128: 2.9474, 256: 3.9024}
    got = full_load(ladder_run(tmp_path, rates, 1), level(tuple(rates)))
    assert isinstance(got, str)
    assert got.startswith("not saturated")


def test_gpu_count_applied(tmp_path: Path) -> None:
    """On 4 bound GPUs the same replies per GPU-second take 4 times the GPU-seconds of wall
    time per GPU: the rates are per GPU-second, and 1 / 60 GPU-seconds per reply holds."""
    got = full_load(ladder_run(tmp_path, RATES, 4), level(tuple(RATES)))
    assert isinstance(got, FullLoad)
    assert got.gpus == 4
    assert got.ladder[3][1]["value"] == pytest.approx(60.0, rel=1e-6)
    assert got.gpu_seconds_per_reply["value"] == pytest.approx(1 / 60, rel=1e-6)
    # the same release times read on 1 GPU are 4 times the rate
    run_dir = ladder_run(tmp_path / "one", RATES, 4)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    manifest["machine"]["gpu"]["bound_indices"] = [0]
    (run_dir / "manifest.json").write_text(json.dumps(manifest))
    one = full_load(run_dir, level(tuple(RATES)))
    assert isinstance(one, FullLoad)
    assert one.ladder[3][1]["value"] == pytest.approx(240.0, rel=1e-6)


def test_failed_rung_skipped(tmp_path: Path) -> None:
    """The c = 8 rung lost its last timed batch: it is recorded failed with a null rate, and
    full load is chosen among the rest (16, rate 61, within 5 % of 61.5)."""
    got = full_load(ladder_run(tmp_path, RATES, 1, drop=8), level(tuple(RATES)))
    assert isinstance(got, FullLoad)
    assert got.failed == ((8, "16 of 24 timed replies released"),)
    rate = dict(got.ladder)[8]
    assert (rate["value"], rate["null_reason"]) == (None, "step_failed")
    assert got.concurrency == 16
    assert got.gpu_seconds_per_reply["value"] == pytest.approx(1 / 61, rel=1e-6)


def test_rung_not_served_and_none_served(tmp_path: Path) -> None:
    """A ladder concurrency with no reply is failed; with every rung failed there is no full
    load, and the cause says so."""
    got = full_load(ladder_run(tmp_path, {1: 10.0}, 1), level((1, 2)))
    assert isinstance(got, FullLoad)
    assert got.failed == ((2, "no reply released"),)
    none = full_load(ladder_run(tmp_path / "x", {1: 10.0}, 1, drop=1), level((1,)))
    assert isinstance(none, str)
    assert none.startswith("every ladder rung failed")


def test_batch_off_plan_failed(tmp_path: Path) -> None:
    """A timed batch that served another prompt than the plan's is a failed rung, not a rate."""
    run_dir = ladder_run(tmp_path, {1: 10.0, 2: 19.0}, 1)
    run = json.loads((run_dir / "run.json").read_text())
    for proof in run["proofs"]:
        if proof["proof_id"] == "c2-b1-r1":
            proof["request_index"] = 4  # the plan's is (2 x 2 + 1) mod 64 = 5
    (run_dir / "run.json").write_text(json.dumps(run))
    got = full_load(run_dir, level((1, 2)))
    assert isinstance(got, FullLoad)
    assert got.failed == ((2, "timed replies differ from the plan of 3 batch(es) of 2"),)
    assert got.concurrency == 1


def test_not_a_ladder_run(tmp_path: Path) -> None:
    run_dir = ladder_run(tmp_path, {1: 10.0}, 1)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    manifest["workload"]["load_point"] = "matched"
    (run_dir / "manifest.json").write_text(json.dumps(manifest))
    assert "not a ladder run" in str(full_load(run_dir, level((1,))))
    run = json.loads((run_dir / "run.json").read_text())
    run |= {"status": "failed", "failure": {"kind": "adapter", "message": "boom"}}
    (run_dir / "run.json").write_text(json.dumps(run))
    assert full_load(run_dir, level((1,))) == "run r failed: adapter: boom"
