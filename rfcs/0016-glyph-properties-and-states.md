# RFC-0016: Glyph properties and states

- Status: Draft
- Authors: 0xchqrles (affiliation to be declared in `MAINTAINERS.md`)
- Created: 2026-11-07
- Target milestone: v0.1
- Requires: RFC-0001, RFC-0002, RFC-0012, RFC-0013, RFC-0015
- Supersedes: none
- Discussion: https://github.com/ai-verification-observatory/inference-proofs/issues/318

## Summary

The public site draws every row as a glyph: six properties (Weights hidden, Model bound, Whole output proved, Formally verified, Security level, No trusted party), each in one of four states, printed Yes, Partly, No and Not stated. Today the rules behind those states exist only as prototype data in `web/_data/criteria.json`, whose own `status` reads "draft criteria, prototype only, needs an RFC (RFC-0001)". This RFC makes them normative. It fixes each property's question, what it does not cover and the rule for each state; one state vocabulary; that there is no total, score, count or order over states and no number on a property; the source of a state for each row class (claim card rows, reference rows, public-source rows); which repositories a card row may quote; what a web quote carries in place of a commit; and the contract of the criteria file (`schema: "criteria/1"`, its schema, its G2 rules `CRIT-1` to `CRIT-12` and their tests), which a second pull request implements once this RFC is Accepted. A glyph state is a label printed on every row, so RFC-0001 §Changes to methodology requires this RFC.

## Motivation

Evidence, all at this repository's commit `356949a5ee8afe328ee2cb0d68b18be1b1d82453` unless stated:

