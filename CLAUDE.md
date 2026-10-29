# Pitwall — contexto para o Claude Code

Dashboard local de tempo real para iRacing (estilo "Joel Real Timing"), do Caio (pt-BR; responda em português).
Roda no PC do sim e é exibido num **monitor secundário** (tela cheia no navegador, não é overlay sobre o jogo).
Painéis: Standings, Relative, Fuel, Mapa da pista, Weather. Prioridade: dados limpos/rápidos e interface bonita.

## Rodar
- Windows: `run.bat` (cria `.venv`, instala `requirements.txt`, abre http://localhost:8765). Usa `py -3` ou `python`.
- Manual: `python -m pitwall` (iRacing real) ou `python -m pitwall --mock` (simulador multiclasse para testar sem o sim).
- Opções: `--port 8765`, `--lan`, `--hz 20`, `--flip-map`, `--maps-dir`.
- Ao mexer só em `web/`, basta F5 (código é `no-store`; `/img/` e `/fonts/` são `no-cache`, revalidados a cada carga). Mudou `pitwall/*.py`? Reinicie o servidor.
- Ao subir o servidor para o usuário, deixe em background e confira o log; o iRacing precisa estar numa sessão.

## Arquitetura
Backend Python + aiohttp, WebSocket a 20 Hz; front em HTML/CSS/JS ES modules puro (sem build, sem framework).

- `pitwall/sources.py` — `IRacingSource` (pyirsdk: `freeze_var_buffer_latest`, lê `SCALARS` + `CAR_ARRAYS`, SessionInfo só quando `SessionInfoUpdate` muda) e `MockSource` (simulador: LMP2×5, GT3×14 incl. o jogador #64, GT4×7, box, amarela, chuva, corrida de 3600 s).
- `pitwall/engine.py` — `PassLog` (360 bins/volta por carro; gap = tempo desde que o carro da frente passou no bin onde o de trás está agora), `FuelTracker` (só voltas limpas, média das últimas 8), `Engine.update(raw)` monta o frame de estado.
- `pitwall/trackmap.py` — `TrackMapper`: grava o contorno por dead reckoning (Speed + YawNorth) numa volta limpa, fecha o erro de fechamento linearmente, reamostra em 480 pontos, cacheia em `maps/<TrackID>_<Config>.json`. `--flip-map` espelha.
- `pitwall/server.py` — `App`: `/ws`, loop no `hz`, envia só o que mudou; comando do cliente `{"cmd":"reset_map"}`.
- `web/js/main.js` — cliente WS com reconexão, store `S`, loop de render (standings/relative/mapa a cada frame, fuel/weather/header ~2 Hz), params `?w=standings,relative,map,fuel,weather`, `&bg=transparent` e `&zoom=1.2`. Escala da interface: padrão 1.1 (monitor fica longe), teclas `+`/`-` ajustam e salvam em `prefs.zoom`, `0` volta para 1.1; feita com `zoom` no `body` e `.app` com `100vh / --zoom`.
- `web/js/{standings,relative,fuel,map,weather,util}.js` — um módulo por painel: `mount(root,S)` e `update(S)`. `util.js` tem formatadores, `prefs` (localStorage) e `fmt` (unidades métrico/imperial).
- `web/app.css` — todo o design system, seguindo o design-kit do caiobatista.dev (`caBatista/landing-page`, pasta `design-kit/`): fundo ink `#111112`, cards ink-soft, texto off-white, **âmbar `#F4B400` é o único acento**; números grandes em Big Shoulders Black (`web/fonts/`), rótulos em Geist Mono caixa-alta, texto em Geist; barras de classe inclinadas 12°; logo CB em `web/img/`. Roxo/verde/vermelho/azul só como semântica de cronometragem.

## Mensagens WS (JSON)
- `hello {source}`; `drivers {drivers{idx→{i,name,team,num,cls,car,make,country,ir,lic,licColor}}, classes[{id,name,color,est,n}], meta{track,config,lengthKm,turns,incLimit}}`;
  `track {key,status,ver,points[[x,y]...]}`; `wx {hist[[t,air,track,wetness,precip]...]}` (5 s, 1 h);
  `state {t, session, me, cars[], rel[], fuel, wx, map}`; `state {connected:false}` quando não há sim.
- `cars[]`: `i,p,cp,lap,pct,last,best,pit,out,srf,cb,pb,gl,ld,gi,li,go,lo,gio,lio` (gl/ld = gap/voltas p/ líder da classe, gi/li = intervalo; go/lo/gio/lio = geral).
- `rel[]`: `i, dt (>=0 à frente, <0 atrás), dl (voltas de diferença), pit, out, srf` — os mais distantes primeiro, depois os de trás.

## Decisões de design (não desfazer sem pedir)
- Standings e Relative são duas visões separadas dos mesmos dados. Standings agrupa por classe (pos. de classe grande, geral pequena) com alternância "Overall"; classes ordenadas pelo tempo de volta estimado.
- Relative: ordem por posição na pista, 3 à frente e 3 atrás por padrão. Colunas: posição (na classe) | nº (Big Shoulders) + marca | bandeira | nome | SR+licença | iRating (caixinha) | melhor volta com 1 casa decimal (roxo = melhor da classe; a última vem −1 quando invalidada) | relativo. Nome sem o sufixo numérico do iRacing ("Laurent2" → "Laurent"); marca vem do `CarPath` (`car_make` no engine) e é desenhada com `web/img/makes/<marca>.png` se existir (logos de carlogos.org, fora do git; ver README da pasta), senão simple-icons via CDN. O navegador prepara cada PNG uma vez (`prepare` em util.js): fica só com a faixa mais pesada da arte (tira wordmark acima/abaixo), corta a margem e pinta de off-white logo quase todo preto. Visual estilo RaceLab: números e nomes do Relative em Montserrat SemiBold (`--num`); posição e nº em caixinhas de altura total com corte a 12°, faixa da cor da classe antes do nº e degradê da classe no fundo do nº, sumindo antes da marca (`.rcar`); linhas encostadas, sem espaço entre pilotos; bandeira vem do `FlairName` mapeado para ISO no navegador e desenhada com flag-icons via CDN.  **vermelho = uma volta à frente, azul = uma volta atrás (só em corrida; em treino/quali não há diferença de voltas)**; tags ao lado do nome: OUT própria e, depois dela, uma tag de status (`.st`) com a mais grave entre DQ > black > meatball > aviso (bits de `CarIdxSessionFlags`, campo `fl`) > PIT, com brilho âmbar em volta; OUT (out lap = de sair do pit road até cruzar a linha; `_out` no engine, campo `out` em `cars[]`/`rel[]`).
- Gaps usam tempo real de passagem (PassLog: horário de cruzamento de cada fronteira de bin, interpolado dentro do bin), não distância×tempo médio: correto entre classes e retardatários. O PassLog só vale com os dois carros andando na pista: se algum está no pit/fora da pista (`CarIdxTrackSurface != 3`), sem dados, ou o PassLog diverge da estimativa por mais de max(2 s, 30%), usa `CarIdxEstTime` reescalado pela classe (`timed_gap` no engine). No pit lane o `CarIdxEstTime` não é monotônico: se a estimativa discorda da ordem na pista (dá mais de meia volta com o carro logo à frente), usa distância × volta (`est_gap`). Sem isso, carro parado à frente mostrava "há quanto tempo passou" (−44 s em vez de 0,4 s).
- Posição: sempre `CarIdxPosition` do iRacing quando existe (qualquer tipo de sessão; conta quem já saiu da pista). `CarIdxBest/LastLapTime` zeram para quem sai do mundo, então completamos com `SessionInfo.Sessions[n].ResultsPositions` (`FastestTime`/`LastTime`). Fora de corrida, quem não tem tempo fica sem posição (`p`/`cp` = null, mostrado "–", no fim da lista).
- `SessionInfoUpdate` vem do cabeçalho do irsdk (`ir._header.session_info_update`), não é variável de telemetria.
- Fuel: consumo só de voltas limpas; meta automática (voltas/tempo da sessão) ou manual; reserva ajustável.
- Weather: o iRacing não dá previsão → mostramos tendência da última hora. WindDir assumido como "de onde vem".
- Mapa: yaw positivo = curva à esquerda; frame do iRacing X frente, Y esquerda.

## Estado e pendências
- Testado só com `--mock` e headless (erro médio do mapa 2,8 m no simulador). **A leitura real do iRacing ainda precisa de validação no PC do Caio**: mapa possivelmente espelhado (`--flip-map`), direção do vento, gaps/combustível em sessão real, `SessionInfo` de várias classes.
- O servidor MCP `iracing-telemetry` do Caio pode ser usado para inspecionar variáveis ao vivo.
- Caio vai pedir várias mudanças de interface; mantenha o estilo atual e confira com `--mock` + screenshot (Playwright) quando alterar o visual.
