"""Development install of the ref-serve adapter into a container started from the pinned vLLM
image itself (docs/runbooks/hf-jobs.md §Production serving; RFC-0014 §Development install).
Run as root, from the checkout, inside the engine image, with its Python:

    python3 systems/ref-serve/dev_install.py ENGINE_IMAGE [GPUS]

ENGINE_IMAGE is the reference the provider started, <repository>@sha256:<digest>; it must be the
Dockerfile's FROM. Before any weights are fetched it checks, and stops on a failure:

1. the image is the Dockerfile's FROM (the job command asserts the reference; the container
   cannot read it back);
2. the engine: `import vllm` reports version 0.32.0, and the image ENV's VLLM_BUILD_COMMIT is the
   pinned source commit;
3. the environment (RFC-0015 SRV-3): the image's own ENV, read from its config by digest, is
   recorded in inputs.json and /opt/iproofs/image_env.json, and a VLLM_*, NCCL_*, CUDA_* or
   TORCH_* variable the job sets beyond it (other than the harness's binding) is refused;
4. with GPUS (the comma-separated indices the runs bind), under the hosted adapter's own
   privilege drop (uid 10001, no capabilities, no new privileges; iproofs.adapter
   DROP_TO_ADAPTER) with only those GPUs visible: torch sees exactly that many; with more than
   one, every pair reports peer access, and one process per GPU joins an NCCL process group and
   all-reduces a small tensor, the multi-process path a tensor-parallel engine starts with.

It then puts `entrypoint`, `system.yaml` and `write_inputs.py` where the Dockerfile puts them.

    python3 systems/ref-serve/dev_install.py --tokenizer-check DIR

loads the tokenizer from DIR (a serving record's files without its weights, `iproofs
fetch-model --serving RECORD --no-weights DIR`) as the engine does, and for a multimodal
config the processor too, under the same drop, before any weights are fetched.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_dev"))
import install as dev

SYSTEM = "ref-serve"
VERSION = "0.32.0"  # RFC-0015 Q1
COMMIT = "5df63a7203cdb9328d824a27b682e77c7b9928be"  # vLLM v0.32.0's source commit
# the hosted adapter's privilege drop, iproofs.adapter.DROP_TO_ADAPTER (a test keeps them equal)
AS_ADAPTER = ["setpriv", f"--reuid={dev.ADAPTER_UID}", f"--regid={dev.ADAPTER_UID}",
              "--clear-groups", "--inh-caps=-all", "--bounding-set=-all",
              "--no-new-privs"]  # fmt: skip
GPU_CHECK = """import socket, sys
import torch
import torch.distributed as dist
import torch.multiprocessing as mp


def worker(rank, n, port):
    torch.cuda.set_device(rank)
    dist.init_process_group("nccl", init_method=f"tcp://127.0.0.1:{port}", rank=rank,
                            world_size=n)
    t = torch.full((1024,), float(rank + 1), device="cuda")
    dist.all_reduce(t)
    torch.cuda.synchronize()
    ok = bool((t == n * (n + 1) / 2).all())
    dist.destroy_process_group()
    if not ok:
        raise SystemExit(f"rank {rank}: all_reduce gave {t[0].item()}")


if __name__ == "__main__":
    n = torch.cuda.device_count()
    peers = all(torch.cuda.can_device_access_peer(i, j)
                for i in range(n) for j in range(n) if i != j)
    print(n, peers)
    if n != int(sys.argv[1]) or not peers:
        sys.exit(1)
    if n > 1:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        mp.spawn(worker, args=(n, port), nprocs=n, join=True)
        print("nccl all_reduce", n, "ok")
"""
TOKENIZER_CHECK = """import json, sys
from pathlib import Path

d = sys.argv[1]
try:
    from vllm.tokenizers import get_tokenizer
except ImportError:
    from vllm.transformers_utils.tokenizer import get_tokenizer
tok = get_tokenizer(d)
print("tokenizer", type(tok).__name__, getattr(tok, "max_token_id", None))
if "vision_config" in json.loads((Path(d) / "config.json").read_text()):
    from transformers import AutoProcessor
    print("processor", type(AutoProcessor.from_pretrained(d)).__name__)
