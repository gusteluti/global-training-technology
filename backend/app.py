from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import json
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional
from pydantic import BaseModel

# Import routers
from fastapi import HTTPException
from admin.routes import curso_arquivado, list_course_summaries, load_course_data, router as admin_router
from payments.routes import pagamento_mockado_efetivo, router as payments_router
from dashboard.routes import router as dashboard_router
from agents.llm_guard import (
    INPUT_BLOCKED,
    LLM_UNAVAILABLE,
    MAX_MESSAGE_CHARS,
    TOO_LONG,
    InputBlockedError,
    LLMUnavailableError,
)
from agents.handoff import acoes_de_handoff
from agents.manager_agent import ManagerAgent, montar_acoes
from auth import router as auth_router
from student.routes import router as student_router
from core.security import get_password_hash, senha_excede_limite_bcrypt
from core import rate_limit
from db import Database

# Initialize FastAPI
app = FastAPI(title="TCC School Chatbot API", version="1.0.0")

# CORS (E9, D48): lista explícita de origens, sem "*" e sem credenciais (a autenticação é pelo
# cabeçalho Authorization). CORS_ALLOWED_ORIGINS (separada por vírgulas) substitui o padrão.
def _origem_de(url: str) -> str:
    partes = urlparse(url.strip())
    if partes.scheme and partes.netloc:
        return f"{partes.scheme}://{partes.netloc}"
    return url.strip().rstrip("/")


def cors_allowed_origins() -> list:
    configuradas = os.getenv("CORS_ALLOWED_ORIGINS")
    if configuradas is not None and configuradas.strip():
        candidatas = configuradas.split(",")
    else:
        candidatas = [
            os.getenv("FRONTEND_BASE_URL") or "http://localhost:8000",
            "http://localhost:4200",
            "http://127.0.0.1:4200",
            "http://127.0.0.1:8000",
        ]
    origens = []
    for candidata in candidatas:
        origem = _origem_de(candidata) if candidata.strip() else ""
        if not origem:
            continue
        if origem == "*":
            print("[AVISO] CORS_ALLOWED_ORIGINS: '*' ignorado; liste as origens explicitamente.")
            continue
        if origem not in origens:
            origens.append(origem)
    return origens


app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Pydantic models
class ChatMessage(BaseModel):
    message: str
    session_id: Optional[str] = None  # só vale se foi emitido pelo servidor (E6, D38.1)

