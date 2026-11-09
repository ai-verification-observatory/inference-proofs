#!/usr/bin/env python3
"""Probe of a GPU host against `prover-h200` (bare metal, docker) or `prover-h200-hosted` (a
container a provider starts), before the harness is installed (docs/runbooks/h200-host.md,
docs/runbooks/hf-jobs.md).

Runs in a few seconds with the Python standard library only and prints one JSON object on
stdout: the GPUs (nvidia-smi), their Confidential Computing mode, the CPU and its SHA
extensions, the NUMA layout and the CPUs this process may use, the CPU quota and memory limit of
its cgroup, memory, free disk per path, the kernel, cgroup and systemd, Docker Engine and its
cgroup driver, the NVIDIA Container Toolkit, whether madvise(MADV_WIPEONFORK) succeeds, whether
it runs as root, and whether ghcr.io, huggingface.co and the pinned adapter images answer.

`requirements` compares each value with the chosen profile in reference/v0.1.yaml (RFC-0006
§H200 profiles), scope `profile`, and with FlashProve's own machine needs
(systems/flashprove/README.md), scope `flashprove`. In a container without a docker engine the
docker, systemd, OS and disk-kind rows are `n/a`: under the hosted profile because the provider
started the container, and under `prover-h200` because a container is not a bare-metal host
(the row `bare_metal` then fails and says to pass `--profile prover-h200-hosted`). The GPU the
job would bind needs a NUMA node, as `iproofs run --gpu` refuses a GPU without one (RFC-0006
§CPU and memory selection), so `cpus_on_gpu_numa_node` fails when sysfs gives it none. The same
verdicts go to
stderr one per line. `failed` lists the profile's failures and `failed_flashprove` FlashProve's;
the exit status is 1 when `failed` is not empty, else 0.

It prints no hostname, IP address, MAC address, serial, UUID, PCI address, user name, uid or
path (AGENTS.md rule 7): the PCI address is read only to find a GPU's NUMA node, paths are
labels, and a final scrub drops the hostname and any IP or MAC pattern.

    python3 docs/runbooks/host-probe.py --work /path/on/the/nvme > probe.json
    python3 docs/runbooks/host-probe.py --profile prover-h200-hosted --work "$WORK" > probe.json
"""

import argparse
import contextlib
import ctypes
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

PROBE_VERSION = 2
GIB = 1024**3
MADV_WIPEONFORK = 18  # linux/mman.h; FlashProve's cp_commit and cp_prove need it
VERIFIER_CPUS = 8  # verifier-cpu, emulated on the prover host (RFC-0006)
# The H200 profiles of reference/v0.1.yaml (test_host_probe.py holds them equal).
PROFILES: dict[str, dict[str, Any]] = {
    "prover-h200": {
        "id": "prover-h200",
        "hosted": False,
        "gpu_model": "NVIDIA H200",
        "gpu_memory_mib_min": 140000,
        "gpu_count": 1,
        "logical_cpus_on_gpu_numa_node": 24,
        "logical_cpus_total_min": 32,
        "host_memory_gib_min": 330,
        "disk_free_gib_min": 500,
        "disk_nvme": True,
        "os": ("ubuntu", "24.04"),
        "kernel_min": "5.19",
        "driver": "unpinned",
        "docker_engine_min": "25.0",
        "nvidia_container_toolkit_min": "1.17",
        "cgroup_driver": "systemd",
    },
    "prover-h200-hosted": {
        "id": "prover-h200-hosted",
        "hosted": True,
        "gpu_model": "NVIDIA H200",
        "gpu_memory_mib_min": 140000,
        "gpu_count": 1,
        "logical_cpus_on_gpu_numa_node": 15,
        "logical_cpus_total_min": 23,
        "host_memory_gib_min": 200,
        "disk_free_gib_min": 500,
        "disk_nvme": False,
        "kernel_min": "5.19",
        "driver": "unpinned",
    },
    # RFC-0006 R6: the hosted serving profiles, for production serving (RFC-0015 SRV-6)
    "serving-h200x1-hosted": {
        "id": "serving-h200x1-hosted",
        "hosted": True,
        "gpu_model": "NVIDIA H200",
        "gpu_memory_mib_min": 140000,
        "gpu_count": 1,
        "logical_cpus_on_gpu_numa_node": 15,
        "logical_cpus_total_min": 23,
        "host_memory_gib_min": 200,
        "disk_free_gib_min": 500,
        "disk_nvme": False,
        "kernel_min": "5.19",
        "driver": "unpinned",
    },
    "serving-h200x4-hosted": {
        "id": "serving-h200x4-hosted",
        "hosted": True,
        "gpu_model": "NVIDIA H200",
        "gpu_memory_mib_min": 140000,
        "gpu_count": 4,
        "logical_cpus_on_gpu_numa_node": 15,
        "logical_cpus_total_min": 92,
        "host_memory_gib_min": 800,
        "disk_free_gib_min": 1000,
        "disk_nvme": False,
        "kernel_min": "5.19",
        "driver": "unpinned",
    },
}
CUDA_DRIVER_MIN = "12.9"  # SASH's image is CUDA 12.9 (systems/sash/README.md, RFC-0006 Q3)
CUDA_DRIVER_MIN_FLASHPROVE = "13.2"  # FlashProve's image is CUDA 13.2 Update 2
FLASHPROVE_COMMIT_B = 330 * 10**9  # run.sh does not start commit below 330 GB available
# (external, reported, systems/flashprove/README.md §Machine needs)
URLS = {
    "ghcr.io": "https://ghcr.io/v2/",
    "huggingface.co": "https://huggingface.co/api/models?limit=1",
    "github.com": "https://github.com/",
    "pypi.org": "https://pypi.org/simple/",
}
TOOLS = ("python3", "git", "uv", "taskset", "setpriv", "docker", "nvidia-smi", "nvidia-ctk",
         "systemd-run", "systemctl")  # fmt: skip
