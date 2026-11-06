# RFC-0016: Glyph properties and states

- Status: Draft
- Authors: 0xchqrles (affiliation to be declared in `MAINTAINERS.md`)
- Created: 2026-11-07
- Target milestone: v0.1
- Requires: RFC-0001, RFC-0002, RFC-0012, RFC-0013, RFC-0015
- Supersedes: none
- Discussion: https://github.com/ai-verification-observatory/inference-proofs/issues/318

## Summary

The public site draws every row as a glyph: six properties (Weights hidden, Model bound, Whole output checked, Formally verified, Security level, No trusted party), each in one of four states, printed Yes, Partly, No and Not stated. Today the rules behind those states exist only as prototype data in `web/_data/criteria.json`, whose own `status` reads "draft criteria, prototype only, needs an RFC (RFC-0001)". This RFC makes them normative. It fixes each property's question, what it does not cover and the rule for each state; one state vocabulary; that there is no total, score, count or order over states and no number on a property; the source of a state for each row class (claim card rows, reference rows, public-source rows); that a card row is read for its card's configuration and quotes only the card's pin; what a web quote carries in place of a commit, and that it comes from the system's own authors; and the contract of the criteria file (`schema: "criteria/1"`, its schema, its G2 rules `CRIT-1` to `CRIT-12` and their tests), which a second pull request implements once this RFC is Accepted. A glyph state is a label printed on every row, so RFC-0001 §Changes to methodology requires this RFC.

## Motivation

Evidence, all at this repository's commit `356949a5ee8afe328ee2cb0d68b18be1b1d82453` unless stated:

