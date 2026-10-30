"""Build the track-map library from the irdashies track drawings.

    python tools/import_tracks.py path/to/tracks.json [maps/library]

irdashies (MIT, github.com/tariknz/irdashies) ships tracks.json: for every iRacing
TrackID the outline taken from iRacing's own track SVGs (trackPathPoints), the
start/finish point, the driving direction and the turn labels. This turns each one
into maps/library/<TrackID>.json in our format: N points ordered by lap distance
from the start/finish line in the driving direction (so they line up with
LapDistPct), y pointing up, plus turn labels in the same frame. With it the map is
there the moment you join a session, no lap needed.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

N = 480


def resample(path, start, n=N):
    """n points evenly spaced by arc length along the closed path, starting at index start."""
    pts = path[start:] + path[:start]
    pts.append(pts[0])
    seg = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
    total = sum(seg)
    out, k, acc = [], 0, 0.0
    for i in range(n):
        target = total * i / n
        while k < len(seg) - 1 and acc + seg[k] < target:
            acc += seg[k]
            k += 1
        w = (target - acc) / seg[k] if seg[k] else 0.0
        a, b = pts[k], pts[k + 1]
        out.append((a[0] + (b[0] - a[0]) * w, a[1] + (b[1] - a[1]) * w))
    return out


def convert(entry):
    raw = (entry.get("active") or {}).get("trackPathPoints") or entry.get("trackPathPoints") or []
    sf = (entry.get("startFinish") or {}).get("point")
    if len(raw) < 50 or not sf:
        return None
    path = [(float(p["x"]), float(p["y"])) for p in raw]
    numbered = sorted(((float(t["x"]), float(t["y"]), int(t["content"])) for t in entry.get("turns") or []
                       if str(t.get("content", "")).strip().isdigit()), key=lambda t: t[2])

    def build(path):
        start = min(range(len(path)), key=lambda i: (path[i][0] - sf["x"]) ** 2 + (path[i][1] - sf["y"]) ** 2)
        return resample(path, start)

    def turn_order(pts):
        """Share of consecutive turn numbers that go forward around the lap from the line."""
        n = len(pts)
        at = [min(range(n), key=lambda i: (pts[i][0] - x) ** 2 + (pts[i][1] - y) ** 2) / n for x, y, _ in numbered]
        return sum((b - a) % 1 < 0.5 for a, b in zip(at, at[1:])) / max(1, len(at) - 1)

    # Driving direction: turn 1, 2, 3... follow the start/finish line in the direction of the lap,
    # so pick the way round where they come in order. The file's "direction" only decides when
    # there are too few numbered turns (it does not always mean the racing direction).
    fwd, rev = build(path), build(path[::-1])
    if len(numbered) >= 3:
        pts = fwd if turn_order(fwd) >= turn_order(rev) else rev
    else:
        area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(path, path[1:] + path[:1]))   # SVG y-down: > 0 clockwise
        want_cw = (entry.get("startFinish") or {}).get("direction", "clockwise") == "clockwise"
        pts = fwd if (area > 0) == want_cw else rev
    # some drawings split a number into one text per digit ("11" = "1" + "1"): glue digits that sit
    # side by side on the same line back together, left to right
    digits = sorted(([float(t["x"]), float(t["y"]), str(t.get("content", "")).strip()] for t in entry.get("turns") or []
                     if str(t.get("content", "")).strip().isdigit()), key=lambda t: t[0])
    merged = []
    for t in digits:
        last = merged[-1] if merged else None
        if last and abs(last[1] - t[1]) < 4 and 0 < t[0] - last[3] < 22:
            last[2] += t[2]; last[3] = t[0]
        else:
            merged.append([t[0], t[1], t[2], t[0]])
    turns = [[round((m[0] + m[3]) / 2, 1), round(-m[1], 1), m[2]] for m in merged]   # numbered only: names clutter
    return {"points": [[round(x, 1), round(-y, 1)] for x, y in pts], "turns": turns, "source": "irdashies"}


def main():
    src = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent.parent / "maps" / "library"
    out.mkdir(parents=True, exist_ok=True)
    data = json.loads(src.read_text(encoding="utf-8"))
    ok = bad = 0
    for track_id, entry in data.items():
        conv = convert(entry or {})
        if conv is None:
            bad += 1
            continue
        (out / f"{track_id}.json").write_text(json.dumps(conv), encoding="utf-8")
        ok += 1
    print(f"{ok} tracks written to {out} ({bad} skipped: no outline or start/finish)")


if __name__ == "__main__":
    main()
