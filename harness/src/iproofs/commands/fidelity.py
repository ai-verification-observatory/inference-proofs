"""`iproofs fidelity run|score` (RFC-0018 FI-8).

`run` drives the `ref-fidelity` image itself through the container runners of
`iproofs.adapter` (docker, or hosted: this process runs inside the image the provider started):
one `info` call, then one `prove` call per model source (the reference with the controls built
from it, the smaller model, each row's committed GGUF). It needs no runner job kind: nothing it
does is timed or counted. It stores the replies, KL logs and its record under
`results/<release>/fidelity/<rung>/`.

`score` runs on a CPU from those records and the rows' counted sessions and writes
`fidelity.json` (`iproofs.fidelity`).
"""

import argparse
import json
import os
import shutil
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from iproofs.commands import Command
from iproofs.errors import ErrorKind, IProofsError

if TYPE_CHECKING:
    from iproofs.adapter import ContainerRunner
    from iproofs.level import Level, Rung
    from iproofs.schema import SchemaRegistry

SYSTEM = "ref-fidelity"
SYSTEMS = {"llama.cpp": "ref-fidelity", "vllm": "ref-fidelity-vllm"}  # RFC-0018 FI-9
ENGINE_REPOS = {"vllm": "vllm-project/vllm"}
RUN_RECORD = "fidelity-run.json"
PART = "controls"  # FI-9: the quantized controls, run apart from a vLLM reference
ROW_PREFIX = "row-"  # the id of a row's committed file in the image's status


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]", command: Command) -> None:
    """Add this module's subcommands to the top-level parser."""
    from iproofs.cli import gpu_list  # noqa: PLC0415 (iproofs.cli is loaded: it calls this)

    parent = sub.add_parser("fidelity", help="the fidelity gate of a rung (RFC-0018 FI-1 to FI-8)")
    fsub = parent.add_subparsers(dest="fidelity_command", required=True, metavar="ACTION")
    p = command(
        "run",
        "the reference's and the controls' greedy replies and KL, in the ref-fidelity image",
        fsub,
        "fidelity run",
    )
    p.add_argument("--level", default="L1", help="level id (default: L1)")
    p.add_argument("--rung", required=True)
    p.add_argument("--release", required=True)
    p.add_argument(
        "--prompts-dir",
        type=Path,
        required=True,
        help="the directory `iproofs level prompts RUNG --out DIR` wrote (prompts.jsonl, "
        "kl-texts.jsonl)",
    )
    p.add_argument(
        "--reference-dir",
        type=Path,
        help="the rung's 16-bit release, for a rung whose reference is not its serving record",
    )
    p.add_argument("--other-model-dir", type=Path, help="the other_model control's 16-bit files")
    p.add_argument(
        "--row-gguf",
        action="append",
        default=[],
        metavar="SYSTEM",
        help="also measure KL on this row's committed GGUF file (its workload's files)",
    )
    p.add_argument("--gpus", type=gpu_list, required=True, metavar="LIST")
    p.add_argument("--slots", type=int, default=1, help="llama-server slots (default: 1)")
    p.add_argument(
        "--engine",
        choices=sorted(SYSTEMS),
        default="llama.cpp",
        help="vllm: the reference, its rerun and the smaller model in vLLM, for a rung whose "
        "16-bit reference llama.cpp's pin cannot run (RFC-0018 FI-9; default: llama.cpp)",
    )
    p.add_argument(
        "--part",
        choices=[PART],
        help="controls: only the quantize controls, in llama.cpp, built from --reference-gguf-dir "
        "(FI-9); the record is fidelity-run-controls.json",
    )
    p.add_argument(
        "--reference-gguf-dir",
        type=Path,
        help="with --part controls: the 16-bit GGUF of the reference, fetched at "
        "--gguf-source REPO@REVISION",
    )
    p.add_argument("--gguf-source", metavar="REPO@REVISION", help="with --reference-gguf-dir")
    p.add_argument(
        "--work",
        type=Path,
        help="the job's io directory, on a disk that holds the 16-bit GGUF and one control "
        "(default: fidelity-work/<release>/<rung>)",
    )
    p.add_argument("--results", type=Path, help="default: the repository's results/")
    p.add_argument(
        "--teacher-forced",
        action="store_true",
        help="feed each prompt and its stored reference reply, and store the engine's top token "
        "at every reply position and its most probable tokens there (RFC-0018 FI-10 to FI-15); "
        "no reply is generated and nothing gates",
    )
    p.add_argument(
        "--system",
        help="with --teacher-forced: a row's own code, through its adapter's score subcommand "
        "(AD-7), in --scoring-image",
    )
    p.add_argument(
        "--scoring-image",
        metavar="REPOSITORY@sha256:DIGEST",
        help="with --system: the image built for scoring; its upstream commit must be the "
        "counted sessions'",
    )
    p.add_argument(
        "--before",
        default="setup",
        metavar="STEP[,STEP]",
        help="with --system: the adapter steps score needs first (default: setup)",
    )
    p.add_argument(
        "--prover-files",
        type=Path,
        help="with --system: the prover files of a counted session's commitment store, each "
        "checked against the digest the sessions record, in place of a commit step",
    )
    p.add_argument("--only", metavar="ID[,ID]", help="with --teacher-forced: these controls only")
    p.add_argument(
        "--limit",
        type=int,
        help="with --teacher-forced: the first N prompts (a trial; `fidelity score` reads no "
        "such run)",
    )
    p.add_argument(
        "--top-k",
        type=int,
        default=256,
        help="with --teacher-forced: the most probable tokens listed per position (default: "
        "256, FI-12; 0: none)",
    )
    p.add_argument(
        "--name",
        help="with --teacher-forced: the run record's name (default: the system, the part or "
        "the engine)",
    )
    p.add_argument("--timeout-h", type=float, default=48.0, help="per call (default: 48)")
    p.add_argument("--hosted", action="store_true", help="this container is the pinned image")
    p.add_argument("--image", metavar="IMAGE_ID", help="a locally built image by ID")
    p.add_argument("--in-process", action="store_true", help=argparse.SUPPRESS)  # tests only
    p.set_defaults(handler=fidelity_run)

    p = command(
        "score",
        "score the controls and the rows against the reference and write fidelity.json (CPU)",
        fsub,
        "fidelity score",
    )
    p.add_argument("--level", default="L1", help="level id (default: L1)")
    p.add_argument("--rung", required=True)
    p.add_argument("--release", required=True)
    p.add_argument(
        "--part",
        choices=["teacher-forced"],
        help="teacher-forced: agreement, its tests and KL from the stored passes into "
        "teacher-forced.json (RFC-0018 FI-10 to FI-15); fidelity.json is not written",
    )
    p.add_argument(
        "--raw",
        type=Path,
        help="with --part teacher-forced: the passes' lists (one directory per id), from which "
        "the KL values are measured into kl.json first",
    )
    p.set_defaults(handler=fidelity_score)


