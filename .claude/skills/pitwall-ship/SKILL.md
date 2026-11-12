---
name: pitwall-ship
description: Close a Pitwall change ("fecha as alterações", "pode commitar", "builda o exe", "fecha e abre de novo"): tests, commit, push, build, install and reopen in one command, never stealing focus from a driver in the car.
---

# Ship a Pitwall change

One command does it all, from the repo root:

```
powershell -NoProfile -ExecutionPolicy Bypass -File tools\ship.ps1 -Message "Titulo curto em pt-BR`n`nO que mudou, sem acentos"
```

- Caio's words decide the switches: only "commitar" → `-NoBuild -NoPush`; "commitar e gerar o exe" → `-NoPush`; "fechar as alterações" → no switch (commit, push, build, install, reopen). Push only when he asked for it or said "fechar".
- The script stops on failing tests: fix them, never skip.
- Driver in the car: it builds and does not install. Say so and offer to finish when he is out (`tools\ship.ps1 -NoPush -Message x` again: nothing new to commit, it just installs).
- It reopens through `explorer.exe`, so the app uses his real settings (see the `msix-appdata` memory). iRacing closed: installs, does not reopen.
- Branch is `develop`. Messages in Portuguese without accents (the shell mangles them), title under 70 characters.

After it runs, tell Caio the commit hash, the install time it printed and what was not tested in the sim.
