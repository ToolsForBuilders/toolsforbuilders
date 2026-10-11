"""Servidor web local: uvicorn polygrafo.main:app --reload"""

from __future__ import annotations

import logging
from pathlib import Path

import anthropic
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from .analyzer import AnalysisError, Polygrafo
from .config import get_settings
from .ingest import fetch_post
from .models import Post, Report

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Polígrafo pessoal", version="0.1.0")
STATIC = Path(__file__).parent / "static"
MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.post("/api/extract", response_model=Post)
async def extract(url: str = Form(...)) -> Post:
    """Só extrai a publicação (útil para confirmar o que foi lido antes de analisar)."""
    return await run_in_threadpool(fetch_post, url, get_settings().transcribe)


@app.post("/api/check", response_model=Report)
async def check(
    url: str | None = Form(None),
    text: str | None = Form(None),
    image: UploadFile | None = File(None),
) -> Report:
    settings = get_settings()
    if url:
        post = await run_in_threadpool(fetch_post, url, settings.transcribe)
    else:
        post = Post(platform="texto colado")
    if text and text.strip():
        # O texto colado pelo utilizador complementa (ou substitui) o extraído.
        post.text = (post.text + "\n\n" + text.strip()).strip() if post.text else text.strip()

    img_bytes, img_type = None, "image/png"
    if image is not None and image.filename:
        if image.content_type not in IMAGE_TYPES:
            raise HTTPException(400, "Formato de imagem não suportado (use PNG, JPEG, WEBP ou GIF).")
        img_bytes = await image.read()
        if len(img_bytes) > MAX_IMAGE_BYTES:
            raise HTTPException(400, "Imagem demasiado grande (máx. 5 MB).")
        img_type = image.content_type
        if post.platform == "texto colado" and not url:
            post.platform = "captura de ecrã"

    try:
        return await run_in_threadpool(Polygrafo(settings).analyze, post, img_bytes, img_type)
    except AnalysisError as e:
        raise HTTPException(422, str(e))
    except anthropic.AuthenticationError:
        raise HTTPException(500, "ANTHROPIC_API_KEY inválida.")
    except TypeError as e:
        # O SDK lança TypeError quando não encontra nenhuma credencial.
        if "authentication" not in str(e):
            raise
        raise HTTPException(500, "ANTHROPIC_API_KEY em falta (defina-a no ficheiro .env ou no ambiente).")
    except anthropic.RateLimitError:
        raise HTTPException(429, "Limite de pedidos da Claude API atingido. Tente mais tarde.")
    except anthropic.APIStatusError as e:
        raise HTTPException(502, f"Erro da Claude API: {e.message}")
    except anthropic.APIConnectionError:
        raise HTTPException(502, "Sem ligação à Claude API.")
