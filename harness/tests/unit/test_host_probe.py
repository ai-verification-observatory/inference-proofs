"""docs/runbooks/host-probe.py, the standard-library probe of a GPU host
(docs/runbooks/h200-host.md, docs/runbooks/hf-jobs.md): its sections on a fixture host tree
with fake nvidia-smi, docker and network, its verdicts against prover-h200 (bare metal) and
prover-h200-hosted (a container with no docker engine), its profile constants against
reference/v0.1.yaml, and the scrub of identifiers (AGENTS.md rule 7)."""

import importlib.util
import json
import shutil
import sys
import urllib.error
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from iproofs.model import ContainerRuntime, HostedRuntime, ProverProfile, load_reference
from iproofs.schema import SchemaRegistry
from secret_samples import sample

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "harness/tests/fixtures/host"
GIB = 1024**3


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "host_probe", ROOT / "docs/runbooks/host-probe.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROBE = _load()

# A node with two H200: GPU 0 at the fixture's PCI address (NUMA node 0) runs a process; GPU 1
# has no sysfs entry. CC mode is off.
OUTPUTS: dict[tuple[str, ...], str] = {
    ("nvidia-smi", "--query-gpu=index,name,memory.total,driver_version,pci.bus_id,compute_mode",
     "--format=csv,noheader,nounits"): (
        "0, NVIDIA H200, 143771, 580.95.05, 00000000:17:00.0, Default\n"
        "1, NVIDIA H200, 143771, 580.95.05, 00000000:99:00.0, Default\n"
    ),
    ("nvidia-smi", "--query-compute-apps=gpu_bus_id", "--format=csv,noheader"):
        "00000000:17:00.0\n",
    ("nvidia-smi",): "| NVIDIA-SMI 580.95.05   Driver Version: 580.95.05   CUDA Version: 13.2 |\n",
    ("nvidia-smi", "conf-compute", "-f"): "CC status: OFF\n",
    ("nvidia-smi", "conf-compute", "-grs"): "Confidential Compute GPUs Ready state: not-ready\n",
    ("docker", "version", "--format", "{{.Server.Version}}"): "27.3.1\n",
    ("docker", "info", "--format", "{{.CgroupDriver}} {{.CgroupVersion}} {{json .Runtimes}}"):
        'systemd 2 {"nvidia":{"path":"nvidia-container-runtime"},"runc":{"path":"runc"}}\n',
    ("nvidia-ctk", "--version"): "NVIDIA Container Toolkit CLI version 1.17.3\ncommit: 0a1b2c\n",
}  # fmt: skip


def fake(outputs: dict[tuple[str, ...], str]) -> Any:
    def runner(argv: list[str]) -> str | None:
        return outputs.get(tuple(argv))

    return runner


class _Response:
    status = 200

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def opener(url: str, timeout: float) -> _Response:
    if "token?scope=repository:ai-verification-observatory/sash" in url:
        return _Response()  # public
    if "ghcr.io" in url:
        raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)  # type: ignore[arg-type]
    if "huggingface.co" in url:
        return _Response()
    raise OSError("no route")


def host(tmp_path: Path, *, sha: bool = True) -> Path:
    root = tmp_path / "root"
    shutil.copytree(FIXTURE, root)
    if sha:
        info = (root / "proc/cpuinfo").read_text()
        (root / "proc/cpuinfo").write_text(
            info.replace("model name", "flags\t\t: fpu sse sha_ni avx\nmodel name", 1)
        )
    (root / "sys/fs/cgroup").mkdir(parents=True)
    (root / "sys/fs/cgroup/cgroup.controllers").write_text("cpu memory\n")
    (root / "run/systemd/system").mkdir(parents=True)
    (root / "proc/self").mkdir(parents=True)
    (root / "proc/self/mounts").write_text(f"/dev/nvme0n1p1 {root} ext4 rw 0 0\n")
    (root / "systems/sash").mkdir(parents=True)
    (root / "systems/sash/system.yaml").write_text(
        'image:\n  repository: "ghcr.io/ai-verification-observatory/sash"\n'
    )
    (root / "systems/flashprove").mkdir(parents=True)
    (root / "systems/flashprove/system.yaml").write_text(
        "image:\n  repository: ghcr.io/ai-verification-observatory/flashprove\n"
    )
    return root


