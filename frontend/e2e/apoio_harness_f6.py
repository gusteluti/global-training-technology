"""Apoio dos e2e da F6 (handoff para o WhatsApp, D77). Não é código de produção.

- `ambiente_f6(prefixo, cors_origin=None, angular=True)`: igual ao `ambiente_f5b`, mas o backend é o
  `servidor_e2e_f6.py` (backend da F5b com `WHATSAPP_HANDOFF_NUMBER` fabricado). Devolve o mesmo dicionário.
- Reexporta `semear_cursos_f5b`, `semear_aluno` e as credenciais do harness da F5b.
- Constantes do contrato da D77 usadas pelos dois e2e (número fabricado, label e texto).

O backend/db.sqlite e o backend/courses de desenvolvimento não são abertos nem alterados.
"""

import contextlib
import json
import os
import shutil
import sys
import tempfile
import urllib.parse
from pathlib import Path

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_harness_f5b import (  # noqa: E402,F401
    GESTAO_EMAIL, GESTAO_SENHA, LABEL_CURSO, SENHA_ALUNO, _api, semear_aluno, semear_cursos_f5b,
)
from servidor_e2e_f6 import NUMERO_FABRICADO  # noqa: E402
from servidor_e2e_h1 import SUPORTE_EMAIL, SUPORTE_SENHA  # noqa: E402,F401
from test_e5_chat_aluno_angular import (  # noqa: E402
    FRONTEND, REPO, _encerrar, _esperar_http, _iniciar, _porta_livre,
)

LABEL_WHATSAPP = "Falar com um atendente no WhatsApp"
PEDIDO_HUMANO = "Quero falar com um atendente"
PEDIDO_HUMANO_CURSO = "Quero falar com um atendente sobre Omega Analytics"


def texto_whatsapp(alvo):
    return f"Olá! Vim do assistente virtual da Global Training e gostaria de falar com um atendente sobre {alvo}."


def conferir_link_whatsapp(href, alvo):
    """Devolve "" se o href é o link da D77 para o alvo; senão, a descrição do problema."""
    prefixo = f"https://wa.me/{NUMERO_FABRICADO}?text="
    if not href or not href.startswith(prefixo):
        return f"href {href!r} não começa com {prefixo!r}"
    partes = urllib.parse.urlsplit(href)
    qs = urllib.parse.parse_qs(partes.query, keep_blank_values=True)
    esperado = texto_whatsapp(alvo)
    if qs != {"text": [esperado]}:
        return f"texto decodificado {qs!r} (esperado {esperado!r})"
    return ""


def conferir_atributos(target, rel):
    """target=_blank e rel com noopener e noreferrer (D77)."""
    problemas = []
    if target != "_blank":
        problemas.append(f"target={target!r} (esperado _blank)")
    tokens = (rel or "").lower().split()
    for exigido in ("noopener", "noreferrer"):
        if exigido not in tokens:
            problemas.append(f"rel={rel!r} sem {exigido}")
    return "; ".join(problemas)


@contextlib.contextmanager
def ambiente_f6(prefixo, cors_origin=None, angular=True):
    tmp = Path(tempfile.mkdtemp(prefix=f"gt_e2e_{prefixo}_"))
    porta_api = _porta_livre("E2E_BACKEND_PORT")
    api = f"http://127.0.0.1:{porta_api}"
    base = None
    if angular:
        porta_web = _porta_livre("E2E_FRONT_PORT")
        base = f"http://localhost:{porta_web}"
        cors_origin = base
    if not cors_origin:
        raise RuntimeError("ambiente_f6: informe cors_origin quando angular=False")
    db_path = tmp / "db.sqlite"
    cursos_tmp = tmp / "courses"
    llm_log = tmp / "llm.jsonl"
    log_api = tmp / "backend.log"
    processos, arquivos = [], []
    try:
        arq_api = open(log_api, "wb")
        arquivos.append(arq_api)
        backend = _iniciar(
            [sys.executable, str(E2E_DIR / "servidor_e2e_f6.py"), "--port", str(porta_api),
             "--db-path", str(db_path), "--outbox", str(tmp / "outbox.jsonl"),
             "--courses-dir", str(cursos_tmp), "--cors-origin", cors_origin, "--log-llm", str(llm_log)],
            arq_api, REPO / "backend",
        )
        processos.append(backend)
        _esperar_http(api + "/health", 90, backend, "backend de teste", log_api)

        if angular:
            log_web = tmp / "ng_serve.log"
            proxy = tmp / "proxy.e2e.json"
            proxy.write_text(json.dumps({"/api": {"target": api, "secure": False, "changeOrigin": True}}),
                             encoding="utf-8")
            arq_web = open(log_web, "wb")
            arquivos.append(arq_web)
            env_web = dict(os.environ, NG_CLI_ANALYTICS="false", NO_COLOR="1")
            comando_ng = f'npx ng serve --port {porta_web} --proxy-config "{proxy}"'
            front = _iniciar(comando_ng, arq_web, FRONTEND, env=env_web, shell=True)
            processos.append(front)
            _esperar_http(base + "/", int(os.environ.get("E2E_NG_TIMEOUT", "300")), front, "ng serve", log_web)

        yield {"base": base, "api": api, "tmp": tmp, "db_path": db_path, "cursos_tmp": cursos_tmp,
               "llm_log": llm_log}
    finally:
        for processo in reversed(processos):
            _encerrar(processo)
        for arquivo in arquivos:
            try:
                arquivo.close()
            except Exception:
                pass
        shutil.rmtree(tmp, ignore_errors=True)
