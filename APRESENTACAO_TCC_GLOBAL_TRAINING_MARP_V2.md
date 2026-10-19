---
marp: true
title: Global Training Technology — Apresentação (Resumo)
description: Versão de apresentação menos técnica, adequada para banca e público geral
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

# Global Training Technology

## Tema: solução web para jornada de matrícula em cursos profissionalizantes

**Integrantes:**
- Gustavo Santos Steluti
- João Pedro Costa Malta
- Victor Hugo

**Instituição:** PUC-Campinas

---

<div class="kicker">Objetivo e Motivação</div>

## Objetivo da proposta

- Desenvolver uma plataforma que centraliza divulgação de cursos, atendimento automático e início da matrícula com pagamento seguro.

## Motivação / Visão de mercado

- Reduzir tempo de resposta para dúvidas repetitivas.
- Facilitar atualização do catálogo de cursos.
- Aumentar conversão ao acelerar atendimento e pagamento.

---

<div class="kicker">Diagrama de Caso de Uso</div>

## Principais atores e ações

- Aluno: visualizar cursos, tirar dúvidas, preencher matrícula, pagar;
- Administrador: cadastrar/atualizar cursos, gerenciar catálogo;
- IA (chatbot): responder dúvidas e orientar matrícula;
- Mercado Pago: processar pagamento com checkout hospedado.

(Fluxo resumido: Aluno → Landing → Chatbot/API → Checkout → Mercado Pago)

---

<div class="kicker">Modelo Físico do Banco de Dados</div>

## Estrutura gerada (simplificada)

- **students**: id, email (único), name, created_at
- **enrollments**: id, student_id (FK), course_id, status, enrolled_at
- **payments**: id, enrollment_id (FK), amount, status, transaction_id, created_at

(Essa estrutura permite rastrear alunos, matrículas e pagamentos de forma simples.)

---

<div class="kicker">Modelo Arquitetural</div>

## Tecnologias e responsabilidades (visão geral)

- Frontend: HTML, CSS, JavaScript — interface da landing e painel admin;
- Backend: Python + FastAPI — APIs públicas e administrativas;
- IA: Agentes em Python integrados à Groq — resposta automática às dúvidas;
- Dados: Cursos em JSON para cadastro rápido; SQLite para dados transacionais;
- Pagamentos: Mercado Pago Checkout (checkout hospedado, sem cartão no sistema).

---

<div class="kicker">Metodologia</div>

## Gestão do projeto e Sprint exemplificativo

- Metodologia incremental em Sprints (5 sprints no semestre);
- Exemplo de Sprint: Login Admin → Cadastro de curso → Recarregar IA → Testes na landing;
- Divisão da equipe (exemplo):
  - Gustavo: Backend e integração com IA;
  - João Pedro: Frontend e experiência do usuário;
  - Victor: Admin, testes e pagamentos;

(Entrega incremental com validação funcional a cada Sprint.)

---

<div class="kicker">Partes desenvolvidas da aplicação</div>

## O que foi implementado

- Landing page com catálogo dinâmico de cursos;
- Chatbot conectado ao backend para tirar dúvidas;
- Painel administrativo com login e criação de cursos (JSON);
- Integração com Mercado Pago para checkout;
- Estrutura inicial de banco (SQLite) para matrícula e pagamentos.

---

<div class="kicker">Next Steps</div>

## Próximos passos prioritários (resumido)

- Persistir matrícula e pagamento automaticamente após confirmação;
- Finalizar webhook para atualizar status de pagamento e liberar matrícula;
- Criar área do aluno para acesso a certificado/curso;
- Adicionar dashboard administrativo para edição/exclusão de cursos;
- Preparar deploy com HTTPS, domínio e configurações de produção.

---

<div class="kicker">Encerramento</div>

## Mensagem final

A solução integra atendimento inteligente, administração simples e pagamento seguro para melhorar a jornada de matrícula em cursos profissionalizantes.
