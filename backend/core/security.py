"""
Autenticação e governança de acesso (RBAC) da plataforma.

Dois mecanismos convivem, cada um atendendo a um cliente:

1. Contas de usuário (alunos e funcionários) na tabela `users`, com senha em
   bcrypt e JWT emitido por `POST /api/token` (fluxo OAuth2 password). Usado
   pela aplicação Angular (contribuição do Gustavo).

2. Login administrativo por senha de perfil (ADMIN/FINANCIAL/SUPPORT_PASSWORD),
   que emite um token HMAC com o perfil embutido. Usado pelo `admin.html`
   (contribuição da Fase 2 - Gestão de Acessos e Governança).

`get_current_user` aceita os dois formatos e devolve sempre um `User` com o
`role`, então as rotas e as dependências `require_roles` / `require_role`
funcionam para qualquer um dos dois tipos de token.
"""

import base64
import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
from fastapi import Header, HTTPException
from jose import JWTError, jwt
from passlib.context import CryptContext

from db import Database
from models.user import Role, User

load_dotenv()

# --- Token de funcionário (login por senha de perfil) -----------------------
TOKEN_TTL_SECONDS = 60 * 60 * 8

# --- Token JWT de conta (fluxo /api/token) ----------------------------------
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 8)))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Compatibilidade: o nome antigo do perfil de conta continua disponível.
AuthContext = User


# --- Segredos ---------------------------------------------------------------

def get_admin_secret() -> str:
    secret = os.getenv("ADMIN_TOKEN_SECRET") or os.getenv("ADMIN_PASSWORD")
    if not secret:
        raise HTTPException(status_code=500, detail="ADMIN_TOKEN_SECRET não configurado no backend.")
    return secret


def _jwt_secret() -> str:
    """A chave do JWT é obrigatória: não há fallback fixo, para não aceitar tokens forjados com um segredo público."""
    secret = os.getenv("JWT_SECRET_KEY")
    if not secret:
        raise HTTPException(status_code=500, detail="JWT_SECRET_KEY não configurado no backend.")
    return secret


def sign_payload(payload: str) -> str:
    return hmac.new(
        get_admin_secret().encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


# --- Senhas de conta (bcrypt) -----------------------------------------------

# bcrypt só processa os 72 primeiros bytes. Acima disso a senha não vale: nem para gravar, nem para conferir
# (senão uma senha mais longa autenticaria a conta cuja senha é o prefixo de 72 bytes, ou viraria erro 500).
BCRYPT_MAX_BYTES = 72


def senha_excede_limite_bcrypt(password: str) -> bool:
    return len(password.encode("utf-8")) > BCRYPT_MAX_BYTES


def verify_password(plain_password: str, hashed_password: Optional[str]) -> bool:
    if not hashed_password:
        return False
    if senha_excede_limite_bcrypt(plain_password):
        return False
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    if senha_excede_limite_bcrypt(password):
        raise ValueError(f"A senha excede o limite de {BCRYPT_MAX_BYTES} bytes do bcrypt.")
    return pwd_context.hash(password)


# --- JWT de conta -----------------------------------------------------------

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, _jwt_secret(), algorithm=JWT_ALGORITHM)


def _user_from_jwt(token: str) -> User:
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    user_id = payload.get("user_id")
    email = payload.get("email")
    if user_id is None or email is None:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    user_data = Database.get_user_by_email(email)
    if not user_data:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    return User(
        id=user_data["id"],
        email=user_data["email"],
        name=user_data["name"],
        role=Role(user_data.get("role") or "student"),
        created_at=user_data.get("created_at"),
    )


# --- Token de funcionário (HMAC com perfil embutido) ------------------------

def get_role_passwords() -> "dict[Role, str]":
    """
    Mapeia cada perfil de funcionário para sua senha.

    Se apenas ADMIN_PASSWORD estiver configurado, o comportamento da Fase 1 é
    mantido (perfil Gestão). FINANCIAL_PASSWORD e SUPPORT_PASSWORD são opcionais.
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


def _user_from_staff_token(token: str) -> User:
    try:
        decoded = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        role_value, expires_at, nonce, signature = decoded.split(":", 3)
    except Exception:
        raise HTTPException(status_code=401, detail="Token de admin inválido.")

    payload = f"{role_value}:{expires_at}:{nonce}"
    if not hmac.compare_digest(signature, sign_payload(payload)):
        raise HTTPException(status_code=401, detail="Token de admin inválido.")

    try:
        role = Role(role_value)
    except ValueError:
        raise HTTPException(status_code=401, detail="Token de admin inválido.")
    if role == Role.STUDENT:
        # Aluno não tem token de funcionário; só entra pelo JWT de conta.
        raise HTTPException(status_code=401, detail="Token de admin inválido.")

    if int(expires_at) < int(time.time()):
        raise HTTPException(status_code=401, detail="Sessão de admin expirada.")

    return User(id=0, email="", name=role.label, role=role, created_at=None)


# --- Dependências -----------------------------------------------------------

def get_current_user(authorization: str = Header(default="")) -> User:
    """
    Valida o token do cabeçalho `Authorization: Bearer ...` e devolve o usuário.

    JWT tem dois pontos (header.payload.signature); o token de funcionário é
    base64 sem pontos. Cada um segue seu próprio caminho de validação.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente.")

    token = authorization[len("Bearer "):].strip()
    if "." in token:
        return _user_from_jwt(token)
    return _user_from_staff_token(token)


def require_role(user: User, allowed: list) -> None:
    """Checagem por nome de perfil (ex.: ["admin", "financial"]). Lança 403 se o perfil não for permitido."""
    if user.role.value not in allowed:
        raise HTTPException(status_code=403, detail="Acesso não autorizado")


def require_roles(*allowed_roles: Role):
    """
    Dependency factory para rotas protegidas por perfil.

    Ex.: Depends(require_roles(Role.ADMIN, Role.FINANCIAL)) restringe métricas
    financeiras a Gestão/Financeiro; o Suporte recebe 403.
    """

    def dependency(authorization: str = Header(default="")) -> User:
        current_user = get_current_user(authorization)
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Acesso não autorizado para este perfil.")
        return current_user

    return dependency


# Qualquer perfil de funcionário (Gestão, Financeiro ou Suporte). Alunos ficam de fora.
require_staff = require_roles(Role.ADMIN, Role.FINANCIAL, Role.SUPPORT)
