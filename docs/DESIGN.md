# DESIGN.md — Global Training Technology

Sistema visual da landing (`frontend/landing_global_training.html`) e da SPA Angular (`frontend/src`). Serve para pessoas e
agentes de IA que forem mexer em qualquer tela: siga este arquivo para que as duas partes continuem parecendo um produto só.
Os valores abaixo são os mesmos de `frontend/src/styles.css` (tokens `--gt-*`) e do `:root` da landing. Decisões: D66, D93, D106,
D115 (plano de design `docs/tdd/PLANO_DESIGN.md`, DS0 a DS5).

## Assunto e público

Escola de treinamentos em ferramentas de trabalho (Excel, Power BI, SolidWorks e outras), com turmas presenciais, online ao
vivo e EAD, para profissionais e empresas. Três públicos: o visitante da landing (escolhe um curso), o aluno (acompanha
cursos, pagamentos e materiais) e a equipe interna (Gestão, Financeiro, Suporte, no painel administrativo).

O visual parte desse assunto. O elemento marcante da landing é uma **planilha** com os cursos abertos, lidos do catálogo:
é o mundo das ferramentas que a escola ensina. A ousadia fica nesse lugar só; o resto da página é calmo.

## Cores

| Token | Valor | Uso | Contraste medido (WCAG) |
|---|---|---|---|
| `--gt-nav` | `#212830` | barra superior, rodapé, cabeçalho do chat | branco sobre ele 14,88:1; rodapé `#9aa3ad` sobre ele 5,82:1 |
| `--gt-text` | `#17212b` | texto, números dos KPIs, texto do botão laranja de conversão | sobre `#ff7a18` 6,25:1 |
| `--gt-muted` | `#66707c` (landing `#5b6672`) | texto de apoio, rótulos | 5,03:1 sobre `#ffffff`; 4,77:1 sobre `#f7f9fb` |
| `--gt-link` | `#0077a3` | **texto azul**: links (`--bs-link-color`), aba ativa, preço, `.btn-outline-primary`; fundo do `.btn-primary` | 5,04:1 sobre `#ffffff`; 4,77:1 sobre `#f7f9fb`; 4,64:1 sobre `#eaf8fc`; branco sobre ele 5,04:1 |
| `--gt-link-hover` | `#005f84` | hover de link e do `.btn-primary`; texto azul sobre fundo azulado (`.alert-info`) | 7,07:1 sobre `#ffffff`; 6,70:1 sobre `#f7f9fb`; 6,51:1 sobre `#eaf8fc`; branco sobre ele 7,07:1 |
| `--gt-teal` | `#0096c7` | **só preenchimento, borda, foco e ícone** (barra de progresso, indicador das abas, contorno de foco). Nunca texto pequeno | 3,39:1 sobre `#ffffff` (abaixo do AA para texto normal; só vale em texto grande, >= 24 px ou >= 18,66 px em negrito) |
| `--gt-teal-dark` | `#0077a3` | mesmo valor de `--gt-link`; mantido para preenchimentos já existentes (item ativo da sala, bolha do aluno) | branco sobre ele 5,04:1 |
| `--gt-orange` / `--gt-cta` | `#ff7a18` | nome "Global Training" no logo e **só o botão principal de matrícula/conversão** (`.btn-cta`), sempre com texto `#17212b` (D115, D-B) | texto `#17212b` 6,25:1; texto branco daria 2,61:1 (proibido) |
| `--gt-cta-hover` | `#e86a0c` | hover/ativo do `.btn-cta` | texto `#17212b` 5,04:1 |
| texto de apoio no escuro | `#cbd5df` | texto de apoio sobre `#212830` (hero da landing, rótulo de painel) | 10:1 sobre `#212830` |
| foco no escuro | `#7fd8f0` | contorno de foco e ícones sobre `#212830` (barra da SPA, hero e rodapé da landing) | — |
| vermelho destrutivo | `#b42318` | só o botão de confirmar da janela destrutiva (`.gt-btn-destrutiva`) | branco sobre ele 6,57:1 |
| `--gt-border` | `#d8e0e8` | bordas de cartões e campos | — |
| `--gt-bg-soft` | `#f7f9fb` | fundo da SPA e de seções alternadas | — |
| `--gt-soft-blue` | `#eaf8fc` | fundos suaves (ícone de iniciais, hover de tabela, `.alert-info`) | — |
| verde WhatsApp | `#40c351` | só o botão de chat e o botão do WhatsApp | — |

