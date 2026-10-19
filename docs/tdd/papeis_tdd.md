# Papéis do projeto TDD — Fase 2 (fonte: gerente de projeto)

REGRAS COMUNS
- Repo: C:\Users\vihug\Documents\global-training-technology
- NUNCA fazer push. NUNCA trocar a branch de projeto/entrega sem ordem do orquestrador.
- NÃO tocar nas branches anteriores (feature/fase2-painel-administrativo, feature/fase2-merge-gustavo,
  feature/fase2-angular-integrado, origin/payment-system, main).
- Sem teste de carga. Sem segredo hardcoded. Sem arquivo de lixo versionado.
- Commits com Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

AGENTE-TESTES
- Escreve testes ANTES do código, a partir do documento de escopo e da decisão do PM.
- Observa o teste FALHANDO (red) e registra a saída antes de liberar a implementação.
- Depois da implementação roda: testes da entrega, regressão (suítes existentes), segurança e
  comportamento ponta a ponta no navegador (Chromium headless).
- NÃO escreve código de produção. Se um teste estiver errado, reporta ao orquestrador; não altera o
  próprio teste depois que o dev começou sem aprovação.

DEV-BACKEND
- Implementa FastAPI/SQLite somente até os testes passarem (green).
- NÃO altera arquivos de teste. Se achar um teste errado, reporta ao orquestrador e para.

DEV-FRONTEND
- Implementa Angular no padrão do Gustavo (NgModule, ApiService, guards, Bootstrap, Chart.js) somente
  até os testes passarem.
- NÃO altera arquivos de teste. Se achar um teste errado, reporta ao orquestrador e para.

DECISÕES DO PM (não discutir, registrar e seguir)
- Conta do aluno nasce após a compra por link de definição de senha; cadastro direto também permitido.
- Status de matrícula fechado: pending, active, cancelled, refunded.
- Materiais: campo opcional materials: [{title, url, type}] no JSON do curso, visível só com matrícula ativa.
- Recibo: JSON primeiro; PDF só se sobrar tempo.
- Vocabulário de status de PAGAMENTO continua o do Mercado Pago (approved, pending, refunded, rejected...);
  o status de MATRÍCULA é o conjunto fechado acima e é derivado do pagamento.
