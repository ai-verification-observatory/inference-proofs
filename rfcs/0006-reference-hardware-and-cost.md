# RFC-0006: Reference hardware and cost basis

- Status: Draft
- Authors: AbdelStark
- Created: 2026-11-03
- Target milestone: v0.1-alpha (reference file schema), v0.1-beta (machine record and conformance check)
- Requires: RFC-0004, RFC-0012
- Supersedes: none
- Discussion: pull request that introduces it

## Summary

This RFC fixes, per benchmark release, the machine profiles on which rows are measured, the machine record every run stores, the rule for binding a job to CPUs and memory, the conformance check a host must pass before a job starts, and the price used to turn GPU seconds into money. It also bounds what a machine record may contain: enough to reproduce a run, nothing that identifies a host or an account.

## Motivation

A proving rate means little without the machine. Both v0.1 systems publish numbers from one NVIDIA H100 80 GB, with different host resources: FlashProve uses 24 of a host's 96 CPUs and up to about 300 GB of host memory, and its full-size route will not start committing below 330 GB available; SASH's manifest records the GPU and CUDA version (PRD §1; both external, reported, from the upstream repositories at the pins in RFC-0003). Prices differ by provider and by month. Fixing profiles and a price per release keeps rows comparable within a release (PRD G2, F5).

The v0.1 reference GPU is the NVIDIA H200 141 GB (owner decision of 2026-11-08, §H200 profiles). The H200 is a Hopper GPU, compute capability sm_90 like the H100, so the pinned adapter images run on it unchanged. The research cluster the project will use for official runs (Lucid Computing, bare metal, docker) has 5 H200 and 1 H100, and Hugging Face Jobs, used for development runs until then, rents H200 but no H100. The H100 profiles stay declared. AGENTS.md rule 7 forbids machine identifiers beyond what this RFC asks for, so the record's contents must be listed exhaustively.

## Goals

- One file per release, `reference/<release>.yaml`, valid against `schema/reference/1.schema.json`, defines every profile and the cost basis.
- Every run stores a machine record whose fields are exactly those listed here, and none of the excluded ones.
- CPU and memory binding is deterministic given the host topology, and recorded.
- A host that does not meet its profile fails before any timed step, with kind `environment`.
- Cost figures use only the release's asserted price.

## Non-Goals

- Prover profiles whose jobs use more than one GPU; GPUs other than the H100 and H200 (v0.1 systems need neither; see Open Questions). Serving profiles with more GPUs are R6's.
- Pricing CPU time, host memory, storage or network (rule C5 below).
- Measuring the host (RFC-0011 owns sampling; this RFC owns the record and the binding).
- Choosing providers for compute sponsorship (RFC-0001 governance).

## Proposed Design

### Reference file

`reference/<release>.yaml`, authored, YAML loaded per RFC-0012:

```yaml
schema: "reference/1"
release: "v0.1"
profiles:
  prover-h200:                  # the v0.1 reference (§H200 profiles); same host needs as prover-h100
    kind: prover
    gpu: {model: "NVIDIA H200", form_factor: "SXM", count: 1, memory_mib_min: 140000}
    cpu: {logical_cpus_on_gpu_numa_node: 24, logical_cpus_total_min: 32}
    host_memory_gib_min: 330
    disk: {type: "local NVMe", free_gib_min: 500}
    os: {id: "ubuntu", version_id: "24.04"}
    kernel_min: "5.19"
    driver: "<pinned NVIDIA driver version string>"
    container_runtime: {docker_engine_min: "25.0", nvidia_container_toolkit_min: "1.17", cgroup_driver: "systemd"}
    cost: "h200"                # its GPU is priced by costs.h200 (C7)
  prover-h200-hosted:           # §H200 profiles: a minimum spec for a hosted H200 container
    kind: prover
    gpu: {model: "NVIDIA H200", form_factor: "SXM", count: 1, memory_mib_min: 140000}
    cpu: {logical_cpus_on_gpu_numa_node: 15, logical_cpus_total_min: 23}
    host_memory_gib_min: 200
    disk: {type: "any", free_gib_min: 500}
    os: {id: "ubuntu", version_id: "24.04"}
    kernel_min: "5.19"
    driver: "<pinned NVIDIA driver version string>"
    container_runtime: {kind: "hosted", cgroup_version: "2"}
    cost: "h200"
  prover-h100:
    kind: prover
    gpu: {model: "NVIDIA H100 80GB HBM3", form_factor: "SXM", count: 1, memory_mib_min: 80000}
    cpu: {logical_cpus_on_gpu_numa_node: 24, logical_cpus_total_min: 32}
    host_memory_gib_min: 330
    disk: {type: "local NVMe", free_gib_min: 500}
    os: {id: "ubuntu", version_id: "24.04"}
    kernel_min: "5.19"
    driver: "<pinned NVIDIA driver version string>"
    container_runtime: {docker_engine_min: "25.0", nvidia_container_toolkit_min: "1.17", cgroup_driver: "systemd"}
  verifier-cpu:
    kind: verifier
    gpu: null
    cpu: {logical_cpus: 8}
    host_memory_gib: 32
    emulation: {allowed_on: ["prover-h200", "prover-h200-hosted", "prover-h100"]}
cost:
  price_per_gpu_hour_usd:
    value: 0.0                  # placeholder until Q1 resolves; freeze refuses a release whose value is 0 (C6)
    unit: "USD/gpu_hour"
    scope: null
    grade: "asserted"
    tier: "reported"
    source: {kind: "reference_file", ref: "reference/v0.1.yaml#/cost"}
    null_reason: null
  basis: "median on-demand list price of the named providers on the named date"
  providers: ["<provider name>", "<provider name>", "<provider name>"]
  date: "YYYY-MM-DD"
  priced: ["gpu"]
  not_priced: ["cpu", "host_memory", "disk", "network"]
costs:                          # C7: one more basis per GPU model priced apart from `cost`
  h200: {price_per_gpu_hour_usd: {...}, basis: "...", providers: [...], date: "YYYY-MM-DD", readings: [...], priced: ["gpu"], not_priced: [...]}
```

