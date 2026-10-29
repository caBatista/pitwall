"""Turns raw iRacing variables into the state the dashboard draws.

The interesting part is how gaps are measured. Instead of estimating from lap
distance and a nominal lap time (which is wrong across classes), every car's
passing time through ~360 slices of the track is logged. The gap between two
cars is then the real time between them crossing the same point, the way a
timing loop does it.
"""
from __future__ import annotations

import math
import re
from collections import deque

from .trackmap import TrackMapper

BINS = 360
SESSION_STATE = {0: "Invalid", 1: "Get in car", 2: "Warm-up", 3: "Parade laps", 4: "Racing", 5: "Checkered", 6: "Cool down"}
UNLIMITED_TIME = 86400.0
UNLIMITED_LAPS = 32000
WETNESS = ["Unknown", "Dry", "Mostly dry", "Very lightly wet", "Lightly wet", "Moderately wet", "Very wet", "Extremely wet"]


def hexcolor(v, default="#8b95a7"):
    try:
        if isinstance(v, str):
            v = int(v, 16) if v.lower().startswith("0x") else int(v)
        if v is None or v < 0:
            return default
        return "#%06x" % (int(v) & 0xFFFFFF)
    except (TypeError, ValueError):
        return default


def parse_km(text):
    m = re.search(r"([\d.]+)\s*(km|mi)", str(text or ""), re.I)
    if not m:
        return None
    v = float(m.group(1))
    return v * 1.609344 if m.group(2).lower() == "mi" else v


def flag_name(bits: int) -> str:
    bits = int(bits or 0)
    if bits & 0x1:
        return "checkered"
    if bits & 0x10:
        return "red"
    if bits & 0x20000 or bits & 0x10000:
        return "black"
    if bits & (0x4000 | 0x8000 | 0x8 | 0x100):
        return "yellow"
    if bits & 0x2:
        return "white"
    if bits & 0x20:
        return "blue"
    if bits & (0x4 | 0x400):
        return "green"
    return "none"


class PassLog:
    """Last time each car passed each slice of the track."""

    def __init__(self):
        self.tab = {}
        self.last = {}

    def feed(self, idx, pct, t):
        b = int(pct * BINS) % BINS
        tab = self.tab.setdefault(idx, [None] * BINS)
        prev = self.last.get(idx)
        if prev is None or t < prev[1] or t - prev[1] > 3.0:
            tab[b] = t
            self.last[idx] = (b, t)
            return
        pb, pt = prev
        n = (b - pb) % BINS
        if n == 0:
            return
        if n <= 40:
            for k in range(1, n + 1):
                tab[(pb + k) % BINS] = pt + (t - pt) * k / n
        else:  # jump (reset, tow, rewind): don't invent data
            tab[b] = t
        self.last[idx] = (b, t)

    def since(self, idx, pct, now):
        tab = self.tab.get(idx)
        if not tab:
            return None
        v = tab[int(pct * BINS) % BINS]
        return None if v is None else now - v


class FuelTracker:
    KEEP = 10

    def __init__(self):
        self.reset()

    def reset(self):
        self.hist = deque(maxlen=self.KEEP)   # litres per clean lap
        self.times = deque(maxlen=self.KEEP)  # lap times of those laps
        self._lap = None
        self._start = None
        self._valid = False
        self._prev_fuel = None

    def update(self, lapc, fuel, lap_time, on_pit, flag, on_track):
        if fuel is None or fuel < 0:
            return
        if self._prev_fuel is not None and fuel > self._prev_fuel + 0.05:
            self._valid = False  # refuelled
        self._prev_fuel = fuel
        if on_pit or flag == "yellow" or not on_track:
            self._valid = False
        if lapc is None or lapc < 0:
            return
        if self._lap is None:
            self._lap, self._start, self._valid = lapc, fuel, False
            return
        if lapc != self._lap:
            if lapc == self._lap + 1 and self._valid and self._start is not None:
                used = self._start - fuel
                if 0.05 < used < 40:
                    self.hist.append(used)
                    if lap_time and lap_time > 0:
                        self.times.append(lap_time)
            self._lap, self._start = lapc, fuel
            self._valid = not on_pit and flag != "yellow"

    @property
    def avg(self):
        recent = list(self.hist)[-8:]
        return sum(recent) / len(recent) if recent else None

    @property
    def avg_time(self):
        recent = list(self.times)[-5:]
        return sum(recent) / len(recent) if recent else None


