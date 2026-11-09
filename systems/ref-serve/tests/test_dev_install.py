"""The development install (systems/_dev/install.py, systems/ref-serve/dev_install.py) on CPU,
with fixture registry responses and fake subprocess results: no network, no GPU."""

import hashlib
import importlib.machinery
import importlib.util
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

HERE = Path(__file__).resolve().parent
SYSTEMS = HERE.parents[1]
IMAGE = ("docker.io/vllm/vllm-openai@sha256:"
         "befccf0e7e4089aa23926bb6f887a85c0d46c2a99e6de5c5ffdf5cb7957c5b34")  # fmt: skip
ENV = ["PATH=/usr/bin", "CUDA_VERSION=13.0.2", "VLLM_USAGE_SOURCE=production-docker-image",
       "VLLM_BUILD_COMMIT=5df63a7203cdb9328d824a27b682e77c7b9928be"]  # fmt: skip


def module(path: Path, name: str) -> ModuleType:
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


@pytest.fixture
def dev() -> ModuleType:
    return module(SYSTEMS / "_dev/install.py", "install")


@pytest.fixture
def ref(dev: ModuleType, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(SYSTEMS / "_dev"))
    return module(SYSTEMS / "ref-serve/dev_install.py", "dev_install")


def registry(env: list[str]) -> Any:
    """Docker Hub's anonymous token, the manifest list, the amd64 manifest and the config."""

    def get(url: str, headers: Mapping[str, str]) -> bytes:
        if url.startswith("https://auth.docker.io/token"):
            return json.dumps({"token": "t"}).encode()
        assert headers.get("Authorization") == "Bearer t"
        if url.endswith(
            "/manifests/sha256:befccf0e7e4089aa23926bb6f887a85c0d46c2a99e6de5c5ffdf5cb7957c5b34"
        ):
            return json.dumps({"manifests": [
                {"digest": "sha256:arm", "platform": {"architecture": "arm64"}},
                {"digest": "sha256:amd", "platform": {"architecture": "amd64"}},
            ]}).encode()  # fmt: skip
        if url.endswith("/manifests/sha256:amd"):
            return json.dumps({"config": {"digest": "sha256:cfg"}}).encode()
        if url.endswith("/blobs/sha256:cfg"):
            return json.dumps({"config": {"Env": env}}).encode()
        raise AssertionError(url)

    return get


def test_image_env_from_the_registry(dev: ModuleType) -> None:
    assert dev.image_env(IMAGE, registry(ENV)) == ENV
    with pytest.raises(SystemExit, match=r"only docker\.io images"):
        dev.image_env("ghcr.io/x/y@sha256:" + "0" * 64, registry(ENV))
    with pytest.raises(SystemExit, match="no arm64 manifest"):
        dev.image_env(IMAGE, _no_arch(), arch="arm64")


def _no_arch() -> Any:
    def get(url: str, headers: Mapping[str, str]) -> bytes:
        if "token" in url:
            return json.dumps({"token": "t"}).encode()
        return json.dumps({"manifests": []}).encode()

    return get


def test_env_problems(dev: ModuleType) -> None:
    """SRV-3: a variable the image does not set, or sets to another value, is refused; the
    harness's binding passes."""
    environ = {"CUDA_VERSION": "13.0.2", "CUDA_VISIBLE_DEVICES": "0,1", "HOME": "/x",
               "VLLM_ATTENTION_BACKEND": "FLASHINFER", "VLLM_USAGE_SOURCE": "other"}  # fmt: skip
    assert dev.env_problems(environ, ENV) == ["VLLM_ATTENTION_BACKEND=FLASHINFER",
                                              "VLLM_USAGE_SOURCE=other"]  # fmt: skip


def test_dockerfile_copies_and_from(dev: ModuleType) -> None:
    dockerfile = (SYSTEMS / "ref-serve/Dockerfile").read_text()
    assert dev.dockerfile_from(dockerfile) == IMAGE
    assert dev.copies(dockerfile) == [
        ("fake/write_inputs.py", "/opt/iproofs/write_inputs.py"),
        ("ref-serve/entrypoint", "/opt/ref-serve/entrypoint"),
        ("ref-serve/system.yaml", "/opt/iproofs/system.yaml"),
    ]
    assert dev.locked((SYSTEMS / "ref-serve/inputs.lock").read_text()) == []
    with pytest.raises(SystemExit, match="no FROM"):
        dev.dockerfile_from("RUN x\n")


