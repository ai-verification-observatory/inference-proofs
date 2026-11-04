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

A proving rate means little without the machine. Both v0.1 systems publish numbers from one NVIDIA H100 80 GB, with different host resources: FlashProve uses 24 of a host's 96 CPUs and up to about 300 GB of host memory, and its full-size route will not start committing below 330 GB available; SASH's manifest records the GPU and CUDA version (PRD §1; both external, reported, from the upstream repositories at the pins in RFC-0003). Prices differ by provider and by month. Fixing profiles and a price per release keeps rows comparable within a release (PRD G2, F5). AGENTS.md rule 7 forbids machine identifiers beyond what this RFC asks for, so the record's contents must be listed exhaustively.

## Goals

- One file per release, `reference/<release>.yaml`, valid against `schema/reference/1.schema.json`, defines every profile and the cost basis.
- Every run stores a machine record whose fields are exactly those listed here, and none of the excluded ones.
- CPU and memory binding is deterministic given the host topology, and recorded.
- A host that does not meet its profile fails before any timed step, with kind `environment`.
- Cost figures use only the release's asserted price.

## Non-Goals

- Multi-GPU profiles and GPUs other than H100 (v0.1 systems need neither; see Open Questions).
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
    emulation: {allowed_on: ["prover-h100"]}
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

def load_reference(release: str, root: Path) -> ReferenceFile: ...
```

Rules for profiles:

- R1. Every row names its profile id. A system that needs more than `prover-h100` runs on a declared larger profile added to the release file by RFC, and its cost uses that profile's GPU count. v0.1 declares no larger profile.
- R2. `host_memory_gib_min` follows the most demanding v0.1 system's documented need (330 GB available for FlashProve's full-size commit route, external, reported).
- R3. `driver` is pinned to one exact version per release; a host with another driver fails conformance. The NVIDIA Container Toolkit and Docker Engine are lower bounds because they do not enter proving arithmetic.
- R4. Rows from different providers within one profile are allowed. The release index reports, per configuration, the providers used and the spread of the configuration mean across providers (max mean over min mean, computed by `iproofs.derive` as formula D-PROVIDER-SPREAD, unit `ratio`, scope of the input rate).

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
| `provider` | declared by the runner on the command line (`--provider`) | string |
| `verifier_host` | `same_as_prover` or `separate` | enum |

Excluded, and rejected by the secrets and identifiers scan (RFC-0013) if they appear anywhere in a run directory: hostname, fully qualified domain name, IPv4 and IPv6 addresses, MAC addresses, GPU UUID, GPU serial number, board part serial, CPU microcode serial or PPIN, disk serial and WWN, cloud instance ID and region zone identifiers, account and user names, SSH configuration and aliases, absolute home paths.

INV-MR-1: `machine` contains only the fields above; `manifest/1` sets `additionalProperties: false` on it.
INV-MR-2: the record is collected before `info` and again after the last step; a difference in `gpu.driver_version`, `kernel.release` or `cpu.bound_prover` is an `environment` error.

### CPU and memory selection

Prover containers get `--cpuset-cpus <bound_prover> --cpuset-mems <bound_mems>`; verifier containers get `--cpuset-cpus <bound_verifier>` (or `<bound_verifier_single>`), no GPU, `--memory 32g`.

```text
select_cpus(topology, gpu_numa_node, n_prover=24, n_verifier=8):
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

The function is pure (`iproofs.provenance.select_cpus(topology: Topology, gpu_numa_node: int, n_prover: int, n_verifier: int) -> CpuBinding`) and is tested against stored topologies. Verifier CPUs never overlap prover CPUs, so verification timed after proving is not disturbed by a lingering prover process. Upstream advice on thread binding (FlashProve pins its threads only to CPUs it is allowed to use, per its documentation) is followed and noted in each adapter README (RFC-0005).

### Verifier profile emulation

In v0.1 the verifier profile is emulated on the prover host: no GPU device, 8 bound logical CPUs (1 for `verify.single_thread`), memory limit 32 GiB, `--network none`. The run records `verifier_host: same_as_prover` and the CPU model. A separate CPU-only host MAY be used; proofs are then copied by digest and the record says `verifier_host: separate` with that host's own machine record under `machine_verifier`.

RISK: an emulated verifier shares caches, memory bandwidth and the CPU model of a server; a real 8-core machine (for example a laptop) may verify slower or faster. Resolution: rows print the CPU model beside every verify number; the first release report compares one configuration verified on both an emulated and a separate host and publishes the difference; if it exceeds the reproduction tolerance of RFC-0007, a follow-up RFC requires a separate verifier host.

### Profile conformance check

`iproofs.provenance.check_profile(record: MachineRecord, profile: ProverProfile) -> list[ConformanceFailure]` runs before `info`. Any failure aborts the job with kind `environment` and exit code 3 (RFC-0010); nothing is timed. Checks:

