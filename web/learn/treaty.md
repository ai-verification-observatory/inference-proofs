Suppose two governments agree to limits on how they develop and deploy frontier AI models. Neither state trusts the other, and neither is willing to hand over its proprietary model weights for inspection. How much of that agreement could an international inspectorate actually verify using cryptographic proofs of inference?

This page walks through that scenario stage by stage. Each stage is badged by its technical status today: **Run on this site**, **Shown in research**, **Proposed, parts built**, or **Outside a proof's reach**. We take no position on whether states should sign such an agreement; our goal is to be clear about what proofs can and cannot do if they try.

The short version: a proof of inference directly answers one of the six questions an inspectorate needs to ask, and partially helps with a second. The provers that exist today are early research prototypes, and almost everything else a treaty regime requires still depends on boundary hardware, on-site inspections, and national intelligence.

## The cast and the hypothetical rule

- **State A** and **State B** both host companies operating large AI clusters. We follow State A as the party being inspected, though the exact same mechanics apply in reverse.
- **The operator** is a frontier AI lab or cloud provider inside State A. It holds the model weights and runs the cluster, and State A is accountable for its compliance under the agreement.
- **The Inspectorate** is the verification body appointed under the agreement. In our terminology, it is the [[relying party]]: it runs the cryptographic [[verifier]] program on proofs submitted by State A's operator and reports its findings to both governments. (Many governance papers call the two states the "Prover" and the "Verifier"; we use "Inspectorate" so we never confuse an institution with the software program that checks a proof file.)

The hypothetical treaty rule we trace is simple: inside its declared data centres, each state may serve only models whose commitments are entered in a shared register maintained by the Inspectorate, and may not run training jobs above an agreed compute threshold.

