"""Development install of the ref-serve-gguf adapter into a container started from the engine image
itself (docs/runbooks/hf-jobs.md §ref-serve-gguf from the engine image): the files the Dockerfile
copies, at the paths it copies them to, from this checkout, so the hosted runner's command (the
Dockerfile's ENTRYPOINT) finds them. Run as root, from the checkout, inside the engine image, with
its Python (standard library only):

    python3 systems/ref-serve-gguf/dev_install.py ENGINE_IMAGE [GPU]

ENGINE_IMAGE is the reference the provider started, <repository>@sha256:<digest>; it must be the
Dockerfile's FROM. The job command asserts that reference; what is checked here is the server
binary itself: `llama-server --version` must name the pinned build and commit, and that line is
recorded. With GPU (the index the runs bind), the server, run as uid 10001 with only that GPU
visible as the hosted runner gives it, must list exactly one CUDA device, so a CUDA build the
driver cannot run stops the job before the weights are fetched. Nothing here is a pinned adapter
image: a run from it records the image as
local/<ENGINE_IMAGE> (digest_kind config, `iproofs run --hosted --image ENGINE_IMAGE`), the adapter
commit as the checkout's, and in image_inputs the engine image and the adapter files at that
commit. It is never eligible for a release (RFC-0014 §Eligibility).
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OPT = Path("/opt")  # the tests install under a temporary directory instead
FETCH = OPT / "iproofs/fetch"
SITE = OPT / "ref-serve-gguf/site"
SERVER = Path("/app/llama-server")
SERVER_CWD = "/app"  # the image's WORKDIR, where the server finds its libraries (README)
BUILD = "build 12110, commit cd959bae9"  # `--version` of the pinned server (README §Engine)
BLOB = "https://github.com/ai-verification-observatory/inference-proofs/blob"
ADAPTER_UID = "10001"
# as the hosted runner starts a step (iproofs.adapter DROP_TO_ADAPTER); the tests run unprivileged
AS_ADAPTER = ["setpriv", f"--reuid={ADAPTER_UID}", f"--regid={ADAPTER_UID}", "--clear-groups"]
CUDA_DEVICE = re.compile(r"^\s+CUDA\d+: ", re.M)  # common/arg.cpp L1140 to L1150 at the pin


def fail(message: str) -> None:
    raise SystemExit(f"dev-install: {message}")


def dockerfile_from() -> str:
    """The final stage's base image, as the Dockerfile names it."""
    found = re.findall(r"^FROM (\S+)", (HERE / "Dockerfile").read_text(), re.M)
    return found[-1]


def locked() -> list[tuple[str, str, str]]:
    """(name, url, sha256 hex) of every input of inputs.lock (RFC-0014 B2)."""
    rows = []
    for line in (HERE / "inputs.lock").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            name, url, digest = line.split("\t")
            rows.append((name, url, digest.removeprefix("sha256:")))
    return rows


def fetch(url: str, dest: Path, sha256: str) -> None:
    """The fetch stage: the download, refused unless its sha256 is the locked one."""
    with urllib.request.urlopen(url, timeout=120) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != sha256:
        fail(f"{dest.name}: sha256 differs from inputs.lock")
    dest.write_bytes(data)


def git(*args: str) -> str:
    done = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True,
                          check=True)  # fmt: skip
    return done.stdout.strip()


def server_output(*args: str, env: dict[str, str] | None = None, drop: bool = False) -> str:
    """stdout and stderr of the server binary run with `args` from its directory."""
    argv = [*(AS_ADAPTER if drop else []), str(SERVER), *args]
    done = subprocess.run(argv, cwd=SERVER_CWD, capture_output=True, text=True, env=env,
                          timeout=300, check=False)  # fmt: skip
    return done.stdout + done.stderr


def server_version() -> str:
    """The `--version` line of the image's server, refused unless it is the pinned build."""
    out = server_output("--version")
    line = next((x.strip() for x in out.splitlines() if x.startswith("version:")), "")
    if BUILD not in line:
        fail(f"{SERVER} --version says {line or out.strip()[:200]!r}, not {BUILD!r}")
    return line


