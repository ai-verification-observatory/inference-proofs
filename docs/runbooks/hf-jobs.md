# Hugging Face Jobs

How the owner makes development runs of SASH (`sash-l31-8b-c1024`) and FlashProve (`fp-maverick-w1024-b1`, then `fp-maverick-w1024-b24`) on Hugging Face Jobs H200 containers, on the profile `prover-h200-hosted` ([RFC-0006 §H200 profiles](../../rfcs/0006-reference-hardware-and-cost.md#h200-profiles), [§Hosted execution](../../rfcs/0006-reference-hardware-and-cost.md#hosted-execution)), within a budget of 200 EUR, in stages. Official runs come later, on the bare-metal H200 node ([`h200-host.md`](h200-host.md)). Every run here is a development run: it stays out of `results/` (see [Where results live](#where-results-live)).

Hugging Face Jobs starts one container from a named image, with no docker engine inside, and bills it per minute while it is starting or running ([jobs-pricing](https://huggingface.co/docs/hub/jobs-pricing), read 2026-11-08). The harness's hosted mode (`iproofs run --hosted --gpu <index>`) is made for this. Each job runs [`hf-job.sh`](hf-job.sh) from a fresh clone of this repository at a pinned commit: host probe, harness install, binding check, hosted self-test, weights, runs, and a copy of everything it wrote to a private storage bucket mounted in the job.

## Flavors and who runs where

Provider list prices and sizes from `hf jobs hardware` and [jobs-configuration](https://huggingface.co/docs/hub/jobs-configuration) (read 2026-11-08; the provider's price, not this benchmark's cost basis, which is `costs.h200`, RFC-0006 C7):

| Flavor | GPUs | vCPU | RAM | Disk | USD per hour | USD per minute | Used for |
|---|---|---|---|---|---|---|---|
| `cpu-basic` | none | 2 | 16 GB | 50 GB | 0.01 | 0.0002 | stage 1a checks |
| `cpu-xl` | none | 16 | 124 GB | 1,000 GB | 1.00 | 0.0167 | stage 1a, if an image does not fit in 50 GB; stage 5's verifier-side jobs |
| `cpu-performance` | none | 32 | 256 GB | 1,024 GB | 1.90 | 0.0317 | not planned; it also meets stage 5's verifier-side needs (read 2026-11-09) |
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

Results leave each job through a private [storage bucket](https://huggingface.co/docs/hub/storage-buckets) mounted in the container (`-v hf://buckets/<namespace>/iproofs-dev-runs:/upload`; buckets mount read-write, [jobs-configuration §Volumes](https://huggingface.co/docs/hub/jobs-configuration#volumes)). `hf-job.sh` copies its output there. No token enters the container: the job runs on the owner's login, which owns the bucket. Buckets are billed by the amount stored above a free allowance ([hf.co/storage](https://huggingface.co/storage)); a FlashProve job leaves megabytes to a few hundred megabytes there (an assumption: logs, the records, and one proof archive per configuration, about 19 MB by upstream's average proof size). A SASH job leaves far more: the archive of its first accepted proof is 44,638,531,893 bytes (the H100 run's `manifest.json`, measured, n = 1), and a `keep-io` job (stage 2) uploads that proof once, in `io/proofs`, with `io/state` (size not recorded) and the commitment store, instead of the archive.

**Fallback, only if stage 1a shows the mounted bucket is not writable** by the job's user: a private dataset and a narrow token. Create the dataset first with your own login, since a token scoped to one repository cannot create it, then make a fine-grained token with write access to that dataset only, and paste it at a silent prompt so it never appears on a command line or in the shell history:

```sh
hf repos create <namespace>/iproofs-dev-runs-ds --type dataset --private
mkdir -p ~/.config/iproofs && chmod 700 ~/.config/iproofs
( umask 077; read -rs T && printf 'HF_TOKEN=%s\n' "$T" > ~/.config/iproofs/hf-job.secrets; unset T )
```

Jobs passes it to the container as an encrypted secret (`--secrets-file`). `hf-job.sh` uses it for the upload only; the harness, the adapter and `fetch-model` run without it (both models are ungated), and the hosted runner drops any name containing `TOKEN` from the adapter's environment. That keeps the token from the adapter only when the job runs as root, because the hosted runner then drops the adapter to uid 10001. If the job runs as the images' own user 10001 (stage 1a shows it), the adapter and the upstream prover run under the same uid as the job script and can read the token from `/proc/1/environ` (RFC-0006 Q6). The token's scope, write access to that one dataset, is then all that limits it.

## Uploads: through the bucket API, checked (2026-11-09)

On 2026-11-08 SASH's first run (`sash-c1024-r1`) completed with its proof accepted, but its run directory never reached the bucket: the copy into the mounted bucket returned in 38 s and the job ended while the mount was still sending its proof archive in the background, so the archive and everything queued behind it were dropped (the mount's own flush on shutdown is bounded, [hf-mount](https://github.com/huggingface/hf-mount) `--flush-shutdown-timeout-ms`, default 45 s; Jobs does not document its mount's write mode). Small outputs (FlashProve's 18 MB proofs) were not affected.

Every job now uploads through the bucket API when it has a token: `hf-job.sh` runs `hf buckets sync` (huggingface_hub 2.4.0) twice, the records first (no proof archive, no `io/`), then the rest, checks every file of `out/` against the bucket's listing by size, and only then writes `upload.done`. A failed sync or file check is tried again every 10 minutes (`IPROOFS_UPLOAD_RETRY_S`) until 30 minutes before the job's budget ends (`IPROOFS_UPLOAD_RETRY_STOP_S`), so a quota raised or a connection back meanwhile still gets the files out (two SASH keep-io uploads failed at once on a full storage quota, 2026-11-13). A failed or incomplete upload says so in the log. With `keep-io`, each proof goes up as soon as the adapter releases it (a directory under `io/proofs`, renamed into place, RFC-0005), into the job's folder, fixed at the start, under its final run id; the end-of-job sync then finds it there. Proof archives (`.tar`, a full copy of one proof) stay out unless `IPROOFS_UPLOAD_ARCHIVES=1`; with keep-io the proofs are in `io/proofs`.

What the owner sets up once: a dedicated, revocable token with write access, in a file only they can read:

```sh
mkdir -p ~/.config/iproofs && chmod 700 ~/.config/iproofs
( umask 077; printf 'HF_TOKEN=%s\n' '<token>' > ~/.config/iproofs/hf-job.secrets )
```

and every job command adds `--secrets-file ~/.config/iproofs/hf-job.secrets -e IPROOFS_UPLOAD_BUCKET=$NS/iproofs-dev-runs` (the mount may stay for reading stored runs). The token reaches the job as an encrypted secret and is never printed; the adapter and the prover run under the same uid in these images and could read it (RFC-0006 Q6), so it is a dedicated token, deleted after the campaign.

## The job command

Set once per shell. `IPROOFS_COMMIT` is the full hash of a commit on `main` that contains `docs/runbooks/hf-job.sh` (the merge of this change, or later); every job of a campaign uses the same one. `keep-io` and the `seed`, `controls` and `merge` modes exist only at or after the merge of the split-suite change, so the campaign's commit moves to that merge (or later) at stage 2, before any later job: stage 2, the stage 5 jobs and the stages after them use that one commit, whose `systems/sash/system.yaml` pins the image `SASH_IMAGE` names (`iproofs controls --hosted` refuses a run made with another image, and the merge refuses parts of another harness commit). Write it in the campaign notes. The stage 1 probe ran on an earlier commit; its findings about the flavor (GPU, NUMA, memory, disk, uid) still hold, and the stage 2 job repeats the probe, the binding check and the self-test at the new commit anyway.

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

The image digests are those of `systems/sash/system.yaml` and `systems/flashprove/system.yaml`; copy them from there if they have changed. The images' `ENTRYPOINT` is the adapter; Jobs runs the command given after the image instead, as its own example of `hf jobs run vllm/vllm-openai bash -c ...` shows ([jobs-images](https://huggingface.co/docs/hub/jobs-images)); stage 1a checks it. `--detach` prints the job ID; follow a job with `hf jobs logs -f <job id>`, check it with `hf jobs inspect <job id>`, and stop it with `hf jobs cancel <job id>`.

What happens inside, in order (`hf-job.sh`):

1. **Checkout.** Both images have `git`. As root the work directory is `/work`; as the images' own user (uid 10001, RFC-0006 Q6) it is `/tmp/iproofs`, the only place that user can write. The script stops if `HEAD` is not `IPROOFS_COMMIT`. It sets `HOME` and `HF_HOME` under the work directory (that user has no home directory), and logs whether the mounted bucket is writable.
2. **Probe.** `host-probe.py --profile prover-h200-hosted` (standard library only), into `out/probe.json`; the job goes on whatever it finds, so the record is complete. The bound GPU is the probe's `suggested_gpu_index`, or 0.
3. **Harness.** `uv sync --frozen --no-dev --extra gpu --extra fetch --extra prompts` from the checkout's `uv.lock`: NVML, `fetch-model` and `tokenizers`, which every run needs to build the workload's prompts from its `tokenizer.json`. The script then imports all three and stops if one is missing. Both images have Python 3.12.3 (Ubuntu 24.04's `python3`) and `uv` (0.11.18 in SASH's image, by its Dockerfile); FlashProve's also has `pip` 24.0, but Ubuntu's `pip` refuses to install into the system Python (PEP 668), so `uv` is used in both. The harness needs Python 3.12 or 3.13 (`pyproject.toml`).
4. **Binding check.** The CPUs `iproofs run --gpu` would bind on `prover-h200-hosted` (`GpuEnvironment`, RFC-0006 §CPU and memory selection). It fails when the GPU has no NUMA node or fewer than 15 usable CPUs sit on it; the manifest records the failure and the run goes on.
5. **Self-test.** `iproofs machine-record --hosted --selftest` (RFC-0011), into `out/selftest.json` and the results directory.
6. **Development install**, only with `IPROOFS_DEV_IMAGE` ([Production serving](#production-serving-from-the-engine-image-rfc-0015-srv-6)): `systems/<system>/dev_install.py` puts the adapter into the engine image the job started from and checks the engine, the environment and the bound GPUs, and the runs pass `--image` and `--keep-io`. A failed install or check stops the job before any weights are fetched.
7. **Weights.** `iproofs fetch-model <workload>`, under the same deadline as the runs: exactly the workload's files at the pinned revision, every sha256 and the model digest checked (RFC-0014), into `$IPROOFS_CACHE` under the work directory. No token is needed.
8. **Runs.** `iproofs run --system S --workload W --profile prover-h200-hosted --hosted --gpu <index> --provider "Hugging Face Jobs" --repetitions N --allow-nonconforming --results out/dev-results [--control-suite] [--keep-io]`, under `timeout` so it stops 15 minutes before the script's budget (60 minutes with `keep-io`, see stage 2). A run stopped there exits 124 or 137 and never reaches its final write, so its staging directory keeps `io/` (for FlashProve a copy of the weights), the scratch directories and the commitment store (for FlashProve the prover's secret key). The script deletes those before the upload, logging each one's size, and uploads the rest of the staging directory (its logs and `job.lock`). It is reported as a failed run with that exit code (AGENTS.md rule 5).
9. **Upload.** On every exit, `out/` (the job log, probe, self-test, run directories and proof archives) is copied to `runs/<UTC time>-<label>/` in the bucket: the log and the records first, then the self-test record and the run directories, then the proof archives (left out with `keep-io`, whose `io/proofs` holds the same proof; its digest stays in `digests.txt`), then the log again. A copy that ends without an error writes `upload.done` (the bytes sent) into the folder; the `seed`, `controls` and `merge` modes refuse a stored run whose folder has none, since its copy may be partial.

A STEP is `WORKLOAD:REPETITIONS`, with options after further colons: `controls` runs the control suite in the job (`--control-suite`), and `keep-io` keeps the completed run directory's `io/` (prompts, adapter outputs, state, proofs) and commitment store (`--keep-io`), so both are uploaded and a later `controls` job can run from the bucket (stage 5). The job log prints the size of each kept directory. `keep-io` is refused for FlashProve before the probe: its `io/` holds a copy of the weights and its commitment store the prover's secret key.

Three modes work on a stored run, `RUN_PATH` = `runs/<folder>/dev-results/<release>/SYSTEM/<run id>` in the mounted bucket ([RFC-0008 §Split suites](../../rfcs/0008-negative-controls.md#split-suites)). Each refuses, before the probe and the install: a missing bucket mount, another `RUN_PATH` form, a run without `run.json` and `manifest.json`, a folder without `upload.done`, and a run that already has `controls.json` (controls run once per configuration). The dataset fallback is not supported for them.

- `hf-job.sh seed SYSTEM RUN_PATH`: installs the harness only (no probe, GPU or self-test), runs `iproofs controls --draw-seed` on a copy of `run.json` and `manifest.json`, and writes the record, `controls-seed.json`, into the stored run. It refuses a run that has one: the seed is drawn once, by the harness, from `os.urandom` (SPLIT-1).
- `hf-job.sh reverify SYSTEM RUN_PATH [PROOF_ID]` (RFC-0018 CH-4a, `cpu-xl`, no GPU): every kept proof of the run verified again under the trace, about 1,500 s each for SASH; `reverify/` is written beside the stored run. With PROOF_ID, the run is copied without its other proofs and that proof alone is verified into a part in the job's `out/reverify-parts/`; one job per proof, then `iproofs reverify RUN_DIR --merge PART...` writes `reverify/` from the parts.
- `hf-job.sh controls SYSTEM RUN_PATH ID[,ID...]`: also refuses a run without `io/proofs`, `commitment/` (a run made without `keep-io`) or `controls-seed.json`, and an id that is not C1 to C8, P1, P2 or an `id:` of `systems/SYSTEM/controls.yaml`. Then steps 1 to 3; once the GPUs are counted, a prover-side id on a host without one is refused before the copy. With a GPU, steps 4 and 5 and `fetch-model` of the run's workload; without one the job is a verifier host and skips them. It copies the run directory to the job's disk (from `IPROOFS_STORED_DIR`, a read-only mount of the run, when set) and logs the bytes and seconds of that copy, runs `iproofs controls <copy> --hosted [--gpu <index>] --provider "Hugging Face Jobs" --only ID[,ID...] --seed <the recorded seed>` (the copy is never uploaded), and copies the part and the run's logs to `out/controls/`, which the upload sends with the small files. Each control call that returns prints a line (`controls verify C2 trial 0  <elapsed>  exit 0  <seconds> s`, the `control.call` event), so `hf jobs logs` shows progress. Exit 0: the part is written; 2: refused (for example a prover-side id on a verifier host, or a GPU other than the run's); 124 or 137: stopped at the deadline, no part.
- `hf-job.sh merge SYSTEM RUN_PATH`: installs the harness only, copies `run.json`, `manifest.json` and `controls-seed.json`, collects every part of the recorded seed under `runs/*/controls/`, runs `iproofs controls --merge`, and writes `controls.json` into the stored run, with the parts it merged under `controls-parts/<job folder>/` (they say which host measured which trial). It writes nothing when the merge refuses.

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
- The bucket's write and read speed, which no provider page states and stages 2 and 5 depend on. A third `cpu-basic` job measures it: `hf jobs run --detach --flavor cpu-basic --timeout 30m -v "hf://buckets/$NS/iproofs-dev-runs:/upload" "$SASH_IMAGE" -- bash -c 'mkdir -p /upload/stage-1a; date -u +%s; dd if=/dev/zero of=/upload/stage-1a/speed.bin bs=1M count=4096 conv=fsync; date -u +%s; dd if=/upload/stage-1a/speed.bin of=/dev/null bs=1M; date -u +%s; rm /upload/stage-1a/speed.bin'` (4 GiB through the mount, deleted at the end; cap 0.01 USD). Write both rates in the spend log with n = 1. The read follows the write at once and may come from the mount's local cache, so it is an upper bound; every stage 5 `controls` job logs the bytes and seconds of its own copy of the run, the read rate that matters. Stage 2 needs a write rate of 12.4 MB/s or more for its 3,600 s upload reserve; stage 5's estimates assume a read rate of 75 MB/s and its timeouts allow 12.4 MB/s (below).

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

One repetition, no controls in the job, its proofs kept for the control jobs of stage 5:

```sh
iproofs_job h200 43200 "$SASH_IMAGE" sash-c1024-r1 run sash sash-l31-8b-c1024:1:keep-io
```

Timeout 12 h (43,200 s): cap 12 h x 5.00 = 60.00 USD. With `keep-io` the script keeps 3,600 s for the upload instead of 900, so its runs must end by 39,000 s after it starts (43,200 less 600 and 3,600). The upload then holds the proof once: 1,639 parts and 44,638,531,893 bytes in the H100 run (`manifest.json` of the run named below, measured, n = 1), in `io/proofs`. The run also writes an uncompressed tar of that same proof under `.archive/` (RFC-0014, one proof per configuration), which with `keep-io` is not uploaded: otherwise the upload would be 89,277,063,786 bytes (twice the proof) plus `io/state` and need 24.8 MB/s for the same reserve. `io/state` (SASH's kernel build tree among it) and the commitment store go with the proof; no record states their size, so the job log prints the size of `io/`, `commitment/` and the left-out `.archive/`. 3,600 s is enough for the proof alone at a bucket write speed of 12.4 MB/s or more, an assumption until stage 1a measures it; if stage 1a measures less, raise this job's timeout by the difference before starting it. An upload that does not finish writes no `upload.done`, and every stage 5 job refuses that run before it is billed for long. The bucket bills that storage above its free allowance ([hf.co/storage](https://huggingface.co/storage)). If stage 2 already ran without `keep-io`, its proofs and commitment store are not in the bucket (the runner deletes them at the run's final write unless `--keep-io`, RFC-0010) and no control job can run from it; give `keep-io` to stage 4.2 instead and run stage 5 on that run. Estimate, from the one H100 record of this workload and SASH's files, all on an H100, none on an H200:

| Part | Seconds | Source |
|---|---|---|
| `commit` | 6,371 | between its state events, `results/v0.1/sash/2026-11-05-sash-sash-l31-8b-c1024-prover-h100-hosted-1` (measured, tier reported, n = 1; 24 prover CPUs under a 24.96-CPU quota). That run's status is `failed`: kind `timeout`, "verify exceeded 3600.0 s"; the `verify` limit has since been raised to 21,600 s (`systems/sash/system.yaml` `timeouts_s`) |
| `prove`, with the kernel build | 5,768 | same run |
| `verify` on 8 CPUs | 3,600 | a lower bound: the same run's `verify` was stopped at its 3,600 s limit. One development call of `boundary-grid --verify` took 3,381 s at about 3.9 CPUs (n = 1, `systems/sash/system.yaml`) |
| `verify.single_thread` on 1 CPU | 13,186 | assumption: the CPU time of that development call on one CPU, 3,381 s x 3.9; never measured |
| pull, clone, install, 16.1 GB of weights, self-test | 1,200 | assumption |
| **total** | **30,125** (8.37 h) | 8.37 h x 5.00 USD/h = 41.84 USD |

If `commit` and `prove` are CPU-bound and slow by 24/15 with 15 prover CPUs instead of 24 (an assumption the other way), they take 7,283 s more: 37,408 s (10.39 h), 51.96 USD. The deadline leaves 1,592 s above that for `verify` and `verify.single_thread` running longer than assumed (4,292 s without `keep-io`); beyond it the run is stopped at the deadline and recorded so. Issue #142 estimated about 7 h for a self-tested job on the H100.

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

**4.2 SASH: a second repetition on `h200`**, the same command as stage 2 with the label `sash-c1024-r2` and without `keep-io` (controls run once per configuration, RFC-0008), unless stage 2 did not complete with its proofs kept: cap 60.00 USD, estimate 41.84 to 51.96 USD.

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

- **C3 and P1 (perturbed weights).** `iproofs controls --prepare-perturbed` runs the adapter under docker only, so on Jobs no perturbed commitment exists and both controls report `not_applicable` (RFC-0008). They run on the bare-metal node.

## Stage 5: SASH's control suite in parallel jobs (estimate 138.73 to 196.74 USD, cap 330.01 USD)

Stage 5 is outside the 200 USD plan above: the owner sets its budget before the first job, and the stop rule applies with that figure in place of 200.00 USD. It runs SASH's whole control suite against the stage 2 run (or the first completed SASH run kept with `keep-io`), split by [RFC-0008 §Split suites](../../rfcs/0008-negative-controls.md#split-suites) into eleven jobs that run at the same time, instead of one job of 30 h or more, and merges their parts into the run's `controls.json`. Every control keeps its honest twin and its own seeded mutations, so the merged file is the one a single run with the same seed writes (INV-CTRL-7). FlashProve's suite stays inside its run job (stage 4.1, about 300 s of controls, an assumption there), and `keep-io` is refused for it (job command, above).

The suite (`systems/sash/controls.yaml`, RFC-0008) on a SASH run (one request, batch size 1, one proof):

| Controls | Side | Applicable on this run | Verify calls | Weights |
|---|---|---|---|---|
| C1, C2, C5, C8 | verifier | yes | 2 each: twin and trial | no |
| C6 | verifier | yes | 6: twin and five trials, in one part | no |
| C3 | verifier | no: no perturbed commitment on Jobs (below) | 0 | no; on a host that has one, C3 reads only its stored commitment record |
| C4, C7 | verifier | no: one request, and batch size 1 | 0 | no |
| P1, P2 | prover | no: no perturbed weights on Jobs; one precision | 0 | yes, resolved before the not-applicable check |
| the six `sash-unsound-*` controls | prover | yes | 2 each, after the control's prove: twin and the control's proof | yes: each proves again |

A verify call never sees the weights (RFC-0005: `verify` gets no `/models`), so the verifier-side jobs fetch none. A verifier-side job binds the 8 CPUs of `verifier-cpu` (`reference/v0.1.yaml`) on `cpu-xl`, 16 vCPU, 124 GB, 1,000 GB of disk, 1.00 USD per hour (provider list, Flavors above); the harness refuses a host with fewer than 8 usable CPUs, and records in the part a host with less memory than verifier-cpu's 32 GiB. `cpu-performance` (32 vCPU, 256 GB, 1,024 GB, 1.90 USD per hour, Flavors above) meets the same needs at a higher price. A prover-side job runs on `h200`, the run's profile `prover-h200-hosted`, binds the same 8 verifier CPUs beside its 15 prover CPUs, and fetches the 16.1 GB of weights. The harness refuses a prover-side id on a host without a GPU, and on a GPU other than the one in the run's machine record, before any call. Each part records its host's machine record (RFC-0006 fields only) and the profile checks it does not meet; the merge copies the parts into the stored run, so every trial's seconds keep their host.

Disk, from the 44.6 GB proof (stage 2) and the run's `io/state` (size in the stage 2 log), on the 1,000 GB of `cpu-xl` and the 3,000 GB of `h200`:

- the C6 job: the copy of the run, one call's copy at a time and five mutated proofs, about 312 GB plus `io/state`;
- the other verifier-side jobs: under 140 GB plus `io/state`;
- each prover-side job: the copy of the run (44.6 GB plus `io/state`), the control's own proof (about 44.6 GB) and its `io/state` copy, one verify call's copy (44.6 GB) and 16.1 GB of weights, about 150 GB plus twice `io/state`.

### The jobs

Set once, in the shell of the job command above, with the stage 2 folder (`hf buckets list "$NS/iproofs-dev-runs/runs" -h`):

```sh
R1=runs/<the stage 2 folder>/dev-results/v0.1/sash/<run id>
ctl() {  # FLAVOR TIMEOUT_SECONDS LABEL IDS: one part, reading the stored run through a read-only mount
  local EXTRA=(-v "hf://buckets/$NS/iproofs-dev-runs/$R1:/stored:ro" -e IPROOFS_STORED_DIR=/stored)
  iproofs_job "$1" "$2" "$SASH_IMAGE" "sash-ctl-$3" controls sash "$R1" "$4"
}
```

The jobs only write their own `runs/<UTC>-<label>/` folder; the stored run is read through `/stored:ro`. Jobs documents subfolder mounts for repositories and `:ro` for buckets ([jobs-configuration §Volumes](https://huggingface.co/docs/hub/jobs-configuration#volumes), read 2026-11-09); that a bucket subfolder mounts the same way is an assumption. If the first job refuses the mount, drop `EXTRA` from `ctl`: the script then reads the run through the read-write `/upload` mount and writes nothing to it.

What the parts of one suite must share, learned on SASH Level 1 session 3 (2026-11-12):

- **One `IPROOFS_COMMIT` for every part.** The merge refuses parts whose `harness_commit` differs (SPLIT-4). A part rerun after a harness fix means rerunning every part at the new commit, or rerunning the others at the commit of the part kept.
- **The perturbed commitment beside the stored run.** C3 and P1 read `<release>/<system>/_controls/<workload>/` next to the run's folder in the bucket; a session made with `:perturbed` writes it into its own upload folder, so copy it beside the run whose proofs were kept. A P1 host makes W' again with the adapter's `perturb` and P1 refuses unless its digest is the record's `model_digest`.
- **A level session's suite is C1, C2, C3 and P1** (RFC-0018 CH-1): four parts, C1 the longest (three positions, three trials, each with its twin: about 5 h on cpu-xl for SASH 8B).
- **A void part is moved, not deleted.** The merge reads every `runs/*/controls/controls-part-<seed>-*.json`; a part from a failed attempt goes to a `void-<reason>/` folder beside `controls/` in its job's folder.

1. **The seed, once.** One small job draws it with the harness and writes it into the stored run (SPLIT-1). It refuses a run that already has one, so it cannot be drawn again:

   ```sh
   iproofs_job cpu-basic 1800 "$SASH_IMAGE" sash-ctl-seed seed sash "$R1"
   ```

   Its log ends with `seed 0x<16 hex digits> written to .../controls-seed.json`. Write that value in the campaign notes with `R1` and `IPROOFS_COMMIT`. No job takes the seed as an argument: each reads it from the record, so a new shell, a laptop that slept, or a rerun cannot change it. If stage 1a showed the SASH image does not fit in `cpu-basic`'s 50 GB, use `cpu-xl` for this job and for the merge (cap 0.50 USD each).

2. **Wave 1**, all at once, once the seed job has exited 0:

   ```sh
   ctl cpu-xl 25200 c1 C1,C3,C4,C7
   ctl cpu-xl 25200 c2 C2
   ctl cpu-xl 25200 c5 C5
   ctl cpu-xl 25200 c8 C8
   ctl cpu-xl 61200 c6 C6
   ctl h200   34200 p-residual P1,P2,sash-unsound-skip-residual-stream
   ```

3. **Wave 2**, once p-residual's log shows its weakened prove returned: a line `controls prove sash-unsound-skip-residual-stream ... exit 0`, between about 2.1 h and 3.9 h after it starts on the estimates below. That line shows a weakened prove works on this flavor before five more H200 jobs start; an exit other than 0 there is recorded as `prover_failed` in the part, and is a reason to stop and look (stop rule 4), not a reason to start wave 2.

   ```sh
   ctl h200   34200 p-layer    sash-unsound-skip-layer-boundary
   ctl h200   34200 p-kv       sash-unsound-skip-kv-boundary
   ctl h200   34200 p-argmax   sash-unsound-skip-argmax
   ctl h200   34200 p-embed    sash-unsound-skip-embedding
   ctl h200   34200 p-lax      sash-unsound-argmax-lax
   ```

4. **The merge**, once all eleven have exited 0:

   ```sh
   iproofs_job cpu-basic 1800 "$SASH_IMAGE" sash-ctl-merge merge sash "$R1"
   ```

   It merges every part of the recorded seed under `runs/*/controls/` and writes `controls.json` into the stored run, beside its `run.json`, with the parts under `controls-parts/`. It refuses, and writes nothing, on parts of another run, seed record, image, profile, verifier CPU count or harness commit, a control in two parts (a job run twice to completion: stop and look), a control in no part (its message names the missing ids), and a run that already has `controls.json`. `hf buckets sync` that run folder to read the file. An `accepted` outcome where rejection is expected sets `disclosure_pending` (RFC-0008 §Disclosure): follow that section before quoting anything from the file.

The job image is the pinned SASH image on every flavor: `iproofs controls --hosted` refuses a run made with another image, and the verifier runs on the CPU (SIMD backend, `systems/sash/README.md` §verify). Jobs documents `--timeout` in seconds, minutes, hours or days, with `1d` among its examples, and states no maximum ([jobs-configuration §Timeout](https://huggingface.co/docs/hub/jobs-configuration#timeout), read 2026-11-09); it states no limit on concurrent jobs either. Check both with the first wave: if Jobs refuses a 17 h timeout or queues jobs, stop and look before starting more.

### Timeouts and costs

Every duration here is an assumption from H100 records, none measured on these flavors:

- a verify call takes 3,600 s (the H100 run's `verify` on 8 CPUs was stopped at its 3,600 s limit, a lower bound, stage 2), and the timeouts allow 9,000 s per call (2.5 times that);
- a weakened prove takes 5,768 s (the H100 run's `prove`, with the kernel build, measured, tier reported, n = 1), or 9,229 s if CPU-bound by 24/15 (stage 2);
- the pull, clone and install take 600 s on `cpu-xl`, and 1,200 s on `h200` with the binding check, self-test and weights;
- the copy of the run (44.6 GB plus `io/state`) from the bucket takes 600 s at an assumed read rate of 75 MB/s, or 3,600 s at 12.4 MB/s; the provider states no rate, stage 1a gives an upper bound and each job logs its own;
- each timeout adds 600 s for the pull and 900 s for the upload, and allows the slow copy.

| Job | Flavor | Calls | Estimate (s) | Estimate (USD) | Timeout (s) | Cap (USD) |
|---|---|---|---|---|---|---|
| seed, merge (2 jobs) | `cpu-basic` | none | under 1,800 each | under 0.01 | 1,800 | 0.005 each, 0.01 |
| c1, c2, c5, c8 (4 jobs) | `cpu-xl` | 2 | 600 + 600 + 2 x 3,600 = 8,400, to 11,400 with the slow copy | 2.33 to 3.17 each, 9.33 to 12.67 | 25,200 (600 + 3,600 + 2 x 9,000 + 1,500 = 23,700, rounded up to 7 h) | 7.00 each, 28.00 |
| c6 | `cpu-xl` | 6 | 600 + 600 + 6 x 3,600 = 22,800, to 25,800 | 6.33 to 7.17 | 61,200 (600 + 3,600 + 6 x 9,000 + 1,500 = 59,700, rounded up to 17 h) | 17.00 |
| p-residual, p-layer, p-kv, p-argmax, p-embed, p-lax (6 jobs) | `h200` | 2, after one prove | 1,200 + 600 + 5,768 + 2 x 3,600 = 14,768, to 21,229 with the 24/15 prove and the slow copy | 20.51 to 29.48 each, 123.07 to 176.91 | 34,200 (1,200 + 3,600 + 9,229 + 2 x 9,000 + 1,500 = 33,529, rounded up to 9.5 h) | 47.50 each, 285.00 |
| **total** | | | | **138.73 to 196.74**, and under 0.01 for seed and merge | | **330.01** |

Wave 1 caps total 92.50 USD (estimate 36.18 to 49.32 USD); wave 2's five jobs 237.50 USD. On these estimates the suite's wall time is about 6.3 to 9.8 h with the wave 2 gate (wave 1's c6 at 22,800 to 25,800 s; the gate at 7,568 to 14,029 s plus a wave 2 job of 14,768 to 21,229 s), or 6.3 to 7.2 h with every job started at once, against 30 h or more in one job. Starting all eleven at once is faster and risks up to 237.50 USD of wave 2 caps on a failure wave 1 would have shown.

A part prints one line per control call that returns (the `control.call` event), so a job whose log has had no new line for longer than one call's timeout allowance (9,000 s, or 9,229 s plus the copy before the first prove line) is stuck (stop rule 5). A job stopped at its deadline writes no part (SPLIT-6). Its job log and its uploaded `controls/logs/harness.jsonl` hold the `seconds` of every call that finished: size the rerun's timeout from them, never rerun with the same timeout. Each call may take up to the harness's own limit, 21,600 s per verify call (`systems/sash/system.yaml` `timeouts_s`); on `cpu-xl` a timeout of 600 + 3,600 + n x 21,600 + 1,500 s covers n calls at that limit (on `h200` add 600 s and the prove). Rerun the same `ctl` line with the new timeout: the seed comes from the record, so the mutations are the same bytes. List every attempt, stopped or finished, in the spend log; the stopped job's folder stays in the bucket (AGENTS.md rule 5). A control whose call failed has its `error` outcome in its part and is not rerun.

## Production serving from the engine image (RFC-0015 SRV-6)

The production-serving rows (`ref-serve`, owner decision of 2026-11-09): vLLM v0.32.0 serving the publisher's release with every weight in GPU memory, on the hosted serving profiles `serving-h200x1-hosted` (Llama 3.1 8B BF16, `h200`) and `serving-h200x4-hosted` (Llama 4 Maverick FP8, `h200x4`), which pair with `prover-h200-hosted` (RFC-0006 R6). The overhead divides the prover's GPU-seconds per token by these rows' (RFC-0004 D-OVERHEAD-S). Flavors from `hf jobs hardware` (owner's reading of 2026-11-09, the provider's price): `h200x4` is 4x H200, 92 vCPU, 1,024 GB, 20.00 USD/h; `h200x8` is 8x H200, 184 vCPU, 2,048 GB, 40.00 USD/h.

**Why from the engine image.** On 2026-11-09 ghcr.io refused an anonymous pull token for `ai-verification-observatory/ref-serve` (`UNAUTHORIZED`; RFC-0015 Q6), and the pinned `ref-serve` image was built for plain serving, so the runner refuses a job on it. The engine image is public on Docker Hub: `docker.io/vllm/vllm-openai@sha256:befccf0e...` resolved anonymously to a manifest list whose `linux/amd64` manifest is `sha256:6ee13335...` (40 layers, 9.21 GB compressed). The job starts from it and installs the adapter from the pinned checkout ([`systems/ref-serve/dev_install.py`](../../systems/ref-serve/dev_install.py) on [`systems/_dev/install.py`](../../systems/_dev/install.py), RFC-0014 §Development install):

1. The job command installs `git` with `apt-get` when the image has none (the log prints its version; used by the job script only, never by the engine), then clones and checks out `IPROOFS_COMMIT`.
2. The vLLM image ships its own `uv` (0.13.1, read in the image's `linux/arm64` entry on 2026-11-09; the `linux/amd64` entry the job runs was not read; the digest pins both), so `hf-job.sh` downloads nothing and installs the harness with it; `job.log` records `uv --version`. The image's ENV sets `UV_OVERRIDE=/etc/uv-overrides.txt` and `UV_INDEX_STRATEGY=unsafe-best-match` for its own packages; `hf-job.sh` unsets both (and `UV_CONSTRAINT`) for the harness's `uv sync --frozen`, which installs the lock file's versions only. uv 0.11.18 from its GitHub release (sha256 checked) is installed only for an image without `uv`.
3. After the binding check, `dev_install.py` refuses an image other than the Dockerfile's `FROM`; checks `import vllm` reports 0.32.0 and the image ENV's `VLLM_BUILD_COMMIT` is `5df63a72...`; reads the image's ENV from its config by digest, records it in `inputs.json` and `/opt/iproofs/image_env.json`, and refuses any `VLLM_*`, `NCCL_*`, `CUDA_*` or `TORCH_*` variable the job sets beyond it (other than `CUDA_VISIBLE_DEVICES` and `CUDA_DEVICE_ORDER`); puts the entrypoint, `system.yaml` and `write_inputs.py` where the Dockerfile puts them; and, under the hosted adapter's own privilege drop (`iproofs.adapter.DROP_TO_ADAPTER`: uid 10001, no capabilities, no new privileges) with only the bound GPUs visible, requires torch to see exactly that many GPUs with peer access between each pair, and with several GPUs one process per GPU to join an NCCL group and all-reduce a small tensor (the multi-process start of a tensor-parallel engine). On a serving profile of more than one GPU, `hf-job.sh` then compares `/dev/shm` with the profile's `shm_gib_min` (PC-SHM) and stops before any weights if it falls short.
4. Before a record's weights, the first step that uses it fetches its files without the weights (`fetch-model --serving <record> --no-weights DIR`, each file checked as SM-2 checks it) and `dev_install.py --tokenizer-check DIR` loads the engine's tokenizer from them, and the processor for a multimodal config, under the same drop and offline. It would have caught Meta's `special_tokens_map.json` for Maverick, which is not valid JSON and which the engine reads when `tokenizer_config.json` is absent; the record leaves that file out (RFC-0015 Q7).
5. `fetch-model --serving <record>` fetches the record's files from the ungated copy and checks every sha256, size and the publisher's git blob ids (RFC-0014 SM-2); no token reaches it unless the record lists a file from the publisher (RFC-0015 Q7: none today). A later step of the same job on the same record skips it: the run rehashes the files at its start (RFC-0014).
6. Every run passes `--image <the engine image> --keep-io`, `--gpus` (every GPU of the serving profile), and, per step, `--load high` and `--prompts-from` the prover run it replays (`:high`, `:from=DIR`). The run records `system.image` as `local/docker.io/vllm/vllm-openai@sha256:befccf0e...` with `digest_kind: config`, so it is never eligible for a release (RFC-0014), and every serving profile's driver is `unpinned` (RFC-0006 Q5), so it stays out of `results/` (POL-4). Its kept `io/` holds `engine.log`, `commands.jsonl` (the command, the engine environment, the resolved-configuration and KV-capacity lines) and the outputs, and no weights (the adapter reads `/models` from the cache).

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
    --secrets-file "$HOME/.config/iproofs/hf-job.secrets" -e IPROOFS_UPLOAD_BUCKET="$NS/iproofs-dev-runs" \
    -e IPROOFS_COMMIT="$IPROOFS_COMMIT" -e IPROOFS_JOB_BUDGET_S="$((timeout - 600))" \
    -e IPROOFS_LABEL="$label" -e IPROOFS_DEV_IMAGE="$VLLM_IMAGE" -e IPROOFS_PROFILE="$profile" \
    "$VLLM_IMAGE" -- bash -c "$BOOT_ENGINE" hf-job "$@"
}
```

Both helpers upload the same way: the secrets file gives the job `HF_TOKEN` and `IPROOFS_UPLOAD_BUCKET` names the bucket, so `hf-job.sh` sends `out/` through the bucket API and checks it file by file ([Uploads](#uploads-through-the-bucket-api-checked-2026-11-09)); the mount in `UPLOAD` stays, for reading the replayed run (`:from=`). `IPROOFS_COMMIT` must contain this section's `hf-job.sh`, `systems/_dev/` and `systems/ref-serve/dev_install.py`, and RFC-0004 INV-SCOPE-5 (the merge of that change, or later).

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

**S1, Llama 3.1 8B BF16 on `h200`** (TP1, `serving-h200x1-hosted`), matched load, one repetition, replaying the completed SASH run of stage 2 (label `sash-c1024-r1`, on `prover-h200-hosted`). The workload has batch size 1 and one batch a session, so S1 serves the SASH run's one prompt: 1,024 prompt tokens and 64 output tokens. Its capture (`2026-11-09-ref-serve-sash-l31-8b-c1024-serving-h200x1-hosted-1`) recorded `prove.session` 58.464736204 s (measured, tier reported, n = 1, development run), engine start-up and one request together, and no steady scope, so it sizes nothing (RFC-0015 SRV-1). SASH's steady scope is not externally observable, so SASH's headline overhead is D-OVERHEAD-WARM: its proving session over production serving's steady scope (RFC-0004 INV-DERIVE-11). That needs a serving run with a steady scope of at least 60 s, which S1b sizes and S1c makes. Find the run: its folder ends in `-sash-c1024-r1` and holds `upload.done`, and its run directory is the one SASH run under it:

```sh
hf buckets list "$NS/iproofs-dev-runs/runs" -h
hf buckets list "$NS/iproofs-dev-runs/runs/<UTC time>-sash-c1024-r1/dev-results/v0.1/sash" -h
SASH_RUN=runs/<UTC time>-sash-c1024-r1/dev-results/v0.1/sash/<date>-sash-sash-l31-8b-c1024-prover-h200-hosted-1
iproofs_serving_job h200 3600 serving-h200x1-hosted serving-l31-bf16-s1 \
  run ref-serve "sash-l31-8b-c1024:1:from=$SASH_RUN"
```

`iproofs run` refuses, before any step, a `from=` run that did not complete or ran another workload version (`recorded_seed`).

**S1b, the sizing capture of Llama 3.1 8B BF16** (TP1, `serving-h200x1-hosted`, RFC-0015 SRV-1, resolving Q10): the matched entry's `batches_per_session_run` is null, so the step option `sizing=50` runs `iproofs run ... --sizing-batches 50`: 50 batches of 1, the SASH run's prompt first, then 49 further windows of the same seeded generator (`prompt_prefix_digest` equals the SASH run's `prompt_set_digest`, SRV-8). The manifest records `workload.sizing_capture: true` and run.json warns "sizing capture: it sizes batches_per_session_run and joins no overhead (RFC-0015 SRV-1)"; it also carries "steady scope under 60 s". It joins no overhead (RFC-0004 INV-DERIVE-2 (f)).

```sh
iproofs_serving_job h200 3600 serving-h200x1-hosted serving-l31-bf16-size \
  run ref-serve "sash-l31-8b-c1024:1:sizing=50:from=$SASH_RUN"
```

Why 50 (projected, never measured on this profile): one request is 1,024 prompt tokens and 64 generated at batch 1 on one H200. The prefill is about 0.04 s (16 GFLOP a token for 8B parameters, times 1,024 tokens, at an assumed 400 TFLOP/s); the 64 decode steps read the 16.07 GB of weights once each, about 3.3 ms a step at the H200's 4.8 TB/s, so about 6.5 ms a step assumed with the engine's overheads, 0.42 s; with the request round trip, about 0.5 s a request (assumed range 0.3 to 0.8 s). The steady scope covers 49 batches: about 25 s (range 15 to 40 s), well above a second, so the sizing reads a time per batch dominated by serving rather than by the watcher's granularity, and the requests add about 25 s to the job. Timeout 1 h: cap 1 h x 5.00 = 5.00 USD. Estimate (projected): pull and install 600 s (assumed); weights about 60 s and their hash about 16 s (assumed, as S1); the run's rehash about 28 s (as S1); the tokenizer check about 30 s (assumed); engine start-up with the first request about 58 s (S1's `prove.session`, measured, n = 1); the other 49 requests about 25 s: about 817 s (0.23 h), 1.13 USD.

Then size the session from the stored capture, on any machine with the repository (CPU only):

```sh
hf buckets list "$NS/iproofs-dev-runs/runs" -h   # the folder ending in -serving-l31-bf16-size
SIZE_RUN=runs/<UTC time>-serving-l31-bf16-size/dev-results/v0.1/ref-serve/<date>-ref-serve-sash-l31-8b-c1024-serving-h200x1-hosted-1
mkdir -p /tmp/size && for f in run.json manifest.json; do
  hf buckets cp "hf://buckets/$NS/iproofs-dev-runs/$SIZE_RUN/$f" "/tmp/size/$f"; done
uv run iproofs serving size-session /tmp/size
```

It prints `batches_per_session_run` (at 0.5 s a request, projected: 240 steady batches reach 120 s, so 241) and, on stderr, the `system.yaml` line. Set it in the `sash-l31-8b-c1024` matched entry, with a comment naming the capture's run id, its bucket folder and the command, and add the capture to `harness/tests/unit/test_session_size.py` with its recorded values, by pull request (the test checks the stored count is the computed one, AGENTS.md rule 3).

**S1c, three matched repetitions of Llama 3.1 8B BF16** (TP1), after that pull request is merged and `IPROOFS_COMMIT` contains it: each repetition serves `batches_per_session_run` batches of 1, the SASH run's prompt first (SRV-8), and its steady figure is the serving side of SASH's D-OVERHEAD-WARM. Its session figure feeds D-OVERHEAD-SESSION, computed and not displayed: the lengthened session spreads the engine's start-up over every request it serves (RFC-0015 Q10 (b)).

```sh
iproofs_serving_job h200 3600 serving-h200x1-hosted serving-l31-bf16-s3 \
  run ref-serve "sash-l31-8b-c1024:3:from=$SASH_RUN"
```

Timeout 1 h: cap 5.00 USD. Estimate (projected, at the projected count of 241): pull, install, weights, hash and tokenizer check about 706 s (as S1b); per repetition the rehash about 28 s, start-up and the first request about 58 s, and 240 further requests about 120 s: about 1,324 s (0.37 h), 1.84 USD. A repetition whose steady scope falls under 60 s carries the warning and joins nothing (SRV-1): then put the capture and the three runs to the owner before any further job.

Timeout 1 h: cap 1 h x 5.00 = 5.00 USD. Estimate (projected): pull and install 600 s (assumed, as stage 3); weights 16.07 GB, about 60 s (assumed); `fetch-model`'s hash about 16 s (1 GB/s, assumed); the run's rehash about 28 s (scaled from the 395 to 418 s for 232.1 GB, measured, tier reported, n = 6, stage 3 table); engine load and compile 300 s (assumed); requests about 62 s (assumed); the tokenizer check before the weights about 30 s (assumed): about 1,096 s (0.30 h), 1.52 USD.

**S2, Llama 4 Maverick FP8 on `h200x4`** (TP4, `serving-h200x4-hosted`), matched then high load, one repetition each, replaying a completed FlashProve b24 run made with this harness: stage 4.3 (label `fp-b24-r1`, on `prover-h200-hosted`) run at an `IPROOFS_COMMIT` that contains RFC-0004 INV-SCOPE-5, so that its `manifest.json` records `workload.steady_rule: "batch-membership"`. A b24 run recorded before the rule joins no overhead (INV-DERIVE-2 (f)), and `iproofs run` refuses to replay one at batch size 24 (`config`, before any step or weight); if stage 4.3 ran at an earlier commit, run it again at this one first (its command, cap 35.00 USD). Find the run and check the rule before starting the job:

```sh
hf buckets list "$NS/iproofs-dev-runs/runs" -h
hf buckets list "$NS/iproofs-dev-runs/runs/<UTC time>-fp-b24-r1/dev-results/v0.1/flashprove" -h
FP_B24_RUN=runs/<UTC time>-fp-b24-r1/dev-results/v0.1/flashprove/<date>-flashprove-fp-maverick-w1024-b24-prover-h200-hosted-1
hf buckets cp "hf://buckets/$NS/iproofs-dev-runs/$FP_B24_RUN/manifest.json" - |
  python3 -c 'import json, sys; print(json.load(sys.stdin)["workload"].get("steady_rule"))'  # batch-membership
iproofs_serving_job h200x4 10800 serving-h200x4-hosted serving-mav-fp8-s2 \
  run ref-serve "fp-maverick-w1024-b24:1:from=$FP_B24_RUN" "fp-maverick-w1024-b24:1:high:from=$FP_B24_RUN"
```

The matched step serves 214 batches of 24 (`batches_per_session_run`, computed by `iproofs serving size-session` from the first capture, RFC-0015 SRV-1): the prover's 120 prompts plus 5,016 further windows of the same seeded generator, 5,136 in all (5 batches, 120 prompts, before it was set); the high-load step serves 5 batches of 1,024: the prover's 120 prompts plus 5,000 further windows of the same seeded generator (SRV-8; workload facts, not results). The matched step's figures feed FlashProve's D-OVERHEAD-S (steady) and D-OVERHEAD-SESSION; the high-load step's, D-OVERHEAD-HIGH-S.

Timeout 3 h: cap 3 h x 20.00 = 60.00 USD. Estimate (projected): pull and install 600 s (assumed); weights 416.8 GB, about 862 s (scaled from about 8 min for 232.1 GB, reported, n = 1); `fetch-model`'s hash 417 s (1 GB/s, assumed); per repetition the rehash about 731 s (scaled as in S1), loading 397,449 MiB to 4 GPUs with compilation and CUDA graphs 900 s (assumed, never measured), requests about 65 s matched and 300 s high (5 x 1,024 x 1,025 tokens at an assumed 30,000 token/s); the tokenizer check before the weights about 30 s (assumed): about 5,536 s (1.54 h), 30.76 USD. The second step skips `fetch-model` (the first step fetched and checked the files) and the run's own rehash checks them again, so the files are read three times after the download, not four.

**S2', only if every S2 attempt failed `resource`** with the KV-capacity line (or an out-of-memory) as evidence: the same content at TP8 on `h200x8` (timeout 3 h, cap 120.00 USD), after an amendment declares `serving-h200x8-hosted` and its `system.yaml` entries (RFC-0015 NM-1). An `adapter` failure never moves the count: fix it and rerun S2.

S0 to S2 with S1b and S1c: about 35.26 USD projected (32.29 before them), caps 75.01 USD, before S2'. The owner allots them from what the stop rule below leaves. Every figure from these jobs is a development figure: quote it with its scope, grade, tier `reported`, the profile, the flavor, n and the bucket folder (AGENTS.md rule 2). The repetitions for figures (three per load point) wait until the rebuilt `ref-serve` image is public and pinned and a driver pin exists (RFC-0006 Q5).

RISK: the engine image is built on CUDA 13.0 (`NVIDIA_REQUIRE_CUDA=cuda>=13.0` in its ENV, read 2026-11-09). If the provider's driver cannot run it, `dev_install.py`'s GPU check fails within the job's first minutes, before the weights: keep the job's log, put it to the owner, and change neither the engine nor the adapter (AGENTS.md rule 1).

Read afterwards, in the bucket folder: `job.log` (the `dev-install:` lines, the binding, the GPU check), the run directory's `run.json` (`status`, `metrics`, `warnings`, `failure.kind` and `failure.last_lines`, which end with the KV-capacity line for a `resource` failure), `manifest.json` (`engine`, `serving_model`, `workload.prompt_prefix_digest`, `machine.gpu.unbound_samples`, `machine.container.shm_bytes`, `machine.gpu.nvlink_active_links`), and `io/commands.jsonl` and `io/engine.log`. The first captures set `batches_per_session_run` (SRV-1: `iproofs serving size-session RUN_DIR` on the matched run directory, a 120 s steady target for the 60 s minimum; a one-request capture is refused, so a workload of one batch is sized from a sizing capture, S1b), the PC-GPU-IDLE baseline and whether NVML reports NVLink state (PC-GPU-LINK), and become the adapter's replay fixtures (its stored resolved-configuration line among them), by pull request.

## Stop rule

Before starting any job, and after each one ends:

1. Read the spend: [huggingface.co/settings/billing](https://huggingface.co/settings/billing), section Compute Usage, is the authority. Cross-check with `hf jobs ps -a` and `hf jobs inspect <job id>` for each job: its billed minutes times its flavor's per-minute price.
2. Write the job in the spend log below, with its pull time (creation time against the log's first line).
3. Start the next job only if the spend so far plus that job's cap is at most 200.00 USD (for stage 5, the budget the owner set for it). Otherwise stop: the rest of the plan moves to the bare-metal node.
4. Stop and look before spending more when a job fails for a reason not yet understood (a `FAIL` row, a failed binding check, a harness error, an exit other than 0 or 4). The next job is a probe of the question (stage 1a or 1), not a rerun of the same job. Never rerun a failed run to replace it; a rerun is a new repetition and the failed one stays recorded (AGENTS.md rule 5).
5. Cancel a job (`hf jobs cancel <job id>`) whose log shows it stuck (no new line for longer than the longest step estimated above) rather than letting it run to its timeout. A cancelled job does not upload; its billed minutes still count.
6. Never add a flag that weakens a system's statement to make a job pass (AGENTS.md rule 4); the only runs with such flags are the registered controls of `--control-suite` and of stage 5's `controls` jobs.

Spend log (keep it with the campaign notes, not in the repository; no job IDs or account names go into the repository, AGENTS.md rule 7):

```
| Date (UTC) | Stage | Flavor | Timeout | Pull (min) | Billed minutes | USD | Spent so far | Exit, outcome |
| 2026-11-09 | 1 sash probe | h200 | 20 min | 4 | 14 | 1.17 | 1.17 | 0, see probe.json |
```

(The row is an example of the form, not a result.)

## Where results live

- During the job: under the work directory, `out/dev-results/<release>/<system>/<run id>/`, with `out/dev-results/.selftest.json` and `out/dev-results/.archive/` (not uploaded by a `keep-io` job). The container's disk is deleted when the job ends.
- Afterwards: the private bucket `<namespace>/iproofs-dev-runs`, folder `runs/<UTC time>-<label>/`. List it with `hf buckets list <namespace>/iproofs-dev-runs/runs -h`, and copy one folder out with `hf buckets sync hf://buckets/<namespace>/iproofs-dev-runs/runs/<folder> <a directory outside the checkout>`. With the fallback, the private dataset `<namespace>/iproofs-dev-runs-ds`: `hf download <namespace>/iproofs-dev-runs-ds --repo-type dataset --include 'runs/<folder>/*' --local-dir <a directory outside the checkout>`.
- In `results/` only by a results pull request. `prover-h200-hosted` has no pinned driver yet (RFC-0006 Q5), so every run here records `harness.nonconforming: true`; that refuses nothing. RFC-0006 §Hosted execution allows hosted rows as their own configurations. A run needs a passing hosted self-test to be eligible for a release (RFC-0014 §Eligibility).
- What these runs are for: finding what fails on an H200 before the official runs (the `KL.bin` digest, memory, the kernel build, timeouts), and the numbers that size the bare-metal campaign. Quote any figure from them with its labels: scope, grade, tier `reported`, the profile `prover-h200-hosted`, the flavor, n, and the bucket folder it came from (AGENTS.md rule 2).

## What never to post

- No token in a command line, file in the checkout, issue or log. With the bucket, no token exists for these jobs. With the fallback, `HF_TOKEN` exists only in `~/.config/iproofs/hf-job.secrets` and, encrypted, as the job's secret.
- No job ID, account name or namespace in the repository (AGENTS.md rule 7): they live in the spend log and the bucket. The probe and the machine record print no host name, address or serial; read them before pasting any part into an issue.
- No weights and no proof bytes in the repository (AGENTS.md rule 8).
