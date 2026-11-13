If you work on cryptographic proof systems, you already think in terms of arithmetic circuits. A transformer's forward pass is an arithmetic circuit with three inconvenient traits: it is enormous, many of its operations are non-linear rather than finite-field additions and multiplications, and its native data type is floating point rather than field elements. Here is how LLM inference works from a prover's point of view, and how production serving sets the baseline we compare against.

## What a forward pass computes

A language model takes a sequence of [[token|tokens]] (integer IDs from a fixed vocabulary) and computes a vector of scores (logits) over the entire vocabulary for each position. To generate a reply, the model picks a token from the scores at the final position, appends that token to the sequence, and runs another pass to predict the next token.

:::figure pipeline
One forward pass through a transformer, grouped by what a prover has to do. Matrix multiplications against the committed model weights are linear operations; everything else either multiplies two dynamic activations together or is not arithmetic.
:::

From a proof system's perspective, the operations inside each layer fall into three buckets:

- **Matrix multiplications against committed weights.** A vector of dynamic activations multiplied by a static weight matrix that the operator committed to before the session. These linear projections account for the vast majority of the raw FLOPs, and as [Proving a forward pass](/forward-pass) explains, they are actually the easiest part to prove.
- **Products of two dynamic activations.** Self-attention multiplies queries by keys, and then multiplies attention weights by values. Because neither operand is part of the static model commitment, both tensors have to be committed or reduced dynamically during the proof.
- **Non-linear and non-arithmetic operations.** Layer normalisation divides by a square root; softmax exponentiates and normalises; MLP activations apply curves like SiLU or GELU; greedy decoding takes the argmax across tens of thousands of vocabulary logits; token embedding looks up rows in a table. None of these is a native addition or multiplication over a finite field.

## Scale of the circuit

