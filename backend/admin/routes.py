from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field, field_validator
from typing import Annotated, Any, List, Dict, Optional
from dotenv import load_dotenv
from datetime import date
import json
import re
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
from core import login_limit
from admin import course_draft
from db import Database

load_dotenv()
router = APIRouter()
COURSES_DIR = Path(__file__).parent.parent / "courses"

# S10 (D79): id de curso. Só ids neste padrão (string inteira) são criados ou procurados; qualquer outro vale como
# curso inexistente e nunca monta caminho de arquivo.
PADRAO_ID_CURSO = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
ERRO_ID_CURSO = "Id do curso inválido: use letras minúsculas, números, _ ou -."


def id_curso_valido(course_id: Any) -> bool:
    return isinstance(course_id, str) and PADRAO_ID_CURSO.fullmatch(course_id) is not None

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
    # F1 (D68): curso arquivado sai do catálogo, do chat e das vendas. Opcional; no PUT, omitido preserva.
    archived: bool = False

class AdminLoginInput(BaseModel):
    password: str


# --- Turmas (L1, D53) ---------------------------------------------------------------------
# Modelos sem extra=forbid: campos desconhecidos (user_id, course_id no PUT etc.) são ignorados;
# o responsável vem só do token.

CLASS_NAME_MAX = 80
CLASS_CAPACITY_MAX = 2_147_483_647
_DATA_ISO = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
ERR_TURMA_DUPLICADA = "Já existe uma turma com esse nome neste curso."
ERR_CAPACIDADE = "A capacidade não pode ser menor que o número de matrículas da turma."
ERR_TURMA_COM_MATRICULAS = "A turma tem matrículas e não pode ser removida."
ERR_TURMA_OUTRO_CURSO = "A turma pertence a outro curso."
ERR_MATRICULA_STATUS = "Só matrículas pendentes ou ativas podem ser atribuídas a uma turma."
ERR_TURMA_CHEIA = "A turma está cheia."

ClassCapacity = Annotated[int, Field(strict=True, ge=1, le=CLASS_CAPACITY_MAX)]


def _validar_nome_turma(valor: Optional[str]) -> str:
    if valor is None:
        raise ValueError("O nome da turma não pode ser vazio.")
    nome = valor.strip()
    if not 1 <= len(nome) <= CLASS_NAME_MAX:
        raise ValueError(f"O nome da turma deve ter de 1 a {CLASS_NAME_MAX} caracteres.")
    return nome


def _validar_data_turma(valor: Optional[str]) -> Optional[str]:
    if valor is None:
        return None
    if not _DATA_ISO.fullmatch(valor):
        raise ValueError("Data inválida: use o formato AAAA-MM-DD.")
    try:
        date.fromisoformat(valor)
    except ValueError:
        raise ValueError("Data inválida: use uma data real no formato AAAA-MM-DD.")
    return valor


class ClassCreateInput(BaseModel):
    course_id: str
    name: str
    starts_on: Optional[str] = None
    capacity: Optional[ClassCapacity] = None

    nome_valido = field_validator("name")(_validar_nome_turma)
    data_valida = field_validator("starts_on")(_validar_data_turma)


class ClassUpdateInput(BaseModel):
    """Só os campos enviados mudam; null limpa starts_on e capacity (o nome não pode ser nulo)."""
    name: Optional[str] = None
    starts_on: Optional[str] = None
    capacity: Optional[ClassCapacity] = None

    nome_valido = field_validator("name")(_validar_nome_turma)
    data_valida = field_validator("starts_on")(_validar_data_turma)


class EnrollmentClassInput(BaseModel):
    class_id: Optional[Annotated[int, Field(strict=True)]]

# Curso: trava de exclusão e arquivamento (F1, D68).
ERR_CURSO_COM_MATRICULAS = ("Não é possível excluir: o curso tem alunos matriculados. "
                            "Arquive o curso para tirá-lo do catálogo.")
ERR_CURSO_INDISPONIVEL = "Este curso não está disponível para novas matrículas."


def curso_arquivado(course_data: Optional[Dict]) -> bool:
    """Só `archived: true` arquiva; curso antigo sem a chave vale como não arquivado."""
    return bool(course_data) and course_data.get("archived") is True


