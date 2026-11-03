# Fake system for CI (RFC-0005 §Reference implementations). Every FROM is pinned by digest (RFC-0014 B1).
# Build with the systems/ directory as context and the commit system.yaml pins:
#   docker build --build-arg IPROOFS_FAKE_UPSTREAM=<commit> -f systems/fake/Dockerfile systems
# IPROOFS_FAKE_FAULT is for the integration tests only (systems/fake/entrypoint).
FROM docker.io/library/python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30
COPY fake/entrypoint /opt/fake/entrypoint
RUN useradd --uid 10001 --no-create-home adapter
ARG IPROOFS_FAKE_UPSTREAM
ARG IPROOFS_FAKE_FAULT=""
ENV IPROOFS_FAKE_UPSTREAM=${IPROOFS_FAKE_UPSTREAM} IPROOFS_FAKE_FAULT=${IPROOFS_FAKE_FAULT}
USER 10001
ENTRYPOINT ["python3", "/opt/fake/entrypoint"]
