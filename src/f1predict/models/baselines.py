"""Baselines every real model has to beat.

``GridBaseline``
    Strength depends only on starting position: ``a*log(slot) + b*slot``
    (fitted, so it learns *how much* P1 is worth over P2, P10, ...).
    Retirement probability = the average retirement rate in training.

``GridTeamFormBaseline``
    Adds the team's recent results (finishing percentile over its last
    5 races) to strength, and the team's recent retirement rate (shrunk
    toward the field average) to p_dnf. A deliberately simple stand-in
    for "grid + how good is the car right now".
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from f1predict.dataset import grid_slot
from f1predict.models.plackett_luce import fit_pl

TRAIN_SEASONS = 8  # rolling training window


def _grid_features(df: pd.DataFrame) -> pd.DataFrame:
    slot = grid_slot(df["grid"], df["field_size"])
    return pd.DataFrame({"log_slot": np.log(slot), "slot": slot / 10.0}, index=df.index)


def team_form(history: pd.DataFrame, race: pd.DataFrame | None = None, window: int = 5, dnf_window: int = 10,
              shrink: float = 5.0) -> pd.DataFrame:
    """Point-in-time team form for every row of ``history`` (and ``race``).

    For each team lineage and race, uses only that team's *previous* races:
    ``form``: mean finishing percentile (1 = won, 0 = last) over the last
    ``window`` races; ``team_p_dnf``: retirement rate over the last
    ``dnf_window`` starts, shrunk toward the overall rate.
    """
    frames = [history]
    if race is not None:
        frames.append(race)
    df = pd.concat(frames, ignore_index=False)
    pct = 1 - (df["finish_order"] - 1) / (df["field_size"] - 1).clip(lower=1)
    per_race = (
        df.assign(pct=pct, dnf=(~df["finished"].astype("boolean")).astype("Float64"))
        .groupby(["lineage", "race_id"], sort=True)
        .agg(pct=("pct", "mean"), dnf=("dnf", "sum"), starts=("dnf", "count"))
        .reset_index()
    )
    g = per_race.groupby("lineage")
    per_race["form"] = g["pct"].transform(lambda s: s.shift(1).rolling(window, min_periods=1).mean())
    dnf_sum = g["dnf"].transform(lambda s: s.shift(1).rolling(dnf_window, min_periods=1).sum())
    starts = g["starts"].transform(lambda s: s.shift(1).rolling(dnf_window, min_periods=1).sum())
    base = history["finished"].eq(False).mean() if len(history) else 0.15
    per_race["team_p_dnf"] = ((dnf_sum.fillna(0) + shrink * base) / (starts.fillna(0) + shrink)).astype(float)
    per_race["form"] = per_race["form"].astype(float).fillna(0.5)  # new team: assume midfield
    out = df[["lineage", "race_id"]].merge(per_race[["lineage", "race_id", "form", "team_p_dnf"]],
                                          on=["lineage", "race_id"], how="left")
    out.index = df.index
    return out[["form", "team_p_dnf"]]


class GridBaseline:
    name = "grid"
    features = ["log_slot", "slot"]

    def fit(self, history: pd.DataFrame) -> None:
        h = history[history["year"] >= history["year"].max() - TRAIN_SEASONS + 1]
        X = h.join(_grid_features(h))
        self.w = fit_pl(X, self.features)
        self.p_dnf = float((~h["finished"]).mean())

    def predict(self, history: pd.DataFrame, race: pd.DataFrame) -> pd.DataFrame:
        X = _grid_features(race)[self.features].to_numpy()
        return pd.DataFrame({"strength": X @ self.w, "p_dnf": self.p_dnf}, index=race.index)


class GridTeamFormBaseline:
    name = "grid+team_form"
    features = ["log_slot", "slot", "form_c"]

    def _design(self, df: pd.DataFrame, form: pd.DataFrame) -> pd.DataFrame:
        X = _grid_features(df).join(form)
        X["form_c"] = X["form"] - X.groupby(df["race_id"])["form"].transform("mean")  # relative to this field
        return X

    def fit(self, history: pd.DataFrame) -> None:
        h = history[history["year"] >= history["year"].max() - TRAIN_SEASONS + 1]
        form = team_form(history).loc[h.index]
        self.w = fit_pl(h.join(self._design(h, form)), self.features)

    def predict(self, history: pd.DataFrame, race: pd.DataFrame) -> pd.DataFrame:
        recent = history[history["year"] >= race["year"].iloc[0] - 2]
        form = team_form(recent, race).loc[race.index]
        X = self._design(race, form)
        return pd.DataFrame({"strength": X[self.features].to_numpy() @ self.w, "p_dnf": X["team_p_dnf"].to_numpy()},
                            index=race.index)
