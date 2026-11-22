"""DS1 (D115, docs/tdd/PLANO_DESIGN.md) — teste estático, sem navegador: nenhum `confirm()` do navegador no código Angular.

A DS1 troca as 8 chamadas de `confirm()` (aluno: pedir cancelamento, excluir conta; Gestão/Financeiro: ativar/desativar
conta da equipe, excluir turma, aprovar cancelamento, confirmar reembolso, arquivar/desarquivar curso, desativar/reativar
aluno) pela janela de confirmação do próprio app. O comportamento é o mesmo (confirmar executa, voltar não faz nada); o
que muda é só a janela.

S0 o próprio detector (amostras sintéticas; passa no red): acha `confirm(`, `window.confirm(`, `globalThis.confirm`,
   `window['confirm']` e ignora comentários, `confirmar(`, `onConfirm(` e `servico.confirm(` (método de outro objeto).
S1 nenhum arquivo `frontend/src/app/**/*.ts` chama o `confirm` global (lista arquivo:linha de todas as ocorrências).

Escolha do agente-testes: `objeto.confirm(...)` de um serviço do próprio app NÃO é apontado (não é o diálogo do
navegador); `window.confirm`, `globalThis.confirm`, `self.confirm`, `top.confirm`, `parent.confirm` e o `confirm(` solto
são. Comentários (// e /* */) não contam.

Execução (da raiz do repo): python3 -m pytest frontend/e2e/test_ds1_sem_confirm_nativo.py -q
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "frontend" / "src" / "app"

# `confirm(` solto (não precedido de identificador nem de ponto), ou o global por um dos nomes do objeto global.
_GLOBAL = r"(?:window|globalThis|self|top|parent)"
_PADROES = [
    re.compile(r"(?<![\w$.])confirm\s*\("),
    re.compile(rf"(?<![\w$.]){_GLOBAL}\s*\.\s*confirm\b"),
    re.compile(rf"(?<![\w$.]){_GLOBAL}\s*\[\s*['\"`]confirm['\"`]\s*\]"),
]


def _sem_comentarios(fonte):
    """Troca comentários por espaços (preserva as quebras de linha, para o número da linha continuar certo)."""
    def branco(m):
        return re.sub(r"[^\n]", " ", m.group(0))
    fonte = re.sub(r"/\*.*?\*/", branco, fonte, flags=re.S)
    # `//` de comentário; não o de uma URL dentro de string ("http://").
    return re.sub(r"(?<![:'\"`\\])//[^\n]*", branco, fonte)


def ocorrencias(fonte):
    """Lista (linha, trecho) de cada chamada ao confirm global no fonte TypeScript."""
    limpo = _sem_comentarios(fonte)
    achados = []
    for numero, linha in enumerate(limpo.splitlines(), start=1):
        if any(p.search(linha) for p in _PADROES):
            achados.append((numero, fonte.splitlines()[numero - 1].strip()[:140]))
    return achados


def test_ds1_s0_detector():
    apontar = [
        "if (!confirm('Excluir?')) { return; }",
        "if (!window.confirm(`Desativar ${x}?`)) return;",
        "const ok = globalThis.confirm(pergunta);",
        "const f = window['confirm']; f('x');",
        "return confirm (pergunta);",
        "if (!self.confirm('x')) {}",
    ]
    ignorar = [
        "// antes: if (!confirm('Excluir?')) return;",
        "/* window.confirm(pergunta) saiu na DS1 */",
        "this.confirmar(pergunta);",
        "onConfirm(evento: Event) {}",
        "this.confirmacao.confirm({ pergunta });",
        "const url = 'http://exemplo.test/confirmacao';  // confirm(x) só no comentário",
        "confirmacaoAberta = true;",
    ]
    erros = []
    for amostra in apontar:
        if not ocorrencias(amostra):
            erros.append(f"não apontou: {amostra!r}")
    for amostra in ignorar:
        if ocorrencias(amostra):
            erros.append(f"apontou indevidamente: {amostra!r}")
    multilinha = "a();\n/* bloco\nconfirm('x')\n*/\nif (!confirm('y')) {}\n"
    if [n for n, _ in ocorrencias(multilinha)] != [5]:
        erros.append(f"linha errada no bloco multilinha: {ocorrencias(multilinha)}")
    assert not erros, "; ".join(erros)


def test_ds1_s1_sem_confirm_nativo_no_angular():
    arquivos = sorted(APP.rglob("*.ts"))
    assert arquivos, f"nenhum .ts encontrado em {APP}"
    achados = []
    for arquivo in arquivos:
        for numero, trecho in ocorrencias(arquivo.read_text(encoding="utf-8")):
            achados.append(f"{arquivo.relative_to(REPO).as_posix()}:{numero}: {trecho}")
    print(f"\n{len(arquivos)} arquivos .ts verificados; {len(achados)} chamada(s) ao confirm() do navegador")
    for item in achados:
        print(f"  {item}")
    assert not achados, (f"{len(achados)} chamada(s) ao confirm() do navegador (DS1 troca pela janela do app): "
                         + " | ".join(achados))
