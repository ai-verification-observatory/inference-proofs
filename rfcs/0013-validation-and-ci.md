# RFC-0013: Validation pipeline and CI gates

- Status: Draft
- Authors: AbdelStark
- Created: 2026-11-03
- Target milestone: v0.1-alpha
- Requires: RFC-0002, RFC-0004, RFC-0005, RFC-0008, RFC-0012
- Supersedes: none
- Discussion: pull request that introduces it

## Summary

This RFC defines every automated check that stands between a pull request and the default branch, and the local command that runs the same checks. There are twelve gates, G1 to G12. Each gate has one rule, a fixed input set, a failure message format and a required-check status. All gates run on CPU in hosted CI; nothing in this RFC needs a GPU. GPU work is verified by the records it produces, which these gates then check.

## Motivation

The project's credibility rests on rules that a reviewer cannot check by eye at scale: every number labelled (AGENTS.md rule 2), every derived number computed (rule 3), no weakening flag in a measured row (rule 4), commitments from the harness record (rule 6), no secrets or host identifiers (rule 7), neutral language (rule 10), full pins everywhere (working practice). The draft specification's §12 listed five CI checks in one sentence. That is not enough to implement them, to know which are blocking, or to run them locally before pushing.

Concrete scenarios the gates must catch:

- A contributor edits `run.json` to change a mean from `103.6` to `111.2` and leaves the raw samples alone. G4 fails.
- An adapter change adds `--unsound-skip-lookup` to the SASH prove command for a measured job. G6 fails.
- A results PR pastes a log containing a host's IP address. G9 fails.
- A docs PR describes a system as "the fastest prover". G8 fails.
- A system manifest pins upstream as `eb95bfa`. G7 fails.

## Goals

- Every rule in AGENTS.md that can be checked mechanically is checked by a named gate.
- `uv run iproofs validate` on a clean checkout runs G2 to G9 and G12 locally in under 60 s for a tree of 1,000 run directories (budget, not a measurement; see [docs/spec/08-performance-budget.md](../docs/spec/08-performance-budget.md)).
- Every failure message names the file, the location inside it (JSON Pointer or line), the gate, the rule and, where possible, the fix.
- Gates are deterministic: the same tree gives the same verdict on every machine.

## Non-Goals

- Checking the security of a prover, or that a claim card is true. Claim cards are reviewed by people (RFC-0002).
- Running GPU jobs in CI. Hosted runners have no H100, and the cost model forbids it.
- Style rules for Python beyond what ruff and mypy enforce.
- Checking prose numbers in Markdown for labels. A free-text parser for that would be unreliable; reviewers check prose, and reports draw numbers from records through templates (RFC-0009 §Reports).

## Proposed Design

### Overview

```
pull request
  -> job lint-and-types      G1 (ruff, mypy strict)
  -> job tests               G1 (pytest unit + property)
  -> job validate            G2 G3 G4 G5 G6 G7 G8 G9 G12   (iproofs validate --all)
  -> job fake-e2e            G10 (docker on the hosted runner, CPU only)
  -> job dco                 G11
```

All five jobs are required checks on the default branch. A pull request merges only when all are green. Maintainers MUST NOT bypass required checks; a broken gate is fixed by a pull request to the gate.

The command `iproofs validate [PATH ...]` runs the tree gates. With no path it validates the tree under the current directory; with `--all` it ignores git and checks every file; with `--changed-since <ref>` it limits G2 to G9 to files changed since `ref` plus every file that references them (run directories referencing a changed workload or system manifest). CI on pull requests uses `--changed-since origin/main`; CI on the default branch, nightly, uses `--all`.

### Failure message format

Every gate failure is one line on stdout:

```
<gate> <path>[#<json-pointer> | :<line>] <rule-id>: <message>[ (fix: <hint>)]
```

Example: `G5 results/v0.1/sash/2026-12-02-sash-sash-l31-8b-c4096-prover-h100-1/run.json#/metrics/rate_prove.steady INV-QTY-3: unit token/s requires a scope (fix: set scope to one of setup, commit, ...)`.

Failures are sorted by gate, then path bytes, then pointer. After the list, a summary line `validate: <n> failures in <m> files` goes to stderr. Exit code 1 on any failure, 0 otherwise, 2 on bad usage. `--format json` emits a JSON array of `{gate, path, pointer, line, rule, message, hint}` for tooling.

### G1 Lint, types and tests