No Bootstrap, `--bs-primary`/`--bs-primary-rgb` e `--bs-link-color` apontam para `#0077a3` e `--bs-link-hover-color` para
`#005f84`; `.btn-primary` e `.btn-outline-primary` definem as variáveis `--bs-btn-*` com `--gt-link`/`--gt-link-hover` em
todos os estados (normal, hover, ativo, desabilitado), sempre com texto branco sobre o azul. Cor nova só como variação de
contraste da paleta, registrada nesta tabela (D115).

Regras:
- **Contraste AA medido** (D115): texto normal >= 4,5:1 sobre o fundo efetivo; texto grande >= 3:1. Os e2e da DS0 medem pelo
  estilo computado (`frontend/e2e/apoio_contraste.py`).
- Texto azul usa `--gt-link`; `#0096c7` nunca é cor de texto pequeno.
- **Cor é para dados e estados.** Nos painéis, os números ficam na cor do texto (`.gt-kpi`); verde, amarelo e vermelho
  aparecem nos status (badges), nos gráficos e quando há um problema real (ex.: tópicos não compreendidos > 0).
- Não destacar uma palavra do título com outra cor.
- Status nunca só por cor: o badge sempre tem o texto ("Aprovado", "Em análise").

## Tipografia

- **Barlow** (400, 600, 700, 900) para texto e interface; **Barlow Condensed** (700, 900) para títulos e números grandes.
- Títulos: Barlow Condensed 900, entrelinha ~1.0. Landing: h1 64 px (44 px no celular), h2 42 px (34 px no celular).
- Texto: 15–18 px na landing, 14–16 px na SPA; linhas com até ~80 caracteres.
- **Piso de tamanho (D115):** nenhum texto visível abaixo de **14 px** (rótulos `.form-label`, texto de apoio, `.small`,
  rodapé, rótulo de perfil na barra); campos de formulário com **16 px**. Não reduzir o que já está acima disso.
- Números em tabelas, preços e KPIs com `font-variant-numeric: tabular-nums`.
- Valores em reais sempre no formato brasileiro (`R$ 1.234,00`), via `Intl.NumberFormat('pt-BR')` ou o pipe `currency:'BRL'`.
- **Sem rótulos em maiúsculas espaçadas** acima dos títulos. O rótulo de área da SPA (`.gt-tag`, ex.: "Área do aluno") é
  texto normal, 15 px, cinza: ele informa onde a pessoa está, não decora. Exceção: o "TECHNOLOGY" do logo, que é marca.

## Logo

- Arquivos oficiais em `frontend/src/assets/brand/` (servidos em `assets/brand/...` pelo `ng serve` e pelo `ng build`):
  `gtt-logo-fundo-escuro.webp`/`.png` (original, texto branco), `gtt-logo-fundo-claro.webp`/`.png` (versão derivada com o
  texto em `#212830`, mesmo desenho, aprovada na D115, D-A) e `gtt-simbolo.png` (só o símbolo).
- Sobre fundo escuro (barra superior da SPA, rodapé, topo da landing) usa a versão de **fundo escuro**; sobre fundo claro, a
  versão de **fundo claro**. Não redesenhar, recolorir nem recortar o arquivo.
- Na landing o logo vai embutido como `data:` URI (barra e rodapé), porque o servidor de teste da landing só serve o HTML.
  Sai do HTML quando a landing ganhar arquivos estáticos próprios (SG6).
- Na barra da SPA o logo é um único `<img>` com `alt="Global Training Technology"` dentro do link `[data-testid=app-logo]`,
  com altura de 52 px no computador e 44 px no celular (`width: auto`). O antigo disco "GT" desenhado em CSS saiu (DS0).

