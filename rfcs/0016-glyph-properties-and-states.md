# RFC-0016: Glyph properties and states

- Authors: 0xchqrles
- Created: 2026-11-07
- Requires: RFC-0002, RFC-0008, RFC-0009, RFC-0012, RFC-0013, RFC-0015

## Summary

The public site draws every row as a glyph: six properties (Weights hidden, Model bound, Whole output checked, Formally verified, Security level, No trusted party), each in one of four states, printed Yes, Partly, No and Not stated. This RFC fixes the rules behind those states, which `web/_data/criteria.json` records. The benchmark validates claims; it does not audit them. A state on a claim card row means three things at once: the property is stated by the system at its pin, it is read for the configuration the benchmark runs (verifier included), and the benchmark's own negative controls (RFC-0008) do not contradict it; a reference row's state describes the benchmark's own method (SRC-5), and a public-source row's state is stated by its authors and not run (INV-GLYPH-5). A state is not an audit of cryptographic soundness or zero knowledge, not a probability that the property holds and not a security level of the benchmark's own. This RFC fixes each property's question, what it does not cover, the rule for each state and which controls can contradict it; one state vocabulary; that there is no total, score, count or order over states and no number on a property; the source of a state for each row class (claim card rows, reference rows, public-source rows); that a card row is read for its card's configuration and quotes only the card's pin; the override rule, by which a control the configuration's verifier accepted where RFC-0008 expects rejection sets No on a property stated Yes or Partly, whatever the documentation says; what a web quote carries in place of a commit, and that it comes from the system's own authors; and the contract of the criteria file (`schema: "criteria/1"` and its schema). The schema is the check on that file.

## Motivation

Evidence, all at this repository's commit `356949a5ee8afe328ee2cb0d68b18be1b1d82453` unless stated:

- No RFC and no section of `docs/spec/` names the six properties.
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
5. A card says Whole output checked Yes, and in a release the configuration's verifier accepts C1 (a changed output token). The glyph must not keep saying Yes, and the system page must show the quote, the control and the run side by side.

## Goals

