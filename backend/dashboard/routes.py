"""
Dashboards operacionais da Área do Funcionário (Fase 2 - item 1.2 do escopo):
Dashboard de Alunos, Dashboard de Cursos, Dashboard Financeiro e o painel de
Observabilidade do Chatbot (RF23/RF24), todos protegidos por RBAC (RF21).
"""

from fastapi import APIRouter, Depends, Request

from core.security import AuthContext, Role, require_roles, require_staff
from db import Database
from admin.routes import list_course_summaries

router = APIRouter()


@router.get("/alunos")
async def dashboard_alunos(request: Request, current_user: AuthContext = Depends(require_staff)):
    """
    Métricas quantitativas de matriculados, listagem de alunos ativos e
    histórico de interações (RF23). Disponível para todos os perfis internos,
    já que o Suporte precisa acompanhar dados acadêmicos dos alunos.
    """
    students = Database.get_students_overview()
    total_students = len(students)
    active_students = sum(1 for student in students if (student.get("active_enrollments") or 0) > 0)
    manager_agent = getattr(request.app.state, "manager_agent", None)
    total_chat_sessions = len(manager_agent.sessions) if manager_agent else 0

    return {
        "status": "success",
        "metrics": {
            "total_students": total_students,
            "active_students": active_students,
            "total_chat_sessions": total_chat_sessions,
        },
        "students": students,
    }


@router.get("/cursos")
async def dashboard_cursos(current_user: AuthContext = Depends(require_staff)):
    """
    Performance do catálogo: inscritos por turma e taxa de conversão (RF23).
    """
    catalog = {course["id"]: course for course in list_course_summaries()}
    overview_by_course = {row["course_id"]: row for row in Database.get_courses_overview()}

    courses = []
    for course_id, course in catalog.items():
        overview = overview_by_course.get(course_id, {})
        total_enrollments = overview.get("total_enrollments", 0) or 0
        approved_enrollments = overview.get("approved_enrollments", 0) or 0
        conversion_rate = (approved_enrollments / total_enrollments * 100) if total_enrollments else 0.0

        courses.append({
            "id": course_id,
            "name": course.get("name"),
            "price": course.get("price"),
            "level": course.get("level"),
            "total_enrollments": total_enrollments,
            "approved_enrollments": approved_enrollments,
            "pending_enrollments": overview.get("pending_enrollments", 0) or 0,
            "conversion_rate": round(conversion_rate, 1),
        })

    courses.sort(key=lambda course: course["total_enrollments"], reverse=True)

    return {
        "status": "success",
        "total_courses": len(courses),
        "courses": courses,
    }


@router.get("/financeiro")
async def dashboard_financeiro(current_user: AuthContext = Depends(require_roles(Role.ADMIN, Role.FINANCIAL))):
    """
    Valores globais arrecadados, status de transações e projeção de receita.
    Restrito a Gestão/Financeiro (RF23 + item 2 do escopo - RBAC).
    """
    summary = Database.get_financial_summary()

    by_status = {row["status"]: row for row in summary["by_status"]}
    approved = by_status.get("approved", {"total": 0, "amount": 0})
    pending = by_status.get("pending", {"total": 0, "amount": 0})
    refunded = by_status.get("refunded", {"total": 0, "amount": 0})

    monthly_revenue = list(reversed(summary["by_month"]))  # ordem cronológica para o gráfico
    projected_next_month = (
        sum(month["revenue"] for month in monthly_revenue) / len(monthly_revenue)
        if monthly_revenue else 0.0
    )

    return {
        "status": "success",
        "totals": {
            "revenue_approved": round(approved.get("amount", 0) or 0, 2),
            "revenue_pending": round(pending.get("amount", 0) or 0, 2),
            "revenue_refunded": round(refunded.get("amount", 0) or 0, 2),
            "approved_count": approved.get("total", 0),
            "pending_count": pending.get("total", 0),
            "refunded_count": refunded.get("total", 0),
            "projected_next_month": round(projected_next_month, 2),
        },
        "by_status": summary["by_status"],
        "monthly_revenue": monthly_revenue,
        "payments": Database.get_payments_overview(),
    }


@router.get("/observabilidade-ia")
async def dashboard_observabilidade_ia(request: Request, current_user: AuthContext = Depends(require_staff)):
    """
    Painel de observabilidade do chatbot: volume de uso, conversão de
    atendimento e tópicos não compreendidos pelo modelo (RF24).
    """
    manager_agent = getattr(request.app.state, "manager_agent", None)
    if not manager_agent:
        return {"status": "error", "message": "Manager agent não inicializado"}

    return {
        "status": "success",
        "metrics": manager_agent.get_observability_snapshot(),
    }
