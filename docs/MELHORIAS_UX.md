# MELHORIAS_UX.md — Oportunidades de melhoria de UI/UX

Levantamento feito em 05/11/2026 a partir do código da `main` (Angular em `frontend/src` e landing em
`frontend/landing_global_training.html`), comparado com o sistema visual de [`docs/DESIGN.md`](DESIGN.md).
É uma análise de código: as telas não foram testadas com usuários.

Nada aqui é decisão tomada. Cada item é uma proposta para o PM priorizar. Mudança de tela muda o que o usuário percebe,
então segue o ciclo do [`AGENTS.md`](../AGENTS.md): teste antes (e2e de navegador), implementação até o verde,
regressão, e registro da decisão no `docs/tdd/decisoes_tdd.md`. Várias telas citadas têm `data-testid` usados pelos
e2e existentes: mudar a estrutura pode exigir ajuste de teste pelo agente-testes (seção 4.3 do `AGENTS.md`).

**Resumo:** a base visual é consistente. Os maiores ganhos estão no fluxo do aluno, que hoje concentra muita coisa numa
página só.

| # | Melhoria | Prioridade | Tela |
|---|---|---|---|
| 1 | Cartão de curso enxuto, com uma ação principal | Alta | Área do aluno |
| 2 | Avaliação só depois de avançar no curso | Alta | Área do aluno |
| 3 | Momento de conclusão do curso | Alta | Sala do curso / área do aluno |
| 4 | Navegação da sala do curso | Alta | Sala do curso |
| 5 | Recibo perto de onde foi pedido | Alta | Área do aluno |
| 6 | Login e cadastro | Média | Login / cadastro |
| 7 | Confirmação no padrão da plataforma | Média | 8 telas |
| 8 | Estados de carregamento | Média | Várias |
| 9 | Avisos rápidos padronizados (toast) | Média | Várias |
| 10 | Abas do painel administrativo | Média | Painel administrativo |
| 11 | Tabela de alunos | Média | Painel administrativo |
| 12 | Ajustes de consistência | Baixa | Várias |

**Ordem sugerida:** itens 1 a 3 (maior ganho para o aluno e conversam com o certificado novo), depois o 6 (barato e é a
primeira impressão de quem vem da landing), depois o 7 (um componente resolve oito telas).

---

## Prioridade alta — fluxo do aluno

### 1. Cartão de curso enxuto, com uma ação principal

**Onde:** [`student-dashboard.component.html`](../frontend/src/app/components/student-dashboard/student-dashboard.component.html), linhas 53–147.

**Problema:** cada cartão de curso junta botão "Entrar no curso", lista de materiais, a mesma lista repetida como caixas de
marcar, barra de progresso, certificado, formulário de avaliação e pedido de cancelamento. Com dois ou três cursos a
página fica muito longa, e o que importa (continuar estudando) se perde.

**Proposta:**
- O cartão mostra só: ícone, nome, status, turma, barra de progresso e **um** botão principal que muda conforme o
  momento:
  - 0%: "Começar o curso";
  - entre 1% e 99%: "Continuar de onde parei" (a sala já guarda o último conteúdo aberto, D103);
  - 100%: "Baixar certificado".
- Lista de materiais e marcação de aulas ficam só na sala do curso, que já faz isso.
- Avaliação e "Pedir cancelamento" vão para um menu secundário ("⋯") no cartão ou para dentro da sala.

**Cuidado:** os e2e da E3, D2, X1 e U5 usam `curso-entrar`, `material-concluido`, `curso-certificado`,
`curso-cancelar` e os links de material dentro do cartão. Ver com o agente-testes antes de mover esses elementos.

### 2. Avaliação só depois de avançar no curso

**Onde:** mesmo arquivo, linhas 98–119.

**Problema:** o formulário "Avalie o curso" aparece assim que a matrícula fica ativa, com 0% de progresso. O aluno é
convidado a avaliar algo que ainda não fez.

