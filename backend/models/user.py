from enum import Enum
from pydantic import BaseModel
from typing import Optional


class Role(str, Enum):
    STUDENT = "student"
    SUPPORT = "support"
    FINANCIAL = "financial"
    ADMIN = "admin"


class User(BaseModel):
    id: int
    email: str
    name: str
    role: Role
    created_at: Optional[str]