REPO = Path(__file__).resolve().parents[2]  # the checkout, for systems/*/system.yaml

Runner = Callable[[list[str]], str | None]
Opener = Callable[..., Any]


def run(argv: list[str]) -> str | None:
    """stdout of a command that exited 0, else None."""
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None


def read(root: Path, rel: str) -> str | None:
    try:
        return (root / rel.lstrip("/")).read_text()
    except (OSError, UnicodeDecodeError):
        return None


def ranges(text: str | None) -> list[int]:
    """ "0-3,8" -> [0, 1, 2, 3, 8]."""
    out: list[int] = []
    for part in filter(None, (text or "").strip().split(",")):
        low, _, high = part.partition("-")
        out += range(int(low), int(high or low) + 1)
    return out


def version(text: str | None) -> tuple[int, ...] | None:
    """The leading dotted number of a version string: "6.8.0-62-generic" -> (6, 8, 0)."""
    found = re.match(r"\s*v?(\d+(?:\.\d+)*)", text or "")
    return tuple(int(p) for p in found.group(1).split(".")) if found else None


def guarded(section: Callable[[], Any]) -> Any:
    """A section that fails reports its error class, and the probe goes on."""
    try:
        return section()
    except Exception as e:
        return {"error": type(e).__name__}


def in_container(root: Path) -> bool:
    """Whether this process runs in a container: a container runtime's marker file, a
    Kubernetes service variable, or a first process that is not an init system."""
    if (root / ".dockerenv").exists() or (root / "run/.containerenv").exists():
        return True
    if root == Path("/") and "KUBERNETES_SERVICE_HOST" in os.environ:
        return True
    comm = read(root, "proc/1/comm")
    return comm is not None and comm.strip() not in ("systemd", "init")


def affinity(root: Path) -> list[int] | None:
    """The CPUs this process may run on (a provider's cpuset narrows them); None off the real
    root or where the call does not exist."""
    if root != Path("/") or not hasattr(os, "sched_getaffinity"):
        return None
    return sorted(os.sched_getaffinity(0))


# ---------------------------------------------------------------- sections


