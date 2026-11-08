# Questions to system teams on Not stated criteria

Drafts, not sent. Issue #336 asks each team whose public-source row has a Not stated cell in [`web/_data/criteria.json`](../../web/_data/criteria.json) to state the missing properties in its own sources. A maintainer sends them, then records the date and channel of each in a public issue ([RFC-0001 §Adding and removing a system](../../rfcs/0001-process-and-governance.md#adding-and-removing-a-system)). No personal address is written here (AGENTS.md rule 7): a channel is a public repository, a paper's printed correspondence line or a team's own site.

How an answer is used ([RFC-0016](../../rfcs/0016-glyph-properties-and-states.md#public-source-rows-public_sources)):

- An answer sets a state only once it is published in an own source: a file in the team's repository at a commit, its paper, or a page on its domain, archived when read (SRC-8, SRC-9).
- A private message or a reply file sets nothing (OVR-6). An unpublished answer leaves the cell Not stated.
- A reviewer copies the team's words and sets the state by the property's rules. Nobody infers or tests a property from the answer.

The claim card teams (FlashProve, SASH) are asked in #42, not here.

## The six questions

| Property | Question |
|---|---|
| Weights hidden | Does the checker learn nothing about the weights? |
| Model bound | Is each checked token tied to the committed weights? |
| Whole output checked | Does one check cover every output token of a request? |
| Formally verified | Is the security argument for this configuration checked by a proof assistant? |
| Security level | Is a soundness level stated for this configuration, and proven? |
| No trusted party | Does a check hold without trusting a chip maker, a setup ceremony or an honest party? |

## Message

Fill in SYSTEM and CELLS from the table below, and put each cell's question from the table above under CELLS.

> Hello. We maintain Inference Proofs, an open benchmark of provable inference (https://github.com/ai-verification-observatory/inference-proofs). Its site shows each system with six properties. Each is set only from what the system's own sources state ([RFC-0016](https://github.com/ai-verification-observatory/inference-proofs/blob/main/rfcs/0016-glyph-properties-and-states.md)); where they are silent, the site prints Not stated.
>
> For SYSTEM we read the sources listed on its row of `web/_data/criteria.json` and found no statement for these properties:
>
> CELLS
>
> Would you state them in your repository, paper or documentation, or point us to where you already do? "Not provided" or "does not hold" is as useful to us as "holds". We copy your words, link them at a commit or an archived page, and do not infer or test the properties. Thank you.

## Teams and cells

The cells are those still Not stated at `date` 2026-11-08 of the criteria file.

| System | Channel | Cells still Not stated |
|---|---|---|
| Attestable prover | the contact channel on attestable.com | Formally verified |
| DeepProve | issue or discussion on `Lagrange-Labs/deep-prove` | Weights hidden, Model bound, Formally verified, Security level, No trusted party |
| EZKL | discussion on `zkonduit/ezkl` (its README asks for questions there) | Model bound, Whole output checked, Formally verified, Security level |
| JOLT Atlas | issue on `ICME-Lab/jolt-atlas` | Weights hidden, Model bound, Whole output checked, Formally verified, Security level, No trusted party |
| JSTprove | issue on `inference-labs-inc/JSTprove` | Weights hidden, Model bound, Whole output checked, Formally verified, No trusted party |
| LuminAIR | issue on `gizatechxyz/LuminAIR` | Weights hidden, Model bound, Whole output checked, Formally verified, Security level, No trusted party |
| NanoZK | the correspondence address printed on arXiv 2603.18046 | Model bound, Whole output checked, Formally verified |
| opML | issue on `ora-io/opml` | Weights hidden, Model bound, Formally verified, Security level |
| Private ML SDK | issue on `nearai/private-ml-sdk` (row archived) | Weights hidden, Model bound, Formally verified, Security level |
| Remainder (Community Edition) | issue on `worldcoin/Remainder_CE` (not a security report, so not through its SECURITY.md) | Weights hidden, Model bound, Whole output checked, Formally verified, Security level, No trusted party |
| Tinfoil | the contact channel listed on docs.tinfoil.sh | Weights hidden, Model bound, Whole output checked, Formally verified, Security level |
| TOPLOC | issue on `PrimeIntellect-ai/toploc` | Weights hidden, Whole output checked, Formally verified, Security level, No trusted party |
| Verde (with RepOps) | the correspondence address printed on arXiv 2502.19405 | Model bound, Whole output checked, Formally verified, Security level |
| zkGPT | the repository the paper names (`security-Anonymous/zkgpt`), or the correspondence address on ePrint 2025/1184 | Model bound, Whole output checked, Formally verified, Security level, No trusted party |
| zkLLM | the contact link in the `jvhs0706/zkllm-ccs2024` README (issues disabled; the README says it is no longer maintained; row archived) | Model bound, Whole output checked, Formally verified, Security level, No trusted party |
| ZKML | issue on `ddkang/zkml`, or the contact line in its README | Model bound, Whole output checked, Formally verified, Security level, No trusted party |
| zkPyTorch | the contact channel on polyhedra.network, or the correspondence address on ePrint 2025/535 | Weights hidden, Model bound, Whole output checked, Formally verified, Security level, No trusted party |
| ZKTorch | issue on `uiuc-kang-lab/zk-torch` | Model bound, Whole output checked, Formally verified, Security level |
