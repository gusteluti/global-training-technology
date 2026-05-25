# Plano de Testes - Global Training Technology

Este documento explica como rodar o projeto localmente e como testar as principais funcionalidades do MVP.

O objetivo é permitir que outra pessoa valide o sistema inteiro de forma simples, registrando o que funcionou e o que falhou.

---

## 1. Visão geral do projeto

O sistema possui:

- Landing page pública de cursos.
- Chatbot com IA integrado ao backend.
- Painel administrativo protegido por login.
- Cadastro dinâmico de cursos.
- Integração com Mercado Pago Checkout Pro.
- Estrutura preparada para banco SQLite.

Principais arquivos:

```text
frontend/
├── landing_global_training.html
└── admin.html

backend/
├── app.py
├── requirements.txt
├── agents/
├── admin/
├── payments/
└── courses/
```

---

## 2. Pré-requisitos

Antes de testar, confirme se a máquina tem:

- Python 3.12 ou versão compatível.
- Pip instalado.
- Navegador moderno: Chrome, Edge ou Firefox.
- Conta/chave Groq configurada para o chatbot.
- Token de teste do Mercado Pago para o checkout.

---

## 3. Configuração do ambiente

### 3.1. Abrir a pasta do projeto

No PowerShell, vá para a raiz do projeto:

```powershell
cd "C:\Users\Gustavo Steluti\Desktop\Projeto Aplicado TCC"
```

### 3.2. Instalar dependências

Entre na pasta `backend`:

```powershell
cd backend
```

Instale as dependências:

```powershell
pip install -r requirements.txt
```

Se já existir um ambiente virtual `backend/venv`, pode usar:

```powershell
.\venv\Scripts\activate
pip install -r requirements.txt
```

### 3.3. Configurar `.env`

Crie ou edite o arquivo:

```text
backend/.env
```

Ele deve conter pelo menos:

```env
GROQ_API_KEY=sua_chave_groq
GROQ_MODEL=openai/gpt-oss-120b

ADMIN_PASSWORD=sua_senha_admin
ADMIN_TOKEN_SECRET=um_segredo_grande_para_assinar_token

MERCADO_PAGO_ACCESS_TOKEN=seu_token_teste_mercado_pago
FRONTEND_BASE_URL=http://localhost:8000
API_BASE_URL=http://localhost:8000
```

Importante:

- Nunca subir `.env` para o GitHub.
- Usar token de teste do Mercado Pago durante validação.
- `ADMIN_PASSWORD` será usado para entrar no painel admin.

---

## 4. Como rodar o backend

Na pasta `backend`, rode:

```powershell
python app.py
```

Resultado esperado:

- Servidor iniciado em `http://localhost:8000`
- Mensagem indicando carregamento dos cursos.
- Mensagem indicando inicialização do Manager Agent.

Se aparecer erro de chave Groq ou Mercado Pago, conferir o `.env`.

---

## 5. Como abrir o frontend

Abra os arquivos diretamente no navegador:

```text
frontend/landing_global_training.html
frontend/admin.html
```

Ou clique duas vezes nos arquivos.

Observação:

O frontend chama o backend em:

```text
http://localhost:8000
```

Então o backend precisa estar rodando antes dos testes.

---

## 6. Checklist rápido antes dos testes

- [ ] Backend rodando em `localhost:8000`.
- [ ] `.env` configurado.
- [ ] Landing abre no navegador.
- [ ] Admin abre no navegador.
- [ ] Não existe link de Admin na landing pública.
- [ ] A senha admin está disponível para o testador.
- [ ] Internet funcionando para Groq e Mercado Pago.

---

## 7. Plano de testes funcional

Use a coluna "Resultado obtido" para anotar o que aconteceu.

### Teste 1 - Health check do backend

**Objetivo:** verificar se a API está online.

**Passos:**

1. Abrir no navegador:

```text
http://localhost:8000/health
```

**Resultado esperado:**

- Retorno JSON com `"status": "ok"`.
- Deve exibir quantidade de cursos carregados.

