# Pitwall

Dashboard local de tempo real para iRacing: **Standings, Relative, Fuel, Mapa da pista e Weather**.
Lê a memória compartilhada do iRacing (pyirsdk) a 20 Hz e serve a interface em `http://localhost:8765`.

## Rodar (Windows)

1. Instale o Python 3.9+ (marque "Add to PATH").
2. Dê dois cliques em `run.bat` (cria o ambiente, instala e abre o navegador).
3. Abra o iRacing e entre em qualquer sessão — a tela conecta sozinha.

Sem iRacing aberto: `run.bat --mock` mostra um simulador multiclasse (LMP2 + GT3 + GT4) para ver o visual.

## Opções

| Opção | O que faz |
|---|---|
| `--mock` | usa o simulador em vez do iRacing |
| `--port 8765` | porta do servidor |
| `--lan` | libera acesso pela rede (tablet/celular: `http://IP-do-PC:8765`) |
| `--flip-map` | espelha o mapa, se vier invertido |
| `--hz 20` | taxa de atualização |

## Views separadas / overlay

`?w=` escolhe os painéis: `http://localhost:8765/?w=relative`, `?w=relative,fuel`, `?w=map`…
(`standings, relative, map, fuel, weather`). `&bg=transparent` deixa o fundo translúcido para
usar como overlay (OBS / janela sempre-no-topo).

## Como funciona

- **Gaps**: o tempo entre carros é medido pelo instante real em que o carro da frente passou pelo
  ponto da pista onde você está agora (360 pontos por volta) — correto entre classes e retardatários.
- **Standings**: agrupado por classe (posição de classe grande, geral pequena) ou geral; clique numa
  linha para destacar o carro no relative e no mapa.
- **Relative**: ordenado por posição na pista; vermelho = uma volta à frente (vai te dobrar),
  azul = uma volta atrás (você está dobrando). A barra colorida à esquerda é a classe.
- **Fuel**: consumo só de voltas limpas (sem box/bandeira); meta automática em provas por voltas/tempo,
  ou manual; reserva ajustável; mostra quanto abastecer e quantas paradas.
- **Mapa**: gravado na sua primeira volta limpa por dead reckoning e guardado em `maps/`.
  Use "Re-record" para refazer.
- **Weather**: o iRacing só informa o clima *atual* (sem previsão), então o painel mostra
  tendência da última hora: temperaturas, pista molhando/secando, chuva, vento relativo ao carro.

## Limitações conhecidas

- A leitura real do iRacing foi escrita contra a API do pyirsdk, mas testada só com o simulador.
  Se o mapa sair espelhado use `--flip-map`; se a seta do vento apontar ao contrário, avise.
