"""RFC-0015 §Precision matching for reference systems (rule ids PM-1 and PM-2, gate G2).

PM-1: a reference that does not use the workload's `precision.served` declares a
`precision_substitution` with a reason and the engine documentation. PM-2: a substitution
never goes to a lower bit width than the workload (it would flatter the reference), and every
quantity of a substituted row carries `quality.precision_substituted: true`. PM-4: the same bit
widths in another number format (FP8 for an integer W8A8) is a substitution too.
"""

import json
import re
from collections.abc import Iterable
from pathlib import Path

from iproofs.errors import ErrorKind
from iproofs.model import ReferenceWorkload, System, Workload, load
from iproofs.schema import SchemaRegistry
from iproofs.validate import Finding

NAMED = {"int8": (8, 8), "fp8": (8, 8), "int4": (4, 4), "bf16": (16, 16), "fp16": (16, 16),
         "fp32": (32, 32)}  # fmt: skip
FLOAT = {"fp8", "bf16", "fp16", "fp32"}  # every other known scheme, W<w>A<a> included, is integer


def bit_widths(scheme: str) -> tuple[int, int] | None:
    """(weight bits, activation bits) of `W<w>A<a>` or a common name; None if unknown."""
    if m := re.fullmatch(r"(?i)w(\d+)a(\d+)", scheme.strip()):
        return int(m.group(1)), int(m.group(2))
    return NAMED.get(scheme.strip().lower())


def substitution_problem(served: str, used: str) -> str | None:
    """PM-2: higher activation bits at the same weight width, or a higher weight width."""
    s, u = bit_widths(served), bit_widths(used)
    if s is None or u is None:
        return f"cannot order precisions {served!r} and {used!r}: unknown scheme"
    if u[0] < s[0] or (u[0] == s[0] and u[1] < s[1]):
        return f"{used} is a lower bit width than the workload's {served}"
    if u == s and (served.strip().lower() in FLOAT) == (used.strip().lower() in FLOAT):
        return f"{used} is the workload's precision; no substitution to declare"
    return None


def _finding(rel: str, rule: str, message: str, pointer: str = "") -> Finding:
    return Finding("G2", rel, rule, message, ErrorKind.CONFIG, pointer,
                   hint="RFC-0015 §Precision matching")  # fmt: skip


def substituted(root: Path, system: str, workload: str, registry: SchemaRegistry) -> bool:
    path = root / "systems" / system / "system.yaml"
    doc = load(path, registry) if path.is_file() else None
    if not isinstance(doc, System) or doc.kind != "reference":
        return False
    return any(
        isinstance(w, ReferenceWorkload) and w.id == workload and w.precision_substitution
        for w in doc.workloads
    )


def check(root: Path, files: Iterable[str], registry: SchemaRegistry) -> list[Finding]:
    files = list(files)
    return _systems(root, files, registry) + _runs(root, files, registry)


def _systems(root: Path, files: list[str], registry: SchemaRegistry) -> list[Finding]:
    found = []
    for rel in files:
        if not re.fullmatch(r"systems/[^/]+/system\.yaml", rel):
            continue
        doc = load(root / rel, registry)
        if not isinstance(doc, System) or doc.kind != "reference":
            continue
        for i, entry in enumerate(doc.workloads):
            assert isinstance(entry, ReferenceWorkload)  # the schema gives references objects
            wl_path = root / "workloads" / f"{entry.id}.yaml"
            if not wl_path.is_file():
                continue  # cross-references are G2 XREF's job
            wl = load(wl_path, registry)
            assert isinstance(wl, Workload)
            served = wl.precision.served
            pointer = f"/workloads/{i}"
            if entry.precision_used != served and entry.precision_substitution is None:
                found.append(_finding(rel, "PM-1", f"{entry.id}: uses {entry.precision_used}, the "
                                      f"workload serves {served}, and no substitution is declared",
                                      pointer))  # fmt: skip
            elif entry.precision_substitution is not None and (
                problem := substitution_problem(served, entry.precision_used)
            ):
                found.append(_finding(rel, "PM-2", f"{entry.id}: {problem}", pointer))
    return found


def _runs(root: Path, files: list[str], registry: SchemaRegistry) -> list[Finding]:
    found = []
    for rel in files:  # every quantity of a substituted row is flagged
        if not rel.startswith("results/") or not rel.endswith("/run.json"):
            continue
        run = json.loads((root / rel).read_text())
        workload = run.get("workload", {}).get("id")
        if run.get("system_kind") != "reference" or not substituted(
            root, str(run.get("system")), str(workload), registry
        ):
            continue
        for metric, q in sorted(run.get("metrics", {}).items()):
            if not (q.get("quality") or {}).get("precision_substituted"):
                found.append(_finding(rel, "PM-2", f"{metric} lacks quality.precision_substituted",
                                      f"/metrics/{metric}"))  # fmt: skip
    return found
