"""OpenF1: free historical session data from 2023 onwards.

Unlike Jolpica, OpenF1 has *practice* sessions in full: every lap with
sector times and speed traps, tyre stints, weather, pit lane times and
race-control messages. That is the raw material for long-run pace, tyre
degradation and track-evolution features.

Raw JSON is cached per session and endpoint, so re-running only fetches
what is missing. ``tidy()`` turns the cache into parquet tables joined to
Jolpica's ``(year, round, driver)`` keys.
"""

from __future__ import annotations

import gzip
import json
import logging
from datetime import datetime, timezone

import pandas as pd

from f1predict.http import PoliteSession
from f1predict.paths import OPENF1_OUT, OPENF1_RAW, ensure

log = logging.getLogger(__name__)

API = "https://api.openf1.org/v1"
FIRST_YEAR = 2023
ENDPOINTS = ("drivers", "laps", "stints", "weather", "pit", "race_control")

# OpenF1 session_name -> our short codes (matching Jolpica where possible)
SESSION_CODE = {
    "Practice 1": "FP1",
    "Practice 2": "FP2",
    "Practice 3": "FP3",
    "Qualifying": "Q",
    "Sprint Qualifying": "SQ",
    "Sprint Shootout": "SQ",
    "Sprint": "SR",
    "Race": "R",
}


def _cache_path(year: int, session_key: int, endpoint: str):
    return OPENF1_RAW / str(year) / str(session_key) / f"{endpoint}.json.gz"


def _write(path, payload) -> None:
    ensure(path.parent)
    with gzip.open(path, "wt") as fh:
        json.dump(payload, fh)


def _read(path):
    with gzip.open(path, "rt") as fh:
        return json.load(fh)


def sessions(year: int, http: PoliteSession) -> pd.DataFrame:
    data = http.get_json(f"{API}/sessions", params={"year": year})
    df = pd.DataFrame(data)
    if df.empty:
        return df
    df["date_start"] = pd.to_datetime(df["date_start"], utc=True)
    df["date_end"] = pd.to_datetime(df["date_end"], utc=True)
    return df


def fetch(years: list[int] | None = None, endpoints=ENDPOINTS, http: PoliteSession | None = None) -> None:
    http = http or PoliteSession(min_interval=0.4)
    now = datetime.now(timezone.utc)
    years = years or list(range(FIRST_YEAR, now.year + 1))
    for year in years:
        cat = sessions(year, http)
        if cat.empty:
            continue
        cat = cat[(cat["date_end"] < now) & (~cat.get("is_cancelled", False).astype(bool))]
        _write(OPENF1_RAW / str(year) / "sessions.json.gz", json.loads(cat.to_json(orient="records", date_format="iso")))
        todo = [(int(s), e) for s in cat["session_key"] for e in endpoints if not _cache_path(year, int(s), e).exists()]
        log.info("OpenF1 %d: %d sessions, %d endpoint files to fetch", year, len(cat), len(todo))
        for i, (skey, ep) in enumerate(todo, 1):
            resp = http.get(f"{API}/{ep}", params={"session_key": skey})
            payload = resp.json() if resp.status_code == 200 else []
            if not isinstance(payload, list):  # {"detail": "No results found."}
                payload = []
            _write(_cache_path(year, skey, ep), payload)
            if i % 50 == 0:
                log.info("  %d/%d", i, len(todo))


def _load_endpoint(endpoint: str, meta: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for row in meta.itertuples():
        p = _cache_path(row.year, row.session_key, endpoint)
        if p.exists():
            d = _read(p)
            if d:
                frames.append(pd.DataFrame(d).dropna(axis=1, how="all"))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    return df.merge(meta, on="session_key", how="left", suffixes=("", "_s"))


def tidy(jolpica_rounds: pd.DataFrame, jolpica_results: pd.DataFrame) -> dict[str, pd.DataFrame]:
    metas = []
    for p in sorted(OPENF1_RAW.glob("*/sessions.json.gz")):
        metas.append(pd.DataFrame(_read(p)))
    if not metas:
        raise FileNotFoundError("No OpenF1 cache found, run `f1predict pull openf1` first")
    meta = pd.concat(metas, ignore_index=True)
    meta["date_start"] = pd.to_datetime(meta["date_start"], utc=True)
    meta["session"] = meta["session_name"].map(SESSION_CODE)
    meta.loc[meta["session_name"].str.startswith("Day"), "session"] = "TEST"  # pre-season testing
    meta["session"] = meta["session"].fillna(meta["session_name"])

    # meeting -> Jolpica round: match on year + race date (within 3 days)
    race_day = meta.groupby("meeting_key")["date_start"].max().dt.tz_convert(None).dt.normalize()
    mk = meta.groupby("meeting_key").agg(year=("year", "first"), location=("location", "first"),
                                         circuit_short_name=("circuit_short_name", "first")).assign(race_day=race_day)
    jr = jolpica_rounds.dropna(subset=["round"])[["year", "round", "date", "circuit"]]
    m = mk.reset_index().merge(jr, on="year")
    m["gap"] = (m["date"] - m["race_day"]).abs()
    m = m[m["gap"] <= pd.to_timedelta(3, unit="D")].sort_values("gap").drop_duplicates("meeting_key")
    meeting_map = m[["meeting_key", "year", "round", "circuit", "location", "circuit_short_name"]]

    keep = ["session_key", "meeting_key", "year", "session", "date_start"]
    meta = meta[keep].merge(meeting_map[["meeting_key", "round", "circuit"]], on="meeting_key", how="left")
    meta["year"] = meta["year"].astype(int)
    meta.loc[meta["session"] == "TEST", "round"] = 0  # testing happens before round 1
    meta["round"] = meta["round"].astype("Int64")

    # driver_number -> Jolpica driver ref, via the car number in that round's entry list;
    # testing (round 0) uses the season's round-1 entry list.
    carmap = (
        jolpica_results.query("session_type == 'R'").dropna(subset=["car_number"])
        .assign(car_number=lambda d: d["car_number"].astype(int))
        .drop_duplicates(["year", "round", "car_number"])[["year", "round", "car_number", "driver", "team"]]
        .rename(columns={"car_number": "driver_number"})
    )
    first = carmap.loc[carmap["round"] == carmap.groupby("year")["round"].transform("min")]
    carmap = pd.concat([carmap, first.assign(round=0)], ignore_index=True)
    carmap["round"] = carmap["round"].astype("Int64")

    out: dict[str, pd.DataFrame] = {"sessions": meta, "meetings": meeting_map}
    for ep in ENDPOINTS:
        df = _load_endpoint(ep, meta.drop(columns=["meeting_key"]))
        if df.empty:
            continue
        df = df.drop(columns=[c for c in df.columns if c.endswith("_s")])
        if "driver_number" in df.columns:
            df = df.merge(carmap, on=["year", "round", "driver_number"], how="left")
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], utc=True, format="ISO8601")
        # list columns (mini-sector segments) don't round-trip nicely; keep as JSON text
        for c in df.columns:
            if df[c].map(lambda v: isinstance(v, (list, dict))).any():
                df[c] = df[c].map(lambda v: json.dumps(v) if isinstance(v, (list, dict)) else v)
        out[ep] = df

    ensure(OPENF1_OUT)
    for name, df in out.items():
        df.to_parquet(OPENF1_OUT / f"{name}.parquet", index=False)
        log.info("openf1/%s: %d rows", name, len(df))
    return out


def load(name: str) -> pd.DataFrame:
    return pd.read_parquet(OPENF1_OUT / f"{name}.parquet")
