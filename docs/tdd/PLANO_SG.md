# Plano SG — Segurança da superfície pública (proposta, aguardando sinal verde do PM)

Registrar como **D109** quando aprovado. Entregas **SG0 a SG10**, cada uma com ciclo TDD próprio, seguindo o `AGENTS.md`
(orquestrador, agente-testes, dev-backend e dev-frontend, um agente por vez, D84 enxuto). Nenhuma linha de código foi
alterada para escrever este plano.

## Por que este plano

A landing é um HTML estático. O risco está na API pública que ela chama: `/api/chat`, `/api/courses`,
`/api/payments/create-checkout`, `/api/auth/register`. Essa API roda no mesmo processo e no mesmo `db.sqlite` que guarda
alunos, funcionários, pagamentos e conversas, e o SQLite não tem usuários nem permissões para limitar o alcance de uma
falha. O plano reduz o alcance (isolamento) e fecha as aberturas que a leitura do código encontrou.

### Correções à análise anterior (conferidas no código depois dela)
- **XSS no chat: risco menor do que eu disse.** `markdownToHtml` (landing) e o pipe `chatMarkdown` (Angular) escapam o
  HTML antes de formatar, e os cartões de curso da landing usam `escapeHTML`. O que resta é defesa em profundidade:
  CSP e o token em `localStorage`.
- **Bloqueio de login já é persistente** (tabela `login_attempts`, D79). Só os limites do chat, do checkout e da
  checagem de link ficam em memória.
- **Upload é mais seguro do que eu supus:** só `.pdf`, `.docx`, `.xlsx`, `.pptx`, `.zip`, com conferência do início do
  arquivo, e o download exige matrícula ativa. Falta apenas `nosniff`.
- **`X-Forwarded-For` ignorado foi decisão documentada (D79).** O problema só existe atrás de proxy, e o plano trata
  isso como mudança de política (P4).
- **O `"gt"` de `core/progresso.py` é código praticamente morto** (sem `JWT_SECRET_KEY` o app já responde 500 em outros
  pontos), mas é um fallback fixo e sai no SG2.

---

## Regras que valem em todas as entregas

- **Base:** `main` depois do merge do PR #8 (e do #7). Se o PM quiser começar antes, parte da
  `feature/fase2-fluxos-usabilidade` (`55ded1e`). Branch de projeto `feature/fase2-seguranca`; sub-branch por entrega
  (`feature/sg<N>-...`); commit de teste vermelho; commit de implementação só até o verde; suíte da entrega + relacionadas
  + e2e da tela; merge `--no-ff` na branch de projeto; D110, D111... uma entrada por entrega; `PENDENCIAS.md` e
  `HANDOFF_TDD.md` atualizados.
- **Regressão completa e todos os e2e no fim de cada onda** (onda 1 = SG1 a SG4; onda 2 = SG5 e SG6; onda 3 = SG7).
- **Falhas que já existem na `main` (D107):** 13 de backend e 3 e2e continuam "conhecidas" e registradas até serem
  corrigidas. Recomendo corrigi-las antes do SG0, para o CI nascer verde (ver SG0).
- **Nenhum teste chama serviço real:** Groq, Mercado Pago, Turnstile e SMTP entram por dublê injetável.
- **Checklist de 9 itens do `AGENTS.md`:** itens 3 (IDOR) e 4 (material pago) valem onde houver endpoint de usuário ou
  conteúdo; item 7 (401/403) vale em toda rota nova.
- **Textos fixos novos** ficam em módulo próprio da entrega e vão para revisão do PM.
- **Push:** nunca `main`, nunca force-push, auditoria antes de cada push (D30). PR aberto por mim; **merge sempre por
  uma pessoa**.
- **Autoridade 4.3:** ajustes mecânicos de testes antigos causados por decisões deste plano são feitos pelo
  agente-testes e registrados com o encadeamento (D109 → D11x).