# ---------------------------------------------------------------- shared


def _root() -> Path:
    from iproofs.validate import repo_root  # noqa: PLC0415

    return repo_root(Path.cwd())


def _read_jsonl(path: Path) -> list[list[int]]:
    if not path.is_file():
        raise IProofsError(ErrorKind.CONFIG, f"no {path}")
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not all(isinstance(r, list) and all(isinstance(t, int) for t in r) for r in rows):
        raise IProofsError(ErrorKind.CONFIG, f"{path}: not one token-id list per line")
    return rows


def fidelity_dir(results: Path, release: str, rung: str) -> Path:
    return results / release / "fidelity" / rung


# ---------------------------------------------------------------- run


def _cpuset() -> str:
    cpus = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else []
    return ",".join(map(str, cpus)) if cpus else f"0-{(os.cpu_count() or 1) - 1}"


def _containers(
    root: Path, args: argparse.Namespace, registry: "SchemaRegistry", system: str = SYSTEM
) -> tuple["ContainerRunner", str]:
    """The runner and the image reference recorded: the pinned image of system.yaml, a local
    build by ID (`local/...`, never eligible for a release, RFC-0014), or, hosted, the image
    the provider started."""
    from iproofs.adapter import (  # noqa: PLC0415
        DockerRunner,
        HostedRunner,
        InProcessRunner,
        check_image,
        image_environment,
    )
    from iproofs.cli import entrypoint_argv, local_image  # noqa: PLC0415
    from iproofs.serialize import load_yaml  # noqa: PLC0415

    system_dir = root / "systems" / system
    pin = load_yaml(system_dir / "system.yaml").get("image")
    pinned = check_image(f"{pin['repository']}@{pin['digest']}") if isinstance(pin, dict) else None
    if args.in_process:
        if args.hosted or args.image:
            raise IProofsError(ErrorKind.CONFIG, "--in-process runs no image")
        runner = InProcessRunner(system_dir / "entrypoint", registry)
        return runner, "local/in-process@sha256:" + "0" * 64
    image = local_image(system, args.image, hosted=args.hosted) if args.image else pinned
    if image is None:
        raise IProofsError(ErrorKind.CONFIG, f"systems/{system}/system.yaml pins no image yet; "
                           "build it and pass --image")  # fmt: skip
    if args.hosted:
        argv = entrypoint_argv((system_dir / "Dockerfile").read_text())
        environ = image_environment(Path("/proc/1/environ").read_text())
        return HostedRunner(argv, registry, environ), image
    return DockerRunner(registry), image


