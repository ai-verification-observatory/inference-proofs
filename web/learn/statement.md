A proof proves one sentence and nothing more. Two systems can both *prove inference* and prove different sentences, about different models, covering different parts of a reply. So before asking what a prover costs, ask what its verifier's yes means. This page takes that sentence apart, using two systems' own words.

## The parts of the sentence

A proof system is built around a relation between two things: a public [[statement]], which the verifier is given, and a private [[witness]], which only the prover holds. The verifier's yes means that a witness exists for which the relation holds. Some systems state more: that the prover knows such a witness. Read which one a system states.

| Part | Public or private | For inference |
|---|---|---|
| The model's identity | public | a [[commitment]] to the weights |
| The input | public | the prompt, as token ids |
| The output | public | the reply, as token ids, and which of its positions are checked |
| The rules | public | the architecture and its sizes, the arithmetic, the decoding rule |
| The model itself | private | the [[weights]] |
| The work | private | every intermediate value of the forward pass |

The relation then reads: *the committed weights, run on this prompt with this arithmetic and this decoding rule, give this reply at the checked positions.* Each clause of that sentence is a design decision, and each can be made in a way that proves less than a reader assumes.

## Two statements, in their publishers' words

FlashProve's documentation says that, under its exact-match policy, a yes from its verifier ["is meant to show that each checked token is the committed integer model's top choice at its position, up to the error bound"](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/how-it-works.md#L57-L59). One proof covers one pass over a window of tokens.

SASH's prover cuts the computation into segments: one layer applied to one block of positions, or the output head applied to one block. Its [claim card](repo:systems/sash/claim.yaml) records what its verifier's exit code stands for: every segment proof verifies, every link between segments "ran and chained on its own axis", and every position's token is "the prompt's or the previous position's proved argmax".

Both are statements about a committed model decoding greedily. They differ in almost everything else: what one proof covers, how the pieces are joined, what is hidden, and how the strength of the whole is stated. A proving time can be read only beside the sentence it was obtained for.

## Reading it clause by clause

### "The committed model"

A commitment fixes a set of weights. It does not say whose they are. FlashProve's list of known limits says:

:::quote https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/known-limits.md#L29-L32 FlashProve, guide/known-limits.md at 9e2bdd8
A yes does not say whose weights they are, that the shipped committer made the commitment, or which real model it is. A provider can commit to any model it likes, a small or degenerate one included, and a scale file within the admitted range can switch off model blocks, up to all of them (worked out by hand).
:::

Something outside the proof has to tie the commitment to a known model: a public register, an evaluation, a contract. The commitment must also reach the verifier by a path the prover does not control. FlashProve's README asks for it to come from ["a party your user trusts, never from the server being checked or from files sent with the proof"](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/README.md#L147-L148). This benchmark does the same: the verifier is always given the commitment from our own record. Some systems draw a fresh secret each time they commit, so nobody can recompute such a commitment from public weights. For those, our Model check shows the weight change with the system's own digest tool.

### "Integer model"

A proof needs arithmetic that every run reproduces bit for bit. The floating point of a serving engine does not give that: its results depend on the order of operations. So the model a system proves is a quantized copy with exactly specified arithmetic, and the statement is about the copy. FlashProve's copy is in integers throughout. SASH's keeps steps in 16-bit floating point with a fixed rounding rule for its non-linear operations.

:::quote https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/known-limits.md#L58-L60 FlashProve, guide/known-limits.md at 9e2bdd8
Proofs are about the integer model, quantized and fixed-point. How far its outputs track the original floating-point model's is a measurement, not part of any proof
:::

That measurement is our Fidelity check. A system could otherwise make proving cheap by proving a model that has been quantized into something else.

### "Each checked token"

A proof covers the positions it names. A proof of the next token after a prompt and a proof of all 512 tokens of a reply are different statements. For a design that proves a whole window in one pass, the proving costs the same and the difference is the cost of generating the reply. And a reply cut short can verify as a shorter reply. This is why the [[request]] of this benchmark requires every reply token to be checked, and why the Reply check tampers with the first, the last and an interior token.

### "Top choice"

The decoding rule is part of the statement. Under exact match, each reply token must be the highest-scoring token of the committed model at its position. The alternative is a tolerance: the token must be among the top few, or within a margin of the top score. A tolerance is easier to meet when the proved arithmetic differs from the arithmetic that produced the reply, and it is a weaker statement, because it leaves the prover a choice.

### The joins

When a computation is proved in pieces, the statement has to cover the seams. SASH's [documentation](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/docs/statement.md) says how its pieces are tied: "The residual stream leaving a segment and the keys and values a block writes are committed as their own trees, and `boundary-grid` compares each such root with the root the consuming segment committed for its input." Its claim card lists sixteen edges, each marked as [[bound]]: twelve inside a segment, two between segments, and two at the ends, where the embedding row enters and the token is chosen.

Fourteen of the sixteen have a switch that turns their check off, named `--unsound-skip-`: the publisher's own label for a proof that would say less. Its [README](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/README.md) adds: "A run with a skip in effect is a control, never a result." This benchmark holds to the same rule.

### How strong, and for what

A [[security level]] belongs to a specific object. SASH's code sets the parameters of each segment proof for ["100 conjectured bits"](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/prover/src/util.rs#L7-L28), and its claim card records no stated level for a whole grid of segments. FlashProve states a bound of ["about q/2^124 + 2^-101 after q hash queries"](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/what-is-proved.md#L46-L70) for a verifier written in the Lean proof assistant, and adds that this figure is not "claimed for the C++ programs", which are the ones this benchmark runs.

Read every stated level for three things: per piece or for the whole, proven or conjectured, for the protocol or for the program. Errors also add. A level per piece is not the level of the whole, and a level per proof is not the level of a day's proofs: FlashProve's [claim card](repo:systems/flashprove/claim.yaml) records its publisher's sentence that N proofs handed in at once "cost N times that error".

### What is left over

Every statement leaves something a dishonest prover can still do. A claim card calls this the [[residual]]. FlashProve's list includes: ["A proof names no client or time."](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/guide/known-limits.md#L51-L55) A relying party needs the residual as much as the statement, since it is the list of things to cover by other means.

## The claim card

All of the above is recorded per system in a [[claim card]]: the relation, the security notion and level, the assumptions, what is bound, the residual. Every field is copied from the system's own documents at a pinned commit, with a link to the line. Where the documents are silent the card reads "not stated", which records silence and not the absence of a property. Each card records whether the system's maintainers have reviewed it. At the time of writing, neither of the two cards has been. A card copies or cites: where it sums up several lines of a document in a sentence of its own, the link shows the lines.

## What the benchmark does with it

It cannot make two different sentences comparable. It does three smaller things.

- **It fixes the request**, so that every system is asked for the same coverage: one prompt, one reply, every token checked.
- **It tests the bindings it can test.** Changing the model, the prompt or the reply must make the verifier refuse. The [checks page](/checks) defines each test, and a page of the policy track lets you [try them](/proof-of-inference#exp-tamper).
- **It prints what it cannot test**, as stated: the security level, what is hidden, what must be trusted. Those are the petals of the [[glyph]] that are read from documents, not taken from our checks.

The next two pages are introductions. [Inference, for cryptographers](/inference) is for readers who know proof systems. [Proof systems, for ML engineers](/proof-systems) is for readers who know models.
