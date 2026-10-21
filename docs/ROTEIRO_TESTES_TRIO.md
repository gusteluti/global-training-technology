# Roteiro de testes manuais — Global Training (para o trio)

Objetivo: conferir no navegador o que foi feito depois do feedback da professora e os usos mais comuns do sistema.
Anote em cada caso **OK** ou **FALHOU** e, se falhar, o que apareceu na tela (print ajuda muito).

## Antes de começar

- Rode o sistema conforme o passo a passo enviado no grupo (backend + `npm start`). Abre em http://localhost:4200.
- No `backend/.env`, deixe `APP_ENV=development` e `PAYMENTS_MOCK=1` (a compra é aprovada na hora, sem pagar).
- Contas: Gestão, Financeiro e Suporte são as do `.env` (`ADMIN_EMAIL`, `FINANCIAL_EMAIL`, `SUPPORT_EMAIL` e as
  senhas). Alunos você cria em **Cadastro** (use dois: "Aluno A" e "Aluno B").
- Links de "definir senha" e convites vão para o arquivo do `PASSWORD_LINK_OUTBOX` (não há e-mail real ainda).
- Use uma janela anônima para o segundo usuário, para não misturar os logins.

---

## Parte 1 — O que foi feito a partir do feedback

### Cursos e turmas (Gestão)
| # | Passos | Resultado esperado |
|---|---|---|
| 1.1 | Cadastro de cursos → crie um curso. Em Cursos → Gerenciar turmas, crie uma turma com início, término, horário (ex.: "Seg e Qua, 19h às 22h") e capacidade 2. | Turma aparece em "Turmas por curso" com período e horário. |
| 1.2 | Na turma, clique **Editar**, mude o nome e o horário, salve. | Linha atualizada sem recarregar. |
| 1.3 | Edite colocando término antes do início. | Mensagem "A data de término não pode ser anterior ao início." e nada muda. |
| 1.4 | Exclua uma turma sem alunos (confirme). Depois tente excluir uma turma com aluno. | A vazia some; a com aluno mostra que não pode ser removida. |
| 1.5 | Cadastro de cursos → tente **Excluir** um curso que já tem aluno. | Botão desabilitado com o motivo; existe **Arquivar**. |
| 1.6 | **Arquive** esse curso. Veja como aluno o Catálogo e a área do aluno. | Some do catálogo; quem já tinha matrícula ativa continua vendo o curso e os materiais. |
| 1.7 | Cadastro de cursos → **Criar a partir de arquivo** com um PDF de ementa (ou um JSON de curso). | Formulário de novo curso abre preenchido como rascunho, com avisos; o curso só existe depois de Salvar. |

### Compra, turma e chat (Aluno)
| # | Passos | Resultado esperado |
|---|---|---|
| 1.8 | Aluno A → Catálogo → escolha a turma do 1.1 e compre. | Matrícula ativa; o cartão do curso mostra "Turma: …", início, horário e término. |
| 1.9 | Tente comprar o mesmo curso de novo. | "Você já está matriculado". |
| 1.10 | Aluno B compra a mesma turma até lotar (capacidade 2). Com um terceiro aluno, abra o catálogo. | A turma aparece "(lotada)" e não dá para escolher. |
| 1.11 | No chat do aluno, pergunte sobre o curso pelo nome. | O assistente fala das turmas e aparecem botões "Matricular na turma …"; o botão leva ao catálogo com a turma já escolhida. |
| 1.12 | No chat, escreva "quero falar com um atendente". | Aparece o botão "Falar com um atendente no WhatsApp" (só se `WHATSAPP_HANDOFF_NUMBER` estiver no `.env`). |
| 1.13 | Sem estar logado, abra o chat da landing e pergunte sobre um curso; clique no botão de matrícula. | Vai para o login e, depois de entrar como aluno, volta ao catálogo com a turma escolhida. |