## Componentes

- **Botões:** primário azul `--gt-link` com texto branco (hover `--gt-link-hover`; uma ação principal por área); secundário
  com borda e texto `--gt-link`; raio 8 px. O laranja (`.btn-cta`) só aparece no botão principal de matrícula/conversão, com
  texto `#17212b` (D-B): na SPA, "Comprar cursos" no cabeçalho da área do aluno (botão retangular, fora da barra de atalhos) e "Comprar" no catálogo; na landing, o CTA do hero e
  "Matricular agora" nos cartões. Um cartão nunca tem dois botões laranja.
- **Área do aluno (DS2b, D122):** sem cartão em volta da saudação; o h1 "Olá, <nome>!" fica direto sobre o fundo, com o CTA
  laranja à direita (largura total no celular). Os atalhos de seção são uma barra de texto com sublinhado de 2 px no
  hover/foco, não pílulas. "Meus cursos" é uma coluna de largura total, um curso por linha: ícone, nome com o status ao lado,
  matrícula/turma, barra de progresso (`role="progressbar"`) com o percentual, e a ação "Entrar no curso" à direita. Materiais,
  avaliação (numa linha), certificado e cancelamento ficam num bloco secundário `#f7f9fb` dentro do cartão.
- **Janela de confirmação (DS1):** toda ação destrutiva ou irreversível usa `ConfirmacaoService.confirmar({titulo, texto?,
  rotuloConfirmar, destrutiva?})`, que abre o `ConfirmacaoComponent` único da casca (`role="alertdialog"`,
  `[data-testid=confirmacao]`, botões `confirmacao-voltar` e `confirmacao-confirmar`). Foco preso na janela, Esc = Voltar,
  foco volta ao botão de origem. O título diz o que acontece; o texto diz se dá para desfazer. Nunca `window.confirm()`.
  Exceção: excluir curso e excluir conteúdo mantêm a confirmação em dois passos na própria linha (D119).
- **Badge de status (`.badge-status`):** ponto de 8 px em `::before` (cor do texto) mais o rótulo por extenso. O texto do
  badge é só o rótulo ("Ativa", "Em análise"); o ponto não tem texto.
- **Faixa de números (`.gt-faixa`, DS3):** um `<dl>` com itens lado a lado, borda e raio só no contêiner, divisória por
  `border-left`; empilha no celular. Rótulo 14 px cinza em `dt`, número em Barlow Condensed em `dd`. Usada nos KPIs do
  Financeiro; a área do aluno usa a faixa equivalente `.aluno-resumo` (`<dl data-testid="aluno-resumo">`).
- **Tabelas:** cada tabela tem `aria-labelledby` apontando para o título da seção e `scope="col"` em todo `th`; a coluna de
  ações tem o cabeçalho "Ações" visualmente oculto. Cabeçalho `#f3f6f9` com texto `#3b4652`. No celular, rolagem só dentro do
  `.table-responsive`, nunca na página.
- **Estado vazio:** frase do que falta e a próxima ação (ex.: "Você ainda não tem cursos." com o link "Ver cursos").
- **Alvo de toque:** botões, links de ação e controles com pelo menos **44 px** de altura (regra da D115, aplicada na DS1).
- **Cartões:** borda `--gt-border`, raio 8 px, sombra leve. Não aninhar cartão dentro de cartão.
- **Ícone de curso:** quadrado suave com as iniciais do curso (landing `.course-icon`, SPA `.catalogo-icone` e
  `.curso-icone`). Não usar emojis como ícone; ícones de interface são SVG inline.
- **Planilha do hero:** barra de fórmula, letras de coluna, números de linha, uma linha por curso e o total. Clicar numa
  linha leva ao cartão do curso. No celular a coluna "Nível" encolhe a zero.
- **Títulos por tela (DS1–DS3):** um `h1` por rota (no `/admin`, "Painel administrativo"); um `h2` no topo de cada aba e
  subpainel; seções em `h3`/`h4`. Quando o nível subiu, a classe de tamanho antiga ficou (`<h1 class="card-title h4">`), para
  o visual não mudar.
