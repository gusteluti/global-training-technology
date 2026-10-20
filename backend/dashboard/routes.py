"""
Dashboards operacionais da Área do Funcionário (Fase 2 - item 1.2 do escopo):
Dashboard de Alunos, Dashboard de Cursos, Dashboard Financeiro e o painel de
Observabilidade do Chatbot (RF23/RF24), todos protegidos por RBAC (RF21).
"""

from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from core.audit import record_audit
from core.csv_export import data_sp, decimal_br, resposta_csv, rotulo_matricula, rotulo_pagamento
from core.security import AuthContext, Role, require_roles, require_staff
from db import Database
from admin.routes import id_curso_valido, list_course_summaries

router = APIRouter()

# Exportação em massa de dado pessoal: só Gestão e Financeiro (D74). Suporte e aluno recebem 403.
require_exportacao = require_roles(Role.ADMIN, Role.FINANCIAL)

PAGE_SIZE_PADRAO = 50
PAGE_SIZE_MAXIMO = 200

ERRO_ALUNO_NAO_ENCONTRADO = "Aluno não encontrado"
ERRO_CURSO_NAO_ENCONTRADO = "Course not found"


def _pode_ver_valores(current_user: AuthContext) -> bool:
    """Política D68: Gestão e Financeiro veem valores; Suporte vê só status (a chave `amount` nem aparece)."""
    return current_user.role in (Role.ADMIN, Role.FINANCIAL)


def _sem_amount(itens):
    return [{chave: valor for chave, valor in item.items() if chave != "amount"} for item in itens]


def _paginar(itens: List, page: Optional[int], page_size: Optional[int]) -> Tuple[List, Dict]:
    """U1 (D74): sem `page` devolve tudo (page 1, page_size = total); com `page`, fatia de `page_size`
    (padrão 50, acima de 200 vale 200). Página além da última: lista vazia, `total` preservado."""
    total = len(itens)
    if page is None:
        return itens, {"page": 1, "page_size": total, "total": total}
    tamanho = min(page_size or PAGE_SIZE_PADRAO, PAGE_SIZE_MAXIMO)
    inicio = (page - 1) * tamanho
    return itens[inicio:inicio + tamanho], {"page": page, "page_size": tamanho, "total": total}


def _termo(q: Optional[str]) -> Optional[str]:
    termo = (q or "").strip().lower()
    return termo or None


def _filtrar_alunos(students: List[Dict], q: Optional[str]) -> List[Dict]:
    """Busca sem caixa em nome ou e-mail."""
    termo = _termo(q)
    if termo is None:
        return students
    return [s for s in students
            if termo in (s.get("name") or "").lower() or termo in (s.get("email") or "").lower()]


def _nomes_dos_cursos() -> Dict[str, Optional[str]]:
    return {course["id"]: course.get("name") for course in list_course_summaries(include_archived=True)}


def _filtrar_pagamentos(payments: List[Dict], q: Optional[str], status: Optional[str],
                        nomes: Dict[str, Optional[str]]) -> List[Dict]:
    """Busca sem caixa em e-mail, nome do aluno ou curso (id ou nome); `status` exato do pagamento."""
    termo = _termo(q)
    status = (status or "").strip() or None
    resultado = []
    for pagamento in payments:
        if status is not None and pagamento.get("status") != status:
            continue
        if termo is not None:
            campos = (pagamento.get("student_email"), pagamento.get("student_name"), pagamento.get("course_id"),
                      nomes.get(pagamento.get("course_id")))
            if not any(termo in (campo or "").lower() for campo in campos):
                continue
        resultado.append(pagamento)
    return resultado


def _alunos_do_curso(course_id: str, status: Optional[str], class_id: Optional[str]):
    """Curso do catálogo (None se não existir) e as matrículas filtradas (F4, D73)."""
    if not id_curso_valido(course_id):
        return None, []  # S10 (D79): id fora do padrão vale como curso inexistente
    catalogo = {course["id"]: course for course in list_course_summaries(include_archived=True)}
    curso = catalogo.get(course_id)
    if curso is None:
        return None, []

    sem_turma = class_id is not None and class_id.strip().lower() == "none"
    if class_id is not None and not sem_turma:
        try:
            turma = int(class_id)
        except ValueError:
            return curso, []  # class_id não numérico: nenhuma turma corresponde
        return curso, Database.list_students_of_course(course_id, status, turma)
    return curso, Database.list_students_of_course(course_id, status, None, sem_turma)


