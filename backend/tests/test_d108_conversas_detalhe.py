"""D108 (pedido do PM, J-GES-02 passo 1 e J-SUP-01 passo 2) — conversas do chat no detalhe do aluno.

Escritos ANTES da implementação. Hoje GET /api/dashboard/alunos/{user_id} devolve só o resumo do chat
(`chat.messages`, `chat.last_chat_at`, F3/D73); o PM pediu que o detalhe do aluno no painel mostre as conversas
(quantidade, data da última e as mensagens recentes com quem falou), para Gestão e Suporte. As mensagens
recentes não estão na API: campo novo.

Contrato proposto (forma, decisão do orquestrador; o resumo da F3 não muda):
  - `chat.recent`: lista das mensagens mais recentes do aluno, no máximo 20 (`LIMITE_PROPOSTO`), em ordem
    cronológica crescente (a mesma de Database.list_chat_messages e do histórico do aluno). Cada item:
    {"role": "user" | "assistant", "content": <texto como gravado>, "created_at": <UTC como gravado>}.
  - O texto é o que já está gravado em chat_messages (mascarado na entrada pela GR3): nada é desmascarado.
  - Só mensagens do próprio aluno do detalhe (filtro por user_id no servidor).
  - Aluno sem conversa: `recent` = [] (compatibilidade com quem nunca usou o chat).
  - Todos os perfis internos veem as conversas. Suporte (D68) continua sem nenhum valor: nem `amount`, nem o valor
    do pagamento, nem "R$" em lugar nenhum do corpo, inclusive dentro do texto de uma resposta do assistente que
    tenha citado o pagamento do aluno (GR4). Escolha conservadora deste teste (ver relatório): o modo de esconder
    (mascarar o valor ou omitir a mensagem) fica com a implementação; Gestão e Financeiro veem o texto gravado.
  - RBAC inalterado: 401 sem token/forjado, 403 para aluno.

Fixtures, cenário e helpers: os da F3 (test_f3_aluno_curso.py): banco temporário, cursos temporários, JWT montado.
No cenário, Joana tem 2 trocas no chat (2 mensagens do aluno + 2 do assistente) e pagamentos VALOR_A e VALOR_B.

Testes:
  K1  Gestão, Financeiro e Suporte recebem `chat.recent` com as 4 mensagens da Joana, em ordem, com role/content
  K2  limite: com 30 trocas (60 mensagens), `recent` é o final do histórico (entre 10 e 20, terminando na última)
  K3  não mistura alunos: o detalhe da Rita (sem chat) tem `recent` = [] e nada da Joana
  K4  texto mascarado pela GR3 volta como gravado ([cartao]), sem o número
  K5  Suporte: resposta do assistente com o valor do pagamento não leva valor nem "R$" ao Suporte; Gestão vê o texto
  K6  resumo da F3 continua igual (messages / last_chat_at) e coerente com `recent`
  K7  RBAC: 401 sem token e com token forjado; 403 para aluno, sem transcrição no corpo
"""

import json

import pytest

from test_f3_aluno_curso import (  # noqa: F401  (fixtures da F3 reaproveitadas)
    VALOR_A,
    VALOR_B,
    _auth,
    _detalhe,
    _forjado,
    _ok,
    _sem_valores,
    catalogo,
    cenario,
    client,
    contas,
    cursos,
)
from db import Database

LIMITE_PROPOSTO = 20
PAPEIS = {"user", "assistant"}
CARTAO_MASCARADO = "Posso pagar com o cartão [cartao]?"


def _recent(corpo):
    chat = corpo.get("chat") or {}
    assert "recent" in chat, f"o detalhe do aluno não traz chat.recent: {json.dumps(chat)[:300]}"
    assert isinstance(chat["recent"], list), chat["recent"]
    return chat["recent"]


def _projetar(mensagens):
    return [(m["role"], m["content"], m["created_at"]) for m in mensagens]


@pytest.mark.parametrize("perfil", ["gestao", "fin", "sup"])
def test_k1_detalhe_traz_as_mensagens_recentes_com_quem_falou(client, contas, cenario, perfil):
    corpo = _ok(_detalhe(client, getattr(contas, perfil).token, contas.joana.id), f"detalhe joana ({perfil})")
    recentes = _recent(corpo)
    for item in recentes:
        assert {"role", "content", "created_at"} <= set(item), item
        assert item["role"] in PAPEIS, item
    assert [(m["role"], m["content"]) for m in recentes] == [
        ("user", "Quando começa a turma?"), ("assistant", "Em novembro."),
        ("user", "E o material?"), ("assistant", "Está na área do aluno."),
    ]
    assert _projetar(recentes) == _projetar(Database.list_chat_messages(contas.joana.id))


