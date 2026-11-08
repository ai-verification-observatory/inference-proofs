# Inference Proofs: product requirements

Status: Draft 0.1 · Working name, open to change (see Open questions)

## 1. Problem

Several open systems now produce cryptographic proofs that a language model produced a given output. Each publishes its own numbers, measured its own way, on its own model, for its own claim. Nobody can answer the questions a user of these systems actually has:

- What exactly does a proof from system X establish, and under which assumptions?
- What does it cost, in GPU time, memory, money and proof size, to prove one token on a given model?
- How long does it take to check a proof, and on what hardware?
- Does the verifier reject a tampered model, prompt, output or proof?
- Would I get the same numbers if I ran it myself?

The first two open systems show the gap clearly. Both are Apache-2.0, both run on one NVIDIA H100 80 GB, and both are serious work. Their published figures still cannot be put side by side:

| | SASH zk-inference-prover | FlashProve |
|---|---|---|
| Source, pin | `sg-ai-safety-hub/zk-inference-prover` at `eb95bfa`, results in `zk-inference-results` at `11decec` | `anthropics/FlashProve` at `9e2bdd8f` (v0.16.0) |
| Model | Llama-3.1-8B, W8A8 quantized, dense | Llama 4 Maverick, public 4-bit conversion, mixture of experts (about 400B parameters) |
| What one proof covers | one segment: a transformer layer over a block of token positions, or the output head; a sequence is a grid of segments | one request: a pass over a 1,024-token window, stating the next token |
| Phase | prompt and decode positions with greedy continuation | prefill; whole replies under a looser "clipped gap" policy |
| Headline rate | 1.251 positions/s over 4,608 positions, loop scope (0.840 positions/s whole wall) | 111.23 ± 0.92 tokens/s of prefill at 24 requests per batch, steady state, start-up and commitment excluded |
| Proof size | 19.8 GB in total for the 4,608-position run (290 segments) | 18.78 MB per proof on average |
| Verification | 119 s in total for that run, no GPU | about 21 s per proof on one CPU thread (C++); about 24 minutes with the Lean verifier |
| Weights | pinned by commitment; weight hiding not claimed in the repository at this pin | commitment published, weights masked except a declared list (zero knowledge proved in Lean for the protocol, tested in code) |
| Soundness statement | per-edge binding table, each edge switchable off by an `--unsound-skip-*` flag | Lean theorem for the Lean verifier, exact-match policy, random-oracle model |
| How numbers are graded | `constants.json`: each number names card, context, timing scope and a grade (measured, derived, projected, external, asserted) | `docs/figures.tsv` and `limits-all-rows.tsv`; the measuring scripts and run records are not in the repository |

Every cell above comes from the two repositories at the stated pins. Different models, phases, timing scopes and claims: a reader who divides one headline by the other learns nothing. That is the problem this project exists to solve.

## 2. Vision

A neutral, open, reproducible benchmark for provable inference: the same models, the same reference hardware, the same timing rules and an explicit statement of what each proof claims, maintained by the teams that build the provers and the people who would rely on them.

The model is Ethproofs, which made zkVM provers for Ethereum blocks comparable by fixing the workload (real blocks), publishing per-prover rows (hardware, latency, cost) and letting a credible convener publish targets that teams then raced to meet. Two lessons carry over: a fixed workload makes rows comparable, and targets set by users serve readers better than rankings set by the benchmark. One lesson does not: Ethereum blocks are one well-defined statement. Inference proofs make different statements, so the claim has to travel with every number.

## 3. Users

| User | Needs from the benchmark |
|---|---|
| Prover teams | A cheap way to publish credible, reproducible numbers; a fair comparison; a negative-control corpus they do not have to build themselves |
| Researchers | Pinned, rerunnable measurements; the cost structure behind a number (commit, prove, verify, I/O) |
| Relying parties: policy analysts, auditors, labs, governments, standards bodies | A plain statement of what each system proves and what it does not; whether a system meets a threshold they care about |
| Funders | Evidence of progress over time that does not depend on each team's own reporting |

