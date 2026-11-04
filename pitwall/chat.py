"""Writing in the iRacing chat box: the SDK can open it, but not put text in it, so that's keystrokes.
Nothing is typed unless the sim's own window took the focus: anywhere else they'd land in another app."""
from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes

ULONG_PTR = ctypes.c_size_t


class _Key(ctypes.Structure):
    _fields_ = [("vk", wintypes.WORD), ("scan", wintypes.WORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("extra", ULONG_PTR)]


class _Mouse(ctypes.Structure):   # the biggest member: it sets the size of INPUT
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("data", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD), ("extra", ULONG_PTR)]


class _Union(ctypes.Union):
    _fields_ = [("ki", _Key), ("mi", _Mouse)]


class _Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _Union)]


INPUT_KEYBOARD, KEYUP, UNICODE = 1, 0x2, 0x4
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SW_RESTORE = 9


def _api():
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    u.GetForegroundWindow.restype = wintypes.HWND
    u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    u.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_Input), ctypes.c_int]
    for fn in (u.IsWindowVisible, u.IsIconic, u.SetForegroundWindow):
        fn.argtypes = [wintypes.HWND]
    u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    k.OpenProcess.restype = wintypes.HANDLE
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    k.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    return u, k


def _exe(k, pid) -> str:
    h = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf, size = ctypes.create_unicode_buffer(512), wintypes.DWORD(512)
        return os.path.basename(buf.value) if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)) else ""
    finally:
        k.CloseHandle(h)


def sim_window():
    """The visible window of the sim's process (iRacingSim64DX11.exe), or None."""
    u, k = _api()
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if u.IsWindowVisible(hwnd) and _exe(k, pid.value).lower().startswith("iracingsim"):
            found.append(hwnd)
            return False
        return True

    u.EnumWindows(each, 0)
    return found[0] if found else None


def focus_sim() -> bool:
    """Bring the sim to the front. Windows only lets the foreground process do it (the app is, it was
    just clicked); from a browser, borrow the foreground thread's input state."""
    hwnd = sim_window()
    if not hwnd:
        return False
    u, k = _api()
    if u.IsIconic(hwnd):
        u.ShowWindow(hwnd, SW_RESTORE)
    u.SetForegroundWindow(hwnd)
    if u.GetForegroundWindow() != hwnd:
        me, fg = k.GetCurrentThreadId(), u.GetWindowThreadProcessId(u.GetForegroundWindow(), None)
        u.AttachThreadInput(me, fg, True)
        u.SetForegroundWindow(hwnd)
        u.AttachThreadInput(me, fg, False)
    time.sleep(0.05)
    return u.GetForegroundWindow() == hwnd


def type_text(text: str):
    """Send text as characters, whatever the keyboard layout. Only into the sim."""
    u, _ = _api()
    hwnd = sim_window()
    if not hwnd or u.GetForegroundWindow() != hwnd:
        return
    units = text.encode("utf-16-le")
    keys = []
    for n in range(0, len(units), 2):
        code = int.from_bytes(units[n:n + 2], "little")
        for flags in (UNICODE, UNICODE | KEYUP):
            keys.append(_Input(type=INPUT_KEYBOARD, u=_Union(ki=_Key(scan=code, flags=flags))))
    u.SendInput(len(keys), (_Input * len(keys))(*keys), ctypes.sizeof(_Input))
