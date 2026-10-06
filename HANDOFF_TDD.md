# HANDOFF — TDD Fase 2 (global-training-technology)

Documento escrito para quem nunca viu a sessão original. Estado verificado por leitura do git e dos arquivos em 05/10/2026, depois do resgate do log de decisões.

**Atualização de 06/10/2026 (modo autônomo D40; E6 entregue, D41):** ver `docs/tdd/RELATORIO_NOITE.md`.

**Atualização de 06/10/2026 (E5 entregue, D36 e D37):** ver seção 10 e `docs/tdd/decisoes_tdd.md`.

**Atualização de 05/10/2026 (E4 fechada, D34; agentes formalizados em `.claude/agents/`, D35):** ver seção 10 e `docs/tdd/decisoes_tdd.md`.

**Atualização de 05/10/2026 (sessão de validação da E3):** a E3 foi validada por suíte e mergeada. As seções abaixo trazem o resultado. O que vale para a E1 e a E2 continua como estava: não foi revalidado nesta sessão, mas a regressão delas passou junto com a E3 (81 testes de backend verdes).

Log completo de decisões: `docs/tdd/decisoes_tdd.md`. Charter dos papéis: `docs/tdd/papeis_tdd.md`.

> **LEIA PRIMEIRO — duas mudanças de regra de 05/10/2026 que contradizem o texto antigo deste documento:**
> - **Push liberado (D30).** A frase "nunca fazer push", ainda presente na seção 5 e no `papeis_tdd.md`, está **revogada**. Valem os limites da D30: nunca tocar na `main`, nunca force-push, parar e avisar o PM se um push for rejeitado, e auditar segredo antes de cada push.
> - **Objetivo é fechar as nove entregas (D31).** A ordem de "parar depois da E3" está revogada. O plano está na **seção 10**, que deve ser atualizada ao fim de cada entrega, com commit e push.
> - **Autovigilância obrigatória (D32).** Gatilhos de parada na seção 10.
>
> - **Push executado em 05/10/2026 (D33).** `feature/fase2-tdd` e `feature/fase2-tdd-e3-painel-materiais` estão publicadas. `main` intocada. Ver seção 11 para o achado do perfil de navegador, que virou item de backlog e **não deve ser executado** por este time.

**Documento de escopo: LOCALIZADO.** `Escopo_Fase2_Global_Training_Technology.pdf`, na raiz do repo, versionado desde `75a30e6`. A versão anterior deste handoff (seção 2) dizia que não tinha sido encontrado; **estava errado**. O escopo das entregas 4 a 9 sai dele e está destrinchado na seção 10.

---

## 1. Estado das branches (HEAD verificado)

| Branch | HEAD | Situação |
|---|---|---|
| `feature/fase2-tdd` | ver `git log` | **Branch de projeto.** Contém E1, E2 e E3 mergeadas e a E4 (commits diretos, D34). |
| `feature/fase2-tdd-e1-identidade` | `dfe307c` | E1. Totalmente mergeada em `feature/fase2-tdd` (merge `9578a8f`). |
| `feature/fase2-tdd-e2-conta-aluno` | `b988b92` | E2. Totalmente mergeada em `feature/fase2-tdd` (merge `351a130`). |
| `feature/fase2-tdd-e3-painel-materiais` | `1eaa7a7` | E3. Validada e totalmente mergeada em `feature/fase2-tdd` (merge `da55d8f`). |
| `feature/fase2-tdd-e5-chatbot-autenticado` | `b83e378` (+ commit de docs) | E5. Mergeada em `feature/fase2-tdd` (ver `git log`). Aguardando validação do PM. |
| `feature/fase2-painel-administrativo` | `aa619ac` (09/09) | Anterior. Não tocar. |
| `feature/fase2-merge-gustavo` | `9be15e2` | Anterior. Não tocar. |
| `feature/fase2-angular-integrado` | `d34d89b` | Anterior. Não tocar. |
| `main` | `4b75c30` | Não tocar. |
| `origin/payment-system` | `75a30e6` | Não tocar. |

