"""aiohttp app: serves the dashboard and streams the state over a WebSocket."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from aiohttp import WSMsgType, web

from .engine import Engine

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def dumps(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), allow_nan=False, default=str)


def _clean(o):
    """NaN/inf are not valid JSON; replace them with None."""
    if isinstance(o, float):
        return o if o == o and o not in (float("inf"), float("-inf")) else None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


@web.middleware
async def no_cache(request, handler):
    resp = await handler(request)
    # code is never stored (F5 picks up edits). Images/fonts may be stored but are always
    # revalidated (cheap 304), so the relative doesn't re-download logos on every redraw and
    # a logo added to img/makes later still shows up on the next F5 (a 404 is revalidated too).
    static = request.path.startswith(("/img/", "/fonts/"))
    resp.headers["Cache-Control"] = "no-cache" if static else "no-store"
    return resp


class App:
    def __init__(self, source, engine: Engine, hz: float = 20.0):
        self.source = source
        self.engine = engine
        self.hz = hz
        self.clients: set[web.WebSocketResponse] = set()
        self._track_ver = -1
        self._drivers_ver = -1
        self._wx_sent = 0.0
        self._connected = False

    # ---- websocket ---------------------------------------------------------
    async def ws(self, request):
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        self.clients.add(ws)
        try:
            await ws.send_str(dumps({"type": "hello", "source": self.source.name}))
            if self.engine.drivers:
                await ws.send_str(dumps(self.engine.drivers_msg()))
            await ws.send_str(dumps(_clean(self.engine.track_msg())))
            await ws.send_str(dumps(self.engine.wx_msg()))
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except ValueError:
                        continue
                    if data.get("cmd") == "reset_map":
                        self.engine.mapper.reset()
        finally:
            self.clients.discard(ws)
        return ws

    async def broadcast(self, text: str):
        if not self.clients:
            return
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_str(text)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    # ---- main loop ---------------------------------------------------------
    async def run(self):
        period = 1.0 / self.hz
        nxt = time.perf_counter()
        while True:
            try:
                await self.tick()
            except Exception as exc:  # noqa: BLE001  - never let one bad frame kill the stream
                print(f"[pitwall] tick error: {exc!r}")
            nxt += period
            delay = nxt - time.perf_counter()
            if delay < -0.5:
                nxt = time.perf_counter()
            await asyncio.sleep(max(0.0, delay))

    async def tick(self):
        raw = self.source.poll()
        if raw is None:
            if self._connected:
                self._connected = False
                await self.broadcast(dumps({"type": "state", "connected": False}))
            elif self.clients and int(time.time()) % 2 == 0:
                await self.broadcast(dumps({"type": "state", "connected": False}))
            return
        self._connected = True
        info = self.source.session_info(raw)
        if info:
            self.engine.set_session(info)
        if not self.engine.drivers:
            return
        state = _clean(self.engine.update(raw))
        out = []
        if self.engine.drivers_ver != self._drivers_ver:
            self._drivers_ver = self.engine.drivers_ver
            out.append(dumps(self.engine.drivers_msg()))
        if self.engine.mapper.version != self._track_ver:
            self._track_ver = self.engine.mapper.version
            out.append(dumps(_clean(self.engine.track_msg())))
        if time.time() - self._wx_sent > 5:
            self._wx_sent = time.time()
            out.append(dumps(self.engine.wx_msg()))
        out.append(dumps(state))
        for text in out:
            await self.broadcast(text)

    # ---- http --------------------------------------------------------------
    def build(self) -> web.Application:
        app = web.Application(middlewares=[no_cache])

        async def index(_):
            return web.FileResponse(WEB_DIR / "index.html")

        app.router.add_get("/", index)
        app.router.add_get("/ws", self.ws)
        app.router.add_static("/", WEB_DIR, show_index=False)

        async def start(app_):
            app_["loop_task"] = asyncio.create_task(self.run())

        async def stop(app_):
            app_["loop_task"].cancel()

        app.on_startup.append(start)
        app.on_cleanup.append(stop)
        return app
