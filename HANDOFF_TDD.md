# HANDOFF — TDD Fase 2 (global-training-technology)

Documento escrito para quem nunca viu a sessão original. Estado verificado por leitura do git e dos arquivos em 05/10/2026, depois do resgate do log de decisões. Nada aqui foi validado por suíte nova.

Log completo de decisões: `docs/tdd/decisoes_tdd.md`. Charter dos papéis: `docs/tdd/papeis_tdd.md`.

---

## 1. Estado das branches (HEAD verificado)

| Branch | HEAD | Situação |
|---|---|---|
| `feature/fase2-tdd` | `5991c93` (docs do resgate) sobre `351a130` | **Branch de projeto.** Contém E1 e E2 mergeadas. |
| `feature/fase2-tdd-e1-identidade` | `dfe307c` | E1. Totalmente mergeada em `feature/fase2-tdd` (merge `9578a8f`). |
| `feature/fase2-tdd-e2-conta-aluno` | `b988b92` | E2. Totalmente mergeada em `feature/fase2-tdd` (merge `351a130`). |
| `feature/fase2-tdd-e3-painel-materiais` | `2e76cfe` | **E3. NÃO mergeada e NÃO validada.** Ver seção 2. |
| `feature/fase2-painel-administrativo` | `aa619ac` (09/09) | Anterior. Não tocar. |
| `feature/fase2-merge-gustavo` | `9be15e2` | Anterior. Não tocar. |
| `feature/fase2-angular-integrado` | `d34d89b` | Anterior. Não tocar. |
| `main` | `4b75c30` | Não tocar. |
| `origin/payment-system` | `75a30e6` | Não tocar. |

Sub-branches da E3: não existem. A E3 é uma branch só.

## 2. Entregas

### E1 — Identidade unificada (MERGEADA)
- Testes: `dfe307c`, `114d44e` (versão autoritativa, D1).
- Produção: `50a1164` (dev-backend), com sufixo aleatório em `external_reference` (D10).
- Merge: `9578a8f` em `feature/fase2-tdd`, `--no-ff`. Sem push.
- Veredito do PM: **APROVADA com condição**. A condição (prova por mutação do D10) foi cumprida.

### E2 — Autenticação e criação de conta do aluno (MERGEADA)
- Commits: `47d9b69` a `38a7a36` (testes vermelhos, implementação, ajustes de contrato).
- Merge: `351a130` em `feature/fase2-tdd`. Branch: `b988b92`.
- Cobre itens 1.1 e RF21.

### E3 — Painel de inscrições e materiais (RF22, item 1.1) — **PENDENTE**
- Commits **ainda não mergeados** em `feature/fase2-tdd`:
  - `734469d` — testes vermelhos do painel, dos materiais e do IDOR.
  - `2e76cfe` — implementação (`feat(e3)`, D28).
- **Não validada.** Não há registro de suíte rodada sobre `2e76cfe`. Não confiar no relatório da sessão travada sobre a E3.
- Escopo (D28): `GET /api/student/enrollments` e `GET /api/student/enrollments/{id}`. Materiais aparecem só com matrícula `active`. Outro aluno → 404. Perfil de funcionário → 403. Sem token → 401.
- Obrigatório (PM): **IDOR** nos endpoints de aluno.
- Ver seção 6, item E3 (árvore suja).

### Entregas 4 a 9
Não há detalhe nos arquivos resgatados. O documento de escopo não foi localizado (busquei em `%APPDATA%\Claude` e em `C:\Users\vihug`, até 6 níveis). **Escopo das entregas 3 a 9 incompleto neste documento**: é preciso o documento de escopo para descrevê-las.

## 3. Decisões resgatadas (resumo; texto integral em `docs/tdd/decisoes_tdd.md`)

