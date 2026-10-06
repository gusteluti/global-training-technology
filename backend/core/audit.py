"""Trilha de auditoria (E8, D45): grava o responsável sempre a partir do token, nunca do cliente."""

import json
from typing import Any, List, Optional

from fastapi import HTTPException

from db import Database
from models.user import Role, User

MAX_VALUE_CHARS = 2000
ERRO_TRILHA = "Falha ao registrar a trilha de auditoria."


def actor_fields(user: User) -> dict:
    """Campos do responsável a partir do usuário autenticado (`get_current_user`).

    Conta (JWT): user_id, e-mail, nome e perfil. Token administrativo legado (id 0, sem pessoa):
    sem user_id nem e-mail, nome "Login administrativo (<rótulo do perfil>)".
    """
    if user.id:
        return {
            "user_id": user.id,
            "actor_email": user.email,
            "actor_name": user.name,
            "role": user.role.value,
        }
    return {
        "user_id": None,
        "actor_email": None,
        "actor_name": f"Login administrativo ({user.role.label})",
        "role": user.role.value,
    }


def limit_value(value: Any) -> Any:
    """Valor de before/after limitado a 2000 caracteres (texto cortado; lista/objeto serializado se passar disso)."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:MAX_VALUE_CHARS]
    serialized = json.dumps(value, ensure_ascii=False)
    if len(serialized) <= MAX_VALUE_CHARS:
        return value
    return serialized[:MAX_VALUE_CHARS]


def change(field: str, before: Any, after: Any) -> dict:
    return {"field": field, "before": limit_value(before), "after": limit_value(after)}


def record_audit(
    action: str,
    detail: str,
    *,
    user: Optional[User] = None,
    actor: Optional[dict] = None,
    entity_type: Optional[str] = None,
    entity_id: Any = None,
    changes: Optional[List[dict]] = None,
) -> None:
    """Grava o evento. Se a gravação falhar, a operação termina em 500 genérico (sem texto da exceção)."""
    fields = actor if actor is not None else (actor_fields(user) if user is not None else {})
    try:
        Database.add_audit_log(
            action,
            detail,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=changes,
            **fields,
        )
    except Exception as exc:
        print(f"[ERRO] Falha ao gravar auditoria ({action}): {type(exc).__name__}")
        raise HTTPException(status_code=500, detail=ERRO_TRILHA)


def legacy_actor(role: Role) -> dict:
    """Responsável de um login administrativo legado (senha de perfil, sem pessoa)."""
    return {
        "user_id": None,
        "actor_email": None,
        "actor_name": f"Login administrativo ({role.label})",
        "role": role.value,
    }
