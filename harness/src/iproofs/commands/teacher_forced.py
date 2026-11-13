"""`iproofs fidelity run --teacher-forced` and `iproofs fidelity score --part teacher-forced`
(RFC-0018 FI-10 to FI-15).

`run` feeds each of the rung's prompts followed by the stored reference reply to one engine and
stores, under `results/<release>/teacher-forced/<rung>/`, the top token at every reply
position (`top/<id>.jsonl`), the lists of most probable tokens (`raw/<id>/<prompt>.topk`, which
stay outside the repository) and its record (`run-<name>.json`). The engine is the reference
image (the reference itself and the controls it builds, in llama.cpp or vLLM), or with
`--system` a system's own code through its adapter's `score` subcommand (AD-7), in a scoring
image whose upstream commit must be the one the row's counted sessions ran.

`score` runs on a CPU: agreement and the tests from the stored top tokens, KL from the stored
values (`kl.json`), which `--raw DIR` measures first from the lists. It writes
`teacher-forced.json` in that folder and never writes `fidelity.json` (APP-1).
"""

import argparse
import json
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from iproofs.commands import fidelity as fid
from iproofs.errors import ErrorKind, IProofsError

if TYPE_CHECKING:
    from iproofs.adapter import ContainerRunner
    from iproofs.level import Level, Rung
    from iproofs.schema import SchemaRegistry

DIR = "teacher-forced"
LEFT_OUT = "not run: left out of this job (--only)"
SCORED = "teacher-forced.json"
KL_VALUES = "kl.json"
# FI-13: whose computation a row's figures are, printed with them
COMPUTED_BY = {
    "sash": "SASH's witness extractor (harness.witness.extract --head), the program that "
    "writes the prover's input, run on the reference reply; no proof is made of these ids",
    "flashprove": "the publisher's integer-model package (IntegerModel.extend), which the "
    'publisher says is "by design" the function the prover proves; that it equals cp_prove '
    "value by value at full size is not stated",
}


def tf_dir(results: Path, release: str, rung: str) -> Path:
    """A rung's teacher-forced records, a folder of their own beside `fidelity/`."""
    return results / release / DIR / rung


# ---------------------------------------------------------------- run


def _stored_reference(root: Path, args: argparse.Namespace, level: "Level", rung: "Rung"
                      ) -> tuple[Path, list[list[int]]]:  # fmt: skip
    """FI-10 feeds the stored reference replies (FI-1, FI-9), from the repository's results."""
    path = fid.fidelity_dir(root / "results", args.release, rung.id) / "reference.jsonl"
    replies = fid._read_jsonl(path)
    want = level.sessions.slots * rung.requests_per_session
    if len(replies) != want or {len(r) for r in replies} != {level.request.output_tokens}:
        raise IProofsError(ErrorKind.INTEGRITY, f"{path}: not {want} replies of "
                           f"{level.request.output_tokens} tokens")  # fmt: skip
    return path, replies


def _sessions_pin(root: Path, args: argparse.Namespace, level: "Level", rung: "Rung",
                  system: str, digest: str) -> dict[str, Any]:  # fmt: skip
    """What the row's counted sessions ran, and the prover files their commitments record."""
    from iproofs.checks import row_sessions  # noqa: PLC0415
    from iproofs.fidelity import session_replies  # noqa: PLC0415

    sessions = row_sessions(root, args.release, level, rung.id, system, digest)
    runs = []
    files: dict[str, set[str]] = {}
    for slot, s in sorted(sessions.counted.items()):
        m: Any = s.run.manifest
        runs.append({"slot": slot, "run": s.run_id, "image": m["system"]["image"]["ref"],
                     "adapter_commit": m["system"]["adapter_commit"],
                     "upstream_commit": m["system"]["upstream"]["commit"]})  # fmt: skip
        for f in m["commitment"].get("prover_files") or []:
            files.setdefault(str(f["name"]), set()).add(str(f["digest"]))
    if not runs:
        raise IProofsError(ErrorKind.CONFIG, f"{system} has no counted session on {rung.id} in "
                           f"{args.release}: nothing names the commit to score")  # fmt: skip
    # FI-14: the system's own proved reply to prompt 0 (slot 1's first request), which the
    # scoring path must reproduce token for token before any reference reply is scored
    first = sessions.counted.get(1)
    own = session_replies(first.run.run) if first is not None else None
    return {"sessions": runs, "prover_files": {k: sorted(v) for k, v in sorted(files.items())},
            "own_reply": None if not own else {"run": first.run_id if first else None,
                                               "reply": own[0]}}  # fmt: skip


