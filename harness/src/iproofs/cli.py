"""Command-line entry point: argparse, exit codes (RFC-0010 §Command line).

Handlers import their modules lazily, so `iproofs --help` loads no optional extra
(INV-ARCH-6) and starts fast (budget B-CLI-START).
"""

import argparse
import json
import re
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
    from iproofs.model import ServingModel, Workload
    from iproofs.runner import Environment, RunnerIdentity
    from iproofs.schema import SchemaRegistry

Handler = Callable[[argparse.Namespace], int]

# Commands that check stored files report config, integrity and policy findings with exit 1.
CHECK_COMMANDS = {"validate", "derive", "release freeze"}


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
        p.set_defaults(command_name=full or name)
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
    p.add_argument("--allow-nonconforming", action="store_true", help=argparse.SUPPRESS)  # no-op
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
    p.add_argument("--gpu", type=int, metavar="INDEX", help="the bound GPU (NVML index)")
    p.add_argument(
        "--gpus",
        type=gpu_list,
        metavar="LIST",
        help="the bound GPUs of a serving profile, comma-separated NVML indices (RFC-0006 R6)",
    )
    p.add_argument(
        "--load",
        choices=["matched", "high"],
        default="matched",
        help="the load point of a production-serving job (RFC-0015 SRV-1)",
    )
    p.add_argument(
        "--sizing-batches",
        type=int,
        metavar="N",
        help="a sizing capture: a matched production-serving job of N batches (at least 2) "
        "while system.yaml's batches_per_session_run is null, for `iproofs serving "
        "size-session`; it joins no overhead (RFC-0015 SRV-1)",
    )
    p.add_argument(
        "--hosted",
        action="store_true",
        help="the provider started this container from the system's pinned image; run each "
        "step in it as a process (RFC-0006 §Hosted execution)",
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
        "digest_kind config and never eligible for a release (RFC-0014); with --hosted, also "
        "the reference <repository>@sha256:<hex> of the image the provider started when the "
        "adapter was installed into it from this checkout, recorded as local/<reference>",
    )
    p.set_defaults(handler=run)

    p = command("controls", "run the negative-control suite against a run (RFC-0008)")
    p.set_defaults(handler=controls)
    p.add_argument("run_dir", type=Path, nargs="?")
    p.add_argument(
        "--prepare-perturbed",
        metavar="WORKLOAD",
        help="commit the C3 and P1 perturbed weights once per workload and release (with "
        "--system and --profile)",
    )
    p.add_argument("--system", help="with --prepare-perturbed")
    p.add_argument("--profile", help="with --prepare-perturbed")
    p.add_argument("--results", type=Path, default=Path("results"))
    p.add_argument("--image", metavar="IMAGE_ID", help="a locally built image by ID")
    p.add_argument("--in-process", action="store_true", help="test systems only")
    p.add_argument(
        "--only",
        metavar="ID[,ID...]",
        action="append",
        help="run these controls only and write a part for --merge (RFC-0008 §Split suites)",
    )
    p.add_argument(
        "--seed",
        metavar="SEED",
        help="with --only: the seed you expect, 64-bit hex (0x...) or decimal; it must be the "
        "one of RUN_DIR/controls-seed.json",
    )
    p.add_argument(
        "--draw-seed",
        action="store_true",
        help="draw the split suite's seed once into RUN_DIR/controls-seed.json (RFC-0008 SPLIT-1)",
    )
    p.add_argument(
        "--merge",
        metavar="PART",
        nargs="+",
        type=Path,
        help="write RUN_DIR/controls.json from parts that cover the suite once",
    )
    p.add_argument(
        "--hosted",
        action="store_true",
        help="this container is the run's pinned image; run each call in it as a process",
    )
    p.add_argument(
        "--gpu", type=int, metavar="INDEX", help="the bound GPU, for prover-side controls"
    )
    p.add_argument("--provider", metavar="NAME", help="the hosting provider, as declared")

    p = command("machine-record", "print the machine record as JSON (RFC-0006)")
    p.add_argument("--selftest", action="store_true", help="run the RFC-0011 calibration checks")
    p.add_argument("--provider", metavar="NAME", help="the hosting provider, as declared")
    p.add_argument("--gpu", type=int, metavar="INDEX", help="the bound GPU (NVML index)")
    p.add_argument("--gpus", type=gpu_list, metavar="LIST", help="every bound GPU (RFC-0006 R6)")
    p.add_argument("--results", type=Path, default=Path("results"), help="for disk type and space")
    p.add_argument("--hosted", action="store_true", help="the record of a hosted container")
    p.add_argument(
        "--probe-image",
        metavar="IMAGE_ID",
        help="the locally built systems/fake image (sha256:<hex>) whose probe the self-test runs",
    )
    p.set_defaults(handler=machine_record_command)

    p = command("fetch-model", "fetch a workload's weights and check every hash (RFC-0014)")
    p.add_argument("workload", nargs="?")
    p.add_argument(
        "--serving",
        metavar="RECORD",
        help="fetch a production-serving record's files instead (workloads/serving/RECORD.yaml,"
        " RFC-0014 SM-2)",
    )
    p.add_argument(
        "--no-weights",
        type=Path,
        metavar="DIR",
        help="with --serving: fetch every file of the record but the .safetensors weights into"
        " DIR, each checked as SM-2 checks it, for a tokenizer check before the weights",
    )
    p.add_argument(
        "--headers-only",
        action="store_true",
        help="fetch no weights: recompute a computed weight width from the GGUF headers alone,"
        " by range reads at the pinned revision (RFC-0003 WB-5), and print it as JSON",
    )
    p.set_defaults(handler=fetch_model)

    prompts = sub.add_parser("prompts", help="prompt sets (RFC-0003)")
    prompts_sub = prompts.add_subparsers(dest="prompts_command", required=True, metavar="ACTION")
    p = command(
        "build", "materialise a prompt set and print its digest", prompts_sub, "prompts build"
    )
    p.add_argument("workload")
    p.add_argument("--seed", required=True, help="the 64-bit seed, decimal or 0x hex")
    p.add_argument("--out", type=Path, default=Path("prompts.jsonl"), help="where to write")
    p.set_defaults(handler=prompts_build)

    serving = sub.add_parser("serving", help="production-serving records (RFC-0015 SRV-6)")
    serving_sub = serving.add_subparsers(dest="serving_command", required=True, metavar="ACTION")
    p = command(
        "check-mirror",
        "check that the mirror's files are the publisher's, by git blob id (RFC-0014 SM-3)",
        serving_sub,
        "serving check-mirror",
    )
    p.add_argument("record")
    p.set_defaults(handler=serving_check_mirror)
    p = command(
        "pin",
        "write a record's file list, digest and shape from the two tree listings (network)",
        serving_sub,
        "serving pin",
    )
    p.add_argument("record")
    p.add_argument("--include", action="append", required=True, metavar="GLOB",
                   help="mirror paths to pin (repeat)")  # fmt: skip
    p.set_defaults(handler=serving_pin)
    p = command(
        "size-session",
        "compute batches_per_session_run from a stored matched capture (RFC-0015 SRV-1)",
        serving_sub,
        "serving size-session",
    )
    p.add_argument("run_dir", type=Path)
    p.set_defaults(handler=serving_size_session)

    release = sub.add_parser("release", help="benchmark releases (RFC-0009)")
    release_sub = release.add_subparsers(dest="release_command", required=True, metavar="ACTION")
    p = command("freeze", "write releases/<release>/index.json", release_sub, "release freeze")
    p.add_argument("release")
    p.set_defaults(handler=release_freeze)
    p = command("plan", "project the run-campaign compute budget", release_sub, "release plan")
    p.add_argument("release")
    p.add_argument("--repetitions", type=int, default=3, help="repetitions per configuration")
    p.set_defaults(handler=release_plan)

    p = sub.add_parser("fmt")  # hidden maintenance command (RFC-0013 §G3)
    p.add_argument("paths", nargs="+", type=Path)
    p.set_defaults(handler=fmt, command_name="fmt")
    sub._choices_actions = [a for a in sub._choices_actions if a.dest != "fmt"]

    site = sub.add_parser("site", help="static site (RFC-0009)")
    site_sub = site.add_subparsers(dest="site_command", required=True, metavar="ACTION")
    p = command("build", "generate the static site", site_sub, "site build")
    p.add_argument("--out", type=Path, default=None,
                   help="output folder (default: the repository's web/)")  # fmt: skip
    p.set_defaults(handler=site_build)

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
    from iproofs.runner import JobSpec, Runner, recorded_claims, recorded_seed  # noqa: PLC0415
    from iproofs.serialize import load_yaml  # noqa: PLC0415
    from iproofs.validate import repo_root  # noqa: PLC0415
    from iproofs.workloads import load_workload  # noqa: PLC0415

    root = repo_root(Path.cwd())
    system_file = root / "systems" / args.system / "system.yaml"
    if not system_file.is_file():
        raise IProofsError(ErrorKind.CONFIG, f"unknown system {args.system!r}")
    containers, image, registry = _containers(
        system_file, args.in_process, args.image, hosted=args.hosted
    )
    wl = load_workload(args.workload, root=root, registry=registry)
    if args.gpus and args.gpu is not None:
        raise IProofsError(ErrorKind.CONFIG, "give --gpu or --gpus, not both")
    seed = recorded_seed(args.prompts_from, wl.id, wl.version) if args.prompts_from else None
    role = load_yaml(system_file).get("reference_role")
    recompute = role == "recompute"
    if role == "serve" and args.prompts_from:  # before any step or weight
        _replay_steady_rule(args.prompts_from, wl.shape.batch_size)
    if args.sizing_batches is not None and role != "serve":  # RFC-0015 SRV-1, before any step
        raise IProofsError(ErrorKind.CONFIG, "--sizing-batches is for production serving "
                           "(RFC-0015 SRV-1)")  # fmt: skip
    if recompute and not args.prompts_from:  # RFC-0015 RC-1, before any step
        raise IProofsError(ErrorKind.CONFIG, f"{args.system} needs --prompts-from a system run")
    claims = recorded_claims(args.prompts_from) if args.prompts_from and recompute else None
    runner = Runner(
        containers,
        root=root,
        registry=registry,
        image=image,
        operator=_operator(root, args),
        provider=args.provider or "undeclared",
        progress=None if args.quiet else sys.stderr,
        log_level=args.log_level,
        prompts_from=args.prompts_from.resolve().name if args.prompts_from else None,
        replay_seed=seed,
        claims=claims,
        keep_io=args.keep_io,
        env=_environment(
            args.gpu,
            args.hosted,
            _prover_cpus(root, args.profile, registry) if args.gpu is not None or args.gpus else 24,
            _verifier_cpus(root, _release(root), registry),
            args.gpus,
        ),
        hosted=args.hosted,
        load=args.load,
        source_prompt_digest=_prompt_digest(args.prompts_from) if args.prompts_from else None,
        sizing_batches=args.sizing_batches,
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


def _environment(
    gpu: int | None,
    hosted: bool,
    n_prover: int,
    n_verifier: int = 8,
    gpus: list[int] | None = None,
) -> "Environment | None":
    """The GPU host for `--gpu`, binding `n_prover` prover CPUs and `n_verifier` verifier
    CPUs, or a serving host for `--gpus` (RFC-0006 R6); without either, the CPU-only host."""
    from iproofs.provenance import Host  # noqa: PLC0415
    from iproofs.runner import GpuEnvironment, ServingEnvironment  # noqa: PLC0415

    if gpus:
        return ServingEnvironment(gpus, Host(hosted=hosted), n_prover)
    if gpu is None:
        return None
    return GpuEnvironment(gpu, Host(hosted=hosted), n_prover, n_verifier)


def _verifier_cpus(root: Path, release: str, registry: "SchemaRegistry") -> int:
    """The verifier CPUs every host binds: verifier-cpu's `cpu.logical_cpus` in the release's
    reference file, so a GPU host and a verifier-only host bind the same count (RFC-0008
    SPLIT-3); 8, the default of `select_cpus`, for a release without that profile."""
    from iproofs.model import VerifierProfile, load_reference  # noqa: PLC0415

    if not (root / "reference" / f"{release}.yaml").is_file():
        return 8
    profile = load_reference(release, root, registry).profiles.get("verifier-cpu")
    return profile.cpu.logical_cpus if isinstance(profile, VerifierProfile) else 8


def gpu_list(text: str) -> list[int]:
    """`--gpus 0,1,2,3`: distinct NVML indices."""
    try:
        found = [int(x) for x in text.split(",") if x.strip()]
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"{text!r} is not a list of GPU indices") from e
    if not found or len(set(found)) != len(found) or min(found) < 0:
        raise argparse.ArgumentTypeError(f"{text!r}: distinct non-negative GPU indices")
    return found


