# RFC-0017: Requests, tasks and tested states

- Authors: 0xchqrles
- Created: 2026-11-10
- Requires: RFC-0003, RFC-0004, RFC-0005, RFC-0008, RFC-0009, RFC-0012, RFC-0015, RFC-0016
- Amended by RFC-0018 (2026-11-10): Part B is replaced. The Level 1 request is `p512-o512` on every rung; control coverage, the baseline and the verifier of record follow RFC-0018.

Write "None." where a section has no content. Normative text uses MUST, SHOULD and MAY as defined in RFC 2119.

## Summary

Every figure of v0.1 is per token covered. A token covered is a position a proof binds, and the two systems bind positions for different ends: one FlashProve request covers a 1,024-token window and its proof is checked for one output token; one SASH request covers 1,024 prompt positions and 64 output positions and its proof is checked for 64 output tokens. This RFC makes the request the unit a reader compares: it adds five per-request figures computed from stored runs, fixes the request shape that is printed beside them, and defines a task, the rule for when two rows may be read side by side. It adds the median to every statistic. It then fixes the direction of the next runs: the controls each card row still lacks, a serving baseline at the proved precision, and one row per verifier a system documents. No existing figure, formula, state or stored value changes.

The RFC has two parts. Part A is in force with this RFC and is implemented. Part B is decided here and comes into force with the runs that need it; until then its figures are absent, never estimated.

## Motivation

Evidence. Values are from `releases/v0.1/index.json` unless stated: grade `derived`, tier `reported`, means over n completed repetitions, profile `prover-h200-hosted` for the systems.

