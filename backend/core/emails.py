"""Regra única de e-mail: formato aceito e forma normalizada usada para gravar e procurar contas (D104)."""

import re
from typing import Optional

EMAIL_MAX = 254
PADRAO_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def normalizar_email(email: Optional[str]) -> str:
    return (email or "").strip().lower()


def email_valido(email: Optional[str]) -> bool:
    return len(email or "") <= EMAIL_MAX and PADRAO_EMAIL.fullmatch(email or "") is not None