def gpus(root: Path, runner: Runner) -> dict[str, Any]:
    query = "index,name,memory.total,driver_version,pci.bus_id,compute_mode"
    out = runner(["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"])
    if out is None:
        return {"nvidia_smi": False, "count": 0, "devices": []}
    apps = runner(["nvidia-smi", "--query-compute-apps=gpu_bus_id", "--format=csv,noheader"])
    busy = [b.strip().lower() for b in (apps or "").splitlines() if b.strip()]
    devices = []
    for line in filter(None, (raw.strip() for raw in out.splitlines())):
        index, name, memory, driver, bus, mode = (f.strip() for f in line.split(","))
        domain, _, rest = bus.partition(":")  # NVML's 8-digit domain, sysfs's 4 (RFC-0006)
        sysfs = f"{int(domain, 16):04x}:{rest}".lower() if rest else bus.lower()
        node = read(root, f"sys/bus/pci/devices/{sysfs}/numa_node")
        devices.append({
            "index": int(index), "name": name, "memory_total_mib": int(memory),
            "driver_version": driver, "compute_mode": mode,
            "numa_node": int(node) if node is not None and int(node) >= 0 else None,
            "compute_processes": None if apps is None else busy.count(bus.lower()),
        })  # fmt: skip
    header = runner(["nvidia-smi"]) or ""
    cuda = re.search(r"CUDA Version:\s*([0-9.]+)", header)
    return {"nvidia_smi": True, "count": len(devices), "devices": devices,
            "cuda_driver_api": cuda.group(1) if cuda else None}  # fmt: skip


def confidential_computing(runner: Runner) -> dict[str, Any]:
    """NVIDIA Confidential Computing state as `nvidia-smi conf-compute` reports it. The lines are
    kept (they hold modes and states only); `status` is the word after "CC status:"."""
    lines: list[str] = []
    for flag in ("-f", "-grs"):  # feature status; GPUs ready state
        out = runner(["nvidia-smi", "conf-compute", flag])
        lines += [ln.strip() for ln in (out or "").splitlines() if ln.strip()][:4]
    found = re.search(r"CC status:\s*(\w+)", "\n".join(lines), re.I)
    return {"read": bool(lines), "status": found.group(1).lower() if found else None,
            "lines": lines}  # fmt: skip


def cpu(root: Path, allowed: list[int] | None) -> dict[str, Any]:
    info = read(root, "proc/cpuinfo") or ""
    model = re.search(r"^model name\s*:\s*(.+)$", info, re.M)
    flags = re.search(r"^flags\s*:\s*(.+)$", info, re.M)
    cores: set[tuple[str, str]] = set()
    ids: list[int] = []
    for topo in sorted((root / "sys/devices/system/cpu").glob("cpu[0-9]*/topology")):
        cores.add(((topo / "physical_package_id").read_text().strip(),
                   (topo / "core_id").read_text().strip()))  # fmt: skip
        ids.append(int(topo.parent.name.removeprefix("cpu")))
    online = ranges(read(root, "sys/devices/system/cpu/online")) or sorted(ids)
    smt = read(root, "sys/devices/system/cpu/smt/active")
    return {
        "model": model.group(1).strip() if model else None,
        "arch": platform.machine(),
        "sha_ni": bool(flags and "sha_ni" in flags.group(1).split()),
        "logical_cpus": len(online),
        "allowed_cpus": len(online if allowed is None else allowed),
        "sockets": len({c[0] for c in cores}) or None,
        "physical_cores": len(cores) or None,
        "smt_active": None if smt is None else smt.strip() == "1",
    }


def numa(root: Path, allowed: list[int] | None) -> dict[str, Any]:
    """Logical CPUs per node, and those of them this process may use."""
    nodes, usable = {}, {}
    for cpulist in sorted((root / "sys/devices/system/node").glob("node[0-9]*/cpulist")):
        name, ids = cpulist.parent.name.removeprefix("node"), ranges(cpulist.read_text())
        nodes[name] = len(ids)
        usable[name] = len(ids if allowed is None else set(ids) & set(allowed))
    return {"nodes": len(nodes), "logical_cpus_per_node": nodes, "allowed_cpus_per_node": usable}


