"""Race Events: o que vira evento, o que nao vira e o momento certo no replay."""
from conftest import frame, session
from pitwall.events import REPLAY_LEAD


def setup(engine, drivers=(0, 1, 2), kind="Race", **extra):
    engine.set_session(session(drivers, kind=kind, **extra))


def run(engine, t0, t1, make, step=0.25):
    t = t0
    while t <= t1:
        engine.update(make(t))
        t += step


def kinds(engine, k=None):
    return [e for e in engine.ev.items if k is None or e["k"] == k]


def racing(place, t, **over):
    return frame(place, SessionTime=t, **over)


def test_a_pass_needs_to_last(engine):
    setup(engine)
    # 1 passa 0 aos 10 s, e fica
    run(engine, 0, 20, lambda t: racing({0: (5, .50), 1: (5, .49 if t < 10 else .51)}, t))
    p = kinds(engine, "pass")
    assert len(p) == 1
    assert (p[0]["i"], p[0]["j"]) == (1, 0) and 9.9 <= p[0]["t"] <= 10.3   # o momento da ultrapassagem, nao o da confirmacao


def test_side_by_side_is_not_a_pass(engine):
    setup(engine)
    # lado a lado: a ordem vira e volta dentro de 1 s
    run(engine, 0, 20, lambda t: racing({0: (5, .50), 1: (5, .51 if int(t) % 2 else .49)}, t))
    assert not kinds(engine, "pass")


def test_lapping_someone_is_not_a_pass(engine):
    setup(engine)
    run(engine, 0, 10, lambda t: racing({0: (6, .40), 1: (5, .30 + t * .03)}, t))
    assert not kinds(engine, "pass")


def test_a_car_in_the_pits_is_not_passed(engine):
    setup(engine)

    def make(t):
        inn = t >= 5
        f = racing({0: (5, .50), 1: (5, .49 if t < 8 else .51)}, t)
        f["CarIdxOnPitRoad"][0] = 1 if inn else 0
        return f
    run(engine, 0, 15, make)
    assert not kinds(engine, "pass")


def test_rejoining_ahead_is_not_a_pass(engine):
    setup(engine)

    def make(t):
        f = racing({0: (5, .50), 1: (5, .49 if t < 8 else .51)}, t)
        f["CarIdxOnPitRoad"][1] = 1 if 3 <= t < 7.5 else 0
        return f
    run(engine, 0, 12, make)
    assert not kinds(engine, "pass")
    assert [e["d"] for e in kinds(engine, "pit")] == [4.5]


def test_passes_are_per_class(engine):
    setup(engine, [{"CarIdx": 0, "CarClassID": 1}, {"CarIdx": 1, "CarClassID": 2}])
    run(engine, 0, 20, lambda t: racing({0: (5, .50), 1: (5, .49 if t < 10 else .51)}, t))
    assert not kinds(engine, "pass")


def test_my_incidents(engine):
    setup(engine)
    run(engine, 0, 10, lambda t: racing({0: (5, .50), 1: (5, .5005)}, t, PlayerCarMyIncidentCount=0 if t < 5 else 4))
    e = kinds(engine, "inc")
    assert len(e) == 1 and (e[0]["n"], e[0]["total"], e[0]["j"]) == (4, 4, 1)


def test_incidents_already_there_dont_count(engine):
    setup(engine)
    run(engine, 0, 5, lambda t: racing({0: (5, .5)}, t, PlayerCarMyIncidentCount=7))
    assert not kinds(engine, "inc")


def test_off_track_must_last(engine):
    setup(engine)

    def make(t):
        f = racing({0: (5, .5 + t * .001), 1: (5, .1 + t * .001)}, t)
        if 3 <= t < 3.5:
            f["CarIdxTrackSurface"][0] = 0      # raspou na zebra
        if 8 <= t < 11:
            f["CarIdxTrackSurface"][1] = 0
        return f
    run(engine, 0, 15, make)
    e = kinds(engine, "off")
    assert [x["i"] for x in e] == [1] and e[0]["t"] == 8.0


def test_stopped_on_track(engine):
    setup(engine)
    run(engine, 0, 2, lambda t: racing({0: (5, .5), 1: (5, .2)}, t, SessionState=3))

    def make(t):
        return racing({0: (5, .3 + t * .001), 1: (5, min(.2 + t * .001, .3))}, t)
    run(engine, 2, 130, make)
    e = kinds(engine, "stop")
    assert [x["i"] for x in e] == [1]