- **Abas do painel:** a aba ativa tem o texto em `--gt-link` e um indicador teal (preenchimento) desliza até ela
  (`.gt-abas-indicador`).
- **Chat:** bolhas; resposta do assistente revelada de cima para baixo; avatar "GT".

## Landing (DS4)

Ordem dos blocos, pensada como catálogo que converte: barra escura (logo, links de seção Cursos, Como funciona, Dúvidas,
ocultos abaixo de 720 px, e "Área do aluno") → hero `#212830` com título direto, CTA laranja "Ver cursos abertos", garantias
verificáveis e a planilha → `#cursos` (cartões gerados pela API, "Matricular agora" laranja e "Tirar dúvidas com IA"
secundário) → "Treinamento para a sua empresa" (abre o chat) → passos (`#como-funciona`) → "Em todos os cursos" →
"Dúvidas frequentes" (`#duvidas`, respostas tiradas de `backend/knowledge`) → faixa final → rodapé com "Área do funcionário"
(D-E). O script inline é o mesmo de antes da DS4 (guarda `test_ds4_script_inalterado.py`); a remoção dele e a CSP são da SG6.

## Movimento

Três momentos, todos desligados com `prefers-reduced-motion: reduce`:
1. o cursor de célula da planilha percorre as linhas de curso uma vez ao abrir a landing;
2. o indicador das abas desliza até a aba clicada;
3. a resposta do chat é revelada de cima para baixo (o texto inteiro já está no DOM desde o início).

Fora isso, só transições curtas (0,2 s) de cor, borda e sombra no hover. Nunca `transition: all`; nunca fade em cada seção.

## Acessibilidade (piso)

- Contraste AA em todo texto (ver "Cores"); texto de apoio com 14 px no mínimo.
- Foco por teclado sempre visível (`:focus-visible`, contorno teal de 2 px).
- Alvo de toque >= 44 px (DS1).
- Botões só com ícone têm `aria-label`; campos têm rótulo ou `aria-label`.
- Um `h1` por página; títulos de seção em `h2`.
- Campo de texto com 16 px no celular (o iOS não dá zoom).
- Link "Pular para o conteúdo" na landing.
- Sem rolagem horizontal em 390 px.

## Textos

- Dizer o que acontece, no vocabulário do aluno: "Ver cursos abertos", "Matricular agora", "Tirar dúvidas no chat".
- Descrever o fluxo real (a matrícula acontece na área do aluno, o pagamento é pelo Mercado Pago, os materiais aparecem
  quando o pagamento é confirmado). Não prometer o que o sistema não faz.
- Erros dizem o que houve e como resolver, sem pedir desculpa vaga.
- Os números do hero (10k+, 500+, 100%) eram ilustrativos do protótipo, mantidos na D106. A D115 (D-C) revogou essa parte da
  D106 e a DS4 trocou os números por garantias verificáveis (certificado de conclusão, pagamento pelo Mercado Pago,
  cancelamento em 7 dias). Não voltar a usar números que o sistema não comprova.
- A janela de confirmação diz o que acontece e se dá para desfazer; o botão de confirmar repete a ação ("Cancelar
  matrícula"), nunca "OK" ou "Sim".

## Como verificar

`py -3 -m pytest frontend/e2e/test_d4_polimento_visual.py -s` confere as regras acima no navegador (estilo computado).
`py -3 -m pytest frontend/e2e/test_ds0_fundacao_angular.py -s` confere logo, contraste AA dos tokens e o piso de 14 px (D115).
Os e2e `test_ds1_*`, `test_ds2_area_aluno_angular.py`, `test_ds3_painel_equipe_angular.py`, `test_ds4_landing.py` e
`test_ds4_script_inalterado.py` conferem, tela a tela, contraste AA pelo estilo computado, um `h1`, rótulos de campo, alvos de
44 px, ausência de `confirm()` e de rolagem horizontal em 390 px (apoio em `frontend/e2e/apoio_contraste.py` e
`frontend/e2e/apoio_confirmacao.py`).
