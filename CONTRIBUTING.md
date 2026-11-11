# Contributing

Thank you for helping. This project measures provers; it does not build, rank or certify them. Read [AGENTS.md](AGENTS.md) (rules for every contributor, human or agent), [docs/SPEC.md](docs/SPEC.md) and the RFCs your change touches.

## Issues

- Open an issue for a bug, a question or a proposal. Say what you observed, what you expected, and the commit, image digest or run id involved.
- Do not report a vulnerability, or a verifier that accepts a tampered proof, in a public issue. Follow [SECURITY.md](SECURITY.md).

## Pull requests

- Say what changed and why, in plain words.
- A change to the methodology updates the RFC it touches ([rfcs/](rfcs/README.md)).

## Running jobs

A run may record who ran it, as declared by the runner: `iproofs run ... --runner HANDLE --runner-org ORG --affiliated SYSTEM`, or the environment variables `IPROOFS_RUNNER`, `IPROOFS_RUNNER_ORG` and `IPROOFS_RUNNER_SYSTEMS` (comma-separated). Only the handle, the organisation and system ids are recorded; never put an account name or host identifier there (AGENTS.md rule 7).

## Editing claim cards

A claim card copies what the system's documentation states at the pinned commit, with a source for every stated field and "not stated" where it is silent ([RFC-0002 §Rules](rfcs/0002-claim-card.md#rules)). `uv run iproofs validate` checks every card against its schema, its sources and the pin in `system.yaml`.

## Tests and CI

- Every adapter ships a CPU-only test against stored fixtures; every schema ships valid and invalid examples; every derived metric ships a test against a hand-computed case ([docs/spec/07-testing-strategy.md](docs/spec/07-testing-strategy.md)).
- Run the checks locally before you push: `make ci` runs the same commands as `.github/workflows/ci.yml`. The gate list is [RFC-0013](rfcs/0013-validation-and-ci.md).
- `uv run iproofs validate` runs the tree gates (schemas, cross-references, append-only results, file sizes, canonical JSON, derived recompute, labels, policy, pins, secrets) and prints one line per failure; `--format json` gives the same list for tools, and `--changed-since origin/main` adds the append-only check against a base branch.
- A test that fails intermittently is a bug: open an issue with the log, then fix the test or quarantine it within 7 days with `@pytest.mark.quarantine(issue=<n>)` ([docs/spec/07-testing-strategy.md §Flaky-test policy](docs/spec/07-testing-strategy.md#flaky-test-policy)). Nothing retries a failing test.
- Neutral language (AGENTS.md rule 10) is a rule for authors and reviewers; no gate checks it.
- GPU work runs on a GPU host, never in hosted CI.

## Licences

Code is Apache-2.0; specifications, data, results and reports are CC BY 4.0. See the licence section of [README.md](README.md). By contributing you agree that your contribution is licensed accordingly.

## Conduct

Everyone in this project follows the [Code of Conduct](CODE_OF_CONDUCT.md).
