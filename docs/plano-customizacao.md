# Customização do Pitwall: levantamento e plano

Rascunho para discutirmos, nada implementado. Levantado em 2026-11-05 em Racelab 8.6.1 e iOverlay 1.6.0.

Fontes: as telas dos dois apps, o `settings.dat` do iOverlay e os textos de interface do Racelab
(`resources/apiresources/translations`). O arquivo de preferências do Racelab é criptografado e não foi aberto.
Os textos mostram quais opções existem, não o comportamento de cada uma; o que não abri na tela é leitura dos rótulos.
A tela de Fuel do iOverlay só abre com o overlay ligado; as opções dele vieram do `settings.dat`.
Telas PRO do iOverlay não foram abertas.

## 1. Onde estamos

- O módulo de configurações não está na `main`. Está em `integracao/temas-personalizacao`
  (`web/js/config.js`, `web/js/settings.js`, `web/settings.css`), 17 commits à frente e 11 atrás da `main`.
  A branch ainda não conhece Race Events atual, gaps do iRacing nem nomes de classe.
- O que ele faz hoje: gaveta lateral, abre com `S`. Tema, logo, carros à frente/atrás, só minha classe, unidades,
  widgets ligados, colunas de Standings e Relative, itens do cabeçalho e do rodapé. Tudo em listas com setas.
- Limites dele:
  - Uma configuração só, para todas as sessões.
  - A disposição é uma regra fixa (`boardPlan`): o primeiro widget grande à esquerda, o resto empilhado à direita.
  - Coluna só liga e desliga, sem opção própria (casas decimais, formato do nome).
  - Fica em `localStorage`: não vale para outro aparelho na LAN e some se o perfil do WebView2 for limpo.
- Vale aproveitar: `config.js` é puro, tem versão, migração e `sanitize`, e a tabela de colunas é a base certa.

## 2. O que os apps oferecem

Legenda da coluna Pitwall: **tem** / **parcial** / **não**.

### Geral do app

| Opção | Racelab | iOverlay | Pitwall |
|---|---|---|---|
| Unidades | sim | sim | parcial (prefs, sem tela na main) |
| Fonte, peso | sim, por overlay | sim, global | não |
| Densidade (Cozy/Comfortable/Compact) | sim | não | não |
| Escala | sim | sim (`overlay size`) | tem (`+`/`-`) |
| Opacidade, fundo | sim | sim | não se aplica |
| Cores (padrão, piloto em destaque, fundo) | por overlay | global | não |
| FPS de renderização | por overlay | `lower fps` | parcial (`--render-hz`) |
| Aceleração de hardware | sim | sim | não se aplica |
| Iniciar minimizado, com o Windows | sim | parcial | não |
| Abrir em qual monitor | sim | não | parcial (`window.json`) |
| Abrir sozinho junto com o sim (auto-start) | sim, com ferramentas externas | não | não |
| Atalhos de teclado e botões do volante | sim, com botão por ação | só F6 | não |
| Idioma | 17 | não | não |
| Importar/exportar | por layout | sim | não |
| Resetar | tudo, posições, overlay individual | posições | só na gaveta |
| Busca nas opções | sim | não | não |
| Prévia com dados de demonstração | sim, ao lado das opções | sim, lista de prévias | não |

### Layouts e contexto

| Opção | Racelab | iOverlay | Pitwall |
|---|---|---|---|
| Vários layouts salvos | sim | perfil | não |
| Ativação automática por sessão, série, carro, categoria | sim, regras | não | fixo no código |
| Por tipo de sessão | sim | sim, cada coluna com race/quali/practice | fixo no código |
| Conforme o estado: no carro, fora do carro, spotting, garagem | sim | sim | fixo (`data-out`, `data-over`) |
| Layouts da comunidade | sim | não | fora de escopo |

### Standings e Relative

Colunas do **iOverlay** (ordenáveis, cada uma com race/quali/practice, várias com ajuste próprio): posição, classe,
posições ganhas, número, bandeira, equipe, marca, licença, iRating, intervalo, gap, black flag, última, delta de volta,
melhor, nome, status de pit, tempo no pit lane, relativo, tempo no box, stint atual, joker, pneu, driver tags,
média 5, média 10, push to pass.

