from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Any, List, Dict, Optional
from dotenv import load_dotenv
import json
from pathlib import Path

from core.security import (
    AuthContext,
    Role,
    create_admin_token,
    require_roles,
    require_staff,
    resolve_role_from_password,
    TOKEN_TTL_SECONDS,
)
from core.audit import change, legacy_actor, record_audit
from db import Database

load_dotenv()
router = APIRouter()
COURSES_DIR = Path(__file__).parent.parent / "courses"

class MaterialInput(BaseModel):
    """Material didático. Só aparece para o aluno com matrícula ativa (E3, D28)."""
    title: str
    url: str
    type: str

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
    # Opcional: cursos antigos continuam aceitos sem o campo (E3, D28).
    materials: List[MaterialInput] = []

class AdminLoginInput(BaseModel):
    password: str

# Campos do curso auditados na edição (D45). Os de lista ausentes no arquivo valem [].
COURSE_AUDIT_FIELDS = [
    "price", "name", "description", "duration_hours", "level", "target_audience",
    "objectives", "topics", "benefits", "faq", "system_prompt", "materials",
]
COURSE_LIST_FIELDS = {"objectives", "topics", "benefits", "faq", "materials"}


def _same_value(before: Any, after: Any) -> bool:
    """Igualdade de valor para a trilha: 100 e 100.0 são o mesmo preço."""
    numeric = (int, float)
    if (isinstance(before, numeric) and not isinstance(before, bool)
            and isinstance(after, numeric) and not isinstance(after, bool)):
        return float(before) == float(after)
    return before == after


def _course_changes(before_data: Dict, after_data: Dict) -> List[Dict]:
    """Só os campos cujo valor mudou, com antes e depois."""
    changes = []
    for field in COURSE_AUDIT_FIELDS:
        before = before_data.get(field)
        after = after_data.get(field)
        if field in COURSE_LIST_FIELDS:
            before = [] if before is None else before
            after = [] if after is None else after
        if not _same_value(before, after):
            changes.append(change(field, before, after))
    return changes

@router.post("/login")
async def admin_login(credentials: AdminLoginInput):
    try:
        role = resolve_role_from_password(credentials.password)
    except HTTPException as exc:
        if exc.status_code == 401:
            # Senha inválida: nunca grava a senha digitada nem diz de quem foi a tentativa.
            record_audit(
                "staff.login_failed",
                "Tentativa de login administrativo recusada (senha inválida)",
                actor={},
            )
        raise
    record_audit(
        "staff.login",
        f"Login administrativo ({role.label})",
        actor=legacy_actor(role),
    )

    return {
        "status": "success",
        "token": create_admin_token(role),
        "role": role.value,
        "role_label": role.label,
        "expires_in_seconds": TOKEN_TTL_SECONDS,
    }

@router.get("/audit-logs")
async def get_audit_logs(
    action: Optional[str] = None,
    user_id: Optional[int] = None,
    limit: int = Database.AUDIT_LIST_DEFAULT_LIMIT,
    current_user: AuthContext = Depends(require_roles(Role.ADMIN)),
):
    """Trilhas de auditoria dos eventos críticos da área do funcionário (Fase 2 - Governança).

    Somente leitura (E8): não há rota para alterar ou apagar eventos. `user_id` aqui é filtro de consulta.
    Padrão de 100 itens; acima de 500 vale 500.
    """
    return {
        "status": "success",
        "logs": Database.list_audit_logs(limit=limit, action=action, user_id=user_id),
    }

