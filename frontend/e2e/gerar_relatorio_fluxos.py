"""Gera o relatório de testes em PDF a partir do resultado real (D107): números, defeitos, conversas com o modelo e prints.

Uso: py -3 frontend/e2e/gerar_relatorio_fluxos.py <pasta com junit, fotos e dados.json> <saida.pdf>
Espera na pasta: qa.xml, rag.xml, fluxos.xml, llm.xml, qa_llm_real.json, fotos/ e dados.json
(dados.json: {"data", "suites": [{nome, resultado}], "cobertura", "defeitos": [...], "limites": [...]}).
"""

import base64
import html
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from playwright.sync_api import sync_playwright

e = html.escape


def contagem(arquivo):
    total = falhas = 0
    for caso in ET.parse(arquivo).getroot().iter("testcase"):
        total += 1
        falhas += caso.find("failure") is not None or caso.find("error") is not None
    return total, total - falhas


def imagem(caminho):
    return "data:image/jpeg;base64," + base64.b64encode(caminho.read_bytes()).decode()


def main():
    pasta, saida = Path(sys.argv[1]), Path(sys.argv[2])
    dados = json.loads((pasta / "dados.json").read_text(encoding="utf-8"))
    conversas = json.loads((pasta / "qa_llm_real.json").read_text(encoding="utf-8"))
    fotos = json.loads((pasta / "fotos" / "fotos.json").read_text(encoding="utf-8"))

    linhas_suite = ""
    for suite in dados["suites"]:
        if suite.get("arquivo"):
            total, ok = contagem(pasta / suite["arquivo"])
            resultado = f"{ok} de {total}"
            passou = ok == total
        else:
            resultado, passou = suite["resultado"], suite["ok"]
        classe = "ok" if passou else "nok"
        linhas_suite += (f"<tr><td>{e(suite['nome'])}</td><td>{e(suite['oque'])}</td>"
                         f"<td class='{classe}'>{e(resultado)}</td></tr>")

    defeitos = "".join(
        f"<tr><td>{e(d['id'])}</td><td>{e(d['sev'])}</td><td>{e(d['desc'])}</td><td>{e(d['como'])}</td>"
        f"<td class='ok'>{e(d['situacao'])}</td></tr>" for d in dados["defeitos"])
    falas = "".join(
        f"<div class='fala'><b>{e(c['caso'])}</b><p class='q'>Pergunta: {e(c['pergunta'])}</p>"
        f"<p>Resposta: {e(c['resposta'][:420])}</p>"
        f"<p class='fonte'>Fontes: {e(', '.join(c['fontes']) or 'nenhuma')}</p></div>" for c in conversas)

    grupos, atual, corpo = {}, None, ""
    for foto in fotos:
        grupos.setdefault(foto["fluxo"], []).append(foto)
    numero = 0
    for fluxo, itens in grupos.items():
        corpo += f"<h3>{e(fluxo)}</h3>"
        for foto in itens:
            numero += 1
            corpo += (f"<figure><figcaption><b>Figura {numero}. {e(foto['passo'])}.</b> Resultado: {e(foto['resultado'])}"
                      f"</figcaption><img src='{imagem(pasta / 'fotos' / foto['arquivo'])}'></figure>")
    limites = "".join(f"<li>{e(item)}</li>" for item in dados["limites"])
    resumo = "".join(f"<li>{e(item)}</li>" for item in dados["resumo"])

    documento = f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Relatório de testes</title><style>
@page {{ size: A4; margin: 16mm 15mm; }}
body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #1f2933; font-size: 10.5pt; line-height: 1.45; }}
h1 {{ font-size: 24pt; color: #0077a3; margin: 0 0 3mm; line-height: 1.15; }}
h2 {{ font-size: 15pt; color: #0077a3; margin: 8mm 0 2mm; break-after: avoid; }}
h3 {{ font-size: 12pt; margin: 6mm 0 1mm; break-after: avoid; }}
.sub {{ font-size: 12pt; color: #52606d; margin-bottom: 6mm; }}
.nota {{ background: #eef7fb; border-left: 3px solid #0096c7; padding: 3mm 4mm; margin: 4mm 0; }}
table {{ width: 100%; border-collapse: collapse; font-size: 9pt; margin: 3mm 0; }}
th {{ background: #0077a3; color: #fff; text-align: left; padding: 1.6mm 2mm; }}
td {{ border-bottom: 0.25mm solid #d9e2ec; padding: 1.6mm 2mm; vertical-align: top; }}
tr {{ break-inside: avoid; }} .ok {{ color: #1b7a43; font-weight: 600; }} .nok {{ color: #b42318; font-weight: 600; }}
figure {{ break-inside: avoid; margin: 3mm 0 5mm; }}
figure img {{ display: block; width: auto; max-width: 100%; max-height: 118mm; border: 0.3mm solid #d9e2ec; }}
figcaption {{ margin-bottom: 1.5mm; font-size: 9.5pt; color: #3e4c59; }}
.fala {{ break-inside: avoid; border-bottom: 0.25mm solid #d9e2ec; padding: 2mm 0; font-size: 9.5pt; }}
.fala p {{ margin: 0.6mm 0; }} .q {{ color: #3e4c59; }} .fonte {{ color: #52606d; font-size: 8.5pt; }}
.quebra {{ break-before: page; }} li {{ margin-bottom: 1.2mm; }}
</style><body>
<h1>Relatório de testes</h1>
<div class="sub">Sala do curso, assistente com as apostilas e fluxos principais. {e(dados['data'])}.</div>
<ul>{resumo}</ul>
<div class="nota"><b>Como ler este relatório.</b> Os números vêm da execução automática sobre o código final, em ambiente
isolado, com dados fictícios. O Mercado Pago foi simulado em todos os testes. O modelo de IA foi simulado nos fluxos de tela
e foi o Groq real na seção 3.</div>
<h2>1. Resultado por suíte</h2>
<table><tr><th>Suíte</th><th>O que verifica</th><th>Passaram</th></tr>{linhas_suite}</table>
<p>{e(dados['cobertura'])}</p>
<h2>2. Defeitos encontrados</h2>
<table><tr><th>Id</th><th>Sev.</th><th>Defeito</th><th>Como foi achado</th><th>Situação</th></tr>{defeitos}</table>
<h2 class="quebra">3. Conversas reais com o assistente</h2>
<p>Modelo real do Groq, com apostilas de teste. Cada resposta abaixo é a que o sistema devolveu nesta rodada.</p>
{falas}
<h2>4. O que não foi provado</h2><ul>{limites}</ul>
<h2 class="quebra">5. Fluxos de tela</h2>
<p>Cada fluxo foi executado em navegador real, preenchendo e clicando. Os prints são dessa execução.</p>
{corpo}
</body></html>"""

    temporario = pasta / "relatorio.html"
    temporario.write_text(documento, encoding="utf-8")
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page()
        pagina.goto(temporario.resolve().as_uri(), wait_until="load")
        pagina.pdf(path=str(saida), format="A4", print_background=True, prefer_css_page_size=True,
                   display_header_footer=True, header_template="<span></span>",
                   footer_template='<div style="font-size:8px;width:100%;text-align:center;color:#7b8794">'
                                   '<span class="pageNumber"></span> de <span class="totalPages"></span></div>')
        navegador.close()
    print(saida, round(saida.stat().st_size / 1e6, 1), "MB")


if __name__ == "__main__":
    main()
