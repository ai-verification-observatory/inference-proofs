Suppose two states agree, by treaty or otherwise, to limits on how they develop and use advanced AI. Neither trusts the other, and neither will show the other its weights. Someone has to check. This page walks through what that someone could check with proofs of inference, one stage at a time, and marks each stage by what stands behind it today: run on this site, shown in research, proposed, or outside what a proof can reach. It takes no position on whether such an agreement should exist.

The short answer: a proof speaks to one of the six things the checking side needs to know. The systems that make such proofs are research prototypes. Most of what an agreement needs rests on equipment, inspectors and intelligence.

## The cast and the rule

- **State A** and **State B** each have companies that run large AI models in data centres. We follow State A as the one being checked. The same applies in the other direction.
- **The operator** is a company in State A. It runs the model and holds its weights, and State A answers for it.
- **The Inspectorate** is the body both states accept as checker. It is the [[relying party]] of this story: it runs the [[verifier]], which is a program, and has to decide what the program's verdicts allow it to report. The two states act on its reports. The research literature calls the two sides the Prover and the Verifier, meaning states or bodies, not programs. Inspectorate is our word, and the checker could as well be State B itself.

The rule in our scenario: in its declared data centres, a state serves only models entered in a shared register that the Inspectorate keeps, and trains nothing above an agreed size.