"""


def engine_version(run: object = subprocess.run) -> str:
    done = run(["python3", "-c", "import vllm; print(vllm.__version__)"],  # type: ignore[operator]
               capture_output=True, text=True, check=False)  # fmt: skip
    version = (done.stdout or "").strip()
    if not version.startswith(VERSION):
        dev.fail(f"import vllm reports {version or done.stderr.strip()[-200:]!r}, not {VERSION}")
    return version


def check_build(image_vars: list[str]) -> None:
    built = dict(e.split("=", 1) for e in image_vars if "=" in e).get("VLLM_BUILD_COMMIT")
    if built != COMMIT:
        dev.fail(f"the image's VLLM_BUILD_COMMIT is {built!r}, not {COMMIT}")


def as_adapter_script(code: str, name: str) -> Path:
    """A script file the adapter uid can read (torch.multiprocessing's spawn re-imports the
    main module from its file, so `python3 -c` cannot run the NCCL check)."""
    path = Path(tempfile.mkdtemp(prefix="iproofs-dev-check-")) / name
    path.write_text(code)
    path.parent.chmod(0o755)
    path.chmod(0o644)
    return path


def check_gpus(gpus: str, run: object = subprocess.run) -> None:
    """As the adapter is dropped, with only the bound GPUs visible, as the hosted runner gives
    them; with several GPUs, an NCCL all-reduce across them (the tensor-parallel start)."""
    count = len([g for g in gpus.split(",") if g.strip()])
    environ = {**os.environ, "CUDA_DEVICE_ORDER": "PCI_BUS_ID", "CUDA_VISIBLE_DEVICES": gpus,
               "HOME": "/tmp"}  # fmt: skip
    script = as_adapter_script(GPU_CHECK, "gpu_check.py")
    done = run([*AS_ADAPTER, "python3", str(script), str(count)],  # type: ignore[operator]
               capture_output=True, text=True, env=environ, check=False)  # fmt: skip
    print(f"dev-install: GPU check {done.stdout.strip()} (CUDA_VISIBLE_DEVICES={gpus})")
    if done.returncode != 0:
        tail = (done.stdout + done.stderr).strip()[-600:]
        dev.fail(f"torch did not see {count} GPU(s) with peer access between each pair, or "
                 f"the NCCL all-reduce failed: {tail}")  # fmt: skip


def check_tokenizer(directory: str, run: object = subprocess.run) -> None:
    """The engine's tokenizer load (and the processor's, for a multimodal config) from the
    record's files without the weights, offline, as the adapter is dropped."""
    environ = {**os.environ, "HOME": "/tmp", "XDG_CACHE_HOME": "/tmp/.cache-iproofs-check",
               "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}  # fmt: skip
    environ.pop("HF_TOKEN", None)
    script = as_adapter_script(TOKENIZER_CHECK, "tokenizer_check.py")
    done = run([*AS_ADAPTER, "python3", str(script), directory],  # type: ignore[operator]
               capture_output=True, text=True, env=environ, check=False)  # fmt: skip
    print(f"dev-install: tokenizer check {done.stdout.strip()} ({directory})")
    if done.returncode != 0:
        dev.fail(f"the engine cannot load the tokenizer or processor from {directory}: "
                 f"{(done.stdout + done.stderr).strip()[-600:]}")  # fmt: skip


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[1] == "--tokenizer-check":
        if os.geteuid() != 0:
            dev.fail("run as root (it drops to uid 10001 as the hosted adapter is dropped)")
        check_tokenizer(argv[2])
        return 0
    if len(argv) not in (2, 3):
        dev.fail("usage: dev_install.py ENGINE_IMAGE [GPUS] | dev_install.py --tokenizer-check DIR")
    if os.geteuid() != 0:
        dev.fail("run as root (it writes /opt and adds uid 10001)")
    image = argv[1]
    version = engine_version()
    print(f"dev-install: vllm {version}")
    image_vars = dev.image_env(image)
    check_build(image_vars)
    dev.install(SYSTEM, image, toolchains={"vllm": version}, env=image_vars)
    dev.ensure_adapter_user()
    if len(argv) == 3:
        check_gpus(argv[2])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