A mais no **Racelab**: stint concluído, voltas por composto, off-tracks (contagem e destaque), TOW com tempo restante,
pneus, gear, distância física, gap e intervalo em distância, top speed, última top speed, energia virtual, nacionalidade em texto,
volta da parada, tempo da parada, notas do piloto.

Ajustes de linha e grupo:

| Opção | Racelab | iOverlay | Pitwall |
|---|---|---|---|
| Carros à frente/atrás | sim | sim | fixo em 3 (gaveta tem) |
| Líderes fixos no topo, por classe | sim | sim (PRO) | fixo |
| Mínimo de pilotos visíveis | sim | não | não |
| Esconder carros no pit | sim | só no box | não |
| Destaque do piloto de referência | cor, faixa | cor | fixo |
| Listrado | sim | não | não |
| Mostrar nomes das colunas | sim | sim | fixo |
| Cabeçalho de classe: voltas, nome, pilotos, SOF | sim | sim (PRO) | fixo |
| Casas decimais por coluna | sim | sim | fixo |
| Formato do nome | 13 formatos | sim | fixo |
| Largura do nome e da equipe | sim | sim | fixo |
| Quantos deltas de volta | sim | sim | fixo em 3 |
| iRating/licença: aparência e cor | sim | sim | fixo |
| Número na cor da classe, marca colorida | parcial | sim | fixo |
| Excluir do destaque: volta rápida, pit, punição, xadrez | sim | não | não |
| Rádio transmitindo | parcial | sim | fixo |
| Mapa linear anexo ao Relative | sim | não | não |

### Cabeçalho e rodapé

O iOverlay oferece a lista abaixo nos dois, ordenável e por tipo de sessão. Ela é o melhor catálogo dos dois apps:
pista, chuva, umidade da pista, nome da sessão, tipo de evento, hora local e do sim (24h e am/pm), ar, pista, umidade do ar,
neblina, tempo restante, voltas restantes, incidentes, volta atual, melhor da sessão, última, última calculada,
delta para melhor, ótima, melhor da sessão, ótima da sessão e última da sessão, brake bias, combustível, água, óleo, SOF,
stint em voltas e em tempo, RPM, deploy mode, ARB dianteira e traseira, ABS, TC1, TC2, weight jacker, rear brake valve,
pista declarada molhada, perda no pit, vento relativo ao piloto, **posição prevista depois do pit**, iRating e ganho, push to pass.

### Fuel

| Opção | Racelab | iOverlay | Pitwall |
|---|---|---|---|
| Estratégia de consumo: média total, 5, 10, última, maior, menor | sim, várias ao mesmo tempo | não | só média de 8 limpas |
| Margem de abastecimento em litros e em voltas | voltas | litros e voltas | reserva em voltas |
| Meta de consumo por volta para chegar ao fim | sim | sim | não |
| Tempo até esvaziar, com barra | sim | sim | não |
| Stint | sim | sim | não |
| Janela de combustível em barra e status | sim | não | parcial (texto) |
| Histórico de consumo | sim | não | não |
| Consumo guardado entre sessões | sim, com reset | não | não |
| Auto fuel | sim | não | tem |
| Fuel sharing entre companheiros | sim | sim | não |

### Mapa

| Opção | Racelab | iOverlay | Pitwall |
|---|---|---|---|
| Rótulo do carro: número ou posição | sim | sim | fixo em posição |
| Tamanho dos carros, do meu carro, largura da pista | sim | sim | proporcional |
| Cores da pista, de mim, dos amigos | sim | parcial | fixo |
| Curvas: número e nome | sim | sim | só número |
| Largada e setores | sim, com delta por setor | não | tem, sem delta |
| Marcador de líder da classe | sim, vários formatos | sim | não |
| **Indicador pós-pit no mapa** | sim | sim | não |
| Carro em incidente, off-track | sim | sim | não |
| Mostrar carros no pit, safety car | sim | parcial | não |
| Quem fala no rádio | sim | não | previsto |
| Indicador de vento | sim | não | não |
| 3D, zoom, formato circular | sim | não | não precisa |

