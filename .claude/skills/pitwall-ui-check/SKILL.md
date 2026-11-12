---
name: pitwall-ui-check
description: Check a visual or front-end change of Pitwall in the simulator before telling Caio it works: the board at 1920×1080, every session type, settings pages, flags, without the real sim.
---

# Checking the board in the mock

1. `preview_start` with `pitwall-mock` (port 8765) or `pitwall-mock-over` (8766, starts near the end of the race). Then `resize_window` 1920×1080: the real monitor.
2. Wait ~2.5 s, then use `javascript_tool`, cheaper than screenshots:
   - Sessions: click the buttons in `#mock-seg` (Test, Practice, Qualify, Race, Race over, In garage).
   - Settings without saving to disk: `const u = await import('/js/util.js'); u.prefs.x = ...; dispatchEvent(new Event('prefs'))`. Never call `savePrefs()`: it writes the project's settings.json.
   - Flags: click `.flag-test [data-flag="yellow"]` (only visible in dev and mock).
   - What the page sends: wrap `WebSocket.prototype.send` and collect the messages.
   - Overlap and alignment: compare `getBoundingClientRect()` of the parts. The shared bottom line is the Standings footer (`.me-bar`).
3. One screenshot at the end, `zoom` on the part that changed. The pane may be hidden: scripts over ~40 s time out, so split long waits (a mock lap takes ~85 s).
4. `preview_stop` when done. Say what was seen in the mock and what only the sim can show.
