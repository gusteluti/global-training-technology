"""Base institucional do chatbot (GR1, D95): RAG das políticas com fonte e "não sei".

Índice SQLite FTS5 **em memória** (sem dependência nova, não toca o db.sqlite) montado a partir dos arquivos
`*.md` de `KNOWLEDGE_DIR` (lida a cada consulta; padrão `backend/knowledge`). O índice é reconstruído quando o
conjunto de arquivos, o mtime ou o tamanho muda (mesmo padrão do `refresh_courses_if_changed`). Pasta vazia ou
inexistente vira índice vazio: o chat segue como antes.

Cada arquivo tem um cabeçalho YAML simples (`id`, `titulo`, `visibilidade` publico|aluno, `curso` opcional) e o
corpo é dividido em trechos pelas seções `##` (até ~900 caracteres cada). Arquivo sem `id` ou com `visibilidade`
fora do vocabulário fica fora do índice (nunca é recuperado).

Controle de acesso (item 4 do checklist): visitante recupera só `publico`; aluno recupera `publico`, `aluno` sem
curso e `aluno` de curso em que ele tem matrícula `active`. Os ids de curso vêm do servidor (JWT -> banco), nunca
do corpo da requisição.
"""

import os
import re
import sqlite3
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from agents.llm_guard import mascarar_pii
from core import conteudos

VAR_BASE = "KNOWLEDGE_DIR"
DIRETORIO_PADRAO = Path(__file__).resolve().parent.parent / "knowledge"

VISIBILIDADES = ("publico", "aluno")
K_PADRAO = 3
MAX_TRECHO = 900
# bm25() do FTS5 é negativo: quanto mais negativo, mais relevante. O corte só descarta casamentos quase nulos
# (termo presente em quase todos os trechos); os acertos medidos nos testes ficam entre -3,96 e -11.
CORTE_BM25 = -0.5

# Stopwords pt (e palavras de cortesia/genéricas do domínio que aparecem em quase todo texto).
STOPWORDS = frozenset("""
a o as os um uma uns umas ao aos à às de do da dos das em no na nos nas num numa por pelo pela pelos pelas
para pra pro com sem e ou mas nem que se como qual quais quanto quanta quantos quantas quando onde porque pq
eu tu voce voces ele ela eles elas nos vos me te lhe lhes mim meu minha meus minhas teu tua seu sua seus suas
nosso nossa este esta estes estas esse essa esses essas isto isso aquilo aquele aquela aqui ali la ai ja
e eh sao ser sou foi era estar esta estou estao tem tenho temos ter ha havia vai vou fazer faz fiz
posso pode podem poderia quero queria gostaria preciso saber sobre mais menos muito muita bem tambem so ainda
sim nao ola oi bom boa dia tarde noite obrigado obrigada favor ok entao algum alguma alguns algumas todo toda
todos todas cada outro outra the of to and is
curso cursos
""".split())

PEDIDO_DE_MATERIAL = frozenset("""material materiais conteudo conteudos apostila apostilas aula aulas video videos
modulo modulos pdf pdfs arquivo arquivos""".split())

_TOKEN = re.compile(r"[a-z0-9]+")
_CABECALHO = re.compile(r"\A﻿?---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
_SECAO = re.compile(r"^##[ \t]+(.+?)[ \t]*#*[ \t]*$", re.M)


@dataclass(frozen=True)
class Trecho:
    doc_id: str
    titulo: str
    secao: str
    visibilidade: str
    curso: Optional[str]
    texto: str


def diretorio_base() -> Path:
    """KNOWLEDGE_DIR lida em tempo de execução (os testes apontam para um diretório temporário)."""
    bruto = (os.getenv(VAR_BASE) or "").strip()
    return Path(bruto) if bruto else DIRETORIO_PADRAO


def _sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto or "")
    return "".join(ch for ch in decomposto if unicodedata.category(ch) not in ("Mn", "Cf")).lower()


