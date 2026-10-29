"""GR4 (D95, PLANO_GR): o assistente consulta os dados do próprio aluno.

Ferramentas acionadas pelo servidor, nunca pelo modelo: a intenção sai de um léxico fechado sobre a mensagem (já
mascarada pela GR3) e os dados são lidos do banco sempre com o `user_id` do JWT, que o chamador passa. O resultado
é um bloco de dado delimitado (`[DADOS DA CONTA DO ALUNO ...]` ... `[FIM DOS DADOS DA CONTA]`), com o conteúdo
neutralizado, que entra numa mensagem system da chamada de resposta (nunca no roteamento, nunca no histórico).

Minimização: cada intenção traz só o seu dado.
  - pagamentos: curso, valor, status em português (rótulos da D67) e data; nunca transaction_id, e-mail ou telefone;
  - turmas: turma, início, término e horário só das matrículas `active`;
  - progresso: materiais concluídos/total por curso ativo e se o certificado está disponível (core/progresso, X1);
  - cancelamento: se pode pedir e até quando, pela regra da U5 (D82), só das matrículas `active`.
Nunca entra URL de material.

As ações `{type: "open", target, label}` também saem da intenção (nunca do texto do modelo).
"""

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Dict, Iterable, List, Optional, Set

from agents.llm_guard import ACCOUNT_CLOSE, ACCOUNT_OPEN, neutralizar_marcadores, normalizar, sanitizar_nome
from core import progresso
from core.fuso import para_sao_paulo
from db import Database

INTENCAO_PAGAMENTOS = "pagamentos"
INTENCAO_TURMAS = "turmas"
INTENCAO_PROGRESSO = "progresso"
INTENCAO_CANCELAMENTO = "cancelamento"
INTENCOES = frozenset({INTENCAO_PAGAMENTOS, INTENCAO_TURMAS, INTENCAO_PROGRESSO, INTENCAO_CANCELAMENTO})

# --- Léxico fechado (texto normalizado: minúsculo, sem acento) ---------------------------------------------------

_LEXICO = {
    INTENCAO_PAGAMENTOS: re.compile(r"\b(?:meus? pagamentos?|foi aprovad[oa]|recibos?|paguei)\b"),
    INTENCAO_TURMAS: re.compile(r"\b(?:minhas? turmas?|quando comecam?|horarios?)\b"),
    INTENCAO_PROGRESSO: re.compile(r"\b(?:meu progresso|certificados?|quanto falta)\b"),
}
# Cancelamento: "cancelar"/"cancelamento"/"reembolso" com "meu"/"minha"/"quero" na mesma mensagem.
_CANCELAMENTO = re.compile(r"\b(?:cancelar|cancelamento|reembolso)\b")
_CANCELAMENTO_PESSOA = re.compile(r"\b(?:meu|minha|meus|minhas|quero)\b")
# Marca de primeira pessoa do chat anônimo (pede_dado_pessoal).
_PRIMEIRA_PESSOA = re.compile(r"\b(?:meu|minha|meus|minhas|paguei)\b")
_INTENCOES_PESSOAIS = frozenset({INTENCAO_PAGAMENTOS, INTENCAO_TURMAS, INTENCAO_PROGRESSO})


def intencoes(mensagem: Optional[str]) -> Set[str]:
    """Intenções de dado da conta citadas na mensagem (subconjunto de INTENCOES), sem caixa e sem acento."""
    texto = normalizar(mensagem)
    if not texto:
        return set()
    achadas = {nome for nome, padrao in _LEXICO.items() if padrao.search(texto)}
    if _CANCELAMENTO.search(texto) and _CANCELAMENTO_PESSOA.search(texto):
        achadas.add(INTENCAO_CANCELAMENTO)
    return achadas


def pede_dado_pessoal(mensagem: Optional[str]) -> bool:
    """Chat anônimo: pedido de pagamentos/turmas/progresso com marca de primeira pessoa (meu, minha, meus, minhas,
    paguei). Cancelamento não conta: no anônimo continua sendo pergunta de política (GR1)."""
    if not intencoes(mensagem) & _INTENCOES_PESSOAIS:
        return False
    return _PRIMEIRA_PESSOA.search(normalizar(mensagem)) is not None