## 4. Goals

1. **G1. Claim first.** Every published number carries a claim card: the relation proved, the security notion, the assumptions, the scope and the residual (what a dishonest prover can still do). A number without a claim card is not published.
2. **G2. Comparable by construction.** Fixed workloads, fixed reference hardware, fixed timing scopes, fixed cost basis. Where systems cannot run the same workload, the benchmark says so and compares only what is comparable.
3. **G3. Reproducible.** Every row pins the prover commit, container digest, model hash, hardware and driver versions, and the exact command. A number is called measured only once someone other than the authors has reproduced it.
4. **G4. Adversarial.** Every system faces the same negative controls; each row reports which ones it rejects.
5. **G5. Neutral.** Multi-organisation maintainers, open methodology through RFCs, conflicts declared, teams review their own rows before publication, right of reply. No single score and no ranking.
6. **G6. Low cost to join.** A prover joins through a thin adapter. The harness never forks or patches a prover.

## 5. Non-goals

- Ranking systems or naming a "fastest" or "best" prover.
- Certifying security. The benchmark reports declared claims and test results; it does not audit soundness proofs or code.
- Building or maintaining provers or shared proving libraries.
- Training, fine-tuning or compute-accounting claims (out of scope for v0; see Roadmap).
- Setting the thresholds that matter for policy use. Relying parties set those (Section 9).

## 6. Scope of v0.1

Two systems, run unchanged at pinned commits on one reference machine type:

1. **SASH zk-inference-prover**, on its native workload: Llama-3.1-8B W8A8, the headline shape (4,096 prompt positions plus 512 continuation positions) and one shorter shape.
2. **FlashProve**, on its native workload: Llama 4 Maverick (public 4-bit conversion), 1,024-token windows, batch sizes 1 and 24.

Plus two reference rows per workload, so every proof cost reads against something:

- **Plain serving:** the same model and precision served unproved on the same hardware (vLLM, pinned). The overhead factor is the most asked-for number.
- **Naive recompute:** a verifier holding the weights reruns the forward pass. What does a proof buy over that?

What v0.1 does not do: compare SASH and FlashProve on one model. Neither supports the other's model at these pins. v0.1 publishes both on their native workloads, side by side, with normalised metrics (cost per proved token at the reference price, overhead against plain serving, prover time per bit of active weights) and the claim cards that explain why the headline numbers differ.

v0.1 also defines one closed workload, `l31-8b-c1024`: Llama-3.1-8B W8A8 at SASH's shorter shape, with one fixed claim class, where rows compare directly. Its rows publish once a second system with that class runs it through an adapter with no upstream change (RFC-0003 Q7, a default until the owner resolves it; the release freeze enforces it). Of the systems read, SASH alone runs it today; the sources of TOPLOC, Verde, the Private ML SDK and zkPyTorch name the model, and none of them has a claim card ([RFC-0003 §Closed workloads](../rfcs/0003-workloads.md#closed-workloads), [`workloads/README.md`](../workloads/README.md#closed-workloads)). More common workloads come in v0.2 (RFC-0003).

## 7. Requirements

### Functional

| ID | Requirement | RFC |
|---|---|---|
| F1 | A claim card schema, machine-checkable, filled per system and reviewed by its maintainers | 0002 |
| F2 | A workload registry: model by content hash, prompt sets by hash, shapes, decoding rule; native and common workloads | 0003 |
| F3 | A metric set with fixed timing scopes (commit, prove, verify, whole wall, steady state) and a grade on every number | 0004 |
| F4 | An adapter contract: one OCI container per system exposing `info`, `setup`, `commit`, `prove`, `verify` over JSON files | 0005 |
| F5 | A reference hardware profile and a cost basis fixed per release | 0006 |
| F6 | Evidence tiers (reported, peer-reviewed, reproduced) and a reproduction protocol; closed and open divisions | 0007 |
| F7 | A negative-control suite: shared controls plus each system's own; rejection expected; results per row | 0008 |
| F8 | A results format, a generated static site and a per-release report, with right of reply | 0009 |
| F9 | A harness that runs a job end to end, measures externally, collects the adapter's internal timings and writes a result file valid against the schema | SPEC |
| F10 | CI that validates every submission against the schemas and recomputes every derived number | SPEC |

