# RFC-0001: RFC format

- Status: Draft
- Authors: AbdelStark
- Created: 2026-11-03
- Target milestone: v0.1-alpha
- Requires: none
- Supersedes: none
- Discussion: pull request that introduces it

## Summary

This RFC fixes how decisions are written down: the RFC format, its numbering and its status labels, the roles named elsewhere in the corpus, and the governance files. The governance rules it held before (maintainer seats, Last call, conflict-of-interest merge rules, system inclusion and opt-out, release approval, DCO sign-off) are out for the research phase (owner decision, 2026-11-09, [rfcs/README.md](README.md)); they come back from git history when a public release needs them.

## Motivation

Methodology and load-bearing technical decisions need one place where they are stated, so code and readers can point at them.

## Goals

- Every methodology decision is written in an RFC.
- Every RFC has a stable number.

## Non-Goals

- Approval rules, votes and seat rules (out for the research phase).
- Certification of any system ([PRD §5](../docs/PRD.md#5-non-goals)).

## Proposed Design

### Roles

| Role | Definition |
|---|---|
| Maintainer | Merges pull requests and runs releases |
| System maintainer | Named by a prover team to own its adapter, claim card and row review |
| Contributor | Anyone who opens an issue or pull request |
| Relying party | Publishes targets under their own name (RFC-0009) |
| Runner | Anyone who executes jobs and submits run directories, declared in the run manifest |

### RFC format

1. An RFC copies [0000-template.md](0000-template.md) and fills the sections that apply.
2. An RFC number is the next free number when its pull request opens. Numbers are never reused.
3. The status line (Draft, Accepted, Final, Withdrawn, Superseded) is a label. It gates nothing.
4. Past results are never edited (RFC-0009 append-only rule). A methodology change relabels or reruns; it does not rewrite stored records.

### Governance files

| File | Content |
|---|---|
| `CONTRIBUTING.md` | how to open an issue and a pull request, test and CI expectations |
| `SECURITY.md` | private reporting channel for harness vulnerabilities, and the embargo rule for accepted controls (RFC-0008) |
| `CODE_OF_CONDUCT.md` | Contributor Covenant 2.1, with the enforcement contact |
| `LICENSE` | Apache-2.0, for code |
| `LICENSES/CC-BY-4.0.txt` and a note in `README.md` | CC BY 4.0, for specifications, data, results and reports |

## Alternatives Considered

None.

## Drawbacks

Without written approval rules, decisions rest on the maintainers' judgement until a public release brings the rules back.

## Conflicts of Interest

None declared.

## Migration / Rollout

None.

## Testing Strategy

None.

## Open Questions

- OPEN QUESTION Q1 (owner: AbdelStark, resolve by: 2027-03-31): the permanent name and home (organisation and domain). Default until resolved: working name "Inference Proofs" in the current repository; schema `$id` hosts are placeholders and resolution does not change validation.
- OPEN QUESTION Q3 (owner: AbdelStark, resolve by: 2026-12-01): the private reporting channel named in `SECURITY.md`. Default: the hosting platform's private vulnerability reporting feature.

## References

- [docs/PRD.md](../docs/PRD.md).
- Contributor Covenant 2.1, contributor-covenant.org.
- RFC 2119, key words for use in RFCs to indicate requirement levels.