def _replay_steady_rule(run_dir: Path, batch_size: int) -> None:
    """RFC-0004 INV-SCOPE-5 and INV-DERIVE-2 (f): at a batch size above 1, a system run recorded
    without `workload.steady_rule` joins no overhead, so a production-serving job replaying it
    could feed none; it is refused (`config`) before the engine starts or a weight is fetched."""
    from iproofs.derive import STEADY_RULE  # noqa: PLC0415

    manifest = run_dir / "manifest.json"
    workload = json.loads(manifest.read_text()).get("workload", {}) if manifest.is_file() else {}
    if batch_size > 1 and workload.get("steady_rule") != STEADY_RULE:
        raise IProofsError(ErrorKind.CONFIG, f"{run_dir} was recorded without workload."
                           f"steady_rule {STEADY_RULE!r} at batch size {batch_size} (before "
                           "RFC-0004 INV-SCOPE-5): it joins no overhead, so replaying it would "
                           "feed none; replay a run recorded with the rule")  # fmt: skip


def _prompt_digest(run_dir: Path) -> str | None:
    """The `--prompts-from` run's prompt set digest (RFC-0015 SRV-8), read from its manifest."""
    manifest = run_dir / "manifest.json"
    if not manifest.is_file():
        return None
    digest = json.loads(manifest.read_text()).get("workload", {}).get("prompt_set_digest")
    return str(digest) if digest else None