def tokens(texto: Optional[str]) -> List[str]:
    """Tokens minúsculos, sem acento, só [a-z0-9]."""
    return _TOKEN.findall(_sem_acento(texto or ""))


def termos_da_consulta(texto: Optional[str]) -> List[str]:
    """Termos da consulta sem stopwords e sem repetição, na ordem em que aparecem."""
    vistos: List[str] = []
    for token in tokens(texto):
        if token in STOPWORDS or token in vistos:
            continue
        vistos.append(token)
    return vistos


# --- Leitura dos documentos -------------------------------------------------------------

def _valor_yaml(bruto: str) -> str:
    valor = bruto.strip()
    if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
        valor = valor[1:-1]
    return valor.strip()


def ler_cabecalho(conteudo: str) -> Tuple[Dict[str, str], str]:
    """(campos do cabeçalho YAML simples `chave: valor`, corpo). Sem cabeçalho -> ({}, conteúdo)."""
    achado = _CABECALHO.match(conteudo)
    if not achado:
        return {}, conteudo
    campos: Dict[str, str] = {}
    for linha in achado.group(1).splitlines():
        if not linha.strip() or linha.lstrip().startswith("#") or ":" not in linha:
            continue
        chave, valor = linha.split(":", 1)
        campos[chave.strip().lower()] = _valor_yaml(valor)
    return campos, conteudo[achado.end():]


def _partir(texto: str, limite: int = MAX_TRECHO) -> List[str]:
    """Divide o texto da seção em pedaços de até `limite` caracteres, por parágrafo e, se preciso, por palavra."""
    texto = texto.strip()
    if len(texto) <= limite:
        return [texto] if texto else []
    pedacos: List[str] = []
    atual = ""
    for paragrafo in re.split(r"\n\s*\n", texto):
        paragrafo = paragrafo.strip()
        if not paragrafo:
            continue
        candidato = f"{atual}\n\n{paragrafo}" if atual else paragrafo
        if len(candidato) <= limite:
            atual = candidato
            continue
        if atual:
            pedacos.append(atual)
        atual = ""
        while len(paragrafo) > limite:
            corte = paragrafo.rfind(" ", 0, limite)
            corte = corte if corte > 0 else limite
            pedacos.append(paragrafo[:corte].strip())
            paragrafo = paragrafo[corte:].strip()
        atual = paragrafo
    if atual:
        pedacos.append(atual)
    return pedacos


def trechos_do_documento(conteudo: str) -> List[Trecho]:
    """Trechos (um por seção `##`, partidos em até ~900 caracteres) de um documento válido; [] se inválido."""
    campos, corpo = ler_cabecalho(conteudo)
    doc_id = campos.get("id", "")
    visibilidade = campos.get("visibilidade", "").lower()
    if not doc_id or visibilidade not in VISIBILIDADES:
        return []
    titulo = campos.get("titulo") or doc_id
    curso = campos.get("curso") or None

    secoes: List[Tuple[str, str]] = []
    marcas = list(_SECAO.finditer(corpo))
    introducao = corpo[:marcas[0].start()] if marcas else corpo
    if introducao.strip():
        secoes.append(("", introducao))
    for i, marca in enumerate(marcas):
        fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(corpo)
        secoes.append((marca.group(1).strip(), corpo[marca.end():fim]))

    trechos: List[Trecho] = []
    for secao, texto in secoes:
        for pedaco in _partir(texto):
            trechos.append(Trecho(doc_id, titulo, secao, visibilidade, curso, pedaco))
    return trechos


