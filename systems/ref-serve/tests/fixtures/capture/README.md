# Captured engine outputs

Captured once on a GPU host (INV-ADAPTER-9) on 2026-11-04 by running `systems/ref-serve/entrypoint` (`info`, then `prove`) inside the pinned engine image `docker.io/vllm/vllm-openai@sha256:befccf0e7e4089aa23926bb6f887a85c0d46c2a99e6de5c5ffdf5cb7957c5b34` (vLLM v0.32.0). The two wheels in `../../../inputs.lock` were installed offline first, as the Dockerfile does. Host: an HF Jobs `l40sx1` container (NVIDIA L40S, driver 580.178.04). That is not the prover-h100 profile, so nothing here is a measurement.

- Model: `unsloth/Llama-3.1-8B-Instruct` at `4699cc75b550f9c6f3173fb80f4703b62d946aa5` (the SASH workloads' model, #49), `*.safetensors` and `*.json` files.
- Options: those of `sash-l31-8b-c1024` in `../../../system.yaml` (FP8 W8A8 quantized at load, PM-4).
- Prompt (`prompts.jsonl`): the first 1,024 token ids of a repeated public-domain sentence ("It was the best of times, ...", Dickens, 1859), tokenised with the model's `tokenizer.json`, without special tokens.
- Job: batch size 1, 1 batch, 64 output tokens.
- Files: `out.json` (the adapter's prove output), `proofs/req-0/outputs.json` (the released outputs) and `commands.jsonl` (the recorded engine call; its `started_mono_ns` is that host's monotonic clock).
