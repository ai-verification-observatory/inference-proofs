# RFC-0001: RFC format

- Authors: AbdelStark
- Created: 2026-11-03
- Requires: none

## Summary

This RFC fixes how decisions are written down: the RFC format, its numbering, the roles named elsewhere in the corpus, and the repository files.

## Motivation

Methodology and load-bearing technical decisions need one place where they are stated, so code and readers can point at them.

## Goals

- Every methodology decision is written in an RFC.
- Every RFC has a stable number.

## Non-Goals

- Certification of any system ([PRD §5](../docs/PRD.md#5-non-goals)).

## Proposed Design

### Roles

| Role | Definition |
|---|---|
| Relying party | Publishes targets under their own name (RFC-0009) |
| Runner | Anyone who executes jobs and submits run directories, declared in the run manifest |

### RFC format

1. An RFC copies [0000-template.md](0000-template.md) and fills the sections that apply.
2. An RFC number is the next free number when its pull request opens. Numbers are never reused.
3. Past results are never edited (RFC-0009 append-only rule). A methodology change relabels or reruns; it does not rewrite stored records.

### Repository files

| File | Content |
|---|---|
| `CONTRIBUTING.md` | how to open an issue and a pull request, test and CI expectations |
| `SECURITY.md` | private reporting channel for harness vulnerabilities, and the private report of accepted controls (RFC-0008) |
| `CODE_OF_CONDUCT.md` | Contributor Covenant 2.1, with the enforcement contact |
| `LICENSE` | Apache-2.0, for code |
| `LICENSES/CC-BY-4.0.txt` and a note in `README.md` | CC BY 4.0, for specifications, data, results and reports |

## Alternatives Considered

None.

## Drawbacks

None.

## Migration / Rollout

None.

## Testing Strategy

None.

## Decisions

- Q1. The working name is "Inference Proofs", in the current repository. Schema `$id` hosts do not resolve and do not change validation.
- Q3. The private reporting channel named in `SECURITY.md` is the hosting platform's private vulnerability reporting feature.

## References

- [docs/PRD.md](../docs/PRD.md).
- Contributor Covenant 2.1, contributor-covenant.org.
- RFC 2119, key words for use in RFCs to indicate requirement levels.
