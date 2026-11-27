# Level 1 runs

This runbook walks through executing Level 1 ([RFC-0018](../../rfcs/0018-level-1-ladder.md), [`levels/L1.yaml`](../../levels/L1.yaml)) on Hugging Face Jobs in order: probes first, then freezing the level, running the counted sessions, and cutting the release. Every job launches through [`hf-job.sh`](hf-job.sh) as described in [`hf-jobs.md`](hf-jobs.md), which covers account setup, the storage bucket, images, and uploads. This page covers only what Level 1 adds.

Cost estimates below are based on stored v0.1 job durations and provider list prices (read 2026-11-08), calculated before the first Level 1 run. The completed release v1.0 runs (SASH on Llama 3.1 8B, FlashProve on Llama 4 Maverick, both serving baselines, fidelity, and teacher-forced passes) live in [`results/v1.0/`](../../results/v1.0/), and the published board is [`releases/v1.0/board.json`](../../releases/v1.0/board.json).

## What runs where

| Job | Flavour | USD per hour | Rung |
|---|---|---|---|
| SASH session (commit, prove 5 requests, verify after weights are removed) | `h200` | 5.00 | Llama 3.1 8B |
| FlashProve session (commit, reply generation, prove 120 requests, verify) | `h200x2` | 10.00 | Llama 4 Maverick |
| Serving ladder, Llama 3.1 8B BF16 | `h200` | 5.00 | Llama 3.1 8B |
| Serving ladder, Llama 4 Maverick FP8 | `h200x4` | 20.00 | Llama 4 Maverick |
| Fidelity, Llama 3.1 8B (reference, six controls, KL) | `h200` | 5.00 | Llama 3.1 8B |
| Fidelity, Llama 4 Maverick (803 GB 16-bit reference) | `h200x8` (availability unverified) | 40.00 | Llama 4 Maverick |
| Verifier-side controls (C1 at three positions, C2, C3) on kept proofs | `cpu-xl` | 1.00 | both |
| Scoring and board generation (no GPU) | the owner's machine | 0 | both |

## Step 0: before any job (free)

1. Confirm `uv run iproofs level check` passes on the draft level.
2. Verify that the SASH weight perturbation for the Model check survives SASH's load-time quantization. Run the CPU tool shipped in `systems/sash/` (see its README, §Level 1) against the pinned BF16 file, then record the tensor, index, and change in `levels/L1.yaml` under `systems.sash.model_change`.
3. Rebuild the adapter images from this commit (adding `strace`, the Level 1 workloads, and FlashProve's reply route) and publish them publicly, following `hf-jobs.md` §Before stage 0.

## Step 1: probes (cap about 185 USD)

Each probe tests a single precondition that determines whether a row can pass. Probes run against a draft level and a past drand beacon round (any already published round), so their prompts stay separate from the counted ones. If any probe fails, stop and report to the owner; RFC-0018 defines the fallback (one request per rung).

| # | Question | Job | Cap (USD) |
|---|---|---|---|
| P1 | Does the 8B fidelity bar exist at n = 15 (can at least one damaged copy be separated from every honest copy)? | fidelity, 8B, on `h200` | 15 |
| P2 | Can the rented CPU container trace file opens during a verify call using `strace`? | a `cpu-xl` job running one stored v0.1 verify under the harness | 1 |
| P3 | Does SASH run at 512 + 512, what are its time per request and proof size, and does a 5-request session fit under the 40 USD cap? | one SASH session with `keep-io` | 45 |
| P4 | Does SASH's verifier reject a modified reply at the first, last, and an interior position, as well as a modified prompt? | verifier-side controls on P3's kept proof, on `cpu-xl` | 10 |
| P5 | Does FlashProve generate exact-match replies through upstream's integer-model package and prove a 512 + 512 window, and how long does generation take? | one FlashProve session of 24 requests (`level=L1` on a draft level; about 2 h of generation at upstream's 0.6 s per token, one reply at a time) | 30 |
| P6 | Serving ladders: does each engine reach full load within the ladder? | both serving ladders | 30 |
| P7 | Can the Maverick 16-bit reference model load and run in llama.cpp? | fidelity, Maverick, reference only | 45 |