- FlashProve on `fp-maverick-w1024-b24`: 0.0056112 gpu_s/token at `prove.steady` (n = 4). SASH on `sash-l31-8b-c1024`: 4.8442 gpu_s/token at `prove.session` (n = 3; SASH has no steady scope, RFC-0004 Q2). Neither number says what a reader asks: what one request costs.
- The two requests differ. The FlashProve adapter sends the range r = T − 1, e = T, so `verify` checks one token, the one after a 1,024-token window ([`systems/flashprove/README.md`](../systems/flashprove/README.md) §verify). The SASH workload proves 1,024 prompt positions and a greedy continuation of 64 tokens. `workloads/fp-maverick-w1024-b24.yaml` has `shape.output_tokens: 1`; `workloads/sash-l31-8b-c1024.yaml` has 64.
- A figure per output token would measure the adapter, not the prover. FlashProve at its pin: "A request holds a window of exactly T tokens: the prompt, then the reply, then filler tokens"; "At full size, T is 1,024"; "To check a whole reply of R tokens (its end token included) after a prompt of P tokens, set r = P - 1 and e = P + R - 1" ([`docs/verifying.md` L115 to L123](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/docs/verifying.md#L115-L123)). And: "With every token of a stored reply checked, under the looser clipped-gap policy, the rate at 24 per batch is 108.67 ± 2.8 tokens/second [...] The same requests, with no reply token checked, ran at 108.73 ± 2.7" ([`guide/performance.md` L17](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/performance.md#L17); upstream figures, grade external, tier reported). The cost of a request is the pass over its window, whatever number of reply tokens the range names. The benchmark's range of one token is the adapter's choice, so dividing by it would move the figure 64-fold with no change in the prover.
- A session mean pools sessions of different lengths. Production serving on `sash-l31-8b-c1024`, profile `serving-h200x1-hosted`, GPU-seconds per request at `prove.session`, n = 5: mean 12.29, median 0.4996, range 0.4927 to 58.47. The five runs served 1, 50, 360, 360 and 360 requests (the first before the session was lengthened, the second the sizing capture of RFC-0015 SRV-1) and read 58.47, 1.497, 0.4960, 0.4996 and 0.4927: start-up is spread over the session, so a session figure depends on its length. The Maverick row has the same shape: 120 requests read 7.101, three runs of 5,136 read 0.2532 to 0.2568. Of the 297 statistics of v0.1 that have a spread, 34 have a maximum above twice their minimum; all 34 are production serving, none is a proving system's, and none is an input of an overhead, which reads the steady scope of the lengthened runs only (RFC-0004 INV-DERIVE-2).
- The glyph says a card-row state is "not contradicted by the benchmark's negative controls" (RFC-0016 INV-GLYPH-5). In v0.1 two runs hold a `controls.json`, both of FlashProve on `fp-maverick-w1024-b1`. SASH and FlashProve at batch 24 have none. In both records C3, P1 and P2 are `not_applicable`, so no row has an outcome for any control mapped to Model bound (RFC-0016 control map), and Whole output checked has outcomes on one configuration. One outcome is outside its expected set: C6 `accepted` in the run `2026-11-08-flashprove-fp-maverick-w1024-b1-prover-h200-hosted-3` (it was `rejected` in the other, `2026-11-09-flashprove-fp-maverick-w1024-b1-prover-h200-hosted-2`); C6 maps to no property.
- The overhead divides a prover on 4.839-bit weights and one GPU by production serving of the publisher's FP8 release on four GPUs (RFC-0015 SRV-6). [PRD §6](../docs/PRD.md#6-scope-of-v01) asked for "the same model and precision served unproved on the same hardware". Both questions are fair; v0.1 answers one.
- FlashProve's card is `exact-match-cp-verify`. Its Formally verified cell is No and its Security level cell Not stated, because the statements its documentation makes are for the Lean verifier and set nothing on this row (RFC-0016 SRC-1). The Lean verifier is a documented accept path; no row runs it.

Scenarios:

1. A policy analyst wants the cost of proving one answer. The site prints a cost per 1M tokens covered. They cannot tell how many tokens covered one answer is.
2. A second system joins on its own model and shape. Its per-token figure sits in another table. The reader needs a rule that says when two per-request costs are the same question.
3. A reviewer sees Yes on SASH's Model bound and assumes a tampered-weights test stands behind it. None was run.

## Goals

- A per-request figure for GPU-seconds, GPU cost, proof size and check time, recomputable from every stored run of v0.1 with no new run.
- The shape of the request (prompt tokens, output tokens checked, tokens covered) printed with those figures.
- One rule for comparing two rows: the task.
- The median stored beside the mean in every statistic.
- A written list of what the next runs add, with the rule each one puts in force.

## Non-Goals

- Removing, renaming or redefining any figure of RFC-0004. The per-token and per-weight-bit figures stay as they are.
- A score, a rank or an order across tasks.
- Changing a glyph property, a state, the control map or the printed words of RFC-0016.
- Running anything. Part B names runs; it adds none.

## Proposed Design

### Terms

- **Request.** One prompt and the output tokens the verifier is given for it. `requests_count` counts them (RFC-0004 §Recorded metrics). A system may release one proof for a request (both v0.1 systems) or several.
- **Request shape.** Three numbers: P, the prompt tokens (`shape.prompt_tokens`); N, the output tokens checked (`shape.output_tokens`); W, the tokens covered (D-TPR). W follows the coverage kind of RFC-0004 INV-TOK-1: `window` gives W = P, since the token after the window is checked and its own position is not computed; `prompt_plus_output` gives W = P + N.
- **Task.** A request shape together with a decoding rule: (P, N, `decoding.rule`). Its id is `p<P>-o<N>`, for example `p1024-o64`.

### Part A: in force

#### Request rules

- INV-REQ-1. Every request of a workload has the workload's shape, so a per-request figure is the per-token figure times the tokens one request covers: X per request = X per token × `tokens_covered_total` / `requests_count`.
- INV-REQ-2. The output tokens checked for a request are the tokens of `claimed_output` of its proofs, which the harness passes to `verify` from its own record (AGENTS.md rule 6). Summed over the proofs of one request they MUST number `shape.output_tokens`; any other count is an `adapter` failure at step `prove` (`iproofs.adapter.check_requests`). The rule holds on every completed run under `results/v0.1/` (48 runs, checked on 2026-11-10), so the shape printed for a stored run is what its verifier was given.
- INV-REQ-3. A page prints a per-request figure with P and N beside it. Per-request figures of different tasks are never put in one table, sorted together or divided by one another.
- INV-REQ-4. No figure per output token is computed or printed. For a `window` system the range of checked tokens is a request parameter with no measured effect on cost (Motivation), so such a figure would rank adapters. A reader who wants it divides a per-request figure by the N printed beside it and sees that N.

#### Per-request figures

Additions to the RFC-0004 catalogue. Level, grade, tier, quality flags and null propagation are as RFC-0004 sets them for a repetition-level derived metric; D-STAT runs over each.

| Formula id | Metric id | Formula | Unit | Scope | Null when |
|---|---|---|---|---|---|
| D-TPR | `tokens_covered_per_request` | `tokens_covered_total` / `requests_count` | token/request | none | either is 0 (`not_applicable`) |
| D-GSPR-S | `gpu_seconds_per_request_<S>` | D-SPT-S × `gpus` × `tokens_covered_total` / `requests_count` | gpu_s/request | S | D-SPT-S null (its reason); `gpu_count` missing: the metric is absent, as D-GSPT-S; `requests_count` 0 (`not_applicable`) |
| D-COST-REQ-S | `cost_per_request_<S>` | D-COST-1K-S / 1000 × `tokens_covered_total` / `requests_count` | USD/request | S | D-COST-1K-S null (its reason); `requests_count` 0 (`not_applicable`) |
| D-BPR | `proof_bytes_per_request` | `proof_bytes_total` / `requests_count` | B/request | none | `proof_bytes_total` absent (`missing_input`), as D-BPT on a reference row |
| D-VSPR | `verify_seconds_per_request` | `verify_seconds_total` / `requests_count` | s/request | `verify` | `verify_seconds_total` absent (`missing_input`), as D-VSPT |

S is `prove.steady`, `prove.session` or `whole_wall`, as for D-SPT-S. `gpus` is `inputs.gpu_count` (RFC-0004 INV-DERIVE-8). Each formula is evaluated left to right on the inputs it names, never on another derived per-request value, so a freeze can evaluate it for a stored run (below). D-GSPR-S and D-COST-REQ-S apply to a reference row: production serving serves a request, and the overhead of a request equals the overhead of a token, since both sides have the same shape.

The units `token/request`, `gpu_s/request`, `USD/request`, `B/request` and `s/request` join `quantity/1`; `gpu_s/request`, `USD/request` and `s/request` are time-based and name a scope (INV-QTY-3). A per-request quantity and a per-token quantity have different units, so no formula can mix them by mistake.

Stored runs. Every run of v0.1 was written before these formulas. They join `FREEZE_FORMULAS`: the freeze evaluates them from each run's unchanged `run.json`, writes them to `freeze_derived`, and D-STAT points there (RFC-0004 Q3). A run written from now on holds them in its own `run.json`, and gate G4 recomputes them.

#### Worked example

The fixture of RFC-0004 §Worked example (invented round numbers, not a result): 5,000 tokens covered, 5 requests, 1 GPU, 3.60 USD per GPU-hour, 10,000,000 proof bytes, 25 s of verification.

| Formula | Computation | Expected |
|---|---|---|
| D-TPR | 5,000 / 5 | 1,000 token/request |
| D-GSPR-prove.steady | 0.01 × 1 × 5,000 / 5 | 10 gpu_s/request |
| D-COST-REQ-prove.steady | 0.01 / 1,000 × 5,000 / 5 | 0.01 USD/request |
| D-COST-REQ-prove.session | 0.0125 / 1,000 × 5,000 / 5 | 0.0125 USD/request |
| D-BPR | 10,000,000 / 5 | 2,000,000 B/request |
| D-VSPR | 25 / 5 | 5 s/request |

#### What v0.1 reads per request

From the freeze of 2026-11-10. Grade `derived`, tier `reported`, source `releases/v0.1/index.json`; ranges are min to max over the completed repetitions; cost at the release's price basis (RFC-0006 C7).

| Row (workload, profile) | Request shape | GPU-seconds per request | GPU cost per request | Proof size per request | Check time per request |
|---|---|---|---|---|---|
| FlashProve (`fp-maverick-w1024-b24`, `prover-h200-hosted`) | P 1,024, N 1, W 1,024 | 5.746 (5.696 to 5.805), `prove.steady`, n = 4 | 0.008531 USD (0.008457 to 0.008618), `prove.steady` | 18.78 MB | 16.74 s (16.64 to 16.88), `verify` |
| FlashProve (`fp-maverick-w1024-b1`, `prover-h200-hosted`) | P 1,024, N 1, W 1,024 | 22.25 (22.16 to 22.36), `prove.steady`, n = 4, 1 failed | 0.03303 USD (0.03290 to 0.03319), `prove.steady` | 18.78 MB | 16.68 s (16.63 to 16.74), `verify` |
| SASH (`sash-l31-8b-c1024`, `prover-h200-hosted`) | P 1,024, N 64, W 1,088 | 5,271 (5,209 to 5,369), `prove.session`, n = 3, 1 failed | 7.825 USD (7.733 to 7.971), `prove.session` | 44.72 GB | 3,568 s (3,507 to 3,608), `verify` |
| Production serving (`fp-maverick-w1024-b24`, `serving-h200x4-hosted`, matched load) | P 1,024, N 1, W 1,024 | 0.09416 (0.09381 to 0.09459), `prove.steady`, n = 4 | 0.0001398 USD | not applicable | not applicable |
| Production serving (`sash-l31-8b-c1024`, `serving-h200x1-hosted`) | P 1,024, N 64, W 1,088 | 0.3345 (0.3311 to 0.3379), `prove.steady`, n = 4 | 0.0004966 USD | not applicable | not applicable |

The two systems run different tasks on different models at different scopes. This table lists them; it compares nothing (INV-REQ-3).

#### Statistics

- ST-1. Every D-STAT statistic, and every statistic over the proofs of one repetition, stores `stats.median` beside n, n_failed, mean, stdev, min and max. The property is optional in `quantity/1`, so documents written before it stay valid, and gate G4 recomputes a stored statistic without it.
- ST-2. The `value` of a statistic stays its mean (RFC-0004 §Statistics, INV-QTY-8). The median is a second reading, not a repair: where a configuration pools sessions of different lengths (Motivation), neither number describes one population. The repair is [Q4](#decisions).

#### Site

A system page's table of other figures gains three rows per setup, after the existing ones: the tokens one request covers, with P and N in the row's name; GPU-seconds per request; GPU cost per request. Each of the last two is the steady statistic, or the session one where the system has no steady scope, and names its scope (as the per-weight-bit column does, RFC-0004 INV-DERIVE-7). The overview is unchanged. Proof size and check time per request are in the index and not on a page: with one proof a request, they equal the two overview figures.

### Part B: decided, in force with its runs

#### B1. Tasks

- TASK-1. Two workloads are the same task when P, N and the decoding rule are equal. Rows of one task may share a table and a sort for their per-request figures, on any models: each row names its model, and the overhead (RFC-0004 D-OVERHEAD-S) is the figure that sets the model's own cost aside.
- TASK-2. The first common task MUST fit every system that joins it, by what each documents at its pin:
  - FlashProve: prompt and reply share one window of T = 1,024 tokens, and a reply may end one token past it, so P + N ≤ 1,025 (Motivation, [`docs/verifying.md` L125 to L128](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/docs/verifying.md#L125-L128)).
  - SASH: the prompt is a power of two and a whole number of blocks, and the generated block is the output: `assert a.prefix > 0 and (a.prefix & (a.prefix - 1)) == 0, "prefix must be a power of two"` ([`gen_ids.py` L52 to L53](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/harness/witness/gen_ids.py#L52-L53); `systems/sash/entrypoint` `geometry` refuses any other shape). So for a reply longer than one token P is 512 or less, to leave room for it in FlashProve's window, and N divides P.
  - SASH's existing shape, 1,024 + 64, does not fit FlashProve's window. A prompt of 960 does not fit SASH.
  The proposed task is `p512-o64`, greedy ([Q5](#decisions)). For FlashProve r = 511 and e = 575, with 448 filler tokens and the token file unused; its own full-size runs on real weights served replies under `--max-tokens 64` ([`integrations/LIMITS.md` L117 to L120](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/integrations/LIMITS.md#L117-L120)). For SASH it is 9 blocks of 64 positions, a part of the grid its three completed v0.1 runs proved (17 blocks of 64). A second task, `p512-o512`, fills FlashProve's window with no filler and uses the one block size SASH's own runs record ("Every recorded run has `S = 512`"); it comes after, because FlashProve's pin shows a reply that long under exact match on synthetic weights only ([`integrations/README.md` L56 to L66](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/integrations/README.md#L56-L66)).
- TASK-3. Under exact match the reply of a task request MUST be the committed model's own. FlashProve at its pin: "At exact match a reply passes only if every token is the integer model's own choice: of 96 stored replies each from stock vLLM at 16 bits and at FP8, none did"; "Through vLLM with a plug-in that is designed to compute the integer model exactly, 48 of 48† short replies were proved and checked" ([`guide/performance.md` L35](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/performance.md#L35)). That plug-in is in the repository at the pin (`integrations/vllm/integer_model/`, "lets vLLM run the integer model"); upstream says of the runs that used it: "None of them was made on the released programs, or with the scripts exactly as they are in this repository" ([`integrations/LIMITS.md` L110](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/integrations/LIMITS.md#L110)). The adapter may use only what upstream documents (AGENTS.md rule 1). If a system cannot produce such a reply at its pin, its row for the task says so and holds no figure; a looser acceptance policy is another claim class and another card (RFC-0002 §Configuration identity).

RISK: the plug-in path may not run inside the adapter contract (no network, one container, vLLM stopped while `cp_prove` runs). Plan: the workload lands with the adapter change and its first run, never before.

#### B2. Control coverage

- COV-1. For each card row, every control the RFC-0016 control map gives a property SHOULD have an outcome in at least one run the row reads, and that outcome SHOULD be a pass or a contradiction, not `not_applicable`, `void`, `error` or absent. Today: Model bound has none on any row; Whole output checked has C1, C2 and C4 on FlashProve at batch 1 only.
- COV-2. What is missing, in runs:
  - SASH: the suite against one repetition whose proofs were kept (`--keep-io`), in parts (RFC-0008 §Split suites); then the perturbed commitment for C3 and P1.
  - FlashProve: the perturbed commitment (`iproofs controls --prepare-perturbed`), then the suite in a batch-1 job and in a batch-24 job, the second for C7, which needs two requests in one batch.
- COV-3. Until then the system page prints "not run" for each such control, as RFC-0016 OVR-7 already requires. This RFC adds no mark to the overview: how the overview tells a tested Yes from an untested one is a site change of its own, shown to the owner before it merges.

#### B3. A serving baseline at the proved precision

- BASE-1. A second overhead, D-OVERHEAD-SP-S (`overhead_vs_same_precision_<S>`): the system's GPU-seconds per token over those of an unproved engine serving the workload's own files, at the precision as proved, on the system's profile. It isolates the cost of proving. D-OVERHEAD-S, against production serving, stays the headline and keeps its name.
- BASE-2. The id and the formula are reserved; no code computes it until a reference system serves the proved precision. For the Maverick workloads that is the llama.cpp adapter on the branch `ref-serve-gguf`. SASH quantizes at load and no engine serves its W8A8 weights unproved, so its row keeps one overhead and says so.

#### B4. One row per verifier

- VER-1. Where a system documents more than one accept path with different statements (FlashProve: `cp_verify` and the Lean verifier `verify`), each is a configuration with its own claim card and row (RFC-0002 §Configuration identity 5). The benchmark runs the Lean verifier as a second FlashProve card on the batch-1 workload. Its check time is part of what the row shows.

### Failure modes

| Failure | Response |
|---|---|
| A proof claims a number of output tokens other than the shape's | `adapter` failure at `prove` (INV-REQ-2) |
| A stored run lacks an input of a per-request formula | that value is null with `missing_input` in `freeze_derived`; the run stays in n of every other statistic |
| A per-request figure is asked for a CPU-only test profile | D-GSPR-S is absent (no GPU count), the others are computed |
| Two rows of different tasks are put in one per-request table | a review failure (INV-REQ-3); no gate checks page layout |

## Alternatives Considered

- **A figure per output token.** Considered because it is the unit a reader thinks in. Rejected (INV-REQ-4): upstream's own runs show no cost for checking more reply tokens in a window, so the figure would follow the range an adapter sends.
- **Replace the per-token figures.** Considered because two units side by side invite confusion. Rejected for now: the owner keeps the old figures, stored runs carry them, and the units differ, so they cannot be mixed in a formula.
- **A `task` field in `workload/1`.** Considered to make the task explicit. Deferred: P, N and the decoding rule already sit in the record, and a field that repeats them could disagree with them.
- **The median as the statistic's `value`.** Considered because it resists one far-off run. Deferred to Q4: it would change every published mean.
- **A mark on the overview for untested states, now.** Considered because the gap is real. Deferred (COV-3): it is a drawing decision, and the data is already on the system page.

## Drawbacks

- A request is not one size. A per-request figure means nothing without its shape, which is why INV-REQ-3 binds them.
- Until a common task runs, the per-request figures of the two systems answer different questions, as the per-token ones do. The RFC names the unit; only B1 makes rows comparable.
- Five more metric ids and five more units.

## Migration / Rollout

- `quantity/1` (additive, RFC-0012 §Schema versioning): five units, three of them in the INV-QTY-3 list; the metric ids `tokens_covered_per_request`, `proof_bytes_per_request`, `verify_seconds_per_request`, `gpu_seconds_per_request_<S>`, `cost_per_request_<S>`; optional `stats.median`. The invalid example `statistic.unknown-key` now uses the key `mode`.
- `releases/v0.1/index.json` is frozen again: 261 keys added (the per-request statistics, their `freeze_derived` values and each `median`); no existing value changed; `inputs_digest` unchanged.
- No `run.json` changes. No adapter changes: INV-REQ-2 already holds on every stored run and for the test systems.
- Part B, in order, with the runs each needs. Costs are estimates from stored job durations and the list prices in `docs/runbooks/hf-jobs.md`, not measurements:
  1. Control coverage (B2): about 95 USD, mostly CPU.
  2. Same-precision baseline and recompute rows on H200 (B3): about 20 USD.
  3. The first task (B1): about 30 USD for FlashProve, plus SASH repetitions at the new shape.
  4. The Lean verifier row (B4): about 80 USD, mostly waiting on the check, about 24 minutes per proof by upstream's figure ([PRD §1](../docs/PRD.md#1-problem); external, reported).

## Testing Strategy

- `test_derive.py::test_worked_example`: the five expected values above, from `expected.json`.
- `test_derive.py::test_freeze_values_fill_only_missing_keys`: a stored run gets D-TPR, D-BPR and D-VSPR at freeze (1,000, 2,000,000, 5), and D-COST-REQ-S null with `missing_input` when its D-COST-1K-S is not stored.
- `test_stats.py::test_stat_median_is_not_the_mean_when_one_run_is_far_off`: 577, 16,000, 16,100, 16,200 gives mean 12,219.25 and median 16,050.
- `test_adapter_requests.py::test_claimed_tokens_per_request_must_match_the_shape`: one proof of 64 tokens passes at N = 64; two proofs of one request summing to 64 pass; 63 fails as `adapter` at `prove`.
- `test_site_e2e.py::test_every_figure_traces_to_the_index`: each new row's printed value is its stored statistic at four significant digits.
- `test_freeze.py::test_deterministic_index`: the golden index, with the new keys.

## Decisions

- Q1. The request is the unit a reader compares. Per-token and per-weight-bit figures stay, unchanged.
- Q2. No figure per output token (INV-REQ-4).
- Q3. The task is derived from the workload shape; no new workload field.
- Q4. Open, recommended: pages keep the mean, and a session-scope statistic of a reference row reads only the runs of the session length the release uses (`batches_per_session_run` of the system's entry), as the overhead join already does for the steady scope; a run of another length is listed as left out, with that reason. Printing the median instead would hide the mix: it reads 0.4996 here only because three of the five runs are the long ones.
- Q5. Open, recommended: the first common task is `p512-o64`, greedy (TASK-2); `p512-o512` is the second. `p960-o64`, proposed before SASH's pin was read, is not runnable by SASH.
- Q6. Recommended: no mark on the overview. The system page already prints, per property, which mapped controls ran and which did not; the gap is closed by running them (B2), after which a mark would show nothing.

## References

- FlashProve at `9e2bdd8ff5bf9c62f18263d7dac189b0400b260c`: [`docs/verifying.md`](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/docs/verifying.md), [`guide/performance.md`](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/performance.md), read 2026-11-10.
- [RFC-0004](0004-metrics-timing-grades.md) §Tokens covered, §Derived metric catalogue, §Statistics, Q3.
- [RFC-0008](0008-negative-controls.md) §Split suites; [RFC-0016](0016-glyph-properties-and-states.md) §Negative control override.
- SASH at `eb95bfa887299d1637550228d42086c27cbb2b3b`: [`harness/witness/gen_ids.py`](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/harness/witness/gen_ids.py), read 2026-11-10.
- [RFC-0015](0015-reference-rows.md) SRV-1, SRV-6; [PRD §6](../docs/PRD.md#6-scope-of-v01).
