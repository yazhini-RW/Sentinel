# Runs the Sentinel engine (FastAPI backend) as a container — used for
# Hugging Face Spaces (Docker SDK) deployment. See DEPLOY.md for the
# step-by-step guide. Hugging Face Spaces expects the app to listen on 7860.

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

# Hugging Face Spaces containers must listen on 7860 and 0.0.0.0.
ENV PORT=7860
EXPOSE 7860

# Cache dir for downloaded models — writable on Spaces' persistent /data,
# falls back to a normal path if that mount isn't present (e.g. local docker run).
ENV HF_HOME=/app/.cache/huggingface

# Public-deploy posture by default: no arbitrary server-folder reads,
# a visitor can only upload files. Override at deploy time if you fork this
# into a private/trusted deployment.
ENV SENTINEL_ALLOW_SOURCES_PATH=0

CMD ["python", "-m", "uvicorn", "sentinel.api:app", "--host", "0.0.0.0", "--port", "7860"]
