"""Limite de taxa em memória (S9, D79): chat anônimo e checkouts.

- POST /api/chat: 30 mensagens por minuto por IP -> 429 ERRO_CHAT.
- Checkouts (aluno logado e landing): 10 por minuto por IP e, no fluxo logado, também por aluno -> 429 ERRO_CHECKOUT.

Janela deslizante de 1 minuto. Tentativa barrada não conta. O estado é zerado no startup do app
(`redefinir_limites()`). O IP é `request.client.host`; X-Forwarded-For não é considerado.
"""

import threading
import time
from collections import deque
from typing import Deque, Dict, Hashable, Iterable, Optional

from fastapi import Request

ERRO_CHAT = "Muitas mensagens em pouco tempo. Aguarde um instante."
ERRO_CHECKOUT = "Muitas tentativas de compra em pouco tempo. Aguarde um instante."
JANELA_SEGUNDOS = 60.0
LIMITE_CHAT_POR_IP = 30
LIMITE_CHECKOUT = 10
_MAX_CHAVES = 10_000  # acima disso, chaves sem registro na janela são descartadas

_trava = threading.Lock()
_registros: Dict[Hashable, Deque[float]] = {}


def redefinir_limites() -> None:
    """Zera todo o estado em memória (startup do app)."""
    with _trava:
        _registros.clear()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client and request.client.host else None


def _podar(fila: Deque[float], limite_inferior: float) -> None:
    while fila and fila[0] <= limite_inferior:
        fila.popleft()


def _consumir(chaves: Iterable[Hashable], limite: int) -> bool:
    """Registra uma ocorrência em todas as chaves se nenhuma estiver no limite; senão não registra nada."""
    agora = time.monotonic()
    inicio = agora - JANELA_SEGUNDOS
    with _trava:
        if len(_registros) > _MAX_CHAVES:
            for chave in list(_registros):
                _podar(_registros[chave], inicio)
                if not _registros[chave]:
                    del _registros[chave]
        filas = []
        for chave in chaves:
            fila = _registros.setdefault(chave, deque())
            _podar(fila, inicio)
            if len(fila) >= limite:
                return False
            filas.append(fila)
        for fila in filas:
            fila.append(agora)
        return True


def permitir_chat(request: Request) -> bool:
    ip = _ip(request)
    if ip is None:
        return True
    return _consumir([("chat", "ip", ip)], LIMITE_CHAT_POR_IP)


def permitir_checkout(request: Request, user_id: Optional[int] = None) -> bool:
    chaves = []
    ip = _ip(request)
    if ip is not None:
        chaves.append(("checkout", "ip", ip))
    if user_id is not None:
        chaves.append(("checkout", "user", user_id))
    return _consumir(chaves, LIMITE_CHECKOUT)
