# Escopo — Sala do curso (conteúdos do aluno)

Proposta para aprovação do PM (03/11/2026). Nada implementado.

## Objetivo
O aluno com matrícula ativa abre uma página do curso e, sem sair da plataforma, assiste às videoaulas gravadas, lê a
apostila e acessa os conteúdos extras daquele curso. A Gestão organiza esse conteúdo por uma tela própria.

## O que existe hoje
- `materials: [{title, url, type}]` no JSON do curso, digitado numa caixa de texto ("Título | URL | tipo").
- O aluno vê uma lista de links no cartão do curso; cada link abre fora da plataforma.
- Progresso por caixa de seleção, com a URL como identificador. O certificado sai com todos os materiais concluídos.
- Só a matrícula ativa recebe as URLs. Mas quem tiver o link consegue abrir, porque o arquivo está fora da plataforma.
- Não há envio de arquivo: é preciso hospedar em outro lugar e colar a URL.

## O que entra

### Aluno
- Botão "Entrar no curso" no cartão de matrícula ativa, que abre `/aluno/curso/:id`.
- Conteúdo organizado em módulos, com aulas em ordem.
- Tipos: **vídeo** (player na própria página), **apostila ou arquivo** (abrir e baixar), **link externo**.
- Seção "Conteúdos extras", separada das aulas.
- Barra de progresso, marcar como concluído e destaque de "continuar de onde parei".

### Gestão
- Tela de conteúdos por curso: criar módulo, adicionar aula, enviar arquivo, colar link de vídeo, reordenar, publicar e
  ocultar. Só o perfil Gestão edita.
- Toda alteração entra na auditoria.

### Regras de acesso
- Só matrícula `active` vê e baixa. `pending`, `cancelled` e `refunded` não recebem título de aula, URL nem arquivo.
- Matrícula alheia devolve o mesmo 404 das demais telas.
- Arquivo servido por endpoint autenticado, com a matrícula conferida a cada download. Nunca por URL pública.
- Quem perde a matrícula perde o acesso na hora, inclusive com a página aberta.
- Curso arquivado continua acessível para quem tem matrícula ativa (como na F1).

## Decisões técnicas propostas
- **Vídeo por incorporação de YouTube (não listado) ou Vimeo**, sem upload ao servidor: não há custo de armazenamento
  nem de streaming. Limite assumido: o link não listado pode ser repassado por quem o tiver.
- **Arquivos no servidor**, em pasta privada fora do repositório, com limite de 20 MB e tipos permitidos: PDF, Word,
  Excel, PowerPoint e ZIP.
- **Tabela nova `course_contents`** no lugar do JSON, com id próprio. O progresso passa a usar esse id, para não se perder
  quando a URL mudar.
- **Migração automática:** os `materials` atuais viram um módulo "Materiais", mantendo o progresso de quem já marcou.

## Fora do escopo
Upload de vídeo, proteção contra cópia (DRM), provas e quizzes, comentários por aula, aulas ao vivo, transcrição, assistente
que responde sobre o conteúdo das aulas, liberação gradual por data e conteúdo por turma.

## Entregas
| # | Entrega | Resultado |
|---|---|---|
| C1 | Modelo e API | Tabela, migração dos materiais, leitura do aluno, progresso por id |
| C2 | Arquivos | Upload pela Gestão e download autenticado |
| C3 | Sala do curso | Página do aluno com player, módulos, extras e progresso |
| C4 | Tela da Gestão | Módulos, aulas, ordem, publicação e auditoria |

## Decisões do PM
1. **Vídeos:** YouTube não listado ou Vimeo? Recomendação: aceitar os dois.
2. **Certificado:** só as aulas contam, e os extras ficam de fora? Recomendação: sim.
3. **Prévia antes da compra:** alguma aula aberta no catálogo? Recomendação: não nesta fase.
4. **Fim da turma:** o acesso continua depois do término? Recomendação: sim, enquanto a matrícula estiver ativa.
5. **Conteúdo por curso ou por turma?** Recomendação: por curso.
