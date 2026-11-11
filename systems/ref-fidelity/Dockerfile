# ref-fidelity (RFC-0018 FI-1, FI-2, FI-7): llama.cpp v0.9.0 built from source, built by the
# RFC-0014 rules. The build follows upstream's .devops/cuda.Dockerfile at the pin (CUDA 12.8.1
# on Ubuntu 24.04, GGML_CUDA=ON, GGML_NATIVE=OFF, linked with --allow-shlib-undefined so no GPU
# is needed to build), for the H200's compute capability 9.0 only and only the three programs
# the entrypoint runs; no UI and no HTTPS (the server listens on the container's loopback).
# B1 every FROM by digest; B2 one `fetch` stage, every download in inputs.lock or in
# convert-requirements.txt (hashes); B3 `RUN --network=none` after it; B4 no patch over upstream
# source; B5 /opt/iproofs/inputs.json; B6 the adapter commit and dirty flag as build arguments.
# Build with the systems/ directory as context:
#   docker build --build-arg IPROOFS_ADAPTER_COMMIT=$(git rev-parse HEAD) \
#     --build-arg IPROOFS_ADAPTER_DIRTY=$(test -z "$(git status --porcelain)" && echo false || echo true) \
#     -f systems/ref-fidelity/Dockerfile systems
# nvidia/cuda:12.8.1-devel-ubuntu24.04 (manifest list digest, Docker Hub, read 2026-11-10)
FROM docker.io/nvidia/cuda@sha256:520292dbb4f755fd360766059e62956e9379485d9e073bbd2f6e3c20c270ed66 AS fetch
ENV DEBIAN_FRONTEND=noninteractive
# Ubuntu 24.04 packages at exact versions (PIN-5; Launchpad's published versions on 2026-11-10).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    build-essential=12.10ubuntu1 cmake=3.28.3-1build7 git=1:2.43.0-1ubuntu7.4 \
    python3=3.12.3-0ubuntu2.1 python3-pip=24.0+dfsg-1ubuntu1.3 \
 && rm -rf /var/lib/apt/lists/*
COPY ref-fidelity/inputs.lock ref-fidelity/convert-requirements.txt /fetch/
ADD --keep-git-dir=true https://github.com/ggml-org/llama.cpp.git#cd959bae99ff4bed22bef2604f45241c09bbb8c8 /opt/llama.cpp/src
RUN test "$(git -C /opt/llama.cpp/src rev-parse HEAD)" = cd959bae99ff4bed22bef2604f45241c09bbb8c8 \
 && test "sha256:$(git -C /opt/llama.cpp/src archive --format=tar HEAD | sha256sum | cut -d' ' -f1)" \
         = "$(awk -F'\t' '$1 == "llama.cpp" {print $3}' /fetch/inputs.lock)" \
 && python3 -m pip install --no-cache-dir --require-hashes --no-deps --target=/opt/convert-deps \
    --requirement=/fetch/convert-requirements.txt \
 && chmod -R a+rX /opt/convert-deps /opt/llama.cpp

FROM fetch
WORKDIR /opt/llama.cpp/src
RUN --network=none cmake -B /opt/llama.cpp/build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF \
    -DGGML_NATIVE=OFF -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=90 -DLLAMA_BUILD_TESTS=OFF \
    -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_UI=OFF -DLLAMA_USE_PREBUILT_UI=OFF \
    -DLLAMA_OPENSSL=OFF -DCMAKE_EXE_LINKER_FLAGS=-Wl,--allow-shlib-undefined . \
 && cmake --build /opt/llama.cpp/build --config Release -j"$(nproc)" \
    --target llama-server llama-quantize llama-perplexity \
 && chmod -R a+rX /opt/llama.cpp/build/bin
COPY fake/write_inputs.py /opt/iproofs/write_inputs.py
COPY ref-fidelity/entrypoint ref-fidelity/drop_blocks.py /opt/ref-fidelity/
COPY ref-fidelity/system.yaml /opt/iproofs/system.yaml
RUN --network=none useradd --uid 10001 --no-create-home adapter \
 && python3 /opt/iproofs/write_inputs.py /fetch/inputs.lock /opt/iproofs/inputs.json \
    cuda="$(nvcc --version | grep -o 'V[0-9.]*$')" gcc="$(gcc -dumpfullversion)" \
    cmake="$(cmake --version | head -1)" llama.cpp="$(git -C /opt/llama.cpp/src rev-parse HEAD)" \
    torch="$(PYTHONPATH=/opt/convert-deps python3 -c 'import torch; print(torch.__version__)')" \
    transformers="$(PYTHONPATH=/opt/convert-deps python3 -c 'import transformers; print(transformers.__version__)')"
ARG IPROOFS_ADAPTER_COMMIT=unknown
ARG IPROOFS_ADAPTER_DIRTY=true
ENV IPROOFS_ADAPTER_COMMIT=${IPROOFS_ADAPTER_COMMIT} IPROOFS_ADAPTER_DIRTY=${IPROOFS_ADAPTER_DIRTY}
USER 10001
ENTRYPOINT ["python3", "/opt/ref-fidelity/entrypoint"]
