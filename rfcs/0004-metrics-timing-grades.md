# RFC-0004: Metrics, timing scopes and grades

- Authors: AbdelStark
- Created: 2026-11-03
- Requires: RFC-0003, RFC-0012
- Amended by RFC-0018 (2026-11-10): for Level 1 runs the steady scope is the release-group rule (RFC-0018 CO-2, CO-3), which replaces INV-SCOPE-5. v0.1's batch-membership rule overcounts FlashProve's steady requests (119 counted, 96 produced), so its published 5.746 GPU-s per request reads 7.060 to 7.195 under the new rule; v0.1 records stay as stored.

## Summary

This RFC defines the raw metrics recorded for every run, the timing scopes required on all time-based figures, the grade labels carried by every quantity, the rules for counting tokens covered, the complete catalogue of derived metrics and exact formulas, and the summary statistics aggregated across repetitions. All derived values are computed programmatically by `iproofs.derive` from stored raw measurements and are never entered by hand. Any published number missing its scope (for time-based metrics), grade, tier, or source is invalid and rejected by CI (RFC-0013).

## Motivation

The first two v0.1 systems publish throughput figures measured over different timing boundaries. SASH's results repository tags each number with a scope (`commit`, `stwo total`, `whole wall`, `loop`, `primitive`) and a grade (`measured`, `derived`, `projected`, `external`, `asserted`). Its 4,096-context headline reports 1.251 positions/s in `loop` scope and 0.840 positions/s in `whole wall` scope across 4,608 positions (grade external, tier reported, source `sg-ai-safety-hub/zk-inference-results` at `11decec3c0b62c707618aab5deb82750b355d202`). FlashProve reports 111.23 ± 0.92 tokens/s of prefill at batch size 24 in steady state (excluding startup and commitment), or 103.60 tokens/s when startup is included across a five-batch session (both grade external, tier reported, source `anthropics/FlashProve` at `9e2bdd8ff5bf9c62f18263d7dac189b0400b260c`). Because the exact same run yields noticeably different rates depending on where the clock starts and stops, any rate without an explicit timing scope cannot be compared meaningfully (PRD §1, PRD G2, PRD F3). This RFC binds the timing scope directly to each number and defines exact boundaries for every scope.

## Goals

- Assign every recorded metric a stable key in `run.json` `metrics`, a unit from the RFC-0012 vocabulary, and a well-defined scope rule.
- Define every timing scope via two externally observable boundary events timestamped on the harness clock (RFC-0011).
- Give every derived metric a formula ID, exact formula, ordered inputs, unit, and null rule, verified bit for bit by `iproofs derive --check`.
- Import upstream figures strictly as `external` quantities, preserving their original upstream scope while labelling the mapping to harness scopes as `exact`, `approximate`, or `none`.
- Standardise repetition summary statistics: `n`, `n_failed`, mean, sample standard deviation, min, and max.

## Non-Goals

- Per-request latency percentiles and queueing metrics (v0.1 workloads use fixed batches with no arrival process; Q1).
- FLOP-based cross-model normalisers (rejected in Alternatives Considered; a multiply-accumulate variant of D-SPAB-S is addressed in Q4).
- Model-normalised proof sizes (succinct proofs grow minimally with model size, so dividing proof bytes by model size inherently favours larger models).
- Measurement collection mechanics (RFC-0011), pricing inputs (RFC-0006), quantity serialization (RFC-0012), and evidence tiers (RFC-0007).
- Pricing CPU time or host memory (RFC-0006 rule 5).

## Proposed Design

### Vocabularies

The enums for unit, grade, tier, and `null_reason` are declared once in `schema/quantity/1.schema.json` (RFC-0012); this RFC defines their semantics.

Grades (every quantity carries exactly one):

| Grade | Meaning | Allowed `source.kind` |
|---|---|---|
| `measured` | Recorded directly by the harness from an artifact of this project's run | `harness`, `adapter` |
| `derived` | Computed by `iproofs.derive` from other quantities using a formula in this RFC | `derivation` |
| `projected` | Estimated from a cost model whose identifier and inputs are recorded in `source.ref` | `derivation` |
| `external` | Copied from a public upstream source at a pinned commit or URL, preserving its original scope and grade | `upstream` |
| `asserted` | An unmeasured reference input (such as a GPU hourly price), accompanied by source and date | `reference_file` (either a reference file or a workload record copied into `run.json` `inputs`, RFC-0003 WB-4) |

INV-GRADE-1: every quantity with grade `derived` or `projected` MUST name a formula ID from the catalogue below in `source.ref`.
INV-GRADE-2: a quantity with grade `measured` and `source.kind: adapter` represents an adapter-reported timing. It MUST NOT feed any derived metric in the catalogue below, and may only appear alongside harness measurements explicitly labelled as adapter-reported. One exception, for Level 1 boards ([RFC-0018](0018-level-1-ladder.md) CO-9, 2026-11-26): the generation part of a further reply of a system with no generation phase of its own is the adapter's reported phase, taken only when the reported phases sum to the harness-timed `prove` call within 1 %, and labelled with its source (`D-L1-FURTHER-GENERATION-ADAPTER`).
INV-GRADE-3: a `derived` quantity retains grade `derived` even when one or more of its inputs are `asserted` (such as GPU price); each asserted input is cited in `source.inputs`.

### Timing scopes

Every duration and rate MUST carry exactly one timing scope (INV-SCOPE-1). Scope boundaries are timestamped by the harness using `time.monotonic_ns()` (RFC-0011). A proof's "release time" is the moment the harness detects the atomic rename of `/io/proofs/.tmp-<proof_id>/` to `/io/proofs/<proof_id>/` (RFC-0005, RFC-0011).

| Scope | Start event | End event | Tokens attributed |
|---|---|---|---|
| `setup` | `setup` container call start | `setup` call exit | none (not a rate scope) |
| `commit` | `commit` call start | `commit` call exit | none (not a rate scope) |
| `prove.session` | `prove` call start | release time of the last proof `r_k` | all proofs `1..k` |
| `prove.steady` | last release among requests with `request_index < b` (`b` = batch size; `r_1` when `b = 1`) | release time of the last proof `r_k` | requests with `request_index >= b` (proofs `2..k` when `b = 1`) |
| `whole_wall` | `commit` call start | release time of the last proof `r_k` | all proofs `1..k` |
| `verify` | `verify` call start for one proof, 8-CPU verifier container | that call's exit | the proof's tokens |
| `verify.single_thread` | same, 1-CPU verifier container | that call's exit | the proof's tokens |
| `primitive` | adapter-reported only | adapter-reported only | adapter-declared |

Boundary rules:

- Model downloads and container image pulls never fall inside any timing scope. `setup` is excluded from `whole_wall` because setup is a one-time preparation step not repeated per request, whereas `commit` is included because v0.1 FlashProve runs commit fresh on every run (`-M 1`).
- INV-SCOPE-2: `prove.steady` requires `k >= 2`. When `k < 2`, both its duration and rate are `null` with `null_reason: fewer_than_two_proofs`.
- INV-SCOPE-3: if the proof-release watcher sets `observable: false` (either because the system sets `incremental_proofs: false` or because all proofs appeared in a single poll observation; RFC-0011 §Proof release watcher), `prove.steady` is `null` with `null_reason: not_externally_observable`. `prove.session` and `whole_wall` are still reported because their end boundary remains the final release.
- INV-SCOPE-4: for every completed job, `commit` start `<= prove` start `<= r_1 <= r_k`. Any violation is an `internal` error (RFC-0010).
- INV-SCOPE-5 (amendment of 2026-11-09): the steady scope is defined by batch membership rather than raw release order. For workload batch size `b`, the first batch comprises requests with `request_index < b`. `prove.steady` begins at the last release among those first-batch requests and ends at `r_k`. Its attributed tokens are the tokens of all requests with `request_index >= b` released strictly after that start time; any later-batch request released at or before the start time completed its work prior to the steady window, so it is excluded from steady tokens and the run logs the warning `"N later-batch request(s) released at or before the steady start, left out of the steady tokens"`. When `b = 1`, this simplifies to `r_1` and proofs `2..k` as before. `prove.steady` is null with `fewer_than_two_proofs` if no later-batch request releases after the start (such as when fewer than two batches finish), and null with `missing_input` if `b > 1` and any proof lacks `request_index`. Under this rule, a system that releases proofs one by one within a batch gets the exact same boundary and token count as one that flushes each batch at the end, and a system that overlaps batches gets the same boundary while dropping requests finished before the window opened. Because the rule applies identically to provers and reference servers, both sides of D-OVERHEAD-S cover the exact same batches. Every manifest records `workload.steady_rule: batch-membership`. Runs stored prior to this amendment retain their original `tokens_covered_steady` and steady durations (APP-1); releases annotate any such configuration at `b > 1` with `steady_boundary: "first-proof boundary (before 2026-11-09)"` in the release index, and runs at `b > 1` lacking `steady_rule` cannot join D-OVERHEAD-S on either side (INV-DERIVE-2).
- Container startup overhead stays inside each step's wall duration and is never subtracted. The `info` call's duration is recorded as `info_seconds` so readers can see the approximate startup cost.

