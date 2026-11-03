"""Gate G11, DCO sign-off (RFC-0013 §G11, RFC-0001 §Governance files).

`uv run python -m iproofs.validate.dco origin/main..HEAD` checks rule DCO-1 over a commit range
with `git log`, so CI and a laptop run the same check with no external service.
"""

import subprocess
import sys
from pathlib import Path

from iproofs.errors import ErrorKind, IProofsError
from iproofs.validate import Finding

FIELD, RECORD = "\x1f", "\x1e"
FORMAT = FIELD.join(("%H", "%an", "%ae", "%P", "%(trailers:key=Signed-off-by,valueonly)"))


def check_range(root: Path, rev_range: str) -> list[Finding]:
    """DCO-1: every non-merge commit carries `Signed-off-by: <author name> <<author email>>`.
    Merge commits are made by the hosting platform when a pull request lands."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "log", f"--format={FORMAT}{RECORD}", rev_range],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        raise IProofsError(ErrorKind.CONFIG, f"git log {rev_range} failed in {root}") from e
    found = []
    for record in out.split(RECORD):
        if not record.strip():
            continue
        sha, name, email, parents, trailers = record.strip("\n").split(FIELD)
        if len(parents.split()) > 1:
            continue
        signed = {_identity(t) for t in trailers.splitlines() if t.strip()}
        if (name, email.lower()) not in signed:
            found.append(
                Finding(
                    "G11",
                    sha[:12],
                    "DCO-1",
                    f"no Signed-off-by matching the author {name} <{email}>",
                    ErrorKind.POLICY,
                    hint="git commit --amend -s, or git rebase --signoff for several commits",
                )
            )
    return found


def _identity(trailer: str) -> tuple[str, str]:
    name, _, rest = trailer.strip().rpartition("<")
    return name.strip(), rest.rstrip(">").strip().lower()


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m iproofs.validate.dco <revision range>", file=sys.stderr)
        return 2
    try:
        found = check_range(Path.cwd(), args[0])
    except IProofsError as e:
        print(f"dco: {e.message}", file=sys.stderr)
        return 1
    for f in found:
        print(f.line())
    print(f"dco: {len(found)} failures", file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
