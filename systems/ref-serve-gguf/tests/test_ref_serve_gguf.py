"""ref-serve-gguf on CPU (INV-ADAPTER-9), on synthetic inputs: the server command line, the
request body, the checks on each response, the release protocol, and `prove` end to end against
a stand-in server (fake_llama_server.py). The replay of captured server responses joins these
once the first GPU run has saved them (README §Capture); no capture is invented here."""

import importlib.machinery
import importlib.util
import json
import os
import re
import sys
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from iproofs.provenance import dockerfile_problems
from iproofs.schema import SchemaRegistry

HERE = Path(__file__).resolve().parent
SYSTEM = HERE.parent
ROOT = SYSTEM.parents[1]
REGISTRY = SchemaRegistry.from_tree(ROOT / "schema")
FAKE = HERE / "fake_llama_server.py"
GGUF = "UD-Q4_K_XL/Llama-4-Maverick-17B-128E-Instruct-UD-Q4_K_XL-0000{}-of-00005.gguf"


@pytest.fixture
def adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    for name, sub in (("IPROOFS_IO", "io"), ("IPROOFS_MODELS", "models"),
                      ("IPROOFS_SCRATCH", "scratch")):  # fmt: skip
        (tmp_path / sub).mkdir()
        monkeypatch.setenv(name, str(tmp_path / sub))
    monkeypatch.setenv("IPROOFS_SYSTEM_YAML", str(SYSTEM / "system.yaml"))
    monkeypatch.setenv("LLAMA_ARG_HOST", "0.0.0.0")  # as the engine image sets it
    monkeypatch.delenv("FAKE_MODE", raising=False)
    loader = importlib.machinery.SourceFileLoader("ref_serve_gguf", str(SYSTEM / "entrypoint"))
    spec = importlib.util.spec_from_loader("ref_serve_gguf", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    module.SERVER = [sys.executable, str(FAKE)]
    module.SERVER_CWD = str(tmp_path / "scratch")
    module.POLL_S = 0.01
    for n in (2, 1, 3, 4, 5):  # five split files, the first one is -m
        (tmp_path / "models" / GGUF.format(n)).parent.mkdir(exist_ok=True)
        (tmp_path / "models" / GGUF.format(n)).write_bytes(b"")
    return module


def job(workload: str, size: int, batches: int, output_tokens: int = 1) -> dict[str, Any]:
    return {"schema": "adapter-job/1", "contract": "adapter/1", "subcommand": "prove",
            "run_id": "r", "workload": {"id": workload, "version": 1},
            "shape": {"prompt_tokens": 4, "output_tokens": output_tokens, "batch_size": size,
                      "batches_per_session": batches, "context_window": 4},
            "model_dir": "/models", "prompts_file": "/io/prompts.jsonl", "batch_size": size,
            "batches": batches, "control": False, "control_flags": [],
            "commitment_id": "not_applicable", "prover_files": []}  # fmt: skip


def run(adapter: ModuleType, sub: str, doc: dict[str, Any]) -> dict[str, Any]:
    io = Path(adapter.host("/io"))
    (io / "job.json").write_text(json.dumps(doc | {"subcommand": sub}))
    adapter.sys.argv = ["entrypoint", sub, "/io/job.json", "/io/out.json"]
    assert adapter.main() == 0
    out: dict[str, Any] = json.loads((io / "out.json").read_text())
    assert REGISTRY.errors("adapter-out/1", out) == []
    return out


def prompts(adapter: ModuleType, count: int) -> list[list[int]]:
    found = [[i, i + 1, i + 2, i + 3] for i in range(count)]
    io = Path(adapter.host("/io"))
    (io / "prompts.jsonl").write_text("".join(json.dumps(p) + "\n" for p in found))
    return found


def commands(adapter: ModuleType) -> list[dict[str, Any]]:
    text = (Path(adapter.host("/io")) / "commands.jsonl").read_text()
    return [json.loads(line) for line in text.splitlines()]


# ---------------------------------------------------------------- configuration (SRV-3, SRV-6)


def test_engine_options_verbatim(adapter: ModuleType) -> None:
    doc = yaml.safe_load((SYSTEM / "system.yaml").read_text())
    for entry in doc["workloads"]:
        assert adapter.engine_args(entry["id"]) == entry["engine_args"]
    with pytest.raises(SystemExit, match=r"not in system\.yaml"):
        adapter.engine_args("sash-l31-8b-c1024")


@pytest.mark.parametrize("workload", ["fp-maverick-w1024-b1", "fp-maverick-w1024-b24"])
def test_engine_options_follow_srv6(workload: str) -> None:
    """SRV-6: as many slots as the batch size, prompt plus output tokens per slot in the one
    pinned form (no -c), every layer on the GPU, the routed experts of the first N layers in
    host memory, and the placement fixed (--fit off)."""
    doc = yaml.safe_load((SYSTEM / "system.yaml").read_text())
    [entry] = [w for w in doc["workloads"] if w["id"] == workload]
    wl = yaml.safe_load((ROOT / "workloads" / f"{workload}.yaml").read_text())
    args, shape = entry["engine_args"], wl["shape"]
    per_slot = shape["prompt_tokens"] + shape["output_tokens"]
    n = args[args.index("--n-cpu-moe") + 1]
    assert args == ["-np", str(shape["batch_size"]), "--kv-unified", "--kv-unified-per-slot",
                    str(per_slot), "-ngl", "all", "--n-cpu-moe", n, "--fit", "off"]  # fmt: skip
    assert 0 <= int(n) <= 48  # llama4.block_count of the pinned files
    assert (entry["precision_used"], entry["precision_substitution"]) == (
        wl["precision"]["served"], None)  # PM-1, no substitution  # fmt: skip
    assert "ref-serve-gguf" in wl["systems"]  # SRV-7: the workload's one plain-serving system
    assert "ref-serve" not in wl["systems"]


def test_server_argv(adapter: ModuleType) -> None:
    args = adapter.engine_args("fp-maverick-w1024-b24")
    adapter.SERVER = ["/app/llama-server"]
    argv = adapter.server_argv("/models/m.gguf", 4242, args)
    assert argv == ["/app/llama-server", "-m", "/models/m.gguf", "--host", "127.0.0.1",
                    "--port", "4242", *args]  # fmt: skip


def test_first_gguf(adapter: ModuleType, tmp_path: Path) -> None:
    assert adapter.first_gguf("/models") == "/models/" + GGUF.format(1)
    with pytest.raises(SystemExit, match="no GGUF file"):
        adapter.first_gguf("/models/none")


def test_server_env(adapter: ModuleType) -> None:
    env = adapter.server_env({"PATH": "/usr/bin", "LLAMA_ARG_HOST": "0.0.0.0",
                              "LLAMA_ARG_PORT": "8080", "HOME": "/"})  # fmt: skip
    assert env == {"PATH": "/usr/bin", "HOME": adapter.SCRATCH,
                   "CUDA_CACHE_PATH": adapter.SCRATCH + "/nv-cache"}  # fmt: skip


def test_request_body(adapter: ModuleType) -> None:
    """SRV-6: token ids, n_predict the output tokens, greedy, neutral penalties, no prompt
    cache; token ids back in one response."""
    assert adapter.request_body([5, 6], 1) == {
        "prompt": [5, 6], "n_predict": 1, "temperature": 0.0, "n_probs": 0,
        "repeat_penalty": 1.0, "presence_penalty": 0.0, "frequency_penalty": 0.0,
        "cache_prompt": False, "return_tokens": True, "stream": False}  # fmt: skip


# ---------------------------------------------------------------- the checks on each response


def response(**over: object) -> dict[str, object]:
    base: dict[str, object] = {"tokens": [17], "stop_type": "limit", "tokens_predicted": 1,
                               "tokens_evaluated": 4, "truncated": True}  # fmt: skip
    return base | over


def test_output_tokens_accepts(adapter: ModuleType) -> None:
    assert adapter.output_tokens(response(), 4, 1) == [17]
    assert adapter.output_tokens(response(truncated=False), 4, 1) == [17]
    eos = response(tokens=[1, 2], stop_type="eos", tokens_predicted=2)
    assert adapter.output_tokens(eos, 4, 3) == [1, 2]  # end of sequence before n_predict


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ([], "not an object"),
        (response(tokens=None), "not a list of token ids"),
        (response(tokens=[-1]), "not a list of token ids"),
        (response(tokens=[True]), "not a list of token ids"),
        (response(tokens=[1, 2], tokens_predicted=2), "limit with 2 tokens"),
        (response(tokens=[], stop_type="eos", tokens_predicted=0), "eos with 0 tokens"),
        (response(stop_type="word"), "stop_type 'word'"),
        (response(stop_type=None), "stop_type None"),
        (response(tokens_predicted=2), "tokens_predicted 2"),
        (response(tokens_evaluated=5), "evaluated 5 prompt tokens, not the 4 sent"),
    ],
)
def test_output_tokens_refuses(adapter: ModuleType, doc: object, message: str) -> None:
    with pytest.raises(adapter.ServeError, match=re.escape(message)):
        adapter.output_tokens(doc, 4, 1)


