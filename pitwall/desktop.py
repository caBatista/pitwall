"""Pitwall as a desktop app: one window, no browser, no port to type.

    pythonw -m pitwall.desktop            (iRacing)
    pythonw -m pitwall.desktop --mock     (simulator)
    pythonw -m pitwall.desktop --windowed (not full screen)
    pythonw -m pitwall.desktop --dev      (from the code, on the installed app's data: see dev.py)

The aiohttp server still runs, but inside this process, on 127.0.0.1 and a free port
picked at start, so it is invisible to the user. The window is a native WebView2
(Edge) window via pywebview showing the same front-end. Opens full screen unless Settings > General
says otherwise (F11 is the same switch); --windowed, to work on it, opens a window and saves nothing.
"""
from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import os
import time
import sys
import socket
import threading
from pathlib import Path

import webview
from aiohttp import web

from . import __version__
from .dev import Dev
from .engine import Engine
from .server import App
from .sources import IRacingSource, MockSource
from .trackmap import TrackMapper

ROOT = Path(__file__).resolve().parent.parent
FROZEN = getattr(sys, "frozen", False)
BUNDLE = Path(getattr(sys, "_MEIPASS", ROOT))
# recorded maps and calibrations must be writable: next to the code when run from source,
# in the user's profile when installed as an .exe
DEV = "--dev" in sys.argv   # from the code, but on the user's own settings, maps and events
DATA = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Pitwall" if FROZEN or DEV else ROOT


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


def square_edges(title: str, on: bool):
    """Windows 11 rounds the corners of a full-screen window and draws a 1 px border around it, with the
    wallpaper showing through. Off in full screen, back to the system's in a window."""
    CORNER, BORDER = 33, 34   # DWMWA_WINDOW_CORNER_PREFERENCE, DWMWA_BORDER_COLOR
    hwnd = ctypes.windll.user32.FindWindowW(None, title)
    corner = ctypes.c_int(1 if on else 0)   # DWMWCP_DONOTROUND / DEFAULT
    color = ctypes.c_uint(0xFFFFFFFE if on else 0xFFFFFFFF)   # DWMWA_COLOR_NONE / DEFAULT
    dwm = ctypes.windll.dwmapi.DwmSetWindowAttribute
    dwm(hwnd, CORNER, ctypes.byref(corner), ctypes.sizeof(corner))   # fails quietly before Windows 11
    dwm(hwnd, BORDER, ctypes.byref(color), ctypes.sizeof(color))


def ordered_screens():
    """The primary first, then left to right: the numbers on the Screen page."""
    return sorted(webview.screens, key=lambda s: ((s.x, s.y) != (0, 0), s.x))


class Api:
    """Called from the page (window.pywebview.api). pywebview walks the public attributes of
    this object to expose them to JS: keep the window and state private (_...) or it walks
    the whole window object and the app hangs on start."""

    def __init__(self, state: dict, url: str):
        self._window = None
        self._settings = None
        self._state = state
        self._url = url

    def fullscreen(self):
        self.set_fullscreen(not self._state["fullscreen"])

    def get_fullscreen(self):
        return self._state["fullscreen"]

    def set_fullscreen(self, on):
        if on != self._state["fullscreen"]:
            self._window.toggle_fullscreen()
            self._state["fullscreen"] = on
        self._edges()
        self._state["full"] = on
        self._save()

    def settings(self):
        """The settings pop-up: over the board, on its monitor, so a change can be seen as it is made."""
        if self._settings:
            return
        self._settings = webview.create_window(
            "Pitwall settings", self._url + "settings.html", js_api=self, screen=pick_screen(self._state),
            width=980, height=680, frameless=True, easy_drag=False, on_top=True, background_color="#111112", text_select=False,
        )
        self._settings.events.closed += self._settings_closed

    def screens(self):
        """The monitors, for the Screen page. on: the one Pitwall is on."""
        cur = self._state.get("screen")
        return [{"x": s.x, "y": s.y, "w": s.width, "h": s.height, "on": [s.x, s.y, s.width, s.height] == cur,
                 "primary": (s.x, s.y) == (0, 0)} for s in ordered_screens()]

    def set_screen(self, i):
        sc = ordered_screens()[i]
        full = self._state["fullscreen"]
        if full:   # full screen follows the monitor the window is on
            self._window.toggle_fullscreen()
        self._window.move(sc.x + 40, sc.y + 40)
        if full:
            self._window.toggle_fullscreen()
            self._edges()
        self._state["screen"] = [sc.x, sc.y, sc.width, sc.height]
        self._save()
        if self._settings:   # it stays over the board
            self._settings.move(sc.x + (sc.width - self._settings.width) // 2, sc.y + (sc.height - self._settings.height) // 2)
        return self.screens()

    def close_settings(self):
        if self._settings:
            self._settings.destroy()

    def _edges(self):
        square_edges(self._window.title, self._state["fullscreen"])

    def _settings_closed(self):
        self._settings = None

    def _moved(self, x, y):
        sc = screen_at(x + 20, y + 20)   # a point inside the window, not its shadow edge
        if sc:
            self._state["screen"] = [sc.x, sc.y, sc.width, sc.height]

    def _save(self):
        try:
            STATE.parent.mkdir(parents=True, exist_ok=True)
            STATE.write_text(json.dumps({"screen": self._state.get("screen"), "full": self._state.get("full", True)}))
        except OSError:
            pass


def server_cmd(args, port) -> list[str]:
    """The server of --dev: the same options, in a process of its own."""
    cmd = [sys.executable, "-u", "-m", "pitwall", "--port", str(port), "--data", str(DATA), "--dev-parent", str(os.getpid())]
    if args.mock:
        cmd += ["--mock", "--speed", str(args.speed), "--mock-start", str(args.mock_start)]
        cmd += ["--mock-cam", str(args.mock_cam)] if args.mock_cam else []
        cmd += ["--mock-wide"] * args.mock_wide + ["--mock-out"] * args.mock_out
    return cmd


LOG_MAX = 1_000_000   # bytes: started again past this


def log_to_file():
    """No console without one (pythonw, the EXE): errors of the server, the full-screen watcher... land in
    pitwall.log next to the settings, or nowhere."""
    if sys.stdout is not None and not FROZEN:
        return
    try:
        path = DATA / "pitwall.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > LOG_MAX:
            path.unlink()
        fh = open(path, "a", encoding="utf-8", buffering=1)   # noqa: SIM115 - open for the life of the app
        fh.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} started\n")
        sys.stdout = sys.stderr = fh
    except OSError:
        pass


