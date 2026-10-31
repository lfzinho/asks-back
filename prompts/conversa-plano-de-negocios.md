# Conversa: elaboração do plano de negócios (AsksBack)

Registro da conversa usada para montar o plano de negócios do hackathon. Os prompts do usuário estão na íntegra, como foram enviados. As respostas do assistente aparecem resumidas.

Data: 31/10/2026

---

## 1

**Prompt:**

> O que é importante ter no plano de negócios de uma empresa?

**Resposta (resumo):** estrutura de plano de negócios segundo o Sebrae (sumário executivo, análise de mercado, marketing, operacional, financeiro, cenários, avaliação), com links para os manuais e o curso gratuito do Sebrae.

---

## 2

**Prompt** (com o PDF "Avaliação Dinâmica com IA — Embasamento e Conceito" anexado):

> Bom, nós temos uma ideia geral de produto e estamos refinando as funcionalidades específicas dele. Como vc pode ler no pdf, a ideia é ter um avaliador de provas que não só atribui uma nota mas também usa do diálogo socrático para conseguir entender mais a fundo o pq o aluno errou. O aluno vai bater um papo e depois o professor vai ter acesso ao papo e a um sumário dizendo o porque ele errou e quais seriam as notas nos eixos do pdf.
>
> Vamos começar pelo mercado. Que há de semelhante no mercado? IA assistente para alunos sei que há de monte, mas e IA que usa essas abordagens descritas e embasadas no doc?

**Resposta (resumo):** mapeamento de concorrentes (Sherpa, Socratic Mind, Eduface, OralExam.ai, Rocketproof, Prova, FeedbackFruits, Classmoji), do precedente ASSISTments para pontuar a ajuda recebida e de corretores brasileiros sem diálogo. Diferencial apontado: escada de mediação pontuada, gatilho seletivo e perfil por turma.

---

## 3

**Prompt:**

> Entendo que o diferencial aqui é mais a escada e o perfil diagnóstico por turma do que o gatilho seletivo. Entendo também que é válido nós nos apoiarmos no ponto de que essas soluções são todas de fora, e que não há nada parecido no Brasil. Você concorda?
>
> Pensando nessa parte de mercado também, faz um sumário geral do tamanho do mercado de escolas particulares do Brasil, já que nosso mercado é esse (escolas/redes de ensino).

**Resposta (resumo):** concordância parcial (perfil por turma já existe em players como a ClavIA; o gatilho seletivo é um diferencial de produto). Alerta sobre as diretrizes do CNE que reservam a nota ao professor. Números do mercado: ~42 mil escolas, 9,2 milhões de matrículas (Censo 2025), R$ 112 bi de faturamento (Hoper), 67% das escolas com menos de 200 alunos.

---

## 4

**Prompt:**

> Faltou contexto. Estou montando esse plano para umia entrega de hackahton. Estamos desnvolvendo um MVP, então talvez seja legal o plano diferenciar o que já existe od que é uma feature que consideramos importante para o produto final mas que ainda não está pornta.
>
> Então vamos lá. Me vai me ajudando mantendo um sumário do que vai ser o nosso plano de négocios.
>
> Propósito geral: ferramenta que avalia os alunos não só com base na prova mas também num dialógo socrático.
>
> Features interessantes:
>
> * Avaliação só dos alunos que precisam
> * Escada de medição que vira *sugestão* de nota para o professor. O professor tem a palavra final *sempre*
> * Gatilhos específicos para tipos de pergunta diferentes
>
> essa parte de perfil diagnóstico por turma não vai estar presente agora, e sim uma feature que consideramos essencial.
>
> Mercado:
>
> * Escolas particulares. Se vão ser redes ou pequenas vamos tentar concluir melhor depois de medir bem os custos da plataforma.

**Resposta (resumo):** criação do documento do plano com contexto, produto (MVP x roadmap), mercado, concorrência, regulação, pendências e fontes.

---

## 5

**Prompt:**

> Bom, por enquanto o MVP ainda está em desenvolvimento, e acho que faz mais sentido estimarmos o custo por cima dele. Então vamos para esse plano operacional. Faça pesquisas do organograma geral de empresas que fazem produtos 100% digitais igual o nosso, faz sentido nos basesarmos nelas