def _prover_cpus(root: Path, profile: str, registry: "SchemaRegistry") -> int:
    """The prover CPUs a job on `profile` binds: its `cpu.logical_cpus_on_gpu_numa_node`
    (RFC-0006 §CPU and memory selection), from the release's reference file or the CI one; 24,
    the default, for a profile in neither (the runner refuses it with `config`)."""
    from iproofs.model import ProverProfile, load_reference  # noqa: PLC0415

    for release in (_release(root), "ci"):
        if (root / "reference" / f"{release}.yaml").is_file():
            found = load_reference(release, root, registry).profiles.get(profile)
            if isinstance(found, ProverProfile):
                return found.cpu.logical_cpus_on_gpu_numa_node
    return 24


def entrypoint_argv(dockerfile: str) -> list[str]:
    """The image's ENTRYPOINT, exec form, from the system's Dockerfile (the last one wins)."""
    found = re.findall(r"^ENTRYPOINT\s+(\[.*\])\s*$", dockerfile, re.M)
    if not found:
        raise IProofsError(ErrorKind.CONFIG, "the Dockerfile has no exec-form ENTRYPOINT")
    argv = json.loads(found[-1])
    assert isinstance(argv, list)
    return [str(a) for a in argv]


def local_image(system: str, image: str, *, hosted: bool) -> str:
    """`--image` as recorded (RFC-0014: an image never pushed is `local/...` with digest_kind
    `config`, never eligible for a release). An image ID gives `local/<system>@<id>`. In hosted
    mode a full reference names the image the provider started, into which the job installed
    the adapter from this checkout (RFC-0014 development install): it is recorded as
    `local/<reference>`, so the record names that image and never an adapter image that was
    not built; the adapter commit is the checkout's. Ported from ref-serve-gguf (258fcb3)."""
    from iproofs.adapter import LOCAL_IMAGE_PREFIX, check_image  # noqa: PLC0415

    if "@" in image:
        if not hosted:
            raise IProofsError(
                ErrorKind.CONFIG,
                f"--image {image!r}: a full image reference only with --hosted; docker runs a "
                "local build by its ID (sha256:<hex>)",
            )
        return check_image(f"{LOCAL_IMAGE_PREFIX}{image.removeprefix(LOCAL_IMAGE_PREFIX)}")
    return check_image(f"{LOCAL_IMAGE_PREFIX}{system}@{image}")