def _registrar_exportacao(current_user: AuthContext, relatorio: str, linhas: int) -> None:
    """Evento `export.csv` (D74), gravado só quando a exportação acontece; responsável sempre do token."""
    record_audit(
        "export.csv",
        f"Exportação CSV: {relatorio} ({linhas} linhas)",
        user=current_user,
        entity_type="report",
        entity_id=relatorio,
    )


@router.get("/alunos.csv")
async def dashboard_alunos_csv(q: Optional[str] = None, current_user: AuthContext = Depends(require_exportacao)):
    """CSV da lista de alunos (D74), com a mesma busca da lista. Só Gestão e Financeiro."""
    students = _filtrar_alunos(Database.get_students_overview(), q)
    linhas = [
        [s.get("name"), s.get("email"), data_sp(s.get("created_at")), s.get("total_enrollments") or 0,
         s.get("active_enrollments") or 0, data_sp(s.get("last_enrollment_at")), s.get("chat_messages") or 0,
         data_sp(s.get("last_chat_at"))]
        for s in students
    ]
    resposta = resposta_csv(
        "alunos",
        ["Nome", "E-mail", "Cadastro", "Matrículas", "Matrículas ativas", "Última matrícula",
         "Mensagens no chat", "Último chat"],
        linhas,
    )
    _registrar_exportacao(current_user, "alunos", len(linhas))
    return resposta


@router.get("/alunos")
async def dashboard_alunos(
    request: Request,
    q: Optional[str] = None,
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1),
    current_user: AuthContext = Depends(require_staff),
):
    """
    Métricas quantitativas de matriculados, listagem de alunos ativos e
    histórico de interações (RF23). Disponível para todos os perfis internos,
    já que o Suporte precisa acompanhar dados acadêmicos dos alunos.
    U1 (D74): `q` (nome ou e-mail, sem caixa) e paginação; `metrics` continuam globais.
    """
    Database.expirar_pendentes()  # S6 (D81)
    students = Database.get_students_overview()
    total_students = len(students)
    active_students = sum(1 for student in students if (student.get("active_enrollments") or 0) > 0)
    manager_agent = getattr(request.app.state, "manager_agent", None)
    total_chat_sessions = len(manager_agent.sessions) if manager_agent else 0
    pagina, pagination = _paginar(_filtrar_alunos(students, q), page, page_size)

    return {
        "status": "success",
        "metrics": {
            "total_students": total_students,
            "active_students": active_students,
            "total_chat_sessions": total_chat_sessions,
        },
        "students": pagina,
        "pagination": pagination,
    }


@router.get("/alunos/{user_id}")
async def dashboard_aluno_detalhe(user_id: int, current_user: AuthContext = Depends(require_staff)):
    """
    Detalhe de um aluno (F3, D73): matrículas com turma, pagamentos e resumo do chat. Id que não é de
    aluno (inexistente, funcionário, fora do intervalo) responde o mesmo 404. Suporte não recebe `amount`.
    """
    Database.expirar_pendentes()  # S6 (D81)
    detalhe = Database.get_student_detail(user_id)
    if detalhe is None:
        raise HTTPException(status_code=404, detail=ERRO_ALUNO_NAO_ENCONTRADO)

    nomes = {course["id"]: course.get("name") for course in list_course_summaries(include_archived=True)}
    aluno = detalhe["student"]
    enrollments = [
        {**item, "course_name": nomes.get(item["course_id"]) or item["course_id"]}
        for item in detalhe["enrollments"]
    ]
    payments = detalhe["payments"]
    if not _pode_ver_valores(current_user):
        payments = _sem_amount(payments)

    return {
        "status": "success",
        "student": {
            "id": aluno["id"],
            "name": aluno["name"],
            "email": aluno["email"],
            "created_at": aluno["created_at"],
            "is_active": bool(aluno["is_active"]),
        },
        "enrollments": enrollments,
        "payments": payments,
        "chat": {"messages": aluno["chat_messages"] or 0, "last_chat_at": aluno["last_chat_at"]},
    }


