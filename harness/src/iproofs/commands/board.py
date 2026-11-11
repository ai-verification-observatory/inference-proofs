"""`iproofs release board RELEASE [--check]` (RFC-0018 §The board file).

Without `--check` it writes `releases/<release>/board.json` and prints its path. With `--check`
it recomputes the board from the stored records and compares it with the stored file byte for
byte, as `iproofs derive --check` does for a run.
"""

import argparse
import sys
from pathlib import Path

from iproofs.commands import Command


def _release_actions(
    sub: "argparse._SubParsersAction[argparse.ArgumentParser]",
) -> "argparse._SubParsersAction[argparse.ArgumentParser]":
    """The `release` command's own subcommands, so `board` sits beside `freeze` and `plan`."""
    release = sub.choices["release"]
    for action in release._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    raise RuntimeError("the release command has no subcommands")  # a harness bug


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]", command: Command) -> None:
    """Add `board` to the `release` command."""
    p = command(
        "board",
        "write releases/<release>/board.json (RFC-0018)",
        _release_actions(sub),
        "release board",
    )
    p.add_argument("release")
    p.add_argument("--level", default="L1", help="the level file's id (default: L1)")
    p.add_argument(
        "--check", action="store_true", help="recompute and compare with the stored file"
    )
    p.set_defaults(handler=release_board)


def release_board(args: argparse.Namespace) -> int:
    """Build, validate against `board/1`, then write or compare."""
    from iproofs.board import board_path, build_board  # noqa: PLC0415
    from iproofs.errors import ErrorKind, IProofsError  # noqa: PLC0415
    from iproofs.schema import SchemaRegistry  # noqa: PLC0415
    from iproofs.serialize import dumps, write_json  # noqa: PLC0415
    from iproofs.validate import repo_root  # noqa: PLC0415

    root = repo_root(Path.cwd())
    board = build_board(root, args.release, args.level)
    errors = SchemaRegistry.from_tree(root / "schema").errors("board/1", board)
    if errors:
        raise IProofsError(ErrorKind.INTERNAL, f"board.json fails board/1: {errors[0]}")
    out = board_path(root, args.release)
    if args.check:
        if not out.is_file():
            print(f"release board: no {out.relative_to(root)}", file=sys.stderr)
            return 1
        if out.read_bytes() != dumps(board):
            print(f"release board: {out.relative_to(root)} differs from the recomputed board",
                  file=sys.stderr)  # fmt: skip
            return 1
        print(f"release board: {out.relative_to(root)} matches", file=sys.stderr)
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    write_json(out, board)
    print(out.relative_to(root))
    return 0
