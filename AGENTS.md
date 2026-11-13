# AGENTS.md — Como continuar o projeto TDD da Fase 2

Este arquivo é para quem nunca viu o projeto: uma pessoa ou outro agente de IA que vai pegar o trabalho. Tudo o que você precisa para continuar está aqui ou nos arquivos que ele referencia. Nada depende de conversa anterior.

**Leia nesta ordem:**
1. Este `AGENTS.md` (processo, papéis, regras, comandos).
2. `docs/tdd/PENDENCIAS.md` (o que está fechado, o que falta, backlog).
3. `HANDOFF_TDD.md` (estado das branches e resultado de cada entrega, com hashes).
4. `docs/tdd/decisoes_tdd.md` (log integral de decisões, D0 a D33).
5. `docs/tdd/papeis_tdd.md` (charter original do gerente de projeto).
6. `Escopo_Fase2_Global_Training_Technology.pdf` (documento de escopo, na raiz).

Para mexer em qualquer tela, siga também `docs/DESIGN.md` (sistema visual da landing e da SPA, D106).

Em caso de conflito entre documentos, valem as decisões de número mais alto no `decisoes_tdd.md`. Algumas regras antigas foram revogadas (ver "Regras revogadas" abaixo).

---

> **Modo autônomo (D40, 06/10/2026):** em janelas autorizadas pelo PM, o orquestrador segue a própria recomendação, não pergunta, e passa à próxima entrega depois de fechar a atual. Mantidos: D30, D32, um agente por vez, ciclo TDD e a proibição de limpar o histórico do `.chrome-pdf-profile/`. Detalhes e a fila na D40 e em `docs/tdd/RELATORIO_NOITE.md`.

## 1. O modelo de trabalho

O projeto é a Fase 2 da plataforma Global Training Technology: área do aluno, área do funcionário, RBAC, observabilidade de IA e auditoria. O trabalho é feito em **TDD com três papéis e um gerente de projeto**.

- **Gerente de projeto (PM):** decide política e o que o usuário final percebe. Valida uma entrega por vez.
- **Orquestrador:** quem coordena. Lê o escopo, escreve as decisões de forma (ver seção 4), chama os agentes, verifica o resultado e reporta ao PM.
- **Agente-testes, dev-backend e dev-frontend:** os três agentes. Charter na seção 2.

**Por que foi montado assim:** o TDD força o teste a existir antes da implementação. Quem escreve o teste não é quem escreve o código, para que a implementação não caiba o teste à força. O PM fica de fora da forma, para decidir só política. Essa separação foi a principal proteção contra erro de processo do projeto, e as regras da seção 3 nasceram de erros reais.

**Ciclo por entrega:** sub-branch própria a partir de `feature/fase2-tdd` → commit de teste vermelho → commit de implementação só até o verde → suíte da entrega + regressão + e2e de navegador (quando houver tela) → checklist de 9 itens → merge `--no-ff` em `feature/fase2-tdd` → atualizar `PENDENCIAS.md` e `HANDOFF_TDD.md`, commit e push → reportar ao PM e **parar**.

---

## 2. Os agentes e seus charters

No Claude Code, os três agentes estão definidos em `.claude/agents/` (`agente-testes`, `dev-backend`, `dev-frontend`) e são chamados pelo nome (D35). O charter abaixo é a fonte; os arquivos o reproduzem.

### Agente-testes
- Escreve os testes **antes** do código, a partir do documento de escopo e das decisões do PM.
- **Observa o red** (teste falhando pelo motivo certo) e registra a saída antes de liberar a implementação.
- Depois da implementação, roda: testes da entrega, regressão (suítes existentes), segurança e comportamento ponta a ponta no navegador (Chromium headless).
- **Não escreve código de produção.**
- Se um teste estiver errado, reporta ao orquestrador. **Não altera o próprio teste depois que o dev começou**, sem aprovação.
- Ele é o único agente autorizado a alterar teste, e só nas condições da seção 4.2 (autoridade permanente).

### Dev-backend (FastAPI / SQLite)
- Implementa **somente até os testes passarem** (verde).
- **Não altera arquivos de teste.** Se achar teste errado, reporta ao orquestrador e **para**.

