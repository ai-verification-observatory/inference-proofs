# Inference Proofs: specification

Entry point of the specification corpus. This page is an index and an executive summary; the detail lives in `docs/spec/` and the normative decisions in `rfcs/`. Where any document here and an RFC disagree, the RFC takes precedence (AGENTS.md, sources of truth). Requirement keywords (MUST, SHOULD, MAY) follow RFC 2119. Terms are defined once, in the [glossary](spec/10-glossary.md).

## Executive summary

Several open systems prove that a language model produced a given output. Each publishes its own numbers, on its own model, under its own timing rules, for its own claim, so no two can be read side by side ([PRD §1](PRD.md#1-problem)). This project is a neutral benchmark that removes those differences where they can be removed and labels them where they cannot.

Five mechanisms carry the design:

1. **A claim card beside every number** ([RFC-0002](../rfcs/0002-claim-card.md)). A number is published only with a machine-checkable statement of the relation proved, the security notion, the assumptions, the bound and unbound edges and the residual.
2. **One labelled-quantity type** ([RFC-0012](../rfcs/0012-schemas-and-serialization.md), [RFC-0004](../rfcs/0004-metrics-timing-grades.md)). Every stored number carries unit, timing scope, grade, evidence tier and source. Derived numbers are recomputed bit for bit by CI from raw ones.
3. **External measurement of unchanged provers** ([RFC-0005](../rfcs/0005-adapter-contract.md), [RFC-0010](../rfcs/0010-harness-runner.md), [RFC-0011](../rfcs/0011-measurement-and-sampling.md)). Each system runs at a pinned commit inside a hardened, network-less container behind a five-subcommand adapter contract. The harness times calls and proof releases from outside and samples GPU and host resources.
4. **Adversarial checks applied by the harness** ([RFC-0008](../rfcs/0008-negative-controls.md)). Every verifier faces the same tampering controls, each with an honest twin, so a verifier that accepts everything, or a broken control, is visible.
5. **Evidence tiers** ([RFC-0007](../rfcs/0007-evidence-tiers-and-reproduction.md)). Every number carries a tier; every stored number is at tier `reported`.

Benchmark release v0.1 covers two systems on their native workloads on one NVIDIA H200 141 GB reference profile ([RFC-0006 §H200 profiles](../rfcs/0006-reference-hardware-and-cost.md#h200-profiles)), SASH zk-inference-prover and FlashProve, plus plain-serving and recompute reference rows ([RFC-0003](../rfcs/0003-workloads.md), [RFC-0015](../rfcs/0015-reference-rows.md)). It publishes no ranking and no aggregate score ([PRD §5](PRD.md#5-non-goals)).

## Corpus

| Section | Content |
|---|---|
| [00 Overview](spec/00-overview.md) | thesis, users, goals and non-goals, v0.1 scope and run matrix, success criteria, design reflection and risks |
| [01 Architecture](spec/01-architecture.md) | components, module boundaries and allowed dependencies, data flow from workload to site |
| [02 Public API](spec/02-public-api.md) | the public surfaces (CLI, schemas, adapter contract, file layout) and their stability |
| [03 Data model](spec/03-data-model.md) | objects, keys, references, cross-object invariants, lifecycles |
| [04 Error model](spec/04-error-model.md) | error taxonomy and the failure-mode catalogue |
| [05 Observability](spec/05-observability.md) | structured logs, event catalogue, redaction, diagnosis from a run directory |
| [06 Security](spec/06-security.md) | threat model, trust boundaries, container hardening, secrets, privacy, disclosure |
| [07 Testing strategy](spec/07-testing-strategy.md) | test pyramid, named suites, fixtures, fake system, GPU-host tests |
| [08 Performance budget](spec/08-performance-budget.md) | harness overhead, CI and build budgets, run-campaign budget method |
| [09 Release and versioning](spec/09-release-and-versioning.md) | harness SemVer, schema and contract majors, benchmark releases, deprecation, changelog |
| [10 Glossary](spec/10-glossary.md) | canonical vocabulary |

## RFC index

| RFC | Title | Decides |
|---|---|---|
| [0001](../rfcs/0001-rfc-format.md) | RFC format | the RFC template and numbering |
| [0002](../rfcs/0002-claim-card.md) | Claim card | what a proof establishes, per configuration |
| [0003](../rfcs/0003-workloads.md) | Workloads, prompt sets and divisions | workload schema, v0.1 workloads, prompt generation, seeds, divisions |
| [0004](../rfcs/0004-metrics-timing-grades.md) | Metrics, timing scopes and grades | recorded metrics, scopes, grades, derived formulas, statistics |
| [0005](../rfcs/0005-adapter-contract.md) | Adapter contract | container interface, `system.yaml`, proof release, verdict mapping |
| [0006](../rfcs/0006-reference-hardware-and-cost.md) | Reference hardware and cost basis | profiles, machine record, CPU binding, price basis |
| [0007](../rfcs/0007-evidence-tiers-and-reproduction.md) | Evidence tiers | the `tier` label |
| [0008](../rfcs/0008-negative-controls.md) | Negative controls | shared and system controls, honest twins, outcomes, disclosure |
| [0009](../rfcs/0009-results-and-publication.md) | Results format and publication | run directories, releases, site, targets |
| [0010](../rfcs/0010-harness-runner.md) | Harness runner and job lifecycle | CLI, job state machine, error taxonomy, retries, timeouts |
| [0011](../rfcs/0011-measurement-and-sampling.md) | External measurement and resource sampling | clocks, proof release watcher, NVML and cgroup sampling |
| [0012](../rfcs/0012-schemas-and-serialization.md) | Artifact schemas, labelled quantities and serialization | schema catalogue, versioning, quantity type, digests, JSON writer |
| [0013](../rfcs/0013-validation-and-ci.md) | Validation pipeline and CI gates | every CI gate and its exact rule |
| [0014](../rfcs/0014-provenance-and-integrity.md) | Provenance, pinning and artifact integrity | pins, image builds, model fetch, manifest, commitment handling |
| [0015](../rfcs/0015-reference-rows.md) | Reference rows: plain serving and recompute | what the reference rows measure and when they are null |
| [0016](../rfcs/0016-glyph-properties-and-states.md) | Glyph properties and states (no longer drives the site from Level 1, RFC-0018) | the six glyph properties, the four states, the source of each state by row class, the negative control override, the criteria file |
| [0018](../rfcs/0018-level-1-ladder.md) | Level 1: the ladder, six checks, cost and fidelity | the level file, rungs, the common request, beacon prompts, sessions, the release-group steady rule, the serving ladder, the six checks, fidelity and KL, the order rule, the board file, the site. Wins over earlier RFCs for a Level 1 release |
| [0017](../rfcs/0017-requests-tasks-and-tested-states.md) | Requests, tasks and tested states | the request as the unit a reader compares, the per-request figures, the task rule, the median; then what the next runs add: control coverage, a baseline at the proved precision, one row per verifier |

## Pinned upstreams for v0.1

| System | Repository | Commit |
|---|---|---|
| SASH zk-inference-prover | `sg-ai-safety-hub/zk-inference-prover` | `eb95bfa887299d1637550228d42086c27cbb2b3b` |
| SASH results (external figures) | `sg-ai-safety-hub/zk-inference-results` | `11decec3c0b62c707618aab5deb82750b355d202` |
| FlashProve | `anthropics/FlashProve` | `9e2bdd8ff5bf9c62f18263d7dac189b0400b260c` (v0.16.0) |

Full hashes were resolved from the abbreviated pins in the PRD through the GitHub API on 2026-11-03.
