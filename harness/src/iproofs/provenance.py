"""Digests, pin checks and the machine record (RFC-0014, RFC-0006).

Digest byte definitions are normative in RFC-0012 §Digests.
"""

import hashlib
import os
import re
import shutil
import subprocess
import tarfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import HostedRuntime, ProverProfile

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_CHUNK = 1 << 20


def check_digest(value: str) -> str:
    """Return `value` if it is a well-formed digest string, else raise ErrorKind.integrity."""
    if not DIGEST_RE.fullmatch(value):
        raise IProofsError(ErrorKind.INTEGRITY, f"malformed digest {value!r}, want sha256:<64 hex>")
    return value


def _hex(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def file_digest(path: Path) -> str:
    """Digest of the file's bytes as stored, streamed."""
    return "sha256:" + _hex(path)


def _listing_digest(entries: Mapping[str, Path]) -> str:
    """sha256 over `<name>\\t<hex>\\n` lines sorted by the UTF-8 bytes of the name."""
    h = hashlib.sha256()
    for name in sorted(entries, key=lambda n: n.encode("utf-8")):
        h.update(f"{name}\t{_hex(entries[name])}\n".encode())
    return "sha256:" + h.hexdigest()


def _files(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for p in root.rglob("*"):
        if p.is_symlink():
            raise IProofsError(
                ErrorKind.INTEGRITY, f"{p}: symlinks are not allowed in a hashed tree"
            )
        if p.is_file():
            files[p.relative_to(root).as_posix()] = p
        elif not p.is_dir():
            raise IProofsError(ErrorKind.INTEGRITY, f"{p}: not a regular file")
    return files


def tree_digest(root: Path) -> str:
    """Digest of every file under `root`; empty subdirectories do not count."""
    return _listing_digest(_files(root))


def model_digest(model_root: Path) -> str:
    return tree_digest(model_root)


def proof_digest(proof_dir: Path) -> str:
    """Digest over the part files of one proof directory, named by file name."""
    files = _files(proof_dir)
    nested = [name for name in files if "/" in name]
    if nested:
        raise IProofsError(ErrorKind.INTEGRITY, f"{proof_dir}: nested part files {nested}")
    return _listing_digest(files)


def archive_proof(proof_dir: Path, out: Path) -> tuple[str, int]:
    """RFC-0014 §Proof digests and archive: the proof directory as a POSIX ustar tar, entries
    sorted by name, mtime 0, uid and gid 0, mode 0644, no compression, so the same parts give
    the same bytes. Returns (sha256 digest, bytes) of the archive."""
    files = _files(proof_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out, "w", format=tarfile.USTAR_FORMAT) as tar:
        for name in sorted(files, key=lambda n: n.encode("utf-8")):
            info = tarfile.TarInfo(name)
            info.size, info.mtime, info.mode = files[name].stat().st_size, 0, 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            with files[name].open("rb") as f:
                tar.addfile(info, f)
    return file_digest(out), out.stat().st_size


def corpus_digest(entries: Mapping[str, Path]) -> str:
    """Digest over the corpus files, each named by its corpus entry `id`."""
    return _listing_digest(entries)


def prompt_set_digest(prompts_jsonl: Path) -> str:
    return file_digest(prompts_jsonl)


# ---------------------------------------------------------------- git state (RFC-0014)


def git_state(root: Path, paths: Sequence[str] = ()) -> tuple[str, bool]:
    """(HEAD commit, dirty) of the checkout; `paths` limits the dirty check."""
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--", *paths],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        raise IProofsError(ErrorKind.ENVIRONMENT, f"{root} is not a git checkout") from e
    return head, bool(status.strip())


def file_records(paths: Sequence[Path]) -> list[dict[str, object]]:
    """`{name, digest, bytes}` per file, as manifest.json lists commitment and proof files."""
    return [{"name": p.name, "digest": file_digest(p), "bytes": p.stat().st_size} for p in paths]


# ---------------------------------------------------------------- machine record (RFC-0006)


class Host:
    """The allowlisted probes of RFC-0006 §Machine record, and nothing else: `/proc`, `/sys`,
    `/etc/os-release`, `uname -r`, `docker version`, `docker info`, `nvidia-ctk --version`
    and NVML. `root` is `/` on a host and a fixture tree in tests; `run` and `nvml` are
    replaced in tests. A probe that fails leaves its field out (CPU-only hosts, macOS)."""

    def __init__(
        self,
        root: Path = Path("/"),
        run: Callable[[list[str]], str | None] | None = None,
        nvml: Callable[[int], dict[str, object] | None] | None = None,
        dev_of: Callable[[Path], tuple[int, int]] | None = None,
        *,
        hosted: bool = False,
    ) -> None:
        self.root = root
        self.run = run or _run
        self.nvml = nvml or _nvml
        self.dev_of = dev_of or _dev_of
        self.hosted = hosted  # RFC-0006 §Hosted execution: the harness runs in the adapter image

    def read(self, rel: str) -> str | None:
        try:
            return (self.root / rel).read_text().strip()
        except OSError:
            return None

    def cpu(self) -> dict[str, object]:
        out: dict[str, object] = {}
        info = self.read("proc/cpuinfo") or ""
        if m := re.search(r"^model name\s*:\s*(.+)$", info, re.M):
            out["model"] = m.group(1).strip()
        cpus = self.root / "sys/devices/system/cpu"
        topo = sorted(cpus.glob("cpu[0-9]*/topology")) if cpus.is_dir() else []
        if topo:
            packages = [(p / "physical_package_id").read_text().strip() for p in topo]
            cores = {
                (pkg, (p / "core_id").read_text().strip())
                for pkg, p in zip(packages, topo, strict=True)
            }
            out |= {
                "sockets": len(set(packages)),
                "physical_cores": len(cores),
                "logical_cpus": len(topo),
            }
        if (smt := self.read("sys/devices/system/cpu/smt/active")) is not None:
            out["smt_active"] = smt == "1"
        quota, _, period = (self.read("sys/fs/cgroup/cpu.max") or "max").partition(" ")
        if quota != "max" and period:  # a CPU time quota on this cgroup, in CPUs
            out["cgroup_quota_cpus"] = round(int(quota) / int(period), 2)
        return out

    def memory(self) -> dict[str, object]:
        info = self.read("proc/meminfo") or ""
        out: dict[str, object] = {}
        for key, field_name in (
            ("MemTotal", "total_bytes"),
            ("MemAvailable", "available_bytes_at_start"),
        ):
            if m := re.search(rf"^{key}:\s*(\d+) kB$", info, re.M):
                out[field_name] = int(m.group(1)) * 1024
        if (limit := self.read("sys/fs/cgroup/memory.max")) not in (None, "max"):
            out["cgroup_limit_bytes"] = int(limit)
        return out

    def disk(self, path: Path) -> dict[str, object]:
        out: dict[str, object] = {}
        path = next((p for p in [path, *path.absolute().parents] if p.exists()), path)
        try:  # the results directory may not exist yet: its nearest existing parent
            out["free_bytes_at_start"] = shutil.disk_usage(path).free
            major, minor = self.dev_of(path)
        except OSError:
            return out
        device = (self.root / f"sys/dev/block/{major}:{minor}").resolve()
        if (device / "partition").exists():
            device = device.parent
        rotational = self.read(str((device / "queue/rotational").relative_to(self.root.resolve())))
        if device.name.startswith("nvme"):
            out["type"] = "nvme"
        elif rotational is not None:
            out["type"] = "hdd" if rotational == "1" else "ssd"
        return out

    def os_release(self) -> dict[str, object]:
        if self.hosted:  # /etc/os-release is the image's; the host's is not visible
            return {}
        text = self.read("etc/os-release") or ""
        fields = dict(re.findall(r'^(ID|VERSION_ID)="?([^"\n]*)"?$', text, re.M))
        return {k.lower(): v for k, v in fields.items()}

    def container(self) -> dict[str, object]:
        if self.hosted:  # no engine to ask: the provider started this container
            mounts = self.read("proc/self/mounts") or ""
            v2 = re.search(r"^\S+ /sys/fs/cgroup cgroup2 ", mounts, re.M) is not None
            return {"execution": "hosted", "cgroup_version": "2" if v2 else "1"}
        out: dict[str, object] = {}
        if engine := self.run(["docker", "version", "--format", "{{.Server.Version}}"]):
            out["docker_engine"] = engine
        if info := self.run(["docker", "info", "--format", "{{.CgroupDriver}} {{.CgroupVersion}}"]):
            driver, _, version = info.partition(" ")
            out |= {"cgroup_driver": driver, "cgroup_version": version}
        ctk = self.run(["nvidia-ctk", "--version"]) or ""
        if m := re.search(r"version\s+(\d+(?:\.\d+)+)", ctk):
            out["nvidia_container_toolkit"] = m.group(1)
        return out

    def gpu(self, index: int) -> dict[str, object]:
        """NVML fields of the bound GPU (and the visible count); never its UUID or serial."""
        found = self.nvml(index)
        if not found:
            return {}
        out = {k: found[k] for k in GPU_FIELDS if k in found and k != "numa_node"}
        bus = found.get("pci_bus_id")
        if isinstance(bus, str) and (
            node := self.read(f"sys/bus/pci/devices/{sysfs_bus_id(bus)}/numa_node")
        ):
            out["numa_node"] = int(node)
        out["bound_index"] = index
        return out


def sysfs_bus_id(bus: str) -> str:
    """NVML's `busId` has an 8-digit PCI domain (NVML_DEVICE_PCI_BUS_ID_FMT, `%08X:%02X:%02X.0`);
    sysfs names the device with a 4-digit domain, in lower case."""
    domain, sep, rest = bus.strip().partition(":")
    try:
        return f"{int(domain, 16):04x}{sep}{rest}".lower()
    except ValueError:
        return bus.strip().lower()


GPU_FIELDS = (
    "model",
    "count_visible",
    "memory_total_mib",
    "numa_node",
    "driver_version",
    "cuda_driver_api",
)


def machine_record(
    host: Host,
    *,
    results: Path,
    gpu_index: int | None,
    cpus: Mapping[str, Sequence[int]],
    mems: Sequence[int],
    provider: str,
    verifier_host: str = "same_as_prover",
    redact: Callable[[str], str] = lambda s: s,
) -> dict[str, object]:
    """RFC-0006 §Machine record: exactly the listed fields, every string redacted."""
    cpu = host.cpu() | {
        "bound_prover": list(cpus.get("prover", ())),
        "bound_verifier": list(cpus.get("verifier", ())),
        "bound_verifier_single": list(cpus.get("verifier_1", ())),
    }
    nodes = host.root / "sys/devices/system/node"
    numa: dict[str, object] = {"bound_mems": list(mems)}
    if nodes.is_dir():
        numa["nodes"] = len(list(nodes.glob("node[0-9]*")))
    record: dict[str, object] = {
        "cpu": cpu,
        "numa": numa,
        "memory": host.memory(),
        "disk": host.disk(results),
        "os": host.os_release(),
        "container": host.container(),
        "provider": provider,
        "verifier_host": verifier_host,
    }
    if (release := host.run(["uname", "-r"])) is not None:
        record["kernel"] = {"release": release}
    if gpu_index is not None and (gpu := host.gpu(gpu_index)):
        record["gpu"] = gpu
    clean: dict[str, object] = _redacted(record, redact)
    return clean


def _redacted(value: object, redact: Callable[[str], str]) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: _redacted(v, redact) for k, v in value.items()}
    if isinstance(value, list):
        return [_redacted(v, redact) for v in value]
    return value


MACHINE_DRIFT = (("gpu", "driver_version"), ("kernel", "release"), ("cpu", "bound_prover"))


def machine_drift(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    """INV-MR-2: the fields that may not change between the two collections."""
    return [
        f"{a}.{b}: {before.get(a, {}).get(b)!r} -> {after.get(a, {}).get(b)!r}"
        for a, b in MACHINE_DRIFT
        if before.get(a, {}).get(b) != after.get(a, {}).get(b)
    ]


def _run(argv: list[str]) -> str | None:
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.strip() or None if done.returncode == 0 else None


def _dev_of(path: Path) -> tuple[int, int]:
    dev = os.stat(path).st_dev
    return os.major(dev), os.minor(dev)


def _nvml(index: int) -> dict[str, object] | None:
    try:
        import pynvml  # noqa: PLC0415 (optional extra, INV-ARCH-6)

        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(index)
        cuda = pynvml.nvmlSystemGetCudaDriverVersion_v2()
        return {
            "model": str(pynvml.nvmlDeviceGetName(handle)),
            "count_visible": int(pynvml.nvmlDeviceGetCount()),
            "memory_total_mib": int(pynvml.nvmlDeviceGetMemoryInfo(handle).total) // (1024 * 1024),
            "driver_version": str(pynvml.nvmlSystemGetDriverVersion()),
            "cuda_driver_api": f"{cuda // 1000}.{cuda % 1000 // 10}",
            "pci_bus_id": str(pynvml.nvmlDeviceGetPciInfo(handle).busId),
        }
    except Exception:
        return None


# ---------------------------------------------------------------- CPU selection (RFC-0006)


@dataclass(frozen=True, slots=True)
class Cpu:
    id: int
    package: int
    core: int
    node: int


@dataclass(frozen=True, slots=True)
class Topology:
    cpus: tuple[Cpu, ...]


@dataclass(frozen=True, slots=True)
class CpuBinding:
    prover: tuple[int, ...]
    verifier: tuple[int, ...]
    verifier_1: tuple[int, ...]
    mems: tuple[int, ...]

    def roles(self) -> dict[str, list[int]]:
        """The machine record's `cpu.bound_*` lists, keyed by role."""
        return {
            "prover": list(self.prover),
            "verifier": list(self.verifier),
            "verifier_1": list(self.verifier_1),
        }


def _ranges(text: str) -> list[int]:
    out: list[int] = []
    for part in filter(None, text.strip().split(",")):
        low, _, high = part.partition("-")
        out += range(int(low), int(high or low) + 1)
    return out


def read_topology(root: Path = Path("/")) -> Topology:
    """`/sys/devices/system/cpu/cpuN/topology` and `/sys/devices/system/node/nodeK/cpulist`."""
    node_of: dict[int, int] = {}
    for cpulist in (root / "sys/devices/system/node").glob("node[0-9]*/cpulist"):
        node = int(cpulist.parent.name.removeprefix("node"))
        node_of |= dict.fromkeys(_ranges(cpulist.read_text()), node)
    cpus = []
    for topo in (root / "sys/devices/system/cpu").glob("cpu[0-9]*/topology"):
        cpu_id = int(topo.parent.name.removeprefix("cpu"))
        package = int((topo / "physical_package_id").read_text())
        core = int((topo / "core_id").read_text())
        cpus.append(Cpu(cpu_id, package, core, node_of.get(cpu_id, 0)))
    return Topology(tuple(sorted(cpus, key=lambda c: c.id)))


def usable_topology(host: Host, allowed: Iterable[int] | None = None) -> Topology:
    """RFC-0006 §CPU and memory selection: the host's topology, reduced to the CPUs `allowed`.
    Without `allowed`, a hosted container on the real root keeps the CPUs of this process's
    scheduler affinity (a provider's cpuset), so no CPU outside the container's set is bound; a
    docker host, or a fixture tree, keeps every CPU."""
    topology = read_topology(host.root)
    if allowed is None and host.hosted and host.root == Path("/"):
        allowed = os.sched_getaffinity(0) if hasattr(os, "sched_getaffinity") else None
    if allowed is None:
        return topology
    keep = set(allowed)
    return Topology(tuple(c for c in topology.cpus if c.id in keep))


def _ordered(cpus: Iterable[Cpu]) -> list[int]:
    """One logical CPU per physical core first (lowest id of each core), then SMT siblings."""
    groups: dict[tuple[int, int], list[int]] = {}
    for c in sorted(cpus, key=lambda c: c.id):
        groups.setdefault((c.package, c.core), []).append(c.id)
    cores = sorted(groups.values(), key=min)
    return [g[0] for g in cores] + [cpu for g in cores for cpu in g[1:]]


def select_cpus(
    topology: Topology, gpu_numa_node: int, n_prover: int, n_verifier: int = 8
) -> CpuBinding:
    """RFC-0006 §CPU and memory selection, a pure function of the topology. `n_prover` is the
    profile's `cpu.logical_cpus_on_gpu_numa_node` and has no default, so no caller binds 24 on a
    profile that asks for fewer."""
    on_node = [c for c in topology.cpus if c.node == gpu_numa_node]
    ordered = _ordered(on_node)
    if len(ordered) < n_prover:
        raise IProofsError(
            ErrorKind.ENVIRONMENT,
            f"not enough CPUs on GPU NUMA node {gpu_numa_node}: {len(ordered)} < {n_prover}"
            " (PC-CPU-NUMA)",
        )
    prover = ordered[:n_prover]
    taken = set(prover)
    rest = [c for c in topology.cpus if c.id not in taken]
    nodes = sorted({c.node for c in rest}, key=lambda n: (n != gpu_numa_node, n))
    others = [cpu for n in nodes for cpu in _ordered(c for c in rest if c.node == n)]
    if len(others) < n_verifier:
        raise IProofsError(
            ErrorKind.ENVIRONMENT,
            f"not enough CPUs for verifier emulation: {len(others)} < {n_verifier}",
        )
    verifier = others[:n_verifier]
    return CpuBinding(tuple(prover), tuple(verifier), tuple(verifier[:1]), (gpu_numa_node,))


def select_verifier_cpus(topology: Topology, n_verifier: int) -> tuple[int, ...]:
    """A host that only verifies, with no GPU and no prover (RFC-0008 §Split suites):
    `n_verifier` CPUs taken as `select_cpus` takes the verifier's, NUMA nodes in order and one
    logical CPU per physical core before SMT siblings."""
    nodes = sorted({c.node for c in topology.cpus})
    ordered = [cpu for n in nodes for cpu in _ordered(c for c in topology.cpus if c.node == n)]
    if len(ordered) < n_verifier:
        raise IProofsError(
            ErrorKind.ENVIRONMENT,
            f"not enough CPUs for the verifier profile: {len(ordered)} < {n_verifier}",
        )
    return tuple(ordered[:n_verifier])


# ---------------------------------------------------------------- profile conformance (RFC-0006)


@dataclass(frozen=True, slots=True)
class ConformanceFailure:
    check: str  # RFC-0006 check id, PC-*
    message: str

    def line(self) -> str:
        return f"{self.check}: {self.message}"


def _version(text: object) -> tuple[int, ...]:
    """Leading dotted numbers: "6.8.0-45-generic" -> (6, 8, 0); "" -> ()."""
    m = re.match(r"\d+(?:\.\d+)*", str(text or ""))
    return tuple(int(p) for p in m.group(0).split(".")) if m else ()


def check_profile(  # noqa: PLR0912, PLR0915 (one branch per RFC-0006 check)
    record: Mapping[str, Any],
    profile: ProverProfile,
    *,
    numa_node_cpus: int | None = None,
    gpu_processes: int | None = None,
) -> list[ConformanceFailure]:
    """RFC-0006 §Profile conformance check. `numa_node_cpus` (logical CPUs on the GPU's NUMA
    node, from the topology) and `gpu_processes` (NVML) are probes the record does not hold."""
    found: list[ConformanceFailure] = []

    def fail(check: str, message: str) -> None:
        found.append(ConformanceFailure(check, message))

    gpu, cpu, mem = record.get("gpu", {}), record.get("cpu", {}), record.get("memory", {})
    disk, osr, box = record.get("disk", {}), record.get("os", {}), record.get("container", {})
    if profile.gpu is not None:
        spec = profile.gpu
        if gpu.get("model") != spec.model:
            fail(
                "PC-GPU-MODEL",
                f"bound GPU is {gpu.get('model')!r}, the profile needs {spec.model!r}",
            )
        if gpu.get("memory_total_mib", 0) < spec.memory_mib_min:
            fail("PC-GPU-MEM", f"{gpu.get('memory_total_mib')} MiB < {spec.memory_mib_min} MiB")
        if gpu.get("count_visible", 0) < spec.count:
            fail("PC-GPU-COUNT", f"{gpu.get('count_visible')} visible GPUs < {spec.count}")
        if gpu_processes:
            fail("PC-GPU-BUSY", f"{gpu_processes} compute process(es) hold the bound GPU")
        if gpu.get("driver_version") != profile.driver:
            fail(
                "PC-DRIVER",
                f"driver {gpu.get('driver_version')!r}, the profile pins {profile.driver!r}",
            )
        need = profile.cpu.logical_cpus_on_gpu_numa_node
        if numa_node_cpus is None or numa_node_cpus < need:
            fail("PC-CPU-NUMA", f"{numa_node_cpus} logical CPUs on the GPU's NUMA node < {need}")
    if cpu.get("logical_cpus", 0) < profile.cpu.logical_cpus_total_min:
        fail(
            "PC-CPU-TOTAL",
            f"{cpu.get('logical_cpus')} logical CPUs < {profile.cpu.logical_cpus_total_min}",
        )
    quota = cpu.get("cgroup_quota_cpus")
    if quota is not None and quota < profile.cpu.logical_cpus_on_gpu_numa_node:
        fail("PC-CPU-QUOTA", f"a CPU quota of {quota} CPUs < the prover's"
             f" {profile.cpu.logical_cpus_on_gpu_numa_node}")  # fmt: skip
    usable = min(mem.get("available_bytes_at_start", 0), mem.get("cgroup_limit_bytes", 2**63))
    if usable < profile.host_memory_gib_min * 1024**3:
        fail("PC-MEM", f"{usable} B available or allowed < {profile.host_memory_gib_min} GiB")
    free_gib = disk.get("free_bytes_at_start", 0) / 1024**3
    if free_gib < profile.disk.free_gib_min or (
        "nvme" in profile.disk.type.lower() and disk.get("type") != "nvme"
    ):
        fail(
            "PC-DISK",
            f"{free_gib:.1f} GiB free on a {disk.get('type')!r} disk; the profile needs"
            f" {profile.disk.free_gib_min} GiB on {profile.disk.type}",
        )
    hosted = isinstance(profile.container_runtime, HostedRuntime)
    if not hosted and (osr.get("id"), osr.get("version_id")) != (
        profile.os.id,
        profile.os.version_id,
    ):
        fail(
            "PC-OS",
            f"{osr.get('id')} {osr.get('version_id')}, the profile needs"
            f" {profile.os.id} {profile.os.version_id}",
        )
    kernel = _version(record.get("kernel", {}).get("release"))
    if not kernel or kernel < _version(profile.kernel_min):
        fail(
            "PC-KERNEL",
            f"kernel {record.get('kernel', {}).get('release')!r} older than {profile.kernel_min}",
        )
    runtime = profile.container_runtime
    if isinstance(runtime, HostedRuntime):
        if box.get("execution") != "hosted":
            fail("PC-RUNTIME", "the profile needs hosted execution (--hosted)")
        if box.get("cgroup_version") != runtime.cgroup_version:
            fail("PC-CGROUP", f"cgroup v{box.get('cgroup_version')}; the profile needs v2")
        return found
    if box.get("execution") == "hosted":
        fail("PC-RUNTIME", "the profile needs docker on the host, not hosted execution")
    if box.get("cgroup_version") != "2" or box.get("cgroup_driver") != runtime.cgroup_driver:
        fail(
            "PC-CGROUP",
            f"cgroup v{box.get('cgroup_version')} with {box.get('cgroup_driver')!r};"
            f" the profile needs v2 with {runtime.cgroup_driver!r}",
        )
    if _version(box.get("docker_engine")) < _version(runtime.docker_engine_min) or not box.get(
        "docker_engine"
    ):
        fail(
            "PC-RUNTIME",
            f"Docker Engine {box.get('docker_engine')!r} below {runtime.docker_engine_min}",
        )
    toolkit_min = _version(runtime.nvidia_container_toolkit_min)
    if any(toolkit_min) and _version(box.get("nvidia_container_toolkit")) < toolkit_min:
        fail(
            "PC-RUNTIME",
            f"NVIDIA Container Toolkit {box.get('nvidia_container_toolkit')!r}"
            f" below {runtime.nvidia_container_toolkit_min}",
        )
    return found


# ---------------------------------------------------------------- Dockerfile rules (RFC-0014)


def _instructions(text: str) -> list[tuple[int, str, str]]:
    """(first line number, instruction, arguments), with continuation lines joined."""
    out, buf, start = [], "", 0
    for n, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not buf and (not line or line.startswith("#")):
            continue
        start = start or n
        if line.endswith("\\"):
            buf += line[:-1] + " "
            continue
        word, _, rest = (buf + line).partition(" ")
        out.append((start, word.upper(), rest.strip()))
        buf, start = "", 0
    return out


def dockerfile_problems(dockerfile: str, inputs_lock: str = "") -> list[str]:
    """RFC-0014 B1 to B3 for an adapter Dockerfile, each problem as `<line>: B<n> <what>`.

    B1 every FROM names a digest (or an earlier stage); B2 a downloaded input (`ADD` of a URL)
    sits in the stage named `fetch`, carries `--checksum`, and is listed in inputs.lock with
    that digest; B3 every RUN outside `fetch` uses `--network=none`."""
    locked = {
        parts[1]: parts[2]
        for line in inputs_lock.splitlines()
        if line.strip() and not line.startswith("#") and len(parts := line.split("\t")) == 3
    }
    problems, stages, stage = [], set(), ""
    for n, word, args in _instructions(dockerfile):
        tokens = args.split()
        if word == "FROM":
            image = next(t for t in tokens if not t.startswith("--"))
            if "@sha256:" not in image and image not in stages:
                problems.append(f"{n}: B1 FROM {image} has no digest")
            stage = tokens[-1] if len(tokens) >= 3 and tokens[-2].upper() == "AS" else ""
            stages.add(stage)
        elif word == "RUN" and stage != "fetch" and "--network=none" not in tokens:
            problems.append(f"{n}: B3 RUN outside the fetch stage without --network=none")
        elif word == "ADD":
            sources = [t for t in tokens if not t.startswith("--")][:-1]
            checksum = next(
                (t.split("=", 1)[1] for t in tokens if t.startswith("--checksum=")), None
            )
            for src in sources:
                if not src.startswith(("http://", "https://", "git@")):
                    continue
                if stage != "fetch":
                    problems.append(f"{n}: B2 {src} downloaded outside the fetch stage")
                elif locked.get(src) is None:
                    problems.append(f"{n}: B2 {src} is not in inputs.lock")
                elif checksum != locked[src] and "#" not in src:
                    problems.append(f"{n}: B2 {src} checksum differs from inputs.lock")
    return problems