def memory(root: Path) -> dict[str, Any]:
    kib = dict(re.findall(r"^(\w+):\s+(\d+) kB", read(root, "proc/meminfo") or "", re.M))
    return {"total_bytes": int(kib.get("MemTotal", 0)) * 1024 or None,
            "available_bytes": int(kib.get("MemAvailable", 0)) * 1024 or None}  # fmt: skip


def cgroup(root: Path) -> dict[str, Any]:
    """The CPU quota and memory limit of this process's cgroup, and which of the counters the
    hosted runner reads (RFC-0011) are readable."""
    base = root / "sys/fs/cgroup"
    quota, _, period = (read(root, "sys/fs/cgroup/cpu.max") or "max").strip().partition(" ")
    limit = (read(root, "sys/fs/cgroup/memory.max") or "").strip()
    names = ("cpu.stat", "memory.stat", "memory.events", "memory.peak")
    return {
        "version": "2" if (base / "cgroup.controllers").is_file() else
                   "1" if base.is_dir() else None,
        "cpu_quota_cpus": round(int(quota) / int(period), 2) if quota != "max" and period else None,
        "memory_limit_bytes": int(limit) if limit.isdigit() else None,
        "counters_readable": {n: read(root, f"sys/fs/cgroup/{n}") is not None for n in names},
    }  # fmt: skip


def _mount_of(path: Path, mounts: str) -> tuple[str, str, str]:
    """(mount point, device, file system type) of the longest mount point holding `path`."""
    longest = ("", "", "")
    for fields in (m.split() for m in mounts.splitlines()):
        if len(fields) > 2 and (str(path) + "/").startswith(fields[1].rstrip("/") + "/"):
            longest = max(longest, (fields[1], fields[0], fields[2]), key=lambda b: len(b[0]))
    return longest


def _device_kind(root: Path, device: str) -> str | None:
    """nvme, ssd or hdd for a /dev/<block> mount source; the device name is not printed."""
    name = device.removeprefix("/dev/")
    if not device.startswith("/dev/") or "/" in name:
        return None
    if name.startswith("nvme"):
        return "nvme"
    base = re.sub(r"\d+$", "", name)
    rotational = read(root, f"sys/block/{base}/queue/rotational")
    return None if rotational is None else ("hdd" if rotational.strip() == "1" else "ssd")


def _writable(path: Path) -> bool:
    try:
        with tempfile.NamedTemporaryFile(dir=path):
            return True
    except OSError:
        return False


def disks(root: Path, paths: dict[str, Path]) -> dict[str, Any]:
    """Free space, file system, device kind and write access per label (`work`, `/`, `/tmp`,
    `docker_root`); the paths themselves are not printed."""
    mounts = read(root, "proc/self/mounts") or ""
    out = {}
    for label, path in paths.items():
        if not path.is_dir():
            out[label] = {"exists": False}
            continue
        st = os.statvfs(path)
        _, device, fs_type = _mount_of(path.resolve(), mounts)
        out[label] = {"exists": True, "free_bytes": st.f_bavail * st.f_frsize,
                      "fs_type": fs_type or None, "device_kind": _device_kind(root, device),
                      "writable": _writable(path)}  # fmt: skip
    return out


def _home_writable() -> bool:
    """Whether $HOME is a writable directory (an image user without a passwd entry may get /);
    huggingface_hub keeps its cache and locks under it unless HF_HOME is set."""
    home = os.environ.get("HOME")
    return bool(home) and Path(home).is_dir() and _writable(Path(home))


def system(root: Path) -> dict[str, Any]:
    osr = dict(re.findall(r'^(\w+)="?([^"\n]*)"?$', read(root, "etc/os-release") or "", re.M))
    return {
        "os_id": osr.get("ID"),
        "os_version_id": osr.get("VERSION_ID"),
        "kernel_release": platform.release(),
        "gvisor": "gvisor" in (platform.release() + (read(root, "proc/version") or "")).lower(),
        "systemd_running": (root / "run/systemd/system").is_dir(),
        "root": os.geteuid() == 0,
        "container": in_container(root),
        "home_writable": _home_writable() if root == Path("/") else None,
        "proc1_environ_readable": read(root, "proc/1/environ") is not None,
        "python": platform.python_version(),
        "tools": {t: shutil.which(t) is not None for t in TOOLS},
    }


