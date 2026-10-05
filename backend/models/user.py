from enum import Enum
from pydantic import BaseModel
from typing import Optional


class Role(str, Enum):
    """Perfis da plataforma. Valores compartilhados pelo login por conta (JWT) e pelo login administrativo (Fase 2)."""

    STUDENT = "student"
    SUPPORT = "support"
    FINANCIAL = "financial"
    ADMIN = "admin"

    @property
    def label(self) -> str:
        return {
            Role.STUDENT: "Aluno",
            Role.SUPPORT: "Suporte",
            Role.FINANCIAL: "Financeiro",
            Role.ADMIN: "Gestão",
        }[self]


class User(BaseModel):
    id: int
    email: str
    name: str
    role: Role
    created_at: Optional[str]
