"""Token de definição e de redefinição de senha do aluno (E2, D12, D14, D16; B1, D60).

O token de definição ('setup') é gerado quando um pagamento vira aprovado e a conta do comprador não tem senha,
ou quando um aluno sem senha pede recuperação. O de redefinição ('reset') é gerado no pedido de recuperação de
um aluno que já tem senha.
Só o SHA-256 do token é gravado no banco. O token em claro vai apenas no link entregue ao aluno.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from db import Database
from core.security import get_password_hash

TOKEN_VALIDADE = timedelta(hours=48)  # D12
TOKEN_VALIDADE_SETUP = TOKEN_VALIDADE
TOKEN_VALIDADE_RESET = timedelta(hours=1)  # D60
VALIDADE_POR_FINALIDADE = {"setup": TOKEN_VALIDADE_SETUP, "reset": TOKEN_VALIDADE_RESET}
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


def _formatar(momento: datetime) -> str:
    return momento.isoformat(sep=" ", timespec="seconds")


def emitir_token_definicao(user_id: int) -> str:
    """Cria um token 'setup' novo para a conta, grava só o hash e devolve o token em claro (uma vez)."""
    token = secrets.token_urlsafe(32)
    expira = _formatar(_agora_utc() + TOKEN_VALIDADE_SETUP)
    Database.insert_password_setup_token(user_id, hash_token(token), expira, "setup")
    return token


def emitir_token_com_limite(user_id: int, purpose: str) -> Optional[str]:
    """Emite um token da finalidade dada (D60), com o limite de 3 por conta por hora aplicado de forma atômica.

    Invalida os tokens abertos anteriores da mesma conta e finalidade. Devolve o token em claro (uma vez) ou None
    se o limite foi atingido (nada é gravado)."""
    token = secrets.token_urlsafe(32)
    expira = _formatar(_agora_utc() + VALIDADE_POR_FINALIDADE[purpose])
    if not Database.emitir_token_com_limite(user_id, hash_token(token), expira, purpose):
        return None
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
    if registro is None or registro.get("purpose") != "setup":
        return False
    return Database.definir_senha_com_token(
        registro["id"], registro["user_id"], get_password_hash(senha)
    )


def redefinir_senha_pelo_token(token: str, senha: str) -> Optional[str]:
    """Redefine a senha da conta DONA de um token 'reset' (D60). Devolve o e-mail da conta, ou None se falhou.

    A política da senha e a validade do token são conferidas ANTES do bcrypt; o hash só é calculado para
    pedidos que podem valer, e o consumo do token é atômico. Nenhum user_id vindo do cliente é usado."""
    if not senha_aceitavel(senha):
        return None
    registro = validar_token(token)
    if registro is None or registro.get("purpose") != "reset":
        return None
    return Database.redefinir_senha_com_token(
        hash_token(token), get_password_hash(senha), _agora_utc().strftime("%Y-%m-%d %H:%M:%S")
    )
