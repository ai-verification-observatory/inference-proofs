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

## Examples rule

Every schema ships valid and invalid examples (AGENTS.md, working practice). Each invalid example has a sibling `<file>.reason` whose text must appear in the validation error, so an example cannot fail for an unrelated reason. Gate G2 runs the rule ([RFC-0013 §G2](../rfcs/0013-validation-and-ci.md#g2-schema-validation)); locally, `iproofs.schema.check_examples` runs it.

## Changing a schema

Additive changes (a new optional property, a wider enum, a new `$defs` entry) edit the current file and add a CHANGELOG entry. Anything else is a new major file and needs an RFC ([RFC-0012 §Schema versioning](../rfcs/0012-schemas-and-serialization.md#schema-versioning)).