@router.get("/cursos/{course_id}/alunos.csv")
async def dashboard_curso_alunos_csv(
    course_id: str,
    status: Optional[str] = None,
    class_id: Optional[str] = None,
    current_user: AuthContext = Depends(require_exportacao),
):
    """CSV dos alunos de um curso (D74), com os mesmos filtros da lista. Só Gestão e Financeiro."""
    curso, students = _alunos_do_curso(course_id, status, class_id)
    if curso is None:
        raise HTTPException(status_code=404, detail=ERRO_CURSO_NAO_ENCONTRADO)
    linhas = [
        [s.get("name"), s.get("email"), s.get("enrollment_id"), rotulo_matricula(s.get("status")),
         data_sp(s.get("enrolled_at")), s.get("class_name") or "", rotulo_pagamento(s.get("payment_status")),
         decimal_br(s.get("amount"))]
        for s in students
    ]
    resposta = resposta_csv(
        f"{course_id}_alunos",
        ["Nome", "E-mail", "Matrícula", "Status da matrícula", "Data da matrícula", "Turma",
         "Status do pagamento", "Valor (R$)"],
        linhas,
    )
    _registrar_exportacao(current_user, f"curso:{course_id}", len(linhas))
    return resposta


@router.get("/cursos/{course_id}/alunos")
async def dashboard_curso_alunos(
    course_id: str,
    status: Optional[str] = None,
    class_id: Optional[str] = None,
    current_user: AuthContext = Depends(require_staff),
):
    """
    Alunos de um curso do catálogo (F4, D73), inclusive arquivado. Filtros opcionais `status` e `class_id`
    (`none` = sem turma). Matrícula mais recente primeiro. Suporte não recebe `amount`.
    """
    Database.expirar_pendentes()  # S6 (D81)
    curso, students = _alunos_do_curso(course_id, status, class_id)
    if curso is None:
        raise HTTPException(status_code=404, detail=ERRO_CURSO_NAO_ENCONTRADO)

    if not _pode_ver_valores(current_user):
        students = _sem_amount(students)

    return {
        "status": "success",
        "course": {
            "id": curso["id"],
            "name": curso.get("name"),
            "archived": curso.get("archived") is True,
        },
        "total": len(students),
        "students": students,
    }


@router.get("/cursos")
async def dashboard_cursos(current_user: AuthContext = Depends(require_staff)):
    """
    Performance do catálogo: inscritos por turma e taxa de conversão (RF23).
    """
    Database.expirar_pendentes()  # S6 (D81)
    catalog = {course["id"]: course for course in list_course_summaries(include_archived=True)}
    overview_by_course = {row["course_id"]: row for row in Database.get_courses_overview()}
    classes_by_course = {}
    for turma in Database.list_classes():
        classes_by_course.setdefault(turma["course_id"], []).append(turma)
    unassigned_by_course = Database.get_unassigned_counts()

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
            "archived": course.get("archived") is True,  # F1: arquivado continua com o histórico
            "total_enrollments": total_enrollments,
            "approved_enrollments": approved_enrollments,
            "pending_enrollments": overview.get("pending_enrollments", 0) or 0,
            "conversion_rate": round(conversion_rate, 1),
            # L1 (D53): inscritos por turma e matrículas ativas/pendentes ainda sem turma.
            "classes": classes_by_course.get(course_id, []),
            "unassigned": unassigned_by_course.get(course_id, {"total": 0, "active": 0, "pending": 0}),
        })

    courses.sort(key=lambda course: course["total_enrollments"], reverse=True)

    return {
        "status": "success",
        "total_courses": len(courses),
        "courses": courses,
    }


