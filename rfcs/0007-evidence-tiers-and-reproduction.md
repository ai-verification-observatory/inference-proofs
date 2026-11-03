# RFC-0007: Evidence tiers, reproduction and peer review

- Status: Draft
- Authors: AbdelStark
- Created: 2026-11-03
- Target milestone: v0.1
- Requires: RFC-0003, RFC-0004, RFC-0006, RFC-0012
- Supersedes: none
- Discussion: pull request that introduces it

## Summary

Every number says who stands behind it: one runner (`reported`), a reviewer from another organisation (`peer-reviewed`), or an independent rerun within tolerance (`reproduced`). Only reproduced numbers are called measured in prose. This RFC revises the tier definitions so that a first run by anyone, not only by a system's authors, starts as `reported`; fixes the review and reproduction record formats; fixes the tolerance formula and the verdict and digest matching rules; defines which runs are eligible for reproduction; and gives the algorithm that computes each run's effective tier at release freeze, since `run.json` itself is append-only and always says `reported`.

## Motivation

Published proving numbers are almost always reported by their authors, from scripts and records readers cannot always see ([PRD §11](../docs/PRD.md#11-risks)). FlashProve's performance page says its timed runs were made by measuring scripts that are not in the repository and that "a reader cannot check the figures on this page against" the run records. SASH publishes its run manifests, but its headline manifest records that the producing prover tree was dirty. Neither is unusual; both mean a reader needs an independent rerun before treating a number as established. [PRD §8](../docs/PRD.md#8-success-metrics) makes third-party reproduction of both systems the v0.1 exit criterion.

The earlier draft defined `reported` as "produced by the system's own authors". In v0.1 the benchmark maintainers run both systems, so a first run is by neither the authors nor an independent reproducer. The tiers must cover that case.

## Goals

- Every quantity carries a tier, and the tier is derived from records, never typed (INV-TIER-1).
- A tier can rise only through an append-only record: a review record or a reproduction record.
- Reproduction is a mechanical check with a written tolerance, run by `iproofs reproduce compare`.
- A failed reproduction is published with both sets of numbers.
- Imported upstream figures never reach `reproduced` without a rerun.

## Non-Goals

- Cryptographic attestation of runners (OPEN QUESTION Q1).
- Auditing a system's security claims; tiers concern numbers, not claims.
- Ranking runners or providers.

## Proposed Design

### Tiers

| Tier | Meaning | Recorded by |
|---|---|---|
| `reported` | produced by one runner and not yet checked; the runner and the runner's affiliation are recorded in the manifest | the run itself (`run.json`) |
| `peer-reviewed` | a maintainer or system maintainer from an organisation other than the runner's has checked the submission: pins, configuration, logs, consistency of derived numbers | a review record |
| `reproduced` | rerun end to end through the harness by a runner unaffiliated with both the system's authors and the original runner, on a machine they chose within the profile, with results within tolerance | a reproduction record with `outcome: within_tolerance` |

The tiers form a total order `reported < peer-reviewed < reproduced`. A run that is reproduced but never peer-reviewed is `reproduced`: reproduction implies the record was checked closely enough to rerun it.

Affiliation. A manifest records `runner: {handle, organisation, affiliated_systems: [system ids]}`. "Unaffiliated with the system's authors" means the runner's organisation is not the organisation of any system maintainer of that system in `MAINTAINERS.md` and `affiliated_systems` does not contain the system. Self-declaration is the v0.1 trust basis; a false declaration is a Code of Conduct matter (RFC-0001) and the affected tiers are recomputed in the next release.

Prose rule (INV-TIER-2): in reports, the site and documentation, the word "measured" describes only `reproduced` numbers. Other numbers are "reported" or "peer-reviewed". The site prints the tier beside every number.

### Review record

`results/<release>/<system>/<run-id>/reviews/<reviewer-handle>-<YYYY-MM-DD>.json`, valid against `schema/review/1.schema.json`:

```json
{
  "schema": "review/1",
  "run_id": "2027-01-10-flashprove-fp-maverick-w1024-b24-prover-h100-1",
  "reviewer": {"handle": "example", "organisation": "Example Org"},
  "date": "2027-01-20",
  "checks": {
    "pins": "pass",
    "configuration": "pass",
    "logs": "pass",
    "derived_numbers": "pass",
    "controls": "pass"
  },
  "objections": [],
  "outcome": "approved"
}
```

- Each `checks` value is `pass`, `fail` or `not_checked`. `outcome` is `approved` only when every check is `pass`; otherwise `objected`.
- `objections`: list of `{check, text, issue}` where `issue` is the issue URL, labelled with the reviewer's organisation.
- INV-TIER-3: `reviewer.organisation` differs from the run's `runner.organisation`. The validator rejects a review record that breaks it.

### Reproduction record

`results/<release>/<system>/<original-run-id>/reproductions/<repro-run-id>.json`, written by `iproofs reproduce compare ORIG_RUN REPRO_RUN`, valid against `schema/reproduction/1.schema.json`:

```json
{
  "schema": "reproduction/1",
  "original_run_ids": ["<run-id>", "..."],
  "reproduction_run_ids": ["<run-id>", "..."],
  "runner": {"handle": "example", "organisation": "Example Org", "affiliated_systems": []},
  "eligibility": {"same_release": true, "same_image_digest": true, "same_workload_digests": true, "same_profile": true, "different_machine": true, "clean_build": true, "repetitions": 3},
  "comparisons": [
    {"metric": "rate_prove.steady", "unit": "token/s", "scope": "prove.steady",
     "original": {"mean": 0.0, "stdev": 0.0, "n": 3},
     "reproduction": {"mean": 0.0, "stdev": 0.0, "n": 3},
     "bound": 0.0, "difference": 0.0, "within": true}
  ],
  "verdicts_match": true,
  "digests": {"required": false, "matched": null},
  "fresh_seed_runs": ["<run-id>"],
  "outcome": "within_tolerance"
}
```

The numbers above are placeholders for shape only. `outcome` is one of `within_tolerance`, `outside_tolerance`, `ineligible`.

A reproduction compares one configuration: all original runs with the same `(system, configuration, workload, profile, image digest)` against all reproduction runs with the same key. A configuration's runs are aggregated per RFC-0004 statistics before comparison.

### Eligibility

A reproduction is eligible (else `outcome: ineligible`, with the failing field `false`) when:

1. Same release, same adapter image digest, same workload ids and versions, same model and corpus digests, same profile (RFC-0006).
2. A different machine, recorded by the machine record (RFC-0006) differing in at least the provider or the run date and the CPU binding; a different provider where possible (SHOULD).
3. At least three successful repetitions replaying the original's recorded seeds (RFC-0003), plus at least one run with a fresh seed.
4. Clean build (INV-TIER-4): the adapter image was built from clean upstream checkouts at full commit hashes, as recorded in the image's input digests (RFC-0014). Results imported from upstream with a dirty or unknown source tree are `external` grade (RFC-0004) and stay `reported`; they are shown with that fact noted.
5. The runner is unaffiliated as defined above.

### Tolerance

For each compared metric with original mean `m_o`, sample standard deviation `s_o`, count `n_o`, and reproduction `m_r`, `s_r`, `n_r`:

```
bound      = max(0.10 * |m_o|, 3 * sqrt(s_o**2 / n_o + s_r**2 / n_r))
difference = |m_r - m_o|
within     = difference <= bound
```

- Computed in binary64 with the RFC-0012 rules; `bound` and `difference` are stored unrounded.
- Compared metrics (all that exist for the configuration): `rate_prove.steady`, `rate_prove.session`, `whole_wall_seconds`, `commit_seconds`, `verify_seconds` (per proof, mean over proofs), `verify_single_thread_seconds`, `prove_gpu_memory_peak`, `prove_host_memory_peak_anon`, `proof_bytes` (RFC-0004 metric ids).
- A metric that is null in either set is listed with `within: null` and does not fail the comparison; a metric null in one set and not the other fails with `difference: null, within: false`.
- Other derived metrics are not compared; they follow from the compared metrics.

### Verdict and digest matching

- Verdicts (INV-TIER-5): for every replayed seed, the multiset of honest verdicts and the outcome of every control (RFC-0008) MUST be identical between original and reproduction. Any difference sets `verdicts_match: false` and `outcome: outside_tolerance`, regardless of timings.
- Digests: when the system's `system.yaml` declares `deterministic_proofs: true`, the proof digests (RFC-0012) for each replayed seed MUST match (`digests.required: true`). A mismatch sets `outcome: outside_tolerance`. When `deterministic_proofs` is false or absent, digests are recorded and not compared.
- Fresh-seed runs are checked for verdicts only (all honest proofs accepted, controls classified as in the original); their timings are not part of the tolerance comparison but are shown.

### Effective tier at release freeze

`iproofs release freeze RELEASE` computes the effective tier of every quantity of every included run and writes it to `releases/<release>/index.json`. `run.json` is never edited.

```python
def effective_tier(run: Run, reviews: list[Review], repros: list[Reproduction], maintainers: Maintainers) -> Tier:
    if run.grade_is_external_only:                         # imported upstream figures
        return "reported"
    if not clean_build(run):                               # INV-TIER-4
        return "reported"
    if any(r.outcome == "within_tolerance"
           and run.run_id in r.original_run_ids
           and is_unaffiliated(r.runner, run.system, run.runner, maintainers)
           for r in repros):
        return "reproduced"
    if any(v.outcome == "approved"
           and v.reviewer.organisation != run.runner.organisation
           for v in reviews):
        return "peer-reviewed"
    return "reported"
```

Rules:

1. The tier is per run and applies to every quantity of grade `measured` or `derived` in it. `asserted` inputs (a price) and `projected` numbers keep tier `reported` always; `external` numbers keep the tier their source states, `reported` by default.
2. A derived quantity's tier is the minimum of the tiers of its inputs (INV-TIER-6). For example, a cost per token derived from a `reproduced` rate and an `asserted` price is `reported`; the site shows the rate's tier and the price's grade separately so the reader sees why.
3. Only records present at freeze count. A later reproduction raises the tier in the next release, never in a published one.

Rule 2 means every cost figure in v0.1 is `reported`, because the price is asserted. This is intended: the price is a choice, not a measurement. The site shows "rate reproduced; price asserted" beside cost figures.

### Failed reproductions

An `outside_tolerance` record is published in the release (INV-TIER-7): the site shows both sets of numbers, the bound and the difference for every metric, and links both run directories. The original run stays at its prior tier. The release report lists every failed reproduction and any explanation from the system maintainers, who may use their reply (RFC-0009).

### Peer review before release

1. Each system maintainer reviews at least one other system's submission (MLPerf practice), producing a review record.
2. Objections are issues labelled with the reviewer's organisation and linked from the record.
3. Maintainers resolve objections by consensus or vote (RFC-0001); a resolved objection gets a new review record with `outcome: approved`; the old record stays.
4. Release approval requires every objection closed (RFC-0001 Release approval).

### Failure modes

| Failure | Response |
|---|---|
| A reproducer declares no affiliation falsely | Tiers recomputed at the next release once known; the event noted in the report |
| No independent runner with H100 access and model licences volunteers | Rows stay `peer-reviewed` or `reported`; the v0.1 success criterion is unmet and the release report says so |
| A system is nondeterministic in timing beyond 10 % | The statistical term of the bound widens with observed variance; if still outside, the reproduction is published as failed |
| Reproduction uses a different image digest | `ineligible`; recorded, not counted |
| Review record from the runner's own organisation | Validator rejects it (INV-TIER-3) |
| Original and reproduction disagree on a control outcome | `outside_tolerance`; the control discrepancy is shown in full and, if a control was accepted where rejection was expected, the RFC-0008 private report applies |

RISK: third-party reproduction depends on volunteers with H100 access and gated-model licences. Resolution plan: line up reproducers during v0.1-beta, ask compute sponsors (disclosed per RFC-0009) to fund an independent runner's machine time, and report the outcome either way.

## Alternatives Considered

- **A single "verified" badge.** Rejected: it hides who checked what. Three tiers keep the claim about the number separate from the claim about the system.
- **Keep the draft definition (reported = by authors).** Rejected: a first run by the benchmark maintainers would have no tier.
- **Write the tier into `run.json` and edit it when evidence arrives.** Rejected: breaks the append-only rule (RFC-0009) and loses history. Computing at freeze from append-only records keeps every past state reconstructible.
- **Fixed relative tolerance only (for example 10 %).** Considered for simplicity. Rejected: FlashProve reports up to 9 % between whole runs on different machines (external, reported, FlashProve documentation at the pin), so a fixed 10 % bound would fail honest reproductions of noisy configurations and pass dishonest ones of quiet configurations equally. The statistical term scales with observed variance.
- **Welch's t-test at a significance level.** Considered because it is standard. Rejected: with n = 3 per side its power is low, and a test answers "is there a difference" rather than "is the difference small enough". A bounded difference is the question a reproducer asks.
- **Reproduction with fresh seeds only.** Rejected: proof digests could never be compared. Replaying seeds plus one fresh-seed run gives both.
- **Signed results from attested runners instead of reproduction.** Deferred (OPEN QUESTION Q1): attestation shows where code ran, not that the numbers hold on another machine.

## Drawbacks

- Reproduction costs as much GPU time as the original runs, plus one fresh-seed run per configuration. The release budget estimate is produced by the derivation code from upstream figures, not typed here.
- Self-declared affiliation can be abused; v0.1 relies on social enforcement.
- INV-TIER-6 makes all v0.1 costs `reported`, which readers may misread as weak evidence; the site's explanation is needed.
- The 3-sigma term can be wide at n = 3, so a real 20 % regression on a very noisy configuration can pass.

## Conflicts of Interest

The author's affiliations and any interest in a measured system are declared in `MAINTAINERS.md` before this RFC enters Last call (RFC-0001).

## Migration / Rollout

1. v0.1-alpha: `review/1` and `reproduction/1` schemas with examples; tolerance and effective-tier functions with unit tests; `iproofs reproduce compare` on fake-system runs.
2. v0.1: peer review round and third-party reproduction of every v0.1 configuration; freeze computes tiers.
3. Revised `reported` definition: no data exists yet; the change is recorded in the CHANGELOG.

## Testing Strategy

Hand-computed cases (AGENTS.md: every derived metric ships a test against a hand-computed case):

- `test_tolerance_relative_dominates`: `m_o=100, s_o=1, n_o=3, m_r=109, s_r=1, n_r=3`: statistical term `3*sqrt(1/3+1/3) = 2.449...`, bound `10`, difference `9`, within.
- `test_tolerance_relative_fails`: same with `m_r=111`: difference `11 > 10`, outside.
- `test_tolerance_statistical_dominates`: `m_o=100, s_o=10, n_o=3, m_r=115, s_r=10, n_r=3`: statistical term `3*sqrt(100/3+100/3) = 24.49...`, bound `24.49...`, within.
- `test_tolerance_zero_variance`: `s_o=s_r=0`, `m_o=0`: bound 0; `m_r=0` within; `m_r=1e-9` outside.
- `test_tolerance_symmetric_in_stats` (property): swapping `(s_o,n_o)` with `(s_r,n_r)` does not change the statistical term.
- `test_verdict_mismatch_overrides`: all timings within, one control outcome differs: outcome `outside_tolerance`.
- `test_digest_required_only_if_deterministic`: digest mismatch with `deterministic_proofs: false` stays `within_tolerance`; with `true` fails.
- `test_null_metric_handling`: null on both sides passes; null on one side fails.
- `test_eligibility_image_digest`: different digest gives `ineligible`.
- `test_effective_tier_order`: fixtures for no records (`reported`), approved review from another organisation (`peer-reviewed`), same-organisation review (rejected by validator), within-tolerance reproduction by an unaffiliated runner (`reproduced`), within-tolerance reproduction by an affiliated runner (stays at review tier), dirty build (`reported`).
- `test_derived_tier_minimum`: derived cost from `reproduced` rate and asserted price is `reported`.
- `test_failed_repro_published`: freeze includes an `outside_tolerance` record in `index.json` with both sets.
- End to end on the fake system: two runs from fixtures with different runner organisations; `reproduce compare` writes a record that validates and freeze yields `reproduced`.

## Open Questions

- OPEN QUESTION Q1 (owner: AbdelStark, resolve by: RFC for v0.3): whether signed result files from an attested runner could replace part of the reproduction burden. Default: no; reproduction is a rerun.
- OPEN QUESTION Q2 (owner: AbdelStark, resolve by: 2027-03-31): whether the tolerance needs per-system adjustment for systems with large run-to-run variance, after the first FlashProve reproduction. Default: the formula above applies to every system unchanged.
- OPEN QUESTION Q3 (owner: AbdelStark, resolve by: 2027-01-31): how affiliation is verified beyond self-declaration. Default: self-declaration with Code of Conduct enforcement.

## References

- [docs/PRD.md](../docs/PRD.md), sections 4 (G3), 7 (F6, N1, N3), 8 and 11.
- MLPerf Inference submission rules and peer review process.
- FlashProve at `9e2bdd8ff5bf9c62f18263d7dac189b0400b260c` (performance page, run-to-run variance); SASH results at `11decec3c0b62c707618aab5deb82750b355d202` (headline manifest, dirty tree).
- [RFC-0003](0003-workloads.md) (seed replay), [RFC-0004](0004-metrics-timing-grades.md) (metric ids, statistics), [RFC-0006](0006-reference-hardware-and-cost.md) (profiles, machine record), [RFC-0008](0008-negative-controls.md) (control outcomes), [RFC-0009](0009-results-and-publication.md) (freeze, append-only), [RFC-0012](0012-schemas-and-serialization.md) (records, digests), [RFC-0014](0014-provenance-and-integrity.md) (clean build).
