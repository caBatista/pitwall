"""Race Events: o que vira evento, o que nao vira e o momento certo no replay."""
import json
import os
import time

from conftest import frame, session
from types import SimpleNamespace

from pitwall.events import REPLAY_LEAD, EventLog, past_race, purge


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


def test_a_best_lap_belongs_to_the_lap_that_ended(engine):
    setup(engine)
    run(engine, 0, 2, lambda t: racing({0: (5, .5), 1: (5, .2)}, t, best={1: 90.0, 0: 95.0}))
    run(engine, 2, 4, lambda t: racing({0: (5, .5), 1: (5, .2)}, t, best={1: 89.0 if t >= 3 else 90.0, 0: 95.0}))
    e = kinds(engine, "fast")[0]
    assert e["cl"] == engine.ev.lap_of(1) - 1


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
            return {"Groups": [{"GroupNum": 10, "GroupName": "Scenic"}, {"GroupNum": 20, "GroupName": "Chase"}]} if k == "CameraInfo" else 1

        def __getattr__(self, name):
            return lambda *a: calls.append((name, *a) if name == "cam_switch_num" else name)

    src = IRacingSource.__new__(IRacingSource)
    src.ir = Ir()
    src.replay(0, 1000, "64")
    assert calls == [("cam_switch_num", "64", 20, 1), "replay_set_play_speed", "replay_search_session_time"]   # sempre chase
    calls.clear()
    src.replay_live()
    assert calls == ["replay_set_play_speed", "replay_search"]


def test_my_own_points_are_exact(engine):
    setup(engine)
    run(engine, 0, 4, lambda t: racing({0: (5, .5)}, t, PlayerCarMyIncidentCount=0 if t < 2 else 1))
    run(engine, 4, 8, lambda t: racing({0: (5, .5)}, t, PlayerCarMyIncidentCount=1 if t < 6 else 5))
    # 4 s apart: the same moment, as iRacing's off track turned into a loss of control
    assert [(e.get("n0"), e["n"], e["total"]) for e in kinds(engine, "inc")] == [(1, 5, 5)]
    run(engine, 8, 30, lambda t: racing({0: (5, .5)}, t, PlayerCarMyIncidentCount=5 if t < 25 else 7))
    assert [(e["n"], e["total"]) for e in kinds(engine, "inc")][-1] == (2, 7)   # later on: one of its own


def test_each_car_keeps_its_own_lap(engine):
    setup(engine)
    run(engine, 0, 20, lambda t: racing({0: (7, .50), 1: (7, .49 if t < 10 else .51)}, t))
    e = kinds(engine, "pass")[0]
    assert (e["cl"], e["cj"]) == (8, 8)
    setup(engine)
    run(engine, 21, 25, lambda t: racing({0: (9, .5), 1: (3, .2 + (.1 if t >= 23 else 0))}, t, PlayerCarMyIncidentCount=0 if t < 23 else 4))
    assert kinds(engine, "inc")[0]["cl"] == 10


def test_the_list_survives_a_restart(engine, tmp_path):
    setup(engine)
    run(engine, 100, 103, lambda t: racing({0: (5, .50), 1: (5, .49)}, t))
    run(engine, 103, 115, lambda t: racing({0: (5, .50), 1: (5, .49 if t < 104 else .51)}, t))
    assert kinds(engine, "pass")
    engine.ev.sub = sub = 777
    engine.ev._f = SimpleNamespace(**{**vars(engine.ev._f), "sub": sub})
    engine.ev.save(tmp_path)

    other = EventLog()
    other.dir = tmp_path
    other.feed(SimpleNamespace(**{**vars(engine.ev._f), "sub": sub}))
    assert [e["id"] for e in other.items] == [e["id"] for e in engine.ev.items] and other.cleared
    e = kinds(engine, "pass")[0]
    other.snum = e["sn"]
    assert other.add(e["t"], "pass", i=e["i"], j=e.get("j")) is None   # visto de novo no replay: nao duplica
    assert other.add(e["t"] + 60, "pass", i=e["i"], j=e.get("j"))["id"] == max(x["id"] for x in engine.ev.items) + 1
    assert other.replay_target(other.items[0]["id"])

    third = EventLog()
    third.dir = tmp_path
    third.feed(SimpleNamespace(**{**vars(engine.ev._f), "sub": "outra"}))
    assert not third.items


