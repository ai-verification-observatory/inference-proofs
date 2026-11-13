A cryptographic proof establishes one exact mathematical sentence and nothing beyond it. Two systems can both say they "prove inference" while actually proving very different statements, about different representations of a model, covering different parts of a reply. Before you ask how much a prover costs, you have to ask what its verifier's "accept" actually means. Here we unpack that statement clause by clause using the words of two published provers on our ladder.

## Anatomy of an inference statement

Every cryptographic proof system checks a relation between two sets of inputs: public inputs (which both the prover and verifier see) and a private [[witness]] (which only the prover holds). The [[statement]] is the claim that a valid witness exists satisfying the relation for those public inputs. When a verifier accepts, it confirms that such a witness exists (or, in a proof of knowledge, that the prover actually knows one).

| Component | Visibility | What it represents in inference |
|---|---|---|
| Model identity | public | a cryptographic [[commitment]] to the model weights |
| Input | public | the prompt, represented as a sequence of token IDs |
| Output | public | the reply as token IDs, along with which token positions are checked |
| Execution rules | public | model architecture dimensions, numeric precision, and decoding rule |
| Model parameters | private | the [[weights]] themselves |
| Execution trace | private | every intermediate activation across every layer of the forward pass |

Put together, the relation says: *the weights fixed by this commitment, when evaluated on this prompt under this arithmetic and decoding rule, produce these reply tokens at the checked positions.* Every phrase in that sentence is a concrete engineering choice, and relaxing any one of them weakens what the proof guarantees.

## Two real statements, in their publishers' own words

