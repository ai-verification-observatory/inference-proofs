# RFC-0015: Reference rows: plain serving and recompute

- Status: Draft
- Authors: AbdelStark
- Created: 2026-11-03
- Target milestone: v0.1-beta
- Requires: RFC-0003, RFC-0004, RFC-0005, RFC-0006, RFC-0011
- Supersedes: none
- Discussion: pull request that introduces it

## Summary

Every native workload gets two reference rows measured on the same profile, with the same prompts and the same token accounting as the proving systems: plain serving (the model served unproved) and recompute (a verifier holding the weights reruns the forward pass and checks the claimed output). Plain serving gives the overhead factor, the most asked-for number (PRD §6). Recompute answers what a proof buys over a party that simply holds the weights. Both are implemented as ordinary adapters (`systems/ref-serve`, `systems/ref-recompute`) under the RFC-0005 contract with `kind: reference`, so the harness, measurement and statistics are shared and nothing is special-cased except which steps run.

## Motivation

PRD §6 asks for "two reference rows per workload, so every proof cost reads against something": plain serving with vLLM, pinned, on the same model, precision and hardware, and naive recompute by a verifier holding the weights. A proving rate alone says nothing about cost relative to the work being proved; the overhead against plain serving does (RFC-0004 D-OVERHEAD-S). Recompute also gives a second, independent check of the claimed outputs: FlashProve's claim card states that it proves the integer model, which differs from the 16-bit model's top token at some positions (RFC-0002 example residual), and readers need to see how often the claimed output agrees with a plain forward pass.

## Goals

- Reference rows use the same workload ids, versions, prompt sets (seeds), shapes and profile as the system rows they serve.
- Tokens are counted with the same rule as the proving system's claim card coverage (RFC-0004 INV-TOK-1), so D-OVERHEAD-S divides like by like.
- The serving engine is pinned by image digest and version; precision substitutions are declared and flagged.
- Output agreement between recompute and each system's claimed outputs is reported as counts and a derived rate, separately from verdicts.
- A reference row that cannot run on the profile is recorded as such, and every metric that depends on it is null with a reason.

## Non-Goals

- Tuning the serving engine for peak throughput beyond its documented defaults and the workload's batch size. The reference is "plain serving as documented", not the maximum throughput the engine could reach with tuning.
- Decode-heavy serving profiles, latency under load, request arrival processes (no such workload in v0.1).
- Judging which output is correct when recompute and a system disagree. Agreement is reported; no verdict is changed.
- Reference rows on profiles other than the system rows' profile.

## Proposed Design

### Reference systems

Two directories, each a normal adapter (RFC-0005) with `system.yaml` field `kind: reference` and `reference_role: serve | recompute`:

```
systems/ref-serve/       Dockerfile (engine image by digest), entrypoint, system.yaml, README.md, tests/
systems/ref-recompute/   Dockerfile (same engine image by digest), entrypoint, system.yaml, README.md, tests/
```

Reference systems have no `claim.yaml` (they prove nothing) and no controls. The site shows them only as reference rows beside a workload's system rows, never as systems.

```yaml
# systems/ref-serve/system.yaml (shape)
schema: "system/1"
name: "ref-serve"
kind: "reference"
reference_role: "serve"
engine: {name: "vllm", version: "<pinned release>", image: "<repo>@sha256:<digest>"}
workloads:
  - id: "sash-l31-8b-c4096"
    precision_used: "<scheme>"           # equal to the workload's as-served precision, or a declared substitute
    precision_substitution: null         # or {reason: "...", source: "<engine docs URL at version>"}
    engine_args: ["--max-num-seqs", "1"] # only options the engine documents; recorded verbatim
incremental_proofs: true
deterministic_proofs: false
forbidden_flags: []
```

### Steps per job

For `kind: reference` the runner (RFC-0010) runs `info`, `setup`, `prove`; it records `commit` and `verify` as `skipped`. Consequences in RFC-0004 terms: `commit_seconds` and the D-COMMIT-AMORT metrics are null with `null_reason: not_applicable`; `whole_wall` is null with `not_applicable` (there is no commit start event); `prove.session` and `prove.steady` are measured exactly as for a proving system.

