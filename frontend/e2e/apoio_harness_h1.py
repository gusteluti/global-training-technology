"""Apoio dos três e2e antigos migrados para servidores e banco isolados (D58, entrega H1). Não é código de produção.

- `ambiente_isolado(prefixo)`: gerenciador de contexto que sobe, em portas livres, o backend de teste
  (`servidor_e2e_h1.py`: SQLite temporário, diretório de cursos temporário, segredo de webhook e CORS de teste,
  Groq e Mercado Pago falsos) e o `ng serve` com proxy temporário /api -> backend; derruba tudo e apaga o
  diretório temporário ao final. Devolve {"base", "api", "tmp", "db_path", "cursos_tmp"}.
  Portas fixas opcionais: E2E_BACKEND_PORT / E2E_FRONT_PORT. Tempo do ng serve: E2E_NG_TIMEOUT (s, padrão 300).
  E2E_BASE_URL / E2E_API_URL NÃO são mais usados: apontar o teste para servidores de fora quebraria o
  isolamento (o seed grava no banco temporário do próprio teste).
- `abrir_banco(db_path)`: devolve a classe `Database` do backend apontada para o MESMO arquivo temporário do
  backend de teste, para os e2e que semeiam pela camada de banco (ex.: `emitir_token_definicao`). O módulo `db`
  executa `Database.init_db()` ao ser importado; por isso o `sqlite3.connect` é redirecionado para o arquivo
  temporário durante o import, e o backend/db.sqlite de desenvolvimento nunca é aberto.

Os utilitários de processo e porta (`_iniciar`, `_encerrar`, `_esperar_http`, `_porta_livre`, `_api`) são os do
e2e do chat (somente leitura, o arquivo não é alterado).
"""

import contextlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from test_e5_chat_aluno_angular import (  # noqa: E402
    FRONTEND, REPO, _api, _encerrar, _esperar_http, _iniciar, _porta_livre,
)

__all__ = ["ambiente_isolado", "abrir_banco", "_api"]


@contextlib.contextmanager
def ambiente_isolado(prefixo):
    tmp = Path(tempfile.mkdtemp(prefix=f"gt_e2e_{prefixo}_"))
    porta_api = _porta_livre("E2E_BACKEND_PORT")
    porta_web = _porta_livre("E2E_FRONT_PORT")
    api = f"http://127.0.0.1:{porta_api}"
    base = f"http://localhost:{porta_web}"
    log_api = tmp / "backend.log"
    log_web = tmp / "ng_serve.log"
    proxy = tmp / "proxy.e2e.json"
    proxy.write_text(json.dumps({"/api": {"target": api, "secure": False, "changeOrigin": True}}), encoding="utf-8")
    db_path = tmp / "db.sqlite"
    cursos_tmp = tmp / "courses"

    processos = []
    arquivos = []
    try:
        arq_api = open(log_api, "wb")
        arquivos.append(arq_api)
        backend = _iniciar(
            [sys.executable, str(E2E_DIR / "servidor_e2e_h1.py"), "--port", str(porta_api),
             "--db-path", str(db_path), "--outbox", str(tmp / "outbox.jsonl"),
             "--courses-dir", str(cursos_tmp), "--cors-origin", base],
            arq_api, REPO / "backend",
        )
        processos.append(backend)
        _esperar_http(api + "/health", 90, backend, "backend de teste", log_api)

        arq_web = open(log_web, "wb")
        arquivos.append(arq_web)
        env_web = dict(os.environ, NG_CLI_ANALYTICS="false", NO_COLOR="1")
        comando_ng = f'npx ng serve --port {porta_web} --proxy-config "{proxy}"'
        front = _iniciar(comando_ng, arq_web, FRONTEND, env=env_web, shell=True)
        processos.append(front)
        _esperar_http(base + "/", int(os.environ.get("E2E_NG_TIMEOUT", "300")), front, "ng serve", log_web)

        yield {"base": base, "api": api, "tmp": tmp, "db_path": db_path, "cursos_tmp": cursos_tmp}
    finally:
        for processo in reversed(processos):
            _encerrar(processo)
        for arquivo in arquivos:
            try:
                arquivo.close()
            except Exception:
                pass
        shutil.rmtree(tmp, ignore_errors=True)


def abrir_banco(db_path):
    """Database do backend apontado para `db_path` (nunca para backend/db.sqlite)."""
    db_path = Path(db_path)
    backend = str(REPO / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    if "db" not in sys.modules:
        original = sqlite3.connect

        def conectar(_database, *args, **kwargs):
            return original(str(db_path), *args, **kwargs)

        sqlite3.connect = conectar
        try:
            import db  # noqa: PLC0415  (executa Database.init_db() no banco temporário)
        finally:
            sqlite3.connect = original
    import db  # noqa: PLC0415

    db.Database.DB_PATH = db_path
    if Path(db.Database.DB_PATH).resolve() == (REPO / "backend" / "db.sqlite").resolve():
        raise RuntimeError("abrir_banco: o banco de desenvolvimento não pode ser usado pelo e2e")
    return db.Database
