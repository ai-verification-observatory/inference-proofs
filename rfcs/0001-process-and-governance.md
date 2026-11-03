# RFC-0001: Process and governance

- Status: Draft
- Created: 2026-11-03
- Requires: none

## Summary

How decisions are made, who makes them, and how conflicts of interest are handled. The benchmark is only useful if the teams it measures trust it, so the process is written down before the first number is.

## Specification

### Roles

- **Maintainers** merge pull requests and run releases. The project MUST have maintainers from at least two organisations before its first public release, and no single organisation may hold more than half of the maintainer seats once there are four or more.
- **System maintainers** are the people a prover team names to own its adapter and claim card. They review every row about their system before publication.
- **Contributors** are anyone who opens an issue or a pull request. Contributions carry a DCO sign-off (`Signed-off-by:`).
- **Relying parties** publish targets (RFC-0009) under their own names.

### RFC lifecycle

| Status | Meaning | Moves on when |
|---|---|---|
| Draft | Open for comment; may change freely | Authors ask for Last call |
| Last call | 14 days for objections | No unresolved objection from a maintainer or an affected system maintainer |
| Accepted | Normative; implementations may start | Implemented and used in a release |
| Final | Used in a release; changes only by a new RFC | |
| Withdrawn | Abandoned by its authors | |
| Superseded | Replaced by a named later RFC | |

Decisions use lazy consensus: silence during Last call is assent. An objection MUST give a reason and, where possible, an alternative. When consensus fails, maintainers vote; a simple majority decides, and the RFC records the vote.

### Conflicts of interest

- Anyone who builds, funds or competes with a measured system declares it in their RFC, in their pull requests that touch that system, and on the project's maintainers page.
- A maintainer does not merge changes to their own system's adapter, claim card or results; another maintainer does.
- Funders of compute are listed on the site and in every report, separately from conflicts, and have no editorial rights.

### Changes to methodology

A change that would alter a published number (a timing scope, a formula, a workload, a control) needs an RFC. Past results are never edited: they are relabelled with the RFC version they were produced under, and rerun if the release needs them.

## Rationale and alternatives

Ethproofs and MLPerf both show that a benchmark lives or dies on whether measured teams accept its rules. MLPerf's practice of submitters reviewing each other's results is adopted in RFC-0007. A foundation or formal consortium is premature for a project with two systems; this RFC can be superseded when one exists.

## Open questions

1. The permanent home (organisation and name).
2. Whether relying parties get a formal advisory role, or only publish targets.
