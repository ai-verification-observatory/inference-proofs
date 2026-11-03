"""INV-GOV-4 (RFC-0001 §Conflicts of interest rule 2): a maintainer with a declared interest in
a system does not alone approve a change to that system's files.

Rule `GOV-5`, under G2. The signal is the pull request's approvals, not the merge actor: the
platform names the merger only after the merge. A change touching `systems/<name>/` or
`results/<release>/<name>/` fails when every approving maintainer declared an interest in
`<name>` (in "Declared interests" or "Systems maintained"); a second, unconflicted maintainer's
approval clears it. Where no CI runs, reviewers make the same check (CONTRIBUTING.md).

    python -m iproofs.validate.merge_guard --base REF --approved handle1,handle2
"""

import argparse
import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

from iproofs.errors import ErrorKind
from iproofs.validate import Finding, repo_root
from iproofs.validate.governance import PATH, Row, parse

SYSTEM_PATH = re.compile(r"^(?:systems|results/[^/]+)/([a-z][a-z0-9-]*)/")


def touched_systems(paths: Iterable[str]) -> set[str]:
    """Systems whose adapter, claim card, results, control registration or replies change."""
    return {m.group(1) for p in paths if (m := SYSTEM_PATH.match(p))}


def interested(row: Row, system: str) -> bool:
    """The row declares an interest in `system` or maintains it (a word match, any case)."""
    word = re.compile(rf"(?<![\w-]){re.escape(system)}(?![\w-])", re.IGNORECASE)
    return bool(word.search(row.interests) or word.search(row.systems))


def check(paths: Iterable[str], approved: Sequence[str], rows: Sequence[Row]) -> list[Finding]:
    maintainers = {r.handle.lower(): r for r in rows if r.role.strip().lower() == "maintainer"}
    approving = [maintainers[h.lower()] for h in approved if h.lower() in maintainers]
    found = []
    for system in sorted(touched_systems(paths)):
        conflicted = [r.handle for r in approving if interested(r, system)]
        if conflicted and len(conflicted) == len(approving):
            found.append(Finding(
                "G2", PATH, "GOV-5",
                f"INV-GOV-4: changes to {system} are approved only by {', '.join(conflicted)}, "
                f"who declared an interest in it",
                ErrorKind.POLICY,
                hint="another maintainer without an interest in the system approves and merges",
            ))  # fmt: skip
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m iproofs.validate.merge_guard")
    parser.add_argument("--base", required=True, help="the target branch ref, e.g. origin/main")
    parser.add_argument("--approved", default="", help="comma-separated approving handles")
    args = parser.parse_args(argv)
    root = repo_root(Path.cwd())
    diff = subprocess.run(["git", "-C", str(root), "diff", "--name-only", f"{args.base}...HEAD"],
                          capture_output=True, text=True, check=True).stdout.split()  # fmt: skip
    approved = [h.strip() for h in args.approved.split(",") if h.strip()]
    found = check(diff, approved, parse((root / PATH).read_text("utf-8")))
    for f in found:
        print(f.line(), file=sys.stderr)
    systems = sorted(touched_systems(diff))
    print(f"merge guard: systems touched {systems or 'none'}; approvals {approved or 'none'}; "
          f"{len(found)} failure(s)")  # fmt: skip
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