def _place_prover_files(
    given: Path, pin: Mapping[str, Any], io: Path
) -> tuple[list[str], dict[str, Any]]:
    """Copies the files of a counted session's commitment into io/state/prover-files after
    checking each against the digest every counted session records (AGENTS.md rule 6)."""
    from iproofs.provenance import file_digest  # noqa: PLC0415

    target = io / "state" / "prover-files"
    target.mkdir(parents=True, exist_ok=True)
    placed, checked = [], {}
    for name, digests in pin["prover_files"].items():
        src = given / name
        if not src.is_file():
            raise IProofsError(ErrorKind.CONFIG, f"--prover-files: no {src}")
        found = file_digest(src)
        if digests != [found]:
            raise IProofsError(ErrorKind.INTEGRITY, f"{src} is {found}; the counted sessions "
                               f"record {digests}")  # fmt: skip
        shutil.copyfile(src, target / name)
        placed.append(f"/io/state/prover-files/{name}")
        checked[name] = found
    return placed, {"from": "a counted session's commitment store", "files": checked,
                    "equal_to_sessions": True}  # fmt: skip


def _system_runner(root: Path, args: argparse.Namespace, registry: "SchemaRegistry",
                   system: str) -> tuple["ContainerRunner", str]:  # fmt: skip
    from iproofs.adapter import (  # noqa: PLC0415
        DockerRunner,
        HostedRunner,
        InProcessRunner,
        check_image,
        image_environment,
    )
    from iproofs.cli import entrypoint_argv  # noqa: PLC0415

    system_dir = root / "systems" / system
    if args.in_process:
        return (InProcessRunner(system_dir / "entrypoint", registry),
                "local/in-process@sha256:" + "0" * 64)  # fmt: skip
    if not args.scoring_image:
        raise IProofsError(ErrorKind.CONFIG, "--system needs --scoring-image "
                           "REPOSITORY@sha256:DIGEST, the image built for scoring")  # fmt: skip
    image = check_image(args.scoring_image)
    if args.hosted:
        argv = entrypoint_argv((system_dir / "Dockerfile").read_text())
        environ = image_environment(Path("/proc/1/environ").read_text())
        return HostedRunner(argv, registry, environ), image
    return DockerRunner(registry), image


