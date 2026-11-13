Benchmark-specific terms (level, rung, check, multiple) follow the normative definitions in the [specification glossary](repo:docs/spec/10-glossary.md).

### Adapter

The thin wrapper through which our harness runs a prover or verifier. It translates the benchmark's standard invocation into the system's own CLI commands without modifying the underlying tool.

On this site: one container image per system, built at a pinned upstream commit hash with no source patches and no undocumented flags.

### Attestation

A signed statement from a piece of hardware or an organisation declaring that a specific condition holds, such as a server processor reporting the hash of the software binary it booted. An attestation is only as trustworthy as the party or hardware signing it.

We use *attested* strictly for signed hardware or institutional reports, never for a mathematical proof. See [Three ways to check](/three-ways).

### Bound

Locked into the statement that a verifier checks, so that changing the value causes verification to fail. If the prompt is bound, a proof generated for one prompt will be rejected if verified against another.

A system's claim card lists everything its proofs bind: the weights to the public commitment, the prompt and reply to the proof, and each layer's output to the next layer's input. Anything left unbound can be changed by a dishonest prover without failing verification.

### Check

One of the six empirical tests a system must pass in our harness before it receives a ranked position on a model: Run, Model, Prompt, Reply, Verify without weights, and Fidelity. Every check finishes as held, failed, or undecided, and an undecided check always states its cause.

The [checks page](/checks) defines each check; each system's page reports its outcomes, and [How we compare](/method) explains how they work.

### Claim card

The structured record, for one system in one configuration, of what its accepted proofs establish: the mathematical statement proved, the stated security level and assumptions, what is bound, and what a dishonest prover could still alter.

Every entry is quoted and linked from the system's own documentation at the pinned commit, or marked "not stated" where the documentation is silent.

### Commitment

A compact cryptographic digest computed from a model's weights that locks them to a single fixed copy. Publishing the commitment does not reveal the weights themselves, though whether it leaks subtle statistical information depends on the commitment scheme. Once published, every future proof is verified against that same commitment. By itself, a commitment does not monitor what the operator actually runs on its servers.

More precisely: the output produced by a system's commit step. A commitment scheme is binding (nobody can feasibly find two different weight sets that produce the same commitment) and, in zero-knowledge systems, hiding (the commitment reveals nothing about the weights beyond public dimensions). In our harness, the verifier always receives the commitment recorded during our own commit step, never a file supplied alongside the proof.

### Control

A deliberate perturbation of the weights, prompt, or reply passed to a verifier to confirm that the change is rejected. Flipping one weight, one prompt token, or one reply token must cause a working verifier to refuse the proof.

Also called a negative control. Every control trial is verified alongside its untouched [[honest twin]].

### Fidelity

How closely the quantized or integer model that a system proves matches the original model released by its publisher. Provers convert models into finite-field or integer arithmetic to make proving feasible, and the fidelity check measures how much the model's outputs shifted as a result.

On this site: a gate that compares a system's greedy replies against the original weights' replies, benchmarked against deliberately degraded copies of the model.

### Field

A finite set of numbers where addition, subtraction, multiplication, and division are all exact and wrap around a prime modulus. Cryptographic proof systems operate over finite fields rather than floating-point numbers because their algebraic checks require exact arithmetic with no rounding drift.

The size of the field determines how unlikely a random check is to miss a forged step.

### Glyph

The five-petal summary figure drawn beside every row on the ladder. Each petal represents one of five verification properties a system can hold: Unforgeable, Weights hidden, Faithful model, Machine-checked, and No third party trusted.

A petal is drawn green (held in full), amber (in part), amber with its arm's end cut off (in lesser part), solid red with its name struck (not held, or a check failed), as a red outline (the publisher's documentation is silent) or as a grey outline (undecided). Four petals are derived from documented facts at the pinned commit and can be lowered if a check fails; Faithful model is set by our fidelity test. The glyph never changes a system's rank, and its five petals are never combined into a single score.

### Greedy decoding

Selecting the single highest-scoring token at every generation step rather than sampling randomly. Under exact arithmetic and a deterministic tie-breaking rule, greedy decoding guarantees that the same model on the same prompt always produces the exact same token sequence, allowing a verifier to check the reply token for token. Standard floating-point execution on GPUs does not guarantee that determinism across runs.

### Honest twin

The unmodified proof verified right alongside a tampered control proof in the same batch. If the verifier fails to accept the honest twin, the entire control trial is void, ensuring that a broken environment or crashing verifier is never mistaken for a successful refusal.

### Inference

Running a trained model forward on an input to produce an output. For a language model, inference means turning a prompt into a reply one token at a time.

### Ladder

The [front page](/) of this benchmark: one section per open-weights model, listing the systems tested on that model and what each cost. Each model section is a [[rung]].

### Level

