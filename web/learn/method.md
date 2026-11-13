A benchmark of provers has to settle three things before it runs anything: what every system is asked to do, what a system must get right to count, and which one number is compared. This page gives each rule of [[level|Level 1]], the reason its text gives, and the places where the text gives none. The rules themselves are in [RFC-0018](repo:rfcs/0018-level-1-ladder.md) and the [level file](repo:levels/L1.yaml). Where this page and they differ, they win.

## What is fixed before the first run

Published figures for provers differ in four things at once: the model, the hardware, the timing rule and the statement proved. We fix the hardware, the timing rule and the request. We cannot fix the model: no two runnable systems share one, so each model is a rung and nothing is ranked across rungs. We cannot fix the statement either, so we print it.

1. **The rules are frozen.** The level file holds the constants of the request, the sessions, the steady state, the baseline, the order rule and the fidelity test. The number of trials per control and the thresholds of the glyph are in the RFC. The stated aim is a level file "frozen before the first counted run, so no constant is chosen after seeing a row". Every counted run names the frozen file by its digest, and the level link in every page's footer carries it in its title. The record differs from the aim in two ways, given under [Who wrote the rules](#who-wrote-the-rules-and-how-they-changed).
2. **Nobody picks the prompts.** They are windows of public-domain books, drawn with a seed taken from a [public randomness beacon](https://docs.drand.love/): the first round produced after the commit that froze the level. In the RFC's words, "nobody, the operator included, knows the prompts when the constants are fixed, and nobody chooses the round". The operator there is whoever runs this benchmark.
3. **Systems run as published.** Each runs at a full commit hash, unpatched, with no option its documentation does not name. An [[adapter]] wraps it and changes nothing.
4. **Times are read from outside.** Our process reads the clock outside the system's container. A proof counts as released at the instant that process sees its files appear, because, in the words of [RFC-0011](repo:rfcs/0011-measurement-and-sampling.md), "this project must not depend on code inside the container for its headline numbers".
5. **The commitment comes from our record.** The verifier is given the [[commitment]] from our record of the commit step, never from files sent with a proof. Otherwise, as [RFC-0014](repo:rfcs/0014-provenance-and-integrity.md) puts it, "a forged proof with a matching forged commitment is accepted".

## One request for every system

The [[request]] is 512 prompt tokens and a 512-token reply, decoded greedily, with every reply token checked by the verifier. It is the same on every model, "so a multiple means the same thing on every rung".

Two details of it close ways to move a figure without changing a prover. The end token does not stop a reply, "so every request decodes exactly the tokens the harness counts" ([RFC-0015](repo:rfcs/0015-reference-rows.md)). And all 512 reply tokens must be covered by accepted proofs. RFC-0018 gives no reason for that. [RFC-0017](repo:rfcs/0017-requests-tasks-and-tested-states.md) gives a related one for printing no figure per token: for a design that proves a window, the range of tokens checked is "a request parameter with no measured effect on cost", so such a figure "would rank adapters".

The length itself is bounded by the systems: one of the first two systems accepts a window of 1,024 tokens. Within that bound the RFC gives no argument for a 512-token reply over a shorter one, and it keeps a shorter reply as a fallback.

## Ranked inside a rung, never across

Each open-weights model is a [[rung]], and a system has a row on each rung it was run on. Rows are ranked inside a rung and nowhere else.

:::quote repo:rfcs/0018-level-1-ladder.md#motivation RFC-0018, Motivation
No two runnable systems share a model at their pins. [...] A table that sorts the two against each other compares models, not provers.
:::

Ranking across rungs by the multiple looks like a way around this, since the multiple sets each model's serving cost aside. The RFC rejects it: "a 400B mixture-of-experts and a dense 8B differ in what serving costs and in how proving scales; the ratio would mix both".

## Six checks before any ranking

A benchmark that only times honest runs cannot tell a verifier from a program that accepts everything. So a system is ranked only once it has [[passed]] six [[check|checks]] that we run.

| Check | What we do | What a held check shows |
|---|---|---|
| [Run](/checks#run) | Three sessions from a cold start, each on its own prompts | The published system returned an accepted proof for every request, three times |
| [Model](/checks#model) | Change one weight; also check an honest proof against the changed weights' commitment | Neither was accepted |
| [Prompt](/checks#prompt) | Change one prompt token | That change was refused |
| [Reply](/checks#reply) | Change one reply token at the first, the last and one interior position | Those changes were refused, and the proofs cover all 512 tokens |
| [No weight file](/checks#no_weight_file) | Trace every file the verifier opens, with no GPU visible and no model file on the machine | The verifier reached its verdicts without opening a model file |
| [Fidelity](/checks#fidelity) | Compare the replies with those of the publisher's original weights | The proved copy is closer to the original than a copy damaged on purpose |

The three tampering checks reuse the [[control|negative controls]] of [RFC-0008](repo:rfcs/0008-negative-controls.md), and three rules keep them from giving a system a result it has not earned, either way.

- **The honest twin.** Each tampered input is checked beside the untouched one, in the same batch. If the untouched proof is not accepted, the trial is void, "so a broken control or a broken run cannot pass for a strong verifier".
- **Three states.** A check is held, failed or undecided, and an undecided check names its cause. It "is never worded as a failure".
- **Reproduce before publishing.** If a verifier accepts a changed input in our adapter, the check reads undecided until the same acceptance is reproduced with the system's own command, outside our code. We tell its publisher first, under the embargo of our [security policy](repo:SECURITY.md). A fault in our adapter is fixed in this repository.

No reviewer sets a state. Each is computed from stored records, which every system page links.

:::note What the checks do not show
None of them attempts a forged proof. The RFC says: "Tests cannot tell a proof from a signature." A system whose proof was only the operator's signature over the commitment, the prompt and the reply, made after checking that the loaded weights match the commitment, would refuse every change we make. The checks show that the changes we made to the model, the prompt and the reply were refused: one weight, one prompt token, three reply positions, three trials each. They do not show that every change would be refused, that the proofs are [[soundness|sound]] or that they hide the weights. Those two properties are read from what each publisher states, and marked as such.
:::

## Fidelity: is the proved model the publisher's?

RFC-0018's motivation says: "A system can quantize a model until proving it is cheap." The Fidelity check asks how far the proved copy has moved from the original.

The score of a reply is the number of leading tokens it shares with the reply of the publisher's original weights to the same prompt. The same score is computed for comparison copies: honest ones (the original run a second time, two mild quantizations) and damaged ones (two harsh quantizations, the model with a quarter of its blocks removed, a smaller model of the same family). The bar is the damaged copy that scores highest among those every honest copy scores above. The check is held when the system's replies score above the bar, by a paired test over the prompts.

The KL divergence from the original is printed beside it and decides nothing, because it "comes from a program that is not the proved computation". The RFC also says where the gate is weak: it "is coarse at 15 replies" on the 8B rung, and "stops gross damage".

## One figure: the multiple of serving

"A proving rate alone says nothing about cost relative to the work being proved", in the words of [RFC-0015](repo:rfcs/0015-reference-rows.md). The ranked figure is therefore a ratio on one model, the [[multiple]]: m, the GPU-seconds of one more proved reply with its generation included, as the mean of three sessions, over b, the GPU-seconds of a reply served at full load on the same kind of GPU. [Where the cost goes](/cost) defines both and draws the session they are taken from.

Each half can be moved without changing a prover, and has a rule against it. Proofs are grouped by when they were released, not by batch. The rule comes from an error of our own: an earlier rule counted more replies than the interval had produced, and proving looked cheaper than it was. For serving, full load is found by raising the concurrency in steps, and a run whose rate is still rising at the last step gives no baseline at all. The stated goal is "a cost figure that a hostile expert cannot move by choosing a window, a batch or a baseline".

Two limits are admitted in [RFC-0015](repo:rfcs/0015-reference-rows.md)'s own list of drawbacks. Serving with an engine's defaults "is not the maximum achievable serving throughput". And the served precision is the publisher's choice, so the ratio "mixes the cost of proving with a precision difference the publisher chose".

:::measured rows
The rows of the board today. A row with too few release groups has no m, and prints its whole-session cost over b instead, labelled as cold sessions.
:::

## Order

A system is placed above another when its multiple is at least 10 % lower and its highest session m is below the other's lowest. A system with a multiple is placed above one without. A system's position is one plus the number of systems placed above it, so systems with the same count share a position. A system that passed is ranked only if its publisher states a security level. The level is printed as stated and no floor is applied, because "tests cannot tell 60 bits from 128, and the levels publishers state are not comparable without recomputation".

## The glyph: stated, then lowered by tests

Passing the checks is the entry gate. The [[glyph]] shows the distance from there to a prover that has all five properties in full: five petals, each green, amber in part, amber in lesser part, red or hollow. Four of them (Unforgeable, Weights hidden, Machine-checked, No third party trusted) are computed from facts a reviewer copies from the publisher's documents at the pinned commit, each with its quote and link; no state is typed. Faithful model is measured against the rung's controls.

- **One fact, one petal.** Whether a bound is proved or conjectured, and its exponents, set Unforgeable; how far a machine-checked proof reaches sets Machine-checked only.
- **Each petal alone.** A petal is decided as if the others were green, and nothing adds them up.

- **Silence is red**, since "a guarantee nobody states is one nobody can rely on". It is drawn as an outline in the red ink. Not read is not silent: a petal whose documents are not read yet is hollow.
- **Tests only lower.** A failed check turns its petals red. A held check never turns one green. RFC-0018 gives no reason. The earlier [RFC-0016](repo:rfcs/0016-glyph-properties-and-states.md) did: a passed control shows that one change was refused, and "reading more into it would turn a test into a certificate".
- **The glyph never moves a position.** The order is cost among the systems that passed.

## What was set by judgement

Some constants have no derivation in the text. They were fixed before the runs and are not argued for:

- the 10 % margin of the order rule;
- the 5 % tolerances of the steady state and of full load;
- three trials per control;
- the 0.05 level of the fidelity test;
- the exponents 128, 100 and 80 that bound Unforgeable's steps (cut points cited from the Ethereum Foundation's zkEVM milestones and NIST SP 800-57, not derived).

If one looks wrong to you, that is an [issue](https://github.com/ai-verification-observatory/inference-proofs/issues) we want.

The same goes for what Level 1 leaves out: closed-weights models, runs made by a lab on its own machines, and any test of soundness. A draft of [Level 2](repo:rfcs/0018-level-1-ladder.md#levels) is published with it "so labs can prepare": a security floor of 100 bits that a third party recomputes from the parameters as run, a KL figure tied to the proved computation that joins the fidelity gate, and a reply chosen after serving.

## Who wrote the rules, and how they changed

The [mandate](/mandate) names who runs this benchmark. RFC-0018 carries a conflict-of-interest note, repeated here because it bears on the rules above. The text "was drafted with an AI agent, Claude, made by Anthropic, which publishes FlashProve". The note names the rules that most affect FlashProve: that generation is counted inside m, how the baseline is chosen, and the order rule's need for a stated security level. FlashProve's documents state one for its Lean verifier and not for the C++ verifier the row runs. The note on the glyph adds that, on Machine-checked, FlashProve is the only listed system that can be above red today, and that the proof-build rule keeps it hollow until a build has been recorded. It also names the readings taken that favour FlashProve: a bound proved for the protocol counts for Unforgeable, which model a commitment names is not graded, and FlashProve's No third party trusted and Machine-checked facts are our readings of its words, marked as such on its page.

A rule changes only through a public [RFC](repo:rfcs/README.md), and a frozen level is meant never to change: a new rule is a new level. The record of Level 1 differs in two ways. The level file was frozen three times on 2026-11-11, each time with a new beacon round: a rung was added, then the serving ladder was extended after a first serving run on the largest model had not reached full load. And two rules were added to the RFC after the last freeze: SE-5, on a refusal by a system's own code, and CO-7, the split of m into generation and proving, written after the first FlashProve session was stored. Neither changes a constant, m or the order rule.

## Reading on

The rules first, then the sources the pages of this track rely on, from the general to the specific.

:::reading
- [RFC-0018: Level 1](repo:rfcs/0018-level-1-ladder.md). The rules this page summarises, with the alternatives considered and the drawbacks its authors see.
- [RFC-0008: Negative controls](repo:rfcs/0008-negative-controls.md). Every tampering test, its expected outcome, the honest twin and the disclosure rule.
- [RFC-0002: Claim card](repo:rfcs/0002-claim-card.md) and [RFC-0015: Reference rows](repo:rfcs/0015-reference-rows.md). How a system's own statement is recorded, and how the serving baseline is run.
- [Proofs, Arguments, and Zero-Knowledge](https://people.cs.georgetown.edu/jthaler/ProofsArgsAndZK.html). Thaler. The textbook, free online. Chapters 2 to 5 cover the random check of a matrix product, the sumcheck protocol and the Fiat-Shamir transformation.
- [17 misconceptions about SNARKs](https://a16zfrontier.com/posts/article/17-misconceptions-about-snarks/). Thaler, 2023. Short corrections of common beliefs, among them what a number of security bits means and why field size matters.
- [zkCNN](https://eprint.iacr.org/2021/673). Liu, Xie and Zhang, 2021. The sumcheck protocol for convolutions that later tensor provers build on.
- [zkLLM](https://arxiv.org/abs/2404.16109). Sun, Li and Zhang, 2024. A sumcheck prover with a lookup argument for attention, on models of up to 13 billion weights. Read it with the repository's note that the released code is an interactive, unaudited proof.
- [zkGPT](https://www.usenix.org/system/files/usenixsecurity25-qu-zkgpt.pdf). Qu and others, 2025. A non-interactive prover for GPT-2, with a table of where its time goes, phase by phase.
- [DeepProve](https://eprint.iacr.org/2026/1112). Gailly and others, 2026. One pass over the prompt and the claimed reply certifies every token. Its cost breakdown is the one quoted on these pages.
- [SASH: the statement](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/docs/statement.md) and [the statement gap](https://github.com/sg-ai-safety-hub/zk-inference-results/blob/11decec3c0b62c707618aab5deb82750b355d202/docs/statement-gap.md). An edge-by-edge account of what one segment proof binds, and a row-by-row account of how the proved statement differs from a served request.
- [FlashProve: what is proved](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/what-is-proved.md) and [known limits](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/known-limits.md). What a machine-checked soundness theorem covers, and what it leaves to tests.
- [VerInf](https://github.com/JamesPetrie/VerInf/blob/7947bb9a6c7ec86ea97927c76370b3920b6269f6/README.md). Petrie, 2026. A different statement: a bound on how much of a floating point reply a committed integer model leaves unexplained.
- [How to Prove False Statements: Practical Attacks on Fiat-Shamir](https://eprint.iacr.org/2025/118). Khovratovich, Rothblum and Soukhanov, 2025. Why the circuit being proved, and who chooses it, is part of a security claim.
- [On the Distribution of the Distances of Random Words](https://eprint.iacr.org/2025/2010). Diamond and Gruen, 2025. One of three papers that disproved the conjecture behind many security levels stated as conjectured.
- [TEE.fail](https://tee.fail/), with [Tinfoil's account](https://tinfoil.sh/blog/2026-02-03-proving-model-identity) of attesting model weights. What trusted hardware can show about a model, and what physical access does to it.
- [DiFR](https://arxiv.org/abs/2511.20621) and [bit-exact recomputation](https://arxiv.org/abs/2606.00279). Karvonen and others, 2025, and Cankaya, 2026. Checking inference by rerunning it: with a tolerance for numerical noise, and without one.
:::

For the wider field there is the [AI Workload Verification Papers](https://github.com/WHodgkins/AI-Verification-Papers) bibliography, built on a reading list by Will Hodgkins and earlier lists by Mauricio Baker and James Petrie.
