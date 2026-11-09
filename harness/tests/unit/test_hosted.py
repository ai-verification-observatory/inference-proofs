"""RFC-0006 §Hosted execution: the hosted runner, its machine-record probes, the hosted profile's
conformance checks and the container cgroup reader."""

import copy
import functools
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from iproofs import adapter as adapter_mod
from iproofs import cli
from iproofs.adapter import HostedRunner, image_environment
from iproofs.errors import IProofsError
from iproofs.measure import ContainerCgroupReader, NullCgroupReader, select_readers
from iproofs.model import (
    ContainerRuntime,
    Disk,
    GpuSpec,
    HostedRuntime,
    OsSpec,
    ProverCpu,
    ProverProfile,
)
from iproofs.provenance import Host, check_profile
from iproofs.runner import GpuEnvironment
from iproofs.schema import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "harness/tests/fixtures/host"
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
GIB = 1024**3
HOSTED = ProverProfile(
    kind="prover",
    gpu=GpuSpec(model="NVIDIA H100 80GB HBM3", form_factor="SXM", count=1, memory_mib_min=80000),
    cpu=ProverCpu(logical_cpus_on_gpu_numa_node=24, logical_cpus_total_min=32),
    host_memory_gib_min=330,
    disk=Disk(type="any", free_gib_min=500),
    os=OsSpec(id="ubuntu", version_id="24.04"),
    kernel_min="5.19",
    driver="610.57.04",
    container_runtime=HostedRuntime(kind="hosted", cgroup_version="2"),
)
RECORD: dict[str, Any] = {
    "gpu": {"model": "NVIDIA H100 80GB HBM3", "count_visible": 1, "memory_total_mib": 81559,
            "bound_index": 0, "numa_node": 1, "driver_version": "610.57.04"},
    "cpu": {"logical_cpus": 208, "cgroup_quota_cpus": 24.96},
    "memory": {"available_bytes_at_start": 1700 * GIB, "cgroup_limit_bytes": 601 * GIB},
    "disk": {"free_bytes_at_start": 700 * GIB},
    "kernel": {"release": "6.8.0-62-generic"},
    "container": {"execution": "hosted", "cgroup_version": "2"},
}  # fmt: skip


def checks(record: dict[str, Any], profile: ProverProfile = HOSTED) -> list[str]:
    return [f.check for f in check_profile(record, profile, numa_node_cpus=104, gpu_processes=0)]


def with_(path: str, value: object) -> dict[str, Any]:
    record = copy.deepcopy(RECORD)
    section, key = path.split(".")
    record[section][key] = value
    return record


def test_hosted_record_conforms_without_a_host_os() -> None:
    """The image's /etc/os-release is not the host's, so the OS check does not apply."""
    assert checks(RECORD) == []


@pytest.mark.parametrize(
    ("path", "value", "check"),
    [
        ("container.execution", None, "PC-RUNTIME"),
        ("container.cgroup_version", "1", "PC-CGROUP"),
        ("cpu.cgroup_quota_cpus", 8.0, "PC-CPU-QUOTA"),
        ("memory.cgroup_limit_bytes", 200 * GIB, "PC-MEM"),
    ],
)
def test_hosted_checks_fail(path: str, value: object, check: str) -> None:
    assert checks(with_(path, value)) == [check]


def test_hosted_record_fails_a_docker_profile() -> None:
    docker = copy.copy(HOSTED)
    object.__setattr__(
        docker,
        "container_runtime",
        ContainerRuntime(
            docker_engine_min="25.0", nvidia_container_toolkit_min="1.17", cgroup_driver="systemd"
        ),
    )
    assert "PC-RUNTIME" in checks(RECORD, docker)