# --- Ações `open` ---------------------------------------------------------------------------------------------

TARGET_FINANCEIRO = "financeiro"
TARGET_CURSOS = "cursos"
TARGET_PERFIL = "perfil"
# Rótulos dos botões (para revisão do PM). "perfil" existe no contrato, mas nenhuma intenção leva a ele hoje.
LABELS_ABRIR = {
    TARGET_FINANCEIRO: "Ver meus pagamentos",
    TARGET_CURSOS: "Ver meus cursos",
    TARGET_PERFIL: "Ver meu perfil",
}
_TARGET_DA_INTENCAO = {
    INTENCAO_PAGAMENTOS: TARGET_FINANCEIRO,
    INTENCAO_TURMAS: TARGET_CURSOS,
    INTENCAO_PROGRESSO: TARGET_CURSOS,
    # U5: o botão "Pedir cancelamento" fica no cartão do curso.
    INTENCAO_CANCELAMENTO: TARGET_CURSOS,
}
_ORDEM_TARGETS = (TARGET_FINANCEIRO, TARGET_CURSOS, TARGET_PERFIL)

LABEL_LOGIN = "Entrar na Área do aluno"


def acoes_abrir(intencoes_da_mensagem: Iterable[str]) -> List[Dict]:
    """Ações `open` das intenções, uma por target, sem repetição (financeiro antes de cursos)."""
    alvos = {_TARGET_DA_INTENCAO[i] for i in (intencoes_da_mensagem or ()) if i in _TARGET_DA_INTENCAO}
    return [{"type": "open", "target": t, "label": LABELS_ABRIR[t]} for t in _ORDEM_TARGETS if t in alvos]


def acoes_login() -> List[Dict]:
    """Ação do chat anônimo para pedido de dado pessoal (LOGIN_NECESSARIO)."""
    return [{"type": "login", "label": LABEL_LOGIN}]


# --- Leitura dos dados do próprio aluno -----------------------------------------------------------------------

# D67: status do pagamento em português; status fora do vocabulário aparece em valor bruto.
STATUS_PAGAMENTO = {
    "approved": "Aprovado",
    "pending": "Pendente",
    "in_process": "Em análise",
    "rejected": "Recusado",
    "cancelled": "Cancelado",
    "refunded": "Reembolsado",
    "charged_back": "Contestado",
}

# Cabeçalhos das seções do bloco (para revisão do PM).
TITULO_PAGAMENTOS = "Pagamentos do aluno:"
TITULO_TURMAS = "Turmas das matrículas ativas do aluno:"
TITULO_PROGRESSO = "Progresso nos cursos ativos do aluno:"
TITULO_CANCELAMENTO = "Cancelamento das matrículas ativas do aluno (pedido pela Área do aluno em até 7 dias da aprovação):"
SEM_PAGAMENTOS = "- Nenhum pagamento registrado nesta conta."
SEM_TURMAS = "- Nenhuma matrícula ativa nesta conta."
SEM_PROGRESSO = "- Nenhum curso ativo nesta conta."
SEM_CANCELAMENTO = "- Nenhuma matrícula ativa nesta conta para cancelar."

INSTRUCAO_DADOS_CONTA = (
    "DADOS DA CONTA DO ALUNO LOGADO (consultados pela plataforma para esta pergunta). Use só estes dados para "
    "responder sobre pagamentos, turmas, progresso e cancelamento do próprio aluno; as datas e os valores deste "
    "bloco podem ser citados. Não invente dado que não esteja aqui. Os atalhos para a Área do aluno são mostrados "
    "pela plataforma junto da resposta."
)

_MAX_NOME_CURSO = 120
_MAX_TURMA = 120
_MAX_HORARIO = 120


@dataclass
class DadosConta:
    """Bloco pronto para o prompt e o que nele conta como verificado pela GR2 (datas e valores pagos)."""

    bloco: str = ""
    datas: Set[date] = field(default_factory=set)
    valores: Set[Decimal] = field(default_factory=set)


