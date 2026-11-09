"""Production-serving jobs through the runner (RFC-0015 SRV-1, SRV-6, SRV-8; RFC-0006 R6;
RFC-0004 INV-DERIVE-8), with the fake adapter declared as a serve-role reference on fixture
serving profiles. CPU only: the bound GPUs are indices the fake environment reports, and the
GPU sampler is replaced by one without a GPU. Every value is a fixture value, not a result."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from iproofs.adapter import InProcessRunner
from iproofs.errors import ErrorKind, IProofsError
from iproofs.measure import ManyGpus, NullCgroupReader, Sampler
from iproofs.provenance import Host, check_profile, machine_record
from iproofs.runner import (
    CpuOnlyEnvironment,
    JobSpec,
    Runner,
    bound_gpus,
    engine_interface,
    profile_gpu_count,
)
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
IMAGE = "ghcr.io/example/engine@sha256:" + "a" * 64
GPU = {"model": "CI fake GPU", "form_factor": "none", "memory_mib_min": 1}


class FakeGpus(CpuOnlyEnvironment):
    """A CPU-only host that reports `gpus` as bound (the fixture serving host)."""

    def __init__(self, gpus: tuple[int, ...]) -> None:
        self._gpus = gpus

    def gpus(self) -> tuple[int, ...]:
        return self._gpus


def serving_profile(count: int) -> dict[str, Any]:
    ci = yaml.safe_load((ROOT / "reference/ci.yaml").read_text())["profiles"]["ci-cpu"]
    return {**ci, "kind": "serving", "gpu": {**GPU, "count": count}, "pairs_with": ["ci-gpu"]}


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The fake systems, a serve-role `fake-ref` with entries for 2 and 4 GPUs at both load
    points, and CI serving profiles of 2 and 4 fixture GPUs."""
    repo = tmp_path / "repo"
    for rel in ("schema", "systems/fake", "systems/fake-broken", "workloads/fake-tiny-ci.yaml",
                "reference",
                "harness/tests/fixtures/prompts", "uv.lock", "pyproject.toml"):  # fmt: skip
        src, dst = ROOT / rel, repo / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst) if src.is_dir() else shutil.copy(src, dst)
    ref = repo / "systems/fake-ref"
    ref.mkdir()
    shutil.copy(ROOT / "systems/fake/entrypoint", ref / "entrypoint")
    entries: list[dict[str, Any]] = []
    for gpus in (2, 4):
        base: dict[str, Any] = {"id": "fake-tiny-ci", "gpus": gpus, "precision_used": "int8",
                "precision_substitution": None, "engine_args": []}  # fmt: skip
        entries += [{**base, "load_point": "matched"},
                    {**base, "load_point": "high", "batch_size": 4}]  # fmt: skip
    system = {"schema": "system/1", "name": "fake-ref", "kind": "reference",
              "reference_role": "serve", "contract": "adapter/1",
              "engine": {"name": "fake", "version": "1", "image": IMAGE}, "workloads": entries,
              "deterministic_proofs": True, "incremental_proofs": True,
              "forbidden_flags": []}  # fmt: skip
    (ref / "system.yaml").write_text(json.dumps(system))  # JSON is YAML, with no anchors
    ci = repo / "reference/ci.yaml"
    doc = yaml.safe_load(ci.read_text())
    doc["profiles"]["ci-gpu"] = {**doc["profiles"]["ci-cpu"], "gpu": {**GPU, "count": 1}}
    doc["profiles"]["ci-serving-x2"] = serving_profile(2)
    doc["profiles"]["ci-serving-x4"] = serving_profile(4)
    ci.write_text(json.dumps(doc))
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "fixture", "--no-gpg-sign"], check=True)
    monkeypatch.setenv("IPROOFS_FAKE_DELAY_S", "0.02")
    monkeypatch.setenv("IPROOFS_FAKE_UPSTREAM", "64168df9fd0706dfd955b6795fa6f535872dff78")
    monkeypatch.setattr("iproofs.runner.Sampler", lambda gpu, readers: Sampler(None, readers))
    monkeypatch.setattr("iproofs.runner.select_readers", lambda **_: NullCgroupReader())
    return repo


