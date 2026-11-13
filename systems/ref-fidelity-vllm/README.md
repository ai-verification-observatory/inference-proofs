# ref-fidelity-vllm: the fidelity reference in vLLM

[RFC-0018 FI-9](../../rfcs/0018-level-1-ladder.md#fidelity): for a rung whose 16-bit reference llama.cpp at the level's pin cannot run, the reference, its rerun and the smaller model run in vLLM. Llama 4 Maverick is that rung: llama.cpp v0.9.0 (`cd959bae`) loads the 16-bit file on 8 H200 and stops in its first computation with `ggml_cuda_compute_forward: MUL_MAT_ID failed ... an illegal memory access was encountered` (with `CUDA_LAUNCH_BLOCKING=1`). The same failure came with `GGML_CUDA_PDL=0`, `GGML_CUDA_DISABLE_GRAPHS=1`, both, flash attention off, no warm-up, batch 256 and one slot, on two machines, from our conversion and from unsloth's BF16 GGUF. The 8-bit file (Q8_0) runs at 16 slots (325 tokens/s). Each merged expert tensor holds 128 × 8,192 × 5,120 values, past a 32-bit index; that is the likely cause, not a confirmed one.

## Engine

vLLM 0.32.0, the image the serving baselines run (`docker.io/vllm/vllm-openai@sha256:befccf0e…`, build commit `5df63a72`). The entrypoint loads each model once in vLLM's offline engine (`vllm.LLM`): `dtype` bfloat16, `tensor_parallel_size` the job's GPU count, `max_model_len` the longest prompt plus 512 plus 64, prefix caching off, no image inputs, seed 0. Each prompt goes in as token ids (no BOS added, as llama.cpp's server does for a token-id prompt) with `temperature` 0, `max_tokens` and `min_tokens` 512 and `ignore_eos`, so an end token chosen greedily stays in the reply and generation goes on (RFC-0018's request). The `rerun` control sends the prompts in reverse order and writes its replies back in prompt order: how far it departs from the reference is what batching changes.

## Calls

`iproofs fidelity run --engine vllm` makes three calls: `info`, `prove` with `call: reference` (the publisher's 16-bit safetensors at /models: the reference and the `rerun` control), `prove` with `call: other_model` (the smaller model). A recipe this image does not build is recorded failed with its cause. The `quantize` controls come from `iproofs fidelity run --part controls` in the `ref-fidelity` image. No KL (FI-7 needs llama.cpp's base on the 16-bit file).

## Teacher-forced pass (RFC-0018 FI-10 to FI-13)

With `teacher_forced` in the job, a call generates no reply: each prompt followed by the stored reference reply goes in as token ids with `prompt_logprobs` 256 ("Number of log probabilities to return per prompt token", [sampling_params.py](https://github.com/vllm-project/vllm/blob/5df63a7203cdb9328d824a27b682e77c7b9928be/vllm/sampling_params.py#L347-L349)), `max_tokens` 1 and `flat_logprobs`, and the engine starts with `max_logprobs` 256, its cap on that number (default 20). Entry j of a request's `prompt_logprobs` is the distribution after tokens 0 to j − 1, so entries 512 to 1,023 are the reply's positions. vLLM lists the sequence's own token first, then the most probable ones; the adapter sorts them (lower id first among equal values) and takes the first as the top token.

What v0.32.0 can return, read at the pin: `prompt_logprobs` −1 returns the whole vocabulary ("When set to -1, return all `vocab_size` log probabilities") when `max_logprobs` is −1, which its documentation warns "may cause OOM": 1,024 positions × 202,048 tokens per prompt, built as Python lists. `prompt_logprob_token_ids` returns the log-probabilities of given ids per position as an array. The pass uses neither: FI-12 asks every engine for its own 256 most probable tokens, the same request llama.cpp and the systems answer.

Sequences go in 32 at a time. The `rerun` control sends them in reverse order, as it does for replies.

## Tests

`tests/test_ref_fidelity_vllm.py` runs both calls, and the teacher-forced pass, on CPU against a stand-in for vLLM.