def containers(runner: Runner) -> dict[str, Any]:
    engine = runner(["docker", "version", "--format", "{{.Server.Version}}"])
    info = runner(["docker", "info", "--format",
                   "{{.CgroupDriver}} {{.CgroupVersion}} {{json .Runtimes}}"])  # fmt: skip
    driver, cg_version, runtimes = [*(info or "").strip().split(" ", 2), "", ""][:3]
    ctk = runner(["nvidia-ctk", "--version"]) or ""
    found = re.search(r"version\s+v?(\d+(?:\.\d+)+)", ctk, re.I)
    return {
        "docker_engine": engine.strip() if engine else None,
        "cgroup_driver": driver or None,
        "cgroup_version": cg_version or None,
        "nvidia_runtime": "nvidia" in runtimes if runtimes else None,
        "nvidia_container_toolkit": found.group(1) if found else None,
    }


def madvise_wipeonfork() -> dict[str, Any]:
    """madvise(MADV_WIPEONFORK) on one anonymous page, as FlashProve calls it at its start."""
    if not sys.platform.startswith("linux"):
        return {"ok": False, "errno": None, "reason": "not linux"}
    libc = ctypes.CDLL(None, use_errno=True)
    libc.mmap.restype = ctypes.c_void_p
    libc.mmap.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int,
                          ctypes.c_int, ctypes.c_long)  # fmt: skip
    libc.madvise.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int)
    libc.munmap.argtypes = (ctypes.c_void_p, ctypes.c_size_t)
    size = 4096
    addr = libc.mmap(None, size, 0x1 | 0x2, 0x02 | 0x20, -1, 0)  # RW, MAP_PRIVATE|ANONYMOUS
    if addr in (None, ctypes.c_void_p(-1).value):
        return {"ok": False, "errno": os.strerror(ctypes.get_errno()), "reason": "mmap failed"}
    try:
        rc = libc.madvise(addr, size, MADV_WIPEONFORK)
        err = ctypes.get_errno()
    finally:
        libc.munmap(addr, size)
    return {"ok": rc == 0, "errno": None if rc == 0 else os.strerror(err), "reason": None}


def _status(opener: Opener, url: str) -> int | str:
    """The HTTP status (an error status still means the host answered), or the error class."""
    try:
        with opener(url, timeout=15) as resp:
            return int(resp.status)
    except urllib.error.HTTPError as e:
        return int(e.code)
    except Exception as e:  # no address or reason is printed, only the error class
        return type(e).__name__


def images(repo: Path) -> list[str]:
    """The pinned adapter image repositories of systems/*/system.yaml, without the registry."""
    found = set()
    for path in sorted(repo.glob("systems/*/system.yaml")):
        name = re.search(r'^\s+repository:\s*"?ghcr\.io/([^"\s]+)"?', path.read_text(), re.M)
        if name:
            found.add(name.group(1))
    return sorted(found)


def network(opener: Opener, repositories: list[str]) -> dict[str, Any]:
    """Each host's HTTP status, and whether ghcr.io grants an anonymous pull token per image
    (200: public; 401 or 403: a login is needed)."""
    out: dict[str, Any] = {name: _status(opener, url) for name, url in URLS.items()}
    out["anonymous_pull"] = {
        r: _status(opener, f"https://ghcr.io/token?scope=repository:{r}:pull") == 200
        for r in repositories
    }
    return out


# ---------------------------------------------------------------- verdicts


def _verdict(ok: bool | None) -> str:
    return "unknown" if ok is None else "pass" if ok else "fail"


def _at_least(found: str | None, need: str) -> bool | None:
    have = version(found)
    return None if have is None else have >= (version(need) or ())


def _section(report: dict[str, Any], name: str) -> dict[str, Any]:
    found = report.get(name)
    return found if isinstance(found, dict) and "error" not in found else {}