## Mapa das entregas

| ID | Entrega | O que fecha | Tamanho | Decisão do PM |
|---|---|---|---|---|
| SG0 | Higiene do repositório e dos segredos | credenciais vazadas, `main` sem proteção, sem CI | P | rotação é manual |
| SG1 | Superfície de descoberta e cabeçalhos da API | `/docs`, debug, `/health` detalhado, sem cabeçalhos | P | P1, P2 |
| SG2 | Configuração de produção que não sobe insegura | login legado por senha única, chave de token = senha, fallback `"gt"` | P | P3 |
| SG3 | IP real atrás de proxy | limites e bloqueios por IP viram um só atrás de proxy | P | P4 |
| SG4 | Teto de custo e abuso do chat anônimo | gasto ilimitado no Groq, sessões em massa | M | P5 |
| SG5 | Inventário de rotas e deploy com proxy | rota nova sem proteção, host público x host de equipe | M | — |
| SG6 | Landing sem script inline e CSP aplicada | sem CSP, token em `localStorage` exposto a XSS | M | — |
| SG7 | Serviço público isolado | alcance ao banco de alunos pela superfície pública | G (3 ciclos) | P8 |
| SG8 | Anti-bot (Turnstile) *(opcional)* | cadastro, reset e chat automatizados | M | P6 |
| SG9 | Segundo fator (TOTP) para a equipe *(opcional)* | conta de Gestão/Financeiro com só uma senha | G | P7 |
| SG10 | Retenção e backup cifrado *(opcional)* | dados pessoais em texto claro em backup | M | P9 |

**Ordem:** SG0 → SG1 → SG2 → SG3 → SG4 (onda 1) → SG5 → SG6 (onda 2) → SG7a/b/c (onda 3) → opcionais.
SG5 depende de SG1 e SG3; SG6 depende de SG5 (a CSP sai do `deploy/`); SG7 depende de SG5.
Tamanho: P = um ciclo curto; M = um ciclo completo; G = dois a três ciclos.

## Decisões para o PM (política, o que o usuário percebe, contrato)

| # | Decisão | Minha recomendação |
|---|---|---|
| P1 | `GET /api/chat/courses-debug`: remover ou deixar só para a Gestão | Remover (só um teste QA usa) |
| P2 | `/health` público: só `{"status"}`; detalhe (`services`, `courses_loaded`, `payments_mock`) em `GET /api/dashboard/saude`. Quem vê? | Só a Gestão |
| P3 | Login legado de funcionário por senha única (`/api/admin/login`) desligado em produção; a equipe usa contas individuais (S3) | Desligar; a tela do Angular já não o usa |
| P4 | Confiar em `X-Forwarded-For` somente de proxies listados em `TRUSTED_PROXIES` (revisa D79) | Aprovar; padrão vazio = comportamento atual |
| P5 | Teto diário de tokens do chat anônimo, teto por IP e texto fixo de indisponibilidade | 300.000 tokens/dia, 200 msgs/IP/dia, 20 sessões novas/IP/hora; texto no SG4 |
| P6 | Turnstile (Cloudflare): serviço externo e widget visível | Sim, como opcional por configuração |
| P7 | TOTP para Gestão e Financeiro, obrigatório em produção | Sim, implementação própria RFC 6238, sem dependência nova |
| P8 | SG7 (serviço isolado) entra neste TCC ou fica documentado como arquitetura-alvo | Entra se houver prazo; senão SG1–SG6 já fecham o grosso e o SG7 vira "próxima fase" |
| P9 | Retenção de conversas (dias) e backup cifrado (dependência `cryptography`) | 180 dias no anônimo; decidir junto da política LGPD do grupo |
| P10 | Base da branch: depois do merge dos PRs #7/#8, ou já a partir da branch de fluxos | Depois do merge |

---

## SG0 — Higiene do repositório e dos segredos