In a dense transformer, each forward pass uses every weight roughly once per token in a multiply-accumulate operation, which comes to about [two arithmetic operations per parameter per token](https://arxiv.org/abs/2001.08361). For an 8-billion-parameter model, generating or processing a single token takes roughly 1.6 × 10^10 operations, and a 1,024-token sequence (512 prompt tokens plus 512 reply tokens) totals roughly 1.6 × 10^13 operations.

Two architectural details matter for the models on our ladder:

1. **Mixture-of-experts (MoE) routing.** An MoE model activates only a subset of its weights for any given token. For example, the 400-billion-parameter model on our ladder activates about 17 billion parameters per token, even though the initial model commitment still covers all 400 billion parameters.
2. **Quadratic attention.** Self-attention compares every token position against every preceding position, adding work that scales quadratically with context length.

Consequently, the execution trace (the [[witness]]) is massive: thousands of intermediate activations per token position at every layer, all of which must be held in memory, encoded as polynomials, and committed.

## Floating-point drift versus deterministic arithmetic

Model developers release weights in 8-bit, 16-bit, or 32-bit floating point, and production serving engines execute them using parallel GPU kernels. Because floating-point addition is not associative, summing the same numbers in a different order changes the low-order bits. In a GPU cluster, the reduction order depends on thread scheduling, tensor-parallel sharding, and how many user requests are batched together at that millisecond. As a result, two honest runs of the exact same model on the exact same prompt can diverge in a low bit, flip a close tie between two top logits, and output a different token, after which the rest of the generated reply diverges completely. A 2025 study found that "[changing system configuration, such as evaluation batch size, GPU count, and GPU version, can introduce significant differences in the generated responses](https://arxiv.org/abs/2506.09501)", even under greedy decoding.

That variation is mostly configuration sensitivity rather than true hardware nondeterminism: if you lock down the exact GPU model, driver version, tensor-parallel degree, and batch size, and avoid atomic reductions whose order depends on thread arrival times, [recent work](https://arxiv.org/abs/2606.00279) shows that standard serving engines can reproduce outputs bit for bit (finding true run-to-run nondeterminism only in certain integer-quantized kernels). However, an external verifier rarely knows the operator's live batching schedule, and in a zero-knowledge setting it does not hold the weights either.

Because a cryptographic proof requires a well-defined mathematical function, *the output of this model on this prompt* is not even a well-defined statement until the arithmetic and rounding rules are pinned down completely. Provers solve this by defining a quantized or fixed-point copy of the model ([[quantization]]) with deterministic rounding at every step. Three practical consequences follow directly from that choice:

- **The proof is about the quantized copy, not the original floats.** An accepted proof guarantees that the prover's quantized model produces the reply; by itself, it says nothing about the publisher's original floating-point release. Our [Fidelity check](/method#fidelity-is-the-proved-model-the-publisher-s) measures whether the proved copy's replies stay closer to the unquantized reference model than intentionally degraded copies do.
- **Live replies must be generated using the prover's arithmetic.** If an operator generates a reply using standard floating-point kernels in vLLM, rounding differences will eventually cause a token mismatch that makes an exact-match proof fail. To be provable under exact match, the reply must be generated using the prover's own deterministic arithmetic.
- **Decoding is greedy.** Under [[greedy decoding]], the reply is a deterministic function of the weights and the prompt. Supporting temperature sampling inside a proof requires committing to a verifiable random seed and proving the sampling step as well.

## How models are served in production

Because we express every prover's cost as a multiple of normal serving, it helps to understand how a production serving engine actually runs. When a request arrives, the engine processes the prompt tokens in parallel (the prefill phase), caches the resulting key and value vectors at every layer (the KV cache), and then generates the reply one token at a time against that cache (the decode phase). Crucially, a single GPU node batches dozens or hundreds of concurrent requests together so that reading the model weights from high-bandwidth memory is amortised across many users at once.

As a result, the GPU cost of serving a single reply depends heavily on concurrency: running one isolated request on an otherwise idle GPU wastes most of the chip's memory bandwidth, whereas running at high concurrency saturates the GPU. To avoid inflating our denominator with an artificially slow baseline, we measure our [[serving baseline]] at full load, stepping up request concurrency until throughput plateaus.

:::measured baselines
Serving baselines across our Level 1 model ladder, running each publisher's official release on the minimum number of H200 GPUs required to hold the weights.
:::

That full-load serving cost per reply (b) is the denominator for every cost multiple on this site.

## Choices every inference statement has to pin down

Saying "this model produced this reply" glosses over six concrete specification choices that a formal [[statement]] must lock down:

| Specification choice | Why leaving it ambiguous breaks verification |
|---|---|
| Which weight representation is committed | Committing to 4-bit quantized integers fixes a different function than committing to 16-bit floats |
| Exact rounding and scaling rules | Low-bit rounding determines logit ties, which determine every subsequent token |
| Token IDs versus raw strings | Transformers operate on integer token IDs; text tokenization sits outside the proof unless explicitly included |
| Decoding rule | Greedy argmax (with a deterministic tie-breaking rule) versus seeded random sampling |
| Stopping condition | Whether an end-of-sequence token halts generation early (our benchmark disables early stopping so every reply is 512 tokens) |
| Checked token positions | Whether the proof verifies a single next token or all 512 tokens of the reply |

[The statement](/statement) examines how two systems on our ladder specify the first four choices, while our benchmark [[request]] standardises tokenization, stopping rules, and full-reply coverage.

## Why transformer inference is awkward to prove

- **Raw circuit size.** Roughly 1.6 × 10^13 operations for a single 1,024-token request on an 8B model means any per-gate proving overhead gets multiplied trillions of times.
- **Heavy non-linear layers.** Every RMSNorm, softmax, activation curve, rescaling step, and argmax requires a [[lookup argument]] or range check at every token position and layer.
- **Fixed-point rescaling.** Mapping floating-point weights into finite fields forces fixed-point quantization, requiring explicit bit-truncation and rescaling proofs after every matrix multiply.
- **Sequential generation.** While a finished 512-token reply can be *checked* in a single parallel pass using causal masking, *generating* those 512 tokens still has to happen sequentially, one token after another.
- **Witness memory footprint.** The prover must hold, interpolate, and commit to all intermediate activations across the sequence alongside the model weights themselves.