def _reference_dir(
    root: Path, registry: "SchemaRegistry", rung: "Rung", given: Path | None
) -> tuple[Path, dict[str, object]]:
    """FI-1's files and how they were checked: the serving record's files, fetched and checked
    against the record (RFC-0014 SM-2), or, for a rung whose reference is a repository the
    level names by revision, the directory given, each file's sha256 recorded (the level file
    lists no files for it yet)."""
    from iproofs.level import ServingReference  # noqa: PLC0415
    from iproofs.model import ServingModel, load  # noqa: PLC0415
    from iproofs.runner import retry_fetch  # noqa: PLC0415
    from iproofs.serving import SERVING_DIR, ensure_serving_model  # noqa: PLC0415
    from iproofs.workloads import default_cache, hub_download  # noqa: PLC0415

    ref = rung.reference
    if isinstance(ref, ServingReference) and ref.serving_files:
        if given is not None:
            raise IProofsError(ErrorKind.CONFIG, f"rung {rung.id}: the reference is the serving "
                               f"record {rung.serving}; drop --reference-dir")  # fmt: skip
        doc = load(root / SERVING_DIR / f"{rung.serving}.yaml", registry)
        assert isinstance(doc, ServingModel)
        path = ensure_serving_model(doc, default_cache(), download=hub_download,
                                    retry=lambda op: retry_fetch(op, f"serving model {doc.id}"),
                                    token=os.environ.get("HF_TOKEN"))  # fmt: skip
        return path, {"serving": rung.serving, "checked": "against the serving record"}
    if given is None or not given.is_dir():
        raise IProofsError(ErrorKind.CONFIG, f"rung {rung.id}: give --reference-dir, the 16-bit "
                           "release the level names")  # fmt: skip
    return given, {"source": _source(ref), "files": _digests(given)}


def _source(ref: object) -> dict[str, object]:
    source = getattr(ref, "source", None)
    return {k: getattr(source, k, None) for k in ("hub", "repo", "revision")}


def _digests(directory: Path) -> dict[str, str]:
    """Each file's sha256, recorded at fetch (AGENTS.md rule 11)."""
    from iproofs.provenance import hex_digests  # noqa: PLC0415

    files = {p.relative_to(directory).as_posix(): p for p in sorted(directory.rglob("*"))
             if p.is_file()}  # fmt: skip
    found = hex_digests(files)
    return {k: f"sha256:{v}" for k, v in sorted(found.items())}


def _row_dir(root: Path, registry: "SchemaRegistry", rung: "Rung", system: str) -> Path:
    """A row's committed files: its workload's model, fetched and checked (RFC-0014)."""
    from iproofs.runner import retry_fetch  # noqa: PLC0415
    from iproofs.workloads import default_cache, ensure_model, load_workload  # noqa: PLC0415

    if system not in rung.workloads:
        raise IProofsError(ErrorKind.CONFIG, f"rung {rung.id} runs no {system!r}")
    wl = load_workload(rung.workloads[system], root=root, registry=registry)
    if not any(f.path.endswith(".gguf") for f in wl.model.files):
        raise IProofsError(ErrorKind.CONFIG, f"{system}: workload {wl.id} commits no GGUF file")
    return ensure_model(wl, default_cache(), retry=lambda op: retry_fetch(op, f"model {wl.id}"),
                        token=os.environ.get("HF_TOKEN"))  # fmt: skip


