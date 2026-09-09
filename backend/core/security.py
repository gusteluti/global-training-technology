"""
Governança de acesso (Fase 2 - RBAC) para a área do funcionário.

Mantém o mesmo esquema de token assinado com HMAC já usado na Fase 1
(base64 de "role:expires_at:nonce:signature"), apenas acrescentando o
conceito de perfis (Role) para diferenciar Gestão/Financeiro de Suporte,
conforme o item "2. Gestão de Acessos e Governança" do escopo da Fase 2.
"""

from enum import Enum
from dataclasses import dataclass
from fastapi import Header, HTTPException
from dotenv import load_dotenv
import base64
import hashlib
import hmac
import os
import secrets
import time

load_dotenv()

TOKEN_TTL_SECONDS = 60 * 60 * 8


class Role(str, Enum):
    """Perfis de acesso da área do funcionário (RF21)."""

    ADMIN = "admin"
    FINANCIAL = "financial"
    SUPPORT = "support"

    @property
    def label(self) -> str:
        return {
            Role.ADMIN: "Gestão",
            Role.FINANCIAL: "Financeiro",
            Role.SUPPORT: "Suporte",
        }[self]


@dataclass
class AuthContext:
    """Identidade resolvida a partir de um token de funcionário válido."""

    role: Role


def get_admin_secret() -> str:
    secret = os.getenv("ADMIN_TOKEN_SECRET") or os.getenv("ADMIN_PASSWORD")
    if not secret:
        raise HTTPException(status_code=500, detail="ADMIN_TOKEN_SECRET não configurado no backend.")
    return secret


def sign_payload(payload: str) -> str:
    return hmac.new(
        get_admin_secret().encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def get_role_passwords() -> "dict[Role, str]":
    """
    Mapeia cada perfil para sua senha de acesso.

    Compatível com a Fase 1: se apenas ADMIN_PASSWORD estiver configurado,
    ele continua funcionando como antes (perfil Gestão). FINANCIAL_PASSWORD
    e SUPPORT_PASSWORD são opcionais e permitem separar níveis hierárquicos
    sem quebrar instalações existentes.
    """
    admin_password = os.getenv("ADMIN_PASSWORD")
    if not admin_password:
        raise HTTPException(status_code=500, detail="ADMIN_PASSWORD não configurado no backend.")

    passwords = {Role.ADMIN: admin_password}

    financial_password = os.getenv("FINANCIAL_PASSWORD")
    if financial_password:
        passwords[Role.FINANCIAL] = financial_password

    support_password = os.getenv("SUPPORT_PASSWORD")
    if support_password:
        passwords[Role.SUPPORT] = support_password

    return passwords


def resolve_role_from_password(password: str) -> Role:
    """Retorna o perfil cuja senha corresponde à informada, ou 401."""
    for role, expected_password in get_role_passwords().items():
        if secrets.compare_digest(password, expected_password):
            return role
    raise HTTPException(status_code=401, detail="Senha administrativa inválida.")


def create_admin_token(role: Role) -> str:
    expires_at = int(time.time()) + TOKEN_TTL_SECONDS
    nonce = secrets.token_urlsafe(12)
    payload = f"{role.value}:{expires_at}:{nonce}"
    signature = sign_payload(payload)
    token = f"{payload}:{signature}"
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("utf-8")


def get_current_user(authorization: str = Header(default="")) -> AuthContext:
    """Decodifica e valida o token de sessão do funcionário, retornando seu perfil."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token de admin ausente.")

    token = authorization.replace("Bearer ", "", 1).strip()
    try:
        decoded = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        role_value, expires_at, nonce, signature = decoded.split(":", 3)
    except Exception:
        raise HTTPException(status_code=401, detail="Token de admin inválido.")

    payload = f"{role_value}:{expires_at}:{nonce}"
    expected_signature = sign_payload(payload)
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=401, detail="Token de admin inválido.")

    try:
        role = Role(role_value)
    except ValueError:
        raise HTTPException(status_code=401, detail="Token de admin inválido.")

    if int(expires_at) < int(time.time()):
        raise HTTPException(status_code=401, detail="Sessão de admin expirada.")

    return AuthContext(role=role)


def require_roles(*allowed_roles: Role):
    """
    Dependency factory para proteger rotas por perfil.

    Ex.: Depends(require_roles(Role.ADMIN, Role.FINANCIAL)) garante que
    métricas financeiras fiquem restritas a Gestão/Financeiro, enquanto o
    perfil de Suporte recebe 403 (item 2 do escopo da Fase 2).
    """

    def dependency(authorization: str = Header(default="")) -> AuthContext:
        current_user = get_current_user(authorization)
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Acesso não autorizado para este perfil.")
        return current_user

    return dependency