def runner(repo: Path, gpus: tuple[int, ...], **kw: Any) -> Runner:
    containers = InProcessRunner(repo / "systems/fake-ref/entrypoint", REGISTRY,
                                 env={"IPROOFS_FAKE_NAME": "fake-ref"})  # fmt: skip
    return Runner(containers, root=repo, registry=REGISTRY, image="local/x@sha256:" + "0" * 64,
                  env=FakeGpus(gpus), allow_nonconforming=True, **kw)  # fmt: skip


def spec(repo: Path, profile: str, system: str = "fake-ref") -> JobSpec:
    return JobSpec(system, "fake-tiny-ci", 1, profile, 1, False, str(repo / "results"), "v0.1")


def read(run_dir: Path, name: str) -> dict[str, Any]:
    out: dict[str, Any] = json.loads((run_dir / f"{name}.json").read_text())
    return out


def test_matched_serving_run_counts_its_gpus(repo: Path) -> None:
    """TC-GSPT-X4 on fixture GPUs: a 2-GPU serving job records `inputs.gpu_count` 2, so
    D-GSPT = D-SPT x 2, D-COST-1K reads the same pointer, and the manifest names the load
    point, the run's shape and the engine (RFC-0010)."""
    run_dir = runner(repo, (0, 1), replay_seed=7).run(spec(repo, "ci-serving-x2"))
    doc, manifest = read(run_dir, "run"), read(run_dir, "manifest")
    assert doc["status"] == "completed", doc["failure"]
    assert doc["inputs"]["gpu_count"]["value"] == 2
    assert doc["inputs"]["gpu_count"]["source"]["ref"] == (
        "reference/ci.yaml#/profiles/ci-serving-x2/gpu/count"
    )
    spt = doc["metrics"]["seconds_per_token_prove.session"]["value"]
    gspt = doc["metrics"]["gpu_seconds_per_token_prove.session"]
    assert gspt["value"] == spt * 2
    assert gspt["source"]["inputs"][1].endswith("run.json#/inputs/gpu_count")
    assert manifest["workload"]["load_point"] == "matched"
    assert (manifest["workload"]["batch_size_run"], manifest["workload"]["prompt_count_run"]) == (
        2, 6)  # fmt: skip
    assert "prompt_prefix_digest" not in manifest["workload"]  # the workload's own set
    assert manifest["engine"] == {"name": "fake", "version": "1", "image": IMAGE,
                                  "interface": "vllm serve"}  # fmt: skip
    assert "serving_model" not in manifest  # toy repository model, no serving record
    assert "steady scope under 60 s" in doc["warnings"]  # SRV-1: kept with the label
    assert REGISTRY.errors("manifest/1", manifest) == []
    assert REGISTRY.errors("run/1", doc) == []


def test_high_load_prompt_prefix(repo: Path) -> None:
    """TC-SRV-PROMPT-PREFIX (SRV-8): a high-load job draws 4 x 3 = 12 prompts from the seed; its
    first 6 are the matched run's set, and a source digest that differs is `config`."""
    matched = runner(repo, (0, 1), replay_seed=7).run(spec(repo, "ci-serving-x2"))
    source = read(matched, "manifest")["workload"]["prompt_set_digest"]
    high = runner(repo, (0, 1), replay_seed=7, load="high", source_prompt_digest=source).run(
        spec(repo, "ci-serving-x2")
    )
    doc, manifest = read(high, "run"), read(high, "manifest")
    assert doc["status"] == "completed", doc["failure"]
    assert manifest["workload"]["prompt_prefix_digest"] == source
    assert manifest["workload"]["prompt_count_run"] == 12
    assert doc["metrics"]["requests_count"]["value"] == 12
    other = runner(repo, (0, 1), replay_seed=8, load="high", source_prompt_digest=source).run(
        spec(repo, "ci-serving-x2")
    )
    failed = read(other, "run")["failure"]
    assert (failed["kind"], failed["step"]) == ("config", "resolved")
    assert "SRV-8" in failed["message"]


