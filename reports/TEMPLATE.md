# Benchmark release v<release>: report

Copy this file to `reports/<release>.md` ([RFC-0009 §Reports](../rfcs/0009-results-and-publication.md#reports)). Keep the sections below, in this order.

Every number is copied from `index.json`, carries its unit, timing scope, grade and evidence tier, and links to its row. The report computes no new number: a ratio it needs is added to the derivation code first (AGENTS.md rule 3). Use neutral language (AGENTS.md rule 10).

## What changed since the last release

Methodology changes with their RFC numbers, systems and pins added or removed, workloads, reference file and price.

## What failed

Failed runs (exit code and last lines) and unexpected control outcomes, each linked to its record.

## What the numbers do not show

Limits of the measurements, including every RISK still open in the RFCs.