**Resposta (resumo):** seção de plano operacional baseada no organograma SaaS de David Sacks, ajustado pelos dados da Carta sobre times menores, com área pedagógica e organograma em fases.

---

## 6

**Prompt:**

> To em dúvida do quanto vale detalhar esse plano operacional para um hackathon. Acho que o principal a priori é deixar claro que seriam 3 equipes principais no começo (pedagógico, produto e tecnologia, CS+comercial no mesmo time), e assessorias externas até pra parte jurídica eu acho

**Resposta (resumo):** plano operacional simplificado para três equipes e assessorias externas, com o organograma redesenhado.

---

## 7

**Prompt:**

> LGPD pode ser alguém de produto + founder. A equipe de founders tem 3 pessoas no momento, com perfil tech

**Resposta (resumo):** LGPD atribuída a Produto + fundador. Alerta de que Pedagógico e Comercial ficam sem responsável com três fundadores técnicos.

---

## 8

**Prompt:**

> Cara melhor a gente já começar a estimar os custos. Até pq o MVP não vai ser na melhor arquitetura do mundo. Estou pensando que a principio nós só precisaremos de dois compoentnes: um banco de dados (para armazenamento de notas, banco de equívocos, etc) e computação para poder servir o serviço em si. Assumindo AWS, o banco seria um RDS não tão grande e o compute poderia ser um ECS em fargate. Penso que o fargate resolveria pq o sistema dificilmente vai ser usado de noite e pq o processamento seria simples, já que o maior custo computacional é o do próprio LLM. Faz sentido? Não sei se vale explorar alocaçoes mais específicas da AWS (como compute agendado) por agora

**Resposta (resumo):** a arquitetura faz sentido, mas o Fargate não economiza sozinho à noite. Custos escondidos: load balancer (~US$ 25 a 33/mês) e NAT Gateway (~US$ 68/mês). Infra fixa de ~US$ 75 a 90/mês em São Paulo, com o LLM como custo dominante.

---

## 9

**Prompt:**

> Caralho, achei meio caro, mas vamos seguir pros modelos. Primeiro estima o quanto uma prova por um aluno pode gastar, e aí depois podemos estimar uma distribuição de cada gatilho por cada aluno para estimar o custo por uma turma (já que nem todos da turma fariam todas as chamadas pra LLM)

**Resposta (resumo):** custo por aluno por prova com Haiku 5.5, Sonnet 5.5 e Opus 5.5 (preços oficiais), com premissas de tokens. Sugestões de Batch API e cache de prompt.

---

## 10

**Prompt:**

> EU tinha até pensado na batch API, mas não vou mentir qu enão fui a fundo de como ela funciona. Eu precisaria passar a agendar serviços para puxarem o resultado? Acho que daria pra fazer isso sem ter que botar um serviço extra na conta e só agendando um cron no meu ecs, o que acha?

**Resposta (resumo):** funcionamento da Batch API (polling, até 24 h, resultados por 29 dias) e sugestão de um loop dentro da própria aplicação. Alerta de que batch na correção atrasa o follow-up.

---

## 11

**Prompt:**

> Beleza, antes de estimar precisamos ter uma noção da distribuição de acertos em questões de provas. Pesquisa se tem um dataset desse tipo aberto

**Resposta (resumo):** datasets abertos (PT ASAG 2018, ASAP-SAS, SciEntsBank, microdados do Enem) e o que cada um permite estimar. Nenhum cobre os cinco gatilhos.

---

## 12

**Prompt:**

> Cara acho que na prática para a estimativa ir a nível de gatilho não vai ser viável. O melhor seria ver tipo "x% das questões tem erro" e aí então na nossa estimativa de tamanho de prova a gnt vai saber que x% das questões por aluno vão precisar ter a chamada de LLM para a ocnversa de follow up

**Resposta (resumo):** modelo por taxa de erro. O limite de 3 questões por aluno domina o custo: acima de ~30% de erro, quase todo aluno bate o limite.

---

## 13

**Prompt:**

> Ajustes:
>
> * Diferencia bem que esse custo de infraestrutura é pensando no produto implementado final (mas com o set básico de features) e não no MVP do nosso hackhaton (esse tá saindo num firebase da vida)
> * Usa esses parametros:
>
> 10 questões por prova
> turmas de 30 alunos aproximadamente
>
> * Estima os custos tanto para haiku quanto para sonnet em batch.
> * Vai ser impossível medir a média real de turnos, assume 3 aqui.
> * Se vc não conseguir encontrar uma fonte legal da taxa de x% considerando meio certas, pode usar 50%.

