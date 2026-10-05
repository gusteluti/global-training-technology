# Pendências do projeto TDD — Fase 2

Estado do projeto para quem vai continuar. Complementa o `AGENTS.md` (processo e comandos) e o `HANDOFF_TDD.md` (estado detalhado com hashes). Atualizar este arquivo ao fim de cada entrega.

Fonte do escopo: `Escopo_Fase2_Global_Training_Technology.pdf`, na raiz do repo.

---

## 1. Entregas fechadas

| Entrega | O que entregou | Hashes principais |
|---|---|---|
| **E1 — Identidade unificada** | Uma identidade para o usuário, com referência externa única por compra (o pagamento não colide mesmo com duas compras do mesmo curso no mesmo segundo). Aprovada pelo PM com condição, cumprida por prova de mutação. | testes `dfe307c`, `114d44e`; produção `50a1164`; merge `9578a8f` |
| **E2 — Conta e login do aluno** | Conta criada após a compra por link de definição de senha (token com hash, expiração de 48 h e uso único), cadastro direto com resposta uniforme, rota de login e política de senha mínima de 8 caracteres. | testes `47d9b69`; implementação `5b9816a`, `8e43bdc`, `bffe69c`, `38a7a36`; merge `351a130` |
| **E3 — Painel de inscrições e materiais** | Aluno vê só as próprias matrículas (com status e `enrolled_at`), detalhe de matrícula alheia devolve 404, materiais aparecem só com matrícula `active`, funcionário recebe 403 e sem token recebe 401. Tela `/student` com "Meus cursos". Validada por suíte e merge em 05/10/2026. | testes `734469d`; backend `2e76cfe`; frontend `1eaa7a7`; validação `ad291d0`; merge `da55d8f` |

Os dois obrigatórios da E3 (**IDOR** e **material só com matrícula ativa**) foram provados por suíte e por sondagem independente de HTTP (38/38). Detalhes no `HANDOFF_TDD.md`, seção 2.

Push de `feature/fase2-tdd` e `feature/fase2-tdd-e3-painel-materiais` feito em 05/10/2026 (D33). `main` intocada.

---

## 2. Em andamento

**E4 — Histórico financeiro + recibos (RF22, item 1.1).** Liberada pelo PM em 05/10/2026 (D33.7). Sub-branch ainda não criada no momento deste documento; confirmar com `git branch` antes de começar.

---

## 3. A fazer — escopo de cada entrega

### E4 — Histórico financeiro + recibos (RF22, item 1.1)
- Aluno acessa recibos e o status de pagamentos concluídos ou pendentes, ligados às inscrições feitas pela landing page.
- Recibo: **endpoint JSON primeiro**. PDF só se sobrar tempo, e não é bloqueante (decisão do PM).
- Vocabulário de status **de pagamento** é o do Mercado Pago (`approved`, `pending`, `refunded`, `rejected`...). Status **de matrícula** é o conjunto fechado `pending`, `active`, `cancelled`, `refunded`, derivado do pagamento.

### E5 — Chatbot autenticado (seção 4 do escopo)
- Para o aluno logado, o chatbot reconhece automaticamente os dados do aluno, os cursos ativos e o histórico de diálogos anteriores.
- O histórico de diálogos precisa ser **persistido**.
- Sem teste obrigatório nomeado pelo PM; o padrão de checklist vale.

### E6 — Segurança de LLM (seção 4 do escopo)
- Filtros e controles contra vulnerabilidades da OWASP para LLMs (cita explicitamente *indirect prompt injection*).
- **Dois testes obrigatórios** (D33.4), no mesmo peso que o IDOR teve na E3:
  - **(a)** agente manipulado para **conceder desconto indevido**;
  - **(b)** **vazamento de informação entre sessões** de usuários diferentes.
- Isolamento de sessão por usuário faz parte da entrega.

### E7 — Observabilidade de IA (seção 4 e RF24)
- Painel na área do funcionário com métricas de uso do LangChain e da API do Groq: conversão de atendimento, volume de requisições, tópicos que o modelo não compreendeu, **custo de inferência**.
- **Obrigatório** (D33.5): o `usage` do Groq é **persistido em banco**. Contador em memória reprova a entrega, porque zera no restart e o PDF pede custo.

