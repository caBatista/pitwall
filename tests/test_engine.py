import pytest

from conftest import frame, session
from pitwall.engine import laps_to_flag, UNLIMITED_TIME
from pitwall.engine import (BINS, Engine, PassLog, car_flag, car_make, flag_name, hexcolor, ir_change, limit,
                            parse_km, session_kind, sof)


# ---- funcoes puras ----------------------------------------------------------
def test_sof():
    assert sof([2000]) == 2000
    assert sof([]) is None
    assert sof([0, None]) is None
    assert 1000 < sof([1000, 3000]) < 2000   # tende ao mais fraco (formula exponencial)
    assert sof([1000, 3000, 0]) == sof([1000, 3000])   # zeros ignorados


def test_ir_change():
    assert ir_change(2000, 1, [(2000, 1)]) is None   # campo de um so
    assert ir_change(None, 1, [(2000, 1), (2000, 2)]) is None
    field = [(2000, 1), (2000, 2)]
    assert ir_change(2000, 1, field) == 50
    assert ir_change(2000, 2, field) == -49
    # mais forte que o campo ganha menos ao vencer
    assert ir_change(3000, 1, [(3000, 1), (1000, 2)]) < ir_change(1000, 1, [(1000, 1), (3000, 2)])


def test_car_flag_priority():
    assert car_flag(0) is None and car_flag(None) is None
    assert car_flag(0x80000) == "warn"
    assert car_flag(0x100000 | 0x80000) == "repair"
    assert car_flag(0x10000 | 0x100000) == "black"
    assert car_flag(0x20000 | 0x10000) == "dq"


@pytest.mark.parametrize("bits,name", [
    (0, "none"), (0x1, "checkered"), (0x10, "red"), (0x10000, "black"), (0x20000, "black"),
    (0x4000, "yellow"), (0x8, "yellow"), (0x2, "white"), (0x20, "blue"), (0x4, "green"), (0x400, "green"),
    (0x1 | 0x4000, "checkered"),   # xadrez ganha de amarela
])
def test_flag_name(bits, name):
    assert flag_name(bits) == name


def test_limit():
    assert limit(17) == 17 and limit("8") == 8
    assert limit("unlimited") is None and limit(None) is None


@pytest.mark.parametrize("text,kind", [
    ("Race", "race"), ("Open Qualify", "qualify"), ("Lone Qualify", "qualify"),
    ("Offline Testing", "test"), ("Practice", "practice"), ("Warmup", "practice"), ("", "practice"), (None, "practice"),
])
def test_session_kind(text, kind):
    assert session_kind(text) == kind


def test_parse_km():
    assert parse_km("5.00 km") == 5.0
    assert parse_km("2.0 mi") == pytest.approx(3.218688)
    assert parse_km("sem unidade") is None and parse_km(None) is None


def test_hexcolor():
    assert hexcolor(0xFF0000) == "#ff0000"
    assert hexcolor("0xff8800") == "#ff8800"
    assert hexcolor("255") == "#0000ff"
    assert hexcolor(-1) == "#8b95a7" and hexcolor(None) == "#8b95a7"
    assert hexcolor("lixo", "#000") == "#000"


@pytest.mark.parametrize("path,make", [
    ("porsche911gt3r", "porsche"), ("chevyvette", "corvette"), ("amvantage", "astonmartin"),
    ("mx5 mx52016", "mazda"), ("BMWM4GT3", "bmw"), ("", ""), (None, ""), ("carroinexistente", ""),
])
def test_car_make(path, make):
    assert car_make(path) == make


# ---- PassLog ----------------------------------------------------------------
def feed_two(log, secs=20.0, step=0.1, lap_time=100.0, gap=5.0):
    """Carro 0 na frente, carro 1 `gap` segundos atras, mesma velocidade constante."""
    n = int(round(secs / step))
    for k in range(n + 1):
        t = k * step
        log.feed(0, ((t + gap) / lap_time) % 1.0, t)
        log.feed(1, (t / lap_time) % 1.0, t)
    return n * step