def _containers(
    system_file: Path, in_process: bool, image_id: str | None = None, *, hosted: bool = False
) -> tuple["ContainerRunner", str | None, "SchemaRegistry"]:
    """The container runner for a system; in process only for test systems."""
    from iproofs.adapter import (  # noqa: PLC0415
        DockerRunner,
        HostedRunner,
        InProcessRunner,
        image_environment,
    )
    from iproofs.model import System, load  # noqa: PLC0415
    from iproofs.schema import SchemaRegistry  # noqa: PLC0415

    registry = SchemaRegistry.from_tree(system_file.parents[2] / "schema")
    system = load(system_file, registry)
    assert isinstance(system, System)
    if hosted:  # the provider started the pinned image, or the local build named by --image
        if in_process:
            raise IProofsError(ErrorKind.CONFIG, "--hosted runs an image; drop --in-process")
        argv = entrypoint_argv((system_file.parent / "Dockerfile").read_text())
        environ = image_environment(Path("/proc/1/environ").read_text())
        local = local_image(system.name, image_id, hosted=True) if image_id else None
        return HostedRunner(argv, registry, environ), local, registry
    if not in_process:
        local = local_image(system.name, image_id, hosted=False) if image_id else None
        return DockerRunner(registry), local, registry
    if image_id:
        raise IProofsError(ErrorKind.CONFIG, "--image names a container image; drop --in-process")
    if system.kind != "test":
        raise IProofsError(ErrorKind.CONFIG, "--in-process is for test systems only")
    # a test system cannot contain its own commit; the harness passes the pinned one
    upstream = {"IPROOFS_FAKE_UPSTREAM": system.upstream.commit} if system.upstream else {}
    runner = InProcessRunner(system_file.parent / "entrypoint", registry, env=upstream)
    return runner, "local/in-process@sha256:" + "0" * 64, registry


def controls(args: argparse.Namespace) -> int:
    """`iproofs controls RUN_DIR`: add controls.json to a completed run kept with --keep-io;
    with --draw-seed, the split suite's seed record; with --only, one part of the suite, with
    that seed; and with --merge, controls.json from the parts (RFC-0008 §Split suites)."""
    from iproofs.controls import parse_control_seed  # noqa: PLC0415
    from iproofs.runner import Runner, controls_for_run, draw_seed, merge_controls  # noqa: PLC0415
    from iproofs.schema import SchemaRegistry  # noqa: PLC0415
    from iproofs.validate import repo_root  # noqa: PLC0415

    if args.prepare_perturbed:
        return _prepare_perturbed(args)
    if args.run_dir is None:
        raise IProofsError(ErrorKind.CONFIG, "give a RUN_DIR")
    root = repo_root(Path.cwd())
    alone = args.only or args.seed or args.hosted or args.gpu is not None
    if args.merge or args.draw_seed:
        flag = "--merge" if args.merge else "--draw-seed"
        if alone or (args.merge and args.draw_seed):
            raise IProofsError(ErrorKind.CONFIG, f"{flag} takes RUN_DIR only, and --merge parts")
        registry_ = SchemaRegistry.from_tree(root / "schema")
        if args.draw_seed:
            path = draw_seed(registry_, args.run_dir)
            print(path, json.loads(path.read_text())["control_seed"])
        else:
            print(merge_controls(registry_, args.run_dir, args.merge))
        return 0
    if args.seed is not None and not args.only:  # a whole suite draws its own (RFC-0008 §Seeds)
        raise IProofsError(ErrorKind.CONFIG, "--seed goes with --only; a whole suite draws one")
    seed = parse_control_seed(args.seed) if args.seed is not None else None
    run = json.loads((args.run_dir / "run.json").read_text())
    image_ref = json.loads((args.run_dir / "manifest.json").read_text())["system"]["image"]["ref"]
    system_file = root / "systems" / run["system"] / "system.yaml"
    in_process = image_ref.startswith("local/in-process@") and not args.hosted
    containers, _, registry = _containers(system_file, in_process, hosted=args.hosted)
    if args.hosted:
        _check_hosted_image(system_file, registry, image_ref)
    env: Environment | None = None  # without --gpu or --hosted: the CPU-only host
    if args.gpu is not None:
        n_prover = _prover_cpus(root, run["profile"], registry)
        n_verifier = _verifier_cpus(root, run["release"], registry)
        env = _environment(args.gpu, args.hosted, n_prover, n_verifier)
    elif args.hosted:
        env = _verifier_host(root, run["release"], registry)
    runner = Runner(
        containers,
        root=root,
        registry=registry,
        env=env,
        hosted=args.hosted,
        provider=args.provider or "undeclared",
        progress=None if args.quiet else sys.stderr,
    )
    print(controls_for_run(runner, args.run_dir, seed=seed, only=args.only))
    return 0