def hosted_root(tmp_path: Path, *, v2: bool = True) -> Path:
    root = tmp_path / "root"
    shutil.copytree(FIXTURE, root)
    (root / "proc/self").mkdir(parents=True)
    kind = "cgroup2" if v2 else "tmpfs"
    (root / "proc/self/mounts").write_text(f"cgroup /sys/fs/cgroup {kind} ro,nosuid 0 0\n")
    (root / "sys/fs/cgroup").mkdir(parents=True)
    (root / "sys/fs/cgroup/cpu.max").write_text("2495999 100000\n")
    (root / "sys/fs/cgroup/memory.max").write_text(f"{601 * GIB}\n")
    return root


def test_hosted_probes(tmp_path: Path) -> None:
    host = Host(hosted_root(tmp_path), run=lambda _: None, hosted=True)
    assert host.container() == {"execution": "hosted", "cgroup_version": "2"}
    assert host.os_release() == {}
    assert host.cpu()["cgroup_quota_cpus"] == 24.96
    assert host.memory()["cgroup_limit_bytes"] == 601 * GIB
    assert Host(hosted_root(tmp_path / "v1", v2=False), hosted=True).container() == {
        "execution": "hosted",
        "cgroup_version": "1",
    }


def test_no_quota_or_limit_recorded_without_one(tmp_path: Path) -> None:
    root = hosted_root(tmp_path)
    (root / "sys/fs/cgroup/cpu.max").write_text("max 100000\n")
    (root / "sys/fs/cgroup/memory.max").write_text("max\n")
    host = Host(root, run=lambda _: None)
    assert "cgroup_quota_cpus" not in host.cpu()
    assert "cgroup_limit_bytes" not in host.memory()


def test_image_environment_drops_the_providers_additions() -> None:
    environ = "\0".join([
        "PATH=/usr/bin", "IPROOFS_ADAPTER_COMMIT=abc", "VAST_CONTAINERLABEL=C.1",
        "CONTAINER_API_KEY=x", "HF_TOKEN=y", "HOSTNAME=h", "GPU_COUNT=1", "PUBLIC_IPADDR=z",
        "SSH_PUBLIC_KEY=k", "NOVALUE", "IPROOFS_DEV_IMAGE=r@sha256:0",
    ])  # fmt: skip
    assert image_environment(environ) == {"PATH": "/usr/bin", "IPROOFS_ADAPTER_COMMIT": "abc"}


def test_hosted_command(tmp_path: Path) -> None:
    io, models = tmp_path / "io", tmp_path / "models"
    ro = io / "state" / "verifier.bin"
    ro.parent.mkdir(parents=True)
    ro.write_text("v")
    runner = HostedRunner(["python3", "/opt/x/entrypoint"], REGISTRY, {"PATH": "/usr/bin"})
    argv, env = runner._command("prove", io, models, 0, "104,105", [(ro, "/io/state/v")])
    drop = ["setpriv"] if os.geteuid() == 0 else []
    assert argv[: 3 + len(drop)] == ["taskset", "-c", "104,105", *drop]
    assert argv[-5:] == ["python3", "/opt/x/entrypoint", "prove", "/io/job.json", "/io/out.json"]
    assert env == {"PATH": "/usr/bin", "IPROOFS_IO": str(io), "IPROOFS_MODELS": str(models),
                   "CUDA_DEVICE_ORDER": "PCI_BUS_ID", "CUDA_VISIBLE_DEVICES": "0"}  # fmt: skip
    assert ro.stat().st_mode & 0o777 == 0o444
    _, env = runner._command("verify", io, models, None, "0", [])
    assert env["CUDA_VISIBLE_DEVICES"] == ""
    assert "IPROOFS_MODELS" not in env
    assert runner._recorded(["taskset", "x"]) == ("hosted", "taskset", "x")


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="taskset is Linux only")
def test_hosted_runner_runs_the_fake_adapter(tmp_path: Path) -> None:
    io = tmp_path / "io"
    io.mkdir()
    (io / "job.json").write_text(
        '{"schema": "adapter-job/1", "contract": "adapter/1", "subcommand": "info",'
        ' "run_id": "r", "workload": {"id": "fake-tiny-ci", "version": 1}}'
    )
    entry = ["python3", str(ROOT / "systems/fake/entrypoint")]
    runner = HostedRunner(entry, REGISTRY, {"PATH": "/usr/bin:/bin"})
    result = runner.run("local/fake@sha256:" + "0" * 64, "info", io, models_dir=None, gpu=None,
                        cpuset="0", mems="0", memory=None, timeout_s=60)  # fmt: skip
    assert result.exit_code == 0, result.stderr_tail
    assert result.argv[0] == "hosted"


