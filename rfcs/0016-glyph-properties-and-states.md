# RFC-0016: Glyph properties and states

- Status: Draft
- Authors: 0xchqrles (affiliation to be declared in `MAINTAINERS.md`)
- Created: 2026-11-07
- Target milestone: v0.1
- Requires: RFC-0001, RFC-0002, RFC-0008, RFC-0009, RFC-0012, RFC-0013, RFC-0015
- Supersedes: none
- Discussion: https://github.com/ai-verification-observatory/inference-proofs/issues/318

## Summary

The public site draws every row as a glyph: six properties (Weights hidden, Model bound, Whole output checked, Formally verified, Security level, No trusted party), each in one of four states, printed Yes, Partly, No and Not stated. Today the rules behind those states exist only as prototype data in `web/_data/criteria.json`, whose own `status` reads "draft criteria, prototype only, needs an RFC (RFC-0001)". This RFC makes them normative. The benchmark validates claims; it does not audit them. A state on a claim card row means three things at once: the property is stated by the system at its pin, it is read for the configuration the benchmark runs (verifier included), and the benchmark's own negative controls (RFC-0008) do not contradict it; a reference row's state describes the benchmark's own method (SRC-5), and a public-source row's state is stated by its authors and not run (INV-GLYPH-5). A state is not an audit of cryptographic soundness or zero knowledge, not a probability that the property holds and not a security level of the benchmark's own. This RFC fixes each property's question, what it does not cover, the rule for each state and which controls can contradict it; one state vocabulary; that there is no total, score, count or order over states and no number on a property; the source of a state for each row class (claim card rows, reference rows, public-source rows); that a card row is read for its card's configuration and quotes only the card's pin; the override rule, by which a control the configuration's verifier accepted where RFC-0008 expects rejection sets No on a property stated Yes or Partly, whatever the documentation says; what a web quote carries in place of a commit, and that it comes from the system's own authors; and the contract of the criteria file (`schema: "criteria/1"`, its schema, its G2 rules `CRIT-1` to `CRIT-14` and their tests), which a second pull request implements once this RFC is Accepted. A glyph state is a label printed on every row, so RFC-0001 §Changes to methodology requires this RFC.

## Motivation

Evidence, all at this repository's commit `356949a5ee8afe328ee2cb0d68b18be1b1d82453` unless stated:

- No RFC and no section of `docs/spec/` names the six properties. The pages print "Draft criteria, needs an RFC" (`glyph.legend.draft_short` of the site's data snapshot under `web/_data/`).
- The states are set by hand. A pipeline outside this repository wrote the data (the snapshot's `generated_by: prototypes/v7/_data/make_site_data.py`). `web/build.py` reads no claim card; it only asserts that the snapshot's `glyph.rows[*].states` equals `criteria.json` `test_mapping` (L41 to L44). Nothing checks a state against `systems/flashprove/claim.yaml` or `systems/sash/claim.yaml`. `criteria.json` has no `schema` field, and no RFC-0013 §G2 input glob covers it.
- The data holds rules that contradict AGENTS.md rule 9 ("Do not infer security properties"): `states.red.meaning` reads "The system's documentation says it does not hold, or the design rules it out", Weights hidden No reads "or the design gives the checker the weights", and No trusted party No reads "The check is a hardware attestation verified against a chip maker's keys", which names a kind of check rather than a statement.
- The data reads FlashProve's Formally verified and Security level from statements its documentation makes for the Lean verifier `verify`, while FlashProve's card is the configuration that runs the C++ verifier `cp_verify`, and the card says that neither the formal statement nor the level is stated for it (`systems/flashprove/claim.yaml` L22 and L26 to L37).
- The data leaves owner decisions open "for the RFC": `risks` R1 (cap public-source rows), R2 (a system's own publication outside the pin) and R6 (fixed public parameters as a trusted input).
- The data uses two vocabularies for one thing: state keys `green`, `amber`, `red`, `grey` with labels "holds", "partly", "does not hold", "not stated" in `criteria.json`, and the words Yes, Partly, No, Not stated in the snapshot's `glyph.inks.ladder`.
- Sourcing gaps (counted in [Migration / Rollout](#migration--rollout)): 13 Yes, Partly or No cells on public-source rows rest only on web quotes with no commit, no retrieval date and no stored copy; 65 Not stated cells carry no list of sources read, 53 of them reading "Not copied yet.". SASH's Whole output proved is Yes from a quote in `sg-ai-safety-hub/zk-inference-results`, a repository the SASH card does not accept as a source (`systems/sash/claim.yaml` L5 to L6, INV-CLAIM-3).
- Derived values are typed, not computed: `quote_check` holds a count (77 quotes) that no rule recomputes. It matches the file today (71 in cells, 4 in `aside`, 2 in `outside_pin`), but nothing would catch it drifting.
- Nothing ties the glyph to the benchmark's own tests. RFC-0008 runs the same tampering controls on every system's verifier and records each outcome in `controls.json`, but no rule lets an accepted control reach a glyph cell, so a row could print Yes on Whole output checked while its verifier accepted a changed output token (C1).

The benchmark's role for these properties is the one L2BEAT plays for rollups: it validates what a system claims, it does not certify it. Three layers make a state: the claim is documented (the claim card quotes the system at its pin, Not stated where it is silent; RFC-0002), the claim is read for what the benchmark actually runs (the card's configuration, verifier included; SRC-1), and the benchmark's own negative controls find no obvious breach ([Negative control override](#negative-control-override)). Each layer is checkable by a reader from stored files. None needs the benchmark to judge a proof, a protocol or code, which it is not placed to do ([PRD §5](../docs/PRD.md#5-non-goals): "it does not audit soundness proofs or code").

Scenarios:

1. A reader sees SASH Not stated on Weights hidden and FlashProve Partly. They need to know that Not stated means the pinned sources are silent, not that SASH hides more.
2. A reviewer sets a public-source row to Yes from a post on the system's own blog. A later reader needs to find the text that was read, as it read on the day, without trusting that the page has not changed.
3. A claim card changes `zero_knowledge.claimed` to `false`. The glyph must not keep saying Yes.
4. A reader adds the six states of two rows and compares the sums. The site must give them nothing to add.
5. A card says Whole output checked Yes, and in a release the configuration's verifier accepts C1 (a changed output token). The glyph must not keep saying Yes, and the system page must show the quote, the control, the run and the maintainers' reply side by side.

## Goals

- A state on a claim card row means: stated by the system at its pin, for the configuration the benchmark runs, and not contradicted by the benchmark's own tests; a reference row's state describes the benchmark's own method (SRC-5), and a public-source row's state is stated by its authors and not run (INV-GLYPH-5). The benchmark validates claims and does not audit them.
- Each of the six properties has a question, a not-covered note, a written rule for each of the four states and the list of controls that can contradict it, or a statement that none can ([Properties](#properties)).
- A state on a system's row is set only from a quote of that system's own documentation, never from the benchmark's reading of a design (AGENTS.md rule 9), with one exception: a recorded negative control outcome that contradicts a stated Yes or Partly sets No (OVR-4). A reference row's states are set by RFC-0015 and this RFC, which document the benchmark's own methods.
- The override is mechanical: CI recomputes every overridden cell from the stored `controls.json` files of the release ([CRIT-13](#validation-rules-g2)), and no reviewer judgement sets or clears it.
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
- Judging whether a system's documentation is correct. The glyph reports what the documentation states, like the claim card it reads (RFC-0002 §Non-Goals), and whether the benchmark's own controls contradict it.
- An audit. No state, page or file of this RFC is an audit result of cryptographic soundness, of zero knowledge, of a formal proof or of code; a probability that a property holds; or a security level assigned by the benchmark (INV-GLYPH-3, [PRD §5](../docs/PRD.md#5-non-goals)). A control that rejects shows that one mutation was rejected, nothing more (RFC-0008 §Non-Goals), so it never raises a state.
- New controls, or changes to a control's algorithm or expected set. Those are RFC-0008's; this RFC only maps its controls to properties.
- Running Last call for this RFC (RFC-0001 §RFC lifecycle rule 4). The bootstrap Last call (#24) covers only RFC-0001 to RFC-0015.

## Proposed Design

### Terms

- **Glyph**: the six-part figure the site draws for one row.
- **Property**: one of the six questions below, identified by its id.
- **Cell**: one property of one row: a state, our short reason, and quotes or a list of sources read.
- **Deciding quote**: the quote that sets a cell's state. Further quotes support it and set nothing.
- **Row class**: `claim_card_at_pin` (a system with a claim card), `reference_rfc_0015` (a reference row) or `public_sources` (a system not benchmarked yet).
- **Own source**: a repository, a domain or a published paper of the system's own authors, listed on a public-source row ([SRC-8](#public-source-rows-public_sources)).
- **Stated state**: the state a cell's quotes give under ST-1 to ST-8, before the override. On a cell that is not overridden it is the cell's state.
- **Contradicting outcome**: a control, mapped to a property by the [control map](#negative-control-override), that a stored `controls.json` records as `accepted` where its expected set does not hold `accepted` (OVR-3).
- **Overridden cell**: a card-row cell whose stated state is `yes` or `partly` and which has at least one contradicting outcome; its state is `no` (OVR-4).

### What the glyph is not

- INV-GLYPH-1. There is no total, score, rank, count, sum or average over states, across properties or across rows. No page, file or report computes one. The criteria file holds no key named `total`, `score`, `rank`, `count`, `sum`, `average`, `mean` or `weight` ([CRIT-10](#validation-rules-g2)). No drawing encodes a state by an amount of fill or area that adds up across properties; each state is told apart by ink or pattern. The shapes themselves are the site's (#319).
- INV-GLYPH-2. Properties carry no numbers. The order of `order` is the clockwise display order and nothing else; it is not a priority or a weight. The criteria file holds no number-typed value at all. The site generator (#320) prints none: the view it renders (`iproofs.site.view`) holds no property number, and the data snapshot that held `glyph.properties[].n`, `glyph.key.numbers` and numbered `aria` strings (`web/_data/` at `39662bf6`) is gone.
- INV-GLYPH-3. Security level shows only whether a level is stated and whether the documentation says it is proven. It never shows, compares or computes a level of its own; the level itself is a quote in the claim card (RFC-0002 `security.level`), and benchmark-assigned levels are rejected (RFC-0002 §Alternatives Considered).
- INV-GLYPH-4. Rows are never ordered by their states. Row order is set by the site (RFC-0009).
- INV-GLYPH-5. A state is a validated claim, not a certificate. On a card row it reads: stated by the system at its pin (SRC-2), for the configuration the benchmark runs (SRC-1, OVR-5), and not contradicted by the benchmark's negative controls (OVR-4). Before the first release a card row's states are stated at the pin for the card's configuration, with no run yet (OVR-5). A row under a pending disclosure draws no state (OVR-8). On a public-source row it reads: stated by the system's own authors (SRC-8), not run by the benchmark. On a reference row it describes the benchmark's own method (SRC-5). No state is an audit result, a probability of correctness or a benchmark-assigned level (§Non-Goals). The overview draws the state and nothing else; the quotes, sources and control outcomes behind it are printed on the system page (OVR-7).

### States

One vocabulary, used in the criteria file and on every page. The site data adopts the ids with #320; until then the mapping in [Criteria file contract](#criteria-file-contract) applies. The four states are unordered: none counts as more or less than another, and no rule in this RFC compares two states except ST-8, inside one cell. The override adds no state: an overridden cell is `no` (OVR-4).

| Id | Printed word | Meaning | Replaces |
|---|---|---|---|
| `yes` | Yes | The documentation says the property holds, by the property's Yes rule, and no control contradicts it. | `green`, "holds" |
| `partly` | Partly | The documentation says it holds with a limit it states, by the property's Partly rule, and no control contradicts it. | `amber`, "partly" |
| `no` | No | The documentation says it does not hold, by the property's No rule; or the documentation says it holds, fully or partly, and a negative control of the benchmark contradicts it (OVR-4). | `red`, "does not hold" |
| `not_stated` | Not stated | The sources read say nothing that meets any of the three rules above, or they have not been read yet ([Q2](#open-questions)). | `grey`, "not stated" |

State rules, for every property:

- ST-1. A cell's stated state is `yes`, `partly` or `no` only when a deciding quote, copied verbatim from a source the row class allows ([Sources by row class](#sources-by-row-class)), meets that state's rule for the property. Reference rows follow SRC-5 instead. The cell's state is its stated state, except on an overridden card-row cell, where it is `no` (OVR-4).
- ST-2. Silence is `not_stated`, never `no`. If the sources read say nothing that meets a rule, the cell is `not_stated` and lists what was read. A contradicting outcome does not change a `not_stated` cell (OVR-4, [Q5](#open-questions)).
- ST-3. A stated `no` requires a statement that the property does not hold. A reviewer's reading of a design, a product category ("runs in an enclave") or an absent feature is not such a statement. Every "or the design rules it out" clause of the prototype is removed (AGENTS.md rule 9). The only other source of `no` on a card row is a contradicting outcome recorded by the harness (OVR-4), which is a measurement of the configuration's verifier, not a reading of its design.
- ST-4. On a reference row only, a method that proves nothing and checks nothing (plain serving) is `no` on every property, and a method that proves nothing but checks (recompute) is `no` on Formally verified and Security level (SRC-7). On a card or public-source row, a statement that the system proves nothing sets `no` only on a property whose own No rule the quote meets.
- ST-5. Each stated limit is counted in one cell only. A limit counted in another cell is printed beside this one as an `aside` and does not change its state (for FlashProve, the clipped-gap policy is counted in Model bound and the one leaked bit in Weights hidden).
- ST-6. Trust and caveats every row shares do not change a state: the checker's own computer, compiler and build; which real, named model a commitment is. They are printed as text. A cell is judged for the configuration the row reads (SRC-1), not for another configuration of the same system.
- ST-7. Public parameters fixed before the hash are shared by every non-interactive proof. They set `partly` on No trusted party only where the documentation says its proved statement excludes a provider who tuned them ([Q1](#open-questions)).
- ST-8. Where two quotes in the allowed sources meet the rules of different states, the reviewer quotes both, the cell carries `conflict: true`, its reason says that the sources conflict, and its stated state is fixed by this table ([Q4](#open-questions)): `yes` with `partly` gives `partly`; `yes` with `no`, or `partly` with `no`, gives `no`. The quote of that state is the deciding quote. The table resolves one cell and is never applied across cells or rows. The override (OVR-4) then applies to the stated state the table gives.

### Properties

The six ids, in display order: `weights_hidden`, `model_bound`, `whole_output`, `formally_verified`, `security_level`, `no_trusted_party`. Each rule below is met only by what the documentation says (ST-1, ST-3). The "Controls" line of each property names the RFC-0008 controls that can contradict it ([control map](#negative-control-override)); a property no control can contradict is documentation only, and its state on a card row means stated at the pin for the configuration run, with no test behind it.

#### Weights hidden (`weights_hidden`)

- Question: does the checker learn nothing about the weights?
- Not covered: hiding the weights from the host operator (an enclave) is not this property.
- Yes: the documentation says the weights stay hidden from the checker in the default use, naming no leak beyond public settings.
- Partly: the documentation says they are hidden with a stated limit: a named leak, hiding shown for one policy or setting only, hiding optional per circuit, or hiding behind a commitment without the formal zero knowledge property.
- No: the documentation says the checker sees the weights, or that hiding is off or not provided. The prototype clause "or the design gives the checker the weights" is removed; recompute's No rests on RFC-0015's statement that its verifier holds the weights.
- Not stated: no statement about hiding the weights from the checker in the sources read.
- Controls: none; documentation only. Every RFC-0008 control observes a verdict or a prover failure, and none observes what the checker learns about the weights.

#### Model bound (`model_bound`)

- Question: is each checked token tied to the committed weights?
- Not covered: which real, named model the commitment is. FlashProve and SASH both say that stays outside their proof; it is printed as text.
- Yes: the documentation says a passing check ties each checked token to the committed weights exactly, in the configuration the row reads (the card's configuration for card rows; the default or expected use for public-source rows).
- Partly: tied with a stated limit: under one of several policies only, within a tolerance or bound, or shown only in empirical tests.
- No: the documentation says outputs are not tied to any weights, or that nothing is checked.
- Not stated: silent.
- Controls: C3, P1 and P2 (OVR-2). Each changes the weights, their commitment or their precision, the input this property's Yes rule names, and an accepted one is read as a passing check not tied to the committed weights. This is an assignment made by the control map, not something the outcome shows alone ([Q9](#open-questions)).

#### Whole output checked (`whole_output`)

- Question: does one check cover every output token of a request?
- Name: the prototype's "Whole output proved" is renamed, because the question asks what a check covers and a reference row's check proves nothing (AGENTS.md rule 10). The id stays `whole_output`.
- Not covered: which requests get a check (sampling, proving after the fact) is a deployment choice. The text before tokenizing and after detokenizing, which FlashProve and SASH both put outside their proof, is printed as text.
- Yes: the documentation says one check, or one joined set of checks, covers the prompt and every output token of a request.
- Partly: one check covers a stated part: the positions the client names, one segment, or one disputed step.
- No: the documentation says no output token is checked, or that nothing is checked.
- Not stated: silent, including a proved run whose output tokens the documentation does not name.
- Controls: C1, C2, C4 and C7 (OVR-2). Each changes the request, the prompt or the claimed output, the inputs this property's Yes rule names, and an accepted one is read as a check that does not cover the prompt and output it was verified for. This is an assignment made by the control map, not something the outcome shows alone ([Q9](#open-questions)).

#### Formally verified (`formally_verified`)

- Question: is the security argument for the row's configuration checked by a proof assistant?
- Not covered: a proof that the code itself is correct, which no row claims; it is printed as text. A statement the documentation makes only for another configuration of the same system (for example another verifier, RFC-0002 §Configuration identity 5) is printed as an `aside` and sets nothing (ST-6, SRC-1).
- Yes: the documentation says the soundness of the configuration the row reads is proved in a proof assistant (Lean, Coq, Isabelle or similar).
- Partly: machine-checked for a stated part only: one component, or a weaker statement than the one the system makes.
- No: the documentation says the argument is not machine-checked, that a machine check is planned only, or that its soundness evidence is review or tests and nothing else. On a reference row, ST-4.
- Not stated: silent.
- Controls: none; documentation only. The property is about the security argument, and a verdict cannot show whether an argument is machine-checked. An accepted control does not show whether the argument is machine-checked; it is printed on the system page and contradicts Model bound or Whole output checked where the control map says so.

#### Security level (`security_level`)

- Question: is a soundness level stated for the row's configuration, and proven?
- Not covered: the number itself, which is a quote in the claim card (INV-GLYPH-3). A level the documentation states only for another configuration of the same system is printed as an `aside` and sets nothing (ST-6, SRC-1).
- Yes: the documentation states a numeric soundness bound for the configuration the row reads and says it is proven, by hand or by machine, under named assumptions.
- Partly: a numeric level is stated but called conjectured, or stated only in code or configuration, or for part of the system. A level stated without saying it is proven or conjectured is Partly until [Q10](#open-questions) is resolved.
- No: the documentation says the settings give no meaningful soundness (for example a test-only setting). On a reference row, ST-4.
- Not stated: no level stated for the configuration.
- Controls: none; documentation only. A level bounds the probability that a false statement is accepted; RFC-0008 runs a fixed few trials per control (five for C6, RFC-0008 §Alternatives Considered 3) and measures no probability, and this RFC computes none (INV-GLYPH-3).

#### No trusted party (`no_trusted_party`)

- Question: does a check hold without trusting a chip maker, a setup ceremony or an honest party?
- Not covered: trust every row shares (ST-6), and where the commitment or the weights come from (see Model bound).
- Yes: the documentation says the check rests on cryptography alone or needs no trusted setup, and names no chip maker, setup or other party to trust.
- Partly: the documentation states a trusted input or condition that its proved statement does not cover: a setup file, public files the user must grant were fixed before the hash (ST-7), or one honest party among several.
- No: the documentation says the check verifies a hardware attestation against a chip maker's keys or certificate chain, or that the provider is trusted. The quote MUST state the dependency; "runs in a trusted execution environment" alone does not (ST-3). This replaces the prototype rule, which named a kind of check.
- Not stated: silent.
- Controls: none; documentation only. No RFC-0008 control changes a setup file, an attestation or another party's input: C3, P1 and P2 change the weights or their precision, and every other control changes the request, the claimed output or the proof.

### Sources by row class

#### Card rows (`claim_card_at_pin`)

- SRC-1. A card row names exactly one claim card by `card: {system, configuration, card_version}` (RFC-0002 §File and identity). Its states are for that card's configuration, the verifier included: a statement the documentation makes only for another configuration of the system (another acceptance policy or another verifier, RFC-0002 §Configuration identity 2 and 5) is printed as an `aside` and sets nothing. A system with several cards in a release has one row per card. This settles R3: FlashProve's card is `exact-match-cp-verify` (issue #69 is closed), so its cells are read for exact match under the C++ verifier `cp_verify`, and its Lean verifier statements set nothing on this row.
- SRC-2. Every quote of a card row, deciding, supporting or `aside`, is copied from the card's `upstream.repo` at the card's `upstream.commit`. This is AGENTS.md rule 9 ("copy what the system states at the pinned commit") and the rule INV-CLAIM-3 sets for the card. Its `sources_read` include that repository at that commit. This settles the SASH companion repository: `sg-ai-safety-hub/zk-inference-results` is not a source of a SASH card-row state, since the SASH card does not accept it (`systems/sash/claim.yaml` L5 to L6). It may appear in `sources_read` and in `outside_pin`. Should RFC-0002 be amended to let a card name companion repositories at full commits, SRC-2 follows it.
- SRC-3. A statement by the system outside the pin MAY be shown beside the cell as `outside_pin`, with a reason and quotes and no state. It never sets the cell's state, and it is never drawn in the glyph or in a state's ink. This settles R2 under AGENTS.md rule 9: the glyph and the card it reads say the same thing. SASH can be asked to state it in the repository (#42).
- SRC-4. A reviewer sets each card-row stated state from quotes. The card fields in the table below limit the stated states a cell may hold ([CRIT-6](#validation-rules-g2)); where the allowed set has one state, the cell's stated state MUST be it ([Q3](#open-questions)). The override (OVR-4) then applies; the card does not limit it.

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

### Negative control override

The third layer of a card-row state (INV-GLYPH-5). RFC-0008 runs the shared controls C1 to C8 and P1, P2, and the system-specific controls a system registers, against the verifier of each benchmarked configuration, and stores every outcome in the run's `controls.json`. These rules let a recorded outcome reach the glyph, and only in one direction: an outcome can contradict a stated property, and no outcome can confirm one.

- OVR-1. The override applies to card rows only. Reference systems run no controls (RFC-0015 §Reference systems: they have "no controls"), and public-source rows have no runs.
- OVR-2. Each control can contradict only the properties the control map below gives. The map is normative; a change to it, or a new RFC-0008 control, amends this table in the same pull request, and the validator's copy is tested against it (`test_control_map_matches_rfc`). Each control is assigned to the property whose Yes rule names the input the mutation changes: the request, the prompt or the claimed output (C1, C2, C4, C7) to Whole output checked; the weights, their commitment or their precision (C3, P1, P2) to Model bound. A control whose mutation changes only proof bytes (C5, C6, C8) names no such input. The assignment is this RFC's rule, not something an accepted outcome shows by itself: an accepted C1, for example, also fits a covered token that is not tied to the committed weights. One property per control keeps the rule mechanical ([Q9](#open-questions)).

| Control (RFC-0008) | Mutation | Property it can contradict | Why |
|---|---|---|---|
| C1 | change the claimed output token | Whole output checked | the check accepted a claimed output it was not made for; the changed input is an output token |
| C2 | change one prompt token in the request | Whole output checked | the check accepted a request it was not made for; the changed input is a prompt token, which the Yes rule covers |
| C3 | verify against the commitment of perturbed weights | Model bound | the check accepted a proof against a commitment it was not made for; the changed input is the weights' commitment |
| C4 | replay a valid proof for a different request | Whole output checked | the check accepted a request and output it was not made for; the changed input is the request |
| C5 | truncate the proof's largest part | none | see below |
| C6 | flip one bit in a part, 5 seeds | none | see below |
| C7 | swap the proofs of two requests in one batch | Whole output checked | as C4, inside one batch; the changed input is the request each proof is checked for |
| C8 | drop one part of the proof | none | see below |
| P1 | commit W, prove with W' | Model bound | the check accepted a proof made from weights other than the committed ones; the changed input is the weights |
| P2 | prove with a precision other than the committed one | Model bound | the check accepted a proof made at a precision other than the committed one; the changed input is the precision |
| system-specific (`fixture_proof`, `weakened_prover`) | registered in `systems/<name>/controls.yaml` | none ([Q7](#open-questions)) | `system-controls/1` names no property, and a `weakened_prover` control expects `accepted` |

C5, C6 and C8 corrupt proof bytes and change no input a Yes rule names. An accepted corrupted proof shows that the verifier accepted bytes other than the honest proof; it does not show which statement fails (a flipped bit may sit in bytes the statement does not depend on), and reading one property onto it would be an inference (AGENTS.md rule 9). Their outcomes, like every outcome, are printed on the system page (OVR-7) and an accepted one goes to disclosure (RFC-0008 §Disclosure). Weights hidden, Formally verified, Security level and No trusted party have no mapped control and stay documentation only, for the reasons each property's "Controls" line gives.

- OVR-3. A control contradicts when its stored record holds the outcome `accepted` (the control's `outcome`, or the `outcome` of any of its `trials`) and its `expected` set does not hold `accepted`. No other record contradicts, and no record raises a state:
  - `rejected`, and `invalid_call` or `prover_failed` where the expected set holds them: the control passed. A pass shows that one mutation was rejected (RFC-0008 §Non-Goals); it never raises a state, so a `not_stated` cell stays `not_stated`.
  - `no_verdict`, and `invalid_call` outside the expected set (for example on C1): the control failed, but nothing was accepted. Inconclusive; it never lowers a state.
  - `void` (the honest twin was not accepted, INV-CTRL-2), `not_applicable` and `error`: the control tested nothing. Never raises or lowers a state.
  - not run: a control absent from a run's `controls.json`, a run with no `controls.json`, and a control the system documents but the harness does not run (for example an upstream rejected-proof example listed in the adapter README and not registered, RFC-0008 Q4; a registered `fixture_proof` control is recorded `not_applicable`, RFC-0008 Q5). Never raises or lowers a state.
  Each of these is printed on the system page as recorded (OVR-7).
- OVR-4. A card-row cell whose stated state is `yes` or `partly`, with at least one contradicting outcome of a control mapped to its property, takes the state `no`, whatever the documentation says. The cell keeps its quotes, which still decide the stated state under ST-1 and ST-8 and are still bound by CRIT-6; it records the stated state in `stated` and the deciding evidence of `no` in `contradicted_by`, one entry per contradicting control and run. A cell whose stated state is `no` or `not_stated` is not changed: `no` already says the property does not hold, and `not_stated` states nothing to contradict ([Q5](#open-questions)). This RFC chooses `no` over a printed note beside the stated state, and over a new state, because: the overview draws the state and nothing else, so a note would leave Yes or Partly drawn on a configuration whose verifier accepted an input the property says it rejects, against INV-GLYPH-5; `no` is what was measured, an input the stated property excludes was accepted by the configuration as run; and a fifth state was rejected for the same reason as in SRC-7 (one vocabulary of four states). The stated state is not lost: the system page prints it with its quotes beside the control that contradicts it.
- OVR-5. The override is computed per configuration and per release. The criteria file names the release it is built for (`release`). The runs read for a card row are the runs listed in `releases/<r>/release.yaml` `runs` for that release and for every release whose `freeze_date` is earlier, whose `run.json` `claim.system` and `claim.configuration` equal the row's `card`, less every run in a read release's `superseded_runs` and every run named in the `replaces` of a read run (RFC-0009 §Append-only rule and corrections). Consequences:
  - With `release` set, every card row is a configuration the benchmark runs: its `card` system and configuration appear in the `claim_cards` of a read `release.yaml`, and at least one run is read for it. A card row lacking either is not benchmarked and fails CRIT-13; the pull request removes the row or the release adds the run (INV-GLYPH-5).
  - A contradiction carries into later releases of the same configuration. A later run that rejects the same control does not clear it, since the accepted mutation is reproducible from its recorded seed (INV-CTRL-3).
  - A card edit at the same pin (a new `card_version`) does not clear it. A new pin, or any other change listed in RFC-0002 §Configuration identity, is a new configuration and a new card row, which starts with no contradiction and reads only its own runs.
  - A correction run that replaces the contradicting run clears it, for example when RFC-0008 §Disclosure finds a fault in the adapter's verdict mapping.
  - A release never reads runs of a later release, and a published release is not edited (RFC-0009).
  - A file with no `release` reads no runs, and none of its cells is overridden.
- OVR-6. The system maintainers' reply (RFC-0009 §Right of reply) is printed on the system page beside every overridden cell of the system, unedited. The reply printed is the file that `releases/<release>/release.yaml` `replies` lists for the system, for the criteria file's `release`, also when the contradiction carries forward from an earlier release; a system with no listed reply has none printed. It does not change the cell. Only a run under OVR-5 does: a correction run, or a run of a new configuration. An objection follows RFC-0009 §Review window and RFC-0001.
- OVR-7. The overview draws each cell's state only. Except while a disclosure of the row is pending (OVR-8), the system page prints, for each cell: the stated state, its quotes and its sources read; for an overridden cell, each `contradicted_by` entry with its control id and run id, linked to the control's record in `controls.json`; and, for each control the map gives the property, its outcome in every run read, including passed, inconclusive, void, not applicable, error and not run, with "not run" printed for a mapped control no read run recorded. For a property with no mapped control, the page says that no RFC-0008 control tests it. The site computes these lists from the control map and the stored `controls.json` files; the criteria file holds only `stated`, `contradicted_by` and `disclosures`, which CRIT-13 recomputes or checks (AGENTS.md rule 3).
- OVR-8. While a disclosure is pending (RFC-0008 §Disclosure), the release states that it is pending without the details (`SECURITY.md` item 3). Drawing `no` on one property would reveal which kind of control was accepted, drawing the stated states would claim that no control contradicts them, and printing the outcome lists of OVR-7 would give the details. So a card row carries `disclosures`, one entry per read run whose `controls.json` has `disclosure_pending: true`. While any entry is `pending`:
  - no cell of the row carries `stated` or `contradicted_by`;
  - the overview draws the row's glyph with no state and no text; the glyph MUST NOT be drawn as any of the four states, Not stated included, since Not stated would claim the sources are silent;
  - the system page prints none of the outcome lists of OVR-7 for the row's read runs, only the RFC-0008 notice; the cells' stated states and quotes are printed with that notice and are not drawn;
  - the release page and the Controls page (RFC-0009 §Site) print the RFC-0008 notice.
  A row drawn with no state is not a fifth state: the cells keep their data, and the four-state vocabulary is unchanged. Once a run's finding is published, a pull request sets that run's entry to `published` with the date and the link of the publication; once no entry is `pending`, OVR-4 and OVR-7 apply. Since `controls.json` is append-only and each read run has its own entry, a later run with `disclosure_pending: true` adds a new `pending` entry and withholds the row again, whatever earlier entries say ([Q8](#open-questions)).

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
  "release": "v0.1",
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
     "disclosures": [{"run_id": "<run-id>", "state": "published", "date": "YYYY-MM-DD", "url": "https://..."}],
     "cells": {"weights_hidden": {"state": "not_stated", "reason": "Text", "quotes": [],
                                  "sources_read": [{"repo": "owner/repo", "commit": "<40-hex>", "paths": ["README.md"]}],
                                  "note": "Text", "conflict": false,
                                  "aside": {"words": "Text", "quotes": ["Quote"]},
                                  "outside_pin": {"reason": "Text", "quotes": ["Quote"]}},
               "whole_output": {"state": "no", "stated": "yes", "reason": "Text", "quotes": ["Quote"],
                                "contradicted_by": [{"control": "C1", "run_id": "<run-id>"}]}}},
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
- `release` (optional): the release id the file is built for (OVR-5), equal to a directory `releases/<release>/` holding a `release.yaml`. Absent until the first release is frozen; without it no run is read and no cell is overridden.
- `stated` and `contradicted_by` (card rows only, both or neither, OVR-4): `stated` is `yes` or `partly`, the stated state the quotes decide; the cell's `state` is then `no`. `contradicted_by` is a non-empty list of `{control, run_id}`, sorted by `control` then `run_id`, with no duplicate pair. `control` is a control id of the [control map](#negative-control-override) mapped to the cell's property; `run_id` is an RFC-0012 run id. The entries are recomputed by CRIT-13 and never edited by hand to differ.
- `disclosures` (card rows only, OVR-8): a non-empty list, one entry per read run whose `controls.json` has `disclosure_pending: true`, sorted by `run_id`, with no duplicate `run_id`. Each entry is `{run_id, state: "pending"}`, or `{run_id, state: "published", date, url}` with `date` a `"YYYY-MM-DD"` string and `url` an https link to the published finding. Absent when no read run has `disclosure_pending: true`.
- `conflict`: `true` only on a cell under ST-8; absent otherwise.
- `sources_read` entry: `{repo, commit, paths}` for a repository (paths or globs read) or `{url, retrieved}` for a web page.
- `not_copied: true` MAY replace `sources_read` on a `not_stated` cell of a public-source row where nothing was read yet ([Q2](#open-questions)).
- `workloads` (reference rows, required): workload ids present in the reference system's `system.yaml` (SRC-6). `own_sources` (public-source rows, required, non-empty): each entry one of `repo`, `domain` or `url`, with `how` (SRC-8).
- Removed from the prototype, each for a reason: `test_mapping`, `rows[].states` and `rows[].pencil` (derived from the cells and `source_class`; derived values are computed, not typed); `quote_check` (a typed count that no rule recomputes); `contrast` and `states.*.fill`, `.ink`, `.mark` (drawing, the site's; `web/words.css` holds the inks it uses); `status` (read from the RFC); `this_repository_commit` (moves into `pins`); `rules` and `risks` (now this RFC's normative text and dispositions); `outside_pin.state` (SRC-3); the `null` `repo`, `commit`, `path` and `lines` keys of web quotes.

### Validation rules (G2)

Each failure is a G2 finding with the rule id and the JSON pointer of the cell or quote. Shape failures (unknown state, unknown key, a number, a missing required field) are schema failures under the generic G2 rule. Semantic rules:

| Id | Rule | Error kind |
|---|---|---|
| `CRIT-1` | A cell whose stated state (`stated` if present, else `state`) is `yes`, `partly` or `no` has at least one quote; its first quote has `decides: true` and no other quote in the cell does. Quotes in `aside` and `outside_pin` have `decides: false`. A cell with `conflict: true` has at least two quotes, and its stated state is the one ST-8's table gives. Every quote has `checked: true`. | `config` |
| `CRIT-2` | A `repository` or `this_repository` quote has a 40-hex `commit` equal to `pins[repo]`, and its `url` contains that commit. Every `pins` entry is used by a quote or a `sources_read` entry. | `integrity` |
| `CRIT-3` | A `web` quote has an https `url`, a `retrieved` date not after the file's `date`, and an `archive_url` or a `copy` whose file exists and whose sha256 matches. A deciding quote of a public-source row comes from an entry of the row's `own_sources`: a `repository` quote's `repo` is a `repo` entry; a `web` quote's host equals a `domain` entry or its url starts with a `url` entry. | `integrity` |
| `CRIT-4` | A `not_stated` cell has no quote with `decides: true`, and exactly one of a non-empty `sources_read` or `not_copied: true`. `not_copied` appears only on public-source rows. | `config` |
| `CRIT-5` | A card row names a card that exists, at `systems/<system>/claim.yaml` or `systems/<system>/claims/<configuration>.yaml` (RFC-0002 §File and identity), whose own `system`, `configuration` and `card_version` equal the row's `card`. Every quote of the row outside `outside_pin` is in the card's `upstream.repo` at `upstream.commit`, and `sources_read` of each `not_stated` cell includes that repository at that commit. | `integrity` |
| `CRIT-6` | A card row's stated state (`stated` if present, else `state`) is in the set the [card fields table](#card-rows-claim_card_at_pin) allows for each card value. If [Q3](#open-questions) resolves to derived states, this rule recomputes each card-row stated state from the card and fails on any difference. | `integrity` |
| `CRIT-7` | A reference row's quotes are all `this_repository` quotes of `rfcs/0015-reference-rows.md`, and each quote's text also occurs, whitespace-normalised, in that file as it stands in the tree being validated. Its `workloads` all exist in its reference system's `system.yaml` and agree on whether `precision_substitution` is declared. Its states equal the [reference table](#reference-rows-reference_rfc_0015), with SRC-6 applied from those workloads. | `integrity` |
| `CRIT-8` | The text of each `this_repository` quote occurs, whitespace-normalised, in `git show <commit>:<path>` at its `lines`. CPU only, no network. A commit absent from the local object store is an `environment` error, never a pass. | `integrity` |
| `CRIT-9` | `order` equals the six ids of [Properties](#properties) in that order; `properties` holds exactly those ids in that order; every row has exactly those six cells; row ids are unique. | `config` |
| `CRIT-10` | No JSON number anywhere in the file, and no key named `total`, `score`, `rank`, `count`, `sum`, `average`, `mean` or `weight` (case-insensitive) at any depth. | `config` |
| `CRIT-11` | `outside_pin`, `stated`, `contradicted_by` and `disclosures` appear only on card rows. `workloads` appears only on reference rows, and `own_sources` only on public-source rows. | `config` |
| `CRIT-12` | A public-source row has `tab` `not_benchmarked` or `archived`; a card or reference row has `tab` `benchmarked`. | `config` |
| `CRIT-13` | Recomputes the override from the stored files (OVR-3 to OVR-5, OVR-8). If `release` is absent, no cell carries `stated` or `contradicted_by` and no row carries `disclosures`. Otherwise `releases/<release>/release.yaml` exists, and for each card row the validator collects the runs OVR-5 reads, from the `release.yaml` files, each run's `run.json` (`claim`, `replaces`) and its `controls.json` where present, each valid under its schema with its `run_id` equal to its directory name. The row's `card` system and configuration appear in the `claim_cards` of a read `release.yaml`, and at least one run is read for it; otherwise an `integrity` failure (OVR-5). For each property it computes the set of `{control, run_id}` pairs of contradicting outcomes (OVR-3) of controls mapped to that property (OVR-2). The set of `run_id` values in the row's `disclosures` equals the set of read runs whose `controls.json` has `disclosure_pending: true`, and the row carries no `disclosures` when that set is empty. If no entry is `pending`: a cell whose stated state is `yes` or `partly` and whose set is non-empty has `state: "no"` and `contradicted_by` equal to the set; every other cell has neither `stated` nor `contradicted_by`. While any entry is `pending`, no cell of the row has `stated` or `contradicted_by`. A listed run directory or a `controls.json` that cannot be read is an `environment` error, never a pass. Reply files are not read (OVR-6). | `integrity` |
| `CRIT-14` | A cell carries `stated` if and only if it carries `contradicted_by`; such a cell has `state: "no"` and `stated` `yes` or `partly`. Each `contradicted_by` entry names a control the [control map](#negative-control-override) maps to the cell's property, so a cell of Weights hidden, Formally verified, Security level or No trusted party never carries one; entries are sorted and unique. `disclosures` entries are sorted by `run_id` with no duplicate, and a `published` entry carries `date` and `url`. | `config` |

Upstream quotes (kind `repository` outside this repository, and `web`) are checked against their source by the reviewer, recorded in `checked_how`. CI does not fetch them (RFC-0012: validators never use the network). CRIT-13 reads only files in the tree being validated, so it runs in every CI job that has the tree.

### Data flow and lifecycle

1. A reviewer edits `web/_data/criteria.json` by pull request, quoting sources at the commits the row class allows.
2. `iproofs validate` runs G2 (schema and `CRIT-1` to `CRIT-14`) and G3 on it.
3. A claim card change (a new `card_version`) fails `CRIT-5` on that row until the row names the new version, so every card change forces a re-read of its row. An RFC-0015 change that moves a quoted sentence fails `CRIT-7` until the quotes and the reference table are amended.
4. When a release is frozen (RFC-0009 §Freeze algorithm), the pull request that builds its site sets `release` and adds every `stated`, `contradicted_by` and `disclosures` entry that `CRIT-13` requires; `CRIT-13` fails until it does. A later run that changes an override (a correction, OVR-5) changes the file in the next release's pull request.
5. When a pending disclosure is published, a pull request sets that run's `disclosures` entry to `published` and, once no entry of the row is `pending`, adds the cells' `stated` and `contradicted_by` (OVR-8). A new run with `disclosure_pending: true` adds a `pending` entry in its release's pull request.
6. `web/build.py` reads the states from the cells; the footer pins the file's sha256 as it does today.

Determinism: the rules read only the file, the claim cards, the reference `system.yaml` files, `rfcs/0015-reference-rows.md`, the `release.yaml`, `run.json` and `controls.json` files of the releases CRIT-13 reads, and git objects of this repository. No clock and no network; the release order comes from `freeze_date` in the files.

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
| A stated Yes kept while a mapped control was accepted in a read run, its disclosure published | `CRIT-13` fails until the cell is `no` with `stated` and `contradicted_by` |
| An override added, kept or dropped by hand (no matching record, a superseded or replaced run, a run of another configuration, a later release's run) | `CRIT-13` fails |
| A Not stated cell given `no` from an accepted control | `CRIT-13` fails (OVR-4, Q5); the outcome is printed on the system page |
| An override on Weights hidden, Formally verified, Security level or No trusted party, or from C5, C6, C8 or a system-specific control | `CRIT-14` fails (OVR-2) |
| An override drawn while its disclosure is pending | `CRIT-13` fails; the row carries a `pending` entry in `disclosures` and draws no state (OVR-8) |
| A second embargo on a row whose first disclosure is published | the new run adds a `pending` entry; `CRIT-13` fails until it does, and the row draws no state again (OVR-8) |
| A card row with no run of its configuration in the release | `CRIT-13` fails (OVR-5); the row is removed or the run added |
| A system team objects to an overridden cell | the reply is printed beside it (OVR-6); the cell changes only with a correction run or a new configuration |
| A release run directory or `controls.json` missing from the tree | `CRIT-13` gives an `environment` error, never a pass |

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
- **Audit the properties: an agent or a human reviewer certifies that a property holds.** Considered because an audit could judge statements the documentation leaves vague and catch a flaw the documentation does not mention. Rejected: it is certification, a non-goal ([PRD §5](../docs/PRD.md#5-non-goals)); it makes the benchmark the source of a security property, against AGENTS.md rule 9; a reader cannot recompute its result from stored files; and the benchmark's reviewers, human or agent, are not placed to audit a proof system's cryptography or code. The benchmark instead does what L2BEAT does for rollups: it checks that a claim is documented, that it is read for what actually runs, and that its own tests do not break it, and it prints each layer's evidence.
- **Show only measured quantities and drop the glyph.** Considered because a measurement needs no reading of documentation and no state vocabulary. Rejected: a proof that proves less is not comparable to one that proves more. "Inference proofs make different statements, so the claim has to travel with every number" ([PRD §2](../docs/PRD.md#2-vision)), and a reader who divides one headline by another learns nothing ([PRD §1](../docs/PRD.md#1-problem)). The glyph is the short form of the claim card on every row; the measured quantities sit beside it.
- **Print a contradiction as a note beside the stated state.** Considered because the documentation's own state stays in view. Rejected (OVR-4): the overview draws the state and nothing else, so Yes would stay drawn on a configuration whose verifier accepted an input the property excludes. The stated state is printed on the system page instead.
- **A fifth state, "Contradicted".** Rejected: one vocabulary of four states (SRC-7), and `no` with `contradicted_by` says what was measured.
- **Let a passed control raise a state, or confirm Yes.** Rejected: a passed control shows that one mutation was rejected (RFC-0008 §Non-Goals); reading more into it would turn a test into a certificate. A pass never raises a state (OVR-3).
- **Map C5, C6 and C8 to Model bound and Whole output checked.** Considered because an accepted corrupted proof is a defect. Rejected: it does not show which statement fails, so the mapping would be an inference (OVR-2). The outcome is printed and disclosed.
- **Clear a contradiction when a later run of the same configuration rejects the control.** Rejected: the accepted mutation is reproducible from its seed (INV-CTRL-3), so a later rejection does not undo it, and the rule would let a release keep the passing run and drop the other (OVR-5). A correction run that replaces the contradicting run, with its reason, clears it.
- **Move the criteria file out of `web/` (for example to `methodology/criteria.json`).** Considered because the file is methodology, not presentation. Rejected for now: `web/build.py` and the footer read it at its path, and moving it is churn with no change in meaning; #320 MAY move it with the generator.

## Drawbacks

- Re-reading is costly: every card change and every web quote needs a reviewer, and 65 Not stated cells need a list or a marker before the file validates.
- A thorough system collects Partly while a silent one shows Not stated (R1, R11). This RFC keeps that, because it is what the documentation says; the site has to explain that Not stated is not No.
- A rule that a No needs a statement, and that a card row reads only its own configuration, will move some cells to Not stated (candidates in [Migration / Rollout](#migration--rollout)), so the glyph shows less than a reader of the design might expect.
- Reference rows' states are set by definition in this RFC where RFC-0015 has no sentence to quote; a reader must trust the project's own description of its baselines.
- Two properties stay reviewer-set for card rows, with little mechanical check beyond the commit pin.
- Controls reach two properties only. Weights hidden, Formally verified, Security level and No trusted party stay documentation only, so their Yes has no test behind it; the system page says so (OVR-7).
- The override is one way and coarse. Passing controls show little (a few seeded mutations per control, RFC-0008 §Drawbacks), and an accepted control sets No even where the documentation states a limit that may cover the mutation (Q6).
- A pending disclosure removes a row's states from its glyph for the length of the embargo, up to 90 days by default (OVR-8, RFC-0008 §Disclosure).

## Conflicts of Interest

The author's affiliation and any interest in a measured system are to be declared in `MAINTAINERS.md` before this RFC enters Last call (RFC-0001); the author is not yet listed there. This text was drafted with an AI agent, Claude, made by Anthropic. Anthropic publishes FlashProve (`anthropics/FlashProve`), one of the two systems with a card row. Reviewers should weigh the decisions that move FlashProve cells with that in mind: SRC-1 on R3, which reads FlashProve for its `exact-match-cp-verify` configuration and so takes its Formally verified and Security level off Yes (the prototype read both from the Lean verifier's statements); and ST-7 and Q1 on R6. The control map (OVR-2) and Q5 to Q9 apply to every card row alike; FlashProve's Model bound and Whole output checked, and SASH's, are the cells a control can contradict, and SASH's registered controls are the ones Q7 leaves unmapped.

## Migration / Rollout

Two pull requests, in order (issue #318). This one adds the RFC and its index rows only. The second opens once this RFC is in Last call and merges only once it is Accepted (RFC-0001 §RFC lifecycle rule 3, INV-GOV-3). It adds the schema and examples, the `CRIT-n` rules and the validator's copy of the control map, `harness/tests/unit/test_criteria.py`, the RFC-0012 catalogue row and the RFC-0013 G2 input, rewrites `web/_data/criteria.json` to `criteria/1`, and updates `web/README.md` (§Open and the criteria text) and `docs/spec/10-glossary.md` (the six properties and four states). Its description lists every state that changes, by row, and every cell edited to pass the new rules.

Counts in the committed file (sha256 starting `4ced468b`, at `356949a5ee8afe328ee2cb0d68b18be1b1d82453`), recomputed by:

```sh
python3 -I -c 'import json;d=json.load(open("web/_data/criteria.json"));c=[(r,c) for r in d["rows"] for c in r["cells"].values()];print(sum(1 for r,x in c if x["state"]!="grey" and x["quotes"] and all(q["kind"]=="web" for q in x["quotes"])), sum(1 for r,x in c if x["state"]=="grey" and not x.get("searched")))'
```

which prints `13 65`. Of 138 cells (23 rows of 6): card rows 4 Yes, 5 Partly, 3 Not stated; reference rows 3 Yes, 9 No; public-source rows 14 Yes, 7 Partly, 3 No, 90 Not stated.

What fails the new rules, and what the second pull request does:

1. Key and field changes, no state change:
   - `green`, `amber`, `red`, `grey` to `yes`, `partly`, `no`, `not_stated`; property rule text moves under `properties[].rules`; the name "Whole output proved" becomes "Whole output checked" in `criteria.json`, which every page reads it from.
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
9. The site, changed with the data so the build still passes and its output is committed:
   - `iproofs.site.inputs.load_criteria` is the one place that reads the file (#320). It drops `STATE_OF`, the map from colour ids to state ids, and its checks of the derived `test_mapping` and `rows[].states`; it reads `criteria/1` (`properties[].rules` keyed by state id, `sources_read`, `workloads`, `own_sources`) and keys each card row by its `card`, so a system with two cards has two rows. The renderer (`web/build.py`) already reads state ids only.
   - the `PHRASES` entries of `web/build.py` that quote criteria text are updated to the new rule and note text, or removed with the text they rewrite, since its `setup` asserts that each still occurs in the data.
   - the rebuilt pages are committed: `web/criteria.html`, every page whose glyph or property name changes, and every page's footer, which pins the criteria file's sha256. `git status --porcelain -- web` then prints nothing.
10. Override: at `356949a5`, no `releases/` directory exists and no run directory under `results/v0.1/` holds a `controls.json`. The rewritten file has no `release`, no cell carries `stated` or `contradicted_by`, no row carries `disclosures`, and no state changes under OVR-1 to OVR-8. Until the first release, the two card rows' states are stated at the pin for each card's configuration, with no run yet (INV-GLYPH-5); once `release` is set, CRIT-13 requires a read run for each. `CRIT-13` and `CRIT-14` are tested on hand-made release trees. The system-page lists of OVR-7 come with the site generator (#320); until a release exists they print "not run" for every mapped control. `systems/sash/controls.yaml` registers `weakened_prover` controls that expect `accepted`; they set nothing (OVR-2, Q7).

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
- `valid/overridden-cell.json`: a card row with `release`, a Whole output checked cell with `state: "no"`, `stated: "yes"` and one `contradicted_by` entry; passes the schema.
- `valid/disclosure-pending.json`: a card row with `disclosures: [{run_id, state: "pending"}]` and no override; passes the schema.
- `invalid/stated-not-stated.json`: a cell with `stated: "not_stated"`; fails on enum.
- `invalid/contradicted-by-empty.json`: `contradicted_by: []`; fails on `minItems`.
- `invalid/contradicted-by-trial-number.json`: a `contradicted_by` entry with `"trial": 0`; fails on `additionalProperties` (and `CRIT-10`).
- `invalid/disclosure-published-no-url.json`: a `disclosures` entry `{run_id, state: "published", date}`; fails on `required`.
- `invalid/disclosure-no-run-id.json`: a `disclosures` entry `{state: "pending"}`; fails on `required`.

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
- `test_control_map_matches_rfc` (OVR-2): the validator's control map equals the control map in this RFC, parsed from the markdown.
- `test_accepted_c1_overrides_whole_output` (`CRIT-13`): a release whose `controls.json` records C1 `accepted` against a card whose Whole output checked is `yes`; the stored `controls.json` has `disclosure_pending: true` and the row carries its `disclosures` entry with `state: "published"`; the cell passes only as `state: "no"`, `stated: "yes"`, `contradicted_by: [{control: "C1", run_id}]`, and fails left at `yes`.
- `test_accepted_c3_overrides_model_bound` and `test_accepted_p1_overrides_model_bound` (`CRIT-13`), on a `partly` Model bound cell; the stored `controls.json` has `disclosure_pending: true` and the row carries its `disclosures` entry with `state: "published"`.
- `test_each_mapped_control_overrides_its_property` (`CRIT-13`), parametrised over C1, C2, C3, C4, C7, P1 and P2: with the control `accepted` and its disclosure published, the override is required on the mapped property and any `contradicted_by` on the other five properties fails.
- `test_c6_one_trial_accepted_sets_nothing` (`CRIT-13`, `CRIT-14`): one C6 trial `accepted` (and C5, C8 `accepted`); the stored `controls.json` has `disclosure_pending: true` and the row carries its `disclosures` entry with `state: "published"`; any `contradicted_by` fails, and the cells keep their stated state.
- `test_non_accepting_outcomes_set_nothing` (`CRIT-13`): for each of `rejected`, `prover_failed`, `invalid_call` (in and out of the expected set), `no_verdict`, `void`, `not_applicable` and `error`, and for a mapped control absent from `controls.json` and a run with no `controls.json`, a cell with `contradicted_by` fails and the stated state passes.
- `test_pass_does_not_raise_not_stated` (`CRIT-13`): a `not_stated` Model bound cell with C3 `rejected` stays `not_stated`; set to `yes` without a quote it fails `CRIT-1`.
- `test_not_stated_and_no_cells_not_overridden` (`CRIT-13`): with C3 `accepted`, a `not_stated` or stated `no` Model bound cell carrying `stated` or `contradicted_by` fails.
- `test_expected_accepted_sets_nothing` (`CRIT-13`): a `weakened_prover` control with `expected: ["accepted"]` and outcome `accepted` sets nothing.
- `test_other_configuration_run_ignored` (`CRIT-13`): an accepted C1 in a run whose `claim.configuration` differs from the row's card sets nothing, and that run's `disclosure_pending: true` requires no `disclosures` entry on the row; a run with the same configuration and another `card_version` does set it, with the row carrying its `disclosures` entry with `state: "published"`.
- `test_superseded_and_replaced_runs_ignored` (`CRIT-13`): an accepted C1 in a run listed in `superseded_runs`, or named in a read run's `replaces`, sets nothing.
- `test_override_carries_to_later_release` (`CRIT-13`): an accepted C1 in `v0.1` (the stored `controls.json` has `disclosure_pending: true` and the row carries its `disclosures` entry with `state: "published"`) overrides the cell in a file built for `v0.2`, also when `v0.2` holds a run of the same configuration with C1 `rejected`.
- `test_later_release_not_read` (`CRIT-13`): a file built for `v0.1` ignores an accepted C1 in a run of `v0.2`.
- `test_no_release_no_override` (`CRIT-13`): a file without `release` that carries `contradicted_by` or `disclosures` fails.
- `test_disclosure_pending_withholds_override` (`CRIT-13`): with `disclosure_pending: true` in a read `controls.json`, a row without a `disclosures` entry for that run fails, and an entry for a run that has no `disclosure_pending: true` fails; with `pending`, a cell carrying `contradicted_by` fails and the stated states pass; with `published`, the override is required.
- `test_new_pending_disclosure_after_published_withholds` (`CRIT-13`): a row whose `v0.1` run has a `published` entry, in a file built for `v0.2` where a new run of the same configuration has `disclosure_pending: true`; the row without a `pending` entry for the new run fails, and with it any `contradicted_by` fails.
- `test_card_row_without_run_fails` (`CRIT-13`): with `release` set, a card row whose configuration is in no read `claim_cards`, or has no read run, fails.
- `test_reply_does_not_change_cell` (`CRIT-13`, OVR-6): adding `systems/<name>/replies/<release>.md` changes no finding.
- `test_missing_controls_file_is_environment_error` (`CRIT-13`): a listed run directory absent from the tree gives an `environment` error.
- `test_contradicted_by_on_documentation_only_property_fails` (`CRIT-14`): a `contradicted_by` on Weights hidden, Formally verified, Security level or No trusted party fails, and one naming C5 on Model bound fails.
- `test_stated_without_contradicted_by_fails` (`CRIT-14`), and `test_override_on_public_row_fails` (`CRIT-11`).
- `test_overridden_cell_quotes_decide_stated` (`CRIT-1`, `CRIT-6`): on an overridden cell, the deciding quote and the card's allowed set are checked against `stated`, not `state`.
- Site tests, added with the site generator (#320): `test_pending_row_draws_no_state` (a row with a `pending` entry is drawn as none of the four states) and `test_pending_row_renders_no_outcome` (while an entry is `pending`, no control outcome of the row's read runs is rendered on the system page, and the RFC-0008 notice is).
- `test_committed_file_passes`: `web/_data/criteria.json` passes every rule. It needs the git objects of the commits quoted, so it runs where full history is present: the `validate` CI job (`fetch-depth: 0`), or a test job given `fetch-depth: 0`. In a shallow clone it is skipped with the reason printed, and `CRIT-8` reports the missing commits as `environment` errors, never as a pass.

Repository checks, as issue #318 lists them: `uv run iproofs validate --all`; `uv run pytest harness/tests/unit/test_criteria.py harness/tests/unit/test_rfc_status.py harness/tests/unit/test_gate_links.py`; `uv run ruff check`; `uv run mypy harness/src`; `cd web && python3 -I build.py && python3 -I test_sort_keys.py && python3 -I test_cards.py && python3 -I test_search.py`, then `git status --porcelain -- web` prints nothing.

## Open Questions

- OPEN QUESTION Q1 (owner: 0xchqrles, resolve by: 2027-01-31): do public parameters fixed before the hash count as a trusted input (R6)? Option (a) treats them as a shared caveat printed as text; option (b) sets Partly only where the documentation says its proved statement excludes a provider who tuned them. Default until resolved: (b) (ST-7). Reason: it copies a condition the documentation states ("that you grant", FlashProve `guide/what-is-proved.md` L288 to L289 at `9e2bdd8f`); (a) would drop a stated condition. The cost is that a system which states the condition shows Partly while one that does not shows Not stated; the reason text says so, and other teams are invited to state their assumptions.
- OPEN QUESTION Q2 (owner: 0xchqrles, resolve by: 2027-01-31): does "not copied yet" stay a Not stated case, or does the site show it apart from silence? Default until resolved: it stays the state `not_stated` (four states only) and the cell carries `not_copied: true`, so the data tells "not read yet" from "read and silent" (CRIT-4); the printed word stays "Not stated", and whether a page prints the difference is the site's (#319). Reason: printing both the same way would claim sources were read that were not, and a fifth state was rejected (SRC-7).
- OPEN QUESTION Q3 (owner: 0xchqrles, resolve by: 2027-01-31): are card-row states derived from card fields, or set by a reviewer from quotes? Default until resolved: set by a reviewer from quotes, within the sets of the card fields table (SRC-4, CRIT-6). Reason: Whole output checked has no card field to derive from, Formally verified has one that only excludes `yes`, and three properties need a reading of free text; derivation would need RFC-0002 fields that do not exist. If resolved to derived, CRIT-6 recomputes every card-row state from the card.
- OPEN QUESTION Q4 (owner: 0xchqrles, resolve by: 2027-01-31): when two allowed quotes meet the rules of different states, which state does the cell take? Default until resolved: the fixed table of ST-8 (`yes` with `partly` gives `partly`; `yes` with `no`, or `partly` with `no`, gives `no`), with `conflict: true` and both quotes printed. Reason: the state is then met by a quote of the system's own, needs no reviewer judgement, and never says more than the more limited of the two statements; the alternatives (the reviewer picks, or the cell becomes Not stated) either add a judgement or hide two statements the system made.
- OPEN QUESTION Q5 (owner: 0xchqrles, resolve by: 2027-01-31): does a contradicting outcome change a `not_stated` cell? Default until resolved: no (OVR-4); the cell stays `not_stated` and the outcome is printed beside it on the system page. Reason: the benchmark validates claims, and a silent system states nothing to contradict; printing `no` would let the benchmark set a property the system does not state (AGENTS.md rule 9). The cost: a silent system with an accepted control draws Not stated where a system that states the property draws No. The system page and the Controls page print every accepted control in full once its disclosure is published (OVR-7, RFC-0009 §Site, RFC-0008 §Reporting), so the outcome is not hidden.
- OPEN QUESTION Q6 (owner: 0xchqrles, resolve by: 2027-01-31): what if the documentation states a limit that covers the mutation, for example a tolerance policy that admits the C3 one-unit perturbation, or a check of the positions the client names that leaves out the token C1 changes? Default until resolved: the override applies (OVR-4), the cell's system page prints the stated limit beside the control, and the case goes to RFC-0008 for a per-configuration expected set. Reason: the expected sets are RFC-0008's and the same for every system; deciding here whether a limit covers a mutation would add a reviewer judgement to a mechanical rule, and RFC-0008 already treats the acceptance as a possible defect sent to disclosure.
- OPEN QUESTION Q7 (owner: 0xchqrles, resolve by: 2027-01-31): can a system-specific control contradict a property? Default until resolved: no (OVR-2); its outcome is printed on the system page. Reason: `system-controls/1` names no property, a `weakened_prover` control expects `accepted`, and its failure (accepted while the binding report marks the edge bound) contradicts the card's binding table, not one glyph property. An RFC-0008 amendment MAY add a property field to `system-controls/1`, copied from the upstream description at the pin, and this table then follows it.
- OPEN QUESTION Q8 (owner: 0xchqrles, resolve by: 2027-01-31): how is the end of an embargo recorded? Default until resolved: `disclosures` on the card row, one entry per read run with `disclosure_pending: true`, authored by pull request (OVR-8), since `controls.json` is append-only and RFC-0008 records no end. Reason: the row then shows neither the details nor an uncontradicted glyph while an embargo runs, and one entry per run keeps a second embargo apart from a first that is published. If RFC-0008 gains a disclosure record, CRIT-13 reads it and `disclosures` is derived from it. The owner should confirm that drawing no state on a row during an embargo is acceptable.
- OPEN QUESTION Q9 (owner: 0xchqrles, resolve by: 2027-01-31): is the assignment of OVR-2 the one intended: C1, C2, C4 and C7 to Whole output checked only, and C3, P1 and P2 to Model bound only? Default until resolved: yes, by the rule that a control is assigned to the property whose Yes rule names the input the mutation changes. Reason: one property per control keeps CRIT-13 mechanical and needs no reading of why a verifier accepted. The cost: an accepted C1, C4 or C7 also fits a check that covers the token but does not tie it to the committed weights, and the map does not lower Model bound for it. Mapping one control to two properties would lower a state the outcome does not single out.
- OPEN QUESTION Q10 (owner: 0xchqrles, resolve by: 2027-01-31): which state does Security level take when the documentation states a numeric level for the row's configuration but says neither that it is proven nor that it is conjectured? The Partly rule lists three cases (called conjectured, stated only in code or configuration, stated for part of the system) and the Not stated rule says no level is stated, so neither fits. Default until resolved: Partly. Reason: a level is stated, so Not stated would hide a statement the system made, and Yes asks the documentation to say the level is proven, which it does not. The cost: such a level is drawn as a conjectured one is. The case was met reading Attestable's blog post ("uphold 100 bits of security", #336); its cell cites this question in its note.

## References

- [RFC-0001](0001-process-and-governance.md) §Changes to methodology, §RFC lifecycle, §Conflicts of interest.
- [RFC-0002](0002-claim-card.md) §File and identity, §Fields, §Rules (INV-CLAIM-2, INV-CLAIM-3), §Configuration identity, §Alternatives Considered.
- [RFC-0008](0008-negative-controls.md) §Shared controls, verifier side, §Shared controls, prover side, §Honest twins, §Outcomes, §controls.json, §System-specific controls, §Disclosure, §Non-Goals, INV-CTRL-2, INV-CTRL-3.
- [RFC-0009](0009-results-and-publication.md) for the site, §Storage, §Append-only rule and corrections, §Release record, §Review window, §Right of reply; its amendment for the live site is #319.
- [RFC-0010](0010-harness-runner.md) error kinds (`config`, `integrity`, `environment`).
- [RFC-0012](0012-schemas-and-serialization.md) §Schema catalogue, §The `schema` field, §YAML subset for authored files (dates), §JSON writer.
- [RFC-0013](0013-validation-and-ci.md) §G2 Schema validation, §G3 JSON format check.
- [RFC-0015](0015-reference-rows.md) §Reference systems, §Plain serving, §Recompute, §Precision matching, §Feasibility on the profile.
- AGENTS.md hard rules 3, 9 and 10. [PRD](../docs/PRD.md) §1, §2 and §5.
- `systems/sash/controls.yaml` (`system-controls/1`).
- `web/_data/criteria.json` (prototype criteria, sha256 starting `4ced468b`); at `356949a5`, the `glyph` object of the site's data snapshot under `web/_data/`, `web/build.py` L41 to L44, L505 to L523, L912, L969 and L1516 to L1535, and `web/README.md` §Data; since #320, `iproofs.site.inputs.load_criteria`.
- `systems/flashprove/claim.yaml` and `systems/sash/claim.yaml`, card version 1 each; `systems/ref-serve/system.yaml` and `systems/ref-recompute/system.yaml`.
- `.github/workflows/ci.yml` (`validate` job, `fetch-depth: 0`).
- FlashProve at `9e2bdd8ff5bf9c62f18263d7dac189b0400b260c`; SASH zk-inference-prover at `eb95bfa887299d1637550228d42086c27cbb2b3b`; SASH zk-inference-results at `11decec3c0b62c707618aab5deb82750b355d202`.
- Issues #318 (this RFC), #319, #320, #321, #42, #69.
