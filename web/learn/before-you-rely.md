A cryptographic verifier outputs a simple accept or refuse, but the [[relying party]] still has to decide what an accepted proof is worth in the real world. This page offers a practical checklist of nine questions to ask before relying on any inference proof system, showing where our benchmark answers them and what you still have to verify on your own.

## Nine questions to ask

### 1. What exact statement does a passing proof establish?

Ask for the precise mathematical relation being proved, not a one-line summary. Does a proof cover every token of the reply, or only a single layer or segment? Does it require each output token to be the exact top-scoring token of the model, or does it allow a numerical tolerance? Each system's [[claim card]] in our repository records its [[statement]] in the publisher's own words, with direct links to the upstream source files. On our benchmark, we hold every system to the same standard: a complete 512-token reply with every output token checked.

### 2. Where did the prompt, the reply, and the model commitment come from?

A proof only connects a specific prompt and reply to a specific [[commitment]] digest. Always ask who supplied those three inputs. If the operator chose which prompt and reply to prove, the proof only shows that the operator has a model capable of producing that reply, "[not that it necessarily served it earlier](https://arxiv.org/abs/2402.02675)". Spot-checking a sample of live traffic only works if a tamper-resistant boundary log recorded the traffic *before* the sample was drawn, using randomness the operator could not predict.

