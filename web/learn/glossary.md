The terms these pages use, in plain words, with the precise meaning where the two differ. The benchmark's own vocabulary (level, rung, check, multiple) keeps the meaning its [specification glossary](repo:docs/spec/10-glossary.md) gives it.

### Adapter

The thin wrapper through which this benchmark runs a system. It translates the benchmark's request into the system's own commands and changes nothing in the system.

On this site: one container image per system, built at a full commit hash, with no patch and no option the system's documentation does not name.

### Attestation

A signed statement by a piece of hardware, or by a party, that something is the case: for example a chip reporting which software it started. An attested claim is as strong as the trust placed in whoever signs.

We say *attested* for this and never for a cryptographic proof. See [Three ways to check](/three-ways).

### Bound

Said of a part of a computation that the verifier's acceptance constrains. If the prompt is bound, a proof made for one prompt is refused for another.

A statement lists what is bound: the weights to the commitment, the prompt and the reply to the proof, each layer's output to the next layer's input. What is not bound, a dishonest prover is free to change.

### Check

One of the six tests this benchmark runs on a system before ranking it: Run, Model, Prompt, Reply, No weight file, Fidelity. Each ends held, failed or undecided, and an undecided check names its cause.

The [checks page](/checks) defines each one. [How we compare](/method) gives the reasons.

### Claim card

The written record, for one system in one configuration, of what its accepted proofs establish: the statement, the security level and its assumptions, what is bound, and what a dishonest prover could still do.

Every field is copied from the system's own documents at a pinned commit, with a link, or reads "not stated".

### Commitment

A short value computed from a model's weights that fixes them. Publishing it does not publish the weights. Whether it leaks anything about them depends on the system. Once it is published, every later proof is checked against it. It does not watch what the operator runs.

Precisely: the value a system's commit step produces. It is binding (nobody can feasibly find two models with the same commitment) and, in some systems, hiding (it reveals nothing about the weights). On this site the verifier is given the commitment from our own record of the commit step, never from files sent with a proof.

### Control

A deliberate tampering with what a verifier or a prover is given, to see whether the change is refused. Change one weight, one prompt token or one reply token, and a working verifier must say no.

Also called a negative control. Each one is checked beside its [[honest twin]].

### Fidelity

How closely the model a system proves follows the model its publisher released. A prover may quantize a model to make proving cheaper, and fidelity asks what that changed.

On this site: a check that compares a system's replies with those of the original weights, against copies damaged on purpose.

### Field

A set of numbers in which addition, subtraction, multiplication and division are all exact. Proof systems use the whole numbers below a prime, with every result reduced modulo that prime.

The random checks of a proof system need exact arithmetic, which is why provers do not compute in floating point. The size of the field sets how often such a check can miss an error.

### Glyph

The five-petal figure drawn for each system this benchmark has run. Each petal is one of five properties a prover can have in full: Unforgeable, Weights hidden, Faithful model, Any model, Only the verifier trusted.

A petal is green, amber, red or hollow. Three petals are read from what the publisher states, and two come from our checks. The glyph never moves a system's position.

### Greedy decoding

Choosing, at every step of a reply, the token the model scores highest. With exact arithmetic and a fixed rule for ties, the same model on the same prompt then always gives the same reply, which is what lets a reply be checked token by token. In floating point on a GPU this is not guaranteed.

### Honest twin

The untouched proof that is checked next to a tampered one. If the verifier does not accept the twin, the test is void: a refusal means something only when the same verifier accepts the real thing.

### Inference

Running a trained model on an input to get an output. For a language model: turning a prompt into a reply, one token at a time.

### Ladder

The [front page](/) of this site: one section per model, with the systems run on it and what each cost. A model on it is a [[rung]].

### Level

A frozen definition of the benchmark: the models, the request, the checks, the order rule and every constant. A level never changes once frozen. A new rule is a new level.

Level 1 is defined in [RFC-0018](repo:rfcs/0018-level-1-ladder.md).

### Lookup argument

A way to prove that every value in a long list appears in a fixed public table, without checking the values one by one. Provers use it for the steps of a model that are not additions or multiplications: a rounding, a comparison, an activation function.

### Multilinear extension

The one polynomial that agrees with a list of numbers at the corners of a cube and is linear in each of its variables. It turns a table of data, such as a matrix of weights, into an object that a single random evaluation can vouch for.

### Multiple

The cost of a proved reply as a multiple of the cost of serving the same reply without a proof, on one model. It is the figure this benchmark ranks by.

Precisely: steady GPU-seconds per further proved reply, over the serving baseline's GPU-seconds per reply at full load. See [Where the cost goes](/cost).

### Operator

Whoever runs the model and answers requests: a company serving an API, a lab, the company behind a state's declared data centre. In a proof of inference the operator is the [[prover]].

### Passed

Said of a system on a model when all six checks are held there. It is never said of a model.

### Polynomial commitment

A [[commitment]] to a polynomial that can later be opened at one point: the prover shows the polynomial's value there, and the verifier checks it against the commitment alone. This is how a verifier works with weights it never receives.

