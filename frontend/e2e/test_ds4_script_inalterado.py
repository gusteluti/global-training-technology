"""Guarda estática da DS4 (D115, D-F): a landing é redesenhada SEM mudar o comportamento do script inline.

Regra (D115, PLANO_DESIGN "Decisões resolvidas" D-D e D-F): só design e conteúdo de vitrine. O script inline continua
com as mesmas funções, chamadas `fetch`, ids, `data-testid`, `onclick` e fluxo do chat, da matrícula e do login. O dev
pode mudar só classes e marcação DENTRO das strings de template (entre crases) que montam o cartão e a planilha.

Referência: a landing na `main` em `3d94f6c` (já com a DS4, lida com `git show`). Fora das templates do cartão e da
planilha, o script de `3d94f6c` é o de `c6f3342` (antes da DS4): a troca de referência não afrouxa a regra.

MUDANÇA DECLARADA DA R3-1 (D? a numerar; autoridade 4.3, encadeamento D115 D-F -> D120 -> R3-1): por decisão do PM o script
da landing muda para (1) resolver o endereço da API (`BACKEND_URL`, meta `gtt-api-url`) e (2) distinguir os erros do chat.
O verificador aceita EXATAMENTE essa mudança, e só ela: em `REGIOES_DECLARADAS` ficam quatro trechos entre âncoras de
texto; o miolo de cada trecho pode mudar, e todo o resto do script continua idêntico (S1). As âncoras também têm de ficar.
  1. `let chatOpen = false;` ... `const APP_URL = (function () {`  -> o resolvedor do endereço da API e suas constantes;
  2. fim de `saveChatSessionId` ... `async function sendMsg() {`    -> constantes e funções auxiliares dos erros do chat;
  3. `const sessionId = getChatSessionId();` ... `if (data && typeof data.session_id === 'string' && data.session_id)
     saveChatSessionId(data.session_id);`                           -> a chamada do POST e a leitura do JSON;
  4. `setChatStatus('Online agora');` ... `function quickReply(text) {` -> o tratamento dos erros.
O bloco de sucesso (do `if (data && typeof data.session_id ...` até `setChatStatus('Online agora');`) e o resto do script
não mudam. Complementos: o número de `fetch(` e de outras formas de rede no script não pode crescer.
RE-BASE (obrigatório quando a R3-1 for mergeada na `main`): trocar `REFERENCIA` pelo merge da R3-1 e esvaziar
`REGIOES_DECLARADAS`; sem isso a exceção ficaria aberta para as próximas entregas.

Cenários (sem servidor nem navegador):
  S0 (e S0b, sobre o script real da referência) o verificador funciona: mudar o código fora das crases é detectado; mudar só espaços, ou só o texto de dentro de
     uma template, é tolerado; crase dentro de comentário, de string e de regex não confunde o leitor        [passa no red]
  S0c a exceção da R3-1 é estreita (sobre o script real da referência): a mudança declarada é aceita; qualquer outra
     mudança fora das quatro regiões, fetch novo ou âncora que sumiu é detectada                              [passa no red]
  S1 o conteúdo do único <script> inline, sem as strings de template, é idêntico ao da referência (tolerando só espaços
     em branco); a página continua com exatamente um <script> e nenhum <script src>. Complemento do agente-testes:
     como as URLs do `fetch` e o destino do login também estão em templates (`${BACKEND_URL}/api/chat`,
     `${APP_URL}/login?area=...`), as templates que NÃO são o cartão, a linha da planilha ou o total da planilha
     também têm de ficar idênticas (comparadas na ordem, sem espaços)
  S2 atributos de evento (on*) da marcação estática: o conjunto de valores é o mesmo da referência (pode repetir um
     valor que já existia, ex.: outro botão com `toggleChat()`; não pode sumir nem aparecer handler novo)
  S3 dentro das templates: todo `onclick`, `id`, `data-testid` e `data-curso` da referência continua presente, igual,
     e nenhum atributo de evento novo aparece
  S4 ids e `data-testid` que o script usa continuam na marcação estática (courses-grid, planilha-linhas, chat-*, ...),
     e o `<meta name="gtt-app-url">` continua lá
  S5 nenhum número nem link de WhatsApp na marcação estática (o atendimento humano só vem das `actions` do servidor)

Escolha do agente-testes: comentários do script contam como código (a regra é "tolerando só espaços"); se o dev mexer
num comentário fora das regiões declaradas, S1 aponta. Isso é deliberado: o script só muda onde o PM autorizou (D-F, R3-1).

Execução (da raiz do repo): python3 -m pytest frontend/e2e/test_ds4_script_inalterado.py -q
"""