def trechos_dos_arquivos() -> List[Trecho]:
    """Apostilas e demais arquivos publicados dos cursos (D107). São conteúdo pago: sempre `aluno` do curso, ou seja,
    só chegam a quem tem matrícula ativa nele (`_visivel`). Dado pessoal escrito no arquivo, como uma lista de presença,
    é mascarado aqui: o modelo nunca recebe o CPF de outra pessoa."""
    trechos: List[Trecho] = []
    for documento in conteudos.documentos_para_o_assistente():
        for numero, pagina in enumerate(documento["pages"], 1):
            for pedaco in _partir(mascarar_pii(pagina)[0]):
                trechos.append(Trecho(f"conteudo:{documento['id']}", documento["title"], f"Página {numero}", "aluno",
                                      documento["course_id"], pedaco))
    for sumario in conteudos.sumarios_para_o_assistente():
        for pedaco in _partir(mascarar_pii(sumario["text"])[0]):
            trechos.append(Trecho(f"sala:{sumario['course_id']}", sumario["title"], "", "aluno", sumario["course_id"], pedaco))
    return trechos


# --- Índice -----------------------------------------------------------------------------

def _visivel(trecho: Trecho, aluno: bool, cursos_ativos: frozenset) -> bool:
    if trecho.visibilidade == "publico":
        return True
    if trecho.visibilidade != "aluno" or not aluno:
        return False
    return trecho.curso is None or trecho.curso in cursos_ativos


def _aderente(trecho: Trecho, termos: List[str]) -> bool:
    """D107: com 3 ou mais termos, uma palavra genérica em comum não basta para o trecho virar fonte."""
    if len(termos) < 3:
        return True
    presentes = set(tokens(f"{trecho.titulo} {trecho.secao} {trecho.texto}"))
    return sum(termo in presentes for termo in termos) >= 2


def _assinatura_dos_arquivos() -> Tuple:
    try:
        return conteudos.assinatura_para_o_assistente()
    except sqlite3.Error:
        return ()


