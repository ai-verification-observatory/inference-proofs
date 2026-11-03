# GPU run

How a prover-h100 host runs measured jobs. This page grows with the GPU work (#117); today it holds the host prerequisites the measurement code relies on.

## Host prerequisites

### NVML (RFC-0011 §GPU sampler)

- The NVIDIA driver, and the harness installed with its `[gpu]` extra, which brings `nvidia-ml-py`: `uv sync --frozen --extra gpu`. Without it, a GPU profile fails with kind `environment`; null readers are only for profiles without a GPU.
- No other compute process on the bound GPU: one found before `info` or a GPU step fails the job (PC-GPU-BUSY); one found after a GPU step marks that step's GPU metrics `degraded: true` and logs `gpu.foreign_process`.

### systemd and cgroup v2 (RFC-0011 §Cgroup accounting)

- cgroup v2 only (the unified hierarchy at `/sys/fs/cgroup`), with Docker's `cgroup_driver: systemd` (`docker info --format '{{.CgroupDriver}} {{.CgroupVersion}}'` prints `systemd 2`).
- A kernel of 5.19 or later, so every slice has `memory.peak` (G-7). Without it the job fails conformance before any timed step.
- `systemd-run` and `systemctl` on the path. For each step the harness runs a placeholder scope, `systemd-run --scope --slice=iproofs-<job_hash>-<step>.slice --unit=iproofs-<job_hash>-<step>-hold sleep infinity`, creates the container with `--cgroup-parent` set to that slice, and stops the scope after reading the counters (G-1 to G-4).
- The harness runs as root, or as a user allowed to start transient scopes and read the slice's `memory.peak`, `memory.stat`, `cpu.stat` and `memory.events`.
- Scopes named `iproofs-*-hold.scope` left by a crashed runner are stopped before conformance and logged as `cgroup.stale_cleanup`.
