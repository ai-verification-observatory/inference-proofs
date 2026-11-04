# Recompute reference adapter (RFC-0015 §Recompute): the ref-serve entrypoint with this
# system.yaml (`reference_role: recompute`), built by the RFC-0014 rules: B1 every FROM by
# digest (vLLM v0.32.0, RFC-0015 Q1); B2 one `fetch` stage, every download in inputs.lock;
# B3 `RUN --network=none` after it; B5 /opt/iproofs/inputs.json; B6 the adapter commit and
# dirty flag as build arguments. Build with the systems/ directory as context:
#   docker build --build-arg IPROOFS_ADAPTER_COMMIT=$(git rev-parse HEAD) \
#     --build-arg IPROOFS_ADAPTER_DIRTY=$(test -z "$(git status --porcelain)" && echo false || echo true) \
#     -f systems/ref-recompute/Dockerfile systems
FROM docker.io/vllm/vllm-openai@sha256:befccf0e7e4089aa23926bb6f887a85c0d46c2a99e6de5c5ffdf5cb7957c5b34 AS fetch
COPY ref-recompute/inputs.lock /fetch/inputs.lock
ADD --checksum=sha256:e795779830ad8907cb0e51bf661dd7784ebaf244b0b324af07a8d3925b6a9739 https://files.pythonhosted.org/packages/0b/1f/55b5023c20ef8c30c8099d713aa2be94783d7a67aa31f87963779d82f5c6/vllm_gguf_plugin-0.0.5-cp310-abi3-manylinux_2_28_x86_64.whl /fetch/
ADD --checksum=sha256:70bcd10edfe697fb2dad6e40af2234b9d8ece9a41a99761405121ebda1c3c1cd https://files.pythonhosted.org/packages/b3/bb/d71d6da82763528c2c2ed6b59a9d6142c6595545a4c448e2085d155e88c2/gguf-0.19.0-py3-none-any.whl /fetch/

FROM docker.io/vllm/vllm-openai@sha256:befccf0e7e4089aa23926bb6f887a85c0d46c2a99e6de5c5ffdf5cb7957c5b34
COPY --from=fetch /fetch/ /opt/iproofs/fetch/
COPY fake/write_inputs.py /opt/iproofs/write_inputs.py
COPY ref-serve/entrypoint /opt/ref-serve/entrypoint
COPY ref-recompute/system.yaml /opt/iproofs/system.yaml
RUN --network=none python3 -m pip install --no-deps --no-index --find-links=/opt/iproofs/fetch \
    vllm-gguf-plugin==0.0.5 gguf==0.19.0 \
 && useradd --uid 10001 --no-create-home adapter \
 && python3 /opt/iproofs/write_inputs.py /opt/iproofs/fetch/inputs.lock /opt/iproofs/inputs.json
ARG IPROOFS_ADAPTER_COMMIT=unknown
ARG IPROOFS_ADAPTER_DIRTY=true
ENV IPROOFS_ADAPTER_COMMIT=${IPROOFS_ADAPTER_COMMIT} IPROOFS_ADAPTER_DIRTY=${IPROOFS_ADAPTER_DIRTY}
USER 10001
ENTRYPOINT ["python3", "/opt/ref-serve/entrypoint"]
