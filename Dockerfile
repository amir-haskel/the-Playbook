# syntax=docker/dockerfile:1
# The Playbook — single-container image for (air-gapped) Kubernetes / OpenShift.
#
# Scripts are NOT baked in: the Helm chart renders charts/playbook/scripts into
# a ConfigMap and mounts it at /scripts, so automation changes ship without an
# image rebuild.

ARG PYTHON_VERSION=3.11

# ---- build stage: resolve dependencies into an isolated virtualenv ----------
FROM python:${PYTHON_VERSION}-slim AS build
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.txt .
RUN pip install --require-virtualenv -r requirements.txt

# ---- runtime stage -----------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ARG VERSION=dev
ARG REVISION=unknown
LABEL org.opencontainers.image.title="playbook" \
      org.opencontainers.image.description="Self-service developer portal: one-click, parameterised scripts with live logs" \
      org.opencontainers.image.source="https://github.com/amir-haskel/devops-dashboard" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}"

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data \
    SCRIPTS_DIR=/scripts

COPY --from=build /opt/venv /opt/venv

WORKDIR /app
COPY app ./app
COPY static ./static

# OpenShift runs containers with an arbitrary UID in group 0, so writable paths
# are group-owned by root and group-writable. App code stays read-only.
RUN mkdir -p /data/db /data/store /scripts \
    && chgrp -R 0 /data /scripts \
    && chmod -R g=u /data /scripts

USER 1001
EXPOSE 8000

# Exec form so uvicorn is PID 1 and receives SIGTERM directly.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
