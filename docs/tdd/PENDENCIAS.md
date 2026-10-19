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
| **E4 — Histórico financeiro + recibos** | `GET /api/student/payments` e `GET /api/student/payments/{id}/receipt` (recibo JSON). Recibo alheio e inexistente devolvem o mesmo 404; consultas filtradas pelo dono do JWT. Histórico e recibo na tela `/student`. Feita direto em `feature/fase2-tdd`, sem sub-branch, por orientação do PM. Fechada pelo PM em 05/10/2026 (D34). | testes `b27bd6d`; backend `f9f20cc`; frontend `da6de8e` |
| **E5 — Chatbot autenticado** | `POST /api/student/chat` e `GET /api/student/chat/history`: o chatbot recebe nome do aluno e cursos `active`, o histórico fica persistido em `chat_messages` e as 10 últimas mensagens vão ao LLM. Chat "Assistente virtual" em `/student`; dashboard de alunos com "Mensagens no chat" e "Última conversa". Entregue 06/10/2026; **aguardando validação do PM** (D37). | testes `7e030c7`, `eeaed3b`, e2e `cf37572`, `970d2c1`; backend `ed5fa3b`; frontend `2421a9c`, `b83e378` |
| **E6 — Segurança de LLM** | Sessão anônima emitida pelo servidor (landing guarda o id); filtro de entrada (injeção direta, PT e EN); política e dados não confiáveis delimitados no prompt (injeção indireta: nome do aluno, base do curso); filtro de saída (desconto, valor fora do catálogo, vazamento de prompt); falha do LLM sem texto de exceção e sem persistir; limite de 2000 caracteres. Obrigatórios (a) desconto indevido e (b) vazamento entre sessões provados. Entregue 06/10/2026; **aguardando validação do PM** (D41). | testes `481b742`, `fb3744d`, `7208da8`, e2e `a00eaff`; backend `8bbd34a`; landing `7e2f9bd` |
| **E7 — Observabilidade de IA** | `usage` do Groq persistido (`ai_usage`), interações e desfechos (`ai_interactions`), custo em USD, latência, resolução, conversão de atendimento, tópicos não compreendidos (só chat anônimo, mascarados), série por dia. Suporte não vê custo. Tela `ai-observability` atualizada. Sobrevive a restart. Entregue 06/10/2026; **aguardando validação do PM** (D44). | testes `6b27fc4`, e2e `9a61216`; backend `b36c188`; frontend `530ea3a` |
| **E8 — Auditoria com usuário responsável** | Trilha com a pessoa responsável (id, e-mail, nome, perfil, vindos do token), alteração estruturada antes/depois, entidade, estampa de tempo, login de funcionário (sucesso e falha), append-only por trigger, filtros e limite no endpoint, sem rotas de escrita. Tela `audit-logs` atualizada. Entregue 06/10/2026; **aguardando validação do PM** (D47). | testes `8ebb6dd`, e2e `162b8fd`; backend `56f91be`; frontend `8131b2e` |
| **E9 — Hardening de pagamento** (acréscimo do PM, fora do PDF) | Assinatura do webhook (fail closed), validação de tópico e id, conferência de valor e moeda, máquina de estados e transição atômica, efeitos colaterais uma vez só, índice único de `transaction_id`, `charged_back` revoga acesso, reembolso só de pagamento aprovado e idempotente, CORS por lista, erro do gateway sem vazar corpo. Entregue 06/10/2026; **aguardando validação do PM** (D50). | testes `a9e9042`, `578f6ea`, `99ca939`; backend `feaa9db` |
| **Turmas (lacuna do dashboard de cursos)** | Tabela `classes`, matrícula atribuível a uma turma por Gestão, capacidade, contagens por turma e "sem turma" no dashboard, auditoria da E8, tela de gestão (Gestão) e números (todos os perfis). Entregue 06/10/2026; **aguardando validação do PM** (D55). | testes `eb6acf7`, e2e `1a42c8b`; backend `21218b8`; frontend `71a7c63` |
| **Cadastro de cursos no Angular + interceptor** | Aba "Cadastro de cursos" (só Gestão) com criar, editar e excluir cursos, listas por linha, FAQ, materiais com validação de URL, trilha da E8; interceptor só anexa o token a `/api/admin/`, `/api/dashboard/`, `/api/student/` e `/api/payments/refund/`. Entregue 06/10/2026; **aguardando validação do PM** (D57). | e2e `570f25e`, `cd53fc9`; frontend `74c1066` |
| **Recuperação de senha do aluno** (backlog) | Pedido de link com resposta uniforme, token `reset` de 1 h, limite de 3 por hora, uso único e atômico, aviso de senha alterada, telas `/esqueci-senha` e `/redefinir-senha`. Entregue 06/10/2026; **aguardando validação do PM** (D62). | testes `0e9a040`, e2e `77acad7`; backend `b7b1390`; frontend `dfbd6c2` |
| **Recibo em PDF** (opcional) | `GET /api/student/payments/{id}/receipt.pdf` (PDF mínimo em Python puro, sem dependência nova), só `approved`/`refunded`, mesmas regras de acesso do recibo JSON, `receipt_pdf_url` na lista, botão "Baixar PDF". Entregue 06/10/2026; **aguardando validação do PM** (D65). | testes `3687b02`, e2e `c0eb94d`; backend `553b9d7`; frontend `675cbd1` |
| **D1 — Design da landing na SPA** (pedido do PM, 07/10/2026) | Casca com barra escura, logo GT e rodapé; tokens, fontes e componentes da landing em todas as telas Angular; Bootstrap e fontes sem CDN. Backup prévio em `backup/fase2-tdd-2026-10-07` (tag `backup-fase2-tdd-2026-10-07`); merge da `main` sem efeito (já contida). Entregue 07/10/2026; **aguardando validação do PM** (D66). | e2e `34d846a`; frontend `b1ecf40`, `6702f56`, `07ba7e7` |
| **D2 — Nova Área do Aluno** (pedido do PM, 07/10/2026; escopo 1.1, RF21/RF22) | `/student` refeita no design da landing: cabeçalho com e-mail do token e atalhos, resumo (cursos ativos, pagamentos pendentes, total investido), cartões de curso com data e materiais só com matrícula ativa, status de pagamento e recibo em português, histórico em cartões no celular, chat em bolhas. Sem mudança de API. Entregue 07/10/2026; **aguardando validação do PM** (D67). | e2e `0b4b45e`; frontend `e5a2de5` |

