# Registro de decisões do orquestrador — TDD Fase 2

## E1 — Identidade unificada

D0 (processo, erro do orquestrador): o agente-testes foi lançado duas vezes em paralelo na mesma
árvore de trabalho. A primeira execução (background) não tinha sido verificada como encerrada antes
da segunda. Resultado: os arquivos de teste foram sobrescritos entre as duas execuções. Correção:
um agente de testes por vez; antes de lançar outro, confirmar que o anterior encerrou.

D1 (versão autoritativa): o estado autoritativo dos testes é o commit 114d44e (diff do disco contra
o commit = vazio). Red observado: 21 falhas, 1 passa (7b).

D2 (teste 7b): passa no red porque é guarda de preservação (aluno já recebe 403 hoje). Mantido como
guarda de regressão. Não conta como red de implementação.

D3 (teste 4, ordem dos asserts): 5 dos 6 casos falham por KeyError 'user_id' antes de verificar o
status. Defeito do teste. Corrigir: verificar o status primeiro, depois user_id. Responsável: agente-testes.

D4 (e2e, 27 vs 29 checks): os dois checks de reembolso pela tela são pulados com banco vazio.
Decisão: a suíte de navegador precisa rodar os 29 checks; o harness semeia um pagamento pendente
antes de rodar. Responsável: agente-testes. Sem alterar código de produção para isso.

D5 (requirements-dev.txt com playwright): aceito. Playwright é ferramenta de teste de navegador.

D6 (alteração pendente em frontend/e2e/test_admin_angular.py): entra em commit de follow-up dos
testes, feito pelo agente-testes, junto com D3 e D4.

D7 (seed do e2e no banco de dev): o seed do e2e grava pagamentos de teste no backend/db.sqlite de dev
(gitignored), e o acúmulo se repete a cada execução. Aceito por ora; registrado como dívida do harness.
Correção futura: subir o backend com DB_PATH isolado. NÃO bloqueia a E1.

D8 (check de reembolso no e2e): o check passou de "refunded >= 2" para comparação antes/depois.
A versão anterior dependia da ordem de execução do admin e do financeiro. A mudança torna o check
correto e está no commit f6f1169. Aceita.

D9 (teste 4 após D3): os casos refunded, cancelled e pending falham por KeyError 'user_id' com o status
já correto. Isso é red legítimo (falta user_id na matrícula). Os casos approved, rejected e in_process
falham por diferença de status. Ambos são red de implementação. Aceito.

Estado de entrada para dev-backend: commit f6f1169. 22 testes; 21 falham; 7b passa (D2).
Regressão 44/44. E2E 29/29.

D10 (desvio de processo, fora do escopo do E1): o dev-backend (commit 50a1164) acrescentou sufixo
aleatório em external_reference (course:timestamp:uuid8). Motivo: evitar colisão de duas compras do
mesmo curso no mesmo segundo. Não estava na lista de requisitos e foi implementado sem teste vermelho
prévio. Aceito como correção real, MAS exige teste que a cubra antes do fechamento da E1
(duas compras do mesmo curso no mesmo segundo geram referências distintas). Responsável: agente-testes.