# Campos do curso auditados na edição (D45). Os de lista ausentes no arquivo valem [].
COURSE_AUDIT_FIELDS = [
    "price", "name", "description", "duration_hours", "level", "target_audience",
    "objectives", "topics", "benefits", "faq", "system_prompt", "materials", "archived",
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
        if field == "archived":
            before, after = curso_arquivado(before_data), curso_arquivado(after_data)
        if not _same_value(before, after):
            changes.append(change(field, before, after))
    return changes

@router.post("/login")
async def admin_login(credentials: AdminLoginInput, request: Request):
    # S2 (D79): o login legado (só senha) é limitado por IP.
    ip = login_limit.ip_do_cliente(request)
    login_limit.exigir_nao_bloqueado(None, ip)
    try:
        role = resolve_role_from_password(credentials.password)
    except HTTPException as exc:
        if exc.status_code == 401:
            login_limit.registrar_falha(None, ip)
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
    q: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    offset: int = Query(0, ge=0),
    current_user: AuthContext = Depends(require_roles(Role.ADMIN)),
):
    """Trilhas de auditoria dos eventos críticos da área do funcionário (Fase 2 - Governança).

    Somente leitura (E8): não há rota para alterar ou apagar eventos. `user_id` aqui é filtro de consulta.
    Padrão de 100 itens; acima de 500 vale 500. U1 (D74): `q` na descrição ou no e-mail do responsável,
    `date_from`/`date_to` (AAAA-MM-DD, dias de São Paulo, inclusivos; inválida -> 422) e `offset`.
    """
    return {
        "status": "success",
        "logs": Database.list_audit_logs(
            limit=limit,
            action=action,
            user_id=user_id,
            q=q.strip() if q and q.strip() else None,
            date_from=_data_iso_ou_422(date_from, "date_from"),
            date_to=_data_iso_ou_422(date_to, "date_to"),
            offset=offset,
        ),
    }


_DATA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _data_iso_ou_422(valor: Optional[str], campo: str) -> Optional[str]:
    """'AAAA-MM-DD' de calendário válida ou 422 (U1, D74). Vazio = sem filtro."""
    if valor is None or not valor.strip():
        return None
    valor = valor.strip()
    try:
        if not _DATA_ISO.match(valor):
            raise ValueError
        return date.fromisoformat(valor).isoformat()
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{campo} inválida: use AAAA-MM-DD.")

@router.post("/create-course")
async def create_course(course: CourseInput, request: Request, current_user: AuthContext = Depends(require_roles(Role.ADMIN))):
    """
    Create a new course from form data
    Saves as JSON file in courses directory
    """
    if not id_curso_valido(course.id):
        raise HTTPException(status_code=422, detail=ERRO_ID_CURSO)
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
        # `archived` só é gravado quando verdadeiro: curso novo fica com as chaves de antes (compatibilidade, F1).
        if course_data.get("archived") is not True:
            course_data.pop("archived", None)

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

@router.post("/course-draft")
def course_draft_from_file(file: UploadFile = File(...),
                           current_user: AuthContext = Depends(require_roles(Role.ADMIN))):
    """Rascunho de curso a partir de anexo JSON ou PDF (F7, D78). Nada é gravado: o curso só nasce quando a
    Gestão salva o formulário pela rota de criação. O responsável vem só do token."""
    conteudo = file.file.read(course_draft.MAX_BYTES + 1)
    if len(conteudo) > course_draft.MAX_BYTES:
        raise HTTPException(status_code=413, detail=course_draft.MSG_413)
    try:
        formato, dados = course_draft.detectar_formato(conteudo)
        if formato == "json":
            draft, warnings = course_draft.montar_rascunho(dados, "json")
        else:
            draft, warnings = course_draft.rascunho_do_pdf(conteudo)
    except course_draft.DraftError as erro:
        raise HTTPException(status_code=erro.status_code, detail=erro.detail)

    nome = course_draft.sanitizar_nome_arquivo(file.filename)
    record_audit(
        "course.draft_from_file",
        f"Rascunho de curso gerado a partir de arquivo {formato.upper()} ({nome})",
        user=current_user,
        entity_type="course",
    )
    return {"status": "success", "format": formato, "draft": draft, "warnings": warnings}