### Dev-frontend (Angular)
- Implementa Angular no padrão do projeto (NgModule, ApiService, guards, Bootstrap, Chart.js), **somente até os testes passarem**.
- **Não altera arquivos de teste.** Mesma regra do dev-backend: reporta e para.

**Regra que liga os três:** dev que discorda de um teste **reporta ao orquestrador e não reescreve o teste**. Isso aconteceu na E2 (D21): o teste estava codificando um comportamento que vazava existência de conta, e a correção veio pelo agente-testes com aprovação do PM. Não é precedente para o dev fazer o mesmo.

---

## 3. Regras de processo (com o motivo de cada uma)

Cada regra abaixo veio de um erro real. O erro está registrado para que ninguém repita.

1. **Um agente por vez no repositório.** *Motivo (D0):* dois agentes de teste foram lançados em paralelo na mesma árvore; o segundo sobrescreveu os arquivos do primeiro. Antes de chamar outro agente, confirmar que o anterior **retornou**.

2. **Árvore limpa antes de entregar o repo a um agente:** commit ou stash de tudo que estiver modificado ou não rastreado. *Motivo:* sem isso, o agente mistura o próprio trabalho com o que já estava na árvore e o commit fica com autoria confusa. Um dos achados da E3 foi exatamente árvore suja de outra autoria.

3. **Agente sempre em primeiro plano.** Nunca encerrar o turno esperando notificação de um agente em segundo plano. *Motivo:* o orquestrador acabava o turno achando que o trabalho estava feito, enquanto o agente ainda escrevia arquivos.

4. **Não usar widget de pergunta interativa.** Dúvida vai em texto, no relatório. *Motivo:* a sessão anterior travou num widget de pergunta e ficou presa, sem conseguir avançar nem ser respondida a tempo. Esse travamento foi um dos motivos da sessão ter morrido.

5. **Nunca rodar a suíte em paralelo com outra execução do repo.** *Motivo (D29):* uma execução paralela deu 26/55 sem reprodução em execução limpa; uso concorrente foi a causa provável.

6. **Autovigilância obrigatória (D32).** Parar o ciclo se: um agente retornar incompleto duas vezes seguidas; o orquestrador repetir a mesma análise em rodadas consecutivas; ou houver perda de rastro do que já foi feito. Ao parar: deixar a árvore limpa e commitada, atualizar `PENDENCIAS.md` e `HANDOFF_TDD.md`, e avisar o PM que precisa de sessão nova. *Motivo:* a sessão anterior morreu de esgotamento e continuou mexendo no repo enquanto degradava. Parar a tempo é resultado bom; forçar e corromper entrega não é.

### Regras revogadas (não seguir)
- ~~"Nunca fazer push"~~ — **revogada pela D30.** Push está liberado, com os limites abaixo.
- ~~"Parar depois da E3"~~ — **revogada pela D31.** O objetivo é fechar as nove entregas, com ritmo de uma por vez.

### Limites do push (D30, continuam valendo)
- Repositório `origin` é **público** (`https://github.com/gusteluti/global-training-technology.git`).
- **Nunca tocar na `main`:** sem push para `main`, sem merge em `main`.
- **Nunca force-push**, em branch nenhuma.
- Push rejeitado por divergência: **parar e avisar o PM.** Não forçar, não resolver sozinho.
- **Antes de cada push, auditar o que será publicado:** nenhum `.env`, `db.sqlite`, token de teste, credencial ou `.chrome-pdf-profile/` pode subir. Achando qualquer um, parar antes do push e reportar.

---

## 4. Modelo de autoridade

### 4.1 O que o orquestrador decide sozinho
São decisões de **forma**, sem efeito sobre o que o usuário percebe nem sobre a política do projeto:
- nome de campo e de parâmetro;
- formato de data e de número;
- estrutura da resposta JSON, desde que siga o padrão já usado no projeto;
- status **dentro** do vocabulário já fechado (ex.: os status de matrícula são `pending`, `active`, `cancelled`, `refunded`; escolher qual deles um caso usa é decisão de forma);
- ordenação de listas.

Essas decisões são registradas no log, mas não sobem ao PM.

