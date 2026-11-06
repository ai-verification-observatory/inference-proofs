# RFC-0009: Results format and publication

- Status: Draft
- Authors: AbdelStark
- Created: 2026-11-03
- Target milestone: v0.1
- Requires: RFC-0002, RFC-0004, RFC-0007, RFC-0008, RFC-0012, RFC-0014
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

Every number in `index.json` is a quantity or statistic. Effective tiers appear here and nowhere in `results/` (INV-QTY-4).

### Freeze algorithm

`iproofs release freeze RELEASE` runs these steps and stops at the first failing step with exit code 1 and a message naming the run and rule:

1. Load and validate `release.yaml`, the reference file, every listed run directory and every claim card at the listed digest.
2. Run G2 to G7 of [RFC-0013](0013-validation-and-ci.md) over the listed runs.
3. Check that `review_window.closes - review_window.opens >= 14 days` and `freeze_date > review_window.closes`, as calendar dates in UTC.
4. Check eligibility of each run (RFC-0014). Ineligible runs are excluded from statistics and listed with reasons.
5. Group runs into configurations and compute statistics per metric over completed repetitions, in repetition order.
6. Compute effective tiers per configuration (RFC-0007): `reproduced` if a reproduction record names this configuration's runs as originals, the reproducer's manifest `runner.affiliated_systems` does not contain the system and `runner.organisation` differs from the original runner's, and the record's `outcome` is `within_tolerance`; else `peer-reviewed` if an `approved` review record exists from an organisation other than the runner's `runner.organisation`; else `reported`. A failed reproduction does not lower a tier below `reported`; it is listed beside the row with both sets of numbers.
7. Summarise controls per configuration.
8. Evaluate targets (§Targets).
9. Write `index.json` with the RFC-0012 writer. No wall-clock timestamps are written; every date comes from `release.yaml`, so the output is deterministic.

The freeze pull request adds `index.json` and is merged only after the review window closes. After merge, the release's files change only by a new release (for example `v0.1` to `v0.2`); there are no point releases of the data.

### Review window

Before `freeze_date`, every system maintainer of every system listed in the release gets at least 14 days (`review_window`) to review its rows, controls and claim card, and to write a reply. The window opens when a release candidate site is built from a draft `index.json` and its location is sent to each system's named maintainers (RFC-0001). Objections are issues tagged with the reviewer's organisation (RFC-0007 §Peer review before release). A system maintainer's silence does not block the release; an unresolved objection from a system maintainer about their own rows blocks it until maintainers resolve it by consensus or vote (RFC-0001).

### Site

`iproofs site build [--out DIR]` generates static HTML into `site/_build/` (not committed) from `releases/*/index.json`, `systems/`, `workloads/`, `targets/` and the replies. Templates live in `site/templates/` (Jinja2). Every page is complete static HTML that reads in full without script; S10 says what script may do.

Pages, in the set the public site at `web/` has (`web/README.md`), plus the pages v0.1 still requires:

| Page | Content, in this order | Live site, 2026-11-07 |
|---|---|---|
| Overview (`/`) | the legend: six key glyphs with each property's name and question (RFC-0016), the four states as words, a link to the criteria page; then, per model, largest first, one table per workload of the systems on it (S6): glyph, name and pin first (S1), then the figures; then References: the reference rows on the same workloads (RFC-0015), on the same columns, not sorted; then Not benchmarked yet: the listed systems with no run, A to Z, as glyph, name, models and status, with no number | yes, with gaps (below) |
| System (`/<system>`) | the name; the glyph with each property's name, its state as a word and the reason (RFC-0016); the facts (kind, model, pinned repositories, licence, status, adapter notes); the claim card in full (RFC-0002); then per configuration: a heading naming workload, division and profile, the runs left out of its figures (S7), one plate per headline figure (a block holding the figure and every label, with the id `fig-<column>`; S2, S3), the other figures in a table; then every control outcome per configuration, each unexpected outcome in full (RFC-0008); then a link to the reference rows on the same workload; then the system maintainers' reply (§Right of reply) | yes, with gaps (below) |
| References (`/reference`) | per reference system (RFC-0015): name, glyph, facts, then its plates and table as on a system page, headed with the reference's name | yes |
| Criteria (`/criteria`) | what the benchmark measures and what it does not; then per property its name and question, what each of the four states means for it, and what it does not cover, as RFC-0016 defines them | yes, without the opening statement; its criteria are a draft until RFC-0016 |
| Release | release scope, RFC commit with a link to every RFC at that commit, reference file, list of systems, list of what was reproduced and what failed, with a link to every unexpected control outcome | not yet |
| Targets | every target with its author, and the rows it was evaluated against, with the mean and the least favourable value beside each result (§Targets) | not yet; no target exists |
| Sponsors and conflicts | sponsors as listed in `release.yaml` and conflicts from `MAINTAINERS.md`, in separate sections (PRD §7 N4, docs/spec/09 §Benchmark release checklist step 10) | not yet |
| Not found | the header and "Not found", served with status 404; no number | yes |

Every page in the table is required in v0.1, Targets only when the release lists a target. The footer of every page names the release and links the release page, the sponsors and conflicts page and the criteria page.

Pages of the first draft of this section that v0.1 does not require, and where their content goes:

- Home: the overview takes `/`. Links to releases and to sponsors and conflicts are in every footer; what the benchmark measures and does not opens the criteria page.
- Workload: each overview table's heading names its workload id and version, model and profile, and links the workload record, which holds the definition and the model and prompt digests (RFC-0003). The table holds every configuration on the workload; the References table holds its reference rows.
- Division table: the overview's tables are the division tables, and each names its division (S6). v0.1 has native workloads only (RFC-0003 §Divisions).
- Controls: per configuration on the system page, beside the claim it tests; the release page links every unexpected outcome.
- Methodology: on the release page, beside the RFC commit.
- Reference rows on the system page: on the overview beside the system rows and on `/reference`. The system page links to them, so each reference figure has one plate.

Rules:

- **S1 Claim first.** On every page that shows a number for a system, the system's glyph (six triangles that make a hexagon, one per property) comes before that system's first number: in the first column of its table row, and at the top of its system page. The glyph shows the six properties of RFC-0016, each in one of its four states. Its states are derived by RFC-0016's criteria from the claim card in force for the configuration (RFC-0002); the glyph summarises the card and never replaces it. On the system page the claim card in full, each field with its source link (INV-CLAIM-3), comes before the first number (INV-CLAIM-1), and every glyph on another page links to that system page. No layout, at any width, moves a number before its system's glyph (S11).
- **S2 Labels with every number.** Every quantity and statistic (RFC-0012) shown carries its unit, scope (when not null), grade and tier, and links to the JSON Pointer of its source in the published record. Facts that describe a workload, a model or a pin (prompt length, batch size, parameter count, a date, a commit) are not quantities; they link to the record they come from. Where the labels sit:
  - On a system or reference page every label is in view beside its value, on the figure's plate or in its row of the table.
  - In a table across systems the unit is in view, and scope, grade and tier MAY leave view. They are then in the figure's accessible description, and the figure links to its plate (`/<system>#fig-<column>`), where every label and the source link are in view. A column whose rows differ in scope, grade or tier shows each figure's own labels in view.
  - Labels MAY use plain display words in place of the stored values (for example "calculated from recorded numbers" for the grade `derived`): one fixed wording per stored value, set in the generator. The linked record holds the stored value.

  AGENTS.md rule 2 holds: no number is in a page without its labels in that page's HTML, and every label is in view on the number's own plate, one link away at most. A number shown without these is a template bug, caught by the site golden tests (docs/spec/07-testing-strategy.md).