Sub-branches da E3: não existem. A E3 é uma branch só. A E3 também carrega um commit duplicado do próprio `HANDOFF_TDD.md` (`f4580f2`), com blob idêntico ao `eed037a` da branch de projeto; o merge resolveu sozinho, sem conflito.

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

### E3 — Painel de inscrições e materiais (RF22, item 1.1) — **VALIDADA E MERGEADA (05/10/2026)**
- Commits:
  - `734469d` — testes vermelhos do painel, dos materiais e do IDOR (backend + e2e).
  - `2e76cfe` — implementação de backend (`feat(e3)`, D28).
  - `1eaa7a7` — implementação de frontend (Angular). **Era a árvore suja descrita na seção 6 da versão anterior deste documento:** os cinco arquivos conferem um a um com a lista registrada lá, a autoria e o `Co-Authored-By` são os mesmos dos outros commits da entrega, e o conteúdo atende exatamente o e2e escrito antes, em `734469d`. Trabalho legítimo da sessão travada, commitado às 14:44, um minuto depois do commit de documentação.
- Merge: `da55d8f` em `feature/fase2-tdd`, `--no-ff`. Sem push.
- Escopo (D28): `GET /api/student/enrollments` e `GET /api/student/enrollments/{id}`. Materiais aparecem só com matrícula `active`. Outro aluno → 404. Perfil de funcionário → 403. Sem token → 401.

**Checklist de 9 itens — fechado.** Os itens são os do contrato da D28 mais o ciclo TDD; os dois obrigatórios do PM são o 3 e o 4.

| # | Item | Veredito | Prova |
|---|---|---|---|
| 1 | Lista só as matrículas do dono do token, com `id`, `course_id`, `course_name`, `status`, `enrolled_at` | OK | `test_t1`, `test_t6`; sonda A1/A2 |
| 2 | Detalhe abre só a matrícula do dono | OK | `test_t5` (a própria abre com 200) |
| 3 | **IDOR (obrigatório):** matrícula alheia → 404 idêntico a inexistente; nenhum endpoint aceita identificador de usuário do cliente | OK | `test_t5`, `test_t6`, `test_t7`; sonda A3–A8 |
| 4 | **`pending`, `cancelled` e `refunded` não liberam material (obrigatório)** | OK | `test_t3` (3 casos), `test_t12` (4 status); sonda B2–B5 |
| 5 | Curso sem o campo `materials` continua aceito e devolve lista vazia | OK | `test_t4`, `test_t11b` |
| 6 | `materials` aceito no `CourseInput` do admin | OK | `test_t11a`; `create-course` e `update-course` usam o mesmo schema |
| 7 | Funcionário → 403; sem token ou token forjado → 401 | OK | `test_t8` (6 casos), `test_t8b` (3), `test_t9`, `test_t10`; sonda C1–C4 |
| 8 | Tela `/student` com "Meus cursos", badge de status, materiais só quando `active` | OK | e2e P1–P7, 7/7 em Chromium; build Angular limpo |
| 9 | Ciclo TDD: red antes do código | OK | ver abaixo |

**Red reproduzido nesta sessão** (worktree isolado em `734469d`, só os testes, sem a implementação): **25 falham, 1 passa**. A que passa é a `test_t11b`, guarda de compatibilidade (curso sem `materials` já era aceito antes da E3) — mesmo padrão do teste 7b da E1 registrado na D2, não é red de implementação.

