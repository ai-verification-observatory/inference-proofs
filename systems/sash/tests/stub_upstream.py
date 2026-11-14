#!/usr/bin/env python3
"""A stand-in for every upstream process the SASH adapter starts, for CPU tests only.

The adapter runs `stub_upstream.py <argv...>` when IPROOFS_SASH_EXEC names this file. It writes
the few files the adapter reads next, shaped as upstream's source says they are; nothing here
is a captured upstream output. IPROOFS_SASH_STUB_GRID picks the `boundary-grid` outcome
(`accept`, `reject_segment`, `reject_chain`, `panic`), IPROOFS_SASH_STUB_TOK the ids every
layer-0 statement states. A head extraction over given ids (`--head --ids`) writes head dumps
of a vocabulary of 8: `head_dump` says which token each row emits.
"""

import hashlib
import json
import os
import re
import struct
import sys
from pathlib import Path

# prover/src/compose.rs EDGES at eb95bfa, the names `provenance.binding` prints
EDGES = (
    "residual stream into the first norm's reduction",
    "first norm's output into the q, k, v matmul inputs",
    "q, k, v outputs into the attention block",
    "attention scores and values into the attention output",
    "attention output into the o matmul input",
    "o output into the first residual add",
    "first residual add into the second norm's reduction",
    "second norm's output into the gate and up matmul inputs",
    "gate and up outputs into the SwiGLU product",
    "SwiGLU output into the down matmul input",
    "down output into the second residual add",
    "each matmul's input times the pinned weights into its accumulator",
    "residual stream out of this segment into the next layer's segment",
    "keys and values out of this token block into the next block",
    "embedding row into the first segment's residual stream",
    "logits into the emitted token",
)
UNBINDS = {"residual-stream": {1, 2, 3, 5, 6, 7, 8, 9, 10, 11}, "layer-boundary": {13},
           "kv-boundary": {14}, "argmax": {16}, "embedding": {15}, "argmax-lax": {16}}  # fmt: skip


def host(p: str) -> Path:
    return Path(os.environ["IPROOFS_IO"] + p[3:]) if p.startswith("/io") else Path(p)


def opt(argv: list[str], name: str) -> str:
    return argv[argv.index(name) + 1]


def bound(ser: Path, tag: str) -> bool:
    """The stand-in's proof of a segment is the sha256 of its statement, so a changed statement
    is a rejected segment, as verify_composed's Horner checks make it."""
    fixed = (ser / f"{tag}.fixed.json").read_bytes()
    return (ser / f"{tag}.proof.json").read_text() == hashlib.sha256(fixed).hexdigest()


def grid_of(argv: list[str]) -> int:
    """boundary-grid on the stand-in's files: every proof bound to its statement, and each id of
    the last block equal to the argmax the head before it emitted."""
    ser = host(opt(argv, "--dir"))
    plan = host(opt(argv, "--plan")).read_text().splitlines()
    tags = [ln.split()[-1] for ln in plan if ln and not ln.startswith("#")]
    accepted = sum(bound(ser, t) for t in tags)
    blocks = sorted({int(re.match(r"B(\d+)", t).group(1)) for t in tags})  # type: ignore[union-attr]
    b = blocks[-1]
    load = lambda t: json.loads((ser / f"{t}.fixed.json").read_text())  # noqa: E731
    tok_in, here, before = (
        load(f"B{b}L0")["tok_in"],
        load(f"B{b}head")["tok_out"],
        load(f"B{b - 1}head")["tok_out"],
    )
    emitted = [before[-1], *here[:-1]]
    bad = [t for t, (i, e) in enumerate(zip(tok_in, emitted, strict=True)) if i != e]
    ok = accepted == len(tags) and not bad
    doc = {"result": {"all_chain": True, "failures": [],
                      "verified": {"run": len(tags), "accepted": accepted,
                                   "all": accepted == len(tags)},
                      "tokens": {"all": not bad, "mismatches": bad, "unbacked": []}}}  # fmt: skip
    print(json.dumps(doc, indent=1))
    print(f"grid: {'ok' if ok else 'FAIL'}", file=sys.stderr)
    return 0 if ok else 1


