"""Camera control: as teclas que o joystick segura, e o que o servidor aceita."""
from conftest import frame, session

from pitwall.camera import ALT, AXES, CTRL, CamKeys, W
from pitwall.server import App
from pitwall.sources import MockSource


def keys(clock):
    sent = []
    return CamKeys(lambda down, key: sent.append((down, key)), clock=lambda: clock[0], keys={}), sent


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


def crossing(engine, t, lap):
    """Um carro passando pela linha, como na telemetria."""
    engine.update(frame({0: (lap, .98), 1: (lap, .98)}, SessionTime=t, IsOnTrack=False, CamCarIdx=1))
    engine.update(frame({0: (lap + 1, .02), 1: (lap + 1, .02)}, SessionTime=t + 1, IsOnTrack=False, CamCarIdx=1))


def test_going_to_a_lap_seen_crossing_the_line(engine):
    src = Source()
    engine.set_session(session([0, 1]))
    crossing(engine, 100.0, 5)
    app = App(src, engine)
    app.camera({"do": "lap", "n": 7})   # 5 completas -> 6: comecou a volta 7
    assert src.calls == [("at", 0, 100900)]


def test_a_jump_in_the_replay_is_not_a_lap_start(engine):
    engine.set_session(session([0, 1]))
    engine.update(frame({0: (5, .98), 1: (5, .98)}, SessionTime=100.0, IsOnTrack=False, CamCarIdx=1))
    engine.update(frame({0: (6, .02), 1: (6, .02)}, SessionTime=300.0, IsOnTrack=False, CamCarIdx=1))
    assert engine.lap_start(1, 7) is None


def test_a_lap_nobody_saw_starts_by_iracings_own_jump_and_lands_on_the_line(engine):
    src = Source()
    src.replay_jump = lambda n: src.calls.append(("jump", n))
    engine.set_session(session([0, 1]))
    engine.update(frame({0: (5, .5), 1: (5, .5)}, SessionTime=100.0, IsOnTrack=False, CamCarIdx=1))
    app = App(src, engine)
    app.camera({"do": "lap", "n": 7})
    app.walk()
    assert src.calls == [("jump", 5)]
    src.calls.clear()
    app._walk_t = 0.0
    engine.update(frame({0: (5, .999), 1: (5, .999)}, SessionTime=150.0, IsOnTrack=False, CamCarIdx=1, ReplayPlaySpeed=0))
    app.walk()
    assert src.calls == [("at", 0, 150400)]
    assert engine.lap_start(1, 7) == 150.0
    app._walk_t = 0.0
    engine.update(frame({0: (6, .004), 1: (6, .004)}, SessionTime=150.4, IsOnTrack=False, CamCarIdx=1, ReplayPlaySpeed=0))
    app.walk()
    assert app._walk is None


def test_a_lap_far_away_jumps_there_first(engine):
    src = Source()
    src.replay_jump = lambda n: src.calls.append(("jump", n))
    engine.set_session(session([0, 1], results=[{"CarIdx": 1, "Position": 1, "FastestTime": 100.0, "LastTime": 100.0}]))
    engine.update(frame({0: (5, .0), 1: (5, .0)}, SessionTime=1000.0, IsOnTrack=False, CamCarIdx=1))
    app = App(src, engine)
    app.camera({"do": "lap", "n": 16})
    app.walk()
    assert src.calls == [("at", 0, 2020000)]   # 10 voltas adiante, a 102 s


def test_the_camera_on_the_frame_is_the_present_even_in_a_replay(engine):
    engine.set_session(session([0, 1]))
    engine.update(frame({0: (5, .5), 1: (5, .4)}, SessionTime=100.0, IsOnTrack=False, CamGroupNumber=1))
    st = engine.update(frame({0: (2, .5), 1: (2, .4)}, SessionTime=20.0, IsOnTrack=False, IsReplayPlaying=True, ReplayFrameNumEnd=6000,
                             CamGroupNumber=9, ReplayPlaySpeed=4))
    assert st["cam"]["g"] == 9 and st["cam"]["speed"] == 4 and st["cam"]["replay"]


