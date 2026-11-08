# Plain-serving reference adapter for the Maverick workloads on llama.cpp (RFC-0015 SRV-6, SRV-7),
# built by the RFC-0014 rules: B1 every FROM by digest (llama.cpp v0.9.0, build b12110, the
# server-cuda image; ghcr.io/ggml-org/llama.cpp:server-cuda-b12110 when pinned); B2 one `fetch`
# stage, every download in inputs.lock; B3 `RUN --network=none` after it; B5
# /opt/iproofs/inputs.json; B6 the adapter commit and dirty flag as build arguments. The engine
# image has Python 3.12 without pip, so the PyYAML wheel is extracted, not installed. Build with
# the systems/ directory as context:
#   docker build --build-arg IPROOFS_ADAPTER_COMMIT=$(git rev-parse HEAD) \
#     --build-arg IPROOFS_ADAPTER_DIRTY=$(test -z "$(git status --porcelain)" && echo false || echo true) \
#     -f systems/ref-serve-gguf/Dockerfile systems
FROM ghcr.io/ggml-org/llama.cpp@sha256:a2963b4817f03eea7e0d6065ea576252322792441ef97aaae178b924520547d6 AS fetch
COPY ref-serve-gguf/inputs.lock /fetch/inputs.lock
ADD --checksum=sha256:ba1cc08a7ccde2d2ec775841541641e4548226580ab850948cbfda66a1befcdc https://files.pythonhosted.org/packages/8b/9d/b3589d3877982d4f2329302ef98a8026e7f4443c765c46cfecc8858c6b4b/pyyaml-6.0.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl /fetch/

FROM ghcr.io/ggml-org/llama.cpp@sha256:a2963b4817f03eea7e0d6065ea576252322792441ef97aaae178b924520547d6
COPY --from=fetch /fetch/ /opt/iproofs/fetch/
COPY fake/write_inputs.py /opt/iproofs/write_inputs.py
COPY ref-serve-gguf/entrypoint /opt/ref-serve-gguf/entrypoint
COPY ref-serve-gguf/system.yaml /opt/iproofs/system.yaml
RUN --network=none python3 -m zipfile -e \
    /opt/iproofs/fetch/pyyaml-6.0.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl \
    /opt/ref-serve-gguf/site \
 && useradd --uid 10001 --no-create-home adapter \
 && python3 /opt/iproofs/write_inputs.py /opt/iproofs/fetch/inputs.lock /opt/iproofs/inputs.json \
    llama.cpp=b12110 \
 && python3 -c 'import sys; sys.path.insert(0, "/opt/ref-serve-gguf/site"); import yaml; print("PyYAML", yaml.__version__)'
ARG IPROOFS_ADAPTER_COMMIT=unknown
ARG IPROOFS_ADAPTER_DIRTY=true
ENV IPROOFS_ADAPTER_COMMIT=${IPROOFS_ADAPTER_COMMIT} IPROOFS_ADAPTER_DIRTY=${IPROOFS_ADAPTER_DIRTY}
USER 10001
ENTRYPOINT ["python3", "/opt/ref-serve-gguf/entrypoint"]
