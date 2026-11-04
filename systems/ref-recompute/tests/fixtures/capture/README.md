# Captured argmax tokens

Captured once on a GPU host (INV-ADAPTER-9) on 2026-11-04 by running `systems/ref-serve/entrypoint` `prove` with `systems/ref-recompute/system.yaml` inside the pinned engine image `docker.io/vllm/vllm-openai@sha256:befccf0e7e4089aa23926bb6f887a85c0d46c2a99e6de5c5ffdf5cb7957c5b34` (vLLM v0.32.0). Host: an HF Jobs `l40sx1` container (NVIDIA L40S, driver 580.178.04). That is not the prover-h100 profile, so nothing here is a measurement.

- Model and options: as in `systems/ref-serve/tests/fixtures/capture/README.md` (`unsloth/Llama-3.1-8B-Instruct` at `4699cc75b550f9c6f3173fb80f4703b62d946aa5`, FP8 W8A8 at load), with this system's `sash-l31-8b-c1024` options.
- Requests (`prompts.jsonl`): the ref-serve fixture's 1,024-token prompt, twice.
- Claims (`claimed.jsonl`):
  - request 0: the 64 tokens ref-serve generated for that prompt;
  - request 1: the same 64 tokens with token 5 increased by one.
- Result (`out.json`, `proofs/`): request 0's argmax equals its claim at all 64 positions. Request 1's differs at positions 5 and 6. Position 6 is fed the changed token 5 in its prefix (RC-7), and the engine's argmax there differs from the original continuation.
- `commands.jsonl`: the recorded engine call; its `started_mono_ns` is that host's monotonic clock.
