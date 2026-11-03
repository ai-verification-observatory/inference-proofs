# Inference Proofs: technical specification

Status: Draft 0.1. This document is the system overview. Each normative part lives in an RFC under `rfcs/`; where this document and an Accepted RFC disagree, the RFC wins. Requirement keywords (MUST, SHOULD, MAY) follow RFC 2119.

## 1. Architecture

```
                  workloads/          systems/<name>/            reference/
                (models, prompts,   (adapter: Dockerfile,     (hardware profiles,
                 shapes, controls)   claim card, pins)         cost basis)
                        \                  |                      /
                         \                 v                     /
                          +------>  harness (runner)  <---------+
                                    |   one job = system x workload x shape x repetition
                                    |   measures externally, calls the adapter, collects outputs
                                    v
                          results/<release>/<system>/<run-id>/
                            run.json  manifest.json  verifier/  logs/  digests
                                    |
                     CI: schema check, recompute derived numbers, control verdicts
                                    |
                                    v
                          site/ (static, generated)   reports/<release>.md
```

Five kinds of object, each with a JSON Schema in `schema/`:

| Object | File | Defined in |
|---|---|---|
| Claim card | `systems/<name>/claim.yaml` | RFC-0002 |
| Workload | `workloads/<id>.yaml` | RFC-0003 |
| System manifest | `systems/<name>/system.yaml` | RFC-0005 |
| Run result | `results/.../run.json` | RFC-0004, RFC-0009 |
| Control verdicts | `results/.../controls.json` | RFC-0008 |

## 2. Repository layout (target)

```
docs/            PRD.md, SPEC.md
rfcs/            numbered RFCs and the template
schema/          JSON Schemas for every object above
harness/         the runner (Python, one package), metric collectors, validators
systems/         one directory per system: adapter Dockerfile, entrypoint, system.yaml, claim.yaml
workloads/       workload definitions and generators for prompts and negative controls
reference/       hardware profiles and cost bases, one file per release
results/         run outputs, append-only
site/            static site generator; output is not committed
reports/         one report per release
```

## 3. The job

A job is one system, one workload, one shape, one repetition, on one machine. The harness:

1. Resolves the workload: downloads the model, checks its content hash, materialises the prompt set and checks its hash.
2. Pulls the system's container by digest and records the digest.
3. Records the machine: GPU model and count, driver, CUDA runtime, CPU model and cores bound, host memory, disk type, kernel, container runtime (RFC-0006).
4. Calls the adapter's entrypoints in order: `info`, `setup`, `commit`, `prove`, then `verify` on a separate verifier profile (Section 5). Each call is timed by the harness, with resource sampling (Section 4).
5. Runs the negative-control jobs for the workload (RFC-0008).
6. Writes `run.json` and `manifest.json`, validates both against the schemas, and computes derived metrics.

A failed step is recorded with its exit code and last lines; the job is kept, not deleted.

## 4. Measurement

The harness measures from outside the container. The adapter may also report internal phase timings, which are kept and labelled as adapter-reported.

| Quantity | How | Unit |
|---|---|---|
| Wall time per entrypoint | monotonic clock around the container call | s |
| GPU memory peak | NVML sampling at 10 Hz or faster, max over the call | MiB |
| GPU utilisation | NVML sampling, mean and p95 | % |
| Host memory peak | cgroup `memory.peak` of the container, file cache excluded | bytes |
| CPU time | cgroup `cpu.stat` | s |
| Energy (optional) | NVML energy counter difference | J |
| Proof size | bytes of every proof file, plus any per-commitment files a verifier must download | bytes |
| Verdict | adapter's normalised verdict (Section 6) and the verifier's raw exit code and last line | |

### Timing scopes

Every time-based number names one scope (RFC-0004). The scopes:

| Scope | Covers |
|---|---|
| `setup` | build or load of the prover, model download excluded |
| `commit` | creating the model commitment; once per model and commitment |
| `prove.steady` | proving after warm-up, start-up excluded, across the measured batches |
| `prove.session` | a proving session from process start to the last proof released, start-up included |
| `whole_wall` | from the first entrypoint call to the last proof, including witness generation and I/O |
| `verify` | checking one proof on the verifier profile |
| `primitive` | one primitive timed alone (adapter-reported only) |

### Derived metrics

Derived numbers are computed by CI from stored raw numbers and are never typed by hand.

| Metric | Formula |
|---|---|
| Proved tokens per second | tokens covered by proofs ÷ seconds, per scope |
| Cost per 1,000 proved tokens | seconds per token × 1,000 × reference price per GPU-hour ÷ 3,600 × GPUs used |
| Amortised commit cost | commit seconds ÷ tokens proved over the stated amortisation horizon (default 1,000 requests) |
| Overhead against plain serving | plain-serving tokens per second ÷ proved tokens per second, same model, precision, hardware and phase |
| Proved active-parameter-tokens per second | proved tokens per second × active parameters per token (dense: all parameters; mixture of experts: active per token) |
| Proof bytes per proved token | total proof bytes ÷ tokens covered |
| Verification seconds per proved token | verify seconds ÷ tokens covered |

"Tokens covered" counts the positions whose computation the proof binds, as declared in the claim card and checked against the workload: for a prefill proof that states the next token, the window's positions; for a segment grid, the positions in the grid. The claim card says which.

## 5. Machines

Two profiles per release, defined in `reference/<release>.yaml` (RFC-0006):

