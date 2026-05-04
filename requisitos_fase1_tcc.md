# Requisitos da Fase 1 do TCC

## 1. Escopo da Fase 1

A fase 1 do projeto terá como foco a construção de uma **landing page** para uma escola de tecnologia, contendo um **chatbot com inteligência artificial** integrado. Nessa etapa inicial, a plataforma ainda não terá todas as funcionalidades planejadas para o sistema completo, mas já deverá atender os principais pontos de contato entre instituição e cliente.

O objetivo principal dessa fase é permitir que o visitante conheça os cursos oferecidos, tire dúvidas de forma rápida e seja conduzido à compra diretamente pela landing page. Além disso, o chatbot também deverá oferecer apoio acadêmico inicial ao aluno, ajudando com dúvidas sobre cursos, conteúdos e orientações básicas relacionadas aos estudos.

A landing page deverá:
- apresentar a instituição e os cursos ofertados;
- destacar benefícios, diferenciais e informações relevantes para conversão;
- permitir a inscrição e a compra do curso no próprio ambiente;
- permitir o pagamento sem que o usuário precise sair da página;
- disponibilizar um chatbot com atuação comercial e acadêmica.

O chatbot deverá ter duas frentes de atuação:
1. **Comercial**, ajudando na captação de clientes, respondendo dúvidas, apresentando cursos e conduzindo o usuário até a compra;
2. **Acadêmica**, auxiliando alunos com dúvidas iniciais sobre aulas, conteúdos, trilhas de estudo e informações gerais da plataforma.

Também faz parte do escopo da fase 1 a definição dos requisitos necessários para que a experiência do usuário seja simples, clara, persuasiva e funcional, principalmente no processo de venda e pagamento.

---

## 2. Requisitos Funcionais

### RF01 – Exibição da landing page
O sistema deve disponibilizar uma landing page com informações institucionais da escola de tecnologia, seus cursos, benefícios, diferenciais e chamadas para ação.

### RF02 – Apresentação dos cursos
O sistema deve apresentar os cursos disponíveis com informações como nome, descrição, objetivos, público-alvo, carga horária, preço e benefícios.

### RF03 – Chatbot para atendimento comercial
O sistema deve disponibilizar um chatbot com IA capaz de responder dúvidas sobre a instituição, cursos, preços, formas de pagamento e processo de inscrição.

### RF04 – Chatbot para apoio acadêmico inicial
O chatbot deve ser capaz de responder dúvidas acadêmicas básicas dos alunos, como informações sobre cursos, organização de estudos, conteúdos introdutórios e orientações gerais.

### RF05 – Persuasão comercial no atendimento
O chatbot deve conduzir a conversa de forma persuasiva, incentivando o potencial cliente a concluir a compra, utilizando argumentos relacionados aos benefícios do curso, diferenciais da instituição e adequação do curso ao perfil do usuário.

### RF06 – Direcionamento para compra
O sistema deve permitir que o chatbot encaminhe o usuário para a compra do curso por meio de botões, links internos ou chamadas para ação dentro da landing page.

### RF07 – Cadastro do usuário
O sistema deve permitir que o usuário informe seus dados básicos para prosseguir com a inscrição no curso.

### RF08 – Inscrição em curso
O sistema deve permitir que o usuário realize sua inscrição no curso escolhido diretamente pela landing page.

### RF09 – Compra do curso na landing page
O sistema deve permitir que a compra do curso seja realizada dentro da própria landing page, sem necessidade de redirecionamento para outro ambiente principal da plataforma.

### RF10 – Processamento de pagamento
O sistema deve permitir que o usuário escolha uma forma de pagamento disponível e conclua a transação pela landing page.

### RF11 – Confirmação de pagamento
O sistema deve informar ao usuário se o pagamento foi aprovado, recusado, pendente ou se houve falha no processamento.

### RF12 – Confirmação de inscrição
Após a confirmação do pagamento, o sistema deve registrar a inscrição do aluno no curso adquirido.

### RF13 – Registro de dados da compra
O sistema deve armazenar as informações essenciais da compra, como curso adquirido, valor pago, data da transação, status do pagamento e identificação do comprador.

### RF14 – Histórico básico de pagamentos
O sistema deve permitir o registro e consulta dos pagamentos realizados, ao menos em nível administrativo ou de controle interno da plataforma.