def test_passlog_gap_between_cars_at_constant_speed():
    log = PassLog()
    now = feed_two(log)
    # o carro 1 esta agora onde o 0 estava ha 5 s
    s = log.since(0, (now / 100.0) % 1.0, now)
    assert s == pytest.approx(5.0, abs=0.05)


def test_passlog_unknown_car_or_bin():
    log = PassLog()
    assert log.since(7, 0.5, 10.0) is None
    log.feed(7, 0.10, 0.0)
    assert log.since(7, 0.60, 10.0) is None   # nunca passou por la


def test_passlog_jump_does_not_invent_data():
    log = PassLog()
    log.feed(0, 0.10, 0.0)
    log.feed(0, 0.50, 0.1)   # pulo de 40% da volta em 0,1 s (reset/tow)
    filled = [b for b, v in enumerate(log.tab[0]) if v is not None]
    assert filled == [int(0.10 * BINS), int(0.50 * BINS)]


def test_passlog_time_reset_or_long_gap_writes_single_bin():
    log = PassLog()
    log.feed(0, 0.10, 100.0)
    log.feed(0, 0.12, 50.0)   # relogio voltou (rewind)
    log.feed(0, 0.13, 60.0)   # >3 s depois do anterior
    filled = [b for b, v in enumerate(log.tab[0]) if v is not None]
    assert filled == [int(0.10 * BINS), int(0.12 * BINS), int(0.13 * BINS)]


def test_passlog_stopped_car_keeps_old_crossing_and_gap_grows():
    log = PassLog()
    for k in range(11):   # anda ate 0.05 e para
        log.feed(0, 0.005 * k, k * 0.1)
    before = list(log.tab[0])
    for k in range(11, 60):
        log.feed(0, 0.05, k * 0.1)
    assert log.tab[0] == before   # parado nao reescreve nada
    assert log.since(0, 0.04, 20.0) > 18.0   # "ha quanto tempo passou" so cresce


# ---- Engine.update ----------------------------------------------------------
def ids(state):
    return [c["i"] for c in state["cars"]]


def car(state, i):
    return next(c for c in state["cars"] if c["i"] == i)


def test_race_live_order_by_distance_not_iracing_position(engine):
    engine.set_session(session([0, 1, 2], "Race"))
    st = engine.update(frame(place={0: (2, 0.30), 1: (2, 0.60), 2: (1, 0.90)},
                             pos={0: 1, 1: 2, 2: 3}, SessionState=4, SessionTime=100.0))
    assert ids(st) == [1, 0, 2]
    assert [c["p"] for c in st["cars"]] == [1, 2, 3]


def test_race_grid_frozen_before_green(engine):
    qual = [{"CarIdx": 2, "Position": 0, "FastestTime": 90.0}, {"CarIdx": 0, "Position": 1, "FastestTime": 91.0},
            {"CarIdx": 1, "Position": 2, "FastestTime": 92.0}]
    engine.set_session(session([0, 1, 2], "Race", qualify=qual))
    # na volta de apresentacao os carros estao em outra ordem na pista e o iRacing diz outra posicao
    st = engine.update(frame(place={0: (0, 0.50), 1: (0, 0.90), 2: (0, 0.10)},
                             pos={0: 3, 1: 1, 2: 2}, SessionState=3, SessionTime=10.0))
    assert ids(st) == [2, 0, 1]
    # Last/Fastest antes do verde sao os tempos do quali
    assert {c["i"]: c["best"] for c in st["cars"]} == {2: 90.0, 0: 91.0, 1: 92.0}