def report(
    root: Path,
    outputs: dict[tuple[str, ...], str] | None = None,
    profile: str = "prover-h200",
    allowed: list[int] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = PROBE.probe(root, fake(OUTPUTS if outputs is None else outputs),
                                      opener, root, root, profile, allowed)  # fmt: skip
    return out


def verdicts(r: dict[str, Any]) -> dict[str, str]:
    return {row["id"]: row["status"] for row in r["requirements"]}


@pytest.mark.parametrize("pid", ["prover-h200", "prover-h200-hosted"])
def test_profile_constants_follow_the_reference_file(pid: str) -> None:
    """The probe carries both H200 profiles' numbers; a change to reference/v0.1.yaml fails here."""
    ref = load_reference("v0.1", ROOT, SchemaRegistry.from_tree(ROOT / "schema"))
    found = ref.profiles[pid]
    assert isinstance(found, ProverProfile)
    assert found.gpu is not None
    p = PROBE.PROFILES[pid]
    assert p["id"] == pid
    assert (p["gpu_model"], p["gpu_memory_mib_min"], p["gpu_count"]) == (
        found.gpu.model, found.gpu.memory_mib_min, found.gpu.count)  # fmt: skip
    assert p["logical_cpus_on_gpu_numa_node"] == found.cpu.logical_cpus_on_gpu_numa_node
    assert p["logical_cpus_total_min"] == found.cpu.logical_cpus_total_min
    assert p["host_memory_gib_min"] == found.host_memory_gib_min
    assert p["disk_free_gib_min"] == found.disk.free_gib_min
    assert p["disk_nvme"] == ("nvme" in found.disk.type.lower())
    assert (p["kernel_min"], p["driver"]) == (found.kernel_min, found.driver)
    runtime = found.container_runtime
    assert p["hosted"] == isinstance(runtime, HostedRuntime)
    if isinstance(runtime, ContainerRuntime):
        assert p["os"] == (found.os.id, found.os.version_id)
        assert (p["docker_engine_min"], p["nvidia_container_toolkit_min"],
                p["cgroup_driver"]) == (runtime.docker_engine_min,
                                        runtime.nvidia_container_toolkit_min,
                                        runtime.cgroup_driver)  # fmt: skip
    verifier = ref.profiles["verifier-cpu"]
    assert verifier.cpu.logical_cpus == PROBE.VERIFIER_CPUS  # type: ignore[union-attr]


def test_sections_on_a_fixture_host(tmp_path: Path) -> None:
    r = report(host(tmp_path))
    gpus = r["gpus"]
    assert gpus["count"] == 2
    assert gpus["devices"][0] == {
        "index": 0, "name": "NVIDIA H200", "memory_total_mib": 143771,
        "driver_version": "580.95.05", "compute_mode": "Default", "numa_node": 0,
        "compute_processes": 1,
    }  # fmt: skip
    assert gpus["devices"][1]["numa_node"] is None  # no sysfs entry for it in the fixture
    assert gpus["devices"][1]["compute_processes"] == 0
    assert gpus["cuda_driver_api"] == "13.2"
    assert r["confidential_computing"]["status"] == "off"
    assert r["cpu"]["sha_ni"] is True
    assert r["cpu"]["model"] == "AMD EPYC 9654 96-Core Processor"
    assert (r["cpu"]["logical_cpus"], r["cpu"]["sockets"], r["cpu"]["physical_cores"]) == (4, 2, 4)
    assert r["numa"] == {"nodes": 2, "logical_cpus_per_node": {"0": 2, "1": 2},
                         "allowed_cpus_per_node": {"0": 2, "1": 2}}  # fmt: skip
    assert r["cgroup"]["version"] == "2"
    assert (r["cgroup"]["cpu_quota_cpus"], r["cgroup"]["memory_limit_bytes"]) == (None, None)
    assert r["memory"]["available_bytes"] == 1550793824 * 1024
    assert r["disks"]["work"]["device_kind"] == "nvme"
    assert r["disks"]["work"]["fs_type"] == "ext4"
    assert "docker_root" not in r["disks"]  # docker info gave no root directory
    assert r["system"]["os_id"] == "ubuntu"
    assert r["system"]["systemd_running"] is True
    assert r["containers"] == {"docker_engine": "27.3.1", "cgroup_driver": "systemd",
                               "cgroup_version": "2", "nvidia_runtime": True,
                               "nvidia_container_toolkit": "1.17.3"}  # fmt: skip
    net = r["network"]
    assert (net["ghcr.io"], net["huggingface.co"]) == (401, 200)
    assert net["anonymous_pull"] == {"ai-verification-observatory/flashprove": False,
                                     "ai-verification-observatory/sash": True}  # fmt: skip


def test_verdicts_against_prover_h200(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The fixture is a small host: it meets the GPU, software and memory needs and fails the
    CPU minimums; the idle GPU 1 is suggested over the busy GPU 0."""
    monkeypatch.setattr(PROBE.shutil, "which", lambda name: f"/usr/bin/{name}")
    r = report(host(tmp_path))
    v = verdicts(r)
    for rid in ("gpu_model", "gpu_count", "gpu_memory_mib", "gpu_idle", "cuda_driver_api",
                "cuda_driver_api_flashprove", "cc_mode_off", "sha_ni", "host_memory_gib",
                "flashprove_commit_floor_gb", "work_disk_nvme", "work_disk_writable", "os",
                "cgroup_v2", "systemd", "cpu_quota", "docker_engine", "docker_cgroup_driver",
                "nvidia_container_toolkit", "reach_ghcr.io", "reach_huggingface.co"):  # fmt: skip
        assert v[rid] == "pass", rid
    assert v["driver"] == "record"  # unpinned until #77
    assert v["cpus_total"] == "fail"
    assert v["cpus_usable"] == "fail"  # 4 < 24 + 8
    assert v["cpus_on_gpu_numa_node"] == "fail"  # GPU 1 has no NUMA node: iproofs run refuses it
    assert v["work_disk_free_gib"] in ("pass", "fail")  # the test machine's own disk
    assert v["pull_ai-verification-observatory/sash"] == "pass"
    assert v["pull_ai-verification-observatory/flashprove"] == "login"
    suggested = next(row for row in r["requirements"] if row["id"] == "suggested_gpu_index")
    assert suggested["found"] == 1
    assert "cpus_total" in r["failed"]
    assert "driver" not in r["failed"]
    assert set(r["failed_flashprove"]) <= {"madvise_wipeonfork"}  # refused off Linux
    assert {row["scope"] for row in r["requirements"]} == {"profile", "flashprove"}


def test_cc_on_busy_gpu_and_old_software_fail(tmp_path: Path) -> None:
    outputs = dict(OUTPUTS)
    outputs[("nvidia-smi", "conf-compute", "-f")] = "CC status: ON\n"
    query = next(k for k in outputs if k[1].startswith("--query-gpu"))
    outputs[query] = "0, NVIDIA H200, 143771, 550.54.15, 00000000:17:00.0, Default\n"
    outputs[("nvidia-smi",)] = "| Driver Version: 550.54.15   CUDA Version: 12.4 |\n"
    outputs[("docker", "version", "--format", "{{.Server.Version}}")] = "24.0.7\n"
    info = next(k for k in outputs if k[:2] == ("docker", "info"))
    outputs[info] = 'cgroupfs 1 {"runc":{"path":"runc"}}\n'
    outputs[("nvidia-ctk", "--version")] = "NVIDIA Container Toolkit CLI version 1.14.6\n"
    v = verdicts(report(host(tmp_path, sha=False), outputs))
    for rid in ("cc_mode_off", "gpu_idle", "cuda_driver_api", "cuda_driver_api_flashprove",
                "docker_engine", "docker_cgroup_driver", "nvidia_container_toolkit",
                "sha_ni"):  # fmt: skip
        assert v[rid] == "fail", rid
    assert v["cpus_on_gpu_numa_node"] == "fail"  # node 0 has 2 CPUs


def test_no_nvidia_smi_no_docker_offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(PROBE.shutil, "which", lambda name: None)
    r = PROBE.probe(host(tmp_path), fake({}), None, tmp_path, tmp_path)
    assert r["gpus"] == {"nvidia_smi": False, "count": 0, "devices": []}
    assert r["confidential_computing"] == {"read": False, "status": None, "lines": []}
    assert r["network"] is None
    v = verdicts(r)
    assert (v["gpu_model"], v["gpu_count"]) == ("fail", "fail")
    assert (v["cc_mode_off"], v["reach_ghcr.io"]) == ("unknown",) * 2
    assert v["docker_engine"] == "fail"  # bare metal without docker
    assert not any(k.startswith("pull_") for k in v)


def test_a_failing_section_does_not_stop_the_probe(tmp_path: Path) -> None:
    outputs = dict(OUTPUTS)
    query = next(k for k in outputs if k[1].startswith("--query-gpu"))
    outputs[query] = "not, a, csv\n"
    r = report(host(tmp_path), outputs)
    assert r["gpus"] == {"error": "ValueError"}
    assert verdicts(r)["gpu_model"] == "fail"


def test_versions_and_ranges() -> None:
    assert PROBE.version("6.8.0-62-generic") == (6, 8, 0)
    assert PROBE.version("v1.17.3") == (1, 17, 3)
    assert PROBE.version("unknown") is None
    assert PROBE.ranges("0-3,8") == [0, 1, 2, 3, 8]
    assert PROBE._device_kind(FIXTURE, "/dev/sda1") is None  # no sysfs entry for sda
    assert PROBE._device_kind(FIXTURE, "overlay") is None


def test_madvise_wipeonfork() -> None:
    result = PROBE.madvise_wipeonfork()
    assert set(result) == {"ok", "errno", "reason"}
    if sys.platform.startswith("linux"):
        assert result["ok"] or result["errno"]  # refused calls say why (gVisor refused it, #68)
    else:
        assert result == {"ok": False, "errno": None, "reason": "not linux"}


def test_scrub_drops_identifiers() -> None:
    """The G9 samples (an IPv4, an IPv6 and a MAC address) and the hostname leave the output;
    driver, kernel and toolkit versions, which look alike, stay."""
    leaks = ["node-7f3a", sample("SEC-5"), sample("SEC-6"), sample("SEC-7")]
    text = json.dumps({"a": " and ".join(leaks), "driver": "580.95.05",
                       "kernel": "6.8.0-62-generic", "ctk": "1.17.3"})  # fmt: skip
    out = PROBE.scrub(text, "node-7f3a")
    for leaked in leaks:
        assert leaked not in out
    for kept in ("580.95.05", "6.8.0-62-generic", "1.17.3"):
        assert kept in out


def test_main_prints_one_json_object_and_exits_on_failures(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(PROBE, "run", fake({}))
    monkeypatch.setattr(
        PROBE.probe,
        "__defaults__",
        (Path("/"), fake({}), None, None, tmp_path, "prover-h200", None),
    )
    assert PROBE.main(["--offline", "--work", str(tmp_path)]) == 1  # no GPU here
    captured = capsys.readouterr()
    doc = json.loads(captured.out)
    assert doc["probe_version"] == 2
    assert doc["profile"] == "prover-h200"
    assert "gpu_model" in doc["failed"]
    assert "FAIL     gpu_model" in captured.err
    assert str(tmp_path) not in captured.out  # the work path is a label, never printed
    assert str(Path.home()) not in captured.out or str(Path.home()) == "/"


# A Hugging Face Jobs `h200`-like container: one H200, no docker engine, a 23-CPU quota and a
# 256 GB memory limit, CC mode unread; the fixture's four CPUs stand in for the host's.
HOSTED_OUTPUTS = {k: v for k, v in OUTPUTS.items()
                  if k[0] == "nvidia-smi" and "conf-compute" not in k}  # fmt: skip
HOSTED_OUTPUTS[next(k for k in OUTPUTS if k[1].startswith("--query-gpu"))] = (
    "0, NVIDIA H200, 143771, 580.95.05, 00000000:17:00.0, Default\n"
)
HOSTED_OUTPUTS[("nvidia-smi", "--query-compute-apps=gpu_bus_id", "--format=csv,noheader")] = ""


def hosted_root(tmp_path: Path, quota: str = "2300000 100000", limit: int = 256 * 10**9) -> Path:
    root = host(tmp_path)
    (root / "sys/fs/cgroup/cpu.max").write_text(quota + "\n")
    (root / "sys/fs/cgroup/memory.max").write_text(f"{limit}\n")
    (root / "sys/fs/cgroup/cpu.stat").write_text("usage_usec 1\n")
    (root / "sys/fs/cgroup/memory.stat").write_text("anon 1\n")
    shutil.rmtree(root / "run/systemd")
    return root


def test_hosted_container_against_prover_h200_hosted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Docker, systemd, the OS and the disk kind are n/a; the quota and limit are read; 256 GB
    passes the profile's 200 GiB and fails FlashProve's 330 GB floor, which does not fail the
    probe; image pulls are not checked by a hosted job but reported."""
    monkeypatch.setattr(PROBE.shutil, "which", lambda name: None)
    r = report(hosted_root(tmp_path), HOSTED_OUTPUTS, "prover-h200-hosted", [0, 1, 2, 3])
    assert r["profile"] == "prover-h200-hosted"
    assert r["cgroup"]["cpu_quota_cpus"] == 23.0
    assert r["cgroup"]["memory_limit_bytes"] == 256 * 10**9
    assert r["cgroup"]["counters_readable"] == {
        "cpu.stat": True,
        "memory.stat": True,
        "memory.events": False,
        "memory.peak": False,
    }
    assert r["containers"]["docker_engine"] is None
    v = verdicts(r)
    for rid in ("work_disk_nvme", "os", "systemd", "docker_engine", "docker_cgroup_driver",
                "nvidia_container_toolkit"):  # fmt: skip
        assert v[rid] == "n/a", rid
    for rid in ("gpu_model", "gpu_count", "gpu_memory_mib", "gpu_idle", "cuda_driver_api",
                "cpu_quota", "host_memory_gib", "cgroup_v2", "proc1_environ"):  # fmt: skip
        assert v[rid] == "pass" or rid == "proc1_environ", rid  # /proc/1 is the test machine's
    assert v["cc_mode_off"] == "unknown"
    assert v["flashprove_commit_floor_gb"] == "fail"
    assert v["runs_as_root"] == "info"
    assert "flashprove_commit_floor_gb" in r["failed_flashprove"]
    assert "flashprove_commit_floor_gb" not in r["failed"]
    assert v["cpus_on_gpu_numa_node"] == "fail"  # 2 usable CPUs on node 0 < 15
    assert v["cpus_usable"] == "fail"  # 4 < 15 + 8


def test_hosted_affinity_and_low_quota(tmp_path: Path) -> None:
    """Only the CPUs this process may use count on the GPU's node; a quota below 15 fails."""
    r = report(hosted_root(tmp_path, quota="1400000 100000", limit=512 * 10**9), HOSTED_OUTPUTS,
               "prover-h200-hosted", [1, 2])  # fmt: skip
    assert r["numa"]["allowed_cpus_per_node"] == {"0": 1, "1": 1}
    assert r["cpu"]["allowed_cpus"] == 2
    v = verdicts(r)
    assert v["cpu_quota"] == "fail"
    assert v["flashprove_commit_floor_gb"] == "pass"  # an h200x2-like 512 GB limit
    assert "cpu_quota" in r["failed"]


def test_affinity_off_the_real_root() -> None:
    assert PROBE.affinity(FIXTURE) is None


def test_main_hosted_profile_exit_follows_profile_failures_only(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root, original = hosted_root(tmp_path), PROBE.probe

    def fixed(*args: Any, **kwargs: Any) -> dict[str, Any]:
        r: dict[str, Any] = original(root, fake(HOSTED_OUTPUTS), None, root, root,
                                     kwargs["profile"], list(range(4)))  # fmt: skip
        r["failed"] = []  # the fixture's four CPUs stand in for a host that meets the profile
        return r

    monkeypatch.setattr(PROBE, "probe", fixed)
    assert PROBE.main(["--offline", "--profile", "prover-h200-hosted"]) == 0
    captured = capsys.readouterr()
    assert "[flashprove]" in captured.err
    assert json.loads(captured.out)["failed_flashprove"]


def test_bound_gpu_with_numa_node_minus_one_fails(tmp_path: Path) -> None:
    """sysfs gives -1 (common in a VM): the harness refuses the GPU (GpuEnvironment, ENVIRONMENT
    "no NUMA node"), so the probe fails the row instead of reporting it unknown."""
    root = hosted_root(tmp_path)
    device = root / "sys/bus/pci/devices/0000:99:00.0"
    device.mkdir(parents=True)
    (device / "numa_node").write_text("-1\n")
    outputs = dict(HOSTED_OUTPUTS)
    outputs[next(k for k in outputs if k[1].startswith("--query-gpu"))] = (
        "0, NVIDIA H200, 143771, 580.95.05, 00000000:99:00.0, Default\n"
    )
    r = report(root, outputs, "prover-h200-hosted", [0, 1, 2, 3])
    assert r["gpus"]["devices"][0]["numa_node"] is None
    row = next(row for row in r["requirements"] if row["id"] == "cpus_on_gpu_numa_node")
    assert (row["status"], row["found"]) == ("fail", "no NUMA node")
    assert "refuses" in row["need"]
    assert "cpus_on_gpu_numa_node" in r["failed"]


def test_container_without_docker_under_the_default_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run by hand in a provider's container with the default profile: the docker, systemd, OS
    and disk-kind rows are n/a, and one row says to probe with the hosted profile."""
    monkeypatch.setattr(PROBE.shutil, "which", lambda name: None)
    root = hosted_root(tmp_path)
    (root / ".dockerenv").touch()
    r = report(root, HOSTED_OUTPUTS, "prover-h200", [0, 1, 2, 3])
    assert r["system"]["container"] is True
    v = verdicts(r)
    for rid in ("work_disk_nvme", "os", "systemd", "docker_engine", "docker_cgroup_driver",
                "nvidia_container_toolkit"):  # fmt: skip
        assert v[rid] == "n/a", rid
    row = next(row for row in r["requirements"] if row["id"] == "bare_metal")
    assert row["status"] == "fail"
    assert "--profile prover-h200-hosted" in row["need"]
    assert r["failed"].count("bare_metal") == 1
    assert not {"docker_engine", "systemd", "os"} & set(r["failed"])


def test_container_markers(tmp_path: Path) -> None:
    root = tmp_path / "r"
    (root / "proc/1").mkdir(parents=True)
    assert PROBE.in_container(root) is False  # no marker, no first process name
    (root / "proc/1/comm").write_text("systemd\n")
    assert PROBE.in_container(root) is False
    (root / "proc/1/comm").write_text("bash\n")
    assert PROBE.in_container(root) is True
    (root / "proc/1/comm").unlink()
    (root / "run").mkdir()
    (root / "run/.containerenv").touch()
    assert PROBE.in_container(root) is True


def test_home_writable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert PROBE._home_writable() is True
    monkeypatch.setenv("HOME", str(tmp_path / "missing"))
    assert PROBE._home_writable() is False
    monkeypatch.delenv("HOME")
    assert PROBE._home_writable() is False
