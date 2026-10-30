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
# per-car flags from CarIdxSessionFlags, most serious first
CAR_FLAGS = [(0x20000, "dq"), (0x10000, "black"), (0x100000, "repair"), (0x80000, "warn")]


SOF_K = 1600 / math.log(2)


def limit(v):
    """WeekendOptions incident limits: a number, or None for 'unlimited'."""
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def session_kind(stype):
    s = (stype or "").lower()
    if "race" in s:
        return "race"
    if "qualif" in s:
        return "qualify"
    if "test" in s:
        return "test"
    return "practice"   # practice, warmup, anything else


def sof(irs):
    irs = [r for r in irs if r and r > 0]
    return round(SOF_K * math.log(len(irs) / sum(math.exp(-r / SOF_K) for r in irs))) if irs else None


def ir_change(me_ir, me_pos, field):
    """Estimated iRating change, the community formula for iRacing's Elo-like system.
    field: [(ir, pos)] of every starter in my class, me included; pos 1-based."""
    n = len(field)
    if n < 2 or not me_ir or not me_pos:
        return None
    q = lambda r: math.exp(-r / SOF_K)
    expected = sum((1 - q(me_ir)) * q(r) / ((1 - q(r)) * q(me_ir) + (1 - q(me_ir)) * q(r))
                   for r, _ in field) - 0.5   # the sum includes me vs me = 0.5
    fudge = (n / 2 - me_pos) / 100
    return round((n - me_pos - expected - fudge) * 200 / n)


def car_flag(bits):
    bits = int(bits or 0)
    return next((name for bit, name in CAR_FLAGS if bits & bit), None)


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


# CarPath prefix -> make (simple-icons slug on the client); first match wins
MAKES = [
    ("porsche", "porsche"), ("ferrari", "ferrari"), ("bmw", "bmw"), ("mclaren", "mclaren"),
    ("mercedes", "mercedes"), ("amg", "mercedes"), ("audi", "audi"), ("lamborghini", "lamborghini"),
    ("ford", "ford"), ("astonmartin", "astonmartin"), ("amvantage", "astonmartin"), ("amvalkyrie", "astonmartin"), ("aston", "astonmartin"),
    ("chevyvette", "corvette"), ("chevy", "chevrolet"), ("chevrolet", "chevrolet"), ("toyota", "toyota"), ("acura", "acura"),
    ("cadillac", "cadillac"), ("honda", "honda"), ("hyundai", "hyundai"), ("mazda", "mazda"),
    ("mx5", "mazda"), ("nissan", "nissan"), ("mini", "mini"), ("kia", "kia"), ("renault", "renault"),
    ("vw", "volkswagen"), ("volkswagen", "volkswagen"), ("lotus", "lotus"), ("ligier", "ligier"),
    ("dallara", "dallara"), ("oreca", "oreca"), ("radical", "radical"), ("ginetta", "ginetta"),
]


