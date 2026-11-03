"""`iproofs validate`: the tree gates G2, G3, G4 and G5 of RFC-0013."""

import fnmatch
import json
import re
import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path

from iproofs.errors import ErrorKind, IProofsError
from iproofs.schema import SchemaRegistry, check_examples, load_document, parse_tree
from iproofs.serialize import check_format
from iproofs.validate import Finding, check_claim, check_controls_summary, check_derived

# RFC-0013 §G2 inputs: documents that name a schema
G2_GLOBS = (
    "systems/*/claim.yaml",
    "systems/*/claims/*.yaml",
    "systems/*/system.yaml",
    "systems/*/external.yaml",
    "systems/*/controls.yaml",
    "workloads/**/*.yaml",
    "reference/*.yaml",
    "targets/**/*.yaml",
    "releases/*/release.yaml",
    "releases/*/index.json",
    "results/**/run.json",
    "results/**/manifest.json",
    "results/**/controls.json",
    "results/**/reviews/*.json",
    "results/**/reproductions/*.json",
)
# Known-bad gate fixtures: checked by their own tests, never by the tree scan.
EXCLUDED = ("harness/tests/fixtures/gates/",)
MAX_FILE_BYTES = 5 * 1024 * 1024  # SIZE-1 (a limit, not a measurement)
MAX_RUN_BYTES = 10 * 1024 * 1024
STRUCTURAL = Path(__file__).with_name("structural_paths.txt")


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _git(root: Path, *args: str) -> list[str]:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        raise IProofsError(ErrorKind.ENVIRONMENT, f"git {' '.join(args)} failed in {root}") from e
    return [line for line in out.splitlines() if line]


def tracked_files(root: Path) -> list[str]:
    """Committed and staged files, excluding the known-bad gate fixtures."""
    files = _git(root, "ls-files", "--cached", "--others", "--exclude-standard")
    return sorted(f for f in files if not f.startswith(EXCLUDED) and (root / f).is_file())


def documents(root: Path, files: Iterable[str]) -> list[str]:
    return sorted(
        f
        for f in files
        if any(fnmatch.fnmatch(f, g) or fnmatch.fnmatch(f, g.replace("**/", "")) for g in G2_GLOBS)
    )


# ---------------------------------------------------------------- G2


def g2_schema(root: Path, files: list[str], registry: SchemaRegistry) -> list[Finding]:
    found = []
    for rel in documents(root, files):
        path = root / rel
        if (rel.startswith("systems/") and rel.endswith(("claim.yaml",))) or "/claims/" in rel:
            found += check_claim(path, root, registry)
            continue
        try:
            load_document(path, registry)
        except IProofsError as e:
            for line in e.message.splitlines():
                message = line.split(": ", 1)[1] if ": " in line else line
                found.append(Finding("G2", rel, "SCHEMA", message, ErrorKind.CONFIG))
    for problem in check_examples(root / "schema", registry):
        found.append(Finding("G2", "schema", "EXAMPLE", problem.splitlines()[0], ErrorKind.CONFIG))
    return found