def test_bound_gpu_count_and_placement(repo: Path) -> None:
    """TC-SRV-GPU-COUNT: one bound GPU on a 2-GPU serving profile is `config` before `info`.
    TC-SRV-PLACEMENT: once a 2-GPU run completed, a 4-GPU job of the workload is `config`."""
    one = read(runner(repo, (0,)).run(spec(repo, "ci-serving-x2")), "run")
    assert (one["failure"]["kind"], one["failure"]["step"]) == ("config", "resolved")
    assert "1 bound GPU(s) [0], profile ci-serving-x2 holds 2" in one["failure"]["message"]
    four = read(runner(repo, (0, 1, 2, 3)).run(spec(repo, "ci-serving-x4")), "run")
    assert four["status"] == "completed"  # no smaller count has run yet
    assert read(runner(repo, (0, 1)).run(spec(repo, "ci-serving-x2")), "run")["status"] == (
        "completed"
    )
    refused = read(runner(repo, (0, 1, 2, 3)).run(spec(repo, "ci-serving-x4")), "run")
    assert refused["failure"]["kind"] == "config"
    assert "a 4-GPU job of this workload is refused" in refused["failure"]["message"]


def test_profile_rules(repo: Path) -> None:
    """RFC-0006 R6: a serving profile runs only a serve-role system; production serving never
    runs on a GPU prover profile; --load is for production serving; an entry must exist."""
    fake = InProcessRunner(repo / "systems/fake/entrypoint", REGISTRY,
                           env={"IPROOFS_FAKE_NAME": "fake"})  # fmt: skip
    prover = Runner(fake, root=repo, registry=REGISTRY, image="local/x@sha256:" + "0" * 64,
                    env=FakeGpus((0, 1)), allow_nonconforming=True)  # fmt: skip
    doc = read(prover.run(spec(repo, "ci-serving-x2", "fake")), "run")
    assert "runs production serving only" in doc["failure"]["message"]
    high = Runner(fake, root=repo, registry=REGISTRY, image="local/x@sha256:" + "0" * 64,
                  load="high")  # fmt: skip
    assert "--load is for production serving" in read(
        high.run(spec(repo, "ci-cpu", "fake")), "run")["failure"]["message"]  # fmt: skip
    gpu = read(runner(repo, (0,)).run(spec(repo, "ci-gpu")), "run")
    assert "runs on a serving profile (RFC-0006 R6), not ci-gpu" in gpu["failure"]["message"]
    system = repo / "systems/fake-ref/system.yaml"
    doc = yaml.safe_load(system.read_text())
    doc["workloads"] = [w for w in doc["workloads"] if w["gpus"] == 4]
    system.write_text(json.dumps(doc))
    none = read(runner(repo, (0, 1)).run(spec(repo, "ci-serving-x2")), "run")
    assert "lists no matched entry for fake-tiny-ci on 2 GPU(s)" in none["failure"]["message"]


def test_helpers(tmp_path: Path) -> None:
    assert bound_gpus(CpuOnlyEnvironment()) == ()
    assert bound_gpus(FakeGpus((2, 3))) == (2, 3)
    with pytest.raises(IProofsError) as e:
        profile_gpu_count(type("P", (), {"gpu": type("G", (), {"count": 0})()})(), "p")
    assert e.value.kind is ErrorKind.CONFIG
    assert profile_gpu_count(type("P", (), {"gpu": None})(), "p") is None
    assert engine_interface(tmp_path) is None
    (tmp_path / "commands.jsonl").write_text(
        "x\n" + json.dumps({"argv": ["vllm.LLM", "--model", "/models"]}) + "\n"
    )
    assert engine_interface(tmp_path) == "LLM class"


class Gpu:
    def __init__(self, mib: float, util: int, energy: int | None, procs: int) -> None:
        self.v = (mib, util, energy, procs)

    def memory_used_mib(self) -> float:
        return self.v[0]

    def util_pct(self) -> int:
        return self.v[1]

    def energy_mj(self) -> int | None:
        return self.v[2]

    def compute_processes(self) -> int:
        return self.v[3]


def test_many_gpus_reads_as_one() -> None:
    """RFC-0011 amendment: memory the maximum, utilisation the mean, energy and processes the
    sum over the bound GPUs (fixture readings)."""
    many = ManyGpus([Gpu(100.0, 50, 10, 1), Gpu(300.0, 70, 20, 0)])
    got = (many.memory_used_mib(), many.util_pct(), many.energy_mj(), many.compute_processes())
    assert got == (300.0, 60, 30, 1)
    assert ManyGpus([Gpu(1.0, 1, None, 0), Gpu(1.0, 1, 5, 0)]).energy_mj() is None
    assert Sampler(None, NullCgroupReader()).gpu is None


