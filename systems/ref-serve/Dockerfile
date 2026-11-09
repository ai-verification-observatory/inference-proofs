# Production-serving reference adapter (RFC-0015 SRV-6), built by the RFC-0014 rules: B1 every
# FROM by digest (vLLM v0.32.0, RFC-0015 Q1); B2 one `fetch` stage, every download in inputs.lock
# (none: the engine image holds everything production serving runs); B3 `RUN --network=none`
# after it; B5 /opt/iproofs/inputs.json; B6 the adapter commit and dirty flag as build arguments.
# The engine image's own VLLM_*, NCCL_*, CUDA_* and TORCH_* ENV is written to
# /opt/iproofs/image_env.json before this file sets any variable, so the adapter refuses any
# other engine variable at run time (SRV-3). Build with the systems/ directory as context:
#   docker build --build-arg IPROOFS_ADAPTER_COMMIT=$(git rev-parse HEAD) \
#     --build-arg IPROOFS_ADAPTER_DIRTY=$(test -z "$(git status --porcelain)" && echo false || echo true) \
#     -f systems/ref-serve/Dockerfile systems
FROM docker.io/vllm/vllm-openai@sha256:befccf0e7e4089aa23926bb6f887a85c0d46c2a99e6de5c5ffdf5cb7957c5b34 AS fetch
COPY ref-serve/inputs.lock /fetch/inputs.lock

FROM docker.io/vllm/vllm-openai@sha256:befccf0e7e4089aa23926bb6f887a85c0d46c2a99e6de5c5ffdf5cb7957c5b34
COPY --from=fetch /fetch/ /opt/iproofs/fetch/
COPY fake/write_inputs.py /opt/iproofs/write_inputs.py
COPY ref-serve/entrypoint /opt/ref-serve/entrypoint
COPY ref-serve/system.yaml /opt/iproofs/system.yaml
RUN --network=none useradd --uid 10001 --no-create-home adapter \
 && python3 /opt/iproofs/write_inputs.py /opt/iproofs/fetch/inputs.lock /opt/iproofs/inputs.json \
 && python3 -c "import json, os; json.dump(sorted(f'{k}={v}' for k, v in os.environ.items() if k.startswith(('VLLM_', 'NCCL_', 'CUDA_', 'TORCH_'))), open('/opt/iproofs/image_env.json', 'w'))"
ARG IPROOFS_ADAPTER_COMMIT=unknown
ARG IPROOFS_ADAPTER_DIRTY=true
ENV IPROOFS_ADAPTER_COMMIT=${IPROOFS_ADAPTER_COMMIT} IPROOFS_ADAPTER_DIRTY=${IPROOFS_ADAPTER_DIRTY}
USER 10001
ENTRYPOINT ["python3", "/opt/ref-serve/entrypoint"]
