# ref-serve and ref-recompute: engine pin

The reference systems of [RFC-0015](../../rfcs/0015-reference-rows.md): plain serving (`ref-serve`) and recompute by a verifier holding the weights (`ref-recompute`, #139). Both run the same pinned engine. This page records the engine pin, the precision used per workload and every engine option, each with the engine's documentation at the pinned version, and how the `ref-serve` adapter works.

## The ref-serve adapter

- **Steps** (RFC-0015 §Steps per job): `info` and `setup` as RFC-0005 defines them; `prove` serves the workload. The harness skips `commit` and `verify`, and the entrypoint refuses them.
- **`prove`** loads the engine once, from its own command-line parser, with the workload's `engine_args` from `system.yaml`, verbatim (SRV-3). It serves the prompts in order, in batches of the workload's `batch_size` for `batches_per_session` batches (SRV-1). Decoding is greedy, with `max_tokens` equal to the workload's `output_tokens` (SRV-2). Prompts and outputs are token ids.
- **Release protocol** (REF-1): after each batch, each request of that batch is released as `/io/proofs/req-<i>/outputs.json` (`request_index`, `batch`, `token_ids`), written under a temporary name and renamed. Releases are per request so the harness counts tokens with the per-request rule of the system the row serves (REF-3); they happen at batch boundaries, so `prove.steady` runs from the first to the last batch. The outputs are kept for audit and never compared with a system's outputs (SRV-4).
- **Commands:** the engine runs inside the adapter process, so `/io/commands.jsonl` records one line, `vllm.LLM --model /models` followed by the options.
- **Image:** `systems/ref-serve/Dockerfile`, built `FROM` the engine image by digest under the RFC-0014 rules (`docker build -f systems/ref-serve/Dockerfile systems`, see its header). Its fetch stage downloads the plugin wheel listed in `inputs.lock`. The image is pushed to the project registry and pinned in `system.yaml` `image` (RFC-0014 B7) by the first build on a GPU host.
- **Tests:** `systems/ref-serve/tests/` run on CPU (INV-ADAPTER-9). They replay engine outputs captured once on a GPU host (`tests/fixtures/capture/`, with its own README) through the outputs builder and the release protocol.

## Engine

- vLLM v0.32.0, released 2026-10-18, source commit `5df63a7203cdb9328d824a27b682e77c7b9928be`, image `docker.io/vllm/vllm-openai@sha256:befccf0e7e4089aa23926bb6f887a85c0d46c2a99e6de5c5ffdf5cb7957c5b34` (manifest list). Chosen by RFC-0015 Q1's default rule: the newest release meeting the constraint on 2026-11-04, the date this pull request opened. v0.33.0rc3 is a release candidate.
- Maverick only: `vllm-gguf-plugin` v0.0.5, published by the vLLM project, installed into the adapter image and pinned in its `inputs.lock` (#138). In v0.32.0 GGUF support lives in that plugin ([gguf.md](https://github.com/vllm-project/vllm/blob/v0.32.0/docs/features/quantization/gguf.md)).
- No engine source change (AGENTS.md rule 1).

## Precision per workload (RFC-0015 §Precision matching)

The reference loads only the workload's pinned files (PM-0). The workloads (#49) must state these `precision.served` values: `W8A8` (integer) for the SASH workloads, `UD-Q4_K_XL` for the Maverick workloads.

| Workload | `precision_used` | Why |
|---|---|---|
| `sash-l31-8b-c4096`, `sash-l31-8b-c1024` | `fp8`, declared substitution | v0.32.0 serves INT8 W8A8 only from a checkpoint pre-quantized with llm-compressor ([int8_w8a8.md](https://github.com/vllm-project/vllm/blob/v0.32.0/docs/features/quantization/llm_compressor/int8_w8a8.md)), which holds other weights (PM-0). FP8 W8A8 is quantized at load time from the pinned BF16 files ([online.md](https://github.com/vllm-project/vllm/blob/v0.32.0/docs/features/quantization/online.md), `fp8_per_tensor`, Hopper listed), with the same bit widths (PM-4). Every quantity of these rows carries `quality.precision_substituted: true`. |
| `fp-maverick-w1024-b1`, `fp-maverick-w1024-b24` | `UD-Q4_K_XL`, the pinned GGUF files | Loaded through the plugin. Its README does not list Llama 4 among its tested families, and the weights (5 files of 33 GB to 50 GB each in the Hub listing at the pinned revision) exceed the GPU's 80 GB, so a recorded failure and NM-1 is the expected outcome (RFC-0015 §Feasibility). |

## Engine options

Every option is an engine argument of v0.32.0 ([engine_args.md](https://github.com/vllm-project/vllm/blob/v0.32.0/docs/configuration/engine_args.md), generated from [`vllm/engine/arg_utils.py`](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/engine/arg_utils.py)). They are listed verbatim per workload in each `system.yaml` (SRV-3).

| Option | Value | Why |
|---|---|---|
| `--quantization` | `fp8_per_tensor` | SASH workloads only: PM-4 above. |
| `--max-model-len` | `ref-serve`: prompt plus output tokens (4,608, 1,088 or 1,025); `ref-recompute`: one more (4,609, 1,089 or 1,026) | the workload's sequence, nothing longer. Recompute feeds prompt plus claimed output as its prompt, and the engine refuses a prompt that leaves no room for the one token it must generate (`VLLMValidationError`, found on the GPU capture). |
| `--max-num-seqs` | the workload's batch size for `ref-serve` (SRV-1); 1 for `ref-recompute` (RC-2) | |
| `--cpu-offload-gb` | 160 | Maverick only: the part of the weights that cannot sit in GPU memory, kept in host memory (the profile has at least 330 GiB). |
| `--skip-tokenizer-init` | | The harness sends token ids and reads token ids, so the engine needs no tokenizer. This also avoids converting a tokenizer out of the GGUF files. |

## Teacher-forced argmax (RFC-0015 Q3)

`ref-recompute` submits prompt plus claimed output as one prompt of token ids with `SamplingParams(prompt_logprobs=1, max_tokens=1)` ([`sampling_params.py`](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/sampling_params.py#L347-L349)). At each position the engine returns the top-1 token of `torch.topk` over the log-probabilities ([`Sampler.gather_logprobs`](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/v1/sample/sampler.py#L312-L337)). That token is the argmax; ties follow `torch.topk`'s order.
