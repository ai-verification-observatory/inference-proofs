# Schemas

JSON Schema Draft 2020-12 files for every document the project reads or writes. The catalogue, the versioning rules and the labelled-quantity type are normative in [RFC-0012](../rfcs/0012-schemas-and-serialization.md#schema-catalogue).

## Layout

```
schema/<name>/<major>.schema.json      $id = https://inference-proofs.org/schema/<name>/<major>.schema.json
schema/<name>/examples/valid/*         must validate
schema/<name>/examples/invalid/*       must fail
schema/<name>/examples/invalid/*.reason   text the validation error must contain
```

- Every document names its schema in a top-level `schema` field, `<name>/<major>` (for example `run/1`). Each schema pins that field with `const`.
- `$id` and `$ref` resolve from this tree only. The validator never fetches anything over the network; the `$id` host is a name that is never dereferenced (RFC-0012 Q1).
- Every object sets `additionalProperties: false` unless the schema documents it as an open map.
- Formats asserted: `date`, `date-time`, `uri` (syntax only).

## Status

Schemas in the RFC-0012 catalogue that have landed, with their Python model in `iproofs.model` where code reads the document field by field ([RFC-0012 §Python loading](../rfcs/0012-schemas-and-serialization.md#python-loading)):

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
| `controls-seed/1` | `<run-dir>/controls-seed.json`, the split suite's one seed (RFC-0008 SPLIT-1) | none (read as a tree) |
| `release/1` | `releases/<release>/release.yaml` | `Release` |
| `release-index/1` | `releases/<release>/index.json` | none (read as a tree) |
| `target/1` | `targets/<author>/<id>.yaml` | none (read as a tree) |
| `perturbed-commitment/1` | `results/<release>/<system>/_controls/<workload>/perturbed.json` | `PerturbedCommitmentRecord` |
| `site-facts/1` | `web/_data/facts.json` | `SiteFacts`, `SiteInfo`, `ModelFacts`, `RowFacts`, `LicenceFacts`, `StatusFacts` |
| `criteria/1` | `web/_data/criteria.json` | none (read as a tree) |
| `level/1` | `levels/L<k>.yaml` (RFC-0018) | none (read by `iproofs.level`) |
| `beacon/1` | `levels/L<k>-beacon.json`, the drand round the prompts are drawn from (RFC-0018 PR-2) | none (read as a tree) |
| `verify-trace/1` | `<run-dir>/verify-trace/<proof-id>.json`, the file opens of one verify call (RFC-0018 CH-4) | none (read as a tree) |
| `fidelity/1` | `results/<release>/fidelity/<rung>/fidelity.json` (RFC-0018 FI-8) | none (read as a tree) |
| `fidelity-run/1` | `results/<release>/fidelity/<rung>/fidelity-run.json`, the record of one fidelity run | none (read as a tree) |
| `board/1` | `releases/<release>/board.json`, what the site reads (RFC-0018 §The board file) | none (read as a tree) |
| `properties/1` | `systems/<name>/properties.yaml`, the statement petals of the glyph (RFC-0018 GL-1) | none (read as a tree) |

## Examples rule

Every schema ships valid and invalid examples (AGENTS.md, working practice). Each invalid example has a sibling `<file>.reason` whose text must appear in the validation error, so an example cannot fail for an unrelated reason. Gate G2 runs the rule ([RFC-0013 §G2](../rfcs/0013-validation-and-ci.md#g2-schema-validation)); locally, `iproofs.schema.check_examples` runs it.

## Quantity

`quantity/1` holds shared `$defs` only: `quantity`, `statistic`, `stats`, `source` and the identifier patterns. No document names it in its `schema` field. Its examples are single values named `<def>.<case>.json` and are validated against `$defs/<def>`. Rules that need more than one value (the derivation graph, INV-QTY-3 second half, INV-QTY-6a, INV-QTY-9 OR rule) belong to gate G5; INV-QTY-8 `value == stats.mean` is checked by `iproofs.quantity.statistic_problems`.

## Changing a schema

Additive changes (a new optional property, a wider enum, a new `$defs` entry) edit the current file and add a CHANGELOG entry. Anything else is a new major file ([RFC-0012 §Schema versioning](../rfcs/0012-schemas-and-serialization.md#schema-versioning)).