def _control_job(control: object) -> dict[str, object]:
    keys = ("id", "kind", "recipe", "type", "every")
    return {k: getattr(control, k) for k in keys if getattr(control, k, None) is not None}


def fidelity_run(args: argparse.Namespace) -> int:
    """`iproofs fidelity run`: FI-1, FI-2 and FI-7. Prints the record's path; exit 4 when the
    reference call failed (nothing can be scored), 0 otherwise (a failed control is recorded)."""
    from iproofs.level import level_digest, level_file, load_level, rung_prompts  # noqa: PLC0415
    from iproofs.provenance import git_state  # noqa: PLC0415
    from iproofs.schema import SchemaRegistry  # noqa: PLC0415
    from iproofs.serialize import write_jsonl  # noqa: PLC0415

    if args.teacher_forced:
        from iproofs.commands import teacher_forced  # noqa: PLC0415

        return teacher_forced.run(args)
    root = _root()
    registry = SchemaRegistry.from_tree(root / "schema")
    level = load_level(root, args.level, registry=registry)
    rung = level.rung(args.rung)
    prompts = _read_jsonl(args.prompts_dir / "prompts.jsonl")
    texts = _read_jsonl(args.prompts_dir / "kl-texts.jsonl")
    _check_inputs(level, rung, prompts, texts)
    work = args.work or Path("fidelity-work") / args.release / rung.id
    io = work / "io"
    io.mkdir(parents=True, exist_ok=True)
    prompts_digest = write_jsonl(io / "prompts.jsonl", rung_prompts(prompts, level, rung))
    texts_digest = write_jsonl(io / "kl-texts.jsonl", texts)
    if args.part is not None and args.engine != "llama.cpp":
        raise IProofsError(ErrorKind.CONFIG, "--part controls runs in llama.cpp; drop --engine")
    if args.engine == "vllm" and args.row_gguf:
        raise IProofsError(ErrorKind.CONFIG, "--row-gguf measures KL in llama.cpp; not with vllm")
    system = SYSTEMS[args.engine]
    containers, image = _containers(root, args, registry, system)
    info, said = _call(containers, image, io, {"subcommand": "info"}, None, args, "info")
    if info["exit_code"] != 0 or not said:
        raise IProofsError(ErrorKind.ADAPTER, f"{system} info failed: {info['stderr_tail']}")
    commit = str(said.get("upstream_commit"))
    pinned = _engine_pin(root, level, system)
    if pinned is not None and commit != pinned:
        raise IProofsError(ErrorKind.INTEGRITY, f"the image runs {args.engine} {commit}, the "
                           f"pin is {pinned}")  # fmt: skip
    common = {"subcommand": "prove", "rung": rung.id, "model_dir": "/models",
              "dtype": rung.reference.dtype, "prompts_file": "/io/prompts.jsonl",
              "kl_texts_file": "/io/kl-texts.jsonl",
              "output_tokens": level.request.output_tokens,
              "kl": {"tokens": level.kl.tokens, "texts": level.kl.texts},
              "slots": args.slots}  # fmt: skip
    calls, not_run, reference_record = _plan(args, root, registry, rung)
    records = [info]
    for name, models, controls, replies, extra in calls:
        job = {**common, **extra, "call": name, "controls": controls, "replies": replies}
        record, _ = _call(containers, image, io, job, models, args, name)
        records.append(record)
        if name == "reference" and record["exit_code"] != 0:
            break  # no reference: the other calls would score against nothing
    out = fidelity_dir(args.results or root / "results", args.release, rung.id)
    suffix = f"-{args.part}" if args.part else ""
    _collect(io, out, suffix)
    commit_sha, dirty = git_state(root)
    run_record = {
        "schema": "fidelity-run/1",
        **({"part": args.part} if args.part else {}),
        "level": {"id": level.id, "digest": level_digest(level_file(root, level.id))},
        "rung": rung.id,
        "release": args.release,
        "engine": {
            "tool": args.engine,
            "repo": ENGINE_REPOS.get(args.engine, level.fidelity.engine.repo),
            "commit": commit,
            "image": image,
        },
        "adapter": {k: said.get(k) for k in ("adapter_commit", "adapter_dirty")},
        "harness": {"git_commit": commit_sha, "git_dirty": dirty},
        "prompts_digest": prompts_digest,
        "kl_texts_digest": texts_digest,
        "gpus": list(args.gpus),
        "slots": args.slots,
        "reference": reference_record,
        "other_model": {
            "source": [_source(c) for c in rung.controls if c.recipe == "other_model"],
            "files": _digests(args.other_model_dir) if args.other_model_dir else {},
        },
        "not_run": not_run,
        "calls": records,
    }
    name = RUN_RECORD.replace(".json", f"{suffix}.json")
    print(_write_checked(registry, "fidelity-run/1", out / name, run_record))
    reference_ok = len(records) > 1 and records[1]["exit_code"] == 0
    return 0 if reference_ok else 4


