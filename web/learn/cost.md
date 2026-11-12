A proved reply costs a multiple of a served one, and that multiple is the one figure this site ranks by. This page says what is inside the figure, where a prover's time goes, and how to read a cost without being misled by it.

## The figure

:::figure session
One session, from a cold start. Proofs are released in groups, because a prover can share work across a batch of requests and release the batch's proofs together. The steady interval runs from the release of the first group to the release of the last. A generation phase, where a system has one, counts in m too.
:::

Two quantities in GPU-seconds of the same kind of GPU, and their ratio.

- **m** is the GPU time of the steady interval, divided by the number of replies released after the first group. Where a system generates its replies in a phase of its own, before proving, that phase's GPU time divided by all the session's replies is added. So m is what one more proved reply costs once a system is running, and generating the reply is always inside it.
- **b** is what one served reply costs: the publisher's own release of the model, on a pinned serving engine with its defaults, at full load.
- **The [[multiple]]** is m over b, on one model. Both halves run on the same GPU at the same price, so the multiple is the same in dollars.

:::measured rows
The rows of the board. Under each figure: what was timed, and over how many sessions.
:::

A system whose sessions release too few groups, or uneven ones, has no steady state. It gets no multiple. Its row prints the cost of its whole sessions over b, labelled as cold sessions, and is placed below every row that has a multiple.

## What is inside m

A prover does six jobs for each reply, and they scale differently.

1. **Generate the reply.** Under exact match the reply has to be produced by the committed copy of the model, token by token. A serving engine does this job with floating point kernels and hundreds of requests batched together. The one generator run here so far does not: FlashProve's integer-model package [states](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/integrations/vllm/integer_model/README.md#L18-L19) "greedy decoding, one sequence at a time, one GPU".
2. **Record the witness.** Every intermediate value of the pass that will be proved is kept: each layer's output at each position.
3. **Commit to what cannot be reduced away.** A prover that works on a trace of the whole computation commits to every recorded value. A sumcheck prover passes claims from layer to layer and commits mainly to the values that enter the non-arithmetic steps. Committing means hashing the values or doing elliptic-curve arithmetic on them, value by value.
4. **Prove the linear steps.** The matrix products, by [[sumcheck]] or by a random check inside the trace. The work is in proportion to the size of the matrices.
5. **Prove the rest.** Each activation, normalisation, rounding and comparison, by a [[lookup argument]] or a range check.
6. **Open and assemble.** Open the model commitment and the witness commitments at the random points the proof arrived at, and write the file.

