# Hugging Face Jobs

This runbook walks through staged development runs of SASH (`sash-l31-8b-c1024`) and FlashProve (`fp-maverick-w1024-b1`, followed by `fp-maverick-w1024-b24`) on Hugging Face Jobs H200 containers under the `prover-h200-hosted` profile ([RFC-0006 §H200 profiles](../../rfcs/0006-reference-hardware-and-cost.md#h200-profiles), [§Hosted execution](../../rfcs/0006-reference-hardware-and-cost.md#hosted-execution)), staying within a 200 EUR budget. The Level 1 runs for release v1.0 used the same job script ([`level-1.md`](level-1.md)). Runs enter `results/` only via a results pull request (imported with `iproofs results import`), and each `manifest.json` records the provider (see [Where results live](#where-results-live)).

Hugging Face Jobs launches a single container from a named image without an inner Docker engine and bills per minute across both startup and execution ([jobs-pricing](https://huggingface.co/docs/hub/jobs-pricing), read 2026-11-08). The harness's hosted mode (`iproofs run --hosted --gpu <index>`) is built for this environment. Each job clones this repository at a pinned commit and runs [`hf-job.sh`](hf-job.sh), which performs the host probe, harness install, CPU/GPU binding check, hosted self-test, model fetch, benchmark runs, and an upload of all outputs to a private storage bucket.

## Flavors and who runs where

Provider list prices and hardware specs from `hf jobs hardware` and [jobs-configuration](https://huggingface.co/docs/hub/jobs-configuration) (read 2026-11-08; these are provider rates, not the benchmark's cost basis `costs.h200` from RFC-0006 C7):

| Flavor | GPUs | vCPU | RAM | Disk | USD per hour | USD per minute | Used for |
|---|---|---|---|---|---|---|---|
| `cpu-basic` | none | 2 | 16 GB | 50 GB | 0.01 | 0.0002 | stage 1a checks |
| `cpu-xl` | none | 16 | 124 GB | 1,000 GB | 1.00 | 0.0167 | stage 1a if an image exceeds 50 GB; stage 5 verifier-side jobs |
| `cpu-performance` | none | 32 | 256 GB | 1,024 GB | 1.90 | 0.0317 | not planned; also meets stage 5 verifier-side requirements (read 2026-11-09) |
| `h200` | 1x H200 141 GB | 23 | 256 GB | 3,000 GB | 5.00 | 0.0833 | SASH probe and SASH runs |
| `h200x2` | 2x H200, 282 GB | 46 | 512 GB | 6,000 GB | 10.00 | 0.1667 | FlashProve probe and FlashProve runs |

- **SASH runs on `h200`:** This flavor satisfies `prover-h200-hosted` (15 prover CPUs plus 8 verifier CPUs equals 23, and 200 GiB fits under 256 GB). Upstream does not state SASH's host memory requirement; if a run exceeds the container limit, it fails with kind `resource` and is recorded and uploaded like any other failure.
- **FlashProve runs on `h200x2`:** Upstream's `run.sh` refuses to start `commit` with less than 330 GB available, and committing peaked at 299.6 GB upstream (external, reported, [`systems/flashprove/README.md`](../../systems/flashprove/README.md) §Machine needs). Both exceed `h200`'s 256 GB. Each job binds a single GPU (`--gpu`, selected by the probe) and leaves the second idle; the provider still bills the second GPU, though the benchmark's cost calculation does not count it (RFC-0006 R1, C5). The FlashProve probe also runs on `h200x2` because the critical constraints (memory limit, GPU NUMA placement, and usable CPUs per node) are flavor-specific.
- **Separate configuration:** Hosted jobs bind 15 prover CPUs rather than `prover-h200`'s 24, whereas FlashProve's upstream timed runs bound 24 (FlashProve README §CPU binding). Hosted rows form their own configuration and are never pooled with bare-metal rows.

## Budget

At the ECB reference rate from 2026-11-06 (1 EUR = 1.1165 USD, [eurofxref-daily.xml](https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml), read 2026-11-08), 200 EUR equals 223.30 USD. Because Jobs bills in USD and card payments may incur conversion fees, this plan budgets against **200 USD**, treating the remaining 23.30 USD as a safety buffer rather than spendable compute.

Every job sets a `--timeout`, and its **cap** is that timeout multiplied by the flavor's hourly rate. Treating the cap as a hard upper bound relies on one assumption: Hugging Face bills the startup phase (image pull) alongside execution ([jobs-pricing](https://huggingface.co/docs/hub/jobs-pricing)), and its docs do not clarify whether `--timeout` includes startup. If startup is excluded from the timeout, a job can exceed its cap by the length of one pull; assuming pulls take at most 10 minutes, that adds at most 0.83 USD on `h200` and 1.67 USD on `h200x2` (up to 9.17 USD across all seven GPU jobs below, well within the 23.30 USD buffer). If startup is included, the job deadline arrives sooner than the script expects, so `iproofs_job` subtracts 600 s from the timeout when setting `IPROOFS_JOB_BUDGET_S`, and the script reserves another 900 s for upload. Stages 1a and 1 measure actual pull times, and the stop rule tracks actual billed spend rather than theoretical caps.

Even if every job through stage 4.2 hits its full timeout, total spend stays within 200 USD. Expected costs below are estimates derived from H100 records and upstream numbers with explicit assumptions; because no H200 run of either system existed when this plan was written, none of these figures are measured H200 durations.

## Before stage 0: the images must be pullable

Hugging Face Jobs can only pull public images or images built by a Docker Space ([jobs-images](https://huggingface.co/docs/hub/jobs-images), read 2026-11-08). On 2026-11-08, `ghcr.io` rejected anonymous pull tokens for both pinned images, `ghcr.io/ai-verification-observatory/sash` and `ghcr.io/ai-verification-observatory/flashprove` (`{"errors":[{"code":"UNAUTHORIZED","message":"authentication required"}]}`), while granting one for a public package (`astral-sh/uv`). That means the packages were private or missing under those names. You can recheck pullability from any machine:

```sh
for r in sash flashprove; do
  printf '%s: ' "$r"
  curl -s "https://ghcr.io/token?scope=repository:ai-verification-observatory/$r:pull" | head -c 60; echo
done   # {"token":... means public; {"errors":... means private or missing
```

Do this once before stage 1a:

1. As a GitHub organization owner, open each package (organization page -> Packages -> `sash` and `flashprove`), go to Package settings -> Danger Zone -> Change visibility, and select Public. GitHub warns that making a package public is irreversible. These images contain only the adapters and upstream sources at their pinned commits and toolchains, with no weights and no secrets (RFC-0014; `systems/*/Dockerfile`).
2. Rerun the check above and confirm that both lines begin with `{"token"`.

If the packages stay private, the only alternative Jobs documents is building the image inside a Docker Space. Rebuilding from `systems/<name>/Dockerfile` produces a different digest, so those runs count as local builds (`--image`), are never eligible for a release (RFC-0014), and would require changes to `hf-job.sh`. Publishing the packages preserves the pinned digests.

## Stage 0: the hf CLI and the bucket (owner, interactive, no cost)

```sh
uv tool install --upgrade huggingface_hub    # or: pip install -U huggingface_hub; this page was checked with hf 2.4.0
hf version
hf auth login                                 # paste a token that may start and manage Jobs
hf auth whoami
hf jobs hardware                              # check the cpu-basic, h200 and h200x2 rows and prices again
hf buckets create <namespace>/iproofs-dev-runs --private
```

Jobs requires a positive credit balance on the account ([jobs-pricing](https://huggingface.co/docs/hub/jobs-pricing)); add 200 EUR at [huggingface.co/settings/billing](https://huggingface.co/settings/billing).

Job outputs are exported through a private [storage bucket](https://huggingface.co/docs/hub/storage-buckets) mounted inside the container (`-v hf://buckets/<namespace>/iproofs-dev-runs:/upload`; buckets mount read-write, [jobs-configuration §Volumes](https://huggingface.co/docs/hub/jobs-configuration#volumes)). `hf-job.sh` copies its outputs there, and because the job runs under the owner's login, no token needs to enter the container. Storage beyond the free allowance is billed by volume ([hf.co/storage](https://huggingface.co/storage)). A FlashProve job stores only megabytes to a few hundred megabytes (assuming logs, records, and one proof archive per configuration at roughly 19 MB from upstream's average proof size). SASH jobs are much larger: the archive of its first accepted proof was 44,638,531,893 bytes (from the H100 run's `manifest.json`, measured, n = 1). Under `keep-io` (stage 2), the job uploads that proof once under `io/proofs`, alongside `io/state` (unrecorded size) and the commitment store, instead of duplicating it in an archive.

**Fallback (only if stage 1a finds the mounted bucket is not writable by the job's UID):** Use a private dataset with a narrowly scoped token. Create the dataset first under your personal login (a single-repo token cannot create repositories), then generate a fine-grained token with write access to that dataset alone and store it via a silent prompt so it never enters command history:

```sh
hf repos create <namespace>/iproofs-dev-runs-ds --type dataset --private
mkdir -p ~/.config/iproofs && chmod 700 ~/.config/iproofs
( umask 077; read -rs T && printf 'HF_TOKEN=%s\n' "$T" > ~/.config/iproofs/hf-job.secrets; unset T )
```

Jobs passes this file to the container as an encrypted secret (`--secrets-file`). `hf-job.sh` uses the token strictly for uploading; the harness, adapter, and `fetch-model` run without it (both models are ungated), and the hosted runner strips any variable containing `TOKEN` from the adapter's environment. Note that this isolates the token from the adapter only when the container runs as root, allowing the hosted runner to drop the adapter to UID 10001. If the container already runs as the image's default user 10001 (checked in stage 1a), the adapter and upstream prover share the same UID as the job script and could read the token from `/proc/1/environ` (RFC-0006 Q6). In that case, the token's write scope to that single dataset is the only boundary limiting it.

## Uploads: through the bucket API, checked (2026-11-09)

On 2026-11-08, SASH's first run (`sash-c1024-r1`) completed with an accepted proof, yet its run directory never reached the bucket. Copying into the mounted bucket returned in 38 s and the job exited while the mount was still flushing the proof archive in the background, dropping the archive and everything queued behind it (`hf-mount` bounds shutdown flushing via `--flush-shutdown-timeout-ms`, defaulting to 45 s, [hf-mount](https://github.com/huggingface/hf-mount); Jobs does not document its mount's write mode). Small outputs like FlashProve's 18 MB proofs were unaffected.

Because of this, every job with a token now uploads directly through the bucket API. `hf-job.sh` runs `hf buckets sync` (`huggingface_hub` 2.4.0) in two passes (small records first, excluding proof archives and `io/`, followed by the large files), verifies every file in `out/` against the bucket listing by size, and writes `upload.done` only after verification passes. If a sync or size check fails, the script retries every 10 minutes (`IPROOFS_UPLOAD_RETRY_S`) until 30 minutes before the job budget expires (`IPROOFS_UPLOAD_RETRY_STOP_S`), giving time to raise a storage quota or wait out a network blip (two SASH `keep-io` uploads failed simultaneously when storage quota filled on 2026-11-13). Any failed or incomplete upload is reported explicitly in the log. With `keep-io`, each proof uploads immediately once the adapter releases it (a directory under `io/proofs` renamed into place, RFC-0005) into the job's pre-assigned folder under its final run ID, so the end-of-job sync finds it already in place. Proof archives (`.tar` copies of one proof) are skipped unless `IPROOFS_UPLOAD_ARCHIVES=1`, since `keep-io` already preserves proofs in `io/proofs`.

Set up a dedicated, revocable token with bucket write access once in a private secrets file:

```sh
mkdir -p ~/.config/iproofs && chmod 700 ~/.config/iproofs
( umask 077; printf 'HF_TOKEN=%s\n' '<token>' > ~/.config/iproofs/hf-job.secrets )
```

Every job command then passes `--secrets-file ~/.config/iproofs/hf-job.secrets -e IPROOFS_UPLOAD_BUCKET=$NS/iproofs-dev-runs` (the bucket mount can remain attached for reading stored runs). The token is injected as an encrypted secret and never printed; because the adapter and prover share the same UID inside these images and could read it (RFC-0006 Q6), use a dedicated token and delete it when the campaign ends.

## The job command

Define these shell variables and helpers once per shell. Set `IPROOFS_COMMIT` to the full 40-character hash of a commit on `main` containing `docs/runbooks/hf-job.sh`, and keep the same commit across the campaign. Because `keep-io` and the `seed`, `controls`, and `merge` modes were introduced with the split-suite merge, advance `IPROOFS_COMMIT` to that merge (or later) starting at stage 2, and use that single commit for stage 2, stage 5, and all subsequent stages. Its `systems/sash/system.yaml` must match `SASH_IMAGE` (`iproofs controls --hosted` rejects runs created with a different image, and `merge` rejects parts from different harness commits). Record the chosen commit in the campaign notes. Although the stage 1 probe ran on an earlier commit, its hardware findings (GPU, NUMA, memory, disk, UID) still apply, and stage 2 reruns the probe, binding check, and self-test at the new commit anyway.

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

EXTRA=()   # more hf jobs run options for one job; stage 5's ctl sets it
iproofs_job() {  # FLAVOR TIMEOUT_SECONDS IMAGE LABEL then hf-job.sh's arguments
  local flavor=$1 timeout=$2 image=$3 label=$4; shift 4
  hf jobs run --detach --flavor "$flavor" --timeout "$timeout" --name "iproofs-$label" \
    --label "iproofs=$label" "${UPLOAD[@]}" "${EXTRA[@]}" \
    --secrets-file "$HOME/.config/iproofs/hf-job.secrets" -e IPROOFS_UPLOAD_BUCKET="$NS/iproofs-dev-runs" \
    -e IPROOFS_COMMIT="$IPROOFS_COMMIT" -e IPROOFS_JOB_BUDGET_S="$((timeout - 600))" \
    -e IPROOFS_LABEL="$label" \
    "$image" -- bash -c "$BOOT" hf-job "$@"
}
```

The image digests match `systems/sash/system.yaml` and `systems/flashprove/system.yaml`; update them here if the pins change. Although each image's `ENTRYPOINT` is the adapter, Jobs overrides it with the command given after the image name, as shown in Hugging Face's own `hf jobs run vllm/vllm-openai bash -c ...` example ([jobs-images](https://huggingface.co/docs/hub/jobs-images)); stage 1a confirms this behavior. `--detach` prints the job ID. Stream logs with `hf jobs logs -f <job id>`, inspect status with `hf jobs inspect <job id>`, and stop a job with `hf jobs cancel <job id>`.

Inside the container, `hf-job.sh` runs these steps in order:

1. **Checkout:** Both images include `git`. The work directory is `/work` when running as root, or `/tmp/iproofs` (the only writable path) when running as the image's UID 10001 (RFC-0006 Q6). The script aborts if `HEAD` does not match `IPROOFS_COMMIT`, sets `HOME` and `HF_HOME` inside the work directory (UID 10001 has no home directory), and checks whether the mounted bucket is writable.
2. **Probe:** Runs `host-probe.py --profile prover-h200-hosted` (Python standard library only) and writes `out/probe.json`. The job continues regardless of probe results so the diagnostic record is complete, selecting the probe's `suggested_gpu_index` (or `0` by default) as the bound GPU.
3. **Harness:** Runs `uv sync --frozen --no-dev --extra gpu --extra fetch --extra prompts` against `uv.lock` to install NVML, `fetch-model`, and `tokenizers` (required to build workload prompts from `tokenizer.json`), then verifies all three import cleanly. Both images include Python 3.12.3 (Ubuntu 24.04's `python3`) and `uv` (0.11.18 in SASH's image per its Dockerfile). FlashProve's image also ships `pip` 24.0, but Ubuntu blocks system-wide `pip` installs under PEP 668, so both images use `uv`. The harness requires Python 3.12 or 3.13 (`pyproject.toml`).
4. **Binding check:** Checks which CPUs `iproofs run --gpu` would bind under `prover-h200-hosted` (`GpuEnvironment`, RFC-0006 §CPU and memory selection). This fails if the GPU lacks a NUMA node or has fewer than 15 usable CPUs on that node; the failure is recorded in the manifest and execution proceeds.
5. **Self-test:** Runs `iproofs machine-record --hosted --selftest` (RFC-0011) and saves the result to `out/selftest.json` and the results directory.
6. **Development install (only when `IPROOFS_DEV_IMAGE` is set):** See [Production serving](#production-serving-from-the-engine-image-rfc-0015-srv-6). `systems/<system>/dev_install.py` installs the adapter into the base engine image and validates the engine, environment, and bound GPUs, while runs pass `--image` and `--keep-io`. Any failure here aborts the job before downloading weights.
7. **Weights:** Runs `iproofs fetch-model <workload>` under the same deadline as the benchmark runs, fetching only the workload's pinned files, verifying every sha256 and the overall model digest (RFC-0014), and caching them in `$IPROOFS_CACHE` under the work directory without needing a token.
8. **Runs:** Runs `iproofs run --system S --workload W --profile prover-h200-hosted --hosted --gpu <index> --provider "Hugging Face Jobs" --repetitions N --allow-nonconforming --results out/dev-results [--control-suite] [--keep-io]` under `timeout`, stopping 15 minutes before the script's budget (or 60 minutes with `keep-io`; see stage 2). A timed-out run exits 124 or 137 before finalizing, leaving `io/` (which holds a weight copy for FlashProve), scratch directories, and the commitment store (which holds FlashProve's secret key) in its staging directory. Before uploading, the script deletes those directories (logging each size) and uploads the remaining staging files (logs and `job.lock`), recording the outcome as a failed run with that exit code (AGENTS.md rule 5).
9. **Upload:** On every exit, copies `out/` (job log, probe, self-test, run directories, and proof archives) to `runs/<UTC time>-<label>/` in the bucket: logs and small records first, then the self-test record and run directories, then proof archives (omitted under `keep-io` because `io/proofs` already contains the proof, while its digest stays in `digests.txt`), and finally the log again. If the upload finishes without error, the script writes `upload.done` (recording bytes sent) into the folder. The `seed`, `controls`, and `merge` modes refuse any stored run missing `upload.done`, since its upload may be incomplete.

Each `STEP` argument takes the form `WORKLOAD:REPETITIONS`, with optional colon-separated flags: `controls` runs the control suite inside the job (`--control-suite`), and `keep-io` retains the completed run's `io/` directory (prompts, adapter outputs, state, proofs) and commitment store (`--keep-io`) so they upload to the bucket for downstream `controls` jobs (stage 5). The job log prints the size of every retained directory. `keep-io` is rejected before the probe for FlashProve because its `io/` holds a full copy of the weights and its commitment store holds the prover's secret key.

A setup is made once and reused by every session (`iproofs.setups`). `hf-job.sh setup SYSTEM WORKLOAD[:level=ID]` runs steps 1 to 7, then `iproofs run ... --make-setup`: info, setup and commit with no prompt. It writes `out/dev-results/<release>/SYSTEM/_setups/<setup id>/` with `setup.json` (the record: the exact job inputs of each call, the pins, the commitment files, the kernel store, each step's seconds, the whole wall and the GPU-seconds, each labelled) and `state.tar` (the `/io/state` commit left). The archive goes up with the record and is checked file by file like every other file. A setup takes no other step field, and FlashProve is refused (its state holds a weights copy and the prover's key). A run step then names it with `setup=runs/<folder>/dev-results/<release>/SYSTEM/_setups/<setup id>`. Before the probe, the script requires the mounted bucket, that path's form, `setup.json` and `state.tar`, and the folder's `upload.done`. The step copies the setup onto local disk before its weights and passes `--setup` to `iproofs run`. The harness checks the archive's sha256 and that the setup was made for this system pin, image, adapter commit, model digest and shape. It restores the state under `/io/state` (timed apart, run.json `setup.restore_seconds`) and calls commit with `setup_state`. The adapter checks the restored state and makes nothing; a commit that returns another commitment than the record's stops the run. For SASH, a session of the ladder is `l1-l31-8b-p512-o512:1:level=L1:session=K:perturbed:keep-io:setup=<path>`: `perturbed` commits W' on the session's host and writes it beside the run, which C3 and P1 need and no later job can add, and `keep-io` keeps the proofs for the split control jobs (`seed`, `controls`, `merge` below). The `controls` step field is not used for a SASH session: inside the job it runs the whole suite, the weakened provers of `controls.yaml` included, each a session's worth of proving.

Four modes operate on an existing stored run at `RUN_PATH` = `runs/<folder>/dev-results/<release>/SYSTEM/<run id>` inside the mounted bucket ([RFC-0008 §Split suites](../../rfcs/0008-negative-controls.md#split-suites)). Before running the probe or install, each mode rejects a missing bucket mount, an invalid `RUN_PATH`, a run missing `run.json` or `manifest.json`, a folder missing `upload.done`, or a run that already contains `controls.json` (controls run once per configuration). The dataset fallback is not supported for these modes:

- `hf-job.sh seed SYSTEM RUN_PATH`: Installs only the harness (skipping probe, GPU checks, and self-test), runs `iproofs controls --draw-seed` against a copy of `run.json` and `manifest.json`, and writes `controls-seed.json` into the stored run. It refuses runs that already have a seed, because the harness draws the seed once from `os.urandom` (SPLIT-1).
- `hf-job.sh reverify SYSTEM RUN_PATH [PROOF_ID]` (RFC-0018 CH-4a, `cpu-xl`, no GPU): Re-verifies every kept proof under syscall tracing (roughly 1,500 s per proof for SASH) and writes `reverify/` beside the stored run. Passing `PROOF_ID` copies the run without its other proofs and verifies only that single proof into `out/reverify-parts/`; you can run one job per proof and combine them with `iproofs reverify RUN_DIR --merge PART...`.
- `hf-job.sh controls SYSTEM RUN_PATH ID[,ID...]`: Additionally rejects runs lacking `io/proofs`, `commitment/` (runs made without `keep-io`), or `controls-seed.json`, as well as any ID outside C1 to C8, P1, P2, or the `id:` entries in `systems/SYSTEM/controls.yaml`. It executes steps 1 through 3; once GPUs are counted, any prover-side ID on a CPU-only host is rejected before copying data. If a GPU is present, it runs steps 4 and 5 and fetches the workload weights; on a verifier-only host, it skips them. Next, it copies the run directory onto local disk (from `IPROOFS_STORED_DIR`, a read-only mount of the run, if set), logs the bytes and duration of the copy, and invokes `iproofs controls <copy> --hosted [--gpu <index>] --provider "Hugging Face Jobs" --only ID[,ID...] --seed <the recorded seed>` (never re-uploading the local copy). The resulting part and logs are copied to `out/controls/` and uploaded with the small files. Each completed control call logs a progress line (`controls verify C2 trial 0  <elapsed>  exit 0  <seconds> s`, the `control.call` event) visible in `hf jobs logs`. Exit 0 writes the part; exit 2 signals a refusal (such as a prover-side ID on a CPU host or a mismatched GPU); exit 124 or 137 means the job hit its deadline and wrote no part.
- `hf-job.sh merge SYSTEM RUN_PATH`: Installs only the harness, copies `run.json`, `manifest.json`, and `controls-seed.json`, gathers all parts matching the recorded seed under `runs/*/controls/`, runs `iproofs controls --merge`, and writes `controls.json` into the stored run alongside the merged parts under `controls-parts/<job folder>/` (preserving which host measured each trial). If merging fails validation, nothing is written.

## Stage 1a: the containers without a GPU (under 0.01 USD)

Run one `cpu-basic` job per image to verify everything that does not require a GPU: pulling by digest, overriding `ENTRYPOINT`, runtime UID, `HOME`, free disk on `/` and `/tmp`, installed versions of `git`, `uv`, and `python3`, bucket write permissions for that UID, and image pull latency:

```sh
for img in "$SASH_IMAGE" "$FP_IMAGE"; do
  hf jobs run --detach --flavor cpu-basic --timeout 15m --name iproofs-stage-1a \
    -v "hf://buckets/$NS/iproofs-dev-runs:/upload" "$img" -- \
    bash -c 'date -u; id -u; echo "HOME=$HOME"; df -h / /tmp; git --version; uv --version; python3 -V;
             mkdir -p /upload/stage-1a && touch "/upload/stage-1a/uid-$(id -u)" && echo "upload: writable"'
done
```

Both jobs together have a cap under 0.01 USD (15 min x 0.01 USD/h each). If either fails before printing its first log line with a disk error, the image exceeds 50 GB; rerun it on `cpu-xl` (cap 0.25 USD). Check these outputs:

- **Pull latency:** Compare the job's creation timestamp in `hf jobs inspect` against the first `date -u` line in its log, and record it in the spend log. If it exceeds 10 minutes, increase the 600 s pull allowance in `iproofs_job` by the excess before stage 1.
- **Runtime UID (`id -u`):** Expect `0` or `10001`. If `10001`, the work directory defaults to `/tmp/iproofs`, meaning `/tmp` must have more than 500 GiB free on GPU flavors (verified in stage 1), and any fallback token would be readable by the adapter (stage 0).
- **Bucket writability (`upload: writable`):** If this line is missing, switch `UPLOAD` to the dataset fallback from stage 0.
- **Bucket throughput:** No provider page documents bucket read and write speeds, which stages 2 and 5 depend on. Measure them with a third `cpu-basic` job: `hf jobs run --detach --flavor cpu-basic --timeout 30m -v "hf://buckets/$NS/iproofs-dev-runs:/upload" "$SASH_IMAGE" -- bash -c 'mkdir -p /upload/stage-1a; date -u +%s; dd if=/dev/zero of=/upload/stage-1a/speed.bin bs=1M count=4096 conv=fsync; date -u +%s; dd if=/upload/stage-1a/speed.bin of=/dev/null bs=1M; date -u +%s; rm /upload/stage-1a/speed.bin'` (writes and reads 4 GiB through the mount and cleans up; cap 0.01 USD). Record both rates in the spend log with n = 1. Because the read immediately follows the write, it may hit the mount's local cache and acts as an upper bound; each stage 5 `controls` job logs the exact bytes and duration of its own run copy, which is the read rate that matters. Stage 2 requires at least 12.4 MB/s write throughput for its 3,600 s upload reserve; stage 5 estimates assume 75 MB/s reads while its timeouts allow down to 12.4 MB/s (below).

## Stage 1: probe jobs (expected 3.75 USD, cap 5.00 USD)

Run one short probe per system on its target GPU flavor before committing to long runs. This checks the GPU's NVML name and memory (`PC-GPU-MODEL` requires `NVIDIA H200`; PCIe variants report a different name), driver and CUDA versions (for the pin, RFC-0006 Q5), CC mode, CPU limit (quota, cpuset, or VM CPU count), NUMA placement and usable CPUs per GPU, memory limit, writable paths and free disk space, whether the container runs as root (Q6), `madvise(MADV_WIPEONFORK)` and SHA extensions (for FlashProve), the CPU/GPU binding check, and the hosted self-test:

```sh
iproofs_job h200   1200 "$SASH_IMAGE" probe-sash       probe
iproofs_job h200x2 1200 "$FP_IMAGE"   probe-flashprove probe
```

Each job has a 20 min timeout: caps are 1.67 USD (`h200`, 20/60 h x 5.00 USD/h) and 3.33 USD (`h200x2`, 20/60 h x 10.00 USD/h), totaling 5.00 USD. Expected spend is 1.25 USD and 2.50 USD assuming 15 min per job (pull latency is billed and measured in stage 1a, while the probe, `uv sync`, binding check, and self-test take a few minutes).

Inspect each job's log and `probe.json` for the following:

- **Profile failures (`failed`):** Any `FAIL` row without `[flashprove]` halts the plan until the root cause is fixed or logged as an issue. In particular, `cpus_on_gpu_numa_node` failing with `no NUMA node`, or a non-zero `binding check exit`, blocks all runs on that flavor because `iproofs run --gpu` refuses unbound GPUs. If `cc_mode_off` reports `UNKNOWN`, note that the container cannot query CC mode.
- **FlashProve checks (`failed_flashprove`):** Must be empty on `h200x2`, and `flashprove_commit_floor_gb` must pass. If `madvise_wipeonfork`, `sha_ni`, or `cuda_driver_api_flashprove` fails, FlashProve cannot run on Jobs: skip stages 3, 4.1, and 4.3 and allocate budget to SASH only. Note `suggested_gpu_index`, which the job will bind.
- **Work disk (`work_disk_free_gib`, `work_disk_writable`):** FlashProve requires roughly 245 GB plus a second copy of its 232.1 GB weights per job (FlashProve README §Machine needs, §What `commit` needs). If free space is below 500 GiB, adjust `BOOT` before stage 3.
- **User context (`system.home_writable`, `system.root`):** Confirm stage 1a findings on the GPU flavors.
- **Driver pin (`driver` marked `RECORD`, and `selftest.json`):** Collect these values for the Q5 driver pin. Until a pull request records them in `reference/v0.1.yaml`, every run counts as a development run.
- **Optional hosted NUMA test:** To run GH-MR-H200 in hosted form ([gpu-run.md](gpu-run.md#gpu-host-tests)), execute `IPROOFS_PROFILE=prover-h200-hosted IPROOFS_GPU=<index> .venv/bin/python -m pytest harness/tests/gpu/test_numa_binding.py` in a dedicated job or a future `hf-job.sh` update (the current script does not invoke it).

## Stage 2: SASH smoke on `h200` (estimate 41.84 to 51.96 USD, cap 60 USD)

Run one repetition without in-job controls, retaining its proofs for the stage 5 control jobs:

```sh
iproofs_job h200 43200 "$SASH_IMAGE" sash-c1024-r1 run sash sash-l31-8b-c1024:1:keep-io
```

The 12 h (43,200 s) timeout caps spend at 60.00 USD (12 h x 5.00 USD/h). With `keep-io`, the script reserves 3,600 s for upload rather than 900 s, leaving 39,000 s after script startup for the run (43,200 minus 600 and 3,600). The proof is uploaded once under `io/proofs` (1,639 parts totaling 44,638,531,893 bytes in the H100 run's `manifest.json`, measured, n = 1). Although the run also writes an uncompressed `.tar` archive of that proof under `.archive/` (RFC-0014, one proof per configuration), `keep-io` skips uploading `.archive/` so the upload does not double to 89,277,063,786 bytes plus `io/state` (which would require 24.8 MB/s). `io/state` (including SASH's kernel build tree) and the commitment store upload alongside `io/proofs`; because their sizes were unrecorded, the job log prints the sizes of `io/`, `commitment/`, and the skipped `.archive/`.

A 3,600 s reserve suffices for the proof alone at a bucket write rate of at least 12.4 MB/s (assumed until measured in stage 1a; increase this timeout accordingly if stage 1a measures a slower write rate). If upload fails to finish, `upload.done` is never written and stage 5 jobs reject the run immediately before incurring significant cost. Bucket storage above the free tier is billed ([hf.co/storage](https://huggingface.co/storage)). If stage 2 already ran without `keep-io`, its proofs and commitment store were deleted at finalization (RFC-0010) and cannot feed control jobs; add `keep-io` to stage 4.2 instead and target that run in stage 5.

Duration estimate, based on the single H100 record of this workload and SASH's files (all H100 measurements, none on H200):

| Part | Seconds | Source |
|---|---|---|
| `commit` | 6,371 | between step events in `results/v0.1/sash/2026-11-05-sash-sash-l31-8b-c1024-prover-h100-hosted-1` (measured, tier reported, n = 1; 24 prover CPUs under a 24.96-CPU quota). That run ended `failed` with kind `timeout` ("verify exceeded 3600.0 s"); the `verify` limit has since been raised to 21,600 s (`systems/sash/system.yaml` `timeouts_s`) |
| `prove`, with the kernel build | 5,768 | same run |
| `verify` on 8 CPUs | 3,600 | lower bound: `verify` hit its 3,600 s limit in that run. A separate development call of `boundary-grid --verify` took 3,381 s at about 3.9 CPUs (n = 1, `systems/sash/system.yaml`) |
| `verify.single_thread` on 1 CPU | 13,186 | assumption: CPU time of that development call on one CPU (3,381 s x 3.9); never measured |
| pull, clone, install, 16.1 GB of weights, self-test | 1,200 | assumption |
| **total** | **30,125** (8.37 h) | 8.37 h x 5.00 USD/h = 41.84 USD |

If `commit` and `prove` are CPU-bound and slow down by 24/15 with 15 prover CPUs instead of 24 (a conservative assumption), they add 7,283 s, bringing total time to 37,408 s (10.39 h, 51.96 USD). That leaves 1,592 s of headroom below the deadline for longer `verify` and `verify.single_thread` calls (or 4,292 s without `keep-io`); any run exceeding the deadline is stopped and recorded as timed out. Issue #142 estimated roughly 7 h for a self-tested H100 job.

## Stage 3: FlashProve smoke on `h200x2` (estimate 12.24 to 19.31 USD, cap 25 USD)

Run one repetition of b1 without controls:

```sh
iproofs_job h200x2 9000 "$FP_IMAGE" fp-b1-r1 run flashprove fp-maverick-w1024-b1:1
```

The 2.5 h (9,000 s) timeout caps spend at 25.00 USD (2.5 h x 10.00 USD/h) and requires the run to finish within 7,500 s of script startup:

| Part | Seconds | Source |
|---|---|---|
| full run, first to last event (weight rehash, `setup`, `commit`, `prove`, `verify`) | 3,344 to 4,074 | six completed b1 runs on an H100 container, `results/v0.1/flashprove/2026-11-05-flashprove-fp-maverick-w1024-b1-prover-h100-hosted-3` through `-8` (measured, tier reported, n = 6). Runs `-1` (failed, kind `adapter`, "setup exited 1") and `-2` (failed, kind `internal`, "runner terminated before completion") remain recorded and are excluded from this range. Across the six completed runs: rehash 395 to 418 s, `setup_seconds` 518 to 874 s, `commit_seconds` 1,956 to 2,122 s |
| weights: 232.1 GB from the Hub | 232 to 774 | assumption: 0.3 to 1.0 GB/s inside the provider's network (undocumented) |
| `fetch-model` sha256 verification over 232.1 GB | 232 | assumption: 1 GB/s |
| pull, clone, install, binding check, self-test | 600 | assumption |
| **total** | **4,408 to 5,680** (1.22 to 1.58 h) | 12.24 to 15.78 USD |

If `commit` is CPU-bound and slows by 24/15 on 15 prover CPUs (assumed; upstream timed runs bound 24), it adds 0.6 x 1,956 to 0.6 x 2,122 s, bringing the total to 5,582 to 6,953 s (15.51 to 19.31 USD), still inside the 7,500 s deadline.

**RISK (RFC-0006 §H200 profiles):** `setup` checks `KL.bin` (fitted in float32 on the GPU) against upstream's reference digest, and upstream notes that "its rounding can differ between GPU models, drivers and torch's CUDA libraries". If the job fails at this step, record the exit code and trailing log lines, open an issue, and modify neither the adapter nor the prover (AGENTS.md rules 1 and 5). Do not proceed to stage 4.1 until the mismatch is understood.

## Stage 4: fuller configurations, as far as the budget goes

Run these steps in order, stopping whenever the stop rule below triggers. Although b1 and b24 share the same weights, they run as separate jobs (each fetching weights on its own for an assumed 464 to 1,006 s) so neither job risks hitting its timeout.

**4.1 FlashProve on `h200x2`: two more b1 repetitions with the control suite.**

```sh
iproofs_job h200x2 14400 "$FP_IMAGE" fp-b1-r2-ctl run flashprove fp-maverick-w1024-b1:2:controls
```

The 4 h timeout caps spend at 40.00 USD and leaves 12,900 s for the runs. Estimated duration is 8,052 to 10,054 s (2.24 to 2.79 h, 22.37 to 27.93 USD): 600 + (232 to 774) + 232 s of setup and weights overhead, 2 x (3,344 to 4,074) s for b1, and roughly 300 s for controls (assuming verifier-side controls and twins call `cp_verify` at roughly 21 s single-threaded upstream, FlashProve README; C3 and P1 report `not_applicable`, see below). If `commit` slows by 24/15 (as assumed in stage 3), duration rises up to 12,600 s (35.00 USD).

**4.2 SASH: a second repetition on `h200`.** Run the same command as stage 2 with label `sash-c1024-r2`, omitting `keep-io` (controls run once per configuration, RFC-0008) unless stage 2 failed to save its proofs. Cap: 60.00 USD; estimate: 41.84 to 51.96 USD.

**4.3 FlashProve on `h200x2`: one b24 repetition** (only if cumulative spend so far is at most 165.00 USD):

```sh
iproofs_job h200x2 12600 "$FP_IMAGE" fp-b24-r1 run flashprove fp-maverick-w1024-b24:1
```

The 3.5 h timeout caps spend at 35.00 USD and leaves 11,100 s for the run. Combining 600 + (232 to 774) + 232 s of overhead with the single H100 b24 run's 6,420 s duration from first to last event (`results/v0.1/flashprove/2026-11-05-flashprove-fp-maverick-w1024-b24-prover-h100-hosted-1`, measured, tier reported, n = 1; its `verify` step alone took 2,217 s) yields 7,484 to 8,026 s (2.08 to 2.23 h, 20.79 to 22.29 USD). If `commit` (1,997 s) slows by 24/15, total time increases up to 9,224 s (25.62 USD).

Budget summary in USD (estimate ranges span the baseline estimate through the 24/15 slowdown case; stage 1a is counted at its cap):

| Stage | Cap | Running total of caps | Estimate | Running total of estimates |
|---|---|---|---|---|
| 1a, two CPU jobs | 0.01 | 0.01 | under 0.01 | under 0.01 |
| 1, two probes | 5.00 | 5.01 | 3.75 to 5.00 | 3.76 to 5.01 |
| 2, SASH r1 | 60.00 | 65.01 | 41.84 to 51.96 | 45.60 to 56.97 |
| 3, FlashProve b1 r1 | 25.00 | 90.01 | 12.24 to 19.31 | 57.84 to 76.28 |
| 4.1, FlashProve b1 r2 + controls | 40.00 | 130.01 | 22.37 to 35.00 | 80.21 to 111.28 |
| 4.2, SASH r2 | 60.00 | 190.01 | 41.84 to 51.96 | 122.05 to 163.24 |
| 4.3, FlashProve b24 r1 | 35.00 | only if spent + 35.00 <= 200.00 | 20.79 to 25.62 | 142.84 to 188.86 |

Stages 1a through 4.2 stay under 200 USD even if every job hits its timeout (190.01 USD). Including stage 4.3 yields 2 repetitions for SASH, 3 for FlashProve b1 (one with controls), and 1 for b24: still short of the 3 repetitions per configuration required for a release (RFC-0004), which is another reason these remain development runs. **4.4 (optional):** If spend after 4.3 is still at most 165.00 USD, run a second b24 repetition using the 4.3 command with label `fp-b24-r2` (cap 35.00 USD). Based on the estimates, that fits only near the low end (142.84 USD after 4.3), and nothing beyond it fits.

What does not run on Jobs:

- **C3 and P1 (perturbed weights):** `iproofs controls --prepare-perturbed` only supports Docker mode, so no perturbed commitment is available on Jobs and both controls report `not_applicable` (RFC-0008). Run these on the bare-metal node instead.

## Stage 5: SASH's control suite in parallel jobs (estimate 138.73 to 196.74 USD, cap 330.01 USD)

Stage 5 sits outside the 200 USD plan above: set a dedicated budget before starting the first job, and apply the stop rule against that amount instead of 200.00 USD. Rather than running a single 30+ hour job, this stage splits SASH's full control suite against the stage 2 run (or the first completed SASH run saved with `keep-io`) into eleven concurrent jobs under [RFC-0008 §Split suites](../../rfcs/0008-negative-controls.md#split-suites), then merges their outputs into `controls.json`. Every control preserves its honest twin and seeded mutations, producing the exact same merged `controls.json` as a single-host run with the same seed (INV-CTRL-7). FlashProve's controls run inside its main job (stage 4.1, assumed ~300 s), and `keep-io` is disallowed for FlashProve (see above).

Breakdown of the SASH suite (`systems/sash/controls.yaml`, RFC-0008) on a single-request, batch-size-1 run:

| Controls | Side | Applicable on this run | Verify calls | Weights |
|---|---|---|---|---|
| C1, C2, C5, C8 | verifier | yes | 2 each: twin and trial | no |
| C6 | verifier | yes | 6: twin and five trials, in one part | no |
| C3 | verifier | no: no perturbed commitment on Jobs (below) | 0 | no; on a host that has one, C3 reads only its stored commitment record |
| C4, C7 | verifier | no: one request, and batch size 1 | 0 | no |
| P1, P2 | prover | no: no perturbed weights on Jobs; one precision | 0 | yes, resolved before the not-applicable check |
| the six `sash-unsound-*` controls | prover | yes | 2 each, after the control's prove: twin and the control's proof | yes: each proves again |

Because `verify` never mounts `/models` (RFC-0005), verifier-side jobs fetch no weights. They bind the 8 CPUs of `verifier-cpu` (`reference/v0.1.yaml`) on `cpu-xl` (16 vCPU, 124 GB RAM, 1,000 GB disk, 1.00 USD/h; see Flavors above). The harness rejects hosts with fewer than 8 usable CPUs and logs a warning if memory falls below `verifier-cpu`'s 32 GiB. `cpu-performance` (32 vCPU, 256 GB RAM, 1,024 GB disk, 1.90 USD/h) also satisfies these needs at higher cost. Prover-side jobs run on `h200` under `prover-h200-hosted`, binding the same 8 verifier CPUs alongside 15 prover CPUs and fetching the 16.1 GB of weights. Before running any call, the harness rejects prover-side IDs on CPU-only hosts or on a GPU different from the run's machine record. Each part records its own host machine record (RFC-0006 fields only) and any unmet profile checks, and `merge` copies all parts into the stored run so every trial's timing stays linked to its host.

Estimated disk footprint (using the 44.6 GB proof from stage 2 plus `io/state` logged in stage 2) on `cpu-xl`'s 1,000 GB and `h200`'s 3,000 GB disks:

- **C6 job:** Copy of the run, one working copy per call, and five mutated proofs: roughly 312 GB plus `io/state`.
- **Other verifier-side jobs:** Under 140 GB plus `io/state`.
- **Prover-side jobs:** Copy of the run (44.6 GB plus `io/state`), the control's new proof (about 44.6 GB) and `io/state` copy, one verify working copy (44.6 GB), and 16.1 GB of weights: roughly 150 GB plus twice `io/state`.

### The jobs

Configure `R1` and the `ctl` helper once in the same shell as `iproofs_job`, using the stage 2 bucket folder (`hf buckets list "$NS/iproofs-dev-runs/runs" -h`):

```sh
R1=runs/<the stage 2 folder>/dev-results/v0.1/sash/<run id>
ctl() {  # FLAVOR TIMEOUT_SECONDS LABEL IDS: one part, reading the stored run through a read-only mount
  local EXTRA=(-v "hf://buckets/$NS/iproofs-dev-runs/$R1:/stored:ro" -e IPROOFS_STORED_DIR=/stored)
  iproofs_job "$1" "$2" "$SASH_IMAGE" "sash-ctl-$3" controls sash "$R1" "$4"
}
```

Each control job writes only to its own `runs/<UTC>-<label>/` folder while reading the stored run through `/stored:ro`. Hugging Face Jobs documents subfolder mounts for repositories and `:ro` for buckets ([jobs-configuration §Volumes](https://huggingface.co/docs/hub/jobs-configuration#volumes), read 2026-11-09); assuming bucket subfolders work the same way, remove `EXTRA` from `ctl` if the first job rejects the mount, and the script will fall back to reading from the read-write `/upload` mount without modifying it.

Requirements shared across all parts of a split suite (from SASH Level 1 session 3, 2026-11-12):

- **Single `IPROOFS_COMMIT`:** `merge` rejects parts with mismatched `harness_commit` values (SPLIT-4). If you fix a harness bug and rerun one part, either rerun every part at the new commit or rerun the remaining parts at the kept part's commit.
- **Perturbed commitment next to the stored run:** C3 and P1 expect `<release>/<system>/_controls/<workload>/` alongside the run folder in the bucket. Because a `:perturbed` session writes that directory into its own upload folder, copy it beside the kept-proof run before running controls. A P1 host regenerates W' via the adapter's `perturb` command and aborts if its digest does not match the recorded `model_digest`.
- **Level session suite:** A Level 1 session runs C1, C2, C3, and P1 (RFC-0018 CH-1) in four parts, with C1 taking the longest (three positions, three trials, each with its honest twin: roughly 5 h on `cpu-xl` for SASH 8B).
- **Quarantine void parts instead of deleting:** `merge` scans every `runs/*/controls/controls-part-<seed>-*.json`. Move any invalid part from a failed attempt into a `void-<reason>/` folder beside `controls/` inside its job folder rather than deleting it.

1. **Draw the seed once.** A small job draws the suite seed using the harness and saves it into the stored run (SPLIT-1). It refuses runs that already have a seed so it cannot be overwritten:

   ```sh
   iproofs_job cpu-basic 1800 "$SASH_IMAGE" sash-ctl-seed seed sash "$R1"
   ```

   The log finishes with `seed 0x<16 hex digits> written to .../controls-seed.json`. Record that seed in the campaign notes alongside `R1` and `IPROOFS_COMMIT`. Control jobs never take the seed on the command line; every job reads it from the stored record so a new shell, a sleeping laptop, or a rerun cannot alter it. If stage 1a showed that SASH's image does not fit in `cpu-basic`'s 50 GB disk, run both `seed` and `merge` on `cpu-xl` instead (cap 0.50 USD each).

2. **Wave 1 (launch concurrently once `seed` exits 0):**

   ```sh
   ctl cpu-xl 25200 c1 C1,C3,C4,C7
   ctl cpu-xl 25200 c2 C2
   ctl cpu-xl 25200 c5 C5
   ctl cpu-xl 25200 c8 C8
   ctl cpu-xl 61200 c6 C6
   ctl h200   34200 p-residual P1,P2,sash-unsound-skip-residual-stream
   ```

3. **Wave 2 (launch once `p-residual` completes its weakened prove):** Wait until `p-residual`'s log prints `controls prove sash-unsound-skip-residual-stream ... exit 0` (expected between 2.1 h and 3.9 h after startup). This confirms weakened proving works on `h200` before launching five more GPU jobs. If it exits non-zero, the part records `prover_failed`; stop and investigate (stop rule 4) instead of starting wave 2.

   ```sh
   ctl h200   34200 p-layer    sash-unsound-skip-layer-boundary
   ctl h200   34200 p-kv       sash-unsound-skip-kv-boundary
   ctl h200   34200 p-argmax   sash-unsound-skip-argmax
   ctl h200   34200 p-embed    sash-unsound-skip-embedding
   ctl h200   34200 p-lax      sash-unsound-argmax-lax
   ```

4. **Merge (once all eleven jobs have exited 0):**

   ```sh
   iproofs_job cpu-basic 1800 "$SASH_IMAGE" sash-ctl-merge merge sash "$R1"
   ```

   This job gathers every part matching the recorded seed under `runs/*/controls/` and writes `controls.json` beside `run.json` in the stored run, storing the individual parts under `controls-parts/`. It aborts without writing if any part mismatches the run, seed record, image, profile, verifier CPU count, or harness commit, if any control appears twice (indicating a duplicate job: stop and inspect), if any expected control is missing (listing the missing IDs), or if `controls.json` already exists. Sync the run folder locally with `hf buckets sync` to inspect the result. Note that any `accepted` outcome where rejection was expected triggers `disclosure_pending` (RFC-0008 §Disclosure); follow the disclosure procedure before quoting results from the file.

Every flavor uses the same pinned SASH image because `iproofs controls --hosted` rejects runs made with a different image, and SASH's verifier runs on the CPU (SIMD backend, `systems/sash/README.md` §verify). Hugging Face Jobs accepts `--timeout` in seconds, minutes, hours, or days (with `1d` in its examples) and documents neither a maximum timeout ([jobs-configuration §Timeout](https://huggingface.co/docs/hub/jobs-configuration#timeout), read 2026-11-09) nor a concurrency cap. Verify both during wave 1: if Jobs rejects the 17 h timeout or queues jobs unexpectedly, pause and check before launching more.

### Timeouts and costs

All durations below are assumptions derived from H100 records rather than measurements on these flavors:

- **Verify calls:** Assumed 3,600 s each (the H100 run's 8-CPU `verify` timed out at 3,600 s, making it a lower bound; see stage 2). Timeouts budget 9,000 s per call (2.5x).
- **Weakened prove:** Assumed 5,768 s (the H100 run's `prove` with kernel build, measured, tier reported, n = 1), or 9,229 s if CPU-bound by 24/15 (stage 2).
- **Startup overhead:** 600 s on `cpu-xl` (pull, clone, install) and 1,200 s on `h200` (adding binding check, self-test, and weights).
- **Bucket copy of the run (44.6 GB plus `io/state`):** 600 s at an assumed 75 MB/s read rate, or 3,600 s at 12.4 MB/s (undocumented by the provider; stage 1a gives an upper bound and each job logs its actual copy rate).
- **Buffer:** Each timeout includes 600 s for image pull, 900 s for upload, and headroom for a slow copy.

| Job | Flavor | Calls | Estimate (s) | Estimate (USD) | Timeout (s) | Cap (USD) |
|---|---|---|---|---|---|---|
| seed, merge (2 jobs) | `cpu-basic` | none | under 1,800 each | under 0.01 | 1,800 | 0.005 each, 0.01 |
| c1, c2, c5, c8 (4 jobs) | `cpu-xl` | 2 | 600 + 600 + 2 x 3,600 = 8,400, to 11,400 with slow copy | 2.33 to 3.17 each, 9.33 to 12.67 | 25,200 (600 + 3,600 + 2 x 9,000 + 1,500 = 23,700, rounded up to 7 h) | 7.00 each, 28.00 |
| c6 | `cpu-xl` | 6 | 600 + 600 + 6 x 3,600 = 22,800, to 25,800 | 6.33 to 7.17 | 61,200 (600 + 3,600 + 6 x 9,000 + 1,500 = 59,700, rounded up to 17 h) | 17.00 |
| p-residual, p-layer, p-kv, p-argmax, p-embed, p-lax (6 jobs) | `h200` | 2, after one prove | 1,200 + 600 + 5,768 + 2 x 3,600 = 14,768, to 21,229 with 24/15 prove and slow copy | 20.51 to 29.48 each, 123.07 to 176.91 | 34,200 (1,200 + 3,600 + 9,229 + 2 x 9,000 + 1,500 = 33,529, rounded up to 9.5 h) | 47.50 each, 285.00 |
| **total** | | | | **138.73 to 196.74**, plus under 0.01 for seed and merge | | **330.01** |

Wave 1 caps total 92.50 USD (estimate 36.18 to 49.32 USD), while wave 2's five jobs cap at 237.50 USD. Under these estimates, total wall time is roughly 6.3 to 9.8 h with the wave 2 gate (wave 1's `c6` takes 22,800 to 25,800 s; the gate clears at 7,568 to 14,029 s followed by wave 2's 14,768 to 21,229 s), or 6.3 to 7.2 h if all eleven jobs launch together, down from 30+ hours in a single job. Launching all eleven simultaneously saves wall time but exposes up to 237.50 USD of wave 2 caps to failures that wave 1 would catch.

Each completed control call prints a `control.call` progress line, so if a job produces no new log line for longer than one call's allowance (9,000 s, or 9,229 s plus copy time before the first prove line), treat it as stuck (stop rule 5). A job killed at its deadline writes no part (SPLIT-6), though its job log and uploaded `controls/logs/harness.jsonl` record the `seconds` of every call that finished. Use those measured durations to size the rerun timeout rather than retrying with the same limit. Each verify call can run up to the harness's 21,600 s per-call cap (`systems/sash/system.yaml` `timeouts_s`); on `cpu-xl`, setting the timeout to `600 + 3,600 + n x 21,600 + 1,500` s covers `n` calls at that ceiling (add 600 s and the prove duration on `h200`). Rerun the exact same `ctl` command with the higher timeout: because the seed comes from the stored record, the mutations stay identical. Log every attempt (stopped or finished) in the spend log, and leave stopped job folders in the bucket (AGENTS.md rule 5). Controls whose calls failed already record an `error` outcome in their part and do not need rerunning.

## Production serving from the engine image (RFC-0015 SRV-6)

The production-serving rows (`ref-serve`, owner decision of 2026-11-09) run vLLM v0.32.0 on the publisher's release with all weights resident in GPU memory, using hosted profiles `serving-h200x1-hosted` (Llama 3.1 8B BF16 on `h200`) and `serving-h200x4-hosted` (Llama 4 Maverick FP8 on `h200x4`) paired with `prover-h200-hosted` (RFC-0006 R6). Overhead divides the prover's GPU-seconds per token by these serving rows (RFC-0004 D-OVERHEAD-S). From `hf jobs hardware` (read 2026-11-09, provider list prices): `h200x4` provides 4x H200, 92 vCPU, and 1,024 GB RAM at 20.00 USD/h; `h200x8` provides 8x H200, 184 vCPU, and 2,048 GB RAM at 40.00 USD/h.

**Why start from the engine image:** On 2026-11-09, `ghcr.io` rejected anonymous pulls for `ai-verification-observatory/ref-serve` (`UNAUTHORIZED`, RFC-0015 Q6), and the pinned `ref-serve` image had been built for plain serving, causing the runner to reject it. By contrast, Docker Hub serves the upstream engine image publicly: `docker.io/vllm/vllm-openai@sha256:befccf0e...` resolved anonymously to a manifest list whose `linux/amd64` manifest is `sha256:6ee13335...` (40 layers, 9.21 GB compressed). Each job therefore starts from the vLLM image and installs the adapter from the pinned checkout ([`systems/ref-serve/dev_install.py`](../../systems/ref-serve/dev_install.py) via [`systems/_dev/install.py`](../../systems/_dev/install.py), RFC-0014 §Development install):

1. If `git` is missing from the image, the boot wrapper installs `git` and `ca-certificates` via `apt-get` (logging `git --version`; used only by the job script, never by the engine), then clones and checks out `IPROOFS_COMMIT`.
2. The vLLM image bundles `uv` (0.13.1 observed in the `linux/arm64` entry on 2026-11-09; the `linux/amd64` entry was not separately inspected, though the digest pins both), so `hf-job.sh` installs the harness without downloading `uv` and logs `uv --version`. Because the image sets `UV_OVERRIDE=/etc/uv-overrides.txt` and `UV_INDEX_STRATEGY=unsafe-best-match` for its own packages, `hf-job.sh` unsets both (along with `UV_CONSTRAINT`) before running `uv sync --frozen` so only locked versions are installed. The fallback download of `uv` 0.11.18 from GitHub releases (sha256-verified) runs only on images without `uv`.
3. After the binding check, `dev_install.py` verifies that the image matches the Dockerfile's `FROM` digest, checks that `import vllm` reports `0.32.0` and `VLLM_BUILD_COMMIT` is `5df63a72...`, and reads the image's `ENV` from its config by digest into `inputs.json` and `/opt/iproofs/image_env.json`. It rejects any extra `VLLM_*`, `NCCL_*`, `CUDA_*`, or `TORCH_*` environment variable injected by the job (apart from `CUDA_VISIBLE_DEVICES` and `CUDA_DEVICE_ORDER`), installs the entrypoint, `system.yaml`, and `write_inputs.py` in their Dockerfile locations, and runs a GPU readiness check under the hosted adapter's privilege drop (`iproofs.adapter.DROP_TO_ADAPTER`: UID 10001, no capabilities, no new privileges) with only bound GPUs visible. That check requires `torch` to see the exact bound GPU count with pairwise peer access, and on multi-GPU profiles spawns one process per GPU to join an NCCL group and all-reduce a small tensor (exercising tensor-parallel startup). On multi-GPU serving profiles, `hf-job.sh` then verifies `/dev/shm` against `shm_gib_min` (PC-SHM) and aborts before downloading weights if it is too small.
4. Before fetching full weights for a serving record, the first step fetches its non-weight files (`fetch-model --serving <record> --no-weights DIR`, verified per SM-2) and runs `dev_install.py --tokenizer-check DIR` offline under the same privilege drop to load the tokenizer (and processor for multimodal configs). This check would have caught Meta's malformed `special_tokens_map.json` on Maverick (which vLLM reads when `tokenizer_config.json` is missing); the serving record now omits that file (RFC-0015 Q7).
5. `fetch-model --serving <record>` downloads the remaining files from the ungated copy and verifies every sha256, byte size, and publisher git blob ID (RFC-0014 SM-2). No token is used unless the record lists a file directly from the publisher (RFC-0015 Q7: none currently). Subsequent steps in the same job skip the download and rely on the harness's startup rehash (RFC-0014).
6. Each run passes `--image <the engine image> --keep-io`, `--gpus` (all GPUs of the serving profile), and per-step `--load high` and `--prompts-from` pointing to the replayed prover run (`:high`, `:from=DIR`). Because `system.image` is recorded as `local/docker.io/vllm/vllm-openai@sha256:befccf0e...` (`digest_kind: config`, ineligible for release under RFC-0014) and serving profile drivers remain `unpinned` (RFC-0006 Q5), these runs stay outside `results/` (POL-4). The retained `io/` directory captures `engine.log`, `commands.jsonl` (launch command, engine environment, resolved configuration, and KV-capacity lines), and outputs, without duplicating weights (the adapter reads `/models` from cache).

Define the serving helper after [The job command](#the-job-command):

```sh
VLLM_IMAGE=docker.io/vllm/vllm-openai@sha256:befccf0e7e4089aa23926bb6f887a85c0d46c2a99e6de5c5ffdf5cb7957c5b34
BOOT_ENGINE='set -eu; command -v git >/dev/null || { apt-get update -qq &&
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends git ca-certificates >/dev/null; };
git --version; '"$BOOT"

iproofs_serving_job() {  # FLAVOR TIMEOUT_SECONDS PROFILE LABEL then hf-job.sh's arguments
  local flavor=$1 timeout=$2 profile=$3 label=$4; shift 4
  hf jobs run --detach --flavor "$flavor" --timeout "$timeout" --name "iproofs-$label" \
    --label "iproofs=$label" "${UPLOAD[@]}" \
    --secrets-file "$HOME/.config/iproofs/hf-job.secrets" -e IPROOFS_UPLOAD_BUCKET="$NS/iproofs-dev-runs" \
    -e IPROOFS_COMMIT="$IPROOFS_COMMIT" -e IPROOFS_JOB_BUDGET_S="$((timeout - 600))" \
    -e IPROOFS_LABEL="$label" -e IPROOFS_DEV_IMAGE="$VLLM_IMAGE" -e IPROOFS_PROFILE="$profile" \
    "$VLLM_IMAGE" -- bash -c "$BOOT_ENGINE" hf-job "$@"
}
```

Both helpers upload identically: the secrets file supplies `HF_TOKEN` and `IPROOFS_UPLOAD_BUCKET` specifies the destination bucket so `hf-job.sh` uploads `out/` via the bucket API with per-file size checks ([Uploads](#uploads-through-the-bucket-api-checked-2026-11-09)), while the mount in `UPLOAD` remains attached for reading replayed runs (`:from=`). Make sure `IPROOFS_COMMIT` includes this section's `hf-job.sh`, `systems/_dev/`, `systems/ref-serve/dev_install.py`, and RFC-0004 INV-SCOPE-5.

**S0, image preflight without a GPU** (`cpu-basic`, 15 min timeout, cap under 0.01 USD): Verify digest pulling, overriding `ENTRYPOINT` (`vllm serve`, which fails immediately with a usage message if not overridden), runtime UID, `import vllm`, presence of `git` and `uv`, `apt-get` connectivity, `/dev/shm` size, and any provider-injected engine environment variables:

```sh
hf jobs run --detach --flavor cpu-basic --timeout 15m --name iproofs-serving-s0 \
  -v "hf://buckets/$NS/iproofs-dev-runs:/upload" "$VLLM_IMAGE" -- \
  bash -c 'date -u; id -u; python3 -V; python3 -c "import vllm; print(vllm.__version__)";
           command -v git uv || true; df -h / /tmp /dev/shm; env | grep -E "^(VLLM|NCCL|CUDA|TORCH)_" | sort;
           apt-get update -qq && echo "apt: reachable";
           mkdir -p /upload/stage-1a && touch "/upload/stage-1a/uid-$(id -u)-vllm" && echo "upload: writable"'
```

If the `env` output contains any variable not already defined in the image's own `ENV` (check against `inputs.json` `image_env` from S1 or the registry config), every serving job will reject itself (`config`, SRV-3); stop and report it to the owner.

**S1, Llama 3.1 8B BF16 on `h200`** (TP1, `serving-h200x1-hosted`): Matched load, one repetition, replaying the completed SASH run from stage 2 (label `sash-c1024-r1` on `prover-h200-hosted`). Because the workload has batch size 1 and one batch per session, S1 serves SASH's single prompt (1,024 prompt tokens and 64 output tokens). That capture (`2026-11-09-ref-serve-sash-l31-8b-c1024-serving-h200x1-hosted-1`) recorded `prove.session` at 58.464736204 s (measured, tier reported, n = 1, development run), covering engine startup plus one request with no steady scope, so it cannot size `batches_per_session_run` (RFC-0015 SRV-1). Because SASH's steady scope is not externally observable, SASH's headline overhead is `D-OVERHEAD-WARM`: its proving session divided by production serving's steady scope (RFC-0004 INV-DERIVE-11), which requires a serving run with at least a 60 s steady scope (sized by S1b and measured by S1c). Locate the stage 2 run folder (ending in `-sash-c1024-r1` with `upload.done`) and launch S1:

```sh
hf buckets list "$NS/iproofs-dev-runs/runs" -h
hf buckets list "$NS/iproofs-dev-runs/runs/<UTC time>-sash-c1024-r1/dev-results/v0.1/sash" -h
SASH_RUN=runs/<UTC time>-sash-c1024-r1/dev-results/v0.1/sash/<date>-sash-sash-l31-8b-c1024-prover-h200-hosted-1
iproofs_serving_job h200 3600 serving-h200x1-hosted serving-l31-bf16-s1 \
  run ref-serve "sash-l31-8b-c1024:1:from=$SASH_RUN"
```

Before executing any step, `iproofs run` rejects any `from=` run that failed to complete or used a different workload version (`recorded_seed`). For S1 itself, the 1 h timeout caps spend at 5.00 USD; projected duration is roughly 1,096 s (0.30 h, 1.52 USD), comprising 600 s pull and install (assumed, as in stage 3), ~60 s to download 16.07 GB of weights (assumed), ~16 s for `fetch-model` hashing (1 GB/s, assumed), ~28 s for the run's rehash (scaled from 395 to 418 s for 232.1 GB, measured, tier reported, n = 6, stage 3 table), ~30 s for the pre-weight tokenizer check (assumed), 300 s for engine load and compile (assumed), and ~62 s for requests (assumed).

**S1b, sizing capture for Llama 3.1 8B BF16** (TP1, `serving-h200x1-hosted`, RFC-0015 SRV-1, resolving Q10): While the matched entry's `batches_per_session_run` is null, passing `sizing=50` invokes `iproofs run ... --sizing-batches 50`, running 50 batches of 1 (the SASH prompt first, followed by 49 additional windows from the same seeded generator so `prompt_prefix_digest` matches SASH's `prompt_set_digest`, SRV-8). The manifest sets `workload.sizing_capture: true`, and `run.json` records both "sizing capture: it sizes batches_per_session_run and joins no overhead (RFC-0015 SRV-1)" and "steady scope under 60 s". Sizing captures never enter overhead calculations (RFC-0004 INV-DERIVE-2 (f)).

```sh
iproofs_serving_job h200 3600 serving-h200x1-hosted serving-l31-bf16-size \
  run ref-serve "sash-l31-8b-c1024:1:sizing=50:from=$SASH_RUN"
```

Why 50 batches (projected, not yet measured on this profile): at batch size 1 on one H200, a single request processes 1,024 prompt tokens and 64 output tokens. Prefill takes roughly 0.04 s (16 GFLOP/token for 8B parameters times 1,024 tokens at an assumed 400 TFLOP/s), and 64 decode steps each stream 16.07 GB of weights (~3.3 ms/step at the H200's 4.8 TB/s, assumed ~6.5 ms/step with engine overhead, or 0.42 s total). Including request round-trip overhead gives roughly 0.5 s per request (assumed range 0.3 to 0.8 s), so 49 steady batches take ~25 s (range 15 to 40 s): long enough for serving time to dominate watcher granularity while adding minimal job cost. The 1 h timeout caps spend at 5.00 USD. Projected total duration is ~817 s (0.23 h, 1.13 USD): 600 s pull and install (assumed), ~60 s weight download and ~16 s hash (assumed, as in S1), ~28 s run rehash (as in S1), ~30 s tokenizer check (assumed), ~58 s for engine startup plus the first request (S1's `prove.session`, measured, n = 1), and ~25 s for the remaining 49 requests.

Compute the session batch count locally from the stored capture (CPU-only):

```sh
hf buckets list "$NS/iproofs-dev-runs/runs" -h   # the folder ending in -serving-l31-bf16-size
SIZE_RUN=runs/<UTC time>-serving-l31-bf16-size/dev-results/v0.1/ref-serve/<date>-ref-serve-sash-l31-8b-c1024-serving-h200x1-hosted-1
mkdir -p /tmp/size && for f in run.json manifest.json; do
  hf buckets cp "hf://buckets/$NS/iproofs-dev-runs/$SIZE_RUN/$f" "/tmp/size/$f"; done
uv run iproofs serving size-session /tmp/size
```

This prints `batches_per_session_run` (at a projected 0.5 s/request, 240 steady batches reach 120 s, yielding 241) along with the `system.yaml` snippet on stderr. Open a pull request updating the `sash-l31-8b-c1024` matched entry (with a comment citing the capture run ID, bucket folder, and command) and adding the capture's recorded values to `harness/tests/unit/test_session_size.py` so CI verifies the stored count matches the derivation (AGENTS.md rule 3).

**S1c, three matched repetitions of Llama 3.1 8B BF16** (TP1): Once that pull request merges and `IPROOFS_COMMIT` includes it, run three repetitions. Each serves `batches_per_session_run` batches of 1 (starting with SASH's prompt, SRV-8). Its steady rate supplies the serving denominator for SASH's `D-OVERHEAD-WARM`, while its session figure feeds `D-OVERHEAD-SESSION` (computed but not displayed, since the longer session amortizes engine startup across all requests, RFC-0015 Q10 (b)).

```sh
iproofs_serving_job h200 3600 serving-h200x1-hosted serving-l31-bf16-s3 \
  run ref-serve "sash-l31-8b-c1024:3:from=$SASH_RUN"
```

The 1 h timeout caps spend at 5.00 USD. Projected duration (at 241 batches) is ~1,324 s (0.37 h, 1.84 USD): ~706 s for pull, install, weights, hashing, and tokenizer check (as in S1b), plus ~28 s rehash, ~58 s startup and first request, and ~120 s for 240 additional requests per repetition. If any repetition finishes with a steady scope under 60 s, it carries the warning and is excluded from overhead calculations (SRV-1); review both the capture and the three runs with the owner before running further jobs.

**S2, Llama 4 Maverick FP8 on `h200x4`** (TP4, `serving-h200x4-hosted`): Matched load followed by high load, one repetition each, replaying a completed FlashProve b24 run from stage 4.3 (`fp-b24-r1` on `prover-h200-hosted`) executed at an `IPROOFS_COMMIT` with RFC-0004 INV-SCOPE-5 so `manifest.json` records `workload.steady_rule: "batch-membership"`. Any b24 run recorded before that rule is excluded from overhead calculations (INV-DERIVE-2 (f)) and rejected by `iproofs run` at batch size 24 (`config`, before fetching weights). If stage 4.3 ran on an older commit, rerun stage 4.3 at the new commit first (cap 35.00 USD). Verify `steady_rule` before launching S2:

```sh
hf buckets list "$NS/iproofs-dev-runs/runs" -h
hf buckets list "$NS/iproofs-dev-runs/runs/<UTC time>-fp-b24-r1/dev-results/v0.1/flashprove" -h
FP_B24_RUN=runs/<UTC time>-fp-b24-r1/dev-results/v0.1/flashprove/<date>-flashprove-fp-maverick-w1024-b24-prover-h200-hosted-1
hf buckets cp "hf://buckets/$NS/iproofs-dev-runs/$FP_B24_RUN/manifest.json" - |
  python3 -c 'import json, sys; print(json.load(sys.stdin)["workload"].get("steady_rule"))'  # batch-membership
iproofs_serving_job h200x4 10800 serving-h200x4-hosted serving-mav-fp8-s2 \
  run ref-serve "fp-maverick-w1024-b24:1:from=$FP_B24_RUN" "fp-maverick-w1024-b24:1:high:from=$FP_B24_RUN"
```

The matched step serves 214 batches of 24 (`batches_per_session_run`, derived by `iproofs serving size-session` from the first capture, RFC-0015 SRV-1): the prover's 120 prompts plus 5,016 additional windows from the same seeded generator, totaling 5,136 (up from 5 batches / 120 prompts prior to sizing). The high-load step serves 5 batches of 1,024: the prover's 120 prompts plus 5,000 additional windows from the same generator (SRV-8; workload properties, not results). The matched step feeds FlashProve's `D-OVERHEAD-S` (steady) and `D-OVERHEAD-SESSION`, while the high-load step feeds `D-OVERHEAD-HIGH-S`.

The 3 h timeout caps spend at 60.00 USD (3 h x 20.00 USD/h). Projected duration is ~5,536 s (1.54 h, 30.76 USD): 600 s pull and install (assumed), ~862 s to download 416.8 GB of weights (scaled from ~8 min for 232.1 GB, reported, n = 1), 417 s for `fetch-model` hashing (1 GB/s, assumed), ~30 s pre-weight tokenizer check (assumed), and per repetition ~731 s rehash (scaled as in S1), 900 s loading 397,449 MiB across 4 GPUs with compilation and CUDA graphs (assumed, unmeasured), and ~65 s for matched requests plus 300 s for high-load requests (5 x 1,024 x 1,025 tokens at an assumed 30,000 token/s). Because the second step reuses the first step's verified download, the files are read three times after download rather than four (once for `fetch-model` hash and once per repetition rehash).

**S2' (fallback only if every S2 attempt fails with `resource`):** If S2 fails with a KV-capacity or out-of-memory error, move to TP8 on `h200x8` (3 h timeout, cap 120.00 USD) after an amendment defines `serving-h200x8-hosted` and its `system.yaml` entries (RFC-0015 NM-1). Never move to TP8 for an `adapter` failure; fix the adapter bug and rerun S2 instead.

Combined spend for S0 through S2 (including S1b and S1c) is projected at ~35.26 USD (32.29 USD before S1b/S1c), with caps totaling 75.01 USD excluding S2', funded from whatever headroom the stop rule leaves. Every number produced here is a development figure and must be quoted with its scope, grade, tier `reported`, profile, flavor, n, and bucket folder (AGENTS.md rule 2). Full three-repetition campaigns per load point wait until the rebuilt `ref-serve` image is public and pinned and the driver is pinned (RFC-0006 Q5).

**RISK:** The vLLM image requires CUDA 13.0 (`NVIDIA_REQUIRE_CUDA=cuda>=13.0` in its `ENV`, read 2026-11-09). If the provider's driver cannot satisfy this requirement, `dev_install.py`'s GPU check fails within the first few minutes before downloading weights. Preserve the job log, report it to the owner, and modify neither the engine nor the adapter (AGENTS.md rule 1).

After each job finishes, inspect these artifacts in the bucket folder:

- `job.log`: `dev-install:` lines, CPU binding, and GPU readiness checks.
- `run.json`: `status`, `metrics`, `warnings`, `failure.kind`, and `failure.last_lines` (which end with the KV-capacity line on `resource` failures).
- `manifest.json`: `engine`, `serving_model`, `workload.prompt_prefix_digest`, `machine.gpu.unbound_samples`, `machine.container.shm_bytes`, and `machine.gpu.nvlink_active_links`.
- `io/commands.jsonl` and `io/engine.log`.

Use the initial captures to set `batches_per_session_run` (SRV-1: run `iproofs serving size-session RUN_DIR` against the matched run for a 120 s steady target above the 60 s floor; single-batch workloads are rejected and must use a sizing capture like S1b), establish the `PC-GPU-IDLE` baseline, check whether NVML reports NVLink state (`PC-GPU-LINK`), and commit the adapter's replay fixtures (including its stored resolved-configuration line) by pull request.

## Stop rule

Before launching any job and after each job finishes:

1. Check actual spend in [huggingface.co/settings/billing](https://huggingface.co/settings/billing) under Compute Usage (the billing authority), and cross-check against `hf jobs ps -a` and `hf jobs inspect <job id>` (billed minutes multiplied by the flavor's per-minute rate).
2. Log the job in the spend log below, including its pull duration (creation timestamp to first log line).
3. Launch the next job only if cumulative spend plus the new job's cap is at most 200.00 USD (or the dedicated budget set for stage 5). Otherwise stop and move the remaining work to the bare-metal node.
4. Pause and investigate before spending more whenever a job fails unexpectedly (a `FAIL` probe row, failed binding check, harness error, or exit code other than 0 or 4). Diagnose with a targeted probe (stage 1a or 1) rather than blindly retrying the full job. Never rerun a failed job to overwrite it; keep the failed record and treat any rerun as a new repetition (AGENTS.md rule 5).
5. Cancel any stalled job (`hf jobs cancel <job id>`) whose log stops advancing for longer than the longest estimated step rather than letting it burn through its full timeout. Note that cancelled jobs do not upload outputs, and their billed minutes still count against budget.
6. Never pass a weakening flag to make a job pass (AGENTS.md rule 4). Weakening flags are allowed only inside the registered controls of `--control-suite` and stage 5 `controls` jobs.

Keep the spend log in your campaign notes rather than in the repository, since job IDs and account names must never be committed (AGENTS.md rule 7):

```
| Date (UTC) | Stage | Flavor | Timeout | Pull (min) | Billed minutes | USD | Spent so far | Exit, outcome |
| 2026-11-09 | 1 sash probe | h200 | 20 min | 4 | 14 | 1.17 | 1.17 | 0, see probe.json |
```

(This row illustrates the format and is not a recorded result.)

## Where results live

- **Inside the running container:** Outputs write to `out/dev-results/<release>/<system>/<run id>/` under the work directory, alongside `out/dev-results/.selftest.json` and `out/dev-results/.archive/` (skipped on upload when using `keep-io`). Container storage is ephemeral and deleted on exit.
- **After exit:** Outputs live in the private bucket `<namespace>/iproofs-dev-runs` under `runs/<UTC time>-<label>/`. List runs with `hf buckets list <namespace>/iproofs-dev-runs/runs -h`, and download a folder with `hf buckets sync hf://buckets/<namespace>/iproofs-dev-runs/runs/<folder> <a directory outside the checkout>`. If using the dataset fallback (`<namespace>/iproofs-dev-runs-ds`), download with `hf download <namespace>/iproofs-dev-runs-ds --repo-type dataset --include 'runs/<folder>/*' --local-dir <a directory outside the checkout>`.
- **Entering `results/`:** Only via a results pull request. Because `prover-h200-hosted` does not yet pin a driver (RFC-0006 Q5), runs record `harness.nonconforming: true`, which does not block execution. RFC-0006 §Hosted execution permits hosted runs as their own configurations, provided they carry a passing hosted self-test to qualify for release (RFC-0014 §Eligibility).
- **Purpose:** These jobs catch H200-specific failures early (such as `KL.bin` rounding, memory limits, kernel compilation, and timeouts) and provide timing estimates for sizing the bare-metal campaign. Whenever quoting a number from these runs, include all required labels: scope, grade, tier `reported`, profile `prover-h200-hosted`, flavor, n, and source bucket folder (AGENTS.md rule 2).

## What never to post

- **Tokens:** Never put tokens in command lines, tracked files, issues, or logs. When using a bucket without the API uploader, no token enters the container; when using the secrets file or dataset fallback, `HF_TOKEN` stays exclusively in `~/.config/iproofs/hf-job.secrets` and is passed encrypted via `--secrets-file`.
- **Job IDs and account identifiers:** Never commit job IDs, account names, or namespaces to the repository (AGENTS.md rule 7); keep them in your local spend log and bucket. Do not link directly to Hugging Face job URLs either, as they embed the namespace and job ID. Under RFC-0014 §Goals, a run's `manifest.json` and public sources alone must suffice to reproduce it. Although the probe and machine record omit host names, addresses, and serials, inspect them before pasting any excerpt into an issue.
- **Weights and proofs:** Never commit model weights or proof bytes to the repository (AGENTS.md rule 8).
