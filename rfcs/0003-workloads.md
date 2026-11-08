# RFC-0003: Workloads, prompt sets and divisions

- Status: Draft
- Authors: AbdelStark
- Created: 2026-11-03
- Target milestone: v0.1-alpha (schema); v0.1-beta (model fetch and prompt materialisation)
- Requires: RFC-0002, RFC-0012
- Supersedes: none
- Discussion: pull request that introduces it

## Summary

A workload fixes what is proved: the model by content hash, the precision, the prompt set by generator and corpus hash, the shape, the decoding rule and the phase. This RFC defines the workload file and its types, the four v0.1 native workloads for SASH and FlashProve, the one closed workload on Llama 3.1 8B, the deterministic prompt generator and its seed policy, the model fetch and hash rule, how a system declares the tokens one proof covers, and the three divisions (native, closed, open). It sets the rule for accepting a common workload and when a closed workload's rows publish.

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

- Common workloads beyond `l31-8b-c1024` and the selection rule (future work, v0.2).
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
| `model.tokenizer_file` | yes | path in `model.files`, or `model.tokenizer_source.file.path` | the tokenizer the prompt generator uses |
| `model.tokenizer_source` | no | `{hub: huggingface, repo, revision, file: {path, sha256, bytes}}` | the tokenizer file from a second pinned repository, when the weights' repository has none (for example a GGUF conversion). `model.digest` covers `model.files` only; this file is checked against its own sha256 |
| `precision` | yes | `{served: Text, proved: Text}` | quantisation as served and as proved |
| `precision.weight_bits` | no | `{bits: number > 0 and <= 64, basis: "stated" or "file_size", covers: "all" or "part", source: URL, files: [path], note: Text}`; `bits` exactly when `basis` is `stated`, `files` exactly when it is `file_size`, and `covers` is `all` for `file_size`; `note` optional | bits per weight of the precision as proved, with its source (§Weight bits); used by RFC-0004 D-SPAB-S |
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

### Weight bits

`precision.weight_bits` holds one number: the bits that store one weight of the precision as proved (`precision.proved`). It is an input of [RFC-0004](0004-metrics-timing-grades.md#derived-metric-catalogue) D-SPAB-S, prover seconds per bit of active weights per token covered, and enters it like `model.parameters`: an `asserted` input (RFC-0004 grades), never measured, whose source is the record's `source`. Multiplied by `model.parameters.active_per_token`, it gives the bits of active weights per token. `covers` says whether the source's width covers `all` the weights `active_per_token` counts or only `part` of them; RFC-0004 INV-DERIVE-7 keeps a `part` width out of sorting. The value comes from one of two bases, in this order of preference:

- WB-1, `stated`: the width that the precision's own documentation states at a pinned commit or revision, copied and linked: the system's documentation when the system quantizes the weights itself, or the publisher's when the pinned files are already quantized. `note` says what the statement covers when it does not cover every weight. This is the rule whenever file size does not give the width:
  - quantization at load time: the pinned files hold another precision than the one proved. The SASH workloads' files hold BF16 weights (file bytes over `parameters.total` is 2 bytes per parameter), and SASH proves int8 weight matmuls, as its own source states;
  - mixed widths: the files store tensors at several widths. A GGUF quant mix such as `UD-Q4_K_XL` holds several block types, and a mixture of experts can store routed experts at another width than its shared weights, so file bytes over total parameters is not the width of the active weights either.
  A statement that names one part of the weights is recorded with `covers: part` and a `note` saying what it covers: Unsloth states its figure per quant under "MoE Bits", that is for the mixture-of-experts layers, and SASH states its int8 width for weight matmuls, which leaves out the embedding table that `active_per_token` counts. Applying such a width to every active weight would extend the statement past what it says, so the figure is a nominal width, not a mean over the active weights; RFC-0004 prints the note beside it and does not sort by it (INV-DERIVE-7).
- WB-2, `file_size`: only when the files in `files` hold every weight of the precision as proved, at one width, and nothing else, so `covers` is `all`. The width is a derived number, so the record does not type it (AGENTS.md rule 3): the loader computes `bits` = the sum of the listed files' `bytes` × 8 / `model.parameters.total`, from `model.files` and the parameter count, in binary64. A listed file outside `model.files` is a `config` error; a typed `bits` with this basis fails the schema.
- WB-3: when no documentation states a width and file size does not give it, the field is absent and D-SPAB-S is null with `missing_input`. The width is never estimated.
- WB-4: `precision.weight_bits` describes the weights; it does not change a job's inputs (model files, prompts, shape), so adding it where it was absent keeps the workload `version`. The runner copies the record's parameter count and weight bits into run.json `inputs` as `asserted` quantities at run time, and D-APT-S and D-SPAB-S name those copies in `source.inputs` (RFC-0004 INV-DERIVE-7), so RFC-0013 G4 recomputes a stored run from the run itself, never from the workload file as it reads later. Once a run has recorded a workload's weight bits, changing `bits`, `basis` or `covers` (a correction, or Q5's resolution) is a new workload `version`: the runs before and after it are then two configurations, never one statistic over two widths. The release freeze enforces it: repetitions of one configuration with different recorded inputs stop the freeze with an error. The field also changes the workload file's bytes, and so its `file_digest` in every manifest recorded after the change (RFC-0014); reproduction eligibility does not compare that digest (Q6).

