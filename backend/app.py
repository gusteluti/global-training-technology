from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import os
import json
from pathlib import Path
from pydantic import BaseModel

# Import routers
from admin.routes import list_course_summaries, router as admin_router
from payments.routes import router as payments_router
from dashboard.routes import router as dashboard_router
from agents.manager_agent import ManagerAgent
from auth import router as auth_router
from core.security import get_password_hash
from db import Database

# Initialize FastAPI
app = FastAPI(title="TCC School Chatbot API", version="1.0.0")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class ChatMessage(BaseModel):
    message: str
    session_id: str = "default"

@app.on_event("startup")
async def startup_event():
    """Load courses and initialize manager agent on startup"""
    try:
        manager_agent = ManagerAgent()
        manager_agent.load_courses()
        app.state.manager_agent = manager_agent
        print(f"✅ Manager Agent initialized with {len(manager_agent.courses)} courses")
        print(f"✅ Groq LLM loaded successfully")
    except Exception as e:
        print(f"❌ Error initializing manager agent: {str(e)}")
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
        if email and password and not Database.get_user_by_email(email):
            name = os.getenv(f"{env_prefix}_NAME", default_name)
            if Database.add_user(email, name, get_password_hash(password), role=role):
                print(f"✅ Conta de {role} criada: {email}")

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
            "available_models": ["mixtral-8x7b-32768"]
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

@app.post("/api/chat")
async def chat(chat_msg: ChatMessage, request: Request):
    """
    Main chat endpoint
    Expected input: {"message": "user message", "session_id": "optional"}
    """
    try:
        manager_agent = getattr(request.app.state, "manager_agent", None)
        if not manager_agent:
            return {
                "status": "error",
                "message": "Manager agent not initialized"
            }
        
        user_message = chat_msg.message.strip()
        session_id = chat_msg.session_id
        
        if not user_message:
            return {
                "status": "error",
                "message": "Mensagem vazia. Por favor, digite algo."
            }
        
        # Route message through manager agent
        response = manager_agent.process_message(user_message, session_id)
        
        return {
            "status": "success",
            "message": response,
            "session_id": session_id
        }
    except Exception as e:
        error_msg = f"Erro ao processar mensagem: {str(e)}"
        print(f"Error in chat endpoint: {error_msg}")
        return {
            "status": "error",
            "message": error_msg
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

# Include admin routes
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
app.include_router(payments_router, prefix="/api/payments", tags=["payments"])
# Dashboards de funcionário (Fase 2), consumidos pela aplicação Angular e pelo admin.html:
# /api/dashboard/{alunos,cursos,financeiro,observabilidade-ia}
app.include_router(dashboard_router, prefix="/api/dashboard", tags=["dashboard"])
# Login por conta (JWT): POST /api/token
app.include_router(auth_router)

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
