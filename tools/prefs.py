"""The settings of the Pitwall that is running (EXE or dev), read through its own /prefs.

The Claude desktop app redirects %LOCALAPPDATA% for whatever it starts, so the settings.json seen from its shells
may not be the user's: the running app is the truth.

    python tools/prefs.py               -> every key
    python tools/prefs.py layout evOff  -> only these
"""
import json
import subprocess
import sys
import urllib.request

out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
pids = subprocess.run(["powershell", "-NoProfile", "-Command",
                       "(Get-Process Pitwall,python,pythonw -ErrorAction SilentlyContinue).Id"], capture_output=True, text=True).stdout.split()
for line in out.splitlines():
    f = line.split()
    if len(f) == 5 and f[3] == "LISTENING" and f[1].startswith("127.0.0.1:") and f[4] in pids:
        try:
            data = json.load(urllib.request.urlopen(f"http://{f[1]}/prefs", timeout=2))
        except Exception:  # noqa: BLE001
            continue
        keys = sys.argv[1:] or list(data)
        print(f[1])
        for k in keys:
            v = data.get(k)
            if k == "layout" and isinstance(v, dict):
                v = {s: [i["id"] for i in items] for s, items in v.items()}
            print(f"{k}: {json.dumps(v, ensure_ascii=False)}")
        break
else:
    print("no Pitwall running")