def _system_calls(  # noqa: PLR0915 (one adapter flow, read top to bottom)
    args: argparse.Namespace, root: Path, registry: "SchemaRegistry", level: "Level",
    rung: "Rung", io: Path, digest: str, requests: Sequence[Mapping[str, object]],
) -> dict[str, Any]:  # fmt: skip
    """AD-7: `info`, the steps `score` needs (`--before`), then `score`. Returns the record's
    parts. The image's upstream commit must be the counted sessions'."""
    from iproofs.provenance import file_digest  # noqa: PLC0415
    from iproofs.runner import retry_fetch  # noqa: PLC0415
    from iproofs.serialize import write_json, write_jsonl  # noqa: PLC0415
    from iproofs.workloads import default_cache, ensure_model, load_workload  # noqa: PLC0415

    system = args.system
    if system not in rung.workloads:
        raise IProofsError(ErrorKind.CONFIG, f"rung {rung.id} runs no {system!r}")
    pin = _sessions_pin(root, args, level, rung, system, digest)
    wl = load_workload(rung.workloads[system], root=root, registry=registry)
    models = ensure_model(wl, default_cache(), retry=lambda op: retry_fetch(op, f"model {wl.id}"),
                          token=None)  # fmt: skip
    containers, image = _system_runner(root, args, registry, system)
    shape = wl.shape
    base = {"schema": "adapter-job/1", "contract": "adapter/1",
            "run_id": f"teacher-forced-{system}-{rung.id}",
            "workload": {"id": wl.id, "version": wl.version},
            "shape": {"prompt_tokens": shape.prompt_tokens, "output_tokens": shape.output_tokens,
                      "batch_size": shape.batch_size,
                      "batches_per_session": shape.batches_per_session,
                      "context_window": shape.context_window},
            "control": False}  # fmt: skip
    records = []
    info, said = fid._call(containers, image, io, {**base, "subcommand": "info"}, None, args,
                           "info")  # fmt: skip
    records.append(info)
    if info["exit_code"] != 0 or not said:
        raise IProofsError(ErrorKind.ADAPTER, f"{system} info failed: {info['stderr_tail']}")
    upstream = {s["upstream_commit"] for s in pin["sessions"]}
    if upstream != {said.get("upstream_commit")}:
        raise IProofsError(ErrorKind.INTEGRITY, f"the image runs upstream "
                           f"{said.get('upstream_commit')}; the counted sessions ran "
                           f"{sorted(upstream)}")  # fmt: skip
    prover_files: list[str] = []
    provenance: dict[str, Any] | None = None
    if args.prover_files is not None:
        prover_files, provenance = _place_prover_files(args.prover_files, pin, io)
    before = [s for s in (args.before or "").split(",") if s]
    ok = True
    for step in before:
        job = {**base, "subcommand": step,
               **({"model_dir": "/models"} if step == "commit" else {})}  # fmt: skip
        record, _ = fid._call(containers, image, io, job, models, args, step)
        records.append(record)
        if record["exit_code"] != 0:
            ok = False
            break
        if step == "commit":  # the files this job's commit kept, against the sessions' record
            out = json.loads((io / "out.json").read_text())
            prover_files = list(out.get("prover_files") or [])
            found = {Path(f).name: file_digest(io / f.removeprefix("/io/")) for f in prover_files}
            equal = all(pin["prover_files"].get(k) == [v] for k, v in found.items())
            provenance = {"from": "this job's commit", "files": found, "equal_to_sessions": equal}
            if not equal:
                raise IProofsError(ErrorKind.INTEGRITY, f"this job's commit kept {found}; the "
                                   f"counted sessions record {pin['prover_files']}")  # fmt: skip
    failed: list[int] = []
    own = pin.pop("own_reply")
    if own is None or len(own["reply"]) != len(requests[0]["reply"]):  # type: ignore[arg-type]
        raise IProofsError(ErrorKind.CONFIG, f"{system}: no proved reply to prompt 0 in a "
                           "counted session of slot 1, which the run scores first")  # fmt: skip
    check: dict[str, Any] | None = None
    if ok:
        # request 0 is the system's own proved reply to prompt 0; the rest follow it
        requests = [{"prompt": requests[0]["prompt"], "reply": own["reply"]}, *requests]
        write_jsonl(io / "score-requests.jsonl", list(requests))
        shutil.rmtree(io / "score", ignore_errors=True)
        job = {**base, "subcommand": "score", "model_dir": "/models",
               "requests_file": "/io/score-requests.jsonl", "out_dir": "/io/score",
               "top_k": args.top_k,
               **({"prover_files": prover_files} if prover_files else {})}  # fmt: skip
        record, _ = fid._call(containers, image, io, job, models, args, "score")
        records.append(record)
        ok = record["exit_code"] == 0
        if ok:
            first = json.loads((io / "score" / "0.json").read_text())
            agreeing = sum(a == b for a, b in zip(first.get("top", []), own["reply"],
                                                  strict=False))  # fmt: skip
            check = {"prompt": 0, "session": own["run"], "positions": len(own["reply"]),
                     "agreeing": agreeing}  # fmt: skip
            if agreeing != len(own["reply"]):
                why = first.get("failed") or f"{agreeing} of {len(own['reply'])} positions agree"
                raise IProofsError(ErrorKind.INTEGRITY, f"{system}: the scoring path does not "
                                   f"reproduce the system's own proved reply to prompt 0 "
                                   f"({why}); nothing is stored")  # fmt: skip
            failed = [i - 1 for i in json.loads((io / "out.json").read_text())["scores"]["failed"]]
    write_json(io / "sessions-pin.json", pin)
    return {"image": image, "said": said, "records": records, "ok": ok, "failed": failed,
            "pin": pin, "prover_files": provenance, "workload": wl.id,
            "own_reply_check": check}  # fmt: skip


