"""Is iRacing open, is the driver in the car? One line, for scripts and for deciding whether a window may open.

    python tools/simstate.py          -> sim=True onTrack=False state=4 replay=True
    exit code: 0 out of the car or no sim, 2 in the car (nothing may take the focus now)
"""
import sys

import irsdk

ir = irsdk.IRSDK()
up = ir.startup()
if not up:
    print("sim=False onTrack=None")
    sys.exit(0)
ir.freeze_var_buffer_latest()
on = bool(ir["IsOnTrack"])
print(f"sim=True onTrack={on} state={ir['SessionState']} replay={bool(ir['IsReplayPlaying'])} session={ir['SessionNum']}")
sys.exit(2 if on else 0)