def test_getting_ahead_for_a_moment_and_losing_it_is_no_pass(engine):
    """T1 da volta 5: fiquei um pouco na frente por fora; quem ja estava na frente nao me passou."""
    setup(engine)
    run(engine, 100, 103, lambda t: racing({0: (5, .50), 1: (5, .49)}, t))
    run(engine, 103, 125, lambda t: racing({0: (5, .50), 1: (5, .49 if t < 105 or t >= 109 else .51)}, t))
    assert not kinds(engine, "pass")


def test_a_battle_counts_by_how_it_ended(engine):
    setup(engine)
    run(engine, 100, 103, lambda t: racing({0: (5, .50), 1: (5, .49)}, t))
    run(engine, 103, 125, lambda t: racing({0: (5, .50), 1: (5, .51 if 104 <= t < 106 or t >= 110 else .49)}, t))
    e = kinds(engine, "pass")
    assert [(x["i"], x["j"]) for x in e] == [(1, 0)] and 109.9 <= e[0]["t"] <= 110.3


def test_an_invalid_lap_is_not_an_event(engine):
    setup(engine)
    run(engine, 100, 103, lambda t: racing({0: (5, .50), 1: (5, .49)}, t))
    assert not kinds(engine, "inv")


def replay_of(t, **over):
    return racing({0: (5, .50), 1: (5, .49)}, t, IsReplayPlaying=True, ReplaySessionTime=t, ReplaySessionNum=0, ReplayFrameNumEnd=60000, **over)


def test_a_finished_race_in_the_replay_is_the_result(engine):
    engine.set_session(session(results=[{"CarIdx": 1, "Position": 1, "FastestTime": 90.5, "LastTime": 91.0}, {"CarIdx": 0, "Position": 2, "FastestTime": 91.5, "LastTime": 92.0}]))
    engine.sessions[0]["ResultsOfficial"] = 1
    st = engine.update(replay_of(100))
    assert st["session"]["static"] and st["session"]["over"]
    assert [c["i"] for c in sorted((c for c in st["cars"] if c["p"]), key=lambda c: c["p"])][:2] == [1, 0]   # a ordem final, nao a da pista


def test_a_race_still_running_in_the_replay_stays_live(engine):
    engine.set_session(session(results=[{"CarIdx": 0, "Position": 1}, {"CarIdx": 1, "Position": 2}]))
    assert not engine.update(replay_of(100))["session"]["static"]


def vanish(f, i):
    """Lap -1, distance -1, off the world: what iRacing sends for a moment now and then."""
    f["CarIdxLapCompleted"][i], f["CarIdxLapDistPct"][i], f["CarIdxTrackSurface"][i] = -1, -1.0, -1
    return f


def test_a_car_vanishing_at_the_line_passes_nobody(engine):
    setup(engine)

    def make(t):
        if t < 10:                         # 1 lidera, chegando na linha
            return racing({0: (5, .90), 1: (5, .95 + t * .004)}, t)
        if t < 11.5:                       # some da telemetria ao cruzar
            return vanish(racing({0: (5, .91), 1: (6, .01)}, t), 1)
        if t < 12.5:                       # volta com a distancia virada e o contador ainda atrasado
            return racing({0: (5, .92), 1: (5, .02)}, t)
        return racing({0: (5, .93), 1: (6, .03)}, t)
    run(engine, 0, 30, make)
    assert not kinds(engine, "pass")
    assert not kinds(engine, "out")


def test_a_car_that_stays_away_did_leave(engine):
    setup(engine)
    run(engine, 0, 20, lambda t: vanish(racing({0: (5, .50), 1: (5, .40)}, t), 1) if t >= 5 else racing({0: (5, .50), 1: (5, .40)}, t))
    out = kinds(engine, "out")
    assert len(out) == 1 and out[0]["i"] == 1 and 4.9 <= out[0]["t"] <= 5.3


def flagged(place, t, flag_t, **over):
    return racing(place, t, SessionState=5 if t >= flag_t else 4, **over)


def test_a_pass_after_the_flag_counts(engine):
    setup(engine)

    def make(t):   # 2 ganha aos 5 s; 1 passa 0 aos 10 s, ja na ultima volta dos dois
        return flagged({2: (10 if t >= 5 else 9, .05 if t >= 5 else .99), 0: (9, .50 + t * .002), 1: (9, .50 + t * .003 - (.005 if t < 10 else 0) + (.0 if t < 10 else -.002))}, t, 5)
    run(engine, 0, 25, make)
    p = kinds(engine, "pass")
    assert [(e["i"], e["j"], e["p"]) for e in p] == [(1, 0, 2)]