Call = tuple[str, Path, list[dict[str, object]], bool, dict[str, object]]


def _plan(
    args: argparse.Namespace, root: Path, registry: "SchemaRegistry", rung: "Rung"
) -> tuple[list[Call], dict[str, str], dict[str, object]]:
    """The calls of this run (name, model directory, controls, replies wanted, extra job keys),
    the controls it leaves out with why, and the record of its reference files."""
    own = [c for c in rung.controls if c.recipe != "other_model"]
    other = [c for c in rung.controls if c.recipe == "other_model"]
    not_run: dict[str, str] = {}
    calls: list[Call] = []
    if args.part == PART:
        reference_record, gguf_dir, gguf = _given_gguf(args)
        chosen = [c for c in own if c.recipe == "quantize"]
        for c in rung.controls:
            if c not in chosen:
                not_run[c.id] = "not in this part: the vLLM run of the rung (FI-9)"
        extra: dict[str, object] = {"reference_gguf": f"/models/{gguf}"}
        calls.append(("controls", gguf_dir, [_control_job(c) for c in chosen], True, extra))
    else:
        reference_dir, reference_record = _reference_dir(root, registry, rung, args.reference_dir)
        kept = own if args.engine == "llama.cpp" else [c for c in own if c.recipe == "rerun"]
        for c in own:
            if c not in kept:
                not_run[c.id] = FI9_CAUSES[c.recipe]
        calls.append(("reference", reference_dir, [_control_job(c) for c in kept], True, {}))
        if other and args.other_model_dir is not None:
            calls.append(("other_model", args.other_model_dir,
                          [_control_job(c) for c in other], True, {}))  # fmt: skip
        for c in other if args.other_model_dir is None else []:
            not_run[c.id] = "not run: no --other-model-dir was given"
        for row_system in args.row_gguf:
            row: dict[str, object] = {"id": f"{ROW_PREFIX}{row_system}", "kind": "row",
                                      "recipe": "file"}  # fmt: skip
            calls.append(("file", _row_dir(root, registry, rung, row_system), [row], False, {}))
    return calls, not_run, reference_record


# FI-9: why a vLLM run of a rung leaves a level control to the llama.cpp part, or does not run it
FI9_CAUSES = {
    "quantize": "run in llama.cpp by the controls part (fidelity-run-controls.json), built from "
    "the 16-bit GGUF (RFC-0018 FI-9)",
    "drop_blocks": "not run: the copy would be the 16-bit file in llama.cpp, which the level's "
    "llama.cpp pin cannot run on this rung (RFC-0018 FI-9)",
}


FI9_NO_KL = ("not measured: llama.cpp's KL base is the 16-bit file, which the level's llama.cpp "
             "pin cannot run on this rung (RFC-0018 FI-9)")  # fmt: skip


def _engine_pin(root: Path, level: "Level", system: str) -> str | None:
    """The engine commit the image must report: the level's llama.cpp pin, or the vLLM commit
    the reference system's system.yaml pins (FI-9)."""
    from iproofs.serialize import load_yaml  # noqa: PLC0415

    if system == SYSTEM:
        return level.fidelity.engine.commit
    engine = load_yaml(root / "systems" / system / "system.yaml").get("engine")
    commit = engine.get("commit") if isinstance(engine, dict) else None
    return str(commit) if commit else None


