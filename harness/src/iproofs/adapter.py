"""Adapter job and output files, container invocation, path safety (RFC-0005).

Everything an adapter writes is untrusted input (docs/spec/06-security.md). Messages name
container-side paths (`/io/...`) only, so no host path reaches a record.
"""

import os
import re
import stat
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

from iproofs.errors import ErrorKind, IProofsError
from iproofs.model import AdapterOut, System, load
from iproofs.schema import SchemaRegistry

MAX_OUT_JSON_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_PROOF_PARTS = 10_000
DEFAULT_MAX_PROOF_BYTES = 64 * 1024**3  # per part


def _adapter_error(message: str, step: str) -> IProofsError:
    return IProofsError(ErrorKind.ADAPTER, message, step=step)


@dataclass(frozen=True, slots=True)
class IoDirs:
    """Host directories mounted at `/io` and, except for verify, `/models`."""

    io: Path
    models: Path | None = None

    def host(self, container_path: str, step: str) -> Path:
        """Map an absolute container path to the host, refusing anything that escapes."""
        pure = PurePosixPath(container_path)
        if not pure.is_absolute() or ".." in pure.parts:
            raise _adapter_error(f"path {container_path!r} is not an absolute /io path", step)
        if pure.parts[1:2] == ("io",):
            root = self.io
        elif pure.parts[1:2] == ("models",) and self.models is not None:
            root = self.models
        else:
            raise _adapter_error(f"path {container_path!r} is outside /io and /models", step)
        host = root.joinpath(*pure.parts[2:])
        if not host.resolve().is_relative_to(root.resolve()):
            raise _adapter_error(f"path {container_path!r} escapes its mount", step)
        return host


def read_out(dirs: IoDirs, registry: SchemaRegistry, step: str) -> AdapterOut:
    """Read /io/out.json: size cap, stdlib parser, schema validation before any field is used."""
    path = dirs.io / "out.json"
    if not path.is_file() or path.is_symlink():
        raise _adapter_error("/io/out.json is missing or not a regular file", step)
    if path.stat().st_size > MAX_OUT_JSON_BYTES:
        raise _adapter_error(f"/io/out.json is larger than {MAX_OUT_JSON_BYTES} bytes", step)
    try:
        out = load(path, registry)
    except IProofsError as e:
        raise _adapter_error(f"/io/out.json is invalid: {e.message}", step) from e
    if not isinstance(out, AdapterOut) or out.subcommand != step:
        raise _adapter_error(f"/io/out.json is not an out file for {step}", step)
    for container_path in (
        *(out.verifier_files or ()),
        *(out.prover_files or ()),
        *(out.log_files or ()),
        *((out.binding_report,) if out.binding_report else ()),
    ):
        dirs.host(container_path, step)
    return out


def check_proofs(dirs: IoDirs, out: AdapterOut, system: System) -> list[str]:
    """INV-ADAPTER-6 and INV-ADAPTER-8 over /io/proofs after `prove`; returns warnings."""
    step = "prove"
    max_parts = system.max_proof_parts or DEFAULT_MAX_PROOF_PARTS
    max_bytes = system.max_proof_bytes or DEFAULT_MAX_PROOF_BYTES
    root = dirs.io / "proofs"
    warnings: list[str] = []
    released: dict[str, Path] = {}
    for entry in sorted(root.iterdir()) if root.is_dir() else []:
        name = f"/io/proofs/{entry.name}"
        mode = entry.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise _adapter_error(f"{name} is not a directory", step)
        if entry.name.startswith(".tmp-"):
            warnings.append(f"{name}: unreleased temporary proof directory ignored")
            continue
        released[entry.name] = entry
    listed = {p.proof_id: p for p in out.proofs or ()}
    if set(listed) != set(released):
        unlisted = sorted(set(released) - set(listed))
        unreleased = sorted(set(listed) - set(released))
        raise _adapter_error(
            f"INV-ADAPTER-6: released but not listed {unlisted}, listed but not released "
            f"{unreleased}",
            step,
        )
    for proof_id, directory in released.items():
        parts = sorted(directory.iterdir())
        if len(parts) > max_parts:
            raise _adapter_error(
                f"/io/proofs/{proof_id} has {len(parts)} parts, cap {max_parts}", step
            )
        names = set()
        for part in parts:
            where = f"/io/proofs/{proof_id}/{part.name}"
            mode = part.lstat().st_mode
            if not stat.S_ISREG(mode):  # symlinks, devices, fifos and subdirectories
                raise _adapter_error(f"INV-ADAPTER-8: {where} is not a regular file", step)
            if part.stat().st_size > max_bytes:
                raise _adapter_error(f"{where} is larger than the {max_bytes}-byte cap", step)
            names.add(part.name)
        if names != set(listed[proof_id].parts):
            raise _adapter_error(
                f"/io/proofs/{proof_id}: parts on disk {sorted(names)} != listed "
                f"{sorted(listed[proof_id].parts)}",
                step,
            )
    return warnings


# ---------------------------------------------------------------- container invocation

IMAGE_RE = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")
ADAPTER_UID = "10001"
VERIFY_MEMORY = "32g"
GPU_STEPS = frozenset({"info", "setup", "commit", "prove"})
STDERR_TAIL = 50


@dataclass(frozen=True, slots=True)
class StepResult:
    """One adapter call (RFC-0010 §Internal API). Samples and release times join in RFC-0011."""

    step: str
    started_mono_ns: int
    ended_mono_ns: int
    exit_code: int
    out: AdapterOut | None  # validated adapter-out document; None when the call failed
    stderr_tail: tuple[str, ...]