def test_a_pass_on_the_line_counts_and_the_cool_down_does_not(engine):
    setup(engine)

    def make(t):
        if t < 8:
            return flagged({2: (10, .05), 0: (9, .96), 1: (9, .95)}, t, 1)
        if t < 10:      # 1 passa 0 a 2 s da linha
            return flagged({2: (10, .05), 0: (9, .97), 1: (9, .98)}, t, 1)
        # os dois cruzam; 1 primeiro. Depois, na volta de resfriamento, 0 vai embora
        if t < 10.5:
            return flagged({2: (10, .05), 1: (10, .01), 0: (9, .99)}, t, 1)
        return flagged({2: (10, .05), 1: (10, .01), 0: (10, .01 + (t - 10.5) * .02)}, t, 1)
    run(engine, 0, 30, make)
    assert [(e["i"], e["j"]) for e in kinds(engine, "pass")] == [(1, 0)]


def test_finishing_position_is_where_the_car_is_not_where_it_was(engine):
    setup(engine)

    def make(t):   # iRacing ainda diz P3 para 1 quando ele cruza a linha em P2
        f = flagged({2: (10, .05), 1: (10 if t >= 8 else 9, .01 if t >= 8 else .98), 0: (10 if t >= 12 else 9, .01 if t >= 12 else .97)}, t, 1)
        return f
    run(engine, 0, 15, make)
    assert [(e["i"], e["p"]) for e in kinds(engine, "finish")] == [(1, 2), (0, 3)]   # o 2 ja estava na frente


def test_the_winner_is_first_even_with_the_counter_a_lap_short(engine):
    setup(engine)
    log = engine.ev

    def make(t):   # na bandeirada o contador do lider ainda nao virou (visto no iRacing): 9 + .9999
        return flagged({0: (9 if t < 6 else 10, .9999 if t < 6 else .01), 1: (9, .95), 2: (9 if t < 8 else 10, .99 if t < 8 else .01)}, t, 5, CarIdxPosition=[1, 2, 3] + [0] * 61)
    run(engine, 0, 10, make)
    assert [(e["i"], e["p"]) for e in log.items if e["k"] == "finish"] == [(0, 1), (2, 2)]


def seen_in_replay(place, t, **over):
    return racing(place, t, IsReplayPlaying=True, ReplayFrameNumEnd=6000, IsOnTrack=False, **over)


def test_the_board_stays_in_the_present_during_a_replay(engine):
    setup(engine)
    run(engine, 100, 110, lambda t: racing({0: (9, .50), 1: (9, .49)}, t))
    st = engine.update(seen_in_replay({0: (2, .10), 1: (2, .20)}, 40.0))
    assert st["session"]["kind"] == "race" and st["session"]["behind"] == 100
    assert next(c for c in st["cars"] if c["i"] == 0)["lap"] != 3   # a volta de agora, nao a do replay
    back = engine.update(racing({0: (9, .60), 1: (9, .59)}, 111))
    assert back["session"]["behind"] == 0


def test_watching_the_replay_is_out_of_the_car_whatever_the_last_live_frame_said(engine):
    setup(engine)
    run(engine, 100, 105, lambda t: racing({0: (9, .50), 1: (9, .49)}, t, IsOnTrack=True))
    assert engine.in_car
    st = engine.update(seen_in_replay({0: (2, .10), 1: (2, .20)}, 40.0))
    assert st["session"]["inCar"] is False and not engine.in_car


def test_another_session_in_the_replay_does_not_change_the_board(engine):
    setup(engine, kind="Race")
    run(engine, 100, 105, lambda t: racing({0: (9, .50), 1: (9, .49)}, t))
    st = engine.update(seen_in_replay({0: (1, .10), 1: (1, .20)}, 40.0, SessionNum=7))
    assert st["session"]["kind"] == "race"


def test_the_replay_still_feeds_the_events(engine):
    setup(engine)
    run(engine, 100, 105, lambda t: racing({0: (9, .50), 1: (9, .49)}, t))
    run(engine, 40, 60, lambda t: seen_in_replay({0: (3, .50), 1: (3, .49 if t < 45 else .51)}, t, ReplaySessionTime=t, ReplaySessionNum=0))
    assert [(e["i"], e["j"]) for e in kinds(engine, "pass")] == [(1, 0)]