The v0.1 values:

| Workload | `bits` | `basis`, `covers` | Source |
|---|---|---|---|
| `sash-l31-8b-c4096`, `sash-l31-8b-c1024`, `l31-8b-c1024` | 8 | `stated`, `part` | SASH at `eb95bfa887299d1637550228d42086c27cbb2b3b`, [`harness/witness/quant.py` L15 to L19](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/harness/witness/quant.py#L15-L19): "weight matmuls are exact int8 x int8 -> int32 accumulations", with one scale per output channel. It states no width for the embedding table, which `active_per_token` counts. The files are BF16 and quantized at load time |
| `fp-maverick-w1024-b1`, `fp-maverick-w1024-b24` | 4.5 | `stated`, `part` | the publisher's model card at `41032e5471dd6ea5b349062d978626215d6c5bba`, [README L122 to L129](https://huggingface.co/unsloth/Llama-4-Maverick-17B-128E-Instruct-GGUF/blob/41032e5471dd6ea5b349062d978626215d6c5bba/README.md#L122-L129): "4.5-bit" for `Q4_K_XL` in the column headed "MoE Bits", a width for the mixture-of-experts layers, not for the other weights the 17e9 active parameters also count (attention among them). The pinned files' GGUF tensor table also stores some tensors as Q5_K, Q6_K and F32, routed experts' down projections included: a nominal width (Q5) |
| `fake-tiny-ci` | 8, computed | `file_size`, `all` | `weights.bin`, 64 B over 64 parameters ([`systems/fake/README.md`](https://github.com/ai-verification-observatory/inference-proofs/blob/64168df9fd0706dfd955b6795fa6f535872dff78/systems/fake/README.md)): 64 × 8 / 64 = 8, recomputed by the loader |

### v0.1 native workloads

| ID | System | Model | Precision | prompt + output tokens | Batch | Batches per session | Prompts per job | Phase | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `sash-l31-8b-c4096` | SASH | Llama-3.1-8B | W8A8 | 4,096 + 512 greedy continuation | 1 | 1 | 1 | both | the system's published headline shape |
| `sash-l31-8b-c1024` | SASH | Llama-3.1-8B | W8A8 | 1,024 + 64 greedy continuation | 1 | 1 | 1 | both | close to FlashProve's window length |
| `fp-maverick-w1024-b1` | FlashProve | Llama 4 Maverick, public 4-bit conversion | 4-bit | 1,024 + 1 (next token) | 1 | 5 | 5 | prefill | |
| `fp-maverick-w1024-b24` | FlashProve | same | 4-bit | 1,024 + 1 (next token) | 24 | 5 | 120 | prefill | the system's published steady-state shape |

Reference rows are jobs of the reference systems `ref-serve` and `ref-recompute` (RFC-0015) on these same workload ids. They are named `ref-serve-<workload-id>` and `ref-recompute-<workload-id>` in tables; there are no separate workload files for them. Each workload's `systems` list includes `ref-serve` and `ref-recompute`.

The model revision, file hashes and parameter counts are filled in the implementing issue from the public model repositories; the schema rejects a workload without them, so no unpinned workload can run.

### Closed workloads

| ID | Model | Precision | prompt + output tokens | Batch | Batches per session | Prompts per job | Phase | Claim class | Status |
|---|---|---|---|---|---|---|---|---|---|
| `l31-8b-c1024` | Llama-3.1-8B, the files and `model.digest` of `sash-l31-8b-c1024` | W8A8 | 1,024 + 64 greedy continuation | 1 | 1 | 1 | both | `greedy-continuation/exact-match/committed-weights` | candidate (Q7) |

The owner decided on 2026-11-08 that v0.1 carries one shared workload on Llama 3.1 8B in the closed division, so that rows on one model compare directly. Its inputs are those of `sash-l31-8b-c1024`: the same model repository, revision, files and digest, tokenizer, corpus, precision and shape. Two workloads may pin the same files; the digest names the files, not the workload, and the fetch rule checks it the same way for both. A closed workload is a different workload from a native one with the same inputs: its rows are compared within it and never with the native workload's rows (INV-WL-5).

Why these choices (defaults, Q8 and Q9):

- **Claim class.** SASH's card class, the one system whose adapter runs the model. A system whose card has another class runs the model in an open workload. FlashProve's card class is `next-token/exact-match/committed-weights`.
- **Precision.** W8A8, the precision SASH proves. Of the other systems whose sources were read for this choice, none states W8A8 for this model ([`workloads/README.md`](../workloads/README.md#which-systems-sources-name-the-model)).
- **Shape.** The shorter of SASH's two native shapes. Upstream SASH records no run at this shape ([`systems/sash/README.md`](../systems/sash/README.md#the-two-v01-shapes)); the adapter derives the grid from the shape.

`workloads/README.md` gives, per system listed on the site, the sources read at a full commit, what they say about Llama 3.1 8B or its model family, the precision and the claim class, or "not stated". A system joins by RFC-0001 §Adding and removing a system; it never joins by an upstream change (RFC-0005).

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
- **Closed.** A common workload with a fixed `claim_class`. Only systems whose card has that exact class run in it: the runner reads the job's claim card when it resolves the job, and a card of another class, or a proving system with no card, is a `config` error before any container starts. A reference system has no card (RFC-0015) and runs on every workload. Rows within one closed workload compare directly. The site renders a closed workload's rows in a table of their own, after the model's native tables, under a heading naming the workload, its division and its profile, without the native header (RFC-0009 S6).
- **Open.** Anything declared: a workload outside the registry or a claim class other than the workload's. Shown separately, as closed tables are.

v0.1 has native workloads and one closed workload, `l31-8b-c1024` (§Closed workloads). It has no open workload.

### Choosing common workloads

A candidate common workload is accepted, by RFC, when at least two systems run it through their adapters with no upstream change. Preference order: a small dense transformer of standard architecture with public weights that every prover can support; a mid-size open model in the 7B to 9B range that at least two provers support; a mixture-of-experts model once two provers support one. Each common workload fixes one claim class.

A candidate's file may land before it is accepted (`l31-8b-c1024`). Until a second system with its class runs it through an adapter, its rows enter no release and the site shows none (Q7). Further common workloads are chosen for v0.2 by the same rule.

### Failure modes

| Failure | Response |
|---|---|
| Weight file hash mismatch | `integrity` error before `info`; job recorded as failed; no retry |
| Model revision no longer available upstream | `fetch` error after 3 retries; workload marked unavailable in the release report; a new revision needs a new workload version |
| Corpus text hash mismatch | `integrity` error in `prompts build`; no job starts |
| Corpus shorter than `prompt_tokens` | `config` error at load |
| INV-WL-4 violated | `config` error at load |
| `precision.weight_bits` with basis `file_size` that lists a file outside `model.files`, or types `bits` (WB-2) | `config` error at load |
| Repetitions of one configuration recorded with different weight bits or parameter counts (WB-4) | the release freeze stops with an error naming the runs; the change needs a new workload version |
| No `precision.weight_bits` (WB-3) | the workload loads; RFC-0004 D-SPAB-S is null with `missing_input` |
| Tokenizer produces different ids on another library version | Prompt digest differs from the recorded one; reproduction fails the digest check and is reported; the `tokenizers` version is recorded in the manifest |
| Adapter's `tokens_covered` differs from the declaration | `adapter` error; no per-token metric |
| A closed workload receives a card with another class, or a proving system with no card | `config` error at job resolution, before any container starts; the run is rejected or moved to open by its submitter |

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
4. The amendment of 2026-11-08 adds `precision.weight_bits` (§Weight bits), the input RFC-0004 D-SPAB-S needs (owner decision of 2026-11-08: prover time per bit of active weights and the overhead against plain serving are the two figures that compare provers across models). The field is optional, so `workload/1` stays at major 1 (RFC-0012); every file in `workloads/` gains it with its source, and no workload version changes (WB-4: the field was absent). Stored runs (`results/v0.1`) are not changed (APP-1): they carry no run.json `inputs`, and a release gets their D-SPAB-S from the workload record at the release commit (RFC-0004 Q3). Following review, the amendment adds `covers`, makes the loader compute a `file_size` width instead of checking a typed one, adds run.json `inputs` (an optional `run/1` property, RFC-0012) and the version rule of WB-4, and settles Q6 by RFC-0007 rule 1.
5. #334: `l31-8b-c1024` lands as a candidate closed workload, and the runner checks a closed workload's class at job resolution. No system lists it in its `system.yaml` yet, so no job of it runs; SASH lists it with a new adapter image, and each other system that joins does so by its own inclusion issue (RFC-0001).

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
- Weight bits (`test_workload.py`): `test_weight_bits_stated` (WB-1 loads as written, `covers: part`), `test_weight_bits_absent` (valid, no field; the run input is null `missing_input`), `test_weight_bits_file_size` (hand-computed: 64 B over 16 parameters, the loader computes 64 × 8 / 16 = 32, fixture values), `test_weight_bits_file_size_typed`, `test_weight_bits_file_size_unknown_file`, `test_weight_bits_file_size_needs_files` (WB-2), `test_asserted_inputs` (WB-4: the run inputs are schema-valid asserted quantities that point at the record).
- WB-4 (`test_runner.py::test_g4_survives_a_weight_bits_correction`): a fake run, then its workload's weight bits corrected from 8 (file size) to 4 (stated); G4 on the stored run stays clean. `test_freeze.py::test_freeze_stops_on_different_workload_inputs`: two repetitions recorded with different inputs stop the freeze.
- Q6 (`test_reproduce.py`): `test_workload_file_digest_alone_keeps_eligibility` (originals and reproduction differ only in `file_digest`: eligible), `test_workload_corpus_digest_breaks_eligibility`.
- `test_closed_workload_loads`: `l31-8b-c1024` loads, is closed, fixes its class and has the model, shape and precision of `sash-l31-8b-c1024`; `test_closed_workload_needs_class`: a closed workload without `claim_class` fails at load.
- `test_closed_workload_class_mismatch` (runner): a job whose card class differs from the closed workload's, or whose system has no card, fails at resolution with a `config` error and no container call; a card of the same class runs; a reference system is not checked.
- Schema examples: `valid/sash-l31-8b-c4096.yaml`, `valid/closed-with-class.yaml`, `valid/weight-bits-file-size.yaml`; `invalid/branch-revision.yaml` (`revision: main`), `invalid/sampled-decoding.yaml`, `invalid/closed-without-class.yaml`, `invalid/weight-bits-zero.yaml`, `invalid/weight-bits-over-64.yaml`, `invalid/weight-bits-unknown-basis.yaml`, `invalid/weight-bits-no-source.yaml`, `invalid/weight-bits-no-covers.yaml`, `invalid/weight-bits-file-size-without-files.yaml`, `invalid/weight-bits-file-size-typed.yaml`, `invalid/weight-bits-file-size-part.yaml`, `invalid/weight-bits-stated-with-files.yaml`, `invalid/context-too-small.yaml` (schema cannot express it; loader test `test_context_window_check`).

## Open Questions

- Resolved Q1: the default holds. The corpus is eight Project Gutenberg plain-text eBooks, public domain in the United States, listed with URLs and hashes in [`workloads/prompts/corpus.yaml`](../workloads/prompts/corpus.yaml); selection and licence basis in [`workloads/prompts/README.md`](../workloads/prompts/README.md). Corpus digest `sha256:cedd5c414e7c70b99348140c4ddfde8754446c3d3085f77d5d29a4e7324f639a`.
- Resolved Q2 (owner decision, 2026-11-08): the mid-size model is Llama 3.1 8B, in the closed workload `l31-8b-c1024` (§Closed workloads). Of the systems the site lists, SASH alone runs it through an adapter at the pins read; TOPLOC's paper and experiments name it, zkPyTorch's paper names "Llama-3" with no public code ([`workloads/README.md`](../workloads/README.md#which-systems-sources-name-the-model)).
- OPEN QUESTION Q3 (owner: AbdelStark, resolve by: RFC for v0.2): whether decode-heavy shapes (long outputs) get their own workload family. Default: no.
- Resolved Q4: one SASH grid proves every prompt and continuation position of its sequence (the recorded 4,096 + 512 run is 9 blocks of 512 positions over 32 layers plus 2 head segments, 290 segments), so `tokens_covered` is `prompt_tokens + output_tokens` per sequence, exact, for both shapes. Upstream states no geometry for the 1,024 + 64 shape; the count does not depend on it. Sources, at the pinned commits: [`systems/sash/README.md`](../systems/sash/README.md#grid-geometry-and-proof-release).
- OPEN QUESTION Q5 (owner: 0xchqrles, resolve by: Last call of RFC-0004's amendment of 2026-11-08, and before the first Maverick run records D-SPAB-S, since a later change is a new workload version under WB-4): for pinned files stored at mixed widths, and for statements that cover part of the weights, does the record keep the stated width or a width computed from the files? Default until resolved: the stated width (WB-1), 4.5 for the Maverick workloads and 8 for the SASH workloads, both `covers: part` with a note, so RFC-0004 INV-DERIVE-7 shows their D-SPAB-S unsorted. With every v0.1 production workload at `covers: part`, no D-SPAB-S row is sortable until Q5 is resolved. The alternative is a third basis, `tensor_table`: the mean storage bits per active weight, which the harness would compute from the GGUF tensor table of the pinned files (each tensor's elements times the bits per element of its block type, as ggml defines the block sizes; routed experts' tensors weighted by experts used per token over expert count) and check at fetch time. Two conventions meet here: Unsloth's 4.5 is ggml's size of a Q4_K block per weight, block scales included, while the SASH workloads' 8 counts the int8 code alone, without its per-channel scale; FlashProve's own guide names the same folder "4 bits" ([examples/maverick/README.md L332](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/examples/maverick/README.md#L332)).
- Resolved Q6: adding `precision.weight_bits` changes each workload file's `file_digest` (WB-4). RFC-0007 eligibility rule 1 asks for the same workload ids and versions and the same model and corpus digests, not the same file digest; the harness had also compared `file_digest`, which would have made every reproduction of a run stored before this amendment ineligible. `same_workload_digests` now compares what rule 1 names (id, version, model, corpus digest), and the manifest keeps recording `file_digest`. A change that alters inputs is a new workload version (§Workload file), which the comparison still catches.
- OPEN QUESTION Q7 (owner: AbdelStark, resolve by: v0.1 freeze): whether the two-system rule holds for `l31-8b-c1024`. Default: it holds; the file lands now, and its rows publish once a second system with its class runs it through an adapter with no upstream change. No check enforces it yet: `iproofs release freeze` does not count the systems of a closed workload, so the release pull request's reviewers do.
- OPEN QUESTION Q8 (owner: AbdelStark, resolve by: v0.1 freeze): which claim class `l31-8b-c1024` fixes. Default: `greedy-continuation/exact-match/committed-weights`, SASH's card class.
- OPEN QUESTION Q9 (owner: AbdelStark, resolve by: v0.1 freeze): the precision and shape of `l31-8b-c1024`. Default: those of `sash-l31-8b-c1024` (W8A8; 1,024 + 64, batch 1). Alternatives: 4,096 + 512, the shape upstream SASH records; bf16, the precision TOPLOC's experiments name.

## References

- [docs/PRD.md](../docs/PRD.md), sections 2, 6, 7 (F2) and 10.
- Python `random` module documentation, reproducibility notes (stability of `random()` across versions).
- Unicode Standard Annex 15, normalisation form C.
- [RFC-0002](0002-claim-card.md) (claim class), [RFC-0004](0004-metrics-timing-grades.md) (tokens covered in metrics), [RFC-0005](0005-adapter-contract.md) (adapter declarations), [RFC-0007](0007-evidence-tiers-and-reproduction.md) (seed replay), [RFC-0008](0008-negative-controls.md) (perturbed weights), [RFC-0012](0012-schemas-and-serialization.md) (digests, canonical JSON), [RFC-0015](0015-reference-rows.md) (reference systems).
