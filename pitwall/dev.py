"""Working on Pitwall with the sim open: no build, nothing to close.

`Pitwall Dev.bat` opens the app from the code, on the same data as the installed one. The window stays and
the server is a separate process: saved a .py, the server starts again; saved anything else the board
shows, the page reloads. pitwall/desktop.py is the window itself, so that one needs reopening.

Restarting forgets what the server worked out during the session (fuel, laps): not for a race.
"""
from __future__ import annotations

import ctypes
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PITWALL, WEB = ROOT / "pitwall", ROOT / "web"
WEB_FILES = (".js", ".css", ".html", ".json", ".svg")
EVERY = 0.4    # s between looks at the files
SETTLE = 0.25  # s for a save that touches several files to finish
UP_IN = 15.0   # s for a server to start listening


def snapshot(folder, suffixes):
    """{file: when it changed}, everything under folder with these endings."""
    found = {}
    for path in Path(folder).rglob("*"):
        if path.suffix in suffixes and "__pycache__" not in path.parts:
            try:
                found[path] = path.stat().st_mtime_ns
            except OSError:   # an editor replacing the file
                pass
    return found


def listening(port, wait=None):
    end = time.monotonic() + (UP_IN if wait is None else wait)
    while time.monotonic() < end:
        with socket.socket() as s:
            s.settimeout(.2)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(.1)
    return False


def die_with(pid):
    """The server ends with the window, even if the window didn't get to say so."""
    SYNCHRONIZE, INFINITE = 0x100000, 0xFFFFFFFF
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    handle = kernel.OpenProcess(SYNCHRONIZE, False, pid)

    def wait():
        if handle:
            kernel.WaitForSingleObject(handle, INFINITE)
        os._exit(0)

    threading.Thread(target=wait, daemon=True).start()


class Dev:
    def __init__(self, cmd, port, log, folders=None):
        self.cmd, self.port, self.log = cmd, port, Path(log)
        self.code, self.web = folders or (PITWALL, WEB)
        self.proc, self._loads = None, 0
        self.pages = lambda: []   # the windows to reload: (window, url)
        self._stop = threading.Event()
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.log.write_text("", "utf-8")

    def say(self, text):
        with open(self.log, "a", encoding="utf-8") as fh:
            fh.write(f"[dev {time.strftime('%H:%M:%S')}] {text}\n")

    def start_server(self):
        self.stop_server()
        with open(self.log, "a", encoding="utf-8") as fh:
            self.proc = subprocess.Popen(self.cmd, cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT)
        self.say(f"server {self.proc.pid} starting")
        up = listening(self.port)
        self.say("server up" if up else "server didn't start: see above")
        return up

    def stop_server(self):
        if self.proc and self.proc.poll() is None:
            # the whole tree: a venv's python is a launcher with the real one under it, and that holds the port
            subprocess.run(["taskkill", "/f", "/t", "/pid", str(self.proc.pid)], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            self.proc.wait(5)
            gone = time.monotonic() + 3
            while time.monotonic() < gone and listening(self.port, .05):
                time.sleep(.05)
        self.proc = None

    def watch(self):
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._stop.set()
        self.stop_server()

    def _run(self):
        code, web = snapshot(self.code, (".py",)), snapshot(self.web, WEB_FILES)
        while not self._stop.wait(EVERY):
            now_code, now_web = snapshot(self.code, (".py",)), snapshot(self.web, WEB_FILES)
            if now_code == code and now_web == web:
                continue
            self._stop.wait(SETTLE)
            restart = snapshot(self.code, (".py",)) != code
            code, web = snapshot(self.code, (".py",)), snapshot(self.web, WEB_FILES)
            try:
                self.apply(restart)
            except Exception as exc:  # noqa: BLE001  - one bad reload doesn't end the watching
                self.say(f"failed: {exc!r}")

    def apply(self, restart):
        if restart:
            self.say("code changed")
            if not self.start_server():
                return   # a mistake in the code: the next save tries again
        self._loads += 1
        for window, url in self.pages():   # the same address again would be ignored by WebView2
            window.load_url(f"{url}{'&' if '?' in url else '?'}dev={self._loads}")
        self.say("page reloaded")
