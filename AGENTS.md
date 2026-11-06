# AGENTS.md

Instructions for coding agents (and humans) working in this repository. Read this file, then `docs/PRD.md`, `docs/SPEC.md` and the RFCs your task touches.

## What this project is

An open, neutral benchmark for provable inference: the same models, the same reference hardware, the same timing rules, and a claim card saying what each proof establishes. It measures provers; it does not build them, rank them or certify them.

## Sources of truth, in order

1. Accepted and Final RFCs in `rfcs/`.
2. `docs/SPEC.md` and the sections under `docs/spec/`.
3. `docs/PRD.md`.
4. Draft RFCs: proposals, not rules.

If code and an Accepted RFC disagree, the RFC wins: fix the code or write an RFC.

## Hard rules

1. **Never patch a prover.** Adapters wrap upstream tools at a full commit hash. No source change, no undocumented parameter. If an adapter cannot work without a change, stop and open an issue.
2. **No number without its labels.** Every number written anywhere (code, results, docs, commit messages) carries its timing scope, grade and evidence tier (RFC-0004, RFC-0007), and its source. Never quote a rate without the workload, profile and scope.
3. **Derived numbers are computed, not typed.** If you need a ratio, add it to the derivation code so CI recomputes it.
4. **Unsound or weakening flags only in control jobs.** Any flag that weakens a system's statement (for example SASH's `--unsound-skip-*`) is a red flag outside a negative-control job (RFC-0008). Never use one to make a run pass.
5. **Never fabricate or round away results.** A failed run is recorded with its exit code and last lines. Report ranges and sample sizes, never a single best run.
6. **The commitment the verifier checks comes from the harness record**, never from files sent with a proof.
7. **No secrets, hosts or personal data.** No API keys, SSH aliases, IP addresses, account names or machine identifiers beyond the hardware record RFC-0006 asks for.
8. **No weights in the repository.** Models are referenced by public source and content hash.
9. **Claims follow the systems' own documentation.** When filling a claim card, copy what the system states at the pinned commit, link it, and write "not stated" where it is silent. Do not infer security properties.
10. **Neutral language.** No "fastest", "best", "winner", "beats". Describe what was measured. Say "proved", "bound", "attested" or "sampled" precisely; never "provably safe".

## Working practice

- One pull request per change, small. Methodology changes need an RFC (RFC-0001).
- Pin everything: full commit hashes, container digests, toolchain versions, model and prompt hashes.
- Slow work (prover builds, GPU runs) runs on a GPU host, not on a laptop. CPU-only steps (schema checks, verifier on stored proofs, adapter unit tests with fixtures) must run anywhere.
- Tests: every adapter ships a CPU-only test against stored fixtures; every schema ships valid and invalid examples; every derived metric ships a test against a hand-computed case.
- Commit messages say what changed and why, in plain words. Sign off (`git commit -s`) per the DCO. If an AI agent wrote a substantial part of a change, say so in the pull request description.

## Writing style

Plain, dense, active voice, short sentences. Define a term once (`docs/spec/10-glossary.md` holds the vocabulary). Numbers carry units and conditions. Use commas, colons or parentheses rather than dashes in prose.

## Layout

| Path | What |
|---|---|
| `docs/PRD.md` | why, for whom, scope, roadmap |
| `docs/SPEC.md` | index and executive summary of the specification corpus |
| `docs/spec/` | specification sections 00 to 10 (overview to glossary) |
| `docs/roadmap/IMPLEMENTATION.md` | the implementation issue set, by milestone |
| `rfcs/` | normative decisions; `0000-template.md` for new ones |
| `schema/` | JSON Schemas (to come, RFC-0012 catalogue) |
| `harness/` | the `iproofs` package and its tests (to come, RFC-0010) |
| `web/` | the public site (static pages from a frozen data snapshot, deployed by Vercel; placeholder results until a release exists) |
| `systems/<name>/` | one adapter per system (to come: `sash`, `flashprove`) |
| `workloads/`, `reference/`, `results/`, `site/`, `reports/` | as SPEC Section 2 |
