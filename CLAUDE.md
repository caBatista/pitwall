# Pitwall — contexto para o Claude Code

Dashboard local de tempo real para iRacing, do Caio (pt-BR: responda em português). Roda no PC do sim e fica em tela cheia num **monitor secundário** (KG 1920×1080 em (3440,353); o sim fica no LG 3440×1440). Prioridade: dados limpos e rápidos, interface bonita, CPU baixa (cada % custa fps no sim).

**Detalhe de cada parte em `docs/referencia.md`**, por seção: leia só a do que for mexer (`grep -n "^## \|^- \*\*\|^- \`" docs/referencia.md` mostra o índice) e atualize-a quando o comportamento mudar.

## Processo
- Branch `develop`. Commit e push só quando o Caio pede ("fechar as alterações" = testes, commit, push, build, instalar, reabrir): skill `pitwall-ship` (`tools\ship.ps1`).
- iRacing aberto: skill `pitwall-sim` antes de agir. Primeiro `python tools/simstate.py` (sai 2 com ele no carro); só na mensagem seguinte abre/fecha janela ou salva `.py` (o dev reinicia). Nunca computer-use com o sim aberto.
- Dev no sim: `tools\dev.ps1` (fecha o EXE, abre `Pitwall Dev.bat` pelo Explorer). Configurações reais do app aberto: `python tools/prefs.py [chave]`. O `%LOCALAPPDATA%` visto daqui é uma cópia do Claude desktop: não confie nele, e abra EXE/dev sempre por `explorer.exe`.
- Mudança visual ou de front: skill `pitwall-ui-check` (mock a 1920×1080, sem gravar prefs).
- Testes: `.venv/Scripts/python.exe -m pytest -q` e `node --test tests/js/*.mjs`. Bench de CPU: `tools/bench_cpu.py`, nunca com o sim aberto.

## Rodar
- App: `Pitwall.bat` / `pythonw -m pitwall.desktop [--mock] [--dev]` (pywebview + WebView2, servidor aiohttp no mesmo processo em porta livre; `--dev` = servidor à parte que reinicia ao salvar). EXE: `build.bat` → `dist\Pitwall`; `installer\install.ps1` instala em `%LOCALAPPDATA%\Programs\Pitwall`. Dados do app instalado em `%LOCALAPPDATA%\Pitwall` (`settings.json`, `window.json`, `maps/`, `pitwall.log`).
- Só servidor: `python -m pitwall [--mock] [--mock-session race|qualify|practice|test] [--mock-start s] [--port 8765] [--lan]`. No mock o seletor do cabeçalho troca a sessão; botões de bandeira só em dev/mock.
- Mexeu só em `web/`: F5 (o dev recarrega sozinho). Mexeu em `pitwall/*.py`: reiniciar o servidor.

## Mapa do código
- `pitwall/sources.py` iRacing (pyirsdk) e mock · `engine.py` monta o quadro (`Engine.update`) · `events.py` Race Events · `trackmap.py` mapa · `server.py` WebSocket/HTTP e comandos · `camera.py`/`keymap.py` teclas e câmera · `chat.py`/`simwindow.py` janela do sim · `desktop.py`/`dev.py` app e modo dev.
- `web/js/main.js` cliente, store `S`, layout, header · um módulo por widget (`standings`, `relative`, `fuel`, `map`, `weather`, `events`, `camera`, `laplog`) com `mount(root,S)`/`update(S)` · `util.js` formatadores e `prefs` · `columns.js`/`layout.js` puros e testados · `web/app.css` todo o design.
- Mensagens WS e campos do quadro: seção "Mensagens WS" da referência.

## Regras que valem sempre
- Visual: design-kit do caiobatista.dev; fundo ink `#111112`, **âmbar `#F4B400` é o único acento**, números em Big Shoulders, rótulos em Geist Mono; roxo/verde/vermelho/azul só como semântica de cronometragem. Decisões de design da referência não se desfazem sem o Caio pedir.
- Desempenho: nada de `innerHTML` em linhas que mudam 20×/s (`patchRows`); nada de animação CSS infinita ou `requestAnimationFrame` livre; efeitos em JS a cada render; não remover o `body::before` de `app.css`. Detalhes e o que já foi testado sem ganho: seção "Desempenho".
- Piloto de referência = carro da câmera (`CamCarIdx`, `state.me`); rodapé e Fuel/pit/incidentes são do jogador (`state.user`). Testes em `tests/test_reference.py`.
- Teclas: o quadro não tem atalhos, toda tecla vai para o sim. Servidor só aceita páginas do próprio Pitwall (Origin).
- Comandos ao iRacing: pit só com o piloto no carro; câmera/replay só fora dele; teclas postadas precisam de ~50 ms entre modificador e tecla.
- `js_api` do pywebview sem atributos públicos pesados (a janela fica em `_window`), senão trava.
- Caio pede mudanças de interface aos poucos e reverte o que foi além do pedido: faça o pedido, confira no mock e diga o que só o sim mostra.
