# FlashProve

Adapter for [`anthropics/FlashProve`](https://github.com/anthropics/FlashProve) at commit `9e2bdd8ff5bf9c62f18263d7dac189b0400b260c` (v0.16.0, RFC-0005). The subcommand mapping lands with #69. This page records the image build. Every fact links upstream at that commit; where upstream is silent, this page says so (AGENTS.md rule 9). Upstream figures are in [`external.yaml`](external.yaml).

## Image and toolchain versions

`Dockerfile` follows [prover/docs/build.md](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/prover/docs/build.md) at the pin, under the RFC-0014 build rules. Each version below is the one upstream names; none is chosen here.

| Toolchain | Version in the image | Upstream source |
|---|---|---|
| CUDA | 13.2 Update 2, `nvcc` V13.2.86, from NVIDIA's PyPI packages `cuda-toolkit[nvcc,cublas,cccl,crt,nvvm,cudart]==13.2.2` | "CUDA 13.2 Update 2, that is nvcc 13.2.86: the release with which the programs are built and tried"; the install lines under [Install the compiler](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/prover/docs/build.md#install-the-compiler) |
| gcc and g++ | 13.3 (Ubuntu 24.04 `g++` 13) | "gcc and g++ 13, first on `PATH`, plus binutils and `flock`" ([docs/quickstart.md](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/docs/quickstart.md)) |
| make, python3 | GNU Make 4.3, Python 3.12.3 (Ubuntu 24.04) | "Ubuntu 24.04 (x86-64) with g++ 13.3, GNU Make 4.3 and Python 3.12 or 3.13" ([docs/quickstart.md](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/docs/quickstart.md#install)) |
| Base | `ubuntu:24.04` by digest | as above |

Build steps, as upstream: from `prover/`, `../verifier/build.sh` then `./build.sh` (the default build: `cp_commit`, `cp_prove` and `cp_verify` in `prover/build/hc`). The build needs no GPU. It prints the `#20011-D` and `#550-D` warnings that upstream lists as expected.

Differences from upstream's instructions, none of which touches upstream source (AGENTS.md rule 1):

- The pip install is locked with hashes (`cuda-requirements.txt`, `--require-hashes`) and runs in the fetch stage (B2). Its `--target` is `/opt/cuda-13.2.86`, not a home directory.
- Upstream links `libcuda.so` to the host driver's library for the link step. A build host without a GPU has none, so NVIDIA's link stub, from its `nvidia/cuda` 13.2.1 devel image by digest, stands in. Its soname is `libcuda.so.1`, so at run time the programs load the driver's own library, which the container runtime provides.
- The source is added with `git` at the pinned commit. The fetch stage checks `git rev-parse HEAD` (INV-ADAPTER-2) and the sha256 of `git archive --format=tar HEAD` against `inputs.lock`.
- Ubuntu packages are pinned to exact versions (PIN-5) from the archive. The Ubuntu snapshot service returned HTTP 503 for every date on 2026-11-04.

At run time upstream needs an H100, a CPU with the SHA extensions, and a sandbox that passes `madvise(MADV_WIPEONFORK)` ([prover/docs/build.md](https://github.com/anthropics/FlashProve/blob/9e2bdd8ff5bf9c62f18263d7dac189b0400b260c/prover/docs/build.md#what-you-need)).