def _given_gguf(args: argparse.Namespace) -> tuple[dict[str, object], Path, str]:
    """FI-9's 16-bit GGUF for the controls part: its source and each file's sha256, the
    directory, and the first file of the set relative to it."""
    given = args.reference_gguf_dir
    if given is None or not given.is_dir() or not args.gguf_source:
        raise IProofsError(ErrorKind.CONFIG, "--part controls needs --reference-gguf-dir and "
                           "--gguf-source REPO@REVISION")  # fmt: skip
    found = sorted(given.rglob("*.gguf"))
    if not found:
        raise IProofsError(ErrorKind.CONFIG, f"no .gguf file under {given}")
    repo, _, revision = str(args.gguf_source).partition("@")
    source = {"hub": "huggingface", "repo": repo, "revision": revision or None}
    return (
        {"source": source, "files": _digests(given)},
        given,
        found[0].relative_to(given).as_posix(),
    )


def _write_checked(
    registry: "SchemaRegistry", schema: str, path: Path, doc: Mapping[str, object]
) -> Path:
    """Write a record the harness made, after its schema accepts it."""
    from iproofs.serialize import write_json  # noqa: PLC0415

    errors = registry.errors(schema, dict(doc))
    if errors:
        raise IProofsError(ErrorKind.INTERNAL, f"{path.name} fails {schema}: {errors[0]}")
    write_json(path, doc)
    return path


def _check_inputs(
    level: "Level", rung: "Rung", prompts: Sequence[list[int]], texts: Sequence[list[int]]
) -> None:
    want = level.sessions.slots * rung.requests_per_session
    if len(prompts) != want:
        raise IProofsError(ErrorKind.CONFIG, f"prompts.jsonl has {len(prompts)} prompts; rung "
                           f"{rung.id} has {want} (slots x requests_per_session)")  # fmt: skip
    if len(texts) != level.kl.texts:
        raise IProofsError(ErrorKind.CONFIG, f"kl-texts.jsonl has {len(texts)} texts, the "
                           f"level {level.kl.texts}")  # fmt: skip
    if {len(p) for p in prompts} != {level.request.prompt_tokens}:
        raise IProofsError(ErrorKind.CONFIG, f"prompts are not all {level.request.prompt_tokens} "
                           "tokens")  # fmt: skip
    if {len(t) for t in texts} != {level.kl.tokens}:
        raise IProofsError(ErrorKind.CONFIG, f"KL texts are not all {level.kl.tokens} tokens")


def _call(
    containers: "ContainerRunner",
    image: str,
    io: Path,
    job: Mapping[str, object],
    models: Path | None,
    args: argparse.Namespace,
    name: str,
) -> tuple[dict[str, object], dict[str, object]]:
    """One call of the image: its record (exit code and last lines kept, AGENTS.md rule 5)
    and what `info` said (upstream and adapter commits), empty for another step."""
    from iproofs.log.redact import Redactor  # noqa: PLC0415
    from iproofs.serialize import write_json  # noqa: PLC0415

    step = str(job["subcommand"])
    (io / "out.json").unlink(missing_ok=True)
    write_json(io / "job.json", job)
    if not args.quiet:
        print(f"fidelity: {name} call", file=sys.stderr)
    started = time.monotonic()
    result = containers.run(
        image,
        step,
        io,
        models_dir=models,
        gpu=",".join(map(str, args.gpus)) if step == "prove" else None,
        cpuset=_cpuset(),
        mems="0",
        memory=None,
        timeout_s=args.timeout_h * 3600,
    )
    redact = Redactor.from_host()
    out = result.out
    record: dict[str, object] = {
        "call": name,
        "step": step,
        "exit_code": result.exit_code,
        "seconds": time.monotonic() - started,
        "stderr_tail": [redact(line) for line in result.stderr_tail[-20:]],
        "phases": [{"name": p.name, "seconds": p.seconds} for p in (out.phases if out else ())],
    }
    said: dict[str, object] = {}
    if out is not None and step == "info":
        said = {"upstream_commit": out.upstream_commit, "adapter_commit": out.adapter_commit,
                "adapter_dirty": out.adapter_dirty}  # fmt: skip
    return record, said