Similarly, ask who published the model commitment and how you know it corresponds to the model you care about (whether through a developer's signed release, a public model register, or an evaluation report). A valid proof only says *this reply came from the weights behind this commitment digest*; if you let the operator hand you a fresh commitment digest alongside each proof, the check proves nothing about model identity. In our harness, the verifier always reads the commitment from our own stored record, never from files bundled with the proof.

### 3. How close is the proved model to the model that is normally served?

Because cryptographic proof systems require bit-for-bit deterministic arithmetic, provers operate on a quantized integer or fixed-point copy of the model under greedy decoding, up to a fixed context limit. Ask what changes the operator had to make to serve that exact copy in production, and how closely that copy tracks the original unquantized weights. A sloppy quantization can degrade the model just to make proving cheaper. On this site, our [Fidelity check](/checks#fidelity) and the "Faithful model" petal of the [[glyph]] measure that gap directly: we compare the prover's replies against the publisher's unquantized reference weights and require them to score above intentionally damaged calibration copies. When a row reads "Fidelity check undecided", that comparison has not yet been completed.

### 4. Who has run the prover besides its own authors?

Performance numbers in a team's launch blog post or paper are naturally measured on the model, hardware, and workload that team chose. Ask whether anyone outside the team has built and run the public code unpatched on a standardised workload. That is the core job of this benchmark: every figure on our site carries its unit, and a system's page prints what each figure timed, its sample size and links to the run records behind it. None of our runs have yet been reproduced by a second benchmark operator, and we label every figure accordingly. Apply the exact same scrutiny to us: our [mandate](/mandate) discloses who runs this benchmark and lists our conflicts of interest.

### 5. How hard is it to forge a proof, and on what basis?

When a publisher quotes a [[security level]] (such as 100 bits or 128 bits), three follow-up questions matter more than the headline number:

1. Is that bound mathematically proved, or conjectured from the absence of known attacks?
2. Does the theorem cover the actual verifier binary that runs on your machine, or only an idealised protocol on paper?
3. Have cryptographers outside the author team reviewed the proof?

In late 2025, a mathematical conjecture used to set parameters in several production proof systems was disproved in its strongest form, prompting the Ethereum Foundation to [warn](https://blog.ethereum.org/2025/12/18/zkevm-security-foundations) that "what was advertised as 100 bits might actually be 80". Existing proofs still verified cleanly; nothing visible to a verifier program changed when the theoretical bound dropped. Our "Unforgeable" petal reports what each publisher's documentation states about its soundness bound, while our tampering checks pull the petal down to red if the verifier accepts a modified model, prompt, or reply.

### 6. Whom else do I have to trust?

Some proof systems rely on a one-time setup ceremony whose secret randomness must be destroyed, a chip vendor's attestation key, or a designated verifier. Others rely only on public randomness (a transparent setup) that anyone can regenerate and check. Our "No third party trusted" petal reports which trust model the publisher documents (and flags whenever the step rests on our reading of their docs rather than an explicit statement). Keep in mind that you always trust the verifier binary itself, so it is worth asking who has audited the verifier code, and in any traffic-sampling scheme you also trust whatever hardware recorded the traffic.

### 7. What does the proof reveal about the model and the traffic?

Any verifier sees the prompt and reply being checked, along with architectural constants like layer dimensions. If the model weights are proprietary, ask whether the proof system mathematically hides the weights (zero-knowledge), whether it still exposes parameters fitted to the weights (such as quantization scales), and whether weight hiding is proved for the implementation or merely expected to hold. Our "Weights hidden" petal records the publisher's documented claim, while our [Verify without weights](/checks#no_weight_file) check confirms the narrower empirical fact that the verifier ran on a CPU machine with no weight file on disk.

### 8. What will proving cost at the sampling rate I need?

Proving every single reply multiplies your serving bill by the system's full cost multiple. If your use case allows random spot-checking after the fact, you can prove only a fraction of replies: for example, drawing 300 random replies catches a 1-in-100 model substitution about 95 times in 100, and catches a 1-in-10,000 substitution about 3 times in 100. (Of course, if a customer wants a receipt for *their specific reply*, sampling across other users does not help.)

Even when you sample, the total cost does not drop all the way to zero. Because a reply can only be proved if it was generated by the prover's deterministic quantized copy of the model, and the operator does not know in advance which replies will be sampled, the operator must run that prover-compatible generation pass on *every* reply; only the cryptographic proving step scales down with the sampling rate. Where a system separates token generation from proof generation, we print both parts of the multiple so you can see the floor.

:::explore cost
Explore how sampling changes the total bill: every reply pays the generation multiple of running the committed model copy, while only the sampled fraction pays the proving multiple.
:::

Also check what verification costs on your side: our ladder prints the CPU verification time per reply, and each system's page reports the proof size in megabytes.

### 9. What happens when a proof fails or never arrives?

No cryptographic protocol can stop an operator from going offline, returning a timeout, or claiming a hardware fault when challenged. Before deploying or mandating proofs, your contract or governance rule must specify the deadline for returning a proof and the penalty when one is missing.

## Reading a row

- **Standing.** "Passed" means all six [benchmark checks](/checks) held for that system on that model. If any check did not hold, the row lists which checks failed or remain undecided. An undecided check is not a failure; it usually means a test is still pending or hit a documented system constraint.
- **Position.** Only systems that passed all six checks *and* whose publishers state a cryptographic security level at the pinned commit receive a numbered position, ordered strictly within that model's table. Nothing is ranked across models.
- **The glyph.** Five petals summarise what kind of proof the system produces. Green means the property holds in full; amber, that it holds in part, or in lesser part (the arm's end cut off); solid red, its name struck, that the property is not met or one of our checks failed; a red outline, that the publisher's documentation at the pinned commit is silent on that property; a grey outline, that the petal is still undecided. Four petals reflect the publisher's documented statements, while Faithful model reflects our fidelity measurements. The glyph never changes a row's ranking position.
- **[Cost vs serving](/checks#multiple).** The GPU-seconds required to produce a proved reply, token generation included, divided by the GPU-seconds required to serve an unproved reply on the same model and hardware. Where a system generates its replies in a phase of its own, its two parts are printed under it: commit and proving, and generation.
- **[Cost](/checks#cost).** The same GPU time in US dollars per proved reply, at the release's price for one H200 GPU-hour.
- **[Verify time](/checks#check-time).** The CPU seconds the verifier takes per reply, with no GPU and no weights.
- **[Fidelity](/glossary#fidelity).** The share of reply positions where the system's top token is the original model's, as a percentage, with the model's Q8_0 and Q4_K_M copies under it to read it against. It sets no state: the Fidelity check's state (held, failed or undecided) is in the system's checks and its Faithful model petal.

The ladder prints each figure with its unit alone; a system's page prints what each figure timed and its sample size (n). A ranked position needs three completed sessions, so a figure over fewer sessions is provisional.

## What this benchmark will not tell you

- **Whether a proof system is mathematically unforgeable or zero-knowledge.** Our harness does not attempt cryptanalysis or weight extraction. Passing our six checks shows that the verifier rejected the specific tampered inputs we fed it on our fixed workload, not that a sophisticated attacker could never forge a proof.
- **How these systems perform on closed proprietary models.** Level 1 benchmarks open-weights models exclusively.
- **Whether a real-world facility is complying with a governance rule.** Answering that requires the physical and hardware layers discussed on [A treaty, stage by stage](/treaty).
- **Which trade-off is acceptable for your application.** Only you can decide your ceiling on cost multiple, verification latency, or trust assumptions. If you have a concrete target workload or threshold in mind, [open an issue and tell us](https://github.com/ai-verification-observatory/inference-proofs/issues).

## Words that differ in policy and cryptography

| Term | In policy and safeguards | In cryptography |
|---|---|---|
| Verification | An overall judgement that a party complied with an agreement | Running a verifier program that outputs accept or refuse on a single proof |
| Verifier | The inspectorate, auditor, or government conducting the check | The software program that checks a proof file |
| Commitment | A political or legal pledge by a state or company | A short cryptographic digest that locks in data without revealing it |
| Binding | Legally enforceable | Mathematically locked: a proof generated for one input is rejected if checked against another |
| Completeness | A declaration leaves no facilities or workloads out | An honest prover with a true statement always produces an accepted proof (the two meanings are unrelated) |
| Attestation | A formal declaration that a standard is met | A hardware enclave's cryptographically signed measurement report (relies on the chip vendor's key, unlike a mathematical proof) |
| Proof | Evidence strong enough to support a conclusion | A mathematical object checked by a verifier algorithm |

## Reading on

Ordered from accessible policy overviews to technical systems papers, drawing on the sources cited across this track:

:::reading
- [Verification methods for international AI agreements](https://arxiv.org/abs/2408.16074). Wasil, Reed, Miller, and Barnett, 2024. A concise survey of ten mechanisms for detecting unauthorised training runs or undeclared clusters, along with historical precedents and evasion paths.
- [The Math Behind Pacing the Frontier](https://www.aisafety.sg/blog/zkp-intro). Singapore AI Safety Hub, 2026. An accessible introduction to proofs of inference alongside trusted hardware, inspections, and recomputation, written by the team behind SASH.
- [The Compute Verification Post](https://jasminexli.substack.com/cp/207744145). Hausenloy and Li, 2026. A clear primer on verifying data centre workloads, organised by how little trust you are willing to place in the operator.
- [How To Make International AI Verification a Reality](https://thefuturesociety.org/international-ai-verification). The Future Society, 2026. A policy memo prioritising verification R&D for middle powers and arguing for shared technical benchmarks.
- [Faster AI Diffusion Through Hardware-Based Verification](https://ifp.org/faster-ai-diffusion-through-hardware-based-verification/). Ammann and Dalrymple, 2025. The case for building verification mechanisms directly into AI accelerators, with a proposed R&D roadmap.
- [AI 2040 Plan A: Verification Plan](https://ai-2040.com/supplements/verification-plan). Dean, 2026. A detailed engineering blueprint for verifying inference-only data centres using perimeter network taps, random sampling, and guarded recomputation.
- [AI 2040 Plan A: Verification SITREP](https://amododesign.com/ai-verification/plan-a-sitrep/). Amodo Design, 2026. Component-by-component engineering readiness assessment of that blueprint from a verification hardware team.
- [Pacing AI Requires Proof](https://attestable.com/blog/pacing-ai-requires-proof). Attestable. A prover team's perspective on where cryptographic proofs fit into AI governance and what problems cryptography cannot solve.
- [Verifying International Agreements on AI](https://arxiv.org/abs/2507.15916). Baker, Kulp, Marks, Brundage, and Heim, RAND, 2025. A comprehensive framework breaking AI treaty verification into four subgoals and six technical layers.
- [Verification for International AI Governance](https://www.oxfordmartin.ox.ac.uk/publications/verification-for-international-ai-governance). Harack and others, 2025. An in-depth study of what international AI agreements can verify under adversarial assumptions, including a section on proofs of inference.
- [Frontier AI Auditing](https://arxiv.org/abs/2601.11699). Brundage and others, 2026. Proposes four assurance levels for auditing frontier AI labs, culminating in "treaty-grade" verification.
- [What does it take to catch a Chinchilla?](https://arxiv.org/abs/2303.11341). Shavit, 2023. The foundational paper introducing the Prover-Verifier framing for verifying compute governance rules.
- [Progress on provable inference for large language models](https://www.anthropic.com/research/provable-inference). Anthropic, 2026. FlashProve's technical overview and a candid list of what the prototype does and does not prove. Together with the Singapore AI Safety Hub's [research note](https://www.aisafety.sg/research/what-proving-llm-inference-actually-costs-research-note), these are the primary author reports on the first two systems our benchmark set out to test.
- [A zero-knowledge protocol for nuclear warhead verification](https://www.nature.com/articles/nature13457). Glaser, Barak, and Goldston, 2014. The classic arms-control proposal for verifying warhead authenticity without measuring classified design details inside an electronic barrier.
:::

For a broader literature list, see the [AI Workload Verification Papers](https://github.com/WHodgkins/AI-Verification-Papers) bibliography maintained by Will Hodgkins (building on earlier lists by Mauricio Baker and James Petrie), which catalogues much of the research cited above.