Python view (`iproofs.model`):

```python
@dataclass(frozen=True, slots=True)
class GpuSpec:
    model: str
    form_factor: str
    count: int
    memory_mib_min: int

@dataclass(frozen=True, slots=True)
class ProverProfile:
    id: str
    gpu: GpuSpec
    logical_cpus_on_gpu_numa_node: int
    logical_cpus_total_min: int
    host_memory_gib_min: int
    disk_free_gib_min: int
    os_id: str
    os_version_id: str
    kernel_min: str
    driver: str
    docker_engine_min: str
    nvidia_container_toolkit_min: str
    cost: str | None = None     # a key of ReferenceFile.costs (C7); None: the release's `cost`

@dataclass(frozen=True, slots=True)
class VerifierProfile:
    id: str
    logical_cpus: int
    host_memory_gib: int
    emulation_allowed_on: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class ReferenceFile:
    release: str
    profiles: Mapping[str, ProverProfile | VerifierProfile]
    price_per_gpu_hour: Quantity
    cost_basis: str
    providers: tuple[str, ...]
    price_date: str
    costs: Mapping[str, Cost] | None = None   # C7

    def price_pointer(self, profile: str) -> str: ...  # "/cost/..." or "/costs/<basis>/..."

def load_reference(release: str, root: Path) -> ReferenceFile: ...
```

Rules for profiles:

- R1. Every row names its profile id. A profile's `gpu.count` is the number of GPUs a job binds and the number its cost counts. It is a lower bound on the host: a host that shows more GPUs passes PC-GPU-COUNT, the job binds `gpu.count` of them by index (`--gpu`), the others stay idle (no step sees them), and they are neither recorded as used nor priced; the machine record's `gpu.count_visible` shows how many the host had. A system that needs more GPUs than its profile gives runs on a declared larger profile added to the release file by RFC, and its cost uses that profile's GPU count. v0.1 declares no larger prover profile. A serving profile (R6) binds `gpu.count` GPUs, all of which the configuration uses and its cost counts (amendment of 2026-11-09). (Amended 2026-11-08: a bare-metal H200 node may hold several GPUs, and a hosted H200 flavor that meets `prover-h200-hosted` may come with two, §H200 profiles.)
- R2. `host_memory_gib_min` follows the most demanding v0.1 system's documented need (330 GB available for FlashProve's full-size commit route, external, reported). Exception (amended 2026-11-08): `prover-h200-hosted` is a minimum that admits the smallest hosted H200 offer; a system whose documented need is higher (FlashProve) runs only on a host of that profile that also meets its own need, and the machine record shows which host it was (§H200 profiles).
- R3. `driver` is pinned to one exact version per release; a host with another driver fails conformance. The NVIDIA Container Toolkit and Docker Engine are lower bounds because they do not enter proving arithmetic.
- R4. Rows from different providers within one profile are allowed. The release index reports, per configuration, the providers used and the spread of the configuration mean across providers (max mean over min mean, computed by `iproofs.derive` as formula D-PROVIDER-SPREAD, unit `ratio`, scope of the input rate).
- R5. The release names its reference profile: in v0.1, `prover-h200` (amended 2026-11-08). Rows from profiles with different GPU models are different configurations (RFC-0009 groups rows by profile); they are never pooled or compared as one set, and the profile name is printed beside every number, as for hosted rows.

