# RFC-0008: Negative controls

- Status: Draft
- Authors: AbdelStark
- Created: 2026-11-03
- Target milestone: v0.1-alpha (harness and fake systems); v0.1-beta (SASH and FlashProve)
- Requires: RFC-0005, RFC-0010, RFC-0012
- Supersedes: none
- Discussion: pull request that introduces it

## Summary

Every system's verifier faces the same set of tampering tests after an honest run, plus tests from the system's own suite. The harness, never the adapter, produces every tampered input. Each control runs next to an honest twin that must be accepted; when the twin is not accepted the control is void, so a broken control or a broken run cannot pass for a strong verifier. Each row reports controls run, rejected, accepted, `no_verdict`, `invalid_call`, void, not applicable and errored. An accepted control where rejection was expected triggers private disclosure to the system maintainers before publication.

## Motivation

Speed is half of a result. A proof system is useful when its verifier rejects what it should ([PRD G4](../docs/PRD.md#4-goals)). Both first systems ship their own rejection tests: FlashProve's `examples/rejected-proofs`, and SASH's `--unsound-skip-*` switches, which unbind one edge each and show what each binding buys (PRD, Section 1). A shared suite lets readers see the same attacks applied to every system, and it is the benchmark's defence against a faulty or dishonest adapter: an adapter that maps every verify call to `accept` fails every shared control ([06-security](../docs/spec/06-security.md)).

## Goals

- A fixed shared suite (C1 to C8 verifier side, P1 and P2 prover side) with exact, seeded, deterministic mutation algorithms.
- Mutations applied by the harness to opaque proof bytes and request fields; no adapter cooperation needed beyond the `adapter/1` contract.
- Every control paired with an honest twin; void controls reported as void.
- A closed outcome vocabulary and a per-control expected set, so pass and fail are mechanical.
- A registry for system-specific controls, including controls that expect `accept` (SASH unsound switches).
- A disclosure rule for accepted controls.

## Non-Goals

- Structured fuzzing of proof formats. It needs each system's format specification; a later RFC.
- Certifying soundness. A passed suite shows these attacks were rejected, nothing more ([PRD Section 5](../docs/PRD.md#5-non-goals)).
- Controls on the binding between a proof and served traffic. No v0.1 system claims that binding.
- Measuring the cost of controls as benchmark numbers. Control verify times are kept in `controls.json` but never published as rows.

## Proposed Design

### Where controls run

`iproofs run ... --control-suite` runs the suite once per configuration, after the honest `verify` step of the first successful repetition (controls test the verifier, not run-to-run variance, and each prover-side control costs a proving run), and `iproofs controls RUN_DIR` runs it against a completed run ([RFC-0010](0010-harness-runner.md)), whole or in parts on several hosts (§Split suites). Inputs: the run's honest proofs, requests, claimed outputs and the harness's commit record. Every mutated input is written by the harness into a fresh verify io dir; the adapter's `verify` subcommand runs unchanged (INV-CTRL-1).

### Seeds

Every control job derives its randomness from one 64-bit `control_seed`, drawn by the harness from `os.urandom` at the start of the control suite (for a split suite, once before its first part, SPLIT-1) and recorded in `controls.json`. No operator chooses it: `iproofs controls` takes no seed for a whole suite. Per-control randomness uses `random.Random(f"{control_seed}:{control_id}:{k}")` with `.random()` only, the method CPython guarantees stable across versions; an index in `[0, m)` is `floor(r * m)`. Rerunning with the recorded seed reproduces every mutation byte for byte (INV-CTRL-3).

### Split suites

Amendment of 2026-11-09 (owner request of 2026-11-08: every control's data as soon as possible; the RFC stays Draft). A suite may run in parts, on several hosts at once, and be merged into the `controls.json` one run writes. Every other rule of this RFC holds for each control in each part.

- SPLIT-1. One seed, drawn once. `iproofs controls RUN_DIR --draw-seed` draws `control_seed` from `os.urandom` and writes it, with the UTC time it was drawn, the run id and the sha256 of the run's `manifest.json`, to `RUN_DIR/controls-seed.json` (`controls-seed/1`, [RFC-0012](0012-schemas-and-serialization.md)). It refuses when that file or `controls.json` exists, so a run has one seed record and one suite. Every part takes its seed from that record (`iproofs controls RUN_DIR --only ID[,ID...]`); `--seed SEED`, hex or decimal, only confirms it and is refused when it differs, and is refused without `--only`. A whole suite is refused once a seed record exists. Every attempt at a part, finished or stopped, is listed in the campaign's record.
- SPLIT-2. Whole controls. A part runs whole controls, each with its honest twins in the same part (INV-CTRL-2) and its mutations from `control_seed` and its own id (INV-CTRL-3); C6's five trials and its twin stay together. A control's record therefore does not depend on which other controls ran in its part. A part that would record a control differently from a single run is refused before any call: P1 when a perturbed commitment exists but its weights are not in this host's cache.
- SPLIT-3. One run, one image, the run's profiles. Every part runs against the same run directory (its run id and the sha256 of its `manifest.json`), in the run's image, with the same harness version and commit and a checkout clean in `harness/`, `systems/<system>/`, `schema/` and `reference/`. Verifier-side controls run on hosts of the run's verifier profile, prover-side controls (P1, P2, `weakened_prover`) on hosts of the run's prover profile, and every part binds its verify calls to verifier-cpu's CPU count (`cpu.logical_cpus`), with or without a GPU. A prover-side part on a GPU other than the one in the run's machine record is refused. A host that cannot prove (no GPU on a GPU profile, or a host that binds a verifier only) refuses a prover-side control before any call, so a prove that cannot run there never reads as `prover_failed`. Every other profile check the host does not meet ([RFC-0006](0006-reference-hardware-and-cost.md) conformance, for a verifier-only host verifier-cpu's memory) is recorded in the part, not refused.
- SPLIT-4. Parts. A part is a `controls-part/1` document ([RFC-0012](0012-schemas-and-serialization.md)) named `controls-part-<16 hex of the seed>-<12 hex of the sha256 of the subset>.json`. It holds the subset, the whole suite in `controls.json` order, what SPLIT-1 and SPLIT-3 name (seed and the sha256 of the seed record; run id and manifest digest; image; verifier and run profiles; verifier CPU count; perturbed commitment; harness version, commit and dirty flag), the host it ran on (its RFC-0006 machine record and the profile checks it does not meet, which parts need not share), then the subset's records. It is a working file, kept with the run's evidence and never in `results/`: the merged `controls.json` holds every trial's `seconds`, and the parts say which host measured which. Each control call that returns logs `control.call` (control, trial, subcommand, exit code, seconds) in the run's `harness.jsonl`, so a part shows its progress and a stopped part leaves its finished calls' spans.
- SPLIT-5. Merge. `iproofs controls RUN_DIR --merge PART...` needs RUN_DIR's `run.json`, `manifest.json` and `controls-seed.json`, and refuses, with a `config` error and nothing written: a part not valid against `controls-part/1`, not made against RUN_DIR or not run with its seed record; parts that differ in any field SPLIT-4 lists before the host; a part whose records are not its subset; a control in two parts, in no part, or outside the suite; an existing `controls.json`. It writes the records in suite order, recomputes `summary` (INV-CTRL-5) and `disclosure_pending`, and checks the document against `controls/1`. The merged file is written next to the stored run it belongs to, where the refusal of an existing `controls.json` applies; `iproofs controls --only` on a run that has `controls.json` is refused too.
- SPLIT-6. A part that stops before its end (deadline, cancelled job, host failure) writes no part. Its controls run again in a new part, with the same seed record, which reproduces their mutations byte for byte, and with a deadline sized from the stopped part's `control.call` spans; the stopped job's log stays in the campaign record (AGENTS.md rule 5). A control whose call failed is not rerun: its `error` outcome is in its part.

### Proof selection

Controls act on honest proofs that the run's own `verify` step accepted. The harness picks `target` = the first accepted proof in release order, and for controls that need two requests, `other` = the next accepted proof in release order with a different request. If the run has no accepted proof, every control is `void`.

### Shared controls, verifier side

All are applied to honest proofs. `vocab_size` comes from the workload's model record ([RFC-0003](0003-workloads.md)).

| ID | Control | Expected set |
|---|---|---|
| C1 | change the claimed output token | {`reject`} |
| C2 | change one prompt token in the request | {`reject`} |
| C3 | verify against the commitment of perturbed weights | {`reject`} |
| C4 | replay a valid proof for a different request | {`reject`} |
| C5 | truncate the largest part the verifier reads | {`reject`, `invalid_call`} |
| C6 | flip one bit at a seeded offset in a seeded part the verifier reads, 5 seeds | {`reject`, `invalid_call`} for each seed |
| C7 | swap the proofs of two requests in one batch | {`reject`} |
| C8 | drop one part the verifier reads | {`reject`, `invalid_call`} |

Algorithms (pseudo-code; `rng(cid, k)` is the seeded generator above; `read(target.parts)` is the target's parts that the adapter declares its verify step reads, §Parts the verifier reads):

```
C1: out = target.claimed_output.copy(); i = len(out) - 1
    out[i] = (out[i] + 1) mod vocab_size
    verify(commit, request=target.request, claimed_output=out, proof=target.proof)

C2: req = target.request.copy(); p = floor(rng("C2",0).random() * len(req))
    req[p] = (req[p] + 1) mod vocab_size
    verify(commit, request=req, claimed_output=target.claimed_output, proof=target.proof)

C3: verify(commit_perturbed, request=target.request,
           claimed_output=target.claimed_output, proof=target.proof)

C4: verify(commit, request=other.request, claimed_output=other.claimed_output, proof=target.proof)
    # applicable iff other exists and other.request != target.request

C5: part = argmax_by(size, then name) over read(target.parts)
    write part truncated to floor(size/2) bytes; other parts unchanged; verify(commit, target fields, mutated proof)

C6: for s in 0..4:
      parts = sorted(read(target.parts) by name)
      part = parts[floor(rng("C6",2s).random() * len(parts))]
      off  = floor(rng("C6",2s+1).random() * size(part) * 8)   # bit offset
      flip bit (off mod 8) of byte (off div 8); verify(commit, target fields, mutated proof)
    # one outcome per seed; C6 passes iff all five outcomes are in the expected set

C7: pick two accepted proofs a, b from the same batch with a.request != b.request
    verify(commit, request=a.request, claimed_output=a.claimed_output, proof=b.proof)
    # applicable iff batch_size >= 2

C8: parts = sorted(read(target.parts) by name); q = parts[floor(rng("C8",0).random() * len(parts))]
    proof directory without q; out.json parts list without q; verify(commit, target fields, mutated proof)
    # applicable iff len(target.parts) >= 2 (every part, read or not)
```

`commit_perturbed` (C3) is the commitment of the workload's weights with one tensor perturbed: the harness copies the model directory, selects the weight tensor with the lexicographically first name among tensors of at least 1,024 elements, and adds one unit in the last place to element 0 at the stored precision. Because committing a full model is expensive (FlashProve's full-size route needs about 330 GB of host memory to start committing, per [RFC-0006](0006-reference-hardware-and-cost.md)), the perturbed commitment is created once per workload per release by `iproofs controls --prepare-perturbed WORKLOAD` and reused; its commit record carries its own digest and is stored under `results/<release>/<system>/_controls/<workload>/`. The perturbed weights never leave the runner's host. C3 is `not_applicable` if the system cannot commit the perturbed model (for example a fixed-architecture loader that rejects it); the reason is recorded.

### Parts the verifier reads

Amendment of 2026-11-09 (finding of a development run on Hugging Face Jobs, 2026-11-09; the RFC stays Draft). A control that mutates a part the adapter's `verify` never reads tests nothing: the mutated bytes never reach the verifier, and an `accepted` outcome then says nothing about the system. In that run (FlashProve, `fp-maverick-w1024-b1`, a development `controls.json` kept with the campaign's record, not under `results/`), C6 seeds 0 and 3 flipped bits of `response.proof` and were rejected (`NO: proof-refused`); seeds 1, 2 and 4 flipped bits 9, 16 and 28 of `response.y`, the 4-byte next-token word `cp_prove` writes, and were accepted, so C6 recorded `accepted`. The adapter's `verify` writes the token file `cp_verify` checks from the job's `claimed_output`, taken from the harness record (INV-CTRL-6), and passes `response.proof` alone, so `response.y` never reaches the verifier ([`systems/flashprove/README.md`](../systems/flashprove/README.md#values-for-systemyaml)). C1, which changes the claimed output token, covers the attack a changed `response.y` would stand for. This is a gap in the control design, not a finding against FlashProve: no disclosure follows from it (§Disclosure), and no row shows FlashProve failing a control because of it.

- READ-1. Declaration. `system.yaml` `proofs.verify_reads` (optional in `system/1`, [RFC-0005](0005-adapter-contract.md#systemyaml)) declares which proof parts the adapter's `verify` reads: `"all"`, or `{read: [part, ...], not_read: [{part, reason}, ...]}` with both lists non-empty and every name a file name of `out.json` `parts[]`. Absent means `"all"`, the rule before this amendment. The declaration is static, reviewed with the adapter, and read by the harness from the checkout without a container call; every part of a split suite reads the same one (SPLIT-3, one harness commit). The adapter README says, with links at the pin, why each part is not read, and a prover adapter declares the field even when it reads every part (a review rule: `system/1` keeps the field optional, so the files written before stay valid).
- READ-2. Fit. Before any call of the suite, or of a part of it, the harness checks the declaration against the target proof (§Proof selection): a declared part the proof does not have, a part of the proof the declaration does not place, or a part placed twice is refused with a `config` error, and nothing is written.
- READ-3. Candidates. C5, C6 and C8 choose their part among the parts read only: each algorithm's candidate list is `read(target.parts)`, sorted by name as before. The seeds, the generator calls, the offsets, the applicability rules and the expected sets are unchanged, and C8's precondition still counts every part, so a mutated proof keeps at least one part. With `"all"`, every mutation is byte for byte the one this RFC specified before the amendment.
- READ-4. Record. Each C5, C6 and C8 record in `controls.json` lists every part not read, with its declared reason, in `parts_not_read` (an optional `controls/1` property, absent when every part is read). C1 to C4 and C7 mutate no part and list none.
- READ-5. Stored files. A `controls.json`, part or seed record written before this amendment stays as recorded: it is never edited and its outcomes are never recomputed under the new candidate lists (append-only, [RFC-0009](0009-results-and-publication.md)). A rerun of the suite is a new record, made as §Where controls run says, with its own seed, never written over the earlier file. No `controls.json` under `results/` predates this amendment.

### Shared controls, prover side

| ID | Control | Expected set |
|---|---|---|
| P1 | commit W, prove with W' (the C3 perturbation) | {`prover_failed`, `reject`} |
| P2 | prove with a precision other than the committed one | {`prover_failed`, `reject`}; `not_applicable` when the system supports one precision |

P1 runs a `prove` job with `model_dir` pointing at W' and `commitment_id` from the commit of W, at the workload's smallest batch, `batches: 1`. If `prove` exits non-zero, the outcome is `prover_failed`. If it produces a proof, the harness verifies it against the commit of W; the expected verdict is `reject`. P2 uses the same procedure with a model directory converted to another precision only if the workload declares an alternative precision; otherwise `not_applicable`. Prover-side controls run with `control: true` and never produce measured rows.

### Honest twins

Each verifier-side control runs its honest twin first: `verify(commit, target.request, target.claimed_output, target.proof)` on unmodified bytes, in the same control batch, with the same image digest and the same verifier profile. For C4 and C7 both proofs involved get a twin. If any twin is not `accept`, the control's outcome is `void` (INV-CTRL-2). For P1 the twin is the run's own honest prove and verify.

### Outcomes

`outcome` is one of: `rejected` (verdict `reject`), `accepted` (verdict `accept`), `no_verdict`, `invalid_call`, `void`, `not_applicable`, `error` (adapter or harness failure during the control, with the failure record), and for prover-side controls `prover_failed`. A control **passes** iff its outcome (or, for C6, every per-seed outcome) is in its expected set, mapping `reject` to `rejected`. A control that is `void`, `not_applicable` or `error` neither passes nor fails; it is counted separately.

### controls.json

Generated JSON, schema `controls/1` ([RFC-0012](0012-schemas-and-serialization.md)):

```json
{
  "schema": "controls/1",
  "run_id": "2026-11-03-fake-fake-tiny-ci-ci-cpu-1",
  "control_seed": "0x5f3c9a12d4e6b780",
  "image": "ghcr.io/<org>/iproofs-fake@sha256:<64 hex>",
  "verifier_profile": "verifier-cpu",
  "perturbed_commitment": {"commitment_id": "...", "model_digest": "sha256:..."},
  "controls": [
    {
      "id": "C6", "side": "verifier", "source": "shared",
      "expected": ["rejected", "invalid_call"],
      "twin": {"verdict": "accept", "raw_exit_code": 0},
      "trials": [
        {"seed_index": 0, "mutation": {"part": "tag.bin", "bit_offset": 117}, "verdict": "reject",
         "outcome": "rejected", "raw_exit_code": 1, "raw_last_line": "...", "seconds": 0.012}
      ],
      "outcome": "rejected", "passed": true, "note": null
    }
  ],
  "summary": {"run": 10, "passed": 8, "rejected": 8, "accepted": 0, "no_verdict": 0,
              "invalid_call": 0, "void": 0, "not_applicable": 2, "error": 0, "prover_failed": 0}
}
```

`seconds` is adapter-reported verify time for the trial; `summary` counts are derived by CI from `controls` and recomputed by `iproofs derive --check` (INV-CTRL-5).

### System-specific controls

`systems/<name>/controls.yaml` (schema `system-controls/1`, an optional file) registers controls from the upstream suite:

```yaml
schema: "system-controls/1"
controls:
  - id: "flashprove-rejected-proofs"         # ^[a-z0-9-]{3,64}$, unique per system
    kind: "fixture_proof"                     # fixture_proof | weakened_prover
    description: "upstream examples/rejected-proofs at the pin"
    source: "https://github.com/anthropics/FlashProve/tree/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/examples/rejected-proofs"
    expected: ["rejected"]
  - id: "sash-unsound-skip-<edge>"
    kind: "weakened_prover"
    control_flags: ["--unsound-skip-<edge>"]  # exact flag names copied from upstream docs at the pin
    expected: ["accepted"]
    requires_unbound_edge: "<edge>"           # pass iff the binding report marks this edge unbound
```

- `fixture_proof` controls verify an upstream-supplied proof as is; the twin is the run's honest proof.
- `weakened_prover` controls run `prove` with `control: true` and `control_flags`, then `verify`. SASH's unsound switches are registered this way with expected `accepted`; the control passes only if the run's binding report (out.json `binding_report`) marks the corresponding edge unbound. The point is to show the switch is honest and the claim card's binding table is accurate, not that the verifier catches it ([RFC-0002](0002-claim-card.md)).
- The list of edges and flag names is copied from upstream documentation at the pin by the SASH adapter issue; this RFC does not enumerate them.

### Applicability

A control is `not_applicable`, with a recorded reason, when its precondition fails: C4 without a second distinct request; C7 with batch size 1 or no two accepted proofs in one batch; C8 with a single part; C3 and P1 when the perturbed commitment cannot be created; P2 when the workload has one precision. Applicability is decided before the twin runs.

### Reporting

Per row the site and release index show: controls run, passed, rejected, accepted, `no_verdict`, `invalid_call`, void, not applicable, error ([RFC-0009](0009-results-and-publication.md)). Every `accepted` outcome where rejection was expected is printed in the row in full (control id, mutation, raw last line). Every `no_verdict` is listed.

### Disclosure

An accepted control where rejection was expected is a possible soundness or adapter defect. The harness marks the run `disclosure_pending: true` in `controls.json`, and the runner reports privately to the system maintainers through the channel in the system's security policy, or, when none is published, through the contact in `system.yaml` maintainers. The finding is published in full at the earlier of: upstream publishing a fix or advisory, or 90 days after the report. A system's own published policy applies where it sets a different period. The release that contains such a run states that a disclosure is pending without the details until the embargo ends (`SECURITY.md`, RFC-0001; [06-security](../docs/spec/06-security.md)). Before disclosure, the runner checks the adapter: a fault in the verdict mapping is fixed in this repository and the run is redone; it is not a finding against the system.

### Invariants

- **INV-CTRL-1:** Every mutated input is produced by the harness; adapters never receive a request to mutate anything.
- **INV-CTRL-2:** A control whose honest twin is not `accept` is `void`, never `rejected`.
- **INV-CTRL-3:** Every mutation is a deterministic function of `control_seed`, the control id and the honest inputs.
- **INV-CTRL-4:** A control job never produces a measured row, and a measured row never comes from a job with `control: true`.
- **INV-CTRL-5:** `summary` in `controls.json` equals the counts recomputed from `controls`.
- **INV-CTRL-6:** The commitment in every control verify call comes from the harness's commit records (the run's or the perturbed one), never from proof files.
- **INV-CTRL-7:** A `controls.json` merged from parts (§Split suites) is byte for byte the one a single run of the suite with the same `control_seed` writes from the same verify results.
- **INV-CTRL-8:** C5, C6 and C8 never mutate a part the adapter declares its verify step does not read, and their records list each such part with its reason (§Parts the verifier reads).

### Failure modes

| Failure | Response |
|---|---|
| Twin not accepted | control `void`; the run's honest verify result is cross-checked and a mismatch is logged as event `control.twin_mismatch` |
| Adapter exits non-zero during a trial | outcome `error` with the failure record; other controls continue |
| Perturbed commitment cannot be created | C3 and P1 `not_applicable` with reason |
| Mutation produces bytes identical to the original (for example C1 with `vocab_size` 1) | harness asserts the mutated input differs; if not, `error` kind `internal` |
| Verify timeout during a trial | outcome `error` kind `timeout` |
| `proofs.verify_reads` does not fit the target proof (READ-2) | `config` error before any call; nothing written |
| Accepted where rejection expected | `disclosure_pending: true`; private report; embargo rule |

## Alternatives Considered

1. **Adapters implement their own tampering.** Considered because adapters understand their proof formats and could make semantically targeted mutations. Rejected: the measured party would author its own tests, and a mapping bug could hide behind a matching mutation bug. Harness-side byte and field mutations are weaker but neutral.
2. **No honest twin; compare against the run's original verify.** Considered because it halves verify calls. Rejected: a control batch can run in a different container, with different files or a corrupted io dir; only a twin in the same batch shows the verify path itself works for the unmodified input.
3. **Random fuzzing with many seeds.** Considered for coverage. Rejected for v0.1: verify on FlashProve costs about 21 s per proof on one CPU thread (grade external, tier reported, source FlashProve docs at `9e2bdd8ff5bf9c62f18263d7dac189b0400b260c`), so hundreds of trials per row cost hours of CPU; five seeded bit flips plus a truncation catch the gross failures. A structured mutation suite is a later RFC.
4. **Pass or fail only, without `void`, `not_applicable`, `error`.** Rejected: it would hide whether a control actually tested anything.
5. **Declare the parts read in the adapter's `info` output** (§Parts the verifier reads). Considered because `info` already reports what the image holds. Rejected: `info` is the measured party's answer at run time, from inside the container; `system.yaml` is reviewed with the adapter README that explains it, the harness reads it before any call, and split parts read the same file at one commit.
6. **Let the adapter's verify step reject a mutated part it does not need** (for example compare `response.y` with `claimed_output`). Rejected: it changes the adapter's `verify` to make a control pass, and the check would test code the adapter added, not the system; C1 already tests the claimed token.
7. **Public immediate disclosure of accepted controls.** Considered for transparency. Rejected: an accepted control may be a real soundness bug in a deployed system; a bounded embargo is standard practice and the finding is still published.

## Drawbacks

- Byte-level mutations do not test semantic attacks a format-aware adversary would try; passing C5 and C6 shows integrity checking, not soundness.
- C3 and P1 require committing a second, perturbed model once per workload per release, which for the Maverick workloads is costly in host memory and time.
- Verify calls on real systems multiply verifier CPU time per row by roughly the number of trials plus twins (about 22 calls for the shared suite, a count of calls, not a measurement).
- System-specific controls depend on upstream suites, so coverage differs between systems; rows show which controls ran.
- `proofs.verify_reads` names parts by file name. A system whose part names vary between proofs and that leaves some part unread cannot declare it; it would need a pattern form, in a later amendment. SASH and FlashProve do not need one.
- The declaration is the adapter author's statement, checked by review against the adapter's `verify` code and README, not by the harness. A part wrongly declared not read is never mutated; its name and reason are printed in every C5, C6 and C8 record, where review can see it.

## Conflicts of Interest

None declared.

## Migration / Rollout

- Replaces the draft control list of the initial design commit; IDs C1 to C8, P1, P2 are kept, C6 is fixed at five seeds and gains exact algorithms.
- v0.1-alpha: harness mutations and classification, tested against `systems/fake` (all shared controls pass) and `systems/fake-broken` (every applicable verifier-side control `accepted`).
- v0.1-beta: suite runs on SASH and FlashProve rows, plus registered system-specific controls.
- Split suites (amendment of 2026-11-09) change no control, algorithm, expected set or `controls/1` field; they add the `controls-seed/1` record, the `controls-part/1` working file, the `control.call` log event and the `--draw-seed`, `--only`, `--seed`, `--merge`, `--hosted`, `--gpu` and `--provider` options of `iproofs controls`. A merged file is a `controls.json` like any other (INV-CTRL-7).
- Parts the verifier reads (amendment of 2026-11-09) changes no control id, applicability rule or expected set and no required field: it narrows the candidate lists of C5, C6 and C8 to the parts the verify step reads and adds the optional `system/1` `proofs.verify_reads` and `controls/1` `parts_not_read`. With `"all"` or no declaration every mutation is unchanged. Stored files stay as recorded (READ-5).
- A new control or a change to an algorithm or expected set needs an RFC and a new `controls/<major>` if the file shape changes. Past `controls.json` files are never edited; they name the RFC version they ran under.

## Testing Strategy

- `test_c1_changes_last_token_mod_vocab`: with `vocab_size = 10` and last token 9, the mutated token is 0.
- `test_c2_seeded_position_stable`: the same `control_seed` yields the same position across two processes; a different seed yields a different position for a 1,024-token request in at least one of ten fixed seeds.
- `test_c5_truncates_largest_part_tiebreak_by_name`: two parts of equal size, the lexicographically first is truncated to `floor(size/2)` bytes.
- `test_c6_five_trials_flip_one_bit`: each trial differs from the original in exactly one bit; trial mutations are reproducible from the seed.
- `test_c7_not_applicable_batch_one` and `test_c8_not_applicable_single_part`.
- `test_c6_chooses_only_read_parts`, `test_c5_truncates_largest_read_part`, `test_c8_drops_only_read_parts` (READ-3): with one part declared not read, the same seeds give trials whose parts are all read parts, indexed into the read list sorted by name, and with `"all"` the mutations are the ones the undeclared suite makes.
- `test_declaration_that_does_not_fit_is_refused_before_any_call` (a declared part the proof does not have, a part of the proof not placed; whole suite and a part without C5, C6, C8), `test_part_placed_twice_refused` and `test_controls_refused_when_a_declared_part_does_not_exist` (through `iproofs controls`, nothing written) (READ-2).
- `test_unread_part_finding_reproduced_then_closed` (READ-3, READ-4, INV-CTRL-8): on a hand-made system whose verifier never opens one part, the undeclared suite has an accepted C6 trial on that part; declared, every C5, C6 and C8 mutation hits the part read, none is accepted, each record lists the part not read with its reason, and C1 to C4 and C7 are the same records. `test_controls_on_a_stored_run_read_the_declaration`: a run made before the declaration, controlled after it.
- `test_twin_failure_voids_control`: a fake verifier that rejects everything yields `void` for every control, never `rejected`.
- `test_fake_all_shared_controls_pass`: on `systems/fake`, every applicable control passes and `summary.accepted == 0`.
- `test_fake_broken_all_accepted`: on `systems/fake-broken`, every applicable verifier-side control is `accepted` and `disclosure_pending` is true.
- `test_summary_recomputed`: editing one outcome in a stored `controls.json` makes `iproofs derive --check` fail.
- `test_weakened_prover_requires_unbound_edge`: a `weakened_prover` control with outcome `accepted` and a binding report marking the edge bound does not pass.
- `test_control_job_never_measured_row`: a run directory with `control: true` in its manifest fails `iproofs validate` if it appears in a release's measured rows ([RFC-0013](0013-validation-and-ci.md)).
- `test_commitment_never_from_proof`: a proof directory containing a forged commitment file does not change the commitment passed to verify.
- `test_merged_parts_equal_one_run_byte_for_byte` (INV-CTRL-7): on `systems/fake`, with a perturbed commitment (C3, P1) and three system controls, the whole suite run once, and the suite split into three parts, each on its own copy of the run with a fresh runner, then merged in a directory that holds only `run.json`, `manifest.json` and `controls-seed.json`, with one seed, give identical bytes.
- `test_split_runs_with_one_drawn_seed`: no part without a seed record; the record is drawn once; `--seed` other than the recorded one, and the whole suite once a record exists, are refused (SPLIT-1).
- `test_merge_refuses_*`: parts of another run, another seed record or any other SPLIT-4 field, overlapping or missing controls, records other than the subset (SPLIT-5).
- `test_prover_side_refused_where_no_prove_can_run`: a prover-side control on a verifier host, or on a GPU profile without `--gpu`, stops before any call (SPLIT-3); `test_prover_part_records_its_host_and_refuses_another_gpu` and `test_p1_part_refused_without_the_perturbed_weights` (SPLIT-2, SPLIT-3).

## Open Questions

- OPEN QUESTION Q1 (owner: AbdelStark, resolve by: 2027-01-31): Controls that target the binding between a proof and served traffic, once any system claims it. Default: none in v0.1.
- OPEN QUESTION Q2 (owner: AbdelStark, resolve by: 2027-01-31): Whether committing the perturbed Maverick model fits the release compute budget. Default: C3 and P1 run for SASH workloads and for FlashProve on its smallest supported synthetic shape if full-size commit is infeasible, with the substitution declared in the row; otherwise `not_applicable`.
- OPEN QUESTION Q3: merged into [RFC-0001](0001-process-and-governance.md#open-questions) Q3 (private reporting channel), which owns it. Until resolved, systems without a published policy are contacted through the maintainers listed in `system.yaml`.
- OPEN QUESTION Q4 (owner: AbdelStark, resolve by: 2027-01-31): upstream rejected-proof examples (for example FlashProve `examples/rejected-proofs`) may come with their own commitment, which conflicts with INV-CTRL-6 (the commitment always comes from a harness record). Default until resolved: such an example is registered only if the harness can regenerate its commitment through the adapter's `commit` step; otherwise it is listed in the adapter README and not run as a control.
- OPEN QUESTION Q5 (owner: AbdelStark, resolve by: 2027-01-31): how the bytes of a `fixture_proof` control reach the harness (`system-controls/1` names only an upstream `source`, and adapters see only `/io` and `/models`). Default until resolved: a `fixture_proof` control is recorded as `not_applicable` with that reason; `weakened_prover` controls run as specified.

## References

- [RFC-0002 Claim card](0002-claim-card.md), [RFC-0003 Workloads](0003-workloads.md), [RFC-0005 Adapter contract](0005-adapter-contract.md), [RFC-0009 Results](0009-results-and-publication.md), [RFC-0010 Harness runner](0010-harness-runner.md), [RFC-0012 Schemas](0012-schemas-and-serialization.md), [RFC-0013 CI gates](0013-validation-and-ci.md).
- FlashProve `examples/rejected-proofs` at `9e2bdd8ff5bf9c62f18263d7dac189b0400b260c`; SASH `--unsound-skip-*` switches at `eb95bfa887299d1637550228d42086c27cbb2b3b`.
- Python `random` module reproducibility guarantee (CPython documentation, "Notes on Reproducibility").
