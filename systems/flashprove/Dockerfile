# FlashProve adapter (RFC-0005), built by the RFC-0014 rules and following upstream's
# prover/docs/build.md at the pin: Ubuntu 24.04, gcc and g++ 13, make, python3, CUDA 13.2
# Update 2 (nvcc 13.2.86) from NVIDIA's PyPI packages with the three library links the link step
# needs, then `../verifier/build.sh` and the default `./build.sh` from prover/. No GPU is needed
# to build. B1 every FROM by digest; B2 one `fetch` stage, every download in inputs.lock or in
# cuda-requirements.txt (hashes); B3 `RUN --network=none` after it; B4 no patch or sed over
# upstream source; B5 /opt/iproofs/inputs.json; B6 the adapter commit and dirty flag as build
# arguments. Build with the systems/ directory as context:
#   docker build --build-arg IPROOFS_ADAPTER_COMMIT=$(git rev-parse HEAD) \
#     --build-arg IPROOFS_ADAPTER_DIRTY=$(test -z "$(git status --porcelain)" && echo false || echo true) \
#     -f systems/flashprove/Dockerfile systems
FROM docker.io/library/ubuntu@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852 AS fetch
ENV DEBIAN_FRONTEND=noninteractive
# Ubuntu packages at exact versions (PIN-5), checked by apt against the archive's signed index.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    g++=4:13.2.0-7ubuntu1 g++-13=13.3.0-6ubuntu2~24.04.1 make=4.3-4.1build2 python3=3.12.3-0ubuntu2.1 \
    python3-pip=24.0+dfsg-1ubuntu1.3 git=1:2.43.0-1ubuntu7.4 strace=6.8-0ubuntu2 \
 && rm -rf /var/lib/apt/lists/*
COPY flashprove/inputs.lock flashprove/cuda-requirements.txt /fetch/
ADD --keep-git-dir=true https://github.com/anthropics/FlashProve.git#9e2bdd8ff5bf9c62f18263d7dac189b0400b260c /src
# The link step needs the name libcuda.so; upstream links it to the host driver's library, which a
# build without a GPU lacks, so NVIDIA's link stub from its CUDA 13.2 image stands in. The programs
# load the driver's own libcuda.so.1 at run time.
COPY --from=docker.io/nvidia/cuda@sha256:44a9504c6dfb50b1241464241b02a93871928f373de6f5a644cf5fe9f080aa63 /usr/local/cuda/lib64/stubs/libcuda.so /fetch/stubs/libcuda.so
# strace: the runner traces each verify call's file opens (RFC-0018 CH-4).
# The fit (examples/maverick/run.sh, stage fit): its calibration inputs, and Python 3.13 with
# upstream's hash-locked requirements.txt (torch 2.9.1) through uv, which checks the interpreter
# download against its own pinned sums. Level 1's replies (RFC-0018 AD-3): a second Python 3.13
# environment with the integer model package as its README installs it, from upstream's
# hash-locked integrations/vllm/requirements.txt (vLLM 0.29.0, torch 2.13.0) and the package's
# tests/requirements.txt (pytest, for its float64 check), then the package itself.
ADD --checksum=sha256:e83889baabc497075506f91975be5fac0d45c5290b6b20582c8cd1e853d0c9f7 https://huggingface.co/datasets/Salesforce/wikitext/resolve/b08601e04326c79dfdd32d625aee71d232d685c3/wikitext-2-raw-v1/train-00000-of-00001.parquet /fetch/calibration/wikitext-2-raw-v1-train.parquet
ADD --checksum=sha256:bcd04f0eadf90287bd26e1a183ac487d8a141b09b06aecb7725bbdd343640f2e https://huggingface.co/TheBloke/Llama-2-7B-Chat-fp16/resolve/4594bf11fd5c66a9021d20f5ae5f3a246ce388a1/tokenizer.json /fetch/calibration/llama2-tokenizer.json
ADD --checksum=sha256:172c9eb4beafc72601690da3ccfcede5c2e6806a8d5ec1fca33e22acea8023a4 https://huggingface.co/unsloth/Llama-4-Maverick-17B-128E-Instruct/resolve/86c5ecb6f2fbddf604c60120125fb202e09f2556/tokenizer.json /fetch/calibration/llama4-tokenizer.json
COPY --from=ghcr.io/astral-sh/uv@sha256:78bc42400d77b0678ba95765305c826652ed5431f399257271dda681d0318f03 /uv /usr/local/bin/uv
RUN test "$(git -C /src rev-parse HEAD)" = 9e2bdd8ff5bf9c62f18263d7dac189b0400b260c \
 && test "sha256:$(git -C /src archive --format=tar HEAD | sha256sum | cut -d' ' -f1)" \
         = "$(awk -F'\t' '$1 == "FlashProve" {print $3}' /fetch/inputs.lock)" \
 && python3 -m pip install --no-cache-dir --require-hashes --target=/opt/cuda-13.2.86 \
    --requirement=/fetch/cuda-requirements.txt \
 && UV_PYTHON_INSTALL_DIR=/opt/python uv venv --no-cache --python 3.13 /opt/fp-venv \
 && uv pip install --no-cache --python=/opt/fp-venv/bin/python --require-hashes \
    --requirement /src/requirements.txt \
 && UV_PYTHON_INSTALL_DIR=/opt/python uv venv --no-cache --python 3.13 /opt/im-venv \
 && uv pip install --no-cache --python=/opt/im-venv/bin/python --require-hashes \
    --requirement /src/integrations/vllm/requirements.txt \
 && uv pip install --no-cache --python=/opt/im-venv/bin/python --require-hashes \
    --requirement /src/integrations/vllm/integer_model/tests/requirements.txt \
 && uv pip install --no-cache --python=/opt/im-venv/bin/python --no-deps --no-build-isolation \
    /src/integrations/vllm/integer_model \
 && chmod -R a+rX /opt/python /opt/fp-venv /opt/im-venv /fetch/calibration

FROM fetch
ENV PATH=/opt/cuda-13.2.86/nvidia/cu13/bin:$PATH
WORKDIR /src/prover
RUN --network=none lib=/opt/cuda-13.2.86/nvidia/cu13/lib \
 && for n in cublasLt cublas cudart; do ln -s lib$n.so.13 "$lib/lib$n.so"; done \
 && mkdir "$lib/stubs" && cp /fetch/stubs/libcuda.so "$lib/stubs/libcuda.so" \
 && chmod -R go-w /opt/cuda-13.2.86 \
 && ../verifier/build.sh && ./build.sh && ../weight_sums/build.sh
COPY fake/write_inputs.py /opt/iproofs/write_inputs.py
COPY flashprove/entrypoint /opt/flashprove/entrypoint
RUN --network=none useradd --uid 10001 --no-create-home adapter \
 && python3 /opt/iproofs/write_inputs.py /fetch/inputs.lock /opt/iproofs/inputs.json \
    cuda="$(nvcc --version | grep -o 'V[0-9.]*$')" gcc="$(gcc -dumpfullversion)" \
    make="$(make --version | head -1)" flashprove="$(cat /src/VERSION)" \
    python="$(/opt/fp-venv/bin/python --version)" \
    torch="$(/opt/fp-venv/bin/python -c 'import torch; print(torch.__version__)')" \
    vllm="$(/opt/im-venv/bin/python -c 'import importlib.metadata as m; print(m.version("vllm"))')" \
    integer_model="$(/opt/im-venv/bin/python -c 'import importlib.metadata as m; print(m.version("integer-model"))')" \
    torch_integer_model="$(/opt/im-venv/bin/python -c 'import importlib.metadata as m; print(m.version("torch"))')" \
    strace="$(strace -V | head -1)" \
 && mkdir -p /opt/iproofs/calibration && cp /fetch/calibration/* /opt/iproofs/calibration/
ARG IPROOFS_ADAPTER_COMMIT=unknown
ARG IPROOFS_ADAPTER_DIRTY=true
ENV IPROOFS_ADAPTER_COMMIT=${IPROOFS_ADAPTER_COMMIT} IPROOFS_ADAPTER_DIRTY=${IPROOFS_ADAPTER_DIRTY}
USER 10001
ENTRYPOINT ["python3", "/opt/flashprove/entrypoint"]
