"""Sentinel web API — local backend for the Next.js UI.

Start with:  sentinel serve   (or: uvicorn sentinel.api:app)

Endpoints:
    GET  /health              liveness + which verifier tier is active
    POST /verify              run the pipeline (multipart: question, answer,
                              files[] upload and/or sources_path)
    GET  /runs                run history (newest first)
    GET  /runs/{run_id}       one run's full JSON log
    GET  /runs/{run_id}/report  the stored HTML report
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .cli import run_pipeline
from .embedder import get_embedder
from .llm import gemini_available
from .verifier import VERDICTS  # noqa: F401  (documents the verdict vocabulary)

LOG_DIR = Path("logs")
MAX_FILES = 20
MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MB per uploaded document
ALLOWED_SUFFIXES = {".txt", ".md"}
VERIFIER_CHOICES = {"auto", "gemini", "nli", "mock"}

_RUN_ID_RE = re.compile(r"^run_[0-9_]+$")

# One heavy pipeline at a time — this is a local, single-user product and the
# torch models are not meant for concurrent inference from one process.
_pipeline_lock = asyncio.Lock()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Warm the models once at startup so the first /verify isn't slow.
    await asyncio.to_thread(get_embedder)
    if not gemini_available():
        from .nli import get_nli_verifier

        await asyncio.to_thread(get_nli_verifier)
    yield


app = FastAPI(title="Sentinel API", version="1.1.0", lifespan=_lifespan)

# Extra UI origins via env: SENTINEL_CORS_ORIGINS=http://localhost:3001,...
_default_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
]
_extra_origins = [
    o.strip()
    for o in os.environ.get("SENTINEL_CORS_ORIGINS", "").split(",")
    if o.strip()
]
_allowed_origins = _default_origins + _extra_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DNS-rebinding guard: a malicious site can point its own hostname at
# 127.0.0.1 and bypass CORS entirely (same-origin then). Only accept
# requests addressed to localhost names.
# "testserver" is FastAPI TestClient's default host — not routable in practice.
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["127.0.0.1", "localhost", "::1", "testserver"],
)


def _reject_cross_site(request: Request) -> None:
    """CORS makes responses unreadable cross-origin, but a browser will still
    SEND a cross-site multipart POST (no preflight). Refuse foreign Origins so
    a malicious page can't trigger pipeline runs / log writes."""
    origin = request.headers.get("origin")
    if origin and origin not in _allowed_origins:
        raise HTTPException(403, "Cross-site requests are not allowed")


def _active_verifier() -> str:
    if gemini_available():
        return "gemini"
    from .nli import get_nli_verifier

    return "nli" if get_nli_verifier() is not None else "mock"


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "default_verifier": _active_verifier()}


async def _save_uploads(files: list[UploadFile], dest: Path) -> int:
    """Validate and write uploaded docs into dest. Returns files written."""
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"Too many files (max {MAX_FILES})")
    written = 0
    for f in files:
        name = Path(f.filename or "").name  # strip any client-sent directories
        suffix = Path(name).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise HTTPException(400, f"Unsupported file type '{name}' (only .txt/.md)")
        data = await f.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(413, f"File '{name}' exceeds {MAX_FILE_BYTES // (1024*1024)} MB")
        if not data.strip():
            continue
        # A unique prefix avoids two uploads with the same basename colliding.
        (dest / f"{written:02d}_{name}").write_bytes(data)
        written += 1
    return written


MAX_QUESTION_CHARS = 2_000
MAX_ANSWER_CHARS = 50_000


@app.post("/verify")
async def verify(
    request: Request,
    question: str = Form(...),
    answer: str = Form(...),
    verifier: str = Form("auto"),
    top_k: int = Form(3),
    sources_path: str | None = Form(None),
    files: list[UploadFile] = File(default=[]),
) -> dict:
    _reject_cross_site(request)
    question, answer = question.strip(), answer.strip()
    if not question or not answer:
        raise HTTPException(400, "Both question and answer are required")
    if len(question) > MAX_QUESTION_CHARS or len(answer) > MAX_ANSWER_CHARS:
        raise HTTPException(413, "Question or answer is too long")
    if verifier not in VERIFIER_CHOICES:
        raise HTTPException(400, f"verifier must be one of {sorted(VERIFIER_CHOICES)}")
    if not 1 <= top_k <= 20:
        raise HTTPException(400, "top_k must be between 1 and 20")

    has_uploads = any(f.filename for f in files)
    if not has_uploads and not sources_path:
        raise HTTPException(400, "Provide source documents: upload files or set sources_path")

    tmpdir: str | None = None
    try:
        if has_uploads:
            tmpdir = tempfile.mkdtemp(prefix="sentinel_upload_")
            written = await _save_uploads([f for f in files if f.filename], Path(tmpdir))
            if written == 0:
                raise HTTPException(400, "All uploaded files were empty")
            sources = tmpdir
        else:
            src = Path(sources_path)  # local product: user points at their own folder
            if not src.is_dir():
                raise HTTPException(400, f"sources_path is not a folder: {sources_path}")
            sources = str(src)

        async with _pipeline_lock:
            try:
                log = await asyncio.to_thread(
                    run_pipeline,
                    question,
                    answer,
                    sources,
                    top_k,
                    str(LOG_DIR),
                    verifier,
                    True,  # cache
                    True,  # quiet
                    True,  # html_report
                )
            except FileNotFoundError as e:
                raise HTTPException(400, str(e)) from e
            except RuntimeError as e:
                raise HTTPException(400, str(e)) from e
        # Uploaded docs live in a temp dir; record friendly names instead.
        if tmpdir:
            log["input"]["sources_folder"] = "(uploaded files)"
        return log
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)


def _summarize(path: Path) -> dict | None:
    try:
        log = json.loads(path.read_text(encoding="utf-8"))
        result = log.get("result", {}) or {}
        return {
            "run_id": log.get("run_id", path.stem),
            "timestamp": log.get("timestamp"),
            "trust_score": result.get("trust_score"),
            "verdict_counts": result.get("verdict_counts", {}),
            "question": (log.get("input", {}) or {}).get("question", ""),
            "verifier": (log.get("config", {}) or {}).get("verifier", "auto"),
        }
    except (OSError, json.JSONDecodeError):
        return None  # skip corrupt/foreign files silently


@app.get("/runs")
async def runs(limit: int = 50) -> list[dict]:
    limit = max(1, min(limit, 500))
    files = sorted(LOG_DIR.glob("run_*.json"), reverse=True)[:limit]
    return [s for s in (_summarize(p) for p in files) if s]


def _run_file(run_id: str, suffix: str) -> Path:
    if not _RUN_ID_RE.match(run_id):  # blocks path traversal
        raise HTTPException(400, "Invalid run id")
    path = (LOG_DIR / run_id).with_suffix(suffix)
    if not path.is_file():
        raise HTTPException(404, f"Run {run_id} not found")
    return path


@app.get("/runs/{run_id}")
async def run_detail(run_id: str) -> dict:
    path = _run_file(run_id, ".json")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(500, f"Run log is corrupt: {e}") from e


@app.get("/runs/{run_id}/report")
async def run_report(run_id: str) -> FileResponse:
    return FileResponse(_run_file(run_id, ".html"), media_type="text/html")