def test_machine_record_serving_fields(tmp_path: Path) -> None:
    """RFC-0006 R6 record fields, PC-GPU-COUNT on a serving profile, PC-GPU-IDLE on an unbound
    GPU, PC-SHM below the minimum (fixture NVML readings)."""
    from iproofs.model import load_reference  # noqa: PLC0415

    def nvml(i: int) -> dict[str, object]:
        return {"model": "NVIDIA H200", "count_visible": 8, "memory_total_mib": 143771,
                "driver_version": "x", "cuda_driver_api": "13.0",
                "pci_bus_id": f"0000:0{i}:00.0"}  # fmt: skip

    reading: dict[str, object] = {"compute_processes": 1, "memory_used_mib": 4000,
                                  "util_percent": 90.0, "nvlink_active_links": None}  # fmt: skip
    busy: dict[int, dict[str, object]] = {5: reading}

    def usage(i: int) -> dict[str, object]:
        return busy.get(i) or {"compute_processes": 0, "memory_used_mib": 1, "util_percent": 0.0,
                               "nvlink_active_links": None}  # fmt: skip

    host = Host(root=tmp_path, nvml=nvml, usage=usage, shm=lambda _: 4 * 1024**3, hosted=True)
    record = machine_record(host, results=tmp_path, gpu_index=0, cpus={}, mems=[],
                            provider="p", gpu_indices=(0, 1, 2, 3))  # fmt: skip
    gpu = record["gpu"]
    assert isinstance(gpu, dict)
    assert gpu["bound_indices"] == [0, 1, 2, 3]
    assert gpu["nvlink_active_links"] == [None] * 4  # PC-GPU-LINK: recorded, not failed
    assert [u["index"] for u in gpu["unbound_samples"]] == [4, 5, 6, 7]
    assert record["container"]["shm_bytes"] == 4 * 1024**3  # type: ignore[index]
    profile = load_reference("v0.1", ROOT, REGISTRY).profiles["serving-h200x4-hosted"]
    checks = {f.check for f in check_profile(record, profile)}  # type: ignore[arg-type]
    assert {"PC-GPU-IDLE", "PC-SHM"} <= checks
    assert "PC-GPU-COUNT" not in checks
    three = machine_record(host, results=tmp_path, gpu_index=0, cpus={}, mems=[],
                           provider="p", gpu_indices=(0, 1, 2))  # fmt: skip
    assert "PC-GPU-COUNT" in {f.check for f in check_profile(three, profile)}  # type: ignore[arg-type]
    busy.clear()
    idle = machine_record(host, results=tmp_path, gpu_index=0, cpus={}, mems=[],
                          provider="p", gpu_indices=(0, 1, 2, 3))  # fmt: skip
    assert "PC-GPU-IDLE" not in {f.check for f in check_profile(idle, profile)}  # type: ignore[arg-type]


def test_declared_failure(tmp_path: Path) -> None:
    """RFC-0005 amendment: a reference adapter's /io/failure.json turns a non-zero exit into
    `config` or `resource`; another kind, bad JSON or a proving system stays `adapter`."""
    from types import SimpleNamespace  # noqa: PLC0415

    from iproofs.runner import _declared_failure  # noqa: PLC0415

    ref = SimpleNamespace(system=SimpleNamespace(kind="reference"))
    prover = SimpleNamespace(system=SimpleNamespace(kind="prover"))
    assert _declared_failure(tmp_path, ref) is None  # type: ignore[arg-type]
    path = tmp_path / "failure.json"
    path.write_text(json.dumps({"kind": "resource", "message": "KV", "evidence": ["line"]}))
    assert _declared_failure(tmp_path, ref) == (ErrorKind.RESOURCE, "KV", ["line"])  # type: ignore[arg-type]
    assert _declared_failure(tmp_path, prover) is None  # type: ignore[arg-type]
    path.write_text(json.dumps({"kind": "integrity", "message": "x"}))
    assert _declared_failure(tmp_path, ref) is None  # type: ignore[arg-type]
    path.write_text("{")
    assert _declared_failure(tmp_path, ref) is None  # type: ignore[arg-type]
