from __future__ import annotations

import argparse
import socket
from pathlib import Path

from aiohttp import web

from . import __version__
from .engine import Engine
from .server import App
from .sources import IRacingSource, MockSource
from .trackmap import TrackMapper


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
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--lan", action="store_true", help="listen on your local network (phone/tablet access)")
    p.add_argument("--hz", type=float, default=20.0, help="updates per second sent to the browser")
    p.add_argument("--flip-map", action="store_true", help="mirror the recorded track map")
    p.add_argument("--maps-dir", default=str(Path(__file__).resolve().parent.parent / "maps"))
    args = p.parse_args()

    source = MockSource(speed=args.speed) if args.mock else IRacingSource()
    mapper = TrackMapper(args.maps_dir, flip=args.flip_map)
    engine = Engine(mapper)
    app = App(source, engine, hz=args.hz).build()

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    print(f"\n  PITWALL {__version__}  ·  source: {source.name}")
    print(f"  Open  http://localhost:{args.port}")
    if args.lan:
        print(f"  LAN   http://{lan_ip()}:{args.port}")
    print("  Ctrl+C to stop\n")
    web.run_app(app, host=host, port=args.port, print=None)


if __name__ == "__main__":
    main()