def _gpu(report: dict[str, Any], p: dict[str, Any]) -> dict[str, Any] | None:
    """The H200 the job would bind: idle, then the most usable CPUs on its NUMA node, then
    index."""
    devices = _section(report, "gpus").get("devices", [])
    per_node = _section(report, "numa").get("allowed_cpus_per_node", {})
    fits = [d for d in devices if d["name"] == p["gpu_model"]]
    if not fits:
        return None
    return min(fits, key=lambda d: (bool(d["compute_processes"]),
                                    -per_node.get(str(d["numa_node"]), 0), d["index"]))  # fmt: skip


def requirements(report: dict[str, Any], p: dict[str, Any]) -> list[dict[str, Any]]:  # noqa: PLR0915
    """One row per requirement: what the profile (scope `profile`) or FlashProve (scope
    `flashprove`) needs, what was found, and the verdict."""
    rows: list[dict[str, Any]] = []
    hosted = p["hosted"]

    def row(rid: str, need: object, found: object, ok: bool | None, status: str = "",
            scope: str = "profile") -> None:  # fmt: skip
        rows.append({"id": rid, "scope": scope, "need": need, "found": found,
                     "status": status or _verdict(ok)})  # fmt: skip

    def not_applicable(rid: str, why: str) -> None:
        row(rid, why, None, None, "n/a")

    g = _section(report, "gpus")
    bound = _gpu(report, p)
    names = sorted({d["name"] for d in g.get("devices", [])})
    row("gpu_model", p["gpu_model"], names, bound is not None)
    row(
        "gpu_count", f">= {p['gpu_count']}", g.get("count"), (g.get("count") or 0) >= p["gpu_count"]
    )
    row("gpu_memory_mib", f">= {p['gpu_memory_mib_min']}", bound and bound["memory_total_mib"],
        bound and bound["memory_total_mib"] >= p["gpu_memory_mib_min"])  # fmt: skip
    busy = None if not bound else bound["compute_processes"]
    row("gpu_idle", "no compute process on the bound GPU", busy,
        None if busy is None else not busy)  # fmt: skip
    row("suggested_gpu_index", "an idle H200 with the most usable CPUs on its NUMA node",
        bound and bound["index"], None, "info")  # fmt: skip
    driver = bound and bound["driver_version"]
    if p["driver"] == "unpinned":  # RFC-0006 Q3, Q5: record this value for the pin
        row("driver", "pinned from a host of this profile (RFC-0006 Q3, Q5)", driver, None,
            "record")  # fmt: skip
    else:
        row("driver", p["driver"], driver, None if driver is None else driver == p["driver"])
    cuda = g.get("cuda_driver_api")
    row("cuda_driver_api", f">= {CUDA_DRIVER_MIN}", cuda, _at_least(cuda, CUDA_DRIVER_MIN))
    row("cuda_driver_api_flashprove", f">= {CUDA_DRIVER_MIN_FLASHPROVE}", cuda,
        _at_least(cuda, CUDA_DRIVER_MIN_FLASHPROVE), scope="flashprove")  # fmt: skip
    cc = _section(report, "confidential_computing")
    row("cc_mode_off", "off", cc.get("status"),
        None if not cc.get("status") else cc["status"] == "off")  # fmt: skip

    c, box, n = _section(report, "cpu"), _section(report, "cgroup"), _section(report, "numa")
    n_prover = p["logical_cpus_on_gpu_numa_node"]
    node = None if not bound or bound["numa_node"] is None else str(bound["numa_node"])
    on_node = n.get("allowed_cpus_per_node", {}).get(node) if node is not None else None
    if bound and bound["numa_node"] is None:  # iproofs run refuses it before any step
        row("cpus_on_gpu_numa_node", f">= {n_prover} usable; iproofs run refuses a GPU with no "
            "NUMA node (RFC-0006 §CPU and memory selection)", "no NUMA node", False)  # fmt: skip
    else:
        row("cpus_on_gpu_numa_node", f">= {n_prover} usable", on_node,
            None if on_node is None else on_node >= n_prover)  # fmt: skip
    total = c.get("logical_cpus")
    row("cpus_total", f">= {p['logical_cpus_total_min']}", total,
        None if not total else total >= p["logical_cpus_total_min"])  # fmt: skip
    usable = c.get("allowed_cpus")
    row("cpus_usable", f">= {n_prover} prover + {VERIFIER_CPUS} verifier", usable,
        None if not usable else usable >= n_prover + VERIFIER_CPUS)  # fmt: skip
    quota = box.get("cpu_quota_cpus")
    row("cpu_quota", f"none, or >= {n_prover}", quota, quota is None or quota >= n_prover)
    row("x86_64", "x86_64", c.get("arch"), None if not c.get("arch") else c["arch"] == "x86_64")
    row("sha_ni", True, c.get("sha_ni"), c.get("sha_ni"), scope="flashprove")

    avail = _section(report, "memory").get("available_bytes")
    limit = box.get("memory_limit_bytes")
    usable_b = min(b for b in (avail, limit) if b is not None) if avail or limit else None
    row("host_memory_gib", f">= {p['host_memory_gib_min']} available and allowed",
        None if usable_b is None else round(usable_b / GIB, 1),
        None if usable_b is None else usable_b >= p["host_memory_gib_min"] * GIB)  # fmt: skip
    floor_ok = None if usable_b is None else usable_b >= FLASHPROVE_COMMIT_B
    row("flashprove_commit_floor_gb", ">= 330 available (run.sh)",
        None if usable_b is None else round(usable_b / 1e9, 1), floor_ok,
        scope="flashprove")  # fmt: skip

    work = _section(report, "disks").get("work", {})
    free = work.get("free_bytes")
    row("work_disk_free_gib", f">= {p['disk_free_gib_min']}",
        None if free is None else round(free / GIB, 1),
        None if free is None else free >= p["disk_free_gib_min"] * GIB)  # fmt: skip
    row("work_disk_writable", True, work.get("writable"), work.get("writable"))
    s, k = _section(report, "system"), _section(report, "containers")
    row("kernel", f">= {p['kernel_min']}", s.get("kernel_release"),
        _at_least(s.get("kernel_release"), p["kernel_min"]))  # fmt: skip
    row("cgroup_v2", "2", box.get("version"), box.get("version") == "2")
    bare_metal_rows = ("work_disk_nvme", "os", "systemd", "docker_engine",
                       "docker_cgroup_driver", "nvidia_container_toolkit")  # fmt: skip
    no_engine = k.get("docker_engine") is None and bool(s.get("container"))
    if hosted:
        why = "hosted: the provider started the container (RFC-0006 §Hosted execution)"
        for rid in bare_metal_rows:
            not_applicable(rid, why)
        row("runs_as_root", "root, so the adapter runs as its own uid (RFC-0006 Q6)",
            s.get("root"), None, "info")  # fmt: skip
        row("proc1_environ", "readable (the image's environment)",
            s.get("proc1_environ_readable"), s.get("proc1_environ_readable"))  # fmt: skip
    elif no_engine:
        hint = "a host that runs docker; in a container with no engine, use the hosted profile"
        row("bare_metal", hint + " (--profile prover-h200-hosted)", "a container, no docker", False)
        for rid in bare_metal_rows:
            not_applicable(rid, "no docker engine in this container")
    else:
        kind = work.get("device_kind")
        row("work_disk_nvme", "nvme", kind, None if kind is None else kind == "nvme")
        found_os = (s.get("os_id"), s.get("os_version_id"))
        row("os", "/".join(p["os"]), "/".join(map(str, found_os)), found_os == p["os"])
        tools = s.get("tools") or {}
        row("systemd", "running, with systemd-run", s.get("systemd_running"),
            bool(s.get("systemd_running") and tools.get("systemd-run")))  # fmt: skip
        engine = k.get("docker_engine")
        row("docker_engine", f">= {p['docker_engine_min']}", engine,
            False if engine is None and not tools.get("docker", True) else
            _at_least(engine, p["docker_engine_min"]))  # fmt: skip
        driver_cg = k.get("cgroup_driver")
        row("docker_cgroup_driver", p["cgroup_driver"], driver_cg,
            None if driver_cg is None else driver_cg == p["cgroup_driver"])  # fmt: skip
        ctk, need_ctk = k.get("nvidia_container_toolkit"), p["nvidia_container_toolkit_min"]
        row("nvidia_container_toolkit", f">= {need_ctk}", ctk, _at_least(ctk, need_ctk))
    m = _section(report, "madvise_wipeonfork")
    row("madvise_wipeonfork", True, m.get("errno") or m.get("ok"), m.get("ok"),
        scope="flashprove")  # fmt: skip
    net = _section(report, "network")
    for name in URLS:
        row(f"reach_{name}", "answers", net.get(name),
            None if name not in net else isinstance(net[name], int))  # fmt: skip
    for image, public in sorted((net.get("anonymous_pull") or {}).items()):
        row(f"pull_{image}", "anonymous pull, or a registry login", public, None,
            "pass" if public else "login")  # fmt: skip
    return rows


