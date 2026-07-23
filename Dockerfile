# Runs the Sentinel engine (FastAPI backend) as a container. Works on both
# Google Cloud Run and Hugging Face Spaces (Docker SDK) — see DEPLOY.md.
# Both platforms inject a PORT env var the container must listen on
# (Cloud Run picks one dynamically; Spaces always uses 7860), so the CMD
# below reads $PORT at startup rather than hardcoding either.

FROM python:3.11-slim

# Torch/sentence-transformers need these for wheel installs on slim images.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps first so Docker caches this layer across code-only changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sentinel ./sentinel
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir -e .

# Default port for local `docker run` / Hugging Face Spaces; Cloud Run
# overrides this at runtime with its own PORT value automatically.
ENV PORT=7860
EXPOSE 7860

# Cache dir for downloaded models — writable on Spaces' persistent /data,
# falls back to a normal path if that mount isn't present (e.g. local docker run).
ENV HF_HOME=/app/.cache/huggingface

# Public-deploy posture by default: no arbitrary server-folder reads,
# a visitor can only upload files. Override at deploy time if you fork this
# into a private/trusted deployment.
ENV SENTINEL_ALLOW_SOURCES_PATH=0

# Shell form so ${PORT} is expanded at container start, not build time.
CMD python -m uvicorn sentinel.api:app --host 0.0.0.0 --port ${PORT}