- No RFC and no section of `docs/spec/` names the six properties. The pages print "Draft criteria, needs an RFC" (`web/_data/site.json` `glyph.legend.draft_short`).
- The states are set by hand. A pipeline outside this repository wrote the data (`site.json` `generated_by: prototypes/v7/_data/make_site_data.py`). `web/build.py` reads no claim card; it only asserts that `site.json` `glyph.rows[*].states` equals `criteria.json` `test_mapping` (L41 to L44). Nothing checks a state against `systems/flashprove/claim.yaml` or `systems/sash/claim.yaml`. `criteria.json` has no `schema` field, and no RFC-0013 §G2 input glob covers it.
- The data holds rules that contradict AGENTS.md rule 9 ("Do not infer security properties"): `states.red.meaning` reads "The system's documentation says it does not hold, or the design rules it out", Weights hidden No reads "or the design gives the checker the weights", and No trusted party No reads "The check is a hardware attestation verified against a chip maker's keys", which names a kind of check rather than a statement.
- The data reads FlashProve's Formally verified and Security level from statements its documentation makes for the Lean verifier `verify`, while FlashProve's card is the configuration that runs the C++ verifier `cp_verify`, and the card says that neither the formal statement nor the level is stated for it (`systems/flashprove/claim.yaml` L22 and L26 to L37).
- The data leaves owner decisions open "for the RFC": `risks` R1 (cap public-source rows), R2 (a system's own publication outside the pin) and R6 (fixed public parameters as a trusted input).
- The data uses two vocabularies for one thing: state keys `green`, `amber`, `red`, `grey` with labels "holds", "partly", "does not hold", "not stated" in `criteria.json`, and the words Yes, Partly, No, Not stated in `site.json` `glyph.inks.ladder`.
- Sourcing gaps (counted in [Migration / Rollout](#migration--rollout)): 13 Yes, Partly or No cells on public-source rows rest only on web quotes with no commit, no retrieval date and no stored copy; 65 Not stated cells carry no list of sources read, 53 of them reading "Not copied yet.". SASH's Whole output proved is Yes from a quote in `sg-ai-safety-hub/zk-inference-results`, a repository the SASH card does not accept as a source (`systems/sash/claim.yaml` L5 to L6, INV-CLAIM-3).
- Derived values are typed, not computed: `quote_check` holds a count (77 quotes) that no rule recomputes. It matches the file today (71 in cells, 4 in `aside`, 2 in `outside_pin`), but nothing would catch it drifting.

Scenarios:

1. A reader sees SASH Not stated on Weights hidden and FlashProve Partly. They need to know that Not stated means the pinned sources are silent, not that SASH hides more.
2. A reviewer sets a public-source row to Yes from a post on the system's own blog. A later reader needs to find the text that was read, as it read on the day, without trusting that the page has not changed.
3. A claim card changes `zero_knowledge.claimed` to `false`. The glyph must not keep saying Yes.
4. A reader adds the six states of two rows and compares the sums. The site must give them nothing to add.

## Goals

- Each of the six properties has a question, a not-covered note and a written rule for each of the four states ([Properties](#properties)).
- A state on a system's row is set only from a quote of that system's own documentation, never from the benchmark's reading of a design (AGENTS.md rule 9). A reference row's states are set by RFC-0015 and this RFC, which document the benchmark's own methods.
- One state vocabulary: one id and one printed word per state. The four states are unordered.
- No total, score, count, average or order over states; no number on a property.
- For each row class, a named source of states; for card rows, the claim card fields each property reads and the states those fields allow.
- A criteria file that validates under G2 with named rules, so CI catches a coloured cell without a deciding quote, a short commit, an unsourced Not stated cell and a card-row quote outside the card's pin.

## Non-Goals

- How the glyph is drawn: shapes, inks, contrast, slice geometry, motion. That is the site's (RFC-0009, amended by #319), within INV-GLYPH-1. This RFC fixes only the printed word of each state and that silence is never printed or drawn as No.
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
- **Own source**: a repository, a domain or a published paper of the system's own authors, listed on a public-source row ([SRC-8](#public-source-rows-public_sources)).

### What the glyph is not

- INV-GLYPH-1. There is no total, score, rank, count, sum or average over states, across properties or across rows. No page, file or report computes one. The criteria file holds no key named `total`, `score`, `rank`, `count`, `sum`, `average`, `mean` or `weight` ([CRIT-10](#validation-rules-g2)). No drawing encodes a state by an amount of fill or area that adds up across properties; each state is told apart by ink or pattern. The shapes themselves are the site's (#319).
- INV-GLYPH-2. Properties carry no numbers. The order of `order` is the clockwise display order and nothing else; it is not a priority or a weight. The criteria file holds no number-typed value at all. `site.json` `glyph.properties[].n`, `glyph.key.numbers` and the numbers in `aria` strings are dropped by the site generator (#320); until then `web/build.py` keeps stripping them (L969).
- INV-GLYPH-3. Security level shows only whether a level is stated and whether the documentation says it is proven. It never shows, compares or computes a level of its own; the level itself is a quote in the claim card (RFC-0002 `security.level`), and benchmark-assigned levels are rejected (RFC-0002 §Alternatives Considered).
- INV-GLYPH-4. Rows are never ordered by their states. Row order is set by the site (RFC-0009).

### States

One vocabulary, used in the criteria file and on every page. The site data adopts the ids with #320; until then the mapping in [Criteria file contract](#criteria-file-contract) applies. The four states are unordered: none counts as more or less than another, and no rule in this RFC compares two states except ST-8, inside one cell.

| Id | Printed word | Meaning | Replaces |
|---|---|---|---|
| `yes` | Yes | The documentation says the property holds, by the property's Yes rule. | `green`, "holds" |
| `partly` | Partly | The documentation says it holds with a limit it states, by the property's Partly rule. | `amber`, "partly" |
| `no` | No | The documentation says it does not hold, by the property's No rule. | `red`, "does not hold" |
| `not_stated` | Not stated | The sources read say nothing that meets any of the three rules above, or they have not been read yet ([Q2](#open-questions)). | `grey`, "not stated" |

State rules, for every property:

- ST-1. A cell is `yes`, `partly` or `no` only when a deciding quote, copied verbatim from a source the row class allows ([Sources by row class](#sources-by-row-class)), meets that state's rule for the property. Reference rows follow SRC-5 instead.
- ST-2. Silence is `not_stated`, never `no`. If the sources read say nothing that meets a rule, the cell is `not_stated` and lists what was read.
- ST-3. `no` requires a statement that the property does not hold. A reviewer's reading of a design, a product category ("runs in an enclave") or an absent feature is not such a statement. Every "or the design rules it out" clause of the prototype is removed (AGENTS.md rule 9).
- ST-4. On a reference row only, a method that proves nothing and checks nothing (plain serving) is `no` on every property, and a method that proves nothing but checks (recompute) is `no` on Formally verified and Security level (SRC-7). On a card or public-source row, a statement that the system proves nothing sets `no` only on a property whose own No rule the quote meets.
- ST-5. Each stated limit is counted in one cell only. A limit counted in another cell is printed beside this one as an `aside` and does not change its state (for FlashProve, the clipped-gap policy is counted in Model bound and the one leaked bit in Weights hidden).
- ST-6. Trust and caveats every row shares do not change a state: the checker's own computer, compiler and build; which real, named model a commitment is. They are printed as text. A cell is judged for the configuration the row reads (SRC-1), not for another configuration of the same system.
- ST-7. Public parameters fixed before the hash are shared by every non-interactive proof. They set `partly` on No trusted party only where the documentation says its proved statement excludes a provider who tuned them ([Q1](#open-questions)).
- ST-8. Where two quotes in the allowed sources meet the rules of different states, the reviewer quotes both, the cell carries `conflict: true`, its reason says that the sources conflict, and its state is fixed by this table ([Q4](#open-questions)): `yes` with `partly` gives `partly`; `yes` with `no`, or `partly` with `no`, gives `no`. The quote of that state is the deciding quote. The table resolves one cell and is never applied across cells or rows.

### Properties

The six ids, in display order: `weights_hidden`, `model_bound`, `whole_output`, `formally_verified`, `security_level`, `no_trusted_party`. Each rule below is met only by what the documentation says (ST-1, ST-3).

#### Weights hidden (`weights_hidden`)

- Question: does the checker learn nothing about the weights?
- Not covered: hiding the weights from the host operator (an enclave) is not this property.
- Yes: the documentation says the weights stay hidden from the checker in the default use, naming no leak beyond public settings.
- Partly: the documentation says they are hidden with a stated limit: a named leak, hiding shown for one policy or setting only, hiding optional per circuit, or hiding behind a commitment without the formal zero knowledge property.
- No: the documentation says the checker sees the weights, or that hiding is off or not provided. The prototype clause "or the design gives the checker the weights" is removed; recompute's No rests on RFC-0015's statement that its verifier holds the weights.
- Not stated: no statement about hiding the weights from the checker in the sources read.

#### Model bound (`model_bound`)

- Question: is each checked token tied to the committed weights?
- Not covered: which real, named model the commitment is. FlashProve and SASH both say that stays outside their proof; it is printed as text.
- Yes: the documentation says a passing check ties each checked token to the committed weights exactly, in the configuration the row reads (the card's configuration for card rows; the default or expected use for public-source rows).
- Partly: tied with a stated limit: under one of several policies only, within a tolerance or bound, or shown only in empirical tests.
- No: the documentation says outputs are not tied to any weights, or that nothing is checked.
- Not stated: silent.

#### Whole output checked (`whole_output`)

- Question: does one check cover every output token of a request?
- Name: the prototype's "Whole output proved" is renamed, because the question asks what a check covers and a reference row's check proves nothing (AGENTS.md rule 10). The id stays `whole_output`.
- Not covered: which requests get a check (sampling, proving after the fact) is a deployment choice. The text before tokenizing and after detokenizing, which FlashProve and SASH both put outside their proof, is printed as text.
- Yes: the documentation says one check, or one joined set of checks, covers the prompt and every output token of a request.
- Partly: one check covers a stated part: the positions the client names, one segment, or one disputed step.
- No: the documentation says no output token is checked, or that nothing is checked.
- Not stated: silent, including a proved run whose output tokens the documentation does not name.

#### Formally verified (`formally_verified`)

- Question: is the security argument for the row's configuration checked by a proof assistant?
- Not covered: a proof that the code itself is correct, which no row claims; it is printed as text. A statement the documentation makes only for another configuration of the same system (for example another verifier, RFC-0002 §Configuration identity 5) is printed as an `aside` and sets nothing (ST-6, SRC-1).
- Yes: the documentation says the soundness of the configuration the row reads is proved in a proof assistant (Lean, Coq, Isabelle or similar).
- Partly: machine-checked for a stated part only: one component, or a weaker statement than the one the system makes.
- No: the documentation says the argument is not machine-checked, that a machine check is planned only, or that its soundness evidence is review or tests and nothing else. On a reference row, ST-4.
- Not stated: silent.

#### Security level (`security_level`)

- Question: is a soundness level stated for the row's configuration, and proven?
- Not covered: the number itself, which is a quote in the claim card (INV-GLYPH-3). A level the documentation states only for another configuration of the same system is printed as an `aside` and sets nothing (ST-6, SRC-1).
- Yes: the documentation states a numeric soundness bound for the configuration the row reads and says it is proven, by hand or by machine, under named assumptions.
- Partly: a numeric level is stated but called conjectured, or stated only in code or configuration, or for part of the system.
- No: the documentation says the settings give no meaningful soundness (for example a test-only setting). On a reference row, ST-4.
- Not stated: no level stated for the configuration.

#### No trusted party (`no_trusted_party`)

- Question: does a check hold without trusting a chip maker, a setup ceremony or an honest party?
- Not covered: trust every row shares (ST-6), and where the commitment or the weights come from (see Model bound).
- Yes: the documentation says the check rests on cryptography alone or needs no trusted setup, and names no chip maker, setup or other party to trust.
- Partly: the documentation states a trusted input or condition that its proved statement does not cover: a setup file, public files the user must grant were fixed before the hash (ST-7), or one honest party among several.
- No: the documentation says the check verifies a hardware attestation against a chip maker's keys or certificate chain, or that the provider is trusted. The quote MUST state the dependency; "runs in a trusted execution environment" alone does not (ST-3). This replaces the prototype rule, which named a kind of check.
- Not stated: silent.

### Sources by row class

#### Card rows (`claim_card_at_pin`)

- SRC-1. A card row names exactly one claim card by `card: {system, configuration, card_version}` (RFC-0002 §File and identity). Its states are for that card's configuration, the verifier included: a statement the documentation makes only for another configuration of the system (another acceptance policy or another verifier, RFC-0002 §Configuration identity 2 and 5) is printed as an `aside` and sets nothing. A system with several cards in a release has one row per card. This settles R3: FlashProve's card is `exact-match-cp-verify` (issue #69 is closed), so its cells are read for exact match under the C++ verifier `cp_verify`, and its Lean verifier statements set nothing on this row.
- SRC-2. Every quote of a card row, deciding, supporting or `aside`, is copied from the card's `upstream.repo` at the card's `upstream.commit`. This is AGENTS.md rule 9 ("copy what the system states at the pinned commit") and the rule INV-CLAIM-3 sets for the card. Its `sources_read` include that repository at that commit. This settles the SASH companion repository: `sg-ai-safety-hub/zk-inference-results` is not a source of a SASH card-row state, since the SASH card does not accept it (`systems/sash/claim.yaml` L5 to L6). It may appear in `sources_read` and in `outside_pin`. Should RFC-0002 be amended to let a card name companion repositories at full commits, SRC-2 follows it.
- SRC-3. A statement by the system outside the pin MAY be shown beside the cell as `outside_pin`, with a reason and quotes and no state. It never sets the cell's state, and it is never drawn in the glyph or in a state's ink. This settles R2 under AGENTS.md rule 9: the glyph and the card it reads say the same thing. SASH can be asked to state it in the repository (#42).
- SRC-4. A reviewer sets each card-row state from quotes. The card fields in the table below limit the states a cell may hold ([CRIT-6](#validation-rules-g2)); where the allowed set has one state, the cell MUST carry it ([Q3](#open-questions)).

Claim card fields each property reads (RFC-0002 §Fields). A card value not named in the last column allows all four states.

| Property | Card fields read | States the card allows (CRIT-6) | Derivable from the card alone |
|---|---|---|---|
| Weights hidden | `zero_knowledge.claimed`, `.hidden`, `.not_hidden`, `.status`; `sources.zero_knowledge*` | `claimed: "not stated"` allows {`not_stated`}; `claimed: false` allows {`partly`, `no`} | Partly: Not stated is; `partly` against `no` needs the quote under the property rules, and `yes` against `partly` a reading of `not_hidden` |
| Model bound | `relation`, `coverage.policy.kind`, `coverage.policy.detail`, `binding`, `claim_class` | `policy.kind: tolerance` allows {`partly`, `no`}; `policy.kind: not_stated` with `binding: "not stated"` allows {`not_stated`} | Partly |
| Whole output checked | `coverage.unit`, `coverage.tokens_covered`, `coverage.phase`, `relation` | none: `tokens_covered` is free text | No |
| Formally verified | `relation_formal`, `security.notion.kind`, `security.notion.verifier`; `sources.security.notion*` | `relation_formal: "not stated"` allows {`partly`, `no`, `not_stated`} | No: only `yes` is excluded |
| Security level | `security.level`, `security.notion.kind`, `security.notion.verifier`, `security.model` | `level: "not stated"` allows {`not_stated`} | Partly: Not stated is; proven against conjectured, and whether the level is stated for this configuration, need the `level` text |
| No trusted party | `security.setup`, `assumptions`, `assumptions_not_stated`, `security.model.assumption` | `setup: trusted` allows {`partly`, `no`}; `setup: not_stated` with `assumptions_not_stated: true` allows {`not_stated`} | Partly |

The fields that set FlashProve's No trusted party are `assumptions` (its third item, `systems/flashprove/claim.yaml` L72 to L75, "Configuration files fixed before the hash function is drawn"), not `security.setup`, which reads `not_stated` (L43). A reviewer reads every field in the row, not only the obvious one. Where a free-text field says a statement is not made for the card's configuration (FlashProve `security.level`: "Not claimed for `cp_verify`"), SRC-1 excludes `yes` by review, since CRIT-6 does not parse free text.

RISK: Whole output checked cannot be limited from the card, and Formally verified only by `relation_formal`, so a card change can leave them stale. Plan: [CRIT-5](#validation-rules-g2) ties every card-row quote to the card's commit and version, so a new pin (a new card, RFC-0002 §Configuration identity 1) fails CRIT-5 until every cell is re-read. A later RFC-0002 amendment MAY add a card field for machine-checked soundness.

#### Reference rows (`reference_rfc_0015`)

- SRC-5. Reference rows are the benchmark's own methods, not systems, and have no claim card (RFC-0015 §Reference systems: "they prove nothing"). Their documentation is RFC-0015 together with the table below, which is normative: it sets each state by definition of the method, and the text of RFC-0015 it rests on. Where RFC-0015 has no sentence that meets a state's rule word for word (plain serving checks nothing; a rerun by the checker trusts no other party), the row's reason begins "By definition:" and names the RFC-0015 text. Every quote is from `rfcs/0015-reference-rows.md` in this repository at a full commit ([CRIT-7](#validation-rules-g2)). A change to RFC-0015 that changes one of these states, or moves a quoted sentence, MUST amend this table and the quotes in the same pull request; CRIT-7 fails until it does.
- SRC-6. A reference row names the workloads whose configuration it reads (`workloads`). These states describe the method as RFC-0015 documents it, not a measurement. The table gives the states of a configuration with no declared precision substitution. A recompute row whose workloads declare a substitution (RFC-0015 PM-2, PM-4) is `partly` on Model bound, because the rerun uses another precision than the workload's; one row reads workloads that agree on whether a substitution is declared. Today `systems/ref-recompute/system.yaml` declares one on both SASH workloads (FP8 W8A8 for the workload's INT8 W8A8, RFC-0015 Resolved Q1 and PM-4) and none on the two Maverick workloads. The criteria file's single recompute row reads the two Maverick workloads, which are the ones the site shows, and keeps Yes. A SASH-workload recompute row needs its own row, with `partly` on Model bound, before any page shows it. A configuration marked `not_measurable_on_profile` (RFC-0015 NM-1) keeps its states, and the row prints the NM-1 reason (settles R8).

| Property | Plain serving (`ref-serve`) | Recompute (`ref-recompute`) | Deciding RFC-0015 text (supporting text) |
|---|---|---|---|
| Weights hidden | No (ST-4) | No | plain serving: §Reference systems L45 "they prove nothing" (§Summary L13); recompute: §Recompute L82 "A verifier holding the weights checks a claimed output by running the model itself." |
| Model bound | No (ST-4) | Yes; Partly with a declared substitution (SRC-6) | plain serving: §Reference systems L45 (SRV-4 L77, outputs not compared); recompute: PM-0 L102 (RC-3 L86, each claimed position compared with the argmax; ties follow the engine's stated rule) |
| Whole output checked | No (ST-4) | Yes | plain serving: §Reference systems L45 (§Summary L13); recompute: RC-3 L86, one forward pass over prompt plus every claimed output token (RC-7 L98) |
| Formally verified | No (ST-4) | No (ST-4) | §Reference systems L45 "they prove nothing" (plain serving: §Summary L13) |
| Security level | No (ST-4) | No (ST-4) | §Reference systems L45 "they prove nothing" (plain serving: §Summary L13) |
| No trusted party | No (ST-4) | Yes, by definition | plain serving: §Reference systems L45 (§Summary L13); recompute: §Recompute L82, the checker reruns the model itself and trusts no other party beyond ST-6 |

- SRC-7. A reference row's `no` on Formally verified and Security level means "no security argument, by definition" and its reason says so. A plain serving row's `no` on every property means "by definition: nothing is checked" (RFC-0015 §Summary, SRV-4). No fifth state ("does not apply") is added (settles R14; one vocabulary of four states).

#### Public-source rows (`public_sources`)

- SRC-8. States come from public quotes by the system's own authors: its repository at a full commit, its paper, or its documentation or blog on a domain its team controls. Each row lists these as `own_sources` (repositories, domains, and URLs of papers or pages its authors published), with how each was identified. A deciding quote comes from an own source ([CRIT-3](#validation-rules-g2)); a third-party page (press, survey, another team's blog) may appear only in `sources_read` or `aside`, and sets nothing (AGENTS.md rule 9). These rows are drawn apart from card and reference rows and are never in the benchmarked tab ([CRIT-12](#validation-rules-g2)). How the site marks them (the prototype's "pencil") is the site's (#319).
- SRC-9. A web quote carries, in place of a commit: the `url`, a `retrieved` date (`"YYYY-MM-DD"`, RFC-0012 dates), and either an `archive_url` (a snapshot in a public web archive taken on or after the retrieved date) or a `copy` (a path in this repository holding the retrieved text, with its sha256). A web quote without these sets no state ([CRIT-3](#validation-rules-g2)).
- SRC-10. A public-source row is not capped below Yes. This settles R1 under AGENTS.md rule 9: a cap would print Partly where the documentation states no limit, a state that comes from the benchmark rather than the source. The thoroughness gap is met instead by drawing public-source rows apart (SRC-8) and by web quotes that carry what was read (SRC-9).

### Criteria file contract

The file stays at `web/_data/criteria.json`, authored JSON in the RFC-0012 canonical form (G3 `FMT-1`). Its schema is `schema/criteria/1.schema.json`, `$id` `https://inference-proofs.org/schema/criteria/1.schema.json`, Draft 2020-12, with `"schema": {"const": "criteria/1"}`.

RFC-0012 §Schema catalogue row, added by the implementing pull request:

| Name | File | Kind | Path of instances | Owner RFC |
|---|---|---|---|---|
| `criteria` | `schema/criteria/1.schema.json` | authored JSON | `web/_data/criteria.json` | RFC-0016 |

RFC-0013 §G2 inputs gain `web/_data/criteria.json` (and `G2_GLOBS` in `harness/src/iproofs/validate/tree.py`); the `CRIT-n` rules join the G2 cross-document checks.

Shape only (every object `additionalProperties: false`; `Text` is a non-empty string; `{}` stands for the same fields as `yes`; `Quote` is defined below):

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
                                  "note": "Text", "conflict": false,
                                  "aside": {"words": "Text", "quotes": ["Quote"]},
                                  "outside_pin": {"reason": "Text", "quotes": ["Quote"]}}}},
    {"id": "ref-recompute", "source_class": "reference_rfc_0015", "tab": "benchmarked",
     "workloads": ["fp-maverick-w1024-b1", "fp-maverick-w1024-b24"], "cells": {}},
    {"id": "tinfoil", "source_class": "public_sources", "tab": "not_benchmarked",
     "own_sources": [{"domain": "docs.tinfoil.sh", "how": "Text"}, {"repo": "owner/repo", "how": "Text"}], "cells": {}}
  ]
}
```

- `card_version` is a string of digits here, because the file holds no number-typed value (INV-GLYPH-2, CRIT-10); CRIT-5 compares it with the card's integer.
- `rfc` names this RFC. The file carries no status: the site reads the status line of `rfcs/0016-*.md`, so a status change stays a two-file pull request (RFC-0001 §RFC lifecycle rule 4). The label "Draft criteria, needs an RFC" changes only when this RFC is Accepted.
- Quote, one of three kinds. All carry `kind`, `text` (verbatim), `label`, `decides` (boolean) and `checked: true` with `checked_how` (Text). `repository` and `this_repository` add `repo`, `commit` (40-hex), `path`, `lines` (`^L[0-9]+(-L[0-9]+)?$`) and `url` (containing `commit`). `web` adds `url`, `retrieved`, and `archive_url` or `copy: {path, sha256}`, and carries no `repo`, `commit`, `path` or `lines` key. The prototype kind `ours` becomes `this_repository`. Quotes in `aside` and `outside_pin` carry `decides: false`.
- `aside`: `{words, quotes}`, text printed beside a cell for a limit counted in another cell (ST-5) or a statement made for another configuration (SRC-1). It sets nothing. The prototype's `aside.quote` and `aside.also` become the entries of `aside.quotes`.
- `outside_pin`: `{reason, quotes}`, card rows only, no `state` (SRC-3).
- `conflict`: `true` only on a cell under ST-8; absent otherwise.
- `sources_read` entry: `{repo, commit, paths}` for a repository (paths or globs read) or `{url, retrieved}` for a web page.
- `not_copied: true` MAY replace `sources_read` on a `not_stated` cell of a public-source row where nothing was read yet ([Q2](#open-questions)).
- `workloads` (reference rows, required): workload ids present in the reference system's `system.yaml` (SRC-6). `own_sources` (public-source rows, required, non-empty): each entry one of `repo`, `domain` or `url`, with `how` (SRC-8).
- Removed from the prototype, each for a reason: `test_mapping`, `rows[].states` and `rows[].pencil` (derived from the cells and `source_class`; derived values are computed, not typed); `quote_check` (a typed count that no rule recomputes); `contrast` and `states.*.fill`, `.ink`, `.mark` (drawing, the site's; `site.json` already holds the inks it uses); `status` (read from the RFC); `this_repository_commit` (moves into `pins`); `rules` and `risks` (now this RFC's normative text and dispositions); `outside_pin.state` (SRC-3); the `null` `repo`, `commit`, `path` and `lines` keys of web quotes.

### Validation rules (G2)

Each failure is a G2 finding with the rule id and the JSON pointer of the cell or quote. Shape failures (unknown state, unknown key, a number, a missing required field) are schema failures under the generic G2 rule. Semantic rules:

| Id | Rule | Error kind |
|---|---|---|
| `CRIT-1` | A `yes`, `partly` or `no` cell has at least one quote; its first quote has `decides: true` and no other quote in the cell does. Quotes in `aside` and `outside_pin` have `decides: false`. A cell with `conflict: true` has at least two quotes, and its state is the one ST-8's table gives. Every quote has `checked: true`. | `config` |
| `CRIT-2` | A `repository` or `this_repository` quote has a 40-hex `commit` equal to `pins[repo]`, and its `url` contains that commit. Every `pins` entry is used by a quote or a `sources_read` entry. | `integrity` |
| `CRIT-3` | A `web` quote has an https `url`, a `retrieved` date not after the file's `date`, and an `archive_url` or a `copy` whose file exists and whose sha256 matches. A deciding quote of a public-source row comes from an entry of the row's `own_sources`: a `repository` quote's `repo` is a `repo` entry; a `web` quote's host equals a `domain` entry or its url starts with a `url` entry. | `integrity` |
| `CRIT-4` | A `not_stated` cell has no quote with `decides: true`, and exactly one of a non-empty `sources_read` or `not_copied: true`. `not_copied` appears only on public-source rows. | `config` |
| `CRIT-5` | A card row names a card that exists, at `systems/<system>/claim.yaml` or `systems/<system>/claims/<configuration>.yaml` (RFC-0002 §File and identity), whose own `system`, `configuration` and `card_version` equal the row's `card`. Every quote of the row outside `outside_pin` is in the card's `upstream.repo` at `upstream.commit`, and `sources_read` of each `not_stated` cell includes that repository at that commit. | `integrity` |
| `CRIT-6` | A card row's state is in the set the [card fields table](#card-rows-claim_card_at_pin) allows for each card value. If [Q3](#open-questions) resolves to derived states, this rule recomputes each card-row state from the card and fails on any difference. | `integrity` |
| `CRIT-7` | A reference row's quotes are all `this_repository` quotes of `rfcs/0015-reference-rows.md`, and each quote's text also occurs, whitespace-normalised, in that file as it stands in the tree being validated. Its `workloads` all exist in its reference system's `system.yaml` and agree on whether `precision_substitution` is declared. Its states equal the [reference table](#reference-rows-reference_rfc_0015), with SRC-6 applied from those workloads. | `integrity` |
| `CRIT-8` | The text of each `this_repository` quote occurs, whitespace-normalised, in `git show <commit>:<path>` at its `lines`. CPU only, no network. A commit absent from the local object store is an `environment` error, never a pass. | `integrity` |
| `CRIT-9` | `order` equals the six ids of [Properties](#properties) in that order; `properties` holds exactly those ids in that order; every row has exactly those six cells; row ids are unique. | `config` |
| `CRIT-10` | No JSON number anywhere in the file, and no key named `total`, `score`, `rank`, `count`, `sum`, `average`, `mean` or `weight` (case-insensitive) at any depth. | `config` |
| `CRIT-11` | `outside_pin` appears only on card rows. `workloads` appears only on reference rows, and `own_sources` only on public-source rows. | `config` |
| `CRIT-12` | A public-source row has `tab` `not_benchmarked` or `archived`; a card or reference row has `tab` `benchmarked`. | `config` |

Upstream quotes (kind `repository` outside this repository, and `web`) are checked against their source by the reviewer, recorded in `checked_how`. CI does not fetch them (RFC-0012: validators never use the network).

### Data flow and lifecycle

1. A reviewer edits `web/_data/criteria.json` by pull request, quoting sources at the commits the row class allows.
2. `iproofs validate` runs G2 (schema and `CRIT-1` to `CRIT-12`) and G3 on it.
3. A claim card change (a new `card_version`) fails `CRIT-5` on that row until the row names the new version, so every card change forces a re-read of its row. An RFC-0015 change that moves a quoted sentence fails `CRIT-7` until the quotes and the reference table are amended.
4. `web/build.py` reads the states from the cells; the footer pins the file's sha256 as it does today.

Determinism: the rules read only the file, the claim cards, the reference `system.yaml` files, `rfcs/0015-reference-rows.md` and git objects of this repository. No clock and no network.

### Failure modes

| Failure | Response |
|---|---|
| A coloured cell without a deciding quote | `CRIT-1` fails |
| A quote at a short or unpinned commit | `CRIT-2` fails |
| A web page changed or removed after it was quoted | the `archive_url` or `copy` still holds the text read; the cell stands until a reviewer re-reads it |
| A web quote with no archive and no copy | `CRIT-3` fails; the cell becomes `not_stated` with the url in `sources_read`, or gains an archive |
| A deciding quote from a third-party page | `CRIT-3` fails; the quote moves to `sources_read` or `aside` |
| A Not stated cell with nothing recorded | `CRIT-4` fails |
| A card-row quote from another repository or commit | `CRIT-5` fails; the quote moves to `outside_pin` or is replaced from the pin |
| A card-row state read from another configuration of the system | review catches it (SRC-1); `CRIT-6` catches it where a card field excludes the state (for example `relation_formal: "not stated"` with Formally verified `yes`) |
| A card change contradicts a cell (for example `zero_knowledge.claimed` becomes `false` while the cell is `yes`) | `CRIT-6` fails |
| RFC-0015 edited so a reference quote no longer reads in the current file | `CRIT-7` fails until the quote, its commit and, if a state changes, this RFC's table are amended (SRC-5) |
| A reviewer's inference used as a deciding quote | review catches it (ST-3); the quote's text must be the system's own words, which `CRIT-8` checks for this repository's quotes |
| A score, count or number added to the file | `CRIT-10` fails |

## Alternatives Considered

- **Keep the design clauses ("or the design rules it out").** Considered because some designs make a property impossible on their face (a recompute verifier must hold the weights). Rejected: it lets the benchmark state a security property the system does not state, against AGENTS.md rule 9, and every case in the data today has a documented statement that serves instead (recompute's rests on RFC-0015).
- **Judge Formally verified and Security level for the protocol, whatever verifier the card runs.** Considered because the prototype does, and the protocol is what the system's theorem is about. Rejected: RFC-0002 §Configuration identity 5 makes the verifier part of the configuration when the verifiers carry different security statements, and the FlashProve card says its statements hold for the Lean verifier only. Reading the Lean statement onto the `cp_verify` row would print a state the card says is not stated for it (SRC-1).
- **Derive every card-row state from card fields.** Considered because CI could then recompute the glyph and no reviewer judgement would remain. Rejected as the default ([Q3](#open-questions)): Whole output checked has no field to derive from, Formally verified has only one that excludes a state, and Yes against Partly on three other properties depends on free text. The allowed sets keep the part that can be derived.
- **Cap public-source rows at Partly (R1).** Rejected by AGENTS.md rule 9 (SRC-10).
- **Let a system's own publication outside the pin, or its companion repository, set a card-row state (R2, SASH).** Rejected by AGENTS.md rule 9 and INV-CLAIM-3 (SRC-2, SRC-3). An RFC-0002 amendment that lets a card name companion repositories remains open to anyone.
- **Keep the name "Whole output proved".** Rejected: a reference row proves nothing, and an attested row's check is not a proof; "proved: Yes" on those rows would misuse the word (AGENTS.md rule 10). "Checked" is true of every row the question asks about.
- **A fifth state, "does not apply", for reference rows.** Considered in R14. Rejected: one vocabulary of four states, and a `no` with the reason "no security argument, by definition" says the same thing.
- **A score per row, or a count of Yes.** Rejected: the benchmark measures and does not rank ([PRD §5](../docs/PRD.md#5-non-goals)); a count would weigh six unlike properties as equal.
- **Benchmark-assigned security levels on the glyph.** Rejected by RFC-0002 §Alternatives Considered: it is certification, a non-goal, and it rounds away the exact form.
- **Accept web quotes with a URL only, from any page.** Considered because the prototype does. Rejected: pages change, and a state must be checkable against the text read; a third party's page is not the system's documentation.
- **Move the criteria file out of `web/` (for example to `methodology/criteria.json`).** Considered because the file is methodology, not presentation. Rejected for now: `web/build.py` and the footer read it at its path, and moving it is churn with no change in meaning; #320 MAY move it with the generator.

## Drawbacks

- Re-reading is costly: every card change and every web quote needs a reviewer, and 65 Not stated cells need a list or a marker before the file validates.
- A thorough system collects Partly while a silent one shows Not stated (R1, R11). This RFC keeps that, because it is what the documentation says; the site has to explain that Not stated is not No.
- A rule that a No needs a statement, and that a card row reads only its own configuration, will move some cells to Not stated (candidates in [Migration / Rollout](#migration--rollout)), so the glyph shows less than a reader of the design might expect.
- Reference rows' states are set by definition in this RFC where RFC-0015 has no sentence to quote; a reader must trust the project's own description of its baselines.
- Two properties stay reviewer-set for card rows, with little mechanical check beyond the commit pin.

## Conflicts of Interest

The author's affiliation and any interest in a measured system are to be declared in `MAINTAINERS.md` before this RFC enters Last call (RFC-0001); the author is not yet listed there. This text was drafted with an AI agent, Claude, made by Anthropic. Anthropic publishes FlashProve (`anthropics/FlashProve`), one of the two systems with a card row. Reviewers should weigh the decisions that move FlashProve cells with that in mind: SRC-1 on R3, which reads FlashProve for its `exact-match-cp-verify` configuration and so takes its Formally verified and Security level off Yes (the prototype read both from the Lean verifier's statements); and ST-7 and Q1 on R6.

## Migration / Rollout

Two pull requests, in order (issue #318). This one adds the RFC and its index rows only. The second opens once this RFC is in Last call and merges only once it is Accepted (RFC-0001 §RFC lifecycle rule 3, INV-GOV-3). It adds the schema and examples, the `CRIT-n` rules, `harness/tests/unit/test_criteria.py`, the RFC-0012 catalogue row and the RFC-0013 G2 input, rewrites `web/_data/criteria.json` to `criteria/1`, and updates `web/README.md` (§Open and the criteria text) and `docs/spec/10-glossary.md` (the six properties and four states). Its description lists every state that changes, by row, and every cell edited to pass the new rules.

Counts in the committed file (sha256 starting `4ced468b`, at `356949a5ee8afe328ee2cb0d68b18be1b1d82453`), recomputed by:

```sh
python3 -I -c 'import json;d=json.load(open("web/_data/criteria.json"));c=[(r,c) for r in d["rows"] for c in r["cells"].values()];print(sum(1 for r,x in c if x["state"]!="grey" and x["quotes"] and all(q["kind"]=="web" for q in x["quotes"])), sum(1 for r,x in c if x["state"]=="grey" and not x.get("searched")))'
```

which prints `13 65`. Of 138 cells (23 rows of 6): card rows 4 Yes, 5 Partly, 3 Not stated; reference rows 3 Yes, 9 No; public-source rows 14 Yes, 7 Partly, 3 No, 90 Not stated.

What fails the new rules, and what the second pull request does:

1. Key and field changes, no state change:
   - `green`, `amber`, `red`, `grey` to `yes`, `partly`, `no`, `not_stated`; property rule text moves under `properties[].rules`; the name "Whole output proved" becomes "Whole output checked" in `criteria.json` and `site.json`.
   - quote kind `ours` to `this_repository` (20 quotes); the `null` `repo`, `commit`, `path` and `lines` keys dropped from the 20 web quotes; `decides: false` added to the 4 `aside` quotes and the 2 `outside_pin` quotes; each `aside`'s `quote` and `also` become `aside.quotes` (3 cells); `outside_pin.state` dropped (2 SASH cells).
   - `searched` to `sources_read` (28 cells, 64 entries, turned into objects). 13 of these entries, in 12 cells, are web pages (arXiv, IACR ePrint, `attestable.com`, `docs.tinfoil.sh`, `polyhedra.network`, `ddkang.github.io`) with no recorded date; each is re-read to set `retrieved`, or dropped from the list if it cannot be.
   - reference rows gain `workloads` (both read the two Maverick workloads); public-source rows gain `own_sources`; removed fields as in [Criteria file contract](#criteria-file-contract); `pins` gains this repository and the 6 public-source repositories quoted (`CRIT-2`).
2. 13 coloured cells whose only quotes are web quotes fail `CRIT-3`: Attestable Weights hidden, Model bound, Whole output checked, No trusted party; NanoZK, zkGPT, zkLLM, ZKML, zkPyTorch and ZKTorch Weights hidden; Tinfoil No trusted party; TOPLOC Model bound; Verde No trusted party. In all, 20 web quotes lack a retrieval date and a stored copy (these 13, one supporting quote on DeepProve Whole output checked, 4 context quotes in Not stated cells, 2 SASH `outside_pin` quotes). Each gains `retrieved` and an `archive_url` or `copy`; a page that cannot be retrieved again sets its cell to `not_stated` with the url in `sources_read`. The deciding quotes of these 13 cells are on 6 hosts (`attestable.com`, `arxiv.org`, `eprint.iacr.org`, `docs.tinfoil.sh`, `ddkang.github.io`, `polyhedra.network`); the second pull request records for each row which pages are its authors' own (`own_sources`), and a deciding quote from any other page moves to `sources_read` and its cell to `not_stated`.
3. 65 Not stated cells, all on public-source rows, have no sources-read list and fail `CRIT-4`. The 53 reading "Not copied yet." take `not_copied: true` (under Q2's default). The other 12 have reasons that name what was read (for example "Proves a graph run; output tokens not named."); each gains a `sources_read` list, or is re-read. `not_copied: true` is used only where nothing was read.
4. SASH Whole output checked (Yes) fails `CRIT-5`: its deciding quote is `docs/statement-gap.md` L3 to L7 in `sg-ai-safety-hub/zk-inference-results` at `11decec3`. Under SRC-2 the reviewer re-reads `sg-ai-safety-hub/zk-inference-prover` at `eb95bfa8` (the card's own `coverage.tokens_covered` source, `prover/src/boundary.rs` L1148 to L1156, and the supporting quote `docs/statement.md` L5 to L7) and sets a deciding quote from there, or Not stated. The 15 `searched` entries in the results repository on SASH cells stay as sources read.
5. FlashProve Formally verified (Yes) fails `CRIT-6`: the card reads `relation_formal: "not stated"` (`systems/flashprove/claim.yaml` L22), and its deciding quote, README L26 ("The protocol's soundness is proved in Lean 4."), is stated for the Lean verifier, while `security.notion.verifier` reads "Stated for the Lean verifier `verify` only, not for `cp_verify`". FlashProve Security level (Yes) fails SRC-1: the card's `security.level` opens "Not claimed for `cp_verify`". Both cells are re-read against the `exact-match-cp-verify` card, the Lean statements move to `aside`, and neither cell may stay `yes`; the new state is set from the quotes and listed in the second pull request.
6. Cells to re-read under the new rules, outcome not decided here, each listed with its result in the second pull request: FlashProve Model bound and Whole output checked, against the `exact-match-cp-verify` card (SRC-1; the current Model bound reason rests on the expected use, which checks only the client's limits, not on the exact-match configuration the card runs); SASH No trusted party, against the first item of the card's `assumptions` ("produced at setup, trusted by the verifier", `prover/src/compose.rs` L5 to L11), which the cell does not cite; Tinfoil and Private ML SDK No trusted party, under the rewritten No rule; the 8 public-source Weights hidden Yes cells (Attestable, NanoZK, VerInf, zkGPT, zkLLM, ZKML, zkPyTorch, ZKTorch), for whether each quote says hidden from the checker (R10); VerInf Formally verified and Whole output checked (R13).
7. Apart from FlashProve Formally verified (item 5), card rows meet every `CRIT-6` set today: SASH Weights hidden is Not stated with `zero_knowledge.claimed: "not stated"`, SASH Formally verified is Not stated with `relation_formal: "not stated"`, and no other set applies to either card.
8. Reference rows: all 20 quotes are at `fbe1f9c798ac9a2865dca086954de5e8a20c91d7`, and each reads verbatim at its lines (checked by the author with `git show`, as `CRIT-8` will); `rfcs/0015-reference-rows.md` is unchanged between that commit and `356949a5`, so `CRIT-7`'s current-file check holds. Every plain serving cell decides on §Reference systems L45, as the reference table cites. States equal the reference table; no change. Each reason that rests on a definition gains "By definition:" (SRC-5, SRC-7).
9. `web/build.py`, changed with the data so the build still passes and its output is committed:
   - L41 to L44 keeps its check by mapping each cell's state id to the `site.json` key (`yes` to `green`, `partly` to `amber`, `no` to `red`, `not_stated` to `grey`) until #320 renames the site keys; `site.json` `glyph.rows[*].states` changes with every state that changes.
   - `build_criteria` (L1516 to L1535) reads each rule as `p["rules"][id]` for the id mapped from each `site.json` `state_order` key, in place of `p[s]`.
   - the `PHRASES` entries (L505 to L523) that quote criteria text are updated to the new rule and note text, or removed with the text they rewrite, since L520 to L523 assert that each still occurs in the data.
   - the rebuilt pages are committed: `web/criteria.html`, every page whose glyph or property name changes, and every page's footer, which pins the criteria file's sha256 (L912). `git status --porcelain -- web` then prints nothing.

Dispositions of the prototype's risks:

| Risk | Disposition |
|---|---|
| R1 cap public-source rows | settled by SRC-10 (AGENTS.md rule 9): no cap |
| R2 publication outside the pin | settled by SRC-3 (AGENTS.md rule 9, INV-CLAIM-3): shown beside the cell, no state, sets nothing |
| R3 FlashProve Model bound by policy | settled by SRC-1 (state per card configuration, verifier included) |
| R4 one Lean fact, two cells | superseded on the FlashProve row by SRC-1 (item 5); the two rules still differ (a hand-proved bound is Yes for Security level and not for Formally verified) |
| R5 SASH "conjectured" | kept: the word is SASH's own |
| R6 fixed public parameters | Q1, default option (b) (ST-7) |
| R7 plain serving No on Weights hidden | kept: ST-4 and SRC-7, the reason says "By definition: no checker, so nothing to hide from" |
| R8 recompute by configuration | settled by SRC-6 (`workloads`, one row per substitution case) |
| R9 FlashProve short replies | kept: the reason names the limit |
| R10 zkPyTorch product page | re-read in the second pull request (item 6), and its page checked against `own_sources` (item 2) |
| R11 mostly Not stated rows | accepted: that is what the sources say |
| R12 inks | out of scope: drawing (#319), within INV-GLYPH-1 |
| R13 VerInf | re-read in the second pull request (item 6) |
| R14 recompute has no argument | settled by ST-4 and SRC-7 |

No past results exist; no release has shown a glyph. No claim card changes. No schema version changes other than the new `criteria/1`.

## Testing Strategy

Schema examples in `schema/criteria/examples/` (every invalid example with a `.reason` file):

- `valid/committed-shape.json`: one card row, one reference row and one public-source row in the committed file's shape, with an `aside` and an `outside_pin`; passes.
- `valid/not-copied.json`: a public-source `not_stated` cell with `not_copied: true`; passes.
- `valid/web-quote-archived.json`: a Yes cell whose deciding quote is a web quote with `retrieved` and `archive_url`; passes.
- `invalid/state-outside-four.json`: a cell with `state: "green"`; fails on enum.
- `invalid/property-number.json`: a property with `"n": 1`; fails on `additionalProperties` (and `CRIT-10`).
- `invalid/total-key.json`: a top-level `total`; fails on `additionalProperties`.
- `invalid/score-key.json`: a row with `score`; fails on `additionalProperties`.
- `invalid/web-quote-no-retrieved.json`: a web quote without `retrieved`; fails on `required`.
- `invalid/short-commit.json`: a repository quote with `commit: "9e2bdd8f"`; fails on pattern.
- `invalid/missing-rule.json`: a property whose `rules` lacks `not_stated`; fails on `required`.
- `invalid/outside-pin-state.json`: an `outside_pin` with `state`; fails on `additionalProperties`.
- `invalid/reference-no-workloads.json`: a reference row without `workloads`; fails on `required`.

Unit tests, `harness/tests/unit/test_criteria.py`, each on a hand-made file:

- `test_yes_cell_without_quote_fails` (`CRIT-1`).
- `test_first_quote_must_decide` (`CRIT-1`): a Partly cell whose first quote has `decides: false` fails.
- `test_aside_quote_deciding_fails` (`CRIT-1`): an `aside` quote with `decides: true` fails.
- `test_conflict_cell_follows_table` (`CRIT-1`): a `conflict: true` cell with one quote fails; with `yes` and `no` quotes and state `partly` fails; with state `no` passes.
- `test_repository_quote_short_commit_fails` (`CRIT-2`).
- `test_quote_commit_differs_from_pin_fails` (`CRIT-2`).
- `test_web_quote_without_archive_or_copy_fails` (`CRIT-3`).
- `test_web_copy_hash_mismatch_fails` (`CRIT-3`).
- `test_deciding_web_quote_not_own_source_fails` (`CRIT-3`): a public-source Yes cell deciding from a host outside `own_sources` fails; the same quote as a supporting quote passes.
- `test_not_stated_without_sources_or_marker_fails` (`CRIT-4`).
- `test_not_copied_on_card_row_fails` (`CRIT-4`).
- `test_card_quote_outside_card_repository_fails` (`CRIT-5`): a SASH cell deciding from `sg-ai-safety-hub/zk-inference-results` fails.
- `test_card_quote_at_other_commit_fails` (`CRIT-5`).
- `test_card_version_mismatch_fails` (`CRIT-5`).
- `test_card_configuration_mismatch_fails` (`CRIT-5`): a row whose `card.configuration` differs from the card file's `configuration` fails, for both card paths.
- `test_card_bound_zero_knowledge` (`CRIT-6`): with `claimed: "not stated"`, each of `yes`, `partly` and `no` fails and `not_stated` passes; with `claimed: false`, `yes` and `not_stated` fail and `partly` and `no` pass.
- `test_card_bound_tolerance_policy` (`CRIT-6`): with `policy.kind: tolerance`, `yes` and `not_stated` fail and `partly` and `no` pass.
- `test_card_bound_relation_formal` (`CRIT-6`): with `relation_formal: "not stated"`, Formally verified `yes` fails and each other state passes.
- `test_card_bound_level_not_stated` (`CRIT-6`): with `security.level: "not stated"`, each of `yes`, `partly` and `no` fails.
- `test_card_bound_trusted_setup` (`CRIT-6`): with `security.setup: trusted`, No trusted party `yes` and `not_stated` fail and `partly` and `no` pass.
- `test_reference_state_differs_from_table_fails` (`CRIT-7`).
- `test_reference_substitution_sets_partly` (`CRIT-7`): a recompute row reading a workload with `precision_substitution` passes with Model bound `partly` and fails with `yes`; a row reading workloads that disagree on substitution fails.
- `test_reference_quote_absent_from_current_rfc_fails` (`CRIT-7`): a quote whose text is no longer in the working copy of `rfcs/0015-reference-rows.md` fails.
- `test_reference_table_matches_rfc` (`CRIT-7`): the validator's table equals the table in this RFC, parsed from the markdown.
- `test_this_repository_quote_not_at_lines_fails` (`CRIT-8`), on a temporary git repository.
- `test_missing_commit_is_environment_error` (`CRIT-8`): a quote at a commit absent from the temporary repository gives an `environment` error.
- `test_number_anywhere_fails` and `test_aggregate_key_fails` (`CRIT-10`).
- `test_order_differs_fails` (`CRIT-9`).
- `test_outside_pin_on_public_row_fails` (`CRIT-11`).
- `test_public_row_in_benchmarked_tab_fails` (`CRIT-12`).
- `test_committed_file_passes`: `web/_data/criteria.json` passes every rule. It needs the git objects of the commits quoted, so it runs where full history is present: the `validate` CI job (`fetch-depth: 0`), or a test job given `fetch-depth: 0`. In a shallow clone it is skipped with the reason printed, and `CRIT-8` reports the missing commits as `environment` errors, never as a pass.

Repository checks, as issue #318 lists them: `uv run iproofs validate --all`; `uv run pytest harness/tests/unit/test_criteria.py harness/tests/unit/test_rfc_status.py`; `uv run ruff check`; `uv run mypy harness/src`; `cd web && python3 -I build.py && python3 -I test_sort_keys.py && python3 -I test_cards.py && python3 -I test_search.py`, then `git status --porcelain -- web` prints nothing.

## Open Questions

- OPEN QUESTION Q1 (owner: 0xchqrles, resolve by: 2027-01-31): do public parameters fixed before the hash count as a trusted input (R6)? Option (a) treats them as a shared caveat printed as text; option (b) sets Partly only where the documentation says its proved statement excludes a provider who tuned them. Default until resolved: (b) (ST-7). Reason: it copies a condition the documentation states ("that you grant", FlashProve `guide/what-is-proved.md` L288 to L289 at `9e2bdd8f`); (a) would drop a stated condition. The cost is that a system which states the condition shows Partly while one that does not shows Not stated; the reason text says so, and other teams are invited to state their assumptions.
- OPEN QUESTION Q2 (owner: 0xchqrles, resolve by: 2027-01-31): does "not copied yet" stay a Not stated case, or does the site show it apart from silence? Default until resolved: it stays the state `not_stated` (four states only) and the cell carries `not_copied: true`, so the data tells "not read yet" from "read and silent" (CRIT-4); the printed word stays "Not stated", and whether a page prints the difference is the site's (#319). Reason: printing both the same way would claim sources were read that were not, and a fifth state was rejected (SRC-7).
- OPEN QUESTION Q3 (owner: 0xchqrles, resolve by: 2027-01-31): are card-row states derived from card fields, or set by a reviewer from quotes? Default until resolved: set by a reviewer from quotes, within the sets of the card fields table (SRC-4, CRIT-6). Reason: Whole output checked has no card field to derive from, Formally verified has one that only excludes `yes`, and three properties need a reading of free text; derivation would need RFC-0002 fields that do not exist. If resolved to derived, CRIT-6 recomputes every card-row state from the card.
- OPEN QUESTION Q4 (owner: 0xchqrles, resolve by: 2027-01-31): when two allowed quotes meet the rules of different states, which state does the cell take? Default until resolved: the fixed table of ST-8 (`yes` with `partly` gives `partly`; `yes` with `no`, or `partly` with `no`, gives `no`), with `conflict: true` and both quotes printed. Reason: the state is then met by a quote of the system's own, needs no reviewer judgement, and never says more than the more limited of the two statements; the alternatives (the reviewer picks, or the cell becomes Not stated) either add a judgement or hide two statements the system made.

## References

- [RFC-0001](0001-process-and-governance.md) §Changes to methodology, §RFC lifecycle, §Conflicts of interest.
- [RFC-0002](0002-claim-card.md) §File and identity, §Fields, §Rules (INV-CLAIM-2, INV-CLAIM-3), §Configuration identity, §Alternatives Considered.
- [RFC-0009](0009-results-and-publication.md) for the site; its amendment for the live site is #319.
- [RFC-0010](0010-harness-runner.md) error kinds (`config`, `integrity`, `environment`).
- [RFC-0012](0012-schemas-and-serialization.md) §Schema catalogue, §The `schema` field, §YAML subset for authored files (dates), §JSON writer.
- [RFC-0013](0013-validation-and-ci.md) §G2 Schema validation, §G3 JSON format check.
- [RFC-0015](0015-reference-rows.md) §Reference systems, §Plain serving, §Recompute, §Precision matching, §Feasibility on the profile.
- AGENTS.md hard rules 3, 9 and 10.
- `web/_data/criteria.json` (prototype criteria, sha256 starting `4ced468b`), `web/_data/site.json` `glyph`, `web/build.py` L41 to L44, L505 to L523, L912, L969 and L1516 to L1535, `web/README.md` §Data.
- `systems/flashprove/claim.yaml` and `systems/sash/claim.yaml`, card version 1 each; `systems/ref-serve/system.yaml` and `systems/ref-recompute/system.yaml`.
- `.github/workflows/ci.yml` (`validate` job, `fetch-depth: 0`).
- FlashProve at `9e2bdd8ff5bf9c62f18263d7dac189b0400b260c`; SASH zk-inference-prover at `eb95bfa887299d1637550228d42086c27cbb2b3b`; SASH zk-inference-results at `11decec3c0b62c707618aab5deb82750b355d202`.
- Issues #318 (this RFC), #319, #320, #321, #42, #69.