RISK: if an upstream prover flushes all proofs only when the process exits, `prove.steady` cannot be observed externally. Resolution: the adapter README documents whether upstream emits proofs incrementally at the pinned commit; if it does not, `prove.steady` is reported as null with its reason, and any upstream steady figure appears only as `external`. A future RFC MAY admit adapter-reported per-batch timestamps as a clearly labelled secondary steady metric once needed.

RISK: SASH proves an entire sequence as a grid of segments, so one proof in this benchmark corresponds to the full set of segment proofs plus the passing grid check (RFC-0005). With one sequence per job (RFC-0003), `k = 1`, leaving `prove.steady` null under INV-SCOPE-2; SASH's `loop` figure therefore appears only as `external` with mapping `approximate`, and tokens are never apportioned across individual segments (Q2).

### Mapping from upstream scopes

Upstream figures enter via `systems/<name>/external.yaml` as quantities with grade `external`, tier `reported`, `source.kind: upstream`, plus two additional fields defined in RFC-0012: `upstream_scope` (quoting the upstream author's wording) and `mapping` (`exact`, `approximate`, or `none`). `scope` contains the corresponding harness scope, or `null` when `mapping` is `none`.

| Harness scope | SASH upstream scope | Mapping | FlashProve upstream scope | Mapping |
|---|---|---|---|---|
| `commit` | `commit` (per run) | exact | `cp_commit` | exact |
| `prove.steady` | `loop` | approximate | steady rate, start-up and commitment excluded | approximate |
| `prove.session` | not published | none | rate with start-up counted over a session | approximate |
| `whole_wall` | `whole wall` | approximate | not published | none |
| `verify` | per-segment verification summed per sequence | approximate | `cp_verify` | approximate |
| `primitive` | `primitive` | exact | not published | none |
| none | `stwo total` | none | | |

INV-MAP-1: the harness's own timing scopes are authoritative. `external` quantities are never combined with `measured` quantities in a derived metric; derivations over external inputs are restricted to run-campaign planning budgets (`docs/spec/08-performance-budget.md`) and carry grade `projected`.

Mappings are marked `approximate` whenever upstream boundary events differ slightly from harness boundaries (for example, whether process startup precedes the first batch timestamp). The site displays "approximate" alongside every such value.

### Tokens covered

INV-TOK-1: `tokens_covered` counts the sequence positions whose computation a single proof binds, as specified in the claim card's `coverage` section (RFC-0002) and calculated by the harness from the workload shape (RFC-0003). Whenever `system.yaml` sets `proofs.tokens_covered: declared_per_proof`, the adapter also emits `tokens_covered` per proof in `out.json` (RFC-0005); any discrepancy against the harness calculation triggers an `adapter` failure.

The coverage kind comes from `proofs.tokens_covered` in `system.yaml` ([RFC-0005](0005-adapter-contract.md#systemyaml)), with `declared_per_proof` accepting the adapter's per-proof count after passing the INV-ADAPTER-7 check.

| Coverage kind (claim card) | Tokens covered by one proof |
|---|---|
| `window` (FlashProve v0.1) | `prompt_tokens` of the window (prompt = window length, output = 0) |
| `prompt_plus_output` (SASH v0.1) | `prompt_tokens + output_tokens` of the sequence (prompt and output reported separately) |

Thus `fp-maverick-w1024-b24` covers 1,024 tokens per proof and `sash-l31-8b-c4096` covers 4,096 + 512 positions per proof, matching the 4,608 positions reported in SASH's results repository (external, reported, at the pinned commit).

INV-TOK-2: a repetition counts as successful only if every honest proof receives the verdict `accept`. If any honest proof is rejected or fails verification, the repetition is recorded as failed at step `verify` (RFC-0010), increments `n_failed`, and emits no throughput metrics, ensuring rates never blend accepted and rejected work.

### Recorded metrics

Keys stored under `run.json` `metrics` for each repetition. Unless noted otherwise, all carry grade `measured`, tier `reported`, and `source.kind: harness`.

| Metric id | Unit | Scope | Definition |
|---|---|---|---|
| `info_seconds` | s | `setup` | Wall duration of the `info` call (tracks container startup overhead; tagged `setup` because it runs prior to setup) |
| `setup_seconds` | s | `setup` | Wall duration of the `setup` call |
| `commit_seconds` | s | `commit` | Wall duration of the `commit` call |
| `prove_session_seconds` | s | `prove.session` | `r_k` minus `prove` call start |
| `prove_steady_seconds` | s | `prove.steady` | `r_k` minus the steady start (`r_1` for `b = 1`; the last release of the first batch for `b > 1`, INV-SCOPE-5) |
| `whole_wall_seconds` | s | `whole_wall` | `r_k` minus `commit` call start |
| `prove_call_seconds` | s | `prove.session` | Full wall duration of the `prove` call (may exceed `prove_session_seconds` due to teardown) |
| `proofs_count` | count | null | `k`, total proofs released |
| `requests_count` | count | null | Total requests in the job (`batch_size × batches_per_session`) |
| `tokens_covered_total` | token | null | Sum of covered tokens across proofs `1..k` |
| `tokens_covered_prompt` | token | null | Prompt-token portion of `tokens_covered_total` |
| `tokens_covered_output` | token | null | Output-token portion of `tokens_covered_total` |
| `tokens_covered_steady` | token | null | Sum of covered tokens for requests with `request_index >= b` released after steady start (proofs `2..k` when `b = 1`, INV-SCOPE-5) |
| `proof_bytes` | B | null | Statistic over proofs: total bytes across all parts of one proof |
| `proof_bytes_total` | B | null | Sum of `proof_bytes` across all proofs |
| `verifier_download_bytes` | B | null | Total bytes of `verifier_files` produced by `commit` (downloaded once per commitment) |
| `prover_keep_bytes` | B | null | Total bytes of `prover_files` produced by `commit` |
| `verify_seconds` | s | `verify` | Statistic over proofs for one `verify` call on 8 CPUs |
| `verify_seconds_total` | s | `verify` | Sum of `verify_seconds` across all proofs |
| `verify_single_thread_seconds` | s | `verify.single_thread` | Statistic over proofs on 1 CPU |
| `verify_host_memory_peak_anon` | B | null | Maximum anonymous host memory across `verify` calls (RFC-0011) |
| `<step>_gpu_memory_peak` | MiB | null | Peak GPU memory for step in `commit`, `prove` (RFC-0011) |
| `<step>_gpu_util_mean`, `<step>_gpu_util_p95` | % | null | Mean and 95th-percentile GPU utilisation for step in `commit`, `prove` |
| `<step>_gpu_energy` | J | null | Optional GPU energy consumed for step in `commit`, `prove` |
| `<step>_host_memory_peak_kernel` | B | null | Cgroup `memory.peak` for step in `commit`, `prove` |
| `<step>_host_memory_peak_anon` | B | null | Peak sampled `memory.stat` `anon` for step in `commit`, `prove` |
| `<step>_cpu_seconds` | s | `commit` or `prove.session` | Difference in cgroup `cpu.stat` `usage_usec` over the step |
| `verdicts_accept_count` | count | null | Number of honest proofs accepted |
| `adapter_phases.<step>.<name>` | s | `primitive` | Adapter-reported internal timing of `commit` or `prove`, one entry per phase name the step's output reports, a name reported twice summed (`source.kind: adapter`; subject to INV-GRADE-2) |

A "Statistic over proofs" stores the mean in `value` and records `n`, `mean`, `stdev`, `min`, and `max` across all proofs within that repetition inside `stats` (`n_failed` is always 0 here under INV-TOK-2).

### Derived metric catalogue

Inputs written as `metrics.X` come from the same repetition's recorded metrics, while `ref.*` inputs come from the matching reference-system configuration (RFC-0015). `price` is `cost.price_per_gpu_hour_usd` from `reference/<release>.yaml` (asserted, RFC-0006). `gpus` is `gpu.count` from the run's hardware profile (INV-DERIVE-8), copied into `run.json` `inputs.gpu_count` (asserted, source `reference/<release>.yaml#/profiles/<profile>/gpu/count`). If any profile declaring a GPU has `gpu.count` missing or below 1, the runner raises a `config` error before `info`; CPU-only test profiles (`gpu: null`, such as `reference/ci.yaml`) omit `gpu_count`, leaving D-GSPT-S null. For runs stored before `inputs.gpu_count` existed, G4 recomputes D-COST-1K-S using `gpu.count` from the reference file, matching pre-2026-11-09 behaviour. `active_parameters_per_token` comes from `model.parameters.active_per_token` and `weight_bits` comes from `precision.weight_bits.bits` (literal for `stated`, loader-computed for `file_size`, and header-rechecked for `computed`; RFC-0003 WB-5); the runner copies both from the workload file ([RFC-0003](0003-workloads.md#weight-bits)) into `run.json` `inputs` (`inputs.active_parameters_per_token`, `inputs.weight_bits`, asserted quantities; RFC-0003 WB-4), while older runs lacking `inputs` reference the workload record directly. In the table below, `S` ranges over the rate scopes {`prove.steady`, `prove.session`, `whole_wall`}, `T(S)` is `tokens_covered_steady` when `S = prove.steady` and `tokens_covered_total` otherwise, and `sec(S)` is the corresponding duration metric.

| Formula id | Metric id | Level | Formula | Unit | Scope | Null when |
|---|---|---|---|---|---|---|
| D-RATE-S | `rate_<S>` | repetition | T(S) / sec(S) | token/s | S | sec(S) null or 0; T(S) = 0 |
| D-SPT-S | `seconds_per_token_<S>` | repetition | sec(S) / T(S) | s/token | S | as D-RATE-S |
| D-COST-1K-S | `cost_per_1k_tokens_<S>` | repetition | D-SPT-S × 1000 × gpus × price / 3600, `gpus` read from `run.json#/inputs/gpu_count` (equivalent to D-GSPT-S × 1000 × price / 3600) | USD/1k_token | S | D-SPT-S null; price null; `gpu_count` missing (`missing_input`) |
| D-GSPT-S | `gpu_seconds_per_token_<S>` | repetition | D-SPT-S × gpus | gpu_s/token | S | D-SPT-S null (inherits reason); `gpu_count` missing (`missing_input`) or 0 (`not_applicable`) |
| D-COMMIT-AMORT-H1 | `commit_seconds_per_token_h1` | repetition | `commit_seconds` / (tokens_covered_total / requests_count × 1) | s/token | `commit` | commit failed |
| D-COMMIT-AMORT-H1000 | `commit_seconds_per_token_h1000` | repetition | `commit_seconds` / (tokens_covered_total / requests_count × 1000) | s/token | `commit` | as above |
| D-APT-S | `active_param_tokens_per_second_<S>` | repetition | D-RATE-S × `active_parameters_per_token` | param_token/s | S | D-RATE-S null; parameter count missing (`missing_input`) |
| D-SPAB-S | `seconds_per_active_weight_bit_token_<S>` | repetition | D-SPT-S / (`active_parameters_per_token` × `weight_bits`) | s/bit_token | S | D-SPT-S null (inherits reason); weight bits or parameter count missing (`missing_input`); parameter count or weight bits 0 (`not_applicable`); always null with `not_applicable` for `kind: reference` (INV-DERIVE-7) |
| D-BPT | `proof_bytes_per_token` | repetition | `proof_bytes_total` / tokens_covered_total | B/token | null | tokens 0 |
| D-VSPT | `verify_seconds_per_token` | repetition | `verify_seconds_total` / tokens_covered_total | s/token | `verify` | tokens 0 |
| D-BPAB | `proof_bytes_per_active_weight_bit_token` | repetition | D-BPT / (`active_parameters_per_token` × `weight_bits`): proof bytes per token covered per bit of active weights, sharing the D-SPAB-S basis (amendment of 2026-11-09) | B/bit_token | null | D-BPT null (inherits reason); same parameter/weight-bits rules as D-SPAB-S; always null with `not_applicable` for `kind: reference` |
| D-VSPAB | `verify_seconds_per_active_weight_bit_token` | repetition | D-VSPT / (`active_parameters_per_token` × `weight_bits`): verification seconds per token covered per bit of active weights (amendment of 2026-11-09) | s/bit_token | `verify` | same as D-BPAB, using D-VSPT |
| D-VSPT-1T | `verify_single_thread_seconds_per_token` | repetition | single-thread verify seconds of the first proof / tokens covered by the first proof (single-thread verify executes on the first proof only, RFC-0010) | s/token | `verify.single_thread` | as D-VSPT |
| D-TPP | `tokens_covered_per_proof` | repetition | `tokens_covered_total` / `proofs_count` | token | null | tokens 0 or `proofs_count` 0 (`not_applicable`); always null with `not_applicable` for `kind: reference` (INV-DERIVE-6) |
| D-VERIFY-HOST | `verify_host_ratio` | configuration | mean `verify` seconds on a separate verifier host / mean `verify` seconds on the emulated verifier profile, over identical proofs | ratio | `verify` | null with `missing_input` unless both host types verified the same proofs (RFC-0006 verifier emulation check) |
| D-STAT | any of the above, configuration level | configuration | summary statistics over successful repetitions (§Statistics) | as input | as input | n = 0 |
| D-OVERHEAD-S | `overhead_vs_production_<S>` | release | mean(system `gpu_seconds_per_token_<S>`) / mean(production-serving `gpu_seconds_per_token_<S>`, matched load) | ratio | S (`prove.steady`) | INV-DERIVE-2 |
| D-OVERHEAD-WARM | `overhead_vs_production_warm` | release | mean(system `gpu_seconds_per_token_prove.session`) / mean(production-serving `gpu_seconds_per_token_prove.steady`, matched load, lengthened per RFC-0015 SRV-1); includes prover startup against warm serving (INV-DERIVE-11, amendment of 2026-11-09) | ratio | `prove.session` (prover's scope; serving's is `prove.steady`) | INV-DERIVE-2 |
| D-OVERHEAD-HIGH-S | `overhead_vs_production_high_<S>` | release | mean(system `gpu_seconds_per_token_<S>`) / mean(production-serving `gpu_seconds_per_token_<S>`, high load) | ratio | S | INV-DERIVE-2 |
| D-AGREE | `agreement_rate` | release | agreement positions / (agreement + disagreement positions), RFC-0015 RC-5 | ratio | null | no compared positions; recompute row `not_measurable_on_profile` |
| D-PROVIDER-SPREAD | `provider_spread_<S>` | release | max across providers of configuration mean `rate_<S>` / min across providers of the same (RFC-0006 R4) | ratio | S | fewer than two providers (`not_applicable`) |
| P-CAMPAIGN | `campaign_gpu_seconds` | release plan | projection from `external` inputs (`docs/spec/08-performance-budget.md`); grade `projected`, never published as a result | s | `whole_wall` | any input missing (`missing_input`) |

Derivation rules:

- INV-DERIVE-1: configuration-level statistics aggregate per-repetition derived values (mean of rates) rather than pooling totals (rate of means), preventing a single slow repetition from skewing the denominator.
- INV-DERIVE-2 (amendment of 2026-11-09): D-OVERHEAD-S, D-OVERHEAD-HIGH-S, and D-OVERHEAD-WARM (INV-DERIVE-11) pair a proving system configuration with the production-serving configuration (RFC-0015 SRV-6) that satisfies every condition below:
  (a) its system is the single serve-role reference system listed in the workload's `systems` (RFC-0015 SRV-7);
  (b) its workload ID and version match exactly;
  (c) its profile is a serving profile whose `pairs_with` includes the prover row's profile (RFC-0006 R6), guaranteeing identical GPU model and runtime kind;
  (d) its `load_point` is `matched` (for D-OVERHEAD-S and D-OVERHEAD-WARM) or `high` (for D-OVERHEAD-HIGH-S);
  (e) its runs record the serving model digest (`serving_model.digest`, per RFC-0014) matching the serving record pinned for the workload at the release commit, and the engine image digest matching the release's `ref-serve` `system.yaml`. Record ID and version are display-only, so a byte-identical mirror leaves join keys intact while a re-pinned engine (RFC-0015 Q1) never pools with an older engine;
  (f) only completed serving runs whose `prompts_from` points to a run of this prover configuration enter the mean (RFC-0015 SRV-8), excluding any run carrying the warning `"steady scope under 60 s"` (RFC-0015 SRV-1) and, for `b > 1`, requiring `workload.steady_rule` (INV-SCOPE-5). Sizing captures (`workload.sizing_capture: true`, RFC-0015 SRV-1) never enter the mean because they exist solely to determine session length. Prover runs at `b > 1` without `steady_rule` are also excluded.
  Placement (RFC-0015 SRV-6): among matching configurations with at least one eligible run, the join selects the smallest GPU count. High-load overhead joins exclusively against that same matched profile. Null rules, evaluated in order:
  - no serve-role system listed for the workload -> key is omitted (e.g. CI workloads);
  - prover mean is null -> null with the prover's `null_reason` (for SASH: `not_externally_observable`);
  - serving configurations exist only on profiles failing (c) or with mismatched model/engine digests (e) -> null `not_applicable`; all prover runs at `b > 1` lack `steady_rule` -> null `not_applicable`; eligible high-load runs exist only on a different profile than the joined matched profile -> D-OVERHEAD-HIGH-S is null `not_applicable`;
  - no serving configuration satisfies (a) through (e), or none has an eligible run under (f) -> null `missing_input`;
  - serving mean is null -> null with the serving row's `null_reason`.
- INV-DERIVE-3: `active_parameters_per_token` comes from the workload record (RFC-0003), copied into `run.json` `inputs` at runtime (RFC-0003 WB-4) as an `asserted` quantity sourced to the model's documentation (all parameters for dense models, active parameters per token for MoE models). Because D-APT-S treats 4-bit and 8-bit weights identically, it is not used to compare provers across models (decided 2026-11-08): it remains in the catalogue so stored runs continue to pass G4 and `run/1` retains its schema keys, but no site page displays it. Cross-model comparisons use D-SPAB-S (INV-DERIVE-7) and D-OVERHEAD-S instead.
- INV-DERIVE-4: every derived quantity records `source: {kind: derivation, ref: derive:<formula id>@<harness version>, inputs: [<JSON pointers>]}` (RFC-0012), and inherits the lowest tier among its inputs (always `reported` inside `run.json`).
- INV-DERIVE-5: all arithmetic uses IEEE 754 binary64 evaluated left-to-right exactly as written in the catalogue table, with `math.fsum` for sums and `statistics.mean` / `statistics.stdev` for summary statistics. Derived numbers are stored unrounded, and `iproofs derive --check` enforces exact `==` equality against stored values, failing CI on any divergence (RFC-0013).
- INV-DERIVE-6: D-TPP reports the average number of sequence positions bound by a single proof (INV-TOK-1) across a repetition's proofs. Because it is a count rather than a duration or rate, it has no timing scope (INV-SCOPE-1 does not apply) and MUST NOT be presented as a throughput. It carries grade `derived` and tier per INV-DERIVE-4 (`reported` in `run.json`). Under `window` and `prompt_plus_output`, every proof covers the same count `c`, so `k × c / k` equals `c` exactly in binary64 whenever `k × c < 2^53`; under `declared_per_proof`, it averages the adapter's per-proof counts. Reference systems (`kind: reference`, RFC-0015) produce outputs rather than proofs (REF-2), so their D-TPP is always null with `null_reason: not_applicable` regardless of `tokens_covered_total` (REF-3) and `proofs_count`. At configuration level, D-STAT aggregates D-TPP across successful repetitions (`n`, `n_failed`, mean, stdev, min, max; for a constant count with `n >= 2`, stdev is 0 and min equals max). The site displays it as `"One proof covers"` (RFC-0009).
- INV-DERIVE-7: D-SPAB-S measures prover seconds per bit of active weights per token covered, dividing D-SPT-S by `active_parameters_per_token × weight_bits`. Token counts follow INV-TOK-1, so scope `S` and `T(S)` mirror D-SPT-S. Its grade remains `derived` despite its two `asserted` workload inputs (INV-GRADE-3, both recorded in `source.inputs`), and its tier follows INV-DERIVE-4. Its ordered inputs are `seconds_per_token_<S>`, `inputs/active_parameters_per_token`, and `inputs/weight_bits` from the run's own `run.json` (RFC-0003 WB-4), ensuring G4 recomputes stored runs solely from their own files even if a later workload version updates the weight width. When a workload omits `weight_bits` (RFC-0003 WB-3), `inputs.weight_bits` is recorded as a null asserted quantity with `missing_input` and D-SPAB-S evaluates to null with `missing_input` (never 0); a zero parameter count or zero weight width evaluates to null with `not_applicable` (TC-NULL-DIV). Reference systems (`kind: reference`, RFC-0015) prove nothing (REF-2), so their D-SPAB-S is always null with `not_applicable`.
  Display rule: like D-APT-S before it, D-SPAB-S is always displayed together with claim cards and the profile name, never in isolation. Every page displaying it includes the exact caveat: `"Attention cost grows with prompt length and is not in this normaliser, so two workloads of one model with different prompt lengths differ for that reason too ({prompt lengths}). Weight bits are as the workload records them, with their basis and source."`, where `{prompt lengths}` is computed automatically from the published release's workloads for that model rather than hardcoded (amendment of 2026-11-09, updating earlier text that referenced an unpublished 4,096-token SASH workload). If `weight_bits` carries a `note`, the page displays that note as well.
  Sorting rule: because D-SPAB-S divides a measured time by two asserted inputs, a row is eligible for sorting on this column only when both inputs match what their sources state for every active weight counted. A width tagged `covers: part` (RFC-0003 WB-1, such as SASH's weight-matmul width) extrapolates beyond upstream's statement when multiplied by all active parameters; such rows still show the value and its note, but are excluded from sorting and placed after sorted rows. Rows with `covers: all` (RFC-0003 WB-2 or WB-5) are sortable. Following RFC-0003 Q5 (2026-11-08), Maverick workloads use `computed` widths (`covers: all`) and sort normally, while SASH workloads and `l31-8b-c1024` remain `covers: part` and unsorted because SASH states a width only for weight matmuls (excluding per-channel scales) and its pinned files are BF16 (RFC-0003 Q5). In practice, this keeps sorting within one model and avoids comparing SASH against Maverick head-to-head (which INV-WL-5 forbids anyway).
- INV-DERIVE-8 (GPU accounting, amendment of 2026-11-09): GPU-seconds for any scope equal wall seconds multiplied by the number of GPUs allocated to the configuration (`profile.gpu.count`). Every GPU inside a tensor-parallel server counts, whereas extra GPUs billed by a provider that no job step binds do not count (RFC-0006 R1; for example, a single-GPU FlashProve job on Hugging Face Jobs `h200x2` counts 1 GPU). This exclusion is verified empirically rather than assumed: PC-GPU-IDLE (RFC-0006) checks every visible unbound GPU before `info`, after the final step, and once per second on a background thread throughout every step, flagging any compute process, memory increase above 1,024 MiB over baseline, or utilisation above 5 % (activity shorter than 1 second could fall between polls). The runner aborts with `config` before `info` if the bound GPU count disagrees with `gpu.count`. D-GSPT-S is the only per-token metric valid for comparing profiles with different GPU counts; D-SPT-S and D-RATE-S remain tied to their configurations and are never divided across profiles.
- INV-DERIVE-9 (statistics and display of the overhead, amendment of 2026-11-09): every overhead quantity includes `pairs: {n_system, n_serving, min, max}`, where `min` is `min(system) / max(serving)` and `max` is `max(system) / min(serving)`, bounding every pairwise ratio across repetitions (RFC-0012 adds this optional property).
  - The headline overhead is D-OVERHEAD-S at `prove.steady` and matched load, excluding startup on both sides just as FlashProve's own comparison does ([guide/performance.md L27](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/performance.md?plain=1#L27)). Systems lacking a steady scope (such as SASH) display D-OVERHEAD-WARM instead (INV-DERIVE-11).
  - D-OVERHEAD-HIGH-S at the same scope appears alongside a steady headline as context; a warm headline displays no high-load context figure (INV-DERIVE-11, Q6). Apart from D-OVERHEAD-WARM, overheads are computed solely at `prove.steady`.
  - Every page displaying an overhead ratio prints its execution conditions generated programmatically from `overhead_conditions` in the release index: the timing scope; batch sizes and batches per session on both sides; prompt counts per side (`prompt_count_run`), plus at high load the prompt-set difference (`"at high load: the prover's {n_p} prompts plus {n_s − n_p} further windows of the same seeded generator"`); the serving engine name, version, interface (`vllm serve` or `LLM` class, RFC-0015 Q8), per-load-point flags from `system.yaml` (`"engine defaults except --tensor-parallel-size 4, --max-model-len 1025, --max-num-seqs 24"`), and the batched-token limit logged by the engine (`engine.observed`); for high load, also its scope, batches per session, and GPU count; greedy decoding and warm/cold startup status (warm on both sides for steady, or warm serving against prover-included startup for warm headlines; INV-DERIVE-11); runtime kind (hosted or docker); serving release publisher/precision and proved precision; GPU count and model on each side; sample counts `n` and pairwise range; and the C5 caveat: `"GPU-seconds only: CPU and host memory are not counted; the prover's GPU comes with its host's CPUs and memory (RFC-0006 C5)"`. Each detail appears once per plate (amendment of 2026-11-09, research phase): scope and warm/cold status sit in the plate's scope row, `n` and pair range sit in the pairs row, serving and proved precision sit in the precision note, weight width sits in the per-Gbit basis, and the conditions line covers the remainder (using "cold" only when startup falls inside the scope).
  - The page also renders an auto-generated precision note: `"Proving the {workload precision.proved} model costs {X} times serving {publisher}'s {serving precision.name} release, in GPU-seconds per token."` (amendment of 2026-11-09: weight width, range, scope, and batch size moved to dedicated plate rows).
- INV-DERIVE-10 (session overhead, amendment of 2026-11-09): every proving system receives an overhead ratio, using D-OVERHEAD-S at `prove.steady` when available, or D-OVERHEAD-WARM when the system has no steady scope (INV-DERIVE-11).
- INV-DERIVE-11 (warm overhead, amendment of 2026-11-09: measuring overhead `"in the conditions the models are actually executed when served by model providers"`): for any proving system lacking a steady scope, the headline overhead compares its full proving session against already-running warm production serving.
  - Rationale: production inference servers stay warm, amortising engine startup across thousands of requests. A prover that releases no proofs until an entire request finishes (SASH at its pin: one proof per request, `incremental_proofs: false`, Q2) has no steady scope and incurs its own startup cost on every proved request, so `prove.session` reflects its real per-request cost. Dividing that by a cold single-request serving session would compare against vLLM startup time rather than production serving cost: in the development capture of `sash-l31-8b-c1024` at TP1, `prove.session` took 58.464736204 s for 1,088 tokens (measured, tier reported, n = 1, run `2026-11-09-ref-serve-sash-l31-8b-c1024-serving-h200x1-hosted-1`, profile `serving-h200x1-hosted`, vLLM 0.32.0), dominated by engine initialization.
  - Definition: D-OVERHEAD-WARM (`overhead_vs_production_warm`, formula ID `D-OVERHEAD-WARM`) equals `mean(system gpu_seconds_per_token_prove.session) / mean(production-serving gpu_seconds_per_token_prove.steady, matched load)`, with `pairs` computed per INV-DERIVE-9. The serving baseline uses the matched configuration lengthened under RFC-0015 SRV-1 (`batches_per_session_run`, determined via a sizing capture for single-batch workloads) so its steady window runs at least 60 s. The quantity records the prover's scope (`prove.session`), while the formula identifies serving's scope (`prove.steady`). It is computed only for rows without a steady scope; rows that have a steady scope (such as FlashProve) omit this key entirely.
  - Join rules: reuses INV-DERIVE-2 unchanged against the same matched serving configuration, placement, keys, prompt replay matching, and filters in (f). Null evaluation follows INV-DERIVE-2's order: if the prover's session mean is null, inherit its reason (e.g. failed step); then check join conditions; then if the serving steady mean is null, inherit its reason (e.g. `fewer_than_two_proofs` on a single-batch run). Serving runs under 60 s steady or sizing captures are excluded, yielding `missing_input` if no eligible runs remain.
  - Headline selection: a system row's headline is D-OVERHEAD-S at `prove.steady` (INV-DERIVE-9) unless every successful repetition has `gpu_seconds_per_token_prove.steady` absent or null with `not_externally_observable` or `fewer_than_two_proofs` (INV-SCOPE-2, INV-SCOPE-3), in which case the headline switches to D-OVERHEAD-WARM (carrying its value or null reason). If a steady overhead is null purely for a join reason, D-OVERHEAD-S remains the headline with that reason. The release freeze writes the choice explicitly into `overhead_headline: {metric, formula, scope, serving_scope, start_up}` (RFC-0012): `{overhead_vs_production_prove.steady, D-OVERHEAD-S, prove.steady, prove.steady, excluded}` for D-OVERHEAD-S, or `{overhead_vs_production_warm, D-OVERHEAD-WARM, prove.session, prove.steady, prover_only}` for D-OVERHEAD-WARM. When the headline is non-null, `overhead_conditions` is populated with `warm: true` (indicating serving startup sits outside its scope). The site reads these fields directly without making any selection logic of its own.
  - Display (RFC-0009 S1, S5): every occurrence of a warm overhead identifies both scopes explicitly. Overview cells show `"session vs warm"` beneath the number (mirroring `"steady"` on steady cells), with the full explanation `"proving session (start-up included; it proves one request at a time) vs warm serving (steady)"` in the title and accessible text (amendment of 2026-11-09, research phase). The plate uses that same line for its scope whether the value is present or null, omits redundant scope text in the conditions line and precision note (each fact once per plate, INV-DERIVE-9), explains why the steady figure is null, omits any high-load figure (Q6), and reports batches per session for both sides.
  - Interpretation: because prover startup is included while serving startup is excluded, D-OVERHEAD-WARM is higher than a steady-only overhead for the same prover would be. It reflects the actual cost of running a per-request prover against an already-warm inference server, not the prover's steady-state speed after warmup.

### Worked example (test fixture, not a result)

The numbers below are synthetic round values used strictly as the hand-computed test fixture at `harness/tests/fixtures/derive/worked-example/` (per AGENTS.md: every derived metric ships a test against a hand-computed case). They do not represent any real system.

Inputs: 1 repetition, 1 GPU, `price` 3.60 USD/gpu_hour (fixture value), `active_parameters_per_token` 8.0e9, `weight_bits` 8 (fixture values stored in `run.json` `inputs`). Batch size 1 across 5 batches, giving `requests_count = 5` and `k = 5` proofs (`proofs_count = 5`) of 1,000 tokens each. Timeline in seconds from `commit` start: `commit` runs 0 to 50, `prove` starts at 62.5, and proofs release at 85, 95, 105, 115, and 125. Each proof is 2,000,000 B, and each 8-CPU `verify` call takes 5 s. Production-serving fixtures (amendment of 2026-11-09): a matched-load row on 4 GPUs at 40,000 token/s steady and a high-load row on 4 GPUs at 80,000 token/s steady.

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

Statistics fixture: four repetitions with `rate_prove.steady` values of 100, 110, and 90 token/s plus one failed repetition yield `n = 3`, `n_failed = 1`, mean 100, stdev 10, min 90, and max 110.

Constant-count statistics fixture: three completed repetitions with `tokens_covered_per_proof` equal to 1,000, 1,000, and 1,000 token yield `n = 3`, `n_failed = 0`, mean 1,000, stdev 0, min 1,000, and max 1,000.

Hand-computed unit tests compare values using `math.isclose(rel_tol=1e-12)` since decimal literals like `0.01` cannot be represented exactly in binary64; `iproofs derive --check` on stored JSON runs enforces exact binary64 equality per INV-DERIVE-5.

### Statistics

- Configurations (identified by system, workload ID and version, profile, and image digest) require at least three completed repetitions. Configurations with fewer than three completed repetitions are still published, labelled `"below minimum repetitions"` alongside their `n`, and never hidden.
- Every aggregated metric reports `n` (completed repetitions), `n_failed`, mean, sample standard deviation (using an `n − 1` denominator; null when `n < 2`), min, max, and median ([RFC-0017](0017-requests-tasks-and-tested-states.md) ST-1; absent on statistics frozen prior to 2026-11-10).
- Confidence intervals are omitted at `n = 3` because assuming normality on three samples overstates statistical precision.
- Failed repetitions are tallied in `n_failed`, linked with their failure records (RFC-0010), and excluded from mean, stdev, min, and max.
- The first proof (or first batch when `b > 1`) of a session is excluded from `prove.steady` and included in `prove.session` (§Timing scopes).

### Failure modes

| Failure | Response |
|---|---|
| Time-based quantity omits `scope` | Fails schema validation (RFC-0012); CI rejects the pull request |
| Stored `derived` value disagrees with recomputation | `iproofs derive --check` exits 1; CI blocks merge |
| Adapter `tokens_covered` disagrees with harness count | Job fails at step `prove` with kind `adapter` |
| Honest proof fails verification | Repetition marked failed at step `verify` (INV-TOK-2) |
| Scope timestamps violate ordering (INV-SCOPE-4) | `internal` error, job fails, bug filed |
| Division by zero or null input | Derived value set to null with the catalogue's `null_reason`, never 0 and never omitted |
| Adapter phase timing passed into a derivation | `iproofs derive` raises `internal` (verified by TC-GRADE-2) |

## Alternatives Considered

- **Publishing a single headline rate per system.** Appealing for simplicity, but rejected because SASH's motivating example shows two distinct rates for one run under different scopes; picking one silently hides the scope choice.
- **Adopting upstream scope vocabularies directly.** Considered because SASH and FlashProve already label their scopes, but rejected as the canonical vocabulary because upstream boundaries do not align across systems. Upstream scopes are preserved under `upstream_scope` and mapped explicitly.
- **Normalising across models by FLOPs per second.** Standard in ML benchmarking, but rejected for v0.1 because proving systems perform substantial non-FLOP cryptographic work, FLOP counts depend on kernel and quantization details every team would need to report, and parameter-based normalisers need only published model-card figures.
- **Normalising across models by active parameters alone (D-APT-S).** Needs only the model card, but rejected for cross-model comparisons (2026-11-08) because a 4-bit model and an 8-bit model of identical parameter count would receive equal credit even though the 8-bit model binds twice as many weight bits. D-SPAB-S incorporates weight bits, while D-APT-S stays computed for backwards compatibility without being displayed (INV-DERIVE-3).
- **Normalising proof size by model size (bytes per active weight bit).** Rejected by the project owner on 2026-11-08: succinct proofs scale very weakly with model size, so dividing by model size systematically favours larger models. Proof sizes remain reported in absolute bytes per workload (though D-BPAB was later added on 2026-11-09 specifically for the unified per-Gbit overview columns).
- **Using pooled rate-of-means (total tokens / total seconds) for configuration statistics.** Weights by total work, but rejected because repetitions share identical workload shapes; pooling lets a single slow outlier dominate the denominator, whereas averaging per-repetition rates keeps `n` and `stdev` straightforward to interpret.
- **Using adapter-reported per-batch timestamps for `prove.steady`.** Would allow SASH and batch-flushing provers to report steady numbers, but rejected for v0.1 because it places headline metrics inside the container's trust boundary, violating PRD F9 (external measurement). Retained as a potential future secondary metric (RISK above).
- **Including `setup` inside `whole_wall`.** Considered for completeness, but rejected because setup is a one-time build or model load amortised indefinitely, so including it would make `whole_wall` depend on image warmup state.

## Drawbacks

- `prove.steady` is null for SASH in v0.1, meaning the two initial systems never both report a measured steady rate.
- Amortising commit cost across two fixed horizons (1 and 1,000 requests) will not match every deployment; readers targeting other horizons must recompute from `commit_seconds`.
- D-SPAB-S excludes attention scaling: attention work grows with prompt length while the denominator does not, causing longer-prompt workloads on the same prover and model to appear slower (disclosed via the INV-DERIVE-7 caveat). Where weight bits are nominal (`covers: part`, RFC-0003 WB-1), precision matches only that upstream statement and rows cannot be sorted (after RFC-0003 Q5, this leaves SASH workloads and `l31-8b-c1024` unsorted, so only Maverick rows sort). Computed widths (WB-5) count full storage bits including block scales, making them consistent across GGUF quant mixes but not directly comparable with scale-free integer widths.
- Requiring exact binary64 equality in `--check` ties stored values to exact evaluation order; changing operand order in a formula becomes a breaking methodology change requiring a schema major bump (RFC-0012).

## Migration / Rollout

No results existed when this RFC was revised from its initial 2026-11-03 draft. That revision introduced `setup` and `verify.single_thread`, anchored `whole_wall` at `commit` (excluding `setup`), anchored `prove.steady` to the first-to-last release interval, added INV-TOK-2, and settled commit amortisation by reporting both 1-request and 1,000-request horizons. The metric IDs serve as keys in `run/1` (RFC-0012): adding new metrics is additive, while renaming a metric or changing a formula increments the `run` schema major version without modifying past records.

The 2026-11-07 amendment adds D-TPP (`tokens_covered_per_proof`), displayed on the site as `"One proof covers"` (addressing the RFC-0009 S2 note that it lacked an RFC-0004 grade). It leaves all prior metrics, formulas, and null rules intact and adds the key additively to `run/1`, `iproofs.derive` (`COMPUTE`, `FORMULAS`, `derive_repetition`), `schema/quantity/1.schema.json`, and the worked-example fixture (#320). In the worked-example fixture, `inputs.json` and `run.json` add `proofs_count = 5` (unit count, scope null, grade `measured`, source `run.json#/proofs`), `run.json` adds derived `tokens_covered_per_proof`, and `expected.json` and `README.md` add D-TPP. Earlier runs in `results/v0.1` remain untouched (APP-1, RFC-0009); because they already record `tokens_covered_total` and `proofs_count`, release freeze computes D-TPP on the fly per Q3.

The 2026-11-08 amendment adds D-SPAB-S (`seconds_per_active_weight_bit_token_<S>`, unit `s/bit_token`) following the owner's decision that cross-model prover comparisons use prover time per active weight bit and overhead against plain serving (D-OVERHEAD-S). It formalises keeping D-APT-S computed but undisplayed (INV-DERIVE-3), adds INV-DERIVE-7 and Q4, and leaves all existing metrics unchanged. The key lands additively in `run/1`, `iproofs.derive` (`COMPUTE`, `FORMULAS`, `derive_repetition`, `PROVER_ONLY`), runner input pointers, `schema/quantity/1.schema.json` (unit enum, INV-QTY-3 list, metric-id pattern; RFC-0012), and the worked-example fixture (`inputs.json` adds `weight_bits = 8`, `run.json` adds `inputs` with 8e9 parameters and 8 bits plus the three D-SPAB-S values, D-APT-S points to `run.json#/inputs/active_parameters_per_token`, `expected.json` and `README.md` add D-SPAB, and `workload.yaml` stays for the pre-`inputs` G4 fixture). Companion changes to workload fields, `run.json` `inputs`, and `bit/weight` landed in RFC-0003 and RFC-0012 on the same date. Stored runs in `results/v0.1` remain unchanged (APP-1) and get D-SPAB-S at release freeze via Q3 alongside D-TPP.

The second 2026-11-08 amendment reflects RFC-0003 Q5: INV-DERIVE-7 enables sorting for workloads whose weight width covers all active weights (`file_size` or `computed`) while keeping `covers: part` rows unsorted, and the inputs description adds `computed`. No formula, metric ID, null rule, or stored value changes.

The 2026-11-09 amendment redefines overhead as the prover's GPU-seconds per token on its profile divided by production serving's GPU-seconds per token on its paired serving profile (RFC-0015 SRV-6) in steady scope at matched load (D-OVERHEAD-S), with high load as context (D-OVERHEAD-HIGH-S). It introduces D-GSPT-S, INV-DERIVE-8, and INV-DERIVE-9, and replaces INV-DERIVE-2:
- D-GSPT-S is added to `COMPUTE`, `FORMULAS`, `derive_repetition`, and `FREEZE_FORMULAS` (Q3), allowing older runs without the key to derive it at freeze from `seconds_per_token_<S>` and `profile.gpu.count`.
- New runs compute D-COST-1K-S using `gpus` from `run.json#/inputs/gpu_count` (matching D-GSPT-S) with identical numeric output.
- RFC-0012 adds unit `gpu_s/token`, and the quantity schema adds `gpu_seconds_per_token_<S>`, `overhead_vs_production_<S>`, and `overhead_vs_production_high_<S>` while removing `overhead_vs_serving_<S>` (the previous single-profile rate ratio; no frozen release under `releases/` at `14e9d34` used it).
- The worked example adds D-GSPT and D-OVERHEAD-HIGH and restates D-OVERHEAD in GPU-seconds (expected value remains 100).
- The glossary's "Overhead" entry is updated accordingly.

A subsequent 2026-11-09 amendment adds INV-DERIVE-10 (every prover receives an overhead ratio) and optional `overhead_headline` in `release-index/1` (RFC-0012), removing the short-lived `D-OVERHEAD-SESSION` and `whole_wall` overhead entries that existed only in unreleased index drafts.

Another 2026-11-09 amendment adds INV-DERIVE-11 (warm overhead against already-running production servers). `D-OVERHEAD-WARM` (`overhead_vs_production_warm`) joins `iproofs.derive.FORMULAS` and `overhead(warm=True)` as the headline for provers lacking a steady scope. Because no release was frozen yet, RFC-0012 updates cleanly: the quantity pattern adds `overhead_vs_production_warm`; `release-index/1` `overhead_headline` adds required `serving_scope` (`prove.steady`), replaces `D-OVERHEAD-SESSION` / `overhead_vs_production_prove.session` with `D-OVERHEAD-WARM` / `overhead_vs_production_warm`, and changes `start_up` from `included` to `prover_only`; `overhead_conditions.warm` indicates serving startup lies outside its scope; `manifest/1` adds `workload.sizing_capture` (RFC-0015 SRV-1) excluded by INV-DERIVE-2 (f). Site rendering (`iproofs.site.view`, `web/draw`) prints both scopes for warm figures, leaving steady-scope systems unchanged apart from `serving_scope`.

Another 2026-11-09 amendment adds INV-SCOPE-5 (batch-membership steady scope). At `b = 1`, behaviour is unchanged. At `b > 1`, steady start shifts from `r_1` to the last release of the first batch and drops the entire first batch from steady tokens, eliminating overcounting of the remaining `b − 1` requests in batch 0. `iproofs.derive.scope_seconds` and `tokens_metrics` accept batch size, per-release `request_index`, and release timestamps (TC-STEADY-BATCH), excluding any later-batch request released prior to steady start. Manifests record `workload.steady_rule`; releases annotate earlier `b > 1` runs with `steady_boundary` and exclude them from overheads, leaving stored runs untouched (APP-1).

Another 2026-11-09 amendment adds D-BPAB (`proof_bytes_per_active_weight_bit_token`, unit `B/bit_token`) and D-VSPAB (`verify_seconds_per_active_weight_bit_token`, unit `s/bit_token` at `verify`) per the owner's decision so all three overview cost columns share the same normalisation (per token covered per bit of active weights). Because D-BPT and D-VSPT already divide by tokens covered, D-BPAB equals `mean proof bytes / tokens covered per proof / (active parameters × weight bits)`, and D-VSPAB does the same for verify seconds. Both join `COMPUTE`, `FORMULAS`, `derive_repetition`, `PROVER_ONLY`, and `FREEZE_FORMULAS` (Q3), letting release freeze populate `freeze_derived` from stored `v0.1` runs without altering `run.json` (APP-1). `schema/quantity/1.schema.json` adds the new unit and metric-id patterns, and the INV-DERIVE-7 attention caveat applies to both.

The 2026-11-10 amendment is [RFC-0017](0017-requests-tasks-and-tested-states.md), adding per-request metrics D-TPR, D-GSPR-S, D-COST-REQ-S, D-BPR, and D-VSPR (units `token/request`, `gpu_s/request`, `USD/request`, `B/request`, `s/request`) to `FREEZE_FORMULAS` (Q3) and adding `stats.median` to every statistic (ST-1), without changing existing formulas, null rules, or stored values (statistic `value` remains the mean).

## Testing Strategy

Unit tests in `harness/tests/unit/`, located in `test_derive.py` unless specified otherwise:

- TC-OVERHEAD-WARM (`test_cross_rows.py`, `test_site_view.py`, INV-DERIVE-11, hand-computed fixture): prover session 0.5 gpu_s/token (544 s for 1,088 tokens on 1 GPU) divided by warm serving steady 0.0005 gpu_s/token (0.544 s per 1,088-token request on 1 GPU) yields 1,000 under `D-OVERHEAD-WARM`, scope `prove.session`, pairs 1,000 to 1,000 over 1 × 1. Verifies the SASH-like row (D-OVERHEAD-S null `not_externally_observable`, headline D-OVERHEAD-WARM 1,000 with `prove.session`, serving `prove.steady`, `start_up: prover_only`, warm conditions, inputs `gpu_seconds_per_token_prove.session` and `gpu_seconds_per_token_prove.steady`), leaves the FlashProve-like row unchanged (headline D-OVERHEAD-S, no `overhead_vs_production_warm`), tests all null branches (no serving run -> `missing_input` keeping warm headline without conditions; single-batch serving -> `fewer_than_two_proofs`; under-60 s steady or sizing capture -> `missing_input`; failed prover session -> `step_failed`), and checks display text prints both scopes and omits high-load context.
- TC-DERIVE-WORKED: verifies every row of the worked example within `rel_tol=1e-12`.
- TC-STAT-FAILED (`test_stats.py`): verifies the statistics fixture yields `n = 3`, `n_failed = 1`, mean 100, stdev 10, min 90, max 110.
- TC-STAT-N1 (`test_stats.py`): verifies a single successful repetition yields `stdev = null` and `mean` equal to the sample value.
- TC-STEADY-K1 (`test_scopes.py`): confirms `k = 1` sets `prove_steady_seconds` and `rate_prove.steady` to null (`fewer_than_two_proofs`) while keeping session and whole-wall metrics populated.
- TC-STEADY-UNOBSERVABLE: confirms releasing all proofs in a single watcher poll yields null steady metrics (`not_externally_observable`).
- TC-HONEST-REJECT (`test_tokens.py`): confirms a single rejected honest proof fails the repetition at `verify` and emits no rates.
- TC-NULL-DIV: confirms zero tokens makes all rates and `tokens_covered_per_proof` null with a `null_reason`, never 0. For D-SPAB-S (`test_null_div_active_weight_bits`), confirms zero parameter count or zero weight bits (reachable during G4 recomputation of edited inputs) produces null `not_applicable` rather than infinity.
- TC-GSPT-WORKED: verifies both D-GSPT rows of the worked example.
- TC-OVERHEAD-GSPT (`test_cross_rows.py`): verifies both overhead rows and hand-computed `pairs` across three prover and three serving repetitions.
- TC-OVERHEAD-PAIR-PROFILE (`test_cross_rows.py`): confirms H100 prover vs H200 serving and hosted vs docker both yield `not_applicable`.
- TC-OVERHEAD-FEWEST (`test_cross_rows.py`): with TP4 having one valid paired run plus two `resource` failures and TP8 having three successes, confirms TP4 is selected as the smallest joinable GPU count.
- TC-OVERHEAD-PROMPTS (`test_cross_rows.py`): confirms serving runs replaying a different system's prompts are excluded, yielding `missing_input` if none match.
- TC-OVERHEAD-SASH (`test_cross_rows.py`): confirms prover steady null `not_externally_observable` propagates cleanly.
- TC-OVERHEAD-RULE (`test_cross_rows.py`): confirms serving runs at `b > 1` missing `steady_rule` yield `missing_input`, while prover runs missing it yield `not_applicable`.
- TC-OVERHEAD-DIGEST (`test_cross_rows.py`): confirms mismatched serving model or engine image digests yield `not_applicable`, whereas a bumped serving record version with identical model digest joins cleanly.
- TC-GSPT-FREEZE (`test_freeze.py`): confirms older stored runs lacking D-GSPT-S derive it from `gpu.count` at freeze.
- TC-GSPT-X4 (`test_runner.py`): confirms a fake 4-GPU serving job records `inputs.gpu_count = 4`, computes `D-GSPT = D-SPT × 4`, shares the pointer with D-COST-1K, and rejects profiles with missing or zero GPU counts with `config`.
- TC-GRADE-2: confirms passing an adapter-reported phase into derivation raises `internal`.
- TC-STEADY-BATCH (`test_scopes.py`, `test_tokens.py`): tests `b = 24`, 5 batches, 120 releases (steady tokens = `96 × 1,024`, steady start = last release among `request_index` 0..23); `b = 24, k = 24` -> `fewer_than_two_proofs`; interleaved release order (swapping requests 23 and 30 drops requests 24..30 released before steady start, giving `89 × 1,024` tokens and warning count 7); batch 0 finishing after all later batches -> `fewer_than_two_proofs`; proof missing `request_index` at `b = 24` -> `missing_input`.
- TC-SCOPE-ORDER (`test_scopes.py`): confirms synthetic timeline with `r_1` before `prove` start raises `internal`.
- TC-TPP-WORKED (`test_tokens_covered_per_proof_worked_example`): confirms worked-example D-TPP (`5,000 / 5 = 1,000` token within `rel_tol=1e-12`, grade `derived`, unit `token`, scope null).
- TC-TPP-ZERO (`test_tokens_covered_per_proof_zero_is_null`): confirms `proofs_count = 0` or `tokens_covered_total = 0` with `proofs_count = 5` both yield null `not_applicable`, never 0.
- TC-TPP-REFERENCE (`test_tokens_covered_per_proof_reference_is_null`): confirms a `kind: reference` repetition (`proofs_count = 1`, `tokens_covered_total = 4,608` token, fixture values) yields null `not_applicable`.
- TC-TPP-SOURCE (`test_tokens_covered_per_proof_source`): confirms `source.ref` is `derive:D-TPP@<harness version>` with `source.inputs` ordered `[tokens_covered_total, proofs_count]` (INV-DERIVE-4).
- TC-TPP-STAT (`test_stats.py::test_tokens_covered_per_proof_constant_statistics`): verifies the constant-count fixture (`n = 3`, `n_failed = 0`, mean 1,000, stdev 0, min 1,000, max 1,000).
- TC-BPAB-WORKED, TC-VSPAB-WORKED (`test_per_bit_proof_size_and_check_time_flashprove_like`, `test_per_bit_proof_size_and_check_time_sash_like`, `test_per_bit_proof_size_and_check_time_nulls`): verifies two hand-computed cases (120 proofs × 1,024 positions at `17e9 × 4` bits -> `2.5e-7 B/bit_token` and `2.5e-13 s/bit_token`; 1 proof × 1,088 positions at `8e9 × 8` bits -> `6.25e-4 B/bit_token` and `5e-11 s/bit_token`), units, scopes, input order, null rules, and worked-example D-BPAB and D-VSPAB rows.
- TC-SPAB-WORKED (`test_seconds_per_active_weight_bit_worked_example`): verifies `0.01 / (8.0e9 × 8) = 1.5625e-13 s/bit_token` within `rel_tol=1e-12`, grade `derived`, unit `s/bit_token`, scope `prove.steady`, tier `reported`.
- TC-SPAB-SOURCE (`test_seconds_per_active_weight_bit_source`): verifies `source.ref` is `derive:D-SPAB-S@<harness version>` and `source.inputs` orders `[seconds_per_token_<S>, active_parameters_per_token, weight_bits]`.
- TC-SPAB-NO-BITS (`test_seconds_per_active_weight_bit_no_bits_is_missing_input`, `test_seconds_per_active_weight_bit_recorded_null_bits`): confirms omitted or null `inputs.weight_bits` yields null `missing_input` across all three scopes while preserving D-SPT-S.
- TC-SPAB-REFERENCE (`test_seconds_per_active_weight_bit_reference_is_null`): confirms `kind: reference` yields null `not_applicable`.
- TC-SPAB-NULL (`test_seconds_per_active_weight_bit_follows_steady_null`): confirms `k = 1` propagates `fewer_than_two_proofs` from D-SPT-prove.steady.
- TC-SPAB-CHECK (`test_derive_check.py`): confirms reference runs recompute as null `not_applicable`, and an unresolvable weight-bits pointer preserves stored null `missing_input` while failing a stored numeric value with DER-3.
- TC-SPAB-CORRECTION (`test_runner.py::test_g4_survives_a_weight_bits_correction`): confirms changing a workload file's weight bits from 8 to 4 leaves G4 clean on an existing fake run that recorded `inputs.weight_bits = 8` (RFC-0003 WB-4).
- TC-Q3-FREEZE (`test_freeze.py`): `test_freeze_evaluates_a_stored_run_without_the_key` (pairs a legacy run lacking D-TPP/D-SPAB-S with a newer run, confirming `n = 2`, freeze output in `freeze_derived`, D-STAT pointing there, and hand-computed fake-workload D-SPAB-prove.steady `0.01 / (64 × 8) s/bit_token`), `test_freeze_value_of_another_workload_version_is_missing_input`, `test_freeze_stops_on_different_workload_inputs` (RFC-0003 WB-4), and `test_derive.py::test_freeze_values_fill_only_missing_keys`.

TC-DERIVE-WORKED covers both the D-TPP and D-SPAB worked-example rows.

Property tests (Hypothesis) in `harness/tests/property/` (in the named file where applicable):

- P-RATE-INVERSE: for any positive finite token count and duration, `rate × seconds_per_token` lies within 4 ulp of 1.
- P-DERIVE-IDEMPOTENT: `derive(derive(run))` matches `derive(run)` byte for byte after serialization.
- P-STAT-BOUNDS (`test_stat_property.py`): `min <= mean <= max` for any non-empty finite sample.
- P-CHECK-DETECTS (`harness/tests/unit/test_derive_check.py`): perturbing any stored derived value by 1 ulp causes `derive --check` to fail.

Schema tests (RFC-0012): invalid examples covering a time unit with null scope (including `s/bit_token`), an `external` quantity omitting `upstream_scope`, and a `derived` quantity omitting a formula ID, alongside a valid D-SPAB-S quantity.

## Decisions

- Q1. Per-request latency percentiles are omitted because v0.1 workloads use fixed batch schedules with no arrival process.
- Q2. SASH has no segment-granular steady scope: `prove.steady` stays null and its upstream `loop` figure appears as `external` with mapping `approximate`. Because the 2026-11-09 amendment defines D-OVERHEAD-S at steady scope, every SASH workload has null D-OVERHEAD-S (`not_externally_observable`), since `systems/sash/system.yaml` declares `incremental_proofs: false` and running more sequences would not make single-proof releases observable at the pin. SASH rows display D-OVERHEAD-WARM instead, comparing its proving session against warm production serving (INV-DERIVE-11).
- Q3. Runs recorded before a formula existed keep their original `run.json` untouched (APP-1). During release freeze, `iproofs.release` evaluates missing `FREEZE_FORMULAS` (D-TPP, D-SPAB-S, and subsequent freeze formulas) from each run's stored inputs (for D-TPP, `tokens_covered_total` and `proofs_count`; for D-SPAB-S, `seconds_per_token_<S>` plus the release commit's workload parameter count and weight bits, returning null `missing_input` if the workload version has changed). D-STAT for D-TPP MUST include every successful repetition of the configuration: either every older run receives a freeze-time value or freeze halts with an error naming the run (no run silently drops out of `n`). Freeze stores these evaluated quantities in `releases/<release>/index.json` under `freeze_derived` (keyed by run ID then metric ID; optional in `release-index/1`, RFC-0012) and points configuration D-STAT inputs at `index.json#/freeze_derived/<run id>/<metric>`. Because `run.json` is untouched, `iproofs derive <run-dir> --check` does not inspect `freeze_derived`, while RFC-0013 G4 validates release index aggregates (`DER-1` on mismatch, `DER-3` on missing input; pending implementation in G4 code). Any freeze formula whose required `run.json` input is absent yields null `missing_input` rather than recomputing intermediates. Implemented via `derive.freeze_values` (`FREEZE_FORMULAS = D-TPP, D-SPAB-S`).
- Q4. D-SPAB-S normalises by active weight bits rather than multiply-accumulates (MACs). A MAC denominator (active weights plus attention at `prompt_tokens`) would capture prompt-length scaling (addressing INV-DERIVE-7's caveat), but requires layer, head, and head-dimension figures from a pinned config (absent from Maverick workloads) and discards weight bit-width, treating 4-bit and 8-bit models identically.
- Q5. Both steady-only serving filters in INV-DERIVE-2 (f) (the 60 s steady minimum in RFC-0015 SRV-1 and `steady_rule` at `b > 1` in INV-SCOPE-5) apply equally to session-based overhead calculations so both figures divide by the same serving runs. In the overview's overhead column, a warm figure (INV-DERIVE-11) sorts alongside steady figures when two systems share a workload table with different headlines (RFC-0009 S6); each cell displays its scope explicitly, noting that warm figures include prover startup and are therefore higher than steady-only overheads would be.
- Q6. Warm headlines carry no high-load context figure: D-OVERHEAD-HIGH-WARM is not computed and no high-load value appears alongside a warm headline, while D-OVERHEAD-HIGH-S remains computed for steady scopes.

## References

- docs/PRD.md §1, §4 (G2), §7 (F3, F9, F10).
- [RFC-0003](0003-workloads.md) for shapes, `active_parameters_per_token` and weight bits; [RFC-0005](0005-adapter-contract.md) for proof directories and `tokens_covered`; [RFC-0006](0006-reference-hardware-and-cost.md) for `price`; [RFC-0007](0007-evidence-tiers-and-reproduction.md) for tiers; [RFC-0009](0009-results-and-publication.md) for the site that prints D-TPP; [RFC-0011](0011-measurement-and-sampling.md) for how each recorded metric is measured; [RFC-0012](0012-schemas-and-serialization.md) for the quantity schema; [RFC-0013](0013-validation-and-ci.md) for the CI gates; [RFC-0015](0015-reference-rows.md) for reference rows.
- SASH results: `sg-ai-safety-hub/zk-inference-results` at `11decec3c0b62c707618aab5deb82750b355d202` (`constants.json`).
- FlashProve: `anthropics/FlashProve` at `9e2bdd8ff5bf9c62f18263d7dac189b0400b260c` (`docs/figures.tsv`).
