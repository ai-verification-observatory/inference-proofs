# RFC-0004: Metrics, timing scopes and grades

- Status: Draft
- Authors: AbdelStark
- Created: 2026-11-03
- Target milestone: v0.1-alpha
- Requires: RFC-0003, RFC-0012
- Supersedes: none
- Discussion: pull request that introduces it

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

- Latency percentiles per request and queueing metrics (no batch or queueing workload exists in v0.1; see Open Questions).
- FLOP-based normalisers (rejected, see Alternatives Considered).
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
| `asserted` | an input that is not measured (for example a price), with source and date | `reference_file` |

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
| `prove.steady` | release time of the first proof r_1 | release time of the last proof r_k | proofs 2..k |
| `whole_wall` | `commit` call start | release time of the last proof r_k | all proofs 1..k |
| `verify` | `verify` call start for one proof, 8-CPU verifier container | that call's exit | the proof's tokens |
| `verify.single_thread` | same, 1-CPU verifier container | that call's exit | the proof's tokens |
| `primitive` | adapter-reported only | adapter-reported only | adapter-declared |

Boundary rules:

- Model download and image pull are never inside any scope. `setup` is excluded from `whole_wall`: setup is a one-off build or load that the workload does not repeat per request; the commitment is per-run work (each v0.1 FlashProve run commits fresh, `-M 1`) and is included.
- INV-SCOPE-2: `prove.steady` requires k >= 2. With k < 2 its seconds and rate are `null` with `null_reason: fewer_than_two_proofs`.
- INV-SCOPE-3: if the release watcher reports `observable: false` (the system declares `incremental_proofs: false`, or all proofs appeared within one observation, RFC-0011 §Proof release watcher), `prove.steady` is `null` with `null_reason: not_externally_observable`, and `prove.session` and `whole_wall` are still reported, because their end event is still the last release.
- INV-SCOPE-4: for any successful job, `commit` start <= `prove` start <= r_1 <= r_k. A violation is an `internal` error (RFC-0010).
- Container start-up overhead is inside each call's time and is not subtracted. The `info` call's wall time is recorded as `info_seconds` so a reader can see the order of magnitude.

RISK: an upstream that writes every proof only at process exit makes `prove.steady` unobservable from outside. Resolution: the adapter README states whether upstream emits proofs incrementally at the pin; if it does not, the row shows `prove.steady` as null with the reason, and the upstream steady figure appears only as `external`. A later RFC MAY admit adapter-reported per-batch timestamps as a labelled secondary steady figure once a system needs it.

RISK: SASH proves one sequence as a grid of segments, and one proof in this benchmark's sense is the whole set of segment proofs for a sequence plus the passing grid check (RFC-0005). With one sequence per job (RFC-0003), k = 1, so `prove.steady` is null by INV-SCOPE-2 and SASH's `loop` figure is shown only as `external` with mapping `approximate`. Resolution plan: if SASH maintainers want a measured steady figure, a follow-up RFC defines a part-granular steady scope with its own token attribution rule; until then no token count is apportioned to individual segments.

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
| `prove_steady_seconds` | s | `prove.steady` | r_k minus r_1 |
| `whole_wall_seconds` | s | `whole_wall` | r_k minus `commit` call start |
| `prove_call_seconds` | s | `prove.session` | wall time of the whole `prove` call (may exceed `prove_session_seconds` by process teardown) |
| `proofs_count` | count | null | k, proofs released |
| `requests_count` | count | null | requests in the job (`batch_size × batches_per_session`) |
| `tokens_covered_total` | token | null | sum over proofs 1..k |
| `tokens_covered_prompt` | token | null | prompt part of the above |
| `tokens_covered_output` | token | null | output part of the above |
| `tokens_covered_steady` | token | null | sum over proofs 2..k |
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

Inputs named `metrics.X` are recorded metrics of the same repetition. `ref.*` inputs come from the matching reference-system configuration (RFC-0015). `price` is `cost.price_per_gpu_hour_usd` from `reference/<release>.yaml` (asserted, RFC-0006). `gpus` is the profile's GPU count. `S` ranges over the rate scopes {`prove.steady`, `prove.session`, `whole_wall`}; `T(S)` is `tokens_covered_steady` for `prove.steady` and `tokens_covered_total` otherwise; `sec(S)` is the matching seconds metric.

