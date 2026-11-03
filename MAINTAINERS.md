# Maintainers

The single source of truth for roles ([RFC-0001 §Roles](rfcs/0001-process-and-governance.md#roles)). Every row names an organisation and declared interests (`none` is a valid declaration). An individual without an organisational affiliation counts as their own organisation.

Rules that read this file:

- INV-GOV-1: maintainers from at least two organisations before the first public release.
- INV-GOV-2: once there are four or more maintainer seats, no organisation holds more than half of them.
- INV-GOV-4: a maintainer does not merge a change to a system in which they declared an interest.

A declared interest is any role in building, funding, advising or competing with a measured system ([RFC-0001 §Conflicts of interest](rfcs/0001-process-and-governance.md#conflicts-of-interest)).

## Maintainers

| Handle | Role | Organisation | Systems maintained | Declared interests | Since |
|---|---|---|---|---|---|
| AbdelStark | maintainer | undeclared | none | undeclared | 2026-11-03 |

`undeclared` means the person has not yet stated the fact. It is not a valid final value: the RFC Last call does not start while any row says `undeclared` (RFC-0001 §Migration / Rollout).

## System maintainers

Named by each prover team by pull request, signed off by a person listed as an author or maintainer in the upstream repository at the pinned commit ([RFC-0001 §Adding and removing a system](rfcs/0001-process-and-governance.md#adding-and-removing-a-system)).

| Handle | Role | Organisation | Systems maintained | Declared interests | Since |
|---|---|---|---|---|---|

None yet.

## Inactive and past maintainers

| Handle | Role | Organisation | Period | Reason |
|---|---|---|---|---|

None yet.
