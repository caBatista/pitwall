"""Back to full screen: when the sim takes the focus while in a window, press Alt+Enter once.

Only the moment it gets the focus counts, so a window asked for on purpose stays until the next time
the focus comes back. A window is one with a title bar that doesn't fill its monitor: seen in iRacing,
a maximized sim window has a title bar too, and the keys would take a full-screen sim out of it.
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

from .chat import INPUT_KEYBOARD, KEYUP, _api, _exe, _Input, _Key, _Union

POLL = 0.5     # s between looks at the window in front
SETTLE = 0.4   # s it has to stay in front: alt-tabbing past it isn't focusing on it
HOLD = 0.06    # s between key events: sent all at once the sim doesn't see them (tested in iRacing)
GWL_STYLE, WS_CAPTION = -16, 0x00C00000
MONITOR_DEFAULTTONEAREST = 2
enabled = True   # Settings > General
only_car = False   # ...or only with the driver in the car
in_car = False    # from the server, each frame
ALT, ENTER = (0x12, 0x38), (0x0D, 0x1C)   # virtual key, scan code: the sim may read either


class _Monitor(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("rect", wintypes.RECT), ("work", wintypes.RECT), ("flags", wintypes.DWORD)]


def is_sim(hwnd) -> bool:
    u, k = _api()
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return _exe(k, pid.value).lower().startswith("iracingsim")


def is_windowed(hwnd) -> bool:
    u, _ = _api()
    u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    u.GetWindowLongW.restype = ctypes.c_long
    u.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    u.MonitorFromWindow.restype = wintypes.HMONITOR
    u.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_Monitor)]
    u.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    if u.GetWindowLongW(hwnd, GWL_STYLE) & WS_CAPTION != WS_CAPTION:
        return False
    info, client = _Monitor(size=ctypes.sizeof(_Monitor)), wintypes.RECT()
    if not u.GetMonitorInfoW(u.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST), ctypes.byref(info)):
        return False
    if not u.GetClientRect(hwnd, ctypes.byref(client)):
        return False
    m = info.rect
    return (client.right, client.bottom) != (m.right - m.left, m.bottom - m.top)


def _send(key):
    u, _ = _api()
    event = _Input(type=INPUT_KEYBOARD, u=_Union(ki=key))
    u.SendInput(1, ctypes.byref(event), ctypes.sizeof(_Input))


def press_alt_enter(send=_send, wait=time.sleep):
    down = [_Key(vk=vk, scan=scan) for vk, scan in (ALT, ENTER)]
    up = [_Key(vk=vk, scan=scan, flags=KEYUP) for vk, scan in (ENTER, ALT)]
    for key in down + up:
        send(key)
        wait(HOLD)


class Watch:
    """Decides; the Windows calls come from outside so this can run without a sim."""

    def __init__(self, front, sim, windowed, press, wait=time.sleep):
        self.front, self.sim, self.windowed, self.press, self.wait = front, sim, windowed, press, wait
        self.last = front()   # already in front when the app opens: not a change of focus

    def step(self):
        hwnd = self.front()
        if hwnd == self.last:
            return
        self.last = hwnd
        if not hwnd or not self.sim(hwnd) or not self.windowed(hwnd):
            return
        self.wait(SETTLE)
        if self.front() == hwnd and self.windowed(hwnd):
            self.press()


def watch():
    """Runs for as long as the app does. Pitwall keeps working if this can't."""
    try:
        u, _ = _api()
        w = Watch(u.GetForegroundWindow, is_sim, is_windowed, press_alt_enter)
        was = False
        while True:
            time.sleep(POLL)
            if enabled and (in_car or not only_car):
                if only_car and not was:
                    w.last = None   # getting in the car counts as the sim taking the focus
                w.step()
            was = in_car
    except Exception as e:  # noqa: BLE001
        print(f"[simwindow] stopped: {e!r}", flush=True)