def grid(outcome: str) -> int:
    if outcome == "panic":
        print("thread 'main' panicked at prover/src/boundary.rs: stub", file=sys.stderr)
        return 101
    bad = outcome == "reject_segment"
    chain = outcome != "reject_chain"
    doc = {"result": {"all_chain": chain, "failures": [] if chain else ["B1L0 -> B1L1"],
                      "verified": {"run": 8, "accepted": 7 if bad else 8, "all": not bad},
                      "tokens": {"all": True, "mismatches": [], "unbacked": []}}}  # fmt: skip
    print(json.dumps(doc, indent=1))
    print(f"grid: {'FAIL' if bad or not chain else 'ok'}", file=sys.stderr)
    return 1 if bad or not chain else 0


VOCAB = 8
# bf16 patterns of the three logits a stub row holds, and extract.py's order key of each
# (`sign ? 0x7FFF - mag : 0x8000 + mag`): 2.0 = 0x4000, 1.0 = 0x3F80, -1.0 = 0xBF80
KEY_TOP, KEY_SECOND, KEY_REST = 0x8000 + 0x4000, 0x8000 + 0x3F80, 0x7FFF - 0x3F80


def head_dump(argv: list[str]) -> int:
    """The head dumps of `extract --head --ids`: for each block, `tok_head.i32`, `key_head.u16`
    (rows x 8) and the manifest's count of rows that emit the next id. Row t of block b emits
    the id after it, except at the reply positions IPROOFS_SASH_STUB_MISS lists (0-based, a
    JSON list), where it emits that id plus 1 modulo 8; the next id modulo 8 holds the second
    logit there. The request IPROOFS_SASH_STUB_REFUSE names (by its place in the call order) is
    refused the way extract.py's assertions refuse."""
    blob = host(opt(argv, "--ids")).read_bytes()
    n = int(opt(argv, "--tokens"))
    ids = list(struct.unpack(f"<{n}q", blob[-8 * n :]))
    s = int(opt(argv, "--chunk"))
    calls = host("/io/stub-head-calls")
    calls.write_text(str(int(calls.read_text()) + 1 if calls.is_file() else 1))
    if os.environ.get("IPROOFS_SASH_STUB_REFUSE") == str(int(calls.read_text()) - 1):
        print("Traceback (most recent call last):", file=sys.stderr)
        print("AssertionError: block 1 layer 16: the attention output leaves the no-wrap "
              "window (stub)", file=sys.stderr)  # fmt: skip
        return 1
    if os.environ.get("IPROOFS_SASH_STUB_REFUSE") == "crash":
        print("RuntimeError: CUDA out of memory (stub)", file=sys.stderr)
        return 1
    miss = set(json.loads(os.environ.get("IPROOFS_SASH_STUB_MISS", "[]")))
    prompt = n - s
    for b in map(int, opt(argv, "--blocks").split(",")):
        dump = host(f"{opt(argv, '--out')}_B{b}")
        dump.mkdir(parents=True)
        tok, keys = [], []
        for t in range(s):
            nxt = ids[b * s + t + 1] % VOCAB if b * s + t + 1 < n else 0
            top = (nxt + 1) % VOCAB if b * s + t + 1 - prompt in miss else nxt
            tok.append(top)
            row = [KEY_REST] * VOCAB
            row[top] = KEY_TOP
            row[(top + 1) % VOCAB if top == nxt else nxt] = KEY_SECOND
            keys += row
        (dump / "tok_head.i32").write_bytes(struct.pack(f"<{s}i", *tok))
        (dump / "key_head.u16").write_bytes(struct.pack(f"<{s * VOCAB}H", *keys))
        emits = sum(tok[t] == ids[b * s + t + 1] for t in range(s - 1) if b * s + t + 1 < n)
        (dump / "manifest.json").write_text(json.dumps({"head": {"emits_next_token": emits}}))
    return 0


