# 03. Data model

Status: Draft 0.1. Normative detail lives in the RFCs named per object; where this section and an RFC disagree, the RFC takes precedence. Encoding, versioning, digests and identifiers are fixed by [RFC-0012](../../rfcs/0012-schemas-and-serialization.md).

## Purpose

This section lists every object the benchmark stores, its key, what it references, who writes it and when it may change. A contributor adding a field or a file starts here to see which other objects depend on it.

## Entities

| Object | Schema | File | Key | References | Written by | Mutability | Owner RFC |
|---|---|---|---|---|---|---|---|
| Claim card | `claim/1` | `systems/<name>/claims/<configuration>.yaml` | (system, configuration, `card_version`) | upstream commit | system maintainers, by PR | PR reviewed by system maintainers; `card_version` increments on every merged change | [RFC-0002](../../rfcs/0002-claim-card.md) |
| System manifest | `system/1` | `systems/<name>/system.yaml` | system | upstream commit, image digest, workloads, profiles, claim cards; declares `kind` (`prover`, `reference`, `test`), `incremental_proofs`, `proofs.{granularity, tokens_covered, steady_boundary, steady_approximate, verify_reads}`, `forbidden_flags` | adapter author | PR | [RFC-0005](../../rfcs/0005-adapter-contract.md) |
| External figures | `external/1` | `systems/<name>/external.yaml` | (system, figure id) | upstream URL at a pinned commit | adapter author | PR | [RFC-0004](../../rfcs/0004-metrics-timing-grades.md) |
| System controls | `system-controls/1` | `systems/<name>/controls.yaml` | (system, control id) | system manifest | adapter author | PR | [RFC-0008](../../rfcs/0008-negative-controls.md) |
| Workload | `workload/1` | `workloads/<id>.yaml` | (id, version) | model source and revision, corpus | maintainers | new version for any change that alters a number | [RFC-0003](../../rfcs/0003-workloads.md) |
| Prompt corpus | `corpus/1` | `workloads/prompts/corpus.yaml` | corpus digest | public source URLs | maintainers | new digest on any change | RFC-0003 |
| Reference file | `reference/1` | `reference/<release>.yaml` | release | none | maintainers | frozen at release | [RFC-0006](../../rfcs/0006-reference-hardware-and-cost.md) |
| Adapter job | `adapter-job/1` | `/io/job.json` (transient) | (run, step) | commitment record, workload | harness | never stored outside the run's logs | RFC-0005 |
| Adapter output | `adapter-out/1` | `/io/out.json` (transient, copied into the run) | (run, step) | none | adapter | copied canonically by the harness | RFC-0005 |
| Run | `run/1` | `results/<release>/<system>/<run-id>/run.json` | run-id | workload (id, version), system, profile, release, claim card (`card_version`), replaced run; holds the `events` list `{event, mono_ns}` | harness | append-only | [RFC-0009](../../rfcs/0009-results-and-publication.md), RFC-0004 |
| Manifest | `manifest/1` | `.../<run-id>/manifest.json` | run-id | image digest, upstream commit, model digest, corpus digest, prompt seed, reference file digest, claim card, runner `{handle, organisation, affiliated_systems}`, machine self-test result | harness | append-only | [RFC-0014](../../rfcs/0014-provenance-and-integrity.md) |
| Control outcomes | `controls/1` | `.../<run-id>/controls.json` | run-id | the run's proofs, perturbed commitment | harness | append-only | RFC-0008 |
| Control suite seed | `controls-seed/1` | `<run-dir>/controls-seed.json`, never in `results/` | run-id | the run's manifest | `iproofs controls --draw-seed` | written once | [RFC-0008 §Split suites](../../rfcs/0008-negative-controls.md#split-suites) |
| Control suite part | `controls-part/1` | `<run-dir>/controls-part-<seed>-<subset>.json`, never in `results/` | (run-id, seed, subset) | the run's manifest and seed record | `iproofs controls --only` | working file, merged by `--merge` | [RFC-0008 §Split suites](../../rfcs/0008-negative-controls.md#split-suites) |
| Verifier record | part of `run/1` defs | `.../<run-id>/verifier/<proof_id>.json` | (run-id, proof id) | proof digest | harness | append-only | RFC-0009 |
| Review record | `review/1` | `.../<run-id>/reviews/<reviewer>-<date>.json` | (run-id, reviewer, date) | run | peer reviewer | add-only | [RFC-0007](../../rfcs/0007-evidence-tiers-and-reproduction.md) |
| Reproduction record | `reproduction/1` | `.../<run-id>/reproductions/<repro-run-id>.json` | (original run-ids, reproduction run-ids) | both sets of runs | `iproofs reproduce compare` | add-only | RFC-0007 |
| Perturbed commitment | `perturbed-commitment/1` | `results/<release>/<system>/_controls/<workload>/perturbed.json` | (release, system, workload) | workload | `iproofs controls --prepare-perturbed` | write-once per release | [RFC-0008](../../rfcs/0008-negative-controls.md#shared-controls-verifier-side) |
| Release record | `release/1` | `releases/<release>/release.yaml` | release | runs, reference file, claim card digests, RFC commit | maintainers | frozen after freeze | RFC-0009 |
| Release index | `release-index/1` | `releases/<release>/index.json` | release | everything in the release record | `iproofs release freeze` | generated once per release | RFC-0009 |
| Target | `target/1` | `targets/<author>/<id>.yaml` | (author, id) | metric id, claim card fields | relying party | PR; history in git | RFC-0009 |
| Reply | Markdown | `systems/<name>/replies/<release>.md` | (system, release) | release | system maintainers | frozen at release | RFC-0009 |
| Maintainers | Markdown | `MAINTAINERS.md` | person | organisations | maintainers | PR | [RFC-0001](../../rfcs/0001-process-and-governance.md) |

A configuration is not a stored object; it is the tuple (system, workload id, workload version, profile, adapter image digest, `control: false`) computed at freeze ([RFC-0009 §Configurations and repetitions](../../rfcs/0009-results-and-publication.md#configurations-and-repetitions)).

## Relations

In words: a run belongs to one system (whose `kind` is `prover`, `reference` or `test`; reference systems skip commit and verify, and `test` systems never appear in a release), one workload version, one profile and one release. Its manifest pins the system's image and upstream commit, the workload's model and corpus digests, the job's prompt seed and the release's reference file. Its controls file refers to its own proofs and, for control C3, to one perturbed commitment recorded in the same release. Review and reproduction records attach to runs. A release record lists runs and claim card digests; the release index derives configurations, statistics, tiers, control summaries and target evaluations from them. Targets reference metric ids and claim card fields and are evaluated against configurations.

```
claims/*.yaml ┐
system.yaml ─┼─< run.json ──── manifest.json
workload ────┤      │  └────── controls.json
reference ───┘      ├─< reviews/*.json
                    └─< reproductions/*.json
release.yaml ──< runs ──> index.json <── targets/*.yaml
```

## Cross-object invariants

Each invariant is checked by the named gate of [RFC-0013](../../rfcs/0013-validation-and-ci.md).

- **INV-DM-1 Referential integrity.** Every run names a workload (id, version), system and profile that exist; every review, reproduction and release entry names existing runs. Gate G2 `XREF-1` to `XREF-4`.
- **INV-DM-2 Labelled numbers.** Every number in a run, controls file, external file, reference file or release index is a quantity or statistic, or sits on the structural-integer allowlist. Gates G2 and G5.
- **INV-DM-3 Derived means computed.** Every `grade: derived` quantity equals its recomputation bit for bit. Gate G4.
- **INV-DM-4 Image consistency.** A run's manifest image digest equals the image digest in its `run.json` and, for release eligibility, the image that `system.yaml` pins at the release commit, built from an ancestor of that commit. Gate G2 `XREF-2`, freeze step 4.
- **INV-DM-5 Commitment provenance.** The `commitment_id` and verifier file digests passed to every verify call equal those recorded in the manifest at the commit step. Enforced structurally by the harness ([RFC-0014 §The commitment record](../../rfcs/0014-provenance-and-integrity.md#the-commitment-record)); tested by G10.
- **INV-DM-6 Control isolation.** A run with `control: true` contributes no measured row to any release table. Gate G6 `POL-2`.
- **INV-DM-7 Tier location.** Tiers in `results/` are `reported`; effective tiers exist only in release indexes. Gate G5 `LBL-3`.
- **INV-DM-8 Append-only.** No file under `results/` changes after merge, except additions under `reviews/` and `reproductions/`. Gate G2 `APP-1`.
- **INV-DM-9 Claim before number.** Every system with a run in a release has a claim card listed by digest in the release record, and every run's `claim.card_version` equals the listed card's. Freeze step 1.
- **INV-DM-11 Conforming hosts only.** No run under `results/` has `harness.nonconforming: true`, and a release includes only runs whose machine self-test passed. Gate G6 `POL-4`, freeze step 4.
- **INV-DM-12 Derived tier.** A derived quantity's tier is the lowest tier among its inputs. Gate G5 `LBL-5`.
- **INV-DM-10 No weights, no proofs in git.** No file under the repository is a model weight or proof part; runs store digests only. Gate G2 rejects files above 5 MiB anywhere outside `results/*/*/*/logs/` with rule `SIZE-1`, and a run directory above 10 MiB.

## Lifecycles

| Object | States |
|---|---|
| Claim card | drafted (empty `reviewed_by`) -> reviewed (system maintainers listed with date) -> frozen in a release by digest; a change after review clears `reviewed_by` for the changed fields' configuration |
| Workload | proposed -> accepted at version 1 -> new version on any change that alters a number; old versions stay |
| Run | allocated (directory created) -> written (`completed` or `failed`) -> merged -> optionally reviewed, reproduced, superseded (by a later run's `replaces`) |
| Release | `release.yaml` drafted -> review window open (candidate index built) -> window closed -> frozen (`index.json` merged) |
| Target | proposed by PR -> published; edits are new commits; a release evaluates the version present at its freeze |

## Schema versioning summary

Every document carries `schema: "<name>/<major>"`. Additive optional fields keep the major; anything else bumps it and needs an RFC. Old majors stay in `schema/`, and readers support the current and previous major for at least one benchmark release. Full rules: [RFC-0012 §Schema versioning](../../rfcs/0012-schemas-and-serialization.md#schema-versioning) and [09-release-and-versioning.md §Schema majors](09-release-and-versioning.md#schema-majors).
