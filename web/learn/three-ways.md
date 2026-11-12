There are three technical ways to check a computation you did not run: run it again, trust the machine that ran it, or check a proof. Each moves your trust somewhere else, and each can fail. This page sets them side by side. Which one fits depends on who is checking whom.

## Run it again

The checker, meaning whoever wants the claim checked, or a server it trusts, holds the model and repeats the computation: all of it, or a random sample. If the results match, the claim stands. This is [[recomputation]].

It is the method the research on AI agreements proposes first, and it is in use. Anthropic, which also publishes one of the provers on this site, [reports](https://www.anthropic.com/research/provable-inference) that it met its own 2026 goal for checking its inference "through a separate but related project, which signs our inference traffic and recomputes inference on a trusted server". The operator's extra cost is close to nothing. The checker pays for whatever share it reruns.

It asks for two things. The arithmetic has to repeat: two runs of the same model can differ in the last digits, so either the computation is made reproducible or the comparison allows a tolerance, and a tolerance is room to cheat. And a machine other than the operator's own has to hold the weights. Between a company and its own security team that is no obstacle. Between rivals it is the hard part. Designs for that case put the rerunning machine in a guarded enclosure, sometimes inside the operator's data centre, and let only a pass or a fail leave it. The weights are then shown to a box, not to the other side, and everything rests on the box. As [Hausenloy and Li](https://jasminexli.substack.com/cp/207744145) put it, "the recomputation cluster sees the records of someone's frontier computations, so it has to be defended like the secrets themselves".

## Trust the hardware

Some processors are built to run software inside a protected region that the machine's owner cannot read or alter, and to sign a report of what they started. This is a [[trusted execution environment]], and the signed report is an [[attestation]]. A service can use it to show which software and which model files it loaded.

It is cheap and available today. One [measurement](https://arxiv.org/abs/2504.04715), on a model of 8 billion parameters on a single GPU, found: "The overhead for first-token latency was 9-16%, while the drop in overall throughput under a high-concurrency load was only 2.88%." Nothing is revealed to the checker, and the model runs unchanged.

What it asks is trust in the chip. The signature is the chip maker's, and it is only as good as the secrecy of the maker's keys and the integrity of the machine. A [review](https://techgov.intelligence.org/blog/on-tees-for-privacy-preserving-monitoring-in-ai-governance) published by MIRI's Technical Governance Team notes that whoever holds the hardware's key "can, in principle, produce valid attestation reports for arbitrary measurements without possessing the physical chip". Researchers have also [forged attestations](https://tee.fail/) with a device attached to a server's memory, at a cost they put "under $1000". The chip makers consider attacks that need physical access to be outside what they defend against. For a cloud customer that is often acceptable. A state checking another state faces an operator with unlimited physical access to its own machines, and a signature from a foreign manufacturer.

## Check a proof

The operator commits to its model and produces, for each reply to be checked, a [[proof of inference]]. The checker runs a small program on the proof. [What a proof of inference is](/proof-of-inference) describes it.

Nobody but the operator holds the weights, and the proof itself asks for trust in no special hardware. What is trusted instead is mathematics, the checking program, and the source of the commitment. Whoever is given the prompt, the reply and the proof can run the check, including parties who were not part of the arrangement.

The price is the operator's. Producing a proof costs a large multiple of producing the reply. Today's systems prove a quantized copy of the model with exactly fixed arithmetic, not the model as it is usually served, so the operator has to serve that copy. An operator can also decline to produce a proof. And the software is young: the Singapore AI Safety Hub, which builds one of the provers, [warns](https://www.aisafety.sg/research/what-proving-llm-inference-actually-costs-research-note) that "bugs in deployed proof systems have let provers prove false statements before". [Before you rely on a proof](/before-you-rely) gives a recent case of a security claim that had to be lowered.

## Side by side

| Question | Run it again | Trust the hardware | Check a proof |
|---|---|---|---|
| The checker must hold | The weights, and hardware that can run them | The chip maker's public key and the expected report | The commitment and a small program |
| What has to be trusted | The machine that reruns | The chip maker, and that nobody opened the machine | Mathematical assumptions, the checking program, the source of the commitment |
| If only a sample is checked | How it is drawn, and the record it is drawn from | Does not apply: every run is attested | How it is drawn, and the record it is drawn from |
| What the operator reveals | The weights, to a machine both sides must trust | Nothing beyond the report | The prompt and the reply it proves, and the model's size and shape. Nothing about the weights, where the system hides them |
| Extra cost to the operator | Close to none | 2.88 % of throughput and 9 to 16 % of first-token latency, in the measurement quoted above | A large multiple of serving: see the [ladder](/) |
| What breaks it | A dishonest rerun, or arithmetic that does not repeat | Physical access to the machine, or a leaked signing key | A flaw in the checking program, a commitment to the wrong model, or an operator that declines to prove |
| Where it stands | In use inside at least one company. Between rivals, no party that both trust to rerun | Generally available | Research prototypes |

Two more approaches sit outside this table. Testing a service from outside needs no cooperation: it compares a service's replies with a reference copy, and it is how the cases on [the first page](/why-verify) were found. It gives a statistical verdict over many requests and says little about any one reply. The other is people on site: inspectors, or evaluators working inside a developer. A [2025 report](https://arxiv.org/abs/2506.15867) on verifying AI agreements stresses that "increased access (e.g., physical inspections of data centers) can often substitute for these technical approaches".

## Using more than one

The three can be used together. Anthropic built both a rerunning system and a prover, and [writes](https://www.anthropic.com/research/provable-inference) that "trusted hardware and cryptography are complementary approaches with different guarantees and tradeoffs". Proposals for agreements between states use several at once: equipment that records all traffic, a random sample drawn afterwards, and then either a rerun in a guarded room or a proof for each sampled reply. The Singapore AI Safety Hub [presents](https://www.aisafety.sg/research/what-proving-llm-inference-actually-costs-research-note) the swap as simple: "A proof answers the same challenge, and nothing else in the protocol has to change." The same note's list of what deployment needs includes: "The provider serves the arithmetic the proof constrains."

## An older version of the same choice

Research on dismantling nuclear warheads faces the same problem. In the words of [Glaser, Barak and Goldston](https://www.nature.com/articles/nature13457), inspectors "will have to gain high confidence in the authenticity of submitted items while learning nothing about them". The first proposal was the information barrier: a trusted machine that measures the secret and shows only a pass or a fail. The three authors wrote that such systems "are at risk of tampering and snooping", and proposed a protocol borrowed from cryptography, "designed in such a way that sensitive information is never measured and so does not need to be hidden".

The parallel holds in one respect. An information barrier is trusted hardware: the secret goes into a box, and everyone has to believe the box. A zero-knowledge protocol is an attempt to do without the box. It breaks in others. The warhead protocol compares an object against ["at least one reference warhead"](https://www.nature.com/articles/ncomms12890), and its secrecy "remains guaranteed only if the prover follows the protocol". It has been shown by calculation, by one laboratory experiment on test objects and by simulation. We found no report of one in use under a treaty. The idea has stayed on paper for more than a decade.

A procedural version of the barrier is in treaty text. In a challenge inspection under the Chemical Weapons Convention, the inspected state may restrict a sample analysis to ["presence or absence"](https://www.opcw.org/chemical-weapons-convention/annexes/verification-annex/part-x-challenge-inspections-pursuant) of listed chemicals: one question, one bit of answer. The instrument still sees the whole sample, so this is a barrier and not a proof.

## Whom both sides can trust

The question to start from is whom the two sides can both trust. A customer and a cloud provider can usually both trust a chip maker. A company and its auditor can agree on a guarded server. Two states that expect each other to cheat may agree on neither, and that is the case where the properties of a proof count for most.

The Singapore AI Safety Hub, which builds a prover and also works on trusted hardware, describes the trade this way:

:::quote https://www.aisafety.sg/research/what-proving-llm-inference-actually-costs-research-note Singapore AI Safety Hub, research note, September 2026
TEEs and activation checks are cheap, and for many settings they are the right tool; TEEs are a sensible starting point for a first agreement. What they cost is trust: in a hardware vendor, in a third party, or in a tolerance. A proof moves that trust into cryptographic assumptions and into code that both sides can read.
:::

Cost is one open question about that move. How mature the software is, what the checker sees and what the operator has to change are others. Most of the plans written for the case of two states choose rerunning. [A treaty, stage by stage](/treaty) walks through that case and marks, stage by stage, what stands behind each step.
