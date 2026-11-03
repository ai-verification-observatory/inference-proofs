# fake-broken (RFC-0005 §Reference implementations). Build with the systems/ directory as context:
#   docker build -f systems/fake-broken/Dockerfile systems
FROM docker.io/library/python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30
COPY fake/entrypoint /opt/fake-broken/fake-entrypoint
COPY fake-broken/entrypoint /opt/fake-broken/entrypoint
RUN useradd --uid 10001 --no-create-home adapter
USER 10001
ENTRYPOINT ["python3", "/opt/fake-broken/entrypoint"]
