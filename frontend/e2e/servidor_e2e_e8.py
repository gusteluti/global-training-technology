"""Backend de teste do e2e da E8 (auditoria com usuário responsável). Não é código de produção.

Reaproveita o harness do E7 (`servidor_e2e_e7.py`, que reaproveita o do E5): banco SQLite temporário isolado,
Groq falso e Mercado Pago falso (create-checkout + webhook aprovam sem rede). Acrescenta:

  1. Diretório de cursos isolado. As rotas admin calculam o diretório com `Path(__file__).parent.parent / "courses"`
     dentro das funções (criar, editar, excluir) e também têm a constante `COURSES_DIR` (usada pelo checkout e pelas
     rotas do aluno). Aqui o nome `Path` do módulo `admin.routes` é substituído, SÓ neste processo de teste, por
     uma função que, ao receber o `__file__` do próprio módulo, devolve um caminho dentro do diretório temporário
     (`<tmp>/admin/routes.py`), de modo que `.parent.parent / "courses"` aponta para `<tmp>/courses`; `COURSES_DIR`
     também aponta para lá. O diretório `backend/courses` NÃO é criado, alterado nem apagado (o agente de chat só
     LÊ esse diretório ao recarregar).
  2. Segundo gestor. O `app.py` semeia uma conta por perfil a partir de <PERFIL>_EMAIL; para ter DOIS gestores com
     e-mails distintos, o helper insere no banco temporário uma segunda conta de perfil admin (a primeira é a de
     `servidor_e2e_e5.ADMIN_EMAIL`) e uma conta de Financeiro (o E5 deixa FINANCIAL_EMAIL vazio). O login é feito
     normalmente em /api/token.

Uso (feito pelo teste, não à mão):
  py -3 frontend/e2e/servidor_e2e_e8.py --port 8123 --db-path <tmp>/db.sqlite --outbox <tmp>/outbox.jsonl \
      --courses-dir <tmp>/courses
"""

import argparse
import os
import sys
from pathlib import Path

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

import servidor_e2e_e5 as base  # noqa: E402
import servidor_e2e_e7 as e7  # noqa: E402

GESTOR2_EMAIL = "gestor2.e8@teste.com"
GESTOR2_NOME = "Segundo Gestor E8"
GESTOR2_SENHA = "senha-gestor2-e8-teste"

FINANCEIRO_EMAIL = "financeiro.e8@teste.com"
FINANCEIRO_SENHA = "senha-fin-e8-teste"

SUPORTE_EMAIL = e7.SUPPORT_EMAIL
SUPORTE_SENHA = e7.SUPPORT_PASSWORD

# Senha do login administrativo legado (/api/admin/login) do perfil Gestão: é o ADMIN_PASSWORD do harness.
SENHA_LEGADA_GESTAO = base.ADMIN_PASSWORD


def _isolar_cursos(courses_dir: Path) -> None:
    from admin import routes as rotas_admin  # noqa: PLC0415

    courses_dir.mkdir(parents=True, exist_ok=True)
    raiz = courses_dir.parent
    arquivo_falso = raiz / "admin" / "routes.py"
    arquivo_real = str(rotas_admin.__file__)
    path_real = Path

    def path_isolado(*partes, **kwargs):
        if len(partes) == 1 and str(partes[0]) == arquivo_real:
            return arquivo_falso
        return path_real(*partes, **kwargs)

    if courses_dir.name != "courses":
        raise RuntimeError("o diretório de cursos do teste precisa se chamar 'courses'")
    rotas_admin.Path = path_isolado
    rotas_admin.COURSES_DIR = courses_dir


def _semear_contas() -> None:
    import db  # noqa: PLC0415
    from core.security import get_password_hash  # noqa: PLC0415

    for email, nome, senha, perfil in (
        (GESTOR2_EMAIL, GESTOR2_NOME, GESTOR2_SENHA, "admin"),
        (FINANCEIRO_EMAIL, "Financeiro E8", FINANCEIRO_SENHA, "financial"),
    ):
        if not db.Database.get_user_by_email(email):
            db.Database.add_user(email, nome, get_password_hash(senha), role=perfil)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--outbox", required=True)
    parser.add_argument("--courses-dir", required=True)
    args = parser.parse_args()

    base._ambiente(args.outbox)
    os.environ["SUPPORT_EMAIL"] = SUPORTE_EMAIL
    os.environ["SUPPORT_PASSWORD"] = SUPORTE_SENHA
    os.environ["GROQ_MODEL"] = e7.MODELO
    os.environ["GROQ_PRICE_INPUT_PER_1M_USD"] = str(e7.PRECO_ENTRADA)
    os.environ["GROQ_PRICE_OUTPUT_PER_1M_USD"] = str(e7.PRECO_SAIDA)
    app = base._importar_app_com_banco_isolado(Path(args.db_path))
    _isolar_cursos(Path(args.courses_dir))
    e7._instalar_groq_falso()
    e7._instalar_mercado_pago_falso()
    _semear_contas()

    import uvicorn  # noqa: PLC0415

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