### E8 — Auditoria com identificação do usuário (seção 2 do escopo)
- Trilha de auditoria para os eventos críticos da área do funcionário: alterações de dados cadastrais, modificação de preço de curso, reembolsos.
- Cada evento registra estampa de tempo, identificação do usuário responsável e a alteração efetuada.

### E9 — Hardening de pagamento (**acréscimo do PM — não consta do escopo**)
- Assinatura do webhook, conferência de valor, idempotência e CORS.
- O PM mantém a entrega por serem defeitos de segurança reais ("entregar sem eles é pior que entregar fora do escopo literal").
- **É a única das nove que não sai do documento de escopo.** O grupo pode cortá-la; quem for apresentar o trabalho precisa saber disso.

---

## 4. Já implementado antes do projeto TDD (RF23, RBAC, SPA do funcionário)

**Não é lacuna de produto.** A área do funcionário já está implementada e mergeada, fora da numeração das entregas. Foi construída antes do projeto TDD, no trabalho que originou a `feature/fase2-angular-integrado` (`d34d89b`, "Angular como interface oficial da área administrativa"). Essa branch é a base da `feature/fase2-tdd`, e `d34d89b` é ancestral dela. Está, portanto, dentro da branch de projeto. Validada na época com **44 checks de backend** e **29 de navegador**.

O que está pronto:
- **RBAC de três perfis:** Gestão, Financeiro e Suporte.
- **Quatro dashboards** (RF23 e RF24): alunos, cursos, financeiro e observabilidade de IA.
- **Trilha de auditoria** (componente `audit-logs`).
- **SPA do funcionário em Angular** (seção 3 do escopo).

Componentes em `frontend/src/app/components/`: `admin-dashboard`, `students-dashboard`, `courses-dashboard`, `financial-dashboard`, `ai-observability`, `audit-logs`, além de `student-dashboard` (área do aluno, E3).

**Por que não tem entrega numerada:** as nove entregas foram planejadas depois, para cobrir o que **faltava**. A área do funcionário ficou de fora do plano por não ser faltante. Isso é lacuna de **rastreabilidade do plano**, não de produto. Quem for ler o plano precisa saber que esta parte existe.

**Ressalvas que ficaram em aberto nessa parte:**
- **Dashboard de cursos sem o conceito de turma.** O escopo pede "número de inscritos por turma". Hoje o dashboard não tem o conceito de turma. É lacuna real frente ao escopo.
- **"Histórico de interações" no dashboard de alunos** só mostra o total de sessões, porque o chat ainda é **anônimo**. Resolve na **E5**, quando o chat for autenticado.
- **Observabilidade de IA vive em memória.** Zera no restart. Resolve na **E7**, com persistência em banco.

**Versão antiga, superada:** `feature/fase2-painel-administrativo` (`aa619ac`, 09/09) é a **versão antiga** dessa mesma área, em `admin.html` com HTML e JavaScript puros. Foi superada pela versão Angular. **Não é trabalho a aproveitar**; serve só de histórico. O `frontend/admin.html` segue versionado como **legado**. O cadastro de cursos ainda existe **só** nele. Isso precisa ser portado para o Angular antes de o legado sair do repo.

---

## 5. Quatro decisões do PM sobre lacunas do escopo

Tomadas pelo PM. Anteriores às D21 a D26 do log. Cobrem o que o documento de escopo exige mas não define.

1. **Conta do aluno nasce após a compra**, por link de definição de senha (o pagamento já valida o e-mail). **Cadastro direto também disponível.**
2. **Status de matrícula é um conjunto fechado:** `pending`, `active`, `cancelled`, `refunded`.
3. **Materiais didáticos:** campo opcional `materials: [{title, url, type}]` no JSON do curso, visível **só com matrícula ativa**.
4. **Recibo:** primeiro endpoint JSON; PDF depois, se houver tempo. **Não é bloqueante.**

---

## 6. Dívidas técnicas abertas