| Formula id | Metric id | Level | Formula | Unit | Scope | Null when |
|---|---|---|---|---|---|---|
| D-RATE-S | `rate_<S>` | repetition | T(S) / sec(S) | token/s | S | sec(S) null or 0; T(S) = 0 |
| D-SPT-S | `seconds_per_token_<S>` | repetition | sec(S) / T(S) | s/token | S | as D-RATE-S |
| D-COST-1K-S | `cost_per_1k_tokens_<S>` | repetition | D-SPT-S × 1000 × gpus × price / 3600 | USD/1k_token | S | D-SPT-S null; price null |
| D-COMMIT-AMORT-H1 | `commit_seconds_per_token_h1` | repetition | `commit_seconds` / (tokens_covered_total / requests_count × 1) | s/token | `commit` | commit failed |
| D-COMMIT-AMORT-H1000 | `commit_seconds_per_token_h1000` | repetition | `commit_seconds` / (tokens_covered_total / requests_count × 1000) | s/token | `commit` | as above |
| D-APT-S | `active_param_tokens_per_second_<S>` | repetition | D-RATE-S × `active_parameters_per_token` | param_token/s | S | D-RATE-S null; parameter count missing (`missing_input`) |
| D-BPT | `proof_bytes_per_token` | repetition | `proof_bytes_total` / tokens_covered_total | B/token | null | tokens 0 |
| D-VSPT | `verify_seconds_per_token` | repetition | `verify_seconds_total` / tokens_covered_total | s/token | `verify` | tokens 0 |
| D-VSPT-1T | `verify_single_thread_seconds_per_token` | repetition | single-thread verify seconds of the first proof / tokens covered by the first proof (single-thread verify runs on the first proof only, RFC-0010) | s/token | `verify.single_thread` | as D-VSPT |
| D-TPP | `tokens_covered_per_proof` | repetition | `tokens_covered_total` / `proofs_count` | token | null | tokens 0 or `proofs_count` 0 (`not_applicable`); always null with `not_applicable` for `kind: reference` (INV-DERIVE-6) |
| D-VERIFY-HOST | `verify_host_ratio` | configuration | mean `verify` seconds on a separate verifier host / mean `verify` seconds on the emulated verifier profile, same proofs | ratio | `verify` | null with `missing_input` unless both host kinds ran the same proofs (RFC-0006 verifier emulation check) |
| D-STAT | any of the above, configuration level | configuration | statistics over successful repetitions (§Statistics) | as input | as input | n = 0 |
| D-OVERHEAD-S | `overhead_vs_serving_<S>` | release | mean(ref-serve `rate_<S>`) / mean(system `rate_<S>`) | ratio | S | either mean null; ref-serve row `not_measurable_on_profile` |
| D-AGREE | `agreement_rate` | release | agreement positions / (agreement + disagreement positions), RFC-0015 RC-5 | ratio | null | no compared positions; recompute row `not_measurable_on_profile` |
| D-PROVIDER-SPREAD | `provider_spread_<S>` | release | max over providers of configuration mean `rate_<S>` / min over providers of the same (RFC-0006 R4) | ratio | S | fewer than two providers (`not_applicable`) |
| P-CAMPAIGN | `campaign_gpu_seconds` | release plan | projection from `external` inputs (docs/spec/08-performance-budget.md); grade `projected`, never published as a result | s | `whole_wall` | any input missing (`missing_input`) |

Rules:

