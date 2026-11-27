"""Run the walk-forward backtest for a set of models and write
``reports/backtest.md`` plus per-driver predictions to ``data/backtests``."""

from __future__ import annotations

from datetime import date

import pandas as pd

from f1predict.audit import md_table
from f1predict.dataset import build_entries
from f1predict.evaluation.backtest import backtest, skill_vs, summarise
from f1predict.evaluation.metrics import METRICS, calibration
from f1predict.paths import DATA_DIR, REPORTS_DIR, ensure

TEST_SEASONS = [2022, 2023, 2024, 2025, 2026]

METRIC_NOTES = {
    "winner_logloss": "↓ −log P(actual winner)",
    "winner_hit": "↑ favourite won",
    "podium_brier": "↓ podium probability error",
    "points_brier": "↓ top-10 probability error",
    "dnf_brier": "↓ retirement probability error",
    "spearman": "↑ predicted vs actual order",
    "top3_overlap": "↑ share of podium predicted",
}


def default_models():
    from f1predict.models.baselines import GridBaseline, GridTeamFormBaseline

    return [GridBaseline(), GridTeamFormBaseline()]


def run(models=None, seasons=TEST_SEASONS, n_sims: int = 20_000) -> str:
    models = models or default_models()
    entries = build_entries(min_year=2000)
    all_preds, all_metrics = [], []
    for m in models:
        p, mt = backtest(m, entries, seasons, n_sims=n_sims)
        all_preds.append(p)
        all_metrics.append(mt)
    preds = pd.concat(all_preds, ignore_index=True)
    metrics = pd.concat(all_metrics, ignore_index=True)

    out_dir = ensure(DATA_DIR / "backtests")
    preds.to_parquet(out_dir / "predictions.parquet", index=False)
    metrics.to_parquet(out_dir / "race_metrics.parquet", index=False)

    ref = models[0].name
    L = ["# Backtest results\n", f"_Generated {date.today().isoformat()} by `f1predict backtest`._\n",
         f"Walk-forward over {seasons[0]}–{seasons[-1]}: each season the model is fitted on earlier seasons "
         "only, then predicts each race using only races before it. Forecast moment: after qualifying, "
         f"before the race. {metrics['race_id'].nunique()} races.\n",
         "## Overall\n",
         md_table(pd.DataFrame([{"metric": k, "meaning": v} for k, v in METRIC_NOTES.items()])), "\n",
         md_table(summarise(metrics), "{:.3f}"), "\n",
         "## Winner log-loss by season\n",
         md_table(metrics.pivot_table(index="year", columns="model", values="winner_logloss").reset_index(), "{:.3f}"),
         f"\nImprovement over `{ref}` (positive = better):\n",
         md_table(skill_vs(metrics, ref).reset_index(), "{:+.3f}"), "\n",
         "## Podium-probability calibration\n",
         "When a model says X%, how often does it happen? Good calibration: *observed* ≈ *predicted*.\n"]
    for m in models:
        L += [f"\n**{m.name}**\n", md_table(calibration(preds[preds["model"] == m.name], "p_podium").astype({"bucket": str}), "{:.3f}")]
    text = "\n".join(L) + "\n"
    ensure(REPORTS_DIR)
    (REPORTS_DIR / "backtest.md").write_text(text)
    return text


__all__ = ["run", "TEST_SEASONS", "METRICS"]
