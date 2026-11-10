# H200 host

How a person brings up a bare-metal NVIDIA H200 node for the v0.1 reference profile `prover-h200` ([RFC-0006 §H200 profiles](../../rfcs/0006-reference-hardware-and-cost.md#h200-profiles)) in docker mode, and makes the first runs on it. The v0.1 node is on Lucid Computing's research cluster, where the official runs are made. Development runs before then go to Hugging Face Jobs on `prover-h200-hosted` ([`hf-jobs.md`](hf-jobs.md)); they never enter `results/`. This page covers the first day: what to ask the provider for, the host probe, the self-test, the images, the weights and the first two runs. The GPU-host tests and the campaign itself are in [`gpu-run.md`](gpu-run.md); per-adapter details are in [`systems/sash/README.md`](../../systems/sash/README.md) and [`systems/flashprove/README.md`](../../systems/flashprove/README.md).

## What to ask the provider for

Each item comes from `prover-h200` in [`reference/v0.1.yaml`](../../reference/v0.1.yaml), from a v0.1 system's documented needs, or from how the harness binds a job. The host probe (step 1) checks every item it can read.

| Item | Need | Why |
|---|---|---|
| Access | root (`sudo`) on the node | the harness runs docker, starts transient systemd scopes and reads their cgroup counters ([gpu-run.md §systemd and cgroup v2](gpu-run.md#systemd-and-cgroup-v2-rfc-0011-cgroup-accounting)) |
| OS | Ubuntu 24.04, kernel 5.19 or later | `os`, `kernel_min`; 5.19 gives `memory.peak` |
| cgroup and init | cgroup v2 unified hierarchy, systemd as init | the per-step slices (RFC-0011) |
| Docker | Docker Engine 25.0 or later with the systemd cgroup driver | `container_runtime`; the adapters run as `docker run` (RFC-0005) |
| NVIDIA Container Toolkit | 1.17 or later, configured for docker (`nvidia-ctk runtime configure --runtime=docker`) | `--gpus device=<index>` |
| GPU | one H200 SXM 141 GB for the campaign's duration, with no other process on it | `gpu`; a process on the bound GPU fails the job (PC-GPU-BUSY) |
| Confidential Computing | CC mode off on that GPU for every prover run, and left off for the campaign | §H200 profiles; CC is enabled on the cluster (Q4) |
| CPUs | at least 24 logical CPUs on the GPU's NUMA node, at least 32 in all, not used by other jobs | `cpu`; the prover cpuset lies on the GPU's node (§CPU and memory selection) |
| Memory | at least 330 GiB available | `host_memory_gib_min`; FlashProve's `run.sh` does not start `commit` below 330 GB available (external, reported, FlashProve README §Machine needs) |
| Disk | local NVMe with at least 500 GiB free for the work directory: results, `IPROOFS_CACHE` and docker's data root | `disk`; see the disk note below |
| Driver | the installed driver, unchanged during the campaign, reporting CUDA 13.2 or later | R3 and Q3: the pin is read from this host; FlashProve's image is CUDA 13.2 Update 2 |
| Network | outbound HTTPS to github.com, ghcr.io, huggingface.co and the Python package index | clone, image pull, weights, `uv sync` |
| Kernel calls | no sandbox between the job and the kernel | FlashProve's `cp_commit` and `cp_prove` stop at their start without `madvise(MADV_WIPEONFORK)` and without the CPU's SHA extensions (FlashProve README §Machine needs; gVisor refused the call, #68) |

Exclusive use of the whole node during measured runs is better than one GPU: other tenants' jobs share the memory bandwidth, the PCIe links and the CPUs of the GPU's NUMA node, and the samplers cannot see them.

Disk note: FlashProve's weights are 232.1 GB of files, and `commit` needs 10 GB and `prove` 1 GB more (external, reported, FlashProve README §Machine needs). The adapter clones the five weight files into the job's io directory with FICLONE, or copies them where the file system cannot clone (FlashProve README §What `commit` needs). On ext4 each FlashProve job therefore holds a second full copy of the weights beside the cache. Ask whether the work directory can be XFS with `reflink=1` or btrfs; otherwise budget the copy, and keep one FlashProve job at a time.

## 1. Probe the host

On the node, before installing anything, from a checkout of this repository:

```sh
export WORK=<a directory on the local NVMe>
git clone https://github.com/ai-verification-observatory/inference-proofs "$WORK/inference-proofs"
cd "$WORK/inference-proofs"
sudo python3 docs/runbooks/host-probe.py --work "$WORK" > "$WORK/probe.json"
```

[`host-probe.py`](host-probe.py) needs Python 3 only. It prints one JSON object on stdout and one line per requirement on stderr (`PASS`, `FAIL`, `UNKNOWN`, `RECORD` for the unpinned driver, `LOGIN` for an image that needs `docker login`, `INFO` for the suggested GPU, `N/A` for a row that does not apply). Rows marked `[flashprove]` are FlashProve's own needs (CUDA 13.2, SHA extensions, `madvise(MADV_WIPEONFORK)`, 330 GB to commit); the others are `prover-h200`'s. `failed` lists the profile's failures and `failed_flashprove` FlashProve's; the probe exits 1 only when `failed` is not empty. Run it as root so it can read docker. It reads the GPUs, CC mode, CPU and NUMA layout, memory, the work directory's free space and device kind, OS, kernel, cgroup, systemd, docker, the toolkit, `madvise(MADV_WIPEONFORK)`, and whether ghcr.io grants an anonymous pull of each pinned image. It prints no host name, address, serial, user name or path.

- Any `FAIL`, in either list, stops the day: send the failing rows to the provider. Do not work around a failure with a flag (AGENTS.md rule 4).
- `cc_mode_off` must pass. `UNKNOWN` means `nvidia-smi conf-compute` did not answer; ask the provider for the GPU's CC mode and do not run a campaign job until it is known off (RFC-0006 Q4).
- `suggested_gpu_index` is the idle H200 with the most CPUs on its NUMA node. Use it as `--gpu` below.
- `driver` is `RECORD`: write the value down for the pin (step 3).

`probe.json` stays on the node. Its `requirements` block goes into the campaign log (step 6).

## 2. Install the harness

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh     # if uv is missing
export UV_CACHE_DIR="$WORK/uv-cache" IPROOFS_CACHE="$WORK/cache"
uv sync --frozen --extra gpu --extra fetch --extra prompts   # NVML, fetch-model, tokenizers
uv run iproofs --version
```

Check out the harness commit the campaign uses, and keep it for the whole campaign. Put docker's data root on the NVMe too (`docker info --format '{{.DockerRootDir}}'`; the probe reports its free space as `docker_root`).

## 3. Self-test and the driver pin

```sh
IMG=$(docker build -q --build-arg IPROOFS_FAKE_UPSTREAM=64168df9fd0706dfd955b6795fa6f535872dff78 \
      -f systems/fake/Dockerfile systems)            # the commit in systems/fake/system.yaml
export GPU=<suggested_gpu_index>
sudo -E .venv/bin/iproofs machine-record --selftest --gpu "$GPU" --probe-image "$IMG" \
     --provider "Lucid Computing" > "$WORK/selftest.json"
```

The self-test (RFC-0011, GH-SELFTEST in [gpu-run.md](gpu-run.md#gpu-host-tests)) saves its result in `results/.selftest.json`, which every later run copies into its manifest. Until `prover-h200` pins a driver, every H200 host fails PC-DRIVER; the self-test itself still has to pass.

The driver pin (RFC-0006 Q3): the record's `gpu.driver_version` and `gpu.cuda_driver_api` are this host's values. A pull request writes the driver into `reference/v0.1.yaml` `profiles.prover-h200.driver` (and updates `PROFILE["driver"]` in `host-probe.py`, which a test holds equal to the reference file). Runs made before that pull request merges are development runs (step 6).

## 4. Pull the pinned images

The images are `<repository>@<digest>` in each `systems/<name>/system.yaml`. On 2026-11-08 ghcr.io refused an anonymous pull token for `ai-verification-observatory/sash` and `ai-verification-observatory/flashprove`, so they are not public; the probe's `pull_*` rows say whether that is still so. Either a maintainer makes the packages public, or the operator logs in with a GitHub token of their own account that has `read:packages`:

```sh
echo "$GHCR_TOKEN" | docker login ghcr.io -u <github user> --password-stdin   # only if needed
for s in sash flashprove ref-serve ref-recompute; do
  repo=$(sed -n 's/^ *repository: *"\{0,1\}\([^"]*\)"\{0,1\}$/\1/p' systems/$s/system.yaml)
  digest=$(sed -n 's/^ *digest: *"\{0,1\}\(sha256:[0-9a-f]*\)"\{0,1\}$/\1/p' systems/$s/system.yaml)
  docker pull "$repo@$digest"
done
docker logout ghcr.io
```

Log out afterwards: no credential stays on a shared node, and the token never goes into a file in the checkout.

## 5. Fetch the weights

```sh
uv run iproofs fetch-model sash-l31-8b-c1024
uv run iproofs fetch-model fp-maverick-w1024-b1      # b24 uses the same files and model digest
```

Both repositories are ungated (`licence.gated: false` in the workload files), so `HF_TOKEN` is not needed for them. `fetch-model` downloads the workload's file list at its pinned revision into `$IPROOFS_CACHE/models/<model digest>/`, checks every sha256 and the model digest, and makes the directory read-only (RFC-0014). SASH's model is four safetensors files and the tokenizer (sizes in `workloads/sash-l31-8b-c1024.yaml`, field `bytes`); FlashProve's is five GGUF files, 232.1 GB in all (external, reported, FlashProve README).

## 6. The first runs, in order

Until the driver pin merges, every run on this host records `harness.nonconforming: true` in its manifest (`--allow-nonconforming` is accepted and changes nothing). Keep development runs outside the checkout, with their own self-test:

```sh
export DEV="$WORK/dev-results"
sudo -E .venv/bin/iproofs machine-record --selftest --gpu "$GPU" --probe-image "$IMG" \
     --provider "Lucid Computing" --results "$DEV" > /dev/null
```

1. **SASH, `sash-l31-8b-c1024`, one repetition.**

   ```sh
   sudo -E .venv/bin/iproofs run --system sash --workload sash-l31-8b-c1024 --profile prover-h200 \
        --gpu "$GPU" --provider "Lucid Computing" --repetitions 1 --allow-nonconforming --results "$DEV"
   ```

   Expect hours. Upstream states no time for the 1,024 + 64 shape (SASH README §Expected run times). On an H100 container (`prover-h100-hosted`), one job of this workload recorded `commit` 6,370 s and `prove` 5,728 s between its step events and then failed at the `verify` limit of that day, 3,600 s (measured, tier reported, n = 1, `results/v0.1/sash/2026-11-05-sash-sash-l31-8b-c1024-prover-h100-hosted-1`). On an H100, `boundary-grid --verify` of one grid of this workload took 3,381 s at about 3.9 CPUs (a development call, n = 1, not a recorded run; `systems/sash/system.yaml`), and the harness also times `verify` on one CPU (`verify.single_thread`); the `verify` limit is 21,600 s. Issue #142 estimates about 7 h for a self-tested job on the H100; no H200 figure exists yet. `prove` also builds the CUDA kernels for the plan's shapes with the card visible (SASH README §Backend).

2. **FlashProve, `fp-maverick-w1024-b1`, one repetition.**

   ```sh
   sudo -E .venv/bin/iproofs run --system flashprove --workload fp-maverick-w1024-b1 --profile prover-h200 \
        --gpu "$GPU" --provider "Lucid Computing" --repetitions 1 --allow-nonconforming --results "$DEV"
   ```

   Before `cp_commit`, the adapter sums the weights ("5 to 6 minutes" upstream) and fits the scales on the GPU (127 s upstream); committing takes about 39 minutes upstream (all external, reported, one H100, FlashProve README). On an H100 container (`prover-h100-hosted`), three b1 jobs gave `prove.session` from 318.3 to 376.7 s (measured, tier reported, n = 3; pull request #297). `commit` needs 330 GB available; peak host memory while committing was 299.6 GB upstream (external, reported).

   RISK (RFC-0006 §H200 profiles): the adapter compares `KL.bin`, fitted in float32 on the GPU, with upstream's digest, and upstream writes that "its rounding can differ between GPU models, drivers and torch's CUDA libraries". If the job stops there on the H200, it is a failed run: keep its exit code and last lines, open an issue, and change neither the adapter nor the prover (AGENTS.md rules 1 and 5).

3. **The campaign**, once the driver pin has merged: run the GPU-host tests and the campaign procedure of [gpu-run.md](gpu-run.md), with `--profile prover-h200 --gpu "$GPU" --provider "Lucid Computing"` and the default `--results results`. Rerun the self-test into `results/` first. For planning, on the H100 container one b24 job gave `commit` 1,996.6 s and `prove.session` 1,200.2 s (measured, tier reported, n = 1; pull request #297).

Before each campaign, rerun the probe and copy its `requirements` block, with `cc_mode_off`, into the campaign log; the machine record holds no CC field (RFC-0006 Q4).

## Where run directories go

| Run | `--results` | Enters the repository |
|---|---|---|
| development (before the driver pin, or any run on a host that fails a check) | `$WORK/dev-results`, outside the checkout | only by a results pull request that names it |
| campaign (conforming, self-tested) | `results` (default), from the checkout's root | yes, by one results pull request per campaign ([gpu-run.md §Campaign procedure](gpu-run.md#campaign-procedure)) |

`results/` is append-only (RFC-0009, APP-1): a run directory is never edited or deleted once merged, and a failed repetition stays recorded, with its exit code and last lines (AGENTS.md rule 5). Proof bytes stay out of git: `--keep-io` directories are ignored.

## What never to commit or post

- No host name, IP address, MAC address, cluster, partition or queue name, job or allocation ID, account or user name, SSH alias or absolute home path (AGENTS.md rule 7; RFC-0006 §Machine record lists the excluded identifiers). The machine record in each manifest is the host's only description, and `--provider "Lucid Computing"` is the declared provider.
- No token: `HF_TOKEN` and the ghcr.io token come from the environment, are never written to a file, and are never passed into a container.
- Before pasting the probe or self-test output into a pull request or issue, read it, and run `uv run iproofs validate` on the tree: gate G9 rejects identifiers it recognises (RFC-0013).
- No weights, no proof bytes, no development run directories.
