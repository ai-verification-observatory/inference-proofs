# Questions to system teams on Not stated criteria

Drafts, not sent. Issue #336 asks each team whose public-source row has a Not stated cell in [`web/_data/criteria.json`](../../web/_data/criteria.json) to state the missing properties in its own sources. A maintainer sends them, then records the date and channel of each in a public issue ([RFC-0001 §Adding and removing a system](../../rfcs/0001-process-and-governance.md#adding-and-removing-a-system)). No personal address is written here (AGENTS.md rule 7): a channel is a public repository, a paper's printed correspondence line or a team's own site.

Each message below lists the cells that are Not stated at `date` 2026-11-08 of the criteria file, and the sources read for them. Check them against the file before sending: a cell set since then is dropped from its message.

How an answer is used ([RFC-0016](../../rfcs/0016-glyph-properties-and-states.md#public-source-rows-public_sources)):

- An answer sets a state only once it is published in an own source: a file in the team's repository at a commit, its paper, or a page on its domain, archived when read (SRC-8, SRC-9). A new public source counts once a maintainer adds it to the row's `own_sources`, with its `how`.
- A private message or an issue comment alone sets nothing (SRC-8; for card rows, cf. OVR-6). An unpublished answer leaves the cell Not stated.
- A reviewer copies the team's words and sets the state by the property's rules. Nobody infers or tests a property from the answer.
- The questions ask about the system's default use, because RFC-0016 reads a public-source row for its default or expected use (SRC-1). An answer for another configuration is printed as an aside and sets nothing.
- A question marked "(Partly cell)" targets a cell that is Partly under an open question of RFC-0016 (Q10), not a Not stated cell.

The claim card teams (FlashProve, SASH) are asked in #42, not here.

## Index

| System | Channel | Cells still Not stated | Send |
|---|---|---|---|
| [Attestable prover](#attestable-prover) | the contact channel on attestable.com | Formally verified | yes |
| [DeepProve](#deepprove) | an issue on `Lagrange-Labs/deep-prove` | Weights hidden, Model bound, Formally verified, Security level, No trusted party | yes |
| [EZKL](#ezkl) | a discussion on `zkonduit/ezkl` (its README asks for questions there) | Model bound, Whole output checked, Formally verified, Security level | yes |
| [JOLT Atlas](#jolt-atlas) | an issue on `ICME-Lab/jolt-atlas` | Weights hidden, Model bound, Whole output checked, Formally verified, Security level, No trusted party | yes |
| [JSTprove](#jstprove) | an issue on `inference-labs-inc/JSTprove` | Weights hidden, Model bound, Whole output checked, Formally verified, Security level, No trusted party | yes |
| [LuminAIR](#luminair) | an issue on `gizatechxyz/LuminAIR` | Weights hidden, Model bound, Whole output checked, Formally verified, Security level, No trusted party | yes |
| [NanoZK](#nanozk) | the correspondence address printed on arXiv 2603.18046 | Model bound, Whole output checked, Formally verified | yes |
| [opML](#opml) | an issue on `ora-io/opml` | Weights hidden, Model bound, Formally verified, Security level | yes |
| [Private ML SDK](#private-ml-sdk) | none that works today | Weights hidden, Model bound, Whole output checked, Formally verified, Security level | optional |
| [Remainder (Community Edition)](#remainder-community-edition) | an issue on `worldcoin/Remainder_CE` (not a security report, so not through its SECURITY.md) | Weights hidden, Model bound, Whole output checked, Formally verified, Security level, No trusted party | yes |
| [Tinfoil](#tinfoil) | the contact channel listed on docs.tinfoil.sh | Weights hidden, Model bound, Whole output checked, Formally verified, Security level | yes |
| [TOPLOC](#toploc) | an issue on `PrimeIntellect-ai/toploc` | Weights hidden, Whole output checked, Formally verified, Security level, No trusted party | yes |
| [Verde (with RepOps)](#verde-with-repops) | the correspondence address printed on arXiv 2502.19405 | Model bound, Whole output checked, Formally verified, Security level | yes |
| [zkGPT](#zkgpt) | the correspondence address printed on ePrint 2025/1184 | Model bound, Whole output checked, Formally verified, Security level, No trusted party | yes |
| [zkLLM](#zkllm) | the correspondence address printed on arXiv 2404.16109 | Model bound, Whole output checked, Formally verified, Security level, No trusted party | optional |
| [ZKML](#zkml) | an issue on `ddkang/zkml` | Model bound, Whole output checked, Formally verified, Security level, No trusted party | yes |
| [zkPyTorch](#zkpytorch) | the contact channel on polyhedra.network, or the correspondence address printed on ePrint 2025/535 | Weights hidden, Model bound, Whole output checked, Formally verified, Security level, No trusted party | yes |
| [ZKTorch](#zktorch) | an issue on `uiuc-kang-lab/zk-torch` | Model bound, Whole output checked, Formally verified, Security level | yes |

## Messages

### Attestable prover

- Channel: the contact channel on attestable.com.
- An answer counts in: a page on attestable.com.

> Hello. We maintain Inference Proofs, an open benchmark of provable inference (https://github.com/ai-verification-observatory/inference-proofs). Its site shows each system with six properties. Each is set only from what the system's own sources state ([RFC-0016](https://github.com/ai-verification-observatory/inference-proofs/blob/main/rfcs/0016-glyph-properties-and-states.md)); where they are silent, the site prints Not stated.
>
> For Attestable prover, we read these sources:
>
> - https://attestable.com/blog/proving-llms-scale (read 2026-11-07)
>
> We found no statement that answers these questions:
>
> 1. Formally verified: Is the security argument for its default use checked in a proof assistant (Lean, Coq, Isabelle or similar)?
>
> One more question would settle a cell we read as Partly:
>
> 2. Security level (Partly cell): Your post states that you "uphold 100 bits of security". Is that level proven or conjectured, and does it cover the whole prover?
>
> Would you state the answers in a page on attestable.com, or point us to where you already do? "Not provided" or "does not hold" is as useful to us as "holds". A reply by message alone does not change the site; the statement needs to be in a public source of yours. We copy your words, link them at a commit or an archived page, and do not infer or test the properties. Thank you.

### DeepProve

- Channel: an issue on `Lagrange-Labs/deep-prove`.
- An answer counts in: a file in `Lagrange-Labs/deep-prove` or a new version of ePrint 2026/1112.

> Hello. We maintain Inference Proofs, an open benchmark of provable inference (https://github.com/ai-verification-observatory/inference-proofs). Its site shows each system with six properties. Each is set only from what the system's own sources state ([RFC-0016](https://github.com/ai-verification-observatory/inference-proofs/blob/main/rfcs/0016-glyph-properties-and-states.md)); where they are silent, the site prints Not stated.
>
> For DeepProve, we read these sources:
>
> - `Lagrange-Labs/deep-prove` at commit `9d1a53e2ef49ffa2c902b8689cd3c58057a4e662`: `**/*.md`, `README.md`, `zkml/README.md`, `docs/src/*.md`, `zkml/docs/src/**/*.md`, `**/*.rs`
> - https://eprint.iacr.org/2026/1112 (read 2026-11-07)
>
> We found no statement that answers these questions:
>
> 1. Weights hidden: In its default use, does the party that checks a result learn nothing about the model weights?
> 2. Model bound: In its default use, is each checked output token tied to the committed weights?
> 3. Formally verified: Is the security argument for its default use checked in a proof assistant (Lean, Coq, Isabelle or similar)?
> 4. Security level: Is a numeric soundness level stated for its default use, and is it proven or conjectured?
> 5. No trusted party: In its default use, does a check hold without trusting a chip maker, a setup ceremony or an honest party?
>
> Would you state the answers in a file in `Lagrange-Labs/deep-prove` or a new version of ePrint 2026/1112, or point us to where you already do? "Not provided" or "does not hold" is as useful to us as "holds". A reply by message alone does not change the site; the statement needs to be in a public source of yours. We copy your words, link them at a commit or an archived page, and do not infer or test the properties. Thank you.

### EZKL

- Channel: a discussion on `zkonduit/ezkl` (its README asks for questions there).
- An answer counts in: a file in `zkonduit/ezkl`.

> Hello. We maintain Inference Proofs, an open benchmark of provable inference (https://github.com/ai-verification-observatory/inference-proofs). Its site shows each system with six properties. Each is set only from what the system's own sources state ([RFC-0016](https://github.com/ai-verification-observatory/inference-proofs/blob/main/rfcs/0016-glyph-properties-and-states.md)); where they are silent, the site prints Not stated.
>
> For EZKL, we read these sources:
>
> - `zkonduit/ezkl` at commit `e196b111c1bafaa61b92ae431cd3c3fe9371da05`: `README.md`, `docs/advanced_security/*.md`, `ezkl.pyi`, `src/pfsys/srs.rs`, `src/**/*.rs`, `examples/notebooks/*.ipynb`
>
> We found no statement that answers these questions:
>
> 1. Model bound: In its default use, is each checked output token tied to the committed weights?
> 2. Whole output checked: Does one check, or one joined set of checks, cover the prompt and every output token of a request?
> 3. Formally verified: Is the security argument for its default use checked in a proof assistant (Lean, Coq, Isabelle or similar)?
> 4. Security level: Is a numeric soundness level stated for its default use, and is it proven or conjectured?
>
> Would you state the answers in a file in `zkonduit/ezkl`, or point us to where you already do? "Not provided" or "does not hold" is as useful to us as "holds". A reply by message alone does not change the site; the statement needs to be in a public source of yours. We copy your words, link them at a commit or an archived page, and do not infer or test the properties. Thank you.

### JOLT Atlas

- Channel: an issue on `ICME-Lab/jolt-atlas`.
- An answer counts in: a file in `ICME-Lab/jolt-atlas`.

> Hello. We maintain Inference Proofs, an open benchmark of provable inference (https://github.com/ai-verification-observatory/inference-proofs). Its site shows each system with six properties. Each is set only from what the system's own sources state ([RFC-0016](https://github.com/ai-verification-observatory/inference-proofs/blob/main/rfcs/0016-glyph-properties-and-states.md)); where they are silent, the site prints Not stated.
>
> For JOLT Atlas, we read these sources:
>
> - `ICME-Lab/jolt-atlas` at commit `329b21efa6f6a74355e6096cf27c3e0cc7dfc226`: `README.md`, `specs/**`, `docs/**`, `AGENTS.md`, `jolt-atlas-core/src/onnx_proof/zk.rs`, `joltworks/src/poly/commitment/**/*.rs`, `**/*.rs`, `**/*.lean`, `**/*.md`
>
> We found no statement that answers these questions:
>
> 1. Weights hidden: In its default use, does the party that checks a result learn nothing about the model weights?
> 2. Model bound: In its default use, is each checked output token tied to the committed weights?
> 3. Whole output checked: Does one check, or one joined set of checks, cover the prompt and every output token of a request?
> 4. Formally verified: Is the security argument for its default use checked in a proof assistant (Lean, Coq, Isabelle or similar)?
> 5. Security level: Is a numeric soundness level stated for its default use, and is it proven or conjectured?
> 6. No trusted party: In its default use, does a check hold without trusting a chip maker, a setup ceremony or an honest party?
>
> Would you state the answers in a file in `ICME-Lab/jolt-atlas`, or point us to where you already do? "Not provided" or "does not hold" is as useful to us as "holds". A reply by message alone does not change the site; the statement needs to be in a public source of yours. We copy your words, link them at a commit or an archived page, and do not infer or test the properties. Thank you.

### JSTprove

- Channel: an issue on `inference-labs-inc/JSTprove`.
- An answer counts in: a file in `inference-labs-inc/JSTprove` or a new version of arXiv 2510.21024.

> Hello. We maintain Inference Proofs, an open benchmark of provable inference (https://github.com/ai-verification-observatory/inference-proofs). Its site shows each system with six properties. Each is set only from what the system's own sources state ([RFC-0016](https://github.com/ai-verification-observatory/inference-proofs/blob/main/rfcs/0016-glyph-properties-and-states.md)); where they are silent, the site prints Not stated.
>
> For JSTprove, we read these sources:
>
> - `inference-labs-inc/JSTprove` at commit `7c3cbbee83aaa01adde700673f00e317a4e902f9`: `README.md`, `docs/*.md`, `prover/poly_commit/src/**/*.rs`, `rust/jstprove_circuits/src/runner/holographic.rs`, `rust/jstprove_circuits/src/proof_config.rs`
> - https://arxiv.org/abs/2510.21024 (read 2026-11-07)
>
> We found no statement that answers these questions:
>
> 1. Weights hidden: In its default use, does the party that checks a result learn nothing about the model weights?
> 2. Model bound: In its default use, is each checked output token tied to the committed weights?
> 3. Whole output checked: Does one check, or one joined set of checks, cover the prompt and every output token of a request?
> 4. Formally verified: Is the security argument for its default use checked in a proof assistant (Lean, Coq, Isabelle or similar)?
> 5. Security level: Which polynomial commitment does the default `--curve bn254` run use, and is a numeric soundness level stated for it, proven or conjectured? We found `PCS_SOUNDNESS_BITS = 128` in `prover/poly_commit/src/lib.rs`, which the Basefold and Orion commitments read.
> 6. No trusted party: In its default use, does a check hold without trusting a chip maker, a setup ceremony or an honest party?
>
> Would you state the answers in a file in `inference-labs-inc/JSTprove` or a new version of arXiv 2510.21024, or point us to where you already do? "Not provided" or "does not hold" is as useful to us as "holds". A reply by message alone does not change the site; the statement needs to be in a public source of yours. We copy your words, link them at a commit or an archived page, and do not infer or test the properties. Thank you.

### LuminAIR

- Channel: an issue on `gizatechxyz/LuminAIR`.
- An answer counts in: a file in `gizatechxyz/LuminAIR`.

> Hello. We maintain Inference Proofs, an open benchmark of provable inference (https://github.com/ai-verification-observatory/inference-proofs). Its site shows each system with six properties. Each is set only from what the system's own sources state ([RFC-0016](https://github.com/ai-verification-observatory/inference-proofs/blob/main/rfcs/0016-glyph-properties-and-states.md)); where they are silent, the site prints Not stated.
>
> For LuminAIR, we read these sources:
>
> - `gizatechxyz/LuminAIR` at commit `9026bd3d0934a35479e6b3b76353a6ac5facd9e8`: `README.md`, `docs/**/*.mdx`, `crates/verifiers/wasm/README.md`, `crates/prover/src/prover.rs`, `crates/verifiers/rust/src/verifier.rs`
>
> We found no statement that answers these questions:
>
> 1. Weights hidden: In its default use, does the party that checks a result learn nothing about the model weights?
> 2. Model bound: In its default use, is each checked output token tied to the committed weights?
> 3. Whole output checked: Does one check, or one joined set of checks, cover the prompt and every output token of a request?
> 4. Formally verified: Is the security argument for its default use checked in a proof assistant (Lean, Coq, Isabelle or similar)?
> 5. Security level: Is a numeric soundness level stated for its default use, and is it proven or conjectured?
> 6. No trusted party: In its default use, does a check hold without trusting a chip maker, a setup ceremony or an honest party?
>
> Would you state the answers in a file in `gizatechxyz/LuminAIR`, or point us to where you already do? "Not provided" or "does not hold" is as useful to us as "holds". A reply by message alone does not change the site; the statement needs to be in a public source of yours. We copy your words, link them at a commit or an archived page, and do not infer or test the properties. Thank you.

### NanoZK

- Channel: the correspondence address printed on arXiv 2603.18046.
- An answer counts in: a new version of arXiv 2603.18046.

> Hello. We maintain Inference Proofs, an open benchmark of provable inference (https://github.com/ai-verification-observatory/inference-proofs). Its site shows each system with six properties. Each is set only from what the system's own sources state ([RFC-0016](https://github.com/ai-verification-observatory/inference-proofs/blob/main/rfcs/0016-glyph-properties-and-states.md)); where they are silent, the site prints Not stated.
>
> For NanoZK, we read these sources:
>
> - https://arxiv.org/pdf/2603.18046v2 (read 2026-11-08)
> - https://arxiv.org/abs/2603.18046 (read 2026-11-07)
>
> We found no statement that answers these questions:
>
> 1. Model bound: In its default use, is each checked output token tied to the committed weights?
> 2. Whole output checked: Does one check, or one joined set of checks, cover the prompt and every output token of a request?
> 3. Formally verified: Is the security argument for its default use checked in a proof assistant (Lean, Coq, Isabelle or similar)?
>
> Would you state the answers in a new version of arXiv 2603.18046, or point us to where you already do? "Not provided" or "does not hold" is as useful to us as "holds". A reply by message alone does not change the site; the statement needs to be in a public source of yours. We copy your words, link them at a commit or an archived page, and do not infer or test the properties. Thank you.

### opML

- Channel: an issue on `ora-io/opml`.
- An answer counts in: a file in `ora-io/opml`.

> Hello. We maintain Inference Proofs, an open benchmark of provable inference (https://github.com/ai-verification-observatory/inference-proofs). Its site shows each system with six properties. Each is set only from what the system's own sources state ([RFC-0016](https://github.com/ai-verification-observatory/inference-proofs/blob/main/rfcs/0016-glyph-properties-and-states.md)); where they are silent, the site prints Not stated.
>
> For opML, we read these sources:
>
> - `ora-io/opml` at commit `2fa43311a4a95bcd96f5092d0a3b34e84da49eb0`: `README.md`, `docs/OPML.md`, `docs/tutorial.md`
>
> We found no statement that answers these questions:
>
> 1. Weights hidden: In its default use, does the party that checks a result learn nothing about the model weights?
> 2. Model bound: In its default use, is each checked output token tied to the committed weights?
> 3. Formally verified: Is the security argument for its default use checked in a proof assistant (Lean, Coq, Isabelle or similar)?
> 4. Security level: Is a numeric soundness level stated for its default use, and is it proven or conjectured?
>
> Would you state the answers in a file in `ora-io/opml`, or point us to where you already do? "Not provided" or "does not hold" is as useful to us as "holds". A reply by message alone does not change the site; the statement needs to be in a public source of yours. We copy your words, link them at a commit or an archived page, and do not infer or test the properties. Thank you.

### Private ML SDK

- Channel: none that works today: `nearai/private-ml-sdk` is archived, so no issue can be opened and no commit can land. A maintainer may ask on an active public repository of the same organization (for example `nearai/cloud-api`).
- An answer counts in: no listed own source can take a new statement; a new public source counts once a maintainer adds it to the row's `own_sources`, with its `how`.
- Optional; the maintainer decides, since no answer can land in the row's only own source.

> Hello. We maintain Inference Proofs, an open benchmark of provable inference (https://github.com/ai-verification-observatory/inference-proofs). Its site shows each system with six properties. Each is set only from what the system's own sources state ([RFC-0016](https://github.com/ai-verification-observatory/inference-proofs/blob/main/rfcs/0016-glyph-properties-and-states.md)); where they are silent, the site prints Not stated.
>
> For Private ML SDK, we read these sources:
>
> - `nearai/private-ml-sdk` at commit `25c25025c556ab2f797eeda3bab433f38a8ffb7a`: `README.md`, `docs/how-cvm-boots.md`, `e2e/README.md`, `vllm-proxy/README.md`, `vllm-proxy/verifiers/README.md`
>
> We found no statement that answers these questions:
>
> 1. Weights hidden: In its default use, does the party that checks a result learn nothing about the model weights?
> 2. Model bound: In its default use, is each checked output token tied to the committed weights?
> 3. Whole output checked: Does one check, or one joined set of checks, cover the prompt and every output token of a request?
> 4. Formally verified: Is the security argument for its default use checked in a proof assistant (Lean, Coq, Isabelle or similar)?
> 5. Security level: Is a numeric soundness level stated for its default use, and is it proven or conjectured?
>
> Would you state the answers in a public source of yours, or point us to where you already do? "Not provided" or "does not hold" is as useful to us as "holds". A reply by message alone does not change the site; the statement needs to be in a public source of yours. We copy your words, link them at a commit or an archived page, and do not infer or test the properties. Thank you.

### Remainder (Community Edition)

- Channel: an issue on `worldcoin/Remainder_CE` (not a security report, so not through its SECURITY.md).
- An answer counts in: a file in `worldcoin/Remainder_CE`.

> Hello. We maintain Inference Proofs, an open benchmark of provable inference (https://github.com/ai-verification-observatory/inference-proofs). Its site shows each system with six properties. Each is set only from what the system's own sources state ([RFC-0016](https://github.com/ai-verification-observatory/inference-proofs/blob/main/rfcs/0016-glyph-properties-and-states.md)); where they are silent, the site prints Not stated.
>
> For Remainder (Community Edition), we read these sources:
>
> - `worldcoin/Remainder_CE` at commit `5687fe7f3a077c75c374422ef79f22e3860de9c1`: `README.md`, `SECURITY.md`, `prover/README.md`, `ligero/src/*.rs`, `hyrax/src/**/*.rs`, `prover/src/**/*.rs`
>
> We found no statement that answers these questions:
>
> 1. Weights hidden: In its default use, does the party that checks a result learn nothing about the model weights?
> 2. Model bound: In its default use, is each checked output token tied to the committed weights?
> 3. Whole output checked: Does one check, or one joined set of checks, cover the prompt and every output token of a request?
> 4. Formally verified: Is the security argument for its default use checked in a proof assistant (Lean, Coq, Isabelle or similar)?
> 5. Security level: Is a numeric soundness level stated for its default use, and is it proven or conjectured?
> 6. No trusted party: In its default use, does a check hold without trusting a chip maker, a setup ceremony or an honest party?
>
> Would you state the answers in a file in `worldcoin/Remainder_CE`, or point us to where you already do? "Not provided" or "does not hold" is as useful to us as "holds". A reply by message alone does not change the site; the statement needs to be in a public source of yours. We copy your words, link them at a commit or an archived page, and do not infer or test the properties. Thank you.

### Tinfoil

- Channel: the contact channel listed on docs.tinfoil.sh.
- An answer counts in: a page on docs.tinfoil.sh.

> Hello. We maintain Inference Proofs, an open benchmark of provable inference (https://github.com/ai-verification-observatory/inference-proofs). Its site shows each system with six properties. Each is set only from what the system's own sources state ([RFC-0016](https://github.com/ai-verification-observatory/inference-proofs/blob/main/rfcs/0016-glyph-properties-and-states.md)); where they are silent, the site prints Not stated.
>
> For Tinfoil, we read these sources:
>
> - https://docs.tinfoil.sh/verification/attestation-architecture (read 2026-11-08)
>
> We found no statement that answers these questions:
>
> 1. Weights hidden: In its default use, does the party that checks a result learn nothing about the model weights?
> 2. Model bound: In its default use, is each checked output token tied to the committed weights?
> 3. Whole output checked: Does one check, or one joined set of checks, cover the prompt and every output token of a request?
> 4. Formally verified: Is the security argument for its default use checked in a proof assistant (Lean, Coq, Isabelle or similar)?
> 5. Security level: Is a numeric soundness level stated for its default use, and is it proven or conjectured?
>
> Would you state the answers in a page on docs.tinfoil.sh, or point us to where you already do? "Not provided" or "does not hold" is as useful to us as "holds". A reply by message alone does not change the site; the statement needs to be in a public source of yours. We copy your words, link them at a commit or an archived page, and do not infer or test the properties. Thank you.

### TOPLOC

- Channel: an issue on `PrimeIntellect-ai/toploc`.
- An answer counts in: a file in `PrimeIntellect-ai/toploc` or a new version of arXiv 2501.16007.

> Hello. We maintain Inference Proofs, an open benchmark of provable inference (https://github.com/ai-verification-observatory/inference-proofs). Its site shows each system with six properties. Each is set only from what the system's own sources state ([RFC-0016](https://github.com/ai-verification-observatory/inference-proofs/blob/main/rfcs/0016-glyph-properties-and-states.md)); where they are silent, the site prints Not stated.
>
> For TOPLOC, we read these sources:
>
> - `PrimeIntellect-ai/toploc` at commit `7ab7bcd6a4459ba4400fd41e4636bbeed7438997`: `README.md`, `CONTRIBUTING.md`, `toploc/*.py`, `toploc/C/csrc/*`
> - https://arxiv.org/abs/2501.16007 (read 2026-11-07)
>
> We found no statement that answers these questions:
>
> 1. Weights hidden: In its default use, does the party that checks a result learn nothing about the model weights?
> 2. Whole output checked: Does one check, or one joined set of checks, cover the prompt and every output token of a request?
> 3. Formally verified: Is the security argument for its default use checked in a proof assistant (Lean, Coq, Isabelle or similar)?
> 4. Security level: Is a numeric soundness level stated for its default use, and is it proven or conjectured?
> 5. No trusted party: In its default use, does a check hold without trusting a chip maker, a setup ceremony or an honest party?
>
> Would you state the answers in a file in `PrimeIntellect-ai/toploc` or a new version of arXiv 2501.16007, or point us to where you already do? "Not provided" or "does not hold" is as useful to us as "holds". A reply by message alone does not change the site; the statement needs to be in a public source of yours. We copy your words, link them at a commit or an archived page, and do not infer or test the properties. Thank you.

### Verde (with RepOps)

- Channel: the correspondence address printed on arXiv 2502.19405.
- An answer counts in: a new version of arXiv 2502.19405.

> Hello. We maintain Inference Proofs, an open benchmark of provable inference (https://github.com/ai-verification-observatory/inference-proofs). Its site shows each system with six properties. Each is set only from what the system's own sources state ([RFC-0016](https://github.com/ai-verification-observatory/inference-proofs/blob/main/rfcs/0016-glyph-properties-and-states.md)); where they are silent, the site prints Not stated.
>
> For Verde (with RepOps), we read these sources:
>
> - https://arxiv.org/pdf/2502.19405v1 (read 2026-11-08)
> - https://arxiv.org/abs/2502.19405 (read 2026-11-07)
>
> We found no statement that answers these questions:
>
> 1. Model bound: In its default use, is each checked output token tied to the committed weights?
> 2. Whole output checked: Does one check, or one joined set of checks, cover the prompt and every output token of a request?
> 3. Formally verified: Is the security argument for its default use checked in a proof assistant (Lean, Coq, Isabelle or similar)?
> 4. Security level: Is a numeric soundness level stated for its default use, and is it proven or conjectured?
>
> Would you state the answers in a new version of arXiv 2502.19405, or point us to where you already do? "Not provided" or "does not hold" is as useful to us as "holds". A reply by message alone does not change the site; the statement needs to be in a public source of yours. We copy your words, link them at a commit or an archived page, and do not infer or test the properties. Thank you.

### zkGPT

- Channel: the correspondence address printed on ePrint 2025/1184.
- An answer counts in: a new version of ePrint 2025/1184.
- The paper names the repository `security-Anonymous/zkGPT`; a statement there counts only once a maintainer adds it to the row's `own_sources`, with its `how`.

> Hello. We maintain Inference Proofs, an open benchmark of provable inference (https://github.com/ai-verification-observatory/inference-proofs). Its site shows each system with six properties. Each is set only from what the system's own sources state ([RFC-0016](https://github.com/ai-verification-observatory/inference-proofs/blob/main/rfcs/0016-glyph-properties-and-states.md)); where they are silent, the site prints Not stated.
>
> For zkGPT, we read these sources:
>
> - https://web.archive.org/web/20250902071715/https://eprint.iacr.org/2025/1184.pdf (read 2026-11-08)
> - https://eprint.iacr.org/2025/1184 (read 2026-11-07)
>
> We found no statement that answers these questions:
>
> 1. Model bound: In its default use, is each checked output token tied to the committed weights?
> 2. Whole output checked: Does one check, or one joined set of checks, cover the prompt and every output token of a request?
> 3. Formally verified: Is the security argument for its default use checked in a proof assistant (Lean, Coq, Isabelle or similar)?
> 4. Security level: Is a numeric soundness level stated for its default use, and is it proven or conjectured?
> 5. No trusted party: In its default use, does a check hold without trusting a chip maker, a setup ceremony or an honest party?
>
> Would you state the answers in a new version of ePrint 2025/1184, or point us to where you already do? "Not provided" or "does not hold" is as useful to us as "holds". A reply by message alone does not change the site; the statement needs to be in a public source of yours. We copy your words, link them at a commit or an archived page, and do not infer or test the properties. Thank you.

### zkLLM

- Channel: the correspondence address printed on arXiv 2404.16109. `jvhs0706/zkllm-ccs2024` is archived with issues disabled, and its README says the author cannot give continued support.
- An answer counts in: a new version of arXiv 2404.16109.
- Optional; the maintainer decides. The repository is archived and unmaintained, so an answer can only come through a new version of the paper.

> Hello. We maintain Inference Proofs, an open benchmark of provable inference (https://github.com/ai-verification-observatory/inference-proofs). Its site shows each system with six properties. Each is set only from what the system's own sources state ([RFC-0016](https://github.com/ai-verification-observatory/inference-proofs/blob/main/rfcs/0016-glyph-properties-and-states.md)); where they are silent, the site prints Not stated.
>
> For zkLLM, we read these sources:
>
> - `jvhs0706/zkllm-ccs2024` at commit `993311ea8e2346b90efacb35337b2e3cfe0d6f8d`: `README.md`, `*.py`, `*.cu`, `*.cuh`
> - https://arxiv.org/abs/2404.16109 (read 2026-11-07)
>
> We found no statement that answers these questions:
>
> 1. Model bound: In its default use, is each checked output token tied to the committed weights?
> 2. Whole output checked: Does one check, or one joined set of checks, cover the prompt and every output token of a request?
> 3. Formally verified: Is the security argument for its default use checked in a proof assistant (Lean, Coq, Isabelle or similar)?
> 4. Security level: Is a numeric soundness level stated for its default use, and is it proven or conjectured?
> 5. No trusted party: In its default use, does a check hold without trusting a chip maker, a setup ceremony or an honest party?
>
> Would you state the answers in a new version of arXiv 2404.16109, or point us to where you already do? "Not provided" or "does not hold" is as useful to us as "holds". A reply by message alone does not change the site; the statement needs to be in a public source of yours. We copy your words, link them at a commit or an archived page, and do not infer or test the properties. Thank you.

### ZKML

- Channel: an issue on `ddkang/zkml`.
- An answer counts in: a file in `ddkang/zkml` or a new version of the paper at https://ddkang.github.io/papers/2024/zkml-eurosys.pdf.

> Hello. We maintain Inference Proofs, an open benchmark of provable inference (https://github.com/ai-verification-observatory/inference-proofs). Its site shows each system with six properties. Each is set only from what the system's own sources state ([RFC-0016](https://github.com/ai-verification-observatory/inference-proofs/blob/main/rfcs/0016-glyph-properties-and-states.md)); where they are silent, the site prints Not stated.
>
> For ZKML, we read these sources:
>
> - `ddkang/zkml` at commit `43789582671f16148dd02cbac5654f462d4fe3e4`: `README.md`, `examples/nlp/*/README.md`, `backwards/README.md`, `src/utils/proving_kzg.rs`, `src/utils/proving_ipa.rs`
> - https://ddkang.github.io/papers/2024/zkml-eurosys.pdf (read 2026-11-07)
>
> We found no statement that answers these questions:
>
> 1. Model bound: In its default use, is each checked output token tied to the committed weights?
> 2. Whole output checked: Does one check, or one joined set of checks, cover the prompt and every output token of a request?
> 3. Formally verified: Is the security argument for its default use checked in a proof assistant (Lean, Coq, Isabelle or similar)?
> 4. Security level: Is a numeric soundness level stated for its default use, and is it proven or conjectured?
> 5. No trusted party: In its default use, does a check hold without trusting a chip maker, a setup ceremony or an honest party?
>
> Would you state the answers in a file in `ddkang/zkml` or a new version of the paper at https://ddkang.github.io/papers/2024/zkml-eurosys.pdf, or point us to where you already do? "Not provided" or "does not hold" is as useful to us as "holds". A reply by message alone does not change the site; the statement needs to be in a public source of yours. We copy your words, link them at a commit or an archived page, and do not infer or test the properties. Thank you.

### zkPyTorch

- Channel: the contact channel on polyhedra.network, or the correspondence address printed on ePrint 2025/535.
- An answer counts in: a page on polyhedra.network or a new version of ePrint 2025/535.

> Hello. We maintain Inference Proofs, an open benchmark of provable inference (https://github.com/ai-verification-observatory/inference-proofs). Its site shows each system with six properties. Each is set only from what the system's own sources state ([RFC-0016](https://github.com/ai-verification-observatory/inference-proofs/blob/main/rfcs/0016-glyph-properties-and-states.md)); where they are silent, the site prints Not stated.
>
> For zkPyTorch, we read these sources:
>
> - https://polyhedra.network/zkPyTorch (read 2026-11-08)
> - https://eprint.iacr.org/2025/535 (read 2026-11-07)
> - https://web.archive.org/web/20260825214632/https://eprint.iacr.org/2025/535.pdf (read 2026-11-08)
>
> We found no statement that answers these questions:
>
> 1. Weights hidden: In its default use, does the party that checks a result learn nothing about the model weights?
> 2. Model bound: In its default use, is each checked output token tied to the committed weights?
> 3. Whole output checked: Does one check, or one joined set of checks, cover the prompt and every output token of a request?
> 4. Formally verified: Is the security argument for its default use checked in a proof assistant (Lean, Coq, Isabelle or similar)?
> 5. Security level: Is a numeric soundness level stated for its default use, and is it proven or conjectured?
> 6. No trusted party: In its default use, does a check hold without trusting a chip maker, a setup ceremony or an honest party?
>
> Would you state the answers in a page on polyhedra.network or a new version of ePrint 2025/535, or point us to where you already do? "Not provided" or "does not hold" is as useful to us as "holds". A reply by message alone does not change the site; the statement needs to be in a public source of yours. We copy your words, link them at a commit or an archived page, and do not infer or test the properties. Thank you.

### ZKTorch

- Channel: an issue on `uiuc-kang-lab/zk-torch`.
- An answer counts in: a file in `uiuc-kang-lab/zk-torch` or a new version of arXiv 2507.07031.

> Hello. We maintain Inference Proofs, an open benchmark of provable inference (https://github.com/ai-verification-observatory/inference-proofs). Its site shows each system with six properties. Each is set only from what the system's own sources state ([RFC-0016](https://github.com/ai-verification-observatory/inference-proofs/blob/main/rfcs/0016-glyph-properties-and-states.md)); where they are silent, the site prints Not stated.
>
> For ZKTorch, we read these sources:
>
> - `uiuc-kang-lab/zk-torch` at commit `63b9c68960f3ca84026d89428dd6d8129e930d53`: `README.md`, `test_gpu_scripts/README.md`
> - https://arxiv.org/abs/2507.07031 (read 2026-11-07)
>
> We found no statement that answers these questions:
>
> 1. Model bound: In its default use, is each checked output token tied to the committed weights?
> 2. Whole output checked: Does one check, or one joined set of checks, cover the prompt and every output token of a request?
> 3. Formally verified: Is the security argument for its default use checked in a proof assistant (Lean, Coq, Isabelle or similar)?
> 4. Security level: Is a numeric soundness level stated for its default use, and is it proven or conjectured?
>
> Would you state the answers in a file in `uiuc-kang-lab/zk-torch` or a new version of arXiv 2507.07031, or point us to where you already do? "Not provided" or "does not hold" is as useful to us as "holds". A reply by message alone does not change the site; the statement needs to be in a public source of yours. We copy your words, link them at a commit or an archived page, and do not infer or test the properties. Thank you.
