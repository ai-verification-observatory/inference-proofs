# DeepProve adapter (RFC-0005), built by the RFC-0014 rules and following upstream's own
# docker/deep-prove-worker.dockerfile at the pin (its build packages: git, protobuf-compiler,
# libssl-dev, pkg-config, cmake, build-essential, g++, libclang-dev) with the rust-toolchain.toml
# nightly, both programs built with `--locked` and default features (CPU: the ndarray backend
# and HyperKZG on BN254, zkml/README.md L36, L111). B1 every FROM by digest; B2 one `fetch`
# stage, every download in inputs.lock or in upstream's Cargo.lock; B3 `RUN --network=none`
# after it; B4 no patch or sed over upstream source; B5 /opt/iproofs/inputs.json; B6 the adapter
# commit and dirty flag as build arguments.
#
# LICENCE: DeepProve's licence (LICENSE at the pin) grants internal use for testing and
# evaluation only and forbids distributing the Software or any portion of it to a third party
# (Sections 2 and 4). This image holds the source and the compiled programs: build it where it
# runs, or keep it in a registry only the operator can read. Do not push it to a public
# registry (README.md §Licence).
#
# Build with the systems/ directory as context:
#   docker build --build-arg IPROOFS_ADAPTER_COMMIT=$(git rev-parse HEAD) \
#     --build-arg IPROOFS_ADAPTER_DIRTY=$(test -z "$(git status --porcelain)" && echo false || echo true) \
#     -f systems/deepprove/Dockerfile systems
FROM docker.io/library/ubuntu@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852 AS fetch
ENV DEBIAN_FRONTEND=noninteractive
# Ubuntu packages at exact versions (PIN-5), checked by apt against the archive's signed index
# (versions read in this base image on 2026-11-11). ca-certificates for cargo's downloads,
# python3 for the entrypoint; strace is not upstream's: the runner traces each verify call's
# file opens (RFC-0018 CH-4). ca-certificates' version is an ARG: its dotted tail reads as an
# address to the secret scan (G9 SEC-5) unless it sits in a version field.
ARG CA_CERTIFICATES_VERSION=20260816ubuntu0.24.04.2
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    build-essential=12.10ubuntu1 g++=4:13.2.0-7ubuntu1 cmake=3.28.3-1build7 \
    git=1:2.43.0-1ubuntu7.4 pkg-config=1.8.1-2build1 libssl-dev=3.0.13-0ubuntu3.16 \
    protobuf-compiler=3.21.12-8.2ubuntu0.4 libclang-dev=1:18.0-59~exp2 \
    ca-certificates=${CA_CERTIFICATES_VERSION} python3=3.12.3-0ubuntu2.1 strace=6.8-0ubuntu2 \
 && rm -rf /var/lib/apt/lists/*
COPY deepprove/inputs.lock /fetch/inputs.lock
ADD --keep-git-dir=true https://github.com/Lagrange-Labs/deep-prove.git#9d1a53e2ef49ffa2c902b8689cd3c58057a4e662 /src
ADD --checksum=sha256:12d13a398249b6e26a5364d66299b1628b817ca93ddf3ad53e2b8d0803c0e3e5 https://static.rust-lang.org/dist/2026-01-27/rust-nightly-x86_64-unknown-linux-gnu.tar.xz /fetch/
ENV CARGO_HOME=/opt/cargo PATH=/opt/rust/bin:$PATH
RUN test "$(git -C /src rev-parse HEAD)" = 9d1a53e2ef49ffa2c902b8689cd3c58057a4e662 \
 && test "sha256:$(git -C /src archive --format=tar HEAD | sha256sum | cut -d' ' -f1)" \
         = "$(awk -F'\t' '$1 == "deep-prove" {print $3}' /fetch/inputs.lock)" \
 && tar -xJf /fetch/rust-nightly-x86_64-unknown-linux-gnu.tar.xz -C /tmp \
 && /tmp/rust-nightly-x86_64-unknown-linux-gnu/install.sh --prefix=/opt/rust \
    --components=rustc,cargo,rust-std-x86_64-unknown-linux-gnu \
 && rm -rf /tmp/rust-nightly-x86_64-unknown-linux-gnu /fetch/rust-nightly-x86_64-unknown-linux-gnu.tar.xz \
 && cd /src && cargo fetch --locked \
 && chmod -R a+rX /opt/cargo

FROM fetch
WORKDIR /src
# upstream's Dockerfile adds `-F otel` (OpenTelemetry export); a container without network has
# nothing to export to, so the default features are built (README.md, deviations)
RUN --network=none cargo build --release --locked --offline -p deep-prove \
    --bin deep-prove-worker --bin deep-prove-cli \
 && cp target/release/deep-prove-worker target/release/deep-prove-cli /usr/local/bin/ \
 && rm -rf target
COPY fake/write_inputs.py /opt/iproofs/write_inputs.py
COPY deepprove/entrypoint /opt/deepprove/entrypoint
RUN --network=none useradd --uid 10001 --no-create-home adapter \
 && python3 /opt/iproofs/write_inputs.py /fetch/inputs.lock /opt/iproofs/inputs.json \
    rust="$(rustc --version)" cargo="$(cargo --version)" gcc="$(gcc -dumpfullversion)" \
    deepprove="$(cat /src/VERSION)" strace="$(strace -V | head -1)"
ARG IPROOFS_ADAPTER_COMMIT=unknown
ARG IPROOFS_ADAPTER_DIRTY=true
ENV IPROOFS_ADAPTER_COMMIT=${IPROOFS_ADAPTER_COMMIT} IPROOFS_ADAPTER_DIRTY=${IPROOFS_ADAPTER_DIRTY}
USER 10001
ENTRYPOINT ["python3", "/opt/deepprove/entrypoint"]
