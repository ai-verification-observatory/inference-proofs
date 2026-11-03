# Writing an adapter

This page is for a prover team, or a contributor with the team's consent, who wants a system measured. An adapter is a thin wrapper around the upstream tools, pinned at a full commit hash. It never patches upstream source and never passes an option the upstream documentation does not name (AGENTS.md rule 1, INV-ADAPTER-1). The normative rules are the RFCs linked from each section; this guide restates none of them differently. Where the two disagree, the RFC wins.

`systems/fake` is the worked example: a complete adapter in one standard-library Python file that CI runs end to end ([Walkthrough](#walkthrough-systemsfake)).

## 1. Ask first

A system is added only with its team's consent ([RFC-0001 §Adding and removing a system](../rfcs/0001-process-and-governance.md#adding-and-removing-a-system), INV-GOV-5).

1. Open a system inclusion issue. Name the upstream repository, the full commit hash, the workloads the system supports and at least one system maintainer.
2. A person listed as an author or maintainer upstream at that commit gives consent on the issue, or links a public statement.
3. The adapter, `system.yaml` and `claim.yaml` land by pull request. The claim card stays unreviewed (`reviewed_by: []`) until the system maintainers review it. System maintainers are added to [MAINTAINERS.md](../MAINTAINERS.md).

## 2. Directory layout

The files are listed in [RFC-0005 §Layout](../rfcs/0005-adapter-contract.md#layout): `Dockerfile`, `entrypoint`, `system.yaml`, `claim.yaml`, optional `external.yaml` and `controls.yaml`, `README.md`, `tests/` and `replies/`. The system name matches `^[a-z][a-z0-9-]{1,31}$`.

## 3. `system.yaml`

The shape and every field rule are in [RFC-0005 §system.yaml](../rfcs/0005-adapter-contract.md#systemyaml); the schema is [`schema/system/1.schema.json`](../schema/system/1.schema.json). The fields that need the most care:

- `upstream.commit`: 40 lowercase hex characters, the commit the Dockerfile checks out and verifies (INV-ADAPTER-2).
- `proofs.granularity`, `proofs.tokens_covered`, `proofs.steady_boundary`: what one proof directory holds, how tokens are counted and where `prove.steady` starts. `incremental_proofs: false` requires `steady_boundary: not_observable` (INV-ADAPTER-10).
- `forbidden_flags`: argument prefixes that weaken the system's statement. They are allowed only in negative-control jobs ([RFC-0005 §Weakening configurations](../rfcs/0005-adapter-contract.md#weakening-configurations), [RFC-0008](../rfcs/0008-negative-controls.md)).
- `timeouts_s`: declare a step only if it needs more than the defaults; reviewers see the value.

`uv run iproofs validate systems/<name>` checks the file against its schema.

## 4. What the container may do

The harness is the only caller and starts every subcommand with the flags in [RFC-0005 §Container invocation](../rfcs/0005-adapter-contract.md#container-invocation). For an adapter author this means:

- No network in any subcommand, including `setup`. Everything needed at run time is in the image or under `/models` (INV-ADAPTER-4).
- A read-only root file system. Write only under `/io` and `/tmp`. State that must survive between steps of one job goes under `/io/state/`.
- A non-root user, uid 10001 by convention, declared with `USER` in the Dockerfile.
- `verify` gets no GPU, no `/models` and a memory limit. A verifier never sees the weights.
- Recorded commitment files are mounted read-only. The commitment `verify` checks comes from the harness's record of `commit`, never from anything `prove` writes (AGENTS.md rule 6, INV-ADAPTER-5, [RFC-0014 §The commitment record](../rfcs/0014-provenance-and-integrity.md#the-commitment-record)).

## 5. Subcommands, `job.json` and `out.json`

`entrypoint <info|setup|commit|prove|verify> /io/job.json /io/out.json`. The common fields and the per-subcommand fields are in [RFC-0005 §Subcommands and file shapes](../rfcs/0005-adapter-contract.md#subcommands-and-file-shapes); the schemas are [`adapter-job/1`](../schema/adapter-job/1.schema.json) and [`adapter-out/1`](../schema/adapter-out/1.schema.json). Exit 0 when the subcommand completed its task, whatever the verdict; a rejected proof is exit 0 with `verdict: "reject"`.

Every path you write in `out.json` is absolute under `/io` or `/models`, or a file name inside a named directory. Anything that escapes the job io dir, a symlink or device file under `/io/proofs/`, or a proof over the part caps is an `adapter` failure ([RFC-0005 §Path safety](../rfcs/0005-adapter-contract.md#path-safety)).

## 6. Releasing proofs

The harness times proofs by watching the file system ([RFC-0005 §Proof release protocol](../rfcs/0005-adapter-contract.md#proof-release-protocol)). Write every part of a proof into `/io/proofs/.tmp-<proof_id>/`, then `rename` it to `/io/proofs/<proof_id>` in one call. Do not touch a proof after its rename. The `proof_id` values in `out.json` must equal the released directories, one to one (INV-ADAPTER-6).

## 7. The command log

Append one JSON line per upstream process you start to `/io/commands.jsonl`, with `argv`, `cwd`, `started_mono_ns` and `exit_code`, and no environment ([RFC-0005 §Command log](../rfcs/0005-adapter-contract.md#command-log)). The policy gate reads these lines to check that no forbidden flag reached a measured run ([RFC-0013 §G6](../rfcs/0013-validation-and-ci.md#g6-policy-check)). A source line that names a forbidden flag must sit behind a `control` guard and be listed in `systems/<name>/policy-allow.txt` (rule POL-3).

## 8. Verdicts

Map the upstream verifier's own signals onto `accept`, `reject`, `no_verdict` and `invalid_call`, and exit non-zero for any signal you cannot map; never guess a verdict ([RFC-0005 §Verdict normalisation](../rfcs/0005-adapter-contract.md#verdict-normalisation)). Put the mapping table in your README, with links at the pin.

## 9. The Dockerfile

Follow rules B1 to B7 of [RFC-0014 §Adapter image build](../rfcs/0014-provenance-and-integrity.md#adapter-image-build): base images by digest; one `fetch` stage that downloads every input, verified against `systems/<name>/inputs.lock`; `RUN --network=none` after it; no patch or `sed` over upstream source; `/opt/iproofs/inputs.json` returned by `info`; a clean-tree build with the adapter commit baked in; release images pushed and referenced by manifest digest. A run is eligible for a release only from a clean build of a pushed image ([RFC-0014 §Eligibility](../rfcs/0014-provenance-and-integrity.md#eligibility)); local builds are recorded with `digest_kind: config` and never are.

`systems/<name>/inputs.lock` lists every downloaded input, one per line, `<name>\t<url>\tsha256:<hex>`; the fetch stage uses `ADD --checksum=sha256:<hex> <url>` for each. Pass the adapter commit and dirty flag as build arguments and return them from `info` (`adapter_commit`, `adapter_dirty`), with `image_inputs` read from `/opt/iproofs/inputs.json`. `systems/fake/Dockerfile`, `systems/fake/inputs.lock` and `systems/fake/write_inputs.py` are the reference. Each adapter's `tests/test_dockerfile_rules.py` calls `iproofs.provenance.dockerfile_problems(dockerfile, inputs_lock)`, which checks B1 to B3.

Gate G7 checks pins in every Dockerfile ([RFC-0013 §G7](../rfcs/0013-validation-and-ci.md#g7-pin-check)).

## 9a. System-specific controls

Register controls from your upstream suite in `systems/<name>/controls.yaml` (schema `system-controls/1`, [RFC-0008 §System-specific controls](../rfcs/0008-negative-controls.md#system-specific-controls)). The harness runs them after the shared controls and records them with `source: system`:

- `weakened_prover`: the harness runs `prove` in its own io dir with `control: true` and `control_flags` passed explicitly, then verifies every proof with the run's recorded commitment. With `requires_unbound_edge`, the control passes only if your `out.json` `binding_report` marks that edge unbound: a JSON object with `edges`, either `{"<edge>": "bound" | "unbound"}` or a list of `{edge, state}`. This shows the switch is honest and the claim card's binding table accurate.
- `fixture_proof`: an upstream-supplied proof verified as is. Until RFC-0008 Q5 says how its bytes reach the harness, it is recorded as `not_applicable` with that reason.

`harness/tests/fixtures/controls/fake-broken-controls.yaml` shows one control of each kind.

## 10. Fixture tests

Every adapter ships CPU-only tests in `systems/<name>/tests/` that run the entrypoint logic against stored fixtures, including the verdict mapping for every documented exit code (INV-ADAPTER-9). Capture the fixtures once on a GPU host:

- Capture small text outputs: the upstream verifier's stdout and stderr lines, exit codes, the last line, the shape of any JSON or log the adapter parses.
- Never capture weights, prompts beyond the workload's own test prompts, or large proofs. Keep each fixture small; files over 5 MiB fail gate G2 (SIZE-1).
- Redact before committing: no host names, IP addresses, user names or home paths (AGENTS.md rule 7). Gate G9 rejects them.
- Record next to the fixtures the upstream commit, the image digest and the command that produced each one.

`uv run pytest systems/<name>/tests` must pass on a laptop with no GPU. CI runs it as gate G1.

## 11. The adapter README

`systems/<name>/README.md` documents the seven items of [RFC-0005 §Adapter README requirements](../rfcs/0005-adapter-contract.md#adapter-readme-requirements), each with a link to upstream documentation at the pinned commit. Copy this checklist into the pull request description and tick each item with the section that covers it:

```
- [ ] 1. Upstream tools each subcommand calls, and every argument passed
- [ ] 2. Verdict mapping table
- [ ] 3. How commitment_id, verifier_files and prover_files map onto upstream artefacts
- [ ] 4. The values under `proofs` in system.yaml, and why
- [ ] 5. Toolchain versions, and why they match upstream
- [ ] 6. Upstream CPU binding advice, and how the harness binding satisfies it
- [ ] 7. Known deviations from upstream's own measuring setup
```

Run instructions in the README follow the host prerequisites, GPU-host tests and campaign procedure of [`docs/runbooks/gpu-run.md`](../docs/runbooks/gpu-run.md) and add only what is specific to the adapter (its smallest workload, setup time, known resource needs).

The claim card copies what the upstream documentation states at the pin and writes "not stated" where it is silent ([RFC-0002 §Rules](../rfcs/0002-claim-card.md#rules), AGENTS.md rule 9).

## Walkthrough: `systems/fake`

The fake system implements the whole contract on CPU with a keyed hash instead of a proof system. Read it beside the sections above.

| File | What it shows |
|---|---|
| [`fake/system.yaml`](fake/system.yaml) | a minimal manifest: `kind: test`, one workload, `proofs` values, `forbidden_flags`, short `timeouts_s` |
| [`fake/entrypoint`](fake/entrypoint) | the five subcommands; `prove` releases each proof through `.tmp-<id>` and a rename and logs to `/io/commands.jsonl`; `prove` refuses a forbidden flag outside a control job; `verify` maps its result onto the four verdicts |
| [`fake/Dockerfile`](fake/Dockerfile) | a base image by digest, the upstream commit passed as a build argument, `USER 10001` |
| [`fake/policy-allow.txt`](fake/policy-allow.txt) | the one source line that names a forbidden flag, with its guard |
| [`fake/tests/test_fake.py`](fake/tests/test_fake.py) | CPU tests of the entrypoint |
| [`fake/README.md`](fake/README.md) | the subcommand table, the `proofs` values and why |

The fake has no build-time downloads, so it shows B1 but not the `fetch` stage of B2 to B5. Its proofs are not proofs of anything about a model.

To run it: `uv run iproofs run --system fake --workload fake-tiny-ci --profile ci-cpu --repetitions 1 --results "$(mktemp -d)" --in-process` runs the entrypoint as a local process and writes the run directory outside the repository. With Docker, `make e2e` builds the image and runs every step in a hardened container, including the negative-control suite (gate G10). Do the same for your adapter on a GPU host before you open the pull request; [`fake-broken`](fake-broken/README.md) shows what the control suite reports for a verifier that accepts everything.
