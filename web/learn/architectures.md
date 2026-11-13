Every system that proves inference has to answer the same four questions: how the computation is written down, how the weights are committed, how a long run is broken into manageable pieces, and what statement comes out at the end. The first two choices are separate, and systems freely mix and match them. This page walks through three ways to represent the computation, commitments built from hash functions alone, the technique of cutting a run into segments and joining them, and finally the non-proof verification methods on the board. Every system named here serves as an example, described in its publisher's own words at the pinned commit we read. Nothing on this page ranks one design against another.

## Circuit compilers

**The mechanism.** Export the model as a computation graph, compile the entire graph into a single system of constraints, and prove it with a general-purpose SNARK.

**In their words.** [EZKL](https://github.com/zkonduit/ezkl/blob/e196b111c1bafaa61b92ae431cd3c3fe9371da05/README.md) is "a library and command-line tool for doing inference for deep learning models and other computational graphs in a zk-snark". [ZKML](https://ddkang.github.io/papers/2024/zkml-eurosys.pdf) is "built on the halo2 proving system".

**What it makes cheap.** Broad model coverage for anything that exports cleanly, along with compact proofs of a few tens of kilobytes or less. EZKL's README notes that its proofs can be verified "on-chain (with the Ethereum Virtual Machine), in a browser, or on a device". Verification times are not always tiny, though: the ZKML authors report between 11.98 and 18.70 seconds to verify their distilled GPT-2 model.

**What it makes expensive.** Prover time and memory, which scale with every operation in the graph. As the ZKML authors write: "The largest model we can prove with under 1TB of RAM is the distilled version of GPT-2".

**What it trusts.** The underlying proof system, plus a trusted setup if it uses a pairing-based commitment scheme. In the ZKML paper's words, one commitment option "requires a one-time, universal trusted setup", while the transparent alternative "requires larger proofs and higher verification time".

## Virtual machines

**The mechanism.** Compile the inference program for a virtual instruction set and prove that the virtual processor executed it properly. Any program written in a standard language like Rust can be proved this way without hand-building a circuit.

**What it makes expensive.** Emulating the processor itself. A single matrix multiplication turns into a long trace of CPU instructions, each of which has to be proved. The authors of [Jolt Atlas](https://arxiv.org/abs/2602.17452), whose prover grew out of a virtual machine project, explain why they moved away from instruction emulation: "Unlike zkVMs (zero-knowledge virtual machines), which emulate CPU instruction execution, Jolt Atlas adapts Jolt's lookup-centric approach and applies it directly to ONNX tensor operations."

We know of no published run proving a billion-parameter language model inside a general-purpose virtual machine.

## Tensor provers on sumcheck

**The mechanism.** This is the approach [the previous page](/forward-pass) walked through. Each layer reduces to a [[sumcheck]] claim over tensors, each non-arithmetic step goes to a [[lookup argument]], and a [[polynomial commitment]] binds the weights.

**In their words.** [zkCNN](https://eprint.iacr.org/2021/673) introduced "a new sumcheck protocol for proving fast Fourier transforms and convolutions with a linear prover time, which is even faster than computing the result asymptotically". [zkLLM](https://arxiv.org/abs/2404.16109) added "tlookup, a parallelized lookup argument designed for non-arithmetic tensor operations". [DeepProve](https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/README.md) pairs "efficient sum-check protocols" for linear operations with "LogUp-GKR lookup arguments" for the non-linear layers.

**What it makes cheap.** Linear algebra, which accounts for most of the arithmetic in a language model.

**What it makes expensive.** Everything that is not a polynomial identity. Beyond that, the choice of polynomial commitment dictates proof size, verification time, and trust assumptions. Systems in this family use commitments based on discrete logarithms without a trusted setup, commitments based on elliptic-curve pairings, or commitments built from hashes alone (covered next).

**A caution from one of them.** The zkLLM [repository](https://github.com/jvhs0706/zkllm-ccs2024/blob/993311ea8e2346b90efacb35337b2e3cfe0d6f8d/README.md) notes that its released code is "an interactive proof" with the prover and verifier running side by side in the same process, and that it "has NOT undergone security auditing".

## Commitments built on hashes alone

**The mechanism.** A commitment constructed strictly from a cryptographic hash function: the data is expanded with an error-correcting code and hashed into a Merkle tree over a small [[field]]. There are no elliptic curves and no [[trusted setup]], and hashing maps well onto GPU hardware. What sits above the commitment layer varies from system to system.

**In their words.** FlashProve's [guide](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/how-it-works.md) writes: "The proof is hash-based: an interactive oracle proof made non-interactive with Merkle trees and Fiat-Shamir." It adds that "Sumcheck and lookup arguments are designed to reduce" the claim that the committed numbers represent a valid run of the model "to a few linear claims". It therefore represents the forward pass like the tensor provers above, while committing with hashes. SASH describes itself as "[A STARK prover for the decode step of a quantized transformer](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/4f41667297430a598165c4a8604258fe37d952ae/README.md#L3-L4)". Its [statement document](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/4f41667297430a598165c4a8604258fe37d952ae/docs/statement.md#L113-L115) explains that "the softmax identities and the accumulation are constraints of one AIR" and that "each matmul is a Freivalds check against the committed weights": an algebraic execution trace rather than a layer-by-layer sumcheck reduction. [VerInf](https://github.com/JamesPetrie/VerInf/blob/7947bb9a6c7ec86ea97927c76370b3920b6269f6/README.md) and [Attestable](https://attestable.com/blog/proving-llms-scale) also build their commitments from hashes alone.

**What it makes cheap.** Committing to large tensors, by hashing directly on the GPUs that run the model.

**What it makes expensive.** Proof size and working memory. Proofs in this family range from megabytes to gigabytes, and the prover has to hold the model, the witness, and its error-correcting encoding in memory at the same time.

**What it trusts.** A hash function modelled as a [[random oracle]], alongside coding parameters whose [[soundness]] each publisher states differently. FlashProve states a machine-checked bound for a verifier written in Lean, while its [known limits](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/known-limits.md) note that "Nothing is proved of the C++ verifier that the examples and most users run". SASH configures its parameters for "100 conjectured bits". Attestable states that it upholds "100 bits of security" without specifying whether that figure is proven or conjectured.

Several 2026 systems that report runs on multi-billion-parameter models rely on hash-based commitments. None of them presents itself as finished production software: FlashProve calls itself "A research artifact: not maintained, not accepting contributions", SASH is a "ZK Inference Prover Measurement Prototype", VerInf is a "Research prototype; no security audit of the full construction.", and Attestable describes its numbers as "These are alpha results."

## On top of any of them: cut and join

A long forward pass can be sliced into pieces by layer, by token block, or both, producing a separate proof for each piece. That allows pieces to be proved in parallel while keeping each piece small enough to fit in memory. [NanoZK](https://arxiv.org/abs/2603.18046) proves "independently provable layers linked by a SHA-256 commitment chain". SASH proves a two-dimensional grid of segments, and its `boundary-grid` command "checks that the segments fit together".

The catch is at the seams. Every activation that crosses from one piece to the next must be committed and verified on both sides of the boundary. SASH's documentation spells out what an unchecked seam would allow: "the segments could each be honest while the sequence they form is not".

## Two questions that cut across families

**What does one proof cover?** Three patterns show up across systems. Some produce one proof per generated token. Others run a single pass over the prompt concatenated with the claimed reply, certifying every token at once: in DeepProve's words, "the model's prediction at position `t` certifies the token at position `t+1`". A third group proves a looser statement about a reply served in standard floating point: VerInf "bounds the unexplained information" in the reply, and FlashProve includes a second verification policy whose acceptance, its guide notes, "says much less than `YES`".

**Is it built for one model, or one shape of model?** Many provers are tailored to specific architectures or dimensions. FlashProve's [source](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/prover/weights_blocks/gguf_source.cuh#L29-L30) states that "only models of width 5120 and head width 128 are supported". SASH's [results repository](https://github.com/sg-ai-safety-hub/zk-inference-results/blob/11decec3c0b62c707618aab5deb82750b355d202/docs/statement-gap.md) describes its target as "Dense Llama-shaped decoder blocks". That specialisation is why this benchmark is organised as a ladder of models with one row per system on each rung, and why every system page names the exact model its row runs on.

## Checks that are not proofs

The [ladder](/) lists several systems as "another kind of check". They are not cryptographic proofs. VerInf proves a different mathematical statement and is listed under "a different statement". The remaining systems tackle the same practical question (which model produced this reply?) by other means, each trading away part of what a cryptographic proof provides.

| Kind | How it works | What it rests on |
|---|---|---|
| [[Attestation]] by hardware | A processor signs a report of the software binary it booted. [Tinfoil](https://tinfoil.sh/blog/2026-02-03-proving-model-identity) extends that report to the model weights so the machine "cannot read bytes that don't match the committed hash". Inference then runs at nearly native GPU speed | The chip manufacturer, and physical protection of the server. The [TEE.fail](https://tee.fail/) researchers forged hardware attestations using an interposer on the memory bus, an attack vector chip vendors place outside their threat model |
| [[Recomputation]] with a referee | Two or more providers run the same request, and a referee settles disputes by re-executing a single disagreed step. [Verde](https://arxiv.org/abs/2502.19405)'s authors state "a guarantee of obtaining the correct result if at least one of them is honest" | At least one honest provider, bit-for-bit deterministic execution, and a referee who holds the model weights |
| Fingerprints and sampled reruns | The provider sends a compact trace of internal activations, or just the reply itself, and a checker holding the model reruns and compares. [TOPLOC](https://arxiv.org/abs/2501.16007) hashes intermediate activations. [DiFR](https://arxiv.org/abs/2511.20621) compares tokens generated under a shared random seed | A verifier that holds the model weights and has the compute to rerun them. The guarantee is statistical, and for activation fingerprints it is an empirical detection rate rather than a proven bound |

Among these alternatives, only hardware attestation keeps the weights hidden from the verifier, and it does so by shifting trust to the chipmaker and the server room. [Three ways to check](/three-ways) in the policy track examines that trade-off in detail.

## Where each system stands on this site

The ladder includes every system we have catalogued, whether we have run it or not. Whenever a system has no row, we state why: its licence, no public verifier, no configuration at the request, another kind of check, a different statement, or not run yet. If a team wants its system added or updated, [open an issue](https://github.com/ai-verification-observatory/inference-proofs/issues): we run upstream releases unpatched and write every claim card directly from the system's own documentation.