**Green registrado nesta sessão:**
- Backend em `1eaa7a7`: **81 passed, 0 failed** (26 da E3 + regressão E1/E2/fase2). Repetido depois do merge, em `da55d8f`: **81 passed**.
- E2E Chromium (`frontend/e2e/test_e3_painel_angular.py`): **7/7 checks** (P1 a P7), com backend em `127.0.0.1:8000` e `ng serve` em `localhost:4200`.
- Sondagem independente de IDOR e de vazamento de material, por HTTP contra o servidor no ar, fora da suíte: **38/38**. Cobriu variantes que a suíte não cobre: `userId`, `student_id`, `id` e `email` na query; cabeçalhos `X-User-Id`, `X-User-Email` e `X-Student-Id` forjados; detalhe de matrícula alheia nos quatro status; e vazamento por outras rotas (`/api/courses` público e `/api/admin/course/{id}` com token de aluno).
- Build Angular de desenvolvimento: limpo.

### Entregas 4 a 9
**Corrigido em 05/10/2026.** O documento de escopo estava na raiz do repo o tempo todo (`Escopo_Fase2_Global_Training_Technology.pdf`). O plano das sete entregas restantes está na **seção 10**.

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

> Atenção: a regra "nunca fazer push" que estava nesta seção e no `papeis_tdd.md` foi **revogada pela D30** em 05/10/2026. Push liberado, com os limites da D30 e a ressalva da seção 11.

1. **Um agente por vez** no repo. Confirmar que o anterior **retornou** antes de chamar o próximo.
2. **Árvore limpa antes de chamar agente:** commit ou stash do que estiver na árvore.
3. **Dev não altera teste.** Mudança de teste só pelo agente-testes, e só com autoridade (seção 7).
4. **Agente em primeiro plano.**
5. Nunca rodar a suíte em paralelo com outra execução do repo (D29, uso concorrente).

## 6. Pendências e pontos de atenção

**E3 — RESOLVIDA.** Validada e mergeada (`da55d8f`). Ver seção 2.

**Árvore de trabalho suja — RESOLVIDA.** As alterações não commitadas em `frontend/` eram do commit `1eaa7a7`, feito pela sessão travada depois do commit de documentação. A árvore está limpa desde então; nada foi commitado em cima de trabalho de terceiros.

**Dívidas abertas:**
- D4 — e2e: 27 vs 29 checks; seed de pagamento pendente no harness.
- D6 — `frontend/e2e/test_admin_angular.py` com alteração pendente, sem commit.
- D7 — seed do e2e grava em `backend/db.sqlite` de dev; falta `DB_PATH` isolado.
- D10 — confirmar que o teste de duas compras no mesmo segundo está commitado e verde.
- D13 — envio de link só em arquivo de dev; SMTP é trabalho futuro.
- Recuperação de senha: fora do escopo, mas login de aluno em produção vai precisar. Item próprio no backlog.
- Entregas 4 a 9 — escopo não localizado.

**Achados da validação da E3 que NÃO bloqueiam o merge (decisão do PM pendente):**
- `PUT /api/admin/update-course` usa o mesmo `CourseInput`, onde `materials` tem default `[]`. Quem editar um curso sem reenviar `materials` **apaga os materiais em silêncio**. Hoje é só risco latente: nesta branch nenhuma tela chama `update-course`. Vira defeito real no dia em que a área administrativa ganhar edição de curso. Fora do escopo da D28.
- Não existe `backend/.env` nesta máquina (é gitignored e não foi encontrado). Para a validação desta sessão as variáveis foram passadas na linha de comando do `uvicorn`, sem criar arquivo no repo. Quem for rodar o e2e precisa fazer o mesmo ou criar o `.env` a partir do `.env.example`.
- A seção 9 dizia que a execução do e2e era "não confirmada". Confirmada agora, para a E3: `py -3 -m pytest frontend/e2e/test_e3_painel_angular.py -s`, com `ADMIN_PASSWORD`, `E2E_BASE_URL` e `E2E_API_URL` no ambiente.

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

Comandos atualizados em 05/10/2026. O backend e o e2e da E3 foram **executados e confirmados**. Variáveis de ambiente, a lista completa e o passo a passo estão no `AGENTS.md`, seção 6.

