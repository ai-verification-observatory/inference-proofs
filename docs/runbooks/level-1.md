# Level 1 runs

How the owner makes the runs of Level 1 ([RFC-0018](../../rfcs/0018-level-1-ladder.md), [`levels/L1.yaml`](../../levels/L1.yaml)) on Hugging Face Jobs, in order: probes first, then the frozen level, then the counted runs, then the release. Every job goes through [`hf-job.sh`](hf-job.sh) as in [`hf-jobs.md`](hf-jobs.md), which covers the account, the bucket, the images and the upload; this page covers only what Level 1 adds. Costs are estimates from stored v0.1 job durations and the provider's list prices (read 2026-11-08); nothing has run at the Level 1 request yet.

## What runs where

| Job | Flavour | USD per hour | Rung |
|---|---|---|---|
| SASH session (commit, prove 5 requests, verify after the weights are removed) | `h200` | 5.00 | Llama 3.1 8B |
| FlashProve session (commit, reply generation, prove 120 requests, verify) | `h200x2` | 10.00 | Llama 4 Maverick |
| Serving ladder, Llama 3.1 8B BF16 | `h200` | 5.00 | Llama 3.1 8B |
| Serving ladder, Llama 4 Maverick FP8 | `h200x4` | 20.00 | Llama 4 Maverick |
| Fidelity, Llama 3.1 8B (reference, six controls, KL) | `h200` | 5.00 | Llama 3.1 8B |
| Fidelity, Llama 4 Maverick (803 GB 16-bit reference) | `h200x8` (availability unverified) | 40.00 | Llama 4 Maverick |
| Verifier-side controls (C1 at three positions, C2, C3) on kept proofs | `cpu-xl` | 1.00 | both |
| Scoring and board (no GPU) | the owner's machine | 0 | both |

## Step 0: before any job (free)

1. `uv run iproofs level check` passes on the draft level.
2. The SASH weight change for the Model check survives SASH's load-time quantization: `systems/sash/` ships the CPU tool (see its README, §Level 1); run it on the pinned BF16 file and record the tensor, index and change in `levels/L1.yaml` `systems.sash.model_change`.
3. The images are rebuilt from this commit (they gain `strace`, the Level 1 workloads and, for FlashProve, the reply route) and pushed public, as `hf-jobs.md` §Before stage 0 describes.

## Step 1: probes (cap about 185 USD)

Each probe answers one question that decides whether a row can pass. Probes use a draft level and a past beacon round (any round already published), so their prompts are not the counted ones. Stop and report to the owner after any probe that fails; RFC-0018 names the fallback (a request per rung).

| # | Question | Job | Cap (USD) |
|---|---|---|---|
| P1 | Does the 8B fidelity bar exist at n = 15 (some damaged copy separable from every honest copy)? | fidelity, 8B, on `h200` | 15 |
| P2 | Can the rented CPU machine trace a verify call's file opens (`strace` under the provider's container)? | a `cpu-xl` job running one stored v0.1 verify under the harness | 1 |
| P3 | Does SASH run at 512 + 512, in what time per request, with what proof size, and does a session of 5 fit the 40 USD cap? | one SASH session, `keep-io` | 45 |
| P4 | Does SASH's verifier refuse a changed reply at the first, last and an interior position, and a changed prompt? | verifier-side controls on P3's kept proof, `cpu-xl` | 10 |
| P5 | Does FlashProve generate exact-match replies through upstream's integer-model package and prove a 512 + 512 window, and how long does generation take? | one FlashProve session of 24 requests (`level=L1` on a draft level; about 2 h of generation by upstream's 0.6 s per token, one reply at a time) | 30 |
| P6 | Serving ladders: does each engine reach full load within the ladder? | both serving ladders | 30 |
| P7 | Can the Maverick 16-bit reference be loaded and run in llama.cpp? | fidelity, Maverick, reference only | 45 |

## Step 2: freeze the level

1. Fill every value marked "to pin" in `levels/L1.yaml` (the smaller models' revisions, the Maverick reference files), set `frozen` to the date, and commit.
2. Right after: `uv run iproofs level beacon` takes the first drand round after that commit (one every 3 s), fetches it from two relays, checks it, and writes `levels/L1-beacon.json`; commit it (RFC-0018 PR-2).
3. `uv run iproofs level check --frozen` passes.

## Step 3: counted runs

For each row, three sessions, one per slot, each a separate job on a fresh container; a failed session is rerun in the same slot, at most five times. Then the verifier-side controls on the kept proofs, the serving ladder of each rung, and each rung's fidelity job.

| Row or rung | Jobs | Estimate (USD) |
|---|---|---|
| SASH on Llama 3.1 8B | 3 sessions + controls | 100 to 150 |
| FlashProve on Llama 4 Maverick | 3 sessions + controls; each session about 12 h, 10.2 to 10.6 h of it reply generation (upstream generates one sequence at a time at the pin; estimate from upstream's H100 figure), so about 120 USD each, the rung's cap | 360 to 400 |
| Serving ladders | 2 | 30 |
| Fidelity | 2 | 60 to 200 |

The job commands follow `hf-jobs.md` with the Level 1 options of `hf-job.sh`:

```sh
hf-job.sh run sash l1-l31-8b-p512-o512:1:level=L1:session=1:keep-io      # one session per job, slots 1 to 3
hf-job.sh run flashprove l1-maverick-p512-o512:1:level=L1:session=1
hf-job.sh run ref-serve l1-l31-8b-p512-o512:1:level=L1:ladder           # serving-h200x1-hosted
hf-job.sh run ref-serve l1-maverick-p512-o512:1:level=L1:ladder         # serving-h200x4-hosted
hf-job.sh fidelity llama-3.1-8b                                         # ref-fidelity image
hf-job.sh fidelity llama-4-maverick                                     # fidelity-h200x8-hosted
```

The verifier-side controls of a kept SASH session run as in `hf-jobs.md` stage 5 (`seed`, `controls`, `merge`); `iproofs controls RUN_DIR` reads the level from the run's manifest.

## Step 4: release

On the owner's machine, from the downloaded run directories:

```sh
uv run iproofs fidelity score --level L1 --rung llama-3.1-8b --release v1.0
uv run iproofs fidelity score --level L1 --rung llama-4-maverick --release v1.0
uv run iproofs release freeze v1.0
uv run iproofs release board v1.0
uv run iproofs site build
```

Then preview on port 4440, send each team its records, and deploy once the owner approves.
