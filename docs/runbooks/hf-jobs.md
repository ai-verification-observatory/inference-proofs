# Hugging Face Jobs

How the owner makes development runs of SASH (`sash-l31-8b-c1024`) and FlashProve (`fp-maverick-w1024-b1`, then `fp-maverick-w1024-b24`) on Hugging Face Jobs H200 containers, on the profile `prover-h200-hosted` ([RFC-0006 §H200 profiles](../../rfcs/0006-reference-hardware-and-cost.md#h200-profiles), [§Hosted execution](../../rfcs/0006-reference-hardware-and-cost.md#hosted-execution)), within a budget of 200 EUR, in stages. Official runs come later, on the bare-metal H200 node ([`h200-host.md`](h200-host.md)). Every run here is a development run: it stays out of `results/` (see [Where results live](#where-results-live)).

Hugging Face Jobs starts one container from a named image, with no docker engine inside, and bills it per minute while it is starting or running ([jobs-pricing](https://huggingface.co/docs/hub/jobs-pricing), read 2026-11-08). The harness's hosted mode (`iproofs run --hosted --gpu <index>`) is made for this. Each job runs [`hf-job.sh`](hf-job.sh) from a fresh clone of this repository at a pinned commit: host probe, harness install, binding check, hosted self-test, weights, runs, and a copy of everything it wrote to a private storage bucket mounted in the job.

## Flavors and who runs where

Provider list prices and sizes from `hf jobs hardware` and [jobs-configuration](https://huggingface.co/docs/hub/jobs-configuration) (read 2026-11-08; the provider's price, not this benchmark's cost basis, which is `costs.h200`, RFC-0006 C7):

| Flavor | GPUs | vCPU | RAM | Disk | USD per hour | USD per minute | Used for |
|---|---|---|---|---|---|---|---|
| `cpu-basic` | none | 2 | 16 GB | 50 GB | 0.01 | 0.0002 | stage 1a checks |
| `cpu-xl` | none | 16 | 124 GB | 1,000 GB | 1.00 | 0.0167 | stage 1a, if an image does not fit in 50 GB |
| `h200` | 1x H200 141 GB | 23 | 256 GB | 3,000 GB | 5.00 | 0.0833 | the SASH probe, SASH |
| `h200x2` | 2x H200, 282 GB | 46 | 512 GB | 6,000 GB | 10.00 | 0.1667 | the FlashProve probe, FlashProve |

- SASH runs on `h200`: the flavor meets `prover-h200-hosted` (15 prover CPUs plus 8 verifier CPUs = 23; 200 GiB is below its 256 GB). SASH's host memory need is not stated upstream; if a job exceeds the container's limit it fails with kind `resource`, and that failure is recorded and uploaded like any other.
- FlashProve runs on `h200x2`: upstream's `run.sh` does not start `commit` below 330 GB available, and committing peaked at 299.6 GB (external, reported, [`systems/flashprove/README.md`](../../systems/flashprove/README.md) §Machine needs). 256 GB is below both. The job binds one GPU (`--gpu`, the probe's suggestion) and the second stays idle; it is billed by the provider and not counted in the benchmark's cost (RFC-0006 R1, C5). Its probe runs on `h200x2` too, since the facts that decide whether FlashProve can run (the memory limit, which NUMA node each GPU sits on and how many CPUs the container may use there) belong to that flavor.
- On this profile a job binds 15 prover CPUs, not the 24 of `prover-h200`, and FlashProve's timed runs upstream bound 24 (FlashProve README §CPU binding). These rows are their own configuration and are never compared with bare-metal rows as one set.

## Budget

200 EUR is 223.30 USD at the ECB reference rate of 2026-11-06, 1 EUR = 1.1165 USD ([eurofxref-daily.xml](https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml), read 2026-11-08). Jobs bill in USD, and a card payment may add a conversion fee, so this plan spends against **200 USD**; the 23.30 USD between the two is a margin, not a stage.

Every job has a `--timeout`. A job's **cap** here is its timeout times its flavor's hourly price. That the cap bounds the bill is an assumption: the provider bills the starting phase (the image pull) as well as the running one ([jobs-pricing](https://huggingface.co/docs/hub/jobs-pricing)), and its documentation does not say whether the timeout counts the starting phase. If it does not, a job can cost up to one pull's length more than its cap; at an assumed pull of at most 10 minutes that is 0.83 USD on `h200` and 1.67 USD on `h200x2`, at most 9.17 USD over the seven GPU jobs below, within the 23.30 USD margin. If it does, the deadline comes earlier than the job script believes, so the job command gives the script its timeout less 600 s (`IPROOFS_JOB_BUDGET_S`), and the script keeps a further 900 s for the upload. Stage 1a and stage 1 measure the pull; the stop rule counts what was billed, not the caps.

The plan below fits within 200 USD even if every job up to stage 4.2 runs to its cap. The expected costs are estimates from the H100 records and upstream figures named in each stage, with the assumptions stated; no H200 run of either system exists yet, so none of them is a measured duration.

## Before stage 0: the images must be pullable

Jobs pulls only public images, or images built by a Docker Space ([jobs-images](https://huggingface.co/docs/hub/jobs-images), read 2026-11-08). On 2026-11-08 ghcr.io refused an anonymous pull token for both pinned images, `ghcr.io/ai-verification-observatory/sash` and `ghcr.io/ai-verification-observatory/flashprove` (`{"errors":[{"code":"UNAUTHORIZED","message":"authentication required"}]}`), while it granted one for a public package (`astral-sh/uv`). So the packages are private, or do not exist under those names. Check again, from any machine:

```sh
for r in sash flashprove; do
  printf '%s: ' "$r"
  curl -s "https://ghcr.io/token?scope=repository:ai-verification-observatory/$r:pull" | head -c 60; echo
done   # {"token":... means public; {"errors":... means private or missing
```

What the owner does, once, before stage 1a:

1. As an owner of the GitHub organisation, open each package (organisation page, Packages, `sash` and `flashprove`), Package settings, Danger Zone, Change visibility, Public. GitHub's documentation warns that a package made public cannot be made private again. The images hold the adapters and the upstream sources at their pinned commits and toolchains, no weights and no secrets (RFC-0014; `systems/*/Dockerfile`).
2. Rerun the check above: both lines must start with `{"token"`.

If the packages stay private, the only route Jobs documents is a Docker Space that builds the image. A Space builds from `systems/<name>/Dockerfile` again, so the image has another digest: its runs are local builds (`--image`), never eligible for a release (RFC-0014), and `hf-job.sh` would need that change. Making the packages public keeps the pinned digests.

## Stage 0: the hf CLI and the bucket (owner, interactive, no cost)

```sh
uv tool install --upgrade huggingface_hub    # or: pip install -U huggingface_hub; this page was checked with hf 2.4.0
hf version
hf auth login                                 # paste a token that may start and manage Jobs
hf auth whoami
hf jobs hardware                              # check the cpu-basic, h200 and h200x2 rows and prices again
hf buckets create <namespace>/iproofs-dev-runs --private
```

Jobs needs a positive credit balance on the account that runs them ([jobs-pricing](https://huggingface.co/docs/hub/jobs-pricing)); add the 200 EUR at [huggingface.co/settings/billing](https://huggingface.co/settings/billing).

Results leave each job through a private [storage bucket](https://huggingface.co/docs/hub/storage-buckets) mounted in the container (`-v hf://buckets/<namespace>/iproofs-dev-runs:/upload`; buckets mount read-write, [jobs-configuration §Volumes](https://huggingface.co/docs/hub/jobs-configuration#volumes)). `hf-job.sh` copies its output there. No token enters the container: the job runs on the owner's login, which owns the bucket. Buckets are billed by the amount stored above a free allowance ([hf.co/storage](https://huggingface.co/storage)); a job leaves megabytes to a few hundred megabytes there (an assumption: logs, the records, and one proof archive per configuration, about 19 MB for FlashProve by upstream's average proof size).

**Fallback, only if stage 1a shows the mounted bucket is not writable** by the job's user: a private dataset and a narrow token. Create the dataset first with your own login, since a token scoped to one repository cannot create it, then make a fine-grained token with write access to that dataset only, and paste it at a silent prompt so it never appears on a command line or in the shell history:

```sh
hf repos create <namespace>/iproofs-dev-runs-ds --type dataset --private
mkdir -p ~/.config/iproofs && chmod 700 ~/.config/iproofs
( umask 077; read -rs T && printf 'HF_TOKEN=%s\n' "$T" > ~/.config/iproofs/hf-job.secrets; unset T )
```

Jobs passes it to the container as an encrypted secret (`--secrets-file`). `hf-job.sh` uses it for the upload only; the harness, the adapter and `fetch-model` run without it (both models are ungated), and the hosted runner drops any name containing `TOKEN` from the adapter's environment. That keeps the token from the adapter only when the job runs as root, because the hosted runner then drops the adapter to uid 10001. If the job runs as the images' own user 10001 (stage 1a shows it), the adapter and the upstream prover run under the same uid as the job script and can read the token from `/proc/1/environ` (RFC-0006 Q6). The token's scope, write access to that one dataset, is then all that limits it.

## The job command

Set once per shell. `IPROOFS_COMMIT` is the full hash of a commit on `main` that contains `docs/runbooks/hf-job.sh` (the merge of this change, or later); every job of a campaign uses the same one.

```sh
export IPROOFS_COMMIT=<full 40-character commit hash>
NS=<namespace>
SASH_IMAGE=ghcr.io/ai-verification-observatory/sash@sha256:bf548d5666b10d653babb23612d670dfa7c86f7b75f3784da0451d53ec90f577
FP_IMAGE=ghcr.io/ai-verification-observatory/flashprove@sha256:7ca6c9ee8c6568b9b925a5c8a8d8eb2f3cd7e394b0f047cde3096d99145a91f8
UPLOAD=(-v "hf://buckets/$NS/iproofs-dev-runs:/upload" -e IPROOFS_UPLOAD_DIR=/upload)
# fallback only: UPLOAD=(--secrets-file ~/.config/iproofs/hf-job.secrets -e IPROOFS_UPLOAD="$NS/iproofs-dev-runs-ds")
BOOT='set -eu; if [ "$(id -u)" = 0 ]; then W=/work; else W=/tmp/iproofs; fi; mkdir -p "$W";
git clone -q https://github.com/ai-verification-observatory/inference-proofs "$W/inference-proofs";
cd "$W/inference-proofs"; git checkout -q "$IPROOFS_COMMIT"; exec bash docs/runbooks/hf-job.sh "$@"'

iproofs_job() {  # FLAVOR TIMEOUT_SECONDS IMAGE LABEL then hf-job.sh's arguments
  local flavor=$1 timeout=$2 image=$3 label=$4; shift 4
  hf jobs run --detach --flavor "$flavor" --timeout "$timeout" --name "iproofs-$label" \
    --label "iproofs=$label" "${UPLOAD[@]}" \
    -e IPROOFS_COMMIT="$IPROOFS_COMMIT" -e IPROOFS_JOB_BUDGET_S="$((timeout - 600))" \
    -e IPROOFS_LABEL="$label" \
    "$image" -- bash -c "$BOOT" hf-job "$@"
}
```

The image digests are those of `systems/sash/system.yaml` and `systems/flashprove/system.yaml`; copy them from there if they have changed. The images' `ENTRYPOINT` is the adapter; Jobs runs the command given after the image instead, as its own example of `hf jobs run vllm/vllm-openai bash -c ...` shows ([jobs-images](https://huggingface.co/docs/hub/jobs-images)); stage 1a checks it. `--detach` prints the job ID; follow a job with `hf jobs logs -f <job id>`, check it with `hf jobs inspect <job id>`, and stop it with `hf jobs cancel <job id>`.

What happens inside, in order (`hf-job.sh`):

1. **Checkout.** Both images have `git`. As root the work directory is `/work`; as the images' own user (uid 10001, RFC-0006 Q6) it is `/tmp/iproofs`, the only place that user can write. The script stops if `HEAD` is not `IPROOFS_COMMIT`. It sets `HOME` and `HF_HOME` under the work directory (that user has no home directory), and logs whether the mounted bucket is writable.
2. **Probe.** `host-probe.py --profile prover-h200-hosted` (standard library only), into `out/probe.json`; the job goes on whatever it finds, so the record is complete. The bound GPU is the probe's `suggested_gpu_index`, or 0.
3. **Harness.** `uv sync --frozen --no-dev --extra gpu --extra fetch --extra prompts` from the checkout's `uv.lock`: NVML, `fetch-model` and `tokenizers`, which every run needs to build the workload's prompts from its `tokenizer.json`. The script then imports all three and stops if one is missing. Both images have Python 3.12.3 (Ubuntu 24.04's `python3`) and `uv` (0.11.18 in SASH's image, by its Dockerfile); FlashProve's also has `pip` 24.0, but Ubuntu's `pip` refuses to install into the system Python (PEP 668), so `uv` is used in both. The harness needs Python 3.12 or 3.13 (`pyproject.toml`).
4. **Binding check.** The CPUs `iproofs run --gpu` would bind on `prover-h200-hosted` (`GpuEnvironment`, RFC-0006 §CPU and memory selection). It fails when the GPU has no NUMA node or fewer than 15 usable CPUs sit on it; `iproofs run` then refuses before any step, and `--allow-nonconforming` does not change that. A `run` job stops here, before any weights are fetched.
5. **Self-test.** `iproofs machine-record --hosted --selftest` (RFC-0011), into `out/selftest.json` and the results directory.
6. **Development install**, only with `IPROOFS_DEV_IMAGE` ([Production serving](#production-serving-from-the-engine-image-rfc-0015-srv-6)): `systems/<system>/dev_install.py` puts the adapter into the engine image the job started from and checks the engine, the environment and the bound GPUs, and the runs pass `--image` and `--keep-io`. A failed install or check stops the job before any weights are fetched.
6. **Weights.** `iproofs fetch-model <workload>`, under the same deadline as the runs: exactly the workload's files at the pinned revision, every sha256 and the model digest checked (RFC-0014), into `$IPROOFS_CACHE` under the work directory. No token is needed.
7. **Runs.** `iproofs run --system S --workload W --profile prover-h200-hosted --hosted --gpu <index> --provider "Hugging Face Jobs" --repetitions N --allow-nonconforming --results out/dev-results [--control-suite]`, under `timeout` so it stops 15 minutes before the script's budget. A run stopped there exits 124 or 137 and never reaches its final write, so its staging directory keeps `io/` (for FlashProve a copy of the weights), the scratch directories and the commitment store (for FlashProve the prover's secret key). The script deletes those before the upload, logging each one's size, and uploads the rest of the staging directory (its logs and `job.lock`). It is reported as a failed run with that exit code (AGENTS.md rule 5).
8. **Upload.** On every exit, `out/` (the job log, probe, self-test, run directories and proof archives) is copied to `runs/<UTC time>-<label>/` in the bucket: the log and the records first, then the run directories, then the log again.

## Stage 1a: the containers without a GPU (under 0.01 USD)

One `cpu-basic` job per image checks what needs no GPU: that Jobs pulls the image by digest, that the command replaces the `ENTRYPOINT`, which uid the job runs as, `HOME`, the free space of `/` and `/tmp`, `git`, `uv`, `python3`, whether the mounted bucket is writable by that uid, and how long the pull takes.

```sh
for img in "$SASH_IMAGE" "$FP_IMAGE"; do
  hf jobs run --detach --flavor cpu-basic --timeout 15m --name iproofs-stage-1a \
    -v "hf://buckets/$NS/iproofs-dev-runs:/upload" "$img" -- \
    bash -c 'date -u; id -u; echo "HOME=$HOME"; df -h / /tmp; git --version; uv --version; python3 -V;
             mkdir -p /upload/stage-1a && touch "/upload/stage-1a/uid-$(id -u)" && echo "upload: writable"'
done
```

Cap 15 min x 0.01 USD/h, under 0.01 USD for both. If a job fails before its first log line with a disk error, the image does not fit in 50 GB: run it again on `cpu-xl` (cap 0.25 USD). Read:

- The pull time: the job's creation time in `hf jobs inspect` against the first `date -u` line of its log. Write it in the spend log. If it is above 10 minutes, raise the 600 s allowance in `iproofs_job` by the difference before stage 1.
- `id -u`: 0 or 10001. If 10001, the work directory is `/tmp/iproofs`, so `/tmp` must have more than 500 GiB free on the GPU flavors (stage 1 reads that); and the fallback token, if it is ever used, is readable by the adapter (stage 0).
- `upload: writable`. Without it, use the fallback of stage 0 and set `UPLOAD` to it.

## Stage 1: probe jobs (expected 3.75 USD, cap 5.00 USD)

One short job per system, on the flavor its runs use, to learn what the containers give before any long job: the GPU's NVML name and memory (PC-GPU-MODEL needs `NVIDIA H200`; the PCIe part reports another name), the driver and CUDA version (for the pin, RFC-0006 Q5), the CC mode, the CPU limit (a quota, a cpuset, or a VM's own CPUs), each GPU's NUMA node and the usable CPUs there, the memory limit, the writable paths and their free space, whether the job runs as root (Q6), `madvise(MADV_WIPEONFORK)` and the SHA extensions (FlashProve), the binding check and the hosted self-test.

```sh
iproofs_job h200   1200 "$SASH_IMAGE" probe-sash       probe
iproofs_job h200x2 1200 "$FP_IMAGE"   probe-flashprove probe
```

Timeout 20 min each: caps 20/60 h x 5.00 USD/h = 1.67 USD and 20/60 h x 10.00 USD/h = 3.33 USD, 5.00 USD for both. Expected 1.25 and 2.50 USD if each job takes 15 min, an assumption: the pull is billed and stage 1a measures it; the probe, `uv sync`, the binding check and the self-test take a few minutes.

Read, in each job's log or `probe.json`:

- Every `FAIL` row without `[flashprove]` (the list `failed`): any one stops the plan; fix the cause (or write it up as an issue) before stage 2. `cpus_on_gpu_numa_node` failing with `no NUMA node`, or `binding check exit` other than 0, blocks every run on that flavor: `iproofs run --gpu` refuses such a GPU. `cc_mode_off` `UNKNOWN` means the container cannot read the CC mode; note it.
- In the FlashProve probe, `failed_flashprove` must be empty on `h200x2`: `flashprove_commit_floor_gb` must pass there. `madvise_wipeonfork`, `sha_ni` or `cuda_driver_api_flashprove` failing means FlashProve cannot run on Jobs: skip stages 3, 4.1 and 4.3 and spend on SASH only. Note `suggested_gpu_index`: the job binds it.
- `work_disk_free_gib` and `work_disk_writable`: FlashProve needs about 245 GB plus a copy of the 232.1 GB of weights per job (FlashProve README §Machine needs, §What `commit` needs). If the work directory has less than 500 GiB, stop and fix `BOOT` before stage 3.
- `system.home_writable`, `system.root`: what stage 1a showed, now on the GPU flavor.
- `driver` (`RECORD`) and `selftest.json`: the values for Q5's pin. A pull request may write them into `reference/v0.1.yaml`; until then every run is a development run.
- Optionally, GH-MR-H200 in hosted form ([gpu-run.md](gpu-run.md#gpu-host-tests)): `IPROOFS_PROFILE=prover-h200-hosted IPROOFS_GPU=<index> .venv/bin/python -m pytest harness/tests/gpu/test_numa_binding.py`. The job script does not run it; it needs a job of its own, or a later change to `hf-job.sh`.

## Stage 2: SASH smoke on `h200` (estimate 41.84 to 51.96 USD, cap 60 USD)

One repetition, no controls:

```sh
iproofs_job h200 43200 "$SASH_IMAGE" sash-c1024-r1 run sash sash-l31-8b-c1024:1
```

Timeout 12 h (43,200 s): cap 12 h x 5.00 = 60.00 USD. The script's runs must end by 41,700 s after it starts (43,200 less 600 and 900). Estimate, from the one H100 record of this workload and SASH's files, all on an H100, none on an H200:

| Part | Seconds | Source |
|---|---|---|
| `commit` | 6,371 | between its state events, `results/v0.1/sash/2026-11-05-sash-sash-l31-8b-c1024-prover-h100-hosted-1` (measured, tier reported, n = 1; 24 prover CPUs under a 24.96-CPU quota). That run's status is `failed`: kind `timeout`, "verify exceeded 3600.0 s"; the `verify` limit has since been raised to 21,600 s (`systems/sash/system.yaml` `timeouts_s`) |
| `prove`, with the kernel build | 5,768 | same run |
| `verify` on 8 CPUs | 3,600 | a lower bound: the same run's `verify` was stopped at its 3,600 s limit. One development call of `boundary-grid --verify` took 3,381 s at about 3.9 CPUs (n = 1, `systems/sash/system.yaml`) |
| `verify.single_thread` on 1 CPU | 13,186 | assumption: the CPU time of that development call on one CPU, 3,381 s x 3.9; never measured |
| pull, clone, install, 16.1 GB of weights, self-test | 1,200 | assumption |
| **total** | **30,125** (8.37 h) | 8.37 h x 5.00 USD/h = 41.84 USD |

If `commit` and `prove` are CPU-bound and slow by 24/15 with 15 prover CPUs instead of 24 (an assumption the other way), they take 7,283 s more: 37,408 s (10.39 h), 51.96 USD. The deadline leaves 4,292 s above that for `verify` and `verify.single_thread` running longer than assumed; beyond it the run is stopped at the deadline and recorded so. Issue #142 estimated about 7 h for a self-tested job on the H100.

## Stage 3: FlashProve smoke on `h200x2` (estimate 12.24 to 19.31 USD, cap 25 USD)

One repetition of b1, no controls:

```sh
iproofs_job h200x2 9000 "$FP_IMAGE" fp-b1-r1 run flashprove fp-maverick-w1024-b1:1
```

Timeout 2.5 h (9,000 s): cap 2.5 h x 10.00 = 25.00 USD; the runs must end by 7,500 s after the script starts. Estimate:

| Part | Seconds | Source |
|---|---|---|
| the run, first to last event (the job's own rehash of the weights, `setup`, `commit`, `prove`, `verify`) | 3,344 to 4,074 | the six completed b1 runs on an H100 container, `results/v0.1/flashprove/2026-11-05-flashprove-fp-maverick-w1024-b1-prover-h100-hosted-3` to `-8` (measured, tier reported, n = 6). Runs `-1` (failed, kind `adapter`, "setup exited 1") and `-2` (failed, kind `internal`, "runner terminated before completion") of the same campaign stay recorded and are not in this range. In the six: the rehash 395 to 418 s, `setup_seconds` 518 to 874 s, `commit_seconds` 1,956 to 2,122 s |
| weights: 232.1 GB from the Hub | 232 to 774 | assumption: 0.3 to 1.0 GB/s inside the provider's network; not documented |
| `fetch-model`'s sha256 pass over 232.1 GB | 232 | assumption: 1 GB/s |
| pull, clone, install, binding check, self-test | 600 | assumption |
| **total** | **4,408 to 5,680** (1.22 to 1.58 h) | 12.24 to 15.78 USD |

If `commit` is CPU-bound and slows by 24/15 with 15 prover CPUs (an assumption; upstream's timed runs bound 24), it takes 0.6 x 1,956 to 0.6 x 2,122 s more: 5,582 to 6,953 s, 15.51 to 19.31 USD, still within the 7,500 s deadline.

RISK (RFC-0006 §H200 profiles): `setup` compares `KL.bin`, fitted in float32 on the GPU, with upstream's digest, and upstream writes that "its rounding can differ between GPU models, drivers and torch's CUDA libraries". If the job stops there, it is a failed run with its exit code and last lines: keep it, open an issue, and change neither the adapter nor the prover (AGENTS.md rules 1 and 5). Do not go on to stage 4.1 until it is understood.

## Stage 4: fuller configurations, as far as the budget goes

In this order, each only under the stop rule below. b1 and b24 use the same weights; they run as separate jobs, each fetching the weights again (464 to 1,006 s, an assumption above), so that no job's estimate comes near its deadline.

**4.1 FlashProve on `h200x2`: two more b1 repetitions with the control suite.**

```sh
iproofs_job h200x2 14400 "$FP_IMAGE" fp-b1-r2-ctl run flashprove fp-maverick-w1024-b1:2:controls
```

Timeout 4 h: cap 40.00 USD; the runs must end by 12,900 s. Estimate: 600 + (232 to 774) + 232 s of overhead, b1 2 x (3,344 to 4,074) s, controls about 300 s (assumption: the verifier-side controls and their twins call `cp_verify`, about 21 s on one thread upstream, FlashProve README; C3 and P1 report `not_applicable`, see below): 8,052 to 10,054 s (2.24 to 2.79 h), 22.37 to 27.93 USD. With `commit` slower by 24/15 (assumption, as in stage 3): up to 12,600 s, 35.00 USD.

**4.2 SASH: a second repetition on `h200`**, the same command as stage 2 with the label `sash-c1024-r2`: cap 60.00 USD, estimate 41.84 to 51.96 USD.

**4.3 FlashProve on `h200x2`: one b24 repetition**, only if the spend so far is at most 165.00 USD:

```sh
iproofs_job h200x2 12600 "$FP_IMAGE" fp-b24-r1 run flashprove fp-maverick-w1024-b24:1
```

Timeout 3.5 h: cap 35.00 USD; the runs must end by 11,100 s. Estimate: 600 + (232 to 774) + 232 s, and the one b24 run on an H100 container, first to last event, 6,420 s (`results/v0.1/flashprove/2026-11-05-flashprove-fp-maverick-w1024-b24-prover-h100-hosted-1`, measured, tier reported, n = 1; its `verify` state alone lasted 2,217 s): 7,484 to 8,026 s (2.08 to 2.23 h), 20.79 to 22.29 USD. With `commit` (1,997 s) slower by 24/15: up to 9,224 s, 25.62 USD.

The arithmetic, in USD (estimate ranges run from the low estimate to the 24/15 case; stage 1a is counted at its cap):

| Stage | Cap | Running total of caps | Estimate | Running total of estimates |
|---|---|---|---|---|
| 1a, two CPU jobs | 0.01 | 0.01 | under 0.01 | under 0.01 |
| 1, two probes | 5.00 | 5.01 | 3.75 to 5.00 | 3.76 to 5.01 |
| 2, SASH r1 | 60.00 | 65.01 | 41.84 to 51.96 | 45.60 to 56.97 |
| 3, FlashProve b1 r1 | 25.00 | 90.01 | 12.24 to 19.31 | 57.84 to 76.28 |
| 4.1, FlashProve b1 r2 + controls | 40.00 | 130.01 | 22.37 to 35.00 | 80.21 to 111.28 |
| 4.2, SASH r2 | 60.00 | 190.01 | 41.84 to 51.96 | 122.05 to 163.24 |
| 4.3, FlashProve b24 r1 | 35.00 | only if spent + 35.00 <= 200.00 | 20.79 to 25.62 | 142.84 to 188.86 |

Stages 1a to 4.2 fit in 200 USD even if every job runs to its timeout (190.01 USD). With 4.3 that gives SASH 2 repetitions, FlashProve b1 3 repetitions (one with controls) and b24 1: fewer than the 3 per configuration RFC-0004 asks of a release, which is one more reason these runs are development runs. **4.4**, only if the spend so far is again at most 165.00 USD: a second b24 repetition, the 4.3 command with the label `fp-b24-r2` (cap 35.00 USD). On the estimates that is possible only near their low end (142.84 USD after 4.3); nothing beyond it fits.

Not on Jobs, and why:

- **SASH's control suite.** Its verifier-side controls and their honest twins are about 20 `boundary-grid --verify` calls of about an hour each (3,600 s or more, above), and its six registered `weakened_prover` controls each prove again (5,768 s on the H100) and verify: well over 30 h, beyond the budget. It runs on the bare-metal node.
- **C3 and P1 (perturbed weights).** `iproofs controls --prepare-perturbed` runs the adapter under docker only, so on Jobs no perturbed commitment exists and both controls report `not_applicable` (RFC-0008). They run on the bare-metal node.

## Production serving from the engine image (RFC-0015 SRV-6)

The production-serving rows (`ref-serve`, owner decision of 2026-11-09): vLLM v0.32.0 serving the publisher's release with every weight in GPU memory, on the hosted serving profiles `serving-h200x1-hosted` (Llama 3.1 8B BF16, `h200`) and `serving-h200x4-hosted` (Llama 4 Maverick FP8, `h200x4`), which pair with `prover-h200-hosted` (RFC-0006 R6). The overhead divides the prover's GPU-seconds per token by these rows' (RFC-0004 D-OVERHEAD-S). Flavors from `hf jobs hardware` (owner's reading of 2026-11-09, the provider's price): `h200x4` is 4x H200, 92 vCPU, 1,024 GB, 20.00 USD/h; `h200x8` is 8x H200, 184 vCPU, 2,048 GB, 40.00 USD/h.

**Why from the engine image.** On 2026-11-09 ghcr.io refused an anonymous pull token for `ai-verification-observatory/ref-serve` (`UNAUTHORIZED`; RFC-0015 Q6), and the pinned `ref-serve` image was built for plain serving, so the runner refuses a job on it. The engine image is public on Docker Hub: `docker.io/vllm/vllm-openai@sha256:befccf0e...` resolved anonymously to a manifest list whose `linux/amd64` manifest is `sha256:6ee13335...` (40 layers, 9.21 GB compressed). The job starts from it and installs the adapter from the pinned checkout ([`systems/ref-serve/dev_install.py`](../../systems/ref-serve/dev_install.py) on [`systems/_dev/install.py`](../../systems/_dev/install.py), RFC-0014 §Development install):

1. The job command installs `git` with `apt-get` when the image has none (the log prints its version; used by the job script only, never by the engine), then clones and checks out `IPROOFS_COMMIT`.
2. `hf-job.sh` installs uv 0.11.18 from its GitHub release (sha256 checked) if the image has no `uv`, then the harness.
3. After the binding check, `dev_install.py` refuses an image other than the Dockerfile's `FROM`; checks `import vllm` reports 0.32.0 and the image ENV's `VLLM_BUILD_COMMIT` is `5df63a72...`; reads the image's ENV from its config by digest, records it in `inputs.json` and `/opt/iproofs/image_env.json`, and refuses any `VLLM_*`, `NCCL_*`, `CUDA_*` or `TORCH_*` variable the job sets beyond it (other than `CUDA_VISIBLE_DEVICES` and `CUDA_DEVICE_ORDER`); puts the entrypoint, `system.yaml` and `write_inputs.py` where the Dockerfile puts them; and, as uid 10001 with only the bound GPUs visible, requires torch to see exactly that many GPUs with peer access between each pair.
4. `fetch-model --serving <record>` fetches the record's files from the ungated copy and checks every sha256, size and the publisher's git blob ids (RFC-0014 SM-2); no token reaches it unless the record lists a file from the publisher (RFC-0015 Q7: none today).
5. Every run passes `--image <the engine image> --keep-io`, `--gpus` (every GPU of the serving profile), and, per step, `--load high` and `--prompts-from` the prover run it replays (`:high`, `:from=DIR`). The run records `system.image` as `local/docker.io/vllm/vllm-openai@sha256:befccf0e...` with `digest_kind: config`, so it is never eligible for a release (RFC-0014), and every serving profile's driver is `unpinned` (RFC-0006 Q5), so it stays out of `results/` (POL-4). Its kept `io/` holds `engine.log`, `commands.jsonl` (the command, the engine environment, the resolved-configuration and KV-capacity lines) and the outputs, and no weights (the adapter reads `/models` from the cache).

The job command, set after [The job command](#the-job-command):

```sh
VLLM_IMAGE=docker.io/vllm/vllm-openai@sha256:befccf0e7e4089aa23926bb6f887a85c0d46c2a99e6de5c5ffdf5cb7957c5b34
BOOT_ENGINE='set -eu; command -v git >/dev/null || { apt-get update -qq &&
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends git ca-certificates >/dev/null; };
git --version; '"$BOOT"

iproofs_serving_job() {  # FLAVOR TIMEOUT_SECONDS PROFILE LABEL then hf-job.sh's arguments
  local flavor=$1 timeout=$2 profile=$3 label=$4; shift 4
  hf jobs run --detach --flavor "$flavor" --timeout "$timeout" --name "iproofs-$label" \
    --label "iproofs=$label" "${UPLOAD[@]}" \
    -e IPROOFS_COMMIT="$IPROOFS_COMMIT" -e IPROOFS_JOB_BUDGET_S="$((timeout - 600))" \
    -e IPROOFS_LABEL="$label" -e IPROOFS_DEV_IMAGE="$VLLM_IMAGE" -e IPROOFS_PROFILE="$profile" \
    "$VLLM_IMAGE" -- bash -c "$BOOT_ENGINE" hf-job "$@"
}
```

`IPROOFS_COMMIT` must contain this section's `hf-job.sh`, `systems/_dev/` and `systems/ref-serve/dev_install.py` (the merge of that change, or later).

**S0, the image without a GPU** (`cpu-basic`, timeout 15 min, cap under 0.01 USD): that Jobs pulls it by digest, that the command replaces its `ENTRYPOINT` (`vllm serve`; if it does not, the job fails at once with the server's usage message), the user, `import vllm`, whether `git` and `uv` are present, `apt-get`, `/dev/shm`, and which engine variables the provider adds:

```sh
hf jobs run --detach --flavor cpu-basic --timeout 15m --name iproofs-serving-s0 \
  -v "hf://buckets/$NS/iproofs-dev-runs:/upload" "$VLLM_IMAGE" -- \
  bash -c 'date -u; id -u; python3 -V; python3 -c "import vllm; print(vllm.__version__)";
           command -v git uv || true; df -h / /tmp /dev/shm; env | grep -E "^(VLLM|NCCL|CUDA|TORCH)_" | sort;
           apt-get update -qq && echo "apt: reachable";
           mkdir -p /upload/stage-1a && touch "/upload/stage-1a/uid-$(id -u)-vllm" && echo "upload: writable"'
```

A variable in the `env` lines that the image's ENV does not hold (compare with `inputs.json` `image_env` of S1, or the registry config) makes every serving job refuse itself (`config`, SRV-3): stop and put it to the owner.

**S1, Llama 3.1 8B BF16 on `h200`** (TP1, `serving-h200x1-hosted`), matched load, one repetition, replaying the SASH run of stage 2 (copy its folder from the bucket listing; SASH's steady scope is not externally observable, so this run's figure joins no overhead, and S1 tests the adapter, the BF16 record and the 1-GPU path):

```sh
SASH_RUN=runs/<stage-2 folder>/dev-results/v0.1/sash/<run id>
iproofs_serving_job h200 3600 serving-h200x1-hosted serving-l31-bf16-s1 \
  run ref-serve "sash-l31-8b-c1024:1:from=$SASH_RUN"
```

Timeout 1 h: cap 1 h x 5.00 = 5.00 USD. Estimate (projected): pull and install 600 s (assumed, as stage 3); weights 16.07 GB, about 60 s (assumed); `fetch-model`'s hash about 16 s (1 GB/s, assumed); the run's rehash about 28 s (scaled from the 395 to 418 s for 232.1 GB, measured, tier reported, n = 6, stage 3 table); engine load and compile 300 s (assumed); requests about 62 s (assumed): about 1,066 s (0.30 h), 1.48 USD.

**S2, Llama 4 Maverick FP8 on `h200x4`** (TP4, `serving-h200x4-hosted`), matched then high load, one repetition each, replaying FlashProve's b24 run (stage 4.3):

```sh
FP_B24_RUN=runs/<stage-4.3 folder>/dev-results/v0.1/flashprove/<run id>
iproofs_serving_job h200x4 10800 serving-h200x4-hosted serving-mav-fp8-s2 \
  run ref-serve "fp-maverick-w1024-b24:1:from=$FP_B24_RUN" "fp-maverick-w1024-b24:1:high:from=$FP_B24_RUN"
```

Timeout 3 h: cap 3 h x 20.00 = 60.00 USD. Estimate (projected): pull and install 600 s (assumed); weights 416.8 GB, about 862 s (scaled from about 8 min for 232.1 GB, reported, n = 1); `fetch-model`'s hash 417 s (1 GB/s, assumed); per repetition the rehash about 731 s (scaled as in S1), loading 397,449 MiB to 4 GPUs with compilation and CUDA graphs 900 s (assumed, never measured), requests about 65 s matched and 300 s high (5 x 1,024 x 1,025 tokens at an assumed 30,000 token/s): about 5,506 s (1.53 h), 30.59 USD. The second step re-checks the cached files (SM-2) rather than fetching them again.

**S2', only if every S2 attempt failed `resource`** with the KV-capacity line (or an out-of-memory) as evidence: the same content at TP8 on `h200x8` (timeout 3 h, cap 120.00 USD), after an amendment declares `serving-h200x8-hosted` and its `system.yaml` entries (RFC-0015 NM-1). An `adapter` failure never moves the count: fix it and rerun S2.

S0 to S2: about 32.08 USD projected, caps 65.01 USD, before S2'. The owner allots them from what the stop rule below leaves. Every figure from these jobs is a development figure: quote it with its scope, grade, tier `reported`, the profile, the flavor, n and the bucket folder (AGENTS.md rule 2). The repetitions for figures (three per load point) wait until the rebuilt `ref-serve` image is public and pinned and a driver pin exists (RFC-0006 Q5).

RISK: the engine image is built on CUDA 13.0 (`NVIDIA_REQUIRE_CUDA=cuda>=13.0` in its ENV, read 2026-11-09). If the provider's driver cannot run it, `dev_install.py`'s GPU check fails within the job's first minutes, before the weights: keep the job's log, put it to the owner, and change neither the engine nor the adapter (AGENTS.md rule 1).

Read afterwards, in the bucket folder: `job.log` (the `dev-install:` lines, the binding, the GPU check), the run directory's `run.json` (`status`, `metrics`, `warnings`, `failure.kind` and `failure.last_lines`, which end with the KV-capacity line for a `resource` failure), `manifest.json` (`engine`, `serving_model`, `workload.prompt_prefix_digest`, `machine.gpu.unbound_samples`, `machine.container.shm_bytes`, `machine.gpu.nvlink_active_links`), and `io/commands.jsonl` and `io/engine.log`. The first captures set `batches_per_session_run` (SRV-1, a 60 s steady minimum), the PC-GPU-IDLE baseline and whether NVML reports NVLink state (PC-GPU-LINK), and become the adapter's replay fixtures (its stored resolved-configuration line among them), by pull request.

## Stop rule

Before starting any job, and after each one ends:

1. Read the spend: [huggingface.co/settings/billing](https://huggingface.co/settings/billing), section Compute Usage, is the authority. Cross-check with `hf jobs ps -a` and `hf jobs inspect <job id>` for each job: its billed minutes times its flavor's per-minute price.
2. Write the job in the spend log below, with its pull time (creation time against the log's first line).
3. Start the next job only if the spend so far plus that job's cap is at most 200.00 USD. Otherwise stop: the rest of the plan moves to the bare-metal node.
4. Stop and look before spending more when a job fails for a reason not yet understood (a `FAIL` row, a failed binding check, a harness error, an exit other than 0 or 4). The next job is a probe of the question (stage 1a or 1), not a rerun of the same job. Never rerun a failed run to replace it; a rerun is a new repetition and the failed one stays recorded (AGENTS.md rule 5).
5. Cancel a job (`hf jobs cancel <job id>`) whose log shows it stuck (no new line for longer than the longest step estimated above) rather than letting it run to its timeout. A cancelled job does not upload; its billed minutes still count.
6. Never add a flag that weakens a system's statement to make a job pass (AGENTS.md rule 4); the only runs with such flags are the registered controls of `--control-suite`.

Spend log (keep it with the campaign notes, not in the repository; no job IDs or account names go into the repository, AGENTS.md rule 7):

```
| Date (UTC) | Stage | Flavor | Timeout | Pull (min) | Billed minutes | USD | Spent so far | Exit, outcome |
| 2026-11-09 | 1 sash probe | h200 | 20 min | 4 | 14 | 1.17 | 1.17 | 0, see probe.json |
```

(The row is an example of the form, not a result.)

## Where results live

- During the job: under the work directory, `out/dev-results/<release>/<system>/<run id>/`, with `out/dev-results/.selftest.json` and `out/dev-results/.archive/`. The container's disk is deleted when the job ends.
- Afterwards: the private bucket `<namespace>/iproofs-dev-runs`, folder `runs/<UTC time>-<label>/`. List it with `hf buckets list <namespace>/iproofs-dev-runs/runs -h`, and copy one folder out with `hf buckets sync hf://buckets/<namespace>/iproofs-dev-runs/runs/<folder> <a directory outside the checkout>`. With the fallback, the private dataset `<namespace>/iproofs-dev-runs-ds`: `hf download <namespace>/iproofs-dev-runs-ds --repo-type dataset --include 'runs/<folder>/*' --local-dir <a directory outside the checkout>`.
- Never in `results/`. Every run here is made with `--allow-nonconforming` because `prover-h200-hosted` has no pinned driver yet (RFC-0006 Q5), and POL-4 refuses such a run anywhere under `results/` (RFC-0013). RFC-0007 and RFC-0009 set no rule of their own on hosted rows; RFC-0006 §Hosted execution allows them as their own configurations. So a later Jobs run could enter `results/` by a results pull request only once Q5 has pinned the driver, the run used the pinned image and a passing hosted self-test, and the runner ran as root (Q6); the H100 rows already in `results/v0.1` were made that way on `prover-h100-hosted`.
- What these runs are for: finding what fails on an H200 before the official runs (the `KL.bin` digest, memory, the kernel build, timeouts), and the numbers that size the bare-metal campaign. Quote any figure from them with its labels: scope, grade, tier `reported`, the profile `prover-h200-hosted`, the flavor, n, and the bucket folder it came from (AGENTS.md rule 2).

## What never to post

- No token in a command line, file in the checkout, issue or log. With the bucket, no token exists for these jobs. With the fallback, `HF_TOKEN` exists only in `~/.config/iproofs/hf-job.secrets` and, encrypted, as the job's secret.
- No job ID, account name or namespace in the repository (AGENTS.md rule 7): they live in the spend log and the bucket. The probe and the machine record print no host name, address or serial; read them before pasting any part into an issue.
- No weights and no proof bytes in the repository (AGENTS.md rule 8).
