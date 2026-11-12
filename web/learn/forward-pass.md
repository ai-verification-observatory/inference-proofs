A forward pass is mostly matrix products, and those are the cheap part to prove. The cost lies in committing to the data and in every step that is not a matrix product. This page follows a single number through a single layer, then widens to a layer, a model and a reply. It assumes the five ideas of [the previous page](/proof-systems).

## One number of one layer

One output of a linear layer is an inner product: a row of weights a times the activations b that enter the layer. Take four weights and four activations, and say the prover claims that their inner product is 25. The verifier holds neither vector.

The [[sumcheck]] protocol proves it by halving the problem. In each round the prover splits the sum into two halves by one bit of the index and sends them, with one extra value that pins down how the two halves blend. The verifier checks that the halves add up to the claim. Then it draws a random number r. The prover blends the two halves of each vector with weights `1 - r` and `r`. The verifier holds no vector, so it computes the new claim from the three values it was sent: the value at r of the one polynomial of degree two that passes through them. The vectors are now half as long, and the new claim is about their inner product. After two rounds, four numbers have become one.

:::explore sumcheck
The inner product of four weights and four activations, modulo 97. An honest prover is always accepted. A prover that claims 26 has to send a first message that is not the true one, and the lie surfaces at the last line unless a draw lands on one of two unlucky values out of 97. Over two rounds that happens 384 times in 9,409, about 4 in 100, and no strategy does better. The bound, rounds × degree / field size, is 4 in 97. With challenges drawn from 2^128 numbers the bound is below 1 in 10^37. Provers that compute in a 31-bit or 64-bit field draw their challenges from a larger extension field for that reason.
:::

Three things about this small run carry over to a model of any size.

- **The verifier's work is small.** Per round it adds two numbers and evaluates one small polynomial. For a vector of n numbers there are log n rounds: 30 rounds for a billion numbers.
- **The prover's work is about the size of the data.** It folds each vector once per round, and the vectors halve each time, so the total is a small multiple of n.
- **A lie is caught with high probability.** Each message commits the prover to a polynomial before the next random draw, and two different polynomials of low degree agree almost nowhere.

## What the verifier is left holding

The last line of the run needs two numbers: the blended weights a(r) and the blended activations b(r), each a single evaluation of a [[multilinear extension]] at a random point. The verifier has neither vector, so it gets these two numbers in two different ways. They are the two halves of a proof of inference built on sumcheck. Other designs answer the same two needs by other routes.

**The weights come from the commitment.** The operator committed to its model once, with a [[polynomial commitment]]. For a(r) it sends an opening: a short proof that the committed weights, blended at r, give this value. This is the only place the model enters. The verifier never sees a weight, and every proof opens the same commitment at fresh random points, so one commitment serves every request.

**The activations become the next claim.** The vector b is the output of the layer before. So b(r) is a claim of exactly the kind we started with, about that layer, and the same step applies to it. The proof walks backwards, layer by layer, until it reaches the input, where the verifier can compute the blend itself, from the prompt. This backward walk is the pattern of the [GKR protocol](https://doi.org/10.1145/1374376.1374396).

A whole matrix product needs no more than this. To check C = A·B, the verifier draws one random blend of the rows and one of the columns, and a single sumcheck over the middle index settles it ([Thaler, 2013](https://eprint.iacr.org/2013/351)). The prover's work beyond computing the product is in proportion to the size of the matrices, not to the cost of multiplying them. So the product is cheap to prove. Committing to the data it was computed on is not cheap: what stays expensive is the commitments behind a(r) and b(r), and every step that is not a matrix product.

## The steps that are not arithmetic

A [[field]] has addition and multiplication. It has no rounding, no comparison and no *largest of*. A transformer needs them: it rescales after every multiplication, applies an activation function, normalises, takes a softmax and, to decode greedily, picks the largest score.

Provers handle these with a [[lookup argument]]. Fix a public table that lists every input of the operation with its output, at the precision in use. The prover then shows that each pair it used is a row of the table. One way to do it ([Haböck, 2022](https://eprint.iacr.org/2022/1530)) turns *every one of my values is in the table* into an equality of two sums of fractions, checked at a random point, and that equality is again a sumcheck.

Lookups have two consequences for every system on this site, and a third follows from them.

- **Cost follows the count.** Each activation of each layer at each token is one lookup or more, and published breakdowns show it. For GPT-2 on 32 threads, the [zkGPT](https://www.usenix.org/system/files/usenixsecurity25-qu-zkgpt.pdf) authors report 12.1 of 21.8 seconds of proving in lookups, and the [DeepProve](https://eprint.iacr.org/2026/1112) authors report that "more than 50% of the prover cost comes from activation functions, Softmax, and requantization".
- **Precision is paid for in lookups.** A table for 16-bit inputs has 65,536 rows. Wider values are cut into digits, each looked up in a small table, so the cost grows with the bits kept. So provers keep few bits.
- **The proved model is therefore a quantized copy.** The statement is exact about that copy. How far the copy is from the publisher's model is a separate question, which the [Fidelity check](/method#fidelity-is-the-proved-model-the-publisher-s) asks.

## From one pass to a reply

A reply of 512 tokens is produced by 512 passes, each reading what the earlier ones cached. A proof does not have to follow them one by one, for the reason that training uses. With a causal mask, one pass over the prompt followed by the claimed reply computes, at every position, the model's choice for the next token. If each choice equals the next claimed token, the reply is the greedy one. In the words of [DeepProve's documentation](https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/README.md), "the model's prediction at position `t` certifies the token at position `t+1`".

A prover still has to produce the reply before it can prove it, and with exactly the arithmetic the proof will use, or the two disagree at some token. On this site that generation is counted in a system's cost, and printed apart where a system does it in a phase of its own. See [Where the cost goes](/cost).

Long computations are also cut into pieces, each with its own proof, and the verifier then checks each piece and each join. [Design families](/architectures) describes the technique, and [The statement](/statement) says why an open join proves less than it appears to.

## Hiding the weights

Nothing above hides anything yet. The prover's messages are values of polynomials built from the weights and the activations, and they leak. The [page before this one](/proof-systems#zero-knowledge-is-a-separate-property) says what [[zero knowledge]] adds. For a sumcheck prover it means masking every sumcheck message with a random polynomial and blinding every commitment ([Chiesa, Forbes and Spooner, 2017](https://eprint.iacr.org/2017/305)), in the program that runs and not only in the protocol on paper.

## What the verifier ends up doing

The verifier recomputes the hashes that fix each random draw, checks one sum per round, evaluates the blends of the prompt and of the reply for itself, and checks the openings of the model commitment and of the commitments made during the proof. It needs four things: the commitment, with the public configuration it was made under (the architecture, the scales, the parameters of the proof), the prompt, the reply and the proof. The configuration has to come from the same trusted source as the commitment. It does not need the weights, and for the systems run here it needs no GPU. Our [No weight file](/checks#no_weight_file) check tests part of that, by tracing every file a verifier opens on a machine with no GPU and no model file.

Real systems differ in everything this page left abstract: which commitment scheme, how lookups are batched, whether pieces are joined by recursion or by a grid of commitments, and which model they are built around. [Design families](/architectures) groups them by those choices.
