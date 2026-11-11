# 01. Architecture

Part of the specification corpus indexed in [docs/SPEC.md](../SPEC.md). Normative detail lives in the RFCs linked from each section; where this document and an RFC disagree, the RFC takes precedence.

## System overview

The benchmark has four kinds of component: authored inputs (workloads, systems, reference hardware, targets), the harness that runs jobs on a host, the results tree that stores what the harness wrote, and the generators and checks that turn results into a release.

```
 authored inputs (git, reviewed)                       host (runner's machine)
 +--------------------------+                 +--------------------------------------------+
 | workloads/<id>.yaml      |                 |  iproofs run                                |
 | workloads/prompts/       |---- resolve --->|   runner state machine (RFC-0010)          |
 | systems/<name>/          |                 |   +-- measure: clock, NVML, cgroup, watcher |
 |   system.yaml claim.yaml |                 |   |        (RFC-0011)                       |
 |   Dockerfile entrypoint  |-- build image ->|   +-- docker run <image@digest> <subcmd>    |
 | reference/<release>.yaml |                 |   |        adapter container (RFC-0005)     |
 +--------------------------+                 |   +-- controls: mutate, twin, classify      |
                                              |            (RFC-0008)                       |
 model weights (public source, by hash) ----->|   /models (ro)   /io (rw)                   |
                                              +---------------------+----------------------+
                                                                    |
                                                                    v
                                     results/<release>/<system>/<run-id>/
                                       run.json manifest.json controls.json
                                       verifier/ logs/ digests.txt
                                                                    |
                           pull request: iproofs validate, derive --check (RFC-0013)
                                                                    |
                                                                    v
                        releases/<release>/release.yaml  -> iproofs release freeze -> index.json
                                                                    |
                                                                    v
                              iproofs site build -> web/ (committed)  reports/<release>.md
```

The same in prose. Authored inputs live in git and change by pull request. A runner invokes `iproofs run` on a host that meets a prover profile ([RFC-0006](../../rfcs/0006-reference-hardware-and-cost.md)). The runner resolves the workload (fetching weights from their public source and checking every file hash), checks the adapter image by digest, records the machine, and drives the adapter container through its five subcommands while measuring from outside the container. Optionally it runs the negative-control suite against the honest proofs. It writes one run directory per job under `results/`. The runner opens a pull request with those directories; CI validates them and recomputes every derived number. A release is cut by authoring `releases/<release>/release.yaml`; `iproofs release freeze` computes statistics and target evaluations into `index.json`; `iproofs site build` renders the static site in `web/` from the frozen release. Reports are written by people from the frozen data.

## Components and responsibilities

