"""Apoio dos e2e da F5b (chat com turmas e ação de matrícula, D76). Não é código de produção.

- `ambiente_f5b(prefixo, cors_origin=None, angular=True)`: sobe, em portas livres, o backend de teste
  `servidor_e2e_f5b.py` (harness D58 + catálogo do bot no diretório temporário de cursos + Groq falso que ecoa) e,
  se `angular`, o `ng serve` com proxy temporário /api -> backend. Sem `angular`, o CORS do backend libera
  `cors_origin` (a landing estática). Derruba tudo e apaga o diretório temporário ao final.
  Devolve {"base", "api", "tmp", "db_path", "cursos_tmp", "llm_log"}.
- `semear_cursos_f5b(api, db_path)`: cria pela API da Gestão os cursos "Omega Analytics" (turmas: lotada, Alfa,
  Beta, Gama, Delta sem data e uma já iniciada) e "Sigma Design" (sem turmas), e as turmas por Database.create_class
  no banco temporário. Devolve os ids e as ações esperadas (ordem D75, até 3, com vaga).
- `semear_aluno(db_path, tag)`: conta de aluno com senha conhecida no banco temporário.

Portas fixas opcionais: E2E_BACKEND_PORT / E2E_FRONT_PORT. Tempo do ng serve: E2E_NG_TIMEOUT (s, padrão 300).
O backend/db.sqlite e o backend/courses de desenvolvimento não são abertos nem alterados.
"""

import contextlib
import json
import os
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from apoio_harness_h1 import abrir_banco  # noqa: E402
from servidor_e2e_h1 import GESTAO_EMAIL, GESTAO_SENHA  # noqa: E402
from test_e5_chat_aluno_angular import (  # noqa: E402
    FRONTEND, REPO, _api, _encerrar, _esperar_http, _iniciar, _porta_livre,
)

SENHA_ALUNO = "senha-aluno-f5b-2026"
LABEL_CURSO = "Matricular no curso"

__all__ = ["ambiente_f5b", "semear_cursos_f5b", "semear_aluno", "GESTAO_EMAIL", "GESTAO_SENHA", "SENHA_ALUNO",
           "LABEL_CURSO", "_api"]


@contextlib.contextmanager
def ambiente_f5b(prefixo, cors_origin=None, angular=True):
    tmp = Path(tempfile.mkdtemp(prefix=f"gt_e2e_{prefixo}_"))
    porta_api = _porta_livre("E2E_BACKEND_PORT")
    api = f"http://127.0.0.1:{porta_api}"
    base = None
    if angular:
        porta_web = _porta_livre("E2E_FRONT_PORT")
        base = f"http://localhost:{porta_web}"
        cors_origin = base
    if not cors_origin:
        raise RuntimeError("ambiente_f5b: informe cors_origin quando angular=False")
    db_path = tmp / "db.sqlite"
    cursos_tmp = tmp / "courses"
    llm_log = tmp / "llm.jsonl"
    log_api = tmp / "backend.log"
    processos, arquivos = [], []
    try:
        arq_api = open(log_api, "wb")
        arquivos.append(arq_api)
        backend = _iniciar(
            [sys.executable, str(E2E_DIR / "servidor_e2e_f5b.py"), "--port", str(porta_api),
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


def _dia_sp(delta):
    return ((datetime.now(timezone.utc) - timedelta(hours=3)).date() + timedelta(days=delta)).isoformat()


def _criar_curso(api, token, course_id, nome, preco):
    corpo = {
        "id": course_id, "name": nome, "description": f"{nome} do e2e F5b", "price": preco,
        "duration_hours": 8, "level": "Basico", "target_audience": "Alunos",
        "objectives": ["Objetivo"], "topics": ["Topico"], "benefits": ["Beneficio"],
        "faq": [{"question": "Pergunta", "answer": "Resposta"}], "system_prompt": "Prompt do curso",
        "materials": [{"title": "Apostila", "url": f"https://materiais.test/{course_id}/apostila.pdf", "type": "pdf"}],
    }
    status, _ = _api(api, "POST", "/api/admin/create-course", corpo, token=token)
    if status != 200:
        raise RuntimeError(f"seed: create-course {course_id} respondeu HTTP {status}")


def semear_aluno(db_path, tag, nome=None):
    Database = abrir_banco(db_path)
    from core.security import get_password_hash  # noqa: PLC0415

    email = f"e2e.f5b.{tag}.{uuid.uuid4().hex[:10]}@teste.com"
    uid = Database.add_user(email, nome or f"Aluno F5b {tag}", get_password_hash(SENHA_ALUNO), role="student")
    if uid is None:
        raise RuntimeError(f"seed: não foi possível criar {email}")
    return email, uid


def semear_cursos_f5b(api, db_path):
    status, corpo = _api(api, "POST", "/api/admin/login", {"password": GESTAO_SENHA})
    if status != 200:
        raise RuntimeError(f"seed: login da Gestão respondeu HTTP {status}")
    token = corpo["token"]
    omega = {"id": "curso_f5b_omega", "nome": "Omega Analytics"}
    sigma = {"id": "curso_f5b_sigma", "nome": "Sigma Design"}
    _criar_curso(api, token, omega["id"], omega["nome"], 300.0)
    _criar_curso(api, token, sigma["id"], sigma["nome"], 150.0)

    Database = abrir_banco(db_path)
    turmas = {}
    for chave, nome, inicio, cap in (
        ("lotada", "Lotada Express", _dia_sp(3), 1),
        ("alfa", "Alfa Noturna", _dia_sp(5), 140),
        ("beta", "Beta Sabado", _dia_sp(8), None),
        ("gama", "Gama Integral", _dia_sp(8), 260),
        ("delta", "Delta Livre", None, 50),
        ("iniciada", "Iniciada Antiga", _dia_sp(-2), 30),
    ):
        class_id = Database.create_class(omega["id"], nome, inicio, cap)
        if class_id is None:
            raise RuntimeError(f"seed: turma {nome} não foi criada")
        turmas[chave] = {"id": class_id, "nome": nome}
    _email, ocupante = semear_aluno(db_path, "ocupante", "Ocupante F5b")
    referencia = f"{omega['id']}:1700000000:{uuid.uuid4().hex[:8]}"
    enrollment_id = Database.create_enrollment(ocupante, omega["id"], referencia)
    Database.record_payment(enrollment_id, 300.0, "mercado_pago")
    import sqlite3  # noqa: PLC0415

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("UPDATE enrollments SET status = 'active', class_id = ? WHERE id = ?",
                     (turmas["lotada"]["id"], enrollment_id))
        conn.execute("UPDATE payments SET status = 'approved' WHERE enrollment_id = ?", (enrollment_id,))
        conn.commit()
    finally:
        conn.close()

    acoes_omega = [{"type": "enroll", "course_id": omega["id"], "class_id": turmas[k]["id"],
                    "label": f"Matricular na turma {turmas[k]['nome']}"} for k in ("alfa", "beta", "gama")]
    acoes_sigma = [{"type": "enroll", "course_id": sigma["id"], "class_id": None, "label": LABEL_CURSO}]
    return {"omega": omega, "sigma": sigma, "turmas": turmas, "acoes_omega": acoes_omega, "acoes_sigma": acoes_sigma}