import re
import subprocess
from pathlib import Path

import pytest

E2E_DIR = Path(__file__).resolve().parent
REPO = E2E_DIR.parent.parent
LANDING = REPO / "frontend" / "landing_global_training.html"
REFERENCIA = "3d94f6c"  # main depois da DS4 (R3-1: antes era c6f3342; o script é o mesmo fora das templates do cartão)
CAMINHO_GIT = "frontend/landing_global_training.html"

# Ids e data-testid que o script lê com getElementById/querySelector (c6f3342).
IDS_DO_SCRIPT = ("courses-grid", "planilha-linhas", "planilha-num-total", "chat-bubble", "chat-btn", "chat-input",
                 "chat-messages", "quick-replies")
TESTIDS_DO_SCRIPT = ("hero-planilha-total", "hero-planilha-cursor")


# ------------------------------------------------------------------------------------------- leitor de JavaScript
class ErroLeitura(Exception):
    pass


_ANTES_DE_REGEX = set("(,=:[!&|?{};+-*%<>~^")
_PALAVRAS_ANTES_DE_REGEX = {"return", "typeof", "case", "do", "else", "in", "of", "void", "delete", "new", "throw"}


def _sem_templates(js):
    """Troca cada template literal (com as expressões ${...} de dentro) por `TPL` e devolve (código, templates).

    Reconhece strings '...' e "...", comentários // e /* */, regex literais (heurística pelo token anterior) e templates
    aninhadas em ${...}. Comentários e strings ficam no código (contam como código)."""
    saida, templates = [], []
    i, n = 0, len(js)

    def anterior_significativo():
        texto = "".join(saida).rstrip()
        if not texto:
            return "", ""
        m = re.search(r"([A-Za-z_$][\w$]*)$", texto)
        return texto[-1], (m.group(1) if m else "")

    def ler_string(j, aspas):
        k = j + 1
        while k < n:
            c = js[k]
            if c == "\\":
                k += 2
                continue
            if c == aspas:
                return k + 1
            if c == "\n":
                raise ErroLeitura(f"string sem fechamento perto de {js[j:j + 40]!r}")
            k += 1
        raise ErroLeitura("string sem fechamento no fim do script")

    def ler_regex(j):
        k, classe = j + 1, False
        while k < n:
            c = js[k]
            if c == "\\":
                k += 2
                continue
            if c == "\n":
                raise ErroLeitura(f"regex sem fechamento perto de {js[j:j + 40]!r}")
            if classe:
                if c == "]":
                    classe = False
            elif c == "[":
                classe = True
            elif c == "/":
                k += 1
                while k < n and (js[k].isalnum() or js[k] == "_"):
                    k += 1
                return k
            k += 1
        raise ErroLeitura("regex sem fechamento no fim do script")

    def ler_template(j):
        """j aponta para a crase de abertura; devolve o índice depois da crase de fechamento."""
        k = j + 1
        while k < n:
            c = js[k]
            if c == "\\":
                k += 2
                continue
            if c == "`":
                return k + 1
            if c == "$" and k + 1 < n and js[k + 1] == "{":
                k = ler_expressao(k + 2)
                continue
            k += 1
        raise ErroLeitura("template sem fechamento no fim do script")

    def ler_expressao(j):
        """Dentro de ${...}: lê código até a chave que fecha; devolve o índice depois dela."""
        k, nivel = j, 0
        while k < n:
            c = js[k]
            if c in "'\"":
                k = ler_string(k, c)
                continue
            if c == "`":
                k = ler_template(k)
                continue
            if c == "{":
                nivel += 1
            elif c == "}":
                if nivel == 0:
                    return k + 1
                nivel -= 1
            k += 1
        raise ErroLeitura("expressão ${ sem fechamento")

    while i < n:
        c = js[i]
        if c in "'\"":
            fim = ler_string(i, c)
            saida.append(js[i:fim])
            i = fim
        elif c == "`":
            fim = ler_template(i)
            templates.append(js[i:fim])
            saida.append("`TPL`")
            i = fim
        elif js.startswith("//", i):
            fim = js.find("\n", i)
            fim = n if fim < 0 else fim
            saida.append(js[i:fim])
            i = fim
        elif js.startswith("/*", i):
            fim = js.find("*/", i + 2)
            if fim < 0:
                raise ErroLeitura("comentário /* sem fechamento")
            saida.append(js[i:fim + 2])
            i = fim + 2
        elif c == "/":
            ultimo, palavra = anterior_significativo()
            if ultimo == "" or ultimo in _ANTES_DE_REGEX or palavra in _PALAVRAS_ANTES_DE_REGEX:
                fim = ler_regex(i)
                saida.append(js[i:fim])
                i = fim
            else:
                saida.append(c)
                i += 1
        else:
            saida.append(c)
            i += 1
    return "".join(saida), templates


