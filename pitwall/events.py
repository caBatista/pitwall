"""Race events: what happened in the session, each with the moment to go and see it in the replay.

The engine feeds this every frame with what it already worked out. Nothing here costs much on a quiet
frame: passes are only looked for when the order inside a class changes.

It always reads what iRacing is showing, live or replay, a saved one included: in a replay the
telemetry is that moment of the race, so what plays gets detected like the rest. Seeing a stretch
twice doesn't list it twice, and a jump in time takes new baselines, so it doesn't read as events.
What happens live while the driver watches the past isn't seen, and only shows up if it gets played.

Accidents: 1x stays out of them. Mine are exact and instant. Everyone else's points are in the session
results (ResultsPositions[].Incidents, seen in an official session), which come when iRacing updates the
session info, so late: the moment comes from the slowdown that went before them, a car far under the
pace of its class at that point of the track. With no results yet (first lap of a race) the slowdown
alone is the accident, estimated: est True, 4x with someone right there, 2x otherwise.
"""
from __future__ import annotations

import json
import os
from types import SimpleNamespace

MAX_EVENTS = 6000
REPLAY_LEAD = 5.0     # the replay starts this many seconds before the event
PASS_HOLD = 2.5       # a pass counts once it lasted this long: side by side the order flips back and forth
FIGHT_GAP = 5.5       # m between two cars of the same class on the same lap: alongside, a car length
FIGHT_MIN = 1.0       # s alongside for it to be a fight
FIGHT_END = 2.0       # s apart: it ended, and whoever is still ahead held the position
ACC_BINS = 100        # points of the lap the class pace is kept for
ACC_RATIO = 0.45      # this far under the pace of the class there, twice in a row: an accident
ACC_FAST = 15.0       # m/s: a pace under this says nothing (hairpin, or no data yet)
ACC_COOLDOWN = 15.0   # s, per car: it stays slow for a while
ACC_NEAR = 15.0       # m: somebody this close at that moment: contact
EXACT_WINDOW = 180.0  # s: the results arrive late; a slowdown this recent is when it happened
SAME_EVENT = 3.0      # s: same event, same cars, this close in time: seen twice
SEEK = 5.0            # s skipped between two frames: a jump in the replay, not racing
PASS_COOLDOWN = 6.0   # same two cars, again this soon: the same fight
PIT_GRACE = 8.0       # just out of the pits: rejoining in front of someone is not a pass
OFF_MIN = 1.0         # s off track for it to count; a wheel over the kerb doesn't
OFF_COOLDOWN = 5.0
STOP_SECS = 3.0       # s without moving, on track
STOP_DIST = 0.0008    # of a lap
STOP_GRACE = 30.0     # s after the green: the start has its slow cars
NEAR_PCT = 0.0025     # of a lap, ~13 m on a 5 km track: who was next to me at an incident
CAUTION = 0x4000 | 0x8000   # caution, caution waving; the plain yellow bits are local and constant
RED = 0x10
ON_TRACK, OFF_TRACK = 3, 0


