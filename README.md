# TCC School Chatbot

Sistema de chatbot com LangChain agents para gerenciar múltiplos cursos em uma plataforma educacional.

## 📁 Estrutura do Projeto

```
projeto-tcc/
├── backend/              # FastAPI + LangChain agents
│   ├── app.py
│   ├── agents/          # Manager e Course agents
│   ├── courses/         # JSONs dos cursos (editáveis!)
│   ├── admin/           # Endpoints de administração
│   └── db.py            # SQLite setup
├── frontend/            # HTML + JS
│   ├── index.html       # Landing + Chat
│   └── admin.html       # Admin panel para criar cursos
└── README.md
```

## 🎯 Objetivo da Fase 1

Criar uma arquitetura simples e extensível onde:
1. **Manager Agent** roteia conversas para agents específicos
2. **Course Agents** respondem com conhecimento do curso (via JSON)
3. **Admin Panel** permite adicionar novos cursos sem tocar no código
4. **Frontend** apenas chama a API (segurança)

## 🚀 Quick Start

### Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env  # Editar com sua OPENAI_API_KEY
python app.py
```

### Frontend
Abra `frontend/admin.html` no navegador para testar criação de cursos.

## 📝 Como adicionar um novo curso

### Opção 1: Pelo Admin Panel (Fácil!)
1. Abra `frontend/admin.html`
2. Preencha o formulário
3. Clique em "Criar Curso"
4. Backend automaticamente cria o JSON e carrega

### Opção 2: Adicionar JSON manualmente
Crie um arquivo em `backend/courses/seu_curso.json` com a estrutura de `example_course.json`

## 🔑 Próximos passos

- [ ] Integrar LLM real (OpenAI/local)
- [ ] Melhorar routing do manager agent
- [x] Adicionar histórico de conversas (sessões)
- [x] Integrar gateway de pagamento
- [ ] Criar landing page completa

## 🔒 Segurança

✅ Toda lógica no backend
✅ API endpoint bem definido
✅ Dados sensíveis em .env
✅ CORS configurado
✅ SQL Injection prevenido (prepared statements)

### Configuração de produção (SG2)

Defina `APP_ENV=production` explicitamente. No startup o app valida a configuração e **não sobe** se faltar ou estiver
insegura (a mensagem lista as variáveis, nunca os valores): `JWT_SECRET_KEY` (mínimo de 32 caracteres),
`ADMIN_TOKEN_SECRET` (próprio, diferente das senhas de perfil), senhas de perfil com 12 caracteres ou mais e diferentes
das senhas públicas do `seed_demo`, `PAYMENTS_MOCK` desligado, `MERCADO_PAGO_WEBHOOK_SECRET` e
`MERCADO_PAGO_ACCESS_TOKEN` preenchidos, e `CORS_ALLOWED_ORIGINS` só com origens `https://` (sem localhost). Fora de
produção o app sobe e registra `[AVISO]` para cada problema. Em produção o login legado por senha única
(`POST /api/admin/login`) fica desligado (404) e o token legado de funcionário não vale.

### IP real atrás de proxy (SG3)

Atrás de nginx, Caddy ou NAT todos chegam com o IP do proxy, e os limites por IP (chat, checkout, checagem de token de
senha e bloqueio de login) passariam a valer para todos juntos. A variável opcional `TRUSTED_PROXIES` (IPs e CIDRs
separados por vírgula, IPv4 ou IPv6) diz quais pares TCP são proxies confiáveis. **Padrão vazio**: vale o par TCP e o
cabeçalho `X-Forwarded-For` é ignorado. Com a lista preenchida e o par TCP nela, o IP do cliente é o primeiro item do
cabeçalho, lendo da direita para a esquerda, que não seja um proxy confiável; cabeçalho malformado volta ao par TCP, e
par fora da lista tem o cabeçalho ignorado. Entradas inválidas da lista são ignoradas.

> **Aviso (uvicorn):** o uvicorn 0.24 liga `--proxy-headers` por padrão e confia em `127.0.0.1`. Em produção, atrás de
> proxy, o app deve rodar com `proxy_headers=False` (`--no-proxy-headers`) para valer só a regra do projeto. Essa
> mudança de execução será feita na SG5; por ora está apenas documentada.

## 🧭 Fase 2 - Área do Funcionário e Governança

A Fase 2 evolui o MVP com o painel administrativo completo descrito no
escopo do TCC (`Escopo_Fase2_Global_Training_Technology.pdf`), priorizando
a Área do Funcionário:

- **RBAC (`backend/core/security.py`)**: três perfis de acesso —
  `Gestão` (`ADMIN_PASSWORD`), `Financeiro` (`FINANCIAL_PASSWORD`, opcional)
  e `Suporte` (`SUPPORT_PASSWORD`, opcional). Cada perfil recebe um token
  assinado com o próprio papel; endpoints sensíveis usam
  `Depends(require_roles(...))` para restringir acesso (ex.: apenas
  Gestão/Financeiro veem o Dashboard Financeiro).
- **Dashboards (`backend/dashboard/routes.py`)**: `/api/dashboard/alunos`,
  `/cursos`, `/financeiro` e `/observabilidade-ia`. São consumidos pela
  aplicação Angular (`frontend/`), que é a interface oficial: abas de
  Financeiro, Alunos, Cursos, Observabilidade de IA e Auditoria, filtradas
  pelo perfil do usuário logado.
- **Legado**: `frontend/admin.html` continua funcionando fora de produção, com o login por
  senha de perfil (`/api/admin/login`), mas não é mais a tela de entrega. Com
  `APP_ENV=production` esse login responde 404 (SG2): em produção só entram contas
  de funcionário (`POST /api/token`).
  Cadastro e edição de cursos ainda estão só nele.
- **Trilhas de auditoria**: tabela `audit_logs` no SQLite; toda alteração
  de preço, criação/edição/remoção de curso e reembolso é registrada com
  perfil responsável e estampa de tempo, visível na aba "Auditoria"
  (restrita ao perfil Gestão).
- **Persistência real de matrículas/pagamentos**: `create-checkout` e o
  webhook do Mercado Pago agora gravam aluno, matrícula e pagamento no
  SQLite (antes eram apenas registrados em log), alimentando os
  dashboards. Novo endpoint `POST /api/payments/refund/{payment_id}` marca
  um pagamento como reembolsado (Gestão/Financeiro) com auditoria.
- **Observabilidade do Chatbot (RF24)**: o `ManagerAgent` contabiliza
  volume de mensagens, mensagens por curso e tópicos não compreendidos
  (perguntas gerais sem curso identificado) em memória.

Itens do escopo da Fase 2 não incluídos nesta entrega (fora da prioridade
"tela administrativa" definida para esta etapa): Área do Aluno com login
próprio via JWT, migração do frontend para Angular/SPA e os filtros de
segurança de LLM contra prompt injection (OWASP for LLMs).