def _normalizar(codigo):
    return re.sub(r"\s+", "", codigo)


def _template_do_cartao_ou_planilha(template):
    """As três templates de c6f3342 que o dev pode remarcar: o cartão (renderCourses), a linha da planilha e o total
    da planilha (renderPlanilha)."""
    return ('class="course-card"' in template or 'data-testid="hero-planilha-linha"' in template
            or template.startswith("`<strong>${total}</strong>"))


_RE_SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.S | re.I)


def _scripts(html):
    return [(m.group(1), m.group(2)) for m in _RE_SCRIPT.finditer(html)]


def _script_inline(html):
    inline = [corpo for atributos, corpo in _scripts(html) if "src=" not in atributos.lower()]
    if len(inline) != 1:
        raise AssertionError(f"{len(inline)} <script> inline na landing (esperado 1)")
    return inline[0]


def _marcacao_estatica(html):
    """O HTML sem os <script> e sem o <style> (só a marcação)."""
    sem = _RE_SCRIPT.sub("", html)
    return re.sub(r"<style\b.*?</style\s*>", "", sem, flags=re.S | re.I)


_RE_EVENTO = re.compile(r"""\s(on[a-z]+)\s*=\s*("([^"]*)"|'([^']*)')""", re.I)


def _handlers(marcacao):
    return [(m.group(1).lower(), m.group(3) if m.group(3) is not None else m.group(4))
            for m in _RE_EVENTO.finditer(marcacao)]


def _atributos(texto, nomes):
    achados = []
    for nome in nomes:
        for m in re.finditer(rf"""\s{nome}\s*=\s*"([^"]*)\"""", texto):
            achados.append((nome, m.group(1)))
    return achados


@pytest.fixture(scope="module")
def versoes():
    try:
        antiga = subprocess.run(["git", "show", f"{REFERENCIA}:{CAMINHO_GIT}"], cwd=str(REPO), capture_output=True,
                                check=True).stdout.decode("utf-8")
    except (subprocess.CalledProcessError, FileNotFoundError) as erro:
        pytest.fail(f"não foi possível ler a landing de {REFERENCIA} com git show: {erro}")
    atual = LANDING.read_text(encoding="utf-8")
    return antiga, atual