**Resultado obtido:**  
Preencher.

---

### Teste 2 - Landing carrega cursos

**Objetivo:** confirmar que a landing busca cursos do backend.

**Passos:**

1. Abrir `frontend/landing_global_training.html`.
2. Ir até a seção de cursos.

**Resultado esperado:**

- Cards de cursos aparecem.
- Não deve aparecer erro no console do navegador.

**Resultado obtido:**  
Preencher.

---

### Teste 3 - Link de admin não aparece na landing

**Objetivo:** validar que o painel admin não está exposto no menu público.

**Passos:**

1. Abrir a landing.
2. Observar o menu superior.

**Resultado esperado:**

- Não existe item "Admin" no menu da landing.

**Resultado obtido:**  
Preencher.

---

### Teste 4 - Login admin com senha errada

**Objetivo:** validar proteção contra acesso indevido.

**Passos:**

1. Abrir `frontend/admin.html`.
2. Digitar senha incorreta.
3. Clicar em entrar.

**Resultado esperado:**

- Sistema nega login.
- Mensagem de erro é exibida.
- Lista de cursos e formulário não ficam acessíveis.

**Resultado obtido:**  
Preencher.

---

### Teste 5 - Login admin com senha correta

**Objetivo:** validar acesso administrativo.

**Passos:**

1. Abrir `frontend/admin.html`.
2. Digitar a senha configurada em `ADMIN_PASSWORD`.
3. Clicar em entrar.

**Resultado esperado:**

- Login bem-sucedido.
- Painel de cadastro aparece.
- Lista de cursos cadastrados aparece.
- Botão "Sair" aparece.

**Resultado obtido:**  
Preencher.

---

### Teste 6 - Criar novo curso pelo admin

**Objetivo:** validar criação dinâmica de curso.

**Passos:**

1. Fazer login no admin.
2. Preencher o formulário com um curso de teste.
3. Usar ID simples, por exemplo:

```text
curso_teste_banca
```

4. Clicar em "Criar curso".

**Resultado esperado:**

- Mensagem de sucesso.
- Curso aparece na lista lateral.
- Arquivo JSON é criado em `backend/courses`.

**Resultado obtido:**  
Preencher.

---

### Teste 7 - Curso novo aparece na landing

**Objetivo:** validar integração admin → backend → landing.

**Passos:**

1. Após criar o curso, voltar para a landing.
2. Atualizar a página.
3. Procurar o curso criado.

**Resultado esperado:**

- O curso criado aparece como card.

**Resultado obtido:**  
Preencher.

---

### Teste 8 - Chatbot responde sobre curso existente

**Objetivo:** validar IA com dados dos cursos.

**Passos:**

1. Abrir a landing.
2. Abrir o chatbot.
3. Perguntar:

```text
Quero saber mais sobre o curso Excel Profissional.
```

ou sobre o curso criado no teste.

**Resultado esperado:**

- Chatbot responde em português.
- Resposta deve mencionar informações coerentes com o curso.

**Resultado obtido:**  
Preencher.

---

### Teste 9 - Chatbot com pergunta geral

**Objetivo:** validar atendimento geral.

**Passos:**

1. No chatbot, perguntar:

```text
Quais cursos estão disponíveis?
```

**Resultado esperado:**

- Chatbot lista ou comenta os cursos disponíveis.

**Resultado obtido:**  
Preencher.

---

### Teste 10 - Modal de matrícula valida dados

**Objetivo:** validar formulário antes de pagamento.

**Passos:**

1. Na landing, clicar em "Matricular agora".
2. Deixar nome/e-mail vazios ou inválidos.
3. Clicar em "Ir para pagamento".

**Resultado esperado:**

- Mensagem de erro pedindo nome completo e e-mail válido.
- Checkout não abre.

**Resultado obtido:**  
Preencher.

---

### Teste 11 - Criar checkout Mercado Pago

**Objetivo:** validar integração de pagamento.

**Passos:**