- INV-DERIVE-1: a configuration-level statistic is computed from per-repetition derived values (mean of rates), never from pooled sums (rate of means). This keeps a long repetition from dominating.
- INV-DERIVE-2: D-OVERHEAD-S is computed only when the reference row matches the system row on workload id, workload version, profile, phase and batch size (RFC-0015). Otherwise it is null with `null_reason: not_applicable`.
- INV-DERIVE-3: `active_parameters_per_token` comes from the workload record (RFC-0003), as an `asserted` quantity whose source is the model's own documentation: all parameters for a dense model, the parameters used per token for a mixture of experts. D-APT-S is a rough normaliser across model sizes and MUST be displayed only together with the claim cards, never alone.
- INV-DERIVE-4: every derived quantity's `source` is `{kind: derivation, ref: derive:<formula id>@<harness version>, inputs: [<JSON pointers>]}` (RFC-0012) and its tier is the lowest tier among its inputs (in `run.json` always `reported`).
- INV-DERIVE-5: arithmetic is IEEE 754 binary64 in a fixed order: the formula is evaluated left to right as written in the table, sums use `math.fsum`, statistics use `statistics.mean` and `statistics.stdev`. Values are stored unrounded. `iproofs derive --check` recomputes and requires `==` equality with the stored value; any difference fails CI (RFC-0013).
- INV-DERIVE-6: D-TPP is the number of positions one proof binds (INV-TOK-1), averaged over the repetition's proofs. It is a count, not a time or a rate, so it has no timing scope (INV-SCOPE-1 does not apply) and MUST NOT be displayed as a throughput. Its grade is `derived` and its tier follows INV-DERIVE-4 (`reported` in `run.json`). For the coverage kinds `window` and `prompt_plus_output` every proof of a repetition covers the same count c, so the value is exactly c (k × c / k is exact in binary64 when the total k × c is below 2^53); for `declared_per_proof` it is the mean of the adapter's per-proof counts. A reference system (`kind: reference`, RFC-0015) proves nothing: its releases are outputs, not proofs (REF-2), so its `tokens_covered_per_proof` is null with `null_reason: not_applicable` whatever its `tokens_covered_total` (REF-3) and `proofs_count`. Its configuration-level value is D-STAT over every successful repetition (§Statistics), with n, n_failed, mean, stdev, min and max like every repetition-level metric; for a constant count at n >= 2, stdev is 0 and min equals max. The public site prints it as "One proof covers" (RFC-0009).

### Worked example (test fixture, not a result)

The following inputs are invented round numbers used only as the hand-computed fixture `harness/tests/fixtures/derive/worked-example/` (AGENTS.md: every derived metric ships a test against a hand-computed case). They describe no system.

Inputs: one repetition, 1 GPU, `price` 3.60 USD/gpu_hour (fixture value), `active_parameters_per_token` 8.0e9. Batch 1, 5 batches, so `requests_count` 5 and k = 5 proofs (`proofs_count` 5) of 1,000 tokens each. Clock (seconds from `commit` start): `commit` runs 0 to 50, `prove` starts at 62.5, proofs release at 85, 95, 105, 115, 125. Each proof is 2,000,000 B; each 8-CPU verify takes 5 s. Reference row fixture: `rate_prove.steady` of ref-serve 10,000 token/s.

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
| D-BPT | 10,000,000 / 5,000 | 2,000 B/token |
| D-VSPT | 25 / 5,000 | 0.005 s/token |
| D-TPP | 5,000 / 5 | 1,000 token |
| D-OVERHEAD-prove.steady | 10,000 / 100 | 100 ratio |

Statistics fixture: four repetitions with `rate_prove.steady` 100, 110, 90 token/s and one failed repetition. Expected: n 3, n_failed 1, mean 100, stdev 10, min 90, max 110.

Constant-count statistics fixture: three repetitions with `tokens_covered_per_proof` 1,000, 1,000, 1,000 token and none failed. Expected: n 3, n_failed 0, mean 1,000, stdev 0, min 1,000, max 1,000.

Hand-computed tests compare with `math.isclose(rel_tol=1e-12)`, because a decimal written in this table (for example 0.01) has no exact binary64 form; `--check` on stored runs uses exact equality per INV-DERIVE-5.

### Statistics

- At least three repetitions per configuration (a configuration is system, workload id and version, profile, image digest). A configuration with fewer than three successful repetitions is published with its n and the label "below minimum repetitions"; it is never hidden.
- Reported per metric: n (successful repetitions), n_failed, mean, sample standard deviation (n − 1 denominator; null when n < 2), min, max.
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
- **Rate of means (pooled tokens over pooled seconds) for configuration statistics.** Considered because it weights by work. Rejected: repetitions have equal shapes, so pooling adds nothing but lets one slow repetition dominate the denominator; mean of per-repetition rates keeps n and stdev interpretable.
- **Adapter-reported per-batch timestamps for `prove.steady`.** Considered because it would give SASH and end-of-run writers a steady figure. Rejected for v0.1: it makes the headline depend on code inside the container, against PRD F9 (measure externally). Kept as a possible later secondary figure (RISK above).
- **Include `setup` in `whole_wall`.** Considered for completeness. Rejected: setup is a one-off build or load amortised over all requests forever; including it would make `whole_wall` depend on whether the image was warm.

