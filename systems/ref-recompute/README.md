# ref-recompute

Recompute by a verifier holding the weights ([RFC-0015 §Recompute](../../rfcs/0015-reference-rows.md#recompute-ref-recompute)). The engine pin, the precision per workload and every engine option are documented in [`ref-serve`'s README, §Recompute](../ref-serve/README.md#recompute-ref-recompute): `--max-num-seqs 1` for every workload (RC-2), and `--max-model-len` one token longer than the workload's sequence, because the engine generates one token after the prompt plus claimed output. Production serving (`ref-serve`, RFC-0015 SRV-6) runs other weights and options; this system keeps the PM rules. The image runs the same entrypoint, `systems/ref-serve/entrypoint`, with this `system.yaml` (`Dockerfile`).

## What `prove` does

- **Input:** the harness runs it only with `--prompts-from` a completed system run (RC-1). The source run's claimed outputs, from its `run.json` `proofs[]`, arrive as `/io/claimed.jsonl` (`claims_file` in `job.json`), one array of token ids per request.
- **One request at a time** (RC-2), whatever the workload's batch size.
- **Teacher-forced check** (RC-3, RC-7): one forward pass over prompt plus claimed output, with `SamplingParams(prompt_logprobs=1, max_tokens=1)` ([`sampling_params.py`](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/sampling_params.py#L347-L349)). At each claimed position the adapter takes the rank-1 token of the returned prompt log-probabilities, which is the argmax. Every position is fed the claimed prefix, so positions after a disagreement are still compared.
- **Ties** follow the engine: rank 1 is the first index `torch.topk` returns over the log-probabilities ([`Sampler.gather_logprobs`](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/v1/sample/sampler.py#L312-L337)).
- **Release** (RC-4): `/io/proofs/req-<i>/outputs.json` (`request_index`, `argmax`) per request, by atomic rename. The adapter judges nothing. The harness compares the argmax tokens with the claims and records `agreement` per proof, then `agreement_positions` and `disagreement_positions` per run (RC-5). Agreement never changes a verdict (INV-REF-1).

## Tests

`tests/` run on CPU (INV-ADAPTER-9) against argmax tokens captured once on a GPU host (`tests/fixtures/capture/`, with its own README).