Variáveis: sem `backend/.env` no repo, passar `JWT_SECRET_KEY`, `ADMIN_PASSWORD`, `FINANCIAL_PASSWORD`, `SUPPORT_PASSWORD` e as demais no ambiente da sessão. Para o e2e: `ADMIN_PASSWORD`, `E2E_BASE_URL` (`http://localhost:4200`) e `E2E_API_URL` (`http://127.0.0.1:8000`).

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

**E2E da E3 (confirmado):** `py -3 -m pytest frontend/e2e/test_e3_painel_angular.py -s`, com as variáveis acima no ambiente.

**E2E dos outros dois arquivos (`test_admin_angular.py`, `test_e2_conta_aluno_angular.py`):** seguem o mesmo padrão, mas a execução **não foi confirmada**. Confirmar antes de usar.

**Build Angular:** `cd frontend` e `npx ng build`. Validado limpo na E3.

Atenção: o e2e grava pagamentos de teste em `backend/db.sqlite` (D7). Antes de rodar de novo, considerar o acúmulo.

---

## 10. Plano das nove entregas (D31) — manter atualizado ao fim de CADA entrega

Fonte do escopo: `Escopo_Fase2_Global_Training_Technology.pdf` (raiz do repo). As seções e RFs citados abaixo são os dele.

| Entrega | Escopo | Rastreabilidade | Estado |
|---|---|---|---|
| **E1** | Identidade unificada | — | **Fechada e mergeada** (`9578a8f`) |
| **E2** | Conta e login do aluno | item 1.1, RF21 | **Fechada e mergeada** (`351a130`) |
| **E3** | Painel de inscrições + materiais | item 1.1, RF22 | **Fechada e mergeada** (`da55d8f`), validada 05/10/2026 |
| **E4** | Histórico financeiro + recibos | item 1.1, RF22 | **Fechada pelo PM (D34), 05/10/2026.** Testes E4 7/7, build Angular verde, regressão de backend 88 passed. Implementada diretamente na branch de projeto por orientação do PM: `b27bd6d`, `f9f20cc`, `da6de8e`. e2e de navegador sem saída registrada. |
| **E5** | Chatbot autenticado: contexto de cursos ativos e histórico persistido | seção 4 | **Entregue e mergeada em 06/10/2026, aguardando validação do PM (D37).** Sub-branch `feature/fase2-tdd-e5-chatbot-autenticado`. Testes `7e030c7`, `eeaed3b`; e2e `cf37572`, `970d2c1`; backend `ed5fa3b`; frontend `2421a9c`, `b83e378`. Backend 131 passed; e2e 11/11 (chat) e 9/9 (dashboard); build limpo. |
| **E6** | Segurança de LLM: isolamento de sessão por usuário + filtros OWASP | seção 4 | **Entregue em 06/10/2026, aguardando validação do PM (D41).** Testes `481b742`, `fb3744d`, `7208da8`; e2e `a00eaff`; backend `8bbd34a`; landing `7e2f9bd`. Backend 271 passed; landing 8/8. |
| **E7** | Observabilidade de IA completa: `usage` do Groq, custo, persistência | seção 4, RF24 | **Entregue em 06/10/2026, aguardando validação do PM (D44).** Testes `6b27fc4`; e2e `9a61216`; backend `b36c188`; frontend `530ea3a`. Backend 348 passed; e2e 11/11. |
| **E8** | Auditoria com identificação do usuário responsável | seção 2 | A fazer |
| **E9** | Hardening de pagamento: assinatura do webhook, conferência de valor, idempotência, CORS | **ACRÉSCIMO DO PM — não consta do documento de escopo** (D33.6) | A fazer |

