"""Feedback 👍/👎 das respostas do chat (GR5, D95, PLANO_GR).

- Toda resposta 200 `status: success` dos dois canais ganha um `reply_id` opaco (32 hex minúsculos, aleatório), inclusive
  as de texto fixo (injeção, fora do domínio, login, "não sei", saída barrada). Erros não ganham.
- O dono do reply_id fica em `ai_replies`: canal + user_id (do JWT) no aluno, ou o hash da sessão anônima. O feedback só
  vale para o dono; qualquer outro caso (outra sessão, outro aluno, outro canal, inexistente) é tratado igual.
- Nada aqui grava texto de mensagem, de resposta nem o id cru da sessão.
"""

import re
import secrets
from typing import Optional

from agents.ai_observability import CANAL_ALUNO, CANAL_ANONIMO, hash_da_sessao
from db import Database

REPLY_ID = re.compile(r"[0-9a-f]{32}")
ERRO_RESPOSTA_NAO_ENCONTRADA = "Resposta não encontrada."


def _emitir(channel: str, user_id: Optional[int], session_hash: Optional[str]) -> str:
    reply_id = secrets.token_hex(16)
    try:
        Database.add_ai_reply(reply_id=reply_id, channel=channel, user_id=user_id, session_hash=session_hash)
    except Exception as e:
        # Falha de gravação não derruba o chat (o feedback desse reply_id é que fica sem efeito).
        print(f"Error recording ai_reply: {type(e).__name__}")
    return reply_id


def emitir_reply_id_anonimo(session_id: str) -> str:
    return _emitir(CANAL_ANONIMO, None, hash_da_sessao(session_id))


def emitir_reply_id_aluno(user_id: int) -> str:
    return _emitir(CANAL_ALUNO, user_id, None)


def _dono(reply_id: str) -> Optional[dict]:
    if not isinstance(reply_id, str) or not REPLY_ID.fullmatch(reply_id):
        return None
    return Database.get_ai_reply(reply_id)


def registrar_feedback_anonimo(session_id: str, reply_id: str, rating: str) -> bool:
    """Grava (ou atualiza) a nota se o reply_id é desta sessão anônima. False = não encontrado."""
    dono = _dono(reply_id)
    session_hash = hash_da_sessao(session_id)
    if not dono or dono["channel"] != CANAL_ANONIMO or dono["session_hash"] != session_hash:
        return False
    Database.upsert_ai_feedback(reply_id=reply_id, rating=rating, channel=CANAL_ANONIMO, user_id=None,
                                session_hash=session_hash)
    return True


def registrar_feedback_aluno(user_id: int, reply_id: str, rating: str) -> bool:
    """Grava (ou atualiza) a nota se o reply_id é do aluno do JWT. False = não encontrado."""
    dono = _dono(reply_id)
    if not dono or dono["channel"] != CANAL_ALUNO or dono["user_id"] != user_id:
        return False
    Database.upsert_ai_feedback(reply_id=reply_id, rating=rating, channel=CANAL_ALUNO, user_id=user_id,
                                session_hash=None)
    return True
