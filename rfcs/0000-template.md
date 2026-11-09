# RFC-NNNN: Title

- Status: Draft
- Authors: handle
- Created: YYYY-MM-DD
- Target milestone: v0.1-alpha | v0.1-beta | v0.1 | later
- Requires: RFC numbers this one depends on
- Supersedes: none
- Discussion: link to the pull request or issue

Write "None." where a section has no content. Normative text uses MUST, SHOULD and MAY as defined in RFC 2119.

## Summary

One paragraph: what this RFC decides and why it matters.

## Motivation

The problem, with evidence: a run, a system's documentation at a pinned commit, a user's need, a passage of `docs/PRD.md` or a section of `docs/spec/`. Concrete scenarios.

## Goals

- Bulleted and testable.

## Non-Goals

- What this RFC explicitly does not address.

## Proposed Design

The full design, in `###` subsections:

- Public interfaces: CLI shapes, JSON Schemas in `schema/` (referenced, not copied), Python signatures, on-disk formats.
- Internal architecture: module and class responsibilities.
- Data flow and lifecycle.
- Concurrency, determinism, error propagation.
- Failure modes, each with the system's response.

Mark any part likely to be wrong with `RISK:` and the plan to resolve it.

## Alternatives Considered

For each alternative: what it is, why it was considered, why it was rejected.

## Drawbacks

What this design gives up.

## Conflicts of Interest

Any author who builds, funds or competes with a system this RFC affects says so here.

## Migration / Rollout

Effect on existing adapters, claim cards, schemas and past results; how they are migrated or relabelled; schema version changes (RFC-0012).

## Testing Strategy

Named test cases that prove the design correct: unit, property, schema example, fixture, integration, GPU-host. Specific cases, not categories.

## Open Questions

Each entry: `OPEN QUESTION Qn (owner: handle, resolve by: YYYY-MM-DD or RFC-NNNN): question. Default until resolved: ...`

## References

Specifications, prior art, papers, related RFCs, upstream documentation at pinned commits.
