"""Servidor web: uvicorn polygrafo.main:app --reload

As análises demoram vários minutos, por isso correm em segundo plano:
POST /api/check devolve um id e a página consulta GET /api/jobs/{id} até terminar.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from .analyzer import AnalysisError, Polygrafo
from .auth import basic_auth_middleware
from .config import Settings, get_settings
from .ingest import fetch_post
from .models import Post

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
app = FastAPI(title="Polígrafo pessoal", version="0.2.0", docs_url=None, redoc_url=None, openapi_url=None)
app.middleware("http")(basic_auth_middleware)

STATIC = Path(__file__).parent / "static"
MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
JOB_TTL_SECONDS = 2 * 60 * 60

_executor = ThreadPoolExecutor(max_workers=2)
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/api/extract", response_model=Post)
async def extract(url: str = Form(...)) -> Post:
    """Só extrai a publicação (útil para confirmar o que foi lido antes de analisar)."""
    return await run_in_threadpool(fetch_post, url, get_settings().transcribe)


def _error_message(e: Exception) -> str:
    if isinstance(e, AnalysisError):
        return str(e)
    if isinstance(e, anthropic.AuthenticationError):
        return "ANTHROPIC_API_KEY inválida."
    if isinstance(e, TypeError) and "authentication" in str(e):
        # O SDK lança TypeError quando não encontra nenhuma credencial.
        return "ANTHROPIC_API_KEY em falta (defina-a no ficheiro .env ou no ambiente)."
    if isinstance(e, anthropic.RateLimitError):
        return "Limite de pedidos da Claude API atingido. Tente mais tarde."
    if isinstance(e, anthropic.APIStatusError):
        return f"Erro da Claude API: {e.message}"
    if isinstance(e, anthropic.APIConnectionError):
        return "Sem ligação à Claude API."
    log.exception("Erro inesperado na análise")
    return "Erro inesperado no servidor."


def _run_job(job_id: str, settings: Settings, url: str | None, text: str | None,
             img_bytes: bytes | None, img_type: str) -> None:
    job = _jobs[job_id]
    try:
        if url:
            job["stage"] = "A ler a publicação…"
            post = fetch_post(url, settings.transcribe)
        else:
            post = Post(platform="captura de ecrã" if img_bytes else "texto colado")
        if text and text.strip():
            # O texto colado pelo utilizador complementa (ou substitui) o extraído.
            post.text = (post.text + "\n\n" + text.strip()).strip() if post.text else text.strip()
        job["stage"] = "A identificar afirmações, pesquisar fontes e cruzar informação…"
        report = Polygrafo(settings).analyze(post, img_bytes, img_type)
        job.update(status="done", result=report.model_dump(mode="json"))
    except Exception as e:  # o erro é devolvido à página em vez de se perder na thread
        job.update(status="error", error=_error_message(e))


def _prune_jobs(now: float) -> None:
    with _jobs_lock:
        for jid in [j for j, v in _jobs.items() if now - v["created"] > JOB_TTL_SECONDS]:
            del _jobs[jid]


@app.post("/api/check", status_code=202)
async def check(
    url: str | None = Form(None),
    text: str | None = Form(None),
    image: UploadFile | None = File(None),
) -> dict:
    if not (url or (text and text.strip()) or (image is not None and image.filename)):
        raise HTTPException(400, "Indique um link, texto ou imagem.")
    img_bytes, img_type = None, "image/png"
    if image is not None and image.filename:
        if image.content_type not in IMAGE_TYPES:
            raise HTTPException(400, "Formato de imagem não suportado (use PNG, JPEG, WEBP ou GIF).")
        img_bytes = await image.read()
        if len(img_bytes) > MAX_IMAGE_BYTES:
            raise HTTPException(400, "Imagem demasiado grande (máx. 5 MB).")
        img_type = image.content_type

    now = time.time()
    _prune_jobs(now)
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {"status": "running", "stage": "Na fila…", "created": now}
    _executor.submit(_run_job, job_id, get_settings(), url, text, img_bytes, img_type)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Análise não encontrada (o servidor pode ter reiniciado). Volte a verificar.")
    return {k: v for k, v in job.items() if k != "created"}
