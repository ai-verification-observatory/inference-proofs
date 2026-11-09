# ref-serve and ref-recompute: production serving and recompute

The reference systems of [RFC-0015](../../rfcs/0015-reference-rows.md): production serving (`ref-serve`, SRV-1 to SRV-10, owner decision of 2026-11-09) and recompute by a verifier holding the weights (`ref-recompute`, #139). Both run the same pinned engine image; `ref-recompute` keeps the plain-serving construction it had before (its own `system.yaml`, §Recompute below). This page records the engine pin, the serving weights, every engine option with the engine's documentation at the pinned version, and how the adapter works.

## Production serving (`ref-serve`)

Users ask how much overhead proving adds in normal conditions, the conditions in which providers serve the model. So the baseline is the model served as providers serve it: the pinned engine with its defaults, the publisher's release precision, every weight in GPU memory, tensor parallel over the fewest H200 that hold it (RFC-0015 SRV-6), and the overhead counts GPU-seconds per token on both sides (RFC-0004 INV-DERIVE-8).

- **Engine.** vLLM v0.32.0 (§Engine), started as its OpenAI-compatible server, `vllm serve /models --host 127.0.0.1 --port <free port> <engine_args>`, the interface providers run (RFC-0015 Q8; usage context `OPENAI_API_SERVER`). `--host` and `--port` bind the server to the container's loopback; they set no engine option. The engine is never built from a full `EngineArgs` dump: the adapter before 2026-11-09 passed every `EngineArgs` field into the `LLM` class, which ran neither that class's defaults nor the server's ([entrypoints/llm.py L226 to L227](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/entrypoints/llm.py#L226-L227)).
- **Options** (SRV-3), the allowlist and nothing else, per entry of `system.yaml` (workload, load point, GPU count), all documented in [engine_args.md](https://github.com/vllm-project/vllm/blob/v0.32.0/docs/configuration/engine_args.md):

  | Option | Value | Why |
  |---|---|---|
  | `--tensor-parallel-size` | the serving profile's `gpu.count` (4 for Maverick FP8, 1 for Llama 3.1 8B BF16) | every weight in GPU memory, over the fewest GPUs that hold it (SRV-6, `sizing.py`) |
  | `--max-model-len` | prompt plus output tokens: 1,025, 1,088 or 4,608 | the workload's sequence |
  | `--max-num-seqs` | the workload's batch size, matched load only | the matched batch (SRV-1); at high load the engine's default, 1,024 on a GPU of 70 GiB or more ([arg_utils.py L2933 to L2942](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/engine/arg_utils.py#L2933-L2942)) |

  No offload, no quantization option, no memory fraction, no `--language-model-only` (RFC-0015 Q4) and no `--skip-tokenizer-init` (Q7): the engine starts with its full default init. The validator refuses any other option for a serve-role entry (schema `system/1` and G2 rule SRV-3), and the adapter refuses one too.
- **Weights** (SRV-6): the serving record that names the workload, `workloads/serving/<id>.yaml`, fetched and checked by `iproofs fetch-model --serving` (RFC-0014 SM-2) and mounted at `/models`: Meta's FP8 release of Llama 4 Maverick (RedHatAI's byte-identical copy) and Meta's BF16 release of Llama 3.1 8B Instruct (NousResearch's copy). Neither copy holds Meta's `tokenizer_config.json` (RFC-0015 Q7); the first capture records whether the engine starts without it.
- **Requests** (SRV-2): each batch is sent whole as one completions request: `prompt` the batch's token-id prompts, `temperature` 0, `max_tokens` the workload's output tokens, `ignore_eos` true ([sampling_params.py L331](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/sampling_params.py#L331-L333)) and `return_token_ids` true, which returns each choice's output token ids as `choices[i].token_ids` ([completion/protocol.py L171 to L178](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/entrypoints/openai/completion/protocol.py#L171-L178); token-in, token-out is the pinned version's own test, [test_token_in_token_out.py](https://github.com/vllm-project/vllm/blob/v0.32.0/tests/entrypoints/openai/completion/test_token_in_token_out.py)). A request that returns another count of tokens fails the job (`adapter`).
- **Checks before the engine** (SRV-3, SRV-6): the entry of the job's load point and GPU count exists; the visible GPUs (`CUDA_VISIBLE_DEVICES`) number `--tensor-parallel-size`; every `VLLM_*`, `NCCL_*`, `CUDA_*` and `TORCH_*` variable of the engine process is the image's own (`/opt/iproofs/image_env.json`, written by the Dockerfile before it sets any variable, or by the development install from the image config by digest) or the harness's binding (`CUDA_VISIBLE_DEVICES`, `CUDA_DEVICE_ORDER`). A refusal is written to `/io/failure.json` with kind `config`, which the harness records as such (RFC-0005 amendment of 2026-11-09).
- **Records** (`/io/commands.jsonl`): the engine command (the runner checks that it ends with the entry's `engine_args` at the run's commit), the engine environment, the engine's resolved-configuration line (`Initializing a V1 LLM engine (v0.32.0) with config: ...`, [v1/engine/core.py L134](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/v1/engine/core.py#L134)) and its KV-capacity line (`GPU KV cache size: N tokens, Maximum concurrency for M tokens per request: Xx`, [v1/core/kv_cache_utils.py L2328](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/v1/core/kv_cache_utils.py#L2328)), and the engine as the adapter saw it run (`engine_observed`: the installed version, the image ENV's `VLLM_BUILD_COMMIT`, and the batched-token limit from `Chunked prefill is enabled with max_num_batched_tokens=N.`, [config/scheduler.py L307](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/config/scheduler.py#L307)). The engine's log is `/io/engine.log`.
- **Placement** (SRV-6): at matched load a KV cache below batch × max model length fails the job with kind `resource` and the KV-capacity line as evidence, and so does an engine that exits at start out of GPU memory (its out-of-memory line as evidence); only such failures move a workload to more GPUs. At high load a small KV cache is a warning and the engine queues the rest of the batch.
- **Release protocol** (REF-1): after each batch, each request is released as `/io/proofs/req-<i>/outputs.json` (`request_index`, `batch`, `token_ids`), under a temporary name then renamed. The outputs are kept for audit and never compared with a system's outputs (SRV-4).
- **Sizing** (`sizing.py`, grade projected, never published): the first GPU count to try, from the record's file bytes and shape and a profile's device memory; it orders the attempts and decides nothing.
- **Image.** `Dockerfile`, `FROM` the engine image by digest, with an empty `inputs.lock` (the engine image holds everything production serving runs). The image pinned in `system.yaml` was built from `2dacdc85` for plain serving; its baked `system.yaml` is not this one, so the runner refuses a job on it until the images workflow rebuilds it and the pin moves (RFC-0014 B7). The package `ghcr.io/ai-verification-observatory/ref-serve` was not anonymously pullable on 2026-11-09 (RFC-0015 Q6), so Hugging Face jobs run the development install (`dev_install.py`, docs/runbooks/hf-jobs.md §Production serving).
- **Tests** (`tests/`, CPU, INV-ADAPTER-9): the checks before the engine, the recorded command, output lengths, the KV-capacity rule, the resolved-configuration comparison, the release protocol against captured outputs (`tests/fixtures/README.md`), and the sizing arithmetic.

## Engine

- vLLM v0.32.0, released 2026-10-18, source commit `5df63a7203cdb9328d824a27b682e77c7b9928be`, image `docker.io/vllm/vllm-openai@sha256:befccf0e7e4089aa23926bb6f887a85c0d46c2a99e6de5c5ffdf5cb7957c5b34` (manifest list). Chosen by RFC-0015 Q1's default rule: the newest release meeting the constraint on 2026-11-04; on 2026-11-09 the GitHub releases API still listed v0.32.0 as the newest release (v0.33.0rc3 is a release candidate).
- `ref-recompute` only: `vllm-gguf-plugin` v0.0.5, published by the vLLM project, installed into the `ref-recompute` image and pinned in its `inputs.lock` (#138). In v0.32.0 GGUF support lives in that plugin ([gguf.md](https://github.com/vllm-project/vllm/blob/v0.32.0/docs/features/quantization/gguf.md)).
- No engine source change (AGENTS.md rule 1).

## Recompute (`ref-recompute`)

`ref-recompute` builds its engine as before 2026-11-09: the `LLM` class from the engine's own command-line parser with its `system.yaml` options, on the workload's own files (RFC-0015 PM-0 to PM-4 govern it).

### Precision per workload (RFC-0015 §Precision matching)

Recompute loads only the workload's pinned files (PM-0). The workloads (#49) must state these `precision.served` values: `W8A8` (integer) for the SASH workloads, `UD-Q4_K_XL` for the Maverick workloads.

| Workload | `precision_used` | Why |
|---|---|---|
| `sash-l31-8b-c4096`, `sash-l31-8b-c1024` | `fp8`, declared substitution | v0.32.0 serves INT8 W8A8 only from a checkpoint pre-quantized with llm-compressor ([int8_w8a8.md](https://github.com/vllm-project/vllm/blob/v0.32.0/docs/features/quantization/llm_compressor/int8_w8a8.md)), which holds other weights (PM-0). FP8 W8A8 is quantized at load time from the pinned BF16 files ([online.md](https://github.com/vllm-project/vllm/blob/v0.32.0/docs/features/quantization/online.md), `fp8_per_tensor`, Hopper listed), with the same bit widths (PM-4). Every quantity of these rows carries `quality.precision_substituted: true`. |
| `fp-maverick-w1024-b1`, `fp-maverick-w1024-b24` | `UD-Q4_K_XL`, the pinned GGUF files | Loaded through the plugin. Its README does not list Llama 4 among its tested families, and the weights (5 files of 33 GB to 50 GB each in the Hub listing at the pinned revision) exceed the GPU's 80 GB, so a recorded failure is the expected outcome (RFC-0015 §Feasibility on the profile). |


### Engine options

Every option is an engine argument of v0.32.0 ([engine_args.md](https://github.com/vllm-project/vllm/blob/v0.32.0/docs/configuration/engine_args.md), generated from [`vllm/engine/arg_utils.py`](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/engine/arg_utils.py)), listed verbatim per workload in `systems/ref-recompute/system.yaml`.

| Option | Value | Why |
|---|---|---|
| `--quantization` | `fp8_per_tensor` | SASH workloads only: PM-4 above. |
| `--max-model-len` | prompt plus output tokens plus one (4,609, 1,089 or 1,026) | Recompute feeds prompt plus claimed output as its prompt, and the engine refuses a prompt that leaves no room for the one token it generates. |
| `--max-num-seqs` | 1 | one request at a time (RC-2) |
| `--cpu-offload-gb` | 160 | Maverick only: the part of the weights that cannot sit in GPU memory, kept in host memory. |
| `--skip-tokenizer-init` | | The harness sends token ids and reads token ids, so the engine needs no tokenizer. This also avoids converting a tokenizer out of the GGUF files. |

### Teacher-forced argmax (RFC-0015 Q3)

`ref-recompute` submits prompt plus claimed output as one prompt of token ids with `SamplingParams(prompt_logprobs=1, max_tokens=1)` ([`sampling_params.py`](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/sampling_params.py#L347-L349)). At each position the engine returns the top-1 token of `torch.topk` over the log-probabilities ([`Sampler.gather_logprobs`](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/v1/sample/sampler.py#L312-L337)). That token is the argmax; ties follow `torch.topk`'s order.


## Stored attempts (RFC-0015 SRV-10)

The `ref-serve` runs in `results/v0.1` (2026-11-05) were plain serving on the system rows' profile, `prover-h100-hosted`, from the workloads' files: 12 completed SASH-workload runs (FP8 at load, PM-4) and 8 failed Maverick runs. They stay as recorded and pair with no system row.