def g2_xref(root: Path, files: list[str]) -> list[Finding]:
    """XREF-1, XREF-3, XREF-4, XREF-5 (XREF-2 has no run.json image field to compare yet)."""
    found = []
    for rel in documents(root, files):
        doc = parse_tree(root / rel)
        schema = doc.get("schema")
        if schema == "run/1":
            wl = doc["workload"]
            assert isinstance(wl, Mapping)
            if not (root / "workloads" / f"{wl['id']}.yaml").is_file():
                found.append(
                    Finding(
                        "G2",
                        rel,
                        "XREF-1",
                        f"unknown workload {wl['id']}",
                        ErrorKind.CONFIG,
                        "/workload/id",
                    )
                )
            if not (root / "systems" / str(doc["system"]) / "system.yaml").is_file():
                found.append(
                    Finding(
                        "G2",
                        rel,
                        "XREF-1",
                        f"unknown system {doc['system']}",
                        ErrorKind.CONFIG,
                        "/system",
                    )
                )
            if not _profile_known(root, str(doc["release"]), str(doc["profile"])):
                found.append(
                    Finding(
                        "G2",
                        rel,
                        "XREF-1",
                        f"unknown profile {doc['profile']}",
                        ErrorKind.CONFIG,
                        "/profile",
                    )
                )
        elif "/reviews/" in rel or "/reproductions/" in rel:
            run_dir = (root / rel).parent.parent
            if not (run_dir / "run.json").is_file():
                found.append(
                    Finding(
                        "G2", rel, "XREF-3", "names no existing run directory", ErrorKind.CONFIG
                    )
                )
        elif schema == "release/1":
            runs = doc.get("runs")
            for i, run in enumerate(runs if isinstance(runs, list) else []):
                if not (root / str(run) / "run.json").is_file():
                    found.append(
                        Finding(
                            "G2",
                            rel,
                            "XREF-4",
                            f"run {run} does not exist",
                            ErrorKind.CONFIG,
                            f"/runs/{i}",
                        )
                    )
            if not (root / str(doc.get("reference_file"))).is_file():
                found.append(
                    Finding(
                        "G2",
                        rel,
                        "XREF-4",
                        "reference file does not exist",
                        ErrorKind.CONFIG,
                        "/reference_file",
                    )
                )
    return found


def _profile_known(root: Path, release: str, profile: str) -> bool:
    for name in (release, "ci"):
        path = root / "reference" / f"{name}.yaml"
        if path.is_file():
            profiles = parse_tree(path).get("profiles")
            if isinstance(profiles, Mapping) and profile in profiles:
                return True
    return False


def g2_append_only(root: Path, base_ref: str) -> list[Finding]:
    """APP-1: under results/, only additions of reviews and reproductions touch existing runs."""
    found = []
    for line in _git(root, "diff", "--name-status", f"{base_ref}...HEAD", "--", "results/"):
        status, *paths = line.split("\t")
        path = paths[-1]
        added_record = status == "A" and re.search(r"/(reviews|reproductions)/[^/]+$", path)
        if status == "A" and not added_record:
            run_dir = "/".join(path.split("/")[:4])
            if _git(root, "ls-tree", "--name-only", base_ref, f"{run_dir}/run.json"):
                found.append(
                    Finding("G2", path, "APP-1", "adds a file to an existing run", ErrorKind.POLICY)
                )
        elif status != "A":
            found.append(
                Finding(
                    "G2",
                    path,
                    "APP-1",
                    f"results are append-only ({status})",
                    ErrorKind.POLICY,
                    hint="write a correction run that names it",
                )
            )
    return found


def g2_size(root: Path, files: list[str]) -> list[Finding]:
    """SIZE-1: 5 MiB per file outside run logs, 10 MiB per run directory (limits)."""
    found = []
    runs: dict[str, int] = {}
    for rel in files:
        size = (root / rel).stat().st_size
        if re.match(r"results/[^/]+/[^/]+/[^/]+/", rel):
            run = "/".join(rel.split("/")[:4])
            runs[run] = runs.get(run, 0) + size
        if size > MAX_FILE_BYTES and not re.match(r"results/[^/]+/[^/]+/[^/]+/logs/", rel):
            found.append(
                Finding(
                    "G2", rel, "SIZE-1", f"{size} bytes exceeds {MAX_FILE_BYTES}", ErrorKind.POLICY
                )
            )
    for run, size in sorted(runs.items()):
        if size > MAX_RUN_BYTES:
            found.append(
                Finding(
                    "G2",
                    run,
                    "SIZE-1",
                    f"run directory holds {size} bytes, limit {MAX_RUN_BYTES}",
                    ErrorKind.POLICY,
                )
            )
    return found


# ---------------------------------------------------------------- G3, G4


def g3_format(root: Path, files: list[str]) -> list[Finding]:
    return [
        Finding(
            "G3",
            rel,
            "FMT-1",
            "not in canonical JSON form",
            ErrorKind.CONFIG,
            hint=f"run iproofs fmt {rel}",
        )
        for rel in files
        if rel.endswith(".json") and not rel.startswith("schema/") and not check_format(root / rel)
    ]


