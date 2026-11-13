As a machine learning engineer, you already use lightweight spot-checks in place of expensive computations: checking a SHA-256 hash instead of comparing two multi-gigabyte weight files byte by byte, or checking finite-difference gradients at a few coordinates instead of differentiating a loss by hand. Cryptographic proof systems push that idea to its mathematical limit. In most modern proof systems, checking a proof takes a tiny fraction of the compute needed to generate it, the verifier never sees the model weights, and at a 100-bit security level a false result slips through less than once in 2^100 attempts.

Everything the provers on our ladder do is built from five core ideas. Let's work through the first one by hand and then see how the other four fit on top.

## 1. A random spot-check can verify a matrix product

Suppose someone hands you three n × n matrices A, B, and C, and claims that C = A·B. Multiplying A by B yourself to check their claim takes O(n^3) operations. [Freivalds' algorithm](https://en.wikipedia.org/wiki/Freivalds%27_algorithm) checks the claim in O(n^2) operations instead: draw a random vector r, compute B·r, then A·(B·r), and check whether that equals C·r. Because each step multiplies a matrix by a vector, you do three matrix-vector products and never multiply two matrices together.

If C truly equals A·B, then A·(B·r) and C·r will match for every possible r. If C has even a single wrong entry, the two sides will disagree for at least half of all binary vectors r ∈ {0, 1}^n, and for almost every vector drawn from a larger finite field.

:::explore random-check
Checking A·B against a claimed product C where one entry has been altered. When r is drawn from {0, 1}, roughly half of all draws hit the corrupted column and reject C. When r is drawn from {0, ..., 96} modulo 97, a draw misses the error only when it happens to place a 0 on the corrupted column (1 time in 97).
:::

Two rules from this tiny example apply to every proof system on our site:

- **The random challenge must be drawn after the claim is fixed.** If a cheating prover knew r ahead of time, it could easily cook up a false matrix C that happens to satisfy A·(B·r) = C·r for that specific vector.
- **Drawing challenges from a larger field drives down the false-pass rate.** With random bits, a single check misses a lie at most 1 time in 2; modulo 97, at most 1 time in 97; in a 64-bit prime field, less than 1 time in 10^18. Crucially, the arithmetic must take place in a mathematical [[field]] rather than wrapping 64-bit integers (`uint64`), because modulo 2^64 an error divisible by 2^63 is missed by every even challenge.

Of course, Freivalds' algorithm by itself is not yet a proof of inference: the verifier still has to hold all three matrices and do work proportional to their size. The next four ideas eliminate both requirements.

## 2. Polynomials turn a local lie into a global difference

Take any list of n numbers, such as a row of model weights or a vector of activations. We can view that list as a function on the corners of a boolean hypercube `{0, 1}^(log n)` and extend it to a unique [[multilinear extension]]: a polynomial in `log n` variables that is linear in each variable separately and can be evaluated at any point over a finite field, not just at `{0, 1}`.

Why turn a table of numbers into a polynomial? Because two distinct polynomials of low degree almost never agree! In one variable, two distinct degree-d polynomials can cross at most d times. In multiple variables, the [Schwartz-Zippel lemma](https://doi.org/10.1145/322217.322225) guarantees that two distinct polynomials of total degree d agree on at most a fraction `d / |S|` of points drawn from a set `S`. For a multilinear polynomial in `log n` variables, `d = log n`. If a cheating prover alters even a single number in its table, the resulting polynomial changes almost everywhere across the field, and evaluating it at a single random point `(r_1, ..., r_{log n})` catches the discrepancy with probability at least `1 - (log n) / |S|`. Unlike sampling a single row from a database, evaluating the multilinear extension at a random field point mixes every entry of the original table together.

For the Schwartz-Zippel lemma to hold, arithmetic must be exact, with no floating-point rounding or silent overflow. That is why provers work over a finite [[field]] (integers modulo a prime `p`). Some GPU provers do their bulk arithmetic in a small 31-bit or 64-bit prime field for speed, and then draw their random challenges `r` from a 128-bit extension field so `|S|` is huge.

## 3. Polynomial commitments let the verifier check values without holding the data

A cryptographic [[commitment]] compresses a large array of data into a short digest that is *binding* (the prover cannot later find a different array with the same digest) and optionally *hiding* (the digest reveals nothing about the underlying data).

A [[polynomial commitment]] adds one crucial capability: after committing to a polynomial `P`, the prover can later prove that `P(r) = v` at any challenge point `r` by sending a short opening proof that the verifier checks against the commitment digest alone, without ever downloading the polynomial's coefficients. That is how a verifier checks a 400-billion-parameter model on a laptop CPU: the operator commits to the model's weight polynomials once ahead of time, and each inference proof opens that commitment at a few random evaluation points.

The choice of polynomial commitment scheme shapes a prover's entire performance and trust profile:

- **Elliptic-curve commitments** such as [KZG](https://doi.org/10.1007/978-3-642-17373-8_11) produce tiny opening proofs, but require a [[trusted setup]] ceremony where secret parameters must be generated and then destroyed.
- **Hash-based commitments** (such as those built on Reed-Solomon error-correcting codes and the [FRI](https://eccc.weizmann.ac.il/report/2017/134/) low-degree test) require no trusted setup at all and run fast on GPUs, at the cost of much larger proofs (often megabytes rather than kilobytes).

While the model weights only need to be committed once, the intermediate activations (the witness) change on every prompt and must be committed fresh during every proof, which often accounts for the single largest share of proving time.

## 4. Fiat-Shamir hashing replaces live interaction

In an interactive proof, the prover sends a commitment, the verifier flips coins to pick a random challenge `r`, and the prover replies. Interactive proofs are inconvenient because they only convince the party who chose the challenges live. The [Fiat-Shamir transformation](https://doi.org/10.1007/3-540-47721-7_12) makes the protocol non-interactive: instead of waiting for a live verifier to pick `r`, the prover derives `r` by hashing the public statement and every message written to the proof transcript so far. Anyone can later verify the resulting file by recomputing those same hashes.

Fiat-Shamir comes with two important caveats:

1. Because the prover can compute hashes offline, a cheating prover can try grinding through billions of slightly different commitments until it finds a hash challenge that happens to miss its lie. Parameters must therefore be sized so that even after `q` hash queries, the probability of finding a lucky collision remains negligible (the [[random oracle]] model).
2. If an engineer forgets to include some part of the public statement or transcript inside the hash input, a cheating prover can modify that omitted value *after* seeing the challenge and forge a proof. This bug class ("Frozen Heart") has bitten real systems repeatedly: Trail of Bits disclosed it across several popular libraries [in 2022](https://blog.trailofbits.com/2022/04/13/part-1-coordinated-disclosure-of-vulnerabilities-affecting-girault-bulletproofs-and-plonk/), and a [2026 audit](https://osec.io/blog/zkvms-unfaithful-claims/) found and fixed six more instances across four sumcheck-based provers and two STARK provers. Even more subtly, a [2025 paper](https://eprint.iacr.org/2025/118) showed that Fiat-Shamir can fail for certain protocols even when every transcript message is hashed, if the attacker is allowed to choose the circuit being proved and tailors it around the hash function.

## Zero knowledge is a separate property

Nothing in steps 1 through 4 automatically hides the model weights! If a prover sends raw evaluations of its weight polynomial at several points, each evaluation reveals a linear equation over the weights. To make a proof [[zero knowledge|zero-knowledge]], the prover must blind its commitments and mask its polynomial evaluations with fresh random noise so that the transcript reveals nothing beyond the fact that the statement holds.

Keep two distinctions in mind when reading zero-knowledge claims:

- **Succinctness and soundness do not imply zero-knowledge.** Many proof systems use "ZK" in their project name while leaving blinding unimplemented or optional for speed.
- **Paper zero-knowledge does not guarantee implementation zero-knowledge.** Even a single unblinded opening or side-channel metadata field in the C++ or Rust code can leak weight information. Our "Weights hidden" petal records what each publisher documents about weight hiding at the pinned commit; our harness does not test for subtle cryptographic leaks.

## What an accepted proof actually guarantees

When a verifier accepts a proof, it means that either the claimed statement holds, or the random challenges happened to land on a point where two unequal polynomials agreed, or one of the underlying cryptographic assumptions was broken. The probability of an unlucky challenge in a single round is the [[soundness]] error; accounting for offline hash grinding gives the [[security level]] in bits.

Whenever a system claims a λ-bit security level, ask whether that bound is *proved* or *conjectured*. In hash-based STARK and proximity-test provers, choosing how many Merkle branches to query depends on how tightly error-correcting codes behave under correlated hashing. For years, many production systems set their query counts using an optimistic mathematical conjecture that roughly halved proof sizes compared to proven bounds. In late 2025, three papers ([one](https://eprint.iacr.org/2025/2010), [two](https://eprint.iacr.org/2025/2046), [three](https://eprint.iacr.org/2025/2055)) disproved that conjecture in its strongest form. No deployed system was forged, and existing proofs still pass verification, but as the [Ethereum Foundation explained](https://blog.ethereum.org/2025/12/18/zkevm-security-foundations), "what was advertised as 100 bits might actually be 80".

Crucially, no black-box benchmark can measure a system's security level by running its verifier. A prover configured for 60 bits of security and a prover configured for 128 bits both accept every honest proof and both reject every tampered input our test suite sends. Distinguishing 60 bits from 128 bits empirically would require executing a `2^60`-hash forgery search. Security bits come from mathematical analysis of the protocol and parameters, which is why our [checks](/checks) test input bindings empirically while our glyph reports the publisher's documented security level alongside its basis.

## Quick guide to common proof-system terms

| Term | What it actually means | What it does *not* imply |
|---|---|---|
| Succinct | The proof is much smaller and faster to verify than re-running the computation | That *generating* the proof is fast |
| Non-interactive | The proof is a static file that anyone can verify without talking to the prover | That the system required no trusted setup ceremony |
| SNARK | Succinct Non-interactive Argument of Knowledge | That the proof hides the witness (hiding requires a *zk*-SNARK) |
| STARK | Typically a proof system built from hash functions and Reed-Solomon codes with no trusted setup | Any specific proof size or proving speed |
| Transparent | Public parameters are derived from public randomness with no secret setup | That the proof relies on no unproven cryptographic assumptions |
| Argument | [[soundness|Sound]] against a computationally bounded prover | Sound against an unbounded adversary (which is an information-theoretic *proof*) |

Next, [Proving a forward pass](/forward-pass) shows how these building blocks come together to prove a transformer layer.
