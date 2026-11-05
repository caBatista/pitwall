"""Photos of all the monitors during a race, to compare Pitwall with RaceLab and iRacing afterwards.

Only looks: one grab of the whole desktop, so every overlay is from the same instant, no window is
touched. Runs at low priority. Each photo goes in index.csv with the moment, so a stretch can be found:
the comparison itself is read from the photos. Waits for the race and ends with the sim.

    python tools/capture_compare.py <folder> [--every 30] [--once]
"""
import argparse
import csv
import ctypes
import time
from pathlib import Path

import irsdk
from PIL import ImageGrab

BELOW_NORMAL = 0x4000
HOLD = 60          # s without the sim: it is over
WAIT = 3 * 3600    # s for the sim to show up


def grab(folder, name):
    ImageGrab.grab(all_screens=True).convert("RGB").save(folder / name, quality=90)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("folder", type=Path)
    p.add_argument("--every", type=float, default=30.0)
    p.add_argument("--once", action="store_true")
    a = p.parse_args()
    a.folder.mkdir(parents=True, exist_ok=True)
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), BELOW_NORMAL)
    if a.once:
        t0 = time.perf_counter()
        grab(a.folder, "test.jpg")
        print(f"{time.perf_counter() - t0:.3f} s")
        return

    ir = irsdk.IRSDK()
    began, last, seen, pit = time.time(), 0.0, None, None
    with open(a.folder / "index.csv", "a", newline="") as fh:
        log = csv.writer(fh)
        while True:
            time.sleep(1)
            now = time.time()
            if not (ir.is_initialized and ir.is_connected) and not ir.startup():
                if now - (seen or began) > (HOLD if seen else WAIT):
                    return
                continue
            seen = now
            ir.freeze_var_buffer_latest()
            if ir["SessionState"] is None or ir["SessionState"] < 4:
                continue
            on_pit = bool(ir["OnPitRoad"])
            if now - last >= a.every or on_pit != pit:
                name = f"{time.strftime('%H%M%S')}.jpg"
                grab(a.folder, name)
                log.writerow([name, ir["SessionNum"], ir["SessionState"], round(ir["SessionTime"], 1),
                              ir["Lap"], round(ir["LapDistPct"], 3), on_pit, round(ir["FuelLevel"], 2)])
                fh.flush()
                last, pit = now, on_pit


if __name__ == "__main__":
    main()