# ---------------------------------------------------------------- prove against a stand-in server


def test_prove_b24_batches_released_per_request(adapter: ModuleType) -> None:
    """SRV-1, SRV-2, REF-1: each batch's 24 requests in flight at once (the stand-in refuses
    them otherwise), released per request after the batch, in request order; the command line
    and every response kept."""
    sent = prompts(adapter, 49)  # one more than the job uses
    out = run(adapter, "prove", job("fp-maverick-w1024-b24", 24, 2))
    io = Path(adapter.host("/io"))
    assert [p["request_index"] for p in out["proofs"]] == list(range(48))
    assert sorted(p.name for p in (io / "proofs").iterdir()) == sorted(
        f"req-{i}" for i in range(48)
    )  # no temporary left
    released = json.loads((io / "proofs/req-30/outputs.json").read_text())
    assert released == {"request_index": 30, "batch": 1, "token_ids": [sum(sent[30]) % 7]}
    assert out["proofs"][30]["claimed_output"] == [sum(sent[30]) % 7]
    [command] = commands(adapter)
    assert command["argv"][:3] == [sys.executable, str(FAKE), "-m"]
    assert command["argv"][3] == "/models/" + GGUF.format(1)  # the container path
    assert command["argv"][8:] == adapter.engine_args("fp-maverick-w1024-b24")
    assert (command["exit_code"], command["cwd"]) == (0, adapter.SERVER_CWD)
    lines = [json.loads(x) for x in (io / "responses.jsonl").read_text().splitlines()]
    assert [(x["request_index"], x["batch"], x["status"]) for x in lines] == [
        (i, i // 24, 200) for i in range(48)
    ]
    assert lines[30]["request"] == adapter.request_body(sent[30], 1)
    assert lines[30]["response"]["tokens"] == [sum(sent[30]) % 7]
    assert "fake llama-server" in (io / "llama-server.log").read_text()


def test_prove_b1(adapter: ModuleType) -> None:
    prompts(adapter, 5)
    out = run(adapter, "prove", job("fp-maverick-w1024-b1", 1, 5))
    assert [p["proof_id"] for p in out["proofs"]] == [f"req-{i}" for i in range(5)]


def test_server_failure_while_loading(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A server that exits while loading (for one, out of GPU memory) fails the step with its
    exit code; the log's last lines go to stderr and the command line is still recorded."""
    monkeypatch.setenv("FAKE_MODE", "die")
    prompts(adapter, 1)
    with pytest.raises(SystemExit, match="llama-server exited 3 while loading"):
        run(adapter, "prove", job("fp-maverick-w1024-b1", 1, 1))
    assert "out of memory (synthetic)" in capsys.readouterr().err
    assert [c["exit_code"] for c in commands(adapter)] == [3]
    assert not list((Path(adapter.host("/io")) / "proofs").iterdir())


def test_server_crash_mid_request(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A server that dies during a batch (for one, out of GPU memory on the first prompt) fails
    the step as the adapter's error, not a traceback: the log's last lines (the allocation
    error) go to stderr, every request of the batch is in responses.jsonl, nothing of the batch
    is released, and the server's exit code is recorded."""
    monkeypatch.setenv("FAKE_MODE", "crash")
    prompts(adapter, 24)
    with pytest.raises(SystemExit, match=r"request 0: no response: .*llama-server exited 134"):
        run(adapter, "prove", job("fp-maverick-w1024-b24", 24, 1))
    assert "CUDA error: out of memory (synthetic)" in capsys.readouterr().err
    io = Path(adapter.host("/io"))
    lines = [json.loads(x) for x in (io / "responses.jsonl").read_text().splitlines()]
    assert [(x["request_index"], x["status"]) for x in lines] == [(i, 0) for i in range(24)]
    assert all(x["response"].startswith("no response: ") for x in lines)
    assert not list((io / "proofs").iterdir())
    assert [c["exit_code"] for c in commands(adapter)] == [134]


def test_request_timeouts(adapter: ModuleType) -> None:
    """A wedged server cannot hold a step until the job's deadline: every request has a socket
    timeout, short for /health, long for /completion."""
    assert 0 < adapter.HEALTH_TIMEOUT_S < adapter.COMPLETION_TIMEOUT_S


def test_server_missing(adapter: ModuleType) -> None:
    adapter.SERVER = [str(Path(adapter.SCRATCH) / "no-such-server")]
    prompts(adapter, 1)
    with pytest.raises(SystemExit, match="llama-server did not start"):
        run(adapter, "prove", job("fp-maverick-w1024-b1", 1, 1))
    assert [c["exit_code"] for c in commands(adapter)] == [None]


@pytest.mark.parametrize(
    ("mode", "message"),
    [("bos", "request 0: the server evaluated 5 prompt tokens, not the 4 sent"),
     ("http500", "request 0: HTTP 500")],
)  # fmt: skip
def test_bad_response_fails_the_batch(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch, mode: str, message: str
) -> None:
    """A response the checks refuse fails the step; nothing of that batch is released, and the
    response is kept in responses.jsonl for the record."""
    monkeypatch.setenv("FAKE_MODE", mode)
    prompts(adapter, 1)
    with pytest.raises(SystemExit, match=re.escape(message)):
        run(adapter, "prove", job("fp-maverick-w1024-b1", 1, 1))
    io = Path(adapter.host("/io"))
    assert not list((io / "proofs").iterdir())
    assert len((io / "responses.jsonl").read_text().splitlines()) == 1
    assert [c["exit_code"] for c in commands(adapter)] == [0]


def test_too_few_prompts_refused(adapter: ModuleType) -> None:
    prompts(adapter, 1)
    with pytest.raises(SystemExit, match=r"1 prompts for 1 batches of 24"):
        run(adapter, "prove", job("fp-maverick-w1024-b24", 24, 1))


def test_release_is_atomic(adapter: ModuleType, tmp_path: Path) -> None:
    proofs = tmp_path / "proofs"
    proofs.mkdir()
    adapter.release(proofs, "req-0", {"token_ids": [1]})
    assert [p.name for p in proofs.iterdir()] == ["req-0"]
    with pytest.raises(OSError, match="req-0"):  # an existing release is never overwritten
        adapter.release(proofs, "req-0", {"token_ids": [2]})


# ---------------------------------------------------------------- info, skipped steps, image


def test_info_and_skipped_steps(adapter: ModuleType) -> None:
    io = Path(adapter.host("/io"))
    base = {"schema": "adapter-job/1", "contract": "adapter/1", "run_id": "r",
            "workload": {"id": "fp-maverick-w1024-b1", "version": 1}}  # fmt: skip
    out = run(adapter, "info", base)
    assert (out["system"], out["upstream_commit"]) == ("ref-serve-gguf", adapter.ENGINE_COMMIT)
    # the profile the row runs on (SRV-6): one H200, the GPU minimum README §Sizing sizes for
    reference = yaml.safe_load((ROOT / "reference/v0.1.yaml").read_text())["profiles"]
    assert out["profile"] == "prover-h200"
    assert reference["prover-h200"]["gpu"] == reference["prover-h200-hosted"]["gpu"]
    assert out["workloads"] == ["fp-maverick-w1024-b1", "fp-maverick-w1024-b24"]
    assert run(adapter, "setup", base)["ready"] is True
    for sub in ("commit", "verify"):
        (io / "job.json").write_text(json.dumps(base | {"subcommand": sub}))
        adapter.sys.argv = ["entrypoint", sub, "/io/job.json", "/io/out.json"]
        with pytest.raises(SystemExit, match=rf"no '{sub}' step"):
            adapter.main()
    (io / "job.json").write_text(json.dumps(base | {"subcommand": "info"}))
    adapter.sys.argv = ["entrypoint", "setup", "/io/job.json", "/io/out.json"]
    with pytest.raises(SystemExit, match=r"job\.json is for 'info'"):
        adapter.main()
    with pytest.raises(SystemExit, match="outside /io and /models"):
        adapter.host("/etc/passwd")


def test_dockerfile_rules() -> None:
    lock = (SYSTEM / "inputs.lock").read_text()
    assert dockerfile_problems((SYSTEM / "Dockerfile").read_text(), lock) == []


def test_engine_pin_matches() -> None:
    """The Dockerfile's base, system.yaml's engine and the entrypoint's commit name one build."""
    doc = yaml.safe_load((SYSTEM / "system.yaml").read_text())
    digest = doc["engine"]["image"].split("@", 1)[1]
    dockerfile = (SYSTEM / "Dockerfile").read_text()
    bases = re.findall(r"^FROM (\S+)", dockerfile, re.M)
    assert bases
    assert all(b.endswith("@" + digest) for b in bases)
    assert (
        'ENGINE_COMMIT = "cd959bae99ff4bed22bef2604f45241c09bbb8c8"'
        in (SYSTEM / "entrypoint").read_text()
    )


@pytest.fixture
def dev_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """dev_install.py with /opt under tmp_path and the download replaced by a local wheel."""
    spec = importlib.util.spec_from_file_location("ref_serve_gguf_dev", SYSTEM / "dev_install.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    opt = tmp_path / "opt"
    monkeypatch.setattr(module, "OPT", opt)
    monkeypatch.setattr(module, "FETCH", opt / "iproofs/fetch")
    monkeypatch.setattr(module, "SITE", opt / "ref-serve-gguf/site")

    def fetch(url: str, dest: Path, sha256: str) -> None:
        with zipfile.ZipFile(dest, "w") as wheel:
            wheel.writestr("yaml/__init__.py", "__version__ = 'fixture'\n")

    monkeypatch.setattr(module, "fetch", fetch)
    monkeypatch.setattr(module, "server_version", lambda: VERSION)
    return module


VERSION = "version: 0.9.0-dev (build 12110, commit cd959bae9)"  # the pinned image's, 2026-11-08


def test_dev_install_mirrors_the_dockerfile(dev_install: ModuleType) -> None:
    """The development install (docs/runbooks/hf-jobs.md) puts the files where the final stage
    of the Dockerfile does, so the hosted runner's command (its ENTRYPOINT) finds them, and lists
    the engine image and the adapter files at the checkout's commit as image inputs."""
    image = dev_install.dockerfile_from()
    dev_install.install(image)
    opt = dev_install.OPT
    dockerfile = (SYSTEM / "Dockerfile").read_text()
    final = dockerfile[dockerfile.rindex("\nFROM ") :]  # the image's own stage
    for dest in re.findall(r"^COPY (?:--from=\S+ )?\S+ /opt/(\S+)$", final, re.M):
        assert (opt / dest.rstrip("/")).exists(), dest
    assert '["python3", "/opt/ref-serve-gguf/entrypoint"]' in final
    assert (opt / "ref-serve-gguf/entrypoint").read_bytes() == (SYSTEM / "entrypoint").read_bytes()
    assert (opt / "ref-serve-gguf/site/yaml/__init__.py").is_file()  # the wheel, extracted
    doc = json.loads((opt / "iproofs/inputs.json").read_text())
    names = [i["name"] for i in doc["inputs"]]
    assert names[0].startswith("pyyaml-6.0.3-")
    engine = doc["inputs"][1]
    assert (engine["url"], engine["digest"]) == (
        "docker://ghcr.io/ggml-org/llama.cpp",
        "sha256:a2963b4817f03eea7e0d6065ea576252322792441ef97aaae178b924520547d6",
    )
    commit = dev_install.git("rev-parse", "HEAD")
    assert doc["inputs"][2]["url"].endswith(f"/{commit}/systems/ref-serve-gguf/entrypoint")
    assert doc["toolchains"]["development_install"].startswith(commit)
    assert doc["toolchains"]["llama-server --version"] == VERSION
    assert REGISTRY.errors("adapter-out/1", {
        "schema": "adapter-out/1", "contract": "adapter/1", "subcommand": "info",
        "phases": [], "warnings": [], "system": "ref-serve-gguf",
        "upstream_commit": "cd959bae99ff4bed22bef2604f45241c09bbb8c8",
        "image_inputs": doc["inputs"], "workloads": [], "profile": "prover-h200",
        "contract_versions": ["adapter/1"]}) == []  # fmt: skip


def test_dev_install_refuses(dev_install: ModuleType, tmp_path: Path) -> None:
    """Another image than the Dockerfile's FROM, a download whose sha256 differs, a non-root
    caller: each stops the install before the runs."""
    with pytest.raises(SystemExit, match="is not the Dockerfile's FROM"):
        dev_install.install("ghcr.io/ggml-org/llama.cpp@sha256:" + "0" * 64)
    source = tmp_path / "wheel.whl"
    source.write_bytes(b"not the locked wheel")
    spec = importlib.util.spec_from_file_location("ref_serve_gguf_dev2", SYSTEM / "dev_install.py")
    assert spec is not None
    assert spec.loader is not None
    real = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(real)
    with pytest.raises(SystemExit, match=r"sha256 differs from inputs\.lock"):
        real.fetch(source.as_uri(), tmp_path / "out.whl", "0" * 64)
    assert not (tmp_path / "out.whl").exists()
    with pytest.raises(SystemExit, match="usage"):
        real.main(["dev_install.py"])
    if os.geteuid() != 0:
        with pytest.raises(SystemExit, match="run as root"):
            real.main(["dev_install.py", real.dockerfile_from()])


def stand_in_server(module: ModuleType, tmp_path: Path, script: str) -> None:
    """A shell script in place of /app/llama-server, run without the uid drop."""
    server = tmp_path / "llama-server"
    server.write_text("#!/bin/sh\n" + script)
    server.chmod(0o755)
    module.SERVER, module.SERVER_CWD, module.AS_ADAPTER = server, str(tmp_path), []


def test_dev_install_checks_the_server_build(tmp_path: Path) -> None:
    """The binary in the image the job started is the pinned build, whatever the job command
    says the image is; its version line goes to inputs.json (see the test above)."""
    spec = importlib.util.spec_from_file_location("ref_serve_gguf_dev3", SYSTEM / "dev_install.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    stand_in_server(module, tmp_path, f'echo "{VERSION}" >&2\necho "built with GNU 14.2.0"\n')
    assert module.server_version() == VERSION
    stand_in_server(module, tmp_path, 'echo "version: 0.9.1 (build 12200, commit 0000000)" >&2\n')
    with pytest.raises(SystemExit, match="not 'build 12110, commit cd959bae9'"):
        module.server_version()


@pytest.mark.parametrize(
    ("listed", "ok"),
    [("  CUDA0: NVIDIA H200 (143771 MiB, 143199 MiB free)", True),  # common/arg.cpp L1149
     ("  (none)", False),
     ("  CUDA0: NVIDIA H200 (1 MiB, 1 MiB free)\n  CUDA1: NVIDIA H200 (1 MiB, 1 MiB free)", False)],
)  # fmt: skip
def test_dev_install_checks_one_cuda_device(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, listed: str, ok: bool
) -> None:
    """Before any weights: the server, with only the bound GPU visible and no LLAMA_ARG_*
    option, lists exactly one CUDA device; a CUDA build the driver cannot run lists none."""
    spec = importlib.util.spec_from_file_location("ref_serve_gguf_dev4", SYSTEM / "dev_install.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("LLAMA_ARG_HOST", "0.0.0.0")
    script = f"""[ "$1" = --list-devices ] || exit 9
[ "$CUDA_VISIBLE_DEVICES" = 1 ] && [ "$CUDA_DEVICE_ORDER" = PCI_BUS_ID ] || exit 8
[ -z "$LLAMA_ARG_HOST" ] || exit 7
printf 'Available devices:\\n{listed}\\n'
"""
    stand_in_server(module, tmp_path, script)
    if ok:
        module.check_gpu("1")
    else:
        with pytest.raises(SystemExit, match=r"CUDA devices listed with CUDA_VISIBLE_DEVICES=1"):
            module.check_gpu("1")
