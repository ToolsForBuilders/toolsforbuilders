"""Proteção por senha (HTTP Basic) para quando a app está publicada online.

- Ativa quando POLYGRAFO_PASSWORD está definida.
- Com POLYGRAFO_REQUIRE_PASSWORD=1 (definido na configuração do Render) e sem
  senha configurada, a app recusa todos os pedidos: nunca fica aberta por engano.
- Após MAX_FAILURES tentativas erradas, o IP fica bloqueado durante LOCKOUT_SECONDS.

HTTP Basic só é seguro sobre HTTPS (o Render fornece HTTPS automaticamente).
"""

from __future__ import annotations

import base64
import binascii
import os
import secrets
import time

from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

MAX_FAILURES = 5
LOCKOUT_SECONDS = 15 * 60
MIN_PASSWORD_LENGTH = 12

_failures: dict[str, list[float]] = {}


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "?"


def _locked(ip: str, now: float) -> bool:
    recent = [t for t in _failures.get(ip, []) if now - t < LOCKOUT_SECONDS]
    _failures[ip] = recent
    return len(recent) >= MAX_FAILURES


def _credentials_ok(header: str, user: str, password: str) -> bool:
    scheme, _, encoded = header.partition(" ")
    if scheme.lower() != "basic" or not encoded:
        return False
    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    given_user, sep, given_password = decoded.partition(":")
    if not sep:
        return False
    # Compara sempre os dois campos para não revelar qual falhou.
    user_ok = secrets.compare_digest(given_user.encode(), user.encode())
    password_ok = secrets.compare_digest(given_password.encode(), password.encode())
    return user_ok and password_ok


def _challenge(message: str) -> Response:
    return PlainTextResponse(
        message, status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="Poligrafo", charset="UTF-8"'},
    )


async def basic_auth_middleware(request: Request, call_next):
    if request.url.path == "/health":
        # Verificação de saúde do alojamento: não expõe dados.
        return await call_next(request)
    password = os.getenv("POLYGRAFO_PASSWORD", "")
    required = os.getenv("POLYGRAFO_REQUIRE_PASSWORD") == "1"
    if not password:
        if required:
            return PlainTextResponse("Defina POLYGRAFO_PASSWORD para ativar a aplicação.", status_code=503)
        return await call_next(request)
    if len(password) < MIN_PASSWORD_LENGTH:
        return PlainTextResponse(
            f"POLYGRAFO_PASSWORD demasiado curta (mínimo {MIN_PASSWORD_LENGTH} caracteres).", status_code=503,
        )

    ip, now = _client_ip(request), time.time()
    if _locked(ip, now):
        return PlainTextResponse("Demasiadas tentativas. Tente daqui a 15 minutos.", status_code=429)

    header = request.headers.get("authorization", "")
    user = os.getenv("POLYGRAFO_USER", "eu")
    if not _credentials_ok(header, user, password):
        if header:
            _failures.setdefault(ip, []).append(now)
        return _challenge("Autenticação necessária.")
    return await call_next(request)
