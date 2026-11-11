#!/usr/bin/env python3
"""A stand-in for the DeepProve worker, for CPU tests only.

The adapter runs `deepprove_stub.py <argv...>` when IPROOFS_DEEPPROVE_EXEC names this file. For
`deep-prove-worker ... one-shot` it writes one `llm-proof-<random>.bin` into its working
directory, laid out as the adapter reads upstream's (README.md §Proof file): the leading fields
of LlmOneShotOutput, opaque bytes for the Proof, the IO tensors, opaque bytes for the verifier
key. Nothing here is a captured upstream output. It tokenizes byte by byte (ids 0 to 255 are
GPT-2's single-byte tokens). IPROOFS_DEEPPROVE_STUB_EOS=k ends the reply at the end token after
k tokens; IPROOFS_DEEPPROVE_STUB_DROP=1 drops the first prompt token, as a tokenizer that does
not give the request's ids back would. Any other program exits 99.
"""

import itertools
import os
import sys
from pathlib import Path

EOS = 50256
PROOF_BYTES = bytes(range(256)) * 4  # stands in for zkml's Proof
VERIFIER_BYTES = b"\x09" * 300  # stands in for LLMVerifierContext


def byte_ids() -> dict[int, int]:
    """byte -> GPT-2 id of its single-byte token (the bytes_to_unicode order)."""
    bs = [*range(0x21, 0x7F), *range(0xA1, 0xAD), *range(0xAE, 0x100)]
    bs += [b for b in range(256) if b not in bs]
    return {b: i for i, b in enumerate(bs)}


def varint(v: int) -> bytes:
    if v < 251:
        return bytes([v])
    for tag, width in ((251, 2), (252, 4), (253, 8)):
        if v < 1 << (8 * width):
            return bytes([tag]) + v.to_bytes(width, "little")
    raise ValueError(v)


def string(s: str) -> bytes:
    raw = s.encode()
    return varint(len(raw)) + raw


def field(v: int) -> bytes:
    return b"\x20" + v.to_bytes(32, "little")


def tensor(data: list[int], unpadded: int) -> bytes:
    return (varint(len(data)) + b"".join(field(v) for v in data) + varint(1) + varint(len(data))
            + varint(1) + varint(unpadded))  # fmt: skip


def reply_of(prompt: list[int], n: int) -> list[int]:
    return [(sum(prompt) + 7 * j) % 250 + 1 for j in range(n)]


def proof_file(prompt_text: str, tokens: list[int], prompt: list[int], new: int,
               eos_after: int | None) -> bytes:  # fmt: skip
    """The bytes of one proof: tokens is what upstream tokenized, prompt the sequence proved."""
    k = new if eos_after is None else eos_after
    reply = reply_of(prompt, k)
    seq = prompt + reply
    padded = seq + [0] * ((1 << (len(seq) - 1).bit_length()) - len(seq))
    # row i predicts token i + 1; the last row predicts what follows the reply
    out = [(3 * t) % 256 for t in prompt[1:]] + reply + [EOS if eos_after is not None else 42]
    out += [0] * (len(padded) - len(out))
    head = (string("gpt2") + string(prompt_text) + varint(len(tokens))
            + b"".join(varint(t) for t in tokens) + b"\x01" + string("response"))  # fmt: skip
    io = varint(1) + tensor(padded, len(seq)) + varint(1) + tensor(out, len(seq)) + b"\x00\x00"
    return head + PROOF_BYTES + io + VERIFIER_BYTES


def worker(argv: list[str]) -> int:
    opts = {a: b for a, b in itertools.pairwise(argv) if a.startswith("--")}
    text = next(a for a in argv if a.startswith("--prompt="))[len("--prompt=") :]
    assert argv[:3] == ["--tensor-store", "temporary", "one-shot"], argv
    assert Path(opts["--model"]).name == "model.safetensors"
    ids = byte_ids()
    prompt = [ids[b] for b in text.encode()]
    tokens = prompt[1:] if os.environ.get("IPROOFS_DEEPPROVE_STUB_DROP") else prompt
    eos = os.environ.get("IPROOFS_DEEPPROVE_STUB_EOS")
    data = proof_file(text, tokens, prompt, int(opts["--max-new-tokens"]),
                      int(eos) if eos else None)  # fmt: skip
    Path(f"llm-proof-{os.getpid():010d}.bin").write_bytes(data)
    print("Successfully generated LLM proof", file=sys.stderr)
    return 0


def main() -> int:
    program, argv = Path(sys.argv[1]).name, sys.argv[2:]
    if program == "deep-prove-worker":
        return worker(argv)
    print(f"stub: no stand-in for {program}", file=sys.stderr)
    return 99


if __name__ == "__main__":
    sys.exit(main())
