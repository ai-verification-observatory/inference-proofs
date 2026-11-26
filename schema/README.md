# Schemas

This directory contains JSON Schema Draft 2020-12 definitions for every document the project reads or writes. The schema catalogue, versioning rules, and labelled-quantity types are defined normatively in [RFC-0012](../rfcs/0012-schemas-and-serialization.md#schema-catalogue).

## Layout

```
schema/<name>/<major>.schema.json      $id = https://inference-proofs.org/schema/<name>/<major>.schema.json
schema/<name>/examples/valid/*         must validate
schema/<name>/examples/invalid/*       must fail
schema/<name>/examples/invalid/*.reason   text the validation error must contain
```

- Every document identifies its schema in a top-level `schema` field formatted as `<name>/<major>` (for example, `run/1`), which each schema fixes with `const`.
- All `$id` and `$ref` lookups resolve strictly within this local tree. The validator never makes network requests, and the `$id` hostname is purely an identifier that is never dereferenced (RFC-0012 Q1).
- Every object sets `additionalProperties: false` unless the schema explicitly defines it as an open map.
- Format assertions cover `date`, `date-time`, and `uri` (syntax only).

## Status

The table below lists all schemas from the RFC-0012 catalogue that are currently implemented, along with their corresponding Python models in `iproofs.model` where code accesses fields directly ([RFC-0012 §Python loading](../rfcs/0012-schemas-and-serialization.md#python-loading)):

| Schema | Instances | Model |
|---|---|---|
| `quantity/1` | shared `$defs` | `Quantity`, `Source`, `Quality` |
| `run/1` | `results/<release>/<system>/<run-id>/run.json` | none (read as a tree) |
| `manifest/1` | `results/<release>/<system>/<run-id>/manifest.json` | none (read as a tree) |
| `claim/1` | `systems/<name>/claim.yaml`, `systems/<name>/claims/<configuration>.yaml` | `ClaimCard` |
| `workload/1` | `workloads/<id>.yaml` | `Workload` |
| `corpus/1` | `workloads/prompts/corpus.yaml` | `Corpus` |
| `system/1` | `systems/<name>/system.yaml` | `System` |
| `system-controls/1` | `systems/<name>/controls.yaml` | `SystemControls` |
| `reference/1` | `reference/<release>.yaml` | `ReferenceFile`, `ProverProfile`, `ServingProfile` |
| `serving-model/1` | `workloads/serving/<id>.yaml` | `ServingModel`, `ServingFiles`, `ServingFile` |
| `adapter-job/1` | `/io/job.json` inside an adapter container | none (read as a tree) |
| `adapter-out/1` | `/io/out.json` inside an adapter container | `AdapterOut`, `ProofEntry`, `CommandLine` |
| `controls/1` | `results/<release>/<system>/<run-id>/controls.json` | none (read as a tree) |
| `controls-part/1` | `<run-dir>/controls-part-<seed>-<subset>.json`, a working file (RFC-0008 §Split suites) | none (read as a tree) |
| `controls-seed/1` | `<run-dir>/controls-seed.json`, the split suite's single seed (RFC-0008 SPLIT-1) | none (read as a tree) |
| `release/1` | `releases/<release>/release.yaml` | `Release` |
| `release-index/1` | `releases/<release>/index.json` | none (read as a tree) |
| `target/1` | `targets/<author>/<id>.yaml` | none (read as a tree) |
| `perturbed-commitment/1` | `results/<release>/<system>/_controls/<workload>/perturbed.json` | `PerturbedCommitmentRecord` |
| `site-facts/1` | `web/_data/facts.json` | `SiteFacts`, `SiteInfo`, `ModelFacts`, `RowFacts`, `LicenceFacts`, `StatusFacts` |
| `criteria/1` | `web/_data/criteria.json` (deleted on 2026-11-15; it stored RFC-0016's vocabulary, such as Formally verified "yes" from documents, which no page uses anymore; the v0.1 record remains in git history at `b9dfa3e`) | none (read as a tree) |
| `level/1` | `levels/L<k>.yaml` (RFC-0018) | none (read by `iproofs.level`) |
| `beacon/1` | `levels/L<k>-beacon.json`, the drand round used to draw prompts (RFC-0018 PR-2) | none (read as a tree) |
| `verify-trace/1` | `<run-dir>/verify-trace/<proof-id>.json`, recording the file opens from a single verify call (RFC-0018 CH-4) | none (read as a tree) |
| `fidelity/1` | `results/<release>/fidelity/<rung>/fidelity.json` (RFC-0018 FI-8), including the run's slot count, the two step thresholds for the Fidelity petal, and each row's tests against them (optional, added 2026-11-13) | none (read as a tree) |
| `fidelity-run/1` | `results/<release>/fidelity/<rung>/fidelity-run.json`, recording a single fidelity run | none (read as a tree) |
| `board/1` | `releases/<release>/board.json`, the dataset consumed by the site (RFC-0018 §The board file); each row's five petals include step, cause, basis, any checks that lowered them, and `reading` when a decision relies on an editor's interpretation (updated in place 2026-11-13 before any release froze; `ineligible_sessions` added in place 2026-11-15) | none (read as a tree) |
| `properties/1` | `systems/<name>/properties.yaml`, storing the glyph's statement petals as typed states; superseded by `properties/2` (2026-11-13) | none (read as a tree) |
| `properties/2` | `systems/<name>/properties.yaml`, storing the underlying facts for each statement petal along with deciding quotes at the pinned commit (RFC-0018 GL-1); `bound.batch`, `bound.program`, and `formal.toolchain` were added in place on 2026-11-13 | none (read as a tree) |
| `refusal/1` | `results/<release>/<system>/refusals/slot-<k>.json`, recording a refusal from a system's own code along with the upstream commit where it occurred (RFC-0018 SE-5, 2026-11-15) | none (read as a tree) |
| `proof-build/1` | `results/<release>/proof-build/<system>/proof-build.json`, recording a build of the theorem referenced in a properties file using the pinned toolchain (exact same spelling) inside a digested image, plus the axioms reported (RFC-0018 MC-4, MC-5) | none (read as a tree) |
| `verifier-trial/1` | `results/<release>/<system>/_trials/<trial id>/trial.json`, recording verify calls on stored proofs outside a session's main suite (such as a second verifier, the C3 null twin, or C1 at every position); these trials do not gate ranking (RFC-0008 §Verifier trials, 2026-11-15) | none (read as a tree) |
| `setup/1` | `<results>/<release>/<system>/_setups/<setup id>/setup.json`, the record of one setup run: info, setup and commit with no prompt, the state commit left kept as `state.tar` beside it, reused by sessions run with `iproofs run --setup` (`iproofs.setups`, RFC-0012 amendment of 2026-11-26) | none (read as a tree) |

## Examples rule

Every schema must include both valid and invalid examples (see AGENTS.md, working practice). Each invalid example is paired with a sibling `<file>.reason` file whose text must appear in the resulting validation error, ensuring the example fails for the intended reason rather than an unrelated mistake. Gate G2 enforces this in CI ([RFC-0013 §G2](../rfcs/0013-validation-and-ci.md#g2-schema-validation)), and you can run it locally via `iproofs.schema.check_examples`.

## Quantity

`quantity/1` defines shared `$defs` only: `quantity`, `statistic`, `stats`, `source`, and the common identifier patterns. No standalone document references it in its `schema` field. Its examples are individual values named `<def>.<case>.json` and are validated directly against `$defs/<def>`. Cross-field rules (such as the derivation graph, the second half of INV-QTY-3, INV-QTY-6a, and the INV-QTY-9 OR rule) are enforced by gate G5, while INV-QTY-8 (`value == stats.mean`) is checked by `iproofs.quantity.statistic_problems`.

## Changing a schema

Additive changes, such as adding an optional property, widening an enum, or introducing a new `$defs` entry, can be made directly in the existing schema file with a corresponding CHANGELOG entry. Any breaking change requires a new major schema file ([RFC-0012 §Schema versioning](../rfcs/0012-schemas-and-serialization.md#schema-versioning)).