- No RFC and no section of `docs/spec/` names the six properties. The pages print "Draft criteria, needs an RFC" (`web/_data/site.json` `glyph.legend.draft_short`).
- The states are set by hand. A pipeline outside this repository wrote the data (`site.json` `generated_by: prototypes/v7/_data/make_site_data.py`). `web/build.py` reads no claim card; it only asserts that `site.json` `glyph.rows[*].states` equals `criteria.json` `test_mapping` (L41 to L44). Nothing checks a state against `systems/flashprove/claim.yaml` or `systems/sash/claim.yaml`. `criteria.json` has no `schema` field, and no RFC-0013 §G2 input glob covers it.
- The data holds rules that contradict AGENTS.md rule 9 ("Do not infer security properties"): `states.red.meaning` reads "The system's documentation says it does not hold, or the design rules it out", Weights hidden No reads "or the design gives the checker the weights", and No trusted party No reads "The check is a hardware attestation verified against a chip maker's keys", which names a kind of check rather than a statement.
- The data leaves owner decisions open "for the RFC": `risks` R1 (cap public-source rows), R2 (a system's own publication outside the pin) and R6 (fixed public parameters as a trusted input).
- The data uses two vocabularies for one thing: state keys `green`, `amber`, `red`, `grey` with labels "holds", "partly", "does not hold", "not stated" in `criteria.json`, and the words Yes, Partly, No, Not stated in `site.json` `glyph.inks.ladder`.
- Sourcing gaps (counted in [Migration / Rollout](#migration--rollout)): 13 Yes, Partly or No cells on public-source rows rest only on web quotes with no commit, no retrieval date and no stored copy; 65 Not stated cells carry no list of sources read, 53 of them reading "Not copied yet.". SASH's Whole output proved is Yes from a quote in `sg-ai-safety-hub/zk-inference-results`, a repository the SASH card does not accept as a source (`systems/sash/claim.yaml` L5 to L6, INV-CLAIM-3).
- Derived values are typed, not computed: `quote_check` holds a count (77 quotes) that no rule recomputes, while the quote objects in the file number 76 (71 in cells, 3 in `aside`, 2 in `outside_pin`).

Scenarios:

1. A reader sees SASH Not stated on Weights hidden and FlashProve Partly. They need to know that Not stated means the pinned sources are silent, not that SASH hides more.
2. A reviewer sets a public-source row to Yes from a blog post. A later reader needs to find the text that was read, as it read on the day, without trusting that the page has not changed.
3. A claim card changes `zero_knowledge.claimed` to `false`. The glyph must not keep saying Yes.
4. A reader adds the six states of two rows and compares the sums. The site must give them nothing to add.

## Goals

- Each of the six properties has a question, a not-covered note and a written rule for each of the four states ([Properties](#properties)).
- A state is set only from a quote of the documentation (for reference rows, RFC-0015), never from the benchmark's reading of a design (AGENTS.md rule 9).
- One state vocabulary: one id and one printed word per state.
- No total, score, count, average or order over states; no number on a property.
- For each row class, a named source of states; for card rows, the claim card fields each property reads and the mechanical bounds those fields set.
- A criteria file that validates under G2 with named rules, so CI catches a coloured cell without a deciding quote, a short commit, an unsourced Not stated cell and a card-row quote outside the card's pin.

## Non-Goals

- How the glyph is drawn: shapes, inks, contrast, slice geometry, motion. That is the site's (RFC-0009, amended by #319). This RFC fixes only the printed word of each state and that silence is never printed or drawn as No.
- The family vocabulary (`proved`, `re_executed`, `attested`, `fingerprinted`, `unchecked`) and which tab a row sits in, beyond [CRIT-12](#validation-rules-g2).
- The site data generator and the split of the site build (#320, #321).
- Claim cards for the 19 systems not benchmarked yet.
- System maintainer review of the SASH and FlashProve cards (#42).
- Judging whether a system's documentation is correct. The glyph reports what the documentation states, like the claim card it reads (RFC-0002 §Non-Goals).
- Running Last call for this RFC (RFC-0001 §RFC lifecycle rule 4). The bootstrap Last call (#24) covers only RFC-0001 to RFC-0015.

## Proposed Design

### Terms

- **Glyph**: the six-part figure the site draws for one row.
- **Property**: one of the six questions below, identified by its id.
- **Cell**: one property of one row: a state, our short reason, and quotes or a list of sources read.
- **Deciding quote**: the quote that sets a cell's state. Further quotes support it and set nothing.
- **Row class**: `claim_card_at_pin` (a system with a claim card), `reference_rfc_0015` (a reference row) or `public_sources` (a system not benchmarked yet).

### What the glyph is not

- INV-GLYPH-1. There is no total, score, rank, count, sum or average over states, across properties or across rows. No page, file or report computes one. The criteria file holds no key named `total`, `score`, `rank`, `count`, `sum`, `average`, `mean` or `weight` ([CRIT-10](#validation-rules-g2)).
- INV-GLYPH-2. Properties carry no numbers. The order of `order` is the clockwise display order and nothing else; it is not a priority or a weight. The criteria file holds no number-typed value at all. `site.json` `glyph.properties[].n`, `glyph.key.numbers` and the numbers in `aria` strings are dropped by the site generator (#320); until then `web/build.py` keeps stripping them (L969).
- INV-GLYPH-3. Security level shows only whether a level is stated and whether the documentation says it is proven. It never shows, compares or computes a level of its own; the level itself is a quote in the claim card (RFC-0002 `security.level`), and benchmark-assigned levels are rejected (RFC-0002 §Alternatives Considered).
- INV-GLYPH-4. Rows are never ordered by their states. Row order is set by the site (RFC-0009).

### States

One vocabulary, used in the criteria file and on every page. The site data adopts the ids with #320; until then the mapping in [Criteria file contract](#criteria-file-contract) applies.

| Id | Printed word | Meaning | Replaces |
|---|---|---|---|
| `yes` | Yes | The documentation says the property holds, by the property's Yes rule. | `green`, "holds" |
| `partly` | Partly | The documentation says it holds with a limit it states, by the property's Partly rule. | `amber`, "partly" |
| `no` | No | The documentation says it does not hold, by the property's No rule. | `red`, "does not hold" |
| `not_stated` | Not stated | The sources read say nothing that meets any of the three rules above, or they have not been read yet ([Q4](#open-questions)). | `grey`, "not stated" |

State rules, for every property:

- ST-1. A cell is `yes`, `partly` or `no` only when a deciding quote, copied verbatim from a source the row class allows ([Sources by row class](#sources-by-row-class)), meets that state's rule for the property.
- ST-2. Silence is `not_stated`, never `no`. If the sources read say nothing that meets a rule, the cell is `not_stated` and lists what was read.
- ST-3. `no` requires a statement that the property does not hold. A reviewer's reading of a design, a product category ("runs in an enclave") or an absent feature is not such a statement. Every "or the design rules it out" clause of the prototype is removed (AGENTS.md rule 9).
- ST-4. A document that says the system proves nothing and checks nothing says `no` for every property. A document that says the system proves nothing (but checks something, as recompute does) says `no` for Formally verified and Security level: there is no argument to machine-check and no soundness level.
- ST-5. Each stated limit is counted in one cell only. A limit counted in another cell is printed beside this one as an `aside` and does not change its state (for FlashProve, the clipped-gap policy is counted in Model bound and the one leaked bit in Weights hidden).
- ST-6. Trust and caveats every row shares do not change a state: the checker's own computer, compiler and verifier build; that the programs are tested rather than proved; which real, named model a commitment is. They are printed as text. Each property is judged for the protocol, as the documentation states it.
- ST-7. Public parameters fixed before the hash are shared by every non-interactive proof. They set `partly` on No trusted party only where the documentation says its proved statement excludes a provider who tuned them ([Q3](#open-questions)).
- ST-8. Where two quotes in the allowed sources conflict, the reviewer quotes both, the deciding quote is the one that states the narrower property, and the reason says that the sources conflict (as RFC-0002 §Failure modes does for cards).

### Properties

The six ids, in display order: `weights_hidden`, `model_bound`, `whole_output`, `formally_verified`, `security_level`, `no_trusted_party`. Each rule below is met only by what the documentation says (ST-1, ST-3).

#### Weights hidden (`weights_hidden`)

- Question: does the checker learn nothing about the weights?
- Not covered: hiding the weights from the host operator (an enclave) is not this property.
- Yes: the documentation says the weights stay hidden from the checker in the default use, naming no leak beyond public settings.
- Partly: the documentation says they are hidden with a stated limit: a named leak, hiding shown for one policy or setting only, or hiding optional per circuit.
- No: the documentation says the checker sees the weights, that hiding is off or not provided, or that nothing is checked (ST-4). The prototype clause "or the design gives the checker the weights" is removed; recompute's No rests on RFC-0015's statement that its verifier holds the weights.
- Not stated: no statement about hiding the weights from the checker in the sources read.

#### Model bound (`model_bound`)

- Question: is each checked token tied to the committed weights?
- Not covered: which real, named model the commitment is. FlashProve and SASH both say that stays outside their proof; it is printed as text.
- Yes: the documentation says a passing check ties each checked token to the committed weights exactly, in the configuration the row reads (the card's configuration for card rows; the default or expected use for other rows).
- Partly: tied with a stated limit: under one of several policies only, within a tolerance or bound, or shown only in empirical tests.
- No: the documentation says outputs are not tied to any weights, or that nothing is checked.
- Not stated: silent.

#### Whole output proved (`whole_output`)

- Question: does one check cover every output token of a request?
- Not covered: which requests get a proof (sampling, proving after the fact) is a deployment choice. The text before tokenizing and after detokenizing, which FlashProve and SASH both put outside their proof, is printed as text.
- Yes: the documentation says one check, or one joined set of checks, covers the prompt and every output token of a request.
- Partly: one check covers a stated part: the positions the client names, one segment, or one disputed step.
- No: the documentation says no output token is checked, or that nothing is checked.
- Not stated: silent, including a proved run whose output tokens the documentation does not name.

#### Formally verified (`formally_verified`)

- Question: is the security argument checked by a proof assistant?
- Not covered: whether the programs users run are proved. No row claims it; it is printed as text (ST-6).
- Yes: the documentation says the protocol's soundness is proved in a proof assistant (Lean, Coq, Isabelle or similar).
- Partly: machine-checked for a stated part only: one component, or a weaker statement than the one the system makes.
- No: the documentation says the argument is not machine-checked, that a machine check is planned only, or that its soundness evidence is review or tests and nothing else; or it says the system proves nothing (ST-4).
- Not stated: silent.

#### Security level (`security_level`)

- Question: is a soundness level stated, and proven?
- Not covered: the number itself, which is a quote in the claim card (INV-GLYPH-3); whether the programs a checker runs meet it, printed as text.
- Yes: the documentation states a numeric soundness bound and says it is proven, by hand or by machine, under named assumptions.
- Partly: a numeric level is stated but called conjectured, or stated only in code or configuration, or for part of the system.
- No: the documentation says the settings give no meaningful soundness (for example a test-only setting), or that the system proves nothing (ST-4).
- Not stated: no level stated.

#### No trusted party (`no_trusted_party`)

- Question: does a check hold without trusting a chip maker, a setup ceremony or an honest party?
- Not covered: trust every row shares (ST-6), and where the commitment or the weights come from (see Model bound).
- Yes: the documentation says the check rests on cryptography alone, needs no trusted setup, or is the checker's own rerun of the computation, and names no chip maker, setup or other party to trust. The rerun clause is new; it is the clause recompute's Yes meets (SRC-5).
- Partly: the documentation states a trusted input or condition that its proved statement does not cover: a setup file, public files the user must grant were fixed before the hash (ST-7), or one honest party among several.
- No: the documentation says the check verifies a hardware attestation against a chip maker's keys or certificate chain, or that the provider is trusted, or that nothing is checked. The quote MUST state the dependency; "runs in a trusted execution environment" alone does not (ST-3). This replaces the prototype rule, which named a kind of check.
- Not stated: silent.

### Sources by row class

#### Card rows (`claim_card_at_pin`)

- SRC-1. A card row names exactly one claim card by `card: {system, configuration, card_version}` (RFC-0002 §File and identity). Its states are for that card's configuration. A system with several cards in a release has one row per card. This settles R3: FlashProve's card is `exact-match-cp-verify` (issue #69 is closed), so its cells are read for exact match.
- SRC-2. Every quote of a card row, deciding, supporting or `aside`, is copied from the card's `upstream.repo` at the card's `upstream.commit`, the same rule INV-CLAIM-3 sets for the card ([Q5](#open-questions)). Its `sources_read` include that repository at that commit.
- SRC-3. A statement by the system outside the pin MAY be shown beside the cell as `outside_pin`, with its own state, reason and quotes. It never sets the cell's state ([Q2](#open-questions)).
- SRC-4. A reviewer sets each card-row state from quotes. The card fields in the table below bound the state mechanically ([CRIT-6](#validation-rules-g2)); where a bound fixes the state, the cell MUST carry that state ([Q6](#open-questions)).

Claim card fields each property reads (RFC-0002 §Fields):

| Property | Card fields read | Mechanical bound (CRIT-6) | Derivable from the card alone |
|---|---|---|---|
| Weights hidden | `zero_knowledge.claimed`, `.hidden`, `.not_hidden`, `.status`; `sources.zero_knowledge*` | `claimed: "not stated"` gives `not_stated`; `claimed: false` gives `no` | Partly: Not stated and No are; Yes against Partly needs a reading of `not_hidden` text |
| Model bound | `relation`, `coverage.policy.kind`, `coverage.policy.detail`, `binding`, `claim_class` | `policy.kind: tolerance` gives at most `partly`; `policy.kind: not_stated` with `binding: "not stated"` gives `not_stated` | Partly |
| Whole output proved | `coverage.unit`, `coverage.tokens_covered`, `coverage.phase`, `relation` | none: `tokens_covered` is free text | No |
| Formally verified | `relation_formal`, `security.notion.kind`, `security.notion.verifier`; `sources.security.notion*` | none: no card field records whether an argument is machine-checked | No |
| Security level | `security.level`, `security.notion.kind`, `security.model` | `level: "not stated"` gives `not_stated` | Partly: Not stated is; proven against conjectured needs the `level` text |
| No trusted party | `security.setup`, `assumptions`, `assumptions_not_stated`, `security.model.assumption` | `setup: trusted` gives at most `partly`; `setup: not_stated` with `assumptions_not_stated: true` gives `not_stated` | Partly |

The fields that set FlashProve's No trusted party are `assumptions` (its third item, `systems/flashprove/claim.yaml` L72 to L75, "Configuration files fixed before the hash function is drawn"), not `security.setup`, which reads `not_stated` (L43). A reviewer reads every field in the row, not only the obvious one.

RISK: Whole output proved and Formally verified cannot be bounded from the card, so a card change can leave them stale. Plan: [CRIT-5](#validation-rules-g2) ties every card-row quote to the card's commit, so a new pin (a new card, RFC-0002 §Configuration identity 1) fails CRIT-5 until every cell is re-read. A later RFC-0002 amendment MAY add a card field for machine-checked soundness.

#### Reference rows (`reference_rfc_0015`)

- SRC-5. Reference rows have no claim card (RFC-0015 §Reference systems: "they prove nothing"). RFC-0015 is their documentation. Every quote is from `rfcs/0015-reference-rows.md` in this repository at a full commit, and the states are the ones below ([CRIT-7](#validation-rules-g2)). A change to RFC-0015 that changes one of these states MUST amend this table in the same pull request.

| Property | Plain serving (`ref-serve`) | Recompute (`ref-recompute`) | RFC-0015 text it rests on |
|---|---|---|---|
| Weights hidden | No (ST-4) | No | plain serving: §Reference systems "they prove nothing"; recompute: §Recompute "A verifier holding the weights checks a claimed output by running the model itself." |
| Model bound | No (ST-4) | Yes (SRC-6) | plain serving: SRV-4 (serving outputs are recorded and not compared); recompute: PM-0 and RC-3 |
| Whole output proved | No (ST-4) | Yes | plain serving: §Summary (the model served unproved); recompute: RC-3 (one forward pass over prompt plus every claimed output token) |
| Formally verified | No (ST-4) | No (ST-4) | §Reference systems "they prove nothing" |
| Security level | No (ST-4) | No (ST-4) | §Reference systems "they prove nothing" |
| No trusted party | No (ST-4) | Yes | plain serving: §Summary; recompute: §Recompute (the checker reruns the model itself) |

- SRC-6. These states describe the method as RFC-0015 documents it, not a measurement. A recompute configuration that declares a precision substitution (RFC-0015 PM-2) is `partly` on Model bound, because the rerun uses another precision than the workload's. A configuration marked `not_measurable_on_profile` (RFC-0015 NM-1) keeps its states, and the row prints the NM-1 reason (settles R8). The table gives the states of a configuration with no declared substitution. Today `systems/ref-recompute/system.yaml` declares one on both SASH workloads (FP8 W8A8 for the workload's INT8 W8A8, RFC-0015 Resolved Q1 and PM-4) and none on the two Maverick workloads, so the criteria file's single recompute row, which the site shows on Maverick, keeps Yes; where a page shows a SASH-workload recompute configuration, its Model bound is `partly`.
- SRC-7. A reference row's `no` on Formally verified and Security level means "no security argument, by definition" and its reason says so. No fifth state ("does not apply") is added (settles R14; one vocabulary of four states).

#### Public-source rows (`public_sources`)

- SRC-8. States come from public quotes: the system's repository at a full commit, or a web page. These rows are drawn apart from card and reference rows and are never in the benchmarked tab ([CRIT-12](#validation-rules-g2)). How the site marks them (the prototype's "pencil") is the site's (#319).
- SRC-9. A web quote carries, in place of a commit: the `url`, a `retrieved` date (`"YYYY-MM-DD"`, RFC-0012 dates), and either an `archive_url` (a snapshot in a public web archive taken on or after the retrieved date) or a `copy` (a path in this repository holding the retrieved text, with its sha256). A web quote without these sets no state ([CRIT-3](#validation-rules-g2)).
- SRC-10. A public-source row is not capped below Yes ([Q1](#open-questions)).

### Criteria file contract

The file stays at `web/_data/criteria.json`, authored JSON in the RFC-0012 canonical form (G3 `FMT-1`). Its schema is `schema/criteria/1.schema.json`, `$id` `https://inference-proofs.org/schema/criteria/1.schema.json`, Draft 2020-12, with `"schema": {"const": "criteria/1"}`.

RFC-0012 §Schema catalogue row, added by the implementing pull request:

| Name | File | Kind | Path of instances | Owner RFC |
|---|---|---|---|---|
| `criteria` | `schema/criteria/1.schema.json` | authored JSON | `web/_data/criteria.json` | RFC-0016 |

RFC-0013 §G2 inputs gain `web/_data/criteria.json` (and `G2_GLOBS` in `harness/src/iproofs/validate/tree.py`); the `CRIT-n` rules join the G2 cross-document checks.

Shape only (every object `additionalProperties: false`; `Text` is a non-empty string; `{}` stands for the same fields as `yes`):

```json
{
  "schema": "criteria/1",
  "rfc": "RFC-0016",
  "date": "YYYY-MM-DD",
  "note": "Text",
  "order": ["weights_hidden", "model_bound", "whole_output", "formally_verified", "security_level", "no_trusted_party"],
  "states": {"yes": {"word": "Yes", "meaning": "Text"}, "partly": {}, "no": {}, "not_stated": {}},
  "properties": [
    {"id": "weights_hidden", "name": "Weights hidden", "question": "Text", "not_here": "Text",
     "rules": {"yes": "Text", "partly": "Text", "no": "Text", "not_stated": "Text"},
     "card_fields": ["zero_knowledge.claimed", "zero_knowledge.hidden"]}
  ],
  "pins": {"owner/repo": "<40-hex>"},
  "rows": [
    {"id": "sash", "name": "Text", "family": "proved", "tab": "benchmarked",
     "source_class": "claim_card_at_pin",
     "card": {"system": "sash", "configuration": "sound-defaults", "card_version": "1"},
     "cells": {"weights_hidden": {"state": "not_stated", "reason": "Text", "quotes": [],
                                  "sources_read": [{"repo": "owner/repo", "commit": "<40-hex>", "paths": ["README.md"]}],
                                  "note": "Text", "outside_pin": {"state": "partly", "reason": "Text", "quotes": []}}}}
  ]
}
```

- `card_version` is a string of digits here, because the file holds no number-typed value (INV-GLYPH-2, CRIT-10); CRIT-5 compares it with the card's integer.
- `rfc` names this RFC. The file carries no status: the site reads the status line of `rfcs/0016-*.md`, so a status change stays a two-file pull request (RFC-0001 §RFC lifecycle rule 4). The label "Draft criteria, needs an RFC" changes only when this RFC is Accepted.
- Quote, one of three kinds. All carry `kind`, `text` (verbatim), `label`, `decides` (boolean) and `checked: true` with `checked_how` (Text). `repository` and `this_repository` add `repo`, `commit` (40-hex), `path`, `lines` (`^L[0-9]+(-L[0-9]+)?$`) and `url` (containing `commit`). `web` adds `url`, `retrieved`, and `archive_url` or `copy: {path, sha256}`. The prototype kind `ours` becomes `this_repository`.
- `sources_read` entry: `{repo, commit, paths}` for a repository (paths or globs read) or `{url, retrieved}` for a web page.
- `not_copied: true` MAY replace `sources_read` on a `not_stated` cell of a public-source row ([Q4](#open-questions)).
- Removed from the prototype, each for a reason: `test_mapping`, `rows[].states` and `rows[].pencil` (derived from the cells and `source_class`; derived values are computed, not typed); `quote_check` (a typed count that no rule recomputes); `contrast` and `states.*.fill`, `.ink`, `.mark` (drawing, the site's; `site.json` already holds the inks it uses); `status` (read from the RFC); `this_repository_commit` (moves into `pins`); `rules` and `risks` (now this RFC's normative text and dispositions).
- `web/build.py` L41 to L44 keeps its check by mapping each cell's state id to the `site.json` key (`yes` to `green`, `partly` to `amber`, `no` to `red`, `not_stated` to `grey`) until #320 renames the site keys.

### Validation rules (G2)

Each failure is a G2 finding with the rule id and the JSON pointer of the cell or quote. Shape failures (unknown state, unknown key, a number, a missing required field) are schema failures under the generic G2 rule. Semantic rules:

| Id | Rule | Error kind |
|---|---|---|
| `CRIT-1` | A `yes`, `partly` or `no` cell has at least one quote; its first quote has `decides: true` and no other quote does. Every quote has `checked: true`. | `config` |
| `CRIT-2` | A `repository` or `this_repository` quote has a 40-hex `commit` equal to `pins[repo]`, and its `url` contains that commit. Every `pins` entry is used by a quote or a `sources_read` entry. | `integrity` |
| `CRIT-3` | A `web` quote has an https `url`, a `retrieved` date not after the file's `date`, and an `archive_url` or a `copy` whose file exists and whose sha256 matches. | `integrity` |
| `CRIT-4` | A `not_stated` cell has no quote with `decides: true`, and exactly one of a non-empty `sources_read` or `not_copied: true`. `not_copied` appears only on public-source rows. | `config` |
| `CRIT-5` | A card row names a card that exists (`systems/<system>/claim.yaml` or `claims/<configuration>.yaml`) with that `card_version`. Every quote outside `outside_pin` is in the card's `upstream.repo` at `upstream.commit`, and `sources_read` of each `not_stated` cell includes that repository at that commit. | `integrity` |
| `CRIT-6` | A card row's state meets every mechanical bound of the [card fields table](#card-rows-claim_card_at_pin). If [Q6](#open-questions) resolves to derived states, this rule recomputes each card-row state from the card and fails on any difference. | `integrity` |
| `CRIT-7` | A reference row's quotes are all `this_repository` quotes of `rfcs/0015-reference-rows.md`, and its states equal the [reference table](#reference-rows-reference_rfc_0015), with SRC-6 applied. | `integrity` |
| `CRIT-8` | The text of each `this_repository` quote occurs, whitespace-normalised, in `git show <commit>:<path>` at its `lines`. CPU only, no network. | `integrity` |
| `CRIT-9` | `order` equals the six ids of [Properties](#properties) in that order; `properties` holds exactly those ids in that order; every row has exactly those six cells; row ids are unique. | `config` |
| `CRIT-10` | No JSON number anywhere in the file, and no key named `total`, `score`, `rank`, `count`, `sum`, `average`, `mean` or `weight` (case-insensitive) at any depth. | `config` |
| `CRIT-11` | `outside_pin` appears only on card rows; its quotes have `decides: false`; its state is one of the four ids. | `config` |
| `CRIT-12` | A public-source row has `tab` `not_benchmarked` or `archived`; a card or reference row has `tab` `benchmarked`. | `config` |

Upstream quotes (kind `repository` outside this repository, and `web`) are checked against their source by the reviewer, recorded in `checked_how`. CI does not fetch them (RFC-0012: validators never use the network).

### Data flow and lifecycle

1. A reviewer edits `web/_data/criteria.json` by pull request, quoting sources at the commits the row class allows.
2. `iproofs validate` runs G2 (schema and `CRIT-1` to `CRIT-12`) and G3 on it.
3. A claim card change (a new `card_version`) fails `CRIT-5` on that row until the row names the new version, so every card change forces a re-read of its row.
4. `web/build.py` reads the states from the cells; the footer pins the file's sha256 as it does today.

Determinism: the rules read only the file, the claim cards and git objects of this repository. No clock and no network.

### Failure modes

| Failure | Response |
|---|---|
| A coloured cell without a deciding quote | `CRIT-1` fails |
| A quote at a short or unpinned commit | `CRIT-2` fails |
| A web page changed or removed after it was quoted | the `archive_url` or `copy` still holds the text read; the cell stands until a reviewer re-reads it |
| A web quote with no archive and no copy | `CRIT-3` fails; the cell becomes `not_stated` with the url in `sources_read`, or gains an archive |
| A Not stated cell with nothing recorded | `CRIT-4` fails |
| A card-row quote from another repository or commit | `CRIT-5` fails; the quote moves to `outside_pin` or is replaced from the pin |
| A card change contradicts a cell (for example `zero_knowledge.claimed` becomes `false` while the cell is `yes`) | `CRIT-6` fails |
| RFC-0015 edited so a reference quote no longer reads at its lines | the quote's commit still holds it (`CRIT-8` reads git objects); a state change needs this RFC's table amended (SRC-5) |
| A reviewer's inference used as a deciding quote | review catches it (ST-3); the quote's text must be the system's own words, which `CRIT-8` checks for this repository's quotes |
| A score, count or number added to the file | `CRIT-10` fails |

## Alternatives Considered

- **Keep the design clauses ("or the design rules it out").** Considered because some designs make a property impossible on their face (a recompute verifier must hold the weights). Rejected: it lets the benchmark state a security property the system does not state, against AGENTS.md rule 9, and every case in the data today has a documented statement that serves instead (recompute's rests on RFC-0015).
- **Derive every card-row state from card fields.** Considered because CI could then recompute the glyph and no reviewer judgement would remain. Rejected as the default ([Q6](#open-questions)): Whole output proved and Formally verified have no field to derive from, and Yes against Partly on three other properties depends on free text. The mechanical bounds keep the part that can be derived.
- **A fifth state, "does not apply", for reference rows.** Considered in R14. Rejected: one vocabulary of four states, and a `no` with the reason "no security argument, by definition" says the same thing.
- **A score per row, or a count of Yes.** Rejected: the benchmark measures and does not rank ([PRD §5](../docs/PRD.md#5-non-goals)); a count would weigh six unlike properties as equal.
- **Benchmark-assigned security levels on the glyph.** Rejected by RFC-0002 §Alternatives Considered: it is certification, a non-goal, and it rounds away the exact form.
- **Accept web quotes with a URL only.** Considered because the prototype does. Rejected: pages change, and a state must be checkable against the text read.
- **Move the criteria file out of `web/` (for example to `methodology/criteria.json`).** Considered because the file is methodology, not presentation. Rejected for now: `web/build.py` and the footer read it at its path, and moving it is churn with no change in meaning; #320 MAY move it with the generator.

## Drawbacks

- Re-reading is costly: every card change and every web quote needs a reviewer, and 65 Not stated cells need a list or a marker before the file validates.
- A thorough system collects Partly while a silent one shows Not stated (R1, R11). This RFC keeps that, because it is what the documentation says; the site has to explain that Not stated is not No.
- A rule that a No needs a statement will move some cells from No to Not stated (candidates in [Migration / Rollout](#migration--rollout)), so the glyph shows less than a reader of the design might expect.
- Two properties stay reviewer-set for card rows, with no mechanical check beyond the commit pin.

## Conflicts of Interest

The author's affiliation and any interest in a measured system are to be declared in `MAINTAINERS.md` before this RFC enters Last call (RFC-0001); the author is not yet listed there. This text was drafted with an AI agent, Claude, made by Anthropic. Anthropic publishes FlashProve (`anthropics/FlashProve`), one of the two systems with a card row. Reviewers should weigh the decisions that move FlashProve cells (SRC-1 on R3, ST-7 and Q3 on R6) with that in mind.

## Migration / Rollout

Two pull requests, in order (issue #318). This one adds the RFC and its index rows only. The second opens once this RFC is in Last call and merges only once it is Accepted (RFC-0001 §RFC lifecycle rule 3, INV-GOV-3). It adds the schema and examples, the `CRIT-n` rules, `harness/tests/unit/test_criteria.py`, the RFC-0012 catalogue row and the RFC-0013 G2 input, rewrites `web/_data/criteria.json` to `criteria/1`, and updates `web/README.md` (§Open and the criteria text) and `docs/spec/10-glossary.md` (the six properties and four states). Its description lists every state that changes, by row, and every cell edited to pass the new rules.

Counts in the committed file (sha256 starting `4ced468b`, at `356949a5ee8afe328ee2cb0d68b18be1b1d82453`), recomputed by:

```sh
python3 -I -c 'import json;d=json.load(open("web/_data/criteria.json"));c=[(r,c) for r in d["rows"] for c in r["cells"].values()];print(sum(1 for r,x in c if x["state"]!="grey" and x["quotes"] and all(q["kind"]=="web" for q in x["quotes"])), sum(1 for r,x in c if x["state"]=="grey" and not x.get("searched")))'
```

which prints `13 65`. Of 138 cells (23 rows of 6): card rows 4 Yes, 5 Partly, 3 Not stated; reference rows 3 Yes, 9 No; public-source rows 14 Yes, 7 Partly, 3 No, 90 Not stated.

What fails the new rules, and what the second pull request does:

1. Key and field renames, no state change: `green`, `amber`, `red`, `grey` to `yes`, `partly`, `no`, `not_stated`; `searched` to `sources_read` (28 cells, entries turned into objects); quote kind `ours` to `this_repository` (20 quotes); removed fields as in [Criteria file contract](#criteria-file-contract); `pins` gains this repository and the 6 public-source repositories quoted (`CRIT-2`).
2. 13 coloured cells whose only quotes are web quotes fail `CRIT-3`: Attestable Weights hidden, Model bound, Whole output proved, No trusted party; NanoZK, zkGPT, zkLLM, ZKML, zkPyTorch and ZKTorch Weights hidden; Tinfoil No trusted party; TOPLOC Model bound; Verde No trusted party. In all, 20 web quotes lack a retrieval date and a stored copy (these 13, one supporting quote on DeepProve Whole output proved, 4 context quotes in Not stated cells, 2 SASH `outside_pin` quotes). Each gains `retrieved` and an `archive_url` or `copy`; a page that cannot be retrieved again sets its cell to `not_stated` with the url in `sources_read`.
3. 65 Not stated cells, all on public-source rows, have no sources-read list and fail `CRIT-4`. The 53 reading "Not copied yet." take `not_copied: true` (under Q4's default). The other 12 have reasons that name what was read (for example "Proves a graph run; output tokens not named."); each gains a `sources_read` list, or `not_copied: true` if the source read cannot be named.
4. SASH Whole output proved (Yes) fails `CRIT-5`: its deciding quote is `docs/statement-gap.md` L3 to L7 in `sg-ai-safety-hub/zk-inference-results` at `11decec3`. Under Q5's default the reviewer re-reads `sg-ai-safety-hub/zk-inference-prover` at `eb95bfa8` (the card's own `coverage.tokens_covered` source, `prover/src/boundary.rs` L1148 to L1156, and the supporting quote `docs/statement.md` L5 to L7) and sets a deciding quote from there, or Not stated. The 15 `searched` entries in the results repository on SASH cells stay as sources read.
5. Cells to re-read under the new rules, outcome not decided here, each listed with its result in the second pull request: FlashProve Model bound and Whole output proved, against the `exact-match-cp-verify` card (SRC-1; the current Model bound reason rests on the expected use, which checks only the client's limits, not on the exact-match configuration the card runs); SASH No trusted party, against the first item of the card's `assumptions` ("produced at setup, trusted by the verifier", `prover/src/compose.rs` L5 to L11), which the cell does not cite; Tinfoil and Private ML SDK No trusted party, under the rewritten No rule; the 8 public-source Weights hidden Yes cells (Attestable, NanoZK, VerInf, zkGPT, zkLLM, ZKML, zkPyTorch, ZKTorch), for whether each quote says hidden from the checker (R10); VerInf Formally verified and Whole output proved (R13).
6. Card rows meet every `CRIT-6` bound today: SASH Weights hidden is Not stated with `zero_knowledge.claimed: "not stated"`, and no other bound applies to either card.
7. Reference rows: all 20 quotes are at `fbe1f9c798ac9a2865dca086954de5e8a20c91d7`, and each reads verbatim at its lines (checked by the author with `git show`, as `CRIT-8` will). States equal the reference table; no change.
8. `site.json` `glyph.rows[*].states` changes with every state that changes, so `web/build.py` L41 to L44 holds; `site.json` keeps its old keys until #320.

Dispositions of the prototype's risks:

| Risk | Disposition |
|---|---|
| R1 cap public-source rows | Q1, default no cap |
| R2 publication outside the pin | Q2, default shown beside the cell, sets nothing (SRC-3) |
| R3 FlashProve Model bound by policy | settled by SRC-1 (state per card configuration) |
| R4 one Lean fact, two cells | kept: the two rules differ (a hand-proved bound is Yes for Security level and not for Formally verified) |
| R5 SASH "conjectured" | kept: the word is SASH's own |
| R6 fixed public parameters | Q3, default option (b) (ST-7) |
| R7 plain serving No on Weights hidden | kept: ST-4, the reason says "no checker, so nothing to hide from" |
| R8 recompute by configuration | settled by SRC-6 |
| R9 FlashProve short replies | kept: the reason names the limit |
| R10 zkPyTorch product page | re-read in the second pull request (item 5) |
| R11 mostly Not stated rows | accepted: that is what the sources say |
| R12 inks | out of scope: drawing (#319) |
| R13 VerInf | re-read in the second pull request (item 5) |
| R14 recompute has no argument | settled by ST-4 and SRC-7 |

No past results exist; no release has shown a glyph. No claim card changes. No schema version changes other than the new `criteria/1`.

## Testing Strategy

Schema examples in `schema/criteria/examples/` (every invalid example with a `.reason` file):

- `valid/committed-shape.json`: one card row, one reference row and one public-source row in the committed file's shape; passes.
- `valid/not-copied.json`: a public-source `not_stated` cell with `not_copied: true`; passes.
- `valid/web-quote-archived.json`: a Yes cell whose deciding quote is a web quote with `retrieved` and `archive_url`; passes.
- `invalid/state-outside-four.json`: a cell with `state: "green"`; fails on enum.
- `invalid/property-number.json`: a property with `"n": 1`; fails on `additionalProperties` (and `CRIT-10`).
- `invalid/total-key.json`: a top-level `total`; fails on `additionalProperties`.
- `invalid/score-key.json`: a row with `score`; fails on `additionalProperties`.
- `invalid/web-quote-no-retrieved.json`: a web quote without `retrieved`; fails on `required`.
- `invalid/short-commit.json`: a repository quote with `commit: "9e2bdd8f"`; fails on pattern.
- `invalid/missing-rule.json`: a property whose `rules` lacks `not_stated`; fails on `required`.

Unit tests, `harness/tests/unit/test_criteria.py`, each on a hand-made file:

- `test_yes_cell_without_quote_fails` (`CRIT-1`).
- `test_first_quote_must_decide` (`CRIT-1`): a Partly cell whose first quote has `decides: false` fails.
- `test_repository_quote_short_commit_fails` (`CRIT-2`).
- `test_quote_commit_differs_from_pin_fails` (`CRIT-2`).
- `test_web_quote_without_archive_or_copy_fails` (`CRIT-3`).
- `test_web_copy_hash_mismatch_fails` (`CRIT-3`).
- `test_not_stated_without_sources_or_marker_fails` (`CRIT-4`).
- `test_not_copied_on_card_row_fails` (`CRIT-4`).
- `test_card_quote_outside_card_repository_fails` (`CRIT-5`): a SASH cell deciding from `sg-ai-safety-hub/zk-inference-results` fails.
- `test_card_quote_at_other_commit_fails` (`CRIT-5`).
- `test_card_version_mismatch_fails` (`CRIT-5`).
- `test_card_bound_zero_knowledge_not_stated` (`CRIT-6`): `zero_knowledge.claimed: "not stated"` with Weights hidden `yes` fails; with `not_stated` passes.
- `test_card_bound_level_not_stated` (`CRIT-6`): `security.level: "not stated"` with Security level `partly` fails.
- `test_card_bound_trusted_setup` (`CRIT-6`): `security.setup: trusted` with No trusted party `yes` fails.
- `test_reference_state_differs_from_table_fails` (`CRIT-7`).
- `test_reference_table_matches_rfc` (`CRIT-7`): the validator's table equals the table in this RFC, parsed from the markdown.
- `test_this_repository_quote_not_at_lines_fails` (`CRIT-8`), on a temporary git repository.
- `test_number_anywhere_fails` and `test_aggregate_key_fails` (`CRIT-10`).
- `test_order_differs_fails` (`CRIT-9`).
- `test_outside_pin_on_public_row_fails` (`CRIT-11`).
- `test_public_row_in_benchmarked_tab_fails` (`CRIT-12`).
- `test_committed_file_passes`: `web/_data/criteria.json` passes every rule.

Repository checks: `iproofs validate --all`; `pytest harness/tests/unit/test_criteria.py harness/tests/unit/test_rfc_status.py`; `cd web && python3 -I build.py`, then `git status --porcelain -- web` prints nothing.

## Open Questions

"RFC Last call" below means the Last call of this RFC.

- OPEN QUESTION Q1 (owner: 0xchqrles, resolve by: RFC Last call): should public-source rows be capped at Partly (R1)? Default until resolved: no cap (SRC-10). Reason: a cap prints Partly where the documentation states no limit, a state that comes from the benchmark rather than the source (AGENTS.md rule 9). The thoroughness gap is met instead by drawing public-source rows apart (SRC-8) and by web quotes that carry what was read (SRC-9).
- OPEN QUESTION Q2 (owner: 0xchqrles, resolve by: RFC Last call): may a system's own dated publication outside the pin set a card row's state (R2)? Default until resolved: no; it is shown beside the cell as `outside_pin` with its own state and quote, and sets nothing (SRC-3). Reason: a card row's sources sit at the card's commit (INV-CLAIM-3), so the glyph and the card it reads say the same thing; a web page has no commit and can change. SASH can be asked to state it in the repository (#42).
- OPEN QUESTION Q3 (owner: 0xchqrles, resolve by: RFC Last call): do public parameters fixed before the hash count as a trusted input (R6)? Option (a) treats them as a shared caveat printed as text; option (b) sets Partly only where the documentation says its proved statement excludes a provider who tuned them. Default until resolved: (b) (ST-7). Reason: it copies a condition the documentation states ("that you grant", FlashProve `guide/what-is-proved.md` L288 to L289 at `9e2bdd8f`); (a) would drop a stated condition. The cost is that a system which states the condition shows Partly while one that does not shows Not stated; the reason text says so, and other teams are invited to state their assumptions.
- OPEN QUESTION Q4 (owner: 0xchqrles, resolve by: RFC Last call): does "not copied yet" stay a Not stated case, or does the site show it apart from silence? Default until resolved: it stays the state `not_stated` (four states only) and the cell carries `not_copied: true`, so the data tells "not read yet" from "read and silent" (CRIT-4); the printed word stays "Not stated", and whether a page prints the difference is the site's (#319). Reason: printing both the same way would claim sources were read that were not, and a fifth state was rejected (SRC-7).
- OPEN QUESTION Q5 (owner: 0xchqrles, resolve by: RFC Last call): may a card row quote the SASH companion repository `sg-ai-safety-hub/zk-inference-results`? Default until resolved: no; a card row quotes only the card's `upstream.repo` at `upstream.commit` (SRC-2). Reason: the SASH card already refuses that repository as a source (`systems/sash/claim.yaml` L5 to L6, INV-CLAIM-3), and one source rule for the card and the glyph keeps them from disagreeing. The alternative is an RFC-0002 amendment that lets a card name companion repositories at full commits, after which SRC-2 would follow it.
- OPEN QUESTION Q6 (owner: 0xchqrles, resolve by: RFC Last call): are card-row states derived from card fields, or set by a reviewer from quotes? Default until resolved: set by a reviewer from quotes, within the mechanical bounds of the card fields table (SRC-4, CRIT-6). Reason: two properties have no card field to derive from and three need a reading of free text; derivation would need RFC-0002 fields that do not exist. If resolved to derived, CRIT-6 recomputes every card-row state from the card.

## References

- [RFC-0001](0001-process-and-governance.md) §Changes to methodology, §RFC lifecycle, §Conflicts of interest.
- [RFC-0002](0002-claim-card.md) §Fields, §Rules (INV-CLAIM-2, INV-CLAIM-3), §Configuration identity, §Alternatives Considered.
- [RFC-0009](0009-results-and-publication.md) for the site; its amendment for the live site is #319.
- [RFC-0012](0012-schemas-and-serialization.md) §Schema catalogue, §The `schema` field, §YAML subset for authored files (dates), §JSON writer.
- [RFC-0013](0013-validation-and-ci.md) §G2 Schema validation, §G3 JSON format check.
- [RFC-0015](0015-reference-rows.md) §Reference systems, §Plain serving, §Recompute, §Precision matching, §Feasibility on the profile.
- AGENTS.md hard rules 3, 9 and 10.
- `web/_data/criteria.json` (prototype criteria, sha256 starting `4ced468b`), `web/_data/site.json` `glyph`, `web/build.py` L41 to L44 and L969, `web/README.md` §Data.
- `systems/flashprove/claim.yaml` and `systems/sash/claim.yaml`, card version 1 each.
- FlashProve at `9e2bdd8ff5bf9c62f18263d7dac189b0400b260c`; SASH zk-inference-prover at `eb95bfa887299d1637550228d42086c27cbb2b3b`; SASH zk-inference-results at `11decec3c0b62c707618aab5deb82750b355d202`.
- Issues #318 (this RFC), #319, #320, #321, #42, #69.