def test_race_official_result_after_checkered(engine):
    res = [{"CarIdx": 1, "Position": 1, "LapsComplete": 10, "Time": 900.0},
           {"CarIdx": 0, "Position": 2, "LapsComplete": 10, "Time": 903.5},
           {"CarIdx": 2, "Position": 3, "LapsComplete": 9, "Time": 905.0}]
    engine.set_session(session([0, 1, 2], "Race", results=res))
    st = engine.update(frame(place={0: (10, 0.90), 1: (10, 0.10), 2: (10, 0.95)},   # na pista o 2 esta a frente
                             SessionState=5, SessionTime=1000.0))
    assert ids(st) == [1, 0, 2]
    assert car(st, 0)["li"] == 0 and car(st, 0)["gi"] == pytest.approx(3.5)
    assert car(st, 2)["li"] == 1   # uma volta atras no resultado


def test_non_race_without_lap_time_has_no_position(engine):
    engine.set_session(session([0, 1, 2], "Open Qualify"))
    st = engine.update(frame(place={0: (3, 0.2), 1: (3, 0.4), 2: (0, 0.1)}, best={0: 92.0, 1: 90.5}, SessionTime=50.0))
    assert (car(st, 1)["p"], car(st, 0)["p"]) == (1, 2)
    assert car(st, 2)["p"] is None and car(st, 2)["cp"] is None
    assert ids(st)[-1] == 2   # sem tempo vai para o fim
    assert car(st, 0)["gl"] == pytest.approx(1.5)   # diferenca de melhor volta para o lider da classe


def test_lapped_car_reports_laps_down(engine):
    engine.set_session(session([0, 1, 2], "Race"))
    st = engine.update(frame(place={0: (5, 0.5), 1: (3, 0.5), 2: (4, 0.5)}, SessionState=4, SessionTime=300.0))
    assert car(st, 1)["ld"] == 2 and car(st, 1)["gl"] is None
    assert car(st, 2)["ld"] == 1
    assert car(st, 0)["ld"] == 0 and car(st, 0)["gl"] is None   # lider
    assert car(st, 1)["li"] == 1   # intervalo para quem esta logo a frente (carro 2)


def test_gap_in_seconds_uses_distance_when_no_passlog(engine):
    engine.set_session(session([0, 1], "Race"))
    st = engine.update(frame(place={0: (2, 0.52), 1: (2, 0.50)}, SessionState=4, SessionTime=200.0))
    c1 = car(st, 1)
    assert c1["ld"] == 0 and c1["gl"] == pytest.approx(2.0)   # 0,02 volta x 100 s


def test_the_gap_is_iracings_own(engine):
    engine.set_session(session([0, 1, 2], "Race"))
    f2 = [0.0] * 64
    f2[1], f2[2] = 3.25, 7.5
    st = engine.update(frame(place={0: (2, 0.60), 1: (2, 0.50), 2: (2, 0.40)}, SessionState=4, SessionTime=200.0, CarIdxF2Time=f2))
    assert car(st, 1)["gl"] == pytest.approx(3.25) and car(st, 2)["gl"] == pytest.approx(7.5)
    assert car(st, 2)["gi"] == pytest.approx(4.25)


def test_no_gap_from_iracing_yet_uses_ours(engine):
    engine.set_session(session([0, 1], "Race"))
    st = engine.update(frame(place={0: (2, 0.52), 1: (2, 0.50)}, SessionState=4, SessionTime=200.0, CarIdxF2Time=[0.0] * 64))
    assert car(st, 1)["gl"] == pytest.approx(2.0)


def test_relative_is_iracings_estimate_not_the_elapsed_time(engine):
    engine.set_session(session([0, 1], "Race"))
    est = [0.0] * 64
    est[0], est[1] = 50.0, 54.0
    place = lambda t: {0: (2, 0.50), 1: (2, 0.54)}
    for k, p in enumerate((.40, .45, .50)):   # I came slowly to .50: the PassLog says much more than 4 s
        engine.update(frame(place={0: (2, p), 1: (2, .54 + k * .01)}, SessionState=4, SessionTime=200.0 + k * 10, CarIdxEstTime=est))
    st = engine.update(frame(place=place(0), SessionState=4, SessionTime=230.0, CarIdxEstTime=est))
    assert st["rel"][0]["dt"] == pytest.approx(4.0)


