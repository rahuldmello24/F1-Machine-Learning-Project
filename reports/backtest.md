# Backtest results

_Generated 2026-11-27 by `f1predict backtest`._

Walk-forward over 2022–2026: each season the model is fitted on earlier seasons only, then predicts each race using only races before it. Forecast moment: after qualifying, before the race. 113 races.

## Overall

| metric | meaning |
|---|---|
| winner_logloss | ↓ −log P(actual winner) |
| winner_hit | ↑ favourite won |
| podium_brier | ↓ podium probability error |
| points_brier | ↓ top-10 probability error |
| dnf_brier | ↓ retirement probability error |
| spearman | ↑ predicted vs actual order |
| top3_overlap | ↑ share of podium predicted |


| model | winner_logloss | winner_hit | podium_brier | points_brier | dnf_brier | spearman | top3_overlap |
|---|---|---|---|---|---|---|---|
| grid | 1.588 | 0.584 | 0.074 | 0.168 | 0.114 | 0.628 | 0.661 |
| grid+team_form | 1.483 | 0.575 | 0.069 | 0.155 | 0.114 | 0.652 | 0.670 |


## Winner log-loss by season

| year | grid | grid+team_form |
|---|---|---|
| 2022 | 1.826 | 1.675 |
| 2023 | 1.529 | 1.207 |
| 2024 | 1.728 | 1.665 |
| 2025 | 1.390 | 1.412 |
| 2026 | 1.467 | 1.446 |

Improvement over `grid` (positive = better):

| year | grid+team_form |
|---|---|
| 2022 | +0.152 |
| 2023 | +0.322 |
| 2024 | +0.062 |
| 2025 | -0.022 |
| 2026 | +0.021 |


## Podium-probability calibration

When a model says X%, how often does it happen? Good calibration: *observed* ≈ *predicted*.


**grid**

| bucket | n | predicted | observed |
|---|---|---|---|
| (-0.001, 0.02] | 141 | 0.018 | 0.007 |
| (0.02, 0.05] | 791 | 0.032 | 0.014 |
| (0.05, 0.1] | 465 | 0.071 | 0.019 |
| (0.1, 0.2] | 345 | 0.135 | 0.070 |
| (0.2, 0.35] | 226 | 0.242 | 0.323 |
| (0.35, 0.5] | 147 | 0.400 | 0.531 |
| (0.5, 0.65] | 72 | 0.512 | 0.708 |
| (0.65, 0.8] | 113 | 0.717 | 0.814 |

**grid+team_form**

| bucket | n | predicted | observed |
|---|---|---|---|
| (-0.001, 0.02] | 423 | 0.014 | 0.000 |
| (0.02, 0.05] | 681 | 0.032 | 0.004 |
| (0.05, 0.1] | 365 | 0.071 | 0.025 |
| (0.1, 0.2] | 267 | 0.145 | 0.131 |
| (0.2, 0.35] | 238 | 0.269 | 0.290 |
| (0.35, 0.5] | 141 | 0.423 | 0.525 |
| (0.5, 0.65] | 90 | 0.566 | 0.733 |
| (0.65, 0.8] | 64 | 0.718 | 0.875 |
| (0.8, 0.9] | 29 | 0.841 | 0.862 |
| (0.9, 1.0] | 2 | 0.912 | 1.000 |