## Drawbacks

- `prove.steady` is null for SASH in v0.1, so the two v0.1 systems never both have a measured steady figure.
- Amortised commit cost at two fixed horizons (1 and 1,000 requests) does not fit every deployment; readers with other horizons must recompute.
- Exact float equality in `--check` couples stored values to the evaluation order; changing a formula's operand order is a methodology change and needs a version bump of the derivation (RFC-0012 schema major).

## Conflicts of Interest

The author's affiliations and any interest in a measured system are declared in `MAINTAINERS.md` before this RFC enters Last call (RFC-0001).

## Migration / Rollout

No results existed when this RFC revised the draft of 2026-11-03. The revision adds `setup` and `verify.single_thread` scopes, fixes `whole_wall` to start at `commit` (setup excluded), fixes `prove.steady` to the first-to-last release interval, adds INV-TOK-2, and resolves the amortisation horizon question (both 1 and 1,000 requests are reported). The metric ids above are keys of `run/1` (RFC-0012). Adding a metric is additive; renaming one or changing a formula bumps `run` to a new major and relabels nothing in place: past runs keep the formula version they were produced under (RFC-0001 §Changes to methodology).

The amendment of 2026-11-07 adds D-TPP (`tokens_covered_per_proof`), the figure the public site prints as "One proof covers", whose current wording RFC-0009 S2 lists as naming no RFC-0004 grade. It changes no existing metric, formula or null rule. The new key is additive to `run/1`: `iproofs.derive` (`COMPUTE`, `FORMULAS`, `derive_repetition`), the metric-id pattern of `schema/quantity/1.schema.json` and the worked-example fixture gain it with the code (#320). In the fixture, `inputs.json` and `run.json` gain the recorded input `proofs_count` 5 (unit count, scope null, grade `measured`, source `run.json#/proofs`, as the runner records it), `run.json` gains the derived `tokens_covered_per_proof`, and `expected.json` and `README.md` gain the D-TPP row. Stored v0.1 runs exist (`results/v0.1`); they were made before that code, carry no `tokens_covered_per_proof` key and are not changed (APP-1, RFC-0009). They keep `tokens_covered_total` and `proofs_count`, so the value stays recomputable from recorded numbers; Q3 sets how a release gets it.

## Testing Strategy

Unit tests in `harness/tests/unit/`, in `test_derive.py` unless an entry names another file:

- TC-DERIVE-WORKED: the worked example above, every row, within `rel_tol=1e-12`.
- TC-STAT-FAILED (`test_stats.py`): the statistics fixture; asserts n 3, n_failed 1, mean 100, stdev 10, min 90, max 110.
- TC-STAT-N1 (`test_stats.py`): one successful repetition; stdev null, mean equals the value.
- TC-STEADY-K1 (`test_scopes.py`): k = 1; `prove_steady_seconds` and `rate_prove.steady` null with `fewer_than_two_proofs`; session and whole wall present.
- TC-STEADY-UNOBSERVABLE: all proofs released in one watcher observation; steady null with `not_externally_observable`.
- TC-HONEST-REJECT (`test_tokens.py`): one honest proof rejected; repetition failed at `verify`; no rates emitted.
- TC-NULL-DIV: zero tokens; every rate, and `tokens_covered_per_proof`, null with a reason, none equal to 0.
- TC-OVERHEAD-MISMATCH (`test_cross_rows.py`): reference row with a different batch size; D-OVERHEAD null with `not_applicable`.
- TC-GRADE-2: an adapter-reported phase passed as a derivation input raises `internal`.
- TC-SCOPE-ORDER (`test_scopes.py`): synthetic timeline with r_1 before `prove` start raises `internal`.
- TC-TPP-WORKED (`test_tokens_covered_per_proof_worked_example`): the worked example's D-TPP row, 5,000 / 5 = 1,000 token within `rel_tol=1e-12`, with grade `derived`, unit `token` and scope null.
- TC-TPP-ZERO (`test_tokens_covered_per_proof_zero_is_null`): `proofs_count` 0, and separately `tokens_covered_total` 0 with `proofs_count` 5, each give a null value with `null_reason: not_applicable`, never 0.
- TC-TPP-REFERENCE (`test_tokens_covered_per_proof_reference_is_null`): a `kind: reference` repetition with `proofs_count` 1 and `tokens_covered_total` 4,608 token (fixture values, not a result) gives a null value with `null_reason: not_applicable`.
- TC-TPP-SOURCE (`test_tokens_covered_per_proof_source`): `source.ref` is `derive:D-TPP@<harness version>` and `source.inputs` points at `tokens_covered_total` then `proofs_count`, in that order (INV-DERIVE-4).
- TC-TPP-STAT (`test_stats.py::test_tokens_covered_per_proof_constant_statistics`): the constant-count statistics fixture; asserts n 3, n_failed 0, mean 1,000, stdev 0, min 1,000, max 1,000.

The D-TPP tests land with the code in #320. TC-DERIVE-WORKED covers the D-TPP row once `expected.json` holds it.

Property tests (hypothesis) under `harness/tests/property/`, in the file an entry names where one exists:

- P-RATE-INVERSE: for positive finite tokens and seconds, `rate × seconds_per_token` is within 4 ulp of 1.
- P-DERIVE-IDEMPOTENT: `derive(derive(run))` equals `derive(run)` byte for byte after serialisation.
- P-STAT-BOUNDS (`test_stat_property.py`): min <= mean <= max for any non-empty list of finite values.
- P-CHECK-DETECTS (`harness/tests/unit/test_derive_check.py`): perturbing any stored derived value by one ulp makes `derive --check` fail.

Schema tests (RFC-0012): invalid examples for a time unit with null scope, an `external` quantity without `upstream_scope`, a `derived` quantity without a formula id.

## Open Questions

- OPEN QUESTION Q1 (owner: AbdelStark, resolve by: 2027-03-31 or a follow-up RFC): should per-request latency percentiles be recorded once batch and queueing workloads exist? Default until resolved: not recorded; v0.1 workloads have fixed batches and no arrival process.
- OPEN QUESTION Q2 (owner: AbdelStark, resolve by: 2027-01-31): does SASH's maintainer team want a part-granular steady scope? Default until resolved: SASH `prove.steady` is null and its `loop` figure is shown as `external`, mapping approximate.
- OPEN QUESTION Q3 (owner: 0xchqrles, resolve by: Last call of this RFC, RFC-0001): how does a release get D-TPP for a run stored before the formula existed, given that APP-1 forbids rewriting its `run.json`? Default until resolved: the release freeze evaluates D-TPP for each such successful repetition from that run's recorded `tokens_covered_total` and `proofs_count`, with `source.inputs` pointing into the unchanged `run.json`, and D-STAT runs over those values. D-STAT for D-TPP MUST cover every successful repetition of the configuration: a run without the key gets the freeze-time value, or the freeze stops with an error naming the run; it never drops out of n. The freeze writes those values and their D-STAT to `releases/<release>/index.json` (RFC-0009), not to `run.json`, so `iproofs derive <run-dir> --check` does not see them; RFC-0013 G4 holds them through its rule for `releases/*/index.json` aggregates (`DER-1` on a mismatch, `DER-3` on a missing input), which the G4 code does not yet apply. The alternative is to rerun the configuration under the new code.

## References

- docs/PRD.md §1, §4 (G2), §7 (F3, F9, F10).
- [RFC-0003](0003-workloads.md) for shapes and `active_parameters_per_token`; [RFC-0005](0005-adapter-contract.md) for proof directories and `tokens_covered`; [RFC-0006](0006-reference-hardware-and-cost.md) for `price`; [RFC-0007](0007-evidence-tiers-and-reproduction.md) for tiers; [RFC-0009](0009-results-and-publication.md) for the site that prints D-TPP; [RFC-0011](0011-measurement-and-sampling.md) for how each recorded metric is measured; [RFC-0012](0012-schemas-and-serialization.md) for the quantity schema; [RFC-0013](0013-validation-and-ci.md) for the CI gates; [RFC-0015](0015-reference-rows.md) for reference rows.
- SASH results: `sg-ai-safety-hub/zk-inference-results` at `11decec3c0b62c707618aab5deb82750b355d202` (`constants.json`).
- FlashProve: `anthropics/FlashProve` at `9e2bdd8ff5bf9c62f18263d7dac189b0400b260c` (`docs/figures.tsv`).
