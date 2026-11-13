Every system that proves inference answers the same questions: how the computation is written down, what the weights are committed with, how a long computation is cut up, and which sentence comes out at the end. The first two are separate choices, and a system can share one answer with one neighbour and the other with another. This page takes three ways to write the computation down, then the commitments built on hashes alone, then the technique of cutting and joining, then the checks that are not proofs. A system named here is an example, described in its publisher's words at the version we read. Nothing here ranks one against another.

## Circuit compilers

**The mechanism.** Export the model as a graph, lower the whole graph to one system of constraints, and prove it with a general-purpose SNARK.

**In their words.** [EZKL](https://github.com/zkonduit/ezkl/blob/e196b111c1bafaa61b92ae431cd3c3fe9371da05/README.md) is "a library and command-line tool for doing inference for deep learning models and other computational graphs in a zk-snark". [ZKML](https://ddkang.github.io/papers/2024/zkml-eurosys.pdf) is "built on the halo2 proving system".

**What it gives.** Any model that exports, and a small proof: a few tens of kilobytes or less. EZKL's README says its proofs can be verified "on-chain (with the Ethereum Virtual Machine), in a browser, or on a device". Check times are not uniformly small: the ZKML authors report between 11.98 and 18.70 seconds to verify their distilled GPT-2.

**What it makes expensive.** The prover's time and memory, which grow with every operation of the graph. The ZKML authors report: "The largest model we can prove with under 1TB of RAM is the distilled version of GPT-2".

**What it trusts.** The underlying proof system, and a trusted setup for one of its two commitment schemes. In the same paper's words, one commitment scheme "requires a one-time, universal trusted setup", and the transparent alternative "requires larger proofs and higher verification time".

## Virtual machines

**The mechanism.** Compile the inference program for a virtual processor, and prove that the processor ran it. Any program in a language such as Rust can be proved this way without designing a circuit.

**What it makes expensive.** The machine itself. A matrix product becomes a long run of emulated instructions, each of which has to be proved. The authors of [Jolt Atlas](https://arxiv.org/abs/2602.17452), whose prover comes from a virtual machine project, write: "Unlike zkVMs (zero-knowledge virtual machines), which emulate CPU instruction execution, Jolt Atlas adapts Jolt's lookup-centric approach and applies it directly to ONNX tensor operations."

We know of no published run of a language model of a billion parameters inside a general-purpose virtual machine.

## Tensor provers on sumcheck

**The mechanism.** The one [the previous page](/forward-pass) walked through. Each layer is a [[sumcheck]] claim about tensors, each non-arithmetic step goes to a [[lookup argument]], and a [[polynomial commitment]] binds the weights.

**In their words.** [zkCNN](https://eprint.iacr.org/2021/673) introduced "a new sumcheck protocol for proving fast Fourier transforms and convolutions with a linear prover time, which is even faster than computing the result asymptotically". [zkLLM](https://arxiv.org/abs/2404.16109) added "tlookup, a parallelized lookup argument designed for non-arithmetic tensor operations". [DeepProve](https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/README.md) lists "efficient sum-check protocols" for its linear operations and "LogUp-GKR lookup arguments" for the rest.

**What it makes cheap.** Linear algebra, which is most of a model.

**What it makes expensive.** Everything that is not a polynomial identity. And the choice of commitment decides the rest: proof size, the verifier's time and what has to be trusted. Systems in this family use commitments based on discrete logarithms with no setup, on pairings, or on hashes (for hashes alone, see the next section).

**A caution from one of them.** The zkLLM [repository](https://github.com/jvhs0706/zkllm-ccs2024/blob/993311ea8e2346b90efacb35337b2e3cfe0d6f8d/README.md) states that its code is "an interactive proof", with prover and verifier implemented side by side, and that it "has NOT undergone security auditing".

## Commitments built on hashes alone

**The mechanism.** A commitment built only from a hash function: the data is extended with an error-correcting code and hashed into a Merkle tree, in a small [[field]]. There is no elliptic curve and no [[trusted setup]], and hashing runs well on a GPU. What sits above the commitment varies from one system to the next.

**In their words.** FlashProve's [guide](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/how-it-works.md) says: "The proof is hash-based: an interactive oracle proof made non-interactive with Merkle trees and Fiat-Shamir." It adds that "Sumcheck and lookup arguments are designed to reduce" the claim that the committed numbers are a correct run of the model "to a few linear claims". So it writes the computation down as the family above does, and commits with hashes. SASH describes itself as ["A STARK prover for the decode step of a quantized transformer"](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/README.md). Its [statement document](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/docs/statement.md) says that "the softmax identities and the accumulation are constraints of one AIR" and that "each matmul is a Freivalds check against the committed weights": a trace of the computation, not a claim per layer. [VerInf](https://github.com/JamesPetrie/VerInf/blob/7947bb9a6c7ec86ea97927c76370b3920b6269f6/README.md) and [Attestable](https://attestable.com/blog/proving-llms-scale) also build on hashes alone.

**What it makes cheap.** Committing, by hashing on the GPU that runs the model.

**What it makes expensive.** Bytes and memory. Proofs in this family run from megabytes to gigabytes, and the prover holds the model, the witness and its encoding at once.

**What it trusts.** A hash function modelled as a [[random oracle]], and parameters whose [[soundness]] each publisher states in its own way. FlashProve states a proven bound for a verifier written in Lean, and its [known limits](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/known-limits.md) say that "Nothing is proved of the C++ verifier that the examples and most users run". SASH's code sets its parameters for "100 conjectured bits". Attestable states that it upholds "100 bits of security" and does not say whether that is proven or conjectured.

Several of the 2026 systems that report runs on models of billions of parameters use such commitments. None presents itself as a finished product. In their words: "A research artifact: not maintained, not accepting contributions" (FlashProve), "ZK Inference Prover Measurement Prototype" (SASH), "Research prototype; no security audit of the full construction." (VerInf), "These are alpha results." (Attestable).

## On top of any of them: cut and join

A long computation can be cut into pieces, by layer, by block of positions or both, with one proof per piece. The pieces can be proved in parallel and each fits in memory. [NanoZK](https://arxiv.org/abs/2603.18046) proves "independently provable layers linked by a SHA-256 commitment chain". SASH proves a grid of segments, and its `boundary-grid` command "checks that the segments fit together".

The price is at the joins. Every value that crosses from one piece to the next has to be committed and checked on both sides. SASH's documentation says what an unchecked join would mean: "the segments could each be honest while the sequence they form is not".

## Two questions that cut across families

**What does one proof cover?** Three answers recur. One proof per generated token. One pass over the prompt followed by the claimed reply, which certifies every token at once: in DeepProve's words, "the model's prediction at position `t` certifies the token at position `t+1`". Or a looser sentence about a reply that was served in floating point: VerInf "bounds the unexplained information" in the reply, and FlashProve offers a second policy whose accept, its guide says, "says much less than `YES`".

**Is it built for one model, or one shape of model?** Several systems are. FlashProve's [source](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/prover/weights_blocks/gguf_source.cuh#L29-L30) states that "only models of width 5120 and head width 128 are supported". SASH's [results repository](https://github.com/sg-ai-safety-hub/zk-inference-results/blob/11decec3c0b62c707618aab5deb82750b355d202/docs/statement-gap.md) describes what it proves as "Dense Llama-shaped decoder blocks". This is the reason the benchmark is a ladder of models with a row per system per model. A system's page names the model its row runs on.

## Checks that are not proofs

The [ladder](/) lists some systems as "another kind of check". They are not proofs. VerInf, a proof of a different sentence described above, is listed apart, as "a different statement". The others address the same question, which model gives this reply, by other means, and each answers a narrower one.

| Kind | How it works | What it rests on |
|---|---|---|
| [[Attestation]] by hardware | A processor signs a report of what it started. [Tinfoil](https://tinfoil.sh/blog/2026-02-03-proving-model-identity) extends the report to the weights: the machine "cannot read bytes that don't match the committed hash". Inference then runs at close to full speed | The chip's maker, and the machine not being opened. The [TEE.fail](https://tee.fail/) authors forged an attestation with a device on the memory bus. Vendors place such attacks outside their threat model |
| [[Recomputation]] with a referee | Two or more providers run the same work, and a referee settles a disagreement by rerunning one step. [Verde](https://arxiv.org/abs/2502.19405)'s authors state "a guarantee of obtaining the correct result if at least one of them is honest" | One honest provider, bit-for-bit reproducible arithmetic, and a referee who holds the model |
| Fingerprints and sampled reruns | The provider sends a compact trace of its computation, or nothing beyond the reply, and a checker with the model reruns and compares. [TOPLOC](https://arxiv.org/abs/2501.16007) hashes intermediate activations. [DiFR](https://arxiv.org/abs/2511.20621) compares tokens under a shared random seed | A checker that holds the model and can run it. The guarantee is statistical, and for the fingerprints it is an observed detection rate, not a bound |

Only attestation hides the weights from the party that checks, and it moves the trust to hardware. That trade is the subject of [Three ways to check](/three-ways) in the policy track.

## Where each system stands on this site

The ladder lists every system we have catalogued, run or not. A system with no row has one stated reason: its licence, no public verifier, no configuration at the benchmark's request, another kind of check, a different statement, or not yet run. A team that wants its row can [open an issue](https://github.com/ai-verification-observatory/inference-proofs/issues): we run the system unchanged and write its claim card from its own documents.
