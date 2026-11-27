"""Jolpica-F1: the community successor to the Ergast API.

Two ways in:

1. **Database dump.** Jolpica publishes the whole database (1950 to now)
   as a zip of CSVs, refreshed with a short delay. One download replaces
   thousands of rate-limited API calls.
2. **API top-up.** Races that happened after the dump was cut are fetched
   from ``api.jolpi.ca/ergast/f1`` and appended.

Both are normalised into the same tidy tables, keyed by human-readable
references (``max_verstappen``, ``red_bull``, ``monaco``) so they join
cleanly with each other and with OpenF1/FastF1 later on.

Output tables (``data/processed/jolpica/*.parquet``):

``rounds``            one row per Grand Prix weekend
``results``           race (``R``) and sprint (``SR``) classifications
``qualifying``        Q1/Q2/Q3 (and sprint-qualifying) best laps and final rank
``laps``              lap-by-lap times and running positions (1996+)
``pitstops``          stop number, lap and duration (2011+)
``driver_standings``  championship table after every round
``team_standings``    constructors' table after every round
"""

from __future__ import annotations

import io
import logging
import zipfile
from datetime import date

import numpy as np
import pandas as pd

from f1predict.http import PoliteSession
from f1predict.paths import JOLPICA_OUT, JOLPICA_RAW, ensure

log = logging.getLogger(__name__)

API = "https://api.jolpi.ca/ergast/f1"
DUMP_URL = "https://api.jolpi.ca/data/dumps/download/delayed/?dump_type=csv"

# Jolpica's numeric session-entry status codes, checked against the
# free-text ``detail`` column of the dump.
OUTCOME = {
    0: "finished",
    1: "lapped",  # classified, one or more laps down
    10: "dnf_incident",  # accident, collision, spin: driver/racing incident
    11: "dnf_mechanical",  # engine, gearbox, hydraulics...
    20: "dsq",
    30: "dns",
    40: "dnq",
}

QUALI_SEGMENTS = {"Q1": 1, "Q2": 2, "Q3": 3}
SPRINT_QUALI_SEGMENTS = {"SQ1": 1, "SQ2": 2, "SQ3": 3}
# Single-session formats used before 2006 (QB = best of two sessions,
# QA = aggregate, QO = one-shot). Treat them as a single segment.
LEGACY_QUALI = {"QB", "QA", "QO"}


# ---------------------------------------------------------------- helpers
def _seconds(s: pd.Series) -> pd.Series:
    """'01:31:55.593' / '1:23.456' / '23.456' -> float seconds."""
    s = s.astype("string").str.strip()
    out = pd.Series(np.nan, index=s.index, dtype="float64")
    mask = s.notna() & (s != "")
    parts = s[mask].str.split(":")
    n = parts.str.len()
    vals = pd.Series(np.nan, index=parts.index, dtype="float64")
    for k in (1, 2, 3):
        sel = n == k
        if not sel.any():
            continue
        p = pd.DataFrame(parts[sel].tolist(), index=parts[sel].index).apply(pd.to_numeric, errors="coerce")
        weights = [3600, 60, 1][-k:]
        vals[sel] = sum(p[i] * w for i, w in enumerate(weights))
    out[mask] = vals
    return out


def _bool(s: pd.Series) -> pd.Series:
    return s.map({"t": True, "f": False, True: True, False: False}).astype("boolean")


# ----------------------------------------------------------------- dump
def download_dump(force: bool = False, http: PoliteSession | None = None) -> zipfile.ZipFile:
    ensure(JOLPICA_RAW)
    path = JOLPICA_RAW / "jolpica-f1-csv.zip"
    if force or not path.exists():
        http = http or PoliteSession()
        log.info("Downloading Jolpica database dump ...")
        resp = http.get(DUMP_URL, allow_redirects=True)
        resp.raise_for_status()
        path.write_bytes(resp.content)
        log.info("Saved %s (%.1f MB)", path, path.stat().st_size / 1e6)
    return zipfile.ZipFile(path)


