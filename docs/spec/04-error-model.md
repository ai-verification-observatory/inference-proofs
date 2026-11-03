# 04. Error model

Status: Draft 0.1, part of the specification corpus indexed in [docs/SPEC.md](../SPEC.md). The error taxonomy is normative in [RFC-0010 §Error taxonomy](../../rfcs/0010-harness-runner.md#error-taxonomy); this section summarises it and catalogues failure modes across the whole system. The implementation is `harness/src/iproofs/errors.py`.

## Principles

1. **A failure is a result.** A job that fails is written as a run directory with its failure record and counted in `n_failed`. It is never deleted or retried into success ([AGENTS.md hard rule 5](../../AGENTS.md#hard-rules), PRD N3).
2. **Fail before measuring, not during.** Everything that can be checked before a timed step (schemas, hashes, image digest, profile, GPU idle) is checked before it, so that a failed precondition costs no GPU time and produces no partial measurement.
3. **Verdicts are not errors.** `accept`, `reject`, `no_verdict` and `invalid_call` are outcomes of a verify call. An adapter that cannot produce one of them has failed.
4. **One taxonomy, closed.** Every failure has exactly one `ErrorKind`. A new kind needs an RFC.
5. **No silent degradation.** When a measurement is incomplete (sampler gaps, unobservable proof release), the number is marked `degraded` or null with a `null_reason`, never estimated.

## Error kinds

| Kind | Meaning | Typical step | CLI exit |
|---|---|---|---|
| `config` | an input file or argument is invalid | before jobs, `resolved` | 1 or 2 |
| `environment` | the host does not meet the profile or a prerequisite: the RFC-0006 conformance checks PC-GPU-MODEL, PC-GPU-MEM, PC-GPU-COUNT, PC-GPU-BUSY, PC-DRIVER, PC-CPU-NUMA, PC-CPU-TOTAL, PC-MEM, PC-DISK, PC-OS, PC-KERNEL, PC-CGROUP, PC-RUNTIME (`iproofs.provenance.check_profile`) | before jobs, `machine_recorded` | 3 |
| `integrity` | a hash, digest or pin does not match | `resolved`, `image_ready`, `info` | 4 (in a job), 1 (validate) |
| `fetch` | a network fetch failed after 3 attempts | `resolved`, `image_ready` | 4 |
| `adapter` | the adapter exited non-zero or broke the contract | any adapter step | 4 |
| `timeout` | a step exceeded its wall limit | any adapter step | 4 |
| `resource` | OOM kill or disk full | any adapter step | 4 |
| `policy` | a weakening configuration outside a control job | `prove`, validate | 4 (run), 1 (validate) |
| `internal` | a harness bug or an interrupted job | any | 5 |

Every recorded failure has the shape `{kind, step, message, exit_code, last_lines[], at}` ([RFC-0010 §Failure record](../../rfcs/0010-harness-runner.md#failure-record)), with `last_lines` holding the last 50 lines of adapter stderr after redaction ([05-observability §Redaction](05-observability.md#redaction)).

## Failure-mode catalogue

Each row names a failure, how it is detected, what the system does, and how it is recorded. "Run failed" means the job reaches `written` with `status: "failed"` and the given kind.

| # | Failure | Detection | Response | Recorded as |
|---|---|---|---|---|
| 1 | Workload, system, reference or target file fails its schema | `iproofs.schema` validation on load | stop before any job | `config`, exit 1 (validate) or 2 (run) |
| 2 | Workload not listed in `system.yaml` `workloads` | runner check at `resolved` | stop before any job | `config`, exit 2 |
| 3 | YAML date or ambiguous scalar not quoted | schema type check | reject the file | `config` |
| 4 | Model fetch fails (network, 5xx, rate limit) | exception in fetcher | retry 3 times with backoff 2 s, 8 s, 32 s; then fail | `fetch`, run failed at `resolved` |
| 5 | Gated model licence not accepted or `HF_TOKEN` missing | 401 or 403 from source | no retry | `fetch` with message naming the model, token never logged |
| 6 | Weight file hash differs from the workload | SHA-256 check before any container sees the file | delete the fetched file, fail | `integrity` at `resolved` |
| 7 | Prompt corpus bytes differ from `corpus.yaml` digest | SHA-256 check | fail | `integrity` at `resolved` |
| 8 | Image digest differs from `system.yaml` | `docker image inspect` | fail | `integrity` at `image_ready` |
| 9 | `info` reports an upstream commit other than `system.yaml` | field comparison | fail | `integrity` at `info` |
| 10 | Unpinned reference (short hash, tag instead of digest) | pin check | reject in CI; refuse to run | `integrity`, exit 1 |
| 11 | cgroup v1, kernel below 5.19, Docker below 25.0, toolkit below 1.17 | environment probe | stop before any job | `environment`, exit 3 |
| 12 | Host below profile (GPU model, CPUs on the GPU's NUMA node, memory, disk) | machine record against profile | stop before any job | `environment`, exit 3 |
| 13 | Another compute process on the bound GPU | NVML process list before each job | stop before the job | `environment`, exit 3 |
| 14 | Another runner active on the results tree | `flock` on `results/.runner.lock` or live staging dir | stop | `environment`, exit 3 |
| 15 | Adapter subcommand exits non-zero | container exit status | run failed; continue with next repetition | `adapter` with exit code and last lines |
| 16 | out.json missing, not JSON, or invalid against `adapter-out/1` | parse and schema validation | run failed | `adapter`; raw file kept in `logs/` |
| 17 | out.json `contract` or `subcommand` differs from the job | field check | run failed | `adapter` |
| 18 | Proof listed in out.json but not released, or released but not listed | INV-ADAPTER-6 check | run failed; released proofs still digested | `adapter` |
| 19 | Path in out.json escapes `/io`, symlink or device file in a proof | path resolution on host | run failed | `adapter` naming the path |
| 20 | Proof part above 64 GiB or more than 10,000 parts | size and count check | run failed | `adapter` |
| 21 | Tokens covered inconsistent with the shape | INV-ADAPTER-7 | run failed | `adapter` |
| 22 | Leftover `.tmp-*` proof directory after `prove` | directory scan | ignored, not counted | warning event `proof.tmp_left` |
| 23 | Step exceeds its wall limit | harness timer (`iproofs.measure.timed_call`) | `docker kill --signal KILL`, wait up to 30 s, container removed, run failed, `step.timeout` event, no retry | `timeout` |
| 24 | Container OOM killed | `docker inspect` `State.OOMKilled` after a non-zero exit (`timed_call`) | run failed, `step.oom` event | `resource` |
| 25 | Disk full while writing proofs or records | `OSError` with `ENOSPC` in a job state (`Runner.run`) | run failed; staging kept for diagnosis | `resource` |
| 26 | NVML sample gap above 150 ms | sampler timestamps | count the gap; above 5 % gaps mark GPU metrics `degraded: true` | quantity flag, event `sampler.gap` |
| 27 | NVML unavailable on a GPU profile | NVML init failure | stop before the job | `environment` |
| 28 | cgroup files of the container unreadable | read error | host memory and CPU time null with `null_reason: "missing_input"` | event `sampler.cgroup_unavailable` |
| 29 | Proofs released all at once (no observable steady window) | release times within one poll interval, or `steady_boundary: not_observable` | `prove.steady` null | `null_reason: "not_externally_observable"` |
| 30 | Fewer than two proofs in a session | count | `prove.steady` null | `null_reason: "fewer_than_two_proofs"` |
| 31 | Verify returns a value outside the four verdicts | schema validation | that verify call failed | `adapter`; row or control outcome `error` |
| 32 | Honest verify returns `reject` or `no_verdict` | verdict per proof | recorded in the row; acceptance count reflects it | verdict counts in `run.json` |
| 33 | Forbidden flag outside a control job | adapter refuses; CI policy check on `commands.jsonl` | run failed or PR blocked | `policy` |
| 34 | A control job appears among a release's measured rows | CI check on manifest `control` | PR blocked | `policy`, exit 1 |
| 35 | Control twin not accepted | twin verdict | control `void` | control outcome `void` |
| 36 | Accepted control where rejection was expected | classification | private disclosure, embargo | `disclosure_pending: true` in `controls.json` |
| 37 | Mutation identical to the original input | assertion in `iproofs.controls` | control `error` | `internal` |
| 38 | Derived value differs from recomputation | `iproofs derive --check` | PR blocked | exit 1 |
| 39 | Quantity missing unit, grade, tier, source or a required scope | label check | PR blocked | exit 1 |
| 40 | Committed JSON not byte-identical to re-serialisation | format check | PR blocked | exit 1 |
| 41 | Run dir edited or deleted after merge | CI diff check on `results/` | PR blocked | exit 1 |
| 42 | Secret or host identifier in a committed file | secrets scan | PR blocked | exit 1 |
| 43 | Runner killed or host lost power mid-job | stale staging dir on next start | written as failed, never resumed | `internal` at last reached step |
| 44 | Harness writes a document that fails its own schema | validation at `written` | run failed; invalid file kept in `logs/invalid/` | `internal`, exit 5 |
| 45 | Reproduction outside tolerance | `iproofs reproduce compare` | published as a failed reproduction with both sets of numbers | reproduction record `outcome: outside_tolerance`, exit 1 |
| 46 | Verdict sets of original and reproduction differ | `iproofs reproduce compare` | failed reproduction | reproduction record |
| 47 | Proof digests differ when `deterministic_proofs: true` and same seed | `iproofs reproduce compare` | failed reproduction | reproduction record |
| 48 | Reference row cannot run on the profile (model does not fit) | adapter failure or declared infeasibility | row recorded failed, overhead null | `null_reason: "not_measurable_on_profile"` |
| 49 | No perturbed commitment for the workload (no tensor of at least 1,024 elements, the adapter cannot commit the copy, or the weights are not on this host) | `iproofs controls --prepare-perturbed`; `_perturbed` lookup at control time | C3 and P1 `not_applicable` with the reason | `config` exit 2 from `--prepare-perturbed`; control note |

## Recovery rules

- **Before measurement:** `fetch` retries; every other failure stops the job or the invocation.
- **During measurement:** nothing retries. The runner records the failure and moves to the next repetition ([RFC-0010 §Retry policy](../../rfcs/0010-harness-runner.md#retry-policy)).
- **After a crash:** the stale job is written as failed `internal` and never resumed ([RFC-0010 §Crash recovery](../../rfcs/0010-harness-runner.md#crash-recovery)). `iproofs run` does this on start (`Runner.recover`): failure step is the last state the job reached, message `runner terminated before completion`, event `runner.recovered`; a staging directory whose runner is still alive on this boot makes it exit 3.
- **In CI:** every check failure blocks the merge; there is no override flag. A maintainer who believes a check is wrong changes the check by pull request.

## Error messages

Messages are one sentence, name the file, field or step, and state the expected and actual values where they are safe to print (hashes, versions, counts). They never include secrets, host names, IP addresses or absolute home paths; redaction applies to messages as to logs.