Os dois obrigatórios da E3 (**IDOR** e **material só com matrícula ativa**) foram provados por suíte e por sondagem independente de HTTP (38/38). Detalhes no `HANDOFF_TDD.md`, seção 2.

Push de `feature/fase2-tdd` e `feature/fase2-tdd-e3-painel-materiais` feito em 05/10/2026 (D33). `main` intocada.

E4: regressão integral de backend registrada depois do fechamento — **88 passed** (81 anteriores + 7 da E4). O e2e de navegador da E4 não tem saída registrada no repo; o fechamento é do PM (D34). Recibo em PDF segue opcional e não bloqueante.

---

## 2. Em andamento

Modo autônomo (D40): ver `docs/tdd/RELATORIO_NOITE.md`. E5 (D37), E6 (D41), E7 (D44), E8 (D47) e E9 (D50) entregues, aguardando validação do PM. Dívidas de segurança resolvidas (D52); turmas entregues (D55). Cadastro de cursos no Angular e interceptor entregues (D57). Dívidas de harness resolvidas (D59); recuperação de senha entregue (D62); recibo em PDF entregue (D65). **Fila da noite (D40) concluída.** Design da landing aplicado à SPA (D66) e nova Área do Aluno (D67), 07/10/2026.

---

## 3. A fazer — escopo de cada entrega

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
- ~~Dashboard de cursos sem o conceito de turma.~~ **Resolvido (D55).**
- **"Histórico de interações" no dashboard de alunos** só mostra o total de sessões, porque o chat ainda é **anônimo**. Resolvido na **E5** para o chat autenticado (contagem e data da última conversa por aluno); o chat anônimo da landing page segue fora desse histórico.
- **Observabilidade de IA vivia em memória.** Resolvido na **E7** (persistida em banco, D44).

**Versão antiga, superada:** `feature/fase2-painel-administrativo` (`aa619ac`, 09/09) é a **versão antiga** dessa mesma área, em `admin.html` com HTML e JavaScript puros. Foi superada pela versão Angular. **Não é trabalho a aproveitar**; serve só de histórico. O `frontend/admin.html` segue versionado como **legado**. O cadastro de cursos foi portado para o Angular (D57); o legado só pode sair do repo por decisão do grupo.

---

## 5. Quatro decisões do PM sobre lacunas do escopo

Tomadas pelo PM. Anteriores às D21 a D26 do log. Cobrem o que o documento de escopo exige mas não define.