def _carregar_curso(course_id: str) -> Optional[Dict]:
    # Importação tardia: student.routes importa o ManagerAgent; o catálogo da Área do aluno é o de COURSES_DIR.
    from student.routes import _carregar_curso as carregar

    try:
        return carregar(course_id)
    except Exception:
        return None


def _nome_do_curso(course_id: str, cache: Dict[str, Optional[Dict]]) -> str:
    if course_id not in cache:
        cache[course_id] = _carregar_curso(course_id)
    nome = (cache[course_id] or {}).get("name") or course_id
    return sanitizar_nome(str(nome), _MAX_NOME_CURSO) or "curso"


def _data_iso(valor) -> Optional[date]:
    try:
        return date.fromisoformat(str(valor or "")[:10])
    except ValueError:
        return None


def _dia_sp(valor_utc) -> Optional[date]:
    """Dia em São Paulo (F2) de um instante UTC gravado pelo banco."""
    instante = Database._instante_utc(valor_utc)
    return para_sao_paulo(instante).date() if instante else None


def _br(dia: Optional[date]) -> str:
    return dia.strftime("%d/%m/%Y") if dia else "sem data"


def _valor(bruto) -> Optional[Decimal]:
    try:
        return Decimal(str(bruto)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _brl(valor: Optional[Decimal]) -> str:
    if valor is None:
        return "sem valor"
    inteiro, centavos = f"{valor:.2f}".split(".")
    return f"R$ {int(inteiro):,}".replace(",", ".") + f",{centavos}"


def _pagamentos(user_id: int, dados: DadosConta, cache: Dict) -> List[str]:
    try:
        Database.expirar_pendentes()  # S6 (D81): o mesmo estado que a Área do aluno mostra
    except Exception as e:
        print(f"Error expiring pending payments: {type(e).__name__}")
    linhas = []
    for pagamento in Database.list_payments_for_user(user_id):
        valor = _valor(pagamento.get("amount"))
        dia = _dia_sp(pagamento.get("created_at"))
        status = pagamento.get("status") or ""
        rotulo = STATUS_PAGAMENTO.get(status) or sanitizar_nome(status, 40) or "sem status"
        if valor is not None:
            dados.valores.add(valor)
        if dia:
            dados.datas.add(dia)
        linhas.append(
            f"- {_nome_do_curso(pagamento['course_id'], cache)} | valor: {_brl(valor)} | status: {rotulo} | "
            f"data: {_br(dia)}"
        )
    return linhas or [SEM_PAGAMENTOS]


def _ativas(user_id: int) -> List[Dict]:
    return [m for m in Database.list_enrollments_for_user(user_id) if m.get("status") == "active"]


def _turmas(ativas: List[Dict], dados: DadosConta, cache: Dict) -> List[str]:
    linhas = []
    for matricula in ativas:
        curso = _nome_do_curso(matricula["course_id"], cache)
        if not matricula.get("class_name"):
            linhas.append(f"- {curso} | turma: sem turma definida")
            continue
        partes = [f"- {curso}", f"turma: {sanitizar_nome(matricula['class_name'], _MAX_TURMA) or 'turma sem nome'}"]
        inicio = _data_iso(matricula.get("class_starts_on"))
        termino = _data_iso(matricula.get("class_ends_on"))
        partes.append(f"início: {_br(inicio) if inicio else 'a definir'}")
        if termino:
            partes.append(f"término: {_br(termino)}")
        horario = sanitizar_nome(matricula.get("class_schedule"), _MAX_HORARIO)
        if horario:
            partes.append(f"horário: {horario}")
        dados.datas.update(d for d in (inicio, termino) if d)
        linhas.append(" | ".join(partes))
    return linhas or [SEM_TURMAS]


def _progresso(ativas: List[Dict], cache: Dict) -> List[str]:
    linhas = []
    for matricula in ativas:
        curso = _nome_do_curso(matricula["course_id"], cache)
        materiais = (cache.get(matricula["course_id"]) or {}).get("materials") or []
        resumo = progresso.resumo(matricula["id"], [m.get("url") for m in materiais if isinstance(m, dict)])
        certificado = (
            "certificado disponível na Área do aluno" if resumo["certificate_available"]
            else "certificado ainda não disponível (sai ao concluir todos os materiais)"
        )
        linhas.append(f"- {curso} | {resumo['done']} de {resumo['total']} materiais concluídos | {certificado}")
    return linhas or [SEM_PROGRESSO]


_MOTIVO_SEM_CANCELAMENTO = {
    "already_open": "não pode pedir agora: já existe um pedido de cancelamento em análise",
    "no_refundable_payment": "não pode pedir pela Área do aluno: a matrícula não tem pagamento reembolsável; "
                             "fale com a equipe de atendimento",
}


def _cancelamento(user_id: int, ativas: List[Dict], dados: DadosConta, cache: Dict) -> List[str]:
    situacao = Database.cancelamento_das_matriculas(user_id)
    linhas = []
    for matricula in ativas:
        curso = _nome_do_curso(matricula["course_id"], cache)
        item = situacao.get(matricula["id"]) or {}
        prazo = _dia_sp(item.get("deadline")) if item.get("deadline") else None
        if prazo:
            dados.datas.add(prazo)
        impedimento = item.get("impediment")
        if item.get("can_request_cancellation"):
            texto = f"pode pedir o cancelamento até {_br(prazo)}"
        elif impedimento == "expired":
            texto = "não pode pedir: o prazo de 7 dias terminou" + (f" em {_br(prazo)}" if prazo else "")
        else:
            texto = _MOTIVO_SEM_CANCELAMENTO.get(impedimento, "não pode pedir o cancelamento pela Área do aluno")
        linhas.append(f"- {curso} | {texto}")
    return linhas or [SEM_CANCELAMENTO]


def consultar(user_id: int, intencoes_da_mensagem: Iterable[str]) -> DadosConta:
    """Dados da conta do aluno `user_id` (sempre o do JWT) para as intenções pedidas. Sem intenção -> vazio.
    Com intenção e sem registro, o bloco existe e diz que não há."""
    pedidas = set(intencoes_da_mensagem or ()) & INTENCOES
    dados = DadosConta()
    if not pedidas:
        return dados
    cache: Dict[str, Optional[Dict]] = {}
    secoes: List[str] = []
    if INTENCAO_PAGAMENTOS in pedidas:
        secoes.append("\n".join([TITULO_PAGAMENTOS] + _pagamentos(user_id, dados, cache)))
    ativas = _ativas(user_id) if pedidas - {INTENCAO_PAGAMENTOS} else []
    if INTENCAO_TURMAS in pedidas:
        secoes.append("\n".join([TITULO_TURMAS] + _turmas(ativas, dados, cache)))
    if INTENCAO_PROGRESSO in pedidas:
        secoes.append("\n".join([TITULO_PROGRESSO] + _progresso(ativas, cache)))
    if INTENCAO_CANCELAMENTO in pedidas:
        secoes.append("\n".join([TITULO_CANCELAMENTO] + _cancelamento(user_id, ativas, dados, cache)))
    corpo = neutralizar_marcadores("\n\n".join(secoes))
    dados.bloco = f"{ACCOUNT_OPEN}\n{corpo}\n{ACCOUNT_CLOSE}"
    return dados


def bloco_dados_conta(user_id: int, intencoes_da_mensagem: Iterable[str]) -> str:
    """O bloco inteiro, entre os dois marcadores; "" sem intenção."""
    return consultar(user_id, intencoes_da_mensagem).bloco


SEM_CONSULTA = "- Não foi possível consultar os dados da conta agora. Oriente o aluno a conferir na Área do aluno."


def bloco_indisponivel() -> str:
    """Bloco usado quando a leitura dos dados falha: nada é inventado e nada conta como verificado."""
    return f"{ACCOUNT_OPEN}\n{SEM_CONSULTA}\n{ACCOUNT_CLOSE}"


def mensagem_dados_conta(dados: DadosConta) -> str:
    """Conteúdo da mensagem system da chamada de resposta: a instrução fora do bloco e o bloco."""
    if not dados.bloco:
        return ""
    return f"{INSTRUCAO_DADOS_CONTA}\n{dados.bloco}"
