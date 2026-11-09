# AGENTS.md

Instructions for coding agents (and humans) working in this repository. Read this file, then `docs/SPEC.md` and the RFCs your task touches.

## What this project is

An open, neutral benchmark for provable inference: the same models, the same reference hardware, the same timing rules, and a claim card saying what each proof establishes. It measures provers; it does not build them, rank them or certify them.

## Sources of truth

The RFCs in `rfcs/`, then `docs/SPEC.md` and `docs/spec/`, then `docs/PRD.md`. If code and an RFC disagree, the RFC wins: fix the code or change the RFC.

## Hard rules

1. **Never patch a prover.** Adapters wrap upstream tools at a full commit hash. No source change, no undocumented parameter. If an adapter cannot work without a change, stop and open an issue.
2. **No published number without its labels.** Every number in `results/`, `releases/` and on the site carries unit, timing scope, grade, tier and source (RFC-0004, RFC-0012), and the site shows the scope and n beside it.
3. **Derived numbers are computed, not typed.** A ratio goes into the derivation code so CI recomputes it.
4. **Weakening flags only in control jobs.** A flag that weakens a system's statement (for example SASH's `--unsound-skip-*`) is never used outside a negative-control job (RFC-0008), never to make a run pass.
5. **Never fabricate or round away results.** A failed run is recorded with its exit code and last lines. Report ranges and sample sizes, never a single best run.
6. **The commitment the verifier checks comes from the harness record**, never from files sent with a proof.
7. **No secrets, hosts or personal data.** No API keys, SSH aliases, IP addresses, account names or machine identifiers beyond the hardware record RFC-0006 asks for.
8. **No weights in the repository.** Models are referenced by public source and content hash.
9. **Claims follow the systems' own documentation.** On a claim card, copy what the system states at the pinned commit, link it, and write "not stated" where it is silent. Do not infer security properties.
10. **Neutral language.** No ranking or superlative words. Describe what was measured. Say "proved", "bound", "attested" or "sampled" precisely; never "provably safe".
11. **Pin everything and check pins against content**: full commit hashes, container digests, toolchain versions, weights sha256 and model digest at fetch. The manifest records the adapter commit and image digest.

## Working practice

- Slow work (prover builds, GPU runs) runs on a GPU host. CPU-only steps (schema checks, the verifier on stored proofs, adapter tests on fixtures) run anywhere.
- Every derived metric ships a test against a hand-computed case. Every adapter ships a CPU-only test against stored fixtures.
- Before pushing: `ruff check`, `ruff format --check`, `mypy --strict harness/src/iproofs harness/tests`, `pytest harness/tests systems -n auto --dist loadfile`, `iproofs validate --all`.

## Writing style

Plain, dense, active voice, short sentences. Define a term once (`docs/spec/10-glossary.md` holds the vocabulary). Numbers carry units and conditions. Use commas, colons or parentheses rather than dashes in prose.

## Layout

| Path | What |
|---|---|
| `docs/` | PRD, SPEC index, `spec/` sections, runbooks |
| `rfcs/` | normative decisions |
| `schema/` | JSON Schemas with valid and invalid examples |
| `harness/` | the `iproofs` package and its tests |
| `systems/<name>/` | one adapter per system |
| `workloads/`, `reference/`, `results/`, `releases/` | inputs, profiles, run records, frozen releases |
| `web/` | the static site written by `iproofs site build`, deployed by Vercel |
