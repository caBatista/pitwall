"""Telemetry sources.

Both sources expose the same tiny interface so the engine does not care where
the numbers come from:

    poll()                 -> dict of iRacing variables, or None when not connected
    session_info(raw)      -> dict(WeekendInfo, DriverInfo, SessionInfo) when it
                              changed since the last call, otherwise None
"""
from __future__ import annotations

import math
import random
import time

# Everything the engine needs, nothing more: fewer reads per tick = lower CPU.
SCALARS = [
    "SessionTime", "SessionNum", "SessionState", "SessionFlags",
    "SessionTimeRemain", "SessionLapsRemainEx", "SessionLapsTotal",
    "SessionTimeTotal", "SessionTimeOfDay", "SessionInfoUpdate",
    "PlayerCarIdx", "IsOnTrack", "OnPitRoad", "Lap", "LapCompleted", "RadioTransmitCarIdx",
    "LapDistPct", "LapDeltaToBestLap", "LapDeltaToBestLap_OK",
    "LapBestLapTime", "LapLastLapTime", "LapCurrentLapTime",
    "Speed", "Gear", "RPM", "FuelLevel", "FuelLevelPct", "FuelUsePerHour",
    "PlayerCarMyIncidentCount", "DisplayUnits", "IsReplayPlaying",
    "YawNorth",
    "TrackTemp", "TrackTempCrew", "AirTemp", "TrackWetness", "Skies",
    "AirPressure", "RelativeHumidity", "WindVel", "WindDir", "Precipitation",
    "FogLevel", "SolarAltitude", "WeatherDeclaredWet",
]
CAR_ARRAYS = [
    "CarIdxLapCompleted", "CarIdxLapDistPct", "CarIdxTrackSurface",
    "CarIdxOnPitRoad", "CarIdxPosition", "CarIdxClassPosition",
    "CarIdxLastLapTime", "CarIdxBestLapTime", "CarIdxEstTime", "CarIdxSessionFlags", "CarIdxTireCompound",
]


class IRacingSource:
    """Reads the live iRacing shared memory through pyirsdk."""

    name = "iRacing"

    def __init__(self):
        try:
            import irsdk  # noqa: WPS433
        except ImportError:  # pragma: no cover
            raise SystemExit("pyirsdk is not installed. Run: pip install -r requirements.txt")
        self.ir = irsdk.IRSDK()
        self._info_tick = None

    def poll(self):
        ir = self.ir
        if not ir.is_connected:
            if ir.is_initialized:
                ir.shutdown()  # sim was closed: drop the stale mapping and retry
            self._info_tick = None
            try:
                ir.startup()
            except Exception:  # noqa: BLE001
                return None
            if not ir.is_connected:
                return None
        ir.freeze_var_buffer_latest()
        try:
            raw = {}
            for key in SCALARS + CAR_ARRAYS:
                try:
                    raw[key] = ir[key]
                except Exception:  # noqa: BLE001
                    raw[key] = None
            # not a telemetry var: it lives in the shared-memory header
            raw["SessionInfoUpdate"] = ir._header.session_info_update
        finally:
            ir.unfreeze_var_buffer_latest()
        return raw

    def session_info(self, raw):
        tick = raw.get("SessionInfoUpdate")
        if tick == self._info_tick:
            return None
        self._info_tick = tick
        info = {}
        for key in ("WeekendInfo", "DriverInfo", "SessionInfo", "SplitTimeInfo", "QualifyResultsInfo"):
            try:
                info[key] = self.ir[key]
            except Exception:  # noqa: BLE001
                info[key] = None
        return info


# --------------------------------------------------------------------------- #
#  Simulator: a multiclass race on a made-up circuit.                          #
#  It produces the same variables as iRacing, including Speed/YawNorth that    #
#  are consistent with the circuit geometry, so the track recorder is tested.  #
# --------------------------------------------------------------------------- #

