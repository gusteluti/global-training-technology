# Plano de atualização de design (PLANO_DESIGN)

Aprovado pelo PM em 22/11/2026 (D115) com a ordem "implemente o plano, não altere nenhuma lógica e funcionalidade". Só mexe em design: nenhuma regra de negócio, rota, API ou dado muda. Protótipo de referência: canvas "Landing GTT" (landing no computador e no celular, área do aluno, janela de confirmação do painel).

## Por que este plano

A análise das 79 capturas (aluno e equipe) mostrou que o problema não é só estilo. O app parece feito por IA porque repete os mesmos cartões, usa a marca de forma tímida e tem falhas reais de uso. Os fatos medidos:

- Texto em azul #0096c7 sobre branco tem contraste 3,39:1 (o mínimo AA é 4,5:1).
- 33 das 39 telas não têm título principal (h1).
- 8 ações usam a janela `confirm()` do navegador.
- Botões e links com 31 px de altura (o mínimo confortável é 44 px).
- Dois painéis rolam na horizontal no celular (411 px).
- A landing page não é um catálogo: o visitante não vê próxima turma, vagas nem carga horária.

Direção da marca, definida pelo PM: prática e direta, mas chamativa; cores atuais mantidas; logo oficial (anexa) sem alteração; a landing page é a porta de entrada e serve para transformar visitante em aluno.

## Regras que valem em todas as entregas

1. Só design. Se uma entrega exigir mudar API ou regra, ela para e vira decisão do PM.
2. Paleta fixa: #212830, #17212b, #0096c7, #0077a3, #ff7a18, #d8e0e8, #f7f9fb, #eaf8fc, #40c351. Cores novas só como variações de contraste da paleta (ex.: #005f84 para texto sobre fundo claro azulado) e ficam registradas em `docs/DESIGN.md`.
3. Logo: usar o arquivo oficial. Sobre fundo escuro, o original. Sobre fundo claro, a versão derivada (ver decisão D-A).
4. Ciclo TDD por entrega: agente-testes escreve os testes vermelhos, dev-frontend implementa até verde, regressão completa, e2e, merge `--no-ff` na branch do projeto, entrada D no `decisoes_tdd.md`, atualização do `PENDENCIAS.md`.
5. Ajustes mecânicos em `frontend/e2e/test_d4_polimento_visual.py` seguem a autoridade 4.3 e ficam registrados.
6. Critérios medidos, não opinião: contraste AA, um h1 por tela, rótulo ligado a cada campo, alvo de toque de 44 px, nenhum `confirm()`, nenhuma rolagem horizontal a 390 px.
7. Estado nunca só por cor (ícone ou texto junto), foco visível, sem emojis, sem rótulos em caixa alta com espaçamento.

## Mapa das entregas

| Entrega | O que muda | Depende de | Prototipado |
|---|---|---|---|
| DS0 Fundação | Tokens, contraste, tipografia, logo, `DESIGN.md` | nada | sim |
| DS1 Componentes base | Janela de confirmação, tabela responsiva, faixa de números, botões e alvos de 44 px, estados vazios | DS0 | sim (janela) |
| DS2 Área do aluno | Login, cadastro, painel, curso, perfil, catálogo interno | DS1 | sim (painel) |
| DS3 Painel da equipe | Abas, tabelas, formulários, aba de IA, as 8 janelas | DS1 | sim (janela) |
| DS4 Landing page | Catálogo que converte, mobile, CTA em laranja | DS1 e SG6 | sim (desktop e celular) |
| DS5 Fechamento | Regressão visual, `DESIGN.md` final, relatório | DS2, DS3, DS4 | não |

DS2 e DS3 não dependem entre si. Como o processo é um agente por vez, a ordem proposta é DS0, DS1, DS2, DS3, DS4, DS5.

## DS0 Fundação

- Tokens em `frontend/src/styles.css`: texto azul passa a #0077a3 (5,04:1) e #005f84 sobre fundo azulado; #0096c7 fica para preenchimentos, bordas e ícones, nunca para texto pequeno.
- Escala tipográfica única (Barlow para texto, Barlow Condensed 900 para títulos) com tamanhos mínimos de 14 px em apoio e 16 px em campos.
- Logo oficial no menu e no rodapé, com as duas variantes. Remove o disco "GT" desenhado em CSS.
- Atualiza `docs/DESIGN.md` (paleta com os pares de contraste, escala, espaçamento, regras de uso do laranja).

Testes vermelhos: contraste calculado de cada par texto/fundo usado nos tokens ≥ 4,5:1; nenhum texto pequeno usa #0096c7; logo presente no menu com `alt`; tamanho mínimo de fonte.

## DS1 Componentes base

- Janela de confirmação do próprio app (`role="alertdialog"`, foco preso, Esc fecha, foco volta ao botão de origem). Substitui os 8 `confirm()`; o texto diz o que acontece e se é reversível.
- Tabela responsiva: no celular vira lista de cartões, sem rolagem horizontal da página.
- Faixa de números (KPI) no lugar dos cartões soltos com ícone.
- Botões e links com 44 px de altura mínima; menu de ações por linha quando houver mais de duas.
- Estados vazios com texto e próxima ação.
- Um h1 por tela, rótulo ligado a cada campo.

Testes vermelhos: nenhum `window.confirm` no código; cada ação destrutiva abre a janela, e "Voltar" não executa nada; navegação por teclado dentro da janela; alvos ≥ 44 px (medidos); sem rolagem horizontal a 390 px nos dois painéis que hoje estouram.

