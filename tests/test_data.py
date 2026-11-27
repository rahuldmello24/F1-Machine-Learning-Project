from datetime import date

import numpy as np
import pandas as pd
import pytest

from f1predict.data import jolpica
from f1predict.eras import era_of, is_reset
from f1predict.teams import lineage


def test_seconds_parses_all_time_formats():
    s = pd.Series(["01:31:55.593", "1:23.456", "23.456", None, ""])
    out = jolpica._seconds(s)
    assert out.iloc[0] == pytest.approx(5515.593)
    assert out.iloc[1] == pytest.approx(83.456)
    assert out.iloc[2] == pytest.approx(23.456)
    assert out.iloc[3:].isna().all()


@pytest.mark.parametrize(
    "status, pos_text, expected",
    [
        ("Finished", "1", "finished"),
        ("+1 Lap", "14", "lapped"),
        ("Lapped", "15", "lapped"),
        ("Accident", "R", "dnf_incident"),
        ("Power Unit", "R", "dnf_mechanical"),  # unseen status falls back to mechanical
        ("Disqualified", "D", "dsq"),
        ("Withdrew", "W", "dns"),
    ],
)
def test_status_to_outcome(status, pos_text, expected):
    detail_map = {"Accident": "dnf_incident", "Engine": "dnf_mechanical"}
    assert jolpica._status_to_outcome(status, pos_text, detail_map) == expected


def test_qualifying_rank_uses_furthest_segment_first():
    # A tops Q1 but is knocked out in Q2; B and C reach Q3.
    ent = pd.DataFrame(
        [
            # year, round, session_type, driver, team, position
            (2025, 1, "Q1", "a", "x", 1), (2025, 1, "Q1", "b", "y", 2), (2025, 1, "Q1", "c", "z", 3),
            (2025, 1, "Q2", "a", "x", 3), (2025, 1, "Q2", "b", "y", 1), (2025, 1, "Q2", "c", "z", 2),
            (2025, 1, "Q3", "b", "y", 2), (2025, 1, "Q3", "c", "z", 1),
        ],
        columns=["year", "round", "session_type", "driver", "team", "position"],
    )
    laps = ent.assign(time_s=np.arange(len(ent), dtype=float) + 80.0)
    q = jolpica._qualifying_from_dump(ent, laps).set_index("driver")
    assert q.loc["c", "position"] == 1
    assert q.loc["b", "position"] == 2
    assert q.loc["a", "position"] == 3
    assert np.isnan(q.loc["a", "q3_s"])
    assert q.loc["b", "best_s"] == q.loc["b", ["q1_s", "q2_s", "q3_s"]].min()


def test_missing_rounds_skips_cancelled_future_and_present():
    rounds = pd.DataFrame(
        {
            "year": [2026] * 4,
            "round": pd.array([1, 2, 3, pd.NA], dtype="Int64"),
            "date": pd.to_datetime(["2026-03-01", "2026-03-15", "2026-12-01", "2026-04-01"]),
            "is_cancelled": pd.array([False, False, False, True], dtype="boolean"),
        }
    )
    results = pd.DataFrame({"year": [2026], "round": [1], "session_type": ["R"]})
    assert jolpica.missing_rounds({"rounds": rounds, "results": results}, today=date(2026, 6, 1)) == [(2026, 2)]


def test_team_lineage_and_eras():
    assert lineage("toro_rosso") == "rb"
    assert lineage("brawn") == "mercedes"
    assert lineage("ferrari") == "ferrari"
    assert list(lineage(pd.Series(["alfa", "sauber"]))) == ["audi", "audi"]
    assert era_of(2025) == 2022
    assert era_of(2026) == 2026
    assert is_reset(2014) and not is_reset(2015)