def _collect_system(io: Path, out: Path, system: str, n: int) -> None:
    """The adapter's per-request files into `top/<system>.jsonl` (a list of top tokens, or
    {"failed": cause}, per prompt) and `raw/<system>/<prompt>.topk`. Also the per-request
    seconds where the adapter records them, as `seconds-<system>.json`."""
    (out / "top").mkdir(parents=True, exist_ok=True)
    lines = []
    for i in range(n):  # request i + 1: request 0 is the system's own reply (FI-14)
        doc = json.loads((io / "score" / f"{i + 1}.json").read_text())
        lines.append(json.dumps({"failed": doc["failed"]} if "failed" in doc else doc["top"],
                                separators=(",", ":")))  # fmt: skip
        lists = io / "score" / f"{i + 1}.topk"
        if lists.is_file():
            (out / "raw" / system).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(lists, out / "raw" / system / f"{i}.topk")
    (out / "top" / f"{system}.jsonl").write_text("".join(x + "\n" for x in lines))
    seconds = [json.loads((io / "score" / f"{i}.json").read_text()).get("seconds")
               for i in range(n + 1)]  # fmt: skip
    if any(x is not None for x in seconds):
        (out / f"seconds-{system}.json").write_text(json.dumps(seconds) + "\n")


def _collect_engine(io: Path, out: Path, name: str) -> list[str]:
    """The reference image's outputs: top tokens, lists, status and logs (host paths redacted,
    AGENTS.md rule 7). Returns the ids that have top tokens."""
    from iproofs.log.redact import Redactor  # noqa: PLC0415

    redact = Redactor.from_host()
    src = io / "fidelity"
    ids = []
    (out / "top").mkdir(parents=True, exist_ok=True)
    for f in sorted((src / DIR / "top").glob("*.jsonl")) if (src / DIR / "top").is_dir() else []:
        shutil.copyfile(f, out / "top" / f.name)
        ids.append(f.stem)
    if (src / DIR / "raw").is_dir():
        shutil.copytree(src / DIR / "raw", out / "raw", dirs_exist_ok=True)
    for f in sorted((src / "logs").glob("*")) if (src / "logs").is_dir() else []:
        # a server's log holds a line per request (megabytes): it stays with the lists
        logs = out / ("raw/server-logs" if f.name.startswith("server-") else "logs") / name
        logs.mkdir(parents=True, exist_ok=True)
        (logs / f.name).write_text(redact(f.read_text(errors="replace")))
    if (src / "status.json").is_file():
        shutil.copyfile(src / "status.json", out / f"status-{name}.json")
    return ids


def _only(calls: list[fid.Call], not_run: dict[str, str], only: set[str] | None) -> list[fid.Call]:
    """`--only`: the controls of this job; the others are recorded as left out of it."""
    if only is None:
        return calls
    kept: list[fid.Call] = []
    for name, models, controls, replies, extra in calls:
        chosen = [c for c in controls if c["id"] in only]
        for c in controls:
            if c["id"] not in only:
                not_run[str(c["id"])] = LEFT_OUT
        if chosen or name == "reference":
            kept.append((name, models, chosen, replies, extra))
    return kept


