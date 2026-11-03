# RFC-0009: Results format and publication

- Status: Draft
- Created: 2026-11-03
- Requires: RFC-0002, RFC-0004, RFC-0007, RFC-0008

## Summary

How runs are stored, how a release is cut, what the site shows, and how teams and relying parties respond.

## Specification

### Storage

```
results/<release>/<system>/<run-id>/
  run.json         every recorded and derived number, each with scope, grade and tier
  manifest.json    image digest, upstream commit, workload hashes, machine record, command lines, provider
  controls.json    RFC-0008 verdicts
  verifier/        verifier output per proof (exit code, last lines)
  logs/            harness and adapter logs, size-capped
  digests.txt      SHA-256 of every proof; one proof per configuration archived in full
```

`run-id` is `<date>-<system>-<workload>-<profile>-<n>`. `results/` is append-only; a correction is a new run that names the one it replaces.

### Release

A release freezes: the runs it includes, the reference file (RFC-0006), the RFC versions in force, and the claim cards as reviewed. Before a release, every listed system maintainer gets at least 14 days to review its rows and cards and to write a reply.

### Site

Static, generated from `results/` and `systems/`. Per system: the claim card first; then rows, each showing workload, profile, scope, grade and tier beside every number; controls; reference rows on the same workload; the system maintainers' reply. Across systems: a table filtered by division, never sorted by speed by default, with no aggregate score.

### Targets

Relying parties publish targets as `targets/<author>/<id>.yaml`: a named metric, a threshold, the claim class it applies to, a rationale, the author and a date. The site shows, per row, "meets" or "does not meet" each applicable target, attributed to its author. The project itself publishes no targets.

### Right of reply

A system maintainer's reply is printed beside the system's rows, unedited, up to 300 words per release.

### Reports

One short report per release in `reports/`, reviewed by every listed team, stating what changed, what was reproduced, what failed, and what the numbers do not show.

## Open questions

1. Hosting for archived proofs (SASH's 4,096-context run alone totals about 19.8 GB of proofs).
2. Whether to offer a machine-readable feed for existing landscape maps.
