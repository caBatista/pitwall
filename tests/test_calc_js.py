"""The fuel plan runs in the browser: its tests run under node."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_js():
    r = subprocess.run(["node", "--test", "tests/js/calc.test.mjs", "tests/js/columns.test.mjs", "tests/js/layout.test.mjs"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