def check_gpu(gpu: str) -> None:
    """The server, as the adapter uid with only GPU visible, lists exactly one CUDA device."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("LLAMA_ARG_")}
    env |= {"CUDA_DEVICE_ORDER": "PCI_BUS_ID", "CUDA_VISIBLE_DEVICES": gpu}
    out = server_output("--list-devices", env=env, drop=True)
    print(out.rstrip())
    found = CUDA_DEVICE.findall(out)
    if len(found) != 1:
        fail(f"{len(found)} CUDA devices listed with CUDA_VISIBLE_DEVICES={gpu}, not 1")


def inputs_json(image: str, commit: str, dirty: bool, version: str) -> dict[str, object]:
    """B5 for a development install: the locked inputs, then the engine image and the adapter
    files at this commit, so the run's image_inputs say what ran."""
    inputs: list[dict[str, str]] = [
        {"name": name, "url": url, "digest": f"sha256:{sha}"} for name, url, sha in locked()
    ]
    repository, digest = image.split("@", 1)
    inputs.append({"name": "engine image (development install)",
                   "url": f"docker://{repository}", "digest": digest})  # fmt: skip
    for name in ("entrypoint", "system.yaml"):
        sha = hashlib.sha256((HERE / name).read_bytes()).hexdigest()
        inputs.append({"name": f"systems/ref-serve-gguf/{name} (development install)",
                       "url": f"{BLOB}/{commit}/systems/ref-serve-gguf/{name}",
                       "digest": f"sha256:{sha}"})  # fmt: skip
    toolchains = {"python": sys.version.split()[0], "llama.cpp": "b12110",
                  "llama-server --version": version,
                  "development_install": f"{commit}{' dirty' if dirty else ''}"}  # fmt: skip
    return {"inputs": inputs, "toolchains": toolchains}


def install(image: str) -> None:
    if image != dockerfile_from():
        fail(f"the job's image {image} is not the Dockerfile's FROM {dockerfile_from()}")
    version = server_version()
    print(f"dev-install: {version}")
    commit = git("rev-parse", "HEAD")
    dirty = bool(git("status", "--porcelain", "--", "systems/ref-serve-gguf"))
    FETCH.mkdir(parents=True, exist_ok=True)
    shutil.copy(HERE / "inputs.lock", FETCH / "inputs.lock")
    for name, url, sha in locked():
        fetch(url, FETCH / name, sha)
        print(f"dev-install: {name} sha256:{sha}")
    # the final stage: the Dockerfile's COPY destinations, then the wheel extracted (no pip)
    for src, dest, mode in (("entrypoint", "ref-serve-gguf/entrypoint", 0o755),
                            ("system.yaml", "iproofs/system.yaml", 0o644)):  # fmt: skip
        (OPT / dest).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(HERE / src, OPT / dest)
        (OPT / dest).chmod(mode)
    shutil.copy(REPO / "systems/fake/write_inputs.py", OPT / "iproofs/write_inputs.py")
    for name, _, _ in locked():
        if name.endswith(".whl"):
            with zipfile.ZipFile(FETCH / name) as wheel:
                wheel.extractall(SITE)
    (OPT / "iproofs/inputs.json").write_text(
        json.dumps(inputs_json(image, commit, dirty, version), sort_keys=True) + "\n"
    )
    for root in (OPT / "iproofs", OPT / "ref-serve-gguf"):  # readable by uid 10001
        for path in [root, *root.rglob("*")]:
            path.chmod(path.stat().st_mode | (0o555 if path.is_dir() else 0o444))
    print(f"dev-install: ref-serve-gguf from {commit} (dirty {str(dirty).lower()}) into {image}")


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        fail("usage: dev_install.py ENGINE_IMAGE [GPU]")
    if os.geteuid() != 0:
        fail("run as root (it writes /opt and adds uid 10001)")
    if not SERVER.is_file():
        fail(f"no {SERVER}: not the engine image")
    install(argv[1])
    if subprocess.run(["id", "-u", ADAPTER_UID], capture_output=True, check=False).returncode != 0:
        subprocess.run(["useradd", "--uid", ADAPTER_UID, "--no-create-home", "adapter"], check=True)
    sys.path.insert(0, str(SITE))
    import yaml  # noqa: PLC0415 (the wheel just extracted)

    print(f"dev-install: PyYAML {yaml.__version__}")
    if len(argv) == 3:
        check_gpu(argv[2])
        print(f"dev-install: one CUDA device, CUDA_VISIBLE_DEVICES={argv[2]}, uid {ADAPTER_UID}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
