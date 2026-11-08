# ref-serve-gguf: plain serving of the Maverick workloads on llama.cpp

The plain-serving reference of [RFC-0015](../../rfcs/0015-reference-rows.md) for `fp-maverick-w1024-b1` and `fp-maverick-w1024-b24`, on llama.cpp's `llama-server` (SRV-6), as a second adapter with `reference_role: serve` (SRV-7). It runs on the profile of the FlashProve rows it serves, so D-OVERHEAD-S divides two rates of one profile. The SASH workloads keep `ref-serve` (vLLM, [`../ref-serve/README.md`](../ref-serve/README.md)).

Status on 2026-11-08: the adapter, its CPU tests and the computed starting placement exist; no GPU run has been made, so nothing on this page is a measurement, and no adapter image is pinned yet.

## The adapter

- **Steps** (RFC-0015 §Steps per job): `info` and `setup` as RFC-0005 defines them; `prove` serves the workload. The harness skips `commit` and `verify`, and the entrypoint refuses them.
- **`prove`** starts `llama-server` once: `-m` the first of the five pinned GGUF files (the server loads the other split files from it), `--host 127.0.0.1 --port <a free port>` for the adapter's own requests, then the workload's `engine_args` from `system.yaml`, verbatim (SRV-3). It waits until `/health` answers 200, then sends each batch's requests to `/completion` at once, one per slot (SRV-1), waits for the whole batch, releases it, and goes on. It stops the server at the end.
- **Release protocol** (REF-1): after each batch, each request of that batch is released as `/io/proofs/req-<i>/outputs.json` (`request_index`, `batch`, `token_ids`), written under a temporary name and renamed, as in `ref-serve`. `prove.steady` runs from the first to the last batch release; server start, model load and any CUDA JIT compilation before the first release are in `prove.session` only.
- **Commands:** `/io/commands.jsonl` records the server command line (with the `/models` path), its working directory and its exit code. The server runs in `/app`, the image's `WORKDIR`, where it finds its own libraries (`libllama-server-impl.so` and the ggml backends; from another directory it exits 127 at start).
- **Kept for audit** in the job's `/io` (kept in the run directory with `--keep-io`): `responses.jsonl`, each request body and the server's response body, one line per request, written before any response is checked; and `llama-server.log`, the server's own output. A failed step prints the log's last 40 lines to stderr, which the harness records.
- **Server failures:** a server that exits while loading fails the step with its exit code. A server that dies or stops answering during a request (an allocation failure on the first prompt, for one) gives that request no response: the whole batch is still written to `responses.jsonl`, nothing of it is released, the step fails naming the request and the server's exit code, and the log's last lines (where the allocation error is) go to stderr. Every request has a socket timeout, a guard and not a measurement: 30 s for `/health`, 3,600 s for `/completion` (an assumption, far above one request of 1,024 prompt tokens and 1 output token).
- **`info`** reports the profile `prover-h200`: the v0.1 reference GPU, one H200 of at least 140,000 MiB (`reference/v0.1.yaml`), the profile of the FlashProve rows this row serves; `prover-h200-hosted`, its hosted form, has the same GPU minimum.
- **Environment:** the server gets the image's environment without any `LLAMA_ARG_*` variable (the engine image sets `LLAMA_ARG_HOST=0.0.0.0` and `LLAMA_ARG_PORT=8080`; the pinned server reads such variables as options), so the recorded command line is the whole configuration. `HOME` and `CUDA_CACHE_PATH` point under `/tmp/ref-serve-gguf`, writable under a read-only root.

## Engine

