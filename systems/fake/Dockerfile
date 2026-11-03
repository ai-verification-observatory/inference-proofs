# Fake system for CI (RFC-0005 §Reference implementations), built by the RFC-0014 rules:
# B1 every FROM by digest; B2 one `fetch` stage downloading every input in inputs.lock (none for
# the fake); B3 `RUN --network=none` after it; B5 /opt/iproofs/inputs.json; B6 the adapter
# commit and dirty flag as build arguments. Build with the systems/ directory as context:
#   docker build --build-arg IPROOFS_FAKE_UPSTREAM=<commit in system.yaml> \
#     --build-arg IPROOFS_ADAPTER_COMMIT=$(git rev-parse HEAD) \
#     --build-arg IPROOFS_ADAPTER_DIRTY=$(test -z "$(git status --porcelain)" && echo false || echo true) \
#     -f systems/fake/Dockerfile systems
# IPROOFS_FAKE_FAULT is for the integration tests only (systems/fake/entrypoint).
FROM docker.io/library/python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30 AS fetch
COPY fake/inputs.lock /fetch/inputs.lock

FROM docker.io/library/python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30
COPY --from=fetch /fetch/inputs.lock /opt/iproofs/inputs.lock
COPY fake/entrypoint /opt/fake/entrypoint
COPY fake/write_inputs.py /opt/iproofs/write_inputs.py
RUN --network=none useradd --uid 10001 --no-create-home adapter \
 && python3 /opt/iproofs/write_inputs.py /opt/iproofs/inputs.lock /opt/iproofs/inputs.json
ARG IPROOFS_FAKE_UPSTREAM
ARG IPROOFS_FAKE_FAULT=""
ARG IPROOFS_ADAPTER_COMMIT=unknown
ARG IPROOFS_ADAPTER_DIRTY=true
ENV IPROOFS_FAKE_UPSTREAM=${IPROOFS_FAKE_UPSTREAM} IPROOFS_FAKE_FAULT=${IPROOFS_FAKE_FAULT} \
    IPROOFS_ADAPTER_COMMIT=${IPROOFS_ADAPTER_COMMIT} IPROOFS_ADAPTER_DIRTY=${IPROOFS_ADAPTER_DIRTY}
USER 10001
ENTRYPOINT ["python3", "/opt/fake/entrypoint"]
