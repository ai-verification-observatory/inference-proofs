# RFC-0005: Adapter contract

- Status: Draft
- Created: 2026-11-03
- Requires: RFC-0003, RFC-0004

## Summary

How a prover joins: one container image per system, built from this repository, that wraps the upstream prover unchanged and exposes five subcommands over JSON files.

## Motivation

Provers differ in language, build system, CLI and output. Some do not accept contributions (FlashProve describes itself as "a research artifact: not maintained, not accepting contributions"). The harness must work with all of them without asking any team to change its code.

## Specification

### Layout

```
systems/<name>/
  Dockerfile        pins the upstream repository by full commit hash and every toolchain by version
  entrypoint        the five subcommands
  system.yaml       name, upstream, maintainers, supported workloads, required profile
  claim.yaml        RFC-0002
  README.md         how the adapter maps each subcommand onto the upstream tools
```

### Rules

1. The adapter MUST NOT patch upstream source or change parameters beyond the options upstream documents.
2. The image MUST build from a clean checkout with no network access after dependencies are fetched, and record the digest of every input it fetched.
3. Toolchains MUST match the versions upstream documents (for FlashProve, CUDA 13.2 Update 2 and gcc 13; for SASH, the pinned Rust toolchain and CUDA 12.9).
4. The adapter MUST NOT run a configuration that weakens the claim (for example SASH's `--unsound-skip-*` flags) unless the job is a negative-control job (RFC-0008); the harness passes `"control": true` in that case.
5. The adapter MUST NOT read the commitment for verification from the prover's outputs; the harness passes it in.

### Interface

`docker run ... <image> <subcommand> /io/job.json /io/out.json`. Each subcommand exits 0 when it completed its task, whatever the verdict, and non-zero on failure.

| Subcommand | `job.json` | `out.json` |
|---|---|---|
| `info` | none | `{system, upstream_commit, image_inputs, workloads[], profile}` |
| `setup` | `{workload, shape}` | `{ready: true, logs}` |
| `commit` | `{model_dir, workload}` | `{commitment_id, verifier_files[], prover_files[], sizes}` |
| `prove` | `{commitment_id, prover_files[], prompts_file, shape, batch, control?}` | `{proofs[], claimed_outputs[], phases{...}, tokens_covered}` |
| `verify` | `{commitment_id, verifier_files[], request, claimed_output, proof}` | `{verdict, raw_exit_code, raw_last_line, seconds}` |

`verdict` is one of `accept`, `reject`, `no_verdict`, `invalid_call`. The adapter maps the upstream verifier's own signals onto these four and documents the mapping. For FlashProve: exit 0 with `YES` or `WITHIN LIMITS` is `accept` (the policy is recorded), exit 1 is `reject`, exit 5 is `no_verdict`, exits 2, 3, 4, 14 and 15 are `invalid_call`. For SASH: every segment proof accepted and the grid check passed is `accept`; any segment rejected or a failed grid check is `reject`.

### Resource limits

The harness binds the container to the profile's CPUs on the GPU's NUMA node and records the binding. Upstream advice on binding (FlashProve pins its threads only to CPUs it is allowed to use) is followed and noted in the adapter README.

## Rationale and alternatives

A container per system isolates toolchains (the first two systems need different CUDA versions). A Python plugin interface was rejected because it would force every team into one language. File-based JSON keeps adapters testable without a GPU.

## Open questions

1. Whether `prove` should stream proofs per batch so the harness can time per-batch latency.
2. A standard way for adapters to report witness-generation time separately.
