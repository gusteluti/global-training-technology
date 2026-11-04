# Relatório de QA (ISTQB)

Gerado por `frontend/e2e/gerar_relatorio_qa.py` a partir do resultado real da suíte `frontend/e2e/test_qa_istqb.py`. Não edite à mão.

## Resumo

- Casos executados: **518** (118 cenários do catálogo)
- Passaram: **518**. Falharam: **0**.
- Requisitos com caso de teste: **19 de 19**
- Endpoints exercitados: **79 de 79**
- Telas exercitadas: **13 de 13**
- Cobertura de linhas do backend: **79%** (só esta suíte; a soma com os testes unitários não foi medida)
- Cobertura de ramos do backend: **não medida**

O frontend não tem medição de cobertura de código: a cobertura dele é de telas e fluxos.

## Casos por técnica

| Técnica | Casos |
|---|---|
| Tabela de decisão | 210 |
| Partição de equivalência | 94 |
| Análise de valor-limite | 72 |
| Suposição de erro | 53 |
| Segurança | 48 |
| Caso de uso | 24 |
| Transição de estado | 16 |
| Concorrência | 1 |

## Matriz de rastreabilidade

| Requisito | Descrição | Casos | Passaram | Cenários |
|---|---|---:|---:|---|
| RF21 | Autenticação restrita, separando alunos e funcionários | 42 | 42 | CT-AUT-01, CT-AUT-02, CT-AUT-03, CT-AUT-04, CT-AUT-05, CT-AUT-17, CT-AUT-18, CT-AUT-06, CT-AUT-07, CT-AUT-08, CT-AUT-09, CT-AUT-10, CT-AUT-11, CT-AUT-12, CT-AUT-13, CT-AUT-14, CT-AUT-15, CT-AUT-16, CT-UI-07, CT-UI-08, CT-UI-09, CT-UI-13 |
| RF22 | Área do aluno: cursos e pagamentos | 57 | 57 | CT-ALU-01, CT-ALU-02, CT-ALU-03, CT-ALU-04, CT-ALU-06, CT-ALU-07, CT-ALU-08, CT-ALU-09, CT-ALU-10, CT-ALU-11, CT-ALU-12, CT-UI-11 |
| RF23 | Área do funcionário: dashboards consolidados | 4 | 4 | CT-UI-04, CT-UI-05, CT-COB-01 |
| RF24 | Observabilidade de IA: eficácia, volume e custos | 2 | 2 | CT-IA-05, CT-UI-17 |
| E1.1-Financeiro | Histórico financeiro e recibos | 5 | 5 | CT-ALU-05 |
| E1.2-Alunos | Dashboard de alunos | 9 | 9 | CT-DAS-02, CT-DAS-03, CT-DAS-05, CT-UI-12 |
| E1.2-Cursos | Dashboard de cursos: inscritos por turma e conversão | 6 | 6 | CT-TUR-05, CT-TUR-06, CT-DAS-04 |
| E1.2-Financeiro | Dashboard financeiro: arrecadado, projeção e transações | 2 | 2 | CT-DAS-01, CT-DAS-06 |
| E2-RBAC | Controle de acesso por perfil | 192 | 192 | CT-RBAC-01, CT-RBAC-02, CT-RBAC-03, CT-RBAC-04, CT-EQU-01, CT-EQU-02, CT-EQU-03, CT-EQU-04, CT-UI-10 |
| E2-Auditoria | Trilha de auditoria | 3 | 3 | CT-CUR-04, CT-DAS-07, CT-DAS-08 |
| E3-SPA | Single Page Application em Angular | 35 | 35 | CT-UI-01, CT-UI-02, CT-UI-03, CT-UI-06 |
| E3-API | API REST desacoplada | 31 | 31 | CT-ALU-13, CT-API-01, CT-API-02, CT-API-03, CT-API-04, CT-API-05 |
| E4-Historico | Chatbot com histórico autenticado | 1 | 1 | CT-IA-04 |
| E4-LLM | Proteção contra manipulação do LLM | 11 | 11 | CT-IA-01, CT-IA-02, CT-IA-03, CT-IA-06, CT-API-06 |
| PAG | Compra, webhook e reembolso (D48, D75) | 20 | 20 | CT-PAG-01, CT-PAG-02, CT-PAG-03, CT-PAG-04, CT-PAG-05, CT-PAG-10, CT-PAG-06, CT-PAG-07, CT-PAG-08, CT-PAG-09 |
| CANC | Cancelamento em 7 dias (D82) | 12 | 12 | CT-CAN-01, CT-CAN-02, CT-CAN-03, CT-CAN-04, CT-CAN-05, CT-CAN-06 |
| CAD | Cadastro, arquivamento e exclusão de cursos (D51, D68) | 29 | 29 | CT-CUR-01, CT-CUR-02, CT-CUR-03, CT-CUR-05, CT-CUR-06, CT-CUR-07, CT-CUR-08, CT-UI-16 |
| TUR | Turmas e matrícula manual (D53, D83) | 14 | 14 | CT-TUR-01, CT-TUR-02, CT-TUR-03, CT-TUR-04 |
| SALA | Sala do curso e certificado (D91, D96) | 43 | 43 | CT-SAL-01, CT-SAL-02, CT-SAL-03, CT-SAL-04, CT-SAL-05, CT-SAL-06, CT-SAL-07, CT-SAL-08, CT-SAL-11, CT-SAL-09, CT-SAL-10, CT-UI-14, CT-UI-15 |

