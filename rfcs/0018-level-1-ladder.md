# RFC-0018: Level 1: the ladder, six checks, cost and fidelity

- Authors: 0xchqrles
- Created: 2026-11-10
- Requires: RFC-0003, RFC-0004, RFC-0005, RFC-0006, RFC-0008, RFC-0009, RFC-0010, RFC-0012, RFC-0014, RFC-0015, RFC-0017

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
- Every state on the page is the outcome of a test we ran, recomputable from stored records.
- One request for the whole level, so a multiple means the same thing on every rung.
- A cost figure that a hostile expert cannot move by choosing a window, a batch or a baseline.
- A fidelity gate that stops a copy quantized far from the original, and a KL figure printed beside it.
- A level file frozen before the first counted run, so no constant is chosen after seeing a row.

## Non-Goals

- Testing soundness or weight secrecy. No check attempts a forged proof. The page says so.
- Recomputing a publisher's security level. It is printed as stated (Level 2 draft, below).
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
- SE-4. A session stops at the rung's spending cap (`rungs[].cap_usd`, else `sessions.cap_usd`), recorded as incomplete with cause `cap`. The cap is a constant of the level, the same for every system on a rung.
- SE-5. A refusal ends the slot at once. When the system's own code declines the request with a reason about its inputs (a refusal it raises on purpose, quoted from the run's last lines: not a crash of our adapter, a host fault, a timeout, out of memory or the cap), RUN is `failed` without further attempts: the slot's prompts and greedy replies are fixed, so a rerun proves the same request and meets the same refusal. A reviewer records it in `results/<release>/<system>/refusals/slot-<k>.json`, naming the run, the refusal line and the upstream source line that raises it (owner decision, 2026-11-11).

### Cost

All figures are in GPU-seconds of bound H200 GPUs; USD prints beside each at the release's price basis (RFC-0006 C7). Prover and baseline use the same GPU and the same price, so the multiple is the same in either unit.

- CO-1. **Session cost per reply.** For one session: GPU-seconds from the start of `commit` to the release of the Nth proof, over N. Generation is inside it wherever it happens. The row prints the mean of the three counted sessions and each session's value.
- CO-2. **Release groups.** Proofs released within `steady.group_gap_s` (1 s) of the previous release form one group. Group g has size n_g and release time t_g (its last release).
- CO-3. **Steady seconds per further reply, m.** For one session with groups 1..G: m = (t_G − t_1) × gpus / (n_2 + ... + n_G). It counts every GPU-second spent on the replies released after the first group. Where the adapter generates all replies in a phase of its own before proving (FlashProve: `cp_prove` refuses a GPU another process holds), that phase is not inside any group interval; the adapter marks its start and end (AD-4), the harness times both marks as it times a release, and m adds the phase's GPU-seconds divided by N. So m always includes generation. It is valid when G − 1 ≥ `steady.min_later_groups` (3) and every later group's per-reply time, (t_g − t_{g−1}) / n_g, is within `steady.tolerance` (5 %) of the median of those times. Otherwise the session has no steady state, with its cause (`too few groups`, `uneven groups`). A row has a steady state when all three counted sessions have one; its m is their mean.
- CO-4. **Baseline.** The rung's serving record (RFC-0015 SRV-6): the publisher's own release, served by the pinned engine on the fewest H200 that hold it. At each concurrency c of `baseline.ladder` (1, 2, 4, ..., 1,024) it serves one warm-up batch and then `baseline.timed_batches` (3) timed batches of c distinct prompts from the rung's ladder prompts (PR-3), each batch sent whole, with the request's decoding. A per-batch cache salt keeps the engine's prefix cache from reusing a prompt across batches. Rate r_c = replies per GPU-second over the timed batches. Full load is the lowest c with r_c ≥ (1 − `baseline.plateau`) × max r. When that is the ladder's top rung, the rate was still rising more than `baseline.plateau` there, so the ladder never reached the engine's capacity: the rung has no baseline ("not saturated") until the ladder is extended. The first Maverick run rose 32 % from c = 128 to 256 against a KV cache with room for about 593 such requests, so the ladder runs to 1,024 (the engine's default batch limit) on `baseline.prompts` = 4,096 distinct prompts. The baseline's seconds per reply is 1 / r at full load. Its concurrency, rate and the whole ladder print on the rung's page. The run's reply token ids are kept beside its run.json, by digest, not in git (RFC-0013 SIZE-1); the baseline reads only release times.
- CO-5. **Multiple.** m over the baseline's seconds per reply, with both halves printed. A row with no steady state has no multiple; it prints its session cost per reply over the baseline's seconds per reply, labelled "cold sessions of N replies".
- CO-7. **Generation and proving.** Where the adapter generates the replies in a phase of its own (AD-4), m splits in two: the generation part, the phase's GPU-seconds over N, and the proving part, m less it. The row prints both beside m, each also over the baseline's seconds per reply. The order rule reads m alone. A system with no such phase has no split; its generation, if any, is inside the proving interval.
- CO-6. Every figure is computed in `iproofs.derive` from stored records (AGENTS.md rule 3) and recomputed by gate G4. The fixture `harness/tests/fixtures/derive/release-groups/` holds the release times of the v0.1 run `2026-11-09-flashprove-fp-maverick-w1024-b24-prover-h200-hosted-1`: five groups of 24, later per-reply times 7.116, 7.136, 7.141 and 7.119 s, m = 7.128 GPU-seconds per request (one token checked at batch 24). The other three H200 runs read 7.060, 7.082 and 7.195; v0.1 published 5.746.