def _read(zf: zipfile.ZipFile, table: str, **kw) -> pd.DataFrame:
    name = next(n for n in zf.namelist() if n.endswith(f"formula_one_{table}.csv"))
    with zf.open(name) as fh:
        return pd.read_csv(io.BytesIO(fh.read()), **kw)


def tidy_dump(zf: zipfile.ZipFile) -> dict[str, pd.DataFrame]:
    season = _read(zf, "season")[["id", "year"]]
    circuit = _read(zf, "circuit")
    rnd = _read(zf, "round")
    session = _read(zf, "session")
    entry = _read(zf, "sessionentry")
    roundentry = _read(zf, "roundentry")
    teamdriver = _read(zf, "teamdriver")
    driver = _read(zf, "driver")
    team = _read(zf, "team")

    # rounds ---------------------------------------------------------
    rounds = (
        rnd.merge(season, left_on="season_id", right_on="id", suffixes=("", "_s"))
        .merge(circuit, left_on="circuit_id", right_on="id", suffixes=("", "_c"))
    )
    has_sprint = session[session["type"] == "SR"]["round_id"].unique()
    rounds = pd.DataFrame(
        {
            "round_id": rounds["id"],
            "year": rounds["year"],
            "round": rounds["number"].astype("Int64"),
            "name": rounds["name"],
            "date": pd.to_datetime(rounds["date"]),
            "circuit": rounds["reference"],
            "circuit_name": rounds["name_c"],
            "locality": rounds["locality"],
            "country": rounds["country"],
            "lat": rounds["latitude"],
            "lon": rounds["longitude"],
            "altitude_m": rounds["altitude"],
            "is_cancelled": _bool(rounds["is_cancelled"]),
            "has_sprint": rounds["id"].isin(has_sprint),
        }
    ).sort_values(["year", "round"], na_position="last")

    # who drove what car at each round --------------------------------
    td = (
        teamdriver.merge(driver[["id", "reference", "abbreviation"]], left_on="driver_id", right_on="id")
        .merge(team[["id", "reference", "name"]], left_on="team_id", right_on="id", suffixes=("_d", "_t"))
    )
    td = td.rename(columns={"id_x": "td_id"})[["td_id", "reference_d", "abbreviation", "reference_t", "name"]]
    td.columns = ["team_driver_id", "driver", "driver_code", "team", "team_name"]
    re_ = roundentry.merge(td, on="team_driver_id")[
        ["id", "round_id", "car_number", "driver", "driver_code", "team", "team_name"]
    ].rename(columns={"id": "round_entry_id"})

    sess = session[["id", "round_id", "type", "number"]].rename(
        columns={"id": "session_id", "type": "session_type", "number": "session_number"}
    )
    key = rounds[["round_id", "year", "round"]]
    ent = (
        entry.merge(sess, on="session_id")
        .merge(re_, on=["round_entry_id", "round_id"])
        .merge(key, on="round_id")
    )

    # results: race + sprint -----------------------------------------
    res = ent[ent["session_type"].isin(["R", "SR"])]
    results = pd.DataFrame(
        {
            "year": res["year"],
            "round": res["round"],
            "session_type": res["session_type"],
            "driver": res["driver"],
            "driver_code": res["driver_code"],
            "team": res["team"],
            "car_number": res["car_number"],
            "grid": res["grid"].astype("Int64"),
            "position": res["position"].astype("Int64"),
            "points": res["points"].astype(float),
            "laps_completed": res["laps_completed"].astype("Int64"),
            "status_code": res["status"].astype("Int64"),
            "outcome": res["status"].map(OUTCOME).fillna("unknown"),
            "detail": res["detail"],
            "is_classified": _bool(res["is_classified"]),
            "time_s": _seconds(res["time"]),
            "fastest_lap_rank": res["fastest_lap_rank"].astype("Int64"),
            "source": "dump",
        }
    )

    # laps -----------------------------------------------------------
    lap = _read(zf, "lap", usecols=["id", "is_deleted", "is_entry_fastest_lap", "number", "position", "session_entry_id", "time"])
    lap = lap.merge(
        ent[["id", "year", "round", "session_type", "driver", "team"]], left_on="session_entry_id", right_on="id", suffixes=("_lap", "")
    )
    laps = pd.DataFrame(
        {
            "lap_id": lap["id_lap"],
            "year": lap["year"],
            "round": lap["round"],
            "session_type": lap["session_type"],
            "driver": lap["driver"],
            "team": lap["team"],
            "lap": lap["number"].astype("Int64"),
            "position": lap["position"].astype("Int64"),
            "time_s": _seconds(lap["time"]),
            "is_deleted": _bool(lap["is_deleted"]),
            "is_entry_fastest_lap": _bool(lap["is_entry_fastest_lap"]),
        }
    )

    # qualifying ------------------------------------------------------
    qualifying = _qualifying_from_dump(ent, laps)

    # pit stops -------------------------------------------------------
    pit = _read(zf, "pitstop").merge(
        ent[["id", "year", "round", "session_type", "driver", "team"]], left_on="session_entry_id", right_on="id", suffixes=("_p", "")
    )
    pit = pit.merge(laps[["lap_id", "lap"]], left_on="lap_id", right_on="lap_id", how="left")
    pitstops = pd.DataFrame(
        {
            "year": pit["year"],
            "round": pit["round"],
            "session_type": pit["session_type"],
            "driver": pit["driver"],
            "team": pit["team"],
            "stop": pit["number"].astype("Int64"),
            "lap": pit["lap"].astype("Int64"),
            "duration_s": _seconds(pit["duration"]),
        }
    )

    # standings ---------------------------------------------------------
    ds = _read(zf, "driverchampionship").merge(driver[["id", "reference"]], left_on="driver_id", right_on="id")
    ts = _read(zf, "teamchampionship").merge(team[["id", "reference"]], left_on="team_id", right_on="id")
    driver_standings = _standings(ds, "driver")
    team_standings = _standings(ts, "team")

    return {
        "rounds": rounds.reset_index(drop=True),
        "results": results.reset_index(drop=True),
        "qualifying": qualifying,
        "laps": laps.drop(columns="lap_id").reset_index(drop=True),
        "pitstops": pitstops.reset_index(drop=True),
        "driver_standings": driver_standings,
        "team_standings": team_standings,
    }


