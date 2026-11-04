import pytest

from pitwall.engine import FuelTracker


def run_laps(ft, usages, fuel=100.0, start_lap=0, **kw):
    """Completa voltas limpas gastando `usages` litros cada; devolve (lap, fuel) finais."""
    lap = start_lap
    ft.update(lap, fuel, 90.0, False, "none", True)
    for u in usages:
        lap += 1
        fuel -= u
        ft.update(lap, fuel, 90.0, kw.get("on_pit_at_line", False), "none", True)
    return lap, fuel


def test_first_lap_never_counts_then_clean_laps_are_recorded():
    ft = FuelTracker()
    run_laps(ft, [3.0, 2.0, 2.0])
    assert list(ft.hist) == [2.0, 2.0]   # a 1a volta (incompleta) fica de fora
    assert ft.avg == 2.0
    assert ft.avg_time == 90.0


def test_no_data_means_no_average():
    ft = FuelTracker()
    assert ft.avg is None and ft.avg_time is None


def test_pit_during_lap_invalidates_it():
    ft = FuelTracker()
    lap, fuel = run_laps(ft, [2.0, 2.0])
    ft.update(lap, fuel - 1, 90.0, True, "none", True)   # passou pelo pit road no meio da volta
    ft.update(lap + 1, fuel - 2, 90.0, False, "none", True)
    assert len(ft.hist) == 1   # so a volta limpa anterior


def test_yellow_flag_invalidates_lap():
    ft = FuelTracker()
    lap, fuel = run_laps(ft, [2.0, 2.0])
    ft.update(lap, fuel - 1, 90.0, False, "yellow", True)
    ft.update(lap + 1, fuel - 1.5, 90.0, False, "none", True)
    assert len(ft.hist) == 1


def test_refuelling_invalidates_lap():
    ft = FuelTracker()
    lap, fuel = run_laps(ft, [2.0, 2.0])
    ft.update(lap, fuel + 20, 90.0, False, "none", True)   # combustivel subiu
    ft.update(lap + 1, fuel + 18, 90.0, False, "none", True)
    assert len(ft.hist) == 1


def test_off_track_invalidates_lap():
    ft = FuelTracker()
    lap, fuel = run_laps(ft, [2.0, 2.0])
    ft.update(lap, fuel - 1, 90.0, False, "none", False)
    ft.update(lap + 1, fuel - 2, 90.0, False, "none", True)
    assert len(ft.hist) == 1


def test_average_uses_only_last_eight_laps():
    ft = FuelTracker()
    laps = [3.0 + u / 100 for u in range(1, 11)]
    run_laps(ft, [1.0] + laps)   # 1a volta ignorada, depois 10 voltas parecidas
    assert len(ft.hist) == 10
    assert ft.avg == pytest.approx(sum(laps[2:]) / 8)


def test_reset_clears_everything():
    ft = FuelTracker()
    run_laps(ft, [2.0, 2.0, 2.0])
    ft.reset()
    assert ft.avg is None and not ft.hist


def test_a_lap_far_from_the_others_does_not_move_the_average():
    f = FuelTracker()
    f.hist.extend([3.0, 3.1, 2.9, 1.2, 3.0])   # a spin
    assert f.avg == pytest.approx(3.0)
    f.reset()
    f.hist.extend([3.0, 1.0])                  # too few to tell which one is off
    assert f.avg == pytest.approx(2.0)
