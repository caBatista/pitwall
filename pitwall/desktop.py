"""Pitwall as a desktop app: one window, no browser, no port to type.

    pythonw -m pitwall.desktop            (iRacing)
    pythonw -m pitwall.desktop --mock     (simulator)
    pythonw -m pitwall.desktop --windowed (not full screen)

The aiohttp server still runs, but inside this process, on 127.0.0.1 and a free port
picked at start, so it is invisible to the user. The window is a native WebView2
(Edge) window via pywebview showing the same front-end. Starts full screen (--windowed for a
window); F11 or the hidden top-right corner button toggles it.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import socket
import threading
from pathlib import Path

import webview
from aiohttp import web

from . import __version__
from .engine import Engine
from .server import App
from .sources import IRacingSource, MockSource
from .trackmap import TrackMapper

ROOT = Path(__file__).resolve().parent.parent
FROZEN = getattr(sys, "frozen", False)
BUNDLE = Path(getattr(sys, "_MEIPASS", ROOT))
# recorded maps and calibrations must be writable: next to the code when run from source,
# in the user's profile when installed as an .exe
DATA = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Pitwall" if FROZEN else ROOT


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(app: web.Application, port: int, ready: threading.Event):
    """Run the dashboard server on its own event loop (pywebview owns the main thread)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    runner = web.AppRunner(app)
    loop.run_until_complete(runner.setup())
    loop.run_until_complete(web.TCPSite(runner, "127.0.0.1", port).start())
    ready.set()
    loop.run_forever()


STATE = DATA / "window.json"   # which monitor, full screen or not


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def pick_screen(state: dict):
    """The monitor used last time; the first time, the secondary one (the dashboard screen)."""
    screens = list(webview.screens)
    saved = state.get("screen")
    for sc in screens:
        if saved and [sc.x, sc.y, sc.width, sc.height] == saved:
            return sc
    secondary = [sc for sc in screens if (sc.x, sc.y) != (0, 0)]
    return (secondary or screens or [None])[0]


def screen_at(x: int, y: int):
    for sc in webview.screens:
        if sc.x <= x < sc.x + sc.width and sc.y <= y < sc.y + sc.height:
            return sc
    return None


class Api:
    """Called from the page (window.pywebview.api). pywebview walks the public attributes of
    this object to expose them to JS: keep the window and state private (_...) or it walks
    the whole window object and the app hangs on start."""

    def __init__(self, state: dict):
        self._window = None
        self._state = state

    def fullscreen(self):
        self._window.toggle_fullscreen()
        self._state["fullscreen"] = not self._state.get("fullscreen", True)
        self._save()

    def _moved(self, x, y):
        sc = screen_at(x + 20, y + 20)   # a point inside the window, not its shadow edge
        if sc:
            self._state["screen"] = [sc.x, sc.y, sc.width, sc.height]

    def _save(self):
        try:
            STATE.parent.mkdir(parents=True, exist_ok=True)
            STATE.write_text(json.dumps(self._state))
        except OSError:
            pass


def main():
    p = argparse.ArgumentParser(prog="pitwall-desktop", description="Pitwall desktop app")
    p.add_argument("--mock", action="store_true", help="run on the simulator (no iRacing needed)")
    p.add_argument("--speed", type=float, default=4.0, help=argparse.SUPPRESS)
    p.add_argument("--windowed", action="store_true", help="start in a window (default: full screen)")
    args = p.parse_args()

    source = MockSource(speed=args.speed) if args.mock else IRacingSource()
    engine = Engine(TrackMapper(DATA / "maps", library_dir=BUNDLE / "maps" / "library"))
    port = free_port()
    ready = threading.Event()
    threading.Thread(target=serve, args=(App(source, engine).build(), port, ready), daemon=True).start()
    ready.wait(10)

    state = load_state()
    if args.windowed:
        state["fullscreen"] = False
    screen = pick_screen(state)
    if screen:
        state["screen"] = [screen.x, screen.y, screen.width, screen.height]
    api = Api(state)
    api._window = webview.create_window(
        f"Pitwall {__version__}", f"http://127.0.0.1:{port}/", js_api=api, screen=screen,
        width=1600, height=900, min_size=(960, 600), background_color="#111112",
        fullscreen=state.get("fullscreen", True), text_select=False,
    )
    api._window.events.moved += api._moved
    api._window.events.closing += api._save
    webview.start()   # returns when the window is closed; the server thread dies with the process


if __name__ == "__main__":
    main()