def test_best_lap_jumps_to_the_start_of_the_lap(engine):
    setup(engine)
    run(engine, 0, 2, lambda t: racing({0: (5, .5), 1: (5, .2)}, t, best={1: 90.0, 0: 95.0}))
    run(engine, 2, 4, lambda t: racing({0: (5, .5), 1: (5, .2)}, t, best={1: 89.0 if t >= 3 else 90.0, 0: 95.0}))
    e = kinds(engine, "fast")
    assert len(e) == 1 and e[0]["v"] == 89.0 and e[0]["at"] == round(e[0]["t"] - 89.0, 2)
    assert engine.ev.replay_target(e[0]["id"]) == (0, 0, 1)   # nao ha replay antes do zero


def test_qualify_laps_say_the_position(engine):
    setup(engine, kind="Open Qualify")
    run(engine, 0, 2, lambda t: frame({0: (2, .5), 1: (2, .5)}, SessionTime=t, best={0: 90.0}))
    run(engine, 2, 5, lambda t: frame({0: (2, .5), 1: (2, .5)}, SessionTime=t, best={0: 90.0, 1: 91.0 if t < 4 else 89.5}))
    q = kinds(engine, "q")
    assert [(e["i"], e["p"], e["pole"]) for e in q] == [(1, 2, False), (1, 1, True)]


def test_the_moment_in_the_replay(engine):
    setup(engine)
    run(engine, 0, 20, lambda t: racing({0: (5, .50), 1: (5, .49 if t < 10 else .51)}, t))
    e = kinds(engine, "pass")[0]
    sn, ms, car = engine.ev.replay_target(e["id"])
    assert (sn, car) == (0, 1)
    assert ms == int((e["t"] - REPLAY_LEAD) * 1000)


def test_a_flag_keeps_the_camera(engine):
    setup(engine)
    run(engine, 0, 3, lambda t: racing({0: (5, .5)}, t, SessionState=3))
    run(engine, 3, 6, lambda t: racing({0: (5, .5)}, t))
    e = kinds(engine, "green")[0]
    assert engine.ev.replay_target(e["id"])[2] is None


def test_caution_comes_and_goes(engine):
    setup(engine)
    run(engine, 0, 9, lambda t: racing({0: (5, .5)}, t, SessionFlags=0x4000 if 3 <= t < 6 else 0x4))
    assert [e["k"] for e in kinds(engine) if e["k"] in ("caution", "clear")] == ["caution", "clear"]


def test_local_yellow_is_not_a_caution(engine):
    setup(engine)
    run(engine, 0, 9, lambda t: racing({0: (5, .5)}, t, SessionFlags=0x8 if 3 <= t < 6 else 0x4))
    assert not kinds(engine, "caution")


def test_going_to_the_replay_and_back_invents_nothing(engine):
    setup(engine)
    run(engine, 0, 5, lambda t: racing({0: (5, .50), 1: (5, .49)}, t))

    def watching(t):   # a telemetria mostra o passado: a ordem e outra, os tempos voltam
        return racing({0: (3, .50), 1: (4, .49)}, t - 200, IsReplayPlaying=True, ReplayFrameNumEnd=12000, PlayerCarMyIncidentCount=4)
    run(engine, 5, 15, watching)
    assert not kinds(engine)
    # de volta ao vivo: nao e nada de novo
    run(engine, 15, 25, lambda t: racing({0: (6, .50), 1: (6, .49)}, t, IsReplayPlaying=True, ReplayFrameNumEnd=1, PlayerCarMyIncidentCount=4))
    assert not kinds(engine)


def test_a_live_race_seen_in_the_replay_is_read_too(engine):
    setup(engine)
    run(engine, 0, 3, lambda t: racing({0: (5, .50), 1: (5, .49)}, t))
    run(engine, 100, 120, lambda t: racing({0: (5, .50), 1: (5, .49 if t < 110 else .51)}, t, IsReplayPlaying=True, ReplayFrameNumEnd=9000))
    assert len(kinds(engine, "pass")) == 1


def test_a_bad_frame_never_costs_the_board(engine, monkeypatch):
    setup(engine)
    monkeypatch.setattr(engine.ev, "feed", lambda f: 1 / 0)
    st = engine.update(racing({0: (5, .5)}, 1))
    assert st["cars"] and engine.ev.failed


