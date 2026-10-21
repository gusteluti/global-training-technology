"""Gestão da equipe (S3, D85): a Gestão lista, convida, troca o perfil, desativa e reativa funcionários.

Montado em /api/admin (app.py). O convite cria a conta sem senha e envia o link de definição de senha da E2.
Trocar o perfil ou desativar incrementa `token_version` (D80): a pessoa entra de novo com o perfil novo.
"""

import os
import re
import sqlite3
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator

from core.audit import change, record_audit
from core.notifications import send_password_setup_link
from core.password_setup import emitir_token_definicao
from core.security import AuthContext, Role, require_roles
from db import Database

router = APIRouter()

PERFIS_EQUIPE = ("admin", "financial", "support")
PerfilEquipe = Literal["admin", "financial", "support"]

ERR_EMAIL_EM_USO = "Já existe uma conta com este e-mail."
ERR_NAO_ENCONTRADO = "Funcionário não encontrado."
ERR_PROPRIA_CONTA = "Você não pode desativar ou trocar o perfil da sua própria conta."
ERR_ULTIMA_GESTAO = "É preciso manter pelo menos uma conta de Gestão ativa."

NOME_MAX = 120
EMAIL_MAX = 254
_PADRAO_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

_gestao = require_roles(Role.ADMIN)


def _nome_valido(valor: Optional[str]) -> Optional[str]:
    if valor is None:
        return None
    valor = valor.strip()
    if not 1 <= len(valor) <= NOME_MAX:
        raise ValueError(f"Informe o nome (de 1 a {NOME_MAX} caracteres).")
    return valor


class ConviteInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    email: str
    name: str
    role: PerfilEquipe

    @field_validator("email")
    @classmethod
    def _email_valido(cls, valor: str) -> str:
        valor = (valor or "").strip()
        if len(valor) > EMAIL_MAX or not _PADRAO_EMAIL.fullmatch(valor):
            raise ValueError("Informe um e-mail válido.")
        return valor

    nome = field_validator("name")(_nome_valido)


class AlteracaoInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    role: Optional[PerfilEquipe] = None
    name: Optional[str] = None

    nome = field_validator("name")(_nome_valido)


# --- Banco -----------------------------------------------------------------------------------------------------------

