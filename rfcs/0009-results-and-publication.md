# RFC-0009: Results format and publication

- Status: Draft
- Authors: AbdelStark
- Created: 2026-11-03
- Target milestone: v0.1
- Requires: RFC-0002, RFC-0003, RFC-0004, RFC-0007, RFC-0008, RFC-0012, RFC-0014, RFC-0015, RFC-0016
- Supersedes: none
- Discussion: pull request that introduces it

## Summary

This RFC fixes how runs are stored, how a correction is made, how a release is cut, what the generated site shows and in which order, how relying parties publish targets and how rows are evaluated against them, how system maintainers reply, and what each release report contains. `results/` is append-only. A release is a frozen, deterministic index over a named set of runs. The site is static HTML that reads in full without script, shows each system's claim before any number, carries scope, grade and tier with every number, and never ranks.

## Motivation

The benchmark's output is what readers see. PRD §11 names the main risk: headline numbers compared out of context. PRD goals G1 (claim first), G3 (reproducible) and G5 (neutral) all turn into presentation rules here. The draft RFC fixed the storage layout, the run-id, a 14-day review window, a 300-word reply and the existence of targets and reports. It did not say what a release file contains, how effective tiers are computed, how repetitions become one published row, how a target is evaluated, or how a correction is recorded without editing the past.

Scenarios:

- A runner discovers a wrong CPU binding in a published run. The original must stay visible, and the corrected run must say what it replaces.
- A policy analyst publishes "verification under 60 s on the verifier profile". A row whose mean is 58 s but whose least favourable repetition is 63 s must not be shown as meeting it without that fact being visible.
- A system maintainer disagrees with how a number is presented. Their reply must appear beside the rows, unedited.

## Goals

- Every run directory is self-describing and validates against its schemas (RFC-0012).
- Nothing in `results/` is ever modified or deleted after merge; corrections are new runs.
- `iproofs release freeze` is deterministic: the same inputs produce a byte-identical `index.json`.
- Every number on the site carries its unit, scope, grade and tier, and links to its source record (§Site S2 says where each label sits).
- The site has no aggregate score and no default sort by any performance metric.
- Targets are attributed to their authors and evaluated conservatively.

## Non-Goals

