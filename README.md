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
- [ ] Adicionar histórico de conversas (sessões)
- [ ] Integrar gateway de pagamento
- [ ] Criar landing page completa

## 🔒 Segurança

✅ Toda lógica no backend
✅ API endpoint bem definido
✅ Dados sensíveis em .env
✅ CORS configurado
✅ SQL Injection prevenido (prepared statements)