def main():
    log_to_file()
    p = argparse.ArgumentParser(prog="pitwall-desktop", description="Pitwall desktop app")
    p.add_argument("--mock", action="store_true", help="run on the simulator (no iRacing needed)")
    p.add_argument("--speed", type=float, default=4.0, help=argparse.SUPPRESS)
    p.add_argument("--mock-start", type=float, default=0.0, help=argparse.SUPPRESS)
    p.add_argument("--mock-cam", default=None, help=argparse.SUPPRESS)
    p.add_argument("--mock-wide", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--mock-out", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--settings", action="store_true", help=argparse.SUPPRESS)   # opens with the pop-up, to work on it
    p.add_argument("--windowed", action="store_true", help="start in a window (default: full screen)")
    p.add_argument("--render-hz", type=float, help="redraw the panels at most this many times a second (default: every update)")
    p.add_argument("--dev", action="store_true", help="the server apart, restarted when the code changes (see dev.py)")
    args = p.parse_args()

    port, dev = free_port(), None
    if args.dev:
        dev = Dev(server_cmd(args, port), port, DATA / "dev.log")
        dev.start_server()
    else:
        cam = int(args.mock_cam) if (args.mock_cam or "").isdigit() else args.mock_cam
        source = MockSource(speed=args.speed, start=args.mock_start, cam=cam, wide=args.mock_wide, out=args.mock_out) if args.mock else IRacingSource()
        engine = Engine(TrackMapper(DATA / "maps", library_dir=BUNDLE / "maps" / "library"))
        up = threading.Event()
        threading.Thread(target=serve, args=(App(source, engine, prefs_path=DATA / "settings.json").build(), port, up), daemon=True).start()
        up.wait(10)

    state = load_state()
    state["fullscreen"] = state.get("full", True) and not args.windowed
    screen = pick_screen(state)
    if screen:
        state["screen"] = [screen.x, screen.y, screen.width, screen.height]
    url = f"http://127.0.0.1:{port}/"
    board = url + (f"?hz={args.render_hz:g}" if args.render_hz else "")
    api = Api(state, url)
    api._window = webview.create_window(
        f"Pitwall {__version__}", board, js_api=api, screen=screen,
        width=1600, height=900, min_size=(960, 600), background_color="#111112",
        fullscreen=state["fullscreen"], text_select=False,
    )
    api._window.events.moved += api._moved
    api._window.events.closing += api._save
    api._window.events.closed += api.close_settings   # a pop-up left open would keep the process alive
    # returns when the windows are closed; the server thread dies with the process
    def ready():
        api._edges()
        if args.settings:
            api.settings()
        if dev:
            dev.pages = lambda: [(api._window, board)] + ([(api._settings, url + "settings.html")] if api._settings else [])
            dev.watch()

    webview.start(ready)
    if dev:
        dev.stop()


if __name__ == "__main__":
    main()