def _qualifying_from_dump(ent: pd.DataFrame, laps: pd.DataFrame) -> pd.DataFrame:
    """One row per driver per weekend for GP qualifying (kind='Q') and
    sprint qualifying (kind='SQ'), with best lap in each segment and the
    final qualifying rank."""
    best = (
        laps[laps["session_type"].isin([*QUALI_SEGMENTS, *SPRINT_QUALI_SEGMENTS, *LEGACY_QUALI])]
        .groupby(["year", "round", "session_type", "driver"])["time_s"]
        .min()
    )
    q = ent[ent["session_type"].isin([*QUALI_SEGMENTS, *SPRINT_QUALI_SEGMENTS, *LEGACY_QUALI])].copy()
    q = q.join(best, on=["year", "round", "session_type", "driver"])
    q["kind"] = np.where(q["session_type"].str.startswith("SQ"), "SQ", "Q")
    q["segment"] = q["session_type"].map({**QUALI_SEGMENTS, **SPRINT_QUALI_SEGMENTS}).fillna(1).astype(int)

    rows = []
    for (year, rnd, kind), g in q.groupby(["year", "round", "kind"], sort=False):
        wide = g.pivot_table(index=["driver", "team"], columns="segment", values="time_s", aggfunc="min")
        wide = wide.reindex(columns=[1, 2, 3])
        wide.columns = ["q1_s", "q2_s", "q3_s"]
        # final rank: furthest segment reached first, then position within it
        reached = g.sort_values("segment").groupby("driver").tail(1).set_index("driver")
        order = reached.sort_values(["segment", "position"], ascending=[False, True])
        rank = pd.Series(np.arange(1, len(order) + 1), index=order.index, name="position")
        wide = wide.reset_index().join(rank, on="driver")
        wide["best_s"] = wide[["q1_s", "q2_s", "q3_s"]].min(axis=1)
        wide.insert(0, "kind", kind)
        wide.insert(0, "round", rnd)
        wide.insert(0, "year", year)
        rows.append(wide)
    out = pd.concat(rows, ignore_index=True)
    out["position"] = out["position"].astype("Int64")
    out["source"] = "dump"
    return out.sort_values(["year", "round", "kind", "position"]).reset_index(drop=True)