D11 (IDOR nesta entrega): não há endpoint de aluno na E1, então o teste de IDOR fica para a E3,
quando /api/student/* existir. Na E1 a cobertura de autorização é 7a e 7b.

Verificação do orquestrador (commit 50a1164): diff dos testes = 0 linhas; suíte backend = 28 passed;
árvore limpa; arquivos de produção: backend/db.py e backend/payments/routes.py.

## Veredito do PM sobre a E1: APROVADA com condição
- Condição (D10, prova por mutação): CUMPRIDA. Mutação na cópia: 2 de 3 testes falharam pelo motivo certo
  (colisão de external_reference; webhook atingindo matrícula vizinha). Restaurado: 3/3 verdes.
- Merge: 9578a8f em feature/fase2-tdd (--no-ff). Sem push.
- Decisão 7a (400 mantido): registrada como decisão consciente, não pendência. Coerência interna do projeto.
- Regra reforçada: um agente por vez; confirmar encerramento do anterior antes de chamar o próximo.
- Decisões aceitas: remoção de students; seed no banco de dev (D7); IDOR N/A na E1.
- IDOR vira item OBRIGATÓRIO do checklist da E3 (endpoints de aluno).

## E2 — Autenticação e criação de conta do aluno (itens 1.1 e RF21)

Decisões de PM (do charter):
- Conta do aluno nasce após a compra, por link de definição de senha. Cadastro direto também permitido.
- Link de definição: token com expiração e uso único; coberto por teste de segurança.
- Nenhum endpoint novo aceita ID de usuário vindo do cliente.

Decisões do orquestrador (minhas, a registrar como D12–D18):
- D12 — Token de definição de senha: gerado pelo webhook quando um pagamento vira aprovado e a conta
  não tem senha. Guardado APENAS como hash SHA-256 (nunca em texto). Expira em 48 h. Uso único.
- D13 — Entrega do link: não há servidor de e-mail neste projeto. A interface de envio é um ponto único
  (função send_password_setup_link) que, nesta entrega, grava o link em arquivo de saída de DESENVOLVIMENTO
  (fora do repo) e registra no log. Trocar por SMTP real é trabalho futuro e está documentado.
- D14 — Política de senha mínima: 8 caracteres. Sem outras regras nesta entrega.
- D15 — Cadastro direto (POST /api/auth/register): papel SEMPRE 'student' (campo role do cliente é ignorado);
  e-mail já existente → 400 com mensagem genérica (não revela se a conta existe) e NÃO altera a senha
  da conta existente (impede tomada de conta).
- D16 — Definição de senha (POST /api/auth/password-setup): só vale para conta SEM senha. Conta que já tem
  senha → 400 genérico. Token inválido, expirado ou já usado → 400 genérico.
- D17 — Nenhum endpoint aceita user_id do cliente nesta entrega (o alvo é sempre o dono do token).
- D18 — Senha armazenada com bcrypt (passlib), nunca em texto.

Escopo de produção da E2 (dev-backend): endpoints register e password-setup; geração do token no webhook
aprovado (conta sem senha); tabela password_setup_tokens (token_hash, user_id, expires_at, used_at);
send_password_setup_link em modo desenvolvimento; validação de senha mínima.
Escopo de frontend (dev-frontend): tela de cadastro e tela "definir senha" (?token=), com mensagens
genéricas de erro; login existente continua. Sem alterar testes.

## D21 — contrato de cadastro: resposta uniforme 200 (aprovada pelo PM)
Motivo: test_3 e test_13a (e-mail existente → 400) e o e2e C3 codificavam um comportamento que vaza
existência de conta. Isso viola o requisito de segurança do escopo (seção 4: proibido vazar informação
entre usuários). Decisão: resposta uniforme (mesmo status 200, mesmo corpo, sem eco de e-mail) para
e-mail novo e existente. Paridade de tempo: o mesmo trabalho de bcrypt nos dois caminhos.
ESTE CASO NÃO É PRECEDENTE. Quem alterou os testes foi o agente-testes, com aprovação do PM, porque o
comportamento codificado se provou errado diante de um requisito de segurança. O dev-backend NÃO reescreve
teste para fazer passar; se achar teste contraditório, reporta e para.

## D22 — comunicação fora do HTTP (acréscimo do PM)
A resposta uniforme não informa o usuário legítimo. Por isso a informação vai por e-mail (outbox):
- e-mail novo → mensagem com o link de definição de senha (como já ocorre);
- e-mail já cadastrado → mensagem avisando que houve tentativa de cadastro, que a conta já existe, e o
  caminho para entrar ou recuperar a senha.
Usa o mesmo PASSWORD_LINK_OUTBOX (em dev, registra no outbox). Os dois ramos têm teste.

## D23 — link de definição de senha no cadastro direto (aprovada pelo PM)
E-mail NOVO no cadastro direto recebe só a confirmação de conta criada, SEM link de definição de senha
(o cadastro já define a senha, e o password-setup recusa conta com senha, D16). O link de definição fica
exclusivo do fluxo de compra. A diferença de conteúdo do e-mail entre os dois casos é permitida; a resposta
HTTP (status, corpo e tempo) NÃO pode diferir entre e-mail novo e existente (D21).

## D24 — 400 do login sem senha tolerado na C8 (aprovada pelo PM, com limite)
Acrescentado ("POST", "/api/token", "/") à lista de 400 tolerados. Tolerância por PAR rota + tela, nunca por
rota solta nem por status solto. Cada novo 400 legítimo entra na lista explicitamente, um por um.

## Regra operacional (obrigatória, PM)
- Antes de chamar qualquer agente: commit ou stash do que está na árvore (árvore limpa).
- Confirmar que o agente anterior RETORNOU antes de chamar o próximo.
- Um agente por vez no repo, sem exceção.

## D25 — test_13b com senha fraca nos dois casos (aprovada pelo PM)
O test_13b cadastrava e-mail EXISTENTE com senha forte e esperava 400. Pela D21 esse caso passa a 200,
e os dois não cabem juntos. Ajuste: senha fraca nos dois casos (e-mail novo e existente). A validação de
tamanho roda ANTES da consulta à conta, então o 400 aparece igual e não vaza existência.
A intenção original ("e-mail existente é recusado") não foi esquecida: foi DELIBERADAMENTE REVOGADA pela
D21, e hoje está coberta por test_enum_1 e test_enum_2. Não ler como cobertura abandonada.

## D26 — aviso de e-mail existente aponta só para o login (aprovada pelo PM)
Prometer recuperação de senha que não existe é pior que não mencionar. O aviso aponta só para a tela de
login. test_b2 deixa de exigir o link de recuperação (consequência mecânica de D26).

## Backlog (fora das nove entregas)
- Recuperação de senha: não está no escopo, mas login de aluno em produção vai precisar. Item próprio.

## Autoridade permanente (aprovada pelo PM)
O orquestrador NÃO precisa consultar o PM quando a alteração de teste é consequência mecânica de decisão já
aprovada e registrada, desde que: (a) a decisão de origem está aprovada e registrada; (b) a intenção do teste
é preservada, ou sua revogação já foi decidida pelo PM; (c) quem altera é o agente-testes, nunca o dev;
(d) fica registrado aqui com o encadeamento explícito. Decisão NOVA (contrato, comportamento visível,
conflito de requisitos, corte de escopo) continua vindo ao PM.

## D27 — correção da associação do filtro da C8 (derivada de D24, dentro da autoridade permanente)
Achado: a C8 falhou 2/2 com o 400 de POST /api/token na tela "/" (C7, login sem senha), que é o par
tolerado por D24. O harness não associou o erro de console à resposta. O defeito está no harness
(associação console ↔ response), não no produto. Correção: o agente-testes corrige a ASSOCIAÇÃO, sem
alterar a lista de pares tolerados e sem alterar a intenção do filtro. Prova exigida: o par D24 passa,
e um 400 fora da lista continua reprovando a C8. Quem altera: agente-testes. Produção: não muda.

## D28 — escopo da Entrega 3 (painel de inscrições + materiais, RF22)
Rastreabilidade: item 1.1 (painel de inscrições: cursos adquiridos, status da matrícula, link de acesso aos
materiais) e RF22 (aluno acessa cursos matriculados e informações de pagamento logado).
- GET /api/student/enrollments: lista SOMENTE as matrículas do usuário do token (role student). Cada item:
  id, course_id, course_name, status (pending | active | cancelled | refunded), enrolled_at.
- GET /api/student/enrollments/{id}: só a matrícula do dono; de outro aluno → 404 (não 403, para não revelar
  existência). IDOR obrigatório (PM).
- Nenhum endpoint de aluno aceita user_id do cliente (query/body) — é ignorado; o alvo é sempre o dono do token.
- Materiais: campo OPCIONAL materials: [{title, url, type}] no JSON do curso e no CourseInput do admin
  (default []). Visível (campo materials com os itens) SOMENTE quando a matrícula está 'active'. Para pending,
  cancelled e refunded, nenhuma URL de material aparece em nenhum lugar da resposta.
- Perfil de funcionário (admin/financial/support) nos endpoints /api/student/* → 403 (área de aluno é só de aluno).
- Sem token → 401.
- Frontend (Angular, padrão do Gustavo): a tela /student passa a mostrar "Meus cursos" com as matrículas, status
  em badge, e os materiais só quando active. Matrícula não ativa mostra mensagem de status, sem links.

## D29 — higiene do teste da E3 (aprovada pelo PM, mecânica)
test_t11b e os testes da E3 que usam curso_e3_sem_<hash> gravam backend/courses/curso_e3_sem_<hash>.json e não
removem. Correção: limpeza no finally do fixture (remover os cursos de teste criados). Intenção do teste
preservada; nenhuma asserção muda. Quem altera: agente-testes, antes do dev-backend começar. A suíte
também mostrou 26/55 numa execução paralela com outra: uso concorrente, não reproduzido em execução limpa.
Regra: nunca rodar a suíte em paralelo com outra execução do repo.

## D29 — CORRIGIDA (nota fiel)
A limpeza do fixture já existia no HEAD 734469d: T11a e T11b removem o curso gravado em backend/courses no
finally. A nota original dizia que não removia; estava desatualizada. Nenhuma alteração de teste foi feita.

## D30 — push LIBERADO (decisão nova do PM, 05/10/2026)
REVOGA a regra "nunca fazer push" que está escrita neste documento (seção de regras comuns) e no
papeis_tdd.md. A partir de 05/10/2026 o push para o origin está autorizado pelo usuário.

Limites que continuam valendo, parte da mesma decisão:
- origin = https://github.com/gusteluti/global-training-technology.git e é um repositório PÚBLICO.
- NÃO tocar na main: sem push para main, sem merge em main.
- NUNCA force-push, em branch nenhuma.
- Push rejeitado por divergência: PARAR e avisar o PM. Não forçar, não resolver por conta própria.
- Antes de cada push, auditar o que será publicado: nenhum .env, db.sqlite, token de teste,
  credencial ou .chrome-pdf-profile pode subir. Achando qualquer um, PARAR antes do push e reportar.
- A partir desta decisão, cada entrega fecha com commit na sua sub-branch, validação, merge em
  feature/fase2-tdd e push das duas. Mantido o padrão de um commit de teste vermelho e um de
  implementação.

Observação para a próxima sessão: o papeis_tdd.md e a seção 5 do HANDOFF_TDD.md ainda têm a frase
"NUNCA fazer push" no texto original. Ela está revogada por esta decisão; o HANDOFF_TDD.md foi
atualizado para apontar para cá.

## D31 — escopo: as nove entregas (decisão do PM, 05/10/2026)
REVOGA a ordem de parar depois da E3. O objetivo é fechar as nove entregas. O plano completo, com a
rastreabilidade de cada uma, está na seção 10 do HANDOFF_TDD.md, que passa a ser mantida ao fim de
cada entrega, com commit e push.

Ritmo: o PM valida UMA entrega por vez. O orquestrador reporta ao fim de cada entrega, com o
checklist de 9 itens preenchido, e NÃO encadeia as seguintes sem resposta do PM. Decisão nova
(contrato, comportamento visível, conflito de requisitos, corte de escopo) continua vindo ao PM.
Os dois obrigatórios da E3 (IDOR e recurso pago liberado só com matrícula ativa) continuam valendo
nas demais entregas onde fizerem sentido.

## D32 — autovigilância de esgotamento (decisão do PM, 05/10/2026)
A sessão anterior morreu de esgotamento e seguiu mexendo no repo enquanto degradava. Gatilhos de
parada obrigatória, qualquer um deles: agente retornando incompleto duas vezes seguidas; o
orquestrador repetindo a mesma análise em rodadas consecutivas; perda de rastro do que já foi feito.
Ao detectar: parar o ciclo, deixar a árvore limpa e commitada, atualizar o HANDOFF_TDD.md, avisar o
PM que precisa de sessão nova. Parar a tempo é resultado bom; forçar e corromper entrega não é.
