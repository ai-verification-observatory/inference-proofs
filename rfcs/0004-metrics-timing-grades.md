# RFC-0004: Metrics, timing scopes and grades

- Authors: AbdelStark
- Created: 2026-11-03
- Requires: RFC-0003, RFC-0012
- Amended by RFC-0018 (2026-11-10): for Level 1 runs the steady scope is the release-group rule (RFC-0018 CO-2, CO-3), which replaces INV-SCOPE-5. v0.1's batch-membership rule overcounts FlashProve's steady requests (119 counted, 96 produced), so its published 5.746 GPU-s per request reads 7.060 to 7.195 under the new rule; v0.1 records stay as stored.

## Summary

This RFC fixes the metrics every run records, the timing scope every time-based number names, the grade every number carries, the rule for counting tokens covered, the catalogue of derived metrics with their exact formulas, and the statistics reported across repetitions. Derived numbers are computed by `iproofs.derive` from stored raw numbers and are never typed by hand. A number without a scope (when it is time-based), a grade, a tier and a source is invalid and fails CI (RFC-0013).

## Motivation

The first two systems publish rates under different scopes. SASH's results repository names each number's scope (`commit`, `stwo total`, `whole wall`, `loop`, `primitive`) and grade (`measured`, `derived`, `projected`, `external`, `asserted`). Its 4,096-context headline is 1.251 positions/s in loop scope and 0.840 positions/s in whole-wall scope over 4,608 positions (grade external, tier reported, source `sg-ai-safety-hub/zk-inference-results` at `11decec3c0b62c707618aab5deb82750b355d202`). FlashProve's headline is 111.23 ± 0.92 tokens/s of prefill at 24 requests per batch, steady state with start-up and commitment excluded; with start-up counted over a five-batch session it is 103.60 tokens/s (both grade external, tier reported, source `anthropics/FlashProve` at `9e2bdd8ff5bf9c62f18263d7dac189b0400b260c`). The same run gives different rates under different scopes, so a rate without its scope cannot be compared with anything (PRD §1, PRD G2, PRD F3). This RFC makes the scope part of the number and fixes how each scope is bounded.

## Goals

- Every recorded metric has a stable id (the key in `run.json` `metrics`), a unit from the RFC-0012 unit vocabulary, and a scope rule.
- Every timing scope is defined by two observable boundary events, both timestamped by the harness clock (RFC-0011).
- Every derived metric has a formula id, an exact formula, named inputs, a unit and a null rule, and `iproofs derive --check` reproduces every stored derived value bit for bit.
- Upstream figures enter only as `external` quantities with their upstream scope kept and the mapping to a harness scope labelled exact, approximate or none.
- Repetition statistics are fixed: n, n_failed, mean, sample standard deviation, min, max.

## Non-Goals

- Latency percentiles per request and queueing metrics (no batch or queueing workload exists in v0.1; Q1).
- FLOP-based normalisers (rejected, see Alternatives Considered; a multiply-accumulate form of D-SPAB-S is open as Q4).
- A normalised proof size (succinct proofs barely grow with the model, so it would favour larger models by construction).
- How the measurements are taken (RFC-0011), how cost inputs are chosen (RFC-0006), how quantities are serialised (RFC-0012), how tiers are assigned (RFC-0007).
- Pricing CPU time or host memory (RFC-0006 rule 5).

## Proposed Design

### Vocabularies

The unit, grade, tier and `null_reason` enums are defined once in the shared quantity schema (`schema/quantity/1.schema.json`, RFC-0012). This RFC owns their meaning.

Grades (every number carries exactly one):

| Grade | Meaning | Allowed `source.kind` |
|---|---|---|
| `measured` | read by the harness from an artifact of this project's run | `harness`, `adapter` |
| `derived` | computed by `iproofs.derive` from other quantities by a formula in this RFC | `derivation` |
| `projected` | from a cost model; the model and its inputs are named in `source.ref` | `derivation` |
| `external` | read from a public source at a pinned commit or URL; upstream scope and grade kept | `upstream` |
| `asserted` | an input that is not measured (for example a price), with source and date | `reference_file` (the reference file, or a workload record the runner copies into run.json `inputs`, RFC-0003 WB-4) |

INV-GRADE-1: a quantity with grade `derived` or `projected` MUST name a formula id from the catalogue below in `source.ref`.
INV-GRADE-2: a quantity with grade `measured` and `source.kind: adapter` is an adapter-reported timing. It MUST NOT feed any derived metric in the catalogue below. It is displayed beside harness numbers, labelled adapter-reported.
INV-GRADE-3: a `derived` quantity's grade stays `derived` even when one of its inputs is `asserted` (a price). The asserted input is listed in `source.inputs`.

### Timing scopes

Every time and every rate MUST name exactly one scope (INV-SCOPE-1). Scope boundaries are harness clock events (`time.monotonic_ns()`, RFC-0011). "Release time" of a proof is the instant the harness observes the atomic rename of `/io/proofs/.tmp-<proof_id>/` to `/io/proofs/<proof_id>/` (RFC-0005, RFC-0011).

| Scope | Start event | End event | Tokens attributed |
|---|---|---|---|
| `setup` | `setup` container call start | `setup` call exit | none (not a rate scope) |
| `commit` | `commit` call start | `commit` call exit | none (not a rate scope) |
| `prove.session` | `prove` call start | release time of the last proof r_k | all proofs 1..k |
| `prove.steady` | last release among the requests with `request_index` < b (b = batch size; r_1 for b = 1) | release time of the last proof r_k | requests with `request_index` ≥ b (proofs 2..k for b = 1) |
| `whole_wall` | `commit` call start | release time of the last proof r_k | all proofs 1..k |
| `verify` | `verify` call start for one proof, 8-CPU verifier container | that call's exit | the proof's tokens |
| `verify.single_thread` | same, 1-CPU verifier container | that call's exit | the proof's tokens |
| `primitive` | adapter-reported only | adapter-reported only | adapter-declared |

Boundary rules:

- Model download and image pull are never inside any scope. `setup` is excluded from `whole_wall`: setup is a one-off build or load that the workload does not repeat per request; the commitment is per-run work (each v0.1 FlashProve run commits fresh, `-M 1`) and is included.
- INV-SCOPE-2: `prove.steady` requires k >= 2. With k < 2 its seconds and rate are `null` with `null_reason: fewer_than_two_proofs`.
- INV-SCOPE-3: if the release watcher reports `observable: false` (the system declares `incremental_proofs: false`, or all proofs appeared within one observation, RFC-0011 §Proof release watcher), `prove.steady` is `null` with `null_reason: not_externally_observable`, and `prove.session` and `whole_wall` are still reported, because their end event is still the last release.
- INV-SCOPE-4: for any successful job, `commit` start <= `prove` start <= r_1 <= r_k. A violation is an `internal` error (RFC-0010).
- INV-SCOPE-5 (amendment of 2026-11-09): the steady scope is defined by batch membership, not by release order. With the workload's `batch_size` b, the first batch is the requests with `request_index` < b. `prove.steady` starts at the last release among the first batch's requests, and ends at r_k. Its tokens are those of the requests with `request_index` ≥ b released after that start: a later-batch request released at or before the start did its work before the window, so it leaves the steady tokens, and the run records the warning "N later-batch request(s) released at or before the steady start, left out of the steady tokens". For b = 1 this is r_1 and proofs 2..k, as before. It is null with `fewer_than_two_proofs` when no later-batch request is released after the start (fewer than two batches completed, among others), and null `missing_input` when b > 1 and any proof lacks `request_index`. A system that releases requests within a batch gets the same boundary and token set as one that releases each batch at its end; one that interleaves batches gets the same boundary, and its token set drops the later-batch requests released before it. The rule applies to proving and reference systems alike, so both sides of D-OVERHEAD-S count the same batches. Every manifest records the rule (`workload.steady_rule: batch-membership`). Runs recorded before the amendment keep their stored `tokens_covered_steady` and steady seconds (APP-1). A release labels a configuration with such a run at b > 1 `steady_boundary: "first-proof boundary (before 2026-11-09)"` in its index entry, and a run at b > 1 without `steady_rule` joins no D-OVERHEAD-S, on either side (INV-DERIVE-2).
- Container start-up overhead is inside each call's time and is not subtracted. The `info` call's wall time is recorded as `info_seconds` so a reader can see the order of magnitude.

RISK: an upstream that writes every proof only at process exit makes `prove.steady` unobservable from outside. Resolution: the adapter README states whether upstream emits proofs incrementally at the pin; if it does not, the row shows `prove.steady` as null with the reason, and the upstream steady figure appears only as `external`. A later RFC MAY admit adapter-reported per-batch timestamps as a labelled secondary steady figure once a system needs it.

