# RFC-0012: Artifact schemas, labelled quantities and serialization

- Status: Draft
- Authors: AbdelStark
- Created: 2026-11-03
- Target milestone: v0.1-alpha
- Requires: RFC-0001, RFC-0004
- Supersedes: none
- Discussion: pull request that introduces it

## Summary

This RFC fixes the shape of every file the benchmark reads or writes. It defines the schema catalogue, the `schema` field that every document carries, the versioning rule for schemas, the labelled quantity that carries every number, the YAML subset for authored files, the single JSON writer for generated files, the digest algorithms with exact byte definitions, the identifier formats, and how the Python harness loads documents. Every other RFC that names a file refers to a schema defined here. The goal is that two people who run the same job write byte-identical records, and that CI can recompute every derived number and compare it bit for bit.

## Motivation

AGENTS.md rule 2 says no number is written without its timing scope, grade, evidence tier and source. A rule like that is enforceable only if a number is a typed object, not a bare float in a table. [RFC-0004 §Grades](0004-metrics-timing-grades.md#vocabularies) defines the grade vocabulary and [RFC-0007 §Tiers](0007-evidence-tiers-and-reproduction.md#tiers) the evidence tiers; this RFC gives them a container.

The draft specification listed five kinds of object (claim card, workload, system manifest, run result, control verdicts) and said each has a JSON Schema in `schema/`. It did not say how schemas evolve, how numbers are encoded, how digests are computed, or how a reader tells which schema version a file follows. Without those rules:

- A result file written by harness 0.2 cannot be told apart from one written by harness 0.1, and a reader may misread a renamed field.
- Two runs of `iproofs derive` on two machines may store `0.30000000000000004` and `0.3` for the same ratio, and the CI recompute check ([RFC-0013](0013-validation-and-ci.md)) either fails spuriously or has to use a tolerance that hides real errors.
- A model digest computed by sorting paths in locale order on one host differs from another host's.
- YAML 1.1 parsers turn an unquoted `no` into `false` and `2026-11-03` into a date object, silently changing an authored claim card.

## Goals

- Every document the benchmark reads or writes validates against exactly one schema, named inside the document.
- Every number in every document is a labelled quantity that passes the invariants INV-QTY-1 to INV-QTY-7.
- Generated JSON is byte-deterministic: the same in-memory object always serialises to the same bytes on every supported platform.
- Digests are defined at the byte level, so any implementation in any language reproduces them.
- A derived number recomputed from stored raw numbers equals the stored value under `==` on binary64.
- Schema evolution has a written rule that tells a contributor, without asking, whether a change bumps the major.

## Non-Goals

- The meaning of each metric, scope or grade. That is [RFC-0004](0004-metrics-timing-grades.md).
- The content rules of each object (which claim card fields are required, which controls exist). Those belong to the owning RFC listed in the catalogue; this RFC fixes encoding and envelope only.
- Signing or attesting documents. That is an open question in [RFC-0014](0014-provenance-and-integrity.md#open-questions).
- A general-purpose data format for other projects.

## Proposed Design

### Schema catalogue

All schemas use JSON Schema Draft 2020-12. Each lives at `schema/<name>/<major>.schema.json` with `$id` equal to `https://inference-proofs.org/schema/<name>/<major>.schema.json`. The host in `$id` is a placeholder (see [Open Questions](#open-questions)); validators MUST resolve `$id` and `$ref` from the local `schema/` tree and MUST NOT fetch anything over the network.

| Name | File | Kind | Path of instances | Owner RFC |
|---|---|---|---|---|
| `quantity` | `schema/quantity/1.schema.json` | shared `$defs` only | none (referenced) | this RFC |
| `claim` | `schema/claim/1.schema.json` | authored YAML | `systems/<name>/claim.yaml` or `systems/<name>/claims/<configuration>.yaml` | RFC-0002 |
| `workload` | `schema/workload/1.schema.json` | authored YAML | `workloads/<id>.yaml` | RFC-0003 |
| `corpus` | `schema/corpus/1.schema.json` | authored YAML | `workloads/prompts/corpus.yaml` | RFC-0003 |
| `system` | `schema/system/1.schema.json` | authored YAML | `systems/<name>/system.yaml` | RFC-0005 |
| `reference` | `schema/reference/1.schema.json` | authored YAML | `reference/<release>.yaml` | RFC-0006 |
| `target` | `schema/target/1.schema.json` | authored YAML | `targets/<author>/<id>.yaml` | RFC-0009 |
| `release` | `schema/release/1.schema.json` | authored YAML | `releases/<release>/release.yaml` | RFC-0009 |
| `release-index` | `schema/release-index/1.schema.json` | generated JSON | `releases/<release>/index.json` | RFC-0009 |
| `external` | `schema/external/1.schema.json` | authored YAML | `systems/<name>/external.yaml` | RFC-0004 |
| `system-controls` | `schema/system-controls/1.schema.json` | authored YAML | `systems/<name>/controls.yaml` | RFC-0008 |
| `adapter-job` | `schema/adapter-job/1.schema.json` | generated JSON | `/io/job.json` inside a container | RFC-0005 |
| `adapter-out` | `schema/adapter-out/1.schema.json` | generated JSON (by an adapter) | `/io/out.json` inside a container | RFC-0005 |
| `run` | `schema/run/1.schema.json` | generated JSON | `results/<release>/<system>/<run-id>/run.json` | RFC-0004, RFC-0009 |
| `manifest` | `schema/manifest/1.schema.json` | generated JSON | `results/.../<run-id>/manifest.json` | RFC-0014 |
| `controls` | `schema/controls/1.schema.json` | generated JSON | `results/.../<run-id>/controls.json` | RFC-0008 |
| `review` | `schema/review/1.schema.json` | generated JSON | `results/.../<run-id>/reviews/<reviewer>-<date>.json` | RFC-0007 |
| `reproduction` | `schema/reproduction/1.schema.json` | generated JSON | `results/.../<run-id>/reproductions/<repro-run-id>.json` | RFC-0007 |
| `perturbed-commitment` | `schema/perturbed-commitment/1.schema.json` | generated JSON | `results/<release>/<system>/_controls/<workload>/perturbed.json` | RFC-0008 |
| `site-facts` | `schema/site-facts/1.schema.json` | authored JSON | `web/_data/facts.json` | RFC-0009 |
| `criteria` | `schema/criteria/1.schema.json` | authored JSON | `web/_data/criteria.json` | RFC-0016 |

`external/1` holds upstream figures per system as quantities with `grade: external`; `system-controls/1` registers system-specific controls. Both reuse `$defs` from `quantity/1`. A claim card carries an integer `card_version`, starting at 1 and incremented by every merged change; a system with several statement-changing configurations has one file per configuration under `systems/<name>/claims/` (RFC-0002).

Each schema directory also holds `examples/valid/` and `examples/invalid/`. Every invalid example has a sibling `<file>.reason` text file naming the invariant or keyword it violates. [RFC-0013 §G2](0013-validation-and-ci.md#g2-schema-validation) runs them.

### The `schema` field

Every document has a top-level string property `schema` of the form `<name>/<major>`, matching `^[a-z][a-z-]*/[1-9][0-9]*$`. The validator reads this field first and selects `schema/<name>/<major>.schema.json`. A document without the field, or naming a schema that does not exist in the tree, is rejected with `ErrorKind.config` and the message `<path>: missing or unknown schema "<value>"`.

Each schema constrains its own `schema` property with `"const": "<name>/<major>"`, so a document cannot validate against the wrong file by accident.

### Schema versioning

A change to a schema is classified by these rules, applied in order. The first rule that matches decides.

| Change | Classification |
|---|---|
| Remove a property, rename a property, change a type, narrow an enum, add a `required` entry, tighten a pattern or bound, change the meaning of a value | major: new file `<major+1>.schema.json`, needs an RFC (RFC-0001 §Changes to methodology) |
| Add an optional property, widen an enum, relax a pattern or bound, add a `$defs` entry | additive: edit the current file in place, no RFC, CHANGELOG entry required |
| Edit `description` or `examples` only | editorial: no CHANGELOG entry |

Widening an enum is additive for readers that ignore unknown values, but every enum in these schemas is closed, so an old reader rejects the new value. This is accepted: old readers are not required to read new documents. New readers MUST read every document written under the current and previous major (the reading window is one benchmark release, see [docs/spec/09-release-and-versioning.md](../docs/spec/09-release-and-versioning.md#schema-majors)).

Old majors stay in the tree unchanged. A document is never rewritten to a new major: results are append-only ([RFC-0009 §Storage](0009-results-and-publication.md#storage)). A migration, where needed, writes a new document that names the one it replaces.

Every schema sets `"additionalProperties": false` at every object level except objects explicitly documented as open maps (for example `phases` in `adapter-out`, keyed by adapter-chosen phase names). A typo in a field name is a validation error, not a silently ignored field.

### Labelled quantity

Defined in `schema/quantity/1.schema.json` under `$defs/quantity`. Every number in every `run`, `controls`, `release` index, `external` and `reference` document that is a measurement, a derivation, a projection, an external figure or an asserted input MUST be a quantity. Counts that are structural rather than measured (for example `batch_size` in a workload shape, `n` inside `stats`) are plain integers and are not quantities.

```json
{
  "$defs": {
    "quantity": {
      "type": "object",
      "additionalProperties": false,
      "required": ["value", "unit", "scope", "grade", "tier", "source", "null_reason"],
      "properties": {
        "value": {"type": ["number", "null"]},
        "unit": {"enum": ["s", "ns", "B", "MiB", "J", "count", "token", "token/s", "s/token",
                          "B/token", "USD", "USD/1k_token", "USD/gpu_hour", "%",
                          "param_token/s", "s/bit_token", "ratio"]},
        "scope": {"enum": [null, "setup", "commit", "prove.steady", "prove.session",
                           "whole_wall", "verify", "verify.single_thread", "primitive"]},
        "grade": {"enum": ["measured", "derived", "projected", "external", "asserted"]},
        "tier": {"enum": ["reported", "peer-reviewed", "reproduced"]},
        "source": {"$ref": "#/$defs/source"},
        "null_reason": {"enum": [null, "not_externally_observable", "fewer_than_two_proofs",
                                 "not_applicable", "step_failed", "not_measurable_on_profile",
                                 "missing_input"]},
        "upstream_scope": {"type": "string", "minLength": 1},
        "upstream_grade": {"type": "string", "minLength": 1},
        "mapping": {"enum": ["exact", "approximate", "none"]},
        "quality": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "degraded": {"type": "boolean"},
            "precision_substituted": {"type": "boolean"}
          }
        },
        "note": {"type": "string", "maxLength": 500}
      },
      "allOf": [
        {"if": {"properties": {"value": {"type": "null"}}},
         "then": {"properties": {"null_reason": {"type": "string"}}},
         "else": {"properties": {"null_reason": {"const": null}}}},
        {"if": {"properties": {"unit": {"enum": ["s", "ns", "token/s", "s/token", "USD",
                                                  "USD/1k_token", "param_token/s",
                                                  "s/bit_token"]}}},
         "then": {"properties": {"scope": {"type": "string"}}}},
        {"if": {"properties": {"grade": {"const": "external"}}},
         "then": {"required": ["upstream_scope", "mapping"],
                  "properties": {"source": {"properties": {"kind": {"const": "upstream"}}}}}}
      ]
    },
    "source": {
      "type": "object",
      "additionalProperties": false,
      "required": ["kind", "ref"],
      "properties": {
        "kind": {"enum": ["harness", "adapter", "derivation", "upstream", "reference_file"]},
        "ref": {"type": "string", "minLength": 1},
        "inputs": {
          "type": "array",
          "items": {"type": "string", "minLength": 1},
          "minItems": 1
        }
      },
      "if": {"properties": {"kind": {"const": "derivation"}}},
      "then": {"required": ["inputs"]},
      "else": {"not": {"required": ["inputs"]}}
    },
    "statistic": {
      "allOf": [{"$ref": "#/$defs/quantity"}],
      "required": ["stats"],
      "properties": {
        "stats": {
          "type": "object",
          "additionalProperties": false,
          "required": ["n", "n_failed", "mean", "stdev", "min", "max"],
          "properties": {
            "n": {"type": "integer", "minimum": 0},
            "n_failed": {"type": "integer", "minimum": 0},
            "mean": {"type": ["number", "null"]},
            "stdev": {"type": ["number", "null"]},
            "min": {"type": ["number", "null"]},
            "max": {"type": ["number", "null"]}
          }
        }
      }
    }
  }
}
```

The fragment above is written for reading. Because `additionalProperties: false` does not see properties declared in an `allOf` sibling, the published file splits the base into `$defs/quantityCore` (the properties and the `allOf` conditions, with no `additionalProperties` keyword) and defines:

```json
"quantity":  {"$ref": "#/$defs/quantityCore", "unevaluatedProperties": false},
"statistic": {"$ref": "#/$defs/quantityCore", "required": ["stats"],
              "properties": {"stats": {"$ref": "#/$defs/stats"}},
              "unevaluatedProperties": false}
```

The invalid examples MUST include a statistic with an unknown key and a quantity carrying `stats`, and both MUST be rejected.

Optional fields: `upstream_scope` (the scope name as the upstream source states it), `mapping` (how that scope maps onto this project's scope: `exact`, `approximate` or `none`; RFC-0004 §Timing scopes), `upstream_grade` (the upstream's own grade where it publishes one, for example SASH's `constants.json` grades), `quality.degraded` (the sampler for this number had gaps above the RFC-0011 threshold), `quality.precision_substituted` (a reference row ran at the nearest supported precision rather than the workload's, RFC-0015), `note` (one sentence, shown on the site).

`source.ref` forms by kind:

| `kind` | `ref` form | Example |
|---|---|---|
| `harness` | repo-relative path plus JSON Pointer to the raw record | `results/v0.1/fake/2026-11-20-fake-fake-tiny-ci-ci-cpu-1/run.json#/raw/prove/wall_ns` |
| `adapter` | same, pointing at the stored `out.json` phase entry | `.../run.json#/adapter_phases/witness` |
| `derivation` | formula id from the RFC-0004 registry, `derive:<id>@<harness version>`; `inputs` lists a repo-relative path plus JSON Pointer for every input quantity, in formula argument order | `derive:D-RATE-S@0.1.0` |
| `upstream` | URL containing a full 40-hex commit hash or an immutable URL | `https://github.com/sg-ai-safety-hub/zk-inference-results/blob/11decec3c0b62c707618aab5deb82750b355d202/constants.json` |
| `reference_file` | repo-relative path plus JSON Pointer into the YAML as parsed | `reference/v0.1.yaml#/cost/price_per_gpu_hour_usd` |

#### Invariants

- **INV-QTY-1** A quantity has all seven required keys; no key is omitted, including `scope` and `null_reason`, which are present as `null` when they do not apply.
- **INV-QTY-2** `value` is null if and only if `null_reason` is a non-null member of its enum.
- **INV-QTY-3** If `unit` is one of `s`, `ns`, `token/s`, `s/token`, `USD`, `USD/1k_token`, `param_token/s`, `s/bit_token`, then `scope` is non-null. If `unit` is `ratio` and the quantity is derived from one or more scoped quantities, `scope` is non-null and equals the scope of the rate in its denominator; this second half is checked by [RFC-0013 §G5](0013-validation-and-ci.md#g5-label-check), not by the schema, because it needs the derivation graph.
- **INV-QTY-4** In a `run.json` or `controls.json`, `tier` is `reported`. Effective tiers appear only in `releases/<release>/index.json` (RFC-0009).
- **INV-QTY-5** `grade: external` implies `source.kind: upstream`, `upstream_scope` and `mapping` present, and `source.ref` contains a 40-hex commit hash or an immutable archive URL (RFC-0014 §Pin rules).
- **INV-QTY-6** `grade: derived` implies `source.kind: derivation`, a non-empty `source.inputs`, and that the formula id exists in the harness's formula registry at the named version.
- **INV-QTY-6a** The tier of a derived quantity is the lowest tier among its inputs, in the order `reported` < `peer-reviewed` < `reproduced` (RFC-0004). In `run.json` this is always `reported`; in a release index it is computed per input.
- **INV-QTY-7** `grade: measured` implies `source.kind` is `harness` or `adapter`.
- **INV-QTY-8** A statistic satisfies `stats.n >= 0`, `stats.n_failed >= 0`, `value == stats.mean`, and `stats.stdev` is null when `stats.n < 2`. When `stats.n == 0`, `value` is null with `null_reason: step_failed`.
- **INV-QTY-9** `quality` appears only on `measured` and `derived` quantities. The harness sets it on measured quantities; a derived quantity carries `quality.degraded` and `quality.precision_substituted` equal to the logical OR over its inputs, so a flag cannot be lost through a formula. G5 checks the OR.

### YAML subset for authored files

Authored files are parsed with `yaml.safe_load` (PyYAML 6, a YAML 1.1 parser). To avoid YAML 1.1 surprises, authored files MUST follow these rules, which the schemas enforce by type:

1. Dates and timestamps are quoted strings (`"2026-11-03"`). The schemas type them as `{"type": "string", "format": "date"}` with format assertion on. An unquoted date parses to `datetime.date`, which is not a JSON type; the loader raises `ErrorKind.config` with `<path>: <pointer>: unquoted date, write "YYYY-MM-DD"`.
2. Booleans are only `true` and `false`. Any string field that could read as a YAML 1.1 boolean (`yes`, `no`, `on`, `off`, `y`, `n`) MUST be quoted; the schema catches the type mismatch when it is not.
3. Commit hashes and digests are quoted strings. An all-digit abbreviated hash would otherwise parse as an integer; full 40-hex hashes are required anyway (RFC-0014).
4. No anchors, aliases or merge keys (`&`, `*`, `<<`). The loader rejects any document whose parse events contain an alias, with `ErrorKind.config`.
5. One document per file (no `---` separators after the first).
6. UTF-8, LF line endings, no byte-order mark.

After parsing, the loader converts the tree to plain JSON types (dict, list, str, int, float, bool, None) and fails on anything else. Validation then runs on that tree.

### JSON writer

`iproofs.serialize.write_json(path: Path, obj: Mapping[str, object]) -> str` is the only function that writes generated JSON. It returns the `sha256:` digest of the bytes written.

```python
def dumps(obj: Mapping[str, object]) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")
```

Rules:

- Writes go to `<path>.tmp-<pid>` then `os.replace` onto `path`, so a crash never leaves a half-written record.
- `allow_nan=False` means NaN and infinities raise `ValueError`, which the caller maps to `ErrorKind.internal`. Code that could produce a non-finite value (division by zero in a derived metric) MUST produce `value: null` with a `null_reason` before reaching the writer.
- Python's `json` emits floats with `repr`, the shortest decimal string that round-trips to the same binary64. Integers are emitted as integers. A field typed `number` may hold either; readers MUST NOT rely on the integer or float form.
- Adapters write `out.json` with any writer. The harness re-reads it, validates it, and stores it in the run record only through `write_json`, so stored copies are canonical.

The format check in [RFC-0013 §G3](0013-validation-and-ci.md#g3-json-format-check) asserts every committed JSON file equals `dumps(json.loads(file_bytes))` byte for byte.

### Digests

All digests are SHA-256, written `sha256:` followed by 64 lowercase hex characters, matching `^sha256:[0-9a-f]{64}$`.

| Digest | Exact input bytes |
|---|---|
| File digest | the file's bytes as stored |
| Model digest | concatenation, over every weight, tokenizer and config file of the model revision sorted by the UTF-8 bytes of its path relative to the model root, of `<relative_path>` + `\t` + `<64 hex of the file digest>` + `\n`. Paths use `/` separators and no leading `./` |
| Proof digest | the same construction over the part files of `/io/proofs/<proof_id>/`, with `<part_name>` (the file name) in place of the path |
| Prompt set digest | file digest of the materialised prompt file `prompts.jsonl` written by `write_jsonl`, one JSON object per line, keys sorted, no indentation, `ensure_ascii=False`, LF after every line including the last |
| Corpus digest | the model-digest construction over the corpus files listed in `corpus.yaml`, using each entry's `id` as the path |
| Record digest | file digest of a JSON file written by `write_json` |
| Image digest | the OCI manifest digest reported by the registry or by `docker buildx` for a local build; recorded, never recomputed by the harness |

Sorting is by raw bytes (Python `sorted(paths, key=lambda p: p.encode("utf-8"))`), never by locale. Symlinks inside a model or proof directory are rejected with `ErrorKind.integrity`, because their targets are outside the hashed set. Empty files are hashed like any other file. Directories other than the root are represented only through the paths of the files inside them; an empty subdirectory does not affect the digest.

### Identifiers

| Identifier | Pattern | Notes |
|---|---|---|
| system | `^[a-z][a-z0-9-]{1,31}$` | `sash`, `flashprove`, `fake`, `fake-broken`, `ref-serve`, `ref-recompute` |
| configuration | `^[a-z0-9][a-z0-9-]{0,47}$` | claim card file stem under `systems/<name>/claims/` |
| workload id | `^[a-z0-9][a-z0-9-]{2,63}$` | plus integer `version >= 1` |
| profile | `^[a-z0-9][a-z0-9-]{2,31}$` | `prover-h100`, `verifier-cpu` |
| release | `^v\d+\.\d+$` | `v0.1` |
| run-id | `^\d{4}-\d{2}-\d{2}-<system>-<workload>-<profile>-[1-9][0-9]*$` | the components are also stored as separate fields in `run.json`; parsers MUST use the fields, not split the string, because ids contain hyphens |
| proof id | `^[a-z0-9][a-z0-9._-]{0,127}$` | chosen by the adapter; must be a single path component |
| control id | `^(C[1-8]|P[1-2]|[a-z0-9-]{3,64})$` | lowercase ids, unique per system, for system-specific controls (RFC-0008) |

The run-id date is the UTC date of the job's start. `n` is the smallest positive integer such that the directory does not exist yet; the harness creates the directory with `os.mkdir` (atomic, fails if it exists) and retries with `n+1`, so concurrent runners on one checkout cannot collide.

### Python loading

`iproofs.schema` exposes:

```python
class SchemaRegistry:
    @classmethod
    def from_tree(cls, root: Path) -> "SchemaRegistry": ...
    def validator(self, schema_id: str) -> jsonschema.protocols.Validator: ...

def load_document(path: Path, registry: SchemaRegistry) -> tuple[str, dict[str, object]]:
    """Parse YAML or JSON by extension, check plain JSON types, read `schema`,
    validate, return (schema_id, tree). Raises IProofsError(kind=config) with every
    validation error, sorted by JSON Pointer."""
```

`iproofs.model` holds one frozen dataclass per schema, `@dataclass(frozen=True, slots=True)`, with a `from_tree(tree) -> Self` constructor that runs only on validated trees. Nested objects become nested dataclasses; arrays become tuples; open maps become `Mapping[str, ...]` wrapped in `types.MappingProxyType`. No constructor accepts an unvalidated tree in production code; tests may build dataclasses directly.

Validation uses `jsonschema.Draft202012Validator` with `format_checker=Draft202012Validator.FORMAT_CHECKER` and a `referencing.Registry` built from the local tree. Formats asserted: `date`, `date-time`, `uri`. `uri` is checked syntactically only.

**Drift test.** `harness/tests/unit/test_model_drift.py` walks every schema, resolves `$ref`s, and for each object schema asserts that the set of property names equals the set of dataclass field names of the corresponding model class, and that required properties map to fields without defaults. A schema change without a model change, or the reverse, fails CI.

### Floats and bit-exact recompute

- All arithmetic on stored numbers uses Python `float` (IEEE 754 binary64, round to nearest even), which CPython guarantees on every supported platform.
- Sums use `math.fsum` (exactly rounded, order independent). Means use `statistics.mean` (RFC-0004 INV-DERIVE-5); sample standard deviation uses `statistics.stdev`. Both are deterministic for a given input list. Inputs are ordered by repetition number before any computation, so the input list is the same everywhere.
- Integers that count bytes, tokens or nanoseconds are stored as JSON integers and converted to `float` only at the point of division. Nanosecond durations up to 2^53 ns (about 104 days) convert exactly.
- Derived values are stored unrounded. `iproofs derive --check` recomputes from the stored raw values and compares with `==`. There is no tolerance. A mismatch means the stored value did not come from this formula on these inputs.
- Display rounding is defined per unit in the site templates (RFC-0009 §Site) and never written back to a record.

### Failure modes

| Failure | Detection | Response |
|---|---|---|
| Document names an unknown schema major | `load_document` | `ErrorKind.config`, file named, CLI exit 1 |
| Authored YAML has an unquoted date or alias | loader type check | `ErrorKind.config` with JSON Pointer and fix hint |
| Generated value is NaN or infinite | `write_json` raises | `ErrorKind.internal`, exit 5; the step that produced it is reported as a bug |
| Two hosts compute different model digests | digest mismatch against `workload.model.digest` | `ErrorKind.integrity`, job stops before any container sees the weights |
| Symlink inside a hashed tree | digest function | `ErrorKind.integrity` |
| Schema edited without model edit | drift test | CI fails |
| Stored derived value differs from recompute | `derive --check` | CI fails with formula id, inputs and both values printed with `repr` |
| Concurrent runners pick the same run-id | `os.mkdir` fails | retry with next `n` |

## Alternatives Considered

**Pydantic models as the source of truth, JSON Schema exported.** Considered because it gives typed Python models and validation in one library, and most Python ML projects use it. Rejected because the schemas are the normative interface for adapters and readers in other languages; an exported schema changes whenever the library's export logic changes, so a library upgrade could change a normative artifact. Hand-written schemas plus a drift test keep the normative text stable and the Python side typed.

**RFC 8785 JSON Canonicalization Scheme for all JSON.** Considered because it is a standard canonical form. Rejected for v0.1 because its number serialisation follows ECMAScript rules, which differ from Python `repr` for some exponents, so a pure-stdlib implementation would need a custom float formatter; and we do not need canonical form across writers, only that our one writer is deterministic. The JSON format check gives the same guarantee for files we write. If documents are ever signed by third-party tools (RFC-0014 open question), JCS is the first candidate.

**A tolerance in the recompute check (for example relative 1e-12).** Considered because floating point is often treated as inexact. Rejected because the computation path is fixed and deterministic; a tolerance would accept a hand-edited value that is close but not computed, which is exactly what AGENTS.md rule 3 forbids.

**Decimal or rational arithmetic for derived values.** Considered for exactness. Rejected because inputs are measured binary64 values anyway, `Decimal` context settings add another thing to pin, and binary64 with `fsum` is exact enough for every v0.1 metric and bit-reproducible.

**Strict YAML 1.2 parser (ruamel.yaml) instead of PyYAML plus rules.** Considered because it removes the YAML 1.1 boolean and date traps at parse time. Rejected because schema validation already catches those traps as type errors with a clear message, and PyYAML is the smaller, more widely packaged dependency. Revisit if contributors repeatedly hit the rules.

**Bare numbers plus a sidecar labels table.** Considered because it keeps result files compact. Rejected because a number separated from its labels is the failure this project exists to prevent; one object per number makes the label check a schema check.

**Semantic versioning with minor numbers for schemas (`run/1.2`).** Considered for finer change tracking. Rejected because readers only need to know whether they can read a file; additive changes do not affect that, so a minor number adds bookkeeping without changing any decision.

## Drawbacks

- Result files are verbose: every number carries seven keys. A run with 60 quantities is about 30 KiB of JSON. Acceptable at the expected volume (hundreds of runs per release).
- Hand-written schemas are more work than generated ones, and the drift test only checks property names and required-ness, not types.
- Closed enums mean every new unit or scope needs at least an additive schema edit, and old readers reject documents using it.
- PyYAML plus rules relies on schemas catching type traps; a field typed as a free string will accept `"no"` when an author meant `false`. Fields where that matters are typed boolean.

## Conflicts of Interest

The author's affiliations and any interest in a measured system are declared in `MAINTAINERS.md` before this RFC enters Last call (RFC-0001).

## Migration / Rollout

No results exist yet, so there is nothing to migrate. Rollout order:

1. Land `schema/quantity/1.schema.json` with examples and the serialisation module (`iproofs.serialize`), with tests.
2. Land every other schema at major 1, each with valid and invalid examples, together with its dataclass and the drift test.
3. Turn on gates G2 and G3 of RFC-0013 as required checks.

The amendment of 2026-11-08 adds the unit `s/bit_token` (seconds per bit of active weights per token covered, [RFC-0004](0004-metrics-timing-grades.md#derived-metric-catalogue) D-SPAB-S) to the unit enum and to the INV-QTY-3 list, and the optional `precision.weight_bits` object to `workload/1` ([RFC-0003 §Weight bits](0003-workloads.md#weight-bits)). Both are additive: every document valid before stays valid, so neither schema changes major.

The existing draft claim card example in the old `docs/SPEC.md` uses `reviewed_by_maintainers` and `security.bits`; RFC-0002's field names (`reviewed_by`, `security.level`) win, and `claim/1` follows RFC-0002.

## Testing Strategy

Unit tests in `harness/tests/unit/`:

- `test_serialize.py::test_dumps_sorted_indented_lf` asserts exact bytes for a fixed object with nested keys, non-ASCII text and a float `0.1`.
- `test_serialize.py::test_nan_rejected` and `test_inf_rejected` assert `ValueError`.
- `test_serialize.py::test_atomic_write_leaves_no_partial` simulates a crash between write and replace and asserts the target is absent or old.
- `test_digest.py::test_model_digest_known_vector` hashes a fixture tree (`a/b.bin` = `b"x"`, `a.bin` = empty, `z` = `b"\n"`) and compares against a digest computed independently with `sha256sum` and `printf` in the test docstring.
- `test_digest.py::test_sort_is_bytewise` uses paths `B`, `a`, `é` and asserts the order `B`, `a`, `é`.
- `test_digest.py::test_symlink_rejected`.
- `test_yaml.py::test_unquoted_date_rejected`, `test_alias_rejected`, `test_norway_no_caught_by_schema` (a claim card with `availability: no` fails validation).
- `test_quantity.py` one test per invariant INV-QTY-1 to INV-QTY-9 (including INV-QTY-6a: a derived quantity over one `reproduced` and one `reported` input is `reported`), each with a minimal violating document.
- `test_ids.py::test_run_id_allocation_concurrent` runs two processes allocating ids in one directory and asserts distinct ids.
- `test_model_drift.py` as described above.

Property tests in `harness/tests/property/` (Hypothesis):

- `test_roundtrip`: for any JSON-typed tree of finite floats, ints, strings and nested dicts or lists, `dumps(json.loads(dumps(x))) == dumps(x)`.
- `test_digest_order_independent`: the model digest of a tree does not depend on the order files are created on disk.
- `test_fsum_order_independent`: `math.fsum` of any permutation of a list of finite floats is equal, which the derivation code relies on.

Schema example tests: every file in `examples/valid/` validates; every file in `examples/invalid/` fails, and the error path or keyword contains the text in its `.reason` file.

## Open Questions

- OPEN QUESTION Q1 (owner: AbdelStark, resolve by: RFC-0001 decision on the permanent home, target 2027-03-31): the host used in `$id`. Default until resolved: `https://inference-proofs.org/` as a placeholder that is never dereferenced. Changing it is an editorial change to every schema, because validators resolve locally.
- OPEN QUESTION Q2 (owner: AbdelStark, resolve by: 2026-12-01): whether the drift test should also compare JSON types against dataclass annotations. Default: names and required-ness only; type comparison is added if a type drift bug is found.

## References

- JSON Schema Draft 2020-12, https://json-schema.org/draft/2020-12
- RFC 2119, key words for requirement levels.
- RFC 8785, JSON Canonicalization Scheme (considered, not adopted).
- RFC 3339, date and time on the internet.
- Python documentation, `json`, `math.fsum`, `statistics`, and the `random` reproducibility guarantee.
- [RFC-0004](0004-metrics-timing-grades.md), [RFC-0007](0007-evidence-tiers-and-reproduction.md), [RFC-0009](0009-results-and-publication.md), [RFC-0013](0013-validation-and-ci.md), [RFC-0014](0014-provenance-and-integrity.md).