# ---------------------------------------------------------------- output

IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
IPV6 = re.compile(
    r"\b(?:[0-9A-Fa-f]{1,4}:){4,7}[0-9A-Fa-f]{1,4}\b|\b[0-9A-Fa-f]{1,4}::[0-9A-Fa-f:]*"
)
MAC = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")


def scrub(text: str, hostname: str) -> str:
    """Drop the hostname, IP and MAC addresses from the output (AGENTS.md rule 7)."""
    if len(hostname) >= 3:
        text = text.replace(hostname, "<redacted>")
    for pattern in (MAC, IPV6, IPV4):
        text = pattern.sub("<redacted>", text)
    return text


def probe(root: Path = Path("/"), runner: Runner = run, opener: Opener | None = None,
          work: Path | None = None, repo: Path = REPO, profile: str = "prover-h200",
          allowed: list[int] | None = None) -> dict[str, Any]:  # fmt: skip
    p = PROFILES[profile]
    allowed = allowed if allowed is not None else affinity(root)
    docker_root = (runner(["docker", "info", "--format", "{{.DockerRootDir}}"]) or "").strip()
    paths = {"work": work or Path.cwd(), "/": root, "/tmp": root / "tmp"}
    if docker_root:
        paths["docker_root"] = root / docker_root.lstrip("/")
    report: dict[str, Any] = {
        "probe_version": PROBE_VERSION,
        "date_utc": time.strftime("%Y-%m-%d", time.gmtime()),
        "profile": p["id"],
        "gpus": guarded(lambda: gpus(root, runner)),
        "confidential_computing": guarded(lambda: confidential_computing(runner)),
        "cpu": guarded(lambda: cpu(root, allowed)),
        "numa": guarded(lambda: numa(root, allowed)),
        "cgroup": guarded(lambda: cgroup(root)),
        "memory": guarded(lambda: memory(root)),
        "disks": guarded(lambda: disks(root, paths)),
        "system": guarded(lambda: system(root)),
        "containers": guarded(lambda: containers(runner)),
        "madvise_wipeonfork": guarded(madvise_wipeonfork),
        "network": guarded(lambda: network(opener, images(repo))) if opener else None,
    }
    report["requirements"] = guarded(lambda: requirements(report, p))
    rows = report["requirements"] if isinstance(report["requirements"], list) else []
    report["failed"] = [r["id"] for r in rows if r["status"] == "fail" and r["scope"] == "profile"]
    report["failed_flashprove"] = [
        r["id"] for r in rows if r["status"] == "fail" and r["scope"] == "flashprove"
    ]
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=Path, help="the directory for results, caches and models")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="prover-h200",
                        help="the profile to check against (default prover-h200)")  # fmt: skip
    parser.add_argument("--offline", action="store_true", help="skip the network checks")
    args = parser.parse_args(argv)
    hostname = ""
    with contextlib.suppress(OSError):
        hostname = socket.gethostname()
    report = probe(opener=None if args.offline else urllib.request.urlopen, work=args.work,
                   profile=args.profile)  # fmt: skip
    for r in report["requirements"] if isinstance(report["requirements"], list) else []:
        scope = "" if r["scope"] == "profile" else f" [{r['scope']}]"
        line = f"{r['status'].upper():8} {r['id']:30} need {r['need']}; found {r['found']}{scope}"
        print(scrub(line, hostname), file=sys.stderr)
    sys.stdout.write(scrub(json.dumps(report, indent=2, sort_keys=True), hostname) + "\n")
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