def test_local_image() -> None:
    """RFC-0014: --image is recorded under local/ (digest_kind config). An ID names a local
    build of the system; in hosted mode a full reference names the image the provider started,
    with the adapter installed from the checkout, never an adapter image that was not built."""
    digest = "sha256:" + "a" * 64
    for hosted in (False, True):
        assert cli.local_image("ref-serve", digest, hosted=hosted) == (f"local/ref-serve@{digest}")
    engine = f"docker.io/vllm/vllm-openai@{digest}"
    assert cli.local_image("ref-serve", engine, hosted=True) == f"local/{engine}"
    assert cli.local_image("x", f"local/{engine}", hosted=True) == f"local/{engine}"
    with pytest.raises(IProofsError, match="only with --hosted"):
        cli.local_image("ref-serve", engine, hosted=False)
    with pytest.raises(IProofsError, match="is not <repository>@sha256"):
        cli.local_image("ref-serve", "docker.io/vllm/vllm-openai:v0.32.0", hosted=True)
    with pytest.raises(IProofsError, match="is not <repository>@sha256"):
        cli.local_image("ref-serve", "abc", hosted=False)


def test_entrypoint_argv() -> None:
    dockerfile = (ROOT / "systems/ref-recompute/Dockerfile").read_text()
    assert cli.entrypoint_argv(dockerfile) == ["python3", "/opt/ref-serve/entrypoint"]
    with pytest.raises(IProofsError, match="no exec-form ENTRYPOINT"):
        cli.entrypoint_argv("ENTRYPOINT python3 /x\n")


def test_select_readers_hosted(tmp_path: Path) -> None:
    yes = lambda: True  # noqa: E731
    assert isinstance(select_readers(gpu_profile=False, hosted=True), NullCgroupReader)
    with pytest.raises(IProofsError, match="no cgroup v2 counters"):
        select_readers(gpu_profile=True, hosted=True, nvml=yes, cgroup_root=tmp_path)
    (tmp_path / "cpu.stat").write_text("usage_usec 2500000\n")
    (tmp_path / "memory.stat").write_text("anon 4096\n")
    (tmp_path / "memory.events").write_text("oom_kill 0\n")
    (tmp_path / "memory.peak").write_text("9999\n")
    reader = select_readers(gpu_profile=True, hosted=True, nvml=yes, cgroup_root=tmp_path)
    assert isinstance(reader, ContainerCgroupReader)
    assert (reader.cpu_usage_usec(), reader.memory_anon(), reader.oom_kills()) == (2500000, 4096, 0)
    assert reader.memory_peak() is None  # the container's peak since it started, not a step's
    with pytest.raises(IProofsError, match="not implemented"):
        select_readers(gpu_profile=True, nvml=yes)


