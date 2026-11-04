# DESIGN.md — Global Training Technology

Sistema visual da landing (`frontend/landing_global_training.html`) e da SPA Angular (`frontend/src`). Serve para pessoas e
agentes de IA que forem mexer em qualquer tela: siga este arquivo para que as duas partes continuem parecendo um produto só.
Os valores abaixo são os mesmos de `frontend/src/styles.css` (tokens `--gt-*`) e do `:root` da landing. Decisões: D66, D93, D99.

## Assunto e público

Escola de treinamentos em ferramentas de trabalho (Excel, Power BI, SolidWorks e outras), com turmas presenciais, online ao
vivo e EAD, para profissionais e empresas. Três públicos: o visitante da landing (escolhe um curso), o aluno (acompanha
cursos, pagamentos e materiais) e a equipe interna (Gestão, Financeiro, Suporte, no painel administrativo).

O visual parte desse assunto. O elemento marcante da landing é uma **planilha** com os cursos abertos, lidos do catálogo:
é o mundo das ferramentas que a escola ensina. A ousadia fica nesse lugar só; o resto da página é calmo.

## Cores

| Token | Valor | Uso |
|---|---|---|
| `--gt-nav` | `#212830` | barra superior, rodapé, cabeçalho do chat |
| `--gt-text` | `#17212b` | texto, números dos KPIs, botão "Matricular agora" |
| `--gt-muted` | `#66707c` (landing `#5b6672`) | texto de apoio, rótulos |
| `--gt-teal` | `#0096c7` | ação principal, links, aba ativa, foco, preço |
| `--gt-teal-dark` | `#0077a3` | hover da ação principal |
| `--gt-orange` | `#ff7a18` | só o nome "Global Training" no logo |
| `--gt-border` | `#d8e0e8` | bordas de cartões e campos |
| `--gt-bg-soft` | `#f7f9fb` | fundo da SPA e de seções alternadas |
| `--gt-soft-blue` | `#eaf8fc` | fundos suaves (ícone de iniciais, hover de tabela) |
| verde WhatsApp | `#40c351` | só o botão de chat e o botão do WhatsApp |

Regras:
- **Cor é para dados e estados.** Nos painéis, os números ficam na cor do texto (`.gt-kpi`); verde, amarelo e vermelho
  aparecem nos status (badges), nos gráficos e quando há um problema real (ex.: tópicos não compreendidos > 0).
- Não destacar uma palavra do título com outra cor.
- Status nunca só por cor: o badge sempre tem o texto ("Aprovado", "Em análise").

## Tipografia

- **Barlow** (400, 600, 700, 900) para texto e interface; **Barlow Condensed** (700, 900) para títulos e números grandes.
- Títulos: Barlow Condensed 900, entrelinha ~1.0. Landing: h1 64 px (44 px no celular), h2 42 px (34 px no celular).
- Texto: 15–18 px na landing, 14–16 px na SPA; linhas com até ~80 caracteres.
- Números em tabelas, preços e KPIs com `font-variant-numeric: tabular-nums`.
- Valores em reais sempre no formato brasileiro (`R$ 1.234,00`), via `Intl.NumberFormat('pt-BR')` ou o pipe `currency:'BRL'`.
- **Sem rótulos em maiúsculas espaçadas** acima dos títulos. O rótulo de área da SPA (`.gt-tag`, ex.: "Área do aluno") é
  texto normal, 15 px, cinza: ele informa onde a pessoa está, não decora. Exceção: o "TECHNOLOGY" do logo, que é marca.

## Componentes

- **Botões:** primário teal com texto branco (uma ação principal por área); secundário com borda; raio 8 px.
- **Cartões:** borda `--gt-border`, raio 8 px, sombra leve. Não aninhar cartão dentro de cartão.
- **Ícone de curso:** quadrado suave com as iniciais do curso (landing `.course-icon`, SPA `.catalogo-icone` e
  `.curso-icone`). Não usar emojis como ícone; ícones de interface são SVG inline.
- **Planilha do hero:** barra de fórmula, letras de coluna, números de linha, uma linha por curso e o total. Clicar numa
  linha leva ao cartão do curso. No celular a coluna "Nível" encolhe a zero.
- **Abas do painel:** um indicador teal desliza até a aba ativa (`.gt-abas-indicador`).
- **Chat:** bolhas; resposta do assistente revelada de cima para baixo; avatar "GT".

## Movimento

Três momentos, todos desligados com `prefers-reduced-motion: reduce`:
1. o cursor de célula da planilha percorre as linhas de curso uma vez ao abrir a landing;
2. o indicador das abas desliza até a aba clicada;
3. a resposta do chat é revelada de cima para baixo (o texto inteiro já está no DOM desde o início).

Fora isso, só transições curtas (0,2 s) de cor, borda e sombra no hover. Nunca `transition: all`; nunca fade em cada seção.

## Acessibilidade (piso)

- Foco por teclado sempre visível (`:focus-visible`, contorno teal de 2 px).
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
- Os números do hero (10k+, 500+, 100%) são ilustrativos do protótipo, mantidos por decisão do PM (D99).

## Como verificar

`py -3 -m pytest frontend/e2e/test_d4_polimento_visual.py -s` confere as regras acima no navegador (estilo computado).