1. Na landing, clicar em "Matricular agora".
2. Preencher:
   - nome;
   - e-mail;
   - telefone.
3. Clicar em "Ir para pagamento".

**Resultado esperado:**

- Mensagem "Criando checkout seguro no Mercado Pago..."
- Uma nova aba abre com checkout do Mercado Pago.

**Resultado obtido:**  
Preencher.

Observação:

Se o Mercado Pago não abrir, verificar:

- `MERCADO_PAGO_ACCESS_TOKEN` no `.env`;
- internet;
- backend rodando;
- console do navegador;
- terminal do backend.

---

### Teste 12 - Logout admin

**Objetivo:** validar encerramento de sessão.

**Passos:**

1. No admin, clicar em "Sair".
2. Tentar acessar o painel novamente.

**Resultado esperado:**

- Usuário volta para tela de login.
- Cursos não carregam sem autenticação.

**Resultado obtido:**  
Preencher.

---

### Teste 13 - Rota admin protegida sem token

**Objetivo:** validar proteção no backend, não só no HTML.

**Passos:**

1. Abrir no navegador:

```text
http://localhost:8000/api/admin/courses
```

sem estar autenticado via admin.

**Resultado esperado:**

- Retorno `401` ou mensagem de token ausente.

**Resultado obtido:**  
Preencher.

---

### Teste 14 - Rota pública de cursos

**Objetivo:** validar que a landing consegue listar cursos sem login.

**Passos:**

1. Abrir:

```text
http://localhost:8000/api/courses
```

**Resultado esperado:**

- Retorno JSON com `status: success`.
- Lista de cursos aparece.

**Resultado obtido:**  
Preencher.

---

## 8. Testes visuais e usabilidade

### Landing

- [ ] Menu está visualmente alinhado.
- [ ] Hero está centralizado.
- [ ] Cards de cursos não quebram layout.
- [ ] Botões são visíveis.
- [ ] Chat não cobre conteúdo importante.
- [ ] Layout funciona em tela menor.

### Admin

- [ ] Tela de login é clara.
- [ ] Formulário é compreensível.
- [ ] Mensagens de erro/sucesso aparecem.
- [ ] Lista de cursos é legível.
- [ ] Botão sair funciona.

### Modal de matrícula

- [ ] Campos são claros.
- [ ] Validação aparece quando dados faltam.
- [ ] Botão de pagamento tem feedback.
- [ ] Checkout abre em nova aba.

---

## 9. Problemas conhecidos / limitações

- Webhook do Mercado Pago precisa de URL pública para funcionar de ponta a ponta fora do localhost.
- O SQLite está preparado, mas o MVP ainda não persiste matrícula aprovada automaticamente.
- Ainda não existe área do aluno.
- Ainda não existe edição/deleção de cursos pelo painel visual, apesar das rotas existirem.
- O chatbot depende da disponibilidade da API Groq.

---

## 10. Como reportar bugs

Para cada problema, anotar:

```text
Título do bug:
Data/hora:
Tela:
Passos para reproduzir:
Resultado esperado:
Resultado obtido:
Print ou erro do console:
Observações:
```

Exemplo:

```text
Título do bug: Checkout não abre
Tela: Landing > Modal de matrícula
Passos: cliquei em Matricular, preenchi os dados, cliquei em pagamento
Resultado esperado: abrir Mercado Pago em nova aba
Resultado obtido: apareceu mensagem de erro
Print/erro: colar aqui
```

---

## 11. Checklist final de aceite

O projeto pode ser considerado validado se:

- [ ] Backend inicia sem erro.
- [ ] Landing carrega cursos.
- [ ] Chatbot responde.
- [ ] Admin exige login.
- [ ] Senha errada é recusada.
- [ ] Senha correta entra.
- [ ] Curso pode ser criado.
- [ ] Curso criado aparece na landing.
- [ ] Checkout Mercado Pago abre.
- [ ] Rotas admin são protegidas sem token.
- [ ] `.env` não está versionado.