## Defeitos encontrados

| Id | Sev. | Caso | Descrição | Situação |
|---|---|---|---|---|
| DEF-01 | Média | CT-AUT-05 | E-mail com maiúsculas criava segunda conta | Corrigido |
| DEF-02 | Média | CT-AUT-02 | Cadastro aceitava e-mail inválido | Corrigido |
| DEF-03 | Média | CT-CUR-02 | API aceitava preço e duração zero ou negativos | Corrigido |
| DEF-04 | Baixa | CT-ALU-04 | Id gigante na URL gerava erro 500 | Corrigido |
| DEF-05 | Baixa | CT-UI-12 | Tópico longo estourava o painel de IA no celular | Corrigido |
| DEF-06 | Alta | test_video_real | Player era recriado a cada 10 s e o vídeo voltava e parava | Corrigido |
| DEF-07 | Alta | test_video_real | Ao trocar de aula, o tempo do vídeo anterior ia para a aula nova | Corrigido |
| DEF-08 | Média | test_video_real | Quem parava no fim recomeçava nos últimos segundos | Corrigido |
| DEF-09 | Média | test_video_real | Posição não era salva quando o vídeo terminava antes do envio | Corrigido |
| DEF-10 | Média | test_video_real | Player do YouTube não ocupava o espaço e sobrava área em branco | Corrigido |

## Catálogo de cenários