- **D0** — Processo: dois agentes de teste rodaram em paralelo na mesma árvore e se sobrescreveram. Regra: um agente por vez.
- **D1** — Versão autoritativa dos testes da E1: `114d44e`. Red observado: 21 falhas, 1 passa (7b).
- **D2** — Teste 7b é guarda de preservação, não red de implementação.
- **D3** — Teste 4: verificar status antes de `user_id`. Defeito do teste, corrigido pelo agente de testes.
- **D4** — E2E: 27 vs 29 checks. Os dois checks de reembolso são pulados com banco vazio. Harness deve semear pagamento pendente. Sem mudar produção.
- **D5** — `requirements-dev.txt` com `playwright`: aceito.
- **D6** — Alteração pendente em `frontend/e2e/test_admin_angular.py`: vai num commit de follow-up dos testes.
- **D7** — Seed do e2e grava pagamentos de teste em `backend/db.sqlite` (dev, ignorado pelo git). Dívida do harness. Correção futura: `DB_PATH` isolado.
- **D8** — Check de reembolso do e2e passou para comparação antes/depois (commit `f6f1169`).
- **D9** — Red legítimo do teste 4 (falta `user_id` na matrícula).
- **D10** — Sufixo aleatório em `external_reference` foi desvio de processo, aceito como correção real; exigiu teste de duas compras no mesmo segundo. Prova por mutação feita.
- **D11** — IDOR não existe na E1 (sem endpoint de aluno). Fica para a E3.
- **D12** — Token de definição de senha: gerado no webhook quando o pagamento vira aprovado e a conta não tem senha. Guardado só como SHA-256. Expira em 48 h. Uso único.
- **D13** — Entrega do link: não há servidor de e-mail. A função `send_password_setup_link` grava em arquivo de saída de **desenvolvimento, fora do repo**. Troca por SMTP é trabalho futuro.
- **D14** — Senha mínima de 8 caracteres.
- **D15** — Cadastro direto: papel sempre `student`; e-mail existente → 400 genérico e não altera a senha.
- **D16** — Definição de senha só vale para conta sem senha; senão 400 genérico.
- **D17** — Nenhum endpoint aceita `user_id` do cliente.
- **D18** — Senha com bcrypt.
- **D21** — Cadastro com resposta uniforme 200 (aprovada pelo PM). Não é precedente: quem alterou o teste foi o agente de testes, com aprovação do PM.
- **D22** — Comunicação fora do HTTP (outbox): e-mail novo recebe o link; e-mail existente recebe aviso.
- **D23** — Cadastro direto não envia link de definição de senha (aprovada pelo PM).
- **D24** — 400 do login sem senha tolerado na C8, por **par** rota+tela (aprovada pelo PM).
- **D25** — `test_13b` com senha fraca nos dois casos (aprovada pelo PM). A intenção de "e-mail existente recusado" foi **revogada** pelo D21, não abandonada.
- **D26** — Aviso de e-mail existente aponta só para o login (aprovada pelo PM).
- **D27** — Correção da associação console↔response no harness da C8 (dentro da autoridade permanente).
- **D28** — Escopo da E3 (ver seção 2).
- **D29** — Higiene do teste da E3. Nota corrigida: a limpeza do fixture **já existia** em `734469d`. Nenhuma alteração de teste foi feita.

## 4. Charter dos papéis (resumo; texto integral em `docs/tdd/papeis_tdd.md`)

- **Agente-testes:** escreve testes antes do código, observa o red, registra a saída. Não escreve produção. Não altera o próprio teste depois que o dev começou, sem aprovação.
- **Dev-backend (FastAPI/SQLite):** implementa até green. **Não altera testes.** Se achar teste errado, reporta e para.
- **Dev-frontend (Angular, padrão do Gustavo):** mesma regra.
- **Regras comuns:** nunca push; não trocar de branch sem ordem do orquestrador; não tocar nas branches anteriores; commits com `Co-Authored-By`.

## 5. Regras de processo (obrigatórias)

1. **Um agente por vez** no repo. Confirmar que o anterior **retornou** antes de chamar o próximo.
2. **Árvore limpa antes de chamar agente:** commit ou stash do que estiver na árvore.
3. **Dev não altera teste.** Mudança de teste só pelo agente-testes, e só com autoridade (seção 7).
4. **Agente em primeiro plano.**
5. Nunca rodar a suíte em paralelo com outra execução do repo (D29, uso concorrente).

