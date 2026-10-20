"""Backend de teste dos e2e da F5b (chat com turmas e ação de matrícula). Não é código de produção.

É o backend do harness D58 (`servidor_e2e_h1.py`: banco SQLite temporário, diretório de cursos temporário, contas de
funcionário fabricadas, CORS de teste, Mercado Pago falso), com duas diferenças:
  1. Catálogo do bot isolado: todo `ManagerAgent` criado neste processo lê o MESMO diretório temporário de cursos das
     rotas admin (`--courses-dir`), e não `backend/courses` (padrão D70). Os cursos criados pela API da Gestão durante
     o teste entram no bot pelo recarregamento por mudança de arquivo que o ManagerAgent já faz.
  2. Groq falso que ECOA: roteamento de intenção ("identifica intenções") -> "GENERAL"; resposta ->
     "Resposta simulada do assistente a: <última mensagem do usuário>" (dublê do `servidor_e2e_e5.py`). Cada chamada é
     registrada em --log-llm. O curso é roteado por palavra-chave do nome (a mensagem cita o curso).

Uso (feito pelo teste, não à mão):
  py -3 frontend/e2e/servidor_e2e_f5b.py --port 8123 --db-path <tmp>/db.sqlite --outbox <tmp>/outbox.jsonl \
      --courses-dir <tmp>/courses --cors-origin http://localhost:4300 --log-llm <tmp>/llm.jsonl
"""

import argparse
import sys
from pathlib import Path

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

import servidor_e2e_e5 as base  # noqa: E402
import servidor_e2e_e7 as e7  # noqa: E402
import servidor_e2e_e8 as e8  # noqa: E402
import servidor_e2e_h1 as h1  # noqa: E402


def _isolar_catalogo_do_bot(courses_dir: Path) -> None:
    from agents.manager_agent import ManagerAgent  # noqa: PLC0415

    original = ManagerAgent.__init__

    def construtor(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self.courses_dir = courses_dir

    ManagerAgent.__init__ = construtor


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--outbox", required=True)
    parser.add_argument("--courses-dir", required=True)
    parser.add_argument("--cors-origin", required=True)
    parser.add_argument("--log-llm", required=True)
    args = parser.parse_args()

    base._ambiente(args.outbox)
    h1._ambiente_h1(args.cors_origin)
    app = base._importar_app_com_banco_isolado(Path(args.db_path))
    e8._isolar_cursos(Path(args.courses_dir))
    _isolar_catalogo_do_bot(Path(args.courses_dir))
    base._instalar_duble(Path(args.log_llm))
    e7._instalar_mercado_pago_falso()

    import uvicorn  # noqa: PLC0415

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