### Weather e outros

Racelab: Weather é uma lista de componentes escolhidos e cantos retos. iOverlay não tem widget, usa cabeçalho e rodapé.
Driver tags nos dois: 16 etiquetas no Racelab, como rival, amigo, sujo, limpo, além de notas e nomes personalizados.

## 3. Widgets que não temos

Filtro: num monitor ao lado, o piloto olha de relance nas retas. Serve o que é **decisão** e muda em voltas.
Não serve o que é **reflexo** e muda em décimos, porque o olho está na pista. O CrewChief já cobre spotter por voz.

### Vale fazer

| # | Widget | Por que aqui | Inspiração | Dados |
|---|---|---|---|---|
| 1 | **Pit: onde eu volto** | Decide quando parar; num monitor grande cabe ver a posição, quem estará perto e o fantasma no mapa | post-pit, rejoin | temos gaps; `PIT_LOSS` fixo em 25 s precisa virar medido |
| 2 | **Gráfico de gaps** | Mostra a tendência que o número sozinho esconde: estou alcançando ou perdendo? | Trend Chart | temos, falta histórico por volta |
| 3 | **Briga** (eu × frente × trás) | Ritmo das últimas voltas, setores e "alcança em N voltas" | Head 2 Head, battle prediction | setores a calcular com o `PassLog` |
| 4 | **Faixa da pista** com tráfego | Multiclasse: onde encontro quem é mais rápido ou o retardatário | Flat Map, Traffic Indicator | temos, custo baixo |
| 5 | **Pit pelo Pitwall** | O que overlay não dá tão bem: botões grandes para combustível, pneus, reparo. Bom com touch ou tablet | nenhum | comandos existem em parte |
| 6 | **Voltas em corrida** | O laptime log existe só no teste; em corrida vira histórico do stint | Laptime Log, Graph | temos |
| 7 | **Carro** | BB, TC, ABS, ARB, temperaturas, energia dos GTP: número pequeno no painel, fácil aqui | Advanced Panel, Boost Box | variáveis novas |
| 8 | **Controle de prova** ao vivo | Race Events só aparece fora do carro; uma versão curta no carro | Race Control Info | temos |

### Não vale, ou fica para depois

| Widget | Motivo |
|---|---|
| Radar, Blind Spot, Radar Bars, Spotter, Overtake Alert | Reflexo; olhar para o lado é justamente o que não se quer |
| Delta Bar, Delta Trace | Reflexo; basta um número opcional no rodapé |
| Input Telemetry, Inputs Graph, G-Force | Não ajudam na hora. O Input que está na branch só faria sentido fora do carro |
| Flags grandes, Digiflag | A flag já "salta"; usar a borda da tela seria mais barato que um widget |
| Fuel Flow, Gear Economy, Burn Zones | Análise de nicho; pensar depois |
| Leaderboard, Race Schedule | Dependem de dados online, e a Data API foi descartada |
| Chat, Mic Visualizer, Garage Cover, Custom URL, Heart Rate, World Map | Coisa de stream ou enfeite |

## 4. Proposta

### Princípios

1. **Não copiar o Racelab.** Ele tem 48 overlays e centenas de opções porque vive em cima do jogo e precisa servir a todos.
   O Pitwall é uma tela inteira com padrões bons. Regra: cada opção precisa de um caso real.
2. **Padrão idêntico ao de hoje.** Quem não mexer vê exatamente o que está lá. As decisões de design do `CLAUDE.md` viram os padrões.
3. **Desempenho é requisito.** Coluna desligada não pode custar nada; nada de opção que force `innerHTML` a 20 Hz. `tools/bench_cpu.py` em cada fase.

### Forma: edição em cima do próprio quadro

Um botão (ou tecla) entra em **modo edição**: o quadro continua na tela, cada card ganha alça. Clicar num card abre as opções
dele num painel lateral, com a mudança aparecendo na hora, sem Aplicar. O próprio quadro é a prévia, e é o que o Pitwall tem
de vantagem: o Racelab precisa de uma imagem de demonstração ao lado porque o overlay real está em outra janela.