| Component | Location | Responsibility | Specified in |
|---|---|---|---|
| Schemas | `schema/<name>/<major>.schema.json` | the normative shape of every file | [RFC-0012](../../rfcs/0012-schemas-and-serialization.md) |
| Workload registry | `workloads/` | model by source, revision and digest; prompt corpus and generator; shapes; division | [RFC-0003](../../rfcs/0003-workloads.md) |
| System adapters | `systems/<name>/` | wrap one upstream prover unchanged behind `adapter/1` | [RFC-0005](../../rfcs/0005-adapter-contract.md) |
| Claim cards | `systems/<name>/claim.yaml` | what one proof establishes | [RFC-0002](../../rfcs/0002-claim-card.md) |
| Reference systems | `systems/ref-serve/`, `systems/ref-recompute/`, `workloads/serving/` | production-serving and recompute rows through the same contract; the serving weights are pinned by record (SRV-6) | [RFC-0015](../../rfcs/0015-reference-rows.md) |
| Test systems | `systems/fake/`, `systems/fake-broken/` | CPU-only toy prover and a verifier that accepts everything, for CI | [RFC-0005](../../rfcs/0005-adapter-contract.md#reference-implementations) |
| Reference hardware and cost | `reference/<release>.yaml` | profiles and price per release | [RFC-0006](../../rfcs/0006-reference-hardware-and-cost.md) |
| Harness | `harness/src/iproofs/` | run jobs, measure, write and check results, build the site | [RFC-0010](../../rfcs/0010-harness-runner.md), [RFC-0011](../../rfcs/0011-measurement-and-sampling.md) |
| Results | `results/<release>/` | append-only run directories | [RFC-0009](../../rfcs/0009-results-and-publication.md) |
| Releases | `releases/<release>/` | frozen set of runs and their statistics | [RFC-0009](../../rfcs/0009-results-and-publication.md) |
| Targets | `targets/<author>/<id>.yaml` | thresholds published by relying parties | [RFC-0009](../../rfcs/0009-results-and-publication.md#targets) |
| CI | `.github/workflows/` | the gates of RFC-0013 | [RFC-0013](../../rfcs/0013-validation-and-ci.md) |
| Site and reports | `web/` (pages written by `iproofs site build`, renderer `web/build.py`), `reports/` | publication | [RFC-0009](../../rfcs/0009-results-and-publication.md) |

## Module boundaries

The harness is one Python package, `iproofs` (distribution `inference-proofs-harness`, source in `harness/src/iproofs/`). Modules are arranged in layers. A module may import only from modules in lower layers or its own layer where stated; the import graph has no cycles (INV-ARCH-1). No test checks the table since 2026-11-10 (the module-layer test was withdrawn with the other layout checks), so it states the intent and reviewers hold it. The rule that matters in practice is INV-ARCH-6: `validate`, `derive`, `release` and `site` import nothing that needs a GPU host or an optional dependency.

| Layer | Module | Responsibility | May import |
|---|---|---|---|
| 0 | `iproofs.errors` | `ErrorKind`, `IProofsError`, `Failure` ([RFC-0010](../../rfcs/0010-harness-runner.md#error-taxonomy)) | stdlib |
| 0 | `iproofs.log` | JSON Lines logger, redaction, progress output ([05](05-observability.md)) | stdlib, `errors` |
| 1 | `iproofs.serialize` | the single JSON writer, YAML safe loading, byte-format check | `errors` |
| 1 | `iproofs.quantity` | labelled quantity and statistic types, vocabularies (units, scopes, grades, tiers) | `errors` |
| 1 | `iproofs.gguf` | GGUF header reader (local file or HTTP range reads), the ggml type table and the weight-width method `gguf-active-mean/1` ([RFC-0003](../../rfcs/0003-workloads.md#weight-bits) WB-5) | `errors` |
| 2 | `iproofs.schema` | schema registry, `$id` resolution, validation with Draft 2020-12 | `errors`, `serialize` |
| 2 | `iproofs.model` | frozen dataclasses for the documents code reads field by field (authored inputs, adapter output), load = parse, validate, construct; the documents the harness writes are trees checked against their schema ([RFC-0012 §Python loading](../../rfcs/0012-schemas-and-serialization.md#python-loading)) | `errors`, `serialize`, `quantity`, `schema` |
| 3 | `iproofs.provenance` | digests (files, models, proofs; the files of a model or a proof are hashed once each, several at a time), pin checks, machine record | layers 0 to 2 |
| 3 | `iproofs.derive` | derived metrics and statistics from stored raw quantities ([RFC-0004](../../rfcs/0004-metrics-timing-grades.md)) | layers 0 to 2 |
| 4 | `iproofs.workloads` | resolve workload, fetch model, materialise prompts | layers 0 to 3 |
| 4 | `iproofs.serving` | production-serving records: SM-1 to SM-3, `serving pin`, fetch of the publisher's release from an ungated byte-identical copy ([RFC-0015](../../rfcs/0015-reference-rows.md) SRV-6, [RFC-0014](../../rfcs/0014-provenance-and-integrity.md#model-fetch-and-verification)) | layers 0 to 3 |
| 4 | `iproofs.adapter` | job.json and out.json, `docker run` argv, io dirs, path safety, `ContainerRunner` implementations | layers 0 to 3, and `iproofs.measure` (a container call is timed where it runs, RFC-0011 T-1) |
| 4 | `iproofs.measure` | monotonic clock, NVML sampler, cgroup sampler, release watcher, proof sizes ([RFC-0011](../../rfcs/0011-measurement-and-sampling.md)) | layers 0 to 3 |
| 5 | `iproofs.controls` | mutations, honest twins, classification, `controls.json` ([RFC-0008](../../rfcs/0008-negative-controls.md)) | layers 0 to 4 |
| 5 | `iproofs.selftest` | the RFC-0011 calibration self-test (`machine-record --selftest`) | layers 0 to 4 |
| 6 | `iproofs.runner` | job state machine, timeouts, retries, crash recovery ([RFC-0010](../../rfcs/0010-harness-runner.md)) | layers 0 to 5 |
| 7 | `iproofs.validate` | every CI check ([RFC-0013](../../rfcs/0013-validation-and-ci.md)); `validate.memo` keeps, outside the repository, the results of the checks that read one file, by the sha256 of its bytes | layers 0 to 5 |
| 7 | `iproofs.release` | freeze, eligibility, statistics, target evaluation | layers 0 to 5 |
| 8 | `iproofs.site` | static site from a frozen release | layers 0 to 5, `release` |
| 9 | `iproofs.cli` | argparse entry point; translates `IProofsError` to exit codes | every module |

Boundary rules:

- **INV-ARCH-1:** no cycles and no upward imports, as above.
- **INV-ARCH-2:** only `iproofs.serialize` writes JSON or YAML files; every other module calls it.
- **INV-ARCH-3:** only `iproofs.adapter` builds container command lines; `iproofs.measure.timed_call` is the one place that starts, kills and removes the container, because the call is timed where it runs (RFC-0011 T-1).
- **INV-ARCH-4:** only `iproofs.measure` reads clocks for durations, NVML or cgroup files; the runner receives `StepResult` values.
- **INV-ARCH-5:** `iproofs.derive` is a pure function of stored documents: no clock, no file system writes, no network. CI can therefore recompute every derived number on any machine.
- **INV-ARCH-6:** optional dependencies are imported lazily inside the modules that need them (`nvidia-ml-py` in `measure`, `huggingface_hub` and `tokenizers` in `workloads`); `iproofs validate`, `derive`, `release` and `site` run with the base install only.

## Data flow

1. **Workload resolution.** `iproofs.workloads` reads `workloads/<id>.yaml`, fetches every weight file from the model's public source at the pinned revision, and checks each file's SHA-256 against the workload. It draws a fresh 64-bit job seed from `os.urandom`, materialises the prompt set from the pinned corpus with that seed, and computes the prompt set digest ([RFC-0003](../../rfcs/0003-workloads.md)). Output: a resolved workload with paths and digests, recorded in the manifest.
2. **Image and machine.** `iproofs.provenance` checks the local image digest against `system.yaml` and records the machine ([RFC-0006](../../rfcs/0006-reference-hardware-and-cost.md)); `iproofs.measure` selects the cpuset on the GPU's NUMA node.
3. **Adapter steps.** For each subcommand the runner writes `job.json`, asks `iproofs.adapter` to run the container, and receives a `StepResult` with the timed window, samples and (for `prove`) proof release times. `commit` yields the commitment record the harness keeps; `verify` receives the commitment from that record only ([RFC-0005](../../rfcs/0005-adapter-contract.md)).
4. **Controls.** `iproofs.controls` mutates copies of honest proofs and requests and runs `verify` on each with its honest twin ([RFC-0008](../../rfcs/0008-negative-controls.md)).
5. **Recording.** The runner turns raw observations into labelled quantities (`grade: measured`, `tier: reported`), calls `iproofs.derive` on the stored values, validates, and renames the staging dir into the run dir ([RFC-0010](../../rfcs/0010-harness-runner.md#writing-the-run-directory)).
6. **Review.** CI runs `iproofs validate` and `iproofs derive --check` on every changed run dir.
7. **Release.** `iproofs release freeze` reads `release.yaml`, collects the listed runs, computes statistics and target evaluations, and writes `index.json`. `iproofs site build` renders the public site into `web/` from it, the claim cards and run records it names, the criteria file and `web/_data/facts.json`; the committed pages are what Vercel serves ([RFC-0009](../../rfcs/0009-results-and-publication.md#site)).

Data never flows backwards: nothing downstream of a run dir edits it (INV-ARCH-7, append-only `results/`).

## Process and deployment model

- One runner process per host, one job per GPU at a time, sequential steps, sampler threads during timed steps ([RFC-0010](../../rfcs/0010-harness-runner.md#concurrency)).
- CPU-only commands (`validate`, `derive`, `release`, `site`, the fake system end to end) run on any machine with Python 3.12 or 3.13, including hosted CI.
- GPU jobs run on a host that meets `prover-h200` (or another declared docker profile, such as `prover-h100`): Linux kernel 5.19 or later, cgroup v2, Docker Engine 25.0 or later with the systemd cgroup driver, NVIDIA Container Toolkit 1.17 or later, and the driver pinned in `reference/<release>.yaml`. Hosted CI never runs GPU jobs.
- There is no server, database or background service. State is files in git; proofs are referenced by digest.

## Trust boundaries

Three boundaries matter: the adapter container (untrusted code from the measured party's side, isolated with no network, read-only root and dropped capabilities), files written by adapters (untrusted input to the harness, checked for path escape and size), and run directories submitted by runners (every number `reported`). The full threat model is in [06-security](06-security.md).

## RISK

- RISK: the layer rules may force small duplications (for example digest helpers needed by both `adapter` and `provenance`). Resolution: shared helpers move down to layer 1 or 3, never sideways.
- RISK: SASH's segment grid and FlashProve's per-request proofs stress the single `proofs/<proof_id>/` abstraction differently. Resolution: the `proofs` declaration in `system.yaml` ([RFC-0005](../../rfcs/0005-adapter-contract.md#systemyaml)); revisited after the first SASH adapter run.
