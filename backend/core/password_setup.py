"""Token de definição de senha do aluno (E2, D12, D14, D16).

O token é gerado quando um pagamento vira aprovado e a conta do comprador não tem senha.
Só o SHA-256 do token é gravado no banco. O token em claro vai apenas no link entregue ao aluno.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from db import Database
from core.security import get_password_hash

TOKEN_VALIDADE = timedelta(hours=48)  # D12
SENHA_MINIMA = 8  # D14
# bcrypt processa no máximo 72 bytes; acima disso a senha não é aceita (evita erro 500).
SENHA_MAXIMA_BYTES = 72


def senha_aceitavel(senha: str) -> bool:
    return (
        isinstance(senha, str)
        and len(senha) >= SENHA_MINIMA
        and len(senha.encode("utf-8")) <= SENHA_MAXIMA_BYTES
    )


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _expirado(expires_at) -> bool:
    if isinstance(expires_at, (int, float)):
        expira = datetime.fromtimestamp(expires_at, tz=timezone.utc).replace(tzinfo=None)
    else:
        expira = datetime.fromisoformat(str(expires_at)).replace(tzinfo=None)
    return expira <= _agora_utc()


def emitir_token_definicao(user_id: int) -> str:
    """Cria um token novo para a conta, grava só o hash e devolve o token em claro (uma vez)."""
    token = secrets.token_urlsafe(32)
    expira = (_agora_utc() + TOKEN_VALIDADE).isoformat(sep=" ", timespec="seconds")
    Database.insert_password_setup_token(user_id, hash_token(token), expira)
    return token


def validar_token(token: str) -> Optional[dict]:
    """Registro do token se ele existe, não foi usado e não expirou; senão None."""
    if not isinstance(token, str) or not token:
        return None
    registro = Database.get_password_setup_token(hash_token(token))
    if registro is None or registro["used_at"] is not None or _expirado(registro["expires_at"]):
        return None
    return registro


def definir_senha_pelo_token(token: str, senha: str) -> bool:
    """Define a senha da conta DONA do token. Nenhum user_id vindo do cliente é usado (D17)."""
    if not senha_aceitavel(senha):
        return False
    registro = validar_token(token)
    if registro is None:
        return False
    return Database.definir_senha_com_token(
        registro["id"], registro["user_id"], get_password_hash(senha)
    )
