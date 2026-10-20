# Relatório do modo autônomo — plano do feedback (D69)

Início: 19/10/2026. Fila: `docs/tdd/PLANO_FEEDBACK_PROF.md`. Atualizado ao fim de cada entrega.

## Entregas

| Entrega | Estado | Commits | Resultado |
|---|---|---|---|
| O0 — checkout do aluno + trava do mock | entregue | red `9dbd134`, D70 `622deb5`, backend `1deadb0` | O0 86/86; regressão 1051 passed; e2e O0 7/7 |
| F1 — trava de exclusão e arquivar curso | entregue | red `554d3ea`; backend `1be517d`, `cb8a1da`; front `2168826` | F1 55/55; regressão verde; e2e F1 11/11, L2 24/24, admin 33/33 |
| F2 — horário de São Paulo | entregue | red `c657d64`; backend `5b702cc`; front `07f54aa`; ajuste E5 `af121b1` | backend e regressão verdes; e2e F2 10/10 e telas tocadas verdes |
| S1 — compra duplicada | entregue | red `47a7172`; ajuste E1 `013949d`; backend `1f3dda6`; front `a67a700` | regressão verde; 8 e2e verdes |
| F3/F4 — aluno ↔ curso e turma do aluno | entregue | red `dbcc791`; backend `bec2701`; front `08d9ecc` | regressão verde; 6 e2e verdes |
| U1/U2 — busca, paginação e CSV | entregue | red `ec1388d`; backend `72a2d8d`; front `64eac03` | regressão 1220 passed; 6 e2e verdes |
| F5a — turma no checkout, reserva e lotação | entregue | red `14dcb11`; backend `4b6901d`; front `34cbc01` | regressão 1384 passed; 8 e2e verdes |
| F5b — chat com turmas e botão de matrícula | entregue | red `df50614`; backend `066a925`; front `cff3d11`; ajuste guarda `7a816d1` | regressão 1431 passed; 13 e2e verdes |
| F6 — handoff para o WhatsApp | entregue | red `74eadf7`; backend `1f93951`; front `6c5d50d` | regressão 1524 passed; 7 e2e verdes |
| F7 — curso a partir de anexo (JSON e PDF) | entregue | red `5acc911`; backend `89c22e8`; front `e7651db` | regressão 1591 passed; 4 e2e verdes |
| S2/S9/S10 — limite de tentativas, limite de taxa, id de curso | entregue | red `31b131b`; backend `8b9e222`; ajustes `03e998b`, `f5b425a` | regressão verde; 12 e2e verdes |
| S4/S5/U3/U9 — conta do aluno | entregue | red `ea05128`; backend `facd5ad`; front `cac20ce` | regressão 1725 passed; 14 e2e verdes |
| U4/S6 — matrícula manual e expiração de pendente | entregue | red `0b0c89b`; backend `370387f`; front `58acc06`; datas relativas `6845c02` | regressão verde; 6 e2e verdes |
| U5 — pedido de cancelamento em 7 dias | entregue | red `8df5c09`; backend `578b224`; front `d61d386` | regressão 1871 passed; 8 e2e verdes |

## Decisões de política tomadas sem o PM (para revisão)