- The meaning of metrics (RFC-0004), tiers (RFC-0007), controls (RFC-0008) or claim card fields (RFC-0002).
- Hosting and domain of the site (open question tied to RFC-0001's permanent home).
- A machine-readable feed for third-party landscape maps (Q2).
- Interactive dashboards. The site is static HTML that reads in full without script; script only reorders, finds or reveals what a page already holds (§Site S10).

## Proposed Design

### Storage

```
results/<release>/<system>/<run-id>/
  run.json          every recorded and derived number of this job, each a quantity (RFC-0012)
  manifest.json     everything needed to rerun (RFC-0014)
  controls.json     control outcomes for this job (RFC-0008), or absent if the job ran no controls
  verifier/<proof_id>.json   per proof: verdict, raw exit code, raw last line, verify seconds
  logs/harness.jsonl         structured harness log (docs/spec/05-observability.md)
  logs/<step>.stdout, logs/<step>.stderr   adapter output per step, redacted
  digests.txt       "<name>\t<sha256:...>" per line, sorted: every proof digest, and the digest of every log before truncation
  reviews/<reviewer>-<YYYY-MM-DD>.json        peer review records (RFC-0007), added later
  reproductions/<repro-run-id>.json           reproduction records (RFC-0007), added later
```

`run-id` is `<YYYY-MM-DD>-<system>-<workload>-<profile>-<n>` as defined in [RFC-0012 §Identifiers](0012-schemas-and-serialization.md#identifiers). The date is the UTC start date of the job.

`run.json` top level (`run/1`):

```json
{
  "schema": "run/1",
  "run_id": "...", "release": "v0.1", "system": "sash", "workload": {"id": "...", "version": 1},
  "profile": "prover-h100", "repetition": 1, "control": false, "system_kind": "prover",
  "claim": {"system": "sash", "configuration": "default", "card_version": 1},
  "status": "completed",
  "failure": null,
  "replaces": null,
  "raw": {"setup": {}, "commit": {}, "prove": {}, "verify": {}},
  "adapter_phases": {},
  "metrics": {},
  "events": [{"event": "prove.start", "mono_ns": 0}, {"event": "proof.released", "mono_ns": 0}],
  "proofs": [{"proof_id": "...", "release_mono_ns": 0, "tokens_covered": 0, "verdict": "accept"}],
  "warnings": []
}
```

- `status` is `completed` or `failed`. `failure` follows the RFC-0010 failure record `{kind, step, message, exit_code, last_lines[], at}` when `failed`, else null.
- `system_kind` copies `system.yaml` `kind`: `prover`, `reference` ([RFC-0015](0015-reference-rows.md)) or `test` (the fake systems). Reference systems skip `commit` and `verify` (recompute rows time their work in `prove`), so their `raw` has no `commit` or `verify` entries. Runs of `test` systems are never listed in a release.
- `events` is the ordered list of lifecycle events `{event, mono_ns}` from which every timing scope is computed ([RFC-0010](0010-harness-runner.md), [RFC-0011](0011-measurement-and-sampling.md)); `mono_ns` values are structural integers on the G5 allowlist, and every published duration is a quantity derived from them.
- `claim` names the claim card in force for the run by system, configuration and `card_version`.
- `raw` holds measured quantities per step; `metrics` holds the recorded and derived quantities keyed by RFC-0004 metric id; `adapter_phases` holds adapter-reported quantities (`source.kind: adapter`).
- `replaces` is null or `{run_id, reason}` (see §Corrections).
- `inputs` (runs recorded from the 2026-11-08 amendments on) holds the workload record's asserted inputs as copied at run time, `active_parameters_per_token` and `weight_bits` ([RFC-0003 WB-4](0003-workloads.md#weight-bits)); the derived quantities that use them point there.

Size rules:

- No proof bytes are committed. Proofs are recorded by digest; one proof per configuration is archived in full outside git ([RFC-0014 §Proof digests and archive](0014-provenance-and-integrity.md#proof-digests-and-archive)).
- Each log file is capped at 1 MiB: the first 256 KiB and the last 768 KiB are kept, joined by the line `[iproofs: <k> bytes omitted, full digest in digests.txt]`. The digest of the untruncated log is recorded in `digests.txt` before truncation.
- A run directory is capped at 10 MiB in total. If the per-file caps leave it above that, adapter logs are cut further to their first 64 KiB and last 192 KiB, largest first, until it fits. `harness.jsonl` is cut last.
- The harness enforces both caps when it writes the directory; G2 rejects a run directory above the cap.

### Append-only rule and corrections

1. After a run directory is merged to the default branch, no file in it changes and none is deleted. G2 enforces this on pull requests by rejecting any diff that modifies or removes a path under `results/` that exists on the base branch, except additions under `reviews/` and `reproductions/`.
2. A correction is a new run whose `run.json` has `replaces: {run_id, reason}`. The reason is one or two sentences. The replaced run stays in `results/` and is shown on the site as superseded, with a link to the replacement and the reason.
3. A run that is wrong for a reason a rerun cannot fix (for example a measurement bug in the harness) is handled the same way, with a run of the fixed harness, or, if no rerun is possible, by a `superseded_runs` entry in the next `release.yaml` with the reason. The original is never deleted.
4. Results produced under an older version of an RFC keep their labels; a release says which RFC commit it was produced under (RFC-0001 §Changes to methodology).

### Configurations and repetitions

A configuration is the tuple (system, workload id, workload version, profile, adapter image digest, `control: false`). Repetitions of one configuration are its runs with `repetition` 1, 2, 3 and so on. A release publishes one row per configuration:

- Each published metric is a statistic (RFC-0012) over the completed repetitions: `stats.n` completed, `stats.n_failed` failed, mean, sample standard deviation, minimum, maximum. The statistic has `grade: derived`, `source.ref: derive:D-STAT@<harness version>`, and `source.inputs` pointing at the per-run quantities in repetition order. Its tier is the lowest effective tier among those inputs (INV-QTY-6a of RFC-0012).
- RFC-0004 requires at least three repetitions. A configuration with fewer than three completed repetitions is still published, with `insufficient_repetitions: true` in the index and the label "below minimum repetitions" shown in the row (RFC-0004 §Statistics), so no result is hidden and no result is overstated.
- Failed repetitions are listed in the row with their failure kind and step and a link to the run.

### Release record

`releases/<release>/release.yaml` (`release/1`), authored by maintainers in a pull request:

```yaml
schema: release/1
release: v0.1
reference_file: reference/v0.1.yaml
rfc_commit: "<40-hex commit of this repository whose rfcs/ tree is in force>"
harness_version: "0.1.0"
runs:
  - results/v0.1/sash/2026-12-02-sash-sash-l31-8b-c4096-prover-h100-1
  # every run directory included, listed explicitly
superseded_runs: []           # [{run_id, reason}] for runs withdrawn without a replacement run
claim_cards:
  - {system: sash, configuration: default, card_version: 1, path: systems/sash/claims/default.yaml, digest: "sha256:..."}
review_window: {opens: "2027-02-15", closes: "2027-03-01"}
freeze_date: "2027-03-02"
replies:
  sash: systems/sash/replies/v0.1.md
sponsors:
  - {name: "<organisation>", provided: "<what, e.g. GPU hours>", period: "<dates>"}
```

`releases/<release>/index.json` (`release-index/1`) is generated by `iproofs release freeze` and contains:

- `configurations[]`: for each configuration, its runs, its statistics per metric, `insufficient_repetitions`, eligibility (RFC-0014 §Eligibility) and reasons, effective tier and the evidence behind it (review and reproduction record paths).
- `controls[]`: per configuration, counts per outcome (`rejected`, `accepted`, `no_verdict`, `invalid_call`, `void`, `not_applicable`, `error`, `prover_failed`) and the list of controls whose outcome is outside their expected set.
- `targets[]`: every applicable target evaluation (§Targets).
- `claim_cards[]` and `reference` digests as frozen.
- `inputs_digest`: SHA-256 over the sorted list of digests of every file the freeze read, so anyone can check they froze the same inputs.
- `freeze_derived` (only when non-empty): per run id, the repetition-level values the freeze evaluated for a run stored before their formula existed ([RFC-0004](0004-metrics-timing-grades.md#open-questions) Q3: D-TPP, D-SPAB-S), which the configuration statistics point at; `run.json` is never rewritten (APP-1).

Every number in `index.json` is a quantity or statistic. Effective tiers appear here and nowhere in `results/` (INV-QTY-4).

### Freeze algorithm

`iproofs release freeze RELEASE` runs these steps and stops at the first failing step with exit code 1 and a message naming the run and rule:

1. Load and validate `release.yaml`, the reference file, every listed run directory and every claim card at the listed digest.
2. Run G2 to G7 of [RFC-0013](0013-validation-and-ci.md) over the listed runs.
3. Check that `review_window.closes - review_window.opens >= 14 days` and `freeze_date > review_window.closes`, as calendar dates in UTC.
4. Check eligibility of each run (RFC-0014). Ineligible runs are excluded from statistics and listed with reasons.
5. Group runs into configurations and compute statistics per metric over completed repetitions, in repetition order. A closed workload's configurations need completed runs from at least two distinct proving systems whose claim cards have the workload's exact class, and no proving configuration on it may hold a card of another class (RFC-0003 §Choosing common workloads, Q7 default); otherwise the freeze stops.
6. Compute effective tiers per configuration (RFC-0007): `reproduced` if a reproduction record names this configuration's runs as originals, the reproducer's manifest `runner.affiliated_systems` does not contain the system and `runner.organisation` differs from the original runner's, and the record's `outcome` is `within_tolerance`; else `peer-reviewed` if an `approved` review record exists from an organisation other than the runner's `runner.organisation`; else `reported`. A failed reproduction does not lower a tier below `reported`; it is listed beside the row with both sets of numbers.
7. Summarise controls per configuration.
8. Evaluate targets (§Targets).
9. Write `index.json` with the RFC-0012 writer. No wall-clock timestamps are written; every date comes from `release.yaml`, so the output is deterministic.

The freeze pull request adds `index.json` and is merged only after the review window closes. After merge, the release's files change only by a new release (for example `v0.1` to `v0.2`); there are no point releases of the data.

### Review window

Before `freeze_date`, every system maintainer of every system listed in the release gets at least 14 days (`review_window`) to review its rows, controls and claim card, and to write a reply. The window opens when a release candidate site is built from a draft `index.json` and its location is sent to each system's named maintainers (RFC-0001). Objections are issues tagged with the reviewer's organisation (RFC-0007 §Peer review before release). A system maintainer's silence does not block the release; an unresolved objection from a system maintainer about their own rows blocks it until maintainers resolve it by consensus or vote (RFC-0001).

### Site

`iproofs site build [--out DIR]` generates the public site into `web/` (committed; Vercel deploys the committed files) from the newest frozen `releases/*/index.json` and its `release.yaml`, the claim cards, run records and replies they name, `systems/`, `workloads/`, `reference/`, `targets/`, the criteria file and `web/_data/facts.json`. The generator is `iproofs.site`: it computes every value a page prints into one view and hands it to the renderer in `web/build.py`, which draws the pages and words stored values; neither types a number. `--out DIR` writes a complete site elsewhere. Every page is complete static HTML that reads in full without script; S10 says what script may do. Until v0.1 is frozen (#146), the deployed pages are built from a placeholder release (`harness/tests/fixtures/placeholder_release.py`) and served with `noindex`.

The site validates claims; it does not audit them. On a system row, a glyph state means what RFC-0016 defines: stated by the system at its pin, for the configuration the benchmark runs (verifier included), and not contradicted by the benchmark's tests, the shared negative controls of RFC-0008 (C1 to C8, P1 and P2), under RFC-0016's rule for control outcomes (#318; the rule lands with the RFC-0016 amendment). "Not contradicted" covers only the controls that ran and gave an outcome: a control that is `void`, `not_applicable` or `error` "neither passes nor fails" (RFC-0008 §Outcomes), a control not run tested nothing, and the system page lists both beside the property (S1). System-specific controls (RFC-0008 §System-specific controls) are shown on the system page with their outcome against their own expected set, and set a state only as RFC-0016 says. A reference row's states come from RFC-0015, and a public-source row's states come from public quotes that no benchmark run or control has tested (RFC-0016 §Sources by row class). No page states an audit or a probability that a claim is correct (this section; RFC-0016 INV-GLYPH-2: properties carry no numbers), nor a security level of the benchmark's own (RFC-0016 INV-GLYPH-3).

Pages, in the set the public site at `web/` has (`web/README.md`), plus the pages v0.1 still requires:

| Page | Content, in this order | Live site, 2026-11-07 |
|---|---|---|
| Overview (`/`) | the legend: six key glyphs with each property's name and question (RFC-0016), the four states as words, a link to the criteria page; then one table across models, one row per benchmarked system (S6), each row's header first, holding the glyph, name and pin and linking its card's validated claims on the system page, with no claim text of the card (S1), then the model and the figures; then Not benchmarked yet: the listed systems with no run (RFC-0016 public-source rows), A to Z, as glyph, name, models and status, with no figure (facts only, S2) | yes, with gaps (below) |
| System (`/<system>`) | the name; per claim card the system's rows read, in the order S1 sets: the validated claims (the glyph, and per property its name, its state as a word, the reason, the deciding quote with its source at the pin or, for Not stated, the sources read, the other quote of a conflicting cell, and the outcome of every control RFC-0016 ties to the property, whatever it is); the card's identity with a link to the card file and its digest; the facts (kind, model, pinned repositories, licence, status, adapter notes; S2); the claim card in full (RFC-0002), folded by default; then, open, its `quality_gap` and `residual` fields with the recompute agreement rate on a plate beside them (RFC-0015 RC-5, RC-6; S2, S3); then per configuration: a heading naming workload, division and profile, the runs left out of its figures (S7), one plate per headline figure (a block holding the figure and every label, with the id `fig-<column>`; S2, S3), the other figures in a table; then every control outcome per configuration, each unexpected outcome in full (RFC-0008); then the reference rows on the same workload (RFC-0015), their figures linking to their plates on `/reference`; then the system maintainers' reply (§Right of reply), with the words "not reviewed by system maintainers" beside it when a system maintainer stopped responding during the release window (RFC-0001 §Failure modes; S1) | yes, with gaps (below) |
| References (`/reference`) | reference rows, not system pages (RFC-0015 §Reference systems): per reference system its name, glyph (states from RFC-0015, RFC-0016 §Sources by row class) and facts; then per workload its reference rows, under a heading naming workload, division and profile, with one plate per figure (id `<reference>-fig-<column>`) and the other figures in a table. No claim card, no controls and no reply; its records are called outputs, not proofs (RFC-0015 REF-2) | yes, with gaps (below) |
| Criteria (`/criteria`) | what the benchmark measures and what it does not; then per property its name and question, what each of the four states means for it, and what it does not cover, as RFC-0016 defines them | yes, without the opening statement; its criteria are a draft until RFC-0016 |
| Release | release scope, RFC commit with a link to every RFC at that commit, reference file, list of systems, list of what was reproduced and what failed, with a link to every unexpected control outcome | yes (`/release`), with gaps (below) |
| Targets | every target with its author, and the rows it was evaluated against, with the mean and the least favourable value beside each result (§Targets) | yes (`/targets`, when the release evaluates one); no target exists |
| Sponsors and conflicts | sponsors as listed in `release.yaml` and conflicts from `MAINTAINERS.md`, in separate sections (PRD §7 N4, docs/spec/09 §Benchmark release checklist step 10) | yes (`/sponsors`) |
| Not found | the header and "Not found", served with status 404; no number | yes |

Every page in the table is required in v0.1, Targets only when the release lists a target. The footer of every page names the release and links the release page, the release's `index.json` (S5), the sponsors and conflicts page and the criteria page.

Pages of the first draft of this section that v0.1 does not require, and where their content goes:

- Home: the overview takes `/`. Links to releases and to sponsors and conflicts are in every footer; what the benchmark measures and does not opens the criteria page.
- Workload: the overview's Model cell names the model, its size and what the workload ran; the system page names the workload id, division and profile and links the workload record, which holds the definition and the model and prompt digests (RFC-0003); `/reference` holds the reference rows.
- Division table: the overview's one table names a closed or open row's division in its Model cell (S6). The first draft's first column held a card summary (four card fields); each row header now holds the glyph in its place, set from the same card, and the card's quotes and the card in full are on the system page (S1). v0.1 has native workloads and one closed workload, `l31-8b-c1024`, whose rows publish once two systems with its class run it (RFC-0003 §Divisions; Q7, default; the freeze enforces it).
- Controls: on the system page, each control's outcome beside the property RFC-0016 ties it to, in the validated claims (S1), and every outcome per configuration after its figures; the release page links every unexpected outcome.
- Methodology: on the release page, beside the RFC commit.

Rules:

- **S1 Claim first.** On every page that shows a quantity or statistic (S2) for a system, the claim card for that number's configuration comes before the number (RFC-0002 INV-CLAIM-1), in the form the next two bullets set, read as the bullet "How a table across systems meets" argues. The system's glyph (six triangles that make a hexagon, one per property) is the summary of that configuration's validated claims: each state is stated by the system, for the configuration run, and not contradicted by the controls (§Site, RFC-0016). The quotes, sources and control outcomes it rests on are on the system page.
  - In a table across systems each row's header comes first in the row and holds, before any figure: the glyph, the system's name and its pin, with a link to the validated claims of the row's card on the system page (`/<system>#claims-<configuration>`). When the table holds more than one row of the system (one per card, RFC-0016 SRC-1), the header also names the card's `configuration`. Of the card the header holds only its identity: the system, the pin (`upstream.commit`) and, where named, the `configuration`, which say which card the row reads and claim nothing. It holds no value of any other card field (`claim_class`, `relation`, `security`, `zero_knowledge`, `assumptions`, `coverage`, `binding`, `residual`, `quality_gap`, `availability`): the glyph is the row's summary, and each of its states is a word in the HTML (S9).
  - On the system page, after the name, for each claim card the system's rows read (RFC-0016 SRC-1), under the anchor `claims-<configuration>`, in this order, with no quantity or statistic before the card in full:
    1. The validated claims: the glyph and, per property, its name; its state as a word; the reason; the deciding quote with its source at the pin (repository, full commit, path and lines, linked; INV-CLAIM-3), or, for Not stated, the sources read (`sources_read`), and, where the cell carries `conflict: true`, the other quote with its source too (RFC-0016 ST-2, ST-8); and the outcome, in every run the row reads, of every control that RFC-0016's rule for control outcomes ties to the property, each with its control id, outcome and a link to its record, whatever the outcome: one that contradicts the state, one in the control's expected set, one outside it that accepted nothing (`no_verdict`, `invalid_call`), and one that tested nothing (`void`, `not_applicable` or `error`, with its recorded reason, or "not run"). A state no control tested so never reads as tested. Which controls a property lists is RFC-0016's, not this section's.
    2. The card's identity (`system`, `configuration`, `card_version`, as frozen in `release.yaml` `claim_cards[]`), with a link to the file at `claim_cards[].path` at the commit that merged the release's `index.json` (§Freeze algorithm) and `claim_cards[].digest` printed beside it, and the words "card not reviewed by system maintainers" while `reviewed_by` holds no entry for that `card_version` (RFC-0002 §Failure modes; Q4).
    3. The facts (S2).
    4. The claim card in full, each field with its source link (INV-CLAIM-3), folded by default in an HTML `details` element, which is in the HTML as sent and opens with one press, with or without script (S10).
    5. Open, the card's `quality_gap` and `residual` fields, with the recompute agreement rate on a plate of its own beside them (RFC-0015 RC-5, RC-6), every label in view (S2, S3).

    The configurations' figures follow.
  - The card body is folded, not left out and not laid open. INV-CLAIM-1 asks the card itself to appear before the number on every page that shows one, and the system page holds the plate of each of the system's figures, so the card body MUST be in that page's HTML, before the first figure in reading order. A link alone would put the card a page away from every plate. Laid open, its fields (relation, assumptions, coverage, residual and the rest, each with its sources) push every figure several screens down, while the validated claims above it already hold each deciding quote, one press from its property (§Site gaps, S1). The agreement rate is a statistic, so it stays out of the fold: S2 and S3 keep every label and value of a system page in view, and RFC-0015 RC-6 prints the rate beside `quality_gap` and `residual`, which are laid open with it after the card.
  - Three RFCs put words "in the rows" that this section puts on the system page, which every row header links: RFC-0002 §Failure modes ("rows show 'card not reviewed by system maintainers'"), shown beside the card's identity; RFC-0001 §Failure modes (a system maintainer who stops responding during a release window: "the rows carry 'not reviewed by system maintainers'"), shown beside the reply, a separate condition from an empty `reviewed_by`; and RFC-0008 §Reporting ("Per row the site and release index show" the count of each outcome, and "Every `accepted` outcome where rejection was expected is printed in the row in full"), read as the configuration's controls on the system page, with each control's outcome also beside its property in the validated claims. The release index keeps RFC-0008's counts per configuration (§Release record, `controls[]`). Q4 records these readings for Last call.
  - The glyph shows the six properties of RFC-0016, each in one of its four states, set as RFC-0016 §Sources by row class decides: for a system row, for the configuration's claim card in force (RFC-0002); for a reference row, from RFC-0015; for a system not benchmarked yet, from public sources. Each state's reason links the quotes it rests on, on the page or one link away.
  - A reference row has no claim card (RFC-0015 §Reference systems). It sits in a References table, never among the system rows, and its glyph links to its reference on `/reference`. A row of a system not benchmarked yet shows no figure. It is drawn apart, in its own section after the References (RFC-0016 SRC-8), and that section says its states come from public sources, not from a claim card. The glyph of a system that has a system page links to that page.
  - How a table across systems meets "claim before numbers". RFC-0002 reads "Every published row resolves to exactly one claim card, shown before any number" (§Goals) and "the card for that number's configuration appears before the number" (§Rules 2, INV-CLAIM-1); RFC-0003 §Divisions renders native tables "with the claim cards above them". This section reads both as met by the row header, "above" read as before in reading order: the header comes before every figure of its row at every width (S11); it resolves to exactly one card, the one in force for the configuration the row's figures were measured under (`run.json` `claim`); its states are set from that card for that configuration, verifier included (RFC-0016 SRC-1), so the glyph says what the card states for what was run, or, where a control outcome contradicts a state, the state RFC-0016's rule for control outcomes sets for that outcome; and each state is a word in the HTML, with its reason, quote, source and control outcomes one link away, in that card's validated claims on the system page, where the card follows. The first draft read the invariant the same way, with a summary in place of the card: its division table showed four of the card's fields. The words are not met to the letter: the row holds the card's identity but none of its claim text, and a reader of the overview sees six states, not the card's own statements. Q4 records this for Last call; until then this reading is the default, and RFC-0002 and RFC-0003 are not changed here.
  - No layout, at any width, moves a figure before its row header, or a system page's figures before its validated claims and its claim card (S11).
- **S2 Labels with every number.** Every quantity and statistic (RFC-0012) shown carries its unit, scope (when not null), grade and tier, and links to the JSON Pointer of its source in the published record. Facts that describe a workload, a model or a pin (prompt length, batch size, parameter count, a date, a commit) are not quantities; they link to the record they come from. What one proof covers is a quantity (RFC-0004 §Tokens covered), not a workload fact, and carries its RFC-0004 grade like any other. Where the labels sit:
  - On a system or reference page every label is in view beside its value, on the figure's plate or in its row of the table.
  - In a table across systems the unit is in view, and scope, grade and tier MAY leave view. They are then in the figure's accessible description, and the figure links to its plate (`/<system>#fig-<column>`, or `/reference#<reference>-fig-<column>` for a reference row), where every label and the source link are in view. A column whose rows differ in scope, grade or tier shows each figure's own labels in view.
  - Labels MAY use plain display words in place of the stored values (for example "calculated from recorded numbers" for the grade `derived`): one fixed wording per stored value, set in the generator. The linked record holds the stored value.

  AGENTS.md rule 2 holds: no number is in a page without its labels in that page's HTML, and every label is in view on the number's own plate, one link away at most. A number shown without these is a template bug, caught by the site golden tests (docs/spec/07-testing-strategy.md).
- **S3 Ranges.** A statistic shows mean, standard deviation, minimum, maximum, n and n_failed, and the label "below minimum repetitions" when it applies (§Configurations and repetitions). On a system or reference page all of them are in view, on the plate and in the table. In a table across systems the printed figure is the mean, with n, n_failed, minimum and maximum in view; the standard deviation MAY leave view, and at 560 px wide and below so MAY n, n_failed, minimum and maximum. What leaves view stays where S2 puts a label that leaves view. "Below minimum repetitions" never leaves view.
- **S4 Display rounding.** Values are shown with 4 significant digits. Rounding is display only (RFC-0012): the full stored value is in the linked record (S2), and every order S5 computes uses it, through a sort key in one base unit that the generator computes from the stored value and never types (AGENTS.md rule 3). A `title` attribute MAY repeat the full value; on its own it does not meet this rule.
- **S5 No ranking.** In the HTML as sent, the overview's rows are ordered by overhead against production serving, ascending, by the stored value of each row's headline figure (RFC-0004 INV-DERIVE-10, -11), a row with no overhead last, ties by system name, then profile id, then the configuration's position in the release's `index.json` (owner decision of 2026-11-09); this is also the order shown when the URL has no hash. A reader with script MAY re-sort by pressing a column head (System, and every figure; Model does not sort). A second press reverses the order. The order is kept in the URL hash as `#sort=<column>-<asc|desc>`, so a shared link opens in the same order. No hash, an unknown order, or Back to the page without a hash gives the default order. A row with no value in the sorted column goes last in both directions; ties keep the default order. A reader without script gets the default order with every row and figure, column heads that do not look pressable, and the release's `index.json`, linked from every footer, for any other order (Q2). Reference rows and systems not yet benchmarked are not sorted with the systems. Search results are ordered by where the query matched, then by kind of entry, then by how closely it matched, then by name; systems not yet benchmarked come after every other match; results are never ordered by a metric. The default order is a measured column, but no row is marked by it. There is no rank number, no medal, no aggregate score and no highlight of an extreme value: the sorted column MAY be set apart from the other columns, but no row or value in it is marked.
- **S6 Divisions.** The overview holds one table across models, one row per benchmarked system (owner decision of 2026-11-09, now that a figure comparing provers across models sorts): the system's configuration on the workload `web/_data/facts.json` names as its `overview_workload` (FlashProve: `fp-maverick-w1024-b24`, the batch of FlashProve's own figure), or its only configuration; a system with more than one and none named stops the build. Its other configurations are on its system page only. Reference rows are not rows of this table: production serving is the baseline the overhead divides by, named in each overhead cell. Columns: System, with the model under the system's name (name, total and active parameters, the weight width, and what the workload ran; a closed or open workload names its division here, INV-WL-5); overhead against production serving (the release's `overhead_headline`: D-OVERHEAD-S, or D-OVERHEAD-WARM where the system has no steady scope), with its scope, its prover and serving run counts and range, and the precision proved against the precision served; then three figures on one basis, per token covered per Gbit of active weights (active parameters per token × weight bits, RFC-0004 INV-DERIVE-7), named once in a line the three heads share: proving time (D-SPAB-S at `prove.steady`, or at `prove.session` where the steady figure is null, in ms, labelled with the scope shown), proof size (D-BPAB, in kB) and check time (D-VSPAB, in ms, with its scope). RFC-0004 INV-DERIVE-7's limit and the weight width are in each of the three cells' description and on their plates. Each cell names its sample size and range (on a phone in short, with the scope). Each numeric column sorts by its stored values (S4, S5), rows whose weight width covers part of the weights (SASH) included, with that width named under the system; for the overview this sets aside RFC-0004 INV-DERIVE-7's rule that lists such rows unsorted (owner decision of 2026-11-09). The absolute proof size and check time of each row's own workload stay on the system page. The system page names the division beside the workload.
- **S7 Runs left out of the figures.** On the system page, above each configuration's figures, its superseded, ineligible and failed runs are listed, each with a link to its run record: a superseded run with its reason and a link to the run that replaces it, an ineligible run with its reasons, a failed run with its failure kind, step, exit code and last line. The same place says how many completed runs the figures are over. These runs never contribute to statistics. Their status is named in words, not shown by strike-through alone (S9). In a table across systems the row carries n_failed (S3), and each of its figures links to its plate, under this list; the row reaches its failed repetitions in one link, and that is how this section reads §Configurations and repetitions' "listed in the row" until an amendment of that section says otherwise.
- **S8 Neutral text.** All site text passes G8 of RFC-0013.
- **S9 Accessibility.** Tables are exposed as tables: native table elements with header cells and `scope` attributes, or, where a layout re-flows each row onto lines of its own, elements with the ARIA `table`, `row`, `columnheader`, `rowheader` and `cell` roles. Either way every cell has one column header and one row header, and a sorted column's header carries `aria-sort`. Labels are text, not colour alone: every glyph state is a word in the page's HTML (in a table, in the row header's cell, as text read after the system's name, since the header's accessible name is the name alone; on the system page, in view), shown as a word under a pointer, on a tap and on keyboard focus; the legend names each state's ink, and Not stated has an ink with no hue. Pages SHOULD pass an automated WCAG 2.2 AA check at desktop and phone widths.
- **S10 Script.** Pages are built for reading without script, and script only adds to them:
  - Every row, figure, label, glyph state and link is in the HTML as sent, in the default order (S5).
  - Script MAY only reorder rows (S5), find (search over `search.json`, an index the build writes from the same inputs, every entry of which leads to a page of the site), or reveal what the page already holds (a glyph state under a pointer or on a tap, the search sheet on a phone). It never adds, removes or changes a figure, label or glyph state of the page. Search shows only entries of `search.json`, and the count of the matches it does not list.
  - A control that works only with script is not shown, or does not look pressable, without script.
  - Every file a page loads (script, style sheet, font, image, frame) comes from the site itself; an inline script is allowed only by its hash in the Content-Security-Policy. Links to other sites are allowed; no page loads anything from them. No page sends anything off the site: no analytics, no third-party requests, and search matches in the browser. Script stores nothing in the browser (no cookie or web storage); the only state it writes is the URL hash.
  - The site runs no code from submissions: replies reach the page as escaped Markdown (emphasis, lists and links only, §Right of reply) and data as escaped text (docs/spec/06-security.md §Trust boundaries, item 5).
  - Movement (rows moving to a new order) is instant under `prefers-reduced-motion`.
- **S11 Narrow screens.** Every page works from 320 CSS px wide: no page scrolls sideways, and a wide table re-flows rather than scrolls. Every label S2 and S3 require stays reachable on a phone: in view, or in the figure's accessible description and in view on the plate the figure links to. A `title` attribute alone does not make a label reachable, since touch screens do not show it. Every link and button has a target at least 24 CSS px tall, and no two targets overlap. S1's order holds at every width.

Changes made to this section on 2026-11-07, so that it describes the site the project publishes (`web/`) before Last call:

| Rule | Kept or changed | Reason |
|---|---|---|
| Page table | changed: the live page set plus Release, Targets and Sponsors and conflicts; Home, Workload, Division table, Controls and Methodology folded into other pages; `/reference` added for reference rows | the overview at `/` holds the per-workload tables a reader comes for; each folded page's content is named above; Sponsors and conflicts stays for PRD §7 N4; `/reference` holds each reference figure's plate once, and the system page keeps its reference rows and the agreement rate (RFC-0015) |
| Script sentence and §Non-Goals | changed: S10 | sorting and search help a reader without changing what a page holds; every page still reads in full without script, and the site still loads nothing from elsewhere |
| S1 | changed: the glyph, set from the card, added to each row header and to the system page as the summary of the validated claims; no claim text of the card in the row headers of tables across systems, which hold glyph, name and pin (and the configuration where a system has two rows) with a link to the card's validated claims; on the system page, before any figure, per property the state, reason, deciding quote with its source at the pin (or the sources read, and both quotes of a conflict) and the outcome of every control RFC-0016 ties to it, then the card's identity with a link to the card file and its digest, then the card in full, folded, then `quality_gap` and `residual` open with the agreement rate; the glyph's source per row class; the "in the row" wordings of RFC-0001, RFC-0002 and RFC-0008 read as the system page | the benchmark validates claims and does not audit them (§Site); the glyph reads the six properties across systems in one column, and its quotes, sources and control outcomes need the room of the system page; INV-CLAIM-1 is unchanged, S1 argues how the row header meets it, and Q4 puts that reading to Last call |
| S2 | changed: scope, grade and tier may leave view in tables across systems; plain display words allowed; One proof covers named a quantity | a table across systems holds several figures per row; each figure's labels stay in its HTML and in view on its plate, and stay in view where rows differ |
| S3 | changed: in tables across systems the sd may leave view, and below 561 px so may n, n_failed and the range | as for S2; every system and reference page keeps all six in view |
| S4 | changed: the full value lives in the linked record and the sort key; `title` optional | a `title` is not reachable on a touch screen or by keyboard; the record is the source a reader and a check both reach |
| S5 | changed: re-sorting by column head with the order in the URL hash; bans kept | one page per address, Back returns to the default order, and the HTML as sent keeps the alphabetical order; see §Alternatives Considered |
| S6 | changed: tables per model and workload, each naming its division; the glyph, set from the card, in each row header before every figure | RFC-0003 §Divisions asks separate tables per native workload, which S6 keeps, and claim cards above them, which S1 reads as met by the row header's glyph with the card on the system page (Q4); INV-WL-5 is met by the heading; the header is kept |
| S7 | changed: runs named in words, with links, above the figures | strike-through shows a status by style alone and makes the reason hard to read; failed runs join the list, and a row across systems reaches it through its plates |
| S8 | kept | |
| S9 | changed: ARIA table roles allowed beside `th` with `scope`; glyph states as text | a table that re-flows each row onto lines can lose native table semantics in some browsers; explicit roles keep the structure |
| S10 | new | replaces the script sentence |
| S11 | new | a shared link is often opened on a phone, and the first draft said nothing of narrow screens; the rules for labels and order must hold there too |

Changes made to this section on 2026-11-08 (#333), on the owner's decision of that date ("drop the all systems table, no repetition please"):

| Rule | Kept or changed | Reason |
|---|---|---|
| Page table | changed: the Overview row says the models are ordered by total parameters and that no table spans models | a table of every system above the per-model tables would print every row twice; see §Alternatives Considered |
| S5 | changed: the tables in S6's order, the rows of each table A to Z; an order reorders rows within each table only | the default order of rows was written for one table; with a table per model and workload, the page order is S6's and the row order is per table |
| S6 | changed: model size defined as `workload.model.parameters.total`, ties by model name; no table across models, so each row (system configuration, workload, profile) is in exactly one table; a system's rows on a closed or open workload stay in their own tables until Q5 is resolved; a table across models waits for a sortable cross-model figure (RFC-0004 INV-DERIVE-7) | "largest first" named no measure; of the two figures RFC-0004 gives for comparing provers across models, prover time per bit of active weights does not sort yet and the overhead is in every table already, so a table across models would add no order and would repeat each row |

Where the public site at `web/` does not yet meet these rules, after #320's second pull request:

- S1: the glyph states come from `web/_data/criteria.json` ("Draft criteria, needs an RFC", until RFC-0016 is Accepted); beside each property the system page prints its name, state and reason, a "source" link to its entry in "How we read it" (`#read-<property>`) and, for an overridden cell, its stated state and the controls that contradict it, with the run one link away in that entry; each property's deciding quote (or a conflict's quotes), its sources read and its control outcomes are folded in "How we read it", a `details` element after the glyph and before the card's identity in reading order, not in view beside the property; the system page prints each cell's deciding quote and both quotes of a conflict, but no other quote (a cell's supporting, `aside` and `outside_pin` quotes) and no cell `note` (RFC-0016 OVR-7); rows are keyed by system, so a system has one card row; each control outcome and run left out names its record by path, a link only once #146 publishes the release; card links use `main`, not the commit that merged `index.json` (#146); the Not benchmarked yet section does not say its states come from public sources and gives no reason or quote (an owner decision on the overview's look), and some of its states rest on web quotes RFC-0016 SRC-9 does not accept (RFC-0016 §Migration / Rollout).
- S2: each plate, overview figure and more-numbers row names its record in the release's `index.json` as a JSON Pointer in text, not a link, since the index is not published yet (S5). Model facts link no model record.
- S4: until the S2 source links exist, no reader can reach the full stored value; the overview keeps it only in each row's sort key, which is not shown.
- S5: the site publishes no `index.json`; every footer names its path, and links it once #146 publishes it.
- S6: the overview's Model cell names the model and shape, not the workload id, profile or a link to the workload record (an owner decision on the overview's look); the system page names them.
- S9: a glyph state is not shown as a word on keyboard focus.
- Pages: the criteria page does not open with what the benchmark measures and does not; system pages print no reference rows (they are on `/reference`); a system with one configuration has no heading naming its workload, division and profile above its figures (the Figures heading names the model and shape; the division is named under Tamper tests); the system maintainers' reply is printed once, after the tamper tests, not beside every overridden cell (RFC-0016 OVR-6), and never carries the words "not reviewed by system maintainers" (RFC-0001 §Failure modes); `/release` links the `rfcs/` tree at the RFC commit, not each RFC, and, while the release is a candidate, prints its freeze date, review window and sponsors as not set, since until #146 they are the placeholder fixture's; `/reference` has no per-workload headings and no table of other figures, and heads each reference's glyph "What one proof establishes" (RFC-0015 REF-2).

### Targets

Relying parties publish targets as `targets/<author>/<id>.yaml` (`target/1`):

```yaml
schema: target/1
id: verify-under-60s
author: {name: "<person or organisation>", affiliation: "<organisation>"}
date: "2027-01-10"
metric: verify_seconds            # an RFC-0004 metric id
comparator: "<="                  # one of <=, >=, ==
threshold:
  value: 60
  unit: s
  scope: verify
  grade: asserted
  tier: reported
  source: {kind: reference_file, ref: "targets/<author>/verify-under-60s.yaml#/threshold"}
  null_reason: null
claim_class: "*/exact-match/*"     # RFC-0002 claim-class pattern, `*` matches one segment
applies_to:                       # optional extra filter; every listed key must match the claim card
  coverage.phase: prefill
  zero_knowledge.claimed: true
profile: verifier-cpu             # optional; restricts to rows on this profile
rationale: "One or two paragraphs in the author's words."
```

Evaluation, per configuration in a release, for each target whose `claim_class` pattern matches the card's `claim_class` (RFC-0002) and whose `applies_to`, if present, matches the card and whose `profile` (if set) matches:

1. If the configuration's metric is missing, null, or has a unit or scope different from the threshold's, the result is `not_evaluable` with the reason.
2. Otherwise compare the least favourable completed repetition: the maximum for `<=`, the minimum for `>=`, every repetition for `==`. The result is `meets` or `does_not_meet`.
3. A target whose `applies_to` does not match is not shown for that configuration.

Using the least favourable repetition rather than the mean is a decision: a target is a threshold a relying party cares about, and a mean inside the threshold with a repetition outside it does not meet it. The site shows the mean and the least favourable value beside the result. The project publishes no targets of its own (PRD §9). Targets are versioned by git history and attributed; changing a target after a release does not change that release's `index.json`.

### Right of reply

Each system maintainer may write `systems/<name>/replies/<release>.md`, up to 300 words, counted as whitespace-separated tokens of the Markdown source after removing link targets. The site renders it below the system's rows with HTML escaped (Markdown emphasis, lists and links only), headed "Reply from the system maintainers", unedited. Maintainers may reject a reply only for G9 violations (secrets or identifiers) or for content that is illegal to publish, and must say so in the pull request. Replies are excluded from the neutral-language lint (RFC-0013 G8) because they are the maintainers' own words.

### Reports

One report per release, `reports/<release>.md`, reviewed by every listed system's maintainers during the review window. Required sections, in order: what changed since the last release; what was reproduced and by whom; what failed (failed runs, failed reproductions, unexpected control outcomes); what the numbers do not show (including every RISK still open in the RFCs); sponsors; conflicts. Every number in a report is copied from `index.json`, carries its unit, scope, grade and tier, and links to its row. A report computes no new numbers (AGENTS.md rule 3); any ratio it needs is added to the derivation code first.

### Failure modes

| Failure | Response |
|---|---|
| A pull request modifies an existing run file | G2 rejects it with the append-only rule id `APP-1` |
| A run directory exceeds 10 MiB | harness truncates at write; G2 rejects a directory still above the cap |
| Fewer than 3 completed repetitions | published with `insufficient_repetitions: true` |
| A listed run is ineligible | excluded from statistics, shown with the reason |
| Review window shorter than 14 days | freeze fails at step 3 |
| A target references an unknown metric | G2 `XREF-5` |
| A reply exceeds 300 words | G2 rule `RPL-1` fails the pull request |
| An archived proof is missing its `uri` at freeze | freeze fails at step 4 (eligibility) |

## Alternatives Considered

**Allow in-place edits of results with git history as the audit trail.** Considered because it is simpler. Rejected: readers of the site do not read git history, and a changed number must be visible as a change. Append-only with `replaces` makes corrections first-class.

**Publish only one selected repetition, or the median.** Rejected by AGENTS.md rule 5 and PRD N3. Mean with range and n is shown; the median adds little at n = 3.

**Evaluate targets on the mean.** Considered because it matches the headline. Rejected for the reason in §Targets; the mean is shown next to the result instead.

**A single default sort by cost per proved token.** Considered because readers expect sorted tables. Rejected: a default sort is a ranking (PRD §5), and native rows on different workloads are not comparable.

**A table of every system across models, above a table per model.** Proposed in #333: one table of every benchmarked system with a Model column and the figures RFC-0004 gives for comparing provers across models (the overhead against plain serving and prover time per bit of active weights), ordered by model size, then a table per model with the absolute figures. Considered because a reader could see every system in one place. Rejected by the owner on 2026-11-08: each system row would be printed twice, glyph and all, and prover time per bit of active weights does not sort while the weight bits are a nominal width (RFC-0004 INV-DERIVE-7), so one of its two figures could not order it, and the other, the overhead, is a column of every per-model table already. It returns once a figure that compares provers across models can be sorted (S6). Ordering the per-model tables by model size is not the ranking that "A single default sort by cost per proved token" rejects: the size is the model's, the same for every system on it, and no system's result moves its table.

**One static page per sort column, so re-sorting needs no script.** The first draft of S5, and what `iproofs site build` wrote before #320. Considered because every order then reads without script. Rejected on 2026-11-07: each column and direction is another page holding a copy of every number, so the golden files and the link checks grow with the columns; a shared copy opens in an order that is not the default and has no way back to it but navigation; and the copies add nothing a reader without script needs, since the page as sent holds every row in the default order and the release's `index.json`, linked from every footer, holds every value for any other. The column heads with the order in the URL hash (S5) keep one page per address, open a shared link in the order it was shared in, and return to the default order with no hash.

**Strike superseded and ineligible runs through.** The first draft of S7. Rejected on 2026-11-07: strike-through marks a status by style alone (S9) and makes the reason hard to read. The status is named in words beside the reason (S7).

**A dynamic site with a database.** Rejected for v0.1: static pages are cheap to host anywhere, easy to archive per release and need no server that someone must operate neutrally.

## Drawbacks

- Append-only results mean the tree grows without bound, by up to the 10 MiB cap per run directory, which is why logs are capped hard.
- Worst-repetition target evaluation makes a system with high variance look worse against a target than its mean suggests. That is intended, and stated on the page.
- A 14-day window and a report reviewed by every team slow each release.
- Unedited replies can contain claims the project cannot check; they are labelled as the maintainers' words.

## Conflicts of Interest

The author's affiliations and any interest in a measured system are declared in `MAINTAINERS.md` before this RFC enters Last call (RFC-0001).

## Migration / Rollout

No results exist yet. v0.1-alpha lands the run directory writer with the fake systems; v0.1-beta lands the first real runs; v0.1 lands freeze, site and report. The draft's storage layout is kept; additions are `reviews/`, `reproductions/`, `replaces`, `releases/`, caps and the freeze algorithm.

Amendment of 2026-11-09 (owner decision, RFC-0015 SRV-6 production serving): in the display rules, the system row's overhead column shows the overhead against production serving (`overhead_vs_production_prove.steady`; its words name production serving), with the RFC-0004 INV-DERIVE-9 conditions line and precision note generated from the release index's `overhead_conditions`, never typed. A SASH row prints that it has no steady figure, with its reason. S6 is unchanged (no table across models).

Amendment of 2026-11-09 (Draft, owner request, RFC-0004 INV-DERIVE-10): every proving system gets an overhead in that column. Where the steady figure is null because the system has no steady scope (SASH), the column shows D-OVERHEAD-SESSION (`overhead_vs_production_prove.session`), the statistic the release index's `overhead_headline` names; the site chooses nothing. Under S2 the figure carries its scope wherever it appears: the cell prints "proving session, start-up included on both sides" under the value, and the plate prints that scope line, the session conditions line and precision note, and why the steady figure is null. A session figure is never worded as a steady one. Where the steady figure has a value, or is null for a join reason, it stays in the column as before. Under S5 and S6 a column sort reorders the rows of one workload's table, so a session figure meets a steady one in a sort only when two systems on one workload have different headline scopes; each cell keeps its scope line (RFC-0004 Q5).

Amendment of 2026-11-09 (Draft, owner direction, RFC-0004 INV-DERIVE-11), replacing the column rule of the amendment above: where the steady figure is null because the system has no steady scope (SASH), the column shows D-OVERHEAD-WARM (`overhead_vs_production_warm`), the prover's proving session over production serving's steady scope, as `overhead_headline` names it; D-OVERHEAD-SESSION is computed and not displayed. Under S2 the figure names both scopes wherever it appears: the cell prints "proving session (start-up included; it proves one request at a time) vs warm serving (steady)" under the value, the plate prints that line as the figure's scope, with the warm conditions line and precision note, and why the steady figure is null, and no high-load figure is printed beside it (RFC-0004 Q6). A warm figure is never worded as a steady one, nor as a session on both sides. Under S5 and S6 a warm figure meets a steady one in a sort only within one workload's table; each cell keeps its scope line (RFC-0004 Q5).

Amendment of 2026-11-09 (owner decision, the cross-model table): S5 and S6 above. The per-model tables, the native workloads header and the References table leave the overview; one table across models holds one row per benchmarked system, default-sorted by overhead against production serving, with prover time per active weight bit (D-SPAB-S) as a column. `site-facts/1` gains the optional row field `overview_workload`. A second amendment of the same date (owner decision) puts the model under the system's name, and replaces the per-bit column and the absolute proof size and check time with proving time, proof size and check time per token per Gbit of active weights (RFC-0004 D-SPAB-S, D-BPAB, D-VSPAB); the absolute figures stay on the system pages.

## Testing Strategy

- `harness/tests/unit/test_results_writer.py::test_log_truncation_keeps_head_and_tail`, `::test_untruncated_digest_recorded`, `::test_run_dir_cap_enforced`.
- `test_append_only.py::test_modified_run_file_rejected`, `::test_added_review_accepted`, `::test_deleted_run_rejected` (G2 `APP-1` against a two-commit fixture repository).
- `test_freeze.py::test_deterministic_index` (freeze the fixture release twice in different working directories, byte-identical `index.json`), `::test_review_window_under_14_days_fails`, `::test_insufficient_repetitions_flagged`, `::test_ineligible_run_excluded`, `::test_superseded_run_excluded_and_listed`, `::test_tier_reproduced_requires_unaffiliated_reproducer`, `::test_failed_reproduction_listed_tier_unchanged`, `::test_closed_workload_needs_two_systems`, `::test_closed_workload_of_one_system_stops_freeze` (RFC-0003 Q7).
- `test_targets.py::test_least_favourable_repetition_used` (repetitions 58 s, 59 s, 63 s against `<= 60 s` gives `does_not_meet`), `::test_scope_mismatch_not_evaluable`, `::test_applies_to_filter_hides_target`.
- `test_reply.py::test_301_words_fails`, `::test_html_escaped`.
- Site tests: `harness/tests/golden/test_site_golden.py::test_site_matches_golden` builds the site from the fixture release and compares its HTML to the golden files in `harness/tests/golden/site/`; `harness/tests/unit/test_site.py` parses every page as sent and holds these checks:
  - `::test_page_set_and_footer` (page table): every required page exists, Targets only when the release lists a target, and every footer names the release and links the release page, the release's `index.json`, the sponsors and conflicts page and the criteria page.
  - `::test_every_number_has_labels` (S2): each quantity and statistic has unit, scope, grade and tier and a source link in view, or, in a table across systems, its unit in view, the other labels in its accessible description and a link to its plate, where they are in view; a column whose rows differ in a label shows it in view.
  - `::test_glyph_before_numbers` (S1): on every page, each row's header, holding its glyph, precedes the row's first figure in DOM order; a system row's header links to `/<system>#claims-<configuration>` of its card, and a reference's glyph to its entry on `/reference`.
  - `::test_claim_card_before_numbers` (S1, INV-CLAIM-1): in every table across systems each system row's header precedes the row's first figure and holds the glyph, with each state as a word, the name, the pin and a link to its card's claims block, the card's `configuration` where the table holds two rows of the system, and no value of a card field other than `system`, `upstream.commit` and `configuration`; on system pages, in DOM order for each card, the validated claims (per property the state, reason, and the deciding quote with a source link at the card's pin, or for Not stated the sources read, and both quotes of a `conflict: true` cell; and one entry, with a link to its record, per control RFC-0016 ties to the property and run read, whatever its outcome, "not run" included), the card's identity with the link to `claim_cards[].path` at the commit that merged `index.json`, whose sha256 equals `claim_cards[].digest` printed beside it, and the claim card in full inside a `details` element in the HTML as sent, precede every quantity and statistic; the agreement rate comes next, outside the `details` element, with `quality_gap` and `residual`; each card-row state equals the state the criteria file sets for that card (RFC-0016).
  - `::test_statistics_shown` (S3): every statistic shows its six values, and "below minimum repetitions" where it applies, in view on system and reference pages.
  - `::test_sort_key_is_stored_value` (S4, extends `::test_display_rounding`): each sort key equals the stored value in one base unit, and the printed figure is that value at 4 significant digits.
  - `::test_default_order_by_overhead` (S5): the HTML as sent holds the rows by overhead ascending, no overhead last, ties by name; the overhead head carries `aria-sort`.
  - `::test_board_order_by_hand` (S5): on hand-made rows, overhead ascending whatever its scope, a row with none last, ties by system name whatever its case, then profile id, then position in `index.json`.
  - `::test_one_row_per_system` (S6): one table, one row per benchmarked system on its `overview_workload` (or its only configuration), its glyph once; no reference row.
  - `::test_each_figure_names_its_scope` and `::test_deployed_figures_by_hand` (S2, S6): the overhead cell names its scope, run counts and the precision on each side; the proving-time and check-time cells their scope (steady, else session; checking), the row header the width; the compact lines the scope and n; the deployed values against `index.json` by hand (proving 0.06821 ms and 75.41 ms, proof size 0.2229 kB and 639.9 kB, check 0.1987 ms and 51.04 ms per token per Gbit of active weights).
  - `::test_no_ranking` (S5, extends `::test_no_aggregate_score_column`): no rank number, medal, aggregate score or marked extreme value in any page.
  - `::test_division_named` (S6): the system page names each configuration's workload, division and profile; an overview row on a closed or open workload names its division in its Model cell.
  - `::test_runs_left_out_listed` (S7, replaces `harness/tests/unit/test_site.py::test_superseded_and_ineligible_struck_through`): the fixture's superseded run and failed repetition are listed above the figures with their reasons, exit code, last line and links, are not in any statistic, and are one link from each figure of the row in a table across systems.
  - `::test_table_semantics` (S9): every cell has one column header and one row header, through `th` with `scope` or ARIA table roles; every glyph state is a word in the HTML, in a table read after the system's name in the row header's cell.
  - `::test_reads_without_script` (S10, replaces `harness/tests/unit/test_site.py::test_no_script_tags_required`): every row, figure, label and glyph state is in the HTML as sent; every script is a site file or an inline script whose hash the Content-Security-Policy lists; no page loads a script, style sheet, font, image or frame from another origin (links to other sites are allowed).
- Site browser checks, in a headless browser on the CPU against the built site served with its headers. #320 places them in a file of their own, for example `harness/tests/browser/test_site_browser.py`, with the generator it keeps (`web/shoot.mjs` runs most of them on the public site today):
  - `test_script_off` (S10): with script off, every page shows the same text as its HTML and no control that needs script; an unknown address answers the Not found page with status 404 and no number.
  - `test_sort_from_hash` (S5, S10): every column and direction from the heads and from a loaded `#sort=` hash; no hash gives the default order; an unknown order falls back and is cleared from the URL; Back to the page without a hash restores the default; rows with no value go last both ways; the table holds the same text before and after every sort; no row or value is marked in any order; under `prefers-reduced-motion` rows move to the new order at once.
  - `test_search_local` (S5, S10): search loads only `search.json` from the site, sends no request while typing, stores nothing in the browser, shows only entries of `search.json`, and orders results by where the query matched, then kind of entry, then how closely it matched, then name, with systems not yet benchmarked after every other match; without script it is not shown.
  - `test_states_as_text` (S9): a glyph state shows as a word under a pointer, on a tap and on keyboard focus, and the word is one the HTML already holds.
  - `test_narrow_screens` (S11): at 320, 360 and 390 px wide and on a phone held sideways, on every page: no sideways scroll, every S2 and S3 label reachable, every link and button 24 px tall or more with no overlap, and each row header before its row's figures.
  - `test_accessibility_check` (S9): an automated WCAG 2.2 AA check on every page at a desktop and a phone width.

## Open Questions

- Resolved Q1: archived proofs and the upstream inputs stored with them (RFC-0014 Q3) go to the public dataset repository `abdelstark/inference-proofs-archive` on the Hugging Face Hub (amended 2026-11-06: the project's organisation on the Hub does not exist yet, and the maintainer chose a dataset under their own account; a later move keeps every recorded URI valid, since each is pinned to a dataset commit). Reasons: one configuration's proof can be large (the SASH 4,096-context run's proofs total about 19.8 GB, as above), and it fits, where the caps of other free hosts may not ([2 GiB per GitHub release asset](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases), [50 GB per Zenodo record](https://help.zenodo.org/docs/deposit/manage-files/), both as stated by those hosts on 2026-11-04); every file is addressed at an immutable commit; and the v0.1 workloads already fetch their weights from the same Hub. Each `manifest.proofs[].archive` URI is pinned to the dataset commit (`.../resolve/<commit>/<path>`), and the stored object's sha256 is read back and checked before the URI is recorded (`iproofs archive upload`, docs/runbooks/gpu-run.md). Uploads happen on the runner's host before the results pull request, because results are append-only. The freeze rule stands: a configuration without an archive URI is ineligible. A release may also deposit its archive with a DOI later; that changes no URI.
- OPEN QUESTION Q2 (owner: AbdelStark, resolve by: 2027-03-31): whether to offer a machine-readable feed for existing landscape maps. Default: `index.json` is published next to the site and is the feed.
- OPEN QUESTION Q3 (owner: AbdelStark, resolve by: RFC-0001 permanent home decision, target 2027-03-31): where the site is hosted. Default: built in CI as an artifact for review; publication location chosen with the permanent home.
- OPEN QUESTION Q4 (owner: 0xchqrles, resolve by: Last call of this RFC, RFC-0001): does a table across systems meet RFC-0002 INV-CLAIM-1 ("the card for that number's configuration appears before the number") and RFC-0003 §Divisions ("with the claim cards above them") with a row header that holds the glyph, name and pin and no claim text of the card? Default: yes, as S1 reads them: the header precedes every figure, resolves to exactly one card, and its states are set from that card for the configuration run and not contradicted by the controls (RFC-0016), with the quotes and the card in full on the system page. Reason: on 2026-11-07 the project decided that the benchmark validates claims and does not audit them, that the overview carries no card text, and that the glyph is the summary of the validated claims. The words of both RFCs are not met to the letter, since no claim text of the card is in the row. If Last call holds them to the letter, either RFC-0002 INV-CLAIM-1 and RFC-0003 §Divisions are amended to say that a summary set from the card meets them in tables across systems, or row headers carry card text again; this RFC changes neither. The same question covers three other wordings that put text in the rows (S1): RFC-0002 §Failure modes, "card not reviewed by system maintainers" for a card with no review, shown by default beside the card's identity on the system page; RFC-0001 §Failure modes, "not reviewed by system maintainers" for a system maintainer who stopped responding in the release window, shown by default beside the reply on the system page; and RFC-0008 §Reporting, the count of each control outcome "per row" and every unexpected `accepted` outcome "in the row in full", shown by default on the system page and kept per configuration in `index.json`. None of these is in the row headers of tables across systems.
- OPEN QUESTION Q5 (owner: 0xchqrles, resolve by: Last call of this RFC, RFC-0001): on the overview, does a system's row on a closed or open workload repeat the system beside its native row, or fold into the native row? On 2026-11-08 the owner asked for "no repetition please" (#333), and S6 keeps the tables of RFC-0003 §Divisions, where closed and open rows are "shown separately" (#334). Default: one row per workload table, as S6 reads now, so a system on its native workload and a closed one has a row, and a glyph, in each table. Reason: folding would put a closed or open workload's figures in a native table, which RFC-0003 §Divisions does not allow, so it needs an RFC-0003 amendment, not this RFC alone. Neither builds a case today: in the deployed results each benchmarked system runs one workload and appears once, and the closed workload `l31-8b-c1024` publishes no rows until two systems with its class run it (RFC-0003 Q7).

## References

- PRD §4 goals G1, G3, G5; §7 N2, N3, N4; §9 targets; §11 risks.
- [RFC-0002](0002-claim-card.md), [RFC-0003](0003-workloads.md), [RFC-0004](0004-metrics-timing-grades.md), [RFC-0007](0007-evidence-tiers-and-reproduction.md), [RFC-0008](0008-negative-controls.md), [RFC-0012](0012-schemas-and-serialization.md), [RFC-0013](0013-validation-and-ci.md), [RFC-0014](0014-provenance-and-integrity.md).
- MLPerf submission review practice; Ethproofs per-prover rows (PRD §2).
