"""Only Pitwall's own pages talk to the server: a web page elsewhere could type in the sim or use the pit menu."""
import asyncio

from aiohttp.test_utils import TestClient, TestServer

from pitwall.server import App
from pitwall.sources import MockSource


def run(coro):
    return asyncio.run(coro)


async def status(origin=None, path="/prefs"):
    from pitwall.engine import Engine
    from pitwall.trackmap import TrackMapper
    import tempfile
    from pathlib import Path
    app = App(MockSource(), Engine(TrackMapper(Path(tempfile.mkdtemp()))))
    async with TestClient(TestServer(app.build())) as c:
        headers = {"Origin": origin.replace("HOST", f"{c.host}:{c.port}")} if origin else {}
        r = await c.get(path, headers=headers)
        return r.status


def test_a_foreign_page_is_refused():
    assert run(status("https://evil.example")) == 403
    assert run(status("http://127.0.0.1:1")) == 403   # another port is another site


def test_its_own_pages_and_tools_get_in():
    assert run(status("http://HOST")) == 200
    assert run(status()) == 200