def test_install_into_a_directory(dev: ModuleType, tmp_path: Path,
                                  monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    """The Dockerfile's COPY destinations, inputs.json with the engine image and the adapter
    files at the commit, the image ENV, all readable; another image than FROM is refused."""
    for key in ("VLLM_ATTENTION_BACKEND", "VLLM_USAGE_SOURCE"):
        monkeypatch.delenv(key, raising=False)
    out = dev.install("ref-serve", IMAGE, toolchains={"vllm": "0.32.0"}, env=ENV, opt=tmp_path)
    assert (tmp_path / "ref-serve/entrypoint").read_bytes() == (
        SYSTEMS / "ref-serve/entrypoint").read_bytes()  # fmt: skip
    assert (tmp_path / "iproofs/system.yaml").is_file()
    doc = json.loads(out.read_text())
    names = [i["name"] for i in doc["inputs"]]
    assert names[0] == "engine image (development install)"
    assert doc["inputs"][0]["digest"] == IMAGE.split("@")[1]
    sha = hashlib.sha256((SYSTEMS / "ref-serve/system.yaml").read_bytes()).hexdigest()
    (entry,) = [i for i in doc["inputs"] if i["name"].startswith("systems/ref-serve/system.yaml")]
    assert entry["digest"] == f"sha256:{sha}"
    assert doc["image_env"] == ENV
    assert json.loads((tmp_path / "iproofs/image_env.json").read_text()) == [
        "CUDA_VERSION=13.0.2", "VLLM_BUILD_COMMIT=5df63a7203cdb9328d824a27b682e77c7b9928be",
        "VLLM_USAGE_SOURCE=production-docker-image"]  # fmt: skip
    assert doc["toolchains"]["vllm"] == "0.32.0"
    with pytest.raises(SystemExit, match="is not the Dockerfile's FROM"):
        dev.install("ref-serve", "docker.io/vllm/vllm-openai@sha256:" + "0" * 64,
                    toolchains={}, env=ENV, opt=tmp_path)  # fmt: skip
    monkeypatch.setenv("VLLM_ATTENTION_BACKEND", "FLASHINFER")
    with pytest.raises(SystemExit, match="VLLM_ATTENTION_BACKEND=FLASHINFER"):
        dev.install("ref-serve", IMAGE, toolchains={}, env=ENV, opt=tmp_path)


def test_fetch_checks_the_lock(dev: ModuleType, tmp_path: Path) -> None:
    body = b"wheel"
    good = hashlib.sha256(body).hexdigest()
    dev.fetch("https://x/w.whl", tmp_path / "w.whl", good, lambda url, h: body)
    assert (tmp_path / "w.whl").read_bytes() == body
    with pytest.raises(SystemExit, match="sha256 differs"):
        dev.fetch("https://x/w.whl", tmp_path / "v.whl", "0" * 64, lambda url, h: body)


def done(stdout: str, rc: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], rc, stdout=stdout, stderr="")


def test_engine_checks(ref: ModuleType) -> None:
    assert ref.engine_version(lambda *a, **k: done("0.32.0\n")) == "0.32.0"
    with pytest.raises(SystemExit, match=r"not 0\.32\.0"):
        ref.engine_version(lambda *a, **k: done("0.33.0rc3\n"))
    ref.check_build(ENV)
    with pytest.raises(SystemExit, match="VLLM_BUILD_COMMIT"):
        ref.check_build(["VLLM_BUILD_COMMIT=0"])


def test_gpu_check(ref: ModuleType) -> None:
    """Under the hosted adapter's exact privilege drop, with only the bound GPUs visible; the
    count, peer access and the NCCL all-reduce (in the script it runs from a file) decide."""
    from iproofs.adapter import DROP_TO_ADAPTER  # noqa: PLC0415

    assert tuple(ref.AS_ADAPTER) == DROP_TO_ADAPTER
    seen: list[Any] = []

    def run(argv: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        seen.append((argv, kw["env"]["CUDA_VISIBLE_DEVICES"]))
        return done("4 True\nnccl all_reduce 4 ok\n")

    ref.check_gpus("0,1,2,3", run)
    argv = seen[0][0]
    assert argv[: len(ref.AS_ADAPTER)] == ref.AS_ADAPTER
    assert argv[-1] == "4"
    assert seen[0][1] == "0,1,2,3"
    script = Path(argv[-2])
    assert script.read_text() == ref.GPU_CHECK
    assert 'init_process_group("nccl"' in ref.GPU_CHECK
    assert "all_reduce" in ref.GPU_CHECK
    compile(ref.GPU_CHECK, "gpu_check.py", "exec")
    with pytest.raises(SystemExit, match="did not see 4 GPU"):
        ref.check_gpus("0,1,2,3", lambda *a, **k: done("3 True\n", 1))


def test_tokenizer_check(ref: ModuleType, tmp_path: Path) -> None:
    """The engine's tokenizer load from the files without the weights, offline, dropped as
    the adapter is, without the token; a load error stops before the weights."""
    seen: list[Any] = []

    def run(argv: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        seen.append((argv, kw["env"]))
        return done("tokenizer TokenizersBackend 201134\nprocessor Llama4Processor\n")

    ref.check_tokenizer(str(tmp_path), run)
    argv, env = seen[0]
    assert argv[: len(ref.AS_ADAPTER)] == ref.AS_ADAPTER
    assert argv[-1] == str(tmp_path)
    assert Path(argv[-2]).read_text() == ref.TOKENIZER_CHECK
    assert (env["HF_HUB_OFFLINE"], env["TRANSFORMERS_OFFLINE"]) == ("1", "1")
    assert "HF_TOKEN" not in env
    compile(ref.TOKENIZER_CHECK, "tokenizer_check.py", "exec")
    with pytest.raises(SystemExit, match="cannot load the tokenizer"):
        ref.check_tokenizer(str(tmp_path), lambda *a, **k: done("JSONDecodeError\n", 1))