# ---------------------------------------------------------------------------------------------------- cenários
def test_s0_o_verificador_detecta_mudanca_fora_das_crases_e_tolera_dentro():
    base = ("const a = `x ${f(`y`)} z`; // comentário com `crase`\n"
            "const r = s.replace(/`([^`]+)`/g, '<code>$1</code>');\n"
            "const t = 'aspas com ` crase'; fetch(`${URL}/api/chat`, { method: 'POST' });\n")
    codigo, templates = _sem_templates(base)
    assert len(templates) == 2, templates
    assert "// comentário com `crase`" in codigo and "/`([^`]+)`/g" in codigo and "'aspas com ` crase'" in codigo
    so_espacos = base.replace("; ", ";\n    ").replace("{ method", "{\n method")
    assert _normalizar(_sem_templates(so_espacos)[0]) == _normalizar(codigo)
    dentro = base.replace("`x ${f(`y`)} z`", "`<div class=\"novo\">${f(`y`)} ${g(c.level)}</div>`")
    assert _normalizar(_sem_templates(dentro)[0]) == _normalizar(codigo)
    fora = base.replace("method: 'POST'", "method: 'GET'")
    assert _normalizar(_sem_templates(fora)[0]) != _normalizar(codigo)
    nova_funcao = base + "function filtrar() { return 1; }\n"
    assert _normalizar(_sem_templates(nova_funcao)[0]) != _normalizar(codigo)


def _diferencas_do_script(script_antigo, script_novo):
    """Lista (vazia = igual) do que mudou no script inline fora do que o dev pode remarcar."""
    velho, t_velhas = _sem_templates(script_antigo)
    novo, t_novas = _sem_templates(script_novo)
    a, b = _normalizar(velho), _normalizar(novo)
    if a != b:
        i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
        return [f"o script inline mudou fora das strings de template (primeira diferença no caractere {i}, sem "
                f"espaços): antes {a[max(0, i - 60):i + 60]!r} / agora {b[max(0, i - 60):i + 60]!r}"]
    # Com o código de fora idêntico, as templates aparecem na mesma ordem. Só as do cartão e da planilha podem mudar;
    # as outras (URLs do fetch, destino do login, classes do chat, texto do chatAbout) continuam iguais.
    if len(t_velhas) != len(t_novas):
        return [f"{len(t_novas)} templates no script (eram {len(t_velhas)})"]
    return [f"template fora do cartão e da planilha mudou: {_normalizar(v)[:70]!r} -> {_normalizar(n)[:70]!r}"
            for v, n in zip(t_velhas, t_novas)
            if not _template_do_cartao_ou_planilha(v) and _normalizar(v) != _normalizar(n)]


# ---------------------------------------------------------------------- exceção declarada da R3-1 (ver o docstring)
# (rótulo, âncora de início, âncora de fim). O texto ENTRE as âncoras pode mudar; as âncoras, não. As âncoras são
# procuradas em sequência (a primeira ocorrência depois do trecho anterior) e comparadas sem diferença de espaços.
REGIOES_DECLARADAS = (
    ("endereço da API (BACKEND_URL)", "let chatOpen = false;", "const APP_URL = (function () {"),
    ("auxiliares dos erros do chat",
     "function saveChatSessionId(id) { try { sessionStorage.setItem(CHAT_SESSION_KEY, id); } "
     "catch (e) { /* sem sessionStorage: segue sem guardar */ } }",
     "async function sendMsg() {"),
    ("POST do chat e leitura do JSON", "const sessionId = getChatSessionId();",
     "if (data && typeof data.session_id === 'string' && data.session_id) saveChatSessionId(data.session_id);"),
    ("tratamento dos erros do chat", "setChatStatus('Online agora');", "function quickReply(text) {"),
)
# A mudança não pode criar caminho de rede novo: estas formas têm de aparecer o mesmo número de vezes que na referência.
FORMAS_DE_REDE = (r"\bfetch\s*\(", r"\bXMLHttpRequest\b", r"\bsendBeacon\b", r"\bWebSocket\b", r"\bEventSource\b",
                  r"\beval\s*\(", r"\bnew\s+Function\b", r"\bimportScripts\b")