### 4.2 O que sobe para o PM
- **Política** (ex.: quem pode ver dado financeiro, quando um link de senha expira);
- **o que o usuário percebe** (ex.: mensagem de erro, o que aparece na tela, se um e-mail é enviado);
- **contrato** da API, **conflito de requisitos** e **corte de escopo**.

Na dúvida entre forma e política, **sobe para o PM**.

### 4.3 Autoridade permanente (concedida pelo PM)
O orquestrador **não precisa consultar o PM** quando a alteração de teste é consequência mecânica de uma decisão já aprovada e registrada, desde que **todas** as condições abaixo valham:
- (a) a decisão de origem está aprovada e registrada no `decisoes_tdd.md`;
- (b) a intenção do teste é preservada, ou sua revogação já foi decidida pelo PM;
- (c) quem altera é o **agente-testes**, nunca o dev;
- (d) fica registrado no log, com o encadeamento explícito (ex.: D21 → D25 → D27).

**Decisão nova** (contrato, comportamento visível, conflito de requisitos, corte de escopo) continua vindo ao PM. Esta autoridade **não é precedente** para mudar política.

---

## 5. Checklist de 9 itens (fecha toda entrega)

Os itens vêm do handoff. Os dois obrigatórios do PM (**IDOR** e **recurso pago liberado só com matrícula ativa**) continuam valendo em toda entrega onde fizerem sentido.

1. A entrega faz exatamente o que o escopo pede, sem extrapolar.
2. Os testes da entrega foram escritos antes da implementação e observados vermelhos, pelo motivo certo, com a saída registrada.
3. **IDOR (obrigatório, quando houver endpoint de usuário):** acesso a recurso alheio devolve o mesmo erro de inexistente (404), e nenhum endpoint aceita identificador de usuário vindo do cliente.
4. **Recurso pago liberado só com matrícula ativa (obrigatório, quando houver conteúdo pago):** `pending`, `cancelled` e `refunded` não liberam nenhuma URL de material em nenhum lugar da resposta.
5. Compatibilidade: dado ou curso sem o campo novo continua aceito e devolve o padrão vazio.
6. Campos novos aceitos também no schema de escrita do admin, quando aplicável.
7. Controle de acesso: perfil sem permissão recebe 403; sem token ou com token forjado recebe 401.
8. Frontend (quando a entrega tiver tela): o recurso aparece e funciona no navegador, com e2e passando, e o build Angular fica limpo.
9. Ciclo TDD completo: red antes do código, regressão verde depois, e atualização de `PENDENCIAS.md` e `HANDOFF_TDD.md`.

---

## 6. Como rodar

Todos os comandos assumem a raiz do repo como diretório de trabalho e Windows com Python 3.14 (`py -3`). Não há `.env` versionado; ver a seção "Variáveis de ambiente".

### 6.1 Variáveis de ambiente
Nomes lidos pelo backend (valores **nunca** no repo):

`ACCESS_TOKEN_EXPIRE_MINUTES`, `ADMIN_PASSWORD`, `ADMIN_TOKEN_SECRET`, `API_BASE_URL`, `APP_ENV`, `BACKUP_DIR`, `BACKUP_KEEP`, `CHAT_ANON_DAILY_MESSAGES_PER_IP`, `CHAT_ANON_DAILY_TOKEN_BUDGET`, `CHAT_ANON_NEW_SESSIONS_PER_IP_HOUR`, `CONTENTS_DIR`, `CORS_ALLOWED_ORIGINS`, `FINANCIAL_PASSWORD`, `FRONTEND_BASE_URL`, `GROQ_API_KEY`, `GROQ_MODEL`, `GROQ_PRICE_INPUT_PER_1M_USD`, `GROQ_PRICE_OUTPUT_PER_1M_USD`, `JWT_SECRET_KEY`, `MERCADO_PAGO_ACCESS_TOKEN`, `MERCADO_PAGO_WEBHOOK_SECRET`, `PASSWORD_LINK_OUTBOX`, `PAYMENTS_MOCK`, `SMTP_FROM`, `SMTP_HOST`, `SMTP_PASSWORD`, `SMTP_PORT`, `SMTP_USER`, `SUPPORT_PASSWORD`, `TRUSTED_PROXIES`, `WHATSAPP_HANDOFF_NUMBER`.