**Risco que fecha:** credenciais vazadas no histórico de um repositório público (chat1.json), `main` aceitando push
direto, nenhuma verificação automática de dependência ou segredo.

**Manual (eu não posso nem devo fazer; Victor e Gustavo):**
1. Rotacionar o token do Mercado Pago, a senha de app do Gmail e o token do GitHub colados em conversa.
2. GitHub → Settings: Secret scanning + Push protection; Dependabot alerts; **branch protection em `main`** (PR
   obrigatório, 1 aprovação, sem force-push, sem exclusão).
3. O histórico **não** é reescrito (decisão do grupo sobre `.chrome-pdf-profile`); o risco aceito fica registrado na D109.

**Código (ciclo TDD):**
- **Testes primeiro** — `backend/tests/test_sg0_higiene.py`:
  - (a) existe `.github/workflows/ci.yml` com passos de pytest, `pip-audit`, `npm audit --omit=dev` e gitleaks no diff
    do PR (**vermelho hoje**: não há workflow);
  - (b) nenhum arquivo rastreado (`git ls-files`) casa com padrões de segredo (`ghp_`, `github_pat_`, `APP_USR-`,
    `gsk_`, `AIza`, `-----BEGIN .* PRIVATE KEY-----`, `SMTP_PASSWORD=` com valor) — guarda verde;
  - (c) `.gitignore` cobre `.env*`, `*.sqlite`, `backend/uploads/`, `.chrome-pdf-profile/`, `backups/` — guarda verde.
- **Implementação (dev-backend):** o workflow e nada mais. Enquanto as 13 falhas da D107 existirem, o CI roda a suíte
  completa em modo informativo e o conjunto SG como obrigatório; depois da correção da D107, tudo obrigatório.
- **Checklist:** itens 1, 2, 9. Sem tela.

## SG1 — Superfície de descoberta e cabeçalhos da API

**Risco que fecha:** `/docs` e `/openapi.json` entregam o mapa completo (inclusive `/api/admin`); `/api/chat/courses-debug`
é rota de depuração pública; `/health` revela se o pagamento está em modo simulado; nenhuma resposta tem cabeçalho de
segurança.

**Contrato:**
- `/docs`, `/redoc` e `/openapi.json` respondem 404, exceto com `APP_ENV` em `development` ou `test`.
- `/api/chat/courses-debug` removido (404) (P1).
- `/health` e `/api/health` públicos devolvem só `{"status": "ok" | "degraded"}`. O detalhe vai para
  `GET /api/dashboard/saude` (401 sem token, 403 fora do perfil de P2).