def test_k2_recent_e_o_final_do_historico_com_limite(client, contas, cenario):
    for numero in range(30):
        Database.add_chat_exchange(contas.pedro.id, f"Pergunta {numero:02d}", f"Resposta {numero:02d}")
    historico = _projetar(Database.list_chat_messages(contas.pedro.id))
    assert len(historico) == 60, "pré-condição: 60 mensagens gravadas"
    recentes = _projetar(_recent(_ok(_detalhe(client, contas.gestao.token, contas.pedro.id), "detalhe pedro")))
    assert 10 <= len(recentes) <= LIMITE_PROPOSTO, f"esperava as mais recentes (10 a {LIMITE_PROPOSTO}): {len(recentes)}"
    assert recentes == historico[-len(recentes):], "recent deve ser o final do histórico, em ordem cronológica"
    assert recentes[-1][:2] == ("assistant", "Resposta 29")


def test_k3_nao_mistura_conversas_de_outro_aluno(client, contas, cenario):
    r = _detalhe(client, contas.gestao.token, contas.rita.id)
    corpo = _ok(r, "detalhe rita")
    assert _recent(corpo) == []
    assert corpo["chat"]["messages"] == 0 and corpo["chat"]["last_chat_at"] is None
    for texto in ("Quando começa a turma?", "Em novembro.", "E o material?"):
        assert texto not in r.text


def test_k4_texto_mascarado_pela_gr3_volta_como_gravado(client, contas, cenario):
    Database.add_chat_exchange(contas.vazio.id, CARTAO_MASCARADO, "Aceitamos cartão pelo Mercado Pago.")
    r = _detalhe(client, contas.sup.token, contas.vazio.id)
    recentes = _recent(_ok(r, "detalhe aluno com cartão mascarado"))
    assert ("user", CARTAO_MASCARADO) in [(m["role"], m["content"]) for m in recentes]
    assert "4111" not in r.text


def test_k5_suporte_nao_ve_valor_nem_rs_mesmo_dentro_da_conversa(client, contas, cenario):
    resposta = f"Sim: seu pagamento de R$ {f'{VALOR_A:.2f}'.replace('.', ',')} do curso foi aprovado."
    Database.add_chat_exchange(contas.joana.id, "Meu pagamento foi aprovado?", resposta)

    gestao = _ok(_detalhe(client, contas.gestao.token, contas.joana.id), "detalhe joana (gestão)")
    assert ("assistant", resposta) in [(m["role"], m["content"]) for m in _recent(gestao)], \
        "Gestão vê o texto gravado"

    r = _detalhe(client, contas.sup.token, contas.joana.id)
    corpo = _ok(r, "detalhe joana (suporte)")
    recentes = _recent(corpo)
    assert ("user", "Meu pagamento foi aprovado?") in [(m["role"], m["content"]) for m in recentes]
    _sem_valores(r, (VALOR_A, VALOR_B))
    assert "R$" not in r.text, f"Suporte recebeu valor em R$ na conversa: {r.text[:500]}"


def test_k6_resumo_da_f3_continua_e_e_coerente_com_recent(client, contas, cenario):
    lista = _ok(client.get("/api/dashboard/alunos", headers=_auth(contas.gestao.token)), "dashboard alunos")
    linha = next(s for s in lista["students"] if s["id"] == contas.joana.id)
    corpo = _ok(_detalhe(client, contas.gestao.token, contas.joana.id), "detalhe joana")
    assert corpo["chat"]["messages"] == linha["chat_messages"] == 2
    assert corpo["chat"]["last_chat_at"] == linha["last_chat_at"]
    do_aluno = [m for m in _recent(corpo) if m["role"] == "user"]
    assert do_aluno and do_aluno[-1]["created_at"] == corpo["chat"]["last_chat_at"]


@pytest.mark.parametrize("quem", ["sem-token", "forjado", "aluno"])
def test_k7_rbac_do_detalhe_continua(client, contas, cenario, quem):
    token = {"sem-token": None, "forjado": _forjado(), "aluno": contas.joana.token}[quem]
    r = _detalhe(client, token, contas.joana.id)
    assert r.status_code == (403 if quem == "aluno" else 401), f"{quem}: HTTP {r.status_code} {r.text[:200]}"
    assert "Quando começa a turma?" not in r.text
