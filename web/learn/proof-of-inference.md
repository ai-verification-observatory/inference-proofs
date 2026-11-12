A proof of inference is a file. A program reads it and answers yes or no. A yes means one sentence, which each system's publisher states. On this site the sentence asked of every system is: a model that was fixed in advance, run on this prompt, gives exactly this reply. The program reaches its answer without holding the model and without redoing the computation. This page explains how that is possible, in plain words, and spends as long on what a yes does not mean.

## Three roles

:::figure parties
Who holds what. The operator holds everything. The verifier is given four things and never the weights. The relying party acts on the verdict.
:::

- **The operator** runs the model and answers requests: a company serving an API, a lab, the operator of a data centre. It makes the proofs, so cryptographers call it the [[prover]].
- **The [[verifier]]** is a program. Anyone can run it. It reads a proof and accepts or refuses.
- **The [[relying party]]** is whoever acts on the result: a customer, an auditor, a regulator, an inspectorate. Technical standards keep the two apart. The IETF's architecture for remote attestation, [RFC 9334](https://www.rfc-editor.org/rfc/rfc9334.txt), describes a verifier as producing results "to be used by a Relying Party". The verifier says yes or no. The relying party decides what follows.

## The commitment: a number that fixes a model

Before any request, the operator computes a [[commitment]] to its model: a short value that fixes the model's [[weights]]. Publishing it does not publish them. A group of auditing researchers [describes it](https://arxiv.org/abs/2601.11699) as "a tamper-evident digital fingerprint". Change one weight and the commitment no longer matches.

A seal on a container is a partial picture, with three differences. A seal protects an object, and a commitment fixes data: it says nothing about which machine later runs. An inspector applies a seal to contents the inspector has checked, and here the operator computes the commitment itself, over weights nobody else sees. And a commitment is only a number. It does not say what it is a commitment to. Someone has to publish that this number stands for that model, and stand behind it: the developer, a public register, an auditor. Everything a proof later shows is relative to that number.

## The proof: costly to make, cheap to check

For a reply that is to be checked, the operator can produce a proof that the committed model, run on the prompt, gives that reply. Making the proof is far more work than computing the reply. Checking it is light by comparison: seconds or minutes on an ordinary processor in most published systems, with no GPU and no copy of the model.

How can a short check stand in for a long computation? By the logic of a spot check. The operator first fixes its answers in a form it cannot change afterwards. The check then picks at random where to look. Unlike an inspector's spot check, each look depends on the whole computation, so one false step anywhere shows up almost everywhere. A false answer passes only if the operator guessed where the check would look, and the numbers are chosen so that guessing is hopeless.

The cost is lopsided by design. The operator pays for the proof, and the checker pays seconds or minutes of processor time. That is not less than serving the reply on a GPU. Its worth is that it needs neither the GPU nor the weights.

:::measured rows
What this site has run so far. The multiple is the cost of a proved reply as a multiple of an unproved one, on the same model and the same kind of GPU. [How to read a row](/before-you-rely#reading-a-row).
:::

## Three properties, in plain words

A [reference text](https://docs.zkproof.org/pages/reference/reference.pdf) of the field names three properties. Every such system aims for the first two, and some for the third.

- **Complete.** An honest operator is always believed: "If the statement is true and both prover and verifier follow the protocol; the verifier will accept."
- **Sound.** A dishonest operator is not: "If the statement is false, and the verifier follows the protocol; the verifier will not be convinced." This holds up to a small probability and under stated mathematical assumptions. The [[security level]] says how small.
- **Zero-knowledge.** The verifier "will not learn any confidential information from the interaction with the prover but the fact the statement is true". For inference, the confidential information is the weights.

The site's [[glyph]] reports what each system's publisher states about the second and third. No test of ours can establish either one, and [How we compare](/method) says why.

## What a yes does not tell you

Nine things a yes does not mean. Where a system's authors say so themselves, we quote them.

:::note A yes is not
**A sign that the model is safe.** The proof is about a computation, not about behaviour. A model can be faithfully served and still be a poor or dangerous model.

**Evidence about anything else the machine did.** Anthropic, which publishes FlashProve, [writes](https://www.anthropic.com/research/provable-inference) that a proof "does not establish that the hardware is not, e.g., training on the side".

**A statement about training.** How a model was made is a different claim, with its own much less mature techniques.

**A record of what happened at the time.** A proof made afterwards shows that the committed model gives this reply. In the words of an [early paper](https://arxiv.org/abs/2402.02675), it shows that the provider has a model that can produce it, "not that it necessarily served it earlier".

**About the model as it is usually run.** Proofs need arithmetic that repeats bit for bit, so today they are about a quantized copy of the model with exactly fixed arithmetic, decoded greedily. Anthropic [lists it](https://www.anthropic.com/research/provable-inference) among its system's limits: "The proof is about an integer model under greedy decoding."

**About the whole product.** The same weights behave differently behind another system prompt, filter or router. A proof speaks about the weights.

**A guarantee that nothing was learned.** Where a system has zero knowledge, it hides the weights. The prompt, the reply and the model's size and shape stay visible to the verifier. Whether a given program hides the weights is its publisher's statement, which this site does not test.

**A promise to prove.** An operator can decline to produce a proof, or produce it late. What a missing proof means is for the rule to say, not the mathematics.

**Certainty.** Soundness rests on assumptions and on software being correct. Either can fail.
:::

One caution applies to this site. Its ladder is made of open-weights models, which anyone with enough hardware could rerun. For those, keeping the weights hidden is not the benefit. The benefit is a check that needs no such hardware. Hiding starts to matter when the same systems are used on closed-weights models.

## What a verifier has to refuse

A proof is only useful if a wrong claim is refused. A verifier must tie its yes to three things: the committed model, the prompt and the reply. If it fails to tie one of them, an operator can change that thing and still be believed.

:::explore tamper
The three tampering checks this site runs on every system: what is changed, and what a verifier does with it when it ties its yes to that thing and when it does not. A check is held when the verifier refuses the change, and only counts if the same verifier accepts the untouched proof. The table above shows how each system run here stands on them.
:::

Passing these checks shows that the verifier refused the changes we tried. It does not show that a proof is hard to forge: no check here tries to forge one. That is soundness, which is argued mathematically and reviewed by experts, not tested by a benchmark.

## What has been built so far

Through mid-2026, governance reports described these proofs as too expensive to use. An [Oxford study](https://www.oxfordmartin.ox.ac.uk/publications/verification-for-international-ai-governance) of 2025 called them "impractical to apply at scale as of this writing", and added in a footnote that with dramatic progress they "might rapidly become the most practical approach for verifying many AI-related questions".

Between August and November 2026, three groups reported systems that prove replies of models with billions of weights, each with its own figures, on its own model, under its own rules. None presents itself as a finished product: ["A research artifact: not maintained, not accepting contributions"](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/README.md) (FlashProve), ["ZK Inference Prover Measurement Prototype"](https://github.com/sg-ai-safety-hub/zk-inference-prover) (SASH), ["These are alpha results."](https://attestable.com/blog/proving-llms-scale) (Attestable). Before this site's first run we knew of no figure for any of them from anyone but its authors, and none under common rules. What this site has run so far is in the table above, and the [ladder](/) lists the systems it has not run, each with the reason.
