"""Handoff para o WhatsApp (F6, D77).

O servidor decide, a partir do que a E7 já grava (ai_usage, ai_interactions) e da própria mensagem, se a resposta
do chat ganha a ação `{type: "handoff", reason, url, label}`. A conversa é a sessão anônima (session_hash) ou o
aluno no dia de São Paulo. O texto da url é fixo e só cita o curso roteado; nunca leva texto do usuário, nome,
e-mail ou id. O número (WHATSAPP_HANDOFF_NUMBER) e o orçamento (CHAT_TOKEN_BUDGET) são lidos do ambiente a cada
requisição e o número nunca vai ao log.
"""

import os
import re
from typing import Dict, Optional
from urllib.parse import quote

from agents.ai_observability import CANAL_ALUNO, CANAL_ANONIMO, hash_da_sessao
from agents.llm_guard import normalizar
from db import Database

VAR_NUMERO = "WHATSAPP_HANDOFF_NUMBER"
VAR_ORCAMENTO = "CHAT_TOKEN_BUDGET"
ORCAMENTO_PADRAO = 20000
FRACAO_ORCAMENTO = 0.8
FALHAS_SEGUIDAS = 2
NAO_ENTENDI_SEGUIDOS = 3
MIN_DIGITOS, MAX_DIGITOS = 10, 15

LABEL_HANDOFF = "Falar com um atendente no WhatsApp"
TEXTO_HANDOFF = "Olá! Vim do assistente virtual da Global Training e gostaria de falar com um atendente sobre {alvo}."
ALVO_GERAL = "os cursos"

# Prioridade da D77 (uma ação só).
MOTIVOS = ("user_request", "llm_failures", "token_budget", "unresolved")

_SEPARADORES = re.compile(r"[\s+\-()]")
_PEDIDO_HUMANO = re.compile(r"\b(atendentes?|humanos?|pessoas?|whatsapp|suporte|falar com alguem)\b")


def numero_configurado() -> Optional[str]:
    """Dígitos do número do PM, ou None (handoff desligado) se ausente ou fora de 10..15 dígitos."""
    bruto = os.getenv(VAR_NUMERO)
    if not bruto:
        return None
    digitos = _SEPARADORES.sub("", bruto)
    if not digitos.isascii() or not digitos.isdigit() or not MIN_DIGITOS <= len(digitos) <= MAX_DIGITOS:
        return None
    return digitos


def orcamento_configurado() -> int:
    bruto = (os.getenv(VAR_ORCAMENTO) or "").strip()
    try:
        valor = int(bruto)
    except ValueError:
        return ORCAMENTO_PADRAO
    return valor if valor > 0 else ORCAMENTO_PADRAO


def pede_atendimento_humano(mensagem: str) -> bool:
    return bool(_PEDIDO_HUMANO.search(normalizar(mensagem)))


def _identidade(user_id: Optional[int], session_id: Optional[str]) -> Dict:
    if user_id is not None:
        return {"channel": CANAL_ALUNO, "user_id": user_id, "session_hash": None}
    return {"channel": CANAL_ANONIMO, "user_id": None, "session_hash": hash_da_sessao(session_id or "")}


def _motivo(mensagem: str, identidade: Dict) -> Optional[str]:
    if pede_atendimento_humano(mensagem):
        return "user_request"
    ultimas = Database.get_conversation_outcomes(limit=NAO_ENTENDI_SEGUIDOS, **identidade)
    if len(ultimas) >= FALHAS_SEGUIDAS and all(o == "llm_error" for o in ultimas[:FALHAS_SEGUIDAS]):
        return "llm_failures"
    if Database.get_conversation_tokens(**identidade) >= FRACAO_ORCAMENTO * orcamento_configurado():
        return "token_budget"
    if len(ultimas) >= NAO_ENTENDI_SEGUIDOS and all(o == "unresolved" for o in ultimas[:NAO_ENTENDI_SEGUIDOS]):
        return "unresolved"
    return None


def acoes_de_handoff(mensagem: str, *, user_id: Optional[int] = None, session_id: Optional[str] = None,
                     course_id: Optional[str] = None, course_name: Optional[str] = None) -> list:
    """Lista com a ação de handoff (0 ou 1 item) para a mensagem já processada; grava ai_handoffs quando emite.

    `user_id` vem só do JWT (aluno); sem ele, a conversa é a sessão anônima `session_id` (emitida pelo servidor).
    Qualquer falha de leitura ou gravação desliga o handoff desta resposta, sem derrubar o chat.
    """
    numero = numero_configurado()
    if numero is None:
        return []
    try:
        identidade = _identidade(user_id, session_id)
        motivo = _motivo(mensagem, identidade)
        if motivo is None:
            return []
        alvo = f"o curso {course_name}" if course_id and course_name else ALVO_GERAL
        texto = TEXTO_HANDOFF.format(alvo=alvo)
        url = f"https://wa.me/{numero}?text={quote(texto, safe='')}"
        Database.add_ai_handoff(reason=motivo, course_id=course_id, **identidade)
    except Exception as e:
        print(f"Error evaluating handoff: {type(e).__name__}")
        return []
    return [{"type": "handoff", "reason": motivo, "url": url, "label": LABEL_HANDOFF}]