def _check_hosted_image(system_file: Path, registry: "SchemaRegistry", image_ref: str) -> None:
    """A hosted container is the one the provider started from the system's pinned image, so
    it can verify a run only if the run used that image (RFC-0006 §Hosted execution)."""
    from iproofs.model import System, load  # noqa: PLC0415

    system = load(system_file, registry)
    assert isinstance(system, System)
    pinned = f"{system.image.repository}@{system.image.digest}" if system.image else None
    if image_ref != pinned:
        raise IProofsError(
            ErrorKind.CONFIG,
            f"--hosted runs in the pinned image {pinned}, but the run used {image_ref}",
        )


def _verifier_host(root: Path, release: str, registry: "SchemaRegistry") -> "Environment":
    """`controls --hosted` without `--gpu`: a CPU host that binds the release's verifier-cpu
    CPUs to every verify call and runs no prove (RFC-0008 §Split suites)."""
    from iproofs.model import VerifierProfile, load_reference  # noqa: PLC0415
    from iproofs.provenance import Host  # noqa: PLC0415
    from iproofs.runner import VerifierEnvironment  # noqa: PLC0415

    profile = load_reference(release, root, registry).profiles.get("verifier-cpu")
    if not isinstance(profile, VerifierProfile):
        raise IProofsError(ErrorKind.CONFIG, f"reference/{release}.yaml has no verifier-cpu")
    return VerifierEnvironment(Host(hosted=True), profile.cpu.logical_cpus)


def _prepare_perturbed(args: argparse.Namespace) -> int:
    """`iproofs controls --prepare-perturbed WORKLOAD --system S --profile P`: prints the path
    of the stored perturbed commitment record (RFC-0008 C3 and P1)."""
    from iproofs.runner import JobSpec, Runner, prepare_perturbed  # noqa: PLC0415
    from iproofs.validate import repo_root  # noqa: PLC0415
    from iproofs.workloads import default_cache, load_workload  # noqa: PLC0415

    if not (args.system and args.profile) or args.run_dir is not None:
        raise IProofsError(
            ErrorKind.CONFIG, "--prepare-perturbed takes --system and --profile, not a RUN_DIR"
        )
    if (
        args.only
        or args.seed
        or args.merge
        or args.draw_seed
        or args.hosted
        or args.gpu is not None
    ):
        raise IProofsError(
            ErrorKind.CONFIG,
            "--prepare-perturbed takes no --only, --seed, --merge, --draw-seed, --hosted or --gpu",
        )
    root = repo_root(Path.cwd())
    system_file = root / "systems" / args.system / "system.yaml"
    if not system_file.is_file():
        raise IProofsError(ErrorKind.CONFIG, f"unknown system {args.system!r}")
    containers, image, registry = _containers(system_file, args.in_process, args.image)
    wl = load_workload(args.prepare_perturbed, root=root, registry=registry)
    runner = Runner(containers, root=root, registry=registry, image=image)
    spec = JobSpec(args.system, wl.id, wl.version, args.profile, 1, False, str(args.results),
                   _release(root))  # fmt: skip
    print(prepare_perturbed(runner, spec, default_cache()))
    return 0


def prompts_build(args: argparse.Namespace) -> int:
    """`iproofs prompts build WORKLOAD --seed SEED`: the prompt set a job with that seed uses,
    written as prompts.jsonl; prints {digest, count, seed} as JSON (RFC-0003, CLI-3)."""
    from iproofs.provenance import prompt_set_digest  # noqa: PLC0415
    from iproofs.schema import SchemaRegistry  # noqa: PLC0415
    from iproofs.serialize import dumps, write_jsonl  # noqa: PLC0415
    from iproofs.validate import repo_root  # noqa: PLC0415
    from iproofs.workloads import (  # noqa: PLC0415
        default_cache,
        load_workload,
        materialise_prompts,
        tokenizer_file,
        tokenizers_version,
    )

    try:
        seed = int(args.seed, 0)
    except ValueError as e:
        raise IProofsError(ErrorKind.CONFIG, f"--seed {args.seed!r} is not a number") from e
    if not 0 <= seed < 2**64:
        raise IProofsError(ErrorKind.CONFIG, "--seed must fit in 64 bits")
    root = repo_root(Path.cwd())
    wl = load_workload(args.workload, root=root, registry=SchemaRegistry.from_tree(root / "schema"))
    tokenizer = tokenizer_file(root, wl, default_cache())
    prompts = materialise_prompts(root, wl, tokenizer.parent, seed)
    write_jsonl(args.out, prompts)
    result = {
        "workload": {"id": wl.id, "version": wl.version},
        "seed": f"0x{seed:016x}",
        "count": len(prompts),
        "digest": prompt_set_digest(args.out),
        "tokenizers_version": tokenizers_version(),
    }
    sys.stdout.write(dumps(result).decode())
    return 0