- REF-1. The `prove` subcommand loads the engine once, processes the workload's requests in the workload's order, and after each batch writes one release directory `/io/proofs/<batch_id>/outputs.json` atomically (RFC-0005 rename contract). The release watcher (RFC-0011) timestamps these directories, so `prove.steady` (first to last batch release) excludes engine start-up and model load, and `prove.session` includes them, with the same boundaries as the proving systems.
- REF-2. Release directories of a reference system are called "outputs", not proofs, in every record and page. The harness computes no proof bytes for them.
- REF-3. Tokens per release are counted by the harness with the coverage rule of the system the reference row serves: for `window`, the window's positions; for `prompt_plus_output`, prompt plus output positions (RFC-0004 INV-TOK-1).

### Plain serving (`ref-serve`)

- SRV-1. Batch size equals the workload's `batch_size`; batches per session equal `batches_per_session`.
- SRV-2. Greedy decoding (temperature 0), `max_tokens` equal to the workload's `output_tokens`, or 1 for next-token workloads (the window is prefilled and one token is produced, the smallest unit the engine serves).
- SRV-3. Engine options: only those the pinned engine version documents, listed verbatim in `system.yaml`, chosen to make the workload fit (for example maximum sequence count equal to the batch size, maximum model length equal to the context window). No option that changes numerics beyond the declared precision.
- SRV-4. Outputs are recorded (`outputs.json`: request index, generated token ids) for audit; serving outputs are not compared with system outputs, because batched serving may legitimately differ from batch 1 at ties.
- SRV-5. Metrics: `rate_prove.steady`, `rate_prove.session`, GPU and host resources as RFC-0011. These feed D-OVERHEAD-S (RFC-0004).

### Recompute (`ref-recompute`)

A verifier holding the weights checks a claimed output by running the model itself.

- RC-1. The job reuses the prompt seeds recorded in a named system run: `iproofs run --system ref-recompute --workload W --profile P --prompts-from RUN_DIR`. The manifest records the source run id. Prompts are therefore identical request by request.
- RC-2. Batch size 1, always, whatever the workload's batch size, because a verifier checks one request at a time and batch 1 removes batch-composition effects on greedy ties.
- RC-3. Teacher-forced check: for each request, the engine runs one forward pass over prompt plus the system's claimed output tokens and takes the argmax at each claimed output position (for next-token workloads, the single position after the window). Each position is `agree` when the argmax equals the claimed token, else `disagree`. Ties are resolved by the pinned engine's own argmax rule, which the adapter README states with a link to the engine documentation or source at the pinned version.
- RC-4. Each request's result is released as `/io/proofs/<request_id>/outputs.json` with per-position argmax tokens; timing follows REF-1. Recompute's cost is reported as D-SPT-prove.steady and D-COST-1K-prove.steady of the ref-recompute configuration: seconds and money per token for a warm verifier holding the weights, on prover-h100.
- RC-5. Agreement is reported per (system configuration, ref-recompute configuration) pair in the release index:

| Metric id | Unit | Scope | Grade | Formula |
|---|---|---|---|---|
| `agreement_positions` | count | null | derived | positions with `agree` |
| `disagreement_positions` | count | null | derived | positions with `disagree` |
| `first_disagreement` | count | null | derived | per request, index of the first disagreeing output position, or null |
| `agreement_rate` | ratio | null | derived | D-AGREE: `agreement_positions / (agreement_positions + disagreement_positions)` |

- RC-6. INV-REF-1: agreement never changes a verdict, a control outcome or a tier. A proof accepted by its verifier stays accepted when recompute disagrees; the claim card's `quality_gap` and `residual` fields (RFC-0002) are the place where a system explains expected disagreement, and the site prints the agreement rate beside them.
- RC-7. For SASH-style continuations, positions after the first disagreement are still compared under teacher forcing (the claimed prefix is fed, not the recomputed one), so every position is checked against the same claimed context.

### Precision matching

