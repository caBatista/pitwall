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
import time
from collections import deque
from statistics import median
from types import SimpleNamespace
from functools import lru_cache

from .events import EventLog
from .trackmap import TrackMapper

BINS = 360
SESSION_STATE = {0: "Invalid", 1: "Get in car", 2: "Warm-up", 3: "Parade laps", 4: "Racing", 5: "Checkered", 6: "Cool down"}
UNLIMITED_TIME = 604000.0   # iRacing reports 604800 s (a week) and 32767 laps; a 24 h race is 86400 s and real
UNLIMITED_LAPS = 32000
# per-car flags from CarIdxSessionFlags, most serious first
CAR_FLAGS = [(0x20000, "dq"), (0x10000, "black"), (0x100000, "repair"), (0x80000, "warn")]
YELLOWS = 0x8 | 0x100 | 0x4000 | 0x8000   # yellow, yellow waving, caution, caution waving


SOF_K = 1600 / math.log(2)
GAP_FIELDS = ("gl", "ld", "gi", "li", "go", "lo", "gio", "lio")   # gaps / laps to class leader, interval, overall


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
    fudge = (n / 2 - me_pos) / 100
    return round((n - me_pos - _ir_expected(me_ir, tuple(r for r, _ in field)) - fudge) * 200 / n)


@lru_cache(maxsize=128)
def _ir_expected(me_ir, irs):
    """Part of ir_change that doesn't depend on positions: the same every frame of a session."""
    q = lambda r: math.exp(-r / SOF_K)
    return sum((1 - q(me_ir)) * q(r) / ((1 - q(r)) * q(me_ir) + (1 - q(me_ir)) * q(r))
               for r in irs) - 0.5   # the sum includes me vs me = 0.5


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


def race_flag(bits, car_bits=0):
    """The flag the driver is under, the most serious first: what the background of the board shows."""
    bits = int(bits or 0) | int(car_bits or 0)
    if bits & (0x20000 | 0x10000):
        return "black"
    if bits & 0x100000:
        return "meatball"
    if bits & YELLOWS:
        return "yellow"
    if bits & 0x40:
        return "debris"
    if bits & 0x1:
        return "checkered"
    if bits & 0x2:
        return "white"
    if bits & 0x20:
        return "blue"
    return "green" if bits & 0x4 else None


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


# Sessions with AI cars come with no class name (seen at Daytona, IMSA grid, 2026-11-05)
CLASS_NAMES = {4029: "GTP", 2523: "LMP2", 4011: "GT3"}
CLASS_IN_CAR = re.compile(r"(?<![A-Z0-9])(GTP|GT[34]|LMP[0-9])(?![A-Z0-9])")


def class_name(cid, car):
    m = CLASS_IN_CAR.search(car or "")
    return CLASS_NAMES.get(cid) or (m.group(1) if m else None)


# Seconds a stop costs at the least. Too low only means one lap more of fuel, too high a car that stops
# short of the line
PIT_LOSS = 25.0


