"""O piloto de referencia (destaque do Standings, Relative, mapa) e sempre o carro da camera do iRacing."""
from conftest import frame, session

CARS = {0: (5, .50), 1: (5, .45), 2: (5, .40)}


def ref(engine, **over):
    return engine.update(frame(CARS, pos={0: 1, 1: 2, 2: 3}, SessionTime=over.pop("SessionTime", 500.0), **over))["me"]["i"]


def test_in_my_car_it_is_me(engine):
    engine.set_session(session())
    assert ref(engine) == 0


def test_the_camera_on_another_car_makes_it_the_reference(engine):
    engine.set_session(session())
    assert ref(engine, CamCarIdx=2) == 2
    assert ref(engine, CamCarIdx=1, IsOnTrack=False) == 1


def test_a_camera_on_nobody_of_the_field_falls_back_to_me(engine):
    engine.set_session(session())
    assert ref(engine, CamCarIdx=40) == 0   # pace car, or a car gone from the field
    assert ref(engine, CamCarIdx=None) == 0


def test_in_the_replay_it_is_the_car_on_camera_not_the_last_live_frame(engine):
    engine.set_session(session())
    ref(engine, CamCarIdx=0, IsOnTrack=False, IsReplayPlaying=True, ReplayFrameNumEnd=1)   # live
    assert ref(engine, CamCarIdx=2, IsOnTrack=False, IsReplayPlaying=True, ReplayFrameNumEnd=6000) == 2


def test_after_the_flag_and_in_the_finished_race_it_still_follows_the_camera(engine):
    engine.set_session(session(results=[{"CarIdx": 0, "Position": 1}, {"CarIdx": 1, "Position": 2}, {"CarIdx": 2, "Position": 3}]))
    assert ref(engine, SessionState=6, IsOnTrack=False, CamCarIdx=1) == 1
    info = session(results=[{"CarIdx": 0, "Position": 1, "LapsComplete": 9}, {"CarIdx": 1, "Position": 2}, {"CarIdx": 2, "Position": 3}])
    info["SessionInfo"]["Sessions"][0]["ResultsOfficial"] = 1
    engine.set_session(info)
    st = engine.update(frame(CARS, IsOnTrack=False, CamCarIdx=2, IsReplayPlaying=True, ReplayFrameNumEnd=6000))
    assert st["me"]["i"] == 2 and st["user"]["i"] == 0


def test_in_qualifying_and_practice_too(engine):
    for kind in ("Lone Qualify", "Practice"):
        engine.set_session(session(kind=kind))
        assert ref(engine, CamCarIdx=1, IsOnTrack=False) == 1