def g4_derived(root: Path, files: list[str]) -> list[Finding]:
    found = []
    for rel in files:
        if rel.startswith("results/") and rel.endswith("/run.json"):
            found += check_derived(root / rel, root)
        elif rel.startswith("results/") and rel.endswith("/controls.json"):
            found += check_controls_summary(root / rel, root)
    return found


# ---------------------------------------------------------------- G5


def _allowlist() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for line in STRUCTURAL.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            name, pattern = line.split()
            out.setdefault(name, []).append(pattern)
    return out


def _is_quantity(node: object) -> bool:
    return isinstance(node, Mapping) and {"value", "unit", "grade", "tier"} <= set(node)


def _bare_numbers(node: object, pointer: str = "") -> Iterable[str]:
    if _is_quantity(node):
        return
    if isinstance(node, Mapping):
        for k, v in node.items():
            yield from _bare_numbers(v, f"{pointer}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _bare_numbers(v, f"{pointer}/{i}")
    elif isinstance(node, int | float) and not isinstance(node, bool):
        yield pointer


def _matches(pointer: str, pattern: str) -> bool:
    """`*` matches exactly one segment; a trailing `*` also matches any deeper path."""
    a, b = pointer.split("/"), pattern.split("/")
    if b[-1] == "*" and len(a) >= len(b):
        a = a[: len(b)]
    return len(a) == len(b) and all(y in ("*", x) for x, y in zip(a, b, strict=True))


def g5_labels(root: Path, files: list[str]) -> list[Finding]:
    """LBL-1, LBL-3 and LBL-4; LBL-2 and LBL-5 are enforced by G4's full recompute."""
    allow = _allowlist()
    found = []
    for rel in files:
        name = rel.rsplit("/", 1)[-1]
        if not rel.startswith(("results/", "releases/")) or name not in allow:
            continue
        doc = json.loads((root / rel).read_text())
        for pointer in _bare_numbers(doc):
            if not any(_matches(pointer, p) for p in allow[name]):
                found.append(
                    Finding(
                        "G5",
                        rel,
                        "LBL-4",
                        "a number outside a quantity is not on the structural allowlist",
                        ErrorKind.CONFIG,
                        pointer,
                        "make it a quantity",
                    )
                )
        metrics = doc.get("metrics", {}) if name == "run.json" else {}
        for key, q in metrics.items():
            if name == "run.json" and q.get("tier") != "reported":
                found.append(
                    Finding(
                        "G5",
                        rel,
                        "LBL-3",
                        "tier must be reported in run.json",
                        ErrorKind.CONFIG,
                        f"/metrics/{key}/tier",
                    )
                )
            if q.get("unit") == "ratio" and q.get("grade") == "derived":
                found += _ratio_scope(root, rel, key, q)
    return found


def _ratio_scope(root: Path, rel: str, key: str, q: Mapping[str, object]) -> list[Finding]:
    """LBL-1: a ratio derived from a rate carries the denominator rate's scope."""
    from iproofs.validate import resolve  # noqa: PLC0415

    source = q["source"]
    inputs = source.get("inputs", []) if isinstance(source, Mapping) else []
    denominator = resolve(root, str(inputs[-1])) if inputs else None
    wrong = (
        isinstance(denominator, Mapping)
        and denominator.get("unit") == "token/s"
        and q.get("scope") != denominator.get("scope")
    )
    if wrong:
        assert isinstance(denominator, Mapping)
        return [
            Finding(
                "G5",
                rel,
                "LBL-1",
                f"scope must be {denominator.get('scope')}",
                ErrorKind.CONFIG,
                f"/metrics/{key}/scope",
            )
        ]
    return []


# ---------------------------------------------------------------- driver


def validate_tree(
    root: Path, *, only: Iterable[str] | None = None, base_ref: str | None = None
) -> list[Finding]:
    """Every tree gate; `only` limits the per-file gates to those repository paths."""
    registry = SchemaRegistry.from_tree(root / "schema")
    files = tracked_files(root)
    if only is not None:
        wanted = [o.rstrip("/") for o in only]
        files = [f for f in files if any(f == w or f.startswith(w + "/") for w in wanted)]
    found = g2_schema(root, files, registry) + g2_xref(root, files) + g2_size(root, files)
    if base_ref:
        found += g2_append_only(root, base_ref)
    found += g3_format(root, files) + g4_derived(root, files) + g5_labels(root, files)
    found += g6_policy(root, files)
    return sorted(found, key=lambda f: (f.gate, f.path.encode(), f.pointer))


# ---------------------------------------------------------------- G6


def forbidden_match(token: str, pattern: str) -> bool:
    """A glob (RFC-0013); an entry without a wildcard is a prefix (RFC-0005)."""
    glob = pattern if any(c in pattern for c in "*?[") else pattern + "*"
    return fnmatch.fnmatchcase(token, glob)


def _forbidden(root: Path, system: str) -> list[str]:
    path = root / "systems" / system / "system.yaml"
    flags = parse_tree(path).get("forbidden_flags") if path.is_file() else None
    return [str(f) for f in flags] if isinstance(flags, list) else []


def g6_policy(root: Path, files: list[str]) -> list[Finding]:
    """POL-1 to POL-4: no measured run used a weakening configuration (RFC-0013 §G6)."""
    found = []
    for rel in files:
        if rel.startswith("results/") and rel.endswith("/manifest.json"):
            found += _manifest_policy(root, rel)
        elif rel.startswith("results/") and rel.endswith("/run.json"):
            doc = json.loads((root / rel).read_text())
            extra = sorted(set(doc.get("metrics", {})) - {"verdicts_accept_count"})
            if doc.get("control") is True and extra:
                found.append(
                    Finding(
                        "G6",
                        rel,
                        "POL-2",
                        f"a control job records measured quantities {extra}",
                        ErrorKind.POLICY,
                        "/metrics",
                    )
                )
        elif re.fullmatch(r"systems/[^/]+/entrypoint[^/]*", rel):
            found += _entrypoint_policy(root, rel)
    return found


def _manifest_policy(root: Path, rel: str) -> list[Finding]:
    doc = json.loads((root / rel).read_text())
    found = []
    if doc.get("harness", {}).get("nonconforming") is True:
        found.append(
            Finding(
                "G6",
                rel,
                "POL-4",
                "produced with --allow-nonconforming",
                ErrorKind.POLICY,
                "/harness/nonconforming",
            )
        )
    if doc.get("control") is False:
        system = str(doc.get("system", {}).get("name", ""))
        patterns = _forbidden(root, system)
        for i, command in enumerate(doc.get("commands", [])):
            for token in command.get("argv", []):
                if any(forbidden_match(str(token), p) for p in patterns):
                    found.append(
                        Finding(
                            "G6",
                            rel,
                            "POL-1",
                            f"measured run used forbidden flag {token!r}",
                            ErrorKind.POLICY,
                            f"/commands/{i}/argv",
                        )
                    )
    return found


def _entrypoint_policy(root: Path, rel: str) -> list[Finding]:
    """POL-3: a forbidden flag literal in adapter source must be listed with its guard."""
    system = rel.split("/")[1]
    literals = [p.rstrip("*") for p in _forbidden(root, system)]
    allow_file = root / "systems" / system / "policy-allow.txt"
    allowed = set()
    if allow_file.is_file():
        for line in allow_file.read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                file, _, content = line.partition("\t")
                allowed.add((file, content.strip()))
    found = []
    name = rel.rsplit("/", 1)[-1]
    for n, line in enumerate((root / rel).read_text(errors="replace").splitlines(), start=1):
        if any(lit and lit in line for lit in literals) and (name, line.strip()) not in allowed:
            found.append(
                Finding(
                    "G6",
                    f"{rel}:{n}",
                    "POL-3",
                    "forbidden flag literal outside policy-allow.txt",
                    ErrorKind.POLICY,
                    hint="list the line and its control guard",
                )
            )
    return found
