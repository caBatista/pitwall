"""Modo dev: reinicia o servidor quando o codigo muda, recarrega a tela quando o resto muda."""
import socket
import sys
import time

from pitwall.dev import Dev, listening, snapshot


class Window:
    def __init__(self):
        self.loaded = []

    def load_url(self, url):
        self.loaded.append(url)


def server(port):
    """Um processo que so escuta na porta, como o servidor."""
    code = f"import socket,time; s=socket.socket(); s.bind(('127.0.0.1',{port})); s.listen(); time.sleep(60)"
    return [sys.executable, "-c", code]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def until(check, secs=6):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(.05)
    return False


def project(tmp_path):
    code, web = tmp_path / "pitwall", tmp_path / "web"
    code.mkdir(), web.mkdir()
    (code / "a.py").write_text("1")
    (web / "a.js").write_text("1")
    return code, web


def test_snapshot_only_sees_these_endings(tmp_path):
    (tmp_path / "a.js").write_text("1")
    (tmp_path / "b.png").write_text("1")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "c.js").write_text("1")
    assert [p.name for p in snapshot(tmp_path, (".js",))] == ["a.js"]


def test_saving_code_gives_a_new_server_and_reloads_the_page(tmp_path):
    code, web = project(tmp_path)
    port, window = free_port(), Window()
    dev = Dev(server(port), port, tmp_path / "dev.log", (code, web))
    try:
        assert dev.start_server()
        first = dev.proc.pid
        dev.pages = lambda: [(window, "board")]
        dev.watch()
        time.sleep(.6)
        (code / "a.py").write_text("2")
        assert until(lambda: window.loaded == ["board?dev=1"])
        assert dev.proc.pid != first and listening(port, 1)
    finally:
        dev.stop()
    assert not listening(port, .3)


def test_saving_the_page_keeps_the_server(tmp_path):
    code, web = project(tmp_path)
    port, window = free_port(), Window()
    dev = Dev(server(port), port, tmp_path / "dev.log", (code, web))
    try:
        assert dev.start_server()
        first = dev.proc.pid
        dev.pages = lambda: [(window, "board")]
        dev.watch()
        time.sleep(.6)
        (web / "a.js").write_text("2")
        assert until(lambda: window.loaded == ["board?dev=1"])
        assert dev.proc.pid == first
    finally:
        dev.stop()


def test_a_mistake_in_the_code_waits_for_the_next_save(tmp_path, monkeypatch):
    code, web = project(tmp_path)
    port, window = free_port(), Window()
    monkeypatch.setattr("pitwall.dev.UP_IN", .3)
    dev = Dev([sys.executable, "-c", "raise SystemExit(1)"], port, tmp_path / "dev.log", (code, web))
    dev.pages = lambda: [(window, "board")]
    try:
        assert not listening(port, .2)
        dev.apply(True)
        assert window.loaded == []
    finally:
        dev.stop()