- **O0:** o mock de pagamento só vale com `APP_ENV=development` (em qualquer outro ambiente é ignorado e segue o fluxo real). Na landing o evento do mock fica com responsável `system`.
- **D70:** os testes de chat usam um catálogo próprio; o curso `lua` apagado pelo Victor continua só nas fixtures de teste.
- **F1:** textos `Não é possível excluir: o curso tem alunos matriculados. Arquive o curso para tirá-lo do catálogo.`, `Este curso não está disponível para novas matrículas.`, `Tem alunos matriculados — arquive em vez de excluir.` e confirmações `Arquivar o curso "<nome>"?`. Excluir curso sem alunos remove junto as turmas vazias.
- **F2:** formato `dd/MM/aaaa HH:mm` nas telas de funcionário e só o dia na área do aluno; PDF sem segundos. Dívidas: receita mensal por mês UTC, datas do chat e antes/depois da auditoria ainda crus.
- **S1 (D72):** a landing responde 409 quando o e-mail já tem acesso ao curso. Isso revela a quem souber e-mail e curso que a matrícula existe (enumeração, cf. D21), em troca de não cobrar duas vezes. Link antigo pago pelo preço anterior depois de mudança de preço cai em `amount_mismatch` (E9). Busca por e-mail exata, sem normalizar caixa.
- **F3/F4:** a lista de alunos do curso não mostra valor na tela para nenhum perfil (a API manda para Gestão/Financeiro). Textos novos escolhidos pelo orquestrador/dev: "início em", "Alunos de <curso>", "Fechar", "Nenhum aluno neste curso." etc.
- **U1/U2 (D74):** exportação CSV só Gestão e Financeiro (Suporte 403); cada exportação vai para a auditoria. Financeiro e auditoria sem paginação na tela (só busca/filtro); mensagem de lista vazia com busca ativa continua a antiga. Busca das listas em memória (dívida de desempenho).
- **F5a/S8 (D75):** pagamento que chega depois de a reserva expirar, com turma lotada, ativa a matrícula **sem turma** e avisa a Gestão pela auditoria (`enrollment.class_overflow`). Turmas já iniciadas não são vendidas. Na disputa da última vaga, quem perde recebe 409 depois de uma preferência criada no gateway (não paga). Landing estática sem seleção de turma.
- **F5b (D76):** botões "Matricular na turma <nome>" / "Matricular no curso" (até 3); turmas todas lotadas → sem botão; aluno já ativo → sem botão. Visitante da landing é levado ao login e volta ao catálogo com a turma escolhida. O texto da instrução ao LLM é do orquestrador/dev.
- **F6 (D77):** texto do WhatsApp `Olá! Vim do assistente virtual da Global Training e gostaria de falar com um atendente sobre o curso <nome>/os cursos.`; label `Falar com um atendente no WhatsApp`; palavras de pedido de humano incluem "suporte" e "pessoa"; entrada bloqueada não recebe o link. **Para ligar em produção: definir `WHATSAPP_HANDOFF_NUMBER=<número do PM com DDI 55>` no `.env` do servidor (não no repo).**
- **F7 (D78):** dependência nova `pypdf` (rodar `pip install -r backend/requirements.txt`). Do PDF não vêm as instruções do assistente (injeção). Avisos de tipo inválido e de material descartado escritos pelo dev. A chamada ao LLM do rascunho não entra na observabilidade (E7).
- **S2/S9 (D79):** limites 5 por e-mail / 20 por IP em 15 min, chat 30/min, checkout 10/min; textos dos 429 do orquestrador. IP atrás de proxy reverso precisa de configuração (dívida). O PUT de curso ainda grava o `id` do corpo sem validar (não monta caminho).
- **S4 (D80):** aluno desativado vê `Sua conta está desativada. Fale com o suporte.` só com a senha certa; telefone 10–15 dígitos; textos do perfil escolhidos pelo dev ("Dados atualizados.", "Senha alterada." etc.).
- **U4/S6 (D81):** pendente expira em 7 dias; matrícula manual exige motivo (5–300) e vira pagamento aprovado `manual` (entra na receita). Dívida: o CSV do financeiro não expira pendentes antes de exportar; mensagem do 422 da tela cita só o motivo.
- **U5 (D82):** prazo de 7 dias contado da aprovação do pagamento (CDC art. 49); matrícula manual/cortesia não entra; aprovar = reembolso local (MVP, sem estorno real no gateway, como na E9). Textos dos botões e confirms escolhidos pelo dev.

## Paradas e itens pulados

- Observação O0: o `frontend/node_modules` local estava sem `@fontsource/barlow*` (instalado com `--no-save`). Em clone novo, rodar `npm ci`.
- O harness e2e (`servidor_e2e_e5/e7/h1`) ainda lê o catálogo real do bot (`c_e_c`, `python_profissional`); não quebra hoje.
- **Achado de segurança (F7):** `POST /api/admin/create-course` aceita `id` vindo do cliente sem validação; um `id` com `../` pode gravar o JSON fora de `backend/courses` (só Gestão). Tratado na entrega S10 da onda 6.
