from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import json
from pathlib import Path
from pydantic import BaseModel

# Import routers
from admin.routes import list_course_summaries, router as admin_router
from payments.routes import router as payments_router
from agents.manager_agent import ManagerAgent
from admin.dashboard import router as dashboard_router
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

# Initialize manager agent
manager_agent = None

# Pydantic models
class ChatMessage(BaseModel):
    message: str
    session_id: str = "default"

@app.on_event("startup")
async def startup_event():
    """Load courses and initialize manager agent on startup"""
    global manager_agent
    try:
        manager_agent = ManagerAgent()
        manager_agent.load_courses()
        app.state.manager_agent = manager_agent
        print(f"✅ Manager Agent initialized with {len(manager_agent.courses)} courses")
        print(f"✅ Groq LLM loaded successfully")
    except Exception as e:
        print(f"❌ Error initializing manager agent: {str(e)}")
        raise

    # Ensure admin user exists if env vars are provided
    admin_email = os.getenv("ADMIN_EMAIL")
    admin_password = os.getenv("ADMIN_PASSWORD")
    if admin_email and admin_password:
        existing = Database.get_user_by_email(admin_email)
        if not existing:
            pwd_hash = get_password_hash(admin_password)
            created = Database.add_user(admin_email, os.getenv("ADMIN_NAME", "Administrator"), pwd_hash, role="admin")
            if created:
                print(f"✅ Admin user created: {admin_email}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
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

@app.post("/api/chat")
async def chat(chat_msg: ChatMessage):
    """
    Main chat endpoint
    Expected input: {"message": "user message", "session_id": "optional"}
    """
    try:
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
app.include_router(dashboard_router, prefix="/api/v1/dashboard", tags=["dashboard"])
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