def _standings(df: pd.DataFrame, who: str) -> pd.DataFrame:
    # several rows per round when sprints exist: keep the state after the
    # last session of the round.
    df = df.sort_values("session_number").groupby(["year", "round_number", "reference"]).tail(1)
    return (
        pd.DataFrame(
            {
                "year": df["year"],
                "round": df["round_number"].astype("Int64"),
                who: df["reference"],
                "points": df["points"].astype(float),
                "position": df["position"].astype("Int64"),
                "wins": df["win_count"].astype("Int64"),
                "source": "dump",
            }
        )
        .sort_values(["year", "round", "position"])
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------- API top-up
def _api_table(http: PoliteSession, path: str) -> list[dict]:
    """Fetch every page of an Ergast-style endpoint, return the race list."""
    races: dict[str, dict] = {}
    offset, limit = 0, 100
    while True:
        data = http.get_json(f"{API}/{path}.json", params={"limit": limit, "offset": offset})["MRData"]
        table = next(v for k, v in data.items() if k.endswith("Table"))
        items = table.get("Races") or table.get("StandingsLists") or []
        for race in items:
            k = f"{race['season']}-{race['round']}"
            if k not in races:
                races[k] = race
            else:  # merge list payloads split across pages
                for key, val in race.items():
                    if isinstance(val, list):
                        races[k].setdefault(key, []).extend(val)
        offset += limit
        if offset >= int(data["total"]):
            return list(races.values())


def _status_to_outcome(status: str, position_text: str, detail_map: dict[str, str]) -> str:
    if position_text == "D":
        return "dsq"
    if position_text in {"W", "F"}:
        return "dns"
    if status == "Finished":
        return "finished"
    if status.startswith("+") or status == "Lapped":
        return "lapped"
    return detail_map.get(status, "dnf_mechanical" if position_text == "R" else "unknown")


def fetch_round_from_api(year: int, rnd: int, detail_map: dict[str, str], http: PoliteSession) -> dict[str, pd.DataFrame]:
    out: dict[str, list] = {k: [] for k in ("results", "qualifying", "laps", "pitstops", "driver_standings", "team_standings")}

    for stype, path, key in (("R", "results", "Results"), ("SR", "sprint", "SprintResults")):
        for race in _api_table(http, f"{year}/{rnd}/{path}"):
            for r in race.get(key, []):
                out["results"].append(
                    {
                        "year": year,
                        "round": rnd,
                        "session_type": stype,
                        "driver": r["Driver"]["driverId"],
                        "driver_code": r["Driver"].get("code"),
                        "team": r["Constructor"]["constructorId"],
                        "car_number": int(r["number"]),
                        "grid": int(r["grid"]),
                        "position": int(r["position"]) if r["positionText"].isdigit() else pd.NA,
                        "points": float(r["points"]),
                        "laps_completed": int(r["laps"]),
                        "outcome": _status_to_outcome(r["status"], r["positionText"], detail_map),
                        "detail": r["status"],
                        "is_classified": r["positionText"].isdigit(),
                        "time_s": int(r["Time"]["millis"]) / 1000 if "Time" in r else np.nan,
                        "fastest_lap_rank": int(r["FastestLap"]["rank"]) if r.get("FastestLap", {}).get("rank") else pd.NA,
                        "source": "api",
                    }
                )

    for race in _api_table(http, f"{year}/{rnd}/qualifying"):
        for q in race.get("QualifyingResults", []):
            times = {f"q{i}_s": q.get(f"Q{i}") for i in (1, 2, 3)}
            out["qualifying"].append(
                {"year": year, "round": rnd, "kind": "Q", "driver": q["Driver"]["driverId"], "team": q["Constructor"]["constructorId"],
                 **times, "position": int(q["position"]), "source": "api"}
            )

    for race in _api_table(http, f"{year}/{rnd}/laps"):
        for lap in race.get("Laps", []):
            for t in lap["Timings"]:
                out["laps"].append(
                    {"year": year, "round": rnd, "session_type": "R", "driver": t["driverId"], "lap": int(lap["number"]),
                     "position": int(t["position"]), "time_s": t["time"]}
                )

    for race in _api_table(http, f"{year}/{rnd}/pitstops"):
        for p in race.get("PitStops", []):
            out["pitstops"].append(
                {"year": year, "round": rnd, "session_type": "R", "driver": p["driverId"], "stop": int(p["stop"]),
                 "lap": int(p["lap"]), "duration_s": p["duration"]}
            )

    for path, key, who, ref in (("driverStandings", "DriverStandings", "driver", ("Driver", "driverId")),
                                ("constructorStandings", "ConstructorStandings", "team", ("Constructor", "constructorId"))):
        for sl in _api_table(http, f"{year}/{rnd}/{path}"):
            for s in sl.get(key, []):
                out[f"{who}_standings"].append(
                    {"year": year, "round": rnd, who: s[ref[0]][ref[1]], "points": float(s["points"]),
                     "position": int(s["position"]) if s.get("position") else pd.NA, "wins": int(s["wins"]), "source": "api"}
                )

    frames = {k: pd.DataFrame(v) for k, v in out.items()}
    for name, cols in (("qualifying", ["q1_s", "q2_s", "q3_s"]), ("laps", ["time_s"]), ("pitstops", ["duration_s"])):
        for c in cols:
            if c in frames[name]:
                frames[name][c] = _seconds(frames[name][c])
    if not frames["qualifying"].empty:
        frames["qualifying"]["best_s"] = frames["qualifying"][["q1_s", "q2_s", "q3_s"]].min(axis=1)
    if not frames["laps"].empty:  # attach team via race results
        teams = frames["results"].query("session_type == 'R'")[["driver", "team"]]
        frames["laps"] = frames["laps"].merge(teams, on="driver", how="left")
        frames["pitstops"] = frames["pitstops"].merge(teams, on="driver", how="left")
    return frames


def missing_rounds(tables: dict[str, pd.DataFrame], today: date | None = None) -> list[tuple[int, int]]:
    """Completed, non-cancelled rounds that have no race result yet."""
    cutoff = pd.Timestamp((today or date.today()).isoformat()) - pd.to_timedelta(1, unit="D")
    r = tables["rounds"]
    done = r[(~r["is_cancelled"].fillna(False)) & r["round"].notna() & (r["date"] < cutoff)]
    have = set(map(tuple, tables["results"].query("session_type == 'R'")[["year", "round"]].drop_duplicates().to_numpy()))
    return [(int(y), int(n)) for y, n in done[["year", "round"]].to_numpy() if (y, n) not in have]


def build(force_download: bool = False, top_up: bool = True) -> dict[str, pd.DataFrame]:
    http = PoliteSession(min_interval=0.5)
    tables = tidy_dump(download_dump(force_download, http))

    if top_up:
        detail_map = (
            tables["results"].dropna(subset=["detail"]).groupby("detail")["outcome"].agg(lambda s: s.mode().iat[0]).to_dict()
        )
        for year, rnd in missing_rounds(tables):
            log.info("Topping up %d round %d from the API", year, rnd)
            extra = fetch_round_from_api(year, rnd, detail_map, http)
            for name, df in extra.items():
                if not df.empty:
                    if name in ("driver_standings", "team_standings"):
                        df = df.astype({"round": "Int64", "position": "Int64", "wins": "Int64"})
                    tables[name] = pd.concat([tables[name], df], ignore_index=True)

    ensure(JOLPICA_OUT)
    for name, df in tables.items():
        df.to_parquet(JOLPICA_OUT / f"{name}.parquet", index=False)
        log.info("jolpica/%s: %d rows", name, len(df))
    return tables


def load(name: str) -> pd.DataFrame:
    return pd.read_parquet(JOLPICA_OUT / f"{name}.parquet")
