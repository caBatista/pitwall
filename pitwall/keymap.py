"""The keys the user has in iRacing. The ones Pitwall presses can be changed there, so they are read from its
controls file, Documents/iRacing/profiles/controls/<profile>/controls.cfg, each time it changes.

The file is binary, no format published: seen in it, each control is its name, a zero, then four little-endian
numbers: uint, kind (6 a key, 0x1F a key with an analogue axis), 4, the virtual key; then the modifiers in the
third byte of a fifth number: 0x03 shift, 0x0C ctrl, 0x30 alt. A name can come stuck to the end of the "PIDVID" of
the entry before. Any other key, or no file: the default keys.
"""
from __future__ import annotations

import ctypes
import re
import struct
from pathlib import Path

NAME = re.compile(rb"([A-Za-z][A-Za-z0-9_]{3,})\x00")
KEY_KINDS = (0x06, 0x1F)
# only these are real virtual keys in the file: the [ and ] that work are saved as 0x76 and 0x78, F7 and F9 if read as such
PLAIN = {0x20, *range(0x30, 0x3A), *range(0x41, 0x5B)}


def parse(data: bytes) -> dict:
    """{control: (modifier bits, virtual key)}; a control with no key on the keyboard isn't in it."""
    keys = {}
    for m in NAME.finditer(data):
        if m.end() + 20 > len(data):
            continue
        _, kind, size, vk, mods = struct.unpack_from("<5I", data, m.end())
        if kind in KEY_KINDS and size == 4 and vk in PLAIN:
            keys[m.group(1).decode().removeprefix("PIDVID")] = ((mods >> 16) & 0xFF, vk)
    return keys


def documents() -> Path | None:
    try:
        buf = ctypes.create_unicode_buffer(260)
        ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)   # CSIDL_PERSONAL: it may be on OneDrive
        return Path(buf.value)
    except (AttributeError, OSError):
        return None


def find() -> Path | None:
    """The controls file saved last: the sim writes the profile in use."""
    docs = documents()
    files = list((docs / "iRacing" / "profiles" / "controls").glob("*/controls.cfg")) if docs else []
    return max(files, key=lambda p: p.stat().st_mtime, default=None)


_seen = (None, 0.0, {})


def current() -> dict:
    """The user's keys, read again only when the file changes."""
    global _seen
    try:
        path = find()
        stamp = path.stat().st_mtime if path else 0.0
        if (path, stamp) != _seen[:2]:
            _seen = (path, stamp, parse(path.read_bytes()) if path else {})
    except OSError:
        pass
    return _seen[2]
