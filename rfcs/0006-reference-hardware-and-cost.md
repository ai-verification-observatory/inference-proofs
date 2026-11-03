# RFC-0006: Reference hardware and cost basis

- Status: Draft
- Created: 2026-11-03
- Requires: RFC-0004

## Summary

Fixes, per release, the machine profiles on which rows are measured and the price used to turn seconds into money.

## Motivation

A proving rate means little without the machine. Both v0.1 systems publish numbers from one NVIDIA H100 80 GB, but with different host resources (FlashProve: 24 of a host's 96 CPUs and up to about 300 GB of host memory; SASH: its manifest records the GPU and CUDA version). Prices differ by provider and by month. Fixing both per release keeps rows comparable within a release.

## Specification

`reference/<release>.yaml`:

```yaml
release: v0.1
profiles:
  prover-h100:
    gpu: {model: NVIDIA H100 80GB HBM3 (SXM), count: 1}
    cpu: {cores_on_gpu_numa_node: 24, min_total: 32}
    host_memory_gb: 330
    disk: {type: local NVMe, free_gb: 500}
    os: Ubuntu 24.04 LTS
    driver: pinned per release
  verifier-cpu:
    gpu: none
    cpu: {cores: 8}
    host_memory_gb: 32
cost:
  price_per_gpu_hour_usd: <value>
  basis: on-demand list price of the named provider(s) on the named date; median if several
  date: <YYYY-MM-DD>
  grade: asserted
```

Rules:

1. Every row names its profile. A row on a larger profile names it, and its cost uses that profile's GPU count.
2. The host memory figure follows the most demanding v0.1 system's documented need (FlashProve's full-size route will not start committing below 330 GB available).
3. Every run records the actual machine (RFC-0004) and the provider. Rows from different providers within one profile are allowed; their spread is reported.
4. Costs are computed only from the release's price, never from a team's own price. A team's own cost figure may be shown as `external`.
5. CPU and host memory are not priced in v0.1; this is stated wherever cost is shown.

## Rationale and alternatives

One GPU type for v0.1 matches what both systems support. Multi-GPU profiles and newer GPUs come when a system needs them. Pricing CPU and memory was considered and deferred: it is provider-specific and small next to GPU time at these rates.

## Open questions

1. Which providers set the price basis, and how often it updates.
2. When to add a second GPU profile.