def test_class_name_when_the_session_gives_none(engine):
    cars = [{"CarIdx": 0, "CarClassID": 4029, "CarClassShortName": None, "CarScreenName": "Acura ARX-06"},
            {"CarIdx": 1, "CarClassID": 4011, "CarClassShortName": None, "CarScreenName": "Acura NSX GT3 EVO 22"},
            {"CarIdx": 2, "CarClassID": 77, "CarClassShortName": None, "CarScreenName": "Dallara P217 LMP2"},
            {"CarIdx": 3, "CarClassID": 78, "CarClassShortName": None, "CarScreenName": "Mazda MX-5"},
            {"CarIdx": 4, "CarClassID": 79, "CarClassShortName": "GT3 Class", "CarScreenName": "BMW M4 GT3"}]
    engine.set_session(session(cars))
    names = {c["id"]: c["name"] for c in engine.classes.values()}
    assert names == {4029: "GTP", 4011: "GT3", 77: "LMP2", 78: "Mazda MX-5", 79: "GT3 Class"}


def test_relative_rescales_each_car_inside_a_class(engine):
    """Spa: BMW 134,10 e Porsche 133,46, mesma classe. Sem isso, 0,6 s a mais no fim da volta."""
    engine.set_session(session([{"CarIdx": 0, "CarClassEstLapTime": 133.46}, {"CarIdx": 1, "CarClassEstLapTime": 134.10}]))
    est = [0.0] * 64
    est[0], est[1] = 127.0, 129.3
    st = engine.update(frame(place={0: (2, .950), 1: (2, .965)}, SessionState=4, SessionTime=200.0, CarIdxEstTime=est))
    assert st["rel"][0]["dt"] == pytest.approx(129.3 - 127.0 * 134.10 / 133.46, abs=.01)


def test_relative_ahead_and_behind(engine):
    engine.set_session(session([0, 1, 2], "Race"))
    st = engine.update(frame(place={0: (2, 0.50), 1: (2, 0.52), 2: (2, 0.48)}, SessionState=4, SessionTime=200.0))
    assert [r["i"] for r in st["rel"]] == [1, 2]
    assert st["rel"][0]["dt"] == pytest.approx(2.0) and st["rel"][1]["dt"] == pytest.approx(-2.0)
    assert all(r["dl"] == 0 for r in st["rel"])


def test_relative_lap_difference_only_after_green(engine):
    engine.set_session(session([0, 1], "Race"))
    place = {0: (1, 0.50), 1: (2, 0.52)}   # o 1 esta uma volta a frente
    racing = engine.update(frame(place=place, SessionState=4, SessionTime=200.0))
    assert racing["rel"][0]["dl"] == 1
    pre = engine.update(frame(place=place, SessionState=3, SessionTime=201.0))
    assert pre["rel"][0]["dl"] == 0


def test_relative_empty_when_focused_car_not_on_track(engine):
    engine.set_session(session([0, 1], "Race"))
    st = engine.update(frame(place={1: (2, 0.5)}, SessionState=4, SessionTime=5.0))
    assert st["rel"] == []


def test_focus_follows_cam_car_and_falls_back_to_player(engine):
    engine.set_session(session([0, 1, 2], "Race"))
    place = {0: (2, 0.5), 1: (2, 0.6), 2: (2, 0.4)}
    st = engine.update(frame(place=place, CamCarIdx=1, SessionTime=10.0, PlayerCarMyIncidentCount=3))
    assert st["me"]["i"] == 1
    assert st["me"]["inc"] is None   # incidentes so do proprio jogador
    assert sorted(r["i"] for r in st["rel"]) == [0, 2]   # relative em torno do foco
    st = engine.update(frame(place=place, CamCarIdx=99, SessionTime=10.1))
    assert st["me"]["i"] == 0