## 6. Pendências e pontos de atenção

**E3 — não validada e mergeada:**
- `734469d` e `2e76cfe` estão só na branch da E3.
- Antes de mergear: rodar a suíte da E3 e a regressão. Não existe registro dessas execuções.
- Confirmar o IDOR (obrigatório, PM).

**Árvore de trabalho suja (não é nossa; não commitar sem entender):** no momento do resgate havia alterações **não commitadas** em `feature/fase2-tdd` herdadas do checkout da E3:
- `frontend/src/app/app-routing.module.ts` (modificado)
- `frontend/src/app/components/student-dashboard/student-dashboard.component.html` (modificado)
- `frontend/src/app/components/student-dashboard/student-dashboard.component.ts` (modificado)
- `frontend/src/app/services/api.service.ts` (modificado)
- `frontend/src/app/resolvers/` (não rastreado)

Autoria provável: a sessão travada, que ainda estava escrevendo. Confirmar antes de qualquer commit.

**Dívidas abertas:**
- D4 — e2e: 27 vs 29 checks; seed de pagamento pendente no harness.
- D6 — `frontend/e2e/test_admin_angular.py` com alteração pendente, sem commit.
- D7 — seed do e2e grava em `backend/db.sqlite` de dev; falta `DB_PATH` isolado.
- D10 — confirmar que o teste de duas compras no mesmo segundo está commitado e verde.
- D13 — envio de link só em arquivo de dev; SMTP é trabalho futuro.
- Recuperação de senha: fora do escopo, mas login de aluno em produção vai precisar. Item próprio no backlog.
- E3 — validação, merge e IDOR (acima).
- Entregas 4 a 9 — escopo não localizado.

## 7. Autoridade permanente concedida pelo PM

O orquestrador **não** precisa consultar o PM quando a alteração de teste é consequência mecânica de decisão já aprovada e registrada, desde que:
- (a) a decisão de origem esteja aprovada e registrada;
- (b) a intenção do teste seja preservada, ou sua revogação já tenha sido decidida pelo PM;
- (c) quem altere seja o **agente-testes**, nunca o dev;
- (d) fique registrado, com o encadeamento explícito (ex.: D21 → D25 → D27).

Decisão **nova** (contrato, comportamento visível, conflito de requisitos, corte de escopo) continua vindo ao PM.

## 8. Decisões do PM sobre lacunas do escopo

**Não consegui identificar com certeza as quatro decisões que o PM tomou sobre lacunas do escopo.** O log não as rotula dessa forma. As decisões que o log marca explicitamente como aprovadas pelo PM são: **D21, D22, D23, D24, D25, D26, D29**, além do veredito sobre a E1 (com condição) e da regra de que o IDOR vira item obrigatório da E3. Confirmar com o PM quais são as quatro antes de considerar este item fechado.

## 9. Comandos para rodar as suítes

Os comandos abaixo foram extraídos das docstrings do projeto. **Não confirmei** cada invocação exata contra o histórico de execução; antes de usar, confirmar.

**Backend (pytest):**
```
cd backend
python -m pytest tests
```
`backend/tests/conftest.py` aponta `DB_PATH` para um arquivo temporário, então os testes não tocam o `db.sqlite` de dev. Nunca rodar em paralelo com outra execução.

**E2E (Chromium via Playwright), pré-requisitos:**
```
cd backend
uvicorn app:app --port 8000
```
```
cd frontend
npx ng serve
```
```
py -3 -m playwright install chromium
```
Contas necessárias no backend: `admin@gt.com`, `financeiro@gt.com`, `suporte@gt.com`, semeadas a partir do `.env` (`ADMIN_EMAIL`, `FINANCIAL_EMAIL`, `SUPPORT_EMAIL` e as senhas de perfil). O `frontend/proxy.conf.json` manda `/api` para `localhost:8000`.

Execução do e2e (ex.: `py -3 frontend/e2e/test_admin_angular.py`): **não confirmada**.

Atenção: o e2e grava pagamentos de teste em `backend/db.sqlite` (D7). Antes de rodar de novo, considerar o acúmulo.