def _collect(io: Path, out: Path, suffix: str = "") -> None:
    """The image's outputs into the results tree: replies, KL logs and command logs (host paths
    redacted, AGENTS.md rule 7), the status, and the reference's replies as reference.jsonl. A
    part's status and command log take its suffix (`status-controls.json`)."""
    from iproofs.log.redact import Redactor  # noqa: PLC0415

    redact = Redactor.from_host()
    out.mkdir(parents=True, exist_ok=True)
    src = io / "fidelity"
    for sub in ("replies", "kl", "logs"):
        target = out / sub
        target.mkdir(exist_ok=True)
        for f in sorted((src / sub).glob("*")) if (src / sub).is_dir() else []:
            if sub == "replies":
                shutil.copyfile(f, target / f.name)
            else:
                (target / f.name).write_text(redact(f.read_text(errors="replace")))
    if (src / "status.json").is_file():
        shutil.copyfile(src / "status.json", out / f"status{suffix}.json")
    if (io / "commands.jsonl").is_file():
        (out / f"commands{suffix}.jsonl").write_text(redact((io / "commands.jsonl").read_text()))
    reference = src / "replies" / "reference.jsonl"
    if reference.is_file():
        shutil.copyfile(reference, out / "reference.jsonl")


# ---------------------------------------------------------------- score


def _kl(base: Path, ref: str, ident: str) -> dict[str, object] | None:
    """FI-7: the KL figure of `kl/<ident>.log`, or None when llama-perplexity printed none."""
    from iproofs.fidelity import kl_quantity, parse_kl  # noqa: PLC0415

    log = base / "kl" / f"{ident}.log"
    value = parse_kl(log.read_text()) if log.is_file() else None
    return kl_quantity(value, f"{ref}/kl/{ident}.log#Mean KLD") if value is not None else None


Scored = tuple[dict[str, object], list[list[int]] | None, str | None, dict[str, object] | None]


def _controls(rung: "Rung", base: Path, ref: str, record: Mapping[str, object]) -> list[Scored]:
    """Each control of the level file with its stored replies, or the cause it has none. A
    control a part ran (FI-9, `status-<part>.json`) takes the part's outcome."""
    status_path = base / "status.json"
    status = json.loads(status_path.read_text()) if status_path.is_file() else {}
    by_id: dict[str, dict[str, object]] = dict(status.get("controls", {}))
    not_run = record.get("not_run")
    skipped: dict[str, str] = dict(not_run) if isinstance(not_run, dict) else {}
    for part in sorted(base.glob("status-*.json")):
        for cid, st in json.loads(part.read_text()).get("controls", {}).items():
            if cid in skipped or cid not in by_id:
                by_id[cid] = st
                skipped.pop(cid, None)
    out: list[Scored] = []
    for c in rung.controls:
        spec: dict[str, object] = {
            "id": c.id,
            "kind": c.kind,
            "recipe": c.recipe,
            "type": getattr(c, "type", None),
        }  # the steps name Q8_0 and Q4_K_M by type
        st = by_id.get(c.id)
        replies_file = base / "replies" / f"{c.id}.jsonl"
        if st is not None and st.get("status") == "ok" and replies_file.is_file():
            out.append((spec, _read_jsonl(replies_file), None, _kl(base, ref, c.id)))
            continue
        cause = skipped.get(c.id) or (str(st.get("cause")) if st else None)
        out.append((spec, None, cause or "not run: the image recorded no outcome for it", None))
    return out


def _rows(
    args: argparse.Namespace,
    level: "Level",
    rung: "Rung",
    registry: "SchemaRegistry",
    base: Path,
    ref: str,
    digest: str,
    no_kl: str | None = None,
) -> tuple[dict[str, list[list[int]] | None], dict[str, tuple[dict[str, object] | None, str]]]:
    """FI-6: each row's replies from its counted sessions (None without all three) and its KL
    figure with the note printed beside it (FI-7); `no_kl`, the note of a rung where no KL is
    measured (FI-9)."""
    from iproofs.checks import row_sessions  # noqa: PLC0415 (SE-3, the counted sessions)
    from iproofs.fidelity import KL_NOTE, row_replies, session_replies  # noqa: PLC0415
    from iproofs.workloads import load_workload  # noqa: PLC0415

    rows: dict[str, list[list[int]] | None] = {}
    row_kl: dict[str, tuple[dict[str, object] | None, str]] = {}
    root = _root()
    for system, workload_id in sorted(rung.workloads.items()):
        sessions = row_sessions(root, args.release, level, rung.id, system, digest)
        by_slot = {}
        for slot, session in sessions.counted.items():
            found = session_replies(session.run.run)
            if found is not None:
                by_slot[slot] = found
        rows[system] = row_replies(by_slot, level.sessions.slots, rung.requests_per_session)
        wl = load_workload(workload_id, root=root, registry=registry)
        quantity = _kl(base, ref, f"{ROW_PREFIX}{system}")
        if quantity is not None:
            row_kl[system] = (quantity, KL_NOTE)
        elif no_kl is not None:
            row_kl[system] = (None, no_kl)
        elif any(f.path.endswith(".gguf") for f in wl.model.files):
            row_kl[system] = (None, "not measured: no KL run on the committed GGUF file yet")
        else:
            row_kl[system] = (None, "not measured: the committed copy is not a file llama.cpp "
                              "loads (FI-7)")  # fmt: skip
    return rows, row_kl


