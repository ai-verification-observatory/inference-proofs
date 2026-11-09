# RFC-0005: Adapter contract

- Status: Draft
- Authors: AbdelStark
- Created: 2026-11-03
- Target milestone: v0.1-alpha (contract, fake systems); v0.1-beta (SASH and FlashProve adapters)
- Requires: RFC-0003, RFC-0004, RFC-0012
- Supersedes: none
- Discussion: pull request that introduces it

## Summary

A prover joins the benchmark through an adapter: one OCI image per system, built from this repository, that wraps the upstream prover unchanged at a full commit hash and exposes five subcommands (`info`, `setup`, `commit`, `prove`, `verify`) over JSON files in a mounted `/io` directory. This RFC fixes the contract version `adapter/1`: the directory layout, the `system.yaml` manifest, the exact container invocation, the typed shape of every job and result file, the proof release protocol the harness times against, path safety, verdict normalisation, and the failure behaviour the harness expects. It matters because every number in the benchmark passes through this boundary; a loose contract lets an adapter change what is measured.

## Motivation

Provers differ in language, build system, CLI and output format. Some do not accept contributions: FlashProve describes itself as "a research artifact: not maintained, not accepting contributions" (upstream README at `9e2bdd8ff5bf9c62f18263d7dac189b0400b260c`). The harness must therefore work with every system without asking any team to change its code (PRD G6, [AGENTS.md hard rule 1](../AGENTS.md#hard-rules)).

The two v0.1 systems also differ in toolchain (FlashProve documents CUDA 13.2 Update 2 and gcc 13; SASH documents a pinned Rust toolchain and CUDA 12.9), in proof granularity (one proof per request for FlashProve; a grid of segment proofs per sequence for SASH, see [RFC-0004](0004-metrics-timing-grades.md)), and in how verification signals its outcome (FlashProve exit codes; SASH per-segment results plus a `boundary-grid` check). The harness measures from outside the container ([RFC-0011](0011-measurement-and-sampling.md)), so the contract must also fix *when* a proof counts as produced, or `prove.steady` cannot be measured externally.

Scenarios this contract must support:

1. A CI job runs the full pipeline against `systems/fake` on a laptop CPU, with no GPU and no network.
2. A runner on an H100 host runs `sash-l31-8b-c4096` three times; the harness timestamps each segment proof as it appears.
3. A negative-control job ([RFC-0008](0008-negative-controls.md)) passes mutated proofs to `verify`; the adapter cannot tell a mutated proof from an honest one except by running the upstream verifier.
4. A SASH negative-control job runs with an `--unsound-skip-*` flag; outside such a job the adapter refuses the flag.

## Goals

- One contract, `adapter/1`, that both v0.1 systems, the two reference systems ([RFC-0015](0015-reference-rows.md)) and the fake systems implement without upstream changes.
- Every job and result file has a JSON Schema in `schema/adapter-job/1.schema.json` and `schema/adapter-out/1.schema.json`; the harness rejects any out.json that fails validation.
- Proof release is atomic and externally observable, so the harness can time each proof without trusting adapter clocks.
- An adapter cannot read the commitment it is verified against from its own prover outputs.
- An adapter cannot run a configuration that weakens the claim outside a control job.
- Every adapter is testable on CPU against stored fixtures.

## Non-Goals

- A Python or Rust plugin API. Adapters are containers.
- Multi-GPU or multi-node proving. v0.1 profiles have one GPU ([RFC-0006](0006-reference-hardware-and-cost.md)).
- Proof format specifications. The harness treats proof parts as opaque bytes.
- Streaming results over a socket. Files in `/io` are the only channel.
- Defining which upstream options are allowed. The upstream documentation at the pin defines that; this RFC only requires the adapter to stay inside it.

## Proposed Design

### Layout

```
systems/<name>/
  Dockerfile        pins the upstream repository by full commit hash and every toolchain by version
  entrypoint        executable implementing the five subcommands
  system.yaml       manifest (schema system/1), below
  claim.yaml        claim card (RFC-0002)
  external.yaml     upstream figures, grade external (RFC-0004), optional
  controls.yaml     system-specific negative controls (RFC-0008), optional
  README.md         mapping of each subcommand onto upstream tools, with links at the pin
  tests/            CPU-only fixture tests (INV-ADAPTER-9)
  replies/          right of reply per release (RFC-0009)
```

`<name>` matches `^[a-z][a-z0-9-]{1,31}$` ([RFC-0012](0012-schemas-and-serialization.md)).

### system.yaml

Authored YAML, validated against `schema/system/1.schema.json`. Typed shape:

```yaml
schema: "system/1"
name: "flashprove"                    # system id
kind: "prover"                        # prover | reference | test
contract: "adapter/1"
upstream:
  repo: "anthropics/FlashProve"       # owner/name on its public host
  url: "https://github.com/anthropics/FlashProve"
  commit: "9e2bdd8ff5bf9c62f18263d7dac189b0400b260c"   # 40 lowercase hex, INV-ADAPTER-2
  tag: "v0.16.0"                      # optional, informative only
image:
  repository: "ghcr.io/<org>/iproofs-flashprove"        # where the built image is pushed
  digest: "sha256:<64 hex>"           # set by the build job, INV-ADAPTER-3
maintainers:                           # system maintainers (RFC-0001); handles only
  - handle: "<github handle>"
    organisation: "<organisation>"
workloads: ["fp-maverick-w1024-b1", "fp-maverick-w1024-b24"]
profile: "prover-h100"                # required prover profile (RFC-0006)
deterministic_proofs: false           # true only if upstream documents byte-identical proofs for identical inputs and seed
incremental_proofs: true             # true when upstream releases proofs one by one during the prove call (RFC-0011)
max_proof_parts: 10000                # cap on part files per proof directory; may only be lowered
max_proof_bytes: 68719476736          # cap on bytes per part (64 GiB); may only be lowered
proofs:
  granularity: "request"              # request | sequence | segment_grid
  tokens_covered: "window"            # window | prompt_plus_output | declared_per_proof
  steady_boundary: "first_proof"      # first_proof | first_complete_sequence | not_observable
  steady_approximate: false           # true when the mapping to the upstream scope is approximate (RFC-0004)
forbidden_flags: []                   # literal argument prefixes the adapter must refuse outside control jobs
timeouts_s:                           # per-step wall limits; defaults below apply when absent
  info: 60
  setup: 3600
  commit: 14400
  prove: 43200
  verify: 3600
```

Field rules:

- Reference systems (`kind: reference`) add the fields `reference_role`, `engine` and the object form of `workloads` (each entry `{id, precision_used, precision_substitution, engine_args}`) defined in [RFC-0015](0015-reference-rows.md#reference-systems). The `system/1` schema accepts the object form only when `kind` is `reference`.

- `kind: test` is reserved for `systems/fake` and `systems/fake-broken`; CI uses them, results with `kind: test` never enter `results/<release>/`.
- `proofs.granularity` declares what one proof directory contains. `request`: one proof per request. `sequence`: one proof per sequence. `segment_grid`: one proof directory per sequence whose parts are segment proofs plus a grid check record; the proof is released when the whole grid is written (SASH, below).
- `proofs.tokens_covered` declares how the harness counts tokens covered by one proof ([RFC-0004](0004-metrics-timing-grades.md)). `window`: the window's positions. `prompt_plus_output`: prompt tokens plus generated tokens of the sequence. `declared_per_proof`: the adapter reports `tokens_covered` per proof in out.json and the harness checks it against the workload shape (INV-ADAPTER-7).
- `proofs.steady_boundary` declares where `prove.steady` starts. `first_proof` reads "the last release of the first batch" for batch size b > 1 (RFC-0004 INV-SCOPE-5, amendment of 2026-11-09). `not_observable` makes the harness report `prove.steady` as null with `null_reason: "not_externally_observable"`.
- `incremental_proofs: false` requires `proofs.steady_boundary: not_observable` (INV-ADAPTER-10): if upstream writes every proof at the end of the call, release times carry no steady-state information ([RFC-0011](0011-measurement-and-sampling.md#proof-release-watcher)).
- `max_proof_parts` and `max_proof_bytes` default to 10,000 parts and 64 GiB per part (limits, not measurements). A system may declare lower caps, never higher ones; exceeding a cap is an `adapter` failure ([Path safety](#path-safety)).
- `forbidden_flags` is matched by prefix against every argument the adapter passes to upstream tools; the adapter logs the full command line to `/io/commands.jsonl` (below) so CI can check it independently ([RFC-0013](0013-validation-and-ci.md)).
- Timeout defaults (used when `timeouts_s` omits a step): `info` 60 s, `setup` 3,600 s, `commit` 14,400 s, `prove` 43,200 s, `verify` 3,600 s. These are wall limits (targets for the harness, not measurements). A system that needs more declares it; the value is visible in review.

### Container invocation

The harness is the only caller. For every subcommand it issues the equivalent of the `docker run` below. It realises the call as `docker create` with these flags, which is not timed, followed by `docker start --attach`, which is timed ([RFC-0011](0011-measurement-and-sampling.md#timing-a-container-call)). The created container also gets `--cgroup-parent` set to a harness-owned slice, so that exact cgroup counters remain readable after the container exits ([RFC-0011](0011-measurement-and-sampling.md#cgroup-accounting)).

```
docker run --rm \
  --network none \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --pids-limit 4096 \
  --cpuset-cpus <cpu list> --cpuset-mems <numa node> \
  [--gpus device=<index>]            # info, setup, commit, prove only; never verify
  [--memory 32g]                     # verify on the verifier profile
  --tmpfs /tmp:rw,size=<profile tmp>,mode=1777 \
  [-v <model_dir>:/models:ro]       # every step except verify; a verifier never sees the weights
  -v <job io dir>:/io:rw \
  --name iproofs-<run-id>-<step> \
  <image repository>@sha256:<digest> <subcommand> /io/job.json /io/out.json
```

- The image is always referenced by digest (INV-ADAPTER-3). A tag never appears in an invocation.
- `--network none` applies to every subcommand, including `setup`. Everything an adapter needs at run time is in the image or in `/models` (INV-ADAPTER-4).
- `verify` runs without `--gpus`, with the verifier profile's cpuset (8 CPUs, or 1 CPU for `verify.single_thread`) and `--memory 32g` ([RFC-0006](0006-reference-hardware-and-cost.md)).
- Prover-side writable state that must survive between steps of one job (prover files, commitment files) lives under `/io/state/`; the harness keeps one job io dir per job and mounts it for every step of that job. `/io` of one job is never mounted into another job.
- The container runs as a non-root user declared in the Dockerfile (`USER`), uid 10001 by convention. The harness creates the io dir owned by that uid.

### Subcommands and file shapes

Each subcommand reads `/io/job.json` (written by the harness, schema `adapter-job/1`) and writes `/io/out.json` (schema `adapter-out/1`). Every job.json carries common fields:

```json
{
  "schema": "adapter-job/1",
  "contract": "adapter/1",
  "subcommand": "prove",
  "run_id": "2026-11-03-flashprove-fp-maverick-w1024-b24-prover-h100-1",
  "workload": {"id": "fp-maverick-w1024-b24", "version": 1},
  "shape": {"prompt_tokens": 1024, "output_tokens": 1, "batch_size": 24, "batches_per_session": 5, "context_window": 1024},
  "control": false
}
```

Every out.json carries common fields:

```json
{
  "schema": "adapter-out/1",
  "contract": "adapter/1",
  "subcommand": "prove",
  "phases": [{"name": "witness", "seconds": 12.5}],
  "warnings": []
}
```

`phases` holds adapter-reported timings. The harness stores them as quantities with `source.kind: "adapter"` ([RFC-0004](0004-metrics-timing-grades.md)); they never replace harness measurements.

Per-subcommand fields (in addition to the common ones):

| Subcommand | job.json | out.json |
|---|---|---|
| `info` | none | `system`, `upstream_commit`, `image_inputs[]` (`{name, url, digest}` for every input fetched at build time), `workloads[]`, `profile`, `contract_versions[]` |
| `setup` | none | `ready: true`, `log_files[]` |
| `commit` | `model_dir` (`"/models"`) | `commitment_id` (string), `verifier_files[]`, `prover_files[]` (paths under `/io/state/`), `sizes` (`{verifier_bytes, prover_bytes}`) |
| `prove` | `commitment_id`, `prover_files[]`, `model_dir`, `prompts_file` (JSONL of token id arrays under `/io/`), `batch_size`, `batches` | `proofs[]`: `{proof_id, request_index, parts[], claimed_output, tokens_covered?}`, `binding_report?` (path) |
| `verify` | `commitment_id`, `verifier_files[]`, `request` (token ids), `claimed_output` (token ids), `proof_dir` | `verdict`, `policy?`, `raw_exit_code`, `raw_last_line`, `seconds` |

Python view (informative; the schemas are normative):

```python
from typing import Literal, TypedDict

Verdict = Literal["accept", "reject", "no_verdict", "invalid_call"]

class ProofEntry(TypedDict, total=False):
    proof_id: str              # ^[a-z0-9][a-z0-9._-]{0,127}$ (RFC-0012 identifiers)
    request_index: int         # index into prompts_file, 0-based
    parts: list[str]           # file names inside /io/proofs/<proof_id>/, order significant
    claimed_output: list[int]  # token ids
    tokens_covered: int        # required iff proofs.tokens_covered == "declared_per_proof"

class VerifyOut(TypedDict):
    verdict: Verdict
    raw_exit_code: int
    raw_last_line: str         # last non-empty line of upstream verifier output, redacted, <= 4096 bytes
    seconds: float             # adapter-reported, stored as source.kind "adapter"
```

The harness passes `commitment_id` and `verifier_files` to `verify` from its own record of the `commit` step, never from anything written by `prove` (INV-ADAPTER-5, [AGENTS.md hard rule 6](../AGENTS.md#hard-rules)). The harness copies `verifier_files` from the commit step's job io dir into a fresh verify io dir; the verify container never sees `/io/state/` of the prover.

Exit status: each subcommand exits 0 when it completed its task, whatever the verdict, and non-zero when it could not. A rejected proof is exit 0 with `verdict: "reject"`.

### Proof release protocol

The harness times proofs by watching the file system, not by trusting the adapter.

1. For each proof, the adapter writes every part into `/io/proofs/.tmp-<proof_id>/`.
2. When the proof is complete, the adapter calls `rename("/io/proofs/.tmp-<proof_id>", "/io/proofs/<proof_id>")`. On one file system this is atomic.
3. The harness watches `/io/proofs/` with inotify (`IN_MOVED_TO`), falling back to a 10 ms poll where inotify is unavailable, and records `release_time` = `time.monotonic_ns()` at the event ([RFC-0011](0011-measurement-and-sampling.md)).
4. After `prove` exits, the harness reads `out.json`, checks that the set of `proof_id` values equals the set of released directories (INV-ADAPTER-6), and computes digests of every part ([RFC-0012](0012-schemas-and-serialization.md)).

When upstream writes all proofs only at the end, the adapter still releases each atomically, and `system.yaml` declares `steady_boundary: not_observable` unless release times differ meaningfully; the harness then reports `prove.steady` as null (RISK below).

### Command log

Every adapter appends one JSON line per upstream process it starts to `/io/commands.jsonl`: `{"argv": [...], "cwd": "...", "started_mono_ns": int, "exit_code": int}`. Environment variables are not logged. The harness copies this file to `logs/commands.jsonl` in the run directory and records its digest in the manifest ([RFC-0014](0014-provenance-and-integrity.md#manifestjson)); the CI policy check reads it ([RFC-0013](0013-validation-and-ci.md)).

### Path safety

Every path in job.json and out.json is an absolute path under `/io` or `/models`, or a file name relative to a named directory (`parts[]`). The harness resolves each path on the host side, rejects any that escapes the job io dir after resolving symlinks, rejects symlinks and device files inside `/io/proofs/`, and rejects any part larger than 64 GiB or any proof directory with more than 10,000 parts. A violation is an `adapter` failure with the offending path recorded (INV-ADAPTER-8).

### Verdict normalisation

`verdict` is one of `accept`, `reject`, `no_verdict`, `invalid_call`. The adapter maps the upstream verifier's own signals onto these four and documents the mapping in its README with links at the pin.

- **FlashProve:** exit 0 with `YES` or `WITHIN LIMITS` is `accept` and the policy is recorded in `policy` (`"exact-match"` or `"clipped-gap"`); exit 1 is `reject`; exit 5 is `no_verdict`; exits 2, 3, 4, 14 and 15 are `invalid_call`. Any other exit code makes the adapter exit non-zero (an `adapter` failure), never a guessed verdict.
- **SASH:** one proof is the set of segment proofs for one sequence plus the `boundary-grid` check. Every segment proof accepted and the grid check passed is `accept`; any segment rejected or a failed grid check is `reject`. Anything the upstream verifier reports that is neither is `no_verdict`, with the raw line kept. The exact segment-verifier and grid-check invocations are documented in the adapter README from upstream docs at the pin.

### Weakening configurations

The adapter MUST refuse, by exiting non-zero before starting any upstream process, any argument matching `forbidden_flags` unless job.json has `control: true`. For SASH, `forbidden_flags` contains `--unsound-skip-` (prefix match). In a control job the harness passes the flag explicitly in `control_flags[]`; the adapter adds nothing else. Results of a control job never become a measured row ([RFC-0008](0008-negative-controls.md), [RFC-0002](0002-claim-card.md)).

### Adapter README requirements

`systems/<name>/README.md` MUST document, each with a link to upstream documentation at the pinned commit:

1. The upstream tools each subcommand calls and every argument it passes.
2. The verdict mapping table.
3. How `commitment_id`, `verifier_files` and `prover_files` map onto upstream artefacts.
4. The values declared under `proofs` in `system.yaml` and why.
5. Toolchain versions and why they match upstream (FlashProve: CUDA 13.2 Update 2, gcc 13; SASH: pinned Rust toolchain, CUDA 12.9).
6. CPU binding advice from upstream and how the harness binding satisfies it (FlashProve pins its threads only to CPUs it is allowed to use).
7. Known deviations from upstream's own measuring setup (for example FlashProve commits fresh per run with `-M 1` because each run consumes batches of a leaf table).

### Reference implementations

- `systems/fake` (`kind: test`): a pure Python adapter, CPU only, no GPU. `commit` writes `commitment_id = sha256(model digest)`; `prove` writes one proof per request with two parts (`body.bin`, `tag.bin`) where `tag = HMAC-SHA256(key=commitment_id, msg=request || claimed_output || body)` and `claimed_output` is a deterministic function of the request; `verify` recomputes and returns `accept` or `reject`, and returns `invalid_call` if a part is missing or truncated below 32 bytes. It releases proofs one by one with a configurable delay so `prove.steady` is observable. It is sound for the shared controls by construction (each mutation changes an HMAC input), which makes it the positive end-to-end test.
- `systems/fake-broken` (`kind: test`): identical except `verify` always returns `accept`. CI asserts that the control suite reports accepted controls for it ([RFC-0013](0013-validation-and-ci.md)).

### Invariants

- **INV-ADAPTER-1:** No adapter patches upstream source or passes an option upstream does not document at the pin.
- **INV-ADAPTER-2:** `upstream.commit` is a full 40-character lowercase hex hash, and the Dockerfile checks out exactly that commit and verifies it with `git rev-parse HEAD`.
- **INV-ADAPTER-3:** Images are invoked only by digest; the digest is recorded in the manifest of every run.
- **INV-ADAPTER-4:** No subcommand has network access.
- **INV-ADAPTER-5:** The commitment used by `verify` comes from the harness's record of `commit`.
- **INV-ADAPTER-6:** The proofs listed in out.json equal the proof directories released, one to one.
- **INV-ADAPTER-7:** Tokens covered by a proof equal what the workload shape and `proofs.tokens_covered` imply; when declared per proof, the harness checks the declared value against the shape and records a mismatch as an `adapter` failure.
- **INV-ADAPTER-8:** No path from an adapter escapes its job io dir.
- **INV-ADAPTER-9:** Every adapter ships CPU-only tests in `systems/<name>/tests/` that run its entrypoint logic against stored fixtures (upstream outputs captured once on a GPU host), including the verdict mapping for every documented exit code.
- **INV-ADAPTER-10:** `incremental_proofs: false` implies `proofs.steady_boundary: not_observable`; the `system/1` schema enforces it with an `if`/`then` rule.
- **INV-ADAPTER-10:** A forbidden flag outside a control job makes the adapter exit non-zero before any upstream process starts.

### Failure modes

| Failure | Detection | Harness response |
|---|---|---|
| Subcommand exits non-zero | exit status | step `failed`, `adapter` failure with exit code and last 50 lines of stderr; job written as failed |
| out.json missing, not JSON, or fails `adapter-out/1` | parse and schema validation | `adapter` failure; out.json kept in `logs/` if present |
| out.json `contract` or `subcommand` mismatch | field check | `adapter` failure |
| Proof listed but not released, or released but not listed | INV-ADAPTER-6 check | `adapter` failure; released proofs are still digested and kept by digest |
| `.tmp-*` directory left after exit | directory scan | warning logged; the directory is ignored and not counted |
| Path escape, symlink, device file, oversize part | INV-ADAPTER-8 check | `adapter` failure, offending path recorded |
| Step exceeds its timeout | harness timer | `docker kill`, then `timeout` failure; no retry |
| Container OOM killed | `docker inspect` `OOMKilled` | `resource` failure |
| Verdict outside the four values | schema validation | `adapter` failure for that verify call; the control or row records `error` |
| Forbidden flag outside control | adapter exit before upstream start, and CI policy check on `commands.jsonl` | `policy` failure; the run cannot be a measured row |
| `tokens_covered` inconsistent with shape | INV-ADAPTER-7 | `adapter` failure |
| Image digest does not match `system.yaml` | `docker image inspect` before run | `integrity` failure before any step |

## Alternatives Considered

1. **Python plugin interface** (`class Adapter: def prove(...)`). Considered because it is the lowest-friction option for Python teams and avoids container start-up time. Rejected: it forces every team into one language and one process, mixes toolchains (the two v0.1 systems need different CUDA versions), and lets adapter code run inside the harness's trust boundary, where it could alter timing.
2. **Long-running gRPC or HTTP service per system.** Considered because it would allow per-request latency and streaming. Rejected for v0.1: it needs network access inside the container (conflicts with INV-ADAPTER-4), adds a protocol every team must implement, and file-based JSON already gives per-proof timing through the release protocol.
3. **Adapter-reported timings as the primary measurement.** Considered because adapters know internal phase boundaries. Rejected: the benchmark's numbers would then rest on code written by the measured party. Adapter timings are kept, labelled `source.kind: "adapter"`, and never substitute for harness measurements.
4. **Run upstream binaries directly, no adapter.** Considered because it removes a layer. Rejected: upstream CLIs differ in arguments, output and verdict signalling; the harness would grow one code path per system and lose the uniform verdict vocabulary.
5. **Let adapters produce the mutated proofs for controls.** Rejected in [RFC-0008](0008-negative-controls.md): the measured party would control its own tests.

## Drawbacks

- Container start-up adds wall time to every step. It is recorded (the `info` call time serves as an overhead estimate, [RFC-0011](0011-measurement-and-sampling.md)) and not subtracted; for steps lasting minutes it is small, for `verify` on the fake system it dominates.
- `--network none` during `setup` means an adapter cannot download anything at run time; large upstream artefacts must be baked into the image or passed as model files, which can make images large.
- The atomic release protocol requires adapters to write proofs through a temporary directory even when upstream writes elsewhere, which can mean a copy of tens of GB on SASH-sized runs (RISK: proof storage volume, about 19.8 GB of proofs for SASH's 4,096-position run, grade external, tier reported, source `sg-ai-safety-hub/zk-inference-results` at `11decec3c0b62c707618aab5deb82750b355d202`). Adapters SHOULD use `rename` within `/io` rather than copy when upstream can be pointed at `/io`.
- A contract with one GPU per container does not cover multi-GPU provers. A future contract major will.

## Conflicts of Interest

The author's affiliations and any interest in a measured system are declared in `MAINTAINERS.md` before this RFC enters Last call (RFC-0001).

## Migration / Rollout

- This RFC replaces the draft adapter contract of the initial design commit. No adapter or result exists yet, so nothing is migrated.
- `adapter/1` lands in v0.1-alpha with `systems/fake` and `systems/fake-broken`; SASH and FlashProve adapters land in v0.1-beta.
- A breaking change to job.json, out.json, the invocation or the release protocol creates `adapter/2` through a new RFC. The harness supports the current and previous contract major for one benchmark release ([09-release-and-versioning](../docs/spec/09-release-and-versioning.md)).
- Additive optional fields in `adapter-out/1` (for example a new `phases` name) do not change the contract version.

RISK: SASH proves a grid of segments; whether one proof directory per sequence (`segment_grid`) is the right unit, and where `prove.steady` starts, depends on how upstream releases segment proofs. Resolution: the SASH adapter issue confirms against upstream docs at the pin and declares `steady_boundary`; if segment release times are not observable, `not_observable` applies.

Amendment of 2026-11-09 (owner decision, RFC-0015 SRV-6 production serving): `job.json` gains `load_point` (`matched` or `high`) and `gpus` (the bound GPU count) for serving jobs, and a serving job's `batch_size` and `batches` are the run's (`batch_size_run`, `batches_per_session_run`). `steady_boundary: first_proof` reads "the last release of the first batch" for b > 1 (RFC-0004 INV-SCOPE-5). Docker serving containers are specified later, with the docker serving profiles (RFC-0006 R6). A reference adapter that exits non-zero may declare why in `/io/failure.json` (`{kind, message, evidence}`): `config` for a refusal before the engine starts (an engine environment variable the image does not set, a GPU count other than the tensor-parallel size, RFC-0015 SRV-3) or `resource` for an engine KV cache below the matched load, with the engine's own line as evidence (SRV-6). The runner records that kind, with the evidence after the stderr tail in `last_lines`; any other kind, a missing or unreadable file, or a proving system's file leaves the failure `adapter`.

## Testing Strategy

Contract tests (CPU, CI):

- `test_job_schema_examples`: every file under `schema/adapter-job/examples/valid/` validates, every file under `invalid/` fails, including a job without `contract`, a `prove` job without `commitment_id`, and a job with an absolute path outside `/io`.
- `test_out_schema_examples`: same for `adapter-out/1`, including `verdict: "maybe"` (invalid) and a proof entry with an empty `parts` list (invalid).
- `test_docker_argv_flags`: the invocation builder produces exactly the flags listed above for each subcommand; `verify` has no `--gpus` and has `--memory 32g`; every invocation has `--network none` and an `@sha256:` reference.
- `test_release_watch_orders_proofs`: a writer thread renames five `.tmp-*` directories with 50 ms gaps; the watcher records five release times in order, each within 20 ms of the rename (inotify) or 30 ms (poll fallback).
- `test_unlisted_proof_is_adapter_failure` and `test_listed_but_unreleased_is_adapter_failure`: INV-ADAPTER-6.
- `test_path_escape_rejected`: out.json with `../../etc/passwd`, an absolute path outside `/io`, and a symlink part each produce an `adapter` failure naming the path.
- `test_forbidden_flag_refused`: the fake adapter, configured with `forbidden_flags: ["--unsound-skip-"]`, exits non-zero on a job with that flag and `control: false`, and runs with `control: true`.
- `test_commitment_from_harness_record`: a fake `prove` writes a different `commitment_id` into its proof directory; `verify` still receives the commit step's value.
- `test_fake_end_to_end`: `iproofs run --system fake` produces a schema-valid run directory with a non-null `prove.steady`.
- `test_fake_broken_flagged`: the control suite reports C1 to C8 as `accepted` for `fake-broken` where applicable.

Per-adapter tests (INV-ADAPTER-9, CPU, CI):

- `systems/flashprove/tests/test_verdict_map.py`: each of exit codes 0 (with `YES`, with `WITHIN LIMITS`), 1, 2, 3, 4, 5, 14, 15 maps as documented; exit 7 (undocumented) makes the adapter exit non-zero.
- `systems/sash/tests/test_verdict_map.py`: all segments accepted and grid passed is `accept`; one segment rejected is `reject`; grid failure is `reject`.
- `systems/*/tests/test_out_json_fixture.py`: entrypoint logic run on stored upstream output fixtures produces schema-valid out.json.

GPU tests (manual runbook on a GPU host, not CI): one `prove` and `verify` of each v0.1 workload at the smallest shape, comparing out.json against the CPU fixtures' structure.

## Open Questions

- Resolved Q1: SASH writes each segment's files as soon as that segment is proved, but verifies the segments only after the loop, and the unit `boundary-grid` accepts is the sequence's whole grid. A job proves one sequence, so the benchmark's one proof is released once: the default stands, `granularity: segment_grid`, `incremental_proofs: false`, `steady_boundary: not_observable`, `prove.steady` null for SASH rows. Sources: [`systems/sash/README.md`](../systems/sash/README.md#grid-geometry-and-proof-release).
- OPEN QUESTION Q2: merged into [RFC-0014](0014-provenance-and-integrity.md#open-questions) Q2 (image registry), which owns it.
- OPEN QUESTION Q3 (owner: AbdelStark, resolve by: 2027-01-31): A standard phase name set for adapter-reported timings (for example `witness`, `commit`, `prove`, `aggregate`). Default: free names matching `^[a-z][a-z0-9_]{0,31}$`, documented per adapter README.
- OPEN QUESTION Q4 (owner: AbdelStark, resolve by: 2027-01-31): which FlashProve verifier the `verify` subcommand calls, the C++ verifier or the Lean verifier. The PRD reports about 21 s per proof on one CPU thread for the C++ verifier and about 24 minutes for the Lean verifier (grade external, tier reported, source FlashProve at 9e2bdd8f), and the claim card states soundness for the Lean verifier. Default until resolved: `verify` calls the C++ verifier and the claim card configuration names it; the Lean verifier is a second configuration with its own card if the system maintainers ask for it.

## References

- [RFC-0002 Claim card](0002-claim-card.md), [RFC-0003 Workloads](0003-workloads.md), [RFC-0004 Metrics](0004-metrics-timing-grades.md), [RFC-0006 Reference hardware](0006-reference-hardware-and-cost.md), [RFC-0008 Negative controls](0008-negative-controls.md), [RFC-0010 Harness runner](0010-harness-runner.md), [RFC-0011 Measurement](0011-measurement-and-sampling.md), [RFC-0012 Schemas](0012-schemas-and-serialization.md), [RFC-0013 CI gates](0013-validation-and-ci.md), [RFC-0015 Reference rows](0015-reference-rows.md).
- [docs/spec/02-public-api.md](../docs/spec/02-public-api.md#adapter-contract).
- FlashProve at `9e2bdd8ff5bf9c62f18263d7dac189b0400b260c`; SASH zk-inference-prover at `eb95bfa887299d1637550228d42086c27cbb2b3b`.
- OCI Image Specification v1.1; Linux `rename(2)` and `inotify(7)`.