def release_freeze(args: argparse.Namespace) -> int:
    """`iproofs release freeze RELEASE`: RFC-0009 §Freeze algorithm; writes
    releases/<release>/index.json and prints its path. A failing step exits 1."""
    from iproofs.release import freeze  # noqa: PLC0415
    from iproofs.schema import SchemaRegistry  # noqa: PLC0415
    from iproofs.serialize import write_json  # noqa: PLC0415
    from iproofs.validate import repo_root  # noqa: PLC0415
    from iproofs.validate.tree import validate_tree  # noqa: PLC0415

    root = repo_root(Path.cwd())
    registry = SchemaRegistry.from_tree(root / "schema")

    def gates(paths: list[str]) -> list[str]:
        found = validate_tree(root, only=paths)
        return [f.line() for f in found if f.gate in GATES_G2_G7 and not f.warning]

    index = freeze(args.release, root, registry, gates)
    errors = registry.errors("release-index/1", index)
    if errors:
        raise IProofsError(ErrorKind.INTERNAL, f"index.json fails release-index/1: {errors[0]}")
    out = root / "releases" / args.release / "index.json"
    write_json(out, index)
    print(out.relative_to(root))
    return 0


GATES_G2_G7 = {"G2", "G3", "G4", "G5", "G6", "G7"}


def site_build(args: argparse.Namespace) -> int:
    """`iproofs site build [--out DIR]`: the public site of the newest frozen release
    (RFC-0009 §Site), into the repository's `web/` unless `--out` names another folder; prints
    the number of pages written."""
    from iproofs.site import build  # noqa: PLC0415
    from iproofs.validate import repo_root  # noqa: PLC0415

    root = repo_root(Path.cwd())
    if args.out is None:
        out = root / "web"
    else:
        out = args.out if args.out.is_absolute() else Path.cwd() / args.out
    pages = build(root, out)
    print(f"{len(pages)} pages in {out}")
    return 0


def release_plan(args: argparse.Namespace) -> int:
    """`iproofs release plan RELEASE`: the P-CAMPAIGN projection as JSON on stdout, from the
    systems' external figures; never written to results/ or releases/ (docs/spec/08)."""
    from iproofs.derive import project_campaign  # noqa: PLC0415
    from iproofs.serialize import dumps  # noqa: PLC0415
    from iproofs.validate import repo_root  # noqa: PLC0415

    if args.repetitions < 3:
        raise IProofsError(ErrorKind.CONFIG, "a release needs at least 3 repetitions (RFC-0004)")
    projection = project_campaign(args.release, repo_root(Path.cwd()), args.repetitions)
    sys.stdout.write(dumps(projection).decode())
    return 0


def fetch_model(args: argparse.Namespace) -> int:
    """`iproofs fetch-model WORKLOAD`: download and verify the weights into the cache
    (RFC-0014 §Model fetch and verification); prints the read-only directory."""
    import os  # noqa: PLC0415

    from iproofs.runner import retry_fetch  # noqa: PLC0415
    from iproofs.schema import SchemaRegistry  # noqa: PLC0415
    from iproofs.validate import repo_root  # noqa: PLC0415
    from iproofs.workloads import (  # noqa: PLC0415
        default_cache,
        ensure_model,
        load_workload,
        tokenizer_file,
    )

    root = repo_root(Path.cwd())
    registry = SchemaRegistry.from_tree(root / "schema")
    if args.serving is not None:
        return _fetch_serving(root, registry, args.serving, args.no_weights)
    if args.no_weights is not None:
        raise IProofsError(ErrorKind.CONFIG, "--no-weights is for --serving RECORD")
    if args.workload is None:
        raise IProofsError(ErrorKind.CONFIG, "give a WORKLOAD or --serving RECORD")
    wl = load_workload(args.workload, root=root, registry=registry)
    if wl.model.source.hub == "repository":
        raise IProofsError(ErrorKind.CONFIG, f"{wl.id} uses toy data in this repository")
    if args.headers_only:
        return _weight_bits_from_headers(wl)
    path = ensure_model(
        wl,
        default_cache(),
        retry=lambda op: retry_fetch(op, f"model {wl.id}"),
        token=os.environ.get("HF_TOKEN"),
    )
    if wl.model.tokenizer_source is not None:  # a run builds its prompts offline, so fetch it now
        retry_fetch(lambda: tokenizer_file(root, wl, default_cache()), f"tokenizer {wl.id}")
    print(path)
    return 0