RISK: SASH proves one sequence as a grid of segments, and one proof in this benchmark's sense is the whole set of segment proofs for a sequence plus the passing grid check (RFC-0005). With one sequence per job (RFC-0003), k = 1, so `prove.steady` is null by INV-SCOPE-2 and SASH's `loop` figure is shown only as `external` with mapping `approximate`. No token count is apportioned to individual segments (Q2).

### Mapping from upstream scopes

Upstream numbers enter through `systems/<name>/external.yaml` as quantities with grade `external`, tier `reported`, `source.kind: upstream` and two extra fields defined in RFC-0012: `upstream_scope` (the upstream's own words) and `mapping` (`exact`, `approximate`, `none`). `scope` holds the mapped harness scope, or `null` when `mapping` is `none`.

| Harness scope | SASH upstream scope | Mapping | FlashProve upstream scope | Mapping |
|---|---|---|---|---|
| `commit` | `commit` (per run) | exact | `cp_commit` | exact |
| `prove.steady` | `loop` | approximate | steady rate, start-up and commitment excluded | approximate |
| `prove.session` | not published | none | rate with start-up counted over a session | approximate |
| `whole_wall` | `whole wall` | approximate | not published | none |
| `verify` | per-segment verification summed per sequence | approximate | `cp_verify` | approximate |
| `primitive` | `primitive` | exact | not published | none |
| none | `stwo total` | none | | |

INV-MAP-1: the harness's own scopes are authoritative. An `external` quantity is never mixed into a derived metric with `measured` inputs; derived metrics over external inputs are computed only for the run-campaign budget (docs/spec/08-performance-budget.md) and carry grade `projected`.

Mappings are approximate because the upstream boundary events differ from ours (for example, whether start-up of the proving process precedes the first batch timestamp). The site prints "approximate" beside every such number.

### Tokens covered

INV-TOK-1: tokens covered counts the positions whose computation a proof binds, as declared in the claim card `coverage` field (RFC-0002) and computed by the harness from the workload shape (RFC-0003). When `system.yaml` declares `proofs.tokens_covered: declared_per_proof`, the adapter also reports `tokens_covered` per proof in `out.json` (RFC-0005); a mismatch with the harness count is an `adapter` error and fails the job.

The coverage kind is the value of `proofs.tokens_covered` in `system.yaml` ([RFC-0005](0005-adapter-contract.md#systemyaml)); a third kind, `declared_per_proof`, takes the adapter's per-proof count after the INV-ADAPTER-7 check.

| Coverage kind (claim card) | Tokens covered by one proof |
|---|---|
| `window` (FlashProve v0.1) | `prompt_tokens` of the window (prompt = window length, output = 0) |
| `prompt_plus_output` (SASH v0.1) | `prompt_tokens + output_tokens` of the sequence (prompt and output reported separately) |

So `fp-maverick-w1024-b24` covers 1,024 tokens per proof and `sash-l31-8b-c4096` covers 4,096 + 512 positions per proof, consistent with the 4,608 positions SASH reports for that shape (external, reported, SASH results repo at the pin).

INV-TOK-2: a repetition is successful only if every honest proof's verdict is `accept`. A repetition with any honest proof not accepted is recorded as failed at step `verify` (RFC-0010), counts in `n_failed`, and contributes no rate. Rates therefore never mix accepted and rejected work.

### Recorded metrics

Keys of `run.json` `metrics` (one object per repetition). All have grade `measured`, tier `reported`, `source.kind: harness` unless stated.

| Metric id | Unit | Scope | Definition |
|---|---|---|---|
| `info_seconds` | s | `setup` | wall time of the `info` call (recorded for container overhead; listed under `setup` scope because it precedes setup) |
| `setup_seconds` | s | `setup` | wall time of the `setup` call |
| `commit_seconds` | s | `commit` | wall time of the `commit` call |
| `prove_session_seconds` | s | `prove.session` | r_k minus `prove` call start |
| `prove_steady_seconds` | s | `prove.steady` | r_k minus the steady start (r_1 for b = 1; the first batch's last release for b > 1, INV-SCOPE-5) |
| `whole_wall_seconds` | s | `whole_wall` | r_k minus `commit` call start |
| `prove_call_seconds` | s | `prove.session` | wall time of the whole `prove` call (may exceed `prove_session_seconds` by process teardown) |
| `proofs_count` | count | null | k, proofs released |
| `requests_count` | count | null | requests in the job (`batch_size × batches_per_session`) |
| `tokens_covered_total` | token | null | sum over proofs 1..k |
| `tokens_covered_prompt` | token | null | prompt part of the above |
| `tokens_covered_output` | token | null | output part of the above |
| `tokens_covered_steady` | token | null | sum over requests with `request_index` ≥ b released after the steady start (proofs 2..k for b = 1, INV-SCOPE-5) |
| `proof_bytes` | B | null | Statistic over proofs: bytes of all parts of one proof |
| `proof_bytes_total` | B | null | sum of `proof_bytes` over proofs |
| `verifier_download_bytes` | B | null | bytes of `verifier_files` from `commit` (once per commitment) |
| `prover_keep_bytes` | B | null | bytes of `prover_files` from `commit` |
| `verify_seconds` | s | `verify` | Statistic over proofs of one `verify` call, 8 CPUs |
| `verify_seconds_total` | s | `verify` | sum over proofs of the above |
| `verify_single_thread_seconds` | s | `verify.single_thread` | Statistic over proofs, 1 CPU |
| `verify_host_memory_peak_anon` | B | null | max over verify calls (RFC-0011) |
| `<step>_gpu_memory_peak` | MiB | null | for step in `commit`, `prove` (RFC-0011) |
| `<step>_gpu_util_mean`, `<step>_gpu_util_p95` | % | null | for step in `commit`, `prove` |
| `<step>_gpu_energy` | J | null | optional, for step in `commit`, `prove` |
| `<step>_host_memory_peak_kernel` | B | null | cgroup `memory.peak`, for step in `commit`, `prove` |
| `<step>_host_memory_peak_anon` | B | null | sampled `memory.stat` `anon` max, for step in `commit`, `prove` |
| `<step>_cpu_seconds` | s | `commit` or `prove.session` | cgroup `cpu.stat` `usage_usec` difference over the call |
| `verdicts_accept_count` | count | null | honest proofs accepted |
| `adapter_phases.<name>` | s | `primitive` | adapter-reported; `source.kind: adapter`; INV-GRADE-2 applies |

A "Statistic over proofs" is a quantity whose `value` is the mean and whose `stats` object holds n, mean, stdev, min, max across proofs of one repetition (`n_failed` is 0 here by INV-TOK-2).

### Derived metric catalogue

Inputs named `metrics.X` are recorded metrics of the same repetition. `ref.*` inputs come from the matching reference-system configuration (RFC-0015). `price` is `cost.price_per_gpu_hour_usd` from `reference/<release>.yaml` (asserted, RFC-0006). `gpus` is `gpu.count` of the run's profile, the GPUs the configuration holds (INV-DERIVE-8), copied by the runner into run.json `inputs.gpu_count` (asserted; source `reference/<release>.yaml#/profiles/<profile>/gpu/count`). The runner raises `config` before `info` when a profile that names a GPU has a GPU count missing or below 1, for every profile class; a CPU-only test profile (`gpu: null`, `reference/ci.yaml`) records no `gpu_count`, and its runs have no D-GSPT-S. A run stored before run.json carried `inputs.gpu_count` names no such input: G4 recomputes its D-COST-1K-S with the profile's GPU count from the reference file, as before the amendment of 2026-11-09. `active_parameters_per_token` is `model.parameters.active_per_token` and `weight_bits` is `precision.weight_bits.bits` (typed for a `stated` basis, computed by the loader for `file_size`, typed for `computed` and recomputed from the files by `fetch-model` and CI, RFC-0003 WB-5), both from the workload record ([RFC-0003](0003-workloads.md#weight-bits)) as the runner copies them into run.json `inputs` at run time (`inputs.active_parameters_per_token`, `inputs.weight_bits`, asserted quantities; RFC-0003 WB-4). A run stored before run.json carried `inputs` names the workload record itself. `S` ranges over the rate scopes {`prove.steady`, `prove.session`, `whole_wall`}; `T(S)` is `tokens_covered_steady` for `prove.steady` and `tokens_covered_total` otherwise; `sec(S)` is the matching seconds metric.

| Formula id | Metric id | Level | Formula | Unit | Scope | Null when |
|---|---|---|---|---|---|---|
| D-RATE-S | `rate_<S>` | repetition | T(S) / sec(S) | token/s | S | sec(S) null or 0; T(S) = 0 |
| D-SPT-S | `seconds_per_token_<S>` | repetition | sec(S) / T(S) | s/token | S | as D-RATE-S |
| D-COST-1K-S | `cost_per_1k_tokens_<S>` | repetition | D-SPT-S × 1000 × gpus × price / 3600, `gpus` read from `run.json#/inputs/gpu_count` (the same value as D-GSPT-S × 1000 × price / 3600) | USD/1k_token | S | D-SPT-S null; price null; `gpu_count` missing (`missing_input`) |
| D-GSPT-S | `gpu_seconds_per_token_<S>` | repetition | D-SPT-S × gpus | gpu_s/token | S | D-SPT-S null (its reason); `gpu_count` missing (`missing_input`) or 0 (`not_applicable`) |
| D-COMMIT-AMORT-H1 | `commit_seconds_per_token_h1` | repetition | `commit_seconds` / (tokens_covered_total / requests_count × 1) | s/token | `commit` | commit failed |
| D-COMMIT-AMORT-H1000 | `commit_seconds_per_token_h1000` | repetition | `commit_seconds` / (tokens_covered_total / requests_count × 1000) | s/token | `commit` | as above |
| D-APT-S | `active_param_tokens_per_second_<S>` | repetition | D-RATE-S × `active_parameters_per_token` | param_token/s | S | D-RATE-S null; parameter count missing (`missing_input`) |
| D-SPAB-S | `seconds_per_active_weight_bit_token_<S>` | repetition | D-SPT-S / (`active_parameters_per_token` × `weight_bits`) | s/bit_token | S | D-SPT-S null (its reason); weight bits or parameter count missing (`missing_input`); parameter count or weight bits 0 (`not_applicable`); always null with `not_applicable` for `kind: reference` (INV-DERIVE-7) |
| D-BPT | `proof_bytes_per_token` | repetition | `proof_bytes_total` / tokens_covered_total | B/token | null | tokens 0 |
| D-VSPT | `verify_seconds_per_token` | repetition | `verify_seconds_total` / tokens_covered_total | s/token | `verify` | tokens 0 |
| D-BPAB | `proof_bytes_per_active_weight_bit_token` | repetition | D-BPT / (`active_parameters_per_token` × `weight_bits`): proof bytes per token covered per bit of active weights, the D-SPAB-S basis (amendment of 2026-11-09) | B/bit_token | null | D-BPT null (its reason); as D-SPAB-S for the parameter count and weight bits; always null with `not_applicable` for `kind: reference` |
| D-VSPAB | `verify_seconds_per_active_weight_bit_token` | repetition | D-VSPT / (`active_parameters_per_token` × `weight_bits`): check seconds per token covered per bit of active weights (amendment of 2026-11-09) | s/bit_token | `verify` | as D-BPAB, with D-VSPT |
| D-VSPT-1T | `verify_single_thread_seconds_per_token` | repetition | single-thread verify seconds of the first proof / tokens covered by the first proof (single-thread verify runs on the first proof only, RFC-0010) | s/token | `verify.single_thread` | as D-VSPT |
| D-TPP | `tokens_covered_per_proof` | repetition | `tokens_covered_total` / `proofs_count` | token | null | tokens 0 or `proofs_count` 0 (`not_applicable`); always null with `not_applicable` for `kind: reference` (INV-DERIVE-6) |
| D-VERIFY-HOST | `verify_host_ratio` | configuration | mean `verify` seconds on a separate verifier host / mean `verify` seconds on the emulated verifier profile, same proofs | ratio | `verify` | null with `missing_input` unless both host kinds ran the same proofs (RFC-0006 verifier emulation check) |
| D-STAT | any of the above, configuration level | configuration | statistics over successful repetitions (§Statistics) | as input | as input | n = 0 |
| D-OVERHEAD-S | `overhead_vs_production_<S>` | release | mean(system `gpu_seconds_per_token_<S>`) / mean(production-serving `gpu_seconds_per_token_<S>`, matched load) | ratio | S (`prove.steady`) | INV-DERIVE-2 |
| D-OVERHEAD-WARM | `overhead_vs_production_warm` | release | mean(system `gpu_seconds_per_token_prove.session`) / mean(production-serving `gpu_seconds_per_token_prove.steady`, matched load, lengthened per RFC-0015 SRV-1); the prover's start-up included, serving warm (INV-DERIVE-11, amendment of 2026-11-09) | ratio | `prove.session` (the prover's; serving's is `prove.steady`) | INV-DERIVE-2 |
| D-OVERHEAD-HIGH-S | `overhead_vs_production_high_<S>` | release | mean(system `gpu_seconds_per_token_<S>`) / mean(production-serving `gpu_seconds_per_token_<S>`, high load) | ratio | S | INV-DERIVE-2 |
| D-AGREE | `agreement_rate` | release | agreement positions / (agreement + disagreement positions), RFC-0015 RC-5 | ratio | null | no compared positions; recompute row `not_measurable_on_profile` |
| D-PROVIDER-SPREAD | `provider_spread_<S>` | release | max over providers of configuration mean `rate_<S>` / min over providers of the same (RFC-0006 R4) | ratio | S | fewer than two providers (`not_applicable`) |
| P-CAMPAIGN | `campaign_gpu_seconds` | release plan | projection from `external` inputs (docs/spec/08-performance-budget.md); grade `projected`, never published as a result | s | `whole_wall` | any input missing (`missing_input`) |

Rules:

- INV-DERIVE-1: a configuration-level statistic is computed from per-repetition derived values (mean of rates), never from pooled sums (rate of means). This keeps a long repetition from dominating.
- INV-DERIVE-2 (amendment of 2026-11-09): D-OVERHEAD-S, D-OVERHEAD-HIGH-S and D-OVERHEAD-WARM (INV-DERIVE-11) join a system configuration with the production-serving configuration (RFC-0015 SRV-6) that meets all of the following:
  (a) its system is the one serve-role system the workload's `systems` names (RFC-0015 SRV-7);
  (b) it has the same workload id and version;
  (c) its profile is a serving profile whose `pairs_with` lists the system row's profile (RFC-0006 R6), so the GPU model and the runtime kind are the same;
  (d) its `load_point` is `matched` (D-OVERHEAD-S, D-OVERHEAD-WARM) or `high` (D-OVERHEAD-HIGH-S);
  (e) its runs record the serving model digest (`serving_model.digest`, the RFC-0014 model digest over the pinned files) of the serving record that names the workload at the release commit, and the engine image digest that the release's `ref-serve` `system.yaml` pins. The record id and version are for display only: a byte-identical replacement mirror changes neither key, and a re-pinned engine (RFC-0015 Q1) never pools with the old one;
  (f) only those of its successful runs whose `prompts_from` is a run of this system configuration enter the mean (RFC-0015 SRV-8), and of those only the runs without the warning "steady scope under 60 s" (RFC-0015 SRV-1) and, at a batch size above 1, with `workload.steady_rule` (INV-SCOPE-5). A sizing capture (manifest `workload.sizing_capture: true`, RFC-0015 SRV-1) never enters: it only sizes the session. The system's runs at b > 1 without `steady_rule` do not enter either.
  Placement (RFC-0015 SRV-6). The joined matched configuration is the smallest GPU count with a run that enters the mean. The high load joins only at the joined matched configuration's profile. Null rules, in this order:
  - no serve-role system named → the key is absent (a CI workload);
  - the system's mean null → null with its reason (SASH: `not_externally_observable`);
  - configurations exist only on profiles that fail (c), or with another model or engine digest (e) → null `not_applicable`; every system run at b > 1 lacks `steady_rule` → null `not_applicable`; a high-load configuration with a run that would enter the mean exists only at another profile than the joined matched one → D-OVERHEAD-HIGH-S null `not_applicable`;
  - no configuration meets (a) to (e), or none has a run that enters the mean (f) → null `missing_input`;
  - the serving mean null → null with its reason.
- INV-DERIVE-3: `active_parameters_per_token` comes from the workload record (RFC-0003), copied into run.json `inputs` at run time (RFC-0003 WB-4), as an `asserted` quantity whose source is the model's own documentation: all parameters for a dense model, the parameters used per token for a mixture of experts. D-APT-S counts an 8-bit and a 4-bit weight alike, so it is not a figure that compares provers across models (decided 2026-11-08): it stays in the catalogue, so that every stored run recomputes under G4 and `run/1` keeps its keys, and no page displays it. The two figures that compare provers across models are D-SPAB-S (INV-DERIVE-7) and D-OVERHEAD-S.
- INV-DERIVE-4: every derived quantity's `source` is `{kind: derivation, ref: derive:<formula id>@<harness version>, inputs: [<JSON pointers>]}` (RFC-0012) and its tier is the lowest tier among its inputs (in `run.json` always `reported`).
- INV-DERIVE-5: arithmetic is IEEE 754 binary64 in a fixed order: the formula is evaluated left to right as written in the table, sums use `math.fsum`, statistics use `statistics.mean` and `statistics.stdev`. Values are stored unrounded. `iproofs derive --check` recomputes and requires `==` equality with the stored value; any difference fails CI (RFC-0013).
- INV-DERIVE-6: D-TPP is the number of positions one proof binds (INV-TOK-1), averaged over the repetition's proofs. It is a count, not a time or a rate, so it has no timing scope (INV-SCOPE-1 does not apply) and MUST NOT be displayed as a throughput. Its grade is `derived` and its tier follows INV-DERIVE-4 (`reported` in `run.json`). For the coverage kinds `window` and `prompt_plus_output` every proof of a repetition covers the same count c, so the value is exactly c (k × c / k is exact in binary64 when the total k × c is below 2^53); for `declared_per_proof` it is the mean of the adapter's per-proof counts. A reference system (`kind: reference`, RFC-0015) proves nothing: its releases are outputs, not proofs (REF-2), so its `tokens_covered_per_proof` is null with `null_reason: not_applicable` whatever its `tokens_covered_total` (REF-3) and `proofs_count`. Its configuration-level value is D-STAT over every successful repetition (§Statistics), with n, n_failed, mean, stdev, min and max like every repetition-level metric; for a constant count at n >= 2, stdev is 0 and min equals max. The public site prints it as "One proof covers" (RFC-0009).

- INV-DERIVE-7: D-SPAB-S is prover seconds per bit of active weights per token covered: D-SPT-S over the bits of the weights one token uses, `active_parameters_per_token` × `weight_bits`. Tokens are tokens covered (INV-TOK-1), so S and T(S) follow D-SPT-S. Its grade is `derived` even though its two workload inputs are `asserted` (INV-GRADE-3; both are listed in `source.inputs`), and its tier follows INV-DERIVE-4. Its inputs, in order: `seconds_per_token_<S>` of the same repetition, then run.json `inputs/active_parameters_per_token`, then `inputs/weight_bits`: the workload record's values as copied at run time (RFC-0003 WB-4), so G4 recomputes a stored run from the run itself and a later correction of the workload file (a new workload version) leaves it valid. A workload record without weight bits (RFC-0003 WB-3) makes `inputs.weight_bits` a null asserted quantity with `missing_input`, and D-SPAB-S null with `missing_input`, never 0; a parameter count or weight width of 0 makes it null with `not_applicable` (TC-NULL-DIV). A reference system (`kind: reference`, RFC-0015) proves nothing (REF-2), so its value is null with `null_reason: not_applicable` whatever its seconds. Display rule: like D-APT-S before it, it is shown only together with the claim cards, never alone, with the profile name beside it, and every page that shows it prints this limit beside it: "Attention cost grows with prompt length and is not in this normaliser, so two workloads of one model with different prompt lengths differ for that reason too ({prompt lengths}). Weight bits are as the workload records them, with their basis and source.", where {prompt lengths} names the prompt lengths of the published release's workloads of one model, computed from their records, never typed (amendment of 2026-11-09: the earlier text named a 4,096-token SASH workload no release holds). When the workload's weight bits carry a `note`, the page prints the note too. Sorting: the figure is a quotient of a measured time and two asserted inputs, so it may sit in a sortable column only when both asserted inputs are what their sources state for every weight they count. A width recorded with `covers: part` (RFC-0003 WB-1: a statement about part of the weights, such as SASH's weight-matmul width) applies the statement past its scope when multiplied by every active parameter, so that row's figure is shown with its note but left out of any sort on the column, listed after the sorted rows. A width with `covers: all` (RFC-0003 WB-2 or WB-5) sorts. With RFC-0003 Q5 resolved (2026-11-08), the Maverick workloads' widths are computed from their files (WB-5, `covers: all`), so their rows sort; the SASH workloads' and `l31-8b-c1024`'s stay `covers: part` and unsorted, because SASH's statement covers the weight matmuls only, counts the int8 code without its scale where WB-5 counts block scales, and the proved width is not in their BF16 files (RFC-0003 Q5). The column therefore sorts rows of one model, never a SASH row against a Maverick row, which INV-WL-5 would forbid presenting as a head-to-head result anyway.

- INV-DERIVE-8 (GPU accounting, amendment of 2026-11-09): GPU-seconds of a scope are its wall seconds times the GPUs the configuration holds: the profile's `gpu.count`. Every GPU of a tensor-parallel server counts. A GPU that the provider bills but no step binds does not (RFC-0006 R1): a FlashProve job on Hugging Face Jobs' `h200x2` counts 1. That exclusion is recorded, not assumed: PC-GPU-IDLE (RFC-0006) reads every visible unbound GPU when the machine record is taken before `info` and after the last step, and once a second on its own thread through every step call, and the manifest records a compute process, memory more than 1,024 MiB above its reading before `info`, or utilisation above 5 %. A use shorter than one second can fall between two readings. The runner refuses a job whose bound GPU count differs from `gpu.count` (`config`, before `info`). D-GSPT-S is the only per-token figure that compares rows on profiles with different GPU counts. D-SPT-S and D-RATE-S stay per configuration and are never divided across profiles.
- INV-DERIVE-9 (statistics and display of the overhead, amendment of 2026-11-09): the overhead quantity carries `pairs: {n_system, n_serving, min, max}`. `min` is the smallest system value over the largest serving value, and `max` the largest over the smallest, so the range covers every pair of repetitions (RFC-0012 adds the optional property).
  - The headline is D-OVERHEAD-S at `prove.steady` and matched load. Start-up is excluded on both sides, as in FlashProve's own figure ([guide/performance.md L27](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/performance.md?plain=1#L27)). A system with no steady scope (SASH) shows D-OVERHEAD-WARM instead (INV-DERIVE-11).
  - D-OVERHEAD-HIGH-S at the headline's scope is printed beside it as context; a warm headline has none beside it (INV-DERIVE-11, Q6). Overheads are computed at `prove.steady` only, apart from D-OVERHEAD-WARM.
  - Every page that shows the figure prints its conditions, each generated from the records (`overhead_conditions` in the release index): the scope; both batch sizes, and the batches per session of each side; the prompt count of each side (`prompt_count_run`), and at high load the token-set difference ("at high load: the prover's {n_p} prompts plus {n_s − n_p} further windows of the same seeded generator"); the engine, its version, its interface (`vllm serve` or `LLM` class, RFC-0015 Q8) and its settings per load point, from the joined configuration's `system.yaml` entry with their values ("engine defaults except --tensor-parallel-size 4, --max-model-len 1025, --max-num-seqs 24"), and the batched-token limit each engine logged (`engine.observed`); at high load also its scope, its batches per session and its GPU count; greedy decoding, and warm (start-up outside the steady scope) or, for a warm headline, warm serving with the prover's start-up inside its session (INV-DERIVE-11); the runtime kind (hosted or docker); the serving release (publisher and precision) and the proved precision; the GPU count and model of each side; n for each side, and the pair range; and the C5 limit: "GPU-seconds only: CPU and host memory are not counted; the prover's GPU comes with its host's CPUs and memory (RFC-0006 C5)". Each fact is printed once per plate (amendment of 2026-11-09, research phase): the scope, warm or cold included, is the plate's scope row; n for each side and the pair range are its pairs row, with each side's runs; the serving release and the proved precision are the precision note's; the weight width is the per-Gbit basis's. The conditions line holds the rest, and says "cold" only for a session whose start-up is inside the scope.
  - It also prints the precision note, built from the records and never typed: "Proving the {workload precision.proved} model costs {X} times serving {publisher}'s {serving precision.name} release, in GPU-seconds per token." (amendment of 2026-11-09: the weight width, range, scope and batch size it printed are the plate's other rows).
- INV-DERIVE-10 (session overhead, amendment of 2026-11-09): every proving system gets an overhead ratio. A system row's headline is D-OVERHEAD-S at `prove.steady`, or D-OVERHEAD-WARM for a system with no steady scope (INV-DERIVE-11).
- INV-DERIVE-11 (warm overhead, amendment of 2026-11-09: overhead "in the conditions the models are actually executed when served by model providers"): the headline of a system with no steady scope compares its proving session with production serving that is already running.
  - Why. A provider's server is warm: its engine started long before the request arrives, and its start-up is spread over every request it serves. A system that releases no proof before the whole request is proved (SASH at its pin: one proof per request, `incremental_proofs: false`, Q2) has no steady scope, so it pays its start-up inside every request it proves: it proves one request at a time, and its proving session is the cost of that request. A session-over-session ratio would divide that by a serving session of the same workload, which for a one-request workload (the SASH workloads: one request at batch size 1) is the engine's start-up plus one request: the development capture of `sash-l31-8b-c1024` at TP1 recorded `prove.session` 58.464736204 s for 1,088 tokens (measured, tier reported, n = 1, run `2026-11-09-ref-serve-sash-l31-8b-c1024-serving-h200x1-hosted-1`, profile `serving-h200x1-hosted`, vLLM 0.32.0), mostly engine start-up. That ratio measures vLLM's start-up, not what serving the request costs a provider, so it is not the headline.
  - Definition. D-OVERHEAD-WARM (`overhead_vs_production_warm`, formula id `D-OVERHEAD-WARM`) is mean(system `gpu_seconds_per_token_prove.session`) / mean(production-serving `gpu_seconds_per_token_prove.steady`, matched load), with `pairs` as INV-DERIVE-9. The serving side is the matched configuration lengthened per RFC-0015 SRV-1 (`batches_per_session_run`, sized from a sizing capture for a one-batch workload), so its steady scope lasts at least 60 s. The quantity's `scope` is the prover's, `prove.session`; the formula names serving's. It is computed only for a system row with no steady scope (the headline rule below), so a row with a steady scope (FlashProve) has no such key and nothing about it changes.
  - Join. INV-DERIVE-2 unchanged, with the matched configuration it joins for D-OVERHEAD-S: the same placement, keys, prompts and filters of (f), so the serving runs are those D-OVERHEAD-S would divide by. Null rules in INV-DERIVE-2's order: the system's session mean null → its reason (a failed step); the join's reasons; then the serving steady mean null → its reason (a serving run of one batch has none: `fewer_than_two_proofs`). A serving run under 60 s steady or a sizing capture enters no mean, so with no other run the figure is null `missing_input`.
  - Headline. A system row's overhead is D-OVERHEAD-S at `prove.steady` (INV-DERIVE-9), unless the system has no steady scope (every successful repetition's `gpu_seconds_per_token_prove.steady` is null with `not_externally_observable` or `fewer_than_two_proofs`, INV-SCOPE-2, INV-SCOPE-3, or none records it). Then it is D-OVERHEAD-WARM, with its value or its own null reason. A steady figure null for a join reason stays the headline, with that reason. Release code records the choice in the index entry, `overhead_headline: {metric, formula, scope, serving_scope, start_up}` (RFC-0012): for D-OVERHEAD-S `{overhead_vs_production_prove.steady, D-OVERHEAD-S, prove.steady, prove.steady, excluded}`, for D-OVERHEAD-WARM `{overhead_vs_production_warm, D-OVERHEAD-WARM, prove.session, prove.steady, prover_only}`; it writes `overhead_conditions` for the headline when it has a value, with `warm` true (serving's start-up outside its scope). The site reads both and chooses nothing.
  - Display (RFC-0009 S1, S5). The warm figure names both scopes wherever it appears: the overview cell prints the scopes' short names, "session vs warm", under the value, as a steady figure's cell prints "steady", with the full phrase "proving session (start-up included; it proves one request at a time) vs warm serving (steady)" in its title and read aloud (amendment of 2026-11-09, research phase); the plate prints the same line as its scope (with a value, and without one), the conditions line and the precision note do not repeat the scopes (each fact once per plate, INV-DERIVE-9; amendment of 2026-11-09), and the plate says why the steady figure is null. No high-load figure is printed beside it (Q6). The conditions print each side's batches per session.
  - Reading it. The figure is larger than a steady overhead of the same prover would be, because the prover's start-up is inside it and serving's is not: that is the cost of proving one request with a system that starts per request, against a server that is already running. It is not a statement about the prover's speed once started.

### Worked example (test fixture, not a result)

The following inputs are invented round numbers used only as the hand-computed fixture `harness/tests/fixtures/derive/worked-example/` (AGENTS.md: every derived metric ships a test against a hand-computed case). They describe no system.

Inputs: one repetition, 1 GPU, `price` 3.60 USD/gpu_hour (fixture value), `active_parameters_per_token` 8.0e9, `weight_bits` 8 (fixture values; the fixture run.json holds the last two in its `inputs`). Batch 1, 5 batches, so `requests_count` 5 and k = 5 proofs (`proofs_count` 5) of 1,000 tokens each. Clock (seconds from `commit` start): `commit` runs 0 to 50, `prove` starts at 62.5, proofs release at 85, 95, 105, 115, 125. Each proof is 2,000,000 B; each 8-CPU verify takes 5 s. Production-serving fixtures (amendment of 2026-11-09): a matched-load row on 4 GPUs at 40,000 token/s steady and a high-load row on 4 GPUs at 80,000 token/s steady.

| Formula | Computation | Expected |
|---|---|---|
| `prove_steady_seconds` | 125 − 85 | 40 s |
| `prove_session_seconds` | 125 − 62.5 | 62.5 s |
| `whole_wall_seconds` | 125 − 0 | 125 s |
| D-RATE-prove.steady | 4,000 / 40 | 100 token/s |
| D-RATE-prove.session | 5,000 / 62.5 | 80 token/s |
| D-RATE-whole_wall | 5,000 / 125 | 40 token/s |
| D-SPT-prove.steady | 40 / 4,000 | 0.01 s/token |
| D-COST-1K-prove.steady | 0.01 × 1,000 × 1 × 3.60 / 3,600 | 0.01 USD/1k_token |
| D-COMMIT-AMORT-H1 | 50 / (5,000 / 5 × 1) | 0.05 s/token |
| D-COMMIT-AMORT-H1000 | 50 / (5,000 / 5 × 1,000) | 0.00005 s/token |
| D-APT-prove.steady | 100 × 8.0e9 | 8.0e11 param_token/s |
| D-SPAB-prove.steady | 0.01 / (8.0e9 × 8) | 1.5625e-13 s/bit_token |
| D-BPT | 10,000,000 / 5,000 | 2,000 B/token |
| D-VSPT | 25 / 5,000 | 0.005 s/token |
| D-BPAB | 2,000 / (8.0e9 × 8) | 3.125e-8 B/bit_token |
| D-VSPAB | 0.005 / (8.0e9 × 8) | 7.8125e-14 s/bit_token |
| D-TPP | 5,000 / 5 | 1,000 token |
| D-GSPT-prove.steady (system, 1 GPU) | 0.01 × 1 | 0.01 gpu_s/token |
| D-GSPT-prove.steady (serving fixture, 4 GPUs, 40,000 token/s) | 0.000025 × 4 | 0.0001 gpu_s/token |
| D-OVERHEAD-prove.steady | 0.01 / 0.0001 | 100 ratio |
| D-OVERHEAD-HIGH-prove.steady (serving fixture, 4 GPUs, 80,000 token/s) | 0.01 / 0.00005 | 200 ratio |

Statistics fixture: four repetitions with `rate_prove.steady` 100, 110, 90 token/s and one failed repetition. Expected: n 3, n_failed 1, mean 100, stdev 10, min 90, max 110.

Constant-count statistics fixture: three repetitions with `tokens_covered_per_proof` 1,000, 1,000, 1,000 token and none failed. Expected: n 3, n_failed 0, mean 1,000, stdev 0, min 1,000, max 1,000.

Hand-computed tests compare with `math.isclose(rel_tol=1e-12)`, because a decimal written in this table (for example 0.01) has no exact binary64 form; `--check` on stored runs uses exact equality per INV-DERIVE-5.

### Statistics

- At least three repetitions per configuration (a configuration is system, workload id and version, profile, image digest). A configuration with fewer than three successful repetitions is published with its n and the label "below minimum repetitions"; it is never hidden.
- Reported per metric: n (successful repetitions), n_failed, mean, sample standard deviation (n − 1 denominator; null when n < 2), min, max, and the median ([RFC-0017](0017-requests-tasks-and-tested-states.md) ST-1; absent from statistics stored before 2026-11-10).
- No confidence intervals at n = 3: an interval from three samples under an unchecked normality assumption would overstate precision.
- Failed repetitions are counted and shown with their failure record (RFC-0010) and excluded from mean, stdev, min and max.
- The first proof of a session is excluded from `prove.steady` and included in `prove.session` (§Timing scopes).

### Failure modes

| Failure | Response |
|---|---|
| A time-based quantity without `scope` | schema validation fails (RFC-0012); CI blocks the pull request |
| A `derived` quantity whose stored value differs from recomputation | `iproofs derive --check` exits 1; CI blocks |
| Adapter `tokens_covered` differs from harness count | job fails at step `prove` with kind `adapter` |
| Honest proof rejected | repetition failed at step `verify` (INV-TOK-2) |
| Scope boundary order violated (INV-SCOPE-4) | `internal` error, job failed, bug filed |
| Division by zero or null input | derived value null with the table's null reason; never 0, never omitted |
| Adapter phase timing used as a derivation input | `iproofs derive` raises `internal`; covered by test TC-GRADE-2 |

## Alternatives Considered

- **One headline rate per system.** Considered because readers want one number. Rejected: the motivating example shows two different rates for one SASH run under two scopes; a single number would silently pick a scope.
- **Use upstream scopes directly.** Considered because SASH and FlashProve already label their numbers. Rejected as the authoritative vocabulary because the two upstream vocabularies do not share boundaries; they are kept as `upstream_scope` and mapped.
- **FLOPs per second as the cross-model normaliser.** Considered as the standard ML throughput measure. Rejected for v0.1: proof systems do work that is not model FLOPs, the count depends on kernel and quantisation details each team would have to declare, and the active-parameter-token metric needs only a parameter count from the model card.
- **Active parameters alone as the cross-model normaliser (D-APT-S).** Considered because it needs only the model card. Rejected as a figure that compares provers across models (2026-11-08): a prover of a 4-bit model and a prover of an 8-bit model of the same size would be credited with the same work, although the second binds twice the bits of weights. D-SPAB-S carries the weight bits; D-APT-S stays computed and undisplayed (INV-DERIVE-3).
- **A normalised proof size (bytes per bit of active weights).** Rejected by the owner on 2026-11-08: succinct proofs barely grow with the model, so dividing by model size would favour larger models by construction. Proof bytes stay absolute, per workload.
- **Rate of means (pooled tokens over pooled seconds) for configuration statistics.** Considered because it weights by work. Rejected: repetitions have equal shapes, so pooling adds nothing but lets one slow repetition dominate the denominator; mean of per-repetition rates keeps n and stdev interpretable.
- **Adapter-reported per-batch timestamps for `prove.steady`.** Considered because it would give SASH and end-of-run writers a steady figure. Rejected for v0.1: it makes the headline depend on code inside the container, against PRD F9 (measure externally). Kept as a possible later secondary figure (RISK above).
- **Include `setup` in `whole_wall`.** Considered for completeness. Rejected: setup is a one-off build or load amortised over all requests forever; including it would make `whole_wall` depend on whether the image was warm.

## Drawbacks

- `prove.steady` is null for SASH in v0.1, so the two v0.1 systems never both have a measured steady figure.
- Amortised commit cost at two fixed horizons (1 and 1,000 requests) does not fit every deployment; readers with other horizons must recompute.
- D-SPAB-S leaves attention out: attention work grows with prompt length while the normaliser does not, so for one prover and one model a long-prompt workload shows a larger figure than a short-prompt one (INV-DERIVE-7 prints this). Where the weight bits are a nominal width (RFC-0003 WB-1, `covers: part`), the figure is as precise as that statement and is not sortable (INV-DERIVE-7); after RFC-0003 Q5 that is the SASH workloads and `l31-8b-c1024`, so the column sorts the Maverick rows only. A computed width (WB-5) counts storage bits with block scales, so it is comparable across GGUF quant mixes, not with a width stated as an integer code alone.
- Exact float equality in `--check` couples stored values to the evaluation order; changing a formula's operand order is a methodology change and needs a version bump of the derivation (RFC-0012 schema major).


## Migration / Rollout

No results existed when this RFC revised the version of 2026-11-03. The revision adds `setup` and `verify.single_thread` scopes, fixes `whole_wall` to start at `commit` (setup excluded), fixes `prove.steady` to the first-to-last release interval, adds INV-TOK-2, and resolves the amortisation horizon question (both 1 and 1,000 requests are reported). The metric ids above are keys of `run/1` (RFC-0012). Adding a metric is additive; renaming one or changing a formula bumps `run` to a new major and relabels nothing in place: past runs keep the formula version they were produced under.

The amendment of 2026-11-07 adds D-TPP (`tokens_covered_per_proof`), the figure the public site prints as "One proof covers", whose current wording RFC-0009 S2 lists as naming no RFC-0004 grade. It changes no existing metric, formula or null rule. The new key is additive to `run/1`: `iproofs.derive` (`COMPUTE`, `FORMULAS`, `derive_repetition`), the metric-id pattern of `schema/quantity/1.schema.json` and the worked-example fixture gain it with the code (#320). In the fixture, `inputs.json` and `run.json` gain the recorded input `proofs_count` 5 (unit count, scope null, grade `measured`, source `run.json#/proofs`, as the runner records it), `run.json` gains the derived `tokens_covered_per_proof`, and `expected.json` and `README.md` gain the D-TPP row. Stored v0.1 runs exist (`results/v0.1`); they were made before that code, carry no `tokens_covered_per_proof` key and are not changed (APP-1, RFC-0009). They keep `tokens_covered_total` and `proofs_count`, so the value stays recomputable from recorded numbers; Q3 sets how a release gets it.

The amendment of 2026-11-08 adds D-SPAB-S (`seconds_per_active_weight_bit_token_<S>`, unit `s/bit_token`) on the owner decision of that date: the two figures that compare provers across models are prover time per bit of active weights and the overhead against plain serving (D-OVERHEAD-S). It decides D-APT-S (kept, computed, not displayed; INV-DERIVE-3), adds INV-DERIVE-7 and Q4. It changes no existing metric, formula or null rule. The new key is additive to `run/1`: `iproofs.derive` (`COMPUTE`, `FORMULAS`, `derive_repetition`, `PROVER_ONLY`), the runner's input pointers, the unit enum, INV-QTY-3 list and metric-id pattern of `schema/quantity/1.schema.json` (RFC-0012) and the worked-example fixture gain it with the code. In the fixture, `inputs.json` gains `weight_bits` 8, `run.json` gains its `inputs` (8e9 parameters, 8 weight bits, as the runner copies them) and the three derived `seconds_per_active_weight_bit_token_<S>` values, D-APT-S's parameter input moves to `run.json#/inputs/active_parameters_per_token`, and `expected.json` and `README.md` gain the D-SPAB row; `workload.yaml` stays for the G4 gate fixture, a run recorded before `inputs`. The workload field, run.json `inputs` and the unit `bit/weight` are RFC-0003's and RFC-0012's amendments of the same date. Stored v0.1 runs (`results/v0.1`) carry no such key and are not changed (APP-1); they keep `seconds_per_token_<S>`, so the value stays recomputable, and the release freeze evaluates it as Q3 sets, which the code now applies to D-TPP and D-SPAB-S.

The second amendment of 2026-11-08 follows RFC-0003's resolution of its Q5: INV-DERIVE-7 sorts rows whose weight bits cover all the active weights (`file_size` or the new `computed` basis) and keeps `covers: part` rows unsorted, and the inputs paragraph names the `computed` basis. No formula, metric id, null rule or stored value changes.

The amendment of 2026-11-09 redefines the overhead: the prover's GPU-seconds per token on its own profile over production serving's GPU-seconds per token on its own (RFC-0015 SRV-6), steady scope, at matched load (D-OVERHEAD-S) and at high load as context (D-OVERHEAD-HIGH-S). It adds D-GSPT-S, INV-DERIVE-8 and INV-DERIVE-9, and replaces INV-DERIVE-2.
- D-GSPT-S joins `COMPUTE`, `FORMULAS` and `derive_repetition`. It joins FREEZE_FORMULAS (Q3): a stored run without the key gets it at freeze, from its recorded `seconds_per_token_<S>` and its profile's `gpu.count` in the reference file at the release commit.
- D-COST-1K-S of a new run reads `gpus` from `run.json#/inputs/gpu_count`, the input D-GSPT-S reads, as its third input; its value is unchanged.
- The unit `gpu_s/token` joins the RFC-0012 unit vocabulary. The quantity schema's metric-id pattern gains `gpu_seconds_per_token_<S>`, `overhead_vs_production_<S>` and `overhead_vs_production_high_<S>`, and loses `overhead_vs_serving_<S>` (the old ratio of rates on one profile). No frozen release holds that key: there is no `releases/` directory at `14e9d34`.
- The worked example gains the D-GSPT and D-OVERHEAD-HIGH rows, and its D-OVERHEAD row is restated in GPU-seconds; the expected value stays 100.
- The glossary's "Overhead" entry is rewritten.

The amendment of 2026-11-09 adds INV-DERIVE-10 (every proving system gets an overhead ratio); the release index gains the optional `overhead_headline` (RFC-0012). D-OVERHEAD-SESSION, which it added, and the `whole_wall` overheads are removed: only the release index held them.

The amendment of 2026-11-09 adds INV-DERIVE-11 (the overhead in the conditions in which providers serve the model, whose servers are warm). D-OVERHEAD-WARM (`overhead_vs_production_warm`) joins `iproofs.derive.FORMULAS` and `overhead` (`warm=True`), and release code computes it for a system row with no steady scope and makes it that row's headline. RFC-0012 changes, with no stored index or run to migrate (no frozen release exists): the quantity metric-id pattern gains `overhead_vs_production_warm`; `release-index/1` `overhead_headline` gains the required `serving_scope` (`prove.steady`), its `formula` and `metric` enums replace D-OVERHEAD-SESSION and `overhead_vs_production_prove.session` with D-OVERHEAD-WARM and `overhead_vs_production_warm`, and `start_up` replaces `included` with `prover_only`; `overhead_conditions.warm` means serving's start-up outside its scope; `manifest/1` gains `workload.sizing_capture` (RFC-0015 SRV-1), and INV-DERIVE-2 (f) keeps such a run out of every mean. The site prints the warm figure with both scopes (`iproofs.site.view`, `web/draw`). For a system with a steady scope nothing changes: its headline, its figures and its index entry are as before, but for `serving_scope`.

The amendment of 2026-11-09 adds INV-SCOPE-5 (steady scope by batch membership). At batch size 1 nothing changes. At batch size b > 1 the steady start moves from r_1 to the first batch's last release and the steady tokens drop the first batch, so a run released batch by batch no longer counts the other b − 1 requests of the first batch, whose work finished before r_1. `iproofs.derive.scope_seconds` and `tokens_metrics` take the batch size, each release's `request_index` and the release times (TC-STEADY-BATCH): a later-batch request released before the start leaves the steady tokens, so a system that overlaps batches does not count work done before the window. Every manifest records `workload.steady_rule`; a release labels a configuration with an earlier run at b > 1 (`steady_boundary`), and such a run joins no overhead. Stored runs keep their values (APP-1).

The amendment of 2026-11-09 adds D-BPAB (`proof_bytes_per_active_weight_bit_token`, new unit `B/bit_token`) and D-VSPAB (`verify_seconds_per_active_weight_bit_token`, `s/bit_token` at `verify`) on the owner decision of that date: proof size and check time on the D-SPAB-S basis, so the overview's three cost columns share one normalisation (per token covered, per bit of active weights). D-BPT and D-VSPT divide by tokens covered, so D-BPAB equals mean proof bytes / tokens covered per proof / (active parameters × weight bits), and D-VSPAB likewise with check seconds. Both join `COMPUTE`, `FORMULAS`, `derive_repetition`, `PROVER_ONLY` and FREEZE_FORMULAS (Q3): stored v0.1 runs hold `proof_bytes_per_token`, `verify_seconds_per_token` and run.json `inputs`, so the freeze evaluates both into `freeze_derived` and no run.json changes (APP-1). The unit enum and the metric-id pattern of `schema/quantity/1.schema.json` gain them. The INV-DERIVE-7 limit (attention left out of the normaliser) applies to both.

The amendment of 2026-11-10 is [RFC-0017](0017-requests-tasks-and-tested-states.md): it adds the per-request figures D-TPR, D-GSPR-S, D-COST-REQ-S, D-BPR and D-VSPR (new units `token/request`, `gpu_s/request`, `USD/request`, `B/request`, `s/request`), puts them in `FREEZE_FORMULAS` (Q3), and adds `stats.median` to every statistic (its ST-1). It changes no existing metric, formula, null rule or stored value: a statistic's `value` stays its mean.

## Testing Strategy

Unit tests in `harness/tests/unit/`, in `test_derive.py` unless an entry names another file:

- TC-OVERHEAD-WARM (`test_cross_rows.py`, `test_site_view.py`, INV-DERIVE-11, hand-computed fixture values): the prover's session of 0.5 gpu_s/token (544 s for 1,088 tokens on 1 GPU) over warm serving's steady 0.0005 gpu_s/token (0.544 s per 1,088-token request on 1 GPU) is 1,000, formula `D-OVERHEAD-WARM`, scope `prove.session`, pairs 1,000 to 1,000 over 1 × 1. The SASH-like row: D-OVERHEAD-S null `not_externally_observable`, D-OVERHEAD-WARM 1,000 as the headline (`prove.session`, serving `prove.steady`, start-up `prover_only`), its conditions warm, its inputs the prover's `gpu_seconds_per_token_prove.session` and serving's `gpu_seconds_per_token_prove.steady`. The FlashProve-like row is unchanged: headline D-OVERHEAD-S, no `overhead_vs_production_warm` key. Null cases: no serving run → `missing_input`, headline still warm, no conditions; a serving run of one batch (no steady scope) → `fewer_than_two_proofs`; a serving run with "steady scope under 60 s" or a sizing capture → `missing_input`; a failed prover session → `step_failed`. The words name both scopes and print no high-load figure.

- TC-DERIVE-WORKED: the worked example above, every row, within `rel_tol=1e-12`.
- TC-STAT-FAILED (`test_stats.py`): the statistics fixture; asserts n 3, n_failed 1, mean 100, stdev 10, min 90, max 110.
- TC-STAT-N1 (`test_stats.py`): one successful repetition; stdev null, mean equals the value.
- TC-STEADY-K1 (`test_scopes.py`): k = 1; `prove_steady_seconds` and `rate_prove.steady` null with `fewer_than_two_proofs`; session and whole wall present.
- TC-STEADY-UNOBSERVABLE: all proofs released in one watcher observation; steady null with `not_externally_observable`.
- TC-HONEST-REJECT (`test_tokens.py`): one honest proof rejected; repetition failed at `verify`; no rates emitted.
- TC-NULL-DIV: zero tokens; every rate, and `tokens_covered_per_proof`, null with a reason, none equal to 0. For D-SPAB-S (`test_null_div_active_weight_bits`): a parameter count of 0, or weight bits of 0 (reachable through a G4 recompute of an edited input), gives null `not_applicable`, never infinity.
- TC-GSPT-WORKED: the two D-GSPT rows of the worked example.
- TC-OVERHEAD-GSPT (`test_cross_rows.py`): the two overhead rows and `pairs` (hand-computed, three system and three serving repetitions).
- TC-OVERHEAD-PAIR-PROFILE (`test_cross_rows.py`): an H100 system row against an H200 serving row gives `not_applicable`, and so does a hosted row against a docker row.
- TC-OVERHEAD-FEWEST (`test_cross_rows.py`): TP4 with one successful paired run and two `resource` failures, TP8 with three successes; TP4 joins (the smallest count with a joinable run).
- TC-OVERHEAD-PROMPTS (`test_cross_rows.py`): serving runs that replay another system's runs do not enter the mean; none paired gives `missing_input`.
- TC-OVERHEAD-SASH (`test_cross_rows.py`): system steady null `not_externally_observable` passes that reason on.
- TC-OVERHEAD-RULE (`test_cross_rows.py`): a serving run at b > 1 without `steady_rule` gives `missing_input`; system runs without it give `not_applicable`.
- TC-OVERHEAD-DIGEST (`test_cross_rows.py`): a serving run with another model digest, or another engine image digest, gives `not_applicable`; a run under a new record version with the same model digest joins.
- TC-GSPT-FREEZE (`test_freeze.py`): a stored run without the key gets it from `gpu.count`.
- TC-GSPT-X4 (`test_runner.py`): a fake 4-GPU serving job records `inputs.gpu_count` 4, and D-GSPT = D-SPT × 4; D-COST-1K reads the same pointer. A profile with GPU count missing or 0 gives `config`.
- TC-GRADE-2: an adapter-reported phase passed as a derivation input raises `internal`.
- TC-STEADY-BATCH (`test_scopes.py`, `test_tokens.py`): b = 24, 5 batches, 120 releases. Steady tokens are 96 × 1,024 and the start is the last release of `request_index` 0 to 23. With b = 24 and k = 24 the result is `fewer_than_two_proofs`. An interleaved release order (request 30 released before request 23) gives the same start; with releases in index order except requests 23 and 30 swapped, requests 24 to 30 are released before the start and leave the steady tokens, 89 × 1,024, and the warning counts 7. A first batch whose last release follows every later release gives `fewer_than_two_proofs`. A proof without `request_index` at b = 24 gives `missing_input`.
- TC-SCOPE-ORDER (`test_scopes.py`): synthetic timeline with r_1 before `prove` start raises `internal`.
- TC-TPP-WORKED (`test_tokens_covered_per_proof_worked_example`): the worked example's D-TPP row, 5,000 / 5 = 1,000 token within `rel_tol=1e-12`, with grade `derived`, unit `token` and scope null.
- TC-TPP-ZERO (`test_tokens_covered_per_proof_zero_is_null`): `proofs_count` 0, and separately `tokens_covered_total` 0 with `proofs_count` 5, each give a null value with `null_reason: not_applicable`, never 0.
- TC-TPP-REFERENCE (`test_tokens_covered_per_proof_reference_is_null`): a `kind: reference` repetition with `proofs_count` 1 and `tokens_covered_total` 4,608 token (fixture values, not a result) gives a null value with `null_reason: not_applicable`.
- TC-TPP-SOURCE (`test_tokens_covered_per_proof_source`): `source.ref` is `derive:D-TPP@<harness version>` and `source.inputs` points at `tokens_covered_total` then `proofs_count`, in that order (INV-DERIVE-4).
- TC-TPP-STAT (`test_stats.py::test_tokens_covered_per_proof_constant_statistics`): the constant-count statistics fixture; asserts n 3, n_failed 0, mean 1,000, stdev 0, min 1,000, max 1,000.

- TC-BPAB-WORKED, TC-VSPAB-WORKED (`test_per_bit_proof_size_and_check_time_flashprove_like`, `test_per_bit_proof_size_and_check_time_sash_like`, `test_per_bit_proof_size_and_check_time_nulls`): two hand-computed cases with the arithmetic in their docstrings (120 proofs of 1,024 positions at 17e9 × 4 bits: 2.5e-7 B/bit_token and 2.5e-13 s/bit_token; one proof of 1,088 positions at 8e9 × 8 bits: 6.25e-4 B/bit_token and 5e-11 s/bit_token), units, scopes, inputs in order, and the null rules; the worked example gains the D-BPAB and D-VSPAB rows.
- TC-SPAB-WORKED (`test_seconds_per_active_weight_bit_worked_example`): the worked example's D-SPAB row, 0.01 / (8.0e9 × 8) = 1.5625e-13 s/bit_token within `rel_tol=1e-12`, with grade `derived`, unit `s/bit_token`, scope `prove.steady` and tier `reported`.
- TC-SPAB-SOURCE (`test_seconds_per_active_weight_bit_source`): `source.ref` is `derive:D-SPAB-S@<harness version>` and `source.inputs` points at `seconds_per_token_<S>`, then the parameter count, then the weight bits.
- TC-SPAB-NO-BITS (`test_seconds_per_active_weight_bit_no_bits_is_missing_input`, `test_seconds_per_active_weight_bit_recorded_null_bits`): no weight bits, as an absent input or as the runner's null `inputs.weight_bits` with `missing_input`, gives null with `missing_input` in all three scopes, while D-SPT-S keeps its value.
- TC-SPAB-REFERENCE (`test_seconds_per_active_weight_bit_reference_is_null`): a `kind: reference` repetition gives null with `not_applicable`.
- TC-SPAB-NULL (`test_seconds_per_active_weight_bit_follows_steady_null`): k = 1; the null D-SPT-prove.steady passes `fewer_than_two_proofs` on.
- TC-SPAB-CHECK (`test_derive_check.py`): in a reference run D-SPAB-S recomputes as null `not_applicable`; an unresolvable weight-bits input recomputes a stored null `missing_input` as it is and fails a stored value with DER-3.
- TC-SPAB-CORRECTION (`test_runner.py::test_g4_survives_a_weight_bits_correction`): a fake run records `inputs.weight_bits` 8 and D-SPAB-S points there; after the workload file's weight bits change to 4, G4 on the stored run is still clean (RFC-0003 WB-4).
- TC-Q3-FREEZE (`test_freeze.py`): `test_freeze_evaluates_a_stored_run_without_the_key` (a run without D-TPP and D-SPAB-S keys next to a run with them: D-STAT has n = 2, the freeze value sits in `freeze_derived` and D-STAT points there; hand-computed D-SPAB-prove.steady 0.01 / (64 × 8) s/bit_token for the fake workload, fixture values), `test_freeze_value_of_another_workload_version_is_missing_input`, `test_freeze_stops_on_different_workload_inputs` (RFC-0003 WB-4); `test_derive.py::test_freeze_values_fill_only_missing_keys`.

TC-DERIVE-WORKED covers the D-TPP and D-SPAB rows.

Property tests (hypothesis) under `harness/tests/property/`, in the file an entry names where one exists:

- P-RATE-INVERSE: for positive finite tokens and seconds, `rate × seconds_per_token` is within 4 ulp of 1.
- P-DERIVE-IDEMPOTENT: `derive(derive(run))` equals `derive(run)` byte for byte after serialisation.
- P-STAT-BOUNDS (`test_stat_property.py`): min <= mean <= max for any non-empty list of finite values.
- P-CHECK-DETECTS (`harness/tests/unit/test_derive_check.py`): perturbing any stored derived value by one ulp makes `derive --check` fail.

Schema tests (RFC-0012): invalid examples for a time unit with null scope (`s/bit_token` included), an `external` quantity without `upstream_scope`, a `derived` quantity without a formula id; a valid D-SPAB-S quantity.

## Decisions

- Q1. Per-request latency percentiles are not recorded: v0.1 workloads have fixed batches and no arrival process.
- Q2. SASH has no part-granular steady scope: its `prove.steady` is null and its `loop` figure is shown as `external`, mapping approximate. Since the amendment of 2026-11-09 the overhead is a steady figure, so every SASH workload's D-OVERHEAD-S is null with `not_externally_observable`: `systems/sash/system.yaml` declares `incremental_proofs: false`, and a workload with more sequences per session would not change that while SASH does not release proofs one by one at its pin. SASH's rows show D-OVERHEAD-WARM instead, its proving session over warm serving's steady scope (INV-DERIVE-11).
- Q3. A run stored before a formula existed keeps its `run.json` (APP-1): the release freeze evaluates D-TPP for each such successful repetition from that run's recorded `tokens_covered_total` and `proofs_count`, with `source.inputs` pointing into the unchanged `run.json`, and D-STAT runs over those values. D-STAT for D-TPP MUST cover every successful repetition of the configuration: a run without the key gets the freeze-time value, or the freeze stops with an error naming the run; it never drops out of n. The freeze writes those values to `releases/<release>/index.json` under `freeze_derived` (by run id, then metric id; an optional `release-index/1` property, RFC-0012) and their D-STAT to the configuration's statistics, whose inputs point at `index.json#/freeze_derived/<run id>/<metric>`; it does not write `run.json`, so `iproofs derive <run-dir> --check` does not see them; RFC-0013 G4 holds them through its rule for `releases/*/index.json` aggregates (`DER-1` on a mismatch, `DER-3` on a missing input), which the G4 code does not yet apply. The same rule applies to D-SPAB-S (amendment of 2026-11-08): the freeze evaluates it from each such run's recorded `seconds_per_token_<S>` and the workload record's parameter count and weight bits at the release commit; when the record now holds another version than the run's, those inputs do not apply and the value is null with `missing_input`. A freeze value whose run.json input the run does not hold is null with `missing_input`, never computed from an intermediate. `iproofs.release` applies this rule (`derive.freeze_values`, FREEZE_FORMULAS = D-TPP, D-SPAB-S).
- Q4. D-SPAB-S divides by bits, as in the catalogue; no multiply-accumulate (MAC) form is computed or shown. A MAC form (one token through the active weights plus attention at the workload's `prompt_tokens`) would count attention, which grows with prompt length (INV-DERIVE-7's limit), but it needs layer, head and head-size figures from a pinned configuration (the Maverick workloads pin none), and it drops the weight bits, so a 4-bit and an 8-bit model of one shape would count alike.
- Q5. The two steady-only filters of INV-DERIVE-2 (f), the 60 s steady minimum (RFC-0015 SRV-1) and `steady_rule` at b > 1 (INV-SCOPE-5), apply to the session figure too, so a row's session and steady figures divide by the same serving runs. The overview's overhead column sorts a warm figure (INV-DERIVE-11) among steady ones; this happens only within one workload's table (RFC-0009 S6), when two systems on that workload have different headlines. Each cell is labelled with its scopes; a warm figure counts the prover's start-up, so it is larger than the same system's steady figure would be.
- Q6. A warm headline carries no high-load context figure: no D-OVERHEAD-HIGH-WARM is computed, and a warm headline prints no high-load figure beside it; D-OVERHEAD-HIGH-S stays computed at each scope.

## References

- docs/PRD.md §1, §4 (G2), §7 (F3, F9, F10).
- [RFC-0003](0003-workloads.md) for shapes, `active_parameters_per_token` and weight bits; [RFC-0005](0005-adapter-contract.md) for proof directories and `tokens_covered`; [RFC-0006](0006-reference-hardware-and-cost.md) for `price`; [RFC-0007](0007-evidence-tiers-and-reproduction.md) for tiers; [RFC-0009](0009-results-and-publication.md) for the site that prints D-TPP; [RFC-0011](0011-measurement-and-sampling.md) for how each recorded metric is measured; [RFC-0012](0012-schemas-and-serialization.md) for the quantity schema; [RFC-0013](0013-validation-and-ci.md) for the CI gates; [RFC-0015](0015-reference-rows.md) for reference rows.
- SASH results: `sg-ai-safety-hub/zk-inference-results` at `11decec3c0b62c707618aab5deb82750b355d202` (`constants.json`).
- FlashProve: `anthropics/FlashProve` at `9e2bdd8ff5bf9c62f18263d7dac189b0400b260c` (`docs/figures.tsv`).
