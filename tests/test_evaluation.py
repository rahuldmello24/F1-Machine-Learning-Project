import numpy as np
import pandas as pd
import pytest

from f1predict.evaluation.backtest import OUTCOME_COLS, backtest
from f1predict.evaluation.metrics import race_metrics
from f1predict.evaluation.simulate import simulate_positions
from f1predict.models.baselines import team_form
from f1predict.models.plackett_luce import fit_pl


def synthetic_entries(n_races=60, n_drivers=10, seed=0, true_w=(1.5,)):
    """Races where a driver's strength = true_w * skill; finishing order sampled
    from that Plackett-Luce model; nobody retires."""
    rng = np.random.default_rng(seed)
    skill = np.linspace(1, -1, n_drivers)
    rows = []
    for r in range(n_races):
        year = 2020 + r // 20
        s = true_w[0] * skill + rng.gumbel(size=n_drivers)
        order = np.argsort(-s).argsort() + 1
        for d in range(n_drivers):
            rows.append({"race_id": year * 100 + r % 20 + 1, "year": year, "round": r % 20 + 1,
                         "date": pd.Timestamp(f"{year}-01-01") + pd.to_timedelta(7 * (r % 20), unit="D"),
                         "driver": f"d{d}", "lineage": f"t{d // 2}", "skill": skill[d], "grid": d + 1,
                         "field_size": n_drivers, "finish_order": int(order[d]), "position": float(order[d]),
                         "finished": True, "outcome": "finished", "laps_completed": 50, "points": 0.0})
    return pd.DataFrame(rows)


def test_pl_fit_recovers_true_weight():
    df = synthetic_entries(n_races=400, seed=1)
    w = fit_pl(df, ["skill"], l2=0.0)
    assert w[0] == pytest.approx(1.5, abs=0.15)


def test_simulation_rows_and_columns_are_distributions():
    P = simulate_positions(np.array([2.0, 1.0, 0.0, -1.0]), np.array([0.1, 0.1, 0.5, 0.0]), n_sims=20_000)
    assert np.allclose(P.sum(axis=0), 1) and np.allclose(P.sum(axis=1), 1)
    assert P[0, 0] > P[1, 0] > P[3, 0]
    # the car that retires half the time finishes last most often
    assert P[2, 3] == P[:, 3].max()


def test_race_metrics_on_a_perfect_forecast():
    r = pd.DataFrame({
        "p_win": [1.0, 0, 0, 0], "p_podium": [1.0, 1, 1, 0], "p_points": [1.0] * 4, "p_dnf": [0.0, 0, 0, 1],
        "exp_position": [1, 2, 3, 4], "finish_order": [1, 2, 3, 4], "finished": [True, True, True, False],
    })
    m = race_metrics(r)
    assert m["winner_logloss"] == pytest.approx(0, abs=1e-9)
    assert m["podium_brier"] == 0 and m["dnf_brier"] == 0
    assert m["spearman"] == pytest.approx(1) and m["top3_overlap"] == 1


class Peeker:
    """A model that tries to cheat by reading the race's outcome columns."""
    name = "peeker"
    seen_max_date = None

    def fit(self, history):
        pass

    def predict(self, history, race):
        assert not set(OUTCOME_COLS) & set(race.columns), "outcome leaked into race frame"
        assert history["date"].max() < race["date"].iloc[0], "future race leaked into history"
        return pd.DataFrame({"strength": 0.0, "p_dnf": 0.0}, index=race.index)


def test_backtest_never_shows_the_future():
    df = synthetic_entries()
    preds, metrics = backtest(Peeker(), df, seasons=[2021, 2022], n_sims=500)
    assert metrics["race_id"].nunique() == 40
    # uniform model: winner log-loss = log(10)
    assert metrics["winner_logloss"].mean() == pytest.approx(np.log(10), abs=0.1)


def test_team_form_is_point_in_time():
    df = synthetic_entries(n_races=10)
    before = team_form(df).loc[df["race_id"] == df["race_id"].max(), "form"]
    # rewriting the last race's result must not change that race's own form feature
    df2 = df.copy()
    last = df2["race_id"] == df2["race_id"].max()
    df2.loc[last, "finish_order"] = df2.loc[last, "finish_order"].to_numpy()[::-1]
    after = team_form(df2).loc[last, "form"]
    assert np.allclose(before.to_numpy(), after.to_numpy())