- **Prover reference:** for v0.1, one NVIDIA H100 80 GB (SXM, HBM3), at least 24 CPU cores on the GPU's NUMA node, at least 330 GB host memory, at least 500 GB local NVMe. Both v0.1 systems run on this profile.
- **Verifier reference:** CPU only, 8 cores, 32 GB memory, no GPU. Verification is also timed on one core.

A system that needs more than the prover reference runs on a declared larger profile and its row says so. Nothing is ever compared across profiles without the profile in the row.

The commitment the verifier checks against comes from the harness's own record of the `commit` step, never from files that travel with the proof.

## 6. Adapter contract (summary)

One OCI image per system, built from `systems/<name>/Dockerfile`, which pins the upstream commit by full hash. The image exposes one entrypoint with five subcommands. Each reads a job file and writes a result file, both JSON, under `/io`:

| Subcommand | Reads | Writes |
|---|---|---|
| `info` | | system name, upstream commit, supported workloads and shapes, required profile |
| `setup` | workload, shape | ready marker; build logs |
| `commit` | model path | commitment identifier, verifier key files, sizes |
| `prove` | commitment, prompt set, shape, batch size | proofs, claimed outputs, adapter-reported phase timings |
| `verify` | commitment, verifier key, request, claimed output, proof | verdict: `accept`, `reject`, `no_verdict` or `invalid_call`, plus the raw exit code and last line |

Adapters translate, they do not change: no patch to the prover's source, no change of its parameters beyond what its documentation offers. Full contract: RFC-0005.

Notes from the first two systems:

- **FlashProve** exposes `cp_commit`, `cp_prove` and `cp_verify`. Its verifier's exit codes map directly: 0 accept, 1 reject, 5 no verdict, 14 invalid call; 2, 3, 4 and 15 are invalid calls. Its own rule that the commitment ID must come from a trusted party matches Section 5. Each proving run consumes batches of a leaf table, so every run commits fresh (`-M 1`) on synthetic or public weights.
- **SASH** proves a grid of segments and checks the seams with `boundary-grid`; one "proof" in our sense is the set of segment proofs for one sequence plus the passing grid check. Its `--unsound-skip-*` flags are used only in negative-control jobs, never in a measured row, and the adapter rejects them otherwise. Its `constants.json` grades map onto our grades (RFC-0004).

## 7. Claim card (summary)

```yaml
system: flashprove
upstream: {repo: anthropics/FlashProve, commit: 9e2bdd8f...}
relation: >
  The output token is the top choice of the integer model whose weights were
  committed under the given commitment ID, on the given 1,024-token window.
security:
  notion: knowledge soundness (Lean verifier); C++ verifier tested against it
  bits: "q/2^124 + 2^-101 after q hash queries, exact-match policy"
  model: random oracle; classical adversary
  setup: to be declared by the maintainers
zero_knowledge: {claimed: true, scope: "weights, except a declared list", status: "proved for the protocol in Lean; tested in code"}
assumptions:
  - configuration files fixed before the hash function is drawn
  - the commitment ID is obtained from a trusted party
coverage: {phase: prefill, tokens_covered: window, policy: exact-match}
residual:
  - proves the integer model, which differs from the 16-bit model's top token at some positions
  - under the clipped-gap policy used for whole replies, only conformance to that policy is proved
availability: available
reviewed_by_maintainers: false
```

Every field has a source link to the system's own documentation at the pinned commit. The example shows the shape, not a reviewed card. Full schema: RFC-0002.

## 8. Grades and evidence tiers

Every number carries two labels:

- **Grade** (how the number was obtained): `measured` (from a stored artifact by the harness), `derived` (computed by CI from measured numbers), `projected` (from a cost model, inputs named), `external` (read from a public source, URL and pin given), `asserted` (an input such as a price, with its reason).
- **Evidence tier** (who stands behind it): `reported` (by the system's authors), `peer-reviewed` (another submitter checked the submission), `reproduced` (rerun by someone other than the authors on hardware they chose). Only reproduced numbers are called measured in prose.

## 9. Divisions

- **Native:** each system on its own supported workload. Rows are shown side by side with normalised metrics and are never presented as a head-to-head result.
- **Closed:** a fixed common workload and a fixed claim class (RFC-0003). Rows in one closed workload compare directly.
- **Open:** any workload or claim, declared, shown separately.

v0.1 has native rows only.

## 10. Negative controls (summary)

Shared controls, applied to every system after an honest run: change the claimed output token, change one prompt token, verify against a different commitment, substitute weights after committing (prover side), replay a valid proof for a different request, truncate the proof, flip one byte of the proof, swap two proofs within a batch. Each control has a positive twin that must be accepted. System-specific controls come from each system's own suites (FlashProve `examples/rejected-proofs`, SASH `--unsound-skip-*` jobs, which a verifier is expected to accept and the claim card must then mark as unbound). A row reports controls rejected out of controls run, and lists any `no_verdict`. Full list: RFC-0008.

## 11. Results and publication

`results/` is append-only. A release freezes a set of runs, the reference file and the RFC versions in force. The site shows, per system: the claim card first, then the rows with their scope, grade and tier, the controls, the reference rows, and the maintainers' reply if any. No aggregate score, no sort by speed by default. Before any release, each listed team reviews its rows for at least 14 days. Full rules: RFC-0009.

## 12. CI

On every pull request: schema validation of every changed object; recomputation of derived numbers from raw ones (a mismatch fails); a check that every number has a scope, grade and tier; a check that no measured row ran with an unsound flag; link and pin checks (full commit hashes, container digests, model hashes).
