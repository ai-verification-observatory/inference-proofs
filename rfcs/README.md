# RFCs

Methodology decisions (what is measured, how, and how it is published) and load-bearing technical decisions (interfaces, schemas, measurement, integrity) are written down as RFCs. The status column is a label, not a gate.

| # | Title | Status | Target milestone |
|---|---|---|---|
| [0001](0001-process-and-governance.md) | RFC format | Draft | v0.1-alpha |
| [0002](0002-claim-card.md) | Claim card | Draft | v0.1-alpha |
| [0003](0003-workloads.md) | Workloads, prompt sets and divisions | Draft | v0.1-alpha |
| [0004](0004-metrics-timing-grades.md) | Metrics, timing scopes and grades | Draft | v0.1-alpha |
| [0005](0005-adapter-contract.md) | Adapter contract | Draft | v0.1-alpha |
| [0006](0006-reference-hardware-and-cost.md) | Reference hardware and cost basis | Draft | v0.1-alpha |
| [0007](0007-evidence-tiers-and-reproduction.md) | Evidence tiers | Draft | v0.1 |
| [0008](0008-negative-controls.md) | Negative controls | Draft | v0.1-alpha |
| [0009](0009-results-and-publication.md) | Results format and publication | Draft | v0.1 |
| [0010](0010-harness-runner.md) | Harness runner and job lifecycle | Draft | v0.1-alpha |
| [0011](0011-measurement-and-sampling.md) | External measurement and resource sampling | Draft | v0.1-beta |
| [0012](0012-schemas-and-serialization.md) | Artifact schemas, labelled quantities and serialization | Draft | v0.1-alpha |
| [0013](0013-validation-and-ci.md) | Validation pipeline and CI gates | Draft | v0.1-alpha |
| [0014](0014-provenance-and-integrity.md) | Provenance, pinning and artifact integrity | Draft | v0.1-beta |
| [0015](0015-reference-rows.md) | Reference rows: production serving and recompute | Draft | v0.1-beta |
| [0016](0016-glyph-properties-and-states.md) | Glyph properties and states | Draft | v0.1 |

## Out for the research phase

The project has no users yet (owner decision, 2026-11-09). These rules are out until a public release needs them; they come back from git history, not from this page:

- Governance: RFC statuses as gates, Last call, MAINTAINERS.md and its checks (GOV-*, INV-GOV-*, LIC-1), the merge guard, DCO sign-off, one pull request per change.
- Release ceremony: review window, freeze date, replies, sponsors, candidate site.
- Evidence tiers beyond `reported`: peer review, reproduction records, effective tiers.
- Eligibility reasons `nonconforming_host`, `image_digest_kind_config`, `image_differs_from_system_yaml`, `image_not_in_project_registry`, `no_archived_proof`; the proof archive requirement.
- Profile conformance as a refusal (PC-*, PC-GPU-IDLE, POL-4): checks are recorded, never refuse a run.
- Gates LBL-4, CARD-1 to CARD-3, RPL-1, TIER-3, CRIT-*, and the coverage floor.
- Serving join bookkeeping: placement exhaustion across GPU counts, NM-1, observed-engine matching; D-OVERHEAD-SESSION and the `whole_wall` overheads.

New RFC: copy [0000-template.md](0000-template.md) to the next free number and fill the sections that apply.