def test_gpu_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fixture host has four CPUs: one prover and one verifier CPU stand in for 24 and 8."""
    from iproofs import provenance, runner  # noqa: PLC0415

    small = functools.partial(provenance.select_cpus, n_verifier=1)
    monkeypatch.setattr(runner, "select_cpus", small)
    host = Host(FIXTURE, run=lambda _: None, nvml=lambda i: {"pci_bus_id": "00000000:17:00.0"})
    env = GpuEnvironment(0, host, n_prover=1)
    prover, mems = env.cpus("prover")
    assert prover == "0"
    assert mems == "0"
    assert env.gpu() == 0
    assert env.host() is host
    assert set(prover.split(",")).isdisjoint(env.cpus("verifier")[0].split(","))
    lost = Host(FIXTURE, run=lambda _: None, nvml=lambda i: {"pci_bus_id": "00000000:99:00.0"})
    with pytest.raises(IProofsError, match="no NUMA node"):
        GpuEnvironment(0, lost, n_prover=1)


def test_disk_of_a_results_directory_not_made_yet(tmp_path: Path) -> None:
    host = Host(FIXTURE, run=lambda _: None, dev_of=lambda _: (259, 0))
    free = host.disk(tmp_path / "results" / "v0.1")["free_bytes_at_start"]
    assert isinstance(free, int)
    assert free > 0


def test_hosted_call_opens_the_parents(tmp_path: Path) -> None:
    closed = tmp_path / "work"
    io = closed / "results" / "io"
    io.mkdir(parents=True)
    closed.chmod(0o744)
    runner = HostedRunner(["python3", "/opt/x/entrypoint"], REGISTRY, {})
    runner._command("info", io, None, None, "0", [])
    assert closed.stat().st_mode & 0o777 == 0o745


def test_fresh_tmp_removes_only_the_adapters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What the adapter uid left in /tmp goes before the next call, as a new docker tmpfs would;
    anything else in /tmp stays."""
    from iproofs import adapter  # noqa: PLC0415

    (tmp_path / "cache").mkdir()
    (tmp_path / "cache/x").write_text("x")
    (tmp_path / "lock").write_text("")
    monkeypatch.setattr(adapter, "ADAPTER_UID", str(os.geteuid()))
    adapter.fresh_tmp(tmp_path)
    assert list(tmp_path.iterdir()) == []
    (tmp_path / "theirs").write_text("")
    monkeypatch.setattr(adapter, "ADAPTER_UID", str(os.geteuid() + 1))
    adapter.fresh_tmp(tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == ["theirs"]


def test_hosted_paths_are_absolute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With `--results results` the io dir is relative; an adapter that runs upstream from
    another directory needs the absolute path, as docker's bind mount gives it."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "results/io").mkdir(parents=True)
    (tmp_path / "models").mkdir()
    runner = HostedRunner(["python3", "/opt/x/entrypoint"], REGISTRY, {})
    _, env = runner._command("prove", Path("results/io"), Path("models"), 0, "0", [])
    assert env["IPROOFS_IO"] == str((tmp_path / "results/io").resolve())
    assert env["IPROOFS_MODELS"] == str((tmp_path / "models").resolve())


def test_io_dir_as_the_adapter_uid_stays_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A job that already runs as the adapter's uid leaves the io dir as created: no folder below
    it is writable by others, which FlashProve's calibrate.py refuses (HF Jobs, 2026-11-08)."""
    io = tmp_path / "io"
    (io / "fit").mkdir(parents=True)
    for d in (io, io / "fit"):
        d.chmod(0o755)
    monkeypatch.setattr(os, "geteuid", lambda: int(adapter_mod.ADAPTER_UID))
    adapter_mod.give_io_to_adapter(io)
    for d in (io, io / "fit"):
        assert d.stat().st_mode & 0o7777 == 0o755


def test_io_dir_as_another_uid_is_open_with_sticky_bit(tmp_path: Path) -> None:
    """A development host running as itself opens the io dirs so the container can write, with
    the sticky bit, so no other account can replace a folder it does not own."""
    io = tmp_path / "io"
    (io / "fit").mkdir(parents=True)
    (io / "job.json").write_text("{}")
    me = os.geteuid()
    if me in (0, int(adapter_mod.ADAPTER_UID)):
        pytest.skip("needs a uid that is neither root nor the adapter's")
    adapter_mod.give_io_to_adapter(io)
    for d in (io, io / "fit"):
        assert d.stat().st_mode & 0o7777 == 0o1777
    assert (io / "job.json").stat().st_mode & 0o7777 != 0o1777
