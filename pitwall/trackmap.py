"""Builds a track outline from your own driving.

iRacing does not expose track coordinates through the telemetry API, so we
record them: during one clean lap we integrate Speed along the heading
(YawNorth), close the loop by spreading the end-point error over the lap and
resample the result by lap distance. The outline is cached in maps/ and reused
the next time you visit that track.

Before any lap, the outline comes from maps/library/<TrackID>.json when it exists
(built by tools/import_tracks.py from iRacing's own track drawings), so the map
and the turn numbers are there the moment you join. A lap you record wins over it.

iRacing's frame is right-handed with X forward / Y left, so positive yaw is a
left turn. Compared with iRacing's own drawings, the outline integrated with
(-sin(yaw), cos(yaw)) came out mirrored, so the x sign is inverted by default;
--flip-map turns it back.
"""
from __future__ import annotations

import json
import math
import re
import time
from bisect import bisect_left
from pathlib import Path


def calibrate(points, samples, max_shift=0.15):
    """Where pct 0 really is on a library outline.

    The start/finish point of iRacing's drawing is not always where LapDistPct is 0
    (COTA: ~5% of a lap off). samples are (pct, yaw) of my car driving; the outline's
    direction at pct+shift must match the car's heading up to one rotation (the drawing
    is not north-up) and maybe a mirror (yaw sign convention). Returns (shift, quality)
    with quality = mean resultant length in 0..1 (1 = every sample agrees)."""
    n = len(points)
    tang = []
    for i in range(n):
        (x0, y0), (x1, y1) = points[(i - 2) % n], points[(i + 2) % n]
        tang.append(math.atan2(y1 - y0, x1 - x0))
    best = (0.0, 0.0)
    for mirror in (1.0, -1.0):
        car = [(pct, math.atan2(math.cos(yaw), -mirror * math.sin(yaw))) for pct, yaw in samples]
        for k in range(-int(max_shift * n), int(max_shift * n) + 1):
            c = sn = 0.0
            for pct, a in car:
                d = tang[(int(pct * n) + k) % n] - a
                c += math.cos(d); sn += math.sin(d)
            r = math.hypot(c, sn) / len(car)
            if r > best[1]:
                best = (k / n, r)
    return best


