# RFCs

Every methodology decision (what is measured, how, and how it is published) and every load-bearing technical decision (interfaces, schemas, measurement, integrity) is made through an RFC. Code that implements an Accepted RFC needs no RFC of its own. The lifecycle and the review rules are in [RFC-0001](0001-process-and-governance.md). `iproofs validate` checks that each RFC's status line matches its row below (rule `GOV-4`): a status change edits both in the same pull request.

| # | Title | Status | Target milestone |
|---|---|---|---|
| [0001](0001-process-and-governance.md) | Process and governance | Draft | v0.1-alpha |
| [0002](0002-claim-card.md) | Claim card | Draft | v0.1-alpha |
| [0003](0003-workloads.md) | Workloads, prompt sets and divisions | Draft | v0.1-alpha |
| [0004](0004-metrics-timing-grades.md) | Metrics, timing scopes and grades | Draft | v0.1-alpha |
| [0005](0005-adapter-contract.md) | Adapter contract | Draft | v0.1-alpha |
| [0006](0006-reference-hardware-and-cost.md) | Reference hardware and cost basis | Draft | v0.1-alpha |
| [0007](0007-evidence-tiers-and-reproduction.md) | Evidence tiers, reproduction and peer review | Draft | v0.1 |
| [0008](0008-negative-controls.md) | Negative controls | Draft | v0.1-alpha |
| [0009](0009-results-and-publication.md) | Results format and publication | Draft | v0.1 |
| [0010](0010-harness-runner.md) | Harness runner and job lifecycle | Draft | v0.1-alpha |
| [0011](0011-measurement-and-sampling.md) | External measurement and resource sampling | Draft | v0.1-beta |
| [0012](0012-schemas-and-serialization.md) | Artifact schemas, labelled quantities and serialization | Draft | v0.1-alpha |
| [0013](0013-validation-and-ci.md) | Validation pipeline and CI gates | Draft | v0.1-alpha |
| [0014](0014-provenance-and-integrity.md) | Provenance, pinning and artifact integrity | Draft | v0.1-beta |
| [0015](0015-reference-rows.md) | Reference rows: plain serving and recompute | Draft | v0.1-beta |
| [0016](0016-glyph-properties-and-states.md) | Glyph properties and states | Draft | v0.1 |

New RFC: copy [0000-template.md](0000-template.md) to the next free number, fill every section, open a pull request, and follow RFC-0001.
