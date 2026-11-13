"""D108 (pedido do PM, J-VIS-03 2N) — checar o link de senha sem consumi-lo.

Escritos ANTES da implementação. Hoje as telas /redefinir-senha e /definir-senha mostram o formulário para qualquer
token e só recusam no envio; o PM pediu o aviso de link inválido ou expirado logo ao abrir. Para isso o backend
precisa dizer se o token vale sem usá-lo.

Rota proposta (contrato novo; forma decidida aqui, ver relatório):
  POST /api/auth/password-token/check   corpo {"token": str}   (pública, como as outras rotas de senha)
    - token válido (existe, não usado, não expirado): 200 {"valid": true, "purpose": "reset" | "setup"}.
      Nada mais no corpo: nem e-mail, nem id da conta, nem validade.
    - inválido, expirado, já usado, substituído por um mais novo, vazio ou ausente: 200 {"valid": false}, exatamente
      esse corpo em todos os casos, sem e-mail nem dado da conta. Mudança de contrato do orquestrador (D108, depois do
      frontend 0811300): antes era 400; passou a 200 para a checagem ao abrir a tela não gerar erro de console no
      navegador (os e2e B1/B9, E2/C8 e L2/K1 contam erros de console).
    - limite por IP: 429 (core/rate_limit, 30 checagens por minuto); a resposta 200 {"valid": false} conta no limite.
    - A checagem NÃO consome o token: depois de checar (mais de uma vez), o token continua valendo na rota própria
      (/api/auth/password-reset para 'reset', /api/auth/password-setup para 'setup').
    - Campos extras (user_id, email) são ignorados; um bearer forjado não muda nada.
  POST em vez de GET: o token não vai para a query string (logs de acesso e de proxy).
  Limite de taxa: a implementação (77bbf09) pôs 30 checagens por minuto por IP com 429; T7 fixa que o 429 continua
  depois da troca do 400 pelo 200.

Fixtures e helpers: os da B1 (banco temporário, outbox em tmp_path, rotas HTTP reais).

Testes:
  T1  token 'reset' válido: 200 {"valid": true, "purpose": "reset"}, sem e-mail nem id
  T2  token 'setup' válido: 200 {"valid": true, "purpose": "setup"}
  T3  checar (duas vezes) não consome: o reset funciona depois e o token fica usado só então
  T4  checar não consome o 'setup': a definição de senha funciona depois
  T5  inexistente, expirado, usado, substituído, vazio e ausente: 200 {"valid": false} (o mesmo corpo), sem e-mail
  T6  campos extras e bearer forjado não mudam a resposta
  T7  limite: 30 checagens inválidas respondem 200 {"valid": false}; a 31ª responde 429, mesmo com token válido
"""

from datetime import timedelta

import pytest

from test_b1_recuperacao_senha import (  # noqa: F401  (fixtures da B1 reaproveitadas)
    SENHA_ANTIGA,
    SENHA_NOVA,
    _agora,
    _aluno,
    _aluno_sem_senha,
    _definir,
    _executar,
    _fmt,
    _inserir_token,
    _login,
    _novo_reset,
    _pedir,
    _redefinir,
    _tokens,
    _ultimo_token,
    client,
    curso_teste,
    outbox,
)
from core.password_setup import hash_token

URL_CHECAR = "/api/auth/password-token/check"
INVALIDO = {"valid": False}  # corpo exato para qualquer link que não vale (D108, contrato 200)
LIMITE_CHECAGENS = 30  # core/rate_limit.LIMITE_CHECAGEM_TOKEN_SENHA (por IP, janela de 1 minuto)


def _checar(client, token, **extra):
    return client.post(URL_CHECAR, json={"token": token, **extra})


def _valido(r, purpose):
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"
    corpo = r.json()
    assert {chave: corpo.get(chave) for chave in ("valid", "purpose")} == {"valid": True, "purpose": purpose}, corpo
    assert set(corpo) - {"status"} == {"valid", "purpose"}, f"campos a mais na checagem: {corpo}"
    return corpo


def _invalido(r, nome="caso"):
    assert r.status_code == 200, f"{nome}: HTTP {r.status_code} {r.text[:200]} (esperado 200 {INVALIDO})"
    assert r.json() == INVALIDO, f"{nome}: corpo {r.text[:200]} (esperado exatamente {INVALIDO})"
    return r.json()


def _registro(token):
    linhas = [t for t in _tokens() if t["token_hash"] == hash_token(token)]
    assert len(linhas) == 1
    return linhas[0]


def test_t1_token_de_redefinicao_valido(client, outbox):
    email = "t1@d108.test"
    user_id = _aluno(email)
    token = _novo_reset(client, outbox, email)
    r = _checar(client, token)
    _valido(r, "reset")
    assert email not in r.text and f'"{user_id}"' not in r.text and "user_id" not in r.text


