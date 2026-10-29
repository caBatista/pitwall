# Pitwall — contexto para o Claude Code

Dashboard local de tempo real para iRacing (estilo "Joel Real Timing"), do Caio (pt-BR; responda em português).
Roda no PC do sim e é exibido num **monitor secundário** (tela cheia no navegador, não é overlay sobre o jogo).
Painéis: Standings, Relative, Fuel, Mapa da pista, Weather. Prioridade: dados limpos/rápidos e interface bonita.

## Rodar
- Windows: `run.bat` (cria `.venv`, instala `requirements.txt`, abre http://localhost:8765). Usa `py -3` ou `python`.
- Manual: `python -m pitwall` (iRacing real) ou `python -m pitwall --mock` (simulador multiclasse para testar sem o sim).
- Opções: `--port 8765`, `--lan`, `--hz 20`, `--flip-map`, `--maps-dir`.
- Ao mexer só em `web/`, basta F5 (o servidor não faz cache). Mudou `pitwall/*.py`? Reinicie o servidor.
- Ao subir o servidor para o usuário, deixe em background e confira o log; o iRacing precisa estar numa sessão.

## Arquitetura
Backend Python + aiohttp, WebSocket a 20 Hz; front em HTML/CSS/JS ES modules puro (sem build, sem framework).

- `pitwall/sources.py` — `IRacingSource` (pyirsdk: `freeze_var_buffer_latest`, lê `SCALARS` + `CAR_ARRAYS`, SessionInfo só quando `SessionInfoUpdate` muda) e `MockSource` (simulador: LMP2×5, GT3×14 incl. o jogador #64, GT4×7, box, amarela, chuva, corrida de 3600 s).
- `pitwall/engine.py` — `PassLog` (360 bins/volta por carro; gap = tempo desde que o carro da frente passou no bin onde o de trás está agora), `FuelTracker` (só voltas limpas, média das últimas 8), `Engine.update(raw)` monta o frame de estado.
- `pitwall/trackmap.py` — `TrackMapper`: grava o contorno por dead reckoning (Speed + YawNorth) numa volta limpa, fecha o erro de fechamento linearmente, reamostra em 480 pontos, cacheia em `maps/<TrackID>_<Config>.json`. `--flip-map` espelha.
- `pitwall/server.py` — `App`: `/ws`, loop no `hz`, envia só o que mudou; comando do cliente `{"cmd":"reset_map"}`.
- `web/js/main.js` — cliente WS com reconexão, store `S`, loop de render (standings/relative/mapa a cada frame, fuel/weather/header ~2 Hz), params `?w=standings,relative,map,fuel,weather` e `&bg=transparent`.
- `web/js/{standings,relative,fuel,map,weather,util}.js` — um módulo por painel: `mount(root,S)` e `update(S)`. `util.js` tem formatadores, `prefs` (localStorage) e `fmt` (unidades métrico/imperial).
- `web/app.css` — todo o design system (tema carbono escuro, acento menta `--accent`, roxo/verde/âmbar/vermelho/azul semânticos, números em JetBrains Mono, fonte Inter).

## Mensagens WS (JSON)
- `hello {source}`; `drivers {drivers{idx→{i,name,team,num,cls,car,ir,lic,licColor}}, classes[{id,name,color,est,n}], meta{track,config,lengthKm,turns,incLimit}}`;
  `track {key,status,ver,points[[x,y]...]}`; `wx {hist[[t,air,track,wetness,precip]...]}` (5 s, 1 h);
  `state {t, session, me, cars[], rel[], fuel, wx, map}`; `state {connected:false}` quando não há sim.
- `cars[]`: `i,p,cp,lap,pct,last,best,pit,srf,cb,pb,gl,ld,gi,li,go,lo,gio,lio` (gl/ld = gap/voltas p/ líder da classe, gi/li = intervalo; go/lo/gio/lio = geral).
- `rel[]`: `i, dt (>=0 à frente, <0 atrás), dl (voltas de diferença), pit, srf` — os mais distantes primeiro, depois os de trás.

## Decisões de design (não desfazer sem pedir)
- Standings e Relative são duas visões separadas dos mesmos dados. Standings agrupa por classe (pos. de classe grande, geral pequena) com alternância "Overall"; classes ordenadas pelo tempo de volta estimado.
- Relative: ordem por posição na pista, barra colorida à esquerda = classe; **vermelho = uma volta à frente, azul = uma volta atrás**; tag PIT; seta de aproximação.
- Gaps usam tempo real de passagem (PassLog), não distância×tempo médio: correto entre classes e retardatários.
- Fuel: consumo só de voltas limpas; meta automática (voltas/tempo da sessão) ou manual; reserva ajustável.
- Weather: o iRacing não dá previsão → mostramos tendência da última hora. WindDir assumido como "de onde vem".
- Mapa: yaw positivo = curva à esquerda; frame do iRacing X frente, Y esquerda.

## Estado e pendências
- Testado só com `--mock` e headless (erro médio do mapa 2,8 m no simulador). **A leitura real do iRacing ainda precisa de validação no PC do Caio**: mapa possivelmente espelhado (`--flip-map`), direção do vento, gaps/combustível em sessão real, `SessionInfo` de várias classes.
- O servidor MCP `iracing-telemetry` do Caio pode ser usado para inspecionar variáveis ao vivo.
- Caio vai pedir várias mudanças de interface; mantenha o estilo atual e confira com `--mock` + screenshot (Playwright) quando alterar o visual.