### Visão do painel
| # | Passos | Resultado esperado |
|---|---|---|
| 1.14 | Gestão → Alunos → clique no nome do Aluno A. | Detalhe com cursos, turma, status em português, pagamentos e conversas. |
| 1.15 | Mesma tela logado como **Suporte**. | Mostra tudo menos valores em R$. |
| 1.16 | Gestão → Cursos → clique no nome do curso. Use os filtros de status e turma. Clique **Exportar CSV**. | Lista de alunos filtra; o CSV abre no Excel com acentos certos. |
| 1.17 | Confira datas na Auditoria e no Financeiro. | Horário de Brasília (dd/mm/aaaa HH:mm). |

---

## Parte 2 — Uso natural do sistema

### Aluno
| # | Passos | Resultado esperado |
|---|---|---|
| 2.1 | Cadastro → entrar → área do aluno. | Cabeçalho "Olá, <nome>!"; resumo com cursos ativos e total investido. |
| 2.2 | **Meu perfil**: mude nome e telefone; troque a senha (teste primeiro com a senha atual errada). | Senha atual errada: "Senha atual incorreta."; com a certa: "Senha alterada." e continua logado. |
| 2.3 | "Esqueci minha senha" com o e-mail do aluno; abra o link do outbox. | Consegue definir nova senha e entrar. |
| 2.4 | Em um pagamento aprovado, clique **Ver recibo** e **Baixar PDF**. | Recibo com valor, curso, forma de pagamento e data. |
| 2.5 | No cartão de um curso comprado hoje, **Pedir cancelamento** com um motivo. | Status "Cancelamento em análise". |
| 2.6 | Erre a senha 6 vezes seguidas no login. | Na 6ª: "Muitas tentativas. Tente novamente em alguns minutos." |

### Gestão
| # | Passos | Resultado esperado |
|---|---|---|
| 2.7 | Aba **Equipe**: convide uma pessoa como Suporte; defina a senha pelo link do outbox e entre com ela. | Entra e só vê as abas do Suporte. |
| 2.8 | Troque o perfil dessa pessoa para Financeiro. Ela recarrega a página. | Ela precisa entrar de novo e passa a ver o Financeiro. |
| 2.9 | Desative essa pessoa e tente entrar com ela. Tente desativar a própria conta. | Login: "Sua conta está desativada…"; própria conta não tem botão de desativar. |
| 2.10 | Alunos → detalhe → **Desativar conta** de um aluno. Na aba do aluno, recarregue. | Aluno cai no login com "Sua sessão expirou. Entre novamente." |
| 2.11 | Cursos → lista de alunos do curso → **Matrícula manual** com e-mail novo, valor 0 e motivo "Bolsa". | Aluno aparece como ativo; conta nova recebe link de senha no outbox. |
| 2.12 | **Auditoria**: busque por "staff" ou "course" e filtre por data. | Os eventos feitos acima aparecem com quem fez. |

### Financeiro
| # | Passos | Resultado esperado |
|---|---|---|
| 2.13 | Financeiro → Solicitações de cancelamento: **Recusar** o pedido do 2.5 com motivo. | Aluno vê "Cancelamento recusado: <motivo>". |
| 2.14 | Aluno pede de novo; Financeiro **Aprova e reembolsa**. | Pagamento "Reembolsado"; aluno perde o acesso ao material. |
| 2.15 | Busque um aluno por e-mail, filtre por status e **Exporte CSV**. | Lista filtrada; CSV correto. |
| 2.16 | Tente abrir a aba Cadastro de cursos ou Equipe. | Não aparecem para o Financeiro. |

### Suporte
| # | Passos | Resultado esperado |
|---|---|---|
| 2.17 | Entre como Suporte e percorra as abas. | Vê Alunos, Cursos e Observabilidade de IA; não vê Financeiro, valores, Cadastro de cursos, Auditoria nem Equipe. |
| 2.18 | Observabilidade de IA. | Números do chat, sem custo em dólar; cartão "Encaminhamentos ao WhatsApp". |

---

## Como reportar
Mande no grupo: número do caso, OK/FALHOU, print e o que esperava. Erros de terminal (backend ou `npm start`) também ajudam.
