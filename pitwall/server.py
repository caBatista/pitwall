"""aiohttp app: serves the dashboard and streams the state over a WebSocket."""
from __future__ import annotations

import asyncio
import json
import math
import os
import sys
import time
from pathlib import Path

from aiohttp import WSMsgType, web

from . import simwindow
from .camera import HIDE, KEY_ACCEL, SCENIC, TEMPORARY, TOOL, WRITABLE
from .engine import Engine
from .events import note, purge

# inside the PyInstaller .exe the bundled files live under sys._MEIPASS
BUNDLE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
WEB_DIR = BUNDLE / "web"


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


def dumps_clean(obj) -> str:
    """dumps() for a state frame: _clean walks every value, only worth it if there is a NaN to remove."""
    try:
        return dumps(obj)
    except ValueError:
        return dumps(_clean(obj))


@web.middleware
async def no_cache(request, handler):
    resp = await handler(request)
    # code is never stored (F5 picks up edits). Images/fonts may be stored but are always
    # revalidated (cheap 304), so the relative doesn't re-download logos on every redraw and
    # a logo added to img/makes later still shows up on the next F5 (a 404 is revalidated too).
    static = request.path.startswith(("/img/", "/fonts/"))
    resp.headers["Cache-Control"] = "no-cache" if static else "no-store"
    return resp


WALK_STEP, WALK_FOR, WALK_TRIES = 0.4, 8.0, 10   # s between jumps; s and jumps to give up
LAP_IN = 0.4   # s after the line: the lap on screen is already the new one


