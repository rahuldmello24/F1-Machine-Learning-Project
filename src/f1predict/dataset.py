"""The race-entry table every model trains and is scored on.

One row per driver per Grand Prix (sprints excluded), with what was
known before the race starts (grid, qualifying) and what happened
(finishing order, whether the car was classified, why not).

Truth for scoring
-----------------
``finish_order`` is the full order of the field, like the official
classification extended to non-finishers: classified cars by position,
then non-classified cars by laps completed (more laps = further up).
``finished`` is the official "classified" flag. Retirements are therefore
scored as finishing behind every classified car, never as a fake "P20".
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from f1predict.data import jolpica
from f1predict.eras import era_of
from f1predict.teams import lineage

PIT_LANE = 0  # Jolpica uses grid 0 for pit-lane starts


def build_entries(min_year: int = 1950) -> pd.DataFrame:
    res = jolpica.load("results").query("session_type == 'R' and year >= @min_year").copy()
    rounds = jolpica.load("rounds")[["year", "round", "date", "circuit", "name"]]
    quali = jolpica.load("qualifying").query("kind == 'Q'")[["year", "round", "driver", "position", "best_s"]]
    quali = quali.rename(columns={"position": "quali_pos", "best_s": "quali_best_s"})

    # 1950s shared drives: keep each driver's best-placed car only
    res = res.sort_values(["year", "round", "driver", "position"]).drop_duplicates(["year", "round", "driver"])

    df = res.merge(rounds, on=["year", "round"], how="left").merge(quali, on=["year", "round", "driver"], how="left")
    df["lineage"] = lineage(df["team"])
    df["era"] = df["year"].map(era_of)
    df["finished"] = df["is_classified"].fillna(False).astype(bool)
    df["pit_lane_start"] = df["grid"].eq(PIT_LANE).fillna(False)

    # full finishing order: classified by position, then the rest by laps completed
    df["_pos"] = df["position"].astype("float").where(df["finished"])
    df["_laps"] = -df["laps_completed"].astype("float").fillna(0)
    df = df.sort_values(["year", "round", "_pos", "_laps"], na_position="last")
    df["finish_order"] = df.groupby(["year", "round"]).cumcount() + 1
    df["field_size"] = df.groupby(["year", "round"])["driver"].transform("size")

    # stable race id ordered by time
    df["race_id"] = (df["year"] * 100 + df["round"]).astype(int)

    cols = [
        "race_id", "year", "round", "date", "circuit", "name", "era", "driver", "team", "lineage",
        "grid", "pit_lane_start", "quali_pos", "quali_best_s", "field_size",
        "finish_order", "position", "finished", "outcome", "laps_completed", "points",
    ]
    return df[cols].sort_values(["race_id", "finish_order"]).reset_index(drop=True)


def grid_slot(grid: pd.Series, field_size: pd.Series | None = None) -> np.ndarray:
    """Starting slot as an int: 1..N, pit-lane / missing -> back of the grid."""
    g = grid.astype("float").to_numpy()
    back = (field_size.to_numpy() if field_size is not None else np.full(len(g), 26.0)) + 1
    g = np.where(np.isnan(g) | (g == PIT_LANE), back, g)
    return g.astype(int)