| Id | Requisito | Técnica | Cenário | Casos | Passaram |
|---|---|---|---|---:|---:|
| CT-ALU-01 | RF22 | DT | Materiais só com matrícula ativa, em qualquer status de pagamento | 4 | 4 |
| CT-ALU-02 | RF22 | SEC | IDOR: recurso de outro aluno devolve o mesmo 404 de um inexistente | 5 | 5 |
| CT-ALU-03 | RF22 | SEC | IDOR em escrita: progresso, avaliação, cancelamento e posição na sala | 5 | 5 |
| CT-ALU-04 | RF22 | EG | Identificador inválido nunca gera erro 500 | 14 | 14 |
| CT-ALU-05 | E1.1-Financeiro | DT | Histórico financeiro: PDF do recibo só para aprovado ou reembolsado | 5 | 5 |
| CT-ALU-06 | RF22 | BVA | Perfil: nome de 1 a 120 e telefone de 10 a 15 dígitos | 11 | 11 |
| CT-ALU-07 | RF22 | SEC | Perfil ignora papel, e-mail e id enviados no corpo | 1 | 1 |
| CT-ALU-08 | RF22 | ST | Troca de senha logado: senha atual errada recusa; a nova passa a valer | 1 | 1 |
| CT-ALU-09 | RF22 | UC | LGPD: exportação traz só os dados do próprio aluno | 1 | 1 |
| CT-ALU-10 | RF22 | ST | LGPD: exclusão pede a senha, encerra o token e impede novo login | 1 | 1 |
| CT-ALU-11 | RF22 | BVA | Avaliação: nota de 1 a 5 e comentário de até 500 caracteres | 10 | 10 |
| CT-ALU-12 | RF22 | ST | Avaliação só com matrícula ativa; reenviar atualiza a nota | 1 | 1 |
| CT-ALU-13 | E3-API | EG | Id gigante nas rotas de funcionário devolve 404 ou 422, nunca 500 | 7 | 7 |
| CT-API-01 | E3-API | EG | Corpo malformado devolve 4xx, nunca 500 | 12 | 12 |
| CT-API-02 | E3-API | EG | Método não suportado devolve 405 e rota desconhecida 404 | 3 | 3 |
| CT-API-03 | E3-API | EG | Texto com caracteres especiais é aceito e devolvido íntegro | 4 | 4 |
| CT-API-04 | E3-API | SEC | CORS: origem desconhecida não é autorizada | 1 | 1 |
| CT-API-05 | E3-API | UC | Saúde e rotas públicas respondem sem autenticação e sem dado sensível | 4 | 4 |
| CT-API-06 | E4-LLM | SEC | Rota de depuração do chat e documentação não expõem o prompt dos cursos | 2 | 2 |
| CT-AUT-01 | RF21 | UC | Cadastro válido permite login e devolve JWT de aluno | 1 | 1 |
| CT-AUT-02 | RF21 | EP | Cadastro recusa e-mail fora do formato | 7 | 7 |
| CT-AUT-03 | RF21 | BVA | Senha do cadastro: limites de 8 caracteres e 72 bytes | 5 | 5 |
| CT-AUT-04 | RF21 | BVA | Senha com acento conta em bytes: 72 bytes passa e 73 não | 2 | 2 |
| CT-AUT-05 | RF21 | EG | E-mail duplicado, inclusive com maiúsculas, não cria segunda conta | 3 | 3 |
| CT-AUT-06 | RF21 | SEC | Papel enviado no cadastro é ignorado: a conta nasce aluno | 1 | 1 |
| CT-AUT-07 | RF21 | SEC | Login errado não revela se o e-mail existe | 1 | 1 |
| CT-AUT-08 | RF21 | BVA | Bloqueio de login: a 5ª falha ainda responde erro comum e a 6ª bloqueia | 1 | 1 |
| CT-AUT-09 | RF21 | SEC | Token ausente, malformado, assinado errado ou com alg none recebe 401 | 5 | 5 |
| CT-AUT-10 | RF21 | SEC | Token expirado recebe 401 | 1 | 1 |
| CT-AUT-11 | RF21 | ST | Recuperação de senha: token é de uso único e a senha antiga deixa de valer | 1 | 1 |
| CT-AUT-12 | RF21 | SEC | Pedido de recuperação responde igual para e-mail existente e inexistente | 1 | 1 |
| CT-AUT-13 | RF21 | EP | Definição e redefinição recusam token inválido | 2 | 2 |
| CT-AUT-14 | RF21 | UC | Login legado do funcionário: senha certa entra, errada recebe 401 e vai à auditoria | 1 | 1 |
| CT-AUT-15 | RF21 | SEC | Injeção de SQL no login não autentica nem gera erro 500 | 3 | 3 |
| CT-AUT-16 | RF21 | ST | Conta desativada: o token em uso cai e o login informa a desativação; reativar devolve o acesso | 1 | 1 |
| CT-AUT-17 | RF21 | EP | E-mail não diferencia maiúsculas: login, recuperação e cadastro acham a mesma conta | 1 | 1 |
| CT-AUT-18 | RF21 | ST | Conta antiga gravada com maiúsculas continua entrando | 1 | 1 |
| CT-CAN-01 | CANC | BVA | Prazo do pedido: 6 dias aceita, 8 dias recusa | 3 | 3 |
| CT-CAN-02 | CANC | BVA | Motivo do pedido: até 500 caracteres | 2 | 2 |
| CT-CAN-03 | CANC | DT | Pedido recusado: matrícula não ativa, matrícula grátis ou pedido já aberto | 1 | 1 |
| CT-CAN-04 | CANC | BVA | Motivo da recusa: de 5 a 300 caracteres | 4 | 4 |
| CT-CAN-05 | CANC | ST | Aprovar reembolsa e encerra; decidir de novo recebe 409 | 1 | 1 |
| CT-CAN-06 | CANC | EP | Decidir pedido inexistente devolve 404 | 1 | 1 |
| CT-COB-01 | RF23 | EG | Todo endpoint da API recebeu ao menos uma chamada nesta suíte (fica por último) | 1 | 1 |
| CT-CUR-01 | CAD | EP | Cadastro recusa id fora do padrão, inclusive path traversal | 8 | 8 |
| CT-CUR-02 | CAD | BVA | Preço e duração precisam ser positivos | 6 | 6 |
| CT-CUR-03 | CAD | EG | Id de curso repetido é recusado sem sobrescrever o original | 1 | 1 |
| CT-CUR-04 | E2-Auditoria | UC | Mudança de preço fica na auditoria com responsável, data e antes e depois | 1 | 1 |
| CT-CUR-05 | CAD | ST | Arquivar tira do catálogo e bloqueia venda; desarquivar devolve | 1 | 1 |
| CT-CUR-06 | CAD | DT | Exclusão: curso sem matrícula sai; com matrícula em qualquer status é bloqueado | 5 | 5 |
| CT-CUR-07 | CAD | EP | Rascunho por anexo: JSON aceito; formato errado 415; acima de 5 MB 413 | 3 | 3 |
| CT-CUR-08 | CAD | EG | Curso e detalhe inexistentes devolvem 404 | 4 | 4 |
| CT-DAS-01 | E1.2-Financeiro | UC | Dashboard financeiro soma aprovado novo, ignora pendente e tem projeção | 1 | 1 |
| CT-DAS-02 | E1.2-Alunos | UC | Dashboard de alunos busca por nome e e-mail e não confunde curinga do LIKE | 1 | 1 |
| CT-DAS-03 | E1.2-Alunos | EG | Detalhe de aluno: funcionário e inexistente devolvem 404 | 2 | 2 |
| CT-DAS-04 | E1.2-Cursos | UC | Dashboard de cursos traz inscritos por turma e taxa de conversão coerente | 1 | 1 |
| CT-DAS-05 | E1.2-Alunos | SEC | CSV neutraliza fórmula e traz BOM para o Excel | 4 | 4 |
| CT-DAS-06 | E1.2-Financeiro | UC | CSV financeiro e de alunos do curso respeitam o filtro | 1 | 1 |
| CT-DAS-07 | E2-Auditoria | EP | Auditoria filtra por ação, texto, datas e pagina; offset negativo é 422 | 1 | 1 |
| CT-DAS-08 | E2-Auditoria | SEC | Auditoria não guarda senhas digitadas | 1 | 1 |
| CT-EQU-01 | E2-RBAC | ST | Equipe: convite, troca de perfil derruba o token, desativar e reativar | 1 | 1 |
| CT-EQU-02 | E2-RBAC | DT | Gestão não pode desativar nem rebaixar a própria conta | 1 | 1 |
| CT-EQU-03 | E2-RBAC | EP | Convite recusa perfil inválido, perfil de aluno e e-mail ruim | 4 | 4 |
| CT-EQU-04 | E2-RBAC | EG | Operação de equipe sobre aluno ou id inexistente devolve 404 | 1 | 1 |
| CT-IA-01 | E4-LLM | BVA | Mensagem: vazia recusa, 2000 caracteres aceita, 2001 recusa | 3 | 3 |
| CT-IA-02 | E4-LLM | SEC | Injeção direta recebe o texto fixo e não entra no histórico do aluno | 1 | 1 |
| CT-IA-03 | E4-LLM | SEC | Sessão anônima forjada não acessa conversa de outra pessoa | 4 | 4 |
| CT-IA-04 | E4-Historico | SEC | Histórico é só do dono do token e dado pessoal fica mascarado | 1 | 1 |
| CT-IA-05 | RF24 | UC | Painel de IA traz volume, eficácia, tokens e bloqueios; custo só para Gestão e Financeiro | 1 | 1 |
| CT-IA-06 | E4-LLM | BVA | Limite do chat: 30 por minuto passam e a 31ª recebe 429 | 1 | 1 |
| CT-PAG-01 | PAG | ST | Compra do aluno: pendente sem material, webhook assinado ativa e libera | 1 | 1 |
| CT-PAG-02 | PAG | SEC | Webhook sem assinatura, adulterado ou com outro segredo não altera nada | 3 | 3 |
| CT-PAG-03 | PAG | EP | Compra recusa curso inexistente, id malicioso e turma de outro curso | 4 | 4 |
| CT-PAG-04 | PAG | ST | Compra duplicada do mesmo curso é recusada | 1 | 1 |
| CT-PAG-05 | PAG | UC | Compra pública da landing cria a matrícula pendente do pagador | 1 | 1 |
| CT-PAG-06 | PAG | CONC | Última vaga disputada por 5 compras simultâneas: só uma leva | 1 | 1 |
| CT-PAG-07 | PAG | BVA | Limite de compras: 10 por minuto passam e a 11ª recebe 429 | 1 | 1 |
| CT-PAG-08 | PAG | ST | Reembolso: aprovado vira reembolsado, aluno perde o material e repetir não duplica | 1 | 1 |
| CT-PAG-09 | PAG | DT | Reembolso recusado para pagamento não aprovado ou inexistente | 3 | 3 |
| CT-PAG-10 | PAG | EP | Compra da landing recusa e-mail inválido sem criar conta | 4 | 4 |
| CT-RBAC-01 | E2-RBAC | DT | Tabela de decisão endpoint × perfil: 2xx com permissão, 403 sem permissão, 401 anônimo | 100 | 100 |
| CT-RBAC-02 | E2-RBAC | DT | Escritas da Gestão: Financeiro, Suporte e Aluno recebem 403; anônimo recebe 401 | 80 | 80 |
| CT-RBAC-03 | E2-RBAC | SEC | Suporte não recebe nenhum valor financeiro nos dashboards | 3 | 3 |
| CT-RBAC-04 | E2-RBAC | SEC | Detalhe do aluno para o Suporte não traz valores | 1 | 1 |
| CT-SAL-01 | SALA | EP | Vídeo: aceita formatos do YouTube e Vimeo e recusa domínio parecido | 12 | 12 |
| CT-SAL-02 | SALA | BVA | Título até 200 e módulo até 120; duração de 0 a 6000 | 9 | 9 |
| CT-SAL-03 | SALA | BVA | Arquivo: 20 MB aceita, 20 MB + 1 byte recusa | 2 | 2 |
| CT-SAL-04 | SALA | EP | Arquivo: tipos permitidos passam; extensão falsa e executável não | 11 | 11 |
| CT-SAL-05 | SALA | ST | Publicado, oculto e excluído: a sala e o download acompanham | 1 | 1 |
| CT-SAL-06 | SALA | BVA | Mover nas pontas da lista mantém a ordem e direção inválida é 422 | 1 | 1 |
| CT-SAL-07 | SALA | UC | Trocar arquivo mantém o progresso e serve o conteúdo novo | 1 | 1 |
| CT-SAL-08 | SALA | DT | Certificado: sem conteúdo não sai; extra não conta; oculta aula pendente libera | 1 | 1 |
| CT-SAL-09 | SALA | SEC | Arquivo removido do disco devolve 404, sem expor caminho interno | 1 | 1 |
| CT-SAL-10 | SALA | EG | Excluir curso remove conteúdos e arquivos | 1 | 1 |
| CT-SAL-11 | SALA | SEC | Vídeo não se conclui à mão nem com tempo informado de uma vez só | 1 | 1 |
| CT-TUR-01 | TUR | BVA | Turma: capacidade mínima, nome e datas | 11 | 11 |
| CT-TUR-02 | TUR | ST | Turma: edita; com aluno não sai; capacidade não fica abaixo dos matriculados | 1 | 1 |
| CT-TUR-03 | TUR | DT | Atribuir matrícula a turma: lotada, de outro curso e inexistente são recusadas | 1 | 1 |
| CT-TUR-04 | TUR | SEC | Turmas públicas não expõem nomes nem e-mails de alunos | 1 | 1 |
| CT-TUR-05 | E1.2-Cursos | UC | Matrícula manual cria aluno novo, sem valor, e registra o motivo | 1 | 1 |
| CT-TUR-06 | E1.2-Cursos | EP | Matrícula manual recusa valor negativo, motivo vazio, e-mail ruim e curso inexistente | 4 | 4 |
| CT-UI-01 | E3-SPA | EP | Telas públicas abrem sem erro e sem rolagem lateral em celular, tablet e desktop | 28 | 28 |
| CT-UI-02 | E3-SPA | DT | Guarda de rotas: anônimo e perfil errado não entram nas áreas restritas | 5 | 5 |
| CT-UI-03 | E3-SPA | DT | Aluno não abre /admin e funcionário não abre /student | 1 | 1 |
| CT-UI-04 | RF23 | DT | Abas por perfil: cada aba abre sem erro de tela | 2 | 2 |
| CT-UI-05 | RF23 | DT | Financeiro vê a aba Financeiro e não vê Cadastro, Equipe nem Auditoria | 1 | 1 |
| CT-UI-06 | E3-SPA | UC | Navegar entre abas e telas não recarrega a página | 1 | 1 |
| CT-UI-07 | RF21 | EP | Login pela tela: senha errada mostra erro e o usuário continua no login | 1 | 1 |
| CT-UI-08 | RF21 | UC | Sair encerra a sessão: voltar não reabre a área restrita | 1 | 1 |
| CT-UI-09 | RF21 | ST | Sessão inválida na tela volta ao login com aviso | 1 | 1 |
| CT-UI-10 | E2-RBAC | SEC | Nome com HTML aparece como texto no painel e não executa script | 1 | 1 |
| CT-UI-11 | RF22 | UC | Aluno percorre painel, perfil, catálogo e recibo sem erro de tela, em celular e desktop | 3 | 3 |
| CT-UI-12 | E1.2-Alunos | EP | Painel do funcionário não estoura em celular | 2 | 2 |
| CT-UI-13 | RF21 | EP | Cadastro pela tela exige o aceite dos termos e mostra erro de senha curta | 1 | 1 |
| CT-UI-14 | SALA | UC | Gestão cadastra pela tela e o aluno usa a sala em celular de 320 px | 1 | 1 |
| CT-UI-15 | SALA | ST | Sala aberta: reembolso encerra o acesso na próxima ação do aluno | 1 | 1 |
| CT-UI-16 | CAD | UC | Gestão arquiva curso pela tela e ele some do catálogo do aluno | 1 | 1 |
| CT-UI-17 | RF24 | UC | Painel de IA mostra gráficos e o cartão de bloqueios | 1 | 1 |

Chamadas à API registradas na execução: 991.