class App:
    def __init__(self, source, engine: Engine, hz: float = 20.0, prefs_path: Path | None = None):
        self.source = source
        self.prefs_path = prefs_path   # the user's settings; the mock and the sim share them
        try:
            self.apply_prefs(json.loads(prefs_path.read_text("utf-8")))
        except (AttributeError, OSError, ValueError):
            pass
        self.engine = engine
        self.hz = hz
        self.clients: set[web.WebSocketResponse] = set()
        self._track_ver = -1
        self._drivers_ver = -1
        self._wx_sent = 0.0
        self._connected = False
        self.auto_fuel = None   # (reserve, laps) with Auto fuel on, from the fuel card
        self.dev = False        # run by Pitwall Dev.bat: the buttons to try things out
        self._walk, self._walk_car, self._walk_tries, self._walk_guesses = None, None, 0, 0   # the lap being gone to
        self._walk_t, self._walk_end = 0.0, 0.0
        self._cam_accel = False   # the tool's key acceleration, off while the sticks are in use
        # each race keeps its events for 30 days; the simulator's are not worth keeping
        self._ev_dir = engine.mapper.dir / "events"
        self._ev_save = source.name != "simulator"
        self._ev_saved, self._ev_save_t, self._ev_told = engine.ev.ver, 0.0, None
        if self._ev_save:
            engine.ev.dir = self._ev_dir
            purge(self._ev_dir)

    # ---- websocket ---------------------------------------------------------
    async def ws(self, request):
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        self.clients.add(ws)
        try:
            await ws.send_str(dumps({"type": "hello", "source": self.source.name, "dev": self.dev}))
            if self.engine.drivers:
                await ws.send_str(dumps(self.engine.drivers_msg()))
            await ws.send_str(dumps(_clean(self.engine.track_msg())))
            await ws.send_str(dumps(self.engine.wx_msg()))
            await ws.send_str(dumps({"type": "events", "all": self.engine.ev.items}))
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except ValueError:
                        continue
                    if data.get("cmd") == "reset_map":
                        self.engine.mapper.reset()
                    elif data.get("cmd") == "auto_fuel":
                        self.set_auto_fuel(data)
                    elif data.get("cmd") == "pit_tyre":
                        self.pit_tyre(data.get("tyre"))
                    elif data.get("cmd") == "replay":
                        self.replay(data.get("id"))
                    elif data.get("cmd") == "replay_live":
                        if not self.engine.in_car:
                            self.source.replay_live()
                    elif data.get("cmd") == "focus":
                        self.focus(data.get("i"))
                    elif data.get("cmd") == "mock_session":
                        if self.source.name == "simulator":
                            self.source.set_session(data.get("kind"))
                    elif data.get("cmd") == "cam":
                        self.camera(data)
                    elif data.get("cmd") == "chat":
                        await asyncio.to_thread(self.chat, data.get("i"), data.get("to"))
        finally:
            self.clients.discard(ws)
        return ws

    # ---- the user's settings: a file, because the app's browser storage dies with the window ----
    @staticmethod
    def apply_prefs(data):
        """The settings the server itself acts on."""
        full = data.get("simFull", True)
        simwindow.enabled, simwindow.only_car = full is not False, full == "car"

    async def prefs_get(self, _):
        try:
            return web.json_response(json.loads(self.prefs_path.read_text("utf-8")))
        except (AttributeError, OSError, ValueError):
            return web.json_response({})

    async def prefs_put(self, request):
        try:
            data = await request.json()
        except ValueError:
            data = None
        if not isinstance(data, dict):
            raise web.HTTPBadRequest()
        self.apply_prefs(data)
        if self.prefs_path:
            tmp = self.prefs_path.with_suffix(".tmp")
            self.prefs_path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
            os.replace(tmp, self.prefs_path)   # a crash halfway never leaves half a file
        return web.Response(status=204)

    # ---- pit commands from the fuel / weather cards -------------------------
    def set_auto_fuel(self, data):
        try:
            self.auto_fuel = (float(data.get("reserve")), float(data.get("laps"))) if data.get("on") else None
        except (TypeError, ValueError):
            self.auto_fuel = None

    def pit_fuel(self, liters):
        try:
            self.source.pit_fuel(max(0, min(math.ceil(float(liters)), math.ceil(self.engine.tank) or 1000)))
        except (TypeError, ValueError, OverflowError):
            pass

    def pit_tyre(self, kind):
        idx = self.engine.tyre_index(kind)
        if idx is not None:   # back to what is on the car: just undoes the choice, no new tyres
            self.source.pit_tyre(idx, kind != self.engine.tyre_on)

    # ---- driver rows: click = reference driver, right click = message ------
    def _driver(self, i):
        return self.engine.drivers.get(i) if isinstance(i, int) else None

    def focus(self, i):
        d = self._driver(i)
        if d and d["num"]:
            self.source.focus(i, d["num"])

    # ---- the camera widget. Never with the driver in the car: the view and the keys are the driving's -----
    def camera(self, data):
        if self.engine.in_car:
            return
        st = self.engine.cam_now
        group, cam, do, n = st.get("g") or 1, st.get("c") or 0, data.get("do"), data.get("n")
        if (st.get("st") or 0) & SCENIC and do in ("group", "camera", "stick"):
            return   # the same lock as iRacing's
        num = (self._driver(st.get("i")) or {}).get("num")
        if do == "group" and isinstance(n, int) and num:
            self.source.cam_switch(num, n, 0)
        elif do == "camera" and isinstance(n, int) and num:
            self.source.cam_switch(num, group, n)
        elif do == "driver":
            d = self._driver(n)
            if d and d["num"]:
                self.source.cam_switch(d["num"], group, cam)
        elif do == "speed" and isinstance(n, int) and -16 <= n <= 16:
            self.source.replay_speed(n, bool(data.get("slow")))
        elif do == "search" and isinstance(n, int) and 0 <= n <= 9:
            self.source.replay_jump(n)
        elif do == "lap" and isinstance(n, int) and n >= 1:
            t = self.engine.lap_start(st.get("i"), n)
            self._walk, self._walk_car, self._walk_tries, self._walk_guesses = n, st.get("i"), 0, 0
            self._walk_t, self._walk_end = 0.0, time.monotonic() + WALK_FOR
            if t is not None:   # known: straight there, and the walk only looks that it landed
                self.source.replay_at(self.engine.now_shown()[0], int((t + LAP_IN) * 1000))
                self._walk_t = time.monotonic() + WALK_STEP
        elif do == "tool":
            self.cam_tool(bool(data.get("on")), st.get("st") or 0)
        elif do == "stick":
            axes = data.get("axes") or {}
            state = st.get("st") or 0
            if axes and not state & TOOL:
                self.cam_tool(True, state)
            elif axes and state & KEY_ACCEL:
                self._cam_accel = True
                self.source.cam_state(state & WRITABLE & ~KEY_ACCEL)
            self.source.cam_move(axes)
        elif do == "reset":   # any state throws away what the keys moved: seen in the sim
            self.source.cam_state((st.get("st") or 0) & WRITABLE)
        elif do == "tap":
            state = st.get("st") or 0
            if n == "hide" and state & HIDE:   # opened hidden: only the state brings the panels back, and that undoes the edit
                self.source.cam_state(state & WRITABLE & ~HIDE)
            else:
                self.source.cam_tap(n)

    def walk(self):
        """To a lap whose start isn't known: a jump to about there, then iRacing's own lap jump, which lands just
        before the line from anywhere in the lap on either side. Then that start is known, for the next time."""
        e, i, goal, now = self.engine, self._walk_car, self._walk - 1, time.monotonic()
        if now < self._walk_t:
            return   # iRacing drops a jump sent right after another
        place, (session, t) = e.place(i), e.now_shown()
        self._walk_tries += 1
        self._walk_t = now + WALK_STEP
        off = None if place is None else place - goal
        speed = e.cam_now.get("speed") or 0
        if now > self._walk_end or self._walk_tries > WALK_TRIES or speed < 0:
            self._walk = None
        elif off is not None and (0 <= off < .03 * max(1, speed) or (goal == 0 and off < .15)):
            self._walk = None
        elif off is not None and -.03 < off < 0:   # just before the line: the lap on screen would still be the last one
            e.lap_seen(i, self._walk, t)
            if speed > 0:   # playing, it goes over the line by itself
                self._walk = None
            else:
                self.source.replay_at(session, int((t + LAP_IN) * 1000))
        elif goal == 0 and self._walk_guesses >= (1 if off is None else 3):   # before the green there is no line to land on
            self._walk = None
        elif off is None or goal == 0 or (abs(off) > 1.5 and self._walk_guesses < 2):
            self._walk_guesses += 1
            guess = e.lap_guess(i, self._walk)
            if guess is None:
                self._walk = None
            else:
                self.source.replay_at(session, int(guess * 1000))
        else:
            self.source.replay_jump(5 if off < 0 else 4)


    def cam_tool(self, on, state):
        """Always with temporary edits: closing the tool puts the camera back, nothing goes to the user's camera file."""
        bits = state & WRITABLE
        if on:
            self._cam_accel = self._cam_accel or bool(bits & KEY_ACCEL)
            self.source.cam_state((bits | TOOL | TEMPORARY | HIDE) & ~KEY_ACCEL)   # iRacing can't open it minimized: without its panels
        else:
            self.source.cam_state(bits & ~TOOL & ~TEMPORARY | (KEY_ACCEL if self._cam_accel else 0))
            self._cam_accel = False

    def replay(self, event_id):
        """Show an event in the replay. iRacing has no replay with the driver in the car."""
        hit = self.engine.ev.replay_target(event_id)
        if hit and not self.engine.in_car:
            session, ms, car = hit
            d = self._driver(car)
            self.source.replay(session, ms, d["num"] if d else None)

    def chat(self, i, to):
        d = self._driver(i)
        target = {"car": "num", "driver": "user", "team": "team"}.get(to)
        if d and target and d[target]:
            self.source.open_chat("/" + d[target].replace(" ", ".") + " ")   # Caio.Batista: how iRacing writes a name

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
        state = self.engine.update(raw)
        simwindow.in_car = self.engine.in_car
        if self._walk is not None:
            self.walk()
        if self.engine.pit_in and self.auto_fuel:
            liters = self.engine.fuel_needed(*self.auto_fuel)
            if liters is not None:   # no clean lap yet: the menu stays as it is
                self.pit_fuel(liters)
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
        ev = self.engine.ev
        if ev.cleared:
            ev.cleared = False
            ev.new = []
            out.append(dumps({"type": "events", "all": ev.items}))
        elif ev.new:
            out.append(dumps({"type": "events", "add": ev.drain()}))
        if self._ev_save and ev.items and ev.ver != self._ev_saved and time.time() - self._ev_save_t > 10:
            self._ev_saved, self._ev_save_t = ev.ver, time.time()
            try:
                path = ev.save(self._ev_dir, self.engine.event_info())
                if path != self._ev_told:
                    self._ev_told = path
                    note(self._ev_dir, f"saving {path.name}")
            except (OSError, TypeError, ValueError) as e:
                note(self._ev_dir, f"not saved: {e!r}")
        out.append(dumps_clean(state))
        for text in out:
            await self.broadcast(text)

    # ---- http --------------------------------------------------------------
    def build(self) -> web.Application:
        app = web.Application(middlewares=[no_cache])

        async def index(_):
            return web.FileResponse(WEB_DIR / "index.html")

        app.router.add_get("/", index)
        app.router.add_get("/ws", self.ws)
        app.router.add_get("/prefs", self.prefs_get)
        app.router.add_put("/prefs", self.prefs_put)

        app.router.add_static("/", WEB_DIR, show_index=False)

        async def start(app_):
            app_["loop_task"] = asyncio.create_task(self.run())

        async def stop(app_):
            app_["loop_task"].cancel()

        app.on_startup.append(start)
        app.on_cleanup.append(stop)
        return app
