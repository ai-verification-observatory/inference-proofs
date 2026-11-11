"""`iproofs validate`: the tree gates G2, G3, G4 and G5 of RFC-0013."""

import fnmatch
import json
import re
import subprocess
from collections.abc import Iterable, Mapping
from functools import partial
from pathlib import Path

from iproofs.errors import ErrorKind, IProofsError
from iproofs.log.patterns import IPV4_ALLOWED, PATTERNS, is_ipv6
from iproofs.schema import SchemaRegistry, check_examples, load_document, parse_tree
from iproofs.serialize import check_format
from iproofs.validate import (
    Finding,
    check_claim,
    check_controls_summary,
    check_derived,
    cost,
    precision,
)
from iproofs.validate.memo import Memo

# RFC-0013 §G2 inputs: documents that name a schema
G2_GLOBS = (
    "systems/*/claim.yaml",
    "systems/*/claims/*.yaml",
    "systems/*/system.yaml",
    "systems/*/external.yaml",
    "systems/*/controls.yaml",
    "systems/*/properties.yaml",
    "workloads/**/*.yaml",
    "reference/*.yaml",
    "levels/*.yaml",
    "levels/*.json",
    "releases/*/board.json",
    "results/**/fidelity.json",
    "results/**/fidelity/*/fidelity-run.json",
    "results/**/verify-trace/*.json",
    "targets/**/*.yaml",
    "releases/*/release.yaml",
    "releases/*/index.json",
    "results/**/run.json",
    "results/**/manifest.json",
    "results/**/controls.json",
    "results/**/_controls/*/perturbed.json",
    "web/_data/facts.json",
    "web/_data/criteria.json",
)
# Known-bad gate fixtures: checked by their own tests, never by the tree scan.
EXCLUDED = ("harness/tests/fixtures/gates/",)
MAX_FILE_BYTES = 5 * 1024 * 1024  # SIZE-1 (a limit, not a measurement)
MAX_RUN_BYTES = 10 * 1024 * 1024


def _git(root: Path, *args: str) -> list[str]:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        raise IProofsError(ErrorKind.ENVIRONMENT, f"git {' '.join(args)} failed in {root}") from e
    return [line for line in out.splitlines() if line]


def tracked_files(root: Path, *, fixtures: bool = False) -> list[str]:
    """Committed and staged files, excluding the known-bad gate fixtures unless asked."""
    files = _git(root, "ls-files", "--cached", "--others", "--exclude-standard")
    return sorted(
        f for f in files if (fixtures or not f.startswith(EXCLUDED)) and (root / f).is_file()
    )


def documents(root: Path, files: Iterable[str]) -> list[str]:
    return sorted(
        f
        for f in files
        if any(fnmatch.fnmatch(f, g) or fnmatch.fnmatch(f, g.replace("**/", "")) for g in G2_GLOBS)
    )


# ---------------------------------------------------------------- G2


def _schema_problems(path: Path, registry: SchemaRegistry) -> list[str]:
    """The SCHEMA messages of one document, without its path: a function of its bytes, its
    file type and the schema tree."""
    try:
        load_document(path, registry)
    except IProofsError as e:
        return [line.split(": ", 1)[1] if ": " in line else line for line in e.message.splitlines()]
    return []


def g2_schema(
    root: Path, files: list[str], registry: SchemaRegistry, memo: Memo | None = None
) -> list[Finding]:
    found = []
    for rel in documents(root, files):
        path = root / rel
        if (rel.startswith("systems/") and rel.endswith(("claim.yaml",))) or "/claims/" in rel:
            found += check_claim(path, root, registry)
            continue
        if memo is None:
            problems = _schema_problems(path, registry)
        else:
            problems = memo.check(
                f"G2{path.suffix}", path.read_bytes(), partial(_schema_problems, path, registry)
            )
        found += [Finding("G2", rel, "SCHEMA", m, ErrorKind.CONFIG) for m in problems]
    for problem in check_examples(root / "schema", registry):
        found.append(Finding("G2", "schema", "EXAMPLE", problem.splitlines()[0], ErrorKind.CONFIG))
    return found


def g2_xref(root: Path, files: list[str]) -> list[Finding]:
    """XREF-1 and XREF-4: runs name known workloads, systems and profiles; releases name
    existing runs and reference files."""
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
        elif schema == "release/1":
            found += _release_xref(root, rel, doc)
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
    """APP-1: results are append-only; no file is added to, changed in or removed from a run."""
    found = []
    for line in _git(root, "diff", "--name-status", f"{base_ref}...HEAD", "--", "results/"):
        status, *paths = line.split("\t")
        path = paths[-1]
        if status == "A":
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


def _release_xref(root: Path, rel: str, doc: Mapping[str, object]) -> list[Finding]:
    """XREF-4: the listed runs and the reference file exist."""
    found: list[Finding] = []
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


