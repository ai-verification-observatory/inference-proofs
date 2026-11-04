"""INV-GOV-6, the licence boundary (RFC-0001 §Governance files).

Code is Apache-2.0 (`LICENSE`); documents and data are CC BY 4.0 (`LICENSES/CC-BY-4.0.txt`).
A file that fits neither list is code. Under `systems/<name>/`, a file must be either a
document listed below or a known part of an adapter, so a new kind of file gets a decision
in review instead of a silent default (`LIC-1`).

`python -m iproofs.validate.licence [--format json]` prints the mapping of every tracked file.
"""

import fnmatch
import json
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from iproofs.errors import ErrorKind
from iproofs.validate import Finding

DATA = (  # CC BY 4.0
    "docs/*", "rfcs/*", "workloads/*", "reference/*", "results/*", "releases/*", "targets/*",
    "reports/*", "systems/*/claim.yaml", "systems/*/claims/*", "systems/*/external.yaml",
    "systems/*/replies/*",
)  # fmt: skip
CODE = ("harness/*", "systems/*", "site/*", "schema/*", ".github/*")  # Apache-2.0
# what an adapter directory holds besides its documents (RFC-0005 §Layout, RFC-0014 B2)
ADAPTER_CODE = (
    "Dockerfile", "Dockerfile.*", "entrypoint", "entrypoint*", "system.yaml", "controls.yaml",
    "README.md", "inputs.lock", "*requirements.txt", "policy-allow.txt", "tests/*", "model/*",
    "*.py",
)  # fmt: skip


def licence(path: str) -> str:
    """'data' (CC BY 4.0) or 'code' (Apache-2.0); a file in neither list is code."""
    return "data" if any(fnmatch.fnmatch(path, g) for g in DATA) else "code"


def check(files: Iterable[str]) -> list[Finding]:
    """LIC-1: every file under systems/<name>/ is a listed document or a known adapter part."""
    found = []
    for path in files:
        parts = path.split("/", 2)
        if parts[0] != "systems" or len(parts) < 3 or licence(path) == "data":
            continue
        if not any(fnmatch.fnmatch(parts[2], g) for g in ADAPTER_CODE):
            found.append(
                Finding(
                    "G1",
                    path,
                    "LIC-1",
                    "neither an adapter part nor a claim card, external figures or a reply",
                    ErrorKind.POLICY,
                    hint="decide its licence in review and add it to iproofs.validate.licence",
                )
            )
    return found


def main(argv: list[str] | None = None) -> int:
    from iproofs.validate import repo_root  # noqa: PLC0415
    from iproofs.validate.tree import tracked_files  # noqa: PLC0415

    args = sys.argv[1:] if argv is None else argv
    files = tracked_files(repo_root(Path.cwd()))
    mapping = {f: licence(f) for f in files}
    if args == ["--format", "json"]:
        print(json.dumps(mapping, indent=2, sort_keys=True))
    else:
        for kind, n in sorted(Counter(mapping.values()).items()):
            print(f"{kind}: {n} files")
    problems = check(files)
    for f in problems:
        print(f.line(), file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
