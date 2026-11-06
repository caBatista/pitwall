"""Moving the camera in iRacing's camera tool. The SDK opens the tool, picks a camera and drives the replay,
but it has no command to move a camera: that is only keys, held down in the tool.

Keys go straight to the sim's window as messages, so it doesn't need the focus: the mouse is on Pitwall's
stick the whole time. Seen in the sim, 2026-11-05, reading the values in its camera panel: W/A/S/D move, Ctrl
gives yaw and pitch, [ and ] the field of view; Alt only counts as a plain key (WM_KEYDOWN), not as the
system key Windows would send.

The keys are on or off and the stick isn't: the key is held for a share of each PERIOD, as far as the stick
is pushed. If the app stops saying what it wants (DEADMAN), everything lets go by itself: a key left down
would keep the camera flying.
"""
from __future__ import annotations

import ctypes
import threading
import time

from . import chat, keymap

CTRL, ALT, SHIFT = (0x11, 0x1D), (0x12, 0x38), (0x10, 0x2A)
W, A, S, D = (0x57, 0x11), (0x41, 0x1E), (0x53, 0x1F), (0x44, 0x20)
OPEN, CLOSE = (0xDB, 0x1A), (0xDD, 0x1B)   # [ ]
AXES = {   # name: (modifier, key)
    "lon+": (None, W), "lon-": (None, S), "lat+": (None, A), "lat-": (None, D),
    "alt+": (ALT, W), "alt-": (ALT, S), "yaw+": (CTRL, A), "yaw-": (CTRL, D),
    "pitch+": (CTRL, S), "pitch-": (CTRL, W), "roll+": (ALT, D), "roll-": (ALT, A),
    "fov+": (None, CLOSE), "fov-": (None, OPEN),   # ] opens the field of view: seen in the sim, 37.12 -> 37.25
}
TAPS = {   # once, not held
    "hide": (None, (0x20, 0x39)),   # Space. Not the state's bit: any cam_set_state throws away what the keys moved (seen in the sim)
    "car+": (None, (0x56, 0x2F)), "car-": (SHIFT, (0x56, 0x2F)),   # V: goes by the track, and works where the telemetry has no cars
}
# what each one is called in iRacing's controls file: these are defaults, the user's own keys come first (keymap.py)
CONTROLS = {
    "lon+": "CamLongInc", "lon-": "CamLongDec", "lat+": "CamLatInc", "lat-": "CamLatDec", "alt+": "CamAltInc", "alt-": "CamAltDec",
    "yaw+": "CamYawInc", "yaw-": "CamYawDec", "pitch+": "CamPitchInc", "pitch-": "CamPitchDec", "roll+": "CamRollInc", "roll-": "CamRollDec",
    "fov+": "CamFOVInc", "fov-": "CamFOVDec", "hide": "ToggleUIVisible", "car+": "FocusNextCar", "car-": "FocusPrevCar",
}
SCENIC, TOOL, HIDE, TEMPORARY = 0x2, 0x4, 0x8, 0x20   # CameraState bits. SCENIC: iRacing holds the view, nothing picks a camera
KEY_ACCEL = 0x40              # the tool's acceleration holds a key back for the first ~0.5 s: seen in the sim
WRITABLE = 0x1FC                         # what a broadcast can change


def binding(name, default, keys=None):
    """(modifier, key) the user has for this: one modifier, the only way these keys are pressed."""
    found = (keymap.current() if keys is None else keys).get(CONTROLS[name])
    if not found:
        return default
    mods, vk = found
    mod = ALT if mods & 0x30 else CTRL if mods & 0x0C else SHIFT if mods & 0x03 else None
    return mod, (vk, ctypes.windll.user32.MapVirtualKeyW(vk, 0))


def post_key(down, key):
    """One key message to the sim's window, wherever the focus is."""
    hwnd = chat.sim_window()
    if hwnd:
        vk, scan = key
        flags = 1 | (scan << 16) | (0 if down else 0xC0000000)
        ctypes.windll.user32.PostMessageW(hwnd, 0x100 if down else 0x101, vk, flags)


class CamKeys:
    PERIOD = 0.12
    TICK = 0.03
    DEADMAN = 0.4
    HOLD = 0.05
    FULL = 0.95   # from here on the key just stays down

    def __init__(self, send=post_key, clock=time.monotonic, keys=None):
        self._send, self._clock, self._keys = send, clock, keys
        self._want, self._seen = {}, 0.0
        self._down, self._mod = set(), None
        self._lock = threading.Lock()
        self._thread = None

    def drive(self, axes):
        """What the stick asks for now, {axis: 0..1}. Only one modifier at a time: the strongest wins."""
        want = {}
        for k, v in (axes or {}).items():
            if k in AXES and isinstance(v, (int, float)) and v > 0:
                want[k] = min(1.0, float(v))
        with self._lock:
            self._want, self._seen = want, self._clock()
        if want and not (self._thread and self._thread.is_alive()):
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def tap(self, name):
        if name in TAPS:
            threading.Thread(target=self._tap, args=(name,), daemon=True).start()   # never holds the frame loop

    def _tap(self, name):
        """With time between the keys: the sim reads them once a frame, and a modifier let go in the same frame is
        not seen, so Shift+V was just V."""
        mod, key = binding(name, TAPS[name], self._keys)
        if mod:
            self._send(True, mod)
            time.sleep(self.HOLD)
        self._send(True, key)
        time.sleep(self.HOLD)
        self._send(False, key)
        if mod:
            time.sleep(self.HOLD)
            self._send(False, mod)

    def _run(self):
        while self.step():
            time.sleep(self.TICK)

    def step(self):
        """One tick. False: nothing is held any more."""
        now = self._clock()
        with self._lock:
            want = dict(self._want) if now - self._seen <= self.DEADMAN else {}
        table = {k: binding(k, AXES[k], self._keys) for k in want}
        mod = table[max(want, key=want.get)][0] if want else None
        want = {k: v for k, v in want.items() if table[k][0] == mod}
        phase = (now % self.PERIOD) / self.PERIOD
        press = {table[k][1] for k, v in want.items() if v >= self.FULL or phase < v}
        for key in self._down - press:
            self._send(False, key)
        if mod != self._mod:
            if self._mod:
                self._send(False, self._mod)
            if mod:
                self._send(True, mod)
            self._mod = mod
        for key in press:
            self._send(True, key)
        self._down = press
        return bool(want)
