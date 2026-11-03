"""Gate G12, links and anchors (RFC-0013 §G12).

`LNK-1` relative Markdown links resolve to a file and, with `#anchor`, to a heading (GitHub
slug rules) or an explicit `<a id>`; `LNK-2` every `RFC-NNNN` names a file in `rfcs/`. Both
run offline inside `iproofs validate`. `python -m iproofs.validate.links --external` fetches
the external links instead; only the weekly scheduled job runs it.
"""

import fnmatch
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Iterable
from pathlib import Path

from iproofs.errors import ErrorKind
from iproofs.validate import Finding

SCOPE = ("README.md", "AGENTS.md", "docs/**", "rfcs/**", "reports/**", "systems/*/README.md")
FENCE = re.compile(r"^\s*(```|~~~)")
CODE_SPAN = re.compile(r"`[^`]*`")
LINK = re.compile(r"\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
HTML_ANCHOR = re.compile(r"<a\s+(?:id|name)=[\"']([^\"']+)[\"']")
RFC_REF = re.compile(r"\bRFC-(\d{4})\b")
EXTERNAL = ("http://", "https://", "mailto:")


def in_scope(rel: str) -> bool:
    return rel.endswith(".md") and any(fnmatch.fnmatch(rel, g) for g in SCOPE)


def prose_lines(text: str) -> list[tuple[int, str]]:
    """(line number, line) outside fenced code blocks, with inline code spans blanked."""
    out, fenced = [], False
    for n, line in enumerate(text.splitlines(), start=1):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            out.append((n, CODE_SPAN.sub(" ", line)))
    return out


def slug(heading: str) -> str:
    """GitHub's heading slug: rendered text, lowercase, punctuation other than - and _
    removed, spaces to -."""
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", heading)  # links render as their text
    text = re.sub(r"<[^>]+>", "", text).replace("`", "").lower()
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def anchors(text: str) -> set[str]:
    found: set[str] = set()
    seen: dict[str, int] = {}
    fenced = False
    for line in text.splitlines():
        if FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        found |= set(HTML_ANCHOR.findall(line))
        if m := HEADING.match(line):
            base = slug(m.group(2))
            n = seen.get(base, 0)
            seen[base] = n + 1
            found.add(base if n == 0 else f"{base}-{n}")
    return found


def check(root: Path, files: Iterable[str], named: Iterable[str] = ()) -> list[Finding]:
    if not (root / "rfcs").is_dir():
        return []  # not the specification corpus (a partial tree in a test), nothing to resolve
    rfcs = {p.name[:4] for p in (root / "rfcs").glob("[0-9][0-9][0-9][0-9]-*.md")}
    cache: dict[Path, set[str]] = {}
    found = []
    for rel in sorted(
        {*(f for f in files if in_scope(f)), *(f for f in named if f.endswith(".md"))}
    ):
        path = root / rel
        for n, line in prose_lines(path.read_text("utf-8")):
            where = f"{rel}:{n}"
            for target in LINK.findall(line):
                if target.startswith(EXTERNAL):
                    continue
                file_part, _, anchor = target.partition("#")
                dest = (path.parent / file_part).resolve() if file_part else path
                if not dest.exists():
                    found.append(_lnk1(where, f"{target}: no such file"))
                    continue
                if anchor and dest.is_file() and dest.suffix == ".md":
                    if dest not in cache:
                        cache[dest] = anchors(dest.read_text("utf-8"))
                    if anchor not in cache[dest]:
                        found.append(_lnk1(where, f"{target}: no such anchor"))
            for number in RFC_REF.findall(line):
                if number not in rfcs:
                    found.append(
                        Finding("G12", where, "LNK-2", f"RFC-{number} does not exist",
                                ErrorKind.POLICY, hint="name an RFC in rfcs/")
                    )  # fmt: skip
    return found


def _lnk1(where: str, message: str) -> Finding:
    return Finding(
        "G12", where, "LNK-1", message, ErrorKind.POLICY, hint="fix the path or the heading"
    )


def external_links(root: Path, files: Iterable[str]) -> list[tuple[str, str]]:
    """(where, url) for every external http(s) link in scope, once per url."""
    seen: dict[str, str] = {}
    for rel in sorted(f for f in files if in_scope(f)):
        for n, line in prose_lines((root / rel).read_text("utf-8")):
            for target in LINK.findall(line):
                if target.startswith(("http://", "https://")):
                    seen.setdefault(target, f"{rel}:{n}")
    return [(where, url) for url, where in seen.items()]


def fetch_failures(links: Iterable[tuple[str, str]], timeout_s: float = 20.0) -> list[str]:
    failures = []
    for where, url in links:
        request = urllib.request.Request(url, headers={"User-Agent": "iproofs-link-check"})
        try:
            with urllib.request.urlopen(request, timeout=timeout_s):
                pass
        except urllib.error.HTTPError as e:
            if e.code >= 400 and e.code not in (403, 429):  # bot walls and rate limits pass
                failures.append(f"{where} {url}: HTTP {e.code}")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            failures.append(f"{where} {url}: {e}")
    return failures


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args != ["--external"]:
        print("usage: python -m iproofs.validate.links --external", file=sys.stderr)
        return 2
    from iproofs.validate import repo_root  # noqa: PLC0415
    from iproofs.validate.tree import tracked_files  # noqa: PLC0415

    root = repo_root(Path.cwd())
    failures = fetch_failures(external_links(root, tracked_files(root)))
    for line in failures:
        print(line)
    print(f"links: {len(failures)} external links failed", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