- **D4 — e2e:** 27 vs 29 checks. Os dois checks de reembolso pela tela são pulados com banco vazio. O harness precisa semear um pagamento pendente antes de rodar. Sem mudança de produção para isso.
- **D6 — pendente:** alteração em `frontend/e2e/test_admin_angular.py` ainda sem commit de follow-up.
- **D7 — harness:** o seed do e2e grava pagamentos de teste em `backend/db.sqlite` de desenvolvimento, e o acúmulo se repete a cada execução. Correção futura: subir o backend com `DB_PATH` isolado.
- **D10 — a confirmar:** confirmar que o teste de duas compras do mesmo curso no mesmo segundo está commitado e verde.
- **D13 — envio de link:** não há servidor de e-mail. A função `send_password_setup_link` grava o link em arquivo de saída de **desenvolvimento, fora do repo**. Troca por SMTP real é trabalho futuro.
- **Defeito latente em `PUT /api/admin/update-course`:** usa o mesmo `CourseInput` em que `materials` tem default `[]`. Quem editar um curso sem reenviar `materials` **apaga os materiais em silêncio**. Hoje nenhuma tela chama esse endpoint, então é risco latente. Vira defeito real quando a área administrativa ganhar edição de curso. Fora do escopo da D28; precisa de decisão do PM.
- **Interceptor HTTP do Angular — higiene.** O interceptor envia o header `Authorization` também em chamadas **públicas**, quando há token no navegador. Não quebra nada hoje; é higiene. Corrigir para anexar o token só a rotas que exigem autenticação.
- **bcrypt e o limite de 72 bytes** — o item foi citado pelo PM. Contexto: o bcrypt ignora tudo depois de 72 bytes da senha. Senhas longas com o mesmo prefixo de 72 bytes ficam equivalentes. A política de senha (D14, mínimo de 8) não limita o máximo. Decidir se a política ganha limite superior ou um pré-hash.
- **Corrida no token de definição de senha** — item citado pelo PM. Risco: o token é de uso único, mas dois pedidos concorrentes podem passar pela checagem antes de qualquer um marcar o token como usado. A marcação de uso precisa ser atômica no banco. Confirmar a implementação atual antes de dar o item como fechado.

---

## 7. Backlog (fora das nove entregas)

- **Recuperação de senha do aluno.** Fora do escopo do PDF, mas o login de aluno em produção vai precisar. Item próprio.
- **Limpeza do histórico do `.chrome-pdf-profile/`.** O commit `92b959a` ("Presentation changes", Gustavo Santos Steluti, 25/05/2026) versionou um perfil de Chrome descartável, com 162 arquivos e 9,8 MB. **Diagnóstico medido:** os cofres estão vazios (0 logins, 0 cookies, 0 autofill, 0 cartões) e não há nenhum padrão de chave nos 162 arquivos. O que vaza é o nome de usuário do Windows num caminho de arquivo, um token de device do media router e um hash de cookie do Google. **Os cofres vazios baixam a urgência, mas não anulam o problema.** O conteúdo já está público em `origin/payment-system`. **Decisão do grupo, não deste time. Não executar**, nem se parecer seguro: reescrever histórico e fazer force-push numa branch do Gustavo é decisão do grupo, com o Gustavo participando. Diagnóstico completo no `HANDOFF_TDD.md`, seção 11.
- **D4, D6, D7** — dívidas do harness de e2e (seção 6 acima).

---

## 8. Notas de consistência

- O `papeis_tdd.md` e a seção 5 do `HANDOFF_TDD.md` ainda carregam a frase "nunca fazer push" no texto original. Ela está **revogada pela D30**. O `HANDOFF_TDD.md` já aponta para o log.
- A seção 9 do `HANDOFF_TDD.md` foi corrigida nesta versão. Os comandos completos, com variáveis de ambiente, estão no `AGENTS.md`, seção 6.
- A árvore de trabalho de `feature/fase2-tdd` deve estar limpa no fim de cada entrega. Qualquer alteração de outra autoria encontrada na árvore precisa ser identificada antes de qualquer commit.
