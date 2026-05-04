# 🚀 Quick Start - Groq Integration

## Resumo do que foi feito

✅ **Integração completa com Groq LLM**
- Manager Agent agora usa Groq para identificar intenção
- Course Agents usam Groq para responder com conhecimento do curso
- Todas as respostas são geradas com IA real!

## ⚡ 3 passos para rodar

### 1️⃣ Obter Groq API Key (2 minutos)
```
1. Acesse https://console.groq.com
2. Crie conta / faça login
3. Vá em "API Keys"
4. Copie sua chave
```

### 2️⃣ Configurar backend
```bash
cd backend

# Copiar template .env
cp .env.example .env

# Abrir .env e adicionar sua chave
# GROQ_API_KEY=sua_chave_aqui

# Instalar dependências
pip install -r requirements.txt
```

### 3️⃣ Rodar servidor + testar
```bash
# Terminal 1: Rodar servidor
python app.py

# Terminal 2 (em outro terminal): Testar
python test_api.py
```

## 🤖 O que mudou

### Antes (sem LLM)
```
User: "Qual curso é bom?"
Bot: "Aqui estão os cursos: [lista estática]"
```

### Agora (com Groq LLM)
```
User: "Qual curso é bom para iniciantes?"
→ Manager Agent (Groq) analisa a mensagem
→ Identifica que é pergunta geral
→ Course Agent gera resposta personalizada com Groq
Bot: "Para iniciantes, recomendo Python Básico! 📚
      • São apenas 20 horas de estudo
      • Você aprenderá do zero
      • Certificado ao final
      Quer ver mais detalhes?"
```

## 📊 URLs de teste

```bash
# Health check
curl http://localhost:8000/health

# Chat com LLM
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Oi! Qual é o curso mais barato?"}'

# Listar cursos
curl http://localhost:8000/api/admin/courses
```

## 🎯 Fluxo completo

```
┌─────────────────────────────────────────────────┐
│                                                 │
│         Frontend (HTML/React)                  │
│                                                 │
└────────────┬──────────────────────────────────┘
             │
             │ POST /api/chat
             │ {"message": "..."}
             │
┌────────────▼──────────────────────────────────┐
│                                                 │
│  Manager Agent (Groq Mixtral 8x7b)            │
│  • Analisa intenção                            │
│  • Roteia para Course Agent                    │
│                                                 │
└────────────┬──────────────────────────────────┘
             │
             ├─► Course Agent Python (Groq)
             ├─► Course Agent Node.js (Groq)
             └─► Course Agent React (Groq)
                (cada um specializado em seu curso)
             │
┌────────────▼──────────────────────────────────┐
│                                                 │
│  Resposta personalizada com IA!                │
│                                                 │
└────────────┬──────────────────────────────────┘
             │
             │ {"status": "success", "message": "..."}
             │
┌────────────▼──────────────────────────────────┐
│                                                 │
│         Frontend mostra resposta               │
│                                                 │
└────────────────────────────────────────────────┘
```

## 📚 Próximas features

- [ ] Frontend chat widget melhorado
- [ ] Histórico de conversas persistente
- [ ] Análise de intenção mais inteligente
- [ ] Integração com pagamento
- [ ] Analytics

## ❓ Dúvidas?

### "Quanto custa o Groq?"
- Grátis! ~9.000 requisições/dia sem limite de tráfego sensível

### "Por que Groq e não OpenAI?"
- Groq é 10x mais rápido (20-50ms)
- Completamente grátis
- Sem limites de tráfego preocupantes

### "Preciso mudar algo para adicionar novo curso?"
- Não! Apenas:
  1. Preencha o formulário em `frontend/admin.html`
  2. Backend cria o JSON automaticamente
  3. Groq já carrega e entende o novo curso

## ✨ Ready?

Bora testar? 🚀
```bash
python app.py
python test_api.py
```
