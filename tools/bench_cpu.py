"""CPU of the desktop app: python tools/bench_cpu.py [--rounds 4] [--secs 40]

The same script every time: mock at 1x, 26 cars, full screen. Each
sample is the CPU time of the whole process tree (python + WebView2) over --secs, after --warm, in %
of one core. A sample is thrown away if our window was not the one showing at the end: an occluded
WebView2 stops painting and would read as a miracle.
"""
from __future__ import annotations

import argparse
import csv
import ctypes
import os
import statistics
import subprocess
import sys
import time
from ctypes import wintypes as w
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
u32 = ctypes.WinDLL("user32")


class PE(ctypes.Structure):
    _fields_ = [("dwSize", w.DWORD), ("cntUsage", w.DWORD), ("pid", w.DWORD), ("heap", ctypes.c_size_t), ("mod", w.DWORD),
                ("threads", w.DWORD), ("ppid", w.DWORD), ("pri", w.LONG), ("flags", w.DWORD), ("exe", ctypes.c_char * 260)]


k32.CreateToolhelp32Snapshot.restype = w.HANDLE
k32.OpenProcess.restype = w.HANDLE
k32.GetProcessTimes.argtypes = [w.HANDLE] + [ctypes.POINTER(w.FILETIME)] * 4
k32.CloseHandle.argtypes = [w.HANDLE]
k32.Process32First.argtypes = k32.Process32Next.argtypes = [w.HANDLE, ctypes.POINTER(PE)]


def procs() -> dict[int, tuple[int, bytes]]:
    snap = k32.CreateToolhelp32Snapshot(2, 0)
    e = PE(); e.dwSize = ctypes.sizeof(PE)
    out = {}
    ok = k32.Process32First(snap, ctypes.byref(e))
    while ok:
        out[e.pid] = (e.ppid, e.exe)
        ok = k32.Process32Next(snap, ctypes.byref(e))
    k32.CloseHandle(snap)
    return out


def tree(root: int) -> list[int]:
    ps, seen, todo = procs(), [], [root]
    while todo:
        p = todo.pop()
        seen.append(p)
        todo += [c for c, (pp, _) in ps.items() if pp == p and c not in seen]
    return seen


def cpu_s(pid: int) -> float:
    h = k32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return 0.0
    a, b, c, d = w.FILETIME(), w.FILETIME(), w.FILETIME(), w.FILETIME()
    ok = k32.GetProcessTimes(h, ctypes.byref(a), ctypes.byref(b), ctypes.byref(c), ctypes.byref(d))
    k32.CloseHandle(h)
    if not ok:
        return 0.0
    return ((c.dwHighDateTime << 32 | c.dwLowDateTime) + (d.dwHighDateTime << 32 | d.dwLowDateTime)) / 1e7


def total(pids: list[int]) -> dict[int, float]:
    return {p: cpu_s(p) for p in pids}


def in_front(root: int) -> bool:
    """Is our window the one showing at its own centre? (Not the focused one: Windows won't give focus
    to a window that opens by itself, and focus doesn't matter for painting. Any monitor counts.)"""
    pids = set(tree(root))
    found = []
    def each(hwnd, _):
        pid = w.DWORD()
        u32.GetWindowThreadProcessId(w.HWND(hwnd), ctypes.byref(pid))
        if pid.value in pids and u32.IsWindowVisible(w.HWND(hwnd)) and u32.GetWindowTextLengthW(w.HWND(hwnd)):
            found.append(hwnd)
        return True
    u32.EnumWindows(ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)(each), 0)
    u32.WindowFromPoint.argtypes = [w.POINT]
    u32.WindowFromPoint.restype = w.HWND
    u32.GetAncestor.argtypes = [w.HWND, w.UINT]
    u32.GetAncestor.restype = w.HWND
    for hwnd in found:
        r = w.RECT()
        u32.GetWindowRect(w.HWND(hwnd), ctypes.byref(r))
        top = u32.GetAncestor(u32.WindowFromPoint(w.POINT((r.left + r.right) // 2, (r.top + r.bottom) // 2)), 2)
        pid = w.DWORD()
        u32.GetWindowThreadProcessId(w.HWND(top), ctypes.byref(pid))
        if pid.value in pids:
            return True
    return False


def sample(theme: str, secs: float, warm: float) -> tuple[float | None, bool]:
    exe = Path(sys.executable).with_name("pythonw.exe")
    pr = subprocess.Popen([str(exe), "-m", "pitwall.desktop", "--mock", "--speed", "1", "--mock-start", "60"], cwd=ROOT)
    try:
        time.sleep(warm)
        pids = tree(pr.pid)
        t0, c0 = time.perf_counter(), total(pids)
        time.sleep(secs)
        c1 = total(pids)
        dt = time.perf_counter() - t0
        front = in_front(pr.pid)
        used = sum(c1[p] - c0[p] for p in pids if c1[p] >= c0[p])
        return 100 * used / dt, front
    finally:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pr.pid)], capture_output=True)
        time.sleep(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("themes", nargs="*", default=["amber"])
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--secs", type=float, default=40)
    ap.add_argument("--warm", type=float, default=15)
    ap.add_argument("--out", default="bench.csv")
    a = ap.parse_args()
    rows, by = [], {t: [] for t in a.themes}
    for r in range(a.rounds):
        for t in (a.themes if r % 2 == 0 else a.themes[::-1]):
            if any(b"iRacingSim" in e for _, e in procs().values()):
                sys.exit("iRacing is running: stopping")
            v, front = sample(t, a.secs, a.warm)
            rows.append((r + 1, t, round(v, 1), front))
            print(r + 1, t, f"{v:.1f}", "" if front else "NOT IN FRONT, discarded", flush=True)
            if front:
                by[t].append(v)
    with open(a.out, "w", newline="") as f:
        csv.writer(f).writerows([("round", "theme", "cpu_pct_core", "in_front"), *rows])
    for t, v in by.items():
        if v:
            print(f"{t:10s} median {statistics.median(v):5.1f}  min {min(v):5.1f}  max {max(v):5.1f}  n={len(v)}")


if __name__ == "__main__":
    main()