class Engine:
    def __init__(self, mapper: TrackMapper):
        self.mapper = mapper
        self.drivers = {}
        self.classes = {}
        self.sessions = {}
        self.meta = {}
        self.player = 0
        self.tank = 0.0
        self.drivers_ver = 0
        self.log = PassLog()
        self.fuel = FuelTracker()
        self.wx_hist = deque(maxlen=720)  # 5 s samples = 1 hour
        self._wx_t = -1e9
        self._prev_t = None
        self._session_key = None

    # ---- session info ------------------------------------------------------
    def set_session(self, info):
        wk = (info.get("WeekendInfo") or {})
        di = (info.get("DriverInfo") or {})
        si = (info.get("SessionInfo") or {})
        track_id = wk.get("TrackID")
        cfg = wk.get("TrackConfigName") or ""
        key = f"{track_id}_{cfg}"
        length_km = parse_km(wk.get("TrackLength"))
        self.meta = {
            "track": wk.get("TrackDisplayName") or wk.get("TrackName") or "Unknown track",
            "config": cfg,
            "trackId": track_id,
            "lengthKm": length_km,
            "turns": wk.get("TrackNumTurns"),
            "incLimit": (wk.get("WeekendOptions") or {}).get("IncidentLimit"),
            "category": wk.get("Category"),
        }
        self.sessions = {s.get("SessionNum"): s for s in (si.get("Sessions") or [])}
        self.player = int(di.get("DriverCarIdx") or 0)
        mx = float(di.get("DriverCarFuelMaxLtr") or 0) * float(di.get("DriverCarMaxFuelPct") or 1)
        self.tank = mx
        est_default = float(di.get("DriverCarEstLapTime") or 100.0)
        self.drivers, classes = {}, {}
        for d in di.get("Drivers") or []:
            if d.get("IsSpectator") or d.get("CarIsPaceCar") or d.get("CarIdx") is None:
                continue
            idx = int(d["CarIdx"])
            cid = int(d.get("CarClassID") or 0)
            car = d.get("CarScreenNameShort") or d.get("CarScreenName") or ""
            cname = d.get("CarClassShortName") or car or f"Class {cid}"
            col = hexcolor(d.get("CarClassColor"))
            est = float(d.get("CarClassEstLapTime") or est_default)
            classes.setdefault(cid, {"id": cid, "name": cname, "color": col, "est": est, "n": 0})
            classes[cid]["n"] += 1
            self.drivers[idx] = {
                "i": idx, "name": d.get("UserName") or f"Car {idx}", "team": d.get("TeamName") or "",
                "num": str(d.get("CarNumber") or ""), "cls": cid, "car": car,
                "ir": d.get("IRating") or 0, "lic": d.get("LicString") or "",
                "licColor": hexcolor(d.get("LicColor"), "#8b95a7"), "ai": bool(d.get("CarIsAI")),
            }
        ordered = sorted(classes.values(), key=lambda c: c["est"])
        self.classes = {c["id"]: c for c in ordered}
        self.class_order = [c["id"] for c in ordered]
        if len(self.classes) == 1:  # single class: iRacing reports white, use a nicer accent
            only = next(iter(self.classes.values()))
            if only["color"].lower() in ("#ffffff", "#8b95a7"):
                only["color"] = "#7cf0c9"
        if key != self._session_key:
            self._session_key = key
            self.mapper.set_track(key)
            self.fuel.reset()
            self.log = PassLog()
            self.wx_hist.clear()
        self.drivers_ver += 1

    def drivers_msg(self):
        return {
            "type": "drivers", "ver": self.drivers_ver, "meta": self.meta,
            "drivers": self.drivers,
            "classes": [self.classes[c] for c in self.class_order],
        }

    def track_msg(self):
        return {"type": "track", "key": self.mapper.key, "status": self.mapper.status,
                "ver": self.mapper.version, "points": self.mapper.points}

    def wx_msg(self):
        return {"type": "wx", "hist": list(self.wx_hist)}

    # ---- per-tick state ----------------------------------------------------
    def update(self, raw):
        t = float(raw.get("SessionTime") or 0.0)
        dt = 0.0 if self._prev_t is None else t - self._prev_t
        self._prev_t = t
        if dt < 0 or dt > 5:
            dt = 0.0

        def arr(key, default):
            v = raw.get(key)
            return v if isinstance(v, (list, tuple)) and v else default

        blank = [0] * 64
        lapc = arr("CarIdxLapCompleted", blank)
        pct = arr("CarIdxLapDistPct", [-1.0] * 64)
        surf = arr("CarIdxTrackSurface", [-1] * 64)
        pitr = arr("CarIdxOnPitRoad", blank)
        pos = arr("CarIdxPosition", blank)
        last = arr("CarIdxLastLapTime", [-1.0] * 64)
        best = arr("CarIdxBestLapTime", [-1.0] * 64)

        snum = raw.get("SessionNum")
        sess = self.sessions.get(snum) or {}
        stype = (sess.get("SessionType") or "").strip()
        is_race = stype.lower() == "race"
        flag = flag_name(raw.get("SessionFlags"))
        me = int(raw.get("PlayerCarIdx") if raw.get("PlayerCarIdx") is not None else self.player)

        present = []
        for idx in self.drivers:
            if idx >= len(surf):
                continue
            if surf[idx] >= 0 or pos[idx] > 0 or best[idx] > 0:
                present.append(idx)
            if surf[idx] >= 0 and 0 <= pct[idx] <= 1.0:
                self.log.feed(idx, pct[idx], t)

        tot = {i: (lapc[i] if lapc[i] is not None and lapc[i] > -2 else 0) + max(0.0, pct[i]) for i in present}

        # ordering
        if is_race and any(pos[i] > 0 for i in present):
            order = sorted(present, key=lambda i: (pos[i] if pos[i] > 0 else 999 + i))
        elif is_race:
            order = sorted(present, key=lambda i: (-tot[i], i))
        else:
            order = sorted(present, key=lambda i: (best[i] if best[i] > 0 else 1e9, i))
        overall = {i: k + 1 for k, i in enumerate(order)}
        groups = {}
        for i in order:
            groups.setdefault(self.drivers[i]["cls"], []).append(i)
        cpos = {i: k + 1 for g in groups.values() for k, i in enumerate(g)}
        class_best = {}
        for cid, g in groups.items():
            bs = [best[i] for i in g if best[i] > 0]
            class_best[cid] = min(bs) if bs else None

        my_cls = self.drivers.get(me, {}).get("cls")
        ref = (class_best.get(my_cls) or best[me] if me < len(best) else 0) or 0
        if not ref or ref <= 0:
            ref = (self.classes.get(my_cls) or {}).get("est") or 100.0

        def gap(i, j):
            """(laps_down, seconds) of car i relative to car j that is ahead of it."""
            diff = tot[j] - tot[i]
            laps = int(math.floor(diff + 1e-6))
            if laps >= 1:
                return laps, None
            if diff <= 0:
                return 0, 0.0
            s = self.log.since(j, pct[i], t)
            if s is None or s < 0 or s > ref * 1.2:
                s = diff * ref
            return 0, round(s, 3)

        cars = []
        for k, i in enumerate(order):
            cid = self.drivers[i]["cls"]
            g = groups[cid]
            ci = g.index(i)
            c = {
                "i": i, "p": overall[i], "cp": cpos[i], "lap": lapc[i], "pct": round(pct[i], 5),
                "last": round(last[i], 3) if last[i] > 0 else None,
                "best": round(best[i], 3) if best[i] > 0 else None,
                "pit": bool(pitr[i]), "srf": surf[i],
                "cb": bool(best[i] > 0 and class_best.get(cid) == best[i]),
                "pb": bool(best[i] > 0 and last[i] > 0 and abs(last[i] - best[i]) < 1e-4),
            }
            if is_race:
                if ci == 0:
                    c["gl"], c["ld"], c["gi"], c["li"] = None, 0, None, 0
                else:
                    c["ld"], c["gl"] = gap(i, g[0])
                    c["li"], c["gi"] = gap(i, g[ci - 1])
                if k == 0:
                    c["go"], c["lo"], c["gio"], c["lio"] = None, 0, None, 0
                else:
                    c["lo"], c["go"] = gap(i, order[0])
                    c["lio"], c["gio"] = gap(i, order[k - 1])
            else:
                def delta(a, b):
                    return round(best[a] - best[b], 3) if best[a] > 0 and best[b] > 0 else None
                c["ld"] = c["li"] = c["lo"] = c["lio"] = 0
                c["gl"] = delta(i, g[0]) if ci else None
                c["gi"] = delta(i, g[ci - 1]) if ci else None
                c["go"] = delta(i, order[0]) if k else None
                c["gio"] = delta(i, order[k - 1]) if k else None
            cars.append(c)

        # relative: everyone physically near me, by real elapsed time
        rel = []
        if me in tot and surf[me] >= 0 and pct[me] >= 0:
            for i in present:
                if i == me or surf[i] < 0 or pct[i] < 0:
                    continue
                dp = pct[i] - pct[me]
                dp = (dp + 0.5) % 1.0 - 0.5
                if dp >= 0:   # ahead on track: how long ago did it pass where I am now
                    s = self.log.since(i, pct[me], t)
                    sec = s if s is not None and 0 <= s <= ref else dp * ref
                    dtm = sec
                else:         # behind: how long ago was I where it is now
                    s = self.log.since(me, pct[i], t)
                    sec = s if s is not None and 0 <= s <= ref else -dp * ref
                    dtm = -sec
                laps = int(round(tot[i] - tot[me] - dp))
                rel.append({"i": i, "dt": round(dtm, 2), "dl": laps, "pit": bool(pitr[i]), "srf": surf[i]})
            ahead = sorted([r for r in rel if r["dt"] >= 0], key=lambda r: r["dt"])[:8]
            behind = sorted([r for r in rel if r["dt"] < 0], key=lambda r: -r["dt"])[:8]
            rel = list(reversed(ahead)) + behind
        else:
            rel = []

        # fuel
        fuel_l = raw.get("FuelLevel")
        lap_t = self.fuel.avg_time or (best[me] if best[me] > 0 else None) or ref
        self.fuel.update(lapc[me], fuel_l, raw.get("LapLastLapTime"), bool(raw.get("OnPitRoad")), flag,
                         bool(raw.get("IsOnTrack")))
        avg = self.fuel.avg
        provisional = False
        if avg is None and (raw.get("FuelUsePerHour") or 0) > 1 and lap_t:
            avg, provisional = raw["FuelUsePerHour"] * lap_t / 3600.0, True
        laps_total = raw.get("SessionLapsTotal") or 0
        laps_rem = raw.get("SessionLapsRemainEx") or 0
        time_total = raw.get("SessionTimeTotal") or 0
        time_rem = raw.get("SessionTimeRemain") or 0
        mypct = max(0.0, pct[me]) if me < len(pct) else 0.0
        mode, laps_left = "none", None
        if laps_total and laps_total < UNLIMITED_LAPS and laps_rem < UNLIMITED_LAPS:
            mode, laps_left = "laps", max(0.0, laps_rem - mypct)
        elif time_total and time_total < UNLIMITED_TIME and time_rem < UNLIMITED_TIME and lap_t:
            mode = "time"
            laps_left = max(0.0, math.ceil(mypct + max(0.0, time_rem) / lap_t) - mypct)
        fuel = {
            "level": round(fuel_l, 3) if fuel_l is not None else None,
            "tank": round(self.tank, 1),
            "avg": round(avg, 3) if avg else None,
            "last": round(self.fuel.hist[-1], 3) if self.fuel.hist else None,
            "laps": [round(x, 2) for x in self.fuel.hist],
            "provisional": provisional,
            "fuelLaps": round(fuel_l / avg, 2) if avg and fuel_l is not None else None,
            "mode": mode,
            "lapsLeft": round(laps_left, 2) if laps_left is not None else None,
            "lapTime": round(lap_t, 3) if lap_t else None,
        }

        # weather
        wetness = int(raw.get("TrackWetness") or 0)
        hum = raw.get("RelativeHumidity")
        wx = {
            "air": raw.get("AirTemp"), "track": raw.get("TrackTemp"), "crew": raw.get("TrackTempCrew"),
            "wet": wetness, "wetName": WETNESS[wetness] if 0 <= wetness < len(WETNESS) else "Unknown",
            "precip": raw.get("Precipitation"), "hum": (hum / 100.0 if hum and hum > 1.5 else hum),
            "wind": raw.get("WindVel"), "windDir": raw.get("WindDir"), "yaw": raw.get("YawNorth"),
            "fog": raw.get("FogLevel"), "skies": raw.get("Skies"),
            "press": raw.get("AirPressure"), "sun": raw.get("SolarAltitude"),
            "tod": raw.get("SessionTimeOfDay"), "declaredWet": bool(raw.get("WeatherDeclaredWet")),
        }
        if raw.get("AirTemp") is not None and t - self._wx_t >= 5.0 or t < self._wx_t:
            self._wx_t = t
            self.wx_hist.append([round(t, 1), round(wx["air"] or 0, 2), round(wx["track"] or 0, 2),
                                 wetness, round(wx["precip"] or 0, 3)])

        # track recorder
        self.mapper.update(dt, float(raw.get("Speed") or 0), float(raw.get("YawNorth") or 0),
                           float(raw.get("LapDistPct") or 0), bool(raw.get("IsOnTrack")),
                           bool(raw.get("OnPitRoad")))

        tr = time_rem if time_rem < UNLIMITED_TIME else None
        return {
            "type": "state", "connected": True, "t": round(t, 2),
            "session": {
                "type": stype or "Session", "name": sess.get("SessionName") or stype,
                "isRace": is_race, "state": int(raw.get("SessionState") or 0),
                "stateName": SESSION_STATE.get(int(raw.get("SessionState") or 0), ""),
                "flag": flag, "timeRemain": tr,
                "timeTotal": time_total if time_total < UNLIMITED_TIME else None,
                "lapsRemain": laps_rem if laps_rem < UNLIMITED_LAPS else None,
                "lapsTotal": laps_total if laps_total < UNLIMITED_LAPS else None,
                "tod": raw.get("SessionTimeOfDay"), "replay": bool(raw.get("IsReplayPlaying")),
                "units": "imperial" if raw.get("DisplayUnits") == 0 else "metric",
            },
            "me": {
                "i": me, "p": overall.get(me), "cp": cpos.get(me), "cls": self.drivers.get(me, {}).get("cls"),
                "lap": raw.get("Lap"), "pct": raw.get("LapDistPct"),
                "last": raw.get("LapLastLapTime"), "best": raw.get("LapBestLapTime"),
                "cur": raw.get("LapCurrentLapTime"),
                "delta": raw.get("LapDeltaToBestLap"), "deltaOk": bool(raw.get("LapDeltaToBestLap_OK")),
                "speed": raw.get("Speed"), "gear": raw.get("Gear"), "rpm": raw.get("RPM"),
                "pit": bool(raw.get("OnPitRoad")), "inc": raw.get("PlayerCarMyIncidentCount"),
                "incLimit": self.meta.get("incLimit"),
            },
            "cars": cars, "rel": rel, "fuel": fuel, "wx": wx,
            "map": {"status": self.mapper.status, "progress": round(self.mapper.progress, 3),
                    "ver": self.mapper.version},
        }