- PM-1. The reference precision equals the workload's `precision.served` (RFC-0003) when the pinned engine documents support for it on the profile's GPU.
- PM-2. Otherwise the reference uses the nearest supported scheme by this order: same weight bit width with higher activation bit width; then the next higher weight bit width with the lowest supported activation bit width. The substitution is declared in `system.yaml` `precision_substitution` with the reason and the engine documentation link, and every metric of the row carries `quality.precision_substituted: true` (RFC-0012).
- PM-3. D-OVERHEAD-S over a substituted reference is computed and flagged, not suppressed: the reader sees the factor and the flag. A substitution to a lower bit width than the workload is never allowed (it would flatter the reference).

### Feasibility on the profile

RISK: the Maverick workloads use a public 4-bit conversion of a mixture-of-experts model with about 400B parameters (PRD §1, external, reported). Its weights exceed the 80 GB of GPU memory on prover-h100, and FlashProve itself relies on about 300 GB of host memory (external, reported). The pinned serving engine may be unable to serve or recompute it on one H100, with or without a documented CPU offload option.

Rule NM-1: the runner attempts each reference job on the system rows' profile with the engine's documented options only (including CPU offload if the pinned version documents it, declared in `engine_args`). If every attempt of a configuration fails with kind `resource` or `adapter` (unsupported model or precision), the failures are recorded as usual (RFC-0010) and the configuration is marked `not_measurable_on_profile` in the release index. Every metric that depends on it (D-OVERHEAD-S, D-AGREE) is null with `null_reason: not_measurable_on_profile`. No larger profile is used in v0.1 (RFC-0006 R1). Resolution path: if the Maverick rows have no reference, the v0.1 report says so in its first paragraph about FlashProve, and a v0.2 RFC decides whether a multi-GPU reference profile is admitted for reference rows only.

### Failure modes

| Failure | Response |
|---|---|
| Engine cannot load the model or precision | job failed (`adapter` or `resource`); after all attempts, NM-1 |
| `--prompts-from` run missing, failed, or for another workload version | `config` error before any step |
| Claimed outputs missing in the source run | `config` error; recompute requires a successful source run |
| Engine option not in the pinned version's documentation | policy check fails in review; adapter README lists the documentation link for every option |
| Precision substitution to fewer bits | validator rejects `system.yaml` (PM-3) |
| Reference row on another profile than the system row | D-OVERHEAD-S null with `not_applicable` (RFC-0004 INV-DERIVE-2) |

## Alternatives Considered