Two published breakdowns of provers built on sumcheck both put more than half of the time outside the matrix products. They do not split it the same way. The [DeepProve](https://eprint.iacr.org/2026/1112) authors report, for GPT-2 at 512 tokens on 48 CPU threads, 57 % of the prover's time in committing to the witness and 35 % in the interactive proof. Inside the interactive proof, the linear algebra is 15 %. The [zkGPT](https://www.usenix.org/system/files/usenixsecurity25-qu-zkgpt.pdf) authors report, for GPT-2 on 32 threads, 12.1 of 21.8 seconds in lookups and 0.8 seconds in the step they call commit advice. Those are their figures for their workloads, not this benchmark's. In both, the matrix products are the small part.

Where a system generates its replies in a phase of its own, before proving, the harness times that phase apart, and the row prints m in two parts: generation and proving. The bar under a multiple on the [ladder](/) is that split. It answers a question a total cannot: how much of a system's cost is producing the reply, and how much is everything after it. The second part is not only cryptography: it includes the pass that records the witness.

Two costs are outside m. The commitment to the model is made once per session, before any request. It is not printed on its own: it is inside the whole-session cost, which starts when the commit step starts. And checking is the verifier's work, not the prover's: the row gives the check time and the proof size per reply.

## Why the multiple is large

Steps 3 to 6 touch every number of the forward pass again, several times, with operations that are each far more expensive than the one that produced the number.

A GPU multiplies and adds 8-bit or 16-bit numbers in bulk. A proof works in a [[field]]. In a field larger than 2^128, each operation takes ["at least about ten 64-bit machine multiplications"](https://a16zfrontier.com/posts/article/measuring-snark-performance-frontends-backends-and-the-future/), by a 2022 estimate. The 31-bit and 64-bit fields that GPU provers favour are cheaper, and need an extension on top for their random challenges. A commitment then hashes each value or multiplies an elliptic-curve point by it. A lookup costs several field operations and a share of a commitment for one comparison that a GPU does in one instruction.

These operations buy a check that needs neither the weights nor the computation. A prover gets cheaper mostly by doing fewer of them per number of the model, and that is where the [design families](/architectures) differ.

## Reading a cost without being misled

Each rule of the benchmark's cost figure exists because there is a way to make a prover look cheaper without making it cheaper.

| A cost can be lowered on paper by | The rule |
|---|---|
| Leaving out start-up, or the commitment, and not saying so | Both scopes are printed and labelled: steady, and the whole session |
| Counting replies by batch membership | Replies are counted by when their proofs were released |
| Checking one token of a reply, not all of them | Every reply token must be covered by an accepted proof |
| Comparing with serving at low load | The baseline is taken at full load, found by raising the concurrency until the rate stops rising |
| Reporting only the lowest of several runs | Three sessions count, one per slot, and each value is printed |
| Quantizing the model until it is cheap to prove | The Fidelity check, and the KL figure printed beside it |
| Not generating the reply with the proved arithmetic | Generation is inside m |

Three limits remain, and the pages say so where they print a figure. The baseline is one engine with its defaults, not the highest throughput anyone could reach. It serves the publisher's precision, while the prover runs a quantized copy, so the multiple mixes the cost of proving with that difference. And only GPU time is priced: CPU, memory and storage are not.

A multiple is also a property of a system on one model. Two systems on two models have not been compared, whatever their multiples.

## From a multiple to a bill

Few uses need every reply proved. If a relying party is content with a random sample, part of the cost falls with the share. Which part depends on the statement.

Under exact match, the statement every row here is run under, a reply can be proved only if the committed copy of the model generated it. A reply from an ordinary serving engine differs in some token and fails. FlashProve's [guide](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/performance.md) reports: "At exact match a reply passes only if every token is the integer model's own choice: of 96 stored replies each from stock vLLM at 16 bits and at FP8, none did". The sample is drawn after serving, so every reply has to come from the committed copy, sampled or not. The generation part of m is then paid on every reply, and only the proving part falls with the share.

:::explore cost
The arithmetic of a sample: the generation part on every reply, the proving part on the share that is proved.
:::

The sum holds for a row that prints its two parts. A row with no split generates inside its proving interval, and the board cannot separate the two. The simpler sum, 1 + share × proving part, holds only if replies from an ordinary engine can be proved. That takes a statement with a tolerance, which this benchmark does not run.

A sample gives a [[sampled]] guarantee. Suppose an operator serves a different model for 1 reply in 100, and 1 reply in 1,000 is proved, chosen at random. Over 1,000,000 replies, 10 of the substituted ones are expected to fall in the sample, and for each the operator has no valid proof to give. The chance that none falls in it is about 1 in 22,000. A single substituted reply is caught 1 time in 1,000.

For this to work, the choice has to come after the reply. The operator must answer first and learn afterwards which replies it must prove, or it will prove only the ones it served honestly. The draft of Level 2 names this: "a reply chosen after serving".

## The verifier's side

A relying party pays twice for a proof: it stores or receives the proof, and it runs the check. Both are meant to be small next to the prover's work, and they differ a great deal from one system to another: in published reports a proof is a few hundred bytes or many gigabytes, and a check takes milliseconds or hours. The rows at the top of this page print both. Read them in their own units: the check time is in seconds of an ordinary processor, and m is in GPU-seconds. For a language model the check is not shorter than serving the reply on a GPU. Its worth is that it needs neither the GPU nor the weights. A relying party that checks a sample of a large service's traffic runs the verifier many times a day.