class TrackMapper:
    N = 480  # points in the stored outline

    def __init__(self, maps_dir, flip: bool = False, library_dir=None):
        self.dir = Path(maps_dir)                     # writable: recorded laps, calibrations
        self.library = Path(library_dir) if library_dir else self.dir / "library"   # read-only is fine
        self.dir.mkdir(parents=True, exist_ok=True)
        self.flip = flip
        self.key = None
        self.points = None  # list[[x, y]] in metres, ordered by lap distance
        self.turns = []     # [[x, y, label]] in the same frame (library maps only)
        self.source = None  # "recorded" | "library"
        self.offset = 0.0   # library outlines: pct shift that puts LapDistPct 0 on the real line
        self._cal = []      # (pct, yaw) samples for the calibration
        self.version = 0
        self.status = "none"  # none | waiting | recording | ready
        self.progress = 0.0
        self._rec = None
        self._prev_pct = None

    # ---- persistence -------------------------------------------------------
    def _file(self):
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.key or "unknown")
        return self.dir / f"{safe}.json"

    def set_track(self, key: str, track_id=None):
        if key == self.key:
            return
        self.key = key
        self.track_id = track_id
        self.points = None
        self.turns = []
        self.source = None
        self._rec = None
        self._prev_pct = None
        self.progress = 0.0
        self.status = "waiting"
        f = self._file()
        if f.exists():
            try:
                data = json.loads(f.read_text())
                pts = data.get("points")
                if pts and len(pts) > 50:
                    self.points = pts
                    self.status = "ready"
                    self.source = "recorded"
            except Exception:  # noqa: BLE001
                pass
        self._load_library()
        self.version += 1

    def _load_library(self):
        """The library outline (official drawing): used when no lap was recorded, and its
        turn labels only when it is also the outline shown (they share its frame)."""
        if self.points is not None or self.track_id is None:
            return
        f = self.library / f"{self.track_id}.json"
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if len(data.get("points") or []) > 50:
            self.points, self.turns = data["points"], data.get("turns") or []
            self.status, self.source = "ready", "library"
            self._cal = []
            try:   # offset found on an earlier visit
                self.offset = float(json.loads(self._cal_file().read_text())["offset"])
                self._calibrated = True
            except (OSError, ValueError, KeyError):
                self.offset, self._calibrated = 0.0, False

    def _cal_file(self):
        return self.dir / f"offset-{self.track_id}.json"   # next to recorded maps: writable

    def _calibrate(self, pct, heading, speed, on_track, in_pit):
        """Collect my heading along the lap; once a good part of the lap is covered, solve the offset."""
        if self._calibrated or not on_track or in_pit or speed < 12:
            return
        self._cal.append((pct, heading))
        covered = len({int(p * 50) for p, _ in self._cal})   # 2% buckets of the lap
        if covered < 15 or len(self._cal) % 200:
            return
        step = max(1, len(self._cal) // 400)   # <= 400 samples keeps the solve ~50 ms on the server loop
        shift, quality = calibrate(self.points, self._cal[::step])
        if quality > 0.9:
            self.offset, self._calibrated = round(shift, 4), True
            self.version += 1
            try:
                self._cal_file().write_text(json.dumps({"offset": self.offset, "quality": round(quality, 3)}))
            except OSError:
                pass

    def reset(self):
        """Forget the stored map for the current track and record a new one."""
        try:
            self._file().unlink()
        except FileNotFoundError:
            pass
        self.points = None
        self.turns = []
        self.source = None
        self._rec = None
        self.status = "waiting"
        self.progress = 0.0
        self.version += 1

    # ---- recording ---------------------------------------------------------
    def update(self, dt: float, speed: float, heading: float, pct: float, on_track: bool, in_pit: bool):
        if self.source == "library":
            self._calibrate(pct, heading, speed, on_track, in_pit)
        if self.key is None or self.points is not None:   # recorded or library outline already there
            return
        prev, self._prev_pct = self._prev_pct, pct
        if prev is None:
            return
        wrapped = prev > 0.9 and pct < 0.1
        usable = on_track and not in_pit and speed > 3.0 and 0 < dt < 0.5

        if self._rec is None:
            self.status = "waiting"
            if wrapped and usable:
                self._rec = {"x": 0.0, "y": 0.0, "last": pct, "s": [(0.0, 0.0, 0.0)]}
                self.status = "recording"
                self.progress = 0.0
            return

        rec = self._rec
        if wrapped:
            self._finish()
            return
        if not usable or pct < rec["last"] - 0.02:  # off track, pits, spin, rewind
            self._rec = None
            self.status = "waiting"
            self.progress = 0.0
            return
        sx = 1.0 if self.flip else -1.0   # recorded COTA came out mirrored with the other sign
        rec["x"] += sx * -math.sin(heading) * speed * dt
        rec["y"] += math.cos(heading) * speed * dt
        rec["last"] = pct
        rec["s"].append((pct, rec["x"], rec["y"]))
        self.progress = pct

    def _finish(self):
        samples = self._rec["s"]
        self._rec = None
        if len(samples) < 200:
            self.status = "waiting"
            return
        # pct must be non-decreasing and without holes
        samples.sort(key=lambda s: s[0])
        gaps = max(b[0] - a[0] for a, b in zip(samples, samples[1:]))
        if gaps > 0.04 or samples[-1][0] < 0.95:
            self.status = "waiting"
            return
        ex, ey = samples[-1][1], samples[-1][2]
        # spread the closing error over the lap (drift is roughly proportional to distance)
        corrected = [(p, x - ex * p, y - ey * p) for p, x, y in samples]
        ps = [c[0] for c in corrected]
        out = []
        for i in range(self.N):
            target = i / self.N
            j = bisect_left(ps, target)
            if j <= 0:
                out.append((corrected[0][1], corrected[0][2]))
            elif j >= len(corrected):
                out.append((corrected[-1][1], corrected[-1][2]))
            else:
                a, b = corrected[j - 1], corrected[j]
                w = (target - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 0.0
                out.append((a[1] + (b[1] - a[1]) * w, a[2] + (b[2] - a[2]) * w))
        smooth = []
        for i in range(self.N):  # light circular smoothing
            px, py = out[(i - 1) % self.N]
            cx, cy = out[i]
            nx, ny = out[(i + 1) % self.N]
            smooth.append([round((px + 2 * cx + nx) / 4, 1), round((py + 2 * cy + ny) / 4, 1)])
        self.points = smooth
        self.turns = []
        self.source = "recorded"
        self.status = "ready"
        self.progress = 1.0
        self.version += 1
        try:
            self._file().write_text(json.dumps({"key": self.key, "created": time.time(), "points": smooth}))
        except OSError:
            pass
