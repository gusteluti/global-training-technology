"""Configuração de produção que não sobe insegura (SG2, D109).

`validar_configuracao(env)` devolve a lista de problemas da configuração, cada um uma frase que CITA o nome da variável
e nunca o valor dela. A lista independe de APP_ENV: quem decide se um problema derruba a subida é
`exigir_configuracao_segura()`, chamada no startup do app (não na importação do módulo). Em produção (`APP_ENV`
normalizado como em `core.cabecalhos.ambiente()`: sem caixa, aparado) ela levanta RuntimeError com todos os problemas de
uma vez; fora de produção devolve a lista e o app escreve um `[AVISO]` por problema.
"""

import os
from typing import List, Mapping, Optional
from urllib.parse import urlparse

from core.cabecalhos import ambiente

JWT_MIN_CARACTERES = 32
SENHA_MIN_CARACTERES = 12

# Senhas públicas dos dados de demonstração. Espelho de `seed_demo.SENHA` (backend/seed_demo.py): não se importa o
# `seed_demo` aqui porque ele carrega .env, banco e geração de PDF na importação e não deve ser exigido em produção.
# Ao trocar a senha do seed, trocar aqui também (o teste a4 usa o valor literal).
SENHAS_PUBLICAS_DO_SEED = ("Senha-Demo-2026",)

SENHAS_DE_PERFIL = ("ADMIN_PASSWORD", "FINANCIAL_PASSWORD", "SUPPORT_PASSWORD")
MOCK_LIGADO = ("1", "true", "yes", "on")
HOSTS_LOCAIS = ("localhost", "127.0.0.1", "::1", "0.0.0.0")


def _valor(env: Mapping[str, str], nome: str) -> str:
    return env.get(nome) or ""


def _origem_insegura(origem: str) -> bool:
    """Só https:// e nada de máquina local."""
    texto = origem.strip().lower()
    if not texto.startswith("https://"):
        return True
    host = (urlparse(texto).hostname or "")
    return host in HOSTS_LOCAIS or "localhost" in host


def validar_configuracao(env: Optional[Mapping[str, str]] = None) -> List[str]:
    """Problemas da configuração de produção. `env` injetável (None = os.environ); lista vazia = configuração segura."""
    if env is None:
        env = os.environ
    problemas: List[str] = []

    jwt = _valor(env, "JWT_SECRET_KEY").strip()
    if len(jwt) < JWT_MIN_CARACTERES:
        problemas.append(f"JWT_SECRET_KEY ausente ou com menos de {JWT_MIN_CARACTERES} caracteres.")

    token_admin = _valor(env, "ADMIN_TOKEN_SECRET")
    senhas = {nome: _valor(env, nome) for nome in SENHAS_DE_PERFIL}
    if not token_admin.strip():
        problemas.append("ADMIN_TOKEN_SECRET ausente; defina um segredo próprio, diferente das senhas de perfil.")
    elif token_admin in [senha for senha in senhas.values() if senha]:
        problemas.append("ADMIN_TOKEN_SECRET igual a uma senha de perfil (ADMIN_PASSWORD, FINANCIAL_PASSWORD ou "
                         "SUPPORT_PASSWORD); use um segredo próprio.")

    for nome, senha in senhas.items():
        if not senha:
            continue  # só ADMIN_PASSWORD é o piso da Fase 1; as demais são opcionais (e ausente não é problema aqui)
        if len(senha.strip()) < SENHA_MIN_CARACTERES:
            problemas.append(f"{nome} com menos de {SENHA_MIN_CARACTERES} caracteres.")
        elif senha in SENHAS_PUBLICAS_DO_SEED:
            problemas.append(f"{nome} é uma das senhas públicas dos dados de demonstração (seed_demo); troque-a.")

    if _valor(env, "PAYMENTS_MOCK").strip().lower() in MOCK_LIGADO:
        problemas.append("PAYMENTS_MOCK ligado; o pagamento simulado não pode existir em produção.")

    if not _valor(env, "MERCADO_PAGO_WEBHOOK_SECRET").strip():
        problemas.append("MERCADO_PAGO_WEBHOOK_SECRET ausente ou vazio.")
    if not _valor(env, "MERCADO_PAGO_ACCESS_TOKEN").strip():
        problemas.append("MERCADO_PAGO_ACCESS_TOKEN ausente ou vazio.")

    origens = [parte for parte in _valor(env, "CORS_ALLOWED_ORIGINS").split(",") if parte.strip()]
    if not origens:
        problemas.append("CORS_ALLOWED_ORIGINS ausente ou vazia; liste as origens https:// do frontend.")
    elif any(_origem_insegura(origem) for origem in origens):
        problemas.append("CORS_ALLOWED_ORIGINS com localhost, 127.0.0.1 ou origem http://; em produção só https:// "
                         "de domínio real.")
    return problemas


def exigir_configuracao_segura() -> List[str]:
    """Lê o os.environ. Em produção com problemas levanta RuntimeError (todos de uma vez, sem valor de segredo).

    Fora de produção não levanta e devolve os problemas, para o chamador registrar como `[AVISO]`.
    """
    problemas = validar_configuracao()
    if problemas and ambiente() == "production":
        lista = "\n".join(f"  - {problema}" for problema in problemas)
        raise RuntimeError(
            "Configuração insegura para APP_ENV=production; o app não sobe. Corrija as variáveis de ambiente:\n" + lista
        )
    return problemas
