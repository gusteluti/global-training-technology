from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from pydantic import BaseModel, ConfigDict

from core.security import create_access_token, verify_password, get_password_hash
from core.password_setup import definir_senha_pelo_token, senha_aceitavel
from db import Database

router = APIRouter()

# Mensagens genéricas (D15, D16): não revelam se a conta existe, não ecoam e-mail nem token.
ERRO_CADASTRO = "Não foi possível concluir o cadastro. Verifique os dados informados."
ERRO_DEFINICAO_SENHA = "Não foi possível definir a senha. Verifique o link e a senha informada."


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
    if Database.get_user_by_email(email):
        raise HTTPException(status_code=400, detail=ERRO_CADASTRO)

    user_id = Database.add_user(email, nome, get_password_hash(dados.password), role="student")
    if user_id is None:
        raise HTTPException(status_code=400, detail=ERRO_CADASTRO)
    return {"status": "success", "message": "Conta criada. Faça login para entrar."}


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
        raise HTTPException(status_code=400, detail="Usuário ou senha inválidos")

    if not verify_password(form_data.password, user.get("password_hash")):
        raise HTTPException(status_code=400, detail="Usuário ou senha inválidos")

    access_token_expires = timedelta(minutes=60*8)
    token = create_access_token({"user_id": user["id"], "email": user["email"], "role": user.get("role", "student")}, expires_delta=access_token_expires)
    return {"access_token": token, "token_type": "bearer"}
