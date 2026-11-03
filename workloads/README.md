# Workloads

One file per workload, `workloads/<id>.yaml`, valid against `schema/workload/1.schema.json` ([RFC-0003 §Workload file](../rfcs/0003-workloads.md#workload-file)). Weights are never stored here; a workload pins them by source, revision and per-file hash.

`iproofs.workloads.load_workload` validates the file against its schema, then checks the rules a schema cannot express. Each violation is a `config` error naming the field:

- the file name matches `id`, and `version` matches the requested version when one is given;
- INV-WL-4: `prompts.count == shape.batch_size * shape.batches_per_session` and `prompts.length_rule.prompt_tokens == shape.prompt_tokens`;
- `shape.context_window >= shape.prompt_tokens + shape.output_tokens - 1`;
- `model.tokenizer_file` is one of `model.files[].path`;
- every id in `systems` has a `systems/<id>/system.yaml`.

The schema itself enforces the closed-division rule (`claim_class` present exactly when `division` is `closed`), greedy decoding and full 40-hex model revisions.

The prompt corpus is `prompts/corpus.yaml` ([RFC-0003 §Prompt corpus](../rfcs/0003-workloads.md#prompt-corpus)).