**Proposta:**
- Mostrar a avaliação a partir de um limite de progresso (ex.: 50%) ou junto com o certificado ("Que nota você dá para o
  curso?"). O limite é decisão do PM.
- Trocar o `<select>` com "5 ★ … 1 ★" por estrelas clicáveis (SVG, com `aria-label` "Nota 4 de 5" e navegação por
  teclado).

### 3. Momento de conclusão do curso

**Onde:** [`course-room.component.html`](../frontend/src/app/components/course-room/course-room.component.html), linhas 9–19, e o cartão
da área do aluno.

**Problema:** quando o aluno termina o curso, o único sinal é um botão pequeno (`btn-sm`) "Baixar certificado". O
certificado ganhou layout próprio e merece destaque.

**Proposta:**
- Ao chegar a 100%, a sala mostra um bloco de destaque: "Você concluiu o curso Excel Profissional!", com o botão
  "Baixar certificado" em tamanho normal e a avaliação logo abaixo (liga com o item 2).
- Sem animação exagerada: o `DESIGN.md` limita o movimento a três momentos e pede respeito a
  `prefers-reduced-motion`.

### 4. Navegação da sala do curso

**Onde:** [`course-room.component.html`](../frontend/src/app/components/course-room/course-room.component.html).

**Problemas:**
- Só existe "Próximo conteúdo" (linha 56); não há "Anterior".
- No celular, a lista de aulas fica abaixo do vídeo; para trocar de aula é preciso rolar a página inteira.
- O título do curso é `h3` e a página não tem `h1` (o `DESIGN.md` pede um `h1` por página).
- Aula concluída é marcada com o caractere "✓" no texto (linha 69), em vez de ícone.

**Proposta:**
- Botões "Anterior" e "Próximo" e um contador "Aula 3 de 12".
- No celular, lista de aulas recolhível no topo ("Aulas do curso ▾").
- Título do curso em `h1`; ícone SVG de concluído com texto acessível ("Concluída").

### 5. Recibo perto de onde foi pedido

**Onde:** [`student-dashboard.component.html`](../frontend/src/app/components/student-dashboard/student-dashboard.component.html), linhas 163–188.

**Problema:** "Ver recibo" numa linha da tabela abre o recibo **abaixo da tabela inteira**. Com vários pagamentos, o
aluno clica e não vê nada acontecer.

**Proposta:** abrir o recibo numa janela modal (com foco preso na janela e fechamento por Esc) ou expandir logo abaixo da
linha clicada.

**Cuidado:** os e2e da E4/B2 procuram `card.border-primary` para o recibo.

---

## Prioridade média — formulários e retorno ao usuário

### 6. Login e cadastro

**Onde:** [`login.component.html`](../frontend/src/app/components/login/login.component.html) e
[`cadastro.component.html`](../frontend/src/app/components/cadastro/cadastro.component.html).

**Problemas:**
- O e-mail do login é `type="text"`, sem `autocomplete="email"`; as senhas não têm `autocomplete="current-password"` /
  `"new-password"`. Gerenciadores de senha e o teclado do celular funcionam pior.
- Não há botão para mostrar a senha. O cadastro não tem confirmação de senha nem indicador de força, só o texto
  "(mínimo 8 caracteres)".
- O botão "Entrar" não mostra que está carregando e aceita cliques repetidos.
- Os títulos ("Acessar Plataforma", "Criar conta de aluno") são `h4`; a página fica sem `h1`. "Acessar Plataforma" usa
  maiúscula fora do padrão dos outros textos.
- Quem chega pela landing com `?area=aluno&next=/catalogo?curso=...` ("Matricular agora") não vê qual curso escolheu.

**Proposta:**
- Corrigir `type` e `autocomplete` dos campos.
- Botão de mostrar/ocultar senha (SVG com `aria-label` e `aria-pressed`).
- Confirmação de senha e dica de força no cadastro.
- Botão "Entrar" com estado "Entrando..." e desabilitado durante o envio.
- Títulos em `h1`, no tom do `DESIGN.md` ("Entrar na plataforma").
- Com `next` apontando para um curso, mostrar "Entre para concluir sua matrícula em Excel Profissional."

### 7. Confirmação no padrão da plataforma

**Onde:** `confirm()` nativo do navegador em 8 lugares:
- [`student-dashboard.component.ts`](../frontend/src/app/components/student-dashboard/student-dashboard.component.ts) (pedir cancelamento);
- [`student-profile.component.ts`](../frontend/src/app/components/student-profile/student-profile.component.ts) (excluir conta);
- [`financial-dashboard.component.ts`](../frontend/src/app/components/financial-dashboard/financial-dashboard.component.ts) (aprovar cancelamento e reembolsar, 2 lugares);
- [`courses-dashboard.component.ts`](../frontend/src/app/components/courses-dashboard/courses-dashboard.component.ts) (excluir turma);
- [`course-admin.component.ts`](../frontend/src/app/components/course-admin/course-admin.component.ts);
- [`students-dashboard.component.ts`](../frontend/src/app/components/students-dashboard/students-dashboard.component.ts);
- [`staff-admin.component.ts`](../frontend/src/app/components/staff-admin/staff-admin.component.ts) (desativar funcionário).

**Problema:** a janela nativa tem visual de sistema operacional, quebra a identidade da plataforma e, no celular, parece
mensagem de erro.

**Proposta:**
- Um único componente/serviço de confirmação (modal Bootstrap no padrão do `DESIGN.md`), reaproveitado nos oito lugares.
- Ação destrutiva com botão vermelho e texto que diz o que acontece ("Excluir minha conta").
- Para exclusão de conta, pedir que a pessoa digite uma palavra de confirmação.

**Cuidado:** os e2e que hoje aceitam o diálogo nativo (`page.on("dialog")`) precisam passar a clicar no botão do modal.

### 8. Estados de carregamento

**Onde:** sala do curso ("Carregando...", linha 3), catálogo ("Carregando cursos..."), área do aluno (usa
`EnrollmentsResolver`, então a navegação parece travada até os dados chegarem).

**Proposta:**
- Esqueletos (blocos cinza com animação suave, desligada em `prefers-reduced-motion`) no lugar de cartões e tabelas.
- Barra fina de progresso no topo durante a navegação entre rotas.

### 9. Avisos rápidos padronizados (toast)

**Onde:** marcar aula, enviar avaliação, salvar perfil, ações do painel administrativo.

**Problema:** cada tela mostra a confirmação de um jeito e num lugar diferente (texto verde em linha, alerta no topo,
nada).

**Proposta:** um serviço de aviso rápido no canto da tela ("Aula marcada como concluída"), com `role="status"`, que some
sozinho. Erros continuam em alerta fixo, porque o usuário precisa ler.

### 10. Abas do painel administrativo

**Onde:** [`admin-dashboard.component.html`](../frontend/src/app/components/admin-dashboard/admin-dashboard.component.html).

**Problemas:** "Painel administrativo" é `h3` (sem `h1`); são até sete abas numa linha, que viram rolagem horizontal no
celular.

**Proposta:** título em `h1`; agrupar as abas ("Operação": Financeiro, Alunos, Cursos — "Gestão": Cadastro de cursos,
Equipe, IA, Auditoria) ou menu lateral no desktop. Manter o indicador deslizante das abas (`DESIGN.md`, Movimento).

### 11. Tabela de alunos

**Onde:** [`students-dashboard.component.html`](../frontend/src/app/components/students-dashboard/students-dashboard.component.html).

**Problemas:**
- A busca só dispara com Enter, sem botão e sem busca enquanto digita.
- Não dá para ordenar pelas colunas.
- Busca sem resultado mostra "Nenhum aluno matriculado ainda", o que é enganoso.

**Proposta:** botão "Buscar" (ou busca com atraso de ~300 ms enquanto digita); ordenação clicando no cabeçalho, com
`aria-sort`; mensagem de vazio diferente para busca ("Nenhum aluno encontrado para "joão"").

---

## Prioridade baixa — consistência

### 12. Ajustes de consistência

- **Emojis como ícone:** os 👍 👎 do feedback do chat
  ([`student-dashboard.component.html`](../frontend/src/app/components/student-dashboard/student-dashboard.component.html), linhas 211–222)
  e o "✓" da lista de aulas contrariam o `DESIGN.md` ("Não usar emojis como ícone; ícones de interface são SVG
  inline"). A landing já tem um conjunto de ícones SVG que pode ser reaproveitado.
- **Links de voltar:** "← Voltar para Meus cursos" (sala), "Voltar para a área do aluno" (catálogo) e "Voltar ao site"
  (barra) seguem padrões diferentes. Definir um único estilo de link de voltar ou um breadcrumb.
- **Assistente no fim da página:** na área do aluno o chat é a última seção; só se chega a ele rolando ou pelo atalho. A
  landing usa botão flutuante; repetir o padrão deixa o assistente sempre à mão. Cuidado com os `data-testid` da E5
  (`chat-panel`, `chat-input`, `chat-send`, `chat-message`).

---

## Como validar

- Cada item vira uma entrega com e2e próprio (Playwright, como os de `frontend/e2e/`).
- Regras visuais e de acessibilidade continuam conferidas por
  `py -3 -m pytest frontend/e2e/test_d4_polimento_visual.py -s`.
- Conferir em 390 px de largura (sem rolagem horizontal) e com navegação só por teclado.
