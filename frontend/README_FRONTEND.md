Aplicação Angular (Fase 2): interface oficial da plataforma
==========================================================

Área do aluno e área administrativa (Gestão, Financeiro e Suporte) numa só SPA.

Como rodar
----------

1. Suba o backend em `http://localhost:8000` (veja `backend/README.md`).
2. Dentro de `frontend/`:

```powershell
npm install
npm start
```

`npm start` usa `proxy.conf.json`: as chamadas para `/api` vão para o backend
em `localhost:8000`, então não há problema de CORS nem URL fixa no código.

Para gerar o build de produção: `npm run build` (saída em `dist/frontend`).

Contas de teste
---------------

As contas são criadas no startup do backend a partir do `.env`:

| Perfil | Variável de e-mail | Variável de senha | Acesso |
| --- | --- | --- | --- |
| Gestão | `ADMIN_EMAIL` | `ADMIN_PASSWORD` | tudo |
| Financeiro | `FINANCIAL_EMAIL` | `FINANCIAL_PASSWORD` | financeiro, alunos, cursos, IA |
| Suporte | `SUPPORT_EMAIL` | `SUPPORT_PASSWORD` | alunos, cursos, IA |
| Aluno | (cadastro próprio) | | área do aluno |

Painéis administrativos
-----------------------

A área administrativa (`/admin`) mostra apenas as abas do perfil logado:

- **Financeiro**: cards de receita, gráfico de receita mensal, transações e reembolso.
- **Alunos**: métricas de matrícula e lista de alunos.
- **Cursos**: inscritos por curso (gráfico) e performance do catálogo com conversão.
- **Observabilidade de IA**: sessões, mensagens, tópicos não compreendidos e mensagens por curso.
- **Auditoria**: trilha de eventos críticos (somente Gestão).

Os dados vêm de `/api/dashboard/*`, `/api/admin/audit-logs` e `/api/payments/refund/{id}`.
A API também aplica as regras de perfil; a tela só esconde o que o perfil não pode ver.

Pontos em aberto
----------------

- Cadastro e edição de cursos ainda não estão na aplicação Angular. Continuam no
  `frontend/admin.html`, que é legado.
- O link "Acessar" da área do aluno aponta para `/courses/:id`, que ainda não existe.
- A área do aluno (painel de inscrições e histórico financeiro) ainda não foi implementada.