### Non-functional

- **N1 Reproducibility.** Every run is reproducible on rented commodity hardware that no maintainer controls.
- **N2 Transparency.** Raw outputs, logs and verifier transcripts are kept, except proofs above a size cap, which are kept by digest with one archived proof per configuration.
- **N3 Honesty of numbers.** Ranges and sample sizes, never a single hand-picked run. Failed runs are recorded, not dropped.
- **N4 Neutral funding.** Any sponsor of compute is disclosed on the site and in every report, separately from conflict notes, and buys no editorial control.
- **N5 Licences.** Code Apache-2.0; specifications, data and reports CC BY 4.0. DCO sign-off on contributions.

## 8. Success metrics

- v0.1: both systems reproduced end to end by someone other than their authors, on the reference hardware, with the maintainers of each system having reviewed their row and claim card.
- v0.2: at least one common workload run by both systems through adapters only, with no harness change.
- Within a year: at least five systems across at least two proof families, at least two maintainers from outside the founding group, and at least one team submitting its own runs unprompted.
- Adoption over attention: submissions and reproductions count, stars do not.

## 9. Targets set by relying parties

The benchmark does not decide what is good enough. It invites relying parties (policy researchers, auditors, labs, standards bodies) to publish targets in their own words, for example a maximum cost per proved token, a maximum verification time on a laptop, a minimum security level, or zero knowledge for the weights. Each row then shows "meets this target" or "does not", per target and per author, next to the claim card. Targets are versioned and attributed.

## 10. Roadmap

| Release | Content | Exit criteria |
|---|---|---|
| v0.1 | SASH and FlashProve on native workloads; plain-serving and recompute reference rows; claim cards; negative controls; harness; site | Both reproduced by a third party; both teams reviewed their rows |
| v0.2 | A common workload family that both systems and new entrants can run (RFC-0003): a small dense transformer that every prover supports, and a mid-size open model; first external system by consent | Two systems on one workload through adapters only |
| v0.3 | More systems and families (other zkML provers, TEE attestation baselines, sampled recompute) with their own claim cards; first targets from relying parties | First cross-family report reviewed by every listed team |
| later | Decode-heavy and long-context workloads; batch and latency profiles; on-chain verification cost where relevant | |

## 11. Risks

| Risk | Mitigation |
|---|---|
| Apples to oranges: headline numbers compared out of context | Claim card beside every number; divisions; normalised metrics only; no single score |
| A team objects to its row | Teams review before publication; right of reply printed beside the row; methodology changes only through RFCs |
| The benchmark looks captured by one organisation | Maintainers from several organisations; conflicts declared; sponsors disclosed; every run reproducible elsewhere |
| Proving runs are expensive | Small and native workloads first; three repetitions, not thirty; results kept by digest |
| Provers that do not accept contributions (FlashProve is a research artifact, "not accepting contributions") | Adapters live in this repository and pin upstream; no upstream change is ever required |
| Upstream measuring scripts or run records are not public | The harness measures externally under its own timing rules; upstream figures are labelled reported until reproduced |
| A negative control the verifier "passes" because the control is broken | Each control ships with a positive twin that must be accepted; controls are reviewed like code |

## 12. Open questions

1. Name. "Inference Proofs" is a working name; a permanent name and home are open.
2. Which mid-size open model should the first common workload use, given what each prover supports today?
3. How should a sampled or statistical guarantee sit beside a cryptographic one in the same table?
4. Should runners sign their result files (for example from an attested runner) to make reproduction cheaper?
5. Which reference price per GPU-hour, and how often is it updated?
6. Which relying parties publish the first targets?
