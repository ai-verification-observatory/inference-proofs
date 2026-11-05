# SASH zk-inference-prover adapter (RFC-0005), built by the RFC-0014 rules and following
# upstream's own Dockerfile at the pin: CUDA 12.9 devel on Ubuntu 24.04, gcc 13, the
# rust-toolchain.toml nightly, both prover backends built with `--locked`, kernels for sm_90
# (CUDAARCHS), and the harness's CUDA torch group (harness/pyproject.toml). B1 every FROM by
# digest; B2 one `fetch` stage, every download in inputs.lock or in upstream's hashed lockfiles;
# B3 `RUN --network=none` after it; B4 no patch or sed over upstream source; B5
# /opt/iproofs/inputs.json; B6 the adapter commit and dirty flag as build arguments.
# Build with the systems/ directory as context:
#   docker build --build-arg IPROOFS_ADAPTER_COMMIT=$(git rev-parse HEAD) \
#     --build-arg IPROOFS_ADAPTER_DIRTY=$(test -z "$(git status --porcelain)" && echo false || echo true) \
#     -f systems/sash/Dockerfile systems
FROM docker.io/nvidia/cuda@sha256:020bc241a628776338f4d4053fed4c38f6f7f3d7eb5919fecb8de313bb8ba47c AS fetch
ENV DEBIAN_FRONTEND=noninteractive
# Ubuntu packages at exact versions (PIN-5), checked by apt against the archive's signed index;
# NVIDIA's apt source is dropped, since the toolkit comes with the base image.
RUN rm -f /etc/apt/sources.list.d/cuda*.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
    cmake=3.28.3-1build7 git=1:2.43.0-1ubuntu7.4 pkg-config=1.8.1-2build1 python3=3.12.3-0ubuntu2.1 \
 && rm -rf /var/lib/apt/lists/*
COPY sash/inputs.lock /fetch/inputs.lock
ADD --keep-git-dir=true https://github.com/sg-ai-safety-hub/zk-inference-prover.git#eb95bfa887299d1637550228d42086c27cbb2b3b /src
ADD --checksum=sha256:ac0a04b2bb6ca1e69c959e9b941ea4362dfaa005b9a9c86444aa434bca396a08 https://static.rust-lang.org/dist/2025-07-14/rust-nightly-x86_64-unknown-linux-gnu.tar.xz /fetch/
COPY --from=ghcr.io/astral-sh/uv@sha256:78bc42400d77b0678ba95765305c826652ed5431f399257271dda681d0318f03 /uv /usr/local/bin/uv
ENV CARGO_HOME=/opt/cargo PATH=/opt/rust/bin:$PATH \
    UV_PYTHON_DOWNLOADS=never UV_CACHE_DIR=/tmp/uv-cache
RUN test "$(git -C /src rev-parse HEAD)" = eb95bfa887299d1637550228d42086c27cbb2b3b \
 && test "sha256:$(git -C /src archive --format=tar HEAD | sha256sum | cut -d' ' -f1)" \
         = "$(awk -F'\t' '$1 == "zk-inference-prover" {print $3}' /fetch/inputs.lock)" \
 && tar -xJf /fetch/rust-nightly-x86_64-unknown-linux-gnu.tar.xz -C /tmp \
 && /tmp/rust-nightly-x86_64-unknown-linux-gnu/install.sh --prefix=/opt/rust \
    --components=rustc,cargo,rust-std-x86_64-unknown-linux-gnu \
 && rm -rf /tmp/rust-nightly-x86_64-unknown-linux-gnu /fetch/rust-nightly-x86_64-unknown-linux-gnu.tar.xz \
 && cd /src && cargo fetch --locked \
 && chmod -R a+rX /opt/cargo \
 && cd harness && uv sync --frozen --no-group cpu --group cuda && rm -rf /tmp/uv-cache

FROM fetch
# nvcc 12.9 accepts gcc 14 or older; Ubuntu 24.04 ships gcc 13 (upstream Dockerfile).
ENV CUDAHOSTCXX=/usr/bin/g++ CUDAARCHS=90
WORKDIR /src
RUN --network=none cargo build --release --locked --offline \
 && cp target/release/zk-prover /usr/local/bin/zk-prover-simd \
 && cargo build --release --locked --offline -p zk-prover --features cuda \
 && cp target/release/zk-prover /usr/local/bin/zk-prover-cuda \
 && rm -rf target
COPY fake/write_inputs.py /opt/iproofs/write_inputs.py
COPY sash/entrypoint /opt/sash/entrypoint
RUN --network=none useradd --uid 10001 --no-create-home adapter \
 && python3 /opt/iproofs/write_inputs.py /fetch/inputs.lock /opt/iproofs/inputs.json \
    rust="$(rustc --version)" cuda="$(nvcc --version | grep -o 'V[0-9.]*$')" \
    gcc="$(gcc -dumpfullversion)" uv="$(uv --version)" cargo="$(cargo --version)"
ARG IPROOFS_ADAPTER_COMMIT=unknown
ARG IPROOFS_ADAPTER_DIRTY=true
ENV IPROOFS_ADAPTER_COMMIT=${IPROOFS_ADAPTER_COMMIT} IPROOFS_ADAPTER_DIRTY=${IPROOFS_ADAPTER_DIRTY}
USER 10001
ENTRYPOINT ["python3", "/opt/sash/entrypoint"]
