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
4. with GPUS (the comma-separated indices the runs bind), as uid 10001 with only those GPUs
   visible: torch sees exactly that many, and with more than one every pair reports peer access.

It then puts `entrypoint`, `system.yaml` and `write_inputs.py` where the Dockerfile puts them.
"""

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_dev"))
import install as dev

SYSTEM = "ref-serve"
VERSION = "0.32.0"  # RFC-0015 Q1
COMMIT = "5df63a7203cdb9328d824a27b682e77c7b9928be"  # vLLM v0.32.0's source commit
AS_ADAPTER = ["setpriv", f"--reuid={dev.ADAPTER_UID}", f"--regid={dev.ADAPTER_UID}",
              "--clear-groups"]  # fmt: skip
GPU_CHECK = """import sys, torch
n = torch.cuda.device_count()
peers = all(torch.cuda.can_device_access_peer(i, j) for i in range(n) for j in range(n) if i != j)
print(n, peers)
sys.exit(0 if n == int(sys.argv[1]) and peers else 1)
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


def check_gpus(gpus: str, run: object = subprocess.run) -> None:
    """As the adapter uid, with only the bound GPUs visible, as the hosted runner gives them."""
    count = len([g for g in gpus.split(",") if g.strip()])
    environ = {**os.environ, "CUDA_DEVICE_ORDER": "PCI_BUS_ID", "CUDA_VISIBLE_DEVICES": gpus}
    done = run([*AS_ADAPTER, "python3", "-c", GPU_CHECK, str(count)],  # type: ignore[operator]
               capture_output=True, text=True, env=environ, check=False)  # fmt: skip
    print(f"dev-install: GPU check {done.stdout.strip()} (CUDA_VISIBLE_DEVICES={gpus})")
    if done.returncode != 0:
        dev.fail(f"torch did not see {count} GPU(s) with peer access between each pair: "
                 f"{(done.stdout + done.stderr).strip()[-300:]}")  # fmt: skip


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        dev.fail("usage: dev_install.py ENGINE_IMAGE [GPUS]")
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