## DS2 Área do aluno

Login, cadastro, esqueci a senha, painel (olá, faixa de números, cursos com progresso, próxima aula, pagamentos, ajuda), página do curso, perfil, catálogo interno. Cada tela com h1, estado de pagamento com texto e ícone, ação principal única e clara (por exemplo "Continuar curso" ou "Pagar agora").

Testes vermelhos: h1 em todas as rotas do aluno; estados de matrícula e pagamento com texto; fluxos de GR/D108 continuam passando; 390 px sem rolagem horizontal.

## DS3 Painel da equipe

Abas com sinal claro de seleção, tabelas com cabeçalho e legenda, filtros com rótulo, ações destrutivas com a janela da DS1, aba de IA mais curta (hoje é a mais longa, 2379 px), formulários agrupados.

Testes vermelhos: h1 por painel; `caption` ou título associado a cada tabela; cada ação destrutiva usa a janela; permissões por perfil (admin, financeiro, suporte) inalteradas; sem rolagem horizontal a 390 px.

## DS4 Landing page (depois do SG6)

A landing é reescrita como catálogo de conversão, seguindo o protótipo aprovado: topo escuro com a logo oficial, título direto, botão laranja com texto escuro (contraste 6,25:1; branco sobre laranja daria 2,61:1 e não passa), planilha como assinatura da marca, catálogo com filtros e cartões de curso, bloco para empresas, passos da compra, dúvidas, chamada final e rodapé.

Por que depois do SG6: o SG6 remove o script inline da landing e aplica a CSP. Refazer a página antes disso significaria fazer duas vezes.

Dados do cartão: nome, nível, formatos e preço já existem. Próxima turma, vagas e carga horária hoje não estão na API de cursos (ver decisão D-D).

Testes vermelhos: um h1; ordem dos blocos; CTA com contraste AA; cartões gerados a partir da API; filtros funcionam sem recarregar; 390 px sem rolagem horizontal; nenhum script inline; link de matrícula leva ao fluxo existente.

## DS5 Fechamento

Regressão completa (backend e e2e), varredura de contraste e h1 em todas as rotas, `DESIGN.md` final, capturas antes e depois no relatório, entrada D e `PENDENCIAS.md`.

## Decisões para o PM

| # | Decisão | Recomendação |
|---|---|---|
| D-A | Versão da logo para fundo claro. O arquivo oficial tem texto branco e só funciona sobre fundo escuro. Derivei uma versão com o texto em #212830 (mesmo desenho, só a cor do texto) | Aprovar a derivada, ou enviar a versão oficial para fundo claro |
| D-B | Laranja #ff7a18 como cor de ação de conversão. Hoje o `DESIGN.md` restringe o laranja ao nome na logo | Liberar o laranja só para o botão principal de matrícula, sempre com texto escuro |
| D-C | Números do topo (10k+, 500+, 100%) mantidos na D106 como ilustrativos | Trocar por garantias verificáveis (certificado, Mercado Pago, cancelamento em 7 dias). É o que o protótipo mostra |
| D-D | Próxima turma, vagas e carga horária no cartão de curso exigem campos na API de cursos | Autorizar o acréscimo desses campos (é a única exceção à regra "só design") ou aceitar o cartão sem eles |
| D-E | Link "Área do funcionário" sai do menu da landing e fica só no rodapé | Aprovar |
| D-F | Sequência: landing (DS4) só depois do SG6 | Aprovar |
| D-G | Fonte: continuar com Barlow via Google Fonts, ou hospedar os arquivos no projeto (melhor para a CSP do SG6) | Hospedar no projeto |

## Decisões resolvidas (D115)

| # | Resolução |
|---|---|
| D-A | Aprovada a versão derivada da logo para fundo claro (texto em #212830). Arquivos em `frontend/src/assets/brand/`. |
| D-B | Laranja liberado só para o botão principal de matrícula/conversão, sempre com texto #17212b. |
| D-C | Números ilustrativos do topo (10k+, 500+, 100%) trocados por garantias verificáveis. Revoga a parte da D106 que os mantinha. |
| D-D | **Rejeitada** pela ordem do PM de não alterar lógica: nenhum campo novo na API. O cartão de curso mostra só o que a API já entrega. |
| D-E | Aprovada: "Área do funcionário" sai do menu da landing e fica no rodapé. |
| D-F | A ordem do PM antecipa a DS4. A landing é refeita nesta onda **sem tocar no script inline** (mesmas funções, ids e chamadas); o SG6 depois só move o script para arquivo e aplica a CSP. |
| D-G | Barlow continua como está nesta onda; hospedar a fonte fica para o SG6, junto da CSP. |

## O que este plano não cobre

- Regras de negócio, rotas, API (exceto os campos da D-D, se aprovada), banco de dados.
- Novas funcionalidades, textos jurídicos (Termos e Privacidade), segurança (plano SG).
- Fotografias, ilustrações e vídeos: o protótipo usa só tipografia, a planilha e ícones. Imagens reais de aula melhorariam a landing, mas dependem de material da empresa.
- Tema escuro do app.

## Critério de pronto

Todas as entregas mergeadas com testes verdes; contraste AA em 100% dos pares usados; um h1 por rota; zero `confirm()`; zero rolagem horizontal a 390 px; landing sem script inline; `DESIGN.md` atualizado; relatório com capturas antes e depois; entradas D e `PENDENCIAS.md` em dia.