Notas de escopo lidas no PDF, para quem for pegar as próximas:
- **E4:** o PDF pede "recibos, status de pagamentos concluídos ou pendentes referentes às inscrições realizadas na landing page". A D-anterior do PM já definiu: recibo em JSON primeiro, PDF só se sobrar tempo (`papeis_tdd.md`).
- **E6 (refinamento ADOTADO pelo PM, D33.4):** os dois riscos nomeados no PDF viram **teste obrigatório** da entrega, não cobertura genérica — (a) agente manipulado para **conceder desconto indevido**; (b) **vazamento de informação entre sessões de usuários diferentes**. Entram no checklist como os obrigatórios da E6, no mesmo peso que o IDOR teve na E3.
- **E7 (refinamento ADOTADO pelo PM, D33.5):** o `usage` do Groq tem de ser **persistido em banco**. O PDF pede custo de inferência, e métrica que zera no restart não atende. Contador em memória reprova a entrega.
- **E8:** o PDF exige "estampa de tempo, identificação do usuário responsável e a alteração efetuada" nos eventos críticos (dados cadastrais, preço de curso, reembolso).
- **E9:** **não está no PDF — é acréscimo do PM** (D33.6). O PM mantém a entrega por serem defeitos de segurança reais ("entregar sem eles é pior que entregar fora do escopo literal"), e registra a classificação para que o grupo possa cortar a entrega se quiser. Quem for apresentar o trabalho precisa saber que esta é a única das nove que não sai do documento.

### Backlog (fora das nove entregas)
- Recuperação de senha do aluno. Fora do escopo, mas login em produção vai precisar.
- Limpeza do `.chrome-pdf-profile/` do histórico (seção 11). **Decisão do grupo, não deste time. Não executar.**
- D4, D6, D7 — dívidas do harness de e2e (seção 6).

### Processo por entrega (padrão fixo)
1. Sub-branch própria a partir de `feature/fase2-tdd`.
2. **Commit de teste vermelho** (agente-testes), com o red observado e registrado.
3. **Commit de implementação** (dev-backend ou dev-frontend), só até o verde.
4. Verificação: suíte da entrega + regressão + e2e no navegador, quando houver tela.
5. Checklist de 9 itens preenchido. Os dois obrigatórios da E3 — **IDOR** e **recurso pago liberado só com matrícula ativa** — continuam valendo em toda entrega onde fizerem sentido.
6. Merge `--no-ff` em `feature/fase2-tdd`.
7. **Atualizar esta seção e a seção 1**, commitar, e dar push das duas branches (ver D30 e seção 11).
8. **Reportar ao PM e parar.** O PM valida uma entrega por vez; não encadear a seguinte sem resposta dele.

### Autovigilância (D32) — parada obrigatória
Qualquer um destes sinais interrompe o ciclo: agente retornando incompleto duas vezes seguidas; o orquestrador repetindo a mesma análise em rodadas consecutivas; perda de rastro do que já foi feito. Ao detectar: parar, deixar a árvore limpa e commitada, atualizar este documento, avisar o PM que precisa de sessão nova. Parar a tempo é resultado bom.

---

## 11. PUSH — executado; e o achado do perfil de navegador (backlog)

**Estado: push FEITO em 05/10/2026.** `feature/fase2-tdd` e `feature/fase2-tdd-e3-painel-materiais` publicadas em `origin`. `main` intocada (`4b75c30`). Sem force-push. O PM escolheu a opção 1 abaixo (D33.2), com o fundamento de que a exposição já existia e o push não acrescenta nenhum blob do perfil.

A auditoria pré-push encontrou o seguinte.

### O achado
O commit **`92b959a`** ("Presentation changes", Gustavo Santos Steluti, 25/05/2026) versionou um **perfil completo do Chrome** em `.chrome-pdf-profile/` — 162 arquivos, 9,8 MB, incluindo `Login Data`, `Network/Cookies`, `History`, `Web Data` e `Account Web Data`.

