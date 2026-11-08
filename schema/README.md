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
- `$id` and `$ref` resolve from this tree only. The validator never fetches anything over the network; the `$id` host is a placeholder until the project's permanent home is decided (RFC-0012 Q1).
- Every object sets `additionalProperties: false` unless the schema documents it as an open map.
- Formats asserted: `date`, `date-time`, `uri` (syntax only).

## Status

Schemas in the RFC-0012 catalogue that have landed, with their Python model in `iproofs.model`:

| Schema | Instances | Model |
|---|---|---|
| `quantity/1` | shared `$defs` | `Quantity`, `Statistic`, `Stats`, `Source`, `Quality` |
| `run/1` | `results/<release>/<system>/<run-id>/run.json` | `Run` |
| `manifest/1` | `results/<release>/<system>/<run-id>/manifest.json` | `Manifest` |
| `claim/1` | `systems/<name>/claim.yaml`, `systems/<name>/claims/<configuration>.yaml` | `ClaimCard` |
| `workload/1` | `workloads/<id>.yaml` | `Workload` |
| `corpus/1` | `workloads/prompts/corpus.yaml` | `Corpus` |
| `system/1` | `systems/<name>/system.yaml` | `System` |
| `system-controls/1` | `systems/<name>/controls.yaml` | `SystemControls` |
| `reference/1` | `reference/<release>.yaml` | `ReferenceFile` |
| `adapter-job/1` | `/io/job.json` inside an adapter container | `AdapterJob` |
| `adapter-out/1` | `/io/out.json` inside an adapter container | `AdapterOut`, `ProofEntry`, `CommandLine` |
| `controls/1` | `results/<release>/<system>/<run-id>/controls.json` | `Controls` |
| `controls-part/1` | `<run-dir>/controls-part-<seed>-<subset>.json`, a working file (RFC-0008 §Split suites) | `ControlsPart` |
| `release/1` | `releases/<release>/release.yaml` | `Release` |
| `release-index/1` | `releases/<release>/index.json` | `ReleaseIndex` |
| `target/1` | `targets/<author>/<id>.yaml` | `Target` |
| `review/1` | `results/<release>/<system>/<run-id>/reviews/<reviewer>-<date>.json` | `ReviewRecord`, `Reviewer`, `ReviewChecks`, `Objection` |
| `reproduction/1` | `results/<release>/<system>/<run-id>/reproductions/<repro-run-id>.json` | `ReproductionRecord`, `ReproductionEligibility`, `Comparison`, `ComparedStats`, `DigestMatch` |
| `perturbed-commitment/1` | `results/<release>/<system>/_controls/<workload>/perturbed.json` | `PerturbedCommitmentRecord` |
| `site-facts/1` | `web/_data/facts.json` | `SiteFacts`, `SiteInfo`, `ModelFacts`, `RowFacts`, `LicenceFacts`, `StatusFacts` |
| `criteria/1` | `web/_data/criteria.json` | `CriteriaFile`, `CriteriaState`, `CriteriaProperty`, `CriteriaRow` |

## Examples rule

Every schema ships valid and invalid examples (AGENTS.md, working practice). Each invalid example has a sibling `<file>.reason` whose text must appear in the validation error, so an example cannot fail for an unrelated reason. Gate G2 runs the rule ([RFC-0013 §G2](../rfcs/0013-validation-and-ci.md#g2-schema-validation)); locally, `iproofs.schema.check_examples` runs it.

## Quantity

`quantity/1` holds shared `$defs` only: `quantity`, `statistic`, `stats`, `source` and the identifier patterns. No document names it in its `schema` field. Its examples are single values named `<def>.<case>.json` and are validated against `$defs/<def>`. Rules that need more than one value (the derivation graph, INV-QTY-3 second half, INV-QTY-6a, INV-QTY-9 OR rule) belong to gate G5; INV-QTY-8 `value == stats.mean` is checked by `iproofs.quantity.statistic_problems`.

## Changing a schema

Additive changes (a new optional property, a wider enum, a new `$defs` entry) edit the current file and add a CHANGELOG entry. Anything else is a new major file and needs an RFC ([RFC-0012 §Schema versioning](../rfcs/0012-schemas-and-serialization.md#schema-versioning)).
