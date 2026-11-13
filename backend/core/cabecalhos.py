"""Cabeçalhos de segurança da API (SG1, D109).

Uma função compartilhada (`aplicar_cabecalhos`) decide os cabeçalhos de toda resposta; dois pontos de entrada a usam:

- `CabecalhosSeguranca`: middleware ASGI puro (não `BaseHTTPMiddleware`, que quebra streaming e FileResponse), ligado
  como o mais externo das middlewares do app: cobre 401/404/405/422/429, o preflight do CORS e os arquivos.
- `erro_interno`: handler de `Exception`. O `ServerErrorMiddleware` do Starlette responde o 500 de exceção não tratada
  fora das middlewares comuns, então o handler aplica a mesma função e devolve mensagem genérica (nada do texto da
  exceção chega ao cliente).
"""

import os
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders

CABECALHOS_BASE = (
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
    ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
)
CSP_JSON = "default-src 'none'; frame-ancestors 'none'"
HSTS = "max-age=31536000; includeSubDomains"

# Rotas de conta: a resposta (inclusive o erro) nunca fica em cache. `/api/token` é exato; os demais são prefixos de
# caminho inteiro (`/api/student` casa `/api/student/me`, mas `/api/students-x` não casa).
NO_STORE_EXATOS = ("/api/token",)
NO_STORE_PREFIXOS = ("/api/auth", "/api/admin", "/api/dashboard", "/api/student")


def ambiente() -> str:
    """APP_ENV normalizado (sem caixa, aparado). Ausente vira vazio, que conta como produção para a documentação."""
    return (os.getenv("APP_ENV") or "").strip().lower()


def documentacao_habilitada() -> bool:
    """`/docs`, `/redoc` e `/openapi.json` só em development e test."""
    return ambiente() in ("development", "test")


def _no_store(caminho: str) -> bool:
    if caminho in NO_STORE_EXATOS:
        return True
    return any(caminho == prefixo or caminho.startswith(prefixo + "/") for prefixo in NO_STORE_PREFIXOS)


def aplicar_cabecalhos(cabecalhos: MutableHeaders, caminho: str) -> None:
    """Aplica os cabeçalhos de segurança a uma resposta. Substitui valor existente de mesmo nome (aparece uma vez)."""
    for nome, valor in CABECALHOS_BASE:
        cabecalhos[nome] = valor
    tipo = (cabecalhos.get("content-type") or "").lower()
    if "application/json" in tipo:
        cabecalhos["Content-Security-Policy"] = CSP_JSON
    if _no_store(caminho) and "cache-control" not in cabecalhos:
        cabecalhos["Cache-Control"] = "no-store"
    if ambiente() == "production":
        cabecalhos["Strict-Transport-Security"] = HSTS


class CabecalhosSeguranca:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        caminho = scope.get("path") or ""

        async def enviar(mensagem):
            if mensagem["type"] == "http.response.start":
                aplicar_cabecalhos(MutableHeaders(scope=mensagem), caminho)
            await send(mensagem)

        await self.app(scope, receive, enviar)


async def erro_interno(request: Request, _erro: Exception) -> JSONResponse:
    """500 de exceção não tratada: mensagem genérica, com os mesmos cabeçalhos das demais respostas."""
    resposta = JSONResponse(status_code=500, content={"detail": "Erro interno do servidor."})
    aplicar_cabecalhos(resposta.headers, request.url.path)
    return resposta
