"""Command-line entry point: argparse, exit codes (RFC-0010 §Command line)."""

import argparse
import subprocess
from pathlib import Path

from iproofs import __version__


def harness_commit() -> str:
    """Return the git commit of the harness checkout, or "unknown" outside a checkout."""
    try:
        out = subprocess.run(
            ["git", "-C", str(Path(__file__).resolve().parent), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="iproofs")
    parser.add_argument(
        "--version", action="version", version=f"iproofs {__version__} ({harness_commit()})"
    )
    parser.parse_args(argv)
    return 0