class EventLog:
    def __init__(self):
        self.sub = None
        self.items, self.new, self.by_id = [], [], {}
        self.cleared = False   # the list went away (another event): clients start over
        self.failed = False    # feed raised once: told in the log
        self.ver = 0
        self._next = 0
        self._seen = {}   # what is listed, for a replay seen twice
        self._saved = None   # what load() found, until the sub-session is known
        self._f = None
        self._new_session(None, None)

    def _new_session(self, sid, snum):
        self.sid, self.snum = sid, snum
        self.kind = None
        self._base = None   # the first frame only takes notes
        self._lap = 0
        self._green_t = None

    def _baseline(self, f):
        self._base = True
        self._f = f
        self._state, self._flags = f.state, f.flags
        self._inc = f.inc
        self._best = {i: f.best[i] for i in f.present if f.best[i] > 0}
        self._cbest = {}
        for i, b in self._best.items():
            c = f.cls[i]
            self._cbest[c] = min(b, self._cbest.get(c, b))
        self._top = {i: (f.laps.get(i) or (None,))[0] for i in f.present}
        self._seq, self._pending, self._pair_t, self._fight = {}, {}, {}, {}
        self._pace, self._acc_pos, self._acc_low, self._acc_t, self._slow = {}, {}, {}, {}, {}
        self._counts = dict(f.counts)   # what is already there isn't news
        self._pit = {i: bool(f.pitr[i]) for i in f.present}
        self._pit_in, self._pit_out = {}, {}
        self._surf = {i: f.surf[i] for i in f.present}
        self._off, self._off_t = {}, {}
        self._anchor, self._stopped, self._sample = {}, set(), f.t
        self._cflag = {i: f.car_flag(f.cflags[i]) for i in f.present}
        self._fin = set(f.fin)
        self._t = f.t
        self._acc_s = f.t

    def lap_of(self, i):
        """The lap this car is on."""
        n = self._f.laps_done(i) if i is not None and self._f else -1
        return n + 1 if n >= 0 else None

    def add(self, t, kind, **fields):
        fields.setdefault("cl", self.lap_of(fields.get("i")))
        fields.setdefault("cj", self.lap_of(fields.get("j")))
        key = (self.snum, kind, fields.get("i"), fields.get("j"), fields.get("v"))
        times = self._seen.setdefault(key, [])
        if any(abs(t - x) < SAME_EVENT for x in times):   # the same one, seen again in the replay
            return None
        times.append(t)
        e = {"id": self._next, "t": round(t, 2), "sn": self.snum, "sk": self.kind, "k": kind, "lap": self._lap, **fields}
        self._next += 1
        self.items.append(e)
        self.by_id[e["id"]] = e
        self.new.append(e)
        self.ver += 1
        if len(self.items) > MAX_EVENTS:
            del self.by_id[self.items.pop(0)["id"]]
        return e

    def save(self, path):
        """Kept on disk so that restarting the app mid-event doesn't lose the list."""
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"sub": self.sub, "items": self.items}, fh)
        os.replace(tmp, path)

    def load(self, path):
        try:
            with open(path, encoding="utf-8") as fh:
                self._saved = json.load(fh)
        except (OSError, ValueError):
            self._saved = None

    def _restore(self, items):
        self.items = items[-MAX_EVENTS:]
        self.by_id = {e["id"]: e for e in self.items}
        self._next = max(self.by_id, default=-1) + 1
        for e in self.items:
            self._seen.setdefault((e["sn"], e["k"], e.get("i"), e.get("j"), e.get("v")), []).append(e["t"])

    def drain(self):
        new, self.new = self.new, []
        return new

    def replay_target(self, event_id):
        """(session, ms, car) to show this event, or None. car: None keeps the camera."""
        e = self.by_id.get(event_id)
        if not e:
            return None
        return e["sn"], int(max(0.0, e.get("at", e["t"]) - REPLAY_LEAD) * 1000), e.get("i")

    # ---- every frame ------------------------------------------------------
    def feed(self, f: SimpleNamespace):
        if f.sub != self.sub:
            self.sub = f.sub
            self.items, self.new, self.by_id = [], [], {}
            self._seen = {}
            saved, self._saved = self._saved, None
            if saved and saved.get("sub") == f.sub:
                self._restore(saved.get("items") or [])
            self.cleared = True
            self.ver += 1
            self.sid = None
        sid = (f.sub, f.snum)
        if sid != self.sid:
            self._new_session(sid, f.snum)
        self.kind = f.kind
        if self._base and not -1 <= f.t - self._t <= SEEK:   # time jumped: a replay
            self._base = None
        self._f = f
        my = f.laps_done(f.me)
        self._lap = my + 1 if my >= 0 else self._lap
        if not self._base:
            self._baseline(f)
            return
        self._t = f.t
        self._session_flags(f)
        self._incidents(f)
        for i in f.present:
            self._car(f, i)
        self._laps(f)
        self._exact_incidents(f)
        if f.kind == "race" and f.state == 4:
            self._passes(f)
            if f.t - self._acc_s >= 0.5:
                self._accidents(f, f.t - self._acc_s)
                self._acc_s = f.t
        else:
            self._acc_s = f.t
        if f.t - self._sample >= 1.0:
            self._sample = f.t
            self._stops(f)

    def _session_flags(self, f):
        if f.kind == "race":
            if self._state < 4 <= f.state:
                self._green_t = f.t
                self.add(f.t, "green")
            if self._state < 5 <= f.state:
                self.add(f.t, "chequered")
        rising = f.flags & ~self._flags
        if rising & CAUTION and not self._flags & CAUTION:
            self.add(f.t, "caution")
        if self._flags & CAUTION and not f.flags & CAUTION:
            self.add(f.t, "clear")
        if rising & RED:
            self.add(f.t, "red")
        self._state, self._flags = f.state, f.flags
        for i in f.fin - self._fin:
            self.add(f.t, "finish", i=i, p=f.cpos.get(i))
        self._fin |= f.fin

    def _incidents(self, f):
        if f.inc is None or self._inc is None or f.inc <= self._inc:
            self._inc = f.inc if f.inc is not None else self._inc
            return
        near, gap = None, NEAR_PCT
        for i in f.present:
            if i != f.me and f.surf[i] >= 0 and f.pct[i] >= 0:
                d = abs(f.pct[i] - f.pct[f.me]) % 1.0
                d = min(d, 1.0 - d)
                if d < gap:
                    near, gap = i, d
        self.add(f.t, "inc", i=f.me, n=f.inc - self._inc, total=f.inc, j=near)
        self._inc = f.inc

    def _car(self, f, i):
        s, p = f.surf[i], bool(f.pitr[i])
        # off track, once it lasted
        if s == OFF_TRACK and not p:
            t0 = self._off.setdefault(i, f.t)
            if t0 and f.t - t0 >= OFF_MIN:
                if f.t - self._off_t.get(i, -1e9) > OFF_COOLDOWN and f.kind != "test":
                    self.add(t0, "off", i=i)
                self._off[i] = 0   # told: not again until back on track
                self._off_t[i] = f.t
        else:
            self._off.pop(i, None)
        if f.kind == "race":
            was_pit = self._pit.get(i, False)
            if p and not was_pit:
                self._pit_in[i] = (f.t, self._lap, self.lap_of(i))   # told when the stop ends, listed when it began
            elif was_pit and not p:
                began = self._pit_in.pop(i, None)
                if s >= 0 and began:
                    self.add(began[0], "pit", i=i, d=round(f.t - began[0], 1), lap=began[1], cl=began[2])
                    self._pit_out[i] = f.t
            if f.state == 4 and s < 0 <= self._surf.get(i, -1):
                self.add(f.t, "out", i=i)
        self._pit[i] = p
        self._surf[i] = s
        # black flag, meatball, slow down, DQ: when it comes up
        cf = f.car_flag(f.cflags[i])
        if cf and cf != self._cflag.get(i):
            self.add(f.t, "pen", i=i, f=cf)
        self._cflag[i] = cf

    def _laps(self, f):
        if f.kind == "race" and f.state < 4:   # before the green Fastest shows the qualifying laps
            return
        for i in f.present:
            top = (f.laps.get(i) or (None,))[0]
            if top is not self._top.get(i):
                self._top[i] = top
                if top and top[1]:
                    self.add(f.t, "inv", i=i)
            b = f.best[i]
            prev = self._best.get(i)
            if b <= 0 or (prev is not None and b >= prev - 1e-4):
                continue
            self._best[i] = b
            c = f.cls[i]
            cb = self._cbest.get(c)
            fastest = cb is None or b < cb - 1e-4
            if fastest:
                self._cbest[c] = b
            at = f.t - b   # the lap from its start
            if f.kind == "qualify":
                rank = 1 + sum(1 for k, x in self._best.items() if f.cls[k] == c and x < b)
                self.add(f.t, "q", i=i, v=round(b, 3), p=rank, pole=fastest, at=round(at, 2))
            elif fastest and cb is not None:
                self.add(f.t, "fast", i=i, v=round(b, 3), at=round(at, 2))
            elif prev is not None:
                self.add(f.t, "pb", i=i, v=round(b, 3), at=round(at, 2))

    def _ok_for_pass(self, f, i):
        return f.surf[i] in (ON_TRACK, OFF_TRACK) and not f.pitr[i] and f.laps_done(i) >= 0 \
            and f.t - self._pit_out.get(i, -1e9) > PIT_GRACE

    def _passes(self, f):
        groups = {}
        for i in f.present:
            if self._ok_for_pass(f, i):
                groups.setdefault(f.cls[i], []).append(i)
        for c, cars in groups.items():
            cars.sort(key=lambda i: -f.tot[i])
            self._alongside(f, cars)
            seq = tuple(cars)
            old = self._seq.get(c)
            if old != seq:
                self._seq[c] = seq
                if old:
                    was = {i: k for k, i in enumerate(old)}
                    for k, a in enumerate(seq):
                        for b in seq[k + 1:]:
                            if a in was and b in was and was[a] > was[b]:
                                self._pending.setdefault((a, b), f.t)
        self._fights_over(f)
        for (a, b), t0 in list(self._pending.items()):
            if not (self._ok_for_pass(f, a) and self._ok_for_pass(f, b)) or f.tot[a] <= f.tot[b]:
                del self._pending[(a, b)]
            elif f.t - t0 >= PASS_HOLD:
                del self._pending[(a, b)]
                pair = (min(a, b), max(a, b))
                if t0 - self._pair_t.get(pair, -1e9) >= PASS_COOLDOWN:
                    self.add(t0, "pass", i=a, j=b, p=f.cpos.get(a))
                self._pair_t[pair] = t0

    def _alongside(self, f, cars):
        """Two cars side by side for a moment: an attack and a defence, even if nothing changed in the end."""
        for a, b in zip(cars, cars[1:]):
            if (f.tot[a] - f.tot[b]) * f.length <= FIGHT_GAP:
                r = self._fight.setdefault((min(a, b), max(a, b)), {"t0": f.t, "front": a, "lap": self._lap, "at": {a: self.lap_of(a), b: self.lap_of(b)}})
                r["last"] = f.t

    def _fights_over(self, f):
        for pair, r in list(self._fight.items()):
            if f.t - r["last"] < FIGHT_END:
                continue
            del self._fight[pair]
            a, b = pair
            if r["last"] - r["t0"] < FIGHT_MIN or not (self._ok_for_pass(f, a) and self._ok_for_pass(f, b)):
                continue
            front = a if f.tot[a] > f.tot[b] else b
            if front == r["front"]:   # (if not, it was a pass, and that has its own event)
                back = a if front == b else b
                self.add(r["t0"], "fight", i=back, j=front, d=round(r["last"] - r["t0"], 1), lap=r["lap"], cl=r["at"][back], cj=r["at"][front])

    def _exact_incidents(self, f):
        """Everyone else's points, from the session results."""
        for i, n in f.counts.items():
            was = self._counts.get(i, 0)
            self._counts[i] = n
            if n - was >= 2 and i != f.me:
                s = self._slow.pop(i, None)
                t, near, lap = s if s and f.t - s[0] < EXACT_WINDOW else (f.t, None, self.lap_of(i))
                self.add(t, "acc", i=i, j=near, x=n - was, est=False, cl=lap)

    def _accidents(self, f, dt):
        """A car far under the pace of the class at that point of the track: when, and who was there."""
        if f.flags & CAUTION or not f.length:
            self._acc_pos = {}
            return
        for i in f.present:
            old, p = self._acc_pos.get(i), f.pct[i]
            if not self._ok_for_pass(f, i) or i == f.me:
                self._acc_pos.pop(i, None)
                self._acc_low.pop(i, None)
                continue
            self._acc_pos[i] = p
            if old is None:
                continue
            v = ((p - old) % 1.0) * f.length / dt
            pace = self._pace.setdefault(f.cls[i], {})
            b = int(p * ACC_BINS) % ACC_BINS
            ref = pace.get(b)
            slow = bool(ref and ref > ACC_FAST and v < ACC_RATIO * ref)
            if not slow:
                pace[b] = v if ref is None else ref + 0.2 * (v - ref)
                self._acc_low.pop(i, None)
                continue
            first = self._acc_low.setdefault(i, f.t)
            if first != f.t and f.t - self._acc_t.get(i, -1e9) > ACC_COOLDOWN:
                self._acc_t[i] = f.t
                near, gap = None, ACC_NEAR / f.length
                for k in f.present:
                    if k != i and f.surf[k] >= 0 and not f.pitr[k] and f.pct[k] >= 0:
                        d = abs(f.pct[k] - p) % 1.0
                        d = min(d, 1.0 - d)
                        if d < gap:
                            near, gap = k, d
                self._slow[i] = (first, near, self.lap_of(i))
                if not f.counts_known:
                    self.add(first, "acc", i=i, j=near, x=4 if near is not None else 2, est=True)

    def _stops(self, f):
        racing = f.kind == "race" and f.state == 4 and self._green_t is not None and f.t - self._green_t > STOP_GRACE
        for i in f.present:
            if not racing or f.surf[i] not in (ON_TRACK, OFF_TRACK) or f.pitr[i]:
                self._anchor.pop(i, None)
                self._stopped.discard(i)
                continue
            a = self._anchor.get(i)
            if a is None or abs(f.pct[i] - a[1]) % 1.0 > STOP_DIST:
                self._anchor[i] = (f.t, f.pct[i])
                self._stopped.discard(i)
            elif f.t - a[0] >= STOP_SECS and i not in self._stopped:
                self._stopped.add(i)
                self.add(a[0], "stop", i=i)
