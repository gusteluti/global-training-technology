import os
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from pydantic import BaseModel, ConfigDict

from core.audit import record_audit
from core.security import create_access_token, verify_password, get_password_hash
from core.password_setup import definir_senha_pelo_token, senha_aceitavel
from core.notifications import send_account_created_notice, send_account_exists_notice
from db import Database
from models.user import Role

router = APIRouter()

STAFF_ROLES = (Role.ADMIN.value, Role.FINANCIAL.value, Role.SUPPORT.value)

# Mensagens genéricas (D15, D16): não revelam se a conta existe, não ecoam e-mail nem token.
ERRO_CADASTRO = "Não foi possível concluir o cadastro. Verifique os dados informados."
ERRO_DEFINICAO_SENHA = "Não foi possível definir a senha. Verifique o link e a senha informada."
# Resposta uniforme do cadastro (D21): a mesma para e-mail novo e existente.
RESPOSTA_CADASTRO = {
    "status": "success",
    "message": "Se os dados forem válidos, a conta estará pronta para uso. Verifique seu e-mail.",
}


def _frontend_base() -> str:
    return os.getenv("FRONTEND_BASE_URL", "http://localhost:8000").rstrip("/")


class RegisterInput(BaseModel):
    # Campos extras (como role) são ignorados: o papel é sempre 'student' (D15).
    model_config = ConfigDict(extra="ignore")
    name: str
    email: str
    password: str


class PasswordSetupInput(BaseModel):
    # user_id (ou qualquer campo extra) é ignorado: o alvo é sempre o dono do token (D17).
    model_config = ConfigDict(extra="ignore")
    token: str
    password: str


@router.post("/api/auth/register")
async def register(dados: RegisterInput):
    """Cadastro direto de aluno (D15). Papel fixo 'student'."""
    nome = dados.name.strip()
    email = dados.email.strip()
    if not nome or "@" not in email or "." not in email or not senha_aceitavel(dados.password):
        raise HTTPException(status_code=400, detail=ERRO_CADASTRO)
    # Paridade de tempo (D21): o bcrypt é calculado ANTES de consultar a conta, nos dois caminhos.
    senha_hash = get_password_hash(dados.password)
    login_url = f"{_frontend_base()}/login"

    if Database.get_user_by_email(email):
        # Conta existente: não é alterada. O aviso vai por e-mail (D22), não na resposta HTTP.
        send_account_exists_notice(email, login_url)
        return RESPOSTA_CADASTRO

    user_id = Database.add_user(email, nome, senha_hash, role="student")
    if user_id is None:
        # Corrida: a conta foi criada entre a consulta e a gravação. Trata como existente.
        send_account_exists_notice(email, login_url)
        return RESPOSTA_CADASTRO

    # Confirmação sem link de definição de senha e sem token (D23).
    send_account_created_notice(email, login_url)
    return RESPOSTA_CADASTRO


@router.post("/api/auth/password-setup")
async def password_setup(dados: PasswordSetupInput):
    """Define a senha pelo link recebido após a compra (D12, D16, D17)."""
    if not definir_senha_pelo_token(dados.token, dados.password):
        raise HTTPException(status_code=400, detail=ERRO_DEFINICAO_SENHA)
    return {"status": "success", "message": "Senha definida. Faça login para entrar."}


@router.post("/api/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """Standard OAuth2 password flow: returns JWT access token."""
    user = Database.get_user_by_email(form_data.username)
    if not user:
        # E-mail inexistente nunca vai para a trilha (E8, D45).
        raise HTTPException(status_code=400, detail="Usuário ou senha inválidos")

    # Só contas de funcionário são auditadas; login de aluno (certo ou errado) não gera evento.
    is_staff = (user.get("role") or "student") in STAFF_ROLES
    actor = {
        "user_id": user["id"],
        "actor_email": user["email"],
        "actor_name": user["name"],
        "role": user.get("role"),
    }

    if not verify_password(form_data.password, user.get("password_hash")):
        if is_staff:
            # Conta existente: grava a conta alvo, nunca a senha digitada.
            record_audit("staff.login_failed", "Login recusado (senha inválida) em conta de funcionário", actor=actor)
        raise HTTPException(status_code=400, detail="Usuário ou senha inválidos")

    if is_staff:
        record_audit("staff.login", "Login de funcionário", actor=actor)

    access_token_expires = timedelta(minutes=60*8)
    token = create_access_token({"user_id": user["id"], "email": user["email"], "role": user.get("role", "student")}, expires_delta=access_token_expires)
    return {"access_token": token, "token_type": "bearer"}