def _serving_record(root: Path, registry: "SchemaRegistry", record: str) -> "ServingModel":
    from iproofs.model import ServingModel, load  # noqa: PLC0415
    from iproofs.serving import SERVING_DIR  # noqa: PLC0415

    path = root / SERVING_DIR / f"{record}.yaml"
    if not path.is_file():
        raise IProofsError(ErrorKind.CONFIG, f"no serving record {path.relative_to(root)}")
    doc = load(path, registry)
    assert isinstance(doc, ServingModel)
    return doc


def _fetch_serving(
    root: Path, registry: "SchemaRegistry", record: str, no_weights: Path | None = None
) -> int:
    """`iproofs fetch-model --serving RECORD [--no-weights DIR]` (RFC-0014 SM-2): HF_TOKEN
    reaches only the files the record fetches from the publisher (`source: publisher`)."""
    import os  # noqa: PLC0415

    from iproofs.runner import retry_fetch  # noqa: PLC0415
    from iproofs.serving import (  # noqa: PLC0415
        ensure_serving_model,
        fetch_no_weights,
        sm1_problems,
    )
    from iproofs.workloads import default_cache, hub_download  # noqa: PLC0415

    doc = _serving_record(root, registry, record)
    problems = sm1_problems(doc)
    if problems:
        raise IProofsError(ErrorKind.CONFIG, problems[0])
    if no_weights is not None:
        fetch_no_weights(doc, no_weights, download=hub_download,
                         retry=lambda op: retry_fetch(op, f"serving files {doc.id}"),
                         token=os.environ.get("HF_TOKEN"))  # fmt: skip
        print(no_weights)
        return 0
    path = ensure_serving_model(doc, default_cache(), download=hub_download,
                                retry=lambda op: retry_fetch(op, f"serving model {doc.id}"),
                                token=os.environ.get("HF_TOKEN"))  # fmt: skip
    print(path)
    return 0


def _hub_get(url: str) -> bytes:
    from iproofs.workloads import http_get  # noqa: PLC0415

    return http_get(url, timeout_s=120.0)


def serving_check_mirror(args: argparse.Namespace) -> int:
    """`iproofs serving check-mirror RECORD` (SM-3): one line per problem, exit 1 on any."""
    from iproofs.schema import SchemaRegistry  # noqa: PLC0415
    from iproofs.serving import check_mirror  # noqa: PLC0415
    from iproofs.validate import repo_root  # noqa: PLC0415

    root = repo_root(Path.cwd())
    doc = _serving_record(root, SchemaRegistry.from_tree(root / "schema"), args.record)
    problems = check_mirror(doc, _hub_get)
    for line in problems:
        print(line)
    rev = doc.model.revision[:12]
    print(f"serving check-mirror {doc.id}: {len(doc.model.files)} files, {len(problems)} "
          f"problems ({doc.model.source.repo}@{rev} against "
          f"{doc.publisher.release.repo}@{doc.publisher.release.revision[:12]})",
          file=sys.stderr)  # fmt: skip
    return 1 if problems else 0


def serving_pin(args: argparse.Namespace) -> int:
    """`iproofs serving pin RECORD --include GLOB...`: rewrite the record's `model.files`,
    `digest`, `vocab_size` and `shape` from the mirror's and the publisher's tree listings and
    the mirror's config.json (never typed, AGENTS.md rule 3); prints the record path."""
    from iproofs.serialize import load_yaml  # noqa: PLC0415
    from iproofs.serving import SERVING_DIR, pin_record  # noqa: PLC0415
    from iproofs.validate import repo_root  # noqa: PLC0415

    root = repo_root(Path.cwd())
    path = root / SERVING_DIR / f"{args.record}.yaml"
    if not path.is_file():
        raise IProofsError(ErrorKind.CONFIG, f"no serving record {path.relative_to(root)}")
    text = pin_record(path.read_text(), dict(load_yaml(path)), args.include, _hub_get)
    path.write_text(text)
    print(path)
    return 0