def harness(argv: list[str]) -> int:
    mod = argv[argv.index("-m") + 1] if "-m" in argv else ""
    if (
        mod == "harness.witness.extract"
        and "--head" in argv
        and "--ids" in argv
        and host(opt(argv, "--ids")).name == "ids.npy"
        and "score-" in opt(argv, "--ids")
    ):
        return head_dump(argv)
    if mod == "harness.witness.gen_ids":  # which proofs were released before this request began
        seen = (
            sorted(p.name for p in host("/io/proofs").iterdir())
            if host("/io/proofs").is_dir()
            else []
        )
        with host("/io/stub-released.jsonl").open("a") as f:
            f.write(json.dumps(seen) + "\n")
    elif mod == "harness.witness.extract":  # common.tokens() and ppl.ACALIB write these
        for name in ("tokens.npz", "attn_ranges.json"):
            (host(os.environ["ZK_OUT"]) / name).touch()
    elif mod == "harness.witness.shapes" and "--merge" in argv:
        worst = {"kmax": 19, "ao_rem_bits": 20, "fold_rem_bits": 15, "fold_alpha": 6}
        host(opt(argv, "--out")).write_text(json.dumps({"worst": worst}))
    elif mod == "harness.witness.plan":
        nb, hb = int(opt(argv, "--blocks")), opt(argv, "--head-blocks").split(",")
        last = int(opt(argv, "--layers").split("-")[1])
        lines = [f"--table-bits 24 --witness w --ser-tag B{b}L{k}"
                 for b in range(nb) for k in range(last + 1)]  # fmt: skip
        lines += [f"--table-bits 25 --witness h --ser-tag B{b}head" for b in hb]
        host(opt(argv, "--out")).write_text("# stub plan\n" + "\n".join(lines) + "\n")
        host(opt(argv, "--emit-out")).write_text(lines[0] + "\n")
    elif "-c" in argv and "worst_of" in argv[argv.index("-c") + 1]:
        print("--ao-rem-bits 20")
    return 0


def compose_chunks(argv: list[str]) -> int:
    lo, hi = map(int, opt(argv, "--plan-slice").split(":"))
    plan = host(opt(argv, "--plan")).read_text().splitlines()
    tags = [ln.split()[-1] for ln in plan if ln and not ln.startswith("#")][lo:hi]
    ser, tok = host(opt(argv, "--ser-dir")), json.loads(os.environ["IPROOFS_SASH_STUB_TOK"])
    nb = 1 + max(int(ln.split()[-1][1:].split("L")[0].split("h")[0]) for ln in plan
                 if ln and not ln.startswith("#"))  # fmt: skip
    for t in tags:
        fixed: dict[str, list[int]] = {"tok_in": tok if re.fullmatch(r"B\d+L0", t) else []}
        if t == f"B{nb - 1}head":  # the head emits each next id; the last is past the reply
            fixed = {"tok_out": [*tok[1:], 0]}
        elif t.endswith("head"):  # the last prompt block's head emits the reply's first id
            fixed = {"tok_out": [0] * (len(tok) - 1) + [tok[0]]}
        text = json.dumps(fixed, indent=1)
        (ser / f"{t}.fixed.json").write_text(text)
        (ser / f"{t}.claims.json").write_text("{}")
        (ser / f"{t}.proof.json").write_text(hashlib.sha256(text.encode()).hexdigest())
    # util.rs unsound_skips(), and the edges each switch unbinds (prover/README.md#L86-L102)
    skips = [a.removeprefix("--unsound-skip-") for a in argv if a.startswith("--unsound-skip-")]
    skips += ["argmax-lax"] * argv.count("--unsound-argmax-lax")
    off = {n for s in skips for n in UNBINDS[s]}
    edges = [{"n": n, "edge": e, "state": "unbound" if n in off else "bound"}
             for n, e in enumerate(EDGES, 1)]  # fmt: skip
    print(json.dumps({"provenance": {"unsound_skips": skips, "binding": {"edges": edges}}}))
    return 0


def prover(argv: list[str]) -> int:
    if argv[1] == "model-roots":
        roots = [{"layer": 0, "c": 0, "model_root": "ab"}]
        host(opt(argv, "--out")).write_text(json.dumps(roots))
    elif argv[1] == "compose-chunks":
        return compose_chunks(argv)
    elif argv[1] == "boundary-grid":
        outcome = os.environ.get("IPROOFS_SASH_STUB_GRID", "check")
        return grid_of(argv) if outcome == "check" else grid(outcome)
    return 0


def cargo(argv: list[str]) -> int:
    lib = host(os.environ["CARGO_TARGET_DIR"]) / "release/build/stwo-0/out/libstwo_cuda.a"
    lib.parent.mkdir(parents=True, exist_ok=True)
    lib.write_bytes(b"")
    return 0


TOOLS = {"uv": harness, "zk-prover-simd": prover, "zk-prover": prover, "cargo": cargo,
         "nvidia-smi": lambda _: print("9.0") or 0,
         "cuobjdump": lambda _: print("ELF file 1: libstwo_cuda.1.sm_90.cubin") or 0}  # fmt: skip


def main(argv: list[str]) -> int:
    return TOOLS.get(Path(argv[0]).name, lambda _: 0)(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
