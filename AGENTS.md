# AGENTS.md

Instructions for coding agents (and humans) working in this repository. Read this file, then `docs/SPEC.md` and the RFCs your task touches.

## What this project is

An open benchmark for provable inference. Level 1 ([RFC-0018](rfcs/0018-level-1-ladder.md), `levels/L1.yaml`) is a ladder of open-weights models. On each rung, every system we can run unpatched gets one fixed request, six checks we run ourselves and one figure: the cost of a proved reply as a multiple of serving it. Systems that pass the six checks are ranked by that figure inside their rung, never across rungs. It runs provers; it does not build or certify them.

## Sources of truth

`levels/` and the RFCs in `rfcs/` (RFC-0018 wins over earlier RFCs for a Level 1 release), then `docs/SPEC.md` and `docs/spec/`, then `docs/PRD.md`. If code and an RFC disagree, the RFC wins: fix the code or change the RFC.

## Hard rules

1. **Never patch a prover.** Adapters wrap upstream tools at a full commit hash. No source change, no undocumented parameter. If an adapter cannot work without a change, stop and open an issue.
2. **No published number without its labels.** Every number in `results/`, `releases/` and on the site carries unit, timing scope, grade, tier and source (RFC-0004, RFC-0012), and a system's page shows the scope and n with it. The ladder and the Scale page print a figure with its unit alone, its labels in its title (RFC-0018 SI-8).
3. **Derived numbers are computed, not typed.** A ratio goes into the derivation code so CI recomputes it.
4. **Weakening flags only in control jobs.** A flag that weakens a system's statement (for example SASH's `--unsound-skip-*`) is never used outside a negative-control job (RFC-0008), never to make a run pass.
5. **Never fabricate or round away results.** A failed run is recorded with its exit code and last lines. Report ranges and sample sizes, never a single best run.
6. **The commitment the verifier checks comes from the harness record**, never from files sent with a proof.
7. **No secrets, hosts or personal data.** No API keys, SSH aliases, IP addresses, account names or machine identifiers beyond the hardware record RFC-0006 asks for.
8. **No weights in the repository.** Models are referenced by public source and content hash.
9. **Claims follow the systems' own documentation.** On a claim card, copy what the system states at the pinned commit, link it, and write "not stated" where it is silent. Do not infer security properties. A quote is printed as the publisher's words; it never sets a check state.
10. **Neutral language.** Rank only by RFC-0018's order rule, inside one rung; nothing is ranked across rungs. No superlatives ("best", "fastest", "secure") and no self-description ("neutral", "independent") on the site. Describe what was measured. Say "proved", "bound", "attested" or "sampled" precisely; never "provably safe".
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
| `levels/` | frozen level definitions (`L1.yaml`) and their beacon records |
| `rfcs/` | normative decisions |
| `schema/` | JSON Schemas with valid and invalid examples |
| `harness/` | the `iproofs` package and its tests |
| `systems/<name>/` | one adapter per system |
| `workloads/`, `reference/`, `results/`, `releases/` | inputs, profiles, run records, frozen releases |
| `web/` | the static site written by `iproofs site build`, deployed by Vercel |
