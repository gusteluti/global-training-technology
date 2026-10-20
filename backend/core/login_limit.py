"""Limite de tentativas de login (S2, D79).

5 falhas do mesmo e-mail (normalizado: aparado e sem caixa) em 15 min bloqueiam o e-mail por 15 min; 20 falhas do
mesmo IP em 15 min bloqueiam o IP por 15 min. Bloqueado: 429 com ERRO_LOGIN, mesmo com a senha certa. E-mail
inexistente conta igual (sem enumeração). Estado na tabela `login_attempts` (sobrevive a restart). O primeiro
bloqueio de cada janela grava `auth.locked` (e-mail mascarado ou IP; nunca a senha).
O IP é `request.client.host`; X-Forwarded-For não é considerado.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from fastapi import HTTPException, Request

from core.audit import record_audit
from db import Database

ERRO_LOGIN = "Muitas tentativas. Tente novamente em alguns minutos."
JANELA = timedelta(minutes=15)
DURACAO_BLOQUEIO = timedelta(minutes=15)
LIMITE_POR_EMAIL = 5
LIMITE_POR_IP = 20
RETENCAO = timedelta(days=1)


def _texto_utc(instante: datetime) -> str:
    return instante.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def normalizar_email(email: Optional[str]) -> Optional[str]:
    valor = (email or "").strip().lower()
    return valor or None


def ip_do_cliente(request: Request) -> Optional[str]:
    return request.client.host if request.client and request.client.host else None


def mascarar_email(email: str) -> str:
    local, _, dominio = email.partition("@")
    inicio = local[:1] or "*"
    return f"{inicio}***@{dominio}" if dominio else f"{inicio}***"


def _chaves(email: Optional[str], ip: Optional[str]) -> List[Tuple[str, str, int]]:
    chaves = []
    if email:
        chaves.append(("email", email, LIMITE_POR_EMAIL))
    if ip:
        chaves.append(("ip", ip, LIMITE_POR_IP))
    return chaves


def exigir_nao_bloqueado(email: Optional[str], ip: Optional[str]) -> None:
    """429 se o e-mail (já normalizado) ou o IP estiverem bloqueados."""
    desde = _texto_utc(datetime.now(timezone.utc) - DURACAO_BLOQUEIO)
    if Database.login_bloqueado([(scope, key) for scope, key, _ in _chaves(email, ip)], desde):
        raise HTTPException(status_code=429, detail=ERRO_LOGIN)


def registrar_falha(email: Optional[str], ip: Optional[str]) -> None:
    """Conta a falha e, se uma chave chegou ao limite agora, grava o bloqueio e um `auth.locked`."""
    agora = datetime.now(timezone.utc)
    novos = Database.registrar_falha_de_login(
        _chaves(email, ip),
        _texto_utc(agora),
        _texto_utc(agora - JANELA),
        _texto_utc(agora - RETENCAO),
    )
    for scope, key in novos:
        if scope == "email":
            alvo = f"e-mail {mascarar_email(key)}"
            entidade = mascarar_email(key)
        else:
            alvo = f"IP {key}"
            entidade = key
        record_audit(
            "auth.locked",
            f"Login bloqueado por 15 minutos após tentativas seguidas com senha inválida ({alvo})",
            actor={},
            entity_type="login_" + scope,
            entity_id=entidade,
        )


def registrar_sucesso(email: Optional[str]) -> None:
    if email:
        Database.limpar_falhas_de_login("email", email)