- Toda resposta da API (inclusive 401, 404, 422, 429) leva `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `Permissions-Policy` sem câmera, microfone e geolocalização.
- Respostas **JSON** levam também `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`. PDFs e
  downloads ficam sem essa CSP (ela quebra o visualizador de PDF) e mantêm `nosniff`.
- `Cache-Control: no-store` em `/api/token`, `/api/auth/*`, `/api/admin/*`, `/api/dashboard/*`, `/api/student/*`.
- `Strict-Transport-Security` só com `APP_ENV=production`.

**Testes primeiro** — `backend/tests/test_sg1_superficie.py` (todos vermelhos hoje, exceto as guardas):
docs 404 em produção e 200 em `development`; `courses-debug` 404; corpo exato de `/health`; `saude` 401/403/200 por
perfil; cabeçalhos presentes em amostras de GET, POST, 401, 404, 422 e 429; CSP ausente no PDF do recibo (guarda) e
`nosniff` presente nele; HSTS só em produção; `no-store` nas rotas de conta e ausente em `/api/courses`.
**Ajustes mecânicos 4.3:** `test_x3_x4_operacao.py` e `test_o0_checkout_aluno.py` (leem `payments_mock` do `/health`) e
`test_qa_istqb.py` (usa `courses-debug`).

**Implementação (dev-backend):** middleware de cabeçalhos, flag de docs, rota `saude`, remoção do debug.
**Tela:** nenhuma. **Checklist:** item 7 na rota nova. **Tamanho:** P.

## SG2 — Configuração de produção que não sobe insegura

**Risco que fecha:** `/api/admin/login` aceita uma senha única por perfil, sem identidade individual e sem 2FA;
`ADMIN_TOKEN_SECRET` cai para `ADMIN_PASSWORD` (quem descobre a senha forja tokens); app sobe em produção com segredo
curto, mock de pagamento ou CORS de localhost; fallback fixo `"gt"` no código de validação do certificado.

**Contrato:**
- Com `APP_ENV=production` o app **não sobe** (mensagem sem valores de segredo) se: `JWT_SECRET_KEY` ausente ou com
  menos de 32 caracteres; `ADMIN_TOKEN_SECRET` ausente ou igual a alguma senha de perfil; senha de perfil com menos de
  12 caracteres ou igual às senhas públicas do `seed_demo`; `PAYMENTS_MOCK` ligado; `MERCADO_PAGO_WEBHOOK_SECRET`
  vazio; `CORS_ALLOWED_ORIGINS` com `localhost` ou `http://`. Fora de produção: só `[AVISO]` no log.
- `POST /api/admin/login` responde 404 em produção (P3); em `development` e `test` continua (os testes e o `seed_demo`
  usam).
- `codigo_validacao` sem fallback: sem `JWT_SECRET_KEY` levanta erro. **Com a chave definida o código é idêntico ao de
  hoje** (certificados já emitidos continuam válidos).

**Testes primeiro** — `backend/tests/test_sg2_configuracao_producao.py`: um caso por condição de recusa, cada um com a
mensagem esperada e a prova de que o valor do segredo não aparece no erro; produção válida sobe; `development` sobe com
avisos; login legado 404 em produção e 200 em `development`; `get_admin_secret` não usa `ADMIN_PASSWORD` em produção;
**guarda:** `codigo_validacao` devolve o mesmo valor de antes para a mesma chave.
**Implementação (dev-backend):** `core/configuracao.py` com `validar_configuracao()` no startup; ajuste em `security.py`
e `progresso.py`. **Tela:** nenhuma. **Atualizar:** lista de variáveis do `AGENTS.md` 6.1 e README. **Tamanho:** P.

## SG3 — IP real atrás de proxy (revisa D79)

**Risco que fecha:** atrás de nginx, Caddy ou NAT todo mundo chega com o mesmo IP: 20 falhas de login bloqueiam **todos**
(DoS trivial) e o limite de 30 mensagens/min vira global. Sem proxy o comportamento atual está correto.

**Contrato (P4):** variável `TRUSTED_PROXIES` (IPs e CIDRs; **padrão vazio = comportamento de hoje**, cabeçalho
ignorado). Função única `core/cliente_ip.py` usada por `rate_limit` e `login_limit`: se o par TCP está na lista, vale o
IP mais à direita de `X-Forwarded-For` que não seja proxy confiável; caso contrário o cabeçalho é ignorado
(anti-spoof). Cabeçalho malformado volta ao par TCP. IPv6 normalizado.
Nota registrada: os limites de chat e checkout continuam em memória, então o serviço roda com **um** worker; se
escalar, mover para tabela.

**Testes primeiro** — `backend/tests/test_sg3_ip_confiavel.py`: sem `TRUSTED_PROXIES` o cabeçalho forjado não muda a
chave (guarda verde); com proxy confiável, dois clientes atrás do mesmo proxy têm contadores separados no chat e no
login, e o bloqueio de um não bloqueia o outro (**vermelho hoje**); cabeçalho vindo de peer não confiável é ignorado;
cadeia `a, b, proxy` usa `b`; malformado; IPv6; `login_attempts` e o evento `auth.locked` guardam o IP efetivo.
**Ajustes mecânicos 4.3:** docstrings e testes S2/S9 que afirmam "X-Forwarded-For não é considerado" passam a dizer
"não é considerado sem `TRUSTED_PROXIES`".
**Implementação (dev-backend).** **Tela:** nenhuma. **Tamanho:** P.

## SG4 — Teto de custo e abuso do chat anônimo

**Risco que fecha:** o chat anônimo gasta a chave do Groq sem teto global; cada IP novo recomeça o limite; sessões
novas em massa.

**Contrato (valores em P5):**
- `CHAT_ANON_DAILY_TOKEN_BUDGET` (padrão 0 = desligado). Soma `ai_usage` do canal anônimo no dia de São Paulo. Estourou:
  texto fixo `CHAT_INDISPONIVEL` — "O assistente está com muitas conversas agora. Fale com a nossa equipe pelo WhatsApp ou
  tente de novo amanhã." — com a ação de handoff da F6, **sem chamar o LLM**, `outcome='unresolved'`, `guard='budget'`
  (valor novo do vocabulário fechado: decisão registrada na D11x).
- `CHAT_ANON_DAILY_MESSAGES_PER_IP` (padrão 0 = desligado) → 429 com `ERRO_CHAT`.
- `CHAT_ANON_NEW_SESSIONS_PER_IP_HOUR` (padrão 0 = desligado) → 429 ao abrir sessão nova.
- O chat do aluno logado **não** é afetado.

**Testes primeiro** — `backend/tests/test_sg4_teto_chat.py` (dublê do Groq com contador de chamadas): orçamento 0 nunca
bloqueia (guarda); depois de gastar N tokens simulados a próxima mensagem recebe o texto fixo e o dublê tem **0**
chamadas; handoff presente quando há número; virada do dia (relógio de São Paulo) zera; chat do aluno segue funcionando;
201ª mensagem do mesmo IP → 429 e outro IP não é afetado; sessões novas por hora; o bloqueio aparece no cartão
Guardrails por tipo `budget`.
**Implementação (dev-backend)** + **dev-frontend:** rótulo "Teto diário atingido" no cartão Guardrails da aba
Observabilidade de IA. **E2E:** `frontend/e2e/test_sg4_teto_chat.py` (landing mostra o texto fixo e o botão de WhatsApp;
cartão mostra o contador). **Checklist:** itens 7 e 8. **Tamanho:** M.

## SG5 — Inventário de rotas e deploy com proxy

**Risco que fecha:** uma rota nova nascer pública por esquecimento; o painel da equipe acessível pelo mesmo host da
landing; nenhuma barreira entre a internet e o que é privado.

**Parte A — inventário (backend):** `backend/core/superficie.py` com tabela única `(método, caminho) → nível`
(`publica`, `webhook`, `aluno`, `equipe`).
- **Testes primeiro** — `backend/tests/test_sg5_inventario.py`: (1) toda rota de `app.routes` está no inventário e
  toda entrada do inventário existe (rota nova sem classificação quebra o teste); (2) toda rota que não é
  `publica` nem `webhook` tem dependência de autenticação (introspecção do `dependant`); (3) para cada rota `aluno` e
  `equipe`, sem token → 401 e com token de perfil errado → 403, **gerado por parametrização**. Vermelho hoje: o
  inventário não existe, e o teste pode **revelar rota desprotegida de verdade**; se revelar, vira defeito corrigido
  na mesma entrega.

**Parte B — deploy (`deploy/`):** `Caddyfile` (TLS automático) com dois hosts. Escolha de ferramenta é decisão de forma
do orquestrador.
- **Host público:** só rotas `publica` e `webhook` + estáticos da landing; `/docs`, `/openapi.json` e `saude` não
  roteados.
- **Host do aplicativo:** SPA + `/api/student`, `/api/dashboard`, `/api/admin`, `/api/auth`, `/api/token`;
  `/api/admin` e `/api/dashboard` opcionalmente limitados por `STAFF_ALLOW_IPS` (VPN ou IP da escola).
- Corpo máximo de 1 MB (20 MB só no upload de conteúdo), timeouts, HSTS, `X-Frame-Options`.
- Backend escuta em `127.0.0.1` por padrão (`API_HOST`, hoje é `0.0.0.0` fixo).
- `docs/SEGURANCA_DEPLOY.md` com o checklist de produção (variáveis, `TRUSTED_PROXIES`, um worker, backups, firewall).
- **Testes primeiro** — `backend/tests/test_sg5_deploy_config.py` (leitura estática do arquivo): todo caminho liberado
  no host público existe no inventário como `publica` ou `webhook`; nenhum `aluno` ou `equipe` aparece lá; cabeçalhos
  exigidos presentes; `API_HOST` padrão é `127.0.0.1`; `caddy validate` quando o binário existir.
- Teste de ponta a ponta do proxy real **não é automatizável no ambiente** (sem Caddy): fica um roteiro de `curl` no
  documento de deploy, para rodar no servidor.

**Checklist:** itens 1, 2, 7, 9. **Tamanho:** M.

## SG6 — Landing sem script inline e CSP aplicada

**Risco que fecha:** sem CSP, qualquer XSS futuro lê o token do `localStorage`. Hoje a landing não aceita CSP
estrita: tem `<script>` inline e `onclick=` dentro de template strings.

**Contrato:** nenhuma mudança visível. (1) JS da landing em `frontend/landing.js`; (2) `onclick` vira `data-acao` com
delegação de eventos; (3) CSP do `deploy/` primeiro em modo `Report-Only`, depois obrigatória:
`script-src 'self'`; `style-src 'self' 'unsafe-inline'` (Bootstrap e Angular); `connect-src 'self'` + API;
`frame-src` do YouTube e do Vimeo (player da sala); `img-src 'self' data:`; `frame-ancestors 'none'`; `base-uri 'self'`;
`form-action 'self'`. A SPA Angular usa o build de produção com a mesma política.

**Testes primeiro:**
- `backend/tests/test_sg6_landing_estatica.py`: a landing não contém `<script>` sem `src` nem atributo `on*=`
  (**vermelho hoje**).
- `frontend/e2e/test_sg6_csp_landing.py` e `test_sg6_csp_angular.py`: servem landing e SPA com a CSP do `deploy/`
  aplicada na resposta (mesmo padrão de interceptação da D104), percorrem catálogo, chat com dublê, "Matricular",
  login, cadastro e sala, e afirmam **zero** `securitypolicyviolation` e zero erro de CSP no console. Negativos: texto
  de resposta do chat com `<script>` e com `<img onerror=...>` aparece como texto e não executa. A parte de vídeo
  roda só na máquina do aluno (YouTube bloqueado na nuvem), como os e2e existentes.

**Implementação (dev-frontend).** **Risco:** muitos e2e da landing chamam funções globais (`goToStudentArea`,
`chatAbout`); os ajustes são mecânicos (4.3) e ficam no log. **Tamanho:** M.

## SG7 — Serviço público isolado

**Objetivo:** um processo, um `.env` e um arquivo de banco próprios para o que é público, **sem alcance** a alunos,
funcionários e pagamentos. Uma invasão pelo chat deixa de ser uma invasão do sistema.

**Escopo (rotas):** `GET /api/courses`, `GET /api/courses/{id}/turmas`, `POST /api/chat`, `POST /api/chat/feedback`,
`GET /health`. **Ficam no núcleo**, protegidas pelo proxy, pelos limites e pelo SG8: cadastro, redefinição de senha,
checkout (cria matrícula), webhook e tudo de aluno e equipe. Mover cadastro e checkout para a base pública com
"intenção de compra" é a **fase B**, fora deste plano.

**SG7a — Spike somente leitura e dados publicados.**
- Mapear tudo que `manager_agent`, `course_agent`, `rag`, `llm_guard`, `handoff` e `ai_observability` importam, leem e
  gravam. Já sabido: o catálogo vem de `backend/courses/*.json` e o RAG de `backend/knowledge/*.md` (arquivos);
  turmas e vagas vêm do banco (`list_open_classes_for_sale`); a telemetria anônima grava as tabelas `ai_*`.
- O núcleo publica `turmas_publicas.json` (escrita atômica por `rename`) ao iniciar, a cada mudança de turma ou
  matrícula e a cada 60 s. A vaga mostrada na landing pode ter até 60 s de atraso; o checkout confere a vaga de verdade.
- **Testes primeiro:** o arquivo é regenerado após criar, editar e lotar turma; arquivo ausente ou corrompido →
  catálogo sem turmas e o chat **não inventa** turma (guarda); escrita atômica; nenhum dado pessoal no arquivo.

**SG7b — App público e telemetria própria.**
- `backend/public_app.py` (novo FastAPI) + `public_db.py`: grava só em `public.sqlite` (`PUBLIC_DB_PATH`): `ai_usage`,
  `ai_interactions`, `ai_replies`, `ai_feedback`, `ai_handoffs` e sessões anônimas. Lê catálogo e conhecimento em
  somente leitura.
- Recebe apenas `GROQ_API_KEY`, `WHATSAPP_HANDOFF_NUMBER`, `PUBLIC_DB_PATH` e diretórios. **Nunca** `JWT_SECRET_KEY`,
  `ADMIN_*`, `MERCADO_PAGO_*`, `SMTP_*`.
- **Testes primeiro** — `backend/tests/test_sg7_servico_publico.py` (vermelho: o módulo não existe):
  1. **inventário exato:** as rotas de `public_app` são exatamente a lista permitida (rota a mais falha);
  2. **isolamento de import:** em subprocesso, importar `public_app` não carrega `admin.*`, `student.*`, `dashboard.*`,
     `payments.*`, `auth` nem o `Database` do núcleo;
  3. **isolamento de ambiente:** com o ambiente reduzido (sem `JWT_SECRET_KEY` e demais segredos) sobe e responde
     `/health`;
  4. **isolamento de dados:** com `db.sqlite` inexistente ou ilegível o chat e o catálogo funcionam, e
     `PUBLIC_DB_PATH` igual ao do núcleo falha na validação de configuração;
  5. **sem vazamento:** com alunos, e-mails e CPFs semeados no banco do núcleo, nenhuma resposta e nenhum prompt
     enviado ao dublê do LLM contém dado deles;
  6. **mesmo contrato:** as suítes do chat anônimo (E6, GR1–GR3, F5b, F6) rodam também contra `public_app` com as
     mesmas expectativas (fixture `cliente_publico`), com ajustes mecânicos 4.3 onde os testes lêem `ai_*` do banco
     do núcleo.

**SG7c — Dashboard, deploy e e2e.**
- O núcleo lê as métricas do canal anônimo de `public.sqlite` com `ATTACH` em somente leitura; observabilidade (E7),
  cartão Guardrails (GR5) e handoff (F6) continuam somando os dois canais.
- `deploy/Caddyfile` roteia as rotas `publica` do chat e do catálogo para a porta do serviço público e as demais
  públicas (cadastro, reset, checkout, webhook) para o núcleo; o teste do SG5 passa a validar isso.
- **E2E:** landing completa (catálogo, chat, matrícula, cadastro) contra os dois serviços; o harness `servidor_e2e_h1`
  sobe ambos. Painel da Gestão mostra as métricas do canal anônimo.

**Checklist:** itens 3 e 4 provados pelo teste 5; item 7 (inventário); item 8. **Tamanho:** G.
**Risco:** muitos testes lêem `ai_*` do banco do núcleo para o canal anônimo; o custo está nesses ajustes mecânicos.

## SG8 — Anti-bot nos pontos de entrada pública *(opcional, P6)*

**Contrato:** `TURNSTILE_SECRET` vazio = desligado (comportamento de hoje). Ligado, exigem `turnstile_token`:
abertura de sessão em `POST /api/chat`, `POST /api/auth/register`, `POST /api/auth/password-reset/request` e
`POST /api/payments/create-checkout`. Falta ou token inválido → 400 com texto fixo (revisão do PM). Se o verificador
cair: **fail-closed** em cadastro, reset e checkout; **fail-open** no chat, para não derrubar a vitrine (confirmar com
o PM). O cliente do verificador é injetável.
**Testes primeiro:** desligado nunca exige (guarda); cada rota rejeita sem token e com token inválido; aceita com
token válido do dublê; falha do verificador segue a política acima; nenhum teste chama a rede.
**Frontend:** widget na landing (chat e cadastro) e nas telas de cadastro e "esqueci a senha"; a CSP do SG6 libera
`challenges.cloudflare.com`. **E2E:** com o script substituído por stub (sem rede). **Tamanho:** M.

## SG9 — Segundo fator (TOTP) para a equipe *(opcional, P7)*

**Contrato:** configuração em "Meu perfil" do funcionário (segredo e código de configuração), 8 códigos de recuperação
guardados com hash; login em duas etapas: `POST /api/token` devolve `mfa_required` + `mfa_token` de 5 min com escopo
só de MFA, e `POST /api/token/mfa` troca pelo JWT; janela ±1 passo, anti-replay do último passo usado, 5 tentativas;
`STAFF_MFA_REQUIRED=1` obriga Gestão e Financeiro em produção; reset só pela Gestão, com evento de auditoria
`staff.mfa_reset`. Implementação própria da RFC 6238 com `hmac` (sem dependência nova).
**Testes primeiro:** vetores oficiais da RFC 6238; fluxo completo; replay; expiração; limites; recuperação; o
`mfa_token` não abre nenhuma outra rota; funcionário só configura o próprio MFA (IDOR); 401/403; auditoria.
**E2E:** login em duas etapas com gerador de código no teste. **Tamanho:** G.

## SG10 — Retenção e backup cifrado *(opcional, P9)*

**Contrato:** `CHAT_RETENTION_DAYS` apaga conversas e tópicos anônimos antigos no startup e uma vez por dia (aluno:
decisão de política junto da LGPD); backups do `operacao.py` cifrados com `BACKUP_ENCRYPTION_KEY`
(`.sqlite.enc`, permissão 0600, script de restauração).
**Testes primeiro:** com relógio falso, o que passou do prazo some e o resto fica; ida e volta do backup; chave errada
falha; nenhum arquivo em texto claro sobra; `ai_interactions` agregados do painel continuam corretos.
Depende de aprovar a dependência `cryptography`. **Tamanho:** M.

---

## O que este plano não cobre

- WAF, proteção contra DDoS de rede e pentest externo (o plano reduz a superfície; não substitui teste de terceiros).
- Migração para Postgres com papéis e RLS (é o equivalente de produção do SG7, fora do escopo do TCC).
- Rotação das credenciais e proteção da `main` (SG0 manual).
- Cadastro e checkout no serviço público (fase B do SG7).

## Critério de pronto

Cada entrega fecha com: testes escritos antes e vistos vermelhos pelo motivo certo, regressão verde (a não ser pelas
falhas conhecidas da D107), e2e quando houver tela, checklist de 9 itens, auditoria pré-push (D30), D11x no
`decisoes_tdd.md`, `PENDENCIAS.md` e `HANDOFF_TDD.md` atualizados. O plano inteiro fecha quando a onda 3 passa na
regressão completa e o texto dos itens "para revisão do PM" for aprovado.
