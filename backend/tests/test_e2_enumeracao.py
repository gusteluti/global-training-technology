"""E2 - Enumeração de contas em POST /api/auth/register.

Um e-mail INEXISTENTE e um EXISTENTE (gestor já criado) devem produzir respostas indistinguíveis
para quem está de fora:
  - mesmo status HTTP;
  - mesmo corpo (mesmas chaves e mesmo texto de detail);
  - nenhum eco do e-mail na resposta;
  - tempo de resposta sem diferença perceptível (teste de tempo).

Três testes separados, para que a falha aponte a causa exata (status, corpo ou tempo).

Sobre o teste de tempo:
  - Ele é INDICATIVO, não é prova de canal lateral. Mede média de 5 chamadas, alternando
    existente e inexistente, em máquina de desenvolvimento com carga variável.
  - O limite de 300 ms é FOLGADO DE PROPÓSITO: um bcrypt (passlib, custo padrão) leva dezenas
    a centenas de ms. Se a implementação só faz hash no caminho de sucesso, a diferença
    tende a passar do limite e o teste revela o problema. Um limite apertado geraria falsos
    vermelhos por ruído da máquina.
"""

import time
import uuid

import pytest
from fastapi.testclient import TestClient

from core.security import get_password_hash
from db import Database


SENHA = "senha-forte-2026"
LIMITE_TEMPO_MS = 300
REPETICOES = 5


@pytest.fixture
def client(banco):
    from app import app as fastapi_app

    with TestClient(fastapi_app) as c:
        yield c


@pytest.fixture
def gestor_existente():
    email = f"gestor.enum.{uuid.uuid4().hex[:8]}@teste.com"
    Database.add_user(email, "Gestor Enumeração", get_password_hash("senha-gestor-enum-1"), role="admin")
    return email


def _registrar(client, email):
    return client.post("/api/auth/register", json={
        "name": "Pessoa Teste", "email": email, "password": SENHA,
    })


def _email_inexistente():
    # Cada chamada usa um e-mail novo: o caminho inexistente cria a conta (não pode ser repetido).
    return f"inexistente.{uuid.uuid4().hex[:10]}@teste.com"


def test_enum_1_status_http_e_igual_para_existente_e_inexistente(client, gestor_existente):
    r_existente = _registrar(client, gestor_existente)
    r_inexistente = _registrar(client, _email_inexistente())

    assert r_existente.status_code == r_inexistente.status_code, (
        f"status diferente: existente={r_existente.status_code}, inexistente={r_inexistente.status_code}"
    )


def test_enum_2_corpo_e_igual_e_sem_eco_do_email(client, gestor_existente):
    email_inexistente = _email_inexistente()
    r_existente = _registrar(client, gestor_existente)
    r_inexistente = _registrar(client, email_inexistente)

    assert set(r_existente.json().keys()) == set(r_inexistente.json().keys()), (
        f"chaves do corpo diferentes: existente={r_existente.json()}, inexistente={r_inexistente.json()}"
    )
    assert r_existente.json() == r_inexistente.json(), (
        f"texto do detail diferente: existente={r_existente.json()}, inexistente={r_inexistente.json()}"
    )
    assert gestor_existente not in r_existente.text, "a resposta não pode ecoar o e-mail existente"
    assert email_inexistente not in r_inexistente.text, "a resposta não pode ecoar o e-mail inexistente"


def test_enum_3_tempo_de_resposta_nao_revela_conta(client, gestor_existente):
    """Teste INDICATIVO (ver docstring do módulo): média de 5 chamadas de cada lado."""
    tempos_existente = []
    tempos_inexistente = []
    for _ in range(REPETICOES):
        inicio = time.perf_counter()
        _registrar(client, gestor_existente)
        tempos_existente.append(time.perf_counter() - inicio)

        inicio = time.perf_counter()
        _registrar(client, _email_inexistente())
        tempos_inexistente.append(time.perf_counter() - inicio)

    media_existente = sum(tempos_existente) / REPETICOES * 1000
    media_inexistente = sum(tempos_inexistente) / REPETICOES * 1000
    diferenca = abs(media_existente - media_inexistente)
    assert diferenca <= LIMITE_TEMPO_MS, (
        f"diferença de tempo de {diferenca:.0f} ms (média existente={media_existente:.0f} ms, "
        f"média inexistente={media_inexistente:.0f} ms; limite={LIMITE_TEMPO_MS} ms)"
    )