- `uv run ruff check .` and `uv run ruff format --check .` with the config in `pyproject.toml`.
- `uv run mypy --strict harness/src/iproofs`.
- `uv run pytest harness/tests/unit harness/tests/property -q` with Hypothesis profile `ci` (`max_examples=200`, `derandomize=True`, so property tests are deterministic in CI).
- Adapter fixture tests: `uv run pytest systems/*/tests -q` (CPU only, stored fixtures, RFC-0005).
- Repository policy tests: `uv run pytest harness/tests/repo -q`. They implement the governance checks of [RFC-0001](0001-process-and-governance.md#testing-strategy) (`MAINTAINERS.md` rows and seat rules, RFC status lines against `rfcs/README.md`, the licence boundary, claim card `card_version` increments, and, where the hosting platform exposes the merger, the interested-maintainer merge guard), the module import layers of [01](../docs/spec/01-architecture.md#module-boundaries), and the quarantine rule for flaky tests ([07](../docs/spec/07-testing-strategy.md#flaky-test-policy)).

### G2 Schema validation

Rule: every document in the tree that has a schema validates against the schema its `schema` field names (RFC-0012). Every `schema/*/examples/valid/*` validates; every `schema/*/examples/invalid/*` fails, and the failure text contains the content of its `.reason` file.

Inputs: files matching `systems/*/claim.yaml`, `systems/*/claims/*.yaml`, `systems/*/{system,external,controls}.yaml`, `workloads/**/*.yaml`, `reference/*.yaml`, `targets/**/*.yaml`, `releases/*/release.yaml`, `releases/*/index.json`, `results/**/{run,manifest,controls}.json`, `results/**/reviews/*.json`, `results/**/reproductions/*.json`, `schema/*/examples/**`.

Cross-document checks (also G2, rule ids `XREF-n`):

- `XREF-1` every `run.json` names a workload id and version that exist in `workloads/`, a system that exists in `systems/`, and a profile that exists in the release's reference file.
- `XREF-2` every `manifest.json` image digest equals the digest recorded in `run.json`.
- `XREF-3` every review and reproduction record names an existing run directory.
- `XREF-4` every `releases/<r>/release.yaml` lists only existing run directories, and the reference file it names exists.
- `XREF-5` every target names a metric id that exists in the RFC-0004 formula registry or the raw metric list.
- `GOV-1` to `GOV-3` (governance, [RFC-0001 §Roles](0001-process-and-governance.md#roles)): every `MAINTAINERS.md` row has a handle, role, organisation and declared interests (`GOV-1`; the placeholder `undeclared` is a warning); INV-GOV-1 (`GOV-2`, a warning until release approval); INV-GOV-2 (`GOV-3`). Warnings go to stderr and never fail the gate.

Repository-shape checks (also G2):

- `APP-1` on pull requests, no path under `results/` that exists on the base branch is modified or deleted; additions under `<run-id>/reviews/` and `<run-id>/reproductions/` are the only changes allowed inside an existing run directory ([RFC-0009 §Append-only rule and corrections](0009-results-and-publication.md#append-only-rule-and-corrections)).
- `SIZE-1` no committed file outside `results/*/*/*/logs/` exceeds 5 MiB, and no run directory exceeds 10 MiB. This keeps weights and proofs out of git (AGENTS.md rule 8).
- `RPL-1` every reply file `systems/*/replies/*.md` has at most 300 words, counted per [RFC-0009 §Right of reply](0009-results-and-publication.md#right-of-reply).

### G3 JSON format check

Rule: for every committed `*.json` file outside `schema/` (schemas are authored), `bytes == dumps(json.loads(bytes))` with the RFC-0012 writer. Rule id `FMT-1`. Hint: `run iproofs fmt <path>`. `iproofs fmt` is a hidden maintenance subcommand that rewrites a file with the canonical writer; it is not part of the public CLI.

### G4 Derived recompute

Rule: for every run directory, `iproofs derive <run-dir> --check` recomputes every quantity with `grade: derived` from the stored raw quantities and the release's reference file, and requires `==` equality with the stored value, `null` with the same `null_reason` where the formula yields null. Rule id `DER-1` for a mismatch, `DER-2` for a derived quantity whose formula id is unknown, `DER-3` for a formula whose inputs are missing. The message prints the formula id, the input pointers and both values with `repr`. Same check for `releases/*/index.json` aggregates (statistics across repetitions).

### G5 Label check

Rule: every quantity satisfies INV-QTY-1 to INV-QTY-8 of [RFC-0012 §Invariants](0012-schemas-and-serialization.md#invariants). Most are schema rules and fire in G2; G5 adds the graph checks the schema cannot express:

- `LBL-1` (INV-QTY-3, second half) a `ratio` derived from a rate carries the denominator rate's scope.
- `LBL-2` (INV-QTY-6) the derivation formula id exists at the named harness version, and every `source.inputs` pointer resolves to a quantity.
- `LBL-5` (INV-QTY-6a, INV-QTY-9) a derived quantity's tier is the lowest tier among its inputs and its `quality` flags are the OR of its inputs' flags.
- `LBL-3` (INV-QTY-4) no `run.json` or `controls.json` quantity has a tier other than `reported`.
- `LBL-4` every number-typed leaf in `run.json`, `controls.json` and `index.json` that is not inside a quantity sits at a path on the structural-integer allowlist in `harness/src/iproofs/validate/structural_paths.txt` (for example `/shape/batch_size`, `/*/stats/n`). A bare float anywhere else fails.

### G6 Policy check

Rule: no measured run uses a weakening configuration.

- Input: each `systems/<name>/system.yaml` field `forbidden_flags: [string]` (for SASH this lists the `--unsound-skip-*` family as a glob, `--unsound-skip-*`; the exact entries come from the upstream documentation at the pinned commit and are confirmed in the adapter issue).
- `POL-1`: for every `manifest.json` with `control: false`, no recorded command line (`manifest.commands[].argv`) contains a token matching any forbidden glob (`fnmatch`, case sensitive).
- `POL-2`: every run with `control: true` has no measured quantities other than verdict counts, and is excluded from every release table except the controls table (checked against `release.yaml`).
- `POL-4`: no run directory whose manifest records `harness.nonconforming: true` is accepted anywhere under `results/`. `iproofs run --allow-nonconforming` exists for adapter development on hosts that do not meet a profile ([RFC-0010](0010-harness-runner.md)); its output is refused by the validator, so it can never enter the repository or a release.
- `POL-3`: every adapter's entrypoint source does not contain a forbidden flag literal outside a code path guarded by the job's `control` field. This is a text check over `systems/<name>/entrypoint*` that flags any line containing a forbidden glob match; the adapter README MUST list each such line and the guard, and the check accepts lines listed in `systems/<name>/policy-allow.txt` (file, line content). Reviewers check the guard.

### G7 Pin check

- `PIN-1` every commit reference in `system.yaml`, `claim.yaml` and `claims/*.yaml` (`upstream.commit`), `external.yaml` source URLs, `Dockerfile` `ARG UPSTREAM_COMMIT=` and `git checkout` lines is a full 40-hex lowercase hash.
- `PIN-2` every image reference in Dockerfiles (`FROM`), `system.yaml` and manifests is `<repo>@sha256:<64 hex>`. Tags alone fail; `<repo>:<tag>@sha256:...` is accepted, the tag is informative.
- `PIN-3` every workload has `model.digest` and per-file digests, `prompts.corpus_digest`, and `model.revision` as a 40-hex hash.
- `PIN-4` every `reference/<release>.yaml` pins the NVIDIA driver version, the CUDA runtime version and the container runtime version as exact strings (no ranges).
- `PIN-5` every toolchain version in an adapter Dockerfile is exact (no `latest`, no `^` or `~` ranges in pip or cargo install lines, `apt-get install` packages pinned with `=` or the base image digest carrying the pin, declared in the adapter README).

### G8 Neutral-language lint

Rule `LANG-1`: no word or phrase from the list below appears, case insensitive, on a word boundary, in files under `docs/`, `rfcs/`, `reports/`, `site/` templates, `systems/*/README.md`, `systems/*/claims/*.yaml` and `README.md`.

```
fastest, slowest, best, worst, winner, wins, beats, beat, crushes, outperforms,
state of the art, state-of-the-art, world-class, revolutionary, blazing,
provably safe, provably secure, guaranteed secure, unbreakable, military-grade
```

Mentions are not uses: an occurrence inside double quotes (`"..."`, typographic quotes) or a backtick span on the same line is skipped, so a document can say that the project never names a "fastest" system. Allowlist: files that state the rule itself (`AGENTS.md`, `docs/spec/10-glossary.md`, `rfcs/0013-validation-and-ci.md`) are skipped. A single line elsewhere can be allowed by an HTML comment on the line above, `<!-- lang-allow: <word> <reason> -->`, which reviewers must approve; each use is printed as a notice in CI output. Right-of-reply files (`systems/*/replies/*.md`) are printed unedited (RFC-0009) and are excluded; the site shows them as the system maintainers' words.

Rule `LANG-2`: no emoji code points (Unicode `Extended_Pictographic`) in the same file set.

The word "best" has legitimate technical uses ("best effort"). The list is matched as whole phrases; `best effort` and `best-effort` are on an exception list in the gate source. Extending either list is an editorial change to this RFC.

### G9 Secrets and identifiers scan

Rule `SEC-n`: no committed text file, including logs under `results/`, matches any of these patterns. The patterns are compiled in `iproofs.log.patterns` (layer 0, so the import direction respects the module layering of [01](../docs/spec/01-architecture.md#module-boundaries)); `iproofs.validate` and the log redactor both import them (docs/spec/05-observability.md), so what the redactor removes is what the scanner looks for.

| Rule | Pattern (Python `re`) | Target |
|---|---|---|
| `SEC-1` | `hf_[A-Za-z0-9]{30,}` | Hugging Face tokens |
| `SEC-2` | `gh[pousr]_[A-Za-z0-9]{36,}` | GitHub tokens |
| `SEC-3` | `AKIA[0-9A-Z]{16}` | AWS access key ids |
| `SEC-4` | `-----BEGIN [A-Z ]*PRIVATE KEY-----` | private keys |
| `SEC-5` | `(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\d.])` excluding `127.0.0.1`, `0.0.0.0` and version-like strings in a `version` field | IPv4 literals |
| `SEC-6` | IPv6 literals with at least two `:` groups of hex, excluding `::1` | IPv6 literals |
| `SEC-7` | `(?i)\b([0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b` | MAC addresses |
| `SEC-8` | `GPU-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}` | NVIDIA GPU UUIDs |
| `SEC-9` | `(?m)^\s*(Host|HostName|IdentityFile)\s+\S+` in any file | SSH config fragments |
| `SEC-10` | `/home/[a-z_][a-z0-9_-]*/`, `[/]Users/[^/\s]+/` | absolute home paths |
| `SEC-11` | `(?i)(token|secret|password|api[_-]?key|credential)\s*[:=]\s*['"]?[A-Za-z0-9/+_\-]{16,}` | assignments of secret-like values |

Allowlist: `schema/*/examples/invalid/` and `harness/tests/fixtures/secrets/` contain deliberate matches for the scanner's own tests and are skipped. False positives elsewhere are fixed by changing the text, not by allowlisting.

The machine-record fields that RFC-0006 permits (GPU model, driver version, kernel version) do not match these patterns; the scan of `manifest.json` therefore needs no exception.

### G10 Fake-system end-to-end

The fake systems (`systems/fake`, `systems/fake-broken`) are small Python programs in CPU-only images. `systems/fake` commits to toy weights by hashing them, proves by writing a body part and an HMAC-SHA256 tag part, keyed by the commitment, over the request, the claimed output and the body ([RFC-0005](0005-adapter-contract.md#reference-implementations)), and verifies by recomputing it; it is sound for the toy relation, so every shared control except those marked `not_applicable` must be rejected. `systems/fake-broken` uses the same prover and a verifier that always accepts.

Rule `E2E-1`: on the hosted runner, with workload `fake-tiny-ci` (a toy workload with 8 prompt tokens, 1 output token, batch 2, 3 batches per session, defined in `workloads/fake-tiny-ci.yaml`) and profile `ci-cpu` (a profile in `reference/ci.yaml` with no GPU), the job runs:

```
uv run iproofs run --system fake --workload fake-tiny-ci --profile ci-cpu --repetitions 3 --results "$RUNNER_TEMP/results" --control-suite
uv run iproofs run --system fake-broken --workload fake-tiny-ci --profile ci-cpu --repetitions 1 --results "$RUNNER_TEMP/results" --control-suite
uv run iproofs validate --all "$RUNNER_TEMP/results"
```

and asserts:

- three `fake` run directories exist and pass G2 to G5;
- every `fake` honest proof is `accept`, and every applicable shared control is `rejected` (C5, C6 and C8 may be `invalid_call`, per RFC-0008);
- `fake-broken` has every applicable control `accepted`, the controls summary marks it failed, and `iproofs validate` reports nothing wrong with the record itself (a weak verifier is a result, not an invalid file);
- GPU quantities are `null` with `null_reason: not_applicable` on the `ci-cpu` profile;
- re-running `iproofs derive --check` on the produced directories succeeds.

Images for the fake systems are built in the job from `systems/fake*/Dockerfile` with base images pinned by digest. Build cache uses the runner's Docker layer cache keyed by the Dockerfile digest.

### G11 DCO sign-off

Rule `DCO-1`: every commit in the pull request has a `Signed-off-by:` trailer whose name and email match the commit author. Implemented as a small script over `git log --format` in CI (no external service), so it runs identically locally: `uv run python -m iproofs.validate.dco origin/main..HEAD`.

### G12 Link and anchor check

Rule `LNK-1`: every relative Markdown link in `README.md`, `AGENTS.md`, `docs/**`, `rfcs/**`, `reports/**` and `systems/*/README.md` resolves to an existing file, and every `#anchor` resolves to a heading in the target using GitHub's slug rules (lowercase, spaces to `-`, punctuation other than `-` and `_` removed). `LNK-2`: RFC references in text of the form `RFC-NNNN` name an RFC file that exists in `rfcs/`. External links are not fetched in CI (non-deterministic); a weekly scheduled job checks them and opens an issue on failure without blocking merges.

### CI workflow structure

- One workflow file `.github/workflows/ci.yml` with the five jobs above, triggered on `pull_request` and `push` to `main`; plus `.github/workflows/nightly.yml` running `iproofs validate --all` and the external link check on a schedule.
- Runner: hosted Ubuntu 24.04. Python from `uv python install` reading `.python-version` (3.12). Dependencies from `uv sync --frozen` so the lockfile is authoritative and a stale lock fails.
- Caches: uv cache keyed by `uv.lock` digest; Docker layer cache for G10 keyed by the fake Dockerfiles.
- Actions referenced by full commit hash, not tag (PIN rules apply to CI itself).
- Permissions: `contents: read` only. No secrets are available to pull request jobs. No job uploads results anywhere.
- Time budget for the whole workflow: 10 min wall on a hosted runner (target).

### Local use

```
uv sync
uv run iproofs validate                 # tree gates on the working copy
uv run pytest harness/tests -q          # G1 tests
make ci                                 # all CPU gates in CI order, including G10 if docker is present
```

`make ci` is a thin `Makefile` that calls the same commands as the workflow, so local and CI runs cannot drift. Contributors without Docker can run everything except G10.

### What runs on GPU hosts instead

GPU jobs (`iproofs run` on `prover-h100`) run on a GPU host following the runbook in each adapter README and `docs/runbooks/gpu-run.md`. They are not CI gates. Their outputs enter the repository by pull request, where G2 to G9 and G12 check them like any other record. The adapter's own CPU fixture tests (G1) cover the adapter's parsing and mapping logic without a GPU.

### Failure modes of the gates themselves

| Failure | Response |
|---|---|
| A gate has a false positive that blocks a correct change | Fix the gate in its own pull request with a regression test; no bypass |
| A gate silently passes everything (for example a glob matching nothing) | Each gate has a self-test with a known-bad fixture under `harness/tests/fixtures/gates/<gate>/`; the gate's test suite fails if the fixture passes |
| Validation is slow on a large `results/` tree | `--changed-since` limits pull request scope; nightly `--all` keeps the full check |
| A required check is renamed and branch protection silently stops requiring it | Branch protection is documented in `docs/runbooks/repository-settings.md` and reviewed at each release checklist (docs/spec/09-release-and-versioning.md) |

## Alternatives Considered

**Pre-commit hooks as the enforcement point.** Considered because they catch problems before push. Rejected as the enforcement point because they are optional and skippable; the same commands are offered as an optional pre-commit configuration, but CI is authoritative.

**Third-party DCO and secret-scanning services.** Considered because they exist and need no code. Rejected because they cannot be run locally with identical results, add an external dependency to a neutrality-sensitive project, and the secret patterns must match the log redactor exactly.

**Schema checks only, no graph checks.** Considered for simplicity. Rejected because the two most important rules (derived numbers recomputed, ratios carrying their scope) need the derivation graph, which JSON Schema cannot express.

**Running a small GPU job in CI on a self-hosted runner.** Considered for coverage of the measurement code. Rejected for v0.1: a self-hosted GPU runner that executes pull request code is a security risk (untrusted code on a machine with credentials), and the cost is ongoing. The fake system and stored fixtures cover the logic; GPU paths are covered by runbook tests on a maintainer-controlled host.

**A language model or classifier for neutral-language checks.** Rejected: non-deterministic and opaque. A word list is crude but predictable and reviewable.

## Drawbacks

- The word list will produce occasional false positives and will miss paraphrases; reviewers remain responsible for tone.
- POL-3 is a text check and can be evaded by constructing a flag string at run time. G6 POL-1 on recorded command lines is the real control; POL-3 is an early warning.
- Twelve gates are a lot for a contributor to learn; the failure message format and `make ci` mitigate this.
- IPv4 matching flags version-like strings outside `version` fields; authors may need to rephrase.

## Conflicts of Interest

The author's affiliations and any interest in a measured system are declared in `MAINTAINERS.md` before this RFC enters Last call (RFC-0001).

## Migration / Rollout

1. v0.1-alpha: land G1, G2, G3, G11 and G12 first, as they need only schemas and the writer. Mark them required.
2. Land G4 and G5 with the derivation module; G10 with the fake systems; G7 and G9 with their pattern modules. Each becomes required in the pull request that adds it.
3. G6 becomes meaningful when SASH's `system.yaml` lists forbidden flags (v0.1-beta); it is required from the start and passes vacuously before then.
4. Branch protection is set by a maintainer and recorded in `docs/runbooks/repository-settings.md`.

## Testing Strategy

- `harness/tests/unit/validate/test_g3_format.py::test_detects_reordered_keys`, `::test_detects_crlf`, `::test_accepts_canonical`.
- `test_g4_derive.py::test_hand_edited_mean_fails` (edit a stored mean by one ulp with `math.nextafter`, expect `DER-1`), `::test_unknown_formula_fails` (`DER-2`).
- `test_g5_labels.py::test_bare_float_outside_allowlist_fails` (`LBL-4`), `::test_ratio_without_scope_fails` (`LBL-1`), `::test_run_tier_not_reported_fails` (`LBL-3`).
- `test_g6_policy.py::test_nonconforming_run_refused` (`POL-4`), `::test_measured_run_with_unsound_flag_fails` (manifest argv contains `--unsound-skip-x`, `control: false`, expect `POL-1`), `::test_control_run_with_flag_passes`.
- `test_g7_pins.py::test_short_hash_fails` (`eb95bfa`), `::test_tag_only_image_fails` (`python:3.12-slim`), `::test_tag_and_digest_passes`.
- `test_g8_language.py::test_fastest_fails`, `::test_best_effort_passes`, `::test_allow_comment_passes_and_notices`, `::test_reply_files_excluded`, `::test_emoji_fails`.
- `test_g9_secrets.py` one case per pattern `SEC-1` to `SEC-11` using fixtures under `harness/tests/fixtures/secrets/`, plus `::test_machine_record_example_passes` against the RFC-0006 example record, and `::test_redactor_and_scanner_share_patterns` asserting the redactor's pattern list is the scanner's.
- `test_g11_dco.py::test_missing_signoff_fails`, `::test_mismatched_email_fails`.
- `test_g12_links.py::test_missing_anchor_fails`, `::test_github_slug_rules` (headings with punctuation, duplicates get `-1`).
- `test_g10_e2e.py` is the G10 job itself; its assertions are listed in §G10.
- Each gate has a fixture under `harness/tests/fixtures/gates/<gate>/bad/` that the gate must flag, as a guard against a gate that passes everything.

## Open Questions

- OPEN QUESTION Q1 (owner: AbdelStark, resolve by: 2026-12-01): whether G8 should also run on issue and pull request bodies through a workflow. Default: no; repository files only.
- OPEN QUESTION Q2 (owner: AbdelStark, resolve by: 2027-01-31): whether a maintainer-controlled GPU host should run a scheduled smoke job on the default branch (not on pull requests) to catch measurement regressions. Default: no scheduled GPU job in v0.1; runbook tests before each campaign.

## References

- AGENTS.md hard rules 2 to 4, 6, 7 and 10, and working practice.
- [RFC-0012](0012-schemas-and-serialization.md) for the writer, quantities and digests.
- [RFC-0004](0004-metrics-timing-grades.md) for formulas, [RFC-0005](0005-adapter-contract.md) for `system.yaml`, [RFC-0008](0008-negative-controls.md) for controls.
- Developer Certificate of Origin 1.1, https://developercertificate.org/
- GitHub Markdown heading anchor rules.