@router.post("/create-course")
async def create_course(course: CourseInput, request: Request, current_user: AuthContext = Depends(require_roles(Role.ADMIN))):
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
        record_audit(
            "course.create",
            f"Curso '{course.name}' ({course.id}) criado com preço R$ {course.price:.2f}",
            user=current_user,
            entity_type="course",
            entity_id=course.id,
            changes=[change("name", None, course.name), change("price", None, course.price)],
        )

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
async def list_courses(current_user: AuthContext = Depends(require_staff)):
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
async def get_course(course_id: str, current_user: AuthContext = Depends(require_staff)):
    """Get full details of a specific course"""
    try:
        courses_dir = Path(__file__).parent.parent / "courses"
        course_file = courses_dir / f"{course_id}.json"
        if not course_file.exists():
            course_file = _find_course_file_by_id(courses_dir, course_id)

        if not course_file:
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
async def update_course(course_id: str, course: CourseInput, request: Request, current_user: AuthContext = Depends(require_roles(Role.ADMIN))):
    """Update an existing course"""
    try:
        courses_dir = Path(__file__).parent.parent / "courses"
        course_file = courses_dir / f"{course_id}.json"
        if not course_file.exists():
            course_file = _find_course_file_by_id(courses_dir, course_id)

        if not course_file:
            raise HTTPException(status_code=404, detail="Course not found")

        # Load existing data to preserve creation date
        with open(course_file, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
        previous_price = existing_data.get('price')

        # `materials` omitido no corpo preserva os existentes; enviado (inclusive []) substitui (D51).
        new_data = course.dict()
        if "materials" not in course.model_fields_set:
            new_data["materials"] = existing_data.get("materials", [])

        # Update with new data
        course_data = {
            **new_data,
            "created_at": existing_data.get('created_at'),
            "updated_at": __import__('datetime').datetime.now().isoformat()
        }

        # Save updated course
        with open(course_file, 'w', encoding='utf-8') as f:
            json.dump(course_data, f, ensure_ascii=False, indent=2)

        loaded_courses = reload_manager_agent_courses(request, f"course update: {course_id}")

        # Audit trail: alteração de preço de curso é um evento crítico (Fase 2 - Governança).
        # Um evento só, com todos os campos alterados (E8, D45).
        changes = _course_changes(existing_data, new_data)
        if any(item["field"] == "price" for item in changes):
            action = "course.price_change"
            detail = (f"Curso '{course.name}' ({course_id}): preço alterado de "
                      f"R$ {float(previous_price):.2f} para R$ {course.price:.2f}"
                      if previous_price is not None else
                      f"Curso '{course.name}' ({course_id}): preço definido em R$ {course.price:.2f}")
        else:
            action = "course.update"
            detail = f"Curso '{course.name}' ({course_id}) atualizado"
        record_audit(
            action,
            detail,
            user=current_user,
            entity_type="course",
            entity_id=course_id,
            changes=changes,
        )

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
async def delete_course(course_id: str, request: Request, current_user: AuthContext = Depends(require_roles(Role.ADMIN))):
    """Delete a course"""
    try:
        courses_dir = Path(__file__).parent.parent / "courses"
        course_file = courses_dir / f"{course_id}.json"
        if not course_file.exists():
            course_file = _find_course_file_by_id(courses_dir, course_id)

        if not course_file:
            raise HTTPException(status_code=404, detail="Course not found")

        # Load course name before deleting
        with open(course_file, 'r', encoding='utf-8') as f:
            course_data = json.load(f)
            course_name = course_data.get('name')
            course_price = course_data.get('price')

        # Delete file
        course_file.unlink()

        loaded_courses = reload_manager_agent_courses(request, f"course deletion: {course_id}")
        record_audit(
            "course.delete",
            f"Curso '{course_name}' ({course_id}) removido",
            user=current_user,
            entity_type="course",
            entity_id=course_id,
            changes=[change("name", course_name, None), change("price", course_price, None)],
        )

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
        print(f"[AVISO] Manager agent not available to reload after {reason}")
        return 0

    loaded_courses = manager_agent.load_courses(reload=True)
    print(f"[RECARREGA] Manager agent reloaded after {reason}. Courses loaded: {loaded_courses}")
    try:
        # Registro do recarregamento (contribuição do Gustavo). Não pode derrubar a operação de cadastro.
        Database.add_audit_log("manager_reload", reason, role="system")
    except Exception:
        pass
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

def _find_course_file_by_id(courses_dir: Path, course_id: str):
    """Find a course JSON file whose internal id matches the requested id."""
    if not courses_dir.exists():
        return None

    for candidate in courses_dir.glob("*.json"):
        try:
            with open(candidate, 'r', encoding='utf-8') as f:
                course_data = json.load(f)
            if course_data.get("id") == course_id:
                return candidate
        except Exception:
            continue

    return None

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
