A transformer's forward pass consists mostly of matrix multiplications, and surprisingly, those matrix multiplications are the cheapest part of the computation to prove. Almost all of the proving cost goes into committing to the execution trace and proving the non-linear steps (activations, normalizations, rescaling, and argmax). Building on the five ideas from [Proof systems, for ML engineers](/proof-systems), let's trace how a single inner product is proved and then scale up to a full layer and a multi-token reply.

## Proving a single inner product via sumcheck

Every entry in the output of a linear layer is the inner product of a weight row `a` and an activation vector `b`. Suppose we have four weights and four activations over the prime field modulo 97, and the prover claims that `<a, b> = 25`. How can the verifier check that sum without holding either `a` or `b`?

The [[sumcheck]] protocol verifies the sum by folding the problem in half each round:

1. In each round, the prover splits the sum into two halves according to the first index bit and sends the partial sums `s(0)` and `s(1)`, along with a third evaluation `s(2)` that uniquely determines the degree-2 polynomial connecting the two halves.
2. The verifier checks that `s(0) + s(1)` equals the current claimed total.
3. Next, the verifier draws a random field element `r`. Both sides fold the problem in half by blending the two halves with weights `1 - r` and `r`. Because the verifier does not hold the vectors, it computes the new target claim simply by evaluating the degree-2 polynomial `s` at `r`.
4. After two rounds of halving, a 4-element inner product is reduced to a claim about a single pair of blended scalars `a(r) · b(r)`.

:::explore sumcheck
Step through a two-round sumcheck for the inner product of four weights and four activations modulo 97. An honest prover always passes. If a cheating prover claims 26 instead of 25, it must send a false polynomial in Round 1, and that lie gets caught at the final check unless a random challenge happens to hit one of at most two root collisions out of 97. Across two rounds, a lie survives 384 times out of 9,409 possible challenge pairs (about 4%), bounded by `rounds × degree / field_size = 4 / 97`. When challenges are drawn from a 128-bit extension field, that false-pass probability drops below 1 in 10^37.
:::

Three properties of this toy example hold at any scale:

- **Verification is logarithmic.** In each round, the verifier adds two field elements and evaluates a degree-2 polynomial. Reducing an inner product of `n` elements takes `log_2(n)` rounds: just 30 rounds for a vector of a billion elements.
- **Prover work is linear in the vector length.** Because the vectors shrink by half after every round, folding them across all rounds takes a small constant multiple of `n` field operations.
- **Cheating is caught with overwhelming probability.** Each round forces the prover to lock in a degree-2 polynomial before seeing the random challenge `r`, and two unequal degree-2 polynomials can agree at most twice across the entire field.

## Discharging the final evaluation

At the end of the sumcheck rounds, the verifier needs two numbers to complete its check: the folded weight evaluation `a(r)` and the folded activation evaluation `b(r)`, each of which is a single point evaluation of a [[multilinear extension]]. Because the verifier holds neither the weights nor the activations, it obtains those two numbers in two different ways:

- **The weight evaluation `a(r)` comes from opening the model commitment.** Before the session started, the operator committed to its model weights using a [[polynomial commitment]]. To supply `a(r)`, the prover sends a short opening proof showing that the committed weight polynomial evaluates to `a(r)` at the random point `r`. Notice that the verifier never sees the individual weights, and the exact same model commitment can be opened at fresh random points across any number of user requests.
- **The activation evaluation `b(r)` becomes the target claim for the previous layer.** Because the activation vector `b` is simply the output of the preceding layer, checking `b(r)` is another evaluation claim of the exact same form! The protocol chains backward from the output layer to the first layer (the [GKR pattern](https://doi.org/10.1145/1374376.1374396)) until it reaches the input tokens, which the verifier holds in the clear and can evaluate on its own.

Proving a full matrix multiplication `C = A·B` is no harder than proving a single inner product: the verifier picks random multilinear weights for the rows and columns, reducing the entire matrix product to a single sumcheck over the shared inner dimension ([Thaler, 2013](https://eprint.iacr.org/2013/351)). Crucially, the extra prover work beyond computing `A·B` itself scales with the size of the matrices (`O(n^2)`), *not* with the `O(n^3)` cost of multiplying them. That is why linear algebra is the cheap part of proving a transformer.

## Proving non-linear steps with lookup arguments

Finite fields only give you exact addition and multiplication modulo `p`. They have no native notion of bit-truncation, division by a square root (RMSNorm), exponentials (softmax), GELU/SiLU curves, or finding the maximum score across a vocabulary (argmax).

To prove those non-linear operations, provers rely on [[lookup argument|lookup arguments]]. First, you precompute a public table listing every valid `(input, output)` pair for the non-linear function at the chosen fixed-point precision. Then, the prover demonstrates that every activation value in its execution trace appears as a valid row in that public table. Modern lookup protocols like [LogUp (Haböck, 2022)](https://eprint.iacr.org/2022/1530) reduce the claim *every element of my witness vector appears in this table* to an algebraic identity between sums of rational functions evaluated at a random challenge point, which is then proved with another sumcheck.

Using lookup tables for non-linearities shapes every inference prover in three ways:

- **Non-linear steps dominate proving time.** Every activation, normalization, and fixed-point rescaling at every layer and token position requires one or more lookups. In published benchmarks on GPT-2, the [zkGPT](https://www.usenix.org/system/files/usenixsecurity25-qu-zkgpt.pdf) authors report that lookup arguments consume 12.1 out of 21.8 seconds of total proving time, while the [DeepProve](https://eprint.iacr.org/2026/1112) authors report that "more than 50% of the prover cost comes from activation functions, Softmax, and requantization".
- **Higher precision explodes table work.** A lookup table over 16-bit inputs has `2^16 = 65,536` rows. To handle wider integers without gigantic tables, provers slice each number into smaller limbs (say, 8-bit chunks) and perform multiple lookups and range checks per value.
- **Provers therefore quantize aggressively.** To keep lookup tables small, provers operate on low-bit quantized copies of the model, which is why our [Fidelity check](/method#fidelity-is-the-proved-model-the-publisher-s) is essential to verify that the quantized copy still behaves like the original model.

## Proving a 512-token reply in one parallel pass

Generating a 512-token reply requires 512 sequential forward passes, since token `t+1` depends on token `t`. Fortunately, *proving* that 512-token reply does not require running 512 separate proofs! Once the full 512-token reply has been generated, the prover concatenates the 512-token prompt and the 512-token reply into a single 1,024-token sequence with a causal attention mask (just like teacher forcing during transformer training). A single parallel forward pass over that 1,024-token window computes the model's next-token prediction at every position simultaneously; if the argmax at position `t` matches token `t+1` across all 512 output positions, the entire greedy reply is certified at once. As [DeepProve's documentation](https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/README.md) puts it, "the model's prediction at position `t` certifies the token at position `t+1`".

Of course, the operator still has to generate those 512 tokens sequentially first, using the exact integer or fixed-point arithmetic that the proof checks. Our benchmark includes that sequential token generation in the system's cost multiple, and breaks it out separately whenever the system runs generation as a distinct phase (see [Where the cost goes](/cost)).

When a full sequence pass does not fit in GPU memory all at once, provers slice the pass into layer or token segments, prove each segment separately, and check that the boundary commitments match at the seams (see [Design families](/architectures) and [The statement](/statement)).

## Adding zero-knowledge to hide the weights

As noted on [Proof systems, for ML engineers](/proof-systems#zero-knowledge-is-a-separate-property), raw sumcheck transcripts and polynomial openings leak linear combinations of the weights and activations. Making a sumcheck-based inference proof [[zero knowledge|zero-knowledge]] requires masking each round's polynomial with a random blinding polynomial and using hiding commitments ([Chiesa, Forbes, and Spooner, 2017](https://eprint.iacr.org/2017/305)) throughout the actual executable implementation.

## What the verifier does at the end

When the proof file arrives, the verifier recomputes the Fiat-Shamir hashes to derive each round's challenge, checks the `s(0) + s(1)` sum in each sumcheck round, evaluates the multilinear extensions of the public prompt and reply tokens directly, and verifies the opening proofs against the model commitment and witness commitments. To do that, the verifier needs only four inputs: the trusted model commitment (alongside its public architecture and quantization parameters), the prompt, the reply, and the proof file. It never touches the model weights and requires no GPU. Our [Verify without weights](/checks#no_weight_file) check confirms this empirically by running every verification call on a CPU-only machine with no weight files on disk while tracing every `open()` system call.

Next, [Design families](/architectures) compares how different systems on our ladder instantiate these building blocks.
