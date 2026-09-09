from fastapi import APIRouter, Depends, HTTPException
from core.security import get_current_user, require_role
from models.user import Role
from db import Database

router = APIRouter()


@router.get("/financeiro")
async def read_financial_data(current_user=Depends(get_current_user)):
    """
    Endpoint protegido para consumo dos dashboards no Angular.
    Garante que apenas perfis autorizados leiam as métricas de valores.
    """
    # Allow only ADMIN and FINANCIAL roles
    require_role(current_user, [Role.ADMIN.value, Role.FINANCIAL.value])

    summary = Database.get_financial_summary()
    return {"status": "success", "revenue_data": summary}


@router.get("/alunos")
async def read_student_metrics(current_user=Depends(get_current_user)):
    # Allow ADMIN and SUPPORT
    require_role(current_user, [Role.ADMIN.value, Role.SUPPORT.value])
    metrics = Database.get_student_metrics()
    return {"status": "success", "student_metrics": metrics}


@router.get("/cursos")
async def read_course_metrics(current_user=Depends(get_current_user)):
    # Allow ADMIN and SUPPORT for course metrics
    require_role(current_user, [Role.ADMIN.value, Role.SUPPORT.value])
    metrics = Database.get_course_metrics()
    return {"status": "success", "course_metrics": metrics}


@router.get("/audit")
async def read_audit_logs(current_user=Depends(get_current_user)):
    # Only ADMIN can read full audit logs
    require_role(current_user, [Role.ADMIN.value])
    logs = Database.get_audit_logs()
    return {"status": "success", "logs": logs}
