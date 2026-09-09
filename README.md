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
  `/cursos`, `/financeiro` e `/observabilidade-ia`, consumidos pelas novas
  abas do `frontend/admin.html` (Dashboard de Alunos, Dashboard de Cursos,
  Dashboard Financeiro e Observabilidade de IA), seguindo o mesmo design já
  usado no cadastro de cursos.
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
