"""Observabilidade de IA (E7, D42): contexto da chamada, custo, mascaramento e gravação em banco.

O contexto (canal, usuário, hash da sessão anônima, tipo de chamada) viaja por `contextvars`, para que
`GroqChatClient.create_chat_completion` grave o `usage` sem mudar a assinatura. O contexto precisa ser
definido na mesma thread que chama o LLM (o endpoint do aluno é `def` síncrono, rodando em threadpool).

Nada aqui grava texto de mensagem de aluno, texto de exceção ou id cru de sessão. Falha de gravação nunca
derruba o chat: só o tipo da exceção vai ao log.
"""

import hashlib
import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional

from db import Database

CANAL_ANONIMO = "anonymous"
CANAL_ALUNO = "student"

PRECO_ENTRADA_PADRAO = 0.15  # USD por 1 milhão de tokens (referência; conferir a tabela de preços da Groq)
PRECO_SAIDA_PADRAO = 0.75

TAMANHO_SESSION_HASH = 16
TAMANHO_MAXIMO_TOPICO = 120

_identidade: ContextVar[Optional[dict]] = ContextVar("ai_identidade", default=None)
_tipo_de_chamada: ContextVar[str] = ContextVar("ai_tipo_de_chamada", default="answer")

_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_NUMERO_LONGO = re.compile(r"\d{5,}")


def hash_da_sessao(session_id: str) -> str:
    """Prefixo do sha256 hex do id da sessão anônima. O id cru nunca é gravado."""
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:TAMANHO_SESSION_HASH]


def mascarar_topico(texto: str) -> str:
    """E-mails viram [email], 5 ou mais dígitos seguidos viram [num], minúsculas, até 120 caracteres."""
    mascarado = _EMAIL.sub("[email]", texto or "")
    mascarado = _NUMERO_LONGO.sub("[num]", mascarado)
    return mascarado.lower()[:TAMANHO_MAXIMO_TOPICO].strip()


@contextmanager
def identidade_anonima(session_id: str):
    """Marca as chamadas ao LLM e as interações do bloco como do canal anônimo."""
    token = _identidade.set({"channel": CANAL_ANONIMO, "user_id": None, "session_hash": hash_da_sessao(session_id)})
    try:
        yield
    finally:
        _identidade.reset(token)


@contextmanager
def identidade_aluno(user_id: int):
    """Marca as chamadas ao LLM e as interações do bloco como do aluno logado. `user_id` vem só do JWT."""
    token = _identidade.set({"channel": CANAL_ALUNO, "user_id": user_id, "session_hash": None})
    try:
        yield
    finally:
        _identidade.reset(token)


@contextmanager
def tipo_de_chamada(tipo: str):
    """'route' (roteamento de curso) ou 'answer' (resposta ao usuário, o padrão)."""
    token = _tipo_de_chamada.set(tipo)
    try:
        yield
    finally:
        _tipo_de_chamada.reset(token)


def identidade_atual() -> Optional[dict]:
    return _identidade.get()


def _preco(nome: str, padrao: float) -> float:
    bruto = os.getenv(nome)
    if bruto is None or not bruto.strip():
        return padrao
    try:
        return float(bruto)
    except ValueError:
        return padrao


def calcular_custo(prompt_tokens: int, completion_tokens: int) -> float:
    """Custo em USD na hora da chamada. Preços lidos do ambiente a cada chamada."""
    preco_entrada = _preco("GROQ_PRICE_INPUT_PER_1M_USD", PRECO_ENTRADA_PADRAO)
    preco_saida = _preco("GROQ_PRICE_OUTPUT_PER_1M_USD", PRECO_SAIDA_PADRAO)
    return prompt_tokens * preco_entrada / 1e6 + completion_tokens * preco_saida / 1e6


def _inteiro(origem, nome: str) -> int:
    valor = origem.get(nome) if isinstance(origem, dict) else getattr(origem, nome, None)
    try:
        return max(int(valor or 0), 0)
    except (TypeError, ValueError):
        return 0


def tokens_do_usage(resposta) -> tuple:
    """(prompt, completion, total) de `response.usage`; ausente vira zeros."""
    usage = resposta.get("usage") if isinstance(resposta, dict) else getattr(resposta, "usage", None)
    if usage is None:
        return 0, 0, 0
    return _inteiro(usage, "prompt_tokens"), _inteiro(usage, "completion_tokens"), _inteiro(usage, "total_tokens")


def registrar_uso(model: str, status: str, latencia_ms: int, prompt_tokens: int = 0,
                  completion_tokens: int = 0, total_tokens: int = 0) -> None:
    """Grava uma linha de ai_usage. Sem contexto de canal (chamada fora do chat), não grava."""
    identidade = identidade_atual()
    if identidade is None:
        return
    try:
        Database.add_ai_usage(
            channel=identidade["channel"],
            user_id=identidade["user_id"],
            session_hash=identidade["session_hash"],
            call_type=_tipo_de_chamada.get(),
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=calcular_custo(prompt_tokens, completion_tokens),
            latency_ms=latencia_ms,
            status=status,
        )
    except Exception as e:
        print(f"Error recording ai_usage: {type(e).__name__}")


def registrar_interacao(outcome: str, course_id: Optional[str] = None, mensagem: Optional[str] = None) -> None:
    """Grava uma linha de ai_interactions para a mensagem que chegou ao pipeline.

    `mensagem` só é usada para o tópico mascarado, e só no canal anônimo com outcome 'unresolved'.
    """
    identidade = identidade_atual()
    if identidade is None:
        return
    topico = None
    if identidade["channel"] == CANAL_ANONIMO and outcome == "unresolved" and mensagem:
        topico = mascarar_topico(mensagem) or None
    try:
        Database.add_ai_interaction(
            channel=identidade["channel"],
            user_id=identidade["user_id"],
            session_hash=identidade["session_hash"],
            course_id=course_id,
            outcome=outcome,
            topic=topico,
        )
    except Exception as e:
        print(f"Error recording ai_interaction: {type(e).__name__}")