This is one of several rules that have been proposed. A [2026 statement](https://www.pacingthefrontier.com/) by employees of AI companies asks the US government to support an international effort to develop "the technical and governance tools needed to deliberately pace the frontier of automated AI development". An [essay](https://darioamodei.com/post/we-must-pace-the-frontier) by Dario Amodei, chief executive of Anthropic, says that pacing "does not mean halting model training" and that "any agreement must either have ironclad verifiability, or must be limited enough that defection would not be militarily existential". The mechanism the essay names is evaluators placed inside companies, "the key step for verifiability of any pacing commitments". It does not mention cryptographic proofs. Anthropic also publishes FlashProve, the system in the table below. We use the simple rule because most of the technical work has studied it, not because either text proposes it.

## What would have to be checked

A [RAND study](https://arxiv.org/abs/2507.15916) splits the job in two: "verifying that declared uses of large-scale AI compute are compliant", and "verifying that there are no undeclared uses of large-scale AI compute". Other authors cut it another way, familiar from nuclear safeguards: what a state declares has to be correct, and it has to be complete.

| What the Inspectorate needs to know | Does a proof of inference speak to it |
|---|---|
| How many chips exist, and where | No |
| That no data centre was left undeclared | No |
| That a given reply is what a registered model gives for its prompt | Yes. This is the statement it proves, for the replies it is asked about |
| That the model in use is the one that was evaluated | In part: it ties both to one commitment |
| That a declared data centre did nothing else | Not alone. Only together with equipment that records everything leaving it |
| How a model was trained, or what it can do | No |

A proof speaks to one row of six in full and to one in part. The rest of this page is about that row, and about how far it can be stretched.

:::explore treaty
The stages below in brief, as a walk in six steps, each marked like its stage. At each one: who holds what, what the Inspectorate can conclude, and what it cannot.
:::

## The stages

:::stage measured This reply is what the registered model gives
The operator computes a [[commitment]] to its model and enters it in the register. For a prompt and a reply the Inspectorate holds, the operator can then produce a [[proof of inference]]. The Inspectorate runs the verifier with the commitment from the register, the prompt, the reply and the proof. It needs no weights and no GPU.

This is what this site runs: it checks whether a system's verifier refuses a changed model, prompt or reply, and records what a proved reply costs.

The limits are today's. The proof is about a quantized copy of the model with exactly fixed arithmetic, decoded greedily, so the operator has to serve that copy for a proof to describe what was served. Length is bounded: the request on this site is 512 prompt tokens and a 512-token reply, and Anthropic [states](https://www.anthropic.com/research/provable-inference) that its system "currently proves inference over contexts of up to 1,024 tokens". The Inspectorate sees the prompt, the reply and the model's size and shape. Whether a proof leaks anything about the weights is each publisher's statement, which this site does not test: FlashProve's [guide](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/what-is-proved.md#L9-L27) says its authors "expect, rather than know, that the programs hide the weights at the default setting, in honest runs, if the provider keeps its duties". The models on the ladder are open-weights models, not the closed models a real agreement would be about.
:::

:::measured rows
The current rows. The multiple is the GPU time of one more proved reply over the GPU time of serving one. It includes generating the reply with the proved copy's arithmetic, and where a row splits it, the two parts are printed apart. [How to read a row](/before-you-rely#reading-a-row).
:::

:::stage demonstrated The model that was evaluated is the model that serves
An agreement will want more than "some registered model". It will want the registered model to have been through agreed tests. A proof can tie the two together: if the test replies and the served replies verify against the same commitment, they are replies of the same weights. A [policy memo](https://thefuturesociety.org/international-ai-verification) by The Future Society notes that verification "can confirm that the model evaluated is the one the provider claims it to be".

This has been [shown with proofs](https://arxiv.org/abs/2402.02675) on small models. We found no report of an evaluation under proof at the scale of a large model, and it would have to fit the length and the decoding rule a prover accepts. The same weights are also not the same product: a system prompt or a filter changes behaviour and is outside the proof. And a proof says nothing about whether the tests were the right tests.
:::

:::stage proposed A sample stands for the traffic
Proving every reply costs the full multiple on every reply. Proposals from several groups prove a sample, and share one design. Equipment at the data centre's network boundary records a fingerprint of every prompt and reply. Afterwards, the Inspectorate draws replies at random from that record and challenges the operator to prove them.

Two conditions make the sample mean something, in the words of a [research note](https://www.aisafety.sg/research/what-proving-llm-inference-actually-costs-research-note) by the Singapore AI Safety Hub, which builds a prover: "the draw must be unpredictable to the provider, and the provider must commit to its answers before the draw." Then an operator that served another model for one reply in a hundred is caught about 95 times in 100 by 300 draws. One that did it for one reply in ten thousand is caught about 3 times in 100. Whether a single reply matters is for the parties to decide.

The design has consequences that a proof does not remove. The operator cannot know which reply will be drawn, so every reply has to come from the proved copy of the model. The recording equipment is trusted hardware inside State A's data centre: in the published designs the checking side supplies it, and someone has to watch that it stays in place. A proof takes far longer to make than a reply, so it arrives afterwards: the scheme detects a substitution and does not prevent one. And an operator can fail to produce a proof, so the agreement has to say what a missing proof means.

The parts exist separately. [Amodo Design](https://amododesign.com/ai-verification/plan-a-sitrep/), a company that builds verification hardware, reports taps that copy a data centre's traffic at today's lower link speeds, and demonstrations of rerunning sampled requests. A device that fingerprints the traffic has been [designed](https://arxiv.org/abs/2606.10724), and we found no report of one built. Proofs are run here. The same research note says of the join: "Nothing yet ties a proof to what the certifier recorded."
:::

:::stage outside The data centre did nothing else
The rule is about what a data centre does not do, and a proof is silent there. Anthropic [writes](https://www.anthropic.com/research/provable-inference) that a proof "does not establish that the hardware is not, e.g., training on the side". Attestable, a company that builds another prover, [says the same](https://attestable.com/blog/pacing-ai-requires-proof): "Workload compliance and compute coverage are separate problems."

Closing the gap takes hardware and people, not mathematics: recording equipment on every connection, limits on hidden channels through which data could leave unrecorded, memory that is wiped or tested, inspectors. Amodo Design's [status report](https://amododesign.com/ai-verification/plan-a-sitrep/) on one such plan lists seventeen pieces of work. It grades four as having an active effort and seven as "Not on track". A record at the boundary also sees only what crosses it. Work a model does for its own developer inside the data centre, the kind a rule on automated AI development would be about, leaves no trace there unless the plan forces its results through the boundary. And there is a doubt about the goal itself. Serving a model can advance research too, so a data centre that only serves is not a data centre that does no development.
:::

:::stage outside Nothing was left undeclared
Every check above happens inside data centres the state declared. None of them reaches a data centre it did not. "A proof cannot discover a datacenter that was never declared", as [Attestable](https://attestable.com/blog/pacing-ai-requires-proof) puts it. That is work for chip tracking, inspections and intelligence. Nuclear arms control divides the work the same way: a [report to the US Congress](https://www.everycrsreport.com/reports/R41201.html) notes that the United States and Russia "rely on their own national technical means of verification (NTM) to collect most of the information needed to verify compliance with arms control agreements".
:::

## A proof or a rerun

Most plans for such an agreement answer the Inspectorate's challenge by rerunning the sampled request on a guarded server, not by a proof. One detailed plan, the [verification supplement](https://ai-2040.com/supplements/verification-plan) of the AI 2040 scenario, recommends "a network-tap and recomputation based approach" and files proofs under promising but "somewhat speculative". [Three ways to check](/three-ways) compares the two.

The case for a proof in this setting rests on three properties. Most of the sources that make it build provers.

- **No second copy of the weights.** A rerun needs a machine with State A's model on it, in a place State B can trust. A proof does not.
- **No trusted machine holds the secret.** The proof itself relies on no chip. The sample still relies on the recording equipment at the boundary.
- **A third party can recheck.** Whoever is given the prompt, the reply and the proof can run the check without the weights. Those prompts and replies are the traffic of State A's users, so State A decides who that is.

The case against is longer, and most of it is in the stages above. The operator has to change what it serves. The Inspectorate sees the model's size and shape, and every sampled prompt and reply. An operator can decline to prove. The table above is what a proved reply costs here so far. And the systems are research prototypes: the Singapore AI Safety Hub [warns](https://www.aisafety.sg/research/what-proving-llm-inference-actually-costs-research-note) that "bugs in deployed proof systems have let provers prove false statements before".

The Future Society's memo ranks work on the cost of zero-knowledge proofs fifth of its five research priorities, behind four kinds of hardware work. It calls it "a high-upside, high-uncertainty task", whose appeal is that such methods "sidestep the hardware-trust problem".

## What the Inspectorate can and cannot say

With proofs, and with a traffic record it trusts, the Inspectorate can report one thing: each reply it drew from that record is what the registered model, in its proved copy, gives for the recorded prompt. It can say this without holding the weights. State B can recheck it if State A releases the sampled prompts and replies. Without the record, the Inspectorate can say this only of replies State A chose to show it.

It cannot report that State A is keeping the agreement. That is a judgement over everything it knows, from chip counts to inspections, in which proofs are one input. The INF Treaty was defended to the US Senate on its ["successive layers of procedures"](https://www.armscontrol.org/act/2007-06/looking-back-intermediate-range-nuclear-forces-treaty), and The Future Society's memo says of AI: "No single mechanism is sufficient or fully secure against a capable state adversary". An agreement can also end while its technology still works: [New START](https://www.armscontrol.org/factsheets/new-start-glance), which limited US and Russian strategic nuclear forces, expired in February 2026.

The same memo observes: "Most verification proposals originate with the laboratories and researchers who design them. A government with sufficient technical capacity of its own can test these proposals against shared benchmarks, so that competing designs become comparable." This site is a benchmark of that kind for one family of proposals. Its [mandate](/mandate) names who runs it and lists its conflicts of interest, and [Before you rely on a proof](/before-you-rely) is about how to read it.
