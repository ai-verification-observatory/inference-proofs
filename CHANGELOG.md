# Changelog

All notable changes to the harness, the schemas and the methodology. Format: [Keep a Changelog 1.1](https://keepachangelog.com/en/1.1.0/), plus a `Methodology` section for changes that need an RFC, each naming its RFC ([docs/spec/09-release-and-versioning.md §CHANGELOG discipline](docs/spec/09-release-and-versioning.md#changelog-discipline)).

Every pull request that changes the public API, a schema or the methodology adds an entry under `Unreleased`. Entries are plain statements of what changed. Any number in an entry carries its labels (AGENTS.md rule 2). CI does not check this file in v0.1; reviewers do.

## [Unreleased]

### Methodology

- RFC-0015: vLLM v0.32.0 pinned for the reference rows (Q1) and teacher-forced argmax through `prompt_logprobs` (Q3); a reference loads only the workload's pinned files (PM-0) and may use the same bit widths in another number format (PM-4), so the SASH reference rows run FP8 W8A8 as a declared substitution (from #257).
- RFC-0009 Q1: archived proofs are stored in a public dataset repository on the Hugging Face Hub, at URIs pinned to the dataset commit.
- RFC-0014 Q2: release images live in `ghcr.io/ai-verification-observatory/`, kept indefinitely.
- RFC-0001 to RFC-0015 added as Draft: governance, claim card, workloads, metrics and grades, adapter contract, reference hardware and cost, evidence tiers, negative controls, publication, runner, measurement, schemas, validation and CI, provenance, reference rows.

### Added

- The `iproofs` harness package (`harness/`), with `validate`, `derive`, `run` and `controls` commands.
- JSON Schemas under `schema/`, each with valid and invalid examples.
- The `fake` and `fake-broken` test systems, the `fake-tiny-ci` workload and the `ci-cpu` profile.
- Tree gates G2 to G7 and G9, and the G10 fake-system end-to-end job (RFC-0013).
- `review/1` and `reproduction/1` schemas with their models (RFC-0007).
- `iproofs prompts build WORKLOAD --seed SEED`: rebuild and digest a job's prompt set from the verified corpus and tokenizer file (RFC-0003).
- `iproofs fetch-model WORKLOAD`: weights fetched at the pinned revision into a read-only cache, every file and the model digest checked, rehashed at every job start (RFC-0014).
- `iproofs machine-record --selftest [--gpu INDEX] [--probe-image IMAGE_ID]`: the RFC-0011 calibration checks ST-CLOCK to ST-OOM, saved for the runner's manifests.
- `iproofs machine-record`: the RFC-0006 machine record from allowlisted probes; every run records it before `info` and checks it again after the last step (INV-MR-2).
- `iproofs run --runner HANDLE --runner-org ORG --affiliated SYSTEM`: the declared runner recorded in every manifest; `iproofs.release.is_unaffiliated` (RFC-0007 §Tiers).
- `iproofs archive upload`: uploads proof archives and the adapters' upstream inputs to the archive dataset, checks every stored digest and records the pinned archive URI in the manifest (RFC-0014, RFC-0009 Q1).
- `iproofs reproduce compare ORIG_RUN REPRO_RUN`: eligibility, the tolerance rule, verdict and digest matching, and the `reproduction/1` record (RFC-0007).

### Changed

- `run/1` `proofs[]`: optional `request_index`, `claimed_output` and, for ref-recompute runs, `agreement`; `adapter-job/1`: optional `claims_file` on `prove`. The runner passes a source run's claims to a ref-recompute job and records the agreement counts as run metrics (RFC-0015 RC-1, RC-5).
- Release freeze refuses a prover run whose image is not in `ghcr.io/ai-verification-observatory/` (eligibility reason `image_not_in_project_registry`, RFC-0014 Q2 and B7; from #255).
- CI runs the unit tests in three shards per Python version and combines coverage in the `tests` jobs, whose check names are unchanged (docs/spec/07 §Sharding).
### Deprecated

### Removed

### Fixed

### Security

- The commitment a verifier checks comes only from the harness's commit record (RFC-0014 §The commitment record).
