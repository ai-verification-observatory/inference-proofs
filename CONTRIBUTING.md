# Contributing

Thank you for helping. This project measures provers; it does not build, rank or certify them. Read [AGENTS.md](AGENTS.md) (rules for every contributor, human or agent), [docs/SPEC.md](docs/SPEC.md) and the RFCs your change touches.

## Issues

- Open an issue for a bug, a question or a proposal. Say what you observed, what you expected, and the commit, image digest or run id involved.
- A prover team that wants its system included opens a system inclusion issue with the upstream repository, the full commit hash, the supported workloads and at least one system maintainer ([RFC-0001 §Adding and removing a system](rfcs/0001-process-and-governance.md#adding-and-removing-a-system)).
- Do not report a vulnerability, or a verifier that accepts a tampered proof, in a public issue. Follow [SECURITY.md](SECURITY.md).

## Pull requests

- One pull request per change, small, with a description that says what changed and why.
- Sign off every commit (`git commit -s`) under the [Developer Certificate of Origin 1.1](https://developercertificate.org/). CI rejects unsigned commits.
- If an AI agent wrote a substantial part of the change, say so in the pull request description.
- A change to the public API, a schema or the methodology adds an entry under `Unreleased` in [CHANGELOG.md](CHANGELOG.md) (`Methodology` entries name their RFC). Releases follow [docs/runbooks/harness-release.md](docs/runbooks/harness-release.md) and [docs/runbooks/benchmark-release.md](docs/runbooks/benchmark-release.md).
- `uv run iproofs validate` also checks `MAINTAINERS.md`: every row needs a handle, role, organisation and declared interests (`none` is valid), and the seat rules INV-GOV-1 and INV-GOV-2 apply (rule ids `GOV-1` to `GOV-3`, [RFC-0001 §Roles](rfcs/0001-process-and-governance.md#roles)).
- A change that touches a system's files (`systems/<name>/`, its results, targets or replies) declares any interest in that system in the description. A maintainer with a declared interest does not merge it ([MAINTAINERS.md](MAINTAINERS.md)).

## RFCs

A change that would alter a published number, a label, or which rows appear needs an RFC: copy [rfcs/0000-template.md](rfcs/0000-template.md) to the next free number and follow [RFC-0001](rfcs/0001-process-and-governance.md). Implementation pull requests may open against an RFC in Last call; they merge once it is Accepted. Code that implements an Accepted RFC needs no RFC of its own.

## Tests and CI

- Every adapter ships a CPU-only test against stored fixtures; every schema ships valid and invalid examples; every derived metric ships a test against a hand-computed case ([docs/spec/07-testing-strategy.md](docs/spec/07-testing-strategy.md)).
- Run the checks locally before you push: `make ci` runs the same commands, in the same order, as `.github/workflows/ci.yml`. The full gate list is [RFC-0013](rfcs/0013-validation-and-ci.md).
- `uv run iproofs validate` runs the tree gates (schemas, cross-references, append-only results, file sizes, canonical JSON, derived recompute, labels) and prints one line per failure; `--format json` gives the same list for tools, and `--changed-since origin/main` adds the append-only check against a base branch.
- A test that fails intermittently is a bug: fix it or quarantine it with an issue number ([docs/spec/07-testing-strategy.md §Flaky-test policy](docs/spec/07-testing-strategy.md#flaky-test-policy)).
- GPU work runs on a GPU host, never in hosted CI.

## Hard rules

These come from [AGENTS.md](AGENTS.md) and are enforced in review and, where possible, in CI:

1. Never patch a prover. Adapters wrap upstream tools at a full commit hash.
2. No number without its labels: timing scope, grade, evidence tier and source.
3. Derived numbers are computed by code, never typed.
4. Flags that weaken a system's statement appear only in negative-control jobs.
5. Never fabricate or round away results. Record failures with their exit code and last lines.
6. The commitment a verifier checks comes from the harness record.
7. No secrets, hosts or personal data.
8. No model weights in the repository.
9. Claim cards copy what the system's own documentation states, and say "not stated" where it is silent.
10. Neutral language: describe what was measured.

## Licences

Code is Apache-2.0; specifications, data, results and reports are CC BY 4.0. See the licence section of [README.md](README.md). By contributing you agree that your contribution is licensed accordingly.

## Conduct

Everyone in this project follows the [Code of Conduct](CODE_OF_CONDUCT.md).
