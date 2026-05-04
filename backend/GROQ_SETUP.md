# Setup com Groq

## 🚀 Passo a passo para integrar Groq

### 1. Obter Groq API Key

1. Acesse [console.groq.com](https://console.groq.com)
2. Faça login/crie uma conta
3. Vá em "API Keys" no menu lateral
4. Clique em "Create API Key"
5. Copie a chave

### 2. Configurar .env

```bash
# No backend/, copie .env.example para .env
cp .env.example .env

# Adicione sua Groq API key e modelo
GROQ_API_KEY=seu_groq_api_key_aqui
GROQ_MODEL=openai/gpt-oss-120b
ENVIRONMENT=development
```

### 3. Instalar dependências

```bash
cd backend
pip install -r requirements.txt
```

### 4. Rodar o servidor

```bash
python app.py
```

Servidor será iniciado em `http://localhost:8000`

## 📋 Testar a integração

### Health Check
```bash
curl http://localhost:8000/health
```

**Resposta esperada:**
```json
{
  "status": "ok",
  "courses_loaded": 1,
  "llm": "groq",
  "available_models": ["mixtral-8x7b-32768"]
}
```

### Chat com LLM
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Qual é o melhor curso para iniciantes?", "session_id": "test123"}'
```

**Resposta esperada:**
```json
{
  "status": "success",
  "message": "Resposta gerada pelo Groq...",
  "session_id": "test123"
}
```

## ⚙️ Modelos disponíveis no Groq

- `mixtral-8x7b-32768` (Padrão) - Bom balanceamento entre velocidade e qualidade
- `llama2-70b-4096` - Mais preciso mas um pouco mais lento
- `gemma-7b-it` - Rápido e bom para instruções

## 📊 Limites gratuitos do Groq

- ~9.000 requisições/dia
- Rate limit: ~170 requisições/minuto
- Latência: ~20-50ms

## 🐛 Debugging

### Erro: "GROQ_API_KEY not found"
- Verifique se o arquivo `.env` existe
- Verifique se a chave está correta
- Reinicie o servidor

### Erro de conexão
- Verifique sua internet
- Confirme a API key em console.groq.com

### Resposta lenta
- Isso é normal no Groq (20-50ms)
- Se demorar mais, pode ser problema de rede

## ✅ Pronto!

Agora o chatbot está usando Groq para:
- ✨ Manager Agent (identifica intenção e roteia)
- 🎓 Course Agents (responde específico de cada curso)
