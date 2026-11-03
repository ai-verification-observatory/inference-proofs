"""Command-line entry point: argparse, exit codes (RFC-0010 §Command line).

Handlers import their modules lazily, so `iproofs --help` loads no optional extra
(INV-ARCH-6) and starts fast (budget B-CLI-START).
"""

import argparse
import json
import subprocess
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from iproofs import __version__
from iproofs.errors import ErrorKind, IProofsError, Phase, exit_code

if TYPE_CHECKING:
    from iproofs.adapter import ContainerRunner
    from iproofs.runner import RunnerIdentity
    from iproofs.schema import SchemaRegistry

Handler = Callable[[argparse.Namespace], int]

# Commands whose implementation lands later; each names the issue that delivers it.
PENDING = {
    "prompts build": 48,
    "release freeze": 93,
    "release plan": 141,
    "site build": 96,
}
# Commands that check stored files report config, integrity and policy findings with exit 1.
CHECK_COMMANDS = {"validate", "derive", "reproduce compare"}


def harness_commit() -> str:
    """Return the git commit of the harness checkout, or "unknown" outside a checkout."""
    try:
        out = subprocess.run(
            ["git", "-C", str(Path(__file__).resolve().parent), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out.stdout.strip()


class _Version(argparse.Action):
    """Like argparse's version action, but asks git for the commit only when used."""

    def __call__(self, parser: argparse.ArgumentParser, *_: object) -> None:
        print(f"iproofs {__version__} ({harness_commit()})")
        parser.exit()


def pending(command: str) -> Handler:
    def handler(args: argparse.Namespace) -> int:
        raise IProofsError(
            ErrorKind.INTERNAL,
            f"`iproofs {command}` is not implemented yet (issue #{PENDING[command]})",
        )

    return handler


def build_parser() -> argparse.ArgumentParser:  # noqa: PLR0915 (one statement per argument)
    parser = argparse.ArgumentParser(
        prog="iproofs", description="Harness for the Inference Proofs benchmark."
    )
    parser.add_argument("--version", action=_Version, nargs=0, help="show version and commit")
    parser.add_argument("--log-level", choices=["debug", "info", "warning"], default="info")
    parser.add_argument("--quiet", action="store_true", help="no progress output on stderr")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    def command(
        name: str,
        help_text: str,
        parent: argparse._SubParsersAction | None = None,  # type: ignore[type-arg]
        full: str | None = None,
    ) -> argparse.ArgumentParser:
        p = (parent or sub).add_parser(name, help=help_text)
        p.set_defaults(handler=pending(full or name), command_name=full or name)
        return p

    p = command("validate", "run every CI check (RFC-0013) on the given paths")
    p.set_defaults(handler=validate)
    p.add_argument("paths", nargs="*", type=Path)
    p.add_argument("--all", action="store_true", help="every file, not only changed ones")
    p.add_argument("--changed-since", metavar="REF")
    p.add_argument("--format", choices=["text", "json"], default="text")

    p = command("derive", "compute derived metrics of a run directory (RFC-0004)")
    p.set_defaults(handler=derive)
    p.add_argument("run_dir", type=Path)
    p.add_argument("--check", action="store_true", help="recompute and compare bit for bit")

    p = command("run", "run jobs of one system on one workload (RFC-0010)")
    p.add_argument("--system", required=True)
    p.add_argument("--workload", required=True)
    p.add_argument("--profile", required=True)
    p.add_argument("--repetitions", type=int, default=3)
    p.add_argument("--results", type=Path, default=Path("results"))
    p.add_argument("--control-suite", action="store_true")
    p.add_argument("--provider", metavar="NAME")
    p.add_argument("--prompts-from", type=Path, metavar="RUN_DIR")
    p.add_argument("--allow-nonconforming", action="store_true")
    p.add_argument(
        "--keep-io",
        action="store_true",
        help="keep the job io directory, with proofs, in the run directory",
    )
    p.add_argument(
        "--in-process",
        action="store_true",
        help="run a test system's entrypoint as a local process instead of a container",
    )
    p.add_argument("--runner", metavar="HANDLE", help="the runner's declared handle (RFC-0007)")
    p.add_argument("--runner-org", metavar="ORG", help="the runner's declared organisation")
    p.add_argument(
        "--affiliated",
        metavar="SYSTEM",
        action="append",
        default=None,
        help="a system the runner is affiliated with (repeat for each)",
    )
    p.add_argument(
        "--image",
        metavar="IMAGE_ID",
        help="a locally built image by ID (sha256:<hex>), recorded as local/<system> with "
        "digest_kind config and never eligible for a release (RFC-0014)",
    )
    p.set_defaults(handler=run)

    p = command("controls", "run the negative-control suite against a run (RFC-0008)")
    p.set_defaults(handler=controls)
    p.add_argument("run_dir", type=Path, nargs="?")
    p.add_argument("--prepare-perturbed", metavar="WORKLOAD")

    p = command("machine-record", "print the machine record as JSON (RFC-0006)")
    p.add_argument("--selftest", action="store_true", help="run the RFC-0011 calibration checks")
    p.add_argument("--provider", metavar="NAME", help="the hosting provider, as declared")
    p.add_argument("--gpu", type=int, metavar="INDEX", help="the bound GPU (NVML index)")
    p.add_argument("--results", type=Path, default=Path("results"), help="for disk type and space")
    p.add_argument(
        "--probe-image",
        metavar="IMAGE_ID",
        help="the locally built systems/fake image (sha256:<hex>) whose probe the self-test runs",
    )
    p.set_defaults(handler=machine_record_command)

    p = command("fetch-model", "fetch a workload's weights and check every hash (RFC-0014)")
    p.add_argument("workload")
    p.set_defaults(handler=fetch_model)

    prompts = sub.add_parser("prompts", help="prompt sets (RFC-0003)")
    prompts_sub = prompts.add_subparsers(dest="prompts_command", required=True, metavar="ACTION")
    p = command(
        "build", "materialise a prompt set and print its digest", prompts_sub, "prompts build"
    )
    p.add_argument("workload")
    p.add_argument("--seed", required=True)

    reproduce = sub.add_parser("reproduce", help="reproduction records (RFC-0007)")
    reproduce_sub = reproduce.add_subparsers(
        dest="reproduce_command", required=True, metavar="ACTION"
    )
    p = command(
        "compare", "apply the RFC-0007 tolerance to two runs", reproduce_sub, "reproduce compare"
    )
    p.add_argument("orig_run", type=Path)
    p.add_argument("repro_run", type=Path)
    p.set_defaults(handler=reproduce_compare)

    release = sub.add_parser("release", help="benchmark releases (RFC-0009)")
    release_sub = release.add_subparsers(dest="release_command", required=True, metavar="ACTION")
    p = command("freeze", "write releases/<release>/index.json", release_sub, "release freeze")
    p.add_argument("release")
    p = command("plan", "project the run-campaign compute budget", release_sub, "release plan")
    p.add_argument("release")

    p = sub.add_parser("fmt")  # hidden maintenance command (RFC-0013 §G3)
    p.add_argument("paths", nargs="+", type=Path)
    p.set_defaults(handler=fmt, command_name="fmt")
    sub._choices_actions = [a for a in sub._choices_actions if a.dest != "fmt"]

    site = sub.add_parser("site", help="static site (RFC-0009)")
    site_sub = site.add_subparsers(dest="site_command", required=True, metavar="ACTION")
    p = command("build", "generate the static site", site_sub, "site build")
    p.add_argument("--out", type=Path, default=Path("site/_build"))
    return parser


def derive(args: argparse.Namespace) -> int:
    """`iproofs derive RUN_DIR [--check]`; without --check it prints, it never rewrites a run."""
    import json  # noqa: PLC0415

    from iproofs.validate import check_controls_summary, check_derived, repo_root  # noqa: PLC0415

    run_json = args.run_dir / "run.json"
    if not run_json.is_file():
        raise IProofsError(ErrorKind.CONFIG, f"{run_json} does not exist")
    root = repo_root(Path.cwd())  # runs may live outside the repository (CI temp dirs)
    findings = check_derived(run_json, root)
    if (args.run_dir / "controls.json").is_file():
        findings += check_controls_summary(args.run_dir / "controls.json", root)
    if args.check:
        for f in findings:
            print(f.line())
        print(f"derive: {len(findings)} failures", file=sys.stderr)
        return 1 if findings else 0
    doc = json.loads(run_json.read_text())
    derived = {k: v for k, v in doc.get("metrics", {}).items() if v.get("grade") == "derived"}
    print(json.dumps(derived, indent=2, sort_keys=True))
    return 1 if findings else 0


def validate(args: argparse.Namespace) -> int:
    """`iproofs validate`: the tree gates; one line per failure, exit 1 on any."""
    from iproofs.validate import repo_root  # noqa: PLC0415
    from iproofs.validate.tree import validate_tree  # noqa: PLC0415

    root = repo_root(Path.cwd())
    only = None if args.all or not args.paths else [_repo_path(root, p) for p in args.paths]
    findings = validate_tree(root, only=only, base_ref=args.changed_since)
    failures = [f for f in findings if not f.warning]
    for f in findings:
        if f.warning:  # stdout stays the RFC-0013 failure list; warnings never fail
            print(f.line(), file=sys.stderr)
    if args.format == "json":
        print(
            json.dumps(
                [
                    {
                        "gate": f.gate,
                        "path": f.path,
                        "pointer": f.pointer or None,
                        "line": None,
                        "rule": f.rule,
                        "message": f.message,
                        "hint": f.hint or None,
                    }
                    for f in failures
                ],
                indent=2,
            )
        )
    else:
        for f in failures:
            print(f.line())
    files = len({f.path.split(":")[0] for f in failures})  # G9 and G12 paths carry :line
    print(f"validate: {len(failures)} failures in {files} files", file=sys.stderr)
    return 1 if failures else 0


def _repo_path(root: Path, path: Path) -> str:
    full = path.resolve()
    if not full.is_relative_to(root):
        raise IProofsError(ErrorKind.CONFIG, f"{path} is outside the repository")
    return full.relative_to(root).as_posix() if full != root else ""


def fmt(args: argparse.Namespace) -> int:
    """Rewrite JSON files with the canonical writer (hidden; fixes FMT-1)."""
    from iproofs.serialize import write_json  # noqa: PLC0415

    for path in args.paths:
        write_json(path, json.loads(path.read_text()))
    return 0


def run(args: argparse.Namespace) -> int:
    """`iproofs run`: N repetitions; exit 4 when any job was recorded as failed."""
    from iproofs.runner import JobSpec, Runner, recorded_seed  # noqa: PLC0415
    from iproofs.validate import repo_root  # noqa: PLC0415
    from iproofs.workloads import load_workload  # noqa: PLC0415

    root = repo_root(Path.cwd())
    system_file = root / "systems" / args.system / "system.yaml"
    if not system_file.is_file():
        raise IProofsError(ErrorKind.CONFIG, f"unknown system {args.system!r}")
    containers, image, registry = _containers(system_file, args.in_process, args.image)
    wl = load_workload(args.workload, root=root, registry=registry)
    seed = recorded_seed(args.prompts_from, wl.id, wl.version) if args.prompts_from else None
    runner = Runner(
        containers,
        root=root,
        registry=registry,
        image=image,
        operator=_operator(root, args),
        provider=args.provider or "undeclared",
        progress=None if args.quiet else sys.stderr,
        log_level=args.log_level,
        allow_nonconforming=args.allow_nonconforming,
        replay_seed=seed,
        keep_io=args.keep_io,
    )
    spec = JobSpec(
        args.system,
        args.workload,
        wl.version,
        args.profile,
        1,
        args.control_suite,
        str(args.results),
        _release(root),
    )
    for recovered in runner.recover(Path(args.results)):
        print(f"recovered as failed: {recovered}", file=sys.stderr)
    dirs = runner.run_many(spec, args.repetitions)
    for d in dirs:
        print(d)
    statuses = [json.loads((d / "run.json").read_text())["status"] for d in dirs]
    return 4 if "failed" in statuses else 0


def _operator(root: Path, args: argparse.Namespace) -> "RunnerIdentity":
    """Who runs the job, self-declared (RFC-0007 §Tiers, Q3): options, else IPROOFS_RUNNER,
    IPROOFS_RUNNER_ORG and IPROOFS_RUNNER_SYSTEMS. Only the handle, the organisation and
    system ids are recorded (AGENTS.md rule 7)."""
    from iproofs.runner import RunnerIdentity  # noqa: PLC0415

    env = RunnerIdentity.from_env()
    systems = tuple(args.affiliated) if args.affiliated is not None else env.affiliated_systems
    known = {p.parent.name for p in (root / "systems").glob("*/system.yaml")}
    unknown = sorted(set(systems) - known)
    if unknown:
        raise IProofsError(ErrorKind.CONFIG, f"affiliated systems {unknown} do not exist")
    return RunnerIdentity(
        args.runner or env.handle,
        args.runner_org or env.organisation,
        tuple(dict.fromkeys(systems)),
    )


def _containers(
    system_file: Path, in_process: bool, image_id: str | None = None
) -> tuple["ContainerRunner", str | None, "SchemaRegistry"]:
    """The container runner for a system; in process only for test systems."""
    from iproofs.adapter import (  # noqa: PLC0415
        LOCAL_IMAGE_PREFIX,
        DockerRunner,
        InProcessRunner,
        check_image,
    )
    from iproofs.model import System, load  # noqa: PLC0415
    from iproofs.schema import SchemaRegistry  # noqa: PLC0415

    registry = SchemaRegistry.from_tree(system_file.parents[2] / "schema")
    system = load(system_file, registry)
    assert isinstance(system, System)
    if not in_process:
        local = f"{LOCAL_IMAGE_PREFIX}{system.name}@{image_id}" if image_id else None
        return DockerRunner(registry), local and check_image(local), registry
    if image_id:
        raise IProofsError(ErrorKind.CONFIG, "--image names a container image; drop --in-process")
    if system.kind != "test":
        raise IProofsError(ErrorKind.CONFIG, "--in-process is for test systems only")
    # a test system cannot contain its own commit; the harness passes the pinned one
    upstream = {"IPROOFS_FAKE_UPSTREAM": system.upstream.commit} if system.upstream else {}
    runner = InProcessRunner(system_file.parent / "entrypoint", registry, env=upstream)
    return runner, "local/in-process@sha256:" + "0" * 64, registry


def controls(args: argparse.Namespace) -> int:
    """`iproofs controls RUN_DIR`: add controls.json to a completed run kept with --keep-io."""
    from iproofs.runner import Runner, controls_for_run  # noqa: PLC0415
    from iproofs.validate import repo_root  # noqa: PLC0415

    if args.prepare_perturbed:
        raise IProofsError(ErrorKind.INTERNAL, "--prepare-perturbed is not implemented yet (#90)")
    if args.run_dir is None:
        raise IProofsError(ErrorKind.CONFIG, "give a RUN_DIR")
    root = repo_root(Path.cwd())
    system = json.loads((args.run_dir / "run.json").read_text())["system"]
    image_ref = json.loads((args.run_dir / "manifest.json").read_text())["system"]["image"]["ref"]
    containers, _, registry = _containers(
        root / "systems" / system / "system.yaml", image_ref.startswith("local/in-process@")
    )
    print(controls_for_run(Runner(containers, root=root, registry=registry), args.run_dir))
    return 0


def fetch_model(args: argparse.Namespace) -> int:
    """`iproofs fetch-model WORKLOAD`: download and verify the weights into the cache
    (RFC-0014 §Model fetch and verification); prints the read-only directory."""
    import os  # noqa: PLC0415

    from iproofs.runner import retry_fetch  # noqa: PLC0415
    from iproofs.schema import SchemaRegistry  # noqa: PLC0415
    from iproofs.validate import repo_root  # noqa: PLC0415
    from iproofs.workloads import default_cache, ensure_model, load_workload  # noqa: PLC0415

    root = repo_root(Path.cwd())
    wl = load_workload(args.workload, root=root, registry=SchemaRegistry.from_tree(root / "schema"))
    if wl.model.source.hub == "repository":
        raise IProofsError(ErrorKind.CONFIG, f"{wl.id} uses toy data in this repository")
    path = ensure_model(
        wl,
        default_cache(),
        retry=lambda op: retry_fetch(op, f"model {wl.id}"),
        token=os.environ.get("HF_TOKEN"),
    )
    print(path)
    return 0


def machine_record_command(args: argparse.Namespace) -> int:
    """`iproofs machine-record`: the RFC-0006 record of this host as JSON on stdout (CLI-3)."""
    from iproofs.log.redact import Redactor  # noqa: PLC0415
    from iproofs.provenance import Host, machine_record  # noqa: PLC0415
    from iproofs.serialize import dumps  # noqa: PLC0415

    record = machine_record(
        Host(),
        results=args.results if args.results.exists() else Path.cwd(),
        gpu_index=args.gpu,
        cpus={},
        mems=[],
        provider=args.provider or "undeclared",
        redact=Redactor.from_host(),
    )
    if not args.selftest:
        sys.stdout.write(dumps(record).decode())
        return 0
    import tempfile  # noqa: PLC0415

    from iproofs import selftest  # noqa: PLC0415

    image = f"local/fake@{args.probe_image}" if args.probe_image else None
    with tempfile.TemporaryDirectory() as work:
        checks = selftest.run_selftest(gpu_index=args.gpu, probe_image=image, work=Path(work))
    selftest.report(checks)
    result = selftest.as_record(checks)
    sys.stdout.write(dumps({"machine": record, "self_test": result}).decode())
    print(f"saved {selftest.save(args.results, result)}", file=sys.stderr)
    if not result["passed"]:
        failed = [c.name for c in checks if not c.passed]
        raise IProofsError(ErrorKind.ENVIRONMENT, f"self-test failed: {', '.join(failed)}")
    return 0


def reproduce_compare(args: argparse.Namespace) -> int:
    """`iproofs reproduce compare ORIG_RUN REPRO_RUN`: the RFC-0007 record; exit 1 unless the
    outcome is within_tolerance."""
    from iproofs.model import System, load  # noqa: PLC0415
    from iproofs.release import compare, write_reproduction  # noqa: PLC0415
    from iproofs.schema import SchemaRegistry  # noqa: PLC0415
    from iproofs.serialize import dumps  # noqa: PLC0415
    from iproofs.validate import governance, repo_root  # noqa: PLC0415

    root = repo_root(Path.cwd())
    registry = SchemaRegistry.from_tree(root / "schema")
    name = json.loads((args.orig_run / "run.json").read_text())["system"]
    system = load(root / "systems" / name / "system.yaml", registry)
    assert isinstance(system, System)
    maintainers = (root / governance.PATH).read_text("utf-8")
    orgs = [
        r.organisation
        for r in governance.parse(maintainers)
        if name in {s.strip() for s in r.systems.split(",")}
    ]
    record = compare(
        args.orig_run,
        args.repro_run,
        deterministic_proofs=bool(system.deterministic_proofs),
        maintainer_organisations=orgs,
    )
    path = write_reproduction(args.orig_run, record, registry)
    sys.stdout.write(dumps(record).decode())  # CLI-3: data on stdout through the single writer
    print(f"wrote {path}: {record['outcome']}", file=sys.stderr)
    return 0 if record["outcome"] == "within_tolerance" else 1


def _release(root: Path) -> str:
    """The release in force: the newest `reference/vX.Y.yaml`."""
    versions = sorted(
        (p.stem for p in (root / "reference").glob("v*.yaml")),
        key=lambda v: tuple(int(x) for x in v[1:].split(".")),
    )
    if not versions:
        raise IProofsError(ErrorKind.CONFIG, "no reference/<release>.yaml")
    return versions[-1]


def phase_of(command: str) -> Phase:
    return "validate" if command in CHECK_COMMANDS else "preflight"


def main(argv: list[str] | None = None) -> int:
    """Run one command; translate errors to RFC-0010 exit codes (argparse errors exit 2)."""
    args = build_parser().parse_args(argv)
    handler: Handler = args.handler
    try:
        return handler(args)
    except IProofsError as e:
        from iproofs.log.redact import Redactor  # noqa: PLC0415 (only on the error path)

        print(f"iproofs: {e.kind}: {Redactor.from_host()(e.message)}", file=sys.stderr)
        return exit_code(e.kind, phase_of(args.command_name))
    except Exception:  # every other exception is a harness bug
        from iproofs.log.redact import Redactor  # noqa: PLC0415

        print(Redactor.from_host()(traceback.format_exc()), file=sys.stderr)
        return exit_code(ErrorKind.INTERNAL, "preflight")
