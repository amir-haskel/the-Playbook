# OpsPulse — single-container image for air-gapped OpenShift.
FROM python:3.11-slim

# Non-root, OpenShift-friendly. The runtime UID is assigned by OpenShift's
# restricted SCC; group root (0) keeps the app dirs group-writable.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data \
    SCRIPTS_DIR=/scripts

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static
COPY scripts /scripts

# Create the state dir and make app/data group-writable for arbitrary UIDs.
RUN mkdir -p /data /scripts \
    && chgrp -R 0 /app /data /scripts \
    && chmod -R g=u /app /data /scripts

EXPOSE 8000
USER 1001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
