"""Limite de taxa em memória (S9, D79): chat anônimo e checkouts.

- POST /api/chat: 30 mensagens por minuto por IP -> 429 ERRO_CHAT.
- POST /api/student/chat (GR3, D95): 30 mensagens por minuto por aluno (id do JWT, em qualquer IP) -> 429 ERRO_CHAT.
  Não consome o limite por IP do chat anônimo.
- Checkouts (aluno logado e landing): 10 por minuto por IP e, no fluxo logado, também por aluno -> 429 ERRO_CHECKOUT.
- POST /api/auth/password-token/check (D108): 30 checagens por minuto por IP -> 429 com o texto do limite de login
  (`login_limit.ERRO_LOGIN`).

Janela deslizante de 1 minuto. Tentativa barrada não conta. O estado é zerado no startup do app
(`redefinir_limites()`). O IP é o de `core.cliente_ip.ip_do_cliente` (par TCP; X-Forwarded-For não é considerado sem `TRUSTED_PROXIES`).

Tetos de abuso do chat anônimo (SG4, D109 P5), além dos 30 por minuto, ambos por IP efetivo, desligados por padrão e
lidos do ambiente a CADA requisição (ausente, vazio, 0, inválido ou negativo = desligado):
- `CHAT_ANON_DAILY_MESSAGES_PER_IP`: mensagens em janela deslizante de 24 h -> 429 `ERRO_CHAT`.
- `CHAT_ANON_NEW_SESSIONS_PER_IP_HOUR`: sessões novas (sem `session_id` válido emitido pelo servidor) em janela
  deslizante de 1 h -> 429 `ERRO_CHAT`; continuar uma sessão existente não conta.
Ordem de verificação em `permitir_chat`: minuto, depois diário, depois sessões novas. A verificação é atômica: se
qualquer uma barra, nada é registrado (a mensagem barrada não conta em nenhuma janela nem estende nenhuma). O estado
fica em memória do processo (um worker); o teto diário de tokens (`CHAT_ANON_DAILY_TOKEN_BUDGET`) não é daqui, usa o
banco.
"""

import os
import threading
import time
from collections import deque
from typing import Deque, Dict, Hashable, Iterable, Optional

from fastapi import Request

from core.cliente_ip import ip_do_cliente

ERRO_CHAT = "Muitas mensagens em pouco tempo. Aguarde um instante."
ERRO_CHECKOUT = "Muitas tentativas de compra em pouco tempo. Aguarde um instante."
JANELA_SEGUNDOS = 60.0
LIMITE_CHAT_POR_IP = 30
LIMITE_CHAT_POR_ALUNO = 30
LIMITE_CHECKOUT = 10
LIMITE_CHECAGEM_TOKEN_SENHA = 30
VAR_MENSAGENS_POR_IP_DIA = "CHAT_ANON_DAILY_MESSAGES_PER_IP"
VAR_SESSOES_NOVAS_POR_IP_HORA = "CHAT_ANON_NEW_SESSIONS_PER_IP_HOUR"
JANELA_DIA_SEGUNDOS = 24 * 3600.0
JANELA_HORA_SEGUNDOS = 3600.0
_MAX_CHAVES = 10_000  # acima disso, chaves sem registro na janela são descartadas

_trava = threading.Lock()
_registros: Dict[Hashable, Deque[float]] = {}
# SG4: janelas longas do chat anônimo, por IP (a poda do `_registros` usa a janela de 1 minuto e as apagaria).
_registros_dia: Dict[Hashable, Deque[float]] = {}
_registros_sessoes: Dict[Hashable, Deque[float]] = {}


def redefinir_limites() -> None:
    """Zera todo o estado em memória (startup do app)."""
    with _trava:
        _registros.clear()
        _registros_dia.clear()
        _registros_sessoes.clear()


def _ip(request: Request) -> Optional[str]:
    return ip_do_cliente(request)


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


def _limite_do_ambiente(nome: str) -> int:
    """Teto inteiro positivo da variável `nome`; ausente, vazia, 0, inválida ou negativa = 0 (desligado)."""
    bruto = (os.getenv(nome) or "").strip()
    if not bruto.isascii() or not bruto.isdecimal():
        return 0
    return int(bruto)


def _fila(registros: Dict[Hashable, Deque[float]], chave: Hashable, inicio: float) -> Deque[float]:
    """Fila da chave já podada; a poda geral só roda quando há chaves demais."""
    if len(registros) > _MAX_CHAVES:
        for outra in list(registros):
            _podar(registros[outra], inicio)
            if not registros[outra]:
                del registros[outra]
    fila = registros.setdefault(chave, deque())
    _podar(fila, inicio)
    return fila


def permitir_chat(request: Request, sessao_nova: bool = False) -> bool:
    """Chat anônimo: 30 por minuto por IP (S9) e, se ligados, os tetos diário de mensagens e de sessões novas por hora
    (SG4). `sessao_nova` diz se esta mensagem abre uma sessão (sem id válido e existente). Atômico: se qualquer teto
    barra, nenhuma janela registra a mensagem."""
    ip = _ip(request)
    if ip is None:
        return True
    teto_mensagens = _limite_do_ambiente(VAR_MENSAGENS_POR_IP_DIA)
    teto_sessoes = _limite_do_ambiente(VAR_SESSOES_NOVAS_POR_IP_HORA) if sessao_nova else 0
    agora = time.monotonic()
    with _trava:
        minuto = _fila(_registros, ("chat", "ip", ip), agora - JANELA_SEGUNDOS)
        if len(minuto) >= LIMITE_CHAT_POR_IP:
            return False
        dia = _fila(_registros_dia, ip, agora - JANELA_DIA_SEGUNDOS) if teto_mensagens else None
        if dia is not None and len(dia) >= teto_mensagens:
            return False
        sessoes = _fila(_registros_sessoes, ip, agora - JANELA_HORA_SEGUNDOS) if teto_sessoes else None
        if sessoes is not None and len(sessoes) >= teto_sessoes:
            return False
        minuto.append(agora)
        if dia is not None:
            dia.append(agora)
        if sessoes is not None:
            sessoes.append(agora)
        return True


def permitir_chat_aluno(user_id: int) -> bool:
    """Limite do chat do aluno logado (GR3): a chave é só o id do JWT, nunca o IP nem o corpo da requisição."""
    return _consumir([("chat", "user", user_id)], LIMITE_CHAT_POR_ALUNO)


def permitir_checkout(request: Request, user_id: Optional[int] = None) -> bool:
    chaves = []
    ip = _ip(request)
    if ip is not None:
        chaves.append(("checkout", "ip", ip))
    if user_id is not None:
        chaves.append(("checkout", "user", user_id))
    return _consumir(chaves, LIMITE_CHECKOUT)


def permitir_checagem_token_senha(request: Request) -> bool:
    """Checagem do link de senha (D108): limite por IP, para não virar oráculo de força bruta de tokens."""
    ip = _ip(request)
    if ip is None:
        return True
    return _consumir([("token-senha", "ip", ip)], LIMITE_CHECAGEM_TOKEN_SENHA)