- **Use upstream serving figures (the engine's published benchmarks).** Considered because it costs no GPU time. Rejected: those figures use other hardware, shapes and scopes; the overhead factor needs the same machine and the same token accounting.
- **Hugging Face Transformers eager forward pass as the reference.** Considered because it is the simplest reference implementation. Rejected for serving: it understates what plain serving achieves, so every overhead factor would look smaller than against a serving engine. Kept in mind for recompute if the serving engine cannot run a precision, via a later RFC.
- **Recompute through the `verify` subcommand, one container call per request.** Considered because recompute is a verifier. Rejected: every call would reload the weights, so the number would mostly measure model load, not what a verifier holding the weights pays per request; RC-4 measures warm cost and keeps load visible in `prove.session`.
- **Recompute on the verifier profile (CPU only).** Considered because the proving systems' verifiers are timed there. Rejected: a verifier holding an 8B or about-400B-parameter model on 8 CPUs and 32 GiB is not a realistic deployment; recompute is reported on prover-h100 and labelled so.
- **Compare free-running greedy outputs instead of teacher forcing.** Considered as simpler. Rejected: after the first divergence the contexts differ and later positions are no longer comparable; teacher forcing checks every claimed position against the same context.
- **A separate workload file per reference row.** Considered for explicitness. Rejected: separate ids invite drift in shape or prompts; reusing the workload id makes INV-DERIVE-2 checkable.

## Drawbacks

- "Plain serving as documented" is not the maximum achievable serving throughput, so overhead factors are relative to a stated engine configuration, not to a physical limit.
- The serving engine is itself a moving target; a newer version may change every overhead factor, which is why it is pinned per release.
- The Maverick reference rows may be absent in v0.1 (RISK above).

## Conflicts of Interest

The author's affiliations and any interest in a measured system are declared in `MAINTAINERS.md` before this RFC enters Last call (RFC-0001).

## Migration / Rollout

New RFC; no results exist. The draft RFC-0003 named `ref-serve-*` and `ref-recompute-*` as workload ids; this RFC replaces them with reference systems run on the existing workload ids (consistent with RFC-0003 as revised). Schema additions (RFC-0012): `system/1` fields `kind`, `reference_role`, `engine`, `precision_used`, `precision_substitution`; `manifest/1` field `prompts_from`; quantity `quality.precision_substituted`; release index agreement block.

## Testing Strategy

CPU-only:

- TC-REF-SKIP: runner on a fake reference system (`systems/fake` with `kind: reference` fixture) records `commit` and `verify` as skipped, `whole_wall` and commit metrics null with `not_applicable`, steady and session present.
- TC-REF-TOKENS: fake reference releases for a `window` workload of 1,024 positions count 1,024 tokens per request.
- TC-AGREE-FIXTURE: hand-computed fixture: 3 requests, claimed outputs of 4 tokens, argmax disagreeing at 1 position in request 2; expects `agreement_positions` 11, `disagreement_positions` 1, `first_disagreement` [null, index, null], `agreement_rate` 11/12.
- TC-AGREE-NO-VERDICT-CHANGE: a disagreeing recompute leaves the source run's verdicts and tiers unchanged in the release index (INV-REF-1).
- TC-PROMPTS-FROM: recompute materialises the same prompt digest as the source run; a source run of another workload version fails `config`.
- TC-PRECISION-SUBST: `system.yaml` with a lower-bit substitution is rejected; a higher-bit one is accepted and every quantity carries `precision_substituted: true`.
- TC-NM-1: all attempts failed with `resource`; release index marks `not_measurable_on_profile`; D-OVERHEAD-S and D-AGREE null with that reason.
- TC-OVERHEAD-JOIN: release-level D-OVERHEAD-S joins only rows with equal workload id, version, profile, phase and batch size.

GPU host:

- GH-REF-SERVE-L31: ref-serve on `sash-l31-8b-c1024`, three repetitions, schema-valid, `rate_prove.steady` non-null.
- GH-REF-RECOMPUTE-L31: ref-recompute with `--prompts-from` a SASH run; agreement block present.
- GH-REF-MAVERICK-ATTEMPT: ref-serve on `fp-maverick-w1024-b1`; either a valid row or a recorded failure leading to NM-1.

## Open Questions

- OPEN QUESTION Q1 (owner: AbdelStark, resolve by: 2027-01-31): which vLLM release and image digest are pinned for v0.1? Constraint: it documents support for Llama-3.1-8B W8A8 and for the public 4-bit Llama 4 Maverick conversion (or a declared nearest precision) on H100. Default until resolved: the newest release that meets the constraint on the date the `systems/ref-serve` pull request opens.
- OPEN QUESTION Q2 (owner: AbdelStark, resolve by: 2027-03-31 or a v0.2 RFC): should a multi-GPU profile be admitted for reference rows only, when a model cannot be served on the system rows' profile? Default until resolved: no; NM-1 applies.
- OPEN QUESTION Q3 (owner: AbdelStark, resolve by: 2027-01-31): does the pinned engine expose argmax over teacher-forced positions directly (for example through prompt log-probabilities), or does the recompute adapter need a documented engine API call? Default until resolved: the adapter README documents the call used; no engine source change is made (AGENTS.md rule 1 applies to reference engines too).

## References

- docs/PRD.md §6, §7.
- [RFC-0002](0002-claim-card.md) for `quality_gap` and `residual`; [RFC-0003](0003-workloads.md) for workload ids, precision and seeds; [RFC-0004](0004-metrics-timing-grades.md) for D-OVERHEAD-S, D-SPT and INV-DERIVE-2; [RFC-0005](0005-adapter-contract.md) for the adapter contract; [RFC-0006](0006-reference-hardware-and-cost.md) for profiles; [RFC-0010](0010-harness-runner.md) for skipped steps; [RFC-0011](0011-measurement-and-sampling.md) for release timing.
- vLLM documentation at the pinned release (engine options, supported quantisation schemes).
