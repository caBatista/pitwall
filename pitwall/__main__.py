from __future__ import annotations

import argparse
import socket
from pathlib import Path

from aiohttp import web

from . import __version__
from .dev import die_with
from .engine import Engine
from .server import App
from .sources import IRacingSource, MockSource
from .trackmap import TrackMapper


ROOT = Path(__file__).resolve().parent.parent


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def main():
    p = argparse.ArgumentParser(prog="pitwall", description="Local real-timing dashboard for iRacing")
    p.add_argument("--mock", action="store_true", help="run on a simulated multiclass race (no iRacing needed)")
    p.add_argument("--speed", type=float, default=4.0, help="simulation speed multiplier (with --mock)")
    p.add_argument("--mock-session", default="race", choices=["race", "qualify", "practice", "test"],
                   help="session type the simulator pretends to be (with --mock)")
    p.add_argument("--mock-track", type=int, default=9999, help="TrackID the simulator reports, e.g. 229 for COTA (with --mock)")
    p.add_argument("--mock-start", type=float, default=0.0, help="start the simulator at this session time, in seconds (rain from 1900)")
    p.add_argument("--mock-cam", default=None, help="car the simulator focuses on: a car index, or 'cycle' (with --mock)")
    p.add_argument("--mock-wide", action="store_true", help="bigger field: six classes, 44 cars (with --mock)")
    p.add_argument("--mock-out", action="store_true", help="the driver is out of the car: Race Events (with --mock)")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--lan", action="store_true", help="listen on your local network (phone/tablet access)")
    p.add_argument("--hz", type=float, default=20.0, help="updates per second sent to the browser")
    p.add_argument("--flip-map", action="store_true", help="mirror the recorded track map")
    p.add_argument("--maps-dir", default=str(ROOT / "maps"))
    p.add_argument("--data", help="folder with settings.json and the maps (default: the project's)")
    p.add_argument("--dev-parent", type=int, help=argparse.SUPPRESS)   # the window of `Pitwall Dev.bat`: see dev.py
    args = p.parse_args()

    if args.dev_parent:
        die_with(args.dev_parent)

    stypes = {"race": "Race", "qualify": "Open Qualify", "practice": "Practice", "test": "Offline Testing"}
    cam = int(args.mock_cam) if (args.mock_cam or "").isdigit() else args.mock_cam
    source = (MockSource(speed=args.speed, session=stypes[args.mock_session], track_id=args.mock_track,
                         start=args.mock_start, cam=cam, wide=args.mock_wide, out=args.mock_out) if args.mock else IRacingSource())
    data = Path(args.data) if args.data else ROOT
    mapper = TrackMapper(data / "maps" if args.data else args.maps_dir, flip=args.flip_map, library_dir=ROOT / "maps" / "library")
    engine = Engine(mapper)
    app = App(source, engine, hz=args.hz, prefs_path=data / "settings.json").build()

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    print(f"\n  PITWALL {__version__}  ·  source: {source.name}")
    print(f"  Open  http://localhost:{args.port}")
    if args.lan:
        print(f"  LAN   http://{lan_ip()}:{args.port}")
    print("  Ctrl+C to stop\n")
    web.run_app(app, host=host, port=args.port, print=None)


if __name__ == "__main__":
    main()
