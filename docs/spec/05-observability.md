# 05. Observability

Status: Draft 0.1, part of the specification corpus indexed in [docs/SPEC.md](../SPEC.md). Logging and redaction rules here are normative for the harness; the measurement itself (what is sampled and how) is in [RFC-0011](../../rfcs/0011-measurement-and-sampling.md).

## Scope

The benchmark's measurements are its product, and they are specified in RFC-0004 and RFC-0011. This section covers the diagnostics around them: what the harness logs, in which format, what it redacts, what it prints for humans, and how a reader diagnoses a failed or surprising run from the run directory alone. There is no tracing system and no metrics backend; a job's steps are its spans, and the run directory is the only sink.

## Log files

Every job writes, inside its run directory:

| File | Content | Writer |
|---|---|---|
| `logs/harness.jsonl` | structured harness events, one JSON object per line | harness |
| `logs/<step>.stdout`, `logs/<step>.stderr` | adapter container output per step, redacted | harness (captured) |
| `logs/commands.jsonl` | upstream command lines the adapter started ([RFC-0005 §Command log](../../rfcs/0005-adapter-contract.md#command-log)) | adapter, copied by harness |
| `logs/invalid/` | documents that failed validation, kept for diagnosis | harness |

Size caps (INV-OBS-1): each log file is capped at 1 MiB, keeping the first 256 KiB and the last 768 KiB with the marker line `[iproofs: <k> bytes omitted, full digest in digests.txt]` between them; the whole run directory is capped at 10 MiB, enforced by cutting the largest adapter output files further first ([RFC-0009 §Storage](../../rfcs/0009-results-and-publication.md#storage)). Adapter output is read through bounded captures (`iproofs.measure.Capture`): a runaway adapter fills neither memory nor disk, and the digest of each whole stream, before redaction and truncation, goes into `digests.txt` as `logs/<step>.<stream>`; every other log file's digest is recorded before any cut. The elided byte count is recorded in the `log.truncated` event. `iproofs controls RUN_DIR` adds its calls' output as `logs/controls-verify.*`.

## Event format

The logger is `harness/src/iproofs/log.py` (`JsonlLogger`, `Event`); a test keeps its event constants equal to the catalogue below.

Each line of `logs/harness.jsonl` is a JSON object written by the single writer ([RFC-0012](../../rfcs/0012-schemas-and-serialization.md)) but on one line (no indent):

```json
{"ts": "2026-11-03T10:15:02.118Z", "mono_ns": 81234567890123, "level": "info",
 "event": "step.end", "job": "2026-11-03-fake-fake-tiny-ci-ci-cpu-1", "step": "prove",
 "exit_code": 0, "seconds": 4.812}
```

| Field | Type | Meaning |
|---|---|---|
| `ts` | string, RFC 3339 UTC, millisecond precision | wall-clock time, for humans and cross-file correlation only |
| `mono_ns` | integer | `time.monotonic_ns()`; the only clock used for durations |
| `level` | `debug`, `info`, `warning`, `error` | severity |
| `event` | string from the catalogue below | what happened |
| `job` | run id or null | the job the event belongs to |
| `step` | state name or null | the job state |
| further fields | per event | event payload |

Rules:

- **INV-OBS-2:** durations in logs are informative. Published numbers come from `run.json` only.
- **INV-OBS-3:** event names are stable within a harness minor version; a renamed event is listed in `CHANGELOG.md`.
- **INV-OBS-4:** every log line passes redaction before it is written.

## Events catalogue

| Event | Level | Fields | Emitted when |
|---|---|---|---|
| `runner.start` | info | `harness_version`, `argv` (redacted) | `iproofs run` begins |
| `runner.recovered` | warning | `run_id`, `last_state` | a stale staging dir is written as failed |
| `job.state` | info | `from`, `to` | every state transition |
| `job.failed` | error | `kind`, `message`, `exit_code` | a failure is recorded |
| `job.written` | info | `run_dir`, `outcome` | the run dir is renamed into place |
| `fetch.attempt` | info | `what`, `attempt`, `backoff_s` | each fetch attempt |
| `fetch.failed` | error | `what`, `attempts` | fetch gives up |
| `integrity.ok` | debug | `what`, `digest` | a hash check passes |
| `integrity.model_rehash` | info | `what`, `seconds` | the cached weights were rehashed at job start, outside every timed scope; a diagnostic, never a published number (RFC-0014) |
| `integrity.mismatch` | error | `what`, `expected`, `actual` | a hash check fails |
| `env.probe` | info | `kernel`, `cgroup`, `docker`, `toolkit` | environment checked |
| `env.gpu_busy` | error | `process_count` | another compute process found on the GPU |
| `gpu.foreign_process` | warning | `process_count` | a compute process appeared on the bound GPU during a GPU step; that step's GPU metrics are `degraded: true` (RFC-0011 S-7) |
| `cpuset.selected` | info | `cpus`, `mems`, `smt` | cpuset chosen for a step |
| `step.start` | info | `subcommand`, `image`, `timeout_s` | before `docker run` |
| `step.end` | info | `exit_code`, `seconds` | after the container exits |
| `step.timeout` | error | `timeout_s` | wall limit reached, container killed |
| `step.oom` | error | | OOM kill detected |
| `proof.released` | debug | `proof_id`, `release_mono_ns`, `index`, `of` | the watcher sees a rename |
| `proof.tmp_left` | warning | `name` | a `.tmp-*` dir remains after `prove` |
| `sampler.start` | debug | `kind`, `hz` | a sampler thread starts |
| `sampler.gap` | warning | `kind`, `gap_ms` | a gap above 150 ms between samples |
| `sampler.cgroup_unavailable` | warning | `path` | cgroup files unreadable |
| `policy.warning` | warning | `detail` | `prove` output echoes the commitment ([RFC-0014 §The commitment record](../../rfcs/0014-provenance-and-integrity.md#the-commitment-record) rule 5); the run continues |
| `cgroup.stale_cleanup` | warning | `units` | placeholder scopes left by a crashed runner were stopped before conformance (RFC-0011 §Cgroup accounting) |
| `verify.result` | info | `proof_id`, `verdict`, `raw_exit_code`, `cpus`, `index`, `of` | after each verify call |
| `control.call` | info | `control` (`twin` for an honest twin), `trial` (null for a prove), `subcommand`, `exit_code`, `seconds` | after each control call that returned, verify or prove, so a long suite shows its progress and a stopped part leaves the span of every finished call (RFC-0008 §Split suites) |
| `control.trial` | info | `control`, `trial`, `outcome` | after each control trial |
| `control.twin_mismatch` | warning | `control`, `twin_verdict` | honest twin not accepted (the control is `void`, `iproofs.controls.control_record`) |
| `control.disclosure_pending` | warning | `control` | accepted where rejection was expected |
| `log.truncated` | info | `file`, `elided_bytes` | a log file hit its cap |
| `validate.fail` | error | `check`, `path`, `message` | a CI check fails (validate command) |

## Redaction

Applied to every log line, every captured adapter output, every failure message and `last_lines`, before writing (INV-OBS-4). The redactor is `iproofs.log.redact.Redactor`; its patterns live in `iproofs.log.patterns`, the module gate G9 also uses. Redaction replaces matches with a fixed marker naming the class, for example `<redacted:token>`.

| Class | Rule |
|---|---|
| Secrets in environment | the values (at least 8 characters long) of every environment variable whose name matches `(?i)(token\|key\|secret\|password\|credential)`, and of `HF_TOKEN`, are replaced wherever they occur |
| IP addresses | IPv4 dotted quads and IPv6 literals (RFC 4291 text forms) |
| Host name | the value of `socket.gethostname()` and its first label |
| Home paths | the absolute path of the user's home directory is replaced by `~` |
| MAC addresses | six colon- or hyphen-separated hex octets |
| GPU identifiers | NVIDIA GPU UUIDs (`GPU-` followed by a UUID) and board serial numbers read from NVML at start |

The harness never logs the full environment, never logs `docker inspect` output whole, and never records account names, SSH configuration or cloud instance IDs. Only the machine record fields listed in [RFC-0006](../../rfcs/0006-reference-hardware-and-cost.md) describe the host. The secrets scan in CI ([RFC-0013](../../rfcs/0013-validation-and-ci.md)) applies the same patterns to every committed file as a second line of defence.

## Progress output

Human-readable progress goes to stderr, one line per state transition and per proof released, for example:

```
[rep 2/3] prove   running   00:41:12  proofs 61/120
[rep 2/3] prove   done      01:22:40  exit 0
[rep 2/3] verify  proof 7/120 accept
[rep 1/1] controls verify C2 trial 0  01:02:13  exit 0  3732 s
```

`--quiet` suppresses it. Progress lines carry no information that is not also in `harness.jsonl`: `iproofs.log.Progress` formats them from the records the logger writes (`job.state`, `proof.released`, `verify.result`, `control.call`, `job.failed`, `job.written`), so a record filtered out by `--log-level` (for example `proof.released`, a debug event) prints no progress line either.

## No telemetry

The harness sends nothing off the host. There is no usage reporting, crash reporting or update check. Network access happens only in `fetch` operations (weights, prompt corpus, images by digest) to the sources named in the workload and system files.

## Diagnosing a run

A reader with only the run directory can answer, in order:

1. **Did it fail, where and why?** `run.json` `status` and `failure` (kind, step, exit code, last lines).
2. **What was running?** `manifest.json`: image digest, upstream commit, workload and prompt digests, job seed, machine record, command lines.
3. **What did the adapter do?** `logs/<step>.stderr` and `logs/commands.jsonl`.
4. **When did each step and proof happen?** `harness.jsonl` `step.start`, `step.end`, `proof.released`.
5. **Can the measurement be trusted?** `sampler.gap` events and `degraded` flags on GPU quantities; `null_reason` on null quantities.
6. **What did the verifier say?** `verifier/<proof_id>.json` with verdict, raw exit code and raw last line; `controls.json` for controls.

A failure that cannot be diagnosed from these files is a defect in the harness's logging and gets an issue.
