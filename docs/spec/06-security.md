# 06. Security

Status: Draft 0.1. This section is the threat model for the benchmark itself: the harness, the adapters, the results repository and the published site. It does not assess the security of any measured prover; that is what claim cards and controls report (PRD §5: the benchmark does not certify security). Normative mechanisms live in [RFC-0005](../../rfcs/0005-adapter-contract.md), [RFC-0008](../../rfcs/0008-negative-controls.md), [RFC-0013](../../rfcs/0013-validation-and-ci.md) and [RFC-0014](../../rfcs/0014-provenance-and-integrity.md).

## Assets

| Asset | Why it matters |
|---|---|
| A1 Integrity of published numbers | The benchmark's only product; a wrong number with correct labels misleads relying parties |
| A2 Integrity of verdicts and control outcomes | A verifier shown as rejecting tampering when it does not is a false security statement |
| A3 Commitment provenance | If the verifier checks against a commitment the prover chose, every accept is meaningless (AGENTS.md rule 6) |
| A4 Runner secrets | `HF_TOKEN`, registry credentials, provider credentials, SSH keys on the runner host |
| A5 Runner privacy | Host identifiers and personal data must not be published (AGENTS.md rule 7) |
| A6 Undisclosed weaknesses | A control a verifier accepts is a vulnerability in that system until its maintainers have had time to respond |
| A7 Neutrality | The perception and fact that no party controls results |

## Adversaries

| Id | Adversary | Goal | Capabilities assumed |
|---|---|---|---|
| T1 | A system team gaming its numbers | better rates, smaller proofs, more controls rejected | writes or reviews its adapter, controls upstream code at the pin, knows the workloads |
| T2 | A malicious or careless adapter | escape the container, read secrets, exfiltrate data, fake verdicts | arbitrary code inside the adapter image |
| T3 | Supply chain | substitute code or data | controls an upstream repository, a registry, a model host or a dependency |
| T4 | A fabricating runner | publish numbers that were never measured | submits run directories by pull request |
| T5 | A contributor weakening the methodology | let a weakened configuration pass as measured, or change a rule without an RFC | opens pull requests |
| T6 | A reader of published logs | learn host identifiers or secrets | reads everything public |

## Trust boundaries

1. **Runner host.** Trusted by the runner who operates it. The harness process runs there with the runner's privileges and holds `HF_TOKEN` in its environment. Nothing else on the host is trusted to be absent: the harness checks that no other compute process is on the bound GPU before each job.
2. **Adapter container.** Untrusted. It receives only `/io` (job inputs, read-write), `/models` (read-only, prover steps only) and the recorded commitment files (read-only). It has no network, no secrets and no host paths beyond those mounts.
3. **Upstream code inside the container.** Untrusted for the same reasons; pinned by commit and recorded by digest.
4. **Results repository.** Changes arrive by pull request; CI gates and reviewers are the boundary. Merged results are append-only.
5. **Site.** Generated from the repository; it executes no code from submissions (replies are escaped Markdown).

## Mechanisms

### Container hardening (T2)

Every adapter container runs with `--network none`, `--read-only` root filesystem, `--cap-drop ALL`, `--security-opt no-new-privileges`, a non-root user declared in the Dockerfile, `--pids-limit 4096`, the profile's `--cpuset-cpus` and `--cpuset-mems`, a memory limit of 32 GiB for verify steps, and `--gpus device=<index>` only for prover steps (RFC-0005 owns the exact argv). Writable scratch is a `--tmpfs /tmp` sized per the profile (RFC-0005). Containers never get the Docker socket, `--privileged`, host PID or IPC namespaces, or device nodes other than the bound GPU.

### Untrusted input handling (T2, T1)

The harness treats everything an adapter writes as hostile input:

