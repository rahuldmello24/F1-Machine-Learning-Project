"""Scoring rules for race forecasts.

All metrics are computed per race, then averaged. Lower is better for
log-loss and Brier scores; higher is better for the rest.

``winner_logloss``  -log(probability given to the actual winner). Heavily
                    punishes confident misses; the main probability metric.
``winner_hit``      did the favourite win?
``podium_brier``    mean squared error of each driver's podium probability
                    against 0/1 outcome.
``points_brier``    same for finishing in the top 10.
``dnf_brier``       same for retiring (not being classified).
``spearman``        rank correlation between predicted (expected) finishing
                    position and the actual full finishing order.
``top3_overlap``    share of the actual podium among the 3 drivers with the
                    highest podium probability.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

EPS = 1e-6

METRICS = ["winner_logloss", "winner_hit", "podium_brier", "points_brier", "dnf_brier", "spearman", "top3_overlap"]
LOWER_IS_BETTER = {"winner_logloss", "podium_brier", "points_brier", "dnf_brier"}


def race_metrics(r: pd.DataFrame) -> dict[str, float]:
    """``r``: one race, with prediction columns (p_win, p_podium, p_points,
    p_dnf, exp_position) and truth columns (finish_order, finished)."""
    won = (r["finish_order"] == 1) & r["finished"]
    podium = (r["finish_order"] <= 3) & r["finished"]
    points = (r["finish_order"] <= 10) & r["finished"]
    dnf = ~r["finished"]

    out = {
        "winner_logloss": float(-np.log(max(r.loc[won, "p_win"].sum(), EPS))) if won.any() else np.nan,
        "winner_hit": float(won[r["p_win"].idxmax()]) if won.any() else np.nan,
        "podium_brier": float(((r["p_podium"] - podium) ** 2).mean()),
        "points_brier": float(((r["p_points"] - points) ** 2).mean()),
        "dnf_brier": float(((r["p_dnf"] - dnf) ** 2).mean()),
        "spearman": float(r["exp_position"].rank().corr(r["finish_order"].rank())),
        "top3_overlap": float(podium[r["p_podium"].nlargest(3).index].sum() / 3),
    }
    return out


def calibration(preds: pd.DataFrame, prob: str = "p_podium", bins=(0, .02, .05, .1, .2, .35, .5, .65, .8, .9, 1.0)) -> pd.DataFrame:
    """Bucket predicted probabilities and compare with observed frequency."""
    truth = {
        "p_win": (preds["finish_order"] == 1) & preds["finished"],
        "p_podium": (preds["finish_order"] <= 3) & preds["finished"],
        "p_points": (preds["finish_order"] <= 10) & preds["finished"],
        "p_dnf": ~preds["finished"],
    }[prob]
    b = pd.cut(preds[prob], bins=list(bins), include_lowest=True)
    return (
        pd.DataFrame({"bucket": b, "p": preds[prob], "y": truth.astype(float)})
        .groupby("bucket", observed=True)
        .agg(n=("y", "size"), predicted=("p", "mean"), observed=("y", "mean"))
        .reset_index()
    )
