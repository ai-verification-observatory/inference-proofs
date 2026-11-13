# RFC-0018: Level 1: the ladder, six checks, cost and fidelity

- Authors: 0xchqrles
- Created: 2026-11-10
- Requires: RFC-0002, RFC-0003, RFC-0004, RFC-0005, RFC-0006, RFC-0008, RFC-0009, RFC-0010, RFC-0012, RFC-0014, RFC-0015, RFC-0016, RFC-0017

Write "None." where a section has no content. Normative text uses MUST, SHOULD and MAY as defined in RFC 2119.

## Summary

This RFC defines Level 1, the first frozen definition of the benchmark, and the site it publishes. The site is a leaderboard laid out as a ladder: one rung per open-weights model, largest first. On each rung every system we can run unpatched gets one fixed request (512 prompt tokens, 512 reply tokens, greedy, every reply token checked), six checks we run ourselves, and one figure: how many times the cost of serving the same request a proved reply costs. Systems that pass the six checks are ranked by that multiple inside their rung. Nothing is divided or ranked across rungs. The headline is the frontier: the largest model on which a system passed, with its multiple.

Level 1 replaces, for everything it publishes, the six documentation properties of RFC-0016, the cross-model comparison of v0.1, the per-token headline of RFC-0004 and Part B of RFC-0017. The measuring core (adapter contract, runner, external timing, provenance, schemas) stays. The definition lives in `levels/L1.yaml` (schema `level/1`); this RFC says what each field means and how every published state and figure follows from stored records. Where this RFC and an earlier one disagree on a Level 1 release, this RFC wins.

## Motivation

- No two runnable systems share a model at their pins. FlashProve accepts only Llama 4 Maverick's shape ("only models of width 5120 and head width 128 are supported", `prover/weights_blocks/gguf_source.cuh` L29 to L30 at `9e2bdd8`); SASH proves dense Llama-shaped models (its recorded runs are all Llama 3.1 8B). A table that sorts the two against each other compares models, not provers. v0.1 did that.
- v0.1's FlashProve headline is wrong. Proofs are released in groups of 24 about 171 s apart, and the batch-membership rule of RFC-0004 INV-SCOPE-5 counted 119 requests where 96 were produced. Recomputed from release times, the four H200 runs read 7.060, 7.082, 7.128 and 7.195 GPU-seconds per request, not 5.746 (`results/v0.1/flashprove/*-fp-maverick-w1024-b24-prover-h200-hosted-*/run.json`).
- v0.1's two systems ran different requests: FlashProve checked one reply token after a 1,024-token window, SASH 64 reply tokens. RFC-0017 made the request the unit; a common request is still missing.
- The glyph of RFC-0016 states what each publisher writes. A reader takes a green cell as a test result. No test stands behind four of its six properties, and on v0.1 no control ever ran for Model bound.
- A system can quantize a model until proving it is cheap. Nothing in v0.1 measures how far the proved copy is from the publisher's model.
- The audience asked for a leaderboard: labs should want the top row, and a policy reader should learn in a minute which system passes, on which model, at what cost.

## Goals

- One page that ranks what can fairly be ranked and states the rest as fact.
- Every check state on the page is the outcome of a test we ran. Every petal step is computed from stored records: our runs, and the facts a reviewer copies from the publisher's documents at the pin.
- One request for the whole level, so a multiple means the same thing on every rung.
- A cost figure that a hostile expert cannot move by choosing a window, a batch or a baseline.
- A fidelity gate that stops a copy quantized far from the original, and a KL figure printed beside it.
- A level file frozen before the first counted run, so no constant is chosen after seeing a row.

## Non-Goals

- Testing soundness or weight secrecy. No check attempts a forged proof. The page says so.
- Recomputing a publisher's security level. It is printed as stated (Level 2 draft, below). Unforgeable reads the exponents of the bound the publisher states and computes no bits figure (Q9).
- Building a publisher's machine-checked proof: Level 1 reads a proof-build record and does not make one (MC-5).
- Closed-weights models, lab-run submissions, outside reruns and sealed provers at Level 1.
- Ranking across rungs, or any figure that divides one rung's cost by another's.
- Disclosure wording (About, operator line). The owner sets it before launch.

## Proposed Design

### Terms

- **Level.** A frozen definition: rungs, request, checks, order rule, constants. `levels/L<k>.yaml`. A change is a new level file (§Levels).
- **Release.** A dated snapshot of results under one level (RFC-0009). Level 1 releases are `v1.<n>`.
- **Rung.** One open-weights model, named by its publisher's original release, with its serving baseline and its fidelity reference. A rung holds one workload per system run on it.
- **Request.** 512 prompt tokens and a 512-token greedy reply, every reply token checked by the verifier (task `p512-o512`, RFC-0017). An end token does not stop the reply: when it is the greedy choice it is part of the reply and generation goes on after it (vLLM's `ignore_eos` behaves this way). A reference or control engine that would instead forbid the end token MUST be driven so it keeps this rule (FI-1).
- **Session.** One cold-start job: the system's `setup` and `commit`, then `prove` on N requests, where N is the rung's `requests_per_session`. A session is complete when `prove` exited 0 and released one accepted proof (or one joined set of proofs, RFC-0017 INV-REQ-2) for every request.
- **Slot.** Each rung has three session slots. Slot k proves prompts `[(k-1)·N, k·N)` of the rung's prompt set. A failed session is rerun in the same slot with the same prompts.
- **Row.** One system on one rung.
- **Check.** One of six tests, each ending `held`, `failed` or `undecided` (with a cause).
- **Passed.** All six checks `held`.
- **Multiple.** Steady GPU-seconds per further proved reply over the baseline's GPU-seconds per reply at full load (§Cost).
- **Frontier.** The largest rung, by total parameters, on which at least one row passed.

### The level file

`levels/L1.yaml`, schema `level/1` (`schema/level/1.schema.json`). Authored YAML, validated by gate G2. Its fields, each a constant some rule below names:

| Field | Meaning |
|---|---|
| `id`, `name`, `frozen` | `L1`; public name "Level 1"; the date it was frozen, or null while it is a draft |
| `request` | prompt and reply tokens, decoding rule, `ignore_eos: true`, `every_reply_token_checked: true` |
| `prompts` | generator `beacon-window/1`, corpus digest, beacon chain and round (§Prompts) |
| `rungs[]` | id, model name and publisher, total parameters, workload per system, serving record, fidelity reference and controls, `requests_per_session` |
| `sessions` | slots (3), attempts per slot (at most 5 runs per slot), spending cap per session in USD |
| `steady` | group gap (1 s), minimum later groups (3), tolerance (0.05) |
| `baseline` | concurrency ladder, plateau tolerance (0.05), warm-up and timed batches per concurrency, ladder prompts |
| `order` | margin (0.10) |
| `fidelity` | score, test, alpha, resample count, seed rule |
| `kl` | text count and length, tool |
| `systems` | per system: the stated security level (words, source) used by the order rule; the Model check's weight change (CH-2); `limits`, a check its own design makes impossible, with the publisher's sentence and source (CH-5) |
| `price` | the release's price basis (a `reference/<release>.yaml` cost key) |

A draft level file (`frozen: null`) can run probes and development runs. A counted run of a Level 1 release names the frozen level file by digest in its manifest; `iproofs release freeze` refuses a release whose runs name another digest.

### Prompts

- PR-1. Generator `beacon-window/1`: `corpus-window/1` (RFC-0003) with its seed taken from a public randomness beacon. The seed is the first 8 bytes, big-endian, of the beacon round's `randomness` (32 bytes, hex). The draw is otherwise identical: one `random.Random(seed).random()` per prompt, windows of 512 tokens of the corpus as the rung's tokenizer encodes it.
- PR-2. The beacon is drand's `quicknet` chain (a round every 3 s). The round is the first one produced after the commit that freezes the level file, so nobody, the operator included, knows the prompts when the constants are fixed, and nobody chooses the round. `iproofs level beacon` computes it from that commit's time, fetches it from two public relays, requires equal answers and `randomness == sha256(signature)`, and writes `levels/L1-beacon.json` (round, randomness, signature, relays, fetch date); `level check --frozen` refuses a stored round other than that one. A probe on a draft level names any past round. The BLS signature itself is not checked by the harness; anyone can check it with drand's own client.
- PR-3. Each rung draws one stream, in this order: its 3·N prompts; `kl.texts` KL windows of `kl.tokens` tokens; `baseline.prompts` (4,096) prompts for the serving ladder.

### Sessions and what is recorded

- SE-1. A session is one job from a cold start: a fresh container, the weights fetched and checked, `setup`, `commit`, then one `prove` call on the slot's N requests. The runner gives `prove` all N requests at once; the call ends by itself.
- SE-2. The harness records the wall time of every call, the release time of every proof (the release watcher, RFC-0011), and the GPUs the system binds. Machine-seconds are GPU-seconds of the bound GPUs (RFC-0006 R1); the rented machine's other GPUs are printed on the system page, not counted.
- SE-3. Three complete sessions count, one per slot: for each slot, the first complete run by start time. A session that ends incomplete is recorded with its exit code and last lines (AGENTS.md rule 5), enters no figure and no check except RUN (§Checks), and is printed on the system page. At most five runs per slot; a slot with five incomplete runs makes RUN `failed`.
- SE-3a. A counted session whose verdicts miss VERIFY WITHOUT WEIGHTS only because a GPU was visible to its verify calls on the job's own host (every trace written, no model file opened), and which was never re-verified (CH-4a, which needs its kept proof bytes), gives its slot to the first later complete session of the same pin (image and adapter commit) whose verdicts all meet CH-4. The replaced session enters no figure and no check and is listed on the system page with that reason. A session is never replaced for its figures, and the replacement is the first such session by start time, not a chosen one. Found 2026-11-13: SASH's verifier loads the CUDA driver and NVML, which open the GPU device on a GPU host even with no GPU given; it verifies with no GPU on a verifier host.
- SE-4. A session stops at the rung's spending cap (`rungs[].cap_usd`, else `sessions.cap_usd`), recorded as incomplete with cause `cap`. The cap is a constant of the level, the same for every system on a rung.
- SE-5. A refusal ends the slot at once. When the system's own code declines the request with a reason about its inputs (a refusal it raises on purpose, quoted from the run's last lines: not a crash of our adapter, a host fault, a timeout, out of memory or the cap), RUN is `failed` without further attempts: the slot's prompts and greedy replies are fixed, so a rerun proves the same request and meets the same refusal. A reviewer records it in `results/<release>/<system>/refusals/slot-<k>.json`, naming the run, the refusal line and the upstream source line that raises it (owner decision, 2026-11-11).

### Cost

All figures are in GPU-seconds of bound H200 GPUs; USD prints beside each at the release's price basis (RFC-0006 C7). Prover and baseline use the same GPU and the same price, so the multiple is the same in either unit.

