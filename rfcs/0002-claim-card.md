# RFC-0002: Claim card

- Status: Draft
- Authors: AbdelStark
- Created: 2026-11-03
- Target milestone: v0.1-alpha (schema and validation); v0.1 (cards reviewed by system maintainers)
- Requires: RFC-0001, RFC-0012
- Supersedes: none
- Discussion: pull request that introduces it

## Summary

A claim card is a machine-readable statement, per system configuration, of what an accepted proof establishes, under which assumptions, which parts of the computation it binds, and what a dishonest prover can still do. Every published number is shown with its card, and no number is published without one. This RFC fixes the card's fields and types, the rule that every field copies the system's own documentation or says "not stated", the source link required per field, what counts as a distinct configuration, the review workflow, and the `claim_class` string that closed divisions and targets filter on. The normative schema is `schema/claim/1.schema.json` (RFC-0012).

## Motivation

The two v0.1 systems prove different statements ([PRD §1](../docs/PRD.md#1-problem)). FlashProve's proof states that the next token after a 1,024-token window is the top choice of a committed integer model, with soundness proved in Lean for its Lean verifier under an exact-match policy, and weights hidden except a declared list. SASH's proof is a grid of per-segment proofs over transformer layers and token blocks of Llama-3.1-8B W8A8, with a per-edge binding table and `--unsound-skip-*` switches that unbind each edge. A cost per token means nothing until the reader knows which of these statements it buys.

Scenarios:

1. A policy analyst sees two cost-per-token figures and needs to know, without reading source code, whether either proof hides the weights.
2. A relying party publishes a target "verification under 60 s on a laptop, for exact-match next-token claims". The site must decide mechanically which rows the target applies to.
3. SASH is run with one `--unsound-skip-*` flag in a negative-control job. Nothing about that run may appear as a measured row under SASH's card.
4. A system's documentation says nothing about quantum adversaries. The card must not say "classical only" on its behalf.

## Goals

- Every published row resolves to exactly one claim card, shown before any number (INV-CLAIM-1).
- Every card field is either copied from the system's documentation at the pinned commit with a source link, or is the literal string `not stated` (INV-CLAIM-2).
- A card is valid against `schema/claim/1.schema.json` and CI checks it.
- Cards are comparable field by field across systems, and filterable by `claim_class`.
- A configuration that weakens the statement has no card and cannot produce a measured row (INV-CLAIM-4).

## Non-Goals

- Auditing or certifying the security claims. The card reports what a system states; it does not check soundness proofs or code ([PRD §5](../docs/PRD.md#5-non-goals)).
- A controlled vocabulary for assumptions (OPEN QUESTION Q1).
- A formal language for relations. `relation` is English, optionally linked to a formal statement.
- Ranking systems by the strength of their claims.

## Proposed Design

### File and identity

- Path: `systems/<system>/claim.yaml` for a system with one configuration; `systems/<system>/claims/<configuration>.yaml` when it has several. A system uses one form or the other, not both.
- Each card is identified by `(system, configuration, card_version)`. `card_version` is a positive integer that increases with every merged change to the card.
- A run's manifest names the card it ran under as `claim: {system, configuration, card_version}`. CI fails a run whose card does not exist or whose configuration does not match the run's recorded configuration (RFC-0013).

### Configuration identity

A new configuration (a new card, not a new version of an existing card) is REQUIRED when any of the following differs, because each changes what an accepted proof means:

1. The upstream commit (a new pin may change the statement; the card is copied forward and re-reviewed, `reviewed_by` reset to empty).
2. The acceptance policy (for example FlashProve's exact-match policy versus its clipped-gap policy for whole replies).
3. The model family or precision as proved.
4. The hiding mode (weights hidden or not).
5. The verifier used to decide acceptance (for example a proved Lean verifier versus a tested C++ verifier), when they carry different security statements.

Changes that do NOT need a new configuration: batch size, prompt length within the workload's supported shapes, and hardware profile. These are workload and profile properties (RFC-0003, RFC-0006).

### Fields

Types use the RFC-0012 conventions. `Text` is a non-empty string; `NotStated` is the literal string `not stated`; `SourceRef` is a URL that MUST contain the full 40-hex upstream commit hash, or a path in this repository at a full commit hash.

| Field | Required | Type | Content |
|---|---|---|---|
| `schema` | yes | `"claim/1"` | schema identifier |
| `system` | yes | system id (`^[a-z][a-z0-9-]{1,31}$`) | matches `systems/<system>/` |
| `configuration` | yes | id (`^[a-z0-9][a-z0-9-]{0,47}$`, RFC-0012) | e.g. `exact-match-lean` |
| `card_version` | yes | integer >= 1 | |
| `upstream` | yes | `{repo: Text, commit: 40-hex}` | repository and full commit hash |
| `claim_class` | yes | string, see [Claim class](#claim-class) | filter key for closed divisions and targets |
| `relation` | yes | `Text` | one English sentence: what is true if the verifier accepts. Optional `relation_formal: SourceRef` links a formal statement (for example a Lean theorem) |
| `security.notion` | yes | `{kind: enum, verifier: Text}` | `kind` in `soundness`, `knowledge_soundness`, `other`, `not_stated`; `verifier` names which verifier the notion is stated for |
| `security.level` | yes | `Text` or `NotStated` | as declared, in its exact form (for example "q/2^124 + 2^-101 after q hash queries"), never rounded to a headline bit count |
| `security.model` | yes | `{assumption: Text or NotStated, adversary: enum}` | `assumption`: random oracle, standard model, interactive, other; `adversary` in `classical`, `quantum`, `not_stated` |
| `security.setup` | yes | enum | `transparent`, `trusted`, `not_applicable`, `not_stated` |
| `zero_knowledge` | yes | `{claimed: bool or NotStated, hidden: Text or NotStated, not_hidden: Text or NotStated, status: enum}` | `status` in `proved`, `tested`, `proved_and_tested`, `neither`, `not_stated` |
| `assumptions` | yes | list of `Text`, may be empty only with `assumptions_not_stated: true` | commitments, configuration files, hardware, honest parties, trusted inputs |
| `coverage` | yes | object, see below | |
| `binding` | yes | `{edges: list of Edge}` or `{statement: Text}` or `NotStated` | per-edge table where the system reports one |
| `residual` | yes | list of `Text`, at least one entry, or `[not stated]` | what a cheating prover can still do while passing verification |
| `quality_gap` | no | list of `{metric: Text, value: Text, source: SourceRef}` | difference between the proved model and the reference model (for example top-token disagreement rate), as stated upstream |
| `availability` | yes | enum | `available` (open source, runnable), `preview` (announced, not runnable), `research` (paper code, runnable, not maintained) |
| `sources` | yes | map from field path to `SourceRef` | one entry for every field above whose value is not `not stated` |
| `reviewed_by` | yes | list of `{handle: Text, organisation: Text, date: "YYYY-MM-DD", card_version: integer}` | empty until review |
| `forbidden_flags` | no | list of strings | flags that weaken the statement; copied into `system.yaml` (RFC-0005) for the policy gate |

`coverage`:

| Field | Type | Content |
|---|---|---|
| `phase` | enum `prefill`, `decode`, `both`, `not_stated` | which inference phase one proof covers |
| `unit` | enum `request`, `sequence`, `segment_grid`, `other` | what one proof in the benchmark's sense is |
| `tokens_covered` | `Text` | how tokens covered are counted for one proof, in the terms of RFC-0004 (for example "the window's 1,024 positions" or "every position in the grid") |
| `operations` | `Text` or `NotStated` | which operations are inside the proved computation (for example "all transformer layers and the output head") |
| `policy` | `{kind: enum, detail: Text}` | `kind` in `exact_match`, `tolerance`, `other`, `not_stated` |

`Edge`:

```yaml
- edge: <Text, the system's own edge name>
  state: bound | unbound | absent | not_stated
  switch: <flag name that unbinds it, or null>
  source: <SourceRef>
```

`state` meanings: `bound` (the system states the edge is bound in this configuration), `unbound` (the system states it is not bound, for example because a switch is on), `absent` (the edge does not exist in this system's computation), `not_stated` (the system does not say).

### Example (shape only, not a reviewed card)

```yaml
schema: claim/1
system: flashprove
configuration: exact-match-lean
card_version: 1
upstream: {repo: anthropics/FlashProve, commit: 9e2bdd8ff5bf9c62f18263d7dac189b0400b260c}
claim_class: next-token/exact-match/committed-weights
relation: >
  The output token is the top choice of the integer model whose weights were
  committed under the given commitment ID, on the given 1,024-token window.
relation_formal: not stated
security:
  notion: {kind: knowledge_soundness, verifier: "Lean verifier; C++ verifier tested against it"}
  level: "q/2^124 + 2^-101 after q hash queries, exact-match policy"
  model: {assumption: random oracle, adversary: classical}
  setup: not_stated
zero_knowledge:
  claimed: true
  hidden: weights
  not_hidden: "a declared list of weights"
  status: proved_and_tested
assumptions:
  - configuration files fixed before the hash function is drawn
  - the commitment ID is obtained from a trusted party
coverage:
  phase: prefill
  unit: request
  tokens_covered: "the window's 1,024 positions"
  operations: not stated
  policy: {kind: exact_match, detail: "top token of the integer model"}
binding: not stated
residual:
  - proves the integer model, which differs from the 16-bit model's top token at some positions
availability: research
sources:
  relation: https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/<path>
reviewed_by: []
```

The values above come from docs/PRD.md and the earlier draft of this RFC; the `<path>` and every other source link are filled from the upstream documentation in the implementing issue. `security.setup: not_stated` and `availability: research` are placeholders to be confirmed against upstream; the real card copies what upstream states.

### Rules

1. **Copy, do not infer (INV-CLAIM-2).** Every field states what the system's own documentation states at the pinned commit. Where the documentation is silent, the field is `not stated` (or the enum value `not_stated`). The benchmark never fills a gap with its own inference, and never strengthens or rounds a stated level.
2. **Card first (INV-CLAIM-1).** On every page and in every report that shows a number for a system, the card for that number's configuration appears before the number. RFC-0009 enforces this in the site generator.
3. **Sources (INV-CLAIM-3).** `sources` has an entry for every field path whose value is not `not stated`. Each `SourceRef` contains the full upstream commit hash of the card's `upstream.commit`. CI fails a card with a missing or mismatched source.
4. **Weakening configurations (INV-CLAIM-4).** A configuration that weakens the statement (for example any SASH `--unsound-skip-*` flag) has no card. A run with such a flag is valid only as a negative-control job (`control: true`, RFC-0008). The flags are listed in `forbidden_flags` and the policy gate (RFC-0013 gate 6) rejects any measured run whose manifest command lines contain one.
5. **Review.** A card changes only by pull request. Every change increments `card_version` and resets `reviewed_by` to empty; a system maintainer re-adds their entry with the new `card_version` after review.
6. **Published cards are frozen.** A release records the `card_version` of every card it shows (RFC-0009). Later card changes do not alter a published release.

### Claim class

`claim_class` is a slash-separated string of three lowercase tokens `<output>/<policy>/<weights>`:

- `<output>`: `next-token`, `greedy-continuation`, `segment-grid`, `other`.
- `<policy>`: `exact-match`, `tolerance`, `other`.
- `<weights>`: `committed-weights`, `public-weights`, `other`.

Pattern: `^(next-token|greedy-continuation|segment-grid|other)/(exact-match|tolerance|other)/(committed-weights|public-weights|other)$`. A closed workload (RFC-0003) fixes one `claim_class`; only cards with that exact string compete in it. A target (RFC-0009) names a `claim_class` filter, which may use `*` for one token. The class is chosen by the card author from the card's own `coverage` and `relation`, and reviewed with the card. It is a filter key, not a security statement.

### Validation

`iproofs validate systems/<name>/claim.yaml` performs, in order: YAML safe load; schema validation against `claim/1`; INV-CLAIM-3 source completeness and commit match; `upstream.commit` equals the commit pinned in `systems/<name>/system.yaml`; `forbidden_flags` is a subset of `system.yaml` `forbidden_flags`. Each failure is an `integrity` or `config` error (RFC-0010) naming the field path.

### Failure modes

| Failure | Response |
|---|---|
| A field is filled with the benchmark's own inference | Review catches it; INV-CLAIM-3 catches it when the inferred field has no source; the card cannot be reviewed while a sourceless field exists |
| Upstream documentation changes after the pin | No effect: sources pin the commit; a new pin is a new configuration |
| Upstream documentation is contradictory | The card quotes both statements in the field, each with its source, and the release report notes the contradiction |
| A system maintainer refuses to review | The card stays unreviewed; rows show "card not reviewed by system maintainers" |
| A run references a card version that was later changed | The run keeps its recorded `card_version`; the release shows the card version in force at freeze, and CI fails if the run's version is not the one frozen |
| A card is missing for a run | CI fails the run; no number is published (INV-CLAIM-1) |

## Alternatives Considered

- **Free-text claim paragraph.** Considered because it is easy for teams to write. Rejected: CI cannot check it, readers cannot compare it across systems, and targets cannot filter on it.
- **Formal statements only (for example Lean or a logic of claims).** Considered because it is precise. Rejected for v0.1: most systems have no formal statement, and readers outside cryptography need the English sentence and the residual most.
- **Benchmark-assigned security levels (for example normalised bits of security).** Considered because it would allow a single column. Rejected: it requires the benchmark to interpret security proofs, which is certification, a non-goal, and it rounds away the exact form.
- **One card per system regardless of configuration.** Rejected: FlashProve's exact-match and clipped-gap policies prove different statements; one card would misdescribe one of them.
- **Allowing weakened configurations as labelled rows.** Considered because the numbers are informative. Rejected: a fast number for a weakened statement next to a full one is the comparison error this project exists to prevent. Such runs stay controls.

The field set merges three sources: the relation, security definition and assumptions split used in proof-system harness designs; the binding tables some provers already print; and the residual, which readers outside cryptography most often miss.

## Drawbacks

- Cards require reading each system's documentation closely and keeping links current; that cost falls on contributors and system maintainers.
- `not stated` can look like a criticism of a system; the site explains that it records silence, not absence of a property.
- `claim_class` is coarse. Two cards in the same class can still differ in security level or hiding; the class only narrows comparison, the card still has to be read.

## Conflicts of Interest

None declared.

## Migration / Rollout

1. v0.1-alpha: `schema/claim/1.schema.json` with valid and invalid examples, the loader dataclass, and `iproofs validate` support.
2. v0.1-beta: draft cards for SASH and FlashProve, every field copied from upstream at the pins in `docs/spec/00-overview.md`, `reviewed_by: []`.
3. v0.1: system maintainers review; reviewed cards are frozen in the release.

The earlier draft of this RFC used `reviewed_by_maintainers: false` and `security.bits` in the SPEC example; they are replaced by `reviewed_by: []` and `security.level`. No published data uses the old names.

## Testing Strategy

Schema examples in `schema/claim/examples/`:

- `valid/minimal-all-not-stated.yaml`: every optional field absent, every stateable field `not stated`; passes.
- `valid/flashprove-shape.yaml`: the example above with sources filled; passes.
- `valid/binding-edges.yaml`: a `binding.edges` table with all four states; passes.
- `invalid/missing-relation.yaml`: fails on `relation`.
- `invalid/short-commit.yaml`: `upstream.commit: 9e2bdd8f`; fails on pattern.
- `invalid/rounded-level-number.yaml`: `security.level: 124` (a number); fails on type.
- `invalid/bad-claim-class.yaml`: `claim_class: next-token/exact`; fails on pattern.
- `invalid/date-unquoted.yaml`: `reviewed_by[0].date` as an unquoted YAML date; fails on type.
- `invalid/zk-status-unknown.yaml`: `zero_knowledge.status: likely`; fails on enum.

Unit tests:

- `test_sources_complete`: a card with `relation` filled and no `sources.relation` fails INV-CLAIM-3; adding it passes.
- `test_source_commit_mismatch`: a source URL with a different commit hash fails.
- `test_forbidden_flags_subset`: a card listing a flag absent from `system.yaml` fails.
- `test_run_card_resolution`: a run manifest pointing to a missing configuration fails; to an existing one passes.
- `test_claim_class_wildcard`: target filter `next-token/*/committed-weights` matches `next-token/exact-match/committed-weights` and not `segment-grid/exact-match/committed-weights`.
- Drift test (RFC-0012): dataclass fields equal schema properties.

## Open Questions

- OPEN QUESTION Q1 (owner: AbdelStark, resolve by: 2027-01-31): a controlled vocabulary for `assumptions` so cards can be filtered. Default: free text, reviewed.
- OPEN QUESTION Q2 (owner: AbdelStark, resolve by: RFC for v0.3 families): how a statistical guarantee (for example sampled recompute) fills `security.level` and `security.notion`. Default for v0.1: not needed, no v0.1 system makes a statistical claim; `kind: other` with the system's own text.
- OPEN QUESTION Q3 (owner: AbdelStark, resolve by: 2027-01-31): whether the claim class needs a fourth token for hiding (`weights-hidden`, `weights-public`) once targets ask for zero knowledge. Default: hiding is read from `zero_knowledge.claimed`, and targets filter on it directly.

## References

- [docs/PRD.md](../docs/PRD.md), sections 1, 4 (G1), 5 and 7 (F1).
- [RFC-0003](0003-workloads.md) (closed divisions use `claim_class`), [RFC-0005](0005-adapter-contract.md) (`system.yaml` `forbidden_flags`), [RFC-0008](0008-negative-controls.md) (weakened configurations as controls), [RFC-0009](0009-results-and-publication.md) (card-first site, targets), [RFC-0012](0012-schemas-and-serialization.md) (schema conventions), [RFC-0013](0013-validation-and-ci.md) (gates).
- FlashProve at `9e2bdd8ff5bf9c62f18263d7dac189b0400b260c`; SASH zk-inference-prover at `eb95bfa887299d1637550228d42086c27cbb2b3b`.