| Check id | Fails when |
|---|---|
| PC-GPU-MODEL | bound GPU name does not match `gpu.model` |
| PC-GPU-MEM | `memory_total_mib` < `memory_mib_min` |
| PC-GPU-COUNT | fewer visible GPUs than `gpu.count` |
| PC-GPU-BUSY | another compute process holds the bound GPU (RFC-0011) |
| PC-DRIVER | driver version differs from `driver` |
| PC-CPU-NUMA | fewer than 24 logical CPUs on the GPU's NUMA node |
| PC-CPU-TOTAL | fewer than `logical_cpus_total_min` logical CPUs |
| PC-MEM | `available_bytes_at_start` < `host_memory_gib_min` GiB |
| PC-DISK | free space < `free_gib_min` on the results or model filesystem, or disk type not NVMe |
| PC-OS | OS id or version differs |
| PC-KERNEL | kernel older than `kernel_min` |
| PC-CGROUP | cgroup version is not 2, or driver is not systemd |
| PC-RUNTIME | Docker Engine or NVIDIA Container Toolkit below minimum |

`iproofs run --allow-nonconforming` exists for development only: the run is written with `harness.nonconforming: true` in the manifest (RFC-0014) and the list of failures, and the validator (RFC-0013) refuses it in `results/` for any release.

### Cost basis

- C1. Costs are computed only from the release's `price_per_gpu_hour_usd`, never from a team's own price. A team's own cost figure MAY be shown as `external`.
- C2. The price is an `asserted` quantity with its basis, providers and date.
- C3. Default basis: the median on-demand list price, for the profile's GPU in the profile's form factor, of at least three named providers, read on one stated date. The reading is archived (provider page URL and date) in the release report.
- C4. The price is fixed for the life of a release. A new price needs a new release or an RFC; past derived costs are never recomputed in place.
- C5. CPU, host memory, disk and network are not priced in v0.1. Every page and report that shows a cost states this.
- C6. A release with `value: 0` or a missing date cannot be frozen (`iproofs release freeze` exits 1).

### Failure modes

| Failure | Response |
|---|---|
| Reference file missing or invalid | `config` error at job start, exit 1 for validate, exit 2 for run |
| Host fails a conformance check | `environment` error, exit 3, no timed step runs, no run directory in `results/` |
| Driver or kernel changes mid-job (INV-MR-2) | job failed at the step where detected, kind `environment` |
| Excluded identifier found in a run directory | CI secrets scan fails; the run is not merged |
| Topology lacks enough CPUs for verifier emulation | `environment`; the runner may use a separate verifier host |
| Price placeholder at release freeze | freeze exits 1 (C6) |

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

## Conflicts of Interest

The author's affiliations and any interest in a measured system are declared in `MAINTAINERS.md` before this RFC enters Last call (RFC-0001).

## Migration / Rollout

No results exist yet. Revisions from the draft of 2026-11-03: the profile gains OS, kernel, runtime and cgroup requirements; the machine record field list and exclusion list are new; CPU selection and verifier emulation are fixed; the cost block becomes a labelled quantity. `reference/1` is a new schema. Adding a profile is additive; changing a profile's requirements within a release is not allowed (a new release file is needed).

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
- GPU-host test GH-MR-H100: on a real prover-h100 host, `iproofs machine-record --selftest` passes and the record validates.

## Open Questions

- Resolved Q1: rule C3 with Lambda, RunPod and CoreWeave, read on 2026-11-04 from their public pricing pages: Lambda's 1x H100 SXM 80 GB, RunPod's H100 SXM on Secure Cloud (its own data centres, not the Community Cloud marketplace), and CoreWeave's 8-GPU HGX H100 instance divided by its 8 GPUs. Each reading (provider, URL, offer, list price, GPU count) is archived in `reference/v0.1.yaml` `cost.readings`, and the validator recomputes the median per GPU-hour from them (COST-1), so the price is never typed by hand. Hyperscalers were not read: their H100 offers are 8-GPU instances whose list prices vary by region.
- OPEN QUESTION Q2 (owner: AbdelStark, resolve by: 2027-03-31 or an RFC for v0.2): when to add a second GPU profile (multi-GPU or a newer GPU). Default until resolved: only `prover-h100` and `verifier-cpu`.
- OPEN QUESTION Q3 (owner: AbdelStark, resolve by: 2027-01-31): which exact NVIDIA driver version is pinned for v0.1? Default until resolved: the newest driver that supports both CUDA 13.2 Update 2 (FlashProve) and CUDA 12.9 (SASH) containers, chosen in the reference file pull request.

## References

- docs/PRD.md §4 (G2, G3), §7 (F5), §11.
- AGENTS.md rule 7.
- [RFC-0004](0004-metrics-timing-grades.md) for cost formulas; [RFC-0005](0005-adapter-contract.md) for container invocation; [RFC-0007](0007-evidence-tiers-and-reproduction.md) for reproduction on another provider; [RFC-0011](0011-measurement-and-sampling.md) for the GPU busy check and sampling; [RFC-0012](0012-schemas-and-serialization.md) for `reference/1` and `manifest/1`; [RFC-0013](0013-validation-and-ci.md) for the identifiers scan.
- Linux sysfs CPU topology and cgroup v2 documentation (kernel.org, `Documentation/admin-guide/cgroup-v2.rst`).
