# Relatório da noite (D40) — 06/10/2026 — **fila concluída**

Atualizado a cada entrega. Quem acordou: leia primeiro a seção "Decisões de política tomadas sem o PM".

## Verificação final do estado integrado (branch `feature/fase2-tdd`)
Rodada pelo orquestrador depois do último merge, uma execução por vez:
- Backend: **965 passed** (`cd backend && python -m pytest tests`, 26 min).
- Build Angular: limpo (`cd frontend && npx ng build`).
- E2E de navegador, todos verdes: admin 33/33, conta do aluno 8/8, painel do aluno 7/7, chat do aluno 11/11, dashboard de alunos 9/9,
  observabilidade 11/11, auditoria 17/17, turmas 16/16, cadastro de cursos 24/24, recuperação de senha 10/10, recibo em PDF 8/8, landing 8/8.
- Publicação: `feature/fase2-tdd` e uma branch por entrega estão no GitHub; a `main` nunca foi tocada; nenhum force-push; antes de
  cada push foi auditado que não subia `.env`, banco, perfil de navegador, `backend/courses` nem chave. Para o grupo: clone o
  repositório, entre em `feature/fase2-tdd` e siga o `AGENTS.md` (seção 6) para rodar.
- Observação: o `backend/db.sqlite` de desenvolvimento (ignorado pelo git) foi alterado pela suíte de backend, que abre esse arquivo no
  `init_db` do import (adiciona tabelas e colunas novas, sem apagar dados). Os e2e novos nunca o abrem.

## Fila e estado
| # | Item | Estado |
|---|---|---|
| 1 | E5 e E6 — chatbot autenticado e segurança de LLM | **entregues** (D37, D41): backend 271 passed, landing 8/8; mergeada e publicada |
| 2 | E7 — observabilidade de IA | **entregue** (D44): backend 348 passed, e2e 11/11; mergeada e publicada |
| 3 | E8 — auditoria | **entregue** (D47): backend 411 passed, e2e 17/17; mergeada e publicada |
| 4 | E9 — hardening de pagamento | **entregue** (D50): backend 596 passed, e2e anteriores verdes; mergeada e publicada |
| 5 | Dívidas de segurança (token, bcrypt, update-course) | **entregue** (D52): backend 669 passed; mergeada e publicada |
| 6 | Lacunas de produto: (a) turmas, (b) cadastro de cursos no Angular + interceptor — **concluído** | (a) **entregue** (D55): backend 828 passed, e2e 16/16; (b) **entregue** (D57): e2e 24/24, regressões de e2e verdes |
| 7 | Dívidas de harness (D4, D6, D7, D10) | **entregue** (D59): os 3 e2e antigos isolados; 33/8/7 checks; db.sqlite intacto |
| 8 | Backlog opcional: (a) recuperação de senha, (b) recibo PDF | (a) **entregue** (D62): backend 921 passed, e2e 10/10; (b) **entregue** (D65): backend 965 passed, e2e 8/8 |

## Decisões de política tomadas sem o PM (revisar na volta)
- **E6:** textos fixos que o usuário final vê (`INPUT_BLOCKED`, `OFFER_BLOCKED`, `LLM_UNAVAILABLE`, `TOO_LONG`), em D38.
- **E6:** conteúdo do filtro: bloqueia parcelamento legítimo ("12x de R$ ...") por ser valor fora do catálogo; limite de 2000 caracteres por mensagem.
- **E6:** falha do Groq no chat do aluno agora responde 502 e nada é gravado (antes virava mensagem do bot).
- **E7 (D42):** definição de `resolution_rate` e de `conversion` (conversão de atendimento: aluno que conversou e depois teve matrícula ativa); preços padrão do Groq são referência, conferir; Suporte não vê custo; tópicos não compreendidos só do chat anônimo (privacidade do aluno).
- **E8 (D45):** "dados cadastrais" interpretado como cadastro de cursos (não existe rota de edição de aluno); trilha append-only por trigger; login de funcionário (sucesso e falha) passa a ser auditado; o login administrativo legado não identifica pessoa e fica registrado como "Login administrativo (perfil)".
- **E8 (D47):** evento gravado depois da alteração; se a gravação falhar, 500 genérico e alteração sem trilha; falha de gravação em login derruba o login (500).
- **E9 (D48):** reembolso só de pagamento `approved` (antes aceitava `pending`): é regra de negócio nova; CORS restrito por lista (sem `*`, sem credenciais); webhook fail closed (503 sem segredo configurado); sem janela de tempo na assinatura (motivo na D48).
- **Dívidas de segurança (D51):** `PUT` do curso sem `materials` passa a preservar os materiais (antes apagava); senha acima de 72 bytes passa a ser recusada no login; conta de funcionário do `.env` com senha acima de 72 bytes deixa de ser criada (aviso no log).
- **Turmas (D53):** modelo mínimo inventado por mim, pois o PDF só diz "inscritos por turma": turma pertence a um curso, a matrícula é atribuída manualmente por um gestor, capacidade opcional; o comprador não escolhe turma no checkout; o aluno não vê a própria turma.
- **Recuperação de senha (D60):** só aluno recebe link; resposta sempre idêntica; no máximo 3 tokens por hora por conta; validade de 1 h; aviso de "senha alterada"; o JWT não é revogado.
- **Recibo em PDF (D63):** só para pagamento aprovado ou reembolsado; PDF gerado em Python puro (sem dependência nova), sem compressão; mostra o nome do aluno, nunca o e-mail.

## Não feito por limite técnico ou regra
- SMTP real para o link de senha: sem servidor e sem credenciais.
- Limpeza do histórico do `.chrome-pdf-profile/`: decisão do grupo (D33.3).

## Incidentes de processo da noite
- Tentativa do dev-backend da E6 interrompida pelo usuário deixou um `llm_guard.py` parcial (234 linhas) solto na
  árvore; um `git add -A` meu o incluiu num commit local de docs. Corrigido antes do push (commit refeito só com
  os arquivos meus); a cópia parcial ficou fora do repo e o dev refez do zero com árvore limpa.