def test_the_sticks_turn_the_key_acceleration_off_and_closing_the_tool_gives_it_back(engine):
    app, src = out_of_car(engine, st=0x75)   # o estado em que o iRacing estava: ferramenta aberta, aceleracao ligada
    app.camera({"do": "stick", "axes": {"lon+": 1}})
    assert not src.calls[0][1] & 0x40 and src.calls[0][1] & 0x4
    app.camera({"do": "tool", "on": False})
    assert src.calls[-1][1] & 0x40 and not src.calls[-1][1] & 0x4


def test_opening_the_tool_already_goes_without_the_key_acceleration(engine):
    app, src = out_of_car(engine, st=0x51)
    app.camera({"do": "tool", "on": True})
    assert not src.calls[0][1] & 0x40


def test_hide_is_a_key_because_any_state_loses_what_the_keys_moved(engine):
    app, src = out_of_car(engine, st=0x35)
    app.camera({"do": "tap", "n": "hide"})
    assert not [c for c in src.calls if c[0] == "state"]


def test_opening_the_tool_hides_the_panels_and_the_hide_icon_brings_them_back(engine):
    app, src = out_of_car(engine, st=0x11)
    app.camera({"do": "stick", "axes": {"lon+": 1}})
    assert src.calls[0][1] & 0x8
    app, src = out_of_car(engine, st=0x3d)
    app.camera({"do": "tap", "n": "hide"})
    assert src.calls == [("state", 0x34)]


def test_a_finished_race_in_the_replay_has_my_end_in_the_footer_and_the_car_on_camera_as_reference(engine):
    info = session([0, 1], results=[{"CarIdx": 0, "Position": 2, "ClassPosition": 1, "FastestTime": 99.5, "LastTime": 100.5, "LapsComplete": 9, "Incidents": 6},
                                    {"CarIdx": 1, "Position": 1, "ClassPosition": 0, "FastestTime": 98.0, "LastTime": 99.0, "LapsComplete": 9}])
    info["SessionInfo"]["Sessions"][0]["ResultsOfficial"] = 1
    engine.set_session(info)
    st = engine.update(frame({0: (4, .5), 1: (4, .4)}, SessionTime=500.0, SessionTimeRemain=900.0, IsOnTrack=False, CamCarIdx=1, IsReplayPlaying=True, ReplayFrameNumEnd=6000))
    assert st["session"]["static"] and st["session"]["timeRemain"] == 0
    assert (st["user"]["i"], st["user"]["p"], st["user"]["lap"], st["user"]["best"], st["user"]["inc"]) == (0, 2, 9, 99.5, 6)
    assert st["me"]["i"] == 1
    assert st["cam"]["i"] == 1


def test_the_results_of_a_finished_race_do_not_overwrite_the_clock_of_the_frame(engine):
    info = session([0, 1], results=[{"CarIdx": 1, "Position": 1, "FastestTime": 99.5, "LastTime": 100.5, "LapsComplete": 9}])
    info["SessionInfo"]["Sessions"][0]["ResultsOfficial"] = 1
    engine.set_session(info)
    for t, lap, pct in ((99.0, 4, .98), (100.0, 5, .02)):
        engine.update(frame({0: (lap, pct), 1: (lap, pct)}, SessionTime=t, IsOnTrack=False, CamCarIdx=1, IsReplayPlaying=True, ReplayFrameNumEnd=6000))
    assert 99 < engine.lap_start(1, 6) <= 100


def test_with_the_view_held_on_scenic_only_the_camera_is_locked(engine):
    app, src = out_of_car(engine, st=0x37)
    app.camera({"do": "group", "n": 7})
    app.camera({"do": "stick", "axes": {"lon+": 1}})
    assert not src.calls
    app.camera({"do": "driver", "n": 1})
    assert src.calls[0][0] == "switch"


def test_keeping_the_sim_in_full_screen_is_a_setting():
    from pitwall import simwindow
    App.apply_prefs({"simFull": False})
    assert not simwindow.enabled
    App.apply_prefs({})
    assert simwindow.enabled