def test_t2_token_de_definicao_valido(client, outbox):
    email = "t2@d108.test"
    _aluno_sem_senha(email)
    assert _pedir(client, email).status_code == 200
    token = _ultimo_token(outbox, email, "/definir-senha")
    r = _checar(client, token)
    _valido(r, "setup")
    assert email not in r.text


def test_t3_checar_nao_consome_o_token_de_redefinicao(client, outbox):
    email = "t3@d108.test"
    _aluno(email)
    token = _novo_reset(client, outbox, email)
    _valido(_checar(client, token), "reset")
    _valido(_checar(client, token), "reset")
    assert _registro(token)["used_at"] is None, "a checagem marcou o token como usado"
    assert _redefinir(client, token, SENHA_NOVA).status_code == 200
    assert _login(client, email, SENHA_NOVA).status_code == 200
    assert _registro(token)["used_at"] is not None


def test_t4_checar_nao_consome_o_token_de_definicao(client, outbox):
    email = "t4@d108.test"
    _aluno_sem_senha(email)
    _pedir(client, email)
    token = _ultimo_token(outbox, email, "/definir-senha")
    _valido(_checar(client, token), "setup")
    assert _definir(client, token, SENHA_NOVA).status_code == 200
    assert _login(client, email, SENHA_NOVA).status_code == 200


EMAILS_T5 = ("t5-expirado@d108.test", "t5-usado@d108.test", "t5-substituido@d108.test")


def _casos_invalidos(client, outbox):
    """Uma conta por caso: o limite de 3 tokens por conta por hora (D60) conta também o token inserido direto."""
    expira_conta, usa_conta, substitui_conta = (_aluno(email) for email in EMAILS_T5)
    expirado = _inserir_token(expira_conta, "reset", horas=1)
    _executar("UPDATE password_setup_tokens SET expires_at = ? WHERE token_hash = ?",
              (_fmt(_agora() - timedelta(minutes=5)), hash_token(expirado)))
    usado = _novo_reset(client, outbox, EMAILS_T5[1])
    assert _redefinir(client, usado, SENHA_NOVA).status_code == 200
    substituido = _novo_reset(client, outbox, EMAILS_T5[2])
    assert _novo_reset(client, outbox, EMAILS_T5[2]) != substituido  # o pedido novo invalida o anterior (D60)
    return {
        "inexistente": "token-que-nunca-existiu-d108",
        "expirado": expirado,
        "usado": usado,
        "substituido": substituido,
        "vazio": "",
    }


def test_t5_invalido_expirado_usado_substituido_vazio_e_ausente_tem_a_mesma_resposta(client, outbox):
    respostas = {nome: _checar(client, token) for nome, token in _casos_invalidos(client, outbox).items()}
    respostas["ausente"] = client.post(URL_CHECAR, json={})  # corpo sem o campo token
    for nome, r in respostas.items():
        _invalido(r, nome)
        for email in EMAILS_T5:
            assert email not in r.text, f"{nome}: a resposta revelou {email}"
    corpos = {nome: r.json() for nome, r in respostas.items()}
    assert len({repr(c) for c in corpos.values()}) == 1, f"corpos diferentes entre os casos inválidos: {corpos}"
    assert _login(client, EMAILS_T5[1], SENHA_NOVA).status_code == 200, "a checagem não muda a senha"
    assert _login(client, EMAILS_T5[2], SENHA_ANTIGA).status_code == 200


@pytest.mark.parametrize("extra", [{"user_id": 1}, {"email": "outra@d108.test"}], ids=["user_id", "email"])
def test_t6_campos_extras_e_bearer_forjado_nao_mudam_a_resposta(client, outbox, extra):
    email = "t6@d108.test"
    _aluno(email)
    token = _novo_reset(client, outbox, email)
    _valido(client.post(URL_CHECAR, json={"token": token, **extra},
                        headers={"Authorization": "Bearer forjado.d108.x"}), "reset")
    invalido = client.post(URL_CHECAR, json={"token": "token-falso-d108", **extra},
                           headers={"Authorization": "Bearer forjado.d108.x"})
    referencia = _checar(client, "outro-falso-d108")
    assert (invalido.status_code, invalido.json()) == (referencia.status_code, referencia.json())
    _invalido(invalido, "falso com extras")
    assert _login(client, email, SENHA_ANTIGA).status_code == 200


def test_t7_limite_conta_as_checagens_invalidas_e_responde_429(client, outbox):
    email = "t7@d108.test"
    _aluno(email)
    token = _novo_reset(client, outbox, email)
    for numero in range(1, LIMITE_CHECAGENS + 1):
        _invalido(_checar(client, f"token-falso-d108-{numero}"), f"checagem {numero}")
    barrada = _checar(client, token)
    assert barrada.status_code == 429, f"checagem {LIMITE_CHECAGENS + 1}: HTTP {barrada.status_code} {barrada.text[:200]}"
    assert barrada.json().get("valid") is not True and email not in barrada.text
    assert _registro(token)["used_at"] is None, "a checagem barrada consumiu o token"