def _conectar() -> sqlite3.Connection:
    conn = sqlite3.connect(Database.DB_PATH, isolation_level=None, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def listar_equipe() -> list:
    conn = _conectar()
    try:
        linhas = conn.execute(
            "SELECT id, name, email, role, is_active, created_at FROM users "
            "WHERE role IN ('admin', 'financial', 'support') ORDER BY name COLLATE NOCASE, id"
        ).fetchall()
        return [{**dict(linha), "is_active": bool(linha["is_active"])} for linha in linhas]
    finally:
        conn.close()


def _gestao_ativa_restante(conn, sem_id: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1 AND id != ?", (sem_id,)
    ).fetchone()[0]


def alterar_funcionario(user_id: int, mudancas: dict, responsavel_id) -> dict:
    """Aplica `mudancas` (role, name, is_active) numa transação. `outcome`: not_found | self | last_admin |
    updated. Em `updated` devolve `before` e `after`; perfil ou desativação incrementam token_version."""
    if not Database._id_sqlite_valido(user_id):
        return {"outcome": "not_found"}
    conn = _conectar()
    try:
        conn.execute("BEGIN IMMEDIATE")
        atual = conn.execute(
            "SELECT id, name, role, is_active FROM users WHERE id = ? AND role IN ('admin', 'financial', 'support')",
            (user_id,),
        ).fetchone()
        if atual is None:
            conn.execute("ROLLBACK")
            return {"outcome": "not_found"}
        before = {"name": atual["name"], "role": atual["role"], "is_active": bool(atual["is_active"])}
        after = {**before, **{k: v for k, v in mudancas.items() if v is not None}}
        muda_perfil = after["role"] != before["role"]
        desativa = before["is_active"] and not after["is_active"]

        if (muda_perfil or desativa) and responsavel_id == user_id:
            conn.execute("ROLLBACK")
            return {"outcome": "self"}
        deixa_de_ser_gestao_ativa = before["role"] == "admin" and before["is_active"] and (
            after["role"] != "admin" or not after["is_active"])
        if deixa_de_ser_gestao_ativa and _gestao_ativa_restante(conn, user_id) == 0:
            conn.execute("ROLLBACK")
            return {"outcome": "last_admin"}

        if after != before:
            versao = 1 if (muda_perfil or desativa) else 0
            conn.execute(
                "UPDATE users SET name = ?, role = ?, is_active = ?, token_version = token_version + ? WHERE id = ?",
                (after["name"], after["role"], 1 if after["is_active"] else 0, versao, user_id),
            )
        conn.execute("COMMIT")
        return {"outcome": "updated", "before": before, "after": after}
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


# --- Rotas -----------------------------------------------------------------------------------------------------------

def _resultado(resultado: dict, user_id: int, current_user: AuthContext, acao: str) -> dict:
    outcome = resultado["outcome"]
    if outcome == "not_found":
        raise HTTPException(status_code=404, detail=ERR_NAO_ENCONTRADO)
    if outcome == "self":
        raise HTTPException(status_code=409, detail=ERR_PROPRIA_CONTA)
    if outcome == "last_admin":
        raise HTTPException(status_code=409, detail=ERR_ULTIMA_GESTAO)
    antes, depois = resultado["before"], resultado["after"]
    mudancas = [change(campo, antes[campo], depois[campo]) for campo in ("name", "role", "is_active")
                if antes[campo] != depois[campo]]
    if mudancas:
        record_audit(
            acao,
            f"Conta de funcionário {user_id} alterada",
            user=current_user,
            entity_type="staff",
            entity_id=str(user_id),
            changes=mudancas,
        )
    return {"status": "success", "staff": {"id": user_id, **depois}}


@router.get("/staff")
async def listar(current_user: AuthContext = Depends(_gestao)):
    return {"status": "success", "staff": listar_equipe()}


@router.post("/staff")
async def convidar(body: ConviteInput, current_user: AuthContext = Depends(_gestao)):
    if Database.get_user_by_email(body.email):
        raise HTTPException(status_code=409, detail=ERR_EMAIL_EM_USO)
    user_id = Database.add_user(body.email, body.name, None, role=body.role)
    if not user_id:
        raise HTTPException(status_code=409, detail=ERR_EMAIL_EM_USO)
    token = emitir_token_definicao(user_id)
    base = os.getenv("FRONTEND_BASE_URL", "http://localhost:8000").rstrip("/")
    send_password_setup_link(body.email, f"{base}/definir-senha?token={token}")
    record_audit(
        "staff.create",
        f"Funcionário convidado ({Role(body.role).label})",
        user=current_user,
        entity_type="staff",
        entity_id=str(user_id),
        changes=[change("role", None, body.role), change("email", None, body.email)],
    )
    return {"status": "success", "staff": {"id": user_id, "name": body.name, "email": body.email,
                                           "role": body.role, "is_active": True}}


@router.put("/staff/{user_id}")
async def alterar(user_id: int, body: AlteracaoInput, current_user: AuthContext = Depends(_gestao)):
    resultado = alterar_funcionario(user_id, {"role": body.role, "name": body.name}, current_user.id)
    return _resultado(resultado, user_id, current_user, "staff.update")


@router.post("/staff/{user_id}/deactivate")
async def desativar(user_id: int, current_user: AuthContext = Depends(_gestao)):
    resultado = alterar_funcionario(user_id, {"is_active": False}, current_user.id)
    return _resultado(resultado, user_id, current_user, "staff.deactivate")


@router.post("/staff/{user_id}/reactivate")
async def reativar(user_id: int, current_user: AuthContext = Depends(_gestao)):
    resultado = alterar_funcionario(user_id, {"is_active": True}, current_user.id)
    return _resultado(resultado, user_id, current_user, "staff.reactivate")
