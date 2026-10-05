"""Entrega de notificações ao aluno (E2, D13).

Não há servidor de e-mail neste projeto. send_password_setup_link é o ponto único de envio.
Nesta entrega ele só grava em modo de desenvolvimento, sem e-mail real:
- se PASSWORD_LINK_OUTBOX estiver definida, acrescenta uma linha JSON nesse arquivo
  (o arquivo deve ficar FORA do repositório);
- senão, registra o link no log (somente desenvolvimento).
Trocar por SMTP real é trabalho futuro.
"""

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def send_password_setup_link(email: str, link: str) -> None:
    caminho = os.getenv("PASSWORD_LINK_OUTBOX")
    if caminho:
        registro = {
            "email": email,
            "link": link,
            "criado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        with open(caminho, "a", encoding="utf-8") as arquivo:
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
    else:
        logger.warning("[dev] link de definição de senha para %s: %s", email, link)
