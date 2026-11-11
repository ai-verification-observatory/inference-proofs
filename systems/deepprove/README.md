# DeepProve adapter

DeepProve (Lagrange Labs) proves the inference of a quantized model. This adapter runs it on the
Level 1 GPT-2 rung (`l1-gpt2-p512-o512`, RFC-0018): 512 prompt tokens, a 512-token greedy reply,
five requests a session. Upstream is pinned at
[`9d1a53e2ef49ffa2c902b8689cd3c58057a4e662`][pin] (default branch `master`, committed
2026-05-26, still the head of the default branch on 2026-11-11). Every fact below was read in the
source at that commit; "read, not run" marks what no run has shown yet.

**State at this commit: `prove` is wired, `verify` refuses.** The upstream verifier takes its
verifier key only from inside the proof file, and no documented step makes that key from the
weights alone ([§Weights binding](#weights-binding)). Until that changes no session can complete,
and every Level 1 check that needs a verdict stays undecided.

[pin]: https://github.com/Lagrange-Labs/deep-prove/tree/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662
[U]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662

## Licence

- The licence is Lagrange's own agreement, not an open-source licence ([`LICENSE`][U-lic],
  [`README.md` L43-L45](https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/README.md#L43-L45)).
  The workspace manifest's `license = "MIT OR Apache-2.0"`
  ([`Cargo.toml` L16](https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/Cargo.toml#L16))
  is package metadata; the README names `LICENSE` as the licence, and we follow `LICENSE`.
- Section 2 ([L12][U-lic12]) grants "a personal, non-exclusive, non-sublicenseable,
  non-transferable, revocable, limited license ... (i) to download, install, and internally use
  the Software solely for the purpose of testing and evaluating it".
- Section 4 ([L16][U-lic16]): "You must not reproduce, distribute, publicly perform, publicly
  display, or create derivative works of or based on the Software, or disclose, rent, lease,
  loan, provide, or otherwise transfer, in any manner, to any third party the Software,
  Documentation or any portion thereof".
- Section 7 ([L25][U-lic25]): the licence ends "immediately and automatically" if a term is
  broken, and Lagrange may end it at any time with notice.
- The crate `dp-crypto` the build fetches (Cargo.lock, commit `22e8e93`) carries the same
  agreement ([`LICENSE` L35-L46, L72](https://github.com/Lagrange-Labs/dp-crypto/blob/22e8e93cd0f94a7638616a1ae22190feb0a6b275/LICENSE#L35-L72)).

What this means for the benchmark (a reading, not legal advice):

- Building and running DeepProve privately to measure it is inside "testing and evaluating".
- **Publishing results** is not addressed by the licence. Results are not the Software, but the
  project publishes nothing about DeepProve without the publisher's written permission, which is
  requested separately.
- **Image distribution: pushing the image to a public registry is not allowed.** The image holds
  the source and the compiled programs, a "portion" of the Software, and a public registry
  provides it to any third party (Section 4). The image is therefore built where it runs, or kept
  in a registry only the operator's own accounts can read. Whether pulling it onto a hosting
  provider's machine (Hugging Face Jobs) counts as providing it to a third party is not stated;
  ask Lagrange in the same permission request. `system.yaml` names the image `local/deepprove`,
  which the harness records with `digest_kind: config`, so under RFC-0014 a run of it is not
  eligible for a release until the project decides how a licence-restricted image is pinned.
- Nothing from upstream is vendored into this repository: the adapter, its tests and the
  stand-in proof files hold no upstream code.

[U-lic]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/LICENSE
[U-lic12]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/LICENSE#L12
[U-lic16]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/LICENSE#L16
[U-lic25]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/LICENSE#L25

## What upstream documents

- The README's quickstart is `bench-llm` ([`zkml/README.md` L113-L242][U-zr]). It proves
  **random** prompts ([`zkml/src/bin/bench/llm.rs` L273][U-b273]), verifies in the same process
  and writes no proof file (L311-L343). `--sequence n` is a prompt of n - 2 tokens and 2
  generated tokens (L78-L81), so the published "GPT-2, 512 tokens" is 510 + 2. It cannot prove a
  given request, so the adapter does not use it.
- The programs that take a given prompt and write a proof file are `deep-prove-worker one-shot`
  and `deep-prove-cli verify` ([`README.md` L37](https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/README.md#L37)).
  Their documentation is their `--help` text, the doc comments of their clap arguments
  ([`deep-prove/src/bin/worker/main.rs` L197-L347][U-wm], [`deep-prove/src/bin/cli/main.rs`
  L17-L70][U-cm]). The adapter passes only arguments listed there (AGENTS.md rule 1).
- What one proof states ([`zkml/README.md` L17-L21][U-zr17]): "concatenates the input tokens and
  the claimed output tokens into a single sequence, and runs the model on that sequence once ...
  the model's prediction at position `t` certifies the token at position `t+1`."
- Quantization: 12-bit symmetric by default, `ZKML_BIT_LEN` to change it
  ([`zkml/README.md` L11][U-zr11]). The adapter leaves it unset.

[U-zr]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/README.md#L113-L242
[U-zr11]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/README.md#L11
[U-zr17]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/README.md#L17-L21
[U-b273]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/src/bin/bench/llm.rs#L273
[U-wm]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/deep-prove/src/bin/worker/main.rs#L197-L347
[U-cm]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/deep-prove/src/bin/cli/main.rs#L17-L70

## 1. Subcommands and the arguments passed

| Subcommand | What runs | Arguments and source |
|---|---|---|
| `info`, `setup` | nothing upstream | |
| `commit` | nothing upstream: sha256 of `model.safetensors`, `config.json`, `tokenizer.json`, `vocab.json`, written to `/io/state/commit.json` with `verifier_key: null` | [§Weights binding](#weights-binding) |
| `prove` | `deep-prove-worker --tensor-store temporary one-shot --model /models/model.safetensors --model-format safetensors --tokenizer /models/tokenizer.json --config /models/config.json --max-new-tokens 512 --prompt=<text>`, once per request, working directory `/io/proofs/.tmp-req-<i>/`, `TMPDIR=/io/state/tmp` | `--tensor-store` required, `temporary` a tensor store in a temporary directory ([worker/main.rs L203-L205, L359-L361][U-ts]; [tenstore genstore.rs L77-L83][U-gs]); `one-shot` and its arguments [L277-L332][U-os]; `--prompt=` keeps a prompt that starts with `-` a value |
| `verify` | refuses before any upstream process, exit 1 | [§Weights binding](#weights-binding) |
| `mutate_reply` | nothing upstream (RFC-0018 AD-6) | [§Proof file](#proof-file) |

`prove`, step by step (one worker process per request, as `one-shot` proves one prompt a call,
[`immediate.rs` L140-L207][U-im140]):

1. The request's ids become text: each id's `vocab.json` string mapped back through GPT-2's byte
   alphabet, the bytes joined and read as UTF-8. The worker takes text, not ids, and tokenizes
   it with `tokenizer.json`, special tokens included ([`immediate.rs` L280-L282][U-im280];
   [`zkml/src/parser/llm/tokenizer.rs` L152-L163][U-tok]). A request whose bytes are not UTF-8
   (a window that cuts a character) or hold a NUL is refused.
2. The worker loads GPT-2 with a context of prompt + 512 = 1,024 positions (L255, L283-L286),
   makes its proving and verifier contexts (L159-L162), generates the greedy reply and proves one
   forward pass over prompt and reply (L164-L166), and writes `llm-proof-<random>.bin` into its
   working directory (L193-L205). Generation is inside the call, so RFC-0018 needs no
   generation marks (AD-4), and the reply is upstream's own (AD-3).
3. The adapter renames the file `proof.bin` (the CLI chooses its reader by the `.bin`
   extension, [`cli/main.rs` L187-L201][U-cm187]), checks that the file's `tokens` are the
   request's ids (refusing a proof of another tokenization), reads the reply from the file's IO
   ([§Proof file](#proof-file)) as `claimed_output`, and releases the directory by one rename.

[U-ts]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/deep-prove/src/bin/worker/main.rs#L203-L205
[U-os]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/deep-prove/src/bin/worker/main.rs#L277-L332
[U-gs]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/tenstore/src/genstore.rs#L77-L83
[U-im140]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/deep-prove/src/bin/worker/immediate.rs#L140-L207
[U-im280]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/deep-prove/src/bin/worker/immediate.rs#L280-L287
[U-tok]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/src/parser/llm/tokenizer.rs#L152-L163
[U-cm187]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/deep-prove/src/bin/cli/main.rs#L187-L201

## Weights binding

AGENTS.md rule 6: the commitment the verifier checks comes from the harness record, never from
files sent with the proof. At the pin DeepProve offers no way to meet it.

- `deep-prove-cli verify <proof.bin>` takes one argument, the proof file
  ([`cli/main.rs` L64-L69][U-cm64]). It decodes `LlmOneShotOutput` from that file and calls
  `llm.verifier.verify(llm.proof.proof, llm.tokens, llm.proof.io)` ([L221-L235][U-cm221]): the
  verifier key (`LLMVerifierContext`, which holds the model commitments,
  [`zkml/src/model/llm.rs` L63-L77][U-llm63]) is the one inside the proof file.
- The worker makes that key inside each proving call ([`immediate.rs` L159-L162][U-im159]) and
  has no option to load one ([worker/main.rs L277-L332][U-os]).
- The key's commitment parameters come from `PCS::test_setup(rng, ...)`
  ([`zkml/src/poly_commit/context.rs` L161-L167][U-pc166]) with `rng_from_env_or_random()`
  ([`zkml/src/iop/context.rs` L190-L197][U-ic190]): the `RNG_SEED` environment variable, else a
  random seed ([`zkml/src/lib.rs` L277-L288][U-lib278]). `RNG_SEED` appears in no README or
  document at the pin, so the adapter does not set it (rule 1). Each call therefore draws other
  parameters, and a key made by a separate step would not be the key a proof was made with.
- `bench-llm --save_params <name>` does write `<name>.vk` from the weights
  ([`zkml/README.md` L158-L174][U-zr158]; [`bench/llm.rs` L248-L263][U-b248]), but bench-llm
  proves only random prompts (L273) and writes no proof, and its key also comes from a random
  setup. It cannot be the commit step.
- Whether two context generations with the same seed give the same bytes is not stated.

So `commit` records the model files' digests and `verifier_key: null`, and `verify` refuses with
a message naming these lines. The gap closes if upstream documents (a) a step that makes the
verifier key from the weights, (b) proving against a given key, and (c) verifying against a key
given apart from the proof; or documents `RNG_SEED` and that the key's bytes are a function of
the weights, the seed and the context length, so `commit` can make the key and `verify` can
check that the proof's key is byte for byte the recorded one.

[U-cm64]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/deep-prove/src/bin/cli/main.rs#L64-L69
[U-cm221]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/deep-prove/src/bin/cli/main.rs#L221-L235
[U-llm63]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/src/model/llm.rs#L63-L77
[U-im159]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/deep-prove/src/bin/worker/immediate.rs#L159-L162
[U-pc166]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/src/poly_commit/context.rs#L161-L167
[U-ic190]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/src/iop/context.rs#L190-L197
[U-lib278]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/src/lib.rs#L277-L288
[U-zr158]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/README.md#L158-L174
[U-b248]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/src/bin/bench/llm.rs#L248-L263

## The end token

- The worker stops generating at the end token: the result thread returns at the first token
  equal to `eos_token` ([`zkml/src/model/llm.rs` L471-L481][U-llm471]), which GPT-2 reads from
  `config.json` `eos_token_id`, 50256 ([`gpt2/mod.rs` L182][U-g182]). The worker's arguments
  ([worker/main.rs L277-L332][U-os]) and bench-llm's (L59-L142) have no option to go on past
  it. Level 1 keeps the end token and goes on (RFC-0018 §Terms, `ignore_eos: true`).
- The adapter does not change this (no patch, and no edit of `config.json`, which upstream reads
  as the model's own). A reply that reaches 50256 before 512 tokens is proved shorter; `prove`
  reports the short `claimed_output` with a warning, and the harness's coverage check (RFC-0017
  INV-REQ-2, `check_requests`) fails the request, so the session is recorded incomplete.
- The verifier's end-token rule, read, not run: `verify` finds the first 50256 among the output
  rows from P - 1 on and takes its index **within those rows** as the unpadded length
  ([`llm.rs` L835-L847][U-llm835]); the shift check then runs `for i in seq_len - 1 ..
  unpadded_output_len - 1` ([L865-L875][U-llm865]), positions counted from the sequence start.
  Read this way, when any of those rows is 50256 (a reply cut by the end token, or a full reply
  whose next prediction, row 1,023, is 50256) the loop covers no reply position. The REPLY
  check's C1 trials test the verifier on our own runs whatever this reading says.

[U-llm471]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/src/model/llm.rs#L471-L491
[U-g182]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/src/parser/llm/models/gpt2/mod.rs#L182
[U-llm835]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/src/model/llm.rs#L835-L847
[U-llm865]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/src/model/llm.rs#L865-L875

## Proof file

The worker writes `LlmOneShotOutput` with bincode 2, `config::standard()` (little endian,
variable-length integers) ([`immediate.rs` L184-L200][U-im184]; the type,
[`deep-prove/src/middleware/llm.rs` L11-L21][U-mw]). The adapter reads, from the source and not
yet from a real file:

| Field | Encoding | Used for |
|---|---|---|
| `model_name`, `prompt` | varint length, UTF-8 | nothing |
| `tokens` | varint count, varint ids (`Token(usize)`, [`parser/llm/mod.rs` L50][U-tokty]) | the prompt the CLI passes the verifier as `user_input` ([`cli/main.rs` L235][U-cm221]); `prove` checks it equals the request |
| `llm_response` | option tag, string; "for logging only" ([`middleware/llm.rs` L11][U-mw]) | nothing |
| `proof.proof` | zkml's `Proof`, opaque to the adapter | nothing |
| `proof.io` | `IO { input: Vec<Tensor>, output: Vec<Tensor>, .. }` ([`iop/verifier.rs` L68-L75][U-io]); a tensor is `data`, `shape`, `unpadded_shape` ([`tensor/mod.rs` L108-L116][U-ten]); an element is serde bytes of arkworks' compressed scalar, 32 bytes little endian ([`zkml/src/lib.rs` L58][U-sf]; [dp-crypto `lib.rs` L9-L31][D-ser]) | `claimed_output`: input elements P to the unpadded length |
| `verifier` | `LLMVerifierContext`, opaque | the key rule 6 forbids ([§Weights binding](#weights-binding)) |

The IO follows the opaque proof, so the adapter finds it by content: the prompt's 512 elements
occur exactly once, preceded by the vector count 1 and the data length, and followed by the
shapes and the output tensor. Any other layout makes `prove` or `mutate_reply` exit non-zero
before releasing or writing anything. The first real proof file confirms or refutes this
reading.

[U-im184]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/deep-prove/src/bin/worker/immediate.rs#L184-L200
[U-mw]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/deep-prove/src/middleware/llm.rs#L11-L21
[U-tokty]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/src/parser/llm/mod.rs#L50
[U-io]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/src/iop/verifier.rs#L68-L75
[U-ten]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/src/tensor/mod.rs#L108-L116
[U-sf]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/src/lib.rs#L58
[D-ser]: https://github.com/Lagrange-Labs/dp-crypto/blob/22e8e93cd0f94a7638616a1ae22190feb0a6b275/dp-crypto/src/lib.rs#L9-L31

## Level 1 checks: how each control reaches the verifier

- **REPLY, C1.** The verifier takes no claimed reply: it reads the reply from the proof's IO
  input and compares each reply token with the argmax output of the row before
  ([`llm.rs` L865-L875][U-llm865]). C1 therefore goes through `mutate_reply` (RFC-0018 AD-6): it
  changes IO input element P + k and IO output element P + k - 1 to the new token, 32 bytes each
  in place, and leaves every other byte as it was. It decides nothing.
- **PROMPT, C2.** The CLI reads the claimed prompt from the file's `tokens` field and the
  verifier checks it against the IO input ([`llm.rs` L856-L863][U-llm856]). A working `verify`
  would write the job's `request` into `tokens`. Not written while `verify` refuses.
- **MODEL, P1 and C3.** `perturb` (AD-5) is not implemented. `levels/L1.yaml` names the change
  as one quantized weight of a block-0 dense layer moved by one step, "which its setup then
  commits". DeepProve quantizes the FP32 weights in each worker call (12-bit by default), so W'
  must be an FP32 file whose quantized value moves by one step; and no separate setup commits
  anything: each proving call makes a new key, so the change can be shown by the files' digests,
  not by a commitment id, and C3 needs the key gap closed first.
- **NO WEIGHT FILE.** `deep-prove-cli verify` reads only the proof file (L183-L185); the image
  has `strace` for the CH-4 trace once `verify` runs.

[U-llm856]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/src/model/llm.rs#L856-L863

## 2. Verdict mapping

`verify` produces no verdict at this commit: it exits 1 with the rule 6 message before any
upstream process. For reference, upstream's signals: `deep-prove-cli verify` returns `Ok` and
logs "Proof verified successfully" on success ([`cli/main.rs` L239-L242][U-cm239]); any error,
from reading the file to a failed check, is returned from `main` as an `anyhow` error (exit 1).
A mapping onto the four verdicts is written when the key gap closes.

[U-cm239]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/deep-prove/src/bin/cli/main.rs#L239-L242

## 3. commitment_id, verifier_files, prover_files

- `verifier_files`: `/io/state/commit.json` (the model files' sha256, `verifier_key: null`, and
  why). `commitment_id`: sha256 over that file's digest (the convention of the SASH adapter).
  It identifies the record; no upstream verifier checks it.
- `prover_files`: none. The worker reads the model from `/models` in each call.

## 4. Values for system.yaml

- `granularity: request`, `incremental_proofs: true`, `steady_boundary: first_proof`: one worker
  process and one proof per request, each released when its process ends.
- `tokens_covered: prompt_plus_output`: one forward pass over the prompt and the reply
  ([`zkml/README.md` L17-L21][U-zr17]).
- `deterministic_proofs: false`: each call draws a new setup ([§Weights binding](#weights-binding)).
- `verify_reads: all`: the one part, `proof.bin`, is read whole.
- `forbidden_flags: []`: no upstream option weakens the statement. The adapter refuses every
  control flag.
- `image`: `local/deepprove` with a placeholder digest (all zeros) until the integrator builds
  the image; the runner's integrity check refuses jobs until then.

## 5. Toolchain

- Rust `nightly-2026-01-27`, upstream's `rust-toolchain.toml`
  ([L2](https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/rust-toolchain.toml#L2)),
  as the standalone tarball with its published checksum (`inputs.lock`).
- Build packages as upstream's own Dockerfile installs them (git, protobuf-compiler, libssl-dev,
  pkg-config, cmake, build-essential, g++, libclang-dev,
  [`docker/deep-prove-worker.dockerfile` L2][U-df]) at exact Ubuntu 24.04 versions; upstream's
  runtime image is Ubuntu 24.04 too (L11). Upstream builds in `rustlang/rust:nightly-slim`, an
  unpinned tag; the adapter uses the toolchain file's nightly instead.
- Default features: the CPU build, ndarray backend and HyperKZG on BN254
  ([`zkml/README.md` L36, L111][U-zr36]). The worker's commitment scheme is fixed to
  `HyperKZG<Bn254>` whatever the features ([`immediate.rs` L38-L39][U-im38]); the GPU scheme
  `HyperKZGGpu` is chosen only in bench-llm ([`bench/llm.rs` L36-L39][U-b36]).
- No GPU was used and no image was built for this adapter yet.

[U-df]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/docker/deep-prove-worker.dockerfile#L1-L11
[U-zr36]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/README.md#L36
[U-im38]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/deep-prove/src/bin/worker/immediate.rs#L38-L39
[U-b36]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/src/bin/bench/llm.rs#L36-L39

## 6. CPU binding

Upstream gives no CPU binding advice for the worker. bench-llm takes `--num_threads` (rayon
threads, [`bench/llm.rs` L109-L113, L163-L177][U-b109]); the worker has no such option, so the
adapter sets none and the process runs on the CPUs the harness's cpuset gives it.

[U-b109]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/src/bin/bench/llm.rs#L109-L177

## Machine

- Upstream's figures are on CPU: "24-core / 504 GB CPU machine (AMD EPYC 9254, 2.9 GHz),
  HyperKZG PCS, default quantization"; GPT-2 at "sequence 512" (510 + 2): 7.64 min to prove,
  1.33 s to verify, 10.71 MiB of proof ([`zkml/README.md` L244-L253][U-zr244]). No figure is
  published for 1,024 positions or for 512 generated tokens, and the peak memory is not published
  (bench-llm measures it, L315-L328). "Large LLMs at long context windows require substantial
  RAM" (L324).
- Proposed profile `prover-cpu-hosted` (not yet in `reference/`): no GPU; at least 24 physical
  cores; at least 504 GB of host memory, the publisher's machine, until a probe measures the peak
  at 1,024 positions; 50 GB of disk (proofs of about 11 MiB, the temporary tensor store
  unmeasured). The verifier profile is unchanged (`verifier-cpu-hosted`): upstream verifies in
  about 1.3 s at 512 positions.
- Level 1 prices GPU-seconds only (`reference/v1.0.yaml`, `priced: [gpu]`). A CPU row needs a CPU
  price basis, or runs on an H200 host whose bound GPU stays idle and is priced: the integrator
  decides.

[U-zr244]: https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/zkml/README.md#L244-L253

## 7. Deviations from upstream's own measuring setup

- Upstream measures with bench-llm on random prompts and 2 generated tokens; the adapter runs the
  worker on the level's prompts and 512 generated tokens.
- The worker makes its proving and verifier contexts in every call, so each request pays for
  them; bench-llm can load saved ones (`--load_params`).
- The prompt is passed as text and tokenized by upstream ([§1](#1-subcommands-and-the-arguments-passed)).
  A Level 1 prompt whose text does not tokenize back to its ids fails its request.
- Built without upstream's `otel` feature (OpenTelemetry export,
  [`deep-prove/Cargo.toml` L12-L18](https://github.com/Lagrange-Labs/deep-prove/blob/9d1a53e2ef49ffa2c902b8689cd3c58057a4e662/deep-prove/Cargo.toml#L12-L18)):
  a container without network has nothing to export to.
- `TMPDIR` points the temporary tensor store at `/io/state/tmp` rather than the container's
  `/tmp` tmpfs.

## Open items

1. Weights binding (above): ask Lagrange, with the permission request.
2. The end token: count, on CPU, how many of the rung's 15 prompts give a greedy GPT-2 reply with
   50256 in its first 512 tokens, or as the 513th prediction. With DeepProve's own quantized
   model the count may differ; the first worker run shows it.
3. Prompt round trip: check, on CPU, that each of the 15 prompts' text tokenizes back to its ids
   with `tokenizer.json` (the `tokenizers` library).
4. `perturb` for the level's model change; there is no `claim.yaml` or `properties.yaml` yet.
   The level file's security words cite the book's commitment scheme (Basefold,
   `docs/src/commitments.md`); the programs this adapter runs use HyperKZG on BN254
   ([`zkml/README.md` L36][U-zr36]; [`immediate.rs` L38-L39][U-im38]).
5. An image of this Dockerfile has not been built; the first build checks the apt pins, the
   archive digest and that the workspace builds offline after `cargo fetch`.

## Tests

`systems/deepprove/tests/` run on CPU with `deepprove_stub.py` standing in for the worker; its
proof files follow the layout read above and are not captured upstream outputs.