**Resposta (resumo):** taxa de erro de 60% (SciEntsBank: 40,4% de respostas corretas). Batch só na correção e no sumário, porque o follow-up é ao vivo.

---

## 14

**Prompt:**

> Po na real dei uma repensada e percebi que eu estava indo pra direção errada. Batch não funciona bem se o aluno vai responder os followups e já ter a conversa continuada pelo LLM. Me ajuda a estimar, dado o nosso uso e o fluxo geral, como ficaria o custo usando uma arquitetura lambda functions + api gateway + s3 + cloudfront + rds. Já levando em conta essa nossa estimativa de uso.

**Resposta (resumo):** arquitetura serverless com infra fixa de ~US$ 35/mês. Pontos de atenção: NAT para a Lambda dentro da VPC, timeout de 30 s do API Gateway e conexões com o RDS. Tabela de custo por volume.

---

## 15

**Prompt:**

> Vamos tentar encontrar o custo anual. A turma vai ter 12 matérias e 4 ou 8 (dois cenários) provas ao ano. Nesse caso qual vai ser o custo por ano daquela turma?

**Resposta (resumo):** custo anual de LLM por turma em dois cenários (48 e 96 provas por ano).

---

## 16

**Prompt:**

> porra, maneiro, vc sente que faltou algo nessa estimativa de infra? Só para me ajduar a ver se não deixei nada passar

**Resposta (resumo):** itens faltantes por impacto: prova em papel, ambiente de testes, tributos e câmbio, Multi-AZ, uso de LLM em desenvolvimento, logs, picos na semana de provas e componentes pequenos (SQS, Cognito, Secrets Manager, Route 53, SES).

---

## 17

**Prompt** (primeira versão, depois reformulada no item 18):

> Ah, pior que tem total a feature de prova em papel. Calcula pra ela. Todos esses custos a gente joga uma margem de seguranç apra cima depois, a não ser que algum deles seja exorbitantemente mais caro

---

## 18

**Prompt:**

> Ah, pior que tem total a feature de prova em papel. O custo ia ser lastreado por prova, já que a conversa socrática não ia usar essa feature. sumariza quais os melhores modelos custo benefício pra isso, entendo que um OCR não é pra ser a coisa mais cara do mundo. Todos esses custos a gente joga uma margem de seguranç apra cima depois, a não ser que algum deles seja exorbitantemente mais caro

**Resposta (resumo):** comparação de opções de transcrição: Haiku 5.5 (~US$ 0,0006 a 0,0008 por página), Google Document AI/Azure Read (~US$ 0,0015), Mistral OCR 4.1 (~US$ 0,004) e Sonnet 5.5. O Amazon Textract não lê manuscrito em português.

---

## 19

**Prompt:**

> Olha aí a nossa implementação simples:
> https://github.com/lfzinho/asks-back
> Valida com os fluxos se nossa construção de custos tá factível. A arquitetura é toda diferente, então a análise é mais da quantidade de requests e chamadas de llm

**Resposta (resumo):** análise do código do worker. Os fluxos conferem, mas a correção usa Opus 5.5 com esforço alto, e o follow-up faz mais chamadas (escrita, checagem e julgamento no Haiku). A transcrição já está dentro da correção. Aviso: `claude_cost` usa sempre os preços do Opus.

---

## 20

**Prompt:**

> A gente não usaria o opus numa versão prática, me faz aquela mesma estimativa por ano de antes considerando os dois modelos, já que todo o resto tá validado

**Resposta (resumo):** custo anual recalculado com os fluxos do código: US$ 25 a 49 por turma com Haiku e US$ 344 a 689 com Sonnet.

---

## 21

**Prompt:**

> Poha tá maneiro. então me ajuda a pensar em, dado o custo de infra nosso, como calcular o custo fina lpra escola. Entendo que primeiro podemos jogar uns +30% nesse custo de infra pra considerrar a maioria daqueles seus pontos de manutenção na nuvem (me diz se achar que é muito mais). E aí também me ajuda a entender como o custo operacional pode entrar na conta. Entendo que o reflexo no custo final vai se basear no número de turmas clientes, então acredito que isso é um parametor que podemos explorar para entender até mesmo o nível da escala necessário