def _padrao_ancora(texto):
    return r"\s*".join(re.escape(parte) for parte in texto.split())


def _recortar_regioes(script, regioes=REGIOES_DECLARADAS):
    """Tira o miolo de cada região declarada (entre as âncoras, que ficam). ErroLeitura se uma âncora não existir, na ordem."""
    partes, cursor = [], 0
    for rotulo, inicio, fim in regioes:
        a = re.search(_padrao_ancora(inicio), script[cursor:])
        if not a:
            raise ErroLeitura(f"âncora de início da região '{rotulo}' não encontrada: {inicio[:60]!r}")
        fim_do_inicio = cursor + a.end()
        b = re.search(_padrao_ancora(fim), script[fim_do_inicio:])
        if not b:
            raise ErroLeitura(f"âncora de fim da região '{rotulo}' não encontrada depois do início: {fim[:60]!r}")
        partes.append(script[cursor:fim_do_inicio])
        cursor = fim_do_inicio + b.start()
    partes.append(script[cursor:])
    return "".join(partes)


def _diferencas_com_excecao(script_antigo, script_novo, regioes=REGIOES_DECLARADAS):
    """Como `_diferencas_do_script`, mas aceitando a mudança declarada: só o miolo das regiões pode mudar."""
    try:
        velho, novo = _recortar_regioes(script_antigo, regioes), _recortar_regioes(script_novo, regioes)
    except ErroLeitura as erro:
        return [str(erro)]
    problemas = _diferencas_do_script(velho, novo)
    for forma in FORMAS_DE_REDE:
        antes, agora = len(re.findall(forma, script_antigo)), len(re.findall(forma, script_novo))
        if agora != antes:
            problemas.append(f"a mudança declarada não pode criar caminho de rede novo: {forma!r} aparece {agora} vez(es), "
                             f"eram {antes}")
    return problemas


def test_s0b_o_verificador_no_script_real(versoes):
    antiga, _ = versoes
    script = _script_inline(antiga)
    assert _diferencas_do_script(script, script) == []
    remarcado = script.replace('<article class="course-card"', '<article class="course-card cartao-novo"') \
                      .replace('<div class="course-type">', '<p class="course-type">')
    assert remarcado != script and _diferencas_do_script(script, remarcado) == []
    for antes, depois in (("`${BACKEND_URL}/api/chat`", "`${BACKEND_URL}/api/chat2`"),
                          ("`${APP_URL}/login?area=funcionario`", "`${APP_URL}/login?area=equipe`"),
                          ("\nloadCoursesFromBackend();", "\nloadCoursesFromBackend();\nfiltrar();"),
                          ("if (chatOpen) document.getElementById('chat-input').focus();", "")):
        alterado = script.replace(antes, depois)
        assert alterado != script, f"pré-condição: trecho {antes!r} não encontrado no script de {REFERENCIA}"
        assert _diferencas_do_script(script, alterado), f"mudança não detectada: {antes!r} -> {depois!r}"