- `out.json` is read with a size limit of 16 MiB, parsed with the stdlib JSON parser, and validated against `adapter-out/1` before any field is used. Invalid output is `ErrorKind.adapter`.
- Every path in `out.json` (proof parts, verifier files, prover files, logs) is resolved relative to the step's `/io` on the host and rejected (`ErrorKind.adapter`) if, after `os.path.realpath`, it leaves that directory, is a symlink, is a device or FIFO, or is not a regular file.
- Proof ids must match the RFC-0012 pattern (one path component).
- File counts and sizes are capped by `system.yaml` (`max_proof_parts`, `max_proof_bytes`); exceeding a cap is `ErrorKind.adapter`, recorded, not truncated.
- Tests: `harness/tests/unit/test_path_safety.py` (`test_path_escape_rejected`, `test_unlisted_proof_is_adapter_failure`, `test_listed_but_unreleased_is_adapter_failure`, the part, size and out.json caps, symlink and non-regular parts). Messages name container paths (`/io/...`) only, never host paths.
- Adapter stdout and stderr are read through a bounded pipe and capped per RFC-0009 before they reach disk; they are redacted before writing.
- Strings from adapter output that reach the site are HTML-escaped by the template engine (autoescape on).

### Commitment provenance (A3)

The harness copies verifier and prover files out of the commit step into a harness-owned store, records their digests, and builds every verify `/io` from that store only ([RFC-0014 §The commitment record](../../rfcs/0014-provenance-and-integrity.md#the-commitment-record)). A prover's own commitment files never reach a verifier. Implementation: `Runner._commit`, `Runner._recorded` and `Runner._commitment_echo` in [`harness/src/iproofs/runner.py`](../../harness/src/iproofs/runner.py) keep the store at `<job tmp>/commitment/` and recheck each digest before the call that uses it. `prove` gets the recorded prover files mounted read-only over their `/io/state/` paths, and every `verify` gets them mounted read-only at `/io/verifier`. A `prove` output that names `commitment_id`, or that ships a file equal to a recorded verifier file, logs `policy.warning` and adds a `run.json` warning. Tests: `harness/tests/unit/test_commitment.py`, plus `test_commitment_from_record` in the G10 module.

### Gaming resistance (T1)

| Gaming route | Response |
|---|---|
| Precompute proofs for known prompts | Fresh 64-bit prompt seed per measured job from `os.urandom`, recorded (RFC-0003) |
| Verifier that accepts everything, or an adapter that maps every exit code to `accept` | Shared controls C1 to C8 expect rejection; `fake-broken` in CI proves the suite detects this pattern (RFC-0013 G10) |
| Report internal timings that exclude work | Harness measures externally; adapter timings are labelled `source.kind: adapter` |
| Run a weakening flag in a measured row | `forbidden_flags` in `system.yaml`, recorded argv, G6 `POL-1` |
| Reuse a cached commitment to skip commit cost | Commit runs in every job; the commitment's files are digested and recorded per job |
| Choose favourable repetitions | All repetitions are recorded and published, including failures (AGENTS.md rule 5) |
| Review one's own adapter | A maintainer does not merge changes to their own system's adapter, claim card or results (RFC-0001) |

### Supply chain (T3)

Pins and build rules B1 to B7 in [RFC-0014](../../rfcs/0014-provenance-and-integrity.md#adapter-image-build): base images and actions by digest or commit, lockfiles with hashes, offline build after a verified fetch stage, weights hashed per file on fetch and before every job, source archives kept with each release.

### Fabricating runner (T4)

v0.1 has no cryptographic defence against a runner who fabricates a whole run directory with consistent numbers. The defences are procedural: every run is `reported` until a different organisation peer-reviews it and an unaffiliated runner reproduces it ([RFC-0007](../../rfcs/0007-evidence-tiers-and-reproduction.md)); a fabricated run fails reproduction. Signed results are [RFC-0014 Q1](../../rfcs/0014-provenance-and-integrity.md#open-questions).

### Methodology weakening (T5)

Required CI gates without bypass (RFC-0013), methodology changes only by RFC (RFC-0001), the conflict-of-interest merge rule, and `forbidden_flags` changes reviewed by a maintainer other than the system's.

## Secrets handling (A4)

The redactor (`iproofs.log.redact`) and the CI secrets scan (gate G9) share one compiled pattern set, `iproofs.log.patterns`.

- The only secret the harness reads is `HF_TOKEN`, from the environment, for gated model downloads. It is passed to the fetch call in the harness process and to nothing else. It is never placed in argv, never passed into a container, never written to any record.
- Registry credentials for pushing release images are used by maintainers' build tooling, not by the harness.
- CI has no secrets available to pull request jobs (`contents: read`).
- The log redactor removes values of environment variables whose names match `(?i)(token|key|secret|password|credential)` wherever they appear in a log line, plus the patterns of RFC-0013 G9. G9 then scans every committed file for the same patterns, so a redaction miss fails CI before publication.
- The rule ids, each a pattern in `iproofs.log.patterns` (RFC-0013 §G9): `SEC-1` Hugging Face tokens, `SEC-2` GitHub tokens, `SEC-3` AWS access key ids, `SEC-4` private key headers, `SEC-5` IPv4 and `SEC-6` IPv6 literals (loopback excepted), `SEC-7` MAC addresses, `SEC-8` GPU UUIDs, `SEC-9` SSH config fragments, `SEC-10` absolute home paths, `SEC-11` secret-like assignments. A G9 failure names the file, the line and the rule id.
- G9 skips `harness/tests/fixtures/secrets/` (one known-bad sample per rule) and `schema/*/examples/invalid/` in a repository scan, and scans them when they are named (`uv run iproofs validate harness/tests/fixtures/secrets`). Tests read secret-shaped samples from those fixtures, so no other file needs an exception.

## Privacy and identifier exclusion (A5, T6)

The machine record contains only the fields [RFC-0006](../../rfcs/0006-reference-hardware-and-cost.md) lists: GPU model, count, memory, driver, CUDA runtime, CPU model, sockets, cores, logical CPUs, the GPU's NUMA node, the bound cpuset, SMT state, host memory total, disk type and free space, kernel version, OS release, container runtime and its version, NVIDIA Container Toolkit version, and the runner-declared provider name. It never contains hostnames, IP or MAC addresses, GPU UUIDs or serials, account or user names, SSH configuration, cloud instance ids or absolute home paths. The harness builds the record from an allowlist of probes, not by filtering a full dump, so a new probe cannot leak a field by accident. The manifest's `runner` block (`handle`, `organisation`, `affiliated_systems`) is what the runner declares for attribution and tier rules (RFC-0007); a runner may give an organisation name only.

## Disclosure

### Accepted controls (A6)

When a control whose expected outcomes exclude `accept` is accepted on a real system ([RFC-0008](../../rfcs/0008-negative-controls.md)):

1. The runner does not open a public pull request with that run. They report privately to the system's maintainers through the channel in the system's security policy, and to the benchmark maintainers through `SECURITY.md`.
2. The embargo follows the system's own policy; if it has none, 90 days from the report or until the upstream publishes a fix or advisory, whichever is earlier.
3. After the embargo the run is published in full, with the outcome printed in the row (RFC-0008 §Reporting) and the system maintainers' reply if they write one.
4. The run is not discarded, and the result is not softened.

### Harness vulnerabilities

`SECURITY.md` names a private reporting channel for vulnerabilities in the harness, the fake systems, the CI workflows or the site generator. Maintainers acknowledge within 7 days (target) and publish a fix and an advisory. A vulnerability that could have affected published numbers is listed in the next release report under "what failed", with the affected runs.

## Residual risks

- A fabricating runner is caught only by reproduction, not prevented (T4).
- A container escape through the GPU driver or container runtime is outside what the harness can prevent; runners should use dedicated or freshly provisioned hosts and keep the driver and runtime at the versions the reference file pins.
- Upstream code inside a container can behave differently when it detects measurement (for example skipping work when not observed). External timing and controls limit the effect; they cannot exclude it.
- The neutral-language lint and the redactor are pattern based and can miss paraphrases and novel secret formats.