- A state on a claim card row means: stated by the system at its pin, for the configuration the benchmark runs, and not contradicted by the benchmark's own tests; a reference row's state describes the benchmark's own method (SRC-5), and a public-source row's state is stated by its authors and not run (INV-GLYPH-5). The benchmark validates claims and does not audit them.
- Each of the six properties has a question, a not-covered note, a written rule for each of the four states and the list of controls that can contradict it, or a statement that none can ([Properties](#properties)).
- A state on a system's row is set only from a quote of that system's own documentation, never from the benchmark's reading of a design (AGENTS.md rule 9), with one exception: a recorded negative control outcome that contradicts a stated Yes or Partly sets No (OVR-4). A reference row's states are set by RFC-0015 and this RFC, which document the benchmark's own methods.
- The override is mechanical: every overridden cell follows from the stored `controls.json` files of the release, and no reviewer judgement sets or clears it.
- One state vocabulary: one id and one printed word per state. The four states are unordered.
- No total, score, count, average or order over states; no number on a property.
- For each row class, a named source of states; for card rows, the claim card fields each property reads and the states those fields allow.
- A criteria file that validates under G2 against its schema (`criteria/1`).

## Non-Goals

- How the glyph is drawn: shapes, inks, contrast, slice geometry, motion. That is the site's (RFC-0009, amended by #319), within INV-GLYPH-1. This RFC fixes only the printed word of each state and that silence is never printed or drawn as No.
- The family vocabulary (`proved`, `re_executed`, `attested`, `fingerprinted`, `unchecked`) and which tab a row sits in.
- The site data generator and the split of the site build (#320, #321).
- Claim cards for the 19 systems not benchmarked yet.

- Judging whether a system's documentation is correct. The glyph reports what the documentation states, like the claim card it reads (RFC-0002 §Non-Goals), and whether the benchmark's own controls contradict it.
- An audit. No state, page or file of this RFC is an audit result of cryptographic soundness, of zero knowledge, of a formal proof or of code; a probability that a property holds; or a security level assigned by the benchmark (INV-GLYPH-3, [PRD §5](../docs/PRD.md#5-non-goals)). A control that rejects shows that one mutation was rejected, nothing more (RFC-0008 §Non-Goals), so it never raises a state.
- New controls, or changes to a control's algorithm or expected set. Those are RFC-0008's; this RFC only maps its controls to properties.

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

- INV-GLYPH-1. There is no total, score, rank, count, sum or average over states, across properties or across rows. No page, file or report computes one. The criteria file holds no key named `total`, `score`, `rank`, `count`, `sum`, `average`, `mean` or `weight`. No drawing encodes a state by an amount of fill or area that adds up across properties; each state is told apart by ink or pattern. The shapes themselves are the site's (#319).
- INV-GLYPH-2. Properties carry no numbers. The order of `order` is the clockwise display order and nothing else; it is not a priority or a weight. The criteria file holds no number-typed value at all. The site generator (#320) prints none: the view it renders (`iproofs.site.view`) holds no property number, and the data snapshot that held `glyph.properties[].n`, `glyph.key.numbers` and numbered `aria` strings (`web/_data/` at `39662bf6`) is gone.
- INV-GLYPH-3. Security level shows only whether a level is stated and whether the documentation says it is proven. It never shows, compares or computes a level of its own; the level itself is a quote in the claim card (RFC-0002 `security.level`), and benchmark-assigned levels are rejected (RFC-0002 §Alternatives Considered).
- INV-GLYPH-4. Rows are never ordered by their states. Row order is set by the site (RFC-0009).
- INV-GLYPH-5. A state is a validated claim, not a certificate. On a card row it reads: stated by the system at its pin (SRC-2), for the configuration the benchmark runs (SRC-1, OVR-5), and not contradicted by the benchmark's negative controls (OVR-4). Before the first release a card row's states are stated at the pin for the card's configuration, with no run yet (OVR-5). On a public-source row it reads: stated by the system's own authors (SRC-8), not run by the benchmark. On a reference row it describes the benchmark's own method (SRC-5). No state is an audit result, a probability of correctness or a benchmark-assigned level (§Non-Goals). The overview draws the state and nothing else; the quotes, sources and control outcomes behind it are printed on the system page (OVR-7).

### States

One vocabulary, used in the criteria file and on every page. The criteria file uses these ids. The four states are unordered: none counts as more or less than another, and no rule in this RFC compares two states except ST-8, inside one cell. The override adds no state: an overridden cell is `no` (OVR-4).

| Id | Printed word | Meaning | Replaces |
|---|---|---|---|
| `yes` | Yes | The documentation says the property holds, by the property's Yes rule, and no control contradicts it. | `green`, "holds" |
| `partly` | Partly | The documentation says it holds with a limit it states, by the property's Partly rule, and no control contradicts it. | `amber`, "partly" |
| `no` | No | The documentation says it does not hold, by the property's No rule; or the documentation says it holds, fully or partly, and a negative control of the benchmark contradicts it (OVR-4). | `red`, "does not hold" |
| `not_stated` | Not stated | The sources read say nothing that meets any of the three rules above, or they have not been read yet ([Q2](#decisions)). | `grey`, "not stated" |

State rules, for every property:

- ST-1. A cell's stated state is `yes`, `partly` or `no` only when a deciding quote, copied verbatim from a source the row class allows ([Sources by row class](#sources-by-row-class)), meets that state's rule for the property. Reference rows follow SRC-5 instead. The cell's state is its stated state, except on an overridden card-row cell, where it is `no` (OVR-4).
- ST-2. Silence is `not_stated`, never `no`. If the sources read say nothing that meets a rule, the cell is `not_stated` and lists what was read. A contradicting outcome does not change a `not_stated` cell (OVR-4, [Q5](#decisions)).
- ST-3. A stated `no` requires a statement that the property does not hold. A reviewer's reading of a design, a product category ("runs in an enclave") or an absent feature is not such a statement. Every "or the design rules it out" clause of the prototype is removed (AGENTS.md rule 9). The only other source of `no` on a card row is a contradicting outcome recorded by the harness (OVR-4), which is a measurement of the configuration's verifier, not a reading of its design.
- ST-4. On a reference row only, a method that proves nothing and checks nothing (plain serving) is `no` on every property, and a method that proves nothing but checks (recompute) is `no` on Formally verified and Security level (SRC-7). On a card or public-source row, a statement that the system proves nothing sets `no` only on a property whose own No rule the quote meets.
- ST-5. Each stated limit is counted in one cell only. A limit counted in another cell is printed beside this one as an `aside` and does not change its state (for FlashProve, the clipped-gap policy is counted in Model bound and the one leaked bit in Weights hidden).
- ST-6. Trust and caveats every row shares do not change a state: the checker's own computer, compiler and build; which real, named model a commitment is. They are printed as text. A cell is judged for the configuration the row reads (SRC-1), not for another configuration of the same system.
- ST-7. Public parameters fixed before the hash are shared by every non-interactive proof. They set `partly` on No trusted party only where the documentation says its proved statement excludes a provider who tuned them ([Q1](#decisions)).
- ST-8. Where two quotes in the allowed sources meet the rules of different states, the reviewer quotes both, the cell carries `conflict: true`, its reason says that the sources conflict, and its stated state is fixed by this table ([Q4](#decisions)): `yes` with `partly` gives `partly`; `yes` with `no`, or `partly` with `no`, gives `no`. The quote of that state is the deciding quote. The table resolves one cell and is never applied across cells or rows. The override (OVR-4) then applies to the stated state the table gives.

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
- Controls: C3, P1 and P2 (OVR-2). Each changes the weights, their commitment or their precision, the input this property's Yes rule names, and an accepted one is read as a passing check not tied to the committed weights. This is an assignment made by the control map, not something the outcome shows alone ([Q9](#decisions)).

#### Whole output checked (`whole_output`)

- Question: does one check cover every output token of a request?
- Name: the prototype's "Whole output proved" is renamed, because the question asks what a check covers and a reference row's check proves nothing (AGENTS.md rule 10). The id stays `whole_output`.
- Not covered: which requests get a check (sampling, proving after the fact) is a deployment choice. The text before tokenizing and after detokenizing, which FlashProve and SASH both put outside their proof, is printed as text.
- Yes: the documentation says one check, or one joined set of checks, covers the prompt and every output token of a request.
- Partly: one check covers a stated part: the positions the client names, one segment, or one disputed step.
- No: the documentation says no output token is checked, or that nothing is checked.
- Not stated: silent, including a proved run whose output tokens the documentation does not name.
- Controls: C1, C2, C4 and C7 (OVR-2). Each changes the request, the prompt or the claimed output, the inputs this property's Yes rule names, and an accepted one is read as a check that does not cover the prompt and output it was verified for. This is an assignment made by the control map, not something the outcome shows alone ([Q9](#decisions)).

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
- Partly: a numeric level is stated but called conjectured, or stated only in code or configuration, or for part of the system. A level stated without saying it is proven or conjectured is Partly ([Q10](#decisions)).
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
- SRC-4. A reviewer sets each card-row stated state from quotes. The card fields in the table below limit the stated states a cell may hold; where the allowed set has one state, the cell's stated state MUST be it ([Q3](#decisions)). The override (OVR-4) then applies; the card does not limit it.

Claim card fields each property reads (RFC-0002 §Fields). A card value not named in the last column allows all four states.

| Property | Card fields read | States the card allows | Derivable from the card alone |
|---|---|---|---|
| Weights hidden | `zero_knowledge.claimed`, `.hidden`, `.not_hidden`, `.status`; `sources.zero_knowledge*` | `claimed: "not stated"` allows {`not_stated`}; `claimed: false` allows {`partly`, `no`} | Partly: Not stated is; `partly` against `no` needs the quote under the property rules, and `yes` against `partly` a reading of `not_hidden` |
| Model bound | `relation`, `coverage.policy.kind`, `coverage.policy.detail`, `binding`, `claim_class` | `policy.kind: tolerance` allows {`partly`, `no`}; `policy.kind: not_stated` with `binding: "not stated"` allows {`not_stated`} | Partly |
| Whole output checked | `coverage.unit`, `coverage.tokens_covered`, `coverage.phase`, `relation` | none: `tokens_covered` is free text | No |
| Formally verified | `relation_formal`, `security.notion.kind`, `security.notion.verifier`; `sources.security.notion*` | `relation_formal: "not stated"` allows {`partly`, `no`, `not_stated`} | No: only `yes` is excluded |
| Security level | `security.level`, `security.notion.kind`, `security.notion.verifier`, `security.model` | `level: "not stated"` allows {`not_stated`} | Partly: Not stated is; proven against conjectured, and whether the level is stated for this configuration, need the `level` text |
| No trusted party | `security.setup`, `assumptions`, `assumptions_not_stated`, `security.model.assumption` | `setup: trusted` allows {`partly`, `no`}; `setup: not_stated` with `assumptions_not_stated: true` allows {`not_stated`} | Partly |

The fields that set FlashProve's No trusted party are `assumptions` (its third item, `systems/flashprove/claim.yaml` L72 to L75, "Configuration files fixed before the hash function is drawn"), not `security.setup`, which reads `not_stated` (L43). A reviewer reads every field in the row, not only the obvious one. Where a free-text field says a statement is not made for the card's configuration (FlashProve `security.level`: "Not claimed for `cp_verify`"), SRC-1 excludes `yes` by review.

RISK: Whole output checked cannot be limited from the card, and Formally verified only by `relation_formal`, so a card change can leave them stale. Plan: every card-row quote names the card's commit and version, so a new pin (a new card, RFC-0002 §Configuration identity 1) needs every cell re-read. A later RFC-0002 amendment MAY add a card field for machine-checked soundness.

#### Reference rows (`reference_rfc_0015`)

- SRC-5. Reference rows are the benchmark's own methods, not systems, and have no claim card (RFC-0015 §Reference systems: "they prove nothing"). Their documentation is RFC-0015 together with the table below, which is normative: it sets each state by definition of the method, and the text of RFC-0015 it rests on. Where RFC-0015 has no sentence that meets a state's rule word for word (plain serving checks nothing; a rerun by the checker trusts no other party), the row's reason begins "By definition:" and names the RFC-0015 text. Every quote is from `rfcs/0015-reference-rows.md` in this repository at a full commit. A change to RFC-0015 that changes one of these states, or moves a quoted sentence, MUST amend this table and the quotes in the same pull request.
- SRC-6. A reference row names the workloads whose configuration it reads (`workloads`). These states describe the method as RFC-0015 documents it, not a measurement. The table gives the states of a configuration with no declared precision substitution. A recompute row whose workloads declare a substitution (RFC-0015 PM-2, PM-4) is `partly` on Model bound, because the rerun uses another precision than the workload's; one row reads workloads that agree on whether a substitution is declared. Today `systems/ref-recompute/system.yaml` declares one on both SASH workloads (FP8 W8A8 for the workload's INT8 W8A8, RFC-0015 Q1 and PM-4) and none on the two Maverick workloads. The criteria file's single recompute row reads the two Maverick workloads, which are the ones the site shows, and keeps Yes. A SASH-workload recompute row needs its own row, with `partly` on Model bound, before any page shows it. A configuration marked `not_measurable_on_profile` (RFC-0015 NM-1) keeps its states, and the row prints the NM-1 reason (settles R8).

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

- SRC-8. States come from public quotes by the system's own authors: its repository at a full commit, its paper, or its documentation or blog on a domain its team controls. Each row lists these as `own_sources` (repositories, domains, and URLs of papers or pages its authors published), with how each was identified. A deciding quote comes from an own source; a third-party page (press, survey, another team's blog) may appear only in `sources_read` or `aside`, and sets nothing (AGENTS.md rule 9). These rows are drawn apart from card and reference rows and are never in the benchmarked tab. How the site marks them (the prototype's "pencil") is the site's (#319).
- SRC-9. A web quote carries, in place of a commit: the `url`, a `retrieved` date (`"YYYY-MM-DD"`, RFC-0012 dates), and either an `archive_url` (a snapshot in a public web archive taken on or after the retrieved date) or a `copy` (a path in this repository holding the retrieved text, with its sha256). A web quote without these sets no state.
- SRC-10. A public-source row is not capped below Yes. This settles R1 under AGENTS.md rule 9: a cap would print Partly where the documentation states no limit, a state that comes from the benchmark rather than the source. The thoroughness gap is met instead by drawing public-source rows apart (SRC-8) and by web quotes that carry what was read (SRC-9).

### Negative control override

The third layer of a card-row state (INV-GLYPH-5). RFC-0008 runs the shared controls C1 to C8 and P1, P2, and the system-specific controls a system registers, against the verifier of each benchmarked configuration, and stores every outcome in the run's `controls.json`. These rules let a recorded outcome reach the glyph, and only in one direction: an outcome can contradict a stated property, and no outcome can confirm one.

- OVR-1. The override applies to card rows only. Reference systems run no controls (RFC-0015 §Reference systems: they have "no controls"), and public-source rows have no runs.
- OVR-2. Each control can contradict only the properties the control map below gives. The map is normative; a change to it, or a new RFC-0008 control, amends this table in the same pull request, and the validator's copy is tested against it (`test_control_map_matches_rfc`). Each control is assigned to the property whose Yes rule names the input the mutation changes: the request, the prompt or the claimed output (C1, C2, C4, C7) to Whole output checked; the weights, their commitment or their precision (C3, P1, P2) to Model bound. A control whose mutation changes only proof bytes (C5, C6, C8) names no such input. The assignment is this RFC's rule, not something an accepted outcome shows by itself: an accepted C1, for example, also fits a covered token that is not tied to the committed weights. One property per control keeps the rule mechanical ([Q9](#decisions)).

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
| system-specific (`fixture_proof`, `weakened_prover`) | registered in `systems/<name>/controls.yaml` | none ([Q7](#decisions)) | `system-controls/1` names no property, and a `weakened_prover` control expects `accepted` |

C5, C6 and C8 corrupt proof bytes and change no input a Yes rule names. An accepted corrupted proof shows that the verifier accepted bytes other than the honest proof; it does not show which statement fails (a flipped bit may sit in bytes the statement does not depend on), and reading one property onto it would be an inference (AGENTS.md rule 9). Their outcomes, like every outcome, are printed on the system page (OVR-7) and an accepted one goes to disclosure (RFC-0008 §Disclosure). Weights hidden, Formally verified, Security level and No trusted party have no mapped control and stay documentation only, for the reasons each property's "Controls" line gives.

- OVR-3. A control contradicts when its stored record holds the outcome `accepted` (the control's `outcome`, or the `outcome` of any of its `trials`) and its `expected` set does not hold `accepted`. No other record contradicts, and no record raises a state:
  - `rejected`, and `invalid_call` or `prover_failed` where the expected set holds them: the control passed. A pass shows that one mutation was rejected (RFC-0008 §Non-Goals); it never raises a state, so a `not_stated` cell stays `not_stated`.
  - `no_verdict`, and `invalid_call` outside the expected set (for example on C1): the control failed, but nothing was accepted. Inconclusive; it never lowers a state.
  - `void` (the honest twin was not accepted, INV-CTRL-2), `not_applicable` and `error`: the control tested nothing. Never raises or lowers a state.
  - not run: a control absent from a run's `controls.json`, a run with no `controls.json`, and a control the system documents but the harness does not run (for example an upstream rejected-proof example listed in the adapter README and not registered, RFC-0008 Q4; a registered `fixture_proof` control is recorded `not_applicable`, RFC-0008 Q5). Never raises or lowers a state.
  Each of these is printed on the system page as recorded (OVR-7).
- OVR-4. A card-row cell whose stated state is `yes` or `partly`, with at least one contradicting outcome of a control mapped to its property, takes the state `no`, whatever the documentation says. The cell keeps its quotes, which still decide the stated state under ST-1 and ST-8 and are still bound by the card fields table; it records the stated state in `stated` and the deciding evidence of `no` in `contradicted_by`, one entry per contradicting control and run. A cell whose stated state is `no` or `not_stated` is not changed: `no` already says the property does not hold, and `not_stated` states nothing to contradict ([Q5](#decisions)). This RFC chooses `no` over a printed note beside the stated state, and over a new state, because: the overview draws the state and nothing else, so a note would leave Yes or Partly drawn on a configuration whose verifier accepted an input the property says it rejects, against INV-GLYPH-5; `no` is what was measured, an input the stated property excludes was accepted by the configuration as run; and a fifth state was rejected for the same reason as in SRC-7 (one vocabulary of four states). The stated state is not lost: the system page prints it with its quotes beside the control that contradicts it.
- OVR-5. The override is computed per configuration and per release. The criteria file names the release it is built for (`release`). The runs read for a card row are the runs listed in `releases/<r>/release.yaml` `runs` for that release and for every earlier release (ordered by release id), whose `run.json` `claim.system` and `claim.configuration` equal the row's `card`, less every run in a read release's `superseded_runs` and every run named in the `replaces` of a read run (RFC-0009 §Append-only rule and corrections). Where a run's `run.json` `claim` is null (runs written before the runner copied the card there, all of v0.1), its `manifest.json` `claim` is read instead, the record release eligibility checks against the release's `claim_cards` and their digests (RFC-0014). Consequences:
  - With `release` set, every card row is a configuration the benchmark runs: its `card` system and configuration appear in the `claim_cards` of a read `release.yaml`, and at least one run is read for it. A card row lacking either is not benchmarked; the pull request removes the row or the release adds the run (INV-GLYPH-5).
  - A contradiction carries into later releases of the same configuration. A later run that rejects the same control does not clear it, since the accepted mutation is reproducible from its recorded seed (INV-CTRL-3).
  - A card edit at the same pin (a new `card_version`) does not clear it. A new pin, or any other change listed in RFC-0002 §Configuration identity, is a new configuration and a new card row, which starts with no contradiction and reads only its own runs.
  - A correction run that replaces the contradicting run clears it, for example when RFC-0008 §Disclosure finds a fault in the adapter's verdict mapping.
  - A release never reads runs of a later release, and a published release is not edited (RFC-0009).
  - A file with no `release` reads no runs, and none of its cells is overridden.
- OVR-6. Only a run under OVR-5 changes a cell: a correction run, or a run of a new configuration.
- OVR-7. The overview draws each cell's state only. The system page prints, for each cell: the stated state, its quotes and its sources read; for an overridden cell, each `contradicted_by` entry with its control id and run id, linked to the control's record in `controls.json`; and, for each control the map gives the property, its outcome in every run read, including passed, inconclusive, void, not applicable, error and not run, with "not run" printed for a mapped control no read run recorded. For a property with no mapped control, the page says that no RFC-0008 control tests it. The site computes these lists from the control map and the stored `controls.json` files; the criteria file holds only `stated` and `contradicted_by`, which follow from the stored files (AGENTS.md rule 3).


### Criteria file contract

The file stays at `web/_data/criteria.json`, authored JSON in the RFC-0012 canonical form (G3 `FMT-1`). Its schema is `schema/criteria/1.schema.json`, `$id` `https://inference-proofs.org/schema/criteria/1.schema.json`, Draft 2020-12, with `"schema": {"const": "criteria/1"}`.

RFC-0012 §Schema catalogue row, added by the implementing pull request:

| Name | File | Kind | Path of instances | Owner RFC |
|---|---|---|---|---|
| `criteria` | `schema/criteria/1.schema.json` | authored JSON | `web/_data/criteria.json` | RFC-0016 |

RFC-0013 §G2 inputs gain `web/_data/criteria.json` (and `G2_GLOBS` in `harness/src/iproofs/validate/tree.py`).

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

- `card_version` is a string of digits here, because the file holds no number-typed value (INV-GLYPH-2); it equals the card's integer.
- `rfc` names this RFC.
- Quote, one of three kinds. All carry `kind`, `text` (verbatim), `label`, `decides` (boolean) and `checked: true` with `checked_how` (Text). `repository` and `this_repository` add `repo`, `commit` (40-hex), `path`, `lines` (`^L[0-9]+(-L[0-9]+)?$`) and `url` (containing `commit`). `web` adds `url`, `retrieved`, and `archive_url` or `copy: {path, sha256}`, and carries no `repo`, `commit`, `path` or `lines` key. The prototype kind `ours` becomes `this_repository`. Quotes in `aside` and `outside_pin` carry `decides: false`.
- `aside`: `{words, quotes}`, text printed beside a cell for a limit counted in another cell (ST-5) or a statement made for another configuration (SRC-1). It sets nothing. The prototype's `aside.quote` and `aside.also` become the entries of `aside.quotes`.
- `outside_pin`: `{reason, quotes}`, card rows only, no `state` (SRC-3).
- `release` (optional): the release id the file is built for (OVR-5), equal to a directory `releases/<release>/` holding a `release.yaml`. Absent until the first release is frozen; without it no run is read and no cell is overridden.
- `stated` and `contradicted_by` (card rows only, both or neither, OVR-4): `stated` is `yes` or `partly`, the stated state the quotes decide; the cell's `state` is then `no`. `contradicted_by` is a non-empty list of `{control, run_id}`, sorted by `control` then `run_id`, with no duplicate pair. `control` is a control id of the [control map](#negative-control-override) mapped to the cell's property; `run_id` is an RFC-0012 run id. The entries follow from the stored `controls.json` files and are never edited by hand to differ.

- `conflict`: `true` only on a cell under ST-8; absent otherwise.
- `sources_read` entry: `{repo, commit, paths}` for a repository (paths or globs read) or `{url, retrieved}` for a web page.
- `not_copied: true` MAY replace `sources_read` on a `not_stated` cell of a public-source row where nothing was read yet ([Q2](#decisions)).
- `workloads` (reference rows, required): workload ids present in the reference system's `system.yaml` (SRC-6). `own_sources` (public-source rows, required, non-empty): each entry one of `repo`, `domain` or `url`, with `how` (SRC-8).
- Removed from the prototype, each for a reason: `test_mapping`, `rows[].states` and `rows[].pencil` (derived from the cells and `source_class`; derived values are computed, not typed); `quote_check` (a typed count that no rule recomputes); `contrast` and `states.*.fill`, `.ink`, `.mark` (drawing, the site's; `web/words.css` holds the inks it uses); `status`; `this_repository_commit` (moves into `pins`); `rules` and `risks` (now this RFC's normative text and dispositions); `outside_pin.state` (SRC-3); the `null` `repo`, `commit`, `path` and `lines` keys of web quotes.

### Data flow and lifecycle

1. A reviewer edits `web/_data/criteria.json` by pull request, quoting sources at the commits the row class allows.
2. `iproofs validate` runs G2 (the schema) and G3 on it.
3. A claim card change (a new `card_version`) needs a re-read of its row, which then names the new version. An RFC-0015 change that moves a quoted sentence needs the quotes and the reference table amended.
4. When a release is frozen (RFC-0009 §Freeze algorithm), the pull request that builds its site sets `release` and adds every `stated` and `contradicted_by` entry OVR-3 to OVR-5 require. A later run that changes an override (a correction, OVR-5) changes the file in the next release's pull request.
5. `web/build.py` reads the states from the cells; the footer pins the file's sha256 as it does today.

Determinism: the override reads only the file, the `release.yaml`, `run.json` and `controls.json` files of the releases it names. No clock and no network; the release order comes from the release ids.

### Failure modes

| Failure | Response |
|---|---|
| A coloured cell without a deciding quote | review catches it |
| A quote at a short or unpinned commit | the schema rejects a short commit; review catches an unpinned one |
| A web page changed or removed after it was quoted | the `archive_url` or `copy` still holds the text read; the cell stands until a reviewer re-reads it |
| A web quote with no archive and no copy | review catches it; the cell becomes `not_stated` with the url in `sources_read`, or gains an archive |
| A deciding quote from a third-party page | review catches it; the quote moves to `sources_read` or `aside` |
| A Not stated cell with nothing recorded | review catches it |
| A card-row quote from another repository or commit | review catches it; the quote moves to `outside_pin` or is replaced from the pin |
| A card-row state read from another configuration of the system | review catches it (SRC-1), against the card fields table |
| A card change contradicts a cell (for example `zero_knowledge.claimed` becomes `false` while the cell is `yes`) | review catches it, against the card fields table |
| RFC-0015 edited so a reference quote no longer reads in the current file | the quote, its commit and, if a state changes, this RFC's table are amended (SRC-5) |
| A reviewer's inference used as a deciding quote | review catches it (ST-3); the quote's text must be the system's own words |
| A score, count or number added to the file | the schema rejects it (`additionalProperties`) |
| A stated Yes kept while a mapped control was accepted in a read run | the pull request is fixed until the cell is `no` with `stated` and `contradicted_by` |
| An override added, kept or dropped by hand (no matching record, a superseded or replaced run, a run of another configuration, a later release's run) | review catches it |
| A Not stated cell given `no` from an accepted control | review catches it (OVR-4, Q5); the outcome is printed on the system page |
| An override on Weights hidden, Formally verified, Security level or No trusted party, or from C5, C6, C8 or a system-specific control | review catches it (OVR-2) |

| A card row with no run of its configuration in the release | review catches it (OVR-5); the row is removed or the run added |
| A system team objects to an overridden cell | the cell changes only with a correction run or a new configuration |
| A release run directory or `controls.json` missing from the tree | review catches it |

## Alternatives Considered

- **Keep the design clauses ("or the design rules it out").** Considered because some designs make a property impossible on their face (a recompute verifier must hold the weights). Rejected: it lets the benchmark state a security property the system does not state, against AGENTS.md rule 9, and every case in the data today has a documented statement that serves instead (recompute's rests on RFC-0015).
- **Judge Formally verified and Security level for the protocol, whatever verifier the card runs.** Considered because the prototype does, and the protocol is what the system's theorem is about. Rejected: RFC-0002 §Configuration identity 5 makes the verifier part of the configuration when the verifiers carry different security statements, and the FlashProve card says its statements hold for the Lean verifier only. Reading the Lean statement onto the `cp_verify` row would print a state the card says is not stated for it (SRC-1).
- **Derive every card-row state from card fields.** Considered because CI could then recompute the glyph and no reviewer judgement would remain. Rejected as the default ([Q3](#decisions)): Whole output checked has no field to derive from, Formally verified has only one that excludes a state, and Yes against Partly on three other properties depends on free text. The allowed sets keep the part that can be derived.
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
- **Map C5, C6 and C8 to Model bound and Whole output checked.** Considered because an accepted corrupted proof is a defect. Rejected: it does not show which statement fails, so the mapping would be an inference (OVR-2). The outcome is printed.
- **Clear a contradiction when a later run of the same configuration rejects the control.** Rejected: the accepted mutation is reproducible from its seed (INV-CTRL-3), so a later rejection does not undo it, and the rule would let a release keep the passing run and drop the other (OVR-5). A correction run that replaces the contradicting run, with its reason, clears it.
- **Move the criteria file out of `web/` (for example to `methodology/criteria.json`).** Considered because the file is methodology, not presentation. Rejected for now: `web/build.py` and the footer read it at its path, and moving it is churn with no change in meaning; #320 MAY move it with the generator.

## Drawbacks

- Re-reading is costly: every card change and every web quote needs a reviewer.
- A thorough system collects Partly while a silent one shows Not stated (R1, R11). This RFC keeps that, because it is what the documentation says; the site has to explain that Not stated is not No.
- A rule that a No needs a statement, and that a card row reads only its own configuration, will move some cells to Not stated (candidates in [Migration / Rollout](#migration--rollout)), so the glyph shows less than a reader of the design might expect.
- Reference rows' states are set by definition in this RFC where RFC-0015 has no sentence to quote; a reader must trust the project's own description of its baselines.
- Card-row states are reviewer-set, with no mechanical check beyond the schema.
- Controls reach two properties only. Weights hidden, Formally verified, Security level and No trusted party stay documentation only, so their Yes has no test behind it; the system page says so (OVR-7).
- The override is one way and coarse. Passing controls show little (a few seeded mutations per control, RFC-0008 §Drawbacks), and an accepted control sets No even where the documentation states a limit that may cover the mutation (Q6).


## Conflicts of Interest

This text was drafted with an AI agent, Claude, made by Anthropic. Anthropic publishes FlashProve (`anthropics/FlashProve`), one of the two systems with a card row. Reviewers should weigh the decisions that move FlashProve cells with that in mind: SRC-1 on R3, which reads FlashProve for its `exact-match-cp-verify` configuration and so takes its Formally verified and Security level off Yes (the prototype read both from the Lean verifier's statements); and ST-7 and Q1 on R6. The control map (OVR-2) and Q5 to Q9 apply to every card row alike; FlashProve's Model bound and Whole output checked, and SASH's, are the cells a control can contradict, and SASH's registered controls are the ones Q7 leaves unmapped.

## Migration / Rollout

Two pull requests (issue #318) brought this in. The first added the RFC and its index rows only. The second added the schema and examples, the validator's copy of the control map, `harness/tests/unit/test_criteria.py`, the RFC-0012 catalogue row and the RFC-0013 G2 input, rewrote `web/_data/criteria.json` to `criteria/1`, and updated `web/README.md` and `docs/spec/10-glossary.md` (the six properties and four states). Its description lists every state that changed, by row, and every cell edited.

Counts in the committed file (sha256 starting `4ced468b`, at `356949a5ee8afe328ee2cb0d68b18be1b1d82453`), recomputed by:

```sh
python3 -I -c 'import json;d=json.load(open("web/_data/criteria.json"));c=[(r,c) for r in d["rows"] for c in r["cells"].values()];print(sum(1 for r,x in c if x["state"]!="grey" and x["quotes"] and all(q["kind"]=="web" for q in x["quotes"])), sum(1 for r,x in c if x["state"]=="grey" and not x.get("searched")))'
```

which prints `13 65`. Of 138 cells (23 rows of 6): card rows 4 Yes, 5 Partly, 3 Not stated; reference rows 3 Yes, 9 No; public-source rows 14 Yes, 7 Partly, 3 No, 90 Not stated.

The second pull request migrated the file to `criteria/1` (keys, quote kinds, `sources_read`, `workloads`, `own_sources`) and rebuilt the site from it.

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

No claim card changes. No schema version changes other than the new `criteria/1`.

## Testing Strategy

Schema examples in `schema/criteria/examples/` (every invalid example with a `.reason` file):

- `valid/committed-shape.json`: one card row, one reference row and one public-source row in the committed file's shape, with an `aside` and an `outside_pin`; passes.
- `valid/not-copied.json`: a public-source `not_stated` cell with `not_copied: true`; passes.
- `valid/web-quote-archived.json`: a Yes cell whose deciding quote is a web quote with `retrieved` and `archive_url`; passes.
- `invalid/state-outside-four.json`: a cell with `state: "green"`; fails on enum.
- `invalid/property-number.json`: a property with `"n": 1`; fails on `additionalProperties`.
- `invalid/total-key.json`: a top-level `total`; fails on `additionalProperties`.
- `invalid/score-key.json`: a row with `score`; fails on `additionalProperties`.
- `invalid/web-quote-no-retrieved.json`: a web quote without `retrieved`; fails on `required`.
- `invalid/short-commit.json`: a repository quote with `commit: "9e2bdd8f"`; fails on pattern.
- `invalid/missing-rule.json`: a property whose `rules` lacks `not_stated`; fails on `required`.
- `invalid/outside-pin-state.json`: an `outside_pin` with `state`; fails on `additionalProperties`.
- `invalid/reference-no-workloads.json`: a reference row without `workloads`; fails on `required`.
- `valid/overridden-cell.json`: a card row with `release`, a Whole output checked cell with `state: "no"`, `stated: "yes"` and one `contradicted_by` entry; passes the schema.

- `invalid/stated-not-stated.json`: a cell with `stated: "not_stated"`; fails on enum.
- `invalid/contradicted-by-empty.json`: `contradicted_by: []`; fails on `minItems`.
- `invalid/contradicted-by-trial-number.json`: a `contradicted_by` entry with `"trial": 0`; fails on `additionalProperties`.


Repository checks: `uv run iproofs validate --all` (the schema and its examples).

## Decisions

- Q1. Public parameters fixed before the hash set Partly on No trusted party only where the documentation says its proved statement excludes a provider who tuned them (ST-7, R6); they are not a shared caveat printed as text. Reason: it copies a condition the documentation states ("that you grant", FlashProve `guide/what-is-proved.md` L288 to L289 at `9e2bdd8f`); a shared caveat would drop a stated condition. The cost is that a system which states the condition shows Partly while one that does not shows Not stated; the reason text says so, and other teams are invited to state their assumptions.
- Q2. "Not copied yet" stays the state `not_stated` (four states only) and the cell carries `not_copied: true`, so the data tells "not read yet" from "read and silent"; the printed word stays "Not stated", and whether a page prints the difference is the site's (#319). Reason: printing both the same way would claim sources were read that were not, and a fifth state was rejected (SRC-7).
- Q3. Card-row states are set by a reviewer from quotes, within the sets of the card fields table (SRC-4), not derived from card fields. Reason: Whole output checked has no card field to derive from, Formally verified has one that only excludes `yes`, and three properties need a reading of free text; derivation would need RFC-0002 fields that do not exist.
- Q4. When two allowed quotes meet the rules of different states, the cell takes the state of the fixed table of ST-8 (`yes` with `partly` gives `partly`; `yes` with `no`, or `partly` with `no`, gives `no`), with `conflict: true` and both quotes printed. Reason: the state is then met by a quote of the system's own, needs no reviewer judgement, and never says more than the more limited of the two statements; the alternatives (the reviewer picks, or the cell becomes Not stated) either add a judgement or hide two statements the system made.
- Q5. A contradicting outcome does not change a `not_stated` cell (OVR-4): the cell stays `not_stated` and the outcome is printed beside it on the system page. Reason: the benchmark validates claims, and a silent system states nothing to contradict; printing `no` would let the benchmark set a property the system does not state (AGENTS.md rule 9). The cost: a silent system with an accepted control draws Not stated where a system that states the property draws No. The system page and the Controls page print every accepted control in full (OVR-7, RFC-0009 §Site, RFC-0008 §Reporting), so the outcome is not hidden.
- Q6. When the documentation states a limit that covers the mutation, for example a tolerance policy that admits the C3 one-unit perturbation, or a check of the positions the client names that leaves out the token C1 changes, the override still applies (OVR-4), and the cell's system page prints the stated limit beside the control. Reason: the expected sets are RFC-0008's and the same for every system; deciding here whether a limit covers a mutation would add a reviewer judgement to a mechanical rule, and RFC-0008 already treats the acceptance as a possible defect.
- Q7. A system-specific control contradicts no property (OVR-2); its outcome is printed on the system page. Reason: `system-controls/1` names no property, a `weakened_prover` control expects `accepted`, and its failure (accepted while the binding report marks the edge bound) contradicts the card's binding table, not one glyph property. An RFC-0008 amendment MAY add a property field to `system-controls/1`, copied from the upstream description at the pin, and this table then follows it.

- Q9. OVR-2 assigns C1, C2, C4 and C7 to Whole output checked only, and C3, P1 and P2 to Model bound only, by the rule that a control is assigned to the property whose Yes rule names the input the mutation changes. Reason: one property per control keeps the override mechanical and needs no reading of why a verifier accepted. The cost: an accepted C1, C4 or C7 also fits a check that covers the token but does not tie it to the committed weights, and the map does not lower Model bound for it. Mapping one control to two properties would lower a state the outcome does not single out.
- Q10. When the documentation states a numeric level for the row's configuration but says neither that it is proven nor that it is conjectured, Security level is Partly. Reason: a level is stated, so Not stated would hide a statement the system made, and Yes asks the documentation to say the level is proven, which it does not. The cost: such a level is drawn as a conjectured one is. The case was met reading Attestable's blog post ("uphold 100 bits of security", #336); its cell's note cites this rule.

## References

- [RFC-0002](0002-claim-card.md) §File and identity, §Fields, §Rules (INV-CLAIM-2, INV-CLAIM-3), §Configuration identity, §Alternatives Considered.
- [RFC-0008](0008-negative-controls.md) §Shared controls, verifier side, §Shared controls, prover side, §Honest twins, §Outcomes, §controls.json, §System-specific controls, §Disclosure, §Non-Goals, INV-CTRL-2, INV-CTRL-3.
- [RFC-0009](0009-results-and-publication.md) for the site, §Storage, §Append-only rule and corrections, §Release record; its amendment for the live site is #319.
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
