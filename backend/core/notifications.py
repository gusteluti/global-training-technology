"""Entrega de notificações ao aluno (E2, D13, D22, D23).

Não há servidor de e-mail neste projeto. Os pontos únicos de envio são:
- send_password_setup_link: link de definição de senha (fluxo de compra, D12/D13);
- send_account_created_notice: confirmação de conta criada no cadastro direto (D22/D23);
- send_account_exists_notice: aviso de tentativa de cadastro com e-mail já existente (D22).

Nesta entrega eles só gravam em modo de desenvolvimento, sem e-mail real:
- se PASSWORD_LINK_OUTBOX estiver definida, acrescenta uma linha JSON nesse arquivo
  (o arquivo deve ficar FORA do repositório);
- senão, registra no log (somente desenvolvimento). Mensagens de cadastro não têm token,
  então o log registra só o assunto.
Trocar por SMTP real é trabalho futuro.
"""

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _escrever_outbox(email: str, registro: dict, *, log_rotulo: str) -> None:
    caminho = os.getenv("PASSWORD_LINK_OUTBOX")
    registro = {
        "email": email,
        **registro,
        "criado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if caminho:
        with open(caminho, "a", encoding="utf-8") as arquivo:
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
    else:
        logger.warning("[dev] %s para %s", log_rotulo, email)


def send_password_setup_link(email: str, link: str) -> None:
    _escrever_outbox(
        email,
        {"link": link},
        log_rotulo=f"link de definição de senha: {link}",
    )


def send_account_created_notice(email: str, login_url: str) -> None:
    """Confirmação de conta criada (D23): sem link de definição de senha e sem token."""
    _escrever_outbox(
        email,
        {
            "assunto": "Conta criada na Global Training",
            "mensagem": (
                "Olá. Sua conta na Global Training foi criada com sucesso. "
                f"Para entrar, acesse a tela de login: {login_url}"
            ),
        },
        log_rotulo="confirmação de conta criada",
    )


def send_account_exists_notice(email: str, login_url: str) -> None:
    """Aviso de tentativa de cadastro com e-mail já existente (D22, D26): sem link de definição, sem
    token, sem senha, sem menção a recuperação de senha (backlog). A conta não é alterada por este envio."""
    _escrever_outbox(
        email,
        {
            "assunto": "Tentativa de cadastro com um e-mail já cadastrado",
            "mensagem": (
                "Olá. Houve uma tentativa de cadastro com este e-mail, mas já existe uma conta com ele. "
                "Sua conta não foi alterada. "
                f"Para entrar, acesse a tela de login: {login_url} "
                "Se não foi você, ignore esta mensagem."
            ),
        },
        log_rotulo="aviso de tentativa de cadastro com conta existente",
    )