def run(args: argparse.Namespace) -> int:  # noqa: PLR0915 (one record, built in order)
    """`iproofs fidelity run --teacher-forced`. Prints the record's path; exit 4 when the pass
    did not run (a failed call), 0 otherwise (a failed control or prompt is recorded)."""
    from iproofs.level import level_digest, level_file, load_level, rung_prompts  # noqa: PLC0415
    from iproofs.provenance import file_digest, git_state  # noqa: PLC0415
    from iproofs.schema import SchemaRegistry  # noqa: PLC0415
    from iproofs.serialize import write_jsonl  # noqa: PLC0415
    from iproofs.teacher_forced import RUN_SCHEMA, raw_digest  # noqa: PLC0415

    root = fid._root()
    registry = SchemaRegistry.from_tree(root / "schema")
    level = load_level(root, args.level, registry=registry)
    rung = level.rung(args.rung)
    digest = level_digest(level_file(root, level.id))
    stream = fid._read_jsonl(args.prompts_dir / "prompts.jsonl")
    prompts = rung_prompts(stream, level, rung)
    reference_path, replies = _stored_reference(root, args, level, rung)
    work = args.work or Path("fidelity-work") / args.release / rung.id
    io = work / "io"
    io.mkdir(parents=True, exist_ok=True)
    prompts_digest = write_jsonl(io / "prompts-all.jsonl", prompts)
    stored = json.loads((reference_path.parent / fid.RUN_RECORD).read_text())
    if stored["prompts_digest"] != prompts_digest:
        raise IProofsError(ErrorKind.INTEGRITY, "these prompts are not the ones the stored "
                           "reference replies answer")  # fmt: skip
    n = min(args.limit, len(prompts)) if args.limit else len(prompts)
    write_jsonl(io / "prompts.jsonl", prompts[:n])
    write_jsonl(io / "reference.jsonl", replies[:n])
    out = tf_dir(args.results or root / "results", args.release, rung.id)
    out.mkdir(parents=True, exist_ok=True)
    name = args.name or args.system or (args.part or args.engine)
    commit_sha, dirty = git_state(root)
    record: dict[str, Any] = {
        "schema": RUN_SCHEMA,
        "name": name,
        "level": {"id": level.id, "digest": digest},
        "rung": rung.id,
        "release": args.release,
        "prompts_digest": prompts_digest,
        "prompts": n,
        "of": len(prompts),
        "reference": {"replies": f"results/{args.release}/fidelity/{rung.id}/reference.jsonl",
                      "digest": file_digest(reference_path)},
        "harness": {"git_commit": commit_sha, "git_dirty": dirty},
        "gpus": list(args.gpus),
        "slots": args.slots,
        "top_k": args.top_k,
    }  # fmt: skip
    if args.system:
        done = _system_calls(args, root, registry, level, rung, io, digest,
                             [{"prompt": p, "reply": r} for p, r in
                              zip(prompts[:n], replies[:n], strict=True)])  # fmt: skip
        if done["ok"]:
            _collect_system(io, out, args.system, n)
        said = done["said"]
        record |= {
            "kind": "system",
            "system": args.system,
            "workload": done["workload"],
            "engine": {"tool": args.system, "commit": said.get("upstream_commit"),
                       "image": done["image"]},
            "adapter": {k: said.get(k) for k in ("adapter_commit", "adapter_dirty")},
            "sessions": done["pin"]["sessions"],
            "upstream_commit_equal_to_sessions": True,
            "prover_files": done["prover_files"],
            "own_reply_check": done["own_reply_check"],
            "ids": [args.system] if done["ok"] else [],
            "failed_prompts": done["failed"],
            "not_run": {},
            "calls": done["records"],
        }  # fmt: skip
        ok = bool(done["ok"])
    else:
        system = fid.SYSTEMS[args.engine]
        containers, image = fid._containers(root, args, registry, system)
        info, said = fid._call(containers, image, io, {"subcommand": "info"}, None, args, "info")
        if info["exit_code"] != 0 or not said:
            raise IProofsError(ErrorKind.ADAPTER, f"{system} info failed: {info['stderr_tail']}")
        commit = str(said.get("upstream_commit"))
        pinned = fid._engine_pin(root, level, system)
        if pinned is not None and commit != pinned:
            raise IProofsError(ErrorKind.INTEGRITY, f"the image runs {args.engine} {commit}, "
                               f"the pin is {pinned}")  # fmt: skip
        common = {"subcommand": "prove", "rung": rung.id, "model_dir": "/models",
                  "dtype": rung.reference.dtype, "prompts_file": "/io/prompts.jsonl",
                  "output_tokens": level.request.output_tokens, "slots": args.slots,
                  "teacher_forced": {"replies_file": "/io/reference.jsonl",
                                     "top_k": args.top_k}}  # fmt: skip
        calls, not_run, reference_record = fid._plan(args, root, registry, rung)
        only = {x for x in args.only.split(",") if x} if args.only else None
        calls = _only([c for c in calls if c[0] != "file"], not_run, only)
        shutil.rmtree(io / "fidelity", ignore_errors=True)
        records = [info]
        for call, models, controls, _, extra in calls:
            job = {**common, **extra, "call": call, "controls": controls}
            rec, _ = fid._call(containers, image, io, job, models, args, call)
            records.append(rec)
            if call == "reference" and rec["exit_code"] != 0:
                break
        ids = _collect_engine(io, out, name)
        record |= {
            "kind": "engine",
            "engine": {"tool": args.engine,
                       "repo": fid.ENGINE_REPOS.get(args.engine, level.fidelity.engine.repo),
                       "commit": commit, "image": image},
            "adapter": {k: said.get(k) for k in ("adapter_commit", "adapter_dirty")},
            "model_files": reference_record,
            "ids": ids,
            "failed_prompts": [],
            "not_run": not_run,
            "calls": records,
        }  # fmt: skip
        ok = len(records) > 1 and all(r["exit_code"] == 0 for r in records[1:])
    commands = io / "commands.jsonl"
    if commands.is_file():
        from iproofs.log.redact import Redactor  # noqa: PLC0415

        (out / f"commands-{name}.jsonl").write_text(Redactor.from_host()(commands.read_text()))
    record["lists"] = {i: {"files": len(list((out / "raw" / i).glob("*.topk"))),
                           "digest": raw_digest(out / "raw" / i)}
                       for i in record["ids"] if (out / "raw" / i).is_dir()}  # fmt: skip
    print(fid._write_checked(registry, RUN_SCHEMA, out / f"run-{name}.json", record))
    return 0 if ok else 4


