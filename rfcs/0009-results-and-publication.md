# RFC-0009: Results format and publication

- Status: Draft
- Authors: AbdelStark
- Created: 2026-11-03
- Target milestone: v0.1
- Requires: RFC-0002, RFC-0004, RFC-0007, RFC-0008, RFC-0012, RFC-0014
- Supersedes: none
- Discussion: pull request that introduces it

## Summary

This RFC fixes how runs are stored, how a correction is made, how a release is cut, what the generated site shows and in which order, how relying parties publish targets and how rows are evaluated against them, how system maintainers reply, and what each release report contains. `results/` is append-only. A release is a frozen, deterministic index over a named set of runs. The site shows the claim card before any number, puts scope, grade and tier beside every number, and never ranks.

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
- Every number on the site sits next to its unit, scope, grade and tier, and links to its source record.
- The site has no aggregate score and no default sort by any performance metric.
- Targets are attributed to their authors and evaluated conservatively.

## Non-Goals

- The meaning of metrics (RFC-0004), tiers (RFC-0007), controls (RFC-0008) or claim card fields (RFC-0002).
- Hosting and domain of the site (open question tied to RFC-0001's permanent home).
- A machine-readable feed for third-party landscape maps (Q2).
- Interactive dashboards. The site is static HTML.

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

`iproofs site build [--out DIR]` generates static HTML into `site/_build/` (not committed) from `releases/*/index.json`, `systems/`, `workloads/`, `targets/` and the replies. Templates live in `site/templates/` (Jinja2). No client-side JavaScript is required to read any page.

Pages:

| Page | Content, in this order |
|---|---|
| Home | what the benchmark measures and does not, links to releases, sponsors and conflicts link |
| Release | release scope, RFC commit, reference file, list of systems, list of what was reproduced and what failed |
| System | the claim card in full; then one table per workload with the configuration rows; then controls; then reference rows on the same workload (RFC-0015); then the system maintainers' reply |
| Workload | definition, model and prompt digests, all configurations on it, reference rows |
| Division table | per division (native, closed, open; RFC-0003), one table across systems, claim card summary column first |
| Controls | all control outcomes per configuration, every unexpected outcome in full |
| Targets | every target with its author, and the rows it was evaluated against |
| Methodology | links to every RFC at the release's RFC commit |
| Sponsors and conflicts | sponsors as listed in `release.yaml` and conflicts from `MAINTAINERS.md`, in separate sections |

Rules:

- **S1 Claim first.** On every page that shows a number for a system, the claim card (or on a division table, its `relation`, `security.notion`, `coverage` and `residual` fields) appears before or in the first column of that system's numbers.
- **S2 Labels beside every number.** Every displayed number shows its unit, scope (when not null), grade and tier next to it, and links to the JSON Pointer of its source in the published record. A number shown without these is a template bug, caught by the site golden tests (docs/spec/07-testing-strategy.md).
- **S3 Ranges.** Statistics show mean, standard deviation, minimum, maximum, n and n_failed.
- **S4 Display rounding.** Values are shown with 4 significant digits; the full stored value is in the cell's `title` attribute and in the linked record. Rounding is display only (RFC-0012).
- **S5 No ranking.** Tables are ordered alphabetically by system name, then workload id, then profile. A reader may re-sort by any column through links that generate a sorted static page; no performance column is the default order. There is no aggregate score, no medal, no highlight of an extreme value.
- **S6 Divisions.** Native rows from different workloads appear side by side with the normalised metrics of RFC-0004 and the header "Native workloads differ: rows are not a head-to-head comparison". Closed-division tables compare directly within one workload.
- **S7 Superseded and ineligible.** Superseded runs and ineligible runs are listed, struck through, with the reason; they never contribute to statistics.
- **S8 Neutral text.** All site text passes G8 of RFC-0013.
- **S9 Accessibility.** Tables use header cells with scope attributes; labels are text, not colour alone.

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
- Site golden tests in `harness/tests/golden/site/`: build the site from the fixture release, compare HTML to stored golden files; `::test_every_number_has_labels` parses every page and asserts each numeric cell has unit, grade and tier elements and a source link; `::test_claim_card_before_numbers` asserts DOM order on system pages; `::test_default_order_alphabetical`; `::test_no_script_tags_required`.

## Open Questions

- Resolved Q1: archived proofs and the upstream inputs stored with them (RFC-0014 Q3) go to the public dataset repository `abdelstark/inference-proofs-archive` on the Hugging Face Hub (amended 2026-11-06: the project's organisation on the Hub does not exist yet, and the maintainer chose a dataset under their own account; a later move keeps every recorded URI valid, since each is pinned to a dataset commit). Reasons: one configuration's proof can be large (the SASH 4,096-context run's proofs total about 19.8 GB, as above), and it fits, where the caps of other free hosts may not ([2 GiB per GitHub release asset](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases), [50 GB per Zenodo record](https://help.zenodo.org/docs/deposit/manage-files/), both as stated by those hosts on 2026-11-04); every file is addressed at an immutable commit; and the v0.1 workloads already fetch their weights from the same Hub. Each `manifest.proofs[].archive` URI is pinned to the dataset commit (`.../resolve/<commit>/<path>`), and the stored object's sha256 is read back and checked before the URI is recorded (`iproofs archive upload`, docs/runbooks/gpu-run.md). Uploads happen on the runner's host before the results pull request, because results are append-only. The freeze rule stands: a configuration without an archive URI is ineligible. A release may also deposit its archive with a DOI later; that changes no URI.
- OPEN QUESTION Q2 (owner: AbdelStark, resolve by: 2027-03-31): whether to offer a machine-readable feed for existing landscape maps. Default: `index.json` is published next to the site and is the feed.
- OPEN QUESTION Q3 (owner: AbdelStark, resolve by: RFC-0001 permanent home decision, target 2027-03-31): where the site is hosted. Default: built in CI as an artifact for review; publication location chosen with the permanent home.

## References

- PRD §4 goals G1, G3, G5; §7 N2, N3, N4; §9 targets; §11 risks.
- [RFC-0002](0002-claim-card.md), [RFC-0003](0003-workloads.md), [RFC-0004](0004-metrics-timing-grades.md), [RFC-0007](0007-evidence-tiers-and-reproduction.md), [RFC-0008](0008-negative-controls.md), [RFC-0012](0012-schemas-and-serialization.md), [RFC-0013](0013-validation-and-ci.md), [RFC-0014](0014-provenance-and-integrity.md).
- MLPerf submission review practice; Ethproofs per-prover rows (PRD §2).
