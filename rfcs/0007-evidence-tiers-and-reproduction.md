# RFC-0007: Evidence tiers

- Authors: AbdelStark
- Created: 2026-11-03
- Requires: RFC-0004, RFC-0012

## Summary

Every quantity carries a `tier` field saying who stands behind the number. Every tier the harness records is `reported`: produced by one runner and not yet checked. Peer review, reproduction records, the reproduction tolerance and an effective-tier computation at release freeze are not defined.

## Motivation

Published proving numbers are almost always reported by their authors, from scripts and records readers cannot always see ([PRD §11](../docs/PRD.md#11-risks)). FlashProve's performance page says its timed runs were made by measuring scripts that are not in the repository and that "a reader cannot check the figures on this page against" the run records. SASH publishes its run manifests, but its headline manifest records that the producing prover tree was dirty. A reader needs to know that a number is one runner's, until an independent rerun exists.

## Goals

- Every quantity carries a tier.
- Imported upstream figures keep the tier their source gives them.

## Non-Goals

- Peer review and reproduction.
- Auditing a system's security claims; tiers concern numbers, not claims.
- Ranking runners or providers.

## Proposed Design

### Tiers

| Tier | Meaning |
|---|---|
| `reported` | produced by one runner and not yet checked; the runner may be declared in the manifest |
| `peer-reviewed` | reserved |
| `reproduced` | reserved |

`run.json` and `index.json` record `reported` for every quantity the harness produces (LBL-3, RFC-0013). The schema keeps the other two values so a later release can use them without a schema change. In prose, a `reported` number is "reported", never "measured" alone without its labels.

## Alternatives Considered

None.

## Drawbacks

No number is independently checked.


## Migration / Rollout

Stored records already say `reported`; nothing is relabelled.

## Testing Strategy

- LBL-3 (RFC-0013): a `run.json` quantity with another tier fails G5.

## Decisions

None.

## References

- [docs/PRD.md](../docs/PRD.md), sections 7 and 11.
- FlashProve at `9e2bdd8ff5bf9c62f18263d7dac189b0400b260c` (performance page); SASH results at `11decec3c0b62c707618aab5deb82750b355d202` (headline manifest, dirty tree).
- [RFC-0004](0004-metrics-timing-grades.md), [RFC-0012](0012-schemas-and-serialization.md).
