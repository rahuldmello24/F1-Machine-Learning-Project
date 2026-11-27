"""Walk-forward backtesting with a hard guard against look-ahead.

For each test season the model is (re)fitted on everything before the
season, then predicts that season's races one at a time. When it predicts
race *r* it receives:

* ``history``: every entry from races dated strictly **before** race *r*
  (so in-season form updates race by race), and
* ``race``: the entries for race *r* with every outcome column removed.

The model therefore cannot see the result it is predicting, or anything
that happened later. ``_check_no_lookahead`` enforces this on every call.
"""

from __future__ import annotations

import logging
import time
from typing import Protocol

import pandas as pd

from f1predict.evaluation.metrics import LOWER_IS_BETTER, METRICS, race_metrics
from f1predict.evaluation.simulate import position_table

log = logging.getLogger(__name__)

# columns that describe what happened in the race: never shown to a model
OUTCOME_COLS = ["finish_order", "position", "finished", "outcome", "laps_completed", "points"]


class Forecaster(Protocol):
    name: str

    def fit(self, history: pd.DataFrame) -> None: ...

    def predict(self, history: pd.DataFrame, race: pd.DataFrame) -> pd.DataFrame:
        """Return a frame indexed like ``race`` with columns
        ``strength`` (Plackett-Luce log-worth) and ``p_dnf``."""
        ...


def _check_no_lookahead(history: pd.DataFrame, race: pd.DataFrame) -> None:
    race_date = race["date"].iloc[0]
    if len(history) and history["date"].max() >= race_date:
        raise AssertionError("history contains races on/after the race being predicted")
    leaked = [c for c in OUTCOME_COLS if c in race.columns]
    if leaked:
        raise AssertionError(f"race frame contains outcome columns {leaked}")


def backtest(model: Forecaster, entries: pd.DataFrame, seasons: list[int], n_sims: int = 20_000) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (predictions per driver, metrics per race)."""
    preds, rows = [], []
    for season in seasons:
        t0 = time.time()
        season_start = entries.loc[entries["year"] == season, "date"].min()
        model.fit(entries[entries["date"] < season_start])
        for race_id, truth in entries[entries["year"] == season].groupby("race_id", sort=True):
            race = truth.drop(columns=OUTCOME_COLS)
            history = entries[entries["date"] < race["date"].iloc[0]]
            _check_no_lookahead(history, race)

            out = model.predict(history, race)
            p = position_table(race.assign(strength=out["strength"].to_numpy(), p_dnf=out["p_dnf"].to_numpy()),
                               n_sims=n_sims, seed=int(race_id))
            p = p.join(truth[OUTCOME_COLS])
            preds.append(p)
            rows.append({"model": model.name, "year": season, "round": int(truth["round"].iloc[0]),
                         "race_id": race_id, **race_metrics(p)})
        log.info("%s %d done in %.1fs", model.name, season, time.time() - t0)
    pred_df = pd.concat(preds, ignore_index=True).assign(model=model.name)
    return pred_df, pd.DataFrame(rows)


def summarise(metrics: pd.DataFrame, by: list[str] | None = None) -> pd.DataFrame:
    by = by or ["model"]
    return metrics.groupby(by)[METRICS].mean().reset_index()


def skill_vs(metrics: pd.DataFrame, reference: str, metric: str = "winner_logloss") -> pd.DataFrame:
    """Per-season improvement over a reference model (positive = better)."""
    s = metrics.groupby(["year", "model"])[metric].mean().unstack("model")
    diff = s.sub(s[reference], axis=0).drop(columns=reference)
    return -diff if metric in LOWER_IS_BETTER else diff