class BaseInstitucional:
    """Índice FTS5 em memória da base institucional, reconstruído quando os arquivos mudam."""

    def __init__(self):
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._trechos: List[Trecho] = []
        self._assinatura: Optional[Tuple] = None

    @staticmethod
    def _assinatura_de(diretorio: Path) -> Tuple:
        itens = []
        try:
            arquivos = sorted(diretorio.glob("*.md")) if diretorio.is_dir() else []
        except OSError:
            arquivos = []
        for arquivo in arquivos:
            try:
                estado = arquivo.stat()
            except OSError:
                continue
            itens.append((arquivo.name, estado.st_mtime_ns, estado.st_size))
        return (str(diretorio), tuple(itens))

    def _montar(self, diretorio: Path) -> None:
        trechos: List[Trecho] = []
        try:
            arquivos = sorted(diretorio.glob("*.md")) if diretorio.is_dir() else []
        except OSError:
            arquivos = []
        for arquivo in arquivos:
            try:
                conteudo = arquivo.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as erro:
                print(f"[AVISO] Base institucional: {arquivo.name} ignorado ({type(erro).__name__})")
                continue
            achados = trechos_do_documento(conteudo)
            if not achados:
                print(f"[AVISO] Base institucional: {arquivo.name} sem cabeçalho válido (id/visibilidade)")
            trechos.extend(achados)
        try:
            trechos.extend(trechos_dos_arquivos())
        except Exception as erro:  # sem os arquivos, a base institucional continua valendo
            print(f"[AVISO] Base institucional: arquivos dos cursos ignorados ({type(erro).__name__})")

        conn = sqlite3.connect(":memory:", check_same_thread=False)
        try:
            conn.execute("CREATE VIRTUAL TABLE trechos USING fts5(conteudo, tokenize = 'unicode61')")
            conn.executemany(
                "INSERT INTO trechos (rowid, conteudo) VALUES (?, ?)",
                [
                    (i, " ".join(tokens(f"{t.titulo} {t.secao} {t.texto}")))
                    for i, t in enumerate(trechos)
                ],
            )
            conn.commit()
        except sqlite3.Error as erro:
            print(f"[AVISO] Base institucional indisponível (FTS5): {type(erro).__name__}")
            conn.close()
            conn, trechos = None, []
        if self._conn is not None:
            self._conn.close()
        self._conn = conn
        self._trechos = trechos

    def atualizar_se_mudou(self) -> bool:
        """Reconstrói o índice se o conjunto de arquivos (nome, mtime, tamanho) ou o diretório mudou."""
        diretorio = diretorio_base()
        assinatura = (self._assinatura_de(diretorio), _assinatura_dos_arquivos())
        with self._lock:
            if assinatura == self._assinatura:
                return False
            self._montar(diretorio)
            self._assinatura = assinatura
            print(f"[OK] Base institucional: {len(self._trechos)} trecho(s) de {diretorio.name or diretorio}")
            return True

    def buscar(self, consulta: Optional[str], *, aluno: bool = False, cursos_ativos: Iterable[str] = (),
               k: int = K_PADRAO) -> List[Trecho]:
        """Até `k` trechos visíveis para quem pergunta, do mais ao menos relevante (bm25), acima do corte."""
        try:
            self.atualizar_se_mudou()
        except Exception as erro:  # a base nunca derruba o chat
            print(f"[AVISO] Base institucional: falha ao atualizar ({type(erro).__name__})")
        termos = termos_da_consulta(consulta)
        if not termos:
            return []
        expressao = " OR ".join(f'"{termo}"' for termo in termos)
        ativos = frozenset(cursos_ativos or ())
        with self._lock:
            if self._conn is None or not self._trechos:
                return []
            try:
                linhas = self._conn.execute(
                    "SELECT rowid, bm25(trechos) AS nota FROM trechos WHERE trechos MATCH ? ORDER BY nota",
                    (expressao,),
                ).fetchall()
            except sqlite3.Error as erro:
                print(f"[AVISO] Base institucional: consulta falhou ({type(erro).__name__})")
                return []
            trechos = self._trechos
        achados: List[Trecho] = []
        for rowid, nota in linhas:
            if nota > CORTE_BM25:
                continue
            trecho = trechos[rowid]
            if not _visivel(trecho, aluno, ativos) or not _aderente(trecho, termos):
                continue
            achados.append(trecho)
            if len(achados) >= k:
                break
        # D107: "quais materiais tem?" não cita o curso; a lista da sala vem antes das políticas que usam as mesmas palavras.
        if aluno and PEDIDO_DE_MATERIAL & set(termos):
            listas = [t for t in trechos if t.doc_id.startswith("sala:") and _visivel(t, aluno, ativos)]
            achados = (listas + [t for t in achados if t not in listas])[:k]
        return achados


def fontes(trechos: Iterable[Trecho]) -> List[Dict[str, str]]:
    """`sources` da resposta: {id, title} por documento, sem repetição, na ordem de relevância (D96)."""
    vistos = set()
    lista: List[Dict[str, str]] = []
    for trecho in trechos:
        if trecho.doc_id in vistos:
            continue
        vistos.add(trecho.doc_id)
        lista.append({"id": trecho.doc_id, "title": trecho.titulo})
    return lista


# --- Tema de política ("não sei" determinístico) ---------------------------------------

LEXICO_POLITICA = frozenset({
    "cancelar", "cancelamento", "reembolso", "devolucao", "arrependimento", "pagamento", "pagar", "parcelar",
    "parcela", "pix", "boleto", "cartao", "certificado", "mec", "lgpd", "privacidade", "prazo", "garantia", "senha",
})
EXPRESSOES_POLITICA = (("dados", "pessoais"), ("excluir", "conta"))


def tema_de_politica(mensagem: Optional[str]) -> bool:
    """True se a mensagem cita um termo do léxico fechado de política (PLANO_GR), sem caixa e sem acento."""
    lista = tokens(mensagem)
    if any(t in LEXICO_POLITICA for t in lista):
        return True
    for expressao in EXPRESSOES_POLITICA:
        n = len(expressao)
        if any(tuple(lista[i:i + n]) == expressao for i in range(len(lista) - n + 1)):
            return True
    return False
