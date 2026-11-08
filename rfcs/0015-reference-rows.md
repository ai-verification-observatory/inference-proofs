# RFC-0015: Reference rows: plain serving and recompute

- Status: Draft
- Authors: AbdelStark
- Created: 2026-11-03
- Target milestone: v0.1-beta
- Requires: RFC-0003, RFC-0004, RFC-0005, RFC-0006, RFC-0011
- Supersedes: none
- Discussion: pull request that introduces it

## Summary

Every native workload gets two reference rows measured on the same profile, with the same prompts and the same token accounting as the proving systems: plain serving (the model served unproved) and recompute (a verifier holding the weights reruns the forward pass and checks the claimed output). Plain serving gives the overhead factor, the most asked-for number (PRD §6). Recompute answers what a proof buys over a party that simply holds the weights. Both are implemented as ordinary adapters (`systems/ref-serve`, `systems/ref-recompute`) under the RFC-0005 contract with `kind: reference`, so the harness, measurement and statistics are shared and nothing is special-cased except which steps run.

## Motivation

PRD §6 asks for "two reference rows per workload, so every proof cost reads against something": plain serving with vLLM, pinned, on the same model, precision and hardware, and naive recompute by a verifier holding the weights. A proving rate alone says nothing about cost relative to the work being proved; the overhead against plain serving does (RFC-0004 D-OVERHEAD-S). Recompute also gives a second, independent check of the claimed outputs: FlashProve's claim card states that it proves the integer model, which differs from the 16-bit model's top token at some positions (RFC-0002 example residual), and readers need to see how often the claimed output agrees with a plain forward pass.

## Goals

- Reference rows use the same workload ids, versions, prompt sets (seeds), shapes and profile as the system rows they serve.
- Tokens are counted with the same rule as the proving system's claim card coverage (RFC-0004 INV-TOK-1), so D-OVERHEAD-S divides like by like.
- The serving engine is pinned by image digest and version; precision substitutions are declared and flagged.
- Output agreement between recompute and each system's claimed outputs is reported as counts and a derived rate, separately from verdicts.
- A reference row that cannot run on the profile is recorded as such, and every metric that depends on it is null with a reason.

## Non-Goals

- Tuning the serving engine for peak throughput beyond its documented defaults and the workload's batch size. The reference is "plain serving as documented", not the maximum throughput the engine could reach with tuning.
- Decode-heavy serving profiles, latency under load, request arrival processes (no such workload in v0.1).
- Judging which output is correct when recompute and a system disagree. Agreement is reported; no verdict is changed.
- Reference rows on profiles other than the system rows' profile.

## Proposed Design

### Reference systems

Two directories, each a normal adapter (RFC-0005) with `system.yaml` field `kind: reference` and `reference_role: serve | recompute`:

```
systems/ref-serve/       Dockerfile (engine image by digest), entrypoint, system.yaml, README.md, tests/
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
  - id: "sash-l31-8b-c4096"
    precision_used: "<scheme>"           # equal to the workload's as-served precision, or a declared substitute
    precision_substitution: null         # or {reason: "...", source: "<engine docs URL at version>"}
    engine_args: ["--max-num-seqs", "1"] # only options the engine documents; recorded verbatim
incremental_proofs: true
deterministic_proofs: false
forbidden_flags: []
```

### Steps per job

For `kind: reference` the runner (RFC-0010) runs `info`, `setup`, `prove`; it records `commit` and `verify` as `skipped`. Consequences in RFC-0004 terms: `commit_seconds` and the D-COMMIT-AMORT metrics are null with `null_reason: not_applicable`; `whole_wall` is null with `not_applicable` (there is no commit start event); `prove.session` and `prove.steady` are measured exactly as for a proving system.

- REF-1. The `prove` subcommand loads the engine once, processes the workload's requests in the workload's order, and after each batch writes one release directory `/io/proofs/<batch_id>/outputs.json` atomically (RFC-0005 rename contract). The release watcher (RFC-0011) timestamps these directories, so `prove.steady` (first to last batch release) excludes engine start-up and model load, and `prove.session` includes them, with the same boundaries as the proving systems.
- REF-2. Release directories of a reference system are called "outputs", not proofs, in every record and page. The harness computes no proof bytes for them.
- REF-3. Tokens per release are counted by the harness with the coverage rule of the system the reference row serves: for `window`, the window's positions; for `prompt_plus_output`, prompt plus output positions (RFC-0004 INV-TOK-1).

### Plain serving (`ref-serve`)