- CO-1. **Session cost per reply.** For one session: GPU-seconds from the start of `commit` to the release of the Nth proof, over N. Generation is inside it wherever it happens. The row prints the mean of the three counted sessions and each session's value.
- CO-2. **Release groups.** Proofs released within `steady.group_gap_s` (1 s) of the previous release form one group. Group g has size n_g and release time t_g (its last release).
- CO-3. **Steady seconds per further reply, m.** For one session with groups 1..G: m = (t_G − t_1) × gpus / (n_2 + ... + n_G). It counts every GPU-second spent on the replies released after the first group. Where the adapter generates all replies in a phase of its own before proving (FlashProve: `cp_prove` refuses a GPU another process holds), that phase is not inside any group interval; the adapter marks its start and end (AD-4), the harness times both marks as it times a release, and m adds the phase's GPU-seconds divided by N. So m always includes generation. It is valid when G − 1 ≥ `steady.min_later_groups` (3) and every later group's per-reply time, (t_g − t_{g−1}) / n_g, is within `steady.tolerance` (5 %) of the median of those times. Otherwise the session has no steady state, with its cause (`too few groups`, `uneven groups`). A row has a steady state when all three counted sessions have one; its m is their mean.
- CO-4. **Baseline.** The rung's serving record (RFC-0015 SRV-6): the publisher's own release, served by the pinned engine on the fewest H200 that hold it. At each concurrency c of `baseline.ladder` (1, 2, 4, ..., 1,024) it serves one warm-up batch and then `baseline.timed_batches` (3) timed batches of c distinct prompts from the rung's ladder prompts (PR-3), each batch sent whole, with the request's decoding. A per-batch cache salt keeps the engine's prefix cache from reusing a prompt across batches. Rate r_c = replies per GPU-second over the timed batches. Full load is the lowest c with r_c ≥ (1 − `baseline.plateau`) × max r. When that is the ladder's top rung, the rate was still rising more than `baseline.plateau` there, so the ladder never reached the engine's capacity: the rung has no baseline ("not saturated") until the ladder is extended. The first Maverick run rose 32 % from c = 128 to 256 against a KV cache with room for about 593 such requests, so the ladder runs to 1,024 (the engine's default batch limit) on `baseline.prompts` = 4,096 distinct prompts. The baseline's seconds per reply is 1 / r at full load. Its concurrency, rate and the whole ladder print on the rung's page. The run's reply token ids are kept beside its run.json, by digest, not in git (RFC-0013 SIZE-1); the baseline reads only release times.
- CO-5 (amended 2026-11-13). **Multiple.** m over the baseline's seconds per reply, with both halves printed. A row with no steady state has no multiple; it prints its session cost per reply over the baseline's seconds per reply, labelled "whole sessions of N replies" (until 2026-11-13 "cold sessions of N replies": the figure counts each session whole, start-up included, and "cold" did not say so).
- CO-7. **Generation and proving.** Where the adapter generates the replies in a phase of its own (AD-4), m splits in two: the generation part, the phase's GPU-seconds over N, and the proving part, m less it. The row prints both beside m, each also over the baseline's seconds per reply. The order rule reads m alone. A system with no such phase has no split; its generation, if any, is inside the proving interval. Amended 2026-11-13 (Q15): the session cost per reply (CO-1) splits the same way, into the generation part, the phase's GPU-seconds over N, and the commit and proving part, the session cost less it (the `commit` call, the `prove` call outside its generation phase, and the seconds between the two calls), each the mean of the counted sessions, timed as CO-1 is (whole session), with n the counted sessions. A row with no steady state prints both beside its session figure, each also over the baseline's seconds per reply.
- CO-6. Every figure is computed in `iproofs.derive` from stored records (AGENTS.md rule 3) and recomputed by gate G4. The fixture `harness/tests/fixtures/derive/release-groups/` holds the release times of the v0.1 run `2026-11-09-flashprove-fp-maverick-w1024-b24-prover-h200-hosted-1`: five groups of 24, later per-reply times 7.116, 7.136, 7.141 and 7.119 s, m = 7.128 GPU-seconds per request (one token checked at batch 24). The other three H200 runs read 7.060, 7.082 and 7.195; v0.1 published 5.746.

### The six checks