- **S3 Ranges.** A statistic shows mean, standard deviation, minimum, maximum, n and n_failed, and the label "below minimum repetitions" when it applies (§Configurations and repetitions). On a system or reference page all of them are in view, on the plate and in the table. In a table across systems the printed figure is the mean, with n, n_failed, minimum and maximum in view; the standard deviation MAY leave view, and at 560 px wide and below so MAY n, n_failed, minimum and maximum. What leaves view stays where S2 puts a label that leaves view. "Below minimum repetitions" never leaves view.
- **S4 Display rounding.** Values are shown with 4 significant digits. Rounding is display only (RFC-0012): the full stored value is in the linked record (S2), and every order S5 computes uses it, through a sort key in one base unit that the generator computes from the stored value and never types (AGENTS.md rule 3). A `title` attribute MAY repeat the full value; on its own it does not meet this rule.
- **S5 No ranking.** In the HTML as sent, rows are ordered alphabetically by system name, then workload id, then profile; this is also the order shown when the URL has no hash. A reader with script MAY re-sort by pressing a column head. A second press reverses the order. One order applies to every sortable table on the page, and it is kept in the URL hash as `#sort=<column>-<asc|desc>`, so a shared link opens in the same order. No hash, an unknown order, or Back to the page without a hash gives the default order. A row with no value in the sorted column goes last in both directions; ties keep the default order. A reader without script gets the default order with every row and figure, column heads that do not look pressable, and `index.json` for any other order (Q2). Reference rows and systems not yet benchmarked are not sorted with the systems. Search results are ordered by how the query matched, then by kind of entry, then by name, never by a metric. No performance column is the default order. There is no rank number, no medal, no aggregate score and no highlight of an extreme value: the sorted column MAY be set apart from the other columns, but no row or value in it is marked.
- **S6 Divisions.** Each table of system rows holds the rows of one workload, so rows of different native workloads are never in one such table (RFC-0003 §Divisions). Tables are grouped by model, largest first, then by workload id. Each table's heading names its workload, its division and its profile, and so names the division of every row in it (INV-WL-5); the system page names the division beside the workload. Where tables of different native workloads sit side by side (two workloads on one model, or a page across models), they show the normalised metrics of RFC-0004 and carry, above them, the header "Native workloads differ: rows are not a head-to-head comparison". Any other table that holds rows from different native workloads (for example a References table that summarises a reference across workloads) carries the same header. Closed-division tables compare directly within one workload. Open-division rows are shown in tables of their own.
- **S7 Runs left out of the figures.** On the system page, above each configuration's figures, its superseded, ineligible and failed runs are listed, each with a link to its run record: a superseded run with its reason and a link to the run that replaces it, an ineligible run with its reasons, a failed run with its failure kind, step, exit code and last line. The same place says how many completed runs the figures are over. These runs never contribute to statistics. Their status is named in words, not shown by strike-through alone (S9).
- **S8 Neutral text.** All site text passes G8 of RFC-0013.
- **S9 Accessibility.** Tables are exposed as tables: native table elements with header cells and `scope` attributes, or, where a layout re-flows each row onto lines of its own, elements with the ARIA `table`, `row`, `columnheader`, `rowheader` and `cell` roles. Either way every cell has one column header and one row header, and a sorted column's header carries `aria-sort`. Labels are text, not colour alone: every glyph state is a word in the page's HTML (in each row header's accessible text in a table, in view on the system page), shown as a word under a pointer, on a tap and on keyboard focus; the legend names each state's ink, and Not stated has an ink with no hue. Pages SHOULD pass an automated WCAG 2.2 AA check at desktop and phone widths.
- **S10 Script.** Pages are built for reading without script, and script only adds to them:
  - Every row, figure, label, glyph state and link is in the HTML as sent, in the default order (S5).
  - Script MAY only reorder rows (S5), find (search over `search.json`, an index the build writes from the same inputs, every entry of which leads to a page of the site), or reveal what the page already holds (a glyph state under a pointer or on a tap, the search sheet on a phone). It never adds, removes or changes a number, label or state.
  - A control that works only with script is not shown, or does not look pressable, without script.
  - Script and every other file load from the site itself; an inline script is allowed only by its hash in the Content-Security-Policy. No page sends anything off the site: no analytics, no third-party fonts or requests, and search matches in the browser. Script keeps no state but the URL hash.
  - The site runs no code from submissions: replies and data reach the page as escaped text (docs/spec/06-security.md §Trust boundaries, item 5).
  - Movement (rows moving to a new order) is instant under `prefers-reduced-motion`.
- **S11 Narrow screens.** Every page works from 320 CSS px wide: no page scrolls sideways, and a wide table re-flows rather than scrolls. Every label S2 and S3 require stays reachable on a phone: in view, or in the figure's accessible description and in view on the plate the figure links to. A `title` attribute alone does not make a label reachable, since touch screens do not show it. Every link and button has a target at least 24 CSS px tall, and no two targets overlap. S1's order holds at every width.

Changes made to this section on 2026-11-07, so that it describes the site the project publishes (`web/`) before Last call:

| Rule | Kept or changed | Reason |
|---|---|---|
| Page table | changed: the live page set plus Release, Targets and Sponsors and conflicts; Home, Workload, Division table, Controls and Methodology folded into other pages | the overview at `/` holds the per-workload tables a reader comes for; each folded page's content is named above; Sponsors and conflicts stays for PRD §7 N4 |
| Script sentence and §Non-Goals | changed: S10 | sorting and search help a reader without changing what a page holds; every page still reads in full without script, and the site still loads nothing from elsewhere |
| S1 | changed: the glyph before every number, the card in full on the system page before its numbers | the six properties of RFC-0016 read across systems in one column; the card stays before every number on the page that holds it (INV-CLAIM-1), one link from each glyph |
| S2 | changed: scope, grade and tier may leave view in tables across systems; plain display words allowed | a table across systems holds several figures per row; each figure's labels stay in its HTML and in view on its plate, and stay in view where rows differ |
| S3 | changed: in tables across systems the sd may leave view, and below 561 px so may n, n_failed and the range | as for S2; every system and reference page keeps all six in view |
| S4 | changed: the full value lives in the linked record and the sort key; `title` optional | a `title` is not reachable on a touch screen or by keyboard; the record is the source a reader and a check both reach |
| S5 | changed: re-sorting by column head with the order in the URL hash; bans kept | one page per address, Back returns to the default order, and the HTML as sent keeps the alphabetical order; see §Alternatives Considered |
| S6 | changed: tables per model and workload, each naming its division | agrees with RFC-0003 §Divisions (separate tables per native workload) and INV-WL-5 (every row names its division); the header is kept |
| S7 | changed: runs named in words, with links, above the figures | strike-through shows a status by style alone and makes the reason hard to read; failed runs join the list, as §Configurations and repetitions asks |
| S8 | kept | |
| S9 | changed: ARIA table roles allowed beside `th` with `scope`; glyph states as text | a table that re-flows each row onto lines can lose native table semantics in some browsers; explicit roles keep the structure |
| S10 | new | replaces the script sentence |
| S11 | new | a shared link is often opened on a phone, and the first draft said nothing of narrow screens; the rules for labels and order must hold there too |

Where the public site at `web/` does not yet meet these rules, for #320 (which builds one generator against them):

- S1: the glyph states come from `web/_data/criteria.json` ("Draft criteria, needs an RFC"), not from claim cards by RFC-0016's criteria; system pages do not show the claim card in full.
- S2: the measured plates and the more-numbers table link no source, since no run record exists yet; only the One proof covers plate links its source.
- S3: the more-numbers table shows one value per figure, with no mean, standard deviation, range or counts.
- S4: until the S2 source links exist, a system page reader cannot reach the full stored value.
- S6: tables are headed by model only; no heading names its workload id, division or profile, and none links the workload record.
- S7: the runs left out are counted in one line with their reasons; no run id, link to a run record or link to the replacing run is given.
- S9: a glyph state is not shown as a word on keyboard focus.
- Pages: there is no release, targets or sponsors and conflicts page; the footer links none of them; the criteria page does not open with what the benchmark measures and does not; system pages have no division, per-control list, link to reference rows or reply.
- `iproofs site build` follows the first draft of this section (no script, one static page per sort key) and none of the changes above.

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

**One static page per sort column, so re-sorting needs no script.** The first draft of S5, and what `iproofs site build` writes. Considered because every order then reads without script. Rejected on 2026-11-07: each column and direction is another page holding a copy of every number, so the golden files and the link checks grow with the columns; a shared copy opens in an order that is not the default and has no way back to it but navigation; and the copies add nothing a reader without script needs, since the page as sent holds every row in the default order and `index.json` serves any other. The column heads with the order in the URL hash (S5) keep one page per address, open a shared link in the order it was shared in, and return to the default order with no hash.

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

## Testing Strategy

- `harness/tests/unit/test_results_writer.py::test_log_truncation_keeps_head_and_tail`, `::test_untruncated_digest_recorded`, `::test_run_dir_cap_enforced`.
- `test_append_only.py::test_modified_run_file_rejected`, `::test_added_review_accepted`, `::test_deleted_run_rejected` (G2 `APP-1` against a two-commit fixture repository).
- `test_freeze.py::test_deterministic_index` (freeze the fixture release twice in different working directories, byte-identical `index.json`), `::test_review_window_under_14_days_fails`, `::test_insufficient_repetitions_flagged`, `::test_ineligible_run_excluded`, `::test_superseded_run_excluded_and_listed`, `::test_tier_reproduced_requires_unaffiliated_reproducer`, `::test_failed_reproduction_listed_tier_unchanged`.
- `test_targets.py::test_least_favourable_repetition_used` (repetitions 58 s, 59 s, 63 s against `<= 60 s` gives `does_not_meet`), `::test_scope_mismatch_not_evaluable`, `::test_applies_to_filter_hides_target`.
- `test_reply.py::test_301_words_fails`, `::test_html_escaped`.
- Site golden tests in `harness/tests/golden/site/`: build the site from the fixture release, compare HTML to stored golden files, and parse every page as sent:
  - `::test_every_number_has_labels` (S2): each quantity and statistic has unit, scope, grade and tier and a source link in view, or, in a table across systems, its unit in view, the other labels in its accessible description and a link to its plate, where they are in view; a column whose rows differ in a label shows it in view.
  - `::test_glyph_before_numbers` (S1): on every page, each system's glyph precedes that system's first number in DOM order, and links to its system page.
  - `::test_claim_card_before_numbers` (S1, INV-CLAIM-1): on system pages the claim card in full precedes the first number.
  - `::test_statistics_shown` (S3): every statistic shows its six values, and "below minimum repetitions" where it applies, in view on system and reference pages.
  - `::test_sort_key_is_stored_value` (S4): each sort key equals the stored value in one base unit, and the printed figure is that value at 4 significant digits.
  - `::test_default_order_alphabetical` (S5): the HTML as sent holds the rows in the default order.
  - `::test_no_ranking` (S5): no rank number, medal, aggregate score or marked extreme value in any page.
  - `::test_division_named` and `::test_native_workloads_header` (S6): each table heading names its workload, division and profile; tables of different native workloads side by side, and any table mixing them, carry the header.
  - `::test_runs_left_out_listed` (S7, replaces `test_superseded_and_ineligible_struck_through`): the fixture's superseded run and failed repetition are listed above the figures with their reasons, exit code, last line and links, and are not in any statistic.
  - `::test_table_semantics` (S9): every cell has one column header and one row header, through `th` with `scope` or ARIA table roles; every glyph state is a word in the HTML.
  - `::test_reads_without_script` (S10, replaces `::test_no_script_tags_required`): every row, figure, label and glyph state is in the HTML as sent; every script is a site file or an inline script whose hash the Content-Security-Policy lists; no page names a resource on another origin.
- Site browser checks, in a headless browser on the CPU against the built site served with its headers (`web/shoot.mjs` runs most of them on the public site today; #320 places them with the generator it keeps):
  - `::test_script_off` (S10): with script off, every page shows the same text as its HTML and no control that needs script.
  - `::test_sort_from_hash` (S5, S10): every column and direction from the heads and from a loaded `#sort=` hash; no hash gives the default order; an unknown order falls back and is cleared from the URL; Back to the page without a hash restores the default; rows with no value go last both ways; each table holds the same text before and after every sort; no row or value is marked in any order.
  - `::test_search_local` (S5, S10): search loads only `search.json` from the site, sends no request while typing, and orders results by match, kind and name; without script it is not shown.
  - `::test_states_as_text` (S9): a glyph state shows as a word under a pointer, on a tap and on keyboard focus, and the word is one the HTML already holds.
  - `::test_narrow_screens` (S11): at 320, 360 and 390 px wide and on a phone held sideways, on every page: no sideways scroll, every S2 and S3 label reachable, every link and button 24 px tall or more with no overlap, and each glyph before its system's numbers.
  - `::test_accessibility_check` (S9): an automated WCAG 2.2 AA check on every page at a desktop and a phone width.

## Open Questions

- Resolved Q1: archived proofs and the upstream inputs stored with them (RFC-0014 Q3) go to the public dataset repository `abdelstark/inference-proofs-archive` on the Hugging Face Hub (amended 2026-11-06: the project's organisation on the Hub does not exist yet, and the maintainer chose a dataset under their own account; a later move keeps every recorded URI valid, since each is pinned to a dataset commit). Reasons: one configuration's proof can be large (the SASH 4,096-context run's proofs total about 19.8 GB, as above), and it fits, where the caps of other free hosts may not ([2 GiB per GitHub release asset](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases), [50 GB per Zenodo record](https://help.zenodo.org/docs/deposit/manage-files/), both as stated by those hosts on 2026-11-04); every file is addressed at an immutable commit; and the v0.1 workloads already fetch their weights from the same Hub. Each `manifest.proofs[].archive` URI is pinned to the dataset commit (`.../resolve/<commit>/<path>`), and the stored object's sha256 is read back and checked before the URI is recorded (`iproofs archive upload`, docs/runbooks/gpu-run.md). Uploads happen on the runner's host before the results pull request, because results are append-only. The freeze rule stands: a configuration without an archive URI is ineligible. A release may also deposit its archive with a DOI later; that changes no URI.
- OPEN QUESTION Q2 (owner: AbdelStark, resolve by: 2027-03-31): whether to offer a machine-readable feed for existing landscape maps. Default: `index.json` is published next to the site and is the feed.
- OPEN QUESTION Q3 (owner: AbdelStark, resolve by: RFC-0001 permanent home decision, target 2027-03-31): where the site is hosted. Default: built in CI as an artifact for review; publication location chosen with the permanent home.

## References

- PRD §4 goals G1, G3, G5; §7 N2, N3, N4; §9 targets; §11 risks.
- [RFC-0002](0002-claim-card.md), [RFC-0003](0003-workloads.md), [RFC-0004](0004-metrics-timing-grades.md), [RFC-0007](0007-evidence-tiers-and-reproduction.md), [RFC-0008](0008-negative-controls.md), [RFC-0012](0012-schemas-and-serialization.md), [RFC-0013](0013-validation-and-ci.md), [RFC-0014](0014-provenance-and-integrity.md).
- MLPerf submission review practice; Ethproofs per-prover rows (PRD §2).
