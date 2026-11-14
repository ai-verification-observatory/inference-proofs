# ref-fidelity: the fidelity reference

The reference of [RFC-0018 §Fidelity](../../rfcs/0018-level-1-ladder.md#fidelity) (FI-1, FI-2, FI-7): each rung's publisher's 16-bit release run greedily in llama.cpp, the controls built from it, and llama.cpp's KL divergence of each control against it. It is a reference job, not a row. `iproofs fidelity run` drives it; `iproofs fidelity score` (CPU) turns its records and the rows' counted sessions into `fidelity.json` (`harness/src/iproofs/fidelity.py`, schema `fidelity/1`).

## Engine

- llama.cpp v0.9.0, the newest non-prerelease on the GitHub releases page on 2026-11-10 (published 2026-11-04), commit `cd959bae99ff4bed22bef2604f45241c09bbb8c8` (the annotated tag `v0.9.0` points at it). It is the commit `iproofs.gguf` already follows. `inputs.lock` holds the sha256 of `git archive --format=tar HEAD`, which the image build recomputes.
- Built from source in the image (`Dockerfile`), following upstream's [.devops/cuda.Dockerfile](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/.devops/cuda.Dockerfile) at the pin: `nvidia/cuda:12.8.1-devel-ubuntu24.04` by digest, `GGML_CUDA=ON`, `GGML_NATIVE=OFF`, `--allow-shlib-undefined`. Changed from upstream's file, and why: compute capability 9.0 only (H200), static libraries, the three programs the entrypoint runs (`llama-server`, `llama-quantize`, `llama-perplexity`), no web UI and no HTTPS (`LLAMA_BUILD_UI=OFF`, `LLAMA_USE_PREBUILT_UI=OFF`, which would download at configure time, `LLAMA_OPENSSL=OFF`).
- The converter's Python packages (`convert-requirements.txt`): upstream's `requirements/requirements-convert_hf_to_gguf.txt` at the pin resolved for CPython 3.12 on x86_64 Linux, every file by hash (torch 2.11.0 CPU, transformers 4.57.6, numpy 2.2.6). The `gguf` package is the source tree's own `gguf-py`, which the converter puts on its path.
- No source change (AGENTS.md rule 1).

## What a job does

`iproofs fidelity run --level L1 --rung R --release v1.0 --prompts-dir DIR --gpus 0,...` makes one `info` call, then one `prove` call per model source, each with the same `/io` directory:

| Call | `/models` | Builds and runs |
|---|---|---|
| `reference` | the rung's 16-bit release (the serving record's files for the 8B rung; `--reference-dir` for Maverick) | the reference, then every control the level builds from it |
| `other_model` | `--other-model-dir`, the smaller model of the same publisher | the `other_model` control |
| `file` (per `--row-gguf SYSTEM`) | the row's workload files, fetched and checked | KL only, on the file the system commits |

In each call:

1. **Convert** (FI-1): `python3 convert_hf_to_gguf.py /models --outtype bf16 --outfile /io/work/reference.gguf`, offline (`HF_HUB_OFFLINE=1`).
2. **Replies** (FI-1, FI-2): `llama-server -m <file> --host 127.0.0.1 --port <free> -c <slots x 1,088> -np <slots> -ngl 999 --cache-ram 0 --no-webui`, then one `/completion` request per prompt ([tools/server/README.md](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md)):
   - `prompt` the 512 token ids. A token-id prompt gets no BOS token added (README §POST /completion).
   - `n_predict` the tokens still wanted, `return_tokens` true: the reply is the response's `tokens`. A longer reply (README: `n_predict` "may exceed the set limit slightly" at a partial character) is cut at 512.
   - `samplers` `["temperature"]` with `temperature` 0 and `n_probs` 0: llama.cpp's greedy sampler ([common/sampling.cpp L403 to L406](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/common/sampling.cpp#L403-L406)).
   - End tokens (RFC-0018 §Terms, Request): an end-of-generation token chosen greedily is part of the reply and generation goes on. `ignore_eos` stays false, since llama.cpp's sets every end token's logit bias to minus infinity ([server-schema.cpp L442 to L452](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/server-schema.cpp#L442-L452)), which would forbid the token. The server stops after an end token, returns it as the last of `tokens` with `stop_type` `eos` ([server-context.cpp L2142 to L2145, L2254 to L2256](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/server-context.cpp#L2142-L2145)); the entrypoint then sends prompt + reply so far as a new prompt for the remaining count, as often as needed (`greedy_reply`). Each reply's number of continuations is recorded in `status.json` (`continuations`, one count per prompt). A stop of any other kind short of 512 tokens fails the control. A continued reply is evaluated from an empty cache over the longer prompt, so its later tokens can differ in the last bits from an uninterrupted generation.
   - `cache_prompt` false and `--cache-ram 0`: every prompt is evaluated from an empty cache.
   - `-ngl 999`: every layer on the GPUs; llama.cpp splits layers over the visible GPUs (its default `--split-mode layer`).
   - Why `llama-server` and not `llama-cli`: at the pin the server takes a prompt as token ids and returns token ids (`return_tokens`); `llama-cli` and `llama-completion` take text, which would be tokenized again.
   - `--slots` (default 1) sets `-np`. Replies of one rung must all come from one setting; the honest control `reference-2` is the reference rerun under the same setting.
3. **KL** (FI-7): the KL texts (token windows) are written as text by the server's `/detokenize` and joined by blank lines; `llama-perplexity -m reference.gguf -f kl.txt -c 512 --chunks 64 --kl-divergence-base kl-base.kld` tokenizes that text again and stores the reference's logits, then `llama-perplexity -m <file> -c 512 --kl-divergence-base kl-base.kld --kl-divergence` for each control and row file. The figure is the `Mean    KLD:` line, nats per token, over the second half of each 512-token chunk ([tools/perplexity/README.md](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/perplexity/README.md); the stored base logits are 16-bit). It never gates.
4. Each control's model file is deleted once its replies and KL are written; the reference GGUF at the end of its call.

### Controls (FI-2)

| Recipe | Built by |
|---|---|
| `rerun` | the reference GGUF, a second server start |
| `quantize` | `llama-quantize reference.gguf <id>.gguf <TYPE>` |
| `drop_blocks` | `drop_blocks.py reference.gguf <id>.gguf --every 4`, then read back with the source tree's `gguf` package |
| `other_model` | its own conversion, as step 1 |

`drop_blocks.py` removes 1/4 of the transformer blocks, renumbers the rest, sets `<arch>.block_count` and filters every per-block metadata array. A model that interleaves mixture-of-experts blocks (`<arch>.interleave_moe_layer_step` s > 1; Llama 4 Maverick has s = 2) loses whole groups of s consecutive blocks, since llama.cpp reads block i as a mixture-of-experts block when (i + 1) is a multiple of s ([src/models/llama4.cpp L62](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/src/models/llama4.cpp#L62)) and a single removal would leave a copy that does not load: blocks 3, 7, ..., 31 of Llama 3.1 8B (8 of 32); pairs (6, 7), (14, 15), ..., (46, 47) of Maverick (12 of 48). The module uses the standard library only, so its CPU test needs no llama.cpp.

### Records

The image writes under `/io`: `fidelity/replies/<id>.jsonl` (one reply per line, prompt order; `reference.jsonl` for FI-1), `fidelity/kl/<id>.log`, `fidelity/logs/`, `fidelity/status.json` (each call's and control's outcome and each reply's continuation count; a failed control keeps its cause and the call goes on), and `commands.jsonl`. `iproofs fidelity run` copies them to `results/<release>/fidelity/<rung>/` (logs with host paths redacted) and writes `fidelity-run.json` there (schema `fidelity-run/1`): level digest, engine commit and image, adapter and harness commits, prompt digests, GPUs, slots, the reference's files with their sha256, and every call's exit code, last lines and phases.

## Teacher-forced pass (RFC-0018 FI-10 to FI-13)

With `teacher_forced` in the job, a call builds the same model files and generates no reply: each prompt followed by the stored reference reply is scored position by position. llama.cpp at the pin has no tool that prints the logits of given token ids (`llama-perplexity` reads text, and text tokenized again is not the same ids), so the pass uses `llama-server`, as documented in its [README](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md): one `/completion` request per reply position, whose `prompt` is the array of token ids up to that position, with `n_predict` 1, the greedy settings of the reply run, `cache_prompt` true and `id_slot` fixed, so the 512-token prompt is evaluated once in a batch and each later position evaluates one token, as greedy generation does. The generated token (`tokens`) is the model's top token at the position. With `n_probs` 256 the response lists "the probabilities of top N tokens for each generated token", computed "via a simple softmax of the logits without considering any other sampler settings".

One limit of the server at the pin: it returns no list for a generated token that ends inside a UTF-8 character ([server-context.cpp L2149-L2177](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/server-context.cpp#L2149-L2177), `add_token` runs only on a complete character). The top token is still returned; the position is counted in `positions_without_list` and left out of that engine's KL (FI-12).

Outputs: `/io/fidelity/teacher-forced/top/<id>.jsonl` and `raw/<id>/<prompt>.topk`. No KL tool runs and no reply file is written in this mode.

Measured on Llama 3.1 8B (1 H200, one slot, `results/v1.0/teacher-forced/llama-3.1-8b/run-llama.cpp.json`, n = 1 run): a pass over the 15 prompts (7,680 positions, each with its list of 256) took 73 to 104 s with the control's build and load, about 9 ms per position for the reference; 1 position of 61,440 came back without a list (in the `drop_blocks` control). The reference's own pass gives its stored reply at every position, as does its rerun: at one slot the engine repeats itself.

Measured on Llama 4 Maverick (4 H200, 16 slots, the Q8_0 and Q4_K_M controls, each as three runs of 120 prompts, `results/v1.0/teacher-forced/llama-4-maverick/run-controls-*.json`): the pass ran at 6.7 positions per second, 2.5 s per request, so 61,440 positions took about 2 h 35 min per run after a build and load of 9 to 20 min. The server's logs show 6 prompt tokens evaluated per request at 1.5 to 2.5 s, while the same server evaluated a 512-token prompt at 347 tokens per second; on Llama 3.1 8B a request evaluated 1 token (5 ms at one slot; 26 ms at 16 slots, with or without `GGML_CUDA_DISABLE_GRAPHS=1`, n = 1 run each, 2026-11-14).

The cause, from a probe of 2026-11-14 (Q4_K_M on 4 H200, 16 slots, 16 prompts and 10 to 12 positions each, a second server started by hand on the file the job built; a diagnostic, not a pass): llama.cpp at the pin gives this model a sliding-window attention cache, which cannot drop only its last token, so a request that replaces one token is not a one-token step.

| Server option | Prompt tokens evaluated per request | Request, median | Positions per second |
|---|---|---|---|
| default | 6 | 1,543 ms | 10.4 |
| `--ctx-checkpoints 0` | 519 to 521 (the whole prompt again) | 975 ms | 15.6 |
| `--swa-full` | 1 | 90 ms | 168 |

`--swa-full` is documented ("use full-size SWA cache", [tools/server/README.md](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md)); the default and `--swa-full` rows were each measured twice in that job with the same result (n = 2). With it a pass over Maverick's 360 prompts would take about 18 min in place of about 7 h 40 min. Not yet checked: that the option leaves the top tokens and log-probabilities unchanged (the probe's outputs were not kept). The stored Q8_0 and Q4_K_M passes ran with the default cache; a pass with `--swa-full` should first repeat a stored shard and be compared with it. No position came back without a list. An earlier run of the whole Q4_K_M pass in one job was stopped at its deadline and stored nothing (`not-stored.json`).

## Resources

- Llama 3.1 8B: 16 GB at 16 bits, one H200; a few minutes per control for 15 prompts.
- Llama 4 Maverick: about 800 GB at 16 bits, so the 16-bit reference needs at least 6 H200 (141 GB each) before its KV cache, and `/io/work` must hold the 16-bit GGUF and the largest control at once (about 1.4 TB), beside the 16-bit release itself (about 800 GB). Llama 4 Scout at 16 bits is about 220 GB (two H200).

## Tests

`tests/` (CPU): `drop_blocks.py` on a tiny synthetic GGUF, read back by the harness's own GGUF reader; the end-token continuation loop against a scripted server; one `reference` call against fake llama.cpp tools (files built, replies written, a failed control recorded and the call going on, built files deleted, `out.json` valid); the request fields; the Dockerfile rules (RFC-0014 B1 to B3).
