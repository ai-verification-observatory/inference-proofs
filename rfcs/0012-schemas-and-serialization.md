# RFC-0012: Artifact schemas, labelled quantities and serialization

- Authors: AbdelStark
- Created: 2026-11-03
- Requires: RFC-0001, RFC-0004

## Summary

This RFC defines the format and envelope of every file the benchmark reads or writes. It covers the schema catalogue, the top-level `schema` identifier required in every document, schema versioning rules, the labelled quantity structure used for all benchmark numbers, the YAML subset permitted for hand-authored files, the single canonical JSON writer for generated outputs, byte-level digest definitions, identifier syntax, and how the Python harness loads and validates documents. Every other RFC that references a file relies on a schema defined here. Together, these rules ensure that two operators running the same job produce byte-identical records and that CI can recompute every derived figure and verify bit-for-bit equality.

## Motivation

AGENTS.md rule 2 requires that no published number appear without its timing scope, grade, evidence tier, and source. Enforcing that mechanically requires representing every number as a typed object rather than a bare float inside a table. [RFC-0004 §Grades](0004-metrics-timing-grades.md#vocabularies) defines the grade vocabulary and [RFC-0007 §Tiers](0007-evidence-tiers-and-reproduction.md#tiers) defines evidence tiers; this RFC provides the data container that binds them to every value.

The initial specification named five document kinds (claim card, workload, system manifest, run result, and control verdicts) and called for JSON Schemas in `schema/`, but left out schema evolution, numeric encoding, digest definitions, and version discovery. Without those conventions:

- Readers could not distinguish a result written by harness 0.2 from one written by harness 0.1, risking silent misinterpretation of renamed fields.
- Running `iproofs derive` on two different machines might serialise `0.30000000000000004` versus `0.3` for the same ratio, forcing CI ([RFC-0013](0013-validation-and-ci.md)) either to fail spuriously or to introduce tolerances that mask genuine errors.
- Sorting file paths using the host's locale would yield different model digests on different machines.
- YAML 1.1 parsers silently coerce unquoted `no` into `false` and `2026-11-03` into a date object, subtly altering hand-authored claim cards.

## Goals

- Validate every document read or written by the benchmark against exactly one schema identified inside the document itself.
- Represent every benchmark number as a labelled quantity satisfying invariants INV-QTY-1 through INV-QTY-7.
- Make generated JSON byte-deterministic so identical in-memory objects always serialise to identical bytes across supported platforms.
- Define all digests down to exact byte sequences so any implementation in any language reproduces them.
- Guarantee exact `==` binary64 equality when recomputing derived numbers from stored raw values.
- Give contributors a clear, mechanical rule for deciding whether a schema edit requires a new major version.

## Non-Goals

- Defining the semantics of individual metrics, timing scopes, or grades (owned by [RFC-0004](0004-metrics-timing-grades.md)).
- Defining domain-specific document rules, such as required claim card fields or negative control algorithms (owned by the respective RFCs in the catalogue); this RFC governs encoding and envelopes only.
- Cryptographic signing or attestation of documents ([RFC-0014](0014-provenance-and-integrity.md#decisions) Q1).
- Designing a general-purpose interchange format for external projects.

## Proposed Design

### Schema catalogue

All schemas use JSON Schema Draft 2020-12 and live at `schema/<name>/<major>.schema.json` with `$id` set to `https://inference-proofs.org/schema/<name>/<major>.schema.json`. That hostname is never dereferenced ([Q1](#decisions)); validators MUST resolve `$id` and `$ref` strictly from the local `schema/` directory and MUST NOT perform network requests.

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
| `controls-part` | `schema/controls-part/1.schema.json` | generated JSON | `<run-dir>/controls-part-<seed>-<subset>.json`, a working file never committed under `results/` | RFC-0008 §Split suites |
| `controls-seed` | `schema/controls-seed/1.schema.json` | generated JSON | `<run-dir>/controls-seed.json`, written once before the first part, never committed under `results/` | RFC-0008 §Split suites |
| `perturbed-commitment` | `schema/perturbed-commitment/1.schema.json` | generated JSON | `results/<release>/<system>/_controls/<workload>/perturbed.json` | RFC-0008 |
| `verifier-trial` | `schema/verifier-trial/1.schema.json` | generated JSON | `results/<release>/<system>/_trials/<trial id>/trial.json` | RFC-0008 §Verifier trials (amended 2026-11-15) |
| `setup` | `schema/setup/1.schema.json` | generated JSON | `<results>/<release>/<system>/_setups/<setup id>/setup.json`, beside the `state.tar` it names (development runs) | this RFC, amendment of 2026-11-26 (setup records) |
| `refusal` | `schema/refusal/1.schema.json` | authored JSON | `results/<release>/<system>/refusals/slot-<k>.json` | RFC-0018 SE-5 (amended 2026-11-15) |
| `site-facts` | `schema/site-facts/1.schema.json` | authored JSON | `web/_data/facts.json` | RFC-0009 |
| `criteria` | `schema/criteria/1.schema.json` | authored JSON | `web/_data/criteria.json` (deleted 2026-11-15 because it used RFC-0016's vocabulary, such as Formally verified "yes" from documents, which no page reads; the v0.1 version remains in git history at `b9dfa3e`) | RFC-0016 |

`external/1` stores upstream figures per system as `grade: external` quantities, and `system-controls/1` registers system-specific controls; both reuse `$defs` from `quantity/1`. Every claim card carries an integer `card_version`, starting at 1 and incrementing with every merged edit. Systems with multiple statement-changing configurations store one claim card per configuration under `systems/<name>/claims/` (RFC-0002).

Each schema directory also contains `examples/valid/` and `examples/invalid/`. Every invalid example is paired with a sibling `<file>.reason` text file specifying the invariant or schema keyword it violates, verified automatically by [RFC-0013 §G2](0013-validation-and-ci.md#g2-schema-validation).

### The `schema` field

Every document carries a top-level string field `schema` formatted as `<name>/<major>` (`^[a-z][a-z-]*/[1-9][0-9]*$`). The validator inspects this field first to locate `schema/<name>/<major>.schema.json`. Missing or unrecognised schema identifiers fail with `ErrorKind.config` and the message `<path>: missing or unknown schema "<value>"`.

Each schema pins its own `schema` field using `"const": "<name>/<major>"`, preventing accidental validation against the wrong schema file.

### Schema versioning

Schema changes are classified by applying the rules below in order (the first match wins):

| Change | Classification |
|---|---|
| Removing or renaming a property, changing a type, narrowing an enum, adding a `required` field, tightening a pattern or bound, or changing a value's meaning | Major: create `<major+1>.schema.json` and update the owning RFC |
| Adding an optional property, widening an enum, relaxing a pattern or bound, or adding a `$defs` entry | Additive: edit the current schema in place with a CHANGELOG entry (no RFC needed) |
| Editing `description` or `examples` only | Editorial: no CHANGELOG entry needed |

Although widening a closed enum causes older readers to reject new enum values, this is intentional: older readers are not required to parse newer documents. Newer readers, however, MUST support documents written under both the current and previous major versions (a one-release reading window; see [docs/spec/09-release-and-versioning.md](../docs/spec/09-release-and-versioning.md#schema-majors)).

Previous major schema files remain untouched in the repository. Because results are append-only ([RFC-0009 §Storage](0009-results-and-publication.md#storage)), existing documents are never rewritten in place to a newer major; any necessary migration writes a new document referencing the one it replaces.

Every schema sets `"additionalProperties": false` at every object level except where an object is explicitly documented as an open map (such as `phases` in `adapter-out`, keyed by adapter-chosen phase names). Typos in field names therefore fail validation immediately instead of being silently ignored.

### Labelled quantity

Defined under `$defs/quantity` in `schema/quantity/1.schema.json`, this object wraps every measurement, derivation, projection, external figure, or asserted input inside `run`, `controls`, `release-index`, `external`, and `reference` documents. Structural integers that are not measurements (such as `batch_size` in a workload shape or `n` inside `stats`) remain plain integers.

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
                          "B/token", "B/bit_token", "USD", "USD/1k_token", "USD/gpu_hour", "%",
                          "param_token/s", "s/bit_token", "bit/weight", "ratio"]},
        "scope": {"enum": [null, "setup", "commit", "prove.steady", "prove.session",
                           "whole_wall", "verify", "verify.single_thread", "primitive"]},
        "grade": {"enum": ["measured", "derived", "projected", "external", "asserted"]},
        "tier": {"enum": ["reported", "peer-reviewed", "reproduced"]},
        "source": {"$ref": "#/$defs/source"},
        "null_reason": {"enum": [null, "not_externally_observable", "fewer_than_two_proofs",
                                 "not_applicable", "step_failed", "not_measurable_on_profile",
                                 "missing_input", "setup_reused"]},
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

The snippet above is simplified for readability. Because `additionalProperties: false` cannot see properties declared inside a sibling `allOf`, the actual published schema factors the shared properties and `allOf` rules into `$defs/quantityCore` (without `additionalProperties`) and defines:

```json
"quantity":  {"$ref": "#/$defs/quantityCore", "unevaluatedProperties": false},
"statistic": {"$ref": "#/$defs/quantityCore", "required": ["stats"],
              "properties": {"stats": {"$ref": "#/$defs/stats"}},
              "unevaluatedProperties": false}
```

The invalid schema examples MUST include both a `statistic` carrying an unknown key and a plain `quantity` carrying `stats`, and validation MUST reject both.

Optional fields serve specific roles: `upstream_scope` records the scope label used by an upstream source; `mapping` states how closely that upstream scope matches this project's scope (`exact`, `approximate`, or `none`; RFC-0004 §Timing scopes); `upstream_grade` preserves an upstream source's own grade where published (for example SASH's `constants.json` grades); `quality.degraded` flags metrics whose sampler exceeded RFC-0011's gap threshold; `quality.precision_substituted` flags reference rows that ran at the nearest supported precision rather than the workload's precision (RFC-0015); and `note` holds a single explanatory sentence rendered on the site.

The expected format of `source.ref` depends on `source.kind`:

| `kind` | `ref` form | Example |
|---|---|---|
| `harness` | Repo-relative path plus JSON Pointer to the raw measurement | `results/v0.1/fake/2026-11-20-fake-fake-tiny-ci-ci-cpu-1/run.json#/raw/prove/wall_ns` |
| `adapter` | Repo-relative path plus JSON Pointer to the phase's own entry in `run.json`; the adapter's `out.json` is not kept, so the value is as the accepted output reported it (INV-GRADE-2) | `.../run.json#/adapter_phases/commit/witness` |
| `derivation` | Formula id from RFC-0004 as `derive:<id>@<harness version>`; `inputs` lists a repo-relative path plus JSON Pointer for each input quantity in argument order | `derive:D-RATE-S@0.1.0` |
| `upstream` | URL containing a full 40-hex commit hash or an immutable archive URL | `https://github.com/sg-ai-safety-hub/zk-inference-results/blob/11decec3c0b62c707618aab5deb82750b355d202/constants.json` |
| `reference_file` | Repo-relative path plus JSON Pointer into parsed YAML (either a reference file or the workload record from which a `run.json` `inputs` quantity was copied, RFC-0003 WB-4) | `reference/v0.1.yaml#/cost/price_per_gpu_hour_usd`, `workloads/sash-l31-8b-c1024.yaml#/precision/weight_bits` |

#### Invariants

- **INV-QTY-1**: Every quantity includes all seven required keys; even when `scope` or `null_reason` does not apply, it must be present with value `null`.
- **INV-QTY-2**: `value` is `null` if and only if `null_reason` is a non-null enum member.
- **INV-QTY-3**: Whenever `unit` is `s`, `ns`, `token/s`, `s/token`, `USD`, `USD/1k_token`, `param_token/s`, or `s/bit_token`, `scope` must be non-null. If `unit` is `ratio` and the quantity derives from one or more scoped quantities, `scope` must be non-null and match the denominator rate's scope; this second clause is enforced by [RFC-0013 §G5](0013-validation-and-ci.md#g5-label-check) rather than JSON Schema because it requires walking the derivation graph.
- **INV-QTY-4**: Every quantity inside `run.json` or `controls.json` has tier `reported`.
- **INV-QTY-5**: `grade: external` requires `source.kind: upstream`, both `upstream_scope` and `mapping`, and a `source.ref` containing a 40-hex commit hash or immutable archive URL (RFC-0014 §Pin rules).
- **INV-QTY-6**: `grade: derived` requires `source.kind: derivation`, a non-empty `source.inputs`, and a formula id registered in the harness at the stated version.
- **INV-QTY-6a**: A derived quantity inherits the lowest tier among its inputs in the ordering `reported` < `peer-reviewed` < `reproduced` (RFC-0004). All recorded tiers are currently `reported` (RFC-0007).
- **INV-QTY-7**: `grade: measured` requires `source.kind` to be either `harness` or `adapter`.
- **INV-QTY-8**: Every statistic satisfies `stats.n >= 0`, `stats.n_failed >= 0`, `value == stats.mean`, and `stats.stdev == null` whenever `stats.n < 2`. When `stats.n == 0`, `value` is `null` with `null_reason: step_failed`.
- **INV-QTY-9**: `quality` is permitted only on `measured` and `derived` quantities. The harness sets quality flags on measured quantities, and derived quantities compute `quality.degraded` and `quality.precision_substituted` as the logical OR over their inputs so quality warnings cannot disappear through a formula. Gate G5 verifies the OR propagation.

### YAML subset for authored files

Hand-authored files are loaded via `yaml.safe_load` (PyYAML 6, which implements YAML 1.1). To eliminate YAML 1.1 type pitfalls, authored files MUST obey six rules enforced by the loader and schemas:

1. Quote all dates and timestamps (for example `"2026-11-03"`). Schemas type them as `{"type": "string", "format": "date"}` with format assertion enabled. Unquoted dates parse into `datetime.date`, which fails JSON type validation with `ErrorKind.config` and `<path>: <pointer>: unquoted date, write "YYYY-MM-DD"`.
2. Write booleans strictly as `true` or `false`. Any string value that YAML 1.1 interprets as a boolean (`yes`, `no`, `on`, `off`, `y`, `n`) MUST be quoted; otherwise schema validation catches the type mismatch.
3. Quote commit hashes and digests so an all-digit hash cannot parse as an integer (and use full 40-hex hashes per RFC-0014).
4. Do not use YAML anchors, aliases, or merge keys (`&`, `*`, `<<`). The loader inspects parse events and rejects any alias with `ErrorKind.config`.
5. Keep one YAML document per file (no subsequent `---` document separators).
6. Encode files as UTF-8 with LF line endings and no byte-order mark.

After parsing, the loader verifies that the tree contains only plain JSON types (`dict`, `list`, `str`, `int`, `float`, `bool`, `None`) before running JSON Schema validation.

### JSON writer

`iproofs.serialize.write_json(path: Path, obj: Mapping[str, object]) -> str` is the sole function permitted to write generated JSON files. It returns the `sha256:` digest of the written bytes.

```python
def dumps(obj: Mapping[str, object]) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")
```

Rules:

- Every write goes to `<path>.tmp-<pid>` first and moves into place via `os.replace`, ensuring crashes never leave truncated files.
- `allow_nan=False` causes `NaN` and infinities to raise `ValueError`, which callers map to `ErrorKind.internal`. Any calculation that could divide by zero or yield a non-finite number MUST produce `value: null` with an appropriate `null_reason` before reaching the writer.
- Python's `json` module formats floats using `repr` (the shortest decimal string that round-trips back to the exact binary64 value) and emits integers as integers. Because JSON `number` fields may hold either form, readers MUST NOT depend on integer-versus-float representation.
- Adapters may write `/io/out.json` with any serializer, but the harness parses, validates, and rewrites it into the run record via `write_json` so every stored copy is canonical.

Gate G3 ([RFC-0013 §G3](0013-validation-and-ci.md#g3-json-format-check)) verifies that every committed JSON file equals `dumps(json.loads(file_bytes))` byte for byte.

### Digests

All digests use SHA-256 formatted as `sha256:` followed by 64 lowercase hexadecimal characters (`^sha256:[0-9a-f]{64}$`).

| Digest | Exact input bytes |
|---|---|
| File digest | The exact bytes of the file as stored |
| Model digest | Over every weight, tokenizer, and config file in the model revision, sorted by the UTF-8 bytes of its path relative to the model root, the concatenation of `<relative_path>` + `\t` + `<64 hex of the file digest>` + `\n` (using `/` separators and no leading `./`) |
| Proof digest | The same construction over the part files inside `/io/proofs/<proof_id>/`, using `<part_name>` (file name) in place of the relative path |
| Prompt set digest | File digest of the materialised `prompts.jsonl` produced by `write_jsonl`: one JSON object per line, sorted keys, no indentation, `ensure_ascii=False`, and trailing LF on every line including the last |
| Corpus digest | The model-digest construction over the files listed in `corpus.yaml`, using each entry's `id` as the path |
| Record digest | File digest of a JSON document written through `write_json` |
| Image digest | The OCI manifest digest reported by the registry or `docker buildx` for a local build (recorded as reported, never recomputed by the harness) |

Paths are always sorted by raw UTF-8 bytes (`sorted(paths, key=lambda p: p.encode("utf-8"))`), never by host locale. Symlinks inside model or proof directories trigger `ErrorKind.integrity` because their targets sit outside the hashed tree. Empty files are hashed like any other file. Subdirectories are represented solely via the paths of the files they contain, so an empty subdirectory has no effect on the digest.

### Identifiers

| Identifier | Pattern | Notes |
|---|---|---|
| system | `^[a-z][a-z0-9-]{1,31}$` | Examples: `sash`, `flashprove`, `fake`, `fake-broken`, `ref-serve`, `ref-recompute` |
| configuration | `^[a-z0-9][a-z0-9-]{0,47}$` | Claim card file stem under `systems/<name>/claims/` |
| workload id | `^[a-z0-9][a-z0-9-]{2,63}$` | Paired with integer `version >= 1` |
| profile | `^[a-z0-9][a-z0-9-]{2,31}$` | Examples: `prover-h100`, `verifier-cpu` |
| release | `^v\d+\.\d+$` | Example: `v0.1` |
| run-id | `^\d{4}-\d{2}-\d{2}-<system>-<workload>-<profile>-[1-9][0-9]*$` | Components are also stored individually in `run.json`; parsers MUST read those fields rather than splitting the string, since ids contain hyphens |
| proof id | `^[a-z0-9][a-z0-9._-]{0,127}$` | Chosen by the adapter; must be a single path segment |
| control id | `^(C[1-8]|P[1-2]|[a-z0-9-]{3,64})$` | Lowercase ids, unique per system, for system-specific controls (RFC-0008) |

The date prefix of a run id is the UTC date at job start. The trailing integer `n` is the smallest positive integer whose directory does not yet exist; the harness allocates it atomically via `os.mkdir` and increments `n` on collision so concurrent processes sharing a checkout cannot collide.

### Python loading

`iproofs.schema` exposes the core loading API:

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

`iproofs.model` defines a frozen dataclass (`@dataclass(frozen=True, slots=True)`) for every document that Python code accesses field by field: authored inputs (workload, corpus, system, system controls, claim card, reference file, serving record, release, and site facts) plus outputs returned by adapters or control preparation (`adapter-out/1`, `perturbed-commitment/1`). Each exposes a `from_tree(tree) -> Self` constructor that runs strictly on validated trees. Documents that the harness only writes or manipulates as generic dicts have no dataclass and are defined solely by their JSON Schema: `run/1`, `manifest/1`, `controls/1`, `controls-part/1`, `controls-seed/1`, `release-index/1`, `adapter-job/1`, `target/1`, `external/1`, and `criteria/1` (listed in `iproofs.model.TREES`; prior to 2026-11-10 each had an unused dataclass). Those tree-only documents are validated against their schema on both write and read. Within dataclasses, nested objects map to nested dataclasses, arrays map to tuples, and open maps map to `Mapping[str, ...]` wrapped in `types.MappingProxyType`. Production code never constructs a dataclass from an unvalidated tree, though unit tests may instantiate them directly.

Validation uses `jsonschema.Draft202012Validator` with `format_checker=Draft202012Validator.FORMAT_CHECKER` and a `referencing.Registry` populated strictly from the local `schema/` tree. Checked formats are `date`, `date-time`, and syntactic `uri`.

**Drift test.** `harness/tests/unit/test_model_drift.py` resolves all `$ref` links and checks that every schema paired with a model class has the exact same set of property names as the dataclass fields, with required properties mapping to fields without defaults. Editing a schema without updating its dataclass (or vice versa) breaks CI. Every document schema must appear in either the model table or `TREES`, never in both or neither.

### Floats and bit-exact recompute

- All floating-point math operates on Python `float` (IEEE 754 binary64, round-to-nearest-even), guaranteed by CPython across all supported platforms.
- Sums use `math.fsum` (exact rounding, invariant to input order). Means use `statistics.mean` (RFC-0004 INV-DERIVE-5) and sample standard deviations use `statistics.stdev`. Inputs are sorted by repetition number before aggregation so every machine evaluates the identical sequence.
- Integer counts of bytes, tokens, or nanoseconds are stored as JSON integers and converted to `float` only at division time. Nanosecond spans up to 2^53 ns (about 104 days) convert without precision loss.
- Derived metrics are stored without rounding. `iproofs derive --check` recomputes them from the stored raw values and checks exact `==` equality with zero tolerance: any mismatch means the stored number was not produced by that formula on those inputs.
- Display rounding is handled per unit in the site templates (RFC-0009 §Site) and is never written back into records.

### Failure modes

| Failure | Detection | Response |
|---|---|---|
| Document references an unknown schema major | `load_document` | `ErrorKind.config` naming the file, CLI exit 1 |
| Authored YAML contains an unquoted date or alias | Loader type check | `ErrorKind.config` with JSON Pointer and fix suggestion |
| Generated value is NaN or infinite | `write_json` raises `ValueError` | `ErrorKind.internal`, exit 5; reported as a harness bug |
| Two hosts obtain different model digests | Digest mismatch against `workload.model.digest` | `ErrorKind.integrity`; job aborts before any container sees weights |
| Symlink inside a hashed directory | Digest helper | `ErrorKind.integrity` |
| Schema updated without updating its dataclass | Drift test | CI fails |
| Stored derived value differs from recomputed value | `derive --check` | CI fails, printing formula id, input pointers, and both `repr` values |
| Concurrent runners try to claim the same run id | `os.mkdir` fails | Retry with `n + 1` |

## Alternatives Considered

**Generate JSON Schemas from Pydantic models.** Having one Python definition for both models and schemas is convenient, but here the JSON Schemas are the normative contract for adapters and tools in other languages. Exporting schemas from a Python library ties the normative artifacts to that library's release behaviour. Hand-written schemas coupled with an automated drift test keep the contract stable while keeping Python code strictly typed.

**Use RFC 8785 JSON Canonicalization Scheme (JCS) everywhere.** JCS is a standard canonicalisation spec, but its float formatting follows ECMAScript rules that differ from Python's `repr` at certain exponents, requiring a custom float formatter instead of stdlib `json`. Because we only need determinism from our single writer rather than cross-writer canonicalisation, Python's `json` plus gate G3 suffices for v0.1. If third-party signing is added later (RFC-0014 Q1), JCS is the primary candidate.

**Allow a floating-point tolerance (such as relative 1e-12) in `derive --check`.** Although floating-point comparisons often use tolerances, our derivation pipeline is completely deterministic; a tolerance would let hand-edited values slip past CI, violating AGENTS.md rule 3.

**Use `Decimal` or rational arithmetic for derived metrics.** Because the underlying measurements are already binary64 floats, `Decimal` would add context precision settings to pin without improving physical accuracy; binary64 paired with `math.fsum` is both accurate enough for v0.1 and bit-reproducible.

**Use a strict YAML 1.2 parser (`ruamel.yaml`) instead of PyYAML plus lint rules.** While YAML 1.2 avoids YAML 1.1 boolean and date quirks at parse time, our schemas already reject those quirks with clear error messages, and PyYAML is smaller and more widely packaged. We can revisit this if contributors trip over the YAML rules frequently.

**Store bare numbers with a separate sidecar label table.** Keeping numbers separate from their labels shrinks JSON size, but unlabelled numbers are the exact failure mode this benchmark is designed to eliminate. Embedding labels inside every quantity object lets JSON Schema enforce labelling directly.

**Include minor versions in schema identifiers (such as `run/1.2`).** Readers only care whether they can parse a document, and additive changes do not break compatibility, so tracking minor schema numbers adds bookkeeping without changing reader behaviour.

## Drawbacks

- Carrying seven keys on every number makes result files verbose (roughly 30 KiB of JSON for a run with 60 quantities), which is fine at our expected scale of hundreds of runs per release.
- Maintaining schemas by hand takes more effort than code generation, and the drift test verifies property names and required status rather than full type equivalence.
- Closed enums require an additive schema update for every new unit or scope, and older readers reject newer enum values.
- Using PyYAML with schema type checks still allows an unquoted `"no"` inside a free-text string field when an author intended `false`; any field where that distinction matters is typed as boolean.

## Migration / Rollout

Because no results existed when this RFC was drafted, initial rollout required no migration:

1. Land `schema/quantity/1.schema.json` with valid/invalid examples and `iproofs.serialize` with unit tests.
2. Land all remaining major-1 schemas with examples, corresponding dataclasses, and the drift test.
3. Enable RFC-0013 gates G2 and G3 as required checks.

Amendment of 2026-11-08: Adds the unit `s/bit_token` (seconds per active weight bit per covered token, [RFC-0004](0004-metrics-timing-grades.md#derived-metric-catalogue) D-SPAB-S) to the unit enum and INV-QTY-3, along with the optional `precision.weight_bits` object in `workload/1` ([RFC-0003 §Weight bits](0003-workloads.md#weight-bits)). Both changes are additive and keep schemas at major 1. Following review, the same amendment also adds: the unit `bit/weight` for asserted weight widths; `covers` and computed `file_size` width in `precision.weight_bits`; the optional `run/1` `inputs` object (`active_parameters_per_token` in `count` and `weight_bits` in `bit/weight`, both `asserted` quantities with `source.kind: reference_file` copied from the workload at run time, RFC-0003 WB-4), modelled by `RunInputs`; and the optional `release-index/1` `freeze_derived` map (keyed by run id and metric id for formulas evaluated at freeze time on older runs, RFC-0004 Q3). Every addition is optional or widens an enum, keeping all schemas at major 1 (`workload/1`'s `weight_bits` shape was adjusted before any release used it). A second amendment on 2026-11-08 (resolving RFC-0003 Q5) adds `computed` to `precision.weight_bits.basis` plus the optional `method` enum (`gguf-active-mean/1`), required specifically for `computed` alongside `bits`, `files`, and `covers: all` (RFC-0003 WB-5), and adds `method` to `WeightBits`; both remain additive on `workload/1`.

Where the old `docs/SPEC.md` claim card example used `reviewed_by_maintainers` and `security.bits`, RFC-0002's field names (`reviewed_by` and `security.level`) take precedence, and `claim/1` matches RFC-0002.

Amendment of 2026-11-09 (RFC-0015 SRV-6 production serving):
- Adds the new `serving-model/1` schema (`workloads/serving/<id>.yaml`) with valid and invalid examples.
- Extends `reference/1` with `kind: serving`, `pairs_with`, `shm_gib_min`, and `gpu.count > 1` (serving profiles only).
- Extends `system/1` for serve-role workload entries with `load_point`, `gpus`, `batch_size` (high load only), and `batches_per_session_run`; requires `precision_substitution: null` for `reference_role: serve`; restricts `engine_args` to the SRV-3 allowlist; and adds optional `engine.commit` (engine source commit, RFC-0015 Q1).
- Extends `manifest/1` with `workload.load_point`, `workload.batch_size_run`, `workload.batches_per_session_run`, `workload.prompt_count_run`, `workload.prompt_prefix_digest`, `workload.steady_rule` (RFC-0004 INV-SCOPE-5), `engine` (with optional `engine.observed` covering version, build commit, and batched-token limit per RFC-0015 SRV-3), and `serving_model`; adds `inputs.gpu_count` to `run/1`.
- Extends `quantity/1` with unit `gpu_s/token`, metric ids `gpu_seconds_per_token_<S>`, `overhead_vs_production_<S>`, and `overhead_vs_production_high_<S>` (replacing `overhead_vs_serving_<S>`), plus optional `pairs` (RFC-0004 INV-DERIVE-9).
- Extends `release-index/1` with optional per-configuration `overhead_conditions` (high-load settings, GPU count, profile, and engine batched-token limits, RFC-0004 INV-DERIVE-9), optional `steady_boundary` (RFC-0004 INV-SCOPE-5), and optional `overhead_headline` (`{metric, formula, scope, start_up}` with `metric` set to `overhead_vs_production_prove.steady` or `overhead_vs_production_prove.session`, RFC-0004 INV-DERIVE-10, with examples).

Amendment of 2026-11-09 (RFC-0004 INV-DERIVE-11 and RFC-0015 SRV-1). Because no frozen release index existed yet, the enum narrowings below affected no stored record:
- `quantity/1`: adds metric id `overhead_vs_production_warm` (D-OVERHEAD-WARM).
- `release-index/1`: requires `serving_scope` (`prove.steady`) on `overhead_headline`; restricts `formula` to `D-OVERHEAD-S` or `D-OVERHEAD-WARM`, `metric` to `overhead_vs_production_prove.steady` or `overhead_vs_production_warm`, and `start_up` to `excluded` or `prover_only` (removing `D-OVERHEAD-SESSION`, `overhead_vs_production_prove.session`, and `included`); sets `overhead_conditions.warm` to true when serving start-up is outside scope; updates the valid example to `warm-headline.json`.
- `manifest/1`: adds optional `workload.sizing_capture` (`const: true`) for matched sizing captures (RFC-0015 SRV-1), paired with an invalid example (`false`).

Amendment of 2026-11-13 (RFC-0018 §The glyph). Because no release was frozen and the single stored board was recomputed in the same commit, these updates affected no stored run record:
- `board/1` (updated in place): replaces the rung-counting petal with `machine_checked` in fourth position; makes `step` (string or null), `cause`, and `lowered_by` required on every petal; removes `run` from `basis`; adds `formal` to Machine-checked and `visible` to Weights hidden; adds optional boolean `reading` (defaulting to false when absent), set true whenever any fact read by the petal's decision carries a note. Under §Schema versioning these would normally constitute major changes, but they are applied in place (following the 2026-11-09 precedent) because `releases/v1.0` has no frozen `release.yaml` or `index.json` and `releases/v1.0/board.json` is an output regenerated outside `results/` by `iproofs release board` and checked byte-for-byte with `--check`, so no reader needs the old layout.
- `properties/2` (`schema/properties/2.schema.json`, new major): stores the quoted facts used to compute each statement petal without hand-typed states, steps, or reasons (RFC-0018 GL-1), adding `bound.batch`, `bound.program`, and `formal.toolchain`, and requiring non-empty `hiding.visible` whenever `hiding.visible_listed` is true. `properties/1` remains in the tree unchanged.
- `fidelity/1` (additive): adds optional `slots`, `steps`, and per-row `step_tests` (`$defs/step_test`) written by `iproofs fidelity score` (RFC-0018 §Faithful model).
- `proof-build/1` (new): records a single build of a publisher's machine-checked proof at `results/<release>/proof-build/<system>/proof-build.json` (RFC-0018 MC-4, MC-5), requiring a SHA-256 digest in `toolchain.image`.

Amendment of 2026-11-15 (RFC-0008 §Verifier trials): Adds `verifier-trial/1` (`results/<release>/<system>/_trials/<trial id>/trial.json`) for standalone verification trials on stored proofs outside any session control suite, with `gates` fixed to `nothing`, `program.patched` fixed to `false`, and all durations recorded as quantities. Affects no stored records.

Amendment of 2026-11-15 (RFC-0018 SE-3b, SE-5, SI-3, SI-4a, CO-7, MC-7, WH-6, FM-5). All additions are additive, and the stored board is recomputed in the same commit (RFC-0018 Q14), leaving stored run records untouched:
- `refusal/1` (new): records an intentional refusal of a Level 1 request by a system's own code at a named upstream commit (SE-5).
- `board/1`: adds per-row `ineligible_sessions` (SE-3b), `level_statement` (SI-4a), `session_commit_gpu_seconds_per_reply`, `session_proving_gpu_seconds_per_reply`, and `generation_gpu_seconds_per_reply_token` (CO-7); adds `trials` on each check (detailing inputs sent and refusals); adds `conclusion`, `ceiling`, and `scope_bounds` on Machine-checked's `formal`; adds `forms` and `visible_at_least` on Weights hidden; adds `engine` and `slots_cause` on rung `fidelity` parts; adds `interval_rule` and per-entry `percent_interval` on `teacher_forced`.
- `properties/2`: adds `level_statement.accept_is_model_reply` with `sources_read` (SI-4a); adds `verifiers` and Machine-checked `formal.conclusion` (MC-7) plus optional `bound` per scope-card property; adds `hiding.zk_kind`, `zk_model`, `zk_unit`, `forms`, and `visible_at_least` (WH-6); adds `verifier_inputs` for the Statement block (SI-3).
- `fidelity/1`: adds `slots_cause` (FM-5).
- `site-facts/1`: adds per-system `pin` (pull request run by a row, SI-3), `generation`, and per-reason `reason_source` (SI-4b).
- `claim/1`: unchanged; keeping Statement block fields in `properties/2` preserves the claim card digests recorded in v1.0 runs.

Amendment of 2026-11-16 (RFC-0018 Q37, GL-11, CO-8, SI-9). Additive, with the stored board recomputed in the same commit (RFC-0018 Q14):
- `quantity/1`: adds unit `token/gpu_s` (reply tokens per GPU-second) to the unit enum and INV-QTY-3.
- `board/1`: adds optional per-petal `next` (GL-11: next reachable step and required actions, null at Met) and optional per-row `session_reply_tokens_per_gpu_second` (CO-8).
- `board/1` (second 2026-11-16 amendment, RFC-0018 Q39): adds optional `reply_tokens_per_gpu_second` (CO-8) and `gpu_model` (from the serving run's manifest) to each rung's `baseline`.
- `properties/2`: adds optional top-level `number_format` (SI-9: weights and activations formats, each `integer`, `fixed_point`, `floating_point`, or `not_stated`, with quotes).
- `site-facts/1`: adds optional per-system `paper`, pointing to a paper file inside the publisher's repository at the row's pinned commit (the site build rejects links pointing to any other commit).

Amendment of 2026-11-16 (RFC-0018 MC-4a, GL-5, SI-3, Q42, Q43). Additive, with the stored board recomputed in the same commit (RFC-0018 Q14):
- `proof-build/1`: adds `stopped` to `status` (for builds halted by our infrastructure before reaching a verdict) alongside `stop` (`cause`: `timeout` or `signal`, plus `detail`), required when `status` is `stopped` and omitted otherwise. One record is stored: FlashProve's full check (`results/v1.0/proof-build/flashprove/proof-build.json`, status `built`).
- `board/1`: adds optional `build` inside Formally verified's `formal` (recording the file path, toolchain name and version, publisher command without our timeout wrapper, start time, duration in seconds, exit code, and status).

Amendment of 2026-11-17 (RFC-0018 Q44, GL-5, GL-11, SI-3). Additive, with the stored board recomputed in the same commit (RFC-0018 Q14):
- `board/1`: adds optional per-petal `to_met`, `sources`, `sources_count`, `read_facts` (each carrying `used`), `why`, and structured page facts (`bound`, `hiding`, `fidelity`, `trust`), plus optional `limits`, `said`, and `build.axioms` inside `formal`.
- `properties/2`: adds optional `plain`, `named`, `described`, and `check` on individual facts, plus optional `bound.after` (verified offline against its quote) and `formal.limits`.

Amendment of 2026-11-26 (RFC-0004 `adapter_phases.<step>.<name>`): `run/1` `adapter_phases` is keyed by step (`commit`, `prove`), then by the phase name the adapter reports, each an adapter-reported quantity in `s` at scope `primitive`. The runner had written the field empty since it was introduced, so every stored run holds `{}`, which stays valid; no stored record, board or page changes.

Amendment of 2026-11-26 (RFC-0018 Q55, CO-9). Additive; no stored record, board or page changes (v1.0's board is built by the whole-sessions rule and carries none of these fields):
- `board/1`: adds optional top-level `cost_rule` (`further-reply`) and, required on every row when it is present, `further_reply_gpu_seconds`, `further_reply_generation_gpu_seconds`, `further_reply_proving_gpu_seconds`, `further_reply_split`, `further_reply_multiple`, `further_reply_proving_multiple`, `further_reply_tokens_per_gpu_second`, `further_reply_usd_per_reply`, `one_time_gpu_seconds`, `one_time_usd`, `one_time_mark_replies`, `one_time_setups`, `proving_batch`, `prove_gpu_util_mean` and `prove_gpu_memory_peak`, and per counted session `further_reply`, `further_reply_generation` and `one_time`.

Amendment of 2026-11-26 (setup records, `iproofs.setups`). Additive; no stored run, board or page changes:
- `setup/1` (new): one setup run's record. The run calls info, setup and commit with no prompt (`prompts_file` is `null` and the kept adapter-job/1 inputs carry none), keeps the state commit left in `/io/state` as `state.tar` with its digest, and records the system pin, image, adapter commit, model digest, shape, commitment files, kernel store, each step's and phase's seconds, the whole wall and the GPU-seconds, each a labelled quantity.
- `run/1`: adds optional `setup`. It names the setup a session reused by its record digest and archive digest, the commitment it names (the one verified, AGENTS.md hard rule 6), and the restore's seconds, timed apart from the commit step.
- `adapter-job/1`: adds optional `setup_state` (`commitment_id`, optional `build_key`), on commit only: the values the setup record names, which the adapter checks the restored state against before it returns the same commitment. `adapter-out/1`: adds optional `kernels` on commit and prove (a device-kernel store's counts, build key and shape set; for prove, `replies_built`).
- `quantity/1`: adds unit `gpu_s` (GPU-seconds) to the unit enum and INV-QTY-3, for a setup's `gpu_seconds` (bound GPUs times wall seconds, `iproofs.setups.gpu_seconds`), and null reason `setup_reused`. A session that reused a setup records `commit_seconds` and `whole_wall_seconds` null with `setup_reused` and source `run.json#/setup`: its commit step only checks the restored state, so a figure timed from it would leave the setup's commitment and build out under the same labels. Formulas over them (D-COMMIT-AMORT-H1, -H1000, rates at `whole_wall`) are null with that reason, and the Level 1 board reads no session figure from such a run (RFC-0018 CO-1 times a session from the start of its commit).
- `run/1`: adds optional `kernels` (`commit`, `prove`: each step's adapter-out/1 `kernels` as the adapter reported it, or null), so a run without `--keep-io` still shows the store a session proved from and how many replies rebuilt it; `setup` adds optional `build_key`, the store build key the setup record names.

## Testing Strategy

Unit tests in `harness/tests/unit/`:

- `test_serialize.py::test_dumps_sorted_indented_lf`: asserts exact output bytes for a fixture with nested keys, non-ASCII text, and float `0.1`.
- `test_serialize.py::test_nan_rejected` and `test_inf_rejected`: assert `ValueError`.
- `test_serialize.py::test_atomic_write_leaves_no_partial`: simulates a crash between write and rename, confirming the target file is either absent or untouched.
- `test_digest.py::test_model_digest_known_vector`: hashes a fixture directory (`a/b.bin` = `b"x"`, `a.bin` = empty, `z` = `b"\n"`) against a reference digest computed separately with `sha256sum` and `printf` in the test docstring.
- `test_digest.py::test_sort_is_bytewise`: verifies that paths `B`, `a`, and `é` sort in raw UTF-8 byte order `B`, `a`, `é`.
- `test_digest.py::test_symlink_rejected`.
- `test_yaml.py::test_unquoted_date_rejected`, `test_alias_rejected`, and `test_norway_no_caught_by_schema` (confirming a claim card with `availability: no` fails validation).
- `test_quantity.py`: one test per invariant INV-QTY-1 through INV-QTY-9 (including INV-QTY-6a, verifying that deriving from one `reproduced` and one `reported` input yields `reported`), each paired with a minimal violating fixture.
- `test_ids.py::test_run_id_allocation_concurrent`: spawns two processes allocating run ids in the same directory and verifies distinct ids.
- `test_model_drift.py`: enforces schema-to-dataclass parity as described above.

Property tests in `harness/tests/property/` (Hypothesis):

- `test_roundtrip`: verifies that for any JSON-typed tree of finite floats, integers, strings, dicts, and lists, `dumps(json.loads(dumps(x))) == dumps(x)`.
- `test_digest_order_independent`: verifies that a directory's model digest does not depend on file creation order on disk.
- `test_fsum_order_independent`: verifies that `math.fsum` produces identical results across arbitrary permutations of finite floats, matching the assumption relied on by derivation code.

Schema example tests assert that every file in `examples/valid/` validates and every file in `examples/invalid/` fails with an error path or keyword matching its companion `.reason` file.

## Decisions

- Q1. Schema `$id` values use `https://inference-proofs.org/` and are never dereferenced (RFC-0001 Q1). Changing that hostname is an editorial change across schemas because all validators resolve locally.
- Q2. The drift test checks property names and required status only, rather than comparing JSON Schema types against Python annotations; type checking will be added if a type-drift bug ever arises.

## References

- JSON Schema Draft 2020-12, https://json-schema.org/draft/2020-12
- RFC 2119, key words for requirement levels.
- RFC 8785, JSON Canonicalization Scheme (considered, not adopted).
- RFC 3339, date and time on the internet.
- Python documentation for `json`, `math.fsum`, `statistics`, and `random` reproducibility guarantees.
- [RFC-0004](0004-metrics-timing-grades.md), [RFC-0007](0007-evidence-tiers-and-reproduction.md), [RFC-0009](0009-results-and-publication.md), [RFC-0013](0013-validation-and-ci.md), [RFC-0014](0014-provenance-and-integrity.md).