def test_session_change_resets_lap_history(engine):
    engine.set_session(session([0, 1], "Race"))
    place = {0: (1, 0.5), 1: (1, 0.4)}
    engine.update(frame(place=place, SessionTime=1.0))
    engine.update(frame(place=place, SessionTime=2.0))
    st = engine.update(frame(place=place, last={1: 91.234}, SessionTime=3.0))
    assert car(st, 1)["lh"] == [91.234]
    st = engine.update(frame(place=place, last={1: 91.234}, SessionNum=1, SessionTime=4.0))
    assert car(st, 1)["lh"] == []


def test_race_over_after_flag_and_crossing_line_or_in_cool_down(engine, tmp_path):
    engine.set_session(session([0, 1], "Race"))
    place = {0: (10, 0.90), 1: (10, 0.95)}
    assert engine.update(frame(place=place, SessionState=4, SessionTime=1.0))["session"]["over"] is False
    # bandeirada, eu ainda andando antes da linha
    assert engine.update(frame(place=place, SessionState=5, SessionTime=2.0))["session"]["over"] is False
    # cruzei a linha
    st = engine.update(frame(place={0: (11, 0.02), 1: (10, 0.97)}, SessionState=5, SessionTime=3.0))
    assert st["session"]["over"] is True
    # cool down e sempre "over"
    e2 = Engine(engine.mapper)
    e2.set_session(session([0, 1], "Race"))
    assert e2.update(frame(place=place, SessionState=6, SessionTime=1.0))["session"]["over"] is True


def test_invalid_lap_is_timed_by_engine_and_marked(engine):
    engine.set_session(session([0, 1], "Race"))
    # o carro 1 cruza a linha duas vezes, a 2a sem tempo oficial (volta invalidada)
    for t, lap, p in [(99.0, 1, 0.9), (100.0, 1, 0.99), (100.1, 2, 0.005), (190.0, 2, 0.99), (190.1, 3, 0.005)]:
        engine.update(frame(place={0: (1, 0.3), 1: (lap, p)}, SessionState=4, SessionTime=t))
    st = engine.update(frame(place={0: (1, 0.3), 1: (3, 0.06)}, SessionState=4, SessionTime=194.0))
    c = car(st, 1)
    assert c["lastx"] is True
    assert c["last"] == pytest.approx(90.0, abs=0.2)
    assert c["lx"][0] is True


def test_valid_lap_with_official_time_is_not_marked(engine):
    engine.set_session(session([0, 1], "Race"))
    for t, lap, p in [(99.0, 1, 0.9), (100.0, 1, 0.99), (100.1, 2, 0.005), (190.0, 2, 0.99)]:
        engine.update(frame(place={0: (1, 0.3), 1: (lap, p)}, SessionState=4, SessionTime=t))
    engine.update(frame(place={0: (1, 0.3), 1: (3, 0.005)}, last={1: 89.9}, SessionState=4, SessionTime=190.1))
    st = engine.update(frame(place={0: (1, 0.3), 1: (3, 0.06)}, last={1: 89.9}, SessionState=4, SessionTime=195.0))
    c = car(st, 1)
    assert "lastx" not in c and c["last"] == 89.9


# ---- fuel_needed ------------------------------------------------------------
def test_fuel_needed(engine):
    engine.tank = 100.0
    engine._fuel_now = (None, None, None)
    assert engine.fuel_needed(1.0, 10) is None   # sem media de voltas limpas
    engine._fuel_now = (10.0, 2.0, 5.0)   # nivel, media, voltas restantes
    assert engine.fuel_needed(1.0, 99) == pytest.approx(2.0)   # (5+1)*2-10; usa as voltas da sessao
    engine._fuel_now = (10.0, 2.0, None)
    assert engine.fuel_needed(0.0, 8) == pytest.approx(6.0)   # cai nas voltas digitadas
    assert engine.fuel_needed(0.0, None) is None