def test_a_new_session_keeps_the_list_a_new_event_clears_it(engine):
    setup(engine, kind="Race")
    run(engine, 0, 20, lambda t: racing({0: (5, .50), 1: (5, .49 if t < 10 else .51)}, t))
    assert kinds(engine, "pass")
    run(engine, 0, 5, lambda t: racing({0: (0, .10), 1: (0, .20)}, t, SessionNum=1))
    assert kinds(engine, "pass")
    setup(engine, sub_id=2)
    run(engine, 0, 2, lambda t: racing({0: (0, .10), 1: (0, .20)}, t))
    assert not engine.ev.items and engine.ev.cleared


def test_fields_for_the_panel(engine):
    setup(engine)
    run(engine, 0, 20, lambda t: racing({0: (5, .50), 1: (5, .49 if t < 10 else .51)}, t))
    st = engine.update(racing({0: (5, .50), 1: (5, .51)}, 21))
    assert st["session"]["inCar"] is True and st["session"]["player"] == 0 and st["session"]["num"] == 0
    assert st["session"]["behind"] == 0
    e = kinds(engine, "pass")[0]
    assert e["sk"] == "race" and e["lap"] == 6 and e["p"] == 1


def test_side_by_side_is_a_fight(engine):
    setup(engine)   # pista de 5 km: 0.0005 de volta = 2,5 m, lado a lado por 4 s e depois abre
    run(engine, 0, 20, lambda t: racing({0: (5, .5005), 1: (5, .50 if 3 <= t < 7 else .49)}, t))
    e = kinds(engine, "fight")
    assert [(x["i"], x["j"]) for x in e] == [(1, 0)]   # 1 atacou, 0 defendeu
    assert e[0]["t"] == 3.0 and not kinds(engine, "pass")


def test_a_fight_that_ends_in_a_pass_is_a_pass(engine):
    setup(engine)
    run(engine, 0, 20, lambda t: racing({0: (5, .5005), 1: (5, .49 if t < 3 else .50 if t < 7 else .52)}, t))
    assert len(kinds(engine, "pass")) == 1 and not kinds(engine, "fight")


def test_a_brush_is_not_a_fight(engine):
    setup(engine)
    run(engine, 0, 20, lambda t: racing({0: (5, .5005), 1: (5, .50 if 3 <= t < 3.5 else .49)}, t))
    assert not kinds(engine, "fight")


def test_a_saved_replay_is_the_race(engine):
    info = session((0, 1))
    info["WeekendInfo"]["SimMode"] = "replay"
    engine.set_session(info)
    # o fim do replay esta longe, e mesmo assim as ultrapassagens contam
    run(engine, 0, 20, lambda t: racing({0: (5, .50), 1: (5, .49 if t < 10 else .51)}, t, IsReplayPlaying=True, ReplayFrameNumEnd=90000))
    assert len(kinds(engine, "pass")) == 1
    st = engine.update(racing({0: (5, .50), 1: (5, .51)}, 21, IsReplayPlaying=True, ReplayFrameNumEnd=90000))
    assert st["session"]["behind"] == 0


def test_seeing_the_replay_twice_lists_once(engine):
    info = session((0, 1))
    info["WeekendInfo"]["SimMode"] = "replay"
    engine.set_session(info)
    make = lambda t: racing({0: (5, .50), 1: (5, .49 if t < 10 else .51)}, t, IsReplayPlaying=True, ReplayFrameNumEnd=90000)
    run(engine, 0, 20, make)
    run(engine, 0, 20, make)
    assert len(kinds(engine, "pass")) == 1


def test_a_seek_forward_invents_nothing(engine):
    info = session((0, 1))
    info["WeekendInfo"]["SimMode"] = "replay"
    engine.set_session(info)
    run(engine, 0, 5, lambda t: racing({0: (5, .50), 1: (5, .49)}, t, IsReplayPlaying=True, ReplayFrameNumEnd=90000))
    run(engine, 600, 610, lambda t: racing({0: (20, .50), 1: (20, .60)}, t, IsReplayPlaying=True, ReplayFrameNumEnd=60000, PlayerCarMyIncidentCount=6))
    assert not kinds(engine)


def test_in_a_replay_the_clock_is_the_replays(engine):
    setup(engine)
    run(engine, 100, 103, lambda t: racing({0: (5, .50), 1: (5, .49)}, t))
    # o SessionTime segue o relogio ao vivo; o que esta na tela e o ReplaySessionTime
    make = lambda t: racing({0: (5, .50), 1: (5, .49 if t < 50 else .51)}, 200 + t, IsReplayPlaying=True,
                            ReplaySessionTime=t, ReplaySessionNum=0, ReplayFrameNumEnd=9000)
    run(engine, 40, 60, make)
    e = kinds(engine, "pass")
    assert len(e) == 1 and 49.9 <= e[0]["t"] <= 50.3


