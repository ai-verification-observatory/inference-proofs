"""RFC-0015 §Precision matching for reference systems (rule ids PM-1 and PM-2, gate G2).

PM-1: a reference that does not use the workload's `precision.served` declares a
`precision_substitution` with a reason and the engine documentation. PM-2: a substitution
never goes to a lower bit width than the workload (it would flatter the reference), and every
quantity of a substituted row carries `quality.precision_substituted: true`. PM-4: the same bit
widths in another number format (FP8 for an integer W8A8) is a substitution too. The PM rules
govern `ref-recompute`; a production-serving system (`reference_role: serve`) serves the
publisher's release as it is (SRV-6), and its entries follow SRV-3 and SRV-6 instead (rule ids
SRV-3, SRV-6), as do the serving records under workloads/serving/ (SM-1 and the SRV-6 mapping).
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
    found = _systems(root, files, registry) + _runs(root, files, registry)
    if any(f.startswith(("workloads/", "systems/")) for f in files):
        found += _serving(root, registry)
    return found


SERVE_FLAGS = ("--tensor-parallel-size", "--max-model-len", "--max-num-seqs")


def serve_entry_problems(entry: ReferenceWorkload, wl: Workload) -> list[str]:
    """SRV-1, SRV-3 and SRV-6 on one production-serving entry: flag and value pairs of the
    allowlist, each once; `--tensor-parallel-size` is the entry's GPU count; `--max-model-len`
    is prompt plus output tokens; `--max-num-seqs` is the workload's batch size at matched load
    and absent at high load, where `batch_size` names the batch; a matched session runs at least
    the workload's batches."""
    args = list(entry.engine_args)
    flags = [a for i, a in enumerate(args) if i % 2 == 0]
    values = [a for i, a in enumerate(args) if i % 2 == 1]
    problems = []
    if len(args) % 2 or any(f not in SERVE_FLAGS for f in flags) or len(set(flags)) != len(flags):
        return [f"{entry.id}: engine_args {args} are not flag and value pairs of {SERVE_FLAGS}"]
    given = dict(zip(flags, values, strict=True))
    want = {"--tensor-parallel-size": str(entry.gpus),
            "--max-model-len": str(wl.shape.prompt_tokens + wl.shape.output_tokens)}  # fmt: skip
    if entry.load_point == "matched":
        want["--max-num-seqs"] = str(wl.shape.batch_size)
        if entry.batch_size is not None:
            problems.append(f"{entry.id}: a matched entry runs the workload's batch size")
        run = entry.batches_per_session_run
        if run is not None and run < wl.shape.batches_per_session:
            problems.append(f"{entry.id}: batches_per_session_run {run} is below the "
                            f"workload's {wl.shape.batches_per_session} (SRV-1: that count, or "
                            "more)")  # fmt: skip
    elif entry.batch_size is None:
        problems.append(f"{entry.id}: a high-load entry names its batch_size")
    elif entry.batches_per_session_run is not None:
        problems.append(f"{entry.id}: a high-load session is max(batches_per_session, 2)")
    if given != want:
        problems.append(f"{entry.id} ({entry.load_point}, {entry.gpus} GPUs): engine_args "
                        f"{given} differ from {want}")  # fmt: skip
    return problems


def _serving(root: Path, registry: SchemaRegistry) -> list[Finding]:  # noqa: PLR0912
    """SM-1 on every serving record and the SRV-6 mapping between records and workloads."""
    from iproofs.serving import SERVING_DIR, load_records, mapping_problems, sm1_problems  # noqa: PLC0415

    try:
        records = load_records(root, registry)
    except Exception as e:
        return [_finding(SERVING_DIR, "SRV-6", f"serving records do not load: {e}")]
    docs = []
    for path in sorted((root / "workloads").glob("*.yaml")):
        try:
            docs.append(load(path, registry))
        except Exception:  # G2 SCHEMA reports it
            continue
    workloads = {doc.id: doc for doc in docs if isinstance(doc, Workload)}
    serve = []
    for path in sorted((root / "systems").glob("*/system.yaml")):
        try:
            doc = load(path, registry)
        except Exception:
            continue
        if isinstance(doc, System) and doc.reference_role == "serve":
            serve.append(doc.name)
    found = []
    for rid, rec in sorted(records.items()):
        rel = f"{SERVING_DIR}/{rid}.yaml"
        found += [_finding(rel, "SM-1", line, "/model/files") for line in sm1_problems(rec)]
    for line in mapping_problems(records, workloads, serve):
        found.append(_finding(SERVING_DIR, "SRV-6", line))
    for name in serve:
        rel = f"systems/{name}/system.yaml"
        doc = load(root / rel, registry)
        assert isinstance(doc, System)
        seen = set()
        for i, entry in enumerate(doc.workloads):
            assert isinstance(entry, ReferenceWorkload)
            key = (entry.id, entry.load_point, entry.gpus)
            if key in seen:
                found.append(_finding(rel, "SRV-6", f"{key} is listed twice", f"/workloads/{i}"))
            seen.add(key)
            named = next((r for r in records.values() if entry.id in r.workloads), None)
            if named is not None and entry.precision_used != named.precision.name:
                found.append(_finding(rel, "SRV-6", f"{entry.id}: precision_used "
                                      f"{entry.precision_used} is not the serving record's "
                                      f"{named.precision.name}", f"/workloads/{i}"))  # fmt: skip
            if entry.id in workloads:
                found += [_finding(rel, "SRV-3", line, f"/workloads/{i}")
                          for line in serve_entry_problems(entry, workloads[entry.id])]  # fmt: skip
    return found


def _systems(root: Path, files: list[str], registry: SchemaRegistry) -> list[Finding]:
    found = []
    for rel in files:
        if not re.fullmatch(r"systems/[^/]+/system\.yaml", rel):
            continue
        doc = load(root / rel, registry)
        if not isinstance(doc, System) or doc.kind != "reference" or doc.reference_role == "serve":
            continue  # production serving substitutes nothing (SRV-6): see _serving
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
