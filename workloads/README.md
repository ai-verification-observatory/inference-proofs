# Workloads

One file per workload, `workloads/<id>.yaml`, valid against `schema/workload/1.schema.json` ([RFC-0003 §Workload file](../rfcs/0003-workloads.md#workload-file)). Weights are never stored here; a workload pins them by source, revision and per-file hash.

`iproofs.workloads.load_workload` validates the file against its schema, then checks the rules a schema cannot express. Each violation is a `config` error naming the field:

- the file name matches `id`, and `version` matches the requested version when one is given;
- INV-WL-4: `prompts.count == shape.batch_size * shape.batches_per_session` and `prompts.length_rule.prompt_tokens == shape.prompt_tokens`;
- `shape.context_window >= shape.prompt_tokens + shape.output_tokens - 1`;
- `model.tokenizer_file` is one of `model.files[].path`, or, when `model.tokenizer_source` names a second pinned repository for the tokenizer file alone, that source's `file.path`;
- every id in `systems` has a `systems/<id>/system.yaml`.

The schema itself enforces the closed-division rule (`claim_class` present exactly when `division` is `closed`), greedy decoding and full 40-hex model revisions.

## v0.1 workloads

| Workload | Model, at its pinned revision | Precision | Shape (prompt + output, batch, batches per session) | Phase | Systems |
|---|---|---|---|---|---|
| [`sash-l31-8b-c4096`](sash-l31-8b-c4096.yaml) | `unsloth/Llama-3.1-8B-Instruct` | W8A8 | 4,096 + 512, 1, 1 | both | `ref-serve`, `ref-recompute` |
| [`sash-l31-8b-c1024`](sash-l31-8b-c1024.yaml) | `unsloth/Llama-3.1-8B-Instruct` | W8A8 | 1,024 + 64, 1, 1 | both | `ref-serve`, `ref-recompute` |
| [`fp-maverick-w1024-b1`](fp-maverick-w1024-b1.yaml) | `unsloth/Llama-4-Maverick-17B-128E-Instruct-GGUF`, folder `UD-Q4_K_XL`; tokenizer from `unsloth/Llama-4-Maverick-17B-128E-Instruct` | UD-Q4_K_XL | 1,024 + 1, 1, 5 | prefill | `ref-serve`, `ref-recompute` |
| [`fp-maverick-w1024-b24`](fp-maverick-w1024-b24.yaml) | `unsloth/Llama-4-Maverick-17B-128E-Instruct-GGUF`, folder `UD-Q4_K_XL`; tokenizer from `unsloth/Llama-4-Maverick-17B-128E-Instruct` | UD-Q4_K_XL | 1,024 + 1, 24, 5 | prefill | `ref-serve`, `ref-recompute` |

The model is the one each system's own runs name: SASH's recorded runs use the ungated mirror `unsloth/Llama-3.1-8B-Instruct` at `4699cc75b550f9c6f3173fb80f4703b62d946aa5`; FlashProve names the `UD-Q4_K_XL` files of `unsloth/Llama-4-Maverick-17B-128E-Instruct-GGUF` at `41032e5471dd6ea5b349062d978626215d6c5bba`, whose repository has no tokenizer file, so `model.tokenizer_source` pins it from the ungated full-precision repository. A native system joins its workloads' `systems` list when its `system.yaml` lands; until then only the reference systems (RFC-0015) are listed.

The prompt corpus is `prompts/corpus.yaml` ([RFC-0003 §Prompt corpus](../rfcs/0003-workloads.md#prompt-corpus)).

## Checking a prompt set

`iproofs prompts build WORKLOAD --seed SEED [--out prompts.jsonl]` rebuilds the prompt set a job with that seed used, without running a prover: it fetches and verifies the corpus, loads the workload's tokenizer file (from the verified model cache, or fetched alone and checked against its listed sha256), runs `corpus-window/1`, writes `prompts.jsonl` and prints `{workload, seed, count, digest, tokenizers_version}` as JSON. The digest equals the manifest's `workload.prompt_set_digest` for a run that recorded that seed. Real tokenizer files need the `[prompts]` extra (`uv sync --extra prompts`); a different `tokenizers` version can tokenize differently, which shows as a different digest (RFC-0003 §Failure modes).