- SRV-1. Batch size equals the workload's `batch_size`; batches per session equal `batches_per_session`.
- SRV-2. Greedy decoding (temperature 0), `max_tokens` equal to the workload's `output_tokens`, or 1 for next-token workloads (the window is prefilled and one token is produced, the smallest unit the engine serves).
- SRV-3. Engine options: only those the pinned engine version documents, listed verbatim in `system.yaml`, chosen to make the workload fit (for example maximum sequence count equal to the batch size, maximum model length equal to the context window). No option that changes numerics beyond the declared precision.
- SRV-4. Outputs are recorded (`outputs.json`: request index, generated token ids) for audit; serving outputs are not compared with system outputs, because batched serving may legitimately differ from batch 1 at ties.
- SRV-5. Metrics: `rate_prove.steady`, `rate_prove.session`, GPU and host resources as RFC-0011. These feed D-OVERHEAD-S (RFC-0004).
- SRV-6. Engine per workload. The SASH workloads' plain-serving row runs on vLLM (Q1). The Maverick workloads' row runs on llama.cpp's `llama-server` (amendment of 2026-11-08, owner decision): the pinned files are GGUF files, and "the GGUF container, the block formats and their decoding are ggml's (github.com/ggml-org/llama.cpp, [...])", as FlashProve's own model definition puts it ([docs/model.md L576 to L577](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/docs/model.md#L576-L577)); the pinned llama.cpp version names the architecture of the pinned files, `llama4` ([src/llama-arch.cpp L12](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/src/llama-arch.cpp#L12)). The pin, by the rule Q1 used (the newest stable release on the day of the decision, 2026-11-08): llama.cpp v0.9.0, published 2026-11-04, commit `cd959bae99ff4bed22bef2604f45241c09bbb8c8` (build `b12110`), server image built with CUDA 12 `ghcr.io/ggml-org/llama.cpp:server-cuda-b12110@sha256:a2963b4817f03eea7e0d6065ea576252322792441ef97aaae178b924520547d6` (multi-platform index; the `server-cuda` family of [docs/docker.md](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/docs/docker.md)). The row:
  - runs on the same profile as the FlashProve rows it serves, so D-OVERHEAD-S never mixes two profiles (INV-DERIVE-2 unchanged);
  - loads the workload's pinned GGUF files unchanged and serves `UD-Q4_K_XL` as stored: PM-0 and PM-1 hold, with no substitution;
  - keeps part of the weights in host memory with options the pinned version documents ([tools/server/README.md](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md)): `-ngl` for the layers on the GPU, and `--n-cpu-moe N` ("keep the Mixture of Experts (MoE) weights of the first N layers in the CPU") or `--cpu-moe` for the routed experts. N is the smallest value with which the job runs on the profile, and `--fit off` keeps the placement the recorded one rather than one the engine chooses at load time. Finding N is a sizing step, not a measurement: each N tried is a `system.yaml` of its own (`engine_args` are pinned, SRV-3), and its runs are recorded as usual (RFC-0010), failures included, under that manifest. The published configuration fixes the final N verbatim in `engine_args`; the runs of other N values are never part of its statistics. NM-1 applies to the Maverick row only after `--cpu-moe` (every routed expert in host memory) also fails on the profile;
  - serves the workload's batch with as many server slots (`-np`) as the batch size and a context of prompt plus output tokens per slot (SRV-1), pinned in one form: `--kv-unified --kv-unified-per-slot 1025` and no `-c` ("context limit per parallel slot [...] when set without -c/--ctx-size, the shared KV pool is sized to n_parallel*N", [README L165 and L169](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md#L165-L169)), so each of the 1 or 24 slots holds 1,024 prompt tokens plus 1 output token;
  - sends prompts as arrays of token ids, which the pinned server does not prefix with a beginning-of-sequence token (README L501 to L503, consistent with RFC-0003 generator rule 2); `n_predict` equal to the output tokens (SRV-2); `temperature` 0 with the default sampler order and `n_probs` 0, which the pinned sampler turns into its greedy sampler ([common/sampling.cpp L403 to L406](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/common/sampling.cpp#L403-L406)); `repeat_penalty` 1.0, `presence_penalty` 0 and `frequency_penalty` 0, so the penalties sampler, which runs before the greedy one in the default chain, leaves the logits unchanged (the pinned README states a `/completion` default `repeat_penalty` of 1.1, [README L551 to L557](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md#L551-L557), while `common/common.h` defaults it to 1.00; the request sets it so greedy decoding does not hinge on which applies); and `cache_prompt` false, so no request reuses another request's KV cache (default true, README L597).
- SRV-7. One plain-serving system per workload. An adapter image is built from one engine image (§Reference systems), so the llama.cpp row is a second adapter with `reference_role: serve`, `systems/ref-serve-gguf`. When it lands, the Maverick workloads' `systems` lists name `ref-serve-gguf` in place of `ref-serve`, and `systems/ref-serve/system.yaml` drops the two Maverick workloads. Every workload names at most one system with `reference_role: serve` (a CI workload such as `fake-tiny-ci` names none), and D-OVERHEAD-S joins that system's configuration. Tables keep the label `ref-serve-<workload-id>` and print the engine name beside it. `ref-recompute` is not changed by this amendment.

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

- PM-0. A reference loads only the workload's pinned model files (RFC-0003), never another checkpoint of the model (for example one pre-quantized with other weights), so it runs the same weights as the workload pins.
- PM-1. The reference precision equals the workload's `precision.served` (RFC-0003) when the pinned engine documents support for it on the profile's GPU, loading the pinned files.
- PM-2. Otherwise the reference uses the nearest supported scheme by this order: same weight bit width with higher activation bit width; then the next higher weight bit width with the lowest supported activation bit width. The substitution is declared in `system.yaml` `precision_substitution` with the reason and the engine documentation link, and every metric of the row carries `quality.precision_substituted: true` (RFC-0012).
- PM-4. When the engine supports the workload's scheme only from another checkpoint (PM-0), the reference first uses the same bit widths in another number format that the engine quantizes at load time from the pinned files (for example FP8 W8A8 for an integer W8A8), before PM-2's order. It is a declared substitution like any other.
- PM-3. D-OVERHEAD-S over a substituted reference is computed and flagged, not suppressed: the reader sees the factor and the flag. A substitution to a lower bit width than the workload is never allowed (it would flatter the reference).

### Feasibility on the profile

RISK: the Maverick workloads use a public 4-bit conversion of a mixture-of-experts model with about 400B parameters (PRD §1, external, reported). Its weights exceed the 80 GB of GPU memory on prover-h100, and FlashProve itself relies on about 300 GB of host memory (external, reported). The pinned serving engine may be unable to serve or recompute it on one H100, with or without a documented CPU offload option.

Rule NM-1: the runner attempts each reference job on the system rows' profile with the engine's documented options only (including CPU offload if the pinned version documents it, declared in `engine_args`; for the Maverick plain-serving row, llama.cpp with part of the weights in host memory, SRV-6). If every attempt of a configuration fails with kind `resource` or `adapter` (unsupported model or precision), the failures are recorded as usual (RFC-0010) and the configuration is marked `not_measurable_on_profile` in the release index. Every metric that depends on it (D-OVERHEAD-S, D-AGREE) is null with `null_reason: not_measurable_on_profile`. No larger profile is used in v0.1 (RFC-0006 R1), and no multi-GPU profile is admitted for reference rows (Q2). If the Maverick rows have no reference, the v0.1 report says so in its first paragraph about FlashProve.

### Failure modes

| Failure | Response |
|---|---|
| Engine cannot load the model or precision | job failed (`adapter` or `resource`); after all attempts, NM-1 |
| `--prompts-from` run missing, failed, or for another workload version | `config` error before any step |
| Claimed outputs missing in the source run | `config` error; recompute requires a successful source run |
| Engine option not in the pinned version's documentation | policy check fails in review; adapter README lists the documentation link for every option |
| Precision substitution to fewer bits | validator rejects `system.yaml` (PM-3) |
| Reference row on another profile than the system row | D-OVERHEAD-S null with `not_applicable` (RFC-0004 INV-DERIVE-2) |
| llama.cpp cannot serve a Maverick workload on the profile, with every documented placement of the experts tried | job failed (`resource` or `adapter`); after all attempts, NM-1 |
| A workload names two plain-serving systems | `config` error at load, once the loader check of SRV-7 lands |

## Alternatives Considered

- **Use upstream serving figures (the engine's published benchmarks).** Considered because it costs no GPU time. Rejected: those figures use other hardware, shapes and scopes; the overhead factor needs the same machine and the same token accounting.
- **Hugging Face Transformers eager forward pass as the reference.** Considered because it is the simplest reference implementation. Rejected for serving: it understates what plain serving achieves, so every overhead factor would look smaller than against a serving engine. Kept in mind for recompute if the serving engine cannot run a precision, via a later RFC.
- **Recompute through the `verify` subcommand, one container call per request.** Considered because recompute is a verifier. Rejected: every call would reload the weights, so the number would mostly measure model load, not what a verifier holding the weights pays per request; RC-4 measures warm cost and keeps load visible in `prove.session`.
- **A multi-GPU profile for the Maverick plain-serving row.** Considered because the weights fit in the memory of several GPUs. Rejected by the owner on 2026-11-08: the overhead would divide a rate on several GPUs by a rate on one, and a rule for counting GPUs (rate ratio or GPU-seconds per token) would be needed to make the two comparable. llama.cpp on the system rows' profile keeps one profile per ratio (SRV-6).
- **vLLM with its GGUF plugin and `--cpu-offload-gb` for Maverick.** The v0.1 choice (Q1). Kept for the SASH workloads; replaced for Maverick by llama.cpp, whose pinned version names the files' architecture, while the plugin's README does not list Llama 4 among its tested families.
- **Recompute on the verifier profile (CPU only).** Considered because the proving systems' verifiers are timed there. Rejected: a verifier holding an 8B or about-400B-parameter model on 8 CPUs and 32 GiB is not a realistic deployment; recompute is reported on prover-h100 and labelled so.
- **Compare free-running greedy outputs instead of teacher forcing.** Considered as simpler. Rejected: after the first divergence the contexts differ and later positions are no longer comparable; teacher forcing checks every claimed position against the same context.
- **A separate workload file per reference row.** Considered for explicitness. Rejected: separate ids invite drift in shape or prompts; reusing the workload id makes INV-DERIVE-2 checkable.

## Drawbacks

- "Plain serving as documented" is not the maximum achievable serving throughput, so overhead factors are relative to a stated engine configuration, not to a physical limit.
- The serving engine is itself a moving target; a newer version may change every overhead factor, which is why it is pinned per release.
- The Maverick reference rows may be absent in v0.1 (RISK above).
- Two engines serve the plain-serving rows (vLLM for the SASH workloads, llama.cpp for Maverick), so overhead factors of the two workload families are relative to different engines; the engine is printed beside each factor (SRV-7).
- With routed experts in host memory, the Maverick plain-serving rate includes host-to-GPU traffic that a deployment with enough GPU memory would not pay, so its overhead factor is smaller than against such a deployment. FlashProve itself relies on about 300 GB of host memory on the same profile (external, reported; RISK above).

## Conflicts of Interest

The author's affiliations and any interest in a measured system are declared in `MAINTAINERS.md` before this RFC enters Last call (RFC-0001).

## Migration / Rollout

New RFC; no results exist. The draft RFC-0003 named `ref-serve-*` and `ref-recompute-*` as workload ids; this RFC replaces them with reference systems run on the existing workload ids (consistent with RFC-0003 as revised). Schema additions (RFC-0012): `system/1` fields `kind`, `reference_role`, `engine`, `precision_used`, `precision_substitution`; `manifest/1` field `prompts_from`; quantity `quality.precision_substituted`; release index agreement block.

The amendment of 2026-11-08 adds SRV-6 and SRV-7 (llama.cpp v0.9.0 for the Maverick plain-serving row, on the system rows' profile) and resolves Q2. It changes no rule for the SASH workloads. The adapter `systems/ref-serve-gguf`, its image and its GPU captures need a GPU host and land with their own pull request (the next step is described in [`systems/ref-serve/README.md`](../systems/ref-serve/README.md#next-step-llamacpp-for-the-maverick-workloads)); until then the Maverick workloads list `ref-serve`, whose stored v0.1 attempts stay as recorded (APP-1). The release join (`_overheads` in `iproofs.release`) then picks the serve-role system the workload names (SRV-7), and the workload loader checks that at most one is named.

## Testing Strategy

CPU-only:

- TC-REF-SKIP: runner on a fake reference system (`systems/fake` with `kind: reference` fixture) records `commit` and `verify` as skipped, `whole_wall` and commit metrics null with `not_applicable`, steady and session present.
- TC-REF-TOKENS: fake reference releases for a `window` workload of 1,024 positions count 1,024 tokens per request.
- TC-AGREE-FIXTURE: hand-computed fixture: 3 requests, claimed outputs of 4 tokens, argmax disagreeing at 1 position in request 2; expects `agreement_positions` 11, `disagreement_positions` 1, `first_disagreement` [null, index, null], `agreement_rate` 11/12.
- TC-AGREE-NO-VERDICT-CHANGE: a disagreeing recompute leaves the source run's verdicts and tiers unchanged in the release index (INV-REF-1).
- TC-PROMPTS-FROM: recompute materialises the same prompt digest as the source run; a source run of another workload version fails `config`.
- TC-PRECISION-SUBST: `system.yaml` with a lower-bit substitution is rejected; a higher-bit one is accepted and every quantity carries `precision_substituted: true`.
- TC-NM-1: all attempts failed with `resource`; release index marks `not_measurable_on_profile`; D-OVERHEAD-S and D-AGREE null with that reason.
- TC-OVERHEAD-JOIN: release-level D-OVERHEAD-S joins only rows with equal workload id, version, profile, phase and batch size.

GPU host:

- GH-REF-SERVE-L31: ref-serve on `sash-l31-8b-c1024`, three repetitions, schema-valid, `rate_prove.steady` non-null.
- GH-REF-RECOMPUTE-L31: ref-recompute with `--prompts-from` a SASH run; agreement block present.
- GH-REF-MAVERICK-ATTEMPT: `ref-serve-gguf` (llama.cpp, SRV-6) on `fp-maverick-w1024-b1` and `fp-maverick-w1024-b24`, on the FlashProve rows' profile; either a valid row or a recorded failure leading to NM-1. The captures for the adapter's CPU tests come from this run.
- TC-SRV-7 (CPU, with the adapter): a workload naming two systems with `reference_role: serve` fails `config` at load, one naming none (`fake-tiny-ci`) loads; the release joins D-OVERHEAD-S to the named one.

## Open Questions

- Resolved Q1: by the default rule, on 2026-11-04 (the date the `systems/ref-serve` pull request opened): vLLM v0.32.0 (released 2026-10-18; v0.33.0rc3 is a release candidate), image `docker.io/vllm/vllm-openai@sha256:befccf0e7e4089aa23926bb6f887a85c0d46c2a99e6de5c5ffdf5cb7957c5b34`, source commit `5df63a7203cdb9328d824a27b682e77c7b9928be`. It documents `LlamaForCausalLM` (Llama 3.1) and `Llama4ForConditionalGeneration` (Llama 4) on its [supported models](https://github.com/vllm-project/vllm/blob/v0.32.0/docs/models/supported_models.md) page, and INT8 W8A8 and FP8 W8A8 on Hopper ([quantization](https://github.com/vllm-project/vllm/blob/v0.32.0/docs/features/quantization/README.md)). Per workload: the SASH workloads use FP8 W8A8 quantized at load from the pinned files (PM-4), because INT8 W8A8 needs an llm-compressor checkpoint ([int8_w8a8.md](https://github.com/vllm-project/vllm/blob/v0.32.0/docs/features/quantization/llm_compressor/int8_w8a8.md), [online.md](https://github.com/vllm-project/vllm/blob/v0.32.0/docs/features/quantization/online.md)); the Maverick workloads load the pinned GGUF files through the vLLM project's `vllm-gguf-plugin` v0.0.5 ([gguf.md](https://github.com/vllm-project/vllm/blob/v0.32.0/docs/features/quantization/gguf.md)), which does not list Llama 4 among its tested families, so NM-1 is the expected outcome. Details in [`systems/ref-serve/README.md`](../systems/ref-serve/README.md).
- Resolved Q2 (owner decision, 2026-11-08): no multi-GPU profile for reference rows. When a model does not fit in the GPU memory of the system rows' profile, the plain-serving row uses an engine that documents keeping part of the weights in host memory on that same profile (SRV-6 for Maverick), and NM-1 applies when that fails.
- Resolved Q3: yes, through prompt log-probabilities. Recompute submits prompt plus claimed output as one prompt of token ids with `SamplingParams(prompt_logprobs=1, max_tokens=1)` ([`sampling_params.py`](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/sampling_params.py#L347-L349)). At each position the engine returns the top-1 token of `torch.topk` over the log-probabilities ([`Sampler.gather_logprobs`](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/v1/sample/sampler.py#L312-L337)), which is the argmax; ties follow `torch.topk`'s order. No engine source change.

## References

- docs/PRD.md §6, §7.
- [RFC-0002](0002-claim-card.md) for `quality_gap` and `residual`; [RFC-0003](0003-workloads.md) for workload ids, precision and seeds; [RFC-0004](0004-metrics-timing-grades.md) for D-OVERHEAD-S, D-SPT and INV-DERIVE-2; [RFC-0005](0005-adapter-contract.md) for the adapter contract; [RFC-0006](0006-reference-hardware-and-cost.md) for profiles; [RFC-0010](0010-harness-runner.md) for skipped steps; [RFC-0011](0011-measurement-and-sampling.md) for release timing.
- vLLM documentation at the pinned release (engine options, supported quantisation schemes).
