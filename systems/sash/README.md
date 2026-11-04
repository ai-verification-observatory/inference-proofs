# SASH zk-inference-prover

Adapter for [`sg-ai-safety-hub/zk-inference-prover`](https://github.com/sg-ai-safety-hub/zk-inference-prover) at commit `eb95bfa887299d1637550228d42086c27cbb2b3b` (RFC-0005). The subcommand mapping lands with #65; this page records what upstream states about the grid of proofs and how the benchmark counts it. Every fact links upstream at that commit, or the companion results repository `sg-ai-safety-hub/zk-inference-results` at `11decec3c0b62c707618aab5deb82750b355d202`. Where upstream is silent, this page says not stated (AGENTS.md rule 9).

## Grid geometry and proof release

### What one proof is

- One segment is "one transformer layer applied to one block of `S` token positions with a context of `C` earlier positions, or the language-model head applied to one block. A sequence is proved as a grid of such segments, and `boundary-grid` checks that the segments fit together" ([statement.md](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/docs/statement.md#L3-L6)). "Every recorded run has `S = 512`" ([GLOSSARY.md](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/GLOSSARY.md#L7-L9)).
- The context of a block is a whole number of blocks: the grid rejects a `C` that is not a multiple of `S` ([boundary.rs](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/prover/src/boundary.rs#L1285-L1305)), and the extractor refuses a ragged last block ([extract.py](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/harness/witness/extract.py#L715-L721)).
- The head is proved over the last prompt block and the generated block ([decision of 2026-09-08](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/docs/decisions/2026-09-08-the-head-is-proved-over-the-last-prompt-block.md#L5-L11), [plan.py](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/harness/witness/plan.py#L230-L238)).
- Prompt and continuation positions are proved alike: "the loop already proves a prompt chunk as readily as a decode one" ([chunks.rs](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/prover/src/chunks.rs#L63-L70)). `boundary-grid` checks a prompt position's id against the prompt and a generated position's id against the previous position's proved argmax ([boundary.rs](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/prover/src/boundary.rs#L1148-L1156)). The README's phrase "a STARK prover for the decode step" ([README.md](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/README.md#L3-L4)) predates this.

### The two v0.1 shapes

| Workload shape | Upstream geometry |
|---|---|
| 4,096 prompt + 512 continuation positions | recorded: `"context": 4096, "s": 512, "positions": 4608, "blocks": 9, "layers": 32, "segments": 290, "head_blocks": "7,8"` ([headline run config](https://github.com/sg-ai-safety-hub/zk-inference-results/blob/11decec3c0b62c707618aab5deb82750b355d202/runs/2026-09-09-headline-c4096-h100/config.json#L1-L7)); "a grid of 290 segments over 32 layers" ([decision of 2026-09-09](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/docs/decisions/2026-09-09-the-verifier-derives-the-shape-root.md#L37-L40)). 9 blocks of 32 layer segments plus 2 head segments is 290. |
| 1,024 prompt + 64 continuation positions | not stated: upstream has no run, plan or driver for this shape. Every recorded run sets the continuation to one block of `S` positions; at `S = 64` that would be 17 blocks and 546 segments, an arithmetic consequence of that convention, not an upstream statement. |

### When proofs are written

- `compose-chunks --ser-dir` writes each segment's three files (`<tag>.fixed.json`, `<tag>.claims.json`, `<tag>.proof.json`) as soon as that segment is proved ([chunks.rs](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/prover/src/chunks.rs#L570-L575), [cli.rs](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/prover/src/cli.rs#L1484-L1500)).
- The segments are verified only after the loop: "**Nothing is proved until everything is.** `rows` holds every chunk's `Composed` *and* its serialized bytes until the loop is over, because the verifier runs afterwards on purpose" ([chunks.rs](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/prover/src/chunks.rs#L73-L79)).
- `boundary-grid --verify --prompt` reads the serialized files of every segment, verifies each proof, derives each shape root from the published calibration, and checks every layer and token link and every position's id ([boundary.rs](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/prover/src/boundary.rs#L1489-L1531), [#L1445-L1477](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/prover/src/boundary.rs#L1445-L1477)). It exits 0 only when all of that holds, and 1 otherwise ([boundary.rs](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/prover/src/boundary.rs#L1120-L1124)).

## Upstream figures

The figures SASH publishes for the 4,096 + 512 shape (rates and times in its `loop` and `whole wall` scopes) are in [`external.yaml`](external.yaml), copied from `constants.json` in the results repository at `11decec3c0b62c707618aab5deb82750b355d202`, grade `external`, with the mapping to this benchmark's scopes (RFC-0004 §Mapping from upstream scopes). They are context, never inputs to a measured number (INV-MAP-1).

## Values for `system.yaml`

`system.yaml` lands with the image (#64): `system/1` requires a prover's image digest and its system maintainers, and neither exists yet. These are the values it declares, from the facts above:

```yaml
deterministic_proofs: true
incremental_proofs: false
proofs: {granularity: "segment_grid", tokens_covered: "prompt_plus_output", steady_boundary: "not_observable", steady_approximate: false}
forbidden_flags: ["--unsound-skip-", "--unsound-argmax-lax"]
```

- `proofs.granularity: segment_grid`. One proof in the benchmark's sense is a sequence's whole grid, the unit `boundary-grid` accepts or rejects, released when every segment of it is written (RFC-0005 §system.yaml).
- `proofs.tokens_covered: prompt_plus_output`. A grid proves every prompt and continuation position of its sequence, so one proof covers `prompt_tokens + output_tokens` positions: 4,608 and 1,088 for the two shapes, a function of the shape whatever the block length.
- `incremental_proofs: false` and `proofs.steady_boundary: not_observable`. A job proves one sequence, so its one grid is released once; release times carry no steady-state information, and `prove.steady` is null for SASH rows (INV-ADAPTER-10). Segment files appear one by one, but a segment is not the benchmark's proof.
- `proofs.steady_approximate: false`: no steady scope is reported.
- `deterministic_proofs: true`. Upstream gates every change on reproducing recorded proof digests on both backends: "A change that should not alter the proof reproduces the recorded digests on both backends before it merges" ([README.md](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/README.md#L60-L66)).
- `forbidden_flags`: the `--unsound-skip-` prefix and `--unsound-argmax-lax`, each of which unbinds or weakens an edge of the binding table ([statement.md](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/docs/statement.md#L19-L36), [#L153-L160](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/docs/statement.md#L153-L160)).

## Image and toolchain versions

`Dockerfile` follows upstream's own [Dockerfile](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/Dockerfile) at the pin, under the RFC-0014 build rules. Each version below is the one upstream names; none is chosen here.

| Toolchain | Version in the image | Upstream source |
|---|---|---|
| CUDA toolkit | 12.9.1 devel on Ubuntu 24.04 (`nvcc` V12.9.86), `nvidia/cuda` by digest | "CUDA 12.9 is the toolkit the recorded digests were built with" ([Dockerfile](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/Dockerfile#L1-L5)); `FROM nvidia/cuda:12.9.1-devel-ubuntu24.04` |
| gcc and g++ | 13.3 (Ubuntu 24.04), `CUDAHOSTCXX=/usr/bin/g++` | "nvcc 12.9 accepts gcc 14 or older; Ubuntu 24.04 ships gcc 13" ([Dockerfile](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/Dockerfile)) |
| Rust | `nightly-2025-07-14` (rustc 1.90.0-nightly e9182f195), the standalone tarball with the checksum static.rust-lang.org publishes | [rust-toolchain.toml](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/rust-toolchain.toml) |
| uv | 0.11.18, `ghcr.io/astral-sh/uv` by digest | `COPY --from=ghcr.io/astral-sh/uv:0.11.18` ([Dockerfile](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/Dockerfile)) |
| Python packages | `harness/uv.lock` at the pin, `uv sync --frozen --no-group cpu --group cuda` | the CUDA host's selection documented in [harness/pyproject.toml](https://github.com/sg-ai-safety-hub/zk-inference-prover/blob/eb95bfa887299d1637550228d42086c27cbb2b3b/harness/pyproject.toml) (torch from the `cu129` index) |

Build steps, as upstream: `cargo build --release --locked` for `zk-prover-simd`, then `cargo build --release --locked -p zk-prover --features cuda` for `zk-prover-cuda`, with `CUDAARCHS=90` (sm_90, the H100). Differences from upstream's Dockerfile, none of which touches upstream source (AGENTS.md rule 1):

- Rust comes from the checksummed standalone tarball instead of `rustup`, so the fetch stage checks it against `inputs.lock` (B2). `curl` is not installed, since only `rustup` needed it.
- Crates are fetched with `cargo fetch --locked` in the fetch stage and built `--offline` (B3); Cargo.lock's checksums verify them.
- The harness's CUDA torch group is installed instead of the default CPU group, as upstream documents for a CUDA host.
- The source is added with `git` at the pinned commit; the fetch stage checks `git rev-parse HEAD` (INV-ADAPTER-2) and the sha256 of `git archive --format=tar HEAD` against `inputs.lock`.
- Ubuntu packages are pinned to exact versions (PIN-5) from the archive; the Ubuntu snapshot service, which would keep them installable after an update, returned HTTP 503 for every date on 2026-11-04.
