"""Development install of an adapter into a container started from its engine image (RFC-0014
§Development install, generic form; first written for branch ref-serve-gguf, commit d842275).

When an adapter's own image is not yet pullable by a hosted provider, a development job starts
from the public engine image the adapter's Dockerfile is built `FROM` and installs the adapter
from the checkout it runs: the files the Dockerfile copies, at the paths it copies them to, and
the inputs of its `inputs.lock`, each checked by its sha256. A system's `dev_install.py` calls
`install()` with its own engine check. Standard library only (the engine image's Python).

Nothing here is a pinned adapter image: a run from it records the image as `local/<engine image>`
(digest_kind config, `iproofs run --hosted --image <engine image>`), the adapter commit as the
checkout's, and in `image_inputs` the engine image and the adapter files at that commit. It is
never eligible for a release (RFC-0014 §Eligibility).
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OPT = Path("/opt")  # the tests install under a temporary directory instead
BLOB = "https://github.com/ai-verification-observatory/inference-proofs/blob"
ADAPTER_UID = "10001"
ENV_PREFIXES = ("VLLM_", "NCCL_", "CUDA_", "TORCH_")  # RFC-0015 SRV-3
BINDING_ENV = ("CUDA_VISIBLE_DEVICES", "CUDA_DEVICE_ORDER")  # set by the harness (RFC-0006)
Get = Callable[[str, Mapping[str, str]], bytes]


def fail(message: str) -> None:
    raise SystemExit(f"dev-install: {message}")


def dockerfile_from(dockerfile: str) -> str:
    """The final stage's base image, as the Dockerfile names it."""
    found = re.findall(r"^FROM (\S+)", dockerfile, re.M)
    if not found:
        fail("the Dockerfile has no FROM")
    return str(found[-1])


def copies(dockerfile: str) -> list[tuple[str, str]]:
    """(source under systems/, destination) of each COPY of the final stage from the build
    context (not `--from=`), in order."""
    final = dockerfile[dockerfile.rindex("\nFROM ") :]
    out = []
    for line in final.splitlines():
        parts = line.split()
        if parts[:1] == ["COPY"] and not any(p.startswith("--from") for p in parts):
            out.append((parts[-2], parts[-1]))
    return out


def locked(text: str) -> list[tuple[str, str, str]]:
    """(name, url, sha256 hex) of every input of inputs.lock (RFC-0014 B2)."""
    rows = []
    for line in text.splitlines():
        if line.strip() and not line.startswith("#"):
            name, url, digest = line.split("\t")
            rows.append((name, url, digest.removeprefix("sha256:")))
    return rows


def http_get(url: str, headers: Mapping[str, str]) -> bytes:
    request = urllib.request.Request(url, headers=dict(headers))
    with urllib.request.urlopen(request, timeout=120) as response:
        data: bytes = response.read()
    return data


def fetch(url: str, dest: Path, sha256: str, get: Get = http_get) -> None:
    """The fetch stage: the download, refused unless its sha256 is the locked one."""
    data = get(url, {})
    if hashlib.sha256(data).hexdigest() != sha256:
        fail(f"{dest.name}: sha256 differs from inputs.lock")
    dest.write_bytes(data)


INDEX = ("application/vnd.oci.image.index.v1+json, "
         "application/vnd.docker.distribution.manifest.list.v2+json")  # fmt: skip
MANIFEST = ("application/vnd.oci.image.manifest.v1+json, "
            "application/vnd.docker.distribution.manifest.v2+json")  # fmt: skip


def image_env(image: str, get: Get = http_get, arch: str = "amd64") -> list[str]:
    """The image's own ENV, read from its config by digest through Docker Hub's anonymous
    registry API (`docker.io/<repo>@sha256:<digest>`): the reference the engine environment is
    checked against (RFC-0015 SRV-3)."""
    ref, digest = image.split("@", 1)
    repo = ref.removeprefix("docker.io/")
    if "/" not in repo or "." in repo.split("/", 1)[0]:
        fail(f"{image}: only docker.io images are read here")
    token_url = ("https://auth.docker.io/token?service=registry.docker.io"
                 f"&scope=repository:{repo}:pull")  # fmt: skip
    token = json.loads(get(token_url, {}))["token"]
    auth = {"Authorization": f"Bearer {token}"}
    base = f"https://registry-1.docker.io/v2/{repo}"
    doc = json.loads(get(f"{base}/manifests/{digest}", {**auth, "Accept": f"{INDEX}, {MANIFEST}"}))
    if "manifests" in doc:  # a list: this architecture's manifest
        mine = [m for m in doc["manifests"] if m.get("platform", {}).get("architecture") == arch]
        if not mine:
            fail(f"{image} has no {arch} manifest")
        doc = json.loads(get(f"{base}/manifests/{mine[0]['digest']}", {**auth, "Accept": MANIFEST}))
    config = json.loads(get(f"{base}/blobs/{doc['config']['digest']}", auth))
    return [str(e) for e in config.get("config", {}).get("Env") or []]