### The six checks

Each check ends `held`, `failed` or `undecided`. An undecided check names its cause, one of: `system limit` (the system cannot do what the test needs, quoted), `not run` (the operator has not run it), `not resolved` (the test ran and decided nothing), `not reproduced` (failed in our adapter, not yet reproduced outside it). An undecided check is never worded as a failure. `failed` from an adapter-run test needs a reproduction record (CH-8).

| Check | Id | Held when | Failed when | Evidence |
|---|---|---|---|---|
| RUN | `run` | three slots each have a complete session (SE-1), built from the public pin, unpatched, no weakening flag | a slot has five incomplete runs or a recorded refusal (SE-5), or a counted session used a weakening flag | `run.json` of every session |
| MODEL | `model` | P1 (RFC-0008: commit W, prove with W′, one weight changed) produced no accepted proof in 3 of 3 trials, and C3 (an honest proof verified against the commitment of W′) was refused in 3 of 3 trials | any trial of either accepted | `controls.json` |
| PROMPT | `prompt` | C2 (one prompt token changed at a seeded position) refused in 3 of 3 trials | any trial accepted | `controls.json` |
| REPLY | `reply` | every accepted proof covers all 512 reply tokens (RFC-0017 INV-REQ-2), and C1 refused at the first, the last and one seeded interior reply position, 3 of 3 trials each | coverage short, or any trial accepted | `run.json`, `controls.json` |
| NO WEIGHT FILE | `no_weight_file` | every counted verdict came from a verify call (a) with no GPU visible, (b) on a filesystem holding no model file of the workload (removed or never fetched), (c) under a file-open trace that names no model file | the trace names a model file, or a verify call needed one | `verify-trace/` of every session |
| FIDELITY | `fidelity` | the row's replies score above the rung's bar (§Fidelity) | the bar scores above the row | `fidelity.json` of the rung |

- CH-1. The checks run against the counted sessions' honest proofs. MODEL, PROMPT and REPLY reuse RFC-0008's controls with their seeds, honest twins and `void` rule; only the trial counts and positions above are new. A trial whose honest twin was not accepted is `void` and is rerun with the next seed, at most 10 seeds per series (each C1 position is its own series); 3 counted trials are needed.
- CH-1a. A failed control prove (P1) is the prover's refusal only when the trial names the reason the prover gave. A trial whose line is only the harness's "<kind>: prove exited <code>" decided nothing and counts as `error`; a prove that ends in a Python traceback from the adapter's own entrypoint is recorded as `error` (RFC-0008 §Outcomes). Found 2026-11-13: FlashProve session 1's three P1 trials stopped in the adapter (`FileExistsError` on its work directory) before FlashProve ran, and had been read as refusals.
- CH-1b. P1 may come from a control run of the row: `iproofs run --level L1 --session K --control-run --control-suite`, slot K's first prompt at batch 1 (its P1 proves at that batch too: P1 asks only whether a prove with W′ yields an accepted proof), `control: true` in run.json, never a session (SE-3) and never printed as one. MODEL takes P1 trials from a complete control run whose manifest names the level digest, workload, image and adapter commit of the row's counted sessions; C1, C2 and C3 come from counted sessions only. Why: P1 commits W and proves with W′ against that commitment, and a system that draws a fresh secret at each commit (FlashProve) can prove for a session's commitment only inside that session; when a session's P1 decided nothing (CH-1a) and its state is gone, the commit of its own a control run makes is the way to run P1 at the same pin. Found 2026-11-13.
- CH-2. The weight change for MODEL is fixed per system before the first counted run and recorded in the level file: one stored code in a dense tensor every request reads, changed by one step in the representation the system commits. For a system that quantizes at load (SASH), the change MUST survive quantization: it moves the stored integer code. The adapter makes W′ itself through its `perturb` subcommand (AD-5), so the change is the one the level names and no harness code reads the system's format. A system whose commitment draws a fresh secret on each commit (FlashProve) shows the change by the system's own weight digest tool on W and W′, not by the commitment id. If no change can be shown, MODEL is `undecided`, cause `not run`, until one is found. P1 and C3 are control jobs: an adapter MAY accept W′ there in place of the published files it otherwise requires, and only there (AGENTS.md rule 4).
- CH-3. REPLY's interior position is `seeded_index(control_seed, "C1-interior", k, 510) + 1` for trial k, so it is never the first or last.
- CH-4. NO WEIGHT FILE: the trace is `strace -f -e trace=open,openat,openat2 -o <file>` around the adapter's verify process (or the hosted equivalent). The harness reduces it to the list of paths opened with their sizes and writes `verify-trace/<proof_id>.json`. A path counts as a model file when it is, or its realpath is, a file listed in the workload's `model.files` or under the model directory. A trace tool missing from the image makes the check `undecided`, cause `not run`.
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