def test_a_replay_records_nothing_on_the_board_engine(engine):
    setup(engine)
    run(engine, 100, 105, lambda t: racing({0: (9, .50), 1: (9, .49)}, t))
    calls = []
    engine.mapper.update = lambda *a: calls.append(a)
    run(engine, 40, 42, lambda t: seen_in_replay({0: (3, .50), 1: (3, .49)}, t))
    assert not calls


def test_positions_keep_coming_from_the_results_during_a_replay(engine):
    setup(engine)
    run(engine, 100, 105, lambda t: racing({0: (9, .50), 1: (9, .49)}, t))
    info = dict(engine._info)
    info["SessionInfo"] = {"Sessions": [{**engine.sessions[0], "ResultsPositions": [
        {"CarIdx": 1, "Position": 1, "ClassPosition": 0, "FastestTime": 90.5, "LastTime": 91.0},
        {"CarIdx": 0, "Position": 2, "ClassPosition": 1, "FastestTime": 90.9, "LastTime": 92.0}]}]}
    engine.set_session(info)
    st = engine.update(seen_in_replay({0: (3, .50), 1: (3, .49)}, 40.0))
    assert [c["i"] for c in st["cars"]][:2] == [1, 0] and st["cars"][0]["best"] == 90.5 and st["cars"][0]["cp"] == 1


def race_file(folder, key, saved, **extra):
    (folder / f"{key}.json").write_text(json.dumps({"saved": saved, "items": [], "meta": {"track": "Spa"}, **extra}), "utf-8")


def test_old_races_go_after_30_days(tmp_path):
    race_file(tmp_path, "old", 1.0)
    race_file(tmp_path, "new", 2.0)
    old = time.time() - 31 * 86400
    os.utime(tmp_path / "old.json", (old, old))
    assert purge(tmp_path) == 1
    assert [p.stem for p in tmp_path.glob("*.json")] == ["new"]


def test_a_name_from_outside_never_leaves_the_folder(tmp_path):
    race_file(tmp_path, "ok", 1.0)
    assert past_race(tmp_path, "ok")["saved"] == 1.0
    assert past_race(tmp_path, "../ok") is None and past_race(tmp_path, "") is None


def test_offline_sessions_do_not_share_a_file(engine, tmp_path):
    log = EventLog()
    log.sub, log._began = 0, 123
    log.items = [{"id": 0}]
    assert log.save(tmp_path, {"player": 1}).name == "offline-123.json"
    log._began = 124
    assert log.save(tmp_path).name == "offline-124.json"
    log.sub = 999
    assert log.key() == "999"


def test_an_offline_session_comes_back_only_if_it_was_saved_moments_ago(tmp_path):
    (tmp_path / "offline-100.json").write_text(json.dumps({"saved": 1.0, "items": []}), "utf-8")
    log = EventLog()
    log.dir = tmp_path
    assert log._recent_offline() is not None and log._began == 100
    old = time.time() - 3600
    os.utime(tmp_path / "offline-100.json", (old, old))
    assert log._recent_offline() is None


def test_a_race_saved_before_the_join_gets_its_lost_incident_back():
    from pitwall.events import mend_incidents
    items = [{"k": "inc", "sn": 2, "t": 764.3, "i": 0, "n": 1, "total": 3}, {"k": "inc", "sn": 2, "t": 946.7, "i": 0, "n": 1, "total": 4},
             {"k": "inc", "sn": 2, "t": 2049.1, "i": 0, "n": 1, "total": 6}]
    mend_incidents(items)
    assert [(e.get("n0"), e["n"], e["total"]) for e in items] == [(None, 1, 3), (1, 2, 5), (None, 1, 6)]


def test_in_qualifying_whoever_is_done_has_the_flag(engine):
    from conftest import frame, session
    engine.set_session(session(kind="Lone Qualify"))
    flags = [0] * 64
    flags[1] = 0x1
    cars = {c["i"]: c for c in engine.update(frame({0: (3, .5), 1: (3, .4)}, best={0: 99.0, 1: 98.0}, CarIdxSessionFlags=flags))["cars"]}
    assert cars[1]["fin"] and not cars[0]["fin"]