def env_problems(environ: Mapping[str, str], image: Sequence[str]) -> list[str]:
    """SRV-3: every VLLM_*, NCCL_*, CUDA_* and TORCH_* variable of this process is the image's
    own, or the harness's binding; a job that sets another changes the engine."""
    own = dict(e.split("=", 1) for e in image if "=" in e)
    return [f"{k}={v}" for k, v in sorted(environ.items())
            if k.startswith(ENV_PREFIXES) and k not in BINDING_ENV and own.get(k) != v]  # fmt: skip


def git(*args: str) -> str:
    done = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True,
                          check=True)  # fmt: skip
    return done.stdout.strip()


def inputs_json(system: str, image: str, files: Sequence[str], commit: str, dirty: bool,
                toolchains: Mapping[str, str], lock: str) -> dict[str, object]:  # fmt: skip
    """B5 for a development install: the locked inputs, then the engine image and the adapter
    files at this commit, so the run's image_inputs say what ran."""
    inputs: list[dict[str, str]] = [
        {"name": name, "url": url, "digest": f"sha256:{sha}"} for name, url, sha in locked(lock)
    ]
    repository, digest = image.split("@", 1)
    inputs.append({"name": "engine image (development install)",
                   "url": f"docker://{repository}", "digest": digest})  # fmt: skip
    for name in files:
        sha = hashlib.sha256((REPO / "systems" / name).read_bytes()).hexdigest()
        url = f"{BLOB}/{commit}/systems/{name}"
        inputs.append({"name": f"systems/{name} (development install)", "url": url,
                       "digest": f"sha256:{sha}"})  # fmt: skip
    built = f"{commit}{' dirty' if dirty else ''}"
    tools = {"python": sys.version.split()[0], **toolchains, "development_install": built}
    return {"inputs": inputs, "toolchains": tools}


def install(
    system: str,
    image: str,
    *,
    toolchains: Mapping[str, str],
    env: Sequence[str] | None = None,
    get: Get = http_get,
    opt: Path = OPT,
) -> Path:
    """Put the system's Dockerfile COPY sources at their destinations under `opt`, fetch its
    locked inputs, write inputs.json and the image ENV (`image_env.json`), and make it all
    readable by uid 10001. Returns the inputs.json path. `env` is the image's ENV (read from the
    registry when None)."""
    here = REPO / "systems" / system
    dockerfile = (here / "Dockerfile").read_text()
    if image != dockerfile_from(dockerfile):
        fail(f"the job's image {image} is not the Dockerfile's FROM {dockerfile_from(dockerfile)}")
    image_vars = image_env(image, get) if env is None else list(env)
    if bad := env_problems(os.environ, image_vars):
        fail(f"engine environment not set by the image's ENV: {bad} (RFC-0015 SRV-3)")
    commit = git("rev-parse", "HEAD")
    dirty = bool(git("status", "--porcelain", "--", f"systems/{system}"))
    lock = (here / "inputs.lock").read_text()
    fetch_dir = opt / "iproofs/fetch"
    fetch_dir.mkdir(parents=True, exist_ok=True)
    (fetch_dir / "inputs.lock").write_text(lock)
    for name, url, sha in locked(lock):
        fetch(url, fetch_dir / name, sha, get)
    copied = []
    for src, dest in copies(dockerfile):
        target = opt / dest.removeprefix("/opt/")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / "systems" / src, target)
        target.chmod(0o755 if os.access(REPO / "systems" / src, os.X_OK) else 0o644)
        copied.append(src)
    out = opt / "iproofs/inputs.json"
    doc = inputs_json(system, image, copied, commit, dirty, toolchains, lock)
    doc["image_env"] = image_vars
    out.write_text(json.dumps(doc, sort_keys=True) + "\n")
    engine = sorted(e for e in image_vars if e.startswith(ENV_PREFIXES))
    (opt / "iproofs/image_env.json").write_text(json.dumps(engine) + "\n")
    for root in {opt / d.removeprefix("/opt/").split("/", 1)[0] for _, d in copies(dockerfile)}:
        for path in [root, *root.rglob("*")]:  # readable by uid 10001
            path.chmod(path.stat().st_mode | (0o555 if path.is_dir() else 0o444))
    print(f"dev-install: {system} from {commit} (dirty {str(dirty).lower()}) into {image}")
    return out


def ensure_adapter_user() -> None:
    if subprocess.run(["id", "-u", ADAPTER_UID], capture_output=True, check=False).returncode:
        subprocess.run(["useradd", "--uid", ADAPTER_UID, "--no-create-home", "adapter"],
                       check=True)  # fmt: skip
