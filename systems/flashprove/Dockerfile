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
    python3-pip=24.0+dfsg-1ubuntu1.3 git=1:2.43.0-1ubuntu7.4 \
 && rm -rf /var/lib/apt/lists/*
COPY flashprove/inputs.lock flashprove/cuda-requirements.txt /fetch/
ADD --keep-git-dir=true https://github.com/anthropics/FlashProve.git#9e2bdd8ff5bf9c62f18263d7dac189b0400b260c /src
# The link step needs the name libcuda.so; upstream links it to the host driver's library, which a
# build without a GPU lacks, so NVIDIA's link stub from its CUDA 13.2 image stands in. The programs
# load the driver's own libcuda.so.1 at run time.
COPY --from=docker.io/nvidia/cuda@sha256:44a9504c6dfb50b1241464241b02a93871928f373de6f5a644cf5fe9f080aa63 /usr/local/cuda/lib64/stubs/libcuda.so /fetch/stubs/libcuda.so
RUN test "$(git -C /src rev-parse HEAD)" = 9e2bdd8ff5bf9c62f18263d7dac189b0400b260c \
 && test "sha256:$(git -C /src archive --format=tar HEAD | sha256sum | cut -d' ' -f1)" \
         = "$(awk -F'\t' '$1 == "FlashProve" {print $3}' /fetch/inputs.lock)" \
 && python3 -m pip install --no-cache-dir --require-hashes --target=/opt/cuda-13.2.86 \
    --requirement=/fetch/cuda-requirements.txt

FROM fetch
ENV PATH=/opt/cuda-13.2.86/nvidia/cu13/bin:$PATH
WORKDIR /src/prover
RUN --network=none lib=/opt/cuda-13.2.86/nvidia/cu13/lib \
 && for n in cublasLt cublas cudart; do ln -s lib$n.so.13 "$lib/lib$n.so"; done \
 && mkdir "$lib/stubs" && cp /fetch/stubs/libcuda.so "$lib/stubs/libcuda.so" \
 && chmod -R go-w /opt/cuda-13.2.86 \
 && ../verifier/build.sh && ./build.sh
COPY fake/write_inputs.py /opt/iproofs/write_inputs.py
COPY flashprove/entrypoint /opt/flashprove/entrypoint
RUN --network=none useradd --uid 10001 --no-create-home adapter \
 && python3 /opt/iproofs/write_inputs.py /fetch/inputs.lock /opt/iproofs/inputs.json \
    cuda="$(nvcc --version | grep -o 'V[0-9.]*$')" gcc="$(gcc -dumpfullversion)" \
    make="$(make --version | head -1)" flashprove="$(cat /src/VERSION)"
ARG IPROOFS_ADAPTER_COMMIT=unknown
ARG IPROOFS_ADAPTER_DIRTY=true
ENV IPROOFS_ADAPTER_COMMIT=${IPROOFS_ADAPTER_COMMIT} IPROOFS_ADAPTER_DIRTY=${IPROOFS_ADAPTER_DIRTY}
USER 10001
ENTRYPOINT ["python3", "/opt/flashprove/entrypoint"]
