"""Typed readers of every file the site reads (RFC-0018 §Site).

The level file, the board file of the newest Level 1 release (or one given for a preview), the
claim cards, `web/_data/facts.json` and the Learn pages' words (`web/learn/`). No git call and
no clock: the same files give the same view in a full clone, a depth-1 clone or a tree with no
`.git` (CLI-4). Each file is read once per build.
"""

import re
from pathlib import Path
from typing import Any

from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import SiteFacts, load
from iproofs.provenance import file_digest
from iproofs.schema import SchemaRegistry, parse_tree
from iproofs.serialize import load_yaml

REPOSITORY = "https://github.com/ai-verification-observatory/inference-proofs"
FACTS = "web/_data/facts.json"
LEVEL = "levels/L1.yaml"
BOARD = "board.json"
LEARN = "web/learn"  # the Learn pages' words: index.yaml and one Markdown file per page
SLUG = re.compile(r"^[a-z][a-z0-9-]{1,31}$")  # a Learn page's address, as a system's name is
# RFC-0018 SI-4: the one fixed reason a system not run is listed with
REASONS = ("licence", "no public verifier", "no configuration at the request",
           "another kind of check", "not yet run")  # fmt: skip
RELEASE = re.compile(r"^v1\.(0|[1-9]\d*)$")  # Level 1 releases (RFC-0018 §Terms)


def config(message: str) -> IProofsError:
    return IProofsError(ErrorKind.CONFIG, f"site: {message}")


def load_facts(root: Path, registry: SchemaRegistry) -> SiteFacts:
    facts = load(root / FACTS, registry)
    assert isinstance(facts, SiteFacts)
    return facts


def read_yaml(path: Path) -> dict[str, Any]:
    return dict(load_yaml(path))


def level(root: Path) -> tuple[dict[str, Any], str]:
    """The level file and its digest (`levels/L1.yaml`, schema `level/1`)."""
    path = root / LEVEL
    if not path.is_file():
        raise config(f"no level file at {LEVEL}")
    return read_yaml(path), file_digest(path)


def newest_board(root: Path) -> Path | None:
    """`releases/<newest Level 1 release>/board.json`, or None while no Level 1 release has one."""
    found = []
    for path in root.glob(f"releases/*/{BOARD}"):
        m = RELEASE.match(path.parent.name)
        if m:
            found.append((int(m[1]), path))
    return max(found)[1] if found else None


def board(path: Path, registry: SchemaRegistry) -> dict[str, Any]:
    """A board file (`board/1`), validated against its schema."""
    if not path.is_file():
        raise config(f"no board file at {path}")
    tree = parse_tree(path)
    if tree.get("schema") != "board/1":
        raise config(f"{path}: schema {tree.get('schema')!r}, the site reads 'board/1'")
    if errors := registry.errors("board/1", tree):
        raise config("\n".join(f"{path}: {e}" for e in errors))
    return dict(tree)


def _learn_page(root: Path, entry: dict[str, Any], seen: set[str]) -> dict[str, Any]:
    slug = str(entry["slug"])
    if not SLUG.match(slug) or slug in seen:
        raise config(f"{LEARN}/index.yaml: slug {slug!r} is malformed or listed twice")
    seen.add(slug)
    path = root / LEARN / f"{slug}.md"
    if not path.is_file():
        raise config(f"no page text at {LEARN}/{slug}.md")
    return {
        "slug": slug,
        "title": str(entry["title"]),
        "summary": str(entry["summary"]),
        "path": f"{LEARN}/{slug}.md",
        "text": path.read_text(encoding="utf-8"),
    }


def learn(root: Path) -> dict[str, Any] | None:
    """The Learn pages' words: `web/learn/index.yaml` (the hub's words, the tracks and their
    pages in reading order, the glossary) with each listed page's Markdown text beside it, or
    None in a tree that holds none. Words only: the renderer draws them, and every figure a page
    prints still comes from the board file."""
    index = root / LEARN / "index.yaml"
    if not index.is_file():
        return None
    doc = read_yaml(index)
    seen: set[str] = set()
    try:
        return {
            "path": LEARN,
            "title": str(doc["title"]),
            "lead": str(doc["lead"]),
            "tracks": [
                {
                    "id": str(t["id"]),
                    "name": str(t["name"]),
                    "reader": str(t["reader"]),
                    "pages": [_learn_page(root, p, seen) for p in t["pages"]],
                }
                for t in doc["tracks"]
            ],
            "glossary": _learn_page(root, doc["glossary"], seen),
        }
    except (KeyError, TypeError) as e:
        raise config(f"{LEARN}/index.yaml: a field is missing or of the wrong type ({e})") from e


def engine(root: Path) -> dict[str, Any] | None:
    """The serving engine the baseline runs, as the serving reference pins it."""
    path = root / "systems" / "ref-serve" / "system.yaml"
    found = read_yaml(path).get("engine") if path.is_file() else None
    return dict(found) if isinstance(found, dict) else None
