# Fake system for CI (RFC-0005 §Reference implementations). Every FROM is pinned by digest (RFC-0014 B1).
FROM docker.io/library/python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30
COPY entrypoint /opt/fake/entrypoint
RUN useradd --uid 10001 --no-create-home adapter
USER 10001
ENTRYPOINT ["python3", "/opt/fake/entrypoint"]