def _aplicar_a_mudanca_da_r3_1(script):
    """O que o dev faz na R3-1, simulado sobre o script da referência (só dentro das quatro regiões)."""
    novo = script.replace("const BACKEND_URL = 'http://localhost:8000';", """// R3-1
const BACKEND_URL = (function () {
  const meta = document.querySelector('meta[name="gtt-api-url"]');
  const configurada = meta && meta.content.trim();
  if (configurada) return configurada.replace(/\\/+$/, '');
  const local = window.location.protocol === 'file:' || ['localhost', '127.0.0.1', ''].includes(window.location.hostname);
  return local ? 'http://localhost:8000' : window.location.origin;
})();""", 1)
    assert novo != script, f"pré-condição: BACKEND_URL não encontrado no script de {REFERENCIA}"
    ancora = "async function sendMsg() {"
    assert ancora in novo
    novo = novo.replace(ancora, """const MSG_REDE = 'Não consegui falar com o servidor.';
function mostrarErroDoChat(texto) { addMsg(texto, 'bot'); setChatStatus('Offline'); }
""" + ancora, 1)
    inicio = novo.index("const sessionId = getChatSessionId();") + len("const sessionId = getChatSessionId();")
    fim = novo.index("if (data && typeof data.session_id === 'string' && data.session_id) saveChatSessionId(data.session_id);")
    novo = novo[:inicio] + """
  const urlChat = `${BACKEND_URL}/api/chat`;
  let response;
  try {
    response = await fetch(urlChat, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(sessionId ? { message: text, session_id: sessionId } : { message: text }) });
  } catch (erro) {
    mostrarErroDoChat(MSG_REDE);
    console.error(`sem resposta de ${urlChat} (CORS_ALLOWED_ORIGINS)`, erro);
    return;
  }
  const data = await response.json();
  try {
    """ + novo[fim:]
    inicio = novo.index("setChatStatus('Online agora');") + len("setChatStatus('Online agora');")
    fim = novo.index("function quickReply(text) {")
    return novo[:inicio] + "\n  } catch (erro) {\n    console.error(erro);\n  }\n}\n" + novo[fim:]


def test_s0c_a_excecao_da_r3_1_e_estreita(versoes):
    antiga, _ = versoes
    script = _script_inline(antiga)
    assert _diferencas_com_excecao(script, script) == []
    mudado = _aplicar_a_mudanca_da_r3_1(script)
    assert mudado != script
    assert _diferencas_com_excecao(script, mudado) == [], "a mudança declarada deveria ser aceita"
    assert _diferencas_do_script(script, mudado), "pré-condição: a regra estrita (S0b) continua vendo essa mudança"
    for rotulo, antes, depois in (
        ("linha do bloco de sucesso removida", "    if (data.status === 'success') addEnrollActions(data.actions);\n", ""),
        ("destino do login (APP_URL)", "return local ? 'http://localhost:4200' : window.location.origin;",
         "return local ? 'http://localhost:4300' : window.location.origin;"),
        ("URL do feedback", "`${BACKEND_URL}/api/chat/feedback`", "`${BACKEND_URL}/api/chat/feedback2`"),
        ("URL dos cursos", "`${BACKEND_URL}/api/courses`", "`${BACKEND_URL}/api/cursos`"),
        ("função nova fora das regiões", "\nloadCoursesFromBackend();", "\nfunction filtrar() {}\nloadCoursesFromBackend();"),
        ("texto do aviso de dados pessoais", "Para sua segurança, removemos dados pessoais", "Para sua segurança, removemos dados"),
        ("status 'Online agora' no bloco de sucesso", "    setChatStatus('Online agora');", "    setChatStatus('Online');"),
    ):
        alterado = mudado.replace(antes, depois, 1)
        assert alterado != mudado, f"pré-condição: trecho de {rotulo!r} não encontrado"
        assert _diferencas_com_excecao(script, alterado), f"mudança fora das regiões não detectada: {rotulo}"
    # caminho de rede novo, mesmo dentro de uma região declarada
    com_fetch = mudado.replace("mostrarErroDoChat(MSG_REDE);", "fetch('https://exemplo.invalido/x'); mostrarErroDoChat(MSG_REDE);", 1)
    assert com_fetch != mudado
    assert any("caminho de rede novo" in p for p in _diferencas_com_excecao(script, com_fetch))
    # âncora que sumiu: o verificador reprova em vez de aceitar tudo
    sem_ancora = mudado.replace("function quickReply(text) {", "function responderRapido(text) {", 1)
    assert any("âncora" in p for p in _diferencas_com_excecao(script, sem_ancora)), "âncora ausente não foi apontada"
    sem_ancora_inicio = mudado.replace("let chatOpen = false;", "let chatAberto = false;", 1)
    assert any("âncora" in p for p in _diferencas_com_excecao(script, sem_ancora_inicio))


