# TCC School Chatbot - Backend

Sistema de chatbot com agents LangChain para gerenciar múltiplos cursos em uma plataforma educacional.

**LLM**: Groq (Mixtral 8x7b) - Rápido, grátis, sem limite de tráfego sensível

## 🏗️ Arquitetura

```
backend/
├── app.py                  # FastAPI main app
├── db.py                   # SQLite database setup
├── requirements.txt        # Python dependencies
├── agents/
│   ├── manager_agent.py    # Gerencia routing com Groq LLM
│   └── course_agent.py     # Agents específicos com Groq LLM
├── courses/                # 📌 Dados dos cursos em JSON (editáveis!)
│   └── example_course.json
└── admin/
    └── routes.py           # Endpoints para criar/editar cursos
```

## 🚀 Como funciona

### 1. **Carregamento dinâmico de cursos**
- Todo arquivo JSON em `courses/` é carregado automaticamente ao iniciar o backend
- Manager agent tem acesso a todos os cursos

### 2. **Fluxo de conversação com LLM**
```
Frontend → POST /api/chat → Manager Agent (Groq LLM)
   ├─→ Identifica intenção/curso (LLM)
   └─→ Route para Course Agent (Groq LLM) → Resposta personalizada
```

### 3. **Criação de novo curso (Admin)**
```
Admin preenche formulário → POST /api/admin/create-course →
Backend cria arquivo JSON → Manager carrega automaticamente
```

## 📋 Endpoints disponíveis

### Chat
- `POST /api/chat` - Enviar mensagem ao chatbot (com LLM)
- `GET /health` - Health check com info da LLM

### Admin
- `POST /api/admin/create-course` - Criar novo curso
- `GET /api/admin/courses` - Listar todos os cursos
- `GET /api/admin/course/{course_id}` - Detalhes de um curso
- `PUT /api/admin/course/{course_id}` - Atualizar curso
- `DELETE /api/admin/course/{course_id}` - Deletar curso

## 🗂️ Estrutura de um curso (JSON)

Ver `courses/example_course.json` para exemplo completo:

```json
{
  "id": "python_basics",
  "name": "Python Básico",
  "description": "...",
  "price": 99.90,
  "duration_hours": 20,
  "level": "Iniciante",
  "target_audience": "...",
  "objectives": [...],
  "topics": [...],
  "benefits": [...],
  "faq": [
    {
      "question": "...",
      "answer": "..."
    }
  ],
  "system_prompt": "...",
  "created_at": "2026-05-04"
}
```

## ⚙️ Setup com Groq

### 1. Instalar dependências
```bash
pip install -r requirements.txt
```

### 2. Obter Groq API Key
- Acesse [console.groq.com](https://console.groq.com)
- Crie uma conta
- Gere uma API Key

### 3. Configurar variáveis de ambiente
```bash
cp .env.example .env
# Editar .env com sua GROQ_API_KEY
```

### 4. Iniciar servidor
```bash
python app.py
```

**Ver [GROQ_SETUP.md](./GROQ_SETUP.md) para instruções detalhadas**

## 🧪 Testar endpoints

### Chat com LLM
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Qual é o melhor curso para iniciantes?"}'
```

### Health Check
```bash
curl http://localhost:8000/health
```

### Listar cursos
```bash
curl http://localhost:8000/api/admin/courses
```

## 🔒 Segurança

✅ Frontend **apenas** faz chamadas HTTP para o backend
✅ Toda lógica de IA/agents no backend
✅ Dados sensíveis (GROQ_API_KEY) em .env
✅ CORS configurado
✅ SQL Injection prevenido (prepared statements)

## ⚡ Características do Groq

- 🚀 **Ultra-rápido**: ~20-50ms de latência
- 💰 **Grátis**: ~9.000 requisições/dia sem limite de tráfego
- 🧠 **Modelos bons**: Mixtral 8x7b (padrão), Llama 2, Gemma
- 🔧 **Fácil integração**: Apenas uma chave de API

## 📝 Próximos passos

1. ✅ Integração completa com Groq LLM
2. [ ] Criar frontend (HTML/JS) com admin panel melhorado
3. [ ] Adicionar pagamento (RazorPay/Stripe)
4. [ ] Melhorar routing (histórico inteligente)
5. [ ] Analytics e logs