1. **Conta do aluno nasce após a compra**, por link de definição de senha (o pagamento já valida o e-mail). **Cadastro direto também disponível.**
2. **Status de matrícula é um conjunto fechado:** `pending`, `active`, `cancelled`, `refunded`.
3. **Materiais didáticos:** campo opcional `materials: [{title, url, type}]` no JSON do curso, visível **só com matrícula ativa**.
4. **Recibo:** primeiro endpoint JSON; PDF depois, se houver tempo. **Não é bloqueante.**

---

## 6. Dívidas técnicas abertas

- ~~D4 — e2e: 27 vs 29 checks. Os dois checks de reembolso pela tela são pulados com banco vazio. O harness precisa semear um pagamento pendente antes de rodar. Sem mudança de produção para isso.~~ **Resolvido (D59).**
- ~~D6 — pendente: alteração em `frontend/e2e/test_admin_angular.py` ainda sem commit de follow-up.~~ **Resolvido (D59).**
- ~~D7 — harness: o seed do e2e grava pagamentos de teste em `backend/db.sqlite` de desenvolvimento, e o acúmulo se repete a cada execução. Correção futura: subir o backend com `DB_PATH` isolado.~~ **Resolvido (D59).**
- ~~D10 — a confirmar: confirmar que o teste de duas compras do mesmo curso no mesmo segundo está commitado e verde.~~ **Resolvido (D59).**
- **D13 — envio de link:** não há servidor de e-mail. A função `send_password_setup_link` grava o link em arquivo de saída de **desenvolvimento, fora do repo**. Troca por SMTP real é trabalho futuro.
- ~~Defeito latente em `PUT /api/admin/update-course`: usa o mesmo `CourseInput` em que `materials` tem default `[]`. Quem editar um curso sem reenviar `materials` apaga os materiais em silêncio. Hoje nenhuma tela chama esse endpoint, então é risco latente. Vira defeito real quando a área administrativa ganhar edição de curso. Fora do escopo da D28; precisa de decisão do PM.~~ **Resolvido (D52).**
- **(Resolvido na E6, D38) E5 — erro do LLM vira mensagem do bot.** Se o Groq falhar, `CourseAgent` e `_answer_general_question` devolvem o texto "Desculpe, ocorreu um erro... {exceção}" (comportamento herdado do `/api/chat`). No chat autenticado esse texto é **persistido** como mensagem do assistente, entra no contexto das próximas perguntas e pode expor detalhe da exceção ao aluno. Tratar na E6 (política: o que o aluno vê e se erro é gravado).
- **(Resolvido na E6, D38) E5 — sem limite de tamanho da mensagem** no `POST /api/student/chat` (nem `maxlength` no campo). Avaliar na E6 (custo e abuso).
- **E6 — dívidas:** sessões anônimas em memória sem teto (cresce sem limite) e sem limitação de taxa; filtro de saída bloqueia parcelamento legítimo ("12x de R$ 19,33"); filtro de entrada é heurístico (paráfrase e outros idiomas podem passar; a contenção real é o filtro de saída); `backend/test_api.py` e `DOCUMENTACAO_TECNICA_TCC.html` ainda mostram o `session_id` fixo. Textos fixos escolhidos pelo orquestrador (D38): `INPUT_BLOCKED`, `OFFER_BLOCKED`, `LLM_UNAVAILABLE`, `TOO_LONG`.
- **E7 — dívidas:** preços padrão do Groq a conferir; custo só em USD; `per_day` em UTC; `total_sessions` inclui sessões só com mensagem bloqueada; rótulos de tela escolhidos pelo orquestrador (D44).
- **E8 — dívidas:** alteração fica sem trilha se a gravação do evento falhar (500 genérico); reembolsos simultâneos podem duplicar evento; falha de login legado vira `role='system'` sem pessoa; sem limitação de taxa em eventos de falha de login; eventos anteriores à E8 sem ator.
- **E9 — dívidas:** reenvio do link de senha se a entrega falhar; webhook bloqueia o loop; base antiga com `transaction_id` duplicado sem índice; botão Reembolsar visível para não aprovado (409); origem `null` (`file://`); sem limitação de taxa no checkout nem estorno real; `MERCADO_PAGO_WEBHOOK_SECRET` obrigatório no ambiente.
- **Turmas — dívidas:** edição e exclusão de turma sem tela; o aluno não vê a própria turma; sem atribuição automática nem escolha no checkout; matrícula reativada por webhook pode ultrapassar a capacidade.
- **L2 — dívidas:** duração na lista por N+1; rótulos escolhidos pelo orquestrador; título de material com `|`; `admin.html` segue como legado.
- **Recibo em PDF — dívidas:** linha truncada em 90 caracteres; sem logotipo nem numeração fiscal; status e forma de pagamento em valor bruto.
- **D1 — dívidas:** a landing estática segue no Google Fonts e com CSS próprio (não compartilha o `styles.css` da SPA); rótulos da casca escolhidos pelo orquestrador; nenhuma tela foi redesenhada além do que o CSS global alcança (exceto a área do aluno, D2).
- **D2 — dívidas:** o cabeçalho mostra o e-mail, não o nome (o JWT não traz o nome); o aluno continua sem ver a própria turma (dívida das Turmas); status de pagamento desconhecido aparece em valor bruto; textos escolhidos pelo orquestrador.
- **Recuperação de senha — dívidas:** JWT já emitido não é revogado; SMTP real; `href` absoluto no link "Ir para o login" de `definir-senha`; textos de erro escolhidos pelo orquestrador.
- **E5 — textos da tela escolhidos pelo orquestrador**, sem revisão do PM: "Assistente virtual", "Digite sua mensagem", "Enviar", "Nenhuma mensagem ainda. Pergunte algo ao assistente.", "Não foi possível carregar o histórico do chat.", "Não foi possível enviar a mensagem. Tente novamente.", e as colunas "Mensagens no chat" e "Última conversa".
- **E5 — e2e de E2 e E3 não reexecutados** depois de a E5 alterar `student-dashboard` (mesmo componente do "Meus cursos"). Backend: regressão 131 passed. O e2e antigo grava no `db.sqlite` de desenvolvimento (D7), por isso não foi rodado.
- ~~Interceptor HTTP do Angular — higiene.~~ **Resolvido (D57).**
- ~~bcrypt e o limite de 72 bytes — o item foi citado pelo PM. Contexto: o bcrypt ignora tudo depois de 72 bytes da senha. Senhas longas com o mesmo prefixo de 72 bytes ficam equivalentes. A política de senha (D14, mínimo de 8) não limita o máximo. Decidir se a política ganha limite superior ou um pré-hash.~~ **Resolvido (D52).**
- ~~Corrida no token de definição de senha — item citado pelo PM. Risco: o token é de uso único, mas dois pedidos concorrentes podem passar pela checagem antes de qualquer um marcar o token como usado. A marcação de uso precisa ser atômica no banco. Confirmar a implementação atual antes de dar o item como fechado.~~ **Resolvido (D52).**

