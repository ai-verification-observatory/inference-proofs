#!/usr/bin/env python3
"""A stand-in for every upstream process the SASH adapter starts, for CPU tests only.

The adapter runs `stub_upstream.py <argv...>` when IPROOFS_SASH_EXEC names this file. It writes
the few files the adapter reads next, shaped as upstream's source says they are; nothing here
is a captured upstream output. IPROOFS_SASH_STUB_GRID picks the `boundary-grid` outcome
(`accept`, `reject_segment`, `reject_chain`, `panic`), IPROOFS_SASH_STUB_TOK the ids every
layer-0 statement states.
"""

import json
import os
import re
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


def harness(argv: list[str]) -> int:
    mod = argv[argv.index("-m") + 1] if "-m" in argv else ""
    if mod == "harness.witness.extract":  # common.tokens() and ppl.ACALIB write these
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
    for t in tags:
        fixed = {"tok_in": tok if re.fullmatch(r"B\d+L0", t) else []}
        (ser / f"{t}.fixed.json").write_text(json.dumps(fixed))
        (ser / f"{t}.claims.json").write_text("{}")
        (ser / f"{t}.proof.json").write_text("{}")
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
        return grid(os.environ.get("IPROOFS_SASH_STUB_GRID", "accept"))
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
