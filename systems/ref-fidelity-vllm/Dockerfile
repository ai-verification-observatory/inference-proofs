# ref-fidelity-vllm (RFC-0018 FI-9): the fidelity reference in vLLM, for a rung whose 16-bit
# reference llama.cpp at the level's pin cannot run. Built by the RFC-0014 rules: B1 every FROM
# by digest (vLLM v0.32.0, the engine the serving baselines run, RFC-0015 Q1); B2 one `fetch`
# stage, every download in inputs.lock (none: the engine image holds everything it runs); B3
# `RUN --network=none` after it; B5 /opt/iproofs/inputs.json; B6 the adapter commit and dirty
# flag as build arguments. Build with the systems/ directory as context:
#   docker build --build-arg IPROOFS_ADAPTER_COMMIT=$(git rev-parse HEAD) \
#     --build-arg IPROOFS_ADAPTER_DIRTY=$(test -z "$(git status --porcelain)" && echo false || echo true) \
#     -f systems/ref-fidelity-vllm/Dockerfile systems
FROM docker.io/vllm/vllm-openai@sha256:befccf0e7e4089aa23926bb6f887a85c0d46c2a99e6de5c5ffdf5cb7957c5b34 AS fetch
ENV DEBIAN_FRONTEND=noninteractive
# git for the job's clone of this repository (hf-job.sh): the engine image has none and the
# image runs as uid 10001. Ubuntu 24.04's version, as ref-fidelity pins it (PIN-5).
RUN apt-get update \
 && apt-get install -y --no-install-recommends git=1:2.43.0-1ubuntu7.4 \
 && rm -rf /var/lib/apt/lists/*
COPY ref-fidelity-vllm/inputs.lock /fetch/inputs.lock

FROM fetch
COPY --from=fetch /fetch/ /opt/iproofs/fetch/
COPY fake/write_inputs.py /opt/iproofs/write_inputs.py
COPY ref-fidelity-vllm/entrypoint /opt/ref-fidelity-vllm/entrypoint
COPY ref-fidelity-vllm/system.yaml /opt/iproofs/system.yaml
RUN --network=none useradd --uid 10001 --no-create-home adapter \
 && python3 /opt/iproofs/write_inputs.py /opt/iproofs/fetch/inputs.lock /opt/iproofs/inputs.json
ARG IPROOFS_ADAPTER_COMMIT=unknown
ARG IPROOFS_ADAPTER_DIRTY=true
ENV IPROOFS_ADAPTER_COMMIT=${IPROOFS_ADAPTER_COMMIT} IPROOFS_ADAPTER_DIRTY=${IPROOFS_ADAPTER_DIRTY}
USER 10001
ENTRYPOINT ["python3", "/opt/ref-fidelity-vllm/entrypoint"]