**Resposta (resumo):** modelo de precificação (custo por turma = C_var + (F_infra + F_op)/N; preço = custo/(1 − t − μ)), margens sugeridas (+30% nuvem, +25% tokens, tributos de até +50% sobre serviço importado) e exemplo por número de turmas.

---

## 22

**Prompt:**

> E ignorando o custo da empresa, como fica no final com nossos acrescimos? Só levando em conta o custo de infra

**Resposta (resumo):** custo só de tecnologia por aluno por ano, por número de turmas, com todos os acréscimos.

---

## 23

**Prompt:**

> Faz a estimativa do custo por turma

**Resposta (resumo):** a mesma tabela, por turma por ano.

---

## 24

**Prompt:**

> Anteriormente como vc tinha feito mesmo aquele cálculo da turma sem dividr o custo da infra fixa?

**Resposta (resumo):** passo a passo do cálculo anterior (LLM por prova de turma × provas por ano, sem margens e sem a nuvem fixa) e como o cálculo novo aplica os multiplicadores.

---

## 25

**Prompt:**

> Faz o custo sem considerar a infra fixa de novo mas com esses parametros de segurança novos. Quero em custo por turma por ano

**Resposta (resumo):** piso por turma por ano: Haiku US$ 49 a 98; Sonnet US$ 649 a 1.297.

---

## 26

**Prompt:**

> Converte em reais

**Resposta (resumo):** conversão a R$ 5,44 (fechamento de 30/10/2026): Haiku R$ 267 a 533; Sonnet R$ 3.531 a 7.056 por turma por ano.

---

## 27

**Prompt:**

> Agora dá pra mim a memória de cálculo bem resumida (por componente) pra eu consultar se necessário

**Resposta (resumo):** memória de cálculo em 9 passos (parâmetros, correção, follow-up, chamadas por prova, LLM por prova e por ano, Lambda/API, acréscimos, câmbio, nuvem fixa).

---

## 28

**Prompt:**

> Sim. No plano o ideal é a sessão de custos ter só o macro do custo de infra, e as memórias de cálculo ficarem em apendice

**Resposta (resumo):** seção de custos reduzida ao macro e criação do Apêndice A com a memória de cálculo e o detalhamento.

---

## 29

**Prompt:**

> Tira toda a parte com correção em sonnet, considera correção em haiku apenas

**Resposta (resumo):** todas as menções ao Sonnet removidas do plano; números apenas com correção em Haiku 5.5.

---

## 30

**Prompt:**

> Correções gerais no plano:
> tira aquilo lá de dizer que o argumento do mercado brasileiro é fraco. tira o que diz do mercado endereçavel por enquanto também.
> Me ajuda a com o que tem nele concluir, toda essa parte estratgéiga, marketing, etc, não cabem nesse contexto e no nosso tempo livre. Tira os to-dos do plano

**Resposta (resumo):** remoção do "ponto fraco", do mercado endereçável e das pendências; inclusão de uma conclusão.

---

## 31

**Prompt:**

> Tira esse risco de qualidade e amazon textract também. E aí me dá o arquivo PDF pronto pra eu por no meu repo

**Resposta (resumo):** remoção dos dois parágrafos, troca da fórmula em TeX por texto simples e exportação do plano em PDF (A4, 15 páginas).

---

## 32

**Prompt:**

> Agora me gera um arquivo json ou md com toda a nossa conversa desse chat, preciso por no repo os prompts que fiz para elaborar o plano

**Resposta (resumo):** este arquivo.

---

## 33

**Prompt:**

> Deixa como tava antes. E tira o RDS do plano, estamos pensando que não faz sentido mantermos um, dá problema com LGPD. Na prática não muda o custo né

**Resposta (resumo):** o RDS foi substituído por armazenamento pago por uso. O piso por turma não muda (US$ 49 a 98 por ano), mas a nuvem fixa cai de ~US$ 1.270 para ~US$ 120 por ano, porque sem banco ligado a Lambda dispensa VPC e NAT. Alerta: as obrigações da LGPD vêm de guardar dados de alunos, não do tipo de banco.
