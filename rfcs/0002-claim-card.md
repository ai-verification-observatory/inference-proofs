# RFC-0002: Claim card

- Status: Draft
- Created: 2026-11-03
- Requires: RFC-0001

## Summary

A machine-readable statement, per system and per configuration, of what a proof establishes, under which assumptions, and what a dishonest prover can still do. No number is published without one.

## Motivation

The two first systems prove different things. FlashProve's proof states that the next token after a 1,024-token window is the top choice of a committed integer model, with soundness proved in Lean for its Lean verifier under an exact-match policy, and weights hidden except a declared list. SASH's proof is a grid of per-segment proofs over layers and token blocks of Llama-3.1-8B W8A8, with a per-edge binding table and switches that unbind each edge. A cost per token means nothing until the reader knows which of these statements it buys.

## Specification

`systems/<name>/claim.yaml`, valid against `schema/claim.schema.json`. One card per system configuration that changes the statement (for example a policy, a model family or a hiding mode).

| Field | Required | Content |
|---|---|---|
| `system`, `configuration` | yes | identifiers |
| `upstream` | yes | repository and full commit hash |
| `relation` | yes | one precise English sentence: what is true if the verifier accepts. MAY link a formal statement (for example Lean) |
| `security.notion` | yes | soundness, knowledge soundness, or other, and for which verifier (a proved verifier and a tested one are different) |
| `security.level` | yes | as declared by the system, with its exact form (for example "q/2^124 + 2^-101 after q hash queries"), never rounded to a headline |
| `security.model` | yes | random oracle, standard model, interactive, and the adversary class (classical or quantum) |
| `security.setup` | yes | transparent, trusted, or not applicable |
| `zero_knowledge` | yes | claimed or not; what is hidden; what is not (the declared list); whether proved, tested, or neither |
| `assumptions` | yes | list: commitments, configuration files, hardware, honest parties, trusted inputs |
| `coverage` | yes | phase (prefill, decode, both), tokens covered by one proof, operations covered, policy (exact match, tolerance) |
| `binding` | yes | which edges of the computation are bound, unbound or absent, where the system reports this; else a free-text statement |
| `residual` | yes | list: what a cheating prover can still do while passing verification |
| `quality_gap` | if any | difference between the proved model and the reference model (for example top-token disagreement rate), with source |
| `availability` | yes | `available` (open source, runnable), `preview` (announced), `research` (paper code) |
| `sources` | yes | a link at the pinned commit for every field above |
| `reviewed_by` | yes | system maintainers who reviewed the card, with date; empty until review |

Rules:

1. Every field states what the system's own documentation states. Where the documentation is silent, the field says "not stated". The benchmark never fills a gap with its own inference.
2. A card is shown before any number on every page that shows the system.
3. A card changes only by pull request, reviewed by the system maintainers.
4. A run whose configuration weakens the statement (for example any `--unsound-skip-*` flag in SASH) has no card and cannot be a measured row; it may only be a negative-control job.

## Rationale and alternatives

The fields merge three sources: the relation, security definition and assumptions split used in proof-system harness designs; the binding tables some provers already print; and the residual, which readers outside cryptography most often miss. A free-text claim was rejected because it cannot be checked by CI or compared across systems.

## Open questions

1. A controlled vocabulary for assumptions, so cards can be filtered.
2. How a statistical guarantee (for example sampled recompute) fills `security.level`.
