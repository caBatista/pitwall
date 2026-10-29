"""Builds a track outline from your own driving.

iRacing does not expose track coordinates through the telemetry API, so we
record them: during one clean lap we integrate Speed along the heading
(YawNorth), close the loop by spreading the end-point error over the lap and
resample the result by lap distance. The outline is cached in maps/ and reused
the next time you visit that track.

iRacing's frame is right-handed with X forward / Y left, so positive yaw is a
left turn. With north = +Y and east = +X, the heading vector is
(-sin(yaw), cos(yaw)). If a map ever shows up mirrored, start with --flip-map.
"""
from __future__ import annotations

import json
import math
import re
import time
from bisect import bisect_left
from pathlib import Path


class TrackMapper:
    N = 480  # points in the stored outline

    def __init__(self, maps_dir, flip: bool = False):
        self.dir = Path(maps_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.flip = flip
        self.key = None
        self.points = None  # list[[x, y]] in metres, ordered by lap distance
        self.version = 0
        self.status = "none"  # none | waiting | recording | ready
        self.progress = 0.0
        self._rec = None
        self._prev_pct = None

    # ---- persistence -------------------------------------------------------
    def _file(self):
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.key or "unknown")
        return self.dir / f"{safe}.json"

    def set_track(self, key: str):
        if key == self.key:
            return
        self.key = key
        self.points = None
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
            except Exception:  # noqa: BLE001
                pass
        self.version += 1

    def reset(self):
        """Forget the stored map for the current track and record a new one."""
        try:
            self._file().unlink()
        except FileNotFoundError:
            pass
        self.points = None
        self._rec = None
        self.status = "waiting"
        self.progress = 0.0
        self.version += 1

    # ---- recording ---------------------------------------------------------
    def update(self, dt: float, speed: float, heading: float, pct: float, on_track: bool, in_pit: bool):
        if self.key is None or self.points is not None:
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
        sx = -1.0 if self.flip else 1.0
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
        self.status = "ready"
        self.progress = 1.0
        self.version += 1
        try:
            self._file().write_text(json.dumps({"key": self.key, "created": time.time(), "points": smooth}))
        except OSError:
            pass