### The glyph

The glyph shows how close a row is to a perfect prover: one that cannot be fooled, hides the weights, proves the publisher's own model, runs on any model, and asks the user to trust only the verifier. A fully green glyph means all five hold in full. Passing the checks is the bare minimum; the glyph is the distance from there to perfect (owner decision, 2026-11-10).

| Petal | Id | Basis | Green | Amber | Red |
|---|---|---|---|---|---|
| Unforgeable | `unforgeable` | statement, lowered by tests | a soundness level of at least 128 bits, proven, for the verifier code the row runs (a proof or formal verification that covers that code, not only the protocol) | a level that is conjectured, below 128 bits, stated per part only, or proven for the protocol but not for the code run | no level stated; or our Model, Prompt or Reply check failed (the verifier accepted a false statement) |
| Weights hidden | `weights_hidden` | statement, lowered by tests | zero knowledge proven for the program run, with no leak beyond public sizes | hidden with leaks the publisher lists, or proven for the protocol but not for the program run | the checker receives the weights, hiding is off or not stated; or our No weight file check failed |
| Faithful model | `faithful_model` | our fidelity run | the row's replies are not shown below a second run of the reference (FI-4 test, reference rerun above the row: p ≥ alpha) | the row scores above the bar (FIDELITY held) and the reference rerun scores above the row | FIDELITY failed |
| Any model | `any_model` | our runs | the system passed on every rung of the level | it passed on more than one rung, not all | it passed on one rung or none |
| Only the verifier trusted | `no_trusted_party` | statement | soundness rests on cryptographic assumptions alone, as the publisher states them (for example a random oracle): no setup ceremony, hardware maker's key or third party. Public files fixed before the hash do not count against it: every non-interactive proof shares them | one honest party among several, or a setup the publisher says anyone can reproduce | a trusted setup, hardware attestation, or a trusted key; or not stated |

- GL-1. A petal based on a statement is read from the publisher's documents at the row's pin, recorded in `systems/<name>/properties.yaml` (schema `properties/1`) with the deciding quotes, their links and the date read. A reviewer sets it; CI checks the file against its schema. Silence is red, printed as "not stated in <documents read> at <commit>" (owner decision, 2026-11-10: a guarantee nobody states is one nobody can rely on).
- GL-2. Tests only lower: a failed check sets its petals red whatever the statement says; a held check never raises a statement.
- GL-3. A measured petal not yet decided (FIDELITY undecided, no completed attempt on a rung) is drawn hollow, with its cause.
- GL-4. The glyph is drawn only for rows we ran. It never moves a position: the order is cost among passed rows (OR-1 to OR-6), and the page says so.
- GL-5. `iproofs.glyph` computes every petal from the properties file and the stored records; the board file carries each petal's state, basis, reason and quotes.

### Order

- OR-1. Only passed rows are ranked, and only inside a rung.
- OR-2. A passed row is ranked only if the level file records a security level its publisher states at the pin (`systems.<id>.security.stated: true`, with words and source). Otherwise it is listed as passed, unranked, "publisher states no security level".
- OR-3. Row A is placed above row B when both have a multiple, A's mean multiple is at most (1 − `order.margin`) times B's, and A's highest session value of m is below B's lowest. A row with a multiple is placed above a row without one. Two rows without a multiple compare the same way on session cost per reply.
- OR-4. A row's position is 1 plus the number of rows placed above it. Rows with equal positions share it. A lone passed, ranked row holds position 1, and the page prints the count of systems run on the rung beside every position.
- OR-5. Under the ranked rows: passed and unranked rows, then rows that have not passed, each group alphabetical. A row that has not passed prints its checks and its figures; it has no position.
- OR-6. The frontier headline names the largest rung with a passed row, the row at position 1 there (or every passed row if none is ranked), its multiple, and the count of systems run on that rung.