A frozen edition of the benchmark specification fixing the models, the request shape, the six checks, the ordering rule, and all numerical constants. Once frozen, a level is meant to stay unchanged so that substantive rule changes wait for the next level. [How we compare](/method) documents where Level 1 departed from that rule.

Level 1 is specified in [RFC-0018](repo:rfcs/0018-level-1-ladder.md).

### Lookup argument

A cryptographic protocol for proving that every entry in a long list of witness values exists in a fixed public reference table, at a cost far lower than checking each entry individually. Inference provers rely on lookup arguments for operations that cannot be expressed cleanly as low-degree polynomials, such as GELU or SiLU activations, softmax exponentials, reciprocal square roots, and bit-width rounding.

### Multilinear extension

The unique polynomial that matches a multi-dimensional array of numbers at every corner of the boolean hypercube and is linear in each variable separately. Extending a weight matrix or activation tensor into a multilinear polynomial lets a verifier check a claim about the entire table by evaluating the polynomial at a single random point.

### Multiple

The GPU cost of a proved reply expressed as a ratio of the GPU cost of serving the same reply without a proof on the same model. It is the single figure used to order passing systems within a rung, printed on the ladder as Cost vs serving.

Specifically: steady-state GPU-seconds per additional proved reply (including generation) divided by full-load serving GPU-seconds per reply on the same hardware. A system with no steady state is given its whole sessions' GPU time per reply over the same baseline instead, labelled whole sessions. See [Where the cost goes](/cost).

### Operator

The party that hosts the model and serves requests, whether a commercial API provider, an AI lab, or the operator of a declared sovereign compute cluster. In a proof of inference, the operator runs the [[prover]].

### Passed

A system's status on a specific model rung once all six benchmark checks are held. Systems pass on a rung; models themselves do not pass or fail.

### Petal

One of the five arms of the [[glyph]], corresponding to a single verification property that a system can hold in full, in part, in lesser part, or not at all.

### Polynomial commitment

A cryptographic [[commitment]] to a polynomial that allows the prover to later reveal the polynomial's value at a random point chosen by the verifier, accompanied by a short proof that the revealed value is consistent with the initial commitment. Polynomial commitments allow a verifier to check algebraic claims about billions of model weights without ever downloading the weights.

### Position

A system's numerical rank among the systems that passed all six checks on a single model rung, defined as one plus the number of systems placed strictly above it. Only a passing system whose publisher states a security level in bits receives a position.

### Prompt

The input tokens sent to a language model in a request.

### Proof of inference

A cryptographic proof file (or bundle of files) that allows a verifier program to confirm that a specific reply is the output of a committed model on a specific prompt, without re-running the model. When the proof system is zero-knowledge, verification also reveals nothing about the model's weights beyond what the statement makes public.

In our harness: the set of proof files verified by a single verifier call for one request. An accepted proof establishes the system's documented [[statement]] under its stated cryptographic assumptions.

### Proved

Established by the acceptance of a [[soundness|sound]] verifier under stated mathematical assumptions. A proof of inference proves that a reply matches what the committed model produces on a prompt; it does not prove which weights ran on the server in real time, nor does it prove that a model is safe, and we never use the word in that loose sense.

### Prover

The program that generates a cryptographic proof, and by extension the operator running it. The prover holds the secret model weights, records the intermediate activations, and performs the heavy computational work that makes verification cheap for the [[verifier]].

### Publisher

The team or organisation that releases a proof system and its documentation, or that releases an open-weights model. Wherever both appear in the same context, our pages specify whether we mean the system publisher or the model publisher.

### Quantization

Representing a model's weights and activations with lower-precision integers (such as 8-bit or 4-bit integers) instead of 16-bit or 32-bit floating-point numbers. Quantization reduces memory traffic and makes finite-field proving practical, at the cost of shifting the model's token predictions slightly or substantially. Every inference prover on this board proves a quantized or integer-converted copy of the model.

### Random oracle

An idealised mathematical model of a cryptographic hash function in which every distinct input produces a uniformly random output. Many non-interactive proof systems prove their soundness in the random oracle model before instantiating the oracle with a concrete hash function like SHA-256 or Poseidon.

### Recomputation

Verifying a claimed output by executing the computation a second time and comparing the results. Recomputation requires full access to the model weights, enough hardware to run them, and deterministic arithmetic so two honest runs agree.

Re-running only a randomly chosen subset of requests or layers is called *sampled* recomputation and provides a statistical guarantee. See [Three ways to check](/three-ways).

### Relying party

Whoever acts on the result of verification: an API customer, an external auditor, a regulator, or an international treaty inspectorate. The relying party runs the [[verifier]] itself (or delegates verification to someone it trusts) and needs to understand both what an accepted proof guarantees and what it leaves unchecked.

### Reply

The sequence of output tokens generated by a model in response to a prompt.

### Request