class ContainerRunner(Protocol):
    def run(  # noqa: PLR0913 (RFC-0010 §Internal API signature)
        self,
        image: str,
        subcommand: str,
        io_dir: Path,
        *,
        models_dir: Path | None,
        gpu: int | None,
        cpuset: str,
        mems: str,
        memory: str | None,
        timeout_s: float,
    ) -> StepResult: ...


def check_image(image: str) -> str:
    """INV-ADAPTER-3: images are referenced by digest, never by tag alone."""
    if not IMAGE_RE.fullmatch(image):
        raise IProofsError(ErrorKind.CONFIG, f"image {image!r} is not <repository>@sha256:<digest>")
    return image


def docker_create_argv(  # noqa: PLR0913 (mirrors ContainerRunner.run)
    image: str,
    subcommand: str,
    io_dir: Path,
    *,
    models_dir: Path | None,
    gpu: int | None,
    cpuset: str,
    mems: str,
    memory: str | None,
    tmpfs: str = "1g",
) -> list[str]:
    """`docker create` arguments for one adapter call (RFC-0005 §Container invocation)."""
    argv = [
        "docker",
        "create",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "4096",
        "--user",
        f"{ADAPTER_UID}:{ADAPTER_UID}",
        "--cpuset-cpus",
        cpuset,
        "--cpuset-mems",
        mems,
        "--tmpfs",
        f"/tmp:rw,size={tmpfs},mode=1777",
        "-v",
        f"{io_dir}:/io:rw",
    ]
    if subcommand == "verify":
        argv += ["--memory", VERIFY_MEMORY]  # never a GPU, never the weights
    else:
        if models_dir is not None:
            argv += ["-v", f"{models_dir}:/models:ro"]
        if gpu is not None and subcommand in GPU_STEPS:
            argv += ["--gpus", f"device={gpu}"]
        if memory is not None:
            argv += ["--memory", memory]
    return [*argv, check_image(image), subcommand, "/io/job.json", "/io/out.json"]


def _tail(text: str) -> tuple[str, ...]:
    return tuple(text.splitlines()[-STDERR_TAIL:])


class DockerRunner:
    """Runs adapter calls with the docker CLI; the only place a container is started."""

    def __init__(self, registry: SchemaRegistry, clock: Callable[[], int] = time.monotonic_ns):
        self.registry = registry
        self.clock = clock

    def run(  # noqa: PLR0913 (RFC-0010 §Internal API signature)
        self,
        image: str,
        subcommand: str,
        io_dir: Path,
        *,
        models_dir: Path | None,
        gpu: int | None,
        cpuset: str,
        mems: str,
        memory: str | None,
        timeout_s: float,
    ) -> StepResult:
        argv = docker_create_argv(
            image,
            subcommand,
            io_dir,
            models_dir=models_dir,
            gpu=gpu,
            cpuset=cpuset,
            mems=mems,
            memory=memory,
        )
        created = subprocess.run(argv, capture_output=True, text=True, check=False)
        if created.returncode != 0:
            raise IProofsError(
                ErrorKind.ENVIRONMENT,
                f"docker create failed: {created.stderr}",
                step=subcommand,
                exit_code=created.returncode,
            )
        cid = created.stdout.strip()  # host-local id: used here only, never recorded
        start = self.clock()
        try:
            done = subprocess.run(
                ["docker", "start", "--attach", cid],
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            subprocess.run(["docker", "kill", cid], capture_output=True, check=False)
            stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
            raise IProofsError(
                ErrorKind.TIMEOUT,
                f"{subcommand} exceeded {timeout_s} s",
                step=subcommand,
                last_lines=_tail(stderr),
            ) from e
        finally:
            end = self.clock()
            subprocess.run(["docker", "rm", "-f", cid], capture_output=True, check=False)
        out = read_out(IoDirs(io_dir), self.registry, subcommand) if done.returncode == 0 else None
        return StepResult(subcommand, start, end, done.returncode, out, _tail(done.stderr))


class InProcessRunner:
    """Runs an adapter entrypoint as a local process with the same job.json and out.json
    contract, mapping /io and /models through IPROOFS_IO and IPROOFS_MODELS (tests, CI)."""

    def __init__(
        self,
        entrypoint: Path,
        registry: SchemaRegistry,
        env: Mapping[str, str] | None = None,
        clock: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self.entrypoint = entrypoint
        self.registry = registry
        self.env = dict(env or {})
        self.clock = clock

    def run(  # noqa: PLR0913 (RFC-0010 §Internal API signature)
        self,
        image: str,
        subcommand: str,
        io_dir: Path,
        *,
        models_dir: Path | None,
        gpu: int | None,
        cpuset: str,
        mems: str,
        memory: str | None,
        timeout_s: float,
    ) -> StepResult:
        env = {**os.environ, **self.env, "IPROOFS_IO": str(io_dir)}
        if models_dir is not None and subcommand != "verify":
            env["IPROOFS_MODELS"] = str(models_dir)
        start = self.clock()
        try:
            done = subprocess.run(
                [sys.executable, str(self.entrypoint), subcommand, "/io/job.json", "/io/out.json"],
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            raise IProofsError(
                ErrorKind.TIMEOUT, f"{subcommand} exceeded {timeout_s} s", step=subcommand
            ) from e
        end = self.clock()
        out = read_out(IoDirs(io_dir), self.registry, subcommand) if done.returncode == 0 else None
        return StepResult(subcommand, start, end, done.returncode, out, _tail(done.stderr))