def serving_size_session(args: argparse.Namespace) -> int:
    """`iproofs serving size-session RUN_DIR` (RFC-0015 SRV-1): the `batches_per_session_run`
    of the capture's (workload, GPU count), computed from its run.json and manifest.json and
    the workload record's `batches_per_session` (never typed, AGENTS.md rule 3). Prints JSON;
    the expected seconds are projections from the capture (grade projected)."""
    from iproofs.schema import SchemaRegistry  # noqa: PLC0415
    from iproofs.serialize import dumps  # noqa: PLC0415
    from iproofs.serving import session_size  # noqa: PLC0415
    from iproofs.validate import repo_root  # noqa: PLC0415
    from iproofs.workloads import load_workload  # noqa: PLC0415

    docs = []
    for name in ("run.json", "manifest.json"):
        path = args.run_dir / name
        try:
            docs.append(json.loads(path.read_text()))
        except (OSError, ValueError) as e:
            raise IProofsError(ErrorKind.CONFIG, f"{path}: not a readable run record ({e})") from e
    run, manifest = docs
    root = repo_root(Path.cwd())
    wl_ref = manifest.get("workload") or {}
    wl = load_workload(str(wl_ref.get("id")), wl_ref.get("version"), root=root,
                       registry=SchemaRegistry.from_tree(root / "schema"))  # fmt: skip
    size = session_size(run, manifest, wl.shape.batches_per_session)
    source = f"{args.run_dir.resolve().name}/run.json#/metrics/prove_steady_seconds"
    out = {
        "batches_per_session_run": size.batches,
        "workload": size.workload,
        "load_point": "matched",
        "gpus": size.gpus,
        "batch_size": size.batch_size,
        "prompt_count_run": size.prompt_count,
        "steady_batches": size.steady_batches,
        "target_prove_steady_seconds": size.target_s,
        "capture": {
            "run_id": size.run_id,
            "profile": run.get("profile"),
            "batches": size.capture_batches,
            "sizing_capture": (manifest.get("workload") or {}).get("sizing_capture") is True,
            "prove_steady_seconds": size.capture_steady_s,
            "prove_session_seconds": size.capture_session_s,
            "seconds_per_steady_batch": size.seconds_per_batch,
            "grade": "measured",
            "source": source,
        },
        "expected": {
            "prove_steady_seconds": size.expected_steady_s,
            "prove_session_seconds": size.expected_session_s,
            "grade": "projected",
            "basis": f"the capture's seconds per steady batch x {size.batches - 1} steady "
            f"batches; the session adds {size.batches - size.capture_batches} batches to the "
            "capture's prove.session",
        },
    }
    sys.stdout.write(dumps(out).decode())
    print(f"system.yaml {size.workload} matched gpus {size.gpus}: batches_per_session_run: "
          f"{size.batches}  # iproofs serving size-session on {size.run_id}",
          file=sys.stderr)  # fmt: skip
    return 0


def _weight_bits_from_headers(wl: "Workload") -> int:
    """`fetch-model --headers-only`: the RFC-0003 WB-5 recheck from range reads of the GGUF
    headers, without the weights (whose digests a header read cannot check: the revision is
    pinned and each file's size must equal the listed bytes). Prints the result as JSON."""
    from iproofs.runner import retry_fetch  # noqa: PLC0415
    from iproofs.serialize import dumps  # noqa: PLC0415
    from iproofs.workloads import computed_bits, hub_sources  # noqa: PLC0415

    result = retry_fetch(lambda: computed_bits(wl, hub_sources(wl)), f"headers {wl.id}")
    wb = wl.precision.weight_bits
    assert wb is not None  # computed_bits refuses a record without a computed width
    active = result.active_weights
    out = {
        "workload": wl.id,
        "method": wb.method,
        "bits": result.bits,
        "recorded_bits": wb.bits,
        "active_weights": int(active) if active.denominator == 1 else float(active),
        "active_per_token": wl.model.parameters.active_per_token,
        "total_weights": result.total_weights,
        "expert_count": result.expert_count,
        "expert_used_count": result.expert_used_count,
    }
    sys.stdout.write(dumps(out).decode())
    return 0


def machine_record_command(args: argparse.Namespace) -> int:
    """`iproofs machine-record`: the RFC-0006 record of this host as JSON on stdout (CLI-3)."""
    from iproofs.log.redact import Redactor  # noqa: PLC0415
    from iproofs.provenance import Host, machine_record  # noqa: PLC0415
    from iproofs.serialize import dumps  # noqa: PLC0415

    if args.gpus and args.gpu is not None:
        raise IProofsError(ErrorKind.CONFIG, "give --gpu or --gpus, not both")
    record = machine_record(
        Host(hosted=args.hosted),
        results=args.results if args.results.exists() else Path.cwd(),
        gpu_index=args.gpus[0] if args.gpus else args.gpu,
        cpus={},
        mems=[],
        provider=args.provider or "undeclared",
        redact=Redactor.from_host(),
        gpu_indices=args.gpus or (),
    )
    if not args.selftest:
        sys.stdout.write(dumps(record).decode())
        return 0
    import tempfile  # noqa: PLC0415

    from iproofs import selftest  # noqa: PLC0415
    from iproofs.validate import repo_root  # noqa: PLC0415

    image = f"local/fake@{args.probe_image}" if args.probe_image else None
    entry = repo_root(Path.cwd()) / "systems/fake/entrypoint" if args.hosted else None
    with tempfile.TemporaryDirectory(dir=Path.cwd()) as work:  # not /tmp, the adapter's
        checks = selftest.run_selftest(  # a serving host's first bound GPU (RFC-0006 R6)
            gpu_index=args.gpus[0] if args.gpus else args.gpu,
            probe_image=image,
            work=Path(work),
            hosted_probe=entry,
        )
    selftest.report(checks)
    result = selftest.as_record(checks)
    sys.stdout.write(dumps({"machine": record, "self_test": result}).decode())
    print(f"saved {selftest.save(args.results, result)}", file=sys.stderr)
    if not result["passed"]:
        failed = [c.name for c in checks if not c.passed]
        raise IProofsError(ErrorKind.ENVIRONMENT, f"self-test failed: {', '.join(failed)}")
    return 0


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
