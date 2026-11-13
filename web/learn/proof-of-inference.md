A proof of inference is a file accompanied by a small program called a verifier. The verifier reads the proof alongside a model commitment, a prompt, and a reply, and outputs a simple yes or no. On this benchmark, we ask every system to prove the same core claim: that a specific model committed to in advance, when run on this prompt, produces this exact reply. Crucially, the verifier reaches its verdict without holding the model weights and without re-running the model.

## Three roles

:::figure parties
Who holds what in a proof of inference, and what passes between them.
:::

- **The operator** runs the language model and serves replies (for example, an API provider, an AI lab, or a data centre operator). Because the operator also generates the cryptographic proofs, the cryptography literature calls this role the [[prover]].
- **The [[verifier]]** is a small software program that anyone can run on an ordinary CPU. It reads the public inputs and the proof file, and either accepts or refuses.
- **The [[relying party]]** is the person or institution deciding what the verifier's answer means in practice: a customer, an auditor, a regulator, or an international inspectorate. Technical standards deliberately separate the verifier from the relying party. In the IETF's remote attestation architecture ([RFC 9334](https://www.rfc-editor.org/rfc/rfc9334.txt)), a verifier produces verification results "to be used by a Relying Party". The verifier checks the math; the relying party decides whether the surrounding system deserves trust.

## The commitment: locking in a model before the run

Before serving any requests, the operator computes a cryptographic [[commitment]] to its model: a short digest that locks in all of the model's [[weights]] without revealing what they are. Auditing researchers [describe](https://arxiv.org/abs/2601.11699) a model commitment as "a tamper-evident digital fingerprint". If the operator changes even a single weight later, the commitment will no longer match.

People often compare a cryptographic commitment to a physical tamper-evident seal on a container, but that analogy breaks down in three important ways:

1. A physical seal guards a piece of hardware in a room, whereas a commitment only pins down a static array of numbers. It tells you nothing about which machines later run those numbers.
2. In physical safeguards, an outside inspector examines the container first and then applies the seal. Here, the operator computes the commitment on its own machines over weights nobody else can see.
3. A commitment by itself is just a string of bytes. Nothing inside that string tells you whether the underlying model is safe, capable, or authentic. For a commitment to mean anything to an outsider, someone has to bind that digest to a known model through a public release, an evaluation report, or an official register. Everything a proof establishes later is only relative to that committed digest.

## The proof: expensive to generate, cheap to check

Whenever a reply needs to be verified, the operator generates a proof showing that the committed model produces that reply on the given prompt. Building that proof takes far more compute than running the model normally. Checking the proof, on the other hand, is lightweight: the verifier runs on a standard CPU without a GPU or the model weights. The table below shows the proving overhead and verification time recorded for each system we have run.

How can a short CPU check verify trillions of matrix operations without re-running them? The core mechanism works like an algebraic spot-check. First, the operator encodes every intermediate step of the forward pass into polynomials and commits to them so it cannot change its intermediate values later. Next, random challenges determine where the verifier inspects those polynomials. Unlike a physical spot-check that only inspects one isolated box in a warehouse, evaluating a polynomial at a random point mixes information from the entire computation, so a single forged step almost anywhere corrupts the polynomial almost everywhere. A cheating prover can pass the check only if it gets lucky on the random challenge, and the protocol parameters are chosen so that the chance of a lucky guess is bounded by the [[security level]].

That makes the cost structure heavily lopsided: the operator pays a steep GPU bill to construct the proof, while the checker spends a fraction of a second (or a few seconds) of CPU time. Checking a proof is not necessarily faster than generating a reply on a GPU; its value is that the checker needs neither the GPU cluster nor the secret weights.

:::measured rows
Cost vs serving compares the GPU time of generating a proved reply against serving an unproved reply on the same model and GPU type. See [Reading a row](/before-you-rely#reading-a-row).
:::

## Three cryptographic properties

The [ZKProof Community Reference](https://docs.zkproof.org/pages/reference/reference.pdf) defines three standard properties for proof systems. Every prover on our ladder aims for the first two, and some also aim for the third:

- **Completeness.** An honest prover can always convince the verifier: "If the statement is true and both prover and verifier follow the protocol; the verifier will accept."
- **Soundness.** A cheating prover cannot convince the verifier of a false claim: "If the statement is false, and the verifier follows the protocol; the verifier will not be convinced." Soundness holds up to a tiny failure probability (the [[security level]]) under explicit mathematical assumptions.
- **Zero knowledge.** The verifier "will not learn any confidential information from the interaction with the prover but the fact the statement is true". In an inference proof, the confidential input being hidden is the model's weights.

Our five-petal [[glyph]] summarises what each publisher's documentation states about soundness and zero knowledge, alongside our own empirical tests. Because no finite test suite can prove that a system is unforgeable or zero-knowledge, we report the publisher's documented claims and quotes rather than certifying them ourselves; [How we compare](/method) explains how each petal is set.

## What an accepted proof does not tell you

When a verifier outputs "accept", it is easy to read too much into that verdict. Here are nine things an accepted proof does *not* establish, quoting the prover authors themselves where they make the same point.

:::note What a yes does not mean
**It does not mean the model is safe or aligned.** A proof verifies that a specific mathematical function was evaluated; it says nothing about how the model behaves. A dangerous or poorly trained model can be proved just as faithfully as a benign one.

**It does not show what else the cluster was doing.** As Anthropic (publisher of FlashProve) [notes](https://www.anthropic.com/research/provable-inference), a proof of inference "does not establish that the hardware is not, e.g., training on the side".

**It says nothing about how the model was trained.** Verifying a training run is a completely different problem with much less mature tooling.

**It does not prove the reply was generated live when the user asked.** A proof generated after the fact only shows that the committed model produces this reply for this prompt. As an [early verifiable-inference paper](https://arxiv.org/abs/2402.02675) put it, a proof shows that the provider holds a model that produces the output, "not that it necessarily served it earlier".

**It covers a quantized, deterministic copy of the model rather than standard floating-point serving.** Cryptographic proof systems require exact, bit-reproducible arithmetic, so today's provers operate on an integer or fixed-point [[quantization]] of the weights under greedy decoding. Anthropic [lists this](https://www.anthropic.com/research/provable-inference) explicitly among FlashProve's limitations: "The proof is about an integer model under greedy decoding."

**It does not cover surrounding system prompts, routers, or content filters.** The same model weights can behave very differently behind a hidden system prompt or post-generation filter that sits outside the proved computation.

**It does not hide the prompt, the reply, or the model's architecture.** Even when a proof system is zero-knowledge with respect to the weights, the verifier still sees the prompt, the reply, and structural constants like layer dimensions. Moreover, whether a specific implementation actually hides the weights is a statement by its publisher that our benchmark does not test.

**It cannot force an operator to hand over a proof.** An operator can always refuse to return a proof, claim a server error, or stall. What happens when a proof is missing is a policy or contract question, not a cryptographic one.

**It is not an absolute guarantee.** Every proof system rests on unproven hardness assumptions (or hash-function models) and on the absence of implementation bugs in the verifier.
:::

One extra caveat applies specifically to this benchmark. Our Level 1 ladder uses open-weights models so that anyone can reproduce our runs and compare outputs against the original weights. Because those weights are already public, weight secrecy is not the reason to use a proof on these specific models; the benefit here is being able to verify a reply on a laptop CPU without renting a multi-GPU node. Weight secrecy becomes critical when the same prover architectures are applied to proprietary models.

## What a verifier must reject

A verifier that says "accept" to everything is useless. For a proof to mean anything, the verifier must bind its verdict to three inputs: the committed model, the prompt, and the reply. If the verifier fails to check any one of those bindings, an operator can swap that input and still get a green light.

:::explore tamper
Our three tampering checks: what we modify in the verifier's input record, how a properly bound verifier responds, and what happens when a binding is missing. A check holds only when the verifier accepts the untouched proof and refuses the tampered one.
:::

Passing these three tampering checks confirms that the verifier refused the specific modifications we tested. It does not prove that a determined adversary could never forge a proof: cryptographic soundness rests on mathematical reductions and code audits, not black-box test cases.

## Where the technology stands today

In 2025, an [Oxford Martin School study](https://www.oxfordmartin.ox.ac.uk/publications/verification-for-international-ai-governance) described cryptographic proofs of inference as "impractical to apply at scale as of this writing", while noting in a footnote that with rapid algorithmic progress they "might rapidly become the most practical approach for verifying many AI-related questions".

Between August and November 2026, three separate teams released prototypes capable of proving replies from multi-billion-parameter language models, each reporting numbers on its own chosen model under its own measurement rules. All three teams describe their code as early research rather than production software: "[A research artifact: not maintained, not accepting contributions](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/README.md)" (FlashProve), "[ZK Inference Prover Measurement Prototype](https://github.com/sg-ai-safety-hub/zk-inference-prover)" (SASH), and "[These are alpha results.](https://attestable.com/blog/proving-llms-scale)" (Attestable). Before we launched this benchmark, we could find no third-party measurements of any of these systems, and no comparison running them on the same workload. The table above shows what we have run so far, and the main [ladder](/) lists every system we track alongside why unrun systems have not yet been run.
