# RFC-0003: Workloads and divisions

- Status: Draft
- Created: 2026-11-03
- Requires: RFC-0002

## Summary

Defines what a workload is, the three divisions (native, closed, open), the v0.1 native workloads for SASH and FlashProve, and how common workloads are chosen for v0.2.

## Motivation

Fixed workloads are what made Ethproofs rows comparable. Provable inference has no single workload yet: at their pinned commits, SASH supports Llama-3.1-8B (W8A8) and FlashProve supports Llama 4 Maverick at full size plus small synthetic shapes. Neither runs the other's model. The benchmark has to be honest about that from the first release.

## Specification

### Workload

`workloads/<id>.yaml`, valid against `schema/workload.schema.json`:

| Field | Content |
|---|---|
| `id`, `version` | e.g. `llama31-8b-w8a8-c4096`, `1` |
| `model` | source, revision, content hash of every weight file, licence and access terms |
| `precision` | quantisation scheme as served and as proved |
| `prompts` | generator or file, seed, count, content hash |
| `shape` | prompt length, output length, batch size, context window |
| `decoding` | greedy or sampled; if sampled, the seed rule |
| `phase` | prefill, decode, or both |
| `division` | native, closed or open |
| `systems` | systems known to support it |

Weights are referenced by hash and fetched from their public source; the repository never redistributes weights.

### Divisions

- **Native.** A system's own supported model and shape. Rows from different native workloads are shown side by side with normalised metrics (RFC-0004) and are never called a head-to-head result.
- **Closed.** A common workload and a fixed claim class (for example "greedy output tokens of the committed model on this prompt, exact match"). Rows within one closed workload compare directly.
- **Open.** Anything declared. Shown separately.

### v0.1 workloads (native)

| ID | System | Model | Shape | Notes |
|---|---|---|---|---|
| `sash-l31-8b-c4096` | SASH | Llama-3.1-8B, W8A8 | 4,096 prompt + 512 greedy continuation, batch 1 | the system's published headline shape |
| `sash-l31-8b-c1024` | SASH | same | 1,024 prompt + 64 continuation | close to FlashProve's window length |
| `fp-maverick-w1024-b1` | FlashProve | Llama 4 Maverick, public 4-bit conversion | 1,024-token window, next token, batch 1 | |
| `fp-maverick-w1024-b24` | FlashProve | same | 1,024-token window, next token, batch 24 | the system's published steady-state shape |
| `ref-serve-*` | plain vLLM | each model above at the same precision where the engine supports it, else the nearest, declared | same shapes | reference row |
| `ref-recompute-*` | plain forward pass by a verifier holding the weights | each model above | same shapes | reference row |

Prompts: a fixed public-domain text set, tokenised per model, seeded, hashed. The same text feeds every workload so that lengths in tokens differ only by tokenizer.

### Choosing common workloads (v0.2)

A candidate common workload is accepted when at least two systems run it through their adapters without upstream changes. Candidates, in order of preference:

1. A small dense transformer of standard architecture with public weights, which every prover can support (a floor for comparison).
2. A mid-size open model in the 7B to 9B range that at least two provers support.
3. A mixture-of-experts model, once two provers support one.

Each common workload fixes one claim class for its closed division.

## Rationale and alternatives

Forcing both systems onto one model now would mean patching provers, which the adapter contract forbids (RFC-0005). Publishing native rows with claim cards and normalised metrics is honest about what can be compared today and creates the pressure for common workloads.

## Open questions

1. Which mid-size model has the widest prover support as of the first v0.2 call?
2. Whether decode-heavy shapes (long outputs) get their own workload family.