**Configuração de produção (SG2, D109).** Em produção o `APP_ENV=production` precisa estar **explícito** (ausente vale como não produção para a validação, embora a documentação da API já o trate como produção, SG1). Com ele, o startup chama `core/configuracao.py` e o app **não sobe** (RuntimeError listando todos os problemas, sem valor de segredo) se: `JWT_SECRET_KEY` ausente ou com menos de 32 caracteres; `ADMIN_TOKEN_SECRET` ausente ou igual a uma senha de perfil; `ADMIN_PASSWORD`/`FINANCIAL_PASSWORD`/`SUPPORT_PASSWORD` (quando definidas) com menos de 12 caracteres ou iguais à senha pública do `seed_demo`; `PAYMENTS_MOCK` ligado; `MERCADO_PAGO_WEBHOOK_SECRET` ou `MERCADO_PAGO_ACCESS_TOKEN` vazio; `CORS_ALLOWED_ORIGINS` ausente, com `localhost`/`127.0.0.1` ou origem `http://`. Fora de produção o app sobe e escreve um `[AVISO]` por problema. Em produção também: `POST /api/admin/login` (login legado por senha única) responde 404 e o token legado de funcionário é recusado (401); `ADMIN_TOKEN_SECRET` não cai mais para `ADMIN_PASSWORD`. O código de validação do certificado exige `JWT_SECRET_KEY` em qualquer ambiente (sem fallback fixo).

**IP real atrás de proxy (SG3, D109 P4).** `TRUSTED_PROXIES` (opcional; IPs e CIDRs IPv4/IPv6 separados por vírgula; **padrão vazio** = só o par TCP vale e `X-Forwarded-For` é ignorado). Lida a cada requisição; entradas inválidas são ignoradas e nunca derrubam o app. Só quando o par TCP está na lista, `core/cliente_ip.py` lê `X-Forwarded-For` da direita para a esquerda, pula proxies confiáveis e usa o primeiro item que não é proxy (malformado = par TCP; se todos são proxies, o mais à esquerda). Vale para os limites de chat, checkout e checagem de token de senha (`rate_limit`) e para o bloqueio de login (`login_limit`, `login_attempts`, `auth.locked`). **Cuidado:** o uvicorn 0.24 liga `--proxy-headers` por padrão e confia em `127.0.0.1`; em produção atrás de proxy o app deve rodar com `proxy_headers=False` (`--no-proxy-headers`) para valer só a regra do projeto. Essa mudança de execução fica para a SG5.

**Teto de custo e de abuso do chat anônimo (SG4, D109 P5).** Três variáveis opcionais, **desligadas por padrão** (ausente, vazia, `0`, inválida ou negativa = desligado), lidas a cada requisição, só para `POST /api/chat` (o chat do aluno não é afetado). `CHAT_ANON_DAILY_TOKEN_BUDGET`: soma de `ai_usage.total_tokens` do canal anônimo no dia de São Paulo (`core/fuso.py`); com a soma >= teto, o chat anônimo devolve 200 com a resposta fixa `CHAT_INDISPONIVEL` (`agents/llm_guard.py`), sem chamar o LLM (nem roteamento nem classificador), `outcome='unresolved'`, `guard='budget'` (valor novo do vocabulário fechado e de `AI_GUARDS`; cartão Guardrails do painel) e a ação de handoff da F6 quando `WHATSAPP_HANDOFF_NUMBER` é válido; falha ao ler o banco = o chat segue (fail-open). `CHAT_ANON_DAILY_MESSAGES_PER_IP` (janela deslizante de 24 h) e `CHAT_ANON_NEW_SESSIONS_PER_IP_HOUR` (sessões novas, 1 h) usam o IP efetivo da SG3 e respondem 429 `ERRO_CHAT`; o estado fica em memória do processo (`core/rate_limit.py`, zerado em `redefinir_limites()`), por isso **um único worker** em produção. Sugestões de produção: 300000 tokens/dia, 200 mensagens/IP/dia, 20 sessões novas/IP/hora. Ordem no `POST /api/chat`: 429 por IP (minuto, diário, sessões novas) -> mensagem vazia/longa -> teto de tokens (resposta fixa) -> guardrails de entrada -> LLM.

