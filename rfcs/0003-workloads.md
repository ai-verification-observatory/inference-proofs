# RFC-0003: Workloads, prompt sets and divisions

- Status: Draft
- Authors: AbdelStark
- Created: 2026-11-03
- Target milestone: v0.1-alpha (schema); v0.1-beta (model fetch and prompt materialisation)
- Requires: RFC-0002, RFC-0012
- Supersedes: none
- Discussion: pull request that introduces it

## Summary

A workload fixes what is proved: the model by content hash, the precision, the prompt set by generator and corpus hash, the shape, the decoding rule and the phase. This RFC defines the workload file and its types, the four v0.1 native workloads for SASH and FlashProve, the deterministic prompt generator and its seed policy, the model fetch and hash rule, how a system declares the tokens one proof covers, and the three divisions (native, closed, open). It sketches the v0.2 rule for choosing common workloads as future work.

## Motivation

Fixed workloads are what made Ethproofs rows comparable ([PRD §2](../docs/PRD.md#2-vision)). Provable inference has no single workload yet: at their pinned commits, SASH supports Llama-3.1-8B (W8A8) and FlashProve supports Llama 4 Maverick at full size plus small synthetic shapes. Neither runs the other's model ([PRD §6](../docs/PRD.md#6-scope-of-v01)). The benchmark has to be honest about that from the first release and still make every row reproducible.

Scenarios:

1. A reproducer six months later must regenerate exactly the prompts of an original run from the record alone.
2. A team could precompute proofs if the prompt set were fixed and public in advance. Measured runs must not be cacheable.
3. A model host silently replaces a weight file under the same revision. The run must fail before any container sees the file.
4. Two rows from different native workloads appear on one page. The reader must not see them presented as a head-to-head result.

## Goals

- A workload file is valid against `schema/workload/1.schema.json` and fully determines the job's inputs except the per-job seed.
- Given a workload, a seed and the pinned tokenizer, the prompt set is bit-for-bit reproducible on any machine with the pinned Python range (INV-WL-2).
- Every weight file is hash-checked before use (INV-WL-1).
- Every measured job uses a fresh seed recorded in its manifest (INV-WL-3).
- Every row names its division, and rows from different native workloads are never shown as a direct comparison (INV-WL-5).

## Non-Goals

- Common workloads for v0.2 beyond the selection rule (future work).
- Sampled decoding. v0.1 is greedy only.
- Redistributing weights or tokenizers. The repository never holds weights ([AGENTS.md](../AGENTS.md) rule 8).
- Measuring model quality. `quality_gap` is copied from upstream (RFC-0002).

## Proposed Design

### Workload file

`workloads/<id>.yaml`, valid against `schema/workload/1.schema.json`. Types follow RFC-0012.

| Field | Required | Type | Content |
|---|---|---|---|
| `schema` | yes | `"workload/1"` | |
| `id` | yes | `^[a-z0-9][a-z0-9-]{2,63}$` | e.g. `sash-l31-8b-c4096` |
| `version` | yes | integer >= 1 | increments on any change that alters inputs; a new version is a new workload for comparison |
| `division` | yes | enum `native`, `closed`, `open` | |
| `claim_class` | closed only | claim class string (RFC-0002) | the single class allowed in a closed workload |
| `model.source` | yes | `{hub: "huggingface", repo: Text}` | public source |
| `model.revision` | yes | 40-hex commit of the model repository | never a branch or tag |
| `model.files` | yes | list of `{path: Text, sha256: 64-hex, bytes: integer}` | every file the adapter or tokenizer reads |
| `model.digest` | yes | `sha256:<hex>` | over `<path>\t<sha256>\n` lines sorted by path bytes (RFC-0012) |
| `model.licence` | yes | `{name: Text, url: Text, gated: bool}` | access terms |
| `model.parameters` | yes | `{total: integer, active_per_token: integer, source: URL}` | from the model's own documentation; used by RFC-0004 |
| `model.tokenizer_file` | yes | path in `model.files` | the tokenizer the prompt generator uses |
| `precision` | yes | `{served: Text, proved: Text}` | quantisation as served and as proved |
| `prompts.generator` | yes | `"corpus-window/1"` | generator id and version |
| `prompts.corpus_digest` | yes | `sha256:<hex>` | digest of `workloads/prompts/corpus.yaml` content set |
| `prompts.count` | yes | integer >= 1 | prompts per job |
| `prompts.length_rule` | yes | `{prompt_tokens: integer}` | exact token count per prompt |
| `shape.prompt_tokens` | yes | integer >= 1 | |
| `shape.output_tokens` | yes | integer >= 1 | 1 for next-token workloads |
| `shape.batch_size` | yes | integer >= 1 | requests per batch |
| `shape.batches_per_session` | yes | integer >= 1 | batches per `prove` call |
| `shape.context_window` | yes | integer >= `prompt_tokens + output_tokens - 1` (every position the model reads; the last output token is predicted, never read) | |
| `model.vocab_size` | yes | integer > 0, from the model's own configuration at the pinned revision | used by control C1 ([RFC-0008](0008-negative-controls.md#shared-controls-verifier-side)) |
| `precision.alternatives` | no | list of precision ids the system can also prove, from its own documentation | used by control P2; absent means P2 is `not_applicable` |
| `decoding` | yes | `{rule: "greedy"}` | sampled rules are rejected by the schema in `workload/1` |
| `phase` | yes | enum `prefill`, `decode`, `both` | |
| `systems` | yes | list of system ids | systems known to support it, including reference systems |
| `notes` | no | `Text` | |

Invariant INV-WL-4: `prompts.count == shape.batch_size * shape.batches_per_session` and `prompts.length_rule.prompt_tokens == shape.prompt_tokens`. The loader checks it; a violation is a `config` error.

### v0.1 native workloads

| ID | System | Model | Precision | prompt + output tokens | Batch | Batches per session | Prompts per job | Phase | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `sash-l31-8b-c4096` | SASH | Llama-3.1-8B | W8A8 | 4,096 + 512 greedy continuation | 1 | 1 | 1 | both | the system's published headline shape |
| `sash-l31-8b-c1024` | SASH | Llama-3.1-8B | W8A8 | 1,024 + 64 greedy continuation | 1 | 1 | 1 | both | close to FlashProve's window length |
| `fp-maverick-w1024-b1` | FlashProve | Llama 4 Maverick, public 4-bit conversion | 4-bit | 1,024 + 1 (next token) | 1 | 5 | 5 | prefill | |
| `fp-maverick-w1024-b24` | FlashProve | same | 4-bit | 1,024 + 1 (next token) | 24 | 5 | 120 | prefill | the system's published steady-state shape |

Reference rows are jobs of the reference systems `ref-serve` and `ref-recompute` (RFC-0015) on these same workload ids. They are named `ref-serve-<workload-id>` and `ref-recompute-<workload-id>` in tables; there are no separate workload files for them. Each workload's `systems` list includes `ref-serve` and `ref-recompute`.

The model revision, file hashes and parameter counts are filled in the implementing issue from the public model repositories; the schema rejects a workload without them, so no unpinned workload can run.

### Prompt corpus

`workloads/prompts/corpus.yaml`, valid against `schema/corpus/1.schema.json`:

```yaml
schema: corpus/1
normalisation: {unicode: NFC, newlines: LF, strip_bom: true}
texts:
  - id: <short id>
    source_url: <URL of the plain-text file>
    licence: <statement, e.g. "public domain in the United States">
    sha256: <64-hex of the downloaded bytes>
    bytes: <integer>
```

The corpus digest is sha256 over the lines `<id>\t<sha256>\n` sorted by `id` bytes. The corpus text is fetched once by `iproofs prompts build`, hash-checked, normalised, and cached outside the repository. The same corpus feeds every workload, so prompt lengths in tokens differ only by tokenizer.

### Prompt generator `corpus-window/1`

Inputs: the normalised corpus texts in `id` order, the workload's tokenizer file, `count`, `L = prompt_tokens`, and a 64-bit unsigned `seed`.

```python
def corpus_window_v1(texts: list[str], tokenizer: Tokenizer, count: int, L: int, seed: int) -> list[list[int]]:
    # Concatenate with a single LF between texts, then tokenise once without special tokens.
    ids = tokenizer.encode("\n".join(texts), add_special_tokens=False).ids
    N = len(ids)
    if N < L:
        raise ConfigError("corpus shorter than prompt length")
    rng = random.Random(seed)            # Mersenne Twister, seeded from the integer
    prompts = []
    for _ in range(count):
        r = rng.random()                 # the only method CPython guarantees stable across versions
        offset = math.floor(r * (N - L + 1))
        prompts.append(ids[offset:offset + L])
    return prompts
```

Rules:

1. Only `random.Random(seed).random()` is called. `randrange`, `choice` and `shuffle` are not used, because CPython does not guarantee their sequences across versions.
2. Special tokens (beginning of sequence, chat templates) are not inserted by the generator. If an upstream prover requires a beginning-of-sequence token, the adapter adds it and documents it in its README; the workload's `prompt_tokens` counts the generator's tokens only, and the adapter declares any added tokens in `tokens_covered` (RFC-0004).
3. The materialised prompt set is written as `prompts.jsonl`, one JSON array of token ids per line, in generation order, with the canonical JSON writer (RFC-0012). Its digest is `sha256:` of the file bytes.
4. The generator id is versioned. Any change to this algorithm is `corpus-window/2` and a new workload version.

INV-WL-2: for fixed corpus digest, tokenizer file hash, `count`, `L` and `seed`, `prompts.jsonl` is byte-identical across machines and across Python 3.12 and 3.13.

### Seed policy

- **Measured jobs (INV-WL-3).** The harness draws `seed = int.from_bytes(os.urandom(8), "big")` at job start, in the `resolved` state before `info` (RFC-0010). The manifest records the seed and the prompt set digest (`workload.prompt_seed`, `workload.prompt_set_digest`, RFC-0014). A fresh seed per job means a prover cannot precompute proofs for a known prompt set.
- **Reproduction jobs.** A reproducer reruns with each of the original's recorded seeds (`--prompts-from` replay, RFC-0010), which makes proof digests and verdicts comparable, and runs at least one additional job with a fresh seed (RFC-0007).
- **Control jobs.** Controls reuse the honest run's prompts; seeded positions and offsets inside controls derive from the control suite's own recorded `control_seed` (RFC-0008).
- `iproofs prompts build WORKLOAD --seed SEED` prints the digest so anyone can check a recorded prompt set without running a prover.

### Model fetch and hash rule

1. `iproofs fetch-model WORKLOAD` downloads every file in `model.files` from `model.source` at `model.revision`, into a cache directory outside the repository.
2. Each file's sha256 and byte count are checked against the workload. Then `model.digest` is recomputed and checked (INV-WL-1).
3. Any mismatch is an `integrity` error. The job stops before `info`, no container sees the files, and the failure is recorded.
4. Fetch failures retry at most 3 times with backoff 2 s, 8 s, 32 s (RFC-0010); all outside timed scopes.
5. Gated models: the runner accepts the licence with their own account. The token is read from `HF_TOKEN`, never logged, never written to any record (RFC-0010 redaction).
6. The model directory is mounted read-only at `/models` in every container.

Prover-side controls need perturbed weights (RFC-0008). The perturbed copy is produced by the harness from the verified files, recorded with its own digest, and never confused with the workload's `model.digest`.

### Tokens covered

Every system declares, in `system.yaml` (RFC-0005) and its claim card `coverage.tokens_covered`, how many tokens one proof covers for each supported workload, as a function of the shape. The harness computes `tokens_covered` per proof from that declaration and checks it against the adapter's reported `tokens_covered` (RFC-0005 `prove` output). A mismatch is an `adapter` error.

- Next-token prefill proof (FlashProve): the window's positions, `prompt_tokens` per request.
- Segment grid (SASH): the positions in the grid, `prompt_tokens + output_tokens` per sequence, as the adapter declares from upstream documentation.

RISK: SASH's segment grid does not map onto per-request proofs. If the adapter cannot declare tokens covered as a function of the shape from upstream documentation, the workload's rows carry `tokens_covered` with `null_reason: missing_input` and per-token metrics are not computed. Resolution plan: the SASH adapter issue confirms the grid geometry from the upstream documentation at the pin before the first beta run.

### Divisions

- **Native.** A system's own supported model and shape. Rows from different native workloads are shown side by side with normalised metrics (RFC-0004) and are never called a head-to-head result (INV-WL-5). The site renders native rows of different workloads in separate tables with the claim cards above them.
- **Closed.** A common workload with a fixed `claim_class`. Only systems whose card has that exact class run in it. Rows within one closed workload compare directly.
- **Open.** Anything declared: a workload outside the registry or a claim class other than the workload's. Shown separately.

v0.1 has native workloads only. The schema accepts `closed` and `open` so v0.2 needs no schema major.

### Choosing common workloads (future work, v0.2)

A candidate common workload is accepted, by RFC, when at least two systems run it through their adapters with no upstream change. Preference order: a small dense transformer of standard architecture with public weights that every prover can support; a mid-size open model in the 7B to 9B range that at least two provers support; a mixture-of-experts model once two provers support one. Each common workload fixes one claim class.

### Failure modes

| Failure | Response |
|---|---|
| Weight file hash mismatch | `integrity` error before `info`; job recorded as failed; no retry |
| Model revision no longer available upstream | `fetch` error after 3 retries; workload marked unavailable in the release report; a new revision needs a new workload version |
| Corpus text hash mismatch | `integrity` error in `prompts build`; no job starts |
| Corpus shorter than `prompt_tokens` | `config` error at load |
| INV-WL-4 violated | `config` error at load |
| Tokenizer produces different ids on another library version | Prompt digest differs from the recorded one; reproduction fails the digest check and is reported; the `tokenizers` version is recorded in the manifest |
| Adapter's `tokens_covered` differs from the declaration | `adapter` error; no per-token metric |
| A closed workload receives a card with another class | `config` error; the run is rejected or moved to open by its submitter |

## Alternatives Considered

- **A fixed public prompt file per workload.** Considered because it is simplest to reproduce. Rejected: it allows precomputed proofs. The fixed corpus plus recorded fresh seed keeps reproducibility (replay the seed) and removes caching.
- **Secret prompts held by the maintainers.** Considered because it is the strongest anti-caching measure. Rejected: reproducers could not regenerate inputs without the secret, and secrecy conflicts with N1 reproducibility.
- **Synthetic random token ids.** Considered because it needs no corpus. Rejected: attention and activation statistics on random ids differ from text, and some provers may behave differently on out-of-distribution inputs. Text keeps workloads realistic.
- **Forcing both systems onto one model now.** Rejected: it would require patching provers, forbidden by RFC-0005.
- **NumPy or PCG64 for offsets.** Considered for stronger stream guarantees. Rejected: adds a dependency for one call; `random.Random.random()` has a documented stability guarantee.
- **Hashing only the model directory as a whole.** Rejected: a per-file list localises a mismatch and lets adapters read a subset while still being checked.

## Drawbacks

- Fresh seeds mean two measured runs of one workload prove different prompts; run-to-run variance includes prompt variance. For fixed-length shapes this is expected to be small, and the statistics report it.
- Gated licences make reproduction depend on each runner accepting terms.
- Full-size Maverick weights are large to fetch and hash on every new machine.
- The corpus choice is a judgement call; a different corpus could shift timings for data-dependent provers.

## Conflicts of Interest

The author's affiliations and any interest in a measured system are declared in `MAINTAINERS.md` before this RFC enters Last call (RFC-0001).

## Migration / Rollout

1. v0.1-alpha: `workload/1` and `corpus/1` schemas with examples; loader with INV-WL-4; the generator against a toy tokenizer fixture.
2. v0.1-beta: the four workload files with pinned revisions and hashes; `corpus.yaml` with chosen texts; `fetch-model` and `prompts build` on real models.
3. The earlier draft's shape fields (prompt length, output length, batch size, context window) are kept and `batches_per_session` is added. No results exist yet, so nothing is relabelled.

## Testing Strategy

- `test_generator_golden`: fixed tiny corpus, a stored toy `tokenizer.json`, `seed=0`, `count=3`, `L=8`: output equals a committed golden `prompts.jsonl` and digest.
- `test_generator_stable_across_python`: the golden test runs in CI on Python 3.12 and 3.13.
- `test_generator_offset_bounds` (property, hypothesis): for any `N >= L >= 1` and any seed, every offset is in `[0, N - L]` and every prompt has length `L`.
- `test_generator_seed_sensitivity`: seeds 0 and 1 give different prompt sets on the fixture.
- `test_generator_only_random_method`: the generator module imports no `random` method other than `Random` and calls only `.random()` (AST check).
- `test_corpus_too_short`: `L > N` raises `config`.
- `test_inv_wl4`: `count != batch_size * batches_per_session` fails at load.
- `test_model_hash_mismatch`: a fixture model dir with one byte changed raises `integrity` and the container runner is never called (mock asserts no call).
- `test_model_digest_order`: digest is independent of filesystem listing order.
- `test_fresh_seed_recorded`: two fake-system jobs record different seeds; replaying one seed reproduces its prompt digest.
- Schema examples: `valid/sash-l31-8b-c4096.yaml`, `valid/closed-with-class.yaml`; `invalid/branch-revision.yaml` (`revision: main`), `invalid/sampled-decoding.yaml`, `invalid/closed-without-class.yaml`, `invalid/context-too-small.yaml` (schema cannot express it; loader test `test_context_window_check`).

## Open Questions

- Resolved Q1: the default holds. The corpus is eight Project Gutenberg plain-text eBooks, public domain in the United States, listed with URLs and hashes in [`workloads/prompts/corpus.yaml`](../workloads/prompts/corpus.yaml); selection and licence basis in [`workloads/prompts/README.md`](../workloads/prompts/README.md). Corpus digest `sha256:cedd5c414e7c70b99348140c4ddfde8754446c3d3085f77d5d29a4e7324f639a`.
- OPEN QUESTION Q2 (owner: AbdelStark, resolve by: RFC for v0.2): which mid-size model has the widest prover support at the first v0.2 call. Default: none chosen; v0.1 is native only.
- OPEN QUESTION Q3 (owner: AbdelStark, resolve by: RFC for v0.2): whether decode-heavy shapes (long outputs) get their own workload family. Default: no.
- Resolved Q4: one SASH grid proves every prompt and continuation position of its sequence (the recorded 4,096 + 512 run is 9 blocks of 512 positions over 32 layers plus 2 head segments, 290 segments), so `tokens_covered` is `prompt_tokens + output_tokens` per sequence, exact, for both shapes. Upstream states no geometry for the 1,024 + 64 shape; the count does not depend on it. Sources, at the pinned commits: [`systems/sash/README.md`](../systems/sash/README.md#grid-geometry-and-proof-release).

## References

- [docs/PRD.md](../docs/PRD.md), sections 2, 6, 7 (F2) and 10.
- Python `random` module documentation, reproducibility notes (stability of `random()` across versions).
- Unicode Standard Annex 15, normalisation form C.
- [RFC-0002](0002-claim-card.md) (claim class), [RFC-0004](0004-metrics-timing-grades.md) (tokens covered in metrics), [RFC-0005](0005-adapter-contract.md) (adapter declarations), [RFC-0007](0007-evidence-tiers-and-reproduction.md) (seed replay), [RFC-0008](0008-negative-controls.md) (perturbed weights), [RFC-0012](0012-schemas-and-serialization.md) (digests, canonical JSON), [RFC-0015](0015-reference-rows.md) (reference systems).