Variations of this rule appear throughout the recent AI governance literature. For example, a [2026 open letter](https://www.pacingthefrontier.com/) signed by AI lab employees calls on the US government to back international work on "the technical and governance tools needed to deliberately pace the frontier of automated AI development". In a [related essay](https://darioamodei.com/post/we-must-pace-the-frontier), Anthropic CEO Dario Amodei argues that pacing "does not mean halting model training" and that "any agreement must either have ironclad verifiability, or must be limited enough that defection would not be militarily existential". Notably, Amodei's essay points to human evaluators embedded inside labs as "the key step for verifiability of any pacing commitments" and does not mention cryptographic proofs (though Anthropic separately publishes FlashProve, one of the provers on our ladder). We use the registered-inference rule here because it is the setting that technical verification papers study most closely.

## What an inspectorate actually needs to know

A [RAND framework](https://arxiv.org/abs/2507.15916) divides international AI verification into two halves: "verifying that declared uses of large-scale AI compute are compliant", and "verifying that there are no undeclared uses of large-scale AI compute". Hardware engineers at [Amodo Design](https://amododesign.com/notes/2026-06-23-verification-algorithms/) borrow a complementary distinction from nuclear safeguards: a state's declarations must be checked both for *correctness* (are the declared workloads what the state says they are?) and for *completeness* (did the state declare every workload it ran?).

| What the Inspectorate needs to establish | Can a proof of inference establish it? |
|---|---|
| How many AI accelerators exist, and where they are located | No |
| That no undeclared data centres exist | No |
| That a specific reply is what a registered model outputs for a given prompt | Yes: this is the exact statement a proof of inference verifies |
| That the model serving live traffic is the same model that passed safety evaluations | Partially: proofs can tie both the evaluation replies and the served replies to the same weight commitment |
| That a declared data centre ran no unauthorized training or side jobs | Not by itself: requires tamper-resistant boundary hardware logging all traffic |
| How the model was trained, or what capabilities sit latent inside its weights | No |

As the table shows, cryptographic proofs address the third row directly and contribute to the fourth. The rest of this page examines how far that guarantee can be stretched across five operational stages.

:::explore treaty
Walk through the six steps of a treaty verification workflow: see what each party holds at each step, what the Inspectorate can conclude, and what remains out of reach.
:::

## The five stages

:::stage measured This reply is what the registered model gives
First, the operator computes a cryptographic [[commitment]] to its model weights and records that digest in the Inspectorate's register. Later, when the Inspectorate holds a prompt and a reply, the operator generates a [[proof of inference]]. The Inspectorate runs the verifier program on the registered commitment, the prompt, the reply, and the proof. It needs neither the model weights nor a GPU.

This first stage is what our benchmark tests directly: we run each system's prover and verifier, check that the verifier rejects tampered models, prompts, and replies, and measure how much GPU time each proved reply costs relative to normal serving.

Even at this first stage, current prototypes come with strict practical constraints. Because proofs require deterministic finite-field or integer arithmetic, they cover a [[quantization|quantized]] copy of the model under greedy decoding rather than standard floating-point serving, meaning the operator must serve that exact quantized copy in production for the proof to match live outputs. Context lengths are also tight: our Level 1 workload uses 512 prompt tokens and 512 reply tokens, and Anthropic [notes](https://www.anthropic.com/research/provable-inference) that FlashProve "currently proves inference over contexts of up to 1,024 tokens". Moreover, the Inspectorate sees every prompt and reply it checks, along with the model's architectural dimensions. Whether a proof leaks anything about the weights is a claim we record from each publisher's documentation rather than testing ourselves; for instance, FlashProve's [documentation](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/what-is-proved.md#L9-L27) states that its authors "expect, rather than know, that the programs hide the weights at the default setting, in honest runs, if the provider keeps its duties". Finally, every model on our Level 1 ladder is an open-weights release rather than a closed state-held frontier model.
:::

:::measured rows
Benchmark results measured so far. The cost multiple is the GPU time of generating one proved reply divided by the GPU time of serving one unproved reply on the same hardware. Where a system separates token generation from proof generation, both parts are shown. See [How to read a row](/before-you-rely#reading-a-row).
:::

:::stage demonstrated The model that was evaluated is the model that serves
A real treaty will not just require that a model be listed in a register; it will require that the registered model pass agreed capability or safety evaluations first. Proofs of inference can link those two steps: if the replies during the evaluation session and the replies during live serving are both proved against the same weight commitment, the Inspectorate knows both came from the same underlying weights. As a [policy memo](https://thefuturesociety.org/international-ai-verification) from The Future Society puts it, verification "can confirm that the model evaluated is the one the provider claims it to be".

Researchers have [demonstrated this workflow](https://arxiv.org/abs/2402.02675) on small models. We know of no published demonstration of a full frontier safety evaluation conducted under cryptographic proof, and any such evaluation would have to fit within the context-length and greedy-decoding constraints of the prover. Just as importantly, identical weights do not mean identical behavior in deployment: system prompts, scaffolding, and output filters sit outside the model weights and can drastically alter how a model acts. Nor can a proof tell you whether the evaluation suite itself asked the right questions.
:::

:::stage proposed A sample stands for the traffic
Proving every single reply in a busy data centre would multiply the facility's GPU requirement by the prover's full cost multiple. To make verification affordable, several proposals combine proofs with random spot-checking. First, tamper-resistant hardware at the data centre's network perimeter records a cryptographic hash of every prompt and reply entering or leaving the facility. Later, the Inspectorate selects a small random sample of those logged requests and challenges the operator to produce proofs for them.

As a [research note](https://www.aisafety.sg/research/what-proving-llm-inference-actually-costs-research-note) from the Singapore AI Safety Hub explains, two conditions are essential for random sampling to have teeth: "the draw must be unpredictable to the provider, and the provider must commit to its answers before the draw." When both conditions hold, an operator that substitutes an undeclared model on 1 out of every 100 replies will be caught about 95 times in 100 by a sample of 300 draws. An operator that substitutes an undeclared model on 1 out of every 10,000 replies will be caught about 3 times in 100 by 300 draws. Whether a tiny fraction of unverified traffic is an acceptable treaty risk is a political judgment for the signatories.

Notice what this sampling architecture entails even when the cryptography works as advertised:

- Because the operator does not know in advance which requests will be sampled, it must generate *every* live reply using the prover-compatible quantized copy of the model.
- The boundary logging box sits inside State A's facility and must be trusted not to drop or alter records, bringing hardware trust back into the picture.
- Because generating a proof takes much longer than serving a reply, proofs arrive after the fact: the system detects violations after they happen rather than blocking them in real time.
- If the operator fails to return a proof for a sampled request, the treaty text must define whether that counts as a technical fault or a treaty breach.

Today, the pieces of this pipeline exist only in isolation. [Amodo Design](https://amododesign.com/ai-verification/plan-a-sitrep/) has demonstrated optical network taps at current link speeds alongside recomputation of sampled requests, and academic researchers have [designed](https://arxiv.org/abs/2606.10724) a boundary fingerprinting appliance on paper, while we run the provers themselves here. As the Singapore AI Safety Hub note observes, "Nothing yet ties a proof to what the certifier recorded."
:::

:::stage outside The data centre did nothing else
A treaty limit is ultimately about what a facility *does not* do, and a proof of inference is completely silent about unproved compute on the same cluster. Anthropic [states](https://www.anthropic.com/research/provable-inference) directly that a proof "does not establish that the hardware is not, e.g., training on the side", and Attestable [makes the same point](https://attestable.com/blog/pacing-ai-requires-proof): "Workload compliance and compute coverage are separate problems."

Closing that loophole requires physical and hardware controls rather than cryptography: perimeter logging on every high-bandwidth link, defenses against covert side channels, periodic memory scrubs, and on-site inspectors. When Amodo Design [audited](https://amododesign.com/ai-verification/plan-a-sitrep/) the seventeen engineering components required for one such perimeter-based verification plan, it graded four as having active work underway and seven as "Not on track". Even a watertight perimeter tap only sees traffic that leaves the building; if a lab uses its cluster internally to generate synthetic training data or run automated R&D without exporting the traffic across the perimeter, boundary taps will never see it unless the facility's internal network is tapped as well.
:::

:::stage outside Nothing was left undeclared
Every stage above takes place inside facilities that State A chose to declare. No cryptographic protocol can find a secret cluster hidden in an undeclared warehouse. As [Attestable](https://attestable.com/blog/pacing-ai-requires-proof) writes, "A proof cannot discover a datacenter that was never declared". Detecting undeclared facilities requires supply-chain tracking of AI chips, satellite imagery, power-grid monitoring, on-site inspections, and traditional intelligence. That division of labor mirrors nuclear arms control: as a [US Congressional Research Service report](https://www.everycrsreport.com/reports/R41201.html) notes, the United States and Russia "rely on their own national technical means of verification (NTM) to collect most of the information needed to verify compliance with arms control agreements".
:::

## Proofs versus guarded recomputation in a treaty

Most technical blueprints for international AI verification answer the Inspectorate's spot-check challenges by re-running the sampled prompts inside a guarded hardware enclave rather than generating cryptographic proofs. For example, the [verification supplement](https://ai-2040.com/supplements/verification-plan) to the AI 2040 scenario recommends "a network-tap and recomputation based approach", describing zero-knowledge proofs as promising but "somewhat speculative". ([Three ways to check](/three-ways) compares the two approaches in detail.)

Proponents of cryptographic proofs (many of whom build provers themselves) point to three advantages in an adversarial state-to-state setting:

- **No second copy of the weights.** Re-running sampled traffic requires placing a copy of State A's frontier weights onto a verification cluster that State B trusts not to cheat and State A trusts not to leak. With a proof, the weights never leave State A's serving cluster.
- **No reliance on foreign chip vendors for the check itself.** While boundary traffic logging still requires trusted hardware, checking the proof itself does not depend on enclave attestation keys held by a chip manufacturer.
- **Third-party auditability.** Any party given the prompt, the reply, and the proof can verify the result on its own CPU without seeing the weights (though because those prompts and replies come from State A's users, State A still controls which transcripts can be shared).

The drawbacks are equally concrete: the operator must serve a quantized integer variant of its model on every request, the Inspectorate sees the full text of every sampled prompt and reply plus the model's dimensions, the compute overhead is steep, and early proof systems carry real implementation risk. As the Singapore AI Safety Hub [cautions](https://www.aisafety.sg/research/what-proving-llm-inference-actually-costs-research-note), "bugs in deployed proof systems have let provers prove false statements before".

For those reasons, The Future Society's policy memo ranks reducing the overhead of zero-knowledge proofs fifth out of five verification R&D priorities, behind four hardware-focused workstreams, characterizing it as "a high-upside, high-uncertainty task" whose primary appeal is that it can "sidestep the hardware-trust problem".

## What the Inspectorate can and cannot conclude

Suppose the boundary logging hardware is in place and the proofs verify cleanly. The Inspectorate can then report one precise finding: every reply drawn in its random sample matches the output of the registered model's quantized copy for the recorded prompt, verified without touching the model weights. If State A permits the sampled prompts and replies to be shared, State B can run the same verifier and confirm the verdict itself. Without trusted boundary logging, the Inspectorate can make that statement only about transcripts State A chose to hand over.

What the Inspectorate *cannot* conclude from proofs alone is that State A is complying with the treaty. Compliance is an all-source judgment combining chip inventories, perimeter telemetry, physical inspections, and intelligence, in which inference proofs are at most one piece of evidence. Just as the INF Treaty relied on ["successive layers of procedures"](https://www.armscontrol.org/act/2007-06/looking-back-intermediate-range-nuclear-forces-treaty), The Future Society's memo emphasizes that for AI governance, "No single mechanism is sufficient or fully secure against a capable state adversary". And of course, technical verification cannot keep a treaty alive when politics change: [New START](https://www.armscontrol.org/factsheets/new-start-glance), the last treaty limiting US and Russian strategic nuclear arsenals, expired in February 2026 despite well-established verification procedures.

As the same Future Society memo notes: "Most verification proposals originate with the laboratories and researchers who design them. A government with sufficient technical capacity of its own can test these proposals against shared benchmarks, so that competing designs become comparable." We built this site to provide that kind of shared benchmark for inference provers. Read our [mandate](/mandate) for how we operate, or continue to [Before you rely on a proof](/before-you-rely) for a practical checklist on reading our results.