# schemas are authored
G3_SKIP = ("schema/",)


def _canonical(path: Path, memo: Memo | None) -> bool:
    if memo is None:
        return check_format(path)
    return memo.check("G3", path.read_bytes(), lambda: check_format(path))


def g3_format(root: Path, files: list[str], memo: Memo | None = None) -> list[Finding]:
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
        if rel.endswith(".json")
        and not rel.startswith(G3_SKIP)
        and not _canonical(root / rel, memo)
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


def g5_labels(root: Path, files: list[str]) -> list[Finding]:
    """LBL-1 and LBL-3; LBL-2 and LBL-5 are enforced by G4's full recompute."""
    found = []
    for rel in files:
        if not (rel.startswith("results/") and rel.endswith("/run.json")):
            continue
        doc = json.loads((root / rel).read_text())
        for key, q in doc.get("metrics", {}).items():
            if q.get("tier") != "reported":
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
    root: Path,
    *,
    only: Iterable[str] | None = None,
    base_ref: str | None = None,
    memo_path: Path | None = None,
) -> list[Finding]:
    """Every tree gate; `only` limits the per-file gates to those repository paths. With
    `memo_path`, the checks that read one file reuse their stored results for the same bytes
    (iproofs.validate.memo); without it, as in a release freeze, every check is computed."""
    registry = SchemaRegistry.from_tree(root / "schema")
    memo = Memo(memo_path, registry) if memo_path is not None else None
    wanted = [o.rstrip("/") for o in only] if only is not None else []
    # a gate fixture directory named on the command line is scanned (`validate .../gates/G7`)
    fixtures = [w for w in wanted if (w + "/").startswith(EXCLUDED)]
    files = tracked_files(root, fixtures=bool(fixtures))
    if only is not None:
        files = [f for f in files if any(f == w or f.startswith(w + "/") for w in wanted)]
    found = g2_schema(root, files, registry, memo) + g2_xref(root, files) + g2_size(root, files)
    if base_ref:
        found += g2_append_only(root, base_ref)
    found += g3_format(root, files, memo) + g4_derived(root, files) + g5_labels(root, files)
    found += g6_policy(root, files) + g7_pins(root, files)
    found += g9_secrets(root, files, only or (), memo)
    found += precision.check(root, files, registry) + cost.check(root, files)
    if memo is not None:
        memo.save(whole=only is None)
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
    """POL-1 to POL-3: no measured run used a weakening configuration (RFC-0013 §G6)."""
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
    found: list[Finding] = []
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


# ---------------------------------------------------------------- G7

_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_REF = re.compile(r"^\S+@sha256:[0-9a-f]{64}$")
_RANGE = re.compile(r"[<>^~*]|\bx\b|latest")


def g7_pins(root: Path, files: list[str]) -> list[Finding]:
    """PIN-1 to PIN-5 (RFC-0013 §G7); schema-level pins already fail in G2."""
    found = []
    for rel in files:
        name = rel.rsplit("/", 1)[-1]
        if name.startswith("Dockerfile") and rel.startswith("systems/"):
            found += _dockerfile_pins(root, rel)
        elif re.fullmatch(r"reference/[^/]+\.yaml", rel):
            found += _reference_pins(root, rel)
    return found


def _dockerfile_pins(root: Path, rel: str) -> list[Finding]:
    found = []
    stages: set[str] = set()
    for n, raw in enumerate((root / rel).read_text().splitlines(), start=1):
        line = raw.strip()
        where = f"{rel}:{n}"
        if m := re.match(r"(?i)^FROM\s+(\S+)(?:\s+AS\s+(\S+))?", line):
            image, stage = m.group(1), m.group(2)
            if image != "scratch" and image not in stages and not _DIGEST_REF.match(image):
                found.append(
                    Finding(
                        "G7",
                        where,
                        "PIN-2",
                        f"FROM {image} is not pinned by digest",
                        ErrorKind.INTEGRITY,
                        hint="use <repo>@sha256:<64 hex>",
                    )
                )
            if stage:
                stages.add(stage)
        m = re.match(r"^ARG\s+UPSTREAM_COMMIT=(\S+)", line)
        if m and not _HEX40.match(m.group(1)):
            found.append(
                Finding(
                    "G7",
                    where,
                    "PIN-1",
                    f"UPSTREAM_COMMIT {m.group(1)} is not a full 40-hex hash",
                    ErrorKind.INTEGRITY,
                )
            )
        if m := re.search(r"git\s+checkout\s+(\S+)", line):
            ref = m.group(1)
            if not ref.startswith("$") and not _HEX40.match(ref):
                found.append(
                    Finding(
                        "G7",
                        where,
                        "PIN-1",
                        f"git checkout {ref} is not a full 40-hex hash",
                        ErrorKind.INTEGRITY,
                    )
                )
        found += _toolchain_pins(line, where)
    return found


