# GPU run

How a person runs measured jobs on a `prover-h100` host: what the host needs, the GPU-host tests to pass before every campaign, and the campaign itself. GPU jobs are not CI gates ([RFC-0013 §What runs on GPU hosts instead](../../rfcs/0013-validation-and-ci.md#what-runs-on-gpu-hosts-instead)); their records enter the repository by pull request, where the gates check them. Per-adapter steps live in each adapter's README ([`systems/README.md`](../../systems/README.md)).

## Host prerequisites

The minimum versions come from the release's reference file, for example [`reference/v0.1.yaml`](../../reference/v0.1.yaml) (`kernel_min`, `container_runtime`, `driver`):

| Item | Requirement | Check |
|---|---|---|
| Linux kernel | at least 5.19 | `uname -r` |
| cgroup | v2, unified hierarchy at `/sys/fs/cgroup` | `stat -fc %T /sys/fs/cgroup` prints `cgroup2fs` |
| Docker Engine | at least 25.0, `cgroup_driver: systemd` | `docker info --format '{{.CgroupDriver}} {{.CgroupVersion}}'` prints `systemd 2` |
| NVIDIA Container Toolkit | at least 1.17 | `nvidia-ctk --version` |
| NVIDIA driver | the `driver` field of `reference/<release>.yaml` (unpinned until issue #77) | `nvidia-smi --query-gpu=driver_version --format=csv,noheader` |
| Harness | a checkout at the release's harness commit, `uv sync --frozen --extra gpu --extra fetch` | `uv run iproofs --version` |

`iproofs run` checks the same items (conformance, exit 3) before any timed step; the table is for setting a host up, not a substitute for that check. Gated model licences are accepted with the runner's own account, and `HF_TOKEN` comes from the environment only (see below).

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

## Prompt corpus cache (RFC-0014 §Corpus fetch)

The first job, or `iproofs prompts build`, downloads each text of `workloads/prompts/corpus.yaml` into `$IPROOFS_CACHE/corpus/<sha256>`. A download whose sha256 differs from the listing, or a cached file that changed, fails with `integrity`; nothing unverified is kept. Prompts are built only from the verified cache, after NFC, LF and BOM normalisation. Fetches retry three times, outside every timed scope.

## GPU-host tests

Run every test below on the host before each campaign, in this order, and record each outcome in the campaign log (next section). A test that fails stops the campaign until it passes; a failure is recorded with its exit code and last lines (AGENTS.md rule 5), never retried away. The tests in [`harness/tests/gpu/`](../../harness/tests/gpu/) skip without NVML, so CI and laptops report skips only.

Set once per shell, after building the fake image (see the self-test above):

```sh
export IPROOFS_GPU=0                                 # the bound GPU index
export IPROOFS_PROBE_IMAGE=<image ID of systems/fake>  # sha256:...
export IPROOFS_CUDA_PROBE_IMAGE=<image>@sha256:<digest>  # any pinned image with python3 and torch
```

| Test | Procedure | Pass criterion |
|---|---|---|
| GH-SELFTEST ([RFC-0011](../../rfcs/0011-measurement-and-sampling.md#testing-strategy)) | `sudo .venv/bin/iproofs machine-record --selftest --gpu $IPROOFS_GPU --probe-image $IPROOFS_PROBE_IMAGE > selftest.json` | exit 0; every check `pass` on stderr; `results/.selftest.json` written |
| GH-MR-H100 ([RFC-0006](../../rfcs/0006-reference-hardware-and-cost.md#testing-strategy)) | GH-SELFTEST, then `sudo -E .venv/bin/python -m pytest harness/tests/gpu/test_numa_binding.py` | GH-SELFTEST passes; both tests pass (the record validates against `manifest/1` `$defs/machine` and names an H100) |
| NUMA binding (docs/spec/07) | part of GH-MR-H100's `test_numa_binding.py` | the prover cpuset lies on the GPU's NUMA node, on distinct physical cores, apart from the verifier sets |
| Sampler rate (docs/spec/07) | `uv run pytest harness/tests/gpu/test_nvml_sampler.py -k rate` | at least 10 Hz over 60 s; gaps above 150 ms on at most 5 % of the call; ST-JITTER passes |
| GH-NVML-PEAK | `uv run pytest harness/tests/gpu/test_nvml_sampler.py -k peak` | `memory_peak_mib` at least 40,960 while a CUDA probe holds 40 GiB for 2 s |
| Cgroup reader (docs/spec/07) | `sudo -E .venv/bin/python -m pytest harness/tests/gpu/test_cgroup_reader.py -k known` | ST-CGROUP passes: `memory.peak` and the sampled `anon` both at least 256 MiB |
| GH-CGROUP-EXACT | `sudo -E .venv/bin/python -m pytest harness/tests/gpu/test_cgroup_reader.py -k exact` | the slice's `memory.peak` at least 1 GiB after a probe that touches 1 GiB and exits at once |
| GH-OVERHEAD ([RFC-0011](../../rfcs/0011-measurement-and-sampling.md#measurement-overhead-budget), docs/spec/08 B-OVH-*) | `IPROOFS_GH_OVERHEAD=1 uv run pytest harness/tests/gpu/test_nvml_sampler.py -k overhead` (30 minutes) | sampler and release watcher CPU at most 1 % of one CPU; p99 lateness at most 10 ms; resident memory at most 256 MiB |
| Fake run | `sudo -E .venv/bin/iproofs run --system fake --workload fake-tiny-ci --profile prover-h100 --image $IPROOFS_PROBE_IMAGE --control-suite` | exit 0; the run directory passes `uv run iproofs validate <run dir>` |
| Adapter smoke job | per adapter, its README's shortest job on the smallest workload, with `--control-suite` | exit 0 and a valid run directory; every control's outcome matches its expected verdict |
| GH-REF-SERVE-L31 ([RFC-0015](../../rfcs/0015-reference-rows.md#testing-strategy)) | `sudo -E .venv/bin/iproofs run --system ref-serve --workload sash-l31-8b-c1024 --profile prover-h100 --repetitions 3` | three repetitions, schema-valid, `rate_prove.steady` non-null |
| GH-REF-RECOMPUTE-L31 | `sudo -E .venv/bin/iproofs run --system ref-recompute --workload sash-l31-8b-c1024 --profile prover-h100 --prompts-from <a completed SASH run dir>` | completed; the agreement block is present |
| GH-REF-MAVERICK-ATTEMPT | `sudo -E .venv/bin/iproofs run --system ref-serve --workload fp-maverick-w1024-b1 --profile prover-h100` | either a valid row, or a recorded failure (`resource` or `adapter`) that leads to NM-1 |

GH-OVERHEAD runs the sampler at 20 Hz and the release watcher in the test process for 30 minutes and measures that process; the container's own work is outside the harness process, so the figure bounds the harness's share of one call. The reference-row tests need the reference systems and the adapter tests need the adapters (issues #65, #69, #138, #139); until those exist, the campaign log records them as not run, with the reason.

## Campaign procedure

1. Check the host prerequisites and fetch the models (`iproofs fetch-model WORKLOAD`) for every workload of the campaign.
   Then, once per workload per release and system, prepare the C3 and P1 perturbed commitment: `sudo -E .venv/bin/iproofs controls --prepare-perturbed WORKLOAD --system S --profile prover-h100`. It writes `results/<release>/<system>/_controls/<workload>/` (commit to the results pull request) and keeps the perturbed weights in `$IPROOFS_CACHE/perturbed/` on this host only.
2. Run the GPU-host tests above, in order. Start the campaign log.
3. Project the GPU time with `uv run iproofs release plan RELEASE` ([docs/spec/08](../spec/08-performance-budget.md#run-campaign-compute-budget)) and check it fits the sponsored budget.
4. Run the matrix: per configuration, `sudo -E .venv/bin/iproofs run --system S --workload W --profile prover-h100 --repetitions N --control-suite` with N at least 3 (RFC-0004). A failed job (exit 4) is kept as recorded; rerun only as new repetitions, never by deleting the failed one.
5. Validate the whole tree: `uv run iproofs validate results/`.
6. Open the results pull request: one pull request per campaign, holding the new run directories under `results/` and nothing else. Its description is the campaign log.

The campaign log is a checklist in the results pull request description:

```
Release: v0.1   Harness commit: <full hash>   Host: prover-h100 (provider <name>)
| Test | Date (UTC) | Outcome | Evidence |
| GH-SELFTEST | 2026-11-20 | pass | results/.selftest.json copied into every manifest |
| GH-OVERHEAD | 2026-11-20 | fail, exit 1 | <last lines of the pytest output> |
| GH-REF-MAVERICK-ATTEMPT | | not run | needs issue #139 |
```

It holds no host name, IP address, account name or token (AGENTS.md rule 7); the machine record in each manifest is the host's only description.
