# Trade-offs e decisões de arquitetura

Decisões tomadas no MVP, o que se ganhou e o que se perdeu com cada uma.

## Por que duas APIs?

A **principal** cuida de tudo que tem efeito colateral: rede (Overpass), banco (SQLite) e histórico. A **secundária** é uma calculadora pura: recebe vias, devolve ilhas e propostas. Os algoritmos podem ser testados sem internet nem banco, e trocados ou escalados sem mexer no CRUD.
**Custo:** uma chamada de rede a mais em cada análise, e mais um serviço para subir.

## Por que a secundária não tem estado?

Sem banco e sem rede, ela é fácil de testar, de subir em várias cópias e continua funcionando mesmo se a Overpass cair. Ela nem sabe que a Overpass existe: só conhece o contrato de vias.
**Custo:** a principal precisa mandar todas as vias do bairro a cada análise (algumas centenas de KB de JSON).

## Por que REST (e não GraphQL)?

As duas APIs trocam um único formato (lista de vias → análise), sem consultas variadas do cliente, que é onde o GraphQL brilha. REST com JSON é o que a equipe domina, e o Swagger sai de graça com o FastAPI. O GraphQL foi considerado e descartado pelo prazo.

## Por que SQLite?

Um arquivo, zero configuração e um container a menos. O volume de dados é pequeno (áreas e propostas). Começou com PostgreSQL e foi trocado pelo prazo.
**Custo:** um único escritor por vez e nenhum acesso concorrente de várias instâncias da principal. Trocar para PostgreSQL exige só mudar a `DATABASE_URL` (o acesso é todo via SQLAlchemy).

## E se a Overpass cair ou ficar lenta?

A chamada tem **timeout de 30 s** (`OVERPASS_TIMEOUT`). Se der erro, timeout, 429 (limite de uso) ou uma resposta com erro no campo `remark`, a principal usa a resposta salva do bairro em `dados/overpass/` e grava `fonte_dados = "arquivo_local"`. Isso aconteceu de verdade durante o desenvolvimento: a Overpass devolveu 429 e a análise de Copacabana saiu do arquivo salvo.
**Custo:** os dados salvos envelhecem, e só existem para os 18 bairros da Zona Sul. Fora deles, sem Overpass, a resposta é **503**.

## Por que não há cache?

Foi cortado pelo prazo. Os arquivos salvos já funcionam como um cache estático para a demonstração. O próximo passo seria um cache em memória com validade (TTL) por bairro: os dados do OSM mudam pouco, e isso reduziria a carga na Overpass, que tem limite de uso.

## Por que BFS e Dijkstra, e qual o limite?

- **BFS** encontra as ilhas (componentes conexos) do grafo de ciclovias em O(V + E). No OpenStreetMap, uma ciclovia é dividida em muitas vias, e a ligação entre elas só aparece pelos nós compartilhados. Por isso é preciso a BFS, e não basta contar vias.
- **Dijkstra com várias origens** (todos os nós da malha principal começam com distância 0) acha o menor trecho entre a malha e cada ilha em O((V + E) log V). Com *k* ilhas, a análise custa O(k · (V + E) log V).
- **Limites conhecidos:**
  - cada ilha é ligada só à malha principal, e nunca a outra ilha;
  - `metros_construir` conta o caminho inteiro, mesmo que um trecho dele já seja ciclovia de outra ilha;
  - o ranking é guloso (proposta por proposta), e não o conjunto ótimo de obras. O ótimo global é o problema da árvore de Steiner, que é NP-difícil.

## O que fazer com o ruído do OpenStreetMap?

Os dados são usados como vêm, sem filtro:

- estradas de lazer (como as da Floresta da Tijuca) aparecem marcadas como ciclovia;
- vias `service` (acessos e estacionamentos) entram no grafo como ruas possíveis de uma ligação;
- vias que cruzam a divisa do bairro entram inteiras.

Filtrar exigiria regras por tag, e cada regra esconderia dados reais. A decisão foi deixar o ruído visível e documentado.

**Limite encontrado com os dados reais:** a consulta traz só ciclovias e ruas de carro. Em Ipanema, no Flamengo e na Glória, a malha principal (a orla e o Aterro) é uma ciclovia segregada que se liga às ruas **só por faixas de pedestre e calçadas** (`footway`, `path`). Sem essas vias no grafo, o Dijkstra não alcança a malha principal, e esses bairros ficam sem propostas. Incluir `footway`/`path` resolveria, mas também faria o sistema propor ligações por calçadas e aumentaria muito o grafo. Fica como próximo passo.

## Onde está o ponto único de falha?

A **API principal**, que orquestra tudo, e o arquivo SQLite, que fica dentro dela. Se a secundária cair, a principal responde **503** com uma mensagem clara e não grava nada pela metade. A queda da Overpass é coberta pelo fallback.

## O que quebra primeiro com 100x o volume?

1. **O limite de uso da Overpass**, que é pública. Já recebemos 429 baixando só 18 bairros em sequência. A resposta seria cache por bairro e, em escala, um servidor Overpass próprio ou um extrato do OSM.
2. **O `POST /areas` síncrono:** Overpass mais análise levam de 5 a 20 s, com um worker preso. A resposta seria uma fila de tarefas: o POST devolve 202 e a análise roda em segundo plano.
3. **O SQLite**, com um escritor por vez. A resposta seria o PostgreSQL.
4. **O tamanho do JSON de vias** entre as APIs, para áreas maiores que um bairro. A resposta seria compactar o JSON ou mandar o grafo já montado.

## Segurança

O nome do bairro entra na consulta da Overpass. Por isso ele é validado com uma expressão regular: só letras, espaços, hífen e apóstrofo. Sem essa validação, um usuário poderia fechar as aspas e injetar Overpass QL. Não há autenticação, que foi cortada pelo prazo.
