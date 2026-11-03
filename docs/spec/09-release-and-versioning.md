# 09. Release and versioning

Status: Draft 0.1. Normative sources: [RFC-0001](../../rfcs/0001-process-and-governance.md) for governance, [RFC-0009](../../rfcs/0009-results-and-publication.md) for benchmark releases, [RFC-0012](../../rfcs/0012-schemas-and-serialization.md) for schema versions, [RFC-0005](../../rfcs/0005-adapter-contract.md) for the adapter contract.

## Four version lines

The project versions four things independently. Mixing them is the most common source of confusion, so each has its own name format.

| Line | Format | Example | What it versions |
|---|---|---|---|
| Harness | SemVer 2.0 `MAJOR.MINOR.PATCH` | `0.1.0` | the `inference-proofs-harness` package and its `iproofs` CLI |
| Schema | `<name>/<major>` | `run/1` | one document type |
| Adapter contract | `adapter/<major>` | `adapter/1` | the container interface between harness and adapters |
| Benchmark release | `v<major>.<minor>` | `v0.1` | a frozen set of runs, reference file, RFCs and claim cards |

## Harness

### Public API

The public API is: the `iproofs` CLI (subcommands, options, exit codes, stdout formats marked machine-readable), the schemas, the adapter contract and the repository file layout the CLI reads and writes. Python modules under `iproofs` are internal; importing them from outside the repository is unsupported and may break in any release.

### SemVer rules

- While `0.x`: a MINOR bump may break the public API; the CHANGELOG entry says what broke and how to migrate. A PATCH bump never changes the public API.
- From `1.0.0`: a breaking change to the public API needs a MAJOR bump and an RFC.
- A change that alters any published number for the same inputs (a formula, a timing boundary, a sampling rule) is a methodology change and needs an RFC regardless of the version bump (RFC-0001 §Changes to methodology).
- `1.0.0` is cut no earlier than the first benchmark release after v0.1 that uses the same harness major without breaking changes, so the public API has been exercised by a real release.

### Version source

The version lives in `pyproject.toml` only. `iproofs --version` prints it and the harness git commit. Every manifest records both (RFC-0014).

## Schema majors

- Additive optional changes edit the current major in place; anything else creates `schema/<name>/<major+1>.schema.json` through an RFC ([RFC-0012 §Schema versioning](../../rfcs/0012-schemas-and-serialization.md#schema-versioning)).
- The harness writes only the current major of each schema.
- The harness reads the current and previous major of each schema for at least one benchmark release after the new major lands. Reading support for an older major is removed only after a deprecation notice (below).
- Stored documents are never rewritten to a new major.

## Adapter contract major

- Every `job.json` carries `contract: "adapter/1"`. An adapter's `info` output declares the contract majors it supports.
- A breaking change to the interface (subcommands, required fields, verdict vocabulary, `/io` layout) needs an RFC and a new major.
- The harness supports the current and previous contract major for one benchmark release, so adapters have one release cycle to migrate. An adapter on a dropped major cannot be used in the next release.

## Benchmark releases

A benchmark release (`v0.1`) is cut by the freeze of [RFC-0009 §Freeze algorithm](../../rfcs/0009-results-and-publication.md#freeze-algorithm). A release pins:

- the list of run directories;
- the reference file (`reference/<release>.yaml`) by path and digest;
- the RFC commit whose `rfcs/` tree is in force;
- the harness version used for the freeze and recorded in each run's manifest;
- the schema majors of every document included;
- every adapter image digest (through the runs' manifests);
- every claim card by digest;
- the review window dates and the sponsors list.

Benchmark release numbers do not follow harness numbers. `v0.1` may be frozen with harness `0.3.2`. A release's data never changes after freeze; corrections go into the next release.

## Deprecation policy

A deprecation is announced in the CHANGELOG and in the release report of the benchmark release before removal, naming what is deprecated, the replacement and the release in which it is removed. Minimum window: one benchmark release. CLI options keep working during the window and print a warning to stderr naming the replacement.

## CHANGELOG discipline

- `CHANGELOG.md` at the repository root, Keep a Changelog 1.1 format, sections `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`, plus `Methodology` for changes that need an RFC (with the RFC number).
- Every pull request that changes the public API, a schema or the methodology adds an entry under `Unreleased`. CI does not enforce this in v0.1; reviewers do.
- Entries are plain statements of what changed; any number in an entry carries its labels (AGENTS.md rule 2).

## Release checklists

### Harness version

1. All required checks green on `main`; no quarantined test older than 30 days ([07-testing-strategy.md §Flaky-test policy](07-testing-strategy.md#flaky-test-policy); `harness/tests/repo/test_quarantine.py` fails on one).
2. Version bumped in `pyproject.toml`; CHANGELOG `Unreleased` moved under the new version with the date.
3. `uv build` produces a wheel and sdist; `uv run --isolated --with dist/*.whl iproofs --version` succeeds in a clean environment.
4. Tag `harness-v<version>` signed by a maintainer, on the release commit.
5. Branch protection and required checks reviewed against `docs/runbooks/repository-settings.md`.
6. Publishing to a package index is not part of v0.1; the wheel is attached to the tag's release notes. (OPEN QUESTION Q1 below.)

### Benchmark release

1. RFCs used by the release are Accepted (RFC-0001); their commit is named in `release.yaml`.
2. Reference file merged with price, date and pinned driver, CUDA and runtime versions.
3. All runs merged; every run eligible or listed as ineligible with reason.
4. Claim cards reviewed by system maintainers (`reviewed_by` non-empty) and listed by digest.
5. Peer reviews and reproductions merged; failed reproductions included.
6. Archived proofs uploaded, one per configuration, with `uri` and digest.
7. Candidate site and draft `index.json` built; review window opened with at least 14 days; system maintainers notified.
8. Replies merged (optional for each team); report drafted and reviewed by every listed team.
9. Window closed; `iproofs release freeze` run; `index.json` merged; tag `v<release>` on that commit.
10. Site published from the tagged commit; sponsors and conflicts pages checked against `release.yaml` and `MAINTAINERS.md`.

## Licence split

- Code (harness, adapters, site generator, CI): Apache-2.0, the repository's `LICENSE` file.
- Specifications, RFCs, documentation, data (workloads, results, release indexes, targets) and reports: CC BY 4.0 (PRD §7 N5). The README states the split; a `LICENSES/CC-BY-4.0.txt` file holds the licence text.
- Contributions carry a DCO sign-off (RFC-0001, RFC-0013 G11). No contributor licence agreement.
- Upstream provers keep their own licences; adapter images redistribute upstream code only as their licences permit (both v0.1 systems are Apache-2.0 per PRD §1).

## Open Questions

- OPEN QUESTION Q1 (owner: AbdelStark, resolve by: 2027-03-31): whether to publish the harness to a public package index. Default: no; installation from a tagged checkout with `uv sync`, since the harness is a tool for runners of this repository rather than a library.
