# RFC-0001: Process and governance

- Status: Draft
- Authors: AbdelStark
- Created: 2026-11-03
- Target milestone: v0.1-alpha
- Requires: none
- Supersedes: none
- Discussion: pull request that introduces it

## Summary

This RFC fixes how decisions are made, who makes them, how conflicts of interest are declared and handled, how a system joins or leaves the benchmark, and how a release is approved. The benchmark is useful only if the teams it measures accept its rules, so the process is written down before the first number is. It also fixes the governance files every contributor relies on (`MAINTAINERS.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`), the licence split and the Developer Certificate of Origin (DCO) sign-off.

## Motivation

[PRD §4 G5](../docs/PRD.md#4-goals) requires multi-organisation maintainers, open methodology through RFCs, declared conflicts, team review before publication and right of reply. [PRD §11](../docs/PRD.md#11-risks) names two governance risks: a team objecting to its row, and the benchmark looking captured by one organisation. Both risks are cheaper to prevent with written rules than to repair after a contested release.

Concrete scenarios this RFC must decide:

1. A maintainer works for the organisation that publishes a measured system and opens a pull request that changes that system's claim card. Who merges it?
2. A prover team asks for its system to be removed two weeks before a release. What happens to its existing rows?
3. Two maintainers disagree about whether a new timing scope changes published numbers. Who decides, and how is the decision recorded?
4. A contributor opens a pull request implementing an RFC that is still in Draft. May it merge?
5. A security researcher finds that a verifier accepts a tampered proof. Where do they report it, and when does it become public?

## Goals

- Every role has a written definition, a way in and a way out.
- Every methodology decision has a recorded RFC with a status and a decision trail.
- No maintainer merges a change to their own organisation's system.
- No single organisation controls a majority of maintainer seats once there are four or more seats.
- No system is measured or published without its team's consent, and every team can opt out with a defined effect.
- A release is approved by a recorded rule, not by one person.
- Every contribution is licensed under the split stated here and carries a DCO sign-off that CI checks.

## Non-Goals

- A foundation, legal entity or formal consortium. Premature for a project with two systems.
- Funding policy beyond disclosure. Sponsors are disclosed (RFC-0009); how money is raised is out of scope.
- Certification of any system. The benchmark reports declared claims and test results ([PRD §5](../docs/PRD.md#5-non-goals)).
- The permanent name and home of the project (OPEN QUESTION Q1).

## Proposed Design

### Roles

| Role | Definition | Granted by | Removed by |
|---|---|---|---|
| Maintainer | Merges pull requests, runs releases, votes on contested decisions | Majority vote of existing maintainers, recorded in `MAINTAINERS.md` | Own resignation; or majority vote of the other maintainers after 90 days of inactivity or a Code of Conduct ruling |
| System maintainer | Named by a prover team to own its adapter, claim card and row review | The prover team, by a pull request to `MAINTAINERS.md` signed off by a person listed in the upstream repository's contributors or authors | The prover team, by pull request; or automatically when the system is removed |
| Contributor | Anyone who opens an issue or pull request | Nobody; open to all | Code of Conduct ruling only |
| Relying party | Publishes targets under their own name (RFC-0009) | Opens a pull request adding `targets/<author>/` | Own request; targets stay in history |
| Runner | Anyone who executes jobs and submits run directories | Nobody; open to all, affiliation declared in the run manifest (RFC-0007) | Not applicable |

Rules:

1. The project MUST have maintainers from at least two organisations before its first public release (INV-GOV-1).
2. Once there are four or more maintainer seats, no single organisation MAY hold more than half of them (INV-GOV-2). If a change of employment breaks INV-GOV-2, the affected maintainers have 60 days to restore it, by resignation or by electing new maintainers; until then they do not vote.
3. An individual without an organisational affiliation counts as their own organisation.
4. `MAINTAINERS.md` is the single source of truth for roles. CI checks that every handle in it has an `organisation` and a `declared_interests` entry (empty list allowed, written `none`).

`MAINTAINERS.md` entries follow this shape (Markdown table, one row per person):

```
| Handle | Role | Organisation | Systems maintained | Declared interests | Since |
|---|---|---|---|---|---|
| AbdelStark | maintainer | <organisation> | none | <list or none> | 2026-11-03 |
```

### RFC lifecycle

| Status | Meaning | Moves on when |
|---|---|---|
| Draft | Open for comment; may change freely | Authors ask for Last call in the pull request |
| Last call | 14 days for objections | No unresolved objection from a maintainer or an affected system maintainer |
| Accepted | Normative; implementations may merge | Implemented and used in a release |
| Final | Used in a release; changes only by a new RFC | |
| Withdrawn | Abandoned by its authors | |
| Superseded | Replaced by a named later RFC | |

Rules:

1. Decisions use lazy consensus: silence during Last call is assent. An objection MUST give a reason and, where possible, an alternative.
2. When consensus fails, maintainers vote. A simple majority of maintainers who vote decides, with a quorum of half of all maintainer seats rounded up. The RFC records the vote: each handle and its choice. Maintainers with a declared interest in a system that the RFC affects MAY vote, and the record marks their vote as interested.
3. Implementation pull requests MAY be opened against an RFC in Last call. They merge only once the RFC is Accepted (INV-GOV-3). Code that implements an Accepted RFC needs no RFC of its own.
4. A change to the status of an RFC is a pull request that edits only the status line and `rfcs/README.md`, merged by a maintainer who is not an author of that RFC.
5. The bootstrap set (RFC-0001 to RFC-0015) enters Last call together, after the specification pull request merges. Each RFC in the set may be objected to separately; an objection to one does not hold the others.
6. An RFC number is assigned at pull request time as the next free number. Numbers are never reused.

### Changes to methodology

A change that would alter a published number, a label, or which rows appear MUST go through an RFC. This includes timing scopes, formulas, workloads, controls, tolerance, tiers and the cost basis. Past results are never edited (RFC-0009 append-only rule): they are relabelled in the release index with the RFC versions in force when they were produced, and rerun if a later release needs them.

Changes that do not need an RFC: bug fixes in the harness that make it conform to an Accepted RFC, documentation corrections that change no normative text, new examples, new tests.

If a harness bug fix changes a published number, the fix pull request MUST say so, and the next release report lists every affected row.

### Conflicts of interest

1. Anyone who builds, funds, advises or competes with a measured system declares it in `MAINTAINERS.md` (if a maintainer or system maintainer), in the Conflicts of Interest section of every RFC they author, and in the description of every pull request that touches that system's files (`systems/<name>/`, `results/*/<name>/`, its targets or replies).
2. A maintainer MUST NOT merge a change to an adapter, claim card, run result, control registration or reply of a system in which they declared an interest (INV-GOV-4). Another maintainer does. CI enforces this by comparing the merger's handle with `MAINTAINERS.md` where the hosting platform exposes it; otherwise reviewers check it.
3. Funders of compute are listed on the site and in every report, separately from conflicts, and have no editorial rights (PRD N4).
4. An undeclared interest discovered later is recorded in `MAINTAINERS.md` with the date of discovery, and the next release report lists every decision the person voted on or merged.

### Adding and removing a system

A system is added only with the consent of its team (INV-GOV-5):

1. The team, or a contributor with the team's written consent linked from the issue, opens a "system inclusion" issue naming the upstream repository, the full commit hash, the workloads it supports and at least one system maintainer.
2. Consent is a comment on the issue by a person listed as an author or maintainer in the upstream repository at the pinned commit, or a public statement linked from it.
3. The adapter, `system.yaml` and `claim.yaml` land by pull request. The claim card follows RFC-0002 and stays unreviewed (`reviewed_by: []`) until the system maintainers review it.

A team that has published its system under an open licence and does not respond within 30 days of a documented contact attempt MAY still be measured, if the maintainers vote for it. Its rows then carry the note "system maintainers not reached" and its claim card stays unreviewed. Silence is never recorded as consent.

A team MAY opt out at any time by a pull request or an issue. Effect:

- No new runs of the system are accepted.
- Existing runs stay in `results/` (append-only); the system leaves the next release's index, and the release report states that the team opted out and when.
- Already published releases are not edited.

### Release approval

A release is approved when all of the following hold, checked in the release pull request:

1. Every listed system maintainer has had at least 14 days to review its rows and claim card (RFC-0009), counted from the day the release candidate index is published.
2. Every review objection (issue labelled with the reviewer's organisation, RFC-0007) is closed as resolved or as declined with a recorded vote.
3. Two maintainers from different organisations approve the release pull request, and neither is the sole maintainer of any system listed.
4. CI passes every gate in RFC-0013 on the frozen release.

### Governance files

| File | Content | Owner |
|---|---|---|
| `MAINTAINERS.md` | roles table above, declared interests, inactive and past maintainers | maintainers |
| `CONTRIBUTING.md` | how to open an issue, how to open a pull request, DCO, RFC process summary, test and CI expectations, the hard rules from `AGENTS.md`, AI assistance disclosure | maintainers |
| `SECURITY.md` | private reporting channel for vulnerabilities in the harness, and the embargo rule for accepted controls (RFC-0008): system security policy first, default 90 days or until upstream publishes, whichever is earlier | maintainers |
| `CODE_OF_CONDUCT.md` | Contributor Covenant 2.1, with the enforcement contact | maintainers |
| `LICENSE` | Apache-2.0, for code | |
| `LICENSES/CC-BY-4.0.txt` and a note in `README.md` | CC BY 4.0, for specifications, data, results and reports | |

Licence boundary (INV-GOV-6): files under `harness/`, `systems/*/` (except `claim.yaml`, `external.yaml` and `replies/`), `site/` templates, `schema/` and CI configuration are code (Apache-2.0). Files under `docs/`, `rfcs/`, `workloads/`, `reference/`, `results/`, `releases/`, `targets/`, `reports/`, and claim cards, external figures and replies are documents or data (CC BY 4.0). A file that does not fit either list is code.

DCO: every commit carries `Signed-off-by: Name <email>` matching the commit author (`git commit -s`). CI rejects a pull request with an unsigned commit (RFC-0013 gate 11). Pull requests where an AI agent wrote a substantial part of the change say so in the description.

### Failure modes

| Failure | Response |
|---|---|
| A maintainer merges a change to their own system | CI flags it where possible; otherwise any maintainer reverts it and it is re-merged by another; the event is noted in the next report |
| INV-GOV-2 broken by a job change | 60-day restoration window; affected maintainers do not vote meanwhile |
| Quorum not reached in a vote | The vote stays open 7 more days; if quorum still fails, the RFC stays in its current status |
| A system maintainer stops responding during a release window | The release proceeds after the 14 days; the rows carry "not reviewed by system maintainers" |
| A team objects to its row after publication | The objection is an issue; the reply mechanism (RFC-0009) applies to the next release; the published release is not edited |
| An RFC is accepted with an error | A new RFC corrects it; the old one becomes Superseded |

## Alternatives Considered

- **Benevolent dictator model.** Considered because it is fast for a small project. Rejected: it fails INV-GOV-1 by construction and is exactly the capture risk in PRD §11.
- **Foundation or formal consortium now.** Considered because it gives legal neutrality. Rejected for v0.1: the cost and delay are out of proportion with two systems. This RFC can be superseded when one exists.
- **Consensus required for every decision (no voting).** Considered because it maximises buy-in. Rejected: one objector could block any change indefinitely, including corrections.
- **Measuring any open-source system without consent.** Considered because public code is public and Ethproofs-style dashboards sometimes list systems unasked. Rejected as the default: rows on systems whose teams did not review them invite disputes the benchmark cannot settle. Kept as an exception requiring a vote, a documented contact attempt and a visible note.
- **Merging implementations of Draft RFCs.** Considered because it speeds early work. Rejected: Draft RFCs may change freely and code that encodes them silently becomes the rule. Opening such pull requests during Last call is allowed instead.

## Drawbacks

- Fourteen days of Last call plus 14 days of release review slow every methodology change.
- The consent rule means a system whose team never answers is either absent or carries a visible note, so coverage of the field is incomplete.
- INV-GOV-4 needs a second maintainer for every system-touching merge, which is a bottleneck while there are few maintainers.
- Lazy consensus favours people who follow the repository closely.

## Conflicts of Interest

The author's affiliations and any interest in a measured system are declared in `MAINTAINERS.md` before this RFC enters Last call (RFC-0001).

## Migration / Rollout

1. The specification pull request lands this RFC as Draft.
2. `MAINTAINERS.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md` and `LICENSES/CC-BY-4.0.txt` land in separate pull requests before Last call starts.
3. The bootstrap RFCs enter Last call together; Accepted RFCs unblock implementation merges.
4. INV-GOV-1 is checked at release approval for v0.1. Until then the project is in design phase and publishes no rows.

No existing results or adapters exist, so nothing is relabelled.

## Testing Strategy

- `test_maintainers_file_schema`: CI parses `MAINTAINERS.md` and fails if any row lacks a handle, role, organisation or declared interests.
- `test_seat_rule`: a unit test of the seat checker with hand-built tables: two organisations, two seats passes INV-GOV-1; four seats with three from one organisation fails INV-GOV-2; four seats with two and two passes.
- `test_dco_gate`: CI fixture with one unsigned commit fails gate 11; a signed commit passes.
- `test_licence_boundary`: a script maps every tracked file to code or data per INV-GOV-6 and fails if any file is unmapped under the listed directories.
- `test_rfc_status_index`: every `rfcs/NNNN-*.md` status line matches its row in `rfcs/README.md`.
- Manual check at each release: the release pull request carries a checklist with the four approval conditions, each linked to evidence.

## Open Questions

- OPEN QUESTION Q1 (owner: AbdelStark, resolve by: 2027-03-31): the permanent name and home (organisation and domain). Default until resolved: working name "Inference Proofs" in the current repository; schema `$id` hosts are placeholders and resolution does not change validation.
- OPEN QUESTION Q2 (owner: AbdelStark, resolve by: 2027-03-31): whether relying parties get a formal advisory role or only publish targets. Default: they only publish targets (RFC-0009).
- OPEN QUESTION Q3 (owner: AbdelStark, resolve by: 2026-12-01): the private reporting channel named in `SECURITY.md` (the hosting platform's private vulnerability reporting, or a dedicated address). Default: the hosting platform's private vulnerability reporting feature.

## References

- [docs/PRD.md](../docs/PRD.md), sections 4, 5, 7 (N4, N5) and 11.
- MLPerf submission and peer review rules (submitters review each other's results), adopted in RFC-0007.
- Ethproofs (ethproofs.org): fixed workloads, per-prover rows, targets published by a convener.
- Developer Certificate of Origin 1.1, developercertificate.org.
- Contributor Covenant 2.1, contributor-covenant.org.
- RFC 2119, key words for use in RFCs to indicate requirement levels.
- RFC-0007 (peer review), RFC-0008 (embargo), RFC-0009 (release review window, replies, targets), RFC-0013 (CI gates).