## Step 2: freeze the level

1. Fill in every field marked "to pin" in `levels/L1.yaml` (the smaller models' revisions and the Maverick reference files), set `frozen` to the current date, and commit.
2. Immediately afterward, run `uv run iproofs level beacon`. It selects the first drand round published after that commit (one round every 3 s), fetches it from two relays, verifies it, and writes `levels/L1-beacon.json`. Commit that file (RFC-0018 PR-2).
3. Verify that `uv run iproofs level check --frozen` passes.

## Step 3: counted runs

Each row requires three sessions, one per slot, each run in its own job on a fresh container. A failed session may be retried in the same slot up to five times. After the sessions, run verifier-side controls on the kept proofs, the serving ladder for each rung, and each rung's fidelity job.

| Row or rung | Jobs | Estimate (USD) |
|---|---|---|
| SASH on Llama 3.1 8B | 3 sessions + controls | 100 to 150 |
| FlashProve on Llama 4 Maverick | 3 sessions + controls; each session takes about 12 h, with 10.2 to 10.6 h spent on reply generation (upstream generates one sequence at a time at the pin; estimated from upstream's H100 figure), or about 120 USD each, matching the rung's cap | 360 to 400 |
| Serving ladders | 2 | 30 |
| Fidelity | 2 | 60 to 200 |

Launch jobs using `hf-jobs.md` along with the Level 1 options in `hf-job.sh`:

```sh
hf-job.sh run sash l1-l31-8b-p512-o512:1:level=L1:session=1:keep-io      # one session per job, slots 1 to 3
hf-job.sh run flashprove l1-maverick-p512-o512:1:level=L1:session=1
hf-job.sh run ref-serve l1-l31-8b-p512-o512:1:level=L1:ladder           # serving-h200x1-hosted
hf-job.sh run ref-serve l1-maverick-p512-o512:1:level=L1:ladder         # serving-h200x4-hosted
# RFC-0018 CO-10 (proposed): each rung's request A, then the rung's request again on the same host
hf-job.sh run ref-serve l1-l31-8b-p512-o1:1:level=L1:ladder l1-l31-8b-p512-o512:1:level=L1:ladder    # serving-h200x1-hosted
hf-job.sh run ref-serve l1-maverick-p512-o1:1:level=L1:ladder l1-maverick-p512-o512:1:level=L1:ladder  # serving-h200x4-hosted
hf-job.sh fidelity llama-3.1-8b                                         # ref-fidelity image
hf-job.sh fidelity llama-4-maverick   # fidelity-h200x8-hosted, IPROOFS_FIDELITY_SLOTS=16
```

Run verifier-side controls on a kept SASH session using the split-suite flow in `hf-jobs.md` stage 5 (`seed`, `controls`, `merge`); `iproofs controls RUN_DIR` reads the level directly from the run's manifest. Any session whose verification host exposed a GPU (such as SASH) must be reverified on `cpu-xl` with `hf-job.sh reverify SYSTEM RUN_PATH` (RFC-0018 CH-4a). That job writes `reverify/` beside the stored run, and `iproofs results import JOB_RUN --add-to results/<release>/<system>/<run id>` merges it into the imported run directory.

SASH's slot 2 required a replacement session because its 2026-11-13 run failed the machine self-test. See [`sash-slot2-rerun.md`](sash-slot2-rerun.md) for the rerun jobs, cost estimates, import steps, and the two follow-up weakened-prover control jobs.

### Teacher-forced passes (RFC-0018 FI-10 to FI-15)

Teacher-forced passes are displayed alongside the fidelity check and do not gate any check. Because they depend on the rung's stored `reference.jsonl`, run them after the fidelity job finishes. Run one job per engine using `hf-job.sh fidelity RUNG` with `IPROOFS_TF=1`:

| Engine | Image | Flavour | Also set |
|---|---|---|---|
| llama.cpp: the reference and the controls it builds (8B) | `ref-fidelity` | `h200` | nothing |
| SASH's own code (8B) | the scoring image, `systems/sash/Dockerfile.score` | `h200` | `IPROOFS_TF_SYSTEM=sash`, `IPROOFS_TF_IMAGE`, `IPROOFS_TF_PROVER_FILES` (a counted session's `commitment/prover` folder in the bucket) |
| vLLM: the reference, its rerun, the other model (Maverick) | `ref-fidelity-vllm` | `h200x8` | `IPROOFS_FIDELITY_ENGINE=vllm` |
| llama.cpp: the quantized controls (Maverick) | `ref-fidelity` | `h200x4` | `IPROOFS_FIDELITY_PART=controls`, `IPROOFS_FIDELITY_GGUF`, `IPROOFS_FIDELITY_SLOTS=16`, `IPROOFS_TF_EACH=q8_0,q4_k_m` for one run per control, in that order |
| FlashProve's own code (Maverick) | the scoring image, `systems/flashprove/Dockerfile.score` | `h200x2` | `IPROOFS_TF_SYSTEM=flashprove`, `IPROOFS_TF_IMAGE` |

The images workflow builds each scoring image with `dockerfile: Dockerfile.score`, layering this commit's adapter file onto the row's pinned image while keeping the pin in `system.yaml` unchanged.

When testing a new code path, start with a single-prompt trial (`IPROOFS_TF_LIMIT=1`); trials are excluded from scoring. Set generous timeouts well above the estimate and launch with `--ssh` (`hf jobs run --ssh`, then `hf jobs ssh JOB`) so you can monitor slow runs without cutting them short. On 2026-11-13, a Maverick control run sized right to its estimate hit its deadline after 45 minutes and saved nothing. Since that incident, jobs stopped at a deadline preserve completed work: a system run saves every prompt whose requests finished (recording the count, and remaining a trial until the rest complete), and an engine run saves each finished control pass.

Long passes can be split across jobs with `IPROOFS_TF_OFFSET=K` and `IPROOFS_TF_LIMIT=N`, which processes prompts K through K + N - 1 (Maverick's quantized controls ran as three 120-prompt jobs, one per session slot). Together, jobs that cover every prompt once form a single pass. On Llama 4 Maverick, pass `IPROOFS_TF_SERVER_ARGS=--swa-full` to llama.cpp runs (achieving 133 to 146 positions per second vs. 6.7 without it, `systems/ref-fidelity/README.md`); the Q3_K_S and Q2_K passes ran together under this flag as one job with `IPROOFS_TF_EACH=q3_k_s,q2_k`.

Each job writes `teacher-forced/<rung>/` under its upload's release folder. Copy `run-*.json`, `top/`, `status-*.json`, `commands-*.jsonl`, and `logs/` into `results/v1.0/teacher-forced/<rung>/`, and keep `raw/` (the token lists, about 1 MB per prompt and engine, plus per-request server logs) out of the repository. After merging every job's `raw/` folders into one local directory, score the pass:

```sh
uv run iproofs fidelity score --level L1 --rung llama-3.1-8b --release v1.0 --part teacher-forced --raw <the merged raw directory>
```

This writes `kl.json` and `teacher-forced.json` into that folder (omitting `--raw` reads from the stored `kl.json`). Because merged scoring records are append-only (APP-1), do not edit them when adding new passes. Instead, rerun with `--scoring 2 --reason "..."` (then 3, and so on) to write `teacher-forced-2.json` and `kl-2.json`; the board reads the highest-numbered scoring file.

## Step 4: release

On the owner's machine, using the downloaded run directories:

```sh
uv run iproofs fidelity score --level L1 --rung llama-3.1-8b --release v1.0
uv run iproofs fidelity score --level L1 --rung llama-4-maverick --release v1.0
uv run iproofs release freeze v1.0
uv run iproofs release board v1.0
uv run iproofs site build
```

`release freeze` fails if any statement petal of a listed run has not been read (RFC-0018 GL-9). It reads the properties files and the commits of the listed runs, not `board.json`, which `release board` generates in the next step.

Finally, preview the site on port 4440, share each team's records with them for review, and deploy once the owner approves.
