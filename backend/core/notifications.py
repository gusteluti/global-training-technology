"""Entrega de notificações ao aluno (E2, D13, D22, D23).

Não há servidor de e-mail neste projeto. Os pontos únicos de envio são:
- send_password_setup_link: link de definição de senha (fluxo de compra, D12/D13);
- send_password_reset_link: link de redefinição de senha do aluno que já tem senha (B1, D60);
- send_password_changed_notice: aviso de senha alterada, sem senha e sem token (B1, D60);
- send_account_created_notice: confirmação de conta criada no cadastro direto (D22/D23);
- send_account_exists_notice: aviso de tentativa de cadastro com e-mail já existente (D22).

Cada envio:
- se PASSWORD_LINK_OUTBOX estiver definida, acrescenta uma linha JSON nesse arquivo
  (o arquivo deve ficar FORA do repositório); senão, registra no log (somente desenvolvimento);
- U6 (D88): se SMTP_HOST estiver definida, envia também um e-mail real por SMTP (SMTP_PORT, SMTP_USER,
  SMTP_PASSWORD, SMTP_FROM; porta 465 usa SSL, as demais STARTTLS). Falha de envio é registrada no log e nunca
  interrompe o fluxo (a pessoa pode pedir o link de novo). Senha e token nunca vão para o log.
"""

import html
import json
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


SMTP_TIMEOUT_S = 15


def smtp_configurado() -> bool:
    return bool((os.getenv("SMTP_HOST") or "").strip())


def _corpo_html(mensagem: str, link: str = None) -> str:
    texto = html.escape(mensagem)
    botao = ""
    if link:
        url = html.escape(link, quote=True)
        texto = texto.replace(html.escape(link), "")
        botao = (f'<p style="margin:24px 0"><a href="{url}" style="background:#f07a1a;color:#fff;padding:12px 20px;'
                 f'border-radius:6px;text-decoration:none;font-weight:bold">Abrir link</a></p>'
                 f'<p style="font-size:12px;color:#666">Se o botão não funcionar, copie e cole: {url}</p>')
    return ('<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;color:#1b1f24">'
            '<h2 style="color:#0b2a4a">Global Training Technology</h2>'
            f'<p style="line-height:1.5">{texto}</p>{botao}'
            '<p style="font-size:12px;color:#888;margin-top:32px">Mensagem automática; não responda.</p></div>')


def _enviar_smtp(email: str, assunto: str, mensagem: str, link: str = None) -> bool:
    """Envia por SMTP quando configurado. Devolve True se enviou. Nunca levanta exceção."""
    if not smtp_configurado():
        return False
    host = os.getenv("SMTP_HOST", "").strip()
    try:
        porta = int(os.getenv("SMTP_PORT") or 587)
    except ValueError:
        porta = 587
    usuario = (os.getenv("SMTP_USER") or "").strip()
    senha = os.getenv("SMTP_PASSWORD") or ""
    remetente = (os.getenv("SMTP_FROM") or usuario).strip()
    nome, endereco = parseaddr(remetente)
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = formataddr((nome or "Global Training", endereco or usuario))
    msg["To"] = email
    msg.set_content(mensagem)
    msg.add_alternative(_corpo_html(mensagem, link), subtype="html")
    try:
        contexto = ssl.create_default_context()
        if porta == 465:
            servidor = smtplib.SMTP_SSL(host, porta, timeout=SMTP_TIMEOUT_S, context=contexto)
        else:
            servidor = smtplib.SMTP(host, porta, timeout=SMTP_TIMEOUT_S)
        with servidor:
            if porta != 465:
                servidor.ehlo()
                if servidor.has_extn("starttls"):
                    servidor.starttls(context=contexto)
                    servidor.ehlo()
            if usuario:
                servidor.login(usuario, senha)
            servidor.send_message(msg)
        return True
    except Exception as erro:  # o fluxo nunca cai por falha de e-mail
        logger.error("Falha ao enviar e-mail (%s) para %s: %s", assunto, email, type(erro).__name__)
        return False


def _escrever_outbox(email: str, registro: dict, *, log_rotulo: str) -> None:
    if registro.get("assunto") and registro.get("mensagem"):
        _enviar_smtp(email, registro["assunto"], registro["mensagem"], registro.get("link"))
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
    """Link de definição de senha (compra, convite de funcionário, matrícula manual). Vale por 48 h, uso único."""
    _escrever_outbox(
        email,
        {
            "assunto": "Defina sua senha na Global Training",
            "mensagem": (
                "Olá. Sua conta na Global Training está pronta. "
                f"Para definir sua senha e entrar, acesse: {link} "
                "O link vale por 48 horas e só pode ser usado uma vez."
            ),
            "link": link,
        },
        log_rotulo="link de definição de senha",
    )


def send_password_reset_link(email: str, link: str) -> None:
    """Link de redefinição de senha (D60). O link leva o token; vale por 1 hora e uma única vez."""
    _escrever_outbox(
        email,
        {
            "assunto": "Redefinição de senha",
            "mensagem": (
                "Olá. Recebemos um pedido para redefinir a senha da sua conta na Global Training. "
                f"Para escolher uma nova senha, acesse: {link} "
                "O link vale por 1 hora e só pode ser usado uma vez. "
                "Se não foi você, ignore esta mensagem: sua senha atual continua valendo."
            ),
            "link": link,
        },
        log_rotulo="link de redefinição de senha",
    )


def send_password_changed_notice(email: str, login_url: str) -> None:
    """Aviso de senha alterada (D60): sem senha, sem token e sem link de redefinição."""
    _escrever_outbox(
        email,
        {
            "assunto": "Sua senha foi alterada",
            "mensagem": (
                "Olá. A senha da sua conta na Global Training foi alterada. "
                f"Para entrar, acesse a tela de login: {login_url} "
                "Se não foi você, entre em contato com o suporte."
            ),
        },
        log_rotulo="aviso de senha alterada",
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