_FIRST = ["Lucas", "Mateus", "Rafael", "Enzo", "Pedro", "Thiago", "Diego", "Andre", "Bruno", "Caio",
          "Felipe", "Gustavo", "Hugo", "Igor", "Joao", "Kleber", "Leo", "Marcos", "Nuno", "Otavio",
          "Paulo", "Rui", "Sergio", "Tomas", "Vitor", "Yuri", "Zeca"]
_LAST = ["Silva", "Costa", "Pereira", "Ramos", "Duarte", "Moura", "Nunes", "Rocha", "Teixeira", "Vidal",
         "Campos", "Lopes", "Barros", "Freitas", "Garcia", "Mendes", "Pinto", "Reis", "Souza", "Tavares"]
_CLASSES = [
    # id, short name, car name, colour, speed factor, count, tank (L), burn (L/lap)
    (4001, "LMP2", "Oreca 07", 0xB066FF, 1.085, 5, 75.0, 2.5),
    (4002, "GT3", "Porsche 992 GT3 R", 0xFFCD3C, 1.000, 14, 110.0, 3.1),
    (4003, "GT4", "BMW M4 GT4", 0x3CC8FF, 0.905, 7, 100.0, 2.7),
]


class MockSource:
    name = "simulator"

    def __init__(self, speed: float = 4.0, seed: int = 11, session: str = "Race", track_id: int = 9999):
        self.speed = max(0.1, speed)
        self.seed = seed
        self.track_id = track_id   # a real TrackID makes the map come from maps/library
        self.session = session   # iRacing SessionType to pretend: Race / Open Qualify / Practice / Offline Testing
        self._reset()

    # ---- construction ------------------------------------------------------
    def _reset(self):
        self.rng = random.Random(self.seed)
        self._build_track()
        self._build_cars()
        self.t = 0.0
        self._wall = time.perf_counter()
        self._sent_info = False
        self.race_len = 3600.0

    def _build_track(self):
        n = 2400
        raw = []
        for i in range(n):
            a = 2 * math.pi * i / n
            x = 1000 * math.cos(a) + 260 * math.cos(3 * a + 0.6) + 90 * math.sin(5 * a + 0.3)
            y = 620 * math.sin(a) + 180 * math.sin(2 * a + 1.2) + 70 * math.cos(4 * a)
            raw.append((x, y))
        # resample to equal arc length so that "lap distance" really is distance
        cum = [0.0]
        for i in range(n):
            cum.append(cum[-1] + math.dist(raw[i], raw[(i + 1) % n]))
        length = cum[-1]
        k = 5400.0 / length
        eq, j = [], 0
        for i in range(n):
            target = length * i / n
            while cum[j + 1] < target:
                j += 1
            w = (target - cum[j]) / (cum[j + 1] - cum[j])
            a, b = raw[j], raw[(j + 1) % n]
            eq.append(((a[0] + (b[0] - a[0]) * w) * k, (a[1] + (b[1] - a[1]) * w) * k))
        self.pts = eq
        self.L = 5400.0
        self.n = n
        step = self.L / n
        hd = []
        for i in range(n):
            dx = self.pts[(i + 1) % n][0] - self.pts[i][0]
            dy = self.pts[(i + 1) % n][1] - self.pts[i][1]
            hd.append(math.atan2(-dx, dy))
        # curvature -> corner speed -> accel/brake limited profile
        kap = []
        for i in range(n):
            d = hd[(i + 3) % n] - hd[(i - 3) % n]
            d = (d + math.pi) % (2 * math.pi) - math.pi
            kap.append(abs(d) / (6 * step))
        v = [max(26.0, min(84.0, math.sqrt(15.0 / max(k_, 1e-4)))) for k_ in kap]
        for _ in range(2):
            for i in range(n * 2):
                j = i % n
                nxt = (j + 1) % n
                v[nxt] = min(v[nxt], math.sqrt(v[j] ** 2 + 2 * 7.5 * step))
            for i in range(n * 2):
                j = (n - 1 - i) % n
                prv = (j - 1) % n
                v[prv] = min(v[prv], math.sqrt(v[j] ** 2 + 2 * 13.0 * step))
        self.hd = hd
        self.v = v

    def _at(self, arr, pct):
        f = (pct % 1.0) * self.n
        i = int(f) % self.n
        j = (i + 1) % self.n
        w = f - int(f)
        if arr is self.hd:
            d = (arr[j] - arr[i] + math.pi) % (2 * math.pi) - math.pi
            return arr[i] + d * w
        return arr[i] * (1 - w) + arr[j] * w

    def _build_cars(self):
        rng = self.rng
        used = set()
        self.cars = []
        idx = 0
        grid = 0
        order = [(c, i) for c in _CLASSES for i in range(c[5])]
        rng.shuffle(order)
        # the player is car 0 and drives a GT3
        order.sort(key=lambda ci: 0 if (ci[0][0] == 4002 and ci[1] == 0) else 1)
        for cls, _ in order:
            while True:
                name = f"{rng.choice(_FIRST)} {rng.choice(_LAST)}"
                if name not in used:
                    used.add(name)
                    break
            you = idx == 0
            ir = rng.randint(1100, 6800)
            lic = "A 3.41" if ir > 4500 else ("B 2.80" if ir > 2200 else "C 3.12")
            self.cars.append({
                "idx": idx,
                "name": "Caio Batista" if you else name,
                "num": str(64 if you else rng.randint(2, 98)),
                "cls": cls,
                "ir": 1990 if you else ir,
                "lic": "B 2.85" if you else lic,
                "skill": cls[4] * (1.0 + rng.gauss(0, 0.010)),
                "wob": rng.uniform(0, 6.28),
                "d": -0.0045 * grid - 0.002,  # grid slot, in laps
                "fuel": cls[6] * rng.uniform(0.55, 0.9) if not you else 62.0,
                "pit": None, "pit_t": 0.0,
                "t_lap": 0.0, "last": -1.0, "best": -1.0,
                "pits": 0, "inc": 0,
            })
            idx += 1
            grid += 1

    # ---- iRacing-like interface -------------------------------------------
    def session_info(self, raw):
        if self._sent_info:
            return None
        self._sent_info = True
        drivers = []
        for c in self.cars:
            drivers.append({
                "CarIdx": c["idx"], "UserName": c["name"], "TeamName": c["name"],
                "CarNumber": c["num"], "CarClassID": c["cls"][0],
                "CarClassShortName": c["cls"][1], "CarScreenNameShort": c["cls"][2],
                "CarClassColor": c["cls"][3], "CarClassEstLapTime": 100.0 / c["cls"][4],
                "IRating": c["ir"], "LicString": c["lic"],
                "LicColor": "0xfc8a27" if c["lic"][0] == "B" else ("0x0153db" if c["lic"][0] == "A" else "0xfeec04"),
                "IsSpectator": 0, "CarIsPaceCar": 0, "CarIsAI": 0,
            })
        drivers.append({"CarIdx": 63, "UserName": "Pace Car", "CarIsPaceCar": 1, "CarClassID": 0})
        return {
            "WeekendInfo": {
                "TrackID": self.track_id, "TrackName": "pitwall test", "TrackDisplayName": "Pitwall Test Circuit",
                "TrackConfigName": "Grand Prix", "TrackLength": "5.40 km", "TrackNumTurns": 16,
                "Category": "SportsCar", "SeriesID": 0,
                "WeekendOptions": {"IncidentLimit": 25, "IncidentWarningInitialLimit": 17, "IncidentWarningSubsequentLimit": 8},
            },
            "SplitTimeInfo": {"Sectors": [{"SectorNum": 0, "SectorStartPct": 0.0}, {"SectorNum": 1, "SectorStartPct": 0.34},
                                          {"SectorNum": 2, "SectorStartPct": 0.68}]},
            "DriverInfo": {
                "DriverCarIdx": 0, "DriverCarFuelMaxLtr": 110.0, "DriverCarMaxFuelPct": 1.0,
                "DriverCarEstLapTime": 100.0, "Drivers": drivers,
            },
            "SessionInfo": {"Sessions": [
                {"SessionNum": 0, "SessionType": self.session, "SessionName": self.session.upper(),
                 "SessionTrackRubberState": "moderate usage",
                 "SessionLaps": "unlimited", "SessionTime": f"{self.race_len:.4f} sec"},
            ]},
        }

    def poll(self):
        now = time.perf_counter()
        dt = min(0.25, now - self._wall) * self.speed
        self._wall = now
        self.t += dt
        if self.t > self.race_len + 600:
            self._reset()
            return self.poll()
        self._step(dt)
        return self._snapshot()

    # ---- simulation --------------------------------------------------------
    def _yellow(self):
        return 1500 < self.t < 1620

    def _step(self, dt):
        slow = 0.62 if self._yellow() else 1.0
        finished = self.t >= self.race_len
        for c in self.cars:
            cls = c["cls"]
            pct = c["d"] % 1.0
            if c["pit"] is None:
                base = self._at(self.v, pct) * c["skill"] * slow
                base *= 1.0 + 0.012 * math.sin(self.t / 37.0 + c["wob"])
                if self.t < 8:  # rolling start: stay in formation
                    base = min(base, 38.0)
                v = base
            else:
                v = 20.0  # pit-lane speed limit
                if c["pit"] == "stall":
                    v = 0.0
                    c["pit_t"] -= dt
                    if c["pit_t"] <= 0:
                        c["pit"] = "exit"
                        c["fuel"] = cls[6] * 0.97
            c["v"] = v
            nd = c["d"] + v * dt / self.L
            # lap bookkeeping
            if math.floor(nd) > math.floor(c["d"]) and c["d"] >= 0:
                lt = self.t - c["t_lap"]
                if random.random() < 0.1:   # invalidated lap (track limits): no time, like iRacing
                    c["last"] = -1.0
                else:
                    c["last"] = lt
                    if c["best"] < 0 or lt < c["best"]:
                        c["best"] = lt
                c["t_lap"] = self.t
                if self.rng.random() < 0.012:
                    c["inc"] += self.rng.choice([1, 2, 4])
            elif c["d"] < 0 <= nd:
                c["t_lap"] = self.t
            c["d"] = nd
            # fuel & pit logic
            c["fuel"] = max(0.0, c["fuel"] - (cls[7] * (0.45 if self._yellow() else 1.0)) * v * dt / self.L
                            if c["pit"] is None else c["fuel"])
            pct = c["d"] % 1.0
            if c["pit"] is None and c["fuel"] < cls[7] * 1.6 and 0.965 < pct < 0.99 and c["d"] > 0:
                c["pit"] = "enter"
            elif c["pit"] == "enter" and pct < 0.5 and pct >= 0.0 and (c["d"] % 1.0) < 0.02:
                c["pit"] = "stall"
                c["pit_t"] = 22.0
                c["pits"] += 1
            elif c["pit"] == "exit" and 0.03 < pct < 0.5:
                c["pit"] = None
        self._finished = finished

    def _snapshot(self):
        n = 64
        lapc = [-1] * n
        pct = [-1.0] * n
        surf = [-1] * n
        pitr = [0] * n
        pos = [0] * n
        cpos = [0] * n
        last = [-1.0] * n
        best = [-1.0] * n
        est = [0.0] * n
        started = self.t > 2
        ranked = sorted(self.cars, key=lambda c: -c["d"])
        cls_rank = {}
        for k, c in enumerate(ranked):
            pos[c["idx"]] = k + 1 if started else 0
            cls_rank[c["cls"][0]] = cls_rank.get(c["cls"][0], 0) + 1
            cpos[c["idx"]] = cls_rank[c["cls"][0]] if started else 0
        for c in self.cars:
            i = c["idx"]
            lapc[i] = math.floor(c["d"])
            pct[i] = c["d"] % 1.0
            surf[i] = 1 if c["pit"] == "stall" else (2 if c["pit"] else 3)
            pitr[i] = 1 if c["pit"] else 0
            last[i] = c["last"]
            best[i] = c["best"]
            est[i] = pct[i] * 100.0 / c["cls"][4]
        me =self.cars[0]
        mp = me["d"] % 1.0
        pit = me["pit"] is not None
        speed = me.get("v", 0.0)
        cur = self.t - me["t_lap"]
        remain = max(0.0, self.race_len - self.t)
        t = self.t
        rain = max(0.0, min(0.75, (t - 1900) / 500)) if t < 2800 else max(0.0, 0.75 - (t - 2800) / 700)
        wet = 1 + int(round(rain * 7)) if rain > 0.02 else 1
        air = 24.0 + 1.2 * math.sin(t / 1900.0) - 4.0 * rain
        track = air + 13.0 + 2.5 * math.sin(t / 700.0) - 14.0 * rain
        flags = 0x4
        if self._yellow():
            flags = 0x8 | 0x4000
        if t >= self.race_len:
            flags = 0x1
        raw = {
            "SessionTime": t, "SessionNum": 0, "SessionState": 5 if t >= self.race_len else (3 if t < 8 else 4),
            "SessionFlags": flags, "SessionTimeRemain": remain, "SessionLapsRemainEx": 32767,
            "SessionLapsTotal": 32767, "SessionTimeTotal": self.race_len,
            "SessionTimeOfDay": 12 * 3600 + t, "SessionInfoUpdate": 1, "PlayerCarIdx": 0,
            "IsOnTrack": True, "OnPitRoad": pit, "Lap": max(0, lapc[0] + 1), "LapCompleted": lapc[0],
            "LapDistPct": mp, "LapDeltaToBestLap": 0.35 * math.sin(t / 9.0) + 0.12 * math.sin(t / 2.3),
            "LapDeltaToBestLap_OK": me["best"] > 0, "LapBestLapTime": me["best"],
            "LapLastLapTime": me["last"], "LapCurrentLapTime": cur, "Speed": speed,
            "Gear": 0 if speed < 1 else max(1, min(6, int(speed / 14) + 1)),
            "RPM": 3500 + (speed % 14) * 400, "FuelLevel": me["fuel"],
            "FuelLevelPct": me["fuel"] / 110.0, "FuelUsePerHour": 0.0 if speed < 1 else 3.1 * speed / self.L * 3600,
            "PlayerCarMyIncidentCount": me["inc"], "DisplayUnits": 1, "IsReplayPlaying": False,
            "YawNorth": self._at(self.hd, mp) if not pit else self._at(self.hd, mp),
            "TrackTemp": track, "TrackTempCrew": track - 0.6, "AirTemp": air,
            "TrackWetness": wet, "Skies": 1 if rain < 0.05 else (2 if rain < 0.3 else 3),
            "AirPressure": 101300.0 - 150 * math.sin(t / 3000.0), "RelativeHumidity": 0.48 + 0.4 * rain,
            "WindVel": 3.4 + 1.6 * math.sin(t / 500.0), "WindDir": (1.1 + t / 2400.0) % (2 * math.pi),
            "Precipitation": rain, "FogLevel": 0.0, "SolarAltitude": 0.9 - t / 20000.0,
            "WeatherDeclaredWet": rain > 0.25,
            "CarIdxLapCompleted": lapc, "CarIdxLapDistPct": pct, "CarIdxTrackSurface": surf,
            "CarIdxOnPitRoad": pitr, "CarIdxPosition": pos, "CarIdxClassPosition": cpos,
            "CarIdxLastLapTime": last, "CarIdxBestLapTime": best,
            "CarIdxEstTime": est,
        }
        return raw