def car_make(path):
    p = (path or "").lower()
    return next((make for prefix, make in MAKES if p.startswith(prefix)), "")


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
    """Last time each car crossed each bin boundary (tab[b] = crossing of b/BINS)."""

    def __init__(self):
        self.tab = {}
        self.last = {}

    def feed(self, idx, pct, t):
        tab = self.tab.setdefault(idx, [None] * BINS)
        prev = self.last.get(idx)
        self.last[idx] = (pct, t)
        if prev is None or t < prev[1] or t - prev[1] > 3.0:
            tab[int(pct * BINS) % BINS] = t
            return
        pp, pt = prev
        d = (pct - pp) % 1.0
        if d == 0 or d > 0.5:  # stopped, or jitter backwards
            return
        if d > 40 / BINS:  # jump (reset, tow, rewind): don't invent data
            tab[int(pct * BINS) % BINS] = t
            return
        # interpolate the exact crossing time of every boundary passed this frame
        x0 = pp * BINS
        k = math.floor(x0) + 1
        while k <= x0 + d * BINS:
            tab[k % BINS] = pt + (t - pt) * (k - x0) / (d * BINS)
            k += 1

    def since(self, idx, pct, now):
        tab = self.tab.get(idx)
        if not tab:
            return None
        x = pct * BINS
        b = int(x) % BINS
        v0, v1 = tab[b], tab[(b + 1) % BINS]
        if v0 is None:
            return None
        if v1 is not None and 0 < v1 - v0 < 5.0:  # same pass: interpolate inside the bin
            v0 += (v1 - v0) * (x - math.floor(x))
        return now - v0


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
        self._sess_id = None   # (SubSessionID, SessionNum): laps, fuel, grid... belong to one session
        self._qgrid = {}       # starting grid from the qualifying results
        self._qtimes = {}      # car -> (fastest, last) qualifying lap, shown until the green
        self._in_pit = set()   # cars seen on pit road
        self._out = {}         # car -> laps completed when it left pit road (out lap)
        self._pits = {}        # car -> [lap of its last pit stop, pit road entry time, time on pit road or None while there]
        self._laps = {}        # car -> deque of its latest valid lap times, newest first
        self._seen_last = {}   # car -> CarIdxLastLapTime last seen (a change = a new lap)
        self.tyres = {}        # tyre compound index -> "dry" / "wet" (DriverInfo.DriverTires)
        self._grid = {}        # car -> starting position (overall) for positions gained in a race
        self._mylaps = deque(maxlen=60)   # my lap log (test sessions): lap, time, temp, fuel left, fuel used
        self._my_last = None
        self._fuel_at_line = None
        self._my_lapc = None

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
            "incDq": limit((wk.get("WeekendOptions") or {}).get("IncidentLimit")),
            "incPen": limit((wk.get("WeekendOptions") or {}).get("IncidentWarningInitialLimit")),
            "incPenNext": limit((wk.get("WeekendOptions") or {}).get("IncidentWarningSubsequentLimit")),
            "category": wk.get("Category"),
            "seriesId": wk.get("SeriesID"),
            "subId": wk.get("SubSessionID"),
            "sectors": [round(float(x.get("SectorStartPct") or 0), 5) for x in (info.get("SplitTimeInfo") or {}).get("Sectors") or []],
        }
        # starting grid for "positions gained" (qualifying results, 0-based in iRacing)
        qres = (info.get("QualifyResultsInfo") or {}).get("Results") or []
        self._qgrid = {int(r["CarIdx"]): int(r.get("Position", -1)) + 1 for r in qres if r.get("CarIdx") is not None}
        self.sessions = {s.get("SessionNum"): s for s in (si.get("Sessions") or [])}
        # qualifying lap times, shown in the race until the green flag
        self._qtimes = {}
        for r in (info.get("QualifyResultsInfo") or {}).get("Results") or []:
            if r.get("CarIdx") is not None and (r.get("FastestTime") or 0) > 0:
                self._qtimes[int(r["CarIdx"])] = (float(r["FastestTime"]), None)
        for q in self.sessions.values():
            if session_kind(q.get("SessionType")) == "qualify":
                for r in q.get("ResultsPositions") or []:
                    fast, lst = float(r.get("FastestTime") or -1), float(r.get("LastTime") or -1)
                    if r.get("CarIdx") is not None and fast > 0:
                        self._qtimes[int(r["CarIdx"])] = (fast, lst if lst > 0 else None)
        self.player = int(di.get("DriverCarIdx") or 0)
        mx = float(di.get("DriverCarFuelMaxLtr") or 0) * float(di.get("DriverCarMaxFuelPct") or 1)
        self.tank = mx
        est_default = float(di.get("DriverCarEstLapTime") or 100.0)
        self.tyres = {int(t.get("TireIndex", k)): ("wet" if "wet" in str(t.get("TireCompoundType", "")).lower() else "dry")
                      for k, t in enumerate(di.get("DriverTires") or [])}
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
            # "Matthieu Laurent2": iRacing's suffix for duplicate names, not part of the name
            name = re.sub(r"\d+$", "", (d.get("UserName") or "").strip()).strip() or f"Car {idx}"
            self.drivers[idx] = {
                # solo sessions report the user name as the team: not a team
                "i": idx, "name": name, "team": "" if d.get("TeamName") == d.get("UserName") else d.get("TeamName") or "",
                "make": car_make(d.get("CarPath")), "country": d.get("FlairName") or "",
                "num": str(d.get("CarNumber") or ""), "cls": cid, "car": car,
                "ir": d.get("IRating") or 0, "lic": d.get("LicString") or "",
                "licColor": hexcolor(d.get("LicColor"), "#8b95a7"), "ai": bool(d.get("CarIsAI")),
            }
        for c in classes.values():   # strength of field, iRacing's formula, per class
            irs = [d["ir"] for d in self.drivers.values() if d["cls"] == c["id"] and d["ir"] > 0]
            c["sof"] = round(SOF_K * math.log(len(irs) / sum(math.exp(-r / SOF_K) for r in irs))) if irs else None
        ordered = sorted(classes.values(), key=lambda c: c["est"])
        self.meta["sof"] = sof([d["ir"] for d in self.drivers.values()])
        self.classes = {c["id"]: c for c in ordered}
        self.class_order = [c["id"] for c in ordered]
        if len(self.classes) == 1:  # single class: the colour carries no information, use the dash amber
            next(iter(self.classes.values()))["color"] = "#f4b400"
        if key != self._session_key:   # new track: map, timing loops
            self._session_key = key
            self.mapper.set_track(key, track_id)
            self.log = PassLog()
        self.drivers_ver += 1

    def drivers_msg(self):
        return {
            "type": "drivers", "ver": self.drivers_ver, "meta": self.meta,
            "drivers": self.drivers,
            "classes": [self.classes[c] for c in self.class_order],
        }

    def track_msg(self):
        return {"type": "track", "key": self.mapper.key, "status": self.mapper.status,
                "ver": self.mapper.version, "points": self.mapper.points,
                "turns": self.mapper.turns, "source": self.mapper.source, "offset": self.mapper.offset}

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
        est = arr("CarIdxEstTime", None)
        cflags = arr("CarIdxSessionFlags", blank)
        tyre = arr("CarIdxTireCompound", [-1] * 64)
        # lap history for the standings delta columns: a new CarIdxLastLapTime is a new lap
        # (an invalidated lap reports -1 and is simply not recorded)
        if self._seen_last is None:   # first frame of a session: take note, a lap only counts once it changes
            self._seen_last = dict(enumerate(last))
        for i, lt in enumerate(last):
            if lt and lt > 0 and lt != self._seen_last.get(i):
                h = self._laps.setdefault(i, deque(maxlen=3))
                if not h or h[0] != round(lt, 3):   # -1 then the same time again (left/rejoined): not a new lap
                    h.appendleft(round(lt, 3))
            self._seen_last[i] = lt

        snum = raw.get("SessionNum")
        # a new session (another event, or practice -> qualify -> race) starts its own laps:
        # same track or not, nothing lap-related carries over
        sid = (self.meta.get("subId"), snum)
        if sid != self._sess_id:
            self._sess_id = sid
            self.fuel.reset()
            self.wx_hist.clear()   # weather is per session too (set by hand, or rain in one and not the next)
            self._wx_t = -1e9
            self._in_pit, self._out, self._pits = set(), {}, {}
            self._laps, self._seen_last = {}, None
            self._mylaps, self._my_last, self._fuel_at_line, self._my_lapc = deque(maxlen=60), raw.get("LapLastLapTime"), None, None
            self._pending_lap = None
            self._grid = {}
        if not self._grid and self._qgrid:
            self._grid = dict(self._qgrid)
        sess = self.sessions.get(snum) or {}
        # CarIdxBest/LastLapTime are wiped for cars that leave the world (garage, disconnect);
        # the session results in SessionInfo keep everyone's times
        res = {r.get("CarIdx"): r for r in (sess.get("ResultsPositions") or [])}
        best = [b if b > 0 else float((res.get(i) or {}).get("FastestTime") or -1) for i, b in enumerate(best)]
        last = [x if x > 0 else float((res.get(i) or {}).get("LastTime") or -1) for i, x in enumerate(last)]
        stype = (sess.get("SessionType") or "").strip()
        kind = session_kind(stype)
        is_race = kind == "race"
        flag = flag_name(raw.get("SessionFlags"))
        me = int(raw.get("PlayerCarIdx") if raw.get("PlayerCarIdx") is not None else self.player)
        talk = raw.get("RadioTransmitCarIdx")

        present = []
        for idx in self.drivers:
            if idx >= len(surf):
                continue
            present.append(idx)   # everyone registered, also those who never went on track
            if surf[idx] >= 0 and 0 <= pct[idx] <= 1.0:
                self.log.feed(idx, pct[idx], t)
            # out lap: from leaving pit road until the next line crossing
            if surf[idx] < 0 or pitr[idx]:
                self._out.pop(idx, None)
                if pitr[idx]:
                    if idx not in self._in_pit:   # last pit stop: lap it is on and pit road time
                        self._pits[idx] = [(lapc[idx] or 0) + 1, t, None]
                    self._in_pit.add(idx)
                elif idx in self._pits and self._pits[idx][2] is None:   # to the garage from the pits: not a stop
                    del self._pits[idx]
                    self._in_pit.discard(idx)
            elif idx in self._in_pit:
                self._in_pit.discard(idx)
                self._out[idx] = lapc[idx]
                if idx in self._pits and self._pits[idx][2] is None:
                    self._pits[idx][2] = t - self._pits[idx][1]
            elif idx in self._out and lapc[idx] != self._out[idx]:
                del self._out[idx]

        tot = {i: (lapc[i] if lapc[i] is not None and lapc[i] > -2 else 0) + max(0.0, pct[i]) for i in present}

        # ordering. Race, while racing: live order by distance covered (laps + lap fraction), the
        # way overlays do it - CarIdxPosition only changes when a car crosses the line. Cars not
        # on track keep iRacing's position behind them. Otherwise iRacing's position when it has one.
        racing = is_race and int(raw.get("SessionState") or 0) == 4
        if racing and any(lapc[i] is not None and lapc[i] >= 0 and surf[i] >= 0 for i in present):
            running = [i for i in present if lapc[i] is not None and lapc[i] >= 0 and surf[i] >= 0]
            rest = [i for i in present if i not in running]
            order = sorted(running, key=lambda i: (-tot[i], i)) + sorted(rest, key=lambda i: (pos[i] if pos[i] > 0 else 999 + i))
        elif is_race and int(raw.get("SessionState") or 0) < 4:
            # before the green (grid, parade/formation lap): frozen in grid order, whatever
            # happens on track - nothing moves, neither the rows nor the numbers
            grid = self._grid or self._qgrid
            order = sorted(present, key=lambda i: (grid.get(i) or (pos[i] if pos[i] > 0 else 999), i))
        elif any(pos[i] > 0 for i in present):
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
        if not is_race:  # practice/qualy: no lap time, no position (they are sorted last already)
            for i in order:
                if best[i] <= 0:
                    overall[i] = cpos[i] = None
        # race, before the green: Last / Fastest are the qualifying laps and gaps compare them
        pre_green = is_race and int(raw.get("SessionState") or 0) < 4
        if pre_green:
            best = [self._qtimes.get(i, (-1, None))[0] for i in range(len(best))]
            last = [self._qtimes.get(i, (-1, None))[1] or self._qtimes.get(i, (-1, None))[0] for i in range(len(last))]
        class_best = {}
        for cid, g in groups.items():
            bs = [best[i] for i in g if best[i] > 0]
            class_best[cid] = min(bs) if bs else None

        my_cls = self.drivers.get(me, {}).get("cls")
        ref = (class_best.get(my_cls) or best[me] if me < len(best) else 0) or 0
        if not ref or ref <= 0:
            ref = (self.classes.get(my_cls) or {}).get("est") or 100.0

        def lap_of(i):
            return (self.classes.get(self.drivers[i]["cls"]) or {}).get("est") or ref

        def est_gap(a, b):
            """Fallback before the PassLog has data: seconds since car a (ahead) was where car b is.
            CarIdxEstTime follows the track's speed profile; b's value is rescaled to a's class."""
            la = lap_of(a)
            linear = ((pct[a] - pct[b]) % 1.0) * la
            if est is None:
                return linear
            g = (est[a] - est[b] * la / lap_of(b)) % la
            # EstTime isn't monotonic in the pit lane: a car a hair ahead in the stalls can
            # carry a smaller estimate, and the modulo turns that into a whole lap (-203 s).
            # If the estimate disagrees with the track order, trust the distance.
            return linear if g > la / 2 and linear < la / 2 else g

        def timed_gap(a, b):
            """Seconds car b (behind) is from car a (ahead). The PassLog ("how long ago did a
            pass where b is now") is exact while both race; it goes stale as soon as a stops or
            crawls (pit stall, spin, tow), so then fall back to iRacing's estimate."""
            est_s = est_gap(a, b)
            if surf[a] != 3 or surf[b] != 3 or pitr[a] or pitr[b]:  # 3 = on track
                return est_s
            s = self.log.since(a, pct[b], t)
            if s is None or s < 0 or abs(s - est_s) > max(2.0, 0.3 * est_s):
                return est_s
            return s

        def gap(i, j):
            """(laps_down, seconds) of car i relative to car j that is ahead of it."""
            diff = tot[j] - tot[i]
            laps = int(math.floor(diff + 1e-6))
            if laps >= 1:
                return laps, None
            if diff <= 0:
                return 0, 0.0
            return 0, round(timed_gap(j, i), 3)

        # starting grid: qualifying results, else the first racing position we see
        if is_race and int(raw.get("SessionState") or 0) >= 4:
            for i in present:
                if i not in self._grid and pos[i] > 0:
                    self._grid[i] = pos[i]
        cgrid = {}   # start position within the class
        for g in groups.values():
            ranked = sorted((i for i in g if i in self._grid), key=lambda i: self._grid[i])
            cgrid.update({i: k + 1 for k, i in enumerate(ranked)})

        cars = []
        for k, i in enumerate(order):
            cid = self.drivers[i]["cls"]
            g = groups[cid]
            ci = g.index(i)
            c = {
                "i": i, "p": overall[i], "cp": cpos[i], "lap": lapc[i], "pct": round(pct[i], 5),
                "last": round(last[i], 3) if last[i] > 0 else None,
                "best": round(best[i], 3) if best[i] > 0 else None,
                "pit": bool(pitr[i]), "out": i in self._out, "fl": car_flag(cflags[i]), "srf": surf[i],
                "tc": self.tyres.get(tyre[i], "wet" if tyre[i] > 0 else "dry") if tyre[i] >= 0 else None,
                "lh": list(self._laps.get(i, ())),
                # last pit stop: lap, seconds on pit road, still there (pd counts up live)
                **({"pl": self._pits[i][0], "pd": round(self._pits[i][2] if self._pits[i][2] is not None else t - self._pits[i][1], 1),
                    "pip": self._pits[i][2] is None} if i in self._pits else {}),
                "cb": bool(best[i] > 0 and class_best.get(cid) == best[i]),
                "pb": bool(best[i] > 0 and last[i] > 0 and abs(last[i] - best[i]) < 1e-4),
            }
            if is_race and not pre_green:
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
            if is_race and overall[i] and i in self._grid:   # positions gained (+) / lost (-) since the start
                c["pg"], c["pgc"] = self._grid[i] - overall[i], (cgrid[i] - cpos[i]) if i in cgrid and cpos[i] else None
            cars.append(c)

        # estimated iRating change for everyone (race, within each class, at the current positions)
        ir_gain = None
        if is_race:
            byc = {c["i"]: c for c in cars}
            for g in groups.values():
                field = [(self.drivers[i]["ir"], cpos[i]) for i in g if cpos.get(i)]
                for i in g:
                    if cpos.get(i):
                        byc[i]["irg"] = ir_change(self.drivers[i]["ir"], cpos[i], field)
            ir_gain = byc.get(me, {}).get("irg")

        # my lap log (test sessions): fuel is split at the line, the lap time arrives just after
        my_fuel = raw.get("FuelLevel")
        if lapc[me] != self._my_lapc:
            if self._my_lapc is not None and lapc[me] > (self._my_lapc or 0):
                used = (self._fuel_at_line - my_fuel) if self._fuel_at_line is not None and my_fuel is not None else None
                self._pending_lap = {"lap": lapc[me], "temp": raw.get("TrackTemp"), "fuel": my_fuel,
                                     "used": round(used, 3) if used is not None and used >= 0 else None}
            self._my_lapc, self._fuel_at_line = lapc[me], my_fuel
        mylast = raw.get("LapLastLapTime")
        if mylast != self._my_last:
            pend = getattr(self, "_pending_lap", None)
            if pend and mylast and mylast > 0:
                pend["time"] = round(mylast, 3)
                self._mylaps.appendleft(pend)
                self._pending_lap = None
            self._my_last = mylast

        # relative: everyone physically near me, by real elapsed time
        rel = []
        if me in tot and surf[me] >= 0 and pct[me] >= 0:
            for i in present:
                if i == me or surf[i] < 0 or pct[i] < 0:
                    continue
                dp = pct[i] - pct[me]
                dp = (dp + 0.5) % 1.0 - 0.5
                dtm = timed_gap(i, me) if dp >= 0 else -timed_gap(me, i)
                # lap difference only means something in a race (in practice everyone is "laps ahead")
                laps = int(round(tot[i] - tot[me] - dp)) if is_race else 0
                rel.append({"i": i, "dt": round(dtm, 2), "dl": laps, "pit": bool(pitr[i]), "out": i in self._out, "fl": car_flag(cflags[i]), "srf": surf[i]})
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
            "grip": sess.get("SessionTrackRubberState"),   # iRacing gives the rubber state as words
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
                "isRace": is_race, "kind": kind, "state": int(raw.get("SessionState") or 0),
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
                "incPen": self.meta.get("incPen"), "incPenNext": self.meta.get("incPenNext"), "incDq": self.meta.get("incDq"),
                "irGain": ir_gain, "laps": list(self._mylaps),
            },
            "cars": cars, "rel": rel, "fuel": fuel, "wx": wx,
            "talk": talk if talk is not None and talk >= 0 else None,   # car on the radio right now
            "map": {"status": self.mapper.status, "progress": round(self.mapper.progress, 3),
                    "ver": self.mapper.version},
        }
