# Relatório do modo autônomo — plano do feedback (D69)

Início: 19/10/2026. Fila: `docs/tdd/PLANO_FEEDBACK_PROF.md`. Atualizado ao fim de cada entrega.

## Entregas

| Entrega | Estado | Commits | Resultado |
|---|---|---|---|
| O0 — checkout do aluno + trava do mock | entregue | red `9dbd134`, D70 `622deb5`, backend `1deadb0` | O0 86/86; regressão 1051 passed; e2e O0 7/7 |
| F1 — trava de exclusão e arquivar curso | entregue | red `554d3ea`; backend `1be517d`, `cb8a1da`; front `2168826` | F1 55/55; regressão verde; e2e F1 11/11, L2 24/24, admin 33/33 |

## Decisões de política tomadas sem o PM (para revisão)

- **O0:** o mock de pagamento só vale com `APP_ENV=development` (em qualquer outro ambiente é ignorado e segue o fluxo real). Na landing o evento do mock fica com responsável `system`.
- **D70:** os testes de chat usam um catálogo próprio; o curso `lua` apagado pelo Victor continua só nas fixtures de teste.
- **F1:** textos `Não é possível excluir: o curso tem alunos matriculados. Arquive o curso para tirá-lo do catálogo.`, `Este curso não está disponível para novas matrículas.`, `Tem alunos matriculados — arquive em vez de excluir.` e confirmações `Arquivar o curso "<nome>"?`. Excluir curso sem alunos remove junto as turmas vazias.

## Paradas e itens pulados

- Observação O0: o `frontend/node_modules` local estava sem `@fontsource/barlow*` (instalado com `--no-save`). Em clone novo, rodar `npm ci`.
- O harness e2e (`servidor_e2e_e5/e7/h1`) ainda lê o catálogo real do bot (`c_e_c`, `python_profissional`); não quebra hoje.