### O que ele realmente contém (medido, não presumido)
Os cofres estão **vazios**: 0 logins, 0 logins com senha, 0 cookies, 0 registros de autofill, 0 cartões de crédito. Era um perfil descartável de Chrome headless, usado para gerar o PDF da apresentação. Varredura por padrões de chave (`gsk_`, `APP_USR-`, `sk-`, `ghp_`, `AIza`, JWT) em todos os 162 arquivos: **nenhuma ocorrência**.

O que vaza de fato é pequeno, mas não é nada: o caminho `C:/Users/Gustavo Steluti/Desktop/Projeto Aplicado TCC/` (nome de usuário do Windows, no único registro de histórico), um `media_router.receiver_id_hash_token` e um hash de `gaia_cookie` nas `Preferences`.

### O agravante
Esse commit **já está no repositório público**: é ancestral de `origin/payment-system`, e os 162 arquivos estão na árvore do tip dessa branch. **A exposição já existe hoje**, independente de qualquer push nosso.

### O que o push de `feature/fase2-tdd` enviaria de novo
Só código-fonte, testes e documentação: **265 objetos, nenhum deles** do perfil, `.env`, `db.sqlite`, mídia ou PDF (o remoto já tem esses blobs). Verificado com `git rev-list --objects origin/main..feature/fase2-tdd --not --remotes=origin`.

Ainda assim o push foi **suspenso**, porque o perfil está no *histórico* da branch: publicá-la torna esses blobs alcançáveis também por `feature/fase2-tdd`. Importa se o PM um dia apagar `payment-system` para limpar a exposição — a cópia sobreviveria pela nossa branch.

### Higiene já existente
`.gitignore` já cobre `.chrome-pdf-profile/`, `.env`, `.env.*` e `*.sqlite`. A árvore de trabalho e o tip de `feature/fase2-tdd` estão limpos. O problema é exclusivamente histórico.

### Opções para o PM
1. **Push assim mesmo.** A exposição já existe via `payment-system` e nada de novo sobe. Mais rápido; mantém o histórico sujo.
2. **Limpar primeiro, depois push.** Expurgar `.chrome-pdf-profile/` do histórico (`git filter-repo`) nas branches de trabalho e apagar/limpar `payment-system` no remoto. Reescreve histórico e exige force-push — **que a D30 proíbe**, então é decisão explícita do PM, com o Gustavo avisado, já que a branch é dele.
3. **Push só da sub-branch da E3 e da `feature/fase2-tdd` como estão, e tratar a limpeza como item próprio de backlog.**

Recomendação do orquestrador: **opção 1 para destravar a entrega, com a opção 2 agendada como tarefa própria** — e, de qualquer forma, avisar o Gustavo de que um perfil de navegador dele está público, mesmo sem credencial dentro.

### Veredito do PM (D33) — item de BACKLOG, NÃO EXECUTAR
O PM escolheu a **opção 1** e o push foi feito. A limpeza do histórico fica como **item de backlog e não deve ser executada por este time**: reescrever histórico com `filter-repo` e dar force-push numa branch do Gustavo, em repositório dele, é decisão do grupo, com o Gustavo participando — não nossa. **Não executar nem se parecer seguro.**

Resumo para quem for levar o assunto ao grupo:
- O que é: perfil descartável de Chrome headless usado para gerar o PDF da apresentação, versionado por engano em `92b959a`.
- Gravidade: **baixa**. Os cofres estão vazios (0 logins, 0 cookies, 0 autofill, 0 cartões) e não há nenhum padrão de chave nos 162 arquivos. Isso **baixa a urgência, mas não anula o problema**.
- O que vaza: nome de usuário do Windows do Gustavo num caminho de arquivo, um token de device do media router e um hash de cookie do Google.
- Onde está: `origin/payment-system` (na árvore do tip) e, desde 05/10/2026, também no histórico de `feature/fase2-tdd` e da sub-branch da E3.
- Custo de limpar: reescrita de histórico nas branches afetadas + force-push + coordenação com todo mundo que tenha clone.