A single prompt paired with the reply presented to the verifier. Across Level 1, every system receives the same request shape: a 512-token prompt and a 512-token greedy reply, with all 512 reply tokens verified.

### Residual

What a dishonest prover could still manipulate or substitute while still producing a proof that the verifier accepts. Every claim card explicitly lists the system's residual gaps because no statement covers the entire physical world.

### Row

One system's entry on one model [[rung]] of the [[ladder]], showing its check standing, its five-petal glyph, and its cost and verification figures.

### Rung

One open-weights model in a benchmark level, paired with its full-load serving baseline. Systems are compared and ranked strictly inside a single rung, never across different rungs.

### Sampled

Derived from checking a randomly selected fraction of the work, such as auditing a random subset of replies or checking random positions inside a trace. A sampled check provides a statistical guarantee: it bounds how much systematic cheating can go undetected over time, without certifying any single uninspected reply.

### Security level

A quantitative measure, expressed in bits, of how much computation a dishonest prover would need to make a verifier accept a false statement. At a 100-bit security level, a single forgery attempt succeeds with probability at most 1 in 2^100, requiring roughly 2^100 operations to forge a proof.

Each publisher states its security level as either mathematically proven or conjectured, and either for an abstract protocol on paper or for the concrete implementation that runs. Level 1 records what the publisher states at the pinned commit and does not recompute or test the bound.

### Serving baseline

The GPU cost of answering the benchmark request without a proof, measured using the model publisher's released weights on a standard serving engine at full load. It is the denominator of the cost [[multiple]].

### Session

One complete benchmark run of a system starting from a cold state: committing to the model weights, then generating and proving a fixed sequence of requests. A ranked position requires three sessions.

### Soundness

The property that a verifier rejects false statements. A proof system is computationally sound if no prover with feasible computing resources can make the verifier accept a false claim except with negligible probability.

Soundness is a mathematical property established by proof under explicit cryptographic assumptions; empirical testing can refute soundness by finding a bug, but cannot establish it. See [[security level]].

### Statement

The exact proposition that an accepted proof certifies. For an inference prover, the statement takes the form: *the model fixed by this commitment, run on this prompt under this decoding rule, produces this reply.* What a proof is worth in practice depends on every detail its statement binds and every detail it leaves out.

See [The statement](/statement).

### Sumcheck

An interactive proof protocol (later made non-interactive via Fiat-Shamir) that lets a prover convince a verifier of the sum of a polynomial over exponentially many inputs while the verifier performs only logarithmic work and evaluates the polynomial at a single random point. It is the workhorse behind most tensor and linear-algebra provers.

See [Proving a forward pass](/forward-pass).

### Token

The basic unit of text processed by a language model: a word, sub-word fragment, or character represented as an integer ID from the model's vocabulary.

### Trusted execution environment

A hardware enclave inside a CPU or GPU designed to isolate running code and memory from the machine's owner and operating system, while signing cryptographic reports of the binary loaded inside it. Commonly abbreviated TEE. Its security is an [[attestation]] guarantee that depends on the chip manufacturer's keys and on physical protection of the hardware against bus-probing attacks.

### Trusted setup

A one-time ceremony required by some polynomial commitment schemes to generate public parameters from secret random numbers that must subsequently be destroyed ("toxic waste"). Anyone who retains or reconstructs those secret numbers can forge proofs undetected. Proof systems that require no trusted setup are called transparent.

### Verification

Confirming a claim against evidence that holds up even when the party making the claim has an incentive to cheat. Across this site we distinguish four uses of the word: checking a claim in general, verifying treaty or regulatory compliance, formal mathematical verification of software, and running a cryptographic [[verifier]] program. See [Why verify](/why-verify).

### Verifier

The lightweight program that inspects a cryptographic proof and outputs accept or refuse. It takes as input the weight commitment, the public model configuration, the prompt, the reply, and the proof bytes. It never needs the secret model weights, and for every system run on this benchmark it runs on an ordinary CPU with no GPU attached.

### Weights

The learned numerical parameters that define a trained neural network, numbering in the billions for modern language models. They are the proprietary asset an operator may wish to keep confidential, and the data that a cryptographic [[commitment]] locks down.

### Witness

All the private inputs and intermediate values that the prover knows and uses to construct a proof, which the verifier does not see directly. In a proof of inference, the witness comprises the model weights together with the layer-by-layer activations of the forward pass.

### Zero knowledge

The cryptographic property that a proof reveals nothing whatsoever beyond the truth of the statement being proved. When a proof of inference is zero-knowledge, a verifier learns that the reply came from the committed model on the given prompt, and learns nothing else about the secret weights.

Anything included in the public statement remains visible to the verifier, including the model's architecture dimensions, the prompt, and the reply. Zero knowledge is completely separate from [[soundness]], and must hold for the actual code and transcript emitted by the prover, not merely for an idealised protocol on paper.
