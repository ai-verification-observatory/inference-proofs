A cloud provider claims its API is serving a specific frontier model. A developer tells a regulator that the model in production is the exact one that passed pre-deployment testing. One government tells another that its declared data centres only run approved models. In every case, the person on the receiving end faces the same problem: the claim is about a computation running on someone else's machines, behind closed doors.

:::note In short
A cryptographic proof of inference establishes one specific fact: that a given reply is the output of a pre-committed model for a given prompt. Anyone can check that proof without holding the model's weights. A proof cannot tell you whether that reply was actually served to a user, whether the cluster ran other jobs on the side, or whether the model itself is safe. The systems that generate these proofs today are research prototypes, and the table on the next page shows every system we have run so far.
:::

## Claims nobody outside can check

When you send a prompt to an inference API and receive a reply, the provider tells you which model wrote it. You have the prompt and the reply, but you do not have the model, and nothing in the text of the reply proves which weights produced it.

That gap is not hypothetical. Researchers who tested commercial APIs serving four open-weights models in 2024 found that "[11 out of 31 endpoints serve different distributions than reference weights released by Meta](https://arxiv.org/abs/2410.20247)", noting that providers "may quantize, watermark, or finetune the underlying model" without disclosing it. A [2026 study](https://arxiv.org/abs/2603.01919) of third-party proxy and resale endpoints reported "identity verification failures in 45.83% of fingerprint tests", finding "fingerprint-based evidence consistent with deceptive model claims in a subset of audited endpoints".

Regulators run into a broader version of the same problem. As the 2026 [International AI Safety Report](https://internationalaisafetyreport.org/publication/international-ai-safety-report-2026) puts it: "Information asymmetries limit access to evidence about general-purpose AI systems."

## What verification means

People use the word "verification" to mean four distinct things, and discussions quickly get muddled when those meanings are conflated.

| Sense | What it means | Who does it |
|---|---|---|
| Checking a claim | Gathering evidence to test whether a stated fact holds | Anyone given the evidence |
| Assessing compliance | Judging whether a party has abided by a law, contract, or treaty | An institution weighing all available evidence |
| Formal verification | Proving mathematically that a piece of software satisfies a formal specification | Verification engineers using theorem provers |
| Running a verifier | Executing a program that checks a cryptographic proof and outputs accept or refuse | Any computer |

A [RAND report](https://arxiv.org/abs/2507.15916) on verifying international AI agreements defines the first sense as: "The act or process of checking whether a claim is true, such as checking whether a party has complied with a requirement as claimed." The systems we benchmark on this site belong to the fourth row: they produce cryptographic proofs checked by a verifier program. Running a verifier program can supply one piece of evidence for checking a claim or assessing compliance, but it never settles compliance on its own. As a [US Congressional Research Service report](https://www.everycrsreport.com/reports/R41201.html) on arms control observes, "verification is almost always a matter of judgment".

Across these pages, we use a practical working definition: verifying a claim means checking it against evidence that holds up even when you do not trust the party making the claim.

That still does not mean 100 percent certainty. "There is no such thing as absolute, 100 percent verification", [George Shultz told the US Senate](https://www.armscontrol.org/act/2007-06/looking-back-intermediate-range-nuclear-forces-treaty) while defending the INF missile treaty. The useful questions are always concrete: what kind of violation, how large, caught how quickly, and under what assumptions.

## Why inference is hard to verify

Three obstacles get in the way whenever you try to check which AI model produced a reply:

- **The model weights are proprietary.** The most direct way to check which model answered is to inspect the model and run it yourself. For closed models, the weights are the owner's core trade secret, and user prompts are often confidential too. Policy researchers call this the [transparency-security trade-off](https://www.oxfordmartin.ox.ac.uk/publications/verification-for-international-ai-governance): the more an operator reveals to prove compliance, the more sensitive IP or private data it exposes.
- **Re-running inference is expensive.** Generating a single reply from a frontier model takes trillions of arithmetic operations on specialised GPU clusters.
- **The operator controls the hardware.** Any ordinary server log or API metadata comes from machines owned and administered by the very party whose claim you want to check.

Every technical approach to checking inference trades off against these three constraints. Re-running the model requires access to the weights and spare GPUs. Hardware attestation avoids sharing the weights, but requires trusting the chip manufacturer and assuming the operator has not physically tampered with the server. A cryptographic proof requires neither the weights nor trusted hardware, at the cost of making the operator do orders of magnitude more compute. [Three ways to check](/three-ways) compares these options directly.

## A wide field, and our small corner of it

The [AI Workload Verification Papers](https://github.com/WHodgkins/AI-Verification-Papers) bibliography, which we draw on throughout these pages, describes the broader research area like this:

:::quote https://github.com/WHodgkins/AI-Verification-Papers AI Workload Verification Papers, a bibliography built on a reading list by Will Hodgkins
AI workload verification establishes properties of computations performed on AI hardware — for example, whether accelerators are being used for training or inference, which model is running, whether required safeguards are active, or whether information has left an approved environment.
:::

This benchmark focuses on a single slice of that problem: verifying *which model produced a given reply*, one request at a time, using cryptographic proofs of inference. Answering the other questions in that quote requires very different tools, including hardware telemetry, physical inspections, power and network monitoring, and hardware enclaves. In the pages ahead, we spend just as much time on where cryptographic proofs stop as on how they work, because almost every real-world governance proposal depends on what happens outside the proof.

## Who might rely on inference proofs

| Who relies on the check | The claim they want checked | What is used or demonstrated today |
|---|---|---|
| An API customer | The model I paid for actually wrote this reply | External black-box fingerprinting tests, and GPU hardware attestation |
| An auditor or regulator | The model deployed in production is the one that was evaluated | Demonstrated with proofs on small models and with trusted hardware on larger ones; still an [open problem](https://arxiv.org/abs/2407.14981) at frontier scale |
| An internal security team | Only replies from our approved model leave this server | [Signing inference traffic](https://www.anthropic.com/rsp/roadmap) and [recomputing inference on a trusted server](https://www.anthropic.com/research/provable-inference) (at Anthropic) |
| A party to an international agreement | Another state's declared data centres only run declared workloads | Conceptual architectures and research prototypes |

While these use cases are widely discussed, it is still an open question whether cryptographic proofs will be the tool chosen for them. Where verification is deployed in practice today, it typically relies on the alternatives covered in [Three ways to check](/three-ways). Nor do current regulations require cryptographic proofs. For example, the [EU AI Act](http://publications.europa.eu/resource/celex/32024R1689) requires providers of general-purpose models to maintain technical documentation, and requires providers of models with systemic risk to conduct model evaluations and protect model weights. A proof of inference could in principle help show that the deployed model matches the evaluated one, but no regulation mandates it.

## Verification in recent policy statements

In 2026, the term "verification" began appearing regularly in official government statements on AI. The UK government [describes](https://www.gov.uk/government/news/britain-steps-up-national-defences-against-growing-ai-risks) "the emerging field of AI verification" as work that "helps check that claims about how AI systems have been developed, tested and assessed stands up to scrutiny". Similarly, the [Paris Call](https://www.elysee.fr/en/emmanuel-macron/2026/11/09/paris-call-for-ai-safety-and-security) of November 2026, signed as of 12 November 2026 by seventeen governments and ten AI companies, names "transparency, incident reporting, risk management and verification" as areas requiring "tangible and immediate results".

Neither statement endorses a specific technical mechanism, and most government-funded work in this area focuses on hardware security and inspections rather than cryptography. We take no position on whether states should negotiate limits on AI development. Instead, we ask a conditional question: *if* someone needs to verify a claim about model inference without trusting the operator, what actually works today, what does it prove, and what does it cost?

Verification mechanisms also carry real costs and risks of their own. The RAND report cautions that verification, "if implemented without adequate restraint, could compromise sensitive information, hinder innovation, and centralize information and power". For instance, the architecture we examine on [the treaty page](/treaty) logs a fingerprint of every prompt and reply crossing a data centre's boundary and hands random samples to an inspectorate. We explain how such a design works and where it can fail; we do not advocate building it.

:::note Conflicts and authorship
Several organisations quoted in these pages build inference provers or verification hardware, including Anthropic, the Singapore AI Safety Hub, Attestable, and Amodo Design. We identify each organisation whenever we quote its work. One conflict of interest applies directly to us: Anthropic publishes FlashProve, one of the systems on our ladder, and parts of this project's code and prose (including drafts of these Learn pages) were written with the help of Claude, Anthropic's model. See our [mandate](/mandate) for who operates this site and how our rules are enforced.
:::

## Where to go next in this track

- [What a proof of inference is](/proof-of-inference): how a cryptographic proof binds a model commitment, a prompt, and a reply, what an accepted proof guarantees, and nine things it does not tell you.
- [Three ways to check](/three-ways): how re-running inference, trusting hardware enclaves, and checking cryptographic proofs compare on trust assumptions and cost.
- [A treaty, stage by stage](/treaty): how proofs of inference would fit into a bilateral AI agreement, marking what is running today versus what remains unbuilt.
- [Before you rely on a proof](/before-you-rely): nine questions to ask any prover team, and how to read a row on our benchmark ladder.
