"""`iproofs level` subcommands (RFC-0018): check, beacon, prompts.

`level beacon` sits under `level` because `prompts` is already a group of `iproofs.cli`.
"""

import argparse
import sys
from pathlib import Path

from iproofs.commands import Command


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]", command: Command) -> None:
    """Add this module's subcommands to the top-level parser."""
    level = sub.add_parser("level", help="level files, beacon rounds and rung prompts (RFC-0018)")
    level_sub = level.add_subparsers(dest="level_command", required=True, metavar="ACTION")

    p = command("check", "check a level file and the files it names", level_sub, "level check")
    p.add_argument("--level", default="L1", help="level id (default: L1)")
    p.add_argument(
        "--frozen", action="store_true", help="also refuse any value a frozen level needs"
    )
    p.set_defaults(handler=level_check)

    p = command(
        "beacon",
        "fetch the level's beacon round from its relays and write levels/<id>-beacon.json"
        " (network)",
        level_sub,
        "level beacon",
    )
    p.add_argument("--level", default="L1", help="level id (default: L1)")
    p.add_argument("--round", type=int, help="the round; default: the level file's")
    p.set_defaults(handler=level_beacon)

    p = command(
        "prompts",
        "materialise a rung's prompts, slots and KL windows from the stored beacon round",
        level_sub,
        "level prompts",
    )
    p.add_argument("rung")
    p.add_argument("--level", default="L1", help="level id (default: L1)")
    p.add_argument("--out", type=Path, required=True, help="directory to write into")
    p.set_defaults(handler=level_prompts)


def level_check(args: argparse.Namespace) -> int:
    """`iproofs level check [--frozen]`: prints the level's digest, or fails `config` with
    every problem."""
    from iproofs.errors import ErrorKind, IProofsError  # noqa: PLC0415
    from iproofs.level import check_level, level_digest, level_file, load_level  # noqa: PLC0415
    from iproofs.validate import repo_root  # noqa: PLC0415

    root = repo_root(Path.cwd())
    level = load_level(root, args.level)
    problems = check_level(root, level, frozen=args.frozen)
    path = level_file(root, args.level)
    if problems:
        raise IProofsError(ErrorKind.CONFIG, "\n".join(f"{path.name}: {p}" for p in problems))
    state = f"frozen {level.frozen}" if level.frozen else "draft"
    print(f"{path.name}: ok ({state}) {level_digest(path)}")
    return 0


def level_beacon(args: argparse.Namespace) -> int:
    """`iproofs level beacon [--round R]`: PR-2. Fetches the round (by default the first one after
    the commit that froze the level file) from every relay of the level, checks it, and writes
    levels/<id>-beacon.json; refuses to replace a stored record of another round."""
    import json  # noqa: PLC0415

    from iproofs.errors import ErrorKind, IProofsError  # noqa: PLC0415
    from iproofs.level import beacon_file, beacon_round, fetch_beacon, load_level  # noqa: PLC0415
    from iproofs.schema import SchemaRegistry  # noqa: PLC0415
    from iproofs.serialize import write_json  # noqa: PLC0415
    from iproofs.validate import repo_root  # noqa: PLC0415
    from iproofs.workloads import http_get  # noqa: PLC0415

    root = repo_root(Path.cwd())
    registry = SchemaRegistry.from_tree(root / "schema")
    level = load_level(root, args.level, registry=registry)
    beacon = level.prompts.beacon
    rule = beacon_round(root, level) if level.frozen is not None else None
    round_ = args.round if args.round is not None else rule
    if round_ is None:
        raise IProofsError(ErrorKind.CONFIG, f"{level.id} is a draft: pass --round for a probe")
    if rule is not None and round_ != rule:
        raise IProofsError(ErrorKind.CONFIG, f"{level.id} takes round {rule} (PR-2), not {round_}")
    path = beacon_file(root, level.id)
    if path.is_file():
        stored = json.loads(path.read_text())
        if stored.get("round") != round_ or stored.get("chain_hash") != beacon.chain_hash:
            raise IProofsError(
                ErrorKind.CONFIG, f"{path} holds another round; remove it to fetch round {round_}"
            )
    record = fetch_beacon(round_, beacon.relays, http_get, chain_hash=beacon.chain_hash)
    errors = registry.errors("beacon/1", record)
    if errors:
        raise IProofsError(ErrorKind.INTERNAL, "\n".join(errors))
    write_json(path, record)
    print(path)
    return 0


def level_prompts(args: argparse.Namespace) -> int:
    """`iproofs level prompts RUNG --out DIR`: PR-3 from the stored beacon record. Writes
    prompts.jsonl (slots·N), slot-<k>.jsonl, kl-texts.jsonl and baseline.jsonl; prints
    their digests as JSON."""
    from iproofs.errors import ErrorKind, IProofsError  # noqa: PLC0415
    from iproofs.level import (  # noqa: PLC0415
        baseline_prompts,
        beacon_seed,
        kl_texts,
        level_digest,
        level_file,
        load_beacon,
        load_level,
        rung_prompts,
        rung_stream,
        rung_tokenizer_workload,
        slot_prompts,
    )
    from iproofs.serialize import dumps, write_jsonl  # noqa: PLC0415
    from iproofs.validate import repo_root  # noqa: PLC0415
    from iproofs.workloads import (  # noqa: PLC0415
        default_cache,
        local_corpus,
        pinned_corpus,
        tokenizer_file,
        tokenizer_for,
        tokenizers_version,
    )

    root = repo_root(Path.cwd())
    level = load_level(root, args.level)
    rung = level.rung(args.rung)
    record = load_beacon(root, level)
    digest = level.prompts.corpus_digest
    texts = local_corpus(root, digest) or pinned_corpus(root, digest)
    if texts is None:
        raise IProofsError(ErrorKind.CONFIG, f"corpus {digest} is not available locally")
    wl = rung_tokenizer_workload(root, level, rung)
    tokenizer = tokenizer_for(tokenizer_file(root, wl, default_cache()))
    randomness = str(record["randomness"])
    stream = rung_stream(texts, tokenizer, level, rung, randomness)
    prompts = rung_prompts(stream, level, rung)
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    files = {"prompts": write_jsonl(out / "prompts.jsonl", prompts)}
    for k in range(1, level.sessions.slots + 1):
        rows = slot_prompts(prompts, k, rung.requests_per_session)
        files[f"slot-{k}"] = write_jsonl(out / f"slot-{k}.jsonl", rows)
    files["kl-texts"] = write_jsonl(out / "kl-texts.jsonl", kl_texts(stream, level, rung))
    files["baseline"] = write_jsonl(out / "baseline.jsonl", baseline_prompts(stream, level, rung))
    result = {
        "level": {"id": level.id, "digest": level_digest(level_file(root, level.id))},
        "rung": rung.id,
        "tokenizer_workload": wl.id,
        "beacon": {"round": record["round"], "seed": f"0x{beacon_seed(randomness):016x}"},
        "files": files,
        "tokenizers_version": tokenizers_version(),
    }
    sys.stdout.write(dumps(result).decode())
    return 0