def test_fuel_needed_capped_by_tank_and_zero_when_enough(engine):
    engine.tank = 50.0
    engine._fuel_now = (10.0, 2.0, 30.0)
    assert engine.fuel_needed(0.0, None) == pytest.approx(40.0)   # precisaria de 50, cabe 40
    engine._fuel_now = (60.0, 2.0, 5.0)
    assert engine.fuel_needed(0.0, None) == 0.0


# ---- laps to the flag --------------------------------------------------------
def test_laps_to_flag_lap_race():
    assert laps_to_flag(9.3, 100, 9.3, 100, laps_total=10) == pytest.approx(0.7)   # I am the leader
    assert laps_to_flag(9.9, 100, 9.7, 100, laps_total=10) == pytest.approx(0.3)   # same lap, just behind
    assert laps_to_flag(9.9, 100, 8.7, 100, laps_total=10) == pytest.approx(0.3)   # lapped: one lap less


def test_laps_to_flag_timed_race_goes_by_the_leader():
    # the leader crossed the line just before zero: a whole lap more, and I then finish mine
    assert laps_to_flag(20.001, 100, 19.5, 100, time_rem=0.5) == pytest.approx(1.5)
    # my own clock (0.5 s, half a lap to the line) would have said 0.5: a lap of fuel short
    assert laps_to_flag(20.9, 100, 20.9, 100, time_rem=0.0) == pytest.approx(0.1)
    assert laps_to_flag(10.0, 100, 10.0, 100, time_rem=1000.0) == pytest.approx(10.0)


def test_laps_to_flag_my_stop_to_come():
    # Spa, 40 min: at the pit entry, end of lap 12, ahead of a leader who already stopped and has 6.08 to go
    t = 748.3
    assert laps_to_flag(11.92, 136.3, 11.988, 136.3, time_rem=t) == pytest.approx(7.012)
    assert laps_to_flag(11.92, 136.3, 11.988, 136.3, time_rem=t, stop=25.0) == pytest.approx(6.012)
    # leading, my stop moves the flag too: without it the clock runs out just into another lap
    assert laps_to_flag(10.0, 100, 10.0, 100, time_rem=610.0) == pytest.approx(7.0)
    assert laps_to_flag(10.0, 100, 10.0, 100, time_rem=610.0, stop=25.0) == pytest.approx(6.0)


def test_laps_to_flag_both_limits_first_one_wins():
    assert laps_to_flag(5.0, 100, 5.0, 100, laps_total=8, time_rem=100000) == pytest.approx(3.0)
    assert laps_to_flag(5.0, 100, 5.0, 100, laps_total=80, time_rem=250) == pytest.approx(3.0)


def test_laps_to_flag_slower_car_does_fewer_laps():
    assert laps_to_flag(0.0, 100, 0.0, 125, laps_total=10) == pytest.approx(8.0)


def test_24h_race_is_not_unlimited():
    assert 86400 < UNLIMITED_TIME < 604800


# ---- lap counter and lap distance at the line ---------------------------------
def test_distance_does_not_jump_when_counter_lags(engine):
    assert engine.lap_fix(1, 5, 0.99, 10.0) == 0
    assert engine.lap_fix(1, 5, 0.01, 10.05) == 1     # distance wrapped first
    assert engine.lap_fix(1, 5, 0.02, 10.10) == 1
    assert engine.lap_fix(1, 6, 0.03, 10.15) == 0     # the counter caught up


def test_distance_does_not_jump_when_counter_leads(engine):
    assert engine.lap_fix(1, 5, 0.99, 10.0) == 0
    assert engine.lap_fix(1, 6, 0.995, 10.05) == -1
    assert engine.lap_fix(1, 6, 0.01, 10.10) == 0


def test_a_tow_is_not_taken_for_a_crossing_for_long(engine):
    engine.lap_fix(1, 5, 0.9, 10.0)
    assert engine.lap_fix(1, 5, 0.1, 10.1) == 1
    assert engine.lap_fix(1, 5, 0.1, 13.0) == 0