@router.get("/financeiro.csv")
async def dashboard_financeiro_csv(
    q: Optional[str] = None,
    status: Optional[str] = None,
    current_user: AuthContext = Depends(require_exportacao),
):
    """CSV dos pagamentos (D74), com a mesma busca e o mesmo filtro de status da lista. Só Gestão e Financeiro."""
    nomes = _nomes_dos_cursos()
    payments = _filtrar_pagamentos(Database.get_payments_overview(limit=None), q, status, nomes)
    linhas = [
        [p.get("id"), data_sp(p.get("created_at")), p.get("student_name"), p.get("student_email"),
         nomes.get(p.get("course_id")) or p.get("course_id"), decimal_br(p.get("amount")),
         rotulo_pagamento(p.get("status")), p.get("payment_method")]
        for p in payments
    ]
    resposta = resposta_csv(
        "financeiro",
        ["Pagamento", "Data", "Aluno", "E-mail", "Curso", "Valor (R$)", "Status", "Forma de pagamento"],
        linhas,
    )
    _registrar_exportacao(current_user, "financeiro", len(linhas))
    return resposta


@router.get("/financeiro")
async def dashboard_financeiro(
    q: Optional[str] = None,
    status: Optional[str] = None,
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1),
    current_user: AuthContext = Depends(require_roles(Role.ADMIN, Role.FINANCIAL)),
):
    """
    Valores globais arrecadados, status de transações e projeção de receita.
    Restrito a Gestão/Financeiro (RF23 + item 2 do escopo - RBAC).
    U1 (D74): a lista `payments` aceita `q` (e-mail, nome ou curso), `status` e paginação; sem `page` vem
    inteira (sem o antigo corte de 50). Totais, `by_status` e `monthly_revenue` continuam globais.
    """
    Database.expirar_pendentes()  # S6 (D81)
    summary = Database.get_financial_summary()
    payments = _filtrar_pagamentos(Database.get_payments_overview(limit=None), q, status, _nomes_dos_cursos())
    pagina, pagination = _paginar(payments, page, page_size)

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
        "payments": pagina,
        "pagination": pagination,
    }


@router.get("/observabilidade-ia")
async def dashboard_observabilidade_ia(request: Request, current_user: AuthContext = Depends(require_staff)):
    """
    Painel de observabilidade do chatbot (RF24, E7/D42): uso do LLM (tokens, latência, custo), desfecho das
    mensagens, taxa de resolução, conversão de atendimento e tópicos não compreendidos. Tudo lido do banco
    (sobrevive ao restart). Taxas são fração de 0 a 1. O Suporte não recebe nenhum campo de custo
    (dado financeiro, item 2 do escopo): Gestão e Financeiro recebem.
    """
    manager_agent = getattr(request.app.state, "manager_agent", None)
    if not manager_agent:
        return {"status": "error", "message": "Manager agent não inicializado"}

    pode_ver_custo = current_user.role in (Role.ADMIN, Role.FINANCIAL)

    interacoes = Database.get_ai_interaction_stats()
    outcomes = interacoes.pop("outcomes")
    atendidas = sum(outcomes[o] for o in ("answered", "unresolved", "output_blocked", "llm_error"))
    resolution_rate = round(outcomes["answered"] / atendidas, 4) if atendidas else 0

    conversao = Database.get_ai_conversion()
    conversion = {
        **conversao,
        "rate": round(conversao["converted"] / conversao["students_with_chat"], 4)
        if conversao["students_with_chat"] else 0,
    }

    usage = Database.get_ai_usage_totals()
    per_day = Database.get_ai_usage_per_day(14)
    if not pode_ver_custo:
        usage.pop("cost_usd", None)
        per_day = [{chave: valor for chave, valor in dia.items() if chave != "cost_usd"} for dia in per_day]

    return {
        "status": "success",
        "metrics": {
            **interacoes,
            "model": manager_agent.llm.model,
            "usage": usage,
            "outcomes": outcomes,
            "resolution_rate": resolution_rate,
            "conversion": conversion,
            "unresolved_topics": Database.get_ai_unresolved_topics(10),
            "per_day": per_day,
            # F6 (D77): encaminhamentos ao WhatsApp; não é custo, vale para todos os perfis.
            "handoff": Database.get_ai_handoff_stats(),
        },
    }
