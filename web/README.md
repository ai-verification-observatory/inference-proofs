# Dashboard preview

The first version of the platform dashboard: a Next.js static export with the pages and display rules of [RFC-0009 §Site](../rfcs/0009-results-and-publication.md#site). Claim card before numbers (S1), unit, scope, grade, tier and source beside every number (S2), mean, sd, min, max, n and n_failed (S3), 4 significant digits with the full value in `title` (S4), alphabetical order with reader-requested sorts on separate static pages (S5), the native-division header (S6), struck-through superseded and failed runs (S7), and text labels on every colour (S9).

## Where the data comes from

[`lib/release.ts`](lib/release.ts) picks the newest `releases/<release>/index.json` (by version number) at build time and renders it: configurations, statistics, controls, targets and claim cards as frozen (RFC-0009), every number copied with its unit, scope, grade, tier and a link to its JSON Pointer in the index, never recomputed. Claim cards, workloads, targets and systems are read from the paths the index names. The status comes from `releases/<release>/release.yaml`, because the index has no draft field: the site is a release candidate under review, with a banner on every page, until the review window has closed and the freeze date has come; a missing `release.yaml` keeps it a candidate. Rows of a system whose `system.yaml` has `maintainers: []` say "system maintainers not reached"; a card with an empty `reviewed_by` says "card not reviewed by system maintainers"; rows on `prover-h100-hosted` say they ran in a hosted container. Reference rows follow the system rows they serve.

When no index exists, the pages render the mock data below, labelled mock. `npm test` runs the loader against the golden index `harness/tests/golden/index/v0.1.json`.

## What is mock and what is not (no index yet)

| Data | Source |
|---|---|
| Run repetitions, controls, targets, reproductions, release dates | mock, in [`lib/mock.ts`](lib/mock.ts); every value shows a `mock` label and the site-wide banner says so |
| Statistics and derived metrics (rates, cost per 1k tokens, proof bytes per token, overhead against serving) | computed from the mock repetitions by the RFC-0004 formulas, never typed |
| Upstream figures | `systems/*/external.yaml`, read at build time |
| Reference price and profiles | `reference/v0.1.yaml`, read at build time |
| RFC list and statuses, maintainers | `rfcs/`, `MAINTAINERS.md`, read at build time |
| Claim cards | FlashProve: the RFC-0002 example (shape only, not reviewed). SASH: coverage and flags from `systems/sash/README.md`, every other field not stated |

The pages are marked `noindex` (mock data and release candidates) so they are never indexed as results.

## Run

```
npm ci
npm run dev      # http://localhost:3000
npm test         # format, statistics, ordering and release loader checks (node --test)
npm run build    # tests, then the static export into out/
```

Node 22.18 or later (the tests run TypeScript directly). The build reads files outside `web/`, so it runs from a full checkout.

## Deploy on Vercel

Import the repository and set **Root Directory** to `web`; Vercel detects Next.js and reads [`vercel.json`](vercel.json). Keep "Include files outside the root directory" on (the default), because the build reads `../releases`, `../systems`, `../workloads`, `../targets`, `../reference`, `../rfcs` and `../MAINTAINERS.md`. Every page is prerendered HTML served from the CDN, with no server functions; only the sidebar's current-page highlight uses client JavaScript.
