from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from typing import List, Dict
from dotenv import load_dotenv
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import time

load_dotenv()
router = APIRouter()
COURSES_DIR = Path(__file__).parent.parent / "courses"
TOKEN_TTL_SECONDS = 60 * 60 * 8

class CourseInput(BaseModel):
    """Schema for creating/updating a course"""
    id: str
    name: str
    description: str
    price: float
    duration_hours: int
    level: str
    target_audience: str
    objectives: List[str]
    topics: List[str]
    benefits: List[str]
    faq: List[Dict[str, str]]
    system_prompt: str

class AdminLoginInput(BaseModel):
    password: str

def get_admin_password() -> str:
    password = os.getenv("ADMIN_PASSWORD")
    if not password:
        raise HTTPException(status_code=500, detail="ADMIN_PASSWORD não configurado no backend.")
    return password

def get_admin_secret() -> str:
    secret = os.getenv("ADMIN_TOKEN_SECRET") or os.getenv("ADMIN_PASSWORD")
    if not secret:
        raise HTTPException(status_code=500, detail="ADMIN_TOKEN_SECRET não configurado no backend.")
    return secret

def sign_payload(payload: str) -> str:
    signature = hmac.new(
        get_admin_secret().encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return signature

def create_admin_token() -> str:
    expires_at = int(time.time()) + TOKEN_TTL_SECONDS
    nonce = secrets.token_urlsafe(12)
    payload = f"admin:{expires_at}:{nonce}"
    signature = sign_payload(payload)
    token = f"{payload}:{signature}"
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("utf-8")

def verify_admin_token(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token de admin ausente.")

    token = authorization.replace("Bearer ", "", 1).strip()
    try:
        decoded = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        role, expires_at, nonce, signature = decoded.split(":", 3)
    except Exception:
        raise HTTPException(status_code=401, detail="Token de admin inválido.")

    payload = f"{role}:{expires_at}:{nonce}"
    expected_signature = sign_payload(payload)
    if role != "admin" or not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=401, detail="Token de admin inválido.")
    if int(expires_at) < int(time.time()):
        raise HTTPException(status_code=401, detail="Sessão de admin expirada.")

    return True

@router.post("/login")
async def admin_login(credentials: AdminLoginInput):
    if not secrets.compare_digest(credentials.password, get_admin_password()):
        raise HTTPException(status_code=401, detail="Senha administrativa inválida.")

    return {
        "status": "success",
        "token": create_admin_token(),
        "expires_in_seconds": TOKEN_TTL_SECONDS,
    }

@router.post("/create-course")
async def create_course(course: CourseInput, request: Request, _: bool = Depends(verify_admin_token)):
    """
    Create a new course from form data
    Saves as JSON file in courses directory
    """
    try:
        courses_dir = Path(__file__).parent.parent / "courses"
        courses_dir.mkdir(exist_ok=True)
        
        # Create course file
        course_file = courses_dir / f"{course.id}.json"
        
        # Check if course already exists
        if course_file.exists():
            raise HTTPException(status_code=400, detail="Course with this ID already exists")
        
        # Prepare course data
        course_data = {
            **course.dict(),
            "created_at": __import__('datetime').datetime.now().isoformat()
        }
        
        # Save to JSON
        with open(course_file, 'w', encoding='utf-8') as f:
            json.dump(course_data, f, ensure_ascii=False, indent=2)
        
        loaded_courses = reload_manager_agent_courses(request, f"course creation: {course.id}")
        
        return {
            "status": "success",
            "message": f"Course '{course.name}' created successfully",
            "course_id": course.id,
            "file": str(course_file),
            "agent_courses_loaded": loaded_courses
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating course: {str(e)}")

@router.get("/courses")
async def list_courses(_: bool = Depends(verify_admin_token)):
    """List all available courses"""
    try:
        courses = list_course_summaries()
        return {
            "status": "success",
            "total": len(courses),
            "courses": courses
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing courses: {str(e)}")

@router.get("/course/{course_id}")
async def get_course(course_id: str, _: bool = Depends(verify_admin_token)):
    """Get full details of a specific course"""
    try:
        courses_dir = Path(__file__).parent.parent / "courses"
        course_file = courses_dir / f"{course_id}.json"
        
        if not course_file.exists():
            raise HTTPException(status_code=404, detail="Course not found")
        
        with open(course_file, 'r', encoding='utf-8') as f:
            course_data = json.load(f)
        
        return {
            "status": "success",
            "course": course_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving course: {str(e)}")

@router.put("/course/{course_id}")
async def update_course(course_id: str, course: CourseInput, request: Request, _: bool = Depends(verify_admin_token)):
    """Update an existing course"""
    try:
        courses_dir = Path(__file__).parent.parent / "courses"
        course_file = courses_dir / f"{course_id}.json"
        
        if not course_file.exists():
            raise HTTPException(status_code=404, detail="Course not found")
        
        # Load existing data to preserve creation date
        with open(course_file, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
        
        # Update with new data
        course_data = {
            **course.dict(),
            "created_at": existing_data.get('created_at'),
            "updated_at": __import__('datetime').datetime.now().isoformat()
        }
        
        # Save updated course
        with open(course_file, 'w', encoding='utf-8') as f:
            json.dump(course_data, f, ensure_ascii=False, indent=2)

        loaded_courses = reload_manager_agent_courses(request, f"course update: {course_id}")
        
        return {
            "status": "success",
            "message": f"Course '{course.name}' updated successfully",
            "course_id": course_id,
            "agent_courses_loaded": loaded_courses
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating course: {str(e)}")

@router.delete("/course/{course_id}")
async def delete_course(course_id: str, request: Request, _: bool = Depends(verify_admin_token)):
    """Delete a course"""
    try:
        courses_dir = Path(__file__).parent.parent / "courses"
        course_file = courses_dir / f"{course_id}.json"
        
        if not course_file.exists():
            raise HTTPException(status_code=404, detail="Course not found")
        
        # Load course name before deleting
        with open(course_file, 'r', encoding='utf-8') as f:
            course_data = json.load(f)
            course_name = course_data.get('name')
        
        # Delete file
        course_file.unlink()

        loaded_courses = reload_manager_agent_courses(request, f"course deletion: {course_id}")
        
        return {
            "status": "success",
            "message": f"Course '{course_name}' deleted successfully",
            "course_id": course_id,
            "agent_courses_loaded": loaded_courses
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting course: {str(e)}")

def reload_manager_agent_courses(request: Request, reason: str):
    """Reload in-memory course agents so chat can see admin changes immediately."""
    manager_agent = getattr(request.app.state, "manager_agent", None)
    if not manager_agent:
        print(f"⚠️ Manager agent not available to reload after {reason}")
        return 0

    loaded_courses = manager_agent.load_courses(reload=True)
    print(f"🔄 Manager agent reloaded after {reason}. Courses loaded: {loaded_courses}")
    return loaded_courses

def load_course_data(course_id: str) -> Dict:
    course_file = COURSES_DIR / f"{course_id}.json"
    if course_file.exists():
        with open(course_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    if COURSES_DIR.exists():
        for candidate in COURSES_DIR.glob("*.json"):
            with open(candidate, 'r', encoding='utf-8') as f:
                course_data = json.load(f)
            if course_data.get("id") == course_id:
                return course_data

    raise HTTPException(status_code=404, detail="Course not found")

def list_course_summaries() -> List[Dict]:
    courses = []
    if COURSES_DIR.exists():
        for course_file in COURSES_DIR.glob("*.json"):
            with open(course_file, 'r', encoding='utf-8') as f:
                course_data = json.load(f)
                courses.append({
                    "id": course_data.get('id'),
                    "name": course_data.get('name'),
                    "price": course_data.get('price'),
                    "level": course_data.get('level')
                })
    return courses