def test_the_speed_never_comes_after_the_search():
    """Enviada logo depois do salto, a velocidade cancela o salto no iRacing."""
    from pitwall.sources import IRacingSource

    calls = []

    class Ir:
        is_connected = True

        def __getitem__(self, k):
            return 1

        def __getattr__(self, name):
            return lambda *a: calls.append(name)

    src = IRacingSource.__new__(IRacingSource)
    src.ir = Ir()
    src.replay(0, 1000, "64")
    assert calls == ["cam_switch_num", "replay_set_play_speed", "replay_search_session_time"]
    calls.clear()
    src.replay_live()
    assert calls == ["replay_set_play_speed", "replay_search"]


def pace_lap(engine, t0, slow_from=None, near=None, cars=(0, 1, 2), step=.25):
    """Tres carros em volta normal; o 1 cai para 20% do ritmo a partir de slow_from."""
    pos = {1: 0.30}
    t = t0
    while t < t0 + 80:
        pos[1] += (.002 if slow_from and t >= slow_from else .01) * step * 2
        pos[2] = pos[1] + near if near else pos.get(2, .55) + .01 * step * 2
        place = {0: (5, .05), 1: (5 + int(pos[1]), pos[1] % 1.0), 2: (2, pos[2] % 1.0)}
        engine.update(racing(place, t))
        t += step
    return t


def test_a_car_far_under_its_pace_is_an_accident(engine):
    setup(engine)
    run(engine, 0, 1, lambda t: racing({1: (5, .30)}, t, SessionState=3))
    pace_lap(engine, 2)
    assert not kinds(engine, "acc")
    t = pace_lap(engine, 90, slow_from=120)
    e = kinds(engine, "acc")
    assert [x["i"] for x in e] == [1] and e[0]["est"] is True and e[0]["x"] == 2 and e[0]["j"] is None
    assert 119 <= e[0]["t"] <= 122


def test_someone_right_there_makes_it_a_contact(engine):
    setup(engine)
    run(engine, 0, 1, lambda t: racing({1: (5, .30)}, t, SessionState=3))
    pace_lap(engine, 2, near=.001)
    pace_lap(engine, 90, slow_from=120, near=.001)
    e = kinds(engine, "acc")
    assert e and e[0]["x"] == 4 and e[0]["j"] == 2


def test_my_own_points_are_exact(engine):
    setup(engine)
    run(engine, 0, 4, lambda t: racing({0: (5, .5)}, t, PlayerCarMyIncidentCount=0 if t < 2 else 1))
    run(engine, 4, 8, lambda t: racing({0: (5, .5)}, t, PlayerCarMyIncidentCount=1 if t < 6 else 5))
    assert [(e["n"], e["total"]) for e in kinds(engine, "inc")] == [(1, 1), (4, 5)]
    assert not kinds(engine, "acc")


def test_points_of_the_others_are_used_when_the_session_gives_them(engine):
    ds = [{"CarIdx": 0}, {"CarIdx": 1, "CurDriverIncidentCount": 1}]
    engine.set_session(session(ds))
    run(engine, 0, 3, lambda t: racing({0: (5, .5), 1: (5, .2)}, t))
    engine.set_session(session([{"CarIdx": 0}, {"CarIdx": 1, "CurDriverIncidentCount": 2}]))
    run(engine, 3, 5, lambda t: racing({0: (5, .5), 1: (5, .2)}, t))
    assert not kinds(engine, "acc")   # +1x: fica de fora
    engine.set_session(session([{"CarIdx": 0}, {"CarIdx": 1, "CurDriverIncidentCount": 6}]))
    run(engine, 5, 7, lambda t: racing({0: (5, .5), 1: (5, .2)}, t))
    e = kinds(engine, "acc")
    assert [(x["i"], x["x"], x["est"]) for x in e] == [(1, 4, False)]


def test_each_car_keeps_its_own_lap(engine):
    setup(engine)
    run(engine, 0, 20, lambda t: racing({0: (7, .50), 1: (7, .49 if t < 10 else .51)}, t))
    e = kinds(engine, "pass")[0]
    assert (e["cl"], e["cj"]) == (8, 8)
    setup(engine)
    run(engine, 21, 25, lambda t: racing({0: (9, .5), 1: (3, .2 + (.1 if t >= 23 else 0))}, t, PlayerCarMyIncidentCount=0 if t < 23 else 4))
    assert kinds(engine, "inc")[0]["cl"] == 10