---

## 7. Backlog (fora das nove entregas)

- ~~Recuperação de senha do aluno.~~ **Entregue (D62).**
- **Limpeza do histórico do `.chrome-pdf-profile/`.** O commit `92b959a` ("Presentation changes", Gustavo Santos Steluti, 25/05/2026) versionou um perfil de Chrome descartável, com 162 arquivos e 9,8 MB. **Diagnóstico medido:** os cofres estão vazios (0 logins, 0 cookies, 0 autofill, 0 cartões) e não há nenhum padrão de chave nos 162 arquivos. O que vaza é o nome de usuário do Windows num caminho de arquivo, um token de device do media router e um hash de cookie do Google. **Os cofres vazios baixam a urgência, mas não anulam o problema.** O conteúdo já está público em `origin/payment-system`. **Decisão do grupo, não deste time. Não executar**, nem se parecer seguro: reescrever histórico e fazer force-push numa branch do Gustavo é decisão do grupo, com o Gustavo participando. Diagnóstico completo no `HANDOFF_TDD.md`, seção 11.
- ~~D4, D6, D7 — dívidas do harness de e2e.~~ **Resolvidas (D59).**

---

## 8. Notas de consistência

- O `papeis_tdd.md` e a seção 5 do `HANDOFF_TDD.md` ainda carregam a frase "nunca fazer push" no texto original. Ela está **revogada pela D30**. O `HANDOFF_TDD.md` já aponta para o log.
- A seção 9 do `HANDOFF_TDD.md` foi corrigida nesta versão. Os comandos completos, com variáveis de ambiente, estão no `AGENTS.md`, seção 6.
- A árvore de trabalho de `feature/fase2-tdd` deve estar limpa no fim de cada entrega. Qualquer alteração de outra autoria encontrada na árvore precisa ser identificada antes de qualquer commit.