### Prompt

The input of a request: the tokens the model is given.

### Proof of inference

A file, or a set of files, that lets a program check that a given reply is what a given model gives for a given prompt, without running the model. In some systems the check also reveals nothing about the model's weights.

Precisely: on this site, the set of files one verify call checks for one request. What an accepted proof establishes is the system's [[statement]], and it holds under the assumptions the system names.

### Proved

Said of a statement that a [[soundness|sound]] verifier's acceptance establishes, under stated assumptions. A proof of inference proves that a reply is what the committed model gives for a prompt. It does not prove that the reply was served, or that the model is safe, and we never use the word that way.

### Prover

The program that produces a proof, and by extension whoever runs it. The prover holds everything: the weights, the prompt, the reply. It does far more work than the [[verifier]].

### Quantization

Storing a model's weights, and sometimes its intermediate values, with fewer bits: 8-bit or 4-bit integers in place of 16-bit floating point. It makes a model cheaper to run and to prove, and changes its replies a little or a lot. A proof of inference is about a quantized copy, computed in exactly specified arithmetic.

### Random oracle

An idealised hash function: one that answers every new question with a fresh random value. Many proof systems are shown sound on the assumption that their hash function behaves this way.

### Recomputation

Checking a result by running the computation again. It needs the weights and the compute, and it needs the computation to give the same answer twice.

Checking only a random share of the work is *sampled* recomputation: the guarantee is then statistical. See [Three ways to check](/three-ways).

### Relying party

Whoever acts on a proof: a customer, an auditor, a regulator, an inspectorate. The relying party runs the [[verifier]], or trusts someone who does, and has to know what an accepted proof does and does not establish.

### Reply

The output of a request: the tokens the model produces.

### Request

One prompt and the reply the verifier is given for it. On this site every system gets the same request: 512 prompt tokens and a 512-token reply, decoded greedily, every reply token checked.

### Residual

What a dishonest prover can still do while passing verification. A claim card lists it, because no statement covers everything.

### Rung

One open-weights model of a level, with its serving baseline. Systems are ranked inside a rung and never across rungs.

### Sampled

Said of a guarantee that comes from checking a random part of the work: some of the replies, or some steps of one computation. It is statistical: it bounds how much cheating could go unnoticed, and it says nothing certain about any single reply.

### Security level

How hard it is to get a false statement accepted, as a number of bits. At 100 bits, one attempt succeeds with probability about 1 in 2^100, and a dishonest prover needs about 2^100 attempts.

It is stated by a system's publisher, as proven or as conjectured, and for a protocol or for the code that runs. This benchmark prints it as stated and does not test it.

### Serving baseline

What it costs to answer the request with no proof: the publisher's own release of the model, served by a standard engine at full load. It is the denominator of the [[multiple]].

### Soundness

The property that a false statement is not accepted. A verifier is sound when no prover with feasible computing power, however dishonest, can make it accept a false statement, except with negligible probability.

Soundness is argued mathematically, under assumptions. Running a verifier cannot establish it. See [[security level]].

### Statement

The sentence a proof proves. For inference: *the model fixed by this commitment, on this prompt, gives this reply under this decoding rule.* Everything a proof is worth depends on what its statement says and leaves out.

See [The statement](/statement).

### Sumcheck

A protocol by which a prover convinces a verifier that a very large sum has a given value, while the verifier does a small amount of work. Most systems that prove matrix products are built on it.

See [Proving a forward pass](/forward-pass).

### Token

The unit of text a language model reads and writes: a word, a piece of a word or a punctuation mark, as a number.

### Trusted execution environment

A processor feature designed to run code in an enclave the machine's owner cannot read or alter, and to sign a report of what was started. Often shortened to TEE. Its guarantee is an [[attestation]] and rests on the chip's maker and on the chip not being physically attacked.

### Trusted setup

Public parameters that some proof systems need, generated from secret numbers that must then be destroyed. Whoever kept the secrets could forge proofs. A system with no such step is called transparent.

### Verification

Checking a claim against evidence that holds up even if the claimant is not trusted. The word has four senses that these pages keep apart: checking a claim, finding that a party kept a rule, formal verification of software, and running the program that checks a proof. See [Why verify](/why-verify).

### Verifier

The program that checks a proof and answers accept or refuse. It needs the commitment, with the public configuration it was made under, the prompt, the reply and the proof. It does not need the weights, and for the systems run here it needs no GPU.

### Weights

The numbers that make up a trained model: billions of them for the models on this site. They are what an operator may want to keep secret, and what a [[commitment]] fixes.

### Witness

What the prover knows and the verifier does not. In a proof of inference the witness is the weights, with the intermediate values of the computation.

### Zero knowledge

The property that a proof reveals nothing beyond the truth of its statement. A verifier of a zero-knowledge proof of inference learns that the reply is what the committed model gives, and nothing else about the weights.

What stays public is still public: the model's size and shape, the prompt and the reply. Zero knowledge is a property separate from [[soundness]], and has to hold for the program that runs, not only for the protocol on paper.