@router.get("/courses")
async def list_courses(current_user: AuthContext = Depends(require_staff)):
    """List all available courses"""
    try:
        courses = list_course_summaries(include_archived=True)
        contagens = Database.count_enrollments_by_course()
        for course in courses:
            course["enrollments_count"] = contagens.get(course["id"], 0)
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
        course_file = _arquivo_do_curso(Path(__file__).parent.parent / "courses", course_id)

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
        course_file = _arquivo_do_curso(Path(__file__).parent.parent / "courses", course_id)

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
        # `archived` omitido preserva o valor atual (F1); curso antigo sem a chave continua sem a chave.
        if "archived" not in course.model_fields_set:
            if "archived" in existing_data:
                new_data["archived"] = curso_arquivado(existing_data)
            else:
                new_data.pop("archived", None)

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
        course_file = _arquivo_do_curso(Path(__file__).parent.parent / "courses", course_id)

        if not course_file:
            raise HTTPException(status_code=404, detail="Course not found")

        # Load course name before deleting
        with open(course_file, 'r', encoding='utf-8') as f:
            course_data = json.load(f)
            course_name = course_data.get('name')
            course_price = course_data.get('price')

        # F1 (D68): matrícula em qualquer status trava a exclusão; sem matrícula, as turmas saem junto.
        resultado = Database.excluir_curso_sem_matriculas(course_id, course_file.unlink)
        if resultado["outcome"] == "has_enrollments":
            record_audit(
                "course.delete_blocked",
                f"Exclusão do curso '{course_name}' ({course_id}) bloqueada: o curso tem matrículas",
                user=current_user,
                entity_type="course",
                entity_id=course_id,
            )
            raise HTTPException(status_code=409, detail=ERR_CURSO_COM_MATRICULAS)

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

def _definir_arquivamento(course_id: str, arquivar: bool, request: Request, current_user: AuthContext) -> Dict:
    """Grava `archived` no JSON do curso (F1). Idempotente: sem mudança, não reescreve nem grava evento."""
    course_file = _arquivo_do_curso(Path(__file__).parent.parent / "courses", course_id)
    if not course_file:
        raise HTTPException(status_code=404, detail="Course not found")

    with open(course_file, 'r', encoding='utf-8') as f:
        course_data = json.load(f)
    antes = curso_arquivado(course_data)
    if antes == arquivar:
        return {"status": "success", "course_id": course_id, "archived": arquivar}

    course_data["archived"] = arquivar
    course_data["updated_at"] = __import__('datetime').datetime.now().isoformat()
    with open(course_file, 'w', encoding='utf-8') as f:
        json.dump(course_data, f, ensure_ascii=False, indent=2)

    reload_manager_agent_courses(request, f"course {'archive' if arquivar else 'unarchive'}: {course_id}")
    nome = course_data.get("name")
    record_audit(
        "course.archive" if arquivar else "course.unarchive",
        f"Curso '{nome}' ({course_id}) {'arquivado' if arquivar else 'desarquivado'}",
        user=current_user,
        entity_type="course",
        entity_id=course_id,
        changes=[change("archived", antes, arquivar)],
    )
    return {"status": "success", "course_id": course_id, "archived": arquivar}


@router.post("/course/{course_id}/archive")
async def archive_course(course_id: str, request: Request,
                         current_user: AuthContext = Depends(require_roles(Role.ADMIN))):
    """Arquiva o curso (F1, D68): sai do catálogo, do chat e das vendas; o aluno ativo mantém o acesso."""
    return _definir_arquivamento(course_id, True, request, current_user)


