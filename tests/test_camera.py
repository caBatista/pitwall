"""Camera control: as teclas que o joystick segura, e o que o servidor aceita."""
from conftest import frame, session

from pitwall.camera import ALT, AXES, CTRL, CamKeys, W
from pitwall.server import App
from pitwall.sources import MockSource


def keys(clock):
    sent = []
    return CamKeys(lambda down, key: sent.append((down, key)), clock=lambda: clock[0]), sent


def test_a_stick_pushed_all_the_way_holds_the_key():
    t = [10.0]
    k, sent = keys(t)
    k._want, k._seen = {"lon+": 1.0}, 10.0
    assert k.step()
    assert sent == [(True, W)]


def test_half_way_the_key_is_held_half_of_the_time():
    t = [1.2]   # um numero redondo de periodos
    k, sent = keys(t)
    k._seen = 100.0
    k._want = {"lon+": .5}
    on = 0
    for n in range(100):
        t[0] = 100.0 + n * k.PERIOD / 100
        k._seen = t[0]
        k.step()
        on += W in k._down
    assert 45 <= on <= 55


def test_the_modifier_goes_down_first_and_up_last():
    t = [5.0]
    k, sent = keys(t)
    k._want, k._seen = {"alt+": 1.0}, 5.0
    k.step()
    assert sent == [(True, ALT), (True, W)]
    sent.clear()
    k._want = {}
    assert not k.step()
    assert sent == [(False, W), (False, ALT)]


def test_it_lets_go_by_itself_if_the_app_stops_talking():
    t = [5.0]
    k, sent = keys(t)
    k._want, k._seen = {"yaw+": 1.0}, 5.0
    k.step()
    t[0] = 5.0 + k.DEADMAN + .1
    assert not k.step()
    assert not k._down and k._mod is None
    assert sent[-1] == (False, CTRL)


def test_two_modifiers_at_once_the_strongest_wins():
    t = [5.0]
    k, sent = keys(t)
    k._want, k._seen = {"alt+": .3, "yaw+": 1.0}, 5.0
    k.step()
    assert k._mod == CTRL


def test_unknown_axes_are_ignored():
    k, _ = keys([1.0])
    k.drive({"nope": 1, "lon+": "x", "lat+": -1})
    assert k._want == {}


def test_every_axis_is_a_key():
    for name in ("lon", "lat", "alt", "yaw", "pitch", "roll", "fov"):
        assert f"{name}+" in AXES and f"{name}-" in AXES


class Source(MockSource):
    def __init__(self):
        super().__init__()
        self.calls = []

    def cam_switch(self, *a):
        self.calls.append(("switch", *a))

    def cam_state(self, bits):
        self.calls.append(("state", bits))

    def cam_move(self, axes):
        self.calls.append(("move", axes))

    def replay_speed(self, *a):
        self.calls.append(("speed", *a))

    def replay_at(self, *a):
        self.calls.append(("at", *a))


def out_of_car(engine, st=0x51):
    src = Source()
    engine.set_session(session([0, 1]))
    engine.update(frame({0: (5, .5), 1: (5, .4)}, IsOnTrack=False, CamCarIdx=1, CamGroupNumber=2, CamCameraNumber=3, CamCameraState=st))
    return App(src, engine), src


def test_nothing_with_the_driver_in_the_car(engine):
    src = Source()
    engine.set_session(session([0, 1]))
    engine.update(frame({0: (5, .5), 1: (5, .4)}, IsOnTrack=True))
    assert engine.in_car
    App(src, engine).camera({"do": "stick", "axes": {"lon+": 1}})
    assert not src.calls


def test_picking_a_group_keeps_the_driver(engine):
    app, src = out_of_car(engine)
    app.camera({"do": "group", "n": 7})
    assert src.calls == [("switch", engine.drivers[1]["num"], 7, 0)]


def test_the_tool_never_touches_the_cameras_file(engine):
    app, src = out_of_car(engine)
    app.camera({"do": "tool", "on": True})
    assert src.calls[0][1] & 0x4 and src.calls[0][1] & 0x20


def test_the_stick_opens_the_tool_by_itself(engine):
    app, src = out_of_car(engine)
    app.camera({"do": "stick", "axes": {"lon+": 1}})
    assert src.calls[0][0] == "state" and src.calls[1] == ("move", {"lon+": 1})


def test_letting_go_of_the_stick_does_not_open_the_tool(engine):
    app, src = out_of_car(engine)
    app.camera({"do": "stick", "axes": {}})
    assert src.calls == [("move", {})]


def test_going_to_a_lap_of_the_car_on_camera(engine):
    src = Source()
    engine.set_session(session([0, 1]))
    for t, lap in ((10, 4), (100, 5), (200, 6)):
        engine.update(frame({0: (lap, .5), 1: (lap, .4)}, SessionTime=float(t), IsOnTrack=False, CamCarIdx=1))
    app = App(src, engine)
    app.camera({"do": "lap", "n": 6})
    assert src.calls == [("at", 0, 100000)]
    src.calls.clear()
    app.camera({"do": "lap", "n": 40})   # essa nao foi vista
    assert not src.calls


def test_the_camera_on_the_frame_is_the_present_even_in_a_replay(engine):
    engine.set_session(session([0, 1]))
    engine.update(frame({0: (5, .5), 1: (5, .4)}, SessionTime=100.0, IsOnTrack=False, CamGroupNumber=1))
    st = engine.update(frame({0: (2, .5), 1: (2, .4)}, SessionTime=20.0, IsOnTrack=False, IsReplayPlaying=True, ReplayFrameNumEnd=6000,
                             CamGroupNumber=9, ReplayPlaySpeed=4))
    assert st["cam"]["g"] == 9 and st["cam"]["speed"] == 4 and st["cam"]["replay"]