def test_reset_sends_the_state_as_it_is_which_drops_the_edit(engine):
    app, src = out_of_car(engine, st=0x3d)
    app.camera({"do": "reset"})
    assert src.calls == [("state", 0x3c)]


def test_the_lap_box_is_only_for_races(engine):
    st = out_of_car(engine)[0].engine.cam_now
    assert st["race"]
    engine.sessions[0]["SessionType"] = "Practice"
    assert not engine._cam({"SessionNum": 0})["race"]


def test_the_footer_is_the_user_with_another_car_on_camera(engine):
    engine.set_session(session([0, 1]))
    st = engine.update(frame({0: (5, .5), 1: (5, .4)}, IsOnTrack=False, CamCarIdx=1, PlayerCarMyIncidentCount=4))
    assert st["me"]["i"] == 1 and st["user"]["i"] == 0 and st["user"]["inc"] == 4


def test_opened_in_the_replay_the_clock_is_now_not_that_moment(engine):
    engine.set_session(session([0, 1], kind="Practice"))
    st = engine.update(frame({0: (5, .5), 1: (5, .4)}, SessionTimeRemain=900.0, IsOnTrack=False, IsReplayPlaying=True, ReplayFrameNumEnd=6000))
    assert st["session"]["timeRemain"] == 800


def test_before_the_green_the_clock_stands_at_the_length_of_the_race(engine):
    info = session([0, 1])
    info["SessionInfo"]["Sessions"][0]["SessionTime"] = "1800.0000 sec"
    engine.set_session(info)
    st = engine.update(frame({0: (0, .5), 1: (0, .4)}, SessionState=3, SessionTimeRemain=0.0, SessionTimeTotal=1800.0))
    assert st["session"]["timeRemain"] == 1800


def test_after_the_flag_no_time_is_left_whatever_the_clock_of_the_cool_down_says(engine):
    engine.set_session(session([0, 1]))
    st = engine.update(frame({0: (5, .5), 1: (5, .4)}, SessionState=5, SessionTimeRemain=780.0))
    assert st["session"]["timeRemain"] == 0


def test_leaving_the_pits_for_the_grid_is_not_a_pit_stop(engine):
    engine.set_session(session([0, 1]))
    st = engine.update(frame({0: (0, .5), 1: (0, .4)}, SessionState=2, CarIdxOnPitRoad=[True, False]))
    st = engine.update(frame({0: (0, .6), 1: (0, .4)}, SessionState=4, CarIdxOnPitRoad=[False, False]))
    assert "pl" not in next(c for c in st["cars"] if c["i"] == 0)


def test_with_nobody_in_the_world_the_lap_is_the_last_one(engine):
    engine.set_session(session([0, 1], results=[{"CarIdx": 0, "Position": 1, "LapsComplete": 8}]))
    assert engine._cam({"SessionNum": 0, "CamCarIdx": 0, "CarIdxLapCompleted": [-1] * 2})["lap"] == 8


def test_the_keys_are_the_ones_the_user_has_in_iracing():
    import struct
    from pitwall import keymap
    entry = lambda name, kind, vk, mods: name + b"\0" + struct.pack("<5I", 1, kind, 4, vk, mods << 16) + bytes(40)
    keys = keymap.parse(entry(b"PIDVIDFocusNextCar", 6, 0x4B, 0) + entry(b"CamAltInc", 0x1F, 0x49, 0x0C) + entry(b"Gone", 3, 0x10, 0) + entry(b"CamFOVInc", 0x1F, 0x78, 0))
    assert keys == {"FocusNextCar": (0, 0x4B), "CamAltInc": (0x0C, 0x49)}
    sent = []
    CamKeys(lambda down, key: sent.append((down, key[0])), keys=keys)._tap("car+")
    assert sent == [(True, 0x4B), (False, 0x4B)]
    k = CamKeys(lambda down, key: sent.append((down, key[0])), keys={})
    sent.clear()
    k._tap("car-")
    assert sent == [(True, 0x10), (True, 0x56), (False, 0x56), (False, 0x10)]
