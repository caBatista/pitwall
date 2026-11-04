"""Helpers para testar o engine sem iRacing: quadros `raw` e `SessionInfo` sinteticos."""
import pytest

from pitwall.engine import Engine
from pitwall.trackmap import TrackMapper

N = 64


def frame(place=None, pos=None, last=None, best=None, **over):
    """Quadro `raw` minimo e valido (arrays de 64).

    place: {idx: (voltas_completas, pct)}; o carro fica na pista (surf 3).
    pos: {idx: CarIdxPosition}; last/best: {idx: tempo}. over sobrescreve qualquer chave.
    """
    raw = {
        "SessionTime": 0.0, "SessionNum": 0, "SessionState": 4, "SessionFlags": 0,
        "PlayerCarIdx": 0, "CamCarIdx": 0,
        "CarIdxLapCompleted": [-1] * N, "CarIdxLapDistPct": [-1.0] * N,
        "CarIdxTrackSurface": [-1] * N, "CarIdxOnPitRoad": [0] * N,
        "CarIdxPosition": [0] * N, "CarIdxLastLapTime": [-1.0] * N,
        "CarIdxBestLapTime": [-1.0] * N, "CarIdxSessionFlags": [0] * N,
        "CarIdxTireCompound": [-1] * N,
        "IsOnTrack": True, "OnPitRoad": False, "Speed": 0.0, "YawNorth": 0.0, "LapDistPct": 0.0,
    }
    for i, (lap, pct) in (place or {}).items():
        raw["CarIdxLapCompleted"][i] = lap
        raw["CarIdxLapDistPct"][i] = pct
        raw["CarIdxTrackSurface"][i] = 3
    for i, p in (pos or {}).items():
        raw["CarIdxPosition"][i] = p
    for i, v in (last or {}).items():
        raw["CarIdxLastLapTime"][i] = v
    for i, v in (best or {}).items():
        raw["CarIdxBestLapTime"][i] = v
    raw.update(over)
    return raw


def session(drivers=(0, 1, 2), kind="Race", results=None, qualify=None, sub_id=1, tank=None, **extra):
    """Dict de `set_session`. drivers: CarIdx (int) ou dicts de DriverInfo.Drivers.
    results: ResultsPositions da sessao 0; qualify: QualifyResultsInfo.Results."""
    ds = []
    for d in drivers:
        d = dict(d) if isinstance(d, dict) else {"CarIdx": d}
        i = d["CarIdx"]
        d.setdefault("UserName", f"Driver {chr(65 + i)}")
        d.setdefault("CarNumber", str(i + 1))
        d.setdefault("CarClassID", 1)
        d.setdefault("CarClassShortName", "GT3")
        d.setdefault("CarClassEstLapTime", 100.0)
        d.setdefault("CarPath", "porsche911gt3r")
        d.setdefault("IRating", 2000)
        ds.append(d)
    sess = {"SessionNum": 0, "SessionType": kind}
    if results is not None:
        sess["ResultsPositions"] = results
    info = {
        "WeekendInfo": {"TrackID": 1, "TrackConfigName": "", "TrackLength": "5.00 km", "SubSessionID": sub_id,
                        "TrackDisplayName": "Test Ring"},
        "DriverInfo": {"DriverCarIdx": 0, "Drivers": ds,
                       **({"DriverCarFuelMaxLtr": tank, "DriverCarMaxFuelPct": 1.0} if tank else {})},
        "SessionInfo": {"Sessions": [sess]},
    }
    if qualify is not None:
        info["QualifyResultsInfo"] = {"Results": qualify}
    info.update(extra)
    return info


@pytest.fixture
def engine(tmp_path):
    return Engine(TrackMapper(tmp_path))