def laps_to_flag(lead_done, lead_lap, my_done, my_lap, laps_total=None, time_rem=None, stop=0.0):
    """Laps I still drive, from here, until I see the chequered flag. The flag falls for the overall
    leader: when they complete the last lap of a lap race, or the lap running when the clock hits zero
    of a timed one. Then I finish the lap I am on, which may be one lap more than my own clock says.
    lead_done, my_done: laps covered, with the fraction. stop: seconds I will still lose in the pits:
    without it, a car about to stop, ahead of a leader who already did, drives one lap too many.
    Same reasoning as irdashies' FuelProjectionProcessor."""
    limits = []
    if laps_total:
        limits.append(max(0.0, laps_total - lead_done))
    if time_rem is not None:
        clock = max(0.0, time_rem - (stop if lead_done == my_done else 0.0))   # leading, my stop is the leader's
        limits.append(math.ceil(lead_done % 1.0 + clock / lead_lap - 1e-6) - lead_done % 1.0)
    left = min(limits, default=0.0)   # both set: whichever comes first
    mine = my_done % 1.0
    return max(0.0, math.ceil(mine + max(0.0, left * lead_lap - stop) / my_lap - 1e-6) - mine)


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
        """Mean of the latest 8 clean laps. A lap far from their median (a spin, a stretch off the
        racing line, a lift behind traffic) says nothing about the next one: Auto fuel uses this."""
        recent = list(self.hist)[-8:]
        if len(recent) >= 3:
            mid = sorted(recent)[len(recent) // 2]
            recent = [x for x in recent if abs(x - mid) <= 0.2 * mid] or recent
        return sum(recent) / len(recent) if recent else None

    @property
    def avg_time(self):
        recent = list(self.times)[-5:]
        return sum(recent) / len(recent) if recent else None


class _ReadOnlyMapper:
    """The track map as the replay's engine sees it: a replay must not record or recalibrate anything."""

    def __init__(self, mapper):
        self._mapper = mapper

    def __getattr__(self, name):
        return getattr(self._mapper, name)

    def set_track(self, *a, **k):
        pass

    def update(self, *a, **k):
        pass


class Engine:
    def __init__(self, mapper: TrackMapper):
        self.mapper = mapper
        self.drivers = {}
        self.classes = {}
        self.sessions = {}
        self.meta = {}
        self.player = 0
        self.tank = 0.0
        self.kg_per_l = 0.75
        self.drivers_ver = 0
        self.log = PassLog()
        self.fuel = FuelTracker()
        self.ev = EventLog()
        self.in_car = False
        self._info = None     # the session info, for the replay's engine
        self._lap_now = {}    # car -> (laps, time, pct) as last seen: a lap begins when it is seen crossing the line
        self.cam_now, self.raw_now = {}, {}
        self._live, self._live_at = None, 0.0   # the last frame that was the present
        self._replay = None   # the engine that reads the replay, see update()
        self.wx_hist = deque(maxlen=720)  # 5 s samples = 1 hour
        self._wx_t = -1e9
        self._prev_t = None
        self._session_key = None
        self._sess_id = None   # (SubSessionID, SessionNum): laps, fuel, grid... belong to one session
        self._qgrid = {}       # starting grid from the qualifying results
        self._qtimes = {}      # car -> (fastest, last) qualifying lap, shown until the green
        self._in_pit = set()   # cars seen on pit road
        self._out = {}         # car -> laps completed when it left pit road (out lap)
        self._flag_lap = None  # my laps completed when the checkered flag came out (race over once I cross)
        self._flag_laps, self._fin = {}, set()   # everyone's laps at the flag / who took the checkered
        self._ended = set()    # (sub-session, session): races seen reaching the flag
        self._race_gaps = {}   # car -> its gap fields on the last frame before the checkered flag
        self._pits = {}        # car -> [lap of its last pit stop, pit road entry time, time on pit road or None while there]
        self._laps = {}        # car -> deque of its latest laps (time, invalid?), newest first
        self._seen_last = {}   # car -> CarIdxLastLapTime last seen (a change = a new lap)
        self._race_laps = None  # (my race length in laps, estimated?)
        self._lap_seen = 0     # my lap, kept when the sim stops telling
        self.tyre_on = None     # "dry" / "wet" on my car
        self.pit_in = False     # this frame I entered the pit lane, in a race under green
        self._on_pit, self._fuel_now = True, (None, None, None)   # (level, clean average, laps left)
        self._want, self._want_raw, self._want_t = None, None, 0.0   # tyre the weather asks for (held 5 s)
        self._mark, self._line, self._pend_lap, self._lap_t = {}, {}, {}, {}   # own lap timing (invalid laps)
        self._lap_sync = {}    # car -> (laps, pct, correction, since when), see lap_fix
        self._inc_line = None   # my incident count when my last lap ended
        self.tyres = {}        # tyre compound index -> "dry" / "wet" (DriverInfo.DriverTires)
        self._grid = {}        # car -> starting position (overall) for positions gained in a race
        self._mylaps = deque(maxlen=60)   # my lap log (test sessions): lap, time, temp, fuel left, fuel used
        self._my_last = None
        self._fuel_at_line = None
        self._my_lapc = None

    # ---- session info ------------------------------------------------------
    def event_info(self):
        """What a saved race needs to be read again another day."""
        m = self.drivers_msg()
        return {"meta": m["meta"], "drivers": m["drivers"], "classes": m["classes"], "player": self.player}

    def set_session(self, info):
        self._info = info
        if self._replay:
            self._replay.set_session(info)
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
            "cameras": [{"n": g.get("GroupNum"), "name": g.get("GroupName"), "scenic": bool(g.get("IsScenic")),
                         "cams": [{"n": c.get("CameraNum"), "name": c.get("CameraName")} for c in g.get("Cameras") or []]}
                        for g in (info.get("CameraInfo") or {}).get("Groups") or []],
            "replayFile": str(wk.get("SimMode") or "").lower() == "replay",   # a saved replay, not a live session
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
        self.kg_per_l = float(di.get("DriverCarFuelKgPerLtr") or 0.75)
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
            cname = d.get("CarClassShortName") or class_name(cid, d.get("CarScreenName")) or car or f"Class {cid}"
            col = hexcolor(d.get("CarClassColor"))
            est = float(d.get("CarClassEstLapTime") or est_default)
            classes.setdefault(cid, {"id": cid, "name": cname, "color": col, "est": est, "n": 0})
            classes[cid]["n"] += 1
            # "Matthieu Laurent2": iRacing's suffix for duplicate names, not part of the name
            name = re.sub(r"\d+$", "", (d.get("UserName") or "").strip()).strip() or f"Car {idx}"
            self.drivers[idx] = {
                # solo sessions report the user name as the team: not a team
                "i": idx, "name": name, "user": (d.get("UserName") or "").strip(), "team": "" if d.get("TeamName") == d.get("UserName") else d.get("TeamName") or "",
                "make": car_make(d.get("CarPath")), "country": d.get("FlairName") or "",
                "num": str(d.get("CarNumber") or ""), "cls": cid, "car": car, "est": est,
                "ir": d.get("IRating") or 0, "lic": d.get("LicString") or "",
                "licColor": hexcolor(d.get("LicColor"), "#8b95a7"), "ai": bool(d.get("CarIsAI")),
            }
        for c in classes.values():   # strength of field, iRacing's formula, per class
            irs = [d["ir"] for d in self.drivers.values() if d["cls"] == c["id"] and d["ir"] > 0]
            c["sof"] = round(SOF_K * math.log(len(irs) / sum(math.exp(-r / SOF_K) for r in irs))) if irs else None
        ordered = sorted(classes.values(), key=lambda c: c["est"])
        self.meta["sof"] = sof([d["ir"] for d in self.drivers.values()])
        self.meta["ai"] = any(d["ai"] for d in self.drivers.values())   # no ratings, licences or countries to show
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
    def tyre_index(self, kind):
        """Compound index iRacing uses for "dry" / "wet", None if this car doesn't have it."""
        return next((i for i, k in sorted(self.tyres.items()) if k == kind), None)

    def fuel_needed(self, reserve, laps):
        """Litres to finish with reserve (in laps) in the tank: 0 if the tank already has it, None if
        there is no clean average yet. laps: the race length typed in, when the session doesn't give one."""
        level, avg, left = self._fuel_now
        target = left if left is not None else laps
        if not avg or level is None or target is None:
            return None
        need = (target + reserve) * avg - level
        return max(0.0, min(need, self.tank - level) if self.tank else need)

    def lap_fix(self, i, laps, pct, t):
        """The lap counter and the lap distance don't flip on the same frame at the line. Added up, the
        car would jump a whole lap back or forward for a moment: order and gaps blink. Crew Chief
        corrects the same mismatch. Returns -1, 0 or +1 to add to the laps; never for more than 2 s, so
        a tow or a reset isn't taken for a line crossing. A car that vanished from the telemetry changes
        nothing here: if it crossed the line meanwhile, it is the wrapped distance that says so."""
        if laps < 0 or pct < 0:
            return 0
        prev = self._lap_sync.get(i)
        fix, since = 0, t
        if prev:
            lc0, p0, fix0, t0 = prev
            if laps == lc0 and p0 - pct > 0.5:      # distance wrapped: ahead of the counter, or caught up with it
                fix = 1 if fix0 >= 0 else 0
            elif laps == lc0 + 1 and pct > 0.5:     # counter first, distance still before the line
                fix = -1
            elif laps == lc0 and fix0 and t - t0 < 2 and (pct < 0.5) == (fix0 > 0):   # still waiting
                fix, since = fix0, t0
        self._lap_sync[i] = (laps, pct, fix, since)
        return fix

    def update(self, raw):
        self.cam_now, self.raw_now = self._cam(raw), raw
        return self._frame(raw)

    def place(self, i):
        """Where this car is on the moment on screen, in laps (2.5: halfway through lap 3). None: not on track."""
        laps, pct = self.raw_now.get("CarIdxLapCompleted") or [], self.raw_now.get("CarIdxLapDistPct") or []
        if not isinstance(i, int) or i >= len(laps) or i >= len(pct) or laps[i] < 0 or pct[i] < 0:
            return None
        return laps[i] + pct[i]

    def now_shown(self):
        """(session, time) of the moment on screen."""
        raw = self.raw_now
        return raw.get("SessionNum") or 0, float(raw.get("ReplaySessionTime") or raw.get("SessionTime") or 0.0)

    def lap_guess(self, i, lap):
        """About when this car began this lap: from the nearest moment known, at a little over its fastest lap.
        Close is enough, iRacing's own lap jump lands on the line from anywhere within a lap. None: nothing to go by."""
        sn, t = self.now_shown()
        fast = next((float(r.get("FastestTime") or 0) for r in (self.sessions.get(sn) or {}).get("ResultsPositions") or [] if r.get("CarIdx") == i), 0.0)
        known = [(k - 1, v) for k, v in self.ev.laps.get(sn, {}).get(i, {}).items()]
        if self.place(i) is not None:
            known.append((self.place(i), t))
        if fast <= 0 or not known:
            return None
        at, when = min(known, key=lambda x: abs(x[0] - (lap - 1)))
        return max(0.0, when + (lap - 1 - at) * fast * 1.02)

    def lap_seen(self, i, lap, t):
        """iRacing's own lap jump landed here, right at the line: nothing knows better."""
        self.ev.laps.setdefault(self.now_shown()[0], {}).setdefault(i, {})[lap] = round(t, 3)

    def _frame(self, raw):
        """A frame of state. While the driver watches the replay all the telemetry is that moment of the
        race, the session and the clock included, and nothing live comes through: the board stays on the
        last live frame, with what still arrives on top (the clock, the results in SessionInfo). The replay
        goes to a second engine, whose only job is to feed the Race Events."""
        behind = (raw.get("ReplayFrameNumEnd") or 0) / 60.0 if raw.get("IsReplayPlaying") and not self.meta.get("replayFile") else 0.0
        if behind <= 3 or self._live is None:
            st = self._update(raw)
            if behind <= 3:
                self._live, self._live_at = st, time.monotonic()
            elif st.get("session", {}).get("timeRemain") is not None:   # opened in the replay: now is this far ahead of the screen
                st = {**st, "session": {**st["session"], "timeRemain": max(0.0, st["session"]["timeRemain"] - behind)}}
            return self._finished(st)
        return self._finished(self._seen_from_replay(raw, behind))

    def _cam(self, raw):
        """The camera and the replay, always as they are: nothing here belongs to a moment of the race."""
        i, laps = raw.get("CamCarIdx"), raw.get("CarIdxLapCompleted") or []
        done = laps[i] if isinstance(i, int) and 0 <= i < len(laps) else -1   # the lap on screen, not the board's
        results = (self.sessions.get(raw.get("SessionNum")) or {}).get("ResultsPositions") or []
        if done < 0:   # gone from the world: its last lap
            done = next(((r.get("LapsComplete") or 0) - 1 for r in results if r.get("CarIdx") == i), -1)
        return {"i": i, "g": raw.get("CamGroupNumber"), "c": raw.get("CamCameraNumber"), "st": raw.get("CamCameraState") or 0,
                "lap": done + 1 if done >= 0 else None,
                "race": "race" in str((self.sessions.get(raw.get("SessionNum")) or {}).get("SessionType") or "").lower(),
                "total": max((r.get("LapsComplete") or 0 for r in results), default=0),
                "speed": raw.get("ReplayPlaySpeed") or 0, "slow": bool(raw.get("ReplayPlaySlowMotion")), "replay": bool(raw.get("IsReplayPlaying"))}

    def lap_start(self, i, lap):
        """When this car began this lap, on the session on screen, if it is known."""
        return self.ev.laps.get(self.now_shown()[0], {}).get(i, {}).get(lap)

    def _seen_from_replay(self, raw, behind):
        if self._replay is None:
            self._replay = Engine(_ReadOnlyMapper(self.mapper))
            self._replay.ev, self._replay._ended = self.ev, self._ended
            if self._info:
                self._replay.set_session(self._info)
        seen = self._replay._update(raw)
        self.pit_in = False
        # where the driver is now, not where the last live frame found them: watching a replay is out of the car
        self.in_car = bool(raw.get("IsOnTrack"))
        live = self._live
        session = dict(live["session"], behind=round(behind, 1), inCar=self.in_car, rflag=None)
        if "session" in seen:
            session["static"] = seen["session"].get("static")
        if session.get("timeRemain") is not None:
            session["timeRemain"] = max(0.0, session["timeRemain"] - (time.monotonic() - self._live_at))
        me = seen.get("me") if seen.get("me", {}).get("i") is not None else live["me"]
        return self._with_results({**live, "session": session, "cam": self._cam(raw), "me": me})

    def _finished(self, st):
        """The result of a finished race, whatever moment the replay is on: no time left, and the footer is the
        driver's own end of the race, not that moment. The highlight follows the car on camera, as live."""
        s = st.get("session") or {}
        if not s.get("static"):
            return st
        session = dict(s, timeRemain=0.0 if s.get("timeRemain") is not None else None)
        r = next((x for x in (self.sessions.get(s.get("num")) or {}).get("ResultsPositions") or [] if x.get("CarIdx") == self.player), None)
        car = next((c for c in st["cars"] if c["i"] == self.player), None)
        if not r or not car:
            return {**st, "session": session}
        me = dict(st.get("user") or st["me"], i=self.player, cls=car.get("cls", (self.drivers.get(self.player) or {}).get("cls")), p=car.get("p"), cp=car.get("cp"),
                  lap=r.get("LapsComplete") or st["me"].get("lap"), inc=r.get("Incidents"))
        if (r.get("FastestTime") or 0) > 0:
            me["best"] = r["FastestTime"]
        if (r.get("LastTime") or 0) > 0:
            me["last"] = r["LastTime"]
        return {**st, "session": session, "user": me}   # the reference stays whoever is on camera

    def _with_results(self, st):
        """Positions and lap times keep coming in SessionInfo, as each car crosses the line."""
        res = {r.get("CarIdx"): r for r in ((self.sessions.get(st["session"].get("num")) or {}).get("ResultsPositions") or [])}
        if not res:
            return st

        def fresh(c):
            r = res.get(c["i"])
            if not r:
                return c
            c = dict(c)
            if (r.get("Position") or 0) > 0:
                c["p"], c["cp"] = r["Position"], (r.get("ClassPosition") or 0) + 1
            if (r.get("FastestTime") or 0) > 0:
                c["best"] = r["FastestTime"]
            if (r.get("LastTime") or 0) > 0:
                c["last"] = r["LastTime"]
            return c
        cars = sorted((fresh(c) for c in st["cars"]), key=lambda c: c.get("p") or 999)
        me = next((c for c in cars if c["i"] == st["me"]["i"]), None)
        return {**st, "cars": cars, "me": {**st["me"], "p": me["p"], "cp": me["cp"]} if me else st["me"]}

    def _update(self, raw):
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
        f2 = arr("CarIdxF2Time", None)   # iRacing's own time behind the leader
        cflags = arr("CarIdxSessionFlags", blank)
        tyre = arr("CarIdxTireCompound", [-1] * 64)
        # lap history (standings Last / delta columns): a new CarIdxLastLapTime is a new lap. An
        # invalidated lap gets no time (-1), so we time it ourselves, line to line, and mark it
        # (x = True); my own laps are also marked when I picked up incidents during them
        pme = raw.get("PlayerCarIdx")
        inc = raw.get("PlayerCarMyIncidentCount")
        if self._seen_last is None:   # first frame of a session: take note, a lap only counts once it changes
            self._seen_last = dict(enumerate(last))
            self._mark, self._line, self._pend_lap, self._lap_t = {}, {}, {}, {}
            self._inc_line = inc

        def push(i, lt, x):
            h = self._laps.setdefault(i, deque(maxlen=5))   # the Standings can compare up to 5
            if i == pme and inc is not None:
                x = x or (self._inc_line is not None and inc > self._inc_line)
                self._inc_line = inc
            if not x and h and h[0][1] and t - self._lap_t.get(i, -1e9) < 10:
                h[0] = (lt, h[0][1] and i == pme)   # the official time came late: not invalid after all
            else:
                h.appendleft((lt, x))
            self._lap_t[i] = t

        for i, lt in enumerate(last):
            if lt and lt > 0 and lt != self._seen_last.get(i):
                h = self._laps.get(i)
                if not h or h[0][0] != round(lt, 3):   # -1 then the same time again (left/rejoined): not a new lap
                    push(i, round(lt, 3), False)
                self._pend_lap.pop(i, None)
            self._seen_last[i] = lt
            # line crossings (interpolated between frames), for our own time of the lap
            lc, p = lapc[i] if i < len(lapc) else -1, pct[i] if i < len(pct) else -1.0
            prev = self._mark.get(i)
            if i >= len(surf) or surf[i] < 0 or not 0 <= p <= 1 or lc is None:
                self._mark.pop(i, None)
                self._line.pop(i, None)
                continue
            if prev and lc == prev[0] + 1:
                d = (p - prev[1]) % 1.0
                tc = prev[2] + (t - prev[2]) * min(1.0, (1.0 - prev[1]) / d) if 0 < d < 0.5 else t
                ln = self._line.get(i)
                if ln and ln[0] == lc - 1 and t - self._lap_t.get(i, -1e9) > 3:
                    self._pend_lap[i] = (round(tc - ln[1], 3), t)   # no official time within 3 s: invalid
                self._line[i] = (lc, tc)
            elif prev and lc != prev[0]:
                self._line.pop(i, None)
            self._mark[i] = (lc, p, t)
        for i, (lt, t0) in list(self._pend_lap.items()):
            if t < t0:
                del self._pend_lap[i]
            elif t - t0 > 3:
                del self._pend_lap[i]
                push(i, lt, True)

        snum = raw.get("SessionNum")
        # a new session (another event, or practice -> qualify -> race) starts its own laps:
        # same track or not, nothing lap-related carries over
        sid = (self.meta.get("subId"), snum)
        if sid != self._sess_id:
            self._sess_id = sid
            self.fuel.reset()
            self.wx_hist.clear()   # weather is per session too (set by hand, or rain in one and not the next)
            self._wx_t = -1e9
            self._in_pit, self._out, self._pits, self._race_gaps = set(), {}, {}, {}
            self._flag_lap = None
            self._lap_sync = {}
            self._laps, self._seen_last, self._race_laps = {}, None, None
            self._lap_now = {}
            self._lap_seen = 0
            self._want, self._want_raw = None, None
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
        # how far behind live the sim is showing: 60 replay frames a second, counted from the end
        # (a saved replay has no live: what it plays is the race)
        saved_replay = bool(self.meta.get("replayFile"))
        replay_behind = (raw.get("ReplayFrameNumEnd") or 0) / 60.0 if raw.get("IsReplayPlaying") and not saved_replay else 0.0
        live = replay_behind <= 3 and not saved_replay
        true_state = int(raw.get("SessionState") or 0)
        ev_best = best
        # a race that ended, seen in the replay: the telemetry is that moment, the board is the result
        ended = (self.meta.get("subId"), snum)
        if kind == "race" and live and true_state >= 5:
            self._ended.add(ended)
        static = kind == "race" and not live and bool(sess.get("ResultsOfficial") or ended in self._ended)
        if static:
            raw = {**raw, "SessionState": 6}
            best = [v if (v := float((res.get(i) or {}).get("FastestTime") or -1)) > 0 else b for i, b in enumerate(best)]
            last = [v if (v := float((res.get(i) or {}).get("LastTime") or -1)) > 0 else x for i, x in enumerate(last)]
        is_race = kind == "race"
        flag = flag_name(raw.get("SessionFlags"))
        me = int(raw.get("PlayerCarIdx") if raw.get("PlayerCarIdx") is not None else self.player)
        # the car the sim is focused on (the reference driver): standings highlight, relative, deltas,
        # map and footer follow it. Mine in the car, whoever I watch otherwise. me stays the player:
        # fuel, pit, incidents and the lap log only exist for the player's own car
        cam = raw.get("CamCarIdx")
        # a finished race seen in the replay too: whoever is on camera is the reference, the footer stays mine
        foc = cam if cam in self.drivers else me
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
                    if idx not in self._in_pit and int(raw.get("SessionState") or 0) >= 4:   # last pit stop: lap it is on and pit road time; leaving for the grid isn't one
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

        tot = {}
        for i in present:
            laps = lapc[i] if lapc[i] is not None and lapc[i] > -2 else 0
            tot[i] = laps + max(0.0, pct[i]) + self.lap_fix(i, laps, pct[i], t)
            if lapc[i] is not None and lapc[i] >= 0:
                # really over the line: not a jump in the replay, not the lap it was on when the app opened
                was = self._lap_now.get(i)
                if was and lapc[i] == was[0] + 1 and 0 < t - was[1] < 3 and was[2] > .5 and 0 <= pct[i] < .5:
                    over = was[1] + (t - was[1]) * (1 - was[2]) / max(1e-6, 1 - was[2] + pct[i])
                    self.ev.laps.setdefault(raw.get("SessionNum") or 0, {}).setdefault(i, {}).setdefault(lapc[i] + 1, round(over, 3))
                self._lap_now[i] = (lapc[i], t, pct[i])

        # ordering. Race, while racing: live order by distance covered (laps + lap fraction), the
        # way overlays do it - CarIdxPosition only changes when a car crosses the line. Cars not
        # on track keep iRacing's position behind them. Otherwise iRacing's position when it has one.
        racing = is_race and int(raw.get("SessionState") or 0) == 4
        # after the checkered flag (5) and in the cool down (6): the official result, not where
        # the cars happen to be on track - SessionInfo's results, else iRacing's position
        finished = is_race and int(raw.get("SessionState") or 0) >= 5
        rpos = {i: int(res[i].get("Position") or 0) for i in present if res.get(i)}
        # race over (the board switches to the results): cool down, or I took the flag myself
        state = int(raw.get("SessionState") or 0)
        if not finished:
            self._flag_lap = None
            self._flag_laps, self._fin = {}, set()
        elif self._flag_lap is None and me < len(lapc):
            self._flag_lap = lapc[me]
        # who took the checkered flag: the winner (the flag comes out as they cross), whoever
        # crosses the line after it, iRacing's own per-car checkered bit, and in the cool down
        # everyone still classified as running
        if finished:
            if not self._flag_laps:
                self._flag_laps = {i: lapc[i] for i in present}
                first = next((i for i in present if rpos.get(i) == 1), None)
                if first is not None:
                    self._fin.add(first)
            for i in present:
                if (lapc[i] > self._flag_laps.get(i, lapc[i]) or int(cflags[i] or 0) & 0x1
                        or (state >= 6 and res.get(i) and int(res[i].get("ReasonOutId") or 0) == 0)):
                    self._fin.add(i)
        # (crossed the line after the flag, or already in the pits / out of the car: the
        # app may also only open once the flag is out)
        mine = me < len(lapc)
        over = is_race and (state >= 6 or (finished and (not mine or surf[me] in (-1, 1) or pitr[me] or (self._flag_lap is not None and lapc[me] > self._flag_lap))))
        if finished and any(pos[i] > 0 or rpos.get(i) for i in present):
            order = sorted(present, key=lambda i: (rpos.get(i) or (pos[i] if pos[i] > 0 else 999), i))
        elif racing and any(lapc[i] is not None and lapc[i] >= 0 and surf[i] >= 0 for i in present):
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

        my_cls = self.drivers.get(foc, {}).get("cls")
        ref = (class_best.get(my_cls) or best[foc] if foc < len(best) else 0) or 0
        if not ref or ref <= 0:
            ref = (self.classes.get(my_cls) or {}).get("est") or 100.0

        def lap_of(i):
            return self.drivers[i]["est"] or ref   # each car its own: inside a class they differ (BMW 134.1, Porsche 133.5 at Spa)

        def est_gap(a, b):
            """Fallback before the PassLog has data: seconds since car a (ahead) was where car b is.
            CarIdxEstTime follows the track's speed profile and each car's own lap; b's is rescaled to a's."""
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

        def result_gap(i, j):
            """After the flag: (laps_down, seconds) from the official results, None without them."""
            ri, rj = res.get(i) or {}, res.get(j) or {}
            if not ri or not rj:
                return None
            laps = int(rj.get("LapsComplete") or 0) - int(ri.get("LapsComplete") or 0)
            if laps >= 1:
                return laps, None
            ti, tj = float(ri.get("Time") or -1), float(rj.get("Time") or -1)
            return (0, round(max(0.0, ti - tj), 3)) if ti > 0 and tj > 0 else None

        def gap(i, j):
            """(laps_down, seconds) of car i relative to car j that is ahead of it."""
            if finished:
                return result_gap(i, j) or (None, None)
            diff = tot[j] - tot[i]
            laps = int(math.floor(diff + 1e-6))
            if laps >= 1:
                return laps, None
            if diff <= 0:
                return 0, 0.0
            s = f2[i] - f2[j] if f2 is not None and f2[i] > 0 else 0
            return 0, round(s if s > 0 else timed_gap(j, i), 3)   # the same gap iRacing shows; nothing yet: ours

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
                "lh": [x[0] for x in self._laps.get(i, ())],
                "lx": [x[1] for x in self._laps.get(i, ())],   # invalidated / with my incidents
                # last pit stop: lap, seconds on pit road, still there (pd counts up live)
                **({"pl": self._pits[i][0], "pd": round(self._pits[i][2] if self._pits[i][2] is not None else t - self._pits[i][1], 1),
                    "pip": self._pits[i][2] is None} if i in self._pits else {}),
                "cb": bool(best[i] > 0 and class_best.get(cid) == best[i]),
                "pb": bool(best[i] > 0 and last[i] > 0 and abs(last[i] - best[i]) < 1e-4),
                # took the checkered flag; in qualifying, done with the run (iRacing's per-car bit, or the session ended)
                "fin": i in self._fin or (kind == "qualify" and bool(int(cflags[i] or 0) & 0x1 or (state >= 5 and res.get(i)))),
            }
            h = self._laps.get(i)
            if h and h[0][1] and not pre_green:   # latest lap invalid: our own time, marked
                c["last"], c["lastx"], c["pb"] = h[0][0], True, False
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
                if racing:
                    self._race_gaps[i] = {f: c[f] for f in GAP_FIELDS}
                elif finished and any(c.get(f) is None for f in ("ld", "li", "lo", "lio")):
                    # no official times yet: the gaps as they were when the flag fell
                    c.update(self._race_gaps.get(i) or {f: None if f[0] == "g" else 0 for f in GAP_FIELDS})
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
        user_gain = None
        if is_race:
            byc = {c["i"]: c for c in cars}
            for g in groups.values():
                field = [(self.drivers[i]["ir"], cpos[i]) for i in g if cpos.get(i)]
                for i in g:
                    if cpos.get(i):
                        byc[i]["irg"] = ir_change(self.drivers[i]["ir"], cpos[i], field)
            ir_gain = byc.get(foc, {}).get("irg")
            user_gain = byc.get(me, {}).get("irg")

        # my lap log (test sessions): fuel is split at the line, the lap time arrives just after
        my_fuel = raw.get("FuelLevel")
        if lapc[me] != self._my_lapc:
            if self._my_lapc is not None and lapc[me] > (self._my_lapc or 0):
                used = (self._fuel_at_line - my_fuel) if self._fuel_at_line is not None and my_fuel is not None else None
                self._pending_lap = {"lap": lapc[me], "temp": raw.get("TrackTemp"), "fuel": my_fuel,
                                     "sn": raw.get("SessionNum") or 0, "end": raw.get("SessionTime"),
                                     "used": round(used, 3) if used is not None and used >= 0 else None}
            self._my_lapc, self._fuel_at_line = lapc[me], my_fuel
        mylast = raw.get("LapLastLapTime")
        if mylast != self._my_last:
            pend = getattr(self, "_pending_lap", None)
            if pend and mylast and mylast > 0:
                pend["time"] = round(mylast, 3)
                end = pend.pop("end", None)
                if end is not None:
                    pend["t0"] = round(end - mylast, 2)   # where it began in the replay: the lap counters don't match there
                self._mylaps.appendleft(pend)
                self._pending_lap = None
            self._my_last = mylast
        pend = getattr(self, "_pending_lap", None)
        mine_h = self._laps.get(me)
        if pend and pend.get("end") is not None and t - pend["end"] > 4 and mine_h and mine_h[0][1]:
            pend["time"], pend["inv"] = round(mine_h[0][0], 3), True
            pend["t0"] = round(pend.pop("end") - pend["time"], 2)
            self._mylaps.appendleft(pend)
            self._pending_lap = None

        # relative: everyone physically near the focused car, by iRacing's estimate, as its own Relative:
        # the elapsed time carries how slowly I came here (3 s more on an out lap)
        rel = []
        if foc in tot and surf[foc] >= 0 and pct[foc] >= 0:
            for i in present:
                if i == foc or surf[i] < 0 or pct[i] < 0:
                    continue
                dp = pct[i] - pct[foc]
                dp = (dp + 0.5) % 1.0 - 0.5
                dtm = est_gap(i, foc) if dp >= 0 else -est_gap(foc, i)
                # lap difference only means something in a race once it started (in practice everyone
                # is "laps ahead"; on the grid and the formation lap the cars cross the line at
                # different moments, but everybody is on the same lap)
                laps = int(round(tot[i] - tot[foc] - dp)) if is_race and not pre_green else 0
                rel.append({"i": i, "dt": round(dtm, 2), "dl": laps, "pit": bool(pitr[i]), "out": i in self._out, "fl": car_flag(cflags[i]), "srf": surf[i]})
            ahead = sorted([r for r in rel if r["dt"] >= 0], key=lambda r: r["dt"])[:8]
            behind = sorted([r for r in rel if r["dt"] < 0], key=lambda r: -r["dt"])[:8]
            rel = list(reversed(ahead)) + behind
        else:
            rel = []

        def pace(i):
            """A car's recent lap time: the middle of its latest valid laps (a pit lap counts as valid),
            else its best, else its class estimate."""
            h = [x[0] for x in self._laps.get(i, ()) if not x[1]]
            return median(h) if h else (best[i] if best[i] > 0 else lap_of(i))

        # fuel
        fuel_l = raw.get("FuelLevel")
        lap_t = self.fuel.avg_time or (best[me] if best[me] > 0 else None) or ref
        # (not flag: a black flag or the white one must not hide a caution)
        self.fuel.update(lapc[me], fuel_l, raw.get("LapLastLapTime"), bool(raw.get("OnPitRoad")),
                         "yellow" if int(raw.get("SessionFlags") or 0) & YELLOWS else flag, bool(raw.get("IsOnTrack")))
        avg = self.fuel.avg
        provisional = False
        if avg is None and (raw.get("FuelUsePerHour") or 0) > 1 and lap_t:
            avg, provisional = raw["FuelUsePerHour"] / self.kg_per_l * lap_t / 3600.0, True   # it comes in kg/h
        laps_total = raw.get("SessionLapsTotal") or 0
        laps_rem = raw.get("SessionLapsRemainEx") or 0
        time_total = raw.get("SessionTimeTotal") or 0
        time_rem = raw.get("SessionTimeRemain") or 0
        mypct = max(0.0, pct[me]) if me < len(pct) else 0.0
        mode, laps_left = "none", None
        lap_limit = laps_total if laps_total and laps_total < UNLIMITED_LAPS and laps_rem < UNLIMITED_LAPS else None
        time_limit = time_rem if time_total and time_total < UNLIMITED_TIME and time_rem < UNLIMITED_TIME and lap_t else None
        if lap_limit is not None or time_limit is not None:
            mode = "laps" if lap_limit is not None else "time"
            if is_race and order and me in tot:
                # by the leader, whose pace is what counts; under a caution the recent laps are the slow ones
                lead = order[0]
                lead_lap = lap_t if lead == me else pace(lead)
                # no valid lap of mine yet: the estimate is too quick (121 s against 133 at COTA), the leader tells more
                timed = any(not x[1] for x in self._laps.get(me, ()))
                my_lap = pace(me) if lead != me and timed else lead_lap
                if finished:
                    laps_left = math.ceil(mypct - 1e-6) - mypct
                else:
                    laps_left = laps_to_flag(tot[lead], lead_lap, tot[me], my_lap, lap_limit, time_limit)
                    short = laps_left * avg - fuel_l if avg and fuel_l is not None else 0
                    if short > 0:   # a stop to come puts me further back, and that can take a lap off my race
                        stops = math.ceil(short / self.tank) if self.tank else 1
                        laps_left = laps_to_flag(tot[lead], lead_lap, tot[me], my_lap, lap_limit, time_limit,
                                                 stops * PIT_LOSS)
            elif lap_limit is not None:
                laps_left = max(0.0, laps_rem - mypct)
            else:
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
            "lap": raw.get("Lap"), "pct": round(mypct, 4),
        }

        # pit: what is on the car and what is set for the next stop. iRacing has no forecast, so a
        # tyre change is offered when the weather turned against the tyres on the car: rain or a
        # wet track on dries, the rain gone on wets. Held 5 s, so a passing drizzle doesn't blink it.
        on = raw.get("PlayerTireCompound")
        on = on if on is not None and on >= 0 else (tyre[me] if me < len(tyre) else -1)
        self.tyre_on = self.tyres.get(on)
        rain = float(raw.get("Precipitation") or 0)
        want = None
        if len(set(self.tyres.values())) > 1:
            if self.tyre_on == "dry" and (rain > 0.02 or int(raw.get("TrackWetness") or 0) >= 4):
                want = "wet"
            elif self.tyre_on == "wet" and rain <= 0.01:
                want = "dry"
        if want != self._want_raw or t < self._want_t:
            self._want_raw, self._want_t = want, t
        if t - self._want_t >= 5:
            self._want = want
        on_pit = bool(raw.get("OnPitRoad"))
        self.pit_in = on_pit and not self._on_pit and racing
        self._on_pit = on_pit
        self._fuel_now = (fuel_l, self.fuel.avg, laps_left)
        pit = {
            "ok": bool(raw.get("IsOnTrack")),   # iRacing only takes pit commands from the car
            "tyre": self.tyre_on, "tyreSet": self.tyres.get(raw.get("PitSvTireCompound"), self.tyre_on),
            "want": self._want,
            "tyres": int(raw.get("PitSvFlags") or 0) & 0xF == 0xF,   # all four ticked for the next stop
            "fuel": round(raw.get("PitSvFuel") or 0, 1) if int(raw.get("PitSvFlags") or 0) & 0x10 else 0,
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
        if kind == "race" and true_state >= 5:   # the flag is out: iRacing's clock goes on for the cool down
            tr = 0.0
        elif kind == "race" and true_state == 1 and tr is not None and 0 < tr < UNLIMITED_TIME:
            pass   # get in the car: iRacing counts down to the grid closing
        elif kind == "race" and (true_state < 4 or (tr is not None and tr < 0)):   # before the green, and -1 on its first frame
            length = re.match(r"[\d.]+", str(sess.get("SessionTime") or ""))
            tr = float(length.group()) if length else time_total if 0 < time_total < UNLIMITED_TIME else tr

        # race length in laps, for the focused car: the race ends when the overall leader takes the flag, so
        # it is the leader's laps (exact in a lap race, estimated in a timed one: the lap running
        # when the clock hits zero is the last) minus how far behind it is, rounded up.
        # Frozen once the flag is out.
        if not is_race:
            self._race_laps = None
        elif not finished and order and foc in tot and surf[foc] >= 0:
            lead = order[0]
            d = max(0.0, tot[lead] - tot[foc])
            if laps_total and laps_total < UNLIMITED_LAPS:
                n = math.ceil(laps_total - d - 1e-6)
                self._race_laps = (n, n != laps_total)
            elif time_total and time_total < UNLIMITED_TIME and time_rem < UNLIMITED_TIME:
                lt = pace(lead)
                n = math.ceil(tot[lead] + max(0.0, time_rem) / lt - 1e-6) if lt else None
                self._race_laps = (math.ceil(n - d - 1e-6), True) if n else None
        race_laps = self._race_laps
        myh = self._laps.get(foc)
        my_lastx = bool(myh and myh[0][1])

        own = foc == me
        self._lap_seen = raw.get("Lap") or self._lap_seen   # the end of a race in the replay comes with 0

        self.in_car = bool(raw.get("IsOnTrack"))
        # in a replay SessionTime keeps being the live clock; the moment on screen is ReplaySessionTime
        replaying = bool(raw.get("IsReplayPlaying"))
        ev_t = (raw.get("ReplaySessionTime") or t) if replaying else t
        ev_num = raw.get("ReplaySessionNum") if replaying and (raw.get("ReplaySessionNum") or 0) >= 0 else snum
        watched = self.sessions.get(ev_num) if ev_num != snum else None   # a replay of another session
        ev_kind = session_kind((watched.get("SessionType") or "").strip()) if watched else kind
        ev_frame = SimpleNamespace(
            t=ev_t, sub=self.meta.get("subId"), snum=ev_num, kind=ev_kind, state=true_state, flags=int(raw.get("SessionFlags") or 0),
            me=me, present=present, cls={i: self.drivers[i]["cls"] for i in present}, tot=tot, pct=pct, surf=surf, pitr=pitr,
            best=ev_best, cflags=cflags, car_flag=car_flag, cpos={} if static else cpos, fin=set() if static else set(self._fin), inc=inc,
            laps_done=lambda i: (lapc[i] if lapc[i] is not None else -1), length=(self.meta.get("lengthKm") or 5.0) * 1000,
        )
        try:
            self.ev.feed(ev_frame)
        except Exception as exc:  # noqa: BLE001  - a wrong event must never cost the board in a race
            if not self.ev.failed:
                self.ev.failed = True
                print(f"[pitwall] events error: {exc!r}", flush=True)

        def mine_t(v, arr):
            if v and v > 0:
                return v
            return round(arr[foc], 3) if foc < len(arr) and arr[foc] > 0 else None

        return {
            "type": "state", "connected": True, "t": round(t, 2),
            "session": {
                "type": stype or "Session", "name": sess.get("SessionName") or stype,
                "isRace": is_race, "kind": kind, "state": int(raw.get("SessionState") or 0), "over": over, "static": static,
                "stateName": SESSION_STATE.get(int(raw.get("SessionState") or 0), ""),
                "flag": flag, "timeRemain": tr, "grid": kind == "race" and true_state == 1,
                "rflag": race_flag(raw.get("SessionFlags"), cflags[me] if me < len(cflags) else 0) if raw.get("IsOnTrack") else None,
                "timeTotal": time_total if time_total < UNLIMITED_TIME else None,
                "lapsRemain": laps_rem if laps_rem < UNLIMITED_LAPS else None,
                "lapsTotal": laps_total if laps_total < UNLIMITED_LAPS else None,
                # my race length in laps, and whether it is an estimate (timed race, or lapped)
                "raceLaps": race_laps[0] if race_laps else None, "raceLapsEst": bool(race_laps and race_laps[1]),
                "tod": raw.get("SessionTimeOfDay"), "replay": bool(raw.get("IsReplayPlaying")),
                "inCar": self.in_car, "behind": round(replay_behind, 1), "num": snum, "player": me,
                "units": "imperial" if raw.get("DisplayUnits") == 0 else "metric",
            },
            # the footer's driver: always the user, whoever is on camera
            "user": {
                "i": me, "lap": self._lap_seen, "inc": raw.get("PlayerCarMyIncidentCount"), "cur": raw.get("LapCurrentLapTime"),
                "delta": raw.get("LapDeltaToBestLap"), "deltaOk": bool(raw.get("LapDeltaToBestLap_OK")),
                "incPen": self.meta.get("incPen"), "incPenNext": self.meta.get("incPenNext"), "incDq": self.meta.get("incDq"),
                "irGain": user_gain,
            },
            "me": {
                "i": foc, "p": overall.get(foc), "cp": cpos.get(foc), "cls": self.drivers.get(foc, {}).get("cls"),
                "lap": self._lap_seen if own else (lapc[foc] or 0) + 1, "pct": pct[foc],
                # the player's own lap times reset once out of the car: then the car's (results) times
                "last": myh[0][0] if my_lastx else mine_t(raw.get("LapLastLapTime") if own else None, last), "lastx": my_lastx,
                "best": mine_t(raw.get("LapBestLapTime") if own else None, best),
                "cur": raw.get("LapCurrentLapTime"),
                "delta": raw.get("LapDeltaToBestLap"), "deltaOk": bool(raw.get("LapDeltaToBestLap_OK")),
                "speed": raw.get("Speed"), "gear": raw.get("Gear"), "rpm": raw.get("RPM"),
                "pit": bool(raw.get("OnPitRoad")), "inc": raw.get("PlayerCarMyIncidentCount") if own else None,   # nobody else's is known
                "incLimit": self.meta.get("incLimit"),
                "incPen": self.meta.get("incPen"), "incPenNext": self.meta.get("incPenNext"), "incDq": self.meta.get("incDq"),
                "irGain": ir_gain, "laps": list(self._mylaps),
            },
            "cars": cars, "rel": rel, "fuel": fuel, "pit": pit, "wx": wx,
            "talk": talk if talk is not None and talk >= 0 else None,   # car on the radio right now
            "cam": self._cam(raw),
            "map": {"status": self.mapper.status, "progress": round(self.mapper.progress, 3),
                    "ver": self.mapper.version},
        }
