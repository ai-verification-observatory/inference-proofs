Before a benchmark of inference provers runs a single command, it has to settle three things: what every system is asked to do, what checks a system must pass before its numbers count, and which single figure orders the rows.

## What is fixed before the first run

Published benchmarks for inference provers usually vary four things at once: the model, the hardware, the timing boundaries, and the mathematical statement being proved. We hold the hardware, the timing rules, and the request constant. We cannot hold the model constant across every system because no two runnable systems currently support the same model at their pinned commits, so each model forms its own rung and nothing is ranked across rungs. Nor can we force every system to prove the exact same statement, so we document each system's statement alongside its row.

1. **The rules are frozen in advance.** The level file fixes the constants for the request, the sessions, the steady-state test, the serving baseline, the ordering rule, and the fidelity check. The trial counts for negative controls and the thresholds for the glyph live in the RFC. The design goal is a level file "frozen before the first counted run, so no constant is chosen after seeing a row". Every counted run records the SHA-256 digest of that frozen file, and the [mandate's line on the level](/mandate#level) shows it on hover. Where the history of Level 1 departed from that goal is recorded below under [Who wrote the rules](#who-wrote-the-rules-and-how-they-changed).
2. **Nobody hand-picks the prompts.** Prompts are 512-token windows sliced from public-domain books using a random seed drawn from a [public randomness beacon](https://docs.drand.love/): specifically, the first beacon round published after the git commit that froze the level file. As the RFC puts it, "nobody, the operator included, knows the prompts when the constants are fixed, and nobody chooses the round". Here, the operator means our own team running the benchmark harness.
3. **Systems run unpatched.** Every system is built at a full upstream commit hash with no source patches and no undocumented flags. Our [[adapter]] translates our harness invocation into the system's own CLI and changes nothing inside the prover or verifier.
4. **Clocks are read outside the container.** Our harness measures timestamps outside the system's container. A proof counts as released at the moment the harness observes its completed file on disk, because "[this project must not depend on code inside the container for its headline numbers](repo:rfcs/0011-measurement-and-sampling.md)".
5. **The weight commitment comes from our harness record.** When we run the verifier, we pass the [[commitment]] recorded by our harness during the commit step, never a commitment file bundled with a proof. Otherwise, "[a forged proof with a matching forged commitment is accepted](repo:rfcs/0014-provenance-and-integrity.md)".

## One request for every system

Every system receives the same [[request]] shape: a 512-token prompt and a 512-token reply, decoded greedily, with all 512 reply tokens verified. Keeping the request uniform across models ensures that "a multiple means the same thing on every rung".

Two details in that specification prevent subtle ways of shifting a number without improving a prover. First, end-of-sequence tokens are masked so generation never stops early, "[so every request decodes exactly the tokens the harness counts](repo:rfcs/0015-reference-rows.md)". Second, accepted proofs must cover all 512 reply tokens. The RFC does not argue for 512 tokens over another fixed count, though it explains why we never publish a per-token cost figure: for architectures that prove a fixed context window at once, the number of tokens checked inside that window is "[a request parameter with no measured effect on cost](repo:rfcs/0017-requests-tasks-and-tested-states.md)", meaning a per-token figure "would rank adapters".

The 1,024-token total context length (512 prompt plus 512 reply) was set by the limits of the first systems tested, one of which supports a maximum window of 1,024 tokens. Within that ceiling, the RFC keeps a shorter reply length only as a documented fallback.

## Ranked inside a rung, never across

Each open-weights model is a [[rung]] on the ladder, and a system has a row on every rung where we have run it. Systems are ranked strictly inside a single rung, never across different models.

:::quote repo:rfcs/0018-level-1-ladder.md#motivation RFC-0018, Motivation
No two runnable systems share a model at their pins. [...] A table that sorts the two against each other compares models, not provers.
:::

It can be tempting to compare multiples across rungs because dividing by each model's serving baseline normalises away raw model size. The RFC explicitly rejects cross-rung comparisons anyway: "a 400B mixture-of-experts and a dense 8B differ in what serving costs and in how proving scales; the ratio would mix both".

## Six checks before any ranking

A benchmark that only times honest runs cannot distinguish a real verifier from a script that prints "accepted" on every file. A system is therefore ranked on a rung only after all six [[check|checks]] have [[passed]] in our harness.

| Check | What we do | What a held check shows |
|---|---|---|
| [Run](/checks#run) | Run three complete sessions from a cold start, each on its own prompt set | The unmodified system produced an accepted proof for every request across all three sessions |
| [Model](/checks#model) | Perturb one model weight; also verify an honest proof against the perturbed model's commitment | Both mismatches were refused |
| [Prompt](/checks#prompt) | Change one token in the prompt | The verifier refused the proof for the altered prompt |
| [Reply](/checks#reply) | Change one reply token at the first, last, and an interior position | All three alterations were refused, and accepted proofs cover all 512 reply tokens |
| [Verify without weights](/checks#no_weight_file) | Trace every file the verifier opens, with no GPU attached and no model weights on disk | The verifier reached its verdicts without reading a weight file |
| [Fidelity](/checks#fidelity) | Compare the proved model's replies against replies from the publisher's original weights | The proved model matches the original more closely than deliberately damaged control models |

The three tampering tests (Model, Prompt, and Reply) implement the [[control|negative controls]] defined in [RFC-0008](repo:rfcs/0008-negative-controls.md). Three safeguards prevent a broken harness or adapter from misreporting a system's behaviour in either direction:

- **The honest twin.** Every tampered input is verified alongside its untouched original in the same run. If the verifier does not accept the untouched proof, the trial is void, "so a broken control or a broken run cannot pass for a strong verifier".
- **Three distinct outcomes.** Every check finishes as held, failed, or undecided, and an undecided check always states its cause. An undecided result "is never worded as a failure".
- **Reproduce outside our adapter before publishing a failure.** If a verifier accepts a tampered input inside our adapter, the check remains undecided until we reproduce that acceptance using the system's own standalone CLI outside our harness. When a flaw is real, we notify the publisher first under the embargo in our [security policy](repo:SECURITY.md). When the fault lies in our adapter, we fix our adapter.

No human reviewer assigns check outcomes by hand; every state is derived automatically from stored run records linked on each system page.

:::note What the checks do not show
None of our checks attempts to construct a cryptographic forgery. As the RFC notes: "Tests cannot tell a proof from a signature." A system whose "proof" was merely the operator's digital signature over the commitment, prompt, and reply (signed after checking that the local weights matched the commitment) would reject every single perturbation we run. Our checks demonstrate that the specific alterations we tested (one weight, one prompt token, three reply positions, across three trials each) were refused. They do not prove that every possible forgery would be refused, that the proof system is [[soundness|sound]], or that proofs hide the weights. Those cryptographic properties come from what each publisher documents and are labelled accordingly.
:::

## Fidelity: is the proved model the publisher's?

"[A system can quantize a model until proving it is cheap.](repo:rfcs/0018-level-1-ladder.md#motivation)" The Fidelity check tests how far the model that a system actually proves has drifted from the model the publisher released.

For each prompt, we score a reply by counting how many leading tokens it shares with the greedy reply of the publisher's original weights. We compute the same prefix-match score for two sets of reference copies: honest variations (a second run of the original weights and two mild quantizations) and deliberately damaged copies (two aggressive quantizations, a copy with a quarter of its transformer blocks removed, and a smaller model from the same family). The threshold is set by the highest-scoring damaged copy that still falls below every honest copy. A system holds the Fidelity check when its replies score significantly above that threshold in a paired test across the prompt set.

We also print the KL divergence from the original weights alongside the Fidelity check, though KL divergence does not gate ranking because it "comes from a program that is not the proved computation". The RFC is candid about the limits of the prefix-match gate: on the 8B rung it "is coarse at 15 replies" and only "stops gross damage".

## One figure: cost vs serving

"[A proving rate alone says nothing about cost relative to the work being proved](repo:rfcs/0015-reference-rows.md)." We therefore rank systems by a dimensionless ratio on the same model, the [[multiple]]: m (steady-state GPU-seconds per additional proved reply, including generation, averaged across three sessions) divided by b (GPU-seconds per reply served at full load on the same GPU type). [Where the cost goes](/cost) walks through the anatomy of a session and both numbers.

Both the numerator and the denominator have rules designed to prevent gaming. On the proving side, replies are grouped by the wall-clock time their proof files appear on disk rather than by internal batch labels. That rule grew out of a mistake of our own: an earlier formula counted more replies than the steady window had actually completed, making proving look cheaper than it was. On the serving side, full load is found by stepping up request concurrency until throughput plateaus; if throughput is still climbing at the highest concurrency step, the baseline run is rejected outright. The aim is "a cost figure that a hostile expert cannot move by choosing a window, a batch or a baseline".

Two trade-offs remain in the [serving baseline](repo:rfcs/0015-reference-rows.md). Running a standard serving engine with its default flags "is not the maximum achievable serving throughput". And because the baseline serves the publisher's default precision while provers quantize the weights, the resulting multiple "mixes the cost of proving with a precision difference the publisher chose".

:::measured rows
A row with too few release groups has no steady-state m and prints its whole-session cost over b instead, labelled whole sessions.
:::

## Order

Inside a rung, one system is placed above another only when its multiple is at least 10 % lower and its highest session m is below the other system's lowest session m. Any system with a steady-state multiple sits above a system that only has a whole-session figure. A system's numerical position is one plus the number of systems placed above it, so tied systems share the same rank. Finally, a system that passes all six checks receives a ranked position only if its publisher states a security level in bits. We print that security level as stated without enforcing a minimum floor in Level 1, because "tests cannot tell 60 bits from 128, and the levels publishers state are not comparable without recomputation".

## The glyph: stated, then lowered by tests

Passing the six checks is the entry gate to be ranked. Alongside each row, the five-petal [[glyph]] summarises how close the system comes to having five verification properties in full: Unforgeable, Weights hidden, Faithful model, Machine-checked, and No third party trusted. Each petal is drawn as green (in full), amber in part, amber in lesser part, red (absent or unstated), or hollow (undecided). Four of the petals are derived from structured facts copied verbatim from the publisher's documentation at the pinned commit, each backed by a quote and link; no reviewer types a colour directly. The fifth petal, Faithful model, is set by our Fidelity check.

- **One fact per petal.** Whether a soundness bound is mathematically proven or conjectured, together with its bit exponents, determines Unforgeable; how much of the system is covered by a machine-checked theorem determines Machine-checked alone.
- **Each petal stands on its own.** Each petal is graded on its own criteria as if the other four were green, and the five petals are never summed into a single score.
- **Silence is red.** Because "a guarantee nobody states is one nobody can rely on", a property on which the publisher's documentation is silent is drawn as a red outline. Unread documentation is distinct from silence: if a system's docs have not been reviewed yet, the petal stays hollow.
- **Tests only lower a petal.** A failed check turns the corresponding petals solid red. Passing a check never turns a petal green: a passed negative control only shows that specific perturbations were refused, and "[reading more into it would turn a test into a certificate](repo:rfcs/0016-glyph-properties-and-states.md)".
- **The glyph never affects ranking.** Position inside a rung is determined solely by the cost multiple among systems that passed the six checks.

## What was set by judgement

Several numerical thresholds in Level 1 are engineering judgements fixed before the runs rather than mathematically derived constants:

- the 10 % separation margin in the ordering rule;
- the 5 % tolerances used to detect steady-state proving and full-load serving;
- running three trials per negative control;
- the 0.05 significance level of the paired fidelity test;
- the 128-bit, 100-bit, and 80-bit cutoffs for the Unforgeable petal (borrowed from the Ethereum Foundation's zkEVM security milestones and NIST SP 800-57 rather than derived from first principles).

If any of those thresholds looks wrong to you, please [open an issue](https://github.com/ai-verification-observatory/inference-proofs/issues).

The same goes for what Level 1 leaves out of scope: proprietary closed-weights models, self-reported runs executed on a vendor's own cluster, and third-party recalculation of cryptographic soundness bounds. A draft of [Level 2](repo:rfcs/0018-level-1-ladder.md#levels) is published alongside Level 1 "so labs can prepare": it adds a 100-bit security floor recomputed from the deployed parameters, a KL divergence gate tied directly to the proved arithmetic, and audit prompts chosen after replies are served.

## Who wrote the rules, and how they changed

Our [mandate](/mandate) lists the people and institutions behind this benchmark. RFC-0018 also includes a conflict-of-interest disclosure that we repeat here because it touches the rules explained on this page: the RFC text "was drafted with an AI agent, Claude, made by Anthropic, which publishes FlashProve". The disclosure highlights the rules that bear most directly on FlashProve: counting reply generation inside m, the serving baseline definition, and the ordering rule's requirement that a publisher state a security level (FlashProve states a security level for its Lean verifier, whereas its benchmark row runs the C++ verifier, for which no level is stated). On the glyph rules, the note points out that FlashProve is currently the only catalogued system eligible to score above red on the Machine-checked petal, while the proof-build verification rule keeps that petal hollow until our harness records a Lean build. It also notes three design choices that work in FlashProve's favour: counting a protocol-level soundness bound toward Unforgeable, not grading which specific model format a commitment binds, and recording our own explicit readings of FlashProve's documentation for No third party trusted and Machine-checked.

Every rule change goes through a public [RFC](repo:rfcs/README.md), and a frozen level file is meant to stay untouched once runs begin. Level 1's actual history departed from that ideal twice. First, `levels/L1.yaml` was frozen three times on 2026-11-11, each time drawing a fresh randomness beacon round: once when a rung was added, and again when the serving concurrency ladder had to be extended because the initial concurrency steps did not saturate the largest model. Second, two rules were added to RFC-0018 after the final level freeze: SE-5 (handling requests that a system's own code refuses to run) and CO-7 (splitting m into generation and proving phases, drafted after the first FlashProve session was recorded). Neither post-freeze addition altered any benchmark constant, total m, or the ordering of rows.

## Reading on

Below are the normative RFCs for this benchmark, followed by the papers and system documents that this track draws on, ordered from foundational texts to specific provers and attacks.

:::reading
- [RFC-0018: Level 1](repo:rfcs/0018-level-1-ladder.md). The full specification summarised on this page, including rejected alternatives and known limitations.
- [RFC-0008: Negative controls](repo:rfcs/0008-negative-controls.md). Every tampering test, its expected result, the honest-twin rule, and the coordinated disclosure policy.
- [RFC-0002: Claim card](repo:rfcs/0002-claim-card.md) and [RFC-0015: Reference rows](repo:rfcs/0015-reference-rows.md). How a system's documented statement is recorded and how the unproved serving baseline is measured.
- [Proofs, Arguments, and Zero-Knowledge](https://people.cs.georgetown.edu/jthaler/ProofsArgsAndZK.html). Justin Thaler's textbook, freely available online. Chapters 2 through 5 cover Freivalds' matrix-product check, the sumcheck protocol, and the Fiat-Shamir transformation.
- [17 misconceptions about SNARKs](https://a16zfrontier.com/posts/article/17-misconceptions-about-snarks/). Thaler, 2023. Concise clarifications of common confusions, including what "bits of security" means and why finite-field size matters for performance.
- [zkCNN](https://eprint.iacr.org/2021/673). Liu, Xie, and Zhang, 2021. Introduces the linear-time sumcheck protocol for convolutions and FFTs that later tensor provers build upon.
- [zkLLM](https://arxiv.org/abs/2404.16109). Sun, Li, and Zhang, 2024. Combines sumcheck with a parallel lookup argument (`tlookup`) for non-linear layers on models up to 13 billion parameters. Read alongside the repository notice that the released code is an interactive, unaudited prototype.
- [zkGPT](https://www.usenix.org/system/files/usenixsecurity25-qu-zkgpt.pdf). Qu et al., 2025. A non-interactive prover for GPT-2 with a detailed phase-by-phase breakdown of prover runtime.
- [DeepProve](https://eprint.iacr.org/2026/1112). Gailly et al., 2026. Certifies an entire multi-token reply in a single forward pass over the prompt plus reply; source of the CPU phase breakdown cited in this track.
- [SASH: the statement](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/4f41667297430a598165c4a8604258fe37d952ae/docs/statement.md) and [the statement gap](https://github.com/sg-ai-safety-hub/zk-inference-results/blob/11decec3c0b62c707618aab5deb82750b355d202/docs/statement-gap.md). A clear, edge-by-edge account of what a single segment proof binds and how the proved computation differs from standard serving.
- [FlashProve: what is proved](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/what-is-proved.md) and [known limits](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/known-limits.md). Explains what a machine-checked Lean soundness theorem covers and what still rests on unverified C++ and CUDA code.
- [VerInf](https://github.com/JamesPetrie/VerInf/blob/7947bb9a6c7ec86ea97927c76370b3920b6269f6/README.md). Petrie, 2026. Proves a different statement: an upper bound on how much information in a floating-point reply is left unexplained by a committed integer model.
- [How to Prove False Statements: Practical Attacks on Fiat-Shamir](https://eprint.iacr.org/2025/118). Khovratovich, Rothblum, and Soukhanov, 2025. Shows why the specific circuit being proved, and who chooses it, is part of a system's soundness claim.
- [On the Distribution of the Distances of Random Words](https://eprint.iacr.org/2025/2010). Diamond and Gruen, 2025. One of three papers that disproved the proximity-gap conjecture underlying many conjectured STARK security levels.
- [TEE.fail](https://tee.fail/), alongside [Tinfoil's account](https://tinfoil.sh/blog/2026-02-03-proving-model-identity) of attesting model weights. What hardware enclaves can attest about a model, and how physical memory-bus interposers break that guarantee.
- [DiFR](https://arxiv.org/abs/2511.20621) and [bit-exact recomputation](https://arxiv.org/abs/2606.00279). Karvonen et al., 2025, and Cankaya, 2026. Verifying inference by re-running the model, either with a tolerance for floating-point drift or with deterministic kernels.
:::

For a broader survey of the literature, see the [AI Workload Verification Papers](https://github.com/WHodgkins/AI-Verification-Papers) bibliography maintained by Will Hodgkins, building on earlier reading lists by Mauricio Baker and James Petrie.