Os e2e não precisam de variável nenhuma (D58): os helpers definem valores fabricados no processo do backend de teste.

Duas formas de fornecer as variáveis, sem commitar nenhuma:
- criar `backend/.env` a partir de `.env.example` (o arquivo é ignorado pelo git), **ou**
- passar no ambiente da sessão, como foi feito na validação da E3.

### 6.2 Suíte de backend (pytest) — e regressão
```
cd backend
python -m pytest tests
```
`backend/tests/conftest.py` aponta `DB_PATH` para um arquivo temporário; a suíte não toca o `db.sqlite` de desenvolvimento. **A regressão** (E1, E2 e fase 2) está dentro dessa mesma suíte: na E3 o resultado foi 81 passed. Não rodar em paralelo com outra execução do repo.

### 6.3 E2E de navegador (Chromium via Playwright)
Desde a D58, **todo e2e sobe os próprios servidores**: backend (processo próprio, banco SQLite temporário, diretório de
cursos temporário, Groq e Mercado Pago falsos, segredo de webhook e CORS de teste, contas de funcionário fabricadas) e
`ng serve` em portas livres com proxy temporário. Não é preciso subir nada à mão, não depende de `.env` real e **não
toca** `backend/db.sqlite` nem `backend/courses` (D7 resolvida). Pré-requisitos: Python com `fastapi`/`uvicorn`/`playwright`,
`frontend/node_modules` e o Chromium (`py -3 -m playwright install chromium`).
Execute da raiz do repo, **um por vez, nunca em paralelo**, com `PYTHONUTF8=1 PYTHONIOENCODING=utf-8` no Windows:
```
py -3 -m pytest frontend/e2e/test_admin_angular.py -s              # 33 checks (funcionário, RBAC, reembolso)
py -3 -m pytest frontend/e2e/test_e2_conta_aluno_angular.py -s     # 8 checks
py -3 -m pytest frontend/e2e/test_e3_painel_angular.py -s          # 7 checks
py -3 -m pytest frontend/e2e/test_e5_chat_aluno_angular.py -s      # 11 checks
py -3 -m pytest frontend/e2e/test_e5_dashboard_alunos_angular.py -s  # 9 checks
py -3 -m pytest frontend/e2e/test_e6_landing_chat.py -s            # 8 testes
py -3 -m pytest frontend/e2e/test_e7_observabilidade_angular.py -s # 11 checks
py -3 -m pytest frontend/e2e/test_e8_auditoria_angular.py -s       # 17 checks
py -3 -m pytest frontend/e2e/test_l1_turmas_angular.py -s          # 16 checks
py -3 -m pytest frontend/e2e/test_l2_cadastro_cursos_angular.py -s # 24 checks
py -3 -m pytest frontend/e2e/test_b1_recuperacao_senha_angular.py -s # 10 checks
py -3 -m pytest frontend/e2e/test_b2_recibo_pdf_angular.py -s      # 8 checks
py -3 -m pytest frontend/e2e/test_d1_design_landing_angular.py -s  # 10 checks (design da landing, D66)
py -3 -m pytest frontend/e2e/test_d2_area_aluno_angular.py -s      # 10 checks (área do aluno, D67)
py -3 -m pytest frontend/e2e/test_d3_ajustes_design_angular.py -s  # 10 checks (ajustes de design, D93)
py -3 -m pytest frontend/e2e/test_d3_landing_vitrine.py -s         # 5 testes (landing: APP_URL e curso no login, D93)
py -3 -m pytest frontend/e2e/test_d4_polimento_visual.py -s     # 2 testes, 17 checks (polimento visual, D106)
py -3 -m pytest frontend/e2e/test_x5_atualizacao_paineis_angular.py -s # 10 checks (atualização automática dos painéis, D87)
py -3 -m pytest frontend/e2e/test_o0_catalogo_angular.py -s  # 7 checks (catálogo do aluno, O0)
py -3 -m pytest frontend/e2e/test_f1_trava_exclusao_angular.py -s  # 11 checks (arquivar curso, F1)
py -3 -m pytest frontend/e2e/test_f2_fuso_horario_angular.py -s  # 10 checks (horário de SP, F2)
py -3 -m pytest frontend/e2e/test_s1_compra_duplicada_angular.py -s  # 7 checks (compra duplicada, S1)
py -3 -m pytest frontend/e2e/test_f3_aluno_curso_angular.py -s  # 11 checks (aluno e curso, F3/F4)
py -3 -m pytest frontend/e2e/test_u1_busca_csv_angular.py -s  # 13 checks (busca e CSV, U1/U2)
py -3 -m pytest frontend/e2e/test_f5a_turma_checkout_angular.py -s  # 8 checks (turma no checkout, F5a)
py -3 -m pytest frontend/e2e/test_f5b_chat_turmas_angular.py -s  # chat com turmas (F5b)
py -3 -m pytest frontend/e2e/test_f5b_landing_chat_turmas.py -s  # 6 testes (landing, F5b)
py -3 -m pytest frontend/e2e/test_f6_handoff_angular.py -s  # WhatsApp no chat (F6)
py -3 -m pytest frontend/e2e/test_f6_landing_handoff.py -s  # 5 testes (landing, F6)
py -3 -m pytest frontend/e2e/test_f7_curso_anexo_angular.py -s  # 11 checks (curso por anexo, F7)
py -3 -m pytest frontend/e2e/test_s2_limites_angular.py -s  # 5 checks (limite de login, S2)
py -3 -m pytest frontend/e2e/test_s4_conta_aluno_angular.py -s  # 12 checks (conta do aluno, S4)
py -3 -m pytest frontend/e2e/test_u4_matricula_manual_angular.py -s  # 7 checks (matrícula manual, U4)
py -3 -m pytest frontend/e2e/test_u5_cancelamento_angular.py -s  # 8 checks (cancelamento, U5)
py -3 -m pytest frontend/e2e/test_u8_turmas_angular.py -s  # 10 checks (turmas, U8)
py -3 -m pytest frontend/e2e/test_s3_equipe_angular.py -s  # equipe (S3)
py -3 -m pytest frontend/e2e/test_u7_lgpd_angular.py -s  # LGPD (U7)
py -3 -m pytest frontend/e2e/test_x1_progresso_angular.py -s  # progresso e certificado (X1)
py -3 -m pytest frontend/e2e/test_x2_avaliacao_angular.py -s  # avaliação (X2)
py -3 -m pytest frontend/e2e/test_x4_saude_angular.py -s  # saúde do sistema (X4)
py -3 -m pytest frontend/e2e/test_c_sala_curso_angular.py -s  # sala do curso (D103)
py -3 -m pytest frontend/e2e/test_video_real_angular.py -s  # videoaula com vídeo real, precisa de internet (D105)
py -3 -m pytest frontend/e2e/test_qa_istqb.py -q  # suíte de QA, 518 casos (D104)
```
Portas e esperas podem ser fixadas com `E2E_BACKEND_PORT`, `E2E_FRONT_PORT` e `E2E_NG_TIMEOUT`. Se houver um `ng serve` seu na
porta 4200, ele não é usado nem encerrado. Cada e2e leva de 20 a 90 s. Contagens validadas em 21/10/2026: os 37 e2e passaram, um por vez (~25 min).

### 6.3.1 Dados de demonstração
Para testar à mão, sem dados reais, rode a partir de `backend/`: `python seed_demo.py`. Cria contas de teste (a senha é impressa
no final), turmas, matrículas e conteúdos no curso Excel Profissional. Pode rodar mais de uma vez e não roda com
`APP_ENV=production`. Para a compra sair aprovada na hora, use `APP_ENV=development` e `PAYMENTS_MOCK=1` no `backend/.env`.

### 6.4 Build do Angular
```
cd frontend
npx ng build
```
O script `build` do `package.json` é `ng build`. O build de desenvolvimento foi validado limpo na E3.

---

## 7. Para onde ir agora

O que está fechado, o que falta, as dívidas e o backlog estão em **`docs/tdd/PENDENCIAS.md`**. Ler esse arquivo antes de começar qualquer entrega.
