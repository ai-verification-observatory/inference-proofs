# RFC-0014: Provenance, pinning and artifact integrity

- Status: Draft
- Authors: AbdelStark
- Created: 2026-11-03
- Target milestone: v0.1-beta
- Requires: RFC-0003, RFC-0005, RFC-0006, RFC-0012
- Supersedes: none
- Discussion: pull request that introduces it

## Summary

Every row the benchmark publishes must be rerunnable by a stranger and must be checkable against the exact inputs that produced it. This RFC fixes how inputs are pinned (commits, images, models, prompt corpora, toolchains), how adapter images are built, how weights are fetched and verified before any container sees them, what `manifest.json` records, how the harness keeps the commitment that the verifier checks against (AGENTS.md rule 6), how proofs are digested and archived, and which supply-chain threats the design answers. Signed result files are left as an open question with a default of unsigned for v0.1.

## Motivation

[RFC-0007 §Motivation](0007-evidence-tiers-and-reproduction.md#motivation) records why provenance matters for the first two systems: FlashProve's performance page states that its measuring scripts are not in the repository and that a reader cannot check the figures against the run records; SASH publishes run manifests, but its headline manifest records that the producing prover tree was dirty. A benchmark that wants to label numbers `reproduced` has to do better than both, for its own runs.

The draft specification said "pin everything" and "the commitment the verifier checks against comes from the harness's own record". Neither said how. Concrete cases this RFC must handle:

- An adapter Dockerfile clones `main` of an upstream repository; a rebuild a month later measures different code under the same row label.
- A weight file on the model host is replaced under the same revision name; a run silently proves a different model.
- A prover writes a commitment file next to its proof, and a buggy adapter passes that file to the verifier; a forged proof with a matching forged commitment is accepted.
- A reproducer cannot rerun a row because the image digest it names was never pushed.

## Goals

- Every input to a measured job is identified by an immutable reference: a 40-hex commit hash, an OCI digest, or a SHA-256 file or tree digest (RFC-0012 §Digests).
- No container sees weights, prompts or verifier keys whose digests have not been checked by the harness first.
- `manifest.json` alone, plus public sources, is enough to rerun the job.
- The commitment the verifier checks against is the one the harness recorded at the `commit` step, never one read from prover output.
- A reproducer can obtain every image a release names.

## Non-Goals

- Bit-reproducible image builds. Reproduction uses the same published image digest (RFC-0007 §Reproduction protocol), not a rebuild. Rebuild reproducibility is desirable and is recorded when it holds, but not required in v0.1.
- Cryptographic attestation of the runner's host (TEE or measured boot). Open question Q1.
- Auditing upstream code for backdoors. The benchmark pins and records; it does not certify (PRD §5).
- Hosting weights. Weights are never redistributed (AGENTS.md rule 8).

## Proposed Design

### Pin rules

| Input | Pin form | Where recorded | Checked by |
|---|---|---|---|
| Upstream source | full 40-hex commit hash | `system.yaml` `upstream.commit`, Dockerfile `ARG UPSTREAM_COMMIT`, `claim.yaml` | G7 `PIN-1` |
| Upstream source archive | `sha256:` of the source tarball the build fetched | `info` output `image_inputs`, manifest | harness at `info` |
| Base images | `<repo>@sha256:<digest>` | Dockerfile `FROM` | G7 `PIN-2` |
| Adapter image | `<registry>/<repo>@sha256:<manifest digest>` | `system.yaml` `image`, manifest | harness before every job |
| Toolchains | exact versions | Dockerfile, adapter README | G7 `PIN-5` |
| Language dependencies | lockfile with hashes (Cargo.lock with `--locked`, pip `--require-hashes`, uv.lock) | inside the image, digest in `image_inputs` | build fails on mismatch |
| Model | source, 40-hex revision, per-file digests, model digest | `workloads/<id>.yaml` | harness at resolve, G7 `PIN-3` |
| Tokenizer | part of the model file set | as above | as above |
| Prompt corpus | per-file digest and corpus digest | `workloads/prompts/corpus.yaml` | harness at resolve |
| Prompt set | prompt seed and prompt set digest | manifest | harness after materialising |
| Harness | version, git commit, dirty flag, `uv.lock` digest | manifest | harness at start |
| Host software | driver, CUDA runtime, container runtime, NVIDIA Container Toolkit versions | machine record (RFC-0006), reference file | harness against `reference/<release>.yaml` |
| CI actions | full commit hash | workflow files | G7 |

Abbreviated hashes, branch names, tags without digests and version ranges are rejected wherever a pin is required. Tags MAY appear next to a digest as information.

### Adapter image build

Each `systems/<name>/Dockerfile` follows these rules (RFC-0005 owns the adapter layout; this RFC owns the build rules):

1. **B1 Base by digest.** Every `FROM` names a digest.
2. **B2 Fetch stage.** One stage named `fetch` downloads every external input: the upstream source at the pinned commit (`ADD https://github.com/<org>/<repo>.git#<commit>` or a tarball with `ADD --checksum=sha256:<hex>`), and dependency sources through lockfiles that carry hashes. Every download is verified against a digest written in the repository (`systems/<name>/inputs.lock`, one line per input: `<name>\t<url>\tsha256:<hex>`).
3. **B3 Offline after fetch.** Every `RUN` in later stages uses `RUN --network=none`. A build step that needs network outside the fetch stage is a defect in the adapter.
4. **B4 No source changes.** The build applies no patch and runs no `sed` or equivalent over upstream source (AGENTS.md rule 1). Build flags are those the upstream documentation names.
5. **B5 Inputs record.** The final image contains `/opt/iproofs/inputs.json`, written by the build, listing every input `{name, url, digest}` and the toolchain versions. The `info` subcommand returns it as `image_inputs`.
6. **B6 Clean tree.** The build context is a clean checkout of this repository at a commit; `info` reports `adapter_commit` (this repository's commit) baked in at build time through a build argument. A build from a dirty tree sets `adapter_dirty: true`, and such an image is not eligible for a release (see §Eligibility).
7. **B7 Publication.** Images used in a release are pushed to the project's container registry, `ghcr.io/ai-verification-observatory/` (Q2), and referenced by manifest digest.

Local images that are not pushed (the fake systems in CI, adapter development) are referenced by their image ID and recorded with `image.digest_kind: "config"`; pushed images record `image.digest_kind: "manifest"`. Only `manifest` images are eligible for a release.

### Model fetch and verification

`iproofs fetch-model WORKLOAD` and the `resolved` state of every job (RFC-0010) run the same procedure:

```python
def ensure_model(workload: Workload, cache: Path) -> VerifiedModel:
    """Return a read-only directory whose file set and digests equal workload.model.
    Raises IProofsError(kind=integrity) on any mismatch, kind=fetch after 3 failed attempts."""
```

1. Target directory: `$IPROOFS_CACHE/models/<model digest hex>/`. `IPROOFS_CACHE` defaults to `~/.cache/iproofs`.
2. If absent, download with `huggingface_hub.snapshot_download(repo_id=source, revision=<40-hex>, allow_patterns=<exact file list>)` into a temporary sibling directory. Fetch errors retry per RFC-0010 (3 attempts, backoff 2 s, 8 s, 32 s).
3. Hash every file. The file set MUST equal the workload's list exactly: a missing file, an extra file or a digest mismatch is `ErrorKind.integrity`, and the temporary directory is deleted.
4. Compute the model digest (RFC-0012) and compare with `workload.model.digest`.
5. Rename into place, then remove write permission from every file and directory.
6. At the start of every job, rehash every file in the cache directory and recompare. This costs time outside every timed scope; the duration is logged as the diagnostic event `integrity.model_rehash` in `logs/harness.jsonl` and is not a published number. A cache entry that fails the rehash is moved to `$IPROOFS_CACHE/quarantine/` and the job fails with `ErrorKind.integrity`; it does not silently refetch, because a changed file on a runner's disk is an event the runner must see.

Gated models: the runner accepts the model licence with their own account. The token is read only from the environment variable `HF_TOKEN`, passed to the fetch call, never written to any file, log or record, and never passed into an adapter container (docs/spec/06-security.md).

The model directory is mounted read-only at `/models` in `commit` and `prove` containers and never in `verify` containers. The reference systems ([RFC-0015](0015-reference-rows.md)) skip `commit` and `verify`; `ref-recompute` reads the weights in its `prove` step, which is where its recompute work is timed.

### Corpus fetch

`workloads/prompts/corpus.yaml` lists each corpus file with `id`, `source_url`, `licence` and `sha256` (RFC-0003). The harness downloads each file into `$IPROOFS_CACHE/corpus/<digest hex>`, checks the digest, and computes the corpus digest. Any mismatch is `ErrorKind.integrity`. Prompt materialisation (RFC-0003) reads only verified corpus files.

### The commitment record

AGENTS.md rule 6: the commitment the verifier checks comes from the harness record, never from files sent with a proof.

1. After `commit` exits 0, the harness validates `out.json` and copies each file in `verifier_files[]` and `prover_files[]` from the commit container's `/io` into a harness-owned store `<job tmp>/commitment/`, which no later container mounts read-write.
2. It records in `manifest.json` under `commitment`: `commitment_id` (string, as returned), and for each verifier and prover file `{name, digest, bytes}`.
3. For `prove`, the harness mounts `commitment/prover/` read-only and passes `commitment_id` and the prover file names in `job.json`.
4. For every `verify` call, the harness creates a fresh `/io` containing only: `job.json`, a read-only copy of `commitment/verifier/` whose file digests it rechecks against the manifest immediately before the call, the request, the claimed output, and the proof's part files. `commitment_id` in `job.json` is copied from the manifest, not from `prove` output.
5. If `prove`'s `out.json` contains any key named `commitment_id` or any file whose digest equals a recorded verifier file, the harness records a `policy` warning in the run log and in `run.json` `warnings[]`; it does not fail the run, because some systems may legitimately echo the identifier, but the verify call still uses only the recorded commitment.
6. Control C3 (RFC-0008) supplies a different recorded commitment through the same path, which is the only way a commitment other than the job's own reaches a verifier.

### manifest.json

`schema/manifest/1.schema.json`. Everything needed to rerun, and nothing that identifies the host beyond RFC-0006's machine record.

```json
{
  "schema": "manifest/1",
  "run_id": "2026-12-02-sash-sash-l31-8b-c4096-prover-h100-1",
  "release": "v0.1",
  "control": false,
  "harness": {"version": "0.1.0", "git_commit": "<40 hex>", "git_dirty": false, "lock_digest": "sha256:...", "nonconforming": false},
  "runner": {"handle": "<declared handle>", "organisation": "<organisation>", "affiliated_systems": []},
  "claim": {"system": "sash", "configuration": "default", "card_version": 1},
  "provider": "<declared provider name>",
  "system": {
    "name": "sash",
    "system_manifest_digest": "sha256:...", "claim_digest": "sha256:...",
    "upstream": {"repo": "sg-ai-safety-hub/zk-inference-prover", "commit": "eb95bfa887299d1637550228d42086c27cbb2b3b"},
    "adapter_commit": "<40 hex>", "adapter_dirty": false,
    "image": {"ref": "<registry>/<repo>@sha256:...", "digest_kind": "manifest"},
    "image_inputs": [{"name": "upstream-source", "url": "...", "digest": "sha256:..."}]
  },
  "workload": {
    "id": "sash-l31-8b-c4096", "version": 1, "file_digest": "sha256:...",
    "model": {"source": "...", "revision": "<40 hex>", "digest": "sha256:..."},
    "corpus_digest": "sha256:...", "prompt_seed": "0x1f2e3d4c5b6a7988", "prompt_set_digest": "sha256:..."
  },
  "profile": {"prover": "prover-h100", "verifier": "verifier-cpu", "verifier_host": "same_as_prover",
              "reference_file": "reference/v0.1.yaml", "reference_digest": "sha256:..."},
  "machine": {"...": "RFC-0006 machine record"},
  "self_test": {"passed": true, "checks": [{"name": "ST-SAMPLER", "passed": true}, {"name": "ST-CGROUP", "passed": true}, {"name": "ST-WATCH", "passed": true}, {"name": "ST-NVML", "passed": true}]},
  "commands": [
    {"step": "commit", "argv": ["docker", "run", "..."], "cpuset": "0-23", "mems": "0", "gpus": "device=0",
     "network": "none", "started_at": "2026-12-02T09:14:03Z", "exit_code": 0}
  ],
  "commitment": {"commitment_id": "...", "verifier_files": [{"name": "...", "digest": "sha256:...", "bytes": 0}],
                 "prover_files": [{"name": "...", "digest": "sha256:...", "bytes": 0}]},
  "proofs": [{"proof_id": "...", "digest": "sha256:...", "parts": [{"name": "...", "digest": "sha256:...", "bytes": 0}],
              "archive": null}],
  "warnings": []
}
```

`runner.affiliated_systems` lists every system whose authors the runner is affiliated with, as the runner declares it; RFC-0007 tier rules read it. `self_test` is the result of the machine self-test, which runs on the host before its first run of a release and before each run campaign (RFC-0011), not before every job: `iproofs machine-record --selftest` keeps the host's latest result in `results/.selftest.json`, and the runner copies it into every manifest when the same harness version took it (otherwise `self_test` is `{passed: false, checks: []}` and the run is ineligible). Check names are the RFC-0011 ids (`ST-CLOCK` to `ST-OOM`). A job on a host whose last self-test failed stops with `ErrorKind.environment` unless `--allow-nonconforming` was given, in which case `harness.nonconforming` is `true` and the run is refused by RFC-0013 `POL-4`. `claim` names the claim card in force by `card_version`. For reference systems `commitment` is `null` and `proofs` lists their outputs as recorded by RFC-0015. `bytes` values are structural integers on the G5 allowlist; the sizes as metrics are quantities in `run.json`. `prompt_seed` is a 64-bit value written as `0x` plus 16 lowercase hex digits, a string, so JSON readers without 64-bit integers cannot corrupt it. `argv` is recorded after redaction (environment values are never in argv; the harness passes secrets only through the fetch call, which runs in the harness process).

### Proof digests and archive

- Every proof directory gets a proof digest (RFC-0012) as soon as the harness sees its rename. The digest goes into `manifest.proofs[]` and `digests.txt` (`<proof_id>\t<digest>` per line, sorted by proof id bytes).
- The harness rechecks the proof digest immediately before each `verify` call and each control mutation, so a proof changed on disk between prove and verify is detected (`ErrorKind.integrity`).
- One proof per configuration (system, workload, profile, release) is archived in full: the first honest proof of repetition 1 that verified `accept`. The archive is a POSIX ustar tar of the proof directory with entries sorted by name, mtime 0, uid and gid 0, mode 0644, no compression, so the archive digest is stable. `manifest.proofs[].archive` records `{uri, digest, bytes}` once uploaded; until then `null`.
- No proof bytes are committed to git (RFC-0009 §Storage). Other proofs are kept by digest only and MAY be deleted from the runner's disk after controls complete.
- Hosting is RFC-0009 Q1, resolved: a public dataset repository on the Hugging Face Hub, with URIs pinned to the dataset commit. `manifest.proofs[].archive` holds that URI (`manifest/1`); the archive's digest and size stay in `digests.txt` and the tar. The release cannot freeze without an archive URI for each configuration.

### Eligibility

A run is eligible for a release (RFC-0009 freeze) only if: `self_test.passed` is true, `harness.nonconforming` is false, the claim card named in `claim` is the one the release lists, `harness.git_dirty` is false, `system.adapter_dirty` is false, `image.digest_kind` is `manifest`, every pin in the manifest is in full form, the image digest equals `system.yaml`'s image at the release's adapter commit, and a prover's image is in the project's registry (B7). A run that fails eligibility stays in `results/` (append-only) and is shown, if at all, as ineligible with the reason. Upstream results with a dirty or unknown tree enter only as `external` quantities (RFC-0007 §Clean builds).

### Supply-chain threats and responses

| Threat | Response |
|---|---|
| Upstream force-push or deletion makes the pinned commit unavailable | The upstream source archive digest is recorded at build; the release archive keeps a copy of each upstream source tarball next to the archived proofs, under the upstream licence (both v0.1 systems are Apache-2.0 per PRD §1) |
| Base image tag moved | `FROM` by digest (B1) |
| Dependency registry serves different bytes | Lockfiles with hashes; build fails |
| Harness dependency compromised | `uv.lock` with hashes, `uv sync --frozen`; dependency updates are their own pull requests with the lock diff reviewed |
| Malicious or careless adapter change | Review by a maintainer other than the system's (RFC-0001); container hardening (docs/spec/06-security.md); controls catch a verifier that accepts everything (RFC-0008) |
| Model host replaces a file under the same revision | Per-file digests checked on fetch and before every job |
| CI action compromised | Actions pinned by commit; `contents: read` permissions (RFC-0013) |
| Image registry loses an image | Release freeze checks every image digest is pullable; release archive lists digests; images are not garbage collected (registry retention set to keep tagged release images) |
| Commitment substituted through prover output | §The commitment record |

### Failure modes

| Failure | Response |
|---|---|
| Pinned upstream commit not fetchable at build | Build fails in `fetch` stage; adapter issue opened; no row |
| Model digest mismatch | `integrity`, job stops before any container runs; cache entry quarantined |
| Verifier file digest changed before verify | `integrity`, that verify call is not made; the job's verify step fails and is recorded |
| Image digest not pullable | `fetch` after retries; job fails at `image_ready` |
| `info` `upstream_commit` differs from `system.yaml` | `integrity`, job stops at `info` |
| Dirty harness tree | job runs and is recorded with `git_dirty: true`; ineligible for a release |

## Alternatives Considered

**Rebuild images for reproduction instead of reusing digests.** Considered because it tests the build as well as the run. Rejected as the requirement because GPU toolchain builds are rarely bit-reproducible (timestamps, compiler nondeterminism), so a rebuild mismatch would block reproductions for reasons unrelated to the numbers. Rebuild comparison is recorded as information when a reproducer does it.

**Trust the model cache after the first check.** Considered because rehashing about 200 GB of weights per job costs minutes. Rejected because the cost is outside timed scopes and small next to proving times, and a silent on-disk change would invalidate every subsequent row.

**Let the adapter read the commitment from its own commit output.** Considered because it is simpler for adapters. Rejected: it makes rule 6 depend on every adapter being correct; the harness-owned store makes it structural.

**Signed result files from the start.** Considered because signatures make reproduction cheaper to trust (PRD open question 4). Deferred: a signature proves who wrote a file, not that the numbers are right, and key management for volunteer runners needs its own design. Q1.

**Archive every proof.** Considered for completeness (N2). Rejected for v0.1 by volume: SASH's 4,096-context run totals 19.8 GB of proofs (290 segments; grade external, tier reported, source `zk-inference-results` at `11decec3c0b62c707618aab5deb82750b355d202`, as cited in PRD §1), times three repetitions per configuration. One per configuration plus digests for all keeps the evidence checkable.

## Drawbacks

- Image publication requires a registry the project controls and pays for, before the permanent home is settled.
- Rehashing weights adds minutes of wall time per job on the runner.
- The fetch-stage discipline (B2, B3) makes adapter Dockerfiles longer and slower to write than a plain `git clone && make`.
- Unsigned results mean a fabricating runner is caught only by reproduction (docs/spec/06-security.md residual risks).

## Conflicts of Interest

The author's affiliations and any interest in a measured system are declared in `MAINTAINERS.md` before this RFC enters Last call (RFC-0001).

## Migration / Rollout

No adapters or results exist yet. Order: manifest schema and the commitment store with the fake systems (v0.1-alpha, since G10 exercises them), then model fetch and verification, build rules B1 to B7 in the SASH and FlashProve adapters, registry publication and archive upload (v0.1-beta). The eligibility rule takes effect at the first freeze (v0.1).

## Testing Strategy

- `harness/tests/unit/test_fetch.py::test_extra_file_rejected`, `::test_missing_file_rejected`, `::test_digest_mismatch_quarantines`, `::test_cache_rehash_detects_change` (flip a byte in a cached fixture model, expect `integrity` and the quarantine move), `::test_token_never_logged` (set `HF_TOKEN`, run a fetch against a local fake hub, grep every written file for the token).
- `test_commitment.py::test_verify_io_contains_only_recorded_commitment` (fake adapter whose prove writes a forged `commitment_id` and a forged key file; assert the verify job's `/io` has the recorded ones and a warning is logged), `::test_verifier_file_changed_before_verify_fails`.
- `test_manifest.py::test_manifest_round_trip_valid` against the schema, `::test_failed_self_test_ineligible`, `::test_reference_run_has_null_commitment`, `::test_prompt_seed_is_hex_string`, `::test_dirty_harness_marks_ineligible`.
- `test_archive.py::test_tar_is_deterministic` (archive the same directory twice with different mtimes and creation order, same digest).
- `test_proof_digest.py::test_changed_part_detected_before_control`.
- Adapter build checks (per system, CPU only, in `systems/<name>/tests/`): `test_dockerfile_rules.py` parses the Dockerfile and asserts B1, B3 (every `RUN` outside `fetch` has `--network=none`) and that `inputs.lock` covers every `ADD` in the fetch stage.
- G10 end-to-end run asserts the manifest of each fake run validates and that `commitment` digests match the files used at verify.

## Open Questions

- OPEN QUESTION Q1 (owner: AbdelStark, resolve by: 2027-03-31, or a later RFC): whether runners sign `run.json` and `manifest.json` (for example with a key bound to an attested runner), and with which scheme. Default for v0.1: unsigned; trust comes from reproduction (RFC-0007).
- Resolved Q2: the default holds. Release images live in `ghcr.io/ai-verification-observatory/`, the container registry of the organisation that hosts the source. They are kept indefinitely: a digest that a release references is never deleted or overwritten, and lookups never go by tag. Release freeze refuses a prover run whose image is elsewhere (eligibility reason `image_not_in_project_registry`). A reference engine image (RFC-0015) is an upstream artifact pinned by digest at its publisher's registry, like upstream source, and B7 does not apply to it.
- OPEN QUESTION Q3 (owner: AbdelStark, resolve by: 2027-01-31): whether the release archive may store upstream source tarballs for systems whose licence does not permit redistribution. Default: v0.1 systems are Apache-2.0 (PRD §1), so yes for v0.1; a future system with a restrictive licence records the digest only.

## References

- AGENTS.md rules 1, 6, 7 and 8, and working practice "Pin everything".
- [RFC-0003](0003-workloads.md), [RFC-0005](0005-adapter-contract.md), [RFC-0006](0006-reference-hardware-and-cost.md), [RFC-0007](0007-evidence-tiers-and-reproduction.md), [RFC-0008](0008-negative-controls.md), [RFC-0009](0009-results-and-publication.md), [RFC-0012](0012-schemas-and-serialization.md), [RFC-0013](0013-validation-and-ci.md).
- OCI Image Specification, image manifest and digests.
- Docker BuildKit `ADD --checksum` and `RUN --network`.
- SLSA build provenance levels, as background for the inputs record.
