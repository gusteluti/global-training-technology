---
marp: true
title: Global Training Technology
description: Apresentacao de TCC - Global Training Technology
paginate: true
size: 16:9
theme: default
style: |
  :root {
    --graphite: #1f262d;
    --graphite-2: #2c343d;
    --ink: #111827;
    --muted: #5b6675;
    --cyan: #0798c9;
    --cyan-2: #11b5d9;
    --cyan-soft: #e8f8fc;
    --orange: #ff7a18;
    --green: #16a34a;
    --line: #d7e0ea;
    --bg: #f7fafc;
    --white: #ffffff;
  }

  section {
    font-family: "Inter", "Segoe UI", Arial, sans-serif;
    background: var(--bg);
    color: var(--ink);
    padding: 46px 64px;
  }

  h1, h2, h3, p {
    margin: 0;
    letter-spacing: 0;
  }

  h1 {
    font-size: 58px;
    line-height: 1.02;
    color: var(--ink);
  }

  h2 {
    font-size: 38px;
    line-height: 1.08;
    margin-bottom: 22px;
    color: var(--ink);
  }

  h3 {
    font-size: 21px;
    line-height: 1.16;
    color: var(--ink);
    margin-bottom: 10px;
  }

  p, li {
    font-size: 21px;
    line-height: 1.32;
  }

  ul {
    margin: 0;
    padding-left: 24px;
  }

  code {
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 17px;
  }

  pre {
    border-radius: 8px;
    padding: 18px;
    background: #101820;
    border: 1px solid #26313d;
  }

  pre code {
    color: #e5f6ff;
  }

  strong {
    color: var(--cyan);
  }

  .cover {
    background: radial-gradient(circle at 78% 18%, rgba(7, 152, 201, 0.22), transparent 28%), var(--graphite);
    color: #fff;
  }

  .cover h1 {
    color: #fff;
    font-size: 68px;
    max-width: 820px;
  }

  .cover .subtitle {
    color: #dceaf2;
    font-size: 28px;
    max-width: 860px;
    margin-top: 22px;
  }

  .brand {
    display: inline-flex;
    gap: 14px;
    align-items: center;
    margin-bottom: 74px;
  }

  .logo-mark {
    width: 62px;
    height: 62px;
    border-radius: 50%;
    background: linear-gradient(135deg, var(--cyan), #14b8d6);
    display: grid;
    place-items: center;
    color: #fff;
    font-weight: 900;
    font-size: 28px;
  }

  .brand-text {
    font-weight: 900;
    line-height: 1.02;
    font-size: 20px;
  }

  .brand-text span {
    display: block;
    color: var(--orange);
  }

  .meta {
    position: absolute;
    left: 64px;
    bottom: 44px;
    color: #c7d2dc;
    font-size: 18px;
    line-height: 1.45;
  }

  .kicker {
    color: var(--cyan);
    font-size: 16px;
    font-weight: 900;
    text-transform: uppercase;
    letter-spacing: 4px;
    margin-bottom: 12px;
  }

  .grid-2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 22px;
    align-items: stretch;
  }

  .grid-3 {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 18px;
  }

  .grid-4 {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
  }

  .card {
    background: var(--white);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 22px;
    box-shadow: 0 12px 28px rgba(17, 24, 39, 0.05);
  }

  .dark-card {
    background: var(--graphite);
    border: 1px solid #3f4b57;
    color: #fff;
    border-radius: 8px;
    padding: 22px;
  }

  .dark-card h3 {
    color: #fff;
  }

  .dark-card p, .dark-card li {
    color: #d7e0ea;
  }

  .small li, .small p {
    font-size: 18px;
  }

  .xs li, .xs p {
    font-size: 16px;
  }

  .number {
    color: var(--cyan);
    font-size: 40px;
    font-weight: 900;
    margin-bottom: 8px;
  }

  .flow {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-top: 20px;
  }

  .step {
    flex: 1;
    min-height: 82px;
    background: #fff;
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 14px;
    display: grid;
    place-items: center;
    text-align: center;
    font-size: 19px;
    font-weight: 800;
  }

  .arrow {
    color: var(--cyan);
    font-size: 34px;
    font-weight: 900;
  }

  .actor {
    background: var(--graphite);
    color: #fff;
    border-radius: 8px;
    padding: 16px;
    font-size: 21px;
    font-weight: 900;
    text-align: center;
  }

  .usecase {
    border: 1px solid var(--line);
    background: #fff;
    border-radius: 999px;
    padding: 11px 14px;
    text-align: center;
    font-size: 16px;
    font-weight: 750;
  }

  .system-box {
    border: 2px solid var(--cyan);
    border-radius: 8px;
    padding: 22px;
    background: linear-gradient(180deg, #ffffff, #f1fbfe);
  }

  .schema {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
    margin-top: 18px;
  }

  .table-card {
    background: #fff;
    border: 1px solid var(--line);
    border-radius: 8px;
    overflow: hidden;
  }

  .table-card h3 {
    background: var(--graphite);
    color: #fff;
    padding: 12px 16px;
    margin: 0;
    font-size: 20px;
  }

  .table-card p {
    font-size: 16px;
    padding: 14px 16px;
    margin: 0;
    color: var(--muted);
  }

  .timeline {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 14px;
    margin-top: 22px;
  }

  .sprint {
    background: #fff;
    border-top: 6px solid var(--cyan);
    border-radius: 8px;
    padding: 16px;
    min-height: 190px;
    border-left: 1px solid var(--line);
    border-right: 1px solid var(--line);
    border-bottom: 1px solid var(--line);
  }

  .sprint h3 {
    color: var(--ink);
    font-size: 19px;
  }

  .sprint p {
    color: var(--muted);
    font-size: 16px;
  }

  .pill {
    display: inline-block;
    padding: 8px 12px;
    border-radius: 999px;
    background: var(--cyan-soft);
    color: var(--cyan);
    font-weight: 900;
    font-size: 15px;
    margin: 3px 4px 3px 0;
  }

  .quote {
    font-size: 28px;
    line-height: 1.25;
    font-weight: 850;
    color: var(--graphite);
    border-left: 8px solid var(--cyan);
    padding-left: 22px;
    margin-top: 26px;
  }

  .screen {
    border: 1px solid var(--line);
    border-radius: 8px;
    background: #fff;
    min-height: 250px;
    overflow: hidden;
  }

  .screen-bar {
    height: 42px;
    background: var(--graphite);
    color: #fff;
    display: flex;
    align-items: center;
    padding: 0 16px;
    font-size: 15px;
    font-weight: 800;
  }

  .screen-body {
    padding: 20px;
  }

  .course-card {
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 16px;
    display: flex;
    align-items: center;
    gap: 14px;
    margin-bottom: 12px;
  }

  .course-icon {
    width: 54px;
    height: 54px;
    border-radius: 8px;
    background: var(--cyan-soft);
    color: var(--cyan);
    display: grid;
    place-items: center;
    font-weight: 900;
    font-size: 22px;
  }
---

<!-- _class: cover -->

<div class="brand">
  <div class="logo-mark">G</div>
  <div class="brand-text"><span>Global Training</span>Technology</div>
</div>

# Global Training Technology

<div class="subtitle">Plataforma de cursos com atendimento inteligente, gestão administrativa e integração de pagamentos</div>

<div class="meta">
Integrantes: preencher nomes da equipe<br>
Orientador(a): preencher nome<br>
Curso / Instituição: preencher<br>
Tema: solução web para jornada de matrícula em cursos profissionalizantes
</div>

---

<div class="kicker">Objetivo, Motivação e Mercado</div>

## Por Que Esta Proposta?

<div class="grid-2">
  <div class="card">
    <h3>Objetivo da proposta</h3>
    <p>Desenvolver uma plataforma web que centraliza cursos, atendimento com IA, administração interna e início de matrícula com pagamento online seguro.</p>
  </div>
  <div class="card">
    <h3>Motivação</h3>
    <ul>
      <li>Dúvidas comerciais repetitivas.</li>
      <li>Catálogo de cursos difícil de atualizar.</li>
      <li>Perda de conversão por demora no atendimento.</li>
      <li>Necessidade de pagamento digital confiável.</li>
    </ul>
  </div>
</div>

<div class="flow">
  <div class="step">Aluno busca curso</div>
  <div class="arrow">→</div>
  <div class="step">IA responde dúvidas</div>
  <div class="arrow">→</div>
  <div class="step">Admin mantém catálogo</div>
  <div class="arrow">→</div>
  <div class="step">Checkout seguro</div>
</div>

---

<div class="kicker">Visão Funcional</div>

## Diagrama de Caso de Uso Geral

<div class="grid-2">
  <div>
    <div class="actor">Aluno</div>
    <div class="system-box" style="margin-top: 14px;">
      <div class="grid-2">
        <div class="usecase">Visualizar cursos</div>
        <div class="usecase">Tirar dúvidas</div>
        <div class="usecase">Preencher matrícula</div>
        <div class="usecase">Realizar pagamento</div>
      </div>
    </div>
  </div>
  <div>
    <div class="actor">Administrador</div>
    <div class="system-box" style="margin-top: 14px;">
      <div class="grid-2">
        <div class="usecase">Fazer login</div>
        <div class="usecase">Cadastrar curso</div>
        <div class="usecase">Listar cursos</div>
        <div class="usecase">Atualizar base da IA</div>
      </div>
    </div>
  </div>
</div>

<div class="grid-2" style="margin-top: 20px;">
  <div class="dark-card small"><h3>Assistente de IA</h3><p>Interpreta intenção do usuário e responde com base no catálogo cadastrado.</p></div>
  <div class="dark-card small"><h3>Mercado Pago</h3><p>Processa o pagamento em ambiente externo, sem expor cartão ao sistema.</p></div>
</div>

---

<div class="kicker">Banco de Dados</div>

## Modelo Físico Criado Até o Momento

<div class="schema">
  <div class="table-card">
    <h3>students</h3>
    <p>id INTEGER PK<br>email TEXT UNIQUE<br>name TEXT<br>created_at TIMESTAMP</p>
  </div>
  <div class="table-card">
    <h3>enrollments</h3>
    <p>id INTEGER PK<br>student_id INTEGER FK<br>course_id TEXT<br>status TEXT<br>enrolled_at TIMESTAMP</p>
  </div>
  <div class="table-card">
    <h3>payments</h3>
    <p>id INTEGER PK<br>enrollment_id INTEGER FK<br>amount REAL<br>status TEXT<br>payment_method TEXT<br>transaction_id TEXT<br>created_at TIMESTAMP<br>updated_at TIMESTAMP</p>
  </div>
</div>

<div class="flow">
  <div class="step">students</div>
  <div class="arrow">1:N</div>
  <div class="step">enrollments</div>
  <div class="arrow">1:N</div>
  <div class="step">payments</div>
</div>

---

<div class="kicker">Banco de Dados</div>

## Exemplo Técnico da Estrutura

<div class="grid-2">
  <div>

```sql
CREATE TABLE students (
  id INTEGER PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE enrollments (
  id INTEGER PRIMARY KEY,
  student_id INTEGER NOT NULL,
  course_id TEXT NOT NULL,
  status TEXT DEFAULT 'pending',
  enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (student_id) REFERENCES students(id)
);
```

  </div>
  <div class="card small">
    <h3>Decisão técnica atual</h3>
    <ul>
      <li>SQLite preparado para persistência de alunos, matrículas e pagamentos.</li>
      <li>Cursos ficam em JSON para cadastro dinâmico e leitura direta pelos agentes de IA.</li>
      <li>Próxima etapa: conectar checkout aprovado ao registro de matrícula.</li>
    </ul>
  </div>
</div>

---

<div class="kicker">Arquitetura</div>

## Modelo Arquitetural e Tecnologias

<div class="grid-3 small">
  <div class="card">
    <h3>Frontend</h3>
    <p>HTML5<br>CSS3<br>JavaScript<br>Landing page<br>Painel admin<br>Chat e modal</p>
  </div>
  <div class="card">
    <h3>Backend</h3>
    <p>Python<br>FastAPI<br>Pydantic<br>Requests<br>Rotas Admin, Chat e Payments</p>
  </div>
  <div class="card">
    <h3>Serviços e Dados</h3>
    <p>Groq API<br>Mercado Pago Checkout Pro<br>JSON de cursos<br>SQLite<br>.env</p>
  </div>
</div>

<div class="flow">
  <div class="step">Landing/Admin</div>
  <div class="arrow">→</div>
  <div class="step">FastAPI</div>
  <div class="arrow">→</div>
  <div class="step">Agents + JSON/SQLite</div>
  <div class="arrow">→</div>
  <div class="step">Groq + Mercado Pago</div>
</div>

---

<div class="kicker">Arquitetura</div>

## Fluxo Técnico Principal

<div class="grid-2">
  <div class="screen">
    <div class="screen-bar">Fluxo público do aluno</div>
    <div class="screen-body">
      <div class="course-card"><div class="course-icon">1</div><p>Aluno acessa landing e visualiza cursos.</p></div>
      <div class="course-card"><div class="course-icon">2</div><p>Chatbot consulta backend e agentes de IA.</p></div>
      <div class="course-card"><div class="course-icon">3</div><p>Modal coleta dados de matrícula.</p></div>
      <div class="course-card"><div class="course-icon">4</div><p>Backend cria checkout no Mercado Pago.</p></div>
    </div>
  </div>
  <div class="screen">
    <div class="screen-bar">Fluxo administrativo</div>
    <div class="screen-body">
      <div class="course-card"><div class="course-icon">1</div><p>Admin faz login e recebe token temporário.</p></div>
      <div class="course-card"><div class="course-icon">2</div><p>Cadastro envia curso para rota protegida.</p></div>
      <div class="course-card"><div class="course-icon">3</div><p>Curso é salvo em JSON.</p></div>
      <div class="course-card"><div class="course-icon">4</div><p>Landing e IA passam a reconhecer o curso.</p></div>
    </div>
  </div>
</div>

---

<div class="kicker">Metodologia</div>

## Gestão do Projeto no Semestre

<div class="timeline">
  <div class="sprint"><h3>Sprint 1</h3><p>Levantamento de requisitos, definição do problema e arquitetura inicial.</p></div>
  <div class="sprint"><h3>Sprint 2</h3><p>Backend FastAPI, rotas iniciais, estrutura de cursos e agentes.</p></div>
  <div class="sprint"><h3>Sprint 3</h3><p>Landing page, cards de cursos, modal de matrícula e chat.</p></div>
  <div class="sprint"><h3>Sprint 4</h3><p>Painel administrativo, autenticação e cadastro dinâmico.</p></div>
  <div class="sprint"><h3>Sprint 5</h3><p>Pagamento, segurança, testes, documentação e apresentação.</p></div>
</div>

<p style="margin-top: 18px;"><strong>Total:</strong> 5 Sprints no semestre, com entregas incrementais e validação funcional a cada etapa.</p>

---

<div class="kicker">Metodologia</div>

## Exemplo de Sprint: Admin e IA

<div class="grid-2">
  <div class="card">
    <h3>Objetivo da Sprint</h3>
    <p>Permitir que a equipe administrativa cadastre cursos sem alterar o código e que o novo curso seja reconhecido pela landing e pelo chatbot.</p>
  </div>
  <div class="card">
    <h3>Atividades executadas</h3>
    <ul>
      <li>Criar tela de login administrativo.</li>
      <li>Proteger rotas com Bearer Token.</li>
      <li>Salvar curso em JSON.</li>
      <li>Recarregar base do ManagerAgent.</li>
      <li>Validar curso novo na landing e no chat.</li>
    </ul>
  </div>
</div>

<div class="flow">
  <div class="step">Login Admin</div>
  <div class="arrow">→</div>
  <div class="step">Cadastrar Curso</div>
  <div class="arrow">→</div>
  <div class="step">JSON Atualizado</div>
  <div class="arrow">→</div>
  <div class="step">IA Reconhece</div>
</div>

---

<div class="kicker">Demonstração</div>

## Partes Desenvolvidas da Aplicação

<div class="grid-4 small">
  <div class="card">
    <div class="number">01</div>
    <h3>Landing Page</h3>
    <p>Apresenta a escola, cursos e chamada para matrícula.</p>
  </div>
  <div class="card">
    <div class="number">02</div>
    <h3>Chatbot</h3>
    <p>Atendimento inteligente integrado ao backend.</p>
  </div>
  <div class="card">
    <div class="number">03</div>
    <h3>Admin</h3>
    <p>Área protegida para cadastro e listagem de cursos.</p>
  </div>
  <div class="card">
    <div class="number">04</div>
    <h3>Checkout</h3>
    <p>Integração com Mercado Pago Checkout Pro.</p>
  </div>
</div>

<div class="quote">O mesmo curso cadastrado no admin alimenta a vitrine pública e a base de respostas da IA.</div>

---

<div class="kicker">Interfaces</div>

## Usabilidade e Layout

<div class="grid-2">
  <div class="card">
    <h3>Landing page</h3>
    <ul>
      <li>Visual alinhado com a identidade Global Training.</li>
      <li>Cards de cursos claros e escaneáveis.</li>
      <li>Botões diretos para cursos, IA e matrícula.</li>
      <li>Chat acessível na jornada do aluno.</li>
    </ul>
  </div>
  <div class="card">
    <h3>Painel administrativo</h3>
    <ul>
      <li>Login antes de acessar funções sensíveis.</li>
      <li>Formulário estruturado para cadastro de curso.</li>
      <li>Feedback visual de sucesso e erro.</li>
      <li>Layout simples para uso interno.</li>
    </ul>
  </div>
</div>

---

<div class="kicker">IA</div>

## Atendimento Inteligente

<div class="grid-2">
  <div class="card">
    <h3>Como funciona</h3>
    <ul>
      <li>Usuário envia pergunta pelo chat.</li>
      <li>Backend recebe a mensagem.</li>
      <li>ManagerAgent identifica a intenção.</li>
      <li>CourseAgent consulta os cursos cadastrados.</li>
      <li>Groq API apoia a geração da resposta.</li>
    </ul>
  </div>
  <div>

```text
Aluno:
"Tem curso de Python?"

IA:
"Sim. Temos Python Basico.
Modalidade: Presencial.
Voce pode iniciar a matricula pela pagina."
```

  </div>
</div>

<div class="kicker">Pagamento</div>

## Integração com Mercado Pago

<div class="grid-2">
  <div class="card">
    <h3>Decisão de segurança</h3>
    <ul>
      <li>Cartão não passa pelo sistema.</li>
      <li>Token Mercado Pago fica no backend.</li>
      <li>Checkout é hospedado pelo Mercado Pago.</li>
      <li>Webhook preparado para confirmar status.</li>
    </ul>
  </div>
  <div class="card">
    <h3>Fluxo de pagamento</h3>
    <ul>
      <li>Aluno escolhe curso e forma de pagamento.</li>
      <li>Backend cria preferência de pagamento.</li>
      <li>Checkout abre em nova aba.</li>
      <li>Mercado Pago retorna status da transação.</li>
    </ul>
  </div>
</div>

<div class="flow">
  <div class="step">Modal matrícula</div>
  <div class="arrow">→</div>
  <div class="step">API Payments</div>
  <div class="arrow">→</div>
  <div class="step">Checkout Pro</div>
  <div class="arrow">→</div>
  <div class="step">Webhook</div>
</div>

---

<div class="kicker">Segurança</div>

## Proteções Implementadas

<div class="grid-3 small">
  <div class="dark-card">
    <h3>Credenciais</h3>
    <ul>
      <li>.env fora do Git.</li>
      <li>.env.example para documentação.</li>
      <li>Tokens apenas no backend.</li>
    </ul>
  </div>
  <div class="dark-card">
    <h3>Admin</h3>
    <ul>
      <li>Login administrativo.</li>
      <li>Token HMAC temporário.</li>
      <li>Rotas protegidas por Bearer Token.</li>
    </ul>
  </div>
  <div class="dark-card">
    <h3>Pagamento</h3>
    <ul>
      <li>Checkout externo.</li>
      <li>Cartão não trafega no sistema.</li>
      <li>Webhook para validar pagamento.</li>
    </ul>
  </div>
</div>

<p style="margin-top: 22px;"><strong>Objetivo:</strong> reduzir exposição de dados sensíveis e separar funções públicas de funções administrativas.</p>

---

<div class="kicker">Qualidade</div>

## Plano de Testes e Validação

<div class="grid-3 small">
  <div class="card">
    <h3>Frontend</h3>
    <ul>
      <li>Carregamento da landing.</li>
      <li>Cards de cursos.</li>
      <li>Modal de matrícula.</li>
      <li>Chatbot visível e funcional.</li>
    </ul>
  </div>
  <div class="card">
    <h3>Backend</h3>
    <ul>
      <li>GET /api/courses.</li>
      <li>POST /api/chat.</li>
      <li>POST /api/admin/login.</li>
      <li>Rotas admin protegidas.</li>
    </ul>
  </div>
  <div class="card">
    <h3>Pagamento</h3>
    <ul>
      <li>Curso existente.</li>
      <li>Dados obrigatórios.</li>
      <li>Criação de checkout.</li>
      <li>Retorno de erro tratado.</li>
    </ul>
  </div>
</div>

---

<div class="kicker">Critérios da Banca</div>

## Como o Projeto Atende os Itens Avaliados

<div class="grid-2 small">
  <div class="card">
    <h3>Produto e inovação</h3>
    <ul>
      <li>Atende mercado de cursos profissionalizantes.</li>
      <li>Combina IA, gestão interna e pagamento online.</li>
      <li>Escopo com funcionalidades integradas.</li>
    </ul>
  </div>
  <div class="card">
    <h3>Execução técnica</h3>
    <ul>
      <li>Frontend, backend, IA, dados e pagamentos.</li>
      <li>Tecnologias atuais e arquitetura modular.</li>
      <li>Metodologia incremental com Sprints.</li>
    </ul>
  </div>
  <div class="card">
    <h3>Interfaces</h3>
    <ul>
      <li>Layout amigável e responsivo.</li>
      <li>Fluxos simples para aluno e admin.</li>
      <li>Feedback visual em ações importantes.</li>
    </ul>
  </div>
  <div class="card">
    <h3>Documentação</h3>
    <ul>
      <li>README e plano de testes.</li>
      <li>Documento de apresentação.</li>
      <li>Arquivos de ambiente exemplificados.</li>
    </ul>
  </div>
</div>

---

<div class="kicker">Próximos Passos</div>

## Evolução da Solução

<div class="grid-2 small">
  <div class="card">
    <h3>Próxima etapa técnica</h3>
    <ul>
      <li>Persistir matrículas e pagamentos no SQLite.</li>
      <li>Finalizar webhook para liberar matrícula aprovada.</li>
      <li>Criar área do aluno.</li>
      <li>Editar e excluir cursos pelo painel.</li>
    </ul>
  </div>
  <div class="card">
    <h3>Evolução de produto</h3>
    <ul>
      <li>Dashboard administrativo.</li>
      <li>Deploy com domínio e URL pública.</li>
      <li>Certificados digitais.</li>
      <li>Analytics de dúvidas, matrículas e conversões.</li>
    </ul>
  </div>
</div>

<div class="flow">
  <div class="step">Versão atual</div>
  <div class="arrow">→</div>
  <div class="step">Banco + Webhook</div>
  <div class="arrow">→</div>
  <div class="step">Área do aluno</div>
  <div class="arrow">→</div>
  <div class="step">Dashboard</div>
</div>

---

<div class="kicker">Encerramento</div>

## Conclusão

<div class="quote">A solução demonstra como atendimento inteligente, automação administrativa e checkout seguro podem melhorar a jornada de matrícula em escolas de cursos profissionalizantes.</div>

<div class="grid-3 small" style="margin-top: 34px;">
  <div class="card"><h3>Clareza</h3><p>Fluxo completo do aluno e do administrador.</p></div>
  <div class="card"><h3>Tecnologia</h3><p>FastAPI, IA com Groq, SQLite, JSON e Mercado Pago.</p></div>
  <div class="card"><h3>Evolução</h3><p>Base preparada para matrícula persistida, área do aluno e dashboards.</p></div>
</div>
