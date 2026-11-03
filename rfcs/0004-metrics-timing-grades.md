# RFC-0004: Metrics, timing scopes and grades

- Status: Draft
- Created: 2026-11-03
- Requires: RFC-0003

## Summary

Fixes the metrics every run records, the timing scope every time-based number must name, the grade every number carries, and the formulas for derived metrics. Derived numbers are computed by CI, never typed.

## Motivation

The first two systems publish rates under different scopes. SASH's results name each number's scope (`commit`, `stwo total`, `whole wall`, `loop`, `primitive`) and grade (`measured`, `derived`, `projected`, `external`, `asserted`): its 4,096-context headline is 1.251 positions per second in loop scope and 0.840 in whole-wall scope, a factor of 1.5 from scope alone. FlashProve's headline, 111.23 tokens per second at 24 requests per batch, is a steady prefill rate with start-up and commitment excluded; with start-up counted over a five-batch session it is 103.60. Comparing headlines without scopes is meaningless; this RFC makes the scope part of the number.

## Specification

### Recorded per run

| Group | Metric | Unit |
|---|---|---|
| Time | wall time per entrypoint (`setup`, `commit`, `prove`, `verify`), measured by the harness | s |
| Time | adapter-reported phase timings (for example witness generation, commit, prove, aggregate) | s |
| Work | tokens covered by proofs, prompt and output separately | tokens |
| Memory | GPU memory peak; host memory peak (cgroup, file cache excluded) | MiB, bytes |
| Size | proof bytes per proof; per-commitment bytes the verifier must download once; per-commitment bytes the prover must keep | bytes |
| Verify | verification wall time on the verifier profile, multi-thread and one thread; peak memory | s, bytes |
| Outcome | verdict per proof; acceptance count | |
| Energy | GPU energy (optional) | J |

### Timing scopes

Every time and every rate MUST name one scope:

| Scope | Definition | Maps from SASH | Maps from FlashProve |
|---|---|---|---|
| `commit` | creating the model commitment | `commit` (per run) | `cp_commit` |
| `prove.steady` | proving after the first batch, start-up excluded | `loop` (closest; declared as approximate) | steady rate |
| `prove.session` | process start to last proof released | | rate with start-up counted |
| `whole_wall` | first entrypoint call to last proof, including witness generation and I/O | `whole wall` | not published |
| `verify` | one proof on the verifier profile | per-segment verify summed per sequence | `cp_verify` |
| `primitive` | one primitive alone | `primitive` | |

Mappings marked approximate are labelled so on the site. The harness's own scopes are authoritative; an upstream number enters only as `external` with its upstream scope stated.

### Grades

Every number carries one grade:

- `measured`: read by the harness from a stored artifact of this project's run.
- `derived`: computed by CI from measured numbers by a formula in this RFC.
- `projected`: from a cost model; the model and its inputs are named.
- `external`: read from a public source at a pinned commit or URL; the upstream scope and grade are kept.
- `asserted`: an input that is not measured (for example a price), with its source and date.

### Derived metrics

| Metric | Formula |
|---|---|
| Proved tokens per second | tokens covered ÷ seconds, per scope |
| Seconds per proved token | inverse of the above |
| Cost per 1,000 proved tokens | seconds per token × 1,000 × GPUs × reference price per GPU-hour ÷ 3,600 |
| Amortised commit cost per token | commit seconds ÷ tokens proved over the amortisation horizon (default 1,000 requests of the workload's shape) |
| Overhead against plain serving | plain-serving tokens per second ÷ proved tokens per second, same model, hardware, phase and batch size |
| Proved active-parameter-tokens per second | proved tokens per second × active parameters per token |
| Proof bytes per proved token | proof bytes ÷ tokens covered |
| Verification seconds per proved token | verify seconds ÷ tokens covered |

Active parameters per token: all parameters for a dense model; for a mixture of experts, the parameters used per token as stated in the model's own documentation, with source. This metric is a rough normaliser across model sizes and MUST be shown with the claim cards, never alone.

### Statistics

At least three repetitions per configuration. Report mean and sample standard deviation, plus minimum and maximum. Failed repetitions are counted and shown. The first batch of a session is excluded from `prove.steady` and included in `prove.session`.

## Rationale and alternatives

The scope and grade vocabularies are adapted from SASH's results repository, which already applies them to every number it publishes; reusing them lowers the cost of adoption. FLOPs per second was considered as a normaliser and rejected for v0.1: proof systems do work that is not model FLOPs, and the active-parameter-token metric is easier to check.

## Open questions

1. The default amortisation horizon for commitment cost.
2. Whether to report latency percentiles per request once batch and queueing workloads exist.
