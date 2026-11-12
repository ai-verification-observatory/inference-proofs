You already trust cheap checks in place of expensive work: a checksum instead of a byte-for-byte comparison, a gradient check instead of a derivation by hand. A proof system pushes that trade as far as it goes. In most published systems the check costs a small fraction of what making the proof costs, the checker never holds the model, and at a security level of 100 bits a wrong result passes less than once in 2^100 tries. Five ideas are enough to follow it. This page works the first by hand and states the other four.

## A random check can stand in for redoing the work

Someone hands you three matrices and says that C = A·B. Multiplying A by B yourself costs about n^3 operations for matrices of side n. [Freivalds' check](https://en.wikipedia.org/wiki/Freivalds%27_algorithm) costs about n^2: draw a random vector r, compute B·r, then A·(B·r), and compare the result with C·r. That is three products of a matrix with a vector and no product of two matrices.

If C is right, the two sides are equal for every r. If C is wrong in even one entry, they differ for at least half of all vectors of zeros and ones.

:::explore random-check
A·B with one entry of the claimed product changed. With r drawn from 0 and 1, about half the draws read the changed column and refuse. With r drawn from 0 to 96, a draw misses only when it puts a zero on that column: 1 time in 97.
:::

Two things in this example hold for every system on this site. The random draw comes after the claim is fixed: a prover who knew r in advance could build a wrong C that passes. And the chance of missing an error is at most one over the size of the set r is drawn from: one half with bits, 1 in 97 with the numbers below 97, less than 1 in 10^18 in a prime field of 64 bits. The set has to be a field: with ordinary 64-bit integers that wrap around, some errors are missed by every even r. Proof systems draw their challenges from large fields for that reason.

Freivalds' check is not yet a proof system. The checker holds all three matrices and does work in proportion to their size. The next ideas remove both: polynomials and commitments let the checker work without the matrices, and the sumcheck protocol of the next page cuts its work.

## Polynomials turn a small lie into a large one

Take a list of numbers, such as a row of weights. There is exactly one polynomial of the lowest possible degree that passes through them, and it can be evaluated anywhere, not only at the positions of the list. (Provers use the [[multilinear extension]], a polynomial in log n variables that is linear in each.)

Two different polynomials of degree d in one variable agree on at most d points. With several variables the count becomes a share: two different polynomials of total degree d agree on at most a share d/|S| of the points whose coordinates are drawn from a set S. This is the [Schwartz-Zippel lemma](https://doi.org/10.1145/322217.322225). For a multilinear extension in log n variables, d is log n. So if a prover changes one number of the list, the polynomial it encodes changes almost everywhere, and a single evaluation at a random point exposes the change, except with that small probability. This is not a spot check of one entry: the random point is not a position of the list, and its value depends on every entry. It is the reason one random query can replace reading the whole list.

For the lemma to hold, the arithmetic has to be exact, with no rounding and no overflow. Provers therefore compute in a [[field]]: the whole numbers below a prime p, where every sum and product is reduced modulo p. That reduction is exact arithmetic as long as the model's own integers stay far below p. Some provers use a small prime, of 31 or 64 bits, and draw their random challenges from a larger extension field. Floating point is not a field. The page on [inference](/inference) says what that costs.

## A commitment fixes data in a short value

A [[commitment]] is a short value computed from a large one. It is binding: finding two different inputs with the same commitment is infeasible. It can also be hiding: the short value reveals nothing about the input.

A [[polynomial commitment]] adds one ability. After committing to the polynomial that encodes its data, the prover can later show that the polynomial's value at a point r is v, with a short opening proof, and the verifier checks that against the commitment alone. This is how a verifier works with weights it never receives: the model is committed once, and each proof opens that commitment at a few random points.

Schemes differ in what their binding rests on, and the choice shapes a whole system. [KZG](https://doi.org/10.1007/978-3-642-17373-8_11) gives openings of constant size for a polynomial in one variable (logarithmic for the multilinear kind) and needs a [[trusted setup]]: secret numbers that someone must generate and destroy. Schemes built on hash functions, such as those that use the [FRI](https://eccc.weizmann.ac.il/report/2017/134/) proximity test, need no setup and produce larger proofs. Committing is itself a large computation. The model is committed once. The intermediate values are committed again for every proof, and in one published breakdown that is the largest single cost of the prover.

## Hashing replaces the verifier's coin flips

The checks above are conversations: the prover claims, the verifier draws a random challenge, the prover answers. A conversation convinces only the party who took part in it. The [Fiat-Shamir transformation](https://doi.org/10.1007/3-540-47721-7_12) turns it into a file anyone can check later. Each challenge is computed as a hash of everything said so far, so the prover can produce the whole transcript alone and still cannot choose the challenges. It can try again with another message and get new ones, so each check has to hold against every retry a prover can afford.

The price is an assumption: the hash function has to behave like a random function, which is the [[random oracle]] model. The transformation also has a known way to go wrong. If any part of the statement is left out of the hash, a prover can change that part after seeing the challenge. Real systems have shipped with this fault: several proof libraries [in 2022](https://blog.trailofbits.com/2022/04/13/part-1-coordinated-disclosure-of-vulnerabilities-affecting-girault-bulletproofs-and-plonk/), and six more proof systems [in a 2026 review](https://osec.io/blog/zkvms-unfaithful-claims/), since fixed. Four of the six are built on sumcheck and two are STARK provers. Separately, [a 2025 result](https://eprint.iacr.org/2025/118) shows a standard protocol for which the transformation fails even when applied in full, if the adversary may choose the program being proved and builds it around the hash function. Which values enter the hash, and who chooses the program being proved, are part of what a security review has to read.

## Zero knowledge is a separate property

A transcript built from evaluations of the prover's polynomials leaks information about them. A [[zero knowledge|zero-knowledge]] proof randomises what it sends, by adding masking polynomials and blinding its commitments, so that the transcript could have been produced by someone who knew only that the statement is true. For inference, the thing hidden is the weights.

Zero knowledge is not implied by the other properties. A proof can be short and [[soundness|sound]] and still leak. It also has to hold for the program that runs, not only for the protocol on paper: one unmasked value in an implementation is a leak. On this site the "Weights hidden" petal of a system's glyph records what its publisher states about this, and no check of ours tests it.

## What "accepted" means

The five ideas give a prover that commits to its data, answers hash-derived challenges about polynomials, and writes the answers to a file. The verifier recomputes the hashes and checks a handful of equations.

When the verifier accepts, the statement is true unless a random point fell where two different polynomials agree, or an assumption is false. The chance of the first, in one attempt, is the [[soundness]] error. A prover that makes its own challenges by hashing can try again, so a [[security level]] of λ bits is stated against work: a prover needs about 2^λ hash evaluations to get a false statement accepted, and after q of them it has succeeded with probability about q/2^λ. Two qualifiers travel with every such number. It is either proven, or conjectured from the strongest attack known. And it is stated for a protocol, which is not the same thing as the code that implements it.

A hash-based system chooses how many random queries to make from an estimate of what each query buys. For years many were configured under a conjecture that a query buys about twice what had been proven. In late 2025 three papers ([one](https://eprint.iacr.org/2025/2010), [two](https://eprint.iacr.org/2025/2046), [three](https://eprint.iacr.org/2025/2055)) showed the conjecture false in its strongest form. None gives a forgery of a deployed system, and proofs made with those parameters verify exactly as before. What changed is the number of bits that can be claimed for them: in the [Ethereum Foundation's words](https://blog.ethereum.org/2025/12/18/zkevm-security-foundations), "what was advertised as 100 bits might actually be 80".

A benchmark cannot measure this number by running the verifier. A system at 60 bits and a system at 128 bits both accept every honest proof, and both refuse every changed input a benchmark will ever send. Telling them apart by trial would take a forgery search of about 2^60 hash evaluations: within reach of a funded attacker, and not something a test suite runs. The level is computed from the parameters and the analysis behind them, never observed. This is why the [checks](/checks) on this site test only that a verifier refuses a changed model, prompt or reply, and why the site prints each publisher's stated security level without testing it.

## What the labels say, and what they do not

| Word | What it says | What it does not say |
|---|---|---|
| Succinct | The proof is short and quick to check, compared with the computation | That the prover is quick |
| Non-interactive | The proof is a file, checked without talking to the prover | That no setup was needed |
| SNARK | A succinct, non-interactive argument of knowledge | That it hides anything: that takes the "zk" in zkSNARK |
| STARK | Usage varies. Most often: built on hash functions, with no trusted setup | A particular proof size or speed |
| Transparent | No trusted setup: the public parameters are public randomness | That there are no assumptions |
| Argument | [[soundness|Sound]] against a prover of bounded computing power | Sound against unlimited computing power: that is a proof in the strict sense |

The next page, [Proving a forward pass](/forward-pass), applies these ideas to one layer of a model.