- R6. Serving profiles (amendment of 2026-11-09). A profile of `kind: serving` runs only reference systems with `reference_role: serve` (RFC-0015 SRV-6); any other system on it is a `config` error. Its `gpu.count` is part of the profile: one serving profile per GPU count, named `serving-<gpu><count>[-hosted]`. `pairs_with` lists the prover profiles whose rows its rows may be divided against (RFC-0004 INV-DERIVE-2 (c)). The validator requires each to have the same `gpu.model` and `form_factor` and the same runtime kind (docker or hosted), so the overhead never crosses GPU generations or runtimes. A hosted serving job binds `gpu.count` GPUs by index (`--gpus i,j,k,l`, through `CUDA_VISIBLE_DEVICES`) and gives the server and its tensor-parallel workers every CPU the container may use; no verifier CPUs, since a reference runs no `verify`. The docker binding of a serving container (NUMA cpusets, `--cpuset-mems`, `--shm-size`) is specified when docker serving profiles are declared, after Q7.

  v0.1 serving profiles (in `reference/v0.1.yaml`): the hosted ones only. Docker serving profiles are added when Q7 is answered, and an 8-GPU profile only when every 4-GPU attempt failed `resource` (RFC-0015 NM-1). Each profile has `gpu.model` "NVIDIA H200", form factor SXM, `memory_mib_min` 140,000 and `cost: "h200"`. Driver, OS and kernel are as the paired prover profile; drivers stay `unpinned` until Q5 resolves, so runs on these profiles are nonconforming and stay out of `results/` (POL-4).

  | Profile | GPUs | Runtime | CPUs total min | Host memory min | Disk free min | `/dev/shm` min | `pairs_with` |
  |---|---|---|---|---|---|---|---|
  | `serving-h200x1-hosted` | 1 | hosted | 23 | 200 GiB | 500 GiB | 8 GiB | `prover-h200-hosted` |
  | `serving-h200x4-hosted` | 4 | hosted | 92 | 800 GiB | 1,000 GiB | 8 GiB | `prover-h200-hosted` |

  The hosted minimums of total CPUs, host memory and disk are those of `prover-h200-hosted` scaled by the GPU count; the CPUs on the first bound GPU's NUMA node stay at its 15 (PC-CPU-NUMA). They admit Hugging Face Jobs' `h200` and `h200x4` flavors: 1 and 4 H200; 23 and 92 vCPU; 256 and 1,024 GB RAM (owner's reading of `hf jobs hardware`, 2026-11-09). Disk: Meta's FP8 release of Maverick is 416.8 GB of files (Hub listing, external, reported). The `/dev/shm` 8 GiB minimum is an assumption, to be revised from the first capture.

### H200 profiles

Amendment of 2026-11-08 (owner decision; the RFC stays Draft). The v0.1 reference GPU becomes the NVIDIA H200 141 GB SXM. NVIDIA states 141 GB of HBM3e for it ([nvidia.com/h200](https://www.nvidia.com/en-us/data-center/h200/), read 2026-11-08). It is a Hopper GPU of compute capability sm_90, the architecture both images are built for (SASH builds with `CUDAARCHS=90`, `systems/sash/README.md`), so the pinned images and adapters are unchanged. Two profiles are added; `prover-h100` and `prover-h100-hosted` stay declared, with their rows and prices.

| Profile | Runtime | Host it describes | Differs from `prover-h100` / `prover-h100-hosted` in |
|---|---|---|---|
| `prover-h200` (reference, R5) | docker | bare metal: 1x NVIDIA H200 141 GB SXM, at least 24 logical CPUs on the GPU's NUMA node and 32 in all, at least 330 GiB host memory, local NVMe with 500 GiB free, Ubuntu 24.04, kernel 5.19 or later, Docker Engine 25.0 and NVIDIA Container Toolkit 1.17 or later on cgroup v2 with the systemd driver | `gpu` and `cost` only |
| `prover-h200-hosted` | hosted (§Hosted execution) | a container a provider starts from the adapter image: 1x NVIDIA H200 141 GB SXM bound, at least 15 logical CPUs it may use on the GPU's NUMA node and 23 in all, and a CPU quota, if any, of at least 15, at least 200 GiB host memory available and allowed, 500 GiB free disk, kernel 5.19 or later, cgroup v2 | `gpu`, `cost`, the CPU and memory minimums, and its driver pin |

- `gpu.model` is `"NVIDIA H200"`, the name NVML reports for the SXM part; `memory_mib_min` is 140,000 MiB, below the 141 GB NVIDIA states, as `prover-h100`'s 80,000 MiB is below its 80 GB. The host probe (`docs/runbooks/host-probe.py`) checks both against the device before the first job; a different NVML name (the PCIe part reports another) is a conformance failure (PC-GPU-MODEL), never a reason to widen the profile without an RFC.
- A host may hold several H200. The job binds one with `--gpu <index>` (docker `--gpus device=<index>`; hosted, `CUDA_VISIBLE_DEVICES` names only the bound index for `setup`, `commit` and `prove`, and nothing for `verify`) and the others stay idle (R1): PC-GPU-COUNT passes, PC-GPU-BUSY checks only the bound GPU, and derived costs count the profile's one GPU. The runner binds the CPUs of the bound GPU's NUMA node (§CPU and memory selection); the probe prints each GPU's node and suggests the index.
- `prover-h200-hosted` is a minimum spec, not one provider's offer. Its CPU and memory minimums are set so that the smallest hosted H200 offer read on 2026-11-08 qualifies: Hugging Face Jobs' `h200` flavor, 1x H200 (141 GB), 23 vCPU, 256 GB RAM, 3,000 GB disk ([jobs-configuration](https://huggingface.co/docs/hub/jobs-configuration), `hf jobs hardware`, read 2026-11-08). 23 CPUs are the 8 verifier CPUs (`verifier-cpu`, §Verifier profile emulation) plus 15 prover CPUs, so `select_cpus` binds 15 prover CPUs on this profile, where the other profiles bind 24; SASH's recorded jobs use 16 prover threads and 20 extraction threads, which its adapter caps at the CPUs it is given (`systems/sash/README.md` §CPU binding). 200 GiB is below the 238 GiB that 256 GB makes, with room for the container's own use. SASH's host memory need is not stated upstream; a SASH job that exceeds the container's limit fails with kind `resource` and is recorded so.
- FlashProve needs more than this minimum: upstream's `run.sh` does not start `commit` below 330 GB available, committing peaked at 299.6 GB, and it needs `madvise(MADV_WIPEONFORK)` and the CPU's SHA extensions (`systems/flashprove/README.md` §Machine needs, external, reported). Its jobs on `prover-h200-hosted` therefore use a larger host of the profile, such as Hugging Face Jobs' `h200x2` (2x H200, 46 vCPU, 512 GB RAM, 6,000 GB disk, same source), binding one GPU (R1); the second GPU is billed by the provider and is not part of the benchmark's cost (C5). FlashProve's timed runs bind 24 CPUs (FlashProve README §CPU binding); on this profile they get 15, so its rows here are not comparable with `prover-h200` rows on that account either (R5, §Hosted execution).
- A provider's list price is not this benchmark's price: rows on both profiles cost from `costs.h200` (C7). The Hugging Face Jobs flavors (5.00 USD/h for `h200`, 10.00 USD/h for `h200x2`, billed per minute, same source) do not state their form factor, which C3 requires, so they are not readings of `costs.h200`.
- NVIDIA Confidential Computing (CC) is a GPU mode set by the host's operator; it is enabled on the research cluster named above (owner's report, 2026-11-08). H200 hosts run with CC mode off, so that every H200 row has one GPU configuration; the CC mode of the GPU behind either v0.1 system's published figures is not stated in its documentation at the pins in RFC-0003. The machine record has no CC field (INV-MR-1), so the mode is checked by the host probe before each campaign and written in the campaign log (Q4). A hosted container may not be able to read it; the probe then reports it unread.
- Drivers: both profiles are `unpinned` until a host is read. `prover-h200` is pinned on the campaign host under Q3 (issue #77); `prover-h200-hosted` is pinned from the driver a hosted H200 reports (Q5), as `prover-h100-hosted` was. Until then every H200 host fails PC-DRIVER, so H200 runs are development runs made with `--allow-nonconforming`, which POL-4 keeps out of `results/` (RFC-0013).
- Verifier emulation is allowed on both profiles (`verifier-cpu` `emulation.allowed_on`).

RISK: FlashProve's build guide names an H100 as the GPU it needs (`prover/docs/build.md` at the pin); on an H200 it is not stated. Its `setup` compares a digest of scales fitted in float32 on the GPU, and upstream writes that "its rounding can differ between GPU models, drivers and torch's CUDA libraries" (`systems/flashprove/README.md`). Resolution: an H200 run that stops there is recorded as a failed run with its exit code and last lines (AGENTS.md rule 5); the adapter is not changed to pass it (AGENTS.md rule 1), and the finding goes to an issue and, if needed, an RFC on the reference GPU.

### Machine record

Written by `iproofs machine-record` and stored in `manifest.json` `machine` (schema `manifest/1`). Fields, exhaustive:

| Field | Source on Linux | Example form |
|---|---|---|
| `gpu.model` | NVML `nvmlDeviceGetName` | string |
| `gpu.count_visible` | NVML device count | int |
| `gpu.memory_total_mib` | NVML `nvmlDeviceGetMemoryInfo.total` | int |
| `gpu.bound_index` | harness choice | int |
| `gpu.numa_node` | `/sys/bus/pci/devices/<bdf>/numa_node` | int |
| `gpu.driver_version` | NVML `nvmlSystemGetDriverVersion` | string |
| `gpu.cuda_driver_api` | NVML `nvmlSystemGetCudaDriverVersion_v2` | string |
| `cpu.model` | `/proc/cpuinfo` `model name` | string |
| `cpu.sockets`, `cpu.physical_cores`, `cpu.logical_cpus` | `/sys/devices/system/cpu/*/topology` | int |
| `cpu.smt_active` | `/sys/devices/system/cpu/smt/active` | bool |
| `cpu.bound_prover` | harness choice (§CPU selection) | list of int |
| `cpu.bound_verifier`, `cpu.bound_verifier_single` | harness choice | list of int |
| `numa.nodes` | `/sys/devices/system/node/` | int |
| `numa.bound_mems` | harness choice | list of int |
| `memory.total_bytes`, `memory.available_bytes_at_start` | `/proc/meminfo` | int |
| `disk.type`, `disk.free_bytes_at_start` | `/sys/block/<dev>/queue/rotational`, transport; `statvfs` of the results and model directories | string, int |
| `os.id`, `os.version_id` | `/etc/os-release` | string |
| `kernel.release` | `uname -r` | string |
| `container.docker_engine`, `container.cgroup_driver`, `container.cgroup_version` | `docker version`, `docker info` | string |
| `container.nvidia_container_toolkit` | `nvidia-ctk --version` | string |
| `container.execution` | `hosted` under §Hosted execution; absent under docker | enum |
| `cpu.cgroup_quota_cpus` | `/sys/fs/cgroup/cpu.max` of the harness's cgroup, quota over period; absent without a quota | number |
| `memory.cgroup_limit_bytes` | `/sys/fs/cgroup/memory.max`; absent without a limit | int |
| `gpu.bound_indices` | harness choice: every bound GPU (amendment of 2026-11-09); `gpu.bound_index` stays as the first | list of int |
| `gpu.numa_nodes` | as `gpu.numa_node`, one per bound GPU | list of int |
| `gpu.nvlink_active_links` | NVML `nvmlDeviceGetNvLinkState` over each bound GPU's links, null where NVML does not report it | list of int or null |
| `gpu.unbound_samples` | per visible unbound GPU: compute-process count, memory used and utilisation, the maxima over its readings (PC-GPU-IDLE; one reading per record today) | list of objects |
| `container.shm_bytes` | `statvfs` of `/dev/shm` | int |
| `provider` | declared by the runner on the command line (`--provider`) | string |
| `verifier_host` | `same_as_prover` or `separate` | enum |

Excluded, and rejected by the secrets and identifiers scan (RFC-0013) if they appear anywhere in a run directory: hostname, fully qualified domain name, IPv4 and IPv6 addresses, MAC addresses, GPU UUID, GPU serial number, board part serial, CPU microcode serial or PPIN, disk serial and WWN, cloud instance ID and region zone identifiers, account and user names, SSH configuration and aliases, absolute home paths.

INV-MR-1: `machine` contains only the fields above; `manifest/1` sets `additionalProperties: false` on it.
INV-MR-2: the record is collected before `info` and again after the last step; a difference in `gpu.driver_version`, `kernel.release` or `cpu.bound_prover` is an `environment` error.

### CPU and memory selection

Prover containers get `--cpuset-cpus <bound_prover> --cpuset-mems <bound_mems>`; verifier containers get `--cpuset-cpus <bound_verifier>` (or `<bound_verifier_single>`), no GPU, `--memory 32g`.

```text
select_cpus(topology, gpu_numa_node, n_prover, n_verifier=8):
    node_cpus   = logical CPUs on gpu_numa_node, ascending id
    cores       = group node_cpus by (package_id, core_id), ordered by smallest cpu id in group
    first_pass  = [min(group) for group in cores]          # one logical CPU per physical core
    second_pass = [remaining cpus of each group, ascending]  # SMT siblings
    ordered     = first_pass + second_pass
    if len(ordered) < n_prover: fail environment("not enough CPUs on GPU NUMA node")
    prover      = ordered[:n_prover]
    others      = all logical CPUs not in prover, same ordering rule, NUMA node of gpu first
    if len(others) < n_verifier: fail environment("not enough CPUs for verifier emulation")
    verifier    = others[:n_verifier]
    verifier_1  = verifier[:1]
    mems        = [gpu_numa_node]
    return prover, verifier, verifier_1, mems
```

The function is pure (`iproofs.provenance.select_cpus(topology: Topology, gpu_numa_node: int, n_prover: int, n_verifier: int) -> CpuBinding`) and is tested against stored topologies. `n_prover` is the profile's `cpu.logical_cpus_on_gpu_numa_node`: 24 on every v0.1 profile except `prover-h200-hosted`, 15 (amended 2026-11-08, §H200 profiles). Under §Hosted execution the topology is first reduced to the CPUs the harness process may run on (its scheduler affinity, which a provider's cpuset narrows), so no CPU outside the container's set is bound; a CPU quota does not narrow it and is checked by PC-CPU-QUOTA. Verifier CPUs never overlap prover CPUs, so verification timed after proving is not disturbed by a lingering prover process. Upstream advice on thread binding (FlashProve pins its threads only to CPUs it is allowed to use, per its documentation) is followed and noted in each adapter README (RFC-0005).

### Verifier profile emulation

In v0.1 the verifier profile is emulated on the prover host: no GPU device, 8 bound logical CPUs (1 for `verify.single_thread`), memory limit 32 GiB, `--network none`. The run records `verifier_host: same_as_prover` and the CPU model. A separate CPU-only host MAY be used; proofs are then copied by digest and the record says `verifier_host: separate` with that host's own machine record under `machine_verifier`.

RISK: an emulated verifier shares caches, memory bandwidth and the CPU model of a server; a real 8-core machine (for example a laptop) may verify slower or faster. Resolution: rows print the CPU model beside every verify number; the first release report compares one configuration verified on both an emulated and a separate host and publishes the difference; if it exceeds the reproduction tolerance of RFC-0007, a follow-up RFC requires a separate verifier host.

### Profile conformance check

`iproofs.provenance.check_profile(record: MachineRecord, profile: ProverProfile) -> list[ConformanceFailure]` runs before `info`. Any failure aborts the job with kind `environment` and exit code 3 (RFC-0010); nothing is timed. Checks:

| Check id | Fails when |
|---|---|
| PC-GPU-MODEL | bound GPU name does not match `gpu.model` |
| PC-GPU-MEM | `memory_total_mib` < `memory_mib_min` |
| PC-GPU-COUNT | fewer visible GPUs than `gpu.count`; on a serving profile, a bound count other than `gpu.count` |
| PC-GPU-BUSY | another compute process holds a bound GPU (RFC-0011); every bound GPU is checked |
| PC-GPU-IDLE | on any profile, a visible unbound GPU has a compute process, or memory used or utilisation above the idle baseline, when the machine record is taken before `info`; a compute process on one when the record is taken again after the last step fails the job `environment` (INV-MR-2) (amendment of 2026-11-09). The idle baseline is an assumption until the first captures set it: 1,024 MiB used and 5 % utilisation. Sampling the unbound GPUs throughout the job, beside the bound ones, is a later amendment |
| PC-GPU-LINK | record only: on a serving profile with `gpu.count` > 1, the NVLink state of each bound GPU is recorded, not checked, until the first `h200x4` capture shows whether NVML reports it inside a Hugging Face container. A later amendment makes it a check |
| PC-SHM | hosted: `container.shm_bytes` below the profile's `shm_gib_min` |
| PC-DRIVER | driver version differs from `driver` |
| PC-CPU-NUMA | fewer than `logical_cpus_on_gpu_numa_node` logical CPUs on the GPU's NUMA node (hosted: of those the container may use) |
| PC-CPU-TOTAL | fewer than `logical_cpus_total_min` logical CPUs |
| PC-CPU-QUOTA | `cgroup_quota_cpus` < `logical_cpus_on_gpu_numa_node` |
| PC-MEM | the smaller of `available_bytes_at_start` and `cgroup_limit_bytes` < `host_memory_gib_min` GiB |
| PC-DISK | free space < `free_gib_min` on the results or model filesystem, or disk type not NVMe |
| PC-OS | OS id or version differs |
| PC-KERNEL | kernel older than `kernel_min` |
| PC-CGROUP | cgroup version is not 2, or driver is not systemd (hosted: cgroup version is not 2) |
| PC-RUNTIME | Docker Engine or NVIDIA Container Toolkit below minimum; or the record's `execution` differs from the profile's runtime |

`iproofs run --allow-nonconforming` exists for development only: the run is written with `harness.nonconforming: true` in the manifest (RFC-0014) and the list of failures, and the validator (RFC-0013) refuses it in `results/` for any release.

### Hosted execution

Some GPU providers rent an H100 or H200 only as a container they start themselves, from an image the renter names, without a docker engine, user namespaces or a writable cgroup tree inside. A profile whose `container_runtime` is `{kind: "hosted", cgroup_version: "2"}` describes such a host. The provider starts the system's pinned image (or, for development, a local build named with `--image`, never eligible for a release under RFC-0014), the harness is installed inside that container, and `iproofs run --hosted --gpu <index>` runs each step as a process of the image's `ENTRYPOINT`:

- CPU binding is the scheduler affinity of the bound CPUs (`taskset -c`), computed by §CPU and memory selection. As root, the call drops to the adapter uid with no capabilities and no new privileges (`setpriv`), as `docker --user --cap-drop ALL --security-opt no-new-privileges` would.
- The recorded commitment copies of RFC-0014 become root-owned and read-only before the call. The verifier reads the harness's own copies, as under docker.
- The adapter gets the environment the image declares, read from the container's first process, without the names a provider adds (access keys, ports, addresses).
- The GPU is chosen by `CUDA_VISIBLE_DEVICES` in PCI bus order; `verify` sees no GPU.
- Docker gives each call a new `/tmp` tmpfs. Here `/tmp` outlives the call, so before each call the harness removes what the adapter uid left in it; engine and compile caches never carry from one repetition to the next. The harness keeps its own files out of `/tmp`.

Not isolated, and recorded so: the network (`commands[].network: "provider"` in `manifest.json`); memory binding (`numa.bound_mems` is the intended node, not enforced: setting a memory policy needs a capability the container lacks); memory limits, including the verifier's 32 GiB; a read-only root filesystem. CPUs may be shared with other tenants under a quota (`cpu.cgroup_quota_cpus`). The host's OS is not visible (`/etc/os-release` is the image's), so PC-OS does not apply and `os` is absent from the record. The disk is the container's overlay, so `disk.type` is absent.

Resource readings (RFC-0011) come from the container's own cgroup: `cpu_seconds` is the difference of `cpu.stat usage_usec` over the call, `host_memory_peak_anon` is the sampled `memory.stat anon`, and an OOM kill during the call is a `resource` failure. These include the harness process, which sleeps between samples. `host_memory_peak_kernel` is null with `not_measurable_on_profile`: the container's `memory.peak` covers its whole life, not one step. GPU readings are NVML's, as on any host.

The calibration self-test of a hosted host is `iproofs machine-record --selftest --hosted` (RFC-0011 §Calibration self-test): the probe runs as a process in the container, ST-CGROUP reads the container's own counters, and ST-OOM is not run.

Rows from a hosted profile are their own configurations (RFC-0009 groups rows by profile); they are never pooled or compared with rows from a docker profile as one set, and the profile name is printed beside every number.

RISK: shared CPUs and an open network make hosted timings noisier and weaker evidence than docker ones. Resolution: the profile name is part of every row's label, the release report says which rows are hosted, and the v0.1 report compares one configuration on both kinds of host once a docker host is available.

### Cost basis

- C1. Costs are computed only from the release's `price_per_gpu_hour_usd`, never from a team's own price. A team's own cost figure MAY be shown as `external`.
- C2. The price is an `asserted` quantity with its basis, providers and date.
- C3. Default basis: the median on-demand list price, for the profile's GPU in the profile's form factor, of at least three named providers, read on one stated date. The reading is archived (provider page URL and date) in the release report.
- C4. The price is fixed for the life of a release. A new price needs a new release or an RFC; past derived costs are never recomputed in place.
- C5. CPU, host memory, disk and network are not priced in v0.1. Every page and report that shows a cost states this.
- C6. A release with `value: 0` or a missing date cannot be frozen (`iproofs release freeze` exits 1). This holds for every basis (C7).
- C7. One basis per GPU model (amended 2026-11-08). A serving row's derived costs count its profile's `gpu.count` GPUs at `costs.h200` (amendment of 2026-11-09). With one price per GPU-hour on both sides, the cost ratio of a system row and its serving row equals D-OVERHEAD-S, and C5 holds: CPU, host memory, disk and network are not priced. The Hugging Face flavor prices (5, 10, 20 and 40 USD/h for 1, 2, 4 and 8 H200, owner's reading of 2026-11-09) are not readings of the basis (no form factor stated, C3). `cost` is the release's default basis. A prover profile whose GPU model is priced apart names a basis of `costs` in its `cost` field, and its rows' derived costs take their price from `costs.<basis>.price_per_gpu_hour_usd` (`ReferenceFile.price_pointer`). Each basis follows C2 to C6 on its own; the validator recomputes each median (COST-1) and refuses a profile that names a basis `costs` lacks (COST-2). In v0.1, `cost` stays the H100 SXM basis of Q1, so the derived costs of the runs already in `results/` still recompute from it (C4: past derived costs are never recomputed in place), and `costs.h200` prices `prover-h200` and `prover-h200-hosted`.

H200 readings for `costs.h200` (rule C3, read 2026-11-08 from each provider's public pricing page; archived in `reference/v0.1.yaml` `costs.h200.readings`, whose median the validator recomputes, so it is not typed here):

| Provider | Page | Offer read | List price | GPUs |
|---|---|---|---|---|
| RunPod | [runpod.io/pricing](https://www.runpod.io/pricing) | H200 SXM 141 GB, Secure Cloud (its own data centres; the Community Cloud marketplace is not read, as in Q1) | 5.29 USD/h | 1 |
| CoreWeave | [coreweave.com/pricing](https://www.coreweave.com/pricing) | NVIDIA HGX H200, on-demand | 50.44 USD/h | 8 |
| Nebius | [nebius.com/prices](https://nebius.com/prices) | NVIDIA HGX H200, on-demand, per GPU | 5.40 USD/h | 1 |
| DigitalOcean | [digitalocean.com/pricing/gpu-droplets](https://www.digitalocean.com/pricing/gpu-droplets) | NVIDIA HGX H200 GPU Droplet, on-demand, per GPU | 4.47 USD/h | 1 |

All four are list prices of the SXM (HGX) form factor, grade asserted, tier reported. Not read: Lambda, a Q1 provider, listed no H200 on 2026-11-08; offers that do not state their form factor, which C3 requires; hyperscalers, for the reason Q1 gives.

### Failure modes

| Failure | Response |
|---|---|
| Reference file missing or invalid | `config` error at job start, exit 1 for validate, exit 2 for run |
| Host fails a conformance check | `environment` error, exit 3, no timed step runs, no run directory in `results/` |
| Driver or kernel changes mid-job (INV-MR-2) | job failed at the step where detected, kind `environment` |
| Excluded identifier found in a run directory | CI secrets scan fails; the run is not merged |
| Topology lacks enough CPUs for verifier emulation | `environment`; the runner may use a separate verifier host |
| Price placeholder at release freeze | freeze exits 1 (C6), for any basis (C7) |
| A profile names a cost basis that `costs` lacks | G2 fails with COST-2; a run on it fails with `config` before any timed step |

## Alternatives Considered

- **Let each team choose its machine and normalise afterwards.** Considered because it lowers the cost of joining. Rejected: normalising across GPUs needs a performance model the benchmark would have to defend; fixed profiles make rows comparable within a release without one (PRD G2).
- **A separate physical verifier host as the default.** Considered because it is the faithful model of a relying party's machine. Rejected for v0.1 on cost and logistics (SASH's 4,096-context run totals about 19.8 GB of proofs, external, reported, SASH results repository at the pin, and every proof would move between hosts); kept as an allowed option and as the RISK resolution path.
- **Price CPU and memory.** Considered because FlashProve needs about 300 GB of host memory (external, reported). Rejected for v0.1: providers bundle CPU and memory with the GPU in different ways, so any split would be an arbitrary choice the benchmark would have to defend; the omission is stated wherever cost appears (C5).
- **Spot or committed-use prices.** Considered because they are what large users pay. Rejected: they vary by hour and contract and cannot be reproduced by a reader; on-demand list prices can.
- **Record the full `lscpu`, `nvidia-smi -q` and `dmidecode` output.** Considered for completeness. Rejected: these contain serials and UUIDs (AGENTS.md rule 7); the explicit field list is enough to reproduce a run.

## Drawbacks

- A single exact driver version per release may exclude hosts whose provider ships another driver; runners must install the pinned one.
- The emulated verifier is a server CPU, not a relying party's laptop (RISK above).
- One price for a whole release ignores price changes during the review window.
- Two GPU models in one release split its rows: H100 and H200 rows are separate configurations, and the H100 rows already recorded are not comparable with the H200 reference rows (R5).
- `prover-h200-hosted` is a minimum: two hosts that meet it can differ (one GPU or two, 23 or 46 CPUs, 256 or 512 GB), and FlashProve meets its own memory floor only on the larger one. The machine record in each manifest says which host a row ran on, and hosted rows are noisier evidence than docker rows (§Hosted execution RISK). A provider bills every GPU of the flavor, while derived costs count one (R1, C5).

## Conflicts of Interest

The author's affiliations and any interest in a measured system are declared in `MAINTAINERS.md` before this RFC enters Last call (RFC-0001).

## Migration / Rollout

Revision of 2026-11-08: the v0.1 reference GPU becomes the H200 (§H200 profiles); `prover-h200` and `prover-h200-hosted` are added; `select_cpus` takes the profile's prover CPU count and, hosted, the container's CPU set; R1 says how a host with more GPUs than its profile is treated; R5 names the reference profile; C7 and `reference/1`'s optional `costs` and profile `cost` price each GPU model apart. The change is additive: existing profiles, prices and runs are unchanged, and the runs in `results/v0.1` (recorded on `prover-h100-hosted`) keep their derived costs.

Amendment of 2026-11-09 (owner decision, RFC-0015 SRV-6): R6 declares serving profiles, which bind several GPUs, for production serving only; prover profiles stay one GPU. `reference/1` gains `kind: serving`, `pairs_with` and `shm_gib_min`, and admits `gpu.count` above 1 for serving profiles only. The machine record gains `gpu.bound_indices`, `gpu.numa_nodes`, `gpu.nvlink_active_links`, `gpu.unbound_samples` and `container.shm_bytes`; none identifies a host. Conformance gains PC-GPU-IDLE, PC-GPU-LINK (record only), PC-SHM and an exact PC-GPU-COUNT on serving profiles. The docker serving binding (TC-CPU-SERVING) is deferred with the docker serving profiles. The change is additive: no stored run changes.

Earlier: no results existed yet. Revisions from the draft of 2026-11-03: the profile gains OS, kernel, runtime and cgroup requirements; the machine record field list and exclusion list are new; CPU selection and verifier emulation are fixed; the cost block becomes a labelled quantity. `reference/1` is a new schema. Adding a profile is additive; changing a profile's requirements within a release is not allowed (a new release file is needed).

## Testing Strategy

- TC-REF-VALID / TC-REF-INVALID: schema examples; invalid cases: missing `driver`, `price_per_gpu_hour_usd` without `grade`, verifier profile with a GPU, unknown field in a profile.
- TC-CPU-2SOCKET-SMT: stored topology of 2 sockets, 48 physical cores, SMT on, GPU on node 1; expects 24 prover CPUs, one per physical core on node 1, verifier CPUs disjoint, mems [1].
- TC-CPU-SMALL-NODE: node with 16 logical CPUs; expects `environment` failure PC-CPU-NUMA.
- TC-CPU-SMT-OFF: SMT off; second pass empty; selection still deterministic.
- TC-CPU-DETERMINISTIC: property test (hypothesis) over random topologies: same input gives same output; prover and verifier sets are disjoint; all chosen CPUs exist.
- TC-MR-FIELDS: `machine-record` on a fixture `/sys` and `/proc` tree (`harness/tests/fixtures/host/`) produces exactly the listed fields.
- TC-MR-NO-IDENTIFIERS: fixture tree seeded with a hostname, GPU UUID and MAC; asserts none appears in the record or the logs.
- TC-MR-DRIFT: record before and after with different kernel strings; asserts `environment` failure.
- TC-CONFORM-EACH: one test per check id, each flipping exactly one fixture field.
- TC-FREEZE-PRICE-ZERO: `release freeze` with `value: 0` exits 1.
- TC-H200-CONFORM (`harness/tests/unit/test_h200_profiles.py`): a fake record of a bare-metal node with 8 H200 (GPU 0 bound) passes every check on `prover-h200` once the driver is pinned; with the driver unpinned, PC-DRIVER is its only failure; with no GPU visible it fails PC-GPU-COUNT; an H100 record fails PC-GPU-MODEL and PC-GPU-MEM; a hosted record fails PC-RUNTIME. Fake records of the Hugging Face Jobs `h200` flavor (1 GPU, 23 CPUs) and `h200x2` flavor (2 GPUs visible, GPU 1 bound) pass every check on `prover-h200-hosted`; a quota of 14 CPUs fails PC-CPU-QUOTA and 192 GiB fails PC-MEM.
- TC-CPU-HOSTED (`test_h200_profiles.py`): on a 23-CPU topology `select_cpus` with `n_prover=15` binds 15 prover and 8 verifier CPUs; a hosted host's topology is reduced to its scheduler affinity; `iproofs run` passes the profile's prover CPU count.
- TC-COST-BASIS (`test_h200_profiles.py`, `test_cost.py`): H200 profiles price from `costs.h200`, H100 profiles from `cost`; COST-1 is checked on every basis against a hand-computed median; COST-2 refuses an unknown basis.
- GPU-host test GH-MR-H100: on a real prover-h100 host, `iproofs machine-record --selftest` passes and the record validates. GH-MR-H200 is the same on a `prover-h200` host, and on a `prover-h200-hosted` host with `--hosted`; there `test_numa_binding.py` runs with `IPROOFS_PROFILE=prover-h200-hosted`, so it binds the profile's 15 prover CPUs from the container's CPU set, as a hosted job does.
- TC-SERVING-PROFILE (`test_h200_profiles.py`): fake records of `h200x4` (4 GPUs bound, shm 8 GiB) pass `serving-h200x4-hosted`, with NVLink state null or down recorded and not failed (PC-GPU-LINK record only). 3 bound GPUs fail PC-GPU-COUNT, and a `pairs_with` naming an H100 profile fails the validator.
- TC-GPU-IDLE (`test_provenance.py`): fake NVML readings for `h200x2` with GPU 0 bound. GPU 1 at the idle baseline passes; GPU 1 with one compute process, or with memory above the baseline at one sample, fails `environment`.
- GPU-host test GH-MR-H200X4: `iproofs machine-record --hosted --gpus 0,1,2,3 --selftest` on `h200x4`.

## Open Questions

- Resolved Q1: rule C3 with Lambda, RunPod and CoreWeave, read on 2026-11-04 from their public pricing pages: Lambda's 1x H100 SXM 80 GB, RunPod's H100 SXM on Secure Cloud (its own data centres, not the Community Cloud marketplace), and CoreWeave's 8-GPU HGX H100 instance divided by its 8 GPUs. Each reading (provider, URL, offer, list price, GPU count) is archived in `reference/v0.1.yaml` `cost.readings`, and the validator recomputes the median per GPU-hour from them (COST-1), so the price is never typed by hand. Hyperscalers were not read: their H100 offers are 8-GPU instances whose list prices vary by region.
- Resolved Q2 (2026-11-08, owner decision): a second GPU model is added, the H200, and it becomes the v0.1 reference (§H200 profiles, R5); the H100 profiles stay declared. Profiles whose jobs use more than one GPU are still not declared: a host may show more GPUs than its profile asks for, and they stay idle and unpriced (R1). A multi-GPU profile needs an RFC. Amended 2026-11-09: serving profiles with more than one GPU are declared (R6); prover profiles stay one GPU.
- OPEN QUESTION Q3 (owner: AbdelStark, resolve by: 2027-01-31): which exact NVIDIA driver version is pinned for v0.1? Default until resolved: the newest driver that supports both CUDA 13.2 Update 2 (FlashProve) and CUDA 12.9 (SASH) containers, chosen in the reference file pull request. Amended 2026-11-08: the same question now covers `prover-h200`, pinned on the H200 campaign host.
- OPEN QUESTION Q4 (owner: AbdelStark, resolve by: 2026-11-30): how is the GPU's Confidential Computing mode recorded in each run? Default until resolved: H200 runs need CC mode off; the host probe (`docs/runbooks/host-probe.py`) reads it from `nvidia-smi conf-compute` before each campaign, and the campaign log in the results pull request records its `cc` line; a host whose mode is on or unread runs no campaign job. Resolution path: an amendment adding a machine record field (`gpu.cc_mode`, from NVML) and a conformance check, with `manifest/1`.
- OPEN QUESTION Q5 (owner: AbdelStark, resolve by: 2026-11-30): which driver does `prover-h200-hosted` pin? Default until resolved: `unpinned`, so every hosted H200 fails PC-DRIVER and its runs are development runs (`--allow-nonconforming`, kept out of `results/` by POL-4). Resolution path: the driver the probe and `iproofs machine-record --hosted` report on a Hugging Face Jobs H200 container, written in by a pull request, as for `prover-h100-hosted`; a later provider with another driver needs its own pin (R3).
- OPEN QUESTION Q6 (owner: AbdelStark, resolve by: 2026-11-30): a provider that starts the container as the image's own user (both adapter images declare `USER 10001`) leaves the harness without root, so §Hosted execution cannot drop the adapter's privileges, clear the adapter's `/tmp` between calls, or make the recorded commitment copies root-owned: they are read-only but owned by the uid that runs the adapter. A secret given to such a job is readable by the adapter too, from the first process's environment under the same uid. Default until resolved: such runs are development runs. Hugging Face Jobs does not document which user its containers run as; the probe prints whether it is root.

- OPEN QUESTION Q7 (owner: AbdelStark, resolve by: 2026-12-15; raised 2026-11-09): does the research cluster have four H200 SXM in one NVLink node? Without that, docker Maverick serving cannot run there, and only hosted serving rows (paired with hosted prover rows) exist. Default until resolved: hosted serving profiles only; docker serving profiles are declared when this is answered.

## References

- docs/PRD.md §4 (G2, G3), §7 (F5), §11.
- AGENTS.md rule 7.
- [RFC-0004](0004-metrics-timing-grades.md) for cost formulas; [RFC-0005](0005-adapter-contract.md) for container invocation; [RFC-0007](0007-evidence-tiers-and-reproduction.md) for reproduction on another provider; [RFC-0011](0011-measurement-and-sampling.md) for the GPU busy check and sampling; [RFC-0012](0012-schemas-and-serialization.md) for `reference/1` and `manifest/1`; [RFC-0013](0013-validation-and-ci.md) for the identifiers scan.
- Linux sysfs CPU topology and cgroup v2 documentation (kernel.org, `Documentation/admin-guide/cgroup-v2.rst`).
