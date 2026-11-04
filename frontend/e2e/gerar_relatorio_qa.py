"""Gera docs/qa/RELATORIO_QA.md a partir do resultado real da suíte de QA (D104).

Uso: py -3 frontend/e2e/gerar_relatorio_qa.py <junit.xml> <cobertura.json> [defeitos.json]
Lê qa_catalogo.json e qa_rotas.log, gravados pela suíte na pasta temporária do sistema.
"""

import json
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TECNICAS = {
    "EP": "Partição de equivalência", "BVA": "Análise de valor-limite", "DT": "Tabela de decisão",
    "ST": "Transição de estado", "UC": "Caso de uso", "EG": "Suposição de erro", "SEC": "Segurança",
    "CONC": "Concorrência",
}
REQUISITOS = {
    "RF21": "Autenticação restrita, separando alunos e funcionários",
    "RF22": "Área do aluno: cursos e pagamentos",
    "RF23": "Área do funcionário: dashboards consolidados",
    "RF24": "Observabilidade de IA: eficácia, volume e custos",
    "E1.1-Financeiro": "Histórico financeiro e recibos",
    "E1.2-Alunos": "Dashboard de alunos",
    "E1.2-Cursos": "Dashboard de cursos: inscritos por turma e conversão",
    "E1.2-Financeiro": "Dashboard financeiro: arrecadado, projeção e transações",
    "E2-RBAC": "Controle de acesso por perfil",
    "E2-Auditoria": "Trilha de auditoria",
    "E3-SPA": "Single Page Application em Angular",
    "E3-API": "API REST desacoplada",
    "E4-Historico": "Chatbot com histórico autenticado",
    "E4-LLM": "Proteção contra manipulação do LLM",
    "PAG": "Compra, webhook e reembolso (D48, D75)",
    "CANC": "Cancelamento em 7 dias (D82)",
    "CAD": "Cadastro, arquivamento e exclusão de cursos (D51, D68)",
    "TUR": "Turmas e matrícula manual (D53, D83)",
    "SALA": "Sala do curso e certificado (D91, D103)",
    "SALA-IA": "Assistente com os arquivos do curso (D107)",
}


def casos(junit):
    for caso in ET.parse(junit).getroot().iter("testcase"):
        falha = caso.find("failure")
        if falha is None:
            falha = caso.find("error")
        funcao = caso.get("name").split("[")[0]
        yield funcao, caso.get("name"), falha


def main():
    junit, cobertura = sys.argv[1], json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    defeitos = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8")) if len(sys.argv) > 3 else []
    pasta = Path(tempfile.gettempdir())
    catalogo = json.loads((pasta / "qa_catalogo.json").read_text(encoding="utf-8"))
    rotas = (pasta / "qa_rotas.log").read_text(encoding="utf-8").splitlines()

    por_funcao, tecnicas, por_req = defaultdict(lambda: [0, 0]), Counter(), defaultdict(lambda: [0, 0, []])
    total = falhas = 0
    falhados = []
    for funcao, nome, falha in casos(junit):
        item = catalogo[funcao]
        total += 1
        tecnicas[item["tec"]] += 1
        por_funcao[funcao][0] += 1
        por_req[item["req"]][0] += 1
        if item["id"] not in por_req[item["req"]][2]:
            por_req[item["req"]][2].append(item["id"])
        if falha is None:
            por_funcao[funcao][1] += 1
            por_req[item["req"]][1] += 1
        else:
            falhas += 1
            falhados.append(f"{item['id']} {nome}")

    linhas = ["# Relatório de QA (ISTQB)", "",
              "Gerado por `frontend/e2e/gerar_relatorio_qa.py` a partir do resultado real da suíte "
              "`frontend/e2e/test_qa_istqb.py`. Não edite à mão.", "", "## Resumo", "",
              f"- Casos executados: **{total}** ({len(por_funcao)} cenários do catálogo)",
              f"- Passaram: **{total - falhas}**. Falharam: **{falhas}**.",
              f"- Requisitos com caso de teste: **{sum(1 for r in REQUISITOS if r in por_req)} de {len(REQUISITOS)}**",
              f"- Endpoints exercitados: **{cobertura['endpoints_atingidos']} de {cobertura['endpoints_total']}**",
              f"- Telas exercitadas: **{cobertura['telas_atingidas']} de {cobertura['telas_total']}**",
              f"- Cobertura de linhas do backend: **{cobertura['linhas']}** ({cobertura['linhas_origem']})",
              f"- Cobertura de ramos do backend: **{cobertura['ramos']}**",
              "", "O frontend não tem medição de cobertura de código: a cobertura dele é de telas e fluxos.", "",
              "## Casos por técnica", "", "| Técnica | Casos |", "|---|---|"]
    linhas += [f"| {TECNICAS[t]} | {n} |" for t, n in tecnicas.most_common()]
    linhas += ["", "## Matriz de rastreabilidade", "", "| Requisito | Descrição | Casos | Passaram | Cenários |",
               "|---|---|---:|---:|---|"]
    for req, descricao in REQUISITOS.items():
        n, ok, ids = por_req.get(req, [0, 0, []])
        linhas.append(f"| {req} | {descricao} | {n} | {ok} | {', '.join(ids) or '**sem caso**'} |")
    linhas += ["", "## Defeitos encontrados", ""]
    if defeitos:
        linhas += ["| Id | Sev. | Caso | Descrição | Situação |", "|---|---|---|---|---|"]
        linhas += [f"| {d['id']} | {d['sev']} | {d['caso']} | {d['desc']} | {d['situacao']} |" for d in defeitos]
    else:
        linhas.append("Nenhum.")
    if falhados:
        linhas += ["", "## Casos que falharam nesta execução", ""] + [f"- {f}" for f in falhados]
    linhas += ["", "## Catálogo de cenários", "", "| Id | Requisito | Técnica | Cenário | Casos | Passaram |",
               "|---|---|---|---|---:|---:|"]
    for funcao, item in sorted(catalogo.items(), key=lambda par: par[1]["id"]):
        n, ok = por_funcao.get(funcao, [0, 0])
        linhas.append(f"| {item['id']} | {item['req']} | {item['tec']} | {item['desc']} | {n} | {ok} |")
    linhas += ["", f"Chamadas à API registradas na execução: {len(rotas)}."]
    saida = REPO / "docs" / "qa" / "RELATORIO_QA.md"
    saida.parent.mkdir(exist_ok=True)
    saida.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(saida, re.sub(r"\s+", " ", f"total={total} falhas={falhas}"))


if __name__ == "__main__":
    main()
