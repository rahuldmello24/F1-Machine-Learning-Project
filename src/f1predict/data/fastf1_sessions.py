"""FastF1 session data for the seasons OpenF1 doesn't cover (2018–2022).

Since October 2026 F1's timing archive (livetiming.formula1.com) needs an
F1 TV Access sign-in. FastF1 3.9+ signs in with your own account: set
``F1_USERNAME`` and ``F1_PASSWORD`` in your shell (never commit them),
or run interactively and FastF1 will prompt. Tokens last about four
days, so this is meant to be run occasionally on your own machine; the
resulting parquet files are all the rest of the pipeline needs.

Per session we keep the lap table (lap and sector times, tyre compound
and age, stint, pit in/out, track status, deleted laps) and weather.
The FastF1 HTTP cache is wiped after each event to keep disk usage flat.
"""

from __future__ import annotations

import logging
import shutil

import pandas as pd

from f1predict.paths import FASTF1_CACHE, FASTF1_OUT, ensure

log = logging.getLogger(__name__)

YEARS = (2018, 2019, 2020, 2021, 2022)
SESSIONS = {
    "Practice 1": "FP1",
    "Practice 2": "FP2",
    "Practice 3": "FP3",
    "Qualifying": "Q",
    "Sprint Qualifying": "SQ",
    "Sprint Shootout": "SQ",
    "Sprint": "SR",
    "Race": "R",
}
LAP_COLS = [
    "DriverNumber", "Driver", "Team", "LapNumber", "LapTime", "Sector1Time", "Sector2Time", "Sector3Time",
    "SpeedI1", "SpeedI2", "SpeedFL", "SpeedST", "Compound", "TyreLife", "FreshTyre", "Stint",
    "PitInTime", "PitOutTime", "TrackStatus", "Position", "Deleted", "IsAccurate", "LapStartTime",
]


def _session_path(year: int, rnd: int, code: str):
    return FASTF1_OUT / "sessions" / f"{year}_{rnd:02d}_{code}"


def fetch(years=YEARS) -> None:
    import fastf1  # optional dependency

    fastf1.set_log_level("ERROR")
    for year in years:
        schedule = fastf1.get_event_schedule(year, include_testing=False)
        for _, ev in schedule.iterrows():
            rnd = int(ev["RoundNumber"])
            ensure(FASTF1_CACHE)
            fastf1.Cache.enable_cache(str(FASTF1_CACHE))
            for i in range(1, 6):
                name = ev.get(f"Session{i}")
                code = SESSIONS.get(name)
                if not code:
                    continue
                out = _session_path(year, rnd, code)
                if (out / "laps.parquet").exists():
                    continue
                try:
                    s = fastf1.get_session(year, rnd, name)
                    s.load(laps=True, telemetry=False, weather=True, messages=True)
                    laps = s.laps
                except Exception as exc:  # missing or broken session upstream
                    log.warning("%d R%02d %s: %s", year, rnd, code, exc)
                    continue
                ensure(out)
                lp = pd.DataFrame(laps)[[c for c in LAP_COLS if c in laps.columns]].copy()
                for c in lp.columns:
                    if pd.api.types.is_timedelta64_dtype(lp[c]):
                        lp[c] = lp[c].dt.total_seconds()
                lp.insert(0, "session", code)
                lp.insert(0, "round", rnd)
                lp.insert(0, "year", year)
                lp.to_parquet(out / "laps.parquet", index=False)
                if s.weather_data is not None and len(s.weather_data):
                    w = s.weather_data.copy()
                    w["Time"] = w["Time"].dt.total_seconds()
                    w.assign(year=year, round=rnd, session=code).to_parquet(out / "weather.parquet", index=False)
                log.info("%d R%02d %-3s %4d laps", year, rnd, code, len(lp))
            shutil.rmtree(FASTF1_CACHE, ignore_errors=True)


def tidy(jolpica_results: pd.DataFrame) -> dict[str, pd.DataFrame]:
    sess_dir = FASTF1_OUT / "sessions"
    laps = pd.concat([pd.read_parquet(p) for p in sorted(sess_dir.glob("*/laps.parquet"))], ignore_index=True)
    weather = pd.concat([pd.read_parquet(p) for p in sorted(sess_dir.glob("*/weather.parquet"))], ignore_index=True)
    carmap = (
        jolpica_results.dropna(subset=["car_number"])
        .assign(DriverNumber=lambda d: d["car_number"].astype(int).astype(str))
        .drop_duplicates(["year", "round", "DriverNumber"])[["year", "round", "DriverNumber", "driver", "team"]]
        .rename(columns={"team": "team_ref"})
    )
    laps = laps.merge(carmap, on=["year", "round", "DriverNumber"], how="left")
    laps.to_parquet(FASTF1_OUT / "laps.parquet", index=False)
    weather.to_parquet(FASTF1_OUT / "weather.parquet", index=False)
    log.info("fastf1/laps: %d rows, weather: %d rows", len(laps), len(weather))
    return {"laps": laps, "weather": weather}


def load(name: str) -> pd.DataFrame:
    return pd.read_parquet(FASTF1_OUT / f"{name}.parquet")