def test_s1_script_inline_identico_fora_das_templates(versoes):
    antiga, atual = versoes
    tags = _scripts(atual)
    externos = [a.strip() for a, _ in tags if "src=" in a.lower()]
    assert not externos, f"a landing ganhou <script src> ({externos}); a landing não adiciona script externo"
    assert len(tags) == 1, f"{len(tags)} <script> na landing (esperado 1, como em {REFERENCIA})"
    problemas = _diferencas_com_excecao(_script_inline(antiga), _script_inline(atual))
    assert not problemas, " | ".join(problemas)


def test_s2_handlers_da_marcacao_estatica_sao_os_mesmos(versoes):
    antiga, atual = versoes
    velhos = set(_handlers(_marcacao_estatica(antiga)))
    novos = set(_handlers(_marcacao_estatica(atual)))
    sumiram, apareceram = sorted(velhos - novos), sorted(novos - velhos)
    assert not sumiram and not apareceram, (
        f"atributos de evento mudaram na marcação: sumiram {sumiram}; apareceram {apareceram}")


def test_s3_atributos_das_templates_preservados(versoes):
    antiga, atual = versoes
    _, t_velhas = _sem_templates(_script_inline(antiga))
    _, t_novas = _sem_templates(_script_inline(atual))
    velhas, novas = " ".join(t_velhas), " ".join(t_novas)
    faltam = [f'{nome}="{valor}"' for nome, valor in _atributos(velhas, ("onclick", "id", "data-testid", "data-curso"))
              if f'{nome}="{valor}"' not in novas]
    assert not faltam, f"atributos das templates do cartão/planilha sumiram ou mudaram: {faltam}"
    eventos_velhos = {m.group(0).strip() for m in _RE_EVENTO.finditer(velhas)}
    eventos_novos = {m.group(0).strip() for m in _RE_EVENTO.finditer(novas)}
    assert eventos_novos <= eventos_velhos, f"atributos de evento novos nas templates: {sorted(eventos_novos - eventos_velhos)}"


def test_s4_ids_e_testids_usados_pelo_script_continuam(versoes):
    _, atual = versoes
    marcacao = _marcacao_estatica(atual)
    ids = {v for _, v in _atributos(marcacao, ("id",))}
    testids = {v for _, v in _atributos(marcacao, ("data-testid",))}
    faltam = [f"id={i}" for i in IDS_DO_SCRIPT if i not in ids]
    faltam += [f"data-testid={t}" for t in TESTIDS_DO_SCRIPT if t not in testids]
    if not re.search(r"""<meta\s+name="gtt-app-url"\s+content="[^"]*"\s*/?>""", atual):
        faltam.append('<meta name="gtt-app-url">')
    if not re.search(r"""class="chat-header-info"[^>]*>.*?<span\b""", marcacao, re.S):
        faltam.append(".chat-header-info span (usado por setChatStatus)")
    assert not faltam, f"a marcação perdeu o que o script usa: {faltam}"


def test_s5_sem_numero_nem_link_de_whatsapp_na_marcacao(versoes):
    _, atual = versoes
    marcacao = _marcacao_estatica(atual)
    achados = re.findall(r"wa\.me|api\.whatsapp\.com|whatsapp\.com/send|href=\"tel:", marcacao, re.I)
    texto = re.sub(r"<[^>]+>", " ", marcacao)
    achados += re.findall(r"(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}", texto)
    assert not achados, f"número ou link de WhatsApp na landing: {achados[:4]}"