@app.on_event("startup")
async def startup_event():
    """Load courses and initialize manager agent on startup"""
    # S9 (D79): estado em memória dos limites de taxa (chat e checkout) nasce zerado a cada startup.
    rate_limit.redefinir_limites()
    # S6 (D81): pagamentos pendentes vencidos (mais de 7 dias) expiram no startup. Uma falha aqui não impede a
    # subida: as leituras de dashboard, do aluno e o checkout repetem a expiração.
    try:
        Database.expirar_pendentes()
    except Exception as exc:  # noqa: BLE001
        print(f"[ERRO] Falha ao expirar pagamentos pendentes no startup: {type(exc).__name__}")
    try:
        manager_agent = ManagerAgent()
        manager_agent.load_courses()
        app.state.manager_agent = manager_agent
        print(f"[OK] Manager Agent initialized with {len(manager_agent.courses)} courses")
        print(f"[OK] Groq LLM loaded successfully")
    except Exception as e:
        print(f"[ERRO] Error initializing manager agent: {str(e)}")
        raise

    # Contas de funcionário para o login da aplicação Angular (um por perfil de RBAC).
    # Cada conta sai de <PERFIL>_EMAIL + <PERFIL>_PASSWORD. As senhas são as mesmas usadas
    # pelo login administrativo legado, então os dois logins aceitam as mesmas credenciais.
    # Contas já existentes não são alteradas: trocar a senha no .env exige trocar o registro.
    staff_accounts = (
        ("ADMIN", "admin", "Administrator"),
        ("FINANCIAL", "financial", "Financeiro"),
        ("SUPPORT", "support", "Suporte"),
    )
    for env_prefix, role, default_name in staff_accounts:
        email = os.getenv(f"{env_prefix}_EMAIL")
        password = os.getenv(f"{env_prefix}_PASSWORD")
        if email and password and senha_excede_limite_bcrypt(password):
            # Nunca grava a senha (nem trecho dela) no log; só o nome da variável.
            print(f"[AVISO] Conta de {role} não criada: {env_prefix}_PASSWORD excede 72 bytes (limite do bcrypt).")
            continue
        if email and password and not Database.get_user_by_email(email):
            name = os.getenv(f"{env_prefix}_NAME", default_name)
            if Database.add_user(email, name, get_password_hash(password), role=role):
                print(f"[OK] Conta de {role} criada: {email}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        manager_agent = getattr(app.state, "manager_agent", None)
        if manager_agent:
            manager_agent.refresh_courses_if_changed()
        courses_count = len(manager_agent.courses) if manager_agent else 0
        return {
            "status": "ok",
            "courses_loaded": courses_count,
            "llm": "groq",
            "available_models": ["mixtral-8x7b-32768"],
            "payments_mock": pagamento_mockado_efetivo(),
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

@app.get("/api/chat/courses-debug")
async def chat_courses_debug(request: Request):
    """Debug endpoint to inspect which courses are loaded by the chat agent."""
    manager_agent = getattr(request.app.state, "manager_agent", None)
    if not manager_agent:
        return {
            "status": "error",
            "message": "Manager agent not initialized",
            "courses": []
        }

    manager_agent.refresh_courses_if_changed()
    return {
        "status": "success",
        "total": len(manager_agent.courses),
        "courses": [
            {
                "id": course_id,
                "name": course_data.get("name"),
                "price": course_data.get("price"),
                "level": course_data.get("level"),
            }
            for course_id, course_data in manager_agent.courses.items()
        ]
    }

def _handoff_anonimo(manager_agent, mensagem: str, session_id: str, course_id: Optional[str]) -> list:
    """Ação de handoff (F6, D77) da sessão anônima; o nome do curso vem do catálogo do servidor."""
    nome = (manager_agent.courses.get(course_id) or {}).get("name") if course_id else None
    return acoes_de_handoff(mensagem, session_id=session_id, course_id=course_id, course_name=nome)


@app.post("/api/chat")
async def chat(chat_msg: ChatMessage, request: Request):
    """
    Main chat endpoint (visitante anônimo)
    Expected input: {"message": "user message", "session_id": "optional, emitido pelo servidor"}
    A resposta traz sempre o session_id efetivo; um id desconhecido abre uma sessão nova (E6, D38.1).
    S9 (D79): 30 mensagens por minuto por IP; acima disso, 429 sem chegar ao LLM.
    """
    if not rate_limit.permitir_chat(request):
        return JSONResponse(status_code=429, content={"status": "error", "message": rate_limit.ERRO_CHAT})
    try:
        manager_agent = getattr(request.app.state, "manager_agent", None)
        if not manager_agent:
            return {
                "status": "error",
                "message": "Manager agent not initialized"
            }
        
        user_message = chat_msg.message.strip()
        
        if not user_message:
            return {
                "status": "error",
                "message": "Mensagem vazia. Por favor, digite algo."
            }

        if len(user_message) > MAX_MESSAGE_CHARS:
            return {"status": "error", "message": TOO_LONG}

        session_id = manager_agent.resolve_session(chat_msg.session_id)

        # Route message through manager agent
        try:
            resultado = manager_agent.process_message(user_message, session_id)
        except InputBlockedError:
            return {"status": "success", "message": INPUT_BLOCKED, "session_id": session_id, "actions": []}
        except LLMUnavailableError as erro:
            corpo = {"status": "error", "message": LLM_UNAVAILABLE, "session_id": session_id}
            # F6 (D77): o erro continua como antes; ganha `actions` só quando o handoff vale.
            handoff = _handoff_anonimo(manager_agent, user_message, session_id, getattr(erro, "curso", None))
            if handoff:
                corpo["actions"] = handoff
            return corpo

        return {
            "status": "success",
            "message": resultado.texto,
            "session_id": session_id,
            # F5b (D76): ações montadas pelo servidor a partir do curso roteado; visitante não tem matrícula.
            # F6 (D77): a ação de handoff, quando vale, vem depois das de matrícula.
            "actions": montar_acoes(resultado)
            + _handoff_anonimo(manager_agent, user_message, session_id, resultado.curso),
        }
    except Exception as e:
        # Nada do texto da exceção vai ao cliente (E6, D38.6); o log leva só o tipo.
        print(f"Error in chat endpoint: {type(e).__name__}")
        return {
            "status": "error",
            "message": "Erro ao processar mensagem."
        }

@app.get("/api/courses")
async def public_courses():
    """Public course listing used by the landing page."""
    courses = list_course_summaries()
    return {
        "status": "success",
        "total": len(courses),
        "courses": courses
    }

@app.get("/api/courses/{course_id}/turmas")
async def public_course_classes(course_id: str):
    """Turmas abertas do curso para a compra (F5a, D75): lista pura `[{id, name, starts_on, capacity,
    seats_left}]`, sem dado de aluno. Curso inexistente ou arquivado -> 404 `Course not found`."""
    course = load_course_data(course_id)
    if curso_arquivado(course):
        raise HTTPException(status_code=404, detail="Course not found")
    return Database.list_open_classes_for_sale(course_id)

# Include admin routes
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
app.include_router(payments_router, prefix="/api/payments", tags=["payments"])
# Dashboards de funcionário (Fase 2), consumidos pela aplicação Angular e pelo admin.html:
# /api/dashboard/{alunos,cursos,financeiro,observabilidade-ia}
app.include_router(dashboard_router, prefix="/api/dashboard", tags=["dashboard"])
# Login por conta (JWT): POST /api/token
app.include_router(auth_router)
# Área do aluno (E3, D28): /api/student/enrollments (só perfil student; IDOR bloqueado no SQL).
app.include_router(student_router, prefix="/api/student", tags=["student"])

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "TCC School Chatbot API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
