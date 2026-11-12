A company says its service answers with a certain model. A lab tells a regulator that the model it sells is the model that was tested. A state tells another state that its data centres serve only approved models. In each case the listener is in the same position: the claim is about a computation that only the claimant can see. This page says what it means to verify such a claim, why that is hard for AI, and which small part of the problem this site covers.

:::note In short
A proof of inference can show one thing: that a given reply is what a model fixed in advance gives for a given prompt. Whoever checks it needs no copy of the weights. A proof cannot show that the reply was served, that the machine did nothing else, or that the model is safe. The systems that make such proofs are research prototypes, and the table on the next page is everything this site has run.
:::

## Claims nobody outside can check

You send a prompt to a service and a reply comes back. The service says a particular model wrote it. You hold the prompt and the reply. You do not hold the model, and nothing in the reply says which model produced it.

Researchers who tested commercial services offering four open models in 2024 found that ["11 out of 31 endpoints serve different distributions than reference weights released by Meta"](https://arxiv.org/abs/2410.20247). The causes they name are that providers "may quantize, watermark, or finetune the underlying model", without saying so. A [2026 study](https://arxiv.org/abs/2603.01919) of unofficial resale services reports "identity verification failures in 45.83% of fingerprint tests", and concludes: "fingerprint-based evidence consistent with deceptive model claims in a subset of audited endpoints".

Regulators meet a wider version of this gap. The 2026 [International AI Safety Report](https://internationalaisafetyreport.org/publication/international-ai-safety-report-2026) puts it as a matter of evidence: "Information asymmetries limit access to evidence about general-purpose AI systems."

## What verification means

The word is used in four ways, and arguments go wrong when they are mixed.

| Sense | What it is | Who does it |
|---|---|---|
| Checking a claim | Finding evidence that a claim is true | Anyone with the evidence |
| Finding compliance | Deciding that a party has kept a rule or a treaty | An institution, using everything it knows |
| Formal verification | A mathematical proof that software meets its specification | Specialists, with proof tools |
| Running a verifier | Running the program that checks a cryptographic proof and answers yes or no | A computer |

A [RAND report](https://arxiv.org/abs/2507.15916) on verifying AI agreements defines the first: "The act or process of checking whether a claim is true, such as checking whether a party has complied with a requirement as claimed." The tools this site runs are of the fourth kind. Such a tool can supply evidence for the first two. It is never the second by itself: as a [report to the US Congress](https://www.everycrsreport.com/reports/R41201.html) on arms control says, "verification is almost always a matter of judgment".

The working definition for these pages: to verify a claim is to check it against evidence that holds up even if the claimant is not trusted.

Holding up does not mean certainty. "There is no such thing as absolute, 100 percent verification", [George Shultz told the US Senate](https://www.armscontrol.org/act/2007-06/looking-back-intermediate-range-nuclear-forces-treaty), defending a missile treaty whose verification he judged effective. The useful questions are narrower: which violation, how large, detected how fast, with what confidence.

## Why it is hard for AI

- **The evidence is the secret.** The direct way to check which model answered is to look at the model. A model's weights are a trade secret of its owner, and prompts are often private. Researchers call this the [transparency-security trade-off](https://www.oxfordmartin.ox.ac.uk/publications/verification-for-international-ai-governance): the more a party shows, the more it gives away.
- **The computation is costly to rerun.** One reply of a large model is trillions of arithmetic operations on hardware few people have.
- **The claimant runs the machine.** Whatever logs or reports exist come from the party being checked.

Each way of checking gives something up against one of these. Rerunning needs the weights and the hardware. Trusted hardware needs trust in a chip maker and in a machine the operator holds. A proof needs neither, and costs the operator a large multiple of serving. [Three ways to check](/three-ways) compares them.

## A wide field, and one corner of it

A [bibliography of the research](https://github.com/WHodgkins/AI-Verification-Papers), which these pages draw on, defines the field this way:

:::quote https://github.com/WHodgkins/AI-Verification-Papers AI Workload Verification Papers, a bibliography built on a reading list by Will Hodgkins
AI workload verification establishes properties of computations performed on AI hardware — for example, whether accelerators are being used for training or inference, which model is running, whether required safeguards are active, or whether information has left an approved environment.
:::

This site covers part of one item of that list, "which model is running": for one reply at a time, with one family of techniques, cryptographic proofs of inference. The other items need other tools: chip tracking, inspections, sensors on power and network, trusted hardware. The pages that follow say where a proof stops, because most of what a serious arrangement needs lies beyond it.

## Who would rely on such evidence

| Who relies | The claim | What exists today |
|---|---|---|
| A customer | The model I pay for wrote this reply | Statistical tests from outside, and attestation by hardware |
| An auditor or a regulator | The model that was evaluated is the model that is deployed | Shown with proofs on small models and with trusted hardware on larger ones. An [open problem](https://arxiv.org/abs/2407.14981) at scale |
| A security team | Only replies of our own model leave this server | [Signing the traffic](https://www.anthropic.com/rsp/roadmap) and [recomputing inference on a trusted server](https://www.anthropic.com/research/provable-inference), at Anthropic |
| A state | Another state's declared data centres do what it declared | Proposals, of which few parts are built |

The needs are documented. Nothing shows that cryptographic proofs will meet them: where something is deployed today, it is usually one of the alternatives that [Three ways to check](/three-ways) compares. And none of the laws and official texts we read asks for a proof. The [EU AI Act](http://publications.europa.eu/resource/celex/32024R1689), for instance, asks providers of general-purpose models for technical documentation, and providers of those with systemic risk also for model evaluations and for cybersecurity protection of the model. A proof could support one of them: that the model evaluated is the model deployed.

## A word in official texts

In 2026 "verification" appeared in government statements about AI. The UK government [describes](https://www.gov.uk/government/news/britain-steps-up-national-defences-against-growing-ai-risks) "the emerging field of AI verification" as one that "helps check that claims about how AI systems have been developed, tested and assessed stands up to scrutiny". The [Paris Call](https://www.elysee.fr/en/emmanuel-macron/2026/11/09/paris-call-for-ai-safety-and-security) of November 2026, signed as of 12 November 2026 by seventeen governments and ten companies, lists "transparency, incident reporting, risk management and verification" as areas needing "tangible and immediate results".

Neither text names a tool, and most of the concrete work behind such statements is on hardware and inspections. This site takes no position on whether states should agree to limit AI development. Its question is the conditional one: if a claim about inference has to be checked, what can be checked today, how, and at what cost.

Verification also costs the party being checked, and it can be misused. The RAND report warns that verification, "if implemented without adequate restraint, could compromise sensitive information, hinder innovation, and centralize information and power". The scheme on [the treaty page](/treaty) records a fingerprint of every prompt and reply in a state's data centres and gives an inspectorate samples of them. These pages describe what such a scheme can show. They do not say it should be built.

:::note Who is speaking
Several sources these pages quote build provers or verification hardware: Anthropic, the Singapore AI Safety Hub, Attestable and Amodo Design. Each is named where it is quoted. One of them bears on this site itself: Anthropic publishes FlashProve, a system on the ladder, and parts of this site's code and text, these pages included, are drafted with Claude, Anthropic's model. The [mandate](/mandate) names who runs the site and lists its conflicts of interest.
:::

## The rest of this track

- [What a proof of inference is](/proof-of-inference): what the file is, what an accepted proof tells you, and a longer list of what it does not.
- [Three ways to check](/three-ways): rerunning, trusted hardware and proofs, and what each asks you to trust.
- [A treaty, stage by stage](/treaty): two states and an inspectorate, stage by stage, with each stage marked by what stands behind it.
- [Before you rely on a proof](/before-you-rely): the questions to ask, and where this site answers them.