- llama.cpp v0.9.0, published 2026-11-04, commit `cd959bae99ff4bed22bef2604f45241c09bbb8c8` (build `b12110`), image `ghcr.io/ggml-org/llama.cpp:server-cuda-b12110@sha256:a2963b4817f03eea7e0d6065ea576252322792441ef97aaae178b924520547d6` (an OCI index; its `linux/amd64` manifest is `sha256:ac11e113c61a57b0b0b86414aa8e1b61b9512dcedf8083c5fdedb35b379342cf`, config `sha256:5044f054636e8e3b5e38f725a7944ae584831cb9dad5fed7962e4a0dfc71ebf0`). Pinned by RFC-0015 SRV-6. No engine source change (AGENTS.md rule 1).
- What the image holds, read on 2026-11-08 by pulling it (`linux/amd64`): Ubuntu 24.04.1; the CUDA 12.8.1 runtime libraries (`CUDA_VERSION=12.8.1`, `NVIDIA_REQUIRE_CUDA=cuda>=12.8`); `ENTRYPOINT ["/app/llama-server"]`, the server and its libraries in `/app`, `libggml-cuda.so` among them; `ENV LLAMA_ARG_HOST=0.0.0.0 LLAMA_ARG_PORT=8080`; no `USER` (it runs as root); `python3` 3.12.3 with its standard library, but no PyYAML, no `pip`, no `ensurepip`, no `git` and no `uv`; `curl`, `bash`, `setpriv` and `taskset`.
- CUDA architectures in `/app/libggml-cuda.so`, read from its `.nv_fatbin` section (147 kernels each): machine code (SASS) for `sm_86`, `sm_89` and `sm_120`, and PTX for `compute_50`, `61`, `70`, `75`, `80` and `90`. There is no `sm_90` machine code: on an H200 or H100 (`sm_90`) the driver compiles the `compute_90` PTX when a kernel is first loaded. This is the upstream default list for a CUDA 12.8 build without `CMAKE_CUDA_ARCHITECTURES` ([ggml/src/ggml-cuda/CMakeLists.txt L43 to L65](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/ggml/src/ggml-cuda/CMakeLists.txt#L43-L65): `90-virtual`), which [.devops/cuda.Dockerfile](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/.devops/cuda.Dockerfile) uses (`CUDA_DOCKER_ARCH=default`). The compile time falls in `prove.session` (load and the server's warmup) and in the first batch, before the first release, so `prove.steady` excludes it; the first GPU run shows how long it takes. Each job starts with an empty cache (`/tmp` is fresh per call, RFC-0005), so no repetition starts warm.

## Precision (RFC-0015 §Precision matching)

`precision_used: UD-Q4_K_XL` for both workloads, with no substitution: the server loads the workload's five pinned GGUF files unchanged and serves the stored block formats (PM-0, PM-1). The pinned version names the files' architecture, `llama4` ([src/llama-arch.cpp L12](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/src/llama-arch.cpp#L12)).

## Engine options

Every option is in the pinned server's documentation, [tools/server/README.md](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md) (README below). They are listed verbatim per workload in `system.yaml` (SRV-3); everything else stays at its default (plain serving as documented).

| Option | Value | Documentation | Why |
|---|---|---|---|
| `-np` | the workload's batch size, 1 or 24 | [README L177](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md#L177) | one slot per request of a batch (SRV-1) |
| `--kv-unified` | | [README L169](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md#L169) | one KV pool shared by the slots |
| `--kv-unified-per-slot` | 1025 | [README L165](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md#L165) | 1,024 prompt tokens plus 1 output token per slot; without `-c` the pool is `-np` times this (SRV-6). The server refuses a prompt of as many tokens as the slot holds ([server-context.cpp L4081](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/server-context.cpp#L4081)), so 1,025 is the smallest that serves a 1,024-token prompt |
| `-ngl` | `all` | [README L85](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md#L85) | every layer on the GPU, except the routed experts `--n-cpu-moe` moves |
| `--n-cpu-moe` | N, 22 to start ([Sizing](#sizing-the-placement---n-cpu-moe-n)) | [README L82](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md#L82) | "keep the Mixture of Experts (MoE) weights of the first N layers in the CPU": the routed expert tensors of layers 0 to N-1 ([common/arg.cpp L2718 to L2726](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/common/arg.cpp#L2718-L2726), [common/common.h L1262 and L1274 to L1281](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/common/common.h#L1262-L1281)); `--cpu-moe` ([README L81](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md#L81)) if no N fits |
| `--fit` | `off` | [README L89](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md#L89) | the recorded options are the placement; the engine does not change unset options to fit at load time |

Transport, not configuration, added by the adapter in front of the options: `-m` ([README L100](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md#L100)), `--host 127.0.0.1` and `--port` ([README L193 to L194](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md#L193-L194); 127.0.0.1 is the documented default, which the image's `LLAMA_ARG_HOST` would otherwise replace).

## Requests (SRV-2, SRV-6)

One `POST /completion` per request ([README L493 onward](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md#L493)):

| Field | Value | Documentation | Why |
|---|---|---|---|
| `prompt` | the prompt's token ids | [L501 to L503](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md#L501-L503) | an array of numbers gets no BOS token (RFC-0003 generator rule 2) |
| `n_predict` | the workload's output tokens (1) | [L533](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md#L533) | SRV-2 |
| `temperature` | 0 | [L521](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md#L521) | with the default sampler order and `n_probs` 0 the pinned sampler is its greedy one ([common/sampling.cpp L403 to L406](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/common/sampling.cpp#L403-L406)) |
| `n_probs` | 0 | [L589](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md#L589) | as above |
| `repeat_penalty`, `presence_penalty`, `frequency_penalty` | 1.0, 0, 0 | [L551 to L557](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md#L551-L557) | the penalties sampler leaves the logits unchanged; the README states a `repeat_penalty` default of 1.1 and `common/common.h` 1.00, and the request does not depend on which applies |
| `cache_prompt` | false | [L597](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md#L597) | no request reuses another request's KV cache (default true) |
| `return_tokens` | true | [L599](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md#L599) | the generated token ids come back in `tokens`; a response field, no effect on decoding |
| `stream` | false | [L544](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md#L544) | one response per request (the default, stated) |

Checks on each response (fields of [L670 to L684](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md#L670-L684)); any other answer fails the step with the request's index, and nothing of that batch is released:

- HTTP 200 and a JSON object;
- `tokens` a list of token ids;
- `stop_type` `limit` with exactly `n_predict` tokens, or `eos` with 1 to `n_predict` tokens;
- `tokens_predicted` equal to the number of tokens;
- `tokens_evaluated` equal to the prompt's length: no BOS added and nothing cut.

`truncated` is recorded, not checked: with a slot of exactly prompt plus one token, the server sets it when it samples that one token ([server-context.cpp L2188 to L2195](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/server-context.cpp#L2188-L2195)), and that token is still the one greedy decoding gives.

## Sizing the placement (`--n-cpu-moe N`)

SRV-6: N is the smallest value with which the job runs on the profile, and finding it is a sizing step, not a measurement. The values below are computed by [`sizing.py`](sizing.py) from the tensor tables of the pinned files, which `iproofs.gguf` read from their headers on 2026-11-08 ([`tests/fixtures/maverick-tensors.json`](tests/fixtures/maverick-tensors.json), header metadata, no weights); a test checks that this table is the script's output.

The model: with `-ngl all` every tensor is on the GPU except the input embedding (`token_embd.weight`, 0.58 GB), which stays in host memory ([src/llama-model.cpp L1772 to L1774](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/src/llama-model.cpp#L1772-L1774)), and the routed experts of layers 0 to N-1. The files hold 48 layers; the 24 odd ones carry the 128 routed experts (`llama4.interleave_moe_layer_step` 2), 9.06 GB per layer for 15 of them and 9.73 GB for 9 (their `ffn_down_exps` is Q5_K, not Q4_K), 223.5 GB in all; the rest, attention, shared experts, the dense layers' feed-forward and the output layer, is 8.07 GB. An odd N places as the even N below it, so only even N are tried. The KV cache is f16 (the default), 8 KV heads of 128 for K and for V in each of 48 layers: 196,608 B per cell, counted for every layer and with the cells rounded up to 256, an upper bound.

The budget: the profile's `gpu.memory_mib_min`, 140,000 MiB (`reference/v0.1.yaml`, `prover-h200-hosted`), less the KV cache, less 8,192 MiB for compute buffers (an assumption, with room for an expert tensor held in host memory and copied to the GPU for a large batch, `--op-offload` on by default, [README L94](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md#L94)), 1,024 MiB for the CUDA context and libraries (an assumption) and 1,024 MiB of margin (the engine's own `--fit-target` default, [README L90](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md#L90)). Output of `python systems/ref-serve-gguf/sizing.py` (computed, not measured):

```
budget per job: 140,000 MiB of GPU memory
-np 1: KV cache at most 240 MiB; weights may use 129,520 MiB; start N = 22
-np 24: KV cache at most 4,656 MiB; weights may use 125,104 MiB; start N = 22

| N | GPU weights (MiB) | host weights (GB) | fits -np 1 | fits -np 24 |
|---|---|---|---|---|
| 14 | 159,053 | 65.3 | no | no |
| 16 | 150,413 | 74.4 | no | no |
| 18 | 141,773 | 83.5 | no | no |
| 20 | 133,133 | 92.5 | no | no |
| 22 | 124,493 | 101.6 | yes | yes |
| 24 | 115,853 | 110.6 | yes | yes |
| 26 | 107,213 | 119.7 | yes | yes |
| 28 | 98,573 | 128.8 | yes | yes |
| 30 | 89,933 | 137.8 | yes | yes |
```

So both workloads start at `--n-cpu-moe 22`: 11 of the 24 expert layers (101.0 GB) in host memory, the rest on the GPU. On `h200x2` the host has 512 GB (hf-jobs.md); the server maps the files (memory-mapped by default), so the host part is the page cache of the model files.

The procedure, one N at a time, each N its own `system.yaml` (SRV-6, SRV-3):

1. Each N tried is `system.yaml` at the commit the job checks out: the manifest of every run records `system.system_manifest_digest` and `adapter_commit`, which name the N. A change of N is a commit that changes `--n-cpu-moe` for that workload (and the comment at the top of `system.yaml`), and the table below gains a row. `prove` reads the options from the `system.yaml` inside the image, so with a pushed image the same commit also rebuilds the image and pins the new digest in `image`; the development install copies the checkout's `system.yaml`, so it needs nothing more. The runner checks that the server command line in `commands.jsonl` ends with the workload's `engine_args` at the run's commit and fails the run with kind `config` otherwise (RFC-0015 SRV-3), so a stale image never runs under another N's manifest.
2. The first run (N 22) reads the engine's own sizes in `llama-server.log` (the model, KV and compute buffer lines of the load log) and the run's `prove_gpu_memory_peak`. They replace the assumptions above for the next N, with the run named as their source.
3. If N runs, the next try is N - 2; if it fails for GPU memory (a failed run, kind `adapter`, with the allocation error in its last lines), N + 2, up to 48. The smallest N that ran is the configuration published. If N 48 fails, `--cpu-moe` is tried; NM-1 applies only after that fails too.
4. Every run is recorded as usual, failures included (RFC-0010, AGENTS.md rule 5). Runs of an N other than the final one never enter the published statistics: only runs of the image `system.yaml` pins at the release commit are eligible (RFC-0014 §Eligibility, `image_differs_from_system_yaml`), and the freeze counts NM-1 over the eligible runs only, so it sees the final configuration's runs, which matches "after `--cpu-moe` also fails". Development-install runs are never eligible (`digest_kind: config`).

| N | `fp-maverick-w1024-b1` | `fp-maverick-w1024-b24` |
|---|---|---|
| 22 | not run yet (computed start) | not run yet (computed start) |

## Image

`systems/ref-serve-gguf/Dockerfile`, built `FROM` the engine image by digest under the RFC-0014 rules (`docker build -f systems/ref-serve-gguf/Dockerfile systems`, see its header). The engine image has Python 3.12 without PyYAML or `pip`, and the entrypoint reads `system.yaml` with PyYAML, so the fetch stage downloads the PyYAML 6.0.3 wheel for CPython 3.12 listed in `inputs.lock` (the version and hash of the harness's `uv.lock`), and the build extracts it into `/opt/ref-serve-gguf/site` with `python3 -m zipfile` and imports it once. The images workflow builds and pushes it as `ghcr.io/ai-verification-observatory/ref-serve-gguf` (RFC-0014 B7); `system.yaml` then pins it in `image`.

**Development install** (no pushed image needed): [`dev_install.py`](dev_install.py) puts the same files at the same paths inside a container started from the engine image itself, from the checkout the job runs; Hugging Face Jobs uses it ([hf-jobs.md](../../docs/runbooks/hf-jobs.md#ref-serve-gguf-from-the-engine-image)). Before the weights, it checks the engine: `llama-server --version` must print the pinned build (`build 12110, commit cd959bae9`; the line goes to `image_inputs`' toolchains), and with the bound GPU given, the server run as uid 10001 with only that GPU visible must list exactly one CUDA device. Such a run records the image as `local/<the engine image reference>` with `digest_kind: config`, the adapter commit as the checkout's, and the engine image and the adapter files in `image_inputs`; it is never eligible for a release (RFC-0014 §Eligibility and §Development install).

## Tests

`systems/ref-serve-gguf/tests/` run on CPU (INV-ADAPTER-9), on synthetic inputs: the server command line, the request body, the checks on each response, the release protocol, and `prove` end to end against a stand-in server ([`tests/fake_llama_server.py`](tests/fake_llama_server.py), the same command line and HTTP endpoints, synthetic outputs; it refuses a batch whose requests do not arrive together; it can also exit while loading, abort with exit code 134 on the first request, add a BOS or answer HTTP 500). The sizing table is checked against `sizing.py`, and `sizing.py` against a hand-computed case. `dev_install.py` runs against a temporary `/opt` with a stand-in wheel: the Dockerfile's final-stage paths, the recorded inputs, and its refusals (another image, a wrong sha256, a caller other than root, a server of another build, a device list without exactly one CUDA device, against a stand-in server script).

One check outside the tests, on 2026-11-08: the image built from this Dockerfile ran `prove` for `fp-maverick-w1024-b24`'s options on CPU (`linux/amd64` under emulation, no GPU) against a 1.2 MB test model, not a workload model (`tinyllamas/stories260K.gguf` of `ggml-org/models`), with 48 prompts of 4 tokens. The pinned server accepted every option, logged `n_slots = 24, n_ctx_slot = 1025, kv_unified = 'true'`, and answered every request with the fields the checks read (`tokens_evaluated` 4: no BOS added to a token array). Nothing from that check is a fixture or a measurement.

## Capture

No server response has been captured yet. The replay tests of captured responses join the CPU tests after the first GPU run, from what that run saves; no capture is written by hand.

What the first GPU run saves (hf-jobs.md runs the development run with `--keep-io`, and the job uploads the run directory, `io/` included, to the bucket; on a docker host, pass `--keep-io`): the run directory's `io/` holds `prompts.jsonl`, `responses.jsonl` (every request body and the server's response body), `llama-server.log`, `commands.jsonl`, `prove.out.json` and `proofs/req-<i>/outputs.json`; the job uploads the run directory to the bucket. To make the fixture, in a pull request:

1. Copy into `systems/ref-serve-gguf/tests/fixtures/capture/`: `prompts.jsonl`, `responses.jsonl`, `prove.out.json` as `out.json`, `commands.jsonl` and `proofs/`. In `responses.jsonl`, drop the response fields `prompt` and `content` (the prompt and output as text, which the adapter does not read) and keep every other field, `generation_settings` included.
2. Write `capture/README.md` as `../ref-serve/tests/fixtures/capture/README.md` does: the date, the flavor and GPU, the driver, the image (engine image plus adapter commit), the workload, N, the bucket folder it came from, and that nothing in it is a measurement.
3. Add the replay test: each captured response body through `output_tokens` and the release protocol gives the captured `out.json` proofs and releases; and the captured `generation_settings` show the request fields of [Requests](#requests-srv-2-srv-6) as the server applied them (temperature 0, the penalties neutral, `n_probs` 0).

## Open points

- **CPU threads.** The server's default thread count is the host's physical core count read from `/sys` ([common/common.cpp L82 to L107 and L206 to L248](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/common/common.cpp#L206-L248)), not the CPUs the job is bound to (15 on `prover-h200-hosted`). Routed experts in host memory are computed on those threads, so on a container with more cores than bound CPUs the default may run more threads than CPUs. `-t` is not set, because SRV-6 lists the options and leaves the rest at their defaults. Too many threads on the bound CPUs would slow only this row, which makes D-OVERHEAD-S smaller, in the provers' favour. Pinning `-t 15 -tb 15` (the profile's prover CPUs) under SRV-3's "chosen to make the workload fit", or amending SRV-6, is an owner decision to take before any run whose rates are published. Until then: the development run's `llama-server.log` shows the thread count the server chose (read it there), and that run's rates are not for publication (a development install is never eligible anyway).
