# Changelog

All notable changes to the harness, the schemas and the methodology. Format: [Keep a Changelog 1.1](https://keepachangelog.com/en/1.1.0/), plus a `Methodology` section for changes that need an RFC, each naming its RFC ([docs/spec/09-release-and-versioning.md §CHANGELOG discipline](docs/spec/09-release-and-versioning.md#changelog-discipline)).

Every pull request that changes the public API, a schema or the methodology adds an entry under `Unreleased`. Entries are plain statements of what changed. Any number in an entry carries its labels (AGENTS.md rule 2). CI does not check this file in v0.1; reviewers do.

## [Unreleased]

### Methodology

- RFC-0001 to RFC-0015 added as Draft: governance, claim card, workloads, metrics and grades, adapter contract, reference hardware and cost, evidence tiers, negative controls, publication, runner, measurement, schemas, validation and CI, provenance, reference rows.

### Added

- The `iproofs` harness package (`harness/`), with `validate`, `derive`, `run` and `controls` commands.
- JSON Schemas under `schema/`, each with valid and invalid examples.
- The `fake` and `fake-broken` test systems, the `fake-tiny-ci` workload and the `ci-cpu` profile.
- Tree gates G2 to G7 and G9, and the G10 fake-system end-to-end job (RFC-0013).
- `review/1` and `reproduction/1` schemas with their models (RFC-0007).
- `iproofs machine-record --selftest [--gpu INDEX] [--probe-image IMAGE_ID]`: the RFC-0011 calibration checks ST-CLOCK to ST-OOM, saved for the runner's manifests.
- `iproofs machine-record`: the RFC-0006 machine record from allowlisted probes; every run records it before `info` and checks it again after the last step (INV-MR-2).
- `iproofs run --runner HANDLE --runner-org ORG --affiliated SYSTEM`: the declared runner recorded in every manifest; `iproofs.release.is_unaffiliated` (RFC-0007 §Tiers).
- `iproofs reproduce compare ORIG_RUN REPRO_RUN`: eligibility, the tolerance rule, verdict and digest matching, and the `reproduction/1` record (RFC-0007).

### Changed

### Deprecated

### Removed

### Fixed

### Security

- The commitment a verifier checks comes only from the harness's commit record (RFC-0014 §The commitment record).