### RF15 – Mensagens automáticas de orientação
O sistema deve apresentar mensagens automáticas orientando o usuário durante as etapas de navegação, inscrição, compra e pagamento.

### RF16 – Atendimento contínuo durante a navegação
O chatbot deve estar acessível ao usuário durante sua permanência na landing page, permitindo interação a qualquer momento.

### RF17 – Encaminhamento de dúvidas frequentes
O sistema deve permitir que o chatbot responda perguntas frequentes sobre cursos, valores, certificação, duração, metodologia e suporte ao aluno.

### RF18 – Suporte à decisão de compra
O chatbot deve ser capaz de identificar dúvidas ou objeções do cliente e responder de forma a aumentar a chance de conversão.

### RF19 – Acesso inicial do aluno após compra
Após a compra, o sistema deve permitir que o aluno receba instruções iniciais de acesso e apoio acadêmico básico por meio do chatbot ou da própria plataforma.

### RF20 – Controle do status da inscrição
O sistema deve manter o status da inscrição do usuário, indicando se está iniciada, pendente, concluída ou cancelada.

---

## 3. Requisitos Não Funcionais

### RNF01 – Usabilidade
A landing page deve possuir interface simples, intuitiva e de fácil navegação, permitindo que o usuário encontre informações e conclua a compra com poucos passos.

### RNF02 – Clareza na comunicação
As informações exibidas na landing page e as respostas do chatbot devem ser objetivas, claras e adequadas ao perfil do público-alvo.

### RNF03 – Desempenho
O sistema deve responder às interações do usuário em tempo adequado, evitando lentidão na navegação, no carregamento da página e no uso do chatbot.

### RNF04 – Disponibilidade
A landing page e o chatbot devem estar disponíveis para acesso contínuo, principalmente em períodos de campanhas e captação de alunos.

### RNF05 – Segurança de dados
O sistema deve proteger os dados pessoais e financeiros informados pelo usuário durante cadastro, inscrição e pagamento.

### RNF06 – Segurança na transação
O processo de pagamento deve ocorrer em ambiente seguro, com proteção contra falhas, perda de dados e acessos indevidos.

### RNF07 – Confiabilidade
O sistema deve registrar corretamente as informações de inscrição, compra e pagamento, evitando inconsistências de dados.

### RNF08 – Responsividade
A landing page deve funcionar adequadamente em computadores, tablets e smartphones.

### RNF09 – Escalabilidade inicial
O sistema deve suportar múltiplos acessos simultâneos sem comprometer a experiência do usuário, especialmente em ações promocionais.

### RNF10 – Qualidade do atendimento do chatbot
O chatbot deve manter respostas coerentes, relevantes e compatíveis com o contexto da conversa, tanto na parte comercial quanto acadêmica.

### RNF11 – Persuasão sem agressividade
O chatbot deve utilizar técnicas de convencimento de forma ética, sem pressão excessiva, linguagem abusiva ou indução enganosa.

### RNF12 – Facilidade de manutenção
A estrutura da landing page, das informações dos cursos e do comportamento do chatbot deve permitir atualização futura com facilidade.

### RNF13 – Integração
O sistema deve ser preparado para integração com serviços de pagamento, cadastro de alunos e futura expansão da plataforma acadêmica.

### RNF14 – Acessibilidade básica
A landing page deve seguir boas práticas mínimas de acessibilidade, com textos legíveis, contraste adequado e navegação compreensível.

### RNF15 – Privacidade
O tratamento dos dados do usuário deve respeitar princípios de privacidade e consentimento, especialmente no cadastro e no pagamento.

---

## 4. Observações para a reunião de orientação

Para a próxima reunião, a proposta da fase 1 pode ser apresentada como um **MVP (Produto Mínimo Viável)** com foco em:
- captação de clientes por meio de uma landing page;
- uso de chatbot com IA para conversão de vendas;
- apoio acadêmico inicial ao aluno;
- inscrição, compra e pagamento diretamente no ambiente;
- estrutura inicial que possa evoluir futuramente para uma plataforma educacional mais completa.

Essa definição ajuda a delimitar bem o projeto, deixando claro que a primeira entrega será enxuta, mas já demonstrará valor real para a instituição e para o usuário final.
