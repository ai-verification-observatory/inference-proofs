"""`iproofs results import SRC_RUN_DIR [--release R]`: a run a hosted job wrote, into results/.

A hosted job starts from an empty results root, so every session it writes is
`<date>-<system>-<workload>-<profile>-1` (INV-RUN-6 sees no earlier run). Importing a second or
third session of the same day under that id would overwrite the first. This command copies the
run directory into `results/<release>/<system>/` under the next free n, as the runner allocates
it, and:

- leaves out the proof bytes and scratch the job kept beside the records (`io/`, `verify/`,
  `commitment/`, `controls-io/`, `logprobs-io/`, `.archive/`), as the earlier imports did;
- writes the new id wherever the old one appears in the copied text files (run.json,
  manifest.json, verify-trace/, verifier/, logs/), so the records name the directory they are in;
- moves run.json's metric citations (`source.ref`, `source.inputs`) from the job's results root
  (`/tmp/iproofs/out/dev-results/`) to `results/`. Values are unchanged; gate G4 recomputes each
  derived one from them. Command lines and verify traces keep the job's paths.

digests.txt is copied as written: it names no run id, and its log digests are of the streams
before redaction, not of the files.
"""

import argparse
import json
import re
import shutil
from pathlib import Path

from iproofs.commands import Command
from iproofs.errors import ErrorKind, IProofsError

LEFT_OUT = ("io", "verify", "commitment", "controls-io", "logprobs-io", ".archive")
JOB_ROOT = "/tmp/iproofs/out/dev-results/"
TEXT = (".json", ".jsonl", ".txt", ".log", ".stderr", ".stdout")


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]", command: Command) -> None:
    parent = sub.add_parser("results", help="run directories in results/ (INV-RUN-6)")
    rsub = parent.add_subparsers(dest="results_command", required=True, metavar="ACTION")
    p = command(
        "import",
        "copy a hosted job's run into results/ under the next free run id",
        rsub,
        "results import",
    )
    p.add_argument("source", type=Path, help="the run directory the job wrote")
    p.add_argument("--release", default="v1.0")
    p.add_argument("--results", type=Path, help="default: the repository's results/")
    p.add_argument(
        "--add-to",
        type=Path,
        metavar="RUN_DIR",
        help="add the source's later records (controls, reverify/) to this imported run, the "
        "source's run id rewritten to its own, once each",
    )
    p.set_defaults(handler=results_import)


def next_run_id(parent: Path, run_id: str) -> str:
    """The id `run_id` takes under `parent`: its stem with the smallest unused n."""
    stem, sep, n = run_id.rpartition("-")
    if not sep or not n.isdigit():
        raise IProofsError(ErrorKind.CONFIG, f"run id {run_id!r} does not end in -<n>")
    k = 1
    while (parent / f"{stem}-{k}").exists() or (parent / f".staging-{stem}-{k}").exists():
        k += 1
    return f"{stem}-{k}"


def relocate(doc: dict[str, object]) -> int:
    """Move run.json's metric citations from the job's results root to results/."""
    moved = 0
    metrics = doc.get("metrics")
    entries: list[object] = (
        list(metrics.values()) if isinstance(metrics, dict)
        else list(metrics) if isinstance(metrics, list) else []
    )  # fmt: skip
    for m in entries:
        src = m.get("source") if isinstance(m, dict) else None
        if not isinstance(src, dict):
            continue
        ref = src.get("ref")
        if isinstance(ref, str) and ref.startswith(JOB_ROOT):
            src["ref"], moved = "results/" + ref[len(JOB_ROOT) :], moved + 1
        inputs = src.get("inputs")
        if isinstance(inputs, list):
            for i, x in enumerate(inputs):
                if isinstance(x, str) and x.startswith(JOB_ROOT):
                    inputs[i], moved = "results/" + x[len(JOB_ROOT) :], moved + 1
    return moved


def import_run(source: Path, results: Path, release: str) -> Path:
    """Copy `source` into results/<release>/<system>/ under the next free id; returns it."""
    run = json.loads((source / "run.json").read_text())
    old, system = str(run["run_id"]), str(run["system"])
    parent = results / release / system
    new = next_run_id(parent, old)
    target = parent / new
    shutil.copytree(source, target, ignore=lambda d, names: [n for n in names if
                    Path(d) == source and n in LEFT_OUT])  # fmt: skip
    same = re.compile(re.escape(old) + r"(?!\d)")
    for path in sorted(p for p in target.rglob("*") if p.is_file() and p.suffix in TEXT):
        text = path.read_text()
        if old in text:
            path.write_text(same.sub(new, text))
    from iproofs.serialize import write_json  # noqa: PLC0415

    run_path = target / "run.json"
    doc = json.loads(run_path.read_text())
    relocate(doc)
    write_json(run_path, doc)
    return target


ADDED_LATER = ("controls.json", "controls-seed.json", "controls-parts", "reverify")


def add_records(source: Path, target: Path) -> list[Path]:
    """The records a merged run may gain once (RFC-0008 controls, RFC-0018 CH-4a reverify/),
    copied from the job's copy of the run into the imported one, the job's run id rewritten to
    the imported id as `import_run` does. Refused when the target already has one of them."""
    old = str(json.loads((source / "run.json").read_text())["run_id"])
    new = str(json.loads((target / "run.json").read_text())["run_id"])
    same = re.compile(re.escape(old) + r"(?!\d)")
    added: list[Path] = []
    for name in ADDED_LATER:
        src = source / name
        if not src.exists():
            continue
        dst = target / name
        if dst.exists():
            raise IProofsError(ErrorKind.CONFIG, f"{dst} exists; it is added once")
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copyfile(src, dst)
        added.append(dst)
        for path in [dst] if dst.is_file() else sorted(dst.rglob("*")):
            if path.is_file() and path.suffix in TEXT and old in (text := path.read_text()):
                path.write_text(same.sub(new, text))
    return added


def results_import(args: argparse.Namespace) -> int:
    from iproofs.validate import repo_root  # noqa: PLC0415

    if not (args.source / "run.json").is_file():
        raise IProofsError(ErrorKind.CONFIG, f"no run.json in {args.source}")
    if args.add_to is not None:
        for path in add_records(args.source, args.add_to):
            print(path)
        return 0
    results = args.results or repo_root(Path.cwd()) / "results"
    print(import_run(args.source, results, args.release))
    return 0
