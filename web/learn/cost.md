Proving a reply costs a multiple of serving it without a proof, and that multiple is the single figure this benchmark ranks by. This page explains how the multiple is defined, where a prover spends its time, and how to read a cost claim without being misled.

## The figure

:::figure session
One session from a cold start. Proofs are released in groups because a prover can batch work across requests and emit their proofs together. The steady interval runs from the release of the first group to the release of the last.
:::

The multiple compares two measurements in GPU-seconds on the same hardware:

- **m** is the GPU time of the steady interval divided by the number of replies released after the first group. When a system generates its replies in a separate phase before proving, that phase's GPU time divided by all replies in the session is added to m. In short, m is the marginal GPU cost of one more proved reply once the prover is warmed up, always including the work of generating the reply itself.
- **b** is the GPU cost of one unproved reply: the publisher's release of the model running on a pinned serving engine with default settings at full load.
- **The [[multiple]]** is m divided by b on the same model. Because both numerator and denominator run on the same GPU type, the ratio in GPU-seconds is also the ratio in hardware dollars.

:::measured rows
:::

If a system releases too few groups in a session, or releases them at uneven rates, it never reaches a measured steady state and receives no multiple. Instead, its row reports the whole-session GPU cost divided by b, explicitly labelled as whole-session, and sits below every row that achieved a steady multiple.

## What is inside m

To produce and prove a reply, a system carries out six distinct jobs that scale in different ways:

1. **Generate the reply.** Under an exact-match statement, the reply must be produced token by token using the committed model's exact arithmetic. Standard serving engines run floating-point kernels across hundreds of batched requests at once. Prover generators often do not: FlashProve's integer-model package, for instance, [notes](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/integrations/vllm/integer_model/README.md#L18-L19) that it runs "greedy decoding, one sequence at a time, one GPU".
2. **Record the witness.** The prover runs a forward pass that saves every intermediate activation that the proof will need: each layer's output at every token position.
3. **Commit to what cannot be reduced away.** A trace-based prover commits to every recorded intermediate value. A sumcheck prover reduces claims from layer to layer and commits mainly to the activations entering non-arithmetic operations. Either way, committing means hashing those values or multiplying elliptic-curve points by them, element by element.
4. **Prove the linear steps.** The matrix multiplications are proved via [[sumcheck]] or random linear checks inside the trace, scaling with the size of the weight matrices.
5. **Prove the non-linear steps.** Every activation function, normalisation, rounding step, and comparison is proved through a [[lookup argument]] or range check.
6. **Open and assemble.** Finally, the prover opens the weight commitment and witness commitments at the random evaluation points chosen during the protocol, and writes out the proof file.

Two published timing breakdowns of sumcheck-based provers both find that more than half of the prover's time goes to steps outside the matrix multiplications, though the two systems bottleneck in different places. For GPT-2 at 512 tokens on 48 CPU threads, the [DeepProve](https://eprint.iacr.org/2026/1112) authors report that 57 % of prover time goes to committing to the witness and 35 % goes to the interactive proof, with linear algebra taking just 15 % of the interactive proof. For GPT-2 on 32 CPU threads, the [zkGPT](https://www.usenix.org/system/files/usenixsecurity25-qu-zkgpt.pdf) authors report 12.1 out of 21.8 seconds in lookup arguments and 0.8 seconds in the step they call commit advice. Those numbers come from the authors' own workloads rather than this benchmark, and in both cases the matrix products are the smaller share of the work.

When a system generates its replies in a separate phase before proving begins, our harness times that phase separately and splits m into two parts: generation, and commit and proving. The two-tone bar underneath a multiple on the [ladder](/) shows that split. It tells you how much of a system's cost comes from running its integer generator and how much comes from everything after, including both witness recording and cryptography.

Two costs sit outside m. First, committing to the model weights happens once per session before any request arrives; it is excluded from steady-state m and included in the whole-session figure. Second, verification is paid by the relying party rather than the prover, so each row reports verification time and proof size separately.

## Why the multiple is large

Steps 3 through 6 revisit every number in the forward pass multiple times, replacing fast hardware arithmetic with much heavier finite-field and cryptographic operations.

During ordinary inference, a GPU multiplies and adds 8-bit or 16-bit numbers in massive parallel blocks. A cryptographic proof works over a finite [[field]]. In a field larger than 2^128, a single field multiplication takes "[at least about ten 64-bit machine multiplications](https://a16zfrontier.com/posts/article/measuring-snark-performance-frontends-backends-and-the-future/)" by a 2022 estimate. The 31-bit and 64-bit fields favoured by GPU provers are much faster per element, though random challenges must then be drawn from an extension field on top. Committing to the trace hashes every value or multiplies an elliptic-curve point by it, and a lookup argument spends several field operations plus a commitment entry to verify a single comparison that a GPU executes in one clock cycle.

That overhead is the price of producing a check that requires neither the model weights nor re-execution. Provers become cheaper mainly by doing fewer cryptographic operations per model parameter, which is where the [design families](/architectures) diverge.

## Reading a cost without being misled

Every rule in our cost definition exists to close a way of making a prover look cheaper on paper without doing less work.

| A cost figure can be lowered on paper by | How the benchmark prevents it |
|---|---|
| Omitting warm-up or model commitment time without saying so | Both scopes are printed and labelled side by side: steady-state and whole-session |
| Counting replies by batch membership rather than completion | Replies are counted strictly by when their proof files are written and released |
| Proving only one token of a reply instead of the whole output | Accepted proofs must cover all 512 reply tokens |
| Comparing against a serving baseline running at low concurrency | The serving baseline is measured at full load, found by raising concurrency until throughput plateaus |
| Cherry-picking the lowest-cost single run | A ranked row requires three sessions, one per slot, with every session's value printed |
| Quantizing the model aggressively until proving is cheap | The Fidelity check gates ranking, and the KL divergence from the publisher's weights is printed beside it |
| Generating replies outside the proved arithmetic | Reply generation is timed and counted inside m |

Three practical limitations remain. First, the baseline uses one standard serving engine with default settings, not the highest throughput achievable with custom tuning. Second, the baseline serves the model at the publisher's released precision while provers run quantized copies, so the multiple combines proving overhead with that precision difference. Third, only GPU time is priced; CPU time, host RAM, and disk traffic are recorded but not folded into the ratio.

Finally, a multiple belongs to a single model. Two systems measured on different models have not been compared, regardless of their multiples.

## From a multiple to a bill

Most practical uses do not require proving every single reply. If a relying party verifies a random sample of traffic, part of the proving cost drops in proportion to the sampling rate. How much of the cost drops depends on the system's statement.

Under an exact-match statement (which every row on this board uses), a reply can be proved only if it was generated by the committed integer or fixed-point model. A reply generated by a standard floating-point engine like vLLM will diverge on at least one token and fail verification. As FlashProve's [guide](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/performance.md) reports: "At exact match a reply passes only if every token is the integer model's own choice: of 96 stored replies each from stock vLLM at 16 bits and at FP8, none did". Because an operator cannot know in advance which replies will be sampled for verification, every reply has to be generated by the committed model. That means the generation component of m is paid on 100 % of traffic, while only the proving component scales down with the sampling rate.

:::explore cost
The arithmetic of random sampling under exact match: you pay the generation cost on every reply, and the proving cost only on the sampled share.
:::

That formula applies directly to rows that separate generation from proving. When a system generates and proves inside a single combined loop, the benchmark cannot split the two costs. The simpler formula (1 + sample share × proving cost) only applies when replies served by a standard floating-point engine can be proved afterwards, which requires a statement with numerical tolerance that this benchmark does not currently run.

Auditing a random sample provides a [[sampled]] guarantee. Suppose an operator quietly substitutes a cheaper model on 1 reply in 100, and a verifier checks 1 reply in 1,000 chosen at random. Across 1,000,000 replies, 10 substituted replies will fall into the sample on average, and for each of those the operator cannot produce a valid proof. The probability that all 10,000 substituted replies slip past the sample is roughly 1 in 22,000. On the other hand, a single targeted substitution will be caught only 1 time in 1,000.

For sampling to work at all, the audit choice must happen after the reply is delivered. If the operator learns which requests will be checked before answering them, it can run the committed model on audited requests and substitute freely on the rest. The Level 2 draft calls this requirement "a reply chosen after serving".

## The verifier's side

A relying party pays two costs of its own: receiving and storing the proof bytes, and running the verifier program. Both are much smaller than proving, yet they vary widely across architectures: published proofs range from a few hundred bytes to tens of gigabytes, and verification times range from milliseconds to hours. The table at the top of this page lists both for every row. Keep the units in mind when reading them: verification time is measured in wall-clock seconds on an ordinary CPU with no GPU attached, whereas m is measured in GPU-seconds. Checking a proof on a CPU is not necessarily faster in wall-clock time than serving the reply on a GPU; its value is that the verifier needs neither a GPU nor the model weights. A relying party auditing a sample of high-volume traffic will run that verifier many times a day.
