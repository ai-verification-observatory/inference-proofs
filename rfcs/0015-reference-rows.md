# RFC-0015: Reference rows: production serving and recompute

- Status: Draft
- Authors: AbdelStark
- Created: 2026-11-03
- Target milestone: v0.1-beta
- Requires: RFC-0003, RFC-0004, RFC-0005, RFC-0006, RFC-0011
- Supersedes: none
- Discussion: pull request that introduces it

## Summary

Every native workload gets two reference rows: production serving, that is plain serving (the model served unproved) as providers run it (an optimised engine, the publisher's release precision, every weight in GPU memory, tensor parallel over the fewest GPUs of the proving system's GPU model that hold it), and recompute (a verifier holding the weights reruns the forward pass on the system rows' profile). Production serving gives the overhead factor in GPU-seconds per token (RFC-0004 D-OVERHEAD-S). Recompute answers what a proof buys over a party that simply holds the weights. Both are implemented as ordinary adapters (`systems/ref-serve`, `systems/ref-recompute`) under the RFC-0005 contract with `kind: reference`, so the harness, measurement and statistics are shared and nothing is special-cased except which steps run.

## Motivation

PRD §6 asks for "two reference rows per workload, so every proof cost reads against something": plain serving with vLLM, pinned, on the same model, precision and hardware, and naive recompute by a verifier holding the weights. A proving rate alone says nothing about cost relative to the work being proved; the overhead against production serving does (RFC-0004 D-OVERHEAD-S, in GPU-seconds per token since the amendment of 2026-11-09). Recompute also gives a second, independent check of the claimed outputs: FlashProve's claim card states that it proves the integer model, which differs from the 16-bit model's top token at some positions (RFC-0002 example residual), and readers need to see how often the claimed output agrees with a plain forward pass.

## Goals

- Recompute rows use the same workload ids, versions, prompts, shapes and profile as the system rows. Production-serving rows use the same workload ids, versions, prompts (replayed, SRV-8) and shapes, on a serving profile of the same GPU model (RFC-0006 R6).
- Tokens are counted with the same rule as the proving system's claim card coverage (RFC-0004 INV-TOK-1), so D-OVERHEAD-S divides like by like.
- Production serving runs a pinned engine on the publisher's release of the model at the precision the publisher releases for serving; the weights are pinned by an ungated byte-identical copy (SRV-6). Recompute precision substitutions are declared and flagged.
- Output agreement between recompute and each system's claimed outputs is reported as counts and a derived rate, separately from verdicts.
- A reference row that cannot run on the profile is recorded as such, and every metric that depends on it is null with a reason.

## Non-Goals

- Tuning the serving engine beyond its defaults and the options the workload shape requires (SRV-3). The reference is "production serving with the engine's defaults", not the maximum throughput the engine could reach with tuning.
- Decode-heavy serving profiles, latency under load, request arrival processes (no such workload in v0.1).
- Judging which output is correct when recompute and a system disagree. Agreement is reported; no verdict is changed.
- Recompute rows on profiles other than the system rows' profile.

## Proposed Design

### Reference systems

Two directories, each a normal adapter (RFC-0005) with `system.yaml` field `kind: reference` and `reference_role: serve | recompute`:

```
systems/ref-serve/       Dockerfile (engine image by digest), entrypoint, system.yaml, sizing.py, dev_install.py, README.md, tests/
systems/ref-recompute/   Dockerfile (same engine image by digest), entrypoint, system.yaml, README.md, tests/
```

Reference systems have no `claim.yaml` (they prove nothing) and no controls. A reference adapter's image is built `FROM` the engine image by digest, pushed like any release image (RFC-0014 B7) and pinned in `system.yaml` `image`; the `engine` field names the engine it builds on. A plugin published by the engine's own project counts as part of the engine pin when it is installed into the adapter image and pinned in its `inputs.lock` (RFC-0014 B2); the adapter README names it. The site shows them only as reference rows beside a workload's system rows, never as systems.

```yaml
# systems/ref-serve/system.yaml (shape)
schema: "system/1"
name: "ref-serve"
kind: "reference"
reference_role: "serve"
engine: {name: "vllm", version: "<pinned release>", image: "<repo>@sha256:<digest>"}
workloads:
  - id: "sash-l31-8b-c1024"
    load_point: "matched"                # matched | high (SRV-1)
    gpus: 1                              # the serving profile's gpu.count (SRV-6)
    precision_used: "BF16"               # the serving record's precision (SRV-6)
    precision_substitution: null         # always null for reference_role serve
    engine_args: ["--tensor-parallel-size", "1", "--max-model-len", "1088", "--max-num-seqs", "1"]  # SRV-3 allowlist
incremental_proofs: true
deterministic_proofs: false
forbidden_flags: []
```

### Steps per job

For `kind: reference` the runner (RFC-0010) runs `info`, `setup`, `prove`; it records `commit` and `verify` as `skipped`. Consequences in RFC-0004 terms: `commit_seconds` and the D-COMMIT-AMORT metrics are null with `null_reason: not_applicable`; `whole_wall` is null with `not_applicable` (there is no commit start event); `prove.session` and `prove.steady` are measured exactly as for a proving system.

- REF-1. The `prove` subcommand loads the engine once, processes the workload's requests in the workload's order, and after each batch writes one release directory `/io/proofs/<batch_id>/outputs.json` atomically (RFC-0005 rename contract). The release watcher (RFC-0011) timestamps these directories, so `prove.steady` (first to last batch release) excludes engine start-up and model load, and `prove.session` includes them, with the same boundaries as the proving systems.
- REF-2. Release directories of a reference system are called "outputs", not proofs, in every record and page. The harness computes no proof bytes for them.
- REF-3. Tokens per release are counted by the harness with the coverage rule of the system the reference row serves: for `window`, the window's positions; for `prompt_plus_output`, prompt plus output positions (RFC-0004 INV-TOK-1).

### Production serving (`ref-serve`)

Amendment of 2026-11-09 (owner decision). It replaces SRV-1 to SRV-7, including the amendment of 2026-11-08, and the rule that plain serving runs on the proving system's profile. Users ask how much overhead proving adds in normal conditions, the conditions in which providers serve the model. The figure built here follows how FlashProve builds its own published figure ([guide/performance.md L27](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/performance.md?plain=1#L27): stock vLLM, FP8, every weight in GPU memory, steady), and states its own conditions just as clearly.

- SRV-1. Load points. Each workload has two serving configurations, by `load_point`.
  - `matched`: batch size equal to the workload's `batch_size`. Batches per session: the workload's `batches_per_session`, or more at the same batch size until the steady scope is expected to last at least 60 s. The count is fixed per (workload, GPU count) in `system.yaml` as `batches_per_session_run`, set from the first capture, and printed in the conditions line. The extra prompts come from the same seeded generator, as at high load (SRV-8).
    - Sizing (Draft amendment of 2026-11-09). `batches_per_session_run` is computed, not typed: `iproofs serving size-session RUN_DIR` reads a completed matched capture of the (workload, GPU count). Seconds per steady batch are its `prove_steady_seconds` over its batches minus one (the steady scope starts at the first batch's last release, RFC-0004 INV-SCOPE-5). The steady batches are the smallest n with n × that time ≥ 120 s; the count is n + 1 (the first batch, outside the steady scope), and never below the workload's `batches_per_session`. The target is 120 s, twice the 60 s minimum, so a run up to twice as slow per batch as its capture still clears 60 s; the 60 s minimum for joining is unchanged. A capture without a steady scope (one batch) is refused (`config`): its only batch is released after engine start-up inside the same `prove` call, and the record does not timestamp the end of start-up, so the time per batch after start-up cannot be separated from start-up. The `system.yaml` comment names the capture's run id and the command.
    - Sizing capture (Draft amendment of 2026-11-09, resolving Q10). While a matched entry's `batches_per_session_run` is null, `iproofs run --system ref-serve ... --sizing-batches N` (the `hf-job.sh` step option `sizing=N`) serves N batches at the workload's batch size, N ≥ 2, so that the capture has a steady scope; `--prompts-from` replays as SRV-8 says (the first `prompts.count` prompts are the source run's). The runner refuses it (`config`, before any step) at the high load, for an entry whose count is set, below 2 batches, and for a system that is not production serving. The manifest records `workload.sizing_capture: true` and run.json the warning "sizing capture: it sizes batches_per_session_run and joins no overhead (RFC-0015 SRV-1)"; the run joins no overhead (RFC-0004 INV-DERIVE-2 (f)), whatever its steady length. `iproofs serving size-session` sizes it like any matched capture and prints `capture.sizing_capture`. N is chosen so the steady scope lasts clearly more than a second (the per-request round trip and the watcher's granularity then weigh little in the time per batch) while the job stays short: for `sash-l31-8b-c1024` at TP1, N = 50 (one request of 1,024 prompt tokens and 64 generated at batch 1 on one H200 is about 0.5 s, projected, never measured; so about 25 s of steady scope over 49 batches, projected; `docs/runbooks/hf-jobs.md` S1b).
  - `high`: a batch of the engine's default maximum sequence count on the profile's GPU (1,024 on a GPU of 70 GiB or more, in both usage contexts, [vllm/engine/arg_utils.py L2933 to L2942](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/engine/arg_utils.py#L2933-L2942)), with `--max-num-seqs` left at its default. Its batches per session are the larger of `batches_per_session` and 2. The engine admits as many of the batch as its cache holds and queues the rest, as a server under load does.
  - A serving run whose steady scope lasts under 60 s keeps its value, with the warning "steady scope under 60 s" in run.json, and joins neither D-OVERHEAD-S nor D-OVERHEAD-HIGH-S (RFC-0004 INV-DERIVE-2): a window that short is dominated by the per-batch request round trip and the release watcher's granularity. Serving runs require `mechanism: inotify` (RFC-0011 W-1), and a polled run fails `environment`.
  The load point is part of the configuration (RFC-0010 manifest `workload.load_point`).
- SRV-2. Greedy decoding (temperature 0), `max_tokens` equal to the workload's `output_tokens` (1 for next-token workloads), `ignore_eos` true ([sampling_params.py L331](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/sampling_params.py#L331-L333)), so every request decodes exactly the tokens the harness counts. A request returning another count is an `adapter` error.
- SRV-3. Engine options: the engine's defaults, plus only these three, listed verbatim in `system.yaml` per (workload, load point, GPU count) and documented at the pinned version:
  - `--tensor-parallel-size` (the serving profile's `gpu.count`);
  - `--max-model-len` (prompt plus output tokens);
  - `--max-num-seqs` (the batch size, `matched` only).
  The validator refuses any other option for `reference_role: serve` (an allowlist). That covers offload (`--cpu-offload-gb`, `--kv-offloading-*`), quantization, memory-fraction, `--language-model-only` (it sets every modality limit to 0, [config/multimodal.py L304 to L306](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/config/multimodal.py#L304-L306), which changes memory profiling and is not how a multimodal model is served; Q4) and `--skip-tokenizer-init` (the engine starts with its full default init, from Meta's own `tokenizer_config.json`; Q7). If the engine cannot load without one of these, that failure is recorded and put to the owner; no flag is admitted without an amendment.
  - The engine is built from the allowlisted flags alone (Q8 default: `vllm serve MODEL <flags>`; alternative: `LLM(model=..., tensor_parallel_size=..., max_model_len=..., max_num_seqs=...)`), never from a full `EngineArgs` field dump. Passing every `EngineArgs` field into the `LLM` class, as the adapter did before this amendment, runs neither that class's defaults nor the server's: `LLM.__init__` sets `disable_log_stats=True` only when the key is absent ([entrypoints/llm.py L226 to L227](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/entrypoints/llm.py#L226-L227)).
  - The adapter records the engine command in `/io/commands.jsonl`, and the runner checks that it ends with the `engine_args` of `system.yaml` at the run's commit. It also records the engine's resolved-configuration log line (the pinned version's start-up line that prints the engine config), and a CPU test requires that the resolved configuration differs from a stored default dump of the pinned version, in the same interface and usage context, only in the allowlisted fields and the fields the serving record's own files set (model path, served name, `dtype`, `quantization`, `quantization_config`); of these, `quantization` must be what the release's `config.json` states (`quantization_config.quant_method`, or none). The stored default is a shape fixture until the first capture replaces it, and no run is checked against it yet (Q9).
  - The adapter records the engine as it saw it run (`engine_observed` in `commands.jsonl`, copied to the manifest's `engine.observed`): the installed version, the image ENV's `VLLM_BUILD_COMMIT`, and the batched-token limit the engine logs at info level ("Chunked prefill is enabled with max_num_batched_tokens=N", [config/scheduler.py L307](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/config/scheduler.py#L307)). The pinned version logs the resolved `max_num_seqs` at debug level only ([engine/arg_utils.py L3182](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/engine/arg_utils.py#L3182)), and raising the log level is an engine variable SRV-3 refuses, so the high load's 1,024 sequences is read from the source, not observed. The default batched-token limit is the smaller of the usage context's default and `max_num_seqs × max_model_len` (L3167 to L3170), so a matched b1 run gets 1,025, not 8,192: the conditions line prints the observed value per load point.
  - Environment. The adapter records the engine process's `VLLM_*`, `NCCL_*`, `CUDA_*` and `TORCH_*` variables in `commands.jsonl`. It refuses the job (`config`, before the engine is built) when any of them is not set by the pinned image's own `ENV` (read from the image config by digest and recorded in `inputs.json`), except the ones the harness sets for binding (`CUDA_VISIBLE_DEVICES`, `CUDA_DEVICE_ORDER`), listed in the adapter. The development install applies the same check. FlashProve's RES-13 records that `VLLM_USE_V2_MODEL_RUNNER=1` changed its baseline rate, so such variables are engine options in all but name.
- SRV-4. Outputs are recorded (`outputs.json`: request index, batch, token ids) for audit; serving outputs are not compared with system outputs.
- SRV-5. Metrics: `rate_<S>`, `seconds_per_token_<S>`, `gpu_seconds_per_token_<S>`, GPU and host resources as RFC-0011 (GPU readings over every bound GPU). They feed D-OVERHEAD-S, D-OVERHEAD-HIGH-S and D-OVERHEAD-WARM (RFC-0004). The adapter's `prove.session` (RFC-0004 §Timing scopes) is its `prove` call from its start, before `vllm serve` is launched (the checks before the engine read files only), to the release of the last request's outputs: engine start (process start, weight load into GPU memory, compilation, CUDA graph capture) to the last token. Every run records it (`prove_session_seconds`, `gpu_seconds_per_token_prove.session`). D-OVERHEAD-WARM divides the prover's session by the matched `gpu_seconds_per_token_prove.steady`, serving warm (RFC-0004 INV-DERIVE-11).
- SRV-6. Production serving (owner decision of 2026-11-09).
  - **Engine.** vLLM, by the Q1 rule (v0.32.0 on 2026-11-04 and still on 2026-11-09, when the GitHub releases API listed v0.32.0 of 2026-10-18 as the newest release and v0.33.0rc3 as a release candidate; image `docker.io/vllm/vllm-openai@sha256:befccf0e7e4089aa23926bb6f887a85c0d46c2a99e6de5c5ffdf5cb7957c5b34`), with its defaults in the interface of Q8 (default: the OpenAI-compatible server, `vllm serve`, usage context `OPENAI_API_SERVER`, the path providers run). The two interfaces' defaults differ (on an H200, 8,192 batched tokens for the server against 16,384 for the `LLM` class, [engine/arg_utils.py L2933 to L2942](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/engine/arg_utils.py#L2933-L2942)), so the interface is printed in the conditions line. FlashProve's RES-13 at `9e2bdd8` ([limits-all-rows.tsv](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/docs/limits-all-rows.tsv)) compares the HTTP server with the Python interface "with tuned settings" and states that "the two differ in more than the interface"; it does not show that the interface caused the gap, and it is not cited as a reason for either choice.
  - **Weights.** The model publisher's own release, at the precision named per model by amendment. For later models the rule is: the release the publisher's documentation designates for serving, else its original release, copied from the publisher with a link, "not stated" where it is silent. The v0.1 choices:
    - Llama 4 Maverick: Meta's FP8 release, `meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8` at `94125d2bd83076b21eed33119525e29eaf3894f4` (owner decision of 2026-11-09). Meta's card at that revision, §Quantization ([README.md](https://huggingface.co/meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8/blob/94125d2bd83076b21eed33119525e29eaf3894f4/README.md)): "the Llama 4 Maverick model is released as both BF16 and FP8 quantized weights. The FP8 quantized weights fit on a single H100 DGX host while still maintaining quality." The card does not use the word "serving"; the designation is the owner's, on that text.
    - Llama 3.1 8B Instruct: Meta's release, `meta-llama/Llama-3.1-8B-Instruct` at `0e9e39f249a16976918f6564b8830bc894c89659`, BF16 (its safetensors' dtype; the card's example loads it as `torch.bfloat16`, [README.md](https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct/blob/0e9e39f249a16976918f6564b8830bc894c89659/README.md)). A precision for serving: not stated.
    - The mirror links of the serving record are the source of the files only, never of the precision statement.
    - The files are fetched from an ungated copy whose every pinned file is byte-identical to the publisher's at that revision. They are pinned in a serving record `workloads/serving/<id>.yaml` (`serving-model/1`, RFC-0012): source repository and revision, and per file the path, sha256, bytes and the publisher's git blob id. The identity rules are SM-1 to SM-3 (RFC-0014 §Model fetch). The record names its workloads, and that list is the only workload-to-record mapping; the loader checks that each listed workload exists and names a serve-role system, that no workload is named by two records, that every serve-role workload is named by one record, and that `vocab_size` equals the workload's.
    - The precision is the release's own, as its files state it. No substitution: PM-0 to PM-4 apply to `ref-recompute` only.
  - **Placement.** Every weight sits in GPU memory, tensor parallel over the fewest GPUs that hold the weights and the matched load's KV cache (batch × max model length), on a serving profile of the proving system's GPU model (RFC-0006 R6).
    - Sizing only orders the attempts (`systems/ref-serve/sizing.py`, grade projected, never published). The first count tried is the smallest count, among those that divide the model's attention and KV heads, whose weight bytes are below count × the reported device memory. It is confirmed at load: the adapter fails with `resource` when the engine reports fewer KV-cache tokens than the matched load needs, and records the engine's KV-capacity line as the evidence; an engine that exits at start with an out-of-memory error (torch's `OutOfMemoryError`, the engine's "No available memory for the cache blocks" or "larger than the available KV cache memory") fails `resource` with that line as the evidence.
    - A larger GPU count is tried after `resource` failures at count n with that recorded KV-capacity (or out-of-memory) evidence. An `adapter` failure is a bug to fix and rerun, never a reason to move. The release joins the smallest GPU count with a joinable run (RFC-0004 INV-DERIVE-2); the placement holds for both load points, and the smaller count's failures stay recorded.
  - **Scope.** `prove.steady` is the headline (the engine's load, compilation and CUDA graph capture fall before the first batch's last release, RFC-0004 INV-SCOPE-5). `prove.session` is recorded (SRV-5). For a system with no steady scope (SASH) the headline is D-OVERHEAD-WARM: the prover's session over this row's steady scope, printed with both scopes (RFC-0004 INV-DERIVE-11).
- SRV-7. One production-serving system per workload: `ref-serve`. A workload's `systems` names at most one system with `reference_role: serve` (loader check, `config`). A CI workload names none. Tables label the row `ref-serve` and print the engine, the GPU count and the serving release beside it.
- SRV-8. Prompts. A production-serving job replays a run of the system configuration it serves: `iproofs run --system ref-serve --workload W --profile P --load matched|high --prompts-from RUN_DIR`. Both sides process the same tokens only when the serving run's batch size and batch count equal the prover's.
  - Otherwise (high load, and a matched run with more batches, SRV-1) the prompt set is generated from the same seed with count B × batches. `corpus-window/1` draws offsets in sequence from one seeded generator, so its first `prompts.count` prompts are the source run's set. The manifest records `prompt_prefix_digest`, the digest of those first lines, and the runner requires it to equal the source run's `prompt_set_digest`.
  - The token-set difference is stated, not hidden: the conditions line prints, from each manifest's `prompt_count_run`, for example "at high load: the prover's 120 prompts plus 5,000 further windows of the same seeded generator" (counts for `fp-maverick-w1024-b24`, 5 × 1,024 = 5,120 serving prompts; workload facts, not results).
  - A development job may run with a fresh seed (`prompts_from` null); such a run never joins D-OVERHEAD-S.
- SRV-9. Precision note. The serving precision is the publisher's choice, not the benchmark's, and it differs from the proved precision. Every page that prints the overhead prints the note of RFC-0004 INV-DERIVE-9 beside it.
- SRV-10. Stored attempts. The `ref-serve` runs in `results/v0.1` were made under the earlier definition: plain serving on the system rows' profile, `prover-h100-hosted`, from the workload's files. That covers 12 completed SASH-workload runs (FP8 substituted at load, PM-4) and 8 failed Maverick runs (6 `config` at resolve, 2 `adapter`: vLLM refused the GGUF folder, "Unrecognized model ... Should have a `model_type` key in its config.json").
  - They stay as recorded (APP-1). They are profile `prover-h100-hosted`, not a serving profile, so they join no overhead (RFC-0004 INV-DERIVE-2 (c)).
  - The release lists them among the reference configurations, labelled "plain serving on the system rows' profile (RFC-0015 before 2026-11-09)".

### Recompute (`ref-recompute`)

A verifier holding the weights checks a claimed output by running the model itself.

- RC-1. The job reuses the prompt seeds recorded in a named system run: `iproofs run --system ref-recompute --workload W --profile P --prompts-from RUN_DIR`. The manifest records the source run id. Prompts are therefore identical request by request. Every run records each proof's `request_index` and `claimed_output` in `run.json` `proofs[]`; the harness passes the source run's claims to the recompute `prove` call as `/io/claimed.jsonl` (`claims_file` in `job.json`, one array of token ids per request, in request order).
- RC-2. Batch size 1, always, whatever the workload's batch size, because a verifier checks one request at a time and batch 1 removes batch-composition effects on greedy ties.
- RC-3. Teacher-forced check: for each request, the engine runs one forward pass over prompt plus the system's claimed output tokens and takes the argmax at each claimed output position (for next-token workloads, the single position after the window). Each position is `agree` when the argmax equals the claimed token, else `disagree`. Ties are resolved by the pinned engine's own argmax rule, which the adapter README states with a link to the engine documentation or source at the pinned version.
- RC-4. Each request's result is released as `/io/proofs/<request_id>/outputs.json` with per-position argmax tokens; timing follows REF-1. Recompute's cost is reported as D-SPT-prove.steady and D-COST-1K-prove.steady of the ref-recompute configuration: seconds and money per token for a warm verifier holding the weights, on prover-h100.
- RC-5. The harness compares each request's argmax tokens with the claim, records `{agree, disagree, first_disagreement}` in the recompute run's `run.json` `proofs[].agreement`, and sums them into the run metrics `agreement_positions` and `disagreement_positions` (counts measured by the harness, source `run.json#/proofs`). Agreement is reported per (system configuration, ref-recompute configuration) pair in the release index:

| Metric id | Unit | Scope | Grade | Formula |
|---|---|---|---|---|
| `agreement_positions` | count | null | derived | positions with `agree` |
| `disagreement_positions` | count | null | derived | positions with `disagree` |
| `first_disagreement` | count | null | derived | per request, index of the first disagreeing output position, or null |
| `agreement_rate` | ratio | null | derived | D-AGREE: `agreement_positions / (agreement_positions + disagreement_positions)` |

- RC-6. INV-REF-1: agreement never changes a verdict, a control outcome or a tier. A proof accepted by its verifier stays accepted when recompute disagrees; the claim card's `quality_gap` and `residual` fields (RFC-0002) are the place where a system explains expected disagreement, and the site prints the agreement rate beside them.
- RC-7. For SASH-style continuations, positions after the first disagreement are still compared under teacher forcing (the claimed prefix is fed, not the recomputed one), so every position is checked against the same claimed context.

### Precision matching

PM-0 to PM-4 govern `ref-recompute`. Production serving uses the publisher's release as it is (SRV-6).

- PM-0. A reference loads only the workload's pinned model files (RFC-0003), never another checkpoint of the model (for example one pre-quantized with other weights), so it runs the same weights as the workload pins.
- PM-1. The reference precision equals the workload's `precision.served` (RFC-0003) when the pinned engine documents support for it on the profile's GPU, loading the pinned files.
- PM-2. Otherwise the reference uses the nearest supported scheme by this order: same weight bit width with higher activation bit width; then the next higher weight bit width with the lowest supported activation bit width. The substitution is declared in `system.yaml` `precision_substitution` with the reason and the engine documentation link, and every metric of the row carries `quality.precision_substituted: true` (RFC-0012).
- PM-4. When the engine supports the workload's scheme only from another checkpoint (PM-0), the reference first uses the same bit widths in another number format that the engine quantizes at load time from the pinned files (for example FP8 W8A8 for an integer W8A8), before PM-2's order. It is a declared substitution like any other.
- PM-3. D-OVERHEAD-S over a substituted reference is computed and flagged, not suppressed: the reader sees the factor and the flag. A substitution to a lower bit width than the workload is never allowed (it would flatter the reference).

### Feasibility on the profile

Recompute: the runner attempts each recompute job on the system rows' profile with the engine's documented options only. Production serving: the runner attempts the configuration on the serving profile with the GPU count SRV-6 sizing puts first, and a larger count after `resource` failures with the recorded KV-capacity or out-of-memory evidence (its profile declared then, RFC-0006 R6). An `adapter` failure never moves the count: it is a bug, fixed and rerun. Failures are recorded as usual (RFC-0010); a figure with no successful run to read is null with `missing_input` or `step_failed`. The `not_measurable_on_profile` judgement (NM-1) is out for the research phase.

RISK: Meta's FP8 release of Maverick is 416.8 GB of safetensors (Hub listing, read 2026-11-09, grade external, tier reported). Planning arithmetic (grade projected) tries 4 H200 first and skips 2. Only `resource` failures at 4 GPUs, with their KV-capacity evidence, lead to 8.

### Failure modes

| Failure | Response |
|---|---|
| Engine cannot load the model or precision | job failed (`adapter` or `resource`); §Feasibility on the profile |
| `--prompts-from` run missing, failed, or for another workload version | `config` error before any step |
| Claimed outputs missing in the source run | `config` error; recompute requires a successful source run |
| Engine option not in the pinned version's documentation | policy check fails in review; adapter README lists the documentation link for every option |
| Precision substitution to fewer bits | validator rejects `system.yaml` (PM-3) |
| Serve-role `engine_args` holds an option outside SRV-3 | validator rejects `system.yaml` |
| Bound GPU count differs from the profile's `gpu.count` or from `--tensor-parallel-size` | `config` before `info` |
| Engine KV cache below the matched load | job failed `resource`; a larger GPU count is tried (SRV-6) |
| A request returns fewer or more tokens than `output_tokens` | job failed `adapter` |
| A serving file's bytes or blob id differ from the record | `fetch-model` fails `config`; no job runs |
| `--prompts-from` run of another workload version, or high-load prefix digest differs | `config` before any step |
| A workload names two serve-role systems | `config` at load (SRV-7) |
| A `VLLM_*`, `NCCL_*`, `CUDA_*` or `TORCH_*` variable not set by the image's `ENV` (and not harness binding) | `config` before the engine is built |
| A job of a larger GPU count when a smaller count of that workload has a successful run | `config` before any step |
| The release watcher falls back to polling on a serving run | job failed `environment` |
| Production-serving row on a profile that does not pair with the system row's | D-OVERHEAD-S null with `not_applicable` (RFC-0004 INV-DERIVE-2) |

## Alternatives Considered

- **Use upstream serving figures (the engine's published benchmarks).** Considered because it costs no GPU time. Rejected: those figures use other hardware, shapes and scopes; the overhead factor needs the same machine and the same token accounting.
- **Hugging Face Transformers eager forward pass as the reference.** Considered because it is the simplest reference implementation. Rejected for serving: it understates what plain serving achieves, so every overhead factor would look smaller than against a serving engine. Kept in mind for recompute if the serving engine cannot run a precision, via a later RFC.
- **Recompute through the `verify` subcommand, one container call per request.** Considered because recompute is a verifier. Rejected: every call would reload the weights, so the number would mostly measure model load, not what a verifier holding the weights pays per request; RC-4 measures warm cost and keeps load visible in `prove.session`.
- **Plain serving on the system rows' profile with part of the weights in host memory (llama.cpp, SRV-6 of 2026-11-08).** Rejected by the owner on 2026-11-09. Providers do not serve this way, and the rate would include host-to-GPU traffic that a production deployment does not pay. Users ask what proving adds over serving in normal conditions.
- **vLLM on the prover's own files and precision (GGUF).** Rejected: the plugin does not list Llama 4 among its tested families, and no provider serves Maverick that way. The stored attempts failed (SRV-10).
- **A multi-GPU serving profile with a ratio of rates.** Rejected: it divides a rate on 4 GPUs by a rate on 1. GPU-seconds per token (RFC-0004 INV-DERIVE-8) counts the GPUs.
- **FlashProve's published multiple as the overhead.** Rejected as the overhead; never mixed with ours (INV-MAP-1). Recording it as an `external` quantity in `systems/flashprove/external.yaml` is left to a later change.
- **Admitting `--language-model-only` and `--skip-tokenizer-init`.** Rejected (SRV-3): neither is a workload-shape requirement. They stood in for the mirrors lacking Meta's `tokenizer_config.json`, and `--language-model-only` also changes the memory the engine profiles for a multimodal model.
- **Recompute on the verifier profile (CPU only).** Considered because the proving systems' verifiers are timed there. Rejected: a verifier holding an 8B or about-400B-parameter model on 8 CPUs and 32 GiB is not a realistic deployment; recompute is reported on prover-h100 and labelled so.
- **Compare free-running greedy outputs instead of teacher forcing.** Considered as simpler. Rejected: after the first divergence the contexts differ and later positions are no longer comparable; teacher forcing checks every claimed position against the same context.
- **A separate workload file per reference row.** Considered for explicitness. Rejected: separate ids invite drift in shape or prompts; reusing the workload id makes INV-DERIVE-2 checkable.

## Drawbacks

- "Production serving with the engine's defaults" is not the maximum achievable serving throughput, so overhead factors are relative to a stated engine configuration, not to a physical limit.
- The serving engine is itself a moving target; a newer version may change every overhead factor, which is why it is pinned per release, and a re-pinned engine never pools with the old one (RFC-0004 INV-DERIVE-2 (e)).
- The ratio mixes the cost of proving with a precision difference the publisher chose (SRV-9).
- The serving profile has more GPUs and more host resources than the prover's. Only GPUs are counted (RFC-0006 C5).
- Engine defaults depend on the interface and usage context; the choice (Q8) is printed with the figure.
- At high load, and on a lengthened matched session, the serving side processes more prompts than the prover's (SRV-8); only the prover's set is shared.

## Conflicts of Interest

None declared.

## Migration / Rollout

New RFC; no results exist. The draft RFC-0003 named `ref-serve-*` and `ref-recompute-*` as workload ids; this RFC replaces them with reference systems run on the existing workload ids (consistent with RFC-0003 as revised). Schema additions (RFC-0012): `system/1` fields `kind`, `reference_role`, `engine`, `precision_used`, `precision_substitution`; `manifest/1` field `prompts_from`; quantity `quality.precision_substituted`; release index agreement block.

The amendment of 2026-11-08 (llama.cpp v0.9.0 for the Maverick plain-serving row, on the system rows' profile) was made and superseded on 2026-11-09; its adapter was never merged.

Amendment of 2026-11-09 (owner decision): production serving replaces plain serving. SRV-1 to SRV-10 replace the earlier SRV rules, Q2 is amended, the PM rules are limited to `ref-recompute`, and the Maverick workloads keep naming `ref-serve`. Schema additions (RFC-0012): `serving-model/1`; `system/1` workload fields `load_point`, `gpus`, `batch_size`, `batches_per_session_run`; `manifest/1` fields `workload.load_point`, `workload.batch_size_run`, `workload.batches_per_session_run`, `workload.prompt_count_run`, `workload.prompt_prefix_digest`, `workload.steady_rule`, `engine` (with `engine.observed`) and `serving_model`; `system/1` `engine.commit`. The stored `ref-serve` runs stay as recorded (SRV-10). The first publishable D-OVERHEAD-S needs an H200 driver pin (RFC-0006 Q5 for hosted, issue #77 for docker), the rebuilt `ref-serve` image public and pinned by digest, and conforming prover rows on the paired profile; until then every serving run is a development run (POL-4).

Amendment of 2026-11-09 (Draft, owner request, with RFC-0004 INV-DERIVE-10): SRV-5 states what `prove.session` is for `ref-serve` (engine start to last token). Nothing new is recorded: every `ref-serve` run has recorded `prove_session_seconds` and `gpu_seconds_per_token_prove.session` since the production-serving amendment.

Amendment of 2026-11-09 (Draft, owner direction, with RFC-0004 INV-DERIVE-11): a matched serving session of a one-batch workload is sized from a sizing capture (SRV-1, `--sizing-batches N`, manifest `workload.sizing_capture`, RFC-0012), which resolves Q10; SRV-5 and SRV-6 name D-OVERHEAD-WARM, the headline of a system with no steady scope, which divides by the matched row's steady figure. No stored run changes; the development capture of `sash-l31-8b-c1024` stays a one-request run that sizes nothing.

## Testing Strategy

CPU-only:

- TC-REF-SKIP: runner on a fake reference system (`systems/fake` with `kind: reference` fixture) records `commit` and `verify` as skipped, `whole_wall` and commit metrics null with `not_applicable`, steady and session present.
- TC-REF-TOKENS: fake reference releases for a `window` workload of 1,024 positions count 1,024 tokens per request.
- TC-AGREE-FIXTURE: hand-computed fixture: 3 requests, claimed outputs of 4 tokens, argmax disagreeing at 1 position in request 2; expects `agreement_positions` 11, `disagreement_positions` 1, `first_disagreement` [null, index, null], `agreement_rate` 11/12.
- TC-AGREE-NO-VERDICT-CHANGE: a disagreeing recompute leaves the source run's verdicts and tiers unchanged in the release index (INV-REF-1).
- TC-PROMPTS-FROM: recompute materialises the same prompt digest as the source run; a source run of another workload version fails `config`.
- TC-PRECISION-SUBST: `system.yaml` with a lower-bit substitution is rejected; a higher-bit one is accepted and every quantity carries `precision_substituted: true`.
- TC-OVERHEAD-JOIN: replaced by the RFC-0004 tests TC-OVERHEAD-GSPT, -PAIR-PROFILE, -FEWEST, -PROMPTS, -SASH and -DIGEST.

GPU host:

- GH-REF-SERVE-L31: ref-serve on `sash-l31-8b-c1024`, Meta's BF16 release at TP1 on `serving-h200x1-hosted`, three repetitions, schema-valid, `rate_prove.steady` non-null.
- GH-REF-RECOMPUTE-L31: ref-recompute with `--prompts-from` a SASH run; agreement block present.
- GH-REF-SERVE-MAVERICK-FP8: `ref-serve` on `fp-maverick-w1024-b24`, Meta's FP8 release, TP4 on `serving-h200x4-hosted`, both load points; TP8 only after TP4 attempts fail `resource`. The captures for the adapter's CPU tests come from this run.
- TC-SRV-7 (CPU, with the adapter): a workload naming two systems with `reference_role: serve` fails `config` at load, one naming none (`fake-tiny-ci`) loads; the release joins D-OVERHEAD-S to the named one.
- TC-SRV-ALLOWLIST: a serve-role entry with `--cpu-offload-gb`, `--quantization`, `--gpu-memory-utilization`, `--language-model-only` or `--skip-tokenizer-init` fails the validator.
- TC-SRV-PROMPT-PREFIX: a high-load job's first `prompts.count` prompts have the source run's `prompt_set_digest`; another digest is `config`.
- TC-SRV-GPU-COUNT: TP 4 with one visible GPU gives `config` before the engine is built.
- TC-SRV-ENV: `VLLM_ATTENTION_BACKEND` set and absent from the image `ENV` gives `config` before the engine is built.
- TC-SRV-RESOLVED: the resolved configuration line differs from the stored default dump only in the allowlisted fields and the record's own; a resolved quantization other than the release's `config.json` states is a problem, FP8 `compressed-tensors` for Maverick is not.
- TC-SRV-SHORT (`test_cross_rows.py`): a paired matched run with the warning "steady scope under 60 s" gives null `missing_input`.
- TC-SRV-HIGH-PLACEMENT (`test_cross_rows.py`): matched at TP4 and high at TP8 give D-OVERHEAD-HIGH-S null `not_applicable`.
- TC-SRV-SESSION (`test_serving_runs.py`, `test_cross_rows.py`): a fake serving job records `gpu_seconds_per_token_prove.session`, D-SPT × the GPU count.
- TC-SRV-OOM (`test_ref_serve.py`): an engine exiting at start with torch's out-of-memory line fails `resource` with that line as evidence; another exit stays `adapter`.
- TC-SRV-SIZE (`test_session_size.py`): the sizing rule against hand-computed cases, the two first captures among them: the `fp-maverick-w1024-b24` TP4 capture (5 batches of 24, `prove_steady_seconds` 2.260716798 s, measured, development run) gives 214; the `sash-l31-8b-c1024` TP1 capture (one request) and the high-load capture are refused `config`; a count below the workload's is raised to it, and an exact boundary is not rounded up.
- TC-SRV-SIZE-RUN (`test_serving_runs.py`, `test_session_size.py`, `test_cli.py`, `test_hf_job.py`, `test_cross_rows.py`): with the matched entry's count null, `--sizing-batches 4` replaying a fake run serves 4 × 2 = 8 prompts whose first 6 have the source's digest, records `sizing_capture: true` and the warning, and `size-session` divides its `prove_steady_seconds` by 3 steady batches; a sizing capture of `sash-l31-8b-c1024` (fixture values: 50 batches of 1, `prove_steady_seconds` 24.5 s, so 0.5 s a batch) gives 240 steady batches and a count of 241; `config` below 2 batches, at the high load, for an entry whose count is set, and for a system that is not production serving (the CLI before any step); the `hf-job.sh` option `sizing=50` with `from=` runs `--sizing-batches 50 --prompts-from ...`; a sizing capture enters no overhead (`missing_input`).
- TC-SRV-LENGTHEN-REPLAY (`test_serving_runs.py`, `test_ref_serve.py`): a matched entry with `batches_per_session_run` replaying a run serves batch size × that count prompts, whose first `prompts.count` have the source run's digest (`prompt_prefix_digest`); the adapter serves every batch the job names.

## Open Questions

- Resolved Q1: by the default rule, on 2026-11-04 (the date the `systems/ref-serve` pull request opened): vLLM v0.32.0 (released 2026-10-18; v0.33.0rc3 is a release candidate), image `docker.io/vllm/vllm-openai@sha256:befccf0e7e4089aa23926bb6f887a85c0d46c2a99e6de5c5ffdf5cb7957c5b34`, source commit `5df63a7203cdb9328d824a27b682e77c7b9928be`. It documents `LlamaForCausalLM` (Llama 3.1) and `Llama4ForConditionalGeneration` (Llama 4) on its [supported models](https://github.com/vllm-project/vllm/blob/v0.32.0/docs/models/supported_models.md) page, and INT8 W8A8 and FP8 W8A8 on Hopper ([quantization](https://github.com/vllm-project/vllm/blob/v0.32.0/docs/features/quantization/README.md)). Per workload: the SASH workloads use FP8 W8A8 quantized at load from the pinned files (PM-4), because INT8 W8A8 needs an llm-compressor checkpoint ([int8_w8a8.md](https://github.com/vllm-project/vllm/blob/v0.32.0/docs/features/quantization/llm_compressor/int8_w8a8.md), [online.md](https://github.com/vllm-project/vllm/blob/v0.32.0/docs/features/quantization/online.md)); the Maverick workloads load the pinned GGUF files through the vLLM project's `vllm-gguf-plugin` v0.0.5 ([gguf.md](https://github.com/vllm-project/vllm/blob/v0.32.0/docs/features/quantization/gguf.md)), which does not list Llama 4 among its tested families, so NM-1 is the expected outcome. Details in [`systems/ref-serve/README.md`](../systems/ref-serve/README.md).
- Resolved Q2 (owner decision of 2026-11-09, replacing the resolution of 2026-11-08): multi-GPU serving profiles are admitted for production serving only (RFC-0006 R6); the overhead counts GPU-seconds per token (RFC-0004 INV-DERIVE-8).
- Resolved Q3: yes, through prompt log-probabilities. Recompute submits prompt plus claimed output as one prompt of token ids with `SamplingParams(prompt_logprobs=1, max_tokens=1)` ([`sampling_params.py`](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/sampling_params.py#L347-L349)). At each position the engine returns the top-1 token of `torch.topk` over the log-probabilities ([`Sampler.gather_logprobs`](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/v1/sample/sampler.py#L312-L337)), which is the argmax; ties follow `torch.topk`'s order. No engine source change.

- OPEN QUESTION Q4 (owner: 0xchqrles, resolve by: v0.2): is `--language-model-only` a shape requirement? Default until resolved: no. It sets every modality limit to 0, which changes the memory the engine profiles for Maverick, and it is not how a multimodal model is served. It is refused (SRV-3).
- OPEN QUESTION Q5 (owner: 0xchqrles, resolve by: v0.2): the high-load batch. Default until resolved: the engine's default maximum sequences (1,024 on an H200). Alternative: a fixed number stated here.
- OPEN QUESTION Q6 (owner: 0xchqrles, resolve by: the first release with a serving row): make the rebuilt `ref-serve` image public on ghcr, so release runs use the pinned image rather than the development install. On 2026-11-09 an anonymous token request for `ref-serve` and `ref-recompute` was refused (`UNAUTHORIZED`), while `sash` and `flashprove` were granted.
- OPEN QUESTION Q7 (owner: 0xchqrles, resolve by: the first serving capture): Meta's `tokenizer_config.json`. No ungated copy checked holds Meta's bytes for either model. Default until resolved: the owner accepts Meta's licence on the Hugging Face account and passes a read token to `iproofs serving pin` and `iproofs fetch-model --serving` only, so the record holds Meta's own file (`source: publisher`). If declined, the capture records whether the engine starts without it, and the result is put to the owner; `--skip-tokenizer-init` is never admitted silently. Meta's `special_tokens_map.json` for Maverick FP8 (blob `d2b717ab`, the same in Meta's repository and RedHatAI's) is not valid JSON: a trailing comma before its closing brace (read 2026-11-09). Without `tokenizer_config.json`, the pinned image's transformers reads it and the tokenizer load fails, as a reviewer reproduced in the pinned image's `linux/arm64` entry on 2026-11-09. The Maverick record leaves that file out; every file it pins is still Meta's bytes, and the prompts are token ids, so no special token is looked up by name. A development job loads the engine's tokenizer from the record's files without the weights before it fetches them (`fetch-model --serving R --no-weights DIR`, `dev_install.py --tokenizer-check DIR`).
- OPEN QUESTION Q9 (owner: 0xchqrles, resolve by: the first release with a serving row): the resolved-configuration check of SRV-3 compares a typed shape fixture, not a captured default dump, and no run is checked against it. Default until resolved: the first capture of each serving record and interface becomes that record's stored default, by pull request, and from then on the adapter compares each run's line with it and refuses a difference with `config`.
- OPEN QUESTION Q8 (owner: 0xchqrles, resolve by: the first serving capture): the engine interface. Default until resolved: `vllm serve` with only the allowlisted flags (usage context `OPENAI_API_SERVER`, what providers run). Alternative: the `LLM` class with only the allowlisted keyword arguments (usage context `LLM_CLASS`, 16,384 rather than 8,192 batched tokens on an H200). Either way the interface is printed in the conditions line. The completions-API field that returns output token ids at v0.32.0 is named, with a link, in `systems/ref-serve/README.md`.
- Resolved Q10 (owner direction, 2026-11-09, Draft): a matched session whose workload serves one batch (the SASH workloads: one request at batch size 1) is sized from a sizing capture: a matched run of a declared count of batches (`--sizing-batches N`, SRV-1), recorded as such and joining no overhead, whose steady scope `size-session` reads. Point (a) of the question (timestamping the first batch's send) is not needed. Point (b) no longer touches the headline: a system with no steady scope is headlined by D-OVERHEAD-WARM, which divides by the lengthened session's steady scope, so the engine's start-up enters neither the serving side nor the ratio (RFC-0004 INV-DERIVE-11). The question as raised: sizing such a session when its capture has no steady scope, so that the SRV-1 rule refuses it and no run of more batches can exist while the count is null.

## References

- docs/PRD.md §6, §7.
- [RFC-0002](0002-claim-card.md) for `quality_gap` and `residual`; [RFC-0003](0003-workloads.md) for workload ids, precision and seeds; [RFC-0004](0004-metrics-timing-grades.md) for D-OVERHEAD-S, D-SPT and INV-DERIVE-2; [RFC-0005](0005-adapter-contract.md) for the adapter contract; [RFC-0006](0006-reference-hardware-and-cost.md) for profiles; [RFC-0010](0010-harness-runner.md) for skipped steps; [RFC-0011](0011-measurement-and-sampling.md) for release timing.
- vLLM documentation at the pinned release (engine options, supported quantisation schemes).
- Meta's model cards at the pinned revisions ([Llama 4 Maverick FP8](https://huggingface.co/meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8/blob/94125d2bd83076b21eed33119525e29eaf3894f4/README.md), [Llama 3.1 8B Instruct](https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct/blob/0e9e39f249a16976918f6564b8830bc894c89659/README.md)).
