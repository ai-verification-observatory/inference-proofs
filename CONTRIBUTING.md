# Contributing

Thank you for helping. This project measures provers; it does not build, rank or certify them. Read [AGENTS.md](AGENTS.md) (rules for every contributor, human or agent), [docs/SPEC.md](docs/SPEC.md) and the RFCs your change touches.

## Issues

- Open an issue for a bug, a question or a proposal. Say what you observed, what you expected, and the commit, image digest or run id involved.
- A prover team that wants its system included opens a system inclusion issue ([form](.github/ISSUE_TEMPLATE/system-inclusion.yml)) with the upstream repository, the full commit hash, the supported workloads and at least one system maintainer ([RFC-0001 §Adding and removing a system](rfcs/0001-process-and-governance.md#adding-and-removing-a-system)). A team opts out with the [opt-out form](.github/ISSUE_TEMPLATE/system-opt-out.yml).
- A peer reviewer files each objection with the [review objection form](.github/ISSUE_TEMPLATE/review-objection.yml) and links it from the review record ([RFC-0007 §Peer review before release](rfcs/0007-evidence-tiers-and-reproduction.md#peer-review-before-release)).
- Do not report a vulnerability, or a verifier that accepts a tampered proof, in a public issue. Follow [SECURITY.md](SECURITY.md).

## Pull requests

- One pull request per change, small, with a description that says what changed and why.
- Sign off every commit (`git commit -s`) under the [Developer Certificate of Origin 1.1](https://developercertificate.org/). The trailer `Signed-off-by: Your Name <you@example.org>` must match the commit's author name and email. CI rejects any other commit (gate G11, rule `DCO-1`); check before pushing with `uv run python -m iproofs.validate.dco origin/main..HEAD`, and fix a branch with `git rebase --signoff origin/main`.
- If an AI agent wrote a substantial part of the change, say so in the pull request description.
- A change to the public API, a schema or the methodology adds an entry under `Unreleased` in [CHANGELOG.md](CHANGELOG.md) (`Methodology` entries name their RFC). Releases follow [docs/runbooks/harness-release.md](docs/runbooks/harness-release.md) and [docs/runbooks/benchmark-release.md](docs/runbooks/benchmark-release.md).
- `uv run iproofs validate` also checks `MAINTAINERS.md`: every row needs a handle, role, organisation and declared interests (`none` is valid), and the seat rules INV-GOV-1 and INV-GOV-2 apply (rule ids `GOV-1` to `GOV-3`, [RFC-0001 §Roles](rfcs/0001-process-and-governance.md#roles)).
- A change that touches a system's files (`systems/<name>/`, its results, targets or replies) declares any interest in that system in the description. A maintainer with a declared interest does not merge it ([MAINTAINERS.md](MAINTAINERS.md)).
- The `merge-guard` check enforces this (INV-GOV-4, rule `GOV-5`): when a pull request touches `systems/<name>/` or `results/<release>/<name>/` and every approving maintainer declared an interest in `<name>` (in "Declared interests" or "Systems maintained"), the check fails until a maintainer without that interest approves; that maintainer merges. The check reads approvals, because the platform names the merger only after the merge. Where the check cannot run (a fork without Actions, an outage), reviewers make the same comparison by hand against [MAINTAINERS.md](MAINTAINERS.md) before merging.

## RFCs

A change that would alter a published number, a label, or which rows appear needs an RFC: copy [rfcs/0000-template.md](rfcs/0000-template.md) to the next free number and follow [RFC-0001](rfcs/0001-process-and-governance.md). Implementation pull requests may open against an RFC in Last call; they merge once it is Accepted. Code that implements an Accepted RFC needs no RFC of its own.

## Running jobs

A run records who ran it, as declared by the runner ([RFC-0007 §Tiers](rfcs/0007-evidence-tiers-and-reproduction.md#tiers)): `iproofs run ... --runner HANDLE --runner-org ORG --affiliated SYSTEM`, or the environment variables `IPROOFS_RUNNER`, `IPROOFS_RUNNER_ORG` and `IPROOFS_RUNNER_SYSTEMS` (comma-separated). Name every system you build, fund, advise or compete with under `--affiliated`. A reproduction counts only when its runner is unaffiliated: an organisation other than the original runner's and the system maintainers', and the system not in the list. An organisation left `undeclared` never counts as unaffiliated. Only the handle, the organisation and system ids are recorded; never put an account name or host identifier there (AGENTS.md rule 7).

## Editing claim cards

A claim card copies what the system's documentation states at the pinned commit ([RFC-0002 §Rules](rfcs/0002-claim-card.md#rules)). On a pull request, `uv run iproofs validate --changed-since origin/main` checks every edited card:

- Any change other than adding a review increments `card_version` by exactly 1 and resets `reviewed_by` to `[]` (`CARD-1`, `CARD-2`). A system maintainer then adds a review entry with the new `card_version`.
- A new upstream commit is a new configuration: copy the card forward to a new file instead of editing the pin (`CARD-3`, [RFC-0002 §Configuration identity](rfcs/0002-claim-card.md#configuration-identity)).

## Replies from system maintainers

Each system's maintainers may publish a reply per release ([RFC-0009 §Right of reply](rfcs/0009-results-and-publication.md#right-of-reply)):

- Write it at `systems/<name>/replies/<release>.md` and name it under `replies` in `releases/<release>/release.yaml`. A named reply file must exist (`XREF-4`).
- At most 300 words (`RPL-1`): whitespace-separated tokens of the Markdown source after removing link targets, so `[our notes](https://...)` counts two words. `uv run iproofs validate systems/` prints the count when it is over.
- The site prints the reply unedited, below the system's rows, headed "Reply from the system maintainers", with HTML escaped (emphasis, lists and links only).
- Replies are the maintainers' own words: the neutral-language lint (G8) skips them. The secrets scan (G9) still applies, and maintainers may reject a reply only for a G9 finding or content illegal to publish, saying so in the pull request.

## Tests and CI

- Every adapter ships a CPU-only test against stored fixtures; every schema ships valid and invalid examples; every derived metric ships a test against a hand-computed case ([docs/spec/07-testing-strategy.md](docs/spec/07-testing-strategy.md)).
- Run the checks locally before you push: `make ci` runs the same commands, in the same order, as `.github/workflows/ci.yml`. The full gate list is [RFC-0013](rfcs/0013-validation-and-ci.md).
- `uv run iproofs validate` runs the tree gates (schemas, cross-references, append-only results, file sizes, canonical JSON, derived recompute, labels) and prints one line per failure; `--format json` gives the same list for tools, and `--changed-since origin/main` adds the append-only check against a base branch.
- Coverage ([docs/spec/07-testing-strategy.md §Coverage](docs/spec/07-testing-strategy.md#coverage)): `make ci` and the tests job run `pytest --cov` with branch coverage, then `harness/tests/coverage_gate.py`. `iproofs.derive` and `iproofs.controls` must stay at 100 % of statements and branches; `iproofs.validate` has a floor that only rises, to 100 %. A change that leaves a branch of these modules untested fails CI. Line coverage of the whole package (target 90 %) is reported in the job summary.
- A test that fails intermittently is a bug: open an issue with the log, then fix the test or quarantine it within 7 days with `@pytest.mark.quarantine(issue=<n>)` ([docs/spec/07-testing-strategy.md §Flaky-test policy](docs/spec/07-testing-strategy.md#flaky-test-policy)). A quarantined test still runs; its failure is reported as xfail and listed in the CI job summary, without failing the check. A marker with no issue number, or older than 30 days, fails `harness/tests/repo/test_quarantine.py`. Nothing retries a failing test: rerun plugins and options are rejected.
- Gate G8 checks neutral language (AGENTS.md rule 10, [RFC-0013 §G8](rfcs/0013-validation-and-ci.md#g8-neutral-language-lint)) in `docs/`, `rfcs/`, `reports/`, `site/`, system READMEs and claim cards: no ranking or overstating word from the RFC list (`LANG-1`) and no emoji (`LANG-2`). Quote a word to mention it; a reviewed `<!-- lang-allow: <word> <reason> -->` on the line above allows one use and prints a notice.
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

Code is Apache-2.0; specifications, data, results and reports are CC BY 4.0. See the licence section of [README.md](README.md). By contributing you agree that your contribution is licensed accordingly. The exact boundary is INV-GOV-6 ([RFC-0001 §Governance files](rfcs/0001-process-and-governance.md#governance-files)); `uv run python -m iproofs.validate.licence --format json` prints the licence of every tracked file, and `test_licence.py` fails on a file under `systems/<name>/` that is neither an adapter part nor a claim card, external figures or a reply (rule `LIC-1`).

## Conduct

Everyone in this project follows the [Code of Conduct](CODE_OF_CONDUCT.md).
