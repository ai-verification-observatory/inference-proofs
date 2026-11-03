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

from iproofs import __version__
from iproofs.errors import ErrorKind, IProofsError, Phase, exit_code

Handler = Callable[[argparse.Namespace], int]

# Commands whose implementation lands later; each names the issue that delivers it.
PENDING = {
    "validate": 119,
    "controls": 89,
    "machine-record": 73,
    "fetch-model": 132,
    "prompts build": 48,
    "reproduce compare": 81,
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
        "--in-process",
        action="store_true",
        help="run a test system's entrypoint as a local process instead of a container",
    )
    p.set_defaults(handler=run)

    p = command("controls", "run the negative-control suite against a run (RFC-0008)")
    p.add_argument("run_dir", type=Path, nargs="?")
    p.add_argument("--prepare-perturbed", metavar="WORKLOAD")

    p = command("machine-record", "print the machine record as JSON (RFC-0006)")
    p.add_argument("--selftest", action="store_true", help="run the RFC-0011 calibration checks")

    p = command("fetch-model", "fetch a workload's weights and check every hash (RFC-0014)")
    p.add_argument("workload")

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

    release = sub.add_parser("release", help="benchmark releases (RFC-0009)")
    release_sub = release.add_subparsers(dest="release_command", required=True, metavar="ACTION")
    p = command("freeze", "write releases/<release>/index.json", release_sub, "release freeze")
    p.add_argument("release")
    p = command("plan", "project the run-campaign compute budget", release_sub, "release plan")
    p.add_argument("release")

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


def run(args: argparse.Namespace) -> int:
    """`iproofs run`: N repetitions; exit 4 when any job was recorded as failed."""
    from iproofs.adapter import ContainerRunner, DockerRunner, InProcessRunner  # noqa: PLC0415
    from iproofs.model import System, load  # noqa: PLC0415
    from iproofs.runner import JobSpec, Runner  # noqa: PLC0415
    from iproofs.schema import SchemaRegistry  # noqa: PLC0415
    from iproofs.validate import repo_root  # noqa: PLC0415

    unsupported = [
        flag
        for flag, on in (
            ("--control-suite", args.control_suite),
            ("--prompts-from", args.prompts_from),
            ("--provider", args.provider),
            ("--allow-nonconforming", args.allow_nonconforming),
        )
        if on
    ]
    if unsupported:
        raise IProofsError(
            ErrorKind.CONFIG, f"not implemented yet: {unsupported} (issues #89, #137, #73, #75)"
        )
    root = repo_root(Path.cwd())
    registry = SchemaRegistry.from_tree(root / "schema")
    system_file = root / "systems" / args.system / "system.yaml"
    if not system_file.is_file():
        raise IProofsError(ErrorKind.CONFIG, f"unknown system {args.system!r}")
    system = load(system_file, registry)
    assert isinstance(system, System)
    if args.in_process:
        if system.kind != "test":
            raise IProofsError(ErrorKind.CONFIG, "--in-process is for test systems only")
        # a test system cannot contain its own commit; the harness passes the pinned one
        upstream = {"IPROOFS_FAKE_UPSTREAM": system.upstream.commit} if system.upstream else {}
        containers: ContainerRunner = InProcessRunner(
            system_file.parent / "entrypoint", registry, env=upstream
        )
        image = "local/in-process@sha256:" + "0" * 64  # never started; recorded as such
    else:
        containers, image = DockerRunner(registry), None
    from iproofs.workloads import load_workload  # noqa: PLC0415

    wl = load_workload(args.workload, root=root, registry=registry)
    runner = Runner(
        containers,
        root=root,
        registry=registry,
        image=image,
        provider=args.provider or "undeclared",
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
    dirs = runner.run_many(spec, args.repetitions)
    failed = [
        d.name for d in dirs if json.loads((d / "run.json").read_text())["status"] == "failed"
    ]
    for d in dirs:
        print(d)
    return 4 if failed else 0


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
