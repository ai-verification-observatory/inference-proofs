A verifier answers yes or no. The [[relying party]] decides what the yes is worth. This page is for that reader: nine questions to put to any system that offers a proof, where this site answers each, and what it leaves open.

## Nine questions

### 1. What does a yes mean, exactly?

Ask for the sentence, not the summary. Which positions of a reply are covered: all of them, or one? Must each token be the model's exact choice, or only close to it? Each system's [[claim card]] records its [[statement]] in its publisher's own words, with a link to the line. On this site every system is asked for the same thing: a full reply, every token checked.

### 2. Where do the prompt, the reply and the commitment come from?

A proof speaks about one prompt and one reply, relative to one number, the [[commitment]]. Ask where each came from. If the operator supplied the prompt and the reply, the proof shows that the operator holds a model that gives this reply, ["not that it necessarily served it earlier"](https://arxiv.org/abs/2402.02675). A sample means something only if a record you trust fixed the replies before the draw, and the operator could not predict the draw.

For the commitment, ask who published the number and what ties it to the model you care about: a register, a signed release, an evaluation report. A yes says "the model behind this number", not whose model that is. If the number arrives with the proof, from the party being checked, the check is worth nothing. We always supply it from our own record.

### 3. Is the proved model the model that is served?

A proof needs arithmetic that repeats bit for bit, so a system proves a quantized copy of a model, decoded greedily, within a fixed length. Ask what the operator has to change to serve exactly that copy, because a proof describes what was served only if it was. Then ask how far the copy is from the original: a copy can be faithful, or degraded until proving it is cheap. Here that is the [Fidelity check](/checks#fidelity) and the "Faithful model" petal of the [[glyph]]: a system's replies are compared with those of the original weights, and have to beat copies that we damaged on purpose. Where a row reads "Fidelity undecided", the comparison has not been run yet.

### 4. Who has run it, besides its authors?

A figure published by a system's own team was obtained on its own model, under its own rules. Ask who else has run the system, from the public code, unchanged. That is what this site does, and it marks every figure with how it was obtained and how many sessions stand behind it. No figure here has yet been reproduced by a second party, and the pages say so. Put the same question to this site: its [mandate](/mandate) names who runs it and lists its conflicts of interest.

### 5. How hard is it to forge, and who says so?

Every system should state a [[security level]]. Three follow-up questions matter more than the number. Is it proven, or conjectured from the absence of a known attack? Does it cover the program that actually runs, or a description of it on paper? Has anyone outside the team reviewed it? In late 2025 a conjecture behind the parameters of many proof systems was shown false in its strongest form, and the Ethereum Foundation [warned](https://blog.ethereum.org/2025/12/18/zkevm-security-foundations) that "what was advertised as 100 bits might actually be 80". The proofs still verified: nothing a checker could see had changed. This site prints each publisher's statement in the "Unforgeable" petal. No test of ours can confirm it, and a failed tampering check turns the petal red.

### 6. Whom else must I trust?

Some systems need a one-time setup whose secrets must be destroyed, a hardware maker's key, or a third party. Others need only the checking program and cryptographic assumptions. The "Only the verifier trusted" petal says which, as the publisher states it. The checking program itself always has to be trusted, so ask who has read it. A scheme that samples traffic also trusts whatever recorded the traffic.

### 7. What does the operator have to show?

The checker sees every prompt and reply it checks, and the model's size and shape. If the weights are a secret, ask what a proof reveals about them, and whether that claim is proven for the program or only expected of it. The "Weights hidden" petal records the publisher's statement. Our [No weight file](/checks#no_weight_file) check shows only that the verifier ran without opening a model file, which is a smaller thing.

### 8. What does it cost, at the share I need?

Proving every reply costs the full multiple on every reply. Some uses need only a sample. A random sample, drawn after the fact, catches a substitution that is frequent next to the size of the sample: 300 draws catch one swapped reply in 100 about 95 times in 100, and one in 10,000 about 3 times in 100. A use that needs one named reply proved, such as a customer's own, gets nothing from a sample.

A sample does not divide the whole cost. A reply can be proved only if the proved copy of the model generated it, and nobody knows in advance which replies will be drawn. So every reply has to be generated by that copy, and only the proving falls with the share. Where a row prints its multiple in two parts, generation is producing the reply with the proved copy's arithmetic, and proving is everything after it.

:::explore cost
The arithmetic of a sample. Every reply is generated by the proved copy, and a share is also proved.
:::

Ask also what the check costs you: the time to verify one proof, which the ladder prints per reply, and its size, which each system's page prints.

### 9. What happens when no proof comes?

An operator can decline, fail or run late. A proof system has no answer to that. The rule you are enforcing has to say what a missing proof means, and by when.

## Reading a row

- **The standing.** "Passed" means all six [checks](/checks) are held for that system on that model. Otherwise the row names the checks that are not. An undecided check is not a failed one: it names its cause, often that a test has not been run yet.
- **The position.** Only a system that passed, and whose publisher states a security level, has one, and only among systems on the same model. Nothing is compared across models.
- **The glyph.** Five petals. Green: holds in full. Amber: in part. Red: not at all, not stated, or one of our checks failed. Hollow: not decided yet. Three petals repeat what the publisher states, and two come from our checks. The glyph never moves a position.
- **The multiple.** The GPU time of one more proved reply, over the GPU time of serving one, on the same kind of GPU. Generating the reply is inside it. Under it: what was timed, and over how many sessions. A position needs three sessions, so a figure over fewer is provisional.

## What this benchmark will not tell you

- **Whether a proof can be forged, or leaks.** No check here attempts either. Passing six checks means that a system's verifier refused each change we made to the model, the prompt and the reply, on the request we fixed. It does not mean that a proof is hard to forge.
- **Anything about secret models.** Level 1 runs open-weights models only.
- **Whether a deployment keeps a rule.** That needs the other tools described on [the treaty page](/treaty).
- **What is good enough.** A threshold is yours to set: a maximum multiple, a minimum security level, a longest acceptable check time. If you have one, [tell us](https://github.com/ai-verification-observatory/inference-proofs/issues).

## Words that look alike

| Word | In policy and safeguards | In cryptography |
|---|---|---|
| Verification | A judgement that a party kept a rule | Running a program that accepts or refuses one proof |
| Verifier | The state or body that checks | The program |
| Commitment | A pledge by a state or a company | A short value that fixes data without showing it |
| Binding | In force in law | Tied by the mathematics: a proof made for one prompt is refused for another |
| Completeness | Nothing was left undeclared | An honest proof is always accepted. The two senses are unrelated |
| Attestation | A signed statement that a requirement is met | A chip's signed report. Not a proof: it is as good as its signer |
| Proof | Evidence strong enough to act on | A specific file with an exact check |

## Reading on

From the most accessible to the most technical. Most are sources these pages cite.

:::reading
- [Verification methods for international AI agreements](https://arxiv.org/abs/2408.16074). Wasil, Reed, Miller and Barnett, 2024. A short survey of ten ways to detect unauthorised training or data centres, each with its precedents and its ways around.
- [The Math Behind Pacing the Frontier](https://www.aisafety.sg/blog/zkp-intro). Singapore AI Safety Hub, 2026. A plain explanation of proofs of inference beside trusted hardware, inspections and rerunning, by a group that builds a prover.
- [The Compute Verification Post](https://jasminexli.substack.com/cp/207744145). Hausenloy and Li, 2026. An informal primer on what can be shown about a data centre, arranged as a ladder of how little you are willing to trust.
- [How To Make International AI Verification a Reality](https://thefuturesociety.org/international-ai-verification). The Future Society, 2026. A policy memo that ranks verification research for states outside the two largest AI powers, and says governments can test proposals against shared benchmarks.
- [Faster AI Diffusion Through Hardware-Based Verification](https://ifp.org/faster-ai-diffusion-through-hardware-based-verification/). Ammann and Dalrymple, 2025. The case for building verification into AI chips, with a costed research programme.
- [AI 2040 Plan A: Verification Plan](https://ai-2040.com/supplements/verification-plan). Dean, 2026. A step-by-step design for data centres that only serve models: network taps, a rerun of sampled work, and the arithmetic of sampling.
- [AI 2040 Plan A: Verification SITREP](https://amododesign.com/ai-verification/plan-a-sitrep/). Amodo Design, 2026. A status report on that design, piece by piece, by a company that builds verification hardware.
- [Pacing AI Requires Proof](https://attestable.com/blog/pacing-ai-requires-proof). Attestable. A vendor's account of what proofs give an agreement, useful for its section on what cryptography does not solve.
- [Verifying International Agreements on AI](https://arxiv.org/abs/2507.15916). Baker, Kulp, Marks, Brundage and Heim, RAND, 2025. A framework of four subgoals and six layers of verification.
- [Verification for International AI Governance](https://www.oxfordmartin.ox.ac.uk/publications/verification-for-international-ai-governance). Harack and others, 2025. A long study of which agreements can be verified under pessimistic assumptions. It has a section on "proof of inference".
- [Frontier AI Auditing](https://arxiv.org/abs/2601.11699). Brundage and others, 2026. Four levels of assurance for audits of AI developers, the highest of which is meant to give "treaty-grade" confirmation.
- [What does it take to catch a Chinchilla?](https://arxiv.org/abs/2303.11341). Shavit, 2023. The paper that set out the Prover and Verifier design for rules on training.
- [Progress on provable inference for large language models](https://www.anthropic.com/research/provable-inference). Anthropic, 2026. One system's figures and a list of what its prototype does not prove. With the [research note](https://www.aisafety.sg/research/what-proving-llm-inference-actually-costs-research-note) of the Singapore AI Safety Hub, the publishers' own reports on the first two systems this benchmark set out to run.
- [A zero-knowledge protocol for nuclear warhead verification](https://www.nature.com/articles/nature13457). Glaser, Barak and Goldston, 2014. The arms control proposal for confirming a property while learning nothing else.
:::

For everything else there is the [AI Workload Verification Papers](https://github.com/WHodgkins/AI-Verification-Papers) bibliography, built on a reading list by Will Hodgkins and earlier lists by Mauricio Baker and James Petrie. It covers more of the field, and several entries above were found through it.
