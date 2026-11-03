"""INV-ARCH-1 and INV-ARCH-6: module layers and lazy optional imports (docs/spec/01).

The layer table is read from docs/spec/01-architecture.md §Module boundaries itself, so the
document and the test cannot disagree.
"""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "docs/spec/01-architecture.md"
SRC = ROOT / "harness/src/iproofs"
OPTIONAL = ("pynvml", "huggingface_hub", "tokenizers")  # INV-ARCH-6


def layer_table(spec: str = SPEC.read_text()) -> dict[str, set[str]]:
    """Module -> the modules it may import, from the §Module boundaries table."""
    section = spec.split("## Module boundaries", 1)[1].split("\n## ", 1)[0]
    rows = re.findall(r"^\| (\d) \| `iproofs\.(\w+)` \| [^|]+ \| ([^|]+) \|$", section, re.M)
    layer = {name: int(n) for n, name, _ in rows}
    allowed = {}
    for _, name, rule in rows:
        may = {m for m in re.findall(r"`(?:iproofs\.)?(\w+)`", rule) if m in layer}
        if span := re.search(r"layers (\d+) to (\d+)", rule):
            low, high = int(span[1]), int(span[2])
            may |= {m for m, n in layer.items() if low <= n <= high}
        if "every module" in rule:
            may |= set(layer)
        allowed[name] = may - {name}
    return allowed


def module_of(path: Path, src: Path) -> str:
    return path.relative_to(src).parts[0].removesuffix(".py")


def imports(tree: ast.Module) -> list[tuple[str, int, bool]]:
    """(imported module, line, at module level) for every import in a file."""
    top = {id(n) for n in _module_level(tree.body)}
    found = []
    for node in ast.walk(tree):
        names: list[str] = []
        if not isinstance(node, ast.Import | ast.ImportFrom):
            continue
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif node.level == 0 and node.module:
            names = [node.module]
            if node.module == "iproofs":  # `from iproofs import cli`
                names = [f"iproofs.{a.name}" for a in node.names]
        found += [(n, node.lineno, id(node) in top) for n in names]
    return found


def _module_level(body: list[ast.stmt]) -> list[ast.stmt]:
    """Statements run at import time: the body, and the bodies of top-level if and try."""
    out: list[ast.stmt] = []
    for stmt in body:
        out.append(stmt)
        if isinstance(stmt, ast.If) and not _type_checking(stmt):
            out += _module_level(stmt.body) + _module_level(stmt.orelse)
        elif isinstance(stmt, ast.Try):
            out += _module_level(stmt.body)
            for handler in stmt.handlers:
                out += _module_level(handler.body)
    return out


def _type_checking(stmt: ast.If) -> bool:
    return isinstance(stmt.test, ast.Name) and stmt.test.id == "TYPE_CHECKING"


def layer_problems(src: Path, allowed: dict[str, set[str]]) -> list[str]:
    problems = []
    graph: dict[str, set[str]] = {}
    for path in sorted(src.rglob("*.py")):
        here = module_of(path, src)
        rel = path.relative_to(src.parent).as_posix()
        for name, line, top in imports(ast.parse(path.read_text())):
            if name.split(".")[0] in OPTIONAL and top:
                problems.append(f"{rel}:{line} imports {name} at module level (INV-ARCH-6)")
            parts = name.split(".")
            if parts[0] != "iproofs" or len(parts) < 2 or here == "__init__":
                continue
            there = parts[1]
            if there in (here, "__init__", "__version__"):
                continue
            graph.setdefault(here, set()).add(there)
            if here in allowed and there not in allowed[here]:
                problems.append(f"{rel}:{line} iproofs.{here} imports iproofs.{there} (INV-ARCH-1)")
    problems += [f"import cycle: {' -> '.join(c)} (INV-ARCH-1)" for c in _cycles(graph)]
    return problems


def _cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    found: list[list[str]] = []
    done: set[str] = set()

    def visit(node: str, path: list[str]) -> None:
        if node in path:
            cycle = [*path[path.index(node) :], node]
            if not any(set(cycle) == set(c) for c in found):
                found.append(cycle)
            return
        if node in done:
            return
        for nxt in sorted(graph.get(node, ())):
            visit(nxt, [*path, node])
        done.add(node)

    for node in sorted(graph):
        visit(node, [])
    return found


def test_import_layers() -> None:
    allowed = layer_table()
    modules = {module_of(p, SRC) for p in SRC.rglob("*.py")} - {"__init__"}
    assert modules <= set(allowed), f"modules missing from docs/spec/01: {modules - set(allowed)}"
    assert layer_problems(SRC, allowed) == []


def test_layer_table_reads_the_spec() -> None:
    allowed = layer_table()
    assert allowed["errors"] == set()
    assert allowed["model"] == {"errors", "serialize", "quantity", "schema"}
    assert "measure" in allowed["adapter"]
    assert "runner" not in allowed["validate"]  # layers 0 to 5 only
    assert "release" in allowed["site"]
    assert allowed["cli"] == set(allowed) - {"cli"}


def package(tmp_path: Path, files: dict[str, str]) -> Path:
    src = tmp_path / "iproofs"
    for rel, text in {"__init__.py": "", **files}.items():
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        (src / rel).write_text(text)
    return src


def test_upward_import_fails(tmp_path: Path) -> None:
    src = package(tmp_path, {"log/__init__.py": "from iproofs.validate import Finding\n"})
    assert layer_problems(src, layer_table()) == [
        "iproofs/log/__init__.py:1 iproofs.log imports iproofs.validate (INV-ARCH-1)"
    ]


def test_module_level_optional_import_fails(tmp_path: Path) -> None:
    src = package(
        tmp_path,
        {
            "measure.py": "import pynvml\n\n\ndef ok():\n    import tokenizers\n",
            "workloads.py": (
                "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import tokenizers\n"
            ),
        },
    )
    assert layer_problems(src, layer_table()) == [
        "iproofs/measure.py:1 imports pynvml at module level (INV-ARCH-6)"
    ]


def test_cycle_named(tmp_path: Path) -> None:
    src = package(
        tmp_path,
        {"adapter.py": "import iproofs.measure\n", "measure.py": "from iproofs import adapter\n"},
    )
    problems = layer_problems(src, layer_table())
    assert "iproofs/measure.py:1 iproofs.measure imports iproofs.adapter (INV-ARCH-1)" in problems
    assert "import cycle: adapter -> measure -> adapter (INV-ARCH-1)" in problems
