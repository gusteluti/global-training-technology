"""SG0 (D109) - higiene do repositorio e workflow de CI. Testes escritos antes do codigo (red).

Tres grupos:

(a) Workflow de CI `.github/workflows/ci.yml` (VERMELHO ate o dev criar o arquivo): um teste por exigencia, para
    o dev saber exatamente o que falta.
(b) Guarda de segredos (VERDE): nenhum arquivo rastreado pelo git casa com padrao de segredo real.
(c) Guarda de `.gitignore` e de arquivos rastreados (VERDE): `.env*`, `*.sqlite`, `backend/uploads/`,
    `.chrome-pdf-profile/` e `backups/` ficam fora do repositorio.

Regras destes testes:
- Nenhuma mensagem de falha imprime o valor encontrado (so arquivo, linha e nome do padrao): o log do CI de um
  repositorio publico nao pode virar um novo vazamento.
- Sem `git` no ambiente (ou fora de um repositorio git), os grupos (b) e (c) pulam com o motivo; (a) nao usa git.
- Os testes leem arquivos; nao chamam rede nem servico real.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

# backend/tests/test_sg0_higiene.py -> parents[0]=tests, [1]=backend, [2]=raiz do repositorio
RAIZ = Path(__file__).resolve().parents[2]
ESTE_ARQUIVO = Path(__file__).resolve()
WORKFLOW = RAIZ / ".github" / "workflows" / "ci.yml"


# ---------------------------------------------------------------------------------------------------------------
# (a) Workflow de CI
# ---------------------------------------------------------------------------------------------------------------

def _carregar_workflow():
    """Le e interpreta o ci.yml. Falha (nao pula) se o arquivo nao existir ou o YAML for invalido."""
    if not WORKFLOW.is_file():
        pytest.fail("SG0: falta .github/workflows/ci.yml (o workflow de CI ainda nao foi criado).")
    try:
        import yaml
    except ImportError:  # PyYAML nao esta em requirements.txt; sem ele o teste nao consegue validar o YAML
        pytest.fail(
            "SG0: PyYAML ausente no ambiente; os testes do workflow precisam dele (pip install pyyaml). "
            "Ele nao esta declarado em backend/requirements-dev.txt."
        )
    try:
        dados = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    except yaml.YAMLError as erro:
        pytest.fail(f"SG0: .github/workflows/ci.yml nao e um YAML valido ({type(erro).__name__}).")
    return dados


def _workflow():
    """Workflow carregado dentro do teste (e nao em fixture) para a falta do arquivo aparecer como FAILED, nao ERROR."""
    dados = _carregar_workflow()
    assert isinstance(dados, dict), "ci.yml deve ser um mapeamento YAML (name, on, permissions, jobs)."
    return dados


def _gatilhos(wf):
    """Conjunto de eventos do `on:`. PyYAML (YAML 1.1) le a chave `on` como o booleano True."""
    bruto = wf.get("on", wf.get(True))
    if bruto is None:
        return set()
    if isinstance(bruto, str):
        return {bruto}
    if isinstance(bruto, list):
        return {str(item) for item in bruto}
    if isinstance(bruto, dict):
        return {str(chave) for chave in bruto}
    return set()


def _passos(wf):
    """Todos os passos de todos os jobs, com o texto executavel (run, uses, with) e o diretorio de trabalho."""
    passos = []
    jobs = wf.get("jobs") or {}
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        defaults_job = ((job.get("defaults") or {}).get("run") or {}).get("working-directory") or ""
        for passo in job.get("steps") or []:
            if not isinstance(passo, dict):
                continue
            run = str(passo.get("run") or "")
            uses = str(passo.get("uses") or "")
            com = " ".join(str(v) for v in (passo.get("with") or {}).values())
            diretorio = str(passo.get("working-directory") or defaults_job)
            passos.append({
                "run": run,
                "uses": uses,
                "diretorio": diretorio,
                "texto": " ".join([run, uses, com, diretorio]),
            })
    return passos


def _achar_passo(wf, predicado):
    return [p for p in _passos(wf) if predicado(p)]


def _chaves_recursivas(obj):
    if isinstance(obj, dict):
        for chave, valor in obj.items():
            yield chave
            yield from _chaves_recursivas(valor)
    elif isinstance(obj, list):
        for item in obj:
            yield from _chaves_recursivas(item)


def _texto_estruturado(wf):
    """Texto de todos os valores e chaves do YAML ja interpretado (comentarios nao entram)."""
    import yaml
    return yaml.safe_dump(wf, allow_unicode=True)


def test_workflow_existe():
    assert WORKFLOW.is_file(), "SG0: falta .github/workflows/ci.yml (o workflow de CI ainda nao foi criado)."


def test_workflow_e_yaml_valido_com_jobs():
    workflow = _workflow()
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict) and jobs, "ci.yml precisa declarar ao menos um job em `jobs:`."
    assert _passos(workflow), "ci.yml precisa ter passos (`steps:`) em algum job."


def test_workflow_dispara_em_pull_request():
    workflow = _workflow()
    assert "pull_request" in _gatilhos(workflow), "`on:` deve incluir pull_request."


def test_workflow_dispara_em_push():
    workflow = _workflow()
    assert "push" in _gatilhos(workflow), "`on:` deve incluir push."


def test_workflow_permissions_contents_read_no_topo():
    workflow = _workflow()
    permissoes = workflow.get("permissions")
    assert isinstance(permissoes, dict), "Declare `permissions:` no topo do workflow (nao so dentro de jobs)."
    assert permissoes.get("contents") == "read", "O topo deve ter `permissions: contents: read`."
    escritas = {k: v for k, v in permissoes.items() if str(v).lower() == "write"}
    assert not escritas, f"O topo nao pode conceder escrita: {sorted(escritas)}."


def test_workflow_executa_pytest_do_backend():
    workflow = _workflow()
    def roda_pytest(passo):
        return re.search(r"python3?\s+-m\s+pytest\b", passo["run"]) is not None

    candidatos = _achar_passo(workflow, roda_pytest)
    assert candidatos, "Falta um passo `run:` com `python -m pytest`."
    assert any(
        re.search(r"(^|[/\\\s])backend\b", c["diretorio"] + " " + c["run"]) for c in candidatos
    ), "O pytest deve rodar no backend (working-directory: backend ou `cd backend`)."


def test_workflow_executa_pip_audit_sobre_requirements_do_backend():
    workflow = _workflow()
    def roda_pip_audit(passo):
        return re.search(r"\bpip-audit\b", passo["run"]) is not None

    candidatos = _achar_passo(workflow, roda_pip_audit)
    assert candidatos, "Falta um passo `run:` com `pip-audit`."
    assert any(
        "requirements.txt" in c["run"] and re.search(r"\bbackend\b", c["diretorio"] + " " + c["run"])
        for c in candidatos
    ), "O pip-audit deve apontar para backend/requirements.txt (`-r backend/requirements.txt` ou working-directory: backend)."


def test_workflow_executa_npm_audit_omit_dev_no_frontend():
    workflow = _workflow()
    def roda_npm_audit(passo):
        return re.search(r"\bnpm\s+audit\b", passo["run"]) is not None

    candidatos = _achar_passo(workflow, roda_npm_audit)
    assert candidatos, "Falta um passo `run:` com `npm audit`."
    assert any(re.search(r"--omit[=\s]+dev\b", c["run"]) for c in candidatos), "O npm audit deve usar `--omit=dev`."
    assert any(
        "--omit" in c["run"] and re.search(r"\bfrontend\b", c["diretorio"] + " " + c["run"]) for c in candidatos
    ), "O npm audit deve rodar em `frontend` (working-directory: frontend, `cd frontend` ou `--prefix frontend`)."


def test_workflow_executa_gitleaks():
    workflow = _workflow()
    candidatos = _achar_passo(workflow, lambda p: re.search(r"gitleaks", p["run"] + " " + p["uses"], re.I))
    assert candidatos, "Falta um passo com gitleaks."


def test_workflow_gitleaks_restrito_ao_diff_do_pr_e_nao_ao_historico():
    """Exige a faixa explicita de commits (`--log-opts "<base>..<head>"`), verificavel sem rodar o CI.

    O gitleaks sem `--log-opts` varre o historico inteiro do repositorio, que tem segredos antigos e aceitos
    (D109: historico nao e reescrito). Toda invocacao do CLI precisa estar restrita a uma faixa `A..B`.
    """
    workflow = _workflow()
    invocacoes = []
    for passo in _passos(workflow):
        for linha in passo["run"].splitlines():
            if re.search(r"\bgitleaks\b", linha) and not linha.lstrip().startswith("#"):
                invocacoes.append(linha)
    assert invocacoes, "Falta uma invocacao do CLI `gitleaks` em um passo `run:`."
    sem_faixa = [
        linha for linha in invocacoes
        if not re.search(r"--log-opts[=\s]+[\"']?.*\.\.", linha)
    ]
    assert not sem_faixa, (
        "Toda chamada ao gitleaks deve ser restrita ao diff do PR com `--log-opts \"<base>..<head>\"` "
        "(ex.: base e head do pull_request); sem isso ele varre o historico inteiro. "
        f"Chamadas sem faixa: {len(sem_faixa)}."
    )


def test_workflow_nao_usa_secrets():
    workflow = _workflow()
    texto = _texto_estruturado(workflow)
    assert not re.search(r"\bsecrets\s*\.", texto), "Nenhum passo pode usar `secrets.` (PR de fork nao recebe segredo)."
    assert "secrets" not in set(map(str, _chaves_recursivas(workflow))), (
        "Nenhum job pode declarar `secrets:` (inclui `secrets: inherit`)."
    )


def test_workflow_nao_usa_pull_request_target():
    workflow = _workflow()
    texto = _texto_estruturado(workflow)
    assert "pull_request_target" not in texto, (
        "`pull_request_target` roda com permissoes do repositorio base; o CI deve usar so `pull_request`."
    )


# ---------------------------------------------------------------------------------------------------------------
# Infra comum a (b) e (c): git
# ---------------------------------------------------------------------------------------------------------------

def _git(*args, input_bytes=None):
    return subprocess.run(
        ["git", "-C", str(RAIZ), *args], capture_output=True, input=input_bytes, timeout=120
    )


@pytest.fixture(scope="module")
def arquivos_rastreados():
    if shutil.which("git") is None:
        pytest.skip("git nao esta disponivel no ambiente de teste")
    resultado = _git("ls-files", "-z")
    if resultado.returncode != 0:
        pytest.skip("a raiz do repositorio nao e um repositorio git (git ls-files falhou)")
    nomes = [n for n in resultado.stdout.decode("utf-8", errors="surrogateescape").split("\0") if n]
    return nomes


@pytest.fixture(scope="module")
def git_disponivel():
    if shutil.which("git") is None:
        pytest.skip("git nao esta disponivel no ambiente de teste")
    if _git("rev-parse", "--git-dir").returncode != 0:
        pytest.skip("a raiz do repositorio nao e um repositorio git")


# ---------------------------------------------------------------------------------------------------------------
# (b) Guarda de segredos nos arquivos rastreados
# ---------------------------------------------------------------------------------------------------------------

# Padroes de segredo real. Os 6 primeiros sao os do plano SG0 (D109), sem alteracao.
PADROES_SEGREDO = {
    "github_token_classico": r"ghp_[A-Za-z0-9]{36}",
    "github_pat_fino": r"github_pat_[A-Za-z0-9_]{50,}",
    "mercado_pago_APP_USR": r"APP_USR-[0-9a-f-]{20,}",
    "groq_gsk": r"gsk_[A-Za-z0-9]{40,}",
    "google_api_key_AIza": r"AIza[0-9A-Za-z_-]{35}",
    "chave_privada_pem": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    # SMTP_PASSWORD com valor nao vazio. O valor precisa comecar por um caractere que possa ser senha: ficam de
    # fora aspas/espaco/fim de linha (valor vazio), `#` (comentario), `<` (placeholder), `$` (referencia a
    # variavel) e crase.
    # EXCECAO EXPLICITA E COMENTADA: a crase exclui a prosa de docs/tdd/PLANO_SG.md:101, onde o texto
    # "`SMTP_PASSWORD=` com valor" descreve este proprio padrao (falso positivo; ha 0 senha ali). Nao e
    # excecao por caminho: qualquer arquivo que escreva SMTP_PASSWORD=<senha> real continua sendo pego.
    "smtp_password_com_valor": r"SMTP_PASSWORD[ \t]*=[ \t]*[\"']?[^\s\"'`#<>$]",
}

# Unico arquivo onde SMTP_PASSWORD= pode aparecer (so como comentario/modelo, sem valor real).
ARQUIVOS_COM_SMTP_PERMITIDO = {".env.example"}
PADRAO_SO_FORA_DO_EXEMPLO = {"smtp_password_com_valor"}


def _eh_binario(dados: bytes) -> bool:
    return b"\0" in dados[:8192]


def _varrer(arquivos):
    """Devolve [(nome_padrao, caminho_relativo, linha)] sem jamais carregar o valor encontrado."""
    compilados = {nome: re.compile(rx) for nome, rx in PADROES_SEGREDO.items()}
    achados = []
    for relativo in arquivos:
        caminho = RAIZ / relativo
        if caminho.resolve() == ESTE_ARQUIVO or not caminho.is_file() or caminho.is_symlink():
            continue
        try:
            dados = caminho.read_bytes()
        except OSError:
            continue
        if _eh_binario(dados):
            continue
        texto = dados.decode("latin-1")
        permite_smtp = relativo in ARQUIVOS_COM_SMTP_PERMITIDO
        for numero, linha in enumerate(texto.splitlines(), start=1):
            for nome, rx in compilados.items():
                if permite_smtp and nome in PADRAO_SO_FORA_DO_EXEMPLO:
                    continue
                if rx.search(linha):
                    achados.append((nome, relativo, numero))
    return achados


@pytest.fixture(scope="module")
def achados_de_segredo(arquivos_rastreados):
    return _varrer(arquivos_rastreados)


@pytest.mark.parametrize("nome", sorted(PADROES_SEGREDO))
def test_nenhum_arquivo_rastreado_casa_com_padrao_de_segredo(nome, achados_de_segredo):
    ocorrencias = [f"{arq}:{lin}" for (n, arq, lin) in achados_de_segredo if n == nome]
    assert not ocorrencias, (
        f"Padrao de segredo '{nome}' encontrado em arquivo rastreado: {ocorrencias[:20]}. "
        "Remova o valor do arquivo (e rotacione a credencial); nao afrouxe o padrao."
    )


def test_padroes_de_segredo_pegam_exemplos_e_ignoram_valores_vazios():
    """Auto-teste dos padroes: um padrao com erro de digitacao passaria 'verde' sem proteger nada.

    Os exemplos sao montados por concatenacao e nao parecem credencial real.
    """
    positivos = {
        "github_token_classico": "ghp_" + "a" * 36,
        "github_pat_fino": "github_pat_" + "B" * 50,
        "mercado_pago_APP_USR": "APP_USR-" + "0123456789abcdef-0123",
        "groq_gsk": "gsk_" + "c" * 40,
        "google_api_key_AIza": "AIza" + "d" * 35,
        "chave_privada_pem": "-----BEGIN " + "RSA PRIVATE KEY-----",
        "smtp_password_com_valor": "SMTP_PASSWORD=" + "abc123",
    }
    assert set(positivos) == set(PADROES_SEGREDO)
    for nome, amostra in positivos.items():
        assert re.search(PADROES_SEGREDO[nome], amostra), f"o padrao '{nome}' nao reconhece um exemplo valido"

    rx_smtp = re.compile(PADROES_SEGREDO["smtp_password_com_valor"])
    for sem_valor in (
        "SMTP_PASSWORD=",
        "SMTP_PASSWORD=   ",
        'SMTP_PASSWORD=""',
        "SMTP_PASSWORD=`",
        "SMTP_PASSWORD=<senha>",
        "SMTP_PASSWORD=${SMTP_PASSWORD}",
        "SMTP_PASSWORD=# preencher",
    ):
        assert not rx_smtp.search(sem_valor), f"valor vazio/placeholder nao deve casar: {sem_valor!r}"
    assert rx_smtp.search('SMTP_PASSWORD="abc123"')
    assert rx_smtp.search("SMTP_PASSWORD = abc123")


def test_varredura_ignora_binarios_e_o_proprio_arquivo(tmp_path):
    """A varredura nao deve olhar binarios (mp3, pdf, pptx) nem este arquivo de teste."""
    assert _eh_binario(b"ID3\x00\x03\x00binario")
    assert not _eh_binario("texto comum, com acentuação".encode("utf-8"))
    assert ESTE_ARQUIVO.name == "test_sg0_higiene.py"


# ---------------------------------------------------------------------------------------------------------------
# (c) .gitignore e arquivos rastreados
# ---------------------------------------------------------------------------------------------------------------

CAMINHOS_QUE_DEVEM_SER_IGNORADOS = {
    ".env": ".env",
    ".env.* (local)": ".env.local",
    ".env.* (production)": ".env.production",
    "backend/.env": "backend/.env",
    "*.sqlite": "backend/db.sqlite",
    "*.sqlite (raiz)": "outro.sqlite",
    "backend/uploads/": "backend/uploads/curso/material.pdf",
    ".chrome-pdf-profile/": ".chrome-pdf-profile/Default/Cookies",
    "backups/": "backups/dump.db",
    "backend/backups/": "backend/backups/dump.db",
}


def _ignorado(caminho: str) -> bool:
    # --no-index: avalia so as regras do .gitignore, sem o arquivo estar (ou deixar de estar) rastreado.
    return _git("check-ignore", "-q", "--no-index", "--", caminho).returncode == 0


@pytest.mark.parametrize("rotulo,caminho", sorted(CAMINHOS_QUE_DEVEM_SER_IGNORADOS.items()))
def test_gitignore_cobre(rotulo, caminho, git_disponivel):
    assert _ignorado(caminho), f".gitignore deve cobrir {rotulo} (exemplo: {caminho})."


def test_gitignore_nao_ignora_env_example(git_disponivel):
    assert not _ignorado(".env.example"), "`.env.example` precisa ser versionado: falta `!.env.example` no .gitignore."


def test_git_nao_rastreia_env_so_o_exemplo(arquivos_rastreados):
    indevidos = [
        n for n in arquivos_rastreados
        if (Path(n).name == ".env" or Path(n).name.startswith(".env.")) and Path(n).name != ".env.example"
    ]
    assert not indevidos, f"Arquivo .env rastreado pelo git (so .env.example pode ser): {indevidos}"
    assert ".env.example" in arquivos_rastreados, "`.env.example` deve continuar rastreado (modelo de variaveis)."


def test_git_nao_rastreia_sqlite(arquivos_rastreados):
    indevidos = [n for n in arquivos_rastreados if n.lower().endswith((".sqlite", ".sqlite3"))]
    assert not indevidos, f"Banco SQLite rastreado pelo git: {indevidos}"


def test_git_nao_rastreia_uploads_de_cursos(arquivos_rastreados):
    indevidos = [n for n in arquivos_rastreados if n.replace("\\", "/").startswith("backend/uploads/")]
    assert not indevidos, f"Arquivo sob backend/uploads/ rastreado pelo git: {indevidos[:20]}"


def test_git_nao_rastreia_perfil_do_navegador(arquivos_rastreados):
    indevidos = [n for n in arquivos_rastreados if ".chrome-pdf-profile" in Path(n).parts]
    assert not indevidos, f"Perfil de navegador (.chrome-pdf-profile/) rastreado pelo git: {indevidos[:20]}"