def fidelity_score(args: argparse.Namespace) -> int:
    """`iproofs fidelity score`: FI-3 to FI-6 from stored records; prints fidelity.json's path."""
    from iproofs.fidelity import Header, SignFlipRule, build_fidelity  # noqa: PLC0415
    from iproofs.level import level_digest, level_file, load_beacon, load_level  # noqa: PLC0415
    from iproofs.provenance import file_digest  # noqa: PLC0415
    from iproofs.schema import SchemaRegistry  # noqa: PLC0415
    from iproofs.serialize import write_json  # noqa: PLC0415

    if args.part == "teacher-forced":
        from iproofs.commands import teacher_forced  # noqa: PLC0415

        return teacher_forced.score(args)
    root = _root()
    registry = SchemaRegistry.from_tree(root / "schema")
    level = load_level(root, args.level, registry=registry)
    rung = level.rung(args.rung)
    base = fidelity_dir(root / "results", args.release, rung.id)
    ref = f"results/{args.release}/fidelity/{rung.id}"  # how records name it (RFC-0012)
    record_path = base / RUN_RECORD
    if not record_path.is_file():
        raise IProofsError(ErrorKind.CONFIG, f"no {record_path}: run `iproofs fidelity run`")
    record = json.loads(record_path.read_text())
    digest = level_digest(level_file(root, level.id))
    for path in [record_path, *sorted(base.glob("fidelity-run-*.json"))]:
        part = json.loads(path.read_text())
        if part["level"]["digest"] != digest:
            ran = part["level"]["digest"]
            raise IProofsError(ErrorKind.CONFIG, f"{path} ran under level digest {ran}, the "
                               f"level file is {digest}")  # fmt: skip
        if part["prompts_digest"] != record["prompts_digest"]:
            raise IProofsError(ErrorKind.INTEGRITY, f"{path}: other prompts than {record_path}")
    beacon = load_beacon(root, level, registry=registry)
    rule = SignFlipRule(level.fidelity.alpha, level.fidelity.exact_up_to,
                        level.fidelity.resamples, str(beacon["randomness"]))  # fmt: skip
    reference_path = base / "reference.jsonl"
    reference = _read_jsonl(reference_path)
    if len(reference) != level.sessions.slots * rung.requests_per_session:
        raise IProofsError(ErrorKind.INTEGRITY, f"{reference_path}: {len(reference)} replies")
    controls = _controls(rung, base, ref, record)
    no_kl = FI9_NO_KL if record["engine"].get("tool") == "vllm" else None
    rows, row_kl = _rows(args, level, rung, registry, base, ref, digest, no_kl)
    engine = dict(record["engine"])
    header = Header(level.id, digest, rung.id, str(record["prompts_digest"]),
                    {k: engine.get(k) for k in ("tool", "repo", "commit", "image")},
                    f"{ref}/reference.jsonl", file_digest(reference_path),
                    int(record["slots"]))  # fmt: skip
    doc = build_fidelity(header, rule, reference, controls, rows, row_kl)
    errors = registry.errors("fidelity/1", doc)
    if errors:
        raise IProofsError(ErrorKind.INTERNAL, f"fidelity.json fails fidelity/1: {errors[0]}")
    out = base / "fidelity.json"
    write_json(out, doc)
    print(out)
    return 0
