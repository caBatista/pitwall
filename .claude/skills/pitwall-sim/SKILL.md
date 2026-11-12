---
name: pitwall-sim
description: Before touching anything while iRacing may be open (opening dev mode, saving a .py that restarts it, reading his settings, sending keys or camera commands to test). Covers the in-car rule, dev mode, his real settings and safe ways to look at the screen.
---

# Working next to a running sim

1. **Look first, act in the next message.** `python tools/simstate.py` (exit 2 = in the car). In the car: no windows, no dev restarts (saving a `.py` restarts dev mode and zeroes laps and fuel), no screenshots that steal focus. Edits that do not reload anything are fine.
2. **Dev mode:** `powershell -NoProfile -ExecutionPolicy Bypass -File tools\dev.ps1`. It refuses in the car, closes the EXE and opens `Pitwall Dev.bat` through explorer.
3. **His settings:** `python tools/prefs.py [key ...]` reads the running app. Never trust `%LOCALAPPDATA%\Pitwall\settings.json` from this shell: the Claude desktop app redirects it to its own copy.
4. **Seeing his screens without stealing focus:** PIL `ImageGrab.grab(bbox=(3440,353,5360,1433), all_screens=True)` is the Pitwall monitor (KG 1920×1080); the LG 3440×1440 is at (0,0). Never computer-use with the sim open.
5. **Testing against the sim:** read telemetry in a fresh process after sending keys or camera commands; the same process returns stale values. Keys need ~50 ms between modifier, key and release (the sim reads once a frame).
6. **Bench:** never with iRacing running. `tools/bench_cpu.py` on a copy of the code in the scratchpad when the tree is being edited.