### The board file

`iproofs release board` writes `releases/<release>/board.json` (schema `board/1`) from the release index, the counted sessions' records and the rungs' `fidelity.json`. The site reads only this file and the claim cards. Shape:

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
      "session_gpu_seconds_per_reply": "<quantity>", "sessions": [{"run_id": "...", "m": 0.0, "session": 0.0, "steady": true}],
      "incomplete_sessions": [{"run_id": "...", "exit_code": 1, "cause": "..."}],
      "fidelity": {"mean_prefix": 0.0, "p_above_bar": 0.0, "p_below_bar": 0.0, "kl": "<quantity or null>", "kl_note": "..."},
      "security": {"words": "...", "source": "<url>"},
      "verify_seconds_per_reply": "<quantity>", "proof_bytes_per_reply": "<quantity>"
    }]
  }]
}
```

Every `<quantity>` is a `quantity/1` value with its labels (AGENTS.md rule 2). Rungs are in the level file's order (largest first). A rung no system has run yet is present with `rows: []`.

### Site

- SI-1. The overview is the ladder: the frontier headline, then one section per rung, largest first. A rung section has its head (model, publisher, total parameters, request, baseline line) and its rows in OR-5 order: position, glyph, system name, status (passed, or the checks not held), multiple, session cost per reply in USD, check time per reply, KL. Rows sort only by the order rule; column heads do not re-sort across positions.
- SI-2. Withdrawn (owner decision, 2026-11-12): the overview prints no line on how its rows are ranked. The order rule, and that the glyph never moves a position, are stated on the checks page.
- SI-3. The system page: the glyph with each petal's state, basis, reason and quotes; the six checks with state, cause and evidence links; the sessions; the cost parts; fidelity beside the rung's controls.
- SI-4. Systems not run are listed after the ladder, alphabetical, each with one fixed reason (`licence`, `no public verifier`, `no configuration at the request`, `another kind of check`, `not yet run`) from `web/_data/facts.json`.
- SI-5. No figure of v0.1 is printed. The v0.1 release stays in the repository as a record.
- SI-6. Words: measurement vocabulary only. "Passed" is said of a system on a model ("FlashProve passed on Llama 4 Maverick"), never of a model. No "secure", "best", "neutral" or "independent".

### Adapter contract amendment (RFC-0005)

- AD-1. `verify` is called with the prompt and the claimed reply of 512 tokens; an adapter MUST pass upstream the range that makes every reply token checked (FlashProve: r = P − 1, e = P + R − 1).
- AD-2. Optional subcommand `logprobs`: input `texts` (token-id lists, the KL chunks as the model's tokenizer reads them); output, per text, the full next-token log-probability distribution at each scored position under `/io/logprobs/`: only the scored positions (the second half of each chunk), row r predicting token n_ctx/2 + r + 1, positions × vocabulary, `float16` little-endian. KL needs the whole distribution, not the log-probability of the next token alone. Used only by FI-7. An adapter without it is valid.
- AD-3. Under exact match a reply MUST be the committed model's own greedy reply (RFC-0017 TASK-3). An adapter generates it with what upstream ships at the pin, or the row's RUN check is `undecided`, cause `system limit`.
- AD-4. Generation marks: an adapter that generates the replies in a phase of its own writes `/io/marks/generation.start` and `/io/marks/generation.end` (empty files, each written under a temporary name and renamed), which the harness times like a proof release (CO-3).
- AD-5. Optional subcommand `perturb`: input the model directory and the level's change; output W′ in `/io/perturbed/` and a record of the tensor, index, old and new stored values, and the system's own digest of W and W′ where it has one. CPU only.
- AD-6. Optional subcommand `mutate_reply`, for a system whose verifier takes no claimed reply and reads the reply from the proof (SASH): input a proof directory, a reply position and a new token; output the proof with that reply value changed where the verifier reads it (and in every field the proof pairs with it), byte for byte otherwise. It decides nothing. C1 for such a system verifies the mutated proof; the trial counts only when upstream's verifier refuses it and accepts the honest twin. A trial decided by adapter code is `void`. Without `mutate_reply`, REPLY is `undecided`, cause `system limit`.

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
| A trace file is missing for a counted verdict | NO WEIGHT FILE `undecided`, `not run` |
| The beacon relays disagree | `level beacon` fails; no prompt set is written |

## Alternatives Considered

- **Rank nothing until two systems share a verifier** (red-team revision 3). Safe, and not a leaderboard: no row could ever hold a position at Level 1. Rejected by the owner, 2026-11-10.
- **Rank across rungs by multiple.** The multiple sets the model's own cost aside, so it is tempting. Rejected: a 400B mixture-of-experts and a dense 8B differ in what serving costs and in how proving scales; the ratio would mix both.
- **Keep the documentation glyph.** Rejected by the owner, 2026-11-10: a reader takes colour for a test result.
- **A request per rung** (512 + 64 on Maverick). Kept as the fallback if a probe shows 512 + 512 cannot run; it would be printed in the rung head and change the multiple's meaning across rungs.
- **KL as a gate.** Rejected for Level 1: the figure comes from a program that is not the proved computation, so it may remove nothing and earn nothing. It is printed. Level 2 binds it.
- **A security floor now.** Rejected for Level 1: tests cannot tell 60 bits from 128, and the levels publishers state are not comparable without recomputation. OR-2 requires a stated level; Level 2 announces the floor.

## Drawbacks

- Each rung holds one system at launch. The page prints the count beside every position.
- The fidelity gate is coarse at 15 replies on the 8B rung; it stops gross damage, and KL carries the finer reading.
- Tests cannot tell a proof from a signature. The page says what is not tested.
- The request 512 + 512 has not run on either system at its pin (RISK below).

RISK: FlashProve's window is 1,024 tokens and its exact-match whole-reply runs at the pin were scripted, not on the released programs (`integrations/LIMITS.md` L110 to L119). SASH has never run at 512 + 512. Plan: the probes of `docs/runbooks/level-1.md` run first; if either system cannot run the request, the fallback above is put to the owner before any counted run.

## Migration / Rollout

- New: `levels/L1.yaml`, `schema/level/1.schema.json`, `schema/board/1.schema.json`, `iproofs.level`, `iproofs.checks`, `iproofs.board`, `iproofs.fidelity`, `systems/ref-fidelity/`, the workloads `l1-maverick-p512-o512` and `l1-l31-8b-p512-o512`, the prompt generator `beacon-window/1`, `docs/runbooks/level-1.md`.
- Changed: the steady rule (CO-2, CO-3) replaces RFC-0004 INV-SCOPE-5 for Level 1 runs; v0.1's stored figures are not recomputed in place. RFC-0016's properties and `web/_data/criteria.json` no longer drive the site. RFC-0017 Part B is replaced by this RFC. The serving baseline at a matched batch (RFC-0015 SRV-1) is replaced by the ladder (CO-4) for Level 1.
- AGENTS.md, README, PRD: the project ranks inside a rung by the order rule; the no-ranking rule now forbids ranking across rungs and by any other figure.

## Testing Strategy

- `test_derive.py`: release groups and m on the fixture (7.128); a session with three later groups of uneven size is not steady.
- `test_checks.py`: each check's states from synthetic records, including `void` reruns, the interior position and the trace rule.
- `test_fidelity.py`: the exact sign-flip test on n = 15 against a hand count; the bar rule with no qualifying control; the seeded Monte Carlo is deterministic.
- `test_board.py`: the order rule on hand-built rows (margin, spread, ties, unranked, no steady state).
- `test_level.py`: the level file validates; the beacon seed from a stored round.

## Conflicts of Interest

This text was drafted with an AI agent, Claude, made by Anthropic, which publishes FlashProve. The rules that most affect FlashProve are the request size (CO-1 counts generation, which FlashProve does in a plug-in), the baseline (CO-4) and OR-2 (FlashProve's card states its levels for the Lean verifier, not for `cp_verify`, which the row runs).

## Decisions

- Q1. Ladder, ranked inside a rung (owner, 2026-11-10).
- Q2. The glyph is the six checks (owner, 2026-11-10); this reverses the documentation glyph and "Not stated drawn as No".
- Q3. Both rungs are run before anything is announced (owner, 2026-11-10).
- Q4. Disclosure wording is set by the owner before launch.
- Q5. No separate correction release: the project is updated, the Level 1 runs are made, then the site is deployed.

## References

- [RFC-0004](0004-metrics-timing-grades.md) INV-SCOPE-5; [RFC-0008](0008-negative-controls.md) C1 to C3, P1; [RFC-0015](0015-reference-rows.md) SRV-6; [RFC-0017](0017-requests-tasks-and-tested-states.md) INV-REQ-2, TASK-2, TASK-3.
- drand quicknet: <https://docs.drand.love/> (read 2026-11-10).