Each check ends `held`, `failed` or `undecided`. An undecided check names its cause, one of: `system limit` (the system cannot do what the test needs, quoted), `not run` (the operator has not run it), `not resolved` (the test ran and decided nothing), `not reproduced` (a verifier accepted a changed input in our adapter; not yet reproduced with the system's own command). An undecided check is never worded as a failure. `failed` from an adapter-run test needs a reproduction record (CH-8).

| Check | Id | Held when | Failed when | Evidence |
|---|---|---|---|---|
| RUN | `run` | three slots each have a complete session (SE-1), built from the public pin, unpatched, no weakening flag | a slot has five incomplete runs or a recorded refusal (SE-5), or a counted session used a weakening flag | `run.json` of every session |
| MODEL | `model` | P1 (RFC-0008: commit W, prove with W′, one weight changed) produced no accepted proof in 3 of 3 trials, and C3 (an honest proof verified against the commitment of W′) was refused in 3 of 3 trials | any trial of either accepted | `controls.json` |
| PROMPT | `prompt` | C2 (one prompt token changed at a seeded position) refused in 3 of 3 trials | any trial accepted | `controls.json` |
| REPLY | `reply` | every accepted proof covers all 512 reply tokens (RFC-0017 INV-REQ-2), and C1 refused at the first, the last and one seeded interior reply position, 3 of 3 trials each | coverage short, or any trial accepted | `run.json`, `controls.json` |
| VERIFY WITHOUT WEIGHTS | `no_weight_file` | every counted verdict came from a verify call (a) with no GPU visible, (b) on a filesystem holding no model file of the workload (removed or never fetched), (c) under a file-open trace that names no model file | the trace names a model file, or a verify call needed one | `verify-trace/` of every session |
| FIDELITY | `fidelity` | the row's replies score above the rung's bar (§Fidelity) | the bar scores above the row | `fidelity.json` of the rung |

- CH-1. The checks run against the counted sessions' honest proofs. MODEL, PROMPT and REPLY reuse RFC-0008's controls with their seeds, honest twins and `void` rule; only the trial counts and positions above are new. A trial whose honest twin was not accepted is `void` and is rerun with the next seed, at most 10 seeds per series (each C1 position is its own series); 3 counted trials are needed.
- CH-1a. A failed control prove (P1) is the prover's refusal only when the trial's line names a stop that the system's `system.yaml` lists under `p1_refusals`: the prover's own stops that mean the weights are not the committed ones, from its documentation at the pinned commit (FlashProve: `hc-own-node`). A control prove with W′ also counts as refused when (a) the prover exits 0 and answers the request "failed" with no proof, as the system documents at its pin and declares under `p1_refusals.failed_answer` (FlashProve, `prover/docs/ends-in-short.md`, "What an exit gives away": "a failed check on a hidden value neither ends the process nor changes its status; the request, or its batch, is answered 'failed'"), (b) the same run's honest proof of that request was accepted, and (c) no Python exception went through the adapter and no layout guard fired (owner decision, 2026-11-13). Any other failed prove decided nothing and counts as `error`: the harness's bare "<kind>: prove exited <code>", a Python exception in the adapter, and a prover guard on how the files are laid out (FlashProve's `cp-weights-files`, raised for a weight file with a second name). A prove whose stderr holds a Python traceback through the adapter's entrypoint is recorded as `error` (RFC-0008 §Outcomes). The trial's line keeps the prover's own reason: the last lines of the newest log in the control prove's io, after `| log:`. A control prove's io holds real copies of what setup and commit left (io/state's entries then, and every other directory they made), made before that prove and removed after it, so one copy is on disk at a time. Found 2026-11-13: FlashProve session 1's P1 trials stopped in the adapter (`FileExistsError` on its work directory); the two control runs that followed stopped on a missing `/io/fit` (`FileNotFoundError`) and on hard-linked weight files (`cp-weights-files`); the third (`runs/20261113T170513Z-l1-fp-p1-control-3`) proved and verified its honest request (accepted), and each of its three W′ proves exited 0 with the request answered "failed" and no proof.
- CH-1b. P1 may come from a control run of the row: `iproofs run --level L1 --session K --control-run --control-suite`, slot K's first prompt at batch 1 (its P1 proves at that batch too: P1 asks only whether a prove with W′ yields an accepted proof), `control: true` in run.json, never a session (SE-3) and never printed as one. MODEL takes P1 trials from a complete control run whose manifest names the level digest, workload, image and adapter commit of the row's counted sessions; C1, C2 and C3 come from counted sessions only. Why: P1 commits W and proves with W′ against that commitment, and a system that draws a fresh secret at each commit (FlashProve) can prove for a session's commitment only inside that session; when a session's P1 decided nothing (CH-1a) and its state is gone, the commit of its own a control run makes is the way to run P1 at the same pin. Found 2026-11-13.
- CH-2. The weight change for MODEL is fixed per system before the first counted run and recorded in the level file: one stored code in a dense tensor every request reads, changed by one step in the representation the system commits. For a system that quantizes at load (SASH), the change MUST survive quantization: it moves the stored integer code. The adapter makes W′ itself through its `perturb` subcommand (AD-5), so the change is the one the level names and no harness code reads the system's format. A system whose commitment draws a fresh secret on each commit (FlashProve) shows the change by the system's own weight digest tool on W and W′, not by the commitment id. If no change can be shown, MODEL is `undecided`, cause `not run`, until one is found. P1 and C3 are control jobs: an adapter MAY accept W′ there in place of the published files it otherwise requires, and only there (AGENTS.md rule 4).
- CH-3. REPLY's interior position is `seeded_index(control_seed, "C1-interior", k, 510) + 1` for trial k, so it is never the first or last.
- CH-4. VERIFY WITHOUT WEIGHTS: the trace is `strace -f -e trace=open,openat,openat2 -o <file>` around the adapter's verify process (or the hosted equivalent). The harness reduces it to the list of paths opened with their sizes and writes `verify-trace/<proof_id>.json`. A path counts as a model file when it is, or its realpath is, a file listed in the workload's `model.files` or under the model directory. A trace tool missing from the image makes the check `undecided`, cause `not run`.
- CH-4a. A verdict whose own trace shows a GPU visible meets (a) to (c) through a re-verify of the same proof on a verifier host with no GPU (`iproofs reverify RUN_DIR`, `hf-job.sh reverify` on `cpu-xl`): the run's kept proof bytes verified again in the run's image, under the same trace, the weights never fetched on that host, recorded once in `reverify/` beside the run (`reverify.json`, schema `reverify/1`, and one trace per proof). It counts when it names the run, its image and each proof's sha256 as the manifest records it, and its verdict is `accept`. The verify time printed stays the session's own.
- CH-5. A test the system's own design makes impossible (for example a verifier that takes no prompt, so C2 cannot be sent) makes that check `undecided`, cause `system limit`, with the publisher's sentence. The row cannot pass.
- CH-6. Checks are computed by `iproofs.checks` from stored records only: the counted sessions' `run.json`, `controls.json`, `verify-trace/` and the rung's `fidelity.json`. No reviewer sets a state.
- CH-7. The six checks are the entry gate: a row that passes them is ranked (§Order). They are printed as one status on the row ("passed", or the checks not held) and as a table on the system page. They are not the glyph (§The glyph).
- CH-8. A `failed` MODEL, PROMPT or REPLY from an accepted trial is published as `failed` only with a reproduction record `results/<release>/<system>/reproductions/<check>.json`: the upstream command, run outside our adapter on the stored inputs, accepting the same altered input. Until then the check is `undecided`, cause `not reproduced`, and the publisher is told (RFC-0008 §Disclosure).

### Fidelity

- FI-1. Reference: the rung's publisher's original weights (the serving record's files, or the 16-bit release where the serving record is FP8), converted to GGUF by `llama.cpp`'s `convert_hf_to_gguf.py` at the level's pinned llama.cpp commit, in the rung's `reference.dtype` (16 bits, `bf16`; 32 bits, `f32`, for GPT-2, whose release is F32), and run greedily in `llama.cpp` on the rung's 3·N prompts for 512 tokens, end-of-sequence ignored. These replies are stored (`results/<release>/fidelity/<rung>/reference.jsonl`).
- FI-2. Controls, each named in the level file by recipe, run the same way on the same prompts:
  - honest: the reference run a second time; `Q8_0`; `Q4_K_M` (`llama-quantize` from the reference GGUF);
  - damaged: `Q3_K_S`; `Q2_K`; the reference model with a quarter of its blocks removed (`systems/ref-fidelity/drop_blocks.py`: every fourth block of a dense model, 8 of 32 for Llama 3.1 8B; for Llama 4 Maverick, whose llama.cpp loader decides which blocks hold experts from their index, every fourth pair of blocks, 12 of 48, so the file still loads); a smaller model of the same publisher and tokenizer (Llama 3.2 1B Instruct for the 8B rung, Llama 4 Scout 17B-16E Instruct for Maverick).
  The file a system commits is never a control.
- FI-3. Score: for one reply, the number of leading tokens equal to the reference reply, 0 to 512.
- FI-4. Test: a paired one-sided sign-flip test on the per-prompt differences of scores, statistic the mean difference. With n ≤ 20 it enumerates all 2^n sign vectors; above, it draws `fidelity.resamples` (200,000) sign vectors from `random.Random(seed)`, seed the first 8 bytes, big-endian, of sha256(randomness bytes ‖ 0x00 ‖ id of A ‖ 0x00 ‖ id of B). The p-value counts sign vectors whose mean is at least the observed one (ties count); the Monte Carlo p is (1 + hits) / (1 + resamples), never 0. "A scores above B" means p < `fidelity.alpha` (0.05).
- FI-5. Bar: among the damaged controls that every honest control scores above, the one with the highest mean score. With none, the rung has no bar, and FIDELITY is `undecided`, cause `not resolved`, on every row of the rung.
- FI-6. A row's replies are the claimed outputs of the accepted proofs of its three counted sessions, n = 3·N. FIDELITY is `held` when the row scores above the bar, `failed` when the bar scores above the row, else `undecided`, cause `not resolved`.
- FI-7. KL, printed and never gating: `llama-perplexity --kl-divergence-base` on the reference over the rung's KL texts, then `--kl-divergence` for each control and, where the system commits a GGUF file that `llama.cpp` loads, for that file. llama.cpp reads the KL texts as text (detokenized from the drawn token windows and tokenized again by the model's own tokenizer) and scores the second half of each 512-token chunk, as `llama-perplexity` does. The figure is the mean KL divergence per scored token, in nats (unit `nat/token`), labelled "computed by llama.cpp on the committed file, not the proved computation". A system whose committed copy is not a file `llama.cpp` loads prints "not measured" with that reason, unless its adapter implements the optional `logprobs` subcommand (AD-2), which returns the system's own next-token distributions over the same chunks; the harness then computes the same mean against the reference's distributions.
- FI-8. `iproofs fidelity run` runs FI-1, FI-2 and FI-7 in the `ref-fidelity` image on a GPU profile; `iproofs fidelity score` computes FI-3 to FI-6 on a CPU from stored replies and writes `results/<release>/fidelity/<rung>/fidelity.json`.
- FI-9. **A rung whose 16-bit reference llama.cpp's pin cannot run** (Llama 4 Maverick, 2026-11-12: llama.cpp v0.9.0 stops on `MUL_MAT_ID` with an illegal memory access on the 16-bit file on 8 H200, with every option tried; its 8-bit file runs). The reference, the `rerun` control and the `other_model` control run in vLLM at the serving baselines' pin (v0.32.0, `systems/ref-fidelity-vllm`): the same prompts, greedy, `ignore_eos`, 512 tokens, no prefix cache, tensor-parallel over the job's GPUs; the rerun sends the prompts in reverse order, so its batches differ from the reference's. The `quantize` controls run in llama.cpp at the level's pin (`fidelity run --part controls`, record `fidelity-run-controls.json`), quantized by `llama-quantize` from the publisher's 16-bit release as a GGUF the run names by repository, revision and each file's sha256 (for Maverick, unsloth's BF16 GGUF at the revision the Maverick workloads pin), since converting 803 GB takes 2 h 10 min on the job's CPUs. `drop_blocks` is not run (its copy is the 16-bit file in llama.cpp) and is printed with that cause; it never sets the bar (FI-5). No KL is measured on such a rung: llama.cpp's KL base is the 16-bit file. `fidelity score` reads both records; they must name the same level digest and prompts. The level file is unchanged: every counted session names its digest.

#### Teacher-forced agreement and KL (amended 2026-11-13, FI-10 to FI-15)

A second fidelity measure, printed beside FI-3's. It gates nothing: FIDELITY (FI-6), the bar (FI-5) and Faithful model's steps (FM-1 to FM-7) read FI-3's score, unchanged. Why it is printed: FI-3 stops at the first token that differs, so one near tie early in a reply sets the score of the 500 tokens after it to nothing, and the scores are heavy-tailed at small n. Here every reply position is a sample of its own.

- FI-10. **Measure.** Each engine is fed, for each of the rung's 3·N prompts, the prompt followed by the stored reference reply (FI-1's or FI-9's `reference.jsonl`, 512 tokens), as token ids. At each of the 512 reply positions the engine gives its own top token: the argmax of its logits there, the lowest id among equal logits. **Alignment:** row t is computed after the prompt and the first t tokens of the reference reply and predicts reply token t, for t from 0 to 511; reply position 0 is predicted after the prompt's last token. **Score:** for one prompt, the number of positions whose top token is the reference token, an integer from 0 to 512, unit `agreeing positions`. It differs from FI-3's in one way: the engine always continues from the reference's tokens, never from its own. The level file names its gating score in one line, `fidelity.score`: Level 1 names `matched_prefix` (FI-3). A level whose line names `teacher_forced_agreement` reads this score wherever FI-4 to FI-6 and Faithful model's thresholds read FI-3's, with nothing else changed (both are integers from 0 to 512 per prompt over the same prompts). Whether a level does so is the owner's decision (Q19); under LV-1 it is a new level file, and the `level/1` schema, which pins `matched_prefix`, gains the second value with it.
- FI-11. **Test, printed, not gating.** FI-4's sign-flip test on these scores, each row against each control that ran, both ways ("the row scores above the control", "the control scores above the row"), with FI-4's alpha, exact count up to n = 20 and resamples. Seeds follow FI-4 with each id prefixed `teacher_forced/`, so no draw is shared with FI-3's tests. A prompt on which a system's own code gives no top tokens (FI-13) scores 0 in the mean and the tests, is never dropped, and is listed with its cause; the mean over the other prompts is printed beside it. A control or the reference with such a prompt is recorded as failed as a whole: it is an engine we drive, so a prompt it does not answer is our run's failure, not a result.
- FI-12. **KL, printed, never gating.** Each engine also lists, at each reply position, its 256 most probable tokens with their log-probabilities. At one position the figure is the KL divergence, in nats, between the reference's distribution and the engine's over this partition of the vocabulary: each token that both lists hold, and one outcome for every other token. With p and q the two probabilities on the common tokens S, m_p = 1 − Σ_S p and m_q = 1 − Σ_S q, it is Σ_S p (ln p − ln q) + m_p (ln m_p − ln m_q). It is at most the KL over the whole vocabulary (pooling outcomes never raises a KL divergence) and equals it when the common tokens hold all of the reference's mass; the mean m_p is printed with the figure (`reference_rest_mass`). A rest mass below 10⁻⁶, which float32 log-probabilities do not resolve, is left out on the reference's side and taken as 10⁻⁶ on the engine's. A prompt's KL is the mean over its positions that hold a list on both sides, a figure's the mean over the prompts that have one, unit `nat/token`, with the count of prompts and positions. An engine that returns no list at a position is counted there (`positions_without_list`): llama-server returns none when its top token ends inside a UTF-8 character. The lists (1 MB per prompt and engine) stay outside the repository; each run record names its lists by digest, and `kl.json` holds the per-prompt values measured from them.
- FI-13. **Whose computation.** Every figure of a row under FI-10 to FI-12 is labelled, word for word, "computed by the system's own code on the reference reply, not by the proved computation". No proof is made of a reference reply: under exact match a proof exists only for the model's own reply (AD-3). What ran, per system:
  - SASH: the witness extractor (`harness.witness.extract --head`), the program that writes the prover's input, with the reference reply as `--ids` and the attention calibration of the counted sessions' commitment. The top token is the extractor's `tok_head` and the logits are its `key_head` order keys, which are bf16 values. Not stated at the pin: that `--ids` is meant for ids other than the model's own greedy reply (its help text says "token ids (.npy) to run instead of the corpus's first --tokens"); that the extractor's values equal the proved ones bit for bit (the source says "A witness and a spec are one object"); whether the segment proofs would accept on such ids (not run).
  - FlashProve: the publisher's integer-model package (`IntegerModel.extend` with `gap_for`, the call of its `examples/score_reply.py`), the package the adapter writes the replies with (AD-3). The publisher says it is "By design, this is the function that the repository's prover proves". Not stated at the pin: that the package equals `cp_prove` value by value at full size ("What was compared with the prover is proof or no proof, and greedy choices"; "nothing was compared at full size"). The logits for FI-12 come from `extend`'s `record` argument, which the call's docstring and `OPERATING.md` describe and the README's "Python API" section does not show; a logit is the integer logit divided by 2^s, which the parameter-file documentation calls "the provider's statement: no equation ties it to the model".
  - A prompt the system's own code declines (SASH: an assertion of the extractor on the ids; FlashProve: `RangeConditionFailed`) is counted as failed with that line as its cause. Any other failure of the call is our run's, and gives the row no figure.
- FI-14. **Runs and pins.** `iproofs fidelity run --teacher-forced` runs one engine: the reference image of the rung (the reference itself and the controls it builds; in llama.cpp one `/completion` request per reply position with the token ids up to it, one token generated, the slot's cache kept; in vLLM one request per prompt with `prompt_logprobs`), or with `--system` a row's adapter (AD-7). Token ids go in and come out: nothing is detokenized and tokenized again. `drop_blocks`, the other model and the quantized controls are built as FI-2 and FI-9 build them, and a control this run does not build is printed with its cause. A row is scored in a **scoring image**: the image its counted sessions ran, by digest, plus the adapter file that holds `score` (`systems/<name>/Dockerfile.score`). The row's `system.yaml` pin and every counted session are unchanged; the run record names the scoring image's digest and adapter commit and the sessions' image, adapter commit and upstream commit, and the run stops unless the image reports the sessions' upstream commit. Commitment files `score` needs (SASH's attention calibration) are a counted session's, each checked against the digest the sessions' manifests record. Before the reference replies, the run scores the system's own proved reply to prompt 0 (slot 1's first request): its top tokens MUST be that reply at all 512 positions, since the reply is the model's own greedy reply (AD-3); otherwise the scoring path is not the sessions', the run stops and nothing is stored (`own_reply_check`). Records, in a folder of their own, `results/<release>/teacher-forced/<rung>/`: `run-<name>.json` (schema `teacher-forced-run/1`), `top/<id>.jsonl` (per prompt the 512 top tokens, or the cause it has none), `kl.json`.
- FI-15. **Scoring.** `iproofs fidelity score --part teacher-forced` computes FI-10 to FI-12 on a CPU from those records into `teacher-forced.json` (schema `teacher-forced/1`) in that folder; it never writes `fidelity.json` (APP-1): per control and per row the scores, mean, median, failed prompts, the KL figure and its note, and each row's tests; also the reference engine's own pass, which shows how often its top token under teacher forcing is the token it wrote. A pass is one run of every prompt, or several runs of one engine that together cover every prompt exactly once (`offset` and `prompts` in each record): a control split across jobs, or a stopped run and the run that finished it; their top tokens are joined in prompt order. Runs that leave a prompt out, or cover one twice, give no pass. A run stopped before its end stores what it finished (a system's prompts, an engine's controls), and a run that stored nothing is listed with its exit code and last lines in `not-stored.json`.

### The glyph

The glyph shows how close a row is to a perfect prover. It asks five questions, one per petal: what bound the publisher states on a false reply being accepted, whether that bound is proved and whether it covers what the row runs; what the publisher states and proves about a proof showing nothing of the weights' values; how close the proved replies stay to the model publisher's own release, against the rung's controls; how far a machine-checked proof of soundness reaches toward the verifier program the row runs; and what soundness rests on besides cryptographic assumptions. A fully green glyph means all five hold in full. Passing the checks is the bare minimum; the glyph is the distance from there to perfect (owner decision, 2026-11-10; petals amended 2026-11-13, Q6).

| Petal | Id | Basis | Lowered by | Question |
|---|---|---|---|---|
| Unforgeable | `unforgeable` | statement | Model, Prompt, Reply | The bound the system's publisher states on a false reply being accepted: whether it is proved, and whether it covers what the row runs. |
| Weights hidden | `weights_hidden` | statement | Verify without weights | What the publisher states and proves about a proof showing nothing of the weights' values. |
| Faithful model | `faithful_model` | test (our fidelity run) | Fidelity | How close the proved replies stay to the model publisher's own release, against the rung's controls. |
| Machine-checked | `machine_checked` | statement | Model, Prompt, Reply (only where it is green); a recorded proof build | How far a machine-checked proof of soundness reaches toward the verifier program the row runs. |
| No third party trusted | `no_trusted_party` | statement | nothing | What soundness rests on besides cryptographic assumptions. |

The rows are in drawing order. A petal set red by a failed check or a failed proof build has basis `test`.

Each petal is at one step. The board stores the step as a word (`step`) and the ink it is drawn in (`state`):

| Step (`step`) | Ink (`state`) | Printed |
|---|---|---|
| `green` | `green` | green · in full |
| `amber_upper` | `amber` | amber · in part |
| `amber_lower` | `amber` | amber · in lesser part |
| `red` | `red` | red · no |
| null | `hollow` | undecided |

A red petal carries a `cause`: `not_stated` (the documents read are silent), `stated` (the publisher states that the property does not hold, or the stated facts do not reach amber) or `check_failed` (a check or a recorded proof build lowered it, GL-2). A hollow petal carries a `cause`: `not_read`, `not_decided` or `proof_build_not_run` (GL-3). A green or amber petal has no cause. The site draws amber in lesser part as the arm with its end cell cut off, and a red petal with cause `not_stated` as an outline in the red ink, its name not struck: it is still red (GL-1). Every other red is solid, its name struck (Q7).

- GL-1 (amended 2026-11-13). A statement petal (Unforgeable, Weights hidden, Machine-checked, No third party trusted) is computed by `iproofs.glyph` from facts a reviewer copies from the publisher's documents at the row's pin into `systems/<name>/properties.yaml` (schema `properties/2`). Each fact holds its value, the deciding quotes with their links at the pin, and a `note` where the value is the reviewer's reading rather than the publisher's words. A quote is a substring of the linked file at the pin once each run of whitespace in both is collapsed to one space; markup and comment markers are kept. No state, step or reason is typed. CI checks the file against its schema and `iproofs validate` checks what it can offline (the pin, the links, the expression and its terms, the trusted base); whether each quote is in the linked file is a review rule, since validate fetches nothing. Silence is red, printed as "not stated in the publisher's documents read at the pin", with the documents read listed beside the quotes, each linked at the pin (owner decision, 2026-11-10: a guarantee nobody states is one nobody can rely on; until 2026-11-13 the reason itself listed the documents and the commit, GL-5).
- GL-2 (amended 2026-11-13). Tests only lower. A failed check sets red, cause `check_failed`, basis `test`, the petals whose claim it contradicts, whatever the statement says: Model, Prompt or Reply sets Unforgeable red, and Machine-checked red where it is green; Verify without weights sets Weights hidden red; Fidelity sets Faithful model red. A matching proof build that failed or exited other than 0, or that reports a set of axioms other than the declared one, sets Machine-checked red (MC-4). The petal's `lowered_by` names what lowered it. An undecided check lowers nothing. A held check never raises a statement: a refused control shows that one attack was refused, nothing more ([RFC-0008 §Non-Goals](0008-negative-controls.md)).
- GL-3 (amended 2026-11-13). A petal not decided is drawn hollow, with its cause: `not_read` (a statement petal whose properties file is missing, is not `properties/2`, or was read at a commit other than the one the row runs, or whose row has no recorded commit), `not_decided` (Faithful model with FIDELITY undecided, no `fidelity.json`, or no scores for the row) or `proof_build_not_run` (Machine-checked stated above red with no proof-build record that matches the row). Not read is not silent: a file nobody read is hollow, never red.
- GL-4. The glyph is drawn only for rows we ran. It never moves a position: the order is cost among passed rows (OR-1 to OR-6), and the page says so. The glyph is not part of the level file (§Terms), so a change to its rules amends this RFC and needs no new level (LV-1).
- GL-5 (amended 2026-11-13). `iproofs.glyph` computes every petal from the properties file and the stored records. The board file carries, for each petal, `id`, `state`, `step`, `cause`, `basis`, `reason`, `quotes` and `lowered_by`; a `not_stated` red carries `sources_read` (GL-1); Machine-checked also carries `formal` (its stated step, reach, tool, theorem and link, trusted base, input code and scope card) and Weights hidden `visible` (the visible values with their tags and quotes). Both are null on a petal not read. A fact with a note is the reader's reading, and the petal says so: it carries `reading: true` when a fact its decision read carries a `note` (absent means false). A petal with basis `test` carries no `reading`: a check or a proof build decided it, not the publisher's words. A petal carries no number of its own. A reason is one plain line, under about 110 characters, that says what was found, with numbers in their units and no symbols; the quotes, the facts and the records printed beside it carry the detail, and it says no more than they support (amended 2026-11-13).
- GL-6. One fact, one petal ([RFC-0016](0016-glyph-properties-and-states.md) ST-5, brought back): each stated fact sets one petal. Whether the bound is proved or conjectured, and its exponents, set Unforgeable; how far a machine-checked proof reaches sets Machine-checked only. Unforgeable asks whether the publisher states or proves that the program the row runs implements what the bound is about (`bound.program`), and counts the two alike; whether that program is machine-checked is Machine-checked's question. Weights hidden does not ask whether the code run is proved.
- GL-7. Each petal alone: a petal is decided as if the other four were green. No line of the tables below reads another petal.
- GL-8. Nothing to add up ([RFC-0016](0016-glyph-properties-and-states.md) INV-GLYPH-1): no total, count, average, sort or filter over petals, on the site or in `board.json`. `step` is a word, never an integer.
- GL-9. `iproofs release freeze` refuses a release in which a statement petal of a listed run is not read (GL-3). It computes this from the properties files and the listed runs' commits, never from a stored `board.json`. `iproofs validate` refuses the board of a frozen release that holds a petal with cause `not_read`.

#### Reading the tables

Each table below is read top to bottom; the first matching line decides. On any doubt the lower step wins. "Under" is strict: an exponent of exactly 80 or 100 is not under it. A statement petal is **not read** in the cases GL-3 names; the commit the row runs is the first counted session's manifest `system.upstream.commit`. A **silent** value is `false`, `not_said`, `not_stated`, null or an empty list. A `not_stated` red carries the petal's `sources_read`, each linked at the pin, and the page prints the list with its quotes (GL-1, amended 2026-11-13).

#### Unforgeable (`unforgeable`)

Facts (`bound`):
- `stated`: whether a bound is stated.
- `expression`: the bound, verbatim, a substring of one of its quotes.
- `terms`: the integer exponent of each error term in the expression, for example [124, 101] for q/2^124 + 2^-101. `iproofs validate` reads the exponents the expression writes (each t of `2^-t`, `2^(-t)` or `/2^t`) and requires them to equal the terms, as sets. When the expression writes no such power (SASH: "100 conjectured bits"), each term must be a whole number written in the expression, not part of a longer one.
- `basis`: `proved`, `conjectured` or `not_said`.
- `unit`: what one stated bound covers: `reply`, `proof`, `part`, `round` or `not_said`.
- `adversary`: `any_prover` (the bound holds against a prover that controls its own machine, with no hardware or third-party condition), `weaker` or `not_said`.
- `parameters`: `row` (the bound is stated for the parameters of the configuration the row runs), `other` or `not_said`.
- `batch`: how the publisher states the bound for members of a batch: `each_member` (for each member checked alone), `together` (only for members or proofs handed in together, for example N times the error of one) or `not_said`.
- `program`: `proved`, `stated` or `not_stated`: whether the program the row runs to verify is proved, or stated, to implement the protocol or verifier the bound is about. A publisher sentence that the bound is not claimed for that program records `not_stated`, with that sentence as its quote.
- `conditions_shown`: true when the publisher's or the harness's records show that the theorem's stated conditions hold for the row's files; false otherwise, including when the publisher says it is not known.

The bound covers one reply of the row when `unit` is `reply`, or `unit` is `proof` and `proofs.granularity` in `systems/<name>/system.yaml` is `request` (one proof per request). It covers the row's batch when the workload's `shape.batch_size` is 1 or `batch` is `each_member`; a batch size that is not recorded counts as not covered. Replies per proof and the batch size come from these two stored records, never from the reviewer and never from `run.json`. The bound covers the run when `adversary` is `any_prover`, `parameters` is `row`, `conditions_shown` is true, the bound covers one reply and the row's batch, and `program` is `proved` or `stated`.

- UF-1. A Model, Prompt or Reply check failed: red, `check_failed`, basis `test`.
- UF-2. Not read: hollow, `not_read`.
- UF-3. `stated` is false, or no term is recorded: red, `not_stated`.
- UF-4. `adversary` is `weaker`: red, `stated`.
- UF-5. A term is under 80: red, `stated`.
- UF-6. `basis` is `conjectured` or `not_said`, and a term is under 100: red, `stated`.
- UF-7. `basis` is `proved`, the bound covers the run, and every term is 128 or more: green.
- UF-8. `basis` is `proved`, the bound covers the run, and every term is 100 or more: amber in part.
- UF-9. Otherwise: amber in lesser part. The reason names the first condition that fails, in this order: the basis (conjectured, or basis not said); adversary not said; the unit (stated per part, stated per round, unit not said, more than one reply per proof, or replies per proof not recorded when `system.yaml` records no granularity); the batch (stated for batch members handed in together, not for members checked alone, while the harness checks each of the row's N replies in its own call; no bound said for batch members while the row proves N a batch; or the batch size not recorded); the parameters (stated for other parameters, or not shown to be the row's); the conditions (not shown to hold for the row's files); the program (not stated for the verifier program the row runs); then an exponent under 100.

Every petal prints the publisher's expression among its quotes; its reason does not repeat it (amended 2026-11-13, GL-5). An error term 2^-t has exponent t. The cut points read the exponents the publisher states and compute nothing: no bits figure is computed or printed (Q9). 128 and 100 are the Ethereum Foundation's zkEVM security milestones (100-bit provable security by the end of May 2026, 128-bit by the end of 2026), which ethproofs draws as its two soundness colours; 80 is the security strength NIST SP 800-57 Part 1 Rev. 5 no longer holds adequate (§References). A bound proved for the protocol counts here when it covers the row's parameters, unit, batch and adversary, and the publisher states or proves that the program the row runs implements that protocol (`program`); how far a machine-checked proof reaches toward that program is Machine-checked's question (GL-6, Q8).

#### Machine-checked (`machine_checked`)

Facts (`formal`):
- `reach`: `none` (the publisher states that nothing is machine-checked); `part` (some component, the constraints against a specification, or a sub-protocol is machine-checked, with the publisher's coverage count); `protocol` (soundness of the whole protocol is machine-checked but not the relation that encodes the model, or the reverse: exactly one of the two); `protocol_and_statement` (soundness is machine-checked for the whole protocol and for the relation that encodes the model's computation, the theorem stated against a reference definition of the model, but not for the verifier program the row runs); `verifier_run` (a machine-checked soundness theorem covers the verifier program the row runs, from the bytes it reads to its verdict); or `not_stated`.
- `tool`; `theorem` (its full name, as the tool prints it) and `theorem_url` (at the pin).
- `toolchain`: `{name, version}`, copied with its quote from the toolchain file or sentence at the pin and spelled as it writes them; null when the documents name none.
- `trusted_base`: the publisher's list, verbatim items. `axioms`: the declared axioms a build must report, each in the trusted base.
- `input_code_unverified`: true when named code that reads inputs sits outside the proof.
- `scope_card`: for soundness, zero knowledge and completeness, each against the protocol, the verifier run and the prover run, one of `machine_checked`, `paper`, `tested` or `not_stated`, with a quote each.

Stated step: `none` or `not_stated`, red; `part` or `protocol`, amber in lesser part; `protocol_and_statement`, amber in part; `verifier_run` with a non-empty trusted base and `input_code_unverified` false, green; `verifier_run` otherwise, amber in part.

The proof build: `results/<release>/proof-build/<system>/proof-build.json` (schema `proof-build/1`) records one build of the named theorem at the pin: the upstream repository and commit, the theorem's name and link, the toolchain (its name and version, spelled as `toolchain` spells them, and the sha256 digest of the image the build ran in, required), the command, its start and duration, the exit code, the status (`built` or `failed`), the last lines and the axioms the build reports. A record matches the row when its repository and commit are the properties file's pin, its theorem is `theorem`, and its toolchain name and version equal `toolchain`. With `toolchain` null, no record matches. Any other record counts as none, and the reason names it; a record at the pin for the theorem under another toolchain prints "the recorded build used {name} {version}, the publisher pins {name} {version}". Level 1 reads this record and does not make one.

- MC-1. Not read: hollow, `not_read`.
- MC-2. The stated step is red: red, `not_stated` when `reach` is `not_stated`, `stated` when it is `none`.
- MC-3. A Model, Prompt or Reply check failed and the stated step is green: red, `check_failed`, basis `test`.
- MC-4. A matching record has a status other than `built` or an exit code other than 0, or reports a set of axioms other than `axioms`: red, `check_failed`, basis `test`, lowered by the proof build. The reason prints the status and the exit code, or both lists of axioms.
- MC-5. No matching record (including when `toolchain` is null): hollow, `proof_build_not_run`. The petal is not drawn from the publisher's words alone (Q10).
- MC-6. Otherwise: the stated step.

The petal grades soundness only: zero knowledge and completeness are claims about the prover, and they appear on the scope card. The scope card is printed on the system page as recorded facts and sets no state. Every outcome but MC-1 carries the stated step and the facts above in the board's `formal`.

#### Weights hidden (`weights_hidden`)

Facts (`hiding`):
- `stated`: true, false or `not_stated`.
- `verifier_gets_weights`: whether the verifier receives the weights.
- `proof`: `none`; `protocol` (a zero-knowledge theorem exists for the protocol only); or `configuration_run` (its stated parameters include the configuration the row runs, batch size included).
- `programs`: what the publisher says of its programs implementing the proved hiding: `stated`, `expected` or `not_stated`.
- `visible_listed`: whether a list of visible values is published. When it is true, `visible` holds at least one item: the schema refuses an empty list.
- `visible`: that list, each item with a quote and a tag: `statement_io` (prompt, reply, served or refused), `shape` (architecture and sizes), `side_channel` (time, lengths, failures, volume) or `fitted_to_weights` (only when the item's own quote says the value depends on or is fitted to the weights).

- WH-1. The Verify without weights check failed: red, `check_failed`, basis `test`.
- WH-2. Not read: hollow, `not_read`.
- WH-3. `verifier_gets_weights` is true, or `stated` is false: red, `stated`. `stated` is `not_stated`: red, `not_stated`.
- WH-4. `proof` is `none`: amber in lesser part.
- WH-5. `proof` is `configuration_run`, `programs` is `stated`, `visible_listed` is true, `visible` is not empty and no item is tagged `fitted_to_weights`: green.
- WH-6. Otherwise: amber in part; the reason names each condition that is missing.

Items tagged `statement_io`, `shape` or `side_channel` are printed and never set a state.

#### Faithful model (`faithful_model`)

Measured from the rung's `fidelity.json`, basis `test` on every line. Two thresholds per rung come from the honest controls' scores over the same n prompts: T_green = (mean(rerun) + mean(Q8_0)) / 2 and T_upper = (mean(Q8_0) + mean(Q4_K_M)) / 2. The rerun is the honest control with recipe `rerun`; Q8_0 and Q4_K_M are the honest `quantize` controls of those types. A threshold is null, with its cause, when one of its controls is missing, failed, or holds a score count other than n.

A row is **shown above** T when FI-4's sign-flip test on d_i = 2n·s_i − (S_a + S_b) gives p < `fidelity.alpha`, where s_i is the row's score on prompt i and S_a, S_b are the two controls' score sums over the n prompts. Since d_i = 2n·(s_i − T), a positive factor, the test is FI-4's test of the row against T, and the integers keep FI-4's exact count. The test is exact for n ≤ 20; above, its seed follows FI-4 with A the row's system id and B `T_green` or `T_upper`. `iproofs fidelity score` writes the thresholds (`steps`), each row's two tests (`step_tests`) and the fidelity run's slot count (`slots`, copied from `fidelity-run.json`) into `fidelity.json`. The glyph reads the stored tests and runs none, with one exception (FM-4a): a `fidelity.json` scored before 2026-11-13 holds no `steps`, and results are append-only (APP-1), so the board computes `slots`, `steps` and `step_tests` for it from its own stored scores, the rung's `fidelity-run.json` and the beacon round, with the functions `iproofs fidelity score` uses, and writes nothing under `results/`. It recomputes each threshold from the stored controls' scores and stops on a difference (AGENTS.md rule 3). It also ties each non-null stored test `step_tests.<k>` to its threshold and stops on a mismatch: `threshold` is `T_green` for green and `T_upper` for upper, `value` equals `steps.<k>.value`, `n` equals the row's score count, and an exact test's p equals the one FI-4's sign-flip count gives again. alpha is `fidelity.json`'s `test.alpha`, which must equal the level's `fidelity.alpha` when the level is at hand; there is no default. Reasons name each threshold in words with its value and FI-3's unit: "the rerun and Q8_0 midpoint, 283.03 leading tokens"; the test's p, alpha and n stay in `fidelity.json` (amended 2026-11-13, GL-5).

- FM-1. FIDELITY failed: red, `check_failed`.
- FM-2. No `fidelity.json`, FIDELITY undecided, or no scores for the row: hollow, `not_decided`, with the cause.
- FM-3. The policy on the claim card of the row's configuration is not exact match, or no claim card is found: amber in lesser part (the claim accepts tokens other than the proved model's own top token).
- FM-4. No step tests are stored, or T_green or T_upper is null (the rerun, Q8_0 or Q4_K_M control is missing or failed): amber in lesser part; the reason names the control and its cause.
- FM-5. Shown above T_green, and `slots` is 1: green.
- FM-6. Shown above T_upper: amber in part. When the row is also shown above T_green and `slots` is not 1 or not stored, the reason says that the slot count kept green out of reach.
- FM-7. Otherwise (FIDELITY held): amber in lesser part. This includes a row shown above T_green but not above T_upper.

Green needs a fidelity run of one request at a time (`slots` 1), so the rerun that anchors T_green is not moved by batching. Every Level 1 rung names a rerun, a Q8_0 and a Q4_K_M honest control (`levels/L1.yaml`), GPT-2's F32 rung included. A rung without a Q4_K_M control has no T_upper, so its rows stay at amber in lesser part (FM-4).

#### No third party trusted (`no_trusted_party`)

Facts (`trust`):
- `rests_on`: `transparent` (soundness rests on cryptographic assumptions alone and no setup ever produced a secret, as the quotes say or as the reader reads them, with a note, GL-1; public files fixed before the hash, or derived deterministically from public inputs, do not count against it: every non-interactive proof shares them); `open_ceremony` (a setup produced a secret in an open ceremony with a public transcript, whose secret stays unknown if one participant was honest); `fixed_parties` (one honest party among a fixed set, or a challenger in a challenge window); `single_party_setup`; `hardware_key`; `trusted_key`; or `not_stated`.
- `publicly_checkable`: true, false or `not_said`: whether anyone can check a proof file, as opposed to an interactive or designated-verifier check.

- NT-1. Not read: hollow, `not_read`.
- NT-2. `rests_on` is `not_stated`: red, `not_stated`.
- NT-3. `rests_on` is `single_party_setup`, `hardware_key` or `trusted_key`: red, `stated`.
- NT-4. `rests_on` is `fixed_parties`, or `publicly_checkable` is false: amber in lesser part.
- NT-5. `rests_on` is `open_ceremony`: amber in part.
- NT-6. Otherwise (`transparent`, and publicly checkable or not said): green. With no note on `rests_on`, the reason reads "stated to rest on cryptographic assumptions alone, with no setup that produced a secret"; with a note, "read as resting on cryptographic assumptions alone; no quote says no setup produced a secret" (amended 2026-11-13, GL-5).

No reason says that the publisher states something its quotes do not say. No check lowers this petal. Which model a commitment names is not graded here (Q12, RFC-0016 ST-6).

### Order

- OR-1. Only passed rows are ranked, and only inside a rung.
- OR-2. A passed row is ranked only if the level file records a security level its publisher states at the pin (`systems.<id>.security.stated: true`, with words and source). Otherwise it is listed as passed, unranked, "publisher states no security level".
- OR-3. Row A is placed above row B when both have a multiple, A's mean multiple is at most (1 − `order.margin`) times B's, and A's highest session value of m is below B's lowest. A row with a multiple is placed above a row without one. Two rows without a multiple compare the same way on session cost per reply.
- OR-4. A row's position is 1 plus the number of rows placed above it. Rows with equal positions share it. A lone passed, ranked row holds position 1, and the page prints the count of systems run on the rung beside every position.
- OR-5. Under the ranked rows: passed and unranked rows, then rows that have not passed, each group alphabetical. A row that has not passed prints its checks and its figures; it has no position.
- OR-6. The frontier headline names the largest rung with a passed row, the row at position 1 there (or every passed row if none is ranked), its multiple, and the count of systems run on that rung.

### The board file

`iproofs release board` writes `releases/<release>/board.json` (schema `board/1`) from the runs `releases/<release>/release.yaml` lists (less its superseded runs; every run under `results/<release>/` while no `release.yaml` exists), the counted sessions' records, the properties files, any proof-build records and the rungs' `fidelity.json`. The site reads only this file and the claim cards. Shape:

```json
{
  "schema": "board/1", "level": "L1", "level_digest": "sha256:...", "release": "v1.0", "date": "YYYY-MM-DD",
  "price": {"basis": "h200", "usd_per_gpu_hour": 0.0, "date": "YYYY-MM-DD"},
  "request": {"prompt_tokens": 512, "output_tokens": 512, "decoding": "greedy"},
  "frontier": {"rung": "llama-4-maverick", "rows": ["flashprove"], "systems_run": 1} ,
  "rungs": [{
    "id": "llama-4-maverick", "model": "Llama 4 Maverick 17B-128E Instruct", "publisher": "Meta",
    "parameters_total": 400000000000, "requests_per_session": 120,
    "baseline": {"serving": "<serving record id>", "gpus": 4, "concurrency": 64,
                 "gpu_seconds_per_reply": "<quantity>", "ladder": [{"concurrency": 1, "replies_per_gpu_second": "<quantity>"}]},
    "fidelity": {"bar": {"control": "q3_k_s", "mean_prefix": 0.0} , "controls": [{"id": "q8_0", "kind": "honest", "mean_prefix": 0.0, "kl": "<quantity or null>"}]},
    "rows": [{
      "system": "flashprove", "configuration": "exact-match-cp-verify", "commit": "<40-hex>",
      "checks": {"run": {"state": "held", "cause": null, "evidence": ["<path>"]}},
      "passed": true, "ranked": true, "position": 1, "unranked_reason": null,
      "multiple": "<quantity>", "steady_gpu_seconds_per_reply": "<quantity>",
      "steady_generation_gpu_seconds_per_reply": "<quantity>", "steady_proving_gpu_seconds_per_reply": "<quantity>",
      "generation_multiple": "<quantity>", "proving_multiple": "<quantity>",
      "session_generation_gpu_seconds_per_reply": "<quantity>", "session_commit_and_proving_gpu_seconds_per_reply": "<quantity>",
      "session_generation_multiple": "<quantity>", "session_commit_and_proving_multiple": "<quantity>",
      "session_gpu_seconds_per_reply": "<quantity>", "sessions": [{"run_id": "...", "m": 0.0, "session": 0.0, "steady": true}],
      "incomplete_sessions": [{"run_id": "...", "exit_code": 1, "cause": "..."}],
      "fidelity": {"mean_prefix": 0.0, "p_above_bar": 0.0, "p_below_bar": 0.0, "kl": "<quantity or null>", "kl_note": "..."},
      "security": {"words": "...", "source": "<url>"},
      "verify_seconds_per_reply": "<quantity>", "proof_bytes_per_reply": "<quantity>",
      "glyph": [
        {"id": "unforgeable", "state": "amber", "step": "amber_lower", "cause": null, "basis": "statement",
         "reason": "...", "quotes": [{"text": "...", "url": "<link at the pin>"}], "lowered_by": []},
        {"id": "weights_hidden", "state": "amber", "step": "amber_upper", "cause": null, "basis": "statement",
         "reason": "...", "quotes": [], "lowered_by": [], "visible": [{"item": "...", "tag": "side_channel", "quotes": [{"text": "...", "url": "<link at the pin>"}]}]},
        {"id": "faithful_model", "state": "hollow", "step": null, "cause": "not_decided", "basis": "test",
         "reason": "...", "quotes": [], "lowered_by": []},
        {"id": "machine_checked", "state": "hollow", "step": null, "cause": "proof_build_not_run", "basis": "statement",
         "reason": "...", "quotes": [], "lowered_by": [],
         "formal": {"stated_step": "amber_upper", "reach": "protocol_and_statement", "tool": "...", "theorem": "...",
                    "theorem_url": "<link at the pin>", "trusted_base": ["..."], "input_code_unverified": true,
                    "scope_card": {"soundness": {"protocol": {"value": "machine_checked", "quotes": [{"text": "...", "url": "..."}]}}}}},
        {"id": "no_trusted_party", "state": "green", "step": "green", "cause": null, "basis": "statement",
         "reason": "...", "quotes": [{"text": "...", "url": "<link at the pin>"}], "lowered_by": [], "reading": true}
      ]
    }]
  }]
}
```

Every `<quantity>` is a `quantity/1` value with its labels (AGENTS.md rule 2). Rungs are in the level file's order (largest first). A rung no system has run yet is present with `rows: []`. `glyph` holds the five petals in drawing order (GL-5); no field sums them (GL-8). The example's values show the shape only; the scope card holds all nine cells, and `reading` appears only where a fact the decision read carries a note (GL-5).

### Site

- SI-1. The overview is the ladder: the frontier headline, then one section per rung, largest first. A rung section has its head (model, publisher, total parameters, request, baseline line) and its rows in OR-5 order: position, glyph, system name, status (passed, or the checks not held), multiple, session cost per reply in USD, verify time per reply, KL. Rows sort only by the order rule; column heads do not re-sort across positions.
- SI-2. Withdrawn (owner decision, 2026-11-12): the overview prints no line on how its rows are ranked. The order rule, and that the glyph never moves a position, are stated on the checks page.
- SI-3. The system page: the glyph with each petal's step in words, cause, basis, reason and quotes, Machine-checked's scope card as recorded facts (it sets no state) and Weights hidden's list of visible values; the six checks with state, cause and evidence links; the sessions; the cost parts; fidelity beside the rung's controls.
- SI-4 (amended 2026-11-13). Systems not run are listed after the ladder, alphabetical, each with one fixed reason (`licence`, `no public verifier`, `no configuration at the request`, `another kind of check`, `a different statement`, `not yet run`) from `web/_data/facts.json`. `a different statement` marks a system that proves a statement other than Level 1's (that a reply is the committed model's own greedy reply to a prompt the verifier is given), so no row of it could pass the six checks.
- SI-5. No figure of v0.1 is printed. The v0.1 release stays in the repository as a record.
- SI-6. Words: measurement vocabulary only. "Passed" is said of a system on a model ("FlashProve passed on Llama 4 Maverick"), never of a model. No "secure", "best", "neutral" or "independent".
- SI-7. The scale page draws every row on a decade (log) axis, one stored figure at a time: the multiple (or, with no steady state, the whole sessions' multiple, CO-5, with its two parts, CO-7), cost per reply, verify time per reply and proof size per reply (amended 2026-11-13). One lane per rung, largest first, its rows in OR-5 order; every lane of a figure shares one decade grid, so a change of scale between rungs is seen by position. It ranks nothing across rungs: no position, ratio, count or order is printed across lanes, no mark joins two lanes, and lanes are never sorted by a value. Each mark is the row's figure, printed beside it with its labels; a row that has not passed is drawn as an outline, never filled. With no script the page draws every figure (adopted 2026-11-13, Q17).
- SI-9. Teacher-forced figures (FI-10 to FI-15, adopted 2026-11-13): the system page prints, beside FI-3's score in its fidelity section, the row's agreement (mean and median, unit, n, failed prompts with their causes), its KL figure with its n, FI-13's label word for word, whose computation it is and the run record; the fidelity page prints the same per rung with every control and the tests. They are printed as figures only: no glyph, petal, check, position or order reads them.

### Adapter contract amendment (RFC-0005)

- AD-1. `verify` is called with the prompt and the claimed reply of 512 tokens; an adapter MUST pass upstream the range that makes every reply token checked (FlashProve: r = P − 1, e = P + R − 1).
- AD-2. Optional subcommand `logprobs`: input `texts` (token-id lists, the KL chunks as the model's tokenizer reads them); output, per text, the full next-token log-probability distribution at each scored position under `/io/logprobs/`: only the scored positions (the second half of each chunk), row r predicting token n_ctx/2 + r + 1, positions × vocabulary, `float16` little-endian. KL needs the whole distribution, not the log-probability of the next token alone. Used only by FI-7. An adapter without it is valid.
- AD-3. Under exact match a reply MUST be the committed model's own greedy reply (RFC-0017 TASK-3). An adapter generates it with what upstream ships at the pin, or the row's RUN check is `undecided`, cause `system limit`.
- AD-4. Generation marks: an adapter that generates the replies in a phase of its own writes `/io/marks/generation.start` and `/io/marks/generation.end` (empty files, each written under a temporary name and renamed), which the harness times like a proof release (CO-3).
- AD-5. Optional subcommand `perturb`: input the model directory and the level's change; output W′ in `/io/perturbed/` and a record of the tensor, index, old and new stored values, and the system's own digest of W and W′ where it has one. CPU only.
- AD-6. Optional subcommand `mutate_reply`, for a system whose verifier takes no claimed reply and reads the reply from the proof (SASH): input a proof directory, a reply position and a new token; output the proof with that reply value changed where the verifier reads it (and in every field the proof pairs with it), byte for byte otherwise. It decides nothing. C1 for such a system verifies the mutated proof; the trial counts only when upstream's verifier refuses it and accepts the honest twin. A trial decided by adapter code is `void`. Without `mutate_reply`, REPLY is `undecided`, cause `system limit`.
- AD-7. Optional subcommand `score` (amended 2026-11-13, used only by FI-10 to FI-13): input `requests_file`, one request per line with `prompt` and `reply` (token ids), `out_dir` and `top_k`; output under `out_dir`, per request i, `<i>.json` holding `top`, the system's own top token at each reply position (FI-10's alignment), or `failed`, the cause its own code gave; and, with `top_k` above 0, `<i>.topk`: the bytes `TFK1`, the positions and k (uint32), then the ids (int32) and the log-probabilities in nats (float32), each positions × k, row by row, little-endian, most probable first and lower id first among equal values. It wraps documented upstream commands and calls only (AGENTS.md rule 1), proves nothing and decides nothing. An adapter without it is valid: its row prints "not measured" with that cause.

### Levels

- LV-1. A level does not change once frozen: a change of rule is a new level file (`L2`), and releases under a level add runs, never rules.
- LV-2. A new rung: open weights released by the organisation that trained the model, chosen by the level, never by an entrant, and only when the request fits its context (GPT-2's is exactly 1,024 tokens). Level 1's rungs, largest first: Llama 4 Maverick, Llama 3.1 8B, GPT-2.
- LV-3. The Level 2 draft, published with Level 1 so labs can prepare: a soundness floor of 100 bits that a third party recomputes from the parameters as run; a KL bound to the proved computation joining the fidelity gate; a reply chosen after serving.

### Failure modes

| Failure | Response |
|---|---|
| A counted run names another level digest | `release freeze` refuses it |
| A slot has no complete session | RUN `undecided` (`not run`) below five attempts, `failed` at five |
| The system refuses the request (SE-5) | RUN `failed` at once, with the refusal record; no further attempt in that slot |
| A session has fewer than 4 release groups | no steady state, cause `too few groups`; the row prints session cost |
| The baseline ladder fails at a concurrency | that rung of the ladder is recorded failed; full load is chosen among the rest; with none, the rung has no multiple |
| A fidelity control fails to run | it is absent from the bar choice and printed as failed |
| A trace file is missing for a counted verdict | VERIFY WITHOUT WEIGHTS `undecided`, `not run` |
| A statement petal's properties file is missing, is not `properties/2`, or was read at another commit, or the row's commit is not recorded | the petal is hollow, `not_read` (GL-3); `release freeze` refuses the release (GL-9) |
| Machine-checked is stated above red and no proof build matching the row is recorded (another commit, theorem or toolchain, or no pinned toolchain stated) | hollow, `proof_build_not_run` (MC-5) |
| A recorded proof build failed or exited other than 0, or reports a set of axioms other than the declared one | Machine-checked red, `check_failed` (MC-4) |
| A teacher-forced pass of a control fails, or a control is not built in that run | the control is printed with its cause and enters no test (FI-11) |
| A system's own code declines a reference reply (FI-13) | the prompt scores 0, is listed with its cause and stays in n; KL covers the other prompts |
| A row's `score` call fails for another reason, or its adapter has no `score` | the row prints "not measured" with the cause; nothing is scored from a partial run |
| The beacon relays disagree | `level beacon` fails; no prompt set is written |

## Alternatives Considered

- **Rank nothing until two systems share a verifier** (red-team revision 3). Safe, and not a leaderboard: no row could ever hold a position at Level 1. Rejected by the owner, 2026-11-10.
- **Rank across rungs by multiple.** The multiple sets the model's own cost aside, so it is tempting. Rejected: a 400B mixture-of-experts and a dense 8B differ in what serving costs and in how proving scales; the ratio would mix both.
- **Keep the documentation glyph.** Rejected by the owner, 2026-11-10: a reader takes colour for a test result.
- **A request per rung** (512 + 64 on Maverick). Kept as the fallback if a probe shows 512 + 512 cannot run; it would be printed in the rung head and change the multiple's meaning across rungs.
- **KL as a gate.** Rejected for Level 1: the figure comes from a program that is not the proved computation, so it may remove nothing and earn nothing. It is printed. Level 2 binds it.
- **A security floor now.** Rejected for Level 1: tests cannot tell 60 bits from 128, and the levels publishers state are not comparable without recomputation. OR-2 requires a stated level; Level 2 announces the floor. Unforgeable's cut points (UF-5 to UF-8) are not that floor: they read the exponents the publisher states, compute no figure, and set a petal step that never moves a position (GL-4).
- **Keep Any model.** Rejected (Q6): it counted the rungs a system passed on, and the system page already says which rung a row runs on.
- **Compute a bits figure.** Rejected (Q9): a security level the benchmark assigns is the benchmark interpreting security proofs, which RFC-0002 rejects (INV-CLAIM-2; §Alternatives, benchmark-assigned security levels), and the conventions differ by tens of bits (the least exponent, or the bound at a fixed query budget). The publisher's expression is printed as a quote.
- **Draw Machine-checked from the publisher's words.** Rejected (Q10): the only system that fills it today is published by the maker of the model that drafted these rules. The petal stays hollow until a build of the named theorem is recorded (MC-5).

## Drawbacks

- Each rung holds one system at launch. The page prints the count beside every position.
- The fidelity gate is coarse at 15 replies on the 8B rung; it stops gross damage, and KL carries the finer reading.
- Tests cannot tell a proof from a signature. The page says what is not tested.
- The request 512 + 512 has not run on either system at its pin (RISK below).
- A statement petal's step rests on facts one reviewer copies, so a misread fact moves a step. Each fact carries its quote and link at the pin, and a reading carries a note, so anyone can check it.
- Machine-checked is hollow on every row until a proof build is recorded, and today only one system states a machine-checked proof, so the petal says little at launch.
- The Maverick fidelity run uses 16 slots (docs/runbooks/level-1.md), so no Maverick row reaches green on Faithful model (FM-5) until that rung's fidelity run is made one request at a time.

RISK: FlashProve's window is 1,024 tokens and its exact-match whole-reply runs at the pin were scripted, not on the released programs (`integrations/LIMITS.md` L110 to L119). SASH has never run at 512 + 512. Plan: the probes of `docs/runbooks/level-1.md` run first; if either system cannot run the request, the fallback above is put to the owner before any counted run.

## Migration / Rollout

- New: `levels/L1.yaml`, `schema/level/1.schema.json`, `schema/board/1.schema.json`, `iproofs.level`, `iproofs.checks`, `iproofs.board`, `iproofs.fidelity`, `systems/ref-fidelity/`, the workloads `l1-maverick-p512-o512` and `l1-l31-8b-p512-o512`, the prompt generator `beacon-window/1`, `docs/runbooks/level-1.md`.
- Changed: the steady rule (CO-2, CO-3) replaces RFC-0004 INV-SCOPE-5 for Level 1 runs; v0.1's stored figures are not recomputed in place. RFC-0016's properties and `web/_data/criteria.json` no longer drive the site. RFC-0017 Part B is replaced by this RFC. The serving baseline at a matched batch (RFC-0015 SRV-1) is replaced by the ladder (CO-4) for Level 1.
- AGENTS.md, README, PRD: the project ranks inside a rung by the order rule; the no-ranking rule now forbids ranking across rungs and by any other figure.
- Amendment of 2026-11-13 (petals): `properties/2` replaces `properties/1` (a new major; /1 stays in the tree). `board/1` is changed in place (any_model removed, step, cause and lowered_by required, basis run removed): no release is frozen and the one stored board, releases/v1.0/board.json, is recomputed by `iproofs release board` in the same change (RFC-0012 amendment of 2026-11-13). `fidelity/1` gains optional `slots`, `steps` and `step_tests`; the two `fidelity.json` files stored before this amendment are not written again, and the board computes those fields from their stored scores (FM-4a). `proof-build/1` is new; its `toolchain.image` is a required sha256 digest. Review fixes of the same day, in place: `properties/2` gains `bound.batch`, `bound.program` and `formal.toolchain`, and refuses `visible_listed` true with an empty `visible`; the board petal gains the optional `reading`. No RFC-0002 amendment is needed: `properties/2` holds `formal` (RFC-0016 L189).

## Testing Strategy

- `test_derive.py`: release groups and m on the fixture (7.128); a session with three later groups of uneven size is not steady.
- `test_checks.py`: each check's states from synthetic records, including `void` reruns, the interior position and the trace rule.
- `test_fidelity.py`: the exact sign-flip test on n = 15 against a hand count; the bar rule with no qualifying control; the seeded Monte Carlo is deterministic.
- `test_board.py`: the order rule on hand-built rows (margin, spread, ties, unranked, no steady state).
- `test_level.py`: the level file validates; the beacon seed from a stored round.
- `test_glyph.py`: one case per line of each decision table (UF-1 to UF-9, MC-1 to MC-6, WH-1 to WH-6, FM-1 to FM-7, NT-1 to NT-6) on facts built in the test, the strict `<` at 80 and 100 included; replies per proof read from `system.yaml` and the batch size from the workload; the offline check of the expression against its terms (an omitted term, a term that is only part of a number); a proof build under another toolchain; a row with no recorded commit; a stored threshold that its controls do not give, or a stored test not tied to its threshold, stops the board; and the real `systems/flashprove` and `systems/sash` properties files read through the decision functions, one (step, cause) per petal.
- `test_fidelity.py`: the step test against a hand count (n = 3), the Monte Carlo seed above `exact_up_to`, and the thresholds computed from the controls' scores.
- `test_teacher_forced.py`: agreement on a hand-built reply (3 of 4, where the matched prefix is 1); KL on a vocabulary of four tokens (¼ ln 2) and with one token pooled (½ ln 2 + ½ ln ⅔); a position without a list; a failed prompt of a system scores 0 and stays in n; the exact test of a row against a control (1/16).
- Adapter tests on CPU: `test_sash_score.py` (the rows read from the head dumps, the order keys inverted to bf16, a refused request), `test_flashprove_score.py` (the choices at the reply positions, a range-condition failure), `test_ref_fidelity_teacher_forced.py` and `test_ref_fidelity_vllm.py` (one request per position, the lists sorted, the rerun's reversed order).
- `test_freeze.py`: `release freeze` refuses a release with a listed run whose properties file is at another commit, with no `board.json` present, and `validate` refuses a board with a `not_read` petal in a frozen release (GL-9).
- Schema examples, `board/1` changed in place: invalid examples for a step that does not match its state, a red petal without a cause, a hollow petal with a step, an integer step, a petal id outside the five, `formal` on another petal and `check_failed` without `lowered_by`; for `properties/2`, a typed `state`, an unknown petal, a decided fact without quotes and `visible_listed` true with an empty `visible`; for `proof-build/1`, a built record with a nonzero exit code, a failed one without last lines and a null image.

## Conflicts of Interest

This text was drafted with an AI agent, Claude, made by Anthropic, which publishes FlashProve. The rules that most affect FlashProve are the request size (CO-1 counts generation, which FlashProve does in a plug-in), the baseline (CO-4) and OR-2 (FlashProve's card states its levels for the Lean verifier, not for `cp_verify`, which the row runs).

Amendment of 2026-11-13 (§The glyph). These rules were drafted with Claude, made by Anthropic, which publishes FlashProve. On Machine-checked, FlashProve is the only listed system that can be above red today. The proof-build rule keeps it hollow until a build of the named theorem has been recorded at the pin with the pinned toolchain (MC-5). The research report also asked that someone with no tie to a listed system sign off Machine-checked's step table before the petal is drawn. That sign-off is not in the rule (Q10), and leaving it out favours FlashProve.

These readings favour FlashProve and are taken:
- A bound proved for the protocol counts for Unforgeable (Q8). The report marks this as the reading more favourable to FlashProve. The rule also asks that the publisher state or prove that the program the row runs implements the protocol (`bound.program`). FlashProve writes that neither of its figures is claimed for the C++ programs, which the row runs, so its `program` is `not_stated` and the reading does not raise its step today.
- Which model a commitment names is not graded (Q12). The report notes that not grading it keeps FlashProve green on No third party trusted.
- FlashProve's `trust.rests_on: transparent` is a reading, with its quotes: the theorems hold at every public setup of three public files, whatever the committer and the prover, and the soundness theorem has no hypothesis beyond its statement. No sentence at the pin says in words that no setup produced a secret, so the fact carries a note, the petal carries `reading`, and the green reason says "read as" (NT-6). A reviewer who reads it as `not_stated` turns No third party trusted red (NT-2). The definition of `transparent` does not count public files fixed before the hash. FlashProve writes that no file shows its public files were fixed before the provider could tune them to the hash function, and that the reader grants it. The same carve-out applies to SASH's public statement file, so it does not separate the two systems today.
- FlashProve's `formal.reach: protocol_and_statement`: the model statement is the publisher's own Lean integer model, and the publisher writes that no theorem describes its constant look-up tables and that what a scale file switches off was worked out by hand, not proved. Read as `protocol`, the stated step would be amber in lesser part, not amber in part. The petal is hollow today (MC-5), so the reading shows only once a build is recorded.

The other values the integrator read rather than copied also carry a `note`, and the board marks each petal that read one (`reading`, GL-5). On Unforgeable, the batch is the first condition FlashProve's row fails (UF-9); its `conditions_shown` and `program` fail too. FlashProve states that N proofs handed in at once under one commitment, or N members of a batch, cost N times the error of one, and that for proofs checked one after another, or members checked in separate sessions, no bound is stated (`bound.batch: together`). The row proves its replies in batches of 24 and the harness checks each reply in its own verify call, so the bound does not cover the run.

Besides the settings fitted to the weights, two of FlashProve's visible values, that the checks of `cp_commit` passed and the masked sums of the weights, are tagged `fitted_to_weights` by the literal rule, because their quotes say the value depends on the weights. The step does not change: a zero-knowledge proof for the protocol only already sets amber in part (WH-6).

## Decisions

- Q1. Ladder, ranked inside a rung (owner, 2026-11-10).
- Q2. The glyph is the six checks (owner, 2026-11-10); this reverses the documentation glyph and "Not stated drawn as No". Correction (2026-11-13): superseded by the owner's decisions of 2026-11-10 recorded in §The glyph: the glyph is the distance from passing the checks to a perfect prover, the six checks are the entry gate and not the glyph (CH-7), and silence is drawn red (GL-1). The glyph is the five petals of §The glyph.
- Q3. Both rungs are run before anything is announced (owner, 2026-11-10).
- Q4. Disclosure wording is set by the owner before launch.
- Q5. No separate correction release: the project is updated, the Level 1 runs are made, then the site is deployed.
- Q6. The petals are Unforgeable, Weights hidden, Faithful model, Machine-checked and No third party trusted, in that drawing order, each at one of four steps or not decided. Any model is removed: the system page already says which rung a row runs on. Only the verifier trusted is printed as No third party trusted, since the treaty language makes the Verifier a party; its id `no_trusted_party` is kept (adopted 2026-11-13 under the owner's request to update the criteria from the research: the research report's recommendation in its section 1, Machine-checked in the slot of Any model, and its recommended answer to open question 6, the names; not decided by the owner).
- Q7. A property not stated stays red (GL-1) and is drawn as an outline in the red ink, its name not struck; a red that is stated or set by a failed check stays solid, its name struck, its cause in words. Amber in lesser part is drawn as the arm with its end cell cut off (adopted 2026-11-13 under the owner's request to update the criteria from the research: the glyph proposal of 2026-11-12, which the owner accepted, draws amber in lesser part with its end cell cut off and, after its blind readings, proposes the red outline for silence; the research report's answer to its open question 3 was one solid red with the cause in words; not decided by the owner).
- Q8. A bound proved for the protocol counts for Unforgeable when it covers the row's parameters, unit, batch and adversary and the publisher states or proves that the program the row runs implements that protocol (`bound.program`); how far a machine-checked proof reaches toward that program is Machine-checked's (GL-6). Proved comes before magnitude: a conjectured bound reaches amber in lesser part at most. The cut points are 128, 100 and 80 on stated exponents (adopted 2026-11-13 under the owner's request to update the criteria from the research: the research report's recommended answer to its open question 1, narrowed, and its section 2 on grading Unforgeable. The narrowing: the report counts a program the publisher states is meant to implement the protocol; `bound.program` records `not_stated` when the publisher also says the bound is not claimed for that program. This is the reading less favourable to FlashProve, and it moves no step today. Not decided by the owner).
- Q9. The benchmark computes and prints no bits figure: the board prints the publisher's bound as a quote, with its terms, and compares each stated exponent with 80, 100 and 128 (adopted 2026-11-13 under the owner's request to update the criteria from the research: the research report's recommended answer to its open question 2; not decided by the owner).
- Q10. Machine-checked is hollow until a build of the named theorem is recorded at the row's commit, with the pinned toolchain and the declared axioms (MC-5); the scope card is printed in the meantime (adopted 2026-11-13 under the owner's request to update the criteria from the research: the first half of the research report's recommended answer to its open question 5, a recorded build; the second half, a sign-off of Machine-checked's step table by a reviewer with no tie to a listed system, is not adopted and is open to the owner; not decided by the owner).
- Q11. Faithful model's steps are two thresholds from the rung's honest controls: the midpoint between the rerun and Q8_0 for green, the midpoint between Q8_0 and Q4_K_M for amber in part, each shown by FI-4's test; green also needs a fidelity run of one request at a time, and a control a step needs that did not run sets amber in lesser part, FM-4 (adopted 2026-11-13 under the owner's request to update the criteria from the research: the research report's recommended answer to its open question 7 and its Faithful model table. That green needs a fidelity run of one request at a time (`slots` 1) is the criteria brief's of 2026-11-13: the report notes that the rerun runs one request at a time and calls a green threshold from a run of 16 at a time provisional. Where that table draws the petal hollow when a control a step needs did not run, the criteria brief of 2026-11-13 sets amber in lesser part; not decided by the owner).
- Q12. Which model a commitment names is not graded on No third party trusted (RFC-0016 ST-6). It is to be decided before a closed-weights level (adopted 2026-11-13 under the owner's request to update the criteria from the research: the research report's recommended answer to its open question 4, do not grade it yet; the disclosure line the report recommends is left out of this amendment by the criteria brief; not decided by the owner).
- Q13. Architecture hiding is not a petal and not a step (adopted 2026-11-13 under the owner's request to update the criteria from the research: the research report's section 2, architecture hiding stays out of the glyph; the disclosure list the report recommends is left out of this amendment by the criteria brief; not decided by the owner).
- Q14. `board/1` is changed in place, not given a new major: no release is frozen, and the one stored board is recomputed in the same change, as §Migration and RFC-0012's amendment of 2026-11-13 say (adopted 2026-11-13 under the owner's request to update the criteria from the research: decided by the implementation spec of 2026-11-13, not by the report; not decided by the owner).
- Q15. A row with no steady state also prints its session cost per reply in two parts, generation and commit and proving, each over the baseline (CO-7, amended 2026-11-13). Why: FlashProve's row has no steady state, and 91 % of its session cost per reply is its generation phase, so its session multiple read alone is taken for the cost of proving. LV-1 holds: the parts are computed from records every counted session already holds and add two printed figures; no rule of entry (the six checks), of order (OR-3 reads m, else the session cost) or of the headline (CO-5's figure and its label) changes, and `levels/L1.yaml` and its digest are unchanged. `board/1` gains the four optional row fields in place, and releases/v1.0/board.json is recomputed in the same change (Q14) (adopted 2026-11-13 on the research report's recommendation on FlashProve's multiple, option (b), with the second part named for the phases in it; open to the owner's flip, not decided by the owner).
- Q16. Wording of 2026-11-13, labels only (no id, key, anchor, state or rule changes): the check NO WEIGHT FILE is printed VERIFY WITHOUT WEIGHTS (it names what is tested: the verifier reached its verdicts with no model file and no GPU), its id `no_weight_file` kept; a hollow petal's step is printed "undecided", the word a check uses; CO-5's label reads "whole sessions of N replies"; the site prints the multiple under the head "Cost vs serving" and the verifier's time as "verify time per reply", so "check" names only the six checks.
- Q17. The scale page's lanes share one decade grid (SI-7), and the site's words "Nothing is compared across models" read "Nothing is ranked across models", as OR-1 says. A grid per rung, each lane on its own values, is one argument of `panel_html` in `web/draw/scale.py` (adopted 2026-11-13 for the scale page; open to the owner, who may set one grid per rung; not decided by the owner).
- Q19. Teacher-forced top-token agreement and KL are printed beside FI-3 and gate nothing (FI-10 to FI-15, adopted 2026-11-13 at the owner's request). Whether a level names `teacher_forced_agreement` as its gating score, in the place of FI-3's matched prefix, is open to the owner and not decided here: FI-10 says what that one line of the level file would change.

## References

- [RFC-0004](0004-metrics-timing-grades.md) INV-SCOPE-5; [RFC-0008](0008-negative-controls.md) C1 to C3, P1; [RFC-0015](0015-reference-rows.md) SRV-6; [RFC-0017](0017-requests-tasks-and-tested-states.md) INV-REQ-2, TASK-2, TASK-3.
- drand quicknet: <https://docs.drand.love/> (read 2026-11-10).
- [RFC-0002](0002-claim-card.md) INV-CLAIM-2 and §Alternatives Considered; [RFC-0016](0016-glyph-properties-and-states.md) ST-5, ST-6, INV-GLYPH-1.
- Ethereum Foundation, zkEVM security foundations: <https://blog.ethereum.org/2025/12/18/zkevm-security-foundations> (read 2026-11-12); ethproofs, soundness colours: <https://github.com/ethproofs/ethproofs/blob/dev/components/zkvms-table/zkvm-pie-chart.tsx> (read 2026-11-12).
- NIST SP 800-57 Part 1 Rev. 5, Recommendation for Key Management: <https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-57pt1r5.pdf> (read 2026-11-12).
