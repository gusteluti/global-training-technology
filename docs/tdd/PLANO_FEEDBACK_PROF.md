# Plano — feedback da professora e básicos de SaaS (19/10/2026)

Origem: conversa com a professora e mensagens do grupo de 19/10/2026. Ela disse que o projeto "está ficando bom, mas faltam coisas básicas de SaaS, travas necessárias e o que vai fazer falta no dia a dia do usuário".

Base: `main` e `feature/fase2-tdd` em `1d9d9ef` (PR #2 + commit "alteracoes 07/10" do Victor).

Processo: o mesmo do `AGENTS.md`. Cada item vira entrega com sub-branch, red, verde, e2e e checklist de 9 itens. As perguntas marcadas **[PM]** são de política e precisam de resposta antes do red da entrega. Ao lado de cada uma está a recomendação do orquestrador.

---

## 0. Antes de tudo: higiene (urgente)

| # | Problema | Ação |
|---|---|---|
| H1 | **`chat1.json` (raiz, 11 mil linhas) é uma exportação de sessão do Kiro e contém o `.env` local do Victor**: `MERCADO_PAGO_WEBHOOK_SECRET`, `JWT_SECRET_KEY`, `ADMIN_TOKEN_SECRET` e senhas `admin123`/`financ123`/`suporte123`. O arquivo está no `origin` **público**, na `main`. | Trocar esses valores em todo ambiente que os usa. Remover o arquivo da árvore e colocar `chat*.json` no `.gitignore`. Reescrever o histórico exigiria force-push, que é proibido (D30), então trocar os segredos é o que resolve. |
| H2 | O commit do Victor (checkout do aluno logado `POST /api/student/checkout`, tela `/catalogo` e `PAYMENTS_MOCK`) entrou **sem teste** e sem passar pelo ciclo TDD. | Testes de caracterização: o aluno vem do JWT (IDOR), funcionário recebe 403, sem token recebe 401, o preço vem do servidor e o mock fica desligado por padrão. |
| H3 | `PAYMENTS_MOCK=1` libera curso pago sem pagamento. Hoje basta uma variável ligada por engano em produção. | Uma trava: o mock só funciona com uma segunda condição de ambiente de desenvolvimento, aparece no `/health` e registra a compra na auditoria como `mock`. A variável entra no `.env.example` e no `AGENTS.md` §6.1. |

---

## 1. Feedback do grupo → entregas

### F1 — Excluir curso só sem alunos (trava)
**Hoje:** `DELETE /api/admin/course/{id}` apaga o JSON mesmo com matrículas e pagamentos. As matrículas ficam órfãs e o recibo e os dashboards perdem o nome do curso. A turma já tem essa trava (409 `ERR_TURMA_COM_MATRICULAS`); o curso, não.
**Entrega:** 409 com mensagem clara quando existir matrícula; o botão "Excluir" fica desabilitado na tela com o motivo ao lado; a tentativa bloqueada vai para a auditoria.
- **[PM]** Quais status contam? *Rec.:* todos (`pending`, `active`, `cancelled`, `refunded`). Pagamento e recibo dependem do curso para sempre.
- **[PM]** No lugar de excluir, oferecer **"Despublicar/arquivar"** (some do catálogo e do chat, mas o aluno ativo continua com acesso)? *Rec.:* sim. Isso é o básico de SaaS para não perder histórico.

### F2 — Horário em GMT-3 (e locale pt-BR em tudo)
**Hoje:** o SQLite grava `CURRENT_TIMESTAMP` em UTC e a tela mostra o texto cru (`audit-logs.component.html:23`). O problema não é só da auditoria: pagamentos, chat, recibo PDF, "Última conversa" e a série por dia da E7 (`per_day` em UTC, que já está nas dívidas) têm o mesmo defeito.
**Entrega:** o banco continua gravando UTC. A API devolve ISO 8601 com `Z`. O Angular registra `LOCALE_ID` como `pt-BR` (`registerLocaleData`) e formata as datas no fuso `America/Sao_Paulo`, no padrão `dd/MM/yyyy HH:mm`. O recibo PDF e o agrupamento por dia usam o mesmo fuso.
- Decisão de forma (orquestrador). O fuso fica fixo em `America/Sao_Paulo`, sem fuso por usuário.

### F3 — Ver, aluno por aluno, os cursos e a turma
**Hoje:** o dashboard de alunos só mostra contagens (`get_students_overview`). O aluno também não vê a própria turma (dívida das Turmas e da D2).
**Entrega:**
- Funcionário: clicar no aluno abre o detalhe (`GET /api/dashboard/alunos/{id}`) com as matrículas (curso, turma, status, data), os pagamentos e as conversas do chat (contagem e última).
- Aluno: o cartão do curso em `/student` mostra a turma e a data de início.
- **[PM]** O Suporte vê valores pagos no detalhe? *Rec.:* não, só o status. Valor fica para Financeiro e Gestão, como já é no RBAC.

### F4 — Painel: cursos disponíveis e alunos matriculados em cada um
**Entrega:** no dashboard de cursos, clicar no curso abre a lista de alunos (nome, e-mail, turma, status, data), com filtro por turma e status e exportação CSV. O endpoint `GET /api/admin/enrollments?course_id=` já existe para Gestão; falta a tela e a regra por perfil.
- Mesma pergunta de perfil da F3.

### F5 — Chat do curso mostra as turmas e oferece a matrícula
**Depende de:** turma escolhida no checkout. Hoje a turma só é atribuída depois, pela Gestão (dívida das Turmas).
**Entrega:**
1. `GET /api/courses/{id}/turmas` público, com as turmas abertas e as **vagas restantes**, sem dado de aluno.
2. O checkout recebe `class_id` e faz a trava de capacidade de forma **atômica** (turma lotada devolve 409 e não vende).
3. O chat do curso lista as turmas, pergunta qual faz mais sentido (horário, data) e devolve uma **ação estruturada** (`{type: "enroll", course_id, class_id}`), não um link escrito pelo LLM. A tela desenha o botão "Matricular".
4. Botão sem login leva ao cadastro/login e volta para o checkout. Com login, vai direto ao checkout do aluno.
- **[PM]** Quando a turma lota com o pagamento pendente, quem paga por último perde a vaga ou a vaga fica reservada? *Rec.:* reserva a vaga por 30 min a partir do checkout e libera se o pagamento não for aprovado.
- Segurança (E6): o filtro de saída valida que a `class_id` da ação existe e tem vaga. O LLM não inventa turma.

### F6 — Handoff para o WhatsApp quando a IA estiver acabando os tokens
"Acabando os tokens" pode significar três coisas diferentes, e o gatilho deve cobrir as três:
- (a) a **conversa** ficou longa demais (orçamento de tokens por sessão, medido com o `usage` que a E7 já grava);
- (b) a **cota/limite do Groq** estourou (429, ou `LLM_UNAVAILABLE` repetido);
- (c) o bot **não está resolvendo**: N mensagens "não compreendidas" seguidas, ou o usuário pede um humano.

**Entrega:** a resposta do chat ganha uma ação `{type: "handoff", url}` com o link `https://wa.me/<número>?text=<resumo>`. O número vem da configuração e não é escrito pelo LLM. A E7 passa a contar a **taxa de handoff** por motivo.
- **[PM]** Número do WhatsApp e texto pré-preenchido. *Rec.:* o texto leva curso e tema, **sem** dado pessoal e sem a conversa inteira.
- **[PM]** Limiares. *Rec.:* 80% do orçamento da sessão, 2 falhas seguidas do LLM, 3 "não entendi" seguidos.

### F7 — Criar curso a partir de um anexo
**Entrega:** a Gestão envia um arquivo e o sistema **preenche o formulário de cadastro** como rascunho. A pessoa revisa e salva. O anexo nunca publica o curso direto.
- Formatos: JSON no modelo dos cursos (validação direta) e PDF/DOCX de ementa, com extração pelo LLM em saída estruturada validada pelo mesmo schema do admin.
- Travas: limite de tamanho (ex.: 5 MB), tipo conferido pelo conteúdo (não só pela extensão) e o texto do anexo tratado como dado não confiável (injeção indireta, mesmo padrão da E6). O upload vai para a auditoria.
- **[PM]** Quais formatos entram na primeira versão? *Rec.:* JSON + PDF. DOCX depois.

---

## 2. Básicos de SaaS que ainda faltam (levantamento do orquestrador)

Conferidos no código em 19/10/2026.

### Travas (o sistema deixa fazer o que não devia)
| # | Lacuna | Evidência | Proposta |
|---|---|---|---|
| S1 | **Comprar o mesmo curso duas vezes** | `create_enrollment` insere sem checar | 409 se já houver matrícula `active`; se houver `pending`, retomar o pagamento existente em vez de criar outro |
| S2 | **Sem limite de tentativas de login** (aluno e funcionário) | não há rate limit em `auth.py` nem em `security.py` | bloqueio temporário por conta + IP após N falhas, com a auditoria da E8 |
| S3 | **Funcionários vêm de variáveis de ambiente** | `ADMIN_PASSWORD`, `FINANCIAL_PASSWORD`… | gestão de usuários internos: convidar, trocar perfil, **desativar** sem apagar |
| S4 | **Não dá para desativar um aluno** | `users` não tem campo de ativo | status da conta + JWT recusado para conta inativa |
| S5 | **Token continua valendo depois da troca de senha** | dívida da recuperação de senha | versão de token por usuário (`token_version`) |
| S6 | **Pagamento `pending` fica pendente para sempre** | sem expiração | expirar em X dias → `cancelled`; o aluno pode retomar ou cancelar |
| S7 | **Ações destrutivas sem confirmação** na tela | excluir curso/turma, reembolsar | modal de confirmação com o nome do item |
| S8 | **Turma ultrapassa a capacidade por webhook** | dívida das Turmas | resolvido junto com a F5 |
| S9 | **Sessões anônimas do chat sem teto e sem rate limit** | dívida da E6 | teto + limite por IP; o checkout também ganha limite |

### Dia a dia (vai fazer falta para o usuário)
| # | Lacuna | Proposta |
|---|---|---|
| U1 | Tabelas sem busca, filtro e paginação (alunos, pagamentos, auditoria) | busca por nome/e-mail, filtros e paginação no servidor |
| U2 | Sem exportação | CSV de alunos por curso/turma e do financeiro (só Financeiro e Gestão) |
| U3 | Aluno não edita o perfil nem troca a senha logado | `/student/perfil` com nome, telefone e "trocar senha" (pede a senha atual) |
| U4 | Matrícula manual/cortesia pela Gestão (pagou por Pix fora, bolsa) | matrícula `active` com motivo obrigatório e auditoria |
| U5 | Aluno não pede cancelamento | "Solicitar cancelamento" dentro de 7 dias (direito de arrependimento, CDC art. 49) → fila do Financeiro |
| U6 | E-mail real (hoje vai para arquivo, D13) | SMTP: confirmação de compra, link de senha, aviso de início da turma |
| U7 | LGPD | aceite de termos e privacidade no cadastro; aviso no chat de que a conversa é gravada; o aluno exporta e pede exclusão dos dados |
| U8 | Turma sem datas visíveis e sem tela de edição/exclusão | início/fim e horário na turma; tela de edição (dívida das Turmas) |
| U9 | Logout e expiração de sessão sem aviso | aviso "sua sessão expirou" e volta ao login preservando a rota |

---

## 3. Ordem proposta

Uma entrega por vez, como sempre. A ordem segue dependência e risco.

| Onda | Entregas | Por quê |
|---|---|---|
| **0** | H1, H2, H3 | segredo publicado e pagamento grátis possível: risco real agora |
| **1** | F1 (+ arquivar), F2, S1, S7 | travas pedidas pelo grupo, pequenas e independentes |
| **2** | F3, F4, U1, U2 | visão do admin pedida pelo grupo; reaproveitam os mesmos endpoints e tabelas |
| **3** | F5 (turma no checkout + chat com botão), S8, U8 | dependem uma da outra; maior entrega do plano |
| **4** | F6 handoff WhatsApp | depende da E7 (`usage`) e da ação estruturada criada na F5 |
| **5** | F7 curso por anexo | isolada; depende do schema do admin (L2) |
| **6** | S2, S3, S4, S5, S6, S9, U3, U4, U5, U9 | o que transforma o sistema em SaaS operável |
| **7** | U6 SMTP, U7 LGPD | dependem de infraestrutura (conta de e-mail) e de texto jurídico |

Se o prazo do TCC apertar, o corte recomendado é: ondas 0 a 4 completas, F7 só com JSON, e da onda 6 só S2 e S4.

---

## 4. Respostas que destravam o início

1. F1: todos os status bloqueiam a exclusão? Entra o "arquivar"?
2. F3/F4: o Suporte vê valores?
3. F5: reservar a vaga por 30 min no checkout?
4. F6: número do WhatsApp, texto pré-preenchido e limiares.
5. F7: só JSON + PDF na primeira versão?
6. H1: quem troca os segredos e onde eles estão em uso.
