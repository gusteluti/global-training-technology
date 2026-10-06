# Relatório da noite (D40) — início em 06/10/2026

Atualizado a cada entrega. Quem acordou: leia primeiro a seção "Decisões de política tomadas sem o PM".

## Fila e estado
| # | Item | Estado |
|---|---|---|
| 1 | E6 — segurança de LLM | **entregue** (D41): backend 271 passed, landing 8/8; mergeada e publicada |
| 2 | E7 — observabilidade de IA | pendente |
| 3 | E8 — auditoria | pendente |
| 4 | E9 — hardening de pagamento | pendente |
| 5 | Dívidas de segurança (token, bcrypt, update-course) | pendente |
| 6 | Lacunas de produto (turma, cadastro de cursos no Angular, interceptor) | pendente |
| 7 | Dívidas de harness (D4, D6, D7, D10) | pendente |
| 8 | Backlog opcional (recuperação de senha, recibo PDF) | pendente |

## Decisões de política tomadas sem o PM (revisar na volta)
- **E6:** textos fixos que o usuário final vê (`INPUT_BLOCKED`, `OFFER_BLOCKED`, `LLM_UNAVAILABLE`, `TOO_LONG`), em D38.
- **E6:** conteúdo do filtro: bloqueia parcelamento legítimo ("12x de R$ ...") por ser valor fora do catálogo; limite de 2000 caracteres por mensagem.
- **E6:** falha do Groq no chat do aluno agora responde 502 e nada é gravado (antes virava mensagem do bot).

## Não feito por limite técnico ou regra
- SMTP real para o link de senha: sem servidor e sem credenciais.
- Limpeza do histórico do `.chrome-pdf-profile/`: decisão do grupo (D33.3).

## Incidentes de processo da noite
- Tentativa do dev-backend da E6 interrompida pelo usuário deixou um `llm_guard.py` parcial (234 linhas) solto na
  árvore; um `git add -A` meu o incluiu num commit local de docs. Corrigido antes do push (commit refeito só com
  os arquivos meus); a cópia parcial ficou fora do repo e o dev refez do zero com árvore limpa.