# ---------------------------------------------------------------- score


def _runs(tf: Path) -> list[tuple[str, dict[str, Any]]]:
    return [(p.name, json.loads(p.read_text())) for p in sorted(tf.glob("run-*.json"))]


def _tops(path: Path) -> tuple[tuple[tuple[int, ...] | None, ...], dict[int, str]]:
    tops: list[tuple[int, ...] | None] = []
    causes: dict[int, str] = {}
    for i, line in enumerate(x for x in path.read_text().splitlines() if x.strip()):
        doc = json.loads(line)
        if isinstance(doc, dict):
            tops.append(None)
            causes[i] = str(doc.get("failed"))
        else:
            tops.append(tuple(int(t) for t in doc))
    return tuple(tops), causes


def _pass_of(ident: str, tf: Path, runs: Sequence[tuple[str, dict[str, Any]]], ref: str,
             n: int, level_digest: str, prompts_digest: str, reference_digest: str
             ) -> tuple[Any, str | None]:  # fmt: skip
    """The stored pass of one id (its top tokens and the record of the run that made them), or
    the cause it has none. A run of other prompts, another level or another reference reply
    file is refused; a run of fewer than all the prompts (a trial) is not a pass."""
    from iproofs.teacher_forced import Pass  # noqa: PLC0415

    cause = "not run"
    for name, run in runs:
        # a run that left the control out says so; a run that leaves it to another part
        # (FI-9) names that part, which is the cause only while no part's run speaks of it
        if ident in run.get("not_run", {}) and (
            cause != LEFT_OUT or name.startswith("run-controls")
        ):
            cause = str(run["not_run"][ident])
        if ident not in run.get("ids", []):
            status = tf / f"status-{run['name']}.json"
            st = json.loads(status.read_text()) if status.is_file() else {}
            found = st.get("controls", {}).get(ident) or (st.get(ident) if ident == "reference"
                                                         else None)  # fmt: skip
            if isinstance(found, dict) and found.get("cause"):
                cause = str(found["cause"])
            continue
        if (run["level"]["digest"], run["prompts_digest"], run["reference"]["digest"]) != (
                level_digest, prompts_digest, reference_digest):  # fmt: skip
            raise IProofsError(ErrorKind.INTEGRITY, f"{name}: another level, other prompts or "
                               "other reference replies than this rung's")  # fmt: skip
        if run["prompts"] != n:
            cause = f"not run on every prompt: {name} ran {run['prompts']} of {run['of']}"
            continue
        tops, causes = _tops(tf / "top" / f"{ident}.jsonl")
        return Pass(ident, tops, causes), f"{ref}/{name}"
    return Pass(ident, None, {}, cause), None


