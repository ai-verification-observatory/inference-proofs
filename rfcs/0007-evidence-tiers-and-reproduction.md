# RFC-0007: Evidence tiers, reproduction and peer review

- Status: Draft
- Created: 2026-11-03
- Requires: RFC-0004, RFC-0006

## Summary

Every number says who stands behind it: the authors, a peer reviewer, or an independent reproduction. Only reproduced numbers are called measured.

## Motivation

Published proving numbers are almost always reported by their authors, from scripts and records readers cannot always see. FlashProve's performance page says its timed runs were made by measuring scripts that are not in the repository and that "a reader cannot check the figures on this page against" the run records. SASH publishes its run manifests, but its headline manifest records that the producing prover tree was dirty. Neither is unusual; both mean a reader needs an independent rerun before treating a number as established.

## Specification

### Tiers

| Tier | Meaning | Who |
|---|---|---|
| `reported` | produced by the system's own authors, through this harness or upstream | system maintainers |
| `peer-reviewed` | another submitter has checked the submission: pins, configuration, logs, consistency of derived numbers | a maintainer or system maintainer from a different organisation |
| `reproduced` | rerun end to end through the harness by someone not affiliated with the system's authors, on a machine they chose within the profile, with results within the tolerance below | independent runner |

### Reproduction protocol

1. Same release, same adapter image digest, same workload hashes, same profile.
2. A different machine and, where possible, a different provider.
3. At least three repetitions.
4. Tolerance: the reproduced mean falls within the larger of 10 % or three combined standard deviations of the original. Verdicts and proof digests MUST match where the system is deterministic.
5. A failed reproduction is published as such, with both sets of numbers.

### Peer review before release

Each system maintainer reviews at least one other system's submission, following MLPerf's practice. Objections are issues tagged with the reviewer's organisation. Maintainers resolve them by consensus or vote (RFC-0001).

### Clean builds

A run is eligible for `reproduced` only if its adapter image was built from clean upstream checkouts at full commit hashes. Results imported from upstream with a dirty or unknown source tree are shown as `external`, with that fact noted.

## Rationale and alternatives

A single "verified" badge was rejected: it hides who checked what. Three tiers keep the claim about the number separate from the claim about the system.

## Open questions

1. Whether signed result files from an attested runner could replace part of the reproduction burden.
2. The tolerance for systems with large run-to-run variance (FlashProve reports up to 9 % between whole runs on different machines).