- Sem sim, ou para editar outro modo, entram **quadros de exemplo** gravados (corrida, quali, treino, fora do carro), estáticos, sem CPU.
- Uma tela **Geral** à parte guarda o que não pertence a um card: unidades, densidade, inicialização, atalhos, importar/exportar.
- Colunas: lista com arrastar e, em cada uma, marcas de sessão como no iOverlay (race/quali/practice) e o ajuste próprio.

### Modelo

```
configuração
├─ geral: unidades, densidade, atalhos...
└─ modos: corrida · quali · treino · teste · fora do carro · resultado
     └─ layout: grade de widgets
          └─ widget: opções e colunas
```

Os modos já existem no código como regras fixas. A proposta é mostrá-los e deixá-los editáveis, com os padrões de hoje.
O arquivo sai do `localStorage` para o disco (`%LOCALAPPDATA%\Pitwall\settings.json`): sobrevive a limpeza do WebView2,
exporta fácil e vale para tablet na LAN. Layout por série ou carro fica para depois.

### Disposição

Recomendo **grade com encaixe**: arrastar e redimensionar em colunas e linhas, sem posição livre em pixel. Nada de sobreposição,
sempre preenche a tela, e os painéis continuam podendo medir sua altura. Layouts prontos servem de ponto de partida.

### Primeiro corte de opções

- **Geral:** unidades, densidade, escala, monitor, abrir com o sim, atalhos, importar/exportar, reset por widget.
- **Standings/Relative:** colunas, carros à frente/atrás, líderes por classe, casas decimais, formato do nome, nº de deltas, esconder quem está no pit.
  Colunas novas: stint, média 5/10, off-tracks, tempo no box, TOW do meu carro.
- **Cabeçalho/rodapé:** catálogo do iOverlay, cortado para o que tem dado.
- **Fuel:** estratégia de consumo, margem em litros ou voltas, meta por volta, tempo até esvaziar, consumo guardado por carro e pista.
- **Mapa:** rótulo número ou posição, tamanhos, líder da classe, carros no pit.
- **Weather:** componentes.
- **Pilotos:** etiquetas, notas e nomes, valendo em Standings, Relative e mapa.

### Fases

| Fase | Entrega | Risco principal |
|---|---|---|
| 0 | Trazer `config.js` para a `main`; decidir temas e o Input da branch | Branch com 97 arquivos de diferença: portar, não mesclar |
| 1 | Arquivo em disco, migração de `prefs`, tela Geral | Perder preferências atuais |
| 2 | Colunas de Standings e Relative, por sessão, com opções | `visibleRows`, `ROW`/`ME`, `fitIr` dependem das alturas fixas |
| 3 | Modo edição, grade e modos | Painéis medem altura só no resize; race over e fora do carro têm regras próprias |
| 4 | Cabeçalho, rodapé, opções de Fuel, Mapa, Weather | Variáveis novas no `sources.py` |
| 5 | Etiquetas de pilotos | Identificar piloto pelo `UserID` e não pelo índice |
| 6 | Widgets novos, um por vez, na ordem que combinarmos | Cada um é quase um projeto |

Cada fase: testes, `--mock` com screenshot, bench de CPU, e nada de EXE novo com o sim aberto.

## 5. Decisões para conversarmos

1. **O que você imaginava?** Esta é a primeira: sem ela o resto é chute meu. O que ficou diferente na gaveta?
2. **Modo edição no quadro ou tela de configurações separada?** Recomendo no quadro.
3. **Grade com encaixe ou layouts prontos só?** Recomendo grade.
4. **Modos editáveis ou um layout só, com a sessão escondendo o que não cabe?** Recomendo editáveis.
5. **Temas:** a branch tem quatro. Ficam ou só o âmbar?
6. **Input telemetry da branch:** descarto?
7. **Widgets:** quais e em que ordem? Minha ordem é a da tabela.
8. **Tablet na LAN é caso real?** Muda o peso do widget de pit e do arquivo em disco.