def _measure(tf: Path, raw: Path, ids: Sequence[str], n: int) -> dict[str, Any]:
    """FI-12 from the lists under `raw` (one directory per id), written to kl.json."""
    from iproofs.teacher_forced import REST_FLOOR, TOP_K, measure_kl, raw_digest  # noqa: PLC0415

    reference = raw / "reference"
    if not any(reference.glob("*.topk")):
        raise IProofsError(ErrorKind.CONFIG, f"no lists of the reference under {reference}")
    engines = {i: measure_kl(reference, raw / i, n) for i in ids if (raw / i).is_dir()}
    return {"top_k": TOP_K, "rest_floor": REST_FLOOR,
            "reference": {"id": "reference", "lists": raw_digest(reference)},
            "engines": engines}  # fmt: skip


def score(args: argparse.Namespace) -> int:
    """`iproofs fidelity score --part teacher-forced [--raw DIR]`: prints the document's path."""
    from iproofs.fidelity import SignFlipRule  # noqa: PLC0415
    from iproofs.level import level_digest, level_file, load_beacon, load_level  # noqa: PLC0415
    from iproofs.provenance import file_digest  # noqa: PLC0415
    from iproofs.schema import SchemaRegistry  # noqa: PLC0415
    from iproofs.serialize import write_json  # noqa: PLC0415
    from iproofs.teacher_forced import SCHEMA, Entry, build, score_pass  # noqa: PLC0415

    root = fid._root()
    registry = SchemaRegistry.from_tree(root / "schema")
    level = load_level(root, args.level, registry=registry)
    rung = level.rung(args.rung)
    base = fid.fidelity_dir(root / "results", args.release, rung.id)
    tf = tf_dir(root / "results", args.release, rung.id)
    ref = f"results/{args.release}/{DIR}/{rung.id}"  # how records name it (RFC-0012)
    runs = _runs(tf)
    if not runs:
        raise IProofsError(ErrorKind.CONFIG, f"no run record under {tf}: run `iproofs fidelity "
                           "run --teacher-forced`")  # fmt: skip
    digest = level_digest(level_file(root, level.id))
    stored = json.loads((base / fid.RUN_RECORD).read_text())
    reference = fid._read_jsonl(base / "reference.jsonl")
    reference_digest = file_digest(base / "reference.jsonl")
    n = len(reference)
    ids = ["reference", *[c.id for c in rung.controls], *sorted(rung.workloads)]
    if args.raw is not None:
        write_json(tf / KL_VALUES, _measure(tf, args.raw, ids[1:], n))
    kl: dict[str, Any] = json.loads((tf / KL_VALUES).read_text()) if (tf / KL_VALUES).is_file() \
        else {"engines": {}}  # fmt: skip

    def entry(ident: str, spec: Mapping[str, object], system: bool) -> Entry:
        found, run = _pass_of(ident, tf, runs, ref, n, digest, str(stored["prompts_digest"]),
                              reference_digest)  # fmt: skip
        return Entry(spec, score_pass(found, reference, system=system), run,
                     kl["engines"].get(ident))  # fmt: skip

    beacon = load_beacon(root, level, registry=registry)
    rule = SignFlipRule(level.fidelity.alpha, level.fidelity.exact_up_to,
                        level.fidelity.resamples, str(beacon["randomness"]))  # fmt: skip
    controls = [entry(c.id, {"id": c.id, "kind": c.kind, "recipe": c.recipe,
                             "type": getattr(c, "type", None)}, False)
                for c in rung.controls]  # fmt: skip
    rows = [entry(s, {"id": s}, True) for s in sorted(rung.workloads)]
    own = entry("reference", {"id": "reference"}, False)
    header = {
        "level": {"id": level.id, "digest": digest},
        "rung": rung.id,
        "n": n,
        "positions": level.request.output_tokens,
        "prompts_digest": stored["prompts_digest"],
        "reference": {"replies": f"results/{args.release}/fidelity/{rung.id}/reference.jsonl",
                      "digest": reference_digest},
    }  # fmt: skip
    doc = build(header, rule, own, controls, rows, f"{ref}/{KL_VALUES}",
                "reference" in kl, COMPUTED_BY)  # fmt: skip
    errors = registry.errors(SCHEMA, doc)
    if errors:
        raise IProofsError(ErrorKind.INTERNAL, f"{SCORED} fails {SCHEMA}: {errors[0]}")
    write_json(tf / SCORED, doc)
    print(tf / SCORED)
    return 0