FlashProve's documentation states that under its exact-match policy, an accepted proof "[is meant to show that each checked token is the committed integer model's top choice at its position, up to the error bound](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/how-it-works.md#L57-L59)". A single FlashProve proof covers one forward pass over a window of tokens.

SASH's prover slices the forward pass into smaller segments: either a single transformer layer applied to a block of token positions, or the language-modelling output head applied to a block. Its [claim card](repo:systems/sash/claim.yaml) records what a passing exit code from its verifier means: every individual segment proof verified, every boundary check between segments "ran and chained on its own axis", and every output position's token is "the prompt's or the previous position's proved argmax".

Both systems prove greedy decoding of a committed model, yet they differ in four critical ways: how much of the forward pass a single proof file covers, how adjacent segments are stitched together, whether the weights are hidden, and how the soundness bound of the overall run is stated. You can only interpret a proving time alongside the exact statement it proved.

## Reading the statement clause by clause

### 1. "The committed model"

A cryptographic commitment locks in a specific array of weights, but it never tells you *whose* weights they are. FlashProve's documentation spells this out candidly:

:::quote https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/known-limits.md#L29-L32 FlashProve, guide/known-limits.md at 9e2bdd8
A yes does not say whose weights they are, that the shipped committer made the commitment, or which real model it is. A provider can commit to any model it likes, a small or degenerate one included, and a scale file within the admitted range can switch off model blocks, up to all of them (worked out by hand).
:::

Something outside the proof system has to connect that commitment digest to a known model, whether through an official release, an audit report, or a shared registry. Just as importantly, the verifier must obtain that commitment from a source the prover cannot overwrite. FlashProve's README warns that the commitment must come from "[a party your user trusts, never from the server being checked or from files sent with the proof](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/README.md#L147-L148)". Our benchmark enforces that rule strictly: the verifier always receives the commitment from the harness's own record of the commit step. (For systems that mix fresh randomness into each commitment so that outsiders cannot recompute the digest from public weights alone, our Model check verifies weight binding using the system's own commitment tool.)

### 2. "Integer model"

A proof system requires arithmetic that produces the exact same bits on every run. Standard GPU floating-point inference does not: because floating-point addition is non-associative, thread scheduling and batching change rounding in the low bits. To make inference deterministic and provable, every prover defines a quantized or fixed-point copy of the model with exact rounding rules, and proves *that copy*. FlashProve converts the entire forward pass to integers; SASH keeps intermediate activations in 16-bit floating point with deterministic rounding rules for non-linearities.

:::quote https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/known-limits.md#L58-L60 FlashProve, guide/known-limits.md at 9e2bdd8
Proofs are about the integer model, quantized and fixed-point. How far its outputs track the original floating-point model's is a measurement, not part of any proof
:::

That external measurement is our Fidelity check. Without it, a system could quantize a model down to junk just to make proving cheap.

### 3. "Each checked token"

A proof only vouches for the token positions it checks. Proving the first generated token after a prompt is a much smaller statement than proving all 512 tokens of a complete reply. (For architectures that prove a full token window in one pass, the proving step itself costs roughly the same either way, while generating the 512 tokens sequentially adds the generation cost.) Similarly, if a verifier does not enforce the reply length, a truncated reply can pass as a valid shorter reply. That is why our benchmark [[request]] requires every system to prove all 512 reply tokens, and why our Reply check tampers with the first, last, and an interior token.

### 4. "Top choice"

The decoding rule is baked into the statement. Under exact-match greedy decoding, every reply token must be the single highest-scoring token (the argmax) of the committed model at that position. An alternative is to prove a relaxed tolerance, allowing any token within the top-k choices or within a score margin of the top token. Relaxing the statement to a tolerance makes it easier to bridge numerical drift between a floating-point serving engine and an integer prover, but it also gives a dishonest prover room to steer outputs among the permitted tokens.

### 5. Stitching segments together

When a prover breaks a forward pass into per-layer or per-block segments, the statement is only as strong as the checks at the seams. SASH's [statement documentation](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/4f41667297430a598165c4a8604258fe37d952ae/docs/statement.md#L138-L141) explains how it links segments: "The residual stream leaving a segment and the keys and values a block writes are committed as their own trees, and `boundary-grid` compares each such root with the root the consuming segment committed for its input." SASH's claim card enumerates sixteen boundary edges, each marked as [[bound]]: twelve internal to a segment, two between adjacent segments, and two at the input embedding and output argmax.

Notably, fourteen of those sixteen checks in SASH have a command-line flag that disables them, prefixed with `--unsound-skip-` so nobody mistakes a skipped check for a full proof. As SASH's [README](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/4f41667297430a598165c4a8604258fe37d952ae/README.md#L76) states: "A run with a skip in effect is a control, never a result." We enforce that same rule across our harness.

### 6. Soundness bounds and what they cover

A [[security level]] always applies to a specific scope. SASH configures each individual segment proof for "[100 conjectured bits](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/4f41667297430a598165c4a8604258fe37d952ae/prover/src/util.rs#L7-L28)", and its documentation states no combined soundness bound for an entire grid of segments. FlashProve states a bound of "[about q/2^124 + 2^-101 after q hash queries](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/what-is-proved.md#L46-L70)" for its formal specification in the Lean proof assistant, while explicitly noting that this theorem is not "claimed for the C++ programs" that users and benchmarks actually run.

Whenever you read a stated security level, check three things: whether it applies to a single component or a full reply, whether it is mathematically proved or conjectured, and whether it covers the paper protocol or the executable verifier binary. Remember too that soundness errors accumulate across segments and batches: as FlashProve's [claim card](repo:systems/flashprove/claim.yaml) quotes, checking a batch of N proofs together "cost N times that error".

### 7. What remains outside the statement (the residual)

Even when every check holds, every statement leaves room for things a dishonest operator can still do without invalidating the proof. On our claim cards, we call this the [[residual]]. For example, FlashProve's documentation notes: "[A proof names no client or time.](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/known-limits.md#L51-L55)" For a relying party, reading the residual is just as important as reading the positive statement, because the residual is the exact list of gaps your surrounding system has to close by other means.

## How we record statements on claim cards

We record all of these details for each system in a structured [[claim card]]: the mathematical relation, the security level and its assumptions, the list of bound edges, and the residual. Every field is copied from the publisher's own documentation at the pinned commit, with a direct link to the source lines. Where the publisher's documentation does not address a question, we write "not stated" (recording silence rather than assuming the property fails). Each card also tracks whether the upstream maintainers have reviewed our summary; as of 2026-11-12, neither card has been reviewed by upstream.

## How our benchmark handles differing statements

No benchmark can magically make two different mathematical statements identical, so we do three concrete things instead:

- **We standardise the workload.** Every system on a model rung is given the exact same [[request]]: one 512-token prompt, one 512-token reply, greedy decoding, with every reply token covered.
- **We empirically test input bindings.** Modifying the committed weights, the prompt, or the reply must cause the verifier to reject the proof. Our [checks page](/checks) defines each test, and you can [explore them interactively](/proof-of-inference#exp-tamper).
- **We surface what cannot be tested empirically.** Properties like mathematical soundness, weight hiding, formal verification reach, and setup trust are displayed in the five-petal [[glyph]] directly from the publisher's documented statements.

Next up are two bridging primers: [Inference, for cryptographers](/inference) introduces transformer serving for readers who already know proof systems, while [Proof systems, for ML engineers](/proof-systems) introduces algebraic proofs for readers who already know machine learning.
