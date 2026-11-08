# 00. Overview

Status: Draft 0.1, part of the specification corpus indexed by [docs/SPEC.md](../SPEC.md). Normative decisions live in the RFCs under [rfcs/](../../rfcs/README.md); where this section and an Accepted RFC disagree, the RFC takes precedence.

## Thesis

Inference Proofs is an open, neutral benchmark for provable inference. It runs proof systems for language-model inference unchanged, on fixed workloads and reference hardware, measures them from outside under fixed timing rules, attacks every verifier with the same negative controls, and publishes every number beside a claim card that says what an accepted proof establishes. It measures provers; it does not build, rank or certify them.

The unique claim is the pairing: comparable measurement and an explicit statement of the proved claim, travelling together. Neither alone is enough, because inference proof systems prove different statements, so a rate without its claim is not comparable and a claim without a measured cost is not actionable.

## Problem

Several open systems produce cryptographic proofs that a language model produced a given output. Each publishes its own numbers, measured its own way, on its own model, for its own claim ([PRD §1](../PRD.md#1-problem)). The first two systems in scope show the gap:

| | SASH zk-inference-prover | FlashProve |
|---|---|---|
| Pin | `sg-ai-safety-hub/zk-inference-prover` at `eb95bfa887299d1637550228d42086c27cbb2b3b`; results in `sg-ai-safety-hub/zk-inference-results` at `11decec3c0b62c707618aab5deb82750b355d202` | `anthropics/FlashProve` at `9e2bdd8ff5bf9c62f18263d7dac189b0400b260c` (v0.16.0) |
| Model | Llama-3.1-8B, W8A8, dense | Llama 4 Maverick, public 4-bit conversion, mixture of experts |
| One proof covers | one segment (a layer over a block of positions, or the output head); a sequence is a grid of segments | one request: a pass over a 1,024-token window, stating the next token |
| Headline rate (external, reported, upstream at the pins) | 1.251 positions/s over 4,608 positions, upstream loop scope; 0.840 positions/s, upstream whole-wall scope | 111.23 ± 0.92 tokens/s of prefill at 24 requests per batch, upstream steady scope, start-up and commitment excluded |

Different models, phases, timing scopes and claims: dividing one headline by the other says nothing. The questions users actually have (what is proved, what it costs per token on given hardware, how long verification takes, whether the verifier rejects tampering, whether a rerun gives the same numbers) have no common answer today.

## Users

| User | Needs | Served by |
|---|---|---|
| Prover teams | cheap, credible, reproducible numbers; a fair comparison; a negative-control corpus | adapter contract (RFC-0005), controls (RFC-0008), reproduction (RFC-0007) |
| Researchers | pinned, rerunnable measurements; cost structure (commit, prove, verify, I/O) | timing scopes (RFC-0004), measurement (RFC-0011), provenance (RFC-0014) |
| Relying parties (policy analysts, auditors, labs, governments, standards bodies) | plain statement of what is proved and not proved; whether a system meets a threshold | claim card (RFC-0002), targets (RFC-0009) |
| Funders | evidence of progress over time independent of self-reporting | evidence tiers (RFC-0007), releases (RFC-0009) |

## Goals

| Goal | Statement | Mechanism | RFC |
|---|---|---|---|
| G1 Claim first | every published number carries a claim card; no card, no number | `claim/1` schema, card-first site rule INV-CLAIM-1 | [RFC-0002](../../rfcs/0002-claim-card.md) |
| G2 Comparable by construction | fixed workloads, reference hardware, timing scopes, cost basis; incomparable rows are labelled | workloads and divisions, scopes, profiles, derived metrics | [RFC-0003](../../rfcs/0003-workloads.md), [RFC-0004](../../rfcs/0004-metrics-timing-grades.md), [RFC-0006](../../rfcs/0006-reference-hardware-and-cost.md), [RFC-0015](../../rfcs/0015-reference-rows.md) |
| G3 Reproducible | every row pins prover commit, image digest, model hash, hardware, driver and command; "measured" in prose only once reproduced | provenance, tiers, reproduction protocol | [RFC-0007](../../rfcs/0007-evidence-tiers-and-reproduction.md), [RFC-0014](../../rfcs/0014-provenance-and-integrity.md) |
| G4 Adversarial | every verifier faces the same negative controls; each row reports outcomes | harness-applied controls with honest twins | [RFC-0008](../../rfcs/0008-negative-controls.md) |
| G5 Neutral | multi-organisation maintainers, RFC process, declared conflicts, team review, right of reply, no single score | governance, publication rules | [RFC-0001](../../rfcs/0001-process-and-governance.md), [RFC-0009](../../rfcs/0009-results-and-publication.md) |
| G6 Low cost to join | a thin adapter; no fork or patch of any prover | one container, five subcommands over JSON files | [RFC-0005](../../rfcs/0005-adapter-contract.md), [RFC-0010](../../rfcs/0010-harness-runner.md) |

Cross-cutting support: labelled quantities and serialization ([RFC-0012](../../rfcs/0012-schemas-and-serialization.md)), CI gates ([RFC-0013](../../rfcs/0013-validation-and-ci.md)), external measurement ([RFC-0011](../../rfcs/0011-measurement-and-sampling.md)).

## Non-goals

- Ranking systems or naming any system superior. No aggregate score, no default sort by speed.
- Certifying security. The benchmark copies declared claims and reports test outcomes; it does not audit soundness proofs or code.
- Building or maintaining provers or shared proving libraries.
- Training, fine-tuning or compute-accounting claims.
- Setting policy thresholds. Relying parties publish targets under their own names.
- In v0.1: common or closed workloads, sampled decoding, multi-GPU profiles (for reference rows too, RFC-0015 Q2), signed or attested results, structured proof-format fuzzing.
- A normalised proof size: succinct proofs barely grow with the model, so dividing by model size would favour larger models by construction (RFC-0004 §Non-Goals).

## v0.1 scope

Two systems, unchanged at the pins above, on one reference prover profile (`prover-h200`: one NVIDIA H200 141 GB SXM; its hosted form `prover-h200-hosted` and the H100 profiles stay declared, [RFC-0006 §H200 profiles](../../rfcs/0006-reference-hardware-and-cost.md#h200-profiles)) and one verifier profile (`verifier-cpu`: 8 CPUs, 32 GiB, no GPU), native division, plus one closed workload on Llama 3.1 8B (`l31-8b-c1024`) whose rows publish once a second system with its claim class runs it (Q7, default) ([RFC-0003 §Closed workloads](../../rfcs/0003-workloads.md#closed-workloads)).

Run matrix. Each cell is a configuration measured with at least 3 repetitions (RFC-0004); the first successful repetition of each configuration is followed by the shared and system-specific controls (RFC-0008).

| Workload | Proving system | `ref-serve` row | `ref-recompute` row |
|---|---|---|---|
| `sash-l31-8b-c4096` | SASH | yes | yes |
| `sash-l31-8b-c1024` | SASH | yes | yes |
| `fp-maverick-w1024-b1` | FlashProve | yes, or recorded as not measurable on profile (RFC-0015) | yes, or recorded as not measurable on profile |
| `fp-maverick-w1024-b24` | FlashProve | same | same |

Published per row: claim card; per-scope times and rates; GPU and host memory peaks; proof bytes; verification time (8 CPUs and 1 CPU); control outcomes; derived metrics (cost per 1,000 proved tokens at the release price, overhead against plain serving, prover time per bit of active weights (with the claim cards and its stated limit, RFC-0004 INV-DERIVE-7), proof bytes and verification seconds per proved token, amortised commit cost at 1 and 1,000 requests); scope, grade, tier and source beside every number.

v0.1 does not compare SASH and FlashProve on one model. Neither supports the other's model at these pins.

Milestones, all inside benchmark release v0.1:

| Milestone | Content | Exit criterion |
|---|---|---|
| `v0.1-alpha` | schemas, serialization, labelled quantities, derivation and statistics, validation CLI, CI gates, fake system, runner against the fake system, governance files | in CI, `iproofs run --system fake` produces a schema-valid run directory, `iproofs derive --check` passes, controls classify, and `fake-broken` is flagged |
| `v0.1-beta` | GPU measurement, model fetch and hash check, prompt generation, SASH and FlashProve adapters, reference rows, controls on real systems | at least one `reported` run per matrix cell on `prover-h200`, each with a valid run directory |
| `v0.1` | reviewed claim cards, peer review, third-party reproduction, site, report, 14-day review window, freeze | the success criteria below |

## Success criteria

v0.1 succeeds when every item holds; each is checkable from the repository:

1. SC-1: `releases/v0.1/index.json` exists and `iproofs validate` passes on the whole tree.
2. SC-2: for each of SASH and FlashProve, at least one configuration has effective tier `reproduced` in the index (PRD §8: reproduced end to end by someone other than their authors).
3. SC-3: every claim card in the release has a non-empty `reviewed_by` whose `card_version` equals the frozen version, or the release report states that the system maintainers did not review it and why.
4. SC-4: every system maintainer listed had at least 14 days between the release candidate and freeze (dates in `release.yaml`).
5. SC-5: every row has control outcomes for C1 to C8 and P1 to P2 (outcome `not_applicable` allowed with reason), and `fake-broken` is flagged in CI.
6. SC-6: zero quantities in the release lack unit, grade, tier or source, or lack scope when time-based (CI gate 5).
7. SC-7: `MAINTAINERS.md` lists maintainers from at least two organisations (RFC-0001 INV-GOV-1).

Beyond v0.1 ([PRD §8](../PRD.md#8-success-metrics)): v0.2 needs one common workload run by two systems through adapters only; within a year, five systems across two proof families and two outside maintainers. Adoption is counted in submissions and reproductions, not stars.

## Design reflection

### What this solves that nothing else does

Each prover's own benchmark answers "how fast is my system under my rules". Generic ML benchmarks (serving throughput suites) measure unproved inference. zkVM dashboards compare provers of one well-defined statement (an Ethereum block). Nothing measures inference proof systems under one set of timing rules, on pinned hardware, with the same tampering tests, while keeping the differing claims visible. The claim card is the piece that makes measurement meaningful across systems whose statements differ.

### The three hardest problems on the path to v1

1. **Honest comparison across different claims and models.** Native workloads differ in model, phase and proof unit. The design answers with claim cards first, divisions, normalised metrics labelled as rough, and a rule that native rows are never presented head to head (RFC-0002, RFC-0003, RFC-0004).
2. **Measuring from outside without patching provers.** Provers report their own phases in their own scopes. The harness must time unmodified binaries in containers, observe per-proof release times through atomic file renames, and sample GPU and cgroup counters without perturbing the run (RFC-0005, RFC-0011). Where a scope is not externally observable, the number is null with a reason, never estimated.
3. **Reproduction at GPU cost.** A single configuration can take hours of H100 time, weights are gated, and proofs are gigabytes. The design reduces cost (three repetitions, digests instead of stored proofs, seed replay) and accepts that tiers may stay below `reproduced` if no independent runner appears (RFC-0007, RFC-0014).

### Load-bearing abstractions and their contracts

| Abstraction | Contract | Invariants | Owner |
|---|---|---|---|
| Labelled quantity | every number is `{value, unit, scope, grade, tier, source, null_reason}`; null needs a reason; time units need a scope | no unlabelled number in any record | RFC-0012, RFC-0004 |
| Claim card | per-configuration statement copied from upstream with sources; `not stated` where silent | INV-CLAIM-1 to INV-CLAIM-4 | RFC-0002 |
| Workload | model by digest, prompts by corpus digest + generator + recorded seed, shape, greedy decoding | INV-WL-1 to INV-WL-5 | RFC-0003 |
| Adapter | one image, five subcommands, JSON in and out, no upstream patch, commitment passed in by the harness | contract `adapter/1` | RFC-0005 |
| Job | one system x workload x shape x repetition; a state machine whose failures are recorded, never dropped | failed jobs are written | RFC-0010 |
| Run directory | append-only record of one job with manifest, controls, verifier outputs and digests | `run.json` tiers are `reported`; derived numbers recompute bit-exactly | RFC-0009, RFC-0012 |
| Control | harness-applied mutation with an honest twin and an expected outcome set | void if the twin is not accepted | RFC-0008 |
| Release | frozen set of runs, reference file, RFC commit and card versions; effective tiers computed at freeze | published releases are never edited | RFC-0009, RFC-0007 |

### Failure modes designed against

| Failure mode | Design response |
|---|---|
| Headline numbers compared out of context | card first, divisions, scope and tier beside every number, no aggregate score |
| An adapter whose verify always says accept | harness-applied controls; such a verifier fails C1 to C8; CI runs `fake-broken` to prove the suite catches it |
| A broken control mistaken for a strong verifier | honest twin first; a control whose twin is not accepted is `void` |
| Precomputed proofs for a public prompt set | fresh seed per measured job, recorded for replay |
| A swapped weight file | per-file hashes checked before any container sees the files |
| Commitment taken from the prover's own output | the harness passes the commitment from its own `commit` record (AGENTS rule 6) |
| A weakened configuration published as a row | forbidden flags in `system.yaml`, policy gate in CI, no card for weakened configurations |
| A failed run silently dropped | every failure is recorded with kind, step, exit code and last lines; counted in `n_failed` |
| Hand-typed derived numbers drifting | CI recomputes every derived value bit-exactly |
| Leaked secrets or host identifiers | redaction before write, CI secrets scan, machine record allowlist |
| A reviewer from the runner's own organisation | review record validator rejects it |

### Explicitly out of scope, and why

- Common workloads: neither v0.1 system runs the other's model without patching, and patching is forbidden. They come by RFC in v0.2.
- Security certification: it requires auditing proofs and code, which no neutral benchmark of this size can do credibly.
- Rankings and single scores: they collapse different claims into one axis, which is the error the project exists to prevent.
- Attested runners: attestation shows where code ran, not that a number holds on another machine; deferred to v0.3 (RFC-0007 Q1).

### The contributor in six months

A contributor adding a third system reads [RFC-0005](../../rfcs/0005-adapter-contract.md) for the container contract, copies `systems/fake/` as a working example, writes `claim.yaml` per [RFC-0002](../../rfcs/0002-claim-card.md) with sources at the pin, runs the CPU-only adapter tests, and opens a system inclusion issue per [RFC-0001](../../rfcs/0001-process-and-governance.md). A contributor changing a metric finds the formula in [RFC-0004](../../rfcs/0004-metrics-timing-grades.md), the code in `iproofs.derive`, the hand-computed test beside it, and the rule that the change needs an RFC because it alters published numbers. The glossary ([10-glossary.md](10-glossary.md)) defines every term once.

### Where this spec is likely wrong

- RISK: the Maverick plain-serving reference may be infeasible on the FlashProve rows' profile (one H100 80 GB or one H200 141 GB), because the 4-bit model (232 GB of weight files, external, reported, `systems/flashprove/README.md`) does not fit in GPU memory. Plan: llama.cpp on that same profile with part of the weights in host memory (RFC-0015 SRV-6), no multi-GPU profile; if it fails, record `not_measurable_on_profile` and publish overhead as null (RFC-0015 NM-1).
- RISK: `prove.steady` is not externally observable if an upstream writes all proofs at the end. Plan: null with `not_externally_observable`; the upstream steady figure shown only as `external` (RFC-0004, RFC-0011).
- RISK: SASH's segment grid does not map onto per-request proofs; tokens covered and the steady boundary depend on the adapter's declaration. Plan: confirm the grid geometry from upstream documentation before the first beta run (RFC-0003 Q4, RFC-0005).
- RISK: the verifier profile emulated on the prover host differs from a real 8-core machine (cache, memory bandwidth). Plan: record `verifier_host` and CPU model; allow a separate verifier host; revisit after v0.1 (RFC-0006).
- RISK: proof storage volume. The SASH 4,096-context run totals about 19.8 GB of proofs (external, reported, SASH results repository at `11decec3c0b62c707618aab5deb82750b355d202`). Plan: digests in git, one archived proof per configuration in an external store (RFC-0009, RFC-0014).
- RISK: third-party reproduction depends on volunteers with H100 access and gated-model licences. Plan: recruit during v0.1-beta, seek disclosed sponsorship, report the outcome either way (RFC-0007).
- RISK: host memory peak with file cache excluded is sampled at 10 Hz, not exact; short spikes can be missed. Plan: publish both the kernel `memory.peak` (exact, includes page cache) and the sampled anonymous peak (RFC-0011).
- RISK: the tier definitions rely on self-declared affiliation. Plan: social enforcement in v0.1; revisit with RFC-0007 Q3.