@router.post("/course/{course_id}/unarchive")
async def unarchive_course(course_id: str, request: Request,
                           current_user: AuthContext = Depends(require_roles(Role.ADMIN))):
    """Desarquiva o curso (F1): volta ao catálogo, ao chat e às vendas."""
    return _definir_arquivamento(course_id, False, request, current_user)


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
    """Dados do curso pelo id; id fora do padrão (S10) ou curso ausente -> 404 `Course not found`."""
    if not id_curso_valido(course_id):
        raise HTTPException(status_code=404, detail="Course not found")
    course_file = COURSES_DIR / f"{course_id}.json"
    if course_file.exists():
        with open(course_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    if COURSES_DIR.exists():
        for candidate in COURSES_DIR.glob("*.json"):
            with open(candidate, 'r', encoding='utf-8') as f:
                course_data = json.load(f)
            if id_curso_valido(course_data.get("id")) and course_data.get("id") == course_id:
                return course_data

    raise HTTPException(status_code=404, detail="Course not found")

def _arquivo_do_curso(courses_dir: Path, course_id: str) -> Optional[Path]:
    """Arquivo JSON do curso (nome `<id>.json` ou id interno igual). Id fora do padrão (S10): None, sem montar
    caminho."""
    if not id_curso_valido(course_id):
        return None
    course_file = courses_dir / f"{course_id}.json"
    if course_file.exists():
        return course_file
    return _find_course_file_by_id(courses_dir, course_id)

def _find_course_file_by_id(courses_dir: Path, course_id: str):
    """Find a course JSON file whose internal id matches the requested id (S10: só ids no padrão)."""
    if not id_curso_valido(course_id) or not courses_dir.exists():
        return None

    for candidate in courses_dir.glob("*.json"):
        try:
            with open(candidate, 'r', encoding='utf-8') as f:
                course_data = json.load(f)
            if id_curso_valido(course_data.get("id")) and course_data.get("id") == course_id:
                return candidate
        except Exception:
            continue

    return None

def list_course_summaries(include_archived: bool = False) -> List[Dict]:
    """Resumo do catálogo. Padrão (público): sem cursos arquivados (F1).
    Com `include_archived`, traz todos e o campo `archived` (lista da Gestão e dashboard)."""
    courses = []
    if COURSES_DIR.exists():
        for course_file in COURSES_DIR.glob("*.json"):
            with open(course_file, 'r', encoding='utf-8') as f:
                course_data = json.load(f)
            arquivado = curso_arquivado(course_data)
            if arquivado and not include_archived:
                continue
            resumo = {
                "id": course_data.get('id'),
                "name": course_data.get('name'),
                "price": course_data.get('price'),
                "level": course_data.get('level')
            }
            if include_archived:
                resumo["archived"] = arquivado
            courses.append(resumo)
    return courses


# --- Turmas: rotas (L1, D53) --------------------------------------------------------------

TURMA_CAMPOS = ("name", "starts_on", "capacity")


def _curso_existe(course_id: str) -> bool:
    """O curso existe no catálogo (arquivo JSON). Id fora do padrão (S10) nunca existe."""
    if not id_curso_valido(course_id):
        return False
    try:
        load_course_data(course_id)
    except HTTPException:
        return False
    return True


def _mudancas_turma(before: Dict, after: Dict) -> List[Dict]:
    return [change(campo, before.get(campo), after.get(campo))
            for campo in TURMA_CAMPOS if before.get(campo) != after.get(campo)]


def _descrever_turma(valores: Dict) -> str:
    partes = [f"'{valores.get('name')}'"]
    if valores.get("starts_on"):
        partes.append(f"início {valores['starts_on']}")
    if valores.get("capacity") is not None:
        partes.append(f"capacidade {valores['capacity']}")
    return ", ".join(partes)


@router.get("/classes")
async def list_classes(
    course_id: Optional[str] = None,
    current_user: AuthContext = Depends(require_staff),
):
    """Turmas com contagens (enrolled = ativas, pending, total). Sem `course_id`, todas as turmas."""
    return {"status": "success", "classes": Database.list_classes(course_id)}


@router.post("/classes")
async def create_class(body: ClassCreateInput, current_user: AuthContext = Depends(require_roles(Role.ADMIN))):
    if not _curso_existe(body.course_id):
        raise HTTPException(status_code=404, detail="Course not found")
    class_id = Database.create_class(body.course_id, body.name, body.starts_on, body.capacity)
    if class_id is None:
        raise HTTPException(status_code=409, detail=ERR_TURMA_DUPLICADA)
    novos = {"name": body.name, "starts_on": body.starts_on, "capacity": body.capacity}
    record_audit(
        "class.create",
        f"Turma {_descrever_turma(novos)} criada no curso {body.course_id}",
        user=current_user,
        entity_type="class",
        entity_id=class_id,
        changes=[change("name", None, body.name)] + [
            change(campo, None, novos[campo]) for campo in ("starts_on", "capacity") if novos[campo] is not None
        ],
    )
    return {"status": "success", "class": Database.get_class(class_id)}


@router.put("/classes/{class_id}")
async def update_class(
    class_id: int,
    body: ClassUpdateInput,
    current_user: AuthContext = Depends(require_roles(Role.ADMIN)),
):
    enviados = {campo: getattr(body, campo) for campo in TURMA_CAMPOS if campo in body.model_fields_set}
    resultado = Database.update_class(class_id, enviados)
    if resultado["outcome"] == "not_found":
        raise HTTPException(status_code=404, detail="Class not found")
    if resultado["outcome"] == "duplicate_name":
        raise HTTPException(status_code=409, detail=ERR_TURMA_DUPLICADA)
    if resultado["outcome"] == "capacity_below_total":
        raise HTTPException(status_code=409, detail=ERR_CAPACIDADE)
    mudancas = _mudancas_turma(resultado["before"], resultado["after"])
    if mudancas:  # PUT sem alteração real não grava evento
        record_audit(
            "class.update",
            f"Turma '{resultado['before']['name']}' do curso {resultado['course_id']} atualizada",
            user=current_user,
            entity_type="class",
            entity_id=class_id,
            changes=mudancas,
        )
    return {"status": "success", "class": Database.get_class(class_id)}


@router.delete("/classes/{class_id}")
async def delete_class(class_id: int, current_user: AuthContext = Depends(require_roles(Role.ADMIN))):
    resultado = Database.delete_class(class_id)
    if resultado["outcome"] == "not_found":
        raise HTTPException(status_code=404, detail="Class not found")
    if resultado["outcome"] == "has_enrollments":
        raise HTTPException(status_code=409, detail=ERR_TURMA_COM_MATRICULAS)
    antes = resultado["before"]
    record_audit(
        "class.delete",
        f"Turma {_descrever_turma(antes)} do curso {resultado['course_id']} removida",
        user=current_user,
        entity_type="class",
        entity_id=class_id,
        changes=[change("name", antes["name"], None)] + [
            change(campo, antes[campo], None) for campo in ("starts_on", "capacity") if antes[campo] is not None
        ],
    )
    return {"status": "success", "message": "Turma removida."}


@router.get("/enrollments")
async def list_course_enrollments(
    course_id: str,
    current_user: AuthContext = Depends(require_roles(Role.ADMIN, Role.SUPPORT)),
):
    """Matrículas de um curso (nome, e-mail, status, turma). Sem dado de pagamento."""
    return {"status": "success", "enrollments": Database.list_enrollments_for_course(course_id)}


@router.put("/enrollments/{enrollment_id}/class")
async def set_enrollment_class(
    enrollment_id: int,
    body: EnrollmentClassInput,
    current_user: AuthContext = Depends(require_roles(Role.ADMIN)),
):
    """Atribui a matrícula a uma turma do mesmo curso (ou remove com `class_id` nulo). O responsável é o token."""
    resultado = Database.assign_enrollment_class(enrollment_id, body.class_id)
    outcome = resultado["outcome"]
    if outcome == "enrollment_not_found":
        raise HTTPException(status_code=404, detail="Enrollment not found")
    if outcome == "class_not_found":
        raise HTTPException(status_code=404, detail="Class not found")
    if outcome == "other_course":
        raise HTTPException(status_code=409, detail=ERR_TURMA_OUTRO_CURSO)
    if outcome == "invalid_status":
        raise HTTPException(status_code=409, detail=ERR_MATRICULA_STATUS)
    if outcome == "full":
        raise HTTPException(status_code=409, detail=ERR_TURMA_CHEIA)
    if outcome == "changed":
        antes, depois = resultado["before_class"], resultado["after_class"]

        def nome(turma):
            return f"'{turma['name']}'" if turma else "sem turma"

        record_audit(
            "enrollment.class_change",
            f"Matrícula {enrollment_id} do curso {resultado['course_id']}: turma {nome(antes)} -> {nome(depois)}",
            user=current_user,
            entity_type="enrollment",
            entity_id=enrollment_id,
            changes=[change("class_id", antes["id"] if antes else None, depois["id"] if depois else None)],
        )
    return {"status": "success", "enrollment_id": enrollment_id, "class_id": body.class_id}


# --- Conta do aluno: desativar / reativar (S4, D80) ---------------------------------------------------------------

ERRO_ALUNO_NAO_ENCONTRADO = "Aluno não encontrado"


def _alterar_conta_do_aluno(user_id: int, ativo: bool, current_user: AuthContext) -> dict:
    """Só Gestão. Id que não é de aluno (inexistente, funcionário, fora do INTEGER) -> 404. Idempotente: o evento
    só é gravado quando o estado muda. O responsável vem do token."""
    resultado = Database.set_student_active(user_id, ativo)
    if resultado is None:
        raise HTTPException(status_code=404, detail=ERRO_ALUNO_NAO_ENCONTRADO)
    if resultado["changed"]:
        record_audit(
            "student.reactivate" if ativo else "student.deactivate",
            f"Conta do aluno {user_id} {'reativada' if ativo else 'desativada'}",
            user=current_user,
            entity_type="student",
            entity_id=str(user_id),
            changes=[change("is_active", not ativo, ativo)],
        )
    return {"status": "success", "user_id": user_id, "is_active": ativo}


@router.post("/students/{user_id}/deactivate")
async def deactivate_student(user_id: int, current_user: AuthContext = Depends(require_roles(Role.ADMIN))):
    return _alterar_conta_do_aluno(user_id, False, current_user)


@router.post("/students/{user_id}/reactivate")
async def reactivate_student(user_id: int, current_user: AuthContext = Depends(require_roles(Role.ADMIN))):
    return _alterar_conta_do_aluno(user_id, True, current_user)