def _toolchain_pins(line: str, where: str) -> list[Finding]:
    """PIN-5: exact toolchain versions in pip and apt installs, never `latest`."""
    found = []
    if ":latest" in line:
        found.append(
            Finding("G7", where, "PIN-5", "`latest` is not a version", ErrorKind.INTEGRITY)
        )
    if m := re.search(r"pip3?\s+install\s+(.*)", line):
        for pkg in m.group(1).split():
            if not pkg.startswith("-") and "==" not in pkg and "@" not in pkg and pkg != "\\":
                found.append(
                    Finding(
                        "G7",
                        where,
                        "PIN-5",
                        f"pip package {pkg} has no ==version",
                        ErrorKind.INTEGRITY,
                    )
                )
    if m := re.search(r"apt-get\s+install\s+(.*)", line):
        for pkg in m.group(1).split():
            if not pkg.startswith("-") and "=" not in pkg and pkg not in {"&&", "\\"}:
                found.append(
                    Finding(
                        "G7",
                        where,
                        "PIN-5",
                        f"apt package {pkg} has no =version",
                        ErrorKind.INTEGRITY,
                    )
                )
    return found


def _reference_pins(root: Path, rel: str) -> list[Finding]:
    """PIN-4: driver, CUDA and container runtime versions are exact strings, never ranges."""
    found = []
    profiles = parse_tree(root / rel).get("profiles")
    for pid, profile in profiles.items() if isinstance(profiles, Mapping) else []:
        if not isinstance(profile, Mapping) or profile.get("kind") != "prover":
            continue
        runtime = profile.get("container_runtime", {})
        values = {
            "driver": profile.get("driver"),
            **(runtime if isinstance(runtime, Mapping) else {}),
        }
        for field, value in values.items():
            if isinstance(value, str) and _RANGE.search(value):
                found.append(
                    Finding(
                        "G7",
                        rel,
                        "PIN-4",
                        f"{field} {value!r} is a range, not an exact version",
                        ErrorKind.INTEGRITY,
                        f"/profiles/{pid}/{field}",
                    )
                )
    return found


# ---------------------------------------------------------------- G9

SECRET_ALLOWLIST = ("harness/tests/fixtures/secrets/",)  # RFC-0013 §G9, plus invalid examples
_VERSION_FIELD = re.compile(r"""(?i)["']?\w*version\w*["']?\s*[:=]""")


def scan_text(text: str, rel: str) -> list[Finding]:
    """SEC-1 to SEC-11 over one file, with the same compiled patterns the redactor uses."""
    return [_secret(rel, n, rule, kind) for n, rule, kind in _scan(text)]


def _secret(rel: str, line: int, rule: str, kind: str) -> Finding:
    return Finding(
        "G9",
        f"{rel}:{line}",
        rule,
        f"matches the {kind} pattern",
        ErrorKind.POLICY,
        hint="remove it; never commit secrets or host identifiers (AGENTS.md rule 7)",
    )


def _scan(text: str) -> list[tuple[int, str, str]]:
    """(line, rule, kind) of every hit: a function of the text alone."""
    found = []
    for n, line in enumerate(text.splitlines(), start=1):
        spans: list[tuple[int, int]] = []
        for p in PATTERNS:
            for m in p.regex.finditer(line):
                hit = m.group(0)
                if any(a <= m.start() and m.end() <= b for a, b in spans):
                    continue  # inside an earlier hit: a MAC address is not also an IPv6 one
                if p.rule == "SEC-5" and (
                    hit in IPV4_ALLOWED
                    or _VERSION_FIELD.search(line)
                    or line[: m.start()].endswith("==")  # a requirement pin, pkg==13.4.1.3
                ):
                    continue
                if p.rule == "SEC-6" and not is_ipv6(hit):
                    continue
                spans.append(m.span())
                found.append((n, p.rule, p.kind))
    return found


def _allowlisted(rel: str) -> bool:
    return rel.startswith(SECRET_ALLOWLIST) or bool(
        re.match(r"schema/[^/]+/examples/invalid/", rel)
    )


def g9_secrets(
    root: Path, files: list[str], only: Iterable[str] = (), memo: Memo | None = None
) -> list[Finding]:
    """Allowlisted files are skipped unless a requested path lies inside the allowlist."""
    named = tuple(w + "/" for w in (o.rstrip("/") for o in only) if _allowlisted(w + "/"))
    found = []
    for rel in files:
        if _allowlisted(rel) and not (rel.startswith(named) or rel + "/" in named):
            continue
        data = (root / rel).read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue  # binary files hold no text secrets this gate can see
        hits = _scan(text) if memo is None else memo.check("G9", data, partial(_scan, text))
        found += [_secret(rel, n, rule, kind) for n, rule, kind in hits]
    return found
