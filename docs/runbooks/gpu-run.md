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

## The calibration self-test (RFC-0011)

Run it on the host before its first run of a release and before each run campaign, after any driver, kernel or Docker change, and whenever a run fails with `environment`:

```sh
docker build -q --build-arg IPROOFS_FAKE_UPSTREAM=<commit in systems/fake/system.yaml> -f systems/fake/Dockerfile systems
sudo .venv/bin/iproofs machine-record --selftest --gpu 0 --probe-image <the image ID printed above>
```

It runs ST-CLOCK, ST-NVML, ST-SAMPLER and ST-JITTER (5 s on the bound GPU), and ST-CGROUP, ST-WATCH and ST-OOM with the fake image's `probe` subcommand under a harness slice. It prints the machine record and the result as JSON, saves the result in `results/.selftest.json`, and exits 3 naming every failed check. Runs copy the saved result into their manifests; a run without a passing self-test from the same harness version is not eligible for a release.

## Model weights and `HF_TOKEN` (RFC-0014 §Model fetch and verification)

- Fetch once per host with `uv sync --frozen --extra fetch`, then `uv run iproofs fetch-model <workload>`. Weights go to `$IPROOFS_CACHE/models/<model digest>/` (`IPROOFS_CACHE` defaults to `~/.cache/iproofs`). The command downloads exactly the workload's file list at its pinned revision, checks every file's sha256 and the model digest, and makes the directory read-only.
- Gated models: accept the model licence with your own account, then export `HF_TOKEN` in the shell that runs the harness. The token is read from the environment only and passed to the download call only; it is never written to a file, a log or a record, and never passed into a container.
- Every job rehashes the cached files before it starts, outside every timed scope, and logs the time as `integrity.model_rehash`. A file that changed on disk fails the job with `integrity` and moves the entry to `$IPROOFS_CACHE/quarantine/`; investigate before fetching again.
- The weights are mounted read-only at `/models` for `commit` and `prove`, and never for `verify`.
